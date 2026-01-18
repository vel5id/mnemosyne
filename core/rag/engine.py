"""
Graph RAG Engine for Mnemosyne Core V5.0

Provides unified interface for:
- Semantic search via LlamaIndex (Redis VectorStore backend)
- Graph analytics via NetworkX
- Write-behind pattern for efficient indexing

Phase 8: Enterprise-grade RAG architecture.
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

import networkx as nx

logger = logging.getLogger(__name__)

# Named constants
DEFAULT_REDIS_URL = "redis://localhost:6379"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_TOP_K = 5


class GraphRAGEngine:
    """
    Unified interface for semantic search (LlamaIndex) and graph analytics (NetworkX).
    
    Architecture:
        - VectorStore: Redis (via LlamaIndex) for semantic embeddings
        - DocStore: Redis for document storage
        - Graph: NetworkX for topology analysis (in-memory, persisted to SQLite)
    
    Usage:
        engine = GraphRAGEngine()
        engine.index_session(session)
        results = engine.query("What was I debugging yesterday?")
    """
    
    def __init__(
        self,
        redis_url: str = DEFAULT_REDIS_URL,
        embed_model: str = DEFAULT_EMBED_MODEL,
        ollama_host: str = "http://localhost:11434"
    ):
        """
        Initialize the Graph RAG Engine.
        
        Args:
            redis_url: Redis connection URL.
            embed_model: Ollama embedding model name.
            ollama_host: Ollama API host URL.
        """
        self.redis_url = redis_url
        self.embed_model_name = embed_model
        self.ollama_host = ollama_host
        
        # Initialize components lazily
        self._index = None
        self._embed_model = None
        self._storage_context = None
        
        # NetworkX graph for topology analysis
        self.graph = nx.DiGraph()
        
        # Track indexed sessions
        self._indexed_sessions: set = set()
        
        logger.info(f"GraphRAGEngine initialized (Redis: {redis_url})")
    
    def _ensure_initialized(self) -> bool:
        """
        Lazy initialization of LlamaIndex components.
        Returns True if successfully initialized.
        """
        if self._index is not None:
            return True
        
        try:
            # Import LlamaIndex components
            from llama_index.core import VectorStoreIndex, Document, Settings
            from llama_index.vector_stores.redis import RedisVectorStore
            from llama_index.embeddings.ollama import OllamaEmbedding
            from llama_index.core.storage import StorageContext
            
            # Setup embedding model (local Ollama)
            self._embed_model = OllamaEmbedding(
                model_name=self.embed_model_name,
                base_url=self.ollama_host
            )
            Settings.embed_model = self._embed_model
            
            # Setup Redis VectorStore
            self._vector_store = RedisVectorStore(
                redis_url=self.redis_url,
                index_name="mnemosyne_sessions",
                overwrite=False
            )
            
            self._storage_context = StorageContext.from_defaults(
                vector_store=self._vector_store
            )
            
            # Create or load index
            self._index = VectorStoreIndex.from_vector_store(
                vector_store=self._vector_store,
                storage_context=self._storage_context
            )
            
            logger.info("LlamaIndex components initialized successfully")
            return True
            
        except ImportError as e:
            logger.warning(f"LlamaIndex not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize LlamaIndex: {e}")
            return False
    
    def index_session(self, session: Any) -> bool:
        """
        Index a session for semantic search.
        
        Args:
            session: Session object with activity_summary, primary_process, etc.
        
        Returns:
            True if successfully indexed.
        """
        if not self._ensure_initialized():
            logger.debug("LlamaIndex not initialized, skipping indexing")
            return False
        
        try:
            from llama_index.core import Document
            
            # Create document from session
            session_uuid = getattr(session, 'session_uuid', str(id(session)))
            
            if session_uuid in self._indexed_sessions:
                logger.debug(f"Session {session_uuid[:8]} already indexed")
                return True
            
            # Build document text
            summary = getattr(session, 'activity_summary', None) or ""
            process = getattr(session, 'primary_process', "unknown")
            window = getattr(session, 'primary_window', "unknown")
            duration = getattr(session, 'duration_seconds', 0)
            
            doc_text = f"""
