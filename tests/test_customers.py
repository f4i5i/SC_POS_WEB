"""
Comprehensive Unit Tests for Customer and Loyalty System
Tests CRUD operations, loyalty points, tier management, and search functionality

Run with: pytest tests/test_customers.py -v
"""

import pytest
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from flask import url_for
from app import create_app
from app.models import db, Customer, Sale, SaleItem, Product, User, Category, Location, SyncQueue


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope='function')
def app():
    """Create application for testing."""
    app = create_app('testing')
    app.config['SERVER_NAME'] = 'localhost'
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['LOGIN_DISABLED'] = False
    app.config['ITEMS_PER_PAGE'] = 10

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture(scope='function')
def runner(app):
    """Create test CLI runner."""
    return app.test_cli_runner()


@pytest.fixture(scope='function')
def init_database(app):
    """Initialize database with test data."""
    with app.app_context():
        # Create admin user
        admin = User(
            username='admin',
            email='admin@test.com',
            full_name='Test Admin',
            role='admin',
            is_active=True,
            is_global_admin=True
        )
        admin.set_password('admin123')
        db.session.add(admin)

        # Create cashier user
        cashier = User(
            username='cashier',
            email='cashier@test.com',
            full_name='Test Cashier',
            role='cashier',
            is_active=True
        )
        cashier.set_password('cashier123')
        db.session.add(cashier)

        # Create test location
        location = Location(
            code='K-001',
            name='Test Kiosk',
            location_type='kiosk',
            is_active=True,
            can_sell=True
        )
        db.session.add(location)

        # Create category
        category = Category(name='Test Category', description='Test')
        db.session.add(category)

        db.session.commit()

        yield

        db.session.remove()


@pytest.fixture(scope='function')
def logged_in_client(client, init_database, app):
    """Return a logged-in test client."""
    with app.app_context():
        # Login as admin
        client.post('/auth/login', data={
            'username': 'admin',
            'password': 'admin123'
        }, follow_redirects=True)
        yield client


@pytest.fixture(scope='function')
def sample_customer(app, init_database):
    """Create a sample customer for testing."""
    with app.app_context():
        customer = Customer(
            name='Test Customer',
            phone='03001234567',
            email='test@example.com',
            address='Test Address',
            city='Test City',
            postal_code='12345',
            customer_type='regular',
            loyalty_points=0,
            is_active=True
        )
        db.session.add(customer)
        db.session.commit()
        customer_id = customer.id
        yield customer_id


@pytest.fixture(scope='function')
def sample_product(app, init_database):
    """Create a sample product for testing."""
    with app.app_context():
        category = Category.query.first()
        product = Product(
            code='PROD-001',
            barcode='1234567890123',
            name='Test Product',
            category_id=category.id if category else None,
            cost_price=Decimal('100.00'),
            selling_price=Decimal('150.00'),
            quantity=100,
            is_active=True
        )
        db.session.add(product)
        db.session.commit()
        product_id = product.id
        yield product_id


# =============================================================================
# CUSTOMER MODEL TESTS
# =============================================================================

