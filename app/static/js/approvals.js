// Approvals page functionality

let currentTab = 'pending';

document.addEventListener('DOMContentLoaded', function() {
    initializeTabs();
    loadApprovals();
    
    // Auto-refresh pending approvals every 30 seconds
    setInterval(() => {
        if (currentTab === 'pending') {
            loadPendingApprovals();
        }
    }, 30000);
});

function initializeTabs() {
    // Handle tab switches
    const tabLinks = document.querySelectorAll('[data-bs-toggle="tab"]');
    tabLinks.forEach(link => {
        link.addEventListener('shown.bs.tab', function(e) {
            const target = e.target.getAttribute('href');
            currentTab = target.substring(1); // Remove #
            
            switch(currentTab) {
                case 'pending':
                    loadPendingApprovals();
                    break;
                case 'completed':
                    loadCompletedApprovals();
                    break;
                case 'policies':
                    loadTriggeredPolicies();
                    break;
            }
        });
    });
}

function loadApprovals() {
    loadPendingApprovals();
    updateApprovalCounts();
}

async function loadPendingApprovals() {
    try {
        const response = await fetch('/api/approvals?status=pending');
        const approvals = await response.json();
        
        displayPendingApprovals(approvals);
        
    } catch (error) {
        console.error('Error loading pending approvals:', error);
        showToast('Error', 'Failed to load pending approvals', 'error');
    }
}

