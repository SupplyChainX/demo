/**
 * Inventory Management JavaScript
 */

document.addEventListener('DOMContentLoaded', function() {
    initializeInventoryFilters();
    initializeInventoryTable();
    initializeInventoryForms();
    initializeCharts();
    initializeThresholdManagement();
});

function initializeInventoryFilters() {
    // Site filter
    document.getElementById('siteFilter').addEventListener('change', function() {
        filterInventoryTable();
    });

    // SKU search
    document.getElementById('skuSearch').addEventListener('input', function() {
        filterInventoryTable();
    });

    // Threshold filter
    document.getElementById('thresholdFilter').addEventListener('change', function() {
        filterInventoryTable();
    });

    // Risk filter
    document.getElementById('riskFilter').addEventListener('change', function() {
        filterInventoryTable();
    });
}

function initializeInventoryTable() {
    // Make table sortable
    const table = document.getElementById('inventoryTable');
    if (table) {
        makeTableSortable(table);
    }
}

function initializeInventoryForms() {
    // Add inventory form
    const addForm = document.getElementById('addInventoryForm');
    if (addForm) {
        addForm.addEventListener('submit', function(e) {
            e.preventDefault();
            addInventoryItem();
        });
    }
}

function initializeCharts() {
    const chartCanvas = document.getElementById('inventoryChart');
    if (chartCanvas) {
        loadStockLevelChart();
        
        // Chart type toggle handlers
        document.querySelectorAll('input[name="chartType"]').forEach(radio => {
            radio.addEventListener('change', function() {
                switch(this.value) {
                    case 'stock':
                        loadStockLevelChart();
                        break;
                    case 'turnover':
                        loadTurnoverChart();
                        break;
                    case 'value':
                        loadValueDistributionChart();
                        break;
                }
            });
        });
    }
}

function initializeThresholdManagement() {
    // Threshold search and filter handlers
    const thresholdSearch = document.getElementById('thresholdSearchSKU');
    if (thresholdSearch) {
        thresholdSearch.addEventListener('input', function() {
            filterThresholdTable();
        });
    }

    const thresholdFilter = document.getElementById('thresholdStatusFilter');
    if (thresholdFilter) {
        thresholdFilter.addEventListener('change', function() {
            filterThresholdTable();
        });
    }
}

function filterInventoryTable() {
    const siteFilter = document.getElementById('siteFilter').value.toLowerCase();
    const skuSearch = document.getElementById('skuSearch').value.toLowerCase();
    const thresholdFilter = document.getElementById('thresholdFilter').value;
    const riskFilter = document.getElementById('riskFilter').value;

    const table = document.getElementById('inventoryTable');
    const rows = table.querySelectorAll('tbody tr');

    rows.forEach(row => {
        let show = true;
        
        // Site filter
        if (siteFilter && !row.dataset.site.toLowerCase().includes(siteFilter)) {
            show = false;
        }

        // SKU search
        if (skuSearch) {
            const sku = row.querySelector('td:first-child strong').textContent.toLowerCase();
            const description = row.querySelector('td:nth-child(2) div').textContent.toLowerCase();
            if (!sku.includes(skuSearch) && !description.includes(skuSearch)) {
                show = false;
            }
        }

        // Threshold filter
        if (thresholdFilter) {
            const daysCoverCell = row.querySelector('td:nth-child(7)');
            const daysCover = parseFloat(daysCoverCell.textContent);
            
            if (thresholdFilter === 'critical' && daysCover >= 5) {
                show = false;
            } else if (thresholdFilter === 'low' && (daysCover < 5 || daysCover >= 10)) {
                show = false;
            } else if (thresholdFilter === 'normal' && daysCover < 10) {
                show = false;
            }
        }

        // Risk filter
        if (riskFilter) {
            const riskBadge = row.querySelector('td:nth-child(9) .badge');
            const riskLevel = riskBadge ? riskBadge.textContent.toLowerCase() : 'low';
            if (riskLevel !== riskFilter) {
                show = false;
            }
        }

        row.style.display = show ? '' : 'none';
    });

    updateFilteredCounts();
}

function updateFilteredCounts() {
    const table = document.getElementById('inventoryTable');
    const visibleRows = table.querySelectorAll('tbody tr[style=""], tbody tr:not([style])');
    
    // Update visible count somewhere in UI if needed
    console.log(`Showing ${visibleRows.length} items`);
}

