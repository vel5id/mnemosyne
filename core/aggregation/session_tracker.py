"""
Session Aggregation Module for Mnemosyne Core V4.0

This module implements session tracking to aggregate granular events
into meaningful time-bounded sessions with LLM-generated summaries.

Key Features:
- Window transition detection
- Idle timeout handling (5 min default)
- Maximum session duration (30 min default)
- In-memory event accumulation before archival
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


# ==============================================================================
# Data Classes
# ==============================================================================

@dataclass
class Session:
    """Represents a user activity session."""
    session_uuid: str
    start_time: int      # Unix timestamp
    end_time: int        # Unix timestamp
    
    primary_process: str
    primary_window: str
    
    window_transitions: List[str] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    avg_input_intensity: float = 0.0
    activity_summary: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    
    @property
    def duration_seconds(self) -> int:
        # Ensure duration is never negative (guard against clock skew)
        return max(0, self.end_time - self.start_time)
    
    @property
    def event_count(self) -> int:
        return len(self.events)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for database insertion."""
        return {
            'session_uuid': self.session_uuid,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration_seconds': self.duration_seconds,
            'primary_process': self.primary_process,
            'primary_window': self.primary_window,
            'window_transitions': json.dumps(self.window_transitions),
            'event_count': self.event_count,
            'avg_input_intensity': self.avg_input_intensity,
            'activity_summary': self.activity_summary,
            'generated_tags': json.dumps(self.tags),
        }


# ==============================================================================
# Session Tracker
# ==============================================================================

class SessionTracker:
    """
    Tracks active user sessions and detects transitions.
    
    A session ends when:
    1. Window changes (new app/document)
    2. Idle timeout (5+ minutes of no activity)
    3. Time limit (30 minutes max)
    
    Args:
        idle_threshold_sec: Seconds of inactivity before closing session (default: 300)
        max_session_sec: Maximum session duration in seconds (default: 1800)
    """
    
    # Named constants (Axiom: no magic numbers)
    DEFAULT_IDLE_THRESHOLD_SEC = 300    # 5 minutes
    DEFAULT_MAX_SESSION_SEC = 1800      # 30 minutes
    
    def __init__(
        self,
        idle_threshold_sec: int = DEFAULT_IDLE_THRESHOLD_SEC,
        max_session_sec: int = DEFAULT_MAX_SESSION_SEC
    ):
        self.idle_threshold_sec = idle_threshold_sec
        self.max_session_sec = max_session_sec
        
        self._current_session: Optional[Session] = None
        self._last_event_time: int = 0
        self._intensity_sum: float = 0.0
        
        logger.info(
            f"SessionTracker initialized. "
            f"Idle threshold: {idle_threshold_sec}s, Max session: {max_session_sec}s"
        )
    
    def process_event(self, event: Dict[str, Any]) -> Optional[Session]:
        """
        Process a single event and detect session transitions.
        
        Args:
            event: Event dictionary with at least 'process_name', 'window_title',
                   'unix_time', and 'input_intensity' keys.
        
        Returns:
            Completed Session if a transition was detected, None otherwise.
        """
        process_name = event.get('process_name', 'unknown')
        window_title = event.get('window_title', 'unknown')
        event_time = int(event.get('unix_time', time.time()))
        intensity = float(event.get('intensity', event.get('input_intensity', 0)))
        
        completed_session: Optional[Session] = None
        
        # Guard: First event ever
        if self._current_session is None:
            self._start_new_session(process_name, window_title, event_time)
            self._add_event_to_session(event, intensity)
            return None
        
        # Check for session end conditions
        should_close, reason = self._should_close_session(
            process_name, window_title, event_time
        )
        
        if should_close:
            # Close current session
            completed_session = self._close_current_session(event_time, reason)
            
            # Start new session (unless it was idle timeout with no new activity)
            self._start_new_session(process_name, window_title, event_time)
        
        # Add event to current session
        self._add_event_to_session(event, intensity)
        
        # Track window transitions within session
        window_key = f"{process_name}:{window_title[:50]}"
        if window_key not in self._current_session.window_transitions:
            self._current_session.window_transitions.append(window_key)
        
        return completed_session
    
    def force_close(self) -> Optional[Session]:
        """
        Force-close current session (for shutdown/flush).
        
        Returns:
            The closed Session, or None if no session was active.
        """
        if self._current_session is None:
            return None
        
        return self._close_current_session(int(time.time()), "forced_close")
    
    def _should_close_session(
        self, 
        process_name: str, 
        window_title: str, 
        event_time: int
    ) -> tuple[bool, str]:
        """
        Determine if current session should be closed.
        
        Returns:
            Tuple of (should_close: bool, reason: str)
        """
        if self._current_session is None:
            return False, ""
        
        # Condition 1: Window changed (new primary app/document)
        if (process_name != self._current_session.primary_process or
            window_title != self._current_session.primary_window):
            return True, "window_change"
        
        # Condition 2: Idle timeout
        time_since_last = event_time - self._last_event_time
        if time_since_last > self.idle_threshold_sec:
            return True, "idle_timeout"
        
        # Condition 3: Max duration exceeded
        session_duration = event_time - self._current_session.start_time
        if session_duration > self.max_session_sec:
            return True, "max_duration"
        
        return False, ""
    
    def _start_new_session(
        self, 
        process_name: str, 
        window_title: str, 
        start_time: int
    ) -> None:
        """Initialize a new session."""
        self._current_session = Session(
            session_uuid=str(uuid.uuid4()),
            start_time=start_time,
            end_time=start_time,  # Will be updated on close
            primary_process=process_name,
            primary_window=window_title,
            window_transitions=[f"{process_name}:{window_title[:50]}"]
        )
        self._intensity_sum = 0.0
        self._last_event_time = start_time
        
        logger.debug(f"Started new session: {process_name} - {window_title[:50]}")
    
    def _add_event_to_session(self, event: Dict[str, Any], intensity: float) -> None:
        """Add event to current session and update metrics."""
        if self._current_session is None:
            return
        
        self._current_session.events.append(event)
        self._intensity_sum += intensity
        self._last_event_time = int(event.get('unix_time', time.time()))
        
        # Update end_time to last event
        self._current_session.end_time = self._last_event_time
    
    def _close_current_session(self, end_time: int, reason: str) -> Session:
        """
        Close the current session and return it.
        
        Args:
            end_time: Unix timestamp for session end.
            reason: Reason for closing (window_change, idle_timeout, max_duration, forced_close)
        
        Returns:
            The completed Session object.
        """
        session = self._current_session
        session.end_time = end_time
        
        # Calculate average intensity
        if session.event_count > 0:
            session.avg_input_intensity = self._intensity_sum / session.event_count
        
        logger.info(
            f"Session closed ({reason}): {session.primary_process} - "
            f"{session.primary_window[:30]}... | "
            f"Duration: {session.duration_seconds}s | Events: {session.event_count}"
        )
        
        self._current_session = None
        return session
    
    @property
    def has_active_session(self) -> bool:
        """Check if there's an active session."""
        return self._current_session is not None
    
    @property
    def current_session_duration(self) -> int:
        """Get current session duration in seconds."""
        if self._current_session is None:
            return 0
        return int(time.time()) - self._current_session.start_time
