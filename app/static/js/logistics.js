// Logistics page functionality

let shipmentMap = null;
let shipmentMarkers = {};
let currentPage = 1;
let filters = {
    status: '',
    risk: '',
    carrier: '',
    dateRange: ''
};

// Initialize logistics page (map always visible now)
document.addEventListener('DOMContentLoaded', function() {
    console.log('LOGISTICS.JS: Initializing logistics page');
    // Defensive: only add listeners if elements exist
    const statusFilter = document.getElementById('statusFilter');
    const riskFilter = document.getElementById('riskFilter');
    const carrierFilter = document.getElementById('carrierFilter');
    const exportBtn = document.getElementById('exportBtn');
    if (statusFilter) statusFilter.addEventListener('change', applyFilters);
    if (riskFilter) riskFilter.addEventListener('change', applyFilters);
    if (carrierFilter) carrierFilter.addEventListener('change', applyFilters);
    if (exportBtn) exportBtn.addEventListener('click', exportShipments);
    
    initializeShipmentMap();
    loadShipments();
    
    // Auto-refresh every 60s
    if (!window.logisticsRefreshInterval) {
        window.logisticsRefreshInterval = setInterval(() => loadShipments(currentPage), 60000);
    }
});

// Load shipments data
async function loadShipments(page = 1) {
    try {
        const params = new URLSearchParams({ page: page });
        if (filters.status) params.append('status', filters.status);
        if (filters.risk) params.append('risk_level', filters.risk);
        if (filters.carrier) params.append('carrier', filters.carrier);
        
        const response = await fetch(`/api/shipments?${params.toString()}`);
        const data = await response.json();
        const shipments = data.shipments || [];
        
        updateShipmentsTable(shipments);
        // API returns pages & page (fallback to inferred)
        updatePagination(data.pages || data.total_pages || 1, data.page || data.current_page || 1);
        updateShipmentMap(shipments);
    } catch (error) {
        console.error('Error loading shipments:', error);
        showToast('Error', 'Failed to load shipments', 'danger');
    }
}

// Update shipments table
function updateShipmentsTable(shipments) {
    const tbody = document.querySelector('#shipmentsTable tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (!Array.isArray(shipments) || shipments.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center py-4 text-muted">No shipments found</td></tr>';
        return;
    }
    shipments.forEach((s, idx) => {
        const ref = s.reference || s.reference_number || `SHIP-${s.id}`;
        const origin = s.origin || s.origin_port || '—';
        const dest = s.destination || s.destination_port || '—';
        const eta = s.eta || s.scheduled_arrival;
        const riskLevel = deriveRiskLevel(s);
        const status = (s.status || 'unknown').toLowerCase();
        const formattedStatus = status.replace(/_/g,' ');
        const row = document.createElement('tr');
        row.dataset.shipmentId = s.id;
        row.innerHTML = `
            <td>${(currentPage - 1) * 20 + idx + 1}</td>
            <td><a href="/shipments/${s.id}" class="text-decoration-none">${ref}</a></td>
            <td>${s.carrier || '—'}</td>
            <td>${origin} → ${dest} <a href="#" onclick="focusShipmentOnMap(${s.id});return false;" class="ms-1" title="Show on map"><i class="bi bi-map"></i></a></td>
            <td class="eta-cell">${formatDate(eta)}</td>
            <td><span class="badge risk-badge bg-${getRiskColor(riskLevel)}">${riskLevel}</span></td>
            <td class="status-cell"><span class="badge status-badge bg-${getStatusColor(status)}">${formattedStatus}</span></td>
            <td>
                <div class="btn-group btn-group-sm" role="group">
                    <a href="/shipments/${s.id}" class="btn btn-outline-primary">View</a>
                    ${riskLevel === 'high' ? `<button class="btn btn-outline-warning" onclick="initiateReroute(${s.id})">Re-route</button>` : ''}
                </div>
            </td>`;
        tbody.appendChild(row);
    });
}

// (Removed toggle view logic) Map always visible.

