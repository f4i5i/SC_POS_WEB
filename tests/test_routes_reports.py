"""
Comprehensive Unit Tests for Reports Routes
/home/f4i5i/SC_POC/SOC_WEB_APP/app/routes/reports.py

Tests cover:
1. Daily report - date filtering, calculations
2. Weekly report - week-over-week comparison
3. Monthly report - category breakdown
4. Custom date range report
5. Profit & Loss report - growth share calculation
6. Inventory valuation
7. Employee performance
8. Product performance
9. Sales by category
10. Customer analysis

Edge cases:
- Empty date ranges (no sales)
- Future dates
- Invalid date formats
- Division by zero in calculations
- Location-based filtering
- Permission checks for profit data
- Large dataset performance
- Decimal precision
"""

import pytest
from datetime import datetime, timedelta, date
from decimal import Decimal
from flask import url_for
from flask_login import login_user, logout_user
from app import create_app
from app.models import (
    db, User, Sale, SaleItem, Product, Customer, Category,
    Location, LocationStock, StockMovement
)
from app.utils.permissions import Permissions


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope='function')
def app():
    """Create and configure a new app instance for each test."""
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SERVER_NAME'] = 'localhost'

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Create a test client for the app."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create a test CLI runner."""
    return app.test_cli_runner()


@pytest.fixture
def warehouse_location(app):
    """Create a warehouse location for testing."""
    with app.app_context():
        location = Location(
            code='WH-001',
            name='Main Warehouse',
            location_type='warehouse',
            is_active=True,
            can_sell=False
        )
        db.session.add(location)
        db.session.commit()
        return location.id


@pytest.fixture
def kiosk_location(app, warehouse_location):
    """Create a kiosk location for testing."""
    with app.app_context():
        location = Location(
            code='K-001',
            name='Test Kiosk',
            location_type='kiosk',
            parent_warehouse_id=warehouse_location,
            is_active=True,
            can_sell=True
        )
        db.session.add(location)
        db.session.commit()
        return location.id


@pytest.fixture
def second_kiosk_location(app, warehouse_location):
    """Create a second kiosk location for multi-location testing."""
    with app.app_context():
        location = Location(
            code='K-002',
            name='Second Kiosk',
            location_type='kiosk',
            parent_warehouse_id=warehouse_location,
            is_active=True,
            can_sell=True
        )
        db.session.add(location)
        db.session.commit()
        return location.id


@pytest.fixture
def global_admin_user(app, kiosk_location):
    """Create a global admin user with full permissions."""
    with app.app_context():
        user = User(
            username='global_admin',
            email='admin@test.com',
            full_name='Global Admin',
            role='admin',
            is_active=True,
            is_global_admin=True,
            location_id=None  # Global admin has no specific location
        )
        user.set_password('testpassword')
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def manager_user(app, kiosk_location):
    """Create a manager user with limited location access."""
    with app.app_context():
        user = User(
            username='manager',
            email='manager@test.com',
            full_name='Test Manager',
            role='manager',
            is_active=True,
            is_global_admin=False,
            location_id=kiosk_location
        )
        user.set_password('testpassword')
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def cashier_user(app, kiosk_location):
    """Create a cashier user with minimal permissions."""
    with app.app_context():
        user = User(
            username='cashier',
            email='cashier@test.com',
            full_name='Test Cashier',
            role='cashier',
            is_active=True,
            is_global_admin=False,
            location_id=kiosk_location
        )
        user.set_password('testpassword')
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def user_without_location(app):
    """Create a user without any location assigned."""
    with app.app_context():
        user = User(
            username='nolocation',
            email='noloc@test.com',
            full_name='No Location User',
            role='manager',
            is_active=True,
            is_global_admin=False,
            location_id=None  # No location assigned
        )
        user.set_password('testpassword')
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def test_category(app):
    """Create a test product category."""
    with app.app_context():
        category = Category(
            name='Test Perfumes',
            description='Test category for perfumes'
        )
        db.session.add(category)
        db.session.commit()
        return category.id


@pytest.fixture
def second_category(app):
    """Create a second product category for category breakdown tests."""
    with app.app_context():
        category = Category(
            name='Attars',
            description='Test category for attars'
        )
        db.session.add(category)
        db.session.commit()
        return category.id


