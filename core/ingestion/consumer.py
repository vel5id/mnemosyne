from collections import defaultdict
from typing import List, Dict, Any, Tuple, Optional
import logging
from core.dal.redis_provider import RedisProvider

logger = logging.getLogger(__name__)

class RedisConsumer:
    """
    Consumes events from Redis Stream and groups them for processing.
    Replaces the SQL GROUP BY logic in the hot path.
    """
    def __init__(self, redis_provider: RedisProvider, stream_key: str = "mnemosyne:events"):
        self.redis = redis_provider
        self.stream_key = stream_key
        self.group_name = "mnemosyne_brain_group"
        self.consumer_name = "brain_worker_1" # In Docker, use hostname
        
        # Ensure group exists on startup
        self.redis.ensure_group(self.stream_key, self.group_name)

    def fetch_and_group(self, batch_size: int = 500) -> List[Dict[str, Any]]:
        """
        Fetches events from Redis and groups them by window.
        Returns a list of groups ready for Brain processing.
        """
        # Read raw events
        raw_events = self.redis.read_group(
            self.stream_key, 
            self.group_name, 
            self.consumer_name, 
            count=batch_size,
            block=2000 # 2s blocking wait
        )
        
        # DEBUG: Log what we received
        logger.info(f"Redis read_group returned {len(raw_events)} events from stream '{self.stream_key}'")
        
        if not raw_events:
            return []

        # Group events by (process, window)
        # This creates 'sessions' of activity in memory
        groups = defaultdict(list)
        for event in raw_events:
            # Handle potential missing keys gracefully
            proc = event.get('process_name', 'unknown')
            win = event.get('window_title', 'unknown')
            key = (proc, win)
            groups[key].append(event)
            
        # Format groups to match the structure Brain expects
        result_groups = []
        for (proc, win), events in groups.items():
            try:
                # Calculate aggregates (mimicking SQL)
                first_seen = min(int(e.get('unix_time', 0)) for e in events)
                last_seen = max(int(e.get('unix_time', 0)) for e in events)
                
                total_intensity = sum(float(e.get('intensity', 0)) for e in events)
                avg_intensity = total_intensity / len(events) if events else 0
                
                # Collect Redis IDs for ACKing
                redis_ids = [e['_redis_id'] for e in events]
                
                result_groups.append({
                    "process_name": proc,
                    "window_title": win,
                    "event_count": len(events),
                    "first_seen": first_seen,
                    "last_seen": last_seen,
                    "avg_intensity": avg_intensity,
                    "screenshot_path": None, # Future: get from message if available
                    "redis_ids": redis_ids   # Crucial for ACK
                })
            except Exception as e:
                logger.error(f"Error processing group {proc}/{win}: {e}")
                continue
            
        # Sort by event count (focus on most active windows first)
        result_groups.sort(key=lambda x: x['event_count'], reverse=True)
            
        return result_groups

    def ack_groups(self, groups: List[Dict[str, Any]]):
        """ACKs all messages in the processed groups."""
        all_ids = []
        for g in groups:
            if 'redis_ids' in g:
                all_ids.extend(g['redis_ids'])
        
        if all_ids:
            # Batch ACK
            self.redis.ack(self.stream_key, self.group_name, all_ids)
            logger.debug(f"ACKed {len(all_ids)} messages in Redis")
