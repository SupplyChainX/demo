// Main Dashboard JavaScript

// Global variables
let riskHeatmap = null;
let etaChart = null;
let socket = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeSocket();
    initializeHeatmap();
    initializeCharts();
    loadDashboardData();
    
    // Refresh data periodically
    setInterval(refreshDashboard, 30000); // 30 seconds
});

// Socket.IO initialization
function initializeSocket() {
    socket = io();
    
    socket.on('connect', function() {
        console.log('Connected to server');
        showToast('Connected to real-time updates', 'success');
    });
    
    socket.on('disconnect', function() {
        console.log('Disconnected from server');
        showToast('Disconnected from real-time updates', 'warning');
    });
    
    // Real-time event handlers
    socket.on('alert_created', function(data) {
        updateAlertCount(data.total_count);
        addAlertToTimeline(data.alert);
        showToast(`New Alert: ${data.alert.title}`, 'warning');
    });
    
    socket.on('shipment_updated', function(data) {
        updateShipmentTable(data.shipment);
        if (data.risk_changed) {
            updateRiskMetrics();
        }
    });
    
    socket.on('recommendation_ready', function(data) {
        addRecommendationCard(data.recommendation);
        showToast('New recommendation available', 'info');
    });
    
    socket.on('kpi_update', function(data) {
        updateKPICards(data);
    });
}

// Initialize disruption heatmap
function initializeHeatmap() {
    // Create Leaflet map
    riskHeatmap = L.map('disruptionMap').setView([20, 0], 2);
    
    // Add tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(riskHeatmap);
    
    // Load risk data
    loadRiskHeatmapData();
}

// Load risk heatmap data
function loadRiskHeatmapData() {
    fetch('/api/risks/heatmap')
        .then(response => response.json())
        .then(data => {
            // Clear existing layers
            riskHeatmap.eachLayer(layer => {
                if (layer instanceof L.Circle || layer instanceof L.Marker) {
                    riskHeatmap.removeLayer(layer);
                }
            });
            
            // Add risk zones
            data.risks.forEach(risk => {
                const color = getRiskColor(risk.severity);
                const radius = risk.affected_radius_km * 1000; // Convert to meters
                
                L.circle([risk.lat, risk.lon], {
                    color: color,
                    fillColor: color,
                    fillOpacity: 0.3,
                    radius: radius,
                    weight: 2
                })
                .bindPopup(`
                    <strong>${risk.title}</strong><br>
                    Type: ${risk.type}<br>
                    Severity: ${risk.severity}<br>
                    Affected: ${risk.affected_count} shipments
                `)
                .addTo(riskHeatmap);
            });
            
            // Add affected shipments
            data.affected_shipments.forEach(shipment => {
                const icon = L.divIcon({
                    html: `<i class="bi bi-box-seam-fill text-${getRiskClass(shipment.risk_score)}"></i>`,
                    iconSize: [20, 20],
                    className: 'custom-div-icon'
                });
                
                L.marker([shipment.lat, shipment.lon], { icon })
                    .bindPopup(`
                        <strong>${shipment.tracking_number}</strong><br>
                        Risk: ${(shipment.risk_score * 100).toFixed(0)}%<br>
                        <a href="/shipments/${shipment.id}">View Details</a>
                    `)
                    .addTo(riskHeatmap);
            });
        })
        .catch(error => {
            console.error('Error loading heatmap data:', error);
            showToast('Failed to load risk data', 'error');
        });
}

// Initialize charts
function initializeCharts() {
    // ETA Variance Chart
    const ctx = document.getElementById('etaVarianceChart').getContext('2d');
    etaChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Planned ETA',
                data: [],
                borderColor: '#0066cc',
                backgroundColor: 'rgba(0, 102, 204, 0.1)',
                tension: 0.1
            }, {
                label: 'Actual/Predicted ETA',
                data: [],
                borderColor: '#ff6b6b',
                backgroundColor: 'rgba(255, 107, 107, 0.1)',
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: 'ETA Variance (Last 14 Days)'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Days from Origin'
                    }
                }
            }
        }
    });
}

// Load dashboard data
function loadDashboardData() {
    // Load KPIs
    fetch('/api/kpis')
        .then(response => response.json())
        .then(data => updateKPICards(data))
        .catch(error => console.error('Error loading KPIs:', error));
    
    // Load shipments at risk
    fetch('/api/shipments/at-risk')
        .then(response => response.json())
        .then(data => updateShipmentsAtRisk(data))
        .catch(error => console.error('Error loading shipments:', error));
    
    // Load recommendations (paginated API endpoint)
    fetch('/api/recommendations?page=1&per_page=10&include_xai=0')
        .then(response => response.json())
        .then(payload => {
            const recs = payload.recommendations || [];
            updateRecommendations({ recommendations: recs });
        })
        .catch(error => console.error('Error loading recommendations:', error));
    
    // Load ETA variance data
    fetch('/api/analytics/eta-variance')
        .then(response => response.json())
        .then(data => updateETAChart(data))
        .catch(error => console.error('Error loading ETA data:', error));
}

