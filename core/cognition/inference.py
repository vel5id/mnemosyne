"""
Intent Inference Module - Cognitive Layer for Mnemosyne Core V3.0

This module implements the Intent Inference Engine that synthesizes multiple
signal sources (window title, UI tree, OCR, VLM description) into a coherent
human-readable intent description.

Key Features:
- Context Layer Cake integration
- Local LLM inference via Ollama (no external API calls)
- WikiLink generation for Obsidian integration
- PII sanitization before processing
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx
from core.security.sanitizer import DataSanitizer

# Configure logging
logger = logging.getLogger(__name__)


# System Prompt for Intent Analysis
SYSTEM_PROMPT = """You are an expert digital activity analyst for Mnemosyne Core. Your task is to synthesize multiple signal sources into a DETAILED, insightful description of what the user is actually doing.

INPUT SIGNALS (use ALL available):
1. Window Title: Application and document context
2. UI Tree: Interactive elements (buttons, menus, tabs)
3. OCR Text: Visible text content on screen
4. Vision Description: Visual analysis of the screenshot
5. Input Intensity: 0-30=passive viewing, 30-70=light interaction, 70-100=active work
6. History: Recent activity for workflow context

ANALYSIS REQUIREMENTS:
- NEVER just repeat the window title. Infer the actual activity.
- Be SPECIFIC about what the user is working on (file names, topics, tools used).
- Consider the APPLICATION context:
  - VS Code / IDE: What code? Which file? Debugging or writing?
  - Browser: Reading docs? Searching? Watching video?
  - AI Assistant (Antigravity/Cursor/Copilot): Reviewing plan? Debugging? Code review?
  - Terminal: Running tests? Building? Deploying?
  - Chat apps: Meeting? Discussion topic?
- Use Input Intensity to distinguish: reading docs (low) vs coding (high)
- Generate WikiLinks [[like this]] for: files, projects, technologies, concepts

EXAMPLES (notice the detail level):
- Window "main.py - VS Code" + high intensity = "Actively coding [[main.py]] - implementing new feature"
- Window "Antigravity - Plan" + low intensity = "Reviewing [[implementation plan]] in AI assistant - planning next steps"
- Window "GitHub PR #123" + medium = "Reviewing pull request for [[authentication]] feature - checking code changes"
- Window "Stack Overflow" + low = "Researching [[Redis Streams]] - reading about consumer groups"
- Window "Discord - #dev" + medium = "Discussing [[project architecture]] with team in Discord"

OUTPUT FORMAT:
Return a single line describing the intent. Be specific. No explanations needed.
If limited info, still provide your best inference based on app type and title keywords.
"""


@dataclass
class EventContext:
    """Data class representing the context of a user event."""
    window_title: str
    ui_tree: Optional[str] = None
    ocr_text: Optional[str] = None
    vision_description: Optional[str] = None
    input_intensity: int = 0  # 0-100 scale
    history: list[str] = field(default_factory=list)
    screenshot_path: Optional[str] = None  # Path for VLM (if needed)
    timestamp: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert context to dictionary for serialization."""
        return {
            'window_title': self.window_title,
            'ui_tree': self.ui_tree,
            'ocr_text': self.ocr_text,
            'vision_description': self.vision_description,
            'input_intensity': self.input_intensity,
            'history': self.history,
            'timestamp': self.timestamp
        }


@dataclass
class InferenceResult:
    """Data class representing the result of intent inference."""
    intent: str
    tags: list[str]
    confidence: float
    raw_response: Optional[str] = None