function viewItem(sku) {
    // Fetch item details and show in modal
    fetch(`/api/inventory/${sku}`)
        .then(response => response.json())
        .then(data => {
            showItemDetails(data);
        })
        .catch(error => {
            console.error('Error fetching item details:', error);
            showToast('Error', 'Failed to load item details', 'error');
        });
}

function editItem(sku) {
    // Open edit modal or navigate to edit page
    window.location.href = `/inventory/${sku}/edit`;
}

function reorderItem(sku) {
    // Trigger reorder process
    if (confirm(`Create a purchase order for ${sku}?`)) {
        fetch(`/api/inventory/${sku}/reorder`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast('Success', `Reorder initiated for ${sku}`, 'success');
                // Refresh table or update UI
                setTimeout(() => window.location.reload(), 1500);
            } else {
                showToast('Error', data.message || 'Failed to initiate reorder', 'error');
            }
        })
        .catch(error => {
            console.error('Error initiating reorder:', error);
            showToast('Error', 'Failed to initiate reorder', 'error');
        });
    }
}

function addInventoryItem() {
    const form = document.getElementById('addInventoryForm');
    const formData = new FormData(form);
    
    // Validate required fields
    const sku = formData.get('sku');
    const name = formData.get('name');
    
    if (!sku || !name) {
        showToast('Error', 'SKU and Name are required fields', 'error');
        return;
    }
    
    fetch('/api/inventory', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.message || 'Failed to add inventory item');
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            showToast('Success', 'Inventory item added successfully', 'success');
            bootstrap.Modal.getInstance(document.getElementById('addInventoryModal')).hide();
            form.reset();
            // Refresh table
            setTimeout(() => window.location.reload(), 1500);
        } else {
            showToast('Error', data.message || 'Failed to add inventory item', 'error');
        }
    })
    .catch(error => {
        console.error('Error adding inventory item:', error);
        showToast('Error', error.message || 'Failed to add inventory item', 'error');
    });
}

