"""
Reports API Routes - Enhanced with Phase 2 Analytics Engine
Live Data Integration for Reports Dashboard with Historical KPI Tracking
"""
from flask import jsonify, request, current_app
from datetime import datetime, timedelta
from sqlalchemy import func, desc, asc
import json
from app.api import api_bp
from app import db
from app.models import (
    Shipment, Alert, Recommendation, PurchaseOrder, 
    Supplier, AlertSeverity, ShipmentStatus,
    KPISnapshot, DecisionItem, PolicyTrigger  # Phase 2 models
)
from app.analytics.kpi_collector import KPICollector  # Phase 2 analytics engine

# Initialize analytics engine for enhanced reporting
kpi_collector = KPICollector(workspace_id=1)

# Helper function for date range parsing
def parse_period(period='7d'):
    """Parse period string and return start_date, end_date"""
    now = datetime.utcnow()
    end_date = now
    
    if period == 'qtd':  # Quarter to date
        # Get current quarter start
        quarter = (now.month - 1) // 3 + 1
        start_month = (quarter - 1) * 3 + 1
        start_date = datetime(now.year, start_month, 1)
    elif period == 'ytd':  # Year to date
        start_date = datetime(now.year, 1, 1)
    elif period == '6months':
        start_date = now - timedelta(days=180)
    elif period == '6weeks':
        start_date = now - timedelta(weeks=6)
    elif period.endswith('d'):
        days = int(period[:-1])
        start_date = now - timedelta(days=days)
    elif period.endswith('w'):
        weeks = int(period[:-1])
        start_date = now - timedelta(weeks=weeks)
    elif period.endswith('m'):
        months = int(period[:-1])
        start_date = now - timedelta(days=months*30)
    else:
        # Default to 7 days
        start_date = now - timedelta(days=7)
    
    return start_date, end_date

def calculate_avg_risk_score():
    """Calculate average risk score across active shipments"""
    result = db.session.query(func.avg(Shipment.risk_score)).filter(
        Shipment.status.in_(['planned', 'in_transit'])
    ).scalar()
    return round(result, 4) if result else 0.0

def calculate_pending_approvals():
    """Calculate number of pending approvals using DecisionItem model"""
    return db.session.query(DecisionItem).filter(
        DecisionItem.status == 'pending',
        DecisionItem.requires_approval == True
    ).count()

def _generate_comparison_summary(comparative_data):
    """Generate summary of comparative analysis"""
    improving = 0
    declining = 0
    stable = 0
    
    for kpi, data in comparative_data.items():
        change_percent = data.get('change_percent', 0)
        if change_percent > 5:
            improving += 1
        elif change_percent < -5:
            declining += 1
        else:
            stable += 1
    
    return {
        'improving_metrics': improving,
        'declining_metrics': declining,
        'stable_metrics': stable,
        'total_metrics': len(comparative_data)
    }

def calculate_on_time_rate(start_date=None, end_date=None):
    """Calculate on-time delivery rate"""
    query = Shipment.query
    if start_date:
        query = query.filter(Shipment.created_at >= start_date)
    if end_date:
        query = query.filter(Shipment.created_at <= end_date)
    
    total_delivered = query.filter(Shipment.status == 'delivered').count()
    if total_delivered == 0:
        return 0.0
    
    # On-time = delivered before or on scheduled arrival
    on_time = query.filter(
        Shipment.status == 'delivered',
        Shipment.actual_arrival <= Shipment.scheduled_arrival
    ).count()
    
    return (on_time / total_delivered) * 100

def calculate_cost_avoided(start_date=None, end_date=None):
    """Calculate cost avoided through route optimization"""
    # For Phase 1, return estimate based on recommendations
    rec_query = Recommendation.query.filter(
        Recommendation.type == 'reroute',
        Recommendation.status == 'approved'
    )
    if start_date:
        rec_query = rec_query.filter(Recommendation.created_at >= start_date)
    if end_date:
        rec_query = rec_query.filter(Recommendation.created_at <= end_date)
    
    approved_reroutes = rec_query.count()
    # Estimate $5000 average savings per approved reroute
    return approved_reroutes * 5000

