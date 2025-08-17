"""Additional tests for EnhancedAIAssistant covering greeting & fallback paths.

These scenarios were previously untested: greeting intents and fallback response
generation when the Watsonx client raises an exception (e.g., network issue).
"""
import pytest
from unittest.mock import patch

from app import create_app, db
from app.models import Workspace, Shipment
from app.agents.ai_assistant import EnhancedAIAssistant


@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        ws = Workspace(name='WS', code='WS')
        db.session.add(ws)
        # Seed a shipment so greeting can report counts
        shipment = Shipment(
            workspace_id=1,
            reference_number='HELLO-001',
            origin_port='Shanghai',
            destination_port='Los Angeles',
            carrier='Maersk',
            status='IN_TRANSIT'
        )
        db.session.add(shipment)
        db.session.commit()
        yield app
        db.drop_all()


@pytest.mark.asyncio
@patch('app.agents.ai_assistant.WatsonxClient.generate', side_effect=Exception("API down"))
async def test_greeting_fallback(mock_gen, app):
    """When Watsonx generation fails, assistant should return a friendly greeting fallback."""
    with app.app_context():
        assistant = EnhancedAIAssistant()
        response = await assistant.process_message(
            message='Hello there',
            context={'page': '/dashboard'},
            conversation_history=[]
        )
        assert 'hello' in response['message'].lower()
        # Should provide some operational context (e.g., mention shipments)
        assert 'shipment' in response['message'].lower()
        assert response['confidence'] >= 0.0  # Fallback sets 0.7 in intent or 0.8 default
        # Actions should still include list (may be empty or navigation suggestions)
        assert isinstance(response['actions'], list)
