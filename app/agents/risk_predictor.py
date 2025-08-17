"""
Risk Predictor Agent - Monitors global threats and predicts supply chain risks
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import json
import numpy as np
from dataclasses import dataclass
from enum import Enum
from functools import reduce

from app import db
from app.models import Alert, Shipment, Supplier, Recommendation, AuditLog
from app.integrations.weather_apis import WeatherIntegration
from app.integrations.geopolitical_apis import GeopoliticalIntegration
from app.integrations.maritime_apis import MaritimeIntegration
from app.agents.communicator import AgentCommunicator, MessageType, AgentMessage

logger = logging.getLogger(__name__)


class RiskType(Enum):
    WEATHER = "weather"
    GEOPOLITICAL = "geopolitical"
    SUPPLIER = "supplier"
    SUPPLIER_DISRUPTION = "supplier_disruption"
    PORT_CONGESTION = "port_congestion"
    OPERATIONAL = "operational"


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskScore:
    """Risk assessment result"""
    risk_type: RiskType
    severity: Severity
    probability: float  # 0.0 to 1.0
    confidence: float   # 0.0 to 1.0
    impact_radius_km: float
    affected_entities: List[Dict[str, Any]]
    data_sources: List[str]
    evidence: Dict[str, Any]
    location: Dict[str, float]  # lat, lon
    
    def overall_score(self) -> float:
        """Calculate overall risk score"""
        severity_weights = {
            Severity.LOW: 0.25,
            Severity.MEDIUM: 0.5,
            Severity.HIGH: 0.75,
            Severity.CRITICAL: 1.0
        }
        return severity_weights[self.severity] * self.probability * self.confidence


class RiskPredictorAgent:
    """Monitors global conditions and predicts supply chain risks"""
    
    def __init__(self, communicator: AgentCommunicator):
        self.communicator = communicator
        self.weather_api = WeatherIntegration()
        self.geopolitical_api = GeopoliticalIntegration()
        self.maritime_api = MaritimeIntegration()
        self.agent_name = "risk_predictor"
        
        # Risk thresholds
        self.SEVERITY_THRESHOLDS = {
            'weather': {
                'wind_speed_kmh': {
                    'low': 50,
                    'medium': 80,
                    'high': 120,
                    'critical': 150
                },
                'wave_height_m': {
                    'low': 2,
                    'medium': 4,
                    'high': 6,
                    'critical': 9
                },
                'precipitation_mm': {
                    'low': 25,
                    'medium': 50,
                    'high': 100,
                    'critical': 200
                }
            },
            'geopolitical': {
                'event_goldstein': {  # GDELT Goldstein scale
                    'low': -5,
                    'medium': -7,
                    'high': -9,
                    'critical': -10
                },
                'article_count': {
                    'low': 10,
                    'medium': 25,
                    'high': 50,
                    'critical': 100
                }
            }
        }
    
    def run_assessment_cycle(self):
        """Main assessment loop - should be called periodically"""
        try:
            logger.info("Starting risk assessment cycle")
            
            # Get active shipments and suppliers
            shipments = self._get_active_shipments()
            suppliers = self._get_monitored_suppliers()
            
            # Assess risks
            weather_risks = self._assess_weather_risks(shipments)
            geopolitical_risks = self._assess_geopolitical_risks(shipments, suppliers)
            port_risks = self._assess_port_congestion(shipments)
            supplier_risks = self._assess_supplier_risks(suppliers)
            
            # Combine all risks
            all_risks = weather_risks + geopolitical_risks + port_risks + supplier_risks
            
            # Generate alerts and save risk records for significant risks
            alerts_generated = 0
            risks_saved = 0
            for risk in all_risks:
                if risk.overall_score() > 0.5:  # Threshold for alert generation
                    alert = self._generate_alert(risk)
                    if alert:
                        alerts_generated += 1
                        self._send_risk_alert(alert, risk)
                
                # Save all risks above threshold to Risk table
                if risk.overall_score() > 0.3:  # Lower threshold for risk record creation
                    saved_risk = self._save_risk_record(risk)
                    if saved_risk:
                        risks_saved += 1
            
            logger.info(f"Risk assessment complete. Generated {alerts_generated} alerts and saved {risks_saved} risk records from {len(all_risks)} risks")
            
            # Send status update
            self.communicator.send_message(
                MessageType.STATUS_UPDATE,
                target_agent=None,  # Broadcast
                payload={
                    'agent': self.agent_name,
                    'risks_assessed': len(all_risks),
                    'alerts_generated': alerts_generated,
                    'risks_saved': risks_saved,
                    'timestamp': datetime.utcnow().isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Error in risk assessment cycle: {e}")
            self._log_error(str(e))
    
    def _assess_weather_risks(self, shipments: List[Shipment]) -> List[RiskScore]:
        """Assess weather-related risks for shipments"""
        risks = []
        
        for shipment in shipments:
            try:
                # Get route waypoints
                route_points = self._get_route_waypoints(shipment)
                
                for point in route_points:
                    # Fetch weather data
                    weather_data = self.weather_api.get_consolidated_forecast(
                        point['lat'], 
                        point['lon']
                    )
                    
                    if not weather_data:
                        continue
                    
                    # Analyze weather conditions
                    risk = self._analyze_weather_conditions(
                        weather_data, 
                        point,
                        shipment
                    )
                    
                    if risk and risk.overall_score() > 0.3:
                        risks.append(risk)
                        
            except Exception as e:
                logger.error(f"Error assessing weather risk for shipment {shipment.id}: {e}")
        
        return risks
    
    def _assess_geopolitical_risks(self, 
                                  shipments: List[Shipment], 
                                  suppliers: List[Supplier]) -> List[RiskScore]:
        """Assess geopolitical risks affecting shipments and suppliers"""
        risks = []
        
        # Get unique locations to monitor
        locations = self._extract_risk_locations(shipments, suppliers)
        
        for location in locations:
            try:
                # Query GDELT for events
                events = self.geopolitical_api.query_gdelt_events(
                    location,
                    timeframe=timedelta(days=7)
                )
                
                if not events:
                    continue
                
                # Analyze event severity
                risk = self._analyze_geopolitical_events(
                    events,
                    location,
                    shipments,
                    suppliers
                )
                
                if risk and risk.overall_score() > 0.4:
                    risks.append(risk)
                    
            except Exception as e:
                logger.error(f"Error assessing geopolitical risk for location {location}: {e}")
        
        return risks
    
    def _assess_port_congestion(self, shipments: List[Shipment]) -> List[RiskScore]:
        """Assess port congestion risks"""
        risks = []
        
        # Extract unique ports
        ports = self._extract_ports_from_shipments(shipments)
        
        for port in ports:
            try:
                # Get port conditions
                port_data = self.maritime_api.fetch_port_conditions(port['code'])
                
                if not port_data:
                    continue
                
                # Check for congestion indicators
                risk = self._analyze_port_congestion(
                    port_data,
                    port,
                    shipments
                )
                
                if risk and risk.overall_score() > 0.3:
                    risks.append(risk)
                    
            except Exception as e:
                logger.error(f"Error assessing port congestion for {port['code']}: {e}")
        
        return risks
    
    def _assess_supplier_risks(self, suppliers: List[Supplier]) -> List[RiskScore]:
        """Assess supplier-specific risks"""
        risks = []
        
        for supplier in suppliers:
            try:
                # Check supplier health indicators
                risk = self._analyze_supplier_health(supplier)
                
                if risk and risk.overall_score() > 0.4:
                    risks.append(risk)
                    
            except Exception as e:
                logger.error(f"Error assessing supplier risk for {supplier.name}: {e}")
        
        return risks
    
    def _analyze_weather_conditions(self, 
                                  weather_data: Dict,
                                  location: Dict,
                                  shipment: Shipment) -> Optional[RiskScore]:
        """Analyze weather data and calculate risk score"""
        
        # Extract key metrics
        wind_speed = weather_data.get('wind_speed_kmh', 0)
        wave_height = weather_data.get('wave_height_m', 0)
        precipitation = weather_data.get('precipitation_mm', 0)
        
        # Determine severity
        severity = self._calculate_weather_severity(
            wind_speed, 
            wave_height, 
            precipitation
        )
        
        if severity == Severity.LOW:
            return None  # Don't create risk for low severity
        
        # Calculate probability based on forecast confidence
        probability = weather_data.get('probability', 0.7)
        confidence = weather_data.get('confidence', 0.8)
        
        # Determine affected entities
        affected = [{
            'type': 'shipment',
            'id': shipment.id,
            'reference': shipment.reference,
            'eta_impact_hours': self._estimate_delay(severity, 'weather')
        }]
        
        return RiskScore(
            risk_type=RiskType.WEATHER,
            severity=severity,
            probability=probability,
            confidence=confidence,
            impact_radius_km=100.0,
            affected_entities=affected,
            data_sources=['NOAA', 'Open-Meteo'],
            evidence={
                'wind_speed_kmh': wind_speed,
                'wave_height_m': wave_height,
                'precipitation_mm': precipitation,
                'forecast_time': weather_data.get('forecast_time')
            },
            location=location
        )
    
    def _analyze_geopolitical_events(self,
                                   events: List[Dict],
                                   location: Dict,
                                   shipments: List[Shipment],
                                   suppliers: List[Supplier]) -> Optional[RiskScore]:
        """Analyze GDELT events and calculate risk score"""
        
        if not events:
            return None
        
        # Calculate aggregate metrics
        total_events = len(events)
        avg_goldstein = np.mean([e.get('goldstein_scale', 0) for e in events])
        negative_events = [e for e in events if e.get('goldstein_scale', 0) < -5]
        
        # Sentiment analysis
        sentiment_scores = [e.get('sentiment_score', 0) for e in events]
        avg_sentiment = np.mean(sentiment_scores) if sentiment_scores else 0
        
        # Determine severity
        severity = self._calculate_geopolitical_severity(
            avg_goldstein,
            len(negative_events),
            avg_sentiment
        )
        
        if severity == Severity.LOW:
            return None
        
        # Calculate probability based on event frequency and recency
        probability = min(0.9, len(negative_events) / 20)  # Cap at 0.9
        confidence = min(0.9, total_events / 50)  # More events = higher confidence
        
        # Find affected entities
        affected = []
        
        # Check shipments passing through the area
        for shipment in shipments:
            if self._shipment_near_location(shipment, location, radius_km=200):
                affected.append({
                    'type': 'shipment',
                    'id': shipment.id,
                    'reference': shipment.reference,
                    'eta_impact_hours': self._estimate_delay(severity, 'geopolitical')
                })
        
        # Check suppliers in the area
        for supplier in suppliers:
            if self._supplier_near_location(supplier, location, radius_km=100):
                affected.append({
                    'type': 'supplier',
                    'id': supplier.id,
                    'name': supplier.name,
                    'impact': 'potential_disruption'
                })
        
        if not affected:
            return None
        
        return RiskScore(
            risk_type=RiskType.GEOPOLITICAL,
            severity=severity,
            probability=probability,
            confidence=confidence,
            impact_radius_km=200.0,
            affected_entities=affected,
            data_sources=['GDELT'],
            evidence={
                'event_count': total_events,
                'negative_events': len(negative_events),
                'avg_goldstein': avg_goldstein,
                'avg_sentiment': avg_sentiment,
                'sample_events': events[:5]  # Include sample events
            },
            location=location
        )
    
    def _analyze_port_congestion(self,
                               port_data: Dict,
                               port: Dict,
                               shipments: List[Shipment]) -> Optional[RiskScore]:
        """Analyze port congestion data"""
        
        # Extract congestion metrics
        vessel_count = port_data.get('vessels_in_port', 0)
        avg_wait_time = port_data.get('avg_wait_hours', 0)
        berth_occupancy = port_data.get('berth_occupancy_pct', 0)
        
        # Determine severity
        if avg_wait_time > 48 or berth_occupancy > 95:
            severity = Severity.HIGH
        elif avg_wait_time > 24 or berth_occupancy > 85:
            severity = Severity.MEDIUM
        elif avg_wait_time > 12 or berth_occupancy > 75:
            severity = Severity.LOW
        else:
            return None
        
        # Probability based on current conditions
        probability = min(0.9, berth_occupancy / 100)
        confidence = 0.85  # Port data is generally reliable
        
        # Find affected shipments
        affected = []
        for shipment in shipments:
            if self._shipment_uses_port(shipment, port['code']):
                affected.append({
                    'type': 'shipment',
                    'id': shipment.id,
                    'reference': shipment.reference,
                    'eta_impact_hours': avg_wait_time
                })
        
        if not affected:
            return None
        
        return RiskScore(
            risk_type=RiskType.PORT_CONGESTION,
            severity=severity,
            probability=probability,
            confidence=confidence,
            impact_radius_km=50.0,
            affected_entities=affected,
            data_sources=['AIS', 'Port Authority'],
            evidence={
                'vessel_count': vessel_count,
                'avg_wait_hours': avg_wait_time,
                'berth_occupancy_pct': berth_occupancy,
                'port_code': port['code']
            },
            location={
                'lat': port['lat'],
                'lon': port['lon']
            }
        )
    
    def _analyze_supplier_health(self, supplier: Supplier) -> Optional[RiskScore]:
        """Analyze supplier health indicators"""
        
        # Check various risk factors
        risk_factors = []
        
        # Financial health (would integrate with real data)
        if supplier.reliability_score and supplier.reliability_score < 70:
            risk_factors.append('low_reliability')
        
        # Recent performance
        recent_delays = self._get_recent_supplier_delays(supplier)
        if recent_delays > 3:
            risk_factors.append('frequent_delays')
        
        # Inventory levels
        if supplier.current_inventory and supplier.min_inventory:
            if supplier.current_inventory < supplier.min_inventory * 1.2:
                risk_factors.append('low_inventory')
        
        if not risk_factors:
            return None
        
        # Determine severity based on risk factors
        if len(risk_factors) >= 3:
            severity = Severity.HIGH
        elif len(risk_factors) >= 2:
            severity = Severity.MEDIUM
        else:
            severity = Severity.LOW
        
        # Calculate probability
        probability = min(0.8, len(risk_factors) * 0.3)
        confidence = 0.7
        
        return RiskScore(
            risk_type=RiskType.SUPPLIER,
            severity=severity,
            probability=probability,
            confidence=confidence,
            impact_radius_km=0,  # Supplier-specific, no geographic radius
            affected_entities=[{
                'type': 'supplier',
                'id': supplier.id,
                'name': supplier.name,
                'risk_factors': risk_factors
            }],
            data_sources=['Internal'],
            evidence={
                'reliability_score': supplier.reliability_score,
                'recent_delays': recent_delays,
                'risk_factors': risk_factors
            },
            location={
                'lat': supplier.latitude or 0,
                'lon': supplier.longitude or 0
            }
        )
    
    def _generate_alert(self, risk: RiskScore) -> Optional[Alert]:
        """Generate alert from risk assessment"""
        try:
            # Create alert title and message
            title = self._generate_alert_title(risk)
            message = self._generate_alert_message(risk)
            
            # Create alert
            alert = Alert(
                title=title,
                message=message,
                severity=risk.severity.value,
                category=risk.risk_type.value,
                source="risk_predictor_agent",
                data=json.dumps({
                    'risk_score': risk.overall_score(),
                    'probability': risk.probability,
                    'confidence': risk.confidence,
                    'evidence': risk.evidence,
                    'location': risk.location
                }),
                status='open',
                latitude=risk.location.get('lat'),
                longitude=risk.location.get('lon')
            )
            
            db.session.add(alert)
            db.session.commit()
            
            # Link affected entities
            self._link_alert_entities(alert, risk.affected_entities)
            
            # Create recommendation
            recommendation = self._create_recommendation(alert, risk)
            
            # Log to audit trail
            audit = AuditLog(
                actor_type='agent',
                actor_id=self.agent_name,
                action='alert_created',
                object_type='alert',
                object_id=str(alert.id),
                details=json.dumps({
                    'risk_type': risk.risk_type.value,
                    'severity': risk.severity.value,
                    'affected_count': len(risk.affected_entities)
                })
            )
            db.session.add(audit)
            db.session.commit()
            
            return alert
            
        except Exception as e:
            logger.error(f"Error generating alert: {e}")
            db.session.rollback()
            return None
    
    def _save_risk_record(self, risk: RiskScore) -> Optional['Risk']:
        """Save risk assessment to Risk table for formal tracking"""
        try:
            from app.models import Risk
            
            # Generate title and description
            title = self._generate_risk_title(risk)
            description = self._generate_risk_description(risk)
            
            # Create risk record
            risk_record = Risk(
                workspace_id=1,  # Default workspace
                title=title,
                description=description,
                risk_type=risk.risk_type.value,
                risk_score=risk.overall_score(),
                severity=risk.severity.value,
                probability=risk.probability,
                confidence=risk.confidence,
                affected_entities=risk.affected_entities,
                impact_assessment={
                    'estimated_delay_hours': self._estimate_enhanced_delay(risk.severity, risk.risk_type.value),
                    'impact_radius_km': risk.impact_radius_km,
                    'affected_count': len(risk.affected_entities),
                    'economic_impact': self._estimate_economic_impact(risk)
                },
                mitigation_strategies=self._generate_mitigation_strategies(risk),
                data_sources=risk.data_sources,
                raw_data=risk.evidence,
                analysis_metadata={
                    'analysis_version': '2.0',
                    'algorithm': 'enhanced_multi_factor',
                    'confidence_intervals': risk.confidence,
                    'external_apis_used': risk.data_sources
                },
                location=risk.location,
                geographic_scope=self._determine_geographic_scope(risk),
                time_horizon=self._determine_time_horizon(risk),
                estimated_duration=self._estimate_enhanced_delay(risk.severity, risk.risk_type.value),
                status='identified',
                created_by_agent=self.agent_name,
                analysis_version='2.0'
            )
            
            db.session.add(risk_record)
            db.session.commit()
            
            logger.info(f"Risk record saved: {title} (Score: {risk.overall_score():.3f})")
            return risk_record
            
        except Exception as e:
            logger.error(f"Error saving risk record: {e}")
            db.session.rollback()
            return None
    
    def _send_risk_alert(self, alert: Alert, risk: RiskScore):
        """Send risk alert to other agents"""
        try:
            # Send to orchestrator
            self.communicator.send_message(
                MessageType.RISK_ALERT,
                target_agent="orchestrator",
                payload={
                    'alert_id': alert.id,
                    'risk_type': risk.risk_type.value,
                    'severity': risk.severity.value,
                    'probability': risk.probability,
                    'confidence': risk.confidence,
                    'affected_entities': risk.affected_entities,
                    'location': risk.location,
                    'evidence': risk.evidence,
                    'recommended_actions': self._get_recommended_actions(risk)
                },
                metadata={
                    'priority': 'high' if risk.severity in [Severity.HIGH, Severity.CRITICAL] else 'normal',
                    'ttl': 3600  # Alert valid for 1 hour
                }
            )
            
            # Also send to route optimizer if shipments affected
            shipment_affected = any(e['type'] == 'shipment' for e in risk.affected_entities)
            if shipment_affected and risk.risk_type in [RiskType.WEATHER, RiskType.GEOPOLITICAL]:
                self.communicator.send_message(
                    MessageType.RISK_ALERT,
                    target_agent="route_optimizer",
                    payload={
                        'alert_id': alert.id,
                        'risk_type': risk.risk_type.value,
                        'affected_shipments': [
                            e for e in risk.affected_entities if e['type'] == 'shipment'
                        ],
                        'location': risk.location,
                        'impact_radius_km': risk.impact_radius_km
                    }
                )
            
        except Exception as e:
            logger.error(f"Error sending risk alert: {e}")
    
    # Helper methods
    
    def _get_active_shipments(self) -> List[Shipment]:
        """Get shipments that need monitoring"""
        return Shipment.query.filter(
            Shipment.status.in_(['pending', 'in_transit', 'delayed'])
        ).all()
    
    def _get_monitored_suppliers(self) -> List[Supplier]:
        """Get suppliers to monitor"""
        return Supplier.query.filter(
            Supplier.is_active == True
        ).all()
    
    def _get_route_waypoints(self, shipment: Shipment) -> List[Dict[str, float]]:
        """Extract waypoints from shipment route"""
        waypoints = []
        
        # Add origin
        if shipment.origin_lat and shipment.origin_lon:
            waypoints.append({
                'lat': shipment.origin_lat,
                'lon': shipment.origin_lon,
                'type': 'origin'
            })
        
        # Add current location if available (fallback to origin if current not available)
        current_lat = getattr(shipment, 'current_latitude', None) or getattr(shipment, 'origin_lat', None)
        current_lon = getattr(shipment, 'current_longitude', None) or getattr(shipment, 'origin_lon', None)
        
        if current_lat and current_lon:
            waypoints.append({
                'lat': current_lat,
                'lon': current_lon,
                'type': 'current'
            })
        
        # Add destination
        if shipment.destination_lat and shipment.destination_lon:
            waypoints.append({
                'lat': shipment.destination_lat,
                'lon': shipment.destination_lon,
                'type': 'destination'
            })
        
        # TODO: Add intermediate waypoints from route
        
        return waypoints
    
    def _extract_risk_locations(self, 
                              shipments: List[Shipment], 
                              suppliers: List[Supplier]) -> List[Dict]:
        """Extract unique locations to monitor"""
        locations = []
        seen = set()
        
        # From shipments
        for shipment in shipments:
            # Check route corridors
            if shipment.origin_lat and shipment.origin_lon:
                key = f"{shipment.origin_lat},{shipment.origin_lon}"
                if key not in seen:
                    seen.add(key)
                    locations.append({
                        'lat': shipment.origin_lat,
                        'lon': shipment.origin_lon,
                        'name': shipment.origin_address or 'Origin',
                        'type': 'port'
                    })
        
        # From suppliers
        for supplier in suppliers:
            if supplier.latitude and supplier.longitude:
                key = f"{supplier.latitude},{supplier.longitude}"
                if key not in seen:
                    seen.add(key)
                    locations.append({
                        'lat': supplier.latitude,
                        'lon': supplier.longitude,
                        'name': supplier.city or supplier.name,
                        'type': 'supplier'
                    })
        
        return locations
    
    def _extract_ports_from_shipments(self, shipments: List[Shipment]) -> List[Dict]:
        """Extract unique ports from shipments"""
        ports = {}
        
        for shipment in shipments:
            # Origin port
            if shipment.origin_port:
                if shipment.origin_port not in ports:
                    ports[shipment.origin_port] = {
                        'code': shipment.origin_port,
                        'lat': shipment.origin_lat,
                        'lon': shipment.origin_lon,
                        'name': shipment.origin_address
                    }
            
            # Destination port
            if shipment.destination_port:
                if shipment.destination_port not in ports:
                    ports[shipment.destination_port] = {
                        'code': shipment.destination_port,
                        'lat': shipment.destination_lat,
                        'lon': shipment.destination_lon,
                        'name': shipment.destination_address
                    }
        
        return list(ports.values())
    
    def _calculate_weather_severity(self, 
                                  wind_speed: float,
                                  wave_height: float,
                                  precipitation: float) -> Severity:
        """Calculate weather severity based on thresholds"""
        
        thresholds = self.SEVERITY_THRESHOLDS['weather']
        
        # Check each metric against thresholds
        severities = []
        
        # Wind
        if wind_speed >= thresholds['wind_speed_kmh']['critical']:
            severities.append(Severity.CRITICAL)
        elif wind_speed >= thresholds['wind_speed_kmh']['high']:
            severities.append(Severity.HIGH)
        elif wind_speed >= thresholds['wind_speed_kmh']['medium']:
            severities.append(Severity.MEDIUM)
        elif wind_speed >= thresholds['wind_speed_kmh']['low']:
            severities.append(Severity.LOW)
        
        # Waves
        if wave_height >= thresholds['wave_height_m']['critical']:
            severities.append(Severity.CRITICAL)
        elif wave_height >= thresholds['wave_height_m']['high']:
            severities.append(Severity.HIGH)
        elif wave_height >= thresholds['wave_height_m']['medium']:
            severities.append(Severity.MEDIUM)
        elif wave_height >= thresholds['wave_height_m']['low']:
            severities.append(Severity.LOW)
        
        # Precipitation
        if precipitation >= thresholds['precipitation_mm']['critical']:
            severities.append(Severity.CRITICAL)
        elif precipitation >= thresholds['precipitation_mm']['high']:
            severities.append(Severity.HIGH)
        elif precipitation >= thresholds['precipitation_mm']['medium']:
            severities.append(Severity.MEDIUM)
        elif precipitation >= thresholds['precipitation_mm']['low']:
            severities.append(Severity.LOW)
        
        # Return highest severity
        if not severities:
            return Severity.LOW
        
        severity_order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        return max(severities, key=lambda x: severity_order.index(x))
    
    def _calculate_geopolitical_severity(self,
                                       avg_goldstein: float,
                                       negative_event_count: int,
                                       avg_sentiment: float) -> Severity:
        """Calculate geopolitical risk severity"""
        
        thresholds = self.SEVERITY_THRESHOLDS['geopolitical']
        
        # Check Goldstein scale (more negative = worse)
        if avg_goldstein <= thresholds['event_goldstein']['critical']:
            return Severity.CRITICAL
        elif avg_goldstein <= thresholds['event_goldstein']['high']:
            return Severity.HIGH
        elif avg_goldstein <= thresholds['event_goldstein']['medium']:
            return Severity.MEDIUM
        elif avg_goldstein <= thresholds['event_goldstein']['low']:
            return Severity.LOW
        
        # Also consider event volume
        if negative_event_count >= thresholds['article_count']['critical']:
            return Severity.HIGH
        elif negative_event_count >= thresholds['article_count']['high']:
            return Severity.MEDIUM
        
        return Severity.LOW
    
    def _estimate_delay(self, severity: Severity, risk_type: str) -> float:
        """Estimate potential delay in hours based on risk"""
        
        delay_estimates = {
            RiskType.WEATHER.value: {
                Severity.LOW: 4,
                Severity.MEDIUM: 12,
                Severity.HIGH: 24,
                Severity.CRITICAL: 48
            },
            RiskType.GEOPOLITICAL.value: {
                Severity.LOW: 8,
                Severity.MEDIUM: 24,
                Severity.HIGH: 72,
                Severity.CRITICAL: 168  # 1 week
            },
            RiskType.PORT_CONGESTION.value: {
                Severity.LOW: 6,
                Severity.MEDIUM: 18,
                Severity.HIGH: 36,
                Severity.CRITICAL: 72
            }
        }
        
        return delay_estimates.get(risk_type, {}).get(severity, 12)
    
    def _shipment_near_location(self, 
                              shipment: Shipment,
                              location: Dict,
                              radius_km: float) -> bool:
        """Check if shipment route passes near location"""
        # Simplified - just check origin/destination
        # TODO: Implement proper route corridor check
        
        points = []
        if shipment.origin_lat and shipment.origin_lon:
            points.append((shipment.origin_lat, shipment.origin_lon))
        if shipment.destination_lat and shipment.destination_lon:
            points.append((shipment.destination_lat, shipment.destination_lon))
        
        for lat, lon in points:
            distance = self._haversine_distance(
                lat, lon,
                location['lat'], location['lon']
            )
            if distance <= radius_km:
                return True
        
        return False
    
    def _supplier_near_location(self,
                              supplier: Supplier,
                              location: Dict,
                              radius_km: float) -> bool:
        """Check if supplier is near location"""
        if not (supplier.latitude and supplier.longitude):
            return False
        
        distance = self._haversine_distance(
            supplier.latitude, supplier.longitude,
            location['lat'], location['lon']
        )
        return distance <= radius_km
    
    def _shipment_uses_port(self, shipment: Shipment, port_code: str) -> bool:
        """Check if shipment uses specific port"""
        return (shipment.origin_port == port_code or 
                shipment.destination_port == port_code)
    
    def _get_recent_supplier_delays(self, supplier: Supplier) -> int:
        """Get count of recent delays from supplier"""
        # TODO: Implement based on shipment history
        return 0
    
    def _haversine_distance(self, lat1: float, lon1: float, 
                          lat2: float, lon2: float) -> float:
        """Calculate distance between two points in kilometers"""
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Earth's radius in kilometers
        
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lat2 - lon1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return R * c
    
    def _generate_alert_title(self, risk: RiskScore) -> str:
        """Generate alert title based on risk"""
        templates = {
            RiskType.WEATHER: "{severity} weather risk: {location}",
            RiskType.GEOPOLITICAL: "{severity} geopolitical risk: {location}",
            RiskType.PORT_CONGESTION: "Port congestion alert: {location}",
            RiskType.SUPPLIER: "Supplier risk alert: {supplier}",
            RiskType.OPERATIONAL: "Operational risk detected: {location}"
        }
        
        template = templates.get(risk.risk_type, "Risk alert: {location}")
        
        # Get location name or supplier name
        if risk.risk_type == RiskType.SUPPLIER and risk.affected_entities:
            supplier_name = risk.affected_entities[0].get('name', 'Unknown')
            return template.format(severity=risk.severity.value.title(), supplier=supplier_name)
        else:
            location_name = risk.evidence.get('location_name', 
                          f"{risk.location['lat']:.2f}, {risk.location['lon']:.2f}")
            return template.format(severity=risk.severity.value.title(), location=location_name)
    
    def _generate_alert_message(self, risk: RiskScore) -> str:
        """Generate detailed alert message"""
        affected_summary = f"{len(risk.affected_entities)} entities affected"
        
        if risk.risk_type == RiskType.WEATHER:
            evidence = risk.evidence
            return (f"Severe weather conditions detected. "
                   f"Wind: {evidence.get('wind_speed_kmh', 0):.0f} km/h, "
                   f"Waves: {evidence.get('wave_height_m', 0):.1f}m. "
                   f"{affected_summary}.")
        
        elif risk.risk_type == RiskType.GEOPOLITICAL:
            evidence = risk.evidence
            return (f"Elevated geopolitical risk detected. "
                   f"{evidence.get('negative_events', 0)} concerning events identified. "
                   f"Goldstein scale: {evidence.get('avg_goldstein', 0):.1f}. "
                   f"{affected_summary}.")
        
        elif risk.risk_type == RiskType.PORT_CONGESTION:
            evidence = risk.evidence
            return (f"Port congestion detected at {evidence.get('port_code', 'Unknown')}. "
                   f"Average wait time: {evidence.get('avg_wait_hours', 0):.0f} hours. "
                   f"Berth occupancy: {evidence.get('berth_occupancy_pct', 0):.0f}%. "
                   f"{affected_summary}.")
        
        elif risk.risk_type == RiskType.SUPPLIER:
            factors = risk.evidence.get('risk_factors', [])
            return (f"Supplier health concerns identified. "
                   f"Risk factors: {', '.join(factors)}. "
                   f"Reliability score: {risk.evidence.get('reliability_score', 'N/A')}.")
        
        else:
            return f"Risk detected with {risk.probability:.0%} probability. {affected_summary}."
    
    def _link_alert_entities(self, alert: Alert, affected_entities: List[Dict]):
        """Link alert to affected shipments and suppliers"""
        try:
            for entity in affected_entities:
                if entity['type'] == 'shipment':
                    shipment = db.session.get(Shipment, entity['id'])
                    if shipment:
                        alert.shipments.append(shipment)
                
                elif entity['type'] == 'supplier':
                    supplier = db.session.get(Supplier, entity['id'])
                    if supplier:
                        alert.suppliers.append(supplier)
            
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Error linking alert entities: {e}")
            db.session.rollback()
    
    def _create_recommendation(self, alert: Alert, risk: RiskScore) -> Optional[Recommendation]:
        """Create recommendation based on risk assessment"""
        try:
            actions = self._get_recommended_actions(risk)
            
            recommendation = Recommendation(
                type='risk_mitigation',
                subject_type='alert',
                subject_id=alert.id,
                severity=risk.severity.value,
                confidence=risk.confidence,
                recommendation=json.dumps(actions),
                rationale=self._generate_rationale(risk),
                input_data=json.dumps({
                    'risk_type': risk.risk_type.value,
                    'evidence': risk.evidence,
                    'affected_entities': risk.affected_entities
                }),
                xai_explanation=json.dumps(self._generate_xai_explanation(risk)),
                status='pending',
                created_by=self.agent_name
            )
            
            db.session.add(recommendation)
            db.session.commit()
            
            return recommendation
            
        except Exception as e:
            logger.error(f"Error creating recommendation: {e}")
            db.session.rollback()
            return None
    
    def _get_recommended_actions(self, risk: RiskScore) -> List[Dict[str, Any]]:
        """Generate recommended actions based on risk type and severity"""
        actions = []
        
        if risk.risk_type == RiskType.WEATHER:
            if risk.severity in [Severity.HIGH, Severity.CRITICAL]:
                actions.append({
                    'action': 'reroute_shipments',
                    'urgency': 'immediate',
                    'description': 'Reroute affected shipments to avoid weather system'
                })
                actions.append({
                    'action': 'notify_carriers',
                    'urgency': 'immediate',
                    'description': 'Alert carriers about severe weather conditions'
                })
            else:
                actions.append({
                    'action': 'monitor_conditions',
                    'urgency': 'normal',
                    'description': 'Continue monitoring weather development'
                })
        
        elif risk.risk_type == RiskType.GEOPOLITICAL:
            if risk.severity in [Severity.HIGH, Severity.CRITICAL]:
                actions.append({
                    'action': 'reroute_shipments',
                    'urgency': 'high',
                    'description': 'Find alternative routes avoiding conflict zone'
                })
                actions.append({
                    'action': 'assess_supplier_alternatives',
                    'urgency': 'high',
                    'description': 'Identify backup suppliers outside affected region'
                })
            actions.append({
                'action': 'increase_monitoring',
                'urgency': 'normal',
                'description': 'Increase monitoring frequency for the region'
            })
        
        elif risk.risk_type == RiskType.PORT_CONGESTION:
            actions.append({
                'action': 'adjust_schedules',
                'urgency': 'normal',
                'description': 'Update ETAs based on port delays'
            })
            if risk.severity in [Severity.HIGH, Severity.CRITICAL]:
                actions.append({
                    'action': 'consider_alternative_ports',
                    'urgency': 'high',
                    'description': 'Evaluate routing through alternative ports'
                })
        
        elif risk.risk_type == RiskType.SUPPLIER:
            actions.append({
                'action': 'increase_safety_stock',
                'urgency': 'high',
                'description': 'Increase inventory buffers for affected items'
            })
            actions.append({
                'action': 'diversify_suppliers',
                'urgency': 'normal',
                'description': 'Identify and qualify alternative suppliers'
            })
        
        return actions
    
    def _generate_rationale(self, risk: RiskScore) -> str:
        """Generate human-readable rationale for the risk assessment"""
        rationale_parts = []
        
        # Severity rationale
        rationale_parts.append(
            f"Risk severity assessed as {risk.severity.value} based on "
            f"{', '.join(risk.data_sources)} data sources."
        )
        
        # Probability rationale
        rationale_parts.append(
            f"Probability of impact is {risk.probability:.0%} with "
            f"{risk.confidence:.0%} confidence."
        )
        
        # Impact rationale
        if risk.affected_entities:
            entity_types = {}
            for entity in risk.affected_entities:
                entity_type = entity['type']
                entity_types[entity_type] = entity_types.get(entity_type, 0) + 1
            
            impact_parts = []
            for entity_type, count in entity_types.items():
                impact_parts.append(f"{count} {entity_type}(s)")
            
            rationale_parts.append(
                f"This risk affects {', '.join(impact_parts)}."
            )
        
        return " ".join(rationale_parts)
    
    def _generate_risk_title(self, risk: RiskScore) -> str:
        """Generate risk title for database record"""
        risk_type_names = {
            RiskType.WEATHER: "Weather",
            RiskType.GEOPOLITICAL: "Geopolitical", 
            RiskType.PORT_CONGESTION: "Port Congestion",
            RiskType.SUPPLIER: "Supplier"
        }
        
        severity_prefix = {
            Severity.CRITICAL: "Critical",
            Severity.HIGH: "High", 
            Severity.MEDIUM: "Medium",
            Severity.LOW: "Low"
        }
        
        base_name = risk_type_names.get(risk.risk_type, risk.risk_type.value.title())
        severity = severity_prefix.get(risk.severity, risk.severity.value.title())
        
        # Add location context if available
        location_context = ""
        if risk.location and 'name' in risk.location:
            location_context = f" in {risk.location['name']}"
        elif risk.location and 'region' in risk.location:
            location_context = f" in {risk.location['region']}"
        
        return f"{severity} {base_name} Risk{location_context}"
    
    def _generate_risk_description(self, risk: RiskScore) -> str:
        """Generate detailed risk description"""
        rationale = self._generate_rationale(risk)
        
        # Add specific details based on risk type
        details = []
        
        if risk.risk_type == RiskType.WEATHER:
            if 'wind_speed_kmh' in risk.evidence:
                details.append(f"Wind speed: {risk.evidence['wind_speed_kmh']} km/h")
            if 'wave_height_m' in risk.evidence:
                details.append(f"Wave height: {risk.evidence['wave_height_m']} m")
            if 'precipitation_mm' in risk.evidence:
                details.append(f"Precipitation: {risk.evidence['precipitation_mm']} mm")
                
        elif risk.risk_type == RiskType.GEOPOLITICAL:
            if 'event_count' in risk.evidence:
                details.append(f"Events detected: {risk.evidence['event_count']}")
            if 'conflict_intensity' in risk.evidence:
                details.append(f"Conflict intensity: {risk.evidence['conflict_intensity']}")
                
        elif risk.risk_type == RiskType.PORT_CONGESTION:
            if 'congestion_level' in risk.evidence:
                details.append(f"Congestion level: {risk.evidence['congestion_level']}/10")
            if 'waiting_vessels' in risk.evidence:
                details.append(f"Vessels waiting: {risk.evidence['waiting_vessels']}")
                
        elif risk.risk_type == RiskType.SUPPLIER:
            if 'reliability_score' in risk.evidence:
                details.append(f"Reliability score: {risk.evidence['reliability_score']}")
            if 'recent_delays' in risk.evidence:
                details.append(f"Recent delays: {risk.evidence['recent_delays']}")
        
        description = rationale
        if details:
            description += f" Details: {', '.join(details)}."
            
        return description
    
    def _estimate_economic_impact(self, risk: RiskScore) -> Dict:
        """Estimate economic impact of the risk"""
        base_impact = {
            Severity.CRITICAL: 100000,
            Severity.HIGH: 50000,
            Severity.MEDIUM: 25000,
            Severity.LOW: 10000
        }
        
        base_cost = base_impact.get(risk.severity, 25000)
        affected_multiplier = len(risk.affected_entities)
        probability_factor = risk.probability
        
        estimated_cost = base_cost * affected_multiplier * probability_factor
        
        return {
            'estimated_cost_usd': round(estimated_cost, 2),
            'confidence': risk.confidence,
            'calculation_basis': 'severity_affected_probability',
            'affected_entities': len(risk.affected_entities)
        }
    
    def _generate_mitigation_strategies(self, risk: RiskScore) -> List[Dict]:
        """Generate mitigation strategies based on risk type"""
        strategies = []
        
        if risk.risk_type == RiskType.WEATHER:
            strategies = [
                {
                    'strategy': 'route_adjustment',
                    'description': 'Adjust route to avoid severe weather conditions',
                    'priority': 'high',
                    'estimated_time_hours': 2
                },
                {
                    'strategy': 'delay_shipment', 
                    'description': 'Delay shipment until weather conditions improve',
                    'priority': 'medium',
                    'estimated_time_hours': 24
                }
            ]
            
        elif risk.risk_type == RiskType.GEOPOLITICAL:
            strategies = [
                {
                    'strategy': 'alternative_route',
                    'description': 'Use alternative route avoiding conflict zones',
                    'priority': 'critical',
                    'estimated_time_hours': 4
                },
                {
                    'strategy': 'enhanced_security',
                    'description': 'Increase security measures for shipment',
                    'priority': 'high', 
                    'estimated_time_hours': 8
                }
            ]
            
        elif risk.risk_type == RiskType.PORT_CONGESTION:
            strategies = [
                {
                    'strategy': 'alternative_port',
                    'description': 'Reroute to alternative port with lower congestion',
                    'priority': 'high',
                    'estimated_time_hours': 6
                },
                {
                    'strategy': 'schedule_adjustment',
                    'description': 'Adjust arrival time to avoid peak congestion',
                    'priority': 'medium',
                    'estimated_time_hours': 12
                }
            ]
            
        elif risk.risk_type == RiskType.SUPPLIER:
            strategies = [
                {
                    'strategy': 'alternative_supplier',
                    'description': 'Source from backup supplier with better reliability',
                    'priority': 'high',
                    'estimated_time_hours': 72
                },
                {
                    'strategy': 'inventory_buffer',
                    'description': 'Increase safety stock to compensate for supplier risk',
                    'priority': 'medium',
                    'estimated_time_hours': 48
                }
            ]
        
        return strategies
    
    def _determine_geographic_scope(self, risk: RiskScore) -> str:
        """Determine geographic scope of the risk"""
        if risk.impact_radius_km > 1000:
            return 'global'
        elif risk.impact_radius_km > 500:
            return 'national'
        elif risk.impact_radius_km > 100:
            return 'regional'
        else:
            return 'local'
    
    def _determine_time_horizon(self, risk: RiskScore) -> str:
        """Determine time horizon of the risk impact"""
        delay_hours = self._estimate_enhanced_delay(risk.severity, risk.risk_type.value)
        
        if delay_hours <= 24:
            return 'immediate'
        elif delay_hours <= 168:  # 1 week
            return 'short_term'
        elif delay_hours <= 720:  # 1 month
            return 'medium_term'
        else:
            return 'long_term'
    
    def _generate_xai_explanation(self, risk: RiskScore) -> Dict[str, Any]:
        """Generate explainable AI explanation for the risk assessment"""
        explanation = {
            'model': 'rule_based_risk_assessment_v1',
            'features_used': [],
            'decision_path': [],
            'counterfactuals': []
        }
        
        # Features used
        if risk.risk_type == RiskType.WEATHER:
            explanation['features_used'] = [
                'wind_speed_kmh',
                'wave_height_m',
                'precipitation_mm',
                'forecast_confidence'
            ]
            
            # Decision path
            explanation['decision_path'] = [
                f"Wind speed ({risk.evidence.get('wind_speed_kmh', 0):.0f} km/h) "
                f"exceeds {self.SEVERITY_THRESHOLDS['weather']['wind_speed_kmh'][risk.severity.value]} km/h threshold",
                f"Severity determined as {risk.severity.value}",
                f"Probability calculated from forecast model confidence"
            ]
            
            # Counterfactuals
            explanation['counterfactuals'] = [
                {
                    'condition': 'If wind speed < 50 km/h',
                    'outcome': 'Risk would be downgraded to LOW'
                }
            ]
        
        elif risk.risk_type == RiskType.GEOPOLITICAL:
            explanation['features_used'] = [
                'goldstein_scale',
                'event_count',
                'sentiment_score',
                'event_recency'
            ]
            
            explanation['decision_path'] = [
                f"Average Goldstein scale ({risk.evidence.get('avg_goldstein', 0):.1f}) "
                f"indicates negative events",
                f"{risk.evidence.get('negative_events', 0)} concerning events detected",
                f"Severity assessed as {risk.severity.value}"
            ]
            
            explanation['counterfactuals'] = [
                {
                    'condition': 'If Goldstein scale > -5',
                    'outcome': 'Risk would be downgraded'
                }
            ]
        
        return explanation
    
    def assess_risks(self, shipments=None, suppliers=None):
        """Comprehensive risk assessment across all categories with enhanced external data"""
        try:
            risks = []
            
            # Get default entities if not provided
            if not shipments:
                shipments = self._get_active_shipments()
            if not suppliers:
                suppliers = self._get_monitored_suppliers()
                
            # Weather risks with enhanced data
            weather_risks = self._assess_weather_risks(shipments)
            risks.extend(weather_risks)
            
            # Geopolitical risks with GDELT integration
            geopolitical_risks = self._assess_geopolitical_risks(shipments, suppliers)
            risks.extend(geopolitical_risks)
            
            # Maritime risks with port data
            maritime_risks = self._assess_port_congestion(shipments)
            risks.extend(maritime_risks)
            
            # Supplier risks with financial data
            supplier_risks = self._assess_supplier_risks(suppliers)
            risks.extend(supplier_risks)
            
            # Generate alerts for high-priority risks
            alerts = []
            for risk in risks:
                if risk.overall_score() > 0.5:  # High risk threshold
                    alert = self._generate_alert(risk)
                    if alert:
                        alerts.append(alert)
                        self._send_risk_alert(alert, risk)
            
            logger.info(f"Enhanced risk assessment completed: {len(risks)} risks identified, {len(alerts)} alerts generated")
            
            return {
                'risks': risks,
                'alerts': alerts,
                'summary': self._generate_risk_summary(risks)
            }
            
        except Exception as e:
            logger.error(f"Enhanced risk assessment failed: {e}")
            return {'risks': [], 'alerts': [], 'summary': {}}
    
    def _extract_risk_locations(self, shipments, suppliers):
        """Extract unique locations for enhanced risk monitoring"""
        try:
            locations = []
            
            # Add shipment locations
            for shipment in shipments:
                if hasattr(shipment, 'origin_lat') and shipment.origin_lat:
                    locations.append({
                        'lat': shipment.origin_lat,
                        'lon': shipment.origin_lon,
                        'name': f"Origin: {shipment.origin_address or 'Unknown'}",
                        'type': 'shipment_origin'
                    })
                
                if hasattr(shipment, 'destination_lat') and shipment.destination_lat:
                    dest_country = getattr(shipment, 'destination_country', None) or getattr(shipment, 'destination', 'Unknown')
                    locations.append({
                        'lat': shipment.destination_lat,
                        'lon': shipment.destination_lon,
                        'name': f"Destination: {dest_country}",
                        'type': 'shipment_destination'
                    })
            
            # Add supplier locations
            for supplier in suppliers:
                if hasattr(supplier, 'location') and supplier.location:
                    try:
                        import json
                        if isinstance(supplier.location, str):
                            location_data = json.loads(supplier.location)
                        else:
                            location_data = supplier.location
                        
                        if 'lat' in location_data and 'lon' in location_data:
                            locations.append({
                                'lat': location_data['lat'],
                                'lon': location_data['lon'],
                                'name': f"Supplier: {supplier.name}",
                                'type': 'supplier'
                            })
                    except Exception:
                        continue
            
            # Remove duplicates (within 50km)
            unique_locations = []
            for loc in locations:
                is_duplicate = False
                for unique_loc in unique_locations:
                    distance = self._calculate_distance(
                        loc['lat'], loc['lon'],
                        unique_loc['lat'], unique_loc['lon']
                    )
                    if distance < 50:  # 50km threshold
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    unique_locations.append(loc)
            
            return unique_locations
            
        except Exception as e:
            logger.error(f"Error extracting enhanced risk locations: {e}")
            return []
    
    def _analyze_enhanced_weather_conditions(self, weather_data, location, shipment):
        """Enhanced weather analysis with better algorithms"""
        try:
            # Extract enhanced metrics
            wind_speed = weather_data.get('wind_speed_kmh', 0)
            wave_height = weather_data.get('wave_height_m', 0) 
            precipitation = weather_data.get('precipitation_mm', 0)
            visibility = weather_data.get('visibility_km', 10)
            temperature = weather_data.get('temperature_c', 20)
            
            # Enhanced severity calculation
            severity = self._calculate_enhanced_weather_severity(
                wind_speed, wave_height, precipitation, visibility, temperature
            )
            
            if severity == Severity.LOW:
                return None
                
            # Enhanced probability calculation
            probability = min(0.95, weather_data.get('probability', 0.7) * 1.2)
            confidence = weather_data.get('confidence', 0.8)
            
            # Determine affected entities with impact estimation
            affected = [{
                'type': 'shipment',
                'id': shipment.id,
                'reference': shipment.reference_number if hasattr(shipment, 'reference_number') else f'SHIP-{shipment.id}',
                'eta_impact_hours': self._estimate_enhanced_delay(severity, 'weather'),
                'risk_factors': self._identify_weather_risk_factors(weather_data)
            }]
            
            return RiskScore(
                risk_type=RiskType.WEATHER,
                severity=severity,
                probability=probability,
                confidence=confidence,
                impact_radius_km=75.0,
                affected_entities=affected,
                data_sources=['NOAA', 'Open-Meteo', 'AccuWeather'],
                evidence={
                    'wind_speed_kmh': wind_speed,
                    'wave_height_m': wave_height,
                    'precipitation_mm': precipitation,
                    'visibility_km': visibility,
                    'temperature_c': temperature,
                    'forecast_time': weather_data.get('forecast_time'),
                    'enhanced_analysis': True
                },
                location=location
            )
            
        except Exception as e:
            logger.error(f"Enhanced weather analysis error: {e}")
            return None
    
    def _calculate_enhanced_weather_severity(self, wind_speed, wave_height, precipitation, visibility, temperature):
        """Enhanced weather severity calculation with multiple factors"""
        # Multiple factor scoring
        wind_score = 0
        if wind_speed >= 150: wind_score = 4
        elif wind_speed >= 120: wind_score = 3
        elif wind_speed >= 80: wind_score = 2
        elif wind_speed >= 50: wind_score = 1
        
        wave_score = 0
        if wave_height >= 9: wave_score = 4
        elif wave_height >= 6: wave_score = 3
        elif wave_height >= 4: wave_score = 2
        elif wave_height >= 2: wave_score = 1
        
        visibility_score = 0
        if visibility <= 0.5: visibility_score = 4
        elif visibility <= 1: visibility_score = 3
        elif visibility <= 2: visibility_score = 2
        elif visibility <= 5: visibility_score = 1
        
        # Combined severity
        max_score = max(wind_score, wave_score, visibility_score)
        
        if max_score >= 4: return Severity.CRITICAL
        elif max_score >= 3: return Severity.HIGH
        elif max_score >= 2: return Severity.MEDIUM
        else: return Severity.LOW
    
    def _estimate_enhanced_delay(self, severity, risk_type):
        """Estimate delay based on enhanced severity analysis"""
        base_delays = {
            'weather': {'low': 2, 'medium': 8, 'high': 24, 'critical': 72},
            'geopolitical': {'low': 6, 'medium': 24, 'high': 72, 'critical': 168},
            'port_congestion': {'low': 4, 'medium': 12, 'high': 48, 'critical': 120},
            'supplier': {'low': 12, 'medium': 48, 'high': 168, 'critical': 336}
        }
        
        return base_delays.get(risk_type, base_delays['weather']).get(severity.value, 8)
    
    def _identify_weather_risk_factors(self, weather_data):
        """Identify specific weather risk factors"""
        factors = []
        
        if weather_data.get('wind_speed_kmh', 0) > 80:
            factors.append('high_winds')
        if weather_data.get('wave_height_m', 0) > 4:
            factors.append('high_seas')
        if weather_data.get('precipitation_mm', 0) > 25:
            factors.append('heavy_precipitation')
        if weather_data.get('visibility_km', 10) < 2:
            factors.append('poor_visibility')
        if weather_data.get('temperature_c', 20) < -10:
            factors.append('extreme_cold')
            
        return factors
    
    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points in km"""
        try:
            import math
            
            R = 6371  # Earth's radius in km
            
            lat1_rad = math.radians(lat1)
            lat2_rad = math.radians(lat2)
            delta_lat = math.radians(lat2 - lat1)
            delta_lon = math.radians(lon2 - lon1)
            
            a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            
            return R * c
            
        except Exception:
            return 0
    
    def _analyze_enhanced_geopolitical_events(self, events, location, shipments, suppliers):
        """Enhanced geopolitical analysis with sentiment and impact assessment"""
        try:
            if not events:
                return None
                
            # Enhanced metrics calculation
            total_events = len(events)
            negative_events = [e for e in events if e.get('tone', 0) < -5]
            high_impact_events = [e for e in events if e.get('impact_score', 0) > 7]
            
            # Enhanced sentiment analysis
            avg_sentiment = np.mean([e.get('sentiment_score', 0) for e in events])
            sentiment_volatility = np.std([e.get('sentiment_score', 0) for e in events])
            
            # Enhanced severity calculation
            severity = self._calculate_enhanced_geopolitical_severity(
                len(negative_events), len(high_impact_events), avg_sentiment, sentiment_volatility
            )
            
            if severity == Severity.LOW:
                return None
                
            # Enhanced probability and confidence
            probability = min(0.9, (len(negative_events) + len(high_impact_events)) / 30)
            confidence = min(0.9, total_events / 100)
            
            # Find affected entities with enhanced impact assessment
            affected = self._find_enhanced_affected_entities(location, shipments, suppliers)
            
            if not affected:
                return None
                
            return RiskScore(
                risk_type=RiskType.GEOPOLITICAL,
                severity=severity,
                probability=probability,
                confidence=confidence,
                impact_radius_km=200.0,
                affected_entities=affected,
                data_sources=['GDELT', 'NewsAPI', 'TheNewsAPI'],
                evidence={
                    'event_count': total_events,
                    'negative_events': len(negative_events),
                    'high_impact_events': len(high_impact_events),
                    'avg_sentiment': avg_sentiment,
                    'sentiment_volatility': sentiment_volatility,
                    'sample_events': events[:3],
                    'enhanced_analysis': True
                },
                location=location
            )
            
        except Exception as e:
            logger.error(f"Enhanced geopolitical analysis error: {e}")
            return None
    
    def _calculate_enhanced_geopolitical_severity(self, negative_events, high_impact_events, avg_sentiment, volatility):
        """Enhanced geopolitical severity calculation"""
        # Multi-factor scoring
        event_score = 0
        if negative_events >= 20: event_score = 4
        elif negative_events >= 10: event_score = 3
        elif negative_events >= 5: event_score = 2
        elif negative_events >= 2: event_score = 1
        
        impact_score = 0
        if high_impact_events >= 10: impact_score = 4
        elif high_impact_events >= 5: impact_score = 3
        elif high_impact_events >= 2: impact_score = 2
        elif high_impact_events >= 1: impact_score = 1
        
        sentiment_score = 0
        if avg_sentiment <= -8: sentiment_score = 4
        elif avg_sentiment <= -6: sentiment_score = 3
        elif avg_sentiment <= -4: sentiment_score = 2
        elif avg_sentiment <= -2: sentiment_score = 1
        
        # Combined severity
        combined_score = max(event_score, impact_score, sentiment_score)
        
        if combined_score >= 4: return Severity.CRITICAL
        elif combined_score >= 3: return Severity.HIGH
        elif combined_score >= 2: return Severity.MEDIUM
        else: return Severity.LOW
    
    def _find_enhanced_affected_entities(self, location, shipments, suppliers):
        """Find entities affected by geopolitical events with enhanced impact assessment"""
        affected = []
        
        # Find affected shipments within impact radius
        for shipment in shipments:
            if self._is_shipment_affected_by_location(shipment, location, 200):  # 200km radius
                impact_hours = self._estimate_geopolitical_impact_hours(location, shipment)
                affected.append({
                    'type': 'shipment',
                    'id': shipment.id,
                    'reference': getattr(shipment, 'reference_number', f'SHIP-{shipment.id}'),
                    'eta_impact_hours': impact_hours,
                    'risk_factors': ['geopolitical_instability', 'route_disruption']
                })
        
        # Find affected suppliers
        for supplier in suppliers:
            if self._is_supplier_affected_by_location(supplier, location, 150):  # 150km radius
                affected.append({
                    'type': 'supplier',
                    'id': supplier.id,
                    'name': supplier.name,
                    'risk_factors': ['regional_instability', 'supply_disruption']
                })
        
        return affected
    
    def _is_shipment_affected_by_location(self, shipment, location, radius_km):
        """Check if shipment is affected by location-based risk"""
        try:
            # Check origin
            if hasattr(shipment, 'origin_lat') and shipment.origin_lat:
                distance = self._calculate_distance(
                    shipment.origin_lat, shipment.origin_lon,
                    location['lat'], location['lon']
                )
                if distance <= radius_km:
                    return True
            
            # Check destination
            if hasattr(shipment, 'destination_lat') and shipment.destination_lat:
                distance = self._calculate_distance(
                    shipment.destination_lat, shipment.destination_lon,
                    location['lat'], location['lon']
                )
                if distance <= radius_km:
                    return True
            
            return False
            
        except Exception:
            return False
    
    def _is_supplier_affected_by_location(self, supplier, location, radius_km):
        """Check if supplier is affected by location-based risk"""
        try:
            if hasattr(supplier, 'location') and supplier.location:
                import json
                if isinstance(supplier.location, str):
                    location_data = json.loads(supplier.location)
                else:
                    location_data = supplier.location
                
                if 'lat' in location_data and 'lon' in location_data:
                    distance = self._calculate_distance(
                        location_data['lat'], location_data['lon'],
                        location['lat'], location['lon']
                    )
                    return distance <= radius_km
            
            return False
            
        except Exception:
            return False
    
    def _estimate_geopolitical_impact_hours(self, location, shipment):
        """Estimate geopolitical impact hours for shipment"""
        # Base impact varies by proximity and shipment type
        base_impact = 24  # 24 hours base delay
        
        # Increase impact for high-value shipments
        if hasattr(shipment, 'value_usd') and shipment.value_usd and shipment.value_usd > 100000:
            base_impact *= 1.5
        
        # Increase impact for critical shipments
        if hasattr(shipment, 'priority') and shipment.priority == 'critical':
            base_impact *= 2
        
        return int(base_impact)
    
    def _log_error(self, error_message: str):
        """Log error via communicator"""
        try:
            self.communicator.send_message(
                MessageType.ERROR_REPORT,
                target_agent="orchestrator",
                payload={
                    'agent': self.agent_name,
                    'error': error_message,
                    'timestamp': datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"Failed to send error report: {e}")


def risk_predictor_loop(app, redis_client):
    """Background loop for risk predictor agent"""
    with app.app_context():
        communicator = AgentCommunicator(redis_client, "risk_predictor")
        agent = RiskPredictorAgent(communicator)
        
        logger.info("Risk Predictor Agent started")
        
        while True:
            try:
                # Run assessment cycle
                agent.run_assessment_cycle()
                
                # Sleep for configured interval (default 5 minutes)
                time.sleep(app.config.get('RISK_ASSESSMENT_INTERVAL', 300))
                
            except Exception as e:
                logger.error(f"Error in risk predictor loop: {e}")
                time.sleep(60)  # Wait a minute before retrying