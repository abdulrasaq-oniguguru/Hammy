from django.shortcuts import redirect
from django.contrib import messages
from .models import UserProfile
import time
from django.utils.deprecation import MiddlewareMixin
from django.db import connection
import logging

# Set up logging
logger = logging.getLogger(__name__)


class AccessControlMiddleware:
    """
    Middleware to handle access control based on user access levels
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Process request before view
        if request.user.is_authenticated:
            try:
                profile = request.user.profile
                # Add profile to request for easy access in templates
                request.user_profile = profile

                # Check if user profile is active
                if not profile.is_active_staff and not request.user.is_superuser:
                    if request.path != '/logout/':
                        messages.error(request, "Your account has been deactivated. Please contact an administrator.")
                        return redirect('login')

            except UserProfile.DoesNotExist:
                # Create a default profile for users without one
                UserProfile.objects.create(
                    user=request.user,
                    access_level='cashier' if not request.user.is_superuser else 'md'
                )
                request.user_profile = request.user.profile

        response = self.get_response(request)
        return response


def user_permissions(request):
    context = {}

    if hasattr(request, 'profile'):  # 👈 Use the profile from middleware
        profile = request.profile
        context.update({
            'user_can_manage_users': profile.can_manage_users(),
            'user_can_access_reports': profile.can_access_reports(),
            'user_can_process_sales': profile.can_process_sales(),
            'user_can_manage_inventory': profile.can_manage_inventory(),
            'user_access_level': profile.access_level,
            'user_access_level_display': profile.get_access_level_display(),
        })
    elif request.user.is_authenticated:
        # Fallback if middleware didn't run (shouldn't happen)
        context.update({
            'user_can_manage_users': False,
            'user_can_access_reports': False,
            'user_can_process_sales': True,
            'user_can_manage_inventory': False,
            'user_access_level': 'unknown',
            'user_access_level_display': 'Unknown',
        })

    return context


class PerformanceMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.start_time = time.time()
        request.start_queries = len(connection.queries)  # 👈 Track DB queries

    def process_response(self, request, response):
        total_time = time.time() - request.start_time
        query_count = len(connection.queries) - getattr(request, 'start_queries', 0)

        if total_time > 2:
            logger.warning(
                f"Slow Request: {request.method} {request.path} | "
                f"Time: {total_time:.2f}s | Queries: {query_count} | "
                f"User: {getattr(request.user, 'username', 'Anonymous')}"
            )
        return response