function displayPendingApprovals(approvals) {
    const container = document.getElementById('pending');
    
    if (approvals.length === 0) {
        container.innerHTML = `
            <div class="col-12 text-center py-5">
                <i class="bi bi-check-circle text-success" style="font-size: 3rem;"></i>
                <h5 class="mt-3">No Pending Approvals</h5>
                <p class="text-muted">All recommendations have been reviewed</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = `
        <div class="row g-3">
            ${approvals.map(approval => createApprovalCard(approval)).join('')}
        </div>
    `;
}

function createApprovalCard(approval) {
    const rec = approval.recommendation;
    const impactHtml = rec.impact_assessment ? createImpactAssessmentHtml(rec.impact_assessment) : '';
    
    return `
        <div class="col-12">
            <div class="card">
                <div class="card-body">
                    <div class="row align-items-center">
                        <div class="col-md-6">
                            <h5 class="mb-1">${rec.title}</h5>
                            <p class="mb-2">${rec.description}</p>
                            <div class="d-flex gap-3 text-muted small">
                                <span>
                                    <i class="bi bi-tag"></i> 
                                    ${rec.type.charAt(0).toUpperCase() + rec.type.slice(1)}
                                </span>
                                <span>
                                    <i class="bi bi-exclamation-circle"></i>
                                    <span class="badge bg-${rec.severity}">
                                        ${rec.severity.charAt(0).toUpperCase() + rec.severity.slice(1)}
                                    </span>
                                </span>
                                <span>
                                    <i class="bi bi-robot"></i>
                                    ${rec.created_by.charAt(0).toUpperCase() + rec.created_by.slice(1)} Agent
                                </span>
                                <span>
                                    <i class="bi bi-clock"></i>
                                    ${formatDateTime(approval.created_at)}
                                </span>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <h6 class="text-muted mb-2">Policy Triggered</h6>
                            ${createPolicyChecksHtml(approval.policy_checks)}
                        </div>
                        <div class="col-md-3 text-end">
                            <button class="btn btn-outline-primary mb-2 w-100" 
                                    onclick="viewDetails(${rec.id})">
                                <i class="bi bi-info-circle"></i> View Details
                            </button>
                            <button class="btn btn-outline-info mb-2 w-100" 
                                    onclick="explainRecommendation(${rec.id})">
                                <i class="bi bi-lightbulb"></i> Explain
                            </button>
                            <div class="btn-group w-100">
                                <button class="btn btn-success" 
                                        onclick="showApprovalModal(${approval.id}, 'approve')">
                                    <i class="bi bi-check-circle"></i> Approve
                                </button>
                                <button class="btn btn-danger" 
                                        onclick="showApprovalModal(${approval.id}, 'reject')">
                                    <i class="bi bi-x-circle"></i> Reject
                                </button>
                            </div>
                        </div>
                    </div>
                    ${impactHtml}
                </div>
            </div>
        </div>
    `;
}

function createPolicyChecksHtml(policyChecks) {
    if (!policyChecks || policyChecks.length === 0) {
        return '<p class="text-muted small">No policy violations</p>';
    }
    
    return policyChecks
        .filter(check => !check.result)
        .map(check => `
            <div class="small">
                <i class="bi bi-shield-x text-danger"></i>
                ${check.policy_name}
                <br>
                <small class="text-muted">${check.reason}</small>
            </div>
        `).join('');
}

function createImpactAssessmentHtml(impact) {
    return `
        <div class="mt-3 p-3 bg-light rounded">
            <h6 class="mb-2">Impact Assessment</h6>
            <div class="row g-3">
                ${Object.entries(impact).map(([key, value]) => `
                    <div class="col-md-3">
                        <small class="text-muted">${formatImpactKey(key)}</small>
                        <div class="fw-bold">
                            ${formatImpactValue(key, value)}
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

function formatImpactKey(key) {
    return key.replace(/_/g, ' ')
        .split(' ')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}

function formatImpactValue(key, value) {
    if (key.includes('cost')) {
        return `$${new Intl.NumberFormat().format(value)}`;
    } else if (key.includes('time')) {
        return `${value} hours`;
    } else if (key.includes('risk') || key.includes('reduction')) {
        return `${(value * 100).toFixed(1)}% reduction`;
    } else if (key.includes('emissions')) {
        return `${value} kg CO₂`;
    }
    return value;
}

async function loadCompletedApprovals() {
    try {
        const response = await fetch('/api/approvals?status=completed&limit=50');
        const approvals = await response.json();
        
        displayCompletedApprovals(approvals);
        
    } catch (error) {
        console.error('Error loading completed approvals:', error);
        showToast('Error', 'Failed to load completed approvals', 'error');
    }
}

function displayCompletedApprovals(approvals) {
    const container = document.getElementById('completed');
    
    container.innerHTML = `
        <div class="table-responsive">
            <table class="table">
                <thead>
                    <tr>
                        <th>Item</th>
                        <th>Type</th>
                        <th>Decision</th>
                        <th>Decided By</th>
                        <th>Date</th>
                        <th>Comments</th>
                    </tr>
                </thead>
                <tbody>
                    ${approvals.map(approval => `
                        <tr>
                            <td>${approval.recommendation.title}</td>
                            <td>${approval.recommendation.type.charAt(0).toUpperCase() + approval.recommendation.type.slice(1)}</td>
                            <td>
                                <span class="badge bg-${approval.status === 'approved' ? 'success' : 'danger'}">
                                    ${approval.status.charAt(0).toUpperCase() + approval.status.slice(1)}
                                </span>
                            </td>
                            <td>${approval.decided_by?.name || 'System'}</td>
                            <td>${formatDateTime(approval.decided_at)}</td>
                            <td>${approval.comments || '-'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

async function loadTriggeredPolicies() {
    try {
        const response = await fetch('/api/policies/triggered');
        const policies = await response.json();
        
        displayTriggeredPolicies(policies);
        
    } catch (error) {
        console.error('Error loading triggered policies:', error);
        showToast('Error', 'Failed to load policy data', 'error');
    }
}

function displayTriggeredPolicies(policies) {
    const container = document.getElementById('policies');
    
    container.innerHTML = `
        <div class="row g-3">
            ${policies.map(policy => `
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">
                            <h6 class="mb-0">${policy.name}</h6>
                        </div>
                        <div class="card-body">
                            <p class="text-muted">${policy.description}</p>
                            <div class="mb-2">
                                <small class="text-muted">Type:</small> ${formatPolicyType(policy.type)}
                            </div>
                            <div class="mb-2">
                                <small class="text-muted">Triggered:</small> ${policy.trigger_count} times today
                            </div>
                            <button class="btn btn-sm btn-outline-primary" 
                                    onclick="viewPolicy(${policy.id})">View Policy</button>
                        </div>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

function formatPolicyType(type) {
    return type.replace(/_/g, ' ')
        .split(' ')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}

async function updateApprovalCounts() {
    try {
        const response = await fetch('/api/approvals/counts');
        const counts = await response.json();
        
        // Update tab badges
        document.querySelectorAll('.nav-link .badge').forEach(badge => {
            const tab = badge.closest('.nav-link').getAttribute('href');
            if (tab === '#pending' && counts.pending !== undefined) {
                badge.textContent = counts.pending;
            } else if (tab === '#completed' && counts.completed !== undefined) {
                badge.textContent = counts.completed;
            } else if (tab === '#policies' && counts.policies !== undefined) {
                badge.textContent = counts.policies;
            }
        });
        
    } catch (error) {
        console.error('Error updating counts:', error);
    }
}

function showApprovalModal(approvalId, action) {
    const modal = new bootstrap.Modal(document.getElementById('approvalModal'));
    
    document.getElementById('approvalId').value = approvalId;
    document.getElementById('approvalAction').value = action;
    document.getElementById('approvalComments').value = '';
    
    // Update modal title
    document.querySelector('#approvalModal .modal-title').textContent = 
        action === 'approve' ? 'Approve Recommendation' : 'Reject Recommendation';
    
    // Update confirm button
    const confirmBtn = document.querySelector('#approvalModal .btn-primary');
    confirmBtn.textContent = action === 'approve' ? 'Approve' : 'Reject';
    confirmBtn.className = `btn ${action === 'approve' ? 'btn-success' : 'btn-danger'}`;
    
    modal.show();
}

async function submitApproval() {
    const approvalId = document.getElementById('approvalId').value;
    const action = document.getElementById('approvalAction').value;
    const comments = document.getElementById('approvalComments').value;
    
    try {
        const response = await fetch(`/api/approvals/${approvalId}/${action}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ comments: comments })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('Success', `Recommendation ${action}d successfully`, 'success');
            bootstrap.Modal.getInstance(document.getElementById('approvalModal')).hide();
            
            // Reload current tab
            if (currentTab === 'pending') {
                loadPendingApprovals();
            }
            updateApprovalCounts();
        } else {
            showToast('Error', data.message || `Failed to ${action} recommendation`, 'error');
        }
        
    } catch (error) {
        console.error(`Error ${action}ing approval:`, error);
        showToast('Error', `Failed to ${action} recommendation`, 'error');
    }
}

function viewDetails(recommendationId) {
    // Open recommendation detail in modal
    fetch(`/api/recommendations/${recommendationId}`)
        .then(response => response.json())
        .then(data => {
            showRecommendationDetail(data);
        })
        .catch(error => {
            console.error('Error loading recommendation:', error);
            showToast('Error', 'Failed to load details', 'error');
        });
}

function showRecommendationDetail(recommendation) {
    const modalHtml = `
        <div class="modal fade" id="detailModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">${recommendation.title}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <h6>Description</h6>
                        <p>${recommendation.description}</p>
                        
                        <h6>Data Sources</h6>
                        <ul>
                            ${recommendation.data_sources.map(source => `<li>${source}</li>`).join('')}
                        </ul>
                        
                        <h6>Confidence Score</h6>
                        <div class="progress mb-3" style="height: 25px;">
                            <div class="progress-bar bg-info" style="width: ${recommendation.confidence * 100}%">
                                ${(recommendation.confidence * 100).toFixed(0)}%
                            </div>
                        </div>
                        
                        ${recommendation.alternatives ? `
                            <h6>Alternatives Considered</h6>
                            <ul>
                                ${recommendation.alternatives.map(alt => `<li>${alt}</li>`).join('')}
                            </ul>
                        ` : ''}
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing modal if present
    const existingModal = document.getElementById('detailModal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Add new modal
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('detailModal'));
    modal.show();
    
    // Clean up on hide
    document.getElementById('detailModal').addEventListener('hidden.bs.modal', function() {
        this.remove();
    });
}

function viewPolicy(policyId) {
    // Navigate to policy detail page
    window.location.href = `/policies/${policyId}`;
}

// WebSocket updates
if (window.socket) {
    window.socket.on('approval_required', (data) => {
        // Reload pending approvals if on that tab
        if (currentTab === 'pending') {
            loadPendingApprovals();
        }
        
        // Update count
        updateApprovalCounts();
        
        // Show notification
        showToast('Approval Required', data.title, 'warning');
    });
    
    window.socket.on('approval_completed', (data) => {
        // Update counts
        updateApprovalCounts();
        
        // Reload appropriate tab
        if (currentTab === 'pending') {
            loadPendingApprovals();
        } else if (currentTab === 'completed') {
            loadCompletedApprovals();
        }
    });
}

// Utility functions
function formatDateTime(dateString) {
    return new Date(dateString).toLocaleString();
}
