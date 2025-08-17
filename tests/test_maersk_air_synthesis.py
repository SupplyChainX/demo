import json
import os
from datetime import datetime, timedelta

from app.models import Shipment, Route, RouteType
from app import db


def test_maersk_air_synthesized_when_air_requested(app, client):
    """Requesting a Maersk shipment with transport_mode AIR should yield a synthetic Maersk AIR route.

    Ensures logic in get_multi_carrier_routes that adds a Maersk Air Express option
    when original_mode == AIR and no native Maersk air product exists.
    """
    os.environ.setdefault('MAERSK_API_KEY', 'test-key')  # ensure provider passes key check
    payload = {
        'reference_number': 'TEST-MAERSK-AIR-SYNTH',
        'origin_port': 'Rotterdam',
        'destination_port': 'Shanghai',
        'carrier': 'Maersk Line',
        'scheduled_departure': (datetime.utcnow() + timedelta(days=1)).isoformat(),
        'scheduled_arrival': (datetime.utcnow() + timedelta(days=20)).isoformat(),
        'transport_mode': 'AIR'
    }

    resp = client.post('/api/shipments', json=payload)
    assert resp.status_code == 201, resp.data
    shipment_id = resp.get_json()['id']

    with app.app_context():
        shipment = db.session.get(Shipment, shipment_id)
        assert shipment.transport_mode == 'AIR'
        routes = Route.query.filter_by(shipment_id=shipment_id).all()
        assert routes, 'Expected routes to be generated'
        # Filter Maersk routes
        maersk_routes = []
        for r in routes:
            md = json.loads(r.route_metadata or '{}')
            if (md.get('carrier') or '').lower().startswith('maersk'):
                maersk_routes.append((r, md))
        assert maersk_routes, 'Expected at least one Maersk route'
        air_maersk = [r for r, md in maersk_routes if r.route_type == RouteType.AIR]
        assert air_maersk, 'Expected a synthesized Maersk AIR route when AIR requested'
        # Validate synthesized characteristics (higher cost vs a sea route)
        sea_maersk = [r for r, md in maersk_routes if r.route_type == RouteType.SEA]
        if sea_maersk:
            # Compare first air vs first sea
            sea = sea_maersk[0]
            air = air_maersk[0]
            assert air.cost_usd > sea.cost_usd, 'Air route should cost more than sea route'
            assert air.estimated_duration_hours < sea.estimated_duration_hours, 'Air route should be faster than sea route'
            # Emissions multiplier (synth logic uses *4.5). Allow tolerance >= 3x to avoid brittle test.
            assert air.carbon_emissions_kg > (sea.carbon_emissions_kg or 0) * 3, 'Air emissions should be significantly higher than sea emissions'
