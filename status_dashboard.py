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

async def get_detailed_db_stats() -> dict:
    """Get detailed breakdowns."""
    if db is None: return {}
    return await db.get_detailed_analytics()


async def check_ollama_status(host: str, name: str) -> dict:
    """Check Ollama server status."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{host}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = [m["name"] for m in data.get("models", [])]
                return {"status": "online", "models": models, "host": host}
            else:
                return {"status": "error", "models": [], "host": host}
    except httpx.ConnectError:
        return {"status": "offline", "models": [], "host": host}
    except Exception as e:
        return {"status": f"error: {str(e)}", "models": [], "host": host}


@app.get("/api/status")
async def api_status():
    """Get full system status."""
    system = await get_system_stats()
    database = await get_db_stats()
    analytics = await get_detailed_db_stats()
    redis_stats = await get_redis_stats()
    
    vlm = await check_ollama_status(OLLAMA_VLM_HOST, "VLM")
    llm = await check_ollama_status(OLLAMA_LLM_HOST, "LLM")
    
    return {
        "timestamp": datetime.now().isoformat(),
        "system": system,
        "database": {**database, "analytics": analytics},
        "redis": redis_stats,
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


@app.get("/api/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "mnemosyne-dashboard"}


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the dashboard HTML."""
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mnemosyne Observability</title>
    <style>
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #1a1a24;
            --accent: #6366f1;
            --accent-glow: rgba(99, 102, 241, 0.3);
            --text-primary: #e4e4e7;
            --text-secondary: #a1a1aa;
            --success: #22c55e;
            --warning: #f59e0b;
            --error: #ef4444;
            --redis-color: #dc2626;
            --sqlite-color: #0ea5e9;
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 2rem;
        }
        
        .header {
            text-align: center;
            margin-bottom: 2rem;
        }
        
        .header h1 {
            font-size: 2.5rem;
            background: linear-gradient(135deg, var(--accent), #a855f7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            max-width: 1400px;
            margin: 0 auto;
        }
        
        .card {
            background: var(--bg-card);
            border-radius: 16px;
            padding: 1.5rem;
            border: 1px solid rgba(255,255,255,0.05);
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }
        
        .card h2 {
            font-size: 1rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--text-secondary);
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
        }
        
        .card h2 .icon { margin-right: 0.5rem; }
        
        .metric {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        
        .metric:last-child { border-bottom: none; }
        
        .metric .label { color: var(--text-secondary); }
        .metric .value { font-weight: 600; font-size: 1.1rem; }
        
        .status-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .status-online { background: var(--success); box-shadow: 0 0 8px var(--success); }
        .status-offline { background: var(--error); box-shadow: 0 0 8px var(--error); }
        
        .progress-bar {
            width: 100%;
            height: 6px;
            background: var(--bg-secondary);
            border-radius: 3px;
            overflow: hidden;
            margin-top: 0.5rem;
        }
        
        .progress-fill {
            height: 100%;
            background: var(--accent);
            border-radius: 3px;
            transition: width 0.3s ease;
        }

        .breakdown-chart {
            display: flex;
            height: 20px;
            width: 100%;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 1rem;
        }
        
        .chart-segment {
            height: 100%;
            transition: width 0.5s ease;
        }
        
        .legend {
            display: flex;
            gap: 1rem;
            margin-top: 0.5rem;
            font-size: 0.8rem;
            color: var(--text-secondary);
        }
        
        .legend-item { display: flex; align-items: center; gap: 0.3rem; }
        .legend-color { width: 8px; height: 8px; border-radius: 50%; }

    </style>
</head>
<body>
    <div class="header">
        <h1>🧠 Mnemosyne Observability</h1>
        <p>Hyper-RAM (v4.0) Status</p>
    </div>
    
    <div class="grid" id="dashboard">
        <!-- Rendered via JS -->
    </div>
    
    <script>
        async function fetchStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                renderDashboard(data);
            } catch (error) {
                console.error(error);
            }
        }
        
        function renderDashboard(data) {
            const sys = data.system;
            const db = data.database;
            const redis = data.redis;
            const analytics = db.analytics || {};
            
            // Calculate Pipeline Breakdown
            const total = analytics.telemetry_events || 1;
            const p_telemetry = ((analytics.telemetry_events || 0) / total * 100).toFixed(1);
            const p_llm = ((analytics.llm_events || 0) / total * 100).toFixed(1);
            const p_vlm = ((analytics.vlm_events || 0) / total * 100).toFixed(1);
            const p_screen = ((analytics.screenshot_events || 0) / total * 100).toFixed(1);

            document.getElementById('dashboard').innerHTML = `
                <!-- System -->
                <div class="card">
                    <h2><span class="icon">💻</span> Resources</h2>
                    <div class="metric"><span class="label">CPU</span><span class="value">${sys.cpu_percent}%</span></div>
                    <div class="progress-bar"><div class="progress-fill" style="width: ${sys.cpu_percent}%"></div></div>
                    <div class="metric"><span class="label">RAM</span><span class="value">${sys.ram_used_gb}/${sys.ram_total_gb} GB</span></div>
                    <div class="progress-bar"><div class="progress-fill" style="width: ${sys.ram_percent}%"></div></div>
                </div>

                <!-- Redis (Hot Layer) -->
                <div class="card" style="border-top: 2px solid var(--redis-color)">
                    <h2>
                        <span class="status-indicator ${redis.status==='connected'?'status-online':'status-offline'}"></span>
                        <span class="icon">🚀</span> Active Pipeline (Redis)
                    </h2>
                    <div class="metric"><span class="label">Status</span><span class="value">${redis.status}</span></div>
                    <div class="metric"><span class="label">Host</span><span class="value">${redis.host || 'N/A'}</span></div>
                    <div class="metric"><span class="label">Ingestion Queue</span><span class="value">${redis.queue_depth}</span></div>
                    <div class="metric"><span class="label">Processing Lag</span><span class="value">${redis.pending}</span></div>
                </div>

                <!-- SQLite (Cold Layer) -->
                <div class="card" style="border-top: 2px solid var(--sqlite-color)">
                    <h2>
                        <span class="status-indicator ${db.status==='connected'?'status-online':'status-offline'}"></span>
                        <span class="icon">💾</span> Archive (SQLite)
                    </h2>
                    <div class="metric"><span class="label">Total Events</span><span class="value">${(db.total_events||0).toLocaleString()}</span></div>
                    <div class="metric"><span class="label">Enriched</span><span class="value">${(db.enriched_events||0).toLocaleString()}</span></div>
                    
                    <div style="margin-top: 1rem; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 0.5rem">
                         <div class="metric"><span class="label">LLM Context</span><span class="value">${analytics.llm_events || 0}</span></div>
                         <div class="metric"><span class="label">VLM Analysis</span><span class="value">${analytics.vlm_events || 0}</span></div>
                         <div class="metric"><span class="label">Screenshots</span><span class="value">${analytics.screenshot_events || 0}</span></div>
                    </div>
                </div>
                
                <!-- Content Breakdown -->
                <div class="card">
                     <h2><span class="icon">📊</span> Pipeline Efficiency</h2>
                     <div class="metric"><span class="label">LLM Coverage</span><span class="value">${p_llm}%</span></div>
                     <div class="metric"><span class="label">VLM Coverage</span><span class="value">${p_vlm}%</span></div>
                     
                     <div class="breakdown-chart">
                        <div class="chart-segment" style="width: ${p_llm}%; background: #a855f7" title="LLM"></div>
                        <div class="chart-segment" style="width: ${p_vlm}%; background: #ec4899" title="VLM"></div>
                        <div class="chart-segment" style="width: ${100 - p_llm - p_vlm}%; background: #3b82f6" title="Raw"></div>
                     </div>
                     <div class="legend">
                        <div class="legend-item"><div class="legend-color" style="background: #a855f7"></div>LLM</div>
                        <div class="legend-item"><div class="legend-color" style="background: #ec4899"></div>VLM</div>
                        <div class="legend-item"><div class="legend-color" style="background: #3b82f6"></div>Raw</div>
                     </div>
                </div>
            `;
        }
        
        // Loop
        fetchStatus();
        setInterval(fetchStatus, 2000); // 2s refresh for realtime redis feel
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html)


if __name__ == "__main__":
    uvicorn.run(
        "status_dashboard:app",
        host="0.0.0.0",
        port=8765,
        reload=True,
        log_level="info"
    )
