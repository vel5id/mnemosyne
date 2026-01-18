"""
Reasoning Client Module - LLM Interface for Mnemosyne Core V3.0

This module provides an async client for interacting with Ollama LLM models.
Supports tiered model selection with automatic fallback.

Key Features:
- Tiered models: Heavy (deepseek-r1) for complex reasoning, Light (phi3) for quick tasks
- Automatic fallback when heavy model fails or is overloaded
- VRAM-aware model selection
"""

import os
import logging
from typing import Optional
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class ModelTier(Enum):
    """Model tier selection."""
    HEAVY = "heavy"
    LIGHT = "light"
    AUTO = "auto"


class ReasoningClient:
    """
    Async client for Ollama LLM reasoning.
    
    Supports tiered model selection:
    - HEAVY: Complex reasoning (deepseek-r1:1.5b)
    - LIGHT: Quick inference (phi3:mini)
    - AUTO: Start with heavy, fallback to light on error
    """
    
    def __init__(
        self,
        ollama_host: Optional[str] = None,
        model_heavy: Optional[str] = None,
        model_light: Optional[str] = None,
        timeout: float = 120.0
    ):
        """
        Initialize the ReasoningClient.
        
        Args:
            ollama_host: Ollama server URL. Defaults to OLLAMA_LLM_HOST env var.
            model_heavy: Heavy reasoning model. Defaults to LLM_MODEL_HEAVY env var.
            model_light: Light fallback model. Defaults to LLM_MODEL_LIGHT env var.
            timeout: Request timeout in seconds.
        """
        self.ollama_host = ollama_host or os.getenv(
            "OLLAMA_LLM_HOST", "http://localhost:11435"
        )
        self.model_heavy = model_heavy or os.getenv(
            "LLM_MODEL_HEAVY", "deepseek-r1:1.5b"
        )
        self.model_light = model_light or os.getenv(
            "LLM_MODEL_LIGHT", "phi3:mini"
        )
        self.timeout = timeout
        
        self._client: Optional[httpx.AsyncClient] = None
        
        logger.info(
            f"ReasoningClient initialized. Host: {self.ollama_host}, "
            f"Heavy: {self.model_heavy}, Light: {self.model_light}"
        )
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.ollama_host,
                timeout=httpx.Timeout(self.timeout)
            )
        return self._client
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    def _get_model_for_tier(self, tier: ModelTier) -> str:
        """Get model name for the specified tier."""
        if tier == ModelTier.HEAVY:
            return self.model_heavy
        elif tier == ModelTier.LIGHT:
            return self.model_light
        else:
            return self.model_heavy  # AUTO starts with heavy
    
    async def reason(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        tier: ModelTier = ModelTier.AUTO,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> Optional[str]:
        """
        Generate reasoning response from LLM.
        
        Args:
            prompt: User prompt for reasoning.
            system_prompt: Optional system instructions.
            tier: Model tier selection (HEAVY, LIGHT, AUTO).
            temperature: Sampling temperature (0.0-1.0).
            max_tokens: Maximum tokens to generate.
        
        Returns:
            Generated response string, or None on error.
        """
        model = self._get_model_for_tier(tier)
        
        try:
            response = await self._call_ollama(
                model=model,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response
            
        except Exception as e:
            logger.error(f"Error with {model}: {e}")
            
            # Auto-fallback to light model
            if tier == ModelTier.AUTO and model != self.model_light:
                logger.info(f"Falling back to light model: {self.model_light}")
                try:
                    return await self._call_ollama(
                        model=self.model_light,
                        prompt=prompt,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                except Exception as fallback_error:
                    logger.error(f"Fallback failed: {fallback_error}")
            
            return None
    
    async def _call_ollama(
        self,
        model: str,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int
    ) -> str:
        """Make actual call to Ollama API."""
        client = await self._get_client()
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }
        
        logger.debug(f"Calling Ollama with model: {model}")
        
        response = await client.post("/api/chat", json=payload)
        response.raise_for_status()
        
        data = response.json()
        content = data.get("message", {}).get("content", "")
        
        logger.debug(f"Received response: {len(content)} chars")
        return content
    
    async def analyze_activity(
        self,
        activity_log: str,
        tier: ModelTier = ModelTier.AUTO
    ) -> Optional[str]:
        """
        Analyze user activity log and generate insights.
        
        Args:
            activity_log: Text describing user activities.
            tier: Model tier for analysis.
        
        Returns:
            Analysis summary or None on error.
        """
        system_prompt = """You are an AI assistant analyzing user activity logs.
Your task is to:
1. Summarize what the user was doing
2. Identify the main goals or tasks
3. Note any patterns or focus areas
4. Keep the summary concise (2-3 sentences)

Respond in the same language as the activity log."""
        
        return await self.reason(
            prompt=f"Analyze this activity log:\n\n{activity_log}",
            system_prompt=system_prompt,
            tier=tier,
            temperature=0.5,
            max_tokens=256
        )
    
    async def is_available(self) -> bool:
        """Check if Ollama server is available."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False
    
    async def list_models(self) -> list[str]:
        """List available models on the Ollama server."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False


# Singleton instance
_reasoning_client: Optional[ReasoningClient] = None


def get_reasoning_client() -> ReasoningClient:
    """Get or create the singleton ReasoningClient instance."""
    global _reasoning_client
    if _reasoning_client is None:
        _reasoning_client = ReasoningClient()
    return _reasoning_client
