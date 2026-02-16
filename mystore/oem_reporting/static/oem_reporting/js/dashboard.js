/**
 * OEM Reporting Dashboard JavaScript
 * Handles all API calls, data visualization, and interactivity
 */

// API Configuration
const API_BASE_URL = '/api/oem';
let authToken = '';
let salesTrendChart = null;
let categoryChart = null;

// Initialize dashboard
async function loadDashboardData() {
    try {
        showLoading(true);

        // Load all dashboard data in parallel
        await Promise.all([
            loadInventorySummary(),
            loadSalesSummary(),
            loadTopProducts(),
            loadStockAlerts(),
            loadSalesTrend(),
            loadCategoryDistribution(),
            loadSyncStatus(),
            loadCategories()
        ]);

        showLoading(false);
    } catch (error) {
        console.error('Error loading dashboard:', error);
        showError('Failed to load dashboard data. Please refresh the page.');
    }
}

// Load inventory summary
async function loadInventorySummary() {
    try {
        const filters = getFilters();
        const url = new URL(`${API_BASE_URL}/inventory/summary/`, window.location.origin);
        if (filters.location) url.searchParams.append('location', filters.location);

        const response = await fetchAPI(url);

        // Update stat cards
        document.getElementById('totalProducts').textContent = response.total_products || 0;
        document.getElementById('lowStockCount').textContent = response.low_stock_count || 0;
        document.getElementById('outOfStock').textContent = response.out_of_stock_count || 0;
    } catch (error) {
        console.error('Error loading inventory summary:', error);
    }
}

// Load sales summary
async function loadSalesSummary() {
    try {
        const filters = getFilters();
        const url = new URL(`${API_BASE_URL}/sales/summary/`, window.location.origin);
        if (filters.period) url.searchParams.append('days', filters.period);
        if (filters.location) url.searchParams.append('location', filters.location);

        const response = await fetchAPI(url);

        // Update revenue stat card
        const totalRevenue = response.total_revenue || 0;
        document.getElementById('totalRevenue').textContent =
            '₦' + totalRevenue.toLocaleString('en-NG', { maximumFractionDigits: 0 });
    } catch (error) {
        console.error('Error loading sales summary:', error);
    }
}

