"""
Vision Agent Module - VLM Engine for Mnemosyne Core V3.0

This module implements the Vision Language Model (VLM) agent with support
for both local HuggingFace models and Ollama-based inference.

Key Features:
- Batch processing for VRAM efficiency
- Switchable backends: Ollama (Docker) or Local (HuggingFace)
- Switchable models: MiniCPM-V (light) or Qwen2.5-VL (heavy)
- Automatic model loading/unloading based on VRAM availability
- Integration with Guardrails for resource management
"""

import gc
import os
import io
import base64
import logging
from pathlib import Path
from typing import Optional, Tuple
from enum import Enum

import httpx
from PIL import Image

# Conditional torch import for local backend
try:
    import torch
    from transformers import AutoModel, AutoTokenizer
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None

from core.system.guardrails import SystemGuard

logger = logging.getLogger(__name__)


class VLMBackend(Enum):
    """VLM backend selection."""
    OLLAMA = "ollama"
    LOCAL = "local"


class VLMModel(Enum):
    """Available VLM models."""
    MINICPM_V = "minicpm-v"
    QWEN_VL = "qwen2.5-vl:7b"


class VisionAgent:
    """
    Vision Language Model Agent with multiple backend support.
    
    Supports:
    - Ollama backend: Uses Docker container for inference
    - Local backend: Uses HuggingFace transformers (requires torch)
    
    Models:
    - minicpm-v: Faster, lighter (~6GB VRAM)
    - qwen2.5-vl:7b: Better OCR, heavier (~8GB VRAM)
    """
    
    # Local model configuration (HuggingFace)
    LOCAL_MODEL_NAME = "openbmb/MiniCPM-V-2_6-int4"
    TRUST_REMOTE_CODE = True
    
    # VRAM requirements (in MB)
    MIN_VRAM_MB = 6000
    
    def __init__(
        self,
        vram_guard: Optional[SystemGuard] = None,
        backend: Optional[str] = None,
        model: Optional[str] = None,
        ollama_host: Optional[str] = None
    ):
        """
        Initialize the Vision Agent.
        
        Args:
            vram_guard: Optional SystemGuard instance for VRAM checks.
            backend: "ollama" or "local". Defaults to VLM_BACKEND env var.
            model: Model name. Defaults to VLM_MODEL env var.
            ollama_host: Ollama server URL. Defaults to OLLAMA_VLM_HOST env var.
        """
        self.vram_guard = vram_guard or SystemGuard()
        
        # Backend configuration
        backend_str = backend or os.getenv("VLM_BACKEND", "ollama")
        self.backend = VLMBackend(backend_str.lower())
        
        # Model configuration
        self.model_name = model or os.getenv("VLM_MODEL", "minicpm-v")
        
        # Ollama configuration
        self.ollama_host = ollama_host or os.getenv(
            "OLLAMA_VLM_HOST", "http://localhost:11434"
        )
        
        # Local model state (for HuggingFace backend)
        self.model = None
        self.tokenizer = None
        self._is_loaded = False
        
        # HTTP client for Ollama
        self._http_client: Optional[httpx.Client] = None
        
        # Device detection
        if TORCH_AVAILABLE:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = "cpu"
        
        logger.info(
            f"VisionAgent initialized. Backend: {self.backend.value}, "
            f"Model: {self.model_name}, Device: {self.device}"
        )
    
    def _get_http_client(self) -> httpx.Client:
        """Get or create HTTP client for Ollama."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.Client(
                base_url=self.ollama_host,
                timeout=httpx.Timeout(120.0)
            )
        return self._http_client
    
    def _check_vram(self) -> bool:
        """Check if sufficient VRAM is available."""
        if self.device == "cpu":
            logger.warning("VisionAgent running on CPU - performance will be degraded")
            return True
        
        return self.vram_guard.check_vram_availability(threshold_mb=self.MIN_VRAM_MB)
    
    def load_model(self) -> bool:
        """Load the local VLM model into VRAM (HuggingFace backend only)."""
        if self.backend == VLMBackend.OLLAMA:
            # Ollama handles model loading automatically
            return True
        
        if not TORCH_AVAILABLE:
            logger.error("Torch not available for local backend")
            return False
        
        if self._is_loaded:
            return True
        
        if not self._check_vram():
            logger.warning(f"Insufficient VRAM (< {self.MIN_VRAM_MB}MB)")
            return False
        
        try:
            logger.info(f"Loading model {self.LOCAL_MODEL_NAME}...")
            
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.LOCAL_MODEL_NAME,
                trust_remote_code=self.TRUST_REMOTE_CODE
            )
            
            self.model = AutoModel.from_pretrained(
                self.LOCAL_MODEL_NAME,
                trust_remote_code=self.TRUST_REMOTE_CODE,
                torch_dtype=torch.float16,
                device_map="auto"
            )
            
            self.model.eval()
            self._is_loaded = True
            
            if self.device == "cuda":
                vram_used = torch.cuda.memory_allocated() / 1024 / 1024
                logger.info(f"VRAM used: {vram_used:.2f} MB")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self._cleanup()
            return False
    
    def unload_model(self) -> None:
        """Unload the local VLM model and free VRAM."""
        if self.backend == VLMBackend.OLLAMA:
            return
        
        if not self._is_loaded:
            return
        
        logger.info("Unloading model...")
        self._cleanup()
    
    def _cleanup(self) -> None:
        """Internal cleanup method."""
        if self.model is not None:
            del self.model
            self.model = None
        
        if self.tokenizer is not None:
            del self.tokenizer
            self.tokenizer = None
        
        self._is_loaded = False
        
        if TORCH_AVAILABLE and self.device == "cuda":
            torch.cuda.empty_cache()
        
        gc.collect()
    
    def _image_to_base64(self, image_path: str) -> str:
        """Convert image to base64 for Ollama API."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    
    def describe_screenshot(
        self,
        image_path: str,
        prompt: str = "Describe what you see in this image. Focus on the user interface, actions being performed, and any visible text.",
        window_rect: Optional[Tuple[int, int, int, int]] = None,
        image_data: Optional[bytes] = None
    ) -> Optional[str]:
        """
        Analyze a screenshot and generate a description.
        
        Args:
            image_path: Path to the screenshot image file (ignored if image_data provided).
            prompt: Custom prompt for the VLM.
            window_rect: Optional tuple (left, top, right, bottom) for cropping.
            image_data: Optional raw bytes of the image (RAM mode).
        
        Returns:
            String description, or None if analysis failed.
        """
        if image_data is None:
            image_file = Path(image_path)
            if not image_file.exists():
                logger.error(f"Image file not found: {image_path}")
                return None
        
        # Handle window cropping (RAM mode support needed)
        if window_rect is not None:
            try:
                if image_data:
                    image = Image.open(io.BytesIO(image_data)).convert('RGB')
                else:
                    image = Image.open(image_path).convert('RGB')
                
                left, top, right, bottom = window_rect
                img_width, img_height = image.size
                left = max(0, min(left, img_width))
                top = max(0, min(top, img_height))
                right = max(left, min(right, img_width))
                bottom = max(top, min(bottom, img_height))
                
                if right > left and bottom > top:
                    image = image.crop((left, top, right, bottom))
                    # Save to RAM buffer for consistency
                    buf = io.BytesIO()
                    image.save(buf, format="JPEG")
                    image_data = buf.getvalue()
                    # We updated image_data, so path is irrelevant now
            except Exception as e:
                logger.error(f"Cropping error: {e}")

        if self.backend == VLMBackend.OLLAMA:
            return self._describe_ollama(image_path, prompt, image_data)
        else:
            return self._describe_local(image_path, prompt, window_rect, image_data)
    
    def _describe_ollama(self, image_path: str, prompt: str, image_data: Optional[bytes] = None) -> Optional[str]:
        """Describe image using Ollama API."""
        try:
            client = self._get_http_client()
            
            if image_data:
                image_b64 = base64.b64encode(image_data).decode("utf-8")
            else:
                image_b64 = self._image_to_base64(image_path)
            
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "images": [image_b64],
                "stream": False
            }
            
            logger.debug(f"Calling Ollama VLM: {self.model_name}")
            response = client.post("/api/generate", json=payload)
            response.raise_for_status()
            
            data = response.json()
            result = data.get("response", "")
            
            logger.debug(f"VLM response: {len(result)} chars")
            return result
            
        except httpx.ConnectError:
            logger.error(f"Cannot connect to Ollama at {self.ollama_host}")
            return "[VLM Error] Ollama server not available"
        except Exception as e:
            logger.error(f"Ollama VLM error: {e}")
            return None
    
    def _describe_local(
        self,
        image_path: str,
        prompt: str,
        window_rect: Optional[Tuple[int, int, int, int]],
        image_data: Optional[bytes] = None
    ) -> Optional[str]:
        """Describe image using local HuggingFace model."""
        if not self._check_vram():
            return "[VRAM Limit] Skipped vision analysis"
        
        if not self._is_loaded:
            if not self.load_model():
                return "[VRAM Limit] Skipped vision analysis"
        
        try:
            if image_data:
                image = Image.open(io.BytesIO(image_data)).convert('RGB')
            else:
                image = Image.open(image_path).convert('RGB')
            
            msgs = [{'role': 'user', 'content': [image, prompt]}]
            
            response = self.model.chat(
                image=None,
                msgs=msgs,
                tokenizer=self.tokenizer,
                sampling=True,
                temperature=0.7,
                max_new_tokens=512
            )
            
            return response
            
        except Exception as e:
            if TORCH_AVAILABLE and "CUDA" in str(e).upper():
                logger.error("CUDA OOM - freeing VRAM")
                self.unload_model()
                return "[VRAM Limit] Skipped vision analysis"
            logger.error(f"Vision inference error: {e}")
            return None
    
    def process_batch(
        self,
        batch: list[Tuple[str, str, Optional[Tuple[int, int, int, int]]]]
    ) -> list[Optional[str]]:
        """
        Process a batch of screenshots.
        
        Args:
            batch: List of tuples (image_path, prompt, window_rect)
        
        Returns:
            List of descriptions.
        """
        if not batch:
            return []
        
        if self.backend == VLMBackend.LOCAL:
            if not self._check_vram():
                return ["[VRAM Limit] Skipped"] * len(batch)
            
            if not self.load_model():
                return ["[VRAM Limit] Skipped"] * len(batch)
        
        try:
            results = []
            for image_path, prompt, window_rect in batch:
                result = self.describe_screenshot(image_path, prompt, window_rect)
                results.append(result)
            return results
        finally:
            if self.backend == VLMBackend.LOCAL:
                self.unload_model()
    
    def switch_model(self, model_name: str) -> None:
        """
        Switch to a different VLM model.
        
        Args:
            model_name: New model name (e.g., "minicpm-v" or "qwen2.5-vl:7b")
        """
        if self.backend == VLMBackend.LOCAL:
            self.unload_model()
        
        self.model_name = model_name
        logger.info(f"Switched VLM model to: {model_name}")
    
    def is_available(self) -> bool:
        """Check if VLM backend is available."""
        if self.backend == VLMBackend.OLLAMA:
            try:
                client = self._get_http_client()
                response = client.get("/api/tags")
                return response.status_code == 200
            except Exception:
                return False
        else:
            return TORCH_AVAILABLE and (self.device == "cuda" or True)
    
    def close(self) -> None:
        """Close resources."""
        if self._http_client and not self._http_client.is_closed:
            self._http_client.close()
        self.unload_model()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
