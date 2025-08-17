"""Integration tests for shipment detail unified routes list.

These tests exercise the backend JSON used by the shipment detail page and
assert the unified routes list (current + alternatives) can be rendered by
the front-end logic (single source list via /api/shipments/<id>). We do not
execute JS here, but we validate data structure and invariants that the
front-end relies upon for map and list rendering (e.g., presence of exactly
one current route, alternatives flagged accordingly, waypoints parseable).
"""
import json
import pytest
from app import db
from app.models import Shipment, Route, RouteType


@pytest.mark.usefixtures("app")
def test_unified_routes_endpoint_structure(client):
    """Create a shipment with multiple routes then assert /api/shipments/<id>
    returns a 'routes' array containing both current and alternative routes
    with required fields for front-end rendering.
    """
    # Create shipment
    with client.application.app_context():
        shipment = Shipment(
            workspace_id=1,
            reference_number='UI-TEST-001',
            tracking_number='UI-TEST-001',
            carrier='Maersk',
            origin_port='Shanghai',
            destination_port='Rotterdam',
            origin_lat=31.2304,
            origin_lon=121.4737,
            destination_lat=51.9225,
            destination_lon=4.4792,
            risk_score=0.55,
            transport_mode='SEA'
        )
        db.session.add(shipment)
        db.session.commit()

        # Current route
        current = Route(
            shipment_id=shipment.id,
            route_type=RouteType.SEA,
            waypoints=json.dumps([
                {"name": "Shanghai", "lat": 31.2304, "lon": 121.4737, "type": "port"},
                {"name": "Singapore", "lat": 1.2966, "lon": 103.8060, "type": "port"},
                {"name": "Rotterdam", "lat": 51.9225, "lon": 4.4792, "type": "port"}
            ]),
            distance_km=20000,
            estimated_duration_hours=840,
            cost_usd=150000,
            carbon_emissions_kg=1000000,
            risk_score=0.55,
            is_current=True,
            is_recommended=True
        )
        db.session.add(current)
        # Alternative route
        alt = Route(
            shipment_id=shipment.id,
            route_type=RouteType.SEA,
            waypoints=current.waypoints,
            distance_km=21000,
            estimated_duration_hours=860,
            cost_usd=149000,
            carbon_emissions_kg=990000,
            risk_score=0.50,
            is_current=False,
            is_recommended=False
        )
        db.session.add(alt)
        db.session.commit()
        shipment_id = shipment.id

    # Fetch JSON API used by UI JS
    resp = client.get(f"/api/shipments/{shipment_id}")
    assert resp.status_code == 200
    data = resp.get_json()

    # Validate presence of routes list
    assert 'routes' in data and isinstance(data['routes'], list)
    assert len(data['routes']) == 2

    # Validate exactly one current route
    current_routes = [r for r in data['routes'] if r.get('is_current')]
    assert len(current_routes) == 1
    alt_routes = [r for r in data['routes'] if not r.get('is_current')]
    assert len(alt_routes) == 1

    # Schema checks for front-end consumption
    required_fields = {'id', 'waypoints', 'distance_km', 'estimated_duration_hours', 'cost_usd', 'risk_score'}
    for r in data['routes']:
        assert required_fields.issubset(r.keys())
        # waypoints stored as JSON string that should parse
        wps = json.loads(r['waypoints']) if isinstance(r['waypoints'], str) else r['waypoints']
        assert isinstance(wps, list) and len(wps) >= 2
        for wp in wps:
            assert {'lat', 'lon'}.issubset(wp.keys())

    # Emulate front-end alternative toggle logic: alternatives hidden until toggle
    # (Here we just confirm their presence; actual visibility is JS responsibility.)
    assert all(not r['is_current'] for r in alt_routes)

    # Cleanup
    with client.application.app_context():
        Route.query.filter_by(shipment_id=shipment_id).delete()
        Shipment.query.filter_by(id=shipment_id).delete()
        db.session.commit()
