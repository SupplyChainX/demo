"""
API routes for SupplyChainX
"""
from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
import json
import random
from app import db
from app.api import api_bp
from app.models import (
    Shipment, Alert, Recommendation, PurchaseOrder,
    Supplier, Inventory, Approval, ApprovalStatus,
    AlertSeverity, RecommendationType, ShipmentStatus,
    Route, RouteType
)
from app.integrations.carrier_routes import CarrierRouteProvider, get_multi_carrier_routes
from app.agents.communicator import AgentCommunicator
from app.utils.decorators import rate_limit, audit_action
from app.utils.redis_manager import RedisManager
from app.config import Config

# Local helper replacing legacy Query.get_or_404 to remove SQLAlchemy 2.0 warnings
from flask import abort as _abort
def _get_or_404(model, object_id):
    obj = db.session.get(model, object_id)
    if obj is None:
        _abort(404)
    return obj

@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'SupplyChainX API'
    })

@api_bp.route('/shipments', methods=['GET', 'POST'])
@rate_limit(max_calls=100, time_window=60)
def get_shipments():
    """Get shipments with optional filters."""
    if request.method == 'POST':
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400
            required_fields = ['reference_number', 'origin_port', 'destination_port', 'carrier']
            for field in required_fields:
                field_key = field
                if field == 'reference_number':
                    field_key = 'reference_number'
                if field_key not in data:
                    return jsonify({'error': f'Missing required field: {field}'}), 400
            status_value = 'PLANNED'
            incoming_status = data.get('status') or data.get('shipment_status')
            if incoming_status:
                try:
                    # Convert incoming status to uppercase string
                    status_value = incoming_status.upper()
                except Exception:
                    pass
            risk_score = 0.1
            if 'risk_score' in data:
                try:
                    rs = float(data.get('risk_score'))
                    if 0 <= rs <= 1:
                        risk_score = rs
                except (TypeError, ValueError):
                    pass
            # Use carrier provided (no forcing)
            carrier_value = data.get('carrier') or 'Multi-Carrier'
            # Transport mode (accept from payload, default SEA)
            transport_mode_val = data.get('transport_mode') or data.get('mode') or 'SEA'
            shipment = Shipment(
                workspace_id=1,
                reference_number=data.get('reference_number') or data.get('reference'),
                tracking_number=data.get('reference_number') or data.get('reference'),
                origin_port=data.get('origin_port') or data.get('origin'),
                destination_port=data.get('destination_port') or data.get('destination'),
                carrier=carrier_value,
                status=status_value,
                scheduled_departure=datetime.fromisoformat(data.get('scheduled_departure')) if data.get('scheduled_departure') else None,
                scheduled_arrival=datetime.fromisoformat(data.get('scheduled_arrival')) if data.get('scheduled_arrival') else None,
                risk_score=risk_score,
                description=data.get('description') or data.get('cargo_description'),
                transport_mode=transport_mode_val,
                container_number=data.get('container_number'),
                container_count=int(data.get('container_count')) if data.get('container_count') else None,
                weight_tons=float(data.get('weight_tons')) if data.get('weight_tons') else (float(data.get('weight')) if data.get('weight') else None),
                cargo_value_usd=float(data.get('cargo_value_usd')) if data.get('cargo_value_usd') else (float(data.get('value')) if data.get('value') else None),
                origin_lat=float(data.get('origin_lat')) if data.get('origin_lat') else None,
                origin_lon=float(data.get('origin_lon')) if data.get('origin_lon') else None,
                destination_lat=float(data.get('destination_lat')) if data.get('destination_lat') else None,
                destination_lon=float(data.get('destination_lon')) if data.get('destination_lon') else None
            )
            db.session.add(shipment)
            db.session.commit()

            # Publish creation event for agents/listeners (compat with tests)
            try:
                communicator = AgentCommunicator()
                communicator.publish_message('shipments.created', {
                    'shipment_id': shipment.id,
                    'tracking_number': shipment.tracking_number,
                    'carrier': shipment.carrier,
                    'origin_port': shipment.origin_port,
                    'destination_port': shipment.destination_port,
                    'transport_mode': shipment.transport_mode,
                    'created_at': shipment.created_at.isoformat() if shipment.created_at else datetime.utcnow().isoformat()
                })
            except Exception:
                current_app.logger.debug('Event publish skipped (no Redis)')

            # Generate and save multi-carrier routes synchronously
            try:
                created = 0
                # Generate for supported carriers (Maersk, DHL, FedEx)
                carrier_lc = str(shipment.carrier or '').lower()
                if any(k in carrier_lc for k in ['maersk', 'dhl', 'fedex']):
                    # Always fetch all modes; we'll select current based on shipment.transport_mode
                    routes = get_multi_carrier_routes(
                        origin=shipment.origin_port,
                        destination=shipment.destination_port,
                        departure_date=shipment.scheduled_departure or datetime.utcnow(),
                        carrier_preference=shipment.carrier,
                        transport_mode='MULTIMODAL',
                        package_weight=(shipment.weight_tons or 1.0) * 1000,
                        package_dimensions={'length': 120, 'width': 80, 'height': 60},
                        package_value=shipment.cargo_value_usd or 10000.0,
                        original_mode=shipment.transport_mode
                    )

                    # Business rule: if user requested Maersk and Maersk API failed (yielding only fallback DHL/FedEx)
                    # don't persist alternative carriers automatically (aligns with test expectations).
                    try:
                        if str(shipment.carrier).lower().startswith('maersk'):
                            has_maersk = any((r.get('carrier','') or '').lower().startswith('maersk') for r in routes)
                            if not has_maersk:
                                current_app.logger.info('Suppressing non-Maersk fallback routes after Maersk 4xx/error for shipment %s', shipment.id)
                                routes = []
                    except Exception:
                        pass

                    for idx, route_data in enumerate(routes):
                        try:
                            # Confidence normalization
                            confidence_score = route_data.get('confidence_score', 'medium')
                            if isinstance(confidence_score, str):
                                confidence_map = {'high': 0.9, 'medium': 0.7, 'low': 0.5}
                                confidence_score = confidence_map.get(confidence_score.lower(), 0.7)
                            else:
                                confidence_score = float(confidence_score)

                            # Transport mode to RouteType
                            # Determine route type from route's transport_modes
                            modes = [m.upper() for m in (route_data.get('transport_modes') or [])]
                            route_type_val = None
                            if 'AIR' in modes:
                                route_type_val = RouteType.AIR
                            elif 'SEA' in modes or 'OCEAN' in modes:
                                route_type_val = RouteType.SEA
                            elif 'ROAD' in modes or 'GROUND' in modes:
                                route_type_val = RouteType.ROAD
                            elif 'RAIL' in modes:
                                route_type_val = RouteType.RAIL
                            else:
                                route_type_val = RouteType.MULTIMODAL

                            # Duration hours from transit days
                            transit_days = route_data.get('transit_time_days', 1)
                            duration_hours = float(transit_days) * 24

                            metadata = {
                                'carrier': route_data.get('carrier', 'Unknown'),
                                'service_type': route_data.get('service_type', route_data.get('service_name', 'Standard')),
                                'vessel_name': route_data.get('vessel_name'),
                                'vessel_imo': route_data.get('vessel_imo'),
                                'estimated_departure': route_data.get('estimated_departure'),
                                'estimated_arrival': route_data.get('estimated_arrival'),
                                'name': f"{route_data.get('carrier', 'Unknown')} - {route_data.get('service_type', 'Standard')}"
                            }

                            route = Route(
                                shipment_id=shipment.id,
                                route_type=route_type_val,
                                waypoints=json.dumps(route_data.get('waypoints', [])),
                                distance_km=float(route_data.get('distance_km', 0)),
                                estimated_duration_hours=duration_hours,
                                cost_usd=float(route_data.get('cost_usd', 0)),
                                carbon_emissions_kg=float(route_data.get('emissions_kg_co2', 0)),
                                risk_score=confidence_score,
                                risk_factors=json.dumps(route_data.get('risk_factors', [])),
                                is_current=False,  # set after sort
                                is_recommended=False,
                                route_metadata=json.dumps(metadata)
                            )
                            db.session.add(route)
                            created += 1
                        except Exception as route_err:
                            current_app.logger.error(f"Error saving route {idx+1}: {route_err}")
                            continue
                    if created:
                        db.session.commit()
                        # Select best as current within selected transport_mode if possible
                        try:
                            from app.models import Route as RouteModel
                            routes_q = RouteModel.query.filter_by(shipment_id=shipment.id).all()
                            preferred_mode = (shipment.transport_mode or 'SEA').upper()
                            candidates = [r for r in routes_q if (getattr(r.route_type, 'value', str(r.route_type)) or '') == preferred_mode]
                            if not candidates:
                                candidates = routes_q
                            if candidates:
                                best = sorted(candidates, key=lambda r: (r.cost_usd or 1e12, r.estimated_duration_hours or 1e12))[0]
                                for r in routes_q:
                                    r.is_current = (r.id == best.id)
                                    r.is_recommended = (r.id == best.id)
                                db.session.commit()
                        except Exception as sel_err:
                            current_app.logger.warning(f"Failed to set best route as current: {sel_err}")
            except Exception as e:
                current_app.logger.warning(f"Multi-carrier route generation failed: {e}")
            return jsonify({
                'id': shipment.id,
                'reference': shipment.reference_number,
                'message': 'Shipment created successfully',
                'routes_generated': created if 'created' in locals() else 0
            }), 201
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating shipment: {str(e)}")
            return jsonify({'error': f'Failed to create shipment: {str(e)}'}), 500
    else:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        status = request.args.get('status')
        risk_threshold = request.args.get('risk_threshold', type=float)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        query = Shipment.query.filter_by(workspace_id=workspace_id)
        if status:
            try:
                query = query.filter(Shipment.status == status)
            except Exception:
                pass
        if risk_threshold is not None:
            query = query.filter(Shipment.risk_score >= risk_threshold)
        pagination = query.paginate(page=page, per_page=per_page)
        return jsonify({
            'shipments': [{
                'id': s.id,
                'reference_number': s.reference_number,
                'status': s.status.value if hasattr(s.status,'value') else str(s.status),
                'risk_score': s.risk_score,
                'origin_port': s.origin_port,
                'destination_port': s.destination_port,
                'scheduled_arrival': s.scheduled_arrival.isoformat() if s.scheduled_arrival else None,
                'carrier': s.carrier,
                'origin_lat': s.origin_lat,
                'origin_lon': s.origin_lon,
                'destination_lat': s.destination_lat,
                'destination_lon': s.destination_lon
            } for s in pagination.items],
            'total': pagination.total,
            'page': pagination.page,
            'pages': pagination.pages
        })

