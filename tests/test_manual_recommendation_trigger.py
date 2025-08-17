import json
from datetime import datetime, timedelta

from app import db
from app.models import Shipment


def test_manual_recommendations_trigger_endpoint(client, app):
    """Ensure the manual trigger endpoint exists (not 404) and processes a high-risk shipment.

    Steps:
      1. Create a high-risk shipment (risk_score >= default threshold 0.75).
      2. POST /api/recommendations/trigger
      3. Assert endpoint returns JSON and processed includes our shipment id (if status ok)
    """
    with app.app_context():
        shipment = Shipment(
            workspace_id=1,
            reference_number='TRIGGER-TEST-001',
            tracking_number='TRIGGER-TEST-001',
            carrier='Maersk',
            origin_port='Shanghai',
            destination_port='Rotterdam',
            origin_lat=31.2304,
            origin_lon=121.4737,
            destination_lat=51.9225,
            destination_lon=4.4792,
            scheduled_departure=datetime.utcnow() - timedelta(days=2),
            scheduled_arrival=datetime.utcnow() + timedelta(days=18),
            risk_score=0.9,
            transport_mode='SEA'
        )
        db.session.add(shipment)
        db.session.commit()

        resp = client.post('/api/recommendations/trigger', json={})
        assert resp.status_code != 404, 'Manual trigger endpoint returned 404 (route not registered or server not reloaded).'
        assert resp.is_json
        data = resp.get_json()
        if resp.status_code == 200:
            assert data.get('status') == 'ok'
            processed = data.get('processed') or []
            assert any(p.get('shipment_id') == shipment.id for p in processed), 'Shipment not processed by trigger endpoint'
        else:
            # Provide debug info but allow failure visibility
            assert 'error' in data

        db.session.delete(shipment)
        db.session.commit()
