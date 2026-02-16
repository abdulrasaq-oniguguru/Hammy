"""
Django management command to sync OEM/Inventory data to online reporting database

Usage:
    python manage.py sync_oem_data
    python manage.py sync_oem_data --days-back 60
    python manage.py sync_oem_data --low-stock-threshold 5
"""

from django.core.management.base import BaseCommand, CommandError
import sys
import os

# Add parent directory to path to import oem_sync_script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from oem_sync_script import OEMDataSyncManager


class Command(BaseCommand):
    help = 'Sync OEM and inventory data to online reporting database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days-back',
            type=int,
            default=30,
            help='Number of days of sales history to sync (default: 30)'
        )
        parser.add_argument(
            '--low-stock-threshold',
            type=int,
            default=10,
            help='Quantity threshold for low stock alerts (default: 10)'
        )
        parser.add_argument(
            '--critical-stock-threshold',
            type=int,
            default=3,
            help='Quantity threshold for critical stock alerts (default: 3)'
        )
        parser.add_argument(
            '--inventory-only',
            action='store_true',
            help='Sync only inventory snapshot'
        )
        parser.add_argument(
            '--sales-only',
            action='store_true',
            help='Sync only sales summaries'
        )

    def handle(self, *args, **options):
        self.stdout.write('=' * 60)
        self.stdout.write(self.style.MIGRATE_HEADING('  OEM/Inventory Data Sync'))
        self.stdout.write('=' * 60)
        self.stdout.write('')

        # Initialize sync manager
        manager = OEMDataSyncManager(
            low_stock_threshold=options['low_stock_threshold'],
            critical_stock_threshold=options['critical_stock_threshold']
        )

        try:
            # Check if partial sync requested
            if options['inventory_only']:
                self.stdout.write('Running inventory-only sync...')
                manager.sync_inventory_snapshot()
                manager.sync_low_stock_alerts()
                result = {
                    'success': True,
                    'records_synced': {
                        'inventory': manager.sync_results.get('inventory', 0),
                        'alerts': manager.sync_results.get('alerts', 0)
                    }
                }

            elif options['sales_only']:
                self.stdout.write(f'Running sales-only sync (last {options["days_back"]} days)...')
                manager.sync_daily_sales_summary(days_back=options['days_back'])
                manager.sync_top_selling_products()
                manager.sync_category_performance()
                manager.sync_shop_performance()
                result = {
                    'success': True,
                    'records_synced': {
                        'sales': manager.sync_results.get('sales_daily', 0),
                        'top_products': manager.sync_results.get('top_products', 0),
                        'categories': manager.sync_results.get('category_perf', 0),
                        'shops': manager.sync_results.get('shop_perf', 0)
                    }
                }

            else:
                # Full sync
                self.stdout.write('Running full data sync...')
                result = manager.sync_all()

            # Display results
            self.stdout.write('')
            if result['success']:
                self.stdout.write(self.style.SUCCESS('✅ Sync completed successfully!'))
                self.stdout.write('')
                self.stdout.write(self.style.SUCCESS('📊 Records Synced:'))

                for data_type, count in result.get('records_synced', {}).items():
                    self.stdout.write(f'   • {data_type}: {count} records')

                if 'duration_seconds' in result:
                    self.stdout.write('')
                    self.stdout.write(f'⏱️  Duration: {result["duration_seconds"]:.2f} seconds')

            else:
                self.stdout.write(self.style.ERROR('❌ Sync failed!'))
                self.stdout.write(self.style.ERROR(f'Error: {result.get("error", "Unknown error")}'))
                raise CommandError('Sync operation failed')

            self.stdout.write('')
            self.stdout.write('=' * 60)

        except Exception as e:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(f'❌ Fatal error during sync: {str(e)}'))
            self.stdout.write('=' * 60)
            raise CommandError(f'Sync failed: {str(e)}')
