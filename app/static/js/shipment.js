// Shipment Detail Page JavaScript
// Handles route visualization, optimization workflow, and real-time updates

let routeMap = null;
let currentRouteLayer = null;
let alternativeRouteLayers = [];
let selectedRoute = null;
let currentStep = 1;
let routeOptions = null;
let routeModalInstance = null;

// Initialize the shipment detail page
function initializeShipmentPage() {
    // Initialize map when route tab is shown
    document.getElementById('route-tab').addEventListener('shown.bs.tab', function() {
        if (!routeMap) {
            initializeRouteMap();
            loadRouteData();
        }
    });

    // Setup reroute button
    const rerouteBtn = document.getElementById('rerouteBtn');
    if (rerouteBtn) {
        rerouteBtn.addEventListener('click', startRerouteProcess);
    }

    // Setup optimize route button
    const optimizeRouteBtn = document.querySelector('.optimize-route-btn');
    if (optimizeRouteBtn) {
        optimizeRouteBtn.addEventListener('click', triggerRouteOptimization);
    }

    // Setup modal navigation
    document.getElementById('nextStep').addEventListener('click', nextStep);
    document.getElementById('prevStep').addEventListener('click', prevStep);
    document.getElementById('confirmReroute').addEventListener('click', confirmReroute);

    // Setup show alternatives toggle
    document.getElementById('showAlternatives').addEventListener('change', toggleAlternatives);

    // Connect to WebSocket for real-time updates
    connectWebSocket();

    // Manual route management UI
    const addRouteBtn = document.getElementById('addRouteBtn');
    const saveRouteBtn = document.getElementById('saveRouteBtn');
    const routeModalEl = document.getElementById('routeModal');
    if (routeModalEl) {
        routeModalInstance = new bootstrap.Modal(routeModalEl);
    }
    if (addRouteBtn) {
        addRouteBtn.addEventListener('click', () => openRouteModal());
    }
    if (saveRouteBtn) {
        saveRouteBtn.addEventListener('click', saveRouteFromModal);
    }

    // Delegate click events for explain/approve/select buttons
    document.body.addEventListener('click', (e) => {
        const explainBtn = e.target.closest('.explain-btn');
        if (explainBtn) {
            const id = parseInt(explainBtn.getAttribute('data-explain-id'), 10);
            if (!isNaN(id)) explainRecommendation(id);
            return;
        }
        const approveBtn = e.target.closest('.approve-btn');
        if (approveBtn) {
            const id = parseInt(approveBtn.getAttribute('data-approve-id'), 10);
            if (!isNaN(id)) approveRecommendation(id);
            return;
        }
        const selectBtn = e.target.closest('.select-route-btn');
        if (selectBtn) {
            const id = parseInt(selectBtn.getAttribute('data-route-id'), 10);
            if (!isNaN(id)) selectRoute(id);
            return;
        }
        const previewBtn = e.target.closest('.preview-route-btn');
        if (previewBtn) {
            const id = parseInt(previewBtn.getAttribute('data-route-id'), 10);
            if (!isNaN(id)) previewRoute(id);
            return;
        }
    });
}

// Initialize the route map
function initializeRouteMap() {
    // Create map centered on shipment origin
    routeMap = L.map('routeMap').setView(
        [window.shipmentData.origin.lat, window.shipmentData.origin.lon],
        4
    );

    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(routeMap);

    // Add origin marker
    L.marker([window.shipmentData.origin.lat, window.shipmentData.origin.lon], {
        icon: L.divIcon({
            html: '<i class="bi bi-geo-alt-fill text-success" style="font-size: 24px;"></i>',
            iconSize: [24, 24],
            className: 'custom-div-icon'
        })
    }).addTo(routeMap)
    .bindPopup(`<strong>Origin:</strong> ${window.shipmentData.origin.name}`);

    // Add destination marker
    L.marker([window.shipmentData.destination.lat, window.shipmentData.destination.lon], {
        icon: L.divIcon({
            html: '<i class="bi bi-flag-fill text-danger" style="font-size: 24px;"></i>',
            iconSize: [24, 24],
            className: 'custom-div-icon'
        })
    }).addTo(routeMap)
    .bindPopup(`<strong>Destination:</strong> ${window.shipmentData.destination.name}`);

    // Add current location marker if in transit
    if (window.shipmentData.currentLocation) {
        L.marker([window.shipmentData.currentLocation.lat, window.shipmentData.currentLocation.lon], {
            icon: L.divIcon({
                html: '<i class="bi bi-geo-fill text-primary" style="font-size: 20px;"></i>',
                iconSize: [20, 20],
                className: 'custom-div-icon'
            })
        }).addTo(routeMap)
        .bindPopup(`<strong>Current Location</strong>`);
    }
}

