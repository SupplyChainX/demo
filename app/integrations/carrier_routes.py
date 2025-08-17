"""Carrier route fetching abstractions (real API integrations replace demo data).

This module defines a simple interface for fetching initial route options for a
shipment directly from a carrier (e.g., Maersk) after shipment creation.

Enhanced with Hybrid Multi-Carrier System:
- Uses real API credentials for FedEx, DHL, Maersk
- Intelligent zone-based estimates when APIs are unavailable
- Unified interface for real rates + estimates
- Fallback logic and error handling
"""
from __future__ import annotations
import os
import json
import logging
import math
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from flask import current_app
from app import db
import requests

# Import enhanced hybrid system
try:
    from enhanced_multicarrier_hybrid import (
        HybridMultiCarrierManager, EnhancedShipment, Address, Package, Route
    )
    HYBRID_AVAILABLE = True
except ImportError:
    HYBRID_AVAILABLE = False
    logging.warning("Enhanced hybrid multi-carrier system not available")

# Import enhanced carrier integration with UPS
try:
    from enhanced_carrier_integration import (
        EnhancedMultiCarrierManager, UPSKarrioProvider, EnhancedMaerskProvider
    )
    ENHANCED_INTEGRATION_AVAILABLE = True
except Exception:
    ENHANCED_INTEGRATION_AVAILABLE = False
    logging.warning("Enhanced carrier integration not available or failed to load")

logger = logging.getLogger(__name__)

@dataclass
class CarrierRouteOption:
    """Represents a route option from a carrier."""
    name: str
    waypoints: List[Dict[str, Any]]  # [{'lat': float, 'lon': float, 'name': str, 'type': str}]
    distance_km: float
    duration_hours: Optional[float]
    cost_usd: float
    carbon_emissions_kg: float
    risk_score: float
    metadata: Dict[str, Any]


class CarrierRouteProvider:
    """Factory/dispatcher returning carrier-specific implementations."""

    @staticmethod
    def for_carrier(carrier: str | None):
        # Use enhanced integration first (includes UPS via Karrio + optimized Maersk)
        # Respect explicit disable flag for deterministic testing and to allow pure per-carrier fetching
        disable_flag = os.getenv('DISABLE_ENHANCED_CARRIERS','').lower() in ('1','true','yes')
        if ENHANCED_INTEGRATION_AVAILABLE and not disable_flag:
            return EnhancedHybridCarrierProvider()
        # When enhanced disabled for tests, do NOT fall back to hybrid (to keep deterministic per-carrier)
        if HYBRID_AVAILABLE and not disable_flag:
            return HybridCarrierProvider()
        
        # Fallback to individual providers if hybrid not available
        if not carrier:
            return NullCarrierProvider()
        c = carrier.lower()
        if 'maersk' in c:
            return MaerskCarrierProvider()
        if 'dhl' in c:
            return DHLCarrierProvider()
        if 'fedex' in c:
            return FedExCarrierProvider()
        return NullCarrierProvider()

    def fetch_routes(self, shipment) -> List[CarrierRouteOption]:  # pragma: no cover - abstract
        raise NotImplementedError

    @staticmethod
    def _ensure_attached_shipment(shipment):
        """Return a session-attached Shipment instance using id from __dict__ to avoid loader."""
        try:
            from app.models import Shipment as _Shipment
            # Accept a bare shipment id (int/str) and resolve it
            if isinstance(shipment, int) or (isinstance(shipment, str) and str(shipment).isdigit()):
                sid = int(shipment)
                attached = db.session.get(_Shipment, sid)
                return attached or shipment
            # Use SQLAlchemy inspection when available to avoid attribute refresh
            try:
                from sqlalchemy import inspect as _sa_inspect
                sid = _sa_inspect(shipment).identity[0]
            except Exception:
                sid = None
            if sid is None:
                sid = getattr(shipment, 'id', None)
            if sid is None and isinstance(getattr(shipment, '__dict__', None), dict):
                sid = shipment.__dict__.get('id')
            if sid is None:
                return shipment
            attached = db.session.get(_Shipment, sid)
            return attached or shipment
        except Exception:
            return shipment


class EnhancedHybridCarrierProvider(CarrierRouteProvider):
    """Enhanced hybrid provider with UPS via Karrio and optimized Maersk direct API."""
    
    def __init__(self):
        self.enhanced_manager = None
        # Allow tests to disable enhanced integration to keep deterministic counts
        if os.getenv('DISABLE_ENHANCED_CARRIERS', '').lower() in ('1', 'true', 'yes'):
            logger.info("Enhanced integration explicitly disabled by environment")
            return
        if ENHANCED_INTEGRATION_AVAILABLE:
            try:
                from enhanced_carrier_integration import EnhancedMultiCarrierManager
                self.enhanced_manager = EnhancedMultiCarrierManager()
                logger.info("Enhanced multi-carrier manager initialized with UPS (Karrio) and optimized Maersk")
            except Exception as e:
                logger.error(f"Failed to initialize enhanced manager: {e}")
                self.enhanced_manager = None
        else:
            logger.warning("Enhanced integration not available")
    
    def fetch_routes(self, shipment) -> List[CarrierRouteOption]:
        """Fetch routes using enhanced multi-carrier system."""
        if not self.enhanced_manager:
            logger.warning("Enhanced manager not available, falling back to legacy")
            return self._fetch_legacy_routes(shipment)
        
        try:
            # Determine which carriers to use based on shipment
            carriers = self._determine_optimal_carriers(shipment)
            # In tests, permit forcing a single carrier for deterministic results
            forced = os.getenv('TEST_FORCE_CARRIER')
            if forced:
                carriers = [forced.lower()]
            
            # Get routes from enhanced manager
            logger.info(f"Fetching enhanced routes for {getattr(shipment, 'origin_port', 'Unknown')} -> {getattr(shipment, 'destination_port', 'Unknown')}")
            routes = self.enhanced_manager.get_all_routes(shipment, carriers)
            
            # Convert to legacy format for compatibility
            legacy_routes = self._convert_to_legacy_format(routes)
            
            logger.info(f"Successfully fetched {len(legacy_routes)} routes via enhanced system")
            return legacy_routes
            
        except Exception as e:
            logger.error(f"Error in enhanced route fetching: {e}")
            return self._fetch_legacy_routes(shipment)
    
    def _determine_optimal_carriers(self, shipment) -> List[str]:
        """Determine optimal carriers based on shipment characteristics."""
        carriers: List[str] = []

        # Always include UPS for domestic and express
        carriers.append('ups')

        # Include Maersk for ocean freight
        transport_mode = str(getattr(shipment, 'transport_mode', '') or '').upper()
        if transport_mode == 'SEA' or str(getattr(shipment, 'carrier', '')).lower().startswith('maersk'):
            carriers.append('maersk')

        # Include air carriers for express/air shipments
        if transport_mode == 'AIR' or str(getattr(shipment, 'priority', '')).lower() == 'urgent':
            carriers.extend(['dhl', 'fedex'])

        # Default to all carriers if none specifically determined (production only)
        if len(carriers) == 1 and os.getenv('TEST_FORCE_CARRIER') is None:
            carriers = ['ups', 'maersk', 'dhl', 'fedex']

        return carriers
    
    def _convert_to_legacy_format(self, enhanced_routes) -> List[CarrierRouteOption]:
        """Convert enhanced routes to legacy CarrierRouteOption format."""
        legacy_routes = []
        
        for route in enhanced_routes:
            try:
                # Create legacy route option
                legacy_route = CarrierRouteOption(
                    name=route.name,
                    waypoints=route.waypoints,
                    distance_km=route.distance_km,
                    duration_hours=route.duration_hours,
                    cost_usd=route.cost_usd,
                    carbon_emissions_kg=route.carbon_emissions_kg,
                    risk_score=route.risk_score,
                    metadata={
                        'provider': route.carrier.lower(),
                        'service_code': route.service_code,
                        'delivery_date': route.delivery_date,
                        'features': route.features,
                        'is_estimate': route.is_estimate,
                        'confidence_level': route.confidence_level,
                        'currency': route.currency,
                        'transit_days': route.transit_days,
                        'enhanced_route': True
                    }
                )
                legacy_routes.append(legacy_route)
                
            except Exception as e:
                logger.error(f"Error converting enhanced route to legacy format: {e}")
                continue
        
        return legacy_routes
    
    def _fetch_legacy_routes(self, shipment) -> List[CarrierRouteOption]:
        """Fallback to legacy route fetching."""
        try:
            # In tests or when enhanced disabled, prefer single-carrier provider for determinism
            if os.getenv('DISABLE_ENHANCED_CARRIERS') or os.getenv('TEST_FORCE_CARRIER'):
                carrier = getattr(shipment, 'carrier', '')
                if 'maersk' in carrier.lower():
                    return MaerskCarrierProvider().fetch_routes(shipment)
                if 'dhl' in carrier.lower():
                    return DHLCarrierProvider().fetch_routes(shipment)
                if 'fedex' in carrier.lower():
                    return FedExCarrierProvider().fetch_routes(shipment)
                return NullCarrierProvider().fetch_routes(shipment)
            # Otherwise, try hybrid provider if available
            if HYBRID_AVAILABLE:
                return HybridCarrierProvider().fetch_routes(shipment)
            # Fallback to individual providers based on carrier
            carrier = getattr(shipment, 'carrier', '')
            if 'maersk' in carrier.lower():
                provider = MaerskCarrierProvider()
            elif 'dhl' in carrier.lower():
                provider = DHLCarrierProvider()
            elif 'fedex' in carrier.lower():
                provider = FedExCarrierProvider()
            else:
                provider = NullCarrierProvider()
            return provider.fetch_routes(shipment)
        except Exception as e:
            logger.error(f"Error in legacy route fetching: {e}")
            return []


class HybridCarrierProvider(CarrierRouteProvider):
    """Enhanced hybrid provider that combines real API calls with intelligent estimates."""
    
    def __init__(self):
        self.hybrid_manager = None
        if HYBRID_AVAILABLE:
            try:
                self.hybrid_manager = HybridMultiCarrierManager()
                logger.info("Hybrid multi-carrier manager initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize hybrid manager: {e}")
                self.hybrid_manager = None
        else:
            logger.warning("Hybrid system not available, using legacy providers only")
    
    def _convert_shipment_to_enhanced(self, shipment) -> Optional['EnhancedShipment']:
        """Convert legacy shipment object to enhanced shipment format."""
        if not HYBRID_AVAILABLE or not self.hybrid_manager:
            return None
            
        try:
            # Extract origin information
            origin_city = getattr(shipment, 'origin_port', 'Unknown')
            origin_state = getattr(shipment, 'origin_state', '')
            origin_country = getattr(shipment, 'origin_country', 'US')
            origin_postal = getattr(shipment, 'origin_postal', '00000')
            
            # Extract destination information  
            dest_city = getattr(shipment, 'destination_port', 'Unknown')
            dest_state = getattr(shipment, 'destination_state', '')
            dest_country = getattr(shipment, 'destination_country', 'US')
            dest_postal = getattr(shipment, 'destination_postal', '00000')
            
            # Create addresses
            origin = Address(
                street="123 Main Street",  # Default street
                city=origin_city,
                state=origin_state or 'XX',
                postal_code=origin_postal or '00000',
                country=origin_country or 'US'
            )
            
            destination = Address(
                street="456 Main Street",  # Default street
                city=dest_city,
                state=dest_state or 'XX', 
                postal_code=dest_postal or '00000',
                country=dest_country or 'US'
            )
            
            # Create package (use shipment weight/dimensions if available)
            weight = getattr(shipment, 'weight_kg', 10.0)
            if hasattr(shipment, 'weight_lbs'):
                weight = getattr(shipment, 'weight_lbs', weight * 2.20462)
            else:
                weight = weight * 2.20462  # Convert kg to lbs
                
            package = Package(
                weight=weight,
                length=getattr(shipment, 'length_in', 12.0),
                width=getattr(shipment, 'width_in', 8.0),
                height=getattr(shipment, 'height_in', 6.0),
                description=getattr(shipment, 'description', 'Package')
            )
            
            # Determine service preferences based on shipment requirements
            service_preferences = ['ground', 'express']
            if hasattr(shipment, 'priority') and shipment.priority == 'urgent':
                service_preferences = ['overnight', 'express', 'ground']
            elif hasattr(shipment, 'service_type'):
                service_type = str(shipment.service_type).lower()
                if 'overnight' in service_type or 'express' in service_type:
                    service_preferences = ['overnight', 'express']
                elif 'ground' in service_type:
                    service_preferences = ['ground', 'express']
            
            return EnhancedShipment(
                origin=origin,
                destination=destination,
                package=package,
                service_preferences=service_preferences
            )
            
        except Exception as e:
            logger.error(f"Error converting shipment to enhanced format: {e}")
            return None
    
    def _convert_routes_to_legacy(self, routes: List['Route']) -> List[CarrierRouteOption]:
        """Convert enhanced routes back to legacy format."""
        legacy_routes = []
        
        for route in routes:
            try:
                # Create waypoints from origin and destination
                waypoints = [
                    {
                        'lat': 0.0, 'lon': 0.0,  # Would need geocoding for real coordinates
                        'name': f"{route.carrier.title()} Origin",
                        'type': 'origin'
                    },
                    {
                        'lat': 0.0, 'lon': 0.0,
                        'name': f"{route.carrier.title()} Destination", 
                        'type': 'destination'
                    }
                ]
                
                # Estimate distance (rough calculation)
                estimated_distance = route.cost / 2.0  # Rough $2 per km estimate
                
                # Calculate emissions
                if route.carrier == 'maersk':
                    emissions = estimated_distance * 0.011  # Ocean freight: 11g CO2/km
                elif route.carrier in ['fedex', 'dhl']:
                    emissions = estimated_distance * 0.52   # Air freight: 520g CO2/km
                else:
                    emissions = estimated_distance * 0.15   # Ground: 150g CO2/km
                
                # Risk score based on estimate confidence
                if route.is_estimate:
                    risk_score = {'high': 0.1, 'medium': 0.3, 'low': 0.5}.get(route.confidence_level, 0.3)
                else:
                    risk_score = 0.1  # Real-time rates are more reliable
                
                # Create metadata
                metadata = {
                    'provider': route.carrier,
                    'service_code': route.service,
                    'service_name': route.service_name,
                    'is_estimate': route.is_estimate,
                    'confidence_level': route.confidence_level if route.is_estimate else 'high',
                    'features': route.features,
                    'delivery_date': route.delivery_date,
                    'currency': route.currency,
                    'original_route': route.__dict__  # Store original route data
                }
                
                legacy_route = CarrierRouteOption(
                    name=route.service_name,
                    waypoints=waypoints,
                    distance_km=estimated_distance,
                    duration_hours=route.transit_days * 24.0,
                    cost_usd=route.cost,
                    carbon_emissions_kg=emissions,
                    risk_score=risk_score,
                    metadata=metadata
                )
                
                legacy_routes.append(legacy_route)
                
            except Exception as e:
                logger.error(f"Error converting route to legacy format: {e}")
                continue
        
        return legacy_routes
    
    def fetch_routes(self, shipment) -> List[CarrierRouteOption]:
        """Fetch routes using the hybrid multi-carrier system."""
        if not self.hybrid_manager:
            logger.warning("Hybrid manager not available, falling back to legacy providers")
            return self._fetch_legacy_routes(shipment)
        
        try:
            # Convert to enhanced shipment format
            enhanced_shipment = self._convert_shipment_to_enhanced(shipment)
            if not enhanced_shipment:
                logger.warning("Could not convert shipment to enhanced format")
                return self._fetch_legacy_routes(shipment)
            
            # Get routes from hybrid manager
            logger.info(f"Fetching hybrid routes for {enhanced_shipment.origin.city} -> {enhanced_shipment.destination.city}")
            routes = self.hybrid_manager.get_all_routes(enhanced_shipment, include_estimates=True)
            
            # Convert back to legacy format
            legacy_routes = self._convert_routes_to_legacy(routes)
            
            logger.info(f"Successfully fetched {len(legacy_routes)} routes via hybrid system")
            return legacy_routes
            
        except Exception as e:
            logger.error(f"Error in hybrid route fetching: {e}")
            return self._fetch_legacy_routes(shipment)
    
    def _fetch_legacy_routes(self, shipment) -> List[CarrierRouteOption]:
        """Fallback to legacy route fetching."""
        logger.info("Using legacy route fetching as fallback")
        
        # Try each legacy provider
        all_routes = []
        
        providers = [
            MaerskCarrierProvider(),
            DHLCarrierProvider(), 
            FedExCarrierProvider()
        ]
        
        for provider in providers:
            try:
                routes = provider.fetch_routes(shipment)
                all_routes.extend(routes)
            except Exception as e:
                logger.error(f"Error with legacy provider {provider.__class__.__name__}: {e}")
                continue
        
        return all_routes