@api_bp.route('/shipments/<int:shipment_id>', methods=['GET'])
def get_shipment(shipment_id):
    """Get shipment details."""
    shipment = _get_or_404(Shipment, shipment_id)
    
    # Create sample route data if none exists (for demo)
    route_data = None
    current_location_obj = None
    
    # Check if shipment has current_location in the database
    if shipment.current_location:
        try:
            # If it's a string, parse it
            if isinstance(shipment.current_location, str):
                current_location_obj = json.loads(shipment.current_location)
            else:
                # It's already a dict
                current_location_obj = shipment.current_location
        except (json.JSONDecodeError, TypeError):
            current_app.logger.error(f"Failed to parse current_location for shipment {shipment_id}")
    
    # If no current_location from database, create one for demo purposes
    if shipment.origin_lat and shipment.origin_lon and shipment.destination_lat and shipment.destination_lon:
        # For simplicity, create a straight line between origin and destination
        # In a real system, this would come from a proper routing engine with waypoints
        origin = [float(shipment.origin_lat), float(shipment.origin_lon)]
        destination = [float(shipment.destination_lat), float(shipment.destination_lon)]
        
        # Create a few intermediate points for the polyline
        import numpy as np
        steps = 5
        lat_steps = np.linspace(origin[0], destination[0], steps)
        lon_steps = np.linspace(origin[1], destination[1], steps)
        
        coordinates = [[float(lat), float(lon)] for lat, lon in zip(lat_steps, lon_steps)]
        
        # Estimated current position (1/3 to 2/3 along the route for in-transit shipments)
        if shipment.status == 'in_transit' and not current_location_obj:
            from random import random
            progress = 0.3 + (random() * 0.4)  # Between 30-70% of the journey
            idx = int(progress * (steps - 1))
            current_location_obj = {
                "lat": coordinates[idx][0],
                "lon": coordinates[idx][1],
                "timestamp": datetime.utcnow().isoformat(),
                "description": "Mid-journey"
            }
        
        route_data = {
            "coordinates": coordinates,
            "distance": 10000,  # Example distance in km
            "duration": 15.0    # Example duration in days
        }
        
    # Process routes if they exist
    route_list = []
    if hasattr(shipment, 'routes') and shipment.routes:
        for route in shipment.routes:
            # Extract name from route_metadata if present
            meta = {}
            try:
                meta = json.loads(route.route_metadata) if route.route_metadata else {}
            except Exception:
                meta = {}
            route_list.append({
                'id': route.id,
                'name': meta.get('name'),
                'is_current': route.is_current,
                'is_recommended': route.is_recommended,
                'risk_score': route.risk_score,
                'estimated_duration_hours': route.estimated_duration_hours,
                # Keep legacy key names alongside new ones for compatibility
                'estimated_cost': getattr(route, 'estimated_cost', None) or route.cost_usd,
                'cost_usd': route.cost_usd,
                'distance_km': route.distance_km,
                'carbon_emissions_kg': route.carbon_emissions_kg,
                # Keep waypoints as JSON string for frontend parser
                'waypoints': route.waypoints
            })

    PORT_COORDS = {
        'Shanghai': (31.22,121.46),'Singapore':(1.29,103.85),'Hong Kong':(22.32,114.17),'Busan':(35.18,129.08),'Tokyo':(35.65,139.77),
        'Rotterdam':(51.91,4.48),'Hamburg':(53.55,10.0),'Antwerp':(51.25,4.40),'Los Angeles':(33.73,-118.26),'New York':(40.71,-74.01),
        'Savannah':(32.08,-81.10),'Vancouver':(49.29,-123.12),'Santos':(-23.93,-46.33),'Buenos Aires':(-34.61,-58.37),'Durban':(-29.86,31.03),
        'Cape Town':(-33.91,18.42),'Tangier':(35.79,-5.81),'Alexandria':(31.20,29.92)
    }
    # Backfill missing coordinates from port code names if needed
    if (not shipment.origin_lat or not shipment.origin_lon):
        # Exact match
        if shipment.origin_port in PORT_COORDS:
            shipment.origin_lat, shipment.origin_lon = PORT_COORDS[shipment.origin_port]
        else:
            # Fuzzy match common typos (e.g., 'Shangai' -> 'Shanghai')
            try:
                import difflib
                keys = list(PORT_COORDS.keys())
                match = difflib.get_close_matches(str(shipment.origin_port or ''), keys, n=1, cutoff=0.8)
                if match:
                    shipment.origin_lat, shipment.origin_lon = PORT_COORDS[match[0]]
            except Exception:
                pass
    if (not shipment.destination_lat or not shipment.destination_lon):
        if shipment.destination_port in PORT_COORDS:
            shipment.destination_lat, shipment.destination_lon = PORT_COORDS[shipment.destination_port]
        else:
            try:
                import difflib
                keys = list(PORT_COORDS.keys())
                match = difflib.get_close_matches(str(shipment.destination_port or ''), keys, n=1, cutoff=0.8)
                if match:
                    shipment.destination_lat, shipment.destination_lon = PORT_COORDS[match[0]]
            except Exception:
                pass

    # Current location
    if shipment.current_location:
        current_location_obj = shipment.current_location
    else:
        # Derive a synthetic current location halfway based on time progress
        if shipment.origin_lat and shipment.origin_lon and shipment.destination_lat and shipment.destination_lon:
            progress = 0.5
            if shipment.scheduled_departure and shipment.scheduled_arrival:
                now = datetime.utcnow()
                total = (shipment.scheduled_arrival - shipment.scheduled_departure).total_seconds()
                if total > 0:
                    progress = max(0,min( (now - shipment.scheduled_departure).total_seconds()/total, 0.95))
            lat = shipment.origin_lat + (shipment.destination_lat - shipment.origin_lat)*progress
            lon = shipment.origin_lon + (shipment.destination_lon - shipment.origin_lon)*progress
            current_location_obj = {
                'lat': lat,
                'lon': lon,
                'timestamp': datetime.utcnow().isoformat(),
                'description': 'En-route position (simulated)'
            }
        else:
            current_location_obj = None

    # Routes (normalized fields for frontend)
    route_list = []
    for r in getattr(shipment, 'routes', []) or []:
        # derive name from metadata if present
        r_name = None
        try:
            meta = json.loads(r.route_metadata) if r.route_metadata else {}
            r_name = meta.get('name')
        except Exception:
            r_name = None
        route_list.append({
            'id': r.id,
            'is_current': r.is_current,
            'is_recommended': r.is_recommended,
            'name': r_name,
            'waypoints': r.waypoints,  # keep as JSON string for frontend JSON.parse
            'distance_km': getattr(r, 'distance_km', None) if hasattr(r, 'distance_km') else getattr(r, 'total_distance_km', None),
            'estimated_duration_hours': r.estimated_duration_hours,
            'cost_usd': getattr(r, 'cost_usd', None) if hasattr(r, 'cost_usd') else getattr(r, 'estimated_cost', None),
            'carbon_emissions_kg': getattr(r, 'carbon_emissions_kg', None) if hasattr(r, 'carbon_emissions_kg') else getattr(r, 'estimated_emissions_kg', None),
            'risk_score': r.risk_score
        })

    # If no current route exists, synthesize a simple one
    if not any(r.get('is_current') for r in route_list):
        if shipment.origin_lat and shipment.origin_lon and shipment.destination_lat and shipment.destination_lon:
            synthetic = {
                'id': 0,
                'is_current': True,
                'is_recommended': True,
                'name': f"{shipment.origin_port or 'Origin'} → {shipment.destination_port or 'Destination'}",
                'waypoints': [
                    {'lat': shipment.origin_lat, 'lon': shipment.origin_lon, 'name':'Origin', 'type':'origin'},
                    # optional mid-point for curvature effect
                    {'lat': (shipment.origin_lat+shipment.destination_lat)/2 + 3, 'lon': (shipment.origin_lon+shipment.destination_lon)/2, 'name':'Midpoint', 'type':'waypoint'},
                    {'lat': shipment.destination_lat, 'lon': shipment.destination_lon, 'name':'Destination', 'type':'destination'}
                ],
                'total_distance_km': None,
                'estimated_duration_hours': None,
                'estimated_cost': None,
                'risk_score': shipment.risk_score or 0
            }
            route_list.insert(0, synthetic)
            route_data = {'coordinates': [ [w['lat'], w['lon']] for w in synthetic['waypoints'] ]}

    if route_data is None and route_list:
        # derive simple coordinates for first current route
        current = next((r for r in route_list if r.get('is_current')), route_list[0])
        wps = current.get('waypoints', [])
        # Parse JSON string waypoints if needed
        if isinstance(wps, str):
            try:
                wps = json.loads(wps)
            except Exception:
                wps = []
        # Build coordinates from waypoints
        coordinates = []
        for w in wps:
            if isinstance(w, dict) and ('lat' in w and ('lon' in w or 'lng' in w)):
                lat = float(w.get('lat'))
                lon = float(w.get('lon') if 'lon' in w else w.get('lng'))
                coordinates.append([lat, lon])
        # Fallback: if missing or only a single point, synthesize a straight line
        if (not coordinates or len(coordinates) < 2) and shipment.origin_lat and shipment.origin_lon and shipment.destination_lat and shipment.destination_lon:
            origin = [float(shipment.origin_lat), float(shipment.origin_lon)]
            destination = [float(shipment.destination_lat), float(shipment.destination_lon)]
            coordinates = [origin, destination]
        route_data = {'coordinates': coordinates}

    return jsonify({
        'id': shipment.id,
        'reference_number': shipment.reference_number,
        'status': shipment.status.value if hasattr(shipment.status, 'value') else str(shipment.status),
        'risk_score': shipment.risk_score,
        'carrier': shipment.carrier,
        'origin': shipment.origin_port,
        'destination': shipment.destination_port,
        'origin_port': shipment.origin_port,
        'destination_port': shipment.destination_port,
        'origin_lat': float(shipment.origin_lat) if shipment.origin_lat else None,
        'origin_lon': float(shipment.origin_lon) if shipment.origin_lon else None,
        'destination_lat': float(shipment.destination_lat) if shipment.destination_lat else None,
        'destination_lon': float(shipment.destination_lon) if shipment.destination_lon else None,
        'scheduled_departure': shipment.scheduled_departure.isoformat() if shipment.scheduled_departure else None,
        'scheduled_arrival': shipment.scheduled_arrival.isoformat() if shipment.scheduled_arrival else None,
        'actual_departure': shipment.actual_departure.isoformat() if shipment.actual_departure else None,
        'actual_arrival': shipment.actual_arrival.isoformat() if shipment.actual_arrival else None,
        'departure_time': shipment.scheduled_departure.isoformat() if shipment.scheduled_departure else None,
        'estimated_arrival': shipment.eta.isoformat() if hasattr(shipment, 'eta') and shipment.eta else shipment.scheduled_arrival.isoformat() if shipment.scheduled_arrival else None,
        'original_eta': shipment.scheduled_arrival.isoformat() if shipment.scheduled_arrival else None,
        'current_location': current_location_obj,
        'route': route_data,
        'routes': route_list,
        'description': shipment.description or ''
    })

