"""
Enhanced AI Assistant API Routes
Revolutionary upgrade with persistent memory, context awareness, and advanced agent orchestration
"""
import logging
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from flask import Blueprint, request, jsonify, session, current_app
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from app.agents.smart_assistant import SmartSupplyChainAssistant
from app.models_enhanced import ChatSession, ChatMessage, UserPersonalization
from app import db

logger = logging.getLogger(__name__)

# Create blueprint for enhanced assistant routes
assistant_bp = Blueprint('smart_assistant', __name__, url_prefix='/api/assistant')

@assistant_bp.route('/start-session', methods=['POST'])
# For testing only, removed login_required temporarily
def start_conversation_session():
    """Start a new enhanced conversation session with context"""
    try:
        data = request.get_json() or {}
        # For testing, allow anonymous sessions
        user_id = current_user.id if hasattr(current_user, 'id') else 1
        
        # Extract context from request
        context = {
            'page_info': data.get('page_info', {}),
            'current_data': data.get('current_data', {}),
            'user_preferences': data.get('user_preferences', {}),
            'session_metadata': {
                'ip_address': request.remote_addr,
                'user_agent': request.user_agent.string,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        # Initialize smart assistant
        assistant = SmartSupplyChainAssistant(user_id=user_id)
        
        # Start conversation with context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                assistant.start_conversation(
                    user_id=user_id,
                    context=context,
                    session_name=data.get('session_name')
                )
            )
        finally:
            loop.close()
        
        if 'error' in result:
            return jsonify({
                'success': False,
                'error': result['error'],
                'fallback_message': result.get('fallback_message', 'Unable to start conversation')
            }), 500
        
        return jsonify({
            'success': True,
            'session_id': result['session_id'],
            'welcome_message': result['welcome_message'],
            'context': result['context'],
            'user_preferences': result['user_preferences'],
            'capabilities': result['available_capabilities'],
            'metadata': {
                'model': 'granite-enhanced',
                'features': ['persistent_memory', 'context_awareness', 'agent_consultation'],
                'timestamp': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Error starting conversation session: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to start conversation session',
            'details': str(e)
        }), 500

@assistant_bp.route('/chat', methods=['POST'])
# For testing only, removed login_required temporarily
def enhanced_chat():
    """Enhanced chat endpoint with full AI capabilities"""
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({
                'success': False,
                'error': 'Message is required'
            }), 400
        
        message = data['message'].strip()
        if not message:
            return jsonify({
                'success': False,
                'error': 'Message cannot be empty'
            }), 400
        
        session_id = data.get('session_id')
        page_context = data.get('page_context', {})
        
        # Initialize smart assistant - for testing, allow anonymous sessions
        user_id = current_user.id if hasattr(current_user, 'id') else 1
        assistant = SmartSupplyChainAssistant(user_id=user_id)
        
        # Process message with full enhancement
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                assistant.process_message(
                    message=message,
                    session_id=session_id,
                    page_context=page_context
                )
            )
        finally:
            loop.close()
        
        if not result.get('success', False):
            return jsonify({
                'success': False,
                'error': result.get('error', 'Unknown processing error'),
                'fallback_response': 'I apologize, but I encountered an issue processing your request. Please try again or contact support if the problem persists.'
            }), 500
        
        # Format response for frontend
        response_data = {
            'success': True,
            'response': result['message'],
            'actions': result.get('actions', []),
            'context': result.get('context_update', {}),
            'agents_consulted': result.get('agent_consultations', []),
            'metadata': result.get('metadata', {}),
            'user_insights': result.get('user_insights', {}),
            'timestamp': datetime.now().isoformat()
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Enhanced chat error: {e}")
        return jsonify({
            'success': False,
            'error': 'Chat processing failed',
            'details': str(e),
            'fallback_response': 'I apologize, but I encountered a technical issue. Please try rephrasing your question or contact support.'
        }), 500

@assistant_bp.route('/sessions', methods=['GET'])
@login_required
def get_user_sessions():
    """Get user's chat sessions with metadata"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 50)
        
        sessions_query = ChatSession.query.filter_by(
            user_id=current_user.id,
            is_active=True
        ).order_by(ChatSession.updated_at.desc())
        
        sessions_paginated = sessions_query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        sessions_data = []
        for session in sessions_paginated.items:
            session_data = {
                'id': session.id,
                'name': session.session_name,
                'message_count': session.message_count,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'context_summary': session.context_data.get('summary', 'General conversation') if session.context_data else 'General conversation',
                'last_activity': session.updated_at.isoformat(),
                'topics': session.context_data.get('topics', []) if session.context_data else []
            }
            sessions_data.append(session_data)
        
        return jsonify({
            'success': True,
            'sessions': sessions_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': sessions_paginated.total,
                'pages': sessions_paginated.pages,
                'has_next': sessions_paginated.has_next,
                'has_prev': sessions_paginated.has_prev
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting user sessions: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve sessions'
        }), 500

@assistant_bp.route('/sessions/<session_id>/messages', methods=['GET'])
@login_required
def get_session_messages(session_id):
    """Get messages from a specific session"""
    try:
        # Verify session ownership
        session = ChatSession.query.filter_by(
            id=session_id,
            user_id=current_user.id
        ).first()
        
        if not session:
            return jsonify({
                'success': False,
                'error': 'Session not found'
            }), 404
        
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        
        messages_query = ChatMessage.query.filter_by(
            session_id=session_id
        ).order_by(ChatMessage.created_at.asc())
        
        messages_paginated = messages_query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        messages_data = []
        for message in messages_paginated.items:
            message_data = {
                'id': message.id,
                'user_message': message.user_message,
                'ai_response': message.ai_response,
                'intent_category': message.intent_category,
                'context_data': message.context_data,
                'created_at': message.created_at.isoformat(),
                'response_time_ms': message.response_time_ms,
                'agents_consulted': message.metadata.get('agents_consulted', []) if message.metadata else [],
                'tools_used': message.metadata.get('tools_used', []) if message.metadata else []
            }
            messages_data.append(message_data)
        
        return jsonify({
            'success': True,
            'session': {
                'id': session.id,
                'name': session.session_name,
                'created_at': session.created_at.isoformat()
            },
            'messages': messages_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': messages_paginated.total,
                'pages': messages_paginated.pages,
                'has_next': messages_paginated.has_next,
                'has_prev': messages_paginated.has_prev
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting session messages: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve messages'
        }), 500

@assistant_bp.route('/sessions/<session_id>', methods=['DELETE'])
@login_required
def delete_session(session_id):
    """Delete a chat session"""
    try:
        session = ChatSession.query.filter_by(
            id=session_id,
            user_id=current_user.id
        ).first()
        
        if not session:
            return jsonify({
                'success': False,
                'error': 'Session not found'
            }), 404
        
        # Soft delete by marking as inactive
        session.is_active = False
        session.updated_at = datetime.now()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Session deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to delete session'
        }), 500

@assistant_bp.route('/personalization', methods=['GET'])
def get_user_personalization():
    """Get user's personalization settings.

    Development convenience: if user is not authenticated, return a default
    personalization payload instead of redirecting to login (which caused the
    frontend to attempt to JSON‑parse an HTML login page producing
    "Unexpected token '<'" errors). This keeps the enhanced assistant UI fully
    functional in anonymous/dev mode while preserving per‑user settings when
    authentication is enabled.
    """
    try:
        # If authenticated, load or create real record
        if getattr(current_user, 'is_authenticated', False):
            personalization = UserPersonalization.query.filter_by(
                user_id=current_user.id
            ).first()

            if not personalization:
                personalization = UserPersonalization(
                    user_id=current_user.id,
                    preferred_response_style='balanced',
                    allow_learning=True
                )
                db.session.add(personalization)
                db.session.commit()
        else:
            # Anonymous/default personalization (not persisted)
            class _Tmp:  # lightweight stand‑in object
                preferred_response_style = 'balanced'
                allow_learning = True
                frequently_asked_topics = []
                interaction_patterns = {}
                preferences = {}
                from datetime import datetime as _dt
                updated_at = _dt.utcnow()
            personalization = _Tmp()

        return jsonify({
            'success': True,
            'personalization': {
                'preferred_response_style': personalization.preferred_response_style,
                'allow_learning': personalization.allow_learning,
                'frequently_asked_topics': personalization.frequently_asked_topics or [],
                'interaction_patterns': personalization.interaction_patterns or {},
                'preferences': personalization.preferences or {},
                'updated_at': personalization.updated_at.isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Error getting personalization: {e}")
        return jsonify({'success': False,'error': 'Failed to retrieve personalization settings'}), 500

@assistant_bp.route('/personalization', methods=['PUT'])
@login_required
def update_user_personalization():
    """Update user's personalization settings"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        personalization = UserPersonalization.query.filter_by(
            user_id=current_user.id
        ).first()
        
        if not personalization:
            personalization = UserPersonalization(user_id=current_user.id)
            db.session.add(personalization)
        
        # Update allowed fields
        if 'preferred_response_style' in data:
            if data['preferred_response_style'] in ['brief', 'balanced', 'detailed']:
                personalization.preferred_response_style = data['preferred_response_style']
        
        if 'allow_learning' in data:
            personalization.allow_learning = bool(data['allow_learning'])
        
        if 'preferences' in data:
            current_prefs = personalization.preferences or {}
            current_prefs.update(data['preferences'])
            personalization.preferences = current_prefs
        
        personalization.updated_at = datetime.now()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Personalization updated successfully',
            'personalization': {
                'preferred_response_style': personalization.preferred_response_style,
                'allow_learning': personalization.allow_learning,
                'preferences': personalization.preferences or {}
            }
        })
        
    except Exception as e:
        logger.error(f"Error updating personalization: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to update personalization settings'
        }), 500

