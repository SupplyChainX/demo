// Main JavaScript for SupplyChainX

// Global variables
let chatOpen = false;
let currentUser = null;

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
    
    // Load notification count
    updateNotificationCount();
    
    // Load alert count
    updateAlertCount();
    
    // Load approval count
    updateApprovalCount();
    
    // Set up auto-refresh
    setInterval(updateCounts, 30000); // Every 30 seconds
    
    // Handle chat input
    const chatInput = document.getElementById('chatInput');
    const chatSend = document.getElementById('chatSend');
    
    if (chatInput && chatSend) {
        chatSend.addEventListener('click', sendChatMessage);
        chatInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendChatMessage();
            }
        });
    }
});

// Legacy chat functions removed - using enhanced assistant instead

// Notification Functions
function updateNotificationCount() {
    fetch('/api/notifications/unread-count')
        .then(response => response.json())
        .then(data => {
            const badge = document.getElementById('notificationBadge');
            const count = document.getElementById('notificationCount');
            
            if (badge && count) {
                if (data.count > 0) {
                    badge.style.display = 'inline-block';
                    count.textContent = data.count;
                } else {
                    badge.style.display = 'none';
                }
            }
        })
        .catch(error => console.error('Error updating notification count:', error));
}

function updateAlertCount() {
    fetch('/api/alerts/open-count')
        .then(response => response.json())
        .then(data => {
            const badge = document.getElementById('alertCount');
            if (badge) {
                if (data.count > 0) {
                    badge.style.display = 'inline-block';
                    badge.textContent = data.count;
                } else {
                    badge.style.display = 'none';
                }
            }
        })
        .catch(error => console.error('Error updating alert count:', error));
}

function updateApprovalCount() {
    fetch('/api/approvals/pending-count')
        .then(response => response.json())
        .then(data => {
            const badge = document.getElementById('approvalCount');
            if (badge) {
                if (data.count > 0) {
                    badge.style.display = 'inline-block';
                    badge.textContent = data.count;
                } else {
                    badge.style.display = 'none';
                }
            }
        })
        .catch(error => console.error('Error updating approval count:', error));
}

function updateCounts() {
    updateNotificationCount();
    updateAlertCount();
    updateApprovalCount();
}

// Toast Notifications
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
    
    const iconClass = getToastIcon(type);
    
    const toastHtml = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header ${bgClass} text-white">
                <i class="bi bi-${iconClass} me-2"></i>
                <strong class="me-auto">${title}</strong>
                <small>just now</small>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
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
    
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

function getToastIcon(type) {
    const icons = {
        'info': 'info-circle',
        'success': 'check-circle',
        'warning': 'exclamation-triangle',
        'danger': 'x-circle',
        'error': 'x-circle'
    };
    return icons[type] || 'info-circle';
}

// API Helper Functions
async function apiRequest(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
        },
    };
    
    const response = await fetch(url, { ...defaultOptions, ...options });
    
    if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
    }
    
    return response.json();
}

// Common Actions
function viewShipment(id) {
    window.location.href = `/logistics/shipment/${id}`;
}

function rerouteShipment(id) {
    window.location.href = `/logistics/shipment/${id}/reroute`;
}

function viewPO(id) {
    window.location.href = `/procurement/purchase-order/${id}`;
}

function viewAlert(id) {
    window.location.href = `/alerts/${id}`;
}

function viewThreat(id) {
    window.location.href = `/risk/threat/${id}`;
}

function explainRecommendation(id) {
    fetch(`/api/recommendations/${id}/explain`)
        .then(response => response.json())
        .then(data => {
            // Show explanation in modal
            const modal = new bootstrap.Modal(document.getElementById('explainModal'));
            document.getElementById('explanationContent').innerHTML = formatExplanation(data);
            modal.show();
        })
        .catch(error => {
            showToast('Error', 'Failed to load explanation', 'error');
        });
}

function formatExplanation(data) {
    return `
        <div class="explanation">
            <h6>Rationale</h6>
            <p>${data.rationale}</p>
            
            <h6>Data Sources</h6>
            <ul>
                ${data.sources.map(s => `<li>${s}</li>`).join('')}
            </ul>
            
            <h6>Confidence: ${(data.confidence * 100).toFixed(0)}%</h6>
            <div class="progress mb-3">
                <div class="progress-bar" style="width: ${data.confidence * 100}%"></div>
            </div>
            
            ${data.counterfactuals ? `
                <h6>What would change the recommendation?</h6>
                <ul>
                    ${data.counterfactuals.map(c => `<li>${c}</li>`).join('')}
                </ul>
            ` : ''}
        </div>
    `;
}

function approveRecommendation(id) {
    if (confirm('Are you sure you want to approve this recommendation?')) {
        fetch(`/api/recommendations/${id}/approve`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ comments: '' })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast('Success', 'Recommendation approved', 'success');
                // Refresh the page or update UI
                setTimeout(() => window.location.reload(), 1000);
            } else {
                showToast('Error', data.message || 'Failed to approve', 'error');
            }
        })
        .catch(error => {
            showToast('Error', 'Failed to approve recommendation', 'error');
        });
    }
}