@api_bp.route('/alerts', methods=['GET'])
def get_alerts():
    """Get alerts with optional filters."""
    workspace_id = request.args.get('workspace_id', 1, type=int)
    status = request.args.get('status', 'open')
    severity = request.args.get('severity')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    query = Alert.query.filter_by(workspace_id=workspace_id, status=status)
    
    if severity:
        query = query.filter_by(severity=severity)
    
    query = query.order_by(Alert.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page)
    
    return jsonify({
        'alerts': [{
            'id': a.id,
            'type': a.type,
            'title': a.title,
            'severity': a.severity.value,
            'probability': a.probability,
            'confidence': a.confidence,
            'location': a.location,
            'created_at': a.created_at.isoformat()
        } for a in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'pages': pagination.pages
    })

@api_bp.route('/recommendations', methods=['GET'])
def get_recommendations():
    from sqlalchemy import func
    workspace_id = request.args.get('workspace_id', 1, type=int)
    status_param = request.args.get('status') or 'pending'
    type_filter = request.args.get('type')
    include_xai = request.args.get('include_xai', '1') not in ['0', 'false', 'False']
    severity_filter = request.args.get('severity')  # HIGH / MEDIUM / LOW
    search = request.args.get('search')  # text search in title/description
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = min(max(per_page, 1), 100)

    query = Recommendation.query.filter_by(workspace_id=workspace_id)
    if status_param:
        query = query.filter(func.lower(Recommendation.status) == status_param.lower())
    if type_filter:
        query = query.filter(func.lower(Recommendation.type) == type_filter.lower())
    if severity_filter:
        query = query.filter(func.lower(Recommendation.severity) == severity_filter.lower())
    if search:
        like_term = f"%{search.lower()}%"
        query = query.filter(func.lower(Recommendation.title).like(like_term) | func.lower(Recommendation.description).like(like_term))

    # Optional on-demand generation
    if request.args.get('trigger_generation') in ('1','true','True'):
        try:
            from app.agents.route_optimizer import RouteOptimizerAgent
            from app.models import Shipment, Route, RouteType
            agent = RouteOptimizerAgent()
            threshold = float(current_app.config.get('REROUTE_RISK_THRESHOLD', 0.75))
            high_risk = Shipment.query.filter(Shipment.risk_score >= threshold).all()
            PORT_COORDS = {
                'Shanghai': (31.22,121.46),'Singapore':(1.29,103.85),'Hong Kong':(22.32,114.17),'Busan':(35.18,129.08),'Tokyo':(35.65,139.77),
                'Rotterdam':(51.91,4.48),'Hamburg':(53.55,10.0),'Antwerp':(51.25,4.40),'Los Angeles':(33.73,-118.26),'New York':(40.71,-74.01),
                'Vancouver':(49.29,-123.12),'Cape Town':(-33.91,18.42)
            }
            for s in high_risk:
                exists = Recommendation.query.filter_by(subject_type='shipment', subject_id=s.id).first()
                if exists:
                    continue
                # Ensure a current route exists; if missing, synthesize one so evaluation can proceed
                if not s.current_route:
                    try:
                        # Backfill coordinates from known port mappings if missing
                        if (not s.origin_lat or not s.origin_lon) and s.origin_port in PORT_COORDS:
                            s.origin_lat, s.origin_lon = PORT_COORDS[s.origin_port]
                        if (not s.destination_lat or not s.destination_lon) and s.destination_port in PORT_COORDS:
                            s.destination_lat, s.destination_lon = PORT_COORDS[s.destination_port]
                        waypoints = []
                        if s.origin_lat and s.origin_lon and s.destination_lat and s.destination_lon:
                            waypoints = [
                                {'name': s.origin_port or 'Origin', 'lat': s.origin_lat, 'lon': s.origin_lon, 'type': 'origin'},
                                {'name': s.destination_port or 'Destination', 'lat': s.destination_lat, 'lon': s.destination_lon, 'type': 'destination'}
                            ]
                        else:
                            # Fallback generic waypoints
                            waypoints = [
                                {'name': 'Origin', 'lat': 0.0, 'lon': 0.0, 'type': 'origin'},
                                {'name': 'Destination', 'lat': 1.0, 'lon': 1.0, 'type': 'destination'}
                            ]
                        r = Route(
                            shipment_id=s.id,
                            route_type=RouteType.SEA,
                            waypoints=json.dumps(waypoints),
                            distance_km=10000.0,
                            estimated_duration_hours= (15*24),
                            cost_usd=100000.0,
                            carbon_emissions_kg=50000.0,
                            risk_score=s.risk_score or 0.8,
                            risk_factors=json.dumps(['synthetic']),
                            is_current=True,
                            is_recommended=True,
                            route_metadata=json.dumps({'name':'Synthetic Current Route','source':'auto-generated'})
                        )
                        db.session.add(r)
                        db.session.commit()
                    except Exception as synth_err:
                        current_app.logger.warning(f"Failed to synthesize route for shipment {s.id}: {synth_err}")
                if s.current_route:
                    agent._evaluate_route_alternatives(s, force=True)
        except Exception as gen_err:
            current_app.logger.warning(f"trigger_generation failed: {gen_err}")

    pagination = query.order_by(Recommendation.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for r in pagination.items:
        xai_payload = None
        if include_xai:
            raw = getattr(r, 'xai_json', None)
            if raw is not None:
                if isinstance(raw, str):
                    try:
                        xai_payload = json.loads(raw)
                    except Exception:
                        xai_payload = {'rationale': raw}
                else:
                    xai_payload = raw
        rec_entry = {
            'id': r.id,
            'type': r.type.value if hasattr(r.type, 'value') else str(r.type),
            'title': r.title,
            'description': r.description,
            'severity': r.severity.value if hasattr(r.severity, 'value') and r.severity else str(r.severity) if r.severity else None,
            'confidence': r.confidence,
            'impact_assessment': r.impact_assessment,
            'actions': r.actions,
            'created_at': r.created_at.isoformat(),
            'agent': getattr(r, 'created_by', 'AI Agent')
        }
        if xai_payload is not None:
            rec_entry['xai'] = xai_payload
            if isinstance(xai_payload, dict) and 'rationale' in xai_payload:
                rec_entry['rationale'] = xai_payload.get('rationale')
        items.append(rec_entry)

    response = {
        'recommendations': items,
        'count': len(items),
        'page': pagination.page,
        'pages': pagination.pages,
        'total': pagination.total,
        'per_page': pagination.per_page
    }
    for k in ['page','pages','total','per_page']:
        response.setdefault(k, getattr(pagination, k, 1 if k=='page' else 0))
    return jsonify(response)

@api_bp.route('/recommendations/trigger', methods=['POST'])
def trigger_recommendations_manual():
    """Manually trigger generation of recommendations for high‑risk shipments.

    Body JSON (all optional):
      - force (bool): force regeneration even if a recommendation exists
      - limit (int): max shipments to process this call
      - model (str): override model id for watsonx generation (defaults Granite instruct)

    Returns summary of processed shipments and new recommendations.
    """
    payload = request.get_json(silent=True) or {}
    force = bool(payload.get('force', False))
    limit = int(payload.get('limit', 10) or 10)
    model_override = payload.get('model')
    try:
        from app.agents.route_optimizer import RouteOptimizerAgent
        from app.models import Shipment, Recommendation
        threshold = float(current_app.config.get('REROUTE_RISK_THRESHOLD', 0.75))
        q = Shipment.query.filter(Shipment.risk_score >= threshold).order_by(Shipment.risk_score.desc())
        shipments = q.limit(limit).all()
        agent = RouteOptimizerAgent()
        processed = []
        created = 0

        # Optional watsonx + langchain summary generation for rationale enrichment
        watsonx_available = bool(current_app.config.get('WATSONX_API_KEY') or current_app.config.get('WATSONX_APIKEY'))
        langchain_rationales = {}
        if watsonx_available:
            try:
                # Lazy import to avoid dependency overhead when not configured
                from langchain_ibm import WatsonxLLM
                model_id = model_override or current_app.config.get('WATSONX_MODEL_ID', 'ibm/granite-3-8b-instruct')
                llm = WatsonxLLM(
                    model_id=model_id,
                    project_id=current_app.config.get('WATSONX_PROJECT_ID'),
                    api_key=current_app.config.get('WATSONX_API_KEY') or current_app.config.get('WATSONX_APIKEY'),
                    url=current_app.config.get('WATSONX_URL','https://us-south.ml.cloud.ibm.com'),
                    params={
                        'max_new_tokens': 300,
                        'temperature': 0.4,
                        'top_p': 0.9
                    }
                )
            except Exception as e:
                current_app.logger.warning(f"LangChain watsonx init failed: {e}")
                llm = None
        else:
            llm = None

        for s in shipments:
            existing = Recommendation.query.filter_by(subject_type='shipment', subject_id=s.id).first()
            if existing and not force:
                processed.append({'shipment_id': s.id, 'skipped': True, 'reason': 'exists'})
                continue
            try:
                # Ensure at least one current route (reuse logic from /recommendations trigger)
                if not s.current_route:
                    from app.models import Route, RouteType
                    r = Route(
                        shipment_id=s.id,
                        route_type=RouteType.SEA,
                        waypoints=json.dumps([
                            {'name': s.origin_port or 'Origin', 'lat': s.origin_lat or 0.0, 'lon': s.origin_lon or 0.0, 'type': 'origin'},
                            {'name': s.destination_port or 'Destination', 'lat': s.destination_lat or 1.0, 'lon': s.destination_lon or 1.0, 'type': 'destination'}
                        ]),
                        distance_km=10000.0,
                        estimated_duration_hours=360.0,
                        cost_usd=100000.0,
                        carbon_emissions_kg=50000.0,
                        risk_score=s.risk_score or threshold,
                        risk_factors=json.dumps(['synthetic']),
                        is_current=True,
                        is_recommended=True,
                        route_metadata=json.dumps({'name':'Synthetic Current Route','source':'manual-trigger'})
                    )
                    db.session.add(r)
                    db.session.commit()
                # Evaluate to create recommendation
                agent._evaluate_route_alternatives(s, force=True)
                rec = Recommendation.query.filter_by(subject_type='shipment', subject_id=s.id).order_by(Recommendation.created_at.desc()).first()
                rationale_extra = None
                if llm and rec:
                    try:
                        prompt = ("Provide a concise (<=80 words) operational explanation for reroute recommendation given "
                                  f"shipment risk_score={s.risk_score:.2f}, origin={s.origin_port}, destination={s.destination_port}. "
                                  "Return only the explanation sentence(s).")
                        rationale_extra = llm.invoke(prompt)
                        # Merge into existing XAI JSON if present
                        if getattr(rec, 'xai_json', None):
                            try:
                                xai_data = json.loads(rec.xai_json) if isinstance(rec.xai_json, str) else dict(rec.xai_json)
                            except Exception:
                                xai_data = {}
                        else:
                            xai_data = {}
                        if rationale_extra and isinstance(rationale_extra, str):
                            xai_data.setdefault('rationale', rationale_extra.strip())
                        rec.xai_json = json.dumps(xai_data)
                        db.session.commit()
                    except Exception as le:
                        current_app.logger.debug(f"LangChain rationale generation failed for shipment {s.id}: {le}")
                created += 1 if rec else 0
                processed.append({'shipment_id': s.id, 'created': bool(rec), 'rationale_llm': bool(rationale_extra)})
            except Exception as ship_err:
                current_app.logger.warning(f"Manual trigger failed for shipment {s.id}: {ship_err}")
                processed.append({'shipment_id': s.id, 'error': str(ship_err)})
        return jsonify({'status':'ok','threshold':threshold,'processed':processed,'created':created,'force':force})
    except Exception as e:
        current_app.logger.error(f"Manual recommendations trigger failed: {e}")
        return jsonify({'status':'error','error':str(e)}), 500

# Dedicated XAI endpoint to avoid collision with main blueprint demo route (/api/recommendations)
@api_bp.route('/recommendations/xai', methods=['GET'])
def get_recommendations_xai():
    """Alias endpoint with XAI + pagination (mirrors /recommendations)."""
    return get_recommendations()

@api_bp.route('/recommendations/<int:recommendation_id>/approve', methods=['POST'])
@audit_action('recommendation_approval')
def approve_recommendation(recommendation_id):
    """Approve a recommendation."""
    recommendation = _get_or_404(Recommendation, recommendation_id)
    
    if recommendation.status != 'pending':
        return jsonify({'error': 'Recommendation is not pending'}), 400
    
    # Get or create approval
    approval = recommendation.approval
    if not approval:
        approval = Approval(
            workspace_id=recommendation.workspace_id,
            recommendation_id=recommendation.id
        )
        db.session.add(approval)
    
    # Update approval
    approval.state = ApprovalStatus.APPROVED
    approval.decided_at = datetime.utcnow()
    approval.comments = request.json.get('comments')
    
    # Update recommendation
    recommendation.status = 'approved'
    
    # Publish event
    redis_manager = RedisManager()
    redis_manager.publish_event('approvals.requests', {
        'recommendation_id': recommendation.id,
        'action': 'approved',
        'type': recommendation.type.value
    })
    
    db.session.commit()
    
    return jsonify({
        'status': 'approved',
        'recommendation_id': recommendation.id
    })

@api_bp.route('/recommendations/<int:recommendation_id>/reject', methods=['POST'])
@audit_action('recommendation_rejection')
def reject_recommendation(recommendation_id):
    """Reject a recommendation."""
    recommendation = _get_or_404(Recommendation, recommendation_id)
    
    if recommendation.status != 'pending':
        return jsonify({'error': 'Recommendation is not pending'}), 400
    
    # Get or create approval
    approval = recommendation.approval
    if not approval:
        approval = Approval(
            workspace_id=recommendation.workspace_id,
            recommendation_id=recommendation.id
        )
        db.session.add(approval)
    
    # Update approval
    approval.state = ApprovalStatus.REJECTED
    approval.decided_at = datetime.utcnow()
    approval.comments = request.json.get('comments')
    
    # Update recommendation
    recommendation.status = 'rejected'
    
    db.session.commit()
    
    return jsonify({
        'status': 'rejected',
        'recommendation_id': recommendation.id
    })

@api_bp.route('/recommendations/<int:recommendation_id>/explain', methods=['GET'])
def explain_recommendation(recommendation_id):
    """Get XAI explanation for a recommendation."""
    recommendation = _get_or_404(Recommendation, recommendation_id)
    
    return jsonify({
        'recommendation_id': recommendation.id,
        'type': recommendation.type.value,
        'explanation': recommendation.xai_explanation or {
            'rationale': 'Based on current risk factors and historical patterns',
            'sources': recommendation.data_sources if hasattr(recommendation, 'data_sources') else [],
            'confidence_factors': {
                'data_quality': 0.85,
                'model_certainty': recommendation.confidence or 0.75,
                'historical_accuracy': 0.90
            }
        },
        'input_data': recommendation.input_data,
        'model_config': recommendation.model_config
    })

@api_bp.route('/suppliers', methods=['GET'])
def get_suppliers():
    """Get suppliers with health scores."""
    workspace_id = request.args.get('workspace_id', 1, type=int)
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    
    query = Supplier.query.filter_by(workspace_id=workspace_id)
    
    if active_only:
        query = query.filter_by(is_active=True)
    
    suppliers = query.order_by(Supplier.health_score.desc()).all()
    
    return jsonify({
        'suppliers': [{
            'id': s.id,
            'name': s.name,
            'code': s.code,
            'health_score': s.health_score,
            'reliability_score': s.reliability_score,
            'composite_score': s.composite_score,
            'average_lead_time_days': s.average_lead_time_days,
            'is_active': s.is_active
        } for s in suppliers]
    })

@api_bp.route('/inventory/at-risk', methods=['GET'])
def get_inventory_at_risk():
    """Get inventory items below reorder point."""
    workspace_id = request.args.get('workspace_id', 1, type=int)
    
    items = Inventory.query.filter(
        Inventory.workspace_id == workspace_id,
        Inventory.quantity_on_hand <= Inventory.reorder_point
    ).all()
    
    return jsonify({
        'items': [{
            'id': i.id,
            'sku': i.sku,
            'description': i.description,
            'quantity_on_hand': i.quantity_on_hand,
            'reorder_point': i.reorder_point,
            'days_of_cover': i.days_of_cover,
            'supplier': {
                'id': i.supplier.id,
                'name': i.supplier.name
            } if i.supplier else None
        } for i in items]
    })

@api_bp.route('/purchase-orders', methods=['GET'])
def get_purchase_orders():
    """Get purchase orders."""
    workspace_id = request.args.get('workspace_id', 1, type=int)
    status = request.args.get('status')
    
    query = PurchaseOrder.query.filter_by(workspace_id=workspace_id)
    
    if status:
        query = query.filter_by(status=status)
    
    pos = query.order_by(PurchaseOrder.created_at.desc()).limit(100).all()
    
    return jsonify({
        'purchase_orders': [{
            'id': po.id,
            'po_number': po.po_number,
            'supplier': {
                'id': po.supplier.id,
                'name': po.supplier.name
            },
            'status': po.status,
            'total_amount': po.total_amount,
            'currency': po.currency,
            'delivery_date': po.delivery_date.isoformat() if po.delivery_date else None,
            'ai_generated': po.ai_generated,
            'created_at': po.created_at.isoformat()
        } for po in pos]
    })

@api_bp.route('/agents/status', methods=['GET'])
def get_agent_status():
    """Get status of all agents."""
    # For MVP, return mock status
    # In production, would check actual agent health
    return jsonify({
        'agents': {
            'risk_predictor': {
                'status': 'healthy',
                'last_run': datetime.utcnow().isoformat(),
                'messages_processed': 142
            },
            'route_optimizer': {
                'status': 'healthy',
                'last_run': datetime.utcnow().isoformat(),
                'recommendations_generated': 23
            },
            'procurement': {
                'status': 'healthy',
                'last_run': datetime.utcnow().isoformat(),
                'pos_generated': 5
            },
            'orchestrator': {
                'status': 'healthy',
                'last_run': datetime.utcnow().isoformat(),
                'approvals_processed': 18
            }
        }
    })

@api_bp.route('/events/stream', methods=['GET'])
def get_event_stream():
    """Get event stream information."""
    redis_manager = RedisManager()
    
    streams = {}
    for key, name in redis_manager.streams.items():
        streams[key] = redis_manager.get_stream_info(key)
    
    return jsonify({'streams': streams})

@api_bp.route('/shipments/<int:shipment_id>/milestones', methods=['GET'])
def get_shipment_milestones(shipment_id):
    """Get milestones for a specific shipment."""
    try:
        # First, check if the shipment exists
        shipment = _get_or_404(Shipment, shipment_id)
        
        # For demo purposes, generate milestones based on shipment data
        # In a real application, this would come from a milestones table
        
        if not (shipment.scheduled_departure and shipment.scheduled_arrival):
            return jsonify([])
            
        departure_date = shipment.actual_departure or shipment.scheduled_departure
        arrival_date = shipment.scheduled_arrival
        duration = (arrival_date - departure_date).total_seconds()
        
        # Create milestones
        milestones = [
            {
                "id": 1,
                "shipment_id": shipment_id,
                "title": f"Departure from {shipment.origin_port}",
                "location": shipment.origin_port,
                "expected_at": departure_date.isoformat(),
                "completed_at": shipment.actual_departure.isoformat() if shipment.actual_departure else None,
                "completed": shipment.actual_departure is not None,
                "notes": "Shipment departed on schedule"
            }
        ]
        
        # Add intermediate milestones if this is a multi-leg journey
        if duration > 3 * 86400:  # More than 3 days
            # Example customs clearance at origin port
            origin_customs_date = departure_date + timedelta(hours=24)
            milestones.append({
                "id": 2,
                "shipment_id": shipment_id,
                "title": "Customs clearance at origin",
                "location": shipment.origin_port,
                "expected_at": origin_customs_date.isoformat(),
                "completed_at": origin_customs_date.isoformat() if shipment.actual_departure else None,
                "completed": shipment.actual_departure is not None,
                "notes": "Customs processing completed"
            })
            
            # Add in-transit milestone
            transit_date = departure_date + timedelta(seconds=duration / 2)
            now = datetime.utcnow()
            milestones.append({
                "id": 3,
                "shipment_id": shipment_id,
                "title": "In transit",
                "location": f"{shipment.origin_port} to {shipment.destination_port}",
                "expected_at": transit_date.isoformat(),
                "completed_at": transit_date.isoformat() if now > transit_date else None,
                "completed": now > transit_date,
                "notes": "Shipment is en route"
            })
            
            # Example customs clearance at destination
            dest_customs_date = arrival_date - timedelta(hours=24)
            milestones.append({
                "id": 4,
                "shipment_id": shipment_id,
                "title": "Customs clearance at destination",
                "location": shipment.destination_port,
                "expected_at": dest_customs_date.isoformat(),
                "completed_at": None,
                "completed": False,
                "notes": "Pending customs clearance"
            })
        
        # Add arrival milestone
        milestones.append({
            "id": 5,
            "shipment_id": shipment_id,
            "title": f"Arrival at {shipment.destination_port}",
            "location": shipment.destination_port,
            "expected_at": arrival_date.isoformat(),
            "completed_at": shipment.actual_arrival.isoformat() if shipment.actual_arrival else None,
            "completed": shipment.actual_arrival is not None,
            "notes": "Final delivery"
        })
        
        return jsonify(milestones)
        
    except Exception as e:
        current_app.logger.error(f"Error getting milestones for shipment {shipment_id}: {str(e)}")
        return jsonify([])

@api_bp.route('/shipments/<int:shipment_id>/documents', methods=['GET'])
def get_shipment_documents(shipment_id):
    """Get documents for a specific shipment."""
    try:
        # First, check if the shipment exists
        shipment = _get_or_404(Shipment, shipment_id)
        
        # For demo purposes, return mock documents
        # In a real application, this would come from a documents table
        
        # Generate mock documents (no cargo_details)
        documents = []
        import random
        # For demo, always include bill of lading for ocean shipments
        if "ocean" in shipment.mode.lower() if hasattr(shipment, "mode") and shipment.mode else False:
            documents.append({
                "id": 1,
                "shipment_id": shipment_id,
                "name": f"Bill of Lading - {shipment.reference_number}",
                "type": "Bill of Lading",
                "uploaded_at": (datetime.utcnow() - timedelta(days=random.randint(1, 10))).isoformat(),
                "url": f"/static/demo/documents/bl_{shipment.id}.pdf"
            })
        # Add some random document types based on shipment ID
        doc_types = [
            ("Commercial Invoice", f"Commercial Invoice - {shipment.reference_number}"),
            ("Packing List", f"Packing List - {shipment.reference_number}"),
            ("Certificate of Origin", f"Certificate of Origin - {shipment.reference_number}"),
            ("Insurance Certificate", f"Insurance Certificate - {shipment.reference_number}")
        ]
        # Add 1-3 random document types
        num_docs = min(3, len(doc_types))  # Up to 3 docs
        selected_docs = random.sample(doc_types, num_docs)
        for i, (doc_type, doc_name) in enumerate(selected_docs, start=2):
            documents.append({
                "id": i,
                "shipment_id": shipment_id,
                "name": doc_name,
                "type": doc_type,
                "uploaded_at": (datetime.utcnow() - timedelta(days=random.randint(1, 10))).isoformat(),
                "url": f"/static/demo/documents/doc_{shipment.id}_{i}.pdf"
            })
        return jsonify(documents)
        
    except Exception as e:
        current_app.logger.error(f"Error getting documents for shipment {shipment_id}: {str(e)}")
        return jsonify([])

@api_bp.route('/shipments/<int:shipment_id>/alerts', methods=['GET'])
def get_shipment_alerts(shipment_id):
    """Get alerts for a specific shipment."""
    try:
        # First, check if the shipment exists
        shipment = _get_or_404(Shipment, shipment_id)
        
        # Query related alerts if relationship exists, otherwise return demo data
        alerts = []
        
        if hasattr(shipment, 'alerts') and shipment.alerts:
            # Use actual related alerts from database
            for alert in shipment.alerts:
                alerts.append({
                    "id": alert.id,
                    "shipment_id": shipment_id,
                    "title": alert.title,
                    "description": alert.description,
                    "severity": alert.severity.value if hasattr(alert.severity, "value") else str(alert.severity),
                    "status": alert.status,
                    "created_at": alert.created_at.isoformat() if alert.created_at else datetime.utcnow().isoformat()
                })
        else:
            # Generate demo alerts based on risk score and status
            if shipment.risk_score > 0.7:
                # High risk shipment
                import random
                
                # Add potential alerts based on status
                if shipment.status == 'delayed':
                    alerts.append({
                        "id": 1000 + shipment_id,
                        "shipment_id": shipment_id,
                        "title": f"Shipment {shipment.reference_number} delayed",
                        "description": "Carrier has reported a significant delay for this shipment",
                        "severity": "high",
                        "status": "active",
                        "created_at": (datetime.utcnow() - timedelta(days=random.randint(1, 3))).isoformat()
                    })
                elif shipment.risk_score > 0.8:
                    # Very high risk - add weather alert
                    alerts.append({
                        "id": 2000 + shipment_id,
                        "shipment_id": shipment_id,
                        "title": "Severe weather warning on route",
                        "description": "Meteorological data indicates severe weather conditions along the planned route",
                        "severity": "high",
                        "status": "active",
                        "created_at": (datetime.utcnow() - timedelta(hours=random.randint(6, 24))).isoformat()
                    })
        
        return jsonify(alerts)
        
    except Exception as e:
        current_app.logger.error(f"Error getting alerts for shipment {shipment_id}: {str(e)}")
        return jsonify([])

@api_bp.route('/shipments/<int:shipment_id>/reroute-options', methods=['GET'])
def get_shipment_reroute_options(shipment_id):
    """Get reroute options for a specific shipment."""
    try:
        # First, check if the shipment exists
        shipment = _get_or_404(Shipment, shipment_id)
        
        # Check if there are alternate routes in the database
        from app.models import Route
        
        # Get current route for this shipment
        current_route = Route.query.filter_by(shipment_id=shipment_id, is_current=True).first()
        
        # Get alternative routes
        alt_routes = Route.query.filter_by(shipment_id=shipment_id, is_current=False).all()
        
        current_app.logger.info(f"Found {len(alt_routes)} alternative routes for shipment {shipment_id}")
        
        if alt_routes:
            # Return actual alternative routes from the database
            options = []
            
            for route in alt_routes:
                # Calculate ETA based on route duration
                new_eta = None
                if route.estimated_duration_hours:
                    # Calculate from now + duration
                    new_eta = datetime.utcnow() + timedelta(hours=route.estimated_duration_hours)
                elif shipment.scheduled_arrival:
                    # Fallback to shipment's scheduled arrival
                    new_eta = shipment.scheduled_arrival
                    
                # Calculate cost impact (difference between this route and current route)
                cost_impact = 0
                if current_route and route.estimated_cost is not None and current_route.estimated_cost is not None:
                    cost_impact = route.estimated_cost - current_route.estimated_cost
                
                # Calculate risk reduction (difference between shipment risk and route risk)
                risk_reduction = 0
                if route.risk_score is not None and shipment.risk_score is not None:
                    risk_reduction = shipment.risk_score - route.risk_score
                
                # Get route description
                description = route.description or get_route_description(route.id % 3, shipment)
                if route.is_recommended:
                    description = f"RECOMMENDED: {description}"
                
                route_details = {
                    "id": route.id,
                    "name": route.name or f"Alternative Route {route.id}",
                    "description": description,
                    "new_eta": new_eta.isoformat() if new_eta else None,
                    "cost_impact": cost_impact,
                    "risk_reduction": risk_reduction
                }
                options.append(route_details)
                
            return jsonify(options)
        else:
            # In a real system, these would be calculated from a routing engine
            # For demo, generate some mock options
            from datetime import datetime, timedelta
            import random
            
            # Generate 2-3 alternative routes
            num_options = random.randint(2, 3)
            options = []
            
            if shipment.scheduled_arrival:
                original_eta = shipment.scheduled_arrival
                base_cost_impact = random.randint(1500, 5000)  # Base cost impact in USD
                
                for i in range(num_options):
                    # Vary the ETA and cost impact for each option
                    eta_adj = random.choice([-1, 1, 2])  # Days adjustment to ETA
                    new_eta = original_eta + timedelta(days=eta_adj)
                    
                    # Cost impact varies - sometimes higher (positive) sometimes lower (negative)
                    cost_adj = random.uniform(-0.5, 1.5)
                    cost_impact = base_cost_impact * cost_adj
                    
                    # Risk reduction is always positive (benefit of rerouting)
                    risk_reduction = random.uniform(0.2, 0.6)
                    
                    options.append({
                        "id": i + 1,
                        "name": f"Alternative Route {i+1}",
                        "description": get_route_description(i, shipment),
                        "new_eta": new_eta.isoformat(),
                        "cost_impact": cost_impact,
                        "risk_reduction": risk_reduction
                    })
            
            return jsonify(options)
        
    except Exception as e:
        current_app.logger.error(f"Error getting reroute options for shipment {shipment_id}: {str(e)}")
        return jsonify([])

def get_route_description(route_id, shipment):
    """Generate a descriptive name for a route alternative."""
    if route_id == 0:
        return f"Route via Panama Canal with expedited handling"
    elif route_id == 1:
        return f"Route with stopover in Singapore for transshipment"
    else:
        return f"Alternative route with weather avoidance"

@api_bp.route('/shipments/<int:shipment_id>/reroute', methods=['POST'])
def apply_shipment_reroute(shipment_id):
    """Apply a reroute to a specific shipment."""
    try:
        # First, check if the shipment exists
        shipment = _get_or_404(Shipment, shipment_id)
        
        # Get the selected option index from request
        data = request.get_json()
        option_index = data.get('option_index', 0)
        
        # In a real system, this would apply the selected route from a routing engine
        # For demo, update the ETA based on the option index
        from datetime import timedelta
        
        if option_index == 0:
            # First option - slight improvement in ETA
            shipment.eta = shipment.scheduled_arrival - timedelta(days=1)
        else:
            # Other options - slight delay for increased safety
            shipment.eta = shipment.scheduled_arrival + timedelta(days=1)
            
        # Update the risk score - rerouting should reduce risk
        shipment.risk_score = max(0.1, shipment.risk_score * 0.7)  # Reduce risk by 30%
        
        # Save changes
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Shipment rerouted successfully",
            "new_eta": shipment.eta.isoformat() if shipment.eta else None
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error applying reroute for shipment {shipment_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Failed to apply reroute: {str(e)}"
        }), 500

@api_bp.route('/shipments/<int:shipment_id>/status', methods=['PUT'])
def update_shipment_status(shipment_id):
    """Update the status of a specific shipment."""
    try:
        # First, check if the shipment exists
        shipment = _get_or_404(Shipment, shipment_id)
        
        # Get the new status from request
        data = request.get_json()
        new_status = data.get('status')
        
        if not new_status:
            return jsonify({
                "success": False,
                "message": "No status provided"
            }), 400
            
        # Update the shipment status
        shipment.status = new_status
            
        # Update timestamp based on status
        now = datetime.utcnow()
        if new_status == 'in_transit' and not shipment.actual_departure:
            shipment.actual_departure = now
        elif new_status == 'delivered' and not shipment.actual_arrival:
            shipment.actual_arrival = now
            
        # Save changes
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Shipment status updated successfully",
            "new_status": new_status
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating status for shipment {shipment_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Failed to update status: {str(e)}"
        }), 500

