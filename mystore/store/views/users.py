# Standard library
import logging

# Django imports
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404

# Local app imports
from ..forms import (
    CustomerForm, CustomUserCreationForm, UserEditForm, UserProfileForm
)
from ..models import (
    Customer, UserProfile, ActivityLog
)
from .auth import is_md, is_cashier, is_superuser, user_required_access

logger = logging.getLogger(__name__)

@login_required
@user_required_access(['md'])
def user_management_dashboard(request):
    """Main user management dashboard - Only MD can access"""
    users = User.objects.select_related('profile').all().order_by('-date_joined')

    # Search functionality
    search_query = request.GET.get('search')
    if search_query:
        users = users.filter(
            username__icontains=search_query
        ) | users.filter(
            first_name__icontains=search_query
        ) | users.filter(
            last_name__icontains=search_query
        )

    # Filter by access level
    access_filter = request.GET.get('access_level')
    if access_filter:
        users = users.filter(profile__access_level=access_filter)

    # Pagination
    paginator = Paginator(users, 10)  # Show 10 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'users': page_obj,
        'search_query': search_query,
        'access_filter': access_filter,
        'access_levels': UserProfile.ACCESS_LEVEL_CHOICES,
        'total_users': users.count(),
    }

    return render(request, 'user_management/dashboard.html', context)


@login_required(login_url='login')
def create_customer(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            # Log customer creation
            ActivityLog.log_activity(
                user=request.user,
                action='customer_create',
                description=f'Created customer: {customer.name} - {customer.phone_number}',
                model_name='Customer',
                object_id=customer.id,
                object_repr=str(customer),
                request=request
            )
            return redirect('customer_list')
    else:
        form = CustomerForm()
    return render(request, 'customer/create_customer.html', {'form': form})


@login_required
@user_required_access(['md'])
def create_user(request):
    """Create new user - Only MD can access"""
    from ..role_permissions import access_level_for_role
    roles = Group.objects.order_by('name')

    if request.method == 'POST':
        user_form = CustomUserCreationForm(request.POST)

        if user_form.is_valid():
            try:
                with transaction.atomic():
                    user = user_form.save()

                    is_admin = request.POST.get('is_admin') == 'on'

                    if is_admin:
                        # Full unrestricted access
                        access_level = 'md'
                        user.is_staff = True
                        user.is_superuser = True
                        user.save(update_fields=['is_staff', 'is_superuser'])
                        assigned_role = None
                    else:
                        # Determine role and derive access_level from it
                        role_id = request.POST.get('role_id')
                        assigned_role = None
                        access_level = 'cashier'

                        if role_id:
                            assigned_role = Group.objects.filter(id=role_id).first()
                            if assigned_role:
                                access_level = access_level_for_role(assigned_role.name)

                        # Assign the selected role (Group)
                        user.groups.clear()
                        if assigned_role:
                            user.groups.add(assigned_role)
                        else:
                            if access_level == 'md':
                                grp, _ = Group.objects.get_or_create(name='MD')
                                user.groups.add(grp)
                            elif access_level == 'cashier':
                                grp, _ = Group.objects.get_or_create(name='Cashier')
                                user.groups.add(grp)
                            elif access_level == 'accountant':
                                grp, _ = Group.objects.get_or_create(name='Accountant')
                                user.groups.add(grp)

                        if access_level == 'md':
                            user.is_staff = True
                            user.save(update_fields=['is_staff'])

                    # Create user profile
                    UserProfile.objects.create(
                        user=user,
                        access_level=access_level,
                        phone_number=user_form.cleaned_data.get('phone_number', ''),
                        created_by=request.user
                    )

                    ActivityLog.log_activity(
                        user=request.user,
                        action='user_create',
                        description=(
                            f'Created user: {user.username} ({user.get_full_name()}) '
                            f'- {"Admin (full access)" if is_admin else f"Role: {assigned_role.name if assigned_role else access_level}"}'
                        ),
                        model_name='User',
                        object_id=user.id,
                        object_repr=user.username,
                        extra_data={'access_level': access_level},
                        request=request
                    )

                    messages.success(request, f'User "{user.username}" created successfully!')
                    return redirect('list_users')
            except Exception as e:
                messages.error(request, f'Error creating user: {str(e)}')
    else:
        user_form = CustomUserCreationForm()

    return render(request, 'user_management/create_user.html', {
        'user_form': user_form,
        'roles': roles,
    })


@login_required
@user_required_access(['md'])
def edit_user(request, user_id):
    """Edit user - Only MD can access"""
    from ..role_permissions import access_level_for_role

    target_user = get_object_or_404(User, id=user_id)

    if target_user.is_superuser and not request.user.is_superuser:
        messages.error(request, "You cannot edit superuser accounts.")
        return redirect('list_users')

    try:
        profile = target_user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=target_user)

    all_roles = Group.objects.order_by('name')
    current_role = target_user.groups.first()

    if request.method == 'POST':
        user_form = UserEditForm(request.POST, instance=target_user)
        profile_form = UserProfileForm(request.POST, instance=profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()

            # Role assignment
            role_id = request.POST.get('role_id')
            assigned_role = Group.objects.filter(id=role_id).first() if role_id else None

            target_user.groups.clear()
            if assigned_role:
                target_user.groups.add(assigned_role)
                access_level = access_level_for_role(assigned_role.name)
                profile.access_level = access_level
                profile.save(update_fields=['access_level'])

                target_user.is_staff = (access_level == 'md')
                target_user.save(update_fields=['is_staff'])

            ActivityLog.log_activity(
                user=request.user,
                action='user_update',
                description=(
                    f'Updated user: {target_user.username} '
                    f'- Role: {assigned_role.name if assigned_role else "none"}'
                ),
                model_name='User',
                object_id=target_user.id,
                object_repr=target_user.username,
                extra_data={'role': assigned_role.name if assigned_role else None,
                            'is_active': target_user.is_active},
                request=request
            )

            messages.success(request, f'User "{target_user.username}" updated successfully!')
            return redirect('list_users')
    else:
        user_form = UserEditForm(instance=target_user)
        profile_form = UserProfileForm(instance=profile)

    return render(request, 'user_management/edit_user.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'user': target_user,
        'all_roles': all_roles,
        'current_role': current_role,
    })


