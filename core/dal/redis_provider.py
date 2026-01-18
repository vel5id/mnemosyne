import redis
import logging
import time
from typing import List, Dict, Optional, Any, Tuple

logger = logging.getLogger(__name__)

class RedisProvider:
    """
    Provider for Redis operations, specifically Stream consumption.
    Used in Mnemosyne v4.0 (Hyper-RAM) architecture.
    """
    def __init__(self, host: str, port: int, db: int = 0):
        self.host = host
        self.port = port
        self.db = db
        self.client: Optional[redis.Redis] = None

    def connect(self) -> bool:
        try:
            self.client = redis.Redis(
                host=self.host, 
                port=self.port, 
                db=self.db, 
                decode_responses=True # Decode strings automatically
            )
            self.client.ping()
            logger.info(f"Connected to Redis at {self.host}:{self.port}")
            return True
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.client = None
            return False

    def ensure_group(self, stream_key: str, group_name: str) -> None:
        """Ensures that the consumer group exists."""
        if not self.client: return
        try:
            # mkstream=True creates the stream if it doesn't exist
            self.client.xgroup_create(stream_key, group_name, id='0', mkstream=True)
            logger.info(f"Created consumer group '{group_name}' for stream '{stream_key}'")
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                pass # Group already exists
            else:
                logger.error(f"Error creating consumer group: {e}")

    def read_group(self, stream_key: str, group_name: str, consumer_name: str, count: int = 100, block: int = 2000) -> List[Dict[str, Any]]:
        """Reads messages from the stream using consumer group.
        
        First attempts to read pending messages (previously delivered but not ACKed),
        then reads new messages if no pending ones exist.
        """
        if not self.client: return []
        
        events = []
        
        try:
            # Step 1: Try to read PENDING messages first (ID = '0')
            # These are messages that were delivered but not ACKed
            streams = self.client.xreadgroup(
                groupname=group_name,
                consumername=consumer_name,
                streams={stream_key: '0'},  # '0' = pending messages for this consumer
                count=count,
                block=0  # Don't block for pending, check immediately
            )
            
            if streams:
                for stream, messages in streams:
                    for message_id, data in messages:
                        data['_redis_id'] = message_id 
                        events.append(data)
                        
            # If we got pending messages, return them
            if events:
                logger.debug(f"Retrieved {len(events)} pending messages")
                return events
            
            # Step 2: No pending messages, read NEW messages (ID = '>')
            streams = self.client.xreadgroup(
                groupname=group_name,
                consumername=consumer_name,
                streams={stream_key: '>'},  # '>' = new messages never delivered
                count=count,
                block=block
            )
            
            if streams:
                for stream, messages in streams:
                    for message_id, data in messages:
                        data['_redis_id'] = message_id 
                        events.append(data)
            
            return events
            
        except Exception as e:
            logger.error(f"Error reading from Redis stream: {e}")
            return []

    def ack(self, stream_key: str, group_name: str, message_ids: List[str]) -> None:
        """Acknowledges processed messages."""
        if not self.client or not message_ids: return
        try:
            self.client.xack(stream_key, group_name, *message_ids)
        except Exception as e:
            logger.error(f"Error ACKing messages: {e}")

    def close(self):
        if self.client:
            self.client.close()
