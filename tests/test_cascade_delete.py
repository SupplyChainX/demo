import json
from app import db
from app.models import Shipment, Route, RouteType

def test_shipment_delete_cascades_routes(app):
    with app.app_context():
        shipment = Shipment(
            reference_number='CASCADE-001',
            carrier='Maersk',
            origin_port='Shanghai',
            destination_port='Rotterdam',
            transport_mode='SEA'
        )
        db.session.add(shipment)
        db.session.commit()
        # Add two routes
        for i in range(2):
            r = Route(
                shipment_id=shipment.id,
                route_type=RouteType.SEA,
                waypoints='[]',
                distance_km=10000 + i,
                estimated_duration_hours=240,
                cost_usd=50000,
                carbon_emissions_kg=100000,
                risk_score=0.2,
                is_current=(i==0)
            )
            db.session.add(r)
        db.session.commit()
        route_ids = [r.id for r in Route.query.filter_by(shipment_id=shipment.id).all()]
        assert len(route_ids) == 2
        # Delete shipment
        db.session.delete(shipment)
        db.session.commit()
        # Routes should be gone
    remaining = Route.query.filter(Route.id.in_(route_ids)).all()
    assert remaining == []
    assert Route.query.filter_by(shipment_id=shipment.id).count() == 0