class IntentInference:
    """
    Intent Inference Engine using local LLM (Ollama).
    
    This class synthesizes multiple signal sources to generate a coherent
    description of user intent. It uses Ollama for local inference to
    preserve privacy and reduce VRAM usage.
    """
    
    # Ollama configuration
    OLLAMA_HOST = "http://localhost:11434"
    DEFAULT_MODEL = "deepseek-r1:1.5b"
    FALLBACK_MODEL = "phi3:mini"
    
    # Request timeout (seconds)
    TIMEOUT = 60
    
    def __init__(
        self,
        ollama_host: Optional[str] = None,
        model: Optional[str] = None,
        obsidian_vault_path: Optional[str] = None
    ):
        """
        Initialize the Intent Inference Engine.
        
        Args:
            ollama_host: URL of the Ollama API server. Defaults to localhost:11434.
            model: Model name to use for inference. Defaults to llama3.1:8b.
            obsidian_vault_path: Path to Obsidian vault for WikiLink generation.
        """
        self.ollama_host = ollama_host or os.environ.get('OLLAMA_LLM_HOST', self.OLLAMA_HOST)
        self.model = model or os.environ.get('LLM_MODEL_HEAVY', self.DEFAULT_MODEL)
        self.obsidian_vault_path = Path(obsidian_vault_path) if obsidian_vault_path else None
        self._client = httpx.Client(timeout=self.TIMEOUT)
        self._sanitizer = DataSanitizer()  # Cache single instance
        
        # Cache of known entities for WikiLink generation
        self._known_entities: set[str] = set()
        
        # Load known entities from Obsidian vault if provided
        if self.obsidian_vault_path:
            self._load_obsidian_entities()
        
        logger.info(f"IntentInference initialized. Model: {self.model}, Host: {self.ollama_host}")
    
    def _load_obsidian_entities(self) -> None:
        """
        Load known entities from Obsidian vault for WikiLink generation.
        
        Scans the vault directory and extracts note names for potential linking.
        """
        if not self.obsidian_vault_path or not self.obsidian_vault_path.exists():
            logger.warning(f"Obsidian vault not found: {self.obsidian_vault_path}")
            return
        
        try:
            # Scan for .md files
            for md_file in self.obsidian_vault_path.rglob("*.md"):
                # Extract note name (filename without extension)
                note_name = md_file.stem
                self._known_entities.add(note_name)
            
            logger.info(f"Loaded {len(self._known_entities)} entities from Obsidian vault")
            
        except Exception as e:
            logger.error(f"Error loading Obsidian entities: {e}")
    
    def _generate_wikilinks(self, text: str) -> str:
        """
        Generate WikiLinks for known entities in the text.
        
        Args:
            text: Input text to process.
        
        Returns:
            Text with WikiLinks added for matching entities.
        """
        if not self._known_entities:
            return text
        
        result = text
        # Sort entities by length (longest first) to avoid partial matches
        sorted_entities = sorted(self._known_entities, key=len, reverse=True)
        
        for entity in sorted_entities:
            # Case-insensitive replacement
            pattern = re.compile(re.escape(entity), re.IGNORECASE)
            # Only link if not already linked
            result = pattern.sub(f"[[{entity}]]", result)
        
        return result
    
    def _build_prompt(self, context: EventContext) -> str:
        """
        Build the user prompt from event context.
        
        Args:
            context: EventContext containing all signal sources.
        
        Returns:
            Formatted prompt string for the LLM.
        """
        prompt_parts = []
        
        # Sanitize all text inputs (use cached sanitizer)
        safe_title = self._sanitizer.clean_text(context.window_title)
        
        prompt_parts.append(f"Window Title: {safe_title}")
        
        if context.ui_tree:
            safe_ui = self._sanitizer.clean_text(context.ui_tree)
            # Truncate UI tree to avoid token overflow
            if len(safe_ui) > 2000:
                safe_ui = safe_ui[:2000] + "..."
            prompt_parts.append(f"UI Tree: {safe_ui}")
        
        if context.ocr_text:
            safe_ocr = self._sanitizer.clean_text(context.ocr_text)
            if len(safe_ocr) > 1500:
                safe_ocr = safe_ocr[:1500] + "..."
            prompt_parts.append(f"OCR Text: {safe_ocr}")
        
        if context.vision_description:
            safe_vision = self._sanitizer.clean_text(context.vision_description)
            prompt_parts.append(f"Vision Description: {safe_vision}")
        
        prompt_parts.append(f"Input Intensity: {context.input_intensity}/100")
        
        if context.history:
            safe_history = [self._sanitizer.clean_text(h) for h in context.history]
            prompt_parts.append(f"Recent Events: {', '.join(safe_history)}")
        
        return "\n\n".join(prompt_parts)
    
    def _call_ollama(self, prompt: str) -> Optional[str]:
        """
        Call Ollama API for inference.
        
        Args:
            prompt: The user prompt to send to the model.
        
        Returns:
            Model response string, or None if the call failed.
        """
        try:
            payload = {
                "model": self.model,
                "system": SYSTEM_PROMPT,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,  # Lower temperature for more deterministic output
                    "num_predict": 200   # Limit output length
                }
            }
            
            response = self._client.post(
                f"{self.ollama_host}/api/generate",
                json=payload
            )
            
            response.raise_for_status()
            data = response.json()
            
            return data.get("response", "").strip()
            
        except httpx.ConnectError:
            logger.error(f"Failed to connect to Ollama at {self.ollama_host}")
            return None
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama API error: {e.response.status_code} - {e.response.text}")
            return None
            
        except Exception as e:
            logger.error(f"Unexpected error calling Ollama: {e}")
            return None
    
    def synthesize(self, context: EventContext) -> InferenceResult:
        """
        Synthesize intent from event context.
        
        Args:
            context: EventContext containing all signal sources.
        
        Returns:
            InferenceResult with intent description, tags, and confidence.
        """
        # Build prompt from context
        prompt = self._build_prompt(context)
        
        # Call LLM
        # 1. Main Inference
        raw_response = self._call_ollama(prompt)
        
        if raw_response is None:
            # Fallback: simple intent from window title
            logger.warning("LLM inference failed, using fallback")
            intent = f"Activity in {self._sanitizer.clean_text(context.window_title)}"
            confidence = 0.3
            tags = self._extract_tags_from_title(context.window_title)
        else:
            # Post-process response
            intent = self._generate_wikilinks(raw_response)
            confidence = 0.8  # Assume good confidence from LLM
            tags = self._extract_tags_from_text(raw_response)
        
        return InferenceResult(
            intent=intent,
            tags=tags,
            confidence=confidence,
            raw_response=raw_response
        )
    
    def _extract_tags_from_title(self, title: str) -> list[str]:
        """
        Extract simple tags from window title.
        
        Args:
            title: Window title string.
        
        Returns:
            List of tag strings.
        """
        tags = []
        safe_title = self._sanitizer.clean_text(title)
        
        # Common application patterns
        app_patterns = {
            r'VS Code': 'vscode',
            r'Visual Studio': 'visualstudio',
            r'Chrome': 'browser',
            r'Firefox': 'browser',
            r'Edge': 'browser',
            r'Word': 'office',
            r'Excel': 'office',
            r'PowerPoint': 'office',
            r'Outlook': 'email',
            r'Terminal': 'terminal',
            r'PowerShell': 'terminal',
            r'Git': 'git',
            r'GitHub': 'github',
            r'Discord': 'communication',
            r'Slack': 'communication',
            r'Teams': 'communication',
        }
        
        for pattern, tag in app_patterns.items():
            if re.search(pattern, safe_title, re.IGNORECASE):
                tags.append(tag)
        
        return tags
    
    def _extract_tags_from_text(self, text: str) -> list[str]:
        """
        Extract tags from intent text.
        
        Args:
            text: Intent description text.
        
        Returns:
            List of tag strings.
        """
        tags = []
        
        # Activity type patterns
        activity_patterns = {
            r'\b(editing|coding|programming|debugging)\b': 'coding',
            r'\b(reading|viewing|browsing)\b': 'reading',
            r'\b(writing|typing|composing)\b': 'writing',
            r'\b(debugging|fixing|troubleshooting)\b': 'debugging',
            r'\b(reviewing|analyzing)\b': 'reviewing',
            r'\b(meeting|call|video)\b': 'meeting',
            r'\b(email|message|chat)\b': 'communication',
        }
        
        for pattern, tag in activity_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                tags.append(tag)
        
        # Extract WikiLinks as tags
        wikilinks = re.findall(r'\[\[([^\]]+)\]\]', text)
        tags.extend(wikilinks)
        
        return list(set(tags))  # Remove duplicates
    
    def check_connection(self) -> bool:
        """
        Check if Ollama is available and responsive.
        
        Returns:
            True if Ollama is available, False otherwise.
        """
        try:
            response = self._client.get(f"{self.ollama_host}/api/tags")
            response.raise_for_status()
            logger.info("Ollama connection verified")
            return True
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")
            return False
    
    # =========================================================================
    # Session Summarization (Phase 6)
    # =========================================================================
    
    SESSION_SUMMARY_PROMPT = """Summarize this user activity session:

Session Details:
- Duration: {duration_minutes} minutes
- Primary Application: {primary_process}
- Primary Window: {primary_window}
- Window Transitions: {transitions}
- Activity Level: {intensity_level} (avg intensity: {avg_intensity:.0f}/100)
- Event Count: {event_count}

Requirements:
- Provide a 1-2 sentence summary of what the user accomplished.
- Be SPECIFIC about the work done (not just "worked in VS Code").
- Generate WikiLinks [[like this]] for key files, projects, or concepts.
- Focus on the outcome, not the process.

Example outputs:
- "Debugging [[Redis consumer]] integration in [[mnemosyne]] project, then researched [[XREADGROUP]] patterns"
- "Reviewing and refactoring [[inference.py]] for better session aggregation"
- "Writing documentation for [[VisionAgent]] API, testing edge cases"

Summary:"""

    def summarize_session(
        self,
        duration_minutes: float,
        primary_process: str,
        primary_window: str,
        transitions: list[str],
        avg_intensity: float,
        event_count: int
    ) -> Optional[str]:
        """
        Generate an LLM summary for a completed session.
        
        Args:
            duration_minutes: Session duration in minutes.
            primary_process: Main application used.
            primary_window: Main window title.
            transitions: List of window transitions during session.
            avg_intensity: Average input intensity (0-100).
            event_count: Number of events in session.
        
        Returns:
            LLM-generated summary string, or None on failure.
        """
        # Determine intensity level description
        if avg_intensity < 30:
            intensity_level = "low (passive viewing/reading)"
        elif avg_intensity < 70:
            intensity_level = "medium (light interaction)"
        else:
            intensity_level = "high (active work/coding)"
        
        # Format transitions (limit to 5 for prompt)
        transitions_str = ", ".join(transitions[:5])
        if len(transitions) > 5:
            transitions_str += f" (+{len(transitions) - 5} more)"
        
        prompt = self.SESSION_SUMMARY_PROMPT.format(
            duration_minutes=duration_minutes,
            primary_process=primary_process,
            primary_window=primary_window[:100],  # Truncate long titles
            transitions=transitions_str,
            intensity_level=intensity_level,
            avg_intensity=avg_intensity,
            event_count=event_count
        )
        
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.4,  # Slightly higher for creative summaries
                    "num_predict": 150
                }
            }
            
            response = self._client.post(
                f"{self.ollama_host}/api/generate",
                json=payload
            )
            response.raise_for_status()
            
            summary = response.json().get("response", "").strip()
            
            # Post-process: add WikiLinks if missing
            summary = self._generate_wikilinks(summary)
            
            logger.debug(f"Session summary generated: {summary[:50]}...")
            return summary
            
        except Exception as e:
            logger.error(f"Session summarization failed: {e}")
            # Fallback: basic summary
            return f"Activity in {primary_process} - {primary_window[:50]}"
    
    def __del__(self):
        """Cleanup HTTP client on deletion."""
        if hasattr(self, '_client'):
            self._client.close()

