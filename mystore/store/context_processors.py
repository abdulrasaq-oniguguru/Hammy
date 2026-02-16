# store/context_processors.py
from .models import StoreConfiguration

def user_permissions(request):
    """
    Adds user permissions or access level to the context for all templates.
    """
    if request.user.is_authenticated:
        try:
            # Assuming you have a UserProfile with access_level
            access_level = request.user.profile.access_level
        except:
            access_level = None

        return {
            'user_access_level': access_level,
            # You can add more permissions logic here
        }

    return {
        'user_access_level': None,
    }


def store_config(request):
    """Add store configuration to context - available globally"""
    config = StoreConfiguration.get_active_config()
    return {
        'store_config': config,
        'store_name': config.store_name,
        'store_email': config.email,
        'store_phone': config.phone,
        'currency_symbol': config.currency_symbol,
    }