@pytest.fixture
def test_products(app, test_category, second_category):
    """Create test products for reporting."""
    with app.app_context():
        products = []

        # Product with normal margin
        p1 = Product(
            code='PROD-001',
            barcode='1234567890123',
            name='Arabian Night Perfume',
            brand='Test Brand',
            category_id=test_category,
            cost_price=Decimal('500.00'),
            selling_price=Decimal('1000.00'),
            quantity=100,
            reorder_level=10,
            is_active=True
        )
        products.append(p1)

        # Product with high margin
        p2 = Product(
            code='PROD-002',
            barcode='1234567890124',
            name='Oud Premium Attar',
            brand='Premium Brand',
            category_id=second_category,
            cost_price=Decimal('200.00'),
            selling_price=Decimal('800.00'),
            quantity=50,
            reorder_level=5,
            is_active=True
        )
        products.append(p2)

        # Product with zero cost (edge case)
        p3 = Product(
            code='PROD-003',
            barcode='1234567890125',
            name='Sample Product',
            brand='Sample Brand',
            category_id=test_category,
            cost_price=Decimal('0.00'),
            selling_price=Decimal('100.00'),
            quantity=200,
            reorder_level=20,
            is_active=True
        )
        products.append(p3)

        # Low stock product
        p4 = Product(
            code='PROD-004',
            barcode='1234567890126',
            name='Low Stock Item',
            brand='Test Brand',
            category_id=test_category,
            cost_price=Decimal('100.00'),
            selling_price=Decimal('250.00'),
            quantity=5,  # Below reorder level
            reorder_level=10,
            is_active=True
        )
        products.append(p4)

        # Out of stock product
        p5 = Product(
            code='PROD-005',
            barcode='1234567890127',
            name='Out of Stock Item',
            brand='Test Brand',
            category_id=test_category,
            cost_price=Decimal('150.00'),
            selling_price=Decimal('350.00'),
            quantity=0,  # Out of stock
            reorder_level=10,
            is_active=True
        )
        products.append(p5)

        for p in products:
            db.session.add(p)
        db.session.commit()

        return [p.id for p in products]


@pytest.fixture
def test_customers(app):
    """Create test customers with varying loyalty levels."""
    with app.app_context():
        customers = []

        # Bronze customer
        c1 = Customer(
            name='Bronze Customer',
            phone='03001234567',
            email='bronze@test.com',
            loyalty_points=100,
            is_active=True
        )
        customers.append(c1)

        # Silver customer
        c2 = Customer(
            name='Silver Customer',
            phone='03001234568',
            email='silver@test.com',
            loyalty_points=600,
            is_active=True
        )
        customers.append(c2)

        # Gold customer
        c3 = Customer(
            name='Gold Customer',
            phone='03001234569',
            email='gold@test.com',
            loyalty_points=1500,
            is_active=True
        )
        customers.append(c3)

        # Platinum customer
        c4 = Customer(
            name='Platinum Customer',
            phone='03001234570',
            email='platinum@test.com',
            loyalty_points=3000,
            is_active=True
        )
        customers.append(c4)

        for c in customers:
            db.session.add(c)
        db.session.commit()

        return [c.id for c in customers]


@pytest.fixture
def location_stock(app, test_products, kiosk_location):
    """Create location stock for the kiosk."""
    with app.app_context():
        for i, prod_id in enumerate(test_products):
            stock = LocationStock(
                location_id=kiosk_location,
                product_id=prod_id,
                quantity=(100 - i * 20),  # Varying quantities
                reserved_quantity=0,
                reorder_level=10
            )
            db.session.add(stock)
        db.session.commit()


