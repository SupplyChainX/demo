// WebSocket connection management

// Initialize Socket.IO with error handling
const socketIO = io({
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    reconnectionAttempts: 5
});

// Connection event handlers
socketIO.on('connect', () => {
    console.log('Connected to WebSocket server');
    updateConnectionStatus(true);
});

socketIO.on('disconnect', () => {
    console.log('Disconnected from WebSocket server');
    updateConnectionStatus(false);
});

socketIO.on('connect_error', (error) => {
    console.error('WebSocket connection error:', error.message);
    updateConnectionStatus(false);
});

// Real-time event handlers
socketIO.on('alert_created', (data) => {
    console.log('New alert:', data);
    if (window.showToast) {
        window.showToast('New Alert', data.message || 'New alert created', 'warning');
    }
    updateAlertBadge();
});

socketIO.on('shipment_updated', (data) => {
    console.log('Shipment updated:', data);
    if (window.updateShipmentStatus) {
        window.updateShipmentStatus(data.shipment_id, data.status);
    }
});

socketIO.on('recommendation_ready', (data) => {
    console.log('New recommendation:', data);
    if (window.showToast) {
        window.showToast('New Recommendation', 'AI has a new recommendation', 'info');
    }
    // Don't automatically reload to prevent potential infinite loops
    // Manual refresh is handled by the regular refresh interval
});

socketIO.on('approval_required', (data) => {
    console.log('Approval required:', data);
    updateApprovalBadge();
});

// Helper functions
function updateConnectionStatus(connected) {
    const indicator = document.querySelector('.connection-indicator');
    if (indicator) {
        indicator.classList.toggle('connected', connected);
        indicator.classList.toggle('disconnected', !connected);
    }
}

function updateAlertBadge() {
    // Changed from /api/alerts/open-count to /api/alerts/count
    fetch('/api/alerts/count?status=open')
        .then(response => response.json())
        .then(data => {
            const badge = document.querySelector('#alertsBadge');
            if (badge && data.count > 0) {
                badge.textContent = data.count;
                badge.style.display = 'inline-block';
            } else if (badge) {
                badge.style.display = 'none';
            }
        })
        .catch(error => console.error('Error updating alerts badge:', error));
}

function updateApprovalBadge() {
    fetch('/api/approvals/pending-count')
        .then(response => response.json())
        .then(data => {
            const badge = document.querySelector('#approvalsBadge');
            if (badge && data.count > 0) {
                badge.textContent = data.count;
                badge.style.display = 'inline-block';
            } else if (badge) {
                badge.style.display = 'none';
            }
        })
        .catch(error => console.error('Error updating approvals badge:', error));
}

// Export for use in other modules
window.socketIO = socketIO;

// Toast notification function
function showToast(title, message, type = 'info') {
    const toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        console.error('Toast container not found');
        return;
    }
    
    const toastId = 'toast-' + Date.now();
    
    const bgClass = {
        'success': 'bg-success',
        'danger': 'bg-danger',
        'warning': 'bg-warning',
        'info': 'bg-info',
        'error': 'bg-danger'
    }[type] || 'bg-secondary';
    
    const toastHtml = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header ${bgClass} text-white">
                <strong class="me-auto">${title}</strong>
                <small>just now</small>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, {
        autohide: true,
        delay: 5000
    });
    toast.show();
    
    // Remove after hidden
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

function updateAlertBadge(count) {
    const badge = document.getElementById('alertBadge');
    if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? 'inline-block' : 'none';
    }
}

function updateChatBadge(count) {
    const badge = document.getElementById('chatBadge');
    if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? 'inline-block' : 'none';
    }
}

function addNotification(notification) {
    const notificationList = document.getElementById('notificationList');
    if (!notificationList) return;
    
    // Remove placeholder if exists
    const placeholder = notificationList.querySelector('.text-muted');
    if (placeholder) {
        placeholder.remove();
    }
    
    const severityClass = {
        'high': 'text-danger',
        'medium': 'text-warning',
        'low': 'text-success'
    }[notification.severity] || 'text-info';
    
    const notificationHtml = `
        <div class="notification-item p-2 border-bottom">
            <div class="d-flex justify-content-between">
                <h6 class="mb-1">${notification.title}</h6>
                <small class="text-muted">${formatTime(notification.timestamp)}</small>
            </div>
            <p class="mb-0 small ${severityClass}">${notification.message}</p>
        </div>
    `;
    
    notificationList.insertAdjacentHTML('afterbegin', notificationHtml);
    
    // Keep only last 10 notifications
    const items = notificationList.querySelectorAll('.notification-item');
    if (items.length > 10) {
        items[items.length - 1].remove();
    }
}

function updateShipmentRow(shipmentId, status) {
    const row = document.querySelector(`tr[data-shipment-id="${shipmentId}"]`);
    if (row) {
        const statusCell = row.querySelector('.status-cell');
        if (statusCell) {
            statusCell.innerHTML = `<span class="badge bg-${getStatusColor(status)}">${status}</span>`;
        }
    }
}

function updateMapMarker(shipmentId, location) {
    if (window.shipmentMarkers && window.shipmentMarkers[shipmentId]) {
        const marker = window.shipmentMarkers[shipmentId];
        marker.setLatLng([location.lat, location.lon]);
        marker.bindPopup(`Shipment ${shipmentId}<br>Updated: ${new Date().toLocaleTimeString()}`);
    }
}

function updateRiskIndex(riskScore) {
    const bar = document.getElementById('riskIndexBar');
    const value = document.getElementById('riskIndexValue');
    
    if (bar && value) {
        const percentage = Math.round(riskScore * 100);
        bar.style.width = percentage + '%';
        value.textContent = riskScore.toFixed(2);
        
        // Update color based on risk level
        bar.className = 'progress-bar';
        if (riskScore >= 0.8) {
            bar.classList.add('bg-danger');
        } else if (riskScore >= 0.5) {
            bar.classList.add('bg-warning');
        } else {
            bar.classList.add('bg-success');
        }
    }
}

// Utility functions
function formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 60000) return 'just now';
    if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
    if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
    return date.toLocaleDateString();
}

function getStatusColor(status) {
    const colors = {
        'delivered': 'success',
        'in_transit': 'primary',
        'delayed': 'warning',
        'at_risk': 'danger',
        'planned': 'secondary'
    };
    return colors[status.toLowerCase()] || 'secondary';
}

// Export for use in other scripts
window.socketIO = socketIO;
window.showToast = showToast;
window.updateAlertBadge = updateAlertBadge;
