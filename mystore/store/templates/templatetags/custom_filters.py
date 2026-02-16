# store/templatetags/custom_filters.py

from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Get value from dictionary by key in Django templates.
    Usage: {{ mydict|get_item:keyvar }}
    """
    if dictionary is None:
        return None
    return dictionary.get(str(key))  # Convert key to string if needed