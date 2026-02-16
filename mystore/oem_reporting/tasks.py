"""
Celery Tasks for OEM/Inventory Data Sync
Scheduled tasks to automatically sync data every 15-30 minutes

Setup Instructions:
1. Configure Celery Beat schedule in celery.py:

   from celery.schedules import crontab

   app.conf.beat_schedule = {
       'full-sync-every-30-minutes': {
           'task': 'oem_reporting.tasks.sync_oem_data_task',
           'schedule': crontab(minute='*/30'),
       },
   }

2. Start Celery Beat:
   celery -A mystore beat --loglevel=info --pool=solo

3. Start Celery Worker:
   celery -A mystore worker --loglevel=info --pool=solo
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone

logger = get_task_logger(__name__)


@shared_task(name='oem_reporting.tasks.sync_oem_data_task', bind=True, max_retries=3)
def sync_oem_data_task(self):
    """
    Scheduled task to sync OEM/Inventory data to online reporting database

    Runs automatically based on Celery Beat schedule
    """
    logger.info('🔄 Starting scheduled OEM data sync...')

    try:
        from .sync import sync_oem_data

        # Run the sync
        result = sync_oem_data()

        if result['success']:
            logger.info(
                f'✅ Sync completed successfully in {result["duration_seconds"]:.2f}s. '
                f'Records synced: {result["records_synced"]}'
            )
            return {
                'status': 'success',
                'timestamp': result['timestamp'],
                'records_synced': result['records_synced']
            }
        else:
            logger.error(f'❌ Sync failed: {result["error"]}')
            # Retry the task
            raise self.retry(countdown=300, exc=Exception(result['error']))  # Retry after 5 minutes

    except Exception as exc:
        logger.error(f'❌ Fatal error in sync task: {str(exc)}', exc_info=True)
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(name='oem_reporting.tasks.sync_inventory_only_task')
def sync_inventory_only_task():
    """
    Quick sync task for inventory only (faster than full sync)
    Can be scheduled more frequently (e.g., every 5 minutes)
    """
    logger.info('📦 Starting inventory-only sync...')

    try:
        from .sync import OEMDataSyncManager

        manager = OEMDataSyncManager()
        manager.sync_inventory_snapshot()
        manager.sync_low_stock_alerts()

        logger.info(
            f'✅ Inventory sync completed. '
            f'Inventory: {manager.sync_results["inventory"]}, '
            f'Alerts: {manager.sync_results["alerts"]}'
        )

        return {
            'status': 'success',
            'inventory_records': manager.sync_results['inventory'],
            'alert_records': manager.sync_results['alerts']
        }

    except Exception as exc:
        logger.error(f'❌ Inventory sync failed: {str(exc)}', exc_info=True)
        raise


@shared_task(name='oem_reporting.tasks.sync_sales_summary_task')
def sync_sales_summary_task():
    """
    Sync sales summaries and performance metrics
    Can be scheduled less frequently (e.g., hourly or daily)
    """
    logger.info('📊 Starting sales summary sync...')

    try:
        from .sync import OEMDataSyncManager

        manager = OEMDataSyncManager()
        manager.sync_daily_sales_summary()
        manager.sync_top_selling_products()
        manager.sync_category_performance()
        manager.sync_shop_performance()

        logger.info(
            f'✅ Sales sync completed. '
            f'Daily summaries: {manager.sync_results["sales_daily"]}, '
            f'Top products: {manager.sync_results["top_products"]}'
        )

        return {
            'status': 'success',
            'sales_records': manager.sync_results['sales_daily'],
            'top_products': manager.sync_results['top_products']
        }

    except Exception as exc:
        logger.error(f'❌ Sales sync failed: {str(exc)}', exc_info=True)
        raise


# Manual trigger functions (can be called from Django admin or views)
def trigger_sync_now():
    """
    Manually trigger a sync immediately
    Returns: Celery task result
    """
    return sync_oem_data_task.delay()


def trigger_inventory_sync_now():
    """
    Manually trigger inventory sync immediately
    Returns: Celery task result
    """
    return sync_inventory_only_task.delay()


def get_last_sync_status():
    """
    Get status of last sync operation
    Returns: dict with sync metadata
    """
    try:
        from .models import SyncMetadata
        metadata = SyncMetadata.objects.using('oem_sync_db').filter(
            sync_type='full_sync'
        ).first()

        if metadata:
            return {
                'last_sync_time': metadata.last_sync_time,
                'status': metadata.sync_status,
                'records_synced': metadata.records_synced,
                'error_message': metadata.error_message
            }
        return None

    except Exception as e:
        logger.error(f'Failed to get sync status: {e}')
        return None