Session: {process} - {window}
Duration: {duration // 60} minutes
Summary: {summary}
"""
            
            # Create LlamaIndex document
            doc = Document(
                text=doc_text.strip(),
                metadata={
                    "session_uuid": session_uuid,
                    "process": process,
                    "duration_seconds": duration
                }
            )
            
            # Insert into index
            self._index.insert(doc)
            self._indexed_sessions.add(session_uuid)
            
            # Update knowledge graph
            self._update_graph(session)
            
            logger.debug(f"Indexed session {session_uuid[:8]}: {process}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to index session: {e}")
            return False
    
    def query(self, question: str, top_k: int = DEFAULT_TOP_K) -> List[Dict[str, Any]]:
        """
        Semantic search across indexed sessions.
        
        Args:
            question: Natural language query.
            top_k: Number of results to return.
        
        Returns:
            List of matching results with score and metadata.
        """
        if not self._ensure_initialized():
            logger.warning("LlamaIndex not initialized, returning empty results")
            return []
        
        try:
            query_engine = self._index.as_query_engine(similarity_top_k=top_k)
            response = query_engine.query(question)
            
            results = []
            for node in response.source_nodes:
                results.append({
                    "text": node.text,
                    "score": node.score,
                    "metadata": node.metadata
                })
            
            logger.info(f"Query '{question[:30]}...' returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return []
    
    def _update_graph(self, session: Any) -> None:
        """
        Update NetworkX knowledge graph with session data.
        
        Nodes: Session, Application, Project, Concept
        Edges: USES, WORKS_ON, MENTIONS
        """
        try:
            import re
            
            session_uuid = getattr(session, 'session_uuid', str(id(session)))
            process = getattr(session, 'primary_process', "unknown")
            summary = getattr(session, 'activity_summary', "") or ""
            tags = getattr(session, 'tags', []) or []
            
            # Add session node
            session_node = f"session:{session_uuid[:8]}"
            self.graph.add_node(
                session_node,
                type="Session",
                summary=summary[:100]
            )
            
            # Add application node and edge
            app_node = f"app:{process}"
            self.graph.add_node(app_node, type="Application")
            self.graph.add_edge(session_node, app_node, relation="USES")
            
            # Extract WikiLinks from summary and add as concepts
            wikilinks = re.findall(r'\[\[(.*?)\]\]', summary)
            for concept in wikilinks:
                concept_node = f"concept:{concept.lower()}"
                self.graph.add_node(concept_node, type="Concept")
                self.graph.add_edge(session_node, concept_node, relation="MENTIONS")
            
            # Add tags as concepts
            for tag in tags:
                tag_node = f"concept:{tag.lower()}"
                self.graph.add_node(tag_node, type="Concept")
                self.graph.add_edge(session_node, tag_node, relation="MENTIONS")
            
            logger.debug(f"Graph updated: {len(self.graph.nodes)} nodes, {len(self.graph.edges)} edges")
            
        except Exception as e:
            logger.error(f"Failed to update graph: {e}")
    
    def find_related(self, entity: str, depth: int = 2) -> List[Dict[str, Any]]:
        """
        Find related entities via graph traversal.
        
        Args:
            entity: Entity name to search from.
            depth: Maximum traversal depth.
        
        Returns:
            List of related entities with paths.
        """
        # Normalize entity name
        entity_lower = entity.lower()
        
        # Find matching nodes
        matching_nodes = [
            n for n in self.graph.nodes
            if entity_lower in n.lower()
        ]
        
        if not matching_nodes:
            logger.debug(f"No nodes matching '{entity}'")
            return []
        
        results = []
        for start_node in matching_nodes:
            # BFS traversal
            for target in nx.single_source_shortest_path_length(
                self.graph, start_node, cutoff=depth
            ):
                if target != start_node:
                    node_data = self.graph.nodes[target]
                    results.append({
                        "node": target,
                        "type": node_data.get("type", "Unknown"),
                        "from": start_node
                    })
        
        logger.info(f"Found {len(results)} related entities for '{entity}'")
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        return {
            "indexed_sessions": len(self._indexed_sessions),
            "graph_nodes": len(self.graph.nodes),
            "graph_edges": len(self.graph.edges),
            "llama_index_ready": self._index is not None
        }
    
    def save_graph(self, path: Path) -> None:
        """Save graph to JSON file."""
        data = nx.node_link_data(self.graph)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Graph saved to {path}")
    
    def load_graph(self, path: Path) -> None:
        """Load graph from JSON file."""
        if not path.exists():
            logger.debug(f"Graph file not found: {path}")
            return
        
        with open(path, 'r') as f:
            data = json.load(f)
        self.graph = nx.node_link_graph(data)
        logger.info(f"Graph loaded: {len(self.graph.nodes)} nodes")
