// app/static/js/dashboard.js
// This file contains the JavaScript code for the dashboard functionality


// Dashboard functionality

// Debug: Direct console log to ensure it's showing
console.log("DASHBOARD.JS: Direct console log test");

// We're using DOMContentLoaded in main_dashboard.html instead of window.onload
// to prevent double initialization


let dashboardMap = null;
let riskMarkers = [];
let shipmentMarkers = {};
let charts = {
    etaVariance: null,
    riskTrend: null
};

// Initialize dashboard
function initializeDashboard() {
    console.log('DASHBOARD.JS: Initializing dashboard...');
    
    try {
        // Initialize dashboard map if not already initialized
        if (!dashboardMap) {
            console.log('DASHBOARD.JS: Setting up map');
            initializeDashboardMap();
        } else {
            console.log('DASHBOARD.JS: Map already initialized');
        }
        
        console.log('DASHBOARD.JS: Setting up charts');
        initializeCharts();
        
        console.log('DASHBOARD.JS: Setting up sort toggles');
        initializeSortToggles();
        
        console.log('DASHBOARD.JS: Loading dashboard data');
        loadDashboardData();
        
        // Set up auto-refresh if not already set
        if (!window.dashboardRefreshInterval) {
            console.log('DASHBOARD.JS: Setting up auto-refresh');
            window.dashboardRefreshInterval = setInterval(refreshDashboard, 30000); // Every 30 seconds
        }
    } catch (error) {
        console.error('DASHBOARD.JS ERROR:', error);
        console.error('Error details:', error.message);
    }
}

// Initialize dashboard map
function initializeDashboardMap() {
    const mapElement = document.getElementById('disruptionMap');
    if (!mapElement) {
        console.error('Map element not found');
        return;
    }
    
    dashboardMap = L.map('disruptionMap').setView([20, 0], 2);
    
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(dashboardMap);
    
    // Add controls
    L.control.scale().addTo(dashboardMap);
    
    // Handle view toggle
    const mapGlobal = document.getElementById('mapGlobal');
    const mapRoutes = document.getElementById('mapRoutes');
    
    if (mapGlobal) {
        mapGlobal.addEventListener('change', function() {
            if (this.checked) {
                localStorage.setItem('dashboardMapView', 'global');
                showGlobalView();
            }
        });
    }
    if (mapRoutes) {
        mapRoutes.addEventListener('change', function() {
            if (this.checked) {
                localStorage.setItem('dashboardMapView', 'routes');
                showRoutesView();
            }
        });
    }
    
    // Restore saved view preference or default to routes view (to show actual content)
    const savedView = localStorage.getItem('dashboardMapView') || 'routes';
    
    if (savedView === 'routes' && mapRoutes) {
        mapRoutes.checked = true;
        // Call showRoutesView after a short delay to ensure map is fully initialized
        setTimeout(() => showRoutesView(), 100);
    } else if (savedView === 'global' && mapGlobal) {
        mapGlobal.checked = true;
        // Call showGlobalView after a short delay to ensure map is fully initialized
        setTimeout(() => showGlobalView(), 100);
    }
}

// Initialize charts
function initializeCharts() {
    // ETA Variance Chart
    const etaCtx = document.getElementById('etaVarianceChart');
    if (etaCtx) {
        charts.etaVariance = new Chart(etaCtx.getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Planned',
                    data: [],
                    borderColor: 'rgb(54, 162, 235)',
                    backgroundColor: 'rgba(54, 162, 235, 0.1)',
                    tension: 0.1
                }, {
                    label: 'Actual',
                    data: [],
                    borderColor: 'rgb(255, 99, 132)',
                    backgroundColor: 'rgba(255, 99, 132, 0.1)',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                    },
                    title: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Transit Time (days)'
                        }
                    }
                }
            }
        });
    }
}

// Initialize sort toggles for shipments at risk table
function initializeSortToggles() {
    console.log('DASHBOARD.JS: Setting up sort toggles');
    
    const sortByRisk = document.getElementById('sortByRisk');
    const sortByRecent = document.getElementById('sortByRecent');
    
    if (sortByRisk && sortByRecent) {
        [sortByRisk, sortByRecent].forEach(toggle => {
            toggle.addEventListener('change', function() {
                if (this.checked) {
                    console.log('DASHBOARD.JS: Sort changed to:', this.value);
                    loadShipmentsAtRisk(this.value);
                }
            });
        });
    } else {
        console.warn('DASHBOARD.JS: Sort toggle elements not found');
    }
}

