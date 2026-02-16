"""
Script to setup Celery Beat periodic tasks in the database.
Run this once to create the scheduled tasks from settings.CELERY_BEAT_SCHEDULE
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mystore.settings')
django.setup()

from django_celery_beat.models import PeriodicTask, CrontabSchedule
from django.conf import settings
import json

def setup_periodic_tasks():
    """Create periodic tasks from CELERY_BEAT_SCHEDULE settings"""

    print("Setting up Celery Beat periodic tasks...")

    for task_name, task_config in settings.CELERY_BEAT_SCHEDULE.items():
        print(f"\nProcessing task: {task_name}")

        # Get schedule configuration
        schedule = task_config['schedule']
        task_path = task_config['task']

        # Create or get crontab schedule
        crontab, created = CrontabSchedule.objects.get_or_create(
            minute=schedule.minute,
            hour=schedule.hour,
            day_of_week=schedule.day_of_week,
            day_of_month=schedule.day_of_month,
            month_of_year=schedule.month_of_year,
            timezone=settings.CELERY_TIMEZONE
        )

        if created:
            print(f"  Created crontab: {crontab}")
        else:
            print(f"  Using existing crontab: {crontab}")

        # Create or update periodic task
        periodic_task, created = PeriodicTask.objects.get_or_create(
            name=task_name,
            defaults={
                'task': task_path,
                'crontab': crontab,
                'enabled': True,
            }
        )

        if not created:
            # Update existing task
            periodic_task.task = task_path
            periodic_task.crontab = crontab
            periodic_task.enabled = True
            periodic_task.save()
            print(f"  Updated existing task: {task_name}")
        else:
            print(f"  Created new task: {task_name}")

        print(f"     Task: {task_path}")
        print(f"     Schedule: {crontab}")
        print(f"     Enabled: {periodic_task.enabled}")

    print("\n" + "="*60)
    print("All periodic tasks have been set up successfully!")
    print("="*60)

    # Display all tasks
    print("\nCurrent periodic tasks in database:")
    all_tasks = PeriodicTask.objects.all()
    for task in all_tasks:
        status = "ENABLED" if task.enabled else "DISABLED"
        print(f"  [{status}] - {task.name}")
        print(f"     Task: {task.task}")
        print(f"     Schedule: {task.crontab}")
        print()

if __name__ == '__main__':
    setup_periodic_tasks()
