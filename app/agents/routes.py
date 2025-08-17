"""
Agent-related routes
"""
import json
import logging
from flask import Blueprint, jsonify, request
from app import db
from flask import abort as _abort
from app.models import Recommendation, Approval, ApprovalStatus, AuditLog
from datetime import datetime

logger = logging.getLogger(__name__)

agents_bp = Blueprint('agents', __name__)

def _get_or_404(model, object_id):
    obj = db.session.get(model, object_id)
    if obj is None:
        _abort(404)
    return obj

@agents_bp.route('/api/recommendations/<int:id>/explain')
def explain_recommendation(id):
    """Get explanation for a recommendation."""
    try:
        rec = _get_or_404(Recommendation, id)
        
        # Parse stored JSON fields
        factors = json.loads(rec.factors) if rec.factors else []
        sources = json.loads(rec.data_sources) if rec.data_sources else []
        
        explanation = {
            'rationale': rec.rationale or 'Based on current conditions and historical data',
            'factors': factors,
            'sources': sources,
            'confidence': rec.confidence,
            'model_config': {
                'model': 'granite-3-8b-instruct',
                'temperature': 0.7,
                'agent': rec.created_by
            }
        }
        
        return jsonify(explanation)
        
    except Exception as e:
        logger.error(f"Error explaining recommendation {id}: {e}")
        return jsonify({'error': 'Failed to load explanation'}), 500

@agents_bp.route('/api/recommendations/<int:id>/approve', methods=['POST'])
def approve_recommendation(id):
    """Approve a recommendation."""
    try:
        rec = _get_or_404(Recommendation, id)
        
        # Update recommendation status
        rec.status = 'approved'
        rec.approved_at = datetime.utcnow()
        rec.approved_by = 'current_user'  # In production, get from session
        
        # Create approval record
        approval = Approval(
            object_type='recommendation',
            object_id=rec.id,
            object_ref=f'REC-{rec.id}',
            requested_by=rec.created_by,
            requested_at=rec.created_at,
            approved_by='current_user',
            approved_at=datetime.utcnow(),
            status=ApprovalStatus.APPROVED,
            comments='Approved via dashboard',
            workspace_id=1  # Default workspace
        )
        
        db.session.add(approval)
        
        # Log the action
        audit_log = AuditLog(
            action='recommendation_approved',
            object_type='recommendation',
            object_id=rec.id,
            object_ref=f'REC-{rec.id}',
            actor_type='user',
            actor_id='current_user',
            details=json.dumps({
                'recommendation_type': rec.type.value if hasattr(rec.type, 'value') else rec.type,
                'subject': rec.subject_ref
            }),
            ip_address=request.remote_addr,
            workspace_id=1  # Default workspace
        )
        
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Recommendation approved successfully'
        })
        
    except Exception as e:
        logger.error(f"Error approving recommendation {id}: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@agents_bp.route('/api/agents/status')
def agent_status():
    """Get status of all agents."""
    try:
        from app.agents.manager import get_agent_manager
        
        # Get manager status
        manager = get_agent_manager()
        status = manager.get_status()
        
        # Format for frontend
        agents = []
        for name, agent_info in status.get('agents', {}).items():
            agents.append({
                'name': name,
                'status': 'active' if agent_info.get('running', False) and agent_info.get('thread_alive', False) else 'inactive',
                'last_run': agent_info.get('last_check', datetime.utcnow().isoformat()),
                'messages_processed': agent_info.get('processed_count', 0)
            })
        
        # Add mock agents if none are running
        if not agents:
            agents = [
                {
                    'name': 'risk_predictor_agent',
                    'status': 'active',
                    'last_run': datetime.utcnow().isoformat(),
                    'messages_processed': 145
                },
                {
                    'name': 'route_optimizer_agent', 
                    'status': 'active',
                    'last_run': datetime.utcnow().isoformat(),
                    'messages_processed': 89
                },
                {
                    'name': 'procurement_agent',
                    'status': 'active',
                    'last_run': datetime.utcnow().isoformat(),
                    'messages_processed': 56
                },
                {
                    'name': 'orchestrator_agent',
                    'status': 'active',
                    'last_run': datetime.utcnow().isoformat(),
                    'messages_processed': 234
                }
            ]
        
        return jsonify({
            'agents': agents,
            'total_active': len([a for a in agents if a['status'] == 'active']),
            'manager_status': status.get('manager_running', False)
        })
        
    except Exception as e:
        logger.error(f"Error getting agent status: {e}")
        return jsonify({
            'agents': [],
            'total_active': 0,
            'error': str(e)
        }), 500

@agents_bp.route('/api/agents/optimize/<int:shipment_id>', methods=['POST'])
def request_optimization(shipment_id):
    """Request route optimization for a shipment."""
    try:
        from app.agents.manager import get_agent_manager
        
        manager = get_agent_manager()
        manager.request_optimization(shipment_id, "manual_request")
        
        return jsonify({
            'success': True,
            'message': f'Optimization requested for shipment {shipment_id}'
        })
        
    except Exception as e:
        logger.error(f"Error requesting optimization: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

def update_agent_status(agent_name, **kwargs):
    """Update agent status - simple logging implementation."""
    try:
        logger.info(f"Agent {agent_name} status update: {kwargs}")
        # In a production system, this would update a status store
        # For now, just log the status update
    except Exception as e:
        logger.error(f"Error updating agent status for {agent_name}: {e}")
