import json
import pytest
from unittest.mock import patch, Mock, MagicMock
from datetime import datetime, timedelta

from app import create_app, db
from app.models import Shipment, Route, Workspace, ShipmentStatus
from app.integrations.carrier_routes import MaerskCarrierProvider
from app.agents.route_optimizer import RouteOptimizerAgent


@pytest.fixture
def app():
    """Create test app."""
    app = create_app('testing')
    app.config['START_AGENTS'] = False  # Don't start agents during testing
    with app.app_context():
        db.create_all()
        # Create default workspace
        if not db.session.get(Workspace, 1):
            db.session.add(Workspace(id=1, name='Test Workspace', code='TEST'))
            db.session.commit()
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def sample_shipment(app):
    """Create a sample shipment for testing and return its id to avoid detachment."""
    with app.app_context():
        shipment = Shipment(
            workspace_id=1,
            reference_number='TEST-001',
            tracking_number='TEST-001',
            carrier='Maersk',
            origin_port='Shanghai',
            destination_port='Los Angeles',
            origin_lat=31.22,
            origin_lon=121.46,
            destination_lat=33.73,
            destination_lon=-118.26,
            status='PLANNED',
            transport_mode='SEA'
        )
        db.session.add(shipment)
        db.session.commit()
        return shipment.id


