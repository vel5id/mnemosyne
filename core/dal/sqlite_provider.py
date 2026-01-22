"""
Mnemosyne Core V5.0 - Database Provider Facade

Unified facade for backward compatibility. Composes all repository modules
into a single interface matching the original DatabaseProvider API.

Usage:
    from core.dal import DatabaseProvider
    
    db = DatabaseProvider(".mnemosyne/activity.db")
    await db.connect()
    events = await db.fetch_pending_events(limit=100)
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from core.dal.base import BaseRepository
from core.dal.events import EventRepository
from core.dal.context import ContextRepository
from core.dal.sessions import SessionRepository
from core.dal.stats import StatsRepository

logger = logging.getLogger(__name__)


class DatabaseProvider:
    """
    Unified facade for SQLite database operations.
    
    Composes EventRepository, ContextRepository, SessionRepository,
    and StatsRepository into a single interface for backward compatibility.
    
    All methods delegate to the appropriate repository.
    """
    
    def __init__(self, db_path: str) -> None:
        """
        Initialize DatabaseProvider facade.
        
        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = Path(db_path)
        
        # Compose repositories (they share connection via base class)
        self._events = EventRepository(db_path)
        self._context = ContextRepository(db_path)
        self._sessions = SessionRepository(db_path)
        self._stats = StatsRepository(db_path)
        
        # Primary repository for connection management
        self._primary = self._events

    @property
    def _connection(self):
        """Expose connection for backward compatibility with tests."""
        return self._primary._connection

    @property
    def _lock(self):
        """Expose lock for backward compatibility with tests."""
        return self._primary._lock

    async def connect(self) -> None:
        """Establish database connection."""
        await self._primary.connect()
        
        # Share connection with other repositories
        self._context._connection = self._primary._connection
        self._context._lock = self._primary._lock
        self._sessions._connection = self._primary._connection
        self._sessions._lock = self._primary._lock
        self._stats._connection = self._primary._connection
        self._stats._lock = self._primary._lock

    async def disconnect(self) -> None:
        """Close database connection."""
        await self._primary.disconnect()

    async def __aenter__(self) -> "DatabaseProvider":
        """Context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        await self.disconnect()

    # =========================================================================
    # Event Repository Delegates
    # =========================================================================

    async def fetch_pending_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Delegate to EventRepository."""
        return await self._events.fetch_pending(limit)

    async def mark_as_processed(self, event_ids: List[int]) -> None:
        """Delegate to EventRepository."""
        return await self._events.mark_processed(event_ids)

    async def batch_mark_processed(self, event_ids: List[int]) -> int:
        """Delegate to EventRepository."""
        return await self._events.batch_mark_processed(event_ids)

    async def get_history_tail(
        self,
        timestamp: int,
        window_seconds: int = 60
    ) -> List[Dict[str, Any]]:
        """Delegate to EventRepository."""
        return await self._events.get_history_tail(timestamp, window_seconds)

    async def fetch_unique_groups(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Delegate to EventRepository."""
        return await self._events.fetch_unique_groups(limit)

    async def archive_enriched_group(
        self,
        group: Dict[str, Any],
        user_intent: str,
        tags: List[str]
    ) -> None:
        """Delegate to EventRepository."""
        return await self._events.archive_enriched_group(group, user_intent, tags)

    # =========================================================================
    # Context Repository Delegates
    # =========================================================================

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
        """Delegate to ContextRepository."""
        return await self._context.update_event_context(
            event_id, accessibility_tree, ocr_content,
            vlm_description, user_intent, wikilinks, tags
        )

    async def batch_insert_context(
        self,
        event_ids: List[int],
        user_intent: str,
        tags: List[str]
    ) -> int:
        """Delegate to ContextRepository."""
        return await self._context.batch_insert_context(event_ids, user_intent, tags)

    # =========================================================================
    # Session Repository Delegates
    # =========================================================================

    async def ensure_sessions_table(self) -> None:
        """Delegate to SessionRepository."""
        return await self._sessions.ensure_table()

    async def insert_session(
        self,
        session_uuid: str,
        start_time: int,
        end_time: int,
        duration_seconds: int,
        primary_process: str,
        primary_window: str,
        window_transitions: str,
        event_count: int,
        avg_input_intensity: float,
        activity_summary: Optional[str],
        generated_tags: str
    ) -> None:
        """Delegate to SessionRepository."""
        return await self._sessions.insert(
            session_uuid, start_time, end_time, duration_seconds,
            primary_process, primary_window, window_transitions,
            event_count, avg_input_intensity, activity_summary, generated_tags
        )

    async def get_recent_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Delegate to SessionRepository."""
        return await self._sessions.get_recent(limit)

    # =========================================================================
    # Stats Repository Delegates
    # =========================================================================

    async def get_stats(self) -> Dict[str, Any]:
        """Delegate to StatsRepository."""
        return await self._stats.get_stats()

    async def get_detailed_analytics(self) -> Dict[str, int]:
        """Delegate to StatsRepository."""
        return await self._stats.get_detailed_analytics()