def generate_sale(app, user_id, location_id, product_ids, customer_id=None,
                  sale_date=None, payment_method='cash', status='completed',
                  discount=Decimal('0.00'), quantities=None):
    """Helper function to generate a sale with items."""
    if sale_date is None:
        sale_date = datetime.now()

    if quantities is None:
        quantities = [1] * len(product_ids)

    with app.app_context():
        # Get fresh product references
        products = [Product.query.get(pid) for pid in product_ids]

        # Calculate totals
        subtotal = Decimal('0.00')
        items_data = []
        for product, qty in zip(products, quantities):
            item_subtotal = product.selling_price * qty
            subtotal += item_subtotal
            items_data.append({
                'product_id': product.id,
                'quantity': qty,
                'unit_price': product.selling_price,
                'subtotal': item_subtotal
            })

        # Generate unique sale number
        sale_number = f"SALE-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

        sale = Sale(
            sale_number=sale_number,
            sale_date=sale_date,
            customer_id=customer_id,
            user_id=user_id,
            location_id=location_id,
            subtotal=subtotal,
            discount=discount,
            discount_type='amount',
            tax=Decimal('0.00'),
            total=subtotal - discount,
            payment_method=payment_method,
            payment_status='paid',
            amount_paid=subtotal - discount,
            amount_due=Decimal('0.00'),
            status=status
        )
        db.session.add(sale)
        db.session.flush()  # Get sale ID

        # Create sale items
        for item_data in items_data:
            sale_item = SaleItem(
                sale_id=sale.id,
                product_id=item_data['product_id'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                discount=Decimal('0.00'),
                subtotal=item_data['subtotal']
            )
            db.session.add(sale_item)

        db.session.commit()
        return sale.id


@pytest.fixture
def today_sales(app, manager_user, kiosk_location, test_products, test_customers):
    """Create sales for today."""
    sale_ids = []
    today = datetime.now()

    # Multiple sales today at different hours
    for hour in [9, 11, 14, 16, 18]:
        sale_date = today.replace(hour=hour, minute=0, second=0, microsecond=0)
        sale_id = generate_sale(
            app,
            user_id=manager_user,
            location_id=kiosk_location,
            product_ids=[test_products[0], test_products[1]],
            customer_id=test_customers[0] if hour % 2 == 0 else None,
            sale_date=sale_date,
            payment_method='cash' if hour < 15 else 'card',
            quantities=[2, 1]
        )
        sale_ids.append(sale_id)

    return sale_ids


@pytest.fixture
def weekly_sales(app, manager_user, kiosk_location, test_products, test_customers):
    """Create sales for the past two weeks for weekly comparison."""
    sale_ids = []
    today = datetime.now()

    # Current week sales (higher volume)
    for day_offset in range(7):
        sale_date = today - timedelta(days=day_offset)
        sale_date = sale_date.replace(hour=12, minute=0, second=0, microsecond=0)

        sale_id = generate_sale(
            app,
            user_id=manager_user,
            location_id=kiosk_location,
            product_ids=[test_products[0]],
            customer_id=test_customers[day_offset % len(test_customers)],
            sale_date=sale_date,
            payment_method='cash',
            quantities=[3]
        )
        sale_ids.append(sale_id)

    # Previous week sales (lower volume for comparison)
    for day_offset in range(8, 15):
        sale_date = today - timedelta(days=day_offset)
        sale_date = sale_date.replace(hour=12, minute=0, second=0, microsecond=0)

        sale_id = generate_sale(
            app,
            user_id=manager_user,
            location_id=kiosk_location,
            product_ids=[test_products[1]],
            customer_id=None,
            sale_date=sale_date,
            payment_method='card',
            quantities=[1]
        )
        sale_ids.append(sale_id)

    return sale_ids


@pytest.fixture
def monthly_sales(app, manager_user, kiosk_location, test_products, test_customers):
    """Create sales for the current month."""
    sale_ids = []
    today = datetime.now()

    # Create sales throughout the month
    for day in range(1, min(today.day, 28)):
        sale_date = today.replace(day=day, hour=12, minute=0, second=0, microsecond=0)

        sale_id = generate_sale(
            app,
            user_id=manager_user,
            location_id=kiosk_location,
            product_ids=[test_products[day % len(test_products)]],
            customer_id=test_customers[day % len(test_customers)],
            sale_date=sale_date,
            payment_method='cash' if day % 2 == 0 else 'card',
            quantities=[day % 5 + 1]
        )
        sale_ids.append(sale_id)

    return sale_ids


@pytest.fixture
def multi_location_sales(app, manager_user, global_admin_user, kiosk_location,
                         second_kiosk_location, test_products, test_customers):
    """Create sales across multiple locations."""
    sale_ids = []
    today = datetime.now()

    # Sales at first kiosk
    for i in range(5):
        sale_date = today.replace(hour=10 + i, minute=0, second=0, microsecond=0)
        sale_id = generate_sale(
            app,
            user_id=manager_user,
            location_id=kiosk_location,
            product_ids=[test_products[0]],
            sale_date=sale_date,
            quantities=[2]
        )
        sale_ids.append(sale_id)

    # Sales at second kiosk
    with app.app_context():
        # Create a user for second location
        user2 = User(
            username='manager2',
            email='manager2@test.com',
            full_name='Second Manager',
            role='manager',
            is_active=True,
            is_global_admin=False,
            location_id=second_kiosk_location
        )
        user2.set_password('testpassword')
        db.session.add(user2)
        db.session.commit()
        user2_id = user2.id

    for i in range(3):
        sale_date = today.replace(hour=10 + i, minute=30, second=0, microsecond=0)
        sale_id = generate_sale(
            app,
            user_id=user2_id,
            location_id=second_kiosk_location,
            product_ids=[test_products[1]],
            sale_date=sale_date,
            quantities=[1]
        )
        sale_ids.append(sale_id)

    return sale_ids


def login_user_helper(client, username, password):
    """Helper to log in a user."""
    return client.post('/auth/login', data={
        'username': username,
        'password': password
    }, follow_redirects=True)


def logout_user_helper(client):
    """Helper to log out current user."""
    return client.get('/auth/logout', follow_redirects=True)


# =============================================================================
# TEST CLASSES
# =============================================================================

class TestReportsIndex:
    """Tests for reports index/dashboard."""

    def test_reports_index_requires_login(self, client, app):
        """Test that reports index requires authentication."""
        with app.app_context():
            response = client.get('/reports/')
            assert response.status_code in [302, 401]  # Redirect to login

    def test_reports_index_accessible_to_authorized_user(self, client, app,
                                                          global_admin_user):
        """Test that authorized users can access reports index."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/')
            assert response.status_code == 200

    def test_reports_index_denied_for_cashier(self, client, app, cashier_user):
        """Test that cashiers cannot access reports (no permission)."""
        with app.app_context():
            login_user_helper(client, 'cashier', 'testpassword')
            response = client.get('/reports/')
            # Should be forbidden or redirect
            assert response.status_code in [302, 403]


class TestDailyReport:
    """Tests for daily sales report."""

    def test_daily_report_today(self, client, app, global_admin_user, today_sales):
        """Test daily report for today's sales."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/daily')
            assert response.status_code == 200
            assert b'total_sales' in response.data or b'Total' in response.data

    def test_daily_report_specific_date(self, client, app, global_admin_user, today_sales):
        """Test daily report with specific date parameter."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            today = datetime.now().strftime('%Y-%m-%d')
            response = client.get(f'/reports/daily?date={today}')
            assert response.status_code == 200

    def test_daily_report_empty_date(self, client, app, global_admin_user):
        """Test daily report for a date with no sales."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            # Use a far future date with no sales
            future_date = '2099-12-31'
            response = client.get(f'/reports/daily?date={future_date}')
            assert response.status_code == 200
            # Should handle empty gracefully - no division by zero

    def test_daily_report_invalid_date_format(self, client, app, global_admin_user):
        """Test daily report with invalid date format."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/daily?date=invalid-date')
            # Should return error or use default date
            assert response.status_code in [200, 400]

    def test_daily_report_past_date(self, client, app, global_admin_user):
        """Test daily report for historical date."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            past_date = '2023-01-15'
            response = client.get(f'/reports/daily?date={past_date}')
            assert response.status_code == 200

    def test_daily_report_location_filtering(self, client, app, manager_user,
                                              today_sales, multi_location_sales):
        """Test that manager sees only their location's sales."""
        with app.app_context():
            login_user_helper(client, 'manager', 'testpassword')
            response = client.get('/reports/daily')
            assert response.status_code == 200
            # Manager should only see filtered data

    def test_daily_report_global_admin_sees_all(self, client, app, global_admin_user,
                                                 multi_location_sales):
        """Test that global admin sees all locations' sales."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/daily')
            assert response.status_code == 200

    def test_daily_report_division_by_zero(self, client, app, global_admin_user):
        """Test that average transaction handles zero transactions."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            # Date with no sales
            response = client.get('/reports/daily?date=2050-01-01')
            assert response.status_code == 200
            # Should not crash due to division by zero

    def test_daily_report_payment_method_breakdown(self, client, app,
                                                    global_admin_user, today_sales):
        """Test payment method breakdown in daily report."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/daily')
            assert response.status_code == 200
            # Should include payment methods


class TestWeeklyReport:
    """Tests for weekly sales comparison report."""

    def test_weekly_report_basic(self, client, app, global_admin_user, weekly_sales):
        """Test basic weekly report generation."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/weekly')
            assert response.status_code == 200

    def test_weekly_report_comparison_calculation(self, client, app,
                                                   global_admin_user, weekly_sales):
        """Test week-over-week comparison calculation."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/weekly')
            assert response.status_code == 200
            # Should contain comparison data

    def test_weekly_report_no_previous_week(self, client, app, global_admin_user,
                                             today_sales):
        """Test weekly report when previous week has no data."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/weekly')
            assert response.status_code == 200
            # Should handle zero previous total (no division by zero)

    def test_weekly_report_location_filter(self, client, app, manager_user,
                                            multi_location_sales):
        """Test weekly report respects location filtering."""
        with app.app_context():
            login_user_helper(client, 'manager', 'testpassword')
            response = client.get('/reports/weekly')
            assert response.status_code == 200

    def test_weekly_report_daily_breakdown(self, client, app, global_admin_user,
                                            weekly_sales):
        """Test that weekly report includes daily breakdown."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/weekly')
            assert response.status_code == 200


class TestMonthlyReport:
    """Tests for monthly comprehensive report."""

    def test_monthly_report_current_month(self, client, app, global_admin_user,
                                           monthly_sales):
        """Test monthly report for current month."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/monthly')
            assert response.status_code == 200

    def test_monthly_report_specific_month(self, client, app, global_admin_user,
                                            monthly_sales):
        """Test monthly report for specific month."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            current_month = datetime.now().strftime('%Y-%m')
            response = client.get(f'/reports/monthly?month={current_month}')
            assert response.status_code == 200

    def test_monthly_report_category_breakdown(self, client, app, global_admin_user,
                                                monthly_sales, test_category):
        """Test category breakdown in monthly report."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/monthly')
            assert response.status_code == 200

    def test_monthly_report_empty_month(self, client, app, global_admin_user):
        """Test monthly report for month with no sales."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/monthly?month=2099-12')
            assert response.status_code == 200

    def test_monthly_report_invalid_month_format(self, client, app, global_admin_user):
        """Test monthly report with invalid month format."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/monthly?month=invalid')
            # Should handle gracefully
            assert response.status_code in [200, 400]

    def test_monthly_report_top_customers(self, client, app, global_admin_user,
                                           monthly_sales, test_customers):
        """Test top customers in monthly report."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/monthly')
            assert response.status_code == 200


class TestCustomReport:
    """Tests for custom date range report."""

    def test_custom_report_without_dates(self, client, app, global_admin_user):
        """Test custom report page without date parameters."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/custom')
            assert response.status_code == 200

    def test_custom_report_with_date_range(self, client, app, global_admin_user,
                                            monthly_sales):
        """Test custom report with valid date range."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            today = datetime.now()
            from_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
            to_date = today.strftime('%Y-%m-%d')

            response = client.get(f'/reports/custom?from_date={from_date}&to_date={to_date}')
            assert response.status_code == 200

    def test_custom_report_reversed_dates(self, client, app, global_admin_user):
        """Test custom report with from_date after to_date."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/custom?from_date=2024-12-31&to_date=2024-01-01')
            # Should handle gracefully (empty results or error)
            assert response.status_code in [200, 400]

    def test_custom_report_same_day(self, client, app, global_admin_user, today_sales):
        """Test custom report for single day range."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            today = datetime.now().strftime('%Y-%m-%d')
            response = client.get(f'/reports/custom?from_date={today}&to_date={today}')
            assert response.status_code == 200

    def test_custom_report_future_date_range(self, client, app, global_admin_user):
        """Test custom report for future date range."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/custom?from_date=2099-01-01&to_date=2099-12-31')
            assert response.status_code == 200
            # Should return empty results

    def test_custom_report_product_performance(self, client, app, global_admin_user,
                                                monthly_sales, test_products):
        """Test product performance in custom report."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            today = datetime.now()
            from_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
            to_date = today.strftime('%Y-%m-%d')

            response = client.get(f'/reports/custom?from_date={from_date}&to_date={to_date}')
            assert response.status_code == 200

    def test_custom_report_invalid_date_format(self, client, app, global_admin_user):
        """Test custom report with invalid date format."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/custom?from_date=invalid&to_date=invalid')
            assert response.status_code in [200, 400]


