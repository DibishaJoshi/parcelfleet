document.addEventListener('DOMContentLoaded', function () {
    // 1. LEAFLET MAP RENDERER FOR LIVE TRACKING PAGE
    const mapElement = document.getElementById('trackingMap');
    
    if (mapElement) {
        const trackingId = mapElement.getAttribute('data-tracking-id');
        
        // Initialize Map
        const map = L.map('trackingMap', {
            zoomControl: true,
            scrollWheelZoom: true
        }).setView([27.7172, 85.3240], 13); // Center on Kathmandu

        // Load OpenStreetMap tiles
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '© OpenStreetMap contributors'
        }).addTo(map);

        // Custom Markers Icons using FontAwesome
        const createCustomIcon = (iconClass, colorClass) => {
            return L.divIcon({
                html: `<div class="custom-map-icon ${colorClass}"><i class="${iconClass}"></i></div>`,
                className: 'custom-leaflet-icon',
                iconSize: [36, 36],
                iconAnchor: [18, 36]
            });
        };

        const pickupIcon = createCustomIcon('fas fa-box', 'pickup');
        const deliveryIcon = createCustomIcon('fas fa-home', 'delivery');
        const driverIcon = createCustomIcon('fas fa-motorcycle', 'driver-active');

        // Smooth sliding and rotation functions in the style of Pathao/InDrive
        const calculateBearing = (startLat, startLng, endLat, endLng) => {
            const dLon = (endLng - startLng) * Math.PI / 180;
            const lat1 = startLat * Math.PI / 180;
            const lat2 = endLat * Math.PI / 180;
            const y = Math.sin(dLon) * Math.cos(lat2);
            const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
            const brng = Math.atan2(y, x) * 180 / Math.PI;
            return (brng + 360) % 360;
        };

        const slideMarker = (marker, targetLatLng, duration) => {
            if (!marker) return;
            const startLatLng = marker.getLatLng();
            const endLatLng = L.latLng(targetLatLng);
            
            if (startLatLng.lat === endLatLng.lat && startLatLng.lng === endLatLng.lng) {
                return;
            }
            
            const bearing = calculateBearing(startLatLng.lat, startLatLng.lng, endLatLng.lat, endLatLng.lng);
            
            const markerElem = marker.getElement();
            if (markerElem) {
                const iconInner = markerElem.querySelector('.custom-map-icon');
                if (iconInner) {
                    iconInner.style.transition = 'transform 0.5s ease';
                    // fa-motorcycle is pointing LEFT (270deg) by default, so we rotate by bearing - 270 degrees
                    iconInner.style.transform = `rotate(${bearing - 270}deg)`;
                }
            }
            
            const startTime = performance.now();
            
            const animate = (currentTime) => {
                const elapsed = currentTime - startTime;
                const progress = Math.min(elapsed / duration, 1);
                
                const lat = startLatLng.lat + (endLatLng.lat - startLatLng.lat) * progress;
                const lng = startLatLng.lng + (endLatLng.lng - startLatLng.lng) * progress;
                
                marker.setLatLng([lat, lng]);
                
                if (progress < 1) {
                    requestAnimationFrame(animate);
                }
            };
            
            requestAnimationFrame(animate);
        };

        // Add custom styles for map icons dynamically if not present
        const style = document.createElement('style');
        style.innerHTML = `
            .custom-map-icon {
                width: 36px;
                height: 36px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #FFFFFF;
                font-size: 1rem;
                box-shadow: 0 4px 6px rgba(0,0,0,0.15);
                border: 2px solid #FFFFFF;
            }
            .custom-map-icon.pickup { background-color: #F59E0B; }
            .custom-map-icon.delivery { background-color: #22C55E; }
            .custom-map-icon.driver-active { background-color: #2563EB; animation: pulse-driver 1.5s infinite; }
            @keyframes pulse-driver {
                0% { box-shadow: 0 0 0 0px rgba(37, 99, 235, 0.4); }
                100% { box-shadow: 0 0 0 8px rgba(37, 99, 235, 0); }
            }
            .route-flow-line {
                stroke-dasharray: 8, 16;
                animation: route-flow-anim 1.5s linear infinite;
            }
            @keyframes route-flow-anim {
                to {
                    stroke-dashoffset: -24;
                }
            }
        `;
        document.head.appendChild(style);

        let pickupMarker = null;
        let deliveryMarker = null;
        let driverMarker = null;
        let routePolyline = null;
        let pathCoords = [];
        let activeRouteLayers = [];
        let hasZoomedOnce = false;
        let selectedRouteIndex = 0;
        let globalRouteData = null;

        const drawRoute = (data) => {
            // Clear existing route layers
            activeRouteLayers.forEach(layer => map.removeLayer(layer));
            activeRouteLayers = [];

            if (!data.routes || data.routes.length === 0) return;

            const segmentLayers = [];

            // Draw alternative routes first (so active route sits on top)
            data.routes.forEach(route => {
                if (route.route_index !== selectedRouteIndex) {
                    const pts = route.coordinates.map(pt => [pt.lat, pt.lng]);
                    
                    // Outer gray border casing
                    const casing = L.polyline(pts, {
                        color: '#64748B',
                        weight: 8,
                        opacity: 0.4,
                        lineCap: 'round',
                        lineJoin: 'round'
                    }).addTo(map);
                    
                    // Inner light gray fill
                    const fill = L.polyline(pts, {
                        color: '#94A3B8',
                        weight: 4,
                        opacity: 0.6,
                        lineCap: 'round',
                        lineJoin: 'round'
                    }).addTo(map);

                    // Click handler to switch routes
                    const selectAlternative = () => {
                        selectedRouteIndex = route.route_index;
                        drawRoute(data);
                        
                        // Update ETA, Distance metrics instantly
                        const etaVal = document.getElementById('eta_minutes');
                        const distVal = document.getElementById('distance_remaining');
                        if (etaVal) etaVal.innerText = Math.round(route.duration_min) + ' Mins';
                        if (distVal) distVal.innerText = route.distance_km.toFixed(2) + ' Km';
                    };
                    
                    casing.on('click', selectAlternative);
                    fill.on('click', selectAlternative);
                    
                    // Bind popup showing alternative route metrics
                    fill.bindPopup(`
                        <div class="p-1 text-center">
                            <strong class="text-dark">${route.name}</strong><br>
                            <span class="text-muted">${Math.round(route.duration_min)} Mins | ${route.distance_km.toFixed(1)} Km</span>
                        </div>
                    `);
                    
                    activeRouteLayers.push(casing, fill);
                    segmentLayers.push(casing);
                }
            });

            // Draw the active/selected route last (so it sits on top)
            const activeRoute = data.routes.find(r => r.route_index === selectedRouteIndex) || data.routes[0];
            if (activeRoute) {
                // If it is the recommended route (index 0) and we have traffic segments from the server
                if (activeRoute.route_index === 0 && data.segments && data.segments.length > 0) {
                    data.segments.forEach(seg => {
                        const pts = seg.coordinates.map(pt => [pt.lat, pt.lng]);
                        
                        const casingPoly = L.polyline(pts, {
                            color: '#1E293B',
                            weight: 10,
                            opacity: 0.9,
                            lineCap: 'round',
                            lineJoin: 'round'
                        }).addTo(map);
                        
                        const fillPoly = L.polyline(pts, {
                            color: seg.color,
                            weight: 6,
                            opacity: 1.0,
                            lineCap: 'round',
                            lineJoin: 'round'
                        }).addTo(map);
                        
                        const flowPoly = L.polyline(pts, {
                            color: '#FFFFFF',
                            weight: 2,
                            opacity: 0.75,
                            className: 'route-flow-line',
                            lineCap: 'round',
                            lineJoin: 'round'
                        }).addTo(map);
                        
                        flowPoly.bindPopup(`
                            <div class="p-1">
                                <h6 class="fw-bold mb-1 text-dark" style="font-size: 0.85rem;">${seg.from} &rarr; ${seg.to}</h6>
                                <p class="mb-1 text-muted" style="font-size: 0.75rem;"><i class="fas fa-traffic-light me-1"></i>Traffic: <span class="badge bg-${seg.traffic === 'Light' ? 'success' : (seg.traffic === 'Moderate' ? 'warning' : 'danger')}">${seg.traffic}</span></p>
                                <p class="mb-1 text-muted" style="font-size: 0.75rem;"><i class="fas fa-road me-1"></i>Condition: ${seg.condition}</p>
                                <p class="mb-0 text-muted" style="font-size: 0.75rem;"><i class="fas fa-gauge me-1"></i>Speed Limit: ${seg.speed_limit} km/h</p>
                            </div>
                        `);
                        
                        segmentLayers.push(casingPoly);
                        activeRouteLayers.push(casingPoly, fillPoly, flowPoly);
                    });
                } else {
                    // Draw active route as standard blue route
                    const pts = activeRoute.coordinates.map(pt => [pt.lat, pt.lng]);
                    
                    const casingPoly = L.polyline(pts, {
                        color: '#1E293B',
                        weight: 10,
                        opacity: 0.9,
                        lineCap: 'round',
                        lineJoin: 'round'
                    }).addTo(map);
                    
                    const fillPoly = L.polyline(pts, {
                        color: '#2563EB', // Google Maps Blue
                        weight: 6,
                        opacity: 1.0,
                        lineCap: 'round',
                        lineJoin: 'round'
                    }).addTo(map);
                    
                    const flowPoly = L.polyline(pts, {
                        color: '#FFFFFF',
                        weight: 2,
                        opacity: 0.75,
                        className: 'route-flow-line',
                        lineCap: 'round',
                        lineJoin: 'round'
                    }).addTo(map);
                    
                    flowPoly.bindPopup(`
                        <div class="p-1 text-center">
                            <strong class="text-dark">${activeRoute.name} (Active)</strong><br>
                            <span class="text-muted">${Math.round(activeRoute.duration_min)} Mins | ${activeRoute.distance_km.toFixed(1)} Km</span>
                        </div>
                    `);
                    
                    segmentLayers.push(casingPoly);
                    activeRouteLayers.push(casingPoly, fillPoly, flowPoly);
                }
            }

            // Update alternative routes buttons list in HTML if container exists
            const altRoutesContainer = document.getElementById('alternative_routes_list');
            if (altRoutesContainer && data.routes) {
                altRoutesContainer.innerHTML = '';
                data.routes.forEach(route => {
                    const isSelected = route.route_index === selectedRouteIndex;
                    const btn = document.createElement('button');
                    btn.className = `btn btn-sm w-100 text-start d-flex align-items-center justify-content-between p-2 mb-2 border ${isSelected ? 'btn-primary text-white border-primary shadow-sm' : 'btn-outline-secondary text-dark border-light'}`;
                    btn.style.fontSize = '0.75rem';
                    btn.style.transition = 'all 0.2s ease';
                    btn.style.borderRadius = '20px';
                    btn.innerHTML = `
                        <span>
                            <i class="fas ${isSelected ? 'fa-circle-check text-white' : 'fa-circle text-muted'} me-2"></i>
                            <strong>${route.name}</strong>
                        </span>
                        <span class="badge ${isSelected ? 'bg-white text-primary' : 'bg-secondary text-white'} rounded-pill">
                            ${Math.round(route.duration_min)}m | ${route.distance_km.toFixed(1)} km
                        </span>
                    `;
                    btn.addEventListener('click', () => {
                        selectedRouteIndex = route.route_index;
                        drawRoute(data);
                        
                        // Update ETA, Distance metrics instantly
                        const etaVal = document.getElementById('eta_minutes');
                        const distVal = document.getElementById('distance_remaining');
                        if (etaVal) etaVal.innerText = Math.round(route.duration_min) + ' Mins';
                        if (distVal) distVal.innerText = route.distance_km.toFixed(2) + ' Km';
                    });
                    altRoutesContainer.appendChild(btn);
                });
            }

            // Zoom map to fit all segments once
            if (!hasZoomedOnce && segmentLayers.length > 0) {
                const group = new L.featureGroup(segmentLayers);
                map.fitBounds(group.getBounds(), { padding: [50, 50] });
                hasZoomedOnce = true;
            }
        };

        // Fetch parcel data and path
        fetch(`/api/parcel/${trackingId}/route`)
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    console.error('Error fetching route data: ', data.error);
                    return;
                }
                globalRouteData = data;

                const pickup = data.pickup;
                const delivery = data.delivery;
                pathCoords = data.path;

                // Add Pickup and Delivery Markers
                pickupMarker = L.marker([pickup.lat, pickup.lng], { icon: pickupIcon })
                    .addTo(map)
                    .bindPopup(`<strong>Pickup:</strong> ${pickup.name}`);

                deliveryMarker = L.marker([delivery.lat, delivery.lng], { icon: deliveryIcon })
                    .addTo(map)
                    .bindPopup(`<strong>Delivery:</strong> ${delivery.name}`);

                // Draw route initially
                drawRoute(data);

                // Add Driver Marker
                if (data.driver) {
                    driverMarker = L.marker([data.driver.lat, data.driver.lng], { icon: driverIcon })
                        .addTo(map)
                        .bindPopup(`<strong>Driver:</strong> ${data.driver.name}<br><strong>Vehicle:</strong> ${data.driver.vehicle}`);
                }

                // Populate route segments list in HTML if element exists
                const segListContainer = document.getElementById('route_segments_list');
                if (segListContainer && data.segments) {
                    segListContainer.innerHTML = '';
                    data.segments.forEach(seg => {
                        const div = document.createElement('div');
                        div.className = 'd-flex align-items-start gap-2 mb-2 p-2 border-bottom border-light';
                        
                        // Icon color mapping
                        let textClass = 'text-success';
                        let bgClass = 'bg-success-subtle';
                        if (seg.traffic === 'Heavy') {
                            textClass = 'text-danger';
                            bgClass = 'bg-danger-subtle';
                        } else if (seg.traffic === 'Moderate') {
                            textClass = 'text-warning';
                            bgClass = 'bg-warning-subtle';
                        }
                        
                        div.innerHTML = `
                            <div class="${bgClass} ${textClass} rounded-circle px-2 py-1" style="font-size: 0.75rem; min-width: 28px; text-align: center;">
                                <i class="fas fa-route"></i>
                            </div>
                            <div>
                                <p class="mb-0 text-dark fw-semibold" style="font-size: 0.85rem;">${seg.from} &rarr; ${seg.to}</p>
                                <span class="d-block text-muted" style="font-size: 0.75rem;"><strong>Condition:</strong> ${seg.condition}</span>
                                <span class="badge ${bgClass} ${textClass} border-0 rounded-pill" style="font-size: 0.65rem; margin-top: 3px;">Traffic: ${seg.traffic} (${seg.speed_limit} km/h limit)</span>
                            </div>
                        `;
                        segListContainer.appendChild(div);
                    });
                }

                // Start Live Telemetry Polling Loop
                pollTelemetry();
                setInterval(pollTelemetry, 10000); // Poll every 10 seconds
            })
            .catch(err => {
                console.error('Error fetching route data: ', err);
                const segListContainer = document.getElementById('route_segments_list');
                if (segListContainer) {
                    segListContainer.innerHTML = '<p class="text-danger mb-0" style="font-size: 0.8rem;"><i class="fas fa-triangle-exclamation me-2"></i>Failed to load route details.</p>';
                }
            });

        const pollTelemetry = () => {
            fetch(`/api/parcel/${trackingId}/telemetry`)
                .then(res => res.json())
                .then(telemetry => {
                    // Update Marker coordinates
                    if (telemetry.driver_latitude && telemetry.driver_longitude) {
                        if (driverMarker) {
                            slideMarker(driverMarker, [telemetry.driver_latitude, telemetry.driver_longitude], 9500);
                        } else {
                            driverMarker = L.marker([telemetry.driver_latitude, telemetry.driver_longitude], { icon: driverIcon })
                                .addTo(map)
                                .bindPopup(`<strong>Driver:</strong> Active<br><strong>Vehicle:</strong> Assigned`);
                        }
                        
                        // Dynamically update the route line from the driver's new position
                        fetch(`/api/parcel/${trackingId}/route`)
                            .then(res => res.json())
                            .then(routeData => {
                                globalRouteData = routeData;
                                drawRoute(routeData);
                            });
                    }

                    // Update ETA metrics in HTML cards
                    const etaVal = document.getElementById('eta_minutes');
                    const distVal = document.getElementById('distance_remaining');
                    const progressVal = document.getElementById('delivery_progress_fill');
                    const progressPct = document.getElementById('progress_percentage_text');
                    const speedVal = document.getElementById('current_speed');
                    const statusText = document.getElementById('telemetry_status_text');

                    const selectedRoute = (globalRouteData && globalRouteData.routes) ? globalRouteData.routes.find(r => r.route_index === selectedRouteIndex) : null;
                    if (selectedRoute && (selectedRouteIndex !== 0 || !telemetry.driver_latitude)) {
                        if (etaVal) etaVal.innerText = Math.round(selectedRoute.duration_min) + ' Mins';
                        if (distVal) distVal.innerText = selectedRoute.distance_km.toFixed(2) + ' Km';
                    } else {
                        if (etaVal) etaVal.innerText = telemetry.eta_minutes + ' Mins';
                        if (distVal) distVal.innerText = telemetry.distance_remaining_km.toFixed(2) + ' Km';
                    }
                    if (speedVal) speedVal.innerText = telemetry.speed_kmh.toFixed(1) + ' km/h';
                    if (statusText) statusText.innerText = telemetry.status;
                    
                    if (progressVal && progressPct) {
                        const pct = Math.round(telemetry.progress_percent);
                        progressVal.style.width = pct + '%';
                        progressPct.innerText = pct + '% Completed';
                    }

                    // Update chronological timeline checks
                    const timelineSteps = document.querySelectorAll('.timeline-step');
                    const activeStatus = telemetry.status.toLowerCase();

                    let foundActive = false;
                    timelineSteps.forEach(step => {
                        const status = step.getAttribute('data-status-key').toLowerCase();
                        
                        if (status === activeStatus) {
                            step.className = 'timeline-step active';
                            foundActive = true;
                        } else if (!foundActive) {
                            step.className = 'timeline-step completed';
                        } else {
                            step.className = 'timeline-step';
                        }
                    });

                    // Dynamic Notification Alert Feeds
                    const alertContainer = document.getElementById('notification_alerts_feed');
                    if (alertContainer && telemetry.notifications) {
                        alertContainer.innerHTML = '';
                        telemetry.notifications.forEach(log => {
                            const date = new Date(log.timestamp);
                            const formattedTime = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                            
                            const div = document.createElement('div');
                            div.className = 'd-flex align-items-start gap-2 mb-2 p-2 border-bottom border-light';
                            div.innerHTML = `
                                <div class="bg-primary-subtle text-primary rounded-circle p-1" style="font-size: 0.75rem;">
                                    <i class="fas fa-bell"></i>
                                </div>
                                <div>
                                    <p class="mb-0 text-dark" style="font-size: 0.85rem;">${log.message}</p>
                                    <span class="text-muted" style="font-size: 0.7rem;">${formattedTime} - ${log.type}</span>
                                </div>
                            `;
                            alertContainer.appendChild(div);
                        });
                    }
                })
                .catch(err => console.error('Error polling telemetry: ', err));
        };
    }

    // 2. FLEET MAP INITIALIZER FOR DRIVERS PAGE
    const fleetMapElement = document.getElementById('fleetMap');
    if (fleetMapElement) {
        const fleetMap = L.map('fleetMap').setView([27.7172, 85.3240], 13);
        
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '© OpenStreetMap contributors'
        }).addTo(fleetMap);

        // Custom FontAwesome Icons for Driver status states
        const getDriverIconColor = (state) => {
            if (state === 'Available') return 'green';
            if (state === 'On Delivery') return 'blue';
            if (state === 'On Break') return 'orange';
            return 'gray';
        };

        const createDriverIcon = (state) => {
            const color = getDriverIconColor(state);
            return L.divIcon({
                html: `<div class="custom-map-icon bg-${color}-status"><i class="fas fa-motorcycle"></i></div>`,
                className: 'custom-leaflet-icon',
                iconSize: [32, 32],
                iconAnchor: [16, 32]
            });
        };

        // Inject color status styles dynamically
        const style = document.createElement('style');
        style.innerHTML = `
            .bg-green-status { background-color: #22C55E; }
            .bg-blue-status { background-color: #2563EB; }
            .bg-orange-status { background-color: #F59E0B; }
            .bg-gray-status { background-color: #64748B; }
        `;
        document.head.appendChild(style);

        let driverMarkers = {};

        const pollFleetLocations = () => {
            fetch('/api/admin/drivers-location')
                .then(res => res.json())
                .then(drivers => {
                    let bounds = [];
                    drivers.forEach(d => {
                        const icon = createDriverIcon(d.availability);
                        const pos = [d.latitude, d.longitude];
                        bounds.push(pos);

                        if (driverMarkers[d.id]) {
                            // Update marker pos & icon
                            driverMarkers[d.id].setLatLng(pos);
                            driverMarkers[d.id].setIcon(icon);
                        } else {
                            // Create marker
                            driverMarkers[d.id] = L.marker(pos, { icon: icon })
                                .addTo(fleetMap)
                                .bindPopup(`
                                    <strong>${d.name}</strong><br>
                                    Vehicle: ${d.vehicle}<br>
                                    Status: <span class="badge bg-${d.availability === 'Available' ? 'success' : d.availability === 'On Delivery' ? 'primary' : d.availability === 'On Break' ? 'warning' : 'secondary'}">${d.availability}</span>
                                `);
                        }
                    });

                    // Fit map bounds to drivers if we have markers and it's the first load
                    if (bounds.length > 0 && Object.keys(driverMarkers).length === drivers.length) {
                        fleetMap.fitBounds(bounds, { padding: [40, 40] });
                    }
                })
                .catch(err => console.error('Error fetching fleet locations: ', err));
        };

        pollFleetLocations();
        setInterval(pollFleetLocations, 10000); // Refresh every 10 seconds
    }
});
