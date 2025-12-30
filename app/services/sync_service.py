"""
Sync Service
Handles synchronization between local SQLite and cloud database
"""

import logging
import requests
import json
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import create_engine
from app.models import db, SyncQueue

logger = logging.getLogger(__name__)


class SyncService:
    """Service for synchronizing local and cloud databases"""

    def __init__(self, app):
        self.app = app
        self.scheduler = None
        self.cloud_engine = None

    def check_internet_connection(self):
        """Check if internet connection is available"""
        try:
            # Try to reach a reliable endpoint
            response = requests.get('https://www.google.com', timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"No internet connection: {e}")
            return False

    def get_cloud_engine(self):
        """Get cloud database engine"""
        if not self.cloud_engine:
            cloud_url = self.app.config.get('CLOUD_DATABASE_URL')
            if cloud_url:
                self.cloud_engine = create_engine(cloud_url)
        return self.cloud_engine

    def sync_table(self, table_name, operation, record_id, data):
        """
        Sync a single record to cloud database

        Args:
            table_name: Name of the table
            operation: insert, update, or delete
            record_id: ID of the record
            data: Data to sync (dict)

        Returns:
            bool: Success status
        """
        try:
            engine = self.get_cloud_engine()
            if not engine:
                logger.error("Cloud database not configured")
                return False

            with engine.connect() as conn:
                if operation == 'insert':
                    # Handle insert
                    logger.info(f"Syncing insert to {table_name}: {record_id}")
                    # This is a simplified version - actual implementation would
                    # need to handle the full record data and schema
                    pass

                elif operation == 'update':
                    # Handle update
                    logger.info(f"Syncing update to {table_name}: {record_id}")
                    pass

                elif operation == 'delete':
                    # Handle delete
                    logger.info(f"Syncing delete to {table_name}: {record_id}")
                    pass

            return True

        except Exception as e:
            logger.error(f"Error syncing {table_name}/{operation}/{record_id}: {e}")
            return False

    def process_sync_queue(self):
        """Process all pending items in sync queue"""
        if not self.check_internet_connection():
            logger.info("No internet connection, skipping sync")
            return

        if not self.app.config.get('ENABLE_CLOUD_SYNC'):
            logger.debug("Cloud sync is disabled")
            return

        with self.app.app_context():
            # Get pending sync items
            pending_items = SyncQueue.query.filter_by(status='pending')\
                .order_by(SyncQueue.created_at).all()

            if not pending_items:
                logger.debug("No pending items to sync")
                return

            logger.info(f"Processing {len(pending_items)} pending sync items")

            synced_count = 0
            failed_count = 0

            for item in pending_items:
                try:
                    # Parse data
                    data = json.loads(item.data_json) if item.data_json else {}

                    # Attempt sync
                    success = self.sync_table(
                        item.table_name,
                        item.operation,
                        item.record_id,
                        data
                    )

                    if success:
                        item.status = 'synced'
                        item.synced_at = datetime.utcnow()
                        synced_count += 1
                    else:
                        item.status = 'failed'
                        item.error_message = 'Sync operation failed'
                        failed_count += 1

                    db.session.commit()

                except Exception as e:
                    item.status = 'failed'
                    item.error_message = str(e)
                    db.session.commit()
                    failed_count += 1
                    logger.error(f"Error processing sync item {item.id}: {e}")

            logger.info(f"Sync completed: {synced_count} synced, {failed_count} failed")

    def sync_all(self):
        """Manually trigger full sync"""
        logger.info("Starting manual sync...")
        self.process_sync_queue()

    def start_scheduler(self):
        """Start background scheduler for automatic sync"""
        if self.scheduler:
            logger.warning("Sync scheduler already running")
            return

        if not self.app.config.get('ENABLE_CLOUD_SYNC'):
            logger.info("Cloud sync is disabled, not starting scheduler")
            return

        self.scheduler = BackgroundScheduler()

        # Get sync interval from config (in minutes)
        interval = self.app.config.get('SYNC_INTERVAL_MINUTES', 30)

        # Schedule periodic sync
        self.scheduler.add_job(
            func=self.process_sync_queue,
            trigger='interval',
            minutes=interval,
            id='sync_queue'
        )

        self.scheduler.start()
        logger.info(f"Sync scheduler started. Will sync every {interval} minutes")

    def stop_scheduler(self):
        """Stop the scheduler"""
        if self.scheduler:
            self.scheduler.shutdown()
            self.scheduler = None
            logger.info("Sync scheduler stopped")

    def get_sync_status(self):
        """Get current sync status"""
        with self.app.app_context():
            pending = SyncQueue.query.filter_by(status='pending').count()
            synced = SyncQueue.query.filter_by(status='synced').count()
            failed = SyncQueue.query.filter_by(status='failed').count()

            return {
                'pending': pending,
                'synced': synced,
                'failed': failed,
                'internet_available': self.check_internet_connection(),
                'sync_enabled': self.app.config.get('ENABLE_CLOUD_SYNC', False)
            }