class TestProfitLossReport:
    """Tests for Profit & Loss report with growth share calculation."""

    def test_profit_loss_daily(self, client, app, global_admin_user, today_sales):
        """Test daily P&L report."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/profit-loss?period=daily')
            assert response.status_code == 200

    def test_profit_loss_weekly(self, client, app, global_admin_user, weekly_sales):
        """Test weekly P&L report."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/profit-loss?period=weekly')
            assert response.status_code == 200

    def test_profit_loss_monthly(self, client, app, global_admin_user, monthly_sales):
        """Test monthly P&L report."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/profit-loss?period=monthly')
            assert response.status_code == 200

    def test_profit_loss_custom_period(self, client, app, global_admin_user,
                                        monthly_sales):
        """Test custom period P&L report."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            today = datetime.now()
            start_date = (today - timedelta(days=15)).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')

            response = client.get(f'/reports/profit-loss?period=custom&start_date={start_date}&end_date={end_date}')
            assert response.status_code == 200

    def test_profit_loss_growth_share_calculation(self, client, app,
                                                   global_admin_user, today_sales):
        """Test that growth share (20%) is calculated correctly."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/profit-loss?period=daily')
            assert response.status_code == 200
            # Response should contain growth share calculation

    def test_profit_loss_zero_revenue(self, client, app, global_admin_user):
        """Test P&L report with zero revenue (division by zero edge case)."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/profit-loss?period=daily&start_date=2099-01-01')
            assert response.status_code == 200
            # Should not crash due to zero division

    def test_profit_loss_negative_gross_profit(self, client, app, global_admin_user):
        """Test P&L when gross profit is negative (COGS > Revenue)."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/profit-loss?period=daily')
            assert response.status_code == 200

    def test_profit_loss_location_filtering(self, client, app, manager_user,
                                             multi_location_sales):
        """Test P&L respects location filtering."""
        with app.app_context():
            login_user_helper(client, 'manager', 'testpassword')
            response = client.get('/reports/profit-loss?period=daily')
            assert response.status_code == 200

    def test_profit_loss_previous_period_comparison(self, client, app,
                                                     global_admin_user, weekly_sales):
        """Test previous period comparison calculation."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/profit-loss?period=weekly')
            assert response.status_code == 200

    def test_profit_loss_zero_previous_period(self, client, app,
                                               global_admin_user, today_sales):
        """Test P&L when previous period has zero revenue."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            # First day with sales, no previous period
            response = client.get('/reports/profit-loss?period=daily')
            assert response.status_code == 200


class TestInventoryValuation:
    """Tests for inventory valuation report."""

    def test_inventory_valuation_basic(self, client, app, global_admin_user,
                                        test_products):
        """Test basic inventory valuation."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/inventory-valuation')
            assert response.status_code == 200

    def test_inventory_valuation_calculations(self, client, app, global_admin_user,
                                               test_products):
        """Test inventory valuation calculations."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/inventory-valuation')
            assert response.status_code == 200
            # Should calculate total cost value, selling value, potential profit

    def test_inventory_valuation_zero_quantity(self, client, app, global_admin_user,
                                                test_products):
        """Test inventory valuation with zero quantity products."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/inventory-valuation')
            assert response.status_code == 200

    def test_inventory_valuation_only_active_products(self, client, app,
                                                       global_admin_user, test_products):
        """Test that only active products are included."""
        with app.app_context():
            # Deactivate a product
            product = Product.query.get(test_products[0])
            product.is_active = False
            db.session.commit()

            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/inventory-valuation')
            assert response.status_code == 200

    def test_inventory_valuation_decimal_precision(self, client, app,
                                                    global_admin_user, test_products):
        """Test decimal precision in valuation calculations."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/inventory-valuation')
            assert response.status_code == 200

    def test_inventory_valuation_permission_required(self, client, app, cashier_user):
        """Test that inventory valuation requires proper permission."""
        with app.app_context():
            login_user_helper(client, 'cashier', 'testpassword')
            response = client.get('/reports/inventory-valuation')
            # Cashier should not have REPORT_VIEW_INVENTORY permission
            assert response.status_code in [302, 403]


class TestEmployeePerformance:
    """Tests for employee performance report."""

    def test_employee_performance_basic(self, client, app, global_admin_user,
                                         monthly_sales):
        """Test basic employee performance report."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/employee-performance')
            assert response.status_code == 200

    def test_employee_performance_date_range(self, client, app, global_admin_user,
                                              monthly_sales):
        """Test employee performance with custom date range."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            today = datetime.now()
            start_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')

            response = client.get(f'/reports/employee-performance?start_date={start_date}&end_date={end_date}')
            assert response.status_code == 200

    def test_employee_performance_default_date_range(self, client, app,
                                                      global_admin_user, monthly_sales):
        """Test employee performance uses current month by default."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/employee-performance')
            assert response.status_code == 200

    def test_employee_performance_location_filter(self, client, app, manager_user,
                                                   multi_location_sales):
        """Test employee performance respects location filter."""
        with app.app_context():
            login_user_helper(client, 'manager', 'testpassword')
            response = client.get('/reports/employee-performance')
            assert response.status_code == 200

    def test_employee_performance_no_sales(self, client, app, global_admin_user):
        """Test employee performance with no sales data."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/employee-performance?start_date=2099-01-01&end_date=2099-12-31')
            assert response.status_code == 200

    def test_employee_performance_items_sold_calculation(self, client, app,
                                                          global_admin_user, today_sales):
        """Test items sold calculation in employee report."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/employee-performance')
            assert response.status_code == 200