// Update KPI cards
function updateKPICards(data) {
    // Global Risk Index
    const riskProgress = document.querySelector('#globalRiskIndex .progress-bar');
    const riskValue = document.querySelector('#globalRiskValue');
    if (riskProgress && riskValue) {
        const riskPercent = (data.global_risk_index * 100).toFixed(0);
        riskProgress.style.width = `${riskPercent}%`;
        riskProgress.className = `progress-bar bg-${getRiskClass(data.global_risk_index)}`;
        riskValue.textContent = data.global_risk_index.toFixed(2);
        
        // Add trend indicator
        const trend = data.risk_trend || 0;
        const trendIcon = trend > 0 ? '↗' : trend < 0 ? '↘' : '→';
        riskValue.innerHTML += ` <small class="${trend > 0 ? 'text-danger' : 'text-success'}">${trendIcon}</small>`;
    }
    
    // On-time Deliveries
    const ontimeElement = document.querySelector('#ontimeDeliveries');
    if (ontimeElement) {
        ontimeElement.textContent = `${data.ontime_percentage}%`;
        
        // Add color based on performance
        const badge = ontimeElement.closest('.card');
        if (badge) {
            badge.classList.remove('border-success', 'border-warning', 'border-danger');
            if (data.ontime_percentage >= 95) {
                badge.classList.add('border-success');
            } else if (data.ontime_percentage >= 90) {
                badge.classList.add('border-warning');
            } else {
                badge.classList.add('border-danger');
            }
        }
    }
    
    // Open Alerts
    const alertsElement = document.querySelector('#openAlerts');
    if (alertsElement) {
        alertsElement.textContent = data.open_alerts_count;
        
        // Add badge for critical alerts
        if (data.critical_alerts_count > 0) {
            alertsElement.innerHTML += ` <span class="badge bg-danger">${data.critical_alerts_count} critical</span>`;
        }
    }
    
    // Inventory at Risk
    const inventoryElement = document.querySelector('#inventoryAtRisk');
    if (inventoryElement) {
        inventoryElement.textContent = `${data.inventory_at_risk_count} SKUs`;
        
        // Add tooltip with details
        inventoryElement.setAttribute('data-bs-toggle', 'tooltip');
        inventoryElement.setAttribute('data-bs-title', `${data.inventory_value_at_risk} value at risk`);
    }
}

// Update shipments at risk table
function updateShipmentsAtRisk(data) {
    const tbody = document.querySelector('#shipmentsAtRiskTable tbody');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    
    data.shipments.forEach((shipment, index) => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${index + 1}</td>
            <td><a href="/shipments/${shipment.id}">${shipment.tracking_number}</a></td>
            <td>${shipment.origin} → ${shipment.destination}</td>
            <td>${formatDate(shipment.eta)}</td>
            <td>
                <span class="badge bg-${getRiskClass(shipment.risk_score)}">
                    ${getRiskLabel(shipment.risk_score)}
                </span>
            </td>
            <td><span class="badge bg-secondary">${shipment.risk_cause}</span></td>
            <td>
                <button class="btn btn-sm btn-outline-primary" onclick="viewShipment(${shipment.id})">
                    View
                </button>
                <button class="btn btn-sm btn-primary" onclick="rerouteShipment(${shipment.id})">
                    Re-route
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });
    
    // Show empty state if no shipments
    if (data.shipments.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center text-muted py-4">
                    <i class="bi bi-check-circle display-4"></i>
                    <p class="mt-2">No shipments at risk</p>
                </td>
            </tr>
        `;
    }
}

// Update recommendations
function updateRecommendations(data) {
    const container = document.querySelector('#recommendationsContainer');
    if (!container) return;
    
    container.innerHTML = '';
    
    data.recommendations.forEach(rec => {
        const card = createRecommendationCard(rec);
        container.appendChild(card);
    });
    
    // Show empty state if no recommendations
    if (data.recommendations.length === 0) {
        container.innerHTML = `
            <div class="text-center text-muted py-5">
                <i class="bi bi-lightbulb display-4"></i>
                <p class="mt-2">No pending recommendations</p>
            </div>
        `;
    }
}

// Create recommendation card
function createRecommendationCard(rec) {
    const card = document.createElement('div');
    card.className = 'card mb-3';
    card.innerHTML = `
        <div class="card-body">
            <div class="d-flex justify-content-between align-items-start">
                <div>
                    <h6 class="card-title mb-1">
                        <i class="bi bi-${getRecommendationIcon(rec.type)} me-2"></i>
                        ${rec.title}
                    </h6>
                    <p class="card-text">${rec.description}</p>
                    <small class="text-muted">
                        By ${rec.created_by} • ${formatTimeAgo(rec.created_at)}
                    </small>
                </div>
                <span class="badge bg-${getSeverityClass(rec.severity)}">${rec.severity}</span>
            </div>
            <div class="mt-3">
                <button class="btn btn-sm btn-outline-primary" onclick="explainRecommendation(${rec.id})">
                    <i class="bi bi-info-circle"></i> Explain
                </button>
                <button class="btn btn-sm btn-success" onclick="approveRecommendation(${rec.id})">
                    <i class="bi bi-check"></i> Approve
                </button>
                <button class="btn btn-sm btn-outline-secondary" onclick="editRecommendation(${rec.id})">
                    <i class="bi bi-pencil"></i> Edit
                </button>
            </div>
        </div>
    `;
    return card;
}

// Update ETA chart
function updateETAChart(data) {
    if (!etaChart) return;
    
    etaChart.data.labels = data.dates;
    etaChart.data.datasets[0].data = data.planned_etas;
    etaChart.data.datasets[1].data = data.actual_etas;
    etaChart.update();
}

// Action handlers
function viewShipment(id) {
    window.location.href = `/shipments/${id}`;
}

function rerouteShipment(id) {
    window.location.href = `/shipments/${id}#reroute`;
}

