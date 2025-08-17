import os
import pytest
from app.integrations.carrier_routes import DHLCarrierProvider, FedExCarrierProvider, CarrierRouteOption
from app.models import Shipment

@pytest.fixture()
def dummy_shipment(app):
    from app import db
    s = Shipment(
        reference_number='PROVIDER-TEST-001',
        carrier='DHL',
        origin_port='Singapore',
        destination_port='Rotterdam',
        transport_mode='AIR'
    )
    db.session.add(s)
    db.session.commit()
    yield s
    db.session.delete(s)
    db.session.commit()


def _assert_option(opt: CarrierRouteOption):
    assert isinstance(opt.name, str)
    assert isinstance(opt.waypoints, list) and len(opt.waypoints) >= 2
    assert opt.distance_km >= 0
    assert opt.cost_usd >= 0
    assert 0 <= opt.risk_score <= 1


def test_dhl_provider_deterministic(dummy_shipment, monkeypatch):
    monkeypatch.setenv('DISABLE_ENHANCED_CARRIERS', '1')  # Force legacy deterministic path
    provider = DHLCarrierProvider()
    routes = provider.fetch_routes(dummy_shipment)
    assert 1 <= len(routes) <= 8
    for r in routes:
        _assert_option(r)
    # Second call should produce same count under deterministic flag
    routes2 = provider.fetch_routes(dummy_shipment)
    assert len(routes) == len(routes2)


def test_fedex_provider_deterministic(app, monkeypatch):
    from app import db
    monkeypatch.setenv('DISABLE_ENHANCED_CARRIERS', '1')
    shipment = Shipment(
        reference_number='PROVIDER-TEST-002',
        carrier='FedEx',
        origin_port='Los Angeles',
        destination_port='New York',
        transport_mode='AIR'
    )
    db.session.add(shipment)
    db.session.commit()
    provider = FedExCarrierProvider()
    routes = provider.fetch_routes(shipment)
    assert len(routes) > 0
    for r in routes:
        _assert_option(r)
    # Determinism: re-fetch
    routes2 = provider.fetch_routes(shipment)
    assert len(routes) == len(routes2)
    db.session.delete(shipment)
    db.session.commit()
