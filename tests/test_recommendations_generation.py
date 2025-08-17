import json
from app import create_app, db
from app.models import Shipment, Recommendation, Route, RouteType
from app.agents.route_optimizer import RouteOptimizerAgent

def test_high_risk_shipment_generates_recommendation(client):
    app = client.application
    with app.app_context():
        # Create a high-risk shipment with a current route
        shipment = Shipment(
            workspace_id=1,
            reference_number='HR-001',
            tracking_number='HR-001',
            origin_port='Shanghai',
            destination_port='Los Angeles',
            carrier='Maersk Line',
            risk_score=0.9,
            transport_mode='SEA'
        )
        db.session.add(shipment)
        db.session.commit()
        # Add a current route
        route = Route(
            shipment_id=shipment.id,
            route_type=RouteType.SEA,
            waypoints=json.dumps([
                {'name':'Shanghai','lat':31.22,'lon':121.46},
                {'name':'Pacific Waypoint','lat':20.0,'lon':150.0},
                {'name':'Los Angeles','lat':33.73,'lon':-118.26}
            ]),
            distance_km=10000,
            estimated_duration_hours=300,
            cost_usd=100000,
            carbon_emissions_kg=50000,
            risk_score=0.85,
            is_current=True,
            is_recommended=True,
            route_metadata=json.dumps({'name':'Baseline Route'})
        )
    db.session.add(route)
    db.session.commit()
    # Ensure no recommendations yet for this shipment
    assert Recommendation.query.filter_by(subject_id=shipment.id).count() == 0
    # Call recommendations endpoint with trigger_generation
    resp = client.get('/api/recommendations?trigger_generation=1&include_xai=1&per_page=10')
    assert resp.status_code == 200
    data = resp.get_json()
    # After trigger there should be at least one recommendation
    assert data['total'] >= 1
    rec = data['recommendations'][0]
    assert 'xai' in rec or 'rationale' in rec
    # Direct DB check
    assert Recommendation.query.filter_by(subject_id=shipment.id).count() >= 1

