"""
Sample Policy Definitions for Phase 2 Implementation
Creates default policies for testing and demonstration
"""
import json
from datetime import datetime
from app import db
from app.models import Policy

def create_sample_policies(workspace_id: int = 1):
    """Create sample policies for testing the policy engine."""
    
    policies = [
        {
            'name': 'High Value Shipment Approval',
            'type': 'shipment_approval',
            'rules': {
                'applies_to': ['shipment'],
                'conditions': [
                    {
                        'field': 'cargo_value_usd',
                        'operator': '>',
                        'value': 50000
                    }
                ],
                'operator': 'AND',
                'action': {
                    'type': 'require_approval',
                    'reason': 'High value cargo requires management approval',
                    'required_role': 'manager',
                    'urgency': 'medium',
                    'expires_hours': 24,
                    'business_impact_calculation': {
                        'type': 'percentage',
                        'base_field': 'cargo_value_usd',
                        'percentage': 5
                    }
                }
            },
            'priority': 100
        },
        {
            'name': 'High Risk Route Approval',
            'type': 'routing',
            'rules': {
                'applies_to': ['shipment'],
                'conditions': [
                    {
                        'field': 'risk_score',
                        'operator': '>',
                        'value': 0.7
                    }
                ],
                'operator': 'AND',
                'action': {
                    'type': 'require_approval',
                    'reason': 'High risk route requires approval for safety compliance',
                    'required_role': 'director',
                    'urgency': 'high',
                    'expires_hours': 8
                }
            },
            'priority': 200
        },
        {
            'name': 'Large Purchase Order Approval',
            'type': 'spend_approval',
            'rules': {
                'applies_to': ['purchase_order'],
                'conditions': [
                    {
                        'field': 'total_amount',
                        'operator': '>',
                        'value': 25000
                    }
                ],
                'operator': 'AND',
                'action': {
                    'type': 'require_approval',
                    'reason': 'Purchase orders over $25,000 require approval',
                    'required_role': 'manager',
                    'urgency': 'normal',
                    'expires_hours': 48,
                    'business_impact_calculation': {
                        'type': 'fixed',
                        'value': 1000
                    }
                }
            },
            'priority': 150
        },
        {
            'name': 'Critical Purchase Order Approval',
            'type': 'spend_approval',
            'rules': {
                'applies_to': ['purchase_order'],
                'conditions': [
                    {
                        'field': 'total_amount',
                        'operator': '>',
                        'value': 100000
                    }
                ],
                'operator': 'AND',
                'action': {
                    'type': 'require_approval',
                    'reason': 'Purchase orders over $100,000 require director approval',
                    'required_role': 'director',
                    'urgency': 'high',
                    'expires_hours': 12,
                    'business_impact_calculation': {
                        'type': 'percentage',
                        'base_field': 'total_amount',
                        'percentage': 2
                    }
                }
            },
            'priority': 300
        },
        {
            'name': 'Supplier Risk Assessment',
            'type': 'supplier_selection',
            'rules': {
                'applies_to': ['purchase_order'],
                'conditions': [
                    {
                        'field': 'supplier.health_score',
                        'operator': '<',
                        'value': 70
                    }
                ],
                'operator': 'AND',
                'action': {
                    'type': 'require_approval',
                    'reason': 'Supplier health score below threshold requires review',
                    'required_role': 'manager',
                    'urgency': 'medium',
                    'expires_hours': 72
                }
            },
            'priority': 120
        },
        {
            'name': 'AI Recommendation Auto-Approval',
            'type': 'recommendation_approval',
            'rules': {
                'applies_to': ['recommendation'],
                'conditions': [
                    {
                        'field': 'confidence',
                        'operator': '>',
                        'value': 0.95
                    },
                    {
                        'field': 'business_impact_usd',
                        'operator': '<',
                        'value': 5000
                    }
                ],
                'operator': 'AND',
                'action': {
                    'type': 'allow',
                    'reason': 'High confidence, low impact recommendations auto-approved'
                }
            },
            'priority': 50
        },
        {
            'name': 'High Impact AI Recommendation',
            'type': 'recommendation_approval',
            'rules': {
                'applies_to': ['recommendation'],
                'conditions': [
                    {
                        'field': 'business_impact_usd',
                        'operator': '>',
                        'value': 10000
                    }
                ],
                'operator': 'AND',
                'action': {
                    'type': 'require_approval',
                    'reason': 'High business impact recommendations require management approval',
                    'required_role': 'director',
                    'urgency': 'high',
                    'expires_hours': 6
                }
            },
            'priority': 250
        },
        {
            'name': 'Emergency Route Change',
            'type': 'risk_threshold',
            'rules': {
                'applies_to': ['shipment'],
                'conditions': [
                    {
                        'field': 'risk_score',
                        'operator': '>',
                        'value': 0.9
                    },
                    {
                        'field': 'status',
                        'operator': 'in',
                        'value': ['in_transit', 'planned']
                    }
                ],
                'operator': 'AND',
                'action': {
                    'type': 'escalate',
                    'reason': 'Critical risk level requires immediate attention',
                    'required_role': 'director',
                    'urgency': 'critical',
                    'expires_hours': 2
                }
            },
            'priority': 400
        },
        {
            'name': 'Delayed Shipment Review',
            'type': 'delivery_monitoring',
            'rules': {
                'applies_to': ['shipment'],
                'conditions': [
                    {
                        'field': 'status',
                        'operator': '==',
                        'value': 'delayed'
                    }
                ],
                'operator': 'AND',
                'action': {
                    'type': 'require_approval',
                    'reason': 'Delayed shipments require investigation and approval for next steps',
                    'required_role': 'supervisor',
                    'urgency': 'medium',
                    'expires_hours': 12
                }
            },
            'priority': 80
        },
        {
            'name': 'Compliance Check Required',
            'type': 'compliance',
            'rules': {
                'applies_to': ['shipment', 'purchase_order'],
                'conditions': [
                    {
                        'field': 'policy_triggered',
                        'operator': '!=',
                        'value': None
                    }
                ],
                'operator': 'AND',
                'action': {
                    'type': 'require_approval',
                    'reason': 'Items with policy triggers require compliance review',
                    'required_role': 'compliance_officer',
                    'urgency': 'normal',
                    'expires_hours': 48
                }
            },
            'priority': 60
        }
    ]
    
    created_policies = []
    
    for policy_data in policies:
        # Check if policy already exists
        existing = db.session.query(Policy).filter(
            Policy.workspace_id == workspace_id,
            Policy.name == policy_data['name']
        ).first()
        
        if existing:
            print(f"Policy '{policy_data['name']}' already exists, skipping...")
            created_policies.append(existing)
            continue
        
        policy = Policy(
            workspace_id=workspace_id,
            name=policy_data['name'],
            type=policy_data['type'],
            rules=policy_data['rules'],
            is_active=True,
            priority=policy_data['priority'],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.session.add(policy)
        created_policies.append(policy)
        print(f"Created policy: {policy_data['name']}")
    
    try:
        db.session.commit()
        print(f"Successfully created {len([p for p in created_policies if p.id is None])} new policies")
        return created_policies
    except Exception as e:
        db.session.rollback()
        print(f"Error creating policies: {e}")
        raise

if __name__ == '__main__':
    # Can be run standalone to create sample policies
    create_sample_policies()
