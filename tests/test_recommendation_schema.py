import json
from app.models import Recommendation, Shipment, Route, RouteType
from app import db

def test_recommendation_xai_schema(app, sample_data):
    shipment = sample_data['shipment']
    current_route = sample_data['current_route']
    # Create mock alternative
    alt_route = Route(
        shipment_id=shipment.id,
        route_type=RouteType.SEA,
        waypoints=current_route.waypoints,
        distance_km=current_route.distance_km * 1.05,
        estimated_duration_hours=current_route.estimated_duration_hours * 0.95,
        cost_usd=current_route.cost_usd * 0.9,
        carbon_emissions_kg=current_route.carbon_emissions_kg * 0.92,
        risk_score=current_route.risk_score * 0.7,
        is_current=False
    )
    db.session.add(alt_route)
    db.session.commit()

    rationale = {
        'rationale': 'Alternative reduces cost and emissions while acceptable risk.',
        'factors': ['cost_optimization','risk_reduction','emissions'],
        'improvements': {
            'cost_delta': -0.1,
            'emissions_delta': -0.08,
            'risk_delta': -0.3
        },
        'data_sources': ['internal_metrics']
    }
    rec = Recommendation(
        recommendation_type='REROUTE',
        subject_type='shipment',
        subject_id=shipment.id,
        subject_ref=f'shipment:{shipment.id}',
        title='Reroute to reduce cost/emissions',
        description='Switch to alternative route to improve KPIs',
        severity='MEDIUM',
        confidence=0.85,
        data={'current_route_id': current_route.id, 'recommended_route_id': alt_route.id},
        rationale=rationale,
        created_by='RouteOptimizer'
    )
    db.session.add(rec)
    db.session.commit()

    # Validate schema
    loaded = json.loads(rec.rationale)
    assert 'rationale' in loaded
    assert 'factors' in loaded and isinstance(loaded['factors'], list)
    assert 'improvements' in loaded or 'route_analysis' in loaded
    assert 'data_sources' in loaded

    # Clean up
    db.session.delete(rec)
    db.session.delete(alt_route)
    db.session.commit()