// Initialize shipment map
function initializeShipmentMap() {
    console.log("Initializing shipment map");
    
    try {
        // Check if map container exists
        const mapContainer = document.getElementById('shipmentMap');
        if (!mapContainer) {
            console.error("Map container #shipmentMap not found in DOM");
            return;
        }
        
        // Check if Leaflet is loaded
        if (typeof L === 'undefined') {
            console.error("Leaflet library not loaded");
            return;
        }
        
        // Check if map is already initialized
        if (shipmentMap) {
            console.log("Map already initialized, destroying existing instance");
            shipmentMap.remove();
        }
        
        // Create new map instance
        shipmentMap = L.map('shipmentMap', {
            center: [20, 0],
            zoom: 2,
            minZoom: 1,
            maxZoom: 18,
            worldCopyJump: true
        });
        
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(shipmentMap);
        
        // Add controls
        L.control.scale().addTo(shipmentMap);
        
    // Add legend for route types
    const legend = L.control({position: 'bottomright'});
    legend.onAdd = function(map) {
        const div = L.DomUtil.create('div', 'info legend');
        div.style.padding = '10px 14px';
        div.style.background = 'white';
        div.style.borderRadius = '8px';
        div.style.boxShadow = '0 0 15px rgba(0,0,0,0.2)';
        
        div.innerHTML = '<h6 class="mb-2">Legend</h6>' +
            '<div style="margin-bottom:5px;"><i class="bi bi-geo-alt-fill text-danger" style="margin-right:5px;"></i> Current Location</div>' +
            '<div style="margin-bottom:5px;"><i class="bi bi-geo-fill text-primary" style="margin-right:5px;"></i> Origin Port</div>' +
            '<div style="margin-bottom:5px;"><i class="bi bi-flag-fill text-success" style="margin-right:5px;"></i> Destination Port</div>' +
            '<div class="mt-2"><strong>Routes by Risk:</strong></div>' +
            '<div style="margin-bottom:3px;"><span style="display: inline-block; width: 30px; height: 3px; background-color: #dc3545;"></span> High Risk</div>' +
            '<div style="margin-bottom:3px;"><span style="display: inline-block; width: 30px; height: 3px; background-color: #ffc107;"></span> Medium Risk</div>' +
            '<div style="margin-bottom:3px;"><span style="display: inline-block; width: 30px; height: 3px; background-color: #198754;"></span> Low Risk</div>' +
            '<div style="margin-top:8px;"><span style="display: inline-block; width: 30px; height: 2px; background-color: #6c757d; border-top: 2px dashed;"></span> Planned Route</div>';
        
        return div;
    };
    legend.addTo(shipmentMap);        // Force a resize to ensure map renders correctly
        setTimeout(() => {
            shipmentMap.invalidateSize();
            console.log("Map initialization complete");
        }, 100);
    } catch (e) {
        console.error("Error initializing map:", e);
    }
}