def calculate_emissions_by_route(start_date=None, end_date=None):
    """Calculate emissions data by route type"""
    from app.models import Route, RouteType
    
    query = db.session.query(
        Route.route_type,
        func.sum(Route.carbon_emissions_kg).label('total_emissions'),
        func.count(Route.id).label('route_count')
    ).join(Shipment)
    
    if start_date:
        query = query.filter(Shipment.created_at >= start_date)
    if end_date:
        query = query.filter(Shipment.created_at <= end_date)
    
    results = query.group_by(Route.route_type).all()
    
    emissions_data = {}
    for route_type, total_emissions, count in results:
        route_name = route_type.value if hasattr(route_type, 'value') else str(route_type)
        emissions_data[route_name] = {
            'total_emissions_kg': float(total_emissions or 0),
            'route_count': count,
            'avg_emissions_kg': float(total_emissions or 0) / count if count > 0 else 0
        }
    
    return emissions_data

def calculate_alert_mttr(start_date=None, end_date=None):
    """Calculate Mean Time to Resolution for alerts"""
    query = Alert.query.filter(Alert.status == 'resolved')
    if start_date:
        query = query.filter(Alert.created_at >= start_date)
    if end_date:
        query = query.filter(Alert.created_at <= end_date)
    
    alerts = query.all()
    if not alerts:
        return 0
    
    total_resolution_time = 0
    resolved_count = 0
    
    for alert in alerts:
        if alert.resolved_at and alert.created_at:
            resolution_time = (alert.resolved_at - alert.created_at).total_seconds() / 3600  # hours
            total_resolution_time += resolution_time
            resolved_count += 1
    
    return total_resolution_time / resolved_count if resolved_count > 0 else 0

# === REPORTS API ENDPOINTS ===

