import json
from app.models import Shipment, Route, RouteType
from app import db

def test_shipment_detail_template_renders(client, app):
    """Smoke test: shipment detail page renders with unified route UI and no template errors."""
    with app.app_context():
        shipment = Shipment(
            workspace_id=1,
            reference_number='TEST-SH-001',
            origin_port='Shanghai',
            destination_port='Los Angeles',
            carrier='Maersk Line',
            risk_score=0.42,
            transport_mode='SEA'
        )
        db.session.add(shipment)
        db.session.commit()
        # Add a current route
        route = Route(
            shipment_id=shipment.id,
            route_type='SEA',
            waypoints=json.dumps([
                {"name":"Shanghai","lat":31.22,"lon":121.46,"type":"ORIGIN"},
                {"name":"Mid Ocean","lat":20.0,"lon":150.0,"type":"WAYPOINT"},
                {"name":"Los Angeles","lat":33.73,"lon":-118.26,"type":"DESTINATION"}
            ]),
            distance_km=10000,
            estimated_duration_hours=240,
            cost_usd=75000,
            carbon_emissions_kg=30000,
            risk_score=0.42,
            risk_factors=json.dumps(["weather"]),
            is_current=True,
            is_recommended=True,
            route_metadata=json.dumps({"name":"Maersk - Standard"})
        )
        db.session.add(route)
        db.session.commit()
        url = f"/shipments/{shipment.id}"
    resp = client.get(url)
    assert resp.status_code == 200
    html = resp.data.decode()
    # Key structural markers
    assert 'Route Map' in html
    assert 'All Routes' in html
    # Ensure only one All Routes header element (comment occurrences ignored)
    assert html.count('<h5 class="mb-0">All Routes') == 1
    # Comparison table present when current route exists
    assert 'Route Comparison' in html
    # No legacy duplicate alternatives table wording
    assert 'Alternative Routes' not in html
    # Embedded JSON script tag present
    assert 'shipment-route-data' in html