// Update shipment map
function updateShipmentMap(shipments) {
    if (!shipmentMap) return;
    // Clear markers & polylines
    Object.values(shipmentMarkers).forEach(m => shipmentMap.removeLayer(m));
    shipmentMarkers = {};
    shipmentMap.eachLayer(layer => {
        if (layer instanceof L.Polyline && !layer._leaflet_id.toString().includes('tile')) {
            shipmentMap.removeLayer(layer);
        }
    });
    const features = [];
    shipments.forEach(s => {
        const riskLevel = deriveRiskLevel(s);
        // Fill missing coords via known port mapping
        ensureCoordinates(s);
        const current = extractCurrentLatLon(s);
        if (!current) return; // need at least current or origin
        const icon = L.divIcon({
            html: `<i class="bi bi-geo-alt-fill text-${getRiskColor(riskLevel)}" style="font-size:20px;text-shadow:0 0 3px #fff"></i>`,
            iconSize:[24,24], className:'shipment-marker', iconAnchor:[12,24]
        });
        const ref = s.reference || s.reference_number || `SHIP-${s.id}`;
        const marker = L.marker(current, {icon})
            .bindPopup(`<strong>${ref}</strong><br>${s.carrier || ''}<br>Status: ${(s.status||'').replace(/_/g,' ')}<br>Risk: ${riskLevel}`);
        marker.addTo(shipmentMap);
        shipmentMarkers[s.id] = marker;
        features.push(marker);
        // Draw origin/dest line if coords present
        if (s.origin_lat && s.origin_lon && s.destination_lat && s.destination_lon) {
            const o = [parseFloat(s.origin_lat), parseFloat(s.origin_lon)];
            const d = [parseFloat(s.destination_lat), parseFloat(s.destination_lon)];
            if (isFinite(o[0]) && isFinite(o[1]) && isFinite(d[0]) && isFinite(d[1])) {
                L.polyline([o,d], {color:riskColorHex(riskLevel), weight:3, opacity:0.75, dashArray: (s.status==='planned'?'5,6':null)}).addTo(shipmentMap);
                features.push(L.marker(o,{icon: L.divIcon({html:'<i class="bi bi-geo-fill text-primary" style="font-size:14px"></i>',className:'',iconSize:[16,16],iconAnchor:[8,8]})}).bindTooltip(`Origin: ${s.origin||s.origin_port||''}`).addTo(shipmentMap));
                features.push(L.marker(d,{icon: L.divIcon({html:'<i class="bi bi-flag-fill text-success" style="font-size:14px"></i>',className:'',iconSize:[16,16],iconAnchor:[8,8]})}).bindTooltip(`Destination: ${s.destination||s.destination_port||''}`).addTo(shipmentMap));
            }
        } else {
            if (s.origin_lat && s.origin_lon && !(s.destination_lat && s.destination_lon)) {
                console.debug('Missing destination coords for shipment', s.id, s.destination || s.destination_port);
            }
        }
        // Custom route polyline
        if (Array.isArray(s.route_points) && s.route_points.length>1) {
            L.polyline(s.route_points, {color:riskColorHex(riskLevel), weight:3, opacity:0.6}).addTo(shipmentMap);
        }
    });
    if (features.length>0) {
        const group = L.featureGroup(features);
        shipmentMap.fitBounds(group.getBounds().pad(0.15));
    } else {
        shipmentMap.setView([20,0],2);
    }
}

// Apply filters
function applyFilters() {
    filters.status = document.getElementById('statusFilter').value;
    filters.risk = document.getElementById('riskFilter').value;
    filters.carrier = document.getElementById('carrierFilter').value;
    
    currentPage = 1;
    loadShipments();
}

// Update pagination
function updatePagination(totalPages, currentPage) {
    const pagination = document.getElementById('pagination');
    pagination.innerHTML = '';
    
    if (totalPages <= 1) return;
    
    // Previous button
    const prevLi = document.createElement('li');
    prevLi.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
    prevLi.innerHTML = `<a class="page-link" href="#" onclick="goToPage(${currentPage - 1})">Previous</a>`;
    pagination.appendChild(prevLi);
    
    // Page numbers
    for (let i = 1; i <= Math.min(totalPages, 10); i++) {
        const li = document.createElement('li');
        li.className = `page-item ${i === currentPage ? 'active' : ''}`;
        li.innerHTML = `<a class="page-link" href="#" onclick="goToPage(${i})">${i}</a>`;
        pagination.appendChild(li);
    }
    
    // Next button
    const nextLi = document.createElement('li');
    nextLi.className = `page-item ${currentPage === totalPages ? 'disabled' : ''}`;
    nextLi.innerHTML = `<a class="page-link" href="#" onclick="goToPage(${currentPage + 1})">Next</a>`;
    pagination.appendChild(nextLi);
}

// Go to page
function goToPage(page) {
    currentPage = page;
    loadShipments(page);
}