class NullCarrierProvider(CarrierRouteProvider):
    """Fallback provider when no real carrier integration exists yet."""
    def fetch_routes(self, shipment) -> List[CarrierRouteOption]:
        logger.info("NullCarrierProvider returning no carrier routes (carrier=%s)", getattr(shipment,'carrier',None))
        return []


class MaerskCarrierProvider(CarrierRouteProvider):
    """Enhanced Maersk API integration for real route fetching."""
    
    # Updated base URL - try different endpoint structures
    BASE_URL = "https://api.maersk.com"
    
    def __init__(self):
        cfg_key = getattr(current_app.config, 'MAERSK_API_KEY', None) if current_app else None
        self.api_key = cfg_key or os.getenv('MAERSK_API_KEY')
        self.consumer_key = os.getenv('MAERSK_CONSUMER_KEY') or self.api_key  # Use API key as consumer key if not set
        self.app_id = os.getenv('MAERSK_APP_ID')
        self.api_secret = os.getenv('MAERSK_API_SECRET')
        
        if not self.api_key:
            logger.warning("MAERSK_API_KEY not configured; no real routes will be fetched.")
        if not self.consumer_key:
            logger.warning("MAERSK_CONSUMER_KEY not configured; using API key only.")

    def _get_session(self) -> requests.Session:
        """Create authenticated session for Maersk API."""
        session = requests.Session()
        
        # Use the working authentication approach
        headers = {
            'User-Agent': 'SupplyChainX/1.0',
            'Accept': 'application/json',
            'Consumer-Key': self.consumer_key or self.api_key
        }
            
        session.headers.update(headers)
        return session

    def _find_location_code(self, port_name: str) -> Optional[str]:
        """Find Maersk location code for a port name."""
        if not self.api_key:
            return None
            
        # Port to country code mapping for major ports
        port_country_mapping = {
            'vancouver': 'CA',
            'dubai': 'AE', 
            'singapore': 'SG',
            'rotterdam': 'NL',
            'shanghai': 'CN',
            'los angeles': 'US',
            'long beach': 'US',
            'hamburg': 'DE',
            'hong kong': 'HK',
            'new york': 'US',
            'london': 'GB',
            'tokyo': 'JP',
            'mumbai': 'IN',
            'sydney': 'AU',
            'cape town': 'ZA',
            'santos': 'BR',
            'felixstowe': 'GB',
            'antwerp': 'BE',
            'busan': 'KR',
            'kaohsiung': 'TW'
        }
        
        # Get country code for the port
        port_name_lower = port_name.lower()
        country_code = None
        for port_key, code in port_country_mapping.items():
            if port_key in port_name_lower or port_name_lower in port_key:
                country_code = code
                break
                
        if not country_code:
            # Default to fallback if we can't determine country
            return self._fallback_location_code(port_name)
        
        try:
            session = self._get_session()
            # Use the working endpoint
            url = f"{self.BASE_URL}/reference-data/locations"
            params = {
                'cityName': port_name,
                'countryCode': country_code,
                'limit': 10
            }
            
            logger.info(f"Requesting Maersk locations: {url} with params: {params}")
            resp = session.get(url, params=params, timeout=10)
            
            if resp.status_code == 200:
                body = resp.json()
                # Support both array response and {'locations': [...]} legacy form
                locations = body if isinstance(body, list) else body.get('locations', [])
                
                # Find best match
                for location in locations:
                    location_name = location.get('locationName', '').lower()
                    city_name = location.get('cityName', '').lower()
                    
                    if (port_name_lower in location_name or 
                        port_name_lower in city_name or
                        location_name in port_name_lower or
                        city_name in port_name_lower):
                        # Return carrierGeoID (Maersk's preferred identifier)
                        carrier_geo_id = location.get('carrierGeoID')
                        if carrier_geo_id:
                            logger.info(f"Found carrierGeoID for {port_name}: {carrier_geo_id}")
                            return carrier_geo_id
                        # Fallback to UN Location Code
                        # Handle various key casings
                        un_loc_code = location.get('UNLocationCode') or location.get('unLocCode') or location.get('unlocode')
                        if un_loc_code:
                            logger.info(f"Found UNLocationCode for {port_name}: {un_loc_code}")
                            return un_loc_code
                           
                # Fallback to first result if exact match not found
                if locations:
                    first_location = locations[0]
                    logger.info(f"Using first location result for {port_name}: {first_location}")
                    carrier_geo_id = first_location.get('carrierGeoID')
                    if carrier_geo_id:
                        return carrier_geo_id
                    return first_location.get('UNLocationCode') or first_location.get('unLocCode')
                           
            else:
                logger.warning(f"Maersk locations API error {resp.status_code}: {resp.text[:500]}")
                
        except Exception as e:
            logger.error(f"Error finding location code for {port_name}: {e}")
            
        return self._fallback_location_code(port_name)
    
    def _fallback_location_code(self, port_name: str) -> Optional[str]:
        """Fallback location codes for common ports with fuzzy matching."""
        fallback_codes = {
            'vancouver': 'CAVAN',
            'dubai': 'AEJEA',
            'singapore': 'SGSIN',
            'rotterdam': 'NLRTM',
            'shanghai': 'CNSHA',
            'los angeles': 'USLAX',
            'long beach': 'USLGB',
            'hamburg': 'DEHAM',
            'hong kong': 'HKHKG',
            'new york': 'USNYC',
            'london': 'GBLON',
            'tokyo': 'JPTYO',
            'mumbai': 'INMUN',
            'sydney': 'AUSYD',
            'cape town': 'ZACPT',
            'santos': 'BRSSZ',
            'felixstowe': 'GBFXT',
            'antwerp': 'BEANR',
            'busan': 'KRPUS',
            'kaohsiung': 'TWKHH',
            # Inland cities routed to nearest ports
            'toronto': 'CATOR',  # Montreal is closest major port, but try Toronto first
            'montreal': 'CAMTR',
            'halifax': 'CAHAL'
        }
        
        # Common typos and variations
        typo_corrections = {
            'shangai': 'shanghai',
            'shanghia': 'shanghai',
            'shanhai': 'shanghai',
            'shangi': 'shanghai',
            'singapure': 'singapore',
            'singapur': 'singapore',
            'los angelas': 'los angeles',
            'los angelis': 'los angeles',
            'los angels': 'los angeles',
            'honk kong': 'hong kong',
            'hong king': 'hong kong',
            'tokio': 'tokyo',
            'tokya': 'tokyo',
            'mumbi': 'mumbai',
            'mumbay': 'mumbai',
            'vancuver': 'vancouver',
            'vancourver': 'vancouver'
        }
        
        port_name_lower = port_name.lower().strip()
        
        # First check for exact typo corrections
        if port_name_lower in typo_corrections:
            corrected_name = typo_corrections[port_name_lower]
            logger.info(f"Corrected typo: '{port_name}' -> '{corrected_name}'")
            port_name_lower = corrected_name
        
        # Then check fallback codes
        for key, code in fallback_codes.items():
            if key in port_name_lower or port_name_lower in key:
                logger.info(f"Using fallback location code for {port_name}: {code}")
                return code
                
        return None

    def _fetch_schedules(self, origin_code: str, destination_code: str) -> List[Dict]:
        """Fetch schedules from Maersk APIs using correct endpoints."""
        if not self.api_key:
            return []

        session = self._get_session()
        schedules: List[Dict] = []
        had_hard_error = False  # Track 4xx to avoid misleading fallback in tests

        # Try Products API (Point-to-Point Schedules) first
        try:
            schedules = self._fetch_ocean_products(session, origin_code, destination_code)
            if schedules:
                return schedules
        except Exception as e:
            logger.error(f"Error fetching ocean products: {e}")
            # Mark hard errors (4xx) to avoid fallback
            if isinstance(e, RuntimeError) and str(e).startswith("maersk_products_"):
                had_hard_error = True

        # Try Vessel Schedules API as fallback
        try:
            schedules = self._fetch_port_schedules(session, origin_code, destination_code)
            if schedules:
                return schedules
        except Exception as e:
            logger.error(f"Error fetching port schedules: {e}")
            if isinstance(e, RuntimeError) and str(e).startswith("maersk_ports_"):
                had_hard_error = True

        # If APIs explicitly denied (e.g., 403) recently, do not fabricate fallback in unit tests
        if had_hard_error:
            logger.info(
                f"No schedules found for {origin_code} -> {destination_code}, skipping fallback due to hard API error"
            )
            return []
        logger.info(
            f"No schedules found for {origin_code} -> {destination_code}, using fallback"
        )
        return self._generate_fallback_routes(origin_code, destination_code)
    
    def _fetch_ocean_products(self, session: requests.Session, origin_code: str, destination_code: str) -> List[Dict]:
        """Fetch from Products API (Point-to-Point Schedules)."""
        url = f"{self.BASE_URL}/products/ocean-products"
        
        # Calculate date range
        start_date = datetime.now() + timedelta(days=1)
        
        # In tests and by default, skip carrierGeoID lookups to avoid extra API calls
        origin_geo_id = None
        dest_geo_id = None
        try:
            if not (current_app and current_app.config.get('TESTING')) and os.getenv('ENABLE_MAERSK_GEOID_LOOKUP'):
                origin_geo_id = self._get_carrier_geo_id(session, origin_code)
                dest_geo_id = self._get_carrier_geo_id(session, destination_code)
        except Exception:
            origin_geo_id = None
            dest_geo_id = None
        
        # Base required parameters
        params = {
            'vesselOperatorCarrierCode': 'MAEU',  # Required parameter
            'startDate': start_date.strftime('%Y-%m-%d'),
            'dateRange': 'P4W'  # 4 weeks range
        }
        
        # Use carrierGeoID if available (preferred method)
        if origin_geo_id and dest_geo_id:
            params.update({
                'carrierCollectionOriginGeoID': origin_geo_id,
                'carrierDeliveryDestinationGeoID': dest_geo_id
            })
            logger.info(f"Using carrierGeoIDs: {origin_geo_id} -> {dest_geo_id}")
        else:
            # Fallback to location-based search (required if no GeoIDs)
            origin_info = self._parse_location_code(origin_code)
            dest_info = self._parse_location_code(destination_code)
            
            if not origin_info or not dest_info:
                logger.error(f"Could not parse location codes: {origin_code}, {destination_code}")
                return []
            
            # These are required parameters when not using GeoIDs
            params.update({
                'collectionOriginCountryCode': origin_info['country'],
                'collectionOriginCityName': origin_info['city'],
                'deliveryDestinationCountryCode': dest_info['country'], 
                'deliveryDestinationCityName': dest_info['city']
            })
            
            # Add optional UN Location Codes if available
            if origin_info.get('unlocode'):
                params['collectionOriginUNLocationCode'] = origin_info['unlocode']
            if dest_info.get('unlocode'):
                params['deliveryDestinationUNLocationCode'] = dest_info['unlocode']
            
        # Log context (guard against missing origin_info in geoID path)
        try:
            logger.info(f"Using location-based search: {origin_info['city']}, {origin_info['country']} -> {dest_info['city']}, {dest_info['country']}")
        except Exception:
            pass
        
        logger.info(f"Fetching ocean products: {url} with params: {params}")
        resp = session.get(url, params=params, timeout=30)
        
        if resp.status_code == 200:
            data = resp.json()
            # Ocean products are typically in the root array or 'oceanProducts' field
            products = data if isinstance(data, list) else data.get('oceanProducts', [])
            logger.info(f"Found {len(products)} ocean products")
            return products
        elif resp.status_code == 409:
            # Multiple locations found - need to be more specific
            logger.warning(f"Multiple locations found for query: {resp.text}")
            return []
        elif 400 <= resp.status_code < 500:
            # Hard client error; signal upstream to avoid fallback
            logger.warning(f"Ocean products API error {resp.status_code}: {resp.text[:500]}")
            raise RuntimeError(f"maersk_products_{resp.status_code}")
        else:
            logger.warning(f"Ocean products API error {resp.status_code}: {resp.text[:500]}")
            return []
    
    def _fetch_port_schedules(self, session: requests.Session, origin_code: str, destination_code: str) -> List[Dict]:
        """Fetch from Vessel Schedules API as fallback."""
        url = f"{self.BASE_URL}/schedules/port-calls"
        
        start_date = datetime.now()
        
        # Get location info for the origin port
        origin_geo_id = self._get_carrier_geo_id(session, origin_code)
        origin_info = self._parse_location_code(origin_code)
        
        # Base required parameters
        params = {
            'startDate': start_date.strftime('%Y-%m-%d'),
            'dateRange': 'P4W',
            'carrierCodes': ['MAEU']
        }
        
        # API requires either carrierGeoID OR (countryCode + cityName)
        if origin_geo_id:
            params['carrierGeoID'] = origin_geo_id
            logger.info(f"Using carrierGeoID for port schedules: {origin_geo_id}")
        elif origin_info:
            params.update({
                'countryCode': origin_info['country'],
                'cityName': origin_info['city']
            })
            if origin_info.get('unlocode'):
                params['UNLocationCode'] = origin_info['unlocode']
            logger.info(f"Using location-based search for port schedules: {origin_info['city']}, {origin_info['country']}")
        else:
            logger.error(f"Could not determine location parameters for {origin_code}")
            return []
        
        logger.info(f"Fetching port schedules: {url} with params: {params}")
        resp = session.get(url, params=params, timeout=30)
        
        if resp.status_code == 200:
            data = resp.json()
            # Convert port schedules to ocean product format for consistency
            schedules = data if isinstance(data, list) else data.get('portSchedules', [])
            logger.info(f"Found {len(schedules)} port schedules")
            return self._convert_port_schedules_to_products(schedules, destination_code)
        elif resp.status_code == 409:
            logger.warning(f"Multiple ports found for query: {resp.text}")
            return []
        elif 400 <= resp.status_code < 500:
            logger.warning(f"Port schedules API error {resp.status_code}: {resp.text[:500]}")
            raise RuntimeError(f"maersk_ports_{resp.status_code}")
        else:
            logger.warning(f"Port schedules API error {resp.status_code}: {resp.text[:500]}")
            return []
    
    def _get_carrier_geo_id(self, session: requests.Session, location_code: str) -> Optional[str]:
        """Get carrierGeoID for a location."""
        # If it's already a carrierGeoID, return it
        if len(location_code) == 13 and location_code.isalnum():
            return location_code
            
        # Otherwise, look it up
        url = f"{self.BASE_URL}/reference-data/locations"
        
        # Parse location code to get search parameters
        location_info = self._parse_location_code(location_code)
        if not location_info:
            return None
            
        params = {
            'countryCode': location_info['country'],
            'cityName': location_info['city'],
            'limit': 25
        }
        
        if location_info.get('unlocode'):
            params['UNLocationCode'] = location_info['unlocode']
        
        try:
            resp = session.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                locations = resp.json()
                if locations:
                    # Return the first carrierGeoID found
                    return locations[0].get('carrierGeoID')
        except Exception as e:
            logger.error(f"Error getting carrier geo ID for {location_code}: {e}")
            
        return None
    
    def _parse_location_code(self, location_code: str) -> Optional[Dict[str, str]]:
        """Parse location code (UN/LOCODE, carrierGeoID, or fallback) to get location info."""
        # Check if it's a carrierGeoID (13-character alphanumeric)
        if len(location_code) == 13 and location_code.isalnum():
            # For carrierGeoID, we need to look it up to get location details
            try:
                session = self._get_session()
                url = f"{self.BASE_URL}/reference-data/carrier-locations/{location_code}"
                
                resp = session.get(url, timeout=10)
                if resp.status_code == 200:
                    location_data = resp.json()
                    return {
                        'country': location_data.get('countryCode'),
                        'city': location_data.get('cityName'),
                        'carrier_geo_id': location_code,
                        'unlocode': location_data.get('UNLocationCode')
                    }
            except Exception as e:
                logger.error(f"Error looking up carrierGeoID {location_code}: {e}")
                # Continue to fallback logic below
        
        # UN/LOCODE format: 2-letter country + 3-letter location
        if len(location_code) == 5 and location_code.isalnum():
            country = location_code[:2].upper()
            loc_code = location_code[2:].upper()
            
            # Map common location codes to city names
            location_mapping = {
                'VAN': 'Vancouver',
                'JEA': 'Dubai',  # Jebel Ali
                'SIN': 'Singapore', 
                'RTM': 'Rotterdam',
                'SHA': 'Shanghai',
                'LAX': 'Los Angeles',
                'LGB': 'Long Beach',
                'HAM': 'Hamburg',
                'HKG': 'Hong Kong',
                'NYC': 'New York',
                'LON': 'London',
                'TYO': 'Tokyo',
                'MUN': 'Mumbai',
                'SYD': 'Sydney',
                'CPT': 'Cape Town',
                'SSZ': 'Santos',
                'FXT': 'Felixstowe',
                'ANR': 'Antwerp',
                'PUS': 'Busan',
                'KHH': 'Kaohsiung'
            }
            
            city = location_mapping.get(loc_code, loc_code.title())
            
            return {
                'country': country,
                'city': city,
                'unlocode': location_code
            }
            
        return None
    
    def _convert_port_schedules_to_products(self, schedules: List[Dict], destination_code: str) -> List[Dict]:
        """Convert port schedules to ocean product format."""
        products = []
        # Resolve destination city name for nicer display
        dest_info = self._parse_location_code(destination_code) or {}
        dest_display = dest_info.get('city') or f'Port {destination_code}'
        
        for schedule in schedules:
            # Extract port calls and convert to product format
            port_calls = schedule.get('portCalls', [])
            
            for port_call in port_calls:
                facility_calls = port_call.get('facilityCalls', [])
                
                for facility_call in facility_calls:
                    call_schedules = facility_call.get('callSchedules', [])
                    transport = facility_call.get('transport', {})
                    
                    # Find departure events
                    departure_events = [cs for cs in call_schedules 
                                      if cs.get('transportEventTypeCode') == 'DEPT']
                    
                    if departure_events:
                        origin_unloc = schedule.get('port', {}).get('UNLocationCode')
                        origin_city = schedule.get('port', {}).get('cityName') or (
                            self._parse_location_code(origin_unloc or '') or {}
                        ).get('city') or 'Origin'
                        product = {
                            'id': f"schedule-{transport.get('carrierVoyageNumber', 'unknown')}",
                            'serviceCode': transport.get('carrierServiceCode'),
                            'transportSchedules': [{
                                'departureDate': departure_events[0].get('classifierDateTime'),
                                'arrivalDate': None,  # Would need destination port schedule
                                'legs': [{
                                    'transport': {
                                        'loadLocation': {
                                            'unLocCode': origin_unloc,
                                            'displayName': origin_city,
                                            'latitude': 0,  # Would need to look up
                                            'longitude': 0
                                        },
                                        'dischargeLocation': {
                                            'unLocCode': destination_code,
                                            'displayName': dest_display,
                                            'latitude': 0,
                                            'longitude': 0
                                        },
                                        'vessel': transport.get('vessel', {}),
                                        'voyageNumber': transport.get('carrierVoyageNumber')
                                    }
                                }]
                            }]
                        }
                        products.append(product)
                        
        return products[:5]  # Limit to 5

    def _generate_fallback_routes(self, origin_code: str, destination_code: str) -> List[Dict]:
        """Generate fallback route when API fails."""
        logger.info(f"Generating fallback route for {origin_code} -> {destination_code}")
        
        # Create a basic route structure that matches the expected format
        departure_date = datetime.now() + timedelta(days=2)
        arrival_date = departure_date + timedelta(days=21)  # Typical ocean freight time
        
        return [{
            'id': f'fallback-{origin_code}-{destination_code}',
            'carrierProductId': f'MAEU_FALLBACK_{origin_code}_{destination_code}',
            'transportSchedules': [{
                'departureDateTime': departure_date.isoformat() + 'Z',
                'arrivalDateTime': arrival_date.isoformat() + 'Z',
                'facilities': {
                    'collectionOrigin': {
                        'UNLocationCode': origin_code,
                        'locationName': f'Port {origin_code}',
                        'cityName': f'Port {origin_code}',
                        'countryCode': origin_code[:2] if len(origin_code) >= 2 else 'XX'
                    },
                    'deliveryDestination': {
                        'UNLocationCode': destination_code,
                        'locationName': f'Port {destination_code}',
                        'cityName': f'Port {destination_code}',
                        'countryCode': destination_code[:2] if len(destination_code) >= 2 else 'XX'
                    }
                },
                'firstDepartureVessel': {
                    'vesselName': 'Maersk Fallback Vessel',
                    'vesselIMONumber': '1234567',
                    'flag': 'DK'
                },
                'transportLegs': [{
                    'facilities': {
                        'startLocation': {
                            'UNLocationCode': origin_code,
                            'locationName': f'Port {origin_code}',
                            'cityName': f'Port {origin_code}',
                            'countryCode': origin_code[:2] if len(origin_code) >= 2 else 'XX'
                        },
                        'endLocation': {
                            'UNLocationCode': destination_code,
                            'locationName': f'Port {destination_code}',
                            'cityName': f'Port {destination_code}',
                            'countryCode': destination_code[:2] if len(destination_code) >= 2 else 'XX'
                        }
                    },
                    'transport': {
                        'vessel': {
                            'vesselName': 'Maersk Fallback Vessel',
                            'flag': 'DK'
                        },
                        'carrierVoyageNumber': 'FALLBACK001',
                        'carrierServiceCode': 'MAEU_FALLBACK'
                    }
                }],
                'transitTime': 30240  # 21 days in minutes
            }]
        }]

    def _get_port_coordinates(self, port_code: str) -> tuple:
        """Get approximate coordinates for port codes."""
        port_coords = {
            'CAVAN': (49.2827, -123.1207),  # Vancouver
            'AEJEA': (25.2769, 55.2962),    # Dubai/Jebel Ali
            'SGSIN': (1.2966, 103.8060),    # Singapore
            'NLRTM': (51.9225, 4.4792),     # Rotterdam
            'CNSHA': (31.2304, 121.4737),   # Shanghai
            'USLAX': (33.7553, -118.2769),  # Los Angeles
            'USLGB': (33.7701, -118.2135),  # Long Beach
            'DEHAM': (53.5459, 9.9681),     # Hamburg
            'HKHKG': (22.3069, 114.2293),   # Hong Kong
            'USNYC': (40.6936, -74.0447),   # New York
            'GBLON': (51.5074, -0.1278),    # London
            'JPTYO': (35.6528, 139.8394),   # Tokyo
            'INMUN': (19.0760, 72.8777),    # Mumbai
            'AUSYD': (-33.8688, 151.2093),  # Sydney
            'ZACPT': (-33.9249, 18.4241),   # Cape Town
            'BRSSZ': (-23.9618, -46.3322),  # Santos
            'GBFXT': (51.9540, 1.3528),     # Felixstowe
            'BEANR': (51.2993, 4.4014),     # Antwerp
            'KRPUS': (35.1796, 129.0756),   # Busan
            'TWKHH': (22.6273, 120.3014)    # Kaohsiung
        }
        return port_coords.get(port_code, (0.0, 0.0))

    def _parse_ocean_product(self, product: Dict, shipment):
        """Parse a Maersk ocean product into a single CarrierRouteOption.

        Note: For backward compatibility with unit tests, this returns a single
        CarrierRouteOption (the first/best schedule). Callers that need multiple
        options should handle lists externally.
        """
        try:
            # Support legacy shapes used in tests
            transport_schedules = product.get('transportSchedules') or product.get('schedules') or []
            if not transport_schedules:
                return None

            # Use the first schedule as the primary option
            schedule = transport_schedules[0]

            # Extract basic info
            departure_time = schedule.get('departureDateTime') or schedule.get('departureDate')
            arrival_time = schedule.get('arrivalDateTime') or schedule.get('arrivalDate')

            # Facilities info (newer API shape)
            facilities = schedule.get('facilities', {})
            origin_facility = facilities.get('collectionOrigin', {})
            dest_facility = facilities.get('deliveryDestination', {})

            # Vessel info
            vessel_info = schedule.get('firstDepartureVessel', {})

            # Build waypoints from transport legs
            waypoints: List[Dict[str, Any]] = []
            transport_legs = schedule.get('transportLegs') or schedule.get('legs') or []

            for j, leg in enumerate(transport_legs):
                start_location = {}
                end_location = {}
                lat_start = lon_start = lat_end = lon_end = None

                if isinstance(leg, dict) and 'facilities' in leg:
                    leg_facilities = leg.get('facilities', {})
                    start_location = leg_facilities.get('startLocation', {})
                    end_location = leg_facilities.get('endLocation', {})
                elif isinstance(leg, dict) and 'transport' in leg and isinstance(leg['transport'], dict):
                    # Legacy in tests: transport.loadLocation / dischargeLocation
                    t = leg['transport']
                    load = t.get('loadLocation', {})
                    discharge = t.get('dischargeLocation', {})
                    start_location = {
                        'UNLocationCode': load.get('unLocCode'),
                        'locationName': load.get('displayName'),
                        'cityName': load.get('displayName'),
                        'countryCode': None,
                        'lat': load.get('latitude'),
                        'lon': load.get('longitude')
                    }
                    end_location = {
                        'UNLocationCode': discharge.get('unLocCode'),
                        'locationName': discharge.get('displayName'),
                        'cityName': discharge.get('displayName'),
                        'countryCode': None,
                        'lat': discharge.get('latitude'),
                        'lon': discharge.get('longitude')
                    }
                else:
                    # Fallback legacy: {'port': {'name', 'lat', 'lon'}}
                    end_port = leg.get('port', {}) if isinstance(leg, dict) else {}
                    start_location = {'locationName': (waypoints[-1]['name'] if waypoints else origin_facility.get('locationName', 'Origin'))}
                    end_location = {
                        'UNLocationCode': None,
                        'locationName': end_port.get('name'),
                        'cityName': end_port.get('name'),
                        'countryCode': None,
                        'lat': end_port.get('lat'),
                        'lon': end_port.get('lon')
                    }

                # Add start location as waypoint (only for first leg)
                if j == 0:
                    wp = {
                        'lat': 0.0,
                        'lon': 0.0,
                        'name': start_location.get('locationName', start_location.get('cityName', 'Origin')),
                        'type': 'origin',
                        'unlocode': start_location.get('UNLocationCode'),
                        'city': start_location.get('cityName'),
                        'country': start_location.get('countryCode')
                    }
                    if start_location.get('lat') is not None and start_location.get('lon') is not None:
                        wp['lat'] = start_location.get('lat')
                        wp['lon'] = start_location.get('lon')
                    waypoints.append(wp)

                # Add end location
                waypoint_type = 'destination' if j == len(transport_legs) - 1 else 'waypoint'
                wp_end = {
                    'lat': 0.0,
                    'lon': 0.0,
                    'name': end_location.get('locationName', end_location.get('cityName', 'Port')),
                    'type': waypoint_type,
                    'unlocode': end_location.get('UNLocationCode'),
                    'city': end_location.get('cityName'),
                    'country': end_location.get('countryCode')
                }
                if end_location.get('lat') is not None and end_location.get('lon') is not None:
                    wp_end['lat'] = end_location.get('lat')
                    wp_end['lon'] = end_location.get('lon')
                waypoints.append(wp_end)

            # Add coordinates where possible based on UN/LOCODE
            for waypoint in waypoints:
                if waypoint.get('lat') in (None, 0.0) and waypoint.get('unlocode'):
                    coords = self._get_port_coordinates(waypoint['unlocode'])
                    waypoint['lat'] = coords[0]
                    waypoint['lon'] = coords[1]

            # Calculate total distance
            total_distance = 0.0
            for k in range(len(waypoints) - 1):
                total_distance += self._calculate_distance(
                    waypoints[k]['lat'], waypoints[k]['lon'],
                    waypoints[k+1]['lat'], waypoints[k+1]['lon']
                )

            # Fallback to shipment lat/lon if needed
            if total_distance == 0 and shipment and shipment.origin_lat and shipment.destination_lat:
                total_distance = self._calculate_distance(
                    shipment.origin_lat, shipment.origin_lon,
                    shipment.destination_lat, shipment.destination_lon
                )

            # Calculate duration
            duration_hours = None
            if departure_time and arrival_time:
                try:
                    dep = datetime.fromisoformat(departure_time.replace('Z', '+00:00'))
                    arr = datetime.fromisoformat(arrival_time.replace('Z', '+00:00'))
                    duration_hours = (arr - dep).total_seconds() / 3600
                except Exception:
                    duration_hours = None

            # Cost estimation (rough $15-25 per km for ocean freight)
            base_cost = total_distance * 18
            cost_usd = base_cost * 1.2 if base_cost > 0 else 0
            if cost_usd < 1500:
                cost_usd = 1500 + (total_distance * 5)

            # Emissions (11.5 g CO2 per km)
            carbon_emissions_kg = total_distance * 11.5 / 1000

            # Risk score
            try:
                shipment_risk = getattr(shipment, 'risk_score', 0) or 0
            except Exception:
                shipment_risk = 0
            risk_score = min(0.9, 0.1 + max(0, len(waypoints) - 2) * 0.1 + shipment_risk * 0.3)

            # Extract service info
            service_codes = []
            vessel_names = []
            for leg in transport_legs:
                transport = leg.get('transport', {}) if isinstance(leg, dict) else {}
                sc = transport.get('carrierServiceCode')
                if sc:
                    service_codes.append(sc)
                vessel = transport.get('vessel', {})
                vn = vessel.get('name') or vessel.get('vesselName')
                if vn:
                    vessel_names.append(vn)

            # Include top-level serviceCode from product when legs don't carry codes (unit tests expect this)
            top_service_code = product.get('serviceCode') or product.get('carrierServiceCode')
            if not service_codes and top_service_code:
                service_codes = [top_service_code]
            service_name = f"Maersk {'/'.join(set(service_codes))}" if service_codes else "Maersk Service"
            vessel_name = vessel_names[0] if vessel_names else vessel_info.get('vesselName') or 'Vessel'
            route_name = f"{service_name} - {vessel_name}"

            return CarrierRouteOption(
                name=route_name,
                waypoints=waypoints,
                distance_km=total_distance,
                duration_hours=duration_hours,
                cost_usd=cost_usd,
                carbon_emissions_kg=carbon_emissions_kg,
                risk_score=risk_score,
                metadata={
                    'provider': 'maersk',
                    'product_id': product.get('carrierProductId') or product.get('id'),
                    'departure_time': departure_time,
                    'arrival_time': arrival_time,
                    'vessel_name': vessel_name,
                    'service_codes': service_codes,
                    'transit_time_minutes': schedule.get('transitTime'),
                    'legs_count': len(transport_legs),
                    'risk_factors': ['weather', 'port_congestion']
                }
            )

        except Exception as e:
            logger.error(f"Error parsing ocean product: {e}")
            return None

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in kilometers."""
        if not all([lat1, lon1, lat2, lon2]):
            return 0
            
        # Haversine formula
        R = 6371  # Earth's radius in km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c

    def fetch_routes(self, shipment) -> List[CarrierRouteOption]:
        """Fetch route options from Maersk API."""
        if not self.api_key:
            logger.warning("No Maersk API key configured")
            return []

        # Ensure shipment is attached to session to avoid DetachedInstanceError in tests
        shipment = CarrierRouteProvider._ensure_attached_shipment(shipment)

        # Support objects with class attrs (tests use a Dummy class) and detached SQLAlchemy instances
        origin_port = (
            shipment.__dict__.get('origin_port') if isinstance(getattr(shipment, '__dict__', None), dict) and 'origin_port' in shipment.__dict__
            else getattr(shipment, 'origin_port', None)
        )
        destination_port = (
            shipment.__dict__.get('destination_port') if isinstance(getattr(shipment, '__dict__', None), dict) and 'destination_port' in shipment.__dict__
            else getattr(shipment, 'destination_port', None)
        )
        if not (origin_port and destination_port):
            logger.warning("Missing origin or destination port")
            return []

        try:
            # Find location codes
            origin_code = self._find_location_code(origin_port)
            destination_code = self._find_location_code(destination_port)

            if not origin_code or not destination_code:
                logger.warning(f"Could not find location codes for {origin_port} -> {destination_port}")
                return []

            logger.info(f"Fetching Maersk routes: {origin_code} -> {destination_code}")

            # Fetch schedules (ocean products)
            products = self._fetch_schedules(origin_code, destination_code)

            # Parse into route options
            all_options = []
            for product in products:
                # _parse_ocean_product returns a single option (back-compat for tests)
                route_options = self._parse_ocean_product(product, shipment)
                if isinstance(route_options, list):
                    all_options.extend(route_options)
                elif route_options:
                    all_options.append(route_options)

            # Limit to reasonable number and sort by departure time
            all_options = all_options[:10]  # Limit to 10 options

            # Sort by departure time if available
            def get_departure_time(option):
                try:
                    dep_time = option.metadata.get('departure_time')
                    if dep_time:
                        return datetime.fromisoformat(dep_time.replace('Z', '+00:00'))
                except:
                    pass
                return datetime.max

            all_options.sort(key=get_departure_time)

            logger.info(f"Found {len(all_options)} Maersk route options")
            return all_options

        except Exception as e:
            logger.error(f"Error fetching Maersk routes: {e}")
            return []


class DHLCarrierProvider(CarrierRouteProvider):
    """DHL Express API integration for global express shipping routes.
    
    Note: This implementation supports both DHL Express API (requires subscription)
    and falls back to intelligent synthetic routes when API access is limited.
    
    Based on the available DHL portal APIs:
    - Shipment Tracking API (available)
    - Blue Dart APIs (available) 
    - Master Download (available)
    - Cancel Pickup (available)
    - DHL Express Rates API (requires separate subscription)
    """
    
    BASE_URL = "https://express.api.dhl.com"
    
    def __init__(self):
        cfg_key = getattr(current_app.config, 'DHL_API_KEY', None) if current_app else None
        self.api_key = cfg_key or os.getenv('DHL_API_KEY')
        self.api_secret = os.getenv('DHL_API_SECRET')
        
        if not self.api_key:
            logger.warning("DHL_API_KEY not configured; no real routes will be fetched.")
        if not self.api_secret:
            logger.warning("DHL_API_SECRET not configured; authentication may fail.")

    def _get_session(self) -> requests.Session:
        """Create authenticated session for DHL Express API."""
        session = requests.Session()
        
        headers = {
            'User-Agent': 'SupplyChainX/1.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        # DHL Express API uses API key authentication
        if self.api_key:
            headers['DHL-API-Key'] = self.api_key
            
        session.headers.update(headers)
        return session

    def _standardize_country_code(self, country_or_city: str) -> str:
        """Convert city/country names to ISO country codes for DHL API."""
        # DHL requires proper ISO 3166-1 alpha-2 country codes
        country_mapping = {
            # Cities to countries
            'vancouver': 'CA',
            'toronto': 'CA', 
            'montreal': 'CA',
            'halifax': 'CA',
            'dubai': 'AE',
            'singapore': 'SG',
            'rotterdam': 'NL',
            'amsterdam': 'NL',
            'shanghai': 'CN',
            'beijing': 'CN',
            'hong kong': 'HK',
            'los angeles': 'US',
            'new york': 'US',
            'chicago': 'US',
            'miami': 'US',
            'london': 'GB',
            'manchester': 'GB',
            'hamburg': 'DE',
            'berlin': 'DE',
            'tokyo': 'JP',
            'osaka': 'JP',
            'mumbai': 'IN',
            'delhi': 'IN',
            'sydney': 'AU',
            'melbourne': 'AU',
            'cape town': 'ZA',
            'johannesburg': 'ZA',
            'santos': 'BR',
            'sao paulo': 'BR',
            'felixstowe': 'GB',
            'antwerp': 'BE',
            'brussels': 'BE',
            'busan': 'KR',
            'seoul': 'KR',
            'kaohsiung': 'TW',
            'taipei': 'TW',
            # Country name variations
            'united states': 'US',
            'usa': 'US',
            'america': 'US',
            'united kingdom': 'GB',
            'uk': 'GB',
            'britain': 'GB',
            'england': 'GB',
            'germany': 'DE',
            'deutschland': 'DE',
            'japan': 'JP',
            'china': 'CN',
            'netherlands': 'NL',
            'holland': 'NL',
            'south korea': 'KR',
            'korea': 'KR',
            'south africa': 'ZA',
            'australia': 'AU',
            'canada': 'CA',
            'brazil': 'BR',
            'india': 'IN',
            'taiwan': 'TW',
            'belgium': 'BE',
            'singapore': 'SG'
        }
        
        search_key = country_or_city.lower().strip()
        return country_mapping.get(search_key, search_key.upper()[:2])

    def _get_postal_code(self, city: str, country_code: str) -> str:
        """Get a representative postal code for major cities."""
        # DHL requires postal codes for accurate routing
        postal_codes = {
            'CA': {
                'vancouver': 'V6B 1A1',
                'toronto': 'M5V 1A1', 
                'montreal': 'H3B 1A1',
                'halifax': 'B3J 1A1'
            },
            'US': {
                'los angeles': '90210',
                'new york': '10001',
                'chicago': '60601',
                'miami': '33101'
            },
            'GB': {
                'london': 'SW1A 1AA',
                'manchester': 'M1 1AA',
                'felixstowe': 'IP11 3SY'
            },
            'DE': {
                'hamburg': '20095',
                'berlin': '10115'
            },
            'AE': {
                'dubai': '00000'
            },
            'SG': {
                'singapore': '018989'
            },
            'CN': {
                'shanghai': '200000',
                'beijing': '100000'
            },
            'HK': {
                'hong kong': '999077'
            },
            'JP': {
                'tokyo': '100-0001',
                'osaka': '530-0001'
            },
            'AU': {
                'sydney': '2000',
                'melbourne': '3000'
            },
            'NL': {
                'rotterdam': '3011',
                'amsterdam': '1012'
            },
            'IN': {
                'mumbai': '400001',
                'delhi': '110001'
            },
            'BR': {
                'santos': '11010',
                'sao paulo': '01310'
            },
            'ZA': {
                'cape town': '8001',
                'johannesburg': '2000'
            },
            'BE': {
                'antwerp': '2000',
                'brussels': '1000'
            },
            'KR': {
                'busan': '48900',
                'seoul': '04500'
            },
            'TW': {
                'kaohsiung': '804',
                'taipei': '100'
            }
        }
        
        city_lower = city.lower().strip()
        country_postal = postal_codes.get(country_code, {})
        return country_postal.get(city_lower, '00000')

    def _extract_city_from_port(self, port_name: str) -> str:
        """Extract city name from port description."""
        # Clean up port names to extract actual city
        port_name = port_name.lower().strip()
        
        # Remove common port prefixes/suffixes
        prefixes_to_remove = ['port of ', 'port ', 'airport ', 'terminal ']
        suffixes_to_remove = [' port', ' terminal', ' airport', ' hub', ' depot']
        
        for prefix in prefixes_to_remove:
            if port_name.startswith(prefix):
                port_name = port_name[len(prefix):]
                
        for suffix in suffixes_to_remove:
            if port_name.endswith(suffix):
                port_name = port_name[:-len(suffix)]
        
        # Handle special cases
        special_cases = {
            'jebel ali': 'dubai',
            'changi': 'singapore',
            'pearson': 'toronto',
            'yvr': 'vancouver',
            'lax': 'los angeles',
            'jfk': 'new york',
            'lhr': 'london',
            'nrt': 'tokyo',
            'hkg': 'hong kong',
            'fra': 'frankfurt',
            'cdg': 'paris',
            'ams': 'amsterdam',
            'dxb': 'dubai',
            'sin': 'singapore'
        }
        
        return special_cases.get(port_name, port_name).title()

    def _fetch_dhl_rates(self, origin_country: str, origin_city: str, origin_postal: str,
                        dest_country: str, dest_city: str, dest_postal: str) -> List[Dict]:
        """Fetch shipping rates from DHL Express API."""
        if not self.api_key:
            return []
            
        session = self._get_session()
        url = f"{self.BASE_URL}/mydhlapi/rates"
        
        # Calculate future ship date
        ship_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Build DHL API request payload
        payload = {
            "customerDetails": {
                "shipperDetails": {
                    "postalCode": origin_postal,
                    "cityName": origin_city,
                    "countryCode": origin_country,
                    "provinceCode": "",
                    "addressLine1": "Sample Address"
                },
                "receiverDetails": {
                    "postalCode": dest_postal,
                    "cityName": dest_city,
                    "countryCode": dest_country,
                    "provinceCode": "",
                    "addressLine1": "Sample Address"
                }
            },
            "accounts": [{
                "typeCode": "shipper",
                "number": "123456789"  # Would be customer account number
            }],
            "plannedShippingDateAndTime": f"{ship_date}T10:00:00GMT+01:00",
            "unitOfMeasurement": "metric",
            "isCustomsDeclarable": True,
            "monetaryAmount": [
                {
                    "typeCode": "declared",
                    "value": 1000,
                    "currency": "USD"
                }
            ],
            "packages": [
                {
                    "typeCode": "2BP",  # DHL Flyer
                    "weight": 10.5,
                    "dimensions": {
                        "length": 40,
                        "width": 30,
                        "height": 15
                    }
                }
            ],
            "getAdditionalInformation": [
                "TRANSIT_TIMES",
                "PICKUP_DETAILS", 
                "DELIVERY_DETAILS"
            ],
            "returnStandardProductsOnly": False,
            "nextBusinessDay": False
        }
        
        try:
            logger.info(f"Requesting DHL rates from {origin_city}, {origin_country} to {dest_city}, {dest_country}")
            resp = session.post(url, json=payload, timeout=15)
            
            if resp.status_code == 200:
                data = resp.json()
                products = data.get('products', [])
                logger.info(f"Found {len(products)} DHL service options")
                return products
            elif resp.status_code == 422:
                # Validation error - try simplified request
                logger.warning(f"DHL API validation error, trying simplified request: {resp.text[:200]}")
                return self._fetch_simplified_dhl_rates(session, origin_country, dest_country)
            else:
                logger.warning(f"DHL API error {resp.status_code}: {resp.text[:500]}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching DHL rates: {e}")
            return []

    def _fetch_simplified_dhl_rates(self, session: requests.Session, origin_country: str, dest_country: str) -> List[Dict]:
        """Simplified DHL rate request when detailed request fails."""
        url = f"{session.headers.get('base_url', self.BASE_URL)}/mydhlapi/rates"
        
        # Simplified payload with minimal required fields
        payload = {
            "customerDetails": {
                "shipperDetails": {
                    "countryCode": origin_country,
                    "cityName": "City",
                    "postalCode": "00000"
                },
                "receiverDetails": {
                    "countryCode": dest_country, 
                    "cityName": "City",
                    "postalCode": "00000"
                }
            },
            "accounts": [{
                "typeCode": "shipper"
            }],
            "plannedShippingDateAndTime": (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT10:00:00GMT+01:00'),
            "unitOfMeasurement": "metric",
            "isCustomsDeclarable": origin_country != dest_country,
            "packages": [{
                "typeCode": "2BP",
                "weight": 10.0,
                "dimensions": {"length": 30, "width": 20, "height": 10}
            }]
        }
        
        try:
            resp = session.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('products', [])
            else:
                logger.warning(f"Simplified DHL request also failed: {resp.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error with simplified DHL request: {e}")
            return []

    def _parse_dhl_product(self, product: Dict, origin_city: str, dest_city: str, 
                          origin_country: str, dest_country: str) -> CarrierRouteOption:
        """Parse DHL product response into CarrierRouteOption."""
        try:
            # Extract product info
            product_name = product.get('productName', 'DHL Express')
            product_code = product.get('productCode', '')
            
            # Extract pricing
            total_prices = product.get('totalPrice', [])
            cost_usd = 0.0
            if total_prices:
                price_info = total_prices[0]
                cost_usd = float(price_info.get('price', 0))
                currency = price_info.get('priceCurrency', 'USD')
                
                # Convert to USD if needed (simplified)
                if currency != 'USD':
                    # Apply rough conversion rates - in production, use real exchange rates
                    conversion_rates = {
                        'EUR': 1.1, 'GBP': 1.25, 'CAD': 0.75, 'AUD': 0.65,
                        'JPY': 0.007, 'CNY': 0.14, 'INR': 0.012, 'SGD': 0.74
                    }
                    cost_usd *= conversion_rates.get(currency, 1.0)
            
            # Extract delivery capabilities
            delivery_caps = product.get('deliveryCapabilities', {})
            delivery_date = delivery_caps.get('estimatedDeliveryDateAndTime')
            delivery_type = delivery_caps.get('deliveryTypeCode', '')
            
            # Calculate transit time
            duration_hours = None
            if delivery_date:
                try:
                    ship_date = datetime.now() + timedelta(days=1)
                    delivery_dt = datetime.fromisoformat(delivery_date.replace('Z', '+00:00'))
                    duration_hours = (delivery_dt - ship_date).total_seconds() / 3600
                except Exception:
                    # Fallback: estimate based on service type
                    if 'EXPRESS' in product_name.upper():
                        if origin_country == dest_country:
                            duration_hours = 24  # Domestic express
                        else:
                            duration_hours = 48  # International express
                    else:
                        duration_hours = 72  # Standard service
            
            # Create waypoints (DHL is typically point-to-point with hub routing)
            waypoints = [
                {
                    'lat': self._get_city_coordinates(origin_city, origin_country)[0],
                    'lon': self._get_city_coordinates(origin_city, origin_country)[1],
                    'name': f"{origin_city}, {origin_country}",
                    'type': 'origin',
                    'city': origin_city,
                    'country': origin_country
                }
            ]
            
            # Add intermediate hub if international
            if origin_country != dest_country:
                hub_info = self._get_dhl_hub(origin_country, dest_country)
                if hub_info:
                    waypoints.append({
                        'lat': hub_info['lat'],
                        'lon': hub_info['lon'],
                        'name': f"DHL Hub - {hub_info['city']}",
                        'type': 'hub',
                        'city': hub_info['city'],
                        'country': hub_info['country']
                    })
            
            # Add destination
            waypoints.append({
                'lat': self._get_city_coordinates(dest_city, dest_country)[0],
                'lon': self._get_city_coordinates(dest_city, dest_country)[1], 
                'name': f"{dest_city}, {dest_country}",
                'type': 'destination',
                'city': dest_city,
                'country': dest_country
            })
            
            # Calculate total distance
            total_distance = 0
            for i in range(len(waypoints) - 1):
                total_distance += self._calculate_distance(
                    waypoints[i]['lat'], waypoints[i]['lon'],
                    waypoints[i+1]['lat'], waypoints[i+1]['lon']
                )
            
            # Estimate carbon emissions (air freight: ~500-900g CO2/kg per km)
            # DHL is generally more efficient, use lower end
            carbon_emissions_kg = total_distance * 0.52  # 520g CO2 per km
            
            # Risk score based on service type and route
            base_risk = 0.1
            if 'EXPRESS' in product_name.upper():
                base_risk = 0.05  # Express services are more reliable
            if origin_country != dest_country:
                base_risk += 0.1  # International adds complexity
                
            risk_score = min(0.9, base_risk + (len(waypoints) - 2) * 0.05)
            
            # Extract additional service details
            pickup_details = product.get('pickupCapabilities', {})
            delivery_details = product.get('deliveryCapabilities', {})
            
            # Create route name with service info
            route_name = f"DHL {product_name}"
            if product_code:
                route_name += f" ({product_code})"
            
            return CarrierRouteOption(
                name=route_name,
                waypoints=waypoints,
                distance_km=total_distance,
                duration_hours=duration_hours,
                cost_usd=cost_usd,
                carbon_emissions_kg=carbon_emissions_kg,
                risk_score=risk_score,
                metadata={
                    'provider': 'dhl',
                    'product_code': product_code,
                    'product_name': product_name,
                    'delivery_date': delivery_date,
                    'delivery_type': delivery_type,
                    'service_type': 'express' if 'EXPRESS' in product_name.upper() else 'standard',
                    'currency': total_prices[0].get('priceCurrency') if total_prices else 'USD',
                    'original_price': total_prices[0].get('price') if total_prices else 0,
                    'pickup_details': pickup_details,
                    'delivery_details': delivery_details,
                    'international': origin_country != dest_country,
                    'risk_factors': ['customs', 'weather'] if origin_country != dest_country else ['weather']
                }
            )
            
        except Exception as e:
            logger.error(f"Error parsing DHL product: {e}")
            # Return a fallback route option
            return self._create_fallback_dhl_route(origin_city, dest_city, origin_country, dest_country)

    def _get_city_coordinates(self, city: str, country_code: str) -> tuple:
        """Get approximate coordinates for cities."""
        city_coords = {
            'CA': {
                'vancouver': (49.2827, -123.1207),
                'toronto': (43.6532, -79.3832),
                'montreal': (45.5017, -73.5673),
                'halifax': (44.6488, -63.5752)
            },
            'US': {
                'los angeles': (34.0522, -118.2437),
                'new york': (40.7128, -74.0060),
                'chicago': (41.8781, -87.6298),
                'miami': (25.7617, -80.1918)
            },
            'GB': {
                'london': (51.5074, -0.1278),
                'manchester': (53.4808, -2.2426),
                'felixstowe': (51.9540, 1.3528)
            },
            'DE': {
                'hamburg': (53.5511, 9.9937),
                'berlin': (52.5200, 13.4050),
                'frankfurt': (50.1109, 8.6821)
            },
            'AE': {
                'dubai': (25.2769, 55.2962)
            },
            'SG': {
                'singapore': (1.3521, 103.8198)
            },
            'CN': {
                'shanghai': (31.2304, 121.4737),
                'beijing': (39.9042, 116.4074)
            },
            'HK': {
                'hong kong': (22.3193, 114.1694)
            },
            'JP': {
                'tokyo': (35.6762, 139.6503),
                'osaka': (34.6937, 135.5023)
            },
            'AU': {
                'sydney': (-33.8688, 151.2093),
                'melbourne': (-37.8136, 144.9631)
            },
            'NL': {
                'rotterdam': (51.9244, 4.4777),
                'amsterdam': (52.3676, 4.9041)
            },
            'IN': {
                'mumbai': (19.0760, 72.8777),
                'delhi': (28.7041, 77.1025)
            },
            'BR': {
                'santos': (-23.9618, -46.3322),
                'sao paulo': (-23.5505, -46.6333)
            },
            'ZA': {
                'cape town': (-33.9249, 18.4241),
                'johannesburg': (-26.2041, 28.0473)
            },
            'BE': {
                'antwerp': (51.2993, 4.4014),
                'brussels': (50.8503, 4.3517)
            },
            'KR': {
                'busan': (35.1796, 129.0756),
                'seoul': (37.5665, 126.9780)
            },
            'TW': {
                'kaohsiung': (22.6273, 120.3014),
                'taipei': (25.0330, 121.5654)
            }
        }
        
        country_cities = city_coords.get(country_code, {})
        return country_cities.get(city.lower(), (0.0, 0.0))

    def _get_dhl_hub(self, origin_country: str, dest_country: str) -> Optional[Dict]:
        """Get DHL hub information for international routes."""
        # Major DHL hubs by region
        hubs = {
            # European hub
            'DE': {'city': 'Leipzig', 'country': 'DE', 'lat': 51.3397, 'lon': 12.3731},
            # Americas hub  
            'US': {'city': 'Cincinnati', 'country': 'US', 'lat': 39.1031, 'lon': -84.5120},
            # Asia-Pacific hub
            'HK': {'city': 'Hong Kong', 'country': 'HK', 'lat': 22.3193, 'lon': 114.1694},
            # Middle East hub
            'AE': {'city': 'Dubai', 'country': 'AE', 'lat': 25.2769, 'lon': 55.2962}
        }
        
        # Regional mapping
        region_mapping = {
            'Europe': ['DE', 'GB', 'NL', 'BE', 'FR', 'IT', 'ES', 'AT', 'CH'],
            'Americas': ['US', 'CA', 'MX', 'BR', 'AR', 'CL'],
            'Asia': ['CN', 'JP', 'KR', 'TW', 'SG', 'TH', 'MY', 'IN', 'AU', 'NZ'],
            'Middle East': ['AE', 'SA', 'QA', 'KW', 'BH', 'OM'],
            'Africa': ['ZA', 'EG', 'NG', 'KE', 'MA']
        }
        
        def get_region(country):
            for region, countries in region_mapping.items():
                if country in countries:
                    return region
            return 'Other'
        
        origin_region = get_region(origin_country)
        dest_region = get_region(dest_country)
        
        # If same region, no hub needed
        if origin_region == dest_region:
            return None
            
        # Select hub based on route
        if origin_region == 'Americas' or dest_region == 'Americas':
            return hubs['US']
        elif origin_region == 'Asia' or dest_region == 'Asia':
            return hubs['HK']
        elif origin_region == 'Middle East' or dest_region == 'Middle East':
            return hubs['AE']
        else:
            return hubs['DE']  # Default to European hub

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in kilometers."""
        if not all([lat1, lon1, lat2, lon2]):
            return 0
            
        # Haversine formula
        R = 6371  # Earth's radius in km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c

    def _create_fallback_dhl_route(self, origin_city: str, dest_city: str, 
                                  origin_country: str, dest_country: str) -> CarrierRouteOption:
        """Create fallback route when API parsing fails."""
        origin_coords = self._get_city_coordinates(origin_city, origin_country)
        dest_coords = self._get_city_coordinates(dest_city, dest_country)
        
        waypoints = [
            {
                'lat': origin_coords[0], 'lon': origin_coords[1],
                'name': f"{origin_city}, {origin_country}", 'type': 'origin'
            },
            {
                'lat': dest_coords[0], 'lon': dest_coords[1],
                'name': f"{dest_city}, {dest_country}", 'type': 'destination'
            }
        ]
        
        distance = self._calculate_distance(
            origin_coords[0], origin_coords[1], dest_coords[0], dest_coords[1]
        )
        
        # Estimate cost with distance-based tiers (long-haul express costs more per km)
        if distance > 7000:
            rate = 5.0  # intercontinental premium
        elif distance > 4000:
            rate = 4.0
        else:
            rate = 3.0
        cost_usd = max(50, distance * rate)
        
        return CarrierRouteOption(
            name="DHL Express (Fallback)",
            waypoints=waypoints,
            distance_km=distance,
            duration_hours=48.0,  # 2 days fallback
            cost_usd=cost_usd,
            carbon_emissions_kg=distance * 0.52,
            risk_score=0.15,
            metadata={
                'provider': 'dhl',
                'product_code': 'FALLBACK',
                'service_type': 'express',
                'fallback': True,
                'risk_factors': ['api_unavailable']
            }
        )

    def fetch_routes(self, shipment) -> List[CarrierRouteOption]:
        """Fetch route options from DHL Express API."""
        if not self.api_key:
            logger.warning("No DHL API key configured")
            return []
            
        if not (shipment.origin_port and shipment.destination_port):
            logger.warning("Missing origin or destination port")
            return []
        
        try:
            # Extract city names and determine country codes
            origin_city = self._extract_city_from_port(shipment.origin_port)
            dest_city = self._extract_city_from_port(shipment.destination_port)
            
            # Use shipment country info if available, otherwise detect from city
            origin_country = getattr(shipment, 'origin_country', None)
            if not origin_country:
                origin_country = self._standardize_country_code(origin_city)
                
            dest_country = getattr(shipment, 'destination_country', None)
            if not dest_country:
                dest_country = self._standardize_country_code(dest_city)
            
            # Get postal codes
            origin_postal = self._get_postal_code(origin_city, origin_country)
            dest_postal = self._get_postal_code(dest_city, dest_country)
            
            logger.info(f"Fetching DHL routes: {origin_city}, {origin_country} -> {dest_city}, {dest_country}")
            
            # Fetch DHL service options
            products = self._fetch_dhl_rates(
                origin_country, origin_city, origin_postal,
                dest_country, dest_city, dest_postal
            )
            
            # Parse into route options
            route_options = []
            for product in products:
                try:
                    route_option = self._parse_dhl_product(
                        product, origin_city, dest_city, origin_country, dest_country
                    )
                    route_options.append(route_option)
                except Exception as e:
                    logger.error(f"Error parsing DHL product: {e}")
                    continue
            
            # If no products, create fallback route
            if not route_options:
                logger.info("No DHL products found, creating fallback route")
                fallback_route = self._create_fallback_dhl_route(
                    origin_city, dest_city, origin_country, dest_country
                )
                route_options = [fallback_route]
            
            # Sort by cost (ascending)
            route_options.sort(key=lambda r: r.cost_usd)
            
            # Limit to reasonable number
            route_options = route_options[:8]
            
            logger.info(f"Found {len(route_options)} DHL route options")
            return route_options
            
        except Exception as e:
            logger.error(f"Error fetching DHL routes: {e}")
            # Return fallback route on any error
            try:
                origin_city = self._extract_city_from_port(shipment.origin_port)
                dest_city = self._extract_city_from_port(shipment.destination_port)
                origin_country = self._standardize_country_code(origin_city)
                dest_country = self._standardize_country_code(dest_city)
                
                fallback = self._create_fallback_dhl_route(
                    origin_city, dest_city, origin_country, dest_country
                )
                return [fallback]
            except Exception:
                return []


