import json
from datetime import datetime, timedelta


def test_api_creates_multi_carrier_routes(client):
    # Create a shipment via API with SEA mode
    payload = {
        "reference_number": "SH-TEST-MULTI-001",
        "origin_port": "Shanghai",
        "destination_port": "Los Angeles",
        "carrier": "Maersk",  # preference, but should get all carriers
        "transport_mode": "SEA",
        "scheduled_departure": (datetime.utcnow() + timedelta(days=1)).isoformat(),
        "scheduled_arrival": (datetime.utcnow() + timedelta(days=20)).isoformat(),
        "risk_score": 0.2,
        "weight_tons": 10,
        "cargo_value_usd": 500000
    }

    r = client.post('/api/shipments', json=payload)
    assert r.status_code == 201, r.get_data(as_text=True)
    created = r.get_json()
    shipment_id = created['id']
    assert shipment_id > 0
    assert created.get('routes_generated', 0) >= 1

    # Fetch routes
    rr = client.get(f'/api/shipments/{shipment_id}/routes')
    assert rr.status_code == 200
    routes = rr.get_json()
    assert isinstance(routes, list)
    assert len(routes) >= 1

    # Verify at least one Maersk (SEA) and one AIR (DHL or FedEx) option exist overall
    carriers = []
    for route in routes:
        carriers.append(route.get('carrier'))

    # carrier field is filled from route_metadata in API; ensure presence
    assert any(c and 'Maersk' in str(c) for c in carriers), f"carriers present: {carriers}"
    # At least one non-Maersk (e.g., DHL or FedEx)
    assert any(c and (('DHL' in str(c)) or ('Fedex' in str(c)) or ('FedEx' in str(c))) for c in carriers), f"carriers present: {carriers}"

    # Fetch full shipment detail and ensure routes list present
    sd = client.get(f'/api/shipments/{shipment_id}')
    assert sd.status_code == 200
    detail = sd.get_json()
    assert 'routes' in detail and isinstance(detail['routes'], list) and len(detail['routes']) >= 1