// Load route data from API
async function loadRouteData() {
    try {
        const response = await fetch(`/api/shipments/${window.shipmentData.id}`);
        const data = await response.json();
        
        if (data.routes) {
            displayRoutes(data.routes);
            updateRouteList(data.routes);
        }
    } catch (error) {
        console.error('Error loading route data:', error);
        showToast('Error', 'Failed to load route data', 'error');
    }
}

// Display routes on the map
function displayRoutes(routes) {
    // Clear existing layers
    if (currentRouteLayer) routeMap.removeLayer(currentRouteLayer);
    alternativeRouteLayers.forEach(l => routeMap.removeLayer(l));
    alternativeRouteLayers = [];

    const showAlts = document.getElementById('showAlternatives')?.checked;

    routes.forEach(route => {
        let waypoints = [];
        try {
            if (typeof route.waypoints === 'string') {
                try {
                    waypoints = JSON.parse(route.waypoints);
                } catch {
                    // If waypoints is a string description, skip map display for this route
                    console.warn('Route waypoints is not valid JSON:', route.waypoints);
                    return;
                }
            } else if (Array.isArray(route.waypoints)) {
                waypoints = route.waypoints;
            }
        } catch (e) {
            console.warn('Error parsing waypoints for route:', route.id, e);
            return;
        }
        
        const coords = waypoints.map(w => [w.lat, w.lon]).filter(c => Array.isArray(c) && c.length === 2 && !isNaN(c[0]) && !isNaN(c[1]));
        if (!coords.length) return;

        const isCurrent = !!route.is_current;
        if (!isCurrent && !showAlts) {
            // don't draw alternative until toggled on
            return;
        }

        const polyline = L.polyline(coords, {
            color: isCurrent ? '#0d6efd' : '#6c757d',
            weight: isCurrent ? 4 : 2,
            opacity: isCurrent ? 1 : 0.9,
            dashArray: isCurrent ? null : '6,6'
        }).addTo(routeMap);

        if (isCurrent) {
            currentRouteLayer = polyline;
            waypoints.forEach((wp, idx) => {
                if (idx === 0 || idx === waypoints.length - 1) return; // skip endpoints (map already has origin/dest markers)
                L.circleMarker([wp.lat, wp.lon], {
                    radius: 5,
                    fillColor: '#0d6efd',
                    color: '#fff',
                    weight: 2,
                    fillOpacity: 1
                }).addTo(routeMap).bindPopup(`<strong>${wp.name || 'Waypoint ' + idx}</strong>`);
            });
        } else {
            alternativeRouteLayers.push(polyline);
            polyline.bindPopup(`
                <strong>${route.name || 'Alternative Route'}</strong><br>
                Distance: ${formatNumber(route.distance_km)} km<br>
                Duration: ${formatNumber(route.estimated_duration_hours)} hrs<br>
                Cost: $${formatNumber(route.cost_usd)}<br>
                Risk Score: ${route.risk_score?.toFixed(2) ?? 'N/A'}
            `);
        }
    });

    // Auto fit to current + visible alternatives
    if (currentRouteLayer) {
        let bounds = currentRouteLayer.getBounds();
        alternativeRouteLayers.forEach(l => bounds.extend(l.getBounds()));
        routeMap.fitBounds(bounds, { padding: [40, 40] });
    }
}

