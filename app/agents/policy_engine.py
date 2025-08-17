"""
Policy Engine - Intelligent Decision and Approval Workflow Automation
Phase 4 Implementation: Advanced Analytics and Agent Integration
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json

from app import db
from app.models import (
    Shipment, PurchaseOrder, Supplier, DecisionItem, PolicyTrigger,
    Recommendation, Alert, AlertSeverity
)

logger = logging.getLogger(__name__)

class PolicyType(Enum):
    PROCUREMENT = "procurement"
    SHIPMENT = "shipment"
    SUPPLIER = "supplier"
    RISK = "risk"
    FINANCIAL = "financial"
    COMPLIANCE = "compliance"

class ThresholdType(Enum):
    MONETARY = "monetary"
    TIME = "time"
    PERCENTAGE = "percentage"
    COUNT = "count"
    SCORE = "score"

@dataclass
class PolicyRule:
    """Individual policy rule definition"""
    name: str
    condition: str
    threshold_value: float
    threshold_type: ThresholdType
    required_role: str
    priority: str
    escalation_hours: int
    description: str
    auto_approve: bool = False

@dataclass
class PolicyViolation:
    """Result of policy evaluation"""
    rule_name: str
    violated: bool
    current_value: float
    threshold_value: float
    severity: str
    requires_approval: bool
    escalation_deadline: datetime
    context: Dict[str, Any]

class PolicyEngine:
    """
    Advanced Policy Engine for automated decision making and approval workflows
    
    Features:
    - Multi-domain policy evaluation (procurement, shipping, risk, compliance)
    - Threshold-based rule engine
    - Automatic approval workflow generation
    - Escalation management
    - Historical policy performance tracking
    """
    
    def __init__(self, workspace_id: int = 1):
        self.workspace_id = workspace_id
        self.policy_rules = self._load_policy_rules()
        
    def _load_policy_rules(self) -> Dict[PolicyType, List[PolicyRule]]:
        """Load policy rules configuration"""
        return {
            PolicyType.PROCUREMENT: [
                PolicyRule(
                    name="high_value_procurement",
                    condition="purchase_amount > threshold",
                    threshold_value=50000.0,
                    threshold_type=ThresholdType.MONETARY,
                    required_role="director",
                    priority="high",
                    escalation_hours=24,
                    description="High-value procurement requires director approval"
                ),
                PolicyRule(
                    name="emergency_procurement",
                    condition="urgency == 'emergency' AND purchase_amount > threshold",
                    threshold_value=25000.0,
                    threshold_type=ThresholdType.MONETARY,
                    required_role="manager",
                    priority="critical",
                    escalation_hours=4,
                    description="Emergency procurement above threshold requires immediate approval"
                ),
                PolicyRule(
                    name="new_supplier_procurement",
                    condition="supplier_relationship_age < threshold",
                    threshold_value=90.0,  # days
                    threshold_type=ThresholdType.TIME,
                    required_role="manager",
                    priority="medium",
                    escalation_hours=48,
                    description="Procurement from new suppliers requires approval"
                ),
                PolicyRule(
                    name="cost_increase_procurement",
                    condition="cost_increase_percent > threshold",
                    threshold_value=15.0,
                    threshold_type=ThresholdType.PERCENTAGE,
                    required_role="manager",
                    priority="medium",
                    escalation_hours=24,
                    description="Significant cost increases require approval"
                )
            ],
            
            PolicyType.SHIPMENT: [
                PolicyRule(
                    name="high_risk_route",
                    condition="route_risk_score > threshold",
                    threshold_value=7.5,
                    threshold_type=ThresholdType.SCORE,
                    required_role="manager",
                    priority="high",
                    escalation_hours=8,
                    description="High-risk shipping routes require approval"
                ),
                PolicyRule(
                    name="route_deviation",
                    condition="route_deviation_percent > threshold",
                    threshold_value=20.0,
                    threshold_type=ThresholdType.PERCENTAGE,
                    required_role="analyst",
                    priority="medium",
                    escalation_hours=12,
                    description="Significant route deviations require approval"
                ),
                PolicyRule(
                    name="high_value_shipment",
                    condition="cargo_value > threshold",
                    threshold_value=100000.0,
                    threshold_type=ThresholdType.MONETARY,
                    required_role="manager",
                    priority="high",
                    escalation_hours=24,
                    description="High-value shipments require enhanced approval"
                ),
                PolicyRule(
                    name="expedited_shipping",
                    condition="shipping_mode == 'expedited' AND cost_premium > threshold",
                    threshold_value=5000.0,
                    threshold_type=ThresholdType.MONETARY,
                    required_role="analyst",
                    priority="medium",
                    escalation_hours=6,
                    description="Expensive expedited shipping requires approval"
                )
            ],
            
            PolicyType.SUPPLIER: [
                PolicyRule(
                    name="supplier_risk_rating",
                    condition="risk_rating_score > threshold",
                    threshold_value=6.0,
                    threshold_type=ThresholdType.SCORE,
                    required_role="director",
                    priority="high",
                    escalation_hours=48,
                    description="High-risk suppliers require senior approval"
                ),
                PolicyRule(
                    name="supplier_financial_distress",
                    condition="financial_health_score < threshold",
                    threshold_value=3.0,
                    threshold_type=ThresholdType.SCORE,
                    required_role="manager",
                    priority="critical",
                    escalation_hours=24,
                    description="Financially distressed suppliers require immediate review"
                ),
                PolicyRule(
                    name="supplier_performance_decline",
                    condition="performance_trend_percent < threshold",
                    threshold_value=-25.0,
                    threshold_type=ThresholdType.PERCENTAGE,
                    required_role="analyst",
                    priority="medium",
                    escalation_hours=72,
                    description="Declining supplier performance requires review"
                )
            ],
            
            PolicyType.RISK: [
                PolicyRule(
                    name="critical_risk_level",
                    condition="risk_score > threshold",
                    threshold_value=8.5,
                    threshold_type=ThresholdType.SCORE,
                    required_role="director",
                    priority="critical",
                    escalation_hours=2,
                    description="Critical risk levels require immediate escalation"
                ),
                PolicyRule(
                    name="multiple_risk_factors",
                    condition="active_risk_count > threshold",
                    threshold_value=3.0,
                    threshold_type=ThresholdType.COUNT,
                    required_role="manager",
                    priority="high",
                    escalation_hours=12,
                    description="Multiple concurrent risks require management review"
                )
            ],
            
            PolicyType.FINANCIAL: [
                PolicyRule(
                    name="budget_variance",
                    condition="budget_variance_percent > threshold",
                    threshold_value=20.0,
                    threshold_type=ThresholdType.PERCENTAGE,
                    required_role="director",
                    priority="high",
                    escalation_hours=24,
                    description="Significant budget variances require approval"
                ),
                PolicyRule(
                    name="cost_avoidance_opportunity",
                    condition="potential_savings > threshold",
                    threshold_value=10000.0,
                    threshold_type=ThresholdType.MONETARY,
                    required_role="manager",
                    priority="medium",
                    escalation_hours=48,
                    description="Significant cost savings opportunities require review"
                )
            ]
        }
    
    def evaluate_shipment_policies(self, shipment: Shipment) -> List[PolicyViolation]:
        """Evaluate shipment against all applicable policies"""
        violations = []
        
        try:
            # Get shipment context data
            context = self._build_shipment_context(shipment)
            
            # Evaluate shipment-specific policies
            for rule in self.policy_rules[PolicyType.SHIPMENT]:
                violation = self._evaluate_rule(rule, context, shipment)
                if violation.violated:
                    violations.append(violation)
                    
            # Evaluate risk policies for shipment
            for rule in self.policy_rules[PolicyType.RISK]:
                violation = self._evaluate_rule(rule, context, shipment)
                if violation.violated:
                    violations.append(violation)
                    
            # Log policy evaluation
            logger.info(f"Evaluated shipment {shipment.id}: {len(violations)} policy violations")
            
        except Exception as e:
            logger.error(f"Error evaluating shipment policies for {shipment.id}: {e}")
            
        return violations
    
    def evaluate_procurement_policies(self, po: PurchaseOrder) -> List[PolicyViolation]:
        """Evaluate purchase order against procurement policies"""
        violations = []
        
        try:
            # Get procurement context data
            context = self._build_procurement_context(po)
            
            # Evaluate procurement policies
            for rule in self.policy_rules[PolicyType.PROCUREMENT]:
                violation = self._evaluate_rule(rule, context, po)
                if violation.violated:
                    violations.append(violation)
                    
            # Evaluate supplier policies
            if po.supplier:
                supplier_context = self._build_supplier_context(po.supplier)
                for rule in self.policy_rules[PolicyType.SUPPLIER]:
                    violation = self._evaluate_rule(rule, supplier_context, po)
                    if violation.violated:
                        violations.append(violation)
                        
            # Evaluate financial policies
            for rule in self.policy_rules[PolicyType.FINANCIAL]:
                violation = self._evaluate_rule(rule, context, po)
                if violation.violated:
                    violations.append(violation)
                    
            logger.info(f"Evaluated PO {po.id}: {len(violations)} policy violations")
            
        except Exception as e:
            logger.error(f"Error evaluating procurement policies for PO {po.id}: {e}")
            
        return violations
    
    def evaluate_supplier_policies(self, supplier: Supplier) -> List[PolicyViolation]:
        """Evaluate supplier against supplier-specific policies"""
        violations = []
        
        try:
            context = self._build_supplier_context(supplier)
            
            for rule in self.policy_rules[PolicyType.SUPPLIER]:
                violation = self._evaluate_rule(rule, context, supplier)
                if violation.violated:
                    violations.append(violation)
                    
            logger.info(f"Evaluated supplier {supplier.id}: {len(violations)} policy violations")
            
        except Exception as e:
            logger.error(f"Error evaluating supplier policies for {supplier.id}: {e}")
            
        return violations
    
    def trigger_approval_workflow(self, item: Any, policy_violations: List[PolicyViolation]) -> List[DecisionItem]:
        """Create approval workflow items based on policy violations"""
        decision_items = []
        
        try:
            for violation in policy_violations:
                if violation.requires_approval:
                    decision_item = self._create_decision_item(item, violation)
                    decision_items.append(decision_item)
                    
                    # Create policy trigger record
                    self._create_policy_trigger(violation, decision_item)
                    
            # Commit all decision items
            if decision_items:
                db.session.add_all(decision_items)
                db.session.commit()
                logger.info(f"Created {len(decision_items)} approval workflow items")
                
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating approval workflows: {e}")
            
        return decision_items
    
    def check_threshold_violations(self, item: Any, item_type: str = None) -> Dict[str, Any]:
        """Check all threshold violations for a given item"""
        
        # Auto-detect item type if not provided
        if item_type is None:
            if isinstance(item, Shipment):
                item_type = "shipment"
            elif isinstance(item, PurchaseOrder):
                item_type = "purchase_order"
            elif isinstance(item, Supplier):
                item_type = "supplier"
            else:
                item_type = "unknown"
        
        # Get all violations
        all_violations = []
        
        if item_type == "shipment":
            all_violations = self.evaluate_shipment_policies(item)
        elif item_type == "purchase_order":
            all_violations = self.evaluate_procurement_policies(item)
        elif item_type == "supplier":
            all_violations = self.evaluate_supplier_policies(item)
        
        # Categorize violations
        critical_violations = [v for v in all_violations if v.severity == "critical"]
        high_violations = [v for v in all_violations if v.severity == "high"]
        medium_violations = [v for v in all_violations if v.severity == "medium"]
        
        # Calculate risk score
        risk_score = len(critical_violations) * 10 + len(high_violations) * 5 + len(medium_violations) * 2
        
        return {
            "item_type": item_type,
            "item_id": getattr(item, 'id', None),
            "total_violations": len(all_violations),
            "critical_count": len(critical_violations),
            "high_count": len(high_violations),
            "medium_count": len(medium_violations),
            "risk_score": risk_score,
            "requires_approval": len(critical_violations) > 0 or len(high_violations) > 0,
            "violations": [self._violation_to_dict(v) for v in all_violations],
            "recommended_action": self._get_recommended_action(all_violations)
        }
    
    def _build_shipment_context(self, shipment: Shipment) -> Dict[str, Any]:
        """Build context data for shipment policy evaluation"""
        return {
            "cargo_value": getattr(shipment, 'cargo_value', 0),
            "route_risk_score": getattr(shipment, 'risk_score', 0),
            "route_deviation_percent": self._calculate_route_deviation(shipment),
            "shipping_mode": getattr(shipment, 'shipping_mode', 'standard'),
            "cost_premium": self._calculate_shipping_premium(shipment),
            "risk_score": getattr(shipment, 'risk_score', 0),
            "active_risk_count": self._count_active_risks(shipment)
        }
    
    def _build_procurement_context(self, po: PurchaseOrder) -> Dict[str, Any]:
        """Build context data for procurement policy evaluation"""
        return {
            "purchase_amount": getattr(po, 'total_amount', 0),
            "urgency": getattr(po, 'urgency', 'normal'),
            "supplier_relationship_age": self._calculate_supplier_relationship_age(po),
            "cost_increase_percent": self._calculate_cost_increase(po),
            "budget_variance_percent": self._calculate_budget_variance(po),
            "potential_savings": getattr(po, 'potential_savings', 0)
        }
    
    def _build_supplier_context(self, supplier: Supplier) -> Dict[str, Any]:
        """Build context data for supplier policy evaluation"""
        return {
            "risk_rating_score": getattr(supplier, 'risk_rating', 0),
            "financial_health_score": getattr(supplier, 'financial_health', 5),
            "performance_trend_percent": self._calculate_performance_trend(supplier)
        }
    
    def _evaluate_rule(self, rule: PolicyRule, context: Dict[str, Any], item: Any) -> PolicyViolation:
        """Evaluate a single policy rule against context data"""
        
        violated = False
        current_value = 0
        
        try:
            # Extract the relevant value based on rule condition
            if "purchase_amount" in rule.condition:
                current_value = context.get("purchase_amount", 0)
                violated = current_value > rule.threshold_value
                
            elif "route_risk_score" in rule.condition:
                current_value = context.get("route_risk_score", 0)
                violated = current_value > rule.threshold_value
                
            elif "cost_increase_percent" in rule.condition:
                current_value = context.get("cost_increase_percent", 0)
                violated = current_value > rule.threshold_value
                
            elif "risk_rating_score" in rule.condition:
                current_value = context.get("risk_rating_score", 0)
                violated = current_value > rule.threshold_value
                
            elif "financial_health_score" in rule.condition:
                current_value = context.get("financial_health_score", 5)
                violated = current_value < rule.threshold_value
                
            elif "performance_trend_percent" in rule.condition:
                current_value = context.get("performance_trend_percent", 0)
                violated = current_value < rule.threshold_value
                
            elif "budget_variance_percent" in rule.condition:
                current_value = context.get("budget_variance_percent", 0)
                violated = current_value > rule.threshold_value
                
            elif "active_risk_count" in rule.condition:
                current_value = context.get("active_risk_count", 0)
                violated = current_value > rule.threshold_value
                
            elif "cargo_value" in rule.condition:
                current_value = context.get("cargo_value", 0)
                violated = current_value > rule.threshold_value
                
            # Handle complex conditions
            elif "urgency == 'emergency'" in rule.condition and "purchase_amount" in rule.condition:
                urgency = context.get("urgency", "normal")
                purchase_amount = context.get("purchase_amount", 0)
                violated = urgency == "emergency" and purchase_amount > rule.threshold_value
                current_value = purchase_amount
                
            elif "shipping_mode == 'expedited'" in rule.condition and "cost_premium" in rule.condition:
                shipping_mode = context.get("shipping_mode", "standard")
                cost_premium = context.get("cost_premium", 0)
                violated = shipping_mode == "expedited" and cost_premium > rule.threshold_value
                current_value = cost_premium
                
        except Exception as e:
            logger.error(f"Error evaluating rule {rule.name}: {e}")
            violated = False
            
        return PolicyViolation(
            rule_name=rule.name,
            violated=violated,
            current_value=current_value,
            threshold_value=rule.threshold_value,
            severity=rule.priority,
            requires_approval=violated and not rule.auto_approve,
            escalation_deadline=datetime.utcnow() + timedelta(hours=rule.escalation_hours),
            context=context
        )
    
    def _create_decision_item(self, item: Any, violation: PolicyViolation) -> DecisionItem:
        """Create a DecisionItem from a policy violation"""
        
        # Determine item type and reference
        if isinstance(item, Shipment):
            item_type = "shipment"
            title = f"Shipment Policy Violation: {violation.rule_name}"
            description = f"Shipment {item.reference_number} violates {violation.rule_name} policy"
        elif isinstance(item, PurchaseOrder):
            item_type = "purchase_order"
            title = f"Procurement Policy Violation: {violation.rule_name}"
            description = f"Purchase Order {item.reference_number} violates {violation.rule_name} policy"
        elif isinstance(item, Supplier):
            item_type = "supplier"
            title = f"Supplier Policy Violation: {violation.rule_name}"
            description = f"Supplier {item.name} violates {violation.rule_name} policy"
        else:
            item_type = "unknown"
            title = f"Policy Violation: {violation.rule_name}"
            description = f"Item violates {violation.rule_name} policy"
        
        return DecisionItem(
            workspace_id=self.workspace_id,
            decision_type="policy_violation",
            title=title,
            description=description,
            status="pending",
            severity=violation.severity,
            requires_approval=violation.requires_approval,
            approval_deadline=violation.escalation_deadline,
            required_role=self._get_required_role_for_violation(violation),
            related_object_type=item_type,
            related_object_id=getattr(item, 'id', None),
            context_data={
                "policy_rule": violation.rule_name,
                "current_value": violation.current_value,
                "threshold_value": violation.threshold_value,
                "violation_context": violation.context
            },
            estimated_impact_usd=self._estimate_financial_impact(violation),
            risk_if_delayed=f"Policy violation {violation.rule_name} if not addressed by {violation.escalation_deadline}"
        )
    
    def _create_policy_trigger(self, violation: PolicyViolation, decision_item: DecisionItem):
        """Create a PolicyTrigger record"""
        trigger = PolicyTrigger(
            workspace_id=self.workspace_id,
            policy_name=violation.rule_name,
            trigger_condition=f"Value {violation.current_value} exceeds threshold {violation.threshold_value}",
            triggered_at=datetime.utcnow(),
            related_object_type=decision_item.related_object_type,
            related_object_id=decision_item.related_object_id,
            decision_item_id=decision_item.id,
            severity=violation.severity,
            is_active=True,
            auto_resolved=False
        )
        db.session.add(trigger)
    
    # Helper methods for calculations
    def _calculate_route_deviation(self, shipment: Shipment) -> float:
        """Calculate route deviation percentage"""
        # Mock calculation - in reality would compare planned vs actual route
        return getattr(shipment, 'route_deviation_percent', 0)
    
    def _calculate_shipping_premium(self, shipment: Shipment) -> float:
        """Calculate shipping cost premium"""
        # Mock calculation - difference between expedited and standard cost
        return getattr(shipment, 'shipping_premium', 0)
    
    def _count_active_risks(self, shipment: Shipment) -> int:
        """Count active risk factors for shipment"""
        # Mock calculation - count of active alerts/risks
        return Alert.query.filter(
            Alert.related_shipment_id == shipment.id,
            Alert.status == "open"
        ).count()
    
    def _calculate_supplier_relationship_age(self, po: PurchaseOrder) -> float:
        """Calculate supplier relationship age in days"""
        if po.supplier and po.supplier.created_at:
            return (datetime.utcnow() - po.supplier.created_at).days
        return 0
    
    def _calculate_cost_increase(self, po: PurchaseOrder) -> float:
        """Calculate cost increase percentage"""
        # Mock calculation - would compare to historical pricing
        return getattr(po, 'cost_increase_percent', 0)
    
    def _calculate_budget_variance(self, po: PurchaseOrder) -> float:
        """Calculate budget variance percentage"""
        # Mock calculation - compare to budgeted amount
        return getattr(po, 'budget_variance_percent', 0)
    
    def _calculate_performance_trend(self, supplier: Supplier) -> float:
        """Calculate supplier performance trend percentage"""
        # Mock calculation - would analyze historical performance data
        return getattr(supplier, 'performance_trend_percent', 0)
    
    def _get_required_role_for_violation(self, violation: PolicyViolation) -> str:
        """Determine required approval role based on violation severity"""
        severity_role_map = {
            "critical": "director",
            "high": "manager", 
            "medium": "analyst",
            "low": "analyst"
        }
        return severity_role_map.get(violation.severity, "analyst")
    
    def _estimate_financial_impact(self, violation: PolicyViolation) -> float:
        """Estimate financial impact of policy violation"""
        # Simple heuristic based on violation type and value
        if "purchase_amount" in str(violation.context):
            return violation.current_value * 0.05  # 5% of purchase amount
        elif "cargo_value" in str(violation.context):
            return violation.current_value * 0.1   # 10% of cargo value
        else:
            return 5000.0  # Default impact estimate
    
    def _get_recommended_action(self, violations: List[PolicyViolation]) -> str:
        """Get recommended action based on violations"""
        if not violations:
            return "No action required"
        
        critical_count = len([v for v in violations if v.severity == "critical"])
        high_count = len([v for v in violations if v.severity == "high"])
        
        if critical_count > 0:
            return "Immediate escalation required"
        elif high_count > 0:
            return "Management review recommended"
        else:
            return "Standard approval process"
    
    def _violation_to_dict(self, violation: PolicyViolation) -> Dict[str, Any]:
        """Convert PolicyViolation to dictionary"""
        return {
            "rule_name": violation.rule_name,
            "violated": violation.violated,
            "current_value": violation.current_value,
            "threshold_value": violation.threshold_value,
            "severity": violation.severity,
            "requires_approval": violation.requires_approval,
            "escalation_deadline": violation.escalation_deadline.isoformat(),
            "context": violation.context
        }

    def get_policy_performance_metrics(self) -> Dict[str, Any]:
        """Get policy engine performance metrics"""
        try:
            # Get policy trigger statistics
            total_triggers = PolicyTrigger.query.filter(
                PolicyTrigger.workspace_id == self.workspace_id
            ).count()
            
            active_triggers = PolicyTrigger.query.filter(
                PolicyTrigger.workspace_id == self.workspace_id,
                PolicyTrigger.is_active == True
            ).count()
            
            # Get decision statistics
            policy_decisions = DecisionItem.query.filter(
                DecisionItem.workspace_id == self.workspace_id,
                DecisionItem.decision_type == "policy_violation"
            ).count()
            
            resolved_decisions = DecisionItem.query.filter(
                DecisionItem.workspace_id == self.workspace_id,
                DecisionItem.decision_type == "policy_violation",
                DecisionItem.status.in_(["approved", "rejected"])
            ).count()
            
            return {
                "total_policy_triggers": total_triggers,
                "active_policy_triggers": active_triggers,
                "total_policy_decisions": policy_decisions,
                "resolved_policy_decisions": resolved_decisions,
                "resolution_rate": (resolved_decisions / policy_decisions * 100) if policy_decisions > 0 else 0,
                "policy_rules_loaded": sum(len(rules) for rules in self.policy_rules.values())
            }
            
        except Exception as e:
            logger.error(f"Error getting policy performance metrics: {e}")
            return {
                "error": str(e),
                "total_policy_triggers": 0,
                "active_policy_triggers": 0,
                "total_policy_decisions": 0,
                "resolved_policy_decisions": 0,
                "resolution_rate": 0,
                "policy_rules_loaded": 0
            }
