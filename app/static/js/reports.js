// Reports page functionality

let charts = {
    deliveryTrend: null,
    costAvoidance: null,
    emissions: null,
    mttr: null,
    agentPerformance: null
};

document.addEventListener('DOMContentLoaded', function() {
    initializeCharts();
    initializeFilters();
    loadReportData();
});

function initializeCharts() {
    // ...existing code...
    
    // Agent Performance
    const agentCtx = document.getElementById('agentPerformanceChart').getContext('2d');
    charts.agentPerformance = new Chart(agentCtx, {
        type: 'radar',
        data: {
            labels: ['Accuracy', 'Speed', 'Cost Savings', 'Risk Reduction', 'User Satisfaction'],
            datasets: [{
                label: 'Risk Predictor',
                data: [],
                borderColor: 'rgb(255, 99, 132)',
                backgroundColor: 'rgba(255, 99, 132, 0.2)'
            }, {
                label: 'Route Optimizer',
                data: [],
                borderColor: 'rgb(54, 162, 235)',
                backgroundColor: 'rgba(54, 162, 235, 0.2)'
            }, {
                label: 'Procurement Agent',
                data: [],
                borderColor: 'rgb(255, 206, 86)',
                backgroundColor: 'rgba(255, 206, 86, 0.2)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                r: {
                    beginAtZero: true,
                    max: 100
                }
            }
        }
    });
}

function initializeFilters() {
    // Date range selector
    document.getElementById('dateRange').addEventListener('change', function() {
        if (this.value === 'custom') {
            showCustomDatePicker();
        } else {
            loadReportData();
        }
    });
    
    // Compare option
    document.getElementById('compareOption').addEventListener('change', loadReportData);
}

async function loadReportData() {
    try {
        const dateRange = document.getElementById('dateRange').value;
        const compare = document.getElementById('compareOption').value;
        
        const params = new URLSearchParams({
            range: dateRange,
            compare: compare
        });
        
        const response = await fetch(`/api/reports/data?${params}`);
        const data = await response.json();
        
        updateCharts(data);
        updateKPICards(data.kpis);
        updateDecisionQueue(data.pending_decisions);
        
    } catch (error) {
        console.error('Error loading report data:', error);
        showToast('Error', 'Failed to load report data', 'error');
    }
}

function updateCharts(data) {
    // Update delivery trend
    if (charts.deliveryTrend && data.deliveryTrend) {
        charts.deliveryTrend.data.labels = data.deliveryTrend.labels;
        charts.deliveryTrend.data.datasets[0].data = data.deliveryTrend.values;
        charts.deliveryTrend.data.datasets[1].data = Array(data.deliveryTrend.labels.length).fill(95); // Target line
        charts.deliveryTrend.update();
    }
    
    // Update cost avoidance
    if (charts.costAvoidance && data.costAvoidance) {
        charts.costAvoidance.data.datasets[0].data = data.costAvoidance.values;
        charts.costAvoidance.update();
    }
    
    // Update emissions
    if (charts.emissions && data.emissions) {
        charts.emissions.data.labels = data.emissions.labels;
        charts.emissions.data.datasets[0].data = data.emissions.values;
        charts.emissions.update();
    }
    
    // Update MTTR
    if (charts.mttr && data.mttr) {
        charts.mttr.data.datasets[0].data = data.mttr.values;
        charts.mttr.update();
    }
    
    // Update agent performance
    if (charts.agentPerformance && data.agentPerformance) {
        data.agentPerformance.forEach((agent, index) => {
            charts.agentPerformance.data.datasets[index].data = agent.scores;
        });
        charts.agentPerformance.update();
    }
}

function updateKPICards(kpis) {
    // Update on-time delivery
    const deliveryCard = document.querySelector('[data-kpi="on-time-delivery"]');
    if (deliveryCard) {
        deliveryCard.querySelector('.kpi-value').textContent = `${kpis.on_time_delivery_rate}%`;
        const trend = deliveryCard.querySelector('.kpi-trend');
        trend.className = `kpi-trend text-${kpis.on_time_trend > 0 ? 'success' : 'danger'}`;
        trend.innerHTML = `<i class="bi bi-arrow-${kpis.on_time_trend > 0 ? 'up' : 'down'}"></i> ${Math.abs(kpis.on_time_trend)}%`;
    }
    
    // Update cost avoidance
    const costCard = document.querySelector('[data-kpi="cost-avoidance"]');
    if (costCard) {
        costCard.querySelector('.kpi-value').textContent = `$${formatCurrency(kpis.cost_avoided)}`;
        costCard.querySelector('.kpi-subtitle').textContent = `From ${kpis.reroutes_count} optimized routes`;
    }
    
    // Update emissions saved
    const emissionsCard = document.querySelector('[data-kpi="emissions-saved"]');
    if (emissionsCard) {
        emissionsCard.querySelector('.kpi-value').textContent = `${formatNumber(kpis.emissions_saved)} kg`;
        emissionsCard.querySelector('.kpi-subtitle').textContent = `${kpis.emissions_reduction_pct}% reduction`;
    }
    
    // Update response time
    const responseCard = document.querySelector('[data-kpi="response-time"]');
    if (responseCard) {
        responseCard.querySelector('.kpi-value').textContent = `${kpis.avg_response_time} min`;
        const badge = responseCard.querySelector('.kpi-badge');
        badge.className = `badge bg-${kpis.avg_response_time < 30 ? 'success' : 'warning'}`;
        badge.textContent = kpis.avg_response_time < 30 ? 'On Target' : 'Above Target';
    }
}

