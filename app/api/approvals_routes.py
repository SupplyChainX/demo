"""
Enhanced Approvals API Routes - Phase 2 Implementation
Live Data Integration for Approvals Dashboard using DecisionItem model
"""
from flask import jsonify, request, current_app
from datetime import datetime, timedelta
from sqlalchemy import func, desc, asc, and_, or_, case
import json
from app.api import api_bp
from app import db
from app.models import (
    DecisionItem, Recommendation, Shipment, PurchaseOrder,
    Alert, Supplier, User
)

# Helper function to get user by ID
def get_user_by_id(user_id):
    """Get user by ID, return dict or None"""
    if not user_id:
        return None
    user = db.session.get(User, user_id)
    if user:
        return {
            'id': user.id,
            'username': user.username,
            'email': getattr(user, 'email', None),
            'role': getattr(user, 'role', 'analyst')
        }
    return None

# === PHASE 2 APPROVALS API ENDPOINTS ===

@api_bp.route('/approvals/pending', methods=['GET'])
def get_pending_approvals():
    """Get all pending approval items using DecisionItem model"""
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        
        # Query pending decisions using DecisionItem model
        pending_decisions = db.session.query(DecisionItem).filter(
            DecisionItem.workspace_id == workspace_id,
            DecisionItem.status == 'pending',
            DecisionItem.requires_approval == True
        ).order_by(DecisionItem.created_at.desc()).all()
        
        approvals_data = []
        for decision in pending_decisions:
            approvals_data.append({
                'id': decision.id,
                'decision_type': decision.decision_type,
                'title': decision.title,
                'description': decision.description,
                'priority': decision.severity,
                'status': decision.status,
                'created_at': decision.created_at.isoformat(),
                'due_date': decision.approval_deadline.isoformat() if decision.approval_deadline else None,
                'assigned_to': decision.required_role,
                'context_data': decision.context_data,
                'approval_reason': f"Requires {decision.required_role} approval",
                'policy_triggered': f"{decision.decision_type}_policy"
            })
        
        return jsonify({
            'success': True,
            'workspace_id': workspace_id,
            'approvals': approvals_data,
            'count': len(approvals_data)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting pending approvals: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/approvals/queue', methods=['GET'])
def get_approval_queue():
    """Get approval queue with priority sorting"""
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        priority_filter = request.args.get('priority')
        
        query = db.session.query(DecisionItem).filter(
            DecisionItem.workspace_id == workspace_id,
            DecisionItem.status == 'pending',
            DecisionItem.requires_approval == True
        )
        
        if priority_filter:
            query = query.filter(DecisionItem.severity == priority_filter.lower())
        
        # Order by priority and creation date
        pending_decisions = query.order_by(
            DecisionItem.priority_score.desc(),
            DecisionItem.created_at.asc()
        ).all()
        
        queue_data = []
        for decision in pending_decisions:
            # Get related object details
            related_object = None
            if decision.related_object_type == 'shipment' and decision.related_object_id:
                related_object = db.session.get(Shipment, decision.related_object_id)
            elif decision.related_object_type == 'purchase_order' and decision.related_object_id:
                related_object = db.session.get(PurchaseOrder, decision.related_object_id)
            elif decision.related_object_type == 'recommendation' and decision.related_object_id:
                related_object = db.session.get(Recommendation, decision.related_object_id)
            
            queue_data.append({
                'id': decision.id,
                'decision_type': decision.decision_type,
                'title': decision.title,
                'description': decision.description,
                'priority': decision.severity,
                'status': decision.status,
                'created_at': decision.created_at.isoformat(),
                'due_date': decision.approval_deadline.isoformat() if decision.approval_deadline else None,
                'assigned_to': decision.required_role,
                'context_data': decision.context_data,
                'related_object': {
                    'type': decision.related_object_type,
                    'id': decision.related_object_id,
                    'exists': related_object is not None,
                    'status': getattr(related_object, 'status', None),
                    'reference': getattr(related_object, 'reference_number', None) or getattr(related_object, 'id', None)
                } if decision.related_object_type else None
            })
        
        # Calculate priority counts
        priority_counts = {'high': 0, 'medium': 0, 'low': 0, 'critical': 0}
        for decision in pending_decisions:
            priority = decision.severity.lower() if decision.severity else 'medium'
            if priority in priority_counts:
                priority_counts[priority] += 1
        
        return jsonify({
            'success': True,
            'workspace_id': workspace_id,
            'priority_filter': priority_filter,
            'approvals': queue_data,
            'count': len(queue_data),
            'priority_counts': priority_counts
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting approval queue: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/approvals/history', methods=['GET'])
def get_approval_history():
    """Get approval history"""
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        days = request.args.get('days', 30, type=int)
        
        since_date = datetime.utcnow() - timedelta(days=days)
        
        # Get resolved decisions
        resolved_decisions = db.session.query(DecisionItem).filter(
            DecisionItem.workspace_id == workspace_id,
            DecisionItem.status.in_(['approved', 'rejected']),
            DecisionItem.updated_at >= since_date
        ).order_by(DecisionItem.updated_at.desc()).all()
        
        history_data = []
        for decision in resolved_decisions:
            resolution_time_hours = None
            if decision.decision_made_at and decision.created_at:
                resolution_time_hours = (decision.decision_made_at - decision.created_at).total_seconds() / 3600
            
            # Get user info if available
            resolved_by = None
            if decision.decision_made_by:
                user = db.session.get(User, decision.decision_made_by)
                resolved_by = user.username if user else f"User {decision.decision_made_by}"
            
            history_data.append({
                'id': decision.id,
                'decision_type': decision.decision_type,
                'title': decision.title,
                'description': decision.description,
                'status': decision.status,
                'priority': decision.severity,
                'assigned_to': decision.required_role,
                'created_at': decision.created_at.isoformat(),
                'resolved_at': decision.decision_made_at.isoformat() if decision.decision_made_at else None,
                'resolution_time_hours': round(resolution_time_hours, 2) if resolution_time_hours else None,
                'resolved_by': resolved_by,
                'decision_rationale': decision.decision_rationale
            })
        
        # Calculate summary statistics
        total_resolved = len(resolved_decisions)
        avg_resolution_time = 0
        if total_resolved > 0:
            total_hours = sum(
                (decision.decision_made_at - decision.created_at).total_seconds() / 3600
                for decision in resolved_decisions 
                if decision.decision_made_at and decision.created_at
            )
            avg_resolution_time = total_hours / total_resolved if total_resolved > 0 else 0
        
        status_counts = {
            'approved': len([d for d in resolved_decisions if d.status == 'approved']),
            'rejected': len([d for d in resolved_decisions if d.status == 'rejected'])
        }
        
        return jsonify({
            'success': True,
            'workspace_id': workspace_id,
            'period_days': days,
            'approvals': history_data,
            'total_count': total_resolved,
            'summary': {
                'total_resolved': total_resolved,
                'avg_resolution_time_hours': round(avg_resolution_time, 2),
                'status_breakdown': status_counts
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting approval history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/approvals/<int:approval_id>', methods=['GET'])
def get_approval_details(approval_id):
    """Get detailed information about a specific approval"""
    
    decision = db.session.get(DecisionItem, approval_id)
    if not decision:
        return jsonify({'success': False, 'error': 'Approval not found'}), 404
    
    # Get related entities
    related_object = None
    if decision.related_object_type and decision.related_object_id:
        if decision.related_object_type == 'shipment':
            related_object = db.session.get(Shipment, decision.related_object_id)
        elif decision.related_object_type == 'purchase_order':
            related_object = db.session.get(PurchaseOrder, decision.related_object_id)
        elif decision.related_object_type == 'recommendation':
            related_object = db.session.get(Recommendation, decision.related_object_id)
    
    resolved_by = None
    if decision.decision_made_by:
        user = db.session.get(User, decision.decision_made_by)
        resolved_by = user.username if user else f"User {decision.decision_made_by}"
    
    # Build detailed response
    details = {
        'success': True,
        'approval': {
            'id': decision.id,
            'decision_type': decision.decision_type,
            'title': decision.title,
            'description': decision.description,
            'priority': decision.severity,
            'status': decision.status,
            'created_at': decision.created_at.isoformat(),
            'approval_deadline': decision.approval_deadline.isoformat() if decision.approval_deadline else None,
            'decision_made_at': decision.decision_made_at.isoformat() if decision.decision_made_at else None,
            'decision_made_by': resolved_by,
            'decision_rationale': decision.decision_rationale,
            'required_role': decision.required_role,
            'context_data': decision.context_data,
            'possible_actions': decision.possible_actions,
            'estimated_impact_usd': decision.estimated_impact_usd,
            'affected_shipments_count': decision.affected_shipments_count,
            'risk_if_delayed': decision.risk_if_delayed
        }
    }
    
    return jsonify(details)


@api_bp.route('/approvals/<int:approval_id>/approve', methods=['POST'])
def approve_approval(approval_id):
    """Approve a specific approval request"""
    
    decision = db.session.get(DecisionItem, approval_id)
    if not decision:
        return jsonify({'success': False, 'error': 'Approval not found'}), 404
    
    if decision.status != 'pending':
        return jsonify({'success': False, 'error': 'Approval is not in pending state'}), 400
    
    # Get request data
    data = request.get_json() or {}
    rationale = data.get('rationale') or data.get('comments')
    
    # For Phase 1, we'll use a mock user ID
    # In production, this would come from JWT token
    approver_id = data.get('approved_by_id', 1)
    
    # Update decision
    decision.status = 'approved'
    decision.decision_made_by = approver_id
    decision.decision_made_at = datetime.utcnow()
    decision.decision_rationale = rationale
    decision.updated_at = datetime.utcnow()
    
    try:
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Approval granted successfully',
            'approval_id': decision.id,
            'approved_at': decision.decision_made_at.isoformat(),
            'new_status': decision.status
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving approval {approval_id}: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to approve', 'detail': str(e)}), 500


@api_bp.route('/approvals/<int:approval_id>/reject', methods=['POST'])
def reject_approval(approval_id):
    """Reject a specific approval request"""
    
    decision = db.session.get(DecisionItem, approval_id)
    if not decision:
        return jsonify({'success': False, 'error': 'Approval not found'}), 404
    
    if decision.status != 'pending':
        return jsonify({'success': False, 'error': 'Approval is not in pending state'}), 400
    
    # Get request data
    data = request.get_json() or {}
    rationale = data.get('rationale') or data.get('reason') or data.get('comments', 'Not specified')
    
    # For Phase 1, we'll use a mock user ID
    approver_id = data.get('approved_by_id', 1)
    
    # Update decision
    decision.status = 'rejected'
    decision.decision_made_by = approver_id
    decision.decision_made_at = datetime.utcnow()
    decision.decision_rationale = f"Rejected: {rationale}"
    decision.updated_at = datetime.utcnow()
    
    try:
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Approval rejected successfully',
            'approval_id': decision.id,
            'rejected_at': decision.decision_made_at.isoformat(),
            'new_status': decision.status,
            'reason': rationale
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error rejecting approval {approval_id}: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to reject', 'detail': str(e)}), 500


@api_bp.route('/approvals/audit-trail', methods=['GET'])
def get_approval_audit_trail():
    """Get audit trail for approval decisions"""
    
    item_id = request.args.get('item_id', type=int)
    days_back = request.args.get('days', 30, type=int)
    
    start_date = datetime.utcnow() - timedelta(days=days_back)
    
    if item_id:
        # Audit trail for specific approval
        decision = db.session.get(DecisionItem, item_id)
        if not decision:
            return jsonify({'success': False, 'error': 'Approval not found'}), 404
        
        events = []
        
        # Creation event
        events.append({
            'timestamp': decision.created_at.isoformat(),
            'action': 'approval_requested',
            'description': f'Approval requested: {decision.title}',
            'user': decision.created_by,
            'details': {
                'decision_type': decision.decision_type,
                'required_role': decision.required_role,
                'priority': decision.severity
            }
        })
        
        # Decision event
        if decision.decision_made_at:
            resolved_by = 'Unknown'
            if decision.decision_made_by:
                user = db.session.get(User, decision.decision_made_by)
                resolved_by = user.username if user else f"User {decision.decision_made_by}"
            
            events.append({
                'timestamp': decision.decision_made_at.isoformat(),
                'action': 'approval_decided',
                'description': f'Approval {decision.status} by {resolved_by}',
                'user': resolved_by,
                'details': {
                    'decision': decision.status,
                    'rationale': decision.decision_rationale
                }
            })
        
        return jsonify({
            'success': True,
            'item_id': item_id,
            'audit_trail': events
        })
    
    else:
        # General audit trail for recent approval decisions
        recent_decisions = db.session.query(DecisionItem).filter(
            DecisionItem.decision_made_at >= start_date,
            DecisionItem.status.in_(['approved', 'rejected'])
        ).order_by(DecisionItem.decision_made_at.desc()).limit(50).all()
        
        events = []
        for decision in recent_decisions:
            resolved_by = 'Unknown'
            if decision.decision_made_by:
                user = db.session.get(User, decision.decision_made_by)
                resolved_by = user.username if user else f"User {decision.decision_made_by}"
            
            events.append({
                'timestamp': decision.decision_made_at.isoformat(),
                'action': 'approval_decided',
                'description': f'Approval {decision.status} for {decision.title}',
                'user': resolved_by,
                'approval_id': decision.id,
                'details': {
                    'decision_type': decision.decision_type,
                    'decision': decision.status,
                    'rationale': decision.decision_rationale
                }
            })
        
        return jsonify({
            'success': True,
            'period_days': days_back,
            'audit_trail': events,
            'total_events': len(events)
        })

