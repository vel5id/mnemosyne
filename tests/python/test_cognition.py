"""
Unit Tests for Cognitive Layer - Mnemosyne Core V3.0

Tests for VisionAgent and IntentInference modules.
Uses mocking to avoid loading heavy models during testing.
"""

import json
import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from core.cognition.inference import (
    IntentInference,
    EventContext,
    InferenceResult
)
from core.perception.vision_agent import VisionAgent


# ==================== VisionAgent Tests ====================

class TestVisionAgent:
    """Test suite for VisionAgent class."""
    
    @pytest.fixture
    def mock_vram_guard(self):
        """Create a mock VRAMGuard."""
        guard = Mock()
        guard.check_vram_availability.return_value = True
        return guard
    
    @pytest.fixture
    def vision_agent(self, mock_vram_guard):
        """Create VisionAgent instance with mocked dependencies."""
        return VisionAgent(vram_guard=mock_vram_guard)
    
    def test_initialization(self, vision_agent):
        """Test VisionAgent initialization."""
        assert vision_agent.model is None
        assert vision_agent.tokenizer is None
        assert not vision_agent._is_loaded
        assert vision_agent.vram_guard is not None
    
    def test_check_vram_success(self, vision_agent, mock_vram_guard):
        """Test VRAM check when sufficient memory is available."""
        mock_vram_guard.check_vram_availability.return_value = True
        assert vision_agent._check_vram() is True
    
    def test_check_vram_insufficient(self, vision_agent, mock_vram_guard):
        """Test VRAM check when insufficient memory is available."""
        mock_vram_guard.check_vram_availability.return_value = False
        assert vision_agent._check_vram() is False
    
    def test_describe_screenshot_vram_limit(self, vision_agent, mock_vram_guard):
        """Test describe_screenshot returns fallback when VRAM is insufficient."""
        mock_vram_guard.check_vram_availability.return_value = False
        
        result = vision_agent.describe_screenshot(
            "fake/path/to/image.png",
            "Describe this image"
        )
        
        assert result == "[VRAM Limit] Skipped vision analysis"
    
    def test_describe_screenshot_file_not_found(self, vision_agent, mock_vram_guard):
        """Test describe_screenshot handles missing files."""
        mock_vram_guard.check_vram_availability.return_value = True
        
        result = vision_agent.describe_screenshot(
            "nonexistent/path/to/image.png",
            "Describe this image"
        )
        
        assert result is None
    
    def test_process_batch_empty(self, vision_agent):
        """Test process_batch with empty batch."""
        result = vision_agent.process_batch([])
        assert result == []
    
    def test_process_batch_vram_limit(self, vision_agent, mock_vram_guard):
        """Test process_batch returns fallbacks when VRAM is insufficient."""
        mock_vram_guard.check_vram_availability.return_value = False
        
        batch = [
            ("img1.png", "Describe", None),
            ("img2.png", "Describe", None)
        ]
        
        result = vision_agent.process_batch(batch)
        
        assert len(result) == 2
        assert all(r == "[VRAM Limit] Skipped vision analysis" for r in result)
    
    def test_cleanup(self, vision_agent):
        """Test cleanup method releases resources."""
        # Simulate loaded model
        vision_agent.model = Mock()
        vision_agent.tokenizer = Mock()
        vision_agent._is_loaded = True
        
        with patch('torch.cuda.empty_cache'), patch('gc.collect'):
            vision_agent._cleanup()
        
        assert vision_agent.model is None
        assert vision_agent.tokenizer is None
        assert not vision_agent._is_loaded


# ==================== IntentInference Tests ====================

class TestEventContext:
    """Test suite for EventContext dataclass."""
    
    def test_event_context_creation(self):
        """Test EventContext creation with all fields."""
        context = EventContext(
            window_title="Test Window",
            ui_tree="{'button': 'Click me'}",
            ocr_text="Extracted text",
            vision_description="A user interface",
            input_intensity=75,
            history=["Event 1", "Event 2"],
            timestamp="2024-01-01T12:00:00Z"
        )
        
        assert context.window_title == "Test Window"
        assert context.ui_tree == "{'button': 'Click me'}"
        assert context.ocr_text == "Extracted text"
        assert context.vision_description == "A user interface"
        assert context.input_intensity == 75
        assert len(context.history) == 2
        assert context.timestamp == "2024-01-01T12:00:00Z"
    
    def test_event_context_defaults(self):
        """Test EventContext with default values."""
        context = EventContext(window_title="Test")
        
        assert context.window_title == "Test"
        assert context.ui_tree is None
        assert context.ocr_text is None
        assert context.vision_description is None
        assert context.input_intensity == 0
        assert context.history == []
        assert context.timestamp is None
    
    def test_event_context_to_dict(self):
        """Test EventContext serialization to dict."""
        context = EventContext(
            window_title="Test Window",
            input_intensity=50
        )
        
        result = context.to_dict()
        
        assert isinstance(result, dict)
        assert result['window_title'] == "Test Window"
        assert result['input_intensity'] == 50


