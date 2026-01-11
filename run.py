"""
Application Entry Point
Initializes and runs the Flask application with background services
"""

import os
import logging
from app import create_app, db
from app.services.sync_service import SyncService
from app.services.email_service import EmailService
from app.services.backup_service import BackupService
from config import config

# Determine configuration environment
config_name = os.environ.get('FLASK_ENV', 'development')
app = create_app(config_name)

# Setup logging
if not os.path.exists(app.config['LOG_FOLDER']):
    os.makedirs(app.config['LOG_FOLDER'])

logging.basicConfig(
    level=getattr(logging, app.config['LOG_LEVEL']),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(app.config['LOG_FOLDER'], 'app.log')),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


@app.shell_context_processor
def make_shell_context():
    """Make database and models available in Flask shell"""
    from app import models
    return {
        'db': db,
        'User': models.User,
        'Product': models.Product,
        'Sale': models.Sale,
        'Customer': models.Customer,
        'Supplier': models.Supplier
    }


@app.cli.command()
def init_db():
    """Initialize the database with tables and default data"""
    logger.info("Initializing database...")
    db.create_all()

    # Create default admin user if not exists
    from app.models import User
    from werkzeug.security import generate_password_hash

    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@sunnatcollection.com',
            full_name='Administrator',
            role='admin',
            is_active=True
        )
        admin.password_hash = generate_password_hash('admin123')
        db.session.add(admin)
        db.session.commit()
        logger.info("Default admin user created (username: admin, password: admin123)")

    logger.info("Database initialized successfully!")


@app.cli.command()
def create_sample_data():
    """Create sample data for testing"""
    from app.utils.helpers import create_sample_products, create_sample_customers
    logger.info("Creating sample data...")
    create_sample_products()
    create_sample_customers()
    logger.info("Sample data created successfully!")


@app.cli.command()
def run_sync():
    """Manually trigger sync operation"""
    logger.info("Starting manual sync...")
    sync_service = SyncService(app)
    sync_service.sync_all()
    logger.info("Sync completed!")


@app.cli.command()
def send_daily_report():
    """Manually send daily report"""
    logger.info("Generating and sending daily report...")
    email_service = EmailService(app)
    email_service.send_daily_report()
    logger.info("Daily report sent!")


@app.cli.command()
def backup_database():
    """Manually backup database"""
    logger.info("Starting database backup...")
    backup_service = BackupService(app)
    backup_service.backup_database()
    logger.info("Backup completed!")


def start_background_services():
    """Start background services for sync, email, and backup"""
    logger.info("Starting background services...")

    # Initialize services
    sync_service = SyncService(app)
    email_service = EmailService(app)
    backup_service = BackupService(app)

    # Start schedulers
    if app.config['ENABLE_CLOUD_SYNC'] and app.config['AUTO_SYNC']:
        sync_service.start_scheduler()
        logger.info("Sync service started")

    if app.config['DAILY_REPORT_RECIPIENTS']:
        email_service.start_scheduler()
        logger.info("Email service started")

    if app.config['BACKUP_ENABLED']:
        backup_service.start_scheduler()
        logger.info("Backup service started")


if __name__ == '__main__':
    # Check if running in development mode
    is_dev = os.environ.get('FLASK_ENV', 'development') == 'development'
    use_reloader = os.environ.get('FLASK_USE_RELOADER', 'true').lower() == 'true'

    with app.app_context():
        # Create tables if they don't exist
        db.create_all()
        logger.info("Database tables created")

        # Start background services (only if not using reloader to avoid duplicate services)
        if not use_reloader or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            start_background_services()

    # Run the application
    logger.info(f"Starting {app.config['BUSINESS_NAME']} POS System...")
    logger.info(f"Debug mode: {is_dev}, Auto-reload: {use_reloader}")

    app.run(
        host='0.0.0.0',
        port=5001,
        debug=is_dev,
        use_reloader=use_reloader
    )