@api_bp.route('/routes/<int:route_id>', methods=['GET'])
def get_route(route_id):
    """Get details for a specific route."""
    try:
        # Get the route
        route = _get_or_404(Route, route_id)
        
        # Convert to dictionary
        # Derive name from metadata if present
        r_name = None
        try:
            meta = json.loads(route.route_metadata) if route.route_metadata else {}
            r_name = meta.get('name')
        except Exception:
            r_name = None

        route_data = {
            'id': route.id,
            'name': r_name,
            'route_type': route.route_type if route.route_type else None,  # route_type is now a string
            'is_current': route.is_current,
            'is_recommended': route.is_recommended,
            'waypoints': [],
            # provide both distance_km and total_distance_km for compatibility
            'distance_km': getattr(route, 'distance_km', None) if hasattr(route, 'distance_km') else getattr(route, 'total_distance_km', None),
            'total_distance_km': getattr(route, 'total_distance_km', None) if hasattr(route, 'total_distance_km') else getattr(route, 'distance_km', None),
            'estimated_duration_hours': route.estimated_duration_hours,
            'estimated_cost': getattr(route, 'estimated_cost', None) if hasattr(route, 'estimated_cost') else route.cost_usd,
            'cost_usd': route.cost_usd,
            'estimated_emissions_kg': getattr(route, 'estimated_emissions_kg', None) if hasattr(route, 'estimated_emissions_kg') else route.carbon_emissions_kg,
            'carbon_emissions_kg': route.carbon_emissions_kg,
            'risk_score': route.risk_score,
            'risk_factors': route.risk_factors
        }
        
        # Add waypoints if they exist
        if route.waypoints:
            try:
                waypoints = route.waypoints
                if isinstance(waypoints, str):
                    waypoints = json.loads(waypoints)
                
                # Ensure each waypoint has both lon and lng for frontend compatibility
                for waypoint in waypoints:
                    if 'lon' in waypoint and 'lng' not in waypoint:
                        waypoint['lng'] = waypoint['lon']
                    elif 'lng' in waypoint and 'lon' not in waypoint:
                        waypoint['lon'] = waypoint['lng']
                    
                    # Add a type if missing for proper icon display
                    if 'type' not in waypoint:
                        if waypoint == waypoints[0]:
                            waypoint['type'] = 'origin'
                        elif waypoint == waypoints[-1]:
                            waypoint['type'] = 'destination'
                        else:
                            waypoint['type'] = 'waypoint'
                
                route_data['waypoints'] = waypoints
            except Exception as e:
                current_app.logger.error(f"Error parsing waypoints for route {route_id}: {str(e)}")
                route_data['waypoints'] = []
        
        return jsonify(route_data)
        
    except Exception as e:
        current_app.logger.error(f"Error getting route {route_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Failed to get route: {str(e)}"
        }), 500

