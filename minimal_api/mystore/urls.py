"""
URL configuration for mystore project.

Minimal API - All endpoints under /api/oem/
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    # Redirect root to Reports Menu (Main Dashboard)
    path('', RedirectView.as_view(url='/api/oem/reports/', permanent=False)),

    # Admin interface (Secured URL - not using default 'admin/')
    # Change this to a random secure URL for production
    path('secure-panel-oem-2024/', admin.site.urls),

    # Authentication API (2FA enabled)
    # Endpoints: /api/auth/login/, /api/auth/register/, /api/auth/setup-2fa/, etc.
    path('api/auth/', include('authentication.urls')),

    # OEM Reporting - HTML pages and API endpoints
    # HTML: /api/oem/dashboard/, /api/oem/reports/
    # API:  /api/oem/sales/summary/, /api/oem/inventory/summary/
    path('api/oem/', include('oem_reporting.urls')),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
