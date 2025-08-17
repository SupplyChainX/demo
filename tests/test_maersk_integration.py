"""
Comprehensive tests for Maersk API integration
"""
import pytest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import requests

from app.integrations.carrier_routes import MaerskCarrierProvider, CarrierRouteOption
from app.models import Shipment


class TestMaerskCarrierProvider:
    """Test suite for Maersk API integration."""
    
    @pytest.fixture
    def provider(self):
        """Create a Maersk provider instance for testing."""
        with patch.dict(os.environ, {
            'MAERSK_API_KEY': 'test_api_key',
            'MAERSK_CONSUMER_KEY': 'test_consumer_key',
            'MAERSK_APP_ID': 'test_app_id',
            'MAERSK_API_SECRET': 'test_secret'
        }):
            return MaerskCarrierProvider()
    
    @pytest.fixture
    def mock_shipment(self):
        """Create a mock shipment for testing."""
        shipment = Mock(spec=Shipment)
        shipment.id = 1
        shipment.carrier = 'Maersk Line'
        shipment.origin_port = 'Vancouver'
        shipment.destination_port = 'Dubai'
        shipment.origin_lat = 49.2827
        shipment.origin_lon = -123.1207
        shipment.destination_lat = 25.2769
        shipment.destination_lon = 55.2962
        shipment.risk_score = 0.3
        return shipment
    
    def test_initialization_with_env_vars(self, provider):
        """Test provider initialization with environment variables."""
        assert provider.api_key == 'test_api_key'
        assert provider.consumer_key == 'test_consumer_key'
        assert provider.app_id == 'test_app_id'
        assert provider.api_secret == 'test_secret'
    
    def test_initialization_without_env_vars(self):
        """Test provider initialization without environment variables."""
        with patch.dict(os.environ, {}, clear=True):
            provider = MaerskCarrierProvider()
            assert provider.api_key is None
            assert provider.consumer_key is None
    
    def test_get_session_headers(self, provider):
        """Test authentication headers in session."""
        session = provider._get_session()
        
        expected_headers = {
            'User-Agent': 'SupplyChainX/1.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Consumer-Key': 'test_consumer_key',
            'X-API-Key': 'test_api_key',
            'X-App-ID': 'test_app_id'
        }
        
        for key, value in expected_headers.items():
            assert session.headers[key] == value
    
    @patch('requests.Session.get')
    def test_find_location_code_success(self, mock_get, provider):
        """Test successful location code lookup."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'referenceData': {
                'locations': [
                    {
                        'unLocCode': 'CAVAN',
                        'locDisplayName': 'Vancouver Container Terminal',
                        'cityDisplayName': 'Vancouver'
                    }
                ]
            }
        }
        mock_get.return_value = mock_response
        
        result = provider._find_location_code('Vancouver')
        
        assert result == 'CAVAN'
        mock_get.assert_called_once()
        
        # Verify the API call parameters
        call_args = mock_get.call_args
        assert '/reference-data/locations' in call_args[0][0]
        assert call_args[1]['params']['name'] == 'Vancouver'
    
    @patch('requests.Session.get')
    def test_find_location_code_api_error(self, mock_get, provider):
        """Test location lookup with API error."""
        # Mock API error response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = '{"error": "Not found"}'
        mock_get.return_value = mock_response
        
        result = provider._find_location_code('Vancouver')
        
        # Should fallback to hardcoded location
        assert result == 'CAVAN'
    
    def test_fallback_location_codes(self, provider):
        """Test fallback location code mapping."""
        test_cases = [
            ('vancouver', 'CAVAN'),
            ('Dubai', 'AEJEA'),
            ('singapore', 'SGSIN'),
            ('rotterdam', 'NLRTM'),
            ('shanghai', 'CNSHA'),
            ('Los Angeles', 'USLAX'),
            ('hong kong', 'HKHKG'),
            ('nonexistent port', None)
        ]
        
        for port_name, expected_code in test_cases:
            result = provider._fallback_location_code(port_name)
            assert result == expected_code
    
    @patch('requests.Session.get')
    def test_fetch_schedules_success(self, mock_get, provider):
        """Test successful schedule fetching."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'referenceData': {
                'pointToPointSchedules': [
                    {
                        'id': 'schedule-123',
                        'serviceCode': 'AE7',
                        'transportSchedules': [{
                            'departureDate': '2025-08-15T10:00:00Z',
                            'arrivalDate': '2025-09-05T14:00:00Z',
                            'legs': [{
                                'transport': {
                                    'loadLocation': {
                                        'unLocCode': 'CAVAN',
                                        'displayName': 'Vancouver',
                                        'latitude': 49.2827,
                                        'longitude': -123.1207
                                    },
                                    'dischargeLocation': {
                                        'unLocCode': 'AEJEA',
                                        'displayName': 'Jebel Ali',
                                        'latitude': 25.2769,
                                        'longitude': 55.2962
                                    },
                                    'vessel': {
                                        'name': 'Maersk Denver',
                                        'flag': 'DK'
                                    },
                                    'voyageNumber': '025E'
                                }
                            }]
                        }]
                    }
                ]
            }
        }
        mock_get.return_value = mock_response
        
        result = provider._fetch_schedules('CAVAN', 'AEJEA')
        
        assert len(result) == 1
        assert result[0]['id'] == 'schedule-123'
        assert result[0]['serviceCode'] == 'AE7'
    
    @patch('requests.Session.get')
    def test_fetch_schedules_api_error(self, mock_get, provider):
        """Test schedule fetching with API error."""
        # Mock API error
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = '{"error": "Internal server error"}'
        mock_get.return_value = mock_response
        
        result = provider._fetch_schedules('CAVAN', 'AEJEA')
        
        # Should return fallback route
        assert len(result) == 1
        assert result[0]['id'] == 'fallback-CAVAN-AEJEA'
        assert result[0]['serviceCode'] == 'MAEU_FALLBACK'
    
    def test_parse_ocean_product(self, provider, mock_shipment):
        """Test parsing of ocean product data."""
        product_data = {
            'id': 'schedule-123',
            'serviceCode': 'AE7',
            'transportSchedules': [{
                'departureDate': '2025-08-15T10:00:00Z',
                'arrivalDate': '2025-09-05T14:00:00Z',
                'legs': [{
                    'transport': {
                        'loadLocation': {
                            'unLocCode': 'CAVAN',
                            'displayName': 'Vancouver',
                            'latitude': 49.2827,
                            'longitude': -123.1207
                        },
                        'dischargeLocation': {
                            'unLocCode': 'AEJEA',
                            'displayName': 'Jebel Ali',
                            'latitude': 25.2769,
                            'longitude': 55.2962
                        },
                        'vessel': {
                            'name': 'Maersk Denver',
                            'flag': 'DK'
                        },
                        'voyageNumber': '025E'
                    }
                }]
            }]
        }
        
        result = provider._parse_ocean_product(product_data, mock_shipment)
        
        assert isinstance(result, CarrierRouteOption)
        assert result.name == 'Maersk AE7 - Maersk Denver'
        assert len(result.waypoints) == 2
        assert result.waypoints[0]['type'] == 'origin'
        assert result.waypoints[1]['type'] == 'destination'
        assert result.distance_km > 0
        assert result.duration_hours is not None
        assert result.cost_usd > 0
        assert result.carbon_emissions_kg > 0
        assert 0 <= result.risk_score <= 1
        assert result.metadata['provider'] == 'maersk'
        assert result.metadata['product_id'] == 'schedule-123'
    
    def test_calculate_distance(self, provider):
        """Test distance calculation between two points."""
        # Vancouver to Dubai coordinates
        lat1, lon1 = 49.2827, -123.1207
        lat2, lon2 = 25.2769, 55.2962
        
        distance = provider._calculate_distance(lat1, lon1, lat2, lon2)
        
        # Expected distance is approximately 16,000 km
        assert 15000 < distance < 17000
    
    def test_calculate_distance_same_point(self, provider):
        """Test distance calculation for same point."""
        distance = provider._calculate_distance(0, 0, 0, 0)
        assert distance == 0
    
    def test_calculate_distance_invalid_coordinates(self, provider):
        """Test distance calculation with invalid coordinates."""
        distance = provider._calculate_distance(None, None, 0, 0)
        assert distance == 0
    
    @patch('app.integrations.carrier_routes.MaerskCarrierProvider._find_location_code')
    @patch('app.integrations.carrier_routes.MaerskCarrierProvider._fetch_schedules')
    @patch('app.integrations.carrier_routes.MaerskCarrierProvider._parse_ocean_product')
    def test_fetch_routes_success(self, mock_parse, mock_fetch, mock_find, provider, mock_shipment):
        """Test successful route fetching end-to-end."""
        # Mock location code lookup
        mock_find.side_effect = ['CAVAN', 'AEJEA']
        
        # Mock schedule fetching
        mock_schedule = {
            'id': 'schedule-123',
            'serviceCode': 'AE7',
            'transportSchedules': [{}]
        }
        mock_fetch.return_value = [mock_schedule]
        
        # Mock route parsing
        mock_route = CarrierRouteOption(
            name='Test Route',
            waypoints=[],
            distance_km=16000,
            duration_hours=500,
            cost_usd=15000,
            carbon_emissions_kg=184000,
            risk_score=0.3,
            metadata={'provider': 'maersk'}
        )
        mock_parse.return_value = mock_route
        
        result = provider.fetch_routes(mock_shipment)
        
        assert len(result) == 1
        assert result[0] == mock_route
        
        # Verify all methods were called
        assert mock_find.call_count == 2
        mock_fetch.assert_called_once_with('CAVAN', 'AEJEA')
        mock_parse.assert_called_once_with(mock_schedule, mock_shipment)
    
    def test_fetch_routes_no_api_key(self, mock_shipment):
        """Test route fetching without API key."""
        provider = MaerskCarrierProvider()  # No env vars set
        result = provider.fetch_routes(mock_shipment)
        assert result == []
    
    def test_fetch_routes_missing_ports(self, provider):
        """Test route fetching with missing port information."""
        shipment = Mock(spec=Shipment)
        shipment.origin_port = None
        shipment.destination_port = 'Dubai'
        
        result = provider.fetch_routes(shipment)
        assert result == []
    
    @patch('app.integrations.carrier_routes.MaerskCarrierProvider._find_location_code')
    def test_fetch_routes_location_not_found(self, mock_find, provider, mock_shipment):
        """Test route fetching when location codes cannot be found."""
        mock_find.return_value = None
        
        result = provider.fetch_routes(mock_shipment)
        assert result == []
    
    def test_get_port_coordinates(self, provider):
        """Test port coordinates lookup."""
        test_cases = [
            ('CAVAN', (49.2827, -123.1207)),  # Vancouver
            ('AEJEA', (25.2769, 55.2962)),     # Dubai/Jebel Ali
            ('SGSIN', (1.2966, 103.8060)),     # Singapore
            ('UNKNOWN', (0.0, 0.0))            # Unknown port
        ]
        
        for port_code, expected_coords in test_cases:
            result = provider._get_port_coordinates(port_code)
            assert result == expected_coords
    
    def test_generate_fallback_routes(self, provider):
        """Test fallback route generation."""
        routes = provider._generate_fallback_routes('CAVAN', 'AEJEA')
        
        assert len(routes) == 1
        route = routes[0]
        
        assert route['id'] == 'fallback-CAVAN-AEJEA'
        assert route['serviceCode'] == 'MAEU_FALLBACK'
        assert 'transportSchedules' in route
        assert len(route['transportSchedules']) == 1
        
        schedule = route['transportSchedules'][0]
        assert 'departureDate' in schedule
        assert 'arrivalDate' in schedule
        assert 'legs' in schedule
        
        leg = schedule['legs'][0]
        transport = leg['transport']
        assert transport['loadLocation']['unLocCode'] == 'CAVAN'
        assert transport['dischargeLocation']['unLocCode'] == 'AEJEA'
        assert transport['vessel']['name'] == 'Maersk Vessel'