// Track if we're already loading data to prevent multiple simultaneous calls
let isLoadingDashboardData = false;

// Load dashboard data
async function loadDashboardData() {
    // Prevent multiple simultaneous calls that could trigger loops
    if (isLoadingDashboardData) {
        console.log('Already loading dashboard data, skipping duplicate call');
        return;
    }
    
    isLoadingDashboardData = true;
    
    try {
        // Load KPIs
        console.log('Fetching KPI data...');
        const kpiResponse = await fetch('/api/kpis');
        const kpiData = await kpiResponse.json();
        console.log('KPI data received:', kpiData);
        updateKPIs(kpiData.kpis);
        
        // Load risks for map
        console.log('Fetching risk data...');
        const riskResponse = await fetch('/api/risks');
        const riskData = await riskResponse.json();
        console.log('Risk data received:', riskData);
        updateRiskMap(riskData.risks);
        
        // Load shipments at risk (using default sort)
        await loadShipmentsAtRisk();
        
    // Recommendations (refactored module)
    Recommendations.fetchAndRender();
        
        // Load ETA variance data
        console.log('Fetching ETA variance data...');
        const etaResponse = await fetch('/api/eta-variance');
        const etaData = await etaResponse.json();
        console.log('ETA variance data received:', etaData);
        updateETAChart(etaData.eta_variance);
        
    } catch (error) {
        console.error('Error loading dashboard data:', error);
        console.error('Error message:', error.message);
        console.error('Error stack:', error.stack);
        if (window.showToast) {
            window.showToast('Error', 'Failed to load dashboard data: ' + error.message, 'danger');
        }
    } finally {
        // Reset the loading flag
        isLoadingDashboardData = false;
        console.log('Dashboard data loading complete');
    }
}

