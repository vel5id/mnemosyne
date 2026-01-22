"""
Mnemosyne Core V5.0 - Context Repository

Handles context_enrichment table operations: update event context,
batch insert context for groups.

Usage:
    repo = ContextRepository(db_path)
    await repo.connect()
    await repo.update_event_context(event_id, intent="coding", tags=["python"])
"""

import json
import logging
from typing import List, Optional

from core.dal.base import BaseRepository

logger = logging.getLogger(__name__)


# SQL Queries
QUERY_INSERT_CONTEXT = """
    INSERT OR REPLACE INTO context_enrichment
    (event_id, accessibility_tree_json, ocr_content,
     vlm_description, user_intent, generated_wikilinks, generated_tags)
    VALUES (?, ?, ?, ?, ?, ?, ?)
"""


class ContextRepository(BaseRepository):
    """
    Repository for context_enrichment table operations.
    
    Responsibilities:
        - Store enriched context (LLM intent, VLM description, OCR, etc.)
        - Batch insert context for event groups
    """

    async def update_event_context(
        self,
        event_id: int,
        accessibility_tree: Optional[str] = None,
        ocr_content: Optional[str] = None,
        vlm_description: Optional[str] = None,
        user_intent: Optional[str] = None,
        wikilinks: Optional[List[str]] = None,
        tags: Optional[List[str]] = None
    ) -> None:
        """
        Update context enrichment for a single event.
        
        Args:
            event_id: ID of the raw event.
            accessibility_tree: JSON dump of UI Automation tree.
            ocr_content: OCR extracted text.
            vlm_description: VLM screenshot description.
            user_intent: LLM-inferred intent.
            wikilinks: List of WikiLinks.
            tags: List of tags.
        
        Raises:
            RuntimeError: If connection not established.
        """
        self._ensure_connected()
        
        async with self._lock:
            try:
                await self._connection.execute(
                    QUERY_INSERT_CONTEXT,
                    (
                        event_id,
                        accessibility_tree,
                        ocr_content,
                        vlm_description,
                        user_intent,
                        json.dumps(wikilinks) if wikilinks else None,
                        json.dumps(tags) if tags else None
                    )
                )
                await self._connection.commit()
                logger.debug(f"Updated context for event {event_id}")
                
            except Exception as e:
                logger.error(f"Error updating event context: {e}")
                raise

    async def batch_insert_context(
        self,
        event_ids: List[int],
        user_intent: str,
        tags: List[str]
    ) -> int:
        """
        Insert context for multiple events (same intent/tags).
        
        Used for deduplication: one LLM call applies to many events.
        
        Args:
            event_ids: List of event IDs.
            user_intent: Shared intent for all events.
            tags: Shared tags for all events.
        
        Returns:
            Number of rows inserted.
        
        Raises:
            RuntimeError: If connection not established.
        """
        self._ensure_connected()
        
        if not event_ids:
            return 0
        
        async with self._lock:
            try:
                tags_json = json.dumps(tags)
                
                for event_id in event_ids:
                    await self._connection.execute(
                        QUERY_INSERT_CONTEXT,
                        (event_id, None, None, None, user_intent, tags_json, tags_json)
                    )
                
                await self._connection.commit()
                logger.debug(f"Batch inserted context for {len(event_ids)} events")
                return len(event_ids)
                
            except Exception as e:
                logger.error(f"Error batch inserting context: {e}")
                raise
