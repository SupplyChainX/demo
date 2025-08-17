"""
Real-Time Analytics API Routes
Enhanced endpoints for Phase 5: Real-Time Analytics Engine

Provides WebSocket-enabled real-time metrics and KPI data
"""
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from flask_socketio import emit
from app import db
from app.models import KPISnapshot, Alert, Shipment
from app.analytics.kpi_collector import KPICollector
from app.utils.metrics import MetricsCalculator

logger = logging.getLogger(__name__)

# Create blueprint
realtime_bp = Blueprint('realtime', __name__)

@realtime_bp.route('/metrics/live', methods=['GET'])
def get_live_metrics():
    """
    Get current real-time metrics
    
    Returns:
        JSON with real-time metric values and trends
    """
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        
        calculator = MetricsCalculator(workspace_id)
        metrics_summary = calculator.get_metrics_summary()
        
        return jsonify({
            'success': True,
            'data': metrics_summary,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting live metrics: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@realtime_bp.route('/dashboard/live', methods=['GET'])
def get_live_dashboard():
    """
    Get complete live dashboard data including metrics, trends, and alerts
    
    Returns:
        JSON with comprehensive dashboard data
    """
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        
        kpi_collector = KPICollector(workspace_id, enable_realtime=True)
        dashboard_data = kpi_collector.get_live_dashboard_data()
        
        return jsonify({
            'success': True,
            'data': dashboard_data,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting live dashboard: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@realtime_bp.route('/metrics/historical', methods=['GET'])
def get_historical_metrics():
    """
    Get historical metrics data for charting
    
    Query Parameters:
        - metric_name: Name of the metric
        - days: Number of days to look back (default: 30)
        - period_type: daily, weekly, monthly (default: daily)
    
    Returns:
        JSON with historical data points
    """
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        metric_name = request.args.get('metric_name', required=True)
        days = request.args.get('days', 30, type=int)
        period_type = request.args.get('period_type', 'daily')
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        snapshots = db.session.query(KPISnapshot).filter(
            KPISnapshot.workspace_id == workspace_id,
            KPISnapshot.metric_name == metric_name,
            KPISnapshot.period_type == period_type,
            KPISnapshot.period_start >= start_date,
            KPISnapshot.period_start <= end_date
        ).order_by(KPISnapshot.period_start).all()
        
        data_points = [
            {
                'date': snapshot.period_start.isoformat(),
                'value': snapshot.value,
                'unit': snapshot.unit,
                'confidence': snapshot.confidence_level
            }
            for snapshot in snapshots
        ]
        
        return jsonify({
            'success': True,
            'data': {
                'metric_name': metric_name,
                'period_type': period_type,
                'data_points': data_points,
                'total_points': len(data_points)
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting historical metrics: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@realtime_bp.route('/metrics/trending', methods=['GET'])
def get_trending_analysis():
    """
    Get trending analysis for a specific metric
    
    Query Parameters:
        - metric_name: Name of the metric
        - days: Number of days for analysis (default: 30)
    
    Returns:
        JSON with trending analysis
    """
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        metric_name = request.args.get('metric_name', required=True)
        days = request.args.get('days', 30, type=int)
        
        kpi_collector = KPICollector(workspace_id)
        trending_data = kpi_collector.calculate_trending_metrics(metric_name, days)
        
        return jsonify({
            'success': True,
            'data': trending_data
        })
        
    except Exception as e:
        logger.error(f"Error getting trending analysis: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@realtime_bp.route('/metrics/comparative', methods=['GET'])
def get_comparative_analysis():
    """
    Get comparative analysis (YoY, MoM, WoW)
    
    Query Parameters:
        - metric_name: Name of the metric
        - compare_type: yoy, mom, wow (default: mom)
    
    Returns:
        JSON with comparative analysis
    """
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        metric_name = request.args.get('metric_name', required=True)
        compare_type = request.args.get('compare_type', 'mom')
        
        kpi_collector = KPICollector(workspace_id)
        comparative_data = kpi_collector.generate_comparative_analytics(metric_name, compare_type)
        
        return jsonify({
            'success': True,
            'data': comparative_data
        })
        
    except Exception as e:
        logger.error(f"Error getting comparative analysis: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@realtime_bp.route('/alerts/active', methods=['GET'])
def get_active_alerts():
    """
    Get currently active alerts for real-time monitoring
    
    Returns:
        JSON with active alerts data
    """
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        limit = request.args.get('limit', 10, type=int)
        
        active_alerts = db.session.query(Alert).filter(
            Alert.workspace_id == workspace_id,
            Alert.status == 'open'
        ).order_by(Alert.created_at.desc()).limit(limit).all()
        
        alerts_data = []
        for alert in active_alerts:
            alerts_data.append({
                'id': alert.id,
                'title': alert.title,
                'description': alert.description,
                'severity': alert.severity.value if hasattr(alert.severity, 'value') else str(alert.severity),
                'type': alert.type,
                'created_at': alert.created_at.isoformat(),
                'location': alert.location,
                'probability': alert.probability,
                'confidence': alert.confidence
            })
        
        return jsonify({
            'success': True,
            'data': {
                'alerts': alerts_data,
                'total_count': len(alerts_data),
                'critical_count': len([a for a in alerts_data if a['severity'] == 'critical']),
                'high_count': len([a for a in alerts_data if a['severity'] == 'high'])
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting active alerts: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@realtime_bp.route('/system/health', methods=['GET'])
def get_system_health():
    """
    Get overall system health metrics
    
    Returns:
        JSON with system health data
    """
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        
        # Calculate system health metrics
        now = datetime.utcnow()
        last_24h = now - timedelta(hours=24)
        
        # Active alerts
        critical_alerts = db.session.query(Alert).filter(
            Alert.workspace_id == workspace_id,
            Alert.status == 'open',
            Alert.severity == 'critical'
        ).count()
        
        total_alerts = db.session.query(Alert).filter(
            Alert.workspace_id == workspace_id,
            Alert.status == 'open'
        ).count()
        
        # Active shipments
        active_shipments = db.session.query(Shipment).filter(
            Shipment.workspace_id == workspace_id,
            Shipment.status.in_(['planned', 'booked', 'in_transit'])
        ).count()
        
        # Recent activity
        recent_shipments = db.session.query(Shipment).filter(
            Shipment.workspace_id == workspace_id,
            Shipment.created_at >= last_24h
        ).count()
        
        # Calculate health score
        health_score = 100
        if critical_alerts > 0:
            health_score -= critical_alerts * 20
        if total_alerts > 5:
            health_score -= (total_alerts - 5) * 5
        
        health_score = max(0, min(100, health_score))
        
        # Determine status
        if health_score >= 90:
            status = 'excellent'
        elif health_score >= 75:
            status = 'good'
        elif health_score >= 60:
            status = 'fair'
        else:
            status = 'poor'
        
        health_data = {
            'overall_score': health_score,
            'status': status,
            'timestamp': now.isoformat(),
            'metrics': {
                'critical_alerts': critical_alerts,
                'total_alerts': total_alerts,
                'active_shipments': active_shipments,
                'recent_activity': recent_shipments
            },
            'components': {
                'alerts_system': 'operational' if total_alerts < 10 else 'degraded',
                'shipment_tracking': 'operational' if active_shipments > 0 else 'idle',
                'analytics_engine': 'operational',
                'policy_engine': 'operational'
            }
        }
        
        return jsonify({
            'success': True,
            'data': health_data
        })
        
    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@realtime_bp.route('/monitoring/start', methods=['POST'])
def start_monitoring():
    """
    Start real-time monitoring with WebSocket updates
    
    Request Body:
        - interval_seconds: Update interval (default: 30)
        - workspace_id: Workspace to monitor (default: 1)
    
    Returns:
        JSON confirmation of monitoring start
    """
    try:
        data = request.get_json() or {}
        workspace_id = data.get('workspace_id', 1)
        interval_seconds = data.get('interval_seconds', 30)
        
        # Initialize KPI collector with real-time monitoring
        kpi_collector = KPICollector(workspace_id, enable_realtime=True)
        kpi_collector.start_real_time_monitoring(interval_seconds)
        
        return jsonify({
            'success': True,
            'message': 'Real-time monitoring started',
            'interval_seconds': interval_seconds,
            'workspace_id': workspace_id
        })
        
    except Exception as e:
        logger.error(f"Error starting monitoring: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# WebSocket event handlers for real-time updates
from app.extensions import socketio

@socketio.on('subscribe_metrics')
def handle_subscribe_metrics(data):
    """Handle client subscription to real-time metrics"""
    try:
        workspace_id = data.get('workspace_id', 1)
        logger.info(f"Client subscribed to metrics for workspace {workspace_id}")
        
        # Send initial metrics data
        calculator = MetricsCalculator(workspace_id)
        initial_metrics = calculator.get_metrics_summary()
        
        emit('initial_metrics', {
            'type': 'initial_metrics',
            'timestamp': datetime.utcnow().isoformat(),
            'workspace_id': workspace_id,
            'metrics': initial_metrics
        })
        
    except Exception as e:
        logger.error(f"Error handling metrics subscription: {e}")
        emit('error', {'message': 'Failed to subscribe to metrics'})

@socketio.on('subscribe_dashboard')
def handle_subscribe_dashboard(data):
    """Handle client subscription to dashboard updates"""
    try:
        workspace_id = data.get('workspace_id', 1)
        logger.info(f"Client subscribed to dashboard for workspace {workspace_id}")
        
        # Send initial dashboard data
        kpi_collector = KPICollector(workspace_id, enable_realtime=True)
        initial_dashboard = kpi_collector.get_live_dashboard_data()
        
        emit('initial_dashboard', {
            'type': 'initial_dashboard',
            'timestamp': datetime.utcnow().isoformat(),
            'workspace_id': workspace_id,
            'data': initial_dashboard
        })
        
    except Exception as e:
        logger.error(f"Error handling dashboard subscription: {e}")
        emit('error', {'message': 'Failed to subscribe to dashboard'})

@socketio.on('request_metric_update')
def handle_metric_update_request(data):
    """Handle on-demand metric update requests"""
    try:
        workspace_id = data.get('workspace_id', 1)
        metric_name = data.get('metric_name')
        
        calculator = MetricsCalculator(workspace_id)
        
        if metric_name:
            # Get specific metric
            if hasattr(calculator, f'calculate_real_time_{metric_name}'):
                metric_func = getattr(calculator, f'calculate_real_time_{metric_name}')
                metric_data = metric_func()
                
                emit('metric_update', {
                    'type': 'metric_update',
                    'timestamp': datetime.utcnow().isoformat(),
                    'workspace_id': workspace_id,
                    'metric_name': metric_name,
                    'data': {
                        'value': metric_data.value,
                        'unit': metric_data.unit,
                        'trend': metric_data.trend,
                        'change_percent': metric_data.change_percent,
                        'status': metric_data.status,
                        'metadata': metric_data.metadata
                    }
                })
            else:
                emit('error', {'message': f'Unknown metric: {metric_name}'})
        else:
            # Get all metrics
            metrics_summary = calculator.get_metrics_summary()
            emit('metrics_update', {
                'type': 'metrics_update',
                'timestamp': datetime.utcnow().isoformat(),
                'workspace_id': workspace_id,
                'metrics': metrics_summary
            })
        
    except Exception as e:
        logger.error(f"Error handling metric update request: {e}")
        emit('error', {'message': 'Failed to update metrics'})
