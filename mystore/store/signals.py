from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
import hashlib
import logging

logger = logging.getLogger(__name__)


@receiver([post_save, post_delete], sender='store.Product')
def invalidate_product_related_cache(sender, instance, **kwargs):
    # Always invalidate global stats and choice caches
    cache_keys = [
        'product_choices_color',
        'product_choices_design',
        'product_choices_category',
        'product_stats',
    ]

    # Invalidate location-specific caches for the product's location
    if hasattr(instance, 'location') and instance.location:
        loc = instance.location
        location_keys = [
            f"location_choices_category_{loc}",
            f"location_choices_size_{loc}",
            f"location_choices_color_{loc}",
            f"location_choices_design_{loc}",
        ]
        cache_keys.extend(location_keys)

    cache.delete_many(cache_keys)

    try:
        from django_redis import get_redis_connection
        r = get_redis_connection("default")
        for key in r.scan_iter("filtered_product_ids_*"):
            r.delete(key)
    except Exception:
        pass


# =====================================
# LOYALTY PROGRAM SIGNALS
# =====================================

@receiver(post_save, sender='store.Receipt')
def process_loyalty_points_for_receipt(sender, instance, created, **kwargs):
    """
    Automatically award loyalty points when a receipt is created or updated

    This signal fires after a receipt is saved and processes loyalty points
    if the receipt has a customer and the loyalty program is active.
    """
    # Only process for receipts with customers
    if not instance.customer:
        return

    # Skip if this is the initial creation (total not yet calculated)
    # or if total is 0 or negative
    if created or instance.total_with_delivery <= 0:
        logger.debug(f"Skipping loyalty processing for receipt {instance.receipt_number}: "
                    f"created={created}, total={instance.total_with_delivery}")
        return

    # Import here to avoid circular imports
    from .loyalty_utils import process_sale_loyalty_points
    from .models import LoyaltyConfiguration

    try:
        # Check if loyalty program is active
        config = LoyaltyConfiguration.get_active_config()
        if not config.is_active:
            return

        # Check if this receipt already has loyalty transactions
        # to avoid duplicate point awards
        if instance.loyalty_transactions.filter(transaction_type='earned').exists():
            logger.debug(f"Receipt {instance.receipt_number} already has loyalty points awarded")
            return

        # Process loyalty points
        result = process_sale_loyalty_points(instance)

        if result:
            logger.info(
                f"Loyalty points processed for receipt {instance.receipt_number}: "
                f"{result['points_earned']} points awarded to {instance.customer.name}"
            )
        else:
            logger.debug(f"No loyalty points processed for receipt {instance.receipt_number}")

    except Exception as e:
        # Log the error but don't raise it to avoid breaking the receipt save
        logger.error(f"Error processing loyalty points for receipt {instance.receipt_number}: {e}")


@receiver(post_save, sender='store.Customer')
def create_loyalty_account_for_customer(sender, instance, created, **kwargs):
    """
    Automatically create a loyalty account when a new customer is created
    Only if they have an email address
    """
    if created and instance.email:
        # Import here to avoid circular imports
        from .loyalty_utils import get_or_create_loyalty_account
        from .models import LoyaltyConfiguration

        try:
            config = LoyaltyConfiguration.get_active_config()
            if config.is_active:
                get_or_create_loyalty_account(instance)
                logger.info(f"Loyalty account created for new customer: {instance.name}")
        except Exception as e:
            logger.error(f"Error creating loyalty account for customer {instance.name}: {e}")