function showItemDetails(item) {
    const content = `
        <div class="row">
            <div class="col-md-6">
                <h6>Basic Information</h6>
                <table class="table table-borderless">
                    <tr><td><strong>SKU:</strong></td><td>${item.sku}</td></tr>
                    <tr><td><strong>Name:</strong></td><td>${item.name}</td></tr>
                    <tr><td><strong>Description:</strong></td><td>${item.description || 'N/A'}</td></tr>
                    <tr><td><strong>Category:</strong></td><td>${item.category || 'N/A'}</td></tr>
                    <tr><td><strong>Unit:</strong></td><td>${item.unit || 'N/A'}</td></tr>
                </table>
            </div>
            <div class="col-md-6">
                <h6>Stock Information</h6>
                <table class="table table-borderless">
                    <tr><td><strong>Current Stock:</strong></td><td>${item.current_stock || 0}</td></tr>
                    <tr><td><strong>Reserved:</strong></td><td>${item.reserved_stock || 0}</td></tr>
                    <tr><td><strong>Available:</strong></td><td>${(item.current_stock || 0) - (item.reserved_stock || 0)}</td></tr>
                    <tr><td><strong>Min Inventory:</strong></td><td>${item.min_inventory || 0}</td></tr>
                    <tr><td><strong>Max Inventory:</strong></td><td>${item.max_inventory || 0}</td></tr>
                    <tr><td><strong>Days Cover:</strong></td><td>${item.days_cover ? item.days_cover.toFixed(1) : 'N/A'}</td></tr>
                </table>
            </div>
        </div>
        <div class="row mt-3">
            <div class="col-12">
                <h6>Recent Activity</h6>
                <div class="table-responsive">
                    <table class="table table-sm">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Type</th>
                                <th>Quantity</th>
                                <th>Reference</th>
                                <th>Notes</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${item.recent_transactions ? item.recent_transactions.map(tx => `
                                <tr>
                                    <td>${new Date(tx.date).toLocaleDateString()}</td>
                                    <td><span class="badge bg-${tx.type === 'in' ? 'success' : 'warning'}">${tx.type.toUpperCase()}</span></td>
                                    <td>${tx.quantity}</td>
                                    <td>${tx.reference || 'N/A'}</td>
                                    <td>${tx.notes || ''}</td>
                                </tr>
                            `).join('') : '<tr><td colspan="5">No recent transactions</td></tr>'}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;

    document.getElementById('itemDetailContent').innerHTML = content;
    new bootstrap.Modal(document.getElementById('itemDetailModal')).show();
}

function exportInventory() {
    window.open('/api/inventory/export', '_blank');
}

function refreshInventory() {
    window.location.reload();
}

function makeTableSortable(table) {
    const headers = table.querySelectorAll('thead th');
    headers.forEach((header, index) => {
        if (index < headers.length - 1) { // Don't make actions column sortable
            header.style.cursor = 'pointer';
            header.addEventListener('click', () => {
                sortTable(table, index);
            });
        }
    });
}

function sortTable(table, columnIndex) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    // Determine sort direction
    const header = table.querySelectorAll('thead th')[columnIndex];
    const isAscending = !header.classList.contains('sort-desc');
    
    // Clear previous sort indicators
    table.querySelectorAll('thead th').forEach(h => {
        h.classList.remove('sort-asc', 'sort-desc');
    });
    
    // Add current sort indicator
    header.classList.add(isAscending ? 'sort-asc' : 'sort-desc');
    
    // Sort rows
    rows.sort((a, b) => {
        const aText = a.children[columnIndex].textContent.trim();
        const bText = b.children[columnIndex].textContent.trim();
        
        // Try to parse as numbers
        const aNum = parseFloat(aText.replace(/[^0-9.-]/g, ''));
        const bNum = parseFloat(bText.replace(/[^0-9.-]/g, ''));
        
        if (!isNaN(aNum) && !isNaN(bNum)) {
            return isAscending ? aNum - bNum : bNum - aNum;
        } else {
            return isAscending ? aText.localeCompare(bText) : bText.localeCompare(aText);
        }
    });
    
    // Reorder rows in DOM
    rows.forEach(row => tbody.appendChild(row));
}

// Toast notification function (if not already defined)
function showToast(title, message, type = 'info') {
    // Implementation depends on your toast system
    // For now, just use console.log
    console.log(`${type.toUpperCase()}: ${title} - ${message}`);
}

// === NEW ADVANCED FEATURES ===

// Threshold Management Functions
function openThresholdManager() {
    loadThresholdData();
    new bootstrap.Modal(document.getElementById('thresholdManagerModal')).show();
}

function loadThresholdData() {
    fetch('/api/inventory/thresholds')
        .then(response => response.json())
        .then(data => {
            renderThresholdTable(data);
        })
        .catch(error => {
            console.error('Error loading threshold data:', error);
            showToast('Error', 'Failed to load threshold data', 'error');
        });
}

function renderThresholdTable(items) {
    const tbody = document.getElementById('thresholdTableBody');
    tbody.innerHTML = '';
    
    items.forEach(item => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td><strong>${item.sku}</strong></td>
            <td>${item.description}</td>
            <td>${item.current_stock}</td>
            <td>
                <input type="number" class="form-control form-control-sm" 
                       value="${item.threshold}" 
                       data-sku="${item.sku}" 
                       data-field="threshold" 
                       min="0" style="width: 80px;">
            </td>
            <td>
                <input type="number" class="form-control form-control-sm" 
                       value="${item.reorder_quantity}" 
                       data-sku="${item.sku}" 
                       data-field="reorder_quantity" 
                       min="1" style="width: 80px;">
            </td>
            <td>
                <span class="badge ${item.days_coverage < 10 ? 'bg-danger' : 'bg-success'}">
                    ${item.days_coverage} days
                </span>
            </td>
            <td>
                <span class="badge ${item.status === 'critical' ? 'bg-danger' : 'bg-success'}">
                    ${item.status.toUpperCase()}
                </span>
            </td>
            <td>
                <button class="btn btn-sm btn-outline-primary" onclick="updateSingleThreshold('${item.sku}')">
                    <i class="fas fa-save"></i>
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function filterThresholdTable() {
    const searchTerm = document.getElementById('thresholdSearchSKU').value.toLowerCase();
    const statusFilter = document.getElementById('thresholdStatusFilter').value;
    const rows = document.querySelectorAll('#thresholdTableBody tr');
    
    rows.forEach(row => {
        const sku = row.querySelector('td strong').textContent.toLowerCase();
        const status = row.querySelector('td:nth-child(7) .badge').textContent.toLowerCase();
        
        let show = true;
        
        if (searchTerm && !sku.includes(searchTerm)) {
            show = false;
        }
        
        if (statusFilter && !status.includes(statusFilter)) {
            show = false;
        }
        
        row.style.display = show ? '' : 'none';
    });
}

function updateSingleThreshold(sku) {
    const row = document.querySelector(`input[data-sku="${sku}"]`).closest('tr');
    const threshold = row.querySelector('input[data-field="threshold"]').value;
    const reorderQuantity = row.querySelector('input[data-field="reorder_quantity"]').value;
    
    updateThreshold(sku, threshold, reorderQuantity);
}

function bulkUpdateThresholds() {
    const updates = [];
    const inputs = document.querySelectorAll('#thresholdTableBody input');
    
    inputs.forEach(input => {
        const sku = input.dataset.sku;
        const field = input.dataset.field;
        const value = input.value;
        
        const existing = updates.find(u => u.sku === sku);
        if (existing) {
            existing[field] = value;
        } else {
            updates.push({ sku, [field]: value });
        }
    });
    
    // Process updates
    Promise.all(updates.map(update => 
        updateThreshold(update.sku, update.threshold, update.reorder_quantity)
    )).then(() => {
        showToast('Success', 'All thresholds updated successfully', 'success');
        bootstrap.Modal.getInstance(document.getElementById('thresholdManagerModal')).hide();
    }).catch(error => {
        showToast('Error', 'Some updates failed', 'error');
    });
}

function updateThreshold(sku, threshold, reorderQuantity) {
    return fetch(`/api/inventory/${sku}/threshold`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            threshold: parseInt(threshold),
            reorder_quantity: parseInt(reorderQuantity)
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Success', `Threshold updated for ${sku}`, 'success');
        } else {
            throw new Error(data.message || 'Update failed');
        }
    });
}

// Chart Functions
function loadStockLevelChart() {
    fetch('/api/inventory/analytics?chart=stock_levels')
        .then(response => response.json())
        .then(data => {
            renderChart('inventoryChart', {
                type: 'bar',
                data: {
                    labels: data.labels || [],
                    datasets: [{
                        label: 'Stock Levels',
                        data: data.values || [],
                        backgroundColor: data.colors || ['#dc3545', '#ffc107', '#28a745'],
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: {
                            display: true,
                            text: 'Current Stock Levels by Category'
                        }
                    }
                }
            });
        })
        .catch(error => console.error('Error loading stock chart:', error));
}

function loadTurnoverChart() {
    fetch('/api/inventory/analytics?chart=turnover')
        .then(response => response.json())
        .then(data => {
            renderChart('inventoryChart', {
                type: 'doughnut',
                data: {
                    labels: ['Fast Moving', 'Medium Moving', 'Slow Moving', 'No Movement'],
                    datasets: [{
                        data: data.values || [0, 0, 0, 0],
                        backgroundColor: ['#28a745', '#ffc107', '#fd7e14', '#dc3545']
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: {
                            display: true,
                            text: 'Inventory Turnover Analysis'
                        }
                    }
                }
            });
        })
        .catch(error => console.error('Error loading turnover chart:', error));
}

function loadValueDistributionChart() {
    fetch('/api/inventory/analytics?chart=value_distribution')
        .then(response => response.json())
        .then(data => {
            renderChart('inventoryChart', {
                type: 'pie',
                data: {
                    labels: data.labels || [],
                    datasets: [{
                        data: data.values || [],
                        backgroundColor: ['#007bff', '#28a745', '#ffc107', '#dc3545', '#6f42c1']
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: {
                            display: true,
                            text: 'Inventory Value Distribution by Category'
                        }
                    }
                }
            });
        })
        .catch(error => console.error('Error loading value chart:', error));
}

function renderChart(canvasId, config) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    
    // Destroy existing chart if it exists
    if (window.inventoryChartInstance) {
        window.inventoryChartInstance.destroy();
    }
    
    window.inventoryChartInstance = new Chart(ctx, config);
}

// Analytics Dashboard Functions
function viewAnalyticsDashboard() {
    loadAdvancedAnalytics();
    new bootstrap.Modal(document.getElementById('analyticsModal')).show();
}

function loadAdvancedAnalytics() {
    const period = document.getElementById('analyticsPeriod')?.value || 30;
    
    fetch(`/api/inventory/analytics?period=${period}&detailed=true`)
        .then(response => response.json())
        .then(data => {
            renderAdvancedCharts(data);
            renderKeyMetrics(data);
            renderTopItemsTable(data.top_items || []);
        })
        .catch(error => {
            console.error('Error loading analytics:', error);
            showToast('Error', 'Failed to load analytics', 'error');
        });
}

function renderAdvancedCharts(data) {
    // ABC Analysis Chart
    const abcCtx = document.getElementById('abcAnalysisChart');
    if (abcCtx) {
        new Chart(abcCtx, {
            type: 'doughnut',
            data: {
                labels: ['A Items (80%)', 'B Items (15%)', 'C Items (5%)'],
                datasets: [{
                    data: [data.abc_analysis?.A || 0, data.abc_analysis?.B || 0, data.abc_analysis?.C || 0],
                    backgroundColor: ['#28a745', '#ffc107', '#dc3545']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });
    }
    
    // Category Performance Chart
    const categoryCtx = document.getElementById('categoryPerformanceChart');
    if (categoryCtx && data.category_analysis) {
        const categories = Object.keys(data.category_analysis);
        const values = categories.map(cat => data.category_analysis[cat].total_value);
        
        new Chart(categoryCtx, {
            type: 'bar',
            data: {
                labels: categories,
                datasets: [{
                    label: 'Total Value',
                    data: values,
                    backgroundColor: '#007bff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }
}

function renderKeyMetrics(data) {
    const content = document.getElementById('keyMetricsContent');
    if (content) {
        content.innerHTML = `
            <div class="mb-3">
                <h6 class="text-primary">Total Inventory Value</h6>
                <div class="h4">$${(data.total_value || 0).toLocaleString()}</div>
            </div>
            <div class="mb-3">
                <h6 class="text-info">Average Turnover</h6>
                <div class="h5">${(data.avg_turnover || 0).toFixed(1)}x/year</div>
            </div>
            <div class="mb-3">
                <h6 class="text-warning">Slow Moving Items</h6>
                <div class="h5">${data.slow_moving_count || 0}</div>
            </div>
            <div class="mb-3">
                <h6 class="text-success">Fill Rate</h6>
                <div class="h5">${(data.fill_rate || 95).toFixed(1)}%</div>
            </div>
        `;
    }
}

function renderTopItemsTable(items) {
    const tbody = document.getElementById('topItemsTableBody');
    if (tbody) {
        tbody.innerHTML = items.map(item => `
            <tr>
                <td><strong>${item.sku}</strong></td>
                <td>${item.description || 'N/A'}</td>
                <td>${item.quantity || 0}</td>
                <td>$${(item.unit_cost || 0).toFixed(2)}</td>
                <td>$${(item.value || 0).toFixed(2)}</td>
                <td>${(item.turnover_rate || 0).toFixed(1)}x</td>
                <td>${item.days_coverage || 0} days</td>
            </tr>
        `).join('');
    }
}

function refreshAnalytics() {
    loadAdvancedAnalytics();
}

function exportAnalytics() {
    const period = document.getElementById('analyticsPeriod')?.value || 30;
    window.open(`/api/inventory/analytics/export?period=${period}`, '_blank');
}

// Automatic Reorder Functions
function triggerAutomaticReorder() {
    fetch('/api/inventory/reorder-needed')
        .then(response => response.json())
        .then(data => {
            const summary = document.getElementById('reorderSummary');
            if (summary) {
                summary.innerHTML = `
                    <div class="alert alert-info">
                        <h6>Items requiring reorder: ${data.length}</h6>
                        <ul class="list-unstyled mb-0">
                            ${data.slice(0, 5).map(item => `
                                <li><strong>${item.sku}</strong> - Current: ${item.current_stock}, Threshold: ${item.threshold}</li>
                            `).join('')}
                            ${data.length > 5 ? `<li><em>... and ${data.length - 5} more items</em></li>` : ''}
                        </ul>
                    </div>
                `;
            }
            new bootstrap.Modal(document.getElementById('autoReorderModal')).show();
        })
        .catch(error => {
            console.error('Error checking reorder needs:', error);
            showToast('Error', 'Failed to check reorder requirements', 'error');
        });
}

function executeAutomaticReorder() {
    fetch('/api/inventory/auto-reorder', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Success', `${data.orders_created} purchase orders created automatically`, 'success');
            bootstrap.Modal.getInstance(document.getElementById('autoReorderModal')).hide();
            // Refresh inventory table
            setTimeout(() => window.location.reload(), 2000);
        } else {
            showToast('Error', data.message || 'Auto reorder failed', 'error');
        }
    })
    .catch(error => {
        console.error('Error executing auto reorder:', error);
        showToast('Error', 'Failed to execute automatic reorder', 'error');
    });
}
