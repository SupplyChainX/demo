/**
 * Real-Time Analytics JavaScript Module
 * Phase 5: Real-Time Analytics Engine with WebSocket Integration
 * 
 * Provides live updates for KPIs, metrics, and dashboard data
 */

class RealTimeAnalytics {
    constructor(options = {}) {
        this.socket = null;
        this.workspace_id = options.workspace_id || 1;
        this.update_interval = options.update_interval || 30000; // 30 seconds
        this.auto_reconnect = options.auto_reconnect !== false;
        this.callbacks = {
            onMetricsUpdate: options.onMetricsUpdate || this.defaultMetricsHandler,
            onDashboardUpdate: options.onDashboardUpdate || this.defaultDashboardHandler,
            onKPIUpdate: options.onKPIUpdate || this.defaultKPIHandler,
            onError: options.onError || this.defaultErrorHandler,
            onConnectionChange: options.onConnectionChange || this.defaultConnectionHandler
        };
        
        this.isConnected = false;
        this.charts = {};
        this.lastUpdate = null;
        
        this.initializeWebSocket();
        this.setupPeriodicUpdates();
    }

    /**
     * Initialize WebSocket connection
     */
    initializeWebSocket() {
        try {
            // Use the existing socket.io connection if available
            if (typeof io !== 'undefined') {
                this.socket = io();
                this.setupSocketEvents();
                console.log('Real-time analytics WebSocket initialized');
            } else {
                console.warn('Socket.IO not available - falling back to polling');
                this.setupPollingFallback();
            }
        } catch (error) {
            console.error('Error initializing WebSocket:', error);
            this.setupPollingFallback();
        }
    }

    /**
     * Setup WebSocket event listeners
     */
    setupSocketEvents() {
        if (!this.socket) return;

        this.socket.on('connect', () => {
            this.isConnected = true;
            console.log('Real-time analytics connected');
            this.callbacks.onConnectionChange(true);
            
            // Subscribe to real-time updates
            this.subscribeTo('metrics');
            this.subscribeTo('dashboard');
        });

        this.socket.on('disconnect', () => {
            this.isConnected = false;
            console.log('Real-time analytics disconnected');
            this.callbacks.onConnectionChange(false);
        });

        this.socket.on('realtime_metrics', (data) => {
            this.handleMetricsUpdate(data);
        });

        this.socket.on('dashboard_update', (data) => {
            this.handleDashboardUpdate(data);
        });

        this.socket.on('kpi_update', (data) => {
            this.handleKPIUpdate(data);
        });

        this.socket.on('initial_metrics', (data) => {
            this.handleMetricsUpdate(data);
        });

        this.socket.on('initial_dashboard', (data) => {
            this.handleDashboardUpdate(data);
        });

        this.socket.on('error', (error) => {
            console.error('Real-time analytics error:', error);
            this.callbacks.onError(error);
        });
    }

    /**
     * Subscribe to specific real-time updates
     */
    subscribeTo(type) {
        if (!this.socket || !this.isConnected) return;

        if (type === 'metrics') {
            this.socket.emit('subscribe_metrics', {
                workspace_id: this.workspace_id
            });
        } else if (type === 'dashboard') {
            this.socket.emit('subscribe_dashboard', {
                workspace_id: this.workspace_id
            });
        }
    }

    /**
     * Request on-demand metric update
     */
    requestMetricUpdate(metric_name = null) {
        if (!this.socket || !this.isConnected) {
            this.fallbackDataFetch();
            return;
        }

        this.socket.emit('request_metric_update', {
            workspace_id: this.workspace_id,
            metric_name: metric_name
        });
    }

    /**
     * Setup polling fallback for when WebSocket is not available
     */
    setupPollingFallback() {
        console.log('Setting up polling fallback for real-time updates');
        
        setInterval(() => {
            this.fallbackDataFetch();
        }, this.update_interval);
    }

    /**
     * Fallback data fetching via HTTP API
     */
    async fallbackDataFetch() {
        try {
            // Fetch live metrics
            const metricsResponse = await fetch(`/api/realtime/metrics/live?workspace_id=${this.workspace_id}`);
            if (metricsResponse.ok) {
                const metricsData = await metricsResponse.json();
                this.handleMetricsUpdate({
                    type: 'realtime_metrics',
                    timestamp: new Date().toISOString(),
                    workspace_id: this.workspace_id,
                    metrics: metricsData.data
                });
            }

            // Fetch dashboard data
            const dashboardResponse = await fetch(`/api/realtime/dashboard/live?workspace_id=${this.workspace_id}`);
            if (dashboardResponse.ok) {
                const dashboardData = await dashboardResponse.json();
                this.handleDashboardUpdate({
                    type: 'dashboard_update',
                    timestamp: new Date().toISOString(),
                    workspace_id: this.workspace_id,
                    data: dashboardData.data
                });
            }

        } catch (error) {
            console.error('Error fetching fallback data:', error);
            this.callbacks.onError(error);
        }
    }

