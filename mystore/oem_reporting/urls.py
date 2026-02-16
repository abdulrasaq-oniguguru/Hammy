"""
OEM Reporting URL Configuration
Complete URL routing for all API endpoints
"""

from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from . import views

app_name = 'oem_reporting'

urlpatterns = [
    # ===========================
    # FRONTEND REPORTS
    # ===========================
    path('dashboard/', views.dashboard, name='dashboard'),
    path('reports/', views.reports_menu, name='reports_menu'),
    path('reports/bi-dashboard/', views.bi_dashboard, name='bi_dashboard'),
    path('reports/sales/', views.sales_report, name='sales_report'),
    path('reports/inventory/', views.inventory_report, name='inventory_report'),
    path('reports/financial/', views.financial_report, name='financial_report'),
    path('reports/stock-alerts/', views.stock_alerts, name='stock_alerts'),
    path('reports/performance/', views.performance_analytics, name='performance_analytics'),

    # ===========================
    # AUTHENTICATION
    # ===========================
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # ===========================
    # CORE API ENDPOINTS
    # ===========================
    path('', views.api_root, name='api_root'),
    path('status/', views.sync_status, name='sync_status'),

    # ===========================
    # INVENTORY ENDPOINTS
    # ===========================
    path('inventory/summary/', views.inventory_summary, name='inventory_summary'),
    path('inventory/by-category/', views.inventory_by_category, name='inventory_by_category'),

    # ===========================
    # ALERT ENDPOINTS
    # ===========================
    path('alerts/low-stock/', views.low_stock_alerts, name='low_stock_alerts'),

    # ===========================
    # SALES ENDPOINTS
    # ===========================
    path('sales/summary/', views.sales_summary, name='sales_summary'),
    path('sales/top-products/', views.top_selling_products, name='top_selling_products'),

    # ===========================
    # PERFORMANCE ENDPOINTS
    # ===========================
    path('performance/categories/', views.category_performance, name='category_performance'),
    path('performance/shops/', views.shop_performance, name='shop_performance'),

    # ===========================
    # ENHANCED SALES REPORTS
    # ===========================
    path('reports/sales/monthly/', views.sales_report_monthly, name='sales_report_monthly'),
    path('reports/sales/by-day-of-week/', views.sales_by_day_of_week, name='sales_by_day_of_week'),
    path('reports/sales/by-hour/', views.sales_by_hour, name='sales_by_hour'),
    path('reports/sales/product-details/', views.product_sales_detail, name='product_sales_detail'),
    path('reports/sales/trends/', views.sales_trends, name='sales_trends'),
    path('reports/comparisons/', views.comparison_reports, name='comparison_reports'),

    # ===========================
    # ADVANCED SEARCH
    # ===========================
    path('search/', views.advanced_search, name='advanced_search'),

    # ===========================
    # DATA SYNC ENDPOINTS
    # ===========================
    path('sync/products/', views.sync_products, name='sync_products'),
    path('sync/receipts/', views.sync_receipts, name='sync_receipts'),
]
