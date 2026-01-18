"""
OCR (Optical Character Recognition) Engine Module.

This module provides OCR functionality using Tesseract as a fallback
when UI Automation is not available or sufficient.

Handles graceful degradation when Tesseract is not installed.
"""

import logging
from typing import Optional
from pathlib import Path

# Try to import pytesseract - if not available, the module will still load
# but extract_text_from_image will return empty string
try:
    import pytesseract
    from PIL import Image
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False
    pytesseract = None
    Image = None

logger = logging.getLogger(__name__)


class OCREngine:
    """
    OCR Engine using Tesseract for text extraction from images.
    
    This is a fallback mechanism when UI Automation is not available
    or when dealing with "Phantom Windows" (closed windows).
    """
    
    def __init__(self, tesseract_path: Optional[str] = None, 
                 lang: str = 'eng+rus'):
        """
        Initialize the OCREngine.
        
        Args:
            tesseract_path: Path to tesseract.exe. If None, uses PATH.
            lang: Language(s) for OCR (e.g., 'eng', 'rus', 'eng+rus').
        """
        self.lang = lang
        self.available = False
        
        if not PYTESSERACT_AVAILABLE:
            logger.warning(
                "pytesseract or PIL not available. "
                "OCREngine will not be able to extract text. "
                "Install with: pip install pytesseract pillow"
            )
            return
        
        if tesseract_path:
            try:
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
                logger.info("Tesseract path set to: %s", tesseract_path)
            except Exception as e:
                logger.warning("Failed to set Tesseract path: %s", e)
        
        # Check if Tesseract is available
        self.available = self._check_tesseract()
        
        if self.available:
            logger.info("OCREngine initialized successfully (lang: %s)", lang)
        else:
            logger.warning(
                "Tesseract not found in PATH. OCR will not work. "
                "Install Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki"
            )
    
    def _check_tesseract(self) -> bool:
        """
        Check if Tesseract is available.
        
        Returns:
            True if Tesseract is available, False otherwise.
        """
        try:
            version = pytesseract.get_tesseract_version()
            logger.debug("Tesseract version: %s", version)
            return True
        except Exception as e:
            logger.debug("Tesseract check failed: %s", e)
            return False
    
    def extract_text_from_image(self, image_path: str) -> str:
        """
        Extract text from an image file.
        
        Args:
            image_path: Path to the image file.
            
        Returns:
            Extracted text, or empty string if:
            - OCR is not available
            - Image file doesn't exist
            - Error during extraction
        """
        if not self.available:
            logger.debug("OCR not available, returning empty string")
            return ''
        
        # Check if image exists
        image_file = Path(image_path)
        if not image_file.exists():
            logger.warning("Image file not found: %s", image_path)
            return ''
        
        try:
            # Open image
            image = Image.open(image_path)
            
            # Extract text using Tesseract
            text = pytesseract.image_to_string(image, lang=self.lang)
            
            # Clean up the text
            text = text.strip()
            
            if text:
                logger.debug("Extracted %d characters from %s", len(text), image_path)
            else:
                logger.debug("No text extracted from %s", image_path)
            
            return text
            
        except Exception as e:
            logger.error("Error extracting text from %s: %s", image_path, e)
            return ''
    
    def extract_text_from_image_bytes(self, image_bytes: bytes) -> str:
        """
        Extract text from image bytes.
        
        Args:
            image_bytes: Raw image data as bytes.
            
        Returns:
            Extracted text, or empty string on error.
        """
        if not self.available:
            logger.debug("OCR not available, returning empty string")
            return ''
        
        try:
            # Open image from bytes
            from io import BytesIO
            image = Image.open(BytesIO(image_bytes))
            
            # Extract text using Tesseract
            text = pytesseract.image_to_string(image, lang=self.lang)
            
            # Clean up the text
            text = text.strip()
            
            return text
            
        except Exception as e:
            logger.error("Error extracting text from image bytes: %s", e)
            return ''
    
    def extract_text_with_confidence(self, image_path: str) -> tuple[str, float]:
        """
        Extract text from an image with confidence score.
        
        Args:
            image_path: Path to the image file.
            
        Returns:
            Tuple of (extracted_text, confidence_score).
            Confidence is 0.0 if OCR is not available or on error.
        """
        if not self.available:
            return '', 0.0
        
        # Check if image exists
        image_file = Path(image_path)
        if not image_file.exists():
            logger.warning("Image file not found: %s", image_path)
            return '', 0.0
        
        try:
            # Open image
            image = Image.open(image_path)
            
            # Extract text with confidence data
            data = pytesseract.image_to_data(
                image, 
                lang=self.lang, 
                output_type=pytesseract.Output.DICT
            )
            
            # Calculate average confidence
            confidences = [int(c) for c in data['conf'] if int(c) > 0]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            # Extract text
            text = pytesseract.image_to_string(image, lang=self.lang).strip()
            
            logger.debug("Extracted text with confidence %.2f%%", avg_confidence)
            
            return text, avg_confidence / 100.0  # Convert to 0-1 range
            
        except Exception as e:
            logger.error("Error extracting text with confidence from %s: %s", 
                        image_path, e)
            return '', 0.0
    
    def is_available(self) -> bool:
        """
        Check if OCR is available.
        
        Returns:
            True if OCR is available, False otherwise.
        """
        return self.available


# Singleton instance for easy import
_ocr_engine_instance = None


def get_ocr_engine() -> OCREngine:
    """Get or create the singleton OCREngine instance."""
    global _ocr_engine_instance
    if _ocr_engine_instance is None:
        _ocr_engine_instance = OCREngine()
    return _ocr_engine_instance
