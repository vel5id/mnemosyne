"""
Mnemosyne Core V5.0 - Brain Orchestrator Module

Coordinates initialization, shutdown, and the main event loop.
Extracted from Brain class to follow Single Responsibility Principle.

Usage:
    brain = BrainOrchestrator(db_path=".mnemosyne/activity.db")
    await brain.run()
"""

import asyncio
import os
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from core.system.guardrails import SystemGuard
from core.dal.sqlite_provider import DatabaseProvider
from core.dal.redis_provider import RedisProvider
from core.ingestion.consumer import RedisConsumer
from core.security.sanitizer import DataSanitizer
from core.perception.text_engine import TextEngine
from core.perception.ocr import OCREngine
from core.perception.vision_agent import VisionAgent
from core.cognition.inference import IntentInference, EventContext, InferenceResult
from core.aggregation.session_tracker import SessionTracker

from core.brain.session_manager import SessionManager

# Phase 8: Graph RAG (lazy import for optional dependency)
try:
    from core.rag.engine import GraphRAGEngine
    HAS_RAG = True
except ImportError:
    HAS_RAG = False
    GraphRAGEngine = None

logger = logging.getLogger(__name__)

# Named constants
PROCESSING_INTERVAL_SEC = 30
DEDUP_WINDOW_SEC = 15
VRAM_THRESHOLD_GB = 4.0
VRAM_CHECK_THRESHOLD_MB = 4096  # VLM analysis threshold
SESSION_IDLE_THRESHOLD_SEC = 300
SESSION_MAX_DURATION_SEC = 1800


