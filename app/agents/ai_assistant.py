"""
Enhanced AI Assistant with LangChain integration and multi-agent communication
"""
import logging
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from flask import current_app
from sqlalchemy import text

from app.models import (
    Shipment, Supplier, Alert, Recommendation, 
    Route, Risk, SupplierRiskAssessment, User,
    ShipmentStatus, PurchaseOrder, Inventory
)
from app.integrations.watsonx_client import WatsonxClient
from app.agents.communicator import AgentCommunicator

logger = logging.getLogger(__name__)

class EnhancedAIAssistant:
    """
    Enhanced AI Assistant with LangChain-style agent orchestration
    and comprehensive supply chain intelligence
    """
    
    def __init__(self):
        self.watsonx = WatsonxClient()
        self.communicator = AgentCommunicator()
        self.tools = self._initialize_tools()
        self.agent_capabilities = {
            'risk_predictor': ['weather_analysis', 'geopolitical_assessment', 'supplier_risk'],
            'route_optimizer': ['route_analysis', 'cost_optimization', 'eta_prediction'],
            'procurement_agent': ['supplier_evaluation', 'po_generation', 'inventory_management'],
            'orchestrator': ['workflow_coordination', 'policy_enforcement', 'approval_management']
        }
        
    def initialize_user_context(self, user_id):
        """Initialize user context for the assistant"""
        from app.models import User, Workspace
        from app import db
        
        user = User.query.get(user_id)
        if not user:
            return {}
            
        # Get user's workspace
        workspace = user.workspace if user.workspace else None
        
        return {
            'user_id': user.id,
            'email': user.email,
            'workspace_id': workspace.id if workspace else None,
            'workspace_name': workspace.name if workspace else None,
            'preferences': user.preferences if hasattr(user, 'preferences') else {},
            'context_initialized': True
        }
        
    def _initialize_tools(self):
        """Initialize available tools for the assistant"""
        return {
            'get_shipments': self.get_shipments_data,
            'get_suppliers': self.get_suppliers_data,
            'get_alerts': self.get_alerts_data,
            'get_recommendations': self.get_recommendations_data,
            'get_inventory': self.get_inventory_data,
            'get_risk_assessment': self.get_risk_assessment_data,
            'get_routes': self.get_routes_data,
            'get_purchase_orders': self.get_purchase_orders_data,
            'analyze_performance': self.analyze_performance_data,
            'query_agent': self.query_specific_agent,
            'execute_action': self.execute_assistant_action
        }
    
    async def process_message(self, message: str, context: Dict[str, Any], 
                            conversation_history: List[Dict]) -> Dict[str, Any]:
        """
        Main message processing with agent orchestration
        """
        try:
            # Analyze the message intent
            intent = await self._analyze_intent(message)
            logger.info(f"Analyzed intent: {intent}")
            
            # Gather relevant data based on intent
            context_data = await self._gather_context_data(intent, context)
            
            # Query relevant agents if needed
            agent_responses = await self._query_relevant_agents(intent, message, context_data)
            
            # Generate comprehensive response
            response = await self._generate_response(
                message, intent, context_data, agent_responses, conversation_history
            )
            
            # Extract and validate actions
            actions = self._extract_actions(intent, message, context)
            
            return {
                'message': response,
                'actions': actions,
                'context_update': {
                    'description': f'{intent.get("category", "General")} inquiry processed',
                    'intent': intent,
                    'timestamp': datetime.utcnow().isoformat()
                },
                'agent_responses': agent_responses,
                'confidence': intent.get('confidence', 0.8),
                'tools_used': intent.get('tools_required', [])
            }
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return self._generate_error_response(message)
    
    async def _analyze_intent(self, message: str) -> Dict[str, Any]:
        """Analyze user message intent using AI"""
        
        intent_prompt = f"""
Analyze the following supply chain management query and extract:
1. Primary category: shipments, procurement, risk, analytics, general
2. Specific intent: tracking, optimization, alerts, reporting, etc.
3. Entities mentioned: shipment IDs, supplier names, locations, etc.
4. Tools required: data queries, agent consultation, actions
5. Confidence score: 0-1

Query: "{message}"

Respond in JSON format:
{{
    "category": "category_name",
    "intent": "specific_intent",
    "entities": ["entity1", "entity2"],
    "tools_required": ["tool1", "tool2"],
    "confidence": 0.9,
    "urgency": "low|medium|high",
    "requires_agent_consultation": true/false
}}
"""
        
        try:
            response = self.watsonx.generate(
                prompt=intent_prompt,
                temperature=0.3,
                max_tokens=200
            )
            
            # Parse JSON response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                intent_data = json.loads(json_match.group())
                return intent_data
            
        except Exception as e:
            logger.warning(f"Error analyzing intent: {e}")
        
        # Fallback intent analysis
        return self._fallback_intent_analysis(message)
    
    def _fallback_intent_analysis(self, message: str) -> Dict[str, Any]:
        """Fallback intent analysis using keyword matching"""
        message_lower = message.lower()
        
        # Category detection
        if any(word in message_lower for word in ['shipment', 'tracking', 'delivery', 'eta']):
            category = 'shipments'
            intent = 'tracking'
        elif any(word in message_lower for word in ['supplier', 'procurement', 'purchase', 'po']):
            category = 'procurement'
            intent = 'management'
        elif any(word in message_lower for word in ['risk', 'alert', 'threat', 'warning']):
            category = 'risk'
            intent = 'monitoring'
        elif any(word in message_lower for word in ['report', 'analytics', 'performance', 'kpi']):
            category = 'analytics'
            intent = 'reporting'
        else:
            category = 'general'
            intent = 'information'
        
        # Extract entities (simple approach)
        entities = []
        import re
        # Look for shipment references
        shipment_refs = re.findall(r'\b[A-Z]{2,3}-\d+\b', message)
        entities.extend(shipment_refs)
        
        return {
            'category': category,
            'intent': intent,
            'entities': entities,
            'tools_required': [f'get_{category}'],
            'confidence': 0.7,
            'urgency': 'medium',
            'requires_agent_consultation': category in ['risk', 'procurement']
        }
    
    async def _gather_context_data(self, intent: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Gather relevant data based on intent"""
        data = {}
        
        try:
            category = intent.get('category', 'general')
            tools_required = intent.get('tools_required', [])
            
            # Execute required tools
            for tool in tools_required:
                if tool in self.tools:
                    data[tool] = await self._execute_tool(tool, intent, context)
            
            # Always include recent activity for context
            data['recent_activity'] = {
                'shipments': self.get_shipments_data(limit=5),
                'alerts': self.get_alerts_data(limit=3),
                'recommendations': self.get_recommendations_data(limit=3)
            }
            
            return data
            
        except Exception as e:
            logger.error(f"Error gathering context data: {e}")
            return {'error': str(e)}
    
    async def _execute_tool(self, tool_name: str, intent: Dict, context: Dict) -> Any:
        """Execute a specific tool and return results"""
        try:
            tool_func = self.tools.get(tool_name)
            if tool_func:
                # Pass relevant parameters based on intent
                if 'entities' in intent and intent['entities']:
                    return tool_func(entities=intent['entities'])
                else:
                    return tool_func()
            return None
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return None
    
    async def _query_relevant_agents(self, intent: Dict, message: str, context_data: Dict) -> List[Dict]:
        """Query specific agents based on intent"""
        agent_responses = []
        
        if not intent.get('requires_agent_consultation', False):
            return agent_responses
        
        try:
            category = intent.get('category')
            
            # Determine which agents to consult
            agents_to_query = []
            if category == 'risk':
                agents_to_query = ['risk_predictor']
            elif category == 'shipments':
                agents_to_query = ['route_optimizer']
            elif category == 'procurement':
                agents_to_query = ['procurement_agent']
            elif intent.get('urgency') == 'high':
                agents_to_query = ['orchestrator']
            
            # Query each relevant agent
            for agent_name in agents_to_query:
                response = await self._query_agent(agent_name, message, context_data)
                if response:
                    agent_responses.append({
                        'agent_name': agent_name,
                        'response': response,
                        'capabilities': self.agent_capabilities.get(agent_name, [])
                    })
            
            return agent_responses
            
        except Exception as e:
            logger.error(f"Error querying agents: {e}")
            return agent_responses
    
    async def _query_agent(self, agent_name: str, message: str, context_data: Dict) -> Optional[str]:
        """Query a specific agent"""
        try:
            # Create agent-specific prompt
            agent_prompt = f"""
As the {agent_name} in the SupplyChain system, analyze this request:
"{message}"

Context data available:
{json.dumps(context_data, indent=2, default=str)}

Provide a brief expert response focusing on your specialty:
- risk_predictor: Risk assessment and threat analysis
- route_optimizer: Route optimization and logistics
- procurement_agent: Supplier evaluation and procurement
- orchestrator: Workflow coordination and recommendations

Response (max 100 words):
"""
            
            response = self.watsonx.generate(
                prompt=agent_prompt,
                temperature=0.5,
                max_tokens=150
            )
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error querying agent {agent_name}: {e}")
            return None
    
    async def _generate_response(self, message: str, intent: Dict, context_data: Dict, 
                               agent_responses: List[Dict], history: List[Dict]) -> str:
        """Generate comprehensive AI response"""
        
        # Build comprehensive prompt
        response_prompt = f"""
You are an intelligent supply chain assistant for SupplyChainX. Based on the analysis below, provide a helpful, accurate response.

USER QUERY: "{message}"

INTENT ANALYSIS:
- Category: {intent.get('category')}
- Intent: {intent.get('intent')}
- Confidence: {intent.get('confidence')}
- Urgency: {intent.get('urgency')}

CURRENT DATA:
{json.dumps(context_data, indent=2, default=str)}

AGENT CONSULTATIONS:
{chr(10).join([f"- {ar['agent_name']}: {ar['response']}" for ar in agent_responses])}

CONVERSATION HISTORY:
{chr(10).join([f"{h['sender']}: {h['message']}" for h in history[-3:]])}

Guidelines for response:
- If this is a greeting (hello, hi, hey), be warm and welcoming, introduce yourself as the SupplyChainX AI assistant
- If this is a conversational message (thank you, how are you), respond naturally and offer help
- For supply chain questions, provide specific data and actionable insights
- Keep responses conversational but professional
- Suggest relevant actions when appropriate
- Maximum 3 paragraphs

Response:
"""
        
        try:
            response = self.watsonx.generate(
                prompt=response_prompt,
                temperature=0.7,
                max_tokens=400
            )
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return self._generate_fallback_response_text(message, intent, context_data)
    
    def _generate_fallback_response_text(self, message: str, intent: Dict, context_data: Dict) -> str:
        """Generate fallback response when AI is unavailable"""
        category = intent.get('category', 'general')
        message_lower = message.lower().strip()
        
        # Handle conversational greetings and common phrases
        if any(greeting in message_lower for greeting in ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening']):
            recent_shipments = context_data.get('recent_activity', {}).get('shipments', [])
            recent_alerts = context_data.get('recent_activity', {}).get('alerts', [])
            shipment_count = len(recent_shipments) if recent_shipments else 0
            alert_count = len(recent_alerts) if recent_alerts else 0
            
            return f"Hello! Welcome to SupplyChainX. I'm your AI assistant and I'm here to help you manage your supply chain operations. Currently, you have {shipment_count} recent shipments and {alert_count} active alerts. I can help you with shipment tracking, supplier management, risk monitoring, and analytics. What would you like to know about?"
        
        elif any(phrase in message_lower for phrase in ['thank you', 'thanks', 'thx']):
            return "You're welcome! I'm always here to help with your supply chain needs. Is there anything else you'd like to know about your shipments, suppliers, or operations?"
            
        elif any(phrase in message_lower for phrase in ['how are you', 'how do you do', 'what\'s up']):
            return "I'm doing great and ready to help! I'm continuously monitoring your supply chain operations and I'm here to assist with any questions about shipments, procurement, risk management, or analytics. What can I help you with today?"
        
        if category == 'shipments':
            recent_shipments = context_data.get('recent_activity', {}).get('shipments', [])
            count = len(recent_shipments) if recent_shipments else 0
            return f"I can help you with shipment tracking and logistics. You currently have {count} recent shipments in the system. I can provide details on status, routes, and ETAs."
            
        elif category == 'procurement':
            return "I can assist with procurement management, including supplier evaluation, purchase order tracking, and inventory monitoring. What specific procurement information do you need?"
            
        elif category == 'risk':
            recent_alerts = context_data.get('recent_activity', {}).get('alerts', [])
            count = len(recent_alerts) if recent_alerts else 0
            return f"I can help monitor supply chain risks and threats. There are currently {count} active alerts in the system. I can provide risk assessments and mitigation recommendations."
            
        else:
            return f"I understand you're asking about '{message}'. I can help with shipment tracking, procurement management, risk monitoring, and supply chain analytics. What specific area would you like to explore?"
    
    def _extract_actions(self, intent: Dict, message: str, context: Dict) -> List[Dict]:
        """Extract suggested actions based on intent"""
        actions = []
        category = intent.get('category')
        
        if category == 'shipments':
            actions.append({
                'type': 'navigate',
                'data': '/logistics',
                'label': 'View Shipments Dashboard'
            })
            
            # If specific shipment mentioned, add direct action
            entities = intent.get('entities', [])
            for entity in entities:
                if '-' in entity:  # Likely a shipment reference
                    actions.append({
                        'type': 'search_shipment',
                        'data': entity,
                        'label': f'Find Shipment {entity}'
                    })
        
        elif category == 'procurement':
            actions.append({
                'type': 'navigate',
                'data': '/procurement',
                'label': 'View Procurement Dashboard'
            })
            actions.append({
                'type': 'navigate',
                'data': '/suppliers',
                'label': 'Manage Suppliers'
            })
        
        elif category == 'risk':
            actions.append({
                'type': 'navigate',
                'data': '/risk',
                'label': 'View Risk Dashboard'
            })
            actions.append({
                'type': 'navigate',
                'data': '/alerts',
                'label': 'View Active Alerts'
            })
        
        elif category == 'analytics':
            actions.append({
                'type': 'navigate',
                'data': '/reports',
                'label': 'View Analytics Reports'
            })
            actions.append({
                'type': 'export_report',
                'data': {'type': 'performance', 'format': 'pdf'},
                'label': 'Export Performance Report'
            })
        
        # Always add general navigation options
        if intent.get('urgency') == 'high':
            actions.append({
                'type': 'show_recommendations',
                'data': {'filter': 'urgent'},
                'label': 'View Urgent Recommendations'
            })
        
        return actions
    
    def _generate_error_response(self, message: str) -> Dict[str, Any]:
        """Generate error response"""
        return {
            'message': f"I apologize, but I encountered an error processing your request about '{message[:50]}...'. Please try rephrasing your question or contact support if the issue persists.",
            'actions': [
                {'type': 'navigate', 'data': '/dashboard', 'label': 'Return to Dashboard'},
                {'type': 'navigate', 'data': '/help', 'label': 'Get Help'}
            ],
            'context_update': {'description': 'Error occurred'},
            'agent_responses': [],
            'confidence': 0.0,
            'tools_used': []
        }
    
    # Data retrieval tools
    def get_shipments_data(self, limit: int = 10, entities: List[str] = None) -> List[Dict]:
        """Get shipments data"""
        try:
            query = Shipment.query
            
            # Filter by entities if provided
            if entities:
                query = query.filter(Shipment.reference_number.in_(entities))
            
            shipments = query.order_by(Shipment.created_at.desc()).limit(limit).all()
            
            return [{
                'id': s.id,
                'reference': s.reference_number,
                'origin': s.origin_port,
                'destination': s.destination_port,
                'status': s.status if s.status else 'unknown',  # status is now a string
                'carrier': s.carrier,
                'created_at': s.created_at.isoformat() if s.created_at else None
            } for s in shipments]
            
        except Exception as e:
            logger.error(f"Error getting shipments data: {e}")
            return []
    
    def get_suppliers_data(self, limit: int = 10, entities: List[str] = None) -> List[Dict]:
        """Get suppliers data"""
        try:
            query = Supplier.query
            
            # Filter by entities if provided
            if entities:
                query = query.filter(Supplier.name.ilike(f'%{entities[0]}%'))
            
            suppliers = query.order_by(Supplier.name).limit(limit).all()
            
            return [{
                'id': s.id,
                'name': s.name,
                'country': s.country,
                'status': s.status if s.status else 'unknown',  # status is now a string
                'reliability_score': float(s.reliability_score) if s.reliability_score else 0.0,
                'performance_rating': float(s.quality_rating) if s.quality_rating else 0.0  # Use quality_rating instead
            } for s in suppliers]
            
        except Exception as e:
            logger.error(f"Error getting suppliers data: {e}")
            return []
    
    def get_alerts_data(self, limit: int = 10, entities: List[str] = None) -> List[Dict]:
        """Get alerts data"""
        try:
            query = Alert.query.filter_by(status='open')
            alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()
            
            return [{
                'id': a.id,
                'title': a.title,
                'severity': a.severity if a.severity else 'unknown',  # severity is now a string
                'type': a.type if a.type else 'unknown',  # Use 'type' field instead of 'alert_type'
                'created_at': a.created_at.isoformat() if a.created_at else None,
                'description': a.description
            } for a in alerts]
            
        except Exception as e:
            logger.error(f"Error getting alerts data: {e}")
            return []
    
    def get_recommendations_data(self, limit: int = 10, entities: List[str] = None) -> List[Dict]:
        """Get recommendations data"""
        try:
            query = Recommendation.query.filter_by(status='PENDING')
            recommendations = query.order_by(Recommendation.created_at.desc()).limit(limit).all()
            
            return [{
                'id': r.id,
                'title': r.title,
                'type': r.type,
                'severity': r.severity,
                'confidence': float(r.confidence) if r.confidence else 0.0,
                'created_at': r.created_at.isoformat() if r.created_at else None,
                'description': r.description
            } for r in recommendations]
            
        except Exception as e:
            logger.error(f"Error getting recommendations data: {e}")
            return []
    
    def get_inventory_data(self, limit: int = 10, entities: List[str] = None) -> List[Dict]:
        """Get inventory data (backward compatible with older schema)."""
        try:
            query = Inventory.query
            if entities:
                query = query.filter(Inventory.sku.in_(entities))
            inventory = query.order_by(Inventory.sku).limit(limit).all()
            items = []
            for i in inventory:
                product_name = getattr(i, 'product_name', None) or getattr(i, 'description', None)
                items.append({
                    'id': i.id,
                    'sku': i.sku,
                    'product_name': product_name,
                    'quantity_on_hand': float(i.quantity_on_hand) if getattr(i, 'quantity_on_hand', None) else 0.0,
                    'reorder_point': float(i.reorder_point) if getattr(i, 'reorder_point', None) else 0.0,
                    'unit_cost': float(i.unit_cost) if getattr(i, 'unit_cost', None) else 0.0,
                    'supplier_id': getattr(i, 'supplier_id', None)
                })
            return items
        except Exception as e:
            logger.error(f"Error getting inventory data: {e}")
            return []

    def get_risk_assessment_data(self, limit: int = 10, entities: List[str] = None) -> List[Dict]:
        """Get risk assessment data using Risk model (legacy compatibility)."""
        try:
            # Prefer Risk model which exists in current schema
            from app.models import Risk  # local import to avoid circular
            query = Risk.query
            risks = query.order_by(Risk.created_at.desc()).limit(limit).all() if hasattr(Risk, 'created_at') else query.limit(limit).all()
            results = []
            for r in risks:
                results.append({
                    'id': r.id,
                    'risk_type': getattr(r, 'risk_type', 'unknown'),
                    'severity': getattr(r, 'severity', 'unknown'),
                    'probability': float(getattr(r, 'probability', 0.0) or 0.0),
                    'impact_score': float(getattr(r, 'risk_score', 0.0) or 0.0),  # map risk_score as impact proxy
                    'created_at': getattr(r, 'created_at', None).isoformat() if getattr(r, 'created_at', None) else None,
                    'description': getattr(r, 'description', None)
                })
            return results
        except Exception as e:
            logger.error(f"Error getting risk assessment data: {e}")
            return []
    
    def get_routes_data(self, limit: int = 10, entities: List[str] = None) -> List[Dict]:
        """Get routes data"""
        try:
            query = Route.query
            routes = query.order_by(Route.created_at.desc()).limit(limit).all()
            
            return [{
                'id': r.id,
                'shipment_id': r.shipment_id,
                'route_type': r.route_type,
                'waypoints': json.loads(r.waypoints) if r.waypoints else [],
                'cost_usd': float(r.cost_usd) if r.cost_usd else 0.0,
                'distance_km': float(r.distance_km) if r.distance_km else 0.0,
                'estimated_duration_hours': float(r.estimated_duration_hours) if r.estimated_duration_hours else 0.0,
                'risk_score': float(r.risk_score) if r.risk_score else 0.0,
                'is_current': r.is_current,
                'is_recommended': r.is_recommended,
                'risk_factors': json.loads(r.risk_factors) if r.risk_factors else []
            } for r in routes]
            
        except Exception as e:
            logger.error(f"Error getting routes data: {e}")
            return []
    
    def get_purchase_orders_data(self, limit: int = 10, entities: List[str] = None) -> List[Dict]:
        """Get purchase orders data"""
        try:
            query = PurchaseOrder.query
            
            # Filter by entities if provided (PO numbers)
            if entities:
                query = query.filter(PurchaseOrder.po_number.in_(entities))
            
            pos = query.order_by(PurchaseOrder.created_at.desc()).limit(limit).all()
            
            return [{
                'id': po.id,
                'po_number': po.po_number,
                'supplier_id': po.supplier_id,
                'status': po.status if po.status else 'unknown',  # status is now a string
                'total_amount': float(po.total_amount) if po.total_amount else 0.0,
                'currency': po.currency,
                'created_at': po.created_at.isoformat() if po.created_at else None,
                'delivery_date': po.delivery_date.isoformat() if po.delivery_date else None
            } for po in pos]
            
        except Exception as e:
            logger.error(f"Error getting purchase orders data: {e}")
            return []
    
    def analyze_performance_data(self, entities: List[str] = None) -> Dict[str, Any]:
        """Analyze overall performance data"""
        try:
            # Get performance metrics
            total_shipments = Shipment.query.count()
            active_alerts = Alert.query.filter_by(status='open').count()
            pending_recommendations = Recommendation.query.filter_by(status='PENDING').count()
            total_suppliers = Supplier.query.count()
            
            # Calculate some basic metrics
            recent_shipments = Shipment.query.filter(
                Shipment.created_at >= datetime.utcnow() - timedelta(days=30)
            ).count()
            
            high_risk_alerts = Alert.query.filter_by(
                status='open', severity='HIGH'
            ).count()
            
            return {
                'total_shipments': total_shipments,
                'recent_shipments_30d': recent_shipments,
                'active_alerts': active_alerts,
                'high_risk_alerts': high_risk_alerts,
                'pending_recommendations': pending_recommendations,
                'total_suppliers': total_suppliers,
                'calculated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing performance data: {e}")
            return {'error': str(e)}
    
    def query_specific_agent(self, agent_name: str, query: str) -> Dict[str, Any]:
        """Query a specific agent directly"""
        try:
            # This would integrate with the actual agent system
            # For now, return a mock response
            return {
                'agent': agent_name,
                'query': query,
                'response': f"Agent {agent_name} response to: {query}",
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error querying agent {agent_name}: {e}")
            return {'error': str(e)}
    
    def execute_assistant_action(self, action_type: str, action_data: Any) -> Dict[str, Any]:
        """Execute an action requested by the assistant"""
        try:
            if action_type == 'create_alert':
                # Create a new alert
                return {'success': True, 'message': 'Alert created successfully'}
            elif action_type == 'update_status':
                # Update status of an entity
                return {'success': True, 'message': 'Status updated successfully'}
            else:
                return {'success': False, 'message': f'Unknown action type: {action_type}'}
        except Exception as e:
            logger.error(f"Error executing action {action_type}: {e}")
            return {'success': False, 'error': str(e)}
