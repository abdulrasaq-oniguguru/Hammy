from django.core.cache import cache
from django.db import models
from .choices import ProductChoices
from .models import Product, WarehouseInventory

def flatten_choices_completely(choices):
    """Completely flatten nested choice structures to simple (value, label) tuples"""
    flattened = []
    try:
        for choice in choices:
            if not choice:  # Skip None or empty choices
                continue

            if isinstance(choice, (tuple, list)) and len(choice) >= 2:
                if isinstance(choice[1], (tuple, list)):
                    for nested_choice in choice[1]:
                        if isinstance(nested_choice, (tuple, list)) and len(nested_choice) >= 2:
                            flattened.append((nested_choice[0], nested_choice[1]))
                        elif isinstance(nested_choice, str):
                            flattened.append((nested_choice, nested_choice))
                else:
                    flattened.append((choice[0], choice[1]))
            elif isinstance(choice, str):
                flattened.append((choice, choice))
    except Exception:
        return []

    seen = set()
    unique_flattened = []
    for item in flattened:
        if item[0] not in seen:
            seen.add(item[0])
            unique_flattened.append(item)

    return unique_flattened


def get_cached_choices(choice_type):
    key = f"product_choices_{choice_type}"
    choices = cache.get(key)
    if choices is None:
        if choice_type == 'color':
            raw = ProductChoices.get_all_colors_with_custom(Product)
            choices = flatten_choices_completely(raw)
        elif choice_type == 'design':
            raw = ProductChoices.get_all_designs_with_custom(Product)
            choices = flatten_choices_completely(raw)
        elif choice_type == 'category':
            raw = ProductChoices.get_all_categories_with_custom(Product)
            choices = flatten_choices_completely(raw)
        cache.set(key, choices, 3600)  # Cache 1 hour
    return choices


def get_product_stats():
    stats = cache.get('product_stats')
    if stats is None:
        # Shop floor: Product table, qty > 0 only
        store_qs = Product.objects.filter(quantity__gt=0)
        # Warehouse: entirely separate WarehouseInventory table, qty > 0 only
        # (Product records are deleted when fully transferred to warehouse,
        #  so Product.filter(shop='WAREHOUSE') is always empty — never use it)
        warehouse_qs = WarehouseInventory.objects.filter(quantity__gt=0)

        # Total item types: deduplicate across both tables.
        # A partial transfer leaves a Product row (remaining floor qty) AND a
        # WarehouseInventory row (warehouse qty) for the same product type at
        # the same time.  Simple addition would count it twice.
        # Fix: collect distinct (brand, category, size, color, design, location)
        # tuples from each table, then take the Python set union — duplicates
        # are eliminated automatically before counting.
        _FIELDS = ('brand', 'category', 'size', 'color', 'design', 'location')
        store_types = set(store_qs.values_list(*_FIELDS).distinct())
        warehouse_types = set(warehouse_qs.values_list(*_FIELDS).distinct())
        total_items = len(store_types | warehouse_types)

        store_agg = store_qs.aggregate(
            qty=models.Sum('quantity'),
            value=models.Sum(models.F('price') * models.F('quantity')),
        )
        warehouse_agg = warehouse_qs.aggregate(
            qty=models.Sum('quantity'),
            value=models.Sum(models.F('price') * models.F('quantity')),
        )

        store_quantity = store_agg['qty'] or 0
        warehouse_quantity = warehouse_agg['qty'] or 0
        store_value = store_agg['value'] or 0
        warehouse_value = warehouse_agg['value'] or 0

        stats = {
            'total_items': total_items,
            'total_quantity': store_quantity + warehouse_quantity,
            'store_quantity': store_quantity,
            'warehouse_quantity': warehouse_quantity,
            'total_inventory_value': store_value + warehouse_value,
            'store_inventory_value': store_value,
            'warehouse_inventory_value': warehouse_value,
        }
        cache.set('product_stats', stats, 60)  # Cache 1 minute for accuracy
    return stats


def get_location_cached_choices(field_name, location):
    """
    Cache unique values for a field filtered by location.
    field_name: 'category', 'size', 'color', 'design'
    """
    cache_key = f"location_choices_{field_name}_{location}"
    choices = cache.get(cache_key)

    if choices is None:
        # Use iexact for case-insensitive distinct — if your DB supports it
        # Otherwise, just use distinct()
        if field_name in ['color', 'design', 'category', 'size']:
            # Get distinct values, excluding blanks
            values = Product.objects.filter(
                location=location
            ).exclude(
                **{f"{field_name}__isnull": True}
            ).exclude(
                **{field_name: ''}
            ).values_list(field_name, flat=True).distinct().order_by(field_name)

            choices = [(v, v) for v in values if v]
        else:
            choices = []

        cache.set(cache_key, choices, 3600)  # Cache 1 hour

    return choices