"""
Mnemosyne Core V3.0 - Main Entry Point (Tier 2: Brain)

Асинхронный аналитический конвейер для обработки событий от Watcher.
Реализует "Smart Full Stop" для защиты ресурсов системы.

Usage:
    python main.py
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional

from core.system.guardrails import SystemGuard
from core.dal.sqlite_provider import DatabaseProvider
from core.security.sanitizer import DataSanitizer
from core.dal.redis_provider import RedisProvider
from core.ingestion.consumer import RedisConsumer
from core.perception.text_engine import TextEngine
from core.perception.ocr import OCREngine
from core.perception.vision_agent import VisionAgent
from core.cognition.inference import IntentInference, EventContext
from core.aggregation.session_tracker import SessionTracker, Session

# Phase 8: Graph RAG (lazy import for optional dependency)
try:
    from core.rag.engine import GraphRAGEngine
    HAS_RAG = True
except ImportError:
    HAS_RAG = False
    GraphRAGEngine = None


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('brain.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)


class Brain:
    """
    Основной класс аналитического ядра Mnemosyne.

    Управляет event loop, проверками ресурсов и обработкой событий.
    """

    def __init__(self, db_path: str = ".mnemosyne/activity.db", obsidian_vault_path: Optional[str] = None):
        """
        Инициализация Brain.

        Args:
            db_path: Путь к файлу базы данных.
            obsidian_vault_path: Путь к хранилищу Obsidian для WikiLink генерации.
        """
        self.db_path = Path(db_path)
        self.obsidian_vault_path = obsidian_vault_path
        self.guard: SystemGuard = None
        self.db: DatabaseProvider = None
        self.sanitizer: DataSanitizer = None
        self.text_engine: TextEngine = None
        self.ocr_engine: OCREngine = None
        self.vision_agent: VisionAgent = None
        self.inference: IntentInference = None
        self.session_tracker: SessionTracker = None  # Phase 6: Session Aggregation
        self.rag_engine = None  # Phase 8: Graph RAG
        self.running = False
        self.shutdown_event = asyncio.Event()

    async def initialize(self) -> None:
        """Инициализация компонентов."""
        logger.info("Initializing Mnemosyne Brain...")

        # Инициализация SystemGuard (VRAM мониторинг)
        self.guard = SystemGuard(vram_threshold_gb=4.0)
        logger.info("SystemGuard initialized")
        
        # Создание папки для скриншотов
        screenshots_dir = Path("screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Screenshots directory ensured: {screenshots_dir}")

        
        # Redis Configuration (v4.0)
        redis_host = os.environ.get("MNEMOSYNE_REDIS_HOST")
        if redis_host:
            try:
                # Assuming default port 6379 for now
                self.redis_provider = RedisProvider(redis_host, 6379)
                if self.redis_provider.connect():
                    self.redis_consumer = RedisConsumer(self.redis_provider)
                    logger.info("🟢 Brain running in REDIS MODE (v4.0)")
                else:
                    logger.warning("🔴 Redis connection failed, falling back to SQLite (v3.0)")
            except Exception as e:
                logger.error(f"Failed to initialize Redis: {e}")
        
        # Инициализация DatabaseProvider
        self.db = DatabaseProvider(self.db_path)
        await self.db.connect()
        logger.info("DatabaseProvider connected")

        # Инициализация DataSanitizer (PII Redaction)
        self.sanitizer = DataSanitizer()
        logger.info("DataSanitizer initialized")

        # Инициализация TextEngine (UI Automation)
        self.text_engine = TextEngine()
        logger.info("TextEngine initialized")

        # Инициализация OCREngine (OCR Fallback)
        self.ocr_engine = OCREngine()
        logger.info("OCREngine initialized")

        # Инициализация VisionAgent (VLM Engine)
        self.vision_agent = VisionAgent(vram_guard=self.guard)
        logger.info("VisionAgent initialized")

        # Инициализация IntentInference (LLM Engine)
        self.inference = IntentInference(obsidian_vault_path=self.obsidian_vault_path)
        
        # Проверка подключения к Ollama
        if not self.inference.check_connection():
            logger.warning("Ollama not available - intent inference will use fallback mode")
        else:
            logger.info("Ollama connection verified")
        
        # Инициализация SessionTracker (Phase 6: Session Aggregation)
        self.session_tracker = SessionTracker(
            idle_threshold_sec=300,   # 5 minutes
            max_session_sec=1800      # 30 minutes
        )
        logger.info("SessionTracker initialized")
        
        # Ensure sessions table exists
        await self.db.ensure_sessions_table()
        logger.info("Sessions table ensured")
        
        # Phase 8: Initialize Graph RAG Engine (optional)
        if HAS_RAG:
            try:
                redis_host = os.environ.get("MNEMOSYNE_REDIS_HOST", "localhost")
                self.rag_engine = GraphRAGEngine(
                    redis_url=f"redis://{redis_host}:6379",
                    ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434")
                )
                # Load persisted knowledge graph
                graph_path = self.db_path.parent / "knowledge_graph.json"
                self.rag_engine.load_graph(graph_path)
                logger.info("GraphRAGEngine initialized")
            except Exception as e:
                logger.warning(f"GraphRAGEngine not available: {e}")
                self.rag_engine = None
        else:
            logger.info("Graph RAG not available (LlamaIndex not installed)")

        # Вывод статистики базы данных
        stats = await self.db.get_stats()
        logger.info(
            f"Database stats - Total: {stats['total_events']}, "
            f"Pending: {stats['pending_events']}, "
            f"Enriched: {stats['enriched_events']}"
        )

    async def shutdown(self) -> None:
        """Корректное завершение работы."""
        logger.info("Shutting down Mnemosyne Brain...")

        self.running = False
        if hasattr(self, 'shutdown_event'):
            self.shutdown_event.set()
        
        # Phase 6: Force-close active session and archive it
        if hasattr(self, 'session_tracker') and self.session_tracker:
            completed_session = self.session_tracker.force_close()
            if completed_session:
                await self._archive_session(completed_session)
                logger.info("Active session archived on shutdown")

        # Выгрузка VLM модели
        if hasattr(self, 'vision_agent') and self.vision_agent:
            self.vision_agent.unload_model()
        
        # Закрытие HTTP клиента Ollama
        if hasattr(self, 'inference') and self.inference:
            del self.inference

        # Закрытие соединения с БД
        if hasattr(self, 'db') and self.db:
            await self.db.disconnect()

        # Завершение работы с NVML
        if hasattr(self, 'guard') and self.guard:
            self.guard.shutdown()
        
        # Phase 8: Save knowledge graph on shutdown
        if hasattr(self, 'rag_engine') and self.rag_engine:
            try:
                graph_path = self.db_path.parent / "knowledge_graph.json"
                self.rag_engine.save_graph(graph_path)
                logger.info(f"Knowledge graph saved ({len(self.rag_engine.graph.nodes)} nodes)")
            except Exception as e:
                logger.warning(f"Failed to save knowledge graph: {e}")

        logger.info("Shutdown complete")

    async def _archive_session(self, session: Session) -> None:
        """
        Archive a completed session to SQLite with LLM summary.
        
        Args:
            session: Completed Session object to archive.
        """
        try:
            # Generate LLM summary
            summary = self.inference.summarize_session(
                duration_minutes=session.duration_seconds / 60,
                primary_process=session.primary_process,
                primary_window=session.primary_window,
                transitions=session.window_transitions,
                avg_intensity=session.avg_input_intensity,
                event_count=session.event_count
            )
            
            session.activity_summary = summary
            
            # Extract tags from summary
            import re
            wikilinks = re.findall(r'\[\[(.*?)\]\]', summary or '')
            session.tags = list(set(wikilinks))
            
            # Insert into database
            session_data = session.to_dict()
            await self.db.insert_session(
                session_uuid=session_data['session_uuid'],
                start_time=session_data['start_time'],
                end_time=session_data['end_time'],
                duration_seconds=session_data['duration_seconds'],
                primary_process=session_data['primary_process'],
                primary_window=session_data['primary_window'],
                window_transitions=session_data['window_transitions'],
                event_count=session_data['event_count'],
                avg_input_intensity=session_data['avg_input_intensity'],
                activity_summary=session_data['activity_summary'],
                generated_tags=session_data['generated_tags']
            )
            
            logger.info(
                f"📝 Session archived: {session.primary_process} - "
                f"{session.duration_seconds}s - {summary[:50] if summary else 'No summary'}..."
            )
            
            # Phase 7: Cleanup screenshots after archival (saves disk space)
            cleaned_count = 0
            for event in session.events:
                screenshot_path = event.get('screenshot_path')
                if screenshot_path:
                    try:
                        path = Path(screenshot_path)
                        if path.exists():
                            path.unlink()
                            cleaned_count += 1
                    except Exception as e:
                        logger.debug(f"Could not delete screenshot {screenshot_path}: {e}")
            
            if cleaned_count > 0:
                logger.debug(f"🗑️ Cleaned {cleaned_count} screenshots after session archival")
            
            # Phase 8: Index session in Graph RAG
            if self.rag_engine:
                try:
                    self.rag_engine.index_session(session)
                    logger.debug(f"📊 Session indexed in Graph RAG")
                except Exception as e:
                    logger.debug(f"RAG indexing failed: {e}")
            
        except Exception as e:
            logger.error(f"Failed to archive session: {e}")

    async def process_events(self, events) -> None:
        """
        Обработка пакета событий с интеграцией Cognitive Layer.

        Логика обработки:
        1. PII Sanitization заголовка окна
        2. UI Automation extraction (если окно живо)
        3. OCR fallback (если окно закрыто и есть скриншот)
        4. VLM анализ (если есть скриншот и Guard разрешает)
        5. Формирование Context Layer Cake
        6. Intent Inference (LLM анализ)
        7. Сохранение результатов в БД

        Args:
            events: Список событий для обработки.
        """
        logger.info(f"Processing {len(events)} events")

        # Подготовка батча для VLM обработки (оптимизация VRAM)
        vlm_batch = []
        events_with_screenshots = []

        # Первый проход: сбор контекста и подготовка батча
        for event in events:
            event_id = event['id']
            window_title = event.get('window_title', '')
            window_hwnd = event.get('window_hwnd')
            has_screenshot = event.get('has_screenshot', False)
            screenshot_hash = event.get('screenshot_hash')
            timestamp = event.get('unix_time')

            logger.debug(
                f"Processing event {event_id}: {event['process_name']} - "
                f"{window_title[:50] if window_title else 'No title'}"
            )

            # Шаг 1: PII Sanitization заголовка окна
            sanitized_title = self.sanitizer.clean_text(window_title)

            # Шаг 2: UI Automation extraction
            accessibility_tree: Optional[str] = None
            ocr_content: Optional[str] = None

            if window_hwnd:
                ui_context = self.text_engine.extract_context(window_hwnd)
                if ui_context:
                    # Окно живо - используем UI Automation
                    import json
                    accessibility_tree = json.dumps(ui_context, ensure_ascii=False)
                    logger.debug(f"Extracted UI context for event {event_id}")
                else:
                    # Phantom Window - окно закрыто
                    logger.debug(f"Phantom Window detected for event {event_id}")
            else:
                logger.debug(f"No HWND for event {event_id}")

            # Шаг 3: OCR fallback (если окно закрыто и есть скриншот)
            if accessibility_tree is None and has_screenshot and screenshot_hash:
                # Формируем путь к скриншоту
                screenshot_path = f"screenshots/{screenshot_hash}.png"
                ocr_content = self.ocr_engine.extract_text_from_image(screenshot_path)
                if ocr_content:
                    # Также очищаем OCR результат от PII
                    ocr_content = self.sanitizer.clean_text(ocr_content)
                    logger.debug(f"Extracted OCR text for event {event_id}: {len(ocr_content)} chars")

            # Подготовка данных для VLM батчинга
            event['sanitized_title'] = sanitized_title
            event['accessibility_tree'] = accessibility_tree
            event['ocr_content'] = ocr_content

            if has_screenshot and screenshot_hash:
                screenshot_path = f"screenshots/{screenshot_hash}.png"
                # Получаем ROI для обрезки скриншота
                window_rect = None
                if (event.get('roi_left') is not None and
                    event.get('roi_top') is not None and
                    event.get('roi_right') is not None and
                    event.get('roi_bottom') is not None):
                    window_rect = (
                        event['roi_left'],
                        event['roi_top'],
                        event['roi_right'],
                        event['roi_bottom']
                    )
                
                vlm_batch.append((screenshot_path, "Describe this user interface", window_rect))
                events_with_screenshots.append(event)

        # Шаг 4: VLM анализ батчем (если Guard разрешает и есть скриншоты)
        vlm_descriptions = {}
        if vlm_batch and self.guard.can_run_vision_model():
            logger.info(f"Running VLM batch inference on {len(vlm_batch)} screenshots")
            vlm_results = self.vision_agent.process_batch(vlm_batch)
            
            for event, vlm_desc in zip(events_with_screenshots, vlm_results):
                event['vlm_description'] = vlm_desc
                vlm_descriptions[event['id']] = vlm_desc
                logger.debug(f"VLM description for event {event['id']}: {len(str(vlm_desc))} chars")
        else:
            # VLM пропущен из-за отсутствия VRAM или скриншотов
            if vlm_batch:
                logger.info("VLM skipped due to VRAM constraints")
            for event in events_with_screenshots:
                event['vlm_description'] = None

        # Второй проход: Intent Inference для каждого события
        for event in events:
            event_id = event['id']
            
            # Получаем исторический контекст
            history_events = await self.db.get_history_tail(
                timestamp=event.get('unix_time'),
                window_seconds=60
            )
            history_descriptions = [
                f"{h['process_name']}: {h['window_title'][:30]}"
                for h in history_events[-3:]  # Последние 3 события
            ]

            # Шаг 5: Формирование Context Layer Cake
            context = EventContext(
                window_title=event['sanitized_title'],
                ui_tree=event.get('accessibility_tree'),
                ocr_text=event.get('ocr_content'),
                vision_description=event.get('vlm_description'),
                input_intensity=event.get('input_intensity', 0),
                history=history_descriptions,
                timestamp=event.get('timestamp_utc')
            )

            # Шаг 6: Intent Inference
            inference_result = self.inference.synthesize(context)

            # Шаг 7: Сохранение контекста в БД
            await self.db.update_event_context(
                event_id=event_id,
                accessibility_tree=event.get('accessibility_tree'),
                ocr_content=event.get('ocr_content'),
                vlm_description=event.get('vlm_description'),
                user_intent=inference_result.intent,
                wikilinks=inference_result.tags,  # WikiLinks как теги
                tags=inference_result.tags
            )
            logger.debug(f"Saved context for event {event_id}: {inference_result.intent}")

    async def event_loop(self) -> None:
        """
        Основной цикл обработки событий с дедупликацией.

        Логика:
        1. Получить уникальные группы (process_name + window_title)
        2. Для каждой группы вызвать LLM один раз
        3. Применить результат ко всем событиям группы
        """
        logger.info("Starting event loop (DEDUPLICATION MODE)...")

        while self.running and not self.shutdown_event.is_set():
            try:
                # Шаг 1: Проверка безопасности запуска
                if not self.guard.is_safe_to_run():
                    logger.info("SystemGuard check failed. Sleeping for 60 seconds...")
                    await asyncio.sleep(60)
                    continue

                # Шаг 2: Получить уникальные группы событий (Redis или SQLite)
                groups = []
                if self.redis_consumer:
                    # Redis Mode (v4.0)
                    # Run in thread because redis-py is sync
                    groups = await asyncio.to_thread(self.redis_consumer.fetch_and_group, batch_size=50)
                else: 
                    # SQLite Mode (v3.0 Legacy)
                    groups = await self.db.fetch_unique_groups(limit=50)

                # Шаг 3: Если групп нет - подождать дольше (экономия ресурсов)
                if not groups:
                    logger.debug("No pending events, sleeping for 10 seconds...")
                    await asyncio.sleep(10)
                    continue

                # Шаг 4: Обработка групп
                total_events = sum(g['event_count'] for g in groups)
                logger.info(f"Processing {len(groups)} unique groups ({total_events} events)")
                
                processed_count = 0
                for group in groups:
                    try:
                        # Phase 6: Track session transitions
                        # Create a synthetic event from group for session tracking
                        session_event = {
                            'process_name': group.get('process_name', 'unknown'),
                            'window_title': group.get('window_title', 'unknown'),
                            'unix_time': group.get('last_seen') or group.get('first_seen') or int(__import__('time').time()),
                            'intensity': group.get('avg_intensity', 0)
                        }
                        
                        completed_session = self.session_tracker.process_event(session_event)
                        
                        # If session completed, archive it
                        if completed_session:
                            await self._archive_session(completed_session)
                        
                        # VLM Analysis (если есть скриншот)
                        vision_description = None
                        screenshot_path = group.get('screenshot_path')
                        
                        if screenshot_path and self.vision_agent and self.guard.check_vram_availability(threshold_mb=4096):
                            try:
                                # Проверяем существование файла
                                import os
                                if os.path.exists(screenshot_path):
                                    logger.debug(f"Running VLM on {screenshot_path}")
                                    vision_description = self.vision_agent.analyze(screenshot_path)
                                    logger.debug(f"VLM result: {vision_description[:50]}...")
                            except Exception as e:
                                logger.warning(f"VLM analysis failed: {e}")

                        # Создаем контекст из группы
                        context = EventContext(
                            window_title=group['window_title'] or "Unknown",
                            input_intensity=int(group['avg_intensity'] or 0),
                            history=[],
                            vision_description=vision_description
                        )
                        
                        # Один LLM вызов на группу
                        inference_result = self.inference.synthesize(context)
                        
                        # Применяем результат
                        if self.redis_consumer:
                            # v4.0: Archive to SQLite + ACK Redis
                            await self.db.archive_enriched_group(
                                group, 
                                inference_result.intent, 
                                inference_result.tags
                            )
                            # ACK in thread
                            await asyncio.to_thread(self.redis_consumer.ack_groups, [group])
                        else:
                            # v3.0: Update existing rows in SQLite
                            await self.db.batch_insert_context(
                                event_ids=group['event_ids'],
                                user_intent=inference_result.intent,
                                tags=inference_result.tags
                            )
                            # Помечаем как обработанные
                            await self.db.batch_mark_processed(group['event_ids'])
                        
                        processed_count += group['event_count']
                        logger.debug(f"Processed group '{group['process_name'][:20]}' ({group['event_count']} events)")
                        
                    except Exception as e:
                        logger.error(f"Error processing group: {e}")
                        continue
                
                logger.info(f"Batch complete: {processed_count} events processed from {len(groups)} groups")

            except asyncio.CancelledError:
                logger.info("Event loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in event loop: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def run(self) -> None:
        """Запуск Brain."""
        try:
            await self.initialize()
            self.running = True
            await self.event_loop()
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            raise
        finally:
            await self.shutdown()


async def main(obsidian_vault_path: Optional[str] = None) -> None:
    """Точка входа."""
    brain = Brain(
        db_path=os.environ.get("MNEMOSYNE_DB_PATH", ".mnemosyne/activity.db"),
        obsidian_vault_path=obsidian_vault_path
    )

    # Windows doesn't support add_signal_handler, use try/except instead
    try:
        await brain.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except asyncio.CancelledError:
        logger.info("Task cancelled")
    finally:
        await brain.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
        sys.exit(0)
