from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Trigger Celery task to send daily sales report'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Report date in YYYY-MM-DD format (defaults to yesterday)'
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Override recipient email address'
        )

    def handle(self, *args, **options):
        date_str = options.get('date')
        override_email = options.get('email')

        # For display purposes
        if date_str:
            display_date = date_str
        else:
            from django.utils import timezone
            from datetime import timedelta
            display_date = (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        # Trigger Celery task
        from store.tasks import send_daily_sales_report_task
        result = send_daily_sales_report_task.delay(
            report_date_str=date_str,
            override_email=override_email
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Task queued for {display_date} - Task ID: {result.id}'
            )
        )