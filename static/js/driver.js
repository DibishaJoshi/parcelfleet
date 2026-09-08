/**
 * ParcelFleet - Driver Panel Controller
 * Handles digital signature verification, photo uploads, high-accuracy live GPS telemetry broadcasting,
 * interactive Leaflet road routing, TSP stop pins, HUD overlay updates, and transit simulation.
 */

// Global helper for modal workflow stage changes
window.toggleWorkflowSections = function (selectEl) {
    const pId = selectEl.getAttribute('data-parcel-id');
    const status = selectEl.value;
    
    const pickupSec = document.getElementById('pickup_section' + pId);
    const deliveredSec = document.getElementById('delivered_section' + pId);
    const failedSec = document.getElementById('failed_section' + pId);

    if (pickupSec) pickupSec.classList.add('d-none');
    if (deliveredSec) deliveredSec.classList.add('d-none');
    if (failedSec) failedSec.classList.add('d-none');

    const pickupFile = document.getElementById('pickup_file' + pId);
    const deliveryFile = document.getElementById('delivery_file' + pId);
    const failedReason = document.getElementById('failedReason' + pId);

    if (pickupFile) pickupFile.removeAttribute('required');
    if (deliveryFile) deliveryFile.removeAttribute('required');
    if (failedReason) failedReason.removeAttribute('required');

    if (status === 'Picked Up') {
        if (pickupSec) pickupSec.classList.remove('d-none');
        if (pickupFile) pickupFile.setAttribute('required', 'required');
    } else if (status === 'Delivered') {
        if (deliveredSec) deliveredSec.classList.remove('d-none');
        if (deliveryFile) deliveryFile.setAttribute('required', 'required');
        
        setTimeout(() => {
            const canvas = document.getElementById('signatureCanvas');
            if (canvas) {
                const rect = canvas.getBoundingClientRect();
                canvas.width = rect.width;
                canvas.height = rect.height;
                const ctx = canvas.getContext('2d');
                ctx.strokeStyle = '#0F172A';
                ctx.lineWidth = 3;
                ctx.lineCap = 'round';
                ctx.lineJoin = 'round';
            }
        }, 150);
    } else if (status === 'Failed Attempt') {
        if (failedSec) failedSec.classList.remove('d-none');
        if (failedReason) failedReason.setAttribute('required', 'required');
    }
};