class BrainOrchestrator:
    """
    Main orchestrator for Mnemosyne Brain.
    
    Responsibilities:
        - Initialize all subsystems (DB, Redis, LLM, VLM, etc.)
        - Coordinate event processing loop
        - Manage graceful shutdown
        - Handle PID deduplication
    """
    
    def __init__(
        self,
        db_path: str = ".mnemosyne/activity.db",
        obsidian_vault_path: Optional[str] = None
    ) -> None:
        """
        Initialize BrainOrchestrator.
        
        Args:
            db_path: Path to SQLite database.
            obsidian_vault_path: Path to Obsidian vault for WikiLink generation.
        """
        self.db_path = Path(db_path)
        self.obsidian_vault_path = obsidian_vault_path
        
        # Components (initialized in initialize())
        self.guard: Optional[SystemGuard] = None
        self.db: Optional[DatabaseProvider] = None
        self.redis_provider: Optional[RedisProvider] = None
        self.redis_consumer: Optional[RedisConsumer] = None
        self.sanitizer: Optional[DataSanitizer] = None
        self.text_engine: Optional[TextEngine] = None
        self.ocr_engine: Optional[OCREngine] = None
        self.vision_agent: Optional[VisionAgent] = None
        self.inference: Optional[IntentInference] = None
        self.session_tracker: Optional[SessionTracker] = None
        self.session_manager: Optional[SessionManager] = None
        self.rag_engine = None
        
        # Control state
        self.running = False
        self.shutdown_event = asyncio.Event()
        
        # PID deduplication cache
        self._recent_pids: Dict[str, float] = {}

    async def initialize(self) -> None:
        """Initialize all subsystems."""
        logger.info("Initializing Mnemosyne Brain...")
        
        # SystemGuard (VRAM monitoring)
        self.guard = SystemGuard(vram_threshold_gb=VRAM_THRESHOLD_GB)
        logger.info("SystemGuard initialized")
        
        # Screenshots directory
        screenshots_dir = Path("screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Screenshots directory ensured: {screenshots_dir}")
        
        # Redis configuration (v4.0)
        await self._init_redis()
        
        # Database
        self.db = DatabaseProvider(self.db_path)
        await self.db.connect()
        logger.info("DatabaseProvider connected")
        
        # Ensure sessions table
        await self.db.ensure_sessions_table()
        logger.info("Sessions table ensured")
        
        # Perception layer
        self.sanitizer = DataSanitizer()
        self.text_engine = TextEngine()
        self.ocr_engine = OCREngine()
        self.vision_agent = VisionAgent(vram_guard=self.guard)
        logger.info("Perception layer initialized")
        
        # Cognition layer
        self.inference = IntentInference(obsidian_vault_path=self.obsidian_vault_path)
        if not self.inference.check_connection():
            logger.warning("Ollama not available - using fallback mode")
        else:
            logger.info("Ollama connection verified")
        
        # Session tracking
        self.session_tracker = SessionTracker(
            idle_threshold_sec=SESSION_IDLE_THRESHOLD_SEC,
            max_session_sec=SESSION_MAX_DURATION_SEC
        )
        logger.info("SessionTracker initialized")
        
        # Graph RAG (optional)
        await self._init_rag()
        
        # Session manager
        self.session_manager = SessionManager(
            db=self.db,
            inference=self.inference,
            rag_engine=self.rag_engine,
            db_path=self.db_path
        )
        
        # Log database stats
        stats = await self.db.get_stats()
        logger.info(
            f"Database stats - Total: {stats['total_events']}, "
            f"Pending: {stats['pending_events']}, "
            f"Enriched: {stats['enriched_events']}"
        )

    async def _init_redis(self) -> None:
        """Initialize Redis connection if configured."""
        redis_host = os.environ.get("MNEMOSYNE_REDIS_HOST")
        if not redis_host:
            return
        
        try:
            self.redis_provider = RedisProvider(redis_host, 6379)
            if self.redis_provider.connect():
                self.redis_consumer = RedisConsumer(self.redis_provider)
                logger.info("🟢 Brain running in REDIS MODE (v4.0)")
            else:
                logger.warning("🔴 Redis connection failed, falling back to SQLite")
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")

    async def _init_rag(self) -> None:
        """Initialize Graph RAG engine if available."""
        if not HAS_RAG:
            logger.info("Graph RAG not available (LlamaIndex not installed)")
            return
        
        try:
            redis_host = os.environ.get("MNEMOSYNE_REDIS_HOST", "localhost")
            ollama_host = os.environ.get(
                "OLLAMA_LLM_HOST",
                os.environ.get("OLLAMA_HOST", "http://localhost:11434")
            )
            
            self.rag_engine = GraphRAGEngine(
                redis_url=f"redis://{redis_host}:6379",
                ollama_host=ollama_host
            )
            
            # Load persisted graph
            graph_path = self.db_path.parent / "knowledge_graph.json"
            self.rag_engine.load_graph(graph_path)
            logger.info("GraphRAGEngine initialized")
            
        except Exception as e:
            logger.warning(f"GraphRAGEngine not available: {e}")
            self.rag_engine = None

    async def shutdown(self) -> None:
        """Graceful shutdown of all subsystems."""
        logger.info("Shutting down Mnemosyne Brain...")
        
        self.running = False
        self.shutdown_event.set()
        
        # Archive active session
        if self.session_tracker:
            completed_session = self.session_tracker.force_close()
            if completed_session and self.session_manager:
                await self.session_manager.archive(completed_session)
                logger.info("Active session archived on shutdown")
        
        # Unload VLM model
        if self.vision_agent:
            self.vision_agent.unload_model()
        
        # Cleanup inference
        if self.inference:
            del self.inference
        
        # Close database
        if self.db:
            await self.db.disconnect()
        
        # Shutdown NVML
        if self.guard:
            self.guard.shutdown()
        
        # Save knowledge graph
        if self.session_manager:
            self.session_manager.save_graph()
        
        logger.info("Shutdown complete")

    async def event_loop(self) -> None:
        """
        Main event processing loop.
        
        Runs on 30-second intervals, fetches events from Redis or SQLite,
        applies PID deduplication, and processes through the pipeline.
        """
        logger.info("Starting event loop (TIME-BASED MODE: 30s intervals)...")
        
        while self.running and not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(PROCESSING_INTERVAL_SEC)
                
                if not self.guard.is_safe_to_run():
                    logger.info("SystemGuard check failed. Skipping cycle...")
                    continue
                
                groups = await self._fetch_groups()
                if not groups:
                    logger.debug("No pending events this cycle")
                    continue
                
                total_events = sum(g['event_count'] for g in groups)
                logger.info(f"Processing {len(groups)} unique groups ({total_events} events)")
                
                processed_count = await self._process_groups(groups)
                logger.info(f"Batch complete: {processed_count} events from {len(groups)} groups")
                
            except asyncio.CancelledError:
                logger.info("Event loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in event loop: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _fetch_groups(self) -> list:
        """Fetch event groups from Redis or SQLite."""
        if self.redis_consumer:
            return await asyncio.to_thread(
                self.redis_consumer.fetch_and_group, 
                batch_size=100
            )
        return await self.db.fetch_unique_groups(limit=100)

    async def _process_groups(self, groups: list) -> int:
        """
        Process event groups through the pipeline.
        
        Returns:
            Number of events processed.
        """
        processed_count = 0
        
        for group in groups:
            try:
                # Session tracking
                session_event = {
                    'process_name': group.get('process_name', 'unknown'),
                    'window_title': group.get('window_title', 'unknown'),
                    'unix_time': group.get('last_seen') or group.get('first_seen') or int(time.time()),
                    'intensity': group.get('avg_intensity', 0)
                }
                
                completed_session = self.session_tracker.process_event(session_event)
                if completed_session:
                    await self.session_manager.archive(completed_session)
                
                # PID deduplication
                if self._should_skip_pid(group):
                    if self.redis_consumer:
                        await asyncio.to_thread(self.redis_consumer.ack_groups, [group])
                    processed_count += group['event_count']
                    continue
                
                # VLM analysis
                vision_description = await self._run_vlm(group)
                
                # Intent inference
                context = EventContext(
                    window_title=group['window_title'] or "Unknown",
                    input_intensity=int(group['avg_intensity'] or 0),
                    history=[],
                    vision_description=vision_description
                )
                inference_result = self.inference.synthesize(context)
                
                # Persist results
                await self._persist_group(group, inference_result)
                processed_count += group['event_count']
                
                logger.debug(f"Processed group '{group['process_name'][:20]}' ({group['event_count']} events)")
                
            except Exception as e:
                logger.error(f"Error processing group: {e}")
                continue
        
        return processed_count

    def _should_skip_pid(self, group: dict) -> bool:
        """Check if PID was recently analyzed (deduplication)."""
        process_name = group.get('process_name', 'unknown')
        current_time = time.time()
        
        if process_name in self._recent_pids:
            time_since = current_time - self._recent_pids[process_name]
            if time_since < DEDUP_WINDOW_SEC:
                logger.debug(f"Skipping duplicate PID '{process_name}' ({time_since:.1f}s ago)")
                return True
        
        # Record and cleanup
        self._recent_pids[process_name] = current_time
        self._recent_pids = {
            k: v for k, v in self._recent_pids.items()
            if current_time - v < 60
        }
        return False

    async def _run_vlm(self, group: dict) -> Optional[str]:
        """Run VLM analysis on group screenshot if available."""
        # Guard clauses first (fail-fast pattern)
        if not self.vision_agent:
            return None
        if not self.guard.check_vram_availability(threshold_mb=VRAM_CHECK_THRESHOLD_MB):
            return None
        
        screenshot_path = group.get('screenshot_path')
        screenshot_data = group.get('screenshot_data')
        image_ready = (screenshot_data is not None) or (screenshot_path and os.path.exists(screenshot_path))
        
        if not image_ready:
            return None
        
        try:
            source_type = "RAM" if screenshot_data else "Disk"
            logger.debug(f"Running VLM ({source_type})")
            
            description = self.vision_agent.describe_screenshot(
                image_path=screenshot_path or "ephemeral.jpg",
                image_data=screenshot_data
            )
            if description:
                logger.debug(f"VLM result: {description[:50]}...")
            return description
            
        except Exception as e:
            logger.warning(f"VLM analysis failed: {e}")
            return None

    async def _persist_group(self, group: dict, inference_result: InferenceResult) -> None:
        """Persist group processing results."""
        if self.redis_consumer:
            await self.db.archive_enriched_group(
                group,
                inference_result.intent,
                inference_result.tags
            )
            await asyncio.to_thread(self.redis_consumer.ack_groups, [group])
        else:
            await self.db.batch_insert_context(
                event_ids=group['event_ids'],
                user_intent=inference_result.intent,
                tags=inference_result.tags
            )
            await self.db.batch_mark_processed(group['event_ids'])

    async def run(self) -> None:
        """Main entry point."""
        try:
            await self.initialize()
            self.running = True
            await self.event_loop()
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            raise
        finally:
            await self.shutdown()
