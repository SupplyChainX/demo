/**
 * Notifications JavaScript
 * Handles notification dropdown, unread count, and mark as read functionality
 */

// Notification management
class NotificationManager {
    constructor() {
        this.alertBadge = document.getElementById('alertBadge');
        this.notificationList = document.getElementById('notificationList');
        this.isLoadingNotifications = false;
        
        // Initialize
        this.loadUnreadCount();
        this.loadRecentNotifications();
        
        // Set up auto-refresh
        setInterval(() => {
            this.loadUnreadCount();
        }, 30000); // Every 30 seconds
        
        // Listen for dropdown open
        const notificationDropdown = document.querySelector('[data-bs-toggle="dropdown"]');
        if (notificationDropdown) {
            notificationDropdown.addEventListener('click', () => {
                if (!this.isLoadingNotifications) {
                    this.loadRecentNotifications();
                }
            });
        }
    }
    
    async loadUnreadCount() {
        try {
            const response = await fetch('/api/alerts/open-count');
            if (response.ok) {
                const data = await response.json();
                // Handle both response formats for compatibility
                const count = data.unread_count || data.count || 0;
                this.updateBadge(count);
            }
        } catch (error) {
            console.error('Error loading unread count:', error);
        }
    }
    
    async loadRecentNotifications() {
        if (this.isLoadingNotifications) return;
        
        this.isLoadingNotifications = true;
        
        try {
            // Show loading state
            if (this.notificationList) {
                this.notificationList.innerHTML = `
                    <div class="text-center py-3">
                        <div class="spinner-border spinner-border-sm" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                    </div>
                `;
            }
            
            const response = await fetch('/api/notifications/recent?limit=5');
            if (response.ok) {
                const data = await response.json();
                this.renderNotifications(data.notifications || []);
            } else {
                throw new Error('Failed to load notifications');
            }
        } catch (error) {
            console.error('Error loading notifications:', error);
            if (this.notificationList) {
                this.notificationList.innerHTML = `
                    <p class="text-danger text-center py-3">Failed to load notifications</p>
                `;
            }
        } finally {
            this.isLoadingNotifications = false;
        }
    }
    
    updateBadge(count) {
        if (this.alertBadge) {
            this.alertBadge.textContent = count;
            this.alertBadge.style.display = count > 0 ? 'inline' : 'none';
        }
    }
    
    renderNotifications(notifications) {
        if (!this.notificationList) return;
        
        if (notifications.length === 0) {
            this.notificationList.innerHTML = `
                <p class="text-muted text-center py-3">No new notifications</p>
            `;
            return;
        }
        
        const notificationsHtml = notifications.map(notification => `
            <div class="notification-item p-2 border-bottom" data-alert-id="${notification.id}">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1 me-2">
                        <h6 class="mb-1 fs-6">${this.escapeHtml(notification.title)}</h6>
                        <p class="mb-1 small text-muted">${this.escapeHtml(notification.description || '')}</p>
                        <div class="d-flex align-items-center gap-2">
                            <span class="badge bg-${this.getSeverityColor(notification.severity)} text-uppercase small">
                                ${notification.severity}
                            </span>
                            <small class="text-muted">${notification.time_ago}</small>
                        </div>
                    </div>
                    <button class="btn btn-sm btn-link text-muted mark-read-btn" 
                            data-alert-id="${notification.id}" 
                            title="Mark as read">
                        <i class="bi bi-check"></i>
                    </button>
                </div>
            </div>
        `).join('');
        
        this.notificationList.innerHTML = notificationsHtml;
        
        // Add click handlers for mark as read buttons
        const markReadButtons = this.notificationList.querySelectorAll('.mark-read-btn');
        markReadButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                const alertId = button.getAttribute('data-alert-id');
                this.markAsRead(alertId);
            });
        });
        
        // Add click handlers for notification items (navigate to alert)
        const notificationItems = this.notificationList.querySelectorAll('.notification-item');
        notificationItems.forEach(item => {
            item.addEventListener('click', () => {
                const alertId = item.getAttribute('data-alert-id');
                this.handleNotificationClick(alertId);
            });
        });
    }
    
    async markAsRead(alertId) {
        try {
            const response = await fetch(`/api/notifications/${alertId}/mark-read`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                // Remove the notification from the list
                const notificationItem = document.querySelector(`[data-alert-id="${alertId}"]`);
                if (notificationItem) {
                    notificationItem.remove();
                }
                
                // Update the count
                this.loadUnreadCount();
                
                // If no more notifications, show empty state
                const remainingItems = this.notificationList.querySelectorAll('.notification-item');
                if (remainingItems.length === 0) {
                    this.notificationList.innerHTML = `
                        <p class="text-muted text-center py-3">No new notifications</p>
                    `;
                }
            }
        } catch (error) {
            console.error('Error marking notification as read:', error);
        }
    }
    
    async markAllAsRead() {
        try {
            const response = await fetch('/api/notifications/mark-all-read', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                // Clear all notifications
                this.notificationList.innerHTML = `
                    <p class="text-muted text-center py-3">No new notifications</p>
                `;
                
                // Update the count
                this.updateBadge(0);
            }
        } catch (error) {
            console.error('Error marking all notifications as read:', error);
        }
    }
    
    handleNotificationClick(alertId) {
        // Mark as read and navigate to alerts page
        this.markAsRead(alertId);
        
        // Navigate to alerts page (will show the specific alert)
        window.location.href = `/alerts?highlight=${alertId}`;
    }
    
    getSeverityColor(severity) {
        const colors = {
            'critical': 'danger',
            'high': 'warning',
            'medium': 'info',
            'low': 'success'
        };
        return colors[severity?.toLowerCase()] || 'secondary';
    }
    
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize notification manager when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.notificationManager = new NotificationManager();
});

// Global function to refresh notifications (for external calls)
window.refreshNotifications = function() {
    if (window.notificationManager) {
        window.notificationManager.loadUnreadCount();
        window.notificationManager.loadRecentNotifications();
    }
};

// Global function to mark all as read
window.markAllNotificationsRead = function() {
    if (window.notificationManager) {
        window.notificationManager.markAllAsRead();
    }
};
