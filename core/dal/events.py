"""
Mnemosyne Core V5.0 - Events Repository

Handles raw_events table CRUD operations: fetch pending, mark processed,
group by process/window, and archive enriched groups.

Usage:
    repo = EventRepository(db_path)
    await repo.connect()
    events = await repo.fetch_pending(limit=100)
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from core.dal.base import BaseRepository

logger = logging.getLogger(__name__)


# SQL Queries
QUERY_FETCH_PENDING = """
    SELECT id, session_uuid, timestamp_utc, unix_time,
           process_name, window_title, window_hwnd,
           roi_left, roi_top, roi_right, roi_bottom,
           input_idle_ms, input_intensity,
           is_processed, has_screenshot, screenshot_hash
    FROM raw_events
    WHERE is_processed = 0
    ORDER BY unix_time ASC
    LIMIT ?
"""

QUERY_MARK_PROCESSED = """
    UPDATE raw_events
    SET is_processed = 1
    WHERE id = ?
"""

QUERY_GET_HISTORY_TAIL = """
    SELECT id, timestamp_utc, process_name, window_title,
           input_intensity, input_idle_ms
    FROM raw_events
    WHERE unix_time >= ? AND unix_time <= ?
    ORDER BY unix_time ASC
"""

QUERY_FETCH_UNIQUE_GROUPS = """
    SELECT process_name, window_title, 
           GROUP_CONCAT(id) as event_ids,
           COUNT(*) as event_count,
           MIN(unix_time) as first_seen,
           MAX(unix_time) as last_seen,
           AVG(input_intensity) as avg_intensity
    FROM raw_events
    WHERE is_processed = 0
    GROUP BY process_name, window_title
    ORDER BY event_count DESC
    LIMIT ?