// Load shipments at risk with sorting
async function loadShipmentsAtRisk(sortBy = 'recent') {
    try {
        console.log('Fetching shipments at risk data with sort:', sortBy);
        
        // Show loading state
        const tbody = document.getElementById('shipmentsAtRiskTable');
        if (tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" class="text-center py-3">
                        <div class="spinner-border spinner-border-sm me-2" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        Loading shipments...
                    </td>
                </tr>
            `;
        }
        
        const shipmentResponse = await fetch(`/api/shipments-at-risk?sort=${sortBy}`);
        const shipmentData = await shipmentResponse.json();
        console.log('Shipments at risk data received:', shipmentData);
        updateShipmentsAtRisk(shipmentData.shipments_at_risk || []);
    } catch (error) {
        console.error('Error loading shipments at risk:', error);
        // Show error state in table
        const tbody = document.getElementById('shipmentsAtRiskTable');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-danger py-3">Error loading shipments data</td></tr>';
        }
    }
}

// Update KPIs
function updateKPIs(kpis) {
    // Risk Index
    const riskBar = document.getElementById('riskIndexBar');
    const riskValue = document.getElementById('riskIndexValue');
    if (riskBar && riskValue) {
        const percentage = Math.round(kpis.risk_index * 100);
        riskBar.style.width = percentage + '%';
        riskBar.className = 'progress-bar';
        if (kpis.risk_index >= 0.7) {
            riskBar.classList.add('bg-danger');
        } else if (kpis.risk_index >= 0.5) {
            riskBar.classList.add('bg-warning');
        } else {
            riskBar.classList.add('bg-success');
        }
        riskValue.textContent = kpis.risk_index.toFixed(2);
    }
    
    // On-time Rate
    const onTimeElement = document.getElementById('onTimeRate');
    if (onTimeElement) {
        onTimeElement.textContent = kpis.on_time_rate + '%';
    }
    
    // Open Alerts
    const alertsElement = document.getElementById('openAlerts');
    if (alertsElement) {
        alertsElement.textContent = kpis.open_alerts;
    }
    
    // Update alert severity breakdown
    const alerts_by_severity = kpis.alerts_by_severity || {};
    const criticalElement = document.getElementById('criticalAlerts');
    const highElement = document.getElementById('highAlerts');
    const mediumElement = document.getElementById('mediumAlerts');
    const lowElement = document.getElementById('lowAlerts');
    
    if (criticalElement) criticalElement.textContent = `${alerts_by_severity.critical || 0} critical`;
    if (highElement) highElement.textContent = `${alerts_by_severity.high || 0} high`;
    if (mediumElement) mediumElement.textContent = `${alerts_by_severity.medium || 0} medium`;
    if (lowElement) lowElement.textContent = `${alerts_by_severity.low || 0} low`;
    
    // Inventory at Risk
    const invElement = document.getElementById('inventoryAtRisk');
    if (invElement) {
        invElement.textContent = kpis.inventory_at_risk;
    }
}

// Update risk map
function updateRiskMap(risks) {
    if (!dashboardMap) return;
    
    // Clear existing markers
    riskMarkers.forEach(marker => dashboardMap.removeLayer(marker));
    riskMarkers = [];
    
    // Add risk markers
    risks.forEach(risk => {
        if (risk.lat && risk.lon) {
            const severity = risk.severity || 'medium';
            const color = {
                'high': '#dc3545',
                'medium': '#ffc107',
                'low': '#28a745'
            }[severity] || '#6c757d';
            
            const marker = L.circleMarker([risk.lat, risk.lon], {
                radius: 8 + (risk.impact || 1) * 2,
                fillColor: color,
                color: '#fff',
                weight: 2,
                opacity: 1,
                fillOpacity: 0.8
            });
            
            marker.bindPopup(`
                <strong>${risk.title}</strong><br>
                Type: ${risk.type}<br>
                Severity: ${severity}<br>
                ${risk.description ? risk.description.substring(0, 100) + '...' : ''}
            `);
            
            marker.addTo(dashboardMap);
            riskMarkers.push(marker);
        }
    });
}

// Update shipments at risk table
function updateShipmentsAtRisk(shipments) {
    const tbody = document.getElementById('shipmentsAtRiskTable');
    if (!tbody) return;
    
    if (shipments.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-3">No shipments at risk</td></tr>';
        return;
    }
    
    tbody.innerHTML = shipments.map((shipment, index) => `
        <tr data-shipment-id="${shipment.id}">
            <td>${index + 1}</td>
            <td><a href="/shipments/${shipment.id}">${shipment.reference}</a></td>
            <td>${shipment.carrier || 'Unknown'}</td>
            <td>${shipment.origin} → ${shipment.destination}</td>
            <td>${formatDate(shipment.eta)}</td>
            <td class="status-cell">
                <span class="badge bg-${getRiskColor(shipment.risk_level)}">${shipment.risk_level}</span>
            </td>
            <td>${shipment.risk_cause || 'Unknown'}</td>
            <td>
                <a href="/shipments/${shipment.id}" class="btn btn-sm btn-outline-primary">View</a>
                <button class="btn btn-sm btn-outline-warning" onclick="initiateReroute(${shipment.id})">Re-route</button>
            </td>
        </tr>
    `).join('');
}

// -----------------------------------------------------------------------------
// Recommendations module (refactored to avoid race conditions & stuck spinner)
// -----------------------------------------------------------------------------
const Recommendations = (function() {
    let fetching = false;
    let lastRenderCount = 0;
    let currentList = [];

    function getContainer(ensure=true) {
        let el = document.getElementById('recommendationsListNew');
        if (!el && ensure) {
            const card = document.getElementById('agentRecommendationsCard');
            if (card) {
                const body = card.querySelector('.card-body');
                if (body) {
                    el = document.createElement('div');
                    el.id = 'recommendationsListNew';
                    body.appendChild(el);
                    console.log('DASHBOARD.JS: Created recommendations container dynamically');
                }
            }
        }
        return el;
    }

    function render(list, meta) {
        const container = getContainer();
        if (!container) {
            console.error('DASHBOARD.JS: Unable to locate or create recommendations container');
            return;
        }

        if (!Array.isArray(list) || list.length === 0) {
            container.innerHTML = '<p class="text-center text-muted py-3 mb-0">No active recommendations</p>';
            lastRenderCount = 0;
            console.log('DASHBOARD.JS: Rendered empty recommendations state');
            return;
        }

        lastRenderCount = list.length;
        currentList = list;
        console.log(`DASHBOARD.JS: Rendering ${lastRenderCount} recommendations`);

        const html = list.map((rec, idx) => {
            if (!rec) return '';
            const title = rec.title || 'Untitled Recommendation';
            const description = rec.description || 'No description provided';
            const agent = rec.agent || 'AI Agent';
            const confidence = typeof rec.confidence === 'number' ? rec.confidence : 0.5;
            const severity = (rec.severity || 'medium').toLowerCase();
            const id = rec.id ?? idx;
            // XAI rationale snippet (first 160 chars)
            let rationaleSnippet = '';
            if (rec.rationale) {
                rationaleSnippet = rec.rationale.substring(0, 160);
                if (rec.rationale.length > 160) rationaleSnippet += '...';
            }
            // Factors badges
            let factorsHtml = '';
            const xai = rec.xai || {};
            const factors = Array.isArray(xai.factors) ? xai.factors.slice(0,6) : [];
            const improvements = xai.improvements && typeof xai.improvements === 'object' ? xai.improvements : null;
            if (factors.length || improvements) {
                factorsHtml += '<div class="mt-2 small xai-factors"><div class="d-flex flex-wrap gap-1">';
                factors.forEach(f => {
                    factorsHtml += `<span class="badge bg-secondary-subtle border text-secondary-emphasis">${f}</span>`;
                });
                if (improvements) {
                    Object.entries(improvements).forEach(([k,v]) => {
                        if (v) factorsHtml += `<span class=\"badge bg-light border text-muted\">${k.replace(/_/g,' ')}: ${v}</span>`;
                    });
                }
                if (!factors.length && !improvements && rationaleSnippet) {
                    factorsHtml += '<span class="badge bg-info-subtle border text-info-emphasis">Rationale</span>';
                }
                factorsHtml += '</div></div>';
            }
            return `
                <div class="card mb-2 recommendation-card shadow-sm" data-recommendation-id="${id}">
                  <div class="card-body py-3">
                    <div class="d-flex justify-content-between align-items-start">
                      <div class="me-3 flex-grow-1">
                        <h6 class="card-title mb-1">${title}</h6>
                        <p class="card-text text-muted small mb-2">${description}</p>
                        ${ rationaleSnippet ? `<div class="xai-snippet small text-secondary mb-2"><strong>Why:</strong> ${rationaleSnippet}</div>` : '' }
                        ${ factorsHtml }
                        <small class="text-muted">by ${agent} • Confidence: ${Math.round(confidence * 100)}%</small>
                      </div>
                      <span class="badge bg-${getSeverityColor(severity)} text-uppercase">${severity}</span>
                    </div>
                    <div class="mt-3 d-flex gap-2">
                      <button class="btn btn-sm btn-primary explain-btn" data-id="${id}" title="Explain"><i class="bi bi-info-circle"></i></button>
                      <button class="btn btn-sm btn-success approve-btn" data-id="${id}" title="Approve"><i class="bi bi-check-circle"></i></button>
                      <button class="btn btn-sm btn-outline-secondary edit-btn" data-id="${id}" title="Edit"><i class="bi bi-pencil"></i></button>
                    </div>
                  </div>
                </div>`;
        }).join('');

        container.innerHTML = html;

        // Event binding
        container.querySelectorAll('.explain-btn').forEach(btn => {
            const id = btn.getAttribute('data-id');
            btn.addEventListener('click', () => openXaiExplain(id));
        });
        container.querySelectorAll('.approve-btn').forEach(btn => {
            const id = btn.getAttribute('data-id');
            btn.addEventListener('click', () => approveRecommendation(id));
        });
        container.querySelectorAll('.edit-btn').forEach(btn => {
            const id = btn.getAttribute('data-id');
            btn.addEventListener('click', () => editRecommendation(id));
        });
    }

    async function fetchAndRender(force=false, page=1) {
        if (fetching) {
            console.log('DASHBOARD.JS: Recommendation fetch already in progress, skipping');
            return;
        }
        fetching = true;
        const container = getContainer();
        if (container && (force || lastRenderCount === 0)) {
            container.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm" role="status"><span class="visually-hidden">Loading...</span></div></div>';
        }
        try {
            const searchEl = document.getElementById('recSearch');
            const sevEl = document.getElementById('recSeverity');
            const qParams = new URLSearchParams();
            qParams.set('include_xai','1');
            qParams.set('page', page);
            qParams.set('per_page', 10);
            if (searchEl && searchEl.value.trim()) qParams.set('search', searchEl.value.trim());
            if (sevEl && sevEl.value) qParams.set('severity', sevEl.value);
            const resp = await fetch(`/api/recommendations?${qParams.toString()}&trigger_generation=1`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            const list = Array.isArray(data) ? data : data.recommendations;
            render(Array.isArray(list) ? list : [], {
                page: data.page,
                pages: data.pages,
                total: data.total,
                per_page: data.per_page
            });
            // TODO: add pagination controls (lightweight inline for now)
            if (container && data.pages && data.pages > 1) {
                let pager = container.querySelector('.rec-pager');
                if (!pager) {
                    pager = document.createElement('div');
                    pager.className = 'rec-pager d-flex justify-content-between align-items-center mt-2';
                    container.appendChild(pager);
                }
                pager.innerHTML = `
                    <div class="small text-muted">Page ${data.page} of ${data.pages} • ${data.total} total</div>
                    <div>
                        <button class="btn btn-sm btn-outline-secondary me-1" ${data.page<=1?'disabled':''} data-role="prev">Prev</button>
                        <button class="btn btn-sm btn-outline-secondary" ${data.page>=data.pages?'disabled':''} data-role="next">Next</button>
                    </div>`;
                pager.querySelectorAll('button[data-role]').forEach(btn => {
                    btn.addEventListener('click', () => {
                        const role = btn.getAttribute('data-role');
                        const target = role === 'prev' ? (data.page-1) : (data.page+1);
                        fetchAndRender(true, target);
                    });
                });
            }
        } catch (e) {
            console.error('DASHBOARD.JS: Failed to fetch recommendations', e);
            if (container) {
                container.innerHTML = '<div class="alert alert-danger mb-0">Failed to load recommendations.</div>';
            }
        } finally {
            fetching = false;
        }
    }

    function openXaiExplain(id) {
        const rec = currentList.find(r => String(r.id) === String(id));
        if (rec && (rec.xai || rec.rationale)) {
            showXaiModal(rec);
        } else {
            // Fallback fetch detailed explanation endpoint
            explainRecommendation(id);
        }
    }

    return { fetchAndRender, render, openXaiExplain };
})();

