"""
Geopolitical data integration - GDELT, news sentiment
"""
import logging
import requests
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from flask import current_app
from app.models import db, IntegrationLog

logger = logging.getLogger(__name__)

class GeopoliticalIntegration:
    """Integration with geopolitical event and news data sources."""
    
    def __init__(self):
        self.endpoints = {
            'gdelt_events': 'https://api.gdeltproject.org/api/v2/doc/doc',
            'gdelt_gkg': 'https://api.gdeltproject.org/api/v2/gkg/gkg',
            'acled': 'https://api.acleddata.com/acled/read',  # Requires key
            'reliefweb': 'https://api.reliefweb.int/v1/reports'
        }
        
        # Risk scoring weights
        self.event_weights = {
            'PROTEST': 0.3,
            'CONFLICT': 0.8,
            'VIOLENCE': 0.9,
            'POLITICAL_TENSION': 0.5,
            'STRIKE': 0.4,
            'BORDER_CLOSURE': 0.7,
            'SANCTIONS': 0.6,
            'COUP': 0.9,
            'TERRORISM': 0.95
        }
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'SupplyChainX/1.0 (supply-chain-monitoring)'
        })
    
    def query_gdelt_events(self, location: Tuple[float, float], 
                          radius_km: float = 100, 
                          timeframe_hours: int = 72) -> List[Dict]:
        """Query GDELT for events near location"""
        try:
            # GDELT uses a different query format
            # We'll use the DOC API for article search
            
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=timeframe_hours)
            
            # Format: YYYYMMDDHHMMSS
            start_str = start_time.strftime('%Y%m%d%H%M%S')
            end_str = end_time.strftime('%Y%m%d%H%M%S')
            
            # Build location query
            lat, lon = location
            location_query = f"near:{lat},{lon},{int(radius_km)}km"
            
            params = {
                'query': location_query,
                'mode': 'artlist',
                'maxrecords': 250,
                'timespan': f"{start_str}-{end_str}",
                'format': 'json',
                'sort': 'hybridrel'
            }
            
            response = self.session.get(
                self.endpoints['gdelt_events'],
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                events = self._parse_gdelt_response(data, location)
                
                # Log successful integration
                self._log_integration('gdelt_query', 'success', {
                    'location': location,
                    'event_count': len(events)
                })
                
                return events
            else:
                logger.warning(f"GDELT API returned status {response.status_code}")
                
        except Exception as e:
            logger.error(f"GDELT query error: {str(e)}")
            self._log_integration('gdelt_query', 'error', {'error': str(e)})
            
        # Return generated events for demo
        return self._generate_demo_events(location, radius_km)
    
    def _parse_gdelt_response(self, data: Dict, location: Tuple[float, float]) -> List[Dict]:
        """Parse GDELT response into standardized events"""
        events = []
        
        if 'articles' not in data:
            return events
            
        for article in data['articles'][:50]:  # Limit to top 50
            # Extract event type from title and content
            event_type = self._classify_event(article)
            
            if event_type:
                events.append({
                    'id': article.get('url', '').split('/')[-1],
                    'type': event_type,
                    'title': article.get('title', ''),
                    'source': article.get('domain', ''),
                    'url': article.get('url', ''),
                    'published': article.get('seendate', ''),
                    'location': location,
                    'tone': float(article.get('tone', 0)),
                    'goldstein': float(article.get('goldstein', 0)),
                    'risk_score': self.event_weights.get(event_type, 0.3)
                })
                
        return events
    
    def _classify_event(self, article: Dict) -> Optional[str]:
        """Classify article into event type"""
        title = article.get('title', '').lower()
        
        # Simple keyword-based classification
        classifications = {
            'PROTEST': ['protest', 'demonstration', 'rally', 'march'],
            'CONFLICT': ['conflict', 'clash', 'fighting', 'battle'],
            'VIOLENCE': ['violence', 'attack', 'killed', 'injured'],
            'POLITICAL_TENSION': ['tension', 'dispute', 'crisis', 'standoff'],
            'STRIKE': ['strike', 'walkout', 'work stoppage'],
            'BORDER_CLOSURE': ['border closed', 'border closure', 'crossing closed'],
            'SANCTIONS': ['sanctions', 'embargo', 'restrictions'],
            'COUP': ['coup', 'overthrow', 'military takeover'],
            'TERRORISM': ['terrorism', 'terrorist', 'bombing', 'explosion']
        }
        
        for event_type, keywords in classifications.items():
            if any(keyword in title for keyword in keywords):
                return event_type
                
        return None
    
    def _generate_demo_events(self, location: Tuple[float, float], 
                            radius_km: float) -> List[Dict]:
        """Generate realistic demo events"""
        import random
        
        # Define event scenarios by region
        lat, lon = location
        
        events = []
        
        # Red Sea region
        if 12 <= lat <= 20 and 32 <= lon <= 43:
            events.extend([
                {
                    'id': 'demo_red_sea_1',
                    'type': 'CONFLICT',
                    'title': 'Houthi militants threaten shipping in Red Sea corridor',
                    'source': 'Reuters',
                    'url': 'https://example.com/red-sea-threat',
                    'published': datetime.utcnow().isoformat(),
                    'location': location,
                    'tone': -7.5,
                    'goldstein': -8.0,
                    'risk_score': 0.8
                },
                {
                    'id': 'demo_red_sea_2',
                    'type': 'POLITICAL_TENSION',
                    'title': 'Naval forces increase patrols in Gulf of Aden',
                    'source': 'AP News',
                    'url': 'https://example.com/naval-patrols',
                    'published': (datetime.utcnow() - timedelta(hours=12)).isoformat(),
                    'location': location,
                    'tone': -4.2,
                    'goldstein': -3.5,
                    'risk_score': 0.5
                }
            ])
            
        # Suez Canal region
        elif 29 <= lat <= 31 and 32 <= lon <= 33:
            events.append({
                'id': 'demo_suez_1',
                'type': 'POLITICAL_TENSION',
                'title': 'Suez Canal Authority announces new transit regulations',
                'source': 'Egypt Today',
                'url': 'https://example.com/suez-regulations',
                'published': datetime.utcnow().isoformat(),
                'location': location,
                'tone': -2.1,
                'goldstein': -1.5,
                'risk_score': 0.3
            })
            
        # South China Sea
        elif 5 <= lat <= 25 and 105 <= lon <= 120:
            events.extend([
                {
                    'id': 'demo_scs_1',
                    'type': 'POLITICAL_TENSION',
                    'title': 'Territorial disputes escalate in South China Sea',
                    'source': 'Bloomberg',
                    'url': 'https://example.com/scs-disputes',
                    'published': datetime.utcnow().isoformat(),
                    'location': location,
                    'tone': -5.3,
                    'goldstein': -4.0,
                    'risk_score': 0.6
                },
                {
                    'id': 'demo_scs_2',
                    'type': 'CONFLICT',
                    'title': 'Naval standoff reported near disputed islands',
                    'source': 'CNN',
                    'url': 'https://example.com/naval-standoff',
                    'published': (datetime.utcnow() - timedelta(hours=6)).isoformat(),
                    'location': location,
                    'tone': -6.8,
                    'goldstein': -7.0,
                    'risk_score': 0.7
                }
            ])
            
        # Europe (strikes/protests)
        elif 45 <= lat <= 55 and -5 <= lon <= 20:
            events.append({
                'id': 'demo_europe_1',
                'type': 'STRIKE',
                'title': 'Port workers announce 48-hour strike in major European ports',
                'source': 'Financial Times',
                'url': 'https://example.com/port-strike',
                'published': datetime.utcnow().isoformat(),
                'location': location,
                'tone': -3.5,
                'goldstein': -2.5,
                'risk_score': 0.4
            })
            
        # Add some general events with lower probability
        if random.random() > 0.7:
            events.append({
                'id': f'demo_general_{random.randint(1000, 9999)}',
                'type': random.choice(['PROTEST', 'POLITICAL_TENSION', 'STRIKE']),
                'title': 'Local unrest reported in industrial district',
                'source': 'Local News',
                'url': 'https://example.com/local-unrest',
                'published': datetime.utcnow().isoformat(),
                'location': location,
                'tone': -3.0,
                'goldstein': -2.0,
                'risk_score': 0.3
            })
            
        return events
    
    def analyze_sentiment(self, articles: List[Dict]) -> Dict:
        """Analyze sentiment and risk from articles"""
        if not articles:
            return {
                'overall_sentiment': 0,
                'risk_assessment': 0,
                'confidence': 0,
                'factors': []
            }
            
        # Calculate aggregate metrics
        total_tone = sum(article.get('tone', 0) for article in articles)
        total_goldstein = sum(article.get('goldstein', 0) for article in articles)
        avg_risk = sum(article.get('risk_score', 0) for article in articles) / len(articles)
        
        avg_tone = total_tone / len(articles)
        avg_goldstein = total_goldstein / len(articles)
        
        # Normalize sentiment to 0-1 scale (inverted, negative is bad)
        # GDELT tone ranges from -10 to +10
        normalized_sentiment = (10 - avg_tone) / 20
        
        # Calculate overall risk
        # Combine article risk scores with sentiment
        overall_risk = (avg_risk * 0.6) + (normalized_sentiment * 0.4)
        
        # Identify key risk factors
        risk_factors = []
        event_counts = {}
        
        for article in articles:
            event_type = article.get('type')
            if event_type:
                event_counts[event_type] = event_counts.get(event_type, 0) + 1
                
        for event_type, count in sorted(event_counts.items(), 
                                      key=lambda x: x[1], reverse=True):
            if count >= 2:  # At least 2 occurrences
                risk_factors.append({
                    'type': event_type,
                    'count': count,
                    'severity': self.event_weights.get(event_type, 0.3)
                })
                
        return {
            'overall_sentiment': round(normalized_sentiment, 2),
            'risk_assessment': round(overall_risk, 2),
            'confidence': min(0.9, 0.3 + (len(articles) * 0.05)),  # More articles = higher confidence
            'factors': risk_factors,
            'metrics': {
                'avg_tone': round(avg_tone, 2),
                'avg_goldstein': round(avg_goldstein, 2),
                'article_count': len(articles)
            }
        }
    
    def assess_route_segment(self, start: Tuple[float, float], 
                           end: Tuple[float, float]) -> Dict:
        """Assess geopolitical risk for a route segment"""
        # Calculate midpoint
        mid_lat = (start[0] + end[0]) / 2
        mid_lon = (start[1] + end[1]) / 2
        
        # Query events near the route
        events = self.query_gdelt_events((mid_lat, mid_lon), radius_km=200)
        
        # Analyze sentiment and risk
        analysis = self.analyze_sentiment(events)
        
        # Check for specific high-risk zones
        risk_zones = self._check_risk_zones(start, end)
        
        # Combine assessments
        zone_risk = max([zone['risk'] for zone in risk_zones], default=0)
        combined_risk = max(analysis['risk_assessment'], zone_risk)
        
        return {
            'segment': {'start': start, 'end': end},
            'risk_score': combined_risk,
            'sentiment': analysis['overall_sentiment'],
            'confidence': analysis['confidence'],
            'events': len(events),
            'risk_zones': risk_zones,
            'factors': analysis['factors']
        }
    
    def _check_risk_zones(self, start: Tuple[float, float], 
                         end: Tuple[float, float]) -> List[Dict]:
        """Check if route passes through known risk zones"""
        risk_zones = []
        
        # Define high-risk zones
        zones = {
            'red_sea_conflict': {
                'bbox': (12, 32, 20, 43),
                'name': 'Red Sea Conflict Zone',
                'risk': 0.8,
                'type': 'military_conflict'
            },
            'gulf_of_aden': {
                'bbox': (10, 43, 15, 52),
                'name': 'Gulf of Aden - Piracy Risk',
                'risk': 0.7,
                'type': 'piracy'
            },
            'strait_of_hormuz': {
                'bbox': (24, 54, 28, 58),
                'name': 'Strait of Hormuz',
                'risk': 0.6,
                'type': 'geopolitical_tension'
            },
            'south_china_sea': {
                'bbox': (5, 105, 25, 120),
                'name': 'South China Sea Disputes',
                'risk': 0.5,
                'type': 'territorial_dispute'
            },
            'malacca_strait': {
                'bbox': (1, 98, 6, 104),
                'name': 'Strait of Malacca',
                'risk': 0.4,
                'type': 'piracy'
            },
            'eastern_mediterranean': {
                'bbox': (30, 25, 37, 35),
                'name': 'Eastern Mediterranean',
                'risk': 0.5,
                'type': 'regional_tension'
            }
        }
        
        for zone_id, zone_info in zones.items():
            if self._route_intersects_zone(start, end, zone_info['bbox']):
                risk_zones.append({
                    'id': zone_id,
                    'name': zone_info['name'],
                    'risk': zone_info['risk'],
                    'type': zone_info['type']
                })
                
        return risk_zones
    
    def _route_intersects_zone(self, start: Tuple[float, float], 
                              end: Tuple[float, float], 
                              bbox: Tuple[float, float, float, float]) -> bool:
        """Check if route intersects with bounding box"""
        # Simple check - in production use proper line-box intersection
        lat1, lon1 = start
        lat2, lon2 = end
        min_lat, min_lon, max_lat, max_lon = bbox
        
        # Check if either endpoint is in box
        if (min_lat <= lat1 <= max_lat and min_lon <= lon1 <= max_lon) or \
           (min_lat <= lat2 <= max_lat and min_lon <= lon2 <= max_lon):
            return True
            
        # Check if route crosses box (simplified)
        route_min_lat = min(lat1, lat2)
        route_max_lat = max(lat1, lat2)
        route_min_lon = min(lon1, lon2)
        route_max_lon = max(lon1, lon2)
        
        # Check for overlap
        return not (route_max_lat < min_lat or route_min_lat > max_lat or
                   route_max_lon < min_lon or route_min_lon > max_lon)
    
    def get_country_risk_profile(self, country_code: str) -> Dict:
        """Get risk profile for a specific country"""
        # In production, integrate with country risk APIs
        # For demo, use predefined profiles
        
        risk_profiles = {
            'YE': {'risk': 0.9, 'factors': ['conflict', 'humanitarian_crisis']},
            'SY': {'risk': 0.9, 'factors': ['conflict', 'sanctions']},
            'AF': {'risk': 0.85, 'factors': ['conflict', 'political_instability']},
            'SO': {'risk': 0.85, 'factors': ['conflict', 'piracy']},
            'LY': {'risk': 0.8, 'factors': ['conflict', 'political_instability']},
            'VE': {'risk': 0.7, 'factors': ['economic_crisis', 'political_tension']},
            'IR': {'risk': 0.7, 'factors': ['sanctions', 'regional_tension']},
            'UA': {'risk': 0.8, 'factors': ['conflict', 'infrastructure_damage']},
            'ML': {'risk': 0.6, 'factors': ['terrorism', 'political_instability']},
            'NE': {'risk': 0.6, 'factors': ['terrorism', 'political_instability']}
        }
        
        profile = risk_profiles.get(country_code, {'risk': 0.2, 'factors': []})
        
        return {
            'country_code': country_code,
            'risk_score': profile['risk'],
            'risk_factors': profile['factors'],
            'last_updated': datetime.utcnow().isoformat()
        }
    
    def get_location_risk(self, location_name: str, country_code: str = None) -> Dict:
        """
        Get comprehensive risk assessment for a location - Primary method for Risk Predictor Agent
        This is the main method called by the Enhanced Risk Predictor Agent
        """
        try:
            logger.info(f"🌍 Assessing geopolitical risk for {location_name} ({country_code})")
            
            # Get coordinates for the location
            coordinates = self._get_location_coordinates(location_name, country_code)
            
            if not coordinates:
                logger.warning(f"Could not find coordinates for {location_name}")
                return self._generate_fallback_risk_assessment(location_name, country_code)
            
            # Query GDELT events for the location
            events = self.query_gdelt_events(coordinates, radius_km=150, timeframe_hours=168)  # 1 week
            
            # Analyze the events
            sentiment_analysis = self.analyze_sentiment(events)
            
            # Get country-specific risk profile
            country_risk = self.get_country_risk_profile(country_code) if country_code else {}
            
            # Assess route risks if in shipping corridor
            route_risk = self.assess_route_segment(coordinates, coordinates)
            
            # Combine all risk factors
            combined_risk = self._calculate_combined_risk_score(
                sentiment_analysis, country_risk, route_risk, events
            )
            
            risk_assessment = {
                'location': location_name,
                'country_code': country_code,
                'coordinates': coordinates,
                'risk_level': self._get_risk_level(combined_risk),
                'risk_score': round(combined_risk, 2),
                'confidence': sentiment_analysis.get('confidence', 0.7),
                'assessment_time': datetime.utcnow().isoformat(),
                'event_count': len(events),
                'sentiment_score': sentiment_analysis.get('overall_sentiment', 0.5),
                'country_risk': country_risk.get('risk_score', 0.3),
                'primary_risks': self._identify_primary_risks(events, sentiment_analysis),
                'recommendations': self._generate_risk_recommendations(combined_risk, events),
                'data_sources': ['gdelt', 'country_profiles', 'risk_zones'],
                'next_assessment': (datetime.utcnow() + timedelta(hours=6)).isoformat()
            }
            
            # Log successful assessment
            self._log_integration('location_risk_assessment', 'success', {
                'location': location_name,
                'risk_score': combined_risk,
                'event_count': len(events)
            })
            
            return risk_assessment
            
        except Exception as e:
            logger.error(f"Location risk assessment error for {location_name}: {e}")
            return self._generate_fallback_risk_assessment(location_name, country_code, str(e))
    
    def _get_location_coordinates(self, location_name: str, country_code: str = None) -> Optional[Tuple[float, float]]:
        """Get coordinates for a location using various methods"""
        try:
            # Major cities and ports database
            major_locations = {
                'singapore': (1.3521, 103.8198),
                'rotterdam': (51.9244, 4.4777),
                'shanghai': (31.2304, 121.4737),
                'los angeles': (34.0522, -118.2437),
                'new york': (40.7128, -74.0060),
                'hong kong': (22.3193, 114.1694),
                'dubai': (25.2048, 55.2708),
                'hamburg': (53.5511, 9.9937),
                'london': (51.5074, -0.1278),
                'tokyo': (35.6762, 139.6503),
                'sydney': (-33.8688, 151.2093),
                'mumbai': (19.0760, 72.8777),
                'cairo': (30.0444, 31.2357),
                'istanbul': (41.0082, 28.9784),
                'suez': (29.9668, 32.5498),
                'panama city': (8.9824, -79.5199),
                'gibraltar': (36.1408, -5.3536),
                'strait of malacca': (4.0000, 100.0000),
                'red sea': (18.0000, 39.0000),
                'gulf of aden': (12.0000, 48.0000),
                'south china sea': (15.0000, 115.0000),
                'persian gulf': (26.0000, 52.0000),
                'mediterranean': (35.0000, 18.0000),
                'north sea': (56.0000, 3.0000),
                'baltic sea': (58.0000, 20.0000)
            }
            
            # Normalize location name
            location_key = location_name.lower().strip()
            
            if location_key in major_locations:
                return major_locations[location_key]
            
            # Try partial matches
            for loc, coords in major_locations.items():
                if location_key in loc or loc in location_key:
                    return coords
            
            # Country capitals as fallback
            if country_code:
                country_capitals = {
                    'US': (39.8283, -98.5795),
                    'CN': (35.8617, 104.1954),
                    'SG': (1.3521, 103.8198),
                    'NL': (52.1326, 5.2913),
                    'DE': (51.1657, 10.4515),
                    'GB': (55.3781, -3.4360),
                    'JP': (36.2048, 138.2529),
                    'AE': (23.4241, 53.8478),
                    'EG': (26.0975, 30.0444),
                    'TR': (38.9637, 35.2433),
                    'YE': (15.5527, 48.5164),
                    'SO': (5.1521, 46.1996),
                    'SY': (34.8021, 38.9968),
                    'IR': (32.4279, 53.6880)
                }
                
                if country_code in country_capitals:
                    return country_capitals[country_code]
            
            return None
            
        except Exception as e:
            logger.error(f"Coordinate lookup error: {e}")
            return None
    
    def _calculate_combined_risk_score(self, sentiment_analysis: Dict, country_risk: Dict, 
                                     route_risk: Dict, events: List[Dict]) -> float:
        """Calculate combined risk score from multiple factors"""
        try:
            # Base weights for different risk factors
            weights = {
                'sentiment': 0.3,
                'country': 0.25,
                'route': 0.2,
                'events': 0.15,
                'recency': 0.1
            }
            
            # Sentiment risk (higher sentiment = lower risk)
            sentiment_risk = sentiment_analysis.get('overall_sentiment', 0.5)
            
            # Country baseline risk
            country_risk_score = country_risk.get('risk_score', 0.3)
            
            # Route/zone specific risks
            route_risk_score = route_risk.get('risk_score', 0.2)
            
            # Event-based risk (more high-severity events = higher risk)
            event_risk = min(0.9, len(events) * 0.05)  # Cap at 0.9
            high_severity_events = [e for e in events if e.get('risk_score', 0) > 0.7]
            if high_severity_events:
                event_risk = min(0.9, event_risk + len(high_severity_events) * 0.1)
            
            # Recency factor (recent events are more concerning)
            recency_risk = 0.2
            recent_events = [e for e in events if self._is_recent_event(e)]
            if recent_events:
                recency_risk = min(0.8, 0.2 + len(recent_events) * 0.05)
            
            # Calculate weighted risk
            combined_risk = (
                sentiment_risk * weights['sentiment'] +
                country_risk_score * weights['country'] +
                route_risk_score * weights['route'] +
                event_risk * weights['events'] +
                recency_risk * weights['recency']
            )
            
            return min(0.95, max(0.05, combined_risk))  # Keep between 0.05 and 0.95
            
        except Exception as e:
            logger.error(f"Risk calculation error: {e}")
            return 0.5  # Default moderate risk
    
    def _is_recent_event(self, event: Dict) -> bool:
        """Check if event occurred in the last 48 hours"""
        try:
            event_time_str = event.get('published', '')
            if not event_time_str:
                return False
                
            # Handle different time formats
            for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y%m%d%H%M%S', '%Y-%m-%dT%H:%M:%S.%f']:
                try:
                    event_time = datetime.strptime(event_time_str[:19], fmt[:19])
                    time_diff = datetime.utcnow() - event_time
                    return time_diff.total_seconds() < (48 * 3600)  # 48 hours
                except ValueError:
                    continue
                    
            return False
            
        except Exception:
            return False
    
    def _get_risk_level(self, risk_score: float) -> str:
        """Convert risk score to categorical level"""
        if risk_score < 0.2:
            return 'very_low'
        elif risk_score < 0.4:
            return 'low'
        elif risk_score < 0.6:
            return 'moderate'
        elif risk_score < 0.8:
            return 'high'
        else:
            return 'very_high'
    
    def _identify_primary_risks(self, events: List[Dict], sentiment_analysis: Dict) -> List[str]:
        """Identify the primary risk factors from events and analysis"""
        risks = []
        
        # From events
        event_types = [event.get('type') for event in events if event.get('type')]
        risk_counts = {}
        for event_type in event_types:
            risk_counts[event_type] = risk_counts.get(event_type, 0) + 1
        
        # Get top risk types
        for risk_type, count in sorted(risk_counts.items(), key=lambda x: x[1], reverse=True)[:3]:
            if count >= 2:  # At least 2 occurrences
                risks.append(risk_type.lower().replace('_', ' '))
        
        # From sentiment analysis factors
        factors = sentiment_analysis.get('factors', [])
        for factor in factors[:2]:  # Top 2 factors
            risk_name = factor.get('type', '').lower().replace('_', ' ')
            if risk_name not in risks:
                risks.append(risk_name)
        
        return risks[:4]  # Maximum 4 primary risks
    
    def _generate_risk_recommendations(self, risk_score: float, events: List[Dict]) -> List[str]:
        """Generate actionable recommendations based on risk assessment"""
        recommendations = []
        
        if risk_score > 0.7:
            recommendations.extend([
                "Consider alternative routing to avoid high-risk areas",
                "Increase security protocols and crew briefings",
                "Monitor situation closely with frequent updates",
                "Coordinate with naval authorities and shipping advisories"
            ])
        elif risk_score > 0.5:
            recommendations.extend([
                "Monitor situation and prepare contingency plans",
                "Maintain regular communication with local agents",
                "Review insurance coverage for the route"
            ])
        elif risk_score > 0.3:
            recommendations.extend([
                "Standard monitoring procedures sufficient",
                "Maintain awareness of regional developments"
            ])
        else:
            recommendations.append("No special precautions required")
        
        # Event-specific recommendations
        event_types = [event.get('type') for event in events]
        if 'CONFLICT' in event_types or 'VIOLENCE' in event_types:
            recommendations.append("Avoid ports and areas with active conflicts")
        if 'STRIKE' in event_types:
            recommendations.append("Prepare for potential port delays due to labor disputes")
        if 'PIRACY' in event_types or 'TERRORISM' in event_types:
            recommendations.append("Implement enhanced security measures")
        
        return list(set(recommendations))  # Remove duplicates
    
    def _generate_fallback_risk_assessment(self, location_name: str, country_code: str = None, error: str = None) -> Dict:
        """Generate fallback risk assessment when primary assessment fails"""
        import random
        
        # Base risk levels by region/country
        high_risk_countries = ['YE', 'SY', 'AF', 'SO', 'LY', 'IR', 'VE']
        medium_risk_countries = ['EG', 'TR', 'PK', 'BD', 'NG', 'KE']
        
        if country_code in high_risk_countries:
            base_risk = random.uniform(0.6, 0.8)
            risk_level = 'high'
        elif country_code in medium_risk_countries:
            base_risk = random.uniform(0.4, 0.6)
            risk_level = 'moderate'
        else:
            base_risk = random.uniform(0.2, 0.4)
            risk_level = 'low'
        
        # Known risk zones
        risk_zones = {
            'red sea': 0.8,
            'gulf of aden': 0.7,
            'strait of hormuz': 0.6,
            'south china sea': 0.5,
            'malacca': 0.4
        }
        
        location_lower = location_name.lower()
        for zone, zone_risk in risk_zones.items():
            if zone in location_lower:
                base_risk = max(base_risk, zone_risk)
                risk_level = self._get_risk_level(base_risk)
                break
        
        return {
            'location': location_name,
            'country_code': country_code,
            'coordinates': None,
            'risk_level': risk_level,
            'risk_score': round(base_risk, 2),
            'confidence': 0.6,  # Lower confidence for fallback
            'assessment_time': datetime.utcnow().isoformat(),
            'event_count': 0,
            'sentiment_score': 0.5,
            'country_risk': base_risk,
            'primary_risks': ['data_unavailable'],
            'recommendations': ['Limited data available - use enhanced monitoring'],
            'data_sources': ['fallback_profiles'],
            'fallback_mode': True,
            'error': error,
            'next_assessment': (datetime.utcnow() + timedelta(hours=12)).isoformat()
        }
    
    def monitor_sanctions(self) -> List[Dict]:
        """Monitor sanctions updates"""
        # In production, integrate with OFAC and other sanctions databases
        # For demo, return sample data
        
        return [
            {
                'entity': 'Example Corp',
                'type': 'company',
                'country': 'XX',
                'program': 'Sample Sanctions Program',
                'added_date': datetime.utcnow().isoformat(),
                'source': 'OFAC'
            }
        ]
    
    def _log_integration(self, action: str, status: str, details: Dict):
        """Log integration activity"""
        try:
            log = IntegrationLog(
                integration_type='geopolitical',
                action=action,
                status=status,
                details=json.dumps(details),
                timestamp=datetime.utcnow()
            )
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            logger.error(f"Failed to log integration: {str(e)}")
