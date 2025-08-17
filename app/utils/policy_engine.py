"""
Policy Engine for rule evaluation and enforcement
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from app.models import Policy

logger = logging.getLogger(__name__)

class PolicyEngine:
    """Evaluate and enforce business policies."""
    
    def evaluate(self, policy: Policy, context: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a policy against context."""
        result = {
            'policy_id': policy.id,
            'policy_name': policy.name,
            'passed': True,
            'reason': '',
            'required_action': None
        }
        
        try:
            # Get policy rules
            rules = policy.rules or {}
            
            # Evaluate based on policy type
            if policy.type == 'spend_approval':
                result = self._evaluate_spend_policy(policy, rules, context)
            
            elif policy.type == 'route_change':
                result = self._evaluate_route_policy(policy, rules, context)
            
            elif policy.type == 'supplier_selection':
                result = self._evaluate_supplier_policy(policy, rules, context)
            
            elif policy.type == 'risk_threshold':
                result = self._evaluate_risk_policy(policy, rules, context)
            
            else:
                # Custom rule evaluation
                result = self._evaluate_custom_rules(policy, rules, context)
            
        except Exception as e:
            logger.error(f"Error evaluating policy {policy.id}: {e}")
            result['passed'] = False
            result['reason'] = f"Policy evaluation error: {str(e)}"
        
        return result
    
    def _evaluate_spend_policy(self, policy: Policy, rules: Dict, 
                             context: Dict) -> Dict[str, Any]:
        """Evaluate spend approval policy."""
        result = {
            'policy_id': policy.id,
            'policy_name': policy.name,
            'passed': True,
            'reason': '',
            'required_action': None
        }
        
        amount = context.get('amount', 0)
        approvers = rules.get('approvers', [])
        approver_count = rules.get('count', 1)
        
        # Check if amount exceeds threshold
        for level in rules.get('levels', []):
            if amount > level.get('threshold', 0):
                approvers = level.get('approvers', [])
                approver_count = level.get('count', 1)
                break
        
        # Manual approval required if no approvers found
        if not approvers:
            result['passed'] = False
            result['reason'] = "No approvers found for this policy"
            result['required_action'] = 'manual_approval'
        
        # Check if all required approvers are in the context
        elif context.get('approvers') and len(context.get('approvers')) >= approver_count:
            result['passed'] = True
        else:
            result['passed'] = False
            result['reason'] = f"Requires {approver_count} approvers: {approvers}"
            result['required_action'] = 'manual_approval'
        
        return result
    
    def _evaluate_route_policy(self, policy: Policy, rules: Dict, 
                            context: Dict) -> Dict[str, Any]:
        """Evaluate route change policy."""
        result = {
            'policy_id': policy.id,
            'policy_name': policy.name,
            'passed': True,
            'reason': '',
            'required_action': None
        }
        
        # Check if route change is within allowed limits
        time_delta = context.get('time_delta_hours', 0)
        cost_increase = context.get('cost_increase', 0)
        region = context.get('region', '')
        
        if time_delta > rules.get('max_time_delta_hours', 48):
            result['passed'] = False
            result['reason'] = f"Route change time delta {time_delta}h exceeds limit"
            result['required_action'] = 'manual_approval'
        
        if cost_increase > rules.get('max_cost_increase', 50000):
            result['passed'] = False
            result['reason'] = f"Route change cost increase ${cost_increase} exceeds limit"
            result['required_action'] = 'manual_approval'
        
        if region in rules.get('excluded_regions', []):
            result['passed'] = False
            result['reason'] = f"Route change through excluded region: {region}"
            result['required_action'] = 'manual_approval'
        
        return result
    
    def _evaluate_supplier_policy(self, policy: Policy, rules: Dict, 
                               context: Dict) -> Dict[str, Any]:
        """Evaluate supplier selection policy."""
        result = {
            'policy_id': policy.id,
            'policy_name': policy.name,
            'passed': True,
            'reason': '',
            'required_action': None
        }
        
        supplier_score = context.get('supplier_score', {})
        health_score = supplier_score.get('health', 0)
        reliability_score = supplier_score.get('reliability', 0)
        
        # Check minimum health and reliability scores
        if health_score < rules.get('min_health_score', 0):
            result['passed'] = False
            result['reason'] = f"Supplier health score {health_score} below minimum"
            result['required_action'] = 'manual_approval'
        
        if reliability_score < rules.get('min_reliability_score', 0):
            result['passed'] = False
            result['reason'] = f"Supplier reliability score {reliability_score} below minimum"
            result['required_action'] = 'manual_approval'
        
        # Check for blacklisted suppliers
        blacklisted = rules.get('blacklisted_suppliers', [])
        if context.get('supplier_id') in blacklisted:
            result['passed'] = False
            result['reason'] = "Supplier is blacklisted"
            result['required_action'] = 'manual_approval'
        
        return result
    
    def _evaluate_risk_policy(self, policy: Policy, rules: Dict, 
                            context: Dict) -> Dict[str, Any]:
        """Evaluate risk threshold policy."""
        result = {
            'policy_id': policy.id,
            'policy_name': policy.name,
            'passed': True,
            'reason': '',
            'required_action': None
        }
        
        recommendation = context.get('recommendation')
        if not recommendation:
            return result
        
        # Check severity thresholds
        severity = context.get('severity', '')
        max_auto_severity = rules.get('max_auto_approve_severity', 'medium')
        
        severity_levels = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}
        
        if severity_levels.get(severity, 0) > severity_levels.get(max_auto_severity, 2):
            result['passed'] = False
            result['reason'] = f"Risk severity '{severity}' exceeds auto-approval threshold"
            result['required_action'] = 'manual_approval'
        
        # Check confidence thresholds
        confidence = recommendation.confidence or 0
        min_confidence = rules.get('min_confidence_auto_approve', 0.8)
        
        if confidence < min_confidence:
            result['passed'] = False
            result['reason'] = f"Confidence {confidence:.2f} below minimum {min_confidence}"
            result['required_action'] = 'manual_approval'
        
        return result
    
    def _evaluate_custom_rules(self, policy: Policy, rules: Dict, 
                             context: Dict) -> Dict[str, Any]:
        """Evaluate custom policy rules."""
        result = {
            'policy_id': policy.id,
            'policy_name': policy.name,
            'passed': True,
            'reason': '',
            'required_action': None
        }
        
        # Custom rule engine
        conditions = rules.get('conditions', [])
        
        for condition in conditions:
            field = condition.get('field')
            operator = condition.get('operator')
            value = condition.get('value')
            
            # Get field value from context
            field_value = self._get_field_value(context, field)
            
            # Evaluate condition
            if not self._evaluate_condition(field_value, operator, value):
                result['passed'] = False
                result['reason'] = f"Condition failed: {field} {operator} {value}"
                result['required_action'] = condition.get('action', 'manual_approval')
                break
        
        return result
    
    def _get_field_value(self, context: Dict, field_path: str) -> Any:
        """Get nested field value from context."""
        parts = field_path.split('.')
        value = context
        
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        
        return value
    
    def _evaluate_condition(self, field_value: Any, operator: str, 
                          expected_value: Any) -> bool:
        """Evaluate a single condition."""
        try:
            if operator == 'equals':
                return field_value == expected_value
            elif operator == 'not_equals':
                return field_value != expected_value
            elif operator == 'greater_than':
                return float(field_value) > float(expected_value)
            elif operator == 'less_than':
                return float(field_value) < float(expected_value)
            elif operator == 'contains':
                return expected_value in str(field_value)
            elif operator == 'in':
                return field_value in expected_value
            else:
                logger.warning(f"Unknown operator: {operator}")
                return True
        except Exception as e:
            logger.error(f"Error evaluating condition: {e}")
            return False
    
    def check_all_policies(self, policy_type: str, context: Dict) -> List[Dict]:
        """Check all active policies of a given type."""
        from app import db
        
        results = []
        
        try:
            # Get all active policies of this type
            policies = Policy.query.filter_by(
                type=policy_type,
                is_active=True
            ).order_by(Policy.priority.desc()).all()
            
            for policy in policies:
                result = self.evaluate(policy, context)
                results.append(result)
                
                # Stop on first failure if policy is blocking
                if not result['passed'] and policy.enforcement == 'blocking':
                    break
            
        except Exception as e:
            logger.error(f"Error checking policies: {e}")
        
        return results
    
    def create_default_policies(self, workspace_id: int):
        """Create default policies for a workspace."""
        from app import db
        
        default_policies = [
            {
                'name': 'Spend Approval Levels',
                'type': 'spend_approval',
                'description': 'Approval thresholds for purchase orders',
                'rules': {
                    'levels': [
                        {
                            'threshold': 10000,
                            'approvers': ['procurement_manager'],
                            'count': 1
                        },
                        {
                            'threshold': 50000,
                            'approvers': ['procurement_manager', 'finance_manager'],
                            'count': 2
                        },
                        {
                            'threshold': 100000,
                            'approvers': ['procurement_director', 'cfo'],
                            'count': 2
                        }
                    ]
                },
                'priority': 100,
                'enforcement': 'blocking'
            },
            {
                'name': 'High Risk Route Changes',
                'type': 'route_change',
                'description': 'Require approval for significant route changes',
                'rules': {
                    'max_time_delta_hours': 48,
                    'max_cost_increase': 50000,
                    'excluded_regions': ['North Korea', 'Iran']
                },
                'priority': 90,
                'enforcement': 'blocking'
            },
            {
                'name': 'Supplier Health Requirements',
                'type': 'supplier_selection',
                'description': 'Minimum supplier scores for auto-approval',
                'rules': {
                    'min_health_score': 70,
                    'min_reliability_score': 80,
                    'blacklisted_suppliers': []
                },
                'priority': 80,
                'enforcement': 'warning'
            },
            {
                'name': 'Risk Auto-Approval Limits',
                'type': 'risk_threshold',
                'description': 'Risk levels requiring manual approval',
                'rules': {
                    'max_auto_approve_severity': 'medium',
                    'min_confidence_auto_approve': 0.8
                },
                'priority': 70,
                'enforcement': 'blocking'
            }
        ]
        
        try:
            for policy_data in default_policies:
                policy = Policy(
                    workspace_id=workspace_id,
                    **policy_data
                )
                db.session.add(policy)
            
            db.session.commit()
            logger.info(f"Created {len(default_policies)} default policies for workspace {workspace_id}")
            
        except Exception as e:
            logger.error(f"Error creating default policies: {e}")
            db.session.rollback()