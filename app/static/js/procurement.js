// Procurement page functionality

let currentView = 'board';
let draftPOs = [];
let suppliers = [];
let allPurchaseOrders = []; // Store all POs for filtering

// Pagination configuration
const ITEMS_PER_PAGE = 8;
let currentPage = {
    draft: 1,
    under_review: 1,
    approved: 1,
    sent: 1,
    fulfilled: 1
};

// Loading state management functions
function showLoadingStates() {
    // Show loading spinners for kanban columns
    const columns = ['draft', 'under-review', 'approved', 'sent', 'fulfilled'];
    columns.forEach(status => {
        const column = document.getElementById(status);
        if (column) {
            const loadingSpinner = document.createElement('div');
            loadingSpinner.className = 'loading-spinner text-center p-3';
            loadingSpinner.innerHTML = '<div class="spinner-border spinner-border-sm" role="status"><span class="sr-only">Loading...</span></div>';
            loadingSpinner.id = `loading-${status}`;
            column.appendChild(loadingSpinner);
        }
    });
    
    // Show loading for list view
    const listContainer = document.getElementById('listContainer');
    if (listContainer) {
        listContainer.innerHTML = '<div class="text-center p-3"><div class="spinner-border" role="status"><span class="sr-only">Loading...</span></div></div>';
    }
}

function hideLoadingStates() {
    // Remove loading spinners from kanban columns
    const columns = ['draft', 'under-review', 'approved', 'sent', 'fulfilled'];
    columns.forEach(status => {
        const loadingSpinner = document.getElementById(`loading-${status}`);
        if (loadingSpinner) {
            loadingSpinner.remove();
        }
    });
    
    // Clear list container spinner if it exists
    const listContainer = document.getElementById('listContainer');
    if (listContainer && listContainer.innerHTML.includes('spinner-border')) {
        listContainer.innerHTML = ''; // Will be populated by updatePOTable
    }
}

// Initialize procurement page
document.addEventListener('DOMContentLoaded', function() {
    loadSuppliers();
    loadPurchaseOrders();
    loadDrafts();
    loadThresholds();
    loadContracts();
    
    // Initialize Sortable for kanban
    initializeKanban();
    
    // Set up auto-refresh
    setInterval(refreshData, 30000);
    
    // Setup search functionality
    setupRealTimeSearch();
    
    // Initialize advanced filters
    initializeAdvancedFilters();
    
    // Add tab change listener to update table when listView tab becomes active
    const listViewTab = document.querySelector('a[href="#listView"]');
    if (listViewTab) {
        listViewTab.addEventListener('shown.bs.tab', function() {
            console.log('List view tab activated - forcing table update');
            // Wait a bit for Bootstrap animations to complete
            setTimeout(() => {
                forceUpdatePOTable();
            }, 150);
        });
    }
    
    // Initialize bulk operations
    initializeBulkOperations();
});

// Initialize kanban drag and drop
function initializeKanban() {
    const columns = document.querySelectorAll('.kanban-column');
    
    columns.forEach(column => {
        new Sortable(column, {
            group: 'purchase-orders',
            animation: 150,
            ghostClass: 'sortable-ghost',
            onEnd: function(evt) {
                const poId = evt.item.dataset.poId;
                const newStatus = evt.to.dataset.status;
                updatePOStatus(poId, newStatus);
            }
        });
    });
}

// Load suppliers for dropdown
async function loadSuppliers() {
    try {
        const response = await fetch('/api/suppliers');
        const data = await response.json();
        suppliers = data.suppliers || [];
        
        // Populate supplier dropdown in PO form
        const select = document.querySelector('select[name="supplier_id"]');
        if (select) {
            select.innerHTML = '<option value="">Select supplier...</option>';
            suppliers.forEach(supplier => {
                select.innerHTML += `
                    <option value="${supplier.id}">${supplier.name} (${supplier.rating}★)</option>
                `;
            });
        }
        
        // Populate supplier filter dropdown
        const supplierFilter = document.getElementById('supplierFilter');
        if (supplierFilter) {
            // Clear existing options except "All Suppliers"
            supplierFilter.innerHTML = '<option value="">All Suppliers</option>';
            
            suppliers.forEach(supplier => {
                const option = document.createElement('option');
                option.value = supplier.name;
                option.textContent = supplier.name;
                supplierFilter.appendChild(option);
            });
        }
        
        console.log('Loaded suppliers:', suppliers.length);
    } catch (error) {
        console.error('Error loading suppliers:', error);
    }
}

