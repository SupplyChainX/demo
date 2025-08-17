"""Tests for RouteOptimizerAgent AI rationale generation fallback paths.

Focus: _create_recommendation unified method and Granite rationale fallback when
 - TESTING config enabled (deterministic path)

We avoid external watsonx calls by relying on TESTING flag which short-circuits
model invocation and returns a deterministic structure.
"""
import json
import pytest

from app import create_app, db
from app.models import Workspace, Shipment, Route, RouteType, Recommendation
from app.agents.route_optimizer import RouteOptimizerAgent


@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        # Minimal workspace (id=1 used implicitly by models)
        ws = Workspace(name="Test WS", code="TST")
        db.session.add(ws)
        db.session.commit()
        yield app
        db.drop_all()


@pytest.fixture
def shipment_with_route(app):
    """Create a shipment with one current route to optimize against."""
    with app.app_context():
        shipment = Shipment(
            workspace_id=1,
            reference_number="OPT-001",
            origin_port="Shanghai",
            destination_port="Los Angeles",
            carrier="Maersk",
            risk_score=0.82,  # high enough to potentially trigger alternative eval
            transport_mode="SEA",
            status="IN_TRANSIT",
        )
        db.session.add(shipment)
        db.session.flush()

        current_route = Route(
            shipment_id=shipment.id,
            route_type=RouteType.SEA,
            waypoints=json.dumps([
                {"name": "Shanghai", "lat": 31.22, "lon": 121.46},
                {"name": "Mid Ocean", "lat": 20.0, "lon": 150.0},
                {"name": "Los Angeles", "lat": 33.73, "lon": -118.26},
            ]),
            distance_km=10000,
            estimated_duration_hours=240,
            cost_usd=50000,
            carbon_emissions_kg=30000,
            risk_score=0.8,
            risk_factors=json.dumps(["weather", "port_congestion"]),
            is_current=True,
            is_recommended=True,
            route_metadata=json.dumps({"name": "Baseline Route", "provider": "maersk"}),
        )
        db.session.add(current_route)
        db.session.commit()
        return shipment.id, current_route.id


def test_create_recommendation_deterministic_fallback(app, shipment_with_route):
    """Ensure _create_recommendation builds a recommendation with deterministic-fallback rationale in TESTING config."""
    shipment_id, current_route_id = shipment_with_route
    with app.app_context():
        agent = RouteOptimizerAgent(app=app)
        from app.models import Shipment as ShipmentModel, Route as RouteModel

        shipment = db.session.get(ShipmentModel, shipment_id)
        current_route = db.session.get(RouteModel, current_route_id)

        # Create an alternative route (recommended)
        alt_route = Route(
            shipment_id=shipment.id,
            route_type=RouteType.SEA,
            waypoints=current_route.waypoints,
            distance_km=current_route.distance_km * 1.05,
            estimated_duration_hours=current_route.estimated_duration_hours * 1.03,
            cost_usd=current_route.cost_usd * 0.97,
            carbon_emissions_kg=current_route.carbon_emissions_kg * 0.98,
            risk_score=current_route.risk_score - 0.1,
            risk_factors=current_route.risk_factors,
            is_current=False,
            is_recommended=True,
            route_metadata=json.dumps({"name": "Optimized Alternative", "provider": "maersk"}),
        )
        db.session.add(alt_route)
        db.session.flush()  # ensure alt_route.id populated

        rec = agent._create_recommendation(shipment, [alt_route], current_route)
        assert rec is not None, "Recommendation should be created"
        assert rec.recommendation_type == 'REROUTE'
        # Severity should be HIGH for list variant per implementation
        assert rec.severity == 'HIGH'
        assert rec.xai_json is not None
        assert rec.xai_json.get('model') == 'deterministic-fallback'
        assert rec.xai_json.get('rationale')
        # Alternatives captured in actions field (legacy data mapping)
        alt_list = rec.actions.get('alternatives') if rec.actions else []
        assert isinstance(alt_list, list)
        assert len(alt_list) >= 1


def test_rationale_fallback_structure_keys(app, shipment_with_route):
    """Validate presence of core keys in fallback rationale block."""
    shipment_id, current_route_id = shipment_with_route
    with app.app_context():
        from app.models import Shipment as ShipmentModel, Route as RouteModel
        agent = RouteOptimizerAgent(app=app)
        shipment = db.session.get(ShipmentModel, shipment_id)
        current_route = db.session.get(RouteModel, current_route_id)
        rec_data = {
            'title': 'Route optimization for OPT-001',
            'current_route': {
                'id': current_route.id,
                'risk_score': current_route.risk_score,
            },
            'alternatives': []
        }
        rationale = agent._build_ai_rationale(shipment, rec_data)
        # Deterministic path should yield fallback structure
        for key in ['rationale', 'factors', 'route_analysis', 'data_sources', 'model', 'confidence']:
            assert key in rationale, f"Missing key {key} in rationale"
        assert rationale['model'] in {'deterministic-fallback', 'fallback-no-api', 'fallback-error'}
