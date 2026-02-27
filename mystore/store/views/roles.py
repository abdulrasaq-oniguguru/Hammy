# Standard library
import logging

# Django imports
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404

# Local app imports
from ..models import ActivityLog
from ..role_permissions import (
    get_grouped_permissions,
    get_permissions_from_post,
    get_checked_keys_for_group,
    group_permissions_by_category,
)
from .auth import user_required_access

logger = logging.getLogger(__name__)

# Role names that are tied to system routing — prevent accidental deletion
SYSTEM_ROLE_NAMES = {'MD', 'Cashier', 'Accountant'}


@login_required
@user_required_access(['md'])
def list_roles(request):
    """List all Roles (Django Groups)."""
    roles = Group.objects.prefetch_related('permissions').order_by('name')
    return render(request, 'roles/list_roles.html', {'roles': roles})


@login_required
@user_required_access(['md'])
def create_role(request):
    """Create a new Role and assign simplified permissions."""
    grouped_perms = get_grouped_permissions()
    categories = group_permissions_by_category(grouped_perms)

    if request.method == 'POST':
        role_name = request.POST.get('role_name', '').strip()

        if not role_name:
            messages.error(request, 'Role name is required.')
            return render(request, 'roles/create_role.html', {
                'categories': categories,
                'grouped_perms': grouped_perms,
                'post_data': request.POST,
            })

        if Group.objects.filter(name__iexact=role_name).exists():
            messages.error(request, f'A role named "{role_name}" already exists.')
            return render(request, 'roles/create_role.html', {
                'categories': categories,
                'grouped_perms': grouped_perms,
                'role_name': role_name,
                'post_data': request.POST,
            })

        with transaction.atomic():
            role = Group.objects.create(name=role_name)
            selected_perms = get_permissions_from_post(request.POST, grouped_perms)
            role.permissions.set(selected_perms)

        ActivityLog.log_activity(
            user=request.user,
            action='role_create',
            description=f'Created role: {role_name} with {len(selected_perms)} permissions',
            model_name='Group',
            object_id=role.id,
            object_repr=role_name,
            request=request,
        )

        messages.success(request, f'Role "{role_name}" created successfully!')
        return redirect('list_roles')

    return render(request, 'roles/create_role.html', {
        'categories': categories,
        'grouped_perms': grouped_perms,
        'post_data': {},
    })


@login_required
@user_required_access(['md'])
def edit_role(request, role_id):
    """Edit an existing Role's name and permissions."""
    role = get_object_or_404(Group, id=role_id)
    grouped_perms = get_grouped_permissions()
    categories = group_permissions_by_category(grouped_perms)
    checked_keys = get_checked_keys_for_group(role, grouped_perms)

    if request.method == 'POST':
        role_name = request.POST.get('role_name', '').strip()

        if not role_name:
            messages.error(request, 'Role name is required.')
            return render(request, 'roles/edit_role.html', {
                'role': role,
                'categories': categories,
                'grouped_perms': grouped_perms,
                'checked_keys': set(request.POST.keys()),
            })

        name_conflict = Group.objects.filter(name__iexact=role_name).exclude(pk=role.pk).exists()
        if name_conflict:
            messages.error(request, f'A role named "{role_name}" already exists.')
            return render(request, 'roles/edit_role.html', {
                'role': role,
                'categories': categories,
                'grouped_perms': grouped_perms,
                'checked_keys': set(request.POST.keys()),
            })

        with transaction.atomic():
            role.name = role_name
            role.save()
            selected_perms = get_permissions_from_post(request.POST, grouped_perms)
            role.permissions.set(selected_perms)

        ActivityLog.log_activity(
            user=request.user,
            action='role_update',
            description=f'Updated role: {role_name} with {len(selected_perms)} permissions',
            model_name='Group',
            object_id=role.id,
            object_repr=role_name,
            request=request,
        )

        messages.success(request, f'Role "{role_name}" updated successfully!')
        return redirect('list_roles')

    return render(request, 'roles/edit_role.html', {
        'role': role,
        'categories': categories,
        'grouped_perms': grouped_perms,
        'checked_keys': checked_keys,
    })


@login_required
@user_required_access(['md'])
def delete_role(request, role_id):
    """Delete a Role (Groups). System roles are protected."""
    role = get_object_or_404(Group, id=role_id)

    if role.name in SYSTEM_ROLE_NAMES:
        messages.error(request, f'"{role.name}" is a system role and cannot be deleted.')
        return redirect('list_roles')

    if request.method == 'POST':
        role_name = role.name
        role.delete()

        ActivityLog.log_activity(
            user=request.user,
            action='role_delete',
            description=f'Deleted role: {role_name}',
            model_name='Group',
            object_id=role_id,
            object_repr=role_name,
            request=request,
        )

        messages.success(request, f'Role "{role_name}" deleted successfully.')
        return redirect('list_roles')

    user_count = role.user_set.count()
    return render(request, 'roles/delete_role.html', {
        'role': role,
        'user_count': user_count,
    })
