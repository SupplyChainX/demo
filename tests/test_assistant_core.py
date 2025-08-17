"""
Core tests for Enhanced AI Assistant functionality
Focus on essential capabilities and endpoints
"""

import pytest
import json
import uuid
from datetime import datetime
from unittest.mock import patch, MagicMock

from app import create_app, db
from app.models_enhanced import ChatSession, ChatMessage, UserPersonalization
from app.models import User
from app.integrations.watsonx_client import WatsonxClient

@pytest.fixture
def app():
    """Create test app instance"""
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()

@pytest.fixture
def sample_user(app):
    """Create sample user"""
    user = User(
        name='Test User',
        email='test@example.com',
        password_hash='test_hash',
        role='operator'
    )
    db.session.add(user)
    db.session.commit()
    return user

class TestWatsonxClientCore:
    """Core Watsonx client tests"""
    
    @patch('app.integrations.watsonx_client.requests.post')
    def test_authentication_success(self, mock_post, app):
        """Test successful authentication with Watsonx"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'test_token_123',
            'expires_in': 3600,
            'token_type': 'Bearer'
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        with app.app_context():
            client = WatsonxClient()
            token = client._get_auth_token()
            
            assert token == 'test_token_123'
            assert client.auth_token == 'test_token_123'
    
    @patch('app.integrations.watsonx_client.requests.post')
    def test_text_generation(self, mock_post, app):
        """Test text generation with Granite model"""
        # Mock auth response
        auth_response = MagicMock()
        auth_response.status_code = 200
        auth_response.json.return_value = {
            'access_token': 'test_token_123',
            'expires_in': 3600
        }
        auth_response.raise_for_status.return_value = None
        
        # Mock generation response
        gen_response = MagicMock()
        gen_response.status_code = 200
        gen_response.json.return_value = {
            'results': [{
                'generated_text': 'This is a test response from Granite.',
                'generated_token_count': 10
            }]
        }
        gen_response.raise_for_status.return_value = None
        
        mock_post.side_effect = [auth_response, gen_response]
        
        with app.app_context():
            client = WatsonxClient()
            response = client.generate('Test prompt')
            
            assert response == 'This is a test response from Granite.'

class TestEnhancedAssistantEndpoints:
    """Test enhanced assistant API endpoints"""
    
    def test_capabilities_endpoint(self, client, app):
        """Test assistant capabilities endpoint"""
        with app.app_context():
            response = client.get('/api/assistant/capabilities')
            data = json.loads(response.data)
            
            assert response.status_code == 200
            assert data['success'] is True
            assert 'capabilities' in data
            assert len(data['capabilities']) > 0
    
    def test_start_session_endpoint(self, client, app, sample_user):
        """Test session creation endpoint"""
        with app.app_context():
            with client.session_transaction() as sess:
                sess['_user_id'] = str(sample_user.id)
            
            response = client.post('/api/assistant/start-session', json={
                'context': {'type': 'dashboard', 'path': '/dashboard'}
            })
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'session_id' in data
    
    @patch.object(WatsonxClient, 'generate')
    def test_chat_endpoint_with_mock(self, mock_generate, client, app, sample_user):
        """Test chat endpoint with mocked Watsonx response"""
        mock_generate.return_value = "Hello! I can help you with supply chain management."
        
        with app.app_context():
            with client.session_transaction() as sess:
                sess['_user_id'] = str(sample_user.id)
            
            # Create a session first
            session_response = client.post('/api/assistant/start-session', json={
                'context': {'type': 'dashboard', 'path': '/dashboard'}
            })
            session_data = json.loads(session_response.data)
            session_id = session_data['session_id']
            
            # Send chat message
            response = client.post('/api/assistant/chat', json={
                'message': 'Hello, can you help me?',
                'session_id': session_id,
                'page_context': {
                    'page_info': {'type': 'dashboard', 'path': '/dashboard'},
                    'current_data': {}
                }
            })
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'message' in data
            # Should not be fallback response when mocked
            assert data['message'] == "Hello! I can help you with supply chain management."

class TestDataPersistence:
    """Test data persistence functionality"""
    
    def test_session_creation(self, app, sample_user):
        """Test chat session creation"""
        with app.app_context():
            session = ChatSession(
                user_id=sample_user.id,
                session_name='Test Session',
                context_data={'type': 'dashboard'}
            )
            db.session.add(session)
            db.session.commit()
            
            retrieved = ChatSession.query.filter_by(user_id=sample_user.id).first()
            assert retrieved is not None
            assert retrieved.session_name == 'Test Session'
    
    def test_message_persistence(self, app, sample_user):
        """Test chat message persistence"""
        with app.app_context():
            # Create session
            session = ChatSession(user_id=sample_user.id)
            db.session.add(session)
            db.session.flush()
            
            # Create message
            message = ChatMessage(
                session_id=session.id,
                user_id=sample_user.id,
                sender='user',
                message='Test message',
                page_context={'type': 'dashboard'}
            )
            db.session.add(message)
            db.session.commit()
            
            retrieved = ChatMessage.query.filter_by(session_id=session.id).first()
            assert retrieved is not None
            assert retrieved.message == 'Test message'
            assert retrieved.sender == 'user'
    
    def test_personalization(self, app, sample_user):
        """Test user personalization"""
        with app.app_context():
            personalization = UserPersonalization(
                user_id=sample_user.id,
                preferred_response_style='brief',
                preferences={'theme': 'dark'}
            )
            db.session.add(personalization)
            db.session.commit()
            
            retrieved = UserPersonalization.query.filter_by(user_id=sample_user.id).first()
            assert retrieved is not None
            assert retrieved.preferred_response_style == 'brief'
            assert retrieved.preferences['theme'] == 'dark'

class TestRealWatsonxIntegration:
    """Test real Watsonx integration (requires valid API keys)"""
    
    def test_real_watsonx_authentication(self, app):
        """Test real Watsonx authentication"""
        with app.app_context():
            try:
                client = WatsonxClient()
                if client.api_key and client.project_id:
                    token = client._get_auth_token()
                    assert token is not None
                    assert len(token) > 50  # Real tokens are long
                else:
                    pytest.skip("No Watsonx credentials available")
            except Exception as e:
                pytest.fail(f"Real Watsonx authentication failed: {e}")
    
    def test_real_watsonx_generation(self, app):
        """Test real text generation"""
        with app.app_context():
            try:
                client = WatsonxClient()
                if client.api_key and client.project_id:
                    response = client.generate(
                        "Please respond with exactly: 'Test successful'",
                        max_tokens=10
                    )
                    assert response != 'Unable to generate AI response at this time.'
                    assert len(response) > 0
                else:
                    pytest.skip("No Watsonx credentials available")
            except Exception as e:
                pytest.fail(f"Real Watsonx generation failed: {e}")

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
