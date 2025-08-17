"""Comprehensive tests for Enhanced AI Assistant with Watson Granite integration."""
import pytest
import json
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from app import create_app, db
from app.models import (
    User, Supplier, Shipment, Alert,
    Recommendation, ChatMessage, Route,
    Risk, SupplierRiskAssessment, Workspace,
    Inventory, PurchaseOrder
)
from app.agents.ai_assistant import EnhancedAIAssistant


@pytest.fixture
def app():
    """Create application for testing."""
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def sample_data(app):
    """Create comprehensive sample data for testing."""
    with app.app_context():
        workspace = Workspace(name='Test Workspace', code='TEST-WS')
        db.session.add(workspace)
        db.session.flush()

        user = User(
            name='Test User',
            email='test@example.com',
            password_hash='hashed_password',
            role='admin'
        )
        db.session.add(user)

        shipment1 = Shipment(
            workspace_id=workspace.id,
            reference_number='TEST-001',
            origin_port='Shanghai',
            destination_port='Los Angeles',
            status='IN_TRANSIT',
            carrier='Maersk'
        )
        db.session.add(shipment1)

        shipment2 = Shipment(
            workspace_id=workspace.id,
            reference_number='TEST-002',
            origin_port='Hamburg',
            destination_port='New York',
            status='PENDING',
            carrier='DHL'
        )
        db.session.add(shipment2)

        supplier1 = Supplier(
            workspace_id=workspace.id,
            name='Test Supplier A',
            country='China',
            is_active=True,
            reliability_score=0.92,
            quality_rating=0.88
        )
        db.session.add(supplier1)

        supplier2 = Supplier(
            workspace_id=workspace.id,
            name='Test Supplier B',
            country='Germany',
            is_active=True,
            reliability_score=0.89,
            quality_rating=0.91
        )
        db.session.add(supplier2)
        # Flush to ensure supplier IDs are assigned before dependent records
        db.session.flush()

        alert1 = Alert(
            workspace_id=workspace.id,
            title='High Risk Weather Alert',
            description='Typhoon approaching shipping lanes',
            severity='HIGH',
            alert_type='WEATHER',
            status='open'
        )
        db.session.add(alert1)

        recommendation1 = Recommendation(
            workspace_id=workspace.id,
            title='Route Optimization Recommendation',
            description='Alternative route suggested to avoid delays',
            type='reroute',
            severity='medium',
            confidence=0.85,
            status='PENDING',
            created_by='route_optimizer_agent'
        )
        db.session.add(recommendation1)

        from app.models import Risk
        risk_r = Risk(
            workspace_id=workspace.id,
            risk_type='GEOPOLITICAL',
            title='Geopolitical Tension',
            description='Political tensions in shipping region',
            risk_score=0.70,
            severity='MEDIUM',
            probability=0.65,
            confidence=0.80
        )
        db.session.add(risk_r)

        inventory1 = Inventory(
            workspace_id=workspace.id,
            sku='SKU-001',
            description='Test Product A',
            quantity_on_hand=100,
            reorder_point=20,
            unit_cost=15.50,
            supplier_id=supplier1.id
        )
        db.session.add(inventory1)

        po1 = PurchaseOrder(
            workspace_id=workspace.id,
            po_number='PO-001',
            supplier_id=supplier1.id,
            status='PENDING',
            total_amount=5000.00,
            currency='USD'
        )
        db.session.add(po1)

        route1 = Route(
            shipment_id=shipment1.id,
            route_type='OCEAN',
            waypoints='[{"lat": 31.2304, "lng": 121.4737, "name": "Shanghai"}, {"lat": 34.0522, "lng": -118.2437, "name": "Los Angeles"}]',
            distance_km=11500.0,
            estimated_duration_hours=480.0,
            cost_usd=2500.00,
            carbon_emissions_kg=850.0,
            risk_score=0.3,
            risk_factors='["weather", "port_congestion"]',
            is_current=True,
            is_recommended=True,
            route_metadata='{"carrier": "Maersk", "vessel": "Ever Given"}'
        )
        db.session.add(route1)

        db.session.commit()

        return {
            'workspace': workspace,
            'user': user,
            'shipments': [shipment1, shipment2],
            'suppliers': [supplier1, supplier2],
            'alerts': [alert1],
            'recommendations': [recommendation1],
            'inventory': [inventory1],
            'risk_assessments': [risk_r],
            'purchase_orders': [po1],
            'routes': [route1]
        }