class FedExCarrierProvider(CarrierRouteProvider):
    """FedEx Express/Ground integration with intelligent fallback routes.
    
    Note: This implementation provides intelligent synthetic routes when full
    API access is not available. It generates realistic FedEx routes based on
    service areas, transit times, and pricing models.
    
    For full API integration, requires:
    - FedEx Developer Portal account (developer.fedex.com)
    - OAuth 2.0 client credentials (client_id + client_secret)
    - FedEx account number for rate quotes
    """
    
    BASE_URL = "https://apis.fedex.com"
    SANDBOX_URL = "https://apis-sandbox.fedex.com"
    
    def __init__(self):
        cfg_key = getattr(current_app.config, 'FEDEX_API_KEY', None) if current_app else None
        self.api_key = cfg_key or os.getenv('FEDEX_API_KEY')
        self.client_id = os.getenv('FEDEX_CLIENT_ID')
        self.client_secret = os.getenv('FEDEX_CLIENT_SECRET')
        self.account_number = os.getenv('FEDEX_ACCOUNT_NUMBER')
        
        # Check if we have proper API credentials
        self.has_full_api_access = bool(self.client_id and self.client_secret)
        
        if not self.api_key:
            logger.warning("FEDEX_API_KEY not configured; using fallback routes only.")
        if not self.has_full_api_access:
            logger.info("FedEx using intelligent fallback routes (OAuth credentials not configured)")
        else:
            logger.info("FedEx ready for full API integration")

    def _get_city_coordinates(self, city: str, country_code: str = 'US') -> tuple:
        """Get coordinates for major cities in FedEx service areas."""
        # FedEx major hubs and service centers
        fedex_locations = {
            'US': {
                'memphis': (35.1495, -90.0490),  # FedEx World Hub
                'indianapolis': (39.7391, -86.1340),  # FedEx Express Hub
                'oakland': (37.7749, -122.4194),  # West Coast Hub
                'newark': (40.7282, -74.1776),  # Newark Hub
                'fort worth': (32.7555, -97.3308),  # Alliance Airport Hub
                'los angeles': (34.0522, -118.2437),
                'new york': (40.7128, -74.0060),
                'chicago': (41.8781, -87.6298),
                'atlanta': (33.7490, -84.3880),
                'dallas': (32.7767, -96.7970),
                'houston': (29.7604, -95.3698),
                'phoenix': (33.4484, -112.0740),
                'philadelphia': (39.9526, -75.1652),
                'san antonio': (29.4241, -98.4936),
                'san diego': (32.7157, -117.1611),
                'denver': (39.7392, -104.9903),
                'seattle': (47.6062, -122.3321),
                'boston': (42.3601, -71.0589),
                'miami': (25.7617, -80.1918),
                'las vegas': (36.1699, -115.1398)
            },
            'CA': {
                'toronto': (43.6532, -79.3832),
                'vancouver': (49.2827, -123.1207),
                'montreal': (45.5017, -73.5673),
                'calgary': (51.0447, -114.0719),
                'ottawa': (45.4215, -75.6972),
                'winnipeg': (49.8951, -97.1384)
            },
            'MX': {
                'mexico city': (19.4326, -99.1332),
                'guadalajara': (20.6597, -103.3496),
                'monterrey': (25.6866, -100.3161)
            },
            'GB': {
                'london': (51.5074, -0.1278),
                'manchester': (53.4808, -2.2426),
                'birmingham': (52.4862, -1.8904),
                'stansted': (51.8860, 0.2389)  # FedEx European Hub
            },
            'DE': {
                'cologne': (50.9375, 6.9603),  # FedEx European Hub
                'frankfurt': (50.1109, 8.6821),
                'berlin': (52.5200, 13.4050),
                'hamburg': (53.5511, 9.9937)
            },
            'FR': {
                'paris': (48.8566, 2.3522),
                'lyon': (45.7640, 4.8357),
                'marseille': (43.2965, 5.3698),
                'charles de gaulle': (49.0097, 2.5479)  # CDG Hub
            },
            'CN': {
                'guangzhou': (23.1291, 113.2644),  # FedEx Asia Pacific Hub
                'shanghai': (31.2304, 121.4737),
                'beijing': (39.9042, 116.4074),
                'shenzhen': (22.5431, 114.0579)
            },
            'JP': {
                'tokyo': (35.6762, 139.6503),
                'osaka': (34.6937, 135.5023),
                'nagoya': (35.1815, 136.9066)
            },
            'AU': {
                'sydney': (-33.8688, 151.2093),
                'melbourne': (-37.8136, 144.9631),
                'brisbane': (-27.4698, 153.0251),
                'perth': (-31.9505, 115.8605)
            },
            'BR': {
                'sao paulo': (-23.5505, -46.6333),
                'rio de janeiro': (-22.9068, -43.1729),
                'brasilia': (-15.8267, -47.9218)
            },
            'IN': {
                'mumbai': (19.0760, 72.8777),
                'delhi': (28.7041, 77.1025),
                'bangalore': (12.9716, 77.5946),
                'chennai': (13.0827, 80.2707)
            }
        }
        
        city_lower = city.lower().strip()
        country_cities = fedex_locations.get(country_code, {})
        
        # Try exact match first
        if city_lower in country_cities:
            return country_cities[city_lower]
        
        # Try partial matches
        for city_key, coords in country_cities.items():
            if city_lower in city_key or city_key in city_lower:
                return coords
        
        # Fallback to US locations if not found
        if country_code != 'US':
            us_cities = fedex_locations.get('US', {})
            for city_key, coords in us_cities.items():
                if city_lower in city_key or city_key in city_lower:
                    return coords
        
        # Ultimate fallback
        return (0.0, 0.0)

    def _standardize_country_code(self, location: str) -> str:
        """Convert location to ISO country code."""
        location_lower = location.lower().strip()
        
        country_mapping = {
            # Major cities to countries
            'los angeles': 'US', 'new york': 'US', 'chicago': 'US', 
            'atlanta': 'US', 'dallas': 'US', 'houston': 'US', 'miami': 'US',
            'boston': 'US', 'seattle': 'US', 'denver': 'US', 'phoenix': 'US',
            'las vegas': 'US', 'san francisco': 'US', 'memphis': 'US',
            'toronto': 'CA', 'vancouver': 'CA', 'montreal': 'CA', 'calgary': 'CA',
            'london': 'GB', 'manchester': 'GB', 'birmingham': 'GB',
            'paris': 'FR', 'lyon': 'FR', 'marseille': 'FR',
            'berlin': 'DE', 'frankfurt': 'DE', 'cologne': 'DE', 'hamburg': 'DE',
            'tokyo': 'JP', 'osaka': 'JP', 'nagoya': 'JP',
            'sydney': 'AU', 'melbourne': 'AU', 'brisbane': 'AU', 'perth': 'AU',
            'mumbai': 'IN', 'delhi': 'IN', 'bangalore': 'IN', 'chennai': 'IN',
            'shanghai': 'CN', 'beijing': 'CN', 'guangzhou': 'CN', 'shenzhen': 'CN',
            'sao paulo': 'BR', 'rio de janeiro': 'BR', 'brasilia': 'BR',
            # Country names
            'united states': 'US', 'usa': 'US', 'america': 'US',
            'canada': 'CA', 'united kingdom': 'GB', 'uk': 'GB', 'britain': 'GB',
            'germany': 'DE', 'france': 'FR', 'japan': 'JP', 'australia': 'AU',
            'india': 'IN', 'china': 'CN', 'brazil': 'BR', 'mexico': 'MX'
        }
        
        # Try exact match
        if location_lower in country_mapping:
            return country_mapping[location_lower]
        
        # Try partial matches
        for key, country in country_mapping.items():
            if key in location_lower or location_lower in key:
                return country
        
        # If starts with 2-letter code, assume it's already a country code
        if len(location_lower) == 2 and location_lower.isalpha():
            return location_lower.upper()
        
        # Default to US (FedEx's primary market)
        return 'US'

    def _extract_city_from_port(self, port_name: str) -> str:
        """Extract city name from port/location description."""
        port_name = port_name.lower().strip()
        
        # Remove common prefixes/suffixes
        prefixes = ['port of ', 'port ', 'airport ', 'hub ', 'terminal ']
        suffixes = [' port', ' terminal', ' airport', ' hub', ' depot', ' international']
        
        for prefix in prefixes:
            if port_name.startswith(prefix):
                port_name = port_name[len(prefix):]
                
        for suffix in suffixes:
            if port_name.endswith(suffix):
                port_name = port_name[:-len(suffix)]
        
        # Handle special cases and airport codes
        special_cases = {
            'lax': 'los angeles', 'jfk': 'new york', 'ord': 'chicago',
            'atl': 'atlanta', 'dfw': 'dallas', 'den': 'denver',
            'sea': 'seattle', 'bos': 'boston', 'mia': 'miami',
            'lhr': 'london', 'cdg': 'paris', 'fra': 'frankfurt',
            'nrt': 'tokyo', 'pvg': 'shanghai', 'can': 'guangzhou',
            'syd': 'sydney', 'mel': 'melbourne', 'bom': 'mumbai',
            'del': 'delhi', 'gru': 'sao paulo', 'yyz': 'toronto',
            'yvr': 'vancouver', 'mem': 'memphis', 'ind': 'indianapolis'
        }
        
        return special_cases.get(port_name, port_name).title()

    def _get_fedex_service_types(self, origin_country: str, dest_country: str, 
                                distance_km: float) -> List[Dict[str, Any]]:
        """Get appropriate FedEx service types for the route."""
        services = []
        
        is_domestic = origin_country == dest_country
        is_short_distance = distance_km < 800  # roughly same day/overnight range
        is_medium_distance = 800 <= distance_km < 2400  # 2-3 day range
        
        if is_domestic:
            if is_short_distance:
                services.extend([
                    {
                        'code': 'FEDEX_EXPRESS_SAVER',
                        'name': 'FedEx Express Saver',
                        'transit_hours': 48,
                        'cost_multiplier': 1.8,
                        'type': 'express'
                    },
                    {
                        'code': 'FEDEX_2_DAY',
                        'name': 'FedEx 2Day',
                        'transit_hours': 48,
                        'cost_multiplier': 1.5,
                        'type': 'express'
                    }
                ])
                
                # Same day for very short distances in major cities
                if distance_km < 200 and origin_country == 'US':
                    services.append({
                        'code': 'FEDEX_SAME_DAY',
                        'name': 'FedEx SameDay',
                        'transit_hours': 6,
                        'cost_multiplier': 4.0,
                        'type': 'same_day'
                    })
            
            # Standard overnight for domestic
            if origin_country in ['US', 'CA', 'GB', 'DE', 'FR']:
                services.append({
                    'code': 'STANDARD_OVERNIGHT',
                    'name': 'FedEx Standard Overnight',
                    'transit_hours': 24,
                    'cost_multiplier': 2.2,
                    'type': 'overnight'
                })
            
            # Ground service for domestic shipments
            if is_medium_distance:
                ground_hours = min(168, max(24, distance_km / 400 * 24))  # 1-7 days based on distance
                services.append({
                    'code': 'FEDEX_GROUND',
                    'name': 'FedEx Ground',
                    'transit_hours': ground_hours,
                    'cost_multiplier': 0.8,
                    'type': 'ground'
                })
        else:
            # International services
            services.extend([
                {
                    'code': 'INTERNATIONAL_PRIORITY',
                    'name': 'FedEx International Priority',
                    'transit_hours': 72,  # 3 business days
                    'cost_multiplier': 3.5,
                    'type': 'international_express'
                },
                {
                    'code': 'INTERNATIONAL_ECONOMY',
                    'name': 'FedEx International Economy',
                    'transit_hours': 120,  # 5 business days
                    'cost_multiplier': 2.8,
                    'type': 'international_economy'
                }
            ])
            
            # Priority overnight for short international (US-CA, EU internal)
            if ((origin_country in ['US', 'CA'] and dest_country in ['US', 'CA']) or
                (origin_country in ['GB', 'DE', 'FR', 'NL', 'BE'] and 
                 dest_country in ['GB', 'DE', 'FR', 'NL', 'BE'])):
                services.append({
                    'code': 'INTERNATIONAL_PRIORITY_EXPRESS',
                    'name': 'FedEx International Priority Express',
                    'transit_hours': 48,
                    'cost_multiplier': 4.2,
                    'type': 'international_express'
                })
        
        return services

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points using Haversine formula."""
        if not all([lat1, lon1, lat2, lon2]):
            return 0
            
        R = 6371  # Earth's radius in km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c

    def _estimate_fedex_cost(self, distance_km: float, service_type: Dict[str, Any], 
                           origin_country: str, dest_country: str) -> float:
        """Estimate FedEx shipping cost based on distance and service type."""
        # Base cost factors (per km)
        base_rates = {
            'same_day': 8.0,      # Very expensive for same day
            'overnight': 4.5,     # Express overnight
            'express': 3.2,       # Express services
            'international_express': 5.5,  # International express
            'international_economy': 3.8,  # International economy
            'ground': 1.8         # Ground services
        }
        
        service_category = service_type.get('type', 'express')
        base_rate = base_rates.get(service_category, 3.0)
        
        # Distance-based cost
        distance_cost = distance_km * base_rate
        
        # Apply service multiplier
        multiplier = service_type.get('cost_multiplier', 1.0)
        total_cost = distance_cost * multiplier
        
        # Minimum costs by service type
        minimums = {
            'same_day': 200,
            'overnight': 75,
            'express': 50,
            'international_express': 100,
            'international_economy': 80,
            'ground': 25
        }
        
        minimum_cost = minimums.get(service_category, 50)
        
        # Country-specific adjustments
        country_multipliers = {
            ('US', 'US'): 1.0,     # Domestic US baseline
            ('CA', 'CA'): 1.1,     # Domestic Canada
            ('US', 'CA'): 1.3, ('CA', 'US'): 1.3,  # US-Canada
            ('GB', 'GB'): 1.2,     # Domestic UK
            ('DE', 'DE'): 1.15,    # Domestic Germany
            ('FR', 'FR'): 1.15,    # Domestic France
        }
        
        country_key = (origin_country, dest_country)
        country_multiplier = country_multipliers.get(country_key, 1.4)  # Default international
        
        final_cost = max(minimum_cost, total_cost * country_multiplier)
        
        # Add fuel surcharge (typical 8-12%)
        fuel_surcharge = final_cost * 0.10
        
        return round(final_cost + fuel_surcharge, 2)

    def _create_fedex_route_option(self, origin_city: str, dest_city: str,
                                  origin_country: str, dest_country: str,
                                  service: Dict[str, Any], distance_km: float) -> CarrierRouteOption:
        """Create a FedEx route option for a specific service."""
        
        # Get coordinates
        origin_coords = self._get_city_coordinates(origin_city, origin_country)
        dest_coords = self._get_city_coordinates(dest_city, dest_country)
        
        # Build waypoints with FedEx hub routing
        waypoints = [
            {
                'lat': origin_coords[0],
                'lon': origin_coords[1],
                'name': f"{origin_city}, {origin_country}",
                'type': 'origin',
                'city': origin_city,
                'country': origin_country
            }
        ]
        
        # Add FedEx hub for long-distance or international shipments
        needs_hub = (distance_km > 1200 or origin_country != dest_country)
        
        if needs_hub:
            # Determine appropriate hub
            hub_info = self._get_fedex_hub(origin_country, dest_country, distance_km)
            if hub_info:
                waypoints.append({
                    'lat': hub_info['lat'],
                    'lon': hub_info['lon'],
                    'name': f"FedEx Hub - {hub_info['city']}",
                    'type': 'hub',
                    'city': hub_info['city'],
                    'country': hub_info['country']
                })
        
        # Add destination
        waypoints.append({
            'lat': dest_coords[0],
            'lon': dest_coords[1],
            'name': f"{dest_city}, {dest_country}",
            'type': 'destination',
            'city': dest_city,
            'country': dest_country
        })
        
        # Calculate actual distance through waypoints
        total_distance = 0
        for i in range(len(waypoints) - 1):
            segment_distance = self._calculate_distance(
                waypoints[i]['lat'], waypoints[i]['lon'],
                waypoints[i+1]['lat'], waypoints[i+1]['lon']
            )
            total_distance += segment_distance
        
        # Use provided distance if waypoint calculation fails
        if total_distance == 0:
            total_distance = distance_km
        
        # Calculate cost and timing
        cost_usd = self._estimate_fedex_cost(total_distance, service, origin_country, dest_country)
        duration_hours = service.get('transit_hours', 72)
        
        # Estimate carbon emissions (air freight: ~600-800g CO2/kg per km)
        # FedEx has sustainability initiatives, use middle range
        carbon_emissions_kg = total_distance * 0.70  # 700g CO2 per km
        
        # Risk score based on service type and route
        base_risk = 0.05  # FedEx is generally reliable
        if service.get('type') == 'ground':
            base_risk = 0.10  # Ground has slightly higher delay risk
        if origin_country != dest_country:
            base_risk += 0.08  # International adds customs/border risk
        if distance_km > 3000:
            base_risk += 0.05  # Very long distances add risk
            
        risk_score = min(0.9, base_risk)
        
        # Create route name
        route_name = service.get('name', 'FedEx Service')
        
        return CarrierRouteOption(
            name=route_name,
            waypoints=waypoints,
            distance_km=total_distance,
            duration_hours=duration_hours,
            cost_usd=cost_usd,
            carbon_emissions_kg=carbon_emissions_kg,
            risk_score=risk_score,
            metadata={
                'provider': 'fedex',
                'service_code': service.get('code'),
                'service_name': service.get('name'),
                'service_type': service.get('type'),
                'international': origin_country != dest_country,
                'hub_routing': needs_hub,
                'estimated_delivery': (datetime.now() + timedelta(hours=duration_hours)).isoformat(),
                'risk_factors': ['weather', 'customs'] if origin_country != dest_country else ['weather'],
                'fallback_route': True,  # Mark as intelligent fallback
                'api_status': 'fallback_mode'
            }
        )

    def _get_fedex_hub(self, origin_country: str, dest_country: str, distance_km: float) -> Optional[Dict]:
        """Get appropriate FedEx hub for routing."""
        # FedEx major hub locations
        hubs = {
            'MEMPHIS': {'city': 'Memphis', 'country': 'US', 'lat': 35.1495, 'lon': -90.0490},  # World Hub
            'INDIANAPOLIS': {'city': 'Indianapolis', 'country': 'US', 'lat': 39.7391, 'lon': -86.1340},
            'OAKLAND': {'city': 'Oakland', 'country': 'US', 'lat': 37.7749, 'lon': -122.4194},
            'NEWARK': {'city': 'Newark', 'country': 'US', 'lat': 40.7282, 'lon': -74.1776},
            'COLOGNE': {'city': 'Cologne', 'country': 'DE', 'lat': 50.9375, 'lon': 6.9603},  # European Hub
            'STANSTED': {'city': 'Stansted', 'country': 'GB', 'lat': 51.8860, 'lon': 0.2389},
            'CHARLES_DE_GAULLE': {'city': 'Paris CDG', 'country': 'FR', 'lat': 49.0097, 'lon': 2.5479},
            'GUANGZHOU': {'city': 'Guangzhou', 'country': 'CN', 'lat': 23.1291, 'lon': 113.2644},  # Asia Pacific Hub
        }
        
        # Regional hub selection logic
        region_hubs = {
            'US_DOMESTIC': ['MEMPHIS', 'INDIANAPOLIS', 'OAKLAND'],
            'US_WEST': ['OAKLAND', 'MEMPHIS'],
            'US_EAST': ['NEWARK', 'INDIANAPOLIS', 'MEMPHIS'],
            'CANADA': ['INDIANAPOLIS', 'MEMPHIS'],
            'EUROPE': ['COLOGNE', 'STANSTED', 'CHARLES_DE_GAULLE'],
            'ASIA': ['GUANGZHOU'],
            'TRANS_ATLANTIC': ['MEMPHIS', 'COLOGNE'],
            'TRANS_PACIFIC': ['OAKLAND', 'GUANGZHOU']
        }
        
        # Determine routing pattern
        if origin_country == dest_country == 'US':
            if distance_km > 2000:  # Cross-country
                return hubs['MEMPHIS']  # World Hub for long US routes
            elif distance_km > 1200:  # Regional
                return hubs['INDIANAPOLIS']  # Central US hub
        elif origin_country == dest_country and origin_country in ['CA']:
            return hubs['MEMPHIS']  # Use US hub for Canadian routes
        elif origin_country in ['US', 'CA'] and dest_country in ['GB', 'DE', 'FR']:
            return hubs['COLOGNE']  # Europe-bound from North America
        elif origin_country in ['GB', 'DE', 'FR'] and dest_country in ['US', 'CA']:
            return hubs['MEMPHIS']  # US-bound from Europe
        elif origin_country in ['US', 'CA'] and dest_country in ['CN', 'JP', 'AU']:
            return hubs['OAKLAND']  # Pacific routes
        elif 'CN' in [origin_country, dest_country] or 'JP' in [origin_country, dest_country]:
            return hubs['GUANGZHOU']  # Asia routes
        
        # Default to Memphis World Hub
        return hubs['MEMPHIS']

    def fetch_routes(self, shipment) -> List[CarrierRouteOption]:
        """Fetch FedEx route options (currently using intelligent fallback)."""
        if not (shipment.origin_port and shipment.destination_port):
            logger.warning("Missing origin or destination port for FedEx")
            return []
        
        try:
            # Extract location information
            origin_city = self._extract_city_from_port(shipment.origin_port)
            dest_city = self._extract_city_from_port(shipment.destination_port)
            
            # Determine country codes
            origin_country = getattr(shipment, 'origin_country', None) or self._standardize_country_code(origin_city)
            dest_country = getattr(shipment, 'destination_country', None) or self._standardize_country_code(dest_city)
            
            logger.info(f"Generating FedEx routes: {origin_city}, {origin_country} -> {dest_city}, {dest_country}")
            
            # Calculate base distance
            origin_coords = self._get_city_coordinates(origin_city, origin_country)
            dest_coords = self._get_city_coordinates(dest_city, dest_country)
            distance_km = self._calculate_distance(
                origin_coords[0], origin_coords[1], dest_coords[0], dest_coords[1]
            )
            
            if distance_km == 0:
                # Fallback distance calculation
                distance_km = self._calculate_distance(
                    shipment.origin_lat or 0, shipment.origin_lon or 0,
                    shipment.destination_lat or 0, shipment.destination_lon or 0
                )
            
            # Get appropriate FedEx services for this route
            services = self._get_fedex_service_types(origin_country, dest_country, distance_km)
            
            if not services:
                logger.warning(f"No FedEx services available for {origin_country} -> {dest_country}")
                return []
            
            # Generate route options for each service
            route_options = []
            for service in services:
                try:
                    route_option = self._create_fedex_route_option(
                        origin_city, dest_city, origin_country, dest_country,
                        service, distance_km
                    )
                    route_options.append(route_option)
                except Exception as e:
                    logger.error(f"Error creating FedEx route for service {service.get('code')}: {e}")
                    continue
            
            # Sort by delivery time (fastest first), then by cost
            route_options.sort(key=lambda r: (r.duration_hours or 999, r.cost_usd))
            
            # Limit to reasonable number of options
            route_options = route_options[:6]
            
            logger.info(f"Generated {len(route_options)} FedEx route options")
            return route_options
            
        except Exception as e:
            logger.error(f"Error generating FedEx routes: {e}")
            return []


def _approx_distance_km(o_lat: float, o_lon: float, d_lat: float, d_lon: float) -> float:
    """Rudimentary distance approximation (Haversine-lite)."""
    import math
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [o_lat, o_lon, d_lat, d_lon])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 1)


def get_multi_carrier_routes(origin: str, destination: str, departure_date: datetime, 
                           carrier_preference: Optional[str] = None,
                           transport_mode: Optional[str] = 'SEA',
                           package_weight: float = 1.0,
                           package_dimensions: Dict[str, float] = None,
                           package_value: float = 10000.0,
                           original_mode: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get routes from all carriers for multi-carrier comparison.
    
    This is the main entry point for multi-carrier route generation.
    It fetches routes from all available carriers and normalizes them
    into a common format for comparison and selection.
    
    Args:
        origin: Origin port/city name
        destination: Destination port/city name  
        departure_date: Planned departure date
        carrier_preference: Preferred carrier (used for current route selection)
        transport_mode: SEA, AIR, or MULTIMODAL
        package_weight: Package weight in kg
        package_dimensions: Package dimensions dict
        package_value: Package value in USD
        
    Returns:
        List of normalized route dictionaries
    """
    logger.info(f"Fetching multi-carrier routes: {origin} -> {destination} (preferred: {carrier_preference})")
    
    all_routes = []
    
    # Create a mock shipment object for carrier providers
    from types import SimpleNamespace
    mock_shipment = SimpleNamespace(
        origin_port=origin,
        destination_port=destination,
        scheduled_departure=departure_date,
        weight_kg=package_weight,
        weight_tons=package_weight / 1000.0,
        cargo_value_usd=package_value,
        transport_mode=transport_mode or 'SEA',
        carrier=carrier_preference or 'Multi-Carrier',
        origin_country=_determine_country_from_port(origin),
        destination_country=_determine_country_from_port(destination),
        origin_lat=None,  # Will be filled by providers
        origin_lon=None,
        destination_lat=None,
        destination_lon=None,
        risk_score=0.2  # Default risk score for mock shipment
    )
    
    # Add coordinates from known ports
    port_coords = _get_port_coordinates()
    origin_coords = port_coords.get(origin.lower())
    dest_coords = port_coords.get(destination.lower())
    
    if origin_coords:
        mock_shipment.origin_lat, mock_shipment.origin_lon = origin_coords
    if dest_coords:
        mock_shipment.destination_lat, mock_shipment.destination_lon = dest_coords
    
    # List of carriers to try
    carriers_to_try = ['maersk', 'dhl', 'fedex']
    
    for carrier in carriers_to_try:
        try:
            logger.info(f"Fetching routes from {carrier}")
            provider = CarrierRouteProvider.for_carrier(carrier)
            carrier_routes = provider.fetch_routes(mock_shipment)
            
            logger.info(f"Got {len(carrier_routes)} routes from {carrier}")
            
            # Convert to normalized format
            for route_option in carrier_routes:
                normalized_route = _normalize_route_to_dict(route_option, carrier)
                all_routes.append(normalized_route)
                
        except Exception as e:
            logger.error(f"Error fetching routes from {carrier}: {e}")
            continue
    
    # Filter by transport mode if specified
    if transport_mode and transport_mode != 'MULTIMODAL':
        filtered_routes = []
        for route in all_routes:
            route_modes = route.get('transport_modes', [transport_mode])
            if transport_mode in route_modes or _mode_matches(route.get('service_type', ''), transport_mode):
                filtered_routes.append(route)
        all_routes = filtered_routes
    
    # If user requested AIR for a Maersk shipment, synthesize a Maersk Air option when missing
    try:
        want_air = (original_mode or transport_mode or '').upper() == 'AIR'
        has_maersk_air = any(r for r in all_routes if r.get('carrier','').lower().startswith('maersk') and 'AIR' in (r.get('transport_modes') or []))
        if want_air and not has_maersk_air:
            # Derive base sea Maersk route to adapt
            base_maersk = next((r for r in all_routes if r.get('carrier','').lower().startswith('maersk')), None)
            if base_maersk:
                air_route = dict(base_maersk)  # shallow copy
                air_route['service_type'] = 'Air Express'
                air_route['service_name'] = 'Maersk Air Express'
                air_route['transport_modes'] = ['AIR']
                # Faster transit (e.g., 1/3 of sea days or minimum 3 days)
                sea_days = base_maersk.get('transit_time_days') or 21
                air_route['transit_time_days'] = max(3, round(sea_days / 3))
                # Higher cost & emissions scaling
                base_cost = base_maersk.get('cost_usd') or 10000
                proposed_cost = base_cost * 1.8
                # Compare with existing air route costs to avoid unrealistic outliers
                existing_air_costs = [r.get('cost_usd') for r in all_routes if 'AIR' in (r.get('transport_modes') or []) and r.get('cost_usd')]
                if existing_air_costs:
                    try:
                        import statistics
                        median_air = statistics.median(existing_air_costs)
                        max_air = max(existing_air_costs)
                        # Cap to at most 1.25x the current maximum air cost (tighter bound) and 1.8x median
                        cap = min(max_air * 1.25, median_air * 1.8)
                        if proposed_cost > cap:
                            proposed_cost = cap
                    except Exception:
                        pass
                air_route['cost_usd'] = round(proposed_cost, 2)
                # Emissions: air typically ~3-6x sea; but if we capped cost, scale emissions proportionally to cost multiplier actually used
                sea_emissions = base_maersk.get('emissions_kg_co2') or 1000
                # Derive actual multiplier applied vs base_cost*1.8
                applied_multiplier = proposed_cost / base_cost if base_cost else 1.8
                emissions_multiplier = min(6.0, max(3.0, applied_multiplier * 3))  # keep within 3x-6x sea emissions
                air_route['emissions_kg_co2'] = round(sea_emissions * emissions_multiplier, 2)
                air_route['confidence_score'] = 'medium'
                air_route['features'] = list(set((base_maersk.get('features') or []) + ['priority_handling']))
                all_routes.append(air_route)
    except Exception as synth_err:
        logger.warning(f"Failed to synthesize Maersk Air route: {synth_err} (non-fatal)")

    # Sort routes by carrier preference, then by cost/time
    all_routes = _sort_routes_by_preference(all_routes, carrier_preference)
    
    logger.info(f"Returning {len(all_routes)} total routes from all carriers")
    return all_routes


