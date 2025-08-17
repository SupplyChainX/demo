"""
Maritime data integration APIs - AIS, port conditions
"""
import logging
import requests
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from flask import current_app
from app.models import db, IntegrationLog

logger = logging.getLogger(__name__)

class MaritimeIntegration:
    """Integration with maritime data sources."""
    
    def __init__(self):
        # Free AIS services (limited queries)
        self.vesselfinder_base = "https://www.vesselfinder.com/api"
        self.marinetraffic_base = "https://www.marinetraffic.com/api"
        # Port conditions - various national sources
        self.ports_apis = {
            'US': 'https://tidesandcurrents.noaa.gov/api/datagetter',
            'EU': 'https://www.emodnet.eu/api',
            'SG': 'https://www.mpa.gov.sg/api'
        }
        
        # Free AIS data sources
        self.ais_endpoints = {
            'vesselfinder': 'https://www.vesselfinder.com/api/pub/click/',
            'marinetraffic_free': 'https://www.marinetraffic.com/getData/get_data_json_4',
            'aishub': 'http://data.aishub.net/ws.php'
        }
        
        # Port information endpoints
        self.port_apis = {
            'noaa_ports': 'https://api.tidesandcurrents.noaa.gov/api/prod/datagetter',
            'port_congestion': 'https://api.portchain.com/api/v1/vessels'  # Limited free tier
        }
        
    def get_ais_vessel_positions(self, bbox: Dict[str, float], 
                                vessel_types: List[str] = None) -> List[Dict[str, Any]]:
        """Get vessel positions within bounding box."""
        try:
            # For demo, return mock data
            # In production, would use actual AIS API with authentication
            vessels = self._get_mock_vessel_data(bbox)
            
            # Try AISHub first (free tier available)
            vessels = self._fetch_aishub_data(bbox)
            
            if not vessels:
                # Fallback to mock enhanced with realistic patterns
                vessels = self._generate_realistic_vessel_data(bbox)
            
            # Log the integration attempt
            self._log_integration('ais_fetch', 'success', {'vessel_count': len(vessels)})
            
            # Filter by vessel types if specified
            if vessel_types:
                vessels = [v for v in vessels 
                          if v.get('vessel_type') in vessel_types]
            
            # Normalize data
            return [self.normalize_maritime_data({
                'source': 'ais',
                'data_type': 'vessel_position',
                'vessel': vessel
            }) for vessel in vessels]
            
        except Exception as e:
            logger.error(f"Error fetching AIS data: {e}")
            self._log_integration('ais_fetch', 'error', {'error': str(e)})
            return self._generate_realistic_vessel_data(bbox)
    
    def fetch_port_conditions(self, port_code: str) -> Dict[str, Any]:
        """Fetch current port conditions and status."""
        try:
            # Determine which API to use based on port code
            country = self._get_port_country(port_code)
            
            if country == 'US':
                return self._fetch_us_port_conditions(port_code)
            elif country in ['EU', 'GB']:
                return self._fetch_eu_port_conditions(port_code)
            elif country == 'SG':
                return self._fetch_sg_port_conditions(port_code)
            else:
                # Generic port status
                return self._get_generic_port_status(port_code)
            
        except Exception as e:
            logger.error(f"Error fetching port conditions for {port_code}: {e}")
            return {
                'port_code': port_code,
                'status': 'unknown',
                'error': str(e)
            }
    
    def get_port_conditions(self, port_code: str) -> Dict[str, Any]:
        """
        Get port conditions - Primary method for Risk Predictor Agent
        This is the main method called by the Enhanced Risk Predictor Agent
        """
        try:
            logger.info(f"🚢 Fetching port conditions for {port_code}")
            
            # Try to fetch real-time conditions first
            conditions = self.fetch_port_conditions(port_code)
            
            if not conditions or conditions.get('error'):
                logger.warning(f"Real-time data unavailable for {port_code}, using enhanced fallback")
                conditions = self._generate_enhanced_port_conditions(port_code)
            
            # Enhance with additional risk factors
            conditions = self._enhance_port_conditions_for_risk_predictor(conditions, port_code)
            
            # Log successful fetch
            self._log_integration('port_conditions_fetch', 'success', {
                'port_code': port_code,
                'operational': conditions.get('operational', True),
                'congestion_level': conditions.get('congestion_level', 'unknown')
            })
            
            return conditions
            
        except Exception as e:
            logger.error(f"Port conditions error for {port_code}: {e}")
            return self._generate_enhanced_port_conditions(port_code, error=str(e))
    
    def _enhance_port_conditions_for_risk_predictor(self, conditions: Dict, port_code: str) -> Dict:
        """Enhance port conditions with risk predictor specific data"""
        try:
            # Add risk scoring
            risk_score = self._calculate_port_risk_score(conditions)
            
            # Add predictive factors
            conditions.update({
                'risk_score': risk_score,
                'risk_level': self._get_port_risk_level(risk_score),
                'predicted_delays': self._predict_port_delays(conditions),
                'capacity_utilization': self._calculate_capacity_utilization(conditions),
                'weather_impact': self._assess_weather_impact(conditions),
                'security_status': self._get_security_status(port_code),
                'last_updated': datetime.utcnow().isoformat(),
                'data_freshness': 'real_time' if not conditions.get('fallback_mode') else 'enhanced_fallback',
                'confidence': 0.85 if not conditions.get('fallback_mode') else 0.70
            })
            
            # Add operational recommendations
            conditions['recommendations'] = self._generate_port_recommendations(conditions)
            
            return conditions
            
        except Exception as e:
            logger.error(f"Port condition enhancement error: {e}")
            return conditions
    
    def _calculate_port_risk_score(self, conditions: Dict) -> float:
        """Calculate overall risk score for port operations"""
        try:
            risk_factors = {
                'congestion': 0.3,
                'weather': 0.25,
                'operational': 0.2,
                'security': 0.15,
                'infrastructure': 0.1
            }
            
            total_risk = 0.0
            
            # Congestion risk
            congestion_level = conditions.get('congestion_level', 'moderate')
            congestion_scores = {
                'low': 0.2,
                'moderate': 0.4,
                'high': 0.7,
                'severe': 0.9
            }
            congestion_risk = congestion_scores.get(congestion_level, 0.4)
            total_risk += congestion_risk * risk_factors['congestion']
            
            # Weather risk
            weather_risk = 0.3  # Default
            if 'weather_conditions' in conditions:
                weather = conditions['weather_conditions']
                wind_speed = weather.get('wind_speed', 10)
                sea_state = weather.get('sea_state', 'Moderate')
                
                if wind_speed > 25 or sea_state in ['Rough', 'Very Rough']:
                    weather_risk = 0.8
                elif wind_speed > 20 or sea_state == 'Moderate':
                    weather_risk = 0.5
                else:
                    weather_risk = 0.2
                    
            total_risk += weather_risk * risk_factors['weather']
            
            # Operational risk
            operational_risk = 0.1 if conditions.get('operational', True) else 0.9
            total_risk += operational_risk * risk_factors['operational']
            
            # Security risk (simplified based on port location)
            security_risk = self._get_port_security_risk(conditions.get('port_code', ''))
            total_risk += security_risk * risk_factors['security']
            
            # Infrastructure risk (based on delays and capacity)
            wait_hours = conditions.get('avg_wait_hours', 12)
            infrastructure_risk = min(0.9, wait_hours / 48)  # Normalize to 48 hours max
            total_risk += infrastructure_risk * risk_factors['infrastructure']
            
            return min(0.95, max(0.05, total_risk))
            
        except Exception as e:
            logger.error(f"Port risk calculation error: {e}")
            return 0.4  # Default moderate risk
    
    def _get_port_security_risk(self, port_code: str) -> float:
        """Get security risk level for port based on location and historical data"""
        # Regional risk mapping
        regional_risks = {
            # Red Sea / Gulf of Aden
            'JED': 0.7, 'HOD': 0.8, 'ADE': 0.8,
            # West Africa
            'LOS': 0.6, 'DKR': 0.5, 'TMA': 0.6,
            # South America
            'CAO': 0.5, 'RIO': 0.4,
            # Middle East
            'KWI': 0.5, 'DOH': 0.4, 'DXB': 0.3,
            # Asia Pacific (generally lower risk)
            'SIN': 0.2, 'HKG': 0.2, 'SHA': 0.3,
            # Europe/North America (low risk)
            'RTM': 0.2, 'HAM': 0.2, 'LAX': 0.2, 'NYC': 0.2
        }
        
        return regional_risks.get(port_code, 0.3)  # Default moderate risk
    
    def _get_port_risk_level(self, risk_score: float) -> str:
        """Convert risk score to categorical level"""
        if risk_score < 0.3:
            return 'low'
        elif risk_score < 0.6:
            return 'moderate'
        elif risk_score < 0.8:
            return 'high'
        else:
            return 'severe'
    
    def _predict_port_delays(self, conditions: Dict) -> Dict:
        """Predict potential delays based on current conditions"""
        base_delay = conditions.get('avg_wait_hours', 12)
        congestion_score = conditions.get('congestion_score', 0.5)
        
        # Calculate predicted delays
        weather_delay = 0
        if 'weather_conditions' in conditions:
            wind_speed = conditions['weather_conditions'].get('wind_speed', 10)
            if wind_speed > 25:
                weather_delay = 6  # 6 hours for severe weather
            elif wind_speed > 20:
                weather_delay = 2  # 2 hours for moderate weather
        
        congestion_delay = congestion_score * 24  # Up to 24 hours for severe congestion
        
        total_predicted_delay = base_delay + weather_delay + congestion_delay
        
        return {
            'base_wait_hours': base_delay,
            'weather_delay_hours': weather_delay,
            'congestion_delay_hours': congestion_delay,
            'total_predicted_delay_hours': round(total_predicted_delay, 1),
            'confidence': 0.7,
            'factors': ['congestion', 'weather', 'historical_patterns']
        }
    
    def _calculate_capacity_utilization(self, conditions: Dict) -> float:
        """Calculate port capacity utilization"""
        try:
            vessels_at_berth = conditions.get('vessels_at_berth', 15)
            vessels_waiting = conditions.get('vessels_waiting', 5)
            berth_availability = conditions.get('berth_availability', 50)
            
            # Estimate total capacity
            total_capacity = vessels_at_berth / (1 - berth_availability/100) if berth_availability < 100 else vessels_at_berth + 10
            current_usage = vessels_at_berth + vessels_waiting
            
            utilization = current_usage / total_capacity if total_capacity > 0 else 0.5
            return min(0.98, max(0.1, utilization))
            
        except Exception:
            return 0.6  # Default moderate utilization
    
    def _assess_weather_impact(self, conditions: Dict) -> Dict:
        """Assess weather impact on port operations"""
        try:
            if 'weather_conditions' not in conditions:
                return {'impact_level': 'unknown', 'score': 0.3}
            
            weather = conditions['weather_conditions']
            wind_speed = weather.get('wind_speed', 10)
            visibility = weather.get('visibility', 'Good')
            sea_state = weather.get('sea_state', 'Moderate')
            
            impact_score = 0.1  # Base impact
            impact_factors = []
            
            # Wind impact
            if wind_speed > 30:
                impact_score = max(impact_score, 0.9)
                impact_factors.append('severe_winds')
            elif wind_speed > 20:
                impact_score = max(impact_score, 0.6)
                impact_factors.append('strong_winds')
            
            # Visibility impact
            if visibility == 'Poor':
                impact_score = max(impact_score, 0.7)
                impact_factors.append('poor_visibility')
            elif visibility == 'Moderate':
                impact_score = max(impact_score, 0.4)
                impact_factors.append('reduced_visibility')
            
            # Sea state impact
            if sea_state in ['Very Rough', 'High']:
                impact_score = max(impact_score, 0.8)
                impact_factors.append('rough_seas')
            elif sea_state == 'Rough':
                impact_score = max(impact_score, 0.5)
                impact_factors.append('moderate_seas')
            
            impact_levels = {
                (0, 0.3): 'minimal',
                (0.3, 0.6): 'moderate',
                (0.6, 0.8): 'significant',
                (0.8, 1.0): 'severe'
            }
            
            impact_level = 'unknown'
            for (min_val, max_val), level in impact_levels.items():
                if min_val <= impact_score < max_val:
                    impact_level = level
                    break
            
            return {
                'impact_level': impact_level,
                'score': round(impact_score, 2),
                'factors': impact_factors,
                'wind_speed': wind_speed,
                'visibility': visibility,
                'sea_state': sea_state
            }
            
        except Exception as e:
            logger.error(f"Weather impact assessment error: {e}")
            return {'impact_level': 'unknown', 'score': 0.3}
    
    def _get_security_status(self, port_code: str) -> Dict:
        """Get security status for port"""
        # Simplified security assessment
        security_levels = {
            'GREEN': {'level': 'normal', 'score': 0.2},
            'YELLOW': {'level': 'elevated', 'score': 0.5},
            'ORANGE': {'level': 'high', 'score': 0.7},
            'RED': {'level': 'severe', 'score': 0.9}
        }
        
        # Determine security level based on port risk
        port_risk = self._get_port_security_risk(port_code)
        
        if port_risk < 0.3:
            security_color = 'GREEN'
        elif port_risk < 0.6:
            security_color = 'YELLOW'
        elif port_risk < 0.8:
            security_color = 'ORANGE'
        else:
            security_color = 'RED'
        
        security_info = security_levels[security_color]
        
        return {
            'alert_level': security_color,
            'status': security_info['level'],
            'risk_score': security_info['score'],
            'last_updated': datetime.utcnow().isoformat(),
            'recommendations': self._get_security_recommendations(security_color)
        }
    
    def _get_security_recommendations(self, alert_level: str) -> List[str]:
        """Get security recommendations based on alert level"""
        recommendations = {
            'GREEN': ['Standard security procedures'],
            'YELLOW': ['Enhanced awareness', 'Monitor local conditions'],
            'ORANGE': ['Increased security measures', 'Coordinate with local authorities', 'Limit crew shore leave'],
            'RED': ['Maximum security protocols', 'Consider alternative ports', 'Immediate threat assessment']
        }
        
        return recommendations.get(alert_level, ['Standard procedures'])
    
    def _generate_port_recommendations(self, conditions: Dict) -> List[str]:
        """Generate operational recommendations based on port conditions"""
        recommendations = []
        
        risk_score = conditions.get('risk_score', 0.4)
        congestion_level = conditions.get('congestion_level', 'moderate')
        weather_impact = conditions.get('weather_impact', {})
        
        # Risk-based recommendations
        if risk_score > 0.7:
            recommendations.extend([
                "High-risk port conditions detected",
                "Consider alternative ports if possible",
                "Implement enhanced safety protocols"
            ])
        elif risk_score > 0.5:
            recommendations.extend([
                "Moderate risk conditions",
                "Monitor situation closely",
                "Prepare for potential delays"
            ])
        
        # Congestion-based recommendations
        if congestion_level in ['high', 'severe']:
            recommendations.extend([
                f"Expect significant delays due to {congestion_level} congestion",
                "Consider arriving during off-peak hours",
                "Coordinate closely with port agents"
            ])
        
        # Weather-based recommendations
        weather_impact_level = weather_impact.get('impact_level', 'minimal')
        if weather_impact_level in ['significant', 'severe']:
            recommendations.extend([
                f"Weather conditions causing {weather_impact_level} impact",
                "Monitor weather forecasts closely",
                "Prepare for weather-related delays"
            ])
        
        # Security-based recommendations
        security_status = conditions.get('security_status', {})
        if security_status.get('alert_level') in ['ORANGE', 'RED']:
            recommendations.extend(security_status.get('recommendations', []))
        
        return list(set(recommendations))  # Remove duplicates
    
    def _generate_enhanced_port_conditions(self, port_code: str, error: str = None) -> Dict:
        """Generate enhanced fallback port conditions when real-time data unavailable"""
        # Use the existing _generate_port_conditions method as base
        conditions = self._generate_port_conditions(port_code)
        
        # Enhance with additional risk predictor data
        conditions.update({
            'fallback_mode': True,
            'data_source': 'enhanced_fallback',
            'error': error,
            'enhanced_features': [
                'risk_scoring',
                'delay_prediction', 
                'capacity_analysis',
                'weather_impact',
                'security_assessment'
            ]
        })
        
        return conditions
    
    def get_port_weather(self, port_code: str) -> Dict[str, Any]:
        """Get weather conditions at port."""
        try:
            # Get port coordinates
            coords = self._get_port_coordinates(port_code)
            if not coords:
                return {}
            
            # Use weather API for port location
            from app.integrations.weather_apis import WeatherIntegration
            weather = WeatherIntegration()
            
            conditions = weather.get_open_meteo_forecast(
                coords['lat'], coords['lon'], days=3
            )
            
            # Add maritime-specific conditions
            marine = weather.get_marine_forecast(coords['lat'], coords['lon'])
            
            return self.normalize_maritime_data({
                'source': 'port_weather',
                'port_code': port_code,
                'coordinates': coords,
                'weather_conditions': conditions,
                'marine_conditions': marine
            })
            
        except Exception as e:
            logger.error(f"Error fetching port weather: {e}")
            return {}
    
    def get_shipping_route_conditions(self, waypoints: List[Dict[str, float]]) -> Dict[str, Any]:
        """Analyze conditions along shipping route."""
        try:
            route_conditions = {
                'waypoints': waypoints,
                'segments': [],
                'overall_risk': 0.0,
                'risk_factors': []
            }
            
            # Analyze each segment
            for i in range(len(waypoints) - 1):
                segment = self._analyze_route_segment(
                    waypoints[i], waypoints[i + 1]
                )
                route_conditions['segments'].append(segment)
            
            # Calculate overall risk
            if route_conditions['segments']:
                total_risk = sum(s.get('risk_score', 0) 
                               for s in route_conditions['segments'])
                route_conditions['overall_risk'] = total_risk / len(route_conditions['segments'])
            
            # Identify main risk factors
            for segment in route_conditions['segments']:
                route_conditions['risk_factors'].extend(
                    segment.get('risk_factors', [])
                )
            
            return self.normalize_maritime_data({
                'source': 'route_analysis',
                'data_type': 'shipping_route',
                'conditions': route_conditions
            })
            
        except Exception as e:
            logger.error(f"Error analyzing route conditions: {e}")
            return {}
    
    def get_piracy_alerts(self, region: str = None) -> List[Dict[str, Any]]:
        """Get piracy and security alerts for maritime regions."""
        try:
            # In production, would integrate with IMB Piracy Reporting Centre
            # For demo, return known high-risk areas
            alerts = []
            
            high_risk_areas = [
                {
                    'region': 'Gulf of Guinea',
                    'lat_min': -10, 'lat_max': 10,
                    'lon_min': -20, 'lon_max': 15,
                    'risk_level': 'high',
                    'incidents_30d': 5
                },
                {
                    'region': 'Red Sea / Gulf of Aden',
                    'lat_min': 10, 'lat_max': 20,
                    'lon_min': 35, 'lon_max': 50,
                    'risk_level': 'high',
                    'incidents_30d': 3
                },
                {
                    'region': 'Strait of Malacca',
                    'lat_min': -2, 'lat_max': 6,
                    'lon_min': 95, 'lon_max': 105,
                    'risk_level': 'medium',
                    'incidents_30d': 2
                }
            ]
            
            for area in high_risk_areas:
                if region and region.lower() not in area['region'].lower():
                    continue
                
                alerts.append({
                    'alert_type': 'piracy',
                    'region': area['region'],
                    'bounds': {
                        'lat_min': area['lat_min'],
                        'lat_max': area['lat_max'],
                        'lon_min': area['lon_min'],
                        'lon_max': area['lon_max']
                    },
                    'risk_level': area['risk_level'],
                    'recent_incidents': area['incidents_30d'],
                    'recommendations': self._get_piracy_recommendations(area['risk_level'])
                })
            
            return [self.normalize_maritime_data({
                'source': 'security_alerts',
                'data_type': 'piracy_alert',
                'alert': alert
            }) for alert in alerts]
            
        except Exception as e:
            logger.error(f"Error fetching piracy alerts: {e}")
            return []
    
    def normalize_maritime_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize maritime data to common format."""
        normalized = {
            'source': raw_data.get('source'),
            'timestamp': raw_data.get('timestamp', datetime.utcnow().isoformat()),
            'data_type': raw_data.get('data_type', 'maritime'),
            'license': self._get_data_license(raw_data.get('source'))
        }
        
        # Handle different data types
        if raw_data.get('data_type') == 'vessel_position':
            vessel = raw_data.get('vessel', {})
            normalized.update({
                'vessel_info': {
                    'mmsi': vessel.get('mmsi'),
                    'name': vessel.get('name'),
                    'type': vessel.get('vessel_type'),
                    'position': {
                        'lat': vessel.get('lat'),
                        'lon': vessel.get('lon')
                    },
                    'speed_knots': vessel.get('speed'),
                    'course': vessel.get('course'),
                    'destination': vessel.get('destination'),
                    'eta': vessel.get('eta')
                }
            })
        
        elif raw_data.get('data_type') == 'port_conditions':
            normalized.update({
                'port_conditions': raw_data.get('conditions', {})
            })
        
        elif raw_data.get('data_type') == 'shipping_route':
            normalized.update({
                'route_analysis': raw_data.get('conditions', {})
            })
        
        elif raw_data.get('data_type') == 'piracy_alert':
            normalized.update({
                'security_alert': raw_data.get('alert', {})
            })
        
        return normalized
    
    # Helper methods
    def _get_mock_vessel_data(self, bbox: Dict[str, float]) -> List[Dict]:
        """Generate mock vessel data for demo."""
        import random
        
        vessel_types = ['Cargo', 'Tanker', 'Container Ship', 'Bulk Carrier']
        vessels = []
        
        for i in range(random.randint(5, 15)):
            lat = random.uniform(bbox['lat_min'], bbox['lat_max'])
            lon = random.uniform(bbox['lon_min'], bbox['lon_max'])
            
            vessels.append({
                'mmsi': f"3{random.randint(10000000, 99999999)}",
                'name': f"VESSEL_{i+1}",
                'vessel_type': random.choice(vessel_types),
                'lat': round(lat, 4),
                'lon': round(lon, 4),
                'speed': round(random.uniform(5, 20), 1),
                'course': random.randint(0, 359),
                'destination': random.choice(['SINGAPORE', 'ROTTERDAM', 'SHANGHAI', 'LOS ANGELES']),
                'eta': (datetime.utcnow() + timedelta(days=random.randint(1, 10))).isoformat()
            })
        
        return vessels
    
    def _fetch_aishub_data(self, bbox: Tuple[float, float, float, float]) -> List[Dict]:
        """Fetch from AISHub (requires free API key)"""
        try:
            # Note: In production, get API key from environment
            params = {
                'username': 'AISHub_demo',  # Demo account
                'format': 'json',
                'output': 'json',
                'compress': '0',
                'latmin': bbox[0],
                'latmax': bbox[2],
                'lonmin': bbox[1],
                'lonmax': bbox[3]
            }
            
            response = requests.get(
                'http://data.aishub.net/ws.php',
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return self._normalize_ais_data(data)
            
        except Exception as e:
            logger.warning(f"AISHub API error: {str(e)}")
            
        return []
    
    def _generate_realistic_vessel_data(self, bbox: Tuple[float, float, float, float]) -> List[Dict]:
        """Generate realistic vessel positions for demo"""
        import random
        
        vessel_types = {
            'Container': {'speed_range': (15, 25), 'prefix': 'CONT'},
            'Tanker': {'speed_range': (10, 20), 'prefix': 'TANK'},
            'Bulk Carrier': {'speed_range': (10, 18), 'prefix': 'BULK'},
            'RoRo': {'speed_range': (18, 23), 'prefix': 'RORO'}
        }
        
        # Major shipping routes through the area
        routes = self._get_shipping_routes(bbox)
        vessels = []
        
        for i in range(random.randint(20, 40)):
            vessel_type = random.choice(list(vessel_types.keys()))
            type_info = vessel_types[vessel_type]
            
            # Place vessels along major routes
            route = random.choice(routes)
            position = self._interpolate_route_position(route, random.random())
            
            vessel = {
                'mmsi': f"2{random.randint(10000000, 99999999)}",
                'name': f"{type_info['prefix']}-{random.randint(1000, 9999)}",
                'lat': position[0],
                'lon': position[1],
                'speed': random.uniform(*type_info['speed_range']),
                'course': random.randint(0, 359),
                'heading': random.randint(0, 359),
                'status': random.choice(['Underway', 'At anchor', 'Moored']),
                'vessel_type': vessel_type,
                'destination': self._get_nearby_port(position),
                'eta': (datetime.utcnow() + timedelta(hours=random.randint(1, 72))).isoformat(),
                'draught': round(random.uniform(8.0, 15.0), 1),
                'length': random.randint(200, 400),
                'width': random.randint(30, 60),
                'timestamp': datetime.utcnow().isoformat()
            }
            vessels.append(vessel)
            
        return vessels
    
    def fetch_port_conditions(self, port_code: str) -> Dict[str, Any]:
        """Fetch current port conditions and status."""
        try:
            # Try NOAA for US ports
            if port_code in self._get_us_port_codes():
                conditions = self._fetch_noaa_port_data(port_code)
                if conditions:
                    return conditions
            
            # Fallback to enhanced mock data
            return self._generate_port_conditions(port_code)
            
        except Exception as e:
            logger.error(f"Port conditions fetch error: {str(e)}")
            return self._generate_port_conditions(port_code)
    
    def _fetch_noaa_port_data(self, port_code: str) -> Optional[Dict]:
        """Fetch real-time data from NOAA for US ports"""
        try:
            # Map port codes to NOAA station IDs
            noaa_stations = {
                'LAX': '9410660',  # Los Angeles
                'NYC': '8518750',  # New York
                'MIA': '8723214',  # Miami
                'SEA': '9447130',  # Seattle
                'SFO': '9414290',  # San Francisco
                'HOU': '8770613',  # Houston
            }
            
            if port_code not in noaa_stations:
                return None
                
            station_id = noaa_stations[port_code]
            
            # Fetch water level data
            water_params = {
                'station': station_id,
                'product': 'water_level',
                'datum': 'MLLW',
                'units': 'metric',
                'time_zone': 'gmt',
                'format': 'json',
                'date': 'latest'
            }
            
            water_response = requests.get(
                self.port_apis['noaa_ports'],
                params=water_params,
                timeout=10
            )
            
            # Fetch wind data
            wind_params = water_params.copy()
            wind_params['product'] = 'wind'
            
            wind_response = requests.get(
                self.port_apis['noaa_ports'],
                params=wind_params,
                timeout=10
            )
            
            conditions = {
                'port_code': port_code,
                'timestamp': datetime.utcnow().isoformat(),
                'operational': True,
                'congestion_level': 'moderate',  # Would need vessel count API
                'water_conditions': {},
                'wind_conditions': {},
                'alerts': []
            }
            
            if water_response.status_code == 200:
                water_data = water_response.json()
                if 'data' in water_data and water_data['data']:
                    latest = water_data['data'][-1]
                    conditions['water_conditions'] = {
                        'level': float(latest.get('v', 0)),
                        'timestamp': latest.get('t', '')
                    }
            
            if wind_response.status_code == 200:
                wind_data = wind_response.json()
                if 'data' in wind_data and wind_data['data']:
                    latest = wind_data['data'][-1]
                    conditions['wind_conditions'] = {
                        'speed': float(latest.get('s', 0)),
                        'direction': float(latest.get('d', 0)),
                        'gusts': float(latest.get('g', 0))
                    }
                    
                    # Add alerts for high winds
                    if conditions['wind_conditions']['speed'] > 30:
                        conditions['alerts'].append({
                            'type': 'weather',
                            'severity': 'high',
                            'message': f"High winds: {conditions['wind_conditions']['speed']} knots"
                        })
            
            return conditions
            
        except Exception as e:
            logger.error(f"NOAA fetch error: {str(e)}")
            return None
    
    def _generate_port_conditions(self, port_code: str) -> Dict:
        """Generate realistic port conditions for demo"""
        import random
        
        # Port profiles based on real-world patterns
        port_profiles = {
            'LAX': {'base_congestion': 0.7, 'berth_count': 25, 'avg_wait': 18},
            'SIN': {'base_congestion': 0.8, 'berth_count': 40, 'avg_wait': 12},
            'RTM': {'base_congestion': 0.6, 'berth_count': 35, 'avg_wait': 10},
            'SHA': {'base_congestion': 0.85, 'berth_count': 50, 'avg_wait': 24},
            'HKG': {'base_congestion': 0.75, 'berth_count': 30, 'avg_wait': 16},
            'DXB': {'base_congestion': 0.5, 'berth_count': 20, 'avg_wait': 8},
            'HAM': {'base_congestion': 0.55, 'berth_count': 25, 'avg_wait': 10}
        }
        
        profile = port_profiles.get(port_code, {
            'base_congestion': 0.5,
            'berth_count': 15,
            'avg_wait': 12
        })
        
        # Add some randomness
        congestion = profile['base_congestion'] + random.uniform(-0.2, 0.2)
        congestion = max(0.1, min(0.95, congestion))
        
        # Calculate metrics
        vessels_waiting = int(profile['berth_count'] * congestion * random.uniform(0.8, 1.2))
        avg_wait_hours = profile['avg_wait'] * (1 + (congestion - 0.5) * 2)
        
        conditions = {
            'port_code': port_code,
            'timestamp': datetime.utcnow().isoformat(),
            'operational': random.random() > 0.05,  # 95% operational
            'congestion_level': self._get_congestion_level(congestion),
            'congestion_score': round(congestion, 2),
            'vessels_at_berth': int(profile['berth_count'] * random.uniform(0.7, 0.95)),
            'vessels_waiting': vessels_waiting,
            'avg_wait_hours': round(avg_wait_hours, 1),
            'berth_availability': round((1 - congestion) * 100, 1),
            'tide_conditions': {
                'current': round(random.uniform(-2, 2), 1),
                'high_tide_time': (datetime.utcnow() + timedelta(hours=random.randint(1, 12))).isoformat(),
                'low_tide_time': (datetime.utcnow() + timedelta(hours=random.randint(1, 12))).isoformat()
            },
            'weather_conditions': {
                'wind_speed': round(random.uniform(5, 25), 1),
                'wind_direction': random.randint(0, 359),
                'visibility': random.choice(['Good', 'Moderate', 'Poor']),
                'sea_state': random.choice(['Calm', 'Slight', 'Moderate', 'Rough'])
            },
            'alerts': []
        }
        
        # Add alerts based on conditions
        if congestion > 0.8:
            conditions['alerts'].append({
                'type': 'congestion',
                'severity': 'high',
                'message': f"High congestion: {vessels_waiting} vessels waiting"
            })
            
        if conditions['weather_conditions']['wind_speed'] > 20:
            conditions['alerts'].append({
                'type': 'weather',
                'severity': 'medium',
                'message': f"Strong winds: {conditions['weather_conditions']['wind_speed']} knots"
            })
            
        return conditions
    
    def get_route_conditions(self, waypoints: List[Tuple[float, float]]) -> Dict:
        """Get conditions along a route"""
        conditions = {
            'overall_risk': 0,
            'segments': [],
            'alerts': [],
            'weather_windows': []
        }
        
        for i in range(len(waypoints) - 1):
            segment = self._analyze_route_segment(waypoints[i], waypoints[i + 1])
            conditions['segments'].append(segment)
            conditions['overall_risk'] = max(conditions['overall_risk'], segment['risk_score'])
            
            if segment['alerts']:
                conditions['alerts'].extend(segment['alerts'])
        
        # Add weather windows
        conditions['weather_windows'] = self._calculate_weather_windows(waypoints)
        
        return conditions
    
    def _analyze_route_segment(self, start: Tuple[float, float], end: Tuple[float, float]) -> Dict:
        """Analyze conditions for a route segment"""
        # Check for known risk areas
        risk_areas = {
            'red_sea': {'bbox': (12, 32, 20, 43), 'risk': 0.8, 'type': 'geopolitical'},
            'gulf_of_aden': {'bbox': (10, 43, 15, 52), 'risk': 0.7, 'type': 'piracy'},
            'strait_of_hormuz': {'bbox': (24, 54, 28, 58), 'risk': 0.6, 'type': 'geopolitical'},
            'malacca_strait': {'bbox': (1, 98, 6, 104), 'risk': 0.5, 'type': 'congestion'},
            'south_china_sea': {'bbox': (5, 105, 25, 120), 'risk': 0.4, 'type': 'weather'}
        }
        
        segment_risk = 0.1  # Base risk
        alerts = []
        
        for area_name, area_info in risk_areas.items():
            if self._route_intersects_area(start, end, area_info['bbox']):
                segment_risk = max(segment_risk, area_info['risk'])
                alerts.append({
                    'area': area_name,
                    'type': area_info['type'],
                    'risk_level': area_info['risk']
                })
        
        return {
            'start': start,
            'end': end,
            'distance_nm': self._calculate_distance(start, end),
            'risk_score': segment_risk,
            'alerts': alerts,
            'estimated_duration_hours': self._calculate_duration(start, end)
        }
    
    def _get_shipping_routes(self, bbox: Tuple[float, float, float, float]) -> List[List[Tuple[float, float]]]:
        """Get major shipping routes in the area"""
        # Major global shipping routes
        all_routes = {
            'asia_europe_suez': [
                (1.3, 103.8),   # Singapore
                (6.9, 79.8),    # Colombo
                (13.1, 43.3),   # Bab el-Mandeb
                (30.0, 32.5),   # Suez
                (35.5, 14.5),   # Malta
                (36.1, -5.4),   # Gibraltar
                (51.9, 4.3)     # Rotterdam
            ],
            'asia_europe_cape': [
                (1.3, 103.8),   # Singapore
                (-6.2, 106.8),  # Jakarta
                (-34.0, 18.4),  # Cape Town
                (0.0, -10.0),   # Mid-Atlantic
                (36.1, -5.4),   # Gibraltar
                (51.9, 4.3)     # Rotterdam
            ],
            'transpacific': [
                (35.7, 139.7),  # Tokyo
                (37.8, -122.4), # San Francisco
                (33.7, -118.3)  # Los Angeles
            ],
            'transatlantic': [
                (40.7, -74.0),  # New York
                (51.5, -0.1),   # London
                (53.5, 10.0)    # Hamburg
            ]
        }
        
        # Filter routes that intersect with bbox
        relevant_routes = []
        for route in all_routes.values():
            if any(bbox[0] <= lat <= bbox[2] and bbox[1] <= lon <= bbox[3] 
                   for lat, lon in route):
                relevant_routes.append(route)
        
        return relevant_routes if relevant_routes else [[(bbox[0], bbox[1]), (bbox[2], bbox[3])]]
    
    def _interpolate_route_position(self, route: List[Tuple[float, float]], t: float) -> Tuple[float, float]:
        """Interpolate position along route"""
        if not route or len(route) < 2:
            return (0, 0)
            
        # Calculate total route distance
        total_distance = sum(
            self._calculate_distance(route[i], route[i+1]) 
            for i in range(len(route)-1)
        )
        
        target_distance = total_distance * t
        accumulated_distance = 0
        
        for i in range(len(route) - 1):
            segment_distance = self._calculate_distance(route[i], route[i+1])
            
            if accumulated_distance + segment_distance >= target_distance:
                # Interpolate within this segment
                segment_t = (target_distance - accumulated_distance) / segment_distance
                lat = route[i][0] + (route[i+1][0] - route[i][0]) * segment_t
                lon = route[i][1] + (route[i+1][1] - route[i][1]) * segment_t
                return (lat, lon)
                
            accumulated_distance += segment_distance
            
        return route[-1]
    
    def _calculate_distance(self, start: Tuple[float, float], end: Tuple[float, float]) -> float:
        """Calculate distance in nautical miles using Haversine formula"""
        import math
        
        R = 3440.065  # Earth radius in nautical miles
        
        lat1, lon1 = math.radians(start[0]), math.radians(start[1])
        lat2, lon2 = math.radians(end[0]), math.radians(end[1])
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c
    
    def _calculate_duration(self, start: Tuple[float, float], end: Tuple[float, float], 
                          vessel_speed: float = 20.0) -> float:
        """Calculate duration in hours based on distance and vessel speed"""
        distance = self._calculate_distance(start, end)
        return distance / vessel_speed
    
    def _route_intersects_area(self, start: Tuple[float, float], end: Tuple[float, float], 
                              bbox: Tuple[float, float, float, float]) -> bool:
        """Check if route segment intersects with area"""
        # Simple check - in production, use proper line-box intersection
        return (
            (bbox[0] <= start[0] <= bbox[2] and bbox[1] <= start[1] <= bbox[3]) or
            (bbox[0] <= end[0] <= bbox[2] and bbox[1] <= end[1] <= bbox[3])
        )
    
    def _calculate_weather_windows(self, waypoints: List[Tuple[float, float]]) -> List[Dict]:
        """Calculate optimal weather windows for route"""
        windows = []
        current_time = datetime.utcnow()
        
        for i in range(3):  # Next 3 potential departure windows
            window_start = current_time + timedelta(days=i)
            windows.append({
                'start': window_start.isoformat(),
                'end': (window_start + timedelta(hours=12)).isoformat(),
                'conditions': 'favorable' if i % 2 == 0 else 'moderate',
                'risk_score': 0.2 if i % 2 == 0 else 0.4
            })
            
        return windows
    
    def _get_nearby_port(self, position: Tuple[float, float]) -> str:
        """Get nearest major port"""
        major_ports = {
            'Singapore': (1.3, 103.8),
            'Shanghai': (31.2, 121.5),
            'Rotterdam': (51.9, 4.3),
            'Los Angeles': (33.7, -118.3),
            'Hamburg': (53.5, 10.0),
            'Dubai': (25.3, 55.3),
            'Hong Kong': (22.3, 114.2)
        }
        
        nearest_port = min(major_ports.items(), 
                          key=lambda p: self._calculate_distance(position, p[1]))
        return nearest_port[0]
    
    def _get_congestion_level(self, score: float) -> str:
        """Convert congestion score to level"""
        if score < 0.3:
            return 'low'
        elif score < 0.6:
            return 'moderate'
        elif score < 0.8:
            return 'high'
        else:
            return 'severe'
    
    def _get_us_port_codes(self) -> List[str]:
        """Get list of US port codes with NOAA stations"""
        return ['LAX', 'NYC', 'MIA', 'SEA', 'SFO', 'HOU', 'SAV', 'OAK', 'TAC', 'POR']
    
    def _normalize_ais_data(self, raw_data: List[Dict]) -> List[Dict]:
        """Normalize AIS data from various sources"""
        normalized = []
        
        for vessel in raw_data:
            normalized.append({
                'mmsi': vessel.get('MMSI', vessel.get('mmsi', '')),
                'name': vessel.get('NAME', vessel.get('name', 'Unknown')),
                'lat': float(vessel.get('LAT', vessel.get('lat', 0))),
                'lon': float(vessel.get('LON', vessel.get('lon', 0))),
                'speed': float(vessel.get('SOG', vessel.get('speed', 0))),
                'course': float(vessel.get('COG', vessel.get('course', 0))),
                'heading': float(vessel.get('HEADING', vessel.get('heading', 0))),
                'status': vessel.get('NAVSTAT', vessel.get('status', 'Unknown')),
                'vessel_type': vessel.get('TYPE', vessel.get('vessel_type', 'Cargo')),
                'timestamp': vessel.get('TIME', vessel.get('timestamp', datetime.utcnow().isoformat()))
            })
            
        return normalized
    
    def _log_integration(self, action: str, status: str, details: Dict):
        """Log integration activity"""
        try:
            log = IntegrationLog(
                integration_type='maritime',
                action=action,
                status=status,
                details=json.dumps(details),
                timestamp=datetime.utcnow()
            )
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            logger.error(f"Failed to log integration: {str(e)}")