    /**
     * Handle metrics updates
     */
    handleMetricsUpdate(data) {
        this.lastUpdate = data.timestamp;
        
        if (data.metrics && data.metrics.metrics) {
            // Update metric displays
            this.updateMetricDisplays(data.metrics.metrics);
            
            // Update status indicators
            this.updateSystemStatus(data.metrics.overall_health);
            
            // Call custom callback
            this.callbacks.onMetricsUpdate(data.metrics);
        }
    }

    /**
     * Handle dashboard updates
     */
    handleDashboardUpdate(data) {
        this.lastUpdate = data.timestamp;
        
        if (data.data) {
            // Update charts if available
            this.updateCharts(data.data);
            
            // Update alerts display
            this.updateAlertsDisplay(data.data.alerts || []);
            
            // Call custom callback
            this.callbacks.onDashboardUpdate(data.data);
        }
    }

    /**
     * Handle KPI updates
     */
    handleKPIUpdate(data) {
        this.lastUpdate = data.timestamp;
        
        if (data.kpis) {
            // Update KPI displays
            this.updateKPIDisplays(data.kpis);
            
            // Call custom callback
            this.callbacks.onKPIUpdate(data.kpis);
        }
    }

    /**
     * Update metric displays on the page
     */
    updateMetricDisplays(metrics) {
        for (const [key, metric] of Object.entries(metrics)) {
            // Update value displays
            const valueElement = document.querySelector(`[data-metric="${key}"] .metric-value`);
            if (valueElement) {
                valueElement.textContent = `${metric.value} ${metric.unit || ''}`;
            }

            // Update trend indicators
            const trendElement = document.querySelector(`[data-metric="${key}"] .trend-indicator`);
            if (trendElement) {
                trendElement.className = `trend-indicator trend-${metric.trend}`;
                trendElement.innerHTML = this.getTrendIcon(metric.trend);
            }

            // Update status badges
            const statusElement = document.querySelector(`[data-metric="${key}"] .status-badge`);
            if (statusElement) {
                statusElement.className = `status-badge badge bg-${this.getStatusColor(metric.status)}`;
                statusElement.textContent = metric.status.toUpperCase();
            }

            // Update change percentages
            const changeElement = document.querySelector(`[data-metric="${key}"] .change-percent`);
            if (changeElement) {
                const sign = metric.change_percent >= 0 ? '+' : '';
                changeElement.textContent = `${sign}${metric.change_percent}%`;
                changeElement.className = `change-percent ${metric.change_percent >= 0 ? 'positive' : 'negative'}`;
            }
        }
    }

    /**
     * Update system status indicator
     */
    updateSystemStatus(overall_health) {
        const statusElement = document.querySelector('.system-status');
        if (statusElement) {
            statusElement.className = `system-status status-${overall_health}`;
            statusElement.textContent = overall_health.toUpperCase();
        }

        // Update status dot
        const statusDot = document.querySelector('.status-dot');
        if (statusDot) {
            statusDot.className = `status-dot bg-${this.getStatusColor(overall_health)}`;
        }
    }

    /**
     * Update KPI displays
     */
    updateKPIDisplays(kpis) {
        for (const [key, value] of Object.entries(kpis)) {
            const kpiElement = document.querySelector(`[data-kpi="${key}"]`);
            if (kpiElement) {
                const valueSpan = kpiElement.querySelector('.kpi-value');
                if (valueSpan) {
                    valueSpan.textContent = value;
                }
            }
        }
    }

    /**
     * Update chart data
     */
    updateCharts(dashboardData) {
        // Update trending charts
        if (dashboardData.trending_data) {
            for (const [metric, trendData] of Object.entries(dashboardData.trending_data)) {
                this.updateTrendChart(metric, trendData);
            }
        }

        // Update real-time metrics charts
        if (dashboardData.real_time_metrics && dashboardData.real_time_metrics.metrics) {
            this.updateRealTimeCharts(dashboardData.real_time_metrics.metrics);
        }
    }

    /**
     * Update trend chart for a specific metric
     */
    updateTrendChart(metric, trendData) {
        const chartId = `${metric}_trend_chart`;
        const chartElement = document.getElementById(chartId);
        
        if (chartElement && trendData.chart_data) {
            // Update Chart.js chart if it exists
            if (this.charts[chartId]) {
                const chart = this.charts[chartId];
                chart.data.labels = trendData.chart_data.map(d => new Date(d.date).toLocaleDateString());
                chart.data.datasets[0].data = trendData.chart_data.map(d => d.value);
                chart.update('none'); // Update without animation for real-time feel
            }
        }
    }

    /**
     * Update real-time charts
     */
    updateRealTimeCharts(metrics) {
        // Update gauge charts, progress bars, etc.
        for (const [key, metric] of Object.entries(metrics)) {
            this.updateRealTimeChart(key, metric);
        }
    }