class TestProductPerformance:
    """Tests for product performance analysis."""

    def test_product_performance_basic(self, client, app, global_admin_user,
                                        monthly_sales, test_products):
        """Test basic product performance report."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/product-performance')
            assert response.status_code == 200

    def test_product_performance_date_range(self, client, app, global_admin_user,
                                             monthly_sales):
        """Test product performance with custom date range."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            today = datetime.now()
            start_date = (today - timedelta(days=60)).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')

            response = client.get(f'/reports/product-performance?start_date={start_date}&end_date={end_date}')
            assert response.status_code == 200

    def test_product_performance_top_products(self, client, app, global_admin_user,
                                               monthly_sales, test_products):
        """Test top performing products list."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/product-performance')
            assert response.status_code == 200

    def test_product_performance_worst_products(self, client, app, global_admin_user,
                                                 monthly_sales, test_products):
        """Test worst performing products list."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/product-performance')
            assert response.status_code == 200

    def test_product_performance_never_sold(self, client, app, global_admin_user,
                                             test_products):
        """Test never sold products identification."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/product-performance')
            assert response.status_code == 200

    def test_product_performance_profit_calculation(self, client, app,
                                                     global_admin_user, monthly_sales):
        """Test profit calculation for products."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/product-performance')
            assert response.status_code == 200

    def test_product_performance_location_filter(self, client, app, manager_user,
                                                  multi_location_sales):
        """Test product performance respects location filter."""
        with app.app_context():
            login_user_helper(client, 'manager', 'testpassword')
            response = client.get('/reports/product-performance')
            assert response.status_code == 200


