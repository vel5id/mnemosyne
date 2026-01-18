"""
Mnemosyne Core V3.0 - Database Access Layer (DAL)

Модуль для асинхронного взаимодействия с SQLite базой данных.
Использует aiosqlite для неблокирующих операций I/O.

Конфигурация PRAGMA критически важна для корректной работы
в режиме WAL с параллельным доступом от Watcher (Go) и Brain (Python).
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

import aiosqlite

logger = logging.getLogger(__name__)


class DatabaseProvider:
    """
    Провайдер асинхронного доступа к SQLite базе данных.

    Обеспечивает безопасное чтение данных, записанных Watcher'ом,
    используя WAL-режим с правильными PRAGMA настройками.
    """

    # SQL запросы
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

    QUERY_INSERT_CONTEXT = """
        INSERT OR REPLACE INTO context_enrichment
        (event_id, accessibility_tree_json, ocr_content,
         vlm_description, user_intent, generated_wikilinks, generated_tags)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """

    # Deduplication queries
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

    QUERY_BATCH_MARK_PROCESSED = """
        UPDATE raw_events
        SET is_processed = 1
        WHERE id IN ({})
    """

    # =========================================================================
    # Session Aggregation Queries (Phase 6)
    # =========================================================================
    
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

    def __init__(self, db_path: str):
        """
        Инициализация провайдера базы данных.

        Args:
            db_path: Путь к файлу базы данных SQLite.
        """
        self.db_path = Path(db_path)
        self._connection: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """
        Установить соединение с базой данных и настроить PRAGMA.

        Критические настройки:
        - busy_timeout=5000: Ждать до 5 сек при блокировке
        - journal_mode=WAL: Позволяет одновременное чтение/запись
        - synchronous=NORMAL: Защита SSD от износа
        - temp_store=MEMORY: Временные таблицы в RAM
        """
        if self._connection is not None:
            logger.warning("Database connection already exists.")
            return

        # Проверяем существование файла БД
        if not self.db_path.exists():
            logger.warning(f"Database file not found: {self.db_path}")
            # Создаем директорию если нужно
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # First try normal connection
            connection_path = str(self.db_path)
            
            # Check if running in Docker (no write access to -shm/-wal files)
            import os
            if os.environ.get('MNEMOSYNE_DB_READONLY', '').lower() == 'true':
                # Use URI with immutable mode for read-only access
                connection_path = f"file:{self.db_path}?immutable=1"
                self._connection = await aiosqlite.connect(connection_path, uri=True)
                logger.info("Connected in read-only (immutable) mode")
            else:
                self._connection = await aiosqlite.connect(self.db_path)

            # Применяем PRAGMA настройки
            await self._apply_pragmas()

            logger.info(f"Connected to database: {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def _apply_pragmas(self) -> None:
        """Применить критические PRAGMA настройки."""
        if self._connection is None:
            raise RuntimeError("Connection not established")

        pragmas = {
            "busy_timeout": "5000",           # 5 секунд ожидания при блокировке
            "journal_mode": "DELETE",         # Rollback journal (безопаснее для Windows+Docker)
            "synchronous": "NORMAL",         # Баланс между производительностью и надежностью
            "temp_store": "MEMORY",           # Временные таблицы в RAM (80GB доступно)
            "mmap_size": "268435456",         # 256MB Memory-Mapped I/O
            "foreign_keys": "ON",             # Включаем внешние ключи
        }

        for key, value in pragmas.items():
            try:
                await self._connection.execute(f"PRAGMA {key}={value}")
                logger.debug(f"PRAGMA {key}={value} applied")
            except Exception as e:
                logger.warning(f"Failed to set PRAGMA {key}={value}: {e}")

    async def disconnect(self) -> None:
        """Закрыть соединение с базой данных."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")

    async def fetch_pending_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Выбрать необработанные события из таблицы raw_events.

        Args:
            limit: Максимальное количество событий для выборки.

        Returns:
            Список словарей с данными событий.
        """
        if self._connection is None:
            raise RuntimeError("Database connection not established")

        async with self._lock:
            try:
                cursor = await self._connection.execute(
                    self.QUERY_FETCH_PENDING,
                    (limit,)
                )
                rows = await cursor.fetchall()

                # Преобразуем строки в словари
                columns = [
                    "id", "session_uuid", "timestamp_utc", "unix_time",
                    "process_name", "window_title", "window_hwnd",
                    "roi_left", "roi_top", "roi_right", "roi_bottom",
                    "input_idle_ms", "input_intensity",
                    "is_processed", "has_screenshot", "screenshot_hash"
                ]

                events = [dict(zip(columns, row)) for row in rows]

                logger.info(f"Fetched {len(events)} pending events")
                return events

            except Exception as e:
                logger.error(f"Error fetching pending events: {e}")
                raise

    async def mark_as_processed(self, event_ids: List[int]) -> None:
        """
        Пометить события как обработанные.

        Args:
            event_ids: Список идентификаторов событий.
        """
        if self._connection is None:
            raise RuntimeError("Database connection not established")

        if not event_ids:
            return

        async with self._lock:
            try:
                await self._connection.execute("BEGIN TRANSACTION")

                for event_id in event_ids:
                    await self._connection.execute(
                        self.QUERY_MARK_PROCESSED,
                        (event_id,)
                    )

                await self._connection.commit()
                logger.info(f"Marked {len(event_ids)} events as processed")

            except Exception as e:
                await self._connection.rollback()
                logger.error(f"Error marking events as processed: {e}")
                raise

    async def get_history_tail(
        self,
        timestamp: int,
        window_seconds: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Получить исторический контекст за указанный период.

        Args:
            timestamp: Текущее время в Unix timestamp.
            window_seconds: Размер окна в секундах (по умолчанию 60).

        Returns:
            Список событий из исторического периода.
        """
        if self._connection is None:
            raise RuntimeError("Database connection not established")

        start_time = timestamp - window_seconds
        end_time = timestamp + window_seconds

        async with self._lock:
            try:
                cursor = await self._connection.execute(
                    self.QUERY_GET_HISTORY_TAIL,
                    (start_time, end_time)
                )
                rows = await cursor.fetchall()

                columns = [
                    "id", "timestamp_utc", "process_name", "window_title",
                    "input_intensity", "input_idle_ms"
                ]

                events = [dict(zip(columns, row)) for row in rows]

                logger.debug(f"Fetched {len(events)} historical events")
                return events

            except Exception as e:
                logger.error(f"Error fetching history tail: {e}")
                raise

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
        Обновить контекст события в таблице context_enrichment.

        Args:
            event_id: Идентификатор события.
            accessibility_tree: JSON дамп UI Automation дерева.
            ocr_content: Текст из OCR.
            vlm_description: Описание от VLM.
            user_intent: Интерпретация намерения пользователя.
            wikilinks: Список вики-ссылок.
            tags: Список тегов.
        """
        if self._connection is None:
            raise RuntimeError("Database connection not established")

        import json

        async with self._lock:
            try:
                await self._connection.execute(
                    self.QUERY_INSERT_CONTEXT,
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

    async def get_stats(self) -> Dict[str, Any]:
        """
        Получить статистику базы данных.

        Returns:
            Словарь со статистикой (количество событий, необработанных и т.д.).
        """
        if self._connection is None:
            raise RuntimeError("Database connection not established")

        async with self._lock:
            try:
                cursor = await self._connection.execute(
                    "SELECT COUNT(*) FROM raw_events"
                )
                total_events = (await cursor.fetchone())[0]

                cursor = await self._connection.execute(
                    "SELECT COUNT(*) FROM raw_events WHERE is_processed = 0"
                )
                pending_events = (await cursor.fetchone())[0]

                cursor = await self._connection.execute(
                    "SELECT COUNT(*) FROM context_enrichment"
                )
                enriched_events = (await cursor.fetchone())[0]

                return {
                    "total_events": total_events,
                    "pending_events": pending_events,
                    "enriched_events": enriched_events
                }

            except Exception as e:
                logger.error(f"Error getting database stats: {e}")
                raise

    async def fetch_unique_groups(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Получить уникальные группы событий (process_name + window_title).
        
        Это позволяет обрабатывать множество похожих событий одним LLM вызовом.
        
        Args:
            limit: Максимальное количество групп.
        
        Returns:
            Список групп с агрегированными данными.
        """
        if self._connection is None:
            raise RuntimeError("Database connection not established")

        async with self._lock:
            try:
                cursor = await self._connection.execute(
                    self.QUERY_FETCH_UNIQUE_GROUPS,
                    (limit,)
                )
                rows = await cursor.fetchall()

                groups = []
                for row in rows:
                    event_ids = [int(x) for x in row[2].split(',')]
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
                    logger.info(f"Fetched {len(groups)} unique groups ({sum(g['event_count'] for g in groups)} events)")
                return groups

            except Exception as e:
                logger.error(f"Error fetching unique groups: {e}")
                raise

    async def batch_mark_processed(self, event_ids: List[int]) -> int:
        """
        Пометить несколько событий как обработанные.
        
        Args:
            event_ids: Список ID событий.
        
        Returns:
            Количество обновленных записей.
        """
        if self._connection is None:
            raise RuntimeError("Database connection not established")

        if not event_ids:
            return 0

        async with self._lock:
            try:
                placeholders = ','.join('?' * len(event_ids))
                query = f"UPDATE raw_events SET is_processed = 1 WHERE id IN ({placeholders})"
                cursor = await self._connection.execute(query, event_ids)
                await self._connection.commit()
                
                logger.debug(f"Batch marked {cursor.rowcount} events as processed")
                return cursor.rowcount

            except Exception as e:
                logger.error(f"Error batch marking events: {e}")
                raise

    async def batch_insert_context(
        self, 
        event_ids: List[int],
        user_intent: str,
        tags: List[str]
    ) -> int:
        """
        Вставить контекст для группы событий.
        
        Args:
            event_ids: Список ID событий.
            user_intent: Общий intent для всех событий.
            tags: Теги.
        
        Returns:
            Количество вставленных записей.
        """
        if self._connection is None:
            raise RuntimeError("Database connection not established")

        async with self._lock:
            try:
                import json
                tags_json = json.dumps(tags)
                
                for event_id in event_ids:
                    await self._connection.execute(
                        self.QUERY_INSERT_CONTEXT,
                        (event_id, None, None, None, user_intent, tags_json, tags_json)
                    )
                
                await self._connection.commit()
                return len(event_ids)

            except Exception as e:
                logger.error(f"Error batch inserting context: {e}")
                raise

    async def __aenter__(self):
        """Контекстный менеджер для автоматического подключения."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Контекстный менеджер для автоматического отключения."""
        await self.disconnect()

    async def archive_enriched_group(self, group: Dict[str, Any], user_intent: str, tags: List[str]) -> None:
        """
        Inserts new events into SQLite with enriched context.
        Used in Redis-mode (v4.0) where events originate from stream.
        """
        import json
        from datetime import datetime
        
        if self._connection is None:
            raise RuntimeError("Database connection not established")

        async with self._lock:
            try:
                timestamp_utc = datetime.utcnow().isoformat()
                tags_json = json.dumps(tags)
                
                # Use bulk insert for efficiency
                # Note: raw_events table might not have user_intent/context_tags columns directly 
                # if we strictly follow schema.sql v3.0 logic where they are in context table?
                # Wait, schema.sql says:
                # CREATE TABLE event_context (event_id, user_intent, tags...)
                # It does NOT say raw_events has these columns.
                
                # So we must insert into raw_events RETURNING id, then insert into event_context.
                
                for event in group.get('events', []):
                    # 1. Insert Raw Event
                    cursor = await self._connection.execute("""
                        INSERT INTO raw_events (
                            session_uuid, timestamp_utc, unix_time,
                            process_name, window_title, window_hwnd,
                            input_idle_ms, input_intensity,
                            is_processed
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                        RETURNING id
                    """, (
                        event.get('session_uuid', 'unknown'),
                        timestamp_utc,
                        event.get('unix_time'),
                        event.get('process_name'),
                        event.get('window_title'),
                        event.get('window_hwnd', 0),
                        event.get('input_idle', 0),
                        event.get('intensity', 0.0)
                    ))
                    
                    row = await cursor.fetchone()
                    if row:
                        event_id = row[0]
                        # 2. Insert Context
                        await self._connection.execute(
                            self.QUERY_INSERT_CONTEXT,
                            (event_id, None, None, None, user_intent, tags_json, tags_json)
                        )

                await self._connection.commit()
                logger.debug(f"Archived group with {len(group.get('events', []))} events")

            except Exception as e:
                logger.error(f"Failed to archive group: {e}")
                raise

    async def get_detailed_analytics(self) -> Dict[str, int]:
        """Returns detailed stats for dashboard breakdown."""
        if self._connection is None:
            return {}
            
        async with self._lock:
            try:
                stats = {}
                
                # 1. Total Telemetry (All Processed)
                cursor = await self._connection.execute("SELECT COUNT(*) FROM raw_events WHERE is_processed=1")
                row = await cursor.fetchone()
                stats['telemetry_events'] = row[0] if row else 0
                
                # 2. LLM Enriched (Has user_intent)
                cursor = await self._connection.execute(
                    "SELECT COUNT(*) FROM raw_events WHERE user_intent IS NOT NULL AND user_intent != ''"
                )
                row = await cursor.fetchone()
                stats['llm_events'] = row[0] if row else 0

                # 3. Screenshots (Has path)
                try:
                    cursor = await self._connection.execute(
                        "SELECT COUNT(*) FROM raw_events WHERE screenshot_path IS NOT NULL AND screenshot_path != ''"
                    )
                    row = await cursor.fetchone()
                    stats['screenshot_events'] = row[0] if row else 0
                except Exception:
                    stats['screenshot_events'] = 0

                # 4. VLM Analyzed
                try:
                    cursor = await self._connection.execute(
                        "SELECT COUNT(*) FROM raw_events WHERE vlm_description IS NOT NULL AND vlm_description != ''"
                    )
                    row = await cursor.fetchone()
                    stats['vlm_events'] = row[0] if row else 0
                except Exception:
                    stats['vlm_events'] = 0
                    
                return stats
                
            except Exception as e:
                logger.error(f"Error getting detailed stats: {e}")
                return {}

    # =========================================================================
    # Session Aggregation Methods (Phase 6)
    # =========================================================================
    
    async def ensure_sessions_table(self) -> None:
        """
        Ensure the sessions table exists. Called during initialization.
        Creates table and index if they don't exist.
        """
        if self._connection is None:
            raise RuntimeError("Database connection not established")
        
        async with self._lock:
            try:
                await self._connection.execute(self.QUERY_CREATE_SESSIONS_TABLE)
                await self._connection.execute(self.QUERY_CREATE_SESSIONS_INDEX)
                await self._connection.commit()
                logger.info("Sessions table ensured")
            except Exception as e:
                logger.error(f"Error creating sessions table: {e}")
                raise
    
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
        """
        Insert a completed session into the sessions table.
        
        Args:
            session_uuid: Unique identifier for the session.
            start_time: Unix timestamp of session start.
            end_time: Unix timestamp of session end.
            duration_seconds: Duration in seconds.
            primary_process: Main application used.
            primary_window: Main window title.
            window_transitions: JSON array of window transitions.
            event_count: Number of raw events in session.
            avg_input_intensity: Average input intensity (0-100).
            activity_summary: LLM-generated summary.
            generated_tags: JSON array of tags.
        """
        if self._connection is None:
            raise RuntimeError("Database connection not established")
        
        async with self._lock:
            try:
                await self._connection.execute(
                    self.QUERY_INSERT_SESSION,
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
    
    async def get_recent_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieve recent sessions from the database.
        
        Args:
            limit: Maximum number of sessions to fetch.
        
        Returns:
            List of session dictionaries.
        """
        if self._connection is None:
            raise RuntimeError("Database connection not established")
        
        async with self._lock:
            try:
                cursor = await self._connection.execute(
                    self.QUERY_GET_RECENT_SESSIONS,
                    (limit,)
                )
                rows = await cursor.fetchall()
                
                columns = [
                    'session_uuid', 'start_time', 'end_time', 'duration_seconds',
                    'primary_process', 'primary_window', 'activity_summary', 'generated_tags'
                ]
                
                return [dict(zip(columns, row)) for row in rows]
                
            except Exception as e:
                logger.error(f"Error fetching sessions: {e}")
                return []