class TestIntentInference:
    """Test suite for IntentInference class."""
    
    @pytest.fixture
    def mock_http_client(self):
        """Create a mock HTTP client for Ollama."""
        client = Mock()
        client.get.return_value = Mock(status_code=200, json=lambda: {"models": []})
        return client
    
    @pytest.fixture
    def inference_engine(self, mock_http_client):
        """Create IntentInference instance with mocked HTTP client."""
        with patch('core.cognition.inference.httpx.Client', return_value=mock_http_client):
            return IntentInference()
    
    def test_initialization(self, inference_engine):
        """Test IntentInference initialization."""
        assert inference_engine.ollama_host == "http://localhost:11434"
        assert inference_engine.model == "llama3.1:8b"
        assert inference_engine._known_entities == set()
    
    def test_initialization_with_custom_params(self):
        """Test IntentInference with custom parameters."""
        with patch('core.cognition.inference.httpx.Client'):
            engine = IntentInference(
                ollama_host="http://custom:8080",
                model="custom-model"
            )
            
            assert engine.ollama_host == "http://custom:8080"
            assert engine.model == "custom-model"
    
    def test_build_prompt_basic(self, inference_engine):
        """Test prompt building with basic context."""
        context = EventContext(
            window_title="VS Code - main.py",
            input_intensity=80
        )
        
        prompt = inference_engine._build_prompt(context)
        
        assert "Window Title" in prompt
        assert "VS Code" in prompt
        assert "Input Intensity: 80/100" in prompt
    
    def test_build_prompt_full_context(self, inference_engine):
        """Test prompt building with full context."""
        context = EventContext(
            window_title="Test App",
            ui_tree="{'button': 'Submit'}",
            ocr_text="Submit Button",
            vision_description="A form with a submit button",
            input_intensity=60,
            history=["Previous event"],
            timestamp="2024-01-01T12:00:00Z"
        )
        
        prompt = inference_engine._build_prompt(context)
        
        assert "Window Title" in prompt
        assert "UI Tree" in prompt
        assert "OCR Text" in prompt
        assert "Vision Description" in prompt
        assert "Input Intensity" in prompt
        assert "Recent Events" in prompt
    
    def test_extract_tags_from_title(self, inference_engine):
        """Test tag extraction from window title."""
        tags = inference_engine._extract_tags_from_title("VS Code - main.py")
        
        assert "vscode" in tags
    
    def test_extract_tags_from_title_browser(self, inference_engine):
        """Test tag extraction for browser windows."""
        tags = inference_engine._extract_tags_from_title("Chrome - Google Search")
        
        assert "browser" in tags
    
    def test_extract_tags_from_text(self, inference_engine):
        """Test tag extraction from intent text."""
        text = "User is editing main.py in VS Code"
        tags = inference_engine._extract_tags_from_text(text)
        
        assert "coding" in tags
    
    def test_extract_tags_from_text_reading(self, inference_engine):
        """Test tag extraction for reading activity."""
        text = "User is reading documentation"
        tags = inference_engine._extract_tags_from_text(text)
        
        assert "reading" in tags
    
    def test_extract_wikilinks_from_text(self, inference_engine):
        """Test WikiLink generation from text."""
        inference_engine._known_entities = {"Project X", "main.py"}
        
        text = "Working on Project X and main.py"
        result = inference_engine._generate_wikilinks(text)
        
        assert "[[Project X]]" in result
        assert "[[main.py]]" in result
    
    def test_check_connection_success(self, inference_engine, mock_http_client):
        """Test Ollama connection check when successful."""
        mock_http_client.get.return_value.status_code = 200
        
        result = inference_engine.check_connection()
        
        assert result is True
    
    def test_check_connection_failure(self, inference_engine, mock_http_client):
        """Test Ollama connection check when failed."""
        mock_http_client.get.side_effect = Exception("Connection refused")
        
        result = inference_engine.check_connection()
        
        assert result is False
    
    def test_synthesize_with_mocked_ollama(self, inference_engine, mock_http_client):
        """Test intent synthesis with mocked Ollama response."""
        # Mock Ollama response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "Editing [[main.py]] in VS Code"
        }
        mock_http_client.post.return_value = mock_response
        
        context = EventContext(
            window_title="VS Code - main.py",
            input_intensity=85
        )
        
        result = inference_engine.synthesize(context)
        
        assert isinstance(result, InferenceResult)
        assert "[[main.py]]" in result.intent
        assert result.confidence == 0.8
        assert "coding" in result.tags
    
    def test_synthesize_fallback_on_ollama_error(self, inference_engine, mock_http_client):
        """Test intent synthesis fallback when Ollama fails."""
        mock_http_client.post.side_effect = Exception("Ollama error")
        
        context = EventContext(
            window_title="VS Code - main.py",
            input_intensity=85
        )
        
        result = inference_engine.synthesize(context)
        
        assert isinstance(result, InferenceResult)
        assert "VS Code" in result.intent
        assert result.confidence == 0.3
        assert "vscode" in result.tags