document.addEventListener('DOMContentLoaded', function () {
    // -------------------------------------------------------------
    // 1. DIGITAL CANVAS SIGNATURE PAD HANDLER
    // -------------------------------------------------------------
    const canvas = document.getElementById('signatureCanvas');
    const signatureInput = document.getElementById('customer_signature_data');
    const clearBtn = document.getElementById('clearSignature');
    
    if (canvas && signatureInput) {
        const ctx = canvas.getContext('2d');
        let isDrawing = false;
        let lastX = 0;
        let lastY = 0;

        const resizeCanvas = () => {
            const rect = canvas.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                canvas.width = rect.width;
                canvas.height = rect.height;
                ctx.strokeStyle = '#0F172A';
                ctx.lineWidth = 3;
                ctx.lineCap = 'round';
                ctx.lineJoin = 'round';
            }
        };

        window.addEventListener('resize', resizeCanvas);
        setTimeout(resizeCanvas, 250);

        const getCoordinates = (e) => {
            const rect = canvas.getBoundingClientRect();
            if (e.touches && e.touches.length > 0) {
                return {
                    x: e.touches[0].clientX - rect.left,
                    y: e.touches[0].clientY - rect.top
                };
            }
            return {
                x: e.clientX - rect.left,
                y: e.clientY - rect.top
            };
        };

        const startDrawing = (e) => {
            isDrawing = true;
            const coords = getCoordinates(e);
            lastX = coords.x;
            lastY = coords.y;
        };

        const draw = (e) => {
            if (!isDrawing) return;
            e.preventDefault();
            const coords = getCoordinates(e);
            ctx.beginPath();
            ctx.moveTo(lastX, lastY);
            ctx.lineTo(coords.x, coords.y);
            ctx.stroke();
            lastX = coords.x;
            lastY = coords.y;
            signatureInput.value = canvas.toDataURL();
        };

        const stopDrawing = () => {
            isDrawing = false;
        };

        canvas.addEventListener('mousedown', startDrawing);
        canvas.addEventListener('mousemove', draw);
        canvas.addEventListener('mouseup', stopDrawing);
        canvas.addEventListener('mouseout', stopDrawing);

        canvas.addEventListener('touchstart', startDrawing, { passive: false });
        canvas.addEventListener('touchmove', draw, { passive: false });
        canvas.addEventListener('touchend', stopDrawing);

        if (clearBtn) {
            clearBtn.addEventListener('click', (e) => {
                e.preventDefault();
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                signatureInput.value = '';
            });
        }
    }

    // -------------------------------------------------------------
    // 2. PHOTO UPLOADS PREVIEW TRIGGER
    // -------------------------------------------------------------
    const fileInputs = document.querySelectorAll('.parcel-photo-input');
    fileInputs.forEach(input => {
        input.addEventListener('change', function () {
            const previewId = this.getAttribute('data-preview');
            const previewEl = document.getElementById(previewId);
            if (previewEl && this.files && this.files[0]) {
                const reader = new FileReader();
                reader.onload = function (e) {
                    previewEl.style.backgroundImage = 'url(' + e.target.result + ')';
                    previewEl.classList.add('has-image');
                };
                reader.readAsDataURL(this.files[0]);
            }
        });
    });

    // -------------------------------------------------------------
    // 3. LIVE NAVIGATION MAP & ROUTING CONTROLLER
    // -------------------------------------------------------------
    const mapContainer = document.getElementById('driverLiveMap');
    const shareLocationToggle = document.getElementById('shareLocationToggle');
    const simulateToggle = document.getElementById('simulateMovementToggle');
    const driverStateSelect = document.getElementById('driverStateSelect');
    const gpsStatusBadge = document.getElementById('gpsStatusBadge');
    const btnRecenterGps = document.getElementById('btnRecenterGps');

    const hudTargetText = document.getElementById('hudTargetText');
    const hudDistanceText = document.getElementById('hudDistanceText');
    const hudEtaText = document.getElementById('hudEtaText');

    let driverMap = null;
    let driverMarker = null;
    let routeLayer = null;
    let stopsLayer = null;
    
    let currentDriverLat = mapContainer && mapContainer.getAttribute('data-driver-lat') ? parseFloat(mapContainer.getAttribute('data-driver-lat')) : 27.6850;
    let currentDriverLng = mapContainer && mapContainer.getAttribute('data-driver-lng') ? parseFloat(mapContainer.getAttribute('data-driver-lng')) : 85.2050;
    let driverVehicleType = 'Bike';
    let pathCoordinates = [];
    let pathIndex = 0;
    let watchPositionId = null;
    let simulationTimer = null;
    let routeFetchInterval = null;

    // Toast notification helper
    function showToast(title, message, type = 'info') {
        const toastContainer = document.getElementById('toast-container');
        if (!toastContainer) return;
        const toast = document.createElement('div');
        toast.className = `toast show align-items-center text-white bg-${type === 'info' ? 'primary' : type} border-0 m-2`;
        toast.role = 'alert';
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    <strong>${title}</strong><br>${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;
        toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 400);
        }, 4000);
    }

    // Initialize Leaflet Map
    function initDriverMap() {
        if (!mapContainer || typeof L === 'undefined') return;

        driverMap = L.map('driverLiveMap', {
            zoomControl: true,
            attributionControl: false
        }).setView([currentDriverLat, currentDriverLng], 14);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19
        }).addTo(driverMap);

        routeLayer = L.layerGroup().addTo(driverMap);
        stopsLayer = L.layerGroup().addTo(driverMap);

        // Custom pulsing marker icon
        const driverIcon = L.divIcon({
            className: 'custom-driver-icon',
            html: `
                <div class="driver-live-marker-wrap">
                    <div class="driver-live-pulse"></div>
                    <div class="driver-live-core">
                        <i class="fas fa-motorcycle"></i>
                    </div>
                </div>
            `,
            iconSize: [36, 36],
            iconAnchor: [18, 18],
            popupAnchor: [0, -18]
        });

        driverMarker = L.marker([currentDriverLat, currentDriverLng], {
            icon: driverIcon,
            zIndexOffset: 1000
        }).addTo(driverMap);
        
        driverMarker.bindPopup('<strong>My Live Location</strong><br>GPS Telemetry Broadcasting');

        // Recenter button click
        if (btnRecenterGps) {
            btnRecenterGps.addEventListener('click', () => {
                if (driverMap && currentDriverLat && currentDriverLng) {
                    driverMap.setView([currentDriverLat, currentDriverLng], 15, { animate: true });
                }
            });
        }
    }

    // Update the visual position of the driver marker on the map
    function updateDriverMarker(lat, lng) {
        currentDriverLat = lat;
        currentDriverLng = lng;
        if (driverMarker) {
            driverMarker.setLatLng([lat, lng]);
        }
    }

    // Send location to server
    function sendLocationUpdate(lat, lng, availabilityState) {
        const payload = {
            availability: availabilityState || (driverStateSelect ? driverStateSelect.value : 'Available')
        };
        if (lat !== null && lng !== null && lat !== undefined && lng !== undefined) {
            payload.latitude = lat;
            payload.longitude = lng;
        }

        return fetch('/api/driver/update-location', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(data => {
            console.log('Driver location update committed: ', data);
            return data;
        })
        .catch(err => console.error('GPS broadcast error: ', err));
    }

    // Fetch active road route & TSP stops from server
    function fetchAndRenderActiveRoute() {
        return fetch('/api/driver/active-route')
            .then(res => res.json())
            .then(data => {
                if (!data || !driverMap) return;

                if (data.driver) {
                    driverVehicleType = data.driver.vehicle_type || 'Bike';
                    // Update vehicle icon in marker if needed
                    const iconEl = document.querySelector('.driver-live-core i');
                    if (iconEl) {
                        if (driverVehicleType.toLowerCase().includes('truck')) {
                            iconEl.className = 'fas fa-truck';
                        } else if (driverVehicleType.toLowerCase().includes('van')) {
                            iconEl.className = 'fas fa-van-shuttle';
                        } else {
                            iconEl.className = 'fas fa-motorcycle';
                        }
                    }
                }

                // Clear previous route polylines and stop markers
                if (routeLayer) routeLayer.clearLayers();
                if (stopsLayer) stopsLayer.clearLayers();

                // 1. Render road polyline if coordinates exist
                if (data.coordinates && data.coordinates.length > 0) {
                    pathCoordinates = data.coordinates;
                    const latlngs = data.coordinates.map(pt => [pt.lat, pt.lng]);
                    
                    // Route casing shadow
                    L.polyline(latlngs, {
                        color: '#1E3A8A',
                        weight: 7,
                        opacity: 0.6,
                        lineCap: 'round',
                        lineJoin: 'round'
                    }).addTo(routeLayer);

                    // Route primary line
                    const primaryLine = L.polyline(latlngs, {
                        color: '#3B82F6',
                        weight: 4,
                        opacity: 0.95,
                        lineCap: 'round',
                        lineJoin: 'round'
                    }).addTo(routeLayer);

                    // Fit map bounds to view driver and route
                    const bounds = primaryLine.getBounds();
                    if (bounds.isValid()) {
                        driverMap.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
                    }
                } else {
                    pathCoordinates = [];
                }

                // 2. Render TSP-ordered Stop Pins
                if (data.stops && data.stops.length > 0) {
                    data.stops.forEach((stop, index) => {
                        const stopNum = stop.stop_number || (index + 1);
                        const isDelivery = (stop.action_type || '').includes('Deliver') || stop.status !== 'Assigned';
                        const badgeClass = isDelivery ? 'stop-delivery' : 'stop-pickup';
                        const actionLabel = stop.action_type || (isDelivery ? 'Delivery' : 'Pickup');

                        const stopIcon = L.divIcon({
                            className: 'custom-stop-icon',
                            html: `<div class="stop-numbered-marker ${badgeClass}">${stopNum}</div>`,
                            iconSize: [28, 28],
                            iconAnchor: [14, 14],
                            popupAnchor: [0, -14]
                        });

                        const recipientInfo = stop.receiver_name ? `<strong>Recipient:</strong> ${stop.receiver_name} (${stop.receiver_phone || 'N/A'})<br>` : '';
                        const senderInfo = stop.sender_name ? `<strong>Sender:</strong> ${stop.sender_name} (${stop.sender_phone || 'N/A'})<br>` : '';
                        const chargeInfo = stop.delivery_charge ? `<strong>Charge:</strong> Rs. ${stop.delivery_charge} (${stop.payment_status || 'Unpaid'})<br>` : '';

                        const popupHtml = `
                            <div style="font-size: 0.85rem; min-width: 180px;">
                                <div class="badge bg-primary mb-1">Stop #${stopNum} &bull; ${actionLabel}</div>
                                <h6 class="fw-bold mb-1 text-dark">${stop.tracking_id || stop.name || 'Destination'}</h6>
                                <p class="text-muted small mb-1"><i class="fas fa-location-dot me-1 text-danger"></i>${stop.delivery_address || stop.name || ''}</p>
                                ${recipientInfo}
                                ${senderInfo}
                                ${chargeInfo}
                            </div>
                        `;

                        L.marker([stop.lat, stop.lng], { icon: stopIcon })
                            .bindPopup(popupHtml)
                            .addTo(stopsLayer);
                    });
                }

                // 3. Update HUD Metrics
                if (hudTargetText && hudDistanceText && hudEtaText) {
                    if (data.type === 'manifest') {
                        hudTargetText.innerHTML = `<i class="fas fa-truck-moving me-1"></i>Freight Manifest: ${data.destination.name}`;
                        hudDistanceText.innerText = `${Number(data.distance_km || 0).toFixed(1)} km`;
                        hudEtaText.innerText = `${Math.round(data.duration_min || 0)} mins`;
                    } else if (data.type === 'parcels' && data.current_target) {
                        const target = data.current_target;
                        const action = target.action_type || 'Deliver to';
                        const recipient = target.receiver_name ? ` (${target.receiver_name})` : '';
                        hudTargetText.innerHTML = `<i class="fas fa-box me-1"></i>Stop #1: ${action}${recipient} &bull; ${target.delivery_address || ''}`;
                        hudDistanceText.innerText = `${Number(data.distance_km || 0).toFixed(1)} km`;
                        hudEtaText.innerText = `${Math.round(data.duration_min || 0)} mins`;
                    } else {
                        hudTargetText.innerHTML = `<i class="fas fa-circle-check text-success me-1"></i>All deliveries complete &bull; Available (Idle)`;
                        hudDistanceText.innerText = `0.0 km`;
                        hudEtaText.innerText = `-- mins`;
                    }
                }
            })
            .catch(err => console.error('Error fetching driver active route: ', err));
    }

    // High Accuracy GPS Watcher
    function startGpsTracking() {
        if (!navigator.geolocation) {
            if (gpsStatusBadge) {
                gpsStatusBadge.className = 'badge bg-warning bg-opacity-10 text-warning border border-warning';
                gpsStatusBadge.innerHTML = '<i class="fa-solid fa-triangle-exclamation me-1"></i>GPS Unsupported';
            }
            return;
        }

        if (gpsStatusBadge) {
            gpsStatusBadge.className = 'badge bg-info bg-opacity-10 text-info border border-info';
            gpsStatusBadge.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i>Acquiring GPS...';
        }

        const geoOptions = {
            enableHighAccuracy: true,
            maximumAge: 2000,
            timeout: 10000
        };

        const onGpsSuccess = (position) => {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;
            const accuracy = Math.round(position.coords.accuracy || 0);

            if (gpsStatusBadge) {
                gpsStatusBadge.className = 'badge bg-success bg-opacity-10 text-success border border-success';
                gpsStatusBadge.innerHTML = `<i class="fa-solid fa-satellite-dish me-1"></i>GPS Active (&plusmn;${accuracy}m)`;
            }

            updateDriverMarker(lat, lng);

            // If location sharing is enabled and not simulating, broadcast real GPS coordinates
            if (shareLocationToggle && shareLocationToggle.checked && (!simulateToggle || !simulateToggle.checked)) {
                sendLocationUpdate(lat, lng);
            }
        };

        const onGpsError = (err) => {
            console.warn('Geolocation watchPosition error: ', err.message);
            if (gpsStatusBadge) {
                gpsStatusBadge.className = 'badge bg-danger bg-opacity-10 text-danger border border-danger';
                gpsStatusBadge.innerHTML = '<i class="fa-solid fa-triangle-exclamation me-1"></i>GPS Denied/Weak';
            }
        };

        // Get single quick fix first
        navigator.geolocation.getCurrentPosition(onGpsSuccess, onGpsError, geoOptions);

        // Continuous watching
        if (watchPositionId !== null) {
            navigator.geolocation.clearWatch(watchPositionId);
        }
        watchPositionId = navigator.geolocation.watchPosition(onGpsSuccess, onGpsError, geoOptions);
    }

    // Stop GPS Watcher
    function stopGpsTracking() {
        if (watchPositionId !== null) {
            navigator.geolocation.clearWatch(watchPositionId);
            watchPositionId = null;
        }
        if (gpsStatusBadge) {
            gpsStatusBadge.className = 'badge bg-secondary bg-opacity-10 text-secondary border border-secondary';
            gpsStatusBadge.innerHTML = '<i class="fa-solid fa-satellite-dish me-1"></i>GPS Standby';
        }
    }

    // Simulation Traversal Loop
    function startSimulation() {
        if (simulationTimer) clearInterval(simulationTimer);
        pathIndex = 0;

        simulationTimer = setInterval(() => {
            if (pathCoordinates && pathCoordinates.length > 0) {
                const coord = pathCoordinates[pathIndex];
                updateDriverMarker(coord.lat, coord.lng);
                
                // Broadcast simulated coordinate
                if (shareLocationToggle && shareLocationToggle.checked) {
                    sendLocationUpdate(coord.lat, coord.lng, 'On Delivery');
                }

                if (gpsStatusBadge) {
                    gpsStatusBadge.className = 'badge bg-primary bg-opacity-10 text-primary border border-primary';
                    gpsStatusBadge.innerHTML = `<i class="fa-solid fa-route me-1"></i>Simulating Transit (${pathIndex + 1}/${pathCoordinates.length})`;
                }

                pathIndex = (pathIndex + 1) % pathCoordinates.length;
            }
        }, 2000);
    }

    function stopSimulation() {
        if (simulationTimer) {
            clearInterval(simulationTimer);
            simulationTimer = null;
        }
        if (shareLocationToggle && shareLocationToggle.checked) {
            startGpsTracking();
        }
    }

    // Wire Driver State Dropdown
    if (driverStateSelect) {
        driverStateSelect.addEventListener('change', function () {
            const newState = this.value;
            fetch('/api/driver/update-state', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ state: newState })
            })
            .then(res => res.json())
            .then(data => {
                showToast('State Updated', `Operational state set to: ${newState}`, 'success');
                fetchAndRenderActiveRoute();
            })
            .catch(err => console.error('State update error: ', err));
        });
    }

    // Wire Share Location Toggle
    if (shareLocationToggle) {
        const driverId = shareLocationToggle.getAttribute('data-driver-id');
        const storedShareState = localStorage.getItem('shareLocation_' + driverId);

        const enableSharing = () => {
            shareLocationToggle.checked = true;
            localStorage.setItem('shareLocation_' + driverId, 'true');
            if (simulateToggle && simulateToggle.checked) {
                startSimulation();
            } else {
                startGpsTracking();
            }
            fetchAndRenderActiveRoute();
        };

        const disableSharing = () => {
            shareLocationToggle.checked = false;
            localStorage.setItem('shareLocation_' + driverId, 'false');
            stopGpsTracking();
            stopSimulation();
            sendLocationUpdate(null, null, driverStateSelect ? driverStateSelect.value : 'Offline');
        };

        shareLocationToggle.addEventListener('change', function () {
            if (this.checked) {
                enableSharing();
                showToast('GPS Broadcast Online', 'Broadcasting live coordinates to fleet manager & clients.', 'success');
            } else {
                disableSharing();
                showToast('GPS Broadcast Offline', 'Live GPS broadcast paused.', 'warning');
            }
        });

        // Initialize state on load
        if (storedShareState === 'true') {
            enableSharing();
        } else {
            // Default to starting GPS tracking for local map view
            startGpsTracking();
        }
    }

    // Wire Simulate Movement Toggle
    if (simulateToggle) {
        const driverId = shareLocationToggle ? shareLocationToggle.getAttribute('data-driver-id') : 'default';
        const storedSimState = localStorage.getItem('simulateLocation_' + driverId);

        simulateToggle.addEventListener('change', function () {
            localStorage.setItem('simulateLocation_' + driverId, this.checked ? 'true' : 'false');
            if (this.checked) {
                startSimulation();
                showToast('Transit Simulation Active', 'Moving driver along turn-by-turn road polyline.', 'info');
            } else {
                stopSimulation();
                showToast('Transit Simulation Stopped', 'Switched back to device GPS receiver.', 'secondary');
            }
        });

        if (storedSimState === 'true') {
            simulateToggle.checked = true;
            startSimulation();
        }
    }

    // Initialize Map and Load Initial Route
    initDriverMap();
    fetchAndRenderActiveRoute();

    // Periodic refresh of route geometry every 25 seconds
    routeFetchInterval = setInterval(fetchAndRenderActiveRoute, 25000);
});
