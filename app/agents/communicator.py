"""
Agent Communication System
Handles inter-agent messaging via Redis Streams
"""
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import redis
from flask import current_app

logger = logging.getLogger(__name__)

class MessageType(Enum):
    """Types of messages that can be sent between agents"""
    RISK_ALERT = "risk_alert"
    ROUTE_RECOMMENDATION = "route_recommendation"
    PROCUREMENT_REQUEST = "procurement_request"
    APPROVAL_REQUEST = "approval_request"
    POLICY_CHECK = "policy_check"
    AUDIT_LOG = "audit_log"
    STATUS_UPDATE = "status_update"
    ERROR_REPORT = "error_report"

class AgentMessage:
    """Message object for inter-agent communication"""
    
    def __init__(self, message_type: MessageType, sender: str, recipient: str, 
                 data: Dict[str, Any], message_id: str = None):
        self.message_id = message_id or str(uuid.uuid4())
        self.message_type = message_type
        self.sender = sender
        self.recipient = recipient
        self.data = data
        self.timestamp = datetime.utcnow().isoformat()
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return {
            'message_id': self.message_id,
            'message_type': self.message_type.value if isinstance(self.message_type, MessageType) else self.message_type,
            'sender': self.sender,
            'recipient': self.recipient,
            'data': self.data,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentMessage':
        """Create message from dictionary"""
        message_type = data.get('message_type')
        if isinstance(message_type, str):
            # Convert string back to enum
            try:
                message_type = MessageType(message_type)
            except ValueError:
                message_type = MessageType.STATUS_UPDATE  # Default fallback
        
        return cls(
            message_type=message_type,
            sender=data.get('sender', ''),
            recipient=data.get('recipient', ''),
            data=data.get('data', {}),
            message_id=data.get('message_id')
        )

class AgentCommunicator:
    """Handles communication between agents using Redis Streams"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client or self._get_redis_client()
        self.streams = {
            'shipments.events': 'shipments.events',
            'shipments.optimize': 'shipments.optimize',
            'routes.updated': 'routes.updated',
            'alerts.created': 'alerts.created',
            'recommendations.created': 'recommendations.created',
            'approvals.requests': 'approvals.requests'
        }
        
    def _get_redis_client(self):
        """Get Redis client from Flask config"""
        try:
            return redis.Redis(
                host=current_app.config.get('REDIS_HOST', 'localhost'),
                port=current_app.config.get('REDIS_PORT', 6379),
                db=current_app.config.get('REDIS_DB', 0),
                decode_responses=True
            )
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            # Return a mock client for development
            return MockRedisClient()
    
    def publish_message(self, stream_name: str, data: Dict[str, Any]) -> str:
        """Publish a message to a Redis Stream"""
        try:
            message_id = str(uuid.uuid4())
            message_data = {
                'id': message_id,
                'timestamp': datetime.utcnow().isoformat(),
                'data': json.dumps(data)
            }
            
            # Add to Redis Stream
            stream_id = self.redis.xadd(stream_name, message_data)
            logger.info(f"Published message {message_id} to {stream_name}")
            return stream_id
            
        except Exception as e:
            logger.error(f"Failed to publish message to {stream_name}: {e}")
            return None
    
    def consume_messages(self, stream_name: str, consumer_group: str, 
                        consumer_name: str, count: int = 10) -> List[Dict]:
        """Consume messages from a Redis Stream"""
        try:
            # Ensure consumer group exists
            try:
                self.redis.xgroup_create(stream_name, consumer_group, '0', mkstream=True)
            except redis.exceptions.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise
            
            # Read messages
            messages = self.redis.xreadgroup(
                consumer_group, consumer_name,
                {stream_name: '>'},
                count=count, block=1000
            )
            
            processed_messages = []
            for stream, msgs in messages:
                for msg_id, fields in msgs:
                    try:
                        data = json.loads(fields.get('data', '{}'))
                        processed_messages.append({
                            'stream_id': msg_id,
                            'message_id': fields.get('id'),
                            'timestamp': fields.get('timestamp'),
                            'data': data
                        })
                        
                        # Acknowledge message
                        self.redis.xack(stream_name, consumer_group, msg_id)
                        
                    except Exception as e:
                        logger.error(f"Failed to process message {msg_id}: {e}")
            
            return processed_messages
            
        except Exception as e:
            logger.error(f"Failed to consume from {stream_name}: {e}")
            return []
    
    def publish_shipment_created(self, shipment_data: Dict) -> str:
        """Publish shipment created event"""
        return self.publish_message('shipments.events', {
            'event_type': 'shipment_created',
            'shipment_id': shipment_data.get('id'),
            'tracking_number': shipment_data.get('tracking_number'),
            'carrier': shipment_data.get('carrier'),
            'origin_port': shipment_data.get('origin_port'),
            'destination_port': shipment_data.get('destination_port'),
            'transport_mode': shipment_data.get('transport_mode'),
            'created_at': shipment_data.get('created_at')
        })
    
    def publish_route_optimization_request(self, shipment_id: int, reason: str = None) -> str:
        """Request route optimization for a shipment"""
        return self.publish_message('shipments.optimize', {
            'shipment_id': shipment_id,
            'reason': reason or 'manual_request',
            'requested_at': datetime.utcnow().isoformat()
        })
    
    def publish_recommendation_created(self, recommendation_data: Dict) -> str:
        """Publish recommendation created event"""
        return self.publish_message('recommendations.created', {
            'recommendation_id': recommendation_data.get('id'),
            'type': recommendation_data.get('type'),
            'subject_ref': recommendation_data.get('subject_ref'),
            'severity': recommendation_data.get('severity'),
            'confidence': recommendation_data.get('confidence'),
            'created_by': recommendation_data.get('created_by'),
            'created_at': recommendation_data.get('created_at')
        })
    
    def receive_messages(self, streams: List[str], consumer_group: str = "default", count: int = 10) -> List[Dict]:
        """Receive messages from specified streams"""
        try:
            messages = []
            for stream in streams:
                stream_messages = self.consume_messages(stream, consumer_group, "agent_consumer", count)
                messages.extend(stream_messages)
            return messages
        except Exception as e:
            logger.error(f"Failed to receive messages: {e}")
            return []

class MockRedisClient:
    """Mock Redis client for development/testing"""
    
    def __init__(self):
        self.streams = {}
        
    def xadd(self, stream_name, data):
        if stream_name not in self.streams:
            self.streams[stream_name] = []
        msg_id = f"{len(self.streams[stream_name])}-0"
        self.streams[stream_name].append((msg_id, data))
        return msg_id
    
    def xreadgroup(self, group, consumer, streams, count=10, block=1000):
        # Return empty for mock
        return []
    
    def xgroup_create(self, stream, group, id, mkstream=False):
        pass
    
    def xack(self, stream, group, *ids):
        pass
        """Consume messages from streams"""
        
        # Build stream dict for xreadgroup
        stream_dict = {stream: '>' for stream in streams}
        
        try:
            # Read messages
            messages = self.redis.xreadgroup(
                consumer_group,
                self.agent_name,
                stream_dict,
                count=count,
                block=block
            )
            
            result = []
            for stream_name, stream_messages in messages:
                for msg_id, data in stream_messages:
                    try:
                        # Deserialize message
                        message = self._deserialize_message(data)
                        
                        # Check if message is for this agent or broadcast
                        if message.target_agent is None or message.target_agent == self.agent_name:
                            result.append((msg_id, message))
                        else:
                            # Not for us, acknowledge and skip
                            self.acknowledge_message(consumer_group, stream_name, msg_id)
                            
                    except Exception as e:
                        logger.error(f"Error processing message {msg_id}: {e}")
                        # Send to DLQ
                        self._send_raw_to_dlq(stream_name, msg_id, data, str(e))
                        # Acknowledge to prevent reprocessing
                        self.acknowledge_message(consumer_group, stream_name, msg_id)
            
            return result
            
        except Exception as e:
            logger.error(f"Error consuming messages: {e}")
            return []
    
    def acknowledge_message(self, consumer_group: str, stream: str, message_id: str):
        """Acknowledge a processed message"""
        try:
            self.redis.xack(stream, consumer_group, message_id)
            logger.debug(f"Acknowledged message {message_id} in stream {stream}")
        except Exception as e:
            logger.error(f"Error acknowledging message: {e}")
    
    def get_pending_messages(self, consumer_group: str, stream: str) -> List[Dict]:
        """Get pending messages for a consumer"""
        try:
            # Get pending messages
            pending = self.redis.xpending_range(
                stream,
                consumer_group,
                '-',
                '+',
                count=100,
                consumername=self.agent_name
            )
            return pending
        except Exception as e:
            logger.error(f"Error getting pending messages: {e}")
            return []
    
    def claim_abandoned_messages(self, 
                               consumer_group: str,
                               stream: str,
                               min_idle_time: int = 300000):  # 5 minutes
        """Claim messages abandoned by other consumers"""
        try:
            # Get idle messages
            pending = self.redis.xpending_range(
                stream,
                consumer_group,
                '-',
                '+',
                count=10
            )
            
            message_ids = []
            for msg in pending:
                if msg['time_since_delivered'] > min_idle_time:
                    message_ids.append(msg['message_id'])
            
            if message_ids:
                # Claim messages
                claimed = self.redis.xclaim(
                    stream,
                    consumer_group,
                    self.agent_name,
                    min_idle_time,
                    message_ids
                )
                logger.info(f"Claimed {len(claimed)} abandoned messages")
                return claimed
            
            return []
            
        except Exception as e:
            logger.error(f"Error claiming abandoned messages: {e}")
            return []
    
    def _serialize_message(self, message: AgentMessage) -> Dict[str, str]:
        """Serialize message for Redis (all values must be strings)"""
        data = message.to_dict()
        # Convert all values to strings for Redis
        serialized = {}
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                serialized[key] = json.dumps(value)
            else:
                serialized[key] = str(value)
        return serialized
    
    def _deserialize_message(self, data: Dict[bytes, bytes]) -> AgentMessage:
        """Deserialize message from Redis"""
        # Decode bytes and parse JSON where needed
        decoded = {}
        for key, value in data.items():
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            value_str = value.decode('utf-8') if isinstance(value, bytes) else value
            
            # Parse JSON fields
            if key_str in ['payload', 'metadata']:
                decoded[key_str] = json.loads(value_str)
            else:
                decoded[key_str] = value_str
        
        return AgentMessage.from_dict(decoded)
    
    def _get_stream_for_message(self, message_type: MessageType) -> str:
        """Determine which stream to use for a message type"""
        mapping = {
            MessageType.RISK_ALERT: self.STREAMS['risk'],
            MessageType.ROUTE_RECOMMENDATION: self.STREAMS['shipments'],
            MessageType.PROCUREMENT_REQUEST: self.STREAMS['procurement'],
            MessageType.APPROVAL_REQUEST: self.STREAMS['approvals'],
            MessageType.POLICY_CHECK: self.STREAMS['orchestrator'],
            MessageType.AUDIT_LOG: self.STREAMS['orchestrator'],
            MessageType.STATUS_UPDATE: self.STREAMS['orchestrator'],
            MessageType.ERROR_REPORT: self.STREAMS['dlq']
        }
        return mapping.get(message_type, self.STREAMS['orchestrator'])
    
    def _publish_notification(self, message: AgentMessage):
        """Publish real-time notification via pub/sub"""
        try:
            channel = f"ui.broadcast.{message.type.value}"
            notification = {
                'message_id': message.id,
                'type': message.type.value,
                'source': message.source_agent,
                'timestamp': message.timestamp,
                'summary': message.payload.get('summary', 'New agent message')
            }
            self.redis.publish(channel, json.dumps(notification))
        except Exception as e:
            logger.error(f"Error publishing notification: {e}")
    
    def _send_to_dlq(self, message: AgentMessage, error: str):
        """Send failed message to dead letter queue"""
        try:
            dlq_entry = {
                'original_message': json.dumps(message.to_dict()),
                'error': error,
                'failed_at': datetime.utcnow().isoformat(),
                'agent': self.agent_name
            }
            self.redis.xadd(self.STREAMS['dlq'], dlq_entry)
            logger.warning(f"Sent message {message.id} to DLQ: {error}")
        except Exception as e:
            logger.error(f"Error sending to DLQ: {e}")
    
    def _send_raw_to_dlq(self, stream: str, msg_id: str, data: Dict, error: str):
        """Send raw message data to DLQ"""
        try:
            dlq_entry = {
                'original_stream': stream,
                'original_id': msg_id,
                'original_data': json.dumps({k.decode(): v.decode() for k, v in data.items()}),
                'error': error,
                'failed_at': datetime.utcnow().isoformat(),
                'agent': self.agent_name
            }
            self.redis.xadd(self.STREAMS['dlq'], dlq_entry)
        except Exception as e:
            logger.error(f"Error sending raw message to DLQ: {e}")
    
    def get_stream_info(self, stream: str) -> Dict:
        """Get information about a stream"""
        try:
            info = self.redis.xinfo_stream(stream)
            return info
        except Exception as e:
            logger.error(f"Error getting stream info: {e}")
            return {}
    
    def trim_stream(self, stream: str, maxlen: int = 10000):
        """Trim stream to prevent unbounded growth"""
        try:
            self.redis.xtrim(stream, maxlen=maxlen, approximate=True)
            logger.info(f"Trimmed stream {stream} to approximately {maxlen} messages")
        except Exception as e:
            logger.error(f"Error trimming stream: {e}")
