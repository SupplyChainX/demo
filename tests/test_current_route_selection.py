from datetime import datetime, timedelta


def test_current_route_aligns_with_selected_mode(client):
    # SEA preference
    sea_payload = {
        "reference_number": "SH-TEST-CURRENT-SEA-001",
        "origin_port": "Shanghai",
        "destination_port": "Rotterdam",
        "carrier": "Maersk",
        "transport_mode": "SEA",
        "scheduled_departure": (datetime.utcnow() + timedelta(days=1)).isoformat(),
        "scheduled_arrival": (datetime.utcnow() + timedelta(days=20)).isoformat(),
    }
    r1 = client.post('/api/shipments', json=sea_payload)
    assert r1.status_code == 201
    s1 = r1.get_json()['id']
    rr1 = client.get(f'/api/shipments/{s1}/routes')
    assert rr1.status_code == 200
    routes1 = rr1.get_json()
    # Find current
    current1 = next((r for r in routes1 if r.get('is_current')), None)
    assert current1 is not None
    # For SEA preference, the chosen route should be SEA if available
    # We can't directly see route_type here, so ensure name/carrier aligns with Maersk when present
    carriers1 = [ (r.get('carrier') or '').lower() for r in routes1 ]
    if any('maersk' in c for c in carriers1):
        assert 'maersk' in (current1.get('carrier') or '').lower() or current1.get('service_type', '').lower() in ['sea','ocean','freight']

    # AIR preference
    air_payload = {
        "reference_number": "SH-TEST-CURRENT-AIR-001",
        "origin_port": "Tokyo",
        "destination_port": "Los Angeles",
        "carrier": "DHL",
        "transport_mode": "AIR",
        "scheduled_departure": (datetime.utcnow() + timedelta(days=1)).isoformat(),
        "scheduled_arrival": (datetime.utcnow() + timedelta(days=7)).isoformat(),
    }
    r2 = client.post('/api/shipments', json=air_payload)
    assert r2.status_code == 201
    s2 = r2.get_json()['id']
    rr2 = client.get(f'/api/shipments/{s2}/routes')
    assert rr2.status_code == 200
    routes2 = rr2.get_json()
    current2 = next((r for r in routes2 if r.get('is_current')), None)
    assert current2 is not None
    carriers2 = [ (r.get('carrier') or '').lower() for r in routes2 ]
    if any('dhl' in c or 'fedex' in c for c in carriers2):
        assert ('dhl' in (current2.get('carrier') or '').lower()) or ('fedex' in (current2.get('carrier') or '').lower())