@api_bp.route('/reports/kpis', methods=['GET'])
def get_reports_kpis():
    """Get comprehensive KPI metrics with enhanced analytics."""
    try:
        period = request.args.get('period', 'mtd')
        compare = request.args.get('compare')  # 'yoy', 'mom', 'wow'
        
        # Get date range
        start_date, end_date = parse_period(period)
        
        # Calculate current KPIs
        kpis = {
            'on_time_delivery_rate': calculate_on_time_rate(start_date, end_date),
            'cost_avoided_usd': calculate_cost_avoided(start_date, end_date),
            'average_risk_score': calculate_avg_risk_score(),
            'active_alerts': Alert.query.filter_by(status='open').count(),
            'pending_approvals': calculate_pending_approvals(),
            'total_shipments': Shipment.query.filter(
                Shipment.created_at.between(start_date, end_date)
            ).count()
        }
        
        response_data = {
            'kpis': kpis,
            'period': period,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Add comparative analysis if requested (Phase 2 Enhancement)
        if compare:
            try:
                comparative_data = {}
                for kpi_name in kpis.keys():
                    comparison = kpi_collector.generate_comparative_analytics(kpi_name, compare)
                    comparative_data[kpi_name] = comparison
                
                response_data['comparison'] = {
                    'type': compare,
                    'data': comparative_data,
                    'summary': _generate_comparison_summary(comparative_data)
                }
            except Exception as e:
                current_app.logger.warning(f"Could not generate comparative analytics: {e}")
        
        return jsonify(response_data)
        
    except Exception as e:
        current_app.logger.error(f"Error in get_reports_kpis: {e}")
        return jsonify({'error': 'Failed to retrieve KPI data'}), 500

@api_bp.route('/reports/kpis/historical', methods=['GET'])
def get_historical_kpis():
    """Get historical KPI data for trending analysis (Phase 2 Feature)."""
    try:
        metric_name = request.args.get('metric', 'on_time_delivery_rate')
        days = int(request.args.get('days', 30))
        period_type = request.args.get('period_type', 'daily')
        
        # Get historical snapshots
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        snapshots = db.session.query(KPISnapshot).filter(
            KPISnapshot.workspace_id == 1,
            KPISnapshot.metric_name == metric_name,
            KPISnapshot.period_type == period_type,
            KPISnapshot.period_start >= start_date,
            KPISnapshot.period_start <= end_date
        ).order_by(KPISnapshot.period_start).all()
        
        # Generate trending analysis
        trending_data = kpi_collector.calculate_trending_metrics(metric_name, days)
        
        # Format data for charts
        chart_data = []
        for snapshot in snapshots:
            chart_data.append({
                'date': snapshot.period_start.isoformat(),
                'value': snapshot.value,
                'period_label': snapshot.period_label,
                'confidence': snapshot.confidence_level
            })
        
        return jsonify({
            'metric_name': metric_name,
            'period_type': period_type,
            'days_analyzed': days,
            'data_points': len(chart_data),
            'chart_data': chart_data,
            'trending_analysis': trending_data,
            'last_updated': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_historical_kpis: {e}")
        return jsonify({'error': 'Failed to retrieve historical KPI data'}), 500

@api_bp.route('/reports/on-time-delivery', methods=['GET'])
def get_on_time_delivery_trend():
    """Get on-time delivery trend data"""
    period = request.args.get('period', '6months')
    start_date, end_date = parse_period(period)
    
    # Generate weekly data points
    data_points = []
    current = start_date
    while current < end_date:
        week_end = min(current + timedelta(days=7), end_date)
        rate = calculate_on_time_rate(current, week_end)
        data_points.append({
            'date': current.strftime('%Y-%m-%d'),
            'on_time_rate': round(rate, 2)
        })
        current = week_end
    
    return jsonify({
        'period': period,
        'data': data_points,
        'summary': {
            'average_rate': round(sum(d['on_time_rate'] for d in data_points) / len(data_points), 2) if data_points else 0,
            'best_week': max(data_points, key=lambda x: x['on_time_rate']) if data_points else None,
            'worst_week': min(data_points, key=lambda x: x['on_time_rate']) if data_points else None
        }
    })

@api_bp.route('/reports/cost-avoided', methods=['GET'])
def get_cost_avoided_trend():
    """Get cost avoided through optimizations over time"""
    period = request.args.get('period', 'ytd')
    start_date, end_date = parse_period(period)
    
    # Monthly aggregation for cost avoided (SQLite compatible)
    # Use strftime for SQLite compatibility instead of date_trunc
    monthly_data = db.session.query(
        func.strftime('%Y-%m', Recommendation.created_at).label('month'),
        func.count(Recommendation.id).label('reroute_count')
    ).filter(
        Recommendation.type == 'reroute',
        Recommendation.status == 'approved',
        Recommendation.created_at >= start_date,
        Recommendation.created_at <= end_date
    ).group_by(func.strftime('%Y-%m', Recommendation.created_at)).all()
    
    data_points = []
    cumulative_savings = 0
    
    for month_str, reroute_count in monthly_data:
        monthly_savings = reroute_count * 5000  # $5000 per approved reroute
        cumulative_savings += monthly_savings
        
        data_points.append({
            'month': month_str,  # Already in YYYY-MM format from strftime
            'monthly_savings': monthly_savings,
            'cumulative_savings': cumulative_savings,
            'reroute_count': reroute_count
        })
    
    return jsonify({
        'period': period,
        'data': data_points,
        'total_savings': cumulative_savings,
        'average_per_reroute': 5000
    })

@api_bp.route('/reports/emissions-by-route', methods=['GET'])
def get_emissions_by_route():
    """Get emissions data by route type"""
    period = request.args.get('period', 'qtd')
    start_date, end_date = parse_period(period)
    
    emissions_data = calculate_emissions_by_route(start_date, end_date)
    
    return jsonify({
        'period': period,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'emissions_by_route': emissions_data
    })

@api_bp.route('/reports/alert-mttr', methods=['GET'])
def get_alert_mttr():
    """Get Mean Time to Resolution for alerts"""
    period = request.args.get('period', '6weeks')
    start_date, end_date = parse_period(period)
    
    mttr_hours = calculate_alert_mttr(start_date, end_date)
    
    # Get alert resolution trend
    weekly_data = []
    current = start_date
    while current < end_date:
        week_end = min(current + timedelta(days=7), end_date)
        week_mttr = calculate_alert_mttr(current, week_end)
        weekly_data.append({
            'week': current.strftime('%Y-%m-%d'),
            'mttr_hours': round(week_mttr, 2)
        })
        current = week_end
    
    return jsonify({
        'period': period,
        'overall_mttr_hours': round(mttr_hours, 2),
        'weekly_trend': weekly_data,
        'target_mttr_hours': 24.0  # 24-hour target
    })

@api_bp.route('/reports/decision-queue', methods=['GET'])
def get_decision_queue():
    """Get current decision queue items requiring action"""
    
    # Get pending recommendations that need approval
    pending_recommendations = Recommendation.query.filter(
        Recommendation.status == 'pending'
    ).order_by(desc(Recommendation.created_at)).all()
    
    # Get high-risk shipments that may need attention
    high_risk_shipments = Shipment.query.filter(
        Shipment.risk_score >= 0.75,
        Shipment.status.in_(['planned', 'in_transit'])
    ).order_by(desc(Shipment.risk_score)).limit(10).all()
    
    # Get active high-severity alerts
    critical_alerts = Alert.query.filter(
        Alert.status == 'active',
        Alert.severity.in_(['high', 'critical'])
    ).order_by(desc(Alert.created_at)).limit(5).all()
    
    decision_items = []
    
    # Add pending recommendations
    for rec in pending_recommendations:
        decision_items.append({
            'id': f"rec_{rec.id}",
            'type': 'recommendation_approval',
            'title': rec.title,
            'description': rec.description,
            'severity': rec.severity or 'medium',
            'created_at': rec.created_at.isoformat(),
            'requires_approval': True,
            'created_by': rec.created_by or 'AI Agent',
            'metadata': {
                'recommendation_id': rec.id,
                'recommendation_type': rec.type
            }
        })
    
    # Add high-risk shipments
    for shipment in high_risk_shipments:
        decision_items.append({
            'id': f"ship_{shipment.id}",
            'type': 'high_risk_shipment',
            'title': f"High Risk Shipment: {shipment.reference_number}",
            'description': f"Shipment from {shipment.origin_port} to {shipment.destination_port} has elevated risk score",
            'severity': 'high' if shipment.risk_score >= 0.85 else 'medium',
            'created_at': shipment.created_at.isoformat(),
            'requires_approval': False,
            'created_by': 'Risk Predictor',
            'metadata': {
                'shipment_id': shipment.id,
                'risk_score': shipment.risk_score,
                'carrier': shipment.carrier
            }
        })
    
    # Add critical alerts
    for alert in critical_alerts:
        decision_items.append({
            'id': f"alert_{alert.id}",
            'type': 'critical_alert',
            'title': alert.title,
            'description': alert.description or 'Critical alert requiring attention',
            'severity': alert.severity.value if hasattr(alert.severity, 'value') else str(alert.severity),
            'created_at': alert.created_at.isoformat(),
            'requires_approval': False,
            'created_by': 'Alert System',
            'metadata': {
                'alert_id': alert.id,
                'alert_type': alert.type,
                'location': alert.location
            }
        })
    
    # Sort by severity and date
    severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    decision_items.sort(
        key=lambda x: (severity_order.get(x['severity'], 3), x['created_at']),
        reverse=True
    )
    
    return jsonify({
        'queue_length': len(decision_items),
        'items': decision_items[:20],  # Limit to top 20 items
        'summary': {
            'pending_approvals': len([item for item in decision_items if item['requires_approval']]),
            'high_risk_items': len([item for item in decision_items if item['severity'] in ['high', 'critical']]),
            'total_items': len(decision_items)
        },
        'last_updated': datetime.utcnow().isoformat()
    })

@api_bp.route('/reports/decisions/<decision_id>/approve', methods=['POST'])
def approve_decision(decision_id):
    """Approve a decision queue item"""
    
    if decision_id.startswith('rec_'):
        # Approve recommendation
        rec_id = int(decision_id.split('_')[1])
        recommendation = db.session.get(Recommendation, rec_id)
        if not recommendation:
            return jsonify({'error': 'Recommendation not found'}), 404
        
        recommendation.status = 'approved'
        
        # Create/update decision record
        decision = DecisionItem(
            workspace_id=recommendation.workspace_id,
            decision_type='recommendation_approval',
            title=f'Approve recommendation {recommendation.id}',
            description=f'Manual approval of recommendation',
            status='approved',
            requires_approval=False,
            related_object_type='recommendation',
            related_object_id=recommendation.id,
            decision_made_at=datetime.utcnow(),
            decision_rationale=request.json.get('comments') if request.json else 'Manual approval'
        )
        db.session.add(decision)
        
        db.session.commit()
        
        return jsonify({
            'status': 'approved',
            'decision_id': decision_id,
            'recommendation_id': rec_id
        })
    
    else:
        return jsonify({'error': 'Decision type not supported for approval'}), 400

@api_bp.route('/reports/decisions/<decision_id>/defer', methods=['POST'])
def defer_decision(decision_id):
    """Defer a decision queue item for later review"""
    
    # For Phase 1, just return success
    # In Phase 2, this would update the item's priority/defer timestamp
    
    return jsonify({
        'status': 'deferred',
        'decision_id': decision_id,
        'deferred_until': (datetime.utcnow() + timedelta(hours=24)).isoformat()
    })

@api_bp.route('/reports/export', methods=['GET'])
def export_reports():
    """Export reports in various formats"""
    format_type = request.args.get('format', 'json')
    report_type = request.args.get('type', 'kpis')
    
    if format_type not in ['json', 'csv', 'pdf']:
        return jsonify({'error': 'Unsupported format'}), 400
    
    if report_type == 'kpis':
        # Get KPI data
        kpis = get_reports_kpis().get_json()
        
        if format_type == 'json':
            return jsonify(kpis)
        elif format_type == 'csv':
            # For Phase 1, return a simple CSV-like structure
            csv_data = "metric,value\n"
            for key, value in kpis['kpis'].items():
                csv_data += f"{key},{value}\n"
            
            from flask import Response
            return Response(
                csv_data,
                mimetype='text/csv',
                headers={'Content-Disposition': 'attachment; filename=kpis_export.csv'}
            )
        elif format_type == 'pdf':
            # For Phase 1, return JSON with a note about PDF generation
            return jsonify({
                'message': 'PDF export will be implemented in Phase 3',
                'data': kpis,
                'suggested_format': 'csv'
            })
    
    elif report_type == 'executive':
        # Executive summary
        summary = {
            'report_type': 'executive_summary',
            'generated_at': datetime.utcnow().isoformat(),
            'kpis': get_reports_kpis().get_json()['kpis'],
            'decision_queue': get_decision_queue().get_json()['summary']
        }
        
        return jsonify(summary)
    
    else:
        return jsonify({'error': 'Unsupported report type'}), 400


# Phase 2 Enhancements: Dashboard and Executive Report Endpoints

@api_bp.route('/reports/dashboard', methods=['GET'])
def get_dashboard_report():
    """Get comprehensive dashboard report combining analytics and approvals"""
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        
        # Get KPI trends from analytics engine
        from app.analytics.kpi_collector import KPICollector
        collector = KPICollector(workspace_id)
        kpi_trends = collector.get_kpi_trends(30)  # Last 30 days
        
        # Get recent KPI snapshots
        recent_snapshots = db.session.query(KPISnapshot).filter(
            KPISnapshot.workspace_id == workspace_id,
            KPISnapshot.period_start >= datetime.utcnow() - timedelta(days=7)
        ).order_by(KPISnapshot.period_start.desc()).limit(10).all()
        
        # Get approval metrics using DecisionItem model
        pending_approvals = db.session.query(DecisionItem).filter(
            DecisionItem.workspace_id == workspace_id,
            DecisionItem.status == 'pending',
            DecisionItem.requires_approval == True
        ).count()
        
        resolved_today = db.session.query(DecisionItem).filter(
            DecisionItem.workspace_id == workspace_id,
            DecisionItem.status.in_(['approved', 'rejected']),
            DecisionItem.updated_at >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        ).count()
        
        # Get policy activity
        active_policies = db.session.query(PolicyTrigger).filter(
            PolicyTrigger.workspace_id == workspace_id,
            PolicyTrigger.is_active == True
        ).count()
        
        triggered_today = db.session.query(PolicyTrigger).filter(
            PolicyTrigger.workspace_id == workspace_id,
            PolicyTrigger.last_triggered >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        ).count()
        
        # Compile dashboard data
        dashboard_data = {
            'success': True,
            'workspace_id': workspace_id,
            'generated_at': datetime.utcnow().isoformat(),
            'kpi_trends': kpi_trends,
            'recent_snapshots': [
                {
                    'date': s.period_start.isoformat(),
                    'type': s.period_type,
                    'total_shipments': s.total_shipments,
                    'on_time_deliveries': s.on_time_deliveries,
                    'avg_risk_score': float(s.avg_risk_score),
                    'cost_savings_usd': float(s.cost_savings_usd)
                } for s in recent_snapshots
            ],
            'approval_metrics': {
                'pending_count': pending_approvals,
                'resolved_today': resolved_today,
                'pending_approvals': pending_approvals
            },
            'policy_activities': {
                'active_policies': active_policies,
                'triggered_today': triggered_today,
                'policy_triggers': triggered_today
            }
        }
        
        return jsonify(dashboard_data)
        
    except Exception as e:
        current_app.logger.error(f"Error generating dashboard report: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/reports/executive', methods=['GET'])
def get_executive_report():
    """Get executive-level summary report"""
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        period_days = request.args.get('period_days', 30, type=int)
        
        since_date = datetime.utcnow() - timedelta(days=period_days)
        
        # Get executive KPI summary
        from app.analytics.kpi_collector import KPICollector
        collector = KPICollector(workspace_id)
        
        # Get aggregated metrics for the period
        period_snapshots = db.session.query(KPISnapshot).filter(
            KPISnapshot.workspace_id == workspace_id,
            KPISnapshot.period_start >= since_date
        ).all()
        
        if period_snapshots:
            total_shipments = sum(s.total_shipments for s in period_snapshots)
            total_on_time = sum(s.on_time_deliveries for s in period_snapshots)
            total_savings = sum(s.cost_savings_usd for s in period_snapshots)
            avg_risk = sum(s.avg_risk_score for s in period_snapshots) / len(period_snapshots)
            
            on_time_rate = (total_on_time / total_shipments * 100) if total_shipments > 0 else 0
        else:
            total_shipments = total_on_time = total_savings = avg_risk = on_time_rate = 0
        
        # Get approval performance using DecisionItem model
        total_approvals = db.session.query(DecisionItem).filter(
            DecisionItem.workspace_id == workspace_id,
            DecisionItem.created_at >= since_date,
            DecisionItem.requires_approval == True
        ).count()
        
        resolved_approvals = db.session.query(DecisionItem).filter(
            DecisionItem.workspace_id == workspace_id,
            DecisionItem.created_at >= since_date,
            DecisionItem.status.in_(['approved', 'rejected'])
        ).all()
        
        approval_rate = (len(resolved_approvals) / total_approvals * 100) if total_approvals > 0 else 0
        
        # Calculate average resolution time
        avg_resolution_hours = 0
        if resolved_approvals:
            total_hours = sum(
                (a.decision_made_at - a.created_at).total_seconds() / 3600
                for a in resolved_approvals 
                if a.decision_made_at and a.created_at
            )
            avg_resolution_hours = total_hours / len(resolved_approvals)
        
        executive_summary = {
            'success': True,
            'workspace_id': workspace_id,
            'period_days': period_days,
            'generated_at': datetime.utcnow().isoformat(),
            'operational_performance': {
                'total_shipments': total_shipments,
                'on_time_delivery_rate': round(on_time_rate, 2),
                'average_risk_score': round(avg_risk, 2),
                'total_cost_savings_usd': float(total_savings)
            },
            'decision_management': {
                'total_approvals': total_approvals,
                'approval_resolution_rate': round(approval_rate, 2),
                'avg_resolution_time_hours': round(avg_resolution_hours, 2),
                'pending_approvals': total_approvals - len(resolved_approvals)
            },
            'automation_impact': {
                'active_policies': db.session.query(PolicyTrigger).filter(
                    PolicyTrigger.workspace_id == workspace_id,
                    PolicyTrigger.is_active == True
                ).count(),
                'policy_triggers': db.session.query(PolicyTrigger).filter(
                    PolicyTrigger.workspace_id == workspace_id,
                    PolicyTrigger.last_triggered >= since_date
                ).count()
            }
        }
        
        return jsonify(executive_summary)
        
    except Exception as e:
        current_app.logger.error(f"Error generating executive report: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/reports/operational', methods=['GET'])
def get_operational_report():
    """Get detailed operational report for managers"""
    try:
        workspace_id = request.args.get('workspace_id', 1, type=int)
        period_days = request.args.get('period_days', 7, type=int)
        
        since_date = datetime.utcnow() - timedelta(days=period_days)
        
        # Get detailed operational metrics
        from app.analytics.kpi_collector import KPICollector
        collector = KPICollector(workspace_id)
        
        # Get recent snapshots with detailed breakdown
        recent_snapshots = db.session.query(KPISnapshot).filter(
            KPISnapshot.workspace_id == workspace_id,
            KPISnapshot.period_start >= since_date
        ).order_by(KPISnapshot.period_start.desc()).all()
        
        # Get active shipments and their status
        active_shipments = db.session.query(Shipment).filter(
            Shipment.workspace_id == workspace_id,
            Shipment.status.in_([ShipmentStatus.IN_TRANSIT, ShipmentStatus.PLANNED, ShipmentStatus.BOOKED])
        ).all()
        
        # Get recent recommendations
        recent_recommendations = db.session.query(Recommendation).filter(
            Recommendation.workspace_id == workspace_id,
            Recommendation.created_at >= since_date
        ).order_by(Recommendation.created_at.desc()).limit(10).all()
        
        # Get approval queue status using DecisionItem model
        approval_queue = db.session.query(DecisionItem).filter(
            DecisionItem.workspace_id == workspace_id,
            DecisionItem.status == 'pending',
            DecisionItem.requires_approval == True
        ).order_by(DecisionItem.created_at.asc()).all()
        
        # Compile operational data
        operational_data = {
            'success': True,
            'workspace_id': workspace_id,
            'period_days': period_days,
            'generated_at': datetime.utcnow().isoformat(),
            'daily_snapshots': [
                {
                    'date': s.period_start.isoformat(),
                    'type': s.period_type,
                    'shipments': s.total_shipments,
                    'on_time': s.on_time_deliveries,
                    'delayed': s.delayed_shipments,
                    'risk_score': float(s.avg_risk_score),
                    'cost_savings': float(s.cost_savings_usd),
                    'approvals': s.approval_requests,
                    'auto_approved': s.auto_approved
                } for s in recent_snapshots
            ],
            'active_shipments': {
                'total': len(active_shipments),
                'in_transit': len([s for s in active_shipments if s.status == ShipmentStatus.IN_TRANSIT]),
                'planned': len([s for s in active_shipments if s.status == ShipmentStatus.PLANNED]),
                'high_risk': len([s for s in active_shipments if s.risk_score and s.risk_score > 0.7])
            },
            'recent_recommendations': [
                {
                    'id': r.id,
                    'type': r.recommendation_type.value if r.recommendation_type else 'unknown',
                    'title': r.title,
                    'confidence': r.confidence_score,
                    'created_at': r.created_at.isoformat(),
                    'status': r.status.value if r.status else 'pending'
                } for r in recent_recommendations
            ],
            'approval_queue': {
                'total_pending': len(approval_queue),
                'urgent': len([a for a in approval_queue if a.priority and a.priority.value == 'HIGH']),
                'overdue': len([a for a in approval_queue if a.due_date and a.due_date < datetime.utcnow()]),
                'queue_items': [
                    {
                        'id': a.id,
                        'type': a.item_type,
                        'priority': a.priority.value if a.priority else 'medium',
                        'age_hours': (datetime.utcnow() - a.created_at).total_seconds() / 3600,
                        'due_date': a.due_date.isoformat() if a.due_date else None
                    } for a in approval_queue[:5]  # Top 5 items
                ]
            }
        }
        
        return jsonify(operational_data)
        
    except Exception as e:
        current_app.logger.error(f"Error generating operational report: {e}")
        return jsonify({'error': str(e)}), 500