// Update ETA variance chart
function updateETAChart(etaData) {
    if (!charts.etaVariance || !etaData) return;
    
    charts.etaVariance.data.labels = etaData.dates;
    charts.etaVariance.data.datasets[0].data = etaData.planned;
    charts.etaVariance.data.datasets[1].data = etaData.actual;
    charts.etaVariance.update();
}

// View toggles
function showGlobalView() {
    if (!dashboardMap) return;
    
    // Clear existing markers and routes
    riskMarkers.forEach(marker => dashboardMap.removeLayer(marker));
    riskMarkers = [];
    
    // Reset map view to global
    dashboardMap.setView([20, 0], 2);
    
    // Load and display global disruptions, alerts, and risk zones
    fetch('/api/global-disruptions')
        .then(response => response.json())
        .then(data => {
            const disruptions = data.disruptions || [];
            
            // Add risk zones and threat markers
            disruptions.forEach(disruption => {
                let icon, color;
                
                switch(disruption.type) {
                    case 'weather':
                        icon = '🌪️';
                        color = '#ffc107';
                        break;
                    case 'geopolitical':
                        icon = '⚠️';
                        color = '#dc3545';
                        break;
                    case 'port_congestion':
                        icon = '🚢';
                        color = '#fd7e14';
                        break;
                    case 'supply_shortage':
                        icon = '📦';
                        color = '#6f42c1';
                        break;
                    default:
                        icon = '⚡';
                        color = '#6c757d';
                }
                
                const marker = L.marker(disruption.coordinates, {
                    icon: L.divIcon({
                        className: 'disruption-marker',
                        html: `<div style="background-color: ${color}; color: white; padding: 4px 8px; border-radius: 50%; font-size: 12px; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">${icon}</div>`,
                        iconSize: [30, 30],
                        iconAnchor: [15, 15]
                    })
                }).addTo(dashboardMap);
                
                const popupContent = `
                    <div class="disruption-popup">
                        <h6 class="mb-2"><span class="badge bg-${getRiskColorFromType(disruption.type)}">${disruption.severity}</span> ${disruption.title}</h6>
                        <p class="mb-1"><strong>Type:</strong> ${disruption.type.replace('_', ' ').toUpperCase()}</p>
                        <p class="mb-1"><strong>Region:</strong> ${disruption.region}</p>
                        <p class="mb-1"><strong>Impact:</strong> ${disruption.description}</p>
                        <small class="text-muted">Last updated: ${formatDate(disruption.updated_at)}</small>
                    </div>
                `;
                
                marker.bindPopup(popupContent);
                riskMarkers.push(marker);
                
                // Add risk circle for area of effect
                if (disruption.radius) {
                    const circle = L.circle(disruption.coordinates, {
                        color: color,
                        fillColor: color,
                        fillOpacity: 0.1,
                        radius: disruption.radius * 1000 // Convert km to meters
                    }).addTo(dashboardMap);
                    
                    riskMarkers.push(circle);
                }
            });
        })
        .catch(error => {
            console.error('Error loading global disruptions:', error);
            // Fallback: show some demo disruption data
            showDemoGlobalDisruptions();
        });
}