@assistant_bp.route('/analytics', methods=['GET'])
@login_required
def get_user_analytics():
    """Get user's AI assistant usage analytics"""
    try:
        # Get session statistics
        session_stats = db.session.query(
            db.func.count(ChatSession.id).label('total_sessions'),
            db.func.sum(ChatSession.message_count).label('total_messages'),
            db.func.max(ChatSession.updated_at).label('last_activity')
        ).filter_by(user_id=current_user.id, is_active=True).first()
        
        # Get recent activity
        recent_sessions = ChatSession.query.filter_by(
            user_id=current_user.id,
            is_active=True
        ).order_by(ChatSession.updated_at.desc()).limit(5).all()
        
        # Get personalization insights
        personalization = UserPersonalization.query.filter_by(
            user_id=current_user.id
        ).first()
        
        analytics_data = {
            'usage_statistics': {
                'total_sessions': session_stats.total_sessions or 0,
                'total_messages': session_stats.total_messages or 0,
                'last_activity': session_stats.last_activity.isoformat() if session_stats.last_activity else None,
                'avg_messages_per_session': round((session_stats.total_messages or 0) / max(session_stats.total_sessions or 1, 1), 2)
            },
            'recent_activity': [
                {
                    'session_name': session.session_name,
                    'message_count': session.message_count,
                    'updated_at': session.updated_at.isoformat(),
                    'topics': session.context_data.get('topics', []) if session.context_data else []
                }
                for session in recent_sessions
            ],
            'personalization_insights': {
                'frequent_topics': personalization.frequently_asked_topics[:5] if personalization and personalization.frequently_asked_topics else [],
                'preferred_style': personalization.preferred_response_style if personalization else 'balanced',
                'learning_enabled': personalization.allow_learning if personalization else True,
                'interaction_patterns': personalization.interaction_patterns if personalization else {}
            }
        }
        
        return jsonify({
            'success': True,
            'analytics': analytics_data
        })
        
    except Exception as e:
        logger.error(f"Error getting user analytics: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve analytics'
        }), 500

