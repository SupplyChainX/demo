import json
from datetime import datetime, timedelta

from app.models import Shipment, Route, RouteType
from app import db


def _create_air_shipment(client, carrier: str, ref: str):
    payload = {
        'reference_number': ref,
        'origin_port': 'Rotterdam',
        'destination_port': 'Shanghai',
        'carrier': carrier,
        'scheduled_departure': (datetime.utcnow() + timedelta(days=1)).isoformat(),
        'scheduled_arrival': (datetime.utcnow() + timedelta(days=7)).isoformat(),
        'transport_mode': 'AIR'
    }
    resp = client.post('/api/shipments', json=payload)
    assert resp.status_code == 201, resp.data
    return resp.get_json()['id']


def test_dhl_air_routes_have_air_current(app, client):
    shipment_id = _create_air_shipment(client, 'DHL', 'TEST-DHL-AIR-1')
    with app.app_context():
        routes = Route.query.filter_by(shipment_id=shipment_id).all()
        assert routes, 'Expected DHL routes generated'
        air_routes = [r for r in routes if r.route_type == RouteType.AIR]
        # All DHL routes should classify as AIR or at least have one AIR
        assert air_routes, 'Expected at least one DHL AIR route'
        current = next((r for r in routes if r.is_current), None)
        assert current is not None, 'A current route must be set'
        if air_routes:
            assert current.route_type == RouteType.AIR, 'Current DHL route should be AIR'


def test_fedex_air_routes_have_air_current(app, client):
    shipment_id = _create_air_shipment(client, 'FedEx', 'TEST-FEDEX-AIR-1')
    with app.app_context():
        routes = Route.query.filter_by(shipment_id=shipment_id).all()
        assert routes, 'Expected FedEx routes generated'
        air_routes = [r for r in routes if r.route_type == RouteType.AIR]
        assert air_routes, 'Expected at least one FedEx AIR route'
        current = next((r for r in routes if r.is_current), None)
        assert current is not None
        if air_routes:
            assert current.route_type == RouteType.AIR, 'Current FedEx route should be AIR'


def test_air_routes_cost_vs_duration_relationship(app, client):
    """Basic heuristic: For both DHL and FedEx, faster services (lower duration) should not cost dramatically less than slower ones."""
    dhl_id = _create_air_shipment(client, 'DHL', 'TEST-DHL-AIR-2')
    fedex_id = _create_air_shipment(client, 'FedEx', 'TEST-FEDEX-AIR-2')
    with app.app_context():
        for sid in (dhl_id, fedex_id):
            routes = Route.query.filter_by(shipment_id=sid).all()
            air_routes = [r for r in routes if r.route_type == RouteType.AIR]
            if len(air_routes) >= 2:
                sorted_by_time = sorted(air_routes, key=lambda r: r.estimated_duration_hours or 1e9)
                fastest, slowest = sorted_by_time[0], sorted_by_time[-1]
                if fastest.cost_usd and slowest.cost_usd:
                    # Fastest shouldn't be dramatically cheaper than slowest (allow some variance for synthetic data)
                    if slowest.cost_usd > 0:
                        ratio = fastest.cost_usd / slowest.cost_usd
                        # Allow more variance but flag egregious underpricing (<75%) beyond a small absolute tolerance
                        if ratio < 0.75 and (slowest.cost_usd - fastest.cost_usd) > 15000:
                            assert False, 'Fastest air service priced implausibly low'
