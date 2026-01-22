"""
Mnemosyne Status Dashboard - System Monitoring API

Provides a web interface and REST API for monitoring:
- System health (VRAM, CPU, RAM)
- Database statistics
- Model status (VLM, LLM)
- Recent activity log

Usage:
    python status_dashboard.py
    # Open http://localhost:8765 in browser
"""

import asyncio
import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import httpx

# Conditional imports
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

try:
    import pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False
    pynvml = None

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from core.dal.sqlite_provider import DatabaseProvider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Mnemosyne Status Dashboard",
    version="3.0",
    description="System monitoring for Mnemosyne Core"
)

# Configuration
# Configuration
DB_PATH = os.getenv("MNEMOSYNE_DB_PATH", ".mnemosyne/activity.db")
REDIS_HOST = os.getenv("MNEMOSYNE_REDIS_HOST", None) # Default None to auto-detect or fail safely
OLLAMA_VLM_HOST = os.getenv("OLLAMA_VLM_HOST", "http://localhost:11434")
OLLAMA_LLM_HOST = os.getenv("OLLAMA_LLM_HOST", "http://localhost:11435")
VLM_MODEL = os.getenv("VLM_MODEL", "minicpm-v")
LLM_MODEL_HEAVY = os.getenv("LLM_MODEL_HEAVY", "deepseek-r1:1.5b")
LLM_MODEL_LIGHT = os.getenv("LLM_MODEL_LIGHT", "phi3:mini")

# Database connection
db: Optional[DatabaseProvider] = None


@app.on_event("startup")
async def startup():
    """Initialize database connection."""
    global db
    db = DatabaseProvider(DB_PATH)
    try:
        await db.connect()
        logger.info(f"Connected to database: {DB_PATH}")
    except Exception as e:
        logger.warning(f"Database not available: {e}")
        db = None
    
    # Initialize NVML
    if PYNVML_AVAILABLE:
        try:
            pynvml.nvmlInit()
            logger.info("NVML initialized")
        except Exception as e:
            logger.warning(f"NVML init failed: {e}")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    global db
    if db:
        await db.disconnect()
    
    if PYNVML_AVAILABLE:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass


async def get_system_stats() -> dict:
    """Get system resource statistics."""
    stats = {
        "cpu_percent": 0,
        "ram_percent": 0,
        "ram_used_gb": 0,
        "ram_total_gb": 0,
        "vram_used_gb": None,
        "vram_total_gb": None,
        "vram_free_gb": None,
        "gpu_name": None
    }
    
    if PSUTIL_AVAILABLE:
        stats["cpu_percent"] = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        stats["ram_percent"] = mem.percent
        stats["ram_used_gb"] = round(mem.used / 1024 / 1024 / 1024, 2)
        stats["ram_total_gb"] = round(mem.total / 1024 / 1024 / 1024, 2)
    
    if PYNVML_AVAILABLE:
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            name = pynvml.nvmlDeviceGetName(handle)
            
            stats["gpu_name"] = name if isinstance(name, str) else name.decode('utf-8')
            stats["vram_total_gb"] = round(info.total / 1024 / 1024 / 1024, 2)
            stats["vram_used_gb"] = round(info.used / 1024 / 1024 / 1024, 2)
            stats["vram_free_gb"] = round(info.free / 1024 / 1024 / 1024, 2)
        except Exception as e:
            logger.debug(f"VRAM query failed: {e}")
    
    return stats


async def get_db_stats() -> dict:
    """Get database statistics."""
    if db is None:
        return {"status": "disconnected", "total_events": 0, "pending_events": 0, "enriched_events": 0}
    
    try:
        stats = await db.get_stats()
        stats["status"] = "connected"
        return stats
    except Exception as e:
        return {"status": f"error: {e}", "total_events": 0, "pending_events": 0, "enriched_events": 0}