class TestMaerskIntegrationReal:
    """Integration tests that can be run against real Maersk API."""
    
    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv('MAERSK_API_KEY'), reason="Requires real Maersk API key")
    def test_real_api_locations(self):
        """Test against real Maersk API for locations."""
        provider = MaerskCarrierProvider()
        
        # Test with a known port
        result = provider._find_location_code('Singapore')
        
        # Should return a valid UN/LOCODE or fallback
        assert result is not None
        assert len(result) == 5  # UN/LOCODE format
    
    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv('MAERSK_API_KEY'), reason="Requires real Maersk API key")
    def test_real_api_schedules(self):
        """Test against real Maersk API for schedules."""
        provider = MaerskCarrierProvider()
        
        # Test with known route
        result = provider._fetch_schedules('SGSIN', 'NLRTM')  # Singapore to Rotterdam
        
        # Should return schedules or fallback
        assert isinstance(result, list)
        assert len(result) >= 1
    
    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv('MAERSK_API_KEY'), reason="Requires real Maersk API key")
    def test_real_api_full_flow(self):
        """Test full flow against real Maersk API."""
        provider = MaerskCarrierProvider()
        
        # Create a test shipment
        shipment = Mock(spec=Shipment)
        shipment.id = 999
        shipment.carrier = 'Maersk Line'
        shipment.origin_port = 'Singapore'
        shipment.destination_port = 'Rotterdam'
        shipment.origin_lat = 1.2966
        shipment.origin_lon = 103.8060
        shipment.destination_lat = 51.9225
        shipment.destination_lon = 4.4792
        shipment.risk_score = 0.2
        
        result = provider.fetch_routes(shipment)
        
        # Should return at least one route (real or fallback)
        assert isinstance(result, list)
        assert len(result) >= 1
        
        # Validate route structure
        route = result[0]
        assert isinstance(route, CarrierRouteOption)
        assert route.name is not None
        assert len(route.waypoints) >= 2
        assert route.distance_km > 0
        assert route.cost_usd > 0
        assert route.carbon_emissions_kg > 0
        assert 0 <= route.risk_score <= 1
        assert route.metadata['provider'] == 'maersk'


if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v'])