@assistant_bp.route('/capabilities', methods=['GET'])
def get_assistant_capabilities():
    """Get current assistant capabilities and features"""
    try:
        capabilities = {
            'features': {
                'persistent_memory': True,
                'context_awareness': True,
                'agent_consultation': True,
                'personalization': True,
                'multi_modal_analysis': True,
                'enterprise_security': True
            },
            'agents': {
                'risk_predictor': {
                    'description': 'Advanced risk assessment and threat prediction',
                    'specialties': ['weather_analysis', 'geopolitical_assessment', 'supplier_risk', 'route_safety']
                },
                'route_optimizer': {
                    'description': 'Intelligent route optimization and logistics planning',
                    'specialties': ['route_analysis', 'cost_optimization', 'eta_prediction', 'multimodal_planning']
                },
                'procurement_agent': {
                    'description': 'Strategic procurement and supplier management',
                    'specialties': ['supplier_evaluation', 'po_generation', 'inventory_management', 'contract_analysis']
                },
                'orchestrator': {
                    'description': 'Workflow coordination and policy enforcement',
                    'specialties': ['workflow_coordination', 'policy_enforcement', 'approval_management', 'compliance']
                }
            },
            'data_access': {
                'shipments': ['tracking', 'routes', 'status', 'performance'],
                'procurement': ['suppliers', 'purchase_orders', 'contracts', 'inventory'],
                'risk': ['assessments', 'alerts', 'threats', 'mitigation'],
                'analytics': ['reports', 'trends', 'forecasting', 'kpis']
            },
            'response_styles': ['brief', 'balanced', 'detailed'],
            'languages': ['english'],
            'model_info': {
                'primary': 'IBM watsonx.ai Granite',
                'fallback': 'Enhanced rule-based system',
                'version': '2.0-enterprise'
            }
        }
        
        return jsonify({
            'success': True,
            'capabilities': capabilities,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting capabilities: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve capabilities'
        }), 500

# Error handlers
@assistant_bp.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint not found'
    }), 404

@assistant_bp.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        'success': False,
        'error': 'Method not allowed'
    }), 405

@assistant_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500