async def get_redis_stats() -> dict:
    """Get Redis queue statistics."""
    if not REDIS_AVAILABLE:
        return {"status": "module_missing", "queue_depth": 0, "pending": 0}
        
    host = REDIS_HOST or "localhost"
    try:
        # Use sync client (fast enough for dashboard)
        r = redis.Redis(host=host, port=6379, socket_connect_timeout=0.5, socket_timeout=0.5)
        
        info = r.info('memory')
        
        # Check stream
        try:
            q_len = r.xlen("mnemosyne:events")
            
            # Check consumer group lag
            pending_info = r.xpending("mnemosyne:events", "mnemosyne_brain_group")
            pending = pending_info['pending']
        except Exception:
            q_len = 0
            pending = 0
            
        return {
            "status": "connected",
            "host": host,
            "queue_depth": q_len,
            "pending": pending,
            "memory": info.get("used_memory_human", "N/A")
        }
    except Exception as e:
        return {"status": "disconnected", "error": str(e), "queue_depth": 0, "pending": 0}

async def check_ollama_status(host: str, name: str) -> dict:
    """Check Ollama instance status."""
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(f"{host}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get('models', [])
                return {
                    "status": "online",
                    "model_count": len(models),
                    "models": [m['name'] for m in models]
                }
    except Exception:
        pass
    return {"status": "offline", "model_count": 0, "models": []}

async def get_detailed_db_stats() -> dict:
    """Get detailed breakdowns from SQLite."""
    if db is None:
        return {}
    try:
        counts = {}
        # Use the provider's internal connection
        conn = db._connection
        if conn is None:
            return {}
        
        # VLM events (has vlm_description in context_enrichment)
        try:
            async with conn.execute(
                "SELECT COUNT(*) FROM context_enrichment WHERE vlm_description IS NOT NULL"
            ) as c:
                counts['vlm_events'] = (await c.fetchone())[0]
        except Exception:
            counts['vlm_events'] = 0
        
        # LLM events (has user_intent in context_enrichment)
        try:
            async with conn.execute(
                "SELECT COUNT(*) FROM context_enrichment WHERE user_intent IS NOT NULL"
            ) as c:
                counts['llm_events'] = (await c.fetchone())[0]
        except Exception:
            counts['llm_events'] = 0
        
        # Screenshot events (has screenshot_path in raw_events)
        try:
            async with conn.execute(
                "SELECT COUNT(*) FROM raw_events WHERE screenshot_path IS NOT NULL AND screenshot_path != ''"
            ) as c:
                counts['screenshot_events'] = (await c.fetchone())[0]
        except Exception:
            counts['screenshot_events'] = 0
        
        # Telemetry events (total raw)
        try:
            async with conn.execute("SELECT COUNT(*) FROM raw_events") as c:
                counts['telemetry_events'] = (await c.fetchone())[0]
        except Exception:
            counts['telemetry_events'] = 0
        
        return counts
        
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        return {}

async def get_recent_sessions_stats() -> list:
    """Get recent sessions."""
    if db is None:
        return []
    try:
        sessions = await db.get_recent_sessions(limit=5)
        # Format timestamps with safety checks
        for s in sessions:
            try:
                ts = s.get('start_time', 0)
                if ts is None:
                    ts = 0
                # Handle milliseconds (if > year 3000 in seconds, assume ms)
                if ts > 32503680000:
                    ts = ts / 1000
                s['time_ago'] = datetime.fromtimestamp(ts).strftime('%H:%M')
            except (OSError, ValueError, OverflowError):
                s['time_ago'] = '--:--'
            
            dur = s.get('duration_seconds', 0) or 0
            s['duration'] = f"{dur // 60}m"
        return sessions
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        return []





@app.get("/api/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "mnemosyne-dashboard"}


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the dashboard HTML from external template."""
    template_path = Path(__file__).parent / "templates" / "dashboard.html"
    
    if not template_path.exists():
        logger.error(f"Template not found: {template_path}")
        return HTMLResponse(
            content="<h1>Error: Dashboard template not found</h1>",
            status_code=500
        )
    
    html = template_path.read_text(encoding="utf-8")
    return HTMLResponse(content=html)

async def get_rag_stats() -> dict:
    """Get Knowledge Graph statistics with detailed breakdown."""
    try:
        graph_path = Path(DB_PATH).parent / "knowledge_graph.json"
        if not graph_path.exists():
            return {"nodes": 0, "edges": 0, "last_updated": "Never", "breakdown": {}, "concepts": [], "applications": []}
        
        import json
        with open(graph_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        nodes = data.get("nodes", [])
        edges = data.get("links", [])
        
        # Breakdown by type
        breakdown = {}
        concepts = []
        applications = []
        sessions_with_summary = []
        
        for node in nodes:
            node_type = node.get("type", "Unknown")
            breakdown[node_type] = breakdown.get(node_type, 0) + 1
            
            if node_type == "Concept":
                concept_id = node.get("id", "")
                if concept_id.startswith("concept:"):
                    concepts.append(concept_id.replace("concept:", ""))
            elif node_type == "Application":
                app_id = node.get("id", "")
                if app_id.startswith("app:"):
                    applications.append(app_id.replace("app:", ""))
            elif node_type == "Session":
                summary = node.get("summary", "")
                if summary and len(summary) > 10:
                    sessions_with_summary.append({
                        "id": node.get("id", "").replace("session:", "")[:8],
                        "summary": summary[:100]
                    })
        
        # Extract recent Event nodes (new)
        recent_events = []
        for node in nodes:
            if node.get("type") == "Event":
                event_id = node.get("id", "")
                recent_events.append({
                    "id": event_id.split(":")[-1] if ":" in event_id else event_id,
                    "process": node.get("process", "unknown"),
                    "window": node.get("window", "")[:30],
                    "intent": node.get("intent", "")[:60]
                })
        
        # Sort by id (most recent first) and limit
        recent_events = recent_events[-10:][::-1]
        
        return {
            "nodes": len(nodes),
            "edges": len(edges),
            "last_updated": datetime.fromtimestamp(graph_path.stat().st_mtime).strftime('%H:%M:%S'),
            "breakdown": breakdown,
            "concepts": concepts[:20],  # Top 20 concepts
            "applications": applications[:10],
            "sessions_with_summary": sessions_with_summary[:5],  # Last 5 sessions with summaries
            "recent_events": recent_events  # New: Event-level details
        }
    except Exception as e:
        logger.debug(f"Error getting RAG stats: {e}")
        return {"nodes": 0, "edges": 0, "last_updated": "Error", "breakdown": {}, "concepts": [], "applications": [], "recent_events": []}

async def get_recent_logs(limit: int = 20) -> list:
    """Fetch raw event log trail."""
    if db is None:
        return []
    try:
        conn = db._connection
        if conn is None:
            return []
        
        # Join raw_events with context_enrichment to get intents
        query = """
            SELECT e.id, e.timestamp_utc, e.process_name, e.window_title, c.user_intent
            FROM raw_events e
            LEFT JOIN context_enrichment c ON e.id = c.event_id
            ORDER BY e.id DESC
            LIMIT ?
        """
        async with conn.execute(query, (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "time": row[1] or "",
                    "process": row[2] or "Unknown",
                    "window": row[3] or "",
                    "intent": row[4] or "Processing..."
                }
                for row in rows
            ]
    except Exception as e:
        logger.debug(f"Error fetching logs: {e}")
        return []

@app.get("/api/status")
async def api_status():
    """Get full system status."""
    system = await get_system_stats()
    database = await get_db_stats()
    analytics = await get_detailed_db_stats()
    redis_stats = await get_redis_stats()
    sessions = await get_recent_sessions_stats()
    logs = await get_recent_logs(20)
    rag = await get_rag_stats()
    
    vlm = await check_ollama_status(OLLAMA_VLM_HOST, "VLM")
    llm = await check_ollama_status(OLLAMA_LLM_HOST, "LLM")
    
    return {
        "timestamp": datetime.now().isoformat(),
        "system": system,
        "database": {**database, "analytics": analytics},
        "redis": redis_stats,
        "sessions": sessions,
        "logs": logs,
        "rag": rag,
        "models": {
            "vlm": {
                **vlm,
                "configured_model": VLM_MODEL
            },
            "llm": {
                **llm,
                "configured_heavy": LLM_MODEL_HEAVY,
                "configured_light": LLM_MODEL_LIGHT
            }
        }
    }


if __name__ == "__main__":
    uvicorn.run(
        "status_dashboard:app",
        host="0.0.0.0",
        port=8765,
        reload=True,
        log_level="info"
    )