"""

# Column mappings
PENDING_COLUMNS = [
    "id", "session_uuid", "timestamp_utc", "unix_time",
    "process_name", "window_title", "window_hwnd",
    "roi_left", "roi_top", "roi_right", "roi_bottom",
    "input_idle_ms", "input_intensity",
    "is_processed", "has_screenshot", "screenshot_hash"
]

HISTORY_COLUMNS = [
    "id", "timestamp_utc", "process_name", "window_title",
    "input_intensity", "input_idle_ms"
]


class EventRepository(BaseRepository):
    """
    Repository for raw_events table operations.
    
    Responsibilities:
        - Fetch pending (unprocessed) events
        - Mark events as processed (single or batch)
        - Fetch historical context
        - Group events by process/window for deduplication
        - Archive enriched groups from Redis
    """

    async def fetch_pending(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch unprocessed events from raw_events table.
        
        Args:
            limit: Maximum number of events to fetch.
        
        Returns:
            List of event dictionaries.
        
        Raises:
            RuntimeError: If connection not established.
        """
        self._ensure_connected()
        
        async with self._lock:
            try:
                cursor = await self._connection.execute(QUERY_FETCH_PENDING, (limit,))
                rows = await cursor.fetchall()
                events = [dict(zip(PENDING_COLUMNS, row)) for row in rows]
                
                logger.info(f"Fetched {len(events)} pending events")
                return events
                
            except Exception as e:
                logger.error(f"Error fetching pending events: {e}")
                raise

    async def mark_processed(self, event_ids: List[int]) -> None:
        """
        Mark events as processed (one by one with transaction).
        
        Args:
            event_ids: List of event IDs to mark.
        
        Raises:
            RuntimeError: If connection not established.
        """
        self._ensure_connected()
        
        if not event_ids:
            return
        
        async with self._lock:
            try:
                await self._connection.execute("BEGIN TRANSACTION")
                
                for event_id in event_ids:
                    await self._connection.execute(QUERY_MARK_PROCESSED, (event_id,))
                
                await self._connection.commit()
                logger.info(f"Marked {len(event_ids)} events as processed")
                
            except Exception as e:
                await self._connection.rollback()
                logger.error(f"Error marking events as processed: {e}")
                raise

    async def batch_mark_processed(self, event_ids: List[int]) -> int:
        """
        Mark multiple events as processed (single query).
        
        Args:
            event_ids: List of event IDs.
        
        Returns:
            Number of rows updated.
        
        Raises:
            RuntimeError: If connection not established.
        """
        self._ensure_connected()
        
        if not event_ids:
            return 0
        
        async with self._lock:
            try:
                placeholders = ",".join("?" * len(event_ids))
                query = f"UPDATE raw_events SET is_processed = 1 WHERE id IN ({placeholders})"
                cursor = await self._connection.execute(query, event_ids)
                await self._connection.commit()
                
                logger.debug(f"Batch marked {cursor.rowcount} events as processed")
                return cursor.rowcount
                
            except Exception as e:
                logger.error(f"Error batch marking events: {e}")
                raise

    async def get_history_tail(
        self,
        timestamp: int,
        window_seconds: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical context around a timestamp.
        
        Args:
            timestamp: Unix timestamp (center point).
            window_seconds: Time window in seconds (default 60).
        
        Returns:
            List of historical event dictionaries.
        
        Raises:
            RuntimeError: If connection not established.
        """
        self._ensure_connected()
        
        start_time = timestamp - window_seconds
        end_time = timestamp + window_seconds
        
        async with self._lock:
            try:
                cursor = await self._connection.execute(
                    QUERY_GET_HISTORY_TAIL,
                    (start_time, end_time)
                )
                rows = await cursor.fetchall()
                events = [dict(zip(HISTORY_COLUMNS, row)) for row in rows]
                
                logger.debug(f"Fetched {len(events)} historical events")
                return events
                
            except Exception as e:
                logger.error(f"Error fetching history tail: {e}")
                raise

    async def fetch_unique_groups(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch unique event groups (process_name + window_title).
        
        Enables LLM deduplication: process similar events with one inference.
        
        Args:
            limit: Maximum number of groups.
        
        Returns:
            List of group dictionaries with aggregated data.
        
        Raises:
            RuntimeError: If connection not established.
        """
        self._ensure_connected()
        
        async with self._lock:
            try:
                cursor = await self._connection.execute(QUERY_FETCH_UNIQUE_GROUPS, (limit,))
                rows = await cursor.fetchall()
                
                groups = []
                for row in rows:
                    # Guard: handle NULL event_ids (Axiom fix)
                    event_ids_str = row[2]
                    if event_ids_str is None:
                        continue
                    
                    event_ids = [int(x) for x in event_ids_str.split(",")]
                    groups.append({
                        "process_name": row[0],
                        "window_title": row[1],
                        "event_ids": event_ids,
                        "event_count": row[3],
                        "first_seen": row[4],
                        "last_seen": row[5],
                        "avg_intensity": row[6] or 0
                    })
                
                if groups:
                    total = sum(g["event_count"] for g in groups)
                    logger.info(f"Fetched {len(groups)} unique groups ({total} events)")
                
                return groups
                
            except Exception as e:
                logger.error(f"Error fetching unique groups: {e}")
                raise

    async def archive_enriched_group(
        self,
        group: Dict[str, Any],
        user_intent: str,
        tags: List[str]
    ) -> None:
        """
        Archive enriched events from Redis stream to SQLite.
        
        Used in Redis mode (v4.0) where events originate from stream.
        
        Args:
            group: Event group with 'events' list.
            user_intent: LLM-inferred intent.
            tags: Generated tags.
        
        Raises:
            RuntimeError: If connection not established.
        """
        self._ensure_connected()
        
        async with self._lock:
            try:
                timestamp_utc = datetime.utcnow().isoformat()
                tags_json = json.dumps(tags)
                
                for event in group.get("events", []):
                    # Insert raw event
                    cursor = await self._connection.execute("""
                        INSERT INTO raw_events (
                            session_uuid, timestamp_utc, unix_time,
                            process_name, window_title, window_hwnd,
                            input_idle_ms, input_intensity, is_processed
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                        RETURNING id
                    """, (
                        event.get("session_uuid", "unknown"),
                        timestamp_utc,
                        event.get("unix_time"),
                        event.get("process_name"),
                        event.get("window_title"),
                        event.get("window_hwnd", 0),
                        event.get("input_idle", 0),
                        event.get("intensity", 0.0)
                    ))
                    
                    row = await cursor.fetchone()
                    if row:
                        event_id = row[0]
                        # Insert context
                        await self._connection.execute("""
                            INSERT OR REPLACE INTO context_enrichment
                            (event_id, accessibility_tree_json, ocr_content,
                             vlm_description, user_intent, generated_wikilinks, generated_tags)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (event_id, None, None, None, user_intent, tags_json, tags_json))
                
                await self._connection.commit()
                logger.debug(f"Archived group with {len(group.get('events', []))} events")
                
            except Exception as e:
                logger.error(f"Failed to archive group: {e}")
                raise
