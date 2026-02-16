from django import template

register = template.Library()

@register.filter
def div(value, arg):
    """Divide value by arg. Returns 0 if invalid or zero division."""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0