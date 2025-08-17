// Alerts page functionality

let currentFilters = {
    status: 'open',
    type: '',
    severity: '',
    assignee: '',
    search: ''
};

// Initialize alerts page
document.addEventListener('DOMContentLoaded', function() {
    loadAlerts();
    
    // Set up select all checkbox
    document.getElementById('selectAll').addEventListener('change', function() {
        const checkboxes = document.querySelectorAll('#alertsTableBody input[type="checkbox"]');
        checkboxes.forEach(cb => cb.checked = this.checked);
    });
    
    // Set up search
    document.getElementById('searchAlerts').addEventListener('keyup', debounce(function() {
        currentFilters.search = this.value;
        loadAlerts();
    }, 300));
});

// Load alerts
async function loadAlerts() {
    try {
        const params = new URLSearchParams(currentFilters);
        const response = await fetch(`/api/alerts?${params}`);
        const data = await response.json();
        
        updateAlertsTable(data.alerts);
        
    } catch (error) {
        console.error('Error loading alerts:', error);
        showToast('Error', 'Failed to load alerts', 'danger');
    }
}

// Update alerts table
function updateAlertsTable(alerts) {
    const tbody = document.getElementById('alertsTableBody');
    tbody.innerHTML = '';
    
    if (alerts.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="text-center py-4 text-muted">
                    <i class="bi bi-inbox fs-1"></i><br>
                    No alerts found
                </td>
            </tr>
        `;
        return;
    }
    
    alerts.forEach(alert => {
        const row = document.createElement('tr');
        row.className = alert.is_read ? '' : 'fw-bold';
        
        const slaClass = getSLAClass(alert.created_at, alert.sla_hours);
        
        row.innerHTML = `
            <td>
                <input class="form-check-input" type="checkbox" value="${alert.id}">
            </td>
            <td>${alert.id}</td>
            <td>
                <a href="/alerts/${alert.id}" class="text-decoration-none">
                    ${alert.title}
                </a>
            </td>
            <td>
                <span class="badge bg-${getSeverityColor(alert.severity)}">
                    ${alert.severity}
                </span>
            </td>
            <td>${alert.affects}</td>
            <td>${formatRelativeTime(alert.created_at)}</td>
            <td class="${slaClass}">${alert.sla_hours}h</td>
            <td>
                <span class="badge bg-${getStatusColor(alert.status)}">
                    ${alert.status}
                </span>
            </td>
            <td>
                <div class="btn-group btn-group-sm">
                    <a href="/alerts/${alert.id}" class="btn btn-outline-primary">Open</a>
                    ${alert.status === 'open' ? 
                        '<button class="btn btn-outline-success" onclick="acknowledgeAlert(' + alert.id + ')">Ack</button>' : ''}
                </div>
            </td>
        `;
        
        tbody.appendChild(row);
    });
}

// Apply filters
function applyFilters() {
    currentFilters.status = document.getElementById('statusFilter').value;
    currentFilters.type = document.getElementById('typeFilter').value;
    currentFilters.severity = document.getElementById('severityFilter').value;
    currentFilters.assignee = document.getElementById('assigneeFilter').value;
    
    loadAlerts();
}

// Mark all as read
async function markAllRead() {
    try {
        const response = await fetch('/api/alerts/mark-all-read', {
            method: 'POST'
        });
        
        if (response.ok) {
            showToast('Success', 'All alerts marked as read', 'success');
            loadAlerts();
        }
    } catch (error) {
        showToast('Error', 'Failed to mark alerts as read', 'danger');
    }
}

// Acknowledge alert
async function acknowledgeAlert(alertId) {
    try {
        const response = await fetch(`/api/alerts/${alertId}/acknowledge`, {
            method: 'POST'
        });
        
        if (response.ok) {
            showToast('Success', 'Alert acknowledged', 'success');
            loadAlerts();
        }
    } catch (error) {
        showToast('Error', 'Failed to acknowledge alert', 'danger');
    }
}

// Export alerts
async function exportAlerts() {
    try {
        const params = new URLSearchParams(currentFilters);
        const response = await fetch(`/api/alerts/export?${params}`);
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `alerts_${new Date().toISOString().split('T')[0]}.csv`;
            document.body.appendChild(a);
            a.click();
            a.remove();
        }
    } catch (error) {
        showToast('Error', 'Failed to export alerts', 'danger');
    }
}

// Helper functions
function getSLAClass(createdAt, slaHours) {
    const created = new Date(createdAt);
    const now = new Date();
    const hoursElapsed = (now - created) / (1000 * 60 * 60);
    
    if (hoursElapsed > slaHours) {
        return 'text-danger';
    } else if (hoursElapsed > slaHours * 0.75) {
        return 'text-warning';
    }
    return '';
}

function getSeverityColor(severity) {
    const colors = {
        'high': 'danger',
        'medium': 'warning',
        'low': 'success'
    };
    return colors[severity] || 'secondary';
}

function getStatusColor(status) {
    const colors = {
        'open': 'danger',
        'acknowledged': 'warning',
        'resolved': 'success'
    };
    return colors[status] || 'secondary';
}

function formatRelativeTime(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    return `${days}d ago`;
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Handle real-time updates
socketIO.on('alert_created', (data) => {
    loadAlerts();
});

socketIO.on('alert_updated', (data) => {
    loadAlerts();
});
    // Display recommendations
    if (alert.recommendations && alert.recommendations.length > 0) {
        displayRecommendations(alert.recommendations);
    }
}

function updateSLAProgress(alert) {
    if (!alert.sla_hours) {
        document.getElementById('slaSection').style.display = 'none';
        return;
    }
    
    const now = new Date();
    const createdAt = new Date(alert.created_at);
    const hoursElapsed = (now - createdAt) / (1000 * 60 * 60);
    const slaPct = (hoursElapsed / alert.sla_hours * 100);
    
    const progressBar = document.getElementById('slaProgress');
    const progressClass = slaPct > 100 ? 'danger' : slaPct > 80 ? 'warning' : 'success';
    
    progressBar.className = `progress-bar bg-${progressClass}`;
    progressBar.style.width = `${Math.min(slaPct, 100)}%`;
    progressBar.textContent = `${hoursElapsed.toFixed(1)}h / ${alert.sla_hours}h`;
    
    if (slaPct > 100) {
        document.getElementById('slaBreach').style.display = 'block';
    }
}

function displayRecommendations(recommendations) {
    const container = document.getElementById('recommendationsContainer');
    
    container.innerHTML = recommendations.map(rec => `
        <div class="alert alert-info">
            <h6>${rec.type}: ${rec.title}</h6>
            <p>${rec.description}</p>
            <div class="d-flex gap-2">
                <button class="btn btn-sm btn-primary" onclick="acceptRecommendation(${rec.id})">
                    Accept
                </button>
                <button class="btn btn-sm btn-outline-primary" onclick="explainRecommendation(${rec.id})">
                    Explain
                </button>
                <button class="btn btn-sm btn-outline-secondary" onclick="modifyRecommendation(${rec.id})">
                    Modify
                </button>
            </div>
        </div>
    `).join('');
}

async function loadAlertTimeline(alertId) {
    try {
        const response = await fetch(`/api/alerts/${alertId}/timeline`);
        const events = await response.json();
        
        const timeline = document.getElementById('alertTimeline');
        timeline.innerHTML = events.map(event => `
            <div class="timeline-item">
                <div class="timeline-marker"></div>
                <div class="timeline-content">
                    <h6>${event.title}</h6>
                    <p>${event.description}</p>
                    <small class="text-muted">
                        ${formatDateTime(event.timestamp)} - ${event.user || 'System'}
                    </small>
                </div>
            </div>
        `).join('');
        
    } catch (error) {
        console.error('Error loading timeline:', error);
    }
}

function loadRelatedItems(alert) {
    // Load affected shipments
    if (alert.shipments && alert.shipments.length > 0) {
        displayRelatedShipments(alert.shipments);
    }
    
    // Load affected suppliers
    if (alert.suppliers && alert.suppliers.length > 0) {
        displayRelatedSuppliers(alert.suppliers);
    }
    
    // Load affected routes
    if (alert.routes && alert.routes.length > 0) {
        displayRelatedRoutes(alert.routes);
    }
}

// Alert actions
async function assignAlert(alertId) {
    const assigneeId = document.getElementById('assigneeSelect').value;
    
    try {
        const response = await fetch(`/api/alerts/${alertId}/assign`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ assignee_id: assigneeId })
        });
        
        if (response.ok) {
            showToast('Success', 'Alert assigned successfully', 'success');
            loadAlertDetail(alertId);
        }
        
    } catch (error) {
        console.error('Error assigning alert:', error);
        showToast('Error', 'Failed to assign alert', 'error');
    }
}

async function resolveAlert(alertId) {
    const resolution = document.getElementById('resolutionText').value;
    
    if (!resolution) {
        showToast('Error', 'Please provide a resolution', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/api/alerts/${alertId}/resolve`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ resolution: resolution })
        });
        
        if (response.ok) {
            showToast('Success', 'Alert resolved successfully', 'success');
            setTimeout(() => {
                window.location.href = '/alerts';
            }, 1000);
        }
        
    } catch (error) {
        console.error('Error resolving alert:', error);
        showToast('Error', 'Failed to resolve alert', 'error');
    }
}

