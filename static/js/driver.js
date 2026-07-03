document.addEventListener('DOMContentLoaded', function () {
    // 1. DIGITAL CANVAS SIGNATURE PAD HANDLER
    const canvas = document.getElementById('signatureCanvas');
    const signatureInput = document.getElementById('customer_signature_data');
    const clearBtn = document.getElementById('clearSignature');
    
    if (canvas && signatureInput) {
        const ctx = canvas.getContext('2d');
        let isDrawing = false;
        let lastX = 0;
        let lastY = 0;

        // Size canvas dynamically to fit border wrapper
        const resizeCanvas = () => {
            const rect = canvas.getBoundingClientRect();
            canvas.width = rect.width;
            canvas.height = rect.height;
            
            // Set canvas stroke styles
            ctx.strokeStyle = '#0F172A'; // Charcoal color
            ctx.lineWidth = 3;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
        };

        window.addEventListener('resize', resizeCanvas);
        // Wait a small delay to make sure UI is rendered
        setTimeout(resizeCanvas, 200);

        const getCoordinates = (e) => {
            const rect = canvas.getBoundingClientRect();
            // Support both touch and mouse coords
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
            e.preventDefault(); // Prevent scrolling on mobile touch
            
            const coords = getCoordinates(e);
            ctx.beginPath();
            ctx.moveTo(lastX, lastY);
            ctx.lineTo(coords.x, coords.y);
            ctx.stroke();
            
            lastX = coords.x;
            lastY = coords.y;
            
            // Write to base64 input
            signatureInput.value = canvas.toDataURL();
        };

        const stopDrawing = () => {
            isDrawing = false;
        };

        // Mouse Events
        canvas.addEventListener('mousedown', startDrawing);
        canvas.addEventListener('mousemove', draw);
        canvas.addEventListener('mouseup', stopDrawing);
        canvas.addEventListener('mouseout', stopDrawing);

        // Touch Events (Mobile/Tablet Support)
        canvas.addEventListener('touchstart', startDrawing);
        canvas.addEventListener('touchmove', draw);
        canvas.addEventListener('touchend', stopDrawing);

        // Clear Canvas
        if (clearBtn) {
            clearBtn.addEventListener('click', (e) => {
                e.preventDefault();
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                signatureInput.value = '';
            });
        }
    }

    // 2. FILE UPLOADS PREVIEW TRIGGER
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

    // 3. SIMULATED GPS GPS-TELEMETRY TICKER LOOP
    const shareLocationToggle = document.getElementById('shareLocationToggle');
    let sharingInterval = null;
    let pathCoordinates = [];
    let pathIndex = 0;

    if (shareLocationToggle) {
        const driverId = shareLocationToggle.getAttribute('data-driver-id');
        
        const fetchActiveRoute = () => {
            // Fetch route coordinates for the current active/In Transit parcel assigned to the driver
            return fetch('/api/driver/active-route')
                .then(res => res.json())
                .then(data => {
                    if (data && data.coordinates && data.coordinates.length > 0) {
                        pathCoordinates = data.coordinates;
                        pathIndex = 0;
                        console.log('Driver Route Coordinates loaded successfully: ', pathCoordinates);
                    } else {
                        pathCoordinates = [];
                        console.log('No active in-transit parcel route found. Will broadcast current base coordinate.');
                    }
                });
        };

        const sendLocationUpdate = (lat, lng, availabilityState) => {
            const payload = { availability: availabilityState };
            if (lat !== null && lng !== null && lat !== undefined && lng !== undefined) {
                payload.latitude = lat;
                payload.longitude = lng;
            }

            fetch('/api/driver/location', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                console.log('Live Telemetry Logged: ', data);
                
                // Show a toast message if coordinates are updated
                const toastContainer = document.getElementById('toast-container');
                if (toastContainer && lat !== null && lng !== null && lat !== undefined && lng !== undefined) {
                    showToast('Telemetry Synchronized', 'Simulated GPS Broadcasted: ' + lat.toFixed(5) + ', ' + lng.toFixed(5), 'info');
                }
            })
            .catch(err => console.error('GPS broadcast error: ', err));
        };

        const tickLocationSimulation = () => {
            const stateSelect = document.getElementById('driverStateSelect');
            const selectedState = stateSelect ? stateSelect.value : 'Available';
            const state = pathCoordinates.length > 0 ? 'On Delivery' : selectedState;

            // Attempt to get the device's REAL coordinates first (High Accuracy)
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    (position) => {
                        const realLat = position.coords.latitude;
                        const realLng = position.coords.longitude;
                        
                        // Boundary check: coordinates must reside within Kathmandu Valley (Lat: 27.5-27.9, Lng: 85.1-85.5)
                        if (realLat >= 27.50 && realLat <= 27.90 && realLng >= 85.10 && realLng <= 85.55) {
                            console.log('Real Device Location Captured within bounds: ', realLat, realLng);
                            sendLocationUpdate(realLat, realLng, state);
                        } else {
                            console.warn('Real GPS coordinates (' + realLat + ', ' + realLng + ') reside outside Kathmandu bounds. Automatically falling back to Dijkstra routing simulation.');
                            runSimulationFallback(state);
                        }
                    },
                    (error) => {
                        console.warn('Real GPS access denied/error. Falling back to simulation: ', error.message);
                        runSimulationFallback(state);
                    },
                    { enableHighAccuracy: true, timeout: 5000, maximumAge: 0 }
                );
            }
 else {
                console.warn('Geolocation API not supported. Falling back to simulation.');
                runSimulationFallback(state);
            }
        };

        const runSimulationFallback = (state) => {
            if (pathCoordinates.length > 0) {
                // Traversal along Dijkstra path simulation
                const currentCoord = pathCoordinates[pathIndex];
                sendLocationUpdate(currentCoord.lat, currentCoord.lng, state);
                
                // Move to next node in path
                pathIndex = (pathIndex + 1) % pathCoordinates.length;
            } else {
                // Keep current database coordinates (do not force reset to Thamel)
                sendLocationUpdate(null, null, state);
            }
        };

        const startSharing = () => {
            console.log('Live location telemetry broadcast enabled.');
            localStorage.setItem('shareLocation_' + driverId, 'true');
            fetchActiveRoute().then(() => {
                tickLocationSimulation(); // Run first tick instantly
                if (sharingInterval) clearInterval(sharingInterval);
                sharingInterval = setInterval(tickLocationSimulation, 10000);
            });
        };

        const stopSharing = () => {
            console.log('Live location telemetry broadcast disabled.');
            localStorage.setItem('shareLocation_' + driverId, 'false');
            if (sharingInterval) {
                clearInterval(sharingInterval);
                sharingInterval = null;
            }
            
            const stateSelect = document.getElementById('driverStateSelect');
            const selectedState = stateSelect ? stateSelect.value : 'Offline';
            sendLocationUpdate(null, null, selectedState);
        };

        shareLocationToggle.addEventListener('change', function () {
            if (this.checked) {
                startSharing();
            } else {
                alert("Location sharing is turned off. Live location is required for active deliveries. Please enable location sharing.");
                stopSharing();
            }
        });

        // Dropdown state select change listener
        const stateSelect = document.getElementById('driverStateSelect');
        if (stateSelect) {
            stateSelect.addEventListener('change', function () {
                if (!shareLocationToggle.checked) {
                    sendLocationUpdate(null, null, this.value);
                }
            });
        }

        // Restore toggled state from localStorage
        const storedShareState = localStorage.getItem('shareLocation_' + driverId);
        if (storedShareState === 'true') {
            shareLocationToggle.checked = true;
            startSharing();
        } else {
            shareLocationToggle.checked = false;
            // Ask to allow location if currently disabled on load
            setTimeout(() => {
                const allow = confirm("Location sharing is currently disabled. Would you like to enable live GPS location sharing to allow customers and administrators to track your active deliveries?");
                if (allow) {
                    shareLocationToggle.checked = true;
                    startSharing();
                }
            }, 1500);
        }

        // Automatic GPS sync check on startup (only if location sharing is active)
        if (shareLocationToggle.checked && navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const startupLat = position.coords.latitude;
                    const startupLng = position.coords.longitude;
                    const stateSelect = document.getElementById('driverStateSelect');
                    const selectedState = stateSelect ? stateSelect.value : 'Available';
                    console.log('Initial startup GPS coordinates registered: ', startupLat, startupLng);
                    sendLocationUpdate(startupLat, startupLng, selectedState);
                },
                (err) => console.log('Initial startup GPS access skipped: ', err.message),
                { enableHighAccuracy: true, timeout: 5000 }
            );
        }
    }

    // Helper functions for showing alerts
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
            setTimeout(() => toast.remove(), 500);
        }, 5000);
    }
});