// Update the route list panel
function updateRouteList(routes) {
    const routeList = document.getElementById('routeList');
    if (!routeList) {
        // Gracefully handle absence of the route list panel so the tab doesn't throw
        console.warn('updateRouteList: #routeList element not found in DOM. Skipping list render.');
        return;
    }
    routeList.innerHTML = '';

    routes.forEach((route, index) => {
        const routeItem = document.createElement('div');
        routeItem.className = `list-group-item ${route.is_current ? 'active' : ''}`;
        
        // Safely parse waypoints
        let waypoints = [];
        let waypointNames = 'Unknown Route';
        try {
            if (typeof route.waypoints === 'string') {
                // Try to parse as JSON first
                try {
                    waypoints = JSON.parse(route.waypoints);
                } catch {
                    // If not JSON, treat as simple string description
                    waypointNames = route.waypoints;
                    waypoints = [];
                }
            } else if (Array.isArray(route.waypoints)) {
                waypoints = route.waypoints;
            }
            
            if (waypoints.length > 0) {
                waypointNames = waypoints.map(wp => wp.name || 'Unknown').join(' → ');
            }
        } catch (e) {
            console.warn('Error parsing waypoints for route:', route.id, e);
            waypointNames = route.name || `Route ${index + 1}`;
        }
        
        routeItem.innerHTML = `
            <div class="d-flex w-100 justify-content-between">
                <h6 class="mb-1">
                    ${route.is_current ? 'Current Route' : (route.name || `Alternative ${index}`)}
                    ${route.is_recommended ? '<span class="badge bg-success ms-2">Recommended</span>' : ''}
                </h6>
                <div>
                    <div class="btn-group btn-group-sm" role="group">
                        ${!route.is_current ? `<button class="btn btn-outline-primary" data-action="make-current" data-id="${route.id}">Make Current</button>` : ''}
                        <button class="btn btn-outline-secondary" data-action="edit" data-id="${route.id}">Edit</button>
                        <button class="btn btn-outline-danger" data-action="delete" data-id="${route.id}">Delete</button>
                    </div>
                </div>
            </div>
            <small class="d-block mb-1">${waypointNames}</small>
            <div class="mt-2">
                <span class="badge bg-light text-dark me-1">
                    <i class="bi bi-geo-alt"></i> ${formatNumber(route.distance_km)} km
                </span>
                <span class="badge bg-light text-dark me-1">
                    <i class="bi bi-clock"></i> ${formatNumber(route.estimated_duration_hours)} hrs
                </span>
                <span class="badge bg-light text-dark me-1">
                    <i class="bi bi-currency-dollar"></i> ${formatNumber(route.cost_usd)}
                </span>
                <span class="badge bg-${getRiskBadgeColor(route.risk_score)} me-1">
                    Risk: ${route.risk_score.toFixed(2)}
                </span>
            </div>
        `;
        
        routeList.appendChild(routeItem);

        // Wire actions
        routeItem.querySelectorAll('button[data-action]').forEach(btn => {
            const action = btn.getAttribute('data-action');
            const id = parseInt(btn.getAttribute('data-id'), 10);
            if (action === 'make-current') {
                btn.addEventListener('click', () => makeRouteCurrent(id));
            } else if (action === 'edit') {
                btn.addEventListener('click', () => openRouteModal(id));
            } else if (action === 'delete') {
                btn.addEventListener('click', () => deleteRoute(id));
            }
        });
    });
}

// Toggle alternative routes visibility
function toggleAlternatives(event) {
    // Re-fetch current routes from API and re-display based on checkbox state
    loadRouteData();
}

// Start the reroute process
async function startRerouteProcess() {
    const modal = new bootstrap.Modal(document.getElementById('rerouteModal'));
    modal.show();
    
    // Reset to first step
    currentStep = 1;
    updateStepDisplay();
    
    // Load route options
    await loadRouteOptions();
}

// Load route optimization options
async function loadRouteOptions() {
    try {
        const response = await fetch(`/api/shipments/${window.shipmentData.id}/reroute-options`);
        routeOptions = await response.json();
        
        // Display step 1 content
        displayStep1Content();
    } catch (error) {
        console.error('Error loading route options:', error);
        showToast('Error', 'Failed to load route alternatives', 'error');
    }
}