async function addAlertNote(alertId) {
    const note = document.getElementById('alertNote').value;
    
    if (!note) return;
    
    try {
        const response = await fetch(`/api/alerts/${alertId}/notes`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ note: note })
        });
        
        if (response.ok) {
            document.getElementById('alertNote').value = '';
            loadAlertTimeline(alertId);
            showToast('Success', 'Note added', 'success');
        }
        
    } catch (error) {
        console.error('Error adding note:', error);
        showToast('Error', 'Failed to add note', 'error');
    }
}

// WebSocket updates
if (window.socket) {
    window.socket.on('alert_created', (data) => {
        // Reload alerts if on alerts page
        if (window.location.pathname === '/alerts') {
            loadAlerts();
        }
        
        // Show notification
        showToast('New Alert', data.title, 'warning');
    });
    
    window.socket.on('alert_updated', (data) => {
        // Update specific alert row if visible
        const row = document.querySelector(`tr[data-alert-id="${data.id}"]`);
        if (row) {
            // Reload just that alert
            updateAlertRow(data.id);
        }
        
        // If on detail page for this alert, reload detail
        if (window.location.pathname === `/alerts/${data.id}`) {
            loadAlertDetail(data.id);
        }
    });
}

async function updateAlertRow(alertId) {
    try {
        const response = await fetch(`/api/alerts/${alertId}`);
        const alert = await response.json();
        
        const row = document.querySelector(`tr[data-alert-id="${alertId}"]`);
        if (row) {
            // Update row content
            const newRow = createAlertRow(alert);
            row.outerHTML = newRow;
        }
        
    } catch (error) {
        console.error('Error updating alert row:', error);
    }
}

// Utility functions
function formatDateTime(dateString) {
    return new Date(dateString).toLocaleString();
}

// Initialize page based on context
if (document.getElementById('alertsTable')) {
    // Alerts list page
    document.addEventListener('DOMContentLoaded', () => {
        initializeFilters();
        loadAlerts();
    });
} else if (document.getElementById('alertDetail')) {
    // Alert detail page
    document.addEventListener('DOMContentLoaded', () => {
        const alertId = window.location.pathname.split('/').pop();
        loadAlertDetail(alertId);
    });
}
