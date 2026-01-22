"""
Mnemosyne Core V5.0 - Sessions Repository

Handles sessions table operations: ensure table exists, insert completed
sessions, retrieve recent sessions.

Usage:
    repo = SessionRepository(db_path)
    await repo.connect()
    await repo.ensure_table()
    await repo.insert(session_data)
"""

import logging
from typing import List, Dict, Any, Optional

from core.dal.base import BaseRepository

logger = logging.getLogger(__name__)


# SQL Queries
QUERY_CREATE_SESSIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_uuid TEXT UNIQUE NOT NULL,
        start_time INTEGER NOT NULL,
        end_time INTEGER NOT NULL,
        duration_seconds INTEGER NOT NULL,
        
        primary_process TEXT NOT NULL,
        primary_window TEXT NOT NULL,
        
        window_transitions TEXT,
        event_count INTEGER DEFAULT 0,
        avg_input_intensity REAL,
        
        activity_summary TEXT,
        generated_tags TEXT,
        
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
"""

QUERY_CREATE_SESSIONS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_sessions_time 
    ON sessions(start_time, end_time)
"""

QUERY_INSERT_SESSION = """
    INSERT INTO sessions (
        session_uuid, start_time, end_time, duration_seconds,
        primary_process, primary_window, window_transitions,
        event_count, avg_input_intensity, activity_summary, generated_tags
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

QUERY_GET_RECENT_SESSIONS = """
    SELECT session_uuid, start_time, end_time, duration_seconds,
           primary_process, primary_window, activity_summary, generated_tags
    FROM sessions
    ORDER BY start_time DESC
    LIMIT ?
"""

# Column mapping
SESSION_COLUMNS = [
    "session_uuid", "start_time", "end_time", "duration_seconds",
    "primary_process", "primary_window", "activity_summary", "generated_tags"
]


class SessionRepository(BaseRepository):
    """
    Repository for sessions table operations.
    
    Responsibilities:
        - Create sessions table and index
        - Insert completed sessions with LLM summaries
        - Retrieve recent sessions for dashboard
    """

    async def ensure_table(self) -> None:
        """
        Ensure sessions table and index exist.
        
        Called during Brain initialization.
        
        Raises:
            RuntimeError: If connection not established.
        """
        self._ensure_connected()
        
        async with self._lock:
            try:
                await self._connection.execute(QUERY_CREATE_SESSIONS_TABLE)
                await self._connection.execute(QUERY_CREATE_SESSIONS_INDEX)
                await self._connection.commit()
                logger.info("Sessions table ensured")
                
            except Exception as e:
                logger.error(f"Error creating sessions table: {e}")
                raise

    async def insert(
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
        """
        Insert a completed session.
        
        Args:
            session_uuid: Unique session identifier.
            start_time: Unix timestamp of session start.
            end_time: Unix timestamp of session end.
            duration_seconds: Duration in seconds.
            primary_process: Main application (mode).
            primary_window: Main window title.
            window_transitions: JSON array of transitions.
            event_count: Number of raw events.
            avg_input_intensity: Average input intensity (0-100).
            activity_summary: LLM-generated summary.
            generated_tags: JSON array of tags.
        
        Raises:
            RuntimeError: If connection not established.
        """
        self._ensure_connected()
        
        async with self._lock:
            try:
                await self._connection.execute(
                    QUERY_INSERT_SESSION,
                    (
                        session_uuid, start_time, end_time, duration_seconds,
                        primary_process, primary_window, window_transitions,
                        event_count, avg_input_intensity, activity_summary, generated_tags
                    )
                )
                await self._connection.commit()
                logger.debug(f"Inserted session {session_uuid[:8]}...")
                
            except Exception as e:
                logger.error(f"Error inserting session: {e}")
                raise

    async def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieve recent sessions.
        
        Args:
            limit: Maximum number of sessions.
        
        Returns:
            List of session dictionaries.
        
        Raises:
            RuntimeError: If connection not established.
        """
        self._ensure_connected()
        
        async with self._lock:
            try:
                cursor = await self._connection.execute(
                    QUERY_GET_RECENT_SESSIONS,
                    (limit,)
                )
                rows = await cursor.fetchall()
                return [dict(zip(SESSION_COLUMNS, row)) for row in rows]
                
            except Exception as e:
                logger.error(f"Error fetching sessions: {e}")
                return []