class TestMaerskCarrierProvider:
    """Test Maersk API integration."""
    
    @patch.dict('os.environ', {'MAERSK_API_KEY': 'test-key'})
    def test_provider_initialization(self, app):
        """Test provider initializes correctly."""
        with app.app_context():
            provider = MaerskCarrierProvider()
            assert provider.api_key == 'test-key'
    
    @patch.dict('os.environ', {'MAERSK_API_KEY': 'test-key'})
    @patch('requests.Session.get')
    def test_find_location_code_success(self, mock_get, app):
        """Test successful location code lookup."""
        with app.app_context():
            # Mock API response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'locations': [
                    {'unLocCode': 'CNSHA', 'name': 'Shanghai'}
                ]
            }
            mock_get.return_value = mock_response
            
            provider = MaerskCarrierProvider()
            result = provider._find_location_code('Shanghai')
            
            assert result == 'CNSHA'
            mock_get.assert_called_once()
    
    @patch.dict('os.environ', {'MAERSK_API_KEY': 'test-key'})
    @patch('requests.Session.get')
    def test_find_location_code_not_found(self, mock_get, app):
        """Test location code lookup when not found."""
        with app.app_context():
            # Mock API response with no results
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'locations': []}
            mock_get.return_value = mock_response
            
            provider = MaerskCarrierProvider()
            result = provider._find_location_code('NonExistentPort')
            
            assert result is None
    
    @patch.dict('os.environ', {'MAERSK_API_KEY': 'test-key'})
    @patch('requests.Session.get')
    def test_fetch_schedules_success(self, mock_get, app):
        """Test successful schedule fetching."""
        with app.app_context():
            # Mock API response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'oceanProducts': [
                    {
                        'id': 'product-1',
                        'serviceCode': 'AE1',
                        'transportSchedules': [{
                            'departureDate': '2024-08-15T10:00:00Z',
                            'arrivalDate': '2024-08-30T18:00:00Z',
                            'legs': [{
                                'transport': {
                                    'loadLocation': {
                                        'displayName': 'Shanghai',
                                        'latitude': 31.22,
                                        'longitude': 121.46
                                    },
                                    'dischargeLocation': {
                                        'displayName': 'Los Angeles',
                                        'latitude': 33.73,
                                        'longitude': -118.26
                                    },
                                    'vessel': {'name': 'MAERSK ATLANTIC'},
                                    'voyageNumber': 'MA123'
                                }
                            }]
                        }]
                    }
                ]
            }
            mock_get.return_value = mock_response
            
            provider = MaerskCarrierProvider()
            result = provider._fetch_schedules('CNSHA', 'USLAX')
            
            assert len(result) == 1
            assert result[0]['id'] == 'product-1'
    
    @patch.dict('os.environ', {'MAERSK_API_KEY': 'test-key'})
    def test_parse_ocean_product(self, app, sample_shipment):
        """Test parsing of ocean product into route option."""
        with app.app_context():
            provider = MaerskCarrierProvider()
            
            # Sample ocean product data
            product = {
                'id': 'product-1',
                'serviceCode': 'AE1',
                'transportSchedules': [{
                    'departureDate': '2024-08-15T10:00:00Z',
                    'arrivalDate': '2024-08-30T18:00:00Z',
                    'legs': [{
                        'transport': {
                            'loadLocation': {
                                'displayName': 'Shanghai',
                                'latitude': 31.22,
                                'longitude': 121.46
                            },
                            'dischargeLocation': {
                                'displayName': 'Los Angeles',
                                'latitude': 33.73,
                                'longitude': -118.26
                            },
                            'vessel': {'name': 'MAERSK ATLANTIC'},
                            'voyageNumber': 'MA123'
                        }
                    }]
                }]
            }
            
            option = provider._parse_ocean_product(product, sample_shipment)
            
            assert option is not None
            assert 'Maersk AE1' in option.name
            assert len(option.waypoints) == 2
            assert option.waypoints[0]['type'] == 'origin'
            assert option.waypoints[1]['type'] == 'destination'
            assert option.distance_km > 0
            assert option.duration_hours > 0
            assert option.cost_usd > 0
            assert option.carbon_emissions_kg > 0
            assert 0 <= option.risk_score <= 1
    
    @patch.dict('os.environ', {'MAERSK_API_KEY': 'test-key'})
    @patch('app.integrations.carrier_routes.MaerskCarrierProvider._find_location_code')
    @patch('app.integrations.carrier_routes.MaerskCarrierProvider._fetch_schedules')
    def test_fetch_routes_integration(self, mock_fetch_schedules, mock_find_location, app, sample_shipment):
        """Test full route fetching integration."""
        with app.app_context():
            # Mock location codes
            mock_find_location.side_effect = ['CNSHA', 'USLAX']
            
            # Mock schedules
            mock_fetch_schedules.return_value = [{
                'id': 'product-1',
                'serviceCode': 'AE1',
                'transportSchedules': [{
                    'departureDate': '2024-08-15T10:00:00Z',
                    'arrivalDate': '2024-08-30T18:00:00Z',
                    'legs': [{
                        'transport': {
                            'loadLocation': {
                                'displayName': 'Shanghai',
                                'latitude': 31.22,
                                'longitude': 121.46
                            },
                            'dischargeLocation': {
                                'displayName': 'Los Angeles',
                                'latitude': 33.73,
                                'longitude': -118.26
                            },
                            'vessel': {'name': 'MAERSK ATLANTIC'},
                            'voyageNumber': 'MA123'
                        }
                    }]
                }]
            }]
            
            provider = MaerskCarrierProvider()
            routes = provider.fetch_routes(sample_shipment)
            
            assert len(routes) == 1
            route = routes[0]
            assert route.name
            assert len(route.waypoints) >= 2
            assert route.distance_km > 0
            assert route.cost_usd > 0