// Export functions for use in other scripts
window.SupplyChainX = {
    showToast,
    apiRequest,
    explainRecommendation,
    approveRecommendation,
    viewShipment,
    rerouteShipment,
    viewPO,
    viewAlert,
    viewThreat
};

// Format currency
function formatCurrency(amount, currency = 'USD') {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: currency
    }).format(amount);
}

// Format date
function formatDate(dateString, includeTime = false) {
    const date = new Date(dateString);
    const options = {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    };
    
    if (includeTime) {
        options.hour = '2-digit';
        options.minute = '2-digit';
    }
    
    return date.toLocaleDateString('en-US', options);
}

// Export utility functions only (chat now handled by enhanced assistant)
window.formatCurrency = formatCurrency;
window.formatDate = formatDate;

// Add message to chat
function addChatMessage(sender, message) {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${sender}-message mb-3`;
    
    const senderClass = sender === 'user' ? 'text-end' : '';
    const bgClass = sender === 'user' ? 'bg-primary text-white' : 'bg-light';
    
    messageDiv.innerHTML = `
        <div class="${senderClass}">
            <div class="d-inline-block p-2 rounded ${bgClass}" style="max-width: 80%;">
                <div class="fw-bold mb-1">${sender === 'user' ? 'You' : 'Assistant'}</div>
                <div>${message}</div>
                <div class="small opacity-75 mt-1">${new Date().toLocaleTimeString()}</div>
            </div>
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Show typing indicator
function showTypingIndicator() {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;
    
    const typingDiv = document.createElement('div');
    typingDiv.id = 'typingIndicator';
    typingDiv.className = 'chat-message assistant-message mb-3';
    typingDiv.innerHTML = `
        <div class="d-inline-block p-2 rounded bg-light">
            <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;
    
    chatMessages.appendChild(typingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Remove typing indicator
function removeTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        indicator.remove();
    }
}

// Handle assistant response
socketIO.on('chat_response', (data) => {
    removeTypingIndicator();
    addChatMessage('assistant', data.message);
    
    // Update chat badge if panel is closed
    const assistantPanel = document.getElementById('assistantPanel');
    if (assistantPanel && !assistantPanel.classList.contains('show')) {
        updateChatBadge(1);
    }
});

// Quick prompt buttons
function sendQuickPrompt(prompt) {
    const input = document.getElementById('chatInput');
    if (input) {
        input.value = prompt;
        sendChatMessage();
    }
}

// Helper functions for enhanced chat
function getSessionId() {
    let sessionId = localStorage.getItem('chat_session_id');
    if (!sessionId) {
        sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        localStorage.setItem('chat_session_id', sessionId);
    }
    return sessionId;
}

function getCurrentPageContext() {
    return {
        page: window.location.pathname,
        timestamp: new Date().toISOString(),
        viewport: {
            width: window.innerWidth,
            height: window.innerHeight
        }
    };
}

function addTypingIndicator() {
    const chatMessages = document.getElementById('chatMessages');
    const typingDiv = document.createElement('div');
    typingDiv.className = 'typing-indicator';
    typingDiv.innerHTML = `
        <div class="d-flex justify-content-start mb-3">
            <div class="p-3 rounded bg-light border" style="max-width: 80%;">
                <div class="d-flex align-items-center">
                    <div class="typing-animation me-2">
                        <span></span><span></span><span></span>
                    </div>
                    <small class="text-muted">Assistant is thinking...</small>
                </div>
            </div>
        </div>
    `;
    chatMessages.appendChild(typingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeTypingIndicator() {
    const typingIndicator = document.querySelector('.typing-indicator');
    if (typingIndicator) {
        typingIndicator.remove();
    }
}

function formatMessage(message) {
    return message
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code class="bg-secondary text-white px-1 rounded">$1</code>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>')
        .replace(/^(.*)$/, '<p>$1</p>');
}

function executeAction(actionType, actionData) {
    try {
        const data = JSON.parse(decodeURIComponent(actionData));
        
        switch(actionType) {
            case 'navigate':
                window.location.href = data;
                break;
            case 'open_shipment':
                window.location.href = `/shipment/${data}`;
                break;
            case 'search_shipment':
                window.location.href = `/logistics?search=${encodeURIComponent(data)}`;
                break;
            case 'open_procurement':
                window.location.href = '/procurement';
                break;
            case 'refresh_data':
                window.location.reload();
                break;
            default:
                console.log('Unknown action:', actionType, data);
        }
    } catch (error) {
        console.error('Error executing action:', error);
    }
}

// Format currency
function formatCurrency(amount, currency = 'USD') {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: currency
    }).format(amount);
}

// Format date
function formatDate(dateString, includeTime = false) {
    const date = new Date(dateString);
    const options = {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    };
    
    if (includeTime) {
        options.hour = '2-digit';
        options.minute = '2-digit';
    }
    
    return date.toLocaleDateString('en-US', options);
}

// Export functions for use in other scripts
window.sendQuickPrompt = sendQuickPrompt;
window.formatCurrency = formatCurrency;
window.formatDate = formatDate;
window.addChatMessage = addChatMessage;
