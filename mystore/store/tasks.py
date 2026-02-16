import logging
from datetime import datetime
from celery import shared_task
import subprocess
from pathlib import Path

logger = logging.getLogger('daily_tasks')


# ===========================
# PYTHONANYWHERE SYNC TASK
# ===========================

@shared_task(bind=True, max_retries=3)
def sync_to_pythonanywhere_task(self):
    """
    Celery task to sync data to PythonAnywhere every 30 minutes.
    Uses improved incremental sync script with batching.
    """
    try:
        logger.info("Starting automated PythonAnywhere sync task")

        # Use the improved sync script with incremental mode
        script_path = Path(__file__).parent.parent.parent / 'sync_to_pythonanywhere_improved.py'
        python_exe = r"C:\III\.venv\Scripts\python.exe"

        if not script_path.exists():
            # Fallback to old script
            script_path = Path(__file__).parent.parent.parent / 'sync_to_pythonanywhere.py'
            if not script_path.exists():
                raise Exception(f"Sync script not found")

        logger.info(f"Running sync script: {script_path}")

        # Run the incremental sync (only recent changes)
        result = subprocess.run(
            [python_exe, str(script_path), '--incremental'],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
            cwd=str(script_path.parent)
        )

        if result.returncode != 0:
            logger.warning(f"Sync script failed: {result.stderr}")
            logger.warning("Will retry on next scheduled run")
            # Don't raise exception - let it try again on next schedule
            return "PythonAnywhere sync failed, will retry"

        logger.info(f"SUCCESS: PythonAnywhere sync completed")
        logger.info(f"Output: {result.stdout}")

        return "PythonAnywhere sync successful"

    except subprocess.TimeoutExpired:
        logger.error("Sync script timed out after 10 minutes")
        # Don't retry - let next scheduled run handle it
        return "Sync timeout, will retry on next schedule"

    except Exception as exc:
        logger.error(f"Failed to sync to PythonAnywhere: {str(exc)}")
        logger.exception("Full traceback:")
        # Don't retry - let next scheduled run handle it
        return f"Sync failed: {str(exc)}"


# ===========================
# DATABASE BACKUP TASK
# ===========================

class BackupConfig:
    # Database Configuration
    DB_SERVER = "localhost"
    DB_NAME = "Store"
    DB_USER = "sa"
    DB_PASSWORD = "*3mb741101"

    # Flash Drive Configuration (Update these paths)
    FLASH_DRIVE_PATH = "D:\\"  # Change to your flash drive letter
    BACKUP_FOLDER = "Database_Backups"

    # SQL Server backup tool path (usually installed with SQL Server)
    SQLCMD_PATH = r"C:\Program Files\Microsoft SQL Server\Client SDK\ODBC\170\Tools\Binn\sqlcmd.exe"


@shared_task(bind=True, max_retries=3)
def run_daily_backup_task(self):
    """
    Celery task to run the daily database backup.
    This will be triggered by Celery Beat at 11:00 AM.
    IMPORTANT: Skips backup if flash drive is not found (doesn't fail).
    """
    try:
        logger.info("Starting daily database backup task via Celery")

        config = BackupConfig()

        # Check if flash drive is available FIRST
        if not Path(config.FLASH_DRIVE_PATH).exists():
            logger.warning(f"SKIPPED: Flash drive not found at {config.FLASH_DRIVE_PATH}")
            logger.warning("Backup skipped - will try again tomorrow at scheduled time")
            # Return success (don't fail) - just skip this backup
            return f"Backup skipped - drive {config.FLASH_DRIVE_PATH} not found"

        # Create backup directory path
        backup_dir = Path(config.FLASH_DRIVE_PATH) / config.BACKUP_FOLDER

        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"SKIPPED: Cannot create backup directory: {e}")
            return "Backup skipped - cannot create directory"

        # Generate backup filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{config.DB_NAME}_backup_{timestamp}.bak"
        backup_path = backup_dir / backup_filename

        # SQL Server BACKUP command
        sql_command = f"""
        BACKUP DATABASE [{config.DB_NAME}]
        TO DISK = N'{backup_path}'
        WITH FORMAT, INIT,
        NAME = N'{config.DB_NAME} Full Database Backup',
        SKIP, NOREWIND, NOUNLOAD, STATS = 10
        """

        # Execute backup command using sqlcmd
        cmd = [
            config.SQLCMD_PATH,
            "-S", config.DB_SERVER,
            "-U", config.DB_USER,
            "-P", config.DB_PASSWORD,
            "-Q", sql_command
        ]

        logger.info(f"Starting backup to: {backup_path}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

        if result.returncode != 0:
            logger.error(f"Backup command failed: {result.stderr}")
            # Don't retry - let tomorrow's scheduled run handle it
            return f"Backup failed: {result.stderr}"

        logger.info(f"SUCCESS: Backup completed successfully: {backup_filename}")

        # Cleanup old backups (keep last 7)
        try:
            cleanup_old_backups(backup_dir, config.DB_NAME)
        except Exception as e:
            logger.warning(f"Cleanup of old backups failed: {e}")
            # Don't fail the task if cleanup fails

        return f"Backup successful: {backup_filename}"

    except Exception as exc:
        logger.error(f"Failed to run backup: {str(exc)}")
        # Don't retry - let tomorrow's scheduled run handle it
        return f"Backup failed: {str(exc)}"


def cleanup_old_backups(backup_dir, db_name, max_days=7):
    """Remove old backup files"""
    try:
        backup_files = list(backup_dir.glob(f"{db_name}_backup_*.bak"))
        backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        # Keep only the most recent backups
        files_to_delete = backup_files[max_days:]

        for file_path in files_to_delete:
            file_path.unlink()
            logger.info(f"Deleted old backup: {file_path.name}")

    except Exception as e:
        logger.error(f"Error cleaning up old backups: {e}")
