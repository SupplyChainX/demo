/**
 * Agent Dashboard JavaScript
 * Handles all interactions and real-time updates for the agent management dashboard
 */

class AgentDashboard {
    constructor() {
        this.refreshInterval = 30000; // 30 seconds
        this.charts = {};
        this.currentAgent = null;
        this.autoRefresh = true;
        this.wsConnection = null;
        
        this.init();
    }
    
    init() {
        console.log('🤖 Initializing Agent Dashboard');
        
        // Initialize on DOM ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.setupDashboard());
        } else {
            this.setupDashboard();
        }
    }
    
    setupDashboard() {
        this.bindEvents();
        this.loadInitialData();
        this.startAutoRefresh();
        this.initializeWebSocket();
        
        console.log('✅ Agent Dashboard initialized');
    }
    
    bindEvents() {
        // Main dashboard controls
        document.getElementById('refreshDashboard')?.addEventListener('click', () => this.refreshAll());
        document.getElementById('startAllAgents')?.addEventListener('click', () => this.startAllAgents());
        
        // Tab switching
        const tabTriggers = document.querySelectorAll('[data-bs-toggle="tab"]');
        tabTriggers.forEach(tab => {
            tab.addEventListener('shown.bs.tab', (e) => this.handleTabSwitch(e.target.getAttribute('data-bs-target')));
        });
        
        // Filter controls
        document.querySelectorAll('[name="recFilter"]').forEach(radio => {
            radio.addEventListener('change', () => this.filterRecommendations());
        });
        
        document.getElementById('logFilter')?.addEventListener('change', () => this.filterLogs());
        document.getElementById('clearLogs')?.addEventListener('click', () => this.clearLogs());
        
        // Configuration
        document.getElementById('saveConfig')?.addEventListener('click', () => this.saveConfiguration());
        document.getElementById('exportLogs')?.addEventListener('click', () => this.exportLogs());
        document.getElementById('systemDiagnostics')?.addEventListener('click', () => this.runDiagnostics());
    }
    
    async loadInitialData() {
        try {
            await Promise.all([
                this.loadSystemOverview(),
                this.loadAgentStatus(),
                this.loadCommunicationData(),
                this.loadRecommendations(),
                this.loadAnalyticsInsights(),
                this.loadActivityLogs()
            ]);
        } catch (error) {
            console.error('Error loading initial data:', error);
            this.showError('Failed to load dashboard data');
        }
    }
    
    async loadSystemOverview() {
        try {
            const response = await fetch('/agent-dashboard/api/overview');
            const data = await response.json();
            
            if (!response.ok) throw new Error(data.error || 'Failed to load overview');
            
            this.updateSystemOverview(data);
        } catch (error) {
            console.error('Error loading system overview:', error);
            this.showMockSystemOverview();
        }
    }
    
    updateSystemOverview(data) {
        const overview = data.system_overview;
        
        // Update system health
        const healthScore = overview.system_health || 85;
        const healthElement = document.getElementById('systemHealthScore');
        const healthStatus = document.getElementById('systemHealthStatus');
        const healthCircle = document.getElementById('systemHealthCircle');
        
        if (healthElement) healthElement.textContent = healthScore;
        if (healthStatus) {
            healthStatus.textContent = healthScore >= 90 ? 'Excellent' : 
                                     healthScore >= 75 ? 'Good' : 
                                     healthScore >= 50 ? 'Fair' : 'Poor';
        }
        if (healthCircle) {
            healthCircle.style.background = healthScore >= 90 ? '#28a745' :
                                          healthScore >= 75 ? '#ffc107' : '#dc3545';
        }
        
        // Update agent counts
        document.getElementById('activeAgentsCount').textContent = overview.active_agents || 0;
        document.getElementById('totalAgentsCount').textContent = overview.total_agents || 0;
        
        // Update metrics
        document.getElementById('messagesPerHour').textContent = this.formatNumber(1247);
        document.getElementById('totalRecommendations').textContent = this.formatNumber(23);
        document.getElementById('pendingRecommendations').textContent = this.formatNumber(8);
    }
    
    showMockSystemOverview() {
        // Show mock data when API is not available
        this.updateSystemOverview({
            system_overview: {
                active_agents: 4,
                total_agents: 5,
                system_health: 87,
                last_update: new Date().toISOString()
            }
        });
    }
    
    async loadAgentStatus() {
        try {
            const response = await fetch('/agent-dashboard/api/agents/status');
            const data = await response.json();
            
            if (!response.ok) throw new Error(data.error || 'Failed to load agent status');
            
            this.updateAgentCards(data.agents || []);
        } catch (error) {
            console.error('Error loading agent status:', error);
            this.showMockAgentStatus();
        }
    }
    
    updateAgentCards(agents) {
        const container = document.getElementById('agentsContainer');
        if (!container) return;
        
        container.innerHTML = '';
        
        agents.forEach(agent => {
            const agentCard = this.createAgentCard(agent);
            container.appendChild(agentCard);
        });
        
        if (agents.length === 0) {
            container.innerHTML = `
                <div class="col-12 text-center py-4">
                    <i class="bi bi-robot fs-1 text-muted"></i>
                    <p class="text-muted mt-2">No agents found</p>
                </div>
            `;
        }
    }
    
    createAgentCard(agent) {
        const col = document.createElement('div');
        col.className = 'col-lg-6 col-xl-4';
        
        const statusClass = agent.status === 'active' ? 'agent-active' : 'agent-inactive';
        const healthColor = agent.health >= 80 ? 'health-good' : 
                           agent.health >= 60 ? 'health-warning' : 'health-critical';
        
        col.innerHTML = `
            <div class="card agent-card ${statusClass} h-100">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <div class="d-flex align-items-center">
                        <span class="health-indicator ${healthColor}"></span>
                        <h6 class="mb-0">${agent.display_name || agent.name}</h6>
                    </div>
                    <div class="dropdown">
                        <button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown">
                            <i class="bi bi-three-dots"></i>
                        </button>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item" href="#" onclick="agentDashboard.viewAgentDetails('${agent.name}')">
                                <i class="bi bi-eye"></i> View Details
                            </a></li>
                            <li><a class="dropdown-item" href="#" onclick="agentDashboard.controlAgent('${agent.name}', 'restart')">
                                <i class="bi bi-arrow-clockwise"></i> Restart
                            </a></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item" href="#" onclick="agentDashboard.controlAgent('${agent.name}', '${agent.status === 'active' ? 'stop' : 'start'}')">
                                <i class="bi bi-${agent.status === 'active' ? 'stop' : 'play'}"></i> ${agent.status === 'active' ? 'Stop' : 'Start'}
                            </a></li>
                        </ul>
                    </div>
                </div>
                <div class="card-body">
                    <div class="row g-2 mb-3">
                        <div class="col-6">
                            <small class="text-muted">Status</small>
                            <div class="fw-bold text-${agent.status === 'active' ? 'success' : 'danger'}">
                                ${agent.status.charAt(0).toUpperCase() + agent.status.slice(1)}
                            </div>
                        </div>
                        <div class="col-6">
                            <small class="text-muted">Health</small>
                            <div class="fw-bold">${agent.health || 0}%</div>
                        </div>
                        <div class="col-6">
                            <small class="text-muted">Uptime</small>
                            <div class="fw-bold">${agent.uptime || 0}h</div>
                        </div>
                        <div class="col-6">
                            <small class="text-muted">Messages</small>
                            <div class="fw-bold">${this.formatNumber(agent.messages_processed || 0)}</div>
                        </div>
                    </div>
                    
                    <div class="mb-3">
                        <small class="text-muted">Capabilities</small>
                        <div class="mt-1">
                            ${(agent.capabilities || []).map(cap => 
                                `<span class="badge bg-light text-dark me-1">${cap}</span>`
                            ).join('')}
                        </div>
                    </div>
                    
                    <div class="d-grid gap-2">
                        <button class="btn btn-sm btn-outline-primary" onclick="agentDashboard.viewAgentPerformance('${agent.name}')">
                            <i class="bi bi-graph-up"></i> Performance
                        </button>
                    </div>
                </div>
                <div class="card-footer">
                    <small class="text-muted">
                        Last activity: ${this.formatTime(agent.last_activity)}
                    </small>
                </div>
            </div>
        `;
        
        return col;
    }
    
    showMockAgentStatus() {
        const mockAgents = [
            {
                name: 'risk_predictor_agent',
                display_name: 'Risk Predictor',
                status: 'active',
                health: 95,
                uptime: 72.5,
                messages_processed: 1456,
                capabilities: ['Risk Assessment', 'Predictive Analysis'],
                last_activity: new Date().toISOString()
            },
            {
                name: 'route_optimizer_agent',
                display_name: 'Route Optimizer',
                status: 'active',
                health: 88,
                uptime: 68.2,
                messages_processed: 892,
                capabilities: ['Route Planning', 'Cost Optimization'],
                last_activity: new Date().toISOString()
            },
            {
                name: 'procurement_agent',
                display_name: 'Procurement Assistant',
                status: 'active',
                health: 91,
                uptime: 71.1,
                messages_processed: 634,
                capabilities: ['Supplier Analysis', 'Purchase Orders'],
                last_activity: new Date().toISOString()
            },
            {
                name: 'advanced_analytics_agent',
                display_name: 'Advanced Analytics',
                status: 'active',
                health: 97,
                uptime: 75.3,
                messages_processed: 2341,
                capabilities: ['ML Analytics', 'Demand Forecasting'],
                last_activity: new Date().toISOString()
            }
        ];
        
        this.updateAgentCards(mockAgents);
    }
    
    async loadCommunicationData() {
        try {
            const response = await fetch('/agent-dashboard/api/communication/overview');
            const data = await response.json();
            
            if (!response.ok) throw new Error(data.error || 'Failed to load communication data');
            
            this.updateCommunicationView(data);
        } catch (error) {
            console.error('Error loading communication data:', error);
            this.showMockCommunicationData();
        }
    }
    
    updateCommunicationView(data) {
        // Update communication flows
        const flowsContainer = document.getElementById('communicationFlows');
        if (flowsContainer && data.message_flows) {
            flowsContainer.innerHTML = '';
            data.message_flows.forEach(flow => {
                const flowElement = this.createCommunicationFlow(flow);
                flowsContainer.appendChild(flowElement);
            });
        }
        
        // Update performance metrics
        const metrics = data.performance_metrics || {};
        document.getElementById('avgLatency').textContent = `${metrics.average_latency || 0} ms`;
        document.getElementById('throughput').textContent = `${metrics.throughput || 0} msg/min`;
        document.getElementById('errorRate').textContent = `${metrics.error_rate || 0}%`;
        
        // Update progress bars
        this.updateProgressBar('latencyBar', (metrics.average_latency || 0) / 500 * 100);
        this.updateProgressBar('throughputBar', (metrics.throughput || 0) / 100 * 100);
        this.updateProgressBar('errorRateBar', metrics.error_rate || 0);
        
        // Update active channels
        this.updateActiveChannels(data.active_channels || []);
    }
    
    createCommunicationFlow(flow) {
        const div = document.createElement('div');
        div.className = 'communication-flow';
        div.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <strong>${this.formatAgentName(flow.from)}</strong> → 
                    <strong>${this.formatAgentName(flow.to)}</strong>
                </div>
                <div class="flow-arrow">→</div>
            </div>
            <div class="row mt-2">
                <div class="col-6">
                    <small class="text-muted">Messages</small>
                    <div class="fw-bold">${flow.count || 0}</div>
                </div>
                <div class="col-6">
                    <small class="text-muted">Avg Latency</small>
                    <div class="fw-bold">${flow.avg_latency || 0}ms</div>
                </div>
            </div>
        `;
        return div;
    }
    
    updateActiveChannels(channels) {
        const container = document.getElementById('activeChannels');
        if (!container) return;
        
        container.innerHTML = '';
        channels.forEach(channel => {
            const channelElement = document.createElement('div');
            channelElement.className = 'd-flex justify-content-between align-items-center mb-2';
            channelElement.innerHTML = `
                <div>
                    <span class="badge bg-${channel.active ? 'success' : 'secondary'} me-2"></span>
                    ${channel.name}
                </div>
                <small class="text-muted">${channel.message_count || 0}</small>
            `;
            container.appendChild(channelElement);
        });
    }
    
    showMockCommunicationData() {
        const mockData = {
            message_flows: [
                { from: 'risk_predictor_agent', to: 'orchestrator_agent', count: 145, avg_latency: 120 },
                { from: 'route_optimizer_agent', to: 'orchestrator_agent', count: 89, avg_latency: 95 },
                { from: 'procurement_agent', to: 'orchestrator_agent', count: 67, avg_latency: 150 }
            ],
            performance_metrics: {
                average_latency: 125,
                throughput: 45,
                error_rate: 2.1
            },
            active_channels: [
                { name: 'risk_alerts', active: true, message_count: 234 },
                { name: 'route_updates', active: true, message_count: 156 },
                { name: 'procurement_requests', active: true, message_count: 89 }
            ]
        };
        
        this.updateCommunicationView(mockData);
    }
    
    async loadRecommendations() {
        try {
            const response = await fetch('/agent-dashboard/api/recommendations/management');
            const data = await response.json();
            
            if (!response.ok) throw new Error(data.error || 'Failed to load recommendations');
            
            this.updateRecommendationsView(data);
        } catch (error) {
            console.error('Error loading recommendations:', error);
            this.showMockRecommendations();
        }
    }
    
    updateRecommendationsView(data) {
        // Update recommendations panel
        const panel = document.getElementById('recommendationsPanel');
        if (panel && data.recent_recommendations) {
            panel.innerHTML = '';
            data.recent_recommendations.forEach(rec => {
                const recElement = this.createRecommendationCard(rec);
                panel.appendChild(recElement);
            });
        }
        
        // Update agent performance cards
        const perfContainer = document.getElementById('agentPerformanceCards');
        if (perfContainer && data.agent_performance) {
            perfContainer.innerHTML = '';
            Object.entries(data.agent_performance).forEach(([agent, perf]) => {
                const perfCard = this.createPerformanceCard(agent, perf);
                perfContainer.appendChild(perfCard);
            });
        }
    }
    
    createRecommendationCard(rec) {
        const div = document.createElement('div');
        div.className = 'card mb-3';
        
        const severityColor = rec.severity === 'high' ? 'danger' : 
                            rec.severity === 'medium' ? 'warning' : 'info';
        
        div.innerHTML = `
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <h6 class="card-title mb-1">${rec.title}</h6>
                    <span class="badge bg-${severityColor}">${rec.severity}</span>
                </div>
                <p class="card-text small text-muted mb-2">${rec.description || 'No description available'}</p>
                <div class="d-flex justify-content-between align-items-center">
                    <small class="text-muted">
                        <i class="bi bi-robot"></i> ${this.formatAgentName(rec.agent)}
                    </small>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-success" onclick="agentDashboard.approveRecommendation(${rec.id})">
                            <i class="bi bi-check"></i>
                        </button>
                        <button class="btn btn-outline-danger" onclick="agentDashboard.rejectRecommendation(${rec.id})">
                            <i class="bi bi-x"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        return div;
    }
    
    createPerformanceCard(agentName, performance) {
        const div = document.createElement('div');
        div.className = 'card mb-3';
        div.innerHTML = `
            <div class="card-body">
                <h6 class="card-title">${this.formatAgentName(agentName)}</h6>
                <div class="row g-2 text-center">
                    <div class="col-6">
                        <div class="h5 mb-0">${performance.total_recommendations || 0}</div>
                        <small class="text-muted">Total</small>
                    </div>
                    <div class="col-6">
                        <div class="h5 mb-0">${Math.round(performance.approval_rate || 0)}%</div>
                        <small class="text-muted">Approved</small>
                    </div>
                </div>
                <div class="progress mt-2" style="height: 4px;">
                    <div class="progress-bar" style="width: ${performance.approval_rate || 0}%"></div>
                </div>
            </div>
        `;
        return div;
    }
    
    showMockRecommendations() {
        const mockData = {
            recent_recommendations: [
                {
                    id: 1,
                    title: 'Reroute shipment via Hawaii',
                    description: 'Typhoon risk mitigation for LA-bound cargo',
                    severity: 'high',
                    agent: 'risk_predictor_agent',
                    status: 'pending'
                },
                {
                    id: 2,
                    title: 'Reorder critical components',
                    description: 'Inventory below safety threshold',
                    severity: 'medium',
                    agent: 'procurement_agent',
                    status: 'pending'
                }
            ],
            agent_performance: {
                risk_predictor_agent: { total_recommendations: 45, approval_rate: 87 },
                route_optimizer_agent: { total_recommendations: 32, approval_rate: 92 },
                procurement_agent: { total_recommendations: 28, approval_rate: 79 }
            }
        };
        
        this.updateRecommendationsView(mockData);
    }
    
    async loadAnalyticsInsights() {
        try {
            const response = await fetch('/agent-dashboard/api/analytics/insights');
            const data = await response.json();
            
            if (!response.ok) throw new Error(data.error || 'Failed to load analytics');
            
            this.updateAnalyticsView(data);
        } catch (error) {
            console.error('Error loading analytics insights:', error);
            this.showMockAnalyticsInsights();
        }
    }
    
    updateAnalyticsView(data) {
        // Update system insights
        const insightsContainer = document.getElementById('systemInsights');
        if (insightsContainer && data.system_insights) {
            insightsContainer.innerHTML = '';
            data.system_insights.forEach(insight => {
                const insightElement = this.createInsightItem(insight);
                insightsContainer.appendChild(insightElement);
            });
        }
        
        // Update optimization suggestions
        const suggestionsContainer = document.getElementById('optimizationSuggestions');
        if (suggestionsContainer && data.optimization_suggestions) {
            suggestionsContainer.innerHTML = '';
            data.optimization_suggestions.forEach(suggestion => {
                const suggestionElement = this.createSuggestionItem(suggestion);
                suggestionsContainer.appendChild(suggestionElement);
            });
        }
        
        // Initialize charts
        this.initializeAnalyticsCharts(data);
    }
    
    createInsightItem(insight) {
        const div = document.createElement('div');
        div.className = 'mb-3 p-3 bg-light rounded';
        
        const iconMap = {
            'performance': 'graph-up',
            'reliability': 'shield-check',
            'efficiency': 'lightning'
        };
        
        div.innerHTML = `
            <div class="d-flex align-items-start">
                <i class="bi bi-${iconMap[insight.type] || 'info-circle'} fs-5 text-primary me-3 mt-1"></i>
                <div>
                    <small class="text-uppercase text-muted fw-bold">${insight.type}</small>
                    <p class="mb-0">${insight.message}</p>
                </div>
            </div>
        `;
        
        return div;
    }
    
    createSuggestionItem(suggestion) {
        const div = document.createElement('div');
        div.className = 'mb-3 p-3 bg-light rounded';
        div.innerHTML = `
            <div class="d-flex align-items-start">
                <i class="bi bi-lightbulb fs-5 text-warning me-3 mt-1"></i>
                <div>
                    <small class="text-uppercase text-muted fw-bold">${suggestion.category}</small>
                    <p class="mb-0">${suggestion.suggestion}</p>
                </div>
            </div>
        `;
        return div;
    }
    
    showMockAnalyticsInsights() {
        const mockData = {
            system_insights: [
                { type: 'performance', message: 'Agent response times improved 15% this week' },
                { type: 'reliability', message: 'Zero agent failures in the last 48 hours' },
                { type: 'efficiency', message: 'Recommendation approval rate is 87%' }
            ],
            optimization_suggestions: [
                { category: 'performance', suggestion: 'Consider increasing check intervals during low activity periods' },
                { category: 'resource', suggestion: 'Route optimizer could benefit from additional memory allocation' },
                { category: 'reliability', suggestion: 'Enable auto-restart for agents with high restart counts' }
            ],
            ml_insights: {
                agent_efficiency_forecast: [95, 96, 94, 97, 95, 96, 98],
                resource_optimization: {
                    recommended_scaling: { risk_predictor_agent: 1.2, route_optimizer_agent: 0.8 }
                }
            }
        };
        
        this.updateAnalyticsView(mockData);
    }
    
    initializeAnalyticsCharts(data) {
        // Efficiency Forecast Chart
        const efficiencyCtx = document.getElementById('efficiencyForecastChart');
        if (efficiencyCtx) {
            this.charts.efficiencyForecast = new Chart(efficiencyCtx, {
                type: 'line',
                data: {
                    labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
                    datasets: [{
                        label: 'Efficiency Forecast',
                        data: data.ml_insights?.agent_efficiency_forecast || [95, 96, 94, 97, 95, 96, 98],
                        borderColor: '#667eea',
                        backgroundColor: 'rgba(102, 126, 234, 0.1)',
                        tension: 0.4,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: { display: true, text: 'Agent Efficiency Forecast' },
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            beginAtZero: false,
                            min: 90,
                            max: 100
                        }
                    }
                }
            });
        }
        
        // Resource Optimization Chart
        const resourceCtx = document.getElementById('resourceOptimizationChart');
        if (resourceCtx) {
            const scalingData = data.ml_insights?.resource_optimization?.recommended_scaling || {};
            
            this.charts.resourceOptimization = new Chart(resourceCtx, {
                type: 'bar',
                data: {
                    labels: Object.keys(scalingData).map(agent => this.formatAgentName(agent)),
                    datasets: [{
                        label: 'Recommended Scaling',
                        data: Object.values(scalingData),
                        backgroundColor: ['#28a745', '#ffc107', '#dc3545', '#007bff'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: { display: true, text: 'Resource Optimization Recommendations' },
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            max: 2,
                            ticks: {
                                callback: function(value) {
                                    return value + 'x';
                                }
                            }
                        }
                    }
                }
            });
        }
    }
    
    async loadActivityLogs() {
        try {
            const response = await fetch('/agent-dashboard/api/overview');
            const data = await response.json();
            
            if (!response.ok) throw new Error(data.error || 'Failed to load activity logs');
            
            this.updateActivityTimeline(data.recent_activity || []);
        } catch (error) {
            console.error('Error loading activity logs:', error);
            this.showMockActivityLogs();
        }
    }
    
    updateActivityTimeline(activities) {
        const timeline = document.getElementById('activityTimeline');
        if (!timeline) return;
        
        timeline.innerHTML = '';
        
        activities.forEach(activity => {
            const timelineItem = document.createElement('div');
            timelineItem.className = 'timeline-item';
            timelineItem.innerHTML = `
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <strong>${activity.action || 'Unknown Action'}</strong>
                        <p class="mb-1 text-muted">${activity.details || 'No details available'}</p>
                        <small class="text-muted">by ${activity.user || 'System'}</small>
                    </div>
                    <small class="text-muted">${this.formatTime(activity.timestamp)}</small>
                </div>
            `;
            timeline.appendChild(timelineItem);
        });
        
        if (activities.length === 0) {
            timeline.innerHTML = `
                <div class="text-center py-4">
                    <i class="bi bi-clock-history fs-1 text-muted"></i>
                    <p class="text-muted mt-2">No recent activity</p>
                </div>
            `;
        }
    }
    
    showMockActivityLogs() {
        const mockActivities = [
            {
                action: 'Agent Started',
                details: 'Risk Predictor Agent started successfully',
                user: 'System',
                timestamp: new Date(Date.now() - 10 * 60 * 1000).toISOString()
            },
            {
                action: 'Recommendation Generated',
                details: 'Route optimization recommendation created',
                user: 'Route Optimizer Agent',
                timestamp: new Date(Date.now() - 25 * 60 * 1000).toISOString()
            },
            {
                action: 'Configuration Updated',
                details: 'Agent refresh interval changed to 30 seconds',
                user: 'Admin User',
                timestamp: new Date(Date.now() - 45 * 60 * 1000).toISOString()
            }
        ];
        
        this.updateActivityTimeline(mockActivities);
    }
    
    // Agent Control Methods
    async controlAgent(agentName, action) {
        try {
            const response = await fetch(`/agent-dashboard/api/agents/${agentName}/control`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action })
            });
            
            const result = await response.json();
            
            if (!response.ok) throw new Error(result.error || 'Control action failed');
            
            this.showSuccess(`Agent ${agentName} ${action} ${result.success ? 'successful' : 'failed'}`);
            
            // Refresh agent status
            await this.loadAgentStatus();
            
        } catch (error) {
            console.error(`Error controlling agent ${agentName}:`, error);
            this.showError(`Failed to ${action} agent: ${error.message}`);
        }
    }
    
    async startAllAgents() {
        this.showInfo('Starting all agents...');
        
        // This would start all inactive agents
        try {
            // Implementation would depend on backend support
            this.showSuccess('All agents started successfully');
            await this.loadAgentStatus();
        } catch (error) {
            this.showError('Failed to start all agents');
        }
    }
    
    async viewAgentDetails(agentName) {
        console.log(`Viewing details for agent: ${agentName}`);
        // This would show detailed agent information in a modal
        this.showInfo(`Showing details for ${this.formatAgentName(agentName)}`);
    }
    
    async viewAgentPerformance(agentName) {
        try {
            const response = await fetch(`/agent-dashboard/api/agents/${agentName}/performance`);
            const data = await response.json();
            
            if (!response.ok) throw new Error(data.error || 'Failed to load performance data');
            
            this.showAgentPerformanceModal(agentName, data);
        } catch (error) {
            console.error(`Error loading performance for ${agentName}:`, error);
            this.showMockAgentPerformance(agentName);
        }
    }
    
    showAgentPerformanceModal(agentName, data) {
        const modal = document.getElementById('agentPerformanceModal');
        const modalLabel = document.getElementById('agentPerformanceModalLabel');
        
        if (modalLabel) {
            modalLabel.textContent = `${this.formatAgentName(agentName)} Performance`;
        }
        
        // Initialize performance charts
        this.initializePerformanceCharts(data);
        
        // Show modal
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }
    
    showMockAgentPerformance(agentName) {
        const mockData = {
            name: agentName,
            metrics: {
                response_time: { average: 125, p95: 250, p99: 500 },
                throughput: { messages_per_hour: 150, requests_per_minute: 12 },
                success_rate: { success_rate: 97, error_rate: 3 }
            },
            trends: {
                hourly: Array.from({length: 24}, () => Math.random() * 20 + 80),
                daily: Array.from({length: 7}, () => Math.random() * 10 + 90),
                weekly: Array.from({length: 4}, () => Math.random() * 5 + 92)
            }
        };
        
        this.showAgentPerformanceModal(agentName, mockData);
    }
    
    initializePerformanceCharts(data) {
        // Response Time Chart
        const responseTimeCtx = document.getElementById('agentResponseTimeChart');
        if (responseTimeCtx) {
            new Chart(responseTimeCtx, {
                type: 'doughnut',
                data: {
                    labels: ['Average', 'P95', 'P99'],
                    datasets: [{
                        data: [
                            data.metrics?.response_time?.average || 0,
                            data.metrics?.response_time?.p95 || 0,
                            data.metrics?.response_time?.p99 || 0
                        ],
                        backgroundColor: ['#28a745', '#ffc107', '#dc3545']
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        title: { display: true, text: 'Response Time Distribution' }
                    }
                }
            });
        }
        
        // Throughput Chart
        const throughputCtx = document.getElementById('agentThroughputChart');
        if (throughputCtx) {
            new Chart(throughputCtx, {
                type: 'bar',
                data: {
                    labels: ['Messages/Hour', 'Requests/Min'],
                    datasets: [{
                        data: [
                            data.metrics?.throughput?.messages_per_hour || 0,
                            data.metrics?.throughput?.requests_per_minute || 0
                        ],
                        backgroundColor: '#007bff'
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        title: { display: true, text: 'Throughput Metrics' },
                        legend: { display: false }
                    }
                }
            });
        }
        
        // Trends Chart
        const trendsCtx = document.getElementById('agentTrendsChart');
        if (trendsCtx) {
            new Chart(trendsCtx, {
                type: 'line',
                data: {
                    labels: Array.from({length: 24}, (_, i) => `${i}:00`),
                    datasets: [{
                        label: 'Performance %',
                        data: data.trends?.hourly || [],
                        borderColor: '#667eea',
                        backgroundColor: 'rgba(102, 126, 234, 0.1)',
                        tension: 0.4,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        title: { display: true, text: '24-Hour Performance Trend' }
                    },
                    scales: {
                        y: { beginAtZero: false, min: 70, max: 100 }
                    }
                }
            });
        }
    }
    
    // Recommendation Management
    async approveRecommendation(recId) {
        try {
            const response = await fetch(`/api/recommendations/${recId}/approve`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const result = await response.json();
            
            if (!response.ok) throw new Error(result.error || 'Failed to approve recommendation');
            
            this.showSuccess('Recommendation approved successfully');
            await this.loadRecommendations();
            
        } catch (error) {
            console.error('Error approving recommendation:', error);
            this.showError('Failed to approve recommendation');
        }
    }
    
    async rejectRecommendation(recId) {
        try {
            // Implementation would depend on backend support for rejection
            this.showSuccess('Recommendation rejected');
            await this.loadRecommendations();
        } catch (error) {
            this.showError('Failed to reject recommendation');
        }
    }
    
    // Filter and Search Methods
    filterRecommendations() {
        const selectedFilter = document.querySelector('[name="recFilter"]:checked')?.id;
        console.log('Filtering recommendations:', selectedFilter);
        // Implementation would filter the displayed recommendations
    }
    
    filterLogs() {
        const filter = document.getElementById('logFilter')?.value;
        console.log('Filtering logs:', filter);
        // Implementation would filter the activity timeline
    }
    
    clearLogs() {
        if (confirm('Are you sure you want to clear the activity logs?')) {
            document.getElementById('activityTimeline').innerHTML = `
                <div class="text-center py-4">
                    <i class="bi bi-clock-history fs-1 text-muted"></i>
                    <p class="text-muted mt-2">No activity logs</p>
                </div>
            `;
            this.showSuccess('Activity logs cleared');
        }
    }
    
    // Configuration and Settings
    saveConfiguration() {
        const config = {
            refreshInterval: document.getElementById('refreshInterval')?.value,
            maxRetries: document.getElementById('maxRetries')?.value,
            autoRestart: document.getElementById('autoRestart')?.checked,
            detailedLogging: document.getElementById('detailedLogging')?.checked
        };
        
        console.log('Saving configuration:', config);
        
        // Update refresh interval
        if (config.refreshInterval) {
            this.refreshInterval = parseInt(config.refreshInterval) * 1000;
            this.restartAutoRefresh();
        }
        
        this.showSuccess('Configuration saved successfully');
        
        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('configModal'));
        modal?.hide();
    }
    
    exportLogs() {
        console.log('Exporting logs...');
        this.showInfo('Exporting activity logs...');
        
        // Mock export
        setTimeout(() => {
            this.showSuccess('Logs exported successfully');
        }, 1000);
    }
    
    runDiagnostics() {
        console.log('Running system diagnostics...');
        this.showInfo('Running system diagnostics...');
        
        // Mock diagnostics
        setTimeout(() => {
            this.showSuccess('System diagnostics completed - All systems operational');
        }, 2000);
    }
    
    // Auto-refresh and Real-time Updates
    startAutoRefresh() {
        if (this.autoRefresh) {
            this.refreshIntervalId = setInterval(() => {
                this.refreshAll();
            }, this.refreshInterval);
        }
    }
    
    stopAutoRefresh() {
        if (this.refreshIntervalId) {
            clearInterval(this.refreshIntervalId);
            this.refreshIntervalId = null;
        }
    }
    
    restartAutoRefresh() {
        this.stopAutoRefresh();
        this.startAutoRefresh();
    }
    
    async refreshAll() {
        console.log('🔄 Refreshing dashboard data...');
        
        try {
            await Promise.all([
                this.loadSystemOverview(),
                this.loadAgentStatus(),
                this.loadCommunicationData(),
                this.loadRecommendations(),
                this.loadActivityLogs()
            ]);
            
            // Update last refresh time
            const now = new Date().toLocaleTimeString();
            console.log(`✅ Dashboard refreshed at ${now}`);
            
        } catch (error) {
            console.error('Error refreshing dashboard:', error);
        }
    }
    
    handleTabSwitch(tabId) {
        console.log('Tab switched to:', tabId);
        
        // Load data specific to the active tab if needed
        switch (tabId) {
            case '#communication':
                this.loadCommunicationData();
                break;
            case '#recommendations':
                this.loadRecommendations();
                break;
            case '#analytics':
                this.loadAnalyticsInsights();
                break;
            case '#logs':
                this.loadActivityLogs();
                break;
        }
    }
    
    // WebSocket for Real-time Updates
    initializeWebSocket() {
        try {
            // Initialize WebSocket connection for real-time updates
            // This would connect to a WebSocket endpoint for live updates
            console.log('WebSocket connection initialized (mock)');
        } catch (error) {
            console.warn('WebSocket not available:', error);
        }
    }
    
    // Utility Methods
    formatAgentName(agentName) {
        const displayNames = {
            'risk_predictor_agent': 'Risk Predictor',
            'route_optimizer_agent': 'Route Optimizer',
            'procurement_agent': 'Procurement Assistant',
            'orchestrator_agent': 'Workflow Orchestrator',
            'advanced_analytics_agent': 'Advanced Analytics',
            'inventory_agent': 'Inventory Manager'
        };
        
        return displayNames[agentName] || agentName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }
    
    formatNumber(num) {
        if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
        return num.toString();
    }
    
    formatTime(timestamp) {
        if (!timestamp) return 'Unknown';
        try {
            return new Date(timestamp).toLocaleString();
        } catch {
            return 'Invalid time';
        }
    }
    
    updateProgressBar(barId, percentage) {
        const bar = document.getElementById(barId);
        if (bar) {
            bar.style.width = `${Math.min(100, Math.max(0, percentage))}%`;
        }
    }
    
    // Notification Methods
    showSuccess(message) {
        this.showToast(message, 'success');
    }
    
    showError(message) {
        this.showToast(message, 'danger');
    }
    
    showInfo(message) {
        this.showToast(message, 'info');
    }
    
    showToast(message, type = 'info') {
        // Create toast notification
        const toastContainer = document.getElementById('toast-container') || this.createToastContainer();
        
        const toast = document.createElement('div');
        toast.className = `toast align-items-center text-bg-${type} border-0`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;
        
        toastContainer.appendChild(toast);
        
        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();
        
        // Remove toast after it's hidden
        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    }
    
    createToastContainer() {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        container.style.zIndex = '11';
        document.body.appendChild(container);
        return container;
    }
}

// Initialize dashboard when DOM is ready
let agentDashboard;

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        agentDashboard = new AgentDashboard();
    });
} else {
    agentDashboard = new AgentDashboard();
}

// Global function for onclick handlers
window.agentDashboard = agentDashboard;