// Display Step 1: Choose Alternative
function displayStep1Content() {
    const content = document.getElementById('stepContent');
    
    let html = '<h5>Available Route Alternatives</h5>';
    html += '<div class="row">';
    
    if (routeOptions && routeOptions.alternatives) {
        routeOptions.alternatives.forEach((route, index) => {
            const improvement = calculateImprovement(routeOptions.current_route, route);
            
            html += `
                <div class="col-md-6 mb-3">
                    <div class="card ${selectedRoute === route.route_id ? 'border-primary' : ''}" 
                         onclick="selectRouteOption(${route.route_id})" 
                         style="cursor: pointer;">
                        <div class="card-body">
                            <h6 class="card-title">
                                ${route.name}
                                ${route.is_recommended ? '<span class="badge bg-success float-end">Recommended</span>' : ''}
                            </h6>
                            <div class="mb-2">
                                <small class="text-muted d-block">
                                    <i class="bi bi-geo-alt"></i> Distance: ${formatNumber(route.metrics.distance_km)} km
                                    <span class="text-${improvement.distance > 0 ? 'danger' : 'success'}">
                                        (${improvement.distance > 0 ? '+' : ''}${formatNumber(improvement.distance)} km)
                                    </span>
                                </small>
                                <small class="text-muted d-block">
                                    <i class="bi bi-clock"></i> Duration: ${formatNumber(route.metrics.duration_hours)} hours
                                    <span class="text-${improvement.duration > 0 ? 'danger' : 'success'}">
                                        (${improvement.duration > 0 ? '+' : ''}${formatNumber(improvement.duration)} hrs)
                                    </span>
                                </small>
                                <small class="text-muted d-block">
                                    <i class="bi bi-currency-dollar"></i> Cost: $${formatNumber(route.metrics.cost_usd)}
                                    <span class="text-${improvement.cost > 0 ? 'danger' : 'success'}">
                                        (${improvement.cost > 0 ? '+' : ''}$${formatNumber(improvement.cost)})
                                    </span>
                                </small>
                            </div>
                            <div class="progress" style="height: 20px;">
                                <div class="progress-bar bg-${getRiskBadgeColor(route.metrics.risk_score)}" 
                                     style="width: ${route.metrics.risk_score * 100}%">
                                    Risk: ${route.metrics.risk_score.toFixed(2)}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
    } else {
        html += '<p class="text-muted">No alternative routes available.</p>';
    }
    
    html += '</div>';
    content.innerHTML = html;
}

// Display Step 2: Cost/ETA Analysis
function displayStep2Content() {
    const content = document.getElementById('stepContent');
    const selected = routeOptions.alternatives.find(r => r.route_id === selectedRoute);
    
    if (!selected) {
        content.innerHTML = '<p class="text-danger">Please select a route first.</p>';
        return;
    }
    
    const current = routeOptions.current_route;
    
    let html = `
        <h5>Cost/ETA Analysis</h5>
        <div class="row">
            <div class="col-md-6">
                <canvas id="comparisonChart" width="400" height="200"></canvas>
            </div>
            <div class="col-md-6">
                <h6>Impact Summary</h6>
                <table class="table table-sm">
                    <tbody>
                        <tr>
                            <td>Delivery Impact:</td>
                            <td>${selected.comparison.duration_delta > 0 ? 
                                `<span class="text-warning">Delayed by ${formatNumber(selected.comparison.duration_delta)} hours</span>` :
                                `<span class="text-success">Faster by ${formatNumber(Math.abs(selected.comparison.duration_delta))} hours</span>`
                            }</td>
                        </tr>
                        <tr>
                            <td>Cost Impact:</td>
                            <td>${selected.comparison.cost_delta > 0 ? 
                                `<span class="text-warning">Additional $${formatNumber(selected.comparison.cost_delta)}</span>` :
                                `<span class="text-success">Savings of $${formatNumber(Math.abs(selected.comparison.cost_delta))}</span>`
                            }</td>
                        </tr>
                        <tr>
                            <td>Risk Reduction:</td>
                            <td><span class="text-success">${formatNumber(Math.abs(selected.comparison.risk_delta) * 100)}%</span></td>
                        </tr>
                        <tr>
                            <td>Carbon Impact:</td>
                            <td>${selected.metrics.emissions_kg > current.metrics.emissions_kg ? 
                                `<span class="text-warning">+${formatNumber((selected.metrics.emissions_kg - current.metrics.emissions_kg) / 1000)} tCO₂e</span>` :
                                `<span class="text-success">-${formatNumber((current.metrics.emissions_kg - selected.metrics.emissions_kg) / 1000)} tCO₂e</span>`
                            }</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    `;
    
    content.innerHTML = html;
    
    // Draw comparison chart
    setTimeout(() => drawComparisonChart(current, selected), 100);
}

// Display Step 3: Compliance Check
function displayStep3Content() {
    const content = document.getElementById('stepContent');
    const selected = routeOptions.alternatives.find(r => r.route_id === selectedRoute);
    
    let html = `
        <h5>Compliance & Policy Check</h5>
        <div class="alert alert-info">
            <i class="bi bi-info-circle"></i> Checking route against company policies...
        </div>
        <ul class="list-group">
    `;
    
    // Simulate compliance checks
    const checks = [
        { name: 'Cost Threshold', status: selected.metrics.cost_usd < 200000, message: 'Within approved budget' },
        { name: 'Geo-Restrictions', status: true, message: 'No restricted territories' },
        { name: 'Carrier Approval', status: true, message: 'Carrier is approved vendor' },
        { name: 'Insurance Coverage', status: true, message: 'Route covered by insurance policy' },
        { name: 'Environmental Impact', status: selected.metrics.emissions_kg < 100000, message: 'Within carbon budget' }
    ];
    
    checks.forEach(check => {
        html += `
            <li class="list-group-item d-flex justify-content-between align-items-center">
                <div>
                    <strong>${check.name}</strong>
                    <small class="d-block text-muted">${check.message}</small>
                </div>
                <span class="badge bg-${check.status ? 'success' : 'warning'}">
                    ${check.status ? 'PASS' : 'REVIEW'}
                </span>
            </li>
        `;
    });
    
    html += `
        </ul>
        <div class="mt-3">
            <div class="form-check">
                <input class="form-check-input" type="checkbox" id="complianceConfirm">
                <label class="form-check-label" for="complianceConfirm">
                    I confirm this route change complies with all policies
                </label>
            </div>
        </div>
    `;
    
    content.innerHTML = html;
}

// Display Step 4: Review & Confirm
function displayStep4Content() {
    const content = document.getElementById('stepContent');
    const selected = routeOptions.alternatives.find(r => r.route_id === selectedRoute);
    
    let html = `
        <h5>Review & Confirm Route Change</h5>
        <div class="card">
            <div class="card-body">
                <h6 class="card-title">Route Change Summary</h6>
                <dl class="row">
                    <dt class="col-sm-4">Shipment:</dt>
                    <dd class="col-sm-8">${window.shipmentData.trackingNumber}</dd>
                    
                    <dt class="col-sm-4">New Route:</dt>
                    <dd class="col-sm-8">${selected.name}</dd>
                    
                    <dt class="col-sm-4">New ETA:</dt>
                    <dd class="col-sm-8">${new Date(Date.now() + selected.metrics.duration_hours * 3600000).toLocaleDateString()}</dd>
                    
                    <dt class="col-sm-4">Total Cost:</dt>
                    <dd class="col-sm-8">$${formatNumber(selected.metrics.cost_usd)}</dd>
                    
                    <dt class="col-sm-4">Risk Score:</dt>
                    <dd class="col-sm-8">
                        <span class="badge bg-${getRiskBadgeColor(selected.metrics.risk_score)}">
                            ${selected.metrics.risk_score.toFixed(2)}
                        </span>
                    </dd>
                </dl>
                
                <div class="alert alert-warning">
                    <i class="bi bi-exclamation-triangle"></i>
                    <strong>Important:</strong> This action will update the shipment route and notify all stakeholders.
                </div>
                
                <div class="form-group">
                    <label for="rerouteReason">Reason for Reroute (Optional):</label>
                    <textarea class="form-control" id="rerouteReason" rows="2" 
                              placeholder="Enter any additional notes..."></textarea>
                </div>
            </div>
        </div>
    `;
    
    content.innerHTML = html;
}

// Navigate to next step
function nextStep() {
    if (currentStep === 1 && !selectedRoute) {
        showToast('Selection Required', 'Please select a route alternative', 'warning');
        return;
    }
    
    if (currentStep === 3) {
        const complianceCheck = document.getElementById('complianceConfirm');
        if (!complianceCheck || !complianceCheck.checked) {
            showToast('Confirmation Required', 'Please confirm compliance', 'warning');
            return;
        }
    }
    
    if (currentStep < 4) {
        currentStep++;
        updateStepDisplay();
    }
}

// Navigate to previous step
function prevStep() {
    if (currentStep > 1) {
        currentStep--;
        updateStepDisplay();
    }
}

// Update step display
function updateStepDisplay() {
    // Update stepper visual
    document.querySelectorAll('.step').forEach((step, index) => {
        if (index + 1 <= currentStep) {
            step.classList.add('active');
        } else {
            step.classList.remove('active');
        }
    });
    
    // Update content
    switch(currentStep) {
        case 1:
            displayStep1Content();
            break;
        case 2:
            displayStep2Content();
            break;
        case 3:
            displayStep3Content();
            break;
        case 4:
            displayStep4Content();
            break;
    }
    
    // Update buttons
    document.getElementById('prevStep').style.display = currentStep > 1 ? 'block' : 'none';
    document.getElementById('nextStep').style.display = currentStep < 4 ? 'block' : 'none';
    document.getElementById('confirmReroute').style.display = currentStep === 4 ? 'block' : 'none';
}

// Select a route option
function selectRouteOption(routeId) {
    selectedRoute = routeId;
    displayStep1Content(); // Refresh to show selection
}

// Preview a route on the map
function previewRoute(routeId) {
    // Switch to route tab
    const routeTab = new bootstrap.Tab(document.getElementById('route-tab'));
    routeTab.show();
    
    // Highlight the selected route
    // This would ideally fetch and highlight the specific route
    showToast('Preview', `Previewing route ${routeId}`, 'info');
}

// Confirm the reroute
async function confirmReroute() {
    const reason = document.getElementById('rerouteReason')?.value || '';
    
    try {
        const response = await fetch(`/api/shipments/${window.shipmentData.id}/reroute`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                route_id: selectedRoute,
                reason: reason,
                approval_override: false
            })
        });
        
    const result = await response.json();
    const ok = result.success === true || result.status === 'success';
    if (ok) {
            showToast('Success', 'Route successfully updated', 'success');
            
            // Close modal
            bootstrap.Modal.getInstance(document.getElementById('rerouteModal')).hide();
            
            // Reload route data
            loadRouteData();
            
            // Reload page after a short delay
            setTimeout(() => location.reload(), 2000);
        } else {
            showToast('Error', result.message || 'Failed to update route', 'error');
        }
    } catch (error) {
        console.error('Error confirming reroute:', error);
        showToast('Error', 'Failed to update route', 'error');
    }
}

// Trigger route optimization
async function triggerRouteOptimization() {
    const shipmentId = window.shipmentData.id;
    const button = document.querySelector('.optimize-route-btn');
    
    try {
        // Disable button and show loading state
        if (button) {
            button.disabled = true;
            button.innerHTML = '<i class="bi bi-arrow-repeat"></i> Optimizing...';
        }

        showToast('Processing', 'Requesting route optimization...', 'info');

        const response = await fetch(`/api/shipments/${shipmentId}/optimize`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin' // Include cookies for authentication
        });

        // Check if we were redirected to login page
        if (response.redirected && response.url.includes('/auth/login')) {
            showToast('Authentication Required', 'Please log in to optimize routes', 'warning');
            // Redirect to login page with return URL
            window.location.href = `/auth/login?next=${encodeURIComponent(window.location.pathname)}`;
            return;
        }

        let result;
        try {
            result = await response.json();
        } catch (jsonError) {
            // If JSON parsing fails, likely got HTML response (login page)
            if (response.status === 200 && response.headers.get('content-type')?.includes('text/html')) {
                showToast('Authentication Required', 'Please log in to optimize routes', 'warning');
                window.location.href = `/auth/login?next=${encodeURIComponent(window.location.pathname)}`;
                return;
            }
            throw new Error('Invalid response format');
        }
        
        if (response.ok && result.status === 'success') {
            showToast('Success', 'Route optimization requested. New routes will be generated shortly.', 'success');
            
            // Reload route data after a short delay to allow background processing
            setTimeout(async () => {
                await loadRouteData();
                showToast('Updated', 'Routes have been refreshed with new optimization results', 'success');
            }, 3000);
            
        } else {
            showToast('Error', result.message || result.error || 'Failed to optimize routes', 'error');
        }
        
    } catch (error) {
        console.error('Error triggering route optimization:', error);
        showToast('Error', 'Failed to request route optimization', 'error');
    } finally {
        // Re-enable button
        if (button) {
            button.disabled = false;
            button.innerHTML = '<i class="bi bi-arrow-repeat"></i> Optimize Route';
        }
    }
}

// Draw comparison chart
function drawComparisonChart(current, selected) {
    const canvas = document.getElementById('comparisonChart');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Distance (km)', 'Duration (hrs)', 'Cost ($1000)', 'Risk Score'],
            datasets: [{
                label: 'Current Route',
                data: [
                    current.metrics.distance_km,
                    current.metrics.duration_hours,
                    current.metrics.cost_usd / 1000,
                    current.metrics.risk_score * 100
                ],
                backgroundColor: 'rgba(13, 110, 253, 0.5)',
                borderColor: 'rgba(13, 110, 253, 1)',
                borderWidth: 1
            }, {
                label: 'Selected Alternative',
                data: [
                    selected.metrics.distance_km,
                    selected.metrics.duration_hours,
                    selected.metrics.cost_usd / 1000,
                    selected.metrics.risk_score * 100
                ],
                backgroundColor: 'rgba(40, 167, 69, 0.5)',
                borderColor: 'rgba(40, 167, 69, 1)',
                borderWidth: 1
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

// Calculate improvement metrics
function calculateImprovement(current, alternative) {
    if (!current) return { distance: 0, duration: 0, cost: 0 };
    
    return {
        distance: alternative.metrics.distance_km - current.metrics.distance_km,
        duration: alternative.metrics.duration_hours - current.metrics.duration_hours,
        cost: alternative.metrics.cost_usd - current.metrics.cost_usd
    };
}

// Explain recommendation
async function explainRecommendation(recommendationId) {
    try {
        const response = await fetch(`/api/recommendations/${recommendationId}/explain`);
        const data = await response.json();
        
        const modal = new bootstrap.Modal(document.getElementById('explanationModal'));
        const content = document.getElementById('explanationContent');
        
        content.innerHTML = `
            <h6>Recommendation Rationale</h6>
            <p>${data.rationale || 'No detailed explanation available.'}</p>
            
            <h6>Decision Factors</h6>
            <ul>
                ${data.factors ? data.factors.map(f => `<li>${f}</li>`).join('') : '<li>No factors available</li>'}
            </ul>
            
            <h6>Data Sources</h6>
            <ul>
                ${data.sources ? data.sources.map(s => `<li>${s}</li>`).join('') : '<li>No sources available</li>'}
            </ul>
            
            <h6>Confidence Score</h6>
            <div class="progress" style="height: 25px;">
                <div class="progress-bar" style="width: ${(data.confidence || 0) * 100}%">
                    ${((data.confidence || 0) * 100).toFixed(0)}%
                </div>
            </div>
        `;
        
        modal.show();
    } catch (error) {
        console.error('Error fetching explanation:', error);
        showToast('Error', 'Failed to load explanation', 'error');
    }
}

// Approve recommendation
async function approveRecommendation(recommendationId) {
    if (!confirm('Are you sure you want to approve this recommendation?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/recommendations/${recommendationId}/approve`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            showToast('Success', 'Recommendation approved', 'success');
            location.reload();
        } else {
            showToast('Error', result.message || 'Failed to approve recommendation', 'error');
        }
    } catch (error) {
        console.error('Error approving recommendation:', error);
        showToast('Error', 'Failed to approve recommendation', 'error');
    }
}

// Connect to WebSocket for real-time updates
function connectWebSocket() {
    if (typeof io !== 'undefined') {
        const socket = io();
        
        socket.on('shipment_updated', function(data) {
            if (data.shipment_id === window.shipmentData.id) {
                showToast('Update', 'Shipment information updated', 'info');
                // Reload relevant sections
                if (routeMap) {
                    loadRouteData();
                }
            }
        });
        
        socket.on('recommendation_created', function(data) {
            if (data.shipment_id === window.shipmentData.id) {
                showToast('New Recommendation', data.message || 'New recommendation available', 'info');
                location.reload();
            }
        });
    }
}

// Helper function to format numbers
function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return new Intl.NumberFormat('en-US').format(Math.round(num));
}

