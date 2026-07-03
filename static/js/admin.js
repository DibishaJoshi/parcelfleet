document.addEventListener('DOMContentLoaded', function () {
    // Initialize Theme Mode
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    
    // Sidebar Toggle
    const toggleBtn = document.getElementById('toggleSidebar');
    const sidebar = document.getElementById('sidebar');
    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener('click', () => {
            sidebar.classList.toggle('show');
        });
    }

    // Dynamic Volumetric and Charge Pricing Calculator
    const pWeight = document.getElementById('parcel_weight');
    const pLength = document.getElementById('parcel_length');
    const pWidth = document.getElementById('parcel_width');
    const pHeight = document.getElementById('parcel_height');
    const pType = document.getElementById('parcel_type');
    const pCharge = document.getElementById('estimated_charge');
    const pChargeableWeight = document.getElementById('chargeable_weight_display');

    if (pWeight && pLength && pWidth && pHeight && pType) {
        const calculatePrice = () => {
            const w = parseFloat(pWeight.value) || 0;
            const l = parseFloat(pLength.value) || 0;
            const wd = parseFloat(pWidth.value) || 0;
            const h = parseFloat(pHeight.value) || 0;
            const type = pType.value;

            // Compute Volumetric Weight
            const volWeight = (l * wd * h) / 5000;
            const chargeableWeight = Math.max(w, volWeight);

            if (pChargeableWeight) {
                pChargeableWeight.textContent = chargeableWeight.toFixed(2) + ' Kg (Volumetric: ' + volWeight.toFixed(2) + ' Kg)';
            }

            // Estimate Charge based on category
            let base = 130;
            let perKg = 15;

            if (type === 'Documents') { base = 100; perKg = 0; }
            else if (type === 'Electronics') { base = 200; perKg = 30; }
            else if (type === 'Clothing') { base = 120; perKg = 15; }
            else if (type === 'Food Items') { base = 150; perKg = 25; }
            else if (type === 'Fragile Goods') { base = 250; perKg = 40; }
            else if (type === 'Medical Supplies') { base = 180; perKg = 20; }
            else if (type === 'Others') { base = 130; perKg = 15; }

            const totalCharge = base + (chargeableWeight * perKg);
            if (pCharge) {
                pCharge.value = Math.ceil(totalCharge);
            }
        };

        [pWeight, pLength, pWidth, pHeight, pType].forEach(el => {
            el.addEventListener('input', calculatePrice);
        });
        pType.addEventListener('change', calculatePrice);
    }

    // Chart.js Setup for Admin Dashboard
    const statusChartCanvas = document.getElementById('statusChart');
    const trendsChartCanvas = document.getElementById('trendsChart');
    
    if (statusChartCanvas || trendsChartCanvas) {
        // Fetch analytics from API
        fetch('/api/admin/analytics')
            .then(res => res.json())
            .then(data => {
                // 1. Status breakdown Chart
                if (statusChartCanvas) {
                    new Chart(statusChartCanvas, {
                        type: 'doughnut',
                        data: {
                            labels: Object.keys(data.status_counts),
                            datasets: [{
                                data: Object.values(data.status_counts),
                                backgroundColor: [
                                    '#F59E0B', // Pending - Orange
                                    '#2563EB', // Assigned - Blue
                                    '#06B6D4', // Picked Up - Info Cyan
                                    '#8B5CF6', // In Transit - Purple
                                    '#EC4899', // Out For Delivery - Pink
                                    '#22C55E', // Delivered - Green
                                    '#EF4444'  // Cancelled - Red
                                ],
                                borderWidth: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: {
                                    position: 'bottom',
                                    labels: {
                                        color: getComputedStyle(document.body).getPropertyValue('--text-color').trim()
                                    }
                                }
                            }
                        }
                    });
                }

                // 2. Monthly Trend Chart
                if (trendsChartCanvas) {
                    new Chart(trendsChartCanvas, {
                        type: 'line',
                        data: {
                            labels: data.monthly_trends.labels,
                            datasets: [{
                                label: 'Deliveries',
                                data: data.monthly_trends.counts,
                                borderColor: '#2563EB',
                                backgroundColor: 'rgba(37, 99, 235, 0.05)',
                                fill: true,
                                tension: 0.4
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: { display: false }
                            },
                            scales: {
                                y: {
                                    grid: { color: getComputedStyle(document.body).getPropertyValue('--border-color').trim() },
                                    ticks: { color: getComputedStyle(document.body).getPropertyValue('--text-muted').trim() }
                                },
                                x: {
                                    grid: { display: false },
                                    ticks: { color: getComputedStyle(document.body).getPropertyValue('--text-muted').trim() }
                                }
                            }
                        }
                    });
                }
            });
    }

    // Dynamic Filter & Search Table Controller
    const searchInput = document.getElementById('tableSearch');
    const statusFilter = document.getElementById('filterStatus');
    const paymentFilter = document.getElementById('filterPayment');
    const tableRows = document.querySelectorAll('.premium-table tbody tr');

    if (searchInput || statusFilter || paymentFilter) {
        const filterTable = () => {
            const query = searchInput ? searchInput.value.toLowerCase() : '';
            const statusVal = statusFilter ? statusFilter.value.toLowerCase() : '';
            const paymentVal = paymentFilter ? paymentFilter.value.toLowerCase() : '';

            tableRows.forEach(row => {
                let textMatch = false;
                let statusMatch = false;
                let paymentMatch = false;

                // 1. Text search columns: Tracking ID, Sender, Receiver, Phone
                const rowText = row.innerText.toLowerCase();
                if (rowText.includes(query)) {
                    textMatch = true;
                }

                // 2. Status Match
                const rowStatusAttr = row.getAttribute('data-status') || '';
                if (!statusVal || rowStatusAttr.toLowerCase() === statusVal) {
                    statusMatch = true;
                }

                // 3. Payment Match
                const rowPaymentAttr = row.getAttribute('data-payment') || '';
                if (!paymentVal || rowPaymentAttr.toLowerCase() === paymentVal) {
                    paymentMatch = true;
                }

                if (textMatch && statusMatch && paymentMatch) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        };

        if (searchInput) searchInput.addEventListener('input', filterTable);
        if (statusFilter) statusFilter.addEventListener('change', filterTable);
        if (paymentFilter) paymentFilter.addEventListener('change', filterTable);
    }

    // Export Reports to CSV
    window.exportReportToCSV = function (filename) {
        const table = document.querySelector('.premium-table');
        if (!table) return;

        let csv = [];
        const rows = table.querySelectorAll('tr');
        
        for (let i = 0; i < rows.length; i++) {
            // Check if row is visible
            if (rows[i].style.display === 'none') continue;
            
            const cols = rows[i].querySelectorAll('td, th');
            let rowData = [];
            
            for (let j = 0; j < cols.length; j++) {
                // Clean text content
                let cleanData = cols[j].innerText.replace(/(\r\n|\n|\r)/gm, '').trim();
                cleanData = cleanData.replace(/"/g, '""');
                rowData.push('"' + cleanData + '"');
            }
            csv.push(rowData.join(','));
        }

        const csvString = csv.join('\n');
        const csvBlob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        
        if (link.download !== undefined) {
            const url = URL.createObjectURL(csvBlob);
            link.setAttribute('href', url);
            link.setAttribute('download', filename || 'parcelfleet_report.csv');
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }
    };
});
