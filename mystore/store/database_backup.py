import os
import subprocess
import logging
import schedule
import time
from datetime import datetime
from pathlib import Path


# Configuration
class BackupConfig:
    # Database Configuration
    DB_SERVER = "localhost"
    DB_NAME = "Store"
    DB_USER = "sa"
    DB_PASSWORD = "*3mb741101"

    # Flash Drive Configuration (Update these paths)
    FLASH_DRIVE_PATH = "D:\\"  # Change to your flash drive letter
    BACKUP_FOLDER = "Database_Backups"

    # Backup Settings
    BACKUP_TIME = "02:00"  # 2:00 AM daily
    MAX_BACKUP_DAYS = 7  # Keep backups for 7 days

    # SQL Server backup tool path (usually installed with SQL Server)
    SQLCMD_PATH = r"C:\Program Files\Microsoft SQL Server\Client SDK\ODBC\170\Tools\Binn\sqlcmd.exe"


class DatabaseBackup:
    def __init__(self):
        self.config = BackupConfig()
        self.setup_logging()
        self.backup_dir = Path(self.config.FLASH_DRIVE_PATH) / self.config.BACKUP_FOLDER
        self.ensure_backup_directory()

    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('backup.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def ensure_backup_directory(self):
        """Create backup directory if it doesn't exist"""
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Backup directory ensured: {self.backup_dir}")
        except Exception as e:
            self.logger.error(f"Failed to create backup directory: {e}")
            raise

    def check_flash_drive(self):
        """Check if flash drive is available"""
        if not Path(self.config.FLASH_DRIVE_PATH).exists():
            self.logger.error(f"Flash drive not found at {self.config.FLASH_DRIVE_PATH}")
            return False
        return True

    def get_backup_filename(self):
        """Generate backup filename with timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{self.config.DB_NAME}_backup_{timestamp}.bak"

    def cleanup_old_backups(self):
        """Remove old backup files"""
        try:
            backup_files = list(self.backup_dir.glob(f"{self.config.DB_NAME}_backup_*.bak"))
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            # Keep only the most recent backups
            files_to_delete = backup_files[self.config.MAX_BACKUP_DAYS:]

            for file_path in files_to_delete:
                file_path.unlink()
                self.logger.info(f"Deleted old backup: {file_path.name}")

        except Exception as e:
            self.logger.error(f"Error cleaning up old backups: {e}")

    def create_backup_sql_server(self):
        """Create backup using SQL Server BACKUP command"""
        if not self.check_flash_drive():
            return False

        backup_filename = self.get_backup_filename()
        backup_path = self.backup_dir / backup_filename

        # SQL Server BACKUP command
        sql_command = f"""
        BACKUP DATABASE [{self.config.DB_NAME}] 
        TO DISK = N'{backup_path}' 
        WITH FORMAT, INIT, 
        NAME = N'{self.config.DB_NAME} Full Database Backup', 
        SKIP, NOREWIND, NOUNLOAD, STATS = 10
        """

        try:
            # Execute backup command using sqlcmd
            cmd = [
                self.config.SQLCMD_PATH,
                "-S", self.config.DB_SERVER,
                "-U", self.config.DB_USER,
                "-P", self.config.DB_PASSWORD,
                "-Q", sql_command
            ]

            self.logger.info(f"Starting backup to: {backup_path}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

            if result.returncode == 0:
                self.logger.info(f"Backup completed successfully: {backup_filename}")
                self.cleanup_old_backups()
                return True
            else:
                self.logger.error(f"Backup failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            self.logger.error("Backup operation timed out")
            return False
        except Exception as e:
            self.logger.error(f"Backup error: {e}")
            return False

    def create_backup_django_dumpdata(self):
        """Alternative: Create backup using Django dumpdata (JSON format)"""
        if not self.check_flash_drive():
            return False

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{self.config.DB_NAME}_django_backup_{timestamp}.json"
        backup_path = self.backup_dir / backup_filename

        try:
            # Django dumpdata command
            cmd = ["python", "manage.py", "dumpdata", "--output", str(backup_path)]

            self.logger.info(f"Starting Django backup to: {backup_path}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

            if result.returncode == 0:
                self.logger.info(f"Django backup completed: {backup_filename}")
                return True
            else:
                self.logger.error(f"Django backup failed: {result.stderr}")
                return False

        except Exception as e:
            self.logger.error(f"Django backup error: {e}")
            return False

    def run_backup(self):
        """Main backup execution method"""
        self.logger.info("=" * 50)
        self.logger.info("Starting daily database backup")

        # Try SQL Server native backup first
        if self.create_backup_sql_server():
            self.logger.info("SQL Server backup completed successfully")
        else:
            self.logger.warning("SQL Server backup failed, trying Django dumpdata...")
            if self.create_backup_django_dumpdata():
                self.logger.info("Django backup completed successfully")
            else:
                self.logger.error("Both backup methods failed!")

        self.logger.info("Backup process finished")
        self.logger.info("=" * 50)

    def start_scheduler(self):
        """Start the backup scheduler"""
        self.logger.info(f"Backup scheduler started. Daily backup at {self.config.BACKUP_TIME}")

        # Schedule daily backup
        schedule.every().day.at(self.config.BACKUP_TIME).do(self.run_backup)

        # Also run a test backup immediately (optional)
        # schedule.every(10).seconds.do(self.run_backup)  # For testing

        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute

        except KeyboardInterrupt:
            self.logger.info("Backup scheduler stopped by user")
        except Exception as e:
            self.logger.error(f"Scheduler error: {e}")


def main():
    """Main function to run the backup system"""
    try:
        backup_system = DatabaseBackup()

        # Run immediate backup (for testing)
        print("Running immediate backup test...")
        backup_system.run_backup()

        # Start scheduler for daily backups
        print(f"Starting daily backup scheduler...")
        backup_system.start_scheduler()

    except Exception as e:
        print(f"Failed to start backup system: {e}")


if __name__ == "__main__":
    main()