@api_bp.route('/shipments/<int:shipment_id>/routes', methods=['GET'])
def get_shipment_routes(shipment_id):
    """Get all routes for a specific shipment."""
    try:
        # First, check if the shipment exists
        shipment = _get_or_404(Shipment, shipment_id)
        
        # Get all routes for this shipment
        routes = Route.query.filter_by(shipment_id=shipment_id).all()
        
        # Convert routes to dictionaries
        route_list = []
        for route in routes:
            # Keep waypoints as stored (JSON string) for frontend
            meta = {}
            try:
                meta = json.loads(route.route_metadata) if route.route_metadata else {}
            except Exception:
                meta = {}
            
            # Extract vessel name from metadata for display
            vessel_name = meta.get('vessel_name', 'Unknown Vessel')
            
            route_list.append({
                'id': route.id,
                'name': meta.get('name'),
                'carrier': meta.get('carrier') or meta.get('provider', 'Unknown'),
                'service_type': meta.get('service_type') or meta.get('service_code', 'Standard'),
                'vessel_name': vessel_name,
                'is_current': route.is_current,
                'is_recommended': route.is_recommended,
                'waypoints': route.waypoints,  # string
                'distance_km': route.distance_km,
                'estimated_duration_hours': route.estimated_duration_hours,
                'cost_usd': route.cost_usd,
                'carbon_emissions_kg': route.carbon_emissions_kg,
                'risk_score': route.risk_score,
                'risk_factors': route.risk_factors  # keep string
            })
        
        return jsonify(route_list)
        
    except Exception as e:
        current_app.logger.error(f"Error getting routes for shipment {shipment_id}: {str(e)}")
        return jsonify([])