class TestEnhancedAIAssistant:
    """Test Enhanced AI Assistant functionality"""
    
    @pytest.fixture
    def assistant(self, app):
        """Create assistant instance for testing"""
        with app.app_context():
            return EnhancedAIAssistant()
    
    @patch('app.agents.ai_assistant.WatsonxClient')
    def test_assistant_initialization(self, mock_watsonx, assistant):
        """Test assistant initialization"""
        assert assistant is not None
        assert assistant.tools is not None
        assert len(assistant.tools) > 0
        assert 'get_shipments' in assistant.tools
        assert 'get_suppliers' in assistant.tools
        assert 'get_alerts' in assistant.tools
        
    @patch('app.agents.ai_assistant.WatsonxClient')
    def test_intent_analysis_shipments(self, mock_watsonx, assistant, sample_data):
        """Test intent analysis for shipment queries"""
        # Mock Watson response
        mock_generate = MagicMock()
        mock_generate.return_value = '''
        {
            "category": "shipments",
            "intent": "tracking",
            "entities": ["TEST-001"],
            "tools_required": ["get_shipments"],
            "confidence": 0.9,
            "urgency": "medium",
            "requires_agent_consultation": false
        }
        '''
        # Replace the assistant's watsonx instance with our mock
        assistant.watsonx = MagicMock()
        assistant.watsonx.generate = mock_generate
        
        message = "What's the status of shipment TEST-001?"
        intent = asyncio.run(assistant._analyze_intent(message))
        
        assert intent['category'] == 'shipments'
        assert intent['intent'] == 'tracking'
        assert 'TEST-001' in intent['entities']
        assert intent['confidence'] > 0.8
        
    @patch('app.agents.ai_assistant.WatsonxClient')
    def test_intent_analysis_procurement(self, mock_watsonx, assistant, sample_data):
        """Test intent analysis for procurement queries"""
        # Mock the assistant's watsonx instance directly
        assistant.watsonx.generate = MagicMock(return_value='''
        {
            "category": "procurement",
            "intent": "management",
            "entities": ["Test Supplier A"],
            "tools_required": ["get_suppliers", "get_purchase_orders"],
            "confidence": 0.85,
            "urgency": "low",
            "requires_agent_consultation": true
        }
        ''')
        
        message = "How is Test Supplier A performing?"
        intent = asyncio.run(assistant._analyze_intent(message))
        
        assert intent['category'] == 'procurement'
        assert intent['intent'] == 'management'
        assert intent['requires_agent_consultation'] == True
        
    def test_fallback_intent_analysis(self, assistant, sample_data):
        """Test fallback intent analysis when Watson is unavailable"""
        message = "Show me shipment tracking information"
        intent = assistant._fallback_intent_analysis(message)
        
        assert intent['category'] == 'shipments'
        assert intent['intent'] == 'tracking'
        assert intent['confidence'] > 0.0
        
    def test_get_shipments_data(self, assistant, sample_data):
        """Test shipments data retrieval"""
        shipments = assistant.get_shipments_data(limit=10)
        
        assert len(shipments) == 2
        assert shipments[0]['reference'] in ['TEST-001', 'TEST-002']
        assert 'origin' in shipments[0]
        assert 'destination' in shipments[0]
        assert 'status' in shipments[0]
        
    def test_get_shipments_data_with_entities(self, assistant, sample_data):
        """Test shipments data retrieval with specific entities"""
        shipments = assistant.get_shipments_data(entities=['TEST-001'])
        
        assert len(shipments) == 1
        assert shipments[0]['reference'] == 'TEST-001'
        
    def test_get_suppliers_data(self, assistant, sample_data):
        """Test suppliers data retrieval"""
        suppliers = assistant.get_suppliers_data(limit=10)
        
        assert len(suppliers) == 2
        assert suppliers[0]['name'] in ['Test Supplier A', 'Test Supplier B']
        assert 'reliability_score' in suppliers[0]
        assert 'performance_rating' in suppliers[0]
        
    def test_get_alerts_data(self, assistant, sample_data):
        """Test alerts data retrieval"""
        alerts = assistant.get_alerts_data(limit=10)
        
        assert len(alerts) == 1
        assert alerts[0]['title'] == 'High Risk Weather Alert'
        assert alerts[0]['severity'] == 'HIGH'
        
    def test_get_recommendations_data(self, assistant, sample_data):
        """Test recommendations data retrieval"""
        recommendations = assistant.get_recommendations_data(limit=10)
        
        assert len(recommendations) == 1
        assert recommendations[0]['title'] == 'Route Optimization Recommendation'
        assert recommendations[0]['type'] == 'reroute'
        
    def test_get_inventory_data(self, assistant, sample_data):
        """Test inventory data retrieval"""
        inventory = assistant.get_inventory_data(limit=10)
        
        assert len(inventory) == 1
        assert inventory[0]['sku'] == 'SKU-001'
        
    def test_get_risk_assessment_data(self, assistant, sample_data):
        """Test risk assessment data retrieval"""
        risk_assessments = assistant.get_risk_assessment_data(limit=10)
        
        assert len(risk_assessments) == 1
        assert risk_assessments[0]['risk_type'] == 'GEOPOLITICAL'
        assert risk_assessments[0]['severity'] == 'MEDIUM'
        
    def test_get_purchase_orders_data(self, assistant, sample_data):
        """Test purchase orders data retrieval"""
        pos = assistant.get_purchase_orders_data(limit=10)
        
        assert len(pos) == 1
        assert pos[0]['po_number'] == 'PO-001'
        assert pos[0]['status'] == 'PENDING'
        
    def test_get_routes_data(self, assistant, sample_data):
        """Test routes data retrieval"""
        routes = assistant.get_routes_data(limit=10)
        
        assert len(routes) == 1
        assert routes[0]['route_type'] == 'OCEAN'
        assert routes[0]['is_current'] == True
        assert routes[0]['is_recommended'] == True
        assert len(routes[0]['waypoints']) == 2
        assert routes[0]['distance_km'] == 11500.0
        
    def test_analyze_performance_data(self, assistant, sample_data):
        """Test performance data analysis"""
        performance = assistant.analyze_performance_data()
        
        assert 'total_shipments' in performance
        assert 'active_alerts' in performance
        assert 'pending_recommendations' in performance
        assert 'total_suppliers' in performance
        assert performance['total_shipments'] == 2
        assert performance['active_alerts'] == 1
        
    @patch('app.agents.ai_assistant.WatsonxClient')
    async def test_process_message_shipment_query(self, mock_watsonx, assistant, sample_data):
        """Test processing a shipment-related message"""
        # Mock Watson responses directly on the assistant instance
        assistant.watsonx.generate = MagicMock(side_effect=[
            # Intent analysis response
            '{"category": "shipments", "intent": "tracking", "entities": ["TEST-001"], "tools_required": ["get_shipments"], "confidence": 0.9, "urgency": "medium", "requires_agent_consultation": false}',
            # Final response
            "I can see that shipment TEST-001 is currently in transit from Shanghai to Los Angeles via Maersk. The shipment is proceeding as planned."
        ])
        
        message = "What's the status of shipment TEST-001?"
        context = {'page': '/dashboard', 'type': 'general'}
        history = []
        
        response = await assistant.process_message(message, context, history)
        
        assert response['message'] is not None
        assert len(response['actions']) > 0
        assert response['confidence'] > 0.8
        assert 'get_shipments' in response['tools_used']
        
    @patch('app.agents.ai_assistant.WatsonxClient')
    async def test_process_message_procurement_query(self, mock_watsonx, assistant, sample_data):
        """Test processing a procurement-related message"""
        assistant.watsonx.generate = MagicMock(side_effect=[
            # Intent analysis response
            '{"category": "procurement", "intent": "management", "entities": [], "tools_required": ["get_suppliers"], "confidence": 0.85, "urgency": "low", "requires_agent_consultation": true}',
            # Agent consultation response
            "Test Supplier A has excellent performance with 92% reliability and 88% performance rating.",
            # Final response
            "Your procurement system shows Test Supplier A performing well with high reliability scores. They have active purchase orders and good performance metrics."
        ])
        
        message = "How are my suppliers performing?"
        context = {'page': '/procurement', 'type': 'procurement'}
        history = []
        
        response = await assistant.process_message(message, context, history)
        
        assert response['message'] is not None
        assert len(response['actions']) > 0
        assert len(response['agent_responses']) > 0
        assert response['confidence'] > 0.8
        
    def test_extract_actions_shipments(self, assistant, sample_data):
        """Test action extraction for shipment queries"""
        intent = {
            'category': 'shipments',
            'intent': 'tracking',
            'entities': ['TEST-001'],
            'urgency': 'medium'
        }
        message = "What's the status of shipment TEST-001?"
        context = {}
        
        actions = assistant._extract_actions(intent, message, context)
        
        assert len(actions) >= 1
        assert any(action['type'] == 'navigate' and '/logistics' in action['data'] for action in actions)
        assert any(action['type'] == 'search_shipment' and 'TEST-001' in action['data'] for action in actions)
        
    def test_extract_actions_procurement(self, assistant, sample_data):
        """Test action extraction for procurement queries"""
        intent = {
            'category': 'procurement',
            'intent': 'management',
            'entities': [],
            'urgency': 'low'
        }
        message = "Show me supplier information"
        context = {}
        
        actions = assistant._extract_actions(intent, message, context)
        
        assert len(actions) >= 1
        assert any(action['type'] == 'navigate' and '/procurement' in action['data'] for action in actions)
        assert any(action['type'] == 'navigate' and '/suppliers' in action['data'] for action in actions)
        
    def test_extract_actions_risk(self, assistant, sample_data):
        """Test action extraction for risk queries"""
        intent = {
            'category': 'risk',
            'intent': 'monitoring',
            'entities': [],
            'urgency': 'high'
        }
        message = "Show me current risk alerts"
        context = {}
        
        actions = assistant._extract_actions(intent, message, context)
        
        assert len(actions) >= 1
        assert any(action['type'] == 'navigate' and '/risk' in action['data'] for action in actions)
        assert any(action['type'] == 'show_recommendations' for action in actions)