function updateDecisionQueue(decisions) {
    const container = document.getElementById('decisionQueue');
    if (!container) return;
    
    if (decisions.length === 0) {
        container.innerHTML = '<p class="text-muted text-center mb-0">No pending decisions</p>';
        return;
    }
    
    container.innerHTML = decisions.map(rec => `
        <div class="alert alert-${rec.severity === 'high' ? 'danger' : 'warning'} d-flex justify-content-between align-items-center">
            <div>
                <strong>${rec.type}:</strong> ${rec.title}
                <br>
                <small class="text-muted">${formatDateTime(rec.created_at)} - Confidence: ${(rec.confidence * 100).toFixed(0)}%</small>
            </div>
            <div>
                <button class="btn btn-sm btn-outline-primary" onclick="explainRecommendation(${rec.id})">
                    Explain
                </button>
                <button class="btn btn-sm btn-success" onclick="approveRecommendation(${rec.id})">
                    Approve
                </button>
                <button class="btn btn-sm btn-outline-secondary" onclick="deferRecommendation(${rec.id})">
                    Defer
                </button>
            </div>
        </div>
    `).join('');
}

function showCustomDatePicker() {
    const modal = new bootstrap.Modal(document.getElementById('customDateModal'));
    modal.show();
}

function applyCustomDateRange() {
    const startDate = document.getElementById('customStartDate').value;
    const endDate = document.getElementById('customEndDate').value;
    
    if (startDate && endDate) {
        // Store custom range and reload data
        window.customDateRange = { start: startDate, end: endDate };
        loadReportData();
        bootstrap.Modal.getInstance(document.getElementById('customDateModal')).hide();
    }
}

function exportReport(format) {
    const dateRange = document.getElementById('dateRange').value;
    const params = new URLSearchParams({
        range: dateRange,
        format: format
    });
    
    // If custom date range, add those parameters
    if (dateRange === 'custom' && window.customDateRange) {
        params.append('start_date', window.customDateRange.start);
        params.append('end_date', window.customDateRange.end);
    }
    
    window.location.href = `/api/reports/export?${params}`;
}

function applyReportFilters() {
    // Get selected filters from modal
    const form = document.getElementById('filterForm');
    const formData = new FormData(form);
    
    // Store filters
    window.reportFilters = {
        regions: Array.from(formData.getAll('regions')),
        carriers: Array.from(formData.getAll('carriers'))
    };
    
    // Close modal and reload data
    bootstrap.Modal.getInstance(document.getElementById('filterModal')).hide();
    loadReportData();
}

async function deferRecommendation(id) {
    try {
        const response = await fetch(`/api/recommendations/${id}/defer`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                reason: 'Deferred for review',
                defer_until: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString() // 24 hours
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('Success', 'Recommendation deferred', 'info');
            loadReportData();
        } else {
            showToast('Error', data.message || 'Failed to defer recommendation', 'error');
        }
        
    } catch (error) {
        console.error('Error deferring recommendation:', error);
        showToast('Error', 'Failed to defer recommendation', 'error');
    }
}

// Utility functions
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(amount);
}

function formatNumber(num) {
    return new Intl.NumberFormat('en-US').format(num);
}

function formatDateTime(dateString) {
    return new Date(dateString).toLocaleString();
}

// Auto-refresh data every 5 minutes
setInterval(() => {
    if (document.visibilityState === 'visible') {
        loadReportData();
    }
}, 5 * 60 * 1000);

// WebSocket updates for real-time KPIs
if (window.socket) {
    window.socket.on('kpi_updated', (data) => {
        // Update specific KPI without full reload
        updateKPICards(data);
    });
    
    window.socket.on('decision_required', (data) => {
        // Add new decision to queue
        const container = document.getElementById('decisionQueue');
        if (container && container.querySelector('.text-muted')) {
            // Replace "no decisions" message
            updateDecisionQueue([data]);
        } else {
            // Prepend to existing decisions
            const newDecision = document.createElement('div');
            newDecision.innerHTML = `
                <div class="alert alert-${data.severity === 'high' ? 'danger' : 'warning'} d-flex justify-content-between align-items-center">
                    <div>
                        <strong>${data.type}:</strong> ${data.title}
                        <br>
                        <small class="text-muted">Just now - Confidence: ${(data.confidence * 100).toFixed(0)}%</small>
                    </div>
                    <div>
                        <button class="btn btn-sm btn-outline-primary" onclick="explainRecommendation(${data.id})">
                            Explain
                        </button>
                        <button class="btn btn-sm btn-success" onclick="approveRecommendation(${data.id})">
                            Approve
                        </button>
                        <button class="btn btn-sm btn-outline-secondary" onclick="deferRecommendation(${data.id})">
                            Defer
                        </button>
                    </div>
                </div>
            `;
            container.insertBefore(newDecision.firstElementChild, container.firstChild);
        }
    });
}