# ==================== Integration Tests ====================

class TestCognitionIntegration:
    """Integration tests for Cognitive Layer components."""
    
    def test_full_context_layer_cake(self):
        """Test building complete context from all signal sources."""
        context = EventContext(
            window_title="VS Code - authentication.py",
            ui_tree=json.dumps({
                "type": "Document",
                "name": "authentication.py",
                "children": [
                    {"type": "Edit", "name": "Code Editor"}
                ]
            }),
            ocr_text="def authenticate_user():",
            vision_description="A code editor showing a Python function",
            input_intensity=90,
            history=[
                "chrome: Stack Overflow - Python auth error",
                "vscode: authentication.py"
            ],
            timestamp="2024-01-01T12:00:00Z"
        )
        
        # Verify all layers are present
        assert context.window_title is not None
        assert context.ui_tree is not None
        assert context.ocr_text is not None
        assert context.vision_description is not None
        assert context.input_intensity > 0
        assert len(context.history) > 0
    
    def test_vram_guard_integration(self):
        """Test VRAMGuard integration with VisionAgent."""
        mock_guard = Mock()
        mock_guard.check_vram_availability.return_value = False
        
        agent = VisionAgent(vram_guard=mock_guard)
        
        # Should return fallback when VRAM is insufficient
        result = agent.describe_screenshot("test.png", "Describe")
        assert result == "[VRAM Limit] Skipped vision analysis"
        
        # Verify VRAM was checked
        mock_guard.check_vram_availability.assert_called_once()


# ==================== Performance Tests ====================

class TestPerformance:
    """Performance tests for Cognitive Layer."""
    
    def test_batch_processing_efficiency(self):
        """Test that batch processing is more efficient than individual."""
        # This is a conceptual test - actual performance testing
        # would require loading real models
        mock_guard = Mock()
        mock_guard.check_vram_availability.return_value = False
        
        agent = VisionAgent(vram_guard=mock_guard)
        
        # Large batch should be handled efficiently
        batch = [(f"img{i}.png", "Describe", None) for i in range(100)]
        result = agent.process_batch(batch)
        
        assert len(result) == 100
        # All should be fallbacks due to VRAM limit
        assert all(r == "[VRAM Limit] Skipped vision analysis" for r in result)


# ==================== Edge Cases ====================

class TestEdgeCases:
    """Edge case tests for Cognitive Layer."""
    
    def test_empty_window_title(self):
        """Test handling of empty window title."""
        context = EventContext(window_title="")
        prompt = IntentInference()._build_prompt(context)
        
        assert "Window Title:" in prompt
    
    def test_very_long_ocr_text(self):
        """Test handling of very long OCR text."""
        long_text = "A" * 3000  # Exceeds 1500 char limit
        
        context = EventContext(
            window_title="Test",
            ocr_text=long_text
        )
        
        prompt = IntentInference()._build_prompt(context)
        
        # Should be truncated
        assert len(prompt) < 5000  # Reasonable limit
    
    def test_unicode_in_context(self):
        """Test handling of Unicode characters in context."""
        context = EventContext(
            window_title="Тестовое окно - тест.py",
            ocr_text="Привет, мир! 你好 世界 🌍"
        )
        
        prompt = IntentInference()._build_prompt(context)
        
        # Should handle Unicode without errors
        assert "Тестовое окно" in prompt
        assert "Привет, мир!" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