@login_required
@user_required_access(['md'])
def toggle_user_status(request, user_id):
    """Toggle user active status via AJAX"""
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)

        # Don't allow deactivating superuser accounts
        if user.is_superuser:
            return JsonResponse({'success': False, 'message': 'Cannot deactivate superuser accounts.'})

        user.is_active = not user.is_active
        user.save()

        status = "activated" if user.is_active else "deactivated"

        # Log user status change
        ActivityLog.log_activity(
            user=request.user,
            action='user_update',
            description=f'User {user.username} {status}',
            model_name='User',
            object_id=user.id,
            object_repr=user.username,
            extra_data={'is_active': user.is_active, 'action': status},
            request=request
        )

        return JsonResponse({
            'success': True,
            'message': f'User "{user.username}" has been {status}.',
            'is_active': user.is_active
        })

    return JsonResponse({'success': False, 'message': 'Invalid request method.'})


@login_required
@user_required_access(['md'])
def delete_user(request, user_id):
    """Delete user - Only MD can access"""
    user = get_object_or_404(User, id=user_id)

    # Don't allow deleting superuser accounts or self
    if user.is_superuser:
        messages.error(request, "Cannot delete superuser accounts.")
        return redirect('user_management_dashboard')

    if user == request.user:
        messages.error(request, "You cannot delete your own account.")
        return redirect('user_management_dashboard')

    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f'User "{username}" deleted successfully!')
        return redirect('user_management_dashboard')

    return render(request, 'user_management/delete_user.html', {'user': user})


@login_required
@user_required_access(['md'])
def list_users(request):
    """Clean user list showing username, full name, assigned role, status, edit."""
    users = (
        User.objects.select_related('profile')
        .prefetch_related('groups')
        .all()
        .order_by('username')
    )

    search_query = request.GET.get('search', '').strip()
    if search_query:
        users = users.filter(
            username__icontains=search_query
        ) | users.filter(
            first_name__icontains=search_query
        ) | users.filter(
            last_name__icontains=search_query
        )

    return render(request, 'user_management/list_users.html', {
        'users': users,
        'search_query': search_query,
    })


@login_required
def user_profile_view(request):
    """View current user's profile"""
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)

    # Get loyalty information if user is also a customer
    loyalty_info = None
    try:
        # Check if this user has an associated customer account (via email matching)
        customer = Customer.objects.filter(email=request.user.email).first()
        if customer:
            from ..loyalty_utils import get_customer_loyalty_summary
            loyalty_info = get_customer_loyalty_summary(customer)
    except Exception as e:
        logger.error(f"Error fetching loyalty info for user {request.user.username}: {e}")

    return render(request, 'user_management/profile.html', {
        'user': request.user,
        'profile': profile,
        'loyalty_info': loyalty_info
    })
