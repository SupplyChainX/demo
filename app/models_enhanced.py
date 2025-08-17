# Enhanced models for persistent AI assistant with memory and context
from datetime import datetime, timedelta
from app.extensions import db
from sqlalchemy import JSON, Text, DateTime, Integer, String, Boolean, Float, ForeignKey
import uuid as uuid_lib

class ChatSession(db.Model):
    """Persistent chat sessions with user context and memory"""
    __tablename__ = "chat_sessions"
    
    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    user_id = db.Column(Integer, db.ForeignKey('users.id'), nullable=False)
    session_name = db.Column(String(255), nullable=True)
    
    # Session context
    context_data = db.Column(JSON, default={})  # Current page, shipment, supplier data
    user_preferences = db.Column(JSON, default={})  # AI behavior preferences
    
    # Memory and state
    conversation_summary = db.Column(Text, nullable=True)  # AI-generated summary
    key_entities = db.Column(JSON, default=[])  # Important entities discussed
    active_topics = db.Column(JSON, default=[])  # Current conversation topics
    
    # Session metadata
    created_at = db.Column(DateTime, default=datetime.utcnow)
    last_activity = db.Column(DateTime, default=datetime.utcnow)
    updated_at = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # Add missing field
    is_active = db.Column(Boolean, default=True)
    message_count = db.Column(Integer, default=0)
    
    # Relationships
    user = db.relationship("User", backref=db.backref("chat_sessions", lazy=True))
    messages = db.relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(db.Model):
    """Individual chat messages with rich metadata"""
    __tablename__ = "chat_messages"
    
    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    session_id = db.Column(String(36), db.ForeignKey('chat_sessions.id'), nullable=False)
    user_id = db.Column(Integer, db.ForeignKey('users.id'), nullable=True)  # Nullable as assistant messages don't have a user
    
    # Message content
    sender = db.Column(String(20), nullable=False)  # 'user' or 'assistant'
    message = db.Column(Text, nullable=False)
    agent_name = db.Column(String(50), nullable=True)  # Name of the AI agent (for test compatibility)
    
    # AI analysis
    intent_category = db.Column(String(50), nullable=True)  # shipments, procurement, risk, etc.
    intent_action = db.Column(String(50), nullable=True)  # tracking, analysis, etc.
    extracted_entities = db.Column(JSON, default=[])  # Shipment IDs, supplier names, etc.
    confidence_score = db.Column(Float, default=0.0)
    
    # Context and tools
    page_context = db.Column(JSON, default={})  # What page user was on
    tools_used = db.Column(JSON, default=[])  # What tools AI used
    agents_consulted = db.Column(JSON, default=[])  # Which agents were involved
    
    # Response metadata
    response_time_ms = db.Column(Integer, nullable=True)
    granite_model_used = db.Column(String(100), nullable=True)
    suggested_actions = db.Column(JSON, default=[])
    
    # Timestamps
    created_at = db.Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    session = db.relationship("ChatSession", back_populates="messages")
    user = db.relationship("User", back_populates="chat_messages")

class UserPersonalization(db.Model):
    """User-specific AI personalization and learning"""
    __tablename__ = "user_personalization"
    
    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    
    # Behavioral patterns
    preferred_response_style = db.Column(String(20), default='balanced')  # brief, detailed, balanced
    frequently_asked_topics = db.Column(JSON, default=[])
    preferred_data_views = db.Column(JSON, default=[])  # dashboards, reports user prefers
    
    # Learning data
    interaction_patterns = db.Column(JSON, default={})  # When/how user interacts
    success_feedback = db.Column(JSON, default={})  # Positive/negative feedback
    custom_shortcuts = db.Column(JSON, default={})  # User-defined quick actions
    preferences = db.Column(JSON, default={})
    
    # Privacy and security
    data_retention_days = db.Column(Integer, default=90)
    allow_learning = db.Column(Boolean, default=True)
    share_analytics = db.Column(Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(DateTime, default=datetime.utcnow)
    updated_at = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship("User", backref=db.backref("personalization", uselist=False))

class AuditLogEnhanced(db.Model):
    """Enhanced audit logging for AI interactions"""
    __tablename__ = "audit_log_enhanced"
    
    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, db.ForeignKey('users.id'), nullable=False)
    session_id = db.Column(String(36), db.ForeignKey('chat_sessions.id'), nullable=True)
    
    # Action details
    action_type = db.Column(String(50), nullable=False)  # ai_query, data_access, etc.
    resource_type = db.Column(String(50), nullable=True)  # shipment, supplier, etc.
    resource_id = db.Column(String(100), nullable=True)
    
    # Request details
    user_query = db.Column(Text, nullable=True)
    ai_response_summary = db.Column(Text, nullable=True)
    tools_accessed = db.Column(JSON, default=[])
    
    # Security and compliance
    ip_address = db.Column(String(45), nullable=True)
    user_agent = db.Column(Text, nullable=True)
    risk_score = db.Column(Float, default=0.0)
    compliance_flags = db.Column(JSON, default=[])
    
    # Performance
    response_time_ms = db.Column(Integer, nullable=True)
    tokens_used = db.Column(Integer, nullable=True)
    
    # Timestamps
    timestamp = db.Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship("User", backref=db.backref("enhanced_audit_logs", lazy=True))
    session = db.relationship("ChatSession", backref=db.backref("audit_logs", lazy=True))