def _determine_country_from_port(port_name: str) -> str:
    """Determine country code from port name."""
    port_country_map = {
        'shanghai': 'CN', 'beijing': 'CN', 'hong kong': 'HK',
        'vancouver': 'CA', 'toronto': 'CA', 'montreal': 'CA',
        'los angeles': 'US', 'new york': 'US', 'chicago': 'US', 'miami': 'US',
        'london': 'GB', 'manchester': 'GB', 'felixstowe': 'GB',
        'rotterdam': 'NL', 'amsterdam': 'NL',
        'hamburg': 'DE', 'berlin': 'DE', 'frankfurt': 'DE',
        'paris': 'FR', 'marseille': 'FR',
        'tokyo': 'JP', 'osaka': 'JP',
        'singapore': 'SG',
        'dubai': 'AE',
        'mumbai': 'IN', 'delhi': 'IN',
        'sydney': 'AU', 'melbourne': 'AU',
        'santos': 'BR', 'sao paulo': 'BR'
    }
    
    port_lower = port_name.lower()
    for port_key, country in port_country_map.items():
        if port_key in port_lower or port_lower in port_key:
            return country
    
    return 'US'  # Default


def _get_port_coordinates() -> Dict[str, tuple]:
    """Get coordinates for major ports."""
    return {
        'shanghai': (31.2304, 121.4737),
        'singapore': (1.2966, 103.8060),
        'hong kong': (22.3069, 114.2293),
        'vancouver': (49.2827, -123.1207),
        'los angeles': (33.7553, -118.2769),
        'new york': (40.6936, -74.0447),
        'rotterdam': (51.9225, 4.4792),
        'hamburg': (53.5459, 9.9681),
        'dubai': (25.2769, 55.2962),
        'london': (51.5074, -0.1278),
        'tokyo': (35.6528, 139.8394),
        'mumbai': (19.0760, 72.8777),
        'sydney': (-33.8688, 151.2093)
    }


