from django.core.cache import cache
from django.db import models  # ← ✅ ADD THIS — needed for F and Sum
from .choices import ProductChoices
from .models import Product

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
        products = Product.objects.filter(quantity__gt=0)
        total_items = products.count()
        total_quantity = products.aggregate(total_qty=models.Sum('quantity'))['total_qty'] or 0
        total_inventory_value = products.aggregate(
            total_value=models.Sum(models.F('price') * models.F('quantity'))
        )['total_value'] or 0.0
        stats = {
            'total_items': total_items,
            'total_quantity': total_quantity,
            'total_inventory_value': total_inventory_value,
        }
        cache.set('product_stats', stats, 300)  # Cache 5 minutes
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