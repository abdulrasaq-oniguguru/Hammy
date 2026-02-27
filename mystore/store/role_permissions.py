"""
Role/Permission grouping utility for RBAC UI.

Each model exposes THREE simplified permissions:
  1. view + add  → "Can View & Create X"
  2. change      → "Can Edit X"
  3. delete      → "Can Delete X"
"""
from collections import OrderedDict

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

# Models to expose in the Role permission UI.
# Tuple: (app_label, model_name, display_name, category)
PERMISSION_MODEL_CONFIG = [
    ('auth',  'user',                   'User Management',        'Administration'),
    ('store', 'userprofile',            'User Profiles',          'Administration'),
    ('store', 'product',                'Product Management',     'Inventory'),
    ('store', 'sale',                   'Sales',                  'Sales & Finance'),
    ('store', 'receipt',                'Receipts',               'Sales & Finance'),
    ('store', 'payment',                'Payments',               'Sales & Finance'),
    ('store', 'paymentmethod',          'Payment Methods',        'Sales & Finance'),
    ('store', 'customer',               'Customer Management',    'Customers'),
    ('store', 'customerloyaltyaccount', 'Loyalty Accounts',       'Customers'),
    ('store', 'invoice',                'Invoices',               'Sales & Finance'),
    ('store', 'return',                 'Returns',                'Sales & Finance'),
    ('store', 'storecredit',            'Store Credits',          'Sales & Finance'),
    ('store', 'delivery',               'Deliveries',             'Operations'),
    ('store', 'preorder',               'Pre-Orders',             'Operations'),
    ('store', 'taxconfiguration',       'Tax Configuration',      'Configuration'),
    ('store', 'loyaltyconfiguration',   'Loyalty Configuration',  'Configuration'),
    ('store', 'activitylog',            'Activity Logs',          'Administration'),
]

# Role name → UserProfile.access_level mapping (lowercase keys)
ROLE_ACCESS_LEVEL_MAP = {
    'md': 'md',
    'managing director': 'md',
    'manager': 'md',
    'cashier': 'cashier',
    'accountant': 'accountant',
}

# Category display order
CATEGORY_ORDER = ['Administration', 'Inventory', 'Sales & Finance', 'Customers', 'Operations', 'Configuration']


def get_grouped_permissions():
    """
    Returns a list of permission groups ordered by category and model.
    Each group dict has THREE permission slots:

        view_key    / view_label    / view_perms    (view + add)
        edit_key    / edit_label    / edit_perms    (change)
        delete_key  / delete_label  / delete_perms  (delete)
    """
    groups = []
    for app_label, model_name, display_name, category in PERMISSION_MODEL_CONFIG:
        try:
            ct = ContentType.objects.get(app_label=app_label, model=model_name)
        except ContentType.DoesNotExist:
            continue

        perms = Permission.objects.filter(content_type=ct)
        view_perms   = list(perms.filter(codename__in=[f'view_{model_name}', f'add_{model_name}']))
        edit_perms   = list(perms.filter(codename=f'change_{model_name}'))
        delete_perms = list(perms.filter(codename=f'delete_{model_name}'))

        if not view_perms and not edit_perms and not delete_perms:
            continue

        groups.append({
            'display_name': display_name,
            'category':     category,
            # --- view + create ---
            'view_key':    f'view_{app_label}_{model_name}',
            'view_label':  f'Can View & Create {display_name}',
            'view_perms':  view_perms,
            # --- edit ---
            'edit_key':    f'edit_{app_label}_{model_name}',
            'edit_label':  f'Can Edit {display_name}',
            'edit_perms':  edit_perms,
            # --- delete ---
            'delete_key':   f'delete_{app_label}_{model_name}',
            'delete_label': f'Can Delete {display_name}',
            'delete_perms': delete_perms,
        })

    def sort_key(g):
        cat_idx = CATEGORY_ORDER.index(g['category']) if g['category'] in CATEGORY_ORDER else 99
        return (cat_idx, g['display_name'])

    groups.sort(key=sort_key)
    return groups


def get_permissions_from_post(post_data, grouped_perms):
    """
    Given POST data and the grouped permissions list, return a list of
    Permission objects that should be assigned to the role.
    """
    selected = []
    for group in grouped_perms:
        if group['view_key'] in post_data:
            selected.extend(group['view_perms'])
        if group['edit_key'] in post_data:
            selected.extend(group['edit_perms'])
        if group['delete_key'] in post_data:
            selected.extend(group['delete_perms'])
    return selected


def get_checked_keys_for_group(django_group, grouped_perms):
    """
    For an existing Django Group, return the set of checkbox keys that
    should be checked in the simplified permission UI.
    """
    existing_ids = set(django_group.permissions.values_list('id', flat=True))
    checked = set()
    for group in grouped_perms:
        if {p.id for p in group['view_perms']} & existing_ids:
            checked.add(group['view_key'])
        if {p.id for p in group['edit_perms']} & existing_ids:
            checked.add(group['edit_key'])
        if {p.id for p in group['delete_perms']} & existing_ids:
            checked.add(group['delete_key'])
    return checked


def access_level_for_role(role_name):
    """Derive UserProfile.access_level from a role name. Defaults to 'cashier'."""
    return ROLE_ACCESS_LEVEL_MAP.get(role_name.strip().lower(), 'cashier')


def group_permissions_by_category(grouped_perms):
    """Convert flat list into OrderedDict {category: [group, ...]} for templates."""
    result = OrderedDict()
    for g in grouped_perms:
        result.setdefault(g['category'], []).append(g)
    return result
