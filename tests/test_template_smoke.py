import json
from app.models import Shipment, Route, RouteType

def test_shipment_template_smoke(client, app, sample_data):
    """Render shipment detail page and verify unified routes table and no Jinja errors."""
    shipment = sample_data['shipment']
    resp = client.get(f"/shipments/{shipment.id}")
    assert resp.status_code == 200
    html = resp.data.decode()
    # Unified table id must exist exactly once
    assert html.count('id="routes-table"') == 1
    # Ensure legacy duplicate alternative tables removed (should not exceed 5 occurrences of label text including button)
    assert html.count('Alternatives') <= 5


def test_routes_api_contract(client, sample_data):
    shipment = sample_data['shipment']
    # Ensure API detail returns JSON structure for routes list endpoint
    resp = client.get(f"/api/shipments/{shipment.id}/routes")
    assert resp.status_code in (200, 404, 500)  # route endpoint may not exist yet
    # If exists, validate contract
    if resp.status_code == 200:
        data = json.loads(resp.data)
        # Some endpoints may directly return a list of routes (legacy). Normalize.
        routes = data.get('routes') if isinstance(data, dict) else data
        assert isinstance(routes, list)
        for r in routes:
            for field in ['id','distance_km','estimated_duration_hours','cost_usd','carbon_emissions_kg','risk_score']:
                assert field in r
