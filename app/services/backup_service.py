"""
Backup Service
Handles automatic database backups and retention
"""

import os
import shutil
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)


class BackupService:
    """Service for database backups"""

    def __init__(self, app):
        self.app = app
        self.scheduler = None

    def backup_database(self):
        """Create a backup of the local database"""
        try:
            with self.app.app_context():
                backup_folder = self.app.config.get('BACKUP_FOLDER')
                db_path = self.app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')

                # Create backup folder if it doesn't exist
                os.makedirs(backup_folder, exist_ok=True)

                # Generate backup filename with timestamp
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_filename = f"backup_{timestamp}.db"
                backup_path = os.path.join(backup_folder, backup_filename)

                # Copy database file
                if os.path.exists(db_path):
                    shutil.copy2(db_path, backup_path)
                    logger.info(f"Database backup created: {backup_filename}")

                    # Cleanup old backups
                    self.cleanup_old_backups()

                    return backup_path
                else:
                    logger.error(f"Database file not found: {db_path}")
                    return None

        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return None

    def cleanup_old_backups(self):
        """Remove old backups based on retention policy"""
        try:
            backup_folder = self.app.config.get('BACKUP_FOLDER')
            retention_days = self.app.config.get('BACKUP_RETENTION_DAYS', 30)

            cutoff_date = datetime.now() - timedelta(days=retention_days)

            for filename in os.listdir(backup_folder):
                if filename.startswith('backup_') and filename.endswith('.db'):
                    filepath = os.path.join(backup_folder, filename)

                    # Get file modification time
                    file_time = datetime.fromtimestamp(os.path.getmtime(filepath))

                    # Delete if older than retention period
                    if file_time < cutoff_date:
                        os.remove(filepath)
                        logger.info(f"Deleted old backup: {filename}")

        except Exception as e:
            logger.error(f"Error cleaning up old backups: {e}")

    def restore_backup(self, backup_filename):
        """
        Restore database from backup

        Args:
            backup_filename: Name of backup file to restore

        Returns:
            bool: Success status
        """
        try:
            backup_folder = self.app.config.get('BACKUP_FOLDER')
            backup_path = os.path.join(backup_folder, backup_filename)

            if not os.path.exists(backup_path):
                logger.error(f"Backup file not found: {backup_filename}")
                return False

            db_path = self.app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')

            # Create a backup of current database before restoring
            current_backup = f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2(db_path, os.path.join(backup_folder, current_backup))

            # Restore from backup
            shutil.copy2(backup_path, db_path)
            logger.info(f"Database restored from: {backup_filename}")

            return True

        except Exception as e:
            logger.error(f"Error restoring backup: {e}")
            return False

    def list_backups(self):
        """
        Get list of available backups

        Returns:
            list: List of backup files with metadata
        """
        try:
            backup_folder = self.app.config.get('BACKUP_FOLDER')
            backups = []

            for filename in os.listdir(backup_folder):
                if filename.startswith('backup_') and filename.endswith('.db'):
                    filepath = os.path.join(backup_folder, filename)

                    backups.append({
                        'filename': filename,
                        'size': os.path.getsize(filepath),
                        'created': datetime.fromtimestamp(os.path.getmtime(filepath)),
                        'path': filepath
                    })

            # Sort by creation time (newest first)
            backups.sort(key=lambda x: x['created'], reverse=True)

            return backups

        except Exception as e:
            logger.error(f"Error listing backups: {e}")
            return []

    def start_scheduler(self):
        """Start background scheduler for automatic backups"""
        if self.scheduler:
            logger.warning("Backup scheduler already running")
            return

        if not self.app.config.get('BACKUP_ENABLED'):
            logger.info("Automatic backups are disabled")
            return

        self.scheduler = BackgroundScheduler()

        # Parse backup time from config (e.g., "23:00")
        backup_time = self.app.config.get('BACKUP_TIME', '23:00')
        hour, minute = map(int, backup_time.split(':'))

        # Schedule daily backup
        self.scheduler.add_job(
            func=self.backup_database,
            trigger='cron',
            hour=hour,
            minute=minute,
            id='daily_backup'
        )

        self.scheduler.start()
        logger.info(f"Backup scheduler started. Daily backups at {backup_time}")

    def stop_scheduler(self):
        """Stop the scheduler"""
        if self.scheduler:
            self.scheduler.shutdown()
            self.scheduler = None
            logger.info("Backup scheduler stopped")
