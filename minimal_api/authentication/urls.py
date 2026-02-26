from django.urls import path
from . import views

app_name = 'authentication'

urlpatterns = [
    # Login & Logout
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('verify-2fa/', views.verify_2fa, name='verify_2fa'),

    # 2FA Management (Superuser only)
    path('setup-2fa/', views.setup_2fa, name='setup_2fa'),
    path('enable-2fa/', views.enable_2fa, name='enable_2fa'),
    path('disable-2fa/', views.disable_2fa, name='disable_2fa'),
    path('check-2fa/', views.check_2fa_status, name='check_2fa'),
]