function showDemoGlobalDisruptions() {
    // Demo global disruptions if API fails
    const demoDisruptions = [
        {
            coordinates: [26.2, 50.6], // Red Sea
            type: 'geopolitical',
            title: 'Red Sea Conflict Zone',
            severity: 'high',
            description: 'Ongoing security threats affecting shipping lanes'
        },
        {
            coordinates: [1.3, 103.8], // Singapore
            type: 'port_congestion',
            title: 'Port Congestion',
            severity: 'medium',
            description: 'Increased wait times due to high traffic'
        },
        {
            coordinates: [25.3, -80.3], // Miami
            type: 'weather',
            title: 'Hurricane Watch',
            severity: 'high',
            description: 'Tropical storm activity affecting operations'
        }
    ];
    
    demoDisruptions.forEach(disruption => {
        let icon, color;
        
        switch(disruption.type) {
            case 'weather':
                icon = '🌪️';
                color = '#ffc107';
                break;
            case 'geopolitical':
                icon = '⚠️';
                color = '#dc3545';
                break;
            case 'port_congestion':
                icon = '🚢';
                color = '#fd7e14';
                break;
        }
        
        const marker = L.marker(disruption.coordinates, {
            icon: L.divIcon({
                className: 'disruption-marker',
                html: `<div style="background-color: ${color}; color: white; padding: 4px 8px; border-radius: 50%; font-size: 12px; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">${icon}</div>`,
                iconSize: [30, 30],
                iconAnchor: [15, 15]
            })
        }).addTo(dashboardMap);
        
        const popupContent = `
            <div class="disruption-popup">
                <h6 class="mb-2"><span class="badge bg-${getRiskColorFromType(disruption.type)}">${disruption.severity}</span> ${disruption.title}</h6>
                <p class="mb-1"><strong>Type:</strong> ${disruption.type.replace('_', ' ').toUpperCase()}</p>
                <p class="mb-1"><strong>Impact:</strong> ${disruption.description}</p>
            </div>
        `;
        
        marker.bindPopup(popupContent);
        riskMarkers.push(marker);
    });
}

