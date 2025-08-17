import os
import sys
import pytest

# Ensure project root on PYTHONPATH
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app, db
from app.models import Workspace, Shipment, Route, RouteType


@pytest.fixture(scope='session')
def app():
    os.environ.setdefault('MAERSK_API_KEY', 'test-key')
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        # Ensure default workspace exists for tests
        if not db.session.get(Workspace, 1):
            db.session.add(Workspace(id=1, name='Default Workspace', code='DEFAULT'))
            db.session.commit()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def sample_data(app):
    """Provide a sample shipment and a current route for route optimization tests.
    Keep the app context open for the duration of each test to avoid DetachedInstanceError.
    """
    from datetime import datetime, timedelta
    ctx = app.app_context()
    ctx.push()
    try:
        # Create a shipment
        shipment = Shipment(
            workspace_id=1,
            reference_number='TEST-REF-001',
            tracking_number='TEST-REF-001',
            carrier='Maersk',
            origin_port='Shanghai',
            destination_port='Rotterdam',
            origin_lat=31.2304,
            origin_lon=121.4737,
            destination_lat=51.9225,
            destination_lon=4.4792,
            scheduled_departure=datetime.utcnow() + timedelta(days=1),
            scheduled_arrival=datetime.utcnow() + timedelta(days=20),
            risk_score=0.4,
            transport_mode='SEA'
        )
        db.session.add(shipment)
        db.session.commit()

        # Create a current route
        current_route = Route(
            shipment_id=shipment.id,
            route_type=RouteType.SEA,
            waypoints='['
                      '{"name":"Shanghai","lat":31.2304,"lon":121.4737,"type":"port"},'
                      '{"name":"Singapore","lat":1.2966,"lon":103.8060,"type":"port"},'
                      '{"name":"Rotterdam","lat":51.9225,"lon":4.4792,"type":"port"}'
                      '] ',
            distance_km=20000,
            estimated_duration_hours=840,
            cost_usd=150000,
            carbon_emissions_kg=1000000,
            risk_score=0.5,
            is_current=True,
            is_recommended=True
        )
        db.session.add(current_route)
        db.session.commit()

        yield {
            'shipment': shipment,
            'current_route': current_route
        }
    finally:
        # Cleanup and pop context
        try:
            # Remove created rows
            Route.query.filter_by(shipment_id=shipment.id).delete()
            db.session.delete(shipment)
            db.session.commit()
        except Exception:
            db.session.rollback()
        ctx.pop()
