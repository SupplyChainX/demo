"""
Real-Time Metrics Calculator
Enhanced utilities for calculating live KPIs and metrics with WebSocket broadcasting

Phase 5: Analytics Engine - Real-Time Metrics
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
    Shipment, PurchaseOrder, Supplier, Alert, 
    DecisionItem, PolicyTrigger, Recommendation,
    KPISnapshot
)

logger = logging.getLogger(__name__)

@dataclass
class RealTimeMetric:
    """Real-time metric data point"""
    name: str
    value: float
    unit: str
    timestamp: datetime
    trend: str  # 'up', 'down', 'stable'
    change_percent: float
    status: str  # 'good', 'warning', 'critical'
    metadata: Dict[str, Any]

class MetricsCalculator:
    """
    Real-time metrics calculator with WebSocket broadcasting capabilities
    """
    
    def __init__(self, workspace_id: int = 1):
        self.workspace_id = workspace_id
        
    def calculate_real_time_otd(self) -> RealTimeMetric:
        """
        Calculate real-time on-time delivery rate
        
        Returns:
            RealTimeMetric with current OTD performance
        """
        now = datetime.utcnow()
        last_7_days = now - timedelta(days=7)
        last_14_days = now - timedelta(days=14)
        
        # Current period (last 7 days)
        current_deliveries = db.session.query(Shipment).filter(
            and_(
                Shipment.workspace_id == self.workspace_id,
                Shipment.status == 'delivered',
                Shipment.actual_arrival >= last_7_days,
                Shipment.actual_arrival.isnot(None),
                Shipment.scheduled_arrival.isnot(None)
            )
        ).all()
        
        # Previous period (7-14 days ago)
        previous_deliveries = db.session.query(Shipment).filter(
            and_(
                Shipment.workspace_id == self.workspace_id,
                Shipment.status == 'delivered',
                Shipment.actual_arrival >= last_14_days,
                Shipment.actual_arrival < last_7_days,
                Shipment.actual_arrival.isnot(None),
                Shipment.scheduled_arrival.isnot(None)
            )
        ).all()
        
        # Calculate current OTD
        if current_deliveries:
            on_time_current = sum(1 for s in current_deliveries 
                                if s.actual_arrival <= s.scheduled_arrival)
            current_otd = (on_time_current / len(current_deliveries)) * 100
        else:
            current_otd = 0.0
        
        # Calculate previous OTD for trend
        if previous_deliveries:
            on_time_previous = sum(1 for s in previous_deliveries 
                                 if s.actual_arrival <= s.scheduled_arrival)
            previous_otd = (on_time_previous / len(previous_deliveries)) * 100
        else:
            previous_otd = current_otd
        
        # Calculate trend
        if previous_otd > 0:
            change_percent = ((current_otd - previous_otd) / previous_otd) * 100
        else:
            change_percent = 0
        
        if change_percent > 2:
            trend = 'up'
        elif change_percent < -2:
            trend = 'down'
        else:
            trend = 'stable'
        
        # Determine status
        if current_otd >= 95:
            status = 'good'
        elif current_otd >= 85:
            status = 'warning'
        else:
            status = 'critical'
        
        return RealTimeMetric(
            name='on_time_delivery_rate',
            value=round(current_otd, 1),
            unit='%',
            timestamp=now,
            trend=trend,
            change_percent=round(change_percent, 1),
            status=status,
            metadata={
                'current_deliveries': len(current_deliveries),
                'on_time_count': sum(1 for s in current_deliveries 
                                   if s.actual_arrival <= s.scheduled_arrival),
                'period': 'last_7_days'
            }
        )
    
    def track_cost_avoidance(self) -> RealTimeMetric:
        """
        Track real-time cost avoidance through optimization
        
        Returns:
            RealTimeMetric with cost avoidance data
        """
        now = datetime.utcnow()
        last_30_days = now - timedelta(days=30)
        
        # Get approved optimization recommendations
        cost_saving_recs = db.session.query(Recommendation).filter(
            and_(
                Recommendation.workspace_id == self.workspace_id,
                Recommendation.status == 'APPROVED',
                Recommendation.created_at >= last_30_days,
                Recommendation.type.in_(['reroute', 'carrier_switch', 'consolidation'])
            )
        ).all()
        
        total_savings = 0
        savings_count = 0
        
        for rec in cost_saving_recs:
            if rec.impact_assessment and isinstance(rec.impact_assessment, dict):
                savings = rec.impact_assessment.get('cost_savings_usd', 0)
                if isinstance(savings, (int, float)) and savings > 0:
                    total_savings += savings
                    savings_count += 1
        
        # Calculate trend based on recent vs older savings
        last_15_days = now - timedelta(days=15)
        
        recent_recs = [r for r in cost_saving_recs if r.created_at >= last_15_days]
        older_recs = [r for r in cost_saving_recs if r.created_at < last_15_days]
        
        recent_savings = sum(
            r.impact_assessment.get('cost_savings_usd', 0) 
            for r in recent_recs 
            if r.impact_assessment and isinstance(r.impact_assessment, dict)
        )
        
        older_savings = sum(
            r.impact_assessment.get('cost_savings_usd', 0) 
            for r in older_recs 
            if r.impact_assessment and isinstance(r.impact_assessment, dict)
        )
        
        # Calculate change
        if older_savings > 0:
            change_percent = ((recent_savings - older_savings) / older_savings) * 100
        else:
            change_percent = 100 if recent_savings > 0 else 0
        
        trend = 'up' if change_percent > 10 else 'down' if change_percent < -10 else 'stable'
        
        # Status based on monthly savings target (example: $50k)
        monthly_target = 50000
        status = 'good' if total_savings >= monthly_target else 'warning' if total_savings >= monthly_target * 0.7 else 'critical'
        
        return RealTimeMetric(
            name='cost_avoidance_usd',
            value=round(total_savings, 0),
            unit='USD',
            timestamp=now,
            trend=trend,
            change_percent=round(change_percent, 1),
            status=status,
            metadata={
                'recommendations_count': savings_count,
                'recent_savings': round(recent_savings, 0),
                'period': 'last_30_days',
                'target': monthly_target
            }
        )
    
    def measure_mttr_metrics(self) -> RealTimeMetric:
        """
        Measure Mean Time To Resolution for alerts
        
        Returns:
            RealTimeMetric with MTTR data
        """
        now = datetime.utcnow()
        last_30_days = now - timedelta(days=30)
        
        # Get resolved alerts from last 30 days
        resolved_alerts = db.session.query(Alert).filter(
            and_(
                Alert.workspace_id == self.workspace_id,
                Alert.status == 'resolved',
                Alert.resolved_at >= last_30_days,
                Alert.resolved_at.isnot(None),
                Alert.created_at.isnot(None)
            )
        ).all()
        
        if not resolved_alerts:
            return RealTimeMetric(
                name='alert_mttr_hours',
                value=0.0,
                unit='hours',
                timestamp=now,
                trend='stable',
                change_percent=0,
                status='good',
                metadata={'alerts_count': 0, 'period': 'last_30_days'}
            )
        
        # Calculate resolution times
        resolution_times = []
        for alert in resolved_alerts:
            resolution_time = alert.resolved_at - alert.created_at
            hours = resolution_time.total_seconds() / 3600
            resolution_times.append(hours)
        
        current_mttr = statistics.mean(resolution_times)
        
        # Calculate trend (compare first half vs second half of period)
        mid_point = last_30_days + timedelta(days=15)
        
        recent_alerts = [a for a in resolved_alerts if a.resolved_at >= mid_point]
        older_alerts = [a for a in resolved_alerts if a.resolved_at < mid_point]
        
        if recent_alerts and older_alerts:
            recent_times = [(a.resolved_at - a.created_at).total_seconds() / 3600 for a in recent_alerts]
            older_times = [(a.resolved_at - a.created_at).total_seconds() / 3600 for a in older_alerts]
            
            recent_mttr = statistics.mean(recent_times)
            older_mttr = statistics.mean(older_times)
            
            change_percent = ((recent_mttr - older_mttr) / older_mttr) * 100 if older_mttr > 0 else 0
        else:
            change_percent = 0
        
        # For MTTR, down is good (faster resolution)
        if change_percent < -10:
            trend = 'up'  # Improving (faster resolution)
        elif change_percent > 10:
            trend = 'down'  # Degrading (slower resolution)
        else:
            trend = 'stable'
        
        # Status based on target MTTR (example: 4 hours)
        target_mttr = 4.0
        if current_mttr <= target_mttr:
            status = 'good'
        elif current_mttr <= target_mttr * 1.5:
            status = 'warning'
        else:
            status = 'critical'
        
        return RealTimeMetric(
            name='alert_mttr_hours',
            value=round(current_mttr, 1),
            unit='hours',
            timestamp=now,
            trend=trend,
            change_percent=round(abs(change_percent), 1),  # Show absolute change for clarity
            status=status,
            metadata={
                'alerts_count': len(resolved_alerts),
                'fastest_resolution': round(min(resolution_times), 1) if resolution_times else 0,
                'slowest_resolution': round(max(resolution_times), 1) if resolution_times else 0,
                'target_mttr': target_mttr,
                'period': 'last_30_days'
            }
        )
    
    def calculate_emissions_data(self) -> RealTimeMetric:
        """
        Calculate real-time emissions per shipment
        
        Returns:
            RealTimeMetric with emissions data
        """
        now = datetime.utcnow()
        last_30_days = now - timedelta(days=30)
        
        # Get recent shipments
        recent_shipments = db.session.query(Shipment).filter(
            and_(
                Shipment.workspace_id == self.workspace_id,
                Shipment.created_at >= last_30_days,
                Shipment.total_distance_km.isnot(None),
                Shipment.total_distance_km > 0
            )
        ).all()
        
        if not recent_shipments:
            return RealTimeMetric(
                name='emissions_per_shipment_kg',
                value=0.0,
                unit='kg CO2',
                timestamp=now,
                trend='stable',
                change_percent=0,
                status='good',
                metadata={'shipments_count': 0, 'period': 'last_30_days'}
            )
        
        # Calculate emissions per shipment
        total_emissions = 0
        shipment_count = 0
        
        for shipment in recent_shipments:
            # Use estimated emissions if available, otherwise calculate
            if hasattr(shipment, 'estimated_emissions_kg') and shipment.estimated_emissions_kg:
                emissions = shipment.estimated_emissions_kg
            else:
                # Emission factors by transport mode (kg CO2 per km)
                emission_factors = {
                    'air': 1.5,
                    'road': 0.8,
                    'rail': 0.3,
                    'ocean': 0.1,
                    'multimodal': 0.6  # Average
                }
                
                mode = getattr(shipment, 'transport_mode', 'multimodal')
                factor = emission_factors.get(mode.lower(), 0.6)
                emissions = shipment.total_distance_km * factor
            
            total_emissions += emissions
            shipment_count += 1
        
        current_emissions_per_shipment = total_emissions / shipment_count if shipment_count > 0 else 0
        
        # Calculate trend (compare first half vs second half)
        mid_point = last_30_days + timedelta(days=15)
        
        recent_shipments_subset = [s for s in recent_shipments if s.created_at >= mid_point]
        older_shipments_subset = [s for s in recent_shipments if s.created_at < mid_point]
        
        # Calculate change
        if recent_shipments_subset and older_shipments_subset:
            recent_emissions = sum(
                getattr(s, 'estimated_emissions_kg', s.total_distance_km * 0.6) 
                for s in recent_shipments_subset
            )
            older_emissions = sum(
                getattr(s, 'estimated_emissions_kg', s.total_distance_km * 0.6) 
                for s in older_shipments_subset
            )
            
            recent_avg = recent_emissions / len(recent_shipments_subset)
            older_avg = older_emissions / len(older_shipments_subset)
            
            change_percent = ((recent_avg - older_avg) / older_avg) * 100 if older_avg > 0 else 0
        else:
            change_percent = 0
        
        # For emissions, down is good (lower environmental impact)
        if change_percent < -5:
            trend = 'up'  # Improving (lower emissions)
        elif change_percent > 5:
            trend = 'down'  # Degrading (higher emissions)
        else:
            trend = 'stable'
        
        # Status based on target emissions (example: 50 kg CO2 per shipment)
        target_emissions = 50.0
        if current_emissions_per_shipment <= target_emissions:
            status = 'good'
        elif current_emissions_per_shipment <= target_emissions * 1.3:
            status = 'warning'
        else:
            status = 'critical'
        
        return RealTimeMetric(
            name='emissions_per_shipment_kg',
            value=round(current_emissions_per_shipment, 1),
            unit='kg CO2',
            timestamp=now,
            trend=trend,
            change_percent=round(abs(change_percent), 1),
            status=status,
            metadata={
                'shipments_count': shipment_count,
                'total_emissions': round(total_emissions, 1),
                'target_emissions': target_emissions,
                'period': 'last_30_days'
            }
        )
    
    def calculate_risk_score_trend(self) -> RealTimeMetric:
        """
        Calculate trending risk score across active shipments
        
        Returns:
            RealTimeMetric with risk trend data
        """
        now = datetime.utcnow()
        
        # Get currently active shipments
        active_shipments = db.session.query(Shipment).filter(
            and_(
                Shipment.workspace_id == self.workspace_id,
                Shipment.status.in_(['planned', 'booked', 'in_transit']),
                Shipment.risk_score.isnot(None)
            )
        ).all()
        
        if not active_shipments:
            return RealTimeMetric(
                name='average_risk_score',
                value=0.0,
                unit='score',
                timestamp=now,
                trend='stable',
                change_percent=0,
                status='good',
                metadata={'active_shipments': 0}
            )
        
        # Calculate current average risk
        risk_scores = [s.risk_score for s in active_shipments if s.risk_score is not None]
        current_avg_risk = statistics.mean(risk_scores) if risk_scores else 0
        
        # Get historical risk data for comparison
        last_7_days = now - timedelta(days=7)
        historical_snapshots = db.session.query(KPISnapshot).filter(
            and_(
                KPISnapshot.workspace_id == self.workspace_id,
                KPISnapshot.metric_name == 'average_risk_score',
                KPISnapshot.period_start >= last_7_days
            )
        ).order_by(desc(KPISnapshot.period_start)).limit(7).all()
        
        # Calculate trend
        if len(historical_snapshots) >= 2:
            recent_avg = statistics.mean([s.value for s in historical_snapshots[:3]])
            older_avg = statistics.mean([s.value for s in historical_snapshots[-3:]])
            
            change_percent = ((current_avg_risk - older_avg) / older_avg) * 100 if older_avg > 0 else 0
        else:
            change_percent = 0
        
        # For risk, down is good (lower risk)
        if change_percent < -5:
            trend = 'up'  # Improving (lower risk)
        elif change_percent > 5:
            trend = 'down'  # Degrading (higher risk)
        else:
            trend = 'stable'
        
        # Status based on risk thresholds
        if current_avg_risk <= 3.0:
            status = 'good'
        elif current_avg_risk <= 6.0:
            status = 'warning'
        else:
            status = 'critical'
        
        # Risk distribution
        low_risk = len([s for s in active_shipments if s.risk_score <= 3.0])
        medium_risk = len([s for s in active_shipments if 3.0 < s.risk_score <= 6.0])
        high_risk = len([s for s in active_shipments if s.risk_score > 6.0])
        
        return RealTimeMetric(
            name='average_risk_score',
            value=round(current_avg_risk, 1),
            unit='score',
            timestamp=now,
            trend=trend,
            change_percent=round(abs(change_percent), 1),
            status=status,
            metadata={
                'active_shipments': len(active_shipments),
                'low_risk_count': low_risk,
                'medium_risk_count': medium_risk,
                'high_risk_count': high_risk,
                'highest_risk': round(max(risk_scores), 1) if risk_scores else 0
            }
        )
    
    def get_all_real_time_metrics(self) -> Dict[str, RealTimeMetric]:
        """
        Get all real-time metrics at once
        
        Returns:
            Dictionary of all calculated metrics
        """
        try:
            metrics = {}
            
            # Calculate all metrics
            metrics['on_time_delivery'] = self.calculate_real_time_otd()
            metrics['cost_avoidance'] = self.track_cost_avoidance()
            metrics['alert_mttr'] = self.measure_mttr_metrics()
            metrics['emissions'] = self.calculate_emissions_data()
            metrics['risk_score'] = self.calculate_risk_score_trend()
            
            logger.info(f"Calculated {len(metrics)} real-time metrics")
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating real-time metrics: {e}")
            return {}
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all metrics for dashboard display
        
        Returns:
            Summary data suitable for dashboard widgets
        """
        metrics = self.get_all_real_time_metrics()
        
        summary = {
            'timestamp': datetime.utcnow().isoformat(),
            'metrics_count': len(metrics),
            'overall_health': 'good',  # Will be calculated based on individual statuses
            'metrics': {}
        }
        
        status_weights = {'good': 3, 'warning': 2, 'critical': 1}
        total_weight = 0
        status_count = 0
        
        for key, metric in metrics.items():
            summary['metrics'][key] = {
                'value': metric.value,
                'unit': metric.unit,
                'trend': metric.trend,
                'change_percent': metric.change_percent,
                'status': metric.status,
                'metadata': metric.metadata
            }
            
            # Calculate overall health
            total_weight += status_weights.get(metric.status, 1)
            status_count += 1
        
        # Determine overall health
        if status_count > 0:
            avg_weight = total_weight / status_count
            if avg_weight >= 2.5:
                summary['overall_health'] = 'good'
            elif avg_weight >= 1.5:
                summary['overall_health'] = 'warning'
            else:
                summary['overall_health'] = 'critical'
        
        return summary

# Convenience functions for quick metric access
def calculate_real_time_otd(workspace_id: int = 1) -> RealTimeMetric:
    """Quick access to real-time OTD calculation"""
    calculator = MetricsCalculator(workspace_id)
    return calculator.calculate_real_time_otd()

def track_cost_avoidance(workspace_id: int = 1) -> RealTimeMetric:
    """Quick access to cost avoidance tracking"""
    calculator = MetricsCalculator(workspace_id)
    return calculator.track_cost_avoidance()

def measure_mttr_metrics(workspace_id: int = 1) -> RealTimeMetric:
    """Quick access to MTTR measurement"""
    calculator = MetricsCalculator(workspace_id)
    return calculator.measure_mttr_metrics()

def calculate_emissions_data(workspace_id: int = 1) -> RealTimeMetric:
    """Quick access to emissions calculation"""
    calculator = MetricsCalculator(workspace_id)
    return calculator.calculate_emissions_data()
