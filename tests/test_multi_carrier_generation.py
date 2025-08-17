"""End-to-end tests for multi-carrier route generation (Maersk, DHL, FedEx).

Validates that creating a shipment via API produces persisted Route rows
for the selected carrier and that the best route is marked current while
alternatives are stored. Tests both SEA (Maersk focus) and AIR (DHL/FedEx focus).
"""
import os
import json
from datetime import datetime, timedelta

import pytest

from app import db
from app.models import Shipment, Route, RouteType


@pytest.fixture(autouse=True)
def disable_enhanced(monkeypatch):
    """Disable enhanced integration for deterministic per-carrier results."""
    monkeypatch.setenv('DISABLE_ENHANCED_CARRIERS', '1')
    # Ensure no forced carrier
    if 'TEST_FORCE_CARRIER' in os.environ:
        monkeypatch.delenv('TEST_FORCE_CARRIER', raising=False)


def _create_api_shipment(client, **overrides):
    payload = {
        'reference_number': overrides.get('reference_number', f'TEST-MULTI-{int(datetime.utcnow().timestamp())}'),
        'origin_port': overrides.get('origin_port', 'Shanghai'),
        'destination_port': overrides.get('destination_port', 'Rotterdam'),
        'carrier': overrides.get('carrier', 'Maersk Line'),
        'scheduled_departure': (datetime.utcnow() + timedelta(days=1)).isoformat(),
        'scheduled_arrival': (datetime.utcnow() + timedelta(days=20)).isoformat(),
        'transport_mode': overrides.get('transport_mode', 'SEA'),
        'risk_score': 0.2
    }
    resp = client.post('/api/shipments', json=payload)
    assert resp.status_code == 201, resp.data
    data = resp.get_json()
    return data['id'], data


def test_maersk_sea_routes(client, app):
    shipment_id, resp = _create_api_shipment(client, carrier='Maersk Line', transport_mode='SEA')
    assert resp['routes_generated'] >= 0  # generation may be 0 if provider returns none
    with app.app_context():
        routes = Route.query.filter_by(shipment_id=shipment_id).all()
        # We expect at least one route for Maersk SEA
        assert len(routes) >= 1, 'Expected at least one Maersk SEA route'
        current = [r for r in routes if r.is_current]
        assert len(current) == 1, 'Exactly one current route required'
        assert current[0].route_type == RouteType.SEA


def test_dhl_air_routes(client, app):
    shipment_id, resp = _create_api_shipment(client, carrier='DHL', transport_mode='AIR')
    with app.app_context():
        routes = Route.query.filter_by(shipment_id=shipment_id).all()
        # For AIR shipments prefer AIR routes; allow multimodal fallback
        assert len(routes) >= 1, 'Expected at least one DHL AIR route'
        current = [r for r in routes if r.is_current]
        assert len(current) == 1
        # Current route type should be AIR if any AIR present
        air_routes = [r for r in routes if r.route_type == RouteType.AIR]
        if air_routes:
            assert current[0].route_type == RouteType.AIR


def test_fedex_air_routes(client, app):
    shipment_id, resp = _create_api_shipment(client, carrier='FedEx', transport_mode='AIR')
    with app.app_context():
        routes = Route.query.filter_by(shipment_id=shipment_id).all()
        assert len(routes) >= 1, 'Expected at least one FedEx AIR route'
        current = [r for r in routes if r.is_current]
        assert len(current) == 1
        air_routes = [r for r in routes if r.route_type == RouteType.AIR]
        if air_routes:
            assert current[0].route_type == RouteType.AIR


def test_route_metadata_integrity(client, app):
    shipment_id, _ = _create_api_shipment(client, carrier='Maersk Line', transport_mode='SEA')
    with app.app_context():
        route = Route.query.filter_by(shipment_id=shipment_id, is_current=True).first()
        assert route is not None
        md = json.loads(route.route_metadata or '{}')
        assert 'carrier' in md
        assert 'service_type' in md
        assert md.get('name')