// Load purchase orders
async function loadPurchaseOrders() {
    try {
        showLoadingStates();
        
        const response = await fetch('/api/purchase-orders');
        const data = await response.json();
        
        // Store all POs for filtering
        allPurchaseOrders = data.purchase_orders || [];
        
        // Always update both views since we don't know which tab will be active
        updateKanbanBoard(allPurchaseOrders);
        updatePOTable(allPurchaseOrders);
        
        // Load drafts separately
        loadDrafts();
        
        hideLoadingStates();
        
    } catch (error) {
        console.error('Error loading purchase orders:', error);
        showToast('Error', 'Failed to load purchase orders', 'danger');
        hideLoadingStates();
    }
}

// Load drafts from AI procurement agent
async function loadDrafts() {
    try {
        const response = await fetch('/api/drafts');
        const data = await response.json();
        
        updateDrafts(data.drafts || []);
        
    } catch (error) {
        console.error('Error loading drafts:', error);
        // Don't show error toast for drafts as it's not critical
    }
}

// Update kanban board with pagination
function updateKanbanBoard(purchaseOrders) {
    // Safety check for undefined or null purchaseOrders
    if (!purchaseOrders || !Array.isArray(purchaseOrders)) {
        purchaseOrders = [];
    }
    
    // Group by status
    const grouped = {};
    purchaseOrders.forEach(po => {
        if (!grouped[po.status]) {
            grouped[po.status] = [];
        }
        grouped[po.status].push(po);
    });
    
    // Update each column with pagination
    const statusOrder = ['draft', 'under_review', 'approved', 'sent', 'fulfilled'];
    
    statusOrder.forEach(status => {
        const column = document.querySelector(`.kanban-column[data-status="${status}"]`);
        if (!column) return;
        
        const pos = grouped[status] || [];
        const startIndex = (currentPage[status] - 1) * ITEMS_PER_PAGE;
        const endIndex = startIndex + ITEMS_PER_PAGE;
        const paginatedPOs = pos.slice(startIndex, endIndex);
        
        // Clear existing content
        column.innerHTML = '';
        
        if (paginatedPOs.length === 0) {
            column.innerHTML = '<div class="text-center py-4 text-muted">No items</div>';
        } else {
            // Create cards
            paginatedPOs.forEach(po => {
                const card = createPOCard(po);
                column.appendChild(card);
            });
            
            // Add pagination if needed
            if (pos.length > ITEMS_PER_PAGE) {
                const pagination = createPagination(status, pos.length);
                column.appendChild(pagination);
            }
        }
        
        // Update count badge
        const badge = column.closest('.card').querySelector('.badge');
        if (badge) {
            badge.textContent = pos.length;
        }
    });
}