// Helper function to get risk badge color
function getRiskBadgeColor(riskScore) {
    if (riskScore > 0.7) return 'danger';
    if (riskScore > 0.5) return 'warning';
    return 'success';
}

// Helper function to show toast notifications
function showToast(title, message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer') || createToastContainer();
    
    const toastHtml = `
        <div class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header bg-${type === 'error' ? 'danger' : type === 'success' ? 'success' : type === 'warning' ? 'warning' : 'info'} text-white">
                <strong class="me-auto">${title}</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        </div>
    `;
    
    const toastElement = document.createElement('div');
    toastElement.innerHTML = toastHtml;
    toastContainer.appendChild(toastElement.firstElementChild);
    
    const toast = new bootstrap.Toast(toastContainer.lastElementChild);
    toast.show();
}

// Create toast container if it doesn't exist
function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container position-fixed top-0 end-0 p-3';
    container.style.zIndex = '9999';
    document.body.appendChild(container);
    return container;
}

// ---------- Manual Route CRUD ----------

function openRouteModal(routeId = null) {
    // Reset form
    document.getElementById('routeForm').reset();
    document.getElementById('routeId').value = routeId ? String(routeId) : '';
    document.getElementById('routeModalLabel').innerText = routeId ? 'Edit Route' : 'Add Route';
    // Prefill waypoints with a sensible template for add
    if (!routeId) {
        const template = [
            { lat: window.shipmentData.origin.lat, lon: window.shipmentData.origin.lon, name: window.shipmentData.origin.name || 'Origin', type: 'origin' },
            { lat: window.shipmentData.destination.lat, lon: window.shipmentData.destination.lon, name: window.shipmentData.destination.name || 'Destination', type: 'destination' }
        ];
        document.getElementById('waypointsJson').value = JSON.stringify(template, null, 2);
        if (routeModalInstance) routeModalInstance.show();
        return;
    }

    // Fetch existing route to prefill
    fetch(`/api/routes/${routeId}`)
        .then(r => r.json())
        .then(route => {
            document.getElementById('routeName').value = route.name || '';
            document.getElementById('routeType').value = (route.route_type || 'SEA');
            document.getElementById('isCurrent').checked = !!route.is_current;
            document.getElementById('isRecommended').checked = !!route.is_recommended;
            document.getElementById('distanceKm').value = route.total_distance_km ?? route.distance_km ?? '';
            document.getElementById('durationHours').value = route.estimated_duration_hours ?? '';
            document.getElementById('costUsd').value = route.estimated_cost ?? route.cost_usd ?? '';
            document.getElementById('emissionsKg').value = route.estimated_emissions_kg ?? route.carbon_emissions_kg ?? '';
            document.getElementById('riskScore').value = route.risk_score ?? '';
            document.getElementById('waypointsJson').value = JSON.stringify(route.waypoints || [], null, 2);
            if (routeModalInstance) routeModalInstance.show();
        })
        .catch(() => showToast('Error', 'Failed to load route details', 'error'));
}