// Create new shipment
async function createShipment() {
    const form = document.getElementById('newShipmentForm');
    const formData = new FormData(form);
    
    // Create a properly formatted request payload
    const formValues = Object.fromEntries(formData);
    
    // Port to coordinates mapping (for demo purposes)
    const portCoordinates = {
        // Asia
        'Shanghai': [31.22, 121.46],
        'Singapore': [1.29, 103.85],
        'Hong Kong': [22.32, 114.17],
        'Busan': [35.18, 129.08],
        'Tokyo': [35.65, 139.77],
        'Dubai': [25.27, 55.33],
        'Mumbai': [18.94, 72.83],
        'Karachi': [24.85, 67.01],
        
        // Europe
        'Rotterdam': [51.91, 4.48],
        'Hamburg': [53.55, 10.00],
        'Antwerp': [51.25, 4.40],
        'Felixstowe': [51.96, 1.31],
        'Piraeus': [37.95, 23.63],
        'Marseille': [43.30, 5.37],
        'Gdansk': [54.41, 18.66],
        
        // Americas
        'Los Angeles': [33.73, -118.26],
        'New York': [40.71, -74.01],
        'Savannah': [32.08, -81.10],
        'Vancouver': [49.29, -123.12],
        'Santos': [-23.93, -46.33],
        'Buenos Aires': [-34.61, -58.37],
        'Panama City': [8.98, -79.52],
        
        // Africa/Middle East
        'Durban': [-29.86, 31.03],
        'Cape Town': [-33.91, 18.42],
        'Tangier': [35.79, -5.81],
        'Alexandria': [31.20, 29.92]
    };
    
    // Get coordinates for origin and destination ports
    let origin_coords = portCoordinates[formValues.origin] || [0, 0];
    let dest_coords = portCoordinates[formValues.destination] || [0, 0];
    
    // Build shipmentData with all fields as top-level keys, correct names/types
    const shipmentData = {
        reference_number: formValues.reference,
        origin_port: formValues.origin,
        destination_port: formValues.destination,
        carrier: formValues.carrier,
        scheduled_departure: formValues.etd,
        scheduled_arrival: formValues.eta,
        status: formValues.status,
        risk_score: formValues.risk_score ? parseFloat(formValues.risk_score) : undefined,
        transport_mode: formValues.transport_mode || 'SEA',
        container_number: formValues.container_number || undefined,
        container_count: formValues.container_count ? parseInt(formValues.container_count, 10) : undefined,
        weight_tons: formValues.weight ? parseFloat(formValues.weight) : undefined,
        cargo_value_usd: formValues.value ? parseFloat(formValues.value) : undefined,
        description: formValues.cargo_description || '',
        origin_lat: origin_coords[0],
        origin_lon: origin_coords[1],
        destination_lat: dest_coords[0],
        destination_lon: dest_coords[1]
    };
    // Remove undefined fields
    Object.keys(shipmentData).forEach(k => shipmentData[k] === undefined && delete shipmentData[k]);
    
    try {
        console.log("Sending data to API:", shipmentData);
        const response = await fetch('/api/shipments', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(shipmentData)
        });
        
        if (response.ok) {
            const shipment = await response.json();
            showToast('Success', `Shipment ${shipment.reference} created`, 'success');
            
            // Close modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('newShipmentModal'));
            modal.hide();
            
            // Reset form
            form.reset();
            
            // Reload shipments
            loadShipments();
        } else {
            const error = await response.json();
            showToast('Error', error.error || 'Failed to create shipment', 'danger');
        }
    } catch (error) {
        console.error('Error creating shipment:', error);
        showToast('Error', 'Failed to create shipment', 'danger');
    }
}

// Export shipments
async function exportShipments() {
    try {
        const params = new URLSearchParams(filters);
        const response = await fetch(`/api/shipments/export?${params}`);
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `shipments_${new Date().toISOString().split('T')[0]}.csv`;
            document.body.appendChild(a);
            a.click();
            a.remove();
        }
    } catch (error) {
        showToast('Error', 'Failed to export shipments', 'danger');
    }
}

// Handle real-time updates
socketIO.on('shipment_updated', (data) => {
    // Update table row if visible
    const row = document.querySelector(`tr[data-shipment-id="${data.shipment_id}"]`);
    if (row) {
        row.classList.add('update-flash');
        setTimeout(() => row.classList.remove('update-flash'), 1000);
        
        // Reload shipments to get updated data
        loadShipments(currentPage);
    }
});

// Show a specific shipment on the map
function focusShipmentOnMap(shipmentId){
    fetch(`/api/shipments?id=${shipmentId}`)
        .then(r=>r.json())
        .then(data=>{
            const s = (data.shipments||[]).find(x=>x.id===shipmentId) || data;
            if (!s || !shipmentMap) return;
            ensureCoordinates(s);
            updateShipmentMap([s]);
            if (shipmentMarkers[shipmentId]) {
                shipmentMap.setView(shipmentMarkers[shipmentId].getLatLng(),8);
                shipmentMarkers[shipmentId].openPopup();
            }
        });
}

