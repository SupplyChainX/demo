import json
from app.agents.route_optimizer import RouteOptimizerAgent
from app.models import Recommendation, Route, RouteType


def _seed_recommendation(app, shipment, current_route, name_suffix='Economical', cost_factor=0.95, duration_factor=1.02, risk_delta=0.1):
    from app import db
    alt_route = Route(
        shipment_id=shipment.id,
        route_type=RouteType.SEA,
        waypoints=current_route.waypoints,
        distance_km=current_route.distance_km * 1.05,
        estimated_duration_hours=current_route.estimated_duration_hours * duration_factor,
        cost_usd=current_route.cost_usd * cost_factor,
        carbon_emissions_kg=current_route.carbon_emissions_kg * 0.97,
        risk_score=max(0.0, (current_route.risk_score or 0) - risk_delta),
        is_current=False,
        is_recommended=True,
        route_metadata=json.dumps({'name': f'Alt {name_suffix} Route', 'composite_score': 0.88})
    )
    db.session.add(alt_route)
    db.session.commit()
    agent = RouteOptimizerAgent()
    rec = agent._create_recommendation(shipment, [alt_route], current_route)
    db.session.add(rec)
    db.session.commit()
    return rec


def test_recommendations_api_includes_xai(app, client, sample_data):
    with app.app_context():
        shipment = sample_data['shipment']
        current_route = sample_data['current_route']
        _seed_recommendation(app, shipment, current_route)
        assert Recommendation.query.count() >= 1
    resp = client.get('/api/recommendations/xai?include_xai=1')
    assert resp.status_code == 200
    data = resp.get_json()
    rec = data['recommendations'][0]
    assert 'xai' in rec
    assert 'rationale' in rec['xai'] or 'rationale' in rec
    assert rec.get('confidence') is not None
    assert rec.get('agent')


def test_recommendations_api_exclude_xai(app, client, sample_data):
    with app.app_context():
        shipment = sample_data['shipment']
        current_route = sample_data['current_route']
        _seed_recommendation(app, shipment, current_route, name_suffix='Emissions', cost_factor=1.0, duration_factor=1.05, risk_delta=0.05)
    resp = client.get('/api/recommendations/xai?include_xai=0')
    assert resp.status_code == 200
    payload = resp.get_json()
    any_with_xai = any('xai' in r for r in payload['recommendations'])
    assert not any_with_xai


def test_recommendations_pagination_filters(app, client, sample_data):
    with app.app_context():
        shipment = sample_data['shipment']
        current_route = sample_data['current_route']
        # Seed multiple recs with alternating severity
        for i in range(25):
            rec = _seed_recommendation(app, shipment, current_route, name_suffix=str(i))
            # Force alternating severity on stored record
            rec.severity = 'HIGH' if i % 2 == 0 else 'MEDIUM'
        from app import db
        db.session.commit()
    # Page 2
    # Explicitly request status=PENDING to match stored uppercase status (api lowers comparison)
    r = client.get('/api/recommendations?page=2&per_page=10&status=pending')
    assert r.status_code == 200
    p = r.get_json()
    # If pagination metadata missing, fail with diagnostic
    assert 'page' in p, f"Pagination metadata missing. Response keys: {list(p.keys())}"
    assert p['page'] == 2
    assert p['per_page'] == 10
    # Severity filter
    high = client.get('/api/recommendations?severity=HIGH').get_json()
    assert all(rec['severity'].upper() == 'HIGH' for rec in high['recommendations'])
    # Search filter (match suffix '5')
    search = client.get('/api/recommendations?search=5').get_json()
    assert any('5' in rec['title'] for rec in search['recommendations'])