async function saveRouteFromModal() {
    const routeId = document.getElementById('routeId').value;
    const name = document.getElementById('routeName').value?.trim();
    const route_type = document.getElementById('routeType').value || 'SEA';
    const is_current = document.getElementById('isCurrent').checked;
    const is_recommended = document.getElementById('isRecommended').checked;
    const distance_km = parseFloat(document.getElementById('distanceKm').value) || 0;
    const estimated_duration_hours = parseFloat(document.getElementById('durationHours').value) || 0;
    const cost_usd = parseFloat(document.getElementById('costUsd').value) || 0;
    const carbon_emissions_kg = parseFloat(document.getElementById('emissionsKg').value) || 0;
    const risk_score = parseFloat(document.getElementById('riskScore').value);
    let waypoints = [];
    try {
        waypoints = JSON.parse(document.getElementById('waypointsJson').value || '[]');
        if (!Array.isArray(waypoints)) throw new Error('Waypoints must be an array');
    } catch (e) {
        showToast('Invalid Waypoints', e.message, 'warning');
        return;
    }

    const payload = {
        route_type,
        waypoints,
        distance_km,
        estimated_duration_hours,
        cost_usd,
        carbon_emissions_kg,
        risk_score: isNaN(risk_score) ? 0 : risk_score,
        is_current,
        is_recommended,
        metadata: { name }
    };

    try {
        let resp;
        if (routeId) {
            resp = await fetch(`/api/routes/${routeId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } else {
            resp = await fetch(`/api/shipments/${window.shipmentData.id}/routes`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        }
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Failed to save route');
        showToast('Saved', routeId ? 'Route updated' : 'Route created', 'success');
        if (routeModalInstance) routeModalInstance.hide();
        await loadRouteData();
    } catch (e) {
        showToast('Error', e.message, 'error');
    }
}

async function deleteRoute(routeId) {
    if (!confirm('Delete this route? This cannot be undone.')) return;
    try {
        const resp = await fetch(`/api/routes/${routeId}`, { method: 'DELETE' });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Failed to delete');
        showToast('Deleted', 'Route removed', 'success');
        await loadRouteData();
    } catch (e) {
        showToast('Error', e.message, 'error');
    }
}

async function makeRouteCurrent(routeId) {
    try {
        const resp = await fetch(`/api/shipments/${window.shipmentData.id}/select-route`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ route_id: routeId })
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.message || 'Failed to set current route');
        showToast('Updated', 'Current route updated', 'success');
        await loadRouteData();
    } catch (e) {
        showToast('Error', e.message, 'error');
    }
}

// Export functions for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        initializeShipmentPage,
        loadRouteData,
        startRerouteProcess,
        confirmReroute
    };
}