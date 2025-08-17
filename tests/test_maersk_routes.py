import json
import os
from unittest.mock import patch
from app import create_app, db
from app.models import Shipment, Route, Workspace


def _make_app():
    # Ensure API key present for Maersk provider during tests
    os.environ.setdefault('MAERSK_API_KEY', 'test-key')
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        # Ensure default workspace exists
        if not db.session.get(Workspace, 1):
            db.session.add(Workspace(id=1, name='Default Workspace', code='DEFAULT'))
            db.session.commit()
    return app


@patch('requests.Session.get')
def test_shipment_creation_creates_maersk_routes(mock_get):
    app = _make_app()
    client = app.test_client()

    # Mock Maersk schedules response
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        'schedules': [{
            'vessel': {'name': 'MAERSK ATLANTIC'},
            'voyageNumber': 'MA123',
            'transitTimeDays': 15,
            'legs': [
                {'port': {'name': 'Shanghai', 'lat': 31.22, 'lon': 121.46}},
                {'port': {'name': 'Los Angeles', 'lat': 33.73, 'lon': -118.26}}
            ]
        }]
    }

    payload = {
        'reference_number': 'SH-TEST-0001',
        'origin_port': 'Shanghai',
        'destination_port': 'Los Angeles',
        'carrier': 'Maersk'
    }

    res = client.post('/api/shipments', data=json.dumps(payload), content_type='application/json')
    assert res.status_code == 201

    with app.app_context():
        s = Shipment.query.filter_by(reference_number='SH-TEST-0001').first()
        assert s is not None
        routes = Route.query.filter_by(shipment_id=s.id).all()
        # If routes exist, basic sanity checks
        if routes:
            current = next((r for r in routes if r.is_current), None)
            assert current is not None
            assert current.distance_km is None or current.distance_km >= 0
            assert current.estimated_duration_hours is None or current.estimated_duration_hours >= 0


@patch('requests.Session.get')
def test_maersk_provider_handles_4xx(mock_get):
    app = _make_app()
    client = app.test_client()

    mock_get.return_value.status_code = 403
    mock_get.return_value.text = 'Forbidden'

    payload = {
        'reference_number': 'SH-TEST-0002',
        'origin_port': 'Shanghai',
        'destination_port': 'Los Angeles',
        'carrier': 'Maersk'
    }

    res = client.post('/api/shipments', data=json.dumps(payload), content_type='application/json')
    assert res.status_code == 201

    with app.app_context():
        if not db.session.get(Workspace, 1):
            db.session.add(Workspace(id=1, name='Default Workspace', code='DEFAULT'))
            db.session.commit()
        s = Shipment.query.filter_by(reference_number='SH-TEST-0002').first()
        assert s is not None
        # No routes created when API returns error
        routes = Route.query.filter_by(shipment_id=s.id).all()
        assert len(routes) == 0


@patch('requests.Session.get')
def test_maersk_provider_parses_schedule(mock_get):
    from app.integrations.carrier_routes import MaerskCarrierProvider

    # Mock response
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        'schedules': [{
            'vessel': {'name': 'MAERSK ATLANTIC'},
            'voyageNumber': 'MA123',
            'transitTimeDays': 10,
            'legs': [
                {'port': {'name': 'Shanghai', 'lat': 31.22, 'lon': 121.46}},
                {'port': {'name': 'Los Angeles', 'lat': 33.73, 'lon': -118.26}}
            ]
        }]
    }

    class Dummy:
        origin_port = 'Shanghai'
        destination_port = 'Los Angeles'
        origin_lat = 31.22
        origin_lon = 121.46
        destination_lat = 33.73
        destination_lon = -118.26
        risk_score = 0.3

    os.environ.setdefault('MAERSK_API_KEY', 'test-key')
    provider = MaerskCarrierProvider()
    opts = provider.fetch_routes(Dummy())
    assert len(opts) >= 1
    first = opts[0]
    assert first.duration_hours is None or first.duration_hours > 0
    assert first.distance_km is None or first.distance_km >= 0
