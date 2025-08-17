import os
from app.integrations.carrier_routes import CarrierRouteProvider
from app.models import Shipment


def test_disable_enhanced_carriers_flag_enforces_legacy(app, monkeypatch):
    monkeypatch.setenv('DISABLE_ENHANCED_CARRIERS', '1')
    # Shipment with Maersk to trigger provider selection
    shipment = Shipment(
        reference_number='DET-001',
        carrier='Maersk',
        origin_port='Shanghai',
        destination_port='Rotterdam',
        transport_mode='SEA'
    )
    from app import db
    db.session.add(shipment)
    db.session.commit()
    provider = CarrierRouteProvider.for_carrier(shipment.carrier)
    # Enhanced provider would have attribute enhanced_manager; when disabled should be simple Maersk provider
    from app.integrations.carrier_routes import MaerskCarrierProvider, EnhancedHybridCarrierProvider
    assert not isinstance(provider, EnhancedHybridCarrierProvider)
    assert isinstance(provider, (MaerskCarrierProvider,)) or provider.__class__.__name__ == 'MaerskCarrierProvider'
    db.session.delete(shipment)
    db.session.commit()
