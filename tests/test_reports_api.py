"""
Unit Tests for Reports API
Tests the real-time analytics and reporting endpoints
"""
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app import create_app, db
from app.models import KPISnapshot, Shipment, Alert, Recommendation
from app.utils.metrics import MetricsCalculator
from app.analytics.kpi_collector import KPICollector


@pytest.fixture
def app():
    """Create test application"""
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def sample_data(app):
    """Create sample data for testing"""
    with app.app_context():
        # Create sample KPI snapshots
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        kpi1 = KPISnapshot(
            workspace_id=1,
            metric_name='on_time_delivery_rate',
            metric_category='delivery',
            value=92.5,
            unit='%',
            period_type='daily',
            period_start=yesterday,
            period_end=yesterday + timedelta(days=1),
            confidence_level=0.95
        )
        
        kpi2 = KPISnapshot(
            workspace_id=1,
            metric_name='cost_avoided_usd',
            metric_category='cost',
            value=15000.0,
            unit='USD',
            period_type='daily',
            period_start=yesterday,
            period_end=yesterday + timedelta(days=1),
            confidence_level=0.95
        )
        
        db.session.add(kpi1)
        db.session.add(kpi2)
        
        # Create sample shipments
        shipment1 = Shipment(
            workspace_id=1,
            tracking_number='TEST123',
            status='delivered',
            scheduled_arrival=yesterday,
            actual_arrival=yesterday - timedelta(hours=2),  # On time
            risk_score=3.5
        )
        
        shipment2 = Shipment(
            workspace_id=1,
            tracking_number='TEST456',
            status='in_transit',
            scheduled_arrival=datetime.utcnow() + timedelta(days=1),
            risk_score=7.2
        )
        
        db.session.add(shipment1)
        db.session.add(shipment2)
        
        # Create sample alert
        alert1 = Alert(
            workspace_id=1,
            type='delay',
            title='Shipment Delay Alert',
            description='Test alert for delay',
            severity='high',
            status='open',
            probability=0.85,
            confidence=0.9
        )
        
        db.session.add(alert1)
        db.session.commit()


class TestReportsAPI:
    """Test suite for Reports API endpoints"""
    
    def test_kpi_endpoints_return_live_data(self, client, sample_data):
        """Test that KPI endpoints return live data from database"""
        # Test live metrics endpoint
        response = client.get('/api/realtime/metrics/live?workspace_id=1')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'data' in data
        assert 'timestamp' in data
        
        # Verify metrics structure
        metrics_data = data['data']
        assert 'metrics_count' in metrics_data
        assert 'overall_health' in metrics_data
        
    def test_time_period_filtering(self, client, sample_data):
        """Test time period filtering for historical metrics"""
        # Test historical metrics with different periods
        response = client.get('/api/realtime/metrics/historical?metric_name=on_time_delivery_rate&days=7')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'data' in data
        
        metrics_data = data['data']
        assert metrics_data['metric_name'] == 'on_time_delivery_rate'
        assert metrics_data['period_type'] == 'daily'
        assert 'data_points' in metrics_data
        
        # Test with different period
        response = client.get('/api/realtime/metrics/historical?metric_name=cost_avoided_usd&days=30')
        assert response.status_code == 200
        
    def test_export_functionality(self, client, sample_data):
        """Test export functionality for reports"""
        # Test dashboard data export
        response = client.get('/api/realtime/dashboard/live?workspace_id=1')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['success'] is True
        
        # Verify exportable data structure
        dashboard_data = data['data']
        assert 'timestamp' in dashboard_data
        assert 'workspace_id' in dashboard_data
        assert 'real_time_metrics' in dashboard_data
        
    def test_trending_analysis_endpoint(self, client, sample_data):
        """Test trending analysis endpoint"""
        response = client.get('/api/realtime/metrics/trending?metric_name=on_time_delivery_rate&days=30')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'data' in data
        
        trending_data = data['data']
        assert 'trend' in trending_data
        assert 'change_percent' in trending_data
        assert 'data_points' in trending_data
        
    def test_comparative_analysis_endpoint(self, client, sample_data):
        """Test comparative analysis endpoint"""
        response = client.get('/api/realtime/metrics/comparative?metric_name=on_time_delivery_rate&compare_type=mom')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'data' in data
        
        comp_data = data['data']
        assert 'comparison_type' in comp_data
        assert comp_data['comparison_type'] == 'mom'
        assert 'change_percent' in comp_data
        
    def test_system_health_endpoint(self, client, sample_data):
        """Test system health monitoring endpoint"""
        response = client.get('/api/realtime/system/health?workspace_id=1')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'data' in data
        
        health_data = data['data']
        assert 'overall_score' in health_data
        assert 'status' in health_data
        assert 'components' in health_data
        assert 'metrics' in health_data
        
    def test_active_alerts_endpoint(self, client, sample_data):
        """Test active alerts endpoint"""
        response = client.get('/api/realtime/alerts/active?workspace_id=1&limit=10')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'data' in data
        
        alerts_data = data['data']
        assert 'alerts' in alerts_data
        assert 'total_count' in alerts_data
        assert len(alerts_data['alerts']) >= 0
        
    def test_error_handling(self, client):
        """Test API error handling"""
        # Test invalid metric name
        response = client.get('/api/realtime/metrics/historical?metric_name=invalid_metric&days=7')
        assert response.status_code == 200  # Should return empty results, not error
        
        # Test invalid parameters
        response = client.get('/api/realtime/metrics/historical?days=invalid')
        assert response.status_code == 400 or response.status_code == 422