// Create enhanced PO card
function createPOCard(po) {
    const card = document.createElement('div');
    card.className = 'card mb-2 po-card shadow-sm';
    card.dataset.poId = po.id;
    
    // Use actual API field names with fallbacks
    const reference = po.po_number || `PO-${po.id}`;
    const supplierName = po.supplier_name || 'Unknown Supplier';
    const itemCount = po.line_items ? po.line_items.length : 0;
    const totalValue = po.total_amount || 0;
    const slaDate = po.delivery_date || po.created_at;
    
    // Priority and risk indicators
    const priorityClass = getPriorityClass(po.priority);
    const riskIndicator = po.supplier_risk === 'high' ? 
        '<i class="bi bi-exclamation-triangle text-danger" title="High Risk Supplier"></i>' : '';
    
    // Status-based styling
    const statusBadge = getStatusBadge(po.status);
    
    card.innerHTML = `
        <div class="card-body p-3">
            <div class="d-flex justify-content-between align-items-start mb-2">
                <div class="d-flex align-items-center">
                    <input type="checkbox" class="form-check-input me-2 po-checkbox" data-po-id="${po.id}">
                    <h6 class="card-title mb-0 me-2">${reference}</h6>
                    ${riskIndicator}
                </div>
                <span class="badge ${priorityClass}">${po.priority || 'normal'}</span>
            </div>
            <p class="text-muted small mb-2">
                <i class="bi bi-building"></i> ${supplierName}
            </p>
            <div class="row text-center mb-2">
                <div class="col-6">
                    <small class="text-muted">Items</small>
                    <div class="fw-bold text-primary">${itemCount}</div>
                </div>
                <div class="col-6">
                    <small class="text-muted">Value</small>
                    <div class="fw-bold text-success">${formatCurrency(totalValue)}</div>
                </div>
            </div>
            <div class="d-flex justify-content-between align-items-center">
                <small class="text-muted">
                    <i class="bi bi-calendar"></i> ${formatDate(slaDate)}
                </small>
                <div class="btn-group">
                    <button class="btn btn-sm btn-outline-primary" onclick="openPO(${po.id})" title="View Details">
                        <i class="bi bi-eye"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-secondary" onclick="editPO(${po.id})" title="Edit">
                        <i class="bi bi-pencil"></i>
                    </button>
                </div>
            </div>
        </div>
    `;
    
    return card;
}

// Update PO table
function updatePOTable(purchaseOrders) {
    const table = document.querySelector('#poTable');
    const tbody = document.querySelector('#poTable tbody');
    
    if (!table || !tbody) {
        // Table may be in a hidden tab - store data and retry later
        console.log('PO table not visible yet - storing data for when tab becomes active');
        window.pendingPOData = purchaseOrders;
        
        // Try again after a short delay (for tab animations)
        setTimeout(() => {
            const retryTable = document.querySelector('#poTable');
            const retryTbody = document.querySelector('#poTable tbody');
            if (retryTable && retryTbody) {
                updatePOTableImmediate(purchaseOrders, retryTbody);
            }
        }, 100);
        return;
    }
    
    updatePOTableImmediate(purchaseOrders, tbody);
}

// Force update of PO table - used when switching to List tab
function forceUpdatePOTable() {
    const data = window.pendingPOData || window.allPurchaseOrders || [];
    const table = document.querySelector('#poTable');
    const tbody = document.querySelector('#poTable tbody');
    
    if (table && tbody && data.length >= 0) {
        updatePOTableImmediate(data, tbody);
        window.pendingPOData = null; // Clear pending data
        console.log('Successfully updated PO table with', data.length, 'items');
    } else {
        console.warn('Could not force update PO table - element not found or no data');
    }
}

// Helper function to actually update the table
function updatePOTableImmediate(purchaseOrders, tbody) {
    tbody.innerHTML = '';
    
    if (!purchaseOrders || purchaseOrders.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">No purchase orders found</td></tr>';
        return;
    }
    
    purchaseOrders.forEach(po => {
        const row = document.createElement('tr');
        
        // Use correct field names from API response
        const reference = po.po_number || `PO-${po.id}`;
        const supplierName = po.supplier_name || 'Unknown Supplier';
        const itemCount = po.line_items ? po.line_items.length : 0;
        const totalValue = po.total_amount || 0;
        const slaDate = po.delivery_date || po.created_at;
        
        row.innerHTML = `
            <td><a href="/purchase/${po.id}">${reference}</a></td>
            <td>${supplierName}</td>
            <td>${itemCount}</td>
            <td>${formatCurrency(totalValue)}</td>
            <td><span class="badge bg-${getStatusColor(po.status)}">${po.status}</span></td>
            <td>${formatDate(slaDate)}</td>
            <td>
                <div class="btn-group btn-group-sm">
                    <a href="/purchase/${po.id}" class="btn btn-outline-primary">Open</a>
                    ${po.status === 'draft' || po.status === 'under_review' ? 
                        '<button class="btn btn-outline-warning" onclick="editPO(' + po.id + ')">Edit</button>' : ''}
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });
    
    console.log(`Updated PO table with ${purchaseOrders.length} rows`);
}

// Update drafts section
function updateDrafts(drafts) {
    const container = document.getElementById('draftsList');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (drafts.length === 0) {
        container.innerHTML = '<p class="text-center text-muted py-4">No AI-generated drafts available</p>';
        return;
    }
    
    drafts.forEach(draft => {
        const card = `
            <div class="col-md-6">
                <div class="card">
                    <div class="card-body">
                        <h6 class="card-title">${draft.title}</h6>
                        <p class="text-muted">${draft.reason}</p>
                        <ul class="small">
                            ${draft.items.map(item => `<li>${item.description} (${item.quantity})</li>`).join('')}
                        </ul>
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="text-muted">Est. ${formatCurrency(draft.estimated_value)}</span>
                            <div>
                                <button class="btn btn-sm btn-primary" onclick="acceptDraft(${draft.id})">
                                    Accept
                                </button>
                                <button class="btn btn-sm btn-outline-secondary" onclick="editDraft(${draft.id})">
                                    Edit
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        container.insertAdjacentHTML('beforeend', card);
    });
}

