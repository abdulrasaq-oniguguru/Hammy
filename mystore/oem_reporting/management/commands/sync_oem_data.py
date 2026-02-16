"""
Django Management Command for OEM Data Sync
Manually sync OEM/Inventory data to online reporting database

Usage:
    python manage.py sync_oem_data
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from oem_reporting.sync import sync_oem_data


class Command(BaseCommand):
    help = 'Sync OEM and inventory data to online reporting database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed sync progress',
        )

    def handle(self, *args, **options):
        verbose = options.get('verbose', False)

        self.stdout.write('=' * 60)
        self.stdout.write(self.style.HTTP_INFO('  OEM/Inventory Data Sync'))
        self.stdout.write('=' * 60)
        self.stdout.write('')

        if verbose:
            self.stdout.write('Running full data sync...')

        try:
            # Run the sync
            result = sync_oem_data()

            if result['success']:
                self.stdout.write('')
                self.stdout.write(self.style.SUCCESS(
                    f"✅ Sync completed successfully!"
                ))
                self.stdout.write('')
                self.stdout.write(self.style.SUCCESS(
                    f"📊 Records Synced:"
                ))
                for key, value in result['records_synced'].items():
                    self.stdout.write(f"   • {key}: {value} records")

                self.stdout.write('')
                self.stdout.write(f"⏱️  Duration: {result['duration_seconds']:.2f} seconds")
                self.stdout.write('')
                self.stdout.write('=' * 60)

            else:
                self.stdout.write('')
                self.stdout.write(self.style.ERROR(
                    f"❌ Sync failed: {result['error']}"
                ))
                self.stdout.write('')
                self.stdout.write('=' * 60)
                return

        except Exception as e:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(
                f"❌ Fatal error: {str(e)}"
            ))
            self.stdout.write('')
            self.stdout.write('=' * 60)
            raise