@api_bp.route('/shipments/<int:shipment_id>/select-route', methods=['POST'])
def select_shipment_route(shipment_id):
    """Select a new route for a shipment."""
    try:
        shipment = _get_or_404(Shipment, shipment_id)
        data = request.get_json() or {}
        route_id = data.get('route_id')
        if not route_id:
            return jsonify({"success": False, "message": "No route ID provided"}), 400

        new_route = _get_or_404(Route, route_id)
        if new_route.shipment_id != shipment.id:
            return jsonify({"success": False, "message": "Route does not belong to this shipment"}), 400

        for route in Route.query.filter_by(shipment_id=shipment.id).all():
            route.is_current = False
        new_route.is_current = True

        if new_route.estimated_duration_hours:
            shipment.scheduled_arrival = datetime.utcnow() + timedelta(hours=new_route.estimated_duration_hours)
        if new_route.risk_score is not None:
            shipment.risk_score = new_route.risk_score

        db.session.commit()

        # Trigger evaluation if risk exceeds threshold after change
        try:
            from flask import current_app as _ca
            threshold = float(_ca.config.get('REROUTE_RISK_THRESHOLD', 0.75)) if _ca else 0.75
        except Exception:
            threshold = 0.75
        try:
            if (shipment.risk_score or 0) >= threshold:
                from app.agents.route_optimizer import RouteOptimizerAgent
                agent = RouteOptimizerAgent()
                agent._evaluate_route_alternatives(shipment, force=True)
        except Exception as trg_err:
            current_app.logger.warning(f"Auto-evaluate after select failed: {trg_err}")
        return jsonify({
            "success": True,
            "message": "Route updated successfully",
            "new_eta": shipment.scheduled_arrival.isoformat() if shipment.scheduled_arrival else None
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error selecting route for shipment {shipment_id}: {str(e)}")
        return jsonify({"success": False, "message": f"Failed to select route: {str(e)}"}), 500

@api_bp.route('/shipments/<int:shipment_id>/notes', methods=['POST'])
def add_shipment_note(shipment_id):
    """Add a note to a specific shipment."""
    try:
        # First, check if the shipment exists
        shipment = _get_or_404(Shipment, shipment_id)
        
        # Get the note from request
        data = request.get_json()
        note = data.get('note')
        
        if not note:
            return jsonify({
                "success": False,
                "message": "No note provided"
            }), 400
            
        # In a real system, this would add to a notes table
        # For demo, we'll just return success
        
        return jsonify({
            "success": True,
            "message": "Note added successfully"
        })
        
    except Exception as e:
        current_app.logger.error(f"Error adding note for shipment {shipment_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Failed to add note: {str(e)}"
        }), 500

@api_bp.route('/shipments/<int:shipment_id>/optimize', methods=['POST'])
def optimize_shipment(shipment_id):
    """Manually trigger route optimization evaluation for a shipment (synchronous)."""
    shipment = _get_or_404(Shipment, shipment_id)
    try:
        from app.agents.route_optimizer import RouteOptimizerAgent
        agent = RouteOptimizerAgent()
        agent._evaluate_route_alternatives(shipment, force=True)
        rec_exists = Recommendation.query.filter_by(subject_type='shipment', subject_id=shipment.id).count()
        return jsonify({
            'status': 'ok',
            'shipment_id': shipment.id,
            'recommendations': rec_exists
        })
    except Exception as e:
        current_app.logger.error(f"Optimize endpoint failure: {e}")
        return jsonify({'status':'error','error':str(e)}), 500

# --- Route CRUD for manual management ---

@api_bp.route('/shipments/<int:shipment_id>/routes', methods=['POST'])
def create_route_for_shipment(shipment_id):
    """Create a route and assign it to a shipment manually."""
    try:
        shipment = _get_or_404(Shipment, shipment_id)
        payload = request.get_json(silent=True) or {}

        # Parse fields
        route_type_raw = payload.get('route_type') or 'SEA'
        try:
            route_type = RouteType(route_type_raw) if isinstance(route_type_raw, RouteType) else RouteType(route_type_raw.upper())
        except Exception:
            route_type = RouteType.SEA

        waypoints = payload.get('waypoints')
        if isinstance(waypoints, list):
            waypoints_json = json.dumps(waypoints)
        else:
            waypoints_json = waypoints if isinstance(waypoints, str) else json.dumps([])

        risk_factors = payload.get('risk_factors')
        if isinstance(risk_factors, list):
            risk_factors_json = json.dumps(risk_factors)
        else:
            risk_factors_json = risk_factors if isinstance(risk_factors, str) else None

        meta = payload.get('metadata') or {}
        if not isinstance(meta, dict):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}

        # Construct route
        route = Route(
            shipment_id=shipment.id,
            route_type=route_type,
            waypoints=waypoints_json,
            distance_km=float(payload.get('distance_km')) if payload.get('distance_km') is not None else 0.0,
            estimated_duration_hours=float(payload.get('estimated_duration_hours')) if payload.get('estimated_duration_hours') is not None else 0.0,
            cost_usd=float(payload.get('cost_usd')) if payload.get('cost_usd') is not None else 0.0,
            carbon_emissions_kg=float(payload.get('carbon_emissions_kg')) if payload.get('carbon_emissions_kg') is not None else 0.0,
            risk_score=float(payload.get('risk_score')) if payload.get('risk_score') is not None else 0.0,
            risk_factors=risk_factors_json,
            is_current=bool(payload.get('is_current')),
            is_recommended=bool(payload.get('is_recommended')),
            route_metadata=json.dumps(meta) if meta else None
        )

        # If setting as current, unset others
        if route.is_current:
            for r in Route.query.filter_by(shipment_id=shipment.id, is_current=True).all():
                r.is_current = False

        db.session.add(route)
        db.session.commit()

        # If marked current and has duration, update shipment ETA
        if route.is_current and route.estimated_duration_hours:
            shipment.scheduled_arrival = datetime.utcnow() + timedelta(hours=route.estimated_duration_hours)
            db.session.commit()

        return jsonify({
            'id': route.id,
            'message': 'Route created',
            'route': {
                'id': route.id,
                'is_current': route.is_current,
                'is_recommended': route.is_recommended,
                'waypoints': route.waypoints,
                'distance_km': route.distance_km,
                'estimated_duration_hours': route.estimated_duration_hours,
                'cost_usd': route.cost_usd,
                'carbon_emissions_kg': route.carbon_emissions_kg,
                'risk_score': route.risk_score
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating route for shipment {shipment_id}: {e}")
        return jsonify({'error': 'Failed to create route', 'detail': str(e)}), 400


@api_bp.route('/routes/<int:route_id>', methods=['PUT'])
def update_route(route_id):
    """Update an existing route."""
    try:
        route = _get_or_404(Route, route_id)
        payload = request.get_json(silent=True) or {}

        if 'route_type' in payload:
            try:
                val = payload.get('route_type')
                route.route_type = RouteType(val) if isinstance(val, RouteType) else RouteType(str(val).upper())
            except Exception:
                pass
        if 'waypoints' in payload:
            w = payload.get('waypoints')
            route.waypoints = json.dumps(w) if isinstance(w, list) else (w if isinstance(w, str) else route.waypoints)
        for num_field in ['distance_km','estimated_duration_hours','cost_usd','carbon_emissions_kg','risk_score']:
            if num_field in payload and payload.get(num_field) is not None:
                try:
                    setattr(route, num_field, float(payload.get(num_field)))
                except Exception:
                    pass
        if 'risk_factors' in payload:
            rf = payload.get('risk_factors')
            route.risk_factors = json.dumps(rf) if isinstance(rf, list) else (rf if isinstance(rf, str) else None)
        if 'is_current' in payload:
            new_current = bool(payload.get('is_current'))
            if new_current:
                for r in Route.query.filter_by(shipment_id=route.shipment_id, is_current=True).all():
                    r.is_current = False
            route.is_current = new_current
        if 'is_recommended' in payload:
            route.is_recommended = bool(payload.get('is_recommended'))
        if 'metadata' in payload:
            meta = payload.get('metadata')
            if not isinstance(meta, dict):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            route.route_metadata = json.dumps(meta) if meta else None

        db.session.commit()

        return jsonify({'status': 'updated', 'route_id': route.id})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating route {route_id}: {e}")
        return jsonify({'error': 'Failed to update route', 'detail': str(e)}), 400


@api_bp.route('/routes/<int:route_id>', methods=['DELETE'])
def delete_route(route_id):
    """Delete a route."""
    try:
        route = _get_or_404(Route, route_id)
        db.session.delete(route)
        db.session.commit()
        return jsonify({'status': 'deleted', 'route_id': route_id})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting route {route_id}: {e}")
        return jsonify({'error': 'Failed to delete route', 'detail': str(e)}), 400