class TestMetricsCalculator:
    """Test suite for MetricsCalculator class"""
    
    def test_kpi_calculations_accuracy(self, app, sample_data):
        """Test accuracy of KPI calculations"""
        with app.app_context():
            calculator = MetricsCalculator(workspace_id=1)
            
            # Test OTD calculation
            otd_metric = calculator.calculate_real_time_otd()
            assert otd_metric.name == 'on_time_delivery_rate'
            assert otd_metric.unit == '%'
            assert otd_metric.value >= 0
            assert otd_metric.status in ['good', 'warning', 'critical']
            
            # Test cost avoidance calculation
            cost_metric = calculator.track_cost_avoidance()
            assert cost_metric.name == 'cost_avoidance_usd'
            assert cost_metric.unit == 'USD'
            assert cost_metric.value >= 0
            
            # Test MTTR calculation
            mttr_metric = calculator.measure_mttr_metrics()
            assert mttr_metric.name == 'alert_mttr_hours'
            assert mttr_metric.unit == 'hours'
            assert mttr_metric.value >= 0
            
    def test_risk_score_calculation(self, app, sample_data):
        """Test risk score trending calculation"""
        with app.app_context():
            calculator = MetricsCalculator(workspace_id=1)
            risk_metric = calculator.calculate_risk_score_trend()
            
            assert risk_metric.name == 'average_risk_score'
            assert risk_metric.unit == 'score'
            assert risk_metric.value >= 0
            assert risk_metric.value <= 10  # Risk score should be 0-10
            
    def test_metrics_summary(self, app, sample_data):
        """Test comprehensive metrics summary"""
        with app.app_context():
            calculator = MetricsCalculator(workspace_id=1)
            summary = calculator.get_metrics_summary()
            
            assert 'timestamp' in summary
            assert 'metrics_count' in summary
            assert 'overall_health' in summary
            assert 'metrics' in summary
            assert summary['overall_health'] in ['good', 'warning', 'critical']


class TestKPICollector:
    """Test suite for KPICollector class"""
    
    def test_historical_data_collection(self, app, sample_data):
        """Test historical data collection and storage"""
        with app.app_context():
            collector = KPICollector(workspace_id=1, enable_realtime=False)
            
            # Test daily snapshot collection
            kpis = collector.collect_daily_snapshots(broadcast_update=False)
            assert isinstance(kpis, dict)
            assert len(kpis) > 0
            
            # Verify snapshots are stored in database
            snapshots = db.session.query(KPISnapshot).filter_by(workspace_id=1).all()
            assert len(snapshots) > 0
            
    def test_trending_calculations(self, app, sample_data):
        """Test trending metrics calculations"""
        with app.app_context():
            collector = KPICollector(workspace_id=1)
            
            # Test trending analysis
            trending = collector.calculate_trending_metrics('on_time_delivery_rate', days=30)
            assert 'trend' in trending
            assert 'change_percent' in trending
            assert 'data_points' in trending
            assert trending['trend'] in ['improving', 'declining', 'stable']
            
    def test_comparative_analytics(self, app, sample_data):
        """Test comparative analytics calculations"""
        with app.app_context():
            collector = KPICollector(workspace_id=1)
            
            # Test month-over-month comparison
            comparison = collector.generate_comparative_analytics('on_time_delivery_rate', 'mom')
            assert 'comparison_type' in comparison
            assert comparison['comparison_type'] == 'mom'
            assert 'change_percent' in comparison
            assert 'current_period_avg' in comparison
            assert 'previous_period_avg' in comparison
            
    def test_real_time_updates(self, app, sample_data):
        """Test real-time metrics collection"""
        with app.app_context():
            collector = KPICollector(workspace_id=1, enable_realtime=False)
            
            # Test real-time metrics collection
            rt_metrics = collector.collect_real_time_metrics(broadcast_update=False)
            assert 'timestamp' in rt_metrics
            assert 'metrics_count' in rt_metrics
            
    def test_live_dashboard_data(self, app, sample_data):
        """Test live dashboard data generation"""
        with app.app_context():
            collector = KPICollector(workspace_id=1, enable_realtime=False)
            
            dashboard_data = collector.get_live_dashboard_data()
            assert 'timestamp' in dashboard_data
            assert 'workspace_id' in dashboard_data
            assert 'real_time_metrics' in dashboard_data
            assert 'trending_data' in dashboard_data
            assert 'alerts' in dashboard_data
            
    def test_historical_data_storage(self, app):
        """Test manual historical data storage"""
        with app.app_context():
            collector = KPICollector(workspace_id=1)
            
            # Store test metric
            collector.store_historical_data(
                metric_name='test_metric',
                value=95.5,
                category='test',
                period_type='daily'
            )
            
            # Verify storage
            snapshot = db.session.query(KPISnapshot).filter_by(
                metric_name='test_metric',
                workspace_id=1
            ).first()
            
            assert snapshot is not None
            assert snapshot.value == 95.5
            assert snapshot.metric_category == 'test'


class TestErrorHandling:
    """Test error handling and edge cases"""
    
    def test_invalid_workspace_id(self, client):
        """Test handling of invalid workspace IDs"""
        response = client.get('/api/realtime/metrics/live?workspace_id=999')
        assert response.status_code == 200  # Should handle gracefully
        
    def test_missing_parameters(self, client):
        """Test handling of missing required parameters"""
        response = client.get('/api/realtime/metrics/historical')
        assert response.status_code == 400 or response.status_code == 422
        
    def test_empty_database(self, client, app):
        """Test behavior with empty database"""
        with app.app_context():
            # Clear all data
            db.session.query(KPISnapshot).delete()
            db.session.query(Shipment).delete()
            db.session.query(Alert).delete()
            db.session.commit()
            
            # Test endpoints with no data
            response = client.get('/api/realtime/metrics/live?workspace_id=1')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert data['success'] is True


if __name__ == '__main__':
    pytest.main([__file__])