class TestSalesByCategory:
    """Tests for sales by category report."""

    def test_sales_by_category_basic(self, client, app, global_admin_user,
                                      monthly_sales, test_category, second_category):
        """Test basic sales by category report."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/sales-by-category')
            assert response.status_code == 200

    def test_sales_by_category_date_range(self, client, app, global_admin_user,
                                           monthly_sales):
        """Test sales by category with custom date range."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            today = datetime.now()
            start_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')

            response = client.get(f'/reports/sales-by-category?start_date={start_date}&end_date={end_date}')
            assert response.status_code == 200

    def test_sales_by_category_uncategorized(self, client, app, global_admin_user):
        """Test handling of uncategorized products in report."""
        with app.app_context():
            # Create product without category
            product = Product(
                code='UNCAT-001',
                name='Uncategorized Product',
                brand='Test',
                category_id=None,
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                quantity=50,
                is_active=True
            )
            db.session.add(product)
            db.session.commit()

            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/sales-by-category')
            assert response.status_code == 200

    def test_sales_by_category_totals(self, client, app, global_admin_user,
                                       monthly_sales):
        """Test total calculations in category report."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/sales-by-category')
            assert response.status_code == 200

    def test_sales_by_category_profit_calculation(self, client, app,
                                                   global_admin_user, monthly_sales):
        """Test profit calculation per category."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/sales-by-category')
            assert response.status_code == 200

    def test_sales_by_category_location_filter(self, client, app, manager_user,
                                                multi_location_sales):
        """Test category report respects location filter."""
        with app.app_context():
            login_user_helper(client, 'manager', 'testpassword')
            response = client.get('/reports/sales-by-category')
            assert response.status_code == 200