// Load top selling products
async function loadTopProducts() {
    try {
        const filters = getFilters();
        const url = new URL(`${API_BASE_URL}/sales/top-products/`, window.location.origin);
        if (filters.period) url.searchParams.append('days', filters.period);
        if (filters.location) url.searchParams.append('location', filters.location);
        url.searchParams.append('limit', '10');

        const response = await fetchAPI(url);
        const tbody = document.getElementById('topProductsTable');

        if (response.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center">No data available</td></tr>';
            return;
        }

        tbody.innerHTML = response.map((product, index) => `
            <tr>
                <td><strong>#${index + 1}</strong></td>
                <td>${product.brand || 'N/A'}</td>
                <td>${product.category || 'N/A'}</td>
                <td><strong>${product.total_units_sold || 0}</strong></td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Error loading top products:', error);
    }
}

// Load stock alerts
async function loadStockAlerts() {
    try {
        const filters = getFilters();
        const url = new URL(`${API_BASE_URL}/alerts/low-stock/`, window.location.origin);
        if (filters.location) url.searchParams.append('location', filters.location);
        url.searchParams.append('limit', '10');

        const response = await fetchAPI(url);
        const tbody = document.getElementById('alertsTable');

        if (response.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center">No alerts at this time</td></tr>';
            return;
        }

        tbody.innerHTML = response.map(alert => `
            <tr>
                <td>${alert.brand || 'N/A'}</td>
                <td>${alert.location || 'N/A'}</td>
                <td>${alert.quantity_available || 0}</td>
                <td>
                    <span class="alert-badge ${alert.severity === 'critical' ? 'critical' : 'low'}">
                        ${alert.severity === 'critical' ? 'Critical' : 'Low Stock'}
                    </span>
                </td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Error loading stock alerts:', error);
    }
}

// Load sales trend chart
async function loadSalesTrend() {
    try {
        const filters = getFilters();
        const url = new URL(`${API_BASE_URL}/reports/sales/trends/`, window.location.origin);
        if (filters.period) url.searchParams.append('days', filters.period);
        if (filters.location) url.searchParams.append('location', filters.location);

        const response = await fetchAPI(url);

        // Prepare chart data
        const labels = response.map(item => item.date || item.period);
        const revenueData = response.map(item => item.total_revenue || 0);
        const unitsData = response.map(item => item.total_units_sold || 0);

        // Destroy existing chart if it exists
        if (salesTrendChart) {
            salesTrendChart.destroy();
        }

        // Create new chart
        const ctx = document.getElementById('salesTrendChart').getContext('2d');
        salesTrendChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Revenue (₦)',
                        data: revenueData,
                        borderColor: '#4e73df',
                        backgroundColor: 'rgba(78, 115, 223, 0.1)',
                        tension: 0.4,
                        fill: true,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Units Sold',
                        data: unitsData,
                        borderColor: '#1cc88a',
                        backgroundColor: 'rgba(28, 200, 138, 0.1)',
                        tension: 0.4,
                        fill: true,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                if (context.parsed.y !== null) {
                                    if (context.datasetIndex === 0) {
                                        label += '₦' + context.parsed.y.toLocaleString('en-NG');
                                    } else {
                                        label += context.parsed.y.toLocaleString();
                                    }
                                }
                                return label;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        ticks: {
                            callback: function(value) {
                                return '₦' + value.toLocaleString('en-NG');
                            }
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        grid: {
                            drawOnChartArea: false
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error loading sales trend:', error);
    }
}

// Load category distribution chart
async function loadCategoryDistribution() {
    try {
        const filters = getFilters();
        const url = new URL(`${API_BASE_URL}/inventory/by-category/`, window.location.origin);
        if (filters.location) url.searchParams.append('location', filters.location);

        const response = await fetchAPI(url);

        // Prepare chart data
        const labels = response.map(item => item.category || 'Unknown');
        const data = response.map(item => item.total_quantity || 0);

        // Destroy existing chart if it exists
        if (categoryChart) {
            categoryChart.destroy();
        }

        // Create new chart
        const ctx = document.getElementById('categoryChart').getContext('2d');
        categoryChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: [
                        '#4e73df',
                        '#1cc88a',
                        '#36b9cc',
                        '#f6c23e',
                        '#e74a3b',
                        '#858796',
                        '#5a5c69'
                    ],
                    borderWidth: 2,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                let label = context.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                const value = context.parsed || 0;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = ((value / total) * 100).toFixed(1);
                                label += value.toLocaleString() + ' (' + percentage + '%)';
                                return label;
                            }
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error loading category distribution:', error);
    }
}

// Load sync status
async function loadSyncStatus() {
    try {
        const response = await fetchAPI(`${API_BASE_URL}/status/`);

        const lastSyncTime = document.getElementById('lastSyncTime');
        const syncStatus = document.getElementById('syncStatus');

        if (response.last_sync) {
            const syncDate = new Date(response.last_sync);
            lastSyncTime.textContent = `Last synced: ${syncDate.toLocaleString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            })}`;
        } else {
            lastSyncTime.textContent = 'No sync data available';
        }

        if (response.status === 'success') {
            syncStatus.className = 'sync-status success';
            syncStatus.innerHTML = '<i class="fas fa-check-circle me-1"></i> Synced';
        } else {
            syncStatus.className = 'sync-status';
            syncStatus.innerHTML = '<i class="fas fa-exclamation-circle me-1"></i> ' + response.status;
        }
    } catch (error) {
        console.error('Error loading sync status:', error);
        document.getElementById('syncStatus').innerHTML =
            '<i class="fas fa-times-circle me-1"></i> Error';
    }
}

// Load categories for filter dropdown
async function loadCategories() {
    try {
        const response = await fetchAPI(`${API_BASE_URL}/inventory/by-category/`);
        const categoryFilter = document.getElementById('categoryFilter');

        // Get unique categories
        const categories = [...new Set(response.map(item => item.category))].filter(Boolean);

        // Populate dropdown
        categories.forEach(category => {
            const option = document.createElement('option');
            option.value = category;
            option.textContent = category;
            categoryFilter.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading categories:', error);
    }
}

// Get current filter values
function getFilters() {
    return {
        location: document.getElementById('locationFilter')?.value || '',
        period: document.getElementById('periodFilter')?.value || '30',
        category: document.getElementById('categoryFilter')?.value || ''
    };
}

// Apply filters and reload data
function applyFilters() {
    loadDashboardData();
}

// Refresh all data
function refreshData() {
    const button = event.target.closest('button');
    const icon = button.querySelector('.fa-sync-alt');

    // Add spin animation
    icon.classList.add('fa-spin');

    loadDashboardData().finally(() => {
        // Remove spin animation after 1 second
        setTimeout(() => icon.classList.remove('fa-spin'), 1000);
    });
}

// Export report as CSV
async function exportReport() {
    try {
        const filters = getFilters();
        const url = new URL(`${API_BASE_URL}/reports/sales/product-details/`, window.location.origin);
        if (filters.period) url.searchParams.append('days', filters.period);
        if (filters.location) url.searchParams.append('location', filters.location);
        if (filters.category) url.searchParams.append('category', filters.category);
        url.searchParams.append('format', 'csv');

        // Fetch CSV data
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (!response.ok) throw new Error('Export failed');

        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = `oem_report_${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(downloadUrl);

        showSuccess('Report exported successfully!');
    } catch (error) {
        console.error('Error exporting report:', error);
        showError('Failed to export report. Please try again.');
    }
}

// Fetch API with authentication
async function fetchAPI(url) {
    try {
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            }
        });

        if (response.status === 401) {
            showError('Session expired. Please refresh the page and log in again.');
            throw new Error('Unauthorized');
        }

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('API fetch error:', error);
        throw error;
    }
}

// Show loading state
function showLoading(show) {
    // Could implement loading overlay if needed
    if (show) {
        console.log('Loading...');
    }
}

// Show error message
function showError(message) {
    // Create toast notification
    const toast = document.createElement('div');
    toast.className = 'alert alert-danger position-fixed top-0 end-0 m-3';
    toast.style.zIndex = '9999';
    toast.innerHTML = `
        <i class="fas fa-exclamation-circle me-2"></i>${message}
        <button type="button" class="btn-close" onclick="this.parentElement.remove()"></button>
    `;
    document.body.appendChild(toast);

    setTimeout(() => toast.remove(), 5000);
}

// Show success message
function showSuccess(message) {
    const toast = document.createElement('div');
    toast.className = 'alert alert-success position-fixed top-0 end-0 m-3';
    toast.style.zIndex = '9999';
    toast.innerHTML = `
        <i class="fas fa-check-circle me-2"></i>${message}
        <button type="button" class="btn-close" onclick="this.parentElement.remove()"></button>
    `;
    document.body.appendChild(toast);

    setTimeout(() => toast.remove(), 3000);
}

// Get auth token from page (set by Django template)
function initAuthToken() {
    // This will be set by Django template
    const tokenElement = document.getElementById('authToken');
    if (tokenElement) {
        authToken = tokenElement.value;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initAuthToken();
    loadDashboardData();

    // Auto-refresh every 5 minutes
    setInterval(loadDashboardData, 5 * 60 * 1000);
});
