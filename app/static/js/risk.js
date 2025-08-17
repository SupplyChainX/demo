// Risk management page functionality

let riskMap = null;
let riskMarkers = [];
let currentRisks = [];

// Initialize risk page
document.addEventListener('DOMContentLoaded', function() {
    initializeRiskMap();
    loadRiskData();
    
    // Set up filters
    document.getElementById('riskTypeFilter').addEventListener('change', applyRiskFilters);
    document.getElementById('severityFilter').addEventListener('change', applyRiskFilters);
    document.getElementById('timeWindowFilter').addEventListener('change', applyRiskFilters);
});

// Initialize risk heatmap
function initializeRiskMap() {
    riskMap = L.map('riskHeatmap').setView([20, 0], 2);
    
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(riskMap);
    
    // Add heatmap layer
    // This would use a proper heatmap plugin in production
}

// Load risk data
async function loadRiskData() {
    try {
        const response = await fetch('/api/risks');
        const data = await response.json();
        
        currentRisks = data.risks;
        updateRiskMap(data.risks);
        updateRiskTimeline(data.timeline || []);
        updateRiskTable(data.risks);
        
    } catch (error) {
        console.error('Error loading risk data:', error);
        showToast('Error', 'Failed to load risk data', 'danger');
    }
}

// Update risk map
function updateRiskMap(risks) {
    // Clear existing markers
    riskMarkers.forEach(marker => riskMap.removeLayer(marker));
    riskMarkers = [];
    
    // Create heat data
    const heatData = [];
    
    risks.forEach(risk => {
        if (risk.latitude && risk.longitude) {
            // Add to heat data
            heatData.push([risk.latitude, risk.longitude, risk.severity_score]);
            
            // Create marker
            const color = getRiskColor(risk.severity);
            const marker = L.circleMarker([risk.latitude, risk.longitude], {
                radius: 10 + (risk.impact * 5),
                fillColor: color,
                color: '#fff',
                weight: 2,
                opacity: 1,
                fillOpacity: 0.8
            });
            
            marker.bindPopup(`
                <strong>${risk.type}: ${risk.title}</strong><br>
                Region: ${risk.region}<br>
                Severity: ${risk.severity}<br>
                Probability: ${(risk.probability * 100).toFixed(0)}%<br>
                <a href="/threat/${risk.id}">View Details</a>
            `);
            
            marker.addTo(riskMap);
            riskMarkers.push(marker);
        }
    });
}

// Update risk timeline
function updateRiskTimeline(timeline) {
    const container = document.getElementById('riskTimeline');
    container.innerHTML = '';
    
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', '200');
    
    // Draw timeline
    // This is a simplified version - would use D3.js in production
    
    container.appendChild(svg);
}

// Update risk table
function updateRiskTable(risks) {
    const tbody = document.querySelector('#riskTable tbody');
    tbody.innerHTML = '';
    
    risks.forEach(risk => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${risk.id}</td>
            <td>${risk.type}</td>
            <td>${risk.region}</td>
            <td>
                <span class="badge bg-${getRiskColor(risk.severity)}">
                    ${risk.severity}
                </span>
            </td>
            <td>${(risk.probability * 100).toFixed(0)}%</td>
            <td>${risk.impact}</td>
            <td>
                <span class="badge bg-${getStatusColor(risk.status)}">
                    ${risk.status}
                </span>
            </td>
            <td>
                <div class="btn-group btn-group-sm">
                    <a href="/threat/${risk.id}" class="btn btn-outline-primary">Details</a>
                    ${risk.status === 'open' ? 
                        '<button class="btn btn-outline-secondary" onclick="muteRisk(' + risk.id + ')">Mute</button>' : ''}
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });
}

// Apply risk filters
function applyRiskFilters() {
    const type = document.getElementById('riskTypeFilter').value;
    const severity = document.getElementById('severityFilter').value;
    const timeWindow = document.getElementById('timeWindowFilter').value;
    
    loadRiskData(); // In production, would pass filters to API
}

// Run risk simulation
async function runSimulation() {
    const form = document.getElementById('simulationForm');
    const formData = new FormData(form);
    
    const simulationData = {
        scenario_type: formData.get('scenario_type'),
        location: formData.get('location'),
        duration: parseInt(formData.get('duration')),
        severity: formData.get('severity')
    };
    
    try {
        const response = await fetch('/api/risks/simulate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(simulationData)
        });
        
        if (response.ok) {
            const result = await response.json();
            
            // Close modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('riskSimulationModal'));
            modal.hide();
            
            // Show results
            showSimulationResults(result);
        }
    } catch (error) {
        showToast('Error', 'Failed to run simulation', 'danger');
    }
}

// Show simulation results
function showSimulationResults(results) {
    // This would show a detailed modal with simulation results
    showToast('Simulation Complete', `Impact: ${results.impact_summary}`, 'info');
    
    // Reload risk data to show simulated risks
    loadRiskData();
}

