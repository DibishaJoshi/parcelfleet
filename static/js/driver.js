/**
 * ParcelFleet - Driver Route Planner & Navigation Controller
 * Matches Route Planner UI with enlarged map, TSP stop sequence, and live GPS telemetry.
 */

// Universal Call / Contact Helper (works on both mobile dialers and desktop browsers)
window.callContact = function(name, phone) {
    if (!phone || phone === 'None' || phone === 'N/A' || phone.trim() === '') {
        alert('No phone number recorded for ' + (name || 'this contact'));
        return;
    }
    
    // Check if device is mobile
    if (/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)) {
        window.location.href = 'tel:' + phone.replace(/\s+/g, '');
        return;
    }

    // On Desktop or fallback, show interactive modal
    let modalEl = document.getElementById('quickContactModal');
    if (!modalEl) {
        // Create modal dynamically if not already in DOM
        modalEl = document.createElement('div');
        modalEl.id = 'quickContactModal';
        modalEl.className = 'modal fade';
        modalEl.tabIndex = -1;
        modalEl.innerHTML = `
            <div class="modal-dialog modal-dialog-centered modal-sm">
                <div class="modal-content border-0 shadow-lg rounded-4">
                    <div class="modal-header border-bottom border-light p-3">
                        <h6 class="modal-title fw-bold text-dark mb-0"><i class="fa-solid fa-phone text-primary me-2"></i>Contact Client</h6>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body text-center p-4">
                        <div class="rounded-circle bg-primary bg-opacity-10 text-primary d-inline-flex align-items-center justify-content-center mb-3" style="width: 54px; height: 54px; font-size: 1.5rem;">
                            <i class="fa-solid fa-phone-volume"></i>
                        </div>
                        <h5 class="fw-bold text-dark mb-1" id="quickContactName">Client</h5>
                        <div class="fs-5 fw-bold text-primary mb-3" id="quickContactPhone">--</div>
                        <div class="d-grid gap-2">
                            <a href="#" id="quickContactDialBtn" class="btn btn-primary rounded-pill py-2 fw-semibold shadow-sm">
                                <i class="fa-solid fa-phone me-1"></i>Dial Call
                            </a>
                            <button type="button" id="quickContactCopyBtn" class="btn btn-light border rounded-pill py-2" onclick="window.copyContactPhone()">
                                <i class="fa-solid fa-copy me-1"></i>Copy Phone Number
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modalEl);
    }

    document.getElementById('quickContactName').innerText = name || 'Customer';
    document.getElementById('quickContactPhone').innerText = phone;
    document.getElementById('quickContactDialBtn').href = 'tel:' + phone.replace(/\s+/g, '');
    
    const bsModal = new bootstrap.Modal(modalEl);
    bsModal.show();
};

window.copyContactPhone = function() {
    const phoneEl = document.getElementById('quickContactPhone');
    if (phoneEl) {
        const phone = phoneEl.innerText;
        navigator.clipboard.writeText(phone).then(() => {
            const btn = document.getElementById('quickContactCopyBtn');
            if (btn) {
                btn.innerHTML = '<i class="fa-solid fa-check text-success me-1"></i>Copied to Clipboard!';
                setTimeout(() => {
                    btn.innerHTML = '<i class="fa-solid fa-copy me-1"></i>Copy Phone Number';
                }, 2000);
            }
        });
    }
};

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
    const mapContainer = document.getElementById('driverLiveMap');
    if (!mapContainer) return;

    let driverMap = null;
    let driverMarker = null;
    let routeLayer = null;
    let stopsLayer = null;
    let currentDriverLat = parseFloat(mapContainer.getAttribute('data-driver-lat')) || 27.7172;
    let currentDriverLng = parseFloat(mapContainer.getAttribute('data-driver-lng')) || 85.3240;
    
    let activeStopsData = [];
    let stopMarkers = [];
    let pathCoordinates = [];

    const hudDistance = document.getElementById('hudTotalDistance');
    const hudTime = document.getElementById('hudTotalTime');
    const stopCountEl = document.getElementById('stopSequenceCount');
    const stopsContainer = document.getElementById('stopsSequenceContainer');
    const gpsStatusBadge = document.getElementById('gpsStatusIndicator');
    const btnLocateMe = document.getElementById('btnLocateMe');
    const btnPlanRoute = document.getElementById('btnPlanRoute');
    const shareToggle = document.getElementById('shareLocationToggle');
    const simulateToggle = document.getElementById('simulateMovementToggle');
    const stateSelect = document.getElementById('driverStateSelect');
    const filterPills = document.querySelectorAll('.route-tab-pill');

    // -------------------------------------------------------------
    // 1. INITIALIZE ENLARGED LEAFLET MAP
    // -------------------------------------------------------------
    function initMap() {
        if (typeof L === 'undefined') return;

        driverMap = L.map('driverLiveMap', {
            zoomControl: true,
            attributionControl: false
        }).setView([currentDriverLat, currentDriverLng], 14);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19
        }).addTo(driverMap);

        routeLayer = L.layerGroup().addTo(driverMap);
        stopsLayer = L.layerGroup().addTo(driverMap);

        const driverIcon = L.divIcon({
            className: 'custom-driver-icon',
            html: `
                <div class="driver-live-marker-wrap">
                    <div class="driver-live-pulse"></div>
                    <div class="driver-live-core">
                        <i class="fa-solid fa-motorcycle"></i>
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

        driverMarker.bindPopup('<strong>My Live Location</strong><br>ParcelFleet Rider Active');
    }

    // -------------------------------------------------------------
    // 2. FETCH & RENDER ROUTE + DYNAMIC STOPS
    // -------------------------------------------------------------
    function fetchAndRenderRoute() {
        return fetch('/api/driver/active-route')
            .then(res => res.json())
            .then(data => {
                if (!data || !driverMap) return;

                if (routeLayer) routeLayer.clearLayers();
                if (stopsLayer) stopsLayer.clearLayers();
                stopMarkers = [];
                activeStopsData = data.stops || [];

                // Update Metrics
                const distKm = Number(data.distance_km || 0).toFixed(1);
                const timeMin = Math.round(data.duration_min || 0);
                if (hudDistance) hudDistance.innerText = `${distKm} km`;
                if (hudTime) hudTime.innerText = `${timeMin} mins`;
                if (stopCountEl) stopCountEl.innerText = activeStopsData.length;

                // Render Road Polyline
                if (data.coordinates && data.coordinates.length > 0) {
                    pathCoordinates = data.coordinates;
                    const latlngs = data.coordinates.map(pt => [pt.lat, pt.lng]);

                    L.polyline(latlngs, {
                        color: '#1E40AF',
                        weight: 7,
                        opacity: 0.5,
                        lineCap: 'round',
                        lineJoin: 'round'
                    }).addTo(routeLayer);

                    const primaryPolyline = L.polyline(latlngs, {
                        color: '#2563EB',
                        weight: 4,
                        opacity: 0.95,
                        lineCap: 'round',
                        lineJoin: 'round'
                    }).addTo(routeLayer);

                    const bounds = primaryPolyline.getBounds();
                    if (bounds.isValid()) {
                        driverMap.fitBounds(bounds, { padding: [50, 50], maxZoom: 16 });
                    }
                } else {
                    pathCoordinates = [];
                }

                // Render Numbered Stop Markers & Dynamic Cards
                let cardsHtml = '';
                if (activeStopsData.length === 0) {
                    cardsHtml = `
                        <div class="text-center py-5 text-muted">
                            <i class="fa-solid fa-box-open fa-2x mb-2 text-secondary opacity-50"></i>
                            <p class="small mb-0">No active delivery stops assigned.</p>
                            <small style="font-size: 0.75rem;">Set state to 'Available' in settings.</small>
                        </div>
                    `;
                } else {
                    activeStopsData.forEach((stop, index) => {
                        const stopNum = stop.stop_number || (index + 1);
                        const isDelivery = (stop.action_type || '').includes('Deliver') || stop.status !== 'Assigned';
                        const markerClass = isDelivery ? 'stop-delivery' : 'stop-pickup';
                        const typeLabel = isDelivery ? 'DELIVERY' : 'PICKUP';
                        const contactName = (isDelivery ? stop.receiver_name : stop.sender_name) || 'Client';
                        const contactPhone = (isDelivery ? stop.receiver_phone : stop.sender_phone) || '';
                        const stopAddress = (isDelivery ? stop.delivery_address : stop.pickup_address) || stop.delivery_address || '';

                        // Marker Icon
                        const stopIcon = L.divIcon({
                            className: 'custom-stop-icon',
                            html: `<div class="stop-numbered-marker ${markerClass}">${stopNum}</div>`,
                            iconSize: [28, 28],
                            iconAnchor: [14, 14],
                            popupAnchor: [0, -14]
                        });

                        const popupHtml = `
                            <div style="font-size: 0.85rem; min-width: 190px;">
                                <div class="d-flex justify-content-between align-items-center mb-1">
                                    <span class="badge ${isDelivery ? 'bg-warning text-dark' : 'bg-success'} rounded-pill" style="font-size: 0.65rem;">Stop #${stopNum} &bull; ${typeLabel}</span>
                                    <strong class="text-primary">${stop.tracking_id || ''}</strong>
                                </div>
                                <h6 class="fw-bold mb-1 text-dark">${contactName}</h6>
                                <p class="text-muted small mb-2"><i class="fa-solid fa-location-dot text-danger me-1"></i>${stopAddress}</p>
                                <div class="d-flex gap-1">
                                    <button type="button" class="btn btn-xs btn-outline-secondary rounded-pill py-1 px-2" onclick="window.callContact('${contactName.replace(/'/g, "\\'")}', '${contactPhone}')" style="font-size: 0.72rem;">
                                        <i class="fa-solid fa-phone me-1"></i>Call (${contactPhone || 'N/A'})
                                    </button>
                                </div>
                            </div>
                        `;

                        const marker = L.marker([stop.lat, stop.lng], { icon: stopIcon })
                            .bindPopup(popupHtml)
                            .addTo(stopsLayer);

                        stopMarkers.push({
                            marker: marker,
                            type: isDelivery ? 'delivery' : 'pickup',
                            lat: stop.lat,
                            lng: stop.lng,
                            stopNum: stopNum
                        });

                        // Append Card HTML
                        cardsHtml += `
                            <div class="stop-sequence-card p-3 mb-2 rounded-3 border border-light shadow-sm" data-stop-type="${isDelivery ? 'delivery' : 'pickup'}" data-parcel-id="${stop.parcel_id || ''}" data-lat="${stop.lat}" data-lng="${stop.lng}">
                                <div class="d-flex justify-content-between align-items-center mb-2">
                                    <div class="d-flex align-items-center gap-2">
                                        <span class="stop-badge-number bg-primary text-white rounded-circle d-flex align-items-center justify-content-center fw-bold" style="width: 22px; height: 22px; font-size: 0.72rem;">
                                            ${stopNum}
                                        </span>
                                        <strong class="text-dark" style="font-size: 0.85rem;">${stop.tracking_id || ''}</strong>
                                    </div>
                                    <span class="badge rounded-pill ${isDelivery ? 'bg-warning-subtle text-warning-emphasis border border-warning border-opacity-25' : 'bg-success-subtle text-success border border-success border-opacity-25'}" style="font-size: 0.65rem; font-weight: 700; text-transform: uppercase;">
                                        ${typeLabel}
                                    </span>
                                </div>

                                <div class="mb-2">
                                    <h6 class="fw-bold text-dark mb-1" style="font-size: 0.88rem;">${contactName}</h6>
                                    <p class="text-muted small mb-0 d-flex align-items-start gap-1" style="font-size: 0.78rem; line-height: 1.3;">
                                        <i class="fa-solid fa-location-dot text-danger mt-1" style="font-size: 0.75rem;"></i>
                                        <span>${stopAddress}</span>
                                    </p>
                                </div>

                                <div class="d-flex justify-content-between align-items-center pt-2 border-top border-light">
                                    <button type="button" class="btn btn-sm btn-light border rounded-pill px-3 text-dark d-flex align-items-center gap-1" onclick="window.callContact('${contactName.replace(/'/g, "\\'")}', '${contactPhone}')" style="font-size: 0.75rem;">
                                        <i class="fa-solid fa-phone text-muted"></i>
                                        <span>Call</span>
                                    </button>
                                    <div class="d-flex gap-1">
                                        <button type="button" class="btn btn-sm btn-light border rounded-pill px-3 text-primary d-flex align-items-center gap-1 btn-nav-stop" data-lat="${stop.lat}" data-lng="${stop.lng}" style="font-size: 0.75rem;">
                                            <i class="fa-solid fa-location-arrow"></i>
                                            <span>Navigate</span>
                                        </button>
                                        <button type="button" class="btn btn-sm btn-primary rounded-pill px-3 d-flex align-items-center gap-1" data-bs-toggle="modal" data-bs-target="#updateStatusModal${stop.parcel_id || ''}" style="font-size: 0.75rem; background: #3B82F6; border: none;">
                                            <span>Handoff</span>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        `;
                    });
                }

                if (stopsContainer) {
                    stopsContainer.innerHTML = cardsHtml;
                }
            })
            .catch(err => console.error('Error fetching driver active route:', err));
    }

    // -------------------------------------------------------------
    // 3. LOCATE ME & PLAN ROUTE
    // -------------------------------------------------------------
    if (btnLocateMe) {
        btnLocateMe.addEventListener('click', function () {
            if (!navigator.geolocation) {
                alert('Geolocation is not supported by your browser.');
                return;
            }

            if (gpsStatusBadge) {
                gpsStatusBadge.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i>Locating...';
            }

            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    currentDriverLat = pos.coords.latitude;
                    currentDriverLng = pos.coords.longitude;
                    if (driverMarker) {
                        driverMarker.setLatLng([currentDriverLat, currentDriverLng]);
                    }
                    if (driverMap) {
                        driverMap.setView([currentDriverLat, currentDriverLng], 15, { animate: true });
                    }
                    if (gpsStatusBadge) {
                        gpsStatusBadge.className = 'badge bg-success bg-opacity-10 text-success border border-success';
                        gpsStatusBadge.innerHTML = `<i class="fa-solid fa-satellite-dish me-1"></i>GPS Fixed (&plusmn;${Math.round(pos.coords.accuracy)}m)`;
                    }
                    fetch('/api/driver/update-location', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ latitude: currentDriverLat, longitude: currentDriverLng })
                    });
                },
                (err) => {
                    console.warn('Locate Me error:', err.message);
                    if (gpsStatusBadge) {
                        gpsStatusBadge.className = 'badge bg-danger bg-opacity-10 text-danger border border-danger';
                        gpsStatusBadge.innerHTML = '<i class="fa-solid fa-triangle-exclamation me-1"></i>GPS Denied';
                    }
                },
                { enableHighAccuracy: true, timeout: 8000 }
            );
        });
    }

    if (btnPlanRoute) {
        btnPlanRoute.addEventListener('click', function () {
            btnPlanRoute.disabled = true;
            btnPlanRoute.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i>Optimizing...';

            fetchAndRenderRoute().finally(() => {
                btnPlanRoute.disabled = false;
                btnPlanRoute.innerHTML = '<i class="fa-solid fa-bolt me-1"></i>Plan Shortest Route';
            });
        });
    }

    // -------------------------------------------------------------
    // 4. FILTER TABS
    // -------------------------------------------------------------
    filterPills.forEach(pill => {
        pill.addEventListener('click', function () {
            filterPills.forEach(p => p.classList.remove('active'));
            this.classList.add('active');

            const filterType = this.getAttribute('data-filter');
            const stopCards = document.querySelectorAll('.stop-sequence-card');

            let visibleCount = 0;
            stopCards.forEach(card => {
                const cardType = card.getAttribute('data-stop-type');
                if (filterType === 'all' || cardType === filterType) {
                    card.classList.remove('d-none');
                    visibleCount++;
                } else {
                    card.classList.add('d-none');
                }
            });

            if (stopCountEl) stopCountEl.innerText = visibleCount;

            stopMarkers.forEach(item => {
                if (filterType === 'all' || item.type === filterType) {
                    if (!stopsLayer.hasLayer(item.marker)) {
                        stopsLayer.addLayer(item.marker);
                    }
                } else {
                    if (stopsLayer.hasLayer(item.marker)) {
                        stopsLayer.removeLayer(item.marker);
                    }
                }
            });
        });
    });

    // -------------------------------------------------------------
    // 5. NAVIGATE BUTTONS
    // -------------------------------------------------------------
    document.addEventListener('click', function (e) {
        const navBtn = e.target.closest('.btn-nav-stop');
        if (navBtn) {
            const lat = parseFloat(navBtn.getAttribute('data-lat'));
            const lng = parseFloat(navBtn.getAttribute('data-lng'));
            if (lat && lng && driverMap) {
                driverMap.setView([lat, lng], 16, { animate: true });
                const matched = stopMarkers.find(m => Math.abs(m.lat - lat) < 0.0001 && Math.abs(m.lng - lng) < 0.0001);
                if (matched && matched.marker) {
                    matched.marker.openPopup();
                }
            }
        }
    });

    // -------------------------------------------------------------
    // 6. CANVAS SIGNATURE
    // -------------------------------------------------------------
    const canvas = document.getElementById('signatureCanvas');
    const signatureInput = document.getElementById('customer_signature_data');
    const clearBtn = document.getElementById('clearSignature');
    
    if (canvas && signatureInput) {
        const ctx = canvas.getContext('2d');
        let isDrawing = false;
        let lastX = 0;
        let lastY = 0;

        const getCoords = (e) => {
            const rect = canvas.getBoundingClientRect();
            if (e.touches && e.touches.length > 0) {
                return { x: e.touches[0].clientX - rect.left, y: e.touches[0].clientY - rect.top };
            }
            return { x: e.clientX - rect.left, y: e.clientY - rect.top };
        };

        const startDraw = (e) => {
            isDrawing = true;
            const c = getCoords(e);
            lastX = c.x;
            lastY = c.y;
        };

        const drawMove = (e) => {
            if (!isDrawing) return;
            e.preventDefault();
            const c = getCoords(e);
            ctx.beginPath();
            ctx.moveTo(lastX, lastY);
            ctx.lineTo(c.x, c.y);
            ctx.stroke();
            lastX = c.x;
            lastY = c.y;
            signatureInput.value = canvas.toDataURL();
        };

        const stopDraw = () => { isDrawing = false; };

        canvas.addEventListener('mousedown', startDraw);
        canvas.addEventListener('mousemove', drawMove);
        canvas.addEventListener('mouseup', stopDraw);
        canvas.addEventListener('mouseout', stopDraw);

        canvas.addEventListener('touchstart', startDraw, { passive: false });
        canvas.addEventListener('touchmove', drawMove, { passive: false });
        canvas.addEventListener('touchend', stopDraw);

        if (clearBtn) {
            clearBtn.addEventListener('click', (e) => {
                e.preventDefault();
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                signatureInput.value = '';
            });
        }
    }

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
    // 7. DRIVER CONTROLS
    // -------------------------------------------------------------
    if (stateSelect) {
        stateSelect.addEventListener('change', function () {
            fetch('/api/driver/update-state', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ state: this.value })
            }).then(() => fetchAndRenderRoute());
        });
    }

    // Initialize Map and Initial Route Render
    initMap();
    fetchAndRenderRoute();
});
