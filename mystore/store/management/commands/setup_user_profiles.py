from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from store.models import UserProfile


class Command(BaseCommand):
    help = 'Create UserProfile instances for existing users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--default-access',
            type=str,
            default='cashier',
            help='Default access level for existing users without profiles',
        )

    def handle(self, *args, **options):
        users_without_profiles = User.objects.filter(profile__isnull=True)
        created_count = 0

        for user in users_without_profiles:
            # Determine access level based on user status
            if user.is_superuser:
                access_level = 'md'
            else:
                access_level = options['default_access']

            UserProfile.objects.create(
                user=user,
                access_level=access_level,
                is_active_staff=user.is_staff
            )
            created_count += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f'Created profile for user: {user.username} (Access: {access_level})'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created {created_count} user profiles'
            )
        )

# 4. Run the management command
# python manage.py setup_user_profiles