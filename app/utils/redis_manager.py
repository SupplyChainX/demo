"""
Redis Manager for SupplyChainX
Handles Redis connections, caching, and event streaming
"""
import redis
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from flask import current_app

logger = logging.getLogger(__name__)

class RedisManager:
    """Centralized Redis management for caching and event streaming."""
    
    def __init__(self, app=None):
        self.redis_client = None
        self.streams = {
            'alerts': 'alerts:stream',
            'recommendations': 'recommendations:stream',
            'approvals': 'approvals:stream',
            'shipments': 'shipments:stream',
            'notifications': 'notifications:stream'
        }
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize Redis with Flask app."""
        try:
            redis_url = app.config.get('REDIS_URL', 'redis://localhost:6379/0')
            
            # Parse Redis URL and create connection
            self.redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # Test connection
            self.redis_client.ping()
            logger.info("Redis connection established successfully")
            
            # Initialize streams if they don't exist
            self._initialize_streams()
            
        except redis.ConnectionError as e:
            logger.warning(f"Redis connection failed: {e}")
            self.redis_client = None
        except Exception as e:
            logger.error(f"Redis initialization error: {e}")
            self.redis_client = None
    
    def _initialize_streams(self):
        """Initialize Redis streams if they don't exist."""
        if not self.redis_client:
            return
            
        try:
            for stream_name in self.streams.values():
                # Check if stream exists, create with dummy message if not
                try:
                    self.redis_client.xinfo_stream(stream_name)
                except redis.ResponseError:
                    # Stream doesn't exist, create it
                    self.redis_client.xadd(stream_name, {'init': 'true'})
                    logger.info(f"Created Redis stream: {stream_name}")
        except Exception as e:
            logger.error(f"Error initializing streams: {e}")
    
    def is_available(self) -> bool:
        """Check if Redis is available."""
        if not self.redis_client:
            return False
        try:
            self.redis_client.ping()
            return True
        except:
            return False
    
    # Cache Operations
    def set_key(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """Set a key-value pair with optional expiration."""
        if not self.is_available():
            return False
        try:
            return self.redis_client.set(key, value, ex=ex)
        except Exception as e:
            logger.error(f"Error setting key {key}: {e}")
            return False
    
    def get_key(self, key: str) -> Optional[str]:
        """Get value by key."""
        if not self.is_available():
            return None
        try:
            return self.redis_client.get(key)
        except Exception as e:
            logger.error(f"Error getting key {key}: {e}")
            return None
    
    def delete_key(self, key: str) -> bool:
        """Delete a key."""
        if not self.is_available():
            return False
        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            logger.error(f"Error deleting key {key}: {e}")
            return False
    
    def set_hash(self, name: str, mapping: Dict[str, Any]) -> bool:
        """Set hash fields."""
        if not self.is_available():
            return False
        try:
            return self.redis_client.hset(name, mapping=mapping)
        except Exception as e:
            logger.error(f"Error setting hash {name}: {e}")
            return False
    
    def get_hash(self, name: str) -> Dict[str, str]:
        """Get all hash fields."""
        if not self.is_available():
            return {}
        try:
            return self.redis_client.hgetall(name)
        except Exception as e:
            logger.error(f"Error getting hash {name}: {e}")
            return {}
    
    # Event Streaming
    def publish_event(self, stream_key: str, event_data: Dict[str, Any]) -> Optional[str]:
        """Publish event to Redis stream."""
        if not self.is_available():
            return None
        
        try:
            stream_name = self.streams.get(stream_key, stream_key)
            
            # Add timestamp if not present
            if 'timestamp' not in event_data:
                event_data['timestamp'] = datetime.utcnow().isoformat()
            
            # Convert all values to strings for Redis
            string_data = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) 
                          for k, v in event_data.items()}
            
            message_id = self.redis_client.xadd(stream_name, string_data)
            logger.debug(f"Published event to {stream_name}: {message_id}")
            return message_id
            
        except Exception as e:
            logger.error(f"Error publishing event to {stream_key}: {e}")
            return None
    
    def read_events(self, stream_key: str, last_id: str = '0', count: int = 100) -> List[Dict]:
        """Read events from Redis stream."""
        if not self.is_available():
            return []
        
        try:
            stream_name = self.streams.get(stream_key, stream_key)
            events = self.redis_client.xread({stream_name: last_id}, count=count)
            
            result = []
            for stream, messages in events:
                for message_id, fields in messages:
                    event = {'id': message_id}
                    for field, value in fields.items():
                        try:
                            # Try to parse JSON, fallback to string
                            event[field] = json.loads(value)
                        except:
                            event[field] = value
                    result.append(event)
            
            return result
            
        except Exception as e:
            logger.error(f"Error reading events from {stream_key}: {e}")
            return []
    
    def get_stream_info(self, stream_key: str) -> Dict[str, Any]:
        """Get information about a Redis stream."""
        if not self.is_available():
            return {}
        
        try:
            stream_name = self.streams.get(stream_key, stream_key)
            info = self.redis_client.xinfo_stream(stream_name)
            return {
                'length': info.get('length', 0),
                'first_entry': info.get('first-entry'),
                'last_entry': info.get('last-entry'),
                'groups': info.get('groups', 0)
            }
        except Exception as e:
            logger.error(f"Error getting stream info for {stream_key}: {e}")
            return {}
    
    # Utility Methods
    def cache_json(self, key: str, data: Any, ttl: int = 3600) -> bool:
        """Cache JSON data with TTL."""
        try:
            json_str = json.dumps(data, default=str)
            return self.set_key(key, json_str, ex=ttl)
        except Exception as e:
            logger.error(f"Error caching JSON for key {key}: {e}")
            return False
    
    def get_cached_json(self, key: str) -> Optional[Any]:
        """Get cached JSON data."""
        try:
            json_str = self.get_key(key)
            if json_str:
                return json.loads(json_str)
            return None
        except Exception as e:
            logger.error(f"Error getting cached JSON for key {key}: {e}")
            return None
    
    def increment_counter(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a counter."""
        if not self.is_available():
            return None
        try:
            return self.redis_client.incr(key, amount)
        except Exception as e:
            logger.error(f"Error incrementing counter {key}: {e}")
            return None
    
    def set_expiry(self, key: str, seconds: int) -> bool:
        """Set expiry for a key."""
        if not self.is_available():
            return False
        try:
            return self.redis_client.expire(key, seconds)
        except Exception as e:
            logger.error(f"Error setting expiry for key {key}: {e}")
            return False
    
    def pubsub(self):
        """Get Redis pubsub client."""
        if not self.is_available():
            return None
        try:
            return self.redis_client.pubsub()
        except Exception as e:
            logger.error(f"Error getting pubsub client: {e}")
            return None

# Global instance
redis_manager = RedisManager()

def init_redis(app):
    """Initialize Redis with Flask app."""
    redis_manager.init_app(app)
    return redis_manager
