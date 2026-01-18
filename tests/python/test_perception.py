"""
Unit tests for Perception and Security modules.

Tests cover:
- DataSanitizer (PII Redaction)
- OCREngine (OCR functionality)
- TextEngine (UI Automation - mocked)
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from core.security.sanitizer import DataSanitizer
from core.perception.ocr import OCREngine


class TestDataSanitizer(unittest.TestCase):
    """Test cases for DataSanitizer class."""

    def setUp(self):
        """Set up test fixtures."""
        self.sanitizer = DataSanitizer()

    def test_email_redaction(self):
        """Test that email addresses are redacted."""
        test_text = "Contact me at user@example.com for more info"
        result = self.sanitizer.clean_text(test_text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("user@example.com", result)

    def test_multiple_emails(self):
        """Test that multiple email addresses are redacted."""
        test_text = "Emails: alice@test.com, bob@example.org"
        result = self.sanitizer.clean_text(test_text)
        self.assertEqual(result.count("[REDACTED]"), 2)

    def test_ipv4_redaction(self):
        """Test that IPv4 addresses are redacted."""
        test_text = "Server at 192.168.1.1 is down"
        result = self.sanitizer.clean_text(test_text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("192.168.1.1", result)

    def test_credit_card_redaction(self):
        """Test that credit card numbers are redacted."""
        test_text = "Card number: 4532 1234 5678 9010"
        result = self.sanitizer.clean_text(test_text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("4532 1234 5678 9010", result)

    def test_openai_key_redaction(self):
        """Test that OpenAI API keys are redacted."""
        test_text = "API key: sk-1234567890abcdefghijklmnopqrstuvwxyz123456"
        result = self.sanitizer.clean_text(test_text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("sk-", result)

    def test_github_key_redaction(self):
        """Test that GitHub PAT keys are redacted."""
        test_text = "Token: ghp_1234567890abcdefghijklmnopqrstuvwxyz12345678"
        result = self.sanitizer.clean_text(test_text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("ghp_", result)

    def test_aws_key_redaction(self):
        """Test that AWS Access Keys are redacted."""
        test_text = "Access Key: AKIAIOSFODNN7EXAMPLE"
        result = self.sanitizer.clean_text(test_text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", result)

    def test_uuid_redaction(self):
        """Test that UUIDs are redacted."""
        test_text = "Session ID: 550e8400-e29b-41d4-a716-446655440000"
        result = self.sanitizer.clean_text(test_text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("550e8400-e29b-41d4-a716-446655440000", result)

    def test_combined_pii(self):
        """Test that multiple PII types are redacted together."""
        test_text = (
            "Contact user@example.com, "
            "server 192.168.1.1, "
            "card 4532123456789010"
        )
        result = self.sanitizer.clean_text(test_text)
        self.assertEqual(result.count("[REDACTED]"), 3)

    def test_empty_text(self):
        """Test that empty text is handled correctly."""
        result = self.sanitizer.clean_text("")
        self.assertEqual(result, "")

    def test_no_pii_text(self):
        """Test that text without PII is unchanged."""
        test_text = "Hello, this is a normal message"
        result = self.sanitizer.clean_text(test_text)
        self.assertEqual(result, test_text)

    def test_contains_pii(self):
        """Test the contains_pii method."""
        self.assertTrue(self.sanitizer.contains_pii("user@example.com"))
        self.assertTrue(self.sanitizer.contains_pii("192.168.1.1"))
        self.assertFalse(self.sanitizer.contains_pii("Hello world"))

    def test_clean_dict(self):
        """Test cleaning a dictionary."""
        test_dict = {
            "name": "John Doe",
            "email": "john@example.com",
            "ip": "192.168.1.1"
        }
        result = self.sanitizer.clean_dict(test_dict)
        self.assertEqual(result["name"], "John Doe")
        self.assertEqual(result["email"], "[REDACTED]")
        self.assertEqual(result["ip"], "[REDACTED]")

    def test_clean_list(self):
        """Test cleaning a list."""
        test_list = ["Hello", "user@example.com", "192.168.1.1"]
        result = self.sanitizer.clean_list(test_list)
        self.assertEqual(result[0], "Hello")
        self.assertEqual(result[1], "[REDACTED]")
        self.assertEqual(result[2], "[REDACTED]")


class TestOCREngine(unittest.TestCase):
    """Test cases for OCREngine class."""

    def setUp(self):
        """Set up test fixtures."""
        self.ocr = OCREngine()

    def test_initialization(self):
        """Test that OCREngine initializes correctly."""
        self.assertIsNotNone(self.ocr)

    @patch('core.perception.ocr.PYTESSERACT_AVAILABLE', False)
    def test_unavailable_ocr(self):
        """Test OCREngine behavior when pytesseract is not available."""
        ocr = OCREngine()
        self.assertFalse(ocr.is_available())
        result = ocr.extract_text_from_image("fake_path.png")
        self.assertEqual(result, "")

    @patch('core.perception.ocr.PYTESSERACT_AVAILABLE', True)
    @patch('core.perception.ocr.pytesseract')
    @patch('core.perception.ocr.Image')
    @patch('core.perception.ocr.Path')
    def test_extract_text_success(self, mock_path_class, mock_image, mock_pytesseract):
        """Test successful text extraction."""
        # Mock Path.exists() to return True
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_class.return_value = mock_path_instance
        
        # Mock the image and pytesseract
        mock_img_instance = MagicMock()
        mock_image.open.return_value = mock_img_instance
        mock_pytesseract.image_to_string.return_value = "Sample text"

        ocr = OCREngine()
        ocr.available = True  # Force available state

        result = ocr.extract_text_from_image("test.png")
        self.assertEqual(result, "Sample text")
        mock_path_class.assert_called_once_with("test.png")
        mock_image.open.assert_called_once_with("test.png")
        mock_pytesseract.image_to_string.assert_called_once()

    @patch('core.perception.ocr.PYTESSERACT_AVAILABLE', True)
    @patch('core.perception.ocr.pytesseract')
    @patch('core.perception.ocr.Image')
    @patch('core.perception.ocr.Path')
    def test_extract_text_file_not_found(self, mock_path, mock_image, mock_pytesseract):
        """Test OCR when image file doesn't exist."""
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = False
        mock_path.return_value = mock_path_instance

        ocr = OCREngine()
        ocr.available = True

        result = ocr.extract_text_from_image("nonexistent.png")
        self.assertEqual(result, "")

    @patch('core.perception.ocr.PYTESSERACT_AVAILABLE', True)
    @patch('core.perception.ocr.pytesseract')
    @patch('core.perception.ocr.Image')
    @patch('core.perception.ocr.Path')
    def test_extract_text_with_confidence(self, mock_path_class, mock_image, mock_pytesseract):
        """Test text extraction with confidence score."""
        # Mock Path.exists() to return True
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_class.return_value = mock_path_instance
        
        mock_img_instance = MagicMock()
        mock_image.open.return_value = mock_img_instance
        
        # Mock pytesseract data output
        mock_pytesseract.Output.DICT = 'dict'
        mock_pytesseract.image_to_string.return_value = "Sample text"
        mock_pytesseract.image_to_data.return_value = {
            'conf': ['95', '90', '85']
        }

        ocr = OCREngine()
        ocr.available = True

        text, confidence = ocr.extract_text_with_confidence("test.png")
        self.assertEqual(text, "Sample text")
        self.assertAlmostEqual(confidence, 0.9, places=1)


