"""
Database Maintenance Utilities for Mnemosyne Core

Provides periodic maintenance functions to keep database size under control:
- VACUUM to reclaim space from deleted rows
- Prune old sessions based on retention policy
- Screenshot cleanup for orphaned files

Usage:
    python -m core.dal.maintenance

Author: Nexus/Praxis (Phase 7: Storage Optimization)
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

# Named constants (Axiom: no magic numbers)
DEFAULT_SESSION_RETENTION_DAYS = 30
DEFAULT_VACUUM_INTERVAL_HOURS = 24


async def vacuum_database(db_path: Path) -> None:
    """
    Run VACUUM to reclaim space from deleted rows.
    
    VACUUM rebuilds the database file, returning unused pages to the OS.
    This can significantly reduce file size after bulk deletions.
    
    Warning: VACUUM requires exclusive lock and can take time on large DBs.
    
    Args:
        db_path: Path to the SQLite database file.
    """
    logger.info(f"Starting VACUUM on {db_path}...")
    start_time = time.time()
    
    async with aiosqlite.connect(db_path) as conn:
        # Get size before
        size_before = db_path.stat().st_size if db_path.exists() else 0
        
        await conn.execute("VACUUM")
        await conn.commit()
        
        # Get size after
        size_after = db_path.stat().st_size if db_path.exists() else 0
        
    elapsed = time.time() - start_time
    saved = size_before - size_after
    
    logger.info(
        f"VACUUM complete in {elapsed:.1f}s. "
        f"Size: {size_before/1024:.1f}KB -> {size_after/1024:.1f}KB "
        f"(saved {saved/1024:.1f}KB)"
    )


async def prune_old_sessions(
    db_path: Path, 
    retention_days: int = DEFAULT_SESSION_RETENTION_DAYS
) -> int:
    """
    Delete sessions older than retention period.
    
    Args:
        db_path: Path to the SQLite database file.
        retention_days: Number of days to keep sessions (default: 30).
    
    Returns:
        Number of sessions deleted.
    """
    cutoff_time = int(time.time()) - (retention_days * 86400)
    
    logger.info(f"Pruning sessions older than {retention_days} days...")
    
    try:
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute(
                "DELETE FROM sessions WHERE end_time < ?",
                (cutoff_time,)
            )
            await conn.commit()
            deleted = cursor.rowcount
        
        if deleted > 0:
            logger.info(f"Pruned {deleted} old sessions")
        else:
            logger.info("No sessions to prune")
        
        return deleted
    except Exception as e:
        if "no such table" in str(e):
            logger.info("Sessions table doesn't exist yet - skipping prune")
            return 0
        raise


async def prune_old_raw_events(
    db_path: Path,
    retention_days: int = 7
) -> int:
    """
    Delete raw_events older than retention period.
    
    These are legacy events that weren't aggregated into sessions.
    
    Args:
        db_path: Path to the SQLite database file.
        retention_days: Number of days to keep raw events (default: 7).
    
    Returns:
        Number of events deleted.
    """
    cutoff_time = int(time.time()) - (retention_days * 86400)
    
    logger.info(f"Pruning raw_events older than {retention_days} days...")
    
    try:
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute(
                "DELETE FROM raw_events WHERE unix_time < ?",
                (cutoff_time,)
            )
            await conn.commit()
            deleted = cursor.rowcount
        
        if deleted > 0:
            logger.info(f"Pruned {deleted} old raw_events")
        else:
            logger.info("No raw_events to prune")
        
        return deleted
    except Exception as e:
        if "no such table" in str(e):
            logger.info("raw_events table doesn't exist - skipping prune")
            return 0
        raise


async def cleanup_orphaned_screenshots(screenshots_dir: Path) -> int:
    """
    Delete screenshot files older than 1 hour that weren't cleaned up.
    
    Args:
        screenshots_dir: Path to screenshots directory.
    
    Returns:
        Number of files deleted.
    """
    if not screenshots_dir.exists():
        return 0
    
    cutoff_time = time.time() - 3600  # 1 hour ago
    deleted = 0
    
    for file in screenshots_dir.glob("*.png"):
        try:
            if file.stat().st_mtime < cutoff_time:
                file.unlink()
                deleted += 1
        except Exception as e:
            logger.debug(f"Could not delete {file}: {e}")
    
    if deleted > 0:
        logger.info(f"Cleaned up {deleted} orphaned screenshots")
    
    return deleted


async def get_database_stats(db_path: Path) -> dict:
    """
    Get current database statistics for monitoring.
    
    Returns:
        Dictionary with size and row counts.
    """
    stats = {
        'file_size_kb': 0,
        'sessions_count': 0,
        'raw_events_count': 0,
        'context_count': 0
    }
    
    if db_path.exists():
        stats['file_size_kb'] = db_path.stat().st_size / 1024
    
    try:
        async with aiosqlite.connect(db_path) as conn:
            # Sessions count
            cursor = await conn.execute("SELECT COUNT(*) FROM sessions")
            row = await cursor.fetchone()
            stats['sessions_count'] = row[0] if row else 0
            
            # Raw events count
            try:
                cursor = await conn.execute("SELECT COUNT(*) FROM raw_events")
                row = await cursor.fetchone()
                stats['raw_events_count'] = row[0] if row else 0
            except:
                pass
            
            # Context enrichment count
            try:
                cursor = await conn.execute("SELECT COUNT(*) FROM context_enrichment")
                row = await cursor.fetchone()
                stats['context_count'] = row[0] if row else 0
            except:
                pass
                
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
    
    return stats


async def run_full_maintenance(
    db_path: Path,
    screenshots_dir: Optional[Path] = None,
    session_retention_days: int = DEFAULT_SESSION_RETENTION_DAYS,
    raw_events_retention_days: int = 7
) -> dict:
    """
    Run full maintenance cycle.
    
    1. Prune old sessions
    2. Prune old raw_events
    3. Cleanup orphaned screenshots
    4. VACUUM database
    
    Args:
        db_path: Path to database.
        screenshots_dir: Path to screenshots directory.
        session_retention_days: Days to keep sessions.
        raw_events_retention_days: Days to keep raw_events.
    
    Returns:
        Dictionary with maintenance results.
    """
    logger.info("=" * 50)
    logger.info("Starting full database maintenance...")
    logger.info("=" * 50)
    
    results = {
        'sessions_pruned': 0,
        'raw_events_pruned': 0,
        'screenshots_cleaned': 0,
        'size_before_kb': 0,
        'size_after_kb': 0
    }
    
    # Get size before
    if db_path.exists():
        results['size_before_kb'] = db_path.stat().st_size / 1024
    
    # Prune sessions
    results['sessions_pruned'] = await prune_old_sessions(db_path, session_retention_days)
    
    # Prune raw_events
    results['raw_events_pruned'] = await prune_old_raw_events(db_path, raw_events_retention_days)
    
    # Cleanup screenshots
    if screenshots_dir:
        results['screenshots_cleaned'] = await cleanup_orphaned_screenshots(screenshots_dir)
    
    # VACUUM
    await vacuum_database(db_path)
    
    # Get size after
    if db_path.exists():
        results['size_after_kb'] = db_path.stat().st_size / 1024
    
    logger.info("=" * 50)
    logger.info(f"Maintenance complete. Saved {results['size_before_kb'] - results['size_after_kb']:.1f}KB")
    logger.info("=" * 50)
    
    return results


# CLI entry point
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    db_path = Path(".mnemosyne/activity.db")
    screenshots_dir = Path("screenshots")
    
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)
    
    asyncio.run(run_full_maintenance(db_path, screenshots_dir))