// Export risk report
async function exportRiskReport() {
    try {
        const response = await fetch('/api/risks/export-report');
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `risk_report_${new Date().toISOString().split('T')[0]}.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
        }
    } catch (error) {
        showToast('Error', 'Failed to export report', 'danger');
    }
}

// Mute risk
async function muteRisk(riskId) {
    try {
        const response = await fetch(`/api/risks/${riskId}/mute`, {
            method: 'POST'
        });
        
        if (response.ok) {
            showToast('Success', 'Risk muted', 'success');
            loadRiskData();
        }
    } catch (error) {
        showToast('Error', 'Failed to mute risk', 'danger');
    }
}

// Helper functions
function getRiskColor(severity) {
    const colors = {
        'high': '#dc3545',
        'medium': '#ffc107',
        'low': '#28a745'
    };
    return colors[severity] || '#6c757d';
}

function getStatusColor(status) {
    const colors = {
        'open': 'danger',
        'tracking': 'warning',
        'mitigated': 'success',
        'muted': 'secondary'
    };
    return colors[status] || 'secondary';
}

// Handle real-time updates
socketIO.on('risk_detected', (data) => {
    showToast('New Risk Detected', data.title, 'warning');
    loadRiskData();
});

// Export functions
window.applyRiskFilters = applyRiskFilters;
window.runSimulation = runSimulation;
window.exportRiskReport = exportRiskReport;
window.muteRisk = muteRisk;
                            <div class="progress" style="height: 25px;">
                                <div class="progress-bar bg-danger" style="width: ${risk.probability * 100}%">
                                    ${(risk.probability * 100).toFixed(0)}%
                                </div>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <label class="text-muted">Confidence</label>
                            <div class="progress" style="height: 25px;">
                                <div class="progress-bar bg-info" style="width: ${risk.confidence * 100}%">
                                    ${(risk.confidence * 100).toFixed(0)}%
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <h6>Data Sources</h6>
                    <ul>
                        ${risk.data_sources.map(source => `<li>${source}</li>`).join('')}
                    </ul>
                    
                    <h6>Affected Entities</h6>
                    <div class="row g-2">
                        ${risk.affected_shipments ? `
                            <div class="col-md-4">
                                <div class="card">
                                    <div class="card-body">
                                        <h6 class="card-title">Shipments</h6>
                                        <p class="card-text fs-3">${risk.affected_shipments.length}</p>
                                    </div>
                                </div>
                            </div>
                        ` : ''}
                        ${risk.affected_suppliers ? `
                            <div class="col-md-4">
                                <div class="card">
                                    <div class="card-body">
                                        <h6 class="card-title">Suppliers</h6>
                                        <p class="card-text fs-3">${risk.affected_suppliers.length}</p>
                                    </div>
                                </div>
                            </div>
                        ` : ''}
                        ${risk.affected_routes ? `
                            <div class="col-md-4">
                                <div class="card">
                                    <div class="card-body">
                                        <h6 class="card-title">Routes</h6>
                                        <p class="card-text fs-3">${risk.affected_routes.length}</p>
                                    </div>
                                </div>
                            </div>
                        ` : ''}
                    </div>
                </div>
                
                <div class="col-md-4">
                    <h6>Recommendations</h6>
                    ${risk.recommendations ? risk.recommendations.map(rec => `
                        <div class="alert alert-warning">
                            <strong>${rec.type}:</strong> ${rec.description}
                            <div class="mt-2">
                                <button class="btn btn-sm btn-primary" onclick="acceptRecommendation(${rec.id})">
                                    Accept
                                </button>
                                <button class="btn btn-sm btn-outline-secondary" onclick="explainRecommendation(${rec.id})">
                                    Explain
                                </button>
                            </div>
                        </div>
                    `).join('') : '<p class="text-muted">No recommendations available</p>'}
                    
                    <h6 class="mt-3">Timeline</h6>
                    <div class="timeline-vertical">
                        ${risk.events ? risk.events.map(event => `
                            <div class="timeline-item">
                                <small class="text-muted">${formatDateTime(event.timestamp)}</small>
                                <p class="mb-0">${event.description}</p>
                            </div>
                        `).join('') : ''}
                    </div>
                </div>
            </div>
        `;
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('riskDetailModal'));
        modal.show();
        
    } catch (error) {
        console.error('Error loading risk details:', error);
        showToast('Error', 'Failed to load risk details', 'error');
    }
}

async function muteAlert(id) {
    if (confirm('Are you sure you want to mute this alert?')) {
        try {
            const response = await fetch(`/api/risks/${id}/mute`, {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (data.success) {
                showToast('Success', 'Alert muted', 'success');
                loadRisks();
            }
            
        } catch (error) {
            console.error('Error muting alert:', error);
            showToast('Error', 'Failed to mute alert', 'error');
        }
    }
}

function exportRisks() {
    const filters = getRiskFilters();
    const params = new URLSearchParams(filters);
    params.append('format', 'csv');
    
    window.location.href = '/api/risks/export?' + params;
}

function refreshRisks() {
    loadRiskHeatmapData();
    loadRisks();
    showToast('Info', 'Risk data refreshed', 'info');
}

// WebSocket updates
if (window.socket) {
    window.socket.on('alert_created', (data) => {
        // Add to timeline
        addToTimeline(data);
        
        // Refresh map and table
        loadRiskHeatmapData();
        loadRisks();
        
        // Show notification
        showToast('New Alert', data.title, 'warning');
    });
}

function addToTimeline(alert) {
    const container = document.querySelector('.timeline-container');
    if (!container) return;
    
    const timelineItem = document.createElement('div');
    timelineItem.className = 'timeline-item mx-2 text-center';
    timelineItem.style.minWidth = '120px';
    timelineItem.innerHTML = `
        <div class="timeline-marker bg-${alert.severity} rounded-circle mx-auto" 
             style="width: 12px; height: 12px;"></div>
        <small class="text-muted">${new Date().toLocaleTimeString()}</small>
        <div class="badge bg-${alert.severity}">${alert.type}</div>
        <p class="small mb-0">${alert.title.substring(0, 30)}...</p>
    `;
    
    container.insertBefore(timelineItem, container.firstChild);
    
    // Scroll to show new item
    container.scrollLeft = 0;
}

function formatDateTime(dateString) {
    return new Date(dateString).toLocaleString();
}