class TestRouteOptimizerAgent:
    """Test Route Optimizer Agent."""
    
    def test_agent_initialization(self, app):
        """Test agent initializes correctly."""
        with app.app_context():
            agent = RouteOptimizerAgent()
            assert agent.agent_name == "route_optimizer_agent"
    
    @patch('app.integrations.carrier_routes.CarrierRouteProvider.for_carrier')
    def test_fetch_and_store_routes(self, mock_for_carrier, app, sample_shipment):
        """Test route fetching and storage."""
        with app.app_context():
            # Mock provider and route options
            mock_provider = Mock()
            mock_route_option = Mock()
            mock_route_option.name = "Test Route"
            mock_route_option.waypoints = [
                {'lat': 31.22, 'lon': 121.46, 'name': 'Shanghai', 'type': 'origin'},
                {'lat': 33.73, 'lon': -118.26, 'name': 'Los Angeles', 'type': 'destination'}
            ]
            mock_route_option.distance_km = 10000
            mock_route_option.duration_hours = 240
            mock_route_option.cost_usd = 75000
            mock_route_option.carbon_emissions_kg = 30000
            mock_route_option.risk_score = 0.3
            mock_route_option.metadata = {'provider': 'maersk', 'risk_factors': ['weather']}
            
            mock_provider.fetch_routes.return_value = [mock_route_option]
            mock_for_carrier.return_value = mock_provider
            
            sample_id = sample_shipment
            agent = RouteOptimizerAgent()
            routes_created = agent.fetch_and_store_routes(db.session.get(Shipment, sample_id))
            
            assert routes_created == 1
            
            # Verify route was stored in database
            routes = Route.query.filter_by(shipment_id=sample_id).all()
            assert len(routes) == 1
            
            route = routes[0]
            assert route.shipment_id == sample_id
            assert route.distance_km == 10000
            assert route.estimated_duration_hours == 240
            assert route.cost_usd == 75000
            assert route.carbon_emissions_kg == 30000
            assert route.risk_score == 0.3
            assert route.is_current is True
            assert route.is_recommended is True
    
    @patch('app.agents.route_optimizer.RouteOptimizerAgent.fetch_and_store_routes')
    def test_handle_shipment_created(self, mock_fetch_routes, app, sample_shipment):
        """Test handling of shipment creation events."""
        with app.app_context():
            mock_fetch_routes.return_value = 2
            
            agent = RouteOptimizerAgent()
            
            # Cache ID to avoid detached access
            sample_id = sample_shipment
            message = {
                'shipment_id': sample_id,
                'carrier': 'Maersk'
            }
            
            agent._handle_shipment_created(message)
            
            mock_fetch_routes.assert_called_once_with(sample_shipment)
    
    def test_analyze_route_optimization(self, app, sample_shipment):
        """Test route optimization analysis."""
        with app.app_context():
            # Create current route
            sample_id = sample_shipment
            current_route = Route(
                shipment_id=sample_id,
                route_type='SEA',
                waypoints='[]',
                distance_km=10000,
                estimated_duration_hours=240,
                cost_usd=75000,
                carbon_emissions_kg=30000,
                risk_score=0.8,
                is_current=True
            )
            db.session.add(current_route)
            
            # Create alternative route with lower risk
            alt_route = Route(
                shipment_id=sample_id,
                route_type='SEA',
                waypoints='[]',
                distance_km=11000,
                estimated_duration_hours=260,
                cost_usd=80000,
                carbon_emissions_kg=32000,
                risk_score=0.3,
                is_current=False
            )
            db.session.add(alt_route)
            db.session.commit()
            
            agent = RouteOptimizerAgent()
            recommendations = agent._analyze_route_optimization(db.session.get(Shipment, sample_id))
            
            assert len(recommendations) >= 1
            risk_rec = next((r for r in recommendations if r['type'] == 'risk_reduction'), None)
            assert risk_rec is not None
            assert risk_rec['risk_reduction'] == 0.5  # 0.8 - 0.3