class TestTextEngine(unittest.TestCase):
    """Test cases for TextEngine class."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock the uiautomation and win32gui imports
        self.uiautomation_patcher = patch('core.perception.text_engine.UIA_AVAILABLE', True)
        self.win32gui_patcher = patch('core.perception.text_engine.WIN32_AVAILABLE', True)
        
        self.uiautomation_patcher.start()
        self.win32gui_patcher.start()
        
        from core.perception.text_engine import TextEngine
        self.text_engine = TextEngine()

    def tearDown(self):
        """Clean up patches."""
        self.uiautomation_patcher.stop()
        self.win32gui_patcher.stop()

    @patch('core.perception.text_engine.UIA_AVAILABLE', False)
    def test_unavailable_uia(self):
        """Test TextEngine when uiautomation is not available."""
        from core.perception.text_engine import TextEngine
        engine = TextEngine()
        result = engine.extract_context(12345)
        self.assertIsNone(result)

    @patch('core.perception.text_engine.UIA_AVAILABLE', True)
    @patch('core.perception.text_engine.WIN32_AVAILABLE', True)
    @patch('core.perception.text_engine.win32gui')
    def test_phantom_window_detection(self, mock_win32gui):
        """Test Phantom Window detection (window closed)."""
        mock_win32gui.IsWindow.return_value = False
        
        from core.perception.text_engine import TextEngine
        engine = TextEngine()
        result = engine.extract_context(12345)
        self.assertIsNone(result)

    @patch('core.perception.text_engine.UIA_AVAILABLE', True)
    @patch('core.perception.text_engine.WIN32_AVAILABLE', True)
    def test_extract_text_from_context(self):
        """Test extracting text from UI context."""
        from core.perception.text_engine import TextEngine
        engine = TextEngine()
        
        context = {
            'title': 'Test Window',
            'elements': [
                {'name': 'Button 1', 'value': 'Click me'},
                {'name': 'Label 1', 'value': 'Some text'}
            ]
        }
        
        result = engine.extract_text_from_context(context)
        self.assertIn('Test Window', result)
        self.assertIn('Button 1', result)
        self.assertIn('Click me', result)


if __name__ == '__main__':
    unittest.main()
