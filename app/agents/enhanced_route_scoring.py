"""
Enhanced Route Scoring with Risk Data Integration
================================================

This module provides sophisticated route scoring that integrates
real-time risk data from multiple sources.
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class EnhancedRouteScorer:
    """Enhanced route scoring with risk data integration."""
    
    def __init__(self, weather_api=None, geopolitical_api=None, maritime_api=None):
        self.weather_api = weather_api
        self.geopolitical_api = geopolitical_api
        self.maritime_api = maritime_api
        
        # Scoring weights for different factors
        self.scoring_weights = {
            'cost': 0.25,
            'time': 0.20,
            'risk': 0.30,
            'emissions': 0.15,
            'reliability': 0.10
        }
        
        # Risk factor weights
        self.risk_weights = {
            'weather': 0.35,
            'geopolitical': 0.30,
            'piracy': 0.20,
            'port_congestion': 0.15
        }
    
    def score_route_with_risk_data(self, route_data: Dict, shipment_data: Dict) -> Dict[str, Any]:
        """Score route using integrated risk data."""
        try:
            waypoints = route_data.get('waypoints', [])
            
            # Base metrics
            base_score = self._calculate_base_score(route_data)
            
            # Risk-enhanced scoring
            weather_score = self._calculate_weather_risk_score(waypoints)
            geopolitical_score = self._calculate_geopolitical_risk_score(waypoints)
            maritime_score = self._calculate_maritime_risk_score(waypoints)
            
            # Combine risk scores
            combined_risk_score = (
                self.risk_weights['weather'] * weather_score +
                self.risk_weights['geopolitical'] * geopolitical_score +
                self.risk_weights['port_congestion'] * maritime_score
            )
            
            # Calculate final composite score
            final_score = (
                self.scoring_weights['cost'] * base_score['cost_score'] +
                self.scoring_weights['time'] * base_score['time_score'] +
                self.scoring_weights['risk'] * (1 - combined_risk_score) +
                self.scoring_weights['emissions'] * base_score['emissions_score'] +
                self.scoring_weights['reliability'] * base_score['reliability_score']
            )
            
            return {
                'composite_score': final_score,
                'base_scores': base_score,
                'risk_scores': {
                    'weather': weather_score,
                    'geopolitical': geopolitical_score,
                    'maritime': maritime_score,
                    'combined': combined_risk_score
                },
                'scoring_metadata': {
                    'weights_used': self.scoring_weights,
                    'risk_weights_used': self.risk_weights,
                    'scored_at': datetime.utcnow().isoformat(),
                    'data_sources': self._get_data_sources()
                }
            }
            
        except Exception as e:
            logger.error(f"Error in risk-based route scoring: {e}")
            return self._fallback_scoring(route_data)
    
    def _calculate_base_score(self, route_data: Dict) -> Dict[str, float]:
        """Calculate base scores for standard metrics."""
        cost = route_data.get('cost_usd', 0)
        duration = route_data.get('estimated_duration_hours', 0)
        emissions = route_data.get('carbon_emissions_kg', 0)
        distance = route_data.get('distance_km', 0)
        
        # Normalize scores (higher is better)
        cost_score = max(0, 1 - (cost / 500000))  # Assuming max cost 500k
        time_score = max(0, 1 - (duration / 720))  # Assuming max 30 days
        emissions_score = max(0, 1 - (emissions / 50000))  # Assuming max 50 tons
        reliability_score = 0.8  # Base reliability, enhanced by risk data
        
        return {
            'cost_score': cost_score,
            'time_score': time_score,
            'emissions_score': emissions_score,
            'reliability_score': reliability_score
        }
    
    def _calculate_weather_risk_score(self, waypoints: List[Dict]) -> float:
        """Calculate weather risk score along route."""
        try:
            if not self.weather_api or not waypoints:
                return 0.3  # Default moderate risk
            
            # Get weather forecast for route
            route_coords = [(wp.get('lat', 0), wp.get('lon', 0)) for wp in waypoints]
            weather_data = self.weather_api.analyze_route_weather(route_coords)
            
            # Extract risk factors
            wind_risk = weather_data.get('wind_risk', 0.2)
            wave_risk = weather_data.get('wave_risk', 0.2)
            storm_risk = weather_data.get('storm_probability', 0.1)
            visibility_risk = weather_data.get('visibility_risk', 0.1)
            
            # Combine weather risks
            overall_weather_risk = min(1.0, (
                wind_risk * 0.3 +
                wave_risk * 0.3 +
                storm_risk * 0.3 +
                visibility_risk * 0.1
            ))
            
            return overall_weather_risk
            
        except Exception as e:
            logger.warning(f"Weather risk calculation failed: {e}")
            return 0.3
    
    def _calculate_geopolitical_risk_score(self, waypoints: List[Dict]) -> float:
        """Calculate geopolitical risk score along route."""
        try:
            if not self.geopolitical_api or not waypoints:
                return 0.2  # Default low risk
            
            max_risk = 0.1
            
            # Check each route segment for geopolitical risks
            for i in range(len(waypoints) - 1):
                start_point = (waypoints[i].get('lat', 0), waypoints[i].get('lon', 0))
                end_point = (waypoints[i+1].get('lat', 0), waypoints[i+1].get('lon', 0))
                
                segment_data = self.geopolitical_api.assess_route_segment(start_point, end_point)
                segment_risk = segment_data.get('risk_score', 0.1)
                max_risk = max(max_risk, segment_risk)
            
            return max_risk
            
        except Exception as e:
            logger.warning(f"Geopolitical risk calculation failed: {e}")
            return 0.2
    
    def _calculate_maritime_risk_score(self, waypoints: List[Dict]) -> float:
        """Calculate maritime and port congestion risk score."""
        try:
            if not self.maritime_api or not waypoints:
                return 0.2  # Default low risk
            
            port_waypoints = [wp for wp in waypoints if wp.get('type') == 'port']
            
            if not port_waypoints:
                return 0.1  # No ports, low risk
            
            total_congestion_risk = 0
            port_count = 0
            
            for port_wp in port_waypoints:
                port_name = port_wp.get('name', '')
                port_code = self._map_port_name_to_code(port_name)
                
                if port_code:
                    port_conditions = self.maritime_api.fetch_port_conditions(port_code)
                    congestion_risk = port_conditions.get('congestion_score', 0.3)
                    total_congestion_risk += congestion_risk
                    port_count += 1
            
            if port_count == 0:
                return 0.2
            
            average_congestion_risk = total_congestion_risk / port_count
            return min(1.0, average_congestion_risk)
            
        except Exception as e:
            logger.warning(f"Maritime risk calculation failed: {e}")
            return 0.2
    
    def _map_port_name_to_code(self, port_name: str) -> Optional[str]:
        """Map port name to standard port code."""
        port_mapping = {
            'singapore': 'SGSIN',
            'rotterdam': 'NLRTM',
            'shanghai': 'CNSHA',
            'los angeles': 'USLAX',
            'hamburg': 'DEHAM',
            'hong kong': 'HKHKG',
            'dubai': 'AEDXB',
            'colombo': 'LKCMB',
            'cape town': 'ZACPT',
            'gibraltar': 'GIGIB',
            'suez': 'EGSUZ',
            'panama': 'PAPAN'
        }
        
        name_lower = port_name.lower()
        for key, code in port_mapping.items():
            if key in name_lower:
                return code
        return None
    
    def _get_data_sources(self) -> List[str]:
        """Get list of available data sources."""
        sources = ['internal_metrics']
        
        if self.weather_api:
            sources.append('weather_api')
        if self.geopolitical_api:
            sources.append('geopolitical_api')
        if self.maritime_api:
            sources.append('maritime_api')
        
        return sources
    
    def _fallback_scoring(self, route_data: Dict) -> Dict[str, Any]:
        """Fallback scoring when APIs are not available."""
        base_score = self._calculate_base_score(route_data)
        composite_score = (
            base_score['cost_score'] * 0.4 +
            base_score['time_score'] * 0.3 +
            base_score['emissions_score'] * 0.2 +
            base_score['reliability_score'] * 0.1
        )
        
        return {
            'composite_score': composite_score,
            'base_scores': base_score,
            'risk_scores': {
                'weather': 0.3,
                'geopolitical': 0.2,
                'maritime': 0.2,
                'combined': 0.25
            },
            'scoring_metadata': {
                'weights_used': {'fallback': True},
                'scored_at': datetime.utcnow().isoformat(),
                'data_sources': ['internal_metrics']
            }
        }

def create_enhanced_scorer(weather_api=None, geopolitical_api=None, maritime_api=None):
    """Factory function to create enhanced route scorer."""
    return EnhancedRouteScorer(weather_api, geopolitical_api, maritime_api)