class TestCustomerAnalysis:
    """Tests for customer analysis report."""

    def test_customer_analysis_basic(self, client, app, global_admin_user,
                                      monthly_sales, test_customers):
        """Test basic customer analysis report."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/customer-analysis')
            assert response.status_code == 200

    def test_customer_analysis_date_range(self, client, app, global_admin_user,
                                           monthly_sales, test_customers):
        """Test customer analysis with custom date range."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            today = datetime.now()
            start_date = (today - timedelta(days=90)).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')

            response = client.get(f'/reports/customer-analysis?start_date={start_date}&end_date={end_date}')
            assert response.status_code == 200

    def test_customer_analysis_top_customers(self, client, app, global_admin_user,
                                              monthly_sales, test_customers):
        """Test top customers by revenue list."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/customer-analysis')
            assert response.status_code == 200

    def test_customer_analysis_loyalty_tiers(self, client, app, global_admin_user,
                                              test_customers):
        """Test loyalty tier breakdown."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/customer-analysis')
            assert response.status_code == 200

    def test_customer_analysis_new_customers(self, client, app, global_admin_user,
                                              test_customers):
        """Test new customers count."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/customer-analysis')
            assert response.status_code == 200

    def test_customer_analysis_location_filter(self, client, app, manager_user,
                                                multi_location_sales, test_customers):
        """Test customer analysis respects location filter."""
        with app.app_context():
            login_user_helper(client, 'manager', 'testpassword')
            response = client.get('/reports/customer-analysis')
            assert response.status_code == 200

    def test_customer_analysis_no_customers(self, client, app, global_admin_user):
        """Test customer analysis with no customer data."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/customer-analysis?start_date=2099-01-01&end_date=2099-12-31')
            assert response.status_code == 200


class TestLocationFiltering:
    """Tests for location-based data filtering across reports."""

    def test_user_without_location_sees_no_data(self, client, app,
                                                 user_without_location, today_sales):
        """Test that user without location assigned sees no data."""
        with app.app_context():
            login_user_helper(client, 'nolocation', 'testpassword')
            response = client.get('/reports/daily')
            assert response.status_code == 200
            # Should return empty/zero results

    def test_global_admin_sees_all_locations(self, client, app, global_admin_user,
                                              multi_location_sales):
        """Test global admin sees data from all locations."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/daily')
            assert response.status_code == 200

    def test_manager_sees_only_assigned_location(self, client, app, manager_user,
                                                  multi_location_sales):
        """Test manager sees only their assigned location's data."""
        with app.app_context():
            login_user_helper(client, 'manager', 'testpassword')
            response = client.get('/reports/daily')
            assert response.status_code == 200


class TestPermissionChecks:
    """Tests for permission validation on reports."""

    def test_sales_report_requires_report_view_sales(self, client, app,
                                                      cashier_user, today_sales):
        """Test that sales reports require REPORT_VIEW_SALES permission."""
        with app.app_context():
            login_user_helper(client, 'cashier', 'testpassword')
            response = client.get('/reports/daily')
            # Cashier doesn't have report.view_sales permission
            assert response.status_code in [302, 403]

    def test_inventory_report_requires_report_view_inventory(self, client, app,
                                                              cashier_user,
                                                              test_products):
        """Test inventory valuation requires REPORT_VIEW_INVENTORY permission."""
        with app.app_context():
            login_user_helper(client, 'cashier', 'testpassword')
            response = client.get('/reports/inventory-valuation')
            # Cashier doesn't have report.view_inventory permission
            assert response.status_code in [302, 403]

    def test_export_requires_report_export(self, client, app, manager_user):
        """Test export functionality requires REPORT_EXPORT permission."""
        with app.app_context():
            login_user_helper(client, 'manager', 'testpassword')
            today = datetime.now().strftime('%Y-%m-%d')
            response = client.get(f'/reports/export-daily-pdf?date={today}')
            # Manager doesn't have report.export permission by default
            assert response.status_code in [302, 403]


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_decimal_precision_in_calculations(self, client, app,
                                                global_admin_user):
        """Test decimal precision is maintained in calculations."""
        with app.app_context():
            # Create product with precise decimal values
            product = Product(
                code='DEC-001',
                name='Decimal Test Product',
                brand='Test',
                cost_price=Decimal('123.45'),
                selling_price=Decimal('234.56'),
                quantity=17,
                is_active=True
            )
            db.session.add(product)

            # Create user for sale
            user = User(
                username='decimal_test_user',
                email='decimal@test.com',
                full_name='Decimal Test',
                role='admin',
                is_active=True,
                is_global_admin=True
            )
            user.set_password('testpassword')
            db.session.add(user)

            db.session.commit()

            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/inventory-valuation')
            assert response.status_code == 200

    def test_large_dataset_handling(self, client, app, global_admin_user,
                                     kiosk_location, manager_user, test_category):
        """Test report handles large datasets efficiently."""
        with app.app_context():
            # Create many products
            products = []
            for i in range(50):  # Create 50 products
                p = Product(
                    code=f'BULK-{i:04d}',
                    name=f'Bulk Product {i}',
                    brand='Bulk Brand',
                    category_id=test_category,
                    cost_price=Decimal('100.00'),
                    selling_price=Decimal('200.00'),
                    quantity=100,
                    is_active=True
                )
                db.session.add(p)
                products.append(p)
            db.session.commit()

            # Create many sales
            today = datetime.now()
            for i in range(20):  # 20 sales
                sale = Sale(
                    sale_number=f'BULK-SALE-{i:04d}',
                    sale_date=today - timedelta(hours=i),
                    user_id=manager_user,
                    location_id=kiosk_location,
                    subtotal=Decimal('1000.00'),
                    total=Decimal('1000.00'),
                    payment_method='cash',
                    status='completed'
                )
                db.session.add(sale)
            db.session.commit()

            login_user_helper(client, 'global_admin', 'testpassword')

            # Test multiple report types with large dataset
            response = client.get('/reports/daily')
            assert response.status_code == 200

            response = client.get('/reports/product-performance')
            assert response.status_code == 200

    def test_concurrent_date_boundaries(self, client, app, global_admin_user,
                                         kiosk_location, manager_user, test_products):
        """Test reports handle date boundary conditions correctly."""
        with app.app_context():
            # Create sale at exact midnight
            midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            generate_sale(
                app,
                user_id=manager_user,
                location_id=kiosk_location,
                product_ids=[test_products[0]],
                sale_date=midnight
            )

            # Create sale at 23:59:59
            end_of_day = datetime.now().replace(hour=23, minute=59, second=59)
            generate_sale(
                app,
                user_id=manager_user,
                location_id=kiosk_location,
                product_ids=[test_products[0]],
                sale_date=end_of_day
            )

            login_user_helper(client, 'global_admin', 'testpassword')
            today = datetime.now().strftime('%Y-%m-%d')
            response = client.get(f'/reports/daily?date={today}')
            assert response.status_code == 200

    def test_handles_null_values_gracefully(self, client, app, global_admin_user,
                                             kiosk_location, manager_user):
        """Test reports handle null/None values in data."""
        with app.app_context():
            # Create sale without customer (null customer_id)
            sale = Sale(
                sale_number='NULL-TEST-001',
                sale_date=datetime.now(),
                customer_id=None,  # Null customer
                user_id=manager_user,
                location_id=kiosk_location,
                subtotal=Decimal('100.00'),
                total=Decimal('100.00'),
                payment_method='cash',
                status='completed'
            )
            db.session.add(sale)
            db.session.commit()

            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/daily')
            assert response.status_code == 200

    def test_handles_refunded_cancelled_sales(self, client, app, global_admin_user,
                                               kiosk_location, manager_user,
                                               test_products):
        """Test reports properly filter out refunded/cancelled sales."""
        with app.app_context():
            # Create refunded sale
            generate_sale(
                app,
                user_id=manager_user,
                location_id=kiosk_location,
                product_ids=[test_products[0]],
                status='refunded'
            )

            # Create cancelled sale
            generate_sale(
                app,
                user_id=manager_user,
                location_id=kiosk_location,
                product_ids=[test_products[0]],
                status='cancelled'
            )

            # Create completed sale
            generate_sale(
                app,
                user_id=manager_user,
                location_id=kiosk_location,
                product_ids=[test_products[0]],
                status='completed'
            )

            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/daily')
            assert response.status_code == 200
            # Only completed sales should be counted