function getRiskColorFromType(type) {
    switch(type) {
        case 'weather': return 'warning';
        case 'geopolitical': return 'danger';
        case 'port_congestion': return 'warning';
        case 'supply_shortage': return 'info';
        default: return 'secondary';
    }
}

function showRoutesView() {
    if (!dashboardMap) return;
    
    // Clear existing markers
    riskMarkers.forEach(marker => dashboardMap.removeLayer(marker));
    riskMarkers = [];
    
    // Load and display active routes
    fetch('/api/active-routes')
        .then(response => response.json())
        .then(data => {
            const routes = data.routes || [];
            
            if (routes.length === 0) {
                console.log('No active routes found');
                return;
            }
            
            const bounds = L.latLngBounds();
            
            routes.forEach(route => {
                // Create origin marker
                const originMarker = L.marker(route.origin.coordinates, {
                    title: route.origin.name,
                    icon: L.divIcon({
                        className: 'map-icon origin-icon',
                        html: '<i class="bi bi-circle-fill text-primary"></i>',
                        iconSize: [20, 20]
                    })
                }).addTo(dashboardMap);
                
                // Create destination marker
                const destMarker = L.marker(route.destination.coordinates, {
                    title: route.destination.name,
                    icon: L.divIcon({
                        className: 'map-icon destination-icon',
                        html: '<i class="bi bi-geo-alt-fill text-danger"></i>',
                        iconSize: [20, 20]
                    })
                }).addTo(dashboardMap);
                
                // Create route line with color based on risk level
                const routeColor = route.risk_level === 'high' ? '#dc3545' : 
                                  (route.risk_level === 'medium' ? '#ffc107' : '#198754');
                const routeLine = L.polyline([route.origin.coordinates, route.destination.coordinates], {
                    color: routeColor,
                    weight: 3,
                    opacity: 0.8,
                    dashArray: '10, 10'
                }).addTo(dashboardMap);
                
                // Add popups
                const popupContent = `
                    <strong>${route.reference}</strong><br>
                    Carrier: ${route.carrier || 'Unknown'}<br>
                    From: ${route.origin.name}<br>
                    To: ${route.destination.name}<br>
                    ETA: ${formatDate(route.eta)}<br>
                    Risk: <span class="badge bg-${getRiskColor(route.risk_level)}">${route.risk_level}</span>
                `;
                
                routeLine.bindPopup(popupContent);
                originMarker.bindPopup(`<strong>${route.origin.name}</strong><br>Origin port`);
                destMarker.bindPopup(`<strong>${route.destination.name}</strong><br>Destination port`);
                
                // Add markers to collection for later cleanup
                riskMarkers.push(originMarker, destMarker, routeLine);
                
                // Extend bounds to include this route
                bounds.extend(route.origin.coordinates);
                bounds.extend(route.destination.coordinates);
            });
            
            // Fit map to show all routes
            dashboardMap.fitBounds(bounds, {
                padding: [50, 50]
            });
        })
        .catch(error => console.error('Error loading routes:', error));
}