class TestAIAssistantAPI:
    """Test AI Assistant API endpoints"""
    
    def test_assistant_chat_endpoint_basic(self, client, sample_data):
        """Test basic assistant chat endpoint"""
        payload = {
            'message': 'Hello, what shipments do I have?',
            'session_id': 'test_session_123',
            'context': {'page': '/dashboard', 'type': 'general'},
            'conversation_history': []
        }
        
        response = client.post('/api/assistant/chat',
                             data=json.dumps(payload),
                             content_type='application/json')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        assert 'message' in data
        assert 'actions' in data
        assert 'context_update' in data
        
    def test_assistant_chat_endpoint_missing_message(self, client, sample_data):
        """Test assistant chat endpoint with missing message"""
        payload = {
            'session_id': 'test_session_123',
            'context': {},
            'conversation_history': []
        }
        
        response = client.post('/api/assistant/chat',
                             data=json.dumps(payload),
                             content_type='application/json')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        
    def test_assistant_chat_endpoint_empty_message(self, client, sample_data):
        """Test assistant chat endpoint with empty message"""
        payload = {
            'message': '   ',
            'session_id': 'test_session_123',
            'context': {},
            'conversation_history': []
        }
        
        response = client.post('/api/assistant/chat',
                             data=json.dumps(payload),
                             content_type='application/json')
        
        assert response.status_code == 400
        
    def test_assistant_chat_shipment_context(self, client, sample_data):
        """Test assistant chat with shipment context"""
        payload = {
            'message': 'Tell me about this shipment',
            'session_id': 'test_session_123',
            'context': {
                'page': '/shipment/1',
                'type': 'shipment_detail',
                'shipment_id': '1'
            },
            'conversation_history': []
        }
        
        response = client.post('/api/assistant/chat',
                             data=json.dumps(payload),
                             content_type='application/json')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        
    def test_assistant_chat_conversation_history(self, client, sample_data):
        """Test assistant chat with conversation history"""
        payload = {
            'message': 'What about procurement?',
            'session_id': 'test_session_123',
            'context': {'page': '/dashboard', 'type': 'general'},
            'conversation_history': [
                {'sender': 'user', 'message': 'Show me shipments', 'timestamp': '2025-08-14T10:00:00Z'},
                {'sender': 'assistant', 'message': 'You have 2 shipments currently', 'timestamp': '2025-08-14T10:00:01Z'}
            ]
        }
        
        response = client.post('/api/assistant/chat',
                             data=json.dumps(payload),
                             content_type='application/json')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True