function explainRecommendation(id) {
    fetch(`/api/recommendations/${id}/explain`)
        .then(response => response.json())
        .then(data => {
            showExplanationModal(data);
        })
        .catch(error => {
            console.error('Error fetching explanation:', error);
            showToast('Failed to load explanation', 'error');
        });
}

function approveRecommendation(id) {
    if (!confirm('Are you sure you want to approve this recommendation?')) {
        return;
    }
    
    fetch(`/api/recommendations/${id}/approve`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Recommendation approved', 'success');
            loadDashboardData(); // Refresh
        } else {
            showToast(data.error || 'Failed to approve', 'error');
        }
    })
    .catch(error => {
        console.error('Error approving recommendation:', error);
        showToast('Failed to approve recommendation', 'error');
    });
}

// Utility functions
function getRiskColor(severity) {
    switch(severity) {
        case 'HIGH': return '#dc3545';
        case 'MEDIUM': return '#ffc107';
        case 'LOW': return '#28a745';
        default: return '#6c757d';
    }
}

function getRiskClass(riskScore) {
    if (riskScore >= 0.7) return 'danger';
    if (riskScore >= 0.4) return 'warning';
    return 'success';
}

function getRiskLabel(riskScore) {
    if (riskScore >= 0.7) return 'High';
    if (riskScore >= 0.4) return 'Med';
    return 'Low';
}

function getSeverityClass(severity) {
    switch(severity) {
        case 'HIGH': return 'danger';
        case 'MEDIUM': return 'warning';
        case 'LOW': return 'info';
        default: return 'secondary';
    }
}

function getRecommendationIcon(type) {
    switch(type) {
        case 'REROUTE': return 'shuffle';
        case 'REORDER': return 'cart-plus';
        case 'NEGOTIATE': return 'currency-dollar';
        case 'HOLD': return 'pause-circle';
        default: return 'lightbulb';
    }
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatTimeAgo(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);
    
    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} hr ago`;
    return `${Math.floor(seconds / 86400)} days ago`;
}

function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.content;
    
    const cookie = document.cookie.split('; ').find(row => row.startsWith('csrf_token='));
    return cookie ? cookie.split('=')[1] : '';
}

function showToast(message, type = 'info') {
    const toastHtml = `
        <div class="toast align-items-center text-white bg-${type === 'error' ? 'danger' : type} border-0" 
             role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" 
                        data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;
    
    const toastContainer = document.getElementById('toastContainer') || createToastContainer();
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    
    const toastElement = toastContainer.lastElementChild;
    const toast = new bootstrap.Toast(toastElement);
    toast.show();
    
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    document.body.appendChild(container);
    return container;
}

function showExplanationModal(explanation) {
    const modalHtml = `
        <div class="modal fade" id="explanationModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">AI Explanation</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <h6>Rationale</h6>
                        <p>${explanation.rationale}</p>
                        
                        <h6>Factors Considered</h6>
                        <ul>
                            ${explanation.factors.map(f => `<li>${f}</li>`).join('')}
                        </ul>
                        
                        <h6>Data Sources</h6>
                        <ul>
                            ${explanation.data_sources.map(s => `<li>${s}</li>`).join('')}
                        </ul>
                        
                        <h6>Decision Path</h6>
                        <ol>
                            ${explanation.decision_path.map(step => `<li>${step}</li>`).join('')}
                        </ol>
                        
                        <div class="mt-3">
                            <span class="badge bg-info">Confidence: ${(explanation.confidence * 100).toFixed(0)}%</span>
                            <span class="badge bg-secondary">Model: ${explanation.model}</span>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const modal = new bootstrap.Modal(document.getElementById('explanationModal'));
    modal.show();
    
    document.getElementById('explanationModal').addEventListener('hidden.bs.modal', function() {
        this.remove();
    });
}

// Refresh dashboard data
function refreshDashboard() {
    loadRiskHeatmapData();
    loadDashboardData();
}

// Initialize tooltips
var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
    return new bootstrap.Tooltip(tooltipTriggerEl);
});
