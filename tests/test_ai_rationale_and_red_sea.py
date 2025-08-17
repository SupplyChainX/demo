import json
import pytest

from app import db
from app.models import Shipment, Route, RouteType, Recommendation
from app.agents.route_optimizer import RouteOptimizerAgent


def _make_shipment(**overrides):
    s = Shipment(
        workspace_id=1,
        reference_number=overrides.get('reference_number', 'AI-R-001'),
        tracking_number=overrides.get('tracking_number', overrides.get('reference_number', 'AI-R-001')),
        origin_port='Shanghai',
        destination_port='Rotterdam',
        carrier='Maersk',
        risk_score=overrides.get('risk_score', 0.8),
        transport_mode='SEA'
    )
    db.session.add(s)
    db.session.commit()
    return s


def _add_current_route(shipment, waypoints, **metrics):
    r = Route(
        shipment_id=shipment.id,
        route_type=RouteType.SEA,
        waypoints=json.dumps(waypoints),
        distance_km=metrics.get('distance_km', 10000),
        estimated_duration_hours=metrics.get('estimated_duration_hours', 400),
        cost_usd=metrics.get('cost_usd', 120000),
        carbon_emissions_kg=metrics.get('carbon_emissions_kg', 500000),
        risk_score=metrics.get('risk_score', shipment.risk_score or 0.8),
        is_current=True,
        is_recommended=True,
        route_metadata=json.dumps({'name': metrics.get('name', 'Baseline Route')})
    )
    db.session.add(r)
    db.session.commit()
    return r


def test_ai_rationale_fallback_no_api_key(client):
    """When TESTING temporarily disabled and no API key, we should see fallback-no-api model."""
    app = client.application
    agent = RouteOptimizerAgent(app)
    with app.app_context():
        shipment = _make_shipment(reference_number='AI-FALLBACK-1')
        original_testing = app.config.get('TESTING', True)
        try:
            app.config['TESTING'] = False
            app.config.pop('WATSONX_API_KEY', None)
            rec_data = {'title': 'Fallback Check', 'current_route': {}, 'alternatives': []}
            xai = agent._build_ai_rationale(shipment, rec_data)
            assert xai['model'] == 'fallback-no-api'
            assert 'rationale' in xai and xai['rationale']
        finally:
            app.config['TESTING'] = original_testing
        Recommendation.query.filter_by(subject_id=shipment.id).delete()
        Route.query.filter_by(shipment_id=shipment.id).delete()
        db.session.delete(shipment)
        db.session.commit()


def test_ai_rationale_live_call_with_api_key(monkeypatch, client):
    """With API key and TESTING disabled, Granite path should set model=granite-3-2b-instruct."""
    app = client.application
    agent = RouteOptimizerAgent(app)
    with app.app_context():
        shipment = _make_shipment(reference_number='AI-LIVE-1')
        original_testing = app.config.get('TESTING', True)
        try:
            app.config['TESTING'] = False
            app.config['WATSONX_API_KEY'] = 'dummy-key'
            app.config['WATSONX_PROJECT_ID'] = 'proj'

            def fake_generate(self, prompt, model_id='ibm/granite-3-2b-instruct', **kwargs):
                return '{"rationale":"Granite generated rationale","factors":["risk_reduction","cost_optimization"],"recommended_route":{"id":1,"name":"Alt"},"improvements":{"risk":"-15%"},"confidence":0.91}'

            monkeypatch.setattr('app.integrations.watsonx_client.WatsonxClient.generate', fake_generate)
            rec_data = {'title': 'Live Call Check', 'current_route': {}, 'alternatives': []}
            xai = agent._build_ai_rationale(shipment, rec_data)
            assert xai['model'] == 'granite-3-2b-instruct'
            assert xai.get('confidence') == 0.91
            assert 'factors' in xai and 'risk_reduction' in xai['factors']
        finally:
            app.config['TESTING'] = original_testing
            app.config.pop('WATSONX_API_KEY', None)
        Recommendation.query.filter_by(subject_id=shipment.id).delete()
        Route.query.filter_by(shipment_id=shipment.id).delete()
        db.session.delete(shipment)
        db.session.commit()


def test_red_sea_reroute_generates_cape_route_and_xai(client):
    """Red Sea / Suez waypoint triggers Cape of Good Hope alternative and recommendation with XAI factors."""
    app = client.application
    agent = RouteOptimizerAgent(app)
    with app.app_context():
        shipment = _make_shipment(reference_number='REDSEA-1', risk_score=0.9)
        current_route = _add_current_route(
            shipment,
            [
                {'name': 'Shanghai', 'lat': 31.22, 'lon': 121.46},
                {'name': 'Red Sea Transit / Suez Canal', 'lat': 30.0, 'lon': 32.5},
                {'name': 'Rotterdam', 'lat': 51.92, 'lon': 4.48}
            ],
            risk_score=0.9,
            name='Red Sea Route'
        )
        assert Recommendation.query.filter_by(subject_id=shipment.id).count() == 0
        agent._evaluate_route_alternatives(shipment, force=True)
        rec = Recommendation.query.filter_by(subject_id=shipment.id).first()
        assert rec is not None
        assert rec.recommendation_type == 'REROUTE'
        xai = rec.xai_json or {}
        assert 'rationale' in xai
        assert 'factors' in xai
        alt = Route.query.filter(Route.shipment_id==shipment.id, Route.is_current==False).filter(Route.id != current_route.id).first()
        assert alt is not None
        meta = json.loads(alt.route_metadata or '{}')
        assert meta.get('name') == 'Cape of Good Hope Route'
        assert alt.risk_score < current_route.risk_score
        Recommendation.query.filter_by(subject_id=shipment.id).delete()
        Route.query.filter_by(shipment_id=shipment.id).delete()
        db.session.delete(shipment)
        db.session.commit()
