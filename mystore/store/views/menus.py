# Standard library
import logging

# Django imports
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

# Local app imports
from .auth import is_md, is_cashier, is_superuser, user_required_access

logger = logging.getLogger(__name__)


@login_required(login_url='login')
def reports_menu(request):
    """Reports menu page showing all available reports"""
    return render(request, 'reports/reports_menu.html')


@login_required(login_url='login')
def user_menu(request):
    """User management menu page"""
    return render(request, 'users/user_menu.html')


@login_required(login_url='login')
def tools_menu(request):
    """Tools and utilities menu page"""
    return render(request, 'tools/tools_menu.html')


@login_required(login_url='login')
def inventory_menu(request):
    """Inventory management menu page"""
    return render(request, 'inventory/inventory_menu.html')
