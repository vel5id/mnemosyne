"""
Mnemosyne Core V5.0 - Stats Repository

Handles analytics queries: basic stats, detailed breakdowns for dashboard.

Usage:
    repo = StatsRepository(db_path)
    await repo.connect()
    stats = await repo.get_stats()
"""

import logging
from typing import Dict, Any

from core.dal.base import BaseRepository

logger = logging.getLogger(__name__)


class StatsRepository(BaseRepository):
    """
    Repository for analytics and statistics queries.
    
    Responsibilities:
        - Basic event counts (total, pending, enriched)
        - Detailed dashboard analytics (LLM, VLM, screenshots)
    """

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get basic database statistics.
        
        Returns:
            Dict with total_events, pending_events, enriched_events.
        
        Raises:
            RuntimeError: If connection not established.
        """
        self._ensure_connected()
        
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

    async def get_detailed_analytics(self) -> Dict[str, int]:
        """
        Get detailed analytics for dashboard breakdown.
        
        Returns:
            Dict with telemetry_events, llm_events, vlm_events, screenshot_events.
            Returns empty dict on error (Axiom: explicit failure, but safe for dashboard).
        """
        self._ensure_connected()
        
        async with self._lock:
            stats: Dict[str, int] = {}
            
            try:
                # Total telemetry
                cursor = await self._connection.execute(
                    "SELECT COUNT(*) FROM raw_events"
                )
                row = await cursor.fetchone()
                stats["telemetry_events"] = row[0] if row else 0
                
            except Exception as e:
                logger.warning(f"Error getting telemetry count: {e}")
                stats["telemetry_events"] = 0
            
            # LLM enriched (Axiom: separate try blocks for isolation)
            try:
                cursor = await self._connection.execute(
                    "SELECT COUNT(*) FROM context_enrichment "
                    "WHERE user_intent IS NOT NULL AND user_intent != ''"
                )
                row = await cursor.fetchone()
                stats["llm_events"] = row[0] if row else 0
            except Exception as e:
                logger.warning(f"Error getting LLM count: {e}")
                stats["llm_events"] = 0
            
            # Screenshots
            try:
                cursor = await self._connection.execute(
                    "SELECT COUNT(*) FROM raw_events "
                    "WHERE screenshot_path IS NOT NULL AND screenshot_path != ''"
                )
                row = await cursor.fetchone()
                stats["screenshot_events"] = row[0] if row else 0
            except Exception as e:
                logger.warning(f"Error getting screenshot count: {e}")
                stats["screenshot_events"] = 0
            
            # VLM analyzed
            try:
                cursor = await self._connection.execute(
                    "SELECT COUNT(*) FROM context_enrichment "
                    "WHERE vlm_description IS NOT NULL AND vlm_description != ''"
                )
                row = await cursor.fetchone()
                stats["vlm_events"] = row[0] if row else 0
            except Exception as e:
                logger.warning(f"Error getting VLM count: {e}")
                stats["vlm_events"] = 0
            
            return stats
