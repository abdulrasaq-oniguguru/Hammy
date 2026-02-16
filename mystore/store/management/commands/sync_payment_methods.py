"""
Management command to sync/initialize payment methods from PaymentMethod.PAYMENT_METHODS
to PaymentMethodConfiguration
"""
from django.core.management.base import BaseCommand
from store.models import PaymentMethod, PaymentMethodConfiguration


class Command(BaseCommand):
    help = 'Sync default payment methods from PaymentMethod.PAYMENT_METHODS to PaymentMethodConfiguration'

    def handle(self, *args, **options):
        """Sync payment methods"""
        created_count = 0
        updated_count = 0

        self.stdout.write(self.style.SUCCESS('Starting payment method synchronization...'))

        # Get all payment methods from PaymentMethod.PAYMENT_METHODS
        for code, display_name in PaymentMethod.PAYMENT_METHODS:
            # Check if payment method already exists
            method, created = PaymentMethodConfiguration.objects.get_or_create(
                code=code,
                defaults={
                    'name': display_name,
                    'display_name': display_name,
                    'is_active': True,
                    'sort_order': 0,
                }
            )

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'  Created: {display_name} ({code})')
                )
            else:
                # Update display name if it changed
                if method.display_name != display_name or method.name != display_name:
                    method.name = display_name
                    method.display_name = display_name
                    method.save()
                    updated_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'  Updated: {display_name} ({code})')
                    )
                else:
                    self.stdout.write(
                        self.style.HTTP_INFO(f'  Exists: {display_name} ({code})')
                    )

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Synchronization complete! Created: {created_count}, Updated: {updated_count}'
            )
        )
