"""
Orchestrator Agent - Central coordination, policy enforcement, and approval workflows
Enhanced with Phase 4: Advanced Decision Queue Generation and Policy Integration
"""
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from flask import current_app
from sqlalchemy import and_, or_, desc
from app import db
from app.models import (
    Recommendation, Approval, Policy, PolicyType, AuditLog,
    Alert, AlertSeverity, Notification, User, UserWorkspaceRole, Role,
    ApprovalStatus, RecommendationType, Outbox,
    PurchaseOrder, Shipment, Route, Supplier,
    DecisionItem, PolicyTrigger, KPISnapshot  # Phase 4 models
)
from app.agents.communicator import AgentCommunicator
from app.agents.routes import update_agent_status
from app.agents.policy_engine import PolicyEngine  # Phase 4 import

logger = logging.getLogger(__name__)

class OrchestratorAgent:
    """
    Central coordination hub for multi-agent system with enhanced decision queue generation.
    
    Phase 4 Enhancements:
    - Integrated PolicyEngine for automated decision making
    - Advanced decision queue prioritization
    - Escalation management for overdue approvals
    - Cross-domain policy evaluation
    """
    
    def __init__(self, workspace_id: int = 1):
        self.name = 'orchestrator'
        self.workspace_id = workspace_id
        self.communicator = AgentCommunicator(self.name)
        self.policies = self._load_policies()
        self.approval_timeout = current_app.config.get('APPROVAL_TIMEOUT_HOURS', 24)
        
        # Phase 4: Initialize Policy Engine
        self.policy_engine = PolicyEngine(workspace_id=workspace_id)
        self.decision_queue_refresh_interval = 300  # 5 minutes
        self.escalation_check_interval = 3600  # 1 hour
        
    def run_cycle(self):
        """
        Run one orchestration cycle with Phase 4 enhancements.
        
        Enhanced workflow:
        1. Traditional approval processing
        2. Advanced decision queue generation
        3. Policy-driven workflow automation
        4. Intelligent escalation management
        """
        try:
            logger.info(f"{self.name} starting enhanced orchestration cycle")
            update_agent_status(self.name, status='running')
            
            # Phase 1: Traditional approval processing
            approval_requests = self.communicator.receive_messages(
                ['approvals.requests'], count=20
            )
            
            approvals_processed = 0
            for request in approval_requests:
                if self._process_approval_request(request):
                    approvals_processed += 1
            
            # Phase 2: Enhanced decision queue generation
            new_decisions = self.generate_decision_items()
            decisions_generated = len(new_decisions)
            
            # Phase 3: Intelligent queue prioritization
            prioritized_queue = self.prioritize_approval_queue()
            queue_size = len(prioritized_queue)
            
            # Phase 4: Escalation management
            escalated_count = self.escalate_overdue_approvals()
            
            # Phase 5: Traditional workflow processing
            pending_recommendations = self._get_pending_recommendations()
            for recommendation in pending_recommendations:
                self._evaluate_recommendation(recommendation)
            
            # Phase 6: Handle approval timeouts
            self._handle_approval_timeouts()
            
            # Phase 7: Resolve conflicts between recommendations
            self._resolve_conflicts()
            
            # Phase 8: Update policy cache
            self._refresh_policies()
            
            # Enhanced status reporting
            logger.info(f"{self.name} cycle complete: {approvals_processed} approvals, "
                       f"{decisions_generated} new decisions, {queue_size} in queue, "
                       f"{escalated_count} escalated")
            
            update_agent_status(self.name, 
                              approvals=approvals_processed,
                              decisions_generated=decisions_generated,
                              queue_size=queue_size,
                              escalated=escalated_count)
            
        except Exception as e:
            logger.error(f"Error in {self.name} enhanced cycle: {e}")
            update_agent_status(self.name, status='error')
    
    def _load_policies(self) -> Dict[str, Policy]:
        """Load active policies from database."""
        policies = {}
        try:
            active_policies = Policy.query.filter_by(is_active=True).all()
            for policy in active_policies:
                policies[policy.name] = policy
            logger.info(f"Loaded {len(policies)} active policies")
        except Exception as e:
            logger.error(f"Error loading policies: {e}")
        return policies
    
    def _process_approval_request(self, request: Dict[str, Any]) -> bool:
        """Process an approval request from an agent."""
        try:
            request_data = request.get('data', {})
            recommendation_id = request_data.get('recommendation_id')
            recommendation_type = request_data.get('recommendation_type')
            details = request_data.get('details', {})
            
            # Get recommendation
            recommendation = db.session.get(Recommendation, recommendation_id)
            if not recommendation:
                logger.warning(f"Recommendation {recommendation_id} not found")
                return False
            
            # Check if already has approval
            existing_approval = Approval.query.filter_by(
                recommendation_id=recommendation_id,
                state='pending'
            ).first()
            
            if existing_approval:
                logger.info(f"Approval already exists for recommendation {recommendation_id}")
                return False
            
            # Evaluate against policies
            policy_results = self._evaluate_policies(recommendation, details)
            
            # Create approval record
            approval = Approval(
                workspace_id=recommendation.workspace_id,
                recommendation_id=recommendation_id,
                recommendation_type=recommendation_type,
                status='pending',
                requested_by=request_data.get('requested_by', 'system'),
                requested_at=datetime.utcnow(),
                policy_checks=policy_results,
                requires_human_approval=self._requires_human_approval(policy_results, details),
                auto_approve_eligible=self._is_auto_approve_eligible(policy_results, details),
                metadata=details
            )
            db.session.add(approval)
            
            # Auto-approve if eligible
            if approval.auto_approve_eligible and not approval.requires_human_approval:
                self._auto_approve(approval, recommendation)
            else:
                # Notify relevant users
                self._notify_approvers(approval, recommendation)
            
            # Audit log
            self._create_audit_log(
                action='approval_requested',
                actor_type='agent',
                actor_id=request_data.get('requested_by', self.name),
                object_type='recommendation',
                object_id=recommendation_id,
                details=policy_results
            )
            
            db.session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error processing approval request: {e}")
            db.session.rollback()
            return False
    
    def _evaluate_policies(self, recommendation: Recommendation, 
                          details: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Evaluate recommendation against active policies."""
        results = []
        
        # Spend threshold policies
        if recommendation.type == RecommendationType.REORDER:
            amount = details.get('amount', 0)
            spend_policy = self.policies.get('spend_threshold')
            if spend_policy:
                thresholds = spend_policy.rules.get('thresholds', [])
                for threshold in thresholds:
                    if amount >= threshold.get('amount', 0):
                        results.append({
                            'policy': 'spend_threshold',
                            'triggered': True,
                            'reason': f"Amount ${amount:,.2f} exceeds ${threshold['amount']:,.2f}",
                            'required_approvals': threshold.get('approvals', 1),
                            'approver_roles': threshold.get('roles', ['manager'])
                        })
                        break
        
        # Geographic exclusion policies
        if recommendation.type == RecommendationType.REROUTE:
            waypoints = details.get('waypoints', [])
            geo_policy = self.policies.get('geo_exclusion')
            if geo_policy:
                excluded_regions = geo_policy.rules.get('excluded_regions', [])
                for waypoint in waypoints:
                    if waypoint.get('country') in excluded_regions:
                        results.append({
                            'policy': 'geo_exclusion',
                            'triggered': True,
                            'reason': f"Route includes excluded region: {waypoint.get('country')}",
                            'action': 'block'
                        })
        
        # Risk threshold policies
        risk_score = recommendation.impact_assessment.get('risk_score', 0)
        risk_policy = self.policies.get('risk_threshold')
        if risk_policy:
            max_risk = risk_policy.rules.get('max_acceptable_risk', 0.8)
            if risk_score > max_risk:
                results.append({
                    'policy': 'risk_threshold',
                    'triggered': True,
                    'reason': f"Risk score {risk_score:.2f} exceeds threshold {max_risk}",
                    'required_approvals': 2
                })
        
        # Carbon cap policies
        if recommendation.type == RecommendationType.REROUTE:
            emissions = details.get('emissions_delta', 0)
            carbon_policy = self.policies.get('carbon_cap')
            if carbon_policy:
                max_increase = carbon_policy.rules.get('max_emissions_increase_percent', 20)
                if emissions > max_increase:
                    results.append({
                        'policy': 'carbon_cap',
                        'triggered': True,
                        'reason': f"Emissions increase {emissions}% exceeds {max_increase}% cap",
                        'action': 'review'
                    })
        
        # SLA policies
        if recommendation.type in [RecommendationType.REROUTE, RecommendationType.REORDER]:
            time_impact = recommendation.impact_assessment.get('time_delta_hours', 0)
            sla_policy = self.policies.get('sla_compliance')
            if sla_policy:
                max_delay = sla_policy.rules.get('max_delay_hours', 48)
                if time_impact > max_delay:
                    results.append({
                        'policy': 'sla_compliance',
                        'triggered': True,
                        'reason': f"Delay of {time_impact}h exceeds SLA limit of {max_delay}h",
                        'action': 'escalate'
                    })
        
        return results
    
    def _requires_human_approval(self, policy_results: List[Dict], 
                               details: Dict[str, Any]) -> bool:
        """Determine if human approval is required."""
        # Check policy results
        for result in policy_results:
            if result.get('triggered'):
                if result.get('action') in ['block', 'escalate']:
                    return True
                if result.get('required_approvals', 0) > 0:
                    return True
        
        # Check amount thresholds
        if details.get('amount', 0) > current_app.config.get('AUTO_APPROVE_LIMIT', 10000):
            return True
        
        # Check risk level
        if details.get('risk_score', 0) > 0.7:
            return True
        
        return False
    
    def _is_auto_approve_eligible(self, policy_results: List[Dict], 
                                 details: Dict[str, Any]) -> bool:
        """Check if recommendation can be auto-approved."""
        # No blocking policies
        for result in policy_results:
            if result.get('triggered') and result.get('action') == 'block':
                return False
        
        # Within auto-approve limits
        if details.get('amount', 0) > current_app.config.get('AUTO_APPROVE_LIMIT', 10000):
            return False
        
        # Low risk
        if details.get('risk_score', 0) > 0.3:
            return False
        
        return True
    
    def _auto_approve(self, approval: Approval, recommendation: Recommendation):
        """Automatically approve a recommendation."""
        try:
            approval.state = ApprovalStatus.APPROVED
            approval.approved_by_id = None  # System approval
            approval.approved_at = datetime.utcnow()
            approval.comments = 'Auto-approved per policy'
            
            recommendation.status = 'approved'
            recommendation.approved_at = datetime.utcnow()
            recommendation.approved_by = 'system'
            
            # Execute the recommendation
            self._execute_recommendation(recommendation)
            
            # Audit log
            self._create_audit_log(
                action='auto_approved',
                actor_type='system',
                actor_id='orchestrator',
                object_type='recommendation',
                object_id=recommendation.id,
                details={'reason': 'Met auto-approval criteria'}
            )
            
            # Notify of auto-approval
            self.communicator.broadcast_update('approval_completed', {
                'recommendation_id': recommendation.id,
                'status': 'approved',
                'auto_approved': True
            })
            
        except Exception as e:
            logger.error(f"Error auto-approving: {e}")
    
    def _notify_approvers(self, approval: Approval, recommendation: Recommendation):
        """Notify relevant users about pending approval."""
        try:
            # Determine approvers based on policy
            approver_roles = []
            for check in approval.policy_checks:
                if check.get('triggered'):
                    approver_roles.extend(check.get('approver_roles', ['manager']))
            
            if not approver_roles:
                approver_roles = ['manager']  # Default
            
            # Find users with required roles
            approvers = db.session.query(User).join(UserWorkspaceRole).join(Role).filter(
                UserWorkspaceRole.workspace_id == approval.workspace_id,
                Role.name.in_(approver_roles),
                User.is_active == True
            ).all()
            
            # Create notifications
            for approver in approvers:
                notification = Notification(
                    workspace_id=approval.workspace_id,
                    user_id=approver.id,
                    type='approval_required',
                    title=f"Approval Required: {recommendation.title}",
                    message=f"{recommendation.description}\n\nRequires your approval.",
                    data={
                        'approval_id': approval.id,
                        'recommendation_id': recommendation.id,
                        'type': recommendation.type.value
                    },
                    created_at=datetime.utcnow()
                )
                db.session.add(notification)
            
            # Broadcast to UI
            self.communicator.broadcast_update('approval_required', {
                'approval_id': approval.id,
                'recommendation_id': recommendation.id,
                'title': recommendation.title,
                'approvers_notified': len(approvers)
            })
            
        except Exception as e:
            logger.error(f"Error notifying approvers: {e}")
    
    def _execute_recommendation(self, recommendation: Recommendation):
        """Execute an approved recommendation."""
        try:
            if recommendation.type == RecommendationType.REROUTE:
                self._execute_reroute(recommendation)
            elif recommendation.type == RecommendationType.REORDER:
                self._execute_procurement(recommendation)
            elif recommendation.type == RecommendationType.ROUTE_OPTIMIZATION:
                self._execute_alert_response(recommendation)
            
            # Update recommendation status
            recommendation.status = 'executed'
            recommendation.executed_at = datetime.utcnow()
            
            # Notify completion
            self.communicator.broadcast_update('recommendation_executed', {
                'recommendation_id': recommendation.id,
                'type': recommendation.type.value,
                'executed_at': recommendation.executed_at.isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error executing recommendation: {e}")
            recommendation.status = 'execution_failed'
            recommendation.error_message = str(e)
    
    def _execute_reroute(self, recommendation: Recommendation):
        """Execute a reroute recommendation."""
        shipment = db.session.get(Shipment, recommendation.shipment_id)
        if not shipment:
            return
        
        # Update current route to not current
        for route in shipment.routes:
            if route.is_current:
                route.is_current = False
        
        # Set recommended route as current
        for route in shipment.routes:
            if route.is_recommended:
                route.is_current = True
                route.is_recommended = False
                break
        
        # Update shipment status
        shipment.last_updated = datetime.utcnow()
        
        # Add to outbox
        outbox_event = Outbox(
            aggregate_id=str(shipment.id),
            aggregate_type='shipment',
            event_type='route_changed',
            event_data={
                'shipment_id': shipment.id,
                'new_route': shipment.current_route.name if shipment.current_route else 'Unknown'
            },
            stream_name='shipments.status'
        )
        db.session.add(outbox_event)
    
    def _execute_procurement(self, recommendation: Recommendation):
        """Execute a procurement recommendation."""
        po = db.session.get(PurchaseOrder, recommendation.subject_id)
        if not po:
            return
        
        # Update PO status
        from app.models import PurchaseOrderStatus
        po.status = PurchaseOrderStatus.APPROVED
        po.approved_at = datetime.utcnow()
        po.approved_by = 'orchestrator'
        
        # Send to supplier (would integrate with actual system)
        outbox_event = Outbox(
            aggregate_id=str(po.id),
            aggregate_type='purchase_order',
            event_type='po_approved',
            event_data={
                'po_id': po.id,
                'supplier_id': po.supplier_id,
                'amount': float(po.total_amount)
            },
            stream_name='procurement.actions'
        )
        db.session.add(outbox_event)
    
    def _get_pending_recommendations(self) -> List[Recommendation]:
        """Get recommendations pending evaluation."""
        return Recommendation.query.filter(
            Recommendation.status == 'pending',
            Recommendation.created_at >= datetime.utcnow() - timedelta(days=7)
        ).limit(50).all()
    
    def _evaluate_recommendation(self, recommendation: Recommendation):
        """Evaluate a pending recommendation."""
        # Check if already has approval record
        approval = Approval.query.filter_by(
            recommendation_id=recommendation.id
        ).first()
        
        if not approval:
            # Create approval request
            self._process_approval_request({
                'data': {
                    'recommendation_id': recommendation.id,
                    'recommendation_type': recommendation.type.value,
                    'details': recommendation.impact_assessment,
                    'requested_by': recommendation.created_by
                }
            })
    
    def _handle_approval_timeouts(self):
        """Handle approvals that have timed out."""
        timeout_threshold = datetime.utcnow() - timedelta(hours=self.approval_timeout)
        
        timed_out = Approval.query.filter(
            Approval.state == 'pending',
            Approval.created_at < timeout_threshold
        ).all()
        
        for approval in timed_out:
            approval.state = ApprovalStatus.TIMEOUT
            approval.decided_at = datetime.utcnow()
            approval.decision_notes = f'Timed out after {self.approval_timeout} hours'
            
            # Update recommendation
            recommendation = db.session.get(Recommendation, approval.recommendation_id)
            if recommendation:
                recommendation.status = 'timeout'
            
            # Notify about timeout
            self._create_notification(
                workspace_id=approval.workspace_id,
                type='approval_timeout',
                title=f"Approval Timeout: {recommendation.title if recommendation else 'Unknown'}",
                message=f"Approval request timed out after {self.approval_timeout} hours"
            )
            
            # Audit log
            self._create_audit_log(
                action='approval_timeout',
                actor_type='system',
                actor_id='orchestrator',
                object_type='approval',
                object_id=approval.id
            )
    
    def _resolve_conflicts(self):
        """Resolve conflicts between multiple recommendations."""
        # Find recommendations for same subject
        recent_recommendations = Recommendation.query.filter(
            Recommendation.status == 'pending',
            Recommendation.created_at >= datetime.utcnow() - timedelta(hours=1)
        ).all()
        
        # Group by subject
        by_subject = {}
        for rec in recent_recommendations:
            key = f"{rec.subject_type}:{rec.subject_id}"
            if key not in by_subject:
                by_subject[key] = []
            by_subject[key].append(rec)
        
        # Resolve conflicts
        for subject_key, recs in by_subject.items():
            if len(recs) > 1:
                self._resolve_subject_conflicts(recs)
    
    def _resolve_subject_conflicts(self, recommendations: List[Recommendation]):
        """Resolve conflicts for recommendations on same subject."""
        # Sort by confidence and severity
        sorted_recs = sorted(
            recommendations,
            key=lambda r: (r.confidence, r.severity.value),
            reverse=True
        )
        
        # Keep highest confidence recommendation
        primary = sorted_recs[0]
        
        # Mark others as superseded
        for rec in sorted_recs[1:]:
            rec.status = 'superseded'
            rec.metadata = rec.metadata or {}
            rec.metadata['superseded_by'] = primary.id
            
            # Audit log
            self._create_audit_log(
                action='recommendation_superseded',
                actor_type='agent',
                actor_id=self.name,
                object_type='recommendation',
                object_id=rec.id,
                details={'superseded_by': primary.id, 'reason': 'conflict_resolution'}
            )
    
    def _refresh_policies(self):
        """Refresh policy cache from database."""
        self.policies = self._load_policies()
    
    def _create_audit_log(self, action: str, actor_type: str, actor_id: str,
                         object_type: str, object_id: Any, details: Dict = None):
        """Create audit log entry."""
        try:
            audit = AuditLog(
                action=action,
                actor_type=actor_type,
                actor_id=actor_id,
                object_type=object_type,
                object_id=str(object_id),
                details=details or {},
                ip_address='127.0.0.1',  # Would get from request in real app
                user_agent='orchestrator',
                created_at=datetime.utcnow()
            )
            db.session.add(audit)
        except Exception as e:
            logger.error(f"Error creating audit log: {e}")
    
    def _create_notification(self, workspace_id: int, type: str, 
                           title: str, message: str, user_id: int = None):
        """Create notification."""
        try:
            notification = Notification(
                workspace_id=workspace_id,
                user_id=user_id,  # None means all users
                type=type,
                title=title,
                message=message,
                created_at=datetime.utcnow()
            )
            db.session.add(notification)
        except Exception as e:
            logger.error(f"Error creating notification: {e}")

    # =====================================
    # PHASE 4: ENHANCED DECISION QUEUE GENERATION
    # =====================================
    
    def generate_decision_items(self) -> List[DecisionItem]:
        """
        Generate decision items from various sources using advanced policy evaluation.
        
        Returns:
            List of DecisionItem objects requiring attention
        """
        decision_items = []
        
        try:
            logger.info("Generating decision items using policy engine")
            
            # 1. Evaluate active shipments for policy violations
            active_shipments = Shipment.query.filter(
                Shipment.status.in_(['planned', 'in_transit', 'scheduled']),
                Shipment.workspace_id == self.workspace_id
            ).all()
            
            for shipment in active_shipments:
                violations = self.policy_engine.evaluate_shipment_policies(shipment)
                if violations:
                    workflow_items = self.policy_engine.trigger_approval_workflow(shipment, violations)
                    # Convert workflow dictionaries to DecisionItem objects
                    for workflow in workflow_items:
                        decision_item = self._create_decision_from_workflow(workflow, 'shipment', shipment.id)
                        if decision_item:
                            decision_items.append(decision_item)
            
            # 2. Evaluate purchase orders for procurement policies  
            pending_pos = PurchaseOrder.query.filter(
                PurchaseOrder.status.in_(['draft', 'pending_approval']),
                PurchaseOrder.workspace_id == self.workspace_id
            ).all()
            
            for po in pending_pos:
                violations = self.policy_engine.evaluate_procurement_policies(po)
                if violations:
                    workflow_items = self.policy_engine.trigger_approval_workflow(po, violations)
                    # Convert workflow dictionaries to DecisionItem objects
                    for workflow in workflow_items:
                        decision_item = self._create_decision_from_workflow(workflow, 'purchase_order', po.id)
                        if decision_item:
                            decision_items.append(decision_item)
            
            # 3. Evaluate suppliers for risk-based decisions
            active_suppliers = Supplier.query.filter(
                Supplier.status == 'active',
                Supplier.workspace_id == self.workspace_id
            ).all()
            
            for supplier in active_suppliers:
                violations = self.policy_engine.evaluate_supplier_policies(supplier)
                if violations:
                    workflow_items = self.policy_engine.trigger_approval_workflow(supplier, violations)
                    # Convert workflow dictionaries to DecisionItem objects  
                    for workflow in workflow_items:
                        decision_item = self._create_decision_from_workflow(workflow, 'supplier', supplier.id)
                        if decision_item:
                            decision_items.append(decision_item)
            
            # 4. Generate decisions from recommendations with complex approval logic
            pending_recommendations = Recommendation.query.filter(
                Recommendation.status == 'pending',
                Recommendation.workspace_id == self.workspace_id
            ).all()
            
            for recommendation in pending_recommendations:
                decision_item = self._create_recommendation_decision(recommendation)
                if decision_item:
                    decision_items.append(decision_item)
            
            # 5. Generate decisions from critical alerts requiring escalation
            critical_alerts = Alert.query.filter(
                Alert.severity == AlertSeverity.CRITICAL.value,
                Alert.status == 'open',
                Alert.workspace_id == self.workspace_id
            ).all()
            
            for alert in critical_alerts:
                decision_item = self._create_alert_decision(alert)
                if decision_item:
                    decision_items.append(decision_item)
            
            logger.info(f"Generated {len(decision_items)} new decision items")
            
        except Exception as e:
            logger.error(f"Error generating decision items: {e}")
        
        return decision_items
    
    def prioritize_approval_queue(self) -> List[DecisionItem]:
        """
        Advanced prioritization of approval queue using multiple factors.
        
        Returns:
            Prioritized list of DecisionItem objects
        """
        try:
            # Get all pending decision items
            pending_decisions = DecisionItem.query.filter(
                DecisionItem.workspace_id == self.workspace_id,
                DecisionItem.status == 'pending',
                DecisionItem.requires_approval == True
            ).all()
            
            # Calculate priority scores for each decision
            for decision in pending_decisions:
                priority_score = self._calculate_priority_score(decision)
                decision.priority_score = priority_score
            
            # Sort by priority score (highest first)
            prioritized_decisions = sorted(
                pending_decisions, 
                key=lambda d: d.priority_score if d.priority_score else 0, 
                reverse=True
            )
            
            # Update database with new priority scores
            for decision in prioritized_decisions:
                db.session.merge(decision)
            
            db.session.commit()
            
            logger.info(f"Prioritized {len(prioritized_decisions)} approval queue items")
            return prioritized_decisions
            
        except Exception as e:
            logger.error(f"Error prioritizing approval queue: {e}")
            db.session.rollback()
            return []
    
    def escalate_overdue_approvals(self) -> int:
        """
        Identify and escalate overdue approvals based on deadline and importance.
        
        Returns:
            Number of approvals escalated
        """
        escalated_count = 0
        
        try:
            # Find overdue approvals
            now = datetime.utcnow()
            overdue_decisions = DecisionItem.query.filter(
                DecisionItem.workspace_id == self.workspace_id,
                DecisionItem.status == 'pending',
                DecisionItem.requires_approval == True,
                DecisionItem.approval_deadline < now
            ).all()
            
            for decision in overdue_decisions:
                escalation_result = self._escalate_approval(decision)
                if escalation_result:
                    escalated_count += 1
            
            # Also check for approvals approaching deadline (within 2 hours)
            deadline_approaching = DecisionItem.query.filter(
                DecisionItem.workspace_id == self.workspace_id,
                DecisionItem.status == 'pending',
                DecisionItem.requires_approval == True,
                DecisionItem.approval_deadline.between(now, now + timedelta(hours=2))
            ).all()
            
            for decision in deadline_approaching:
                self._send_deadline_warning(decision)
            
            logger.info(f"Escalated {escalated_count} overdue approvals")
            
        except Exception as e:
            logger.error(f"Error escalating overdue approvals: {e}")
        
        return escalated_count
    
    def _calculate_priority_score(self, decision: DecisionItem) -> float:
        """
        Calculate comprehensive priority score for decision item.
        
        Factors considered:
        - Severity level
        - Financial impact
        - Time sensitivity (deadline proximity)
        - Affected shipments count
        - Risk if delayed
        - Approval role level
        """
        score = 0.0
        
        try:
            # 1. Base severity score
            severity_scores = {
                'critical': 100,
                'high': 75,
                'medium': 50,
                'low': 25
            }
            score += severity_scores.get(decision.severity, 25)
            
            # 2. Financial impact multiplier
            if decision.estimated_impact_usd:
                if decision.estimated_impact_usd > 100000:
                    score += 50
                elif decision.estimated_impact_usd > 50000:
                    score += 30
                elif decision.estimated_impact_usd > 10000:
                    score += 15
                else:
                    score += 5
            
            # 3. Time sensitivity (deadline proximity)
            if decision.approval_deadline:
                hours_until_deadline = (decision.approval_deadline - datetime.utcnow()).total_seconds() / 3600
                if hours_until_deadline < 2:
                    score += 40  # Extremely urgent
                elif hours_until_deadline < 8:
                    score += 25  # Very urgent
                elif hours_until_deadline < 24:
                    score += 15  # Urgent
                elif hours_until_deadline < 72:
                    score += 5   # Moderately urgent
            
            # 4. Affected shipments multiplier
            if decision.affected_shipments_count:
                score += min(decision.affected_shipments_count * 5, 30)  # Cap at 30 points
            
            # 5. Role escalation level
            role_scores = {
                'director': 30,
                'manager': 20,
                'analyst': 10
            }
            score += role_scores.get(decision.required_role, 10)
            
            # 6. Decision type priority
            type_scores = {
                'route_approval': 20,
                'procurement': 15,
                'risk_mitigation': 25,
                'inventory': 30,
                'policy_violation': 20
            }
            score += type_scores.get(decision.decision_type, 10)
            
            # 7. Age factor (older decisions get slight priority boost)
            if decision.created_at:
                hours_old = (datetime.utcnow() - decision.created_at).total_seconds() / 3600
                score += min(hours_old * 0.5, 20)  # Cap at 20 points
            
        except Exception as e:
            logger.error(f"Error calculating priority score for decision {decision.id}: {e}")
            score = 50  # Default score
        
        return score
    
    def _create_recommendation_decision(self, recommendation: Recommendation) -> Optional[DecisionItem]:
        """Create DecisionItem from Recommendation that needs approval"""
        try:
            # Check if decision already exists
            existing = DecisionItem.query.filter(
                DecisionItem.related_object_type == 'recommendation',
                DecisionItem.related_object_id == recommendation.id,
                DecisionItem.status == 'pending'
            ).first()
            
            if existing:
                return None
            
            # Determine if approval is needed based on recommendation type and complexity
            requires_approval = self._recommendation_requires_approval(recommendation)
            
            if not requires_approval:
                return None
            
            decision_item = DecisionItem(
                workspace_id=self.workspace_id,
                decision_type='recommendation_approval',
                title=f'Approve Recommendation: {recommendation.title}',
                description=f'{recommendation.recommendation_type} recommendation requires approval',
                status='pending',
                severity=self._map_recommendation_severity(recommendation),
                requires_approval=True,
                approval_deadline=datetime.utcnow() + timedelta(hours=48),
                required_role=self._get_recommendation_approval_role(recommendation),
                related_object_type='recommendation',
                related_object_id=recommendation.id,
                context_data={
                    'recommendation_type': recommendation.recommendation_type,
                    'confidence_score': recommendation.confidence_score,
                    'expected_benefit': recommendation.expected_benefit,
                    'implementation_complexity': recommendation.metadata.get('complexity', 'medium')
                },
                estimated_impact_usd=recommendation.expected_benefit or 0,
                risk_if_delayed='Potential optimization opportunities missed if recommendation not reviewed'
            )
            
            db.session.add(decision_item)
            db.session.commit()
            
            return decision_item
            
        except Exception as e:
            logger.error(f"Error creating recommendation decision: {e}")
            db.session.rollback()
            return None
    
    def _create_alert_decision(self, alert: Alert) -> Optional[DecisionItem]:
        """Create DecisionItem from critical Alert that needs escalation"""
        try:
            # Check if decision already exists
            existing = DecisionItem.query.filter(
                DecisionItem.related_object_type == 'alert',
                DecisionItem.related_object_id == alert.id,
                DecisionItem.status == 'pending'
            ).first()
            
            if existing:
                return None
            
            decision_item = DecisionItem(
                workspace_id=self.workspace_id,
                decision_type='alert_escalation',
                title=f'Critical Alert Escalation: {alert.title}',
                description=f'Critical alert requires immediate attention and decision',
                status='pending',
                severity='critical',
                requires_approval=True,
                approval_deadline=datetime.utcnow() + timedelta(hours=4),  # 4-hour escalation
                required_role='manager',
                related_object_type='alert',
                related_object_id=alert.id,
                context_data={
                    'alert_type': alert.alert_type,
                    'alert_data': alert.alert_data,
                    'affected_shipment': alert.related_shipment_id
                },
                estimated_impact_usd=self._estimate_alert_impact(alert),
                risk_if_delayed='Critical operational issue may escalate without intervention'
            )
            
            db.session.add(decision_item)
            db.session.commit()
            
            return decision_item
            
        except Exception as e:
            logger.error(f"Error creating alert decision: {e}")
            db.session.rollback()
            return None
    
    def _create_decision_from_workflow(self, workflow: Dict[str, Any], object_type: str, object_id: int) -> Optional[DecisionItem]:
        """Convert policy workflow dictionary to DecisionItem object"""
        try:
            # Check if decision already exists for this object and rule
            existing = DecisionItem.query.filter(
                DecisionItem.related_object_type == object_type,
                DecisionItem.related_object_id == object_id,
                DecisionItem.status == 'pending'
            ).filter(
                DecisionItem.context_data.contains({'rule_name': workflow.get('rule_name')})
            ).first()
            
            if existing:
                return None
            
            # Map workflow severity to decision severity
            severity_map = {
                'low': 'low',
                'medium': 'medium', 
                'high': 'high',
                'critical': 'critical'
            }
            severity = severity_map.get(workflow.get('severity', 'medium'), 'medium')
            
            # Calculate approval deadline based on severity
            deadline_hours = {
                'critical': 4,
                'high': 24,
                'medium': 48,
                'low': 72
            }
            hours = deadline_hours.get(severity, 48)
            
            decision_item = DecisionItem(
                workspace_id=self.workspace_id,
                decision_type='policy_violation_approval',
                title=f'Policy Violation: {workflow.get("rule_name", "Unknown Rule")}',
                description=f'Policy violation detected requiring approval for {object_type} #{object_id}',
                status='pending',
                severity=severity,
                requires_approval=True,
                approval_deadline=datetime.utcnow() + timedelta(hours=hours),
                required_role=self._get_policy_approval_role(workflow.get('rule_name', ''), severity),
                related_object_type=object_type,
                related_object_id=object_id,
                created_by='orchestrator',
                created_by_type='agent',
                context_data={
                    'rule_name': workflow.get('rule_name'),
                    'violation_severity': workflow.get('severity'),
                    'violation_context': workflow.get('violation_context', {}),
                    'escalation_deadline': workflow.get('escalation_deadline').isoformat() if workflow.get('escalation_deadline') else None,
                    'workflow_type': workflow.get('type', 'approval_required')
                },
                estimated_impact_usd=self._estimate_workflow_impact(workflow, object_type),
                risk_if_delayed=self._calculate_risk_score(workflow, object_type)
            )
            
            db.session.add(decision_item)
            db.session.commit()
            
            return decision_item
            
        except Exception as e:
            logger.error(f"Error creating decision from workflow: {e}")
            db.session.rollback()
            return None
    
    def _get_policy_approval_role(self, rule_name: str, severity: str) -> str:
        """Determine required approval role based on policy rule and severity"""
        # High-value or critical policies require senior approval
        if severity == 'critical' or 'high_value' in rule_name.lower():
            return 'director'
        elif severity == 'high' or 'emergency' in rule_name.lower():
            return 'senior_manager'
        else:
            return 'manager'
    
    def _estimate_workflow_impact(self, workflow: Dict[str, Any], object_type: str) -> float:
        """Estimate financial impact of workflow violation"""
        # Basic estimation based on object type and severity
        base_impact = {
            'shipment': 5000.0,
            'purchase_order': 10000.0,
            'supplier': 15000.0
        }
        
        severity_multiplier = {
            'low': 0.5,
            'medium': 1.0,
            'high': 2.0,
            'critical': 5.0
        }
        
        base = base_impact.get(object_type, 5000.0)
        multiplier = severity_multiplier.get(workflow.get('severity', 'medium'), 1.0)
        
        return base * multiplier
    
    def _calculate_risk_score(self, workflow: Dict[str, Any], object_type: str) -> float:
        """Calculate numeric risk score for workflow violation"""
        # Map severity to risk score (0.0 to 1.0)
        severity_risk = {
            'low': 0.2,
            'medium': 0.5,
            'high': 0.8,
            'critical': 1.0
        }
        
        # Base risk by object type
        type_risk = {
            'shipment': 0.3,
            'purchase_order': 0.6,
            'supplier': 0.8
        }
        
        severity = workflow.get('severity', 'medium')
        base_risk = type_risk.get(object_type, 0.5)
        severity_factor = severity_risk.get(severity, 0.5)
        
        # Calculate combined risk score
        risk_score = min(1.0, base_risk + severity_factor * 0.5)
        
        return round(risk_score, 2)
    
    def _escalate_approval(self, decision: DecisionItem) -> bool:
        """Escalate an overdue approval to higher authority"""
        try:
            # Determine escalation target
            current_role = decision.required_role
            escalation_role = self._get_escalation_role(current_role)
            
            # Update decision with escalation
            decision.required_role = escalation_role
            decision.approval_deadline = datetime.utcnow() + timedelta(hours=12)  # New deadline
            decision.severity = self._escalate_severity(decision.severity)
            
            # Add escalation context
            if not decision.context_data:
                decision.context_data = {}
            decision.context_data['escalated_from'] = current_role
            decision.context_data['escalated_at'] = datetime.utcnow().isoformat()
            decision.context_data['escalation_reason'] = 'Approval deadline exceeded'
            
            # Create escalation notification
            self._create_escalation_notification(decision, current_role, escalation_role)
            
            # Audit log
            self._create_audit_log(
                action='approval_escalated',
                actor_type='system',
                actor_id='orchestrator',
                object_type='decision_item',
                object_id=decision.id,
                details={
                    'from_role': current_role,
                    'to_role': escalation_role,
                    'reason': 'deadline_exceeded'
                }
            )
            
            db.session.commit()
            logger.info(f"Escalated decision {decision.id} from {current_role} to {escalation_role}")
            return True
            
        except Exception as e:
            logger.error(f"Error escalating approval {decision.id}: {e}")
            db.session.rollback()
            return False
    
    def _send_deadline_warning(self, decision: DecisionItem):
        """Send warning notification for approaching deadline"""
        try:
            hours_remaining = (decision.approval_deadline - datetime.utcnow()).total_seconds() / 3600
            
            self._create_notification(
                workspace_id=decision.workspace_id,
                type='deadline_warning',
                title=f'Approval Deadline Approaching',
                message=f'Decision "{decision.title}" requires approval within {hours_remaining:.1f} hours'
            )
            
        except Exception as e:
            logger.error(f"Error sending deadline warning: {e}")
    
    def _create_escalation_notification(self, decision: DecisionItem, from_role: str, to_role: str):
        """Create notification for approval escalation"""
        try:
            self._create_notification(
                workspace_id=decision.workspace_id,
                type='escalation',
                title=f'Approval Escalated to {to_role.title()}',
                message=f'Decision "{decision.title}" has been escalated from {from_role} to {to_role} due to missed deadline'
            )
            
        except Exception as e:
            logger.error(f"Error creating escalation notification: {e}")
    
    # Helper methods for decision generation
    def _recommendation_requires_approval(self, recommendation: Recommendation) -> bool:
        """Determine if recommendation requires human approval"""
        # High-impact or low-confidence recommendations need approval
        if recommendation.confidence_score and recommendation.confidence_score < 0.7:
            return True
        if recommendation.expected_benefit and recommendation.expected_benefit > 10000:
            return True
        if recommendation.recommendation_type in ['route_change', 'supplier_change']:
            return True
        return False
    
    def _map_recommendation_severity(self, recommendation: Recommendation) -> str:
        """Map recommendation to severity level"""
        if recommendation.expected_benefit and recommendation.expected_benefit > 50000:
            return 'high'
        elif recommendation.confidence_score and recommendation.confidence_score < 0.5:
            return 'medium'
        else:
            return 'low'
    
    def _get_recommendation_approval_role(self, recommendation: Recommendation) -> str:
        """Determine required approval role for recommendation"""
        if recommendation.expected_benefit and recommendation.expected_benefit > 25000:
            return 'director'
        elif recommendation.recommendation_type in ['route_change', 'supplier_change']:
            return 'manager'
        else:
            return 'analyst'
    
    def _estimate_alert_impact(self, alert: Alert) -> float:
        """Estimate financial impact of critical alert"""
        # Simple heuristic based on alert type
        impact_map = {
            'shipment_delay': 5000,
            'route_disruption': 15000,
            'supplier_issue': 10000,
            'system_error': 2000
        }
        return impact_map.get(alert.alert_type, 5000)
    
    def _get_escalation_role(self, current_role: str) -> str:
        """Get escalation target role"""
        escalation_map = {
            'analyst': 'manager',
            'manager': 'director',
            'director': 'director'  # Already at top
        }
        return escalation_map.get(current_role, 'manager')
    
    def _escalate_severity(self, current_severity: str) -> str:
        """Escalate severity level"""
        escalation_map = {
            'low': 'medium',
            'medium': 'high',
            'high': 'critical',
            'critical': 'critical'  # Already at top
        }
        return escalation_map.get(current_severity, 'high')


def start_orchestrator_loop(app=None):
    """Main loop for Enhanced Orchestrator Agent with Phase 4 capabilities."""
    logger.info("Starting Enhanced Orchestrator Agent loop with Policy Engine")
    
    if app is None:
        from flask import current_app
        app = current_app._get_current_object()
    
    with app.app_context():
        agent = OrchestratorAgent(workspace_id=1)  # Phase 4: Enhanced initialization
        loop_interval = 30  # Run every 30 seconds
        
        while True:
            try:
                agent.run_cycle()
                time.sleep(loop_interval)
            except Exception as e:
                logger.error(f"Error in enhanced orchestrator loop: {e}")
                time.sleep(loop_interval)
