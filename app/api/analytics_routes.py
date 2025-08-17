"""
Analytics API Routes
Provides endpoints for historical KPI tracking and analytics
"""

from flask import Blueprint, jsonify, request
from app.analytics.kpi_collector import KPICollector
from app.models import KPISnapshot
from app import db
from datetime import datetime, timedelta
import logging

analytics_bp = Blueprint('analytics', __name__)
logger = logging.getLogger(__name__)

@analytics_bp.route('/kpis', methods=['GET'])
def get_kpis():
    """Get current KPI values"""
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        period = request.args.get('period', 'daily')
        
        # Don't use KPICollector for now - direct query
        # collector = KPICollector(workspace_id)
        
        # Get latest snapshots
        latest_snapshots = db.session.query(KPISnapshot).filter(
            KPISnapshot.workspace_id == workspace_id,
            KPISnapshot.period_type == period
        ).order_by(KPISnapshot.period_start.desc()).limit(30).all()
        
        snapshots_data = []
        for snapshot in latest_snapshots:
            snapshots_data.append({
                'date': snapshot.period_start.isoformat(),
                'type': snapshot.period_type,
                'metric_name': snapshot.metric_name,
                'value': snapshot.value,
                'unit': snapshot.unit,
                'category': snapshot.metric_category
            })
        
        return jsonify({
            'success': True,
            'workspace_id': workspace_id,
            'period': period,
            'snapshots': snapshots_data,
            'count': len(snapshots_data)
        })
        
    except Exception as e:
        logger.error(f"Error getting KPIs: {e}")
        return jsonify({'error': str(e)}), 500

@analytics_bp.route('/kpis/trends', methods=['GET'])
def get_kpi_trends():
    """Get KPI trends over time"""
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        days = request.args.get('days', 30, type=int)
        
        since_date = datetime.utcnow() - timedelta(days=days)
        
        # Get snapshots for the specified period
        snapshots = db.session.query(KPISnapshot).filter(
            KPISnapshot.workspace_id == workspace_id,
            KPISnapshot.period_start >= since_date
        ).order_by(KPISnapshot.period_start.asc()).all()
        
        # Group by metric name for trends
        trends = {}
        for snapshot in snapshots:
            metric_name = snapshot.metric_name
            if metric_name not in trends:
                trends[metric_name] = {
                    'metric_name': metric_name,
                    'category': snapshot.metric_category,
                    'unit': snapshot.unit,
                    'data_points': []
                }
            
            trends[metric_name]['data_points'].append({
                'date': snapshot.period_start.isoformat(),
                'value': snapshot.value
            })
        
        return jsonify({
            'success': True,
            'workspace_id': workspace_id,
            'days': days,
            'trends': list(trends.values())
        })
        
    except Exception as e:
        logger.error(f"Error getting KPI trends: {e}")
        return jsonify({'error': str(e)}), 500

@analytics_bp.route('/performance', methods=['GET'])
def get_performance_analytics():
    """Get performance analytics"""
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        
        collector = KPICollector(workspace_id)
        
        # Get recent KPI snapshots for analysis
        recent_snapshots = db.session.query(KPISnapshot).filter(
            KPISnapshot.workspace_id == workspace_id,
            KPISnapshot.period_start >= datetime.utcnow() - timedelta(days=7)
        ).all()
        
        if not recent_snapshots:
            return jsonify({
                'success': True,
                'workspace_id': workspace_id,
                'message': 'No recent performance data available',
                'performance_metrics': {}
            })
        
        # Calculate performance metrics from snapshots
        if not recent_snapshots:
            return jsonify({
                'success': True,
                'workspace_id': workspace_id,
                'message': 'No recent performance data available',
                'performance_metrics': {}
            })
        
        # Group snapshots by metric
        metrics_by_name = {}
        for snapshot in recent_snapshots:
            metric_name = snapshot.metric_name
            if metric_name not in metrics_by_name:
                metrics_by_name[metric_name] = []
            metrics_by_name[metric_name].append(snapshot)
        
        # Calculate aggregated metrics
        performance_metrics = {}
        for metric_name, snapshots in metrics_by_name.items():
            avg_value = sum(s.value for s in snapshots) / len(snapshots)
            performance_metrics[metric_name] = {
                'average_value': round(avg_value, 2),
                'unit': snapshots[0].unit,
                'category': snapshots[0].metric_category,
                'data_points': len(snapshots)
            }
        
        return jsonify({
            'success': True,
            'workspace_id': workspace_id,
            'period': '7 days',
            'performance_metrics': performance_metrics
        })
        
    except Exception as e:
        logger.error(f"Error getting performance analytics: {e}")
        return jsonify({'error': str(e)}), 500

@analytics_bp.route('/comparative', methods=['GET'])
def get_comparative_analytics():
    """Get comparative analytics between periods"""
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        
        collector = KPICollector(workspace_id)
        
        # Get current week vs previous week
        current_week_start = datetime.utcnow() - timedelta(days=7)
        previous_week_start = datetime.utcnow() - timedelta(days=14)
        
        current_week = db.session.query(KPISnapshot).filter(
            KPISnapshot.workspace_id == workspace_id,
            KPISnapshot.period_start >= current_week_start
        ).all()
        
        previous_week = db.session.query(KPISnapshot).filter(
            KPISnapshot.workspace_id == workspace_id,
            KPISnapshot.period_start >= previous_week_start,
            KPISnapshot.period_start < current_week_start
        ).all()
        
        def calculate_metrics(snapshots):
            if not snapshots:
                return {}
            
            # Group by metric name and calculate averages
            metrics_by_name = {}
            for snapshot in snapshots:
                metric_name = snapshot.metric_name
                if metric_name not in metrics_by_name:
                    metrics_by_name[metric_name] = []
                metrics_by_name[metric_name].append(snapshot.value)
            
            # Calculate averages for each metric
            result = {}
            for metric_name, values in metrics_by_name.items():
                result[metric_name] = sum(values) / len(values)
                
            return result
        
        current_metrics = calculate_metrics(current_week)
        previous_metrics = calculate_metrics(previous_week)
        
        # Calculate changes
        changes = {}
        for key in current_metrics:
            current_val = current_metrics[key]
            previous_val = previous_metrics[key]
            
            if previous_val > 0:
                change_pct = ((current_val - previous_val) / previous_val) * 100
            else:
                change_pct = 100 if current_val > 0 else 0
                
            changes[key] = {
                'current': current_val,
                'previous': previous_val,
                'change_pct': round(change_pct, 2)
            }
        
        return jsonify({
            'success': True,
            'workspace_id': workspace_id,
            'comparison': 'Current week vs Previous week',
            'current_period': current_metrics,
            'previous_period': previous_metrics,
            'changes': changes
        })
        
    except Exception as e:
        logger.error(f"Error getting comparative analytics: {e}")
        return jsonify({'error': str(e)}), 500
