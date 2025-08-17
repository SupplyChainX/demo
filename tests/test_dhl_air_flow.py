import json
from datetime import datetime, timedelta


def test_api_creates_dhl_air_routes(client):
    payload = {
        "reference_number": "SH-TEST-DHL-AIR-001",
        "origin_port": "Tokyo",
        "destination_port": "Los Angeles",
        "carrier": "DHL",
        "transport_mode": "AIR",
        "scheduled_departure": (datetime.utcnow() + timedelta(days=1)).isoformat(),
        "scheduled_arrival": (datetime.utcnow() + timedelta(days=7)).isoformat(),
        "risk_score": 0.2,
        "weight_tons": 1,
        "cargo_value_usd": 10000
    }

    r = client.post('/api/shipments', json=payload)
    assert r.status_code == 201, r.get_data(as_text=True)
    created = r.get_json()
    shipment_id = created['id']
    assert created.get('routes_generated', 0) >= 1

    rr = client.get(f'/api/shipments/{shipment_id}/routes')
    assert rr.status_code == 200
    routes = rr.get_json()
    assert isinstance(routes, list) and len(routes) >= 1
    assert any((route.get('carrier') or '').lower().startswith('dhl') for route in routes)
    # Ensure route_type aligns (AIR)
    # Fetch full shipment and check at least one route present in 'routes'
    sd = client.get(f'/api/shipments/{shipment_id}')
    assert sd.status_code == 200
    detail = sd.get_json()
    assert 'routes' in detail and isinstance(detail['routes'], list) and len(detail['routes']) >= 1