class TestWatsonxIntegration:
    """Test Watson AI integration"""
    
    @patch('app.integrations.watsonx_client.requests.post')
    def test_watsonx_client_initialization(self, mock_post, app, monkeypatch):
        """Test Watson client initialization with dummy env vars."""
        # Provide dummy env vars expected by config
        monkeypatch.setenv('WATSONX_API_KEY', 'dummy')
        monkeypatch.setenv('WATSONX_PROJECT_ID', 'proj123')
        with app.app_context():
            from app.integrations.watsonx_client import WatsonxClient
            client = WatsonxClient()
            assert client.api_key == 'dummy'
            assert client.project_id == 'proj123'
            
    @patch('app.integrations.watsonx_client.requests.post')
    def test_watsonx_generate_text(self, mock_post, app):
        """Test Watson text generation"""
        # Mock authentication response
        mock_post.side_effect = [
            # Auth response
            Mock(status_code=200, json=lambda: {
                'access_token': 'test_token',
                'expires_in': 3600
            }),
            # Generation response
            Mock(status_code=200, json=lambda: {
                'results': [{
                    'generated_text': 'This is a test response from Watson.',
                    'generated_token_count': 10
                }]
            })
        ]
        
        with app.app_context():
            from app.integrations.watsonx_client import WatsonxClient
            client = WatsonxClient()
            
            response = client.generate(
                prompt="Test prompt for supply chain analysis",
                max_tokens=100
            )
            
            assert response == 'This is a test response from Watson.'
            assert mock_post.call_count == 2  # Auth + generation
            
    @patch('app.integrations.watsonx_client.requests.post')
    def test_watsonx_generate_embeddings(self, mock_post, app):
        """Test Watson embeddings generation"""
        # Mock responses
        mock_post.side_effect = [
            # Auth response
            Mock(status_code=200, json=lambda: {
                'access_token': 'test_token',
                'expires_in': 3600
            }),
            # Embeddings response
            Mock(status_code=200, json=lambda: {
                'results': [
                    {'embedding': [0.1, 0.2, 0.3]},
                    {'embedding': [0.4, 0.5, 0.6]}
                ]
            })
        ]
        
        with app.app_context():
            from app.integrations.watsonx_client import WatsonxClient
            client = WatsonxClient()
            
            embeddings = client.generate_embeddings([
                "shipment tracking query",
                "supplier performance analysis"
            ])
            
            assert len(embeddings) == 2
            assert embeddings[0] == [0.1, 0.2, 0.3]
            assert embeddings[1] == [0.4, 0.5, 0.6]
            
    @patch('app.integrations.watsonx_client.requests.post')
    def test_watsonx_error_handling(self, mock_post, app):
        """Test Watson error handling"""
        # Mock authentication failure
        mock_post.side_effect = [
            Mock(status_code=401, raise_for_status=Mock(
                side_effect=Exception("Authentication failed")
            ))
        ]
        
        with app.app_context():
            from app.integrations.watsonx_client import WatsonxClient
            client = WatsonxClient()
            
            with pytest.raises(Exception):
                client._get_auth_token()

