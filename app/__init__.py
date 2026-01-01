"""
Flask Application Factory
Initializes and configures the Flask application
"""

import os
from flask import Flask, render_template
from flask_login import LoginManager
from flask_migrate import Migrate
from config import config
from app.models import db, User

# Import extended models for database migrations
from app import models_extended

# Initialize extensions
login_manager = LoginManager()
migrate = Migrate()


def create_app(config_name='default'):
    """
    Application factory pattern
    Creates and configures Flask application
    """
    app = Flask(__name__)

    # Load configuration
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login"""
        return User.query.get(int(user_id))

    # Create upload folders if they don't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['BACKUP_FOLDER'], exist_ok=True)
    os.makedirs(app.config['LOG_FOLDER'], exist_ok=True)

    # Register blueprints
    from app.routes.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.routes.pos import bp as pos_bp
    app.register_blueprint(pos_bp, url_prefix='/pos')

    from app.routes.inventory import bp as inventory_bp
    app.register_blueprint(inventory_bp, url_prefix='/inventory')

    from app.routes.customers import bp as customers_bp
    app.register_blueprint(customers_bp, url_prefix='/customers')

    from app.routes.suppliers import bp as suppliers_bp
    app.register_blueprint(suppliers_bp, url_prefix='/suppliers')

    from app.routes.reports import bp as reports_bp
    app.register_blueprint(reports_bp, url_prefix='/reports')

    from app.routes.settings import bp as settings_bp
    app.register_blueprint(settings_bp, url_prefix='/settings')

    # Register feature module blueprints
    from app.routes.features import bp as features_bp
    app.register_blueprint(features_bp, url_prefix='/features')

    from app.routes.expenses import bp as expenses_bp
    app.register_blueprint(expenses_bp, url_prefix='/expenses')

    from app.routes.promotions import bp as promotions_bp
    app.register_blueprint(promotions_bp, url_prefix='/promotions')

    from app.routes.notifications import bp as notifications_bp
    app.register_blueprint(notifications_bp, url_prefix='/notifications')

    from app.routes.quotations import bp as quotations_bp
    app.register_blueprint(quotations_bp, url_prefix='/quotations')

    from app.routes.returns import bp as returns_bp
    app.register_blueprint(returns_bp, url_prefix='/returns')

    # Register multi-kiosk support blueprints
    from app.routes.locations import bp as locations_bp
    app.register_blueprint(locations_bp, url_prefix='/locations')

    from app.routes.transfers import bp as transfers_bp
    app.register_blueprint(transfers_bp, url_prefix='/transfers')

    from app.routes.warehouse import bp as warehouse_bp
    app.register_blueprint(warehouse_bp, url_prefix='/warehouse')

    # Register main routes
    @app.route('/')
    def index():
        """Redirect to dashboard or login"""
        from flask_login import current_user
        from datetime import datetime
        from app.models import Product, Sale, LocationStock, Location
        if current_user.is_authenticated:
            # Get location context
            user_location = None
            if current_user.location_id:
                user_location = Location.query.get(current_user.location_id)

            today = datetime.now().date()

            # Filter data based on user's location access
            if current_user.is_global_admin:
                # Global admin sees all data
                products = Product.query.filter_by(is_active=True).all()
                today_sales = Sale.query.filter(
                    db.func.date(Sale.created_at) == today
                ).all()
            elif user_location:
                # Store manager/user sees only their location's data
                location_stock = LocationStock.query.filter_by(
                    location_id=user_location.id
                ).all()
                product_ids = [ls.product_id for ls in location_stock]
                products = Product.query.filter(
                    Product.id.in_(product_ids) if product_ids else False,
                    Product.is_active == True
                ).all()
                # Sales for this location today
                today_sales = Sale.query.filter(
                    db.func.date(Sale.created_at) == today,
                    Sale.location_id == user_location.id
                ).all()
            else:
                products = []
                today_sales = []

            # Calculate today's stats
            today_total = sum(s.total_amount for s in today_sales)
            today_count = len(today_sales)

            return render_template('dashboard.html',
                                   now=datetime.now(),
                                   products=products,
                                   user_location=user_location,
                                   today_sales_amount=today_total,
                                   today_sales_count=today_count)
        return render_template('index.html')

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    # Context processors
    @app.context_processor
    def utility_processor():
        """Make utility functions available to all templates"""
        def format_currency(amount):
            """Format amount as currency"""
            symbol = app.config.get('CURRENCY_SYMBOL', 'Rs.')
            return f"{symbol} {amount:,.2f}"

        def format_datetime(dt):
            """Format datetime"""
            if dt:
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            return ''

        def format_date(dt):
            """Format date"""
            if dt:
                return dt.strftime('%Y-%m-%d')
            return ''

        # Import feature flag helper
        from app.utils.feature_flags import is_feature_enabled, get_enabled_features

        # Get current location for templates
        from flask import g
        current_location = getattr(g, 'current_location', None)
        user_locations = getattr(g, 'user_locations', [])
        is_global_admin = getattr(g, 'is_global_admin', False)

        return dict(
            format_currency=format_currency,
            format_datetime=format_datetime,
            format_date=format_date,
            business_name=app.config.get('BUSINESS_NAME', 'Sunnat Collection'),
            is_feature_enabled=is_feature_enabled,
            enabled_features=get_enabled_features(),
            # Multi-kiosk support
            current_location=current_location,
            user_locations=user_locations,
            is_global_admin=is_global_admin
        )

    # Request hooks
    @app.before_request
    def before_request():
        """Actions to perform before each request"""
        from flask import session, g
        from flask_login import current_user
        from datetime import datetime
        session.permanent = True

        # Set location context for multi-kiosk support
        if current_user.is_authenticated:
            from app.utils.location_context import set_location_context
            set_location_context()

    return app
