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
    
    def evaluate_shipment_policies(self, shipment_data: Dict[str, Any]) -> List[PolicyViolation]:
        """Evaluate shipment against all applicable policies"""
        violations = []
        
        try:
            # Build context from shipment data
            context = {
                "cargo_value": shipment_data.get('total_cost', 0),
                "route_risk_score": shipment_data.get('risk_score', 0),
                "route_deviation_percent": shipment_data.get('route_deviation_percent', 0),
                "shipping_mode": shipment_data.get('shipping_mode', 'standard'),
                "cost_premium": shipment_data.get('cost_premium', 0),
                "risk_score": shipment_data.get('risk_score', 0),
                "active_risk_count": shipment_data.get('active_risk_count', 0)
            }
            
            # Evaluate shipment-specific policies
            for rule in self.policy_rules[PolicyType.SHIPMENT]:
                violation = self._evaluate_rule(rule, context)
                if violation.violated:
                    violations.append(violation)
                    
            # Evaluate risk policies for shipment
            for rule in self.policy_rules[PolicyType.RISK]:
                violation = self._evaluate_rule(rule, context)
                if violation.violated:
                    violations.append(violation)
                    
            logger.info(f"Evaluated shipment policies: {len(violations)} violations found")
            
        except Exception as e:
            logger.error(f"Error evaluating shipment policies: {e}")
            
        return violations
    
    def evaluate_procurement_policies(self, po_data: Dict[str, Any]) -> List[PolicyViolation]:
        """Evaluate purchase order against procurement policies"""
        violations = []
        
        try:
            # Build context from procurement data
            context = {
                "purchase_amount": po_data.get('total_amount', 0),
                "urgency": po_data.get('urgency', 'normal'),
                "supplier_relationship_age": po_data.get('supplier_relationship_age', 365),
                "cost_increase_percent": po_data.get('cost_increase_percent', 0),
                "budget_variance_percent": po_data.get('budget_variance_percent', 0),
                "potential_savings": po_data.get('potential_savings', 0)
            }
            
            # Evaluate procurement policies
            for rule in self.policy_rules[PolicyType.PROCUREMENT]:
                violation = self._evaluate_rule(rule, context)
                if violation.violated:
                    violations.append(violation)
                    
            # Evaluate financial policies
            for rule in self.policy_rules[PolicyType.FINANCIAL]:
                violation = self._evaluate_rule(rule, context)
                if violation.violated:
                    violations.append(violation)
                    
            logger.info(f"Evaluated procurement policies: {len(violations)} violations found")
            
        except Exception as e:
            logger.error(f"Error evaluating procurement policies: {e}")
            
        return violations
    
    def check_threshold_violations(self, workspace_id: int = None) -> List[Dict[str, Any]]:
        """Check threshold violations across the workspace"""
        violations = []
        
        try:
            # Mock implementation - in real system would check various thresholds
            violation_data = [
                {
                    "type": "financial",
                    "description": "Monthly budget variance exceeds 20%",
                    "current_value": 25.5,
                    "threshold": 20.0,
                    "severity": "high"
                },
                {
                    "type": "risk",
                    "description": "Average risk score above acceptable level",
                    "current_value": 7.8,
                    "threshold": 7.0,
                    "severity": "medium"
                }
            ]
            
            violations.extend(violation_data)
            
        except Exception as e:
            logger.error(f"Error checking threshold violations: {e}")
            
        return violations
    
    def trigger_approval_workflow(self, item_data: Dict[str, Any], violations: List[PolicyViolation]) -> List[Dict[str, Any]]:
        """Trigger approval workflows based on policy violations"""
        workflows = []
        
        try:
            for violation in violations:
                if violation.requires_approval:
                    workflow = {
                        "type": "approval_required",
                        "rule_name": violation.rule_name,
                        "severity": violation.severity,
                        "escalation_deadline": violation.escalation_deadline,
                        "item_data": item_data,
                        "violation_context": violation.context
                    }
                    workflows.append(workflow)
                    
            logger.info(f"Triggered {len(workflows)} approval workflows")
            
        except Exception as e:
            logger.error(f"Error triggering approval workflows: {e}")
            
        return workflows
    
    def _evaluate_rule(self, rule: PolicyRule, context: Dict[str, Any]) -> PolicyViolation:
        """Evaluate a single policy rule against context data"""
        
        violated = False
        current_value = 0
        
        try:
            # Extract the relevant value based on rule condition
            if "purchase_amount" in rule.condition:
                current_value = context.get("purchase_amount", 0)
                if "urgency == 'emergency'" in rule.condition:
                    violated = context.get("urgency") == "emergency" and current_value > rule.threshold_value
                else:
                    violated = current_value > rule.threshold_value
                
            elif "route_risk_score" in rule.condition:
                current_value = context.get("route_risk_score", 0)
                violated = current_value > rule.threshold_value
                
            elif "cost_increase_percent" in rule.condition:
                current_value = context.get("cost_increase_percent", 0)
                violated = current_value > rule.threshold_value
                
            elif "supplier_relationship_age" in rule.condition:
                current_value = context.get("supplier_relationship_age", 365)
                violated = current_value < rule.threshold_value
                
            elif "budget_variance_percent" in rule.condition:
                current_value = context.get("budget_variance_percent", 0)
                violated = current_value > rule.threshold_value
                
            elif "cargo_value" in rule.condition:
                current_value = context.get("cargo_value", 0)
                violated = current_value > rule.threshold_value
                
            elif "risk_score" in rule.condition:
                current_value = context.get("risk_score", 0)
                violated = current_value > rule.threshold_value
                
            elif "active_risk_count" in rule.condition:
                current_value = context.get("active_risk_count", 0)
                violated = current_value > rule.threshold_value
                
            elif "potential_savings" in rule.condition:
                current_value = context.get("potential_savings", 0)
                violated = current_value > rule.threshold_value
                
            # Handle complex shipping conditions
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
    
    def _should_trigger_workflow(self, item_data: Dict[str, Any], workflow_type: str) -> bool:
        """Determine if a workflow should be triggered"""
        try:
            if workflow_type == "high_risk_shipment":
                return item_data.get("risk_score", 0) > 7.0
            elif workflow_type == "high_value_procurement":
                return item_data.get("total_amount", 0) > 50000
            elif workflow_type == "new_supplier_review":
                return item_data.get("supplier_relationship_age", 365) < 90
            else:
                return False
        except Exception as e:
            logger.error(f"Error checking workflow trigger: {e}")
            return False
    
    def get_policy_performance_metrics(self) -> Dict[str, Any]:
        """Get policy engine performance metrics"""
        try:
            return {
                "total_policy_rules": sum(len(rules) for rules in self.policy_rules.values()),
                "policy_types": len(self.policy_rules),
                "workspace_id": self.workspace_id,
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting policy performance metrics: {e}")
            return {
                "error": str(e),
                "total_policy_rules": 0,
                "policy_types": 0,
                "workspace_id": self.workspace_id,
                "last_updated": datetime.utcnow().isoformat()
            }
