# Standard library
import logging

# Django imports
from django import template
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.shortcuts import render, redirect

# Local app imports
from ..models import (
    ActivityLog, UserProfile
)

logger = logging.getLogger(__name__)

register = template.Library()

@register.filter
def add_class(field, css_class):
    return field.as_widget(attrs={"class": css_class})


def is_md(user):
    if not user.is_authenticated:
        return False
    return user.is_staff  # Adjust this based on your admin check logic


def access_denied(request):
    return render(request, 'access_denied.html')


def is_cashier(user):
    return user.groups.filter(name='Cashier').exists()


def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                # Log successful login
                ActivityLog.log_activity(
                    user=user,
                    action='login',
                    description=f'User {username} logged in successfully',
                    request=request
                )
                return redirect('homepage')  # Replace with your success URL
            else:
                # Log failed login attempt
                ActivityLog.log_activity(
                    user=None,
                    action='failed_login',
                    description=f'Failed login attempt for username: {username}',
                    success=False,
                    request=request
                )
                messages.error(request, 'Invalid username or password. Please try again.')
        else:
            # Form validation errors (username/password format errors)
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
    else:
        form = AuthenticationForm()

    return render(request, 'loginout/login.html', {'form': form})


def logout_view(request):
    # Log logout before actually logging out
    if request.user.is_authenticated:
        ActivityLog.log_activity(
            user=request.user,
            action='logout',
            description=f'User {request.user.username} logged out',
            request=request
        )
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('login')  # Redirect to login page


@login_required(login_url='login')
def homepage(request):
    return render(request, 'homepage.html')


def user_required_access(access_levels):
    """Decorator to check if user has required access level"""

    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "You need to be logged in.")
                return redirect('login')

            try:
                user_profile = request.user.profile
                if user_profile.access_level not in access_levels:
                    messages.error(request, "You don't have permission to access this page.")
                    return redirect('access_denied')
            except UserProfile.DoesNotExist:
                messages.error(request, "User profile not found.")
                return redirect('login')

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator



def is_superuser(user):
    """Check if user is a superuser"""
    return user.is_superuser