class TestChatMessageLogging:
    """Test chat message logging functionality"""
    
    def test_log_enhanced_chat_message(self, app, sample_data):
        """Test enhanced chat message logging"""
        with app.app_context():
            from app.main.routes import log_enhanced_chat_message
            
            session_id = 'test_session_123'
            user_message = 'What shipments do I have?'
            assistant_response = 'You have 2 active shipments.'
            context = {'page': '/dashboard', 'type': 'general'}
            response_data = {
                'confidence': 0.9,
                'tools_used': ['get_shipments'],
                'agent_responses': [],
                'actions': [{'type': 'navigate', 'data': '/logistics'}]
            }
            
            log_enhanced_chat_message(
                session_id, user_message, assistant_response, context, response_data
            )
            
            # Check that messages were logged
            user_chat = ChatMessage.query.filter_by(message=user_message).first()
            assistant_chat = ChatMessage.query.filter_by(message=assistant_response).first()
            
            assert user_chat is not None
            assert assistant_chat is not None
            assert assistant_chat.agent_name == 'enhanced_assistant'
            
            # Check metadata
            assert user_chat.session_id == session_id
            assert assistant_chat.confidence_score == 0.9
            assert 'get_shipments' in assistant_chat.tools_used
            assert len(assistant_chat.suggested_actions) == 1
            assert assistant_chat.suggested_actions[0]['type'] == 'navigate'

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