// Export functions
window.goToPage = goToPage;
window.createShipment = createShipment;
window.initiateReroute = function(shipmentId) {
    window.location.href = `/shipments/${shipmentId}?action=reroute`;
};
window.focusShipmentOnMap = focusShipmentOnMap;
// Backward compat
window.showMapForShipment = focusShipmentOnMap;
window.shipmentMap = shipmentMap;
window.shipmentMarkers = shipmentMarkers;

// Helper functions
function getRiskColor(risk_level) {
    // Returns bootstrap context key for markers; for lines we map separately
    if (risk_level === 'high') return 'danger';
    if (risk_level === 'medium') return 'warning';
    return 'success';
}

function riskColorHex(risk_level){
    const r = (risk_level||'').toLowerCase();
    if (r === 'high') return '#dc3545';
    if (r === 'medium') return '#ffc107';
    if (r === 'low') return '#198754';
    return '#0d6efd';
}

function deriveRiskLevel(s){
    if (s.risk_level) return s.risk_level.toLowerCase();
    const score = s.risk_score;
    if (typeof score === 'number') {
        if (score >= 0.7) return 'high';
        if (score >= 0.4) return 'medium';
        return 'low';
    }
    return 'low';
}

const PORT_COORDS = {
    'Shanghai':[31.22,121.46],'Singapore':[1.29,103.85],'Hong Kong':[22.32,114.17],'Busan':[35.18,129.08],'Tokyo':[35.65,139.77],
    'Rotterdam':[51.91,4.48],'Hamburg':[53.55,10.0],'Antwerp':[51.25,4.40],'Los Angeles':[33.73,-118.26],'New York':[40.71,-74.01],
    'Savannah':[32.08,-81.10],'Vancouver':[49.29,-123.12],'Santos':[-23.93,-46.33],'Buenos Aires':[-34.61,-58.37],'Durban':[-29.86,31.03],
    'Cape Town':[-33.91,18.42],'Tangier':[35.79,-5.81],'Alexandria':[31.20,29.92]
};

function ensureCoordinates(s){
    if ((!s.origin_lat || !s.origin_lon) && (s.origin||s.origin_port) && PORT_COORDS[s.origin||s.origin_port]){
        [s.origin_lat,s.origin_lon]=PORT_COORDS[s.origin||s.origin_port];
    }
    if ((!s.destination_lat || !s.destination_lon) && (s.destination||s.destination_port) && PORT_COORDS[s.destination||s.destination_port]){
        [s.destination_lat,s.destination_lon]=PORT_COORDS[s.destination||s.destination_port];
    }
}

function extractCurrentLatLon(s){
    if (s.current_location){
        try { let loc = typeof s.current_location==='string'? JSON.parse(s.current_location): s.current_location; if(loc.lat&&loc.lon) return [parseFloat(loc.lat), parseFloat(loc.lon)]; } catch(e){}
    }
    if (s.origin_lat && s.origin_lon) return [parseFloat(s.origin_lat), parseFloat(s.origin_lon)];
    return null;
}

function getStatusColor(status) {
    if (status === 'delayed') return 'danger';
    if (status === 'in_transit') return 'primary';
    if (status === 'delivered') return 'success';
    if (status === 'planned') return 'info';
    if (status === 'cancelled') return 'secondary';
    return 'secondary';
}

function formatDate(dateStr) {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    return date.toLocaleDateString();
}

function showToast(title, message, type = 'info') {
    // Add toast notification logic here
    console.log(`${title}: ${message}`);
}

function updateShipmentRow(row, shipment) {
    row.querySelector('.eta-cell').textContent = new Date(shipment.eta).toLocaleString();
    
    const riskBadge = row.querySelector('.risk-badge');
    riskBadge.className = `badge risk-badge bg-${getRiskColor(shipment.risk_level)}`;
    riskBadge.textContent = shipment.risk_level;
    
    const statusBadge = row.querySelector('.status-badge');
    statusBadge.className = `badge status-badge bg-${getStatusColor(shipment.status)}`;
    statusBadge.textContent = shipment.status.replace('_', ' ').toUpperCase();
}
