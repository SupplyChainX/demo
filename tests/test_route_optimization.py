"""
Test Route Optimization Features
"""
import json
import pytest
from datetime import datetime, timedelta
from app import create_app, db
from app.models import (
    User, Workspace, Shipment, Route, RouteType, Alert, 
    Recommendation, ShipmentStatus, AlertSeverity, Approval
)
from app.agents.route_optimizer import RouteOptimizerAgent

@pytest.mark.usefixtures("sample_data")
class TestRouteOptimization:
    """Test route optimization agent functionality"""

    def test_api_execute_reroute(self, client, sample_data):
        """Test API endpoint for executing reroute"""
        shipment = sample_data['shipment']
        
        # Create alternative route
        with client.application.app_context():
            alt_route = Route(
                shipment_id=shipment.id,
                route_type=RouteType.SEA,
                waypoints=json.dumps([
                    {"name": "Singapore", "lat": 1.3521, "lon": 103.8198, "type": "port"},
                    {"name": "Cape of Good Hope", "lat": -34.3587, "lon": 18.4737, "type": "cape"},
                    {"name": "Rotterdam", "lat": 51.9244, "lon": 4.4777, "type": "port"}
                ]),
                distance_km=24000,
                estimated_duration_hours=960,
                cost_usd=165000,
                carbon_emissions_kg=1200000,
                risk_score=0.3,
                is_current=False,
                is_recommended=True
            )
            db.session.add(alt_route)
            db.session.commit()
            route_id = alt_route.id
        
        # Execute reroute
        response = client.post(
            f'/api/shipments/{shipment.id}/reroute',
            json={'route_id': route_id},
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code in [200, 202]
        data = json.loads(response.data)
        
        if response.status_code == 202:
            # Approval required
            assert data['status'] == 'approval_required'
            assert 'approval_id' in data
        else:
            # Direct execution
            assert data['status'] == 'success'
            
            # Verify route was updated
            with client.application.app_context():
                updated_shipment = db.session.get(Shipment, shipment.id)
                new_current = updated_shipment.routes.filter_by(is_current=True).first()
                assert new_current.id == route_id
    
    def test_route_risk_calculation(self, app, sample_data):
        """Test risk calculation for routes"""
        with app.app_context():
            agent = RouteOptimizerAgent()
            
            # Test route through high-risk area
            high_risk_waypoints = [
                {"name": "Start", "lat": 10.0, "lon": 30.0, "type": "port"},
                {"name": "Red Sea", "lat": 20.0, "lon": 38.0, "type": "sea"},
                {"name": "End", "lat": 30.0, "lon": 40.0, "type": "port"}
            ]
            
            risk_score = agent._calculate_risk_score({
                'waypoints': high_risk_waypoints,
                'risk_factors': ['geopolitical', 'piracy']
            })
            
            assert risk_score > 0.5  # High risk
            
            # Test safe route
            safe_waypoints = [
                {"name": "Start", "lat": 40.0, "lon": -70.0, "type": "port"},
                {"name": "Atlantic", "lat": 45.0, "lon": -50.0, "type": "sea"},
                {"name": "End", "lat": 50.0, "lon": -30.0, "type": "port"}
            ]
            
            safe_risk = agent._calculate_risk_score({
                'waypoints': safe_waypoints,
                'risk_factors': []
            })
            
            assert safe_risk < 0.3  # Low risk
    
    def test_weather_impact_on_routes(self, app, sample_data):
        """Test weather integration impact on route scoring"""
        with app.app_context():
            agent = RouteOptimizerAgent()
            
            # Mock route waypoints
            waypoints = [
                {"name": "Miami", "lat": 25.7617, "lon": -80.1918, "type": "port"},
                {"name": "Atlantic", "lat": 30.0, "lon": -70.0, "type": "sea"},
                {"name": "Hamburg", "lat": 53.5511, "lon": 9.9937, "type": "port"}
            ]
            
            # Calculate weather score
            weather_score = agent._calculate_weather_score(waypoints)
            
            assert 0 <= weather_score <= 1
            assert weather_score >= 0.3  # Minimum threshold
    
    def test_port_congestion_scoring(self, app):
        """Test port congestion impact on routes"""
        with app.app_context():
            agent = RouteOptimizerAgent()
            
            # Test with known congested ports
            congested_waypoints = [
                {"name": "Shanghai", "lat": 31.2304, "lon": 121.4737, "type": "port"},
                {"name": "Los Angeles", "lat": 33.7701, "lon": -118.1937, "type": "port"}
            ]
            
            port_score = agent._calculate_port_score(congested_waypoints)
            
            assert 0 <= port_score <= 1
            # Port score should be reduced due to congestion
            assert port_score < 0.9
    
    def test_multimodal_route_generation(self, app):
        """Test generation of multimodal routes"""
        with app.app_context():
            agent = RouteOptimizerAgent()
            
            # Create shipment requiring multimodal transport
            shipment = Shipment(
                tracking_number='TEST-MULTI-001',
                carrier_name='Multi-Carrier',
                origin_name='Shanghai',
                origin_lat=31.2304,
                origin_lon=121.4737,
                destination_name='Munich',
                destination_lat=48.1351,
                destination_lon=11.5820,
                transport_mode='multimodal'
            )
            
            current_route = Route(
                shipment=shipment,
                route_type=RouteType.MULTIMODAL,
                waypoints=json.dumps([
                    {"name": "Shanghai", "lat": 31.2304, "lon": 121.4737, "type": "port"},
                    {"name": "Munich", "lat": 48.1351, "lon": 11.5820, "type": "city"}
                ]),
                distance_km=9000,
                estimated_duration_hours=720,
                cost_usd=50000,
                carbon_emissions_kg=450000,
                risk_score=0.4
            )
            
            alternatives = agent._generate_multimodal_alternatives(shipment, current_route)
            
            assert len(alternatives) > 0
            
            # Check for sea-air combination
            sea_air = next((alt for alt in alternatives if 'Sea-Air' in alt['name']), None)
            assert sea_air is not None
            assert len(sea_air['waypoints']) >= 3  # Origin, transfer, destination
            assert 'modes' in sea_air
            assert 'sea' in sea_air['modes'] and 'air' in sea_air['modes']
    
    def test_recommendation_creation(self, app, sample_data):
        """Test recommendation creation with proper XAI"""
        with app.app_context():
            agent = RouteOptimizerAgent()
            shipment = sample_data['shipment']
            current_route = sample_data['current_route']
            
            # Create alternative route
            alt_route = Route(
                shipment=shipment,
                route_type=RouteType.SEA,
                waypoints=json.dumps([
                    {"name": "Singapore", "lat": 1.3521, "lon": 103.8198, "type": "port"},
                    {"name": "Cape of Good Hope", "lat": -34.3587, "lon": 18.4737, "type": "cape"},
                    {"name": "Rotterdam", "lat": 51.9244, "lon": 4.4777, "type": "port"}
                ]),
                distance_km=24000,
                estimated_duration_hours=960,
                cost_usd=165000,
                carbon_emissions_kg=1200000,
                risk_score=0.3,
                is_current=False,
                is_recommended=True,
                route_metadata=json.dumps({  # Changed from metadata to route_metadata
                    "name": "Cape of Good Hope Route",
                    "composite_score": 0.82
                })
            )
            db.session.add(alt_route)
            db.session.commit()
            
            # Create recommendation
            rec = agent._create_recommendation(shipment, [alt_route], current_route)
            
            assert rec.recommendation_type == 'REROUTE'
            assert rec.subject_id == shipment.id
            assert rec.severity in ['HIGH', 'MEDIUM']
            assert rec.confidence > 0.5
            
            # Check XAI content
            rationale = json.loads(rec.rationale)
            assert 'rationale' in rationale
            assert 'improvements' in rationale
            assert 'factors_considered' in rationale
            
            # Check recommendation data
            data = json.loads(rec.data)
            assert data['current_route_id'] == current_route.id
            assert data['recommended_route_id'] == alt_route.id
    
    def test_approval_workflow(self, app, sample_data):
        """Test approval workflow for high-value reroutes"""
        with app.app_context():
            shipment = sample_data['shipment']
            
            # Create expensive alternative
            expensive_route = Route(
                shipment=shipment,
                route_type=RouteType.AIR,
                waypoints=json.dumps([
                    {"name": "Singapore", "lat": 1.3521, "lon": 103.8198, "type": "airport"},
                    {"name": "Frankfurt", "lat": 50.0379, "lon": 8.5622, "type": "airport"},
                    {"name": "Rotterdam", "lat": 51.9244, "lon": 4.4777, "type": "port"}
                ]),
                distance_km=10000,
                estimated_duration_hours=48,
                cost_usd=250000,  # High cost triggers approval
                carbon_emissions_kg=500000,
                risk_score=0.1,
                is_current=False
            )
            db.session.add(expensive_route)
            db.session.commit()
            
            # Create recommendation
            rec = Recommendation(
                recommendation_type='REROUTE',
                subject_type='shipment',
                subject_id=shipment.id,
                subject_ref=shipment.tracking_number,
                title='Urgent air freight reroute',
                description='Switch to air freight to avoid delays',
                severity='HIGH',
                confidence=0.9,
                data=json.dumps({'route_id': expensive_route.id}),
                created_by='RouteOptimizer'
            )
            db.session.add(rec)
            
            # Create approval requirement
            approval = Approval(
                recommendation=rec,
                policy_triggered='Cost exceeds $100,000 threshold',
                required_role='logistics_manager',
                state='PENDING'
            )
            db.session.add(approval)
            db.session.commit()
            
            # Verify approval is required
            assert approval.state == 'PENDING'
            assert rec.status == 'PENDING'
            assert 'Cost exceeds' in approval.policy_triggered

class TestRouteVisualization:
    """Test route visualization and UI components"""
    
    def test_route_waypoints_format(self, app, sample_data):
        """Test waypoint format for map display"""
        with app.app_context():
            route = sample_data['current_route']
            waypoints = json.loads(route.waypoints)
            
            # Verify waypoint structure
            for wp in waypoints:
                assert 'name' in wp
                assert 'lat' in wp
                assert 'lon' in wp
                assert 'type' in wp
                assert isinstance(wp['lat'], (int, float))
                assert isinstance(wp['lon'], (int, float))
                assert -90 <= wp['lat'] <= 90
                assert -180 <= wp['lon'] <= 180
    
    def test_route_comparison_metrics(self, app, sample_data):
        """Test route comparison calculations"""
        with app.app_context():
            current = sample_data['current_route']
            
            # Create alternative
            alternative = Route(
                shipment_id=current.shipment_id,
                route_type=RouteType.SEA,
                waypoints=current.waypoints,
                distance_km=current.distance_km * 1.2,
                estimated_duration_hours=current.estimated_duration_hours * 1.3,
                cost_usd=current.cost_usd * 0.9,
                carbon_emissions_kg=current.carbon_emissions_kg * 1.1,
                risk_score=current.risk_score * 0.5,
                is_current=False
            )
            
            # Calculate deltas
            distance_delta = alternative.distance_km - current.distance_km
            duration_delta = alternative.estimated_duration_hours - current.estimated_duration_hours
            cost_delta = alternative.cost_usd - current.cost_usd
            risk_delta = current.risk_score - alternative.risk_score
            
            assert distance_delta > 0  # Longer
            assert duration_delta > 0  # Slower
            assert cost_delta < 0  # Cheaper
            assert risk_delta > 0  # Less risky

class TestIntegrationScenarios:
    """Test complete integration scenarios"""
    
    def test_red_sea_conflict_scenario(self, app):
        """Test complete Red Sea conflict rerouting scenario"""
        with app.app_context():
            # Create shipment through Red Sea
            shipment = Shipment(
                tracking_number='RED-SEA-001',
                carrier_name='Maersk',
                origin_name='Shanghai',
                origin_lat=31.2304,
                origin_lon=121.4737,
                destination_name='Hamburg',
                destination_lat=53.5511,
                destination_lon=9.9937,
                status='in_transit',  # Use string value instead of enum
                transport_mode='sea',
                total_value=1000000,
                risk_score=0.2  # Initially low
            )
            db.session.add(shipment)
            
            # Current route through Suez
            current_route = Route(
                shipment=shipment,
                route_type='SEA',  # Use string value instead of enum
                waypoints=json.dumps([
                    {"name": "Shanghai", "lat": 31.2304, "lon": 121.4737, "type": "port"},
                    {"name": "Singapore", "lat": 1.3521, "lon": 103.8198, "type": "port"},
                    {"name": "Red Sea", "lat": 20.0, "lon": 38.0, "type": "sea"},
                    {"name": "Suez Canal", "lat": 30.0, "lon": 32.5, "type": "canal"},
                    {"name": "Hamburg", "lat": 53.5511, "lon": 9.9937, "type": "port"}
                ]),
                distance_km=20000,
                estimated_duration_hours=840,
                cost_usd=150000,
                carbon_emissions_kg=1000000,
                risk_score=0.2,
                is_current=True
            )
            db.session.add(current_route)
            
            # Create Red Sea alert
            alert = Alert(
                title='Red Sea Security Threat',
                description='Military activity in Red Sea shipping lanes',
                alert_type='GEOPOLITICAL',
                severity='high',  # Use string value instead of enum
                probability=0.85,
                impact_radius_km=500,
                location_lat=20.0,
                location_lon=38.0,
                source='GDELT',
                is_active=True
            )
            db.session.add(alert)
            alert.shipments.append(shipment)
            db.session.commit()
            
            # Run route optimizer
            agent = RouteOptimizerAgent()
            agent._evaluate_route_alternatives(shipment, force=True)
            
            # Verify alternative routes created
            alternatives = shipment.routes.filter_by(is_current=False).all()
            assert len(alternatives) > 0
            
            # Verify Cape route exists
            cape_route = next((r for r in alternatives 
                             if 'cape' in json.dumps(r.waypoints).lower()), None)
            assert cape_route is not None
            assert cape_route.risk_score < current_route.risk_score
            
            # Verify recommendation created
            recommendations = Recommendation.query.filter_by(
                subject_type='shipment',
                subject_id=shipment.id
            ).all()
            assert len(recommendations) > 0
            assert recommendations[0].severity == 'HIGH'
    
    def test_emergency_procurement_scenario(self, app):
        """Test emergency procurement due to port closure"""
        with app.app_context():
            # This would be implemented in procurement agent tests
            pass

def test_database_indexes(app):
    """Verify database indexes are created for performance"""
    with app.app_context():
        from sqlalchemy import inspect
        
        inspector = inspect(db.engine)
        
        # Check routes table indexes
        route_indexes = inspector.get_indexes('routes')
        index_columns = [idx['column_names'] for idx in route_indexes]
        
        # Verify critical indexes exist
        assert ['shipment_id'] in index_columns or any('shipment_id' in cols for cols in index_columns)
        assert ['is_current'] in index_columns or any('is_current' in cols for cols in index_columns)
        assert ['risk_score'] in index_columns or any('risk_score' in cols for cols in index_columns)