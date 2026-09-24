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

    // Universal Table Pagination & Live Filter Controller
    function initTablePagination() {
        const tables = document.querySelectorAll('.table-responsive table.premium-table, .table-responsive table.table');
        
        tables.forEach((table, tableIndex) => {
            const tbody = table.querySelector('tbody');
            if (!tbody) return;
            
            // Skip modal tables or explicitly exempt tables
            if (table.closest('.modal-body') || table.classList.contains('no-paginate')) return;
            
            const rawRows = Array.from(tbody.querySelectorAll('tr'));
            const dataRows = rawRows.filter(r => !r.querySelector('td[colspan]'));
            if (dataRows.length === 0) return;

            let currentPage = 1;
            let rowsPerPage = 10;
            let filteredRows = [...dataRows];

            const tableWrapper = table.closest('.table-responsive') || table.parentElement;
            let paginationContainer = tableWrapper.parentElement.querySelector(`.pagination-bar-${tableIndex}`);
            if (!paginationContainer) {
                paginationContainer = document.createElement('div');
                paginationContainer.className = `d-flex flex-wrap align-items-center justify-content-between gap-3 mt-3 pt-3 border-top pagination-bar-${tableIndex} no-print`;
                paginationContainer.style.fontSize = '0.85rem';
                tableWrapper.after(paginationContainer);
            }

            function renderPagination() {
                const totalFiltered = filteredRows.length;
                const totalPages = Math.ceil(totalFiltered / rowsPerPage) || 1;
                if (currentPage > totalPages) currentPage = totalPages;
                if (currentPage < 1) currentPage = 1;

                const startIdx = (currentPage - 1) * rowsPerPage;
                const endIdx = Math.min(startIdx + rowsPerPage, totalFiltered);

                // Hide all data rows
                dataRows.forEach(r => r.style.display = 'none');

                // Show active page slice
                for (let i = startIdx; i < endIdx; i++) {
                    if (filteredRows[i]) filteredRows[i].style.display = '';
                }

                // Handle 0 search results message
                let emptyRow = tbody.querySelector('.pagination-empty-row');
                if (totalFiltered === 0) {
                    if (!emptyRow) {
                        emptyRow = document.createElement('tr');
                        emptyRow.className = 'pagination-empty-row';
                        const colCount = table.querySelectorAll('thead th').length || 7;
                        emptyRow.innerHTML = `<td colspan="${colCount}" class="text-center text-muted py-4"><i class="fas fa-search me-2"></i>No matching records found.</td>`;
                        tbody.appendChild(emptyRow);
                    }
                    emptyRow.style.display = '';
                } else if (emptyRow) {
                    emptyRow.style.display = 'none';
                }

                const showingStart = totalFiltered === 0 ? 0 : startIdx + 1;
                const showingEnd = endIdx;
                const filterNote = totalFiltered !== dataRows.length ? ` <span class="text-muted small">(filtered from ${dataRows.length} total)</span>` : '';

                // Build page buttons HTML
                let buttonsHtml = '';
                
                // Prev button
                buttonsHtml += `<li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
                    <button class="page-link btn-prev" ${currentPage === 1 ? 'disabled' : ''} aria-label="Previous">
                        <i class="fas fa-chevron-left" style="font-size: 0.75rem;"></i>
                    </button>
                </li>`;

                // Smart sliding page buttons
                let startPage = Math.max(1, currentPage - 2);
                let endPage = Math.min(totalPages, currentPage + 2);

                if (startPage > 1) {
                    buttonsHtml += `<li class="page-item"><button class="page-link page-num" data-page="1">1</button></li>`;
                    if (startPage > 2) buttonsHtml += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
                }

                for (let p = startPage; p <= endPage; p++) {
                    buttonsHtml += `<li class="page-item ${p === currentPage ? 'active' : ''}">
                        <button class="page-link page-num" data-page="${p}">${p}</button>
                    </li>`;
                }

                if (endPage < totalPages) {
                    if (endPage < totalPages - 1) buttonsHtml += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
                    buttonsHtml += `<li class="page-item"><button class="page-link page-num" data-page="${totalPages}">${totalPages}</button></li>`;
                }

                // Next button
                buttonsHtml += `<li class="page-item ${currentPage === totalPages ? 'disabled' : ''}">
                    <button class="page-link btn-next" ${currentPage === totalPages ? 'disabled' : ''} aria-label="Next">
                        <i class="fas fa-chevron-right" style="font-size: 0.75rem;"></i>
                    </button>
                </li>`;

                paginationContainer.innerHTML = `
                    <div class="d-flex align-items-center gap-3">
                        <div class="text-muted">
                            Showing <strong class="text-dark">${showingStart}</strong> to <strong class="text-dark">${showingEnd}</strong> of <strong class="text-dark">${totalFiltered}</strong> entries${filterNote}
                        </div>
                        <div class="d-flex align-items-center gap-1">
                            <span class="text-muted small">Show</span>
                            <select class="form-select form-select-sm rows-per-page-select" style="width: 75px; font-size: 0.8rem; padding: 0.2rem 0.5rem;">
                                <option value="10" ${rowsPerPage === 10 ? 'selected' : ''}>10</option>
                                <option value="25" ${rowsPerPage === 25 ? 'selected' : ''}>25</option>
                                <option value="50" ${rowsPerPage === 50 ? 'selected' : ''}>50</option>
                                <option value="100" ${rowsPerPage === 100 ? 'selected' : ''}>100</option>
                            </select>
                        </div>
                    </div>
                    <div>
                        <ul class="pagination pagination-sm mb-0">
                            ${buttonsHtml}
                        </ul>
                    </div>
                `;

                // Wire up button click handlers
                paginationContainer.querySelectorAll('.page-num').forEach(btn => {
                    btn.addEventListener('click', (e) => {
                        e.preventDefault();
                        currentPage = parseInt(btn.getAttribute('data-page'));
                        renderPagination();
                    });
                });

                const prevBtn = paginationContainer.querySelector('.btn-prev');
                if (prevBtn && currentPage > 1) {
                    prevBtn.addEventListener('click', (e) => {
                        e.preventDefault();
                        currentPage--;
                        renderPagination();
                    });
                }

                const nextBtn = paginationContainer.querySelector('.btn-next');
                if (nextBtn && currentPage < totalPages) {
                    nextBtn.addEventListener('click', (e) => {
                        e.preventDefault();
                        currentPage++;
                        renderPagination();
                    });
                }

                const rowsSelect = paginationContainer.querySelector('.rows-per-page-select');
                if (rowsSelect) {
                    rowsSelect.addEventListener('change', (e) => {
                        rowsPerPage = parseInt(e.target.value);
                        currentPage = 1;
                        renderPagination();
                    });
                }
            }

            // Hook live search & filter controls (table-specific or page-level)
            const parentCard = table.closest('.premium-card') || document;
            const searchInput = document.getElementById('tableSearch') || parentCard.querySelector('input[type="text"][placeholder*="Search"]') || document.querySelector('input[type="text"][placeholder*="Search"]');
            const statusFilter = document.getElementById('filterStatus') || parentCard.querySelector('select[id*="Status"]') || document.querySelector('select[id*="Status"]');
            const paymentFilter = document.getElementById('filterPayment') || parentCard.querySelector('select[id*="Payment"]') || document.querySelector('select[id*="Payment"]');

            function applyFilters() {
                const query = searchInput ? searchInput.value.toLowerCase().trim() : '';
                const statusVal = statusFilter ? statusFilter.value.toLowerCase().trim() : '';
                const paymentVal = paymentFilter ? paymentFilter.value.toLowerCase().trim() : '';

                filteredRows = dataRows.filter(row => {
                    let textMatch = true;
                    let statusMatch = true;
                    let paymentMatch = true;

                    if (query) {
                        textMatch = row.innerText.toLowerCase().includes(query);
                    }
                    if (statusVal) {
                        const rowStatus = (row.getAttribute('data-status') || row.innerText).toLowerCase();
                        statusMatch = rowStatus.includes(statusVal);
                    }
                    if (paymentVal) {
                        const rowPayment = (row.getAttribute('data-payment') || row.innerText).toLowerCase();
                        paymentMatch = rowPayment.includes(paymentVal);
                    }

                    return textMatch && statusMatch && paymentMatch;
                });

                currentPage = 1;
                renderPagination();
            }

            if (searchInput) searchInput.addEventListener('input', applyFilters);
            if (statusFilter) statusFilter.addEventListener('change', applyFilters);
            if (paymentFilter) paymentFilter.addEventListener('change', applyFilters);

            // Initial render
            renderPagination();
        });
    }

    // Initialize pagination across all tables
    initTablePagination();

    // Export Reports to CSV
    window.exportReportToCSV = function (filename) {
        const table = document.querySelector('.premium-table') || document.querySelector('table');
        if (!table) return;

        let csv = [];
        const rows = table.querySelectorAll('tr');
        
        for (let i = 0; i < rows.length; i++) {
            // Include header and all data rows (even if paginated)
            if (rows[i].classList.contains('pagination-empty-row')) continue;
            
            const cols = rows[i].querySelectorAll('td, th');
            if (cols.length === 0) continue;
            let rowData = [];
            
            for (let j = 0; j < cols.length; j++) {
                if (cols[j].classList.contains('no-print')) continue;
                let cleanData = cols[j].innerText.replace(/(\r\n|\n|\r)/gm, ' ').trim();
                cleanData = cleanData.replace(/"/g, '""');
                rowData.push('"' + cleanData + '"');
            }
            if (rowData.length > 0) csv.push(rowData.join(','));
        }

        const csvString = csv.join('\n');
        const csvBlob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        
        if (link.download !== undefined) {
            const url = URL.createObjectURL(csvBlob);
            link.setAttribute('href', url);
            link.setAttribute('download', filename || 'parcelfleet_export.csv');
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }
    };
});
