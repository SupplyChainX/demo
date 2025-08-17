"""Tests for recommendation XAI rationale generation (Granite vs fallback).

These tests specifically exercise the Granite (watsonx) path inside
RouteOptimizerAgent._build_ai_rationale by temporarily disabling the
`TESTING` short‑circuit and patching the WatsonxClient to avoid real
network calls. This addresses the user's concern that no Granite calls
were being observed – in normal test mode the code purposefully returns
the deterministic fallback (`model: deterministic-fallback`).
"""
import json
from app.agents.route_optimizer import RouteOptimizerAgent
from app.models import Route, RouteType
from app import db


def test_granite_rationale_generation(monkeypatch, app, sample_data):
    """Validate that when TESTING short-circuit is disabled and watsonx config
    is present, the agent attempts Granite rationale generation and stores
    the parsed JSON with model == 'granite-3-2b-instruct'.

    Implementation detail: _build_ai_rationale returns early with a deterministic
    payload whenever current_app.config['TESTING'] is True. We temporarily set it
    to False inside this test to exercise the Granite branch while still running
    inside the pytest environment. A WatsonxClient.generate patch returns a
    controlled JSON string so no external HTTP call is made.
    """
    shipment = sample_data['shipment']
    current_route = sample_data['current_route']

    # Add an alternative route (recommended) to provide richer rec_data
    alt_route = Route(
        shipment_id=shipment.id,
        route_type=RouteType.SEA,
        waypoints=current_route.waypoints,
        distance_km=current_route.distance_km * 1.05,
        estimated_duration_hours=current_route.estimated_duration_hours * 0.95,
        cost_usd=current_route.cost_usd * 0.9,
        carbon_emissions_kg=current_route.carbon_emissions_kg * 0.92,
        risk_score=max(0.0, current_route.risk_score - 0.15),
        is_current=False,
        is_recommended=True,
        route_metadata=json.dumps({'name': 'Optimized Alt Route', 'composite_score': 0.88})
    )
    db.session.add(alt_route)
    db.session.commit()

    # Patch WatsonxClient.generate to return valid JSON block
    granite_response = json.dumps({
        "rationale": "Switching to alternative reduces risk and cost",
        "factors": ["risk_reduction", "cost_optimization"],
        "improvements": {"risk_reduction": "15%", "cost_savings": "10%"},
        "recommended_route": {"id": alt_route.id, "name": "Optimized Alt Route"},
        "data_sources": ["maersk_api", "dhl_mock"],
        "confidence": 0.91
    })

    class DummyWatsonxClient:
        def generate(self, *args, **kwargs):  # signature compatibility
            return granite_response

    monkeypatch.setenv('WATSONX_API_KEY', 'dummy-test-key')
    monkeypatch.setenv('WATSONX_PROJECT_ID', 'proj-test')

    # Patch WatsonxClient class where it is imported (integrations module);
    # route_optimizer does a local import inside _build_ai_rationale so replacing
    # the class in its original module path is sufficient.
    import app.integrations.watsonx_client as wx_mod
    monkeypatch.setattr(wx_mod, 'WatsonxClient', DummyWatsonxClient, raising=True)

    # Ensure Flask config has keys (code checks current_app.config for API key)
    app.config['WATSONX_API_KEY'] = 'dummy-test-key'
    app.config['WATSONX_PROJECT_ID'] = 'proj-test'
    agent = RouteOptimizerAgent()

    # Temporarily disable TESTING flag to bypass deterministic branch
    old_testing = app.config.get('TESTING')
    app.config['TESTING'] = False
    try:
        rec = agent._create_recommendation(
            shipment,
            [alt_route],  # use list path so legacy merging logic also runs
            current_route
        )
    finally:
        app.config['TESTING'] = old_testing

    assert rec is not None, "Recommendation should be created"
    xai = json.loads(rec.rationale)
    # Ensure Granite branch enriched payload
    assert xai.get('model') == 'granite-3-2b-instruct'
    assert xai.get('confidence') == 0.91
    assert any(f in xai.get('factors', []) for f in ["risk_reduction", "cost_optimization"])
    # Recommended route id surfaced either directly or within route_analysis
    route_analysis = xai.get('route_analysis', {})
    assert 'alternatives' in route_analysis

    # Data field sanity
    data = json.loads(rec.data)
    assert data['recommended_route_id'] == alt_route.id
