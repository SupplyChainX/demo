"""
Routing service integrations - OpenRouteService, OSRM
"""
import logging
import requests
from typing import Dict, List, Any, Optional, Tuple
from flask import current_app
import polyline

logger = logging.getLogger(__name__)

class RoutingIntegration:
    """Integration with routing services for route optimization."""
    
    def __init__(self):
        self.ors_api_key = current_app.config.get('OPENROUTESERVICE_API_KEY')
        self.ors_base_url = "https://api.openrouteservice.org/v2"
        self.osrm_base_url = current_app.config.get('OSRM_BASE_URL', 'http://router.project-osrm.org')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'SupplyChainX/1.0'
        })
        
        if self.ors_api_key:
            self.session.headers.update({
                'Authorization': self.ors_api_key
            })
    
    def calculate_maritime_route(self, origin: Tuple[float, float], 
                               destination: Tuple[float, float],
                               waypoints: List[Tuple[float, float]] = None) -> Dict[str, Any]:
        """Calculate maritime shipping route."""
        try:
            # For maritime routes, we need specialized routing
            # For demo, calculate great circle distance and estimated route
            
            route_info = {
                'origin': {'lat': origin[0], 'lon': origin[1]},
                'destination': {'lat': destination[0], 'lon': destination[1]},
                'waypoints': waypoints or [],
                'distance_nm': self._calculate_great_circle_nm(origin, destination),
                'estimated_days': 0,
                'route_type': 'maritime'
            }
            
            # Add waypoints for major shipping lanes
            if waypoints:
                total_distance = 0
                points = [origin] + waypoints + [destination]
                
                for i in range(len(points) - 1):
                    total_distance += self._calculate_great_circle_nm(points[i], points[i+1])
                
                route_info['distance_nm'] = total_distance
            
            # Estimate transit time (average 12-15 knots for cargo vessels)
            avg_speed_knots = 13
            route_info['estimated_days'] = round(route_info['distance_nm'] / (avg_speed_knots * 24), 1)
            
            # Generate route points for visualization
            route_info['geometry'] = self._generate_maritime_route_points(
                origin, destination, waypoints
            )
            
            return route_info
            
        except Exception as e:
            logger.error(f"Error calculating maritime route: {e}")
            return {}
    
    def calculate_road_route(self, origin: Tuple[float, float],
                           destination: Tuple[float, float],
                           vehicle_type: str = 'truck') -> Dict[str, Any]:
        """Calculate road route using OpenRouteService or OSRM."""
        try:
            if self.ors_api_key:
                return self._calculate_ors_route(origin, destination, vehicle_type)
            else:
                return self._calculate_osrm_route(origin, destination, vehicle_type)
                
        except Exception as e:
            logger.error(f"Error calculating road route: {e}")
            return {}
    
    def _calculate_ors_route(self, origin: Tuple[float, float],
                           destination: Tuple[float, float],
                           vehicle_type: str) -> Dict[str, Any]:
        """Calculate route using OpenRouteService."""
        try:
            # Map vehicle types
            profile_map = {
                'truck': 'driving-hgv',
                'car': 'driving-car',
                'van': 'driving-car'
            }
            profile = profile_map.get(vehicle_type, 'driving-car')
            
            # ORS expects lon,lat order
            coordinates = [[origin[1], origin[0]], [destination[1], destination[0]]]
            
            data = {
                'coordinates': coordinates,
                'profile': profile,
                'preference': 'recommended',
                'units': 'km',
                'geometry': True
            }
            
            response = self.session.post(
                f"{self.ors_base_url}/directions/{profile}",
                json=data,
                timeout=10
            )
            response.raise_for_status()
            
            route_data = response.json()
            
            if 'routes' in route_data and route_data['routes']:
                route = route_data['routes'][0]
                
                return {
                    'distance_km': route['summary']['distance'] / 1000,
                    'duration_hours': route['summary']['duration'] / 3600,
                    'geometry': route['geometry'],
                    'bbox': route['bbox'],
                    'waypoints': self._decode_geometry(route['geometry']),
                    'route_type': 'road',
                    'service': 'openrouteservice'
                }
                
        except Exception as e:
            logger.error(f"Error with OpenRouteService: {e}")
            
        return {}
    
    def _calculate_osrm_route(self, origin: Tuple[float, float],
                            destination: Tuple[float, float],
                            vehicle_type: str) -> Dict[str, Any]:
        """Calculate route using OSRM."""
        try:
            # OSRM format: lon,lat;lon,lat
            coords = f"{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
            
            params = {
                'overview': 'full',
                'geometries': 'polyline',
                'steps': 'false'
            }
            
            response = self.session.get(
                f"{self.osrm_base_url}/route/v1/driving/{coords}",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('code') == 'Ok' and data.get('routes'):
                route = data['routes'][0]
                
                return {
                    'distance_km': route['distance'] / 1000,
                    'duration_hours': route['duration'] / 3600,
                    'geometry': route['geometry'],
                    'waypoints': polyline.decode(route['geometry']),
                    'route_type': 'road',
                    'service': 'osrm'
                }
                
        except Exception as e:
            logger.error(f"Error with OSRM: {e}")
            
        return {}
    
    def calculate_multimodal_route(self, segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate multimodal route with multiple transport modes."""
        try:
            total_distance = 0
            total_duration = 0
            total_cost = 0
            total_emissions = 0
            
            route_segments = []
            
            for segment in segments:
                mode = segment.get('mode', 'road')
                origin = segment.get('origin')
                destination = segment.get('destination')
                
                if mode == 'maritime':
                    route = self.calculate_maritime_route(origin, destination)
                elif mode == 'rail':
                    # For rail, approximate with road * factor
                    road_route = self.calculate_road_route(origin, destination)
                    if road_route:
                        route = {
                            **road_route,
                            'distance_km': road_route.get('distance_km', 0) * 1.1,
                            'duration_hours': road_route.get('duration_hours', 0) * 1.5,
                            'route_type': 'rail'
                        }
                    else:
                        route = {}
                else:
                    route = self.calculate_road_route(origin, destination)
                
                if route:
                    # Calculate segment costs and emissions
                    distance = route.get('distance_km', 0)
                    duration = route.get('duration_hours', 0)
                    
                    cost = self._estimate_segment_cost(mode, distance, duration)
                    emissions = self._estimate_segment_emissions(mode, distance)
                    
                    route_segments.append({
                        **route,
                        'mode': mode,
                        'cost': cost,
                        'emissions_kg': emissions
                    })
                    
                    total_distance += distance
                    total_duration += duration
                    total_cost += cost
                    total_emissions += emissions
            
            return {
                'segments': route_segments,
                'total_distance_km': total_distance,
                'total_duration_hours': total_duration,
                'total_cost': total_cost,
                'total_emissions_kg': total_emissions,
                'route_type': 'multimodal'
            }
            
        except Exception as e:
            logger.error(f"Error calculating multimodal route: {e}")
            return {}
    
    # Helper methods
    def _calculate_great_circle_nm(self, point1: Tuple[float, float], 
                                  point2: Tuple[float, float]) -> float:
        """Calculate great circle distance in nautical miles."""
        import math
        
        lat1, lon1 = math.radians(point1[0]), math.radians(point1[1])
        lat2, lon2 = math.radians(point2[0]), math.radians(point2[1])
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # Earth radius in nautical miles
        R = 3440.065
        
        return round(R * c, 1)
    
    def _generate_maritime_route_points(self, origin: Tuple[float, float],
                                      destination: Tuple[float, float],
                                      waypoints: List[Tuple[float, float]] = None) -> List[List[float]]:
        """Generate points along maritime route for visualization."""
        points = []
        
        # Add all points in order
        all_points = [origin]
        if waypoints:
            all_points.extend(waypoints)
        all_points.append(destination)
        
        # Generate intermediate points for smooth visualization
        for i in range(len(all_points) - 1):
            start = all_points[i]
            end = all_points[i + 1]
            
            # Add intermediate points
            num_points = 10
            for j in range(num_points + 1):
                ratio = j / num_points
                lat = start[0] + (end[0] - start[0]) * ratio
                lon = start[1] + (end[1] - start[1]) * ratio
                points.append([lon, lat])  # GeoJSON format
        
        return points
    
    def _decode_geometry(self, encoded: str) -> List[List[float]]:
        """Decode polyline geometry."""
        try:
            decoded = polyline.decode(encoded)
            # Convert to [lon, lat] format for GeoJSON
            return [[point[1], point[0]] for point in decoded]
        except:
            return []
    
    def _estimate_segment_cost(self, mode: str, distance_km: float, 
                             duration_hours: float) -> float:
        """Estimate cost for route segment."""
        # Simplified cost model (USD)
        cost_per_km = {
            'maritime': 0.05,
            'rail': 0.15,
            'road': 0.25,
            'air': 2.50
        }
        
        base_cost = distance_km * cost_per_km.get(mode, 0.20)
        
        # Add time-based costs
        time_cost = duration_hours * 10  # $10/hour opportunity cost
        
        return round(base_cost + time_cost, 2)
    
    def _estimate_segment_emissions(self, mode: str, distance_km: float) -> float:
        """Estimate CO2 emissions for route segment."""
        # kg CO2 per km
        emission_factors = {
            'maritime': 16,  # Cargo ship
            'rail': 41,      # Freight train
            'road': 62,      # Heavy truck
            'air': 500       # Air cargo
        }
        
        return round(distance_km * emission_factors.get(mode, 50) / 1000, 2)
