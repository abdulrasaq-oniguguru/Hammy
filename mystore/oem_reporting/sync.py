"""
OEM/Inventory Data Sync Module
Exports filtered, aggregated data from main system to separate online database.

SECURITY DESIGN:
- Runs locally on your machine (no remote access to main DB)
- One-way data flow (export only, no write-back)
- Only exports non-sensitive aggregated data
- Main system stays 100% offline

USAGE:
1. Configure DATABASE_ROUTERS in settings.py
2. Run: python manage.py sync_oem_data
3. Or schedule with Celery Beat every 15-30 minutes
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Count, Avg, Q

# Import from main system
from store.models import Product, Sale, Receipt

# Import sync models from this app
from .models import (
    SyncMetadata,
    InventorySnapshot,
    SalesSummaryDaily,
    TopSellingProduct,
    LowStockAlert,
    CategoryPerformance,
    ShopPerformance,
)

logger = logging.getLogger(__name__)


class OEMDataSyncManager:
    """
    Manages syncing data from main system to online reporting database
    """

    def __init__(self, low_stock_threshold=10, critical_stock_threshold=3):
        """
        Initialize sync manager

        Args:
            low_stock_threshold: Quantity below which item is flagged as low stock
            critical_stock_threshold: Quantity below which item is flagged as critical
        """
        self.low_stock_threshold = low_stock_threshold
        self.critical_stock_threshold = critical_stock_threshold
        self.sync_results = {
            'inventory': 0,
            'sales_daily': 0,
            'top_products': 0,
            'alerts': 0,
            'category_perf': 0,
            'shop_perf': 0,
        }

    def sync_all(self):
        """
        Run complete sync of all data types

        Returns:
            dict: Summary of sync results
        """
        logger.info("🔄 Starting OEM data sync...")
        start_time = timezone.now()

        try:
            # Sync different data types
            self.sync_inventory_snapshot()
            self.sync_daily_sales_summary()
            self.sync_top_selling_products()
            self.sync_low_stock_alerts()
            self.sync_category_performance()
            self.sync_shop_performance()

            # Update sync metadata
            self._update_sync_metadata('full_sync', 'success', sum(self.sync_results.values()))

            duration = (timezone.now() - start_time).total_seconds()
            logger.info(f"✅ Sync completed successfully in {duration:.2f}s")
            logger.info(f"   Records synced: {self.sync_results}")

            return {
                'success': True,
                'duration_seconds': duration,
                'records_synced': self.sync_results,
                'timestamp': timezone.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Sync failed: {e}", exc_info=True)
            self._update_sync_metadata('full_sync', 'failed', 0, str(e))
            return {
                'success': False,
                'error': str(e),
                'timestamp': timezone.now().isoformat()
            }

    def sync_inventory_snapshot(self):
        """
        Sync current inventory levels
        Creates/updates InventorySnapshot records
        """
        logger.info("📦 Syncing inventory snapshot...")

        try:
            products = Product.objects.all()
            synced_count = 0

            for product in products:
                # Determine stock status
                is_out_of_stock = product.quantity == 0
                is_low_stock = (
                    product.quantity > 0 and
                    product.quantity <= self.low_stock_threshold
                )

                # Update or create snapshot record
                InventorySnapshot.objects.using('oem_sync_db').update_or_create(
                    product_id=product.id,
                    defaults={
                        'brand': product.brand,
                        'category': product.category,
                        'size': product.size,
                        'color': product.color or '',
                        'design': product.design or '',
                        'quantity_available': product.quantity,
                        'location': product.location,
                        'shop': product.shop,
                        'is_low_stock': is_low_stock,
                        'is_out_of_stock': is_out_of_stock,
                        'data_source_timestamp': timezone.now(),
                    }
                )
                synced_count += 1

            self.sync_results['inventory'] = synced_count
            logger.info(f"   ✓ Synced {synced_count} inventory records")

        except Exception as e:
            logger.error(f"   ✗ Inventory sync failed: {e}")
            raise

    def sync_daily_sales_summary(self, days_back=30):
        """
        Sync aggregated daily sales statistics

        Args:
            days_back: Number of days of history to sync
        """
        logger.info("📊 Syncing daily sales summaries...")

        try:
            # Get sales for last N days
            start_date = (timezone.now() - timedelta(days=days_back)).date()
            sales = Sale.objects.filter(sale_date__gte=start_date)

            synced_count = 0

            # Get unique combinations of date, category, shop, location
            dates = sales.dates('sale_date', 'day')

            for date in dates:
                day_sales = sales.filter(sale_date__date=date)

                # Get unique categories, shops, locations for this date
                categories = day_sales.values_list('product__category', flat=True).distinct()
                shops = day_sales.values_list('product__shop', flat=True).distinct()
                locations = day_sales.values_list('product__location', flat=True).distinct()

                # Create summaries for each combination
                for category in categories:
                    for shop in shops:
                        for location in locations:
                            filtered_sales = day_sales.filter(
                                product__category=category,
                                product__shop=shop,
                                product__location=location
                            )

                            if filtered_sales.exists():
                                # Calculate aggregates
                                total_units = filtered_sales.aggregate(
                                    total=Sum('quantity')
                                )['total'] or 0

                                total_transactions = filtered_sales.count()

                                total_revenue = filtered_sales.aggregate(
                                    revenue=Sum('total_price')
                                )['revenue'] or Decimal('0.00')

                                # Update or create summary
                                SalesSummaryDaily.objects.using('oem_sync_db').update_or_create(
                                    summary_date=date,
                                    category=category,
                                    shop=shop,
                                    location=location,
                                    defaults={
                                        'total_units_sold': total_units,
                                        'total_transactions': total_transactions,
                                        'total_revenue': total_revenue,
                                    }
                                )
                                synced_count += 1

            self.sync_results['sales_daily'] = synced_count
            logger.info(f"   ✓ Synced {synced_count} daily summary records")

        except Exception as e:
            logger.error(f"   ✗ Sales summary sync failed: {e}")
            raise

    def sync_top_selling_products(self, period_days=7, top_n=50):
        """
        Sync top selling products

        Args:
            period_days: Number of days to analyze
            top_n: Number of top products to sync
        """
        logger.info("🏆 Syncing top selling products...")

        try:
            # Calculate period
            period_end = timezone.now().date()
            period_start = period_end - timedelta(days=period_days)

            # Get sales in period
            sales = Sale.objects.filter(
                sale_date__date__gte=period_start,
                sale_date__date__lte=period_end
            )

            # Aggregate by product
            top_products = sales.values(
                'product__brand',
                'product__category',
                'product__location'
            ).annotate(
                total_units=Sum('quantity')
            ).order_by('-total_units')[:top_n]

            # Clear existing top products for this period
            TopSellingProduct.objects.using('oem_sync_db').filter(
                period_start=period_start,
                period_end=period_end,
                period_type='weekly'
            ).delete()

            # Create new top products
            synced_count = 0
            for rank, product in enumerate(top_products, start=1):
                TopSellingProduct.objects.using('oem_sync_db').create(
                    period_type='weekly',
                    period_start=period_start,
                    period_end=period_end,
                    brand=product['product__brand'],
                    category=product['product__category'],
                    location=product['product__location'],
                    units_sold=product['total_units'],
                    rank=rank
                )
                synced_count += 1

            self.sync_results['top_products'] = synced_count
            logger.info(f"   ✓ Synced {synced_count} top products")

        except Exception as e:
            logger.error(f"   ✗ Top products sync failed: {e}")
            raise

    def sync_low_stock_alerts(self):
        """
        Sync low stock alerts
        """
        logger.info("⚠️  Syncing low stock alerts...")

        try:
            # Get low stock products
            low_stock_products = Product.objects.filter(
                quantity__lte=self.low_stock_threshold
            )

            synced_count = 0

            for product in low_stock_products:
                # Determine alert level
                if product.quantity == 0:
                    alert_level = 'out'
                elif product.quantity <= self.critical_stock_threshold:
                    alert_level = 'critical'
                else:
                    alert_level = 'low'

                # Check if alert already exists
                existing_alert = LowStockAlert.objects.using('oem_sync_db').filter(
                    product_id=product.id,
                    is_resolved=False
                ).first()

                if existing_alert:
                    # Update existing alert
                    existing_alert.current_quantity = product.quantity
                    existing_alert.alert_level = alert_level
                    existing_alert.save(using='oem_sync_db')
                else:
                    # Create new alert
                    LowStockAlert.objects.using('oem_sync_db').create(
                        product_id=product.id,
                        brand=product.brand,
                        category=product.category,
                        size=product.size,
                        color=product.color or '',
                        location=product.location,
                        current_quantity=product.quantity,
                        alert_level=alert_level,
                        is_resolved=False
                    )

                synced_count += 1

            # Resolve alerts for products that are back in stock
            restocked_products = Product.objects.filter(
                quantity__gt=self.low_stock_threshold
            )

            for product in restocked_products:
                LowStockAlert.objects.using('oem_sync_db').filter(
                    product_id=product.id,
                    is_resolved=False
                ).update(
                    is_resolved=True,
                    resolved_date=timezone.now()
                )

            self.sync_results['alerts'] = synced_count
            logger.info(f"   ✓ Synced {synced_count} stock alerts")

        except Exception as e:
            logger.error(f"   ✗ Stock alerts sync failed: {e}")
            raise

    def sync_category_performance(self, period_days=30):
        """
        Sync category performance metrics

        Args:
            period_days: Number of days to analyze
        """
        logger.info("📈 Syncing category performance...")

        try:
            period_end = timezone.now().date()
            period_start = period_end - timedelta(days=period_days)

            # Get unique categories
            categories = Product.objects.values_list('category', flat=True).distinct()

            synced_count = 0

            for category in categories:
                for location in ['ABUJA', 'LAGOS']:
                    # Get sales for this category/location in period
                    sales = Sale.objects.filter(
                        sale_date__date__gte=period_start,
                        sale_date__date__lte=period_end,
                        product__category=category,
                        product__location=location
                    )

                    total_units = sales.aggregate(total=Sum('quantity'))['total'] or 0
                    total_revenue = sales.aggregate(revenue=Sum('total_price'))['revenue'] or Decimal('0.00')

                    # Get product count and average stock
                    products = Product.objects.filter(
                        category=category,
                        location=location
                    )

                    product_count = products.count()
                    avg_stock = products.aggregate(avg=Avg('quantity'))['avg'] or Decimal('0.00')

                    # Update or create performance record
                    CategoryPerformance.objects.using('oem_sync_db').update_or_create(
                        period_start=period_start,
                        period_end=period_end,
                        category=category,
                        location=location,
                        defaults={
                            'total_units_sold': total_units,
                            'total_products_in_category': product_count,
                            'average_stock_level': avg_stock,
                            'total_revenue': total_revenue,
                        }
                    )
                    synced_count += 1

            self.sync_results['category_perf'] = synced_count
            logger.info(f"   ✓ Synced {synced_count} category performance records")

        except Exception as e:
            logger.error(f"   ✗ Category performance sync failed: {e}")
            raise

    def sync_shop_performance(self, period_days=30):
        """
        Sync shop/OEM performance metrics

        Args:
            period_days: Number of days to analyze
        """
        logger.info("🏪 Syncing shop performance...")

        try:
            period_end = timezone.now().date()
            period_start = period_end - timedelta(days=period_days)

            # Get unique shops
            shops = Product.objects.values_list('shop', flat=True).distinct()

            synced_count = 0

            for shop in shops:
                for location in ['ABUJA', 'LAGOS']:
                    # Get sales for this shop/location in period
                    sales = Sale.objects.filter(
                        sale_date__date__gte=period_start,
                        sale_date__date__lte=period_end,
                        product__shop=shop,
                        product__location=location
                    )

                    total_units = sales.aggregate(total=Sum('quantity'))['total'] or 0
                    unique_products = sales.values('product').distinct().count()
                    total_revenue = sales.aggregate(revenue=Sum('total_price'))['revenue'] or Decimal('0.00')

                    # Current stock count for this shop
                    current_stock = Product.objects.filter(
                        shop=shop,
                        location=location
                    ).aggregate(total=Sum('quantity'))['total'] or 0

                    # Update or create performance record
                    ShopPerformance.objects.using('oem_sync_db').update_or_create(
                        period_start=period_start,
                        period_end=period_end,
                        shop=shop,
                        location=location,
                        defaults={
                            'total_units_sold': total_units,
                            'unique_products_sold': unique_products,
                            'current_stock_count': current_stock,
                            'total_revenue': total_revenue,
                        }
                    )
                    synced_count += 1

            self.sync_results['shop_perf'] = synced_count
            logger.info(f"   ✓ Synced {synced_count} shop performance records")

        except Exception as e:
            logger.error(f"   ✗ Shop performance sync failed: {e}")
            raise

    def _update_sync_metadata(self, sync_type, status, records_synced, error_msg=''):
        """
        Update sync metadata to track last sync time and status

        Args:
            sync_type: Type of sync performed
            status: 'success', 'failed', or 'in_progress'
            records_synced: Number of records synced
            error_msg: Error message if failed
        """
        try:
            SyncMetadata.objects.using('oem_sync_db').update_or_create(
                sync_type=sync_type,
                defaults={
                    'last_sync_time': timezone.now(),
                    'sync_status': status,
                    'records_synced': records_synced,
                    'error_message': error_msg or ''
                }
            )
        except Exception as e:
            logger.error(f"Failed to update sync metadata: {e}")


# Convenience function for manual sync
def sync_oem_data():
    """
    Run a full OEM data sync

    Returns:
        dict: Sync results
    """
    manager = OEMDataSyncManager(
        low_stock_threshold=10,
        critical_stock_threshold=3
    )
    return manager.sync_all()