class TestEndToEndIntegration:
    """Test end-to-end shipment creation and route fetching."""
    
    @patch.dict('os.environ', {'MAERSK_API_KEY': 'test-key'})
    @patch('app.agents.communicator.AgentCommunicator.publish_message')
    def test_shipment_creation_triggers_route_fetch(self, mock_publish, client, app):
        """Test that creating a Maersk shipment triggers route fetching."""
        with app.app_context():
            payload = {
                'reference_number': 'TEST-002',
                'origin_port': 'Shanghai',
                'destination_port': 'Los Angeles',
                'carrier': 'Maersk',
                'origin_lat': 31.22,
                'origin_lon': 121.46,
                'destination_lat': 33.73,
                'destination_lon': -118.26
            }
            
            response = client.post('/api/shipments', 
                                 data=json.dumps(payload), 
                                 content_type='application/json')
            
            assert response.status_code == 201
            data = response.get_json()
            assert 'id' in data
            
            # Verify shipment was created
            shipment = db.session.get(Shipment, data['id'])
            assert shipment is not None
            assert shipment.carrier == 'Maersk'
            
            # Verify event was published
            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            assert call_args[0][0] == 'shipments.created'
            assert call_args[0][1]['shipment_id'] == shipment.id
    
    @patch.dict('os.environ', {'MAERSK_API_KEY': 'test-key', 'DISABLE_ENHANCED_CARRIERS': '1'})
    @patch('requests.Session.get')
    def test_full_route_creation_workflow(self, mock_get, app, sample_shipment):
        """Test the complete workflow from API call to route storage."""
        with app.app_context():
            # Mock location API responses
            location_responses = [
                Mock(status_code=200, json=lambda: {'locations': [{'unLocCode': 'CNSHA', 'name': 'Shanghai'}]}),
                Mock(status_code=200, json=lambda: {'locations': [{'unLocCode': 'USLAX', 'name': 'Los Angeles'}]})
            ]
            
            # Mock schedule API response
            schedule_response = Mock()
            schedule_response.status_code = 200
            schedule_response.json.return_value = {
                'oceanProducts': [{
                    'id': 'product-1',
                    'serviceCode': 'AE1',
                    'transportSchedules': [{
                        'departureDate': '2024-08-15T10:00:00Z',
                        'arrivalDate': '2024-08-30T18:00:00Z',
                        'legs': [{
                            'transport': {
                                'loadLocation': {
                                    'displayName': 'Shanghai',
                                    'latitude': 31.22,
                                    'longitude': 121.46
                                },
                                'dischargeLocation': {
                                    'displayName': 'Los Angeles',
                                    'latitude': 33.73,
                                    'longitude': -118.26
                                },
                                'vessel': {'name': 'MAERSK ATLANTIC'},
                                'voyageNumber': 'MA123'
                            }
                        }]
                    }]
                }]
            }
            
            mock_get.side_effect = location_responses + [schedule_response]
            
            # Test route fetching
            sample_id = sample_shipment
            agent = RouteOptimizerAgent()
            routes_created = agent.fetch_and_store_routes(db.session.get(Shipment, sample_id))
            
            assert routes_created == 1
            
            # Verify routes in database
            routes = Route.query.filter_by(shipment_id=sample_id).all()
            assert len(routes) == 1
            
            route = routes[0]
            assert route.is_current is True
            assert route.is_recommended is True
            assert route.distance_km > 0
            assert route.cost_usd > 0
            
            # Verify waypoints are properly stored
            waypoints = json.loads(route.waypoints)
            assert len(waypoints) == 2
            assert waypoints[0]['name'] == 'Shanghai'
            assert waypoints[1]['name'] == 'Los Angeles'
    
    def test_non_maersk_carrier_skipped(self, client, app):
        """Test that non-Maersk carriers don't trigger route fetching."""
        with app.app_context():
            payload = {
                'reference_number': 'TEST-003',
                'origin_port': 'Shanghai',
                'destination_port': 'Los Angeles',
                'carrier': 'MSC',  # Non-Maersk carrier
            }
            
            response = client.post('/api/shipments', 
                                 data=json.dumps(payload), 
                                 content_type='application/json')
            
            assert response.status_code == 201
            
            # Shipment should be created but no routes
            data = response.get_json()
            shipment = db.session.get(Shipment, data['id'])
            assert shipment.carrier == 'MSC'
            
            routes = Route.query.filter_by(shipment_id=shipment.id).all()
            assert len(routes) == 0


if __name__ == '__main__':
    pytest.main([__file__])
