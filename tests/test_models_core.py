"""
Comprehensive Unit Tests for Core Models
Tests for User, Product, and Sale models including edge cases,
validation, and relationship integrity.
"""

import pytest
from decimal import Decimal
from datetime import datetime, date, timedelta
from flask import Flask
from werkzeug.security import generate_password_hash, check_password_hash

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models import (
    db, User, Role, Permission, Product, Category, Supplier,
    Sale, SaleItem, Payment, Customer, Location, LocationStock,
    StockMovement, user_roles, role_permissions
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope='function')
def app():
    """Create and configure a new app instance for each test."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SECRET_KEY'] = 'test-secret-key'

    db.init_app(app)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope='function')
def session(app):
    """Create a new database session for a test."""
    with app.app_context():
        yield db.session


@pytest.fixture
def sample_location(session):
    """Create a sample location (warehouse)."""
    location = Location(
        code='WH-001',
        name='Main Warehouse',
        location_type='warehouse',
        address='123 Warehouse St',
        city='Karachi',
        is_active=True,
        can_sell=False
    )
    session.add(location)
    session.commit()
    return location


@pytest.fixture
def sample_kiosk(session, sample_location):
    """Create a sample kiosk location."""
    kiosk = Location(
        code='K-001',
        name='Downtown Kiosk',
        location_type='kiosk',
        address='456 Mall Road',
        city='Karachi',
        is_active=True,
        can_sell=True,
        parent_warehouse_id=sample_location.id
    )
    session.add(kiosk)
    session.commit()
    return kiosk


@pytest.fixture
def sample_user(session, sample_location):
    """Create a sample user."""
    user = User(
        username='testuser',
        email='test@example.com',
        full_name='Test User',
        role='cashier',
        is_active=True,
        location_id=sample_location.id
    )
    user.set_password('password123')
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def admin_user(session):
    """Create an admin user."""
    user = User(
        username='adminuser',
        email='admin@example.com',
        full_name='Admin User',
        role='admin',
        is_active=True,
        is_global_admin=True
    )
    user.set_password('adminpass123')
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def sample_category(session):
    """Create a sample category."""
    category = Category(
        name='Attars',
        description='Traditional perfume oils'
    )
    session.add(category)
    session.commit()
    return category


@pytest.fixture
def sample_supplier(session):
    """Create a sample supplier."""
    supplier = Supplier(
        name='Premium Oils Co',
        contact_person='John Doe',
        phone='+92-300-1234567',
        email='contact@premiumoils.com',
        is_active=True
    )
    session.add(supplier)
    session.commit()
    return supplier


@pytest.fixture
def sample_product(session, sample_category, sample_supplier):
    """Create a sample product."""
    product = Product(
        code='PROD001',
        barcode='1234567890123',
        name='Rose Attar',
        brand='Premium',
        category_id=sample_category.id,
        supplier_id=sample_supplier.id,
        cost_price=Decimal('100.00'),
        selling_price=Decimal('150.00'),
        quantity=100,
        reorder_level=10,
        reorder_quantity=50,
        is_active=True
    )
    session.add(product)
    session.commit()
    return product


@pytest.fixture
def sample_customer(session):
    """Create a sample customer."""
    customer = Customer(
        name='Ali Khan',
        phone='+92-321-9876543',
        email='ali@email.com',
        customer_type='regular',
        loyalty_points=0,
        is_active=True
    )
    session.add(customer)
    session.commit()
    return customer


@pytest.fixture
def sample_sale(session, sample_user, sample_customer, sample_location):
    """Create a sample sale."""
    sale = Sale(
        sale_number='SALE-001',
        user_id=sample_user.id,
        customer_id=sample_customer.id,
        location_id=sample_location.id,
        subtotal=Decimal('150.00'),
        discount=Decimal('0.00'),
        tax=Decimal('0.00'),
        total=Decimal('150.00'),
        payment_method='cash',
        payment_status='paid',
        amount_paid=Decimal('150.00'),
        amount_due=Decimal('0.00'),
        status='completed'
    )
    session.add(sale)
    session.commit()
    return sale


@pytest.fixture
def sample_role(session):
    """Create a sample RBAC role."""
    role = Role(
        name='test_role',
        display_name='Test Role',
        description='A test role',
        is_system=False
    )
    session.add(role)
    session.commit()
    return role


@pytest.fixture
def sample_permission(session):
    """Create a sample permission."""
    permission = Permission(
        name='test.permission',
        display_name='Test Permission',
        description='A test permission',
        module='test'
    )
    session.add(permission)
    session.commit()
    return permission


# =============================================================================
# USER MODEL TESTS
# =============================================================================

class TestUserModel:
    """Tests for User model."""

    # -------------------------------------------------------------------------
    # Basic CRUD Tests
    # -------------------------------------------------------------------------

    def test_user_creation(self, session, sample_location):
        """Test basic user creation."""
        user = User(
            username='newuser',
            email='new@example.com',
            full_name='New User',
            role='cashier',
            location_id=sample_location.id
        )
        user.set_password('testpass')
        session.add(user)
        session.commit()

        assert user.id is not None
        assert user.username == 'newuser'
        assert user.email == 'new@example.com'
        assert user.role == 'cashier'
        assert user.is_active is True  # Default value

    def test_user_repr(self, sample_user):
        """Test user string representation."""
        assert repr(sample_user) == '<User testuser>'

    def test_user_default_values(self, session):
        """Test user default values."""
        user = User(
            username='defaulttest',
            email='default@test.com',
            full_name='Default Test',
            password_hash='dummy_hash'
        )
        session.add(user)
        session.commit()

        assert user.role == 'cashier'  # Default role
        assert user.is_active is True
        assert user.is_global_admin is False
        assert user.created_at is not None

    # -------------------------------------------------------------------------
    # Password Tests
    # -------------------------------------------------------------------------

    def test_password_hashing(self, sample_user):
        """Test password is properly hashed."""
        assert sample_user.password_hash is not None
        assert sample_user.password_hash != 'password123'
        assert len(sample_user.password_hash) > 20

    def test_password_verification_correct(self, sample_user):
        """Test correct password verification."""
        assert sample_user.check_password('password123') is True

    def test_password_verification_incorrect(self, sample_user):
        """Test incorrect password verification."""
        assert sample_user.check_password('wrongpassword') is False

    def test_password_verification_empty(self, sample_user):
        """Test empty password verification."""
        assert sample_user.check_password('') is False

    def test_password_change(self, session, sample_user):
        """Test password change."""
        sample_user.set_password('newpassword456')
        session.commit()

        assert sample_user.check_password('newpassword456') is True
        assert sample_user.check_password('password123') is False

    def test_password_with_special_characters(self, session):
        """Test password with special characters."""
        user = User(
            username='specialuser',
            email='special@test.com',
            full_name='Special User',
            password_hash='temp'
        )
        special_password = 'P@$$w0rd!#%&*()[]{}|'
        user.set_password(special_password)
        session.add(user)
        session.commit()

        assert user.check_password(special_password) is True

    def test_password_with_unicode(self, session):
        """Test password with unicode characters."""
        user = User(
            username='unicodeuser',
            email='unicode@test.com',
            full_name='Unicode User',
            password_hash='temp'
        )
        unicode_password = 'passwordwithurdu'
        user.set_password(unicode_password)
        session.add(user)
        session.commit()

        assert user.check_password(unicode_password) is True

    # -------------------------------------------------------------------------
    # Role and Permission Tests
    # -------------------------------------------------------------------------

    def test_admin_has_all_permissions(self, admin_user):
        """Test admin user has all permissions."""
        assert admin_user.has_permission('pos.view') is True
        assert admin_user.has_permission('inventory.delete') is True
        assert admin_user.has_permission('settings.manage_roles') is True
        assert admin_user.has_permission('any.random.permission') is True

    def test_global_admin_has_all_permissions(self, session):
        """Test global admin has all permissions."""
        user = User(
            username='globaladmin',
            email='global@admin.com',
            full_name='Global Admin',
            role='cashier',  # Even with cashier role
            is_global_admin=True
        )
        user.set_password('pass')
        session.add(user)
        session.commit()

        assert user.has_permission('any.permission') is True

    def test_cashier_permissions(self, sample_user):
        """Test cashier has correct permissions."""
        # Cashier should have POS permissions
        assert sample_user.has_permission('pos.view') is True
        assert sample_user.has_permission('pos.create_sale') is True

        # Cashier should NOT have admin permissions
        assert sample_user.has_permission('settings.manage_users') is False
        assert sample_user.has_permission('inventory.delete') is False

    def test_manager_permissions(self, session, sample_location):
        """Test manager has correct permissions."""
        manager = User(
            username='manager',
            email='manager@test.com',
            full_name='Manager User',
            role='manager',
            location_id=sample_location.id
        )
        manager.set_password('pass')
        session.add(manager)
        session.commit()

        # Manager should have extended permissions
        assert manager.has_permission('pos.close_day') is True
        assert manager.has_permission('pos.apply_discount') is True
        assert manager.has_permission('expense.view') is True

    def test_rbac_role_assignment(self, session, sample_user, sample_role, sample_permission):
        """Test RBAC role assignment."""
        # Add permission to role
        sample_role.permissions.append(sample_permission)
        # Add role to user
        sample_role.users.append(sample_user)
        session.commit()

        # Check user has the role
        assert sample_user.has_role('test_role') is True
        assert sample_user.has_role('nonexistent_role') is False

    def test_get_all_permissions(self, session, sample_user, sample_role, sample_permission):
        """Test getting all user permissions."""
        sample_role.permissions.append(sample_permission)
        sample_role.users.append(sample_user)
        session.commit()

        permissions = sample_user.get_all_permissions()
        assert 'test.permission' in permissions

    # -------------------------------------------------------------------------
    # Location Access Tests
    # -------------------------------------------------------------------------

    def test_user_can_access_assigned_location(self, sample_user, sample_location):
        """Test user can access their assigned location."""
        assert sample_user.can_access_location(sample_location.id) is True

    def test_user_cannot_access_other_location(self, session, sample_user, sample_kiosk):
        """Test user cannot access non-assigned location."""
        assert sample_user.can_access_location(sample_kiosk.id) is False

    def test_global_admin_can_access_any_location(self, admin_user, sample_location, sample_kiosk):
        """Test global admin can access any location."""
        assert admin_user.can_access_location(sample_location.id) is True
        assert admin_user.can_access_location(sample_kiosk.id) is True
        assert admin_user.can_access_location(9999) is True  # Even non-existent

    def test_get_accessible_locations_regular_user(self, sample_user, sample_location):
        """Test getting accessible locations for regular user."""
        locations = sample_user.get_accessible_locations()
        assert len(locations) == 1
        assert locations[0].id == sample_location.id

    def test_get_accessible_locations_global_admin(self, session, admin_user, sample_location, sample_kiosk):
        """Test getting accessible locations for global admin."""
        locations = admin_user.get_accessible_locations()
        assert len(locations) >= 2  # At least warehouse and kiosk

    def test_user_without_location(self, session):
        """Test user without assigned location."""
        user = User(
            username='nolocuser',
            email='noloc@test.com',
            full_name='No Location User',
            password_hash='temp'
        )
        session.add(user)
        session.commit()

        locations = user.get_accessible_locations()
        assert locations == []

    # -------------------------------------------------------------------------
    # Edge Cases and Validation Tests
    # -------------------------------------------------------------------------

    def test_duplicate_username_fails(self, session, sample_user):
        """Test that duplicate username fails."""
        duplicate = User(
            username='testuser',  # Same as sample_user
            email='different@test.com',
            full_name='Duplicate User',
            password_hash='temp'
        )
        session.add(duplicate)
        with pytest.raises(Exception):  # IntegrityError
            session.commit()
        session.rollback()

    def test_duplicate_email_fails(self, session, sample_user):
        """Test that duplicate email fails."""
        duplicate = User(
            username='differentuser',
            email='test@example.com',  # Same as sample_user
            full_name='Duplicate User',
            password_hash='temp'
        )
        session.add(duplicate)
        with pytest.raises(Exception):  # IntegrityError
            session.commit()
        session.rollback()

    def test_user_with_long_username(self, session):
        """Test user with maximum length username."""
        long_username = 'a' * 64  # Max length
        user = User(
            username=long_username,
            email='longuser@test.com',
            full_name='Long Username User',
            password_hash='temp'
        )
        session.add(user)
        session.commit()

        assert user.username == long_username

    def test_user_timestamps(self, session):
        """Test user timestamps are set correctly."""
        user = User(
            username='timestampuser',
            email='timestamp@test.com',
            full_name='Timestamp User',
            password_hash='temp'
        )
        session.add(user)
        session.commit()

        assert user.created_at is not None
        assert isinstance(user.created_at, datetime)

    def test_user_last_login_update(self, session, sample_user):
        """Test updating user last login."""
        assert sample_user.last_login is None

        sample_user.last_login = datetime.utcnow()
        session.commit()

        assert sample_user.last_login is not None


# =============================================================================
# PRODUCT MODEL TESTS
# =============================================================================

class TestProductModel:
    """Tests for Product model."""

    # -------------------------------------------------------------------------
    # Basic CRUD Tests
    # -------------------------------------------------------------------------

    def test_product_creation(self, session, sample_category):
        """Test basic product creation."""
        product = Product(
            code='NEWPROD',
            name='New Product',
            category_id=sample_category.id,
            cost_price=Decimal('50.00'),
            selling_price=Decimal('75.00'),
            quantity=50
        )
        session.add(product)
        session.commit()

        assert product.id is not None
        assert product.code == 'NEWPROD'
        assert product.is_active is True

    def test_product_repr(self, sample_product):
        """Test product string representation."""
        assert repr(sample_product) == '<Product PROD001 - Rose Attar>'

    def test_product_default_values(self, session):
        """Test product default values."""
        product = Product(
            code='DEFPROD',
            name='Default Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00')
        )
        session.add(product)
        session.commit()

        assert product.quantity == 0
        assert product.reorder_level == 10
        assert product.reorder_quantity == 50
        assert product.is_active is True
        assert product.tax_rate == Decimal('0.00')
        assert product.unit == 'piece'

    # -------------------------------------------------------------------------
    # Pricing Tests
    # -------------------------------------------------------------------------

    def test_profit_margin_calculation(self, sample_product):
        """Test profit margin calculation."""
        # Cost: 100, Selling: 150, Margin: 50%
        assert sample_product.profit_margin == 50.0

    def test_profit_margin_zero_cost(self, session):
        """Test profit margin with zero cost price."""
        product = Product(
            code='ZEROCOST',
            name='Zero Cost Product',
            cost_price=Decimal('0.00'),
            selling_price=Decimal('100.00')
        )
        session.add(product)
        session.commit()

        assert product.profit_margin == 0

    def test_stock_value_calculation(self, sample_product):
        """Test stock value calculation."""
        # Quantity: 100, Cost: 100.00
        assert sample_product.stock_value == 10000.0

    def test_stock_value_zero_quantity(self, session):
        """Test stock value with zero quantity."""
        product = Product(
            code='ZEROQTY',
            name='Zero Quantity Product',
            cost_price=Decimal('100.00'),
            selling_price=Decimal('150.00'),
            quantity=0
        )
        session.add(product)
        session.commit()

        assert product.stock_value == 0.0

    def test_negative_profit_margin(self, session):
        """Test negative profit margin (selling at loss)."""
        product = Product(
            code='LOSSPROD',
            name='Loss Product',
            cost_price=Decimal('100.00'),
            selling_price=Decimal('80.00'),  # Selling below cost
            quantity=10
        )
        session.add(product)
        session.commit()

        assert product.profit_margin == -20.0  # 20% loss

    # -------------------------------------------------------------------------
    # Stock Level Tests
    # -------------------------------------------------------------------------

    def test_is_low_stock_below_level(self, session):
        """Test low stock detection when below reorder level."""
        product = Product(
            code='LOWSTOCK',
            name='Low Stock Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            quantity=5,
            reorder_level=10
        )
        session.add(product)
        session.commit()

        assert product.is_low_stock is True

    def test_is_low_stock_at_level(self, session):
        """Test low stock detection at reorder level."""
        product = Product(
            code='ATLEVEL',
            name='At Level Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            quantity=10,
            reorder_level=10
        )
        session.add(product)
        session.commit()

        assert product.is_low_stock is True  # At or below

    def test_is_not_low_stock(self, sample_product):
        """Test product is not low stock."""
        # sample_product has quantity=100, reorder_level=10
        assert sample_product.is_low_stock is False

    def test_zero_stock(self, session):
        """Test product with zero stock."""
        product = Product(
            code='ZEROSTOCK',
            name='Zero Stock Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            quantity=0,
            reorder_level=10
        )
        session.add(product)
        session.commit()

        assert product.is_low_stock is True
        assert product.alert_priority == 'critical'

    # -------------------------------------------------------------------------
    # Expiry Tests
    # -------------------------------------------------------------------------

    def test_days_until_expiry_future(self, session):
        """Test days until expiry for future date."""
        future_date = date.today() + timedelta(days=30)
        product = Product(
            code='EXPFUT',
            name='Future Expiry Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            expiry_date=future_date
        )
        session.add(product)
        session.commit()

        assert product.days_until_expiry == 30
        assert product.is_expired is False

    def test_days_until_expiry_past(self, session):
        """Test days until expiry for past date."""
        past_date = date.today() - timedelta(days=10)
        product = Product(
            code='EXPPAST',
            name='Past Expiry Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            expiry_date=past_date
        )
        session.add(product)
        session.commit()

        assert product.days_until_expiry == -10
        assert product.is_expired is True

    def test_no_expiry_date(self, sample_product):
        """Test product without expiry date."""
        assert sample_product.days_until_expiry is None
        assert sample_product.is_expired is False
        assert sample_product.expiry_status == 'no_expiry'

    def test_expiring_soon(self, session):
        """Test product expiring within 30 days."""
        soon_date = date.today() + timedelta(days=15)
        product = Product(
            code='EXPSOON',
            name='Soon Expiry Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            expiry_date=soon_date
        )
        session.add(product)
        session.commit()

        assert product.is_expiring_soon is True
        assert product.expiry_status == 'warning'

    def test_expiring_critical(self, session):
        """Test product expiring within 7 days."""
        critical_date = date.today() + timedelta(days=5)
        product = Product(
            code='EXPCRIT',
            name='Critical Expiry Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            expiry_date=critical_date
        )
        session.add(product)
        session.commit()

        assert product.is_expiring_critical is True
        assert product.expiry_status == 'critical'

    def test_expiry_badge_classes(self, session):
        """Test expiry badge CSS classes."""
        # Expired product
        expired = Product(
            code='EXP1',
            name='Expired',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            expiry_date=date.today() - timedelta(days=1)
        )
        session.add(expired)
        session.commit()

        assert expired.expiry_badge_class == 'danger'

    # -------------------------------------------------------------------------
    # Alert Priority Tests
    # -------------------------------------------------------------------------

    def test_alert_priority_critical_zero_stock(self, session):
        """Test critical alert for zero stock."""
        product = Product(
            code='ALERTCRIT',
            name='Critical Alert Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            quantity=0
        )
        session.add(product)
        session.commit()

        assert product.alert_priority == 'critical'

    def test_alert_priority_critical_expired(self, session):
        """Test critical alert for expired product."""
        product = Product(
            code='ALERTEXP',
            name='Expired Alert Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            quantity=100,
            expiry_date=date.today() - timedelta(days=1)
        )
        session.add(product)
        session.commit()

        assert product.alert_priority == 'critical'

    def test_alert_priority_high_low_stock(self, session):
        """Test high alert for low stock."""
        product = Product(
            code='ALERTHIGH',
            name='High Alert Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            quantity=5,
            reorder_level=10
        )
        session.add(product)
        session.commit()

        assert product.alert_priority == 'high'

    def test_alert_priority_low_healthy(self, sample_product):
        """Test low alert for healthy product."""
        assert sample_product.alert_priority == 'low'

    # -------------------------------------------------------------------------
    # Edge Cases and Validation Tests
    # -------------------------------------------------------------------------

    def test_duplicate_code_fails(self, session, sample_product):
        """Test that duplicate product code fails."""
        duplicate = Product(
            code='PROD001',  # Same as sample_product
            name='Duplicate Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00')
        )
        session.add(duplicate)
        with pytest.raises(Exception):
            session.commit()
        session.rollback()

    def test_duplicate_barcode_fails(self, session, sample_product):
        """Test that duplicate barcode fails."""
        duplicate = Product(
            code='DIFFCODE',
            barcode='1234567890123',  # Same as sample_product
            name='Duplicate Barcode Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00')
        )
        session.add(duplicate)
        with pytest.raises(Exception):
            session.commit()
        session.rollback()

    def test_product_with_decimal_prices(self, session):
        """Test product with decimal prices."""
        product = Product(
            code='DECIMAL',
            name='Decimal Price Product',
            cost_price=Decimal('99.99'),
            selling_price=Decimal('149.99')
        )
        session.add(product)
        session.commit()

        assert product.cost_price == Decimal('99.99')
        assert product.selling_price == Decimal('149.99')

    def test_product_category_relationship(self, sample_product, sample_category):
        """Test product-category relationship."""
        assert sample_product.category.id == sample_category.id
        assert sample_product in sample_category.products.all()

    def test_product_supplier_relationship(self, sample_product, sample_supplier):
        """Test product-supplier relationship."""
        assert sample_product.supplier.id == sample_supplier.id
        assert sample_product in sample_supplier.products.all()


# =============================================================================
# SALE MODEL TESTS
# =============================================================================

class TestSaleModel:
    """Tests for Sale model."""

    # -------------------------------------------------------------------------
    # Basic CRUD Tests
    # -------------------------------------------------------------------------

    def test_sale_creation(self, session, sample_user, sample_location):
        """Test basic sale creation."""
        sale = Sale(
            sale_number='SALE-NEW',
            user_id=sample_user.id,
            location_id=sample_location.id,
            subtotal=Decimal('200.00'),
            total=Decimal('200.00'),
            payment_method='cash',
            status='completed'
        )
        session.add(sale)
        session.commit()

        assert sale.id is not None
        assert sale.sale_number == 'SALE-NEW'
        assert sale.status == 'completed'

    def test_sale_repr(self, sample_sale):
        """Test sale string representation."""
        assert repr(sample_sale) == '<Sale SALE-001>'

    def test_sale_default_values(self, session, sample_user):
        """Test sale default values."""
        sale = Sale(
            sale_number='SALE-DEF',
            user_id=sample_user.id,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
            payment_method='cash'
        )
        session.add(sale)
        session.commit()

        assert sale.discount == Decimal('0.00')
        assert sale.tax == Decimal('0.00')
        assert sale.discount_type == 'amount'
        assert sale.payment_status == 'paid'
        assert sale.status == 'completed'
        assert sale.synced is False

    # -------------------------------------------------------------------------
    # Status Transition Tests
    # -------------------------------------------------------------------------

    def test_sale_status_completed(self, sample_sale):
        """Test sale with completed status."""
        assert sample_sale.status == 'completed'
        assert sample_sale.payment_status == 'paid'

    def test_sale_status_held(self, session, sample_user, sample_location):
        """Test sale with held status."""
        sale = Sale(
            sale_number='SALE-HELD',
            user_id=sample_user.id,
            location_id=sample_location.id,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
            payment_method='cash',
            status='held'
        )
        session.add(sale)
        session.commit()

        assert sale.status == 'held'

    def test_sale_status_cancelled(self, session, sample_sale):
        """Test cancelling a sale."""
        sample_sale.status = 'cancelled'
        session.commit()

        assert sample_sale.status == 'cancelled'

    def test_sale_status_refunded(self, session, sample_sale):
        """Test refunding a sale."""
        sample_sale.status = 'refunded'
        session.commit()

        assert sample_sale.status == 'refunded'

    # -------------------------------------------------------------------------
    # Total Calculation Tests
    # -------------------------------------------------------------------------

    def test_calculate_totals_no_discount(self, session, sample_user, sample_product, sample_location):
        """Test total calculation without discount."""
        sale = Sale(
            sale_number='SALE-CALC1',
            user_id=sample_user.id,
            location_id=sample_location.id,
            payment_method='cash'
        )
        session.add(sale)
        session.flush()

        # Add item
        item = SaleItem(
            sale_id=sale.id,
            product_id=sample_product.id,
            quantity=2,
            unit_price=Decimal('150.00'),
            discount=Decimal('0.00')
        )
        item.calculate_subtotal()
        session.add(item)
        session.commit()

        sale.calculate_totals()
        session.commit()

        assert sale.subtotal == Decimal('300.00')
        assert sale.total == Decimal('300.00')

    def test_calculate_totals_with_amount_discount(self, session, sample_user, sample_product, sample_location):
        """Test total calculation with amount discount."""
        sale = Sale(
            sale_number='SALE-CALC2',
            user_id=sample_user.id,
            location_id=sample_location.id,
            payment_method='cash',
            discount=Decimal('50.00'),
            discount_type='amount'
        )
        session.add(sale)
        session.flush()

        item = SaleItem(
            sale_id=sale.id,
            product_id=sample_product.id,
            quantity=2,
            unit_price=Decimal('150.00'),
            discount=Decimal('0.00')
        )
        item.calculate_subtotal()
        session.add(item)
        session.commit()

        sale.calculate_totals()
        session.commit()

        assert sale.subtotal == Decimal('300.00')
        assert sale.total == Decimal('250.00')  # 300 - 50

    def test_calculate_totals_with_percentage_discount(self, session, sample_user, sample_product, sample_location):
        """Test total calculation with percentage discount."""
        sale = Sale(
            sale_number='SALE-CALC3',
            user_id=sample_user.id,
            location_id=sample_location.id,
            payment_method='cash',
            discount=Decimal('10.00'),  # 10%
            discount_type='percentage'
        )
        session.add(sale)
        session.flush()

        item = SaleItem(
            sale_id=sale.id,
            product_id=sample_product.id,
            quantity=2,
            unit_price=Decimal('100.00'),
            discount=Decimal('0.00')
        )
        item.calculate_subtotal()
        session.add(item)
        session.commit()

        sale.calculate_totals()
        session.commit()

        assert sale.subtotal == Decimal('200.00')
        assert sale.total == Decimal('180.00')  # 200 - 10%

    def test_calculate_totals_with_tax(self, session, sample_user, sample_product, sample_location):
        """Test total calculation with tax."""
        sale = Sale(
            sale_number='SALE-CALC4',
            user_id=sample_user.id,
            location_id=sample_location.id,
            payment_method='cash',
            tax=Decimal('10.00')  # 10% tax rate
        )
        session.add(sale)
        session.flush()

        item = SaleItem(
            sale_id=sale.id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=Decimal('100.00'),
            discount=Decimal('0.00')
        )
        item.calculate_subtotal()
        session.add(item)
        session.commit()

        sale.calculate_totals()
        session.commit()

        assert sale.subtotal == Decimal('100.00')
        assert sale.total == Decimal('110.00')  # 100 + 10%

    # -------------------------------------------------------------------------
    # Payment Tests
    # -------------------------------------------------------------------------

    def test_sale_paid_status(self, sample_sale):
        """Test fully paid sale."""
        assert sample_sale.payment_status == 'paid'
        assert sample_sale.amount_paid == sample_sale.total
        assert sample_sale.amount_due == Decimal('0.00')

    def test_sale_partial_payment(self, session, sample_user, sample_location):
        """Test partial payment sale."""
        sale = Sale(
            sale_number='SALE-PART',
            user_id=sample_user.id,
            location_id=sample_location.id,
            subtotal=Decimal('200.00'),
            total=Decimal('200.00'),
            payment_method='credit',
            payment_status='partial',
            amount_paid=Decimal('100.00'),
            amount_due=Decimal('100.00')
        )
        session.add(sale)
        session.commit()

        assert sale.payment_status == 'partial'
        assert sale.amount_due == Decimal('100.00')

    def test_sale_pending_payment(self, session, sample_user, sample_location):
        """Test pending payment sale."""
        sale = Sale(
            sale_number='SALE-PEND',
            user_id=sample_user.id,
            location_id=sample_location.id,
            subtotal=Decimal('200.00'),
            total=Decimal('200.00'),
            payment_method='credit',
            payment_status='pending',
            amount_paid=Decimal('0.00'),
            amount_due=Decimal('200.00')
        )
        session.add(sale)
        session.commit()

        assert sale.payment_status == 'pending'
        assert sale.amount_due == Decimal('200.00')

    def test_sale_multiple_payment_methods(self, session, sample_sale, sample_user):
        """Test sale with multiple payments."""
        # Add additional payment
        payment = Payment(
            sale_id=sample_sale.id,
            amount=Decimal('50.00'),
            payment_method='card'
        )
        session.add(payment)
        session.commit()

        payments = sample_sale.payments.all()
        assert len(payments) == 1

    # -------------------------------------------------------------------------
    # Relationship Tests
    # -------------------------------------------------------------------------

    def test_sale_user_relationship(self, sample_sale, sample_user):
        """Test sale-user relationship."""
        assert sample_sale.cashier.id == sample_user.id
        assert sample_sale in sample_user.sales.all()

    def test_sale_customer_relationship(self, sample_sale, sample_customer):
        """Test sale-customer relationship."""
        assert sample_sale.customer.id == sample_customer.id
        assert sample_sale in sample_customer.sales.all()

    def test_sale_location_relationship(self, sample_sale, sample_location):
        """Test sale-location relationship."""
        assert sample_sale.location.id == sample_location.id

    def test_sale_items_relationship(self, session, sample_sale, sample_product):
        """Test sale-items relationship."""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=Decimal('150.00'),
            subtotal=Decimal('150.00')
        )
        session.add(item)
        session.commit()

        assert item in sample_sale.items.all()
        assert item.sale.id == sample_sale.id

    def test_sale_without_customer(self, session, sample_user, sample_location):
        """Test sale without customer (walk-in)."""
        sale = Sale(
            sale_number='SALE-WALKIN',
            user_id=sample_user.id,
            location_id=sample_location.id,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
            payment_method='cash'
        )
        session.add(sale)
        session.commit()

        assert sale.customer_id is None
        assert sale.customer is None

    # -------------------------------------------------------------------------
    # Edge Cases and Validation Tests
    # -------------------------------------------------------------------------

    def test_duplicate_sale_number_fails(self, session, sample_sale, sample_user, sample_location):
        """Test that duplicate sale number fails."""
        duplicate = Sale(
            sale_number='SALE-001',  # Same as sample_sale
            user_id=sample_user.id,
            location_id=sample_location.id,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
            payment_method='cash'
        )
        session.add(duplicate)
        with pytest.raises(Exception):
            session.commit()
        session.rollback()

    def test_sale_with_zero_total(self, session, sample_user, sample_location):
        """Test sale with zero total (free items)."""
        sale = Sale(
            sale_number='SALE-FREE',
            user_id=sample_user.id,
            location_id=sample_location.id,
            subtotal=Decimal('0.00'),
            total=Decimal('0.00'),
            payment_method='cash',
            amount_paid=Decimal('0.00')
        )
        session.add(sale)
        session.commit()

        assert sale.total == Decimal('0.00')

    def test_sale_timestamps(self, sample_sale):
        """Test sale timestamps."""
        assert sample_sale.created_at is not None
        assert sample_sale.sale_date is not None
        assert isinstance(sample_sale.sale_date, datetime)

    def test_cascade_delete_items(self, session, sample_sale, sample_product):
        """Test cascade delete of sale items when sale deleted."""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=Decimal('100.00'),
            subtotal=Decimal('100.00')
        )
        session.add(item)
        session.commit()

        item_id = item.id
        session.delete(sample_sale)
        session.commit()

        # Item should be deleted
        assert SaleItem.query.get(item_id) is None


# =============================================================================
# SALE ITEM MODEL TESTS
# =============================================================================

class TestSaleItemModel:
    """Tests for SaleItem model."""

    def test_sale_item_creation(self, session, sample_sale, sample_product):
        """Test basic sale item creation."""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=2,
            unit_price=Decimal('150.00'),
            discount=Decimal('0.00')
        )
        item.calculate_subtotal()
        session.add(item)
        session.commit()

        assert item.id is not None
        assert item.quantity == 2
        assert item.subtotal == Decimal('300.00')

    def test_sale_item_repr(self, session, sample_sale, sample_product):
        """Test sale item string representation."""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=Decimal('100.00'),
            subtotal=Decimal('100.00')
        )
        session.add(item)
        session.commit()

        assert '<SaleItem' in repr(item)

    def test_calculate_subtotal_with_discount(self, session, sample_sale, sample_product):
        """Test subtotal calculation with discount."""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=2,
            unit_price=Decimal('100.00'),
            discount=Decimal('20.00')
        )
        item.calculate_subtotal()
        session.add(item)
        session.commit()

        # (2 * 100) - 20 = 180
        assert item.subtotal == Decimal('180.00')

    def test_calculate_subtotal_no_discount(self, session, sample_sale, sample_product):
        """Test subtotal calculation without discount."""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=3,
            unit_price=Decimal('50.00'),
            discount=Decimal('0.00')
        )
        item.calculate_subtotal()
        session.add(item)
        session.commit()

        assert item.subtotal == Decimal('150.00')

    def test_sale_item_product_relationship(self, session, sample_sale, sample_product):
        """Test sale item-product relationship."""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=Decimal('100.00'),
            subtotal=Decimal('100.00')
        )
        session.add(item)
        session.commit()

        assert item.product.id == sample_product.id
        assert item in sample_product.sale_items.all()


# =============================================================================
# CUSTOMER MODEL TESTS
# =============================================================================

class TestCustomerModel:
    """Tests for Customer model."""

    def test_customer_creation(self, session):
        """Test basic customer creation."""
        customer = Customer(
            name='Test Customer',
            phone='+92-300-1111111',
            email='customer@test.com'
        )
        session.add(customer)
        session.commit()

        assert customer.id is not None
        assert customer.customer_type == 'regular'
        assert customer.loyalty_points == 0

    def test_customer_repr(self, sample_customer):
        """Test customer string representation."""
        assert repr(sample_customer) == '<Customer Ali Khan>'

    # -------------------------------------------------------------------------
    # Loyalty Points Tests
    # -------------------------------------------------------------------------

    def test_add_loyalty_points(self, session, sample_customer):
        """Test adding loyalty points."""
        points_earned = sample_customer.add_loyalty_points(500)  # Rs. 500 purchase
        session.commit()

        assert points_earned == 5  # 1 point per Rs. 100
        assert sample_customer.loyalty_points == 5

    def test_add_loyalty_points_large_purchase(self, session, sample_customer):
        """Test adding loyalty points for large purchase."""
        points_earned = sample_customer.add_loyalty_points(10000)  # Rs. 10,000 purchase
        session.commit()

        assert points_earned == 100
        assert sample_customer.loyalty_points == 100

    def test_redeem_points_success(self, session, sample_customer):
        """Test successful points redemption."""
        sample_customer.loyalty_points = 500
        session.commit()

        success, result = sample_customer.redeem_points(200)
        session.commit()

        assert success is True
        assert result == 200  # Rs. 200 discount
        assert sample_customer.loyalty_points == 300

    def test_redeem_points_insufficient(self, session, sample_customer):
        """Test redemption with insufficient points."""
        sample_customer.loyalty_points = 50
        session.commit()

        success, result = sample_customer.redeem_points(100)

        assert success is False
        assert 'Insufficient' in result
        assert sample_customer.loyalty_points == 50  # Unchanged

    def test_redeem_points_below_minimum(self, session, sample_customer):
        """Test redemption below minimum threshold."""
        sample_customer.loyalty_points = 500
        session.commit()

        success, result = sample_customer.redeem_points(50)  # Below 100 minimum

        assert success is False
        assert 'Minimum' in result

    # -------------------------------------------------------------------------
    # Loyalty Tier Tests
    # -------------------------------------------------------------------------

    def test_loyalty_tier_bronze(self, sample_customer):
        """Test Bronze loyalty tier."""
        sample_customer.loyalty_points = 0
        assert sample_customer.loyalty_tier == 'Bronze'

    def test_loyalty_tier_silver(self, session, sample_customer):
        """Test Silver loyalty tier."""
        sample_customer.loyalty_points = 500
        session.commit()

        assert sample_customer.loyalty_tier == 'Silver'

    def test_loyalty_tier_gold(self, session, sample_customer):
        """Test Gold loyalty tier."""
        sample_customer.loyalty_points = 1000
        session.commit()

        assert sample_customer.loyalty_tier == 'Gold'

    def test_loyalty_tier_platinum(self, session, sample_customer):
        """Test Platinum loyalty tier."""
        sample_customer.loyalty_points = 2500
        session.commit()

        assert sample_customer.loyalty_tier == 'Platinum'

    def test_points_to_next_tier(self, session, sample_customer):
        """Test points needed for next tier."""
        sample_customer.loyalty_points = 300
        session.commit()

        assert sample_customer.points_to_next_tier == 200  # 500 - 300 for Silver
        assert sample_customer.next_tier_name == 'Silver'

    def test_points_to_next_tier_at_max(self, session, sample_customer):
        """Test points to next tier when at max tier."""
        sample_customer.loyalty_points = 3000
        session.commit()

        assert sample_customer.points_to_next_tier == 0
        assert sample_customer.next_tier_name is None

    def test_loyalty_tier_colors(self, session, sample_customer):
        """Test loyalty tier color assignments."""
        sample_customer.loyalty_points = 0
        assert sample_customer.loyalty_tier_color == 'info'  # Bronze

        sample_customer.loyalty_points = 500
        assert sample_customer.loyalty_tier_color == 'secondary'  # Silver

        sample_customer.loyalty_points = 1000
        assert sample_customer.loyalty_tier_color == 'warning'  # Gold

        sample_customer.loyalty_points = 2500
        assert sample_customer.loyalty_tier_color == 'dark'  # Platinum

    # -------------------------------------------------------------------------
    # Edge Cases
    # -------------------------------------------------------------------------

    def test_duplicate_phone_fails(self, session, sample_customer):
        """Test that duplicate phone fails."""
        duplicate = Customer(
            name='Another Customer',
            phone='+92-321-9876543'  # Same as sample_customer
        )
        session.add(duplicate)
        with pytest.raises(Exception):
            session.commit()
        session.rollback()


# =============================================================================
# LOCATION MODEL TESTS
# =============================================================================

class TestLocationModel:
    """Tests for Location model."""

    def test_warehouse_creation(self, sample_location):
        """Test warehouse location creation."""
        assert sample_location.location_type == 'warehouse'
        assert sample_location.is_warehouse is True
        assert sample_location.is_kiosk is False
        assert sample_location.can_sell is False

    def test_kiosk_creation(self, sample_kiosk):
        """Test kiosk location creation."""
        assert sample_kiosk.location_type == 'kiosk'
        assert sample_kiosk.is_kiosk is True
        assert sample_kiosk.is_warehouse is False
        assert sample_kiosk.can_sell is True

    def test_location_repr(self, sample_location):
        """Test location string representation."""
        assert repr(sample_location) == '<Location WH-001 - Main Warehouse>'

    def test_kiosk_warehouse_relationship(self, sample_kiosk, sample_location):
        """Test kiosk-warehouse relationship."""
        assert sample_kiosk.parent_warehouse.id == sample_location.id
        assert sample_kiosk in sample_location.child_kiosks

    def test_get_stock_for_product_no_stock(self, sample_location, sample_product):
        """Test getting stock when no stock record exists."""
        stock = sample_location.get_stock_for_product(sample_product.id)
        assert stock == 0

    def test_get_stock_for_product_with_stock(self, session, sample_location, sample_product):
        """Test getting stock when stock record exists."""
        loc_stock = LocationStock(
            location_id=sample_location.id,
            product_id=sample_product.id,
            quantity=50,
            reserved_quantity=10
        )
        session.add(loc_stock)
        session.commit()

        stock = sample_location.get_stock_for_product(sample_product.id)
        assert stock == 40  # 50 - 10 reserved


# =============================================================================
# LOCATION STOCK MODEL TESTS
# =============================================================================

class TestLocationStockModel:
    """Tests for LocationStock model."""

    def test_location_stock_creation(self, session, sample_location, sample_product):
        """Test location stock creation."""
        loc_stock = LocationStock(
            location_id=sample_location.id,
            product_id=sample_product.id,
            quantity=100,
            reserved_quantity=0
        )
        session.add(loc_stock)
        session.commit()

        assert loc_stock.id is not None
        assert loc_stock.quantity == 100

    def test_available_quantity(self, session, sample_location, sample_product):
        """Test available quantity calculation."""
        loc_stock = LocationStock(
            location_id=sample_location.id,
            product_id=sample_product.id,
            quantity=100,
            reserved_quantity=25
        )
        session.add(loc_stock)
        session.commit()

        assert loc_stock.available_quantity == 75

    def test_available_quantity_all_reserved(self, session, sample_location, sample_product):
        """Test available quantity when all reserved."""
        loc_stock = LocationStock(
            location_id=sample_location.id,
            product_id=sample_product.id,
            quantity=50,
            reserved_quantity=50
        )
        session.add(loc_stock)
        session.commit()

        assert loc_stock.available_quantity == 0

    def test_available_quantity_over_reserved(self, session, sample_location, sample_product):
        """Test available quantity when over-reserved (edge case)."""
        loc_stock = LocationStock(
            location_id=sample_location.id,
            product_id=sample_product.id,
            quantity=30,
            reserved_quantity=50  # Over-reserved
        )
        session.add(loc_stock)
        session.commit()

        assert loc_stock.available_quantity == 0  # Should be 0, not negative

    def test_is_low_stock(self, session, sample_location, sample_product):
        """Test low stock detection."""
        loc_stock = LocationStock(
            location_id=sample_location.id,
            product_id=sample_product.id,
            quantity=5,
            reorder_level=10
        )
        session.add(loc_stock)
        session.commit()

        assert loc_stock.is_low_stock is True

    def test_stock_value_calculation(self, session, sample_location, sample_product):
        """Test stock value calculation."""
        loc_stock = LocationStock(
            location_id=sample_location.id,
            product_id=sample_product.id,
            quantity=10
        )
        session.add(loc_stock)
        session.commit()

        # Product cost_price is 100.00
        assert loc_stock.stock_value == 1000.0

    def test_unique_constraint(self, session, sample_location, sample_product):
        """Test unique constraint on location-product pair."""
        loc_stock1 = LocationStock(
            location_id=sample_location.id,
            product_id=sample_product.id,
            quantity=50
        )
        session.add(loc_stock1)
        session.commit()

        loc_stock2 = LocationStock(
            location_id=sample_location.id,
            product_id=sample_product.id,
            quantity=30
        )
        session.add(loc_stock2)
        with pytest.raises(Exception):
            session.commit()
        session.rollback()


# =============================================================================
# PAYMENT MODEL TESTS
# =============================================================================

class TestPaymentModel:
    """Tests for Payment model."""

    def test_payment_creation(self, session, sample_sale):
        """Test basic payment creation."""
        payment = Payment(
            sale_id=sample_sale.id,
            amount=Decimal('150.00'),
            payment_method='cash'
        )
        session.add(payment)
        session.commit()

        assert payment.id is not None
        assert payment.payment_date is not None

    def test_payment_repr(self, session, sample_sale):
        """Test payment string representation."""
        payment = Payment(
            sale_id=sample_sale.id,
            amount=Decimal('100.00'),
            payment_method='card'
        )
        session.add(payment)
        session.commit()

        assert '<Payment' in repr(payment)
        assert '100.00' in repr(payment)

    def test_payment_with_reference(self, session, sample_sale):
        """Test payment with reference number."""
        payment = Payment(
            sale_id=sample_sale.id,
            amount=Decimal('200.00'),
            payment_method='bank_transfer',
            reference_number='TXN123456'
        )
        session.add(payment)
        session.commit()

        assert payment.reference_number == 'TXN123456'


# =============================================================================
# ROLE AND PERMISSION MODEL TESTS
# =============================================================================

class TestRolePermissionModels:
    """Tests for Role and Permission models."""

    def test_role_creation(self, sample_role):
        """Test basic role creation."""
        assert sample_role.id is not None
        assert sample_role.name == 'test_role'
        assert sample_role.is_system is False

    def test_role_repr(self, sample_role):
        """Test role string representation."""
        assert repr(sample_role) == '<Role test_role>'

    def test_permission_creation(self, sample_permission):
        """Test basic permission creation."""
        assert sample_permission.id is not None
        assert sample_permission.name == 'test.permission'
        assert sample_permission.module == 'test'

    def test_permission_repr(self, sample_permission):
        """Test permission string representation."""
        assert repr(sample_permission) == '<Permission test.permission>'

    def test_role_has_permission(self, session, sample_role, sample_permission):
        """Test role permission check."""
        sample_role.permissions.append(sample_permission)
        session.commit()

        assert sample_role.has_permission('test.permission') is True
        assert sample_role.has_permission('other.permission') is False

    def test_multiple_permissions_on_role(self, session, sample_role):
        """Test role with multiple permissions."""
        perm1 = Permission(name='perm.one', display_name='Permission One', module='test')
        perm2 = Permission(name='perm.two', display_name='Permission Two', module='test')

        sample_role.permissions.extend([perm1, perm2])
        session.add_all([perm1, perm2])
        session.commit()

        assert sample_role.has_permission('perm.one') is True
        assert sample_role.has_permission('perm.two') is True


# =============================================================================
# CATEGORY MODEL TESTS
# =============================================================================

class TestCategoryModel:
    """Tests for Category model."""

    def test_category_creation(self, sample_category):
        """Test basic category creation."""
        assert sample_category.id is not None
        assert sample_category.name == 'Attars'

    def test_category_repr(self, sample_category):
        """Test category string representation."""
        assert repr(sample_category) == '<Category Attars>'

    def test_subcategory_relationship(self, session, sample_category):
        """Test parent-child category relationship."""
        subcategory = Category(
            name='Rose Attars',
            description='Rose-based attars',
            parent_id=sample_category.id
        )
        session.add(subcategory)
        session.commit()

        assert subcategory.parent.id == sample_category.id
        assert subcategory in sample_category.subcategories


# =============================================================================
# SUPPLIER MODEL TESTS
# =============================================================================

class TestSupplierModel:
    """Tests for Supplier model."""

    def test_supplier_creation(self, sample_supplier):
        """Test basic supplier creation."""
        assert sample_supplier.id is not None
        assert sample_supplier.name == 'Premium Oils Co'
        assert sample_supplier.is_active is True

    def test_supplier_repr(self, sample_supplier):
        """Test supplier string representation."""
        assert repr(sample_supplier) == '<Supplier Premium Oils Co>'

    def test_duplicate_supplier_name_fails(self, session, sample_supplier):
        """Test that duplicate supplier name fails."""
        duplicate = Supplier(
            name='Premium Oils Co'  # Same name
        )
        session.add(duplicate)
        with pytest.raises(Exception):
            session.commit()
        session.rollback()


# =============================================================================
# STOCK MOVEMENT MODEL TESTS
# =============================================================================

class TestStockMovementModel:
    """Tests for StockMovement model."""

    def test_stock_movement_creation(self, session, sample_product, sample_user, sample_location):
        """Test basic stock movement creation."""
        movement = StockMovement(
            product_id=sample_product.id,
            user_id=sample_user.id,
            location_id=sample_location.id,
            movement_type='purchase',
            quantity=50,
            reference='PO-001'
        )
        session.add(movement)
        session.commit()

        assert movement.id is not None
        assert movement.timestamp is not None

    def test_stock_movement_repr(self, session, sample_product, sample_location):
        """Test stock movement string representation."""
        movement = StockMovement(
            product_id=sample_product.id,
            location_id=sample_location.id,
            movement_type='sale',
            quantity=-5
        )
        session.add(movement)
        session.commit()

        assert 'sale' in repr(movement)
        assert '-5' in repr(movement)

    def test_negative_quantity_for_outgoing(self, session, sample_product, sample_location):
        """Test negative quantity for outgoing movements."""
        movement = StockMovement(
            product_id=sample_product.id,
            location_id=sample_location.id,
            movement_type='sale',
            quantity=-10  # Negative for outgoing
        )
        session.add(movement)
        session.commit()

        assert movement.quantity == -10


# =============================================================================
# EDGE CASE AND BOUNDARY TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_product_with_negative_quantity(self, session):
        """Test product with negative quantity (edge case, should be prevented in logic)."""
        product = Product(
            code='NEGQTY',
            name='Negative Quantity Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            quantity=-5  # Edge case
        )
        session.add(product)
        session.commit()

        # Stock value should handle negative
        assert product.stock_value == -50.0

    def test_product_with_very_large_values(self, session):
        """Test product with very large values."""
        product = Product(
            code='LARGEVAL',
            name='Large Value Product',
            cost_price=Decimal('99999999.99'),
            selling_price=Decimal('99999999.99'),
            quantity=99999999
        )
        session.add(product)
        session.commit()

        assert product.id is not None

    def test_sale_with_large_discount(self, session, sample_user, sample_location):
        """Test sale with 100% discount."""
        sale = Sale(
            sale_number='SALE-100DISC',
            user_id=sample_user.id,
            location_id=sample_location.id,
            subtotal=Decimal('100.00'),
            discount=Decimal('100.00'),  # 100% discount
            discount_type='percentage',
            total=Decimal('0.00'),
            payment_method='cash'
        )
        session.add(sale)
        session.commit()

        sale.calculate_totals()
        assert sale.total == Decimal('0.00')

    def test_customer_with_maximum_loyalty_points(self, session):
        """Test customer with very high loyalty points."""
        customer = Customer(
            name='VIP Customer',
            phone='+92-300-9999999',
            loyalty_points=999999999
        )
        session.add(customer)
        session.commit()

        assert customer.loyalty_tier == 'Platinum'
        assert customer.points_to_next_tier == 0

    def test_user_with_all_roles(self, session, sample_user):
        """Test user with multiple RBAC roles."""
        role1 = Role(name='role1', display_name='Role 1')
        role2 = Role(name='role2', display_name='Role 2')
        role3 = Role(name='role3', display_name='Role 3')

        role1.users.append(sample_user)
        role2.users.append(sample_user)
        role3.users.append(sample_user)

        session.add_all([role1, role2, role3])
        session.commit()

        assert sample_user.has_role('role1') is True
        assert sample_user.has_role('role2') is True
        assert sample_user.has_role('role3') is True

    def test_product_expiry_exactly_today(self, session):
        """Test product expiring exactly today."""
        product = Product(
            code='EXPTODAY',
            name='Expires Today Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            expiry_date=date.today()
        )
        session.add(product)
        session.commit()

        assert product.days_until_expiry == 0
        assert product.is_expired is False  # Not expired yet (today is the expiry date)

    def test_empty_string_values(self, session):
        """Test handling of empty strings."""
        product = Product(
            code='EMPTY',
            name='Empty Fields Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            description='',  # Empty string
            brand='',  # Empty string
            batch_number=''  # Empty string
        )
        session.add(product)
        session.commit()

        assert product.description == ''
        assert product.brand == ''


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
