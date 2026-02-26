"""
Minimal API URL Configuration
Contains only essential report endpoints for the API
"""
from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # =====================================================
    # AUTHENTICATION & ACCESS
    # =====================================================
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('access-denied/', views.access_denied, name='access_denied'),

    # =====================================================
    # REPORT ENDPOINTS (JSON API)
    # =====================================================

    # Sales Report
    # GET /sales_report/
    # Query params: start_date, end_date, payment_method, shop_type, export (pdf/excel)
    path('sales_report/', views.sales_report, name='sales_report'),

    # Financial Report
    # GET /reports/financial/
    # Query params: start_date, end_date
    path('reports/financial/', views.financial_report, name='financial_report'),

    # Inventory Report
    # GET /reports/inventory/
    path('reports/inventory/', views.inventory_report, name='inventory_report'),

    # Tax Report
    # GET /reports/tax/
    # Query params: start_date, end_date
    path('reports/tax/', views.tax_report, name='tax_report'),

    # Reports Dashboard (Summary metrics)
    # GET /reports/dashboard/
    path('reports/dashboard/', views.reports_dashboard, name='reports_dashboard'),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
