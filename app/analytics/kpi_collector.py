"""
KPI Collector - Advanced Historical KPI tracking and trending analytics engine
Enhanced for Phase 5: Real-Time Analytics Engine with WebSocket Broadcasting
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json
import statistics
from sqlalchemy import func, and_, or_, desc

from app import db
from app.models import (
    KPISnapshot, Shipment, PurchaseOrder, Supplier, Alert, 
    DecisionItem, PolicyTrigger, Recommendation
)

logger = logging.getLogger(__name__)

# Import WebSocket for real-time updates
try:
    from flask_socketio import emit
    from app.extensions import socketio
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    logger.warning("WebSocket not available - real-time updates disabled")

class KPIType(Enum):
    ON_TIME_DELIVERY = "on_time_delivery"
    COST_SAVINGS = "cost_savings"
    RISK_SCORE = "risk_score"
    ALERT_RESOLUTION = "alert_resolution"
    APPROVAL_CYCLE_TIME = "approval_cycle_time"
    SUPPLIER_PERFORMANCE = "supplier_performance"
    ROUTE_EFFICIENCY = "route_efficiency"
    BUDGET_VARIANCE = "budget_variance"

@dataclass
class KPIMetric:
    """Individual KPI measurement"""
    kpi_type: KPIType
    value: float
    timestamp: datetime
    period_type: str
    metadata: Dict[str, Any]
    unit: str
    target_value: Optional[float] = None
    threshold_warning: Optional[float] = None
    threshold_critical: Optional[float] = None

class KPICollector:
    """
    Collects and stores historical KPI snapshots for trending analysis.
    Provides real-time metrics calculation and historical data storage.
    Enhanced with WebSocket broadcasting for instant updates.
    """
    
    def __init__(self, workspace_id: int = 1, enable_realtime: bool = True):
        self.workspace_id = workspace_id
        self.enable_realtime = enable_realtime and WEBSOCKET_AVAILABLE
        
    def collect_daily_snapshots(self, target_date: Optional[datetime] = None, 
                              broadcast_update: bool = True) -> Dict[str, float]:
        """
        Collect daily KPI snapshots for the specified date.
        
        Args:
            target_date: Date to collect KPIs for (defaults to yesterday)
            broadcast_update: Whether to broadcast updates via WebSocket
            
        Returns:
            Dictionary of collected KPI values
        """
        if target_date is None:
            target_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        
        period_start = target_date
        period_end = period_start + timedelta(days=1)
        
        logger.info(f"Collecting daily KPI snapshots for {period_start.date()}")
        
        kpis = {}
        
        # 1. On-time delivery rate
        otd_rate = self._calculate_on_time_delivery_rate(period_start, period_end)
        kpis['on_time_delivery_rate'] = otd_rate
        self._store_kpi_snapshot(
            'on_time_delivery_rate', otd_rate, 'delivery',
            'daily', period_start, period_end, unit='%'
        )
        
        # 2. Cost avoided through optimization
        cost_avoided = self._calculate_cost_avoided(period_start, period_end)
        kpis['cost_avoided_usd'] = cost_avoided
        self._store_kpi_snapshot(
            'cost_avoided_usd', cost_avoided, 'cost',
            'daily', period_start, period_end, unit='USD'
        )
        
        # 3. Average risk score
        avg_risk = self._calculate_average_risk_score(period_start, period_end)
        kpis['average_risk_score'] = avg_risk
        self._store_kpi_snapshot(
            'average_risk_score', avg_risk, 'risk',
            'daily', period_start, period_end, unit='score'
        )
        
        # 4. Active alerts count
        active_alerts = self._calculate_active_alerts_count(period_end)
        kpis['active_alerts'] = active_alerts
        self._store_kpi_snapshot(
            'active_alerts', active_alerts, 'compliance',
            'daily', period_start, period_end, unit='count'
        )
        
        # 5. Pending approvals count
        pending_approvals = self._calculate_pending_approvals_count(period_end)
        kpis['pending_approvals'] = pending_approvals
        self._store_kpi_snapshot(
            'pending_approvals', pending_approvals, 'compliance',
            'daily', period_start, period_end, unit='count'
        )
        
        # 6. Total shipments processed
        total_shipments = self._calculate_total_shipments(period_start, period_end)
        kpis['total_shipments'] = total_shipments
        self._store_kpi_snapshot(
            'total_shipments', total_shipments, 'delivery',
            'daily', period_start, period_end, unit='count'
        )
        
        # 7. Mean Time to Resolution (MTTR) for alerts
        mttr_hours = self._calculate_alert_mttr(period_start, period_end)
        kpis['alert_mttr_hours'] = mttr_hours
        self._store_kpi_snapshot(
            'alert_mttr_hours', mttr_hours, 'compliance',
            'daily', period_start, period_end, unit='hours'
        )
        
        # 8. Carbon emissions per shipment
        emissions_per_shipment = self._calculate_emissions_per_shipment(period_start, period_end)
        kpis['emissions_per_shipment_kg'] = emissions_per_shipment
        self._store_kpi_snapshot(
            'emissions_per_shipment_kg', emissions_per_shipment, 'sustainability',
            'daily', period_start, period_end, unit='kg'
        )
        
        logger.info(f"Collected {len(kpis)} KPI snapshots for {period_start.date()}")
        
        # Broadcast real-time update if enabled
        if broadcast_update and self.enable_realtime:
            self._broadcast_kpi_update(kpis, period_start.date())
        
        return kpis
    
    def calculate_trending_metrics(self, metric_name: str, days: int = 30) -> Dict:
        """
        Calculate trending metrics for a specific KPI over the specified period.
        
        Args:
            metric_name: Name of the KPI metric
            days: Number of days to look back
            
        Returns:
            Dictionary with trending analysis
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        snapshots = db.session.query(KPISnapshot).filter(
            and_(
                KPISnapshot.workspace_id == self.workspace_id,
                KPISnapshot.metric_name == metric_name,
                KPISnapshot.period_type == 'daily',
                KPISnapshot.period_start >= start_date,
                KPISnapshot.period_start <= end_date
            )
        ).order_by(KPISnapshot.period_start).all()
        
        if not snapshots:
            return {'trend': 'no_data', 'change_percent': 0, 'data_points': 0}
        
        values = [s.value for s in snapshots]
        dates = [s.period_start for s in snapshots]
        
        # Calculate trend
        if len(values) < 2:
            trend = 'stable'
            change_percent = 0
        else:
            first_half = values[:len(values)//2]
            second_half = values[len(values)//2:]
            
            avg_first = sum(first_half) / len(first_half)
            avg_second = sum(second_half) / len(second_half)
            
            if avg_second > avg_first * 1.05:  # 5% increase threshold
                trend = 'improving'
            elif avg_second < avg_first * 0.95:  # 5% decrease threshold
                trend = 'declining'
            else:
                trend = 'stable'
                
            change_percent = ((avg_second - avg_first) / avg_first) * 100 if avg_first > 0 else 0
        
        # Data for charting
        chart_data = [{'date': d.isoformat(), 'value': v} for d, v in zip(dates, values)]
        
        return {
            'trend': trend,
            'change_percent': round(change_percent, 2),
            'data_points': len(values),
            'current_value': values[-1] if values else 0,
            'average_value': sum(values) / len(values) if values else 0,
            'min_value': min(values) if values else 0,
            'max_value': max(values) if values else 0,
            'chart_data': chart_data
        }
    
    def generate_comparative_analytics(self, metric_name: str, compare_type: str = 'yoy') -> Dict:
        """
        Generate comparative analytics (Year-over-Year, Month-over-Month, etc.)
        
        Args:
            metric_name: Name of the KPI metric
            compare_type: 'yoy' (year-over-year), 'mom' (month-over-month), 'wow' (week-over-week)
            
        Returns:
            Comparative analysis data
        """
        now = datetime.utcnow()
        
        if compare_type == 'yoy':
            current_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            previous_start = current_start.replace(year=current_start.year - 1)
            period_type = 'monthly'
        elif compare_type == 'mom':
            current_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if current_start.month == 1:
                previous_start = current_start.replace(year=current_start.year - 1, month=12)
            else:
                previous_start = current_start.replace(month=current_start.month - 1)
            period_type = 'daily'
        else:  # wow
            # Start of current week (Monday)
            days_since_monday = now.weekday()
            current_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
            previous_start = current_start - timedelta(weeks=1)
            period_type = 'daily'
        
        # Get current period data
        current_snapshots = db.session.query(KPISnapshot).filter(
            and_(
                KPISnapshot.workspace_id == self.workspace_id,
                KPISnapshot.metric_name == metric_name,
                KPISnapshot.period_type == period_type,
                KPISnapshot.period_start >= current_start
            )
        ).all()
        
        # Get previous period data
        previous_end = current_start
        previous_snapshots = db.session.query(KPISnapshot).filter(
            and_(
                KPISnapshot.workspace_id == self.workspace_id,
                KPISnapshot.metric_name == metric_name,
                KPISnapshot.period_type == period_type,
                KPISnapshot.period_start >= previous_start,
                KPISnapshot.period_start < previous_end
            )
        ).all()
        
        # Calculate averages
        current_avg = sum(s.value for s in current_snapshots) / len(current_snapshots) if current_snapshots else 0
        previous_avg = sum(s.value for s in previous_snapshots) / len(previous_snapshots) if previous_snapshots else 0
        
        # Calculate change
        if previous_avg > 0:
            change_percent = ((current_avg - previous_avg) / previous_avg) * 100
        else:
            change_percent = 0
        
        return {
            'comparison_type': compare_type,
            'current_period_avg': round(current_avg, 2),
            'previous_period_avg': round(previous_avg, 2),
            'change_percent': round(change_percent, 2),
            'change_direction': 'up' if change_percent > 0 else 'down' if change_percent < 0 else 'stable',
            'current_data_points': len(current_snapshots),
            'previous_data_points': len(previous_snapshots)
        }
    
    def store_historical_data(self, metric_name: str, value: float, category: str, 
                            period_type: str = 'daily', custom_timestamp: Optional[datetime] = None):
        """
        Store a historical KPI data point.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            category: Metric category
            period_type: Period type (daily, weekly, monthly, etc.)
            custom_timestamp: Custom timestamp (defaults to now)
        """
        if custom_timestamp is None:
            custom_timestamp = datetime.utcnow()
        
        # Calculate period boundaries based on type
        if period_type == 'daily':
            period_start = custom_timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            period_end = period_start + timedelta(days=1)
        elif period_type == 'weekly':
            days_since_monday = custom_timestamp.weekday()
            period_start = custom_timestamp.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
            period_end = period_start + timedelta(weeks=1)
        elif period_type == 'monthly':
            period_start = custom_timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if period_start.month == 12:
                period_end = period_start.replace(year=period_start.year + 1, month=1)
            else:
                period_end = period_start.replace(month=period_start.month + 1)
        else:
            period_start = custom_timestamp
            period_end = custom_timestamp
        
        self._store_kpi_snapshot(metric_name, value, category, period_type, period_start, period_end)
    
    def collect_real_time_metrics(self, broadcast_update: bool = True) -> Dict[str, Any]:
        """
        Collect real-time metrics and optionally broadcast updates
        
        Args:
            broadcast_update: Whether to broadcast updates via WebSocket
            
        Returns:
            Dictionary of real-time metrics
        """
        try:
            from app.utils.metrics import MetricsCalculator
            
            calculator = MetricsCalculator(self.workspace_id)
            metrics_summary = calculator.get_metrics_summary()
            
            # Broadcast real-time update if enabled
            if broadcast_update and self.enable_realtime:
                self._broadcast_realtime_metrics(metrics_summary)
            
            logger.info(f"Collected {metrics_summary['metrics_count']} real-time metrics")
            return metrics_summary
            
        except Exception as e:
            logger.error(f"Error collecting real-time metrics: {e}")
            return {'timestamp': datetime.utcnow().isoformat(), 'metrics_count': 0, 'metrics': {}}
    
    def get_live_dashboard_data(self) -> Dict[str, Any]:
        """
        Get comprehensive live dashboard data including historical and real-time metrics
        
        Returns:
            Complete dashboard data for live updates
        """
        dashboard_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'workspace_id': self.workspace_id,
            'real_time_metrics': {},
            'trending_data': {},
            'comparative_analytics': {},
            'alerts': []
        }
        
        try:
            # Get real-time metrics
            dashboard_data['real_time_metrics'] = self.collect_real_time_metrics(broadcast_update=False)
            
            # Get trending data for key metrics
            key_metrics = ['on_time_delivery_rate', 'cost_avoided_usd', 'average_risk_score', 'alert_mttr_hours']
            
            for metric in key_metrics:
                try:
                    trending = self.calculate_trending_metrics(metric, days=30)
                    dashboard_data['trending_data'][metric] = trending
                except Exception as e:
                    logger.warning(f"Could not calculate trending for {metric}: {e}")
                    dashboard_data['trending_data'][metric] = {'trend': 'no_data', 'change_percent': 0}
            
            # Get comparative analytics (month-over-month)
            for metric in key_metrics:
                try:
                    comparative = self.generate_comparative_analytics(metric, 'mom')
                    dashboard_data['comparative_analytics'][metric] = comparative
                except Exception as e:
                    logger.warning(f"Could not calculate comparative analytics for {metric}: {e}")
                    dashboard_data['comparative_analytics'][metric] = {'change_percent': 0}
            
            # Get active alerts for dashboard
            active_alerts = db.session.query(Alert).filter(
                and_(
                    Alert.workspace_id == self.workspace_id,
                    Alert.status == 'open'
                )
            ).order_by(desc(Alert.created_at)).limit(5).all()
            
            dashboard_data['alerts'] = [
                {
                    'id': alert.id,
                    'title': alert.title,
                    'severity': alert.severity.value if hasattr(alert.severity, 'value') else str(alert.severity),
                    'created_at': alert.created_at.isoformat(),
                    'type': alert.type
                }
                for alert in active_alerts
            ]
            
        except Exception as e:
            logger.error(f"Error generating live dashboard data: {e}")
        
        return dashboard_data
    
    def start_real_time_monitoring(self, interval_seconds: int = 30):
        """
        Start real-time monitoring with periodic updates
        
        Args:
            interval_seconds: Update interval in seconds
        """
        if not self.enable_realtime:
            logger.warning("Real-time monitoring not available - WebSocket disabled")
            return
        
        import threading
        import time
        
        def monitoring_loop():
            logger.info(f"Starting real-time KPI monitoring (interval: {interval_seconds}s)")
            
            while True:
                try:
                    # Collect and broadcast real-time metrics
                    self.collect_real_time_metrics(broadcast_update=True)
                    
                    # Sleep until next update
                    time.sleep(interval_seconds)
                    
                except Exception as e:
                    logger.error(f"Error in real-time monitoring loop: {e}")
                    time.sleep(interval_seconds)  # Continue despite errors
        
        # Start monitoring in background thread
        monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitor_thread.start()
        logger.info("Real-time KPI monitoring started")
    
    def _broadcast_kpi_update(self, kpis: Dict[str, float], date: Any):
        """Broadcast KPI updates via WebSocket"""
        if not self.enable_realtime:
            return
        
        try:
            update_data = {
                'type': 'kpi_update',
                'timestamp': datetime.utcnow().isoformat(),
                'date': str(date),
                'workspace_id': self.workspace_id,
                'kpis': kpis
            }
            
            socketio.emit('kpi_update', update_data, namespace='/')
            logger.debug(f"Broadcasted KPI update for {date}")
            
        except Exception as e:
            logger.error(f"Error broadcasting KPI update: {e}")
    
    def _broadcast_realtime_metrics(self, metrics_summary: Dict[str, Any]):
        """Broadcast real-time metrics via WebSocket"""
        if not self.enable_realtime:
            return
        
        try:
            update_data = {
                'type': 'realtime_metrics',
                'timestamp': datetime.utcnow().isoformat(),
                'workspace_id': self.workspace_id,
                'metrics': metrics_summary
            }
            
            socketio.emit('realtime_metrics', update_data, namespace='/')
            logger.debug("Broadcasted real-time metrics update")
            
        except Exception as e:
            logger.error(f"Error broadcasting real-time metrics: {e}")
    
    def _broadcast_dashboard_update(self, dashboard_data: Dict[str, Any]):
        """Broadcast complete dashboard updates via WebSocket"""
        if not self.enable_realtime:
            return
        
        try:
            update_data = {
                'type': 'dashboard_update',
                'timestamp': datetime.utcnow().isoformat(),
                'workspace_id': self.workspace_id,
                'data': dashboard_data
            }
            
            socketio.emit('dashboard_update', update_data, namespace='/')
            logger.debug("Broadcasted dashboard update")
            
        except Exception as e:
            logger.error(f"Error broadcasting dashboard update: {e}")
    
    # Private methods for KPI calculations
    
    def _calculate_on_time_delivery_rate(self, start_date: datetime, end_date: datetime) -> float:
        """Calculate on-time delivery rate for the period."""
        delivered_shipments = db.session.query(Shipment).filter(
            and_(
                Shipment.workspace_id == self.workspace_id,
                Shipment.status == 'delivered',
                Shipment.actual_arrival >= start_date,
                Shipment.actual_arrival < end_date
            )
        ).all()
        
        if not delivered_shipments:
            return 0.0
        
        on_time_count = 0
        for shipment in delivered_shipments:
            if shipment.scheduled_arrival and shipment.actual_arrival:
                if shipment.actual_arrival <= shipment.scheduled_arrival:
                    on_time_count += 1
        
        return (on_time_count / len(delivered_shipments)) * 100
    
    def _calculate_cost_avoided(self, start_date: datetime, end_date: datetime) -> float:
        """Calculate cost avoided through route optimization."""
        # Look for recommendations that resulted in cost savings
        cost_saving_recommendations = db.session.query(Recommendation).filter(
            and_(
                Recommendation.workspace_id == self.workspace_id,
                Recommendation.type == 'reroute',
                Recommendation.status == 'APPROVED',
                Recommendation.created_at >= start_date,
                Recommendation.created_at < end_date
            )
        ).all()
        
        total_savings = 0
        for rec in cost_saving_recommendations:
            if rec.impact_assessment and isinstance(rec.impact_assessment, dict):
                savings = rec.impact_assessment.get('cost_savings_usd', 0)
                if isinstance(savings, (int, float)):
                    total_savings += savings
        
        return total_savings
    
    def _calculate_average_risk_score(self, start_date: datetime, end_date: datetime) -> float:
        """Calculate average risk score for shipments."""
        active_shipments = db.session.query(Shipment).filter(
            and_(
                Shipment.workspace_id == self.workspace_id,
                Shipment.status.in_(['planned', 'in_transit']),
                or_(
                    Shipment.created_at >= start_date,
                    Shipment.updated_at >= start_date
                )
            )
        ).all()
        
        if not active_shipments:
            return 0.0
        
        total_risk = sum(s.risk_score or 0 for s in active_shipments)
        return total_risk / len(active_shipments)
    
    def _calculate_active_alerts_count(self, timestamp: datetime) -> int:
        """Calculate number of active alerts at given timestamp."""
        return db.session.query(Alert).filter(
            and_(
                Alert.workspace_id == self.workspace_id,
                Alert.status == 'open',
                Alert.created_at <= timestamp
            )
        ).count()
    
    def _calculate_pending_approvals_count(self, timestamp: datetime) -> int:
        """Calculate number of pending decision items at given timestamp."""
        return db.session.query(DecisionItem).filter(
            and_(
                DecisionItem.workspace_id == self.workspace_id,
                DecisionItem.status == 'pending',
                DecisionItem.created_at <= timestamp
            )
        ).count()
    
    def _calculate_total_shipments(self, start_date: datetime, end_date: datetime) -> int:
        """Calculate total shipments created in period."""
        return db.session.query(Shipment).filter(
            and_(
                Shipment.workspace_id == self.workspace_id,
                Shipment.created_at >= start_date,
                Shipment.created_at < end_date
            )
        ).count()
    
    def _calculate_alert_mttr(self, start_date: datetime, end_date: datetime) -> float:
        """Calculate mean time to resolution for alerts."""
        resolved_alerts = db.session.query(Alert).filter(
            and_(
                Alert.workspace_id == self.workspace_id,
                Alert.status == 'resolved',
                Alert.resolved_at >= start_date,
                Alert.resolved_at < end_date,
                Alert.resolved_at.isnot(None)
            )
        ).all()
        
        if not resolved_alerts:
            return 0.0
        
        total_resolution_time = 0
        for alert in resolved_alerts:
            if alert.resolved_at and alert.created_at:
                resolution_time = alert.resolved_at - alert.created_at
                total_resolution_time += resolution_time.total_seconds() / 3600  # Convert to hours
        
        return total_resolution_time / len(resolved_alerts)
    
    def _calculate_emissions_per_shipment(self, start_date: datetime, end_date: datetime) -> float:
        """Calculate average carbon emissions per shipment."""
        shipments_in_period = db.session.query(Shipment).filter(
            and_(
                Shipment.workspace_id == self.workspace_id,
                Shipment.created_at >= start_date,
                Shipment.created_at < end_date
            )
        ).all()
        
        if not shipments_in_period:
            return 0.0
        
        total_emissions = 0
        valid_shipments = 0
        
        for shipment in shipments_in_period:
            # Use estimated emissions based on distance and mode if available
            if hasattr(shipment, 'estimated_emissions_kg') and shipment.estimated_emissions_kg:
                total_emissions += shipment.estimated_emissions_kg
                valid_shipments += 1
            else:
                # Fallback estimation based on distance
                if shipment.total_distance_km:
                    # Rough estimate: 0.5 kg CO2 per km for mixed transport
                    estimated_emissions = shipment.total_distance_km * 0.5
                    total_emissions += estimated_emissions
                    valid_shipments += 1
        
        return total_emissions / valid_shipments if valid_shipments > 0 else 0.0
    
    def _store_kpi_snapshot(self, metric_name: str, value: float, category: str, 
                          period_type: str, period_start: datetime, period_end: datetime,
                          unit: str = None, confidence: float = 1.0, metadata: Dict = None):
        """Store a KPI snapshot in the database."""
        try:
            # Check if snapshot already exists for this period
            existing = db.session.query(KPISnapshot).filter(
                and_(
                    KPISnapshot.workspace_id == self.workspace_id,
                    KPISnapshot.metric_name == metric_name,
                    KPISnapshot.period_type == period_type,
                    KPISnapshot.period_start == period_start
                )
            ).first()
            
            if existing:
                # Update existing snapshot
                existing.value = value
                existing.unit = unit
                existing.confidence_level = confidence
                existing.metadata = metadata or {}
                existing.snapshot_timestamp = datetime.utcnow()
            else:
                # Create new snapshot
                snapshot = KPISnapshot(
                    workspace_id=self.workspace_id,
                    metric_name=metric_name,
                    metric_category=category,
                    value=value,
                    unit=unit,
                    period_type=period_type,
                    period_start=period_start,
                    period_end=period_end,
                    confidence_level=confidence,
                    metadata=metadata or {},
                    snapshot_timestamp=datetime.utcnow()
                )
                db.session.add(snapshot)
            
            db.session.commit()
            logger.debug(f"Stored KPI snapshot: {metric_name}={value} for {period_type} period {period_start}")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error storing KPI snapshot for {metric_name}: {e}")
            raise
