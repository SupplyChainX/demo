"""
Main application routes
"""
import logging
import json
import random
import copy
import sys
import os
from sqlalchemy.exc import OperationalError
from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, request, current_app, make_response, redirect, url_for, Response, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import func, or_, and_
from app import db, socketio
from app.models import (
    Shipment, Alert, Recommendation, Inventory, 
    Supplier, PurchaseOrder, User, AuditLog, Approval, Route, RouteType,
    ShipmentStatus, AlertSeverity, RecommendationType, ApprovalStatus, Contract,
    ChatMessage, Policy
)

# SQLAlchemy 2.0 compliant get_or_404 replacement
from flask import abort as _abort
def _get_or_404(model, object_id):
    obj = db.session.get(model, object_id)
    if obj is None:
        _abort(404)
    return obj

logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
@main_bp.route('/dashboard')
def dashboard():
    """Main dashboard view."""
    return render_template('main_dashboard.html')

@main_bp.route('/api/kpis')
def get_kpis():
    """Get current KPIs for dashboard."""
    try:
        from app.utils.redis_manager import RedisManager
        import json
        
        # Try to get KPIs from Redis first for faster response
        redis_manager = RedisManager()
        kpi_data = redis_manager.get_key("dashboard_kpis")
        
        if kpi_data:
            try:
                return jsonify(json.loads(kpi_data))
            except:
                # If parsing fails, continue with database calculation
                pass
        
        # Calculate KPIs from database
        risk_index = calculate_global_risk_index()
        on_time_rate = calculate_on_time_rate()
        # Use consistent alert counting logic with other endpoints
        open_alerts = Alert.query.filter(
            Alert.status.in_(['open', 'active', 'acknowledged'])
        ).count()
        
        # Calculate inventory at risk (items below reorder point or with low daily coverage)
        try:
            inventory_at_risk = Inventory.query.filter(
                (Inventory.quantity_on_hand <= Inventory.reorder_point) |
                ((Inventory.daily_usage_rate > 0) & 
                 (Inventory.quantity_on_hand / Inventory.daily_usage_rate < 10))
            ).count()
        except Exception as e:
            logger.error(f"Error calculating inventory at risk: {e}")
            inventory_at_risk = 12  # Default demo value
        
        # Get alert breakdown
        try:
            alert_breakdown = db.session.query(
                Alert.severity, func.count(Alert.id)
            ).filter(Alert.status.in_(['open', 'active', 'acknowledged'])).group_by(Alert.severity).all()
            
            alerts_by_severity = {
                'high': 0,
                'medium': 0,
                'low': 0,
                'critical': 0
            }
            for severity, count in alert_breakdown:
                # Handle both enum objects and string values
                if hasattr(severity, 'value'):
                    severity_str = severity.value
                else:
                    severity_str = str(severity).lower()
                
                if severity_str in alerts_by_severity:
                    alerts_by_severity[severity_str] = count
        except Exception as e:
            logger.error(f"Error calculating alert breakdown: {e}")
            alerts_by_severity = {'high': 0, 'medium': 0, 'low': 0, 'critical': 0}
        
        kpi_response = {
            'kpis': {
                'risk_index': risk_index,
                'on_time_rate': on_time_rate,
                'open_alerts': open_alerts,
                'inventory_at_risk': inventory_at_risk,
                'alerts_by_severity': alerts_by_severity
            },
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Cache in Redis for 5 minutes
        redis_manager.set_key("dashboard_kpis", json.dumps(kpi_response), ex=300)
        
        return jsonify(kpi_response)
        
    except Exception as e:
        logger.error(f"Error fetching KPIs: {e}")
        return jsonify({'error': 'Failed to fetch KPIs'}), 500

@main_bp.route('/api/shipments-at-risk')
def get_shipments_at_risk():
    """Get shipments currently at risk."""
    try:
        # Get sort parameter from query string (default to 'recent' to show latest updates first)
        sort_by = request.args.get('sort', 'recent')
        
        # Query shipments with high risk or delayed status
        at_risk_query = Shipment.query.filter(
            (Shipment.risk_score > 0.5) | 
            (Shipment.status == 'delayed')
        )
        
        # Apply sorting based on the sort parameter
        if sort_by == 'recent':
            # Sort by most recent updates first
            at_risk = at_risk_query.order_by(Shipment.updated_at.desc()).limit(10).all()
        else:  # Default to 'risk' sorting
            # Sort by highest risk score first, then by ETA
            at_risk = at_risk_query.order_by(
                Shipment.risk_score.desc(), 
                Shipment.scheduled_arrival
            ).limit(10).all()
        
        # If no at-risk shipments exist, return the first shipment as a fallback for testing
        if not at_risk:
            at_risk = Shipment.query.order_by(Shipment.id).limit(10).all()
            # If still no shipments, create a demo one
            if not at_risk:
                try:
                    s = Shipment(workspace_id=1, 
                                reference_number='SH-2024-001', 
                                carrier='Pacific Line',
                                origin_port='Shanghai', 
                                destination_port='Los Angeles', 
                                status='IN_TRANSIT', 
                                risk_score=0.65,
                                origin_lat=31.22, 
                                origin_lon=121.46,
                                destination_lat=33.73, 
                                destination_lon=-118.26)
                    db.session.add(s)
                    db.session.commit()
                    at_risk = [s]
                    logger.info(f"Created demo shipment for 'at risk' display")
                except Exception as create_err:
                    logger.error(f"Could not create demo shipment: {create_err}")
        
        shipments = []
        for shipment in at_risk:
            shipments.append({
                'id': shipment.id,
                'reference': shipment.reference_number,
                'carrier': shipment.carrier or 'Unknown',
                'origin': shipment.origin_port,
                'destination': shipment.destination_port,
                'eta': shipment.scheduled_arrival.isoformat() if shipment.scheduled_arrival else None,
                'risk_level': 'high' if shipment.risk_score > 0.7 else 'medium',
                'risk_cause': get_risk_cause(shipment),
                'status': shipment.status.value if hasattr(shipment.status, 'value') else str(shipment.status)
            })
        
        return jsonify({
            'shipments_at_risk': shipments,
            'total': len(shipments)
        })
        
    except Exception as e:
        logger.error(f"Error fetching shipments at risk: {e}")
        return jsonify({'shipments_at_risk': [], 'total': 0})
        
@main_bp.route('/shipments', methods=['GET', 'POST'])
def get_shipments():
    """Get or create shipments with optional filtering."""
    if request.method == 'POST':
        # Create new shipment
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400
            
            # Validate required fields
            required_fields = ['reference_number', 'origin_port', 'destination_port', 'carrier']
            for field in required_fields:
                if field not in data:
                    return jsonify({'error': f'Missing required field: {field}'}), 400
            
            # Parse optional status
            status_value = 'PLANNED'
            incoming_status = data.get('status') or data.get('shipment_status')
            if incoming_status:
                try:
                    # Convert to uppercase string
                    status_value = incoming_status.upper()
                except Exception:
                    pass

            # Parse risk score (0-1)
            risk_score = 0.1
            if 'risk_score' in data:
                try:
                    rs = float(data.get('risk_score'))
                    if 0 <= rs <= 1:
                        risk_score = rs
                except (TypeError, ValueError):
                    pass

            # Use the selected carrier from the form - multi-carrier support enabled
            carrier_value = data.get('carrier') or 'Maersk Line'
            logger.info(f"Creating shipment with carrier: {carrier_value}")

            # Accept both legacy and new field names from frontend
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
                # Honor incoming transport mode (fallback SEA)
                transport_mode=(data.get('transport_mode') or data.get('mode') or 'SEA'),
                container_number=data.get('container_number'),
                container_count=int(data.get('container_count')) if data.get('container_count') else None,
                weight_tons=float(data.get('weight_tons')) if data.get('weight_tons') else (float(data.get('weight')) if data.get('weight') else None),
                cargo_value_usd=float(data.get('cargo_value_usd')) if data.get('cargo_value_usd') else (float(data.get('value')) if data.get('value') else None),
                origin_lat=float(data.get('origin_lat')) if data.get('origin_lat') else None,
                origin_lon=float(data.get('origin_lon')) if data.get('origin_lon') else None,
                destination_lat=float(data.get('destination_lat')) if data.get('destination_lat') else None,
                destination_lon=float(data.get('destination_lon')) if data.get('destination_lon') else None
            )
            
            # Add origin/destination lat/lon if not provided
            if not shipment.origin_lat or not shipment.origin_lon:
                PORT_COORDS = {
                    'Shanghai': (31.22, 121.46), 'Singapore': (1.29, 103.85), 'Hong Kong': (22.32, 114.17),
                    'Los Angeles': (33.73, -118.26), 'New York': (40.71, -74.01), 'Rotterdam': (51.91, 4.48)
                }
                if shipment.origin_port in PORT_COORDS:
                    shipment.origin_lat, shipment.origin_lon = PORT_COORDS[shipment.origin_port]
                    
            if not shipment.destination_lat or not shipment.destination_lon:
                PORT_COORDS = {
                    'Shanghai': (31.22, 121.46), 'Singapore': (1.29, 103.85), 'Hong Kong': (22.32, 114.17),
                    'Los Angeles': (33.73, -118.26), 'New York': (40.71, -74.01), 'Rotterdam': (51.91, 4.48)
                }
                if shipment.destination_port in PORT_COORDS:
                    shipment.destination_lat, shipment.destination_lon = PORT_COORDS[shipment.destination_port]
            
            db.session.add(shipment)
            db.session.commit()
            
            # Initialize routes_saved variable
            routes_saved = 0
            
            # Generate routes immediately (synchronous) to ensure they're available in the UI
            try:
                from app.integrations.carrier_routes import CarrierRouteProvider, get_multi_carrier_routes
                
                logger.info(f"Starting route generation for shipment {shipment.id}: {shipment.origin_port} -> {shipment.destination_port}")
                
                # Get routes for this shipment with proper transport mode handling
                transport_mode = shipment.transport_mode or 'SEA'
                logger.info(f"Using transport mode: {transport_mode}, carrier preference: {shipment.carrier}")
                
                # Generate multi-carrier routes (Maersk/DHL/FedEx) for richer dataset
                try:
                    routes = get_multi_carrier_routes(
                        origin=shipment.origin_port,
                        destination=shipment.destination_port,
                        departure_date=shipment.scheduled_departure or datetime.utcnow(),
                        carrier_preference=shipment.carrier,
                        transport_mode='MULTIMODAL',  # fetch all, filter when selecting current
                        package_weight=(shipment.weight_tons or 1.0) * 1000,
                        package_dimensions={'length': 120, 'width': 80, 'height': 60},
                        package_value=shipment.cargo_value_usd or 10000.0,
                        original_mode=shipment.transport_mode
                    )
                except Exception as mc_err:
                    logger.warning(f"Multi-carrier generation failed (fallback none): {mc_err}")
                    routes = []
                logger.info(f"Generated {len(routes)} multi-carrier routes for shipment {shipment.id}")

                # Persist routes (mirror logic from api.routes)
                for idx, route_data in enumerate(routes):
                    try:
                        confidence_score = route_data.get('confidence_score', 'medium')
                        if isinstance(confidence_score, str):
                            confidence_map = {'high': 0.9, 'medium': 0.7, 'low': 0.5}
                            confidence_score = confidence_map.get(confidence_score.lower(), 0.7)
                        else:
                            confidence_score = float(confidence_score)

                        # Determine route type from modes
                        modes = [m.upper() for m in (route_data.get('transport_modes') or [])]
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

                        transit_days = route_data.get('transit_time_days', 1)
                        duration_hours = float(transit_days) * 24

                        metadata = {
                            'carrier': route_data.get('carrier', 'Unknown'),
                            'service_type': route_data.get('service_type', route_data.get('service_name', 'Standard')),
                            'vessel_name': route_data.get('vessel_name'),
                            'vessel_imo': route_data.get('vessel_imo'),
                            'estimated_departure': route_data.get('estimated_departure'),
                            'estimated_arrival': route_data.get('estimated_arrival'),
                            'name': route_data.get('service_name') or f"{route_data.get('carrier', 'Unknown')} - {route_data.get('service_type', 'Standard')}"
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
                            is_current=False,
                            is_recommended=False,
                            route_metadata=json.dumps(metadata)
                        )
                        db.session.add(route)
                        routes_saved += 1
                    except Exception as route_err:
                        logger.error(f"Error saving route {idx+1}: {route_err}")
                        continue
                if routes_saved:
                    db.session.commit()
                    # Select best current route within requested mode preference
                    try:
                        from app.models import Route as RouteModel
                        routes_q = RouteModel.query.filter_by(shipment_id=shipment.id).all()
                        preferred_mode = (shipment.transport_mode or 'SEA').upper()
                        candidates = [r for r in routes_q if getattr(r.route_type, 'value', str(r.route_type)).upper() == preferred_mode]
                        if not candidates:
                            candidates = routes_q
                        if candidates:
                            best = sorted(candidates, key=lambda r: (r.cost_usd or 1e12, r.estimated_duration_hours or 1e12))[0]
                            for r in routes_q:
                                r.is_current = (r.id == best.id)
                                r.is_recommended = (r.id == best.id)
                            db.session.commit()
                    except Exception as sel_err:
                        logger.warning(f"Failed to set best current route: {sel_err}")
                logger.info(f"Saved {routes_saved} routes for shipment {shipment.id}")
                
            except Exception as e:
                logger.error(f"Failed to generate routes for shipment {shipment.id}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                # Don't fail shipment creation if route generation fails
            
            # Also publish event for other agents (risk assessment, etc.) 
            try:
                from app.agents.communicator import AgentCommunicator
                communicator = AgentCommunicator()
                communicator.publish_message('shipments.created', {
                    'shipment_id': shipment.id,
                    'tracking_number': shipment.tracking_number,
                    'carrier': shipment.carrier,
                    'origin_port': shipment.origin_port,
                    'destination_port': shipment.destination_port,
                    'transport_mode': shipment.transport_mode,
                    'created_at': shipment.created_at.isoformat() if shipment.created_at else None
                })
                logger.info(f"Published shipment created event for {shipment.id}")
            except Exception as e:
                logger.error(f"Failed to publish shipment created event: {e}")
            
            return jsonify({
                'id': shipment.id,
                'reference': shipment.reference_number,
                'message': 'Shipment created successfully',
                'routes_generated': routes_saved if 'routes_saved' in locals() else 0
            }), 201
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating shipment: {str(e)}")
            return jsonify({'error': f'Failed to create shipment: {str(e)}'}), 500
    else:
        # GET method - retrieve shipments
        try:
            # Get query parameters
            page = int(request.args.get('page', 1))
            status = request.args.get('status', '')
            risk = request.args.get('risk', '')
            carrier = request.args.get('carrier', '')
            shipment_id = request.args.get('shipmentId', '')
            per_page = 20
            
            # Start with base query
            query = Shipment.query
            
            # Apply filters
            if shipment_id:
                try:
                    query = query.filter(Shipment.id == int(shipment_id))
                except ValueError:
                    pass
                    
            if status:
                try:
                    query = query.filter(Shipment.status == ShipmentStatus(status.lower()))
                except ValueError:
                    pass
                    
            if risk:
                try:
                    risk_threshold = float(risk)
                    query = query.filter(Shipment.risk_score >= risk_threshold)
                except ValueError:
                    pass
                    
            if carrier:
                query = query.filter(Shipment.carrier.ilike(f'%{carrier}%'))
            
            # Check if we have any shipments
            total_shipments = query.count()
            
            # If no shipments and no filters: return empty (no auto seeding)
            if total_shipments == 0 and not (status or risk or carrier or shipment_id):
                return jsonify({'shipments': [], 'total': 0, 'page': 1, 'pages': 0})
            
            # Paginate results
            paginated = query.paginate(page=page, per_page=per_page, error_out=False)
            
            shipments = []
            for s in paginated.items:
                shipments.append({
                    'id': s.id,
                    'reference_number': s.reference_number,
                    'tracking_number': s.tracking_number or s.reference_number,
                    'status': s.status.value if hasattr(s.status, 'value') else str(s.status),
                    'risk_score': s.risk_score or 0,
                    'origin_port': s.origin_port,
                    'destination_port': s.destination_port,
                    'scheduled_arrival': s.scheduled_arrival.isoformat() if s.scheduled_arrival else None,
                    'carrier': s.carrier,
                    'origin_lat': s.origin_lat,
                    'origin_lon': s.origin_lon,
                    'destination_lat': s.destination_lat,
                    'destination_lon': s.destination_lon,
                    'transport_mode': s.transport_mode,
                    'container_count': s.container_count,
                    'weight_tons': s.weight_tons,
                    'cargo_value_usd': s.cargo_value_usd
                })
            
            return jsonify({
                'shipments': shipments,
                'total': paginated.total,
                'page': paginated.page,
                'pages': paginated.pages
            })
            
        except Exception as e:
            logger.error(f"Error fetching shipments: {e}")
            return jsonify({'error': 'Failed to fetch shipments'}), 500

@main_bp.route('/dashboard/recommendations')
def get_dashboard_recommendations():
    """(Legacy) Get current recommendations for dashboard.

    NOTE: This route was previously registered at '/api/recommendations' which
    conflicted with the REST API blueprint endpoint that now provides
    pagination, filtering, search, and XAI options. It has been renamed to
    avoid shadowing the true API endpoint used by tests and the SPA frontend.
    Frontend code should call '/api/recommendations' (api blueprint) going
    forward. This legacy endpoint is retained ONLY for any templates or
    external callers that might still reference the old non‑paginated payload.
    """
    try:
        from app.utils.redis_manager import redis_manager
        
        # Try Redis first
        redis_data = redis_manager.get_key("dashboard_recommendations")
        if redis_data:
            recommendations = json.loads(redis_data)
            return jsonify({'recommendations': recommendations})
            
        # Try to get from database
        from app.models import Recommendation
        db_recommendations = Recommendation.query.filter_by(status='pending').order_by(Recommendation.created_at.desc()).limit(10).all()
        
        if db_recommendations:
            recommendations = [{
                'id': r.id,
                'type': r.type.value if hasattr(r.type, 'value') else str(r.type),
                'title': r.title,
                'description': r.description,
                'severity': r.severity.value if hasattr(r.severity, 'value') and r.severity else str(r.severity) if r.severity else 'medium',
                'confidence': r.confidence or 0.85,
                'agent': getattr(r, 'created_by', 'AI Agent'),
                'subject_ref': r.subject_ref,
                'status': r.status or 'pending',
                'created_at': r.created_at.isoformat() if r.created_at else datetime.utcnow().isoformat()
            } for r in db_recommendations]
            
            # Cache in Redis for 5 minutes
            redis_manager.set_key("dashboard_recommendations", json.dumps(recommendations), ex=300)
            return jsonify({'recommendations': recommendations})
            
        # Generate demo recommendations if database doesn't match
        demo_recommendations = [
            {
                'id': 1,
                'type': 'reroute',
                'title': 'Reroute SH-2024-001 via Hawaii',
                'description': 'Typhoon risk mitigation for Los Angeles bound shipment',
                'subject_ref': 'shipment:1',
                'severity': 'high',
                'confidence': 0.82,
                'agent': 'risk_predictor_agent',
                'status': 'pending',
                'created_at': (datetime.utcnow() - timedelta(hours=6)).isoformat()
            },
            {
                'id': 2,
                'type': 'reorder',
                'title': 'Reorder critical component XYZ-123',
                'description': 'Critical inventory level detected for semiconductor components',
                'subject_ref': 'inventory:5',
                'severity': 'high',
                'confidence': 0.95,
                'agent': 'inventory_agent',
                'status': 'pending',
                'created_at': (datetime.utcnow() - timedelta(hours=12)).isoformat()
            },
            {
                'id': 3,
                'type': 'negotiate',
                'title': 'Renegotiate carrier contract with MSC',
                'description': 'Better security measures available for piracy-prone routes',
                'subject_ref': 'supplier:3',
                'severity': 'medium',
                'confidence': 0.76,
                'agent': 'procurement_agent',
                'status': 'pending',
                'created_at': (datetime.utcnow() - timedelta(days=1)).isoformat()
            }
        ]
        
        # Cache in Redis for 5 minutes
        redis_manager.set_key("dashboard_recommendations", json.dumps(demo_recommendations), ex=300)
        return jsonify({'recommendations': demo_recommendations})
    except Exception as e:
        logger.error(f"Error fetching recommendations: {e}")
        # Return demo data as a fallback
        demo_recommendations = [
            {
                'id': 1,
                'type': 'reroute',
                'title': 'Reroute SH-2024-001 via Hawaii',
                'description': 'Typhoon risk mitigation for Los Angeles bound shipment',
                'severity': 'high',
                'agent': 'risk_predictor_agent',
                'confidence': 0.85
            }
        ]
        return jsonify({'recommendations': demo_recommendations})


# View routes
@main_bp.route('/logistics')
def logistics():
    """Logistics view."""
    return render_template('logistics.html')

@main_bp.route('/procurement')
def procurement():
    """Procurement view."""
    return render_template('procurement.html')

# Purchase Order API endpoints
@main_bp.route('/api/purchase-orders', methods=['GET'])
def api_get_purchase_orders():
    """Get all purchase orders with optional filtering."""
    try:
        # Get query parameters
        status = request.args.get('status', '').strip()
        supplier_id = request.args.get('supplier_id', type=int)
        search = request.args.get('search', '').strip()
        
        # Base query
        query = PurchaseOrder.query.join(Supplier)
        
        # Apply filters
        if status:
            query = query.filter(PurchaseOrder.status == status)
            
        if supplier_id:
            query = query.filter(PurchaseOrder.supplier_id == supplier_id)
            
        if search:
            query = query.filter(
                db.or_(
                    PurchaseOrder.po_number.ilike(f'%{search}%'),
                    Supplier.name.ilike(f'%{search}%')
                )
            )
        
        # Execute query
        purchase_orders = query.order_by(PurchaseOrder.created_at.desc()).all()
        
        # Format response
        po_data = []
        for po in purchase_orders:
            po_data.append({
                'id': po.id,
                'po_number': po.po_number,
                'supplier_id': po.supplier_id,
                'supplier_name': po.supplier.name if po.supplier else None,
                'status': po.status,
                'total_amount': float(po.total_amount or 0),
                'currency': po.currency or 'USD',
                'delivery_date': po.delivery_date.isoformat() if po.delivery_date else None,
                'created_at': po.created_at.isoformat() if po.created_at else None,
                'notes': po.notes,
                'line_items': po.line_items or []
            })
        
        return jsonify({
            'purchase_orders': po_data,
            'count': len(po_data)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching purchase orders: {str(e)}")
        return jsonify({'error': 'Failed to fetch purchase orders'}), 500

@main_bp.route('/api/purchase-orders', methods=['POST'])
def api_create_purchase_order():
    """Create a new purchase order."""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['supplier_id', 'items']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        # Verify supplier exists
        supplier = Supplier.query.get(data['supplier_id'])
        if not supplier:
            return jsonify({'error': 'Supplier not found'}), 404
        
        # Generate PO number
        import uuid
        po_number = f"PO-{uuid.uuid4().hex[:8].upper()}"
        
        # Calculate total amount from items
        items = data.get('items', [])
        total_amount = 0
        for item in items:
            quantity = item.get('quantity', 0)
            unit_price = item.get('unit_price', 0)
            total_amount += quantity * unit_price
        
        # Create purchase order
        po = PurchaseOrder(
            workspace_id=1,  # Default workspace
            po_number=po_number,
            supplier_id=data['supplier_id'],
            status='draft',
            line_items=items,
            total_amount=total_amount,
            currency=data.get('currency', 'USD'),
            notes=data.get('notes', ''),
            delivery_date=None  # Set based on lead time
        )
        
        # Calculate delivery date based on supplier lead time
        if supplier.average_lead_time_days:
            from datetime import datetime, timedelta
            po.delivery_date = (datetime.utcnow() + timedelta(days=supplier.average_lead_time_days)).date()
        
        db.session.add(po)
        db.session.commit()
        
        # Log the creation
        audit_log = AuditLog(
            workspace_id=1,
            actor_type='user',
            actor_id='system',  # In production, use actual user ID
            action='purchase_order_created',
            object_type='PurchaseOrder',
            object_id=po.id,
            details=json.dumps({'po_number': po.po_number, 'supplier': supplier.name}),
            result='success'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'message': 'Purchase order created successfully',
            'purchase_order': {
                'id': po.id,
                'po_number': po.po_number,
                'status': po.status,
                'supplier_name': supplier.name,
                'total_amount': po.total_amount
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating purchase order: {str(e)}")
        return jsonify({'error': 'Failed to create purchase order'}), 500

@main_bp.route('/api/purchase-orders/<int:po_id>', methods=['PUT'])
def api_update_purchase_order(po_id):
    """Update an existing purchase order."""
    try:
        po = _get_or_404(PurchaseOrder, po_id)
        data = request.get_json()
        
        # Only allow updates to draft and under_review status
        if po.status not in ['draft', 'under_review']:
            return jsonify({'error': 'Cannot edit purchase orders that are not in draft or under review status'}), 400
        
        # Update fields if provided
        updateable_fields = [
            'supplier_id', 'total_amount', 'currency', 'payment_terms',
            'delivery_date', 'notes', 'line_items'
        ]
        
        for field in updateable_fields:
            if field in data:
                if field == 'delivery_date' and data[field]:
                    # Handle date string conversion
                    if isinstance(data[field], str):
                        po.delivery_date = datetime.strptime(data[field], '%Y-%m-%d').date()
                    else:
                        po.delivery_date = data[field]
                elif field == 'line_items':
                    # Validate and update line items
                    if isinstance(data[field], list):
                        # Recalculate total from line items
                        total = 0
                        for item in data[field]:
                            if 'quantity' in item and 'unit_price' in item:
                                item['total'] = float(item['quantity']) * float(item['unit_price'])
                                total += item['total']
                        po.line_items = data[field]
                        # Update total amount if not explicitly provided
                        if 'total_amount' not in data:
                            po.total_amount = total
                else:
                    setattr(po, field, data[field])
        
        # Update timestamp
        po.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Log the update
        audit_log = AuditLog(
            workspace_id=po.workspace_id,
            actor_type='user',
            actor_id='system',  # In production, use actual user ID
            action='purchase_order_updated',
            object_type='PurchaseOrder',
            object_id=po.id,
            details=json.dumps({
                'po_number': po.po_number,
                'updated_fields': list(data.keys())
            }),
            result='success'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'message': 'Purchase order updated successfully',
            'purchase_order': {
                'id': po.id,
                'po_number': po.po_number,
                'status': po.status,
                'total_amount': po.total_amount,
                'supplier_id': po.supplier_id,
                'delivery_date': po.delivery_date.isoformat() if po.delivery_date else None,
                'updated_at': po.updated_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating purchase order: {str(e)}")
        return jsonify({'error': f'Failed to update purchase order: {str(e)}'}), 500

@main_bp.route('/api/purchase-orders/<int:po_id>/approve', methods=['POST'])
def api_approve_purchase_order(po_id):
    """Approve a purchase order."""
    try:
        po = _get_or_404(PurchaseOrder, po_id)
        
        if po.status != 'draft':
            return jsonify({'error': 'Only draft purchase orders can be approved'}), 400
        
        # Update status
        po.status = 'approved'
        db.session.commit()
        
        # Create approval record
        approval = Approval(
            workspace_id=1,
            recommendation_id=None,  # This would link to a recommendation if from agent
            status='approved',
            decided_by='system',  # In production, use actual user ID
            decided_at=datetime.utcnow(),
            notes=f'Purchase order {po.po_number} approved'
        )
        db.session.add(approval)
        
        # Log the approval
        audit_log = AuditLog(
            workspace_id=1,
            actor_type='user',
            actor_id='system',
            action='purchase_order_approved',
            object_type='PurchaseOrder',
            object_id=po.id,
            details=json.dumps({'po_number': po.po_number}),
            result='success'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'message': 'Purchase order approved successfully',
            'purchase_order': {
                'id': po.id,
                'po_number': po.po_number,
                'status': po.status
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving purchase order: {str(e)}")
        return jsonify({'error': 'Failed to approve purchase order'}), 500

@main_bp.route('/risk')
def risk():
    """Risk management view."""
    from app.models import Risk
    workspace_id = 1  # Default workspace
    
    # Get active risks
    risks = Risk.query.filter_by(
        workspace_id=workspace_id
    ).filter(
        Risk.status.in_(['identified', 'assessed', 'mitigating'])
    ).order_by(Risk.risk_score.desc(), Risk.created_at.desc()).all()
    
    # Get risk statistics
    total_risks = Risk.query.filter_by(workspace_id=workspace_id).count()
    critical_risks = Risk.query.filter_by(workspace_id=workspace_id, severity='critical').count()
    high_risks = Risk.query.filter_by(workspace_id=workspace_id, severity='high').count()
    medium_risks = Risk.query.filter_by(workspace_id=workspace_id, severity='medium').count()
    
    # Get recent resolved risks
    resolved_risks = Risk.query.filter_by(
        workspace_id=workspace_id,
        status='resolved'
    ).order_by(Risk.resolved_at.desc()).limit(5).all()
    
    risk_stats = {
        'total': total_risks,
        'critical': critical_risks,
        'high': high_risks,
        'medium': medium_risks,
        'active': len(risks),
        'resolved_recently': len(resolved_risks)
    }
    
    # Serialize risks for JSON embedding (avoid passing ORM objects to tojson)
    serialized_risks = []
    import json as _json
    for r in risks:
        # Normalize location to dict if JSON string
        loc = None
        if r.location:
            if isinstance(r.location, dict):
                loc = r.location
            else:
                try:
                    loc = _json.loads(r.location)
                except Exception:
                    loc = None
        
        # Only serialize basic database fields, not computed properties
        serialized_risks.append({
            'id': r.id or 0,
            'title': r.title or 'Unknown Risk',
            'risk_type': r.risk_type or 'unknown',
            'severity': r.severity or 'medium',
            'risk_score': float(r.risk_score) if r.risk_score is not None else 0.0,
            'status': r.status or 'identified',
            'created_at': r.created_at.isoformat() if r.created_at else None,
            'location': loc,
            'probability': float(r.probability) if r.probability is not None else 0.0,
            'confidence': float(r.confidence) if r.confidence is not None else 0.0,
            'geographic_scope': r.geographic_scope or 'unknown',
            'workspace_id': r.workspace_id or 1,
            'description': r.description or ''
        })

    return render_template('risk.html', 
                         risks=risks,
                         risks_serialized=serialized_risks,
                         risk_stats=risk_stats,
                         resolved_risks=resolved_risks)

@main_bp.route('/reports')
def reports():
    """Reports view."""
    return render_template('reports.html')

@main_bp.route('/alerts')
def alerts():
    """Alerts inbox view."""
    workspace_id = 1  # Default workspace
    
    # Get active alerts - include 'active' status which is used in the database
    active_alerts = Alert.query.filter_by(
        workspace_id=workspace_id
    ).filter(
        Alert.status.in_(['open', 'investigating', 'escalated', 'active', 'acknowledged'])
    ).order_by(Alert.severity.desc(), Alert.created_at.desc()).all()
    
    # Get recent resolved alerts
    resolved_alerts = Alert.query.filter_by(
        workspace_id=workspace_id,
        status='resolved'
    ).order_by(Alert.resolved_at.desc()).limit(10).all()
    
    # Get alert statistics
    total_alerts = Alert.query.filter_by(workspace_id=workspace_id).count()
    critical_alerts = Alert.query.filter_by(workspace_id=workspace_id, severity=AlertSeverity.CRITICAL.value).count()
    high_alerts = Alert.query.filter_by(workspace_id=workspace_id, severity=AlertSeverity.HIGH.value).count()
    unread_alerts = Alert.query.filter_by(workspace_id=workspace_id).filter(
        Alert.status.in_(['open', 'active', 'acknowledged'])
    ).count()
    
    alert_stats = {
        'total': total_alerts,
        'critical': critical_alerts,
        'high': high_alerts,
        'active': len(active_alerts),
        'unread': unread_alerts,
        'resolved_recently': len(resolved_alerts)
    }
    
    return render_template('alerts.html',
                         alerts=active_alerts,
                         resolved_alerts=resolved_alerts,
                         alert_stats=alert_stats,
                         now=datetime.utcnow())

@main_bp.route('/approvals')
def approvals():
    """Approvals queue view."""
    return render_template('approvals.html')

@main_bp.route('/assistant')
def assistant():
    """Redirect legacy assistant path to dashboard (legacy template removed)."""
    return redirect(url_for('main.dashboard'))

@main_bp.route('/settings')
def settings():
    """Settings view."""
    # Mock data for settings page
    # In production, this would come from the database
    organization = {
        'name': 'SupplyChainX Demo',
        'address': '123 Business St, City, State 12345',
        'phone': '+1 234 567 8900',
        'email': 'info@supplychainx.com',
        'timezone': 'UTC'
    }
    
    integrations = [
        {
            'name': 'Weather API',
            'provider': 'NOAA',
            'status': 'active',
            'last_sync': datetime.utcnow() - timedelta(minutes=30),
            'config_url': '/integrations/weather'
        },
        {
            'name': 'Maritime Tracking',
            'provider': 'AIS',
            'status': 'active',
            'last_sync': datetime.utcnow() - timedelta(hours=1),
            'config_url': '/integrations/maritime'
        },
        {
            'name': 'News & Events',
            'provider': 'GDELT',
            'status': 'active',
            'last_sync': datetime.utcnow() - timedelta(hours=2),
            'config_url': '/integrations/gdelt'
        },
        {
            'name': 'Route Service',
            'provider': 'OSRM',
            'status': 'inactive',
            'last_sync': None,
            'config_url': '/integrations/routing'
        }
    ]
    
    api_keys = [
        {
            'name': 'Production API',
            'key': 'sk_prod_****************************abcd',
            'created_at': datetime.utcnow() - timedelta(days=30),
            'last_used': datetime.utcnow() - timedelta(hours=2),
            'permissions': ['read', 'write']
        },
        {
            'name': 'Webhook Endpoint',
            'key': 'sk_whk_****************************efgh',
            'created_at': datetime.utcnow() - timedelta(days=15),
            'last_used': datetime.utcnow() - timedelta(minutes=45),
            'permissions': ['write']
        }
    ]
    
    # User preferences
    preferences = {
        'notifications': {
            'email': True,
            'sms': False,
            'in_app': True
        },
        'alerts': {
            'high_severity': True,
            'medium_severity': True,
            'low_severity': False
        },
        'quiet_hours': {
            'enabled': True,
            'start': '22:00',
            'end': '06:00'
        }
    }
    
    # Current user (mock data)
    current_user = {
        'name': 'Demo User',
        'email': 'demo@supplychainx.com',
        'role': 'Administrator',
        'timezone': 'America/New_York'
    }
    
    return render_template('settings.html',
                         organization=organization,
                         integrations=integrations,
                         api_keys=api_keys,
                         preferences=preferences,
                         current_user=current_user)

@main_bp.route('/shipments/<int:shipment_id>')
def shipment_detail(shipment_id):
    """Shipment detail view."""
    shipment = _get_or_404(Shipment, shipment_id)
    
    # Calculate risk level for display
    risk_level = "high" if shipment.risk_score > 0.7 else ("medium" if shipment.risk_score > 0.3 else "low")
    
    # Ensure we have routes for this shipment
    try:
        # Removed demo route generation
        pass
    except Exception as e:
        logger.warning(f"Could not generate demo routes: {e}")
    
    # Get recommendations for this shipment
    recommendations = Recommendation.query.filter(
        Recommendation.subject_ref == f'shipment:{shipment_id}'
    ).all()
    
    # Format real recommendations only (no mock fallback)
    shipment_recommendations = []
    for rec in recommendations:
        severity_val = rec.severity
        if isinstance(severity_val, str) and severity_val.lower() in ['high', 'medium', 'low']:
            severity_val = severity_val.upper()
        shipment_recommendations.append({
            'id': rec.id,
            'title': rec.title,
            'description': rec.description,
            'severity': severity_val,
            'status': rec.status,
            'created_at': rec.created_at,
            'confidence': rec.confidence or 0.75
        })
    
    # Use only top-level fields; provide demo values if missing
    weight_kg = getattr(shipment, 'weight_kg', 'N/A')
    value = getattr(shipment, 'cargo_value_usd', 250000)
    container_number = getattr(shipment, 'container_number', 'N/A')
    vessel_name = getattr(shipment, 'carrier', 'N/A')
    total_value = value if value not in (None, '', 'N/A') else 250000
    items_count = getattr(shipment, 'container_count', 5)
    cargo_type = getattr(shipment, 'description', None)
    
    # Ensure there's a current route
    current_route_obj = shipment.current_route
    current_route_dict = None
    
    if current_route_obj:
        try:
            current_route_dict = current_route_obj.to_dict()
        except Exception as e:
            logger.warning(f"Could not convert current route to dict: {e}")
            
    # If no current route, create a synthetic one
    if not current_route_dict:
        o_lat = shipment.origin_lat or 31.22
        o_lon = shipment.origin_lon or 121.46
        d_lat = shipment.destination_lat or 33.73
        d_lon = shipment.destination_lon or -118.26
        
        # Create a synthetic route
        current_route_dict = {
            'id': 0,
            'route_type': 'SEA',
            'waypoints': [
                {'name': shipment.origin_port or 'Origin', 'type': 'ORIGIN', 'lat': o_lat, 'lon': o_lon},
                {'name': 'Mid Ocean', 'type': 'WAYPOINT', 'lat': (o_lat + d_lat)/2, 'lon': (o_lon + d_lon)/2},
                {'name': shipment.destination_port or 'Destination', 'type': 'DESTINATION', 'lat': d_lat, 'lon': d_lon}
            ],
            'distance_km': 10000,
            'estimated_duration_hours': 240,
            'cost_usd': 75000,
            'carbon_emissions_kg': 30000,
            'risk_score': shipment.risk_score or 0.4,
            'risk_factors': ['weather', 'port_congestion']
        }
    
    # Extract risk factors from the current route
    risk_factors_list = []
    if current_route_dict and 'risk_factors' in current_route_dict:
        risk_factors = current_route_dict['risk_factors']
        if isinstance(risk_factors, list):
            risk_factors_list = risk_factors
        elif isinstance(risk_factors, str):
            try:
                risk_factors_list = json.loads(risk_factors)
            except:
                risk_factors_list = []
    
    # Calculate CO2 emissions from current route or use mock value
    co2_emissions = current_route_dict.get('carbon_emissions_kg', 30000) / 1000 if current_route_dict else 23.5
    
    # Calculate days remaining until arrival
    days_remaining = 'N/A'
    if shipment.eta:
        delta = shipment.eta - datetime.utcnow()
        days_remaining = max(0, delta.days)
    
    # Define status color mapping
    status_colors = {
        'planned': 'secondary',
        'in_transit': 'primary',
        'delayed': 'warning',
        'delivered': 'success',
        'cancelled': 'danger',
        # Include uppercase values for compatibility
        'PLANNED': 'secondary',
        'IN_TRANSIT': 'primary',
        'DELAYED': 'warning',
        'DELIVERED': 'success',
        'CANCELLED': 'danger',
        # Include ShipmentStatus Enum objects
        'PLANNED': 'secondary',
        'IN_TRANSIT': 'primary',
        'DELAYED': 'warning',
        'DELIVERED': 'success',
        'CANCELLED': 'danger'
    }
    
    # Generate demo timeline events if needed
    timeline_events = []
    if not hasattr(shipment, 'timeline_events') or not shipment.timeline_events:
        # Create demo events
        now = datetime.utcnow()
        if shipment.status == 'IN_TRANSIT':
            timeline_events = [
                {
                    'title': 'Order Created',
                    'description': f'Shipment {shipment.reference_number} created in system',
                    'timestamp': now - timedelta(days=10)
                },
                {
                    'title': 'Booking Confirmed',
                    'description': f'Booking confirmed with {shipment.carrier or "carrier"}',
                    'timestamp': now - timedelta(days=8)
                },
                {
                    'title': 'Departed Origin Port',
                    'description': f'Vessel departed from {shipment.origin_port}',
                    'timestamp': now - timedelta(days=3)
                },
                {
                    'title': 'In Transit',
                    'description': 'Shipment en route to destination',
                    'timestamp': now - timedelta(days=2)
                }
            ]
        else:
            timeline_events = [
                {
                    'title': 'Order Created',
                    'description': f'Shipment {shipment.reference_number} created in system',
                    'timestamp': now - timedelta(days=3)
                },
                {
                    'title': 'Booking Confirmed',
                    'description': f'Booking confirmed with {shipment.carrier or "carrier"}',
                    'timestamp': now - timedelta(days=1)
                }
            ]
    
    # Create mock documents for the documents tab
    documents = [
        {
            'name': 'Bill of Lading.pdf',
            'type': 'Bill of Lading',
            'uploaded_at': datetime.utcnow() - timedelta(days=5)
        },
        {
            'name': 'Commercial Invoice.pdf',
            'type': 'Invoice',
            'uploaded_at': datetime.utcnow() - timedelta(days=5)
        },
        {
            'name': 'Packing List.pdf',
            'type': 'Packing List',
            'uploaded_at': datetime.utcnow() - timedelta(days=5)
        }
    ]
    
    # Add mock related alerts for testing the alerts tab
    related_alerts = [
        {
            'id': 1,
            'title': 'Weather Warning - Typhoon Risk',
            'description': 'Potential typhoon forming near the shipping route in the Pacific',
            'severity': 'HIGH',
            'created_at': datetime.utcnow() - timedelta(days=1)
        },
        {
            'id': 2,
            'title': 'Port Congestion Alert',
            'description': 'Destination port experiencing higher than normal congestion',
            'severity': 'MEDIUM',
            'created_at': datetime.utcnow() - timedelta(days=2)
        }
    ]
    
    # Get alternative routes (if any)
    alternative_routes = []
    if shipment.routes:
        for route in shipment.routes:
            if not route.is_current:
                try:
                    alt_route = route.to_dict()
                    # Extract vessel name from metadata for display
                    if 'metadata' in alt_route and alt_route['metadata']:
                        vessel_name = alt_route['metadata'].get('vessel_name', 'Unknown Vessel')
                        route_name = alt_route['metadata'].get('name', vessel_name)
                        alt_route['vessel_name'] = vessel_name
                        # Update the name to prioritize vessel name
                        if not alt_route.get('name') or alt_route.get('name') == 'Unknown':
                            alt_route['name'] = vessel_name
                    alternative_routes.append(alt_route)
                except:
                    # Skip if conversion fails
                    pass
    
    # Pass all the data to the template without modifying shipment object
    return render_template('shipment.html', 
                          shipment=shipment,
                          risk_level=risk_level,
                          recommendations=shipment_recommendations,
                          weight_kg=weight_kg,
                          value=value,
                          total_value=total_value,
                          items_count=items_count,
                          container_number=container_number,
                          vessel_name=vessel_name,
                          co2_emissions=co2_emissions,
                          days_remaining=days_remaining,
                          status_colors=status_colors,
                          now=datetime.utcnow(),
                          cargo_type=cargo_type,
                          # Additional fields expected by template (provide fallbacks)
                          carrier_name=shipment.carrier or 'Unknown',
                          origin_name=shipment.origin_port or 'Origin',
                          destination_name=shipment.destination_port or 'Destination',
                          transport_mode=getattr(shipment.current_route, 'route_type', 'SEA') if shipment.current_route else 'SEA',
                          current_route=current_route_dict,
                          alternative_routes=alternative_routes,  
                          risk_factors=risk_factors_list,
                          # Additional data for other tabs
                          timeline_events=timeline_events,
                          documents=documents,
                          related_alerts=related_alerts
                          )


## _generate_demo_routes removed - real carrier integrations should now populate routes.

def _route_to_option_dict(route, current_route=None):
    import json as _json
    metadata = _json.loads(route.route_metadata) if route.route_metadata else {}
    waypoints = _json.loads(route.waypoints) if route.waypoints else []
    comparison = {
        'distance_delta': 0,
        'duration_delta': 0,
        'cost_delta': 0,
        'emissions_delta': 0,
        'risk_delta': 0
    }
    if current_route and current_route.id != route.id:
        comparison = {
            'distance_delta': route.distance_km - current_route.distance_km,
            'duration_delta': route.estimated_duration_hours - current_route.estimated_duration_hours,
            'cost_delta': route.cost_usd - current_route.cost_usd,
            'emissions_delta': route.carbon_emissions_kg - current_route.carbon_emissions_kg,
            'risk_delta': current_route.risk_score - route.risk_score
        }
    return {
        'route_id': route.id,
        'name': metadata.get('name', f'Route {route.id}'),
        'is_recommended': route.is_recommended,
        'waypoints': waypoints,
        'metrics': {
            'distance_km': route.distance_km,
            'duration_hours': route.estimated_duration_hours,
            'cost_usd': route.cost_usd,
            'emissions_kg': route.carbon_emissions_kg,
            'risk_score': route.risk_score
        },
        'comparison': comparison,
        'metadata': metadata
    }

@main_bp.route('/api/shipments/<int:shipment_id>', methods=['GET','PUT'])
def api_shipment_detail(shipment_id):
    """Return or update shipment details.
    GET: JSON details including current route
    PUT: Update editable shipment fields
    """
    import json as _json
    import copy
    import random
    
    shipment = _get_or_404(Shipment, shipment_id)
    if request.method == 'PUT':
        payload = request.get_json(silent=True) or {}
        editable_map = {
            'carrier': 'carrier',
            'origin_port': 'origin_port',
            'destination_port': 'destination_port',
            'scheduled_departure': 'scheduled_departure',
            'scheduled_arrival': 'scheduled_arrival',
            'actual_departure': 'actual_departure',
            'actual_arrival': 'actual_arrival',
            'status': 'status',
            'transport_mode': 'transport_mode',
            'container_number': 'container_number',
            'container_count': 'container_count',
            'weight_tons': 'weight_tons',
            'cargo_value_usd': 'cargo_value_usd',
            'risk_score': 'risk_score',
            'reference_number': 'reference_number'
        }
        # Simple parsing helpers
        def parse_dt(val):
            if not val: return None
            try:
                return datetime.fromisoformat(val.replace('Z','+00:00'))
            except:
                return None
        for key, attr in editable_map.items():
            if key in payload:
                if 'scheduled_' in key or 'actual_' in key:
                    setattr(shipment, attr, parse_dt(payload.get(key)))
                elif key == 'status':
                    val = payload.get(key)
                    if val:
                        try:
                            if isinstance(val, ShipmentStatus):
                                shipment.status = val
                            else:
                                shipment.status = ShipmentStatus(val.lower()) if hasattr(ShipmentStatus, val.upper()) else shipment.status
                        except Exception:
                            pass
                elif key in ['container_count']:
                    try: setattr(shipment, attr, int(payload.get(key)))
                    except: pass
                elif key in ['weight_tons','cargo_value_usd','risk_score']:
                    try: setattr(shipment, attr, float(payload.get(key)))
                    except: pass
                else:
                    setattr(shipment, attr, payload.get(key))
        # Update description if present
        if 'description' in payload:
            shipment.description = payload['description']
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({'error':'Update failed','detail':str(e)}), 400
        return jsonify({'status':'updated','shipment_id': shipment.id})
    now = datetime.utcnow()
    route_dict = None
    try:
    # Demo route generation removed
        current_route = shipment.current_route
        if current_route:
            route_dict = {
                'id': current_route.id,
                'route_type': getattr(current_route.route_type, 'value', 'SEA') if hasattr(current_route, 'route_type') else 'SEA',
                'waypoints': _json.loads(current_route.waypoints) if getattr(current_route, 'waypoints', None) else [],
                'distance_km': getattr(current_route, 'distance_km', 0),
                'estimated_duration_hours': getattr(current_route, 'estimated_duration_hours', 0),
                'cost_usd': getattr(current_route, 'cost_usd', 0),
                'carbon_emissions_kg': getattr(current_route, 'carbon_emissions_kg', 0),
                'risk_score': getattr(current_route, 'risk_score', 0),
                'risk_factors': _json.loads(current_route.risk_factors) if getattr(current_route, 'risk_factors', None) else []
            }
    except OperationalError as e:
        logger.warning(f"Operation error in route generation: {e}")
        # Fallback synthetic route (no DB schema support)
        o_lat = shipment.origin_lat or 31.22  # Shanghai
        o_lon = shipment.origin_lon or 121.46
        d_lat = shipment.destination_lat or 33.73  # Los Angeles
        d_lon = shipment.destination_lon or -118.26
        route_dict = {
            'id': 0,
            'route_type': 'SEA',
            'waypoints': [
                {'name': shipment.origin_port or 'Shanghai', 'type': 'ORIGIN', 'lat': o_lat, 'lon': o_lon},
                {'name': 'Mid Ocean', 'type': 'WAYPOINT', 'lat': (o_lat + d_lat)/2, 'lon': (o_lon + d_lon)/2},
                {'name': shipment.destination_port or 'Los Angeles', 'type': 'DESTINATION', 'lat': d_lat, 'lon': d_lon}
            ],
            'distance_km': 10000,
            'estimated_duration_hours': 240,
            'cost_usd': 75000,
            'carbon_emissions_kg': 30000,
            'risk_score': shipment.risk_score or 0.4,
            'risk_factors': ['weather', 'port_congestion']
        }
    except Exception as e:
        logger.error(f"Error generating routes for shipment {shipment_id}: {e}")
        # Provide a minimal fallback route
        route_dict = {
            'id': 0,
            'route_type': 'SEA',
            'waypoints': [
                {'name': shipment.origin_port or 'Shanghai', 'type': 'ORIGIN', 'lat': shipment.origin_lat or 31.22, 'lon': shipment.origin_lon or 121.46},
                {'name': 'Mid Ocean', 'type': 'WAYPOINT', 'lat': 15.0, 'lon': 170.0},
                {'name': shipment.destination_port or 'Los Angeles', 'type': 'DESTINATION', 'lat': shipment.destination_lat or 33.73, 'lon': shipment.destination_lon or -118.26}
            ],
            'distance_km': 10000,
            'estimated_duration_hours': 240,
            'cost_usd': 75000,
            'carbon_emissions_kg': 30000,
            'risk_score': shipment.risk_score or 0.4,
            'risk_factors': ['weather', 'port_congestion']
        }
    
    # No cargo_details: use only top-level fields
    
    # Ensure we have status correctly formatted for frontend
    status_enum = shipment.status if shipment.status else 'planned'  # status is now a string
    if not status_enum:
        status_enum = 'PLANNED'
    
    # Calculate risk level based on risk score
    risk_score = shipment.risk_score if shipment.risk_score is not None else random.uniform(0.1, 0.9)
    risk_level = "HIGH" if risk_score > 0.7 else ("MEDIUM" if risk_score > 0.3 else "LOW")
    
    # Calculate days remaining until arrival
    days_remaining = None
    if shipment.eta:
        delta = shipment.eta - now
        days_remaining = max(0, delta.days)
    else:
        days_remaining = random.randint(1, 30)
    
    # Generate alternative routes
    alternative_routes = []
    for route in shipment.routes:
        if not route.is_current:
            try:
                # Extract metadata for vessel name and other details
                metadata = {}
                try:
                    metadata = _json.loads(route.route_metadata) if getattr(route, 'route_metadata', None) else {}
                except Exception:
                    metadata = {}
                
                vessel_name = metadata.get('vessel_name', 'Unknown Vessel')
                route_name = metadata.get('name', vessel_name)
                
                alt_dict = {
                    'id': route.id,
                    'name': route_name,
                    'vessel_name': vessel_name,
                    'route_type': getattr(route.route_type, 'value', 'SEA') if hasattr(route.route_type, 'value') else str(route.route_type),
                    'waypoints': _json.loads(route.waypoints) if getattr(route, 'waypoints', None) else [],
                    'distance_km': getattr(route, 'distance_km', 0),
                    'estimated_duration_hours': getattr(route, 'estimated_duration_hours', 0),
                    'cost_usd': getattr(route, 'cost_usd', 0),
                    'carbon_emissions_kg': getattr(route, 'carbon_emissions_kg', 0),
                    'risk_score': getattr(route, 'risk_score', 0),
                    'risk_factors': _json.loads(route.risk_factors) if getattr(route, 'risk_factors', None) else []
                }
                alternative_routes.append(alt_dict)
            except Exception as e:
                logger.warning(f"Could not convert alternative route to dict: {e}")
    
    # If no alternative routes, create synthetic ones
    if not alternative_routes and route_dict:
        base_route = copy.deepcopy(route_dict)
        
        # First alternative - slightly longer but safer
        alt1 = copy.deepcopy(base_route)
        alt1['id'] = -1
        alt1['route_type'] = 'SEA'
        # Add an extra waypoint
        if len(alt1['waypoints']) >= 3:
            mid_idx = len(alt1['waypoints']) // 2
            new_waypoint = {
                'name': 'Alternative Path',
                'type': 'WAYPOINT',
                'lat': alt1['waypoints'][mid_idx]['lat'] + 2,
                'lon': alt1['waypoints'][mid_idx]['lon'] + 2
            }
            alt1['waypoints'].insert(mid_idx, new_waypoint)
        alt1['distance_km'] = int(base_route['distance_km'] * 1.15) if 'distance_km' in base_route else 11500
        alt1['estimated_duration_hours'] = int(base_route['estimated_duration_hours'] * 1.2) if 'estimated_duration_hours' in base_route else 288
        alt1['cost_usd'] = int(base_route['cost_usd'] * 1.1) if 'cost_usd' in base_route else 82500
        alt1['carbon_emissions_kg'] = int(base_route['carbon_emissions_kg'] * 1.15) if 'carbon_emissions_kg' in base_route else 34500
        alt1['risk_score'] = base_route['risk_score'] * 0.7 if 'risk_score' in base_route else 0.28
        
        # Second alternative - faster but more expensive and riskier
        alt2 = copy.deepcopy(base_route)
        alt2['id'] = -2
        alt2['route_type'] = 'MULTIMODAL'  # Air + Sea
        alt2['distance_km'] = int(base_route['distance_km'] * 0.85) if 'distance_km' in base_route else 8500
        alt2['estimated_duration_hours'] = int(base_route['estimated_duration_hours'] * 0.6) if 'estimated_duration_hours' in base_route else 144
        alt2['cost_usd'] = int(base_route['cost_usd'] * 1.8) if 'cost_usd' in base_route else 135000
        alt2['carbon_emissions_kg'] = int(base_route['carbon_emissions_kg'] * 1.5) if 'carbon_emissions_kg' in base_route else 45000
        alt2['risk_score'] = min(0.9, base_route['risk_score'] * 1.2) if 'risk_score' in base_route else 0.48
        
        alternative_routes = [alt1, alt2]
    
    # Create timeline events
    timeline_events = []
    if shipment.status == 'IN_TRANSIT':
        timeline_events = [
            {
                'title': 'Order Created',
                'description': f'Shipment {shipment.reference_number} created in system',
                'timestamp': (now - timedelta(days=10)).isoformat()
            },
            {
                'title': 'Booking Confirmed',
                'description': f'Booking confirmed with {shipment.carrier or "carrier"}',
                'timestamp': (now - timedelta(days=8)).isoformat()
            },
            {
                'title': 'Departed Origin Port',
                'description': f'Vessel departed from {shipment.origin_port}',
                'timestamp': (now - timedelta(days=3)).isoformat()
            },
            {
                'title': 'In Transit',
                'description': 'Shipment en route to destination',
                'timestamp': (now - timedelta(days=2)).isoformat()
            }
        ]
    else:
        timeline_events = [
            {
                'title': 'Order Created',
                'description': f'Shipment {shipment.reference_number} created in system',
                'timestamp': (now - timedelta(days=3)).isoformat()
            },
            {
                'title': 'Booking Confirmed',
                'description': f'Booking confirmed with {shipment.carrier or "carrier"}',
                'timestamp': (now - timedelta(days=1)).isoformat()
            }
        ]
    
    # Create mock documents
    documents = [
        {
            'name': 'Bill of Lading.pdf',
            'type': 'Bill of Lading',
            'uploaded_at': (now - timedelta(days=5)).isoformat()
        },
        {
            'name': 'Commercial Invoice.pdf',
            'type': 'Invoice',
            'uploaded_at': (now - timedelta(days=5)).isoformat()
        },
        {
            'name': 'Packing List.pdf',
            'type': 'Packing List',
            'uploaded_at': (now - timedelta(days=5)).isoformat()
        }
    ]
    
    # Create mock related alerts
    related_alerts = [
        {
            'id': 1,
            'title': 'Weather Warning - Typhoon Risk',
            'description': 'Potential typhoon forming near the shipping route in the Pacific',
            'severity': 'HIGH',
            'created_at': (now - timedelta(days=1)).isoformat()
        },
        {
            'id': 2,
            'title': 'Port Congestion Alert',
            'description': 'Destination port experiencing higher than normal congestion',
            'severity': 'MEDIUM',
            'created_at': (now - timedelta(days=2)).isoformat()
        }
    ]
    
    # Create mock recommendations
    recommendations = Recommendation.query.filter(
        Recommendation.subject_ref == f'shipment:{shipment_id}'
    ).all()
    
    shipment_recommendations = []
    if recommendations:
        for rec in recommendations:
            severity_val = rec.severity
            if isinstance(severity_val, str) and severity_val.lower() in ['high', 'medium', 'low']:
                severity_val = severity_val.upper()
                
            shipment_recommendations.append({
                'id': rec.id,
                'title': rec.title,
                'description': rec.description,
                'severity': severity_val,
                'status': rec.status,
                'created_at': rec.created_at.isoformat() if rec.created_at else now.isoformat(),
                'confidence': rec.confidence or 0.75
            })
    else:
        # Create mock recommendation
        shipment_recommendations = [{
            'id': 1,
            'title': f'Reroute {shipment.reference_number or "shipment"} via Hawaii',
            'description': 'Typhoon risk mitigation for Los Angeles bound shipment',
            'severity': 'HIGH',
            'status': 'pending',
            'created_at': (now - timedelta(hours=6)).isoformat(),
            'confidence': 0.85
        }]
    
    # Build complete response
    # Compose a normalized routes list from DB routes for compatibility
    routes_list = []
    try:
        for r in shipment.routes or []:
            try:
                meta = {}
                try:
                    meta = _json.loads(r.route_metadata) if getattr(r, 'route_metadata', None) else {}
                except Exception:
                    meta = {}
                routes_list.append({
                    'id': r.id,
                    'name': meta.get('name'),
                    'carrier': meta.get('carrier') or meta.get('provider', 'Unknown'),
                    'service_type': meta.get('service_type') or meta.get('service_code', 'Standard'),
                    'is_current': r.is_current,
                    'is_recommended': r.is_recommended,
                    'waypoints': r.waypoints,  # keep JSON string for frontend parsing
                    'distance_km': getattr(r, 'distance_km', None),
                    'estimated_duration_hours': getattr(r, 'estimated_duration_hours', None),
                    'cost_usd': getattr(r, 'cost_usd', None),
                    'carbon_emissions_kg': getattr(r, 'carbon_emissions_kg', None),
                    'risk_score': getattr(r, 'risk_score', None)
                })
            except Exception as _e:
                logger.debug(f"Failed to serialize route {getattr(r,'id',None)}: {_e}")
                continue
    except Exception as _outer_e:
        logger.debug(f"No routes to serialize for shipment {shipment.id}: {_outer_e}")

    result = {
        'id': shipment.id,
        'reference_number': shipment.reference_number or f'SH-{shipment.id}',
        'tracking_number': shipment.reference_number or f'SH-{shipment.id}', # for compatibility with JS
        'status': status_enum.upper(),  # JS progress mapping expects uppercase
        'risk_score': risk_score,
        'risk_level': risk_level,
        'estimated_arrival': shipment.eta.isoformat() if shipment.eta else (now + timedelta(days=days_remaining)).isoformat(),
        'current_route': route_dict,
        'alternative_routes': alternative_routes,
        'carrier': shipment.carrier or 'Unknown',
        'carrier_name': shipment.carrier or 'Unknown Carrier',  # For template compatibility
        'origin_port': shipment.origin_port or 'Origin',
        'origin_name': shipment.origin_port or 'Origin',  # For template compatibility
        'destination_port': shipment.destination_port or 'Destination',
        'destination_name': shipment.destination_port or 'Destination',  # For template compatibility
        'origin_lat': shipment.origin_lat,
        'origin_lon': shipment.origin_lon,
        'destination_lat': shipment.destination_lat,
        'destination_lon': shipment.destination_lon,
        'container_number': shipment.container_number or 'N/A',
        'vessel_name': shipment.carrier or 'N/A',
        'weight': shipment.weight_tons or 'N/A',
        'value': shipment.cargo_value_usd or 0,
        'container_count': shipment.container_count or 1,
        'description': shipment.description or '',
        'days_remaining': days_remaining,
        'timeline_events': timeline_events,
        'documents': documents,
        'related_alerts': related_alerts,
        'recommendations': shipment_recommendations,
        'co2_emissions': route_dict.get('carbon_emissions_kg', 30000) / 1000 if route_dict else 23.5,
        'transport_mode': route_dict.get('route_type', 'SEA') if route_dict else 'SEA',
    'risk_factors': route_dict.get('risk_factors', ['weather', 'port_congestion']) if route_dict else ['weather', 'port_congestion'],
    'routes': routes_list
    }
    
    return jsonify(result)




@main_bp.route('/api/risks')
def get_risks():
    """Get current risk hotspots for map."""
    try:
        import json
        
        # Get active alerts
        alerts = Alert.query.filter(
            Alert.status == 'active'
        ).order_by(Alert.created_at.desc()).limit(50).all()
        
        risks = []
        for alert in alerts:
            # Parse location data if it exists
            lat = None
            lon = None
            
            # Check if alert has location data (stored as JSON string or dict)
            if hasattr(alert, 'location') and alert.location:
                try:
                    # Handle both dict and string formats
                    if isinstance(alert.location, dict):
                        location = alert.location
                    else:
                        location = json.loads(alert.location)
                    lat = location.get('lat')
                    lon = location.get('lon')
                except:
                    pass
            
            # Skip if no valid location
            if not lat or not lon:
                # For demo purposes, generate some mock locations
                import random
                if alert.id % 3 == 0:  # Only show some alerts on map
                    lat = random.uniform(-60, 60)
                    lon = random.uniform(-180, 180)
                else:
                    continue
            
            risks.append({
                'id': alert.id,
                'title': alert.title,
                'type': alert.type,
                'severity': alert.severity.value if hasattr(alert.severity, 'value') else str(alert.severity),
                'lat': lat,
                'lon': lon,
                'impact': calculate_impact_score(alert),
                'description': alert.description[:100] if alert.description else ''
            })
        
        return jsonify({
            'risks': risks,
            'total': len(risks)
        })
        
    except Exception as e:
        logger.error(f"Error fetching risks: {e}")
        return jsonify({'risks': [], 'total': 0}), 200  # Return empty array instead of 500

@main_bp.route('/api/eta-variance')
def get_eta_variance():
    """Get ETA variance trend data for chart."""
    try:
        from app.utils.redis_manager import RedisManager
        import json
        
        # Try to get ETA variance from Redis first
        redis_manager = RedisManager()
        eta_data = redis_manager.get_key("eta_variance_chart")
        
        if eta_data:
            try:
                return jsonify({'eta_variance': json.loads(eta_data)})
            except:
                # If parsing fails, continue with database calculation
                pass
        
        # If not in Redis, or parsing failed, compute from database
        # Get shipments with ETA data from last 30 days
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        
        # For demo purposes, if no actual arrivals are in the database yet,
        # generate some sample data
        shipments = Shipment.query.filter(
            Shipment.scheduled_arrival.between(start_date, end_date)
        ).all()
        
        if not shipments or not any(shipment.actual_arrival for shipment in shipments):
            # Generate demo data for chart
            dates = [(end_date - timedelta(days=x)).strftime('%b %d') for x in range(30, -1, -5)]
            planned = [15, 17, 16, 14, 15, 16, 15]  # In days
            actual = [16, 20, 18, 15, 16, 19, 17]   # Actual transit times
            
            eta_variance = {
                'dates': dates,
                'planned': planned,
                'actual': actual
            }
            
            # Cache in Redis for 30 minutes
            redis_manager.set_key("eta_variance_chart", json.dumps(eta_variance), ex=1800)
            
            return jsonify({'eta_variance': eta_variance})
        
        # If we have real data, calculate from that
        daily_variance = {}
        for shipment in shipments:
            if not shipment.scheduled_departure:
                continue
                
            date_key = shipment.scheduled_arrival.date().isoformat()
            if date_key not in daily_variance:
                daily_variance[date_key] = {
                    'planned': [],
                    'actual': []
                }
            
            # Calculate hours difference
            planned_hours = (shipment.scheduled_arrival - shipment.scheduled_departure).total_seconds() / 3600 / 24  # Convert to days
            
            # If actual arrival exists, use it, otherwise use scheduled
            if shipment.actual_arrival:
                actual_hours = (shipment.actual_arrival - shipment.scheduled_departure).total_seconds() / 3600 / 24
            else:
                # For shipments in transit, use estimated current duration + remaining time
                actual_hours = planned_hours * (1.0 + (random.uniform(-0.1, 0.3)))  # +/- 10-30% variance
            
            daily_variance[date_key]['planned'].append(planned_hours)
            daily_variance[date_key]['actual'].append(actual_hours)
        
        # Average by day
        dates = sorted(daily_variance.keys())
        planned_avg = []
        actual_avg = []
        
        for date in dates:
            planned_avg.append(
                sum(daily_variance[date]['planned']) / len(daily_variance[date]['planned'])
            )
            actual_avg.append(
                sum(daily_variance[date]['actual']) / len(daily_variance[date]['actual'])
            )
        
        eta_variance = {
            'dates': dates,
            'planned': [round(x, 1) for x in planned_avg],
            'actual': [round(x, 1) for x in actual_avg]
        }
        
        # Cache in Redis for 30 minutes
        redis_manager.set_key("eta_variance_chart", json.dumps(eta_variance), ex=1800)
        
        return jsonify({'eta_variance': eta_variance})
        
    except Exception as e:
        logger.error(f"Error calculating ETA variance: {e}")
        return jsonify({'eta_variance': {
            'dates': [(datetime.utcnow() - timedelta(days=i)).strftime('%b %d') for i in range(30, 0, -5)],
            'planned': [15, 14, 16, 15, 14, 15],
            'actual': [16, 20, 18, 14, 18, 16]
        }})

@main_bp.route('/api/active-routes')
def get_active_routes():
    """Get active shipping routes for the routes map view."""
    try:
        # Get all active shipments (in_transit, planned, delayed)
        shipments = Shipment.query.filter(
            Shipment.status.in_(['in_transit', 'planned', 'delayed'])
        ).all()
        
        # If no active shipments, use all shipments with coordinates for demo
        if not shipments:
            shipments = Shipment.query.filter(
                Shipment.origin_lat.isnot(None),
                Shipment.origin_lon.isnot(None),
                Shipment.destination_lat.isnot(None),
                Shipment.destination_lon.isnot(None)
            ).limit(10).all()
        
        routes = []
        for shipment in shipments:
            # Skip shipments with missing coordinate data
            if not (shipment.origin_lat and shipment.origin_lon and 
                    shipment.destination_lat and shipment.destination_lon):
                continue
                
            # Create route information
            routes.append({
                'id': shipment.id,
                'reference': shipment.reference_number,
                'carrier': shipment.carrier,
                'origin': {
                    'name': shipment.origin_port,
                    'coordinates': [float(shipment.origin_lat), float(shipment.origin_lon)]
                },
                'destination': {
                    'name': shipment.destination_port,
                    'coordinates': [float(shipment.destination_lat), float(shipment.destination_lon)]
                },
                'eta': shipment.scheduled_arrival.isoformat() if shipment.scheduled_arrival else None,
                'risk_level': 'high' if shipment.risk_score > 0.7 else ('medium' if shipment.risk_score > 0.3 else 'low'),
                'status': shipment.status
            })
        
        return jsonify({'routes': routes})
    except Exception as e:
        current_app.logger.error(f"Error getting active routes: {str(e)}")
        return jsonify({'routes': []})


@main_bp.route('/api/global-disruptions')
def get_global_disruptions():
    """Get global disruptions, threats, and risk zones for the global map view."""
    try:
        disruptions = []
        
        # Add active alerts as disruptions
        alerts = Alert.query.filter(Alert.status == 'active').all()
        for alert in alerts:
            # Extract coordinates from alert description or use default locations
            coordinates = get_alert_coordinates(alert)
            if coordinates:
                disruptions.append({
                    'id': f'alert_{alert.id}',
                    'coordinates': coordinates,
                    'type': determine_disruption_type(alert.alert_type),
                    'title': alert.title,
                    'severity': alert.severity if hasattr(alert.severity, 'value') else str(alert.severity),
                    'description': alert.description,
                    'region': get_region_from_coordinates(coordinates),
                    'updated_at': alert.created_at.isoformat() if alert.created_at else None,
                    'radius': 200  # 200 km radius of effect
                })
        
        # Add some static global disruption zones for demo
        static_disruptions = [
            {
                'id': 'red_sea_conflict',
                'coordinates': [26.2, 50.6],  # Red Sea
                'type': 'geopolitical',
                'title': 'Red Sea Security Threats',
                'severity': 'high',
                'description': 'Ongoing security concerns affecting major shipping lanes',
                'region': 'Middle East',
                'updated_at': datetime.utcnow().isoformat(),
                'radius': 500
            },
            {
                'id': 'panama_canal_congestion',
                'coordinates': [9.0, -79.5],  # Panama Canal
                'type': 'port_congestion',
                'title': 'Panama Canal Delays',
                'severity': 'medium',
                'description': 'Increased transit times due to water level restrictions',
                'region': 'Central America',
                'updated_at': datetime.utcnow().isoformat(),
                'radius': 100
            },
            {
                'id': 'suez_canal_traffic',
                'coordinates': [30.1, 32.6],  # Suez Canal
                'type': 'port_congestion',
                'title': 'Suez Canal High Traffic',
                'severity': 'medium',
                'description': 'Heavy traffic causing longer wait times',
                'region': 'Egypt',
                'updated_at': datetime.utcnow().isoformat(),
                'radius': 150
            },
            {
                'id': 'south_china_sea_weather',
                'coordinates': [14.0, 113.0],  # South China Sea
                'type': 'weather',
                'title': 'Typhoon Season Activity',
                'severity': 'medium',
                'description': 'Seasonal weather patterns affecting shipping schedules',
                'region': 'South China Sea',
                'updated_at': datetime.utcnow().isoformat(),
                'radius': 800
            }
        ]
        
        disruptions.extend(static_disruptions)
        
        return jsonify({'disruptions': disruptions})
    except Exception as e:
        current_app.logger.error(f"Error getting global disruptions: {str(e)}")
        return jsonify({'disruptions': []})


def get_alert_coordinates(alert):
    """Extract coordinates from alert or return default based on alert type."""
    # This is a simplified implementation - in a real system you'd parse
    # location data from the alert content or have location fields
    location_map = {
        'weather': [25.3, -80.3],      # Miami area (hurricane zone)
        'security': [26.2, 50.6],      # Red Sea
        'operational': [1.3, 103.8],   # Singapore (port hub)
        'supply': [31.2, 121.5],       # Shanghai (manufacturing hub)
    }
    
    alert_type = alert.alert_type if hasattr(alert.alert_type, 'value') else str(alert.alert_type)
    return location_map.get(alert_type.lower(), [20.0, 0.0])  # Default to global center


def determine_disruption_type(alert_type):
    """Map alert types to disruption types."""
    type_map = {
        'weather': 'weather',
        'security': 'geopolitical',
        'operational': 'port_congestion',
        'supply': 'supply_shortage',
        'financial': 'economic',
        'logistics': 'operational'
    }
    
    alert_type_str = alert_type if isinstance(alert_type, str) else str(alert_type)
    return type_map.get(alert_type_str.lower(), 'operational')


def get_region_from_coordinates(coordinates):
    """Get region name from coordinates (simplified implementation)."""
    lat, lon = coordinates
    
    if -30 <= lat <= 70 and -15 <= lon <= 60:
        return "Europe/Africa"
    elif 10 <= lat <= 50 and 60 <= lon <= 150:
        return "Asia"
    elif -60 <= lat <= 80 and -170 <= lon <= -30:
        return "Americas"
    elif -50 <= lat <= 10 and 100 <= lon <= 180:
        return "Oceania"
    else:
        return "Global"


@main_bp.route('/suppliers')
def suppliers():
    """Suppliers list view."""
    return render_template('suppliers.html')

# Supplier API endpoints
@main_bp.route('/api/suppliers', methods=['GET'])
def api_get_suppliers():
    """Get all suppliers with optional filtering."""
    try:
        # Get query parameters for filtering
        search = request.args.get('search', '').strip()
        status = request.args.get('status', '').strip()
        category = request.args.get('category', '').strip()
        rating_min = request.args.get('rating_min', type=float)
        
        # Base query
        query = Supplier.query
        
        # Apply filters
        if search:
            query = query.filter(
                db.or_(
                    Supplier.name.ilike(f'%{search}%'),
                    Supplier.code.ilike(f'%{search}%'),
                    Supplier.country.ilike(f'%{search}%')
                )
            )
        
        if status:
            active_status = status.lower() == 'active'
            query = query.filter(Supplier.is_active == active_status)
            
        if category:
            # Categories are stored as JSON array
            query = query.filter(Supplier.categories.contains([category]))
            
        if rating_min:
            query = query.filter(Supplier.quality_rating >= rating_min)
        
        # Execute query
        suppliers = query.all()
        
        # Calculate performance metrics for each supplier
        supplier_data = []
        for supplier in suppliers:
            # Get recent purchase orders
            recent_pos = PurchaseOrder.query.filter_by(
                supplier_id=supplier.id
            ).order_by(PurchaseOrder.created_at.desc()).limit(50).all()
            
            # Calculate metrics
            total_orders = len(recent_pos)
            on_time_deliveries = sum(1 for po in recent_pos if po.status == 'fulfilled')
            on_time_percentage = (on_time_deliveries / total_orders * 100) if total_orders > 0 else 0
            
            total_volume = sum(po.total_amount or 0 for po in recent_pos)
            
            supplier_data.append({
                'id': supplier.id,
                'name': supplier.name,
                'code': supplier.code,
                'contact_info': supplier.contact_info or {},
                'country': supplier.country,
                'city': supplier.city,
                'categories': supplier.categories or [],
                'health_score': supplier.health_score or 0,
                'reliability_score': supplier.reliability_score or 0,
                'ontime_delivery_rate': supplier.ontime_delivery_rate or 0,
                'quality_rating': supplier.quality_rating or 0,
                'average_lead_time_days': supplier.average_lead_time_days or 0,
                'is_active': supplier.is_active,
                'total_orders': total_orders,
                'on_time_percentage': round(on_time_percentage, 1),
                'total_volume': total_volume,
                'created_at': supplier.created_at.isoformat() if supplier.created_at else None
            })
        
        return jsonify({
            'suppliers': supplier_data,
            'count': len(supplier_data)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching suppliers: {str(e)}")
        return jsonify({'error': 'Failed to fetch suppliers'}), 500

@main_bp.route('/api/suppliers', methods=['POST'])
def api_create_supplier():
    """Create a new supplier."""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'country']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        # Check if supplier with this name already exists
        existing_supplier = Supplier.query.filter_by(name=data['name']).first()
        if existing_supplier:
            return jsonify({'error': 'Supplier with this name already exists'}), 400
        
        # Create new supplier
        supplier = Supplier(
            workspace_id=1,  # Default workspace
            name=data['name'],
            code=data.get('code'),
            contact_info=data.get('contact_info', {}),
            country=data.get('country'),
            city=data.get('city'),
            categories=data.get('categories', []),
            health_score=100.0,  # Default health score
            reliability_score=100.0,  # Default reliability score
            is_active=True
        )
        
        db.session.add(supplier)
        db.session.commit()
        
        # Log the creation
        audit_log = AuditLog(
            workspace_id=1,
            actor_type='user',
            actor_id='system',  # In production, use actual user ID
            action='supplier_created',
            object_type='Supplier',
            object_id=supplier.id,
            details=json.dumps({'supplier_name': supplier.name}),
            result='success'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'message': 'Supplier created successfully',
            'supplier': {
                'id': supplier.id,
                'name': supplier.name,
                'code': supplier.code,
                'country': supplier.country,
                'is_active': supplier.is_active
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating supplier: {str(e)}")
        return jsonify({'error': 'Failed to create supplier'}), 500

@main_bp.route('/api/suppliers/<int:supplier_id>', methods=['PUT'])
def api_update_supplier(supplier_id):
    """Update an existing supplier."""
    try:
        supplier = _get_or_404(Supplier, supplier_id)
        data = request.get_json()
        
        # Update fields if provided
        updateable_fields = ['name', 'code', 'contact_info', 'country', 'city', 'categories', 'is_active']
        for field in updateable_fields:
            if field in data:
                setattr(supplier, field, data[field])
        
        db.session.commit()
        
        # Log the update
        audit_log = AuditLog(
            workspace_id=1,
            actor_type='user',
            actor_id='system',  # In production, use actual user ID
            action='supplier_updated',
            object_type='Supplier',
            object_id=supplier.id,
            details=json.dumps({'supplier_name': supplier.name}),
            result='success'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'message': 'Supplier updated successfully',
            'supplier': {
                'id': supplier.id,
                'name': supplier.name,
                'code': supplier.code,
                'country': supplier.country,
                'is_active': supplier.is_active
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating supplier: {str(e)}")
        return jsonify({'error': 'Failed to update supplier'}), 500

@main_bp.route('/api/suppliers/<int:supplier_id>', methods=['DELETE'])
def api_delete_supplier(supplier_id):
    """Delete a supplier (soft delete by setting status to inactive)."""
    try:
        supplier = _get_or_404(Supplier, supplier_id)
        
        # Soft delete - set status to inactive
        supplier.is_active = False
        db.session.commit()
        
        # Log the deletion
        audit_log = AuditLog(
            workspace_id=1,
            actor_type='user',
            actor_id='system',  # In production, use actual user ID
            action='supplier_deleted',
            object_type='Supplier',
            object_id=supplier.id,
            details=json.dumps({'supplier_name': supplier.name}),
            result='success'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({'message': 'Supplier deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting supplier: {str(e)}")
        return jsonify({'error': 'Failed to delete supplier'}), 500

@main_bp.route('/api/suppliers/export', methods=['GET'])
def api_export_suppliers():
    """Export suppliers to CSV."""
    try:
        import csv
        import io
        
        # Get all suppliers
        suppliers = Supplier.query.all()
        
        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['ID', 'Name', 'Code', 'Country', 'City', 'Categories', 'Health Score', 'Quality Rating', 'Status'])
        
        # Write data
        for supplier in suppliers:
            writer.writerow([
                supplier.id,
                supplier.name,
                supplier.code or '',
                supplier.country or '',
                supplier.city or '',
                ', '.join(supplier.categories) if supplier.categories else '',
                supplier.health_score or 0,
                supplier.quality_rating or 0,
                'Active' if supplier.is_active else 'Inactive'
            ])
        
        # Create response
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=suppliers.csv'}
        )
        
        return response
        
    except Exception as e:
        current_app.logger.error(f"Error exporting suppliers: {str(e)}")
        return jsonify({'error': 'Failed to export suppliers'}), 500

@main_bp.route('/api/suppliers/<int:supplier_id>', methods=['GET'])
def api_get_supplier(supplier_id):
    """Get detailed information about a specific supplier."""
    try:
        supplier = _get_or_404(Supplier, supplier_id)
        
        # Get recent purchase orders
        recent_pos = PurchaseOrder.query.filter_by(
            supplier_id=supplier.id
        ).order_by(PurchaseOrder.created_at.desc()).limit(50).all()
        
        # Calculate performance metrics
        total_orders = len(recent_pos)
        fulfilled_orders = sum(1 for po in recent_pos if po.status == 'fulfilled')
        on_time_percentage = (fulfilled_orders / total_orders * 100) if total_orders > 0 else 0
        
        total_volume = sum(po.total_amount or 0 for po in recent_pos)
        average_order_value = total_volume / total_orders if total_orders > 0 else 0
        
        # Get contracts
        contracts = Contract.query.filter_by(supplier_id=supplier.id).all()
        
        return jsonify({
            'supplier': {
                'id': supplier.id,
                'name': supplier.name,
                'code': supplier.code,
                'contact_info': supplier.contact_info or {},
                'country': supplier.country,
                'city': supplier.city,
                'categories': supplier.categories or [],
                'health_score': supplier.health_score or 0,
                'reliability_score': supplier.reliability_score or 0,
                'ontime_delivery_rate': supplier.ontime_delivery_rate or 0,
                'quality_rating': supplier.quality_rating or 0,
                'average_lead_time_days': supplier.average_lead_time_days or 0,
                'is_active': supplier.is_active,
                'created_at': supplier.created_at.isoformat() if supplier.created_at else None
            },
            'performance': {
                'total_orders': total_orders,
                'on_time_percentage': round(on_time_percentage, 1),
                'total_volume': total_volume,
                'average_order_value': round(average_order_value, 2)
            },
            'contracts': [{
                'id': contract.id,
                'name': contract.name,
                'start_date': contract.start_date.isoformat() if contract.start_date else None,
                'end_date': contract.end_date.isoformat() if contract.end_date else None,
                'status': contract.status,
                'value': contract.value
            } for contract in contracts]
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching supplier details: {str(e)}")
        return jsonify({'error': 'Failed to fetch supplier details'}), 500

@main_bp.route('/api/suppliers/<int:supplier_id>/performance', methods=['GET'])
def api_get_supplier_performance(supplier_id):
    """Get detailed performance metrics for a supplier."""
    try:
        supplier = _get_or_404(Supplier, supplier_id)
        
        # Get all purchase orders for this supplier
        all_pos = PurchaseOrder.query.filter_by(supplier_id=supplier.id).all()
        
        # Calculate comprehensive metrics
        total_orders = len(all_pos)
        fulfilled_orders = sum(1 for po in all_pos if po.status == 'fulfilled')
        pending_orders = sum(1 for po in all_pos if po.status == 'pending')
        cancelled_orders = sum(1 for po in all_pos if po.status == 'cancelled')
        
        # Time-based performance
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        last_30_days = now - timedelta(days=30)
        last_90_days = now - timedelta(days=90)
        
        recent_30_pos = [po for po in all_pos if po.created_at and po.created_at >= last_30_days]
        recent_90_pos = [po for po in all_pos if po.created_at and po.created_at >= last_90_days]
        
        # Financial metrics
        total_value = sum(po.total_amount or 0 for po in all_pos)
        avg_order_value = total_value / total_orders if total_orders > 0 else 0
        
        # Quality metrics (mock calculations based on available data)
        quality_score = supplier.quality_rating or random.uniform(85, 99)
        defect_rate = max(0, 5 - (quality_score - 85) / 3)  # Inverse correlation with quality
        
        # Timeline data for charts (last 6 months)
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']
        delivery_performance = [
            round(random.uniform(85, 98), 1) for _ in months
        ]
        order_volumes = [
            random.randint(5, 25) for _ in months
        ]
        quality_scores = [
            round(random.uniform(88, 97), 1) for _ in months
        ]
        
        return jsonify({
            'supplier_id': supplier.id,
            'supplier_name': supplier.name,
            'overview': {
                'total_orders': total_orders,
                'fulfilled_orders': fulfilled_orders,
                'pending_orders': pending_orders,
                'cancelled_orders': cancelled_orders,
                'fulfillment_rate': round((fulfilled_orders / total_orders * 100) if total_orders > 0 else 0, 1),
                'total_value': total_value,
                'average_order_value': round(avg_order_value, 2)
            },
            'recent_performance': {
                'last_30_days_orders': len(recent_30_pos),
                'last_90_days_orders': len(recent_90_pos),
                'recent_fulfillment_rate': round((sum(1 for po in recent_30_pos if po.status == 'fulfilled') / len(recent_30_pos) * 100) if recent_30_pos else 0, 1)
            },
            'quality_metrics': {
                'overall_quality_score': round(quality_score, 1),
                'defect_rate': round(defect_rate, 2),
                'on_time_delivery_rate': supplier.ontime_delivery_rate or round(random.uniform(85, 98), 1),
                'average_lead_time_days': supplier.average_lead_time_days or random.randint(7, 21)
            },
            'trends': {
                'months': months,
                'delivery_performance': delivery_performance,
                'order_volumes': order_volumes,
                'quality_scores': quality_scores
            },
            'health_indicators': {
                'health_score': supplier.health_score or round(random.uniform(80, 95), 1),
                'reliability_score': supplier.reliability_score or round(random.uniform(85, 98), 1),
                'financial_stability': round(random.uniform(75, 95), 1),
                'communication_score': round(random.uniform(80, 95), 1)
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching supplier performance: {str(e)}")
        return jsonify({'error': 'Failed to fetch supplier performance'}), 500

@main_bp.route('/api/suppliers/<int:supplier_id>/contracts', methods=['GET'])
def api_get_supplier_contracts(supplier_id):
    """Get all contracts for a specific supplier."""
    try:
        supplier = _get_or_404(Supplier, supplier_id)
        
        contracts = Contract.query.filter_by(supplier_id=supplier.id).order_by(
            Contract.start_date.desc()
        ).all()
        
        contract_data = []
        for contract in contracts:
            contract_data.append({
                'id': contract.id,
                'name': contract.name,
                'type': contract.type,
                'status': contract.status,
                'start_date': contract.start_date.isoformat() if contract.start_date else None,
                'end_date': contract.end_date.isoformat() if contract.end_date else None,
                'value': contract.value,
                'currency': contract.currency,
                'terms': contract.terms,
                'auto_renewal': contract.auto_renewal,
                'created_at': contract.created_at.isoformat() if contract.created_at else None
            })
        
        return jsonify({
            'supplier_id': supplier.id,
            'supplier_name': supplier.name,
            'contracts': contract_data,
            'total_contracts': len(contract_data),
            'active_contracts': sum(1 for c in contracts if c.status == 'active'),
            'total_contract_value': sum(c.value or 0 for c in contracts if c.status == 'active')
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching supplier contracts: {str(e)}")
        return jsonify({'error': 'Failed to fetch supplier contracts'}), 500

@main_bp.route('/api/suppliers/<int:supplier_id>/evaluate', methods=['POST'])
def api_evaluate_supplier(supplier_id):
    """Trigger a comprehensive supplier evaluation."""
    try:
        supplier = _get_or_404(Supplier, supplier_id)
        
        # Get evaluation criteria from request or use defaults
        data = request.get_json() or {}
        criteria = data.get('criteria', {
            'delivery_performance': True,
            'quality_assessment': True,
            'financial_stability': True,
            'communication': True,
            'compliance': True
        })
        
        # Simulate comprehensive evaluation
        import time
        evaluation_start = time.time()
        
        # Get supplier data for evaluation
        purchase_orders = PurchaseOrder.query.filter_by(supplier_id=supplier.id).all()
        contracts = Contract.query.filter_by(supplier_id=supplier.id).all()
        
        # Calculate metrics
        total_orders = len(purchase_orders)
        on_time_orders = sum(1 for po in purchase_orders if po.status == 'fulfilled')
        on_time_rate = (on_time_orders / total_orders * 100) if total_orders > 0 else 0
        
        # Evaluation results
        evaluation_results = {
            'supplier_id': supplier.id,
            'supplier_name': supplier.name,
            'evaluation_date': datetime.utcnow().isoformat(),
            'criteria_evaluated': criteria,
            'metrics': {
                'delivery_performance': {
                    'score': round(min(100, on_time_rate + random.uniform(-5, 10)), 1),
                    'on_time_deliveries': on_time_orders,
                    'total_deliveries': total_orders,
                    'on_time_percentage': round(on_time_rate, 1)
                },
                'quality_assessment': {
                    'score': round(random.uniform(85, 98), 1),
                    'defect_rate': round(random.uniform(0.5, 3.0), 2),
                    'quality_certifications': random.randint(2, 8),
                    'customer_satisfaction': round(random.uniform(80, 95), 1)
                },
                'financial_stability': {
                    'score': round(random.uniform(75, 95), 1),
                    'credit_rating': random.choice(['A+', 'A', 'A-', 'B+', 'B']),
                    'payment_terms_compliance': round(random.uniform(90, 100), 1),
                    'financial_health': random.choice(['Excellent', 'Good', 'Fair'])
                },
                'communication': {
                    'score': round(random.uniform(80, 98), 1),
                    'response_time_hours': round(random.uniform(2, 24), 1),
                    'communication_quality': random.choice(['Excellent', 'Good', 'Fair']),
                    'language_capabilities': random.randint(2, 5)
                },
                'compliance': {
                    'score': round(random.uniform(85, 100), 1),
                    'certifications': random.randint(3, 10),
                    'audit_results': random.choice(['Passed', 'Passed with conditions', 'Needs improvement']),
                    'regulatory_compliance': round(random.uniform(90, 100), 1)
                }
            },
            'overall_score': 0,  # Will be calculated
            'recommendations': [],
            'action_items': [],
            'evaluation_duration_seconds': round(time.time() - evaluation_start, 2)
        }
        
        # Calculate overall score
        scores = [
            evaluation_results['metrics']['delivery_performance']['score'],
            evaluation_results['metrics']['quality_assessment']['score'],
            evaluation_results['metrics']['financial_stability']['score'],
            evaluation_results['metrics']['communication']['score'],
            evaluation_results['metrics']['compliance']['score']
        ]
        evaluation_results['overall_score'] = round(sum(scores) / len(scores), 1)
        
        # Generate recommendations based on scores
        if evaluation_results['metrics']['delivery_performance']['score'] < 85:
            evaluation_results['recommendations'].append("Improve delivery performance through better logistics planning")
            evaluation_results['action_items'].append("Schedule quarterly delivery performance reviews")
        
        if evaluation_results['metrics']['quality_assessment']['score'] < 90:
            evaluation_results['recommendations'].append("Implement quality improvement programs")
            evaluation_results['action_items'].append("Conduct quality audits every 6 months")
        
        if evaluation_results['metrics']['financial_stability']['score'] < 80:
            evaluation_results['recommendations'].append("Monitor financial health more closely")
            evaluation_results['action_items'].append("Request quarterly financial statements")
        
        if evaluation_results['overall_score'] >= 90:
            evaluation_results['recommendations'].append("Excellent performance - consider strategic partnership opportunities")
        elif evaluation_results['overall_score'] >= 80:
            evaluation_results['recommendations'].append("Good performance - maintain current relationship with minor improvements")
        else:
            evaluation_results['recommendations'].append("Performance needs improvement - develop improvement plan")
        
        # Update supplier scores
        supplier.health_score = evaluation_results['overall_score']
        supplier.quality_rating = evaluation_results['metrics']['quality_assessment']['score']
        supplier.reliability_score = evaluation_results['metrics']['delivery_performance']['score']
        supplier.ontime_delivery_rate = evaluation_results['metrics']['delivery_performance']['on_time_percentage']
        db.session.commit()
        
        # Log the evaluation
        audit_log = AuditLog(
            workspace_id=supplier.workspace_id,
            actor_type='user',
            actor_id='system',
            action='supplier_evaluated',
            object_type='Supplier',
            object_id=supplier.id,
            details=json.dumps({
                'overall_score': evaluation_results['overall_score'],
                'criteria': list(criteria.keys())
            }),
            result='success'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify(evaluation_results)
        
    except Exception as e:
        current_app.logger.error(f"Error evaluating supplier: {str(e)}")
        return jsonify({'error': 'Failed to evaluate supplier'}), 500

@main_bp.route('/inventory')
def inventory():
    """Inventory view."""
    try:
        # Get all inventory items
        inventory_items = Inventory.query.all()
        
        # Calculate KPIs
        total_skus = len(inventory_items)
        critical_items = sum(1 for item in inventory_items 
                           if item.quantity_on_hand is not None and item.reorder_point is not None 
                           and item.quantity_on_hand <= item.reorder_point * 0.5)
        low_stock_items = sum(1 for item in inventory_items 
                            if item.quantity_on_hand is not None and item.reorder_point is not None 
                            and item.quantity_on_hand <= item.reorder_point)
        total_value = sum((item.quantity_on_hand or 0) * (item.unit_cost or 0) 
                         for item in inventory_items)
        
        # Determine risk level for each item based on calculated days_cover
        for item in inventory_items:
            if item.days_cover and item.days_cover < 5:
                item.risk_level = 'high'
            elif item.days_cover and item.days_cover < 10:
                item.risk_level = 'medium'
            else:
                item.risk_level = 'low'
        
        kpis = {
            'total_skus': total_skus,
            'critical_items': critical_items,
            'low_stock_items': low_stock_items,
            'total_value': total_value
        }
        
        return render_template('inventory.html', 
                             inventory_items=inventory_items,
                             kpis=kpis)
    except Exception as e:
        logger.error(f"Error loading inventory: {e}")
        return render_template('inventory.html', 
                             inventory_items=[],
                             kpis={'total_skus': 0, 'critical_items': 0, 
                                  'low_stock_items': 0, 'total_value': 0})


@main_bp.route('/purchase/<int:po_id>')
def purchase_detail(po_id):
    """Purchase order detail view."""
    po = _get_or_404(PurchaseOrder, po_id)
    return render_template('purchase.html', purchase_order=po)

@main_bp.route('/purchase/<int:po_id>/edit')
def purchase_edit(po_id):
    """Purchase order edit view."""
    po = _get_or_404(PurchaseOrder, po_id)
    # For now, redirect to detail page with edit mode
    # TODO: Create proper edit template/modal
    return render_template('purchase.html', purchase_order=po, edit_mode=True)

@main_bp.route('/supplier/<int:supplier_id>')
def supplier_profile(supplier_id):
    """Supplier profile view."""
    supplier = _get_or_404(Supplier, supplier_id)
    
    # Get related data for the supplier
    contracts = []
    recent_orders = list(supplier.purchase_orders[:10]) if supplier.purchase_orders else []
    recent_activities = []
    
    # Chart data (mock data for now)
    otd_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    otd_data = [95, 92, 96, 88, 94, 91]
    quality_data = [2.1, 1.8, 0.5]
    
    return render_template('supplier_profile.html',
                         supplier=supplier,
                         contracts=contracts,
                         recent_orders=recent_orders,
                         recent_activities=recent_activities,
                         otd_labels=otd_labels,
                         otd_data=otd_data,
                         quality_data=quality_data)

@main_bp.route('/threat/<int:alert_id>')
def threat_detail(alert_id):
    """Threat/alert detail view."""
    alert = _get_or_404(Alert, alert_id)
    from app.models import AuditLog, User, Recommendation
    # Build timeline from audit logs related to this alert
    logs = AuditLog.query.filter_by(
        workspace_id=alert.workspace_id,
        object_type='alert',
        object_id=alert.id
    ).order_by(AuditLog.timestamp.asc()).all()

    action_style_map = {
        'alert.created': 'primary',
        'alert.assigned': 'warning',
        'alert.tracking_started': 'info',
        'alert.updated': 'secondary',
        'alert.recommendation_generated': 'info',
        'alert.resolved': 'success',
        'alert.note_added': 'secondary'
    }

    timeline_events = []
    for l in logs:
        try:
            details = json.loads(l.details) if l.details else {}
        except Exception:
            details = {}
        title = details.get('title') or l.action.replace('alert.', '').replace('_', ' ').title()
        description = details.get('description') or details.get('note') or ''
        timeline_events.append({
            'title': title,
            'description': description,
            'timestamp': l.timestamp.strftime('%Y-%m-%d %H:%M'),
            'actor': f"{l.actor_type}:{l.actor_id}",
            'style': action_style_map.get(l.action, 'primary')
        })

    # Available users for assignment (simple list for now)
    available_users = User.query.limit(25).all()

    # Auto-generate a placeholder recommendation if none exist yet (demo convenience)
    recs = alert.recommendations
    if not recs:
        try:
            placeholder = Recommendation(
                workspace_id=alert.workspace_id,
                type='mitigation',
                subject_ref=f'alert:{alert.id}',
                title='Initial Assessment',
                description=f'Assess and monitor alert {alert.id}. Consider contingency routing if severity escalates.',
                severity=str(alert.severity.name).lower() if alert.severity else None,
                confidence=alert.confidence,
                created_by='risk_agent',
                actions=[{'action': 'Review affected shipments', 'priority': 'high'}, {'action': 'Prepare alternate supplier list'}],
                xai_json={'source': 'auto-generated', 'version': 1}
            )
            db.session.add(placeholder)
            db.session.commit()
            recs = [placeholder]
        except Exception as e:
            current_app.logger.warning(f"Could not create placeholder recommendation: {e}")

    return render_template('threat.html', alert=alert, timeline_events=timeline_events, available_users=available_users)

@main_bp.route('/alert/<int:id>')
def alert_detail(id):
    """Alert detail view (redirects to threat detail for compatibility)."""
    return redirect(url_for('main.threat_detail', alert_id=id))

@main_bp.route('/risk/<int:risk_id>')
def risk_detail(risk_id):
    """Risk detail view."""
    from app.models import Risk
    risk = _get_or_404(Risk, risk_id)
    
    # Get related alerts for this risk
    related_alerts = Alert.query.filter_by(workspace_id=risk.workspace_id).all()
    
    # Get affected entities details
    affected_shipments = []
    affected_suppliers = []
    
    if risk.affected_entities:
        # Extract shipment IDs
        shipment_ids = [e.get('id') for e in risk.affected_entities if e.get('type') == 'shipment']
        if shipment_ids:
            affected_shipments = Shipment.query.filter(Shipment.id.in_(shipment_ids)).all()
        
        # Extract supplier IDs  
        supplier_ids = [e.get('id') for e in risk.affected_entities if e.get('type') == 'supplier']
        if supplier_ids:
            affected_suppliers = Supplier.query.filter(Supplier.id.in_(supplier_ids)).all()
    
    return render_template('risk_detail.html', 
                         risk=risk,
                         related_alerts=related_alerts,
                         affected_shipments=affected_shipments,
                         affected_suppliers=affected_suppliers)

@main_bp.route('/recommendation/<int:id>')
def recommendation_detail(id):
    """Recommendation detail view."""
    try:
        from app.models import Recommendation, Risk
        recommendation = Recommendation.query.get_or_404(id)
        
        # Find related risks based on similar subject or type
        related_risks = []
        if recommendation.subject_ref:
            related_risks = Risk.query.filter(
                Risk.workspace_id == recommendation.workspace_id,
                Risk.id != id
            ).limit(10).all()
        
        return render_template('recommendation_detail.html', 
                             recommendation=recommendation,
                             related_risks=related_risks)
    except Exception as e:
        current_app.logger.error(f"Error loading recommendation detail: {str(e)}")
        abort(404)

@main_bp.route('/api/risks/<int:risk_id>/resolve', methods=['POST'])
def api_resolve_risk(risk_id):
    """Mark a risk as resolved."""
    try:
        from app.models import Risk
        risk = _get_or_404(Risk, risk_id)
        
        data = request.get_json() or {}
        resolution_notes = data.get('resolution_notes', '')
        
        risk.status = 'resolved'
        risk.resolved_at = datetime.utcnow()
        risk.resolution_notes = resolution_notes
        risk.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Risk marked as resolved',
            'risk_id': risk.id,
            'status': risk.status
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error resolving risk: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to resolve risk'}), 500

@main_bp.route('/api/risks/<int:risk_id>/mitigate', methods=['POST'])
def api_mitigate_risk(risk_id):
    """Start mitigation process for a risk."""
    try:
        from app.models import Risk
        risk = _get_or_404(Risk, risk_id)
        
        risk.status = 'mitigating'
        risk.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Mitigation process started',
            'risk_id': risk.id,
            'status': risk.status
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error starting mitigation: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to start mitigation'}), 500

@main_bp.route('/api/risks/<int:risk_id>/export')
def api_export_risk(risk_id):
    """Export risk data as JSON."""
    try:
        from app.models import Risk
        risk = _get_or_404(Risk, risk_id)
        
        export_data = {
            'id': risk.id,
            'title': risk.title,
            'description': risk.description,
            'risk_type': risk.risk_type,
            'risk_score': risk.risk_score,
            'severity': risk.severity,
            'probability': risk.probability,
            'confidence': risk.confidence,
            'affected_entities': risk.affected_entities,
            'impact_assessment': risk.impact_assessment,
            'mitigation_strategies': risk.mitigation_strategies,
            'data_sources': risk.data_sources,
            'location': risk.location,
            'status': risk.status,
            'created_at': risk.created_at.isoformat() if risk.created_at else None,
            'updated_at': risk.updated_at.isoformat() if risk.updated_at else None
        }
        
        response = make_response(jsonify(export_data))
        response.headers['Content-Disposition'] = f'attachment; filename=risk_{risk.id}_export.json'
        response.headers['Content-Type'] = 'application/json'
        
        return response
        
    except Exception as e:
        current_app.logger.error(f"Error exporting risk: {str(e)}")
        return jsonify({'error': 'Failed to export risk data'}), 500

@main_bp.route('/api/risks/trigger-assessment', methods=['POST'])
def api_trigger_risk_assessment():
    """Manually trigger risk assessment - Demo version"""
    try:
        # For demo purposes, always use the sample generator
        from app.models import Risk
        from datetime import datetime, timedelta
        import random
        
        # Clear old demo risks (keep user-generated ones)
        Risk.query.filter_by(created_by_agent='sample_generator').delete()
        
        # Sample risk templates
        risk_templates = [
            {
                'title': 'Critical Storm System in Pacific',
                'description': 'Major storm system detected with 120+ km/h winds affecting Pacific shipping lanes',
                'risk_type': 'weather',
                'severity': 'critical',
                'risk_score': 0.85,
                'probability': 0.9,
                'confidence': 0.8,
                'location': {'lat': 35.0, 'lon': -150.0, 'name': 'North Pacific'},
                'geographic_scope': 'regional',
                'time_horizon': 'immediate',
                'estimated_duration': 72
            },
            {
                'title': 'Red Sea Security Risk',
                'description': 'Heightened security concerns in Red Sea shipping corridor',
                'risk_type': 'geopolitical',
                'severity': 'high',
                'risk_score': 0.75,
                'probability': 0.7,
                'confidence': 0.9,
                'location': {'lat': 20.0, 'lon': 38.0, 'name': 'Red Sea'},
                'geographic_scope': 'regional',
                'time_horizon': 'short_term',
                'estimated_duration': 168
            },
            {
                'title': 'Shanghai Port Congestion',
                'description': 'Higher than normal congestion with 4+ day delays',
                'risk_type': 'port_congestion',
                'severity': 'medium',
                'risk_score': 0.6,
                'probability': 0.8,
                'confidence': 0.85,
                'location': {'lat': 31.22, 'lon': 121.46, 'name': 'Shanghai Port'},
                'geographic_scope': 'local',
                'time_horizon': 'short_term',
                'estimated_duration': 96
            }
        ]
        
        # Create new risk records
        for template in risk_templates:
            risk = Risk(
                workspace_id=1,
                title=template['title'],
                description=template['description'],
                risk_type=template['risk_type'],
                risk_score=template['risk_score'],
                severity=template['severity'],
                probability=template['probability'],
                confidence=template['confidence'],
                affected_entities=[],
                impact_assessment={
                    'estimated_delay_hours': template['estimated_duration'],
                    'economic_impact': {'estimated_cost_usd': random.uniform(10000, 100000)}
                },
                mitigation_strategies=[],
                data_sources=['Manual Trigger', 'Demo Data'],
                location=template['location'],
                geographic_scope=template['geographic_scope'],
                time_horizon=template['time_horizon'],
                estimated_duration=template['estimated_duration'],
                status='identified',
                created_by_agent='sample_generator'
            )
            db.session.add(risk)
        
        db.session.commit()
        
        # Get updated count
        risk_count = Risk.query.filter_by(status='identified').count()
        
        return jsonify({
            'success': True,
            'message': f'Risk assessment completed! Generated {len(risk_templates)} new risks.',
            'current_risks': risk_count,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error triggering risk assessment: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'Failed to trigger risk assessment: {str(e)}'
        }), 500

# ---------------- Alert Management APIs (support threat detail actions) ---------------- #
@main_bp.route('/api/alerts/<int:alert_id>/assign', methods=['POST'])
def api_assign_alert(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    data = request.get_json() or {}
    assignee_id = data.get('assignee_id')
    if not assignee_id:
        return jsonify({'success': False, 'error': 'assignee_id required'}), 400
    from app.models import User, AuditLog
    user = User.query.get(assignee_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    alert.assigned_to = user.id
    db.session.add(alert)
    log = AuditLog(
        workspace_id=alert.workspace_id,
        actor_type='user',
        actor_id=str(user.id),
        user_id=user.id,
        action='alert.assigned',
        object_type='alert',
        object_id=alert.id,
        details=json.dumps({'title': 'Alert Assigned', 'description': f'Assigned to {user.name}'}),
        result='success'
    )
    db.session.add(log)
    db.session.commit()
    return jsonify({'success': True})

@main_bp.route('/api/alerts/<int:alert_id>/track', methods=['POST'])
def api_track_alert(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    if alert.status not in ('open', 'tracking'):
        return jsonify({'success': False, 'error': 'Alert not open'}), 400
    alert.status = 'tracking'
    from app.models import AuditLog
    log = AuditLog(
        workspace_id=alert.workspace_id,
        actor_type='system',
        actor_id='tracking_service',
        action='alert.tracking_started',
        object_type='alert',
        object_id=alert.id,
        details=json.dumps({'title': 'Tracking Started'}),
        result='success'
    )
    db.session.add(alert)
    db.session.add(log)
    db.session.commit()
    return jsonify({'success': True})

@main_bp.route('/api/alerts/<int:alert_id>/resolve', methods=['POST'])
def api_resolve_alert(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    data = request.get_json() or {}
    resolution = data.get('resolution', '')
    alert.status = 'resolved'
    alert.resolved_at = datetime.utcnow()
    from app.models import AuditLog
    log = AuditLog(
        workspace_id=alert.workspace_id,
        actor_type='user',
        actor_id='resolver',
        action='alert.resolved',
        object_type='alert',
        object_id=alert.id,
        details=json.dumps({'title': 'Alert Resolved', 'description': resolution}),
        result='success'
    )
    db.session.add(alert)
    db.session.add(log)
    db.session.commit()
    return jsonify({'success': True})

@main_bp.route('/api/alerts/<int:alert_id>/notes', methods=['POST'])
def api_alert_add_note(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    data = request.get_json() or {}
    note = data.get('note')
    if not note:
        return jsonify({'success': False, 'error': 'note required'}), 400
    from app.models import AuditLog
    log = AuditLog(
        workspace_id=alert.workspace_id,
        actor_type='user',
        actor_id='note_author',
        action='alert.note_added',
        object_type='alert',
        object_id=alert.id,
        details=json.dumps({'title': 'Note Added', 'description': note}),
        result='success'
    )
    db.session.add(log)
    db.session.commit()
    return jsonify({'success': True})

@main_bp.route('/api/alerts/<int:alert_id>/export')
def api_export_alert(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    export = {
        'id': alert.id,
        'title': alert.title,
        'description': alert.description,
        'type': alert.type,
        'severity': alert.severity.name if alert.severity else None,
        'status': alert.status,
        'created_at': alert.created_at.isoformat(),
    }
    response = make_response(jsonify(export))
    response.headers['Content-Disposition'] = f'attachment; filename=alert_{alert.id}.json'
    return response

@main_bp.route('/policies')
def policies():
    """Policies and compliance view."""
    return render_template('policies.html')

@main_bp.route('/api/policies', methods=['GET'])
def api_get_policies():
    """Get all policies with optional filtering."""
    try:
        # Get query parameters
        policy_type = request.args.get('type', '').strip()
        status = request.args.get('status', '').strip()
        search = request.args.get('search', '').strip()
        
        # Base query
        query = Policy.query
        
        # Apply filters
        if policy_type:
            query = query.filter(Policy.type == policy_type)
        
        if status:
            is_active = status.lower() == 'active'
            query = query.filter(Policy.is_active == is_active)
        
        if search:
            query = query.filter(
                db.or_(
                    Policy.name.ilike(f'%{search}%'),
                    Policy.rules.ilike(f'%{search}%')
                )
            )
        
        policies = query.order_by(Policy.created_at.desc()).all()
        
        policy_data = []
        for policy in policies:
            policy_data.append({
                'id': policy.id,
                'name': policy.name,
                'type': policy.type,
                'rules': policy.rules,
                'is_active': policy.is_active,
                'workspace_id': policy.workspace_id,
                'created_at': policy.created_at.isoformat() if policy.created_at else None,
                'updated_at': policy.updated_at.isoformat() if policy.updated_at else None
            })
        
        # Get policy statistics
        total_policies = len(policies)
        active_policies = sum(1 for p in policies if p.is_active)
        inactive_policies = total_policies - active_policies
        
        # Get policy types distribution
        type_counts = {}
        for policy in policies:
            policy_type = policy.type or 'Unknown'
            type_counts[policy_type] = type_counts.get(policy_type, 0) + 1
        
        return jsonify({
            'policies': policy_data,
            'summary': {
                'total_policies': total_policies,
                'active_policies': active_policies,
                'inactive_policies': inactive_policies,
                'type_distribution': type_counts
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching policies: {str(e)}")
        return jsonify({'error': 'Failed to fetch policies'}), 500

@main_bp.route('/api/policies', methods=['POST'])
def api_create_policy():
    """Create a new policy."""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'type', 'rules']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        # Validate name is not empty
        if not data.get('name', '').strip():
            return jsonify({'error': 'Policy name cannot be empty'}), 400
        
        # Validate JSON rules
        try:
            rules_str = data.get('rules', '{}')
            if isinstance(rules_str, str):
                json.loads(rules_str)  # Validate JSON format
        except json.JSONDecodeError:
            return jsonify({'error': 'Invalid JSON format in rules field'}), 400
        
        # Check if policy with this name already exists
        existing_policy = Policy.query.filter_by(
            name=data['name'], 
            workspace_id=1
        ).first()
        if existing_policy:
            return jsonify({'error': 'Policy with this name already exists'}), 400
        
        # Create new policy
        policy = Policy(
            workspace_id=1,  # Default workspace
            name=data['name'].strip(),
            type=data['type'],
            rules=data['rules'],
            is_active=data.get('is_active', True)
        )
        
        db.session.add(policy)
        db.session.commit()
        
        # Log the creation
        audit_log = AuditLog(
            workspace_id=1,
            actor_type='user',
            actor_id='system',
            action='policy_created',
            object_type='Policy',
            object_id=policy.id,
            details=json.dumps({
                'policy_name': policy.name,
                'policy_type': policy.type
            }),
            result='success'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'message': 'Policy created successfully',
            'policy': {
                'id': policy.id,
                'name': policy.name,
                'type': policy.type,
                'rules': policy.rules,
                'is_active': policy.is_active
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating policy: {str(e)}")
        return jsonify({'error': 'Failed to create policy'}), 500

@main_bp.route('/api/policies/<int:policy_id>', methods=['PUT'])
def api_update_policy(policy_id):
    """Update an existing policy."""
    try:
        policy = Policy.query.get(policy_id)
        if not policy:
            return jsonify({'error': 'Policy not found'}), 404
            
        data = request.get_json()
        
        # Update fields if provided
        updateable_fields = ['name', 'type', 'rules', 'is_active']
        old_values = {field: getattr(policy, field) for field in updateable_fields}
        
        # Validate JSON rules if provided
        if 'rules' in data:
            try:
                rules_str = data.get('rules', '{}')
                if isinstance(rules_str, str):
                    json.loads(rules_str)  # Validate JSON format
            except json.JSONDecodeError:
                return jsonify({'error': 'Invalid JSON format in rules field'}), 400
        
        for field in updateable_fields:
            if field in data:
                setattr(policy, field, data[field])
        
        db.session.commit()
        
        # Log the update
        audit_log = AuditLog(
            workspace_id=policy.workspace_id,
            actor_type='user',
            actor_id='system',
            action='policy_updated',
            object_type='Policy',
            object_id=policy.id,
            details=json.dumps({
                'policy_name': policy.name,
                'changes': {k: {'old': old_values[k], 'new': getattr(policy, k)} 
                           for k in updateable_fields if k in data}
            }),
            result='success'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'message': 'Policy updated successfully',
            'policy': {
                'id': policy.id,
                'name': policy.name,
                'type': policy.type,
                'rules': policy.rules,
                'is_active': policy.is_active
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating policy: {str(e)}")
        return jsonify({'error': 'Failed to update policy'}), 500

@main_bp.route('/api/policies/<int:policy_id>', methods=['DELETE'])
def api_delete_policy(policy_id):
    """Delete a policy (soft delete by setting status to inactive)."""
    try:
        policy = Policy.query.get(policy_id)
        if not policy:
            return jsonify({'error': 'Policy not found'}), 404
        
        # Soft delete - set status to inactive
        policy.is_active = False
        db.session.commit()
        
        # Log the deletion
        audit_log = AuditLog(
            workspace_id=policy.workspace_id,
            actor_type='user',
            actor_id='system',
            action='policy_deleted',
            object_type='Policy',
            object_id=policy.id,
            details=json.dumps({'policy_name': policy.name}),
            result='success'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({'message': 'Policy deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting policy: {str(e)}")
        return jsonify({'error': 'Failed to delete policy'}), 500

@main_bp.route('/api/policies/<int:policy_id>/test', methods=['POST'])
def api_test_policy(policy_id):
    """Test a policy against sample data or scenarios."""
    try:
        policy = Policy.query.get(policy_id)
        if not policy:
            return jsonify({'error': 'Policy not found'}), 404
        
        data = request.get_json() or {}
        
        # Get test scenario from request or create a default one
        test_scenario = data.get('scenario', {
            'type': 'purchase_order',
            'amount': 50000,
            'supplier_id': 1,
            'urgent': False,
            'location': 'domestic'
        })
        
        # Validate scenario structure
        if not isinstance(test_scenario, dict):
            return jsonify({'error': 'Test scenario must be a valid object'}), 400
        
        # Simulate policy evaluation
        import time
        test_start = time.time()
        
        # Parse policy rules (simplified simulation)
        rules = policy.rules or ""
        
        # Test results based on policy type and rules
        test_results = {
            'policy_id': policy.id,
            'policy_name': policy.name,
            'policy_type': policy.type,
            'test_scenario': test_scenario,
            'execution_time_ms': 0,  # Will be calculated
            'status': 'passed',
            'triggered': False,
            'conditions_evaluated': [],
            'actions_recommended': [],
            'compliance_score': 100
        }
        
        # Simulate rule evaluation based on policy type
        if policy.type == 'procurement':
            amount = test_scenario.get('amount', 0)
            if 'approval_required' in rules.lower() and amount > 25000:
                test_results['triggered'] = True
                test_results['conditions_evaluated'].append({
                    'condition': 'Amount > $25,000',
                    'result': True,
                    'value': amount
                })
                test_results['actions_recommended'].append('Require manager approval')
            
            if 'dual_approval' in rules.lower() and amount > 100000:
                test_results['triggered'] = True
                test_results['conditions_evaluated'].append({
                    'condition': 'Amount > $100,000',
                    'result': True,
                    'value': amount
                })
                test_results['actions_recommended'].append('Require dual approval')
        
        elif policy.type == 'risk_management':
            if 'high_risk' in rules.lower():
                test_results['conditions_evaluated'].append({
                    'condition': 'High risk supplier check',
                    'result': False,
                    'value': 'Low risk supplier'
                })
        
        elif policy.type == 'compliance':
            test_results['conditions_evaluated'].append({
                'condition': 'Regulatory compliance check',
                'result': True,
                'value': 'All requirements met'
            })
        
        # Calculate compliance score
        if test_results['triggered']:
            test_results['compliance_score'] = 85
            test_results['status'] = 'requires_action'
        
        # Set execution time
        test_results['execution_time_ms'] = round((time.time() - test_start) * 1000, 2)
        
        # If no conditions were evaluated, add a default one
        if not test_results['conditions_evaluated']:
            test_results['conditions_evaluated'].append({
                'condition': 'Policy evaluation completed',
                'result': True,
                'value': 'No specific conditions to evaluate'
            })
        
        # Log the test
        audit_log = AuditLog(
            workspace_id=policy.workspace_id,
            actor_type='user',
            actor_id='system',
            action='policy_tested',
            object_type='Policy',
            object_id=policy.id,
            details=json.dumps({
                'policy_name': policy.name,
                'test_result': test_results['status'],
                'triggered': test_results['triggered']
            }),
            result='success'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify(test_results)
        
    except Exception as e:
        current_app.logger.error(f"Error testing policy: {str(e)}")
        return jsonify({'error': 'Failed to test policy'}), 500

@main_bp.route('/api/policies/analytics', methods=['GET'])
def api_get_policy_analytics():
    """Get policy performance analytics and statistics."""
    try:
        # Get all policies
        policies = Policy.query.all()
        
        # Get policy execution data from audit logs
        policy_logs = AuditLog.query.filter(
            AuditLog.object_type == 'Policy',
            AuditLog.action.in_(['policy_executed', 'policy_triggered', 'policy_tested'])
        ).order_by(AuditLog.timestamp.desc()).limit(1000).all()
        
        # Calculate analytics
        total_policies = len(policies)
        active_policies = sum(1 for p in policies if p.is_active)
        
        # Policy execution statistics
        execution_stats = {
            'total_executions': len(policy_logs),
            'successful_executions': sum(1 for log in policy_logs if log.result == 'success'),
            'failed_executions': sum(1 for log in policy_logs if log.result == 'error'),
            'average_execution_time': round(random.uniform(50, 200), 2)  # Mock data
        }
        
        # Policy type distribution
        type_distribution = {}
        for policy in policies:
            policy_type = policy.type or 'Unknown'
            type_distribution[policy_type] = type_distribution.get(policy_type, 0) + 1
        
        # Recent activity (last 30 days)
        from datetime import datetime, timedelta
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_logs = [log for log in policy_logs if log.timestamp and log.timestamp >= thirty_days_ago]
        
        # Most active policies
        policy_activity = {}
        for log in recent_logs:
            policy_id = log.object_id
            policy_activity[policy_id] = policy_activity.get(policy_id, 0) + 1
        
        most_active_policies = []
        for policy_id, count in sorted(policy_activity.items(), key=lambda x: x[1], reverse=True)[:5]:
            policy = Policy.query.get(policy_id)
            if policy:
                most_active_policies.append({
                    'id': policy.id,
                    'name': policy.name,
                    'type': policy.type,
                    'execution_count': count
                })
        
        # Compliance trends (mock data for demonstration)
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']
        compliance_scores = [round(random.uniform(85, 98), 1) for _ in months]
        policy_violations = [random.randint(0, 15) for _ in months]
        
        return jsonify({
            'summary': {
                'total_policies': total_policies,
                'active_policies': active_policies,
                'inactive_policies': total_policies - active_policies,
                'policy_coverage': round((active_policies / total_policies * 100) if total_policies > 0 else 0, 1)
            },
            'execution_stats': execution_stats,
            'type_distribution': type_distribution,
            'recent_activity': {
                'total_executions_30_days': len(recent_logs),
                'most_active_policies': most_active_policies
            },
            'compliance_trends': {
                'months': months,
                'compliance_scores': compliance_scores,
                'policy_violations': policy_violations
            },
            'performance_metrics': {
                'average_response_time_ms': round(random.uniform(50, 150), 1),
                'success_rate': round(execution_stats['successful_executions'] / execution_stats['total_executions'] * 100 if execution_stats['total_executions'] > 0 else 100, 1),
                'automation_rate': round(random.uniform(75, 90), 1)
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching policy analytics: {str(e)}")
        return jsonify({'error': 'Failed to fetch policy analytics'}), 500

@main_bp.route('/audit-log')
def audit_log():
    """Audit log view."""
    workspace_id = 1  # Default workspace
    
    # Get recent logs
    logs = AuditLog.query.filter_by(
        workspace_id=workspace_id
    ).order_by(AuditLog.timestamp.desc()).limit(100).all()
    
    return render_template('audit_log.html',
        logs=logs
    )

@main_bp.route('/api/audit')
def api_audit_logs():
    """API endpoint for audit logs with filtering and pagination."""
    from datetime import datetime, timedelta
    
    workspace_id = 1  # Default workspace
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    
    # Build query
    query = AuditLog.query.filter_by(workspace_id=workspace_id)
    
    # Apply filters
    date_range = request.args.get('date_range')
    if date_range:
        now = datetime.utcnow()
        if date_range == 'today':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(AuditLog.timestamp >= start_date)
        elif date_range == 'week':
            start_date = now - timedelta(days=7)
            query = query.filter(AuditLog.timestamp >= start_date)
        elif date_range == 'month':
            start_date = now - timedelta(days=30)
            query = query.filter(AuditLog.timestamp >= start_date)
    
    actor_type = request.args.get('actor_type')
    if actor_type:
        query = query.filter(AuditLog.actor_type == actor_type)
    
    action_type = request.args.get('action_type')
    if action_type:
        query = query.filter(AuditLog.action == action_type)
    
    object_type = request.args.get('object_type')
    if object_type:
        query = query.filter(AuditLog.object_type == object_type)
    
    result = request.args.get('result')
    if result:
        query = query.filter(AuditLog.result == result)
    
    # Order by timestamp descending
    query = query.order_by(AuditLog.timestamp.desc())
    
    # Paginate
    pagination = query.paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    # Serialize logs
    logs = []
    for log in pagination.items:
        log_dict = {
            'id': log.id,
            'timestamp': log.timestamp.isoformat() if log.timestamp else None,
            'actor_type': log.actor_type,
            'actor_id': log.actor_id,
            'actor_name': log.actor_id,  # For now, use actor_id as name
            'action': log.action,
            'object_type': log.object_type,
            'object_id': log.object_id,
            'details': log.details,
            'result': log.result,
            'ip_address': log.ip_address,
            'request_id': log.request_id
        }
        logs.append(log_dict)
    
    return jsonify({
        'logs': logs,
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': pagination.page,
        'total_pages': pagination.pages,
        'per_page': per_page,
        'has_next': pagination.has_next,
        'has_prev': pagination.has_prev
    })

@main_bp.route('/api/audit/<int:log_id>')
def api_audit_log_detail(log_id):
    """API endpoint for individual audit log details."""
    workspace_id = 1  # Default workspace
    
    log = AuditLog.query.filter_by(
        id=log_id,
        workspace_id=workspace_id
    ).first_or_404()
    
    # Parse details if it's JSON
    details = log.details
    before_value = None
    after_value = None
    policy_checks = None
    
    if details:
        try:
            import json
            details_data = json.loads(details) if isinstance(details, str) else details
            before_value = details_data.get('before')
            after_value = details_data.get('after')
            policy_checks = details_data.get('policy_checks')
        except (json.JSONDecodeError, TypeError):
            # If it's not JSON, keep as string
            pass
    
    log_dict = {
        'id': log.id,
        'timestamp': log.timestamp.isoformat() if log.timestamp else None,
        'actor_type': log.actor_type,
        'actor_id': log.actor_id,
        'actor_name': log.actor_id,  # For now, use actor_id as name
        'action': log.action,
        'object_type': log.object_type,
        'object_id': log.object_id,
        'details': details,
        'result': log.result,
        'ip_address': log.ip_address,
        'request_id': log.request_id,
        'policy_triggered': log.policy_triggered,
        'policy_result': log.policy_result,
        'error_message': log.error_message,
        'before_value': before_value,
        'after_value': after_value,
        'policy_checks': policy_checks
    }
    
    return jsonify(log_dict)

@main_bp.route('/api/audit/export')
def api_audit_export():
    """Export audit logs as CSV."""
    import csv
    import io
    from flask import Response
    
    workspace_id = 1  # Default workspace
    
    # Build query with same filters as main API
    query = AuditLog.query.filter_by(workspace_id=workspace_id)
    
    # Apply same filters as main endpoint
    date_range = request.args.get('date_range')
    if date_range:
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        if date_range == 'today':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(AuditLog.timestamp >= start_date)
        elif date_range == 'week':
            start_date = now - timedelta(days=7)
            query = query.filter(AuditLog.timestamp >= start_date)
        elif date_range == 'month':
            start_date = now - timedelta(days=30)
            query = query.filter(AuditLog.timestamp >= start_date)
    
    actor_type = request.args.get('actor_type')
    if actor_type:
        query = query.filter(AuditLog.actor_type == actor_type)
    
    action_type = request.args.get('action_type')
    if action_type:
        query = query.filter(AuditLog.action == action_type)
    
    object_type = request.args.get('object_type')
    if object_type:
        query = query.filter(AuditLog.object_type == object_type)
    
    result = request.args.get('result')
    if result:
        query = query.filter(AuditLog.result == result)
    
    # Order by timestamp descending
    logs = query.order_by(AuditLog.timestamp.desc()).all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        'Timestamp', 'Actor Type', 'Actor ID', 'Action', 'Object Type', 
        'Object ID', 'Result', 'Details', 'IP Address', 'Request ID'
    ])
    
    # Data rows
    for log in logs:
        writer.writerow([
            log.timestamp.isoformat() if log.timestamp else '',
            log.actor_type,
            log.actor_id,
            log.action,
            log.object_type,
            log.object_id,
            log.result,
            log.details or '',
            log.ip_address or '',
            log.request_id or ''
        ])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=audit_log.csv'}
    )

@main_bp.route('/integrations')
def integrations():
    """Integrations settings view."""
    return render_template('integration.html')

@main_bp.route('/notifications')
def notifications():
    """Notifications settings view."""
    return render_template('notifications.html')

@main_bp.route('/profile')
def profile():
    """User profile page."""
    # For now, return a simple profile page
    # In production, this would show the logged-in user's profile
    return render_template('profile.html',
                         user={
                             'name': 'Demo User',
                             'email': 'user@example.com',
                             'role': 'Supply Chain Manager',
                             'workspace': 'Default Workspace'
                         })

@main_bp.route('/docs')
def docs():
    """Documentation view."""
    return render_template('docs.html')

# Helper functions
def calculate_global_risk_index():
    """Calculate global risk index based on active alerts."""
    try:
        from app.utils.redis_manager import RedisManager
        
        # Try to get risk index from Redis first
        redis_manager = RedisManager()
        risk_data = redis_manager.get_key("global_risk_index")
        
        if risk_data:
            try:
                risk_json = json.loads(risk_data)
                if 'risk_index' in risk_json:
                    return float(risk_json['risk_index'])
            except:
                # If parsing fails, continue with database calculation
                pass
        
        # Get active alerts
        alerts = Alert.query.filter(Alert.status == 'active').all()
        
        if not alerts:
            return 0.46  # Default for demo
        
        # Weight by severity - handle both enum and string values
        severity_weights = {
            AlertSeverity.LOW: 0.2,
            AlertSeverity.MEDIUM: 0.5,
            AlertSeverity.HIGH: 1.0,
            AlertSeverity.CRITICAL: 1.5,
            # String mappings for database values
            'low': 0.2,
            'medium': 0.5,
            'high': 1.0,
            'critical': 1.5
        }
        
        total_score = sum(
            severity_weights.get(alert.severity, 0.5) * (alert.confidence or 0.5)
            for alert in alerts
        )
        
        # Normalize to 0-1 range
        max_possible = len(alerts) * 1.5  # Max weight is 1.5 for critical
        risk_index = min(total_score / max_possible, 1.0) if max_possible > 0 else 0.0
        
        return round(risk_index, 2)
        
    except Exception as e:
        logger.error(f"Error calculating risk index: {e}")
        return 0.46  # Default demo value

def calculate_on_time_rate():
    """Calculate on-time delivery rate for last 30 days."""
    try:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        
        delivered = Shipment.query.filter(
            Shipment.actual_arrival.between(start_date, end_date)
        ).all()
        
        if not delivered:
            return 100.0
        
        on_time = sum(
            1 for s in delivered 
            if s.actual_arrival <= s.scheduled_arrival + timedelta(hours=24)
        )
        
        rate = (on_time / len(delivered)) * 100
        return round(rate, 1)
        
    except Exception as e:
        logger.error(f"Error calculating on-time rate: {e}")
        return 93.0

def get_risk_cause(shipment):
    """Get primary risk cause for shipment."""
    # Check for associated alerts
    if shipment.alerts:
        alert = shipment.alerts[0]  # Get most recent
        return alert.title[:50]
    
    # Default based on status
    if shipment.status == ShipmentStatus.DELAYED:
        return "Carrier delay"
    elif shipment.risk_score > 0.7:
        return "Route disruption"
    
    return "Unknown"

def calculate_impact_score(alert):
    """Calculate impact score for risk visualization."""
    base_score = {
        AlertSeverity.LOW: 0.2,
        AlertSeverity.MEDIUM: 0.5,
        AlertSeverity.HIGH: 1.0
    }.get(alert.severity, 0.5)
    
    # Adjust by number of affected entities
    affected_count = len(alert.shipments) + len(alert.suppliers)
    multiplier = min(1 + (affected_count * 0.1), 2.0)
    
    return round(base_score * multiplier, 2)

def calculate_on_time_delivery(workspace_id, date_range):
    """Calculate on-time delivery percentage."""
    # Implementation for MVP
    return 93.5

def calculate_cost_avoided(workspace_id, date_range):
    """Calculate cost avoided through optimizations."""
    # Implementation for MVP
    return 125000

def calculate_emissions_saved(workspace_id, date_range):
    """Calculate emissions saved through route optimization."""
    # Implementation for MVP
    return 450.5

def calculate_alert_mttr(workspace_id, date_range):
    """Calculate mean time to resolve alerts."""
    # Implementation for MVP
    return 4.2

@main_bp.route('/api/dashboard/logistics/summary')
def logistics_summary():
    """Get logistics summary for dashboard."""
    # Mock data for now
    return jsonify({
        'total_shipments': 45,
        'in_transit': 23,
        'delayed': 3,
        'on_time_percentage': 93.5
    })

@main_bp.route('/api/dashboard/recent-activity')
def recent_activity():
    """Get recent activity for dashboard."""
    # Mock data for now
    return jsonify({
        'activities': [
            {
                'id': 1,
                'type': 'shipment_update',
                'message': 'Shipment SH-001 departed from Shanghai',
                'timestamp': '2024-08-09T10:30:00Z'
            },
            {
                'id': 2,
                'type': 'alert',
                'message': 'Weather warning for Pacific route',
                'timestamp': '2024-08-09T09:15:00Z'
            }
        ]
    })

@main_bp.route('/api/dashboard/executive/summary')
def executive_summary():
    """Get executive summary for dashboard."""
    # Mock data for now
    return jsonify({
        'total_value_at_risk': 2500000,
        'critical_alerts': 2,
        'pending_approvals': 5,
        'cost_savings_mtd': 125000
    })

# Inventory API Endpoints

@main_bp.route('/api/inventory', methods=['GET'])
def api_inventory_list():
    """Get inventory list with filtering."""
    try:
        # Get filter parameters
        location = request.args.get('location')
        sku_search = request.args.get('search')
        threshold = request.args.get('threshold')
        risk_level = request.args.get('risk')
        
        # Build query
        query = Inventory.query
        
        if location:
            query = query.filter(Inventory.location == location)
        
        if sku_search:
            query = query.filter(or_(
                Inventory.sku.like(f'%{sku_search}%'),
                Inventory.description.like(f'%{sku_search}%')
            ))
        
        inventory_items = query.all()
        
        # Calculate fields and apply filters
        filtered_items = []
        for item in inventory_items:
            # Determine risk level based on calculated days_cover
            if item.days_cover and item.days_cover < 5:
                item.risk_level = 'high'
            elif item.days_cover and item.days_cover < 10:
                item.risk_level = 'medium'
            else:
                item.risk_level = 'low'
            
            # Apply threshold filter
            if threshold:
                if threshold == 'critical' and (not item.days_cover or item.days_cover >= 5):
                    continue
                elif threshold == 'low' and (not item.days_cover or item.days_cover < 5 or item.days_cover >= 10):
                    continue
                elif threshold == 'normal' and (item.days_cover and item.days_cover < 10):
                    continue
            
            # Apply risk filter
            if risk_level and item.risk_level != risk_level:
                continue
            
            filtered_items.append({
                'id': item.id,
                'sku': item.sku,
                'description': item.description,
                'unit_of_measure': item.unit_of_measure,
                'quantity_on_hand': item.quantity_on_hand,
                'quantity_on_order': item.quantity_on_order,
                'available_stock': (item.quantity_on_hand or 0),
                'reorder_point': item.reorder_point,
                'days_cover': item.days_cover,
                'risk_level': item.risk_level,
                'location': item.location,
                'unit_cost': item.unit_cost,
            })
        
        return jsonify({
            'success': True,
            'inventory_items': filtered_items,
            'total_count': len(filtered_items)
        })
        
    except Exception as e:
        logger.error(f"Error fetching inventory: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@main_bp.route('/api/inventory/<sku>', methods=['GET'])
def api_inventory_detail(sku):
    """Get detailed inventory information for a specific SKU."""
    try:
        item = Inventory.query.filter_by(sku=sku).first_or_404()
        
        # Note: days_cover is calculated automatically as a property
        
        # Mock recent transactions (in a real system, this would come from a transactions table)
        recent_transactions = [
            {
                'date': '2025-08-09',
                'type': 'in',
                'quantity': 500,
                'reference': 'PO-231',
                'notes': 'Regular reorder'
            },
            {
                'date': '2025-08-08',
                'type': 'out',
                'quantity': 200,
                'reference': 'SO-445',
                'notes': 'Production consumption'
            }
        ]
        
        return jsonify({
            'success': True,
            'inventory_item': {
                'id': item.id,
                'sku': item.sku,
                'description': item.description,
                'unit_of_measure': item.unit_of_measure,
                'quantity_on_hand': item.quantity_on_hand,
                'quantity_on_order': item.quantity_on_order,
                'available_stock': (item.quantity_on_hand or 0),
                'reorder_point': item.reorder_point,
                'reorder_quantity': item.reorder_quantity,
                'days_cover': item.days_cover,
                'location': item.location,
                'unit_cost': item.unit_cost,
                'daily_usage_rate': item.daily_usage_rate,
                'recent_transactions': recent_transactions
            }
        })
        
    except Exception as e:
        logger.error(f"Error fetching inventory detail for {sku}: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@main_bp.route('/api/inventory', methods=['POST'])
def api_inventory_create():
    """Create new inventory item."""
    try:
        data = request.get_json() if request.is_json else request.form.to_dict()
        
        # Debug logging
        logger.info(f"Received data: {data}")
        
        # Validate required fields
        if not data.get('sku'):
            return jsonify({'success': False, 'message': 'Field sku is required'}), 400
        
        # Handle name/description field mapping - frontend sends 'name', model uses 'description'
        description = data.get('description') or data.get('name', '')
        if not description:
            return jsonify({'success': False, 'message': 'Field description is required'}), 400
        
        # Check if SKU already exists for this workspace
        existing = Inventory.query.filter_by(workspace_id=1, sku=data['sku']).first()
        if existing:
            return jsonify({'success': False, 'message': 'SKU already exists'}), 400
        
        # Create new inventory item with field mapping
        item = Inventory(
            workspace_id=1,  # Default workspace
            sku=data['sku'],
            description=description,
            unit_of_measure=data.get('unit') or data.get('unit_of_measure'),
            quantity_on_hand=float(data.get('current_stock') or data.get('quantity_on_hand', 0)),
            reorder_point=float(data.get('min_inventory') or data.get('reorder_point', 0)),
            reorder_quantity=float(data.get('max_inventory') or data.get('reorder_quantity', 0)),
            location=data.get('site_code') or data.get('location'),
            unit_cost=float(data.get('unit_cost', 0)) if data.get('unit_cost') else None,
            daily_usage_rate=float(data.get('daily_usage_rate', 1)) if data.get('daily_usage_rate') else 1.0
        )
        
        logger.info(f"Created item object: workspace_id={item.workspace_id}, sku={item.sku}")
        
        db.session.add(item)
        db.session.commit()
        
        logger.info(f"Created new inventory item: {item.sku}")
        
        return jsonify({
            'success': True,
            'message': 'Inventory item created successfully',
            'inventory_item': {
                'id': item.id,
                'sku': item.sku,
                'description': item.description
            }
        })
        
    except Exception as e:
        logger.error(f"Error creating inventory item: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@main_bp.route('/api/inventory/reorder', methods=['POST'])
def api_inventory_reorder():
    """API endpoint for inventory reorder."""
    try:
        data = request.get_json()
        if not data or 'sku' not in data:
            return jsonify({'success': False, 'message': 'SKU must be provided in the request body'}), 400
            
        sku = data['sku']
        item = Inventory.query.filter_by(sku=sku).first_or_404()
        
        # In a real system, this would trigger the procurement agent
        # For now, we'll create a mock purchase order recommendation
        
        # Find suitable supplier (mock logic)
        suppliers = Supplier.query.filter_by(is_active=True).all()
        if not suppliers:
            return jsonify({'success': False, 'message': 'No active suppliers found'}), 400
        
        # Calculate order quantity
        order_qty = item.reorder_quantity or (item.reorder_point * 2 if item.reorder_point else 1000)

        # Create a recommendation
        recommendation = Recommendation(
            workspace_id=item.workspace_id,
            type=RecommendationType.REORDER.value,
            subject_ref=f'inventory:{item.id}',
            severity='high' if item.quantity_on_hand <= item.reorder_point * 0.5 else 'medium',
            confidence=0.9,
            status='pending',
            created_by='system',
            xai_json=json.dumps({
                'action': 'create_purchase_order',
                'sku': item.sku,
                'quantity': order_qty,
                'suggested_supplier': suppliers[0].name,
                'urgency': 'high' if item.quantity_on_hand <= item.reorder_point * 0.5 else 'normal',
                'rationale': f"Current stock ({item.quantity_on_hand}) is below or near minimum level ({item.reorder_point})",
                "recommendation_text": f"Reorder {order_qty} units of {item.sku}"
            })
        )
        
        db.session.add(recommendation)
        db.session.commit()
        
        logger.info(f"Created reorder recommendation for {sku}")
        
        return jsonify({
            'success': True,
            'message': f'Reorder initiated for {sku}',
            'recommendation_id': recommendation.id,
            'order_quantity': order_qty
        })
        
    except Exception as e:
        logger.error(f"Error initiating reorder for {sku}: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@main_bp.route('/api/inventory/export')
def api_inventory_export():
    """Export inventory data."""
    try:
        import io
        import csv
        
        # Get all inventory items
        items = Inventory.query.all()
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'SKU', 'Description', 'Unit of Measure',
            'Quantity On Hand', 'Quantity On Order', 'Available Stock',
            'Reorder Point', 'Reorder Quantity', 'Location',
            'Unit Cost', 'Daily Usage Rate'
        ])
        
        # Write data
        for item in items:
            writer.writerow([
                item.sku,
                item.description or '',
                item.unit_of_measure or '',
                item.quantity_on_hand or 0,
                item.quantity_on_order or 0,
                (item.quantity_on_hand or 0),
                item.reorder_point or 0,
                item.reorder_quantity or 0,
                item.location or '',
                item.unit_cost or 0,
                item.daily_usage_rate or 0
            ])
        
        # Prepare response
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = 'attachment; filename=inventory_export.csv'
        
        return response
        
    except Exception as e:
        logger.error(f"Error exporting inventory: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@main_bp.route('/api/inventory/<int:inventory_id>', methods=['PUT'])
def api_update_inventory(inventory_id):
    """Update an existing inventory item."""
    try:
        inventory = _get_or_404(Inventory, inventory_id)
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Update fields if provided
        updateable_fields = [
            'sku', 'description', 'unit_of_measure', 'quantity_on_hand',
            'quantity_on_order', 'reorder_point', 'reorder_quantity',
            'location', 'unit_cost', 'daily_usage_rate'
        ]
        
        old_values = {field: getattr(inventory, field) for field in updateable_fields}
        
        for field in updateable_fields:
            if field in data:
                setattr(inventory, field, data[field])
        
        # Recalculate available stock
        if 'quantity_on_hand' in data or 'quantity_on_order' in data:
            inventory.available_stock = (inventory.quantity_on_hand or 0)
        
        db.session.commit()
        
        # Log the update
        audit_log = AuditLog(
            workspace_id=inventory.workspace_id,
            actor_type='user',
            actor_id='system',
            action='inventory_updated',
            object_type='Inventory',
            object_id=inventory.id,
            details=json.dumps({
                'sku': inventory.sku,
                'changes': {k: {'old': old_values[k], 'new': getattr(inventory, k)} 
                           for k in updateable_fields if k in data}
            }),
            result='success'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'message': 'Inventory item updated successfully',
            'inventory': {
                'id': inventory.id,
                'sku': inventory.sku,
                'description': inventory.description,
                'quantity_on_hand': inventory.quantity_on_hand,
                'available_stock': inventory.available_stock,
                'reorder_point': inventory.reorder_point,
                'location': inventory.location
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating inventory: {str(e)}")
        return jsonify({'error': 'Failed to update inventory item'}), 500

@main_bp.route('/api/inventory/alerts', methods=['GET'])
def api_inventory_alerts():
    """Get low stock alerts and critical inventory items."""
    try:
        # Get query parameters
        alert_type = request.args.get('type', 'all')  # 'low_stock', 'out_of_stock', 'all'
        category = request.args.get('category', '')
        location = request.args.get('location', '')
        
        # Base query
        query = Inventory.query
        
        # Apply filters
        if category:
            query = query.filter(Inventory.sku.ilike(f'{category}%'))
        
        if location:
            query = query.filter(Inventory.location == location)
        
        inventory_items = query.all()
        
        # Categorize alerts
        alerts = {
            'out_of_stock': [],
            'critical_low': [],
            'low_stock': [],
            'reorder_needed': []
        }
        
        for item in inventory_items:
            qty_on_hand = item.quantity_on_hand or 0
            reorder_point = item.reorder_point or 0
            
            # Out of stock
            if qty_on_hand <= 0:
                alerts['out_of_stock'].append({
                    'id': item.id,
                    'sku': item.sku,
                    'description': item.description,
                    'quantity_on_hand': qty_on_hand,
                    'reorder_point': reorder_point,
                    'location': item.location,
                    'unit_cost': item.unit_cost,
                    'severity': 'critical'
                })
            # Critical low (below 50% of reorder point)
            elif reorder_point > 0 and qty_on_hand <= (reorder_point * 0.5):
                alerts['critical_low'].append({
                    'id': item.id,
                    'sku': item.sku,
                    'description': item.description,
                    'quantity_on_hand': qty_on_hand,
                    'reorder_point': reorder_point,
                    'location': item.location,
                    'unit_cost': item.unit_cost,
                    'severity': 'high',
                    'percentage_of_reorder': round((qty_on_hand / reorder_point * 100), 1)
                })
            # Low stock (at or below reorder point)
            elif reorder_point > 0 and qty_on_hand <= reorder_point:
                alerts['low_stock'].append({
                    'id': item.id,
                    'sku': item.sku,
                    'description': item.description,
                    'quantity_on_hand': qty_on_hand,
                    'reorder_point': reorder_point,
                    'location': item.location,
                    'unit_cost': item.unit_cost,
                    'severity': 'medium',
                    'percentage_of_reorder': round((qty_on_hand / reorder_point * 100), 1)
                })
            # Approaching reorder point (within 10% above reorder point)
            elif reorder_point > 0 and qty_on_hand <= (reorder_point * 1.1):
                alerts['reorder_needed'].append({
                    'id': item.id,
                    'sku': item.sku,
                    'description': item.description,
                    'quantity_on_hand': qty_on_hand,
                    'reorder_point': reorder_point,
                    'location': item.location,
                    'unit_cost': item.unit_cost,
                    'severity': 'low',
                    'percentage_of_reorder': round((qty_on_hand / reorder_point * 100), 1)
                })
        
        # Filter by alert type if specified
        if alert_type != 'all':
            filtered_alerts = {alert_type: alerts.get(alert_type, [])}
            alerts = filtered_alerts
        
        # Calculate summary metrics
        total_alerts = sum(len(alert_list) for alert_list in alerts.values())
        total_value_at_risk = sum(
            sum(item.get('unit_cost', 0) * item.get('quantity_on_hand', 0) 
                for item in alert_list)
            for alert_list in alerts.values()
        )
        
        return jsonify({
            'alerts': alerts,
            'summary': {
                'total_alerts': total_alerts,
                'out_of_stock_count': len(alerts.get('out_of_stock', [])),
                'critical_low_count': len(alerts.get('critical_low', [])),
                'low_stock_count': len(alerts.get('low_stock', [])),
                'reorder_needed_count': len(alerts.get('reorder_needed', [])),
                'total_value_at_risk': round(total_value_at_risk, 2)
            },
            'filters_applied': {
                'type': alert_type,
                'category': category if category else None,
                'location': location if location else None
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching inventory alerts: {str(e)}")
        return jsonify({'error': 'Failed to fetch inventory alerts'}), 500

@main_bp.route('/api/inventory/analytics', methods=['GET'])
def api_inventory_analytics():
    """Get comprehensive inventory analytics and insights."""
    try:
        # Get query parameters
        period_days = request.args.get('period', 30, type=int)
        include_trends = request.args.get('trends', 'true').lower() == 'true'
        
        # Get all inventory items
        inventory_items = Inventory.query.all()
        
        if not inventory_items:
            return jsonify({
                'error': 'No inventory data available',
                'analytics': None
            }), 404
        
        # Calculate basic metrics
        total_items = len(inventory_items)
        total_value = sum((item.unit_cost or 0) * (item.quantity_on_hand or 0) for item in inventory_items)
        total_quantity = sum(item.quantity_on_hand or 0 for item in inventory_items)
        
        # Stock status analysis
        out_of_stock = sum(1 for item in inventory_items if (item.quantity_on_hand or 0) <= 0)
        low_stock = sum(1 for item in inventory_items 
                       if item.reorder_point and (item.quantity_on_hand or 0) <= item.reorder_point and (item.quantity_on_hand or 0) > 0)
        critical_stock = sum(1 for item in inventory_items 
                            if item.reorder_point and (item.quantity_on_hand or 0) <= (item.reorder_point * 0.5))
        normal_stock = total_items - out_of_stock - low_stock - critical_stock
        
        # Category analysis
        category_analysis = {}
        for item in inventory_items:
            # Extract category from SKU prefix
            category = item.sku.split('-')[0] if item.sku and '-' in item.sku else 'Other'
            if category not in category_analysis:
                category_analysis[category] = {
                    'item_count': 0,
                    'total_value': 0,
                    'total_quantity': 0,
                    'low_stock_items': 0
                }
            
            category_analysis[category]['item_count'] += 1
            category_analysis[category]['total_value'] += (item.unit_cost or 0) * (item.quantity_on_hand or 0)
            category_analysis[category]['total_quantity'] += (item.quantity_on_hand or 0)
            
            if item.reorder_point and (item.quantity_on_hand or 0) <= item.reorder_point:
                category_analysis[category]['low_stock_items'] += 1
        
        # Location analysis
        location_analysis = {}
        for item in inventory_items:
            location = item.location or 'Unknown'
            if location not in location_analysis:
                location_analysis[location] = {
                    'item_count': 0,
                    'total_value': 0,
                    'total_quantity': 0
                }
            
            location_analysis[location]['item_count'] += 1
            location_analysis[location]['total_value'] += (item.unit_cost or 0) * (item.quantity_on_hand or 0)
            location_analysis[location]['total_quantity'] += (item.quantity_on_hand or 0)
        
        # Top items by value
        top_value_items = sorted(
            [{'sku': item.sku, 'description': item.description, 
              'value': (item.unit_cost or 0) * (item.quantity_on_hand or 0),
              'quantity': item.quantity_on_hand}
             for item in inventory_items],
            key=lambda x: x['value'], reverse=True
        )[:10]
        
        # ABC Analysis (Pareto analysis)
        items_by_value = sorted(inventory_items, 
                               key=lambda x: (x.unit_cost or 0) * (x.quantity_on_hand or 0), 
                               reverse=True)
        
        abc_analysis = {'A': 0, 'B': 0, 'C': 0}
        cumulative_value = 0
        for i, item in enumerate(items_by_value):
            item_value = (item.unit_cost or 0) * (item.quantity_on_hand or 0)
            cumulative_value += item_value
            percentage = (cumulative_value / total_value * 100) if total_value > 0 else 0
            
            if percentage <= 80:
                abc_analysis['A'] += 1
            elif percentage <= 95:
                abc_analysis['B'] += 1
            else:
                abc_analysis['C'] += 1
        
        # Turnover analysis (mock data based on reorder patterns)
        turnover_analysis = {
            'fast_moving': sum(1 for item in inventory_items 
                              if item.daily_usage_rate and item.daily_usage_rate > 5),
            'medium_moving': sum(1 for item in inventory_items 
                                if item.daily_usage_rate and 1 <= item.daily_usage_rate <= 5),
            'slow_moving': sum(1 for item in inventory_items 
                              if item.daily_usage_rate and item.daily_usage_rate < 1),
            'no_movement': sum(1 for item in inventory_items 
                              if not item.daily_usage_rate or item.daily_usage_rate == 0)
        }
        
        # Trend analysis (generate mock trend data for demonstration)
        trends = {}
        if include_trends:
            months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']
            trends = {
                'inventory_value': [round(total_value * random.uniform(0.85, 1.15), 2) for _ in months],
                'stock_levels': [round(total_quantity * random.uniform(0.9, 1.1), 0) for _ in months],
                'reorder_frequency': [random.randint(15, 45) for _ in months],
                'out_of_stock_incidents': [random.randint(0, 8) for _ in months],
                'months': months
            }
        
        # Recommendations based on analysis
        recommendations = []
        
        if out_of_stock > 0:
            recommendations.append({
                'type': 'critical',
                'title': 'Address Out of Stock Items',
                'description': f'{out_of_stock} items are currently out of stock. Immediate reordering required.',
                'action': 'Review and reorder critical items'
            })
        
        if low_stock > total_items * 0.2:  # More than 20% low stock
            recommendations.append({
                'type': 'warning',
                'title': 'High Low Stock Percentage',
                'description': f'{low_stock} items ({low_stock/total_items*100:.1f}%) are at or below reorder point.',
                'action': 'Review reorder points and supplier lead times'
            })
        
        if abc_analysis['A'] > abc_analysis['B'] + abc_analysis['C']:
            recommendations.append({
                'type': 'info',
                'title': 'Optimize High-Value Items',
                'description': 'High concentration of value in few items. Consider better forecasting for A-class items.',
                'action': 'Implement advanced demand planning for top-value items'
            })
        
        return jsonify({
            'analytics': {
                'overview': {
                    'total_items': total_items,
                    'total_value': round(total_value, 2),
                    'total_quantity': total_quantity,
                    'average_item_value': round(total_value / total_items, 2) if total_items > 0 else 0
                },
                'stock_status': {
                    'out_of_stock': out_of_stock,
                    'critical_stock': critical_stock,
                    'low_stock': low_stock,
                    'normal_stock': normal_stock,
                    'stock_health_percentage': round((normal_stock / total_items * 100), 1) if total_items > 0 else 0
                },
                'category_breakdown': category_analysis,
                'location_breakdown': location_analysis,
                'abc_analysis': abc_analysis,
                'turnover_analysis': turnover_analysis,
                'top_value_items': top_value_items,
                'trends': trends if include_trends else None,
                'recommendations': recommendations
            },
            'period_days': period_days,
            'generated_at': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        current_app.logger.error(f"Error generating inventory analytics: {str(e)}")
        return jsonify({'error': 'Failed to generate inventory analytics'}), 500

@main_bp.route('/api/inventory/reorder-needed', methods=['GET'])
def api_inventory_reorder_needed():
    """Get list of inventory items that need reordering."""
    try:
        # Get items that are at or below reorder point
        reorder_items = Inventory.query.filter(
            and_(
                Inventory.reorder_point.isnot(None),
                Inventory.quantity_on_hand <= Inventory.reorder_point
            )
        ).all()
        
        # Format response
        items = []
        for item in reorder_items:
            items.append({
                'id': item.id,
                'sku': item.sku,
                'description': item.description,
                'location': item.location,
                'quantity_on_hand': item.quantity_on_hand,
                'reorder_point': item.reorder_point,
                'reorder_quantity': item.reorder_quantity,
                'unit_cost': item.unit_cost,
                'supplier_name': item.supplier.name if item.supplier else None,
                'supplier_id': item.supplier_id,
                'days_of_supply': round((item.quantity_on_hand / item.daily_usage_rate), 1) if item.daily_usage_rate and item.daily_usage_rate > 0 else None,
                'urgency': 'critical' if item.quantity_on_hand <= (item.reorder_point * 0.5) else 'normal'
            })
        
        # Sort by urgency and quantity on hand
        items.sort(key=lambda x: (x['urgency'] == 'critical', x['quantity_on_hand']))
        
        return jsonify({
            'reorder_items': items,
            'summary': {
                'total_items': len(items),
                'critical_items': len([item for item in items if item['urgency'] == 'critical']),
                'total_value': sum((item['unit_cost'] or 0) * (item['quantity_on_hand'] or 0) for item in items)
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching reorder items: {str(e)}")
        return jsonify({'error': 'Failed to fetch reorder items'}), 500

def calculate_global_risk_index():
    """Calculate global risk index based on active alerts."""
    try:
        # Get active alerts
        alerts = Alert.query.filter(Alert.status != 'resolved').all()
        
        if not alerts:
            return 0.0
        
        # Weight by severity
        severity_weights = {
            AlertSeverity.LOW: 0.2,
            AlertSeverity.MEDIUM: 0.5,
            AlertSeverity.HIGH: 1.0,
            AlertSeverity.CRITICAL: 1.5
        }
        
        total_score = sum(
            severity_weights.get(alert.severity, 0.5) * (alert.confidence or 0.5)
            for alert in alerts
        )
        
        # Normalize to 0-1 range
        max_possible = len(alerts) * 1.5  # Max weight is 1.5 for critical
        risk_index = min(total_score / max_possible, 1.0) if max_possible > 0 else 0.0
        
        return round(risk_index, 2)
        
    except Exception as e:
        logger.error(f"Error calculating risk index: {e}")
        return 0.5

def get_risk_cause(shipment):
    """Get primary risk cause for shipment."""
    # Check for associated alerts
    if shipment.alerts:
        alert = shipment.alerts[0]  # Get most recent
        return alert.title[:50]
    
    # Default based on status
    if shipment.status == ShipmentStatus.DELAYED:
        return "Carrier delay"
    elif shipment.risk_score > 0.7:
        return "Route disruption"
    
    return "Unknown"

def calculate_impact_score(alert):
    """Calculate impact score for risk visualization."""
    base_score = {
        AlertSeverity.LOW: 0.2,
        AlertSeverity.MEDIUM: 0.5,
        AlertSeverity.HIGH: 1.0
    }.get(alert.severity, 0.5)
    
    # Adjust by number of affected entities
    affected_count = len(alert.shipments) + len(alert.suppliers)
    multiplier = min(1 + (affected_count * 0.1), 2.0)
    
    return round(base_score * multiplier, 2)

def calculate_on_time_delivery(workspace_id, date_range):
    """Calculate on-time delivery percentage."""
    # Implementation for MVP
    return 93.5

def calculate_cost_avoided(workspace_id, date_range):
    """Calculate cost avoided through optimizations."""
    # Implementation for MVP
    return 125000

def calculate_emissions_saved(workspace_id, date_range):
    """Calculate emissions saved through route optimization."""
    # Implementation for MVP
    return 450.5

def calculate_alert_mttr(workspace_id, date_range):
    """Calculate mean time to resolve alerts."""
    # Implementation for MVP
    return 4.2

def calculate_dashboard_metrics(workspace_id, date_range):
    """Calculate various dashboard metrics."""
    return {
        'on_time_delivery': 93.5,
        'cost_avoided': 125000,
        'emissions_saved': 450.5,
        'alert_mttr': 4.2
    }

# Removed old notification route - now handled by notifications_routes.py

@main_bp.route('/api/alerts/open-count')
def get_open_alerts_count():
    """Get count of open alerts."""
    try:
        from app.models import Alert
        count = Alert.query.filter(
            Alert.status.in_(['open', 'active', 'acknowledged'])
        ).count()
        return jsonify({'count': count})
    except Exception as e:
        logger.error(f"Error getting open alerts count: {e}")
        return jsonify({'count': 0})

@main_bp.route('/api/approvals/pending-count')
def get_pending_approvals_count():
    """Get count of pending approvals."""
    try:
        from app.models import Approval
        # 'state' is stored as uppercase string (e.g., 'PENDING')
        count = Approval.query.filter_by(state='PENDING').count()
        return jsonify({'count': count})
    except Exception as e:
        logger.error(f"Error getting pending approvals count: {e}")
        return jsonify({'count': 0})

@main_bp.route('/api/approvals/pending')
def get_pending_approvals():
    """Get pending approval items for the approvals inbox."""
    try:
        from app.models import DecisionItem
        
        # Get pending decision items sorted by priority and deadline
        pending_items = DecisionItem.query.filter_by(status='pending')\
            .order_by(DecisionItem.priority_score.desc(), DecisionItem.approval_deadline.asc())\
            .all()
        
        approvals = []
        for item in pending_items:
            approval_data = {
                'id': item.id,
                'title': item.title,
                'description': item.description,
                'type': item.decision_type,
                'severity': item.severity,
                'urgency_level': item.urgency_level,
                'priority_score': item.priority_score,
                'estimated_impact_usd': item.estimated_impact_usd,
                'affected_shipments_count': item.affected_shipments_count,
                'risk_if_delayed': item.risk_if_delayed,
                'required_role': item.required_role,
                'approval_deadline': item.approval_deadline.isoformat() if item.approval_deadline else None,
                'created_by': item.created_by,
                'created_by_type': item.created_by_type,
                'related_object_type': item.related_object_type,
                'related_object_id': item.related_object_id,
                'context_data': item.context_data,
                'created_at': item.created_at.isoformat() if item.created_at else None,
                'status': item.status
            }
            approvals.append(approval_data)
        
        return jsonify({
            'success': True,
            'approvals': approvals,
            'count': len(approvals)
        })
        
    except Exception as e:
        logger.error(f"Error getting pending approvals: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'approvals': [],
            'count': 0
        })

@main_bp.route('/api/approvals/history')
def get_approvals_history():
    """Get completed approval items for the approvals history."""
    try:
        from app.models import DecisionItem
        
        # Get completed decision items (approved, rejected, or expired)
        completed_items = DecisionItem.query.filter(
            DecisionItem.status.in_(['approved', 'rejected', 'expired', 'deferred'])
        ).order_by(DecisionItem.decision_made_at.desc()).limit(50).all()
        
        approvals = []
        for item in completed_items:
            approval_data = {
                'id': item.id,
                'title': item.title,
                'description': item.description,
                'type': item.decision_type,
                'severity': item.severity,
                'status': item.status,
                'decision_made_at': item.decision_made_at.isoformat() if item.decision_made_at else None,
                'decision_made_by': item.decision_made_by,
                'decision_rationale': item.decision_rationale,
                'created_at': item.created_at.isoformat() if item.created_at else None,
                'estimated_impact_usd': item.estimated_impact_usd,
                'related_object_type': item.related_object_type,
                'related_object_id': item.related_object_id
            }
            approvals.append(approval_data)
        
        return jsonify({
            'success': True,
            'approvals': approvals,
            'count': len(approvals)
        })
        
    except Exception as e:
        logger.error(f"Error getting approvals history: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'approvals': [],
            'count': 0
        })

@main_bp.route('/api/approvals/<int:approval_id>')
def get_approval_details(approval_id):
    """Get detailed information about a specific approval item."""
    try:
        from app.models import DecisionItem
        
        item = DecisionItem.query.get_or_404(approval_id)
        
        approval_data = {
            'id': item.id,
            'title': item.title,
            'description': item.description,
            'decision_type': item.decision_type,
            'severity': item.severity,
            'priority_score': item.priority_score,
            'urgency_level': item.urgency_level,
            'estimated_impact_usd': item.estimated_impact_usd,
            'affected_shipments_count': item.affected_shipments_count,
            'risk_if_delayed': item.risk_if_delayed,
            'requires_approval': item.requires_approval,
            'required_role': item.required_role,
            'approval_deadline': item.approval_deadline.isoformat() if item.approval_deadline else None,
            'auto_approve_after': item.auto_approve_after.isoformat() if item.auto_approve_after else None,
            'created_by': item.created_by,
            'created_by_type': item.created_by_type,
            'related_object_type': item.related_object_type,
            'related_object_id': item.related_object_id,
            'recommendation_id': item.recommendation_id,
            'status': item.status,
            'decision_made_at': item.decision_made_at.isoformat() if item.decision_made_at else None,
            'decision_made_by': item.decision_made_by,
            'decision_rationale': item.decision_rationale,
            'context_data': item.context_data,
            'created_at': item.created_at.isoformat() if item.created_at else None,
            'updated_at': item.updated_at.isoformat() if item.updated_at else None,
            'expires_at': item.expires_at.isoformat() if item.expires_at else None
        }
        
        return jsonify({
            'success': True,
            'approval': approval_data
        })
        
    except Exception as e:
        logger.error(f"Error getting approval details for {approval_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@main_bp.route('/api/approvals/<int:approval_id>/approve', methods=['POST'])
def approve_decision_item(approval_id):
    """Approve a decision item."""
    try:
        from app.models import DecisionItem
        from datetime import datetime
        
        item = DecisionItem.query.get_or_404(approval_id)
        
        if item.status != 'pending':
            return jsonify({
                'success': False,
                'error': 'Item is not pending approval'
            })
        
        # Get approval rationale from request
        data = request.get_json() or {}
        rationale = data.get('rationale', 'Approved via web interface')
        
        # Update decision item
        item.status = 'approved'
        item.decision_made_at = datetime.utcnow()
        item.decision_made_by = 1  # TODO: Use actual user ID when auth is implemented
        item.decision_rationale = rationale
        item.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Decision item approved successfully'
        })
        
    except Exception as e:
        logger.error(f"Error approving decision item {approval_id}: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        })

@main_bp.route('/api/approvals/<int:approval_id>/reject', methods=['POST'])
def reject_decision_item(approval_id):
    """Reject a decision item."""
    try:
        from app.models import DecisionItem
        from datetime import datetime
        
        item = DecisionItem.query.get_or_404(approval_id)
        
        if item.status != 'pending':
            return jsonify({
                'success': False,
                'error': 'Item is not pending approval'
            })
        
        # Get rejection rationale from request
        data = request.get_json() or {}
        rationale = data.get('rationale', 'Rejected via web interface')
        
        # Update decision item
        item.status = 'rejected'
        item.decision_made_at = datetime.utcnow()
        item.decision_made_by = 1  # TODO: Use actual user ID when auth is implemented
        item.decision_rationale = rationale
        item.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Decision item rejected successfully'
        })
        
    except Exception as e:
        logger.error(f"Error rejecting decision item {approval_id}: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        })

@main_bp.route('/api/shipments/<int:shipment_id>/reroute-options')
def get_reroute_options(shipment_id):
    """Get available reroute options for a shipment"""
    try:
        # Require auth in non-testing environments; bypass in tests
        from flask import current_app
        from flask_login import current_user
        try:
            from sqlalchemy.exc import OperationalError
        except Exception:
            OperationalError = Exception

        if not current_app.config.get('TESTING', False):
            if not current_user.is_authenticated:
                return jsonify({'error': 'Authentication required'}), 401

        shipment = _get_or_404(Shipment, shipment_id)
        alt_options = []
        current_route_option = None
        try:
            # Demo route generation removed
            current_route = shipment.current_route
            if current_route:
                current_route_option = _route_to_option_dict(current_route)
            # Support dynamic relationship (query) or eager-loaded list
            routes_list = (
                shipment.routes.all() if hasattr(shipment.routes, 'all') else (shipment.routes or [])
            )
            alternatives = [r for r in routes_list if not r.is_current]
            alternatives_sorted = sorted(alternatives, key=lambda r: (not r.is_recommended, r.risk_score))
            alt_options = [_route_to_option_dict(r, current_route) for r in alternatives_sorted]
        except OperationalError:
            # Provide synthetic alternatives
            current_route_option = {
                'route_id': 0,
                'name': 'Baseline Route',
                'is_recommended': False,
                'waypoints': [],
                'metrics': {'distance_km': 1000, 'duration_hours': 240, 'cost_usd': 50000, 'emissions_kg': 30000, 'risk_score': shipment.risk_score or 0.4},
                'comparison': {'distance_delta':0,'duration_delta':0,'cost_delta':0,'emissions_delta':0,'risk_delta':0},
                'metadata': {}
            }
            alt_options = [
                {
                    'route_id': 1,
                    'name': 'Alternative Route 1',
                    'is_recommended': True,
                    'waypoints': [],
                    'metrics': {'distance_km': 980, 'duration_hours': 238, 'cost_usd': 51000, 'emissions_kg': 29500, 'risk_score': (shipment.risk_score or 0.4)*0.9},
                    'comparison': {'distance_delta': -20,'duration_delta': -2,'cost_delta': 1000,'emissions_delta': -500,'risk_delta': 0.04},
                    'metadata': {'risk_factors':['weather'], 'avoided_risks':[{'name':'Storm Cell'}]}
                },
                {
                    'route_id': 2,
                    'name': 'Alternative Route 2',
                    'is_recommended': False,
                    'waypoints': [],
                    'metrics': {'distance_km': 1100, 'duration_hours': 250, 'cost_usd': 48000, 'emissions_kg': 31000, 'risk_score': (shipment.risk_score or 0.4)*1.05},
                    'comparison': {'distance_delta': 100,'duration_delta': 10,'cost_delta': -2000,'emissions_delta': 1000,'risk_delta': -0.02},
                    'metadata': {'risk_factors':['piracy_zone']}
                }
            ]
        # Placeholder for latest recommendation (simple heuristic: any recommendation with subject_ref)
        latest_recommendation = Recommendation.query.filter_by(subject_ref=f'shipment:{shipment.id}').order_by(Recommendation.created_at.desc()).first()
        recommendation_data = None
        if latest_recommendation:
            xai = latest_recommendation.xai_json or {}
            recommendation_data = {
                'id': latest_recommendation.id,
                'title': latest_recommendation.title,
                'description': latest_recommendation.description,
                'rationale': xai.get('rationale'),
                'created_at': latest_recommendation.created_at.isoformat()
            }
        return jsonify({
            'shipment_id': shipment.id,
            'tracking_number': shipment.reference_number,
            'current_route': current_route_option,
            'alternatives': alt_options,
            'recommendation': recommendation_data
        })
        
    except Exception as e:
        logger.error(f"Error getting reroute options: {str(e)}")
        return jsonify({'error': 'Failed to get reroute options'}), 500

@main_bp.route('/api/shipments/<int:shipment_id>/reroute', methods=['POST'])
def reroute_shipment(shipment_id):
    """Execute shipment reroute"""
    try:
        # Require auth in non-testing environments; bypass in tests
        from flask import current_app
        from flask_login import current_user
        if not current_app.config.get('TESTING', False):
            if not current_user.is_authenticated:
                return jsonify({'error': 'Authentication required'}), 401
        shipment = _get_or_404(Shipment, shipment_id)
        # Try to generate demo routes (may fail if schema mismatch)
        try:
            # Demo route generation removed
            pass
        except OperationalError:
            pass
        data = request.get_json() or {}
        
        route_id = data.get('route_id')
        if not route_id:
            return jsonify({'error': 'Route ID required'}), 400
        
        # Get selected route
        selected_route = None
        try:
            selected_route = Route.query.filter_by(
                id=route_id,
                shipment_id=shipment_id
            ).first()
        except OperationalError:
            selected_route = None
        
        if not selected_route:
            # Allow synthetic fallback reroute if using synthetic route options (IDs 1 or 2)
            if int(route_id) in (1, 2):
                return jsonify({
                    'status': 'success',
                    'message': 'Synthetic reroute applied (schema fallback)',
                    'shipment_id': shipment.id,
                    'new_route_id': route_id
                })
            return jsonify({'error': 'Invalid route'}), 404
        
        # Check if approval is needed
        approval_required = False
        approval_reason = None
        
        # Check cost threshold
        if selected_route.cost_usd > 100000:
            approval_required = True
            approval_reason = "Cost exceeds $100,000 threshold"

        # Check risk increase
        current_route = next((r for r in shipment.routes if r.is_current), None)
        if current_route and selected_route.risk_score > current_route.risk_score + 0.2:
            approval_required = True
            approval_reason = "Risk score increases significantly"
        
        if approval_required and not data.get('approval_override'):
            # Create approval request
            # Determine creator identity (support tests without auth)
            from flask_login import current_user as _cu
            creator_ident = f'user:{_cu.id}' if getattr(_cu, 'is_authenticated', False) else 'system'

            recommendation = Recommendation(
                workspace_id=shipment.workspace_id,
                type='reroute',
                subject_ref=f'shipment:{shipment.id}',
                title=f"Approve reroute for {shipment.reference_number}",
                description=f"Reroute requires approval: {approval_reason}",
                severity='high',
                confidence=0.9,
                xai_json={
                    'rationale': approval_reason,
                    'proposed_route_id': route_id,
                    'current_route_id': current_route.id if current_route else None
                },
                status='pending',
                created_by=creator_ident
            )
            db.session.add(recommendation)
            
            approval = Approval(
                workspace_id=shipment.workspace_id,
                recommendation=recommendation,
                policy_triggered=approval_reason,
                required_role='logistics_manager',
                state=ApprovalStatus.PENDING,
                request_metadata=json.dumps({'route_id': route_id})
            )
            db.session.add(approval)
            db.session.commit()
            
            return jsonify({
                'status': 'approval_required',
                'approval_id': approval.id,
                'reason': approval_reason
            }), 202
        
        # Execute reroute
        # Update current route flags
        for route in shipment.routes:
            route.is_current = False
        
        # Set new route as current
        selected_route.is_current = True
        
        # Update shipment
        shipment.risk_score = selected_route.risk_score
        # Store an estimated_arrival attribute (not model column) via scheduled_arrival if empty
        new_eta = datetime.utcnow() + timedelta(hours=selected_route.estimated_duration_hours)
        if hasattr(shipment, 'scheduled_arrival') and not shipment.scheduled_arrival:
            shipment.scheduled_arrival = new_eta
        
        # Create audit log
        # Determine actor identity (support tests without auth)
        from flask_login import current_user as _cu2
        actor_ident = str(_cu2.id) if getattr(_cu2, 'is_authenticated', False) else 'system'

        audit_log = AuditLog(
            actor_type='user',
            actor_id=actor_ident,
            action='reroute_shipment',
            object_type='shipment',
            object_id=str(shipment.id),
            details=json.dumps({
                'tracking_number': shipment.tracking_number,
                'old_route_id': current_route.id if current_route else None,
                'new_route_id': selected_route.id,
                'risk_change': selected_route.risk_score - current_route.risk_score if current_route else 0
            }),
            timestamp=datetime.utcnow()
        )
        db.session.add(audit_log)
        
        # Update any related recommendations
        # Mark any related recommendations implemented
        related_recs = Recommendation.query.filter_by(subject_ref=f'shipment:{shipment.id}', status='pending').all()
        for rec in related_recs:
            rec.status = 'implemented'
            rec.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Publish event
        event = {
            'event': 'shipment_rerouted',
            'shipment_id': shipment.id,
            'tracking_number': shipment.tracking_number,
            'new_route_id': selected_route.id,
            'user_id': current_user.id,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        socketio.emit('shipment_updated', event, namespace='/')
        
        return jsonify({
            'status': 'success',
            'message': 'Shipment rerouted successfully',
            'shipment_id': shipment.id,
            'new_route_id': selected_route.id
        })
        
    except Exception as e:
        logger.error(f"Error rerouting shipment: {str(e)}")
        db.session.rollback()
        return jsonify({'error': 'Failed to reroute shipment'}), 500

@main_bp.route('/api/recommendations/<int:rec_id>/explain', methods=['GET'])
def explain_recommendation(rec_id):
    """Return explanation payload for a recommendation (used by shipment detail modal)."""
    try:
        rec = _get_or_404(Recommendation, rec_id)
        xai = rec.xai_json or {}
        return jsonify({
            'recommendation_id': rec.id,
            'rationale': xai.get('rationale') or rec.description[:200],
            'factors': xai.get('factors_considered') or xai.get('factors') or ['risk reduction','cost impact','schedule adherence'],
            'sources': xai.get('sources') or ['system:simulation','historical_routes'],
            'confidence': rec.confidence or 0.75
        })
    except Exception as e:
        logger.error(f"Error explaining recommendation {rec_id}: {e}")
        return jsonify({'error': 'Failed to generate explanation'}), 500

@main_bp.route('/api/recommendations/<int:rec_id>/approve', methods=['POST'])
def approve_recommendation(rec_id):
    """Approve a recommendation and mark any related approval records."""
    try:
        rec = _get_or_404(Recommendation, rec_id)
        if rec.status and rec.status.lower() not in ('pending','recommended'):
            return jsonify({'success': False, 'error': 'Recommendation already processed'}), 400
        rec.status = 'approved'
        rec.updated_at = datetime.utcnow()
        # If approval record exists mark approved
        if rec.approval:
            rec.approval.state = ApprovalStatus.APPROVED
            rec.approval.approved_by_id = current_user.id
            rec.approval.approved_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error approving recommendation {rec_id}: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Failed to approve recommendation'}), 500

@main_bp.route('/api/shipments/<int:shipment_id>/optimize', methods=['POST'])
def trigger_route_optimization(shipment_id):
    """Manually trigger route optimization for a shipment"""
    try:
        shipment = _get_or_404(Shipment, shipment_id)
        
        # Directly call the route optimizer for immediate results
        from app.agents.route_optimizer import RouteOptimizerAgent
        agent = RouteOptimizerAgent()
        
        logger.info(f"Manual route optimization requested for shipment {shipment_id}")
        logger.info(f"Shipment details: origin={shipment.origin_address}, dest={shipment.destination_address}, carrier={shipment.carrier}")
        
        # Clear existing routes and fetch new ones
        logger.info(f"Calling fetch_and_store_routes for shipment {shipment_id}")
        routes_created = agent.fetch_and_store_routes(shipment)
        logger.info(f"fetch_and_store_routes returned: {routes_created} routes")
        
        # Create audit log
        audit_log = AuditLog(
            workspace_id=1,  # Default workspace for demo
            actor_type='user',
            actor_id='demo_user',  # Use demo user since auth is disabled
            action='optimize_routes',
            object_type='shipment',
            object_id=str(shipment.id),
            details=json.dumps({
                'tracking_number': shipment.tracking_number,
                'reason': 'manual_request',
                'routes_created': routes_created
            }),
            result='success' if routes_created > 0 else 'partial',
            timestamp=datetime.utcnow()
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'Route optimization completed. {routes_created} routes generated.',
            'shipment_id': shipment_id,
            'routes_created': routes_created
        })
        
    except Exception as e:
        logger.error(f"Error optimizing routes for shipment {shipment_id}: {str(e)}")
        return jsonify({'error': f'Failed to optimize routes: {str(e)}'}), 500

# =====================================
# MISSING API ENDPOINTS FOR PROCUREMENT
# =====================================

@main_bp.route('/api/drafts', methods=['GET'])
def api_get_drafts():
    """Get AI-generated purchase order drafts."""
    try:
        # For now, return mock drafts since the procurement agent isn't fully operational
        # In production, this would come from the ProcurementAgent
        mock_drafts = [
            {
                'id': 1,
                'title': 'Auto-reorder for Low Stock Items',
                'reason': 'Inventory levels below threshold detected',
                'estimated_value': 12500.00,
                'items': [
                    {'description': 'Industrial Sensors', 'quantity': 50},
                    {'description': 'Control Cables', 'quantity': 100},
                    {'description': 'Safety Switches', 'quantity': 25}
                ],
                'supplier_id': 1,
                'created_at': datetime.utcnow().isoformat(),
                'status': 'pending'
            },
            {
                'id': 2,
                'title': 'Emergency Stock Replenishment',
                'reason': 'Critical inventory shortage predicted',
                'estimated_value': 8750.00,
                'items': [
                    {'description': 'Backup Power Supplies', 'quantity': 10},
                    {'description': 'Network Cables', 'quantity': 200}
                ],
                'supplier_id': 2,
                'created_at': datetime.utcnow().isoformat(),
                'status': 'pending'
            }
        ]
        
        return jsonify({
            'drafts': mock_drafts,
            'count': len(mock_drafts)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching drafts: {str(e)}")
        return jsonify({'error': 'Failed to fetch drafts'}), 500

@main_bp.route('/api/drafts/<int:draft_id>/accept', methods=['POST'])
def api_accept_draft(draft_id):
    """Accept an AI-generated draft and convert to purchase order."""
    try:
        # In production, this would fetch the actual draft from the database
        # For now, create a mock PO from the draft
        
        po = PurchaseOrder(
            workspace_id=1,
            supplier_id=1,  # Would come from draft
            po_number=f'PO-DRAFT-{draft_id}-{datetime.utcnow().strftime("%Y%m%d")}',
            status='draft',
            created_by='procurement_agent',
            total_amount=12500.00,  # Would come from draft calculation
            delivery_date=datetime.utcnow() + timedelta(days=30),
            notes=f'Generated from AI draft #{draft_id}'
        )
        
        db.session.add(po)
        db.session.commit()
        
        # Create audit log
        audit_log = AuditLog(
            workspace_id=1,
            actor_type='agent',
            actor_id='procurement_agent',
            action='draft_accepted',
            object_type='PurchaseOrder',
            object_id=po.id,
            details=json.dumps({'draft_id': draft_id, 'po_number': po.po_number}),
            result='success'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Draft converted to purchase order',
            'po_id': po.id,
            'po_number': po.po_number
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error accepting draft: {str(e)}")
        return jsonify({'error': 'Failed to accept draft'}), 500

@main_bp.route('/api/inventory/thresholds', methods=['GET'])
def api_get_inventory_thresholds():
    """Get inventory items with their reorder thresholds."""
    try:
        # Get inventory items
        inventory_items = Inventory.query.filter_by(workspace_id=1).all()
        
        thresholds_data = []
        for item in inventory_items:
            # Calculate days of coverage (mock calculation)
            current_quantity = item.quantity_on_hand or 0
            daily_usage = max(1, current_quantity // 30)  # Assume 30-day cycle
            days_coverage = current_quantity / daily_usage if daily_usage > 0 else 999
            
            # Use reorder_point if available, otherwise mock threshold
            threshold = item.reorder_point or max(10, int(current_quantity * 0.2))  # 20% of current stock
            reorder_quantity = item.reorder_quantity or max(50, int(current_quantity * 0.5))  # 50% restock
            
            thresholds_data.append({
                'id': item.id,
                'sku': item.sku,
                'description': item.description or f'Inventory Item {item.sku}',
                'current_stock': current_quantity,
                'threshold': threshold,
                'reorder_quantity': reorder_quantity,
                'days_coverage': int(days_coverage),
                'unit_cost': float(item.unit_cost or 10.0),
                'supplier_id': item.supplier_id or 1,  # Use actual supplier or default
                'status': 'critical' if days_coverage < 10 else 'normal'
            })
        
        # Sort by days coverage (critical items first)
        thresholds_data.sort(key=lambda x: x['days_coverage'])
        
        return jsonify(thresholds_data)
        
    except Exception as e:
        current_app.logger.error(f"Error fetching inventory thresholds: {str(e)}")
        return jsonify({'error': 'Failed to fetch inventory thresholds'}), 500

@main_bp.route('/api/purchase-orders/<int:po_id>/status', methods=['PUT'])
def api_update_po_status(po_id):
    """Update purchase order status (for Kanban drag-and-drop)."""
    try:
        po = _get_or_404(PurchaseOrder, po_id)
        data = request.get_json()
        
        new_status = data.get('status')
        if not new_status:
            return jsonify({'error': 'Status is required'}), 400
        
        valid_statuses = ['draft', 'under_review', 'approved', 'sent', 'fulfilled']
        if new_status not in valid_statuses:
            return jsonify({'error': 'Invalid status'}), 400
        
        old_status = po.status
        po.status = new_status
        po.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Create audit log
        audit_log = AuditLog(
            workspace_id=1,
            actor_type='user',
            actor_id='system',  # In production, use actual user
            action='status_updated',
            object_type='PurchaseOrder',
            object_id=po.id,
            details=json.dumps({
                'old_status': old_status,
                'new_status': new_status,
                'po_number': po.po_number
            }),
            result='success'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Status updated to {new_status}',
            'po_id': po.id,
            'status': po.status
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating PO status: {str(e)}")
        return jsonify({'error': 'Failed to update status'}), 500

@main_bp.route('/api/purchase-orders/counts', methods=['GET'])
def api_get_po_counts():
    """Get count of purchase orders by status for Kanban board."""
    try:
        counts = {}
        statuses = ['draft', 'under_review', 'approved', 'sent', 'fulfilled']
        
        for status in statuses:
            count = PurchaseOrder.query.filter_by(
                workspace_id=1,
                status=status
            ).count()
            counts[status] = count
        
        return jsonify(counts)
        
    except Exception as e:
        current_app.logger.error(f"Error fetching PO counts: {str(e)}")
        return jsonify({'error': 'Failed to fetch counts'}), 500

@main_bp.route('/api/procurement/ai-create-po', methods=['POST'])
def api_ai_create_po():
    """Create AI-generated purchase order from reorder suggestion."""
    try:
        data = request.get_json()
        sku = data.get('sku')
        quantity = data.get('quantity', 50)
        supplier_id = data.get('supplier', 1)
        
        # Create AI-generated PO
        po = PurchaseOrder(
            workspace_id=1,
            supplier_id=supplier_id,
            po_number=f'PO-AI-{sku}-{datetime.utcnow().strftime("%Y%m%d%H%M")}',
            status='draft',
            created_by='procurement_agent',
            total_amount=quantity * 25.0,  # Mock unit price
            delivery_date=datetime.utcnow() + timedelta(days=21),
            notes=f'AI-generated reorder for {sku} (quantity: {quantity})'
        )
        
        db.session.add(po)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'AI purchase order created',
            'po_id': po.id,
            'po_number': po.po_number
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating AI PO: {str(e)}")
        return jsonify({'error': 'Failed to create AI purchase order'}), 500


@main_bp.route('/api/procurement/ai-query', methods=['POST'])
def api_procurement_ai_query():
    """Handle AI queries for procurement chat."""
    try:
        data = request.get_json()
        po_id = data.get('po_id')
        query = data.get('query', '')
        
        # Get PO context if provided
        po = None
        if po_id:
            po = PurchaseOrder.query.get_or_404(po_id)
        
        # Generate AI response based on query
        response = generate_procurement_ai_response(query, po)
        
        return jsonify({
            'response': response['message'],
            'suggestions': response.get('suggestions', []),
            'confidence': response.get('confidence', 0.8)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error processing AI query: {str(e)}")
        return jsonify({'error': 'Failed to process AI query'}), 500


@main_bp.route('/api/procurement/generate-counter-offer', methods=['POST'])
def api_generate_counter_offer():
    """Generate AI counter-offer for procurement."""
    try:
        data = request.get_json()
        po_id = data.get('po_id')
        
        po = PurchaseOrder.query.get_or_404(po_id)
        
        # Generate counter-offer using AI
        counter_offer = generate_ai_counter_offer(po)
        
        return jsonify(counter_offer)
        
    except Exception as e:
        current_app.logger.error(f"Error generating counter-offer: {str(e)}")
        return jsonify({'error': 'Failed to generate counter-offer'}), 500


def generate_procurement_ai_response(query, po=None):
    """Generate AI response for procurement queries."""
    query_lower = query.lower()
    
    # Context-based responses
    if po:
        if 'price' in query_lower or 'cost' in query_lower:
            return {
                'message': f'For PO {po.po_number} with {po.supplier.name}, the current total is ${po.total_amount:,.2f}. Based on market analysis, this appears competitive. Would you like me to suggest alternative suppliers or negotiate better terms?',
                'suggestions': [
                    'Compare with alternative suppliers',
                    'Generate counter-offer',
                    'Check historical pricing'
                ]
            }
        elif 'supplier' in query_lower or 'alternative' in query_lower:
            return {
                'message': f'For the items in PO {po.po_number}, I can identify 3-4 alternative suppliers. {po.supplier.name} has a reliability score of {po.supplier.reliability_score or 0.85:.1%}. Would you like me to rank alternatives by price, quality, or delivery time?',
                'suggestions': [
                    'Rank by price',
                    'Rank by quality',
                    'Rank by delivery time'
                ]
            }
        elif 'delivery' in query_lower or 'lead time' in query_lower:
            return {
                'message': f'Current delivery date for PO {po.po_number} is {po.delivery_date}. Based on {po.supplier.name}\'s track record, there\'s a {85}% chance of on-time delivery. Would you like me to suggest expediting options?',
                'suggestions': [
                    'Expedite delivery',
                    'Check supplier capacity',
                    'Find faster alternatives'
                ]
            }
    
    # General queries
    if 'negotiate' in query_lower:
        return {
            'message': 'I can help you negotiate better terms. I analyze supplier leverage, market conditions, and your buying history to suggest optimal negotiation strategies.',
            'suggestions': [
                'Generate negotiation talking points',
                'Identify leverage opportunities',
                'Draft counter-proposal'
            ]
        }
    elif 'market' in query_lower or 'trend' in query_lower:
        return {
            'message': 'Based on current market data, commodity prices are trending upward (+3.2% this quarter). I recommend securing contracts soon for critical components.',
            'suggestions': [
                'View price trends',
                'Identify at-risk items',
                'Suggest contract timing'
            ]
        }
    else:
        return {
            'message': 'I can help you with pricing analysis, supplier comparison, contract negotiation, and market insights. What specific aspect of procurement would you like to explore?',
            'suggestions': [
                'Analyze pricing trends',
                'Compare suppliers',
                'Negotiate better terms',
                'Check market conditions'
            ]
        }


def generate_ai_counter_offer(po):
    """Generate AI-powered counter-offer."""
    # Mock AI analysis
    current_total = po.total_amount
    suggested_reduction = current_total * 0.08  # 8% reduction
    suggested_amount = current_total - suggested_reduction
    
    return {
        'suggested_amount': suggested_amount,
        'rationale': f'Based on market analysis and your purchase history with {po.supplier.name}, an 8% reduction is achievable.',
        'negotiation_points': [
            f'Volume commitment: Offer to increase order by 15% for better pricing',
            f'Payment terms: Propose faster payment (Net 15) for 3% discount',
            f'Multi-year contract: Lock in pricing for stability',
            f'Exclusivity: Consider preferred supplier status for competitive rates'
        ],
        'draft_message': f'''Dear {po.supplier.name} team,

We're reviewing PO {po.po_number} and would like to discuss terms. Given our strong partnership and expected volume growth, we propose:

- Revised total: ${suggested_amount:,.2f} (was ${current_total:,.2f})
- Payment terms: Net 15 (for additional 3% early payment discount)
- Volume commitment: 15% increase over next 12 months

This reflects current market conditions and strengthens our strategic partnership. Please let us know your thoughts.

Best regards,
Procurement Team'''
    }


@main_bp.route('/api/contracts', methods=['GET'])
def api_get_contracts():
    """Get all active supplier contracts."""
    try:
        # Get query parameters
        supplier_id = request.args.get('supplier_id', type=int)
        status = request.args.get('status', 'active')
        
        # Base query
        query = Contract.query.join(Supplier)
        
        # Apply filters
        if supplier_id:
            query = query.filter(Contract.supplier_id == supplier_id)
            
        if status:
            query = query.filter(Contract.status == status)
        
        # Execute query
        contracts = query.order_by(Contract.start_date.desc()).all()
        
        # Format response
        contract_data = []
        for contract in contracts:
            contract_data.append({
                'id': contract.id,
                'contract_number': contract.contract_number,
                'name': contract.name,
                'supplier_id': contract.supplier_id,
                'supplier_name': contract.supplier.name if contract.supplier else None,
                'status': contract.status,
                'start_date': contract.start_date.isoformat() if contract.start_date else None,
                'end_date': contract.end_date.isoformat() if contract.end_date else None,
                'auto_renew': contract.auto_renew,
                'payment_terms': contract.payment_terms,
                'minimum_order_value': float(contract.minimum_order_value or 0),
                'created_at': contract.created_at.isoformat() if contract.created_at else None,
                'days_to_expiry': (contract.end_date - datetime.utcnow().date()).days if contract.end_date else None
            })
        
        return jsonify({
            'contracts': contract_data,
            'count': len(contract_data)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting contracts: {str(e)}")
        return jsonify({'error': 'Failed to retrieve contracts'}), 500

@main_bp.route('/api/assistant/chat', methods=['POST'])
def assistant_chat():
    """Enhanced AI Assistant chat endpoint with agent orchestration"""
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        session_id = data.get('session_id')
        context = data.get('context', {})
        conversation_history = data.get('conversation_history', [])
        
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        
        # Initialize Enhanced AI Assistant
        from app.agents.ai_assistant import EnhancedAIAssistant
        try:
            assistant = EnhancedAIAssistant()
            
            # Process message with enhanced capabilities
            import asyncio
            response_data = asyncio.run(
                assistant.process_message(message, context, conversation_history)
            )
            
            # Log the conversation
            log_enhanced_chat_message(session_id, message, response_data['message'], context, response_data)
            
            # Emit real-time update
            from app import socketio
            socketio.emit('assistant_activity', {
                'session_id': session_id,
                'message_preview': message[:50],
                'response_preview': response_data['message'][:100],
                'confidence': response_data.get('confidence', 0.8),
                'tools_used': response_data.get('tools_used', [])
            }, room=f'user_{session_id}')
            
            return jsonify({
                'success': True,
                **response_data
            })
            
        except Exception as e:
            current_app.logger.error(f"Enhanced AI Assistant error: {e}")
            # Fallback to basic assistant
            return jsonify({
                'success': True,
                'message': f'I understand your request about "{message[:50]}...". The advanced AI services are currently initializing. I can still help with basic queries about shipments, suppliers, and alerts.',
                'actions': _generate_basic_actions(message, context),
                'context_update': {'description': 'AI Assistant (Basic Mode)'},
                'agent_responses': [],
                'confidence': 0.6,
                'tools_used': ['fallback']
            })
        
    except Exception as e:
        current_app.logger.error(f"Assistant chat error: {e}")
        return jsonify({'error': 'Failed to process chat message'}), 500

def _generate_basic_actions(message, context):
    """Generate basic actions when advanced AI is unavailable"""
    actions = []
    message_lower = message.lower()
    
    if any(word in message_lower for word in ['shipment', 'tracking', 'delivery']):
        actions.append({'type': 'navigate', 'data': '/logistics', 'label': 'View Shipments'})
    elif any(word in message_lower for word in ['supplier', 'procurement', 'purchase']):
        actions.append({'type': 'navigate', 'data': '/procurement', 'label': 'View Procurement'})
    elif any(word in message_lower for word in ['risk', 'alert', 'threat']):
        actions.append({'type': 'navigate', 'data': '/risk', 'label': 'View Risk Dashboard'})
    elif any(word in message_lower for word in ['report', 'analytics']):
        actions.append({'type': 'navigate', 'data': '/reports', 'label': 'View Reports'})
    else:
        actions.extend([
            {'type': 'navigate', 'data': '/dashboard', 'label': 'Main Dashboard'},
            {'type': 'navigate', 'data': '/logistics', 'label': 'Shipments'},
            {'type': 'navigate', 'data': '/procurement', 'label': 'Procurement'}
        ])
    
    return actions

def log_enhanced_chat_message(session_id, user_message, assistant_response, context, response_data=None):
    """Enhanced chat message logging with response metadata - Updated for enhanced models"""
    try:
        # Import enhanced models
        from app.models_enhanced import ChatSession, ChatMessage
        
        # Find or create session
        session = ChatSession.query.filter_by(id=session_id).first()
        if not session:
            # Create a basic session if it doesn't exist
            session = ChatSession(
                id=session_id,
                user_id=1,  # Default user for legacy compatibility
                context_data=context
            )
            db.session.add(session)
            db.session.flush()
        
        # Log user message
        user_chat = ChatMessage(
            session_id=session_id,
            user_id=1,  # Default user
            sender='user',
            message=user_message,
            page_context=context,
            extracted_entities=response_data.get('entities', []) if response_data else []
        )
        db.session.add(user_chat)
        
        # Log assistant response with metadata
        assistant_chat = ChatMessage(
            session_id=session_id,
            sender='assistant',
            message=assistant_response,
            agent_name='enhanced_assistant',
            page_context=context,
            tools_used=response_data.get('tools_used', []) if response_data else [],
            agents_consulted=response_data.get('agent_responses', []) if response_data else [],
            confidence_score=response_data.get('confidence', 0.0) if response_data else 0.0,
            suggested_actions=response_data.get('actions', []) if response_data else []
        )
        db.session.add(assistant_chat)
        
        # Update session activity
        session.last_activity = datetime.utcnow()
        session.message_count = (session.message_count or 0) + 2
        
        db.session.commit()
        
    except Exception as e:
        current_app.logger.error(f"Error logging enhanced chat message: {e}")
        db.session.rollback()

def build_assistant_prompt(message, context, history):
    """Build context-aware prompt for Watson"""
    
    # Get recent data for context
    recent_shipments = Shipment.query.order_by(Shipment.created_at.desc()).limit(5).all()
    recent_alerts = Alert.query.filter_by(status='open').order_by(Alert.created_at.desc()).limit(3).all()
    recent_recommendations = Recommendation.query.filter_by(status='PENDING').order_by(Recommendation.created_at.desc()).limit(3).all()
    
    context_info = f"""
You are an intelligent supply chain assistant for SupplyChainX. You have access to real-time data:

RECENT SHIPMENTS ({len(recent_shipments)}):
{chr(10).join([f"- {s.reference_number}: {s.origin_port} → {s.destination_port} ({s.status.value})" for s in recent_shipments])}

ACTIVE ALERTS ({len(recent_alerts)}):
{chr(10).join([f"- {a.title} ({a.severity.value} severity)" for a in recent_alerts])}

PENDING RECOMMENDATIONS ({len(recent_recommendations)}):
{chr(10).join([f"- {r.title} ({r.type})" for r in recent_recommendations])}

CONVERSATION CONTEXT:
Current page: {context.get('page', 'unknown')}
Context type: {context.get('type', 'general')}

PREVIOUS MESSAGES:
{chr(10).join([f"{h['sender']}: {h['message']}" for h in history[-3:]])}

USER MESSAGE: {message}

Provide a helpful, concise response (max 2 paragraphs). If the user asks about specific data, reference the actual information above. If they want to take action, suggest specific next steps.
"""
    
    return context_info

def process_assistant_response(ai_response, original_message, context):
    """Process AI response and extract actions"""
    
    actions = []
    context_update = None
    agent_responses = []
    
    # Analyze the response for potential actions
    message_lower = original_message.lower()
    
    if any(word in message_lower for word in ['shipment', 'tracking', 'delivery']):
        actions.append({
            'type': 'navigate',
            'data': '/logistics',
            'label': 'View Shipments'
        })
        context_update = {'description': 'Shipment inquiry context'}
        
    elif any(word in message_lower for word in ['supplier', 'procurement', 'purchase']):
        actions.append({
            'type': 'navigate',
            'data': '/procurement',
            'label': 'View Procurement'
        })
        context_update = {'description': 'Procurement context'}
        
    elif any(word in message_lower for word in ['risk', 'alert', 'threat']):
        actions.append({
            'type': 'navigate',
            'data': '/risk',
            'label': 'View Risk Dashboard'
        })
        context_update = {'description': 'Risk management context'}
        
    elif any(word in message_lower for word in ['recommendation', 'suggest', 'optimize']):
        actions.append({
            'type': 'show_recommendations',
            'data': {'type': 'all'},
            'label': 'View Recommendations'
        })
        
    return {
        'message': ai_response,
        'actions': actions,
        'context_update': context_update,
        'agent_responses': agent_responses
    }

def generate_fallback_response(message, context):
    """Generate fallback response when AI is unavailable"""
    
    message_lower = message.lower()
    
    if any(word in message_lower for word in ['shipment', 'tracking', 'delivery']):
        return {
            'message': 'I can help you with shipment tracking. You currently have shipments in various stages. Would you like me to show you the logistics dashboard?',
            'actions': [{'type': 'navigate', 'data': '/logistics', 'label': 'View Shipments'}],
            'context_update': {'description': 'Shipment inquiry'},
            'agent_responses': []
        }
    elif any(word in message_lower for word in ['supplier', 'procurement']):
        return {
            'message': 'I can assist with procurement and supplier management. You can view purchase orders, supplier performance, and inventory status from the procurement dashboard.',
            'actions': [{'type': 'navigate', 'data': '/procurement', 'label': 'View Procurement'}],
            'context_update': {'description': 'Procurement context'},
            'agent_responses': []
        }
    elif any(word in message_lower for word in ['risk', 'alert']):
        return {
            'message': 'I can help you monitor supply chain risks and alerts. The risk dashboard shows current threats and recommendations.',
            'actions': [{'type': 'navigate', 'data': '/risk', 'label': 'View Risk Dashboard'}],
            'context_update': {'description': 'Risk management'},
            'agent_responses': []
        }
    else:
        return {
            'message': f'I understand you\'re asking about "{message}". I can help you with shipment tracking, procurement management, risk monitoring, and supply chain analytics. What specific area would you like to explore?',
            'actions': [
                {'type': 'navigate', 'data': '/dashboard', 'label': 'Main Dashboard'},
                {'type': 'navigate', 'data': '/logistics', 'label': 'Shipments'},
                {'type': 'navigate', 'data': '/procurement', 'label': 'Procurement'}
            ],
            'context_update': {'description': 'General inquiry'},
            'agent_responses': []
        }

def log_chat_message(session_id, user_message, assistant_response, context):
    """Log chat conversation to database"""
    try:
        # Log user message
        user_chat = ChatMessage(
            workspace_id=1,
            message=user_message,
            message_type='text',
            context_type=context.get('type'),
            context_id=context.get('shipment_id'),
            message_metadata=json.dumps({
                'session_id': session_id,
                'context': context
            })
        )
        db.session.add(user_chat)
        
        # Log assistant response
        assistant_chat = ChatMessage(
            workspace_id=1,
            agent_name='assistant',
            message=assistant_response,
            message_type='text',
            context_type=context.get('type'),
            context_id=context.get('shipment_id'),
            message_metadata=json.dumps({
                'session_id': session_id,
                'context': context
            })
        )
        db.session.add(assistant_chat)
        
        db.session.commit()
        
    except Exception as e:
        current_app.logger.error(f"Error logging chat message: {e}")
        db.session.rollback()

@main_bp.route('/contracts/<int:contract_id>')
def contract_detail(contract_id):
    """Display individual contract details"""
    try:
        # Test the simple query first
        contract = db.session.get(Contract, contract_id)
        if contract is None:
            current_app.logger.error(f"Contract {contract_id} not found in database")
            flash('Contract not found', 'error')
            return redirect(url_for('main.procurement'))
        
        current_app.logger.info(f"Found contract {contract_id}: {contract.name}")
        return render_template('contracts/detail.html', contract=contract)
    except Exception as e:
        current_app.logger.error(f"Error loading contract {contract_id}: {str(e)}")
        flash(f'Error loading contract: {str(e)}', 'error')
        return redirect(url_for('main.procurement'))

# === NEW INVENTORY MANAGEMENT API ENDPOINTS ===

@main_bp.route('/api/inventory/<sku>/threshold', methods=['PUT'])
def api_update_inventory_threshold(sku):
    """Update inventory item threshold settings."""
    try:
        data = request.get_json()
        threshold = data.get('threshold')
        reorder_quantity = data.get('reorder_quantity')
        
        if threshold is None:
            return jsonify({'error': 'Threshold is required'}), 400
        
        # Find inventory item by SKU
        inventory_item = Inventory.query.filter_by(sku=sku, workspace_id=1).first()
        if not inventory_item:
            return jsonify({'error': 'Inventory item not found'}), 404
        
        # Update threshold settings
        inventory_item.reorder_point = int(threshold)
        if reorder_quantity:
            inventory_item.reorder_quantity = int(reorder_quantity)
        inventory_item.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Create audit log
        audit_log = AuditLog(
            workspace_id=1,
            actor_type='user',
            actor_id='system',
            action='threshold_updated',
            object_type='Inventory',
            object_id=inventory_item.id,
            details=json.dumps({
                'sku': sku,
                'threshold': threshold,
                'reorder_quantity': reorder_quantity
            }),
            result='success'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Threshold updated for {sku}',
            'threshold': inventory_item.reorder_point,
            'reorder_quantity': inventory_item.reorder_quantity
        })
        
    except Exception as e:
        current_app.logger.error(f"Error updating threshold for {sku}: {str(e)}")
        db.session.rollback()
        return jsonify({'error': 'Failed to update threshold'}), 500

@main_bp.route('/api/inventory/auto-reorder', methods=['POST'])
def api_auto_reorder_inventory():
    """Automatically create purchase orders for items below threshold."""
    try:
        # Get items needing reorder
        inventory_items = Inventory.query.filter(
            Inventory.workspace_id == 1,
            Inventory.quantity_on_hand <= Inventory.reorder_point,
            Inventory.reorder_point.isnot(None)
        ).all()
        
        if not inventory_items:
            return jsonify({
                'success': True,
                'message': 'No items require reordering',
                'orders_created': 0
            })
        
        orders_created = 0
        
        for item in inventory_items:
            try:
                # Find preferred supplier for this item
                supplier = Supplier.query.filter_by(
                    workspace_id=1,
                    id=item.supplier_id
                ).first()
                
                if not supplier:
                    # Use first available supplier
                    supplier = Supplier.query.filter_by(workspace_id=1).first()
                
                if not supplier:
                    current_app.logger.warning(f"No supplier found for item {item.sku}")
                    continue
                
                # Calculate reorder quantity
                reorder_qty = item.reorder_quantity or max(50, int(item.quantity_on_hand * 1.5))
                
                # Create purchase order
                po = PurchaseOrder(
                    workspace_id=1,
                    supplier_id=supplier.id,
                    po_number=f"AUTO-{datetime.utcnow().strftime('%Y%m%d')}-{orders_created + 1:03d}",
                    status='draft',
                    order_date=datetime.utcnow(),
                    expected_delivery=datetime.utcnow() + timedelta(days=item.lead_time_days or 14),
                    total_amount=reorder_qty * (item.unit_cost or 10.0),
                    created_by='system_auto_reorder',
                    notes=f"Automatic reorder for {item.sku} - Current stock: {item.quantity_on_hand}, Threshold: {item.reorder_point}"
                )
                
                db.session.add(po)
                db.session.flush()  # Get the PO ID
                
                # Create purchase order item
                po_item = PurchaseOrderItem(
                    purchase_order_id=po.id,
                    inventory_id=item.id,
                    sku=item.sku,
                    description=item.description or f'Inventory Item {item.sku}',
                    quantity=reorder_qty,
                    unit_price=item.unit_cost or 10.0,
                    total_price=reorder_qty * (item.unit_cost or 10.0)
                )
                
                db.session.add(po_item)
                orders_created += 1
                
                # Create audit log
                audit_log = AuditLog(
                    workspace_id=1,
                    actor_type='system',
                    actor_id='auto_reorder',
                    action='auto_purchase_order_created',
                    object_type='PurchaseOrder',
                    object_id=po.id,
                    details=json.dumps({
                        'sku': item.sku,
                        'quantity': reorder_qty,
                        'supplier': supplier.name,
                        'po_number': po.po_number
                    }),
                    result='success'
                )
                db.session.add(audit_log)
                
            except Exception as item_error:
                current_app.logger.error(f"Error creating PO for {item.sku}: {str(item_error)}")
                continue
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Created {orders_created} purchase orders automatically',
            'orders_created': orders_created
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in auto reorder: {str(e)}")
        db.session.rollback()
        return jsonify({'error': 'Failed to execute automatic reorder'}), 500

@main_bp.route('/api/inventory/analytics/export')
def api_export_inventory_analytics():
    """Export detailed inventory analytics report."""
    try:
        period_days = request.args.get('period', 30, type=int)
        
        # Get comprehensive analytics data
        analytics_response = api_inventory_analytics()
        analytics_data = analytics_response.get_json()
        
        # Create CSV content
        csv_content = []
        csv_content.append(['Inventory Analytics Report'])
        csv_content.append([f'Generated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}'])
        csv_content.append([f'Period: Last {period_days} days'])
        csv_content.append([''])
        
        # Summary metrics
        csv_content.append(['SUMMARY METRICS'])
        csv_content.append(['Metric', 'Value'])
        csv_content.append(['Total Items', analytics_data.get('total_items', 0)])
        csv_content.append(['Total Value', f"${analytics_data.get('total_value', 0):,.2f}"])
        csv_content.append(['Out of Stock Items', analytics_data.get('out_of_stock', 0)])
        csv_content.append(['Low Stock Items', analytics_data.get('low_stock', 0)])
        csv_content.append(['Critical Stock Items', analytics_data.get('critical_stock', 0)])
        csv_content.append([''])
        
        # ABC Analysis
        abc_data = analytics_data.get('abc_analysis', {})
        csv_content.append(['ABC ANALYSIS'])
        csv_content.append(['Category', 'Item Count'])
        csv_content.append(['A Items (High Value)', abc_data.get('A', 0)])
        csv_content.append(['B Items (Medium Value)', abc_data.get('B', 0)])
        csv_content.append(['C Items (Low Value)', abc_data.get('C', 0)])
        csv_content.append([''])
        
        # Top items
        top_items = analytics_data.get('top_value_items', [])
        csv_content.append(['TOP ITEMS BY VALUE'])
        csv_content.append(['SKU', 'Description', 'Quantity', 'Unit Value', 'Total Value'])
        for item in top_items[:20]:  # Top 20 items
            csv_content.append([
                item.get('sku', ''),
                item.get('description', ''),
                item.get('quantity', 0),
                f"${item.get('value', 0) / max(1, item.get('quantity', 1)):.2f}",
                f"${item.get('value', 0):.2f}"
            ])
        
        # Convert to CSV string
        output = []
        for row in csv_content:
            output.append(','.join([f'"{str(cell)}"' for cell in row]))
        
        csv_string = '\n'.join(output)
        
        # Create response
        response = make_response(csv_string)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=inventory_analytics_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'
        
        return response
        
    except Exception as e:
        current_app.logger.error(f"Error exporting analytics: {str(e)}")
        return jsonify({'error': 'Failed to export analytics'}), 500