"""
Mnemosyne Core V5.0 - Event Processor Module

Handles event context extraction, VLM/OCR processing, and intent inference.
Extracted from Brain class to follow Single Responsibility Principle.

Usage:
    processor = EventProcessor(sanitizer, text_engine, ocr_engine, vision_agent, inference, guard, db)
    await processor.process_batch(events)
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from core.security.sanitizer import DataSanitizer
from core.perception.text_engine import TextEngine
from core.perception.ocr import OCREngine
from core.perception.vision_agent import VisionAgent
from core.cognition.inference import IntentInference, EventContext
from core.system.guardrails import SystemGuard
from core.dal.sqlite_provider import DatabaseProvider

logger = logging.getLogger(__name__)


class EventProcessor:
    """
    Processes batches of events through the perception and cognition pipeline.
    
    Responsibilities:
        - PII sanitization of window titles
        - UI Automation context extraction
        - OCR fallback for phantom windows
        - VLM batch inference for screenshots
        - Intent inference via LLM
        - Persisting enriched context to database
    """
    
    def __init__(
        self,
        sanitizer: DataSanitizer,
        text_engine: TextEngine,
        ocr_engine: OCREngine,
        vision_agent: VisionAgent,
        inference: IntentInference,
        guard: SystemGuard,
        db: DatabaseProvider
    ) -> None:
        """
        Initialize EventProcessor with required components.
        
        Args:
            sanitizer: PII redaction engine.
            text_engine: UI Automation context extractor.
            ocr_engine: OCR fallback engine.
            vision_agent: VLM screenshot analyzer.
            inference: LLM intent inference engine.
            guard: VRAM and system guard.
            db: Database provider for persistence.
        """
        self.sanitizer = sanitizer
        self.text_engine = text_engine
        self.ocr_engine = ocr_engine
        self.vision_agent = vision_agent
        self.inference = inference
        self.guard = guard
        self.db = db

    async def process_batch(self, events: List[Dict[str, Any]]) -> None:
        """
        Process a batch of events through the full pipeline.
        
        Pipeline:
            1. PII Sanitization of window titles
            2. UI Automation extraction (if window is live)
            3. OCR fallback (if window closed and screenshot exists)
            4. VLM batch analysis (if VRAM available)
            5. Intent inference per event
            6. Persist enriched context to DB
        
        Args:
            events: List of event dictionaries from Watcher.
        """
        logger.info(f"Processing {len(events)} events")
        
        # First pass: collect context and prepare VLM batch
        vlm_batch: List[tuple] = []
        events_with_screenshots: List[Dict] = []
        
        for event in events:
            self._extract_context(event)
            
            # Collect screenshots for VLM batching
            if event.get('has_screenshot') and event.get('screenshot_hash'):
                screenshot_path = f"screenshots/{event['screenshot_hash']}.png"
                window_rect = self._get_window_rect(event)
                vlm_batch.append((screenshot_path, "Describe this user interface", window_rect))
                events_with_screenshots.append(event)
        
        # VLM batch processing
        await self._run_vlm_batch(vlm_batch, events_with_screenshots)
        
        # Second pass: intent inference and persistence
        for event in events:
            await self._infer_and_persist(event)

    def _extract_context(self, event: Dict[str, Any]) -> None:
        """
        Extract UI context for a single event.
        
        Modifies event dict in-place with:
            - sanitized_title
            - accessibility_tree
            - ocr_content
        """
        import json
        
        window_title = event.get('window_title', '')
        window_hwnd = event.get('window_hwnd')
        event_id = event['id']
        
        # Step 1: PII Sanitization
        event['sanitized_title'] = self.sanitizer.clean_text(window_title)
        
        # Step 2: UI Automation extraction
        accessibility_tree: Optional[str] = None
        ocr_content: Optional[str] = None
        
        if window_hwnd:
            ui_context = self.text_engine.extract_context(window_hwnd)
            if ui_context:
                accessibility_tree = json.dumps(ui_context, ensure_ascii=False)
                logger.debug(f"Extracted UI context for event {event_id}")
            else:
                logger.debug(f"Phantom Window detected for event {event_id}")
        
        # Step 3: OCR fallback
        if accessibility_tree is None and event.get('has_screenshot') and event.get('screenshot_hash'):
            screenshot_path = f"screenshots/{event['screenshot_hash']}.png"
            ocr_content = self.ocr_engine.extract_text_from_image(screenshot_path)
            if ocr_content:
                ocr_content = self.sanitizer.clean_text(ocr_content)
                logger.debug(f"Extracted OCR text for event {event_id}: {len(ocr_content)} chars")
        
        event['accessibility_tree'] = accessibility_tree
        event['ocr_content'] = ocr_content

    def _get_window_rect(self, event: Dict[str, Any]) -> Optional[tuple]:
        """Extract ROI rectangle from event if available."""
        if all(event.get(k) is not None for k in ['roi_left', 'roi_top', 'roi_right', 'roi_bottom']):
            return (
                event['roi_left'],
                event['roi_top'],
                event['roi_right'],
                event['roi_bottom']
            )
        return None

    async def _run_vlm_batch(
        self,
        vlm_batch: List[tuple],
        events_with_screenshots: List[Dict]
    ) -> None:
        """
        Run VLM inference on batch of screenshots.
        
        Args:
            vlm_batch: List of (path, prompt, roi) tuples.
            events_with_screenshots: Corresponding event dicts to update.
        """
        if not vlm_batch:
            return
        
        if not self.guard.can_run_vision_model():
            logger.info("VLM skipped due to VRAM constraints")
            for event in events_with_screenshots:
                event['vlm_description'] = None
            return
        
        logger.info(f"Running VLM batch inference on {len(vlm_batch)} screenshots")
        vlm_results = self.vision_agent.process_batch(vlm_batch)
        
        for event, vlm_desc in zip(events_with_screenshots, vlm_results):
            event['vlm_description'] = vlm_desc
            logger.debug(f"VLM description for event {event['id']}: {len(str(vlm_desc))} chars")

    async def _infer_and_persist(self, event: Dict[str, Any]) -> None:
        """
        Run intent inference and persist to database.
        
        Args:
            event: Event dict with extracted context.
        """
        event_id = event['id']
        
        # Get historical context
        history_events = await self.db.get_history_tail(
            timestamp=event.get('unix_time'),
            window_seconds=60
        )
        history_descriptions = [
            f"{h['process_name']}: {h['window_title'][:30]}"
            for h in history_events[-3:]
        ]
        
        # Build context layer cake
        context = EventContext(
            window_title=event['sanitized_title'],
            ui_tree=event.get('accessibility_tree'),
            ocr_text=event.get('ocr_content'),
            vision_description=event.get('vlm_description'),
            input_intensity=event.get('input_intensity', 0),
            history=history_descriptions,
            timestamp=event.get('timestamp_utc')
        )
        
        # Intent inference
        inference_result = self.inference.synthesize(context)
        
        # Persist to database
        await self.db.update_event_context(
            event_id=event_id,
            accessibility_tree=event.get('accessibility_tree'),
            ocr_content=event.get('ocr_content'),
            vlm_description=event.get('vlm_description'),
            user_intent=inference_result.intent,
            wikilinks=inference_result.tags,
            tags=inference_result.tags
        )
        logger.debug(f"Saved context for event {event_id}: {inference_result.intent}")
