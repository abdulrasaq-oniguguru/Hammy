"""
Custom template filters for the store app
"""
import json
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name='parse_json')
def parse_json(value):
    """
    Parse a JSON string into a Python dictionary

    Usage: {% with data=json_string|parse_json %}
    """
    if not value:
        return {}

    if isinstance(value, dict):
        return value

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