    /**
     * Update individual real-time chart
     */
    updateRealTimeChart(metricName, metricData) {
        const chartId = `${metricName}_realtime_chart`;
        
        if (this.charts[chartId]) {
            const chart = this.charts[chartId];
            
            // Add new data point
            const now = new Date();
            chart.data.labels.push(now.toLocaleTimeString());
            chart.data.datasets[0].data.push(metricData.value);
            
            // Keep only last 20 points for performance
            if (chart.data.labels.length > 20) {
                chart.data.labels.shift();
                chart.data.datasets[0].data.shift();
            }
            
            chart.update('none');
        }
    }

    /**
     * Update alerts display
     */
    updateAlertsDisplay(alerts) {
        const alertsContainer = document.querySelector('.alerts-container');
        if (!alertsContainer) return;

        // Clear existing alerts
        alertsContainer.innerHTML = '';

        // Add new alerts
        alerts.forEach(alert => {
            const alertElement = this.createAlertElement(alert);
            alertsContainer.appendChild(alertElement);
        });

        // Update alert count badge
        const alertBadge = document.querySelector('.alert-count-badge');
        if (alertBadge) {
            alertBadge.textContent = alerts.length;
            alertBadge.className = `alert-count-badge badge bg-${alerts.length > 0 ? 'danger' : 'success'}`;
        }
    }

    /**
     * Create alert element
     */
    createAlertElement(alert) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${this.getAlertSeverityClass(alert.severity)} alert-dismissible fade show`;
        
        alertDiv.innerHTML = `
            <div class="d-flex align-items-center">
                <i class="fas fa-exclamation-triangle me-2"></i>
                <div>
                    <strong>${alert.title}</strong>
                    <div class="small text-muted">${alert.type} • ${new Date(alert.created_at).toLocaleString()}</div>
                </div>
                <button type="button" class="btn-close ms-auto" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        return alertDiv;
    }

    /**
     * Register a chart for real-time updates
     */
    registerChart(chartId, chartInstance) {
        this.charts[chartId] = chartInstance;
    }

    /**
     * Setup periodic updates even when connected
     */
    setupPeriodicUpdates() {
        setInterval(() => {
            if (this.isConnected) {
                this.requestMetricUpdate(); // Request fresh data
            }
        }, this.update_interval);
    }

    /**
     * Helper methods
     */
    getTrendIcon(trend) {
        switch (trend) {
            case 'up': return '<i class="fas fa-arrow-up text-success"></i>';
            case 'down': return '<i class="fas fa-arrow-down text-danger"></i>';
            case 'stable': return '<i class="fas fa-minus text-muted"></i>';
            default: return '<i class="fas fa-question text-secondary"></i>';
        }
    }

    getStatusColor(status) {
        switch (status) {
            case 'good': case 'excellent': return 'success';
            case 'warning': case 'fair': return 'warning';
            case 'critical': case 'poor': return 'danger';
            default: return 'secondary';
        }
    }

    getAlertSeverityClass(severity) {
        switch (severity) {
            case 'critical': return 'danger';
            case 'high': return 'warning';
            case 'medium': return 'info';
            case 'low': return 'light';
            default: return 'secondary';
        }
    }

    /**
     * Default event handlers
     */
    defaultMetricsHandler(metrics) {
        console.log('Metrics updated:', metrics);
    }

    defaultDashboardHandler(data) {
        console.log('Dashboard updated:', data);
    }

    defaultKPIHandler(kpis) {
        console.log('KPIs updated:', kpis);
    }

    defaultErrorHandler(error) {
        console.error('Real-time analytics error:', error);
    }

    defaultConnectionHandler(connected) {
        console.log('Connection status:', connected ? 'Connected' : 'Disconnected');
        
        // Update connection indicator
        const indicator = document.querySelector('.connection-indicator');
        if (indicator) {
            indicator.className = `connection-indicator ${connected ? 'connected' : 'disconnected'}`;
            indicator.title = connected ? 'Real-time updates active' : 'Real-time updates inactive';
        }
    }

    /**
     * Public API methods
     */
    
    /**
     * Start real-time monitoring
     */
    startMonitoring() {
        if (this.socket && this.isConnected) {
            this.subscribeTo('metrics');
            this.subscribeTo('dashboard');
        }
        
        // Also start server-side monitoring
        fetch('/api/realtime/monitoring/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                workspace_id: this.workspace_id,
                interval_seconds: this.update_interval / 1000
            })
        }).catch(error => {
            console.error('Error starting server-side monitoring:', error);
        });
    }

    /**
     * Stop real-time monitoring
     */
    stopMonitoring() {
        if (this.socket) {
            this.socket.disconnect();
        }
    }

    /**
     * Get connection status
     */
    getConnectionStatus() {
        return {
            connected: this.isConnected,
            lastUpdate: this.lastUpdate,
            workspace_id: this.workspace_id
        };
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = RealTimeAnalytics;
} else if (typeof window !== 'undefined') {
    window.RealTimeAnalytics = RealTimeAnalytics;
}
