"""
Mnemosyne Core V5.0 - DAL Base Repository

Provides connection management, PRAGMA configuration, and async locking
for all database repositories.

Usage:
    class MyRepository(BaseRepository):
        async def my_query(self) -> List[Dict]:
            async with self._lock:
                cursor = await self._connection.execute(...)
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)


# Named constants (Axiom: no magic numbers)
BUSY_TIMEOUT_MS = 5000
MMAP_SIZE_256MB = 268435456


class BaseRepository:
    """
    Base class for all DAL repositories.
    
    Provides:
        - Async SQLite connection with WAL mode
        - PRAGMA configuration for performance/reliability
        - Thread-safe locking via asyncio.Lock
        - Context manager support
    
    Attributes:
        db_path: Path to SQLite database file.
    """
    
    def __init__(self, db_path: str) -> None:
        """
        Initialize base repository.
        
        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = Path(db_path)
        self._connection: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """
        Establish connection and apply PRAGMA settings.
        
        PRAGMA Configuration:
            - busy_timeout=5000: Wait up to 5s on lock
            - journal_mode=DELETE: Safe for Windows+Docker
            - synchronous=NORMAL: SSD wear protection
            - temp_store=MEMORY: RAM for temp tables
            - mmap_size=256MB: Memory-mapped I/O
            - foreign_keys=ON: Enforce FK constraints
        
        Raises:
            RuntimeError: If connection already exists.
        """
        if self._connection is not None:
            logger.warning("Database connection already exists")
            return
        
        # Ensure parent directory exists
        if not self.db_path.exists():
            logger.warning(f"Database file not found: {self.db_path}")
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Check for read-only mode (Docker scenario)
            if os.environ.get("MNEMOSYNE_DB_READONLY", "").lower() == "true":
                connection_uri = f"file:{self.db_path}?immutable=1"
                self._connection = await aiosqlite.connect(connection_uri, uri=True)
                logger.info("Connected in read-only (immutable) mode")
            else:
                self._connection = await aiosqlite.connect(self.db_path)
            
            await self._apply_pragmas()
            logger.info(f"Connected to database: {self.db_path}")
            
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def _apply_pragmas(self) -> None:
        """
        Apply critical PRAGMA settings for performance and reliability.
        
        Raises:
            RuntimeError: If connection not established.
        """
        if self._connection is None:
            raise RuntimeError("Connection not established")
        
        pragmas = {
            "busy_timeout": str(BUSY_TIMEOUT_MS),
            "journal_mode": "DELETE",
            "synchronous": "NORMAL",
            "temp_store": "MEMORY",
            "mmap_size": str(MMAP_SIZE_256MB),
            "foreign_keys": "ON",
        }
        
        for key, value in pragmas.items():
            try:
                await self._connection.execute(f"PRAGMA {key}={value}")
                logger.debug(f"PRAGMA {key}={value} applied")
            except Exception as e:
                logger.warning(f"Failed to set PRAGMA {key}={value}: {e}")

    async def disconnect(self) -> None:
        """Close database connection."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")

    async def __aenter__(self) -> "BaseRepository":
        """Context manager entry: connect."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit: disconnect."""
        await self.disconnect()

    def _ensure_connected(self) -> None:
        """
        Guard clause: ensure connection is established.
        
        Raises:
            RuntimeError: If connection not established.
        """
        if self._connection is None:
            raise RuntimeError("Database connection not established")
