"""
Flask Application Factory
Initializes and configures the Flask application
"""

import os
import secrets
from flask import Flask, render_template, request, redirect, flash
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from config import config
from app.models import db, User

# Import extended models for database migrations
from app import models_extended

# Initialize extensions
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()

# Try to import Flask-Limiter for rate limiting
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])
    LIMITER_AVAILABLE = True
except ImportError:
    limiter = None
    LIMITER_AVAILABLE = False


def create_app(config_name='default'):
    """
    Application factory pattern
    Creates and configures Flask application
    """
    app = Flask(__name__)

    # Load configuration
    app.config.from_object(config[config_name])

    # Validate secret key in production
    if config_name == 'production':
        if not app.config.get('SECRET_KEY') or app.config['SECRET_KEY'] == 'dev-secret-key-change-in-production':
            raise ValueError("Production requires a secure SECRET_KEY. Set it via environment variable.")
        if len(app.config['SECRET_KEY']) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters for production.")

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # Initialize rate limiter if available
    if LIMITER_AVAILABLE and limiter:
        limiter.init_app(app)

    # Initialize cache if available
    try:
        from app.utils.cache import init_cache
        init_cache(app)
    except Exception as e:
        app.logger.warning(f"Cache initialization failed: {e}")

    # Initialize Sentry if configured
    if app.config.get('SENTRY_DSN'):
        try:
            import sentry_sdk
            from sentry_sdk.integrations.flask import FlaskIntegration
            sentry_sdk.init(
                dsn=app.config['SENTRY_DSN'],
                integrations=[FlaskIntegration()],
                traces_sample_rate=0.1,
                environment=config_name
            )
            app.logger.info("Sentry error tracking initialized")
        except ImportError:
            app.logger.warning("sentry-sdk not installed. Error tracking disabled.")

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

    from app.routes.production import bp as production_bp
    app.register_blueprint(production_bp, url_prefix='/production')

    from app.routes.receipts import bp as receipts_bp
    app.register_blueprint(receipts_bp, url_prefix='/receipts')

    from app.routes.loyalty import bp as loyalty_bp
    app.register_blueprint(loyalty_bp, url_prefix='/loyalty')

    from app.routes.marketing import bp as marketing_bp
    app.register_blueprint(marketing_bp, url_prefix='/marketing')

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
            today_total = sum((s.total or 0) for s in today_sales)
            today_count = len(today_sales)

            # Get low stock alerts for user's location
            low_stock_alerts = []
            stock_summary = None
            if user_location:
                try:
                    from app.utils.inventory_forecast import get_low_stock_alerts, get_location_stock_summary
                    low_stock_alerts = get_low_stock_alerts(user_location.id, include_forecasting=True)[:10]  # Top 10 alerts
                    stock_summary = get_location_stock_summary(user_location.id)
                except Exception as e:
                    app.logger.error(f"Error getting stock alerts: {e}")

            return render_template('dashboard.html',
                                   now=datetime.now(),
                                   products=products,
                                   user_location=user_location,
                                   today_sales_amount=today_total,
                                   today_sales_count=today_count,
                                   low_stock_alerts=low_stock_alerts,
                                   stock_summary=stock_summary)
        return render_template('index.html')

    @app.route('/api/dashboard/chart-data')
    def dashboard_chart_data():
        """API endpoint for dashboard charts data"""
        from flask_login import current_user
        from flask import jsonify
        from datetime import datetime, timedelta
        from app.models import Sale, SaleItem, Product, Location
        from sqlalchemy import func

        if not current_user.is_authenticated:
            return jsonify({'error': 'Unauthorized'}), 401

        # Get location context
        location_id = current_user.location_id

        # Get sales data for last 7 days
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=6)

        # Build base query
        sales_query = db.session.query(
            func.date(Sale.created_at).label('date'),
            func.sum(Sale.total).label('total'),
            func.count(Sale.id).label('count')
        ).filter(
            func.date(Sale.created_at) >= start_date,
            func.date(Sale.created_at) <= end_date
        )

        if location_id and not current_user.is_global_admin:
            sales_query = sales_query.filter(Sale.location_id == location_id)

        sales_by_day = sales_query.group_by(func.date(Sale.created_at)).all()

        # Build daily data
        daily_labels = []
        daily_sales = []
        daily_counts = []

        for i in range(7):
            day = start_date + timedelta(days=i)
            daily_labels.append(day.strftime('%a'))  # Mon, Tue, etc.
            day_sale = next((s for s in sales_by_day if s.date == day), None)
            daily_sales.append(float(day_sale.total) if day_sale and day_sale.total else 0)
            daily_counts.append(int(day_sale.count) if day_sale else 0)

        # Payment methods breakdown (today)
        payment_query = db.session.query(
            Sale.payment_method,
            func.sum(Sale.total).label('total')
        ).filter(
            func.date(Sale.created_at) == end_date
        )

        if location_id and not current_user.is_global_admin:
            payment_query = payment_query.filter(Sale.location_id == location_id)

        payment_data = payment_query.group_by(Sale.payment_method).all()

        payment_labels = []
        payment_values = []
        for p in payment_data:
            label = (p.payment_method or 'Cash').title()
            payment_labels.append(label)
            payment_values.append(float(p.total) if p.total else 0)

        # If no sales today, show placeholder
        if not payment_labels:
            payment_labels = ['No Sales']
            payment_values = [0]

        # Top 5 products (last 7 days)
        top_products_query = db.session.query(
            Product.name,
            func.sum(SaleItem.quantity).label('qty')
        ).join(SaleItem.product).join(SaleItem.sale).filter(
            func.date(Sale.created_at) >= start_date
        )

        if location_id and not current_user.is_global_admin:
            top_products_query = top_products_query.filter(Sale.location_id == location_id)

        top_products = top_products_query.group_by(Product.id).order_by(
            func.sum(SaleItem.quantity).desc()
        ).limit(5).all()

        top_product_labels = [p.name[:15] + '...' if len(p.name) > 15 else p.name for p in top_products]
        top_product_values = [int(p.qty) for p in top_products]

        # If no products sold, show placeholder
        if not top_product_labels:
            top_product_labels = ['No Sales']
            top_product_values = [0]

        return jsonify({
            'salesTrend': {
                'labels': daily_labels,
                'sales': daily_sales,
                'counts': daily_counts
            },
            'paymentMethods': {
                'labels': payment_labels,
                'values': payment_values
            },
            'topProducts': {
                'labels': top_product_labels,
                'values': top_product_values
            }
        })

    # API Documentation route
    @app.route('/api/docs')
    def api_docs():
        """Serve API documentation with Swagger UI"""
        return render_template('api_docs.html')

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    # CSRF error handler - returns JSON for API calls
    from flask_wtf.csrf import CSRFError
    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        from flask import jsonify, request
        # Return JSON for AJAX/API requests
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or '/api/' in request.path:
            return jsonify({
                'error': 'CSRF token missing or invalid',
                'message': 'Please refresh the page and try again'
            }), 400
        # Flash message and redirect for regular requests
        flash('Session expired. Please try again.', 'warning')
        return redirect(request.url)

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

    @app.after_request
    def add_security_headers(response):
        """Add security headers to all responses"""
        # Content Security Policy - Allow same-origin and common CDNs
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self';"
        )
        response.headers['Content-Security-Policy'] = csp

        # Prevent clickjacking
        response.headers['X-Frame-Options'] = 'DENY'

        # Prevent MIME type sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'

        # Enable XSS filter
        response.headers['X-XSS-Protection'] = '1; mode=block'

        # Referrer policy
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # Permissions policy (formerly feature policy)
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'

        return response

    return app