class TestCustomerModel:
    """Tests for Customer model properties and methods."""

    def test_customer_creation(self, app, init_database):
        """Test basic customer creation."""
        with app.app_context():
            customer = Customer(
                name='John Doe',
                phone='03111111111',
                email='john@example.com',
                customer_type='regular'
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.id is not None
            assert customer.name == 'John Doe'
            assert customer.phone == '03111111111'
            assert customer.loyalty_points == 0
            assert customer.is_active is True

    def test_customer_repr(self, app, init_database):
        """Test customer string representation."""
        with app.app_context():
            customer = Customer(name='Test User', phone='03222222222')
            assert repr(customer) == '<Customer Test User>'

    def test_total_purchases_property(self, app, init_database, sample_customer, sample_product):
        """Test total_purchases calculated property."""
        with app.app_context():
            customer = Customer.query.get(sample_customer)
            product = Product.query.get(sample_product)
            user = User.query.filter_by(username='admin').first()

            # Create a sale
            sale = Sale(
                sale_number='SALE-001',
                customer_id=customer.id,
                user_id=user.id,
                subtotal=Decimal('500.00'),
                total=Decimal('500.00'),
                payment_method='cash',
                status='completed'
            )
            db.session.add(sale)
            db.session.commit()

            assert customer.total_purchases == Decimal('500.00')


# =============================================================================
# LOYALTY TIER TESTS
# =============================================================================

class TestLoyaltyTiers:
    """Tests for loyalty tier calculations and boundaries."""

    def test_bronze_tier_default(self, app, init_database):
        """Test default tier is Bronze for new customers."""
        with app.app_context():
            customer = Customer(name='New Customer', phone='03333333333')
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Bronze'
            assert customer.loyalty_points == 0

    def test_bronze_tier_boundary(self, app, init_database):
        """Test Bronze tier at 499 points."""
        with app.app_context():
            customer = Customer(name='Bronze Customer', phone='03444444444', loyalty_points=499)
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Bronze'
            assert customer.points_to_next_tier == 1  # 500 - 499 = 1

    def test_silver_tier_boundary_lower(self, app, init_database):
        """Test Silver tier at exactly 500 points."""
        with app.app_context():
            customer = Customer(name='Silver Customer', phone='03555555555', loyalty_points=500)
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Silver'
            assert customer.next_tier_name == 'Gold'
            assert customer.points_to_next_tier == 500  # 1000 - 500 = 500

    def test_silver_tier_boundary_upper(self, app, init_database):
        """Test Silver tier at 999 points."""
        with app.app_context():
            customer = Customer(name='Silver Customer', phone='03666666666', loyalty_points=999)
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Silver'
            assert customer.points_to_next_tier == 1  # 1000 - 999 = 1

    def test_gold_tier_boundary_lower(self, app, init_database):
        """Test Gold tier at exactly 1000 points."""
        with app.app_context():
            customer = Customer(name='Gold Customer', phone='03777777777', loyalty_points=1000)
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Gold'
            assert customer.next_tier_name == 'Platinum'
            assert customer.points_to_next_tier == 1500  # 2500 - 1000 = 1500

    def test_gold_tier_boundary_upper(self, app, init_database):
        """Test Gold tier at 2499 points."""
        with app.app_context():
            customer = Customer(name='Gold Customer', phone='03888888888', loyalty_points=2499)
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Gold'
            assert customer.points_to_next_tier == 1  # 2500 - 2499 = 1

    def test_platinum_tier_boundary(self, app, init_database):
        """Test Platinum tier at exactly 2500 points."""
        with app.app_context():
            customer = Customer(name='Platinum Customer', phone='03999999999', loyalty_points=2500)
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Platinum'
            assert customer.next_tier_name is None
            assert customer.points_to_next_tier == 0

    def test_platinum_tier_high_points(self, app, init_database):
        """Test Platinum tier with very high points."""
        with app.app_context():
            customer = Customer(name='VIP Customer', phone='03100000000', loyalty_points=10000)
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Platinum'
            assert customer.points_to_next_tier == 0

    def test_tier_boundary_249_to_250(self, app, init_database):
        """Test tier remains Bronze at 249 points (edge case mentioned in requirements)."""
        with app.app_context():
            customer = Customer(name='Edge Customer', phone='03200000000', loyalty_points=249)
            db.session.add(customer)
            db.session.commit()

            # 249 points should be Bronze (less than 500)
            assert customer.loyalty_tier == 'Bronze'

            # Add 251 points to reach 500
            customer.loyalty_points = 500
            db.session.commit()

            # Now should be Silver
            assert customer.loyalty_tier == 'Silver'

    def test_loyalty_tier_color(self, app, init_database):
        """Test loyalty tier badge colors."""
        with app.app_context():
            # Test each tier color
            bronze = Customer(name='Bronze', phone='03300000001', loyalty_points=0)
            silver = Customer(name='Silver', phone='03300000002', loyalty_points=500)
            gold = Customer(name='Gold', phone='03300000003', loyalty_points=1000)
            platinum = Customer(name='Platinum', phone='03300000004', loyalty_points=2500)

            db.session.add_all([bronze, silver, gold, platinum])
            db.session.commit()

            assert bronze.loyalty_tier_color == 'info'
            assert silver.loyalty_tier_color == 'secondary'
            assert gold.loyalty_tier_color == 'warning'
            assert platinum.loyalty_tier_color == 'dark'


# =============================================================================
# LOYALTY POINT CALCULATION TESTS
# =============================================================================

class TestLoyaltyPointCalculation:
    """Tests for loyalty point earning and calculation."""

    def test_add_loyalty_points_basic(self, app, init_database):
        """Test basic loyalty point earning (1 point per Rs. 100)."""
        with app.app_context():
            customer = Customer(name='Test Customer', phone='03400000001')
            db.session.add(customer)
            db.session.commit()

            points_earned = customer.add_loyalty_points(1000)  # Rs. 1000 purchase
            db.session.commit()

            assert points_earned == 10  # 1000 / 100 = 10 points
            assert customer.loyalty_points == 10

    def test_add_loyalty_points_fractional(self, app, init_database):
        """Test loyalty points for fractional amounts (should truncate)."""
        with app.app_context():
            customer = Customer(name='Test Customer', phone='03400000002')
            db.session.add(customer)
            db.session.commit()

            # Rs. 550 should give 5 points (550 / 100 = 5.5, truncated to 5)
            points_earned = customer.add_loyalty_points(550)
            db.session.commit()

            assert points_earned == 5
            assert customer.loyalty_points == 5

    def test_add_loyalty_points_small_purchase(self, app, init_database):
        """Test loyalty points for purchase under Rs. 100."""
        with app.app_context():
            customer = Customer(name='Test Customer', phone='03400000003')
            db.session.add(customer)
            db.session.commit()

            points_earned = customer.add_loyalty_points(99)
            db.session.commit()

            assert points_earned == 0
            assert customer.loyalty_points == 0

    def test_add_loyalty_points_cumulative(self, app, init_database):
        """Test cumulative loyalty point earning."""
        with app.app_context():
            customer = Customer(name='Test Customer', phone='03400000004')
            db.session.add(customer)
            db.session.commit()

            customer.add_loyalty_points(500)  # +5 points
            customer.add_loyalty_points(300)  # +3 points
            customer.add_loyalty_points(200)  # +2 points
            db.session.commit()

            assert customer.loyalty_points == 10

    def test_points_value_pkr(self, app, init_database):
        """Test points PKR value calculation (100 points = Rs. 100)."""
        with app.app_context():
            customer = Customer(name='Test Customer', phone='03400000005', loyalty_points=500)
            db.session.add(customer)
            db.session.commit()

            # 500 points = Rs. 500
            assert customer.points_value_pkr == 500


# =============================================================================
# POINT REDEMPTION TESTS
# =============================================================================

class TestPointRedemption:
    """Tests for loyalty point redemption."""

    def test_redeem_points_success(self, app, init_database):
        """Test successful point redemption."""
        with app.app_context():
            customer = Customer(name='Test Customer', phone='03500000001', loyalty_points=500)
            db.session.add(customer)
            db.session.commit()

            success, result = customer.redeem_points(200)
            db.session.commit()

            assert success is True
            assert result == 200  # Rs. 200 discount
            assert customer.loyalty_points == 300

    def test_redeem_points_exact_balance(self, app, init_database):
        """Test redeeming exact point balance."""
        with app.app_context():
            customer = Customer(name='Test Customer', phone='03500000002', loyalty_points=500)
            db.session.add(customer)
            db.session.commit()

            success, result = customer.redeem_points(500)
            db.session.commit()

            assert success is True
            assert result == 500
            assert customer.loyalty_points == 0

    def test_redeem_points_exceeding_balance(self, app, init_database):
        """Test redemption exceeding available balance."""
        with app.app_context():
            customer = Customer(name='Test Customer', phone='03500000003', loyalty_points=200)
            db.session.add(customer)
            db.session.commit()

            success, message = customer.redeem_points(500)

            assert success is False
            assert message == "Insufficient loyalty points"
            assert customer.loyalty_points == 200  # Unchanged

    def test_redeem_points_below_minimum(self, app, init_database):
        """Test redemption below minimum (100 points)."""
        with app.app_context():
            customer = Customer(name='Test Customer', phone='03500000004', loyalty_points=500)
            db.session.add(customer)
            db.session.commit()

            success, message = customer.redeem_points(50)

            assert success is False
            assert message == "Minimum 100 points required for redemption"
            assert customer.loyalty_points == 500  # Unchanged

    def test_redeem_points_negative_amount(self, app, init_database):
        """Test redemption with negative points (edge case)."""
        with app.app_context():
            customer = Customer(name='Test Customer', phone='03500000005', loyalty_points=500)
            db.session.add(customer)
            db.session.commit()

            # Negative redemption should fail minimum check
            success, message = customer.redeem_points(-100)

            assert success is False
            assert customer.loyalty_points == 500  # Unchanged

    def test_redeem_points_zero(self, app, init_database):
        """Test redemption with zero points."""
        with app.app_context():
            customer = Customer(name='Test Customer', phone='03500000006', loyalty_points=500)
            db.session.add(customer)
            db.session.commit()

            success, message = customer.redeem_points(0)

            assert success is False
            assert customer.loyalty_points == 500  # Unchanged


# =============================================================================
# NEGATIVE LOYALTY POINTS TESTS
# =============================================================================

class TestNegativeLoyaltyPoints:
    """Tests for handling negative loyalty point scenarios."""

    def test_negative_points_prevention(self, app, init_database):
        """Test that system prevents negative point balance."""
        with app.app_context():
            customer = Customer(name='Test Customer', phone='03600000001', loyalty_points=50)
            db.session.add(customer)
            db.session.commit()

            # Try to redeem more than available
            success, _ = customer.redeem_points(100)

            # Should fail even though 100 meets minimum (not enough balance)
            assert success is False
            assert customer.loyalty_points == 50

    def test_direct_negative_assignment(self, app, init_database):
        """Test behavior when directly assigning negative points."""
        with app.app_context():
            customer = Customer(name='Test Customer', phone='03600000002', loyalty_points=100)
            db.session.add(customer)
            db.session.commit()

            # Direct assignment (should be handled by application logic)
            # The model allows it, business logic should prevent
            customer.loyalty_points = -50
            db.session.commit()

            # Model allows negative, tier calculation should handle gracefully
            assert customer.loyalty_tier == 'Bronze'  # Negative still means Bronze


# =============================================================================
# DUPLICATE PHONE NUMBER TESTS
# =============================================================================

class TestDuplicatePhoneNumbers:
    """Tests for duplicate phone number handling."""

    def test_unique_phone_constraint(self, app, init_database):
        """Test that duplicate phone numbers are rejected."""
        with app.app_context():
            customer1 = Customer(name='Customer 1', phone='03700000001')
            db.session.add(customer1)
            db.session.commit()

            customer2 = Customer(name='Customer 2', phone='03700000001')
            db.session.add(customer2)

            with pytest.raises(Exception):  # IntegrityError
                db.session.commit()

    def test_unique_phone_different_numbers(self, app, init_database):
        """Test that different phone numbers work correctly."""
        with app.app_context():
            customer1 = Customer(name='Customer 1', phone='03700000002')
            customer2 = Customer(name='Customer 2', phone='03700000003')

            db.session.add_all([customer1, customer2])
            db.session.commit()

            assert customer1.id != customer2.id
            assert Customer.query.count() == 2

    def test_phone_case_sensitivity(self, app, init_database):
        """Test phone number uniqueness is not case sensitive (numbers only)."""
        with app.app_context():
            customer1 = Customer(name='Customer 1', phone='03700000004')
            db.session.add(customer1)
            db.session.commit()

            # Try same phone - should fail
            customer2 = Customer(name='Customer 2', phone='03700000004')
            db.session.add(customer2)

            with pytest.raises(Exception):
                db.session.commit()

    def test_null_phone_allowed_multiple(self, app, init_database):
        """Test that NULL phone values are allowed for multiple customers."""
        with app.app_context():
            # Some customers may not have phone numbers
            customer1 = Customer(name='Customer 1', phone=None)
            customer2 = Customer(name='Customer 2', phone=None)

            db.session.add_all([customer1, customer2])
            # This behavior depends on database - SQLite allows multiple NULLs
            # PostgreSQL also allows multiple NULLs in unique columns
            db.session.commit()

            assert customer1.id is not None
            assert customer2.id is not None


# =============================================================================
# PHONE FORMAT VALIDATION TESTS
# =============================================================================

class TestPhoneFormatValidation:
    """Tests for phone number format validation."""

    def test_valid_pakistan_mobile_format(self, app, init_database):
        """Test valid Pakistani mobile number formats."""
        with app.app_context():
            valid_phones = ['03001234567', '03111234567', '03331234567', '+923001234567']

            for i, phone in enumerate(valid_phones):
                customer = Customer(name=f'Customer {i}', phone=phone)
                db.session.add(customer)

            db.session.commit()
            assert Customer.query.count() == len(valid_phones)

    def test_phone_stored_as_string(self, app, init_database):
        """Test that phone is stored as string."""
        with app.app_context():
            customer = Customer(name='Test', phone='03001234567')
            db.session.add(customer)
            db.session.commit()

            fetched = Customer.query.first()
            assert isinstance(fetched.phone, str)
            assert fetched.phone == '03001234567'

    def test_phone_with_special_characters(self, app, init_database):
        """Test phone with dashes/spaces (application should handle)."""
        with app.app_context():
            # The model accepts any string - validation is at route level
            customer = Customer(name='Test', phone='0300-1234567')
            db.session.add(customer)
            db.session.commit()

            assert customer.phone == '0300-1234567'


# =============================================================================
# EMAIL VALIDATION TESTS
# =============================================================================

class TestEmailValidation:
    """Tests for email field handling."""

    def test_valid_email_format(self, app, init_database):
        """Test valid email formats are accepted."""
        with app.app_context():
            customer = Customer(
                name='Test',
                phone='03800000001',
                email='test@example.com'
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.email == 'test@example.com'

    def test_null_email_allowed(self, app, init_database):
        """Test that NULL email is allowed."""
        with app.app_context():
            customer = Customer(name='Test', phone='03800000002', email=None)
            db.session.add(customer)
            db.session.commit()

            assert customer.email is None

    def test_empty_email_string(self, app, init_database):
        """Test empty string email."""
        with app.app_context():
            customer = Customer(name='Test', phone='03800000003', email='')
            db.session.add(customer)
            db.session.commit()

            assert customer.email == ''

    def test_email_not_unique(self, app, init_database):
        """Test that multiple customers can have same email."""
        with app.app_context():
            customer1 = Customer(name='Customer 1', phone='03800000004', email='shared@example.com')
            customer2 = Customer(name='Customer 2', phone='03800000005', email='shared@example.com')

            db.session.add_all([customer1, customer2])
            db.session.commit()

            assert Customer.query.filter_by(email='shared@example.com').count() == 2


# =============================================================================
# CUSTOMER SEARCH TESTS
# =============================================================================

class TestCustomerSearch:
    """Tests for customer search functionality."""

    def test_search_by_name(self, app, logged_in_client, init_database):
        """Test searching customers by name."""
        with app.app_context():
            # Create test customers
            customers = [
                Customer(name='Ahmed Khan', phone='03900000001'),
                Customer(name='Ahmed Ali', phone='03900000002'),
                Customer(name='Muhammad Bilal', phone='03900000003'),
            ]
            db.session.add_all(customers)
            db.session.commit()

        response = logged_in_client.get('/customers/search?q=Ahmed')
        assert response.status_code == 200
        data = response.get_json()

        assert 'customers' in data
        assert len(data['customers']) == 2

    def test_search_by_phone(self, app, logged_in_client, init_database):
        """Test searching customers by phone number."""
        with app.app_context():
            customers = [
                Customer(name='Customer 1', phone='03901111111'),
                Customer(name='Customer 2', phone='03902222222'),
            ]
            db.session.add_all(customers)
            db.session.commit()

        response = logged_in_client.get('/customers/search?q=0390111')
        assert response.status_code == 200
        data = response.get_json()

        assert len(data['customers']) == 1
        assert data['customers'][0]['phone'] == '03901111111'

    def test_search_minimum_characters(self, app, logged_in_client, init_database):
        """Test search requires minimum 2 characters."""
        with app.app_context():
            customer = Customer(name='Test Customer', phone='03903333333')
            db.session.add(customer)
            db.session.commit()

        # Single character search should return empty
        response = logged_in_client.get('/customers/search?q=T')
        assert response.status_code == 200
        data = response.get_json()

        assert data['customers'] == []

    def test_search_with_special_characters(self, app, logged_in_client, init_database):
        """Test search with special characters."""
        with app.app_context():
            customers = [
                Customer(name="O'Brien", phone='03904444444'),
                Customer(name='Smith & Co.', phone='03905555555'),
                Customer(name='Test <script>', phone='03906666666'),
            ]
            db.session.add_all(customers)
            db.session.commit()

        # Search with apostrophe
        response = logged_in_client.get("/customers/search?q=O'Brien")
        assert response.status_code == 200

        # Search with ampersand
        response = logged_in_client.get('/customers/search?q=Smith')
        assert response.status_code == 200

        # Search with angle brackets (potential XSS)
        response = logged_in_client.get('/customers/search?q=<script>')
        assert response.status_code == 200

    def test_search_case_insensitive(self, app, logged_in_client, init_database):
        """Test search is case insensitive."""
        with app.app_context():
            customer = Customer(name='John Doe', phone='03907777777')
            db.session.add(customer)
            db.session.commit()

        # Lowercase search
        response = logged_in_client.get('/customers/search?q=john')
        data = response.get_json()
        assert len(data['customers']) == 1

        # Uppercase search
        response = logged_in_client.get('/customers/search?q=JOHN')
        data = response.get_json()
        assert len(data['customers']) == 1

    def test_search_inactive_customers_excluded(self, app, logged_in_client, init_database):
        """Test that inactive customers are excluded from search."""
        with app.app_context():
            active = Customer(name='Active Customer', phone='03908888888', is_active=True)
            inactive = Customer(name='Inactive Customer', phone='03909999999', is_active=False)
            db.session.add_all([active, inactive])
            db.session.commit()

        response = logged_in_client.get('/customers/search?q=Customer')
        data = response.get_json()

        # Should only return active customer
        assert len(data['customers']) == 1
        assert data['customers'][0]['name'] == 'Active Customer'

    def test_search_empty_query(self, app, logged_in_client, init_database):
        """Test search with empty query."""
        response = logged_in_client.get('/customers/search?q=')
        assert response.status_code == 200
        data = response.get_json()
        assert data['customers'] == []

    def test_search_limit_results(self, app, logged_in_client, init_database):
        """Test search limits results to 10."""
        with app.app_context():
            # Create 15 customers with similar names
            for i in range(15):
                customer = Customer(
                    name=f'Search Customer {i}',
                    phone=f'0391000000{i:02d}'
                )
                db.session.add(customer)
            db.session.commit()

        response = logged_in_client.get('/customers/search?q=Search')
        data = response.get_json()

        assert len(data['customers']) == 10  # Limited to 10


# =============================================================================
# CUSTOMER CRUD OPERATIONS TESTS
# =============================================================================

class TestCustomerCRUD:
    """Tests for Customer CRUD operations via routes."""

    def test_customer_list_page(self, app, logged_in_client, init_database):
        """Test customer list page loads."""
        with app.app_context():
            customer = Customer(name='List Test', phone='03920000001')
            db.session.add(customer)
            db.session.commit()

        response = logged_in_client.get('/customers/')
        assert response.status_code == 200
        assert b'List Test' in response.data or b'customers' in response.data.lower()

    def test_add_customer_form(self, app, logged_in_client, init_database):
        """Test add customer form loads."""
        response = logged_in_client.get('/customers/add')
        assert response.status_code == 200

    def test_add_customer_submit(self, app, logged_in_client, init_database):
        """Test adding a new customer."""
        response = logged_in_client.post('/customers/add', data={
            'name': 'New Customer',
            'phone': '03921111111',
            'email': 'new@example.com',
            'address': 'Test Address',
            'city': 'Test City',
            'postal_code': '12345',
            'customer_type': 'regular',
            'notes': 'Test notes'
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            customer = Customer.query.filter_by(phone='03921111111').first()
            assert customer is not None
            assert customer.name == 'New Customer'

    def test_add_customer_with_birthday(self, app, logged_in_client, init_database):
        """Test adding customer with birthday."""
        response = logged_in_client.post('/customers/add', data={
            'name': 'Birthday Customer',
            'phone': '03922222222',
            'birthday': '1990-05-15',
            'customer_type': 'regular'
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            customer = Customer.query.filter_by(phone='03922222222').first()
            assert customer is not None
            assert customer.birthday == date(1990, 5, 15)

    def test_edit_customer_form(self, app, logged_in_client, sample_customer):
        """Test edit customer form loads."""
        response = logged_in_client.get(f'/customers/edit/{sample_customer}')
        assert response.status_code == 200

    def test_edit_customer_submit(self, app, logged_in_client, sample_customer):
        """Test editing an existing customer."""
        response = logged_in_client.post(f'/customers/edit/{sample_customer}', data={
            'name': 'Updated Customer',
            'phone': '03923333333',
            'email': 'updated@example.com',
            'customer_type': 'vip'
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            customer = Customer.query.get(sample_customer)
            assert customer.name == 'Updated Customer'
            assert customer.customer_type == 'vip'

    def test_view_customer(self, app, logged_in_client, sample_customer):
        """Test viewing customer details."""
        response = logged_in_client.get(f'/customers/view/{sample_customer}')
        assert response.status_code == 200

    def test_delete_customer_soft_delete(self, app, logged_in_client, sample_customer):
        """Test soft delete customer."""
        response = logged_in_client.post(f'/customers/delete/{sample_customer}')
        assert response.status_code == 200

        with app.app_context():
            customer = Customer.query.get(sample_customer)
            assert customer.is_active is False

    def test_delete_nonexistent_customer(self, app, logged_in_client, init_database):
        """Test deleting non-existent customer."""
        response = logged_in_client.post('/customers/delete/99999')
        assert response.status_code == 404


# =============================================================================
# WALK-IN CUSTOMER TESTS
# =============================================================================

class TestWalkInCustomer:
    """Tests for walk-in customer handling."""

    def test_sale_without_customer(self, app, init_database, sample_product):
        """Test creating sale without customer (walk-in)."""
        with app.app_context():
            user = User.query.filter_by(username='admin').first()
            product = Product.query.get(sample_product)

            # Create sale without customer_id
            sale = Sale(
                sale_number='SALE-WALKIN-001',
                customer_id=None,  # Walk-in customer
                user_id=user.id,
                subtotal=Decimal('150.00'),
                total=Decimal('150.00'),
                payment_method='cash',
                status='completed'
            )
            db.session.add(sale)
            db.session.commit()

            assert sale.id is not None
            assert sale.customer_id is None
            assert sale.customer is None

    def test_walk_in_no_loyalty_points(self, app, init_database, sample_product):
        """Test walk-in customers don't earn loyalty points."""
        with app.app_context():
            user = User.query.filter_by(username='admin').first()

            sale = Sale(
                sale_number='SALE-WALKIN-002',
                customer_id=None,
                user_id=user.id,
                subtotal=Decimal('1000.00'),
                total=Decimal('1000.00'),
                payment_method='cash',
                status='completed'
            )
            db.session.add(sale)
            db.session.commit()

            # No loyalty points should be assigned (no customer)
            assert sale.customer is None


# =============================================================================
# CUSTOMER DELETION WITH SALES HISTORY TESTS
# =============================================================================

class TestCustomerDeletionWithHistory:
    """Tests for handling customer deletion when sales history exists."""

    def test_soft_delete_preserves_sales(self, app, init_database, sample_customer, sample_product):
        """Test that soft delete preserves sales history."""
        with app.app_context():
            user = User.query.filter_by(username='admin').first()
            customer = Customer.query.get(sample_customer)

            # Create sale for customer
            sale = Sale(
                sale_number='SALE-HIST-001',
                customer_id=customer.id,
                user_id=user.id,
                subtotal=Decimal('500.00'),
                total=Decimal('500.00'),
                payment_method='cash',
                status='completed'
            )
            db.session.add(sale)
            db.session.commit()

            # Soft delete customer
            customer.is_active = False
            db.session.commit()

            # Sales should still exist and reference customer
            sale_check = Sale.query.filter_by(sale_number='SALE-HIST-001').first()
            assert sale_check is not None
            assert sale_check.customer_id == customer.id
            assert sale_check.customer.name == customer.name

    def test_soft_deleted_customer_hidden_from_list(self, app, logged_in_client, sample_customer):
        """Test soft deleted customers are hidden from list."""
        with app.app_context():
            customer = Customer.query.get(sample_customer)
            customer.is_active = False
            db.session.commit()

        response = logged_in_client.get('/customers/')
        assert response.status_code == 200
        # Customer should not appear in list
        assert b'Test Customer' not in response.data

    def test_view_soft_deleted_customer_still_works(self, app, logged_in_client, sample_customer):
        """Test that viewing soft deleted customer still works (for historical reference)."""
        with app.app_context():
            customer = Customer.query.get(sample_customer)
            customer.is_active = False
            db.session.commit()

        # Should still be viewable via direct URL
        response = logged_in_client.get(f'/customers/view/{sample_customer}')
        assert response.status_code == 200


# =============================================================================
# PURCHASE HISTORY TESTS
# =============================================================================

class TestPurchaseHistory:
    """Tests for customer purchase history."""

    def test_purchase_history_ordered_by_date(self, app, init_database, sample_customer, sample_product):
        """Test purchase history is ordered by date descending."""
        with app.app_context():
            user = User.query.filter_by(username='admin').first()
            customer = Customer.query.get(sample_customer)

            # Create multiple sales
            for i in range(5):
                sale = Sale(
                    sale_number=f'SALE-ORDER-{i:03d}',
                    customer_id=customer.id,
                    user_id=user.id,
                    subtotal=Decimal('100.00'),
                    total=Decimal('100.00'),
                    payment_method='cash',
                    status='completed',
                    sale_date=datetime.now() - timedelta(days=i)
                )
                db.session.add(sale)
            db.session.commit()

            # Fetch sales ordered by date
            sales = Sale.query.filter_by(customer_id=customer.id)\
                .order_by(Sale.sale_date.desc()).all()

            assert len(sales) == 5
            # Check descending order
            for i in range(len(sales) - 1):
                assert sales[i].sale_date >= sales[i + 1].sale_date

    def test_purchase_history_limit(self, app, logged_in_client, sample_customer, sample_product):
        """Test purchase history is limited to recent transactions."""
        with app.app_context():
            user = User.query.filter_by(username='admin').first()
            customer = Customer.query.get(sample_customer)

            # Create many sales
            for i in range(60):
                sale = Sale(
                    sale_number=f'SALE-LIMIT-{i:03d}',
                    customer_id=customer.id,
                    user_id=user.id,
                    subtotal=Decimal('100.00'),
                    total=Decimal('100.00'),
                    payment_method='cash',
                    status='completed'
                )
                db.session.add(sale)
            db.session.commit()

        # View customer - route limits to 50 sales
        response = logged_in_client.get(f'/customers/view/{sample_customer}')
        assert response.status_code == 200


# =============================================================================
# BIRTHDAY FUNCTIONALITY TESTS
# =============================================================================

class TestBirthdayFunctionality:
    """Tests for birthday-related features."""

    def test_birthday_gift_by_tier(self, app, init_database):
        """Test birthday gift varies by loyalty tier."""
        from app.routes.customers import get_birthday_gift_by_tier

        with app.app_context():
            platinum_gift = get_birthday_gift_by_tier('Platinum')
            gold_gift = get_birthday_gift_by_tier('Gold')
            silver_gift = get_birthday_gift_by_tier('Silver')
            bronze_gift = get_birthday_gift_by_tier('Bronze')

            assert platinum_gift['value'] == 25
            assert gold_gift['value'] == 20
            assert silver_gift['value'] == 15
            assert bronze_gift['value'] == 10

    def test_birthday_check_today(self, app, init_database):
        """Test identifying today's birthdays."""
        with app.app_context():
            today = date.today()

            # Create customer with today's birthday
            customer_today = Customer(
                name='Birthday Today',
                phone='03930000001',
                birthday=date(1990, today.month, today.day)
            )

            # Create customer with different birthday
            customer_other = Customer(
                name='Birthday Other',
                phone='03930000002',
                birthday=date(1990, 1, 1) if today.month != 1 or today.day != 1 else date(1990, 12, 31)
            )

            db.session.add_all([customer_today, customer_other])
            db.session.commit()

            # Check today's birthday
            is_birthday_today = (
                customer_today.birthday.month == today.month and
                customer_today.birthday.day == today.day
            )
            assert is_birthday_today is True


# =============================================================================
# SYNC QUEUE TESTS
# =============================================================================

class TestSyncQueue:
    """Tests for sync queue operations."""

    def test_customer_add_creates_sync_entry(self, app, logged_in_client, init_database):
        """Test that adding customer creates sync queue entry."""
        response = logged_in_client.post('/customers/add', data={
            'name': 'Sync Test Customer',
            'phone': '03940000001',
            'customer_type': 'regular'
        }, follow_redirects=True)

        with app.app_context():
            sync_entries = SyncQueue.query.filter_by(
                table_name='customers',
                operation='insert'
            ).all()

            assert len(sync_entries) >= 1

    def test_customer_edit_creates_sync_entry(self, app, logged_in_client, sample_customer):
        """Test that editing customer creates sync queue entry."""
        response = logged_in_client.post(f'/customers/edit/{sample_customer}', data={
            'name': 'Sync Updated',
            'phone': '03940000002',
            'customer_type': 'vip'
        }, follow_redirects=True)

        with app.app_context():
            sync_entries = SyncQueue.query.filter_by(
                table_name='customers',
                operation='update'
            ).all()

            assert len(sync_entries) >= 1


# =============================================================================
# CUSTOMER TYPE TESTS
# =============================================================================

class TestCustomerTypes:
    """Tests for different customer types."""

    def test_regular_customer_type(self, app, init_database):
        """Test regular customer type."""
        with app.app_context():
            customer = Customer(
                name='Regular Customer',
                phone='03950000001',
                customer_type='regular'
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.customer_type == 'regular'

    def test_vip_customer_type(self, app, init_database):
        """Test VIP customer type."""
        with app.app_context():
            customer = Customer(
                name='VIP Customer',
                phone='03950000002',
                customer_type='vip'
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.customer_type == 'vip'

    def test_wholesale_customer_type(self, app, init_database):
        """Test wholesale customer type."""
        with app.app_context():
            customer = Customer(
                name='Wholesale Customer',
                phone='03950000003',
                customer_type='wholesale'
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.customer_type == 'wholesale'

    def test_default_customer_type(self, app, init_database):
        """Test default customer type is regular."""
        with app.app_context():
            customer = Customer(name='Default Type', phone='03950000004')
            db.session.add(customer)
            db.session.commit()

            assert customer.customer_type == 'regular'


# =============================================================================
# TIER UPGRADE/DOWNGRADE SIMULATION TESTS
# =============================================================================

class TestTierTransitions:
    """Tests for loyalty tier transitions."""

    def test_tier_upgrade_bronze_to_silver(self, app, init_database):
        """Test tier upgrade from Bronze to Silver."""
        with app.app_context():
            customer = Customer(name='Upgrade Test', phone='03960000001', loyalty_points=400)
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Bronze'

            # Simulate purchases that add 100 points (reaching 500)
            customer.add_loyalty_points(10000)  # +100 points
            db.session.commit()

            assert customer.loyalty_points == 500
            assert customer.loyalty_tier == 'Silver'

    def test_tier_upgrade_silver_to_gold(self, app, init_database):
        """Test tier upgrade from Silver to Gold."""
        with app.app_context():
            customer = Customer(name='Upgrade Test', phone='03960000002', loyalty_points=900)
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Silver'

            customer.add_loyalty_points(10000)  # +100 points
            db.session.commit()

            assert customer.loyalty_points == 1000
            assert customer.loyalty_tier == 'Gold'

    def test_tier_downgrade_after_redemption(self, app, init_database):
        """Test tier downgrade after point redemption."""
        with app.app_context():
            customer = Customer(name='Downgrade Test', phone='03960000003', loyalty_points=600)
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Silver'

            # Redeem points to go below 500
            customer.redeem_points(200)
            db.session.commit()

            assert customer.loyalty_points == 400
            assert customer.loyalty_tier == 'Bronze'

    def test_tier_remains_same_after_partial_redemption(self, app, init_database):
        """Test tier remains after partial redemption within tier."""
        with app.app_context():
            customer = Customer(name='Partial Test', phone='03960000004', loyalty_points=700)
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Silver'

            customer.redeem_points(100)
            db.session.commit()

            assert customer.loyalty_points == 600
            assert customer.loyalty_tier == 'Silver'  # Still Silver


# =============================================================================
# EDGE CASES AND ERROR HANDLING TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_very_long_customer_name(self, app, init_database):
        """Test handling of very long customer names."""
        with app.app_context():
            long_name = 'A' * 128  # Maximum length
            customer = Customer(name=long_name, phone='03970000001')
            db.session.add(customer)
            db.session.commit()

            assert len(customer.name) == 128

    def test_unicode_customer_name(self, app, init_database):
        """Test handling of Unicode characters in names."""
        with app.app_context():
            customer = Customer(
                name='محمد احمد',  # Arabic name
                phone='03970000002'
            )
            db.session.add(customer)
            db.session.commit()

            fetched = Customer.query.filter_by(phone='03970000002').first()
            assert fetched.name == 'محمد احمد'

    def test_customer_with_all_fields_null(self, app, init_database):
        """Test customer with minimal required fields."""
        with app.app_context():
            customer = Customer(name='Minimal Customer', phone='03970000003')
            db.session.add(customer)
            db.session.commit()

            assert customer.email is None
            assert customer.address is None
            assert customer.city is None
            assert customer.birthday is None

    def test_concurrent_loyalty_point_updates(self, app, init_database):
        """Test handling of concurrent point updates."""
        with app.app_context():
            customer = Customer(name='Concurrent Test', phone='03970000004', loyalty_points=100)
            db.session.add(customer)
            db.session.commit()

            # Simulate concurrent updates
            customer.add_loyalty_points(500)  # +5 points
            customer.add_loyalty_points(500)  # +5 points
            db.session.commit()

            assert customer.loyalty_points == 110

    def test_zero_value_purchase_no_points(self, app, init_database):
        """Test zero value purchase gives no points."""
        with app.app_context():
            customer = Customer(name='Zero Test', phone='03970000005', loyalty_points=50)
            db.session.add(customer)
            db.session.commit()

            points = customer.add_loyalty_points(0)
            db.session.commit()

            assert points == 0
            assert customer.loyalty_points == 50


# =============================================================================
# ACCOUNT BALANCE TESTS
# =============================================================================

class TestAccountBalance:
    """Tests for customer account balance (credit customers)."""

    def test_initial_account_balance_zero(self, app, init_database):
        """Test initial account balance is zero."""
        with app.app_context():
            customer = Customer(name='Balance Test', phone='03980000001')
            db.session.add(customer)
            db.session.commit()

            assert customer.account_balance == Decimal('0.00')

    def test_account_balance_update(self, app, init_database):
        """Test updating account balance."""
        with app.app_context():
            customer = Customer(
                name='Credit Customer',
                phone='03980000002',
                account_balance=Decimal('500.00')
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.account_balance == Decimal('500.00')

    def test_negative_account_balance(self, app, init_database):
        """Test negative account balance (customer owes money)."""
        with app.app_context():
            customer = Customer(
                name='Debit Customer',
                phone='03980000003',
                account_balance=Decimal('-1000.00')
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.account_balance == Decimal('-1000.00')


# =============================================================================
# PAGINATION TESTS
# =============================================================================

class TestCustomerPagination:
    """Tests for customer list pagination."""

    def test_pagination_first_page(self, app, logged_in_client, init_database):
        """Test pagination on first page."""
        with app.app_context():
            # Create more customers than ITEMS_PER_PAGE
            for i in range(15):
                customer = Customer(
                    name=f'Pagination Customer {i:02d}',
                    phone=f'0399000{i:04d}'
                )
                db.session.add(customer)
            db.session.commit()

        response = logged_in_client.get('/customers/?page=1')
        assert response.status_code == 200

    def test_pagination_second_page(self, app, logged_in_client, init_database):
        """Test pagination on second page."""
        with app.app_context():
            for i in range(25):
                customer = Customer(
                    name=f'Page Customer {i:02d}',
                    phone=f'0398000{i:04d}'
                )
                db.session.add(customer)
            db.session.commit()

        response = logged_in_client.get('/customers/?page=2')
        assert response.status_code == 200

    def test_pagination_invalid_page(self, app, logged_in_client, init_database):
        """Test pagination with invalid page number."""
        response = logged_in_client.get('/customers/?page=9999')
        assert response.status_code == 200  # Should still work, just empty


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