// Load inventory thresholds
async function loadThresholds() {
    try {
        const response = await fetch('/api/inventory/thresholds');
        const thresholds = await response.json();
        
        const tbody = document.getElementById('thresholdsTable');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        thresholds.forEach(item => {
            const stockClass = item.days_coverage < 10 ? 'text-danger' : '';
            
            const row = `
                <tr>
                    <td>${item.sku}</td>
                    <td>${item.description}</td>
                    <td class="${stockClass}">${item.current_stock}</td>
                    <td>${item.threshold}</td>
                    <td>${item.reorder_quantity}</td>
                    <td>
                        <button class="btn btn-sm btn-primary" onclick="createReorderPO('${item.sku}')">
                            Reorder
                        </button>
                        <button class="btn btn-sm btn-outline-secondary" onclick="editThreshold('${item.sku}')">
                            Edit
                        </button>
                    </td>
                </tr>
            `;
            tbody.insertAdjacentHTML('beforeend', row);
        });
        
    } catch (error) {
        console.error('Error loading thresholds:', error);
    }
}

// Load contracts
async function loadContracts() {
    try {
        const response = await fetch('/api/contracts');
        const data = await response.json();
        
        const tbody = document.querySelector('#contractsTable tbody');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        const contracts = data.contracts || [];
        
        contracts.forEach(contract => {
            const row = document.createElement('tr');
            
            // Calculate status color based on expiry
            let statusClass = 'success';
            let statusText = contract.status;
            
            if (contract.days_to_expiry !== null) {
                if (contract.days_to_expiry < 0) {
                    statusClass = 'danger';
                    statusText = 'Expired';
                } else if (contract.days_to_expiry < 30) {
                    statusClass = 'warning';
                    statusText = 'Expiring Soon';
                }
            }
            
            row.innerHTML = `
                <td>${contract.contract_number}</td>
                <td>${contract.supplier_name || 'Unknown'}</td>
                <td>${contract.name || '-'}</td>
                <td><span class="badge bg-${statusClass}">${statusText}</span></td>
                <td>${formatDate(contract.start_date)}</td>
                <td>${formatDate(contract.end_date)}</td>
                <td>${contract.days_to_expiry !== null ? contract.days_to_expiry + ' days' : '-'}</td>
                <td>${contract.payment_terms || '-'}</td>
                <td>${formatCurrency(contract.minimum_order_value)}</td>
                <td>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-primary" onclick="viewContract(${contract.id})">
                            View
                        </button>
                        <button class="btn btn-outline-secondary" onclick="editContract(${contract.id})">
                            Edit
                        </button>
                        ${contract.days_to_expiry < 60 && contract.days_to_expiry >= 0 ? 
                          '<button class="btn btn-outline-warning" onclick="renewContract(' + contract.id + ')">Renew</button>' : ''}
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
        
    } catch (error) {
        console.error('Error loading contracts:', error);
    }
}

// Create new PO
async function createPO() {
    const form = document.getElementById('newPOForm');
    const formData = new FormData(form);
    
    // Collect items
    const items = [];
    const descriptions = form.querySelectorAll('input[name="item_description[]"]');
    const quantities = form.querySelectorAll('input[name="quantity[]"]');
    const prices = form.querySelectorAll('input[name="unit_price[]"]');
    
    for (let i = 0; i < descriptions.length; i++) {
        items.push({
            description: descriptions[i].value,
            quantity: parseInt(quantities[i].value),
            unit_price: parseFloat(prices[i].value)
        });
    }
    
    const poData = {
        supplier_id: formData.get('supplier_id'),
        delivery_date: formData.get('delivery_date'),
        items: items
    };
    
    try {
        const response = await fetch('/api/purchase-orders', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(poData)
        });
        
        if (response.ok) {
            const po = await response.json();
            showToast('Success', `Purchase Order ${po.reference} created`, 'success');
            
            // Close modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('newPOModal'));
            modal.hide();
            
            // Reload data
            loadPurchaseOrders();
        } else {
            const error = await response.json();
            showToast('Error', error.message || 'Failed to create PO', 'danger');
        }
    } catch (error) {
        showToast('Error', 'Failed to create purchase order', 'danger');
    }
}

// Update PO status
async function updatePOStatus(poId, newStatus) {
    try {
        const response = await fetch(`/api/purchase-orders/${poId}/status`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ status: newStatus })
        });
        
        if (response.ok) {
            showToast('Success', 'Status updated', 'success');
        } else {
            showToast('Error', 'Failed to update status', 'danger');
            // Reload to revert position
            loadPurchaseOrders();
        }
    } catch (error) {
        showToast('Error', 'Failed to update status', 'danger');
        loadPurchaseOrders();
    }
}

// Add item to PO form
function addItem() {
    const container = document.getElementById('poItems');
    const newItem = container.querySelector('.row').cloneNode(true);
    
    // Clear values
    newItem.querySelectorAll('input').forEach(input => input.value = '');
    
    container.appendChild(newItem);
}

// Remove item from PO form
function removeItem(button) {
    const row = button.closest('.row');
    const container = document.getElementById('poItems');
    
    // Keep at least one item
    if (container.querySelectorAll('.row').length > 1) {
        row.remove();
    }
}

// Helper functions
function openPO(poId) {
    window.location.href = `/purchase/${poId}`;
}

function editPO(poId) {
    // Navigate to PO detail page where edit modal is available
    window.location.href = `/purchase/${poId}`;
}

function negotiatePO(poId) {
    window.location.href = `/purchase/${poId}?action=negotiate`;
}

function acceptDraft(draftId) {
    // Convert draft to PO
    fetch(`/api/drafts/${draftId}/accept`, { method: 'POST' })
        .then(() => {
            showToast('Success', 'Draft converted to purchase order', 'success');
            loadPurchaseOrders();
        })
        .catch(() => {
            showToast('Error', 'Failed to accept draft', 'danger');
        });
}

function editDraft(draftId) {
    window.location.href = `/drafts/${draftId}/edit`;
}

function createReorderPO(sku) {
    // Open new PO modal with pre-filled SKU
    const modal = new bootstrap.Modal(document.getElementById('newPOModal'));
    modal.show();
    
    // Pre-fill with SKU details
    // TODO: Fetch SKU details and populate form
}

function editThreshold(sku) {
    // Open threshold edit modal
    // TODO: Implement threshold editing
}

function refreshData() {
    loadPurchaseOrders();
    loadDrafts();
    loadThresholds();
    loadContracts();
}

function getStatusColor(status) {
    const colors = {
        'draft': 'secondary',
        'under_review': 'warning',
        'approved': 'success',
        'sent': 'info',
        'fulfilled': 'primary'
    };
    return colors[status] || 'secondary';
}

// Handle real-time updates
socketIO.on('po_created', (data) => {
    showToast('New PO', `${data.reference} created`, 'info');
    loadPurchaseOrders();
});

socketIO.on('po_status_changed', (data) => {
    // Update specific card if visible
    const card = document.querySelector(`[data-po-id="${data.po_id}"]`);
    if (card) {
        card.classList.add('update-flash');
        setTimeout(() => card.classList.remove('update-flash'), 1000);
    }
    loadPurchaseOrders();
});

// Export functions
window.createPO = createPO;
window.addItem = addItem;
window.removeItem = removeItem;
window.openPO = openPO;
window.editPO = editPO;
window.negotiatePO = negotiatePO;
window.acceptDraft = acceptDraft;
window.editDraft = editDraft;
window.createReorderPO = createReorderPO;
window.editThreshold = editThreshold;
window.bulkApprove = bulkApprove;
window.bulkReject = bulkReject;
window.acceptAISuggestion = acceptAISuggestion;
window.showLoadingStates = showLoadingStates;
window.hideLoadingStates = hideLoadingStates;

// Advanced filtering functionality
function initializeAdvancedFilters() {
    // Priority filter
    document.getElementById('priorityFilter')?.addEventListener('change', applyFilters);
    
    // Date range filter
    document.getElementById('dateRangeFilter')?.addEventListener('change', applyFilters);
    
    // Value range filter
    document.getElementById('valueRangeFilter')?.addEventListener('change', applyFilters);
    
    // Supplier filter
    document.getElementById('supplierFilter')?.addEventListener('change', applyFilters);
    
    // Risk filter
    document.getElementById('riskFilter')?.addEventListener('change', applyFilters);
}

function applyFilters() {
    const filters = {
        priority: document.getElementById('priorityFilter')?.value || '',
        dateRange: document.getElementById('dateRangeFilter')?.value || '',
        valueRange: document.getElementById('valueRangeFilter')?.value || '',
        supplier: document.getElementById('supplierFilter')?.value || '',
        risk: document.getElementById('riskFilter')?.value || '',
        search: document.getElementById('procurementSearch')?.value || ''
    };
    
    const filteredPOs = filterPurchaseOrders(allPurchaseOrders, filters);
    renderFilteredPOs(filteredPOs);
}

function filterPurchaseOrders(pos, filters) {
    return pos.filter(po => {
        // Search filter
        if (filters.search) {
            const searchTerm = filters.search.toLowerCase();
            const searchText = `${po.po_number} ${po.supplier_name} ${po.description || ''}`.toLowerCase();
            if (!searchText.includes(searchTerm)) return false;
        }
        
        // Priority filter
        if (filters.priority && po.priority !== filters.priority) return false;
        
        // Supplier filter
        if (filters.supplier && po.supplier_name !== filters.supplier) return false;
        
        // Risk filter
        if (filters.risk && po.supplier_risk !== filters.risk) return false;
        
        // Date range filter
        if (filters.dateRange) {
            const poDate = new Date(po.created_at);
            const today = new Date();
            let daysDiff = Math.floor((today - poDate) / (1000 * 60 * 60 * 24));
            
            switch(filters.dateRange) {
                case 'today':
                    if (daysDiff !== 0) return false;
                    break;
                case 'week':
                    if (daysDiff > 7) return false;
                    break;
                case 'month':
                    if (daysDiff > 30) return false;
                    break;
            }
        }
        
        // Value range filter
        if (filters.valueRange && po.total_amount) {
            const amount = po.total_amount;
            switch(filters.valueRange) {
                case 'small':
                    if (amount >= 10000) return false;
                    break;
                case 'medium':
                    if (amount < 10000 || amount >= 50000) return false;
                    break;
                case 'large':
                    if (amount < 50000) return false;
                    break;
            }
        }
        
        return true;
    });
}

function renderFilteredPOs(filteredPOs) {
    // Group by status
    const groupedPOs = {
        draft: filteredPOs.filter(po => po.status === 'draft'),
        under_review: filteredPOs.filter(po => po.status === 'under_review'),
        approved: filteredPOs.filter(po => po.status === 'approved'),
        sent: filteredPOs.filter(po => po.status === 'sent'),
        fulfilled: filteredPOs.filter(po => po.status === 'fulfilled')
    };
    
    // Update each column
    Object.keys(groupedPOs).forEach(status => {
        const column = document.querySelector(`[data-status="${status}"]`);
        if (column) {
            renderColumnPage(column, groupedPOs[status], status, 1);
        }
    });
}

// Enhanced search functionality
function setupRealTimeSearch() {
    const searchInput = document.getElementById('procurementSearch');
    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                applyFilters();
            }, 300);
        });
    }
}

// Bulk operations
function initializeBulkOperations() {
    // Select all checkbox
    document.getElementById('selectAllPOs')?.addEventListener('change', function() {
        const checkboxes = document.querySelectorAll('.po-checkbox');
        checkboxes.forEach(cb => cb.checked = this.checked);
        updateBulkActions();
    });
    
    // Individual checkboxes
    document.addEventListener('change', function(e) {
        if (e.target.classList.contains('po-checkbox')) {
            updateBulkActions();
        }
    });
}

function updateBulkActions() {
    const selectedPOs = document.querySelectorAll('.po-checkbox:checked');
    const bulkActionsDiv = document.getElementById('bulkActions');
    
    if (selectedPOs.length > 0) {
        bulkActionsDiv?.classList.remove('d-none');
        document.getElementById('selectedCount').textContent = selectedPOs.length;
    } else {
        bulkActionsDiv?.classList.add('d-none');
    }
}

function bulkApprove() {
    const selectedPOs = Array.from(document.querySelectorAll('.po-checkbox:checked'))
        .map(cb => cb.dataset.poId);
    
    if (selectedPOs.length === 0) return;
    
    if (confirm(`Approve ${selectedPOs.length} purchase orders?`)) {
        selectedPOs.forEach(poId => updatePOStatus(poId, 'approved'));
        clearSelection();
    }
}

function bulkReject() {
    const selectedPOs = Array.from(document.querySelectorAll('.po-checkbox:checked'))
        .map(cb => cb.dataset.poId);
    
    if (selectedPOs.length === 0) return;
    
    if (confirm(`Reject ${selectedPOs.length} purchase orders?`)) {
        selectedPOs.forEach(poId => updatePOStatus(poId, 'rejected'));
        clearSelection();
    }
}

function clearSelection() {
    document.querySelectorAll('.po-checkbox').forEach(cb => cb.checked = false);
    document.getElementById('selectAllPOs').checked = false;
    updateBulkActions();
}

function acceptAISuggestion(sku, quantity, supplier) {
    // Create AI-generated PO
    fetch('/api/procurement/ai-create-po', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            sku: sku,
            quantity: quantity,
            supplier: supplier
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Success', 'AI-generated PO created', 'success');
            bootstrap.Modal.getInstance(document.getElementById('aiReorderModal')).hide();
            loadPurchaseOrders();
        }
    });
}

// Utility functions
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(amount || 0);
}

function formatNumber(num) {
    return new Intl.NumberFormat('en-US').format(num);
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
        month: 'short', 
        day: 'numeric' 
    });
}

function formatDateTime(dateString) {
    return new Date(dateString).toLocaleString();
}

// Helper functions for card styling
function getPriorityClass(priority) {
    switch(priority?.toLowerCase()) {
        case 'high': return 'bg-danger text-white';
        case 'medium': return 'bg-warning text-dark';
        case 'low': return 'bg-info text-white';
        default: return 'bg-secondary text-white';
    }
}

function getStatusBadge(status) {
    switch(status?.toLowerCase()) {
        case 'draft': return '<span class="badge bg-secondary">Draft</span>';
        case 'pending': return '<span class="badge bg-warning">Pending</span>';
        case 'approved': return '<span class="badge bg-success">Approved</span>';
        case 'rejected': return '<span class="badge bg-danger">Rejected</span>';
        case 'delivered': return '<span class="badge bg-primary">Delivered</span>';
        default: return '<span class="badge bg-light text-dark">Unknown</span>';
    }
}

// Update column counts
async function updateColumnCounts() {
    const response = await fetch('/api/purchase-orders/counts');
    const counts = await response.json();
    
    document.querySelectorAll('.card-header span').forEach(span => {
        const status = span.closest('.card').querySelector('.kanban-column').dataset.status;
        if (counts[status] !== undefined) {
            span.textContent = `(${counts[status]})`;
        }
    });
}

// Contract management functions
function viewContract(contractId) {
    // Open contract details modal or navigate to contract page
    window.open(`/contracts/${contractId}`, '_blank');
}

function editContract(contractId) {
    // Open contract edit modal
    // TODO: Implement contract editing functionality
    showToast('Info', 'Contract editing coming soon', 'info');
}

function renewContract(contractId) {
    // Open contract renewal workflow
    if (confirm('Start contract renewal process?')) {
        fetch(`/api/contracts/${contractId}/renew`, { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showToast('Success', 'Contract renewal initiated', 'success');
                    loadContracts();
                } else {
                    showToast('Error', data.message || 'Failed to renew contract', 'danger');
                }
            })
            .catch(() => {
                showToast('Error', 'Failed to renew contract', 'danger');
            });
    }
}

// Create pagination controls for kanban columns
function createPagination(status, totalItems) {
    const totalPages = Math.ceil(totalItems / ITEMS_PER_PAGE);
    const currentPageNum = currentPage[status];
    
    if (totalPages <= 1) return null;
    
    const pagination = document.createElement('div');
    pagination.className = 'pagination-container mt-2 text-center';
    
    let paginationHTML = '<nav><ul class="pagination pagination-sm justify-content-center">';
    
    // Previous button
    if (currentPageNum > 1) {
        paginationHTML += `<li class="page-item">
            <button class="page-link" onclick="changePage('${status}', ${currentPageNum - 1})">
                <i class="bi bi-chevron-left"></i>
            </button>
        </li>`;
    }
    
    // Page numbers
    for (let i = 1; i <= totalPages; i++) {
        const activeClass = i === currentPageNum ? 'active' : '';
        paginationHTML += `<li class="page-item ${activeClass}">
            <button class="page-link" onclick="changePage('${status}', ${i})">${i}</button>
        </li>`;
    }
    
    // Next button
    if (currentPageNum < totalPages) {
        paginationHTML += `<li class="page-item">
            <button class="page-link" onclick="changePage('${status}', ${currentPageNum + 1})">
                <i class="bi bi-chevron-right"></i>
            </button>
        </li>`;
    }
    
    paginationHTML += '</ul></nav>';
    pagination.innerHTML = paginationHTML;
    
    return pagination;
}

// Handle page changes for kanban columns
function changePage(status, page) {
    currentPage[status] = page;
    updateKanbanBoard(allPurchaseOrders);
}

// Utility functions
function formatCurrency(amount) {
    if (!amount) return '$0.00';
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(amount);
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    try {
        const date = new Date(dateString);
        return date.toLocaleDateString();
    } catch (e) {
        return 'Invalid Date';
    }
}

function getStatusColor(status) {
    const colors = {
        'draft': 'secondary',
        'under_review': 'warning',
        'approved': 'info',
        'sent': 'primary',
        'fulfilled': 'success'
    };
    return colors[status] || 'secondary';
}

function getPriorityClass(priority) {
    const classes = {
        'high': 'bg-danger',
        'medium': 'bg-warning',
        'low': 'bg-success'
    };
    return classes[priority] || 'bg-secondary';
}

function getStatusBadge(status) {
    const color = getStatusColor(status);
    return `<span class="badge bg-${color}">${status.replace('_', ' ')}</span>`;
}

function showToast(title, message, type = 'info') {
    // Simple toast implementation - could be enhanced with Bootstrap toast
    const alertClass = type === 'danger' ? 'alert-danger' : 
                      type === 'success' ? 'alert-success' : 
                      type === 'warning' ? 'alert-warning' : 'alert-info';
    
    const toast = document.createElement('div');
    toast.className = `alert ${alertClass} alert-dismissible fade show position-fixed top-0 end-0 m-3`;
    toast.style.zIndex = '9999';
    toast.innerHTML = `
        <strong>${title}</strong> ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(toast);
    
    // Auto-remove after 3 seconds
    setTimeout(() => {
        if (toast.parentNode) {
            toast.parentNode.removeChild(toast);
        }
    }, 3000);
}

// Export new functions
window.viewContract = viewContract;
window.editContract = editContract;
window.renewContract = renewContract;
window.changePage = changePage;