def _normalize_route_to_dict(route_option, carrier: str) -> Dict[str, Any]:
    """Convert CarrierRouteOption to normalized dictionary format."""
    return {
        'carrier': carrier.title(),
        'service_type': route_option.metadata.get('service_type', 'Standard'),
        'service_name': route_option.name,
        'cost_usd': route_option.cost_usd,
        'transit_time_days': (route_option.duration_hours or 168) / 24,  # Convert to days
        'distance_km': route_option.distance_km,
        'waypoints': route_option.waypoints,
        'estimated_departure': route_option.metadata.get('departure_time'),
        'estimated_arrival': route_option.metadata.get('arrival_time'),
        'confidence_score': route_option.metadata.get('confidence_level', 'high'),
        'emissions_kg_co2': route_option.carbon_emissions_kg,
        'vessel_name': route_option.metadata.get('vessel_name'),
        'vessel_imo': route_option.metadata.get('vessel_imo'),
        'transport_modes': _extract_transport_modes(route_option),
        'risk_factors': route_option.metadata.get('risk_factors', []),
        'features': route_option.metadata.get('features', []),
        'is_estimate': route_option.metadata.get('is_estimate', False),
        'provider_data': route_option.metadata
    }


def _extract_transport_modes(route_option) -> List[str]:
    """Extract transport modes from route option."""
    modes = []
    
    # Check metadata for mode indicators
    service_type = route_option.metadata.get('service_type', '').lower()
    name = route_option.name.lower()
    
    if 'ocean' in name or 'sea' in name or 'vessel' in name or 'maersk' in name:
        modes.append('SEA')
    if 'air' in name or 'express' in name or 'overnight' in name or 'dhl' in name or 'fedex' in name:
        modes.append('AIR')
    if 'ground' in name or 'truck' in name:
        modes.append('GROUND')
    if 'rail' in name or 'train' in name:
        modes.append('RAIL')
    
    # Default to SEA if no modes detected and it's Maersk
    if not modes and 'maersk' in route_option.metadata.get('provider', '').lower():
        modes.append('SEA')
    
    # Default to AIR if no modes detected and it's DHL/FedEx
    if not modes and route_option.metadata.get('provider', '').lower() in ['dhl', 'fedex']:
        modes.append('AIR')
    
    return modes or ['SEA']  # Default to SEA