// Action handlers
async function initiateReroute(shipmentId) {
    window.location.href = `/shipments/${shipmentId}?action=reroute`;
}

async function explainRecommendation(recommendationId) {
    try {
        const response = await fetch(`/api/recommendations/${recommendationId}/explain`);
        const explanation = await response.json();
        
        // Show explanation in modal
        showExplanationModal(explanation);
    } catch (error) {
        if (window.showToast) {
            window.showToast('Error', 'Failed to load explanation', 'danger');
        }
    }
}

async function approveRecommendation(recommendationId) {
    try {
        const response = await fetch(`/api/recommendations/${recommendationId}/approve`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (response.ok) {
            if (window.showToast) {
                window.showToast('Success', 'Recommendation approved', 'success');
            }
            loadDashboardData(); // Refresh
        } else {
            const error = await response.json();
            if (window.showToast) {
                window.showToast('Error', error.message || 'Failed to approve', 'danger');
            }
        }
    } catch (error) {
        if (window.showToast) {
            window.showToast('Error', 'Failed to approve recommendation', 'danger');
        }
    }
}

function editRecommendation(recommendationId) {
    console.log('Edit recommendation:', recommendationId);
    // TODO: Open edit modal
}

function showExplanationModal(explanation) {
    const modalHtml = `
        <div class="modal fade" id="explanationModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Recommendation Explanation</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <h6>Rationale</h6>
                        <p>${explanation.rationale}</p>
                        
                        <h6>Key Factors</h6>
                        <ul>
                            ${explanation.factors.map(f => `<li>${f}</li>`).join('')}
                        </ul>
                        
                        <h6>Data Sources</h6>
                        <ul>
                            ${explanation.sources.map(s => `<li>${s}</li>`).join('')}
                        </ul>
                        
                        <h6>Model Configuration</h6>
                        <pre class="bg-light p-2">${JSON.stringify(explanation.model_config, null, 2)}</pre>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove any existing modal
    const existingModal = document.getElementById('explanationModal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Add new modal
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('explanationModal'));
    modal.show();
}

// New XAI modal using template structure (if present)
function showXaiModal(rec) {
    const tmpl = document.getElementById('xaiFactorsTemplate');
    const existing = document.getElementById('xaiFactorsModal');
    if (existing) existing.remove();
    if (!tmpl) { console.warn('No XAI factors template found'); showExplanationModal(rec.xai || { rationale: rec.rationale || 'No rationale'}); return; }
    document.body.insertAdjacentHTML('beforeend', tmpl.innerHTML.trim());
    const modalEl = document.getElementById('xaiFactorsModal');
    const xai = rec.xai || {};
    // Populate
    const rationaleField = modalEl.querySelector('[data-xai-field="rationale"]');
    if (rationaleField) rationaleField.textContent = xai.rationale || rec.rationale || '—';
    const listFill = (attr, key) => {
        const ul = modalEl.querySelector(`[data-xai-list="${key}"]`);
        if (!ul) return;
        ul.innerHTML = '';
        (Array.isArray(attr) ? attr : []).forEach(item => {
            ul.insertAdjacentHTML('beforeend', `<li>${item}</li>`);
        });
    };
    listFill(xai.factors || xai.factor_list, 'factors');
    listFill(xai.data_sources || xai.dataSources || xai.sources, 'data_sources');
    // Improvements JSON
    const improvementsDiv = modalEl.querySelector('[data-xai-json="improvements"]');
    if (improvementsDiv && xai.improvements && typeof xai.improvements === 'object') {
        const rows = Object.entries(xai.improvements).filter(([,v]) => v).map(([k,v]) => `<div><strong>${k.replace(/_/g,' ')}:</strong> ${v}</div>`).join('');
        improvementsDiv.innerHTML = rows || '<span class="text-muted">None</span>';
    }
    const bsModal = new bootstrap.Modal(modalEl);
    bsModal.show();
}

// Utility functions
function getRiskColor(level) {
    const colors = {
        'high': 'danger',
        'medium': 'warning',
        'low': 'success',
        'critical': 'danger'
    };
    return colors[level.toLowerCase()] || 'secondary';
}

function getSeverityColor(severity) {
    return getRiskColor(severity);
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// Refresh dashboard
function refreshDashboard() {
    loadDashboardData();
}

// Handle real-time updates
window.updateDashboardAlerts = loadDashboardData;
window.updateRecommendations = function(data) {
    console.log('DASHBOARD.JS: External updateRecommendations invoked');
    if (data && (Array.isArray(data) || (data.recommendations && Array.isArray(data.recommendations)))) {
        const list = Array.isArray(data) ? data : data.recommendations;
        Recommendations.render(list);
    } else {
        Recommendations.fetchAndRender();
    }
};

// Function to manually fetch and update recommendations only
window.refreshRecommendations = async function() {
    console.log("DASHBOARD.JS: Manual recommendations refresh requested");
    
    // Prevent refreshing if we're already loading or updating
    if (isLoadingDashboardData || isUpdatingRecommendations) {
        console.log("DASHBOARD.JS: Already loading or updating, skipping manual refresh");
        return false;
    }
    
    try {
    const response = await fetch('/api/recommendations?page=1&per_page=10');
        const data = await response.json();
        
        // Only update if we have valid data and we're not already updating
        if (!isUpdatingRecommendations) {
            if (data && data.recommendations) {
                updateRecommendations(data.recommendations);
            } else if (Array.isArray(data)) {
                updateRecommendations(data);
            }
        }
        return true;
    } catch (error) {
        console.error("Error refreshing recommendations:", error);
        return false;
    }
};

// Ensure functions are properly exported
window.refreshDashboard = refreshDashboard;
window.dashboardMap = dashboardMap;
window.initializeDashboard = initializeDashboard;
window.initiateReroute = initiateReroute;
window.explainRecommendation = explainRecommendation;
window.approveRecommendation = approveRecommendation;
window.editRecommendation = editRecommendation;
window.refreshRecommendations = () => Recommendations.fetchAndRender(true);

// Attach filter listeners (debounced search)
document.addEventListener('DOMContentLoaded', () => {
    const searchEl = document.getElementById('recSearch');
    const sevEl = document.getElementById('recSeverity');
    let searchTimer = null;
    if (searchEl) {
        searchEl.addEventListener('input', () => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => Recommendations.fetchAndRender(true, 1), 300);
        });
    }
    if (sevEl) {
        sevEl.addEventListener('change', () => Recommendations.fetchAndRender(true, 1));
    }
    const manualBtn = document.getElementById('manualTriggerRecsBtn');
    if (manualBtn) {
        manualBtn.addEventListener('click', async () => {
            if (manualBtn.disabled) return;
            manualBtn.disabled = true;
            const originalHtml = manualBtn.innerHTML;
            manualBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span>';
            try {
                const resp = await fetch('/api/recommendations/trigger', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ force: false, limit: 15 })
                });
                const data = await resp.json();
                console.log('Manual trigger response', data);
                if (window.showToast) {
                    if (resp.ok) {
                        window.showToast('Recommendations', `Processed ${data.processed?.length || 0}, created ${data.created}`, 'success');
                    } else {
                        window.showToast('Error', data.error || 'Generation failed', 'danger');
                    }
                }
                // Refresh list (force)
                Recommendations.fetchAndRender(true, 1);
            } catch (e) {
                console.error('Manual trigger failed', e);
                if (window.showToast) window.showToast('Error', 'Trigger failed', 'danger');
            } finally {
                manualBtn.disabled = false;
                manualBtn.innerHTML = originalHtml;
            }
        });
    }
});

// Add a console log when the script loads to verify it's being executed
console.log("DASHBOARD.JS: Script fully loaded and functions exported - v2");