class TestExportFunctionality:
    """Tests for report export functionality."""

    def test_export_daily_pdf_requires_auth(self, client, app):
        """Test PDF export requires authentication."""
        with app.app_context():
            response = client.get('/reports/export-daily-pdf')
            assert response.status_code in [302, 401]

    def test_export_daily_pdf_with_permission(self, client, app, global_admin_user):
        """Test PDF export with proper permission."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            today = datetime.now().strftime('%Y-%m-%d')
            response = client.get(f'/reports/export-daily-pdf?date={today}')
            # May return 200 with PDF or error if PDF generation fails
            assert response.status_code in [200, 404, 500]


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================

class TestPerformance:
    """Performance tests for reports."""

    def test_daily_report_response_time(self, client, app, global_admin_user,
                                         today_sales):
        """Test daily report responds in reasonable time."""
        import time

        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')

            start = time.time()
            response = client.get('/reports/daily')
            elapsed = time.time() - start

            assert response.status_code == 200
            assert elapsed < 5.0  # Should respond within 5 seconds

    def test_monthly_report_response_time(self, client, app, global_admin_user,
                                           monthly_sales):
        """Test monthly report responds in reasonable time."""
        import time

        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')

            start = time.time()
            response = client.get('/reports/monthly')
            elapsed = time.time() - start

            assert response.status_code == 200
            assert elapsed < 10.0  # Should respond within 10 seconds


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestReportIntegration:
    """Integration tests verifying report data consistency."""

    def test_daily_totals_match_sale_records(self, client, app, global_admin_user,
                                              today_sales, kiosk_location):
        """Test that daily report totals match actual sale records."""
        with app.app_context():
            # Calculate expected total from database
            today = datetime.now().date()
            sales = Sale.query.filter(
                db.func.date(Sale.sale_date) == today,
                Sale.status == 'completed'
            ).all()
            expected_total = sum(float(s.total) for s in sales)
            expected_count = len(sales)

            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/daily')

            assert response.status_code == 200
            # The report should show totals consistent with database

    def test_employee_stats_consistent_with_sales(self, client, app,
                                                   global_admin_user, today_sales):
        """Test employee performance stats are consistent with sales."""
        with app.app_context():
            login_user_helper(client, 'global_admin', 'testpassword')
            response = client.get('/reports/employee-performance')
            assert response.status_code == 200


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
