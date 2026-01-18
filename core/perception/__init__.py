"""
Perception module for Mnemosyne Core.

This module provides functionality for extracting information from the UI:
- UI Automation (Accessibility Tree)
- OCR (Optical Character Recognition)
- Vision processing
"""

from .text_engine import TextEngine
from .ocr import OCREngine

__all__ = ['TextEngine', 'OCREngine']