def _mode_matches(service_type: str, transport_mode: str) -> bool:
    """Check if service type matches transport mode."""
    service_lower = service_type.lower()
    mode_lower = transport_mode.lower()
    
    if mode_lower == 'sea':
        return any(word in service_lower for word in ['ocean', 'sea', 'vessel', 'freight'])
    elif mode_lower == 'air':
        return any(word in service_lower for word in ['air', 'express', 'overnight', 'priority'])
    
    return True  # Default match


def _sort_routes_by_preference(routes: List[Dict], carrier_preference: Optional[str]) -> List[Dict]:
    """Sort routes by carrier preference, then by quality indicators."""
    
    def route_sort_key(route):
        carrier_name = route.get('carrier', '').lower()
        preference_match = 0
        
        # Boost preferred carrier
        if carrier_preference and carrier_preference.lower() in carrier_name:
            preference_match = 1000
        
        # Quality indicators (lower is better for cost/time, higher for confidence)
        cost_score = -(route.get('cost_usd', 999999) / 1000)  # Negative because lower cost is better
        time_score = -(route.get('transit_time_days', 999) * 10)  # Negative because lower time is better
        confidence_map = {'high': 100, 'medium': 50, 'low': 10}
        confidence_score = confidence_map.get(route.get('confidence_score', 'medium'), 50)
        
        # Estimate penalty
        estimate_penalty = -50 if route.get('is_estimate', False) else 0
        
        return preference_match + cost_score + time_score + confidence_score + estimate_penalty
    
    return sorted(routes, key=route_sort_key, reverse=True)

