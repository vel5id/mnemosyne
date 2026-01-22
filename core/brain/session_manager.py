"""
Mnemosyne Core V5.0 - Session Manager Module

Manages session lifecycle, archival, and Graph RAG indexing.
Extracted from Brain class to follow Single Responsibility Principle.

Usage:
    manager = SessionManager(db, inference, rag_engine)
    await manager.archive(session)
"""

import re
import logging
from pathlib import Path
from typing import Optional, Any, TYPE_CHECKING

from core.dal.sqlite_provider import DatabaseProvider
from core.cognition.inference import IntentInference

if TYPE_CHECKING:
    from core.aggregation.session_tracker import Session

logger = logging.getLogger(__name__)

# Named constants
MIN_SESSION_DURATION_SEC = 5
MAX_CONCEPT_RELATIONSHIPS = 5


class SessionManager:
    """
    Manages session lifecycle and archival.
    
    Responsibilities:
        - Generate LLM summaries for completed sessions
        - Extract WikiLink tags from summaries
        - Persist sessions to SQLite
        - Cleanup screenshots after archival
        - Index sessions in Graph RAG
        - Run secondary analysis for concept extraction
    """
    
    def __init__(
        self,
        db: DatabaseProvider,
        inference: IntentInference,
        rag_engine: Optional[Any] = None,
        db_path: Optional[Path] = None
    ) -> None:
        """
        Initialize SessionManager.
        
        Args:
            db: Database provider for persistence.
            inference: LLM inference engine for summaries.
            rag_engine: Optional Graph RAG engine for indexing.
            db_path: Path to database (for knowledge graph persistence).
        """
        self.db = db
        self.inference = inference
        self.rag_engine = rag_engine
        self.db_path = db_path or Path(".mnemosyne/activity.db")

    async def archive(self, session: "Session") -> None:
        """
        Archive a completed session to SQLite with LLM summary.
        
        Guards against micro-sessions (<5 seconds).
        
        Args:
            session: Completed Session object to archive.
        """
        # Guard: Skip micro-sessions
        if session.duration_seconds < MIN_SESSION_DURATION_SEC:
            logger.debug(
                f"Skipping micro-session ({session.duration_seconds}s < {MIN_SESSION_DURATION_SEC}s)"
            )
            return
        
        try:
            # Generate LLM summary
            summary = self._generate_summary(session)
            session.activity_summary = summary
            
            # Extract WikiLinks as tags
            session.tags = self._extract_wikilinks(summary)
            
            # Persist to database
            await self._persist_session(session)
            
            logger.info(
                f"📝 Session archived: {session.primary_process} - "
                f"{session.duration_seconds}s - {summary[:50] if summary else 'No summary'}..."
            )
            
            # Cleanup screenshots
            cleaned = self._cleanup_screenshots(session)
            if cleaned > 0:
                logger.debug(f"🗑️ Cleaned {cleaned} screenshots after session archival")
            
            # Index in Graph RAG
            self._index_to_rag(session)
            
            # Run secondary analysis
            await self._run_secondary_analysis(session, summary)
            
        except Exception as e:
            logger.error(f"Failed to archive session: {e}")

    def _generate_summary(self, session: "Session") -> str:
        """Generate LLM summary for session."""
        return self.inference.summarize_session(
            duration_minutes=session.duration_seconds / 60,
            primary_process=session.primary_process,
            primary_window=session.primary_window,
            transitions=session.window_transitions,
            avg_intensity=session.avg_input_intensity,
            event_count=session.event_count
        )

    def _extract_wikilinks(self, text: Optional[str]) -> list:
        """Extract [[WikiLinks]] from text."""
        if not text:
            return []
        wikilinks = re.findall(r'\[\[(.*?)\]\]', text)
        return list(set(wikilinks))

    async def _persist_session(self, session: "Session") -> None:
        """Persist session to SQLite."""
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

    def _cleanup_screenshots(self, session: "Session") -> int:
        """
        Remove screenshots after session archival.
        
        Returns:
            Number of screenshots deleted.
        """
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
        return cleaned_count

    def _index_to_rag(self, session: "Session") -> None:
        """Index session in Graph RAG."""
        if not self.rag_engine:
            return
        
        try:
            self.rag_engine.index_session(session)
            logger.debug("📊 Session indexed in Graph RAG")
        except Exception as e:
            logger.debug(f"RAG indexing failed: {e}")

    async def _run_secondary_analysis(
        self,
        session: "Session",
        summary: Optional[str]
    ) -> None:
        """
        Run secondary LLM pass for deeper concept extraction.
        
        Args:
            session: Session object.
            summary: Primary LLM summary.
        """
        if not summary or len(summary) <= 30:
            return
        
        if not self.rag_engine:
            return
        
        try:
            deep_insights = self.inference.secondary_analysis(
                summary=summary,
                process=session.primary_process,
                event_count=session.event_count,
                duration_minutes=session.duration_seconds / 60
            )
            
            if not deep_insights:
                return
            
            # Add concept relationships to graph
            relationships = deep_insights.get('concept_relationships', [])
            added_count = 0
            
            for rel in relationships[:MAX_CONCEPT_RELATIONSHIPS]:
                if len(rel) == 3:
                    concept_a, relation, concept_b = rel
                    self.rag_engine.graph.add_node(
                        f"concept:{concept_a.lower()}", 
                        type="Concept"
                    )
                    self.rag_engine.graph.add_node(
                        f"concept:{concept_b.lower()}", 
                        type="Concept"
                    )
                    self.rag_engine.graph.add_edge(
                        f"concept:{concept_a.lower()}",
                        f"concept:{concept_b.lower()}",
                        relation=relation
                    )
                    added_count += 1
            
            if added_count > 0:
                logger.info(
                    f"🔗 Added {added_count} concept relationships from secondary analysis"
                )
                
        except Exception as e:
            logger.debug(f"Secondary analysis failed: {e}")

    def save_graph(self) -> None:
        """Save knowledge graph to disk."""
        if not self.rag_engine:
            return
        
        try:
            graph_path = self.db_path.parent / "knowledge_graph.json"
            self.rag_engine.save_graph(graph_path)
            logger.info(f"Knowledge graph saved ({len(self.rag_engine.graph.nodes)} nodes)")
        except Exception as e:
            logger.warning(f"Failed to save knowledge graph: {e}")

    def load_graph(self) -> None:
        """Load knowledge graph from disk."""
        if not self.rag_engine:
            return
        
        try:
            graph_path = self.db_path.parent / "knowledge_graph.json"
            self.rag_engine.load_graph(graph_path)
            logger.info("GraphRAGEngine initialized")
        except Exception as e:
            logger.warning(f"GraphRAGEngine not available: {e}")
