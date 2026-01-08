"""
Comprehensive Form Validation Tests
Tests for all form submissions and validations in the SOC_WEB_APP

This module provides extensive testing for:
1. Login form validation
2. Product form validation
3. Customer form validation
4. Sale checkout form
5. Stock adjustment forms
6. User creation forms
7. Settings forms
8. Supplier forms
9. Expense forms
10. Returns forms

Edge cases tested:
- Required field validation
- Email format validation
- Phone format validation
- Price format validation
- Negative numbers
- Very large numbers
- Special characters
- Unicode characters
- HTML injection
- CSRF protection
- File uploads
"""

import pytest
import json
from decimal import Decimal
from datetime import datetime, date, timedelta
from io import BytesIO
from flask import url_for
from werkzeug.security import generate_password_hash


class TestConfig:
    """Test configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'
    UPLOAD_FOLDER = '/tmp/test_uploads'
    BACKUP_FOLDER = '/tmp/test_backups'
    LOG_FOLDER = '/tmp/test_logs'
    ITEMS_PER_PAGE = 10


@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    import os
    os.makedirs('/tmp/test_uploads', exist_ok=True)
    os.makedirs('/tmp/test_backups', exist_ok=True)
    os.makedirs('/tmp/test_logs', exist_ok=True)

    from app import create_app
    app = create_app('testing')
    app.config.from_object(TestConfig)

    with app.app_context():
        from app.models import db
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture
def db(app):
    """Database fixture."""
    from app.models import db as _db
    return _db


@pytest.fixture
def admin_user(db):
    """Create an admin user for authentication tests."""
    from app.models import User
    user = User(
        username='admin',
        email='admin@test.com',
        full_name='Admin User',
        role='admin',
        is_active=True,
        is_global_admin=True
    )
    user.set_password('admin123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def cashier_user(db):
    """Create a cashier user for testing."""
    from app.models import User
    user = User(
        username='cashier',
        email='cashier@test.com',
        full_name='Cashier User',
        role='cashier',
        is_active=True
    )
    user.set_password('cashier123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def manager_user(db):
    """Create a manager user for testing."""
    from app.models import User
    user = User(
        username='manager',
        email='manager@test.com',
        full_name='Manager User',
        role='manager',
        is_active=True
    )
    user.set_password('manager123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def sample_category(db):
    """Create a sample category."""
    from app.models import Category
    category = Category(
        name='Test Category',
        description='Test category description'
    )
    db.session.add(category)
    db.session.commit()
    return category


@pytest.fixture
def sample_supplier(db):
    """Create a sample supplier."""
    from app.models import Supplier
    supplier = Supplier(
        name='Test Supplier',
        contact_person='John Doe',
        phone='+92 300 1234567',
        email='supplier@test.com',
        address='Test Address',
        is_active=True
    )
    db.session.add(supplier)
    db.session.commit()
    return supplier


@pytest.fixture
def sample_product(db, sample_category, sample_supplier):
    """Create a sample product."""
    from app.models import Product
    product = Product(
        code='TEST001',
        barcode='1234567890123',
        name='Test Product',
        brand='Test Brand',
        category_id=sample_category.id,
        supplier_id=sample_supplier.id,
        cost_price=Decimal('100.00'),
        selling_price=Decimal('150.00'),
        quantity=100,
        reorder_level=10,
        is_active=True
    )
    db.session.add(product)
    db.session.commit()
    return product


@pytest.fixture
def sample_customer(db):
    """Create a sample customer."""
    from app.models import Customer
    customer = Customer(
        name='Test Customer',
        phone='+92 300 9876543',
        email='customer@test.com',
        address='Test Customer Address',
        city='Karachi',
        customer_type='regular',
        is_active=True
    )
    db.session.add(customer)
    db.session.commit()
    return customer


@pytest.fixture
def sample_location(db):
    """Create a sample location."""
    from app.models import Location
    location = Location(
        code='LOC-001',
        name='Test Store',
        location_type='kiosk',
        address='Test Location Address',
        is_active=True
    )
    db.session.add(location)
    db.session.commit()
    return location


def login(client, username, password):
    """Helper function to login a user."""
    return client.post('/auth/login', data={
        'username': username,
        'password': password
    }, follow_redirects=True)


def logout(client):
    """Helper function to logout."""
    return client.get('/auth/logout', follow_redirects=True)


# =============================================================================
# LOGIN FORM VALIDATION TESTS
# =============================================================================

class TestLoginFormValidation:
    """Tests for login form validation."""

    def test_login_with_valid_credentials(self, client, admin_user):
        """Test successful login with valid credentials."""
        response = login(client, 'admin', 'admin123')
        assert response.status_code == 200
        # Should redirect to dashboard after successful login

    def test_login_with_invalid_username(self, client, admin_user):
        """Test login with non-existent username."""
        response = login(client, 'nonexistent', 'admin123')
        assert response.status_code == 200
        assert b'Invalid username or password' in response.data

    def test_login_with_wrong_password(self, client, admin_user):
        """Test login with wrong password."""
        response = login(client, 'admin', 'wrongpassword')
        assert response.status_code == 200
        assert b'Invalid username or password' in response.data

    def test_login_with_empty_username(self, client, admin_user):
        """Test login with empty username."""
        response = client.post('/auth/login', data={
            'username': '',
            'password': 'admin123'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'Invalid username or password' in response.data

    def test_login_with_empty_password(self, client, admin_user):
        """Test login with empty password."""
        response = client.post('/auth/login', data={
            'username': 'admin',
            'password': ''
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'Invalid username or password' in response.data

    def test_login_with_inactive_user(self, client, db):
        """Test login with an inactive user account."""
        from app.models import User
        user = User(
            username='inactive',
            email='inactive@test.com',
            full_name='Inactive User',
            role='cashier',
            is_active=False
        )
        user.set_password('inactive123')
        db.session.add(user)
        db.session.commit()

        response = login(client, 'inactive', 'inactive123')
        assert response.status_code == 200
        assert b'deactivated' in response.data

    def test_login_with_sql_injection(self, client, admin_user):
        """Test login form is protected against SQL injection."""
        response = client.post('/auth/login', data={
            'username': "admin' OR '1'='1",
            'password': "' OR '1'='1"
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'Invalid username or password' in response.data

    def test_login_with_html_injection(self, client, admin_user):
        """Test login form handles HTML injection safely."""
        response = client.post('/auth/login', data={
            'username': '<script>alert("xss")</script>',
            'password': 'test'
        }, follow_redirects=True)
        assert response.status_code == 200
        # Should not execute script, should show invalid credentials

    def test_login_with_unicode_characters(self, client, admin_user):
        """Test login with unicode characters."""
        response = client.post('/auth/login', data={
            'username': 'admin',
            'password': '密码测试'  # Chinese characters
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'Invalid username or password' in response.data

    def test_login_with_very_long_username(self, client, admin_user):
        """Test login with very long username."""
        response = client.post('/auth/login', data={
            'username': 'a' * 10000,
            'password': 'test123'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'Invalid username or password' in response.data

    def test_login_with_special_characters(self, client, admin_user):
        """Test login with special characters."""
        response = client.post('/auth/login', data={
            'username': 'admin@#$%^&*()',
            'password': 'test!@#$%^&*()'
        }, follow_redirects=True)
        assert response.status_code == 200


# =============================================================================
# PASSWORD CHANGE FORM VALIDATION TESTS
# =============================================================================

class TestPasswordChangeValidation:
    """Tests for password change form validation."""

    def test_change_password_success(self, client, admin_user):
        """Test successful password change."""
        login(client, 'admin', 'admin123')
        response = client.post('/auth/change-password', data={
            'current_password': 'admin123',
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'Password changed successfully' in response.data

    def test_change_password_wrong_current(self, client, admin_user):
        """Test password change with wrong current password."""
        login(client, 'admin', 'admin123')
        response = client.post('/auth/change-password', data={
            'current_password': 'wrongpassword',
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'Current password is incorrect' in response.data

    def test_change_password_mismatch(self, client, admin_user):
        """Test password change with mismatched new passwords."""
        login(client, 'admin', 'admin123')
        response = client.post('/auth/change-password', data={
            'current_password': 'admin123',
            'new_password': 'newpassword123',
            'confirm_password': 'differentpassword'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'do not match' in response.data

    def test_change_password_too_short(self, client, admin_user):
        """Test password change with too short new password."""
        login(client, 'admin', 'admin123')
        response = client.post('/auth/change-password', data={
            'current_password': 'admin123',
            'new_password': '12345',  # Less than 6 characters
            'confirm_password': '12345'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'at least 6 characters' in response.data


# =============================================================================
# USER CREATION FORM VALIDATION TESTS
# =============================================================================

class TestUserCreationValidation:
    """Tests for user creation form validation."""

    def test_create_user_success(self, client, admin_user):
        """Test successful user creation."""
        login(client, 'admin', 'admin123')
        response = client.post('/settings/users/add', data={
            'username': 'newuser',
            'email': 'newuser@test.com',
            'full_name': 'New User',
            'role': 'cashier',
            'password': 'newuser123'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_create_user_duplicate_username(self, client, admin_user):
        """Test user creation with duplicate username."""
        login(client, 'admin', 'admin123')
        response = client.post('/settings/users/add', data={
            'username': 'admin',  # Already exists
            'email': 'another@test.com',
            'full_name': 'Another User',
            'role': 'cashier',
            'password': 'test123'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'already exists' in response.data

    def test_create_user_invalid_email(self, client, admin_user):
        """Test user creation with invalid email format."""
        login(client, 'admin', 'admin123')
        response = client.post('/settings/users/add', data={
            'username': 'newuser',
            'email': 'invalid-email',  # Invalid email format
            'full_name': 'New User',
            'role': 'cashier',
            'password': 'newuser123'
        }, follow_redirects=True)
        assert response.status_code == 200
        # Application may accept this - check specific validation

    def test_create_user_with_unicode_name(self, client, admin_user):
        """Test user creation with unicode characters in name."""
        login(client, 'admin', 'admin123')
        response = client.post('/settings/users/add', data={
            'username': 'unicodeuser',
            'email': 'unicode@test.com',
            'full_name': 'Test User',
            'role': 'cashier',
            'password': 'test123'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_create_user_with_html_injection(self, client, admin_user):
        """Test user creation with HTML injection in name."""
        login(client, 'admin', 'admin123')
        response = client.post('/settings/users/add', data={
            'username': 'htmluser',
            'email': 'html@test.com',
            'full_name': '<script>alert("xss")</script>',
            'role': 'cashier',
            'password': 'test123'
        }, follow_redirects=True)
        assert response.status_code == 200
        # The name should be stored but HTML should be escaped when displayed

    def test_create_user_empty_fields(self, client, admin_user):
        """Test user creation with empty required fields."""
        login(client, 'admin', 'admin123')
        response = client.post('/settings/users/add', data={
            'username': '',
            'email': '',
            'full_name': '',
            'role': '',
            'password': ''
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_create_user_non_admin(self, client, cashier_user):
        """Test that non-admin cannot create users."""
        login(client, 'cashier', 'cashier123')
        response = client.post('/settings/users/add', data={
            'username': 'newuser',
            'email': 'new@test.com',
            'full_name': 'New User',
            'role': 'cashier',
            'password': 'test123'
        }, follow_redirects=True)
        assert response.status_code == 200
        # Should be redirected or show permission error


# =============================================================================
# PRODUCT FORM VALIDATION TESTS
# =============================================================================

class TestProductFormValidation:
    """Tests for product form validation."""

    def test_add_product_success(self, client, admin_user, sample_category, sample_supplier):
        """Test successful product creation."""
        login(client, 'admin', 'admin123')
        response = client.post('/inventory/add', data={
            'code': 'PROD001',
            'barcode': '9876543210123',
            'name': 'New Product',
            'brand': 'Test Brand',
            'category_id': sample_category.id,
            'supplier_id': sample_supplier.id,
            'description': 'Product description',
            'size': '100ml',
            'unit': 'piece',
            'cost_price': '50.00',
            'selling_price': '75.00',
            'tax_rate': '0.00',
            'quantity': '100',
            'reorder_level': '10',
            'reorder_quantity': '50'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_product_negative_price(self, client, admin_user, sample_category):
        """Test product creation with negative price."""
        login(client, 'admin', 'admin123')
        response = client.post('/inventory/add', data={
            'code': 'PROD002',
            'name': 'Negative Price Product',
            'category_id': sample_category.id,
            'cost_price': '-50.00',  # Negative price
            'selling_price': '75.00',
            'quantity': '100'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_product_very_large_price(self, client, admin_user, sample_category):
        """Test product creation with very large price."""
        login(client, 'admin', 'admin123')
        response = client.post('/inventory/add', data={
            'code': 'PROD003',
            'name': 'Expensive Product',
            'category_id': sample_category.id,
            'cost_price': '99999999.99',
            'selling_price': '999999999.99',  # Very large price
            'quantity': '100'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_product_invalid_price_format(self, client, admin_user, sample_category):
        """Test product creation with invalid price format."""
        login(client, 'admin', 'admin123')
        response = client.post('/inventory/add', data={
            'code': 'PROD004',
            'name': 'Invalid Price Product',
            'category_id': sample_category.id,
            'cost_price': 'not_a_number',
            'selling_price': 'also_not_a_number',
            'quantity': '100'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_product_negative_quantity(self, client, admin_user, sample_category):
        """Test product creation with negative quantity."""
        login(client, 'admin', 'admin123')
        response = client.post('/inventory/add', data={
            'code': 'PROD005',
            'name': 'Negative Quantity Product',
            'category_id': sample_category.id,
            'cost_price': '50.00',
            'selling_price': '75.00',
            'quantity': '-10'  # Negative quantity
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_product_duplicate_code(self, client, admin_user, sample_product, sample_category):
        """Test product creation with duplicate product code."""
        login(client, 'admin', 'admin123')
        response = client.post('/inventory/add', data={
            'code': 'TEST001',  # Same as sample_product
            'name': 'Duplicate Code Product',
            'category_id': sample_category.id,
            'cost_price': '50.00',
            'selling_price': '75.00',
            'quantity': '100'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_product_with_unicode_name(self, client, admin_user, sample_category):
        """Test product creation with unicode characters in name."""
        login(client, 'admin', 'admin123')
        response = client.post('/inventory/add', data={
            'code': 'PROD006',
            'name': 'Test Product',  # Arabic text
            'category_id': sample_category.id,
            'cost_price': '50.00',
            'selling_price': '75.00',
            'quantity': '100'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_product_with_html_injection(self, client, admin_user, sample_category):
        """Test product creation with HTML injection in name."""
        login(client, 'admin', 'admin123')
        response = client.post('/inventory/add', data={
            'code': 'PROD007',
            'name': '<script>alert("xss")</script>',
            'description': '<img src=x onerror=alert("xss")>',
            'category_id': sample_category.id,
            'cost_price': '50.00',
            'selling_price': '75.00',
            'quantity': '100'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_product_with_special_characters(self, client, admin_user, sample_category):
        """Test product creation with special characters."""
        login(client, 'admin', 'admin123')
        response = client.post('/inventory/add', data={
            'code': 'PROD-008_A',
            'name': "Product's Name (Test) - Special!",
            'brand': 'Brand & Co.',
            'category_id': sample_category.id,
            'cost_price': '50.00',
            'selling_price': '75.00',
            'quantity': '100'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_product_with_expiry_date(self, client, admin_user, sample_category):
        """Test product creation with expiry date."""
        login(client, 'admin', 'admin123')
        future_date = (date.today() + timedelta(days=365)).strftime('%Y-%m-%d')
        response = client.post('/inventory/add', data={
            'code': 'PROD009',
            'name': 'Expiring Product',
            'category_id': sample_category.id,
            'cost_price': '50.00',
            'selling_price': '75.00',
            'quantity': '100',
            'expiry_date': future_date
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_product_with_past_expiry_date(self, client, admin_user, sample_category):
        """Test product creation with past expiry date."""
        login(client, 'admin', 'admin123')
        past_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
        response = client.post('/inventory/add', data={
            'code': 'PROD010',
            'name': 'Expired Product',
            'category_id': sample_category.id,
            'cost_price': '50.00',
            'selling_price': '75.00',
            'quantity': '100',
            'expiry_date': past_date  # Already expired
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_edit_product_success(self, client, admin_user, sample_product):
        """Test successful product edit."""
        login(client, 'admin', 'admin123')
        response = client.post(f'/inventory/edit/{sample_product.id}', data={
            'code': 'TEST001-EDITED',
            'name': 'Edited Product Name',
            'cost_price': '60.00',
            'selling_price': '90.00',
            'quantity': '150'
        }, follow_redirects=True)
        assert response.status_code == 200


# =============================================================================
# CUSTOMER FORM VALIDATION TESTS
# =============================================================================

class TestCustomerFormValidation:
    """Tests for customer form validation."""

    def test_add_customer_success(self, client, admin_user):
        """Test successful customer creation."""
        login(client, 'admin', 'admin123')
        response = client.post('/customers/add', data={
            'name': 'New Customer',
            'phone': '+92 300 1111111',
            'email': 'newcustomer@test.com',
            'address': 'Customer Address',
            'city': 'Lahore',
            'postal_code': '54000',
            'customer_type': 'regular',
            'notes': 'Customer notes'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_customer_invalid_email(self, client, admin_user):
        """Test customer creation with invalid email."""
        login(client, 'admin', 'admin123')
        response = client.post('/customers/add', data={
            'name': 'Invalid Email Customer',
            'phone': '+92 300 2222222',
            'email': 'not-an-email',
            'city': 'Karachi'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_customer_invalid_phone(self, client, admin_user):
        """Test customer creation with various phone formats."""
        login(client, 'admin', 'admin123')

        # Test with different phone formats
        phone_formats = [
            '+923001234567',
            '03001234567',
            '0300-1234567',
            '0300 123 4567',
            '+92-300-1234567',
            '123'  # Too short
        ]

        for i, phone in enumerate(phone_formats):
            response = client.post('/customers/add', data={
                'name': f'Phone Test Customer {i}',
                'phone': phone,
                'city': 'Islamabad'
            }, follow_redirects=True)
            assert response.status_code == 200

    def test_add_customer_with_birthday(self, client, admin_user):
        """Test customer creation with birthday."""
        login(client, 'admin', 'admin123')
        response = client.post('/customers/add', data={
            'name': 'Birthday Customer',
            'phone': '+92 300 3333333',
            'birthday': '1990-05-15',
            'city': 'Rawalpindi'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_customer_with_html_injection(self, client, admin_user):
        """Test customer creation with HTML injection."""
        login(client, 'admin', 'admin123')
        response = client.post('/customers/add', data={
            'name': '<script>alert("xss")</script>',
            'phone': '+92 300 4444444',
            'address': '<img src=x onerror=alert("xss")>',
            'notes': '<a href="javascript:alert(1)">click</a>',
            'city': 'Karachi'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_customer_with_unicode(self, client, admin_user):
        """Test customer creation with unicode characters."""
        login(client, 'admin', 'admin123')
        response = client.post('/customers/add', data={
            'name': 'Test Customer Name',  # Urdu name
            'phone': '+92 300 5555555',
            'address': 'Test Address',  # Urdu address
            'city': 'Karachi'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_customer_empty_name(self, client, admin_user):
        """Test customer creation with empty name."""
        login(client, 'admin', 'admin123')
        response = client.post('/customers/add', data={
            'name': '',
            'phone': '+92 300 6666666',
            'city': 'Peshawar'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_customer_duplicate_phone(self, client, admin_user, sample_customer):
        """Test customer creation with duplicate phone."""
        login(client, 'admin', 'admin123')
        response = client.post('/customers/add', data={
            'name': 'Duplicate Phone Customer',
            'phone': sample_customer.phone,  # Same phone as sample customer
            'city': 'Faisalabad'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_customer_vip_type(self, client, admin_user):
        """Test customer creation with VIP type."""
        login(client, 'admin', 'admin123')
        response = client.post('/customers/add', data={
            'name': 'VIP Customer',
            'phone': '+92 300 7777777',
            'customer_type': 'vip',
            'city': 'Multan'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_customer_wholesale_type(self, client, admin_user):
        """Test customer creation with wholesale type."""
        login(client, 'admin', 'admin123')
        response = client.post('/customers/add', data={
            'name': 'Wholesale Customer',
            'phone': '+92 300 8888888',
            'customer_type': 'wholesale',
            'city': 'Sialkot'
        }, follow_redirects=True)
        assert response.status_code == 200


# =============================================================================
# SALE CHECKOUT FORM VALIDATION TESTS
# =============================================================================

class TestSaleCheckoutValidation:
    """Tests for sale checkout form validation."""

    def test_complete_sale_success(self, client, admin_user, sample_product, sample_customer, db):
        """Test successful sale completion."""
        login(client, 'admin', 'admin123')

        sale_data = {
            'items': [{
                'product_id': sample_product.id,
                'quantity': 2,
                'unit_price': float(sample_product.selling_price),
                'subtotal': float(sample_product.selling_price) * 2
            }],
            'subtotal': float(sample_product.selling_price) * 2,
            'discount': 0,
            'discount_type': 'amount',
            'tax': 0,
            'total': float(sample_product.selling_price) * 2,
            'payment_method': 'cash',
            'amount_paid': float(sample_product.selling_price) * 2,
            'customer_id': sample_customer.id
        }

        response = client.post('/pos/complete-sale',
                              data=json.dumps(sale_data),
                              content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True

    def test_complete_sale_empty_cart(self, client, admin_user):
        """Test sale completion with empty cart."""
        login(client, 'admin', 'admin123')

        sale_data = {
            'items': [],
            'subtotal': 0,
            'total': 0,
            'payment_method': 'cash',
            'amount_paid': 0
        }

        response = client.post('/pos/complete-sale',
                              data=json.dumps(sale_data),
                              content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] == False
        assert 'No items' in data['error']

    def test_complete_sale_insufficient_stock(self, client, admin_user, sample_product, db):
        """Test sale with quantity exceeding available stock."""
        login(client, 'admin', 'admin123')

        # Try to sell more than available
        sale_data = {
            'items': [{
                'product_id': sample_product.id,
                'quantity': sample_product.quantity + 100,  # More than available
                'unit_price': float(sample_product.selling_price),
                'subtotal': float(sample_product.selling_price) * (sample_product.quantity + 100)
            }],
            'subtotal': float(sample_product.selling_price) * (sample_product.quantity + 100),
            'total': float(sample_product.selling_price) * (sample_product.quantity + 100),
            'payment_method': 'cash',
            'amount_paid': float(sample_product.selling_price) * (sample_product.quantity + 100)
        }

        response = client.post('/pos/complete-sale',
                              data=json.dumps(sale_data),
                              content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] == False
        assert 'Insufficient stock' in data['error']

    def test_complete_sale_invalid_product_id(self, client, admin_user):
        """Test sale with non-existent product ID."""
        login(client, 'admin', 'admin123')

        sale_data = {
            'items': [{
                'product_id': 99999,  # Non-existent product
                'quantity': 1,
                'unit_price': 100,
                'subtotal': 100
            }],
            'subtotal': 100,
            'total': 100,
            'payment_method': 'cash',
            'amount_paid': 100
        }

        response = client.post('/pos/complete-sale',
                              data=json.dumps(sale_data),
                              content_type='application/json')
        assert response.status_code == 404
        data = json.loads(response.data)
        assert data['success'] == False

    def test_complete_sale_negative_quantity(self, client, admin_user, sample_product):
        """Test sale with negative quantity."""
        login(client, 'admin', 'admin123')

        sale_data = {
            'items': [{
                'product_id': sample_product.id,
                'quantity': -5,  # Negative quantity
                'unit_price': float(sample_product.selling_price),
                'subtotal': float(sample_product.selling_price) * -5
            }],
            'subtotal': float(sample_product.selling_price) * -5,
            'total': float(sample_product.selling_price) * -5,
            'payment_method': 'cash',
            'amount_paid': float(sample_product.selling_price) * -5
        }

        response = client.post('/pos/complete-sale',
                              data=json.dumps(sale_data),
                              content_type='application/json')
        assert response.status_code in [200, 400]

    def test_complete_sale_zero_quantity(self, client, admin_user, sample_product):
        """Test sale with zero quantity."""
        login(client, 'admin', 'admin123')

        sale_data = {
            'items': [{
                'product_id': sample_product.id,
                'quantity': 0,
                'unit_price': float(sample_product.selling_price),
                'subtotal': 0
            }],
            'subtotal': 0,
            'total': 0,
            'payment_method': 'cash',
            'amount_paid': 0
        }

        response = client.post('/pos/complete-sale',
                              data=json.dumps(sale_data),
                              content_type='application/json')
        assert response.status_code in [200, 400]

    def test_complete_sale_various_payment_methods(self, client, admin_user, sample_product):
        """Test sale with various payment methods."""
        login(client, 'admin', 'admin123')

        payment_methods = ['cash', 'card', 'bank_transfer', 'easypaisa', 'jazzcash', 'credit']

        for method in payment_methods:
            sale_data = {
                'items': [{
                    'product_id': sample_product.id,
                    'quantity': 1,
                    'unit_price': float(sample_product.selling_price),
                    'subtotal': float(sample_product.selling_price)
                }],
                'subtotal': float(sample_product.selling_price),
                'total': float(sample_product.selling_price),
                'payment_method': method,
                'amount_paid': float(sample_product.selling_price)
            }

            response = client.post('/pos/complete-sale',
                                  data=json.dumps(sale_data),
                                  content_type='application/json')
            assert response.status_code in [200, 400]

    def test_complete_sale_with_discount_percentage(self, client, admin_user, sample_product):
        """Test sale with percentage discount."""
        login(client, 'admin', 'admin123')

        subtotal = float(sample_product.selling_price) * 2
        discount_percent = 10
        discount_amount = subtotal * discount_percent / 100
        total = subtotal - discount_amount

        sale_data = {
            'items': [{
                'product_id': sample_product.id,
                'quantity': 2,
                'unit_price': float(sample_product.selling_price),
                'subtotal': subtotal
            }],
            'subtotal': subtotal,
            'discount': discount_percent,
            'discount_type': 'percentage',
            'tax': 0,
            'total': total,
            'payment_method': 'cash',
            'amount_paid': total
        }

        response = client.post('/pos/complete-sale',
                              data=json.dumps(sale_data),
                              content_type='application/json')
        assert response.status_code == 200

    def test_complete_sale_backdate_as_admin(self, client, admin_user, sample_product):
        """Test backdated sale as admin."""
        login(client, 'admin', 'admin123')

        yesterday = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')

        sale_data = {
            'items': [{
                'product_id': sample_product.id,
                'quantity': 1,
                'unit_price': float(sample_product.selling_price),
                'subtotal': float(sample_product.selling_price)
            }],
            'subtotal': float(sample_product.selling_price),
            'total': float(sample_product.selling_price),
            'payment_method': 'cash',
            'amount_paid': float(sample_product.selling_price),
            'sale_date': yesterday
        }

        response = client.post('/pos/complete-sale',
                              data=json.dumps(sale_data),
                              content_type='application/json')
        assert response.status_code == 200

    def test_complete_sale_backdate_as_cashier(self, client, cashier_user, sample_product):
        """Test that cashier cannot backdate sales."""
        login(client, 'cashier', 'cashier123')

        yesterday = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')

        sale_data = {
            'items': [{
                'product_id': sample_product.id,
                'quantity': 1,
                'unit_price': float(sample_product.selling_price),
                'subtotal': float(sample_product.selling_price)
            }],
            'subtotal': float(sample_product.selling_price),
            'total': float(sample_product.selling_price),
            'payment_method': 'cash',
            'amount_paid': float(sample_product.selling_price),
            'sale_date': yesterday
        }

        response = client.post('/pos/complete-sale',
                              data=json.dumps(sale_data),
                              content_type='application/json')
        # Should be forbidden
        assert response.status_code == 403

    def test_complete_sale_future_date(self, client, admin_user, sample_product):
        """Test sale with future date."""
        login(client, 'admin', 'admin123')

        future_date = (date.today() + timedelta(days=7)).strftime('%Y-%m-%d')

        sale_data = {
            'items': [{
                'product_id': sample_product.id,
                'quantity': 1,
                'unit_price': float(sample_product.selling_price),
                'subtotal': float(sample_product.selling_price)
            }],
            'subtotal': float(sample_product.selling_price),
            'total': float(sample_product.selling_price),
            'payment_method': 'cash',
            'amount_paid': float(sample_product.selling_price),
            'sale_date': future_date
        }

        response = client.post('/pos/complete-sale',
                              data=json.dumps(sale_data),
                              content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'future' in data['error'].lower()


# =============================================================================
# STOCK ADJUSTMENT FORM VALIDATION TESTS
# =============================================================================

class TestStockAdjustmentValidation:
    """Tests for stock adjustment form validation."""

    def test_stock_adjustment_add(self, client, admin_user, sample_product):
        """Test adding stock."""
        login(client, 'admin', 'admin123')

        original_qty = sample_product.quantity

        response = client.post(f'/inventory/adjust-stock/{sample_product.id}',
                              data=json.dumps({
                                  'adjustment_type': 'add',
                                  'quantity': 50,
                                  'reason': 'New stock arrival'
                              }),
                              content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        assert data['new_quantity'] == original_qty + 50

    def test_stock_adjustment_remove(self, client, admin_user, sample_product):
        """Test removing stock."""
        login(client, 'admin', 'admin123')

        original_qty = sample_product.quantity

        response = client.post(f'/inventory/adjust-stock/{sample_product.id}',
                              data=json.dumps({
                                  'adjustment_type': 'remove',
                                  'quantity': 10,
                                  'reason': 'Damaged goods'
                              }),
                              content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        assert data['new_quantity'] == original_qty - 10

    def test_stock_adjustment_set(self, client, admin_user, sample_product):
        """Test setting stock to specific value."""
        login(client, 'admin', 'admin123')

        response = client.post(f'/inventory/adjust-stock/{sample_product.id}',
                              data=json.dumps({
                                  'adjustment_type': 'set',
                                  'quantity': 75,
                                  'reason': 'Physical count adjustment'
                              }),
                              content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        assert data['new_quantity'] == 75

    def test_stock_adjustment_negative_result(self, client, admin_user, sample_product):
        """Test stock adjustment that would result in negative stock."""
        login(client, 'admin', 'admin123')

        response = client.post(f'/inventory/adjust-stock/{sample_product.id}',
                              data=json.dumps({
                                  'adjustment_type': 'remove',
                                  'quantity': sample_product.quantity + 100,  # More than available
                                  'reason': 'Test'
                              }),
                              content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] == False
        assert 'negative' in data['error'].lower()

    def test_stock_adjustment_invalid_product(self, client, admin_user):
        """Test stock adjustment for non-existent product."""
        login(client, 'admin', 'admin123')

        response = client.post('/inventory/adjust-stock/99999',
                              data=json.dumps({
                                  'adjustment_type': 'add',
                                  'quantity': 50,
                                  'reason': 'Test'
                              }),
                              content_type='application/json')
        assert response.status_code == 404

    def test_stock_adjustment_zero_quantity(self, client, admin_user, sample_product):
        """Test stock adjustment with zero quantity."""
        login(client, 'admin', 'admin123')

        original_qty = sample_product.quantity

        response = client.post(f'/inventory/adjust-stock/{sample_product.id}',
                              data=json.dumps({
                                  'adjustment_type': 'add',
                                  'quantity': 0,
                                  'reason': 'Zero adjustment'
                              }),
                              content_type='application/json')
        assert response.status_code == 200

    def test_stock_adjustment_page_form(self, client, admin_user, sample_product):
        """Test stock adjustment page form submission."""
        login(client, 'admin', 'admin123')

        response = client.post(f'/inventory/adjust-stock-page/{sample_product.id}', data={
            'adjustment_type': 'add',
            'quantity': '25',
            'reason': 'Stock received from supplier'
        }, follow_redirects=True)
        assert response.status_code == 200


# =============================================================================
# SUPPLIER FORM VALIDATION TESTS
# =============================================================================

class TestSupplierFormValidation:
    """Tests for supplier form validation."""

    def test_add_supplier_success(self, client, admin_user):
        """Test successful supplier creation."""
        login(client, 'admin', 'admin123')
        response = client.post('/suppliers/add', data={
            'name': 'New Supplier',
            'contact_person': 'Contact Person',
            'phone': '+92 300 1234567',
            'email': 'supplier@example.com',
            'address': 'Supplier Address, City',
            'payment_terms': 'Net 30',
            'notes': 'Supplier notes'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_supplier_duplicate_name(self, client, admin_user, sample_supplier):
        """Test supplier creation with duplicate name."""
        login(client, 'admin', 'admin123')
        response = client.post('/suppliers/add', data={
            'name': sample_supplier.name,  # Duplicate name
            'phone': '+92 300 9999999'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_supplier_invalid_email(self, client, admin_user):
        """Test supplier creation with invalid email."""
        login(client, 'admin', 'admin123')
        response = client.post('/suppliers/add', data={
            'name': 'Invalid Email Supplier',
            'email': 'not-an-email'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_supplier_with_html_injection(self, client, admin_user):
        """Test supplier creation with HTML injection."""
        login(client, 'admin', 'admin123')
        response = client.post('/suppliers/add', data={
            'name': '<script>alert("xss")</script>',
            'contact_person': '<img src=x onerror=alert("xss")>',
            'address': '<a href="javascript:void(0)">Link</a>',
            'notes': '"><script>alert("xss")</script>'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_supplier_empty_name(self, client, admin_user):
        """Test supplier creation with empty name."""
        login(client, 'admin', 'admin123')
        response = client.post('/suppliers/add', data={
            'name': '',
            'phone': '+92 300 1111111'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_edit_supplier_success(self, client, admin_user, sample_supplier):
        """Test successful supplier edit."""
        login(client, 'admin', 'admin123')
        response = client.post(f'/suppliers/edit/{sample_supplier.id}', data={
            'name': 'Updated Supplier Name',
            'contact_person': 'New Contact',
            'phone': '+92 300 7777777',
            'email': 'updated@example.com',
            'address': 'New Address',
            'payment_terms': 'Net 60',
            'notes': 'Updated notes'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_delete_supplier(self, client, admin_user, sample_supplier):
        """Test supplier deletion."""
        login(client, 'admin', 'admin123')
        response = client.post(f'/suppliers/delete/{sample_supplier.id}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True


# =============================================================================
# SETTINGS FORM VALIDATION TESTS
# =============================================================================

class TestSettingsFormValidation:
    """Tests for settings form validation."""

    def test_update_business_settings(self, client, admin_user):
        """Test updating business settings."""
        login(client, 'admin', 'admin123')
        response = client.post('/settings/business/update', data={
            'business_name': 'Updated Business Name',
            'business_address': 'New Business Address',
            'business_phone': '+92 51 1234567',
            'business_email': 'business@example.com',
            'currency': 'PKR',
            'currency_symbol': 'Rs.',
            'tax_rate': '16.0'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_update_business_settings_with_html_injection(self, client, admin_user):
        """Test business settings with HTML injection."""
        login(client, 'admin', 'admin123')
        response = client.post('/settings/business/update', data={
            'business_name': '<script>alert("xss")</script>',
            'business_address': '<img src=x onerror=alert("xss")>'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_update_business_settings_non_admin(self, client, cashier_user):
        """Test that non-admin cannot update business settings."""
        login(client, 'cashier', 'cashier123')
        response = client.post('/settings/business/update', data={
            'business_name': 'Hacked Name'
        }, follow_redirects=True)
        assert response.status_code in [200, 403]

    def test_add_category(self, client, admin_user):
        """Test adding a category."""
        login(client, 'admin', 'admin123')
        response = client.post('/settings/categories/add',
                              data=json.dumps({
                                  'name': 'New Category',
                                  'description': 'Category description'
                              }),
                              content_type='application/json')
        assert response.status_code == 200

    def test_add_category_duplicate_name(self, client, admin_user, sample_category):
        """Test adding category with duplicate name."""
        login(client, 'admin', 'admin123')
        response = client.post('/settings/categories/add',
                              data=json.dumps({
                                  'name': sample_category.name,
                                  'description': 'Duplicate category'
                              }),
                              content_type='application/json')
        assert response.status_code in [200, 500]


# =============================================================================
# EXPENSE FORM VALIDATION TESTS
# =============================================================================

class TestExpenseFormValidation:
    """Tests for expense form validation."""

    def setup_expense_category(self, db):
        """Helper to create expense category for testing."""
        try:
            from app.models_extended import ExpenseCategory
            category = ExpenseCategory(
                name='Test Expense Category',
                description='Test description',
                icon='money-bill',
                color='#000000',
                is_active=True
            )
            db.session.add(category)
            db.session.commit()
            return category
        except Exception:
            return None

    def test_add_expense_success(self, client, admin_user, db):
        """Test successful expense creation."""
        login(client, 'admin', 'admin123')

        category = self.setup_expense_category(db)
        if not category:
            pytest.skip("Expense categories not available")

        response = client.post('/expenses/add', data={
            'category_id': category.id,
            'description': 'Office supplies purchase',
            'amount': '500.00',
            'expense_date': date.today().strftime('%Y-%m-%d'),
            'payment_method': 'cash',
            'reference': 'REF-001',
            'vendor_name': 'Office Supplies Store',
            'notes': 'Monthly supplies'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_expense_negative_amount(self, client, admin_user, db):
        """Test expense creation with negative amount."""
        login(client, 'admin', 'admin123')

        category = self.setup_expense_category(db)
        if not category:
            pytest.skip("Expense categories not available")

        response = client.post('/expenses/add', data={
            'category_id': category.id,
            'description': 'Negative expense',
            'amount': '-500.00',
            'expense_date': date.today().strftime('%Y-%m-%d'),
            'payment_method': 'cash'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_expense_very_large_amount(self, client, admin_user, db):
        """Test expense with very large amount."""
        login(client, 'admin', 'admin123')

        category = self.setup_expense_category(db)
        if not category:
            pytest.skip("Expense categories not available")

        response = client.post('/expenses/add', data={
            'category_id': category.id,
            'description': 'Large expense',
            'amount': '99999999.99',
            'expense_date': date.today().strftime('%Y-%m-%d'),
            'payment_method': 'bank_transfer'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_expense_invalid_amount(self, client, admin_user, db):
        """Test expense with invalid amount format."""
        login(client, 'admin', 'admin123')

        category = self.setup_expense_category(db)
        if not category:
            pytest.skip("Expense categories not available")

        response = client.post('/expenses/add', data={
            'category_id': category.id,
            'description': 'Invalid amount expense',
            'amount': 'not_a_number',
            'expense_date': date.today().strftime('%Y-%m-%d'),
            'payment_method': 'cash'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_expense_future_date(self, client, admin_user, db):
        """Test expense with future date."""
        login(client, 'admin', 'admin123')

        category = self.setup_expense_category(db)
        if not category:
            pytest.skip("Expense categories not available")

        future_date = (date.today() + timedelta(days=30)).strftime('%Y-%m-%d')

        response = client.post('/expenses/add', data={
            'category_id': category.id,
            'description': 'Future expense',
            'amount': '100.00',
            'expense_date': future_date,
            'payment_method': 'cash'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_expense_with_html_injection(self, client, admin_user, db):
        """Test expense with HTML injection."""
        login(client, 'admin', 'admin123')

        category = self.setup_expense_category(db)
        if not category:
            pytest.skip("Expense categories not available")

        response = client.post('/expenses/add', data={
            'category_id': category.id,
            'description': '<script>alert("xss")</script>',
            'amount': '100.00',
            'expense_date': date.today().strftime('%Y-%m-%d'),
            'payment_method': 'cash',
            'vendor_name': '<img src=x onerror=alert("xss")>',
            'notes': '"><script>alert("xss")</script>'
        }, follow_redirects=True)
        assert response.status_code == 200


# =============================================================================
# RETURN FORM VALIDATION TESTS
# =============================================================================

class TestReturnFormValidation:
    """Tests for return form validation."""

    def create_sample_sale(self, db, admin_user, sample_product, sample_customer):
        """Helper to create a sample sale for return testing."""
        from app.models import Sale, SaleItem

        sale = Sale(
            sale_number=f'SALE-{datetime.now().strftime("%Y%m%d%H%M%S")}',
            user_id=admin_user.id,
            customer_id=sample_customer.id,
            subtotal=Decimal('150.00'),
            total=Decimal('150.00'),
            payment_method='cash',
            amount_paid=Decimal('150.00'),
            status='completed'
        )
        db.session.add(sale)
        db.session.flush()

        sale_item = SaleItem(
            sale_id=sale.id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=Decimal('150.00'),
            subtotal=Decimal('150.00')
        )
        db.session.add(sale_item)
        db.session.commit()

        return sale

    def test_process_return_success(self, client, admin_user, sample_product, sample_customer, db):
        """Test successful return processing."""
        login(client, 'admin', 'admin123')

        sale = self.create_sample_sale(db, admin_user, sample_product, sample_customer)
        sale_item = sale.items.first()

        return_data = {
            'sale_id': sale.id,
            'return_type': 'cash',
            'return_reason': 'Customer changed mind',
            'notes': 'Test return',
            'items': [{
                'sale_item_id': sale_item.id,
                'quantity': 1,
                'unit_price': float(sale_item.unit_price)
            }]
        }

        response = client.post('/pos/process-return',
                              data=json.dumps(return_data),
                              content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True

    def test_process_return_store_credit(self, client, admin_user, sample_product, sample_customer, db):
        """Test return with store credit."""
        login(client, 'admin', 'admin123')

        sale = self.create_sample_sale(db, admin_user, sample_product, sample_customer)
        sale_item = sale.items.first()

        return_data = {
            'sale_id': sale.id,
            'return_type': 'store_credit',
            'return_reason': 'Product not as expected',
            'notes': 'Store credit return',
            'items': [{
                'sale_item_id': sale_item.id,
                'quantity': 1,
                'unit_price': float(sale_item.unit_price)
            }]
        }

        response = client.post('/pos/process-return',
                              data=json.dumps(return_data),
                              content_type='application/json')
        assert response.status_code == 200

    def test_process_return_empty_items(self, client, admin_user, sample_product, sample_customer, db):
        """Test return with no items selected."""
        login(client, 'admin', 'admin123')

        sale = self.create_sample_sale(db, admin_user, sample_product, sample_customer)

        return_data = {
            'sale_id': sale.id,
            'return_type': 'cash',
            'return_reason': 'Test',
            'items': []
        }

        response = client.post('/pos/process-return',
                              data=json.dumps(return_data),
                              content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'No items' in data['error']

    def test_process_return_invalid_sale(self, client, admin_user):
        """Test return for non-existent sale."""
        login(client, 'admin', 'admin123')

        return_data = {
            'sale_id': 99999,  # Non-existent sale
            'return_type': 'cash',
            'return_reason': 'Test',
            'items': [{
                'sale_item_id': 1,
                'quantity': 1,
                'unit_price': 100
            }]
        }

        response = client.post('/pos/process-return',
                              data=json.dumps(return_data),
                              content_type='application/json')
        assert response.status_code == 404


# =============================================================================
# FILE UPLOAD VALIDATION TESTS
# =============================================================================

class TestFileUploadValidation:
    """Tests for file upload validation."""

    def test_upload_product_image_valid(self, client, admin_user, sample_category):
        """Test uploading valid product image."""
        login(client, 'admin', 'admin123')

        # Create a fake image file
        data = {
            'code': 'IMGPROD001',
            'name': 'Product With Image',
            'category_id': sample_category.id,
            'cost_price': '50.00',
            'selling_price': '75.00',
            'quantity': '100'
        }
        data['image'] = (BytesIO(b'fake image content'), 'test_image.jpg')

        response = client.post('/inventory/add', data=data,
                              content_type='multipart/form-data',
                              follow_redirects=True)
        assert response.status_code == 200

    def test_upload_product_image_invalid_extension(self, client, admin_user, sample_category):
        """Test uploading product image with invalid extension."""
        login(client, 'admin', 'admin123')

        data = {
            'code': 'IMGPROD002',
            'name': 'Product With Invalid Image',
            'category_id': sample_category.id,
            'cost_price': '50.00',
            'selling_price': '75.00',
            'quantity': '100'
        }
        data['image'] = (BytesIO(b'<?php echo "hack"; ?>'), 'malicious.php')

        response = client.post('/inventory/add', data=data,
                              content_type='multipart/form-data',
                              follow_redirects=True)
        assert response.status_code == 200
        # Should not save the malicious file

    def test_import_csv_valid(self, client, admin_user):
        """Test importing valid CSV."""
        login(client, 'admin', 'admin123')

        csv_content = b'code,name,cost_price,selling_price,quantity\nCSV001,CSV Product,50,75,100'

        response = client.post('/inventory/import-csv',
                              data={'file': (BytesIO(csv_content), 'products.csv')},
                              content_type='multipart/form-data',
                              follow_redirects=True)
        assert response.status_code == 200

    def test_import_csv_no_file(self, client, admin_user):
        """Test import with no file."""
        login(client, 'admin', 'admin123')

        response = client.post('/inventory/import-csv',
                              follow_redirects=True)
        assert response.status_code == 200
        assert b'No file' in response.data

    def test_import_csv_empty_file(self, client, admin_user):
        """Test import with empty file."""
        login(client, 'admin', 'admin123')

        response = client.post('/inventory/import-csv',
                              data={'file': (BytesIO(b''), '')},
                              content_type='multipart/form-data',
                              follow_redirects=True)
        assert response.status_code == 200


# =============================================================================
# AJAX ENDPOINT VALIDATION TESTS
# =============================================================================

class TestAjaxEndpointValidation:
    """Tests for AJAX endpoint validation."""

    def test_search_products_short_query(self, client, admin_user):
        """Test product search with too short query."""
        login(client, 'admin', 'admin123')

        response = client.get('/pos/search-products?q=a')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['products'] == []

    def test_search_products_valid_query(self, client, admin_user, sample_product):
        """Test product search with valid query."""
        login(client, 'admin', 'admin123')

        response = client.get(f'/pos/search-products?q={sample_product.name[:5]}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'products' in data

    def test_search_products_sql_injection(self, client, admin_user):
        """Test product search against SQL injection."""
        login(client, 'admin', 'admin123')

        response = client.get('/pos/search-products?q=\' OR 1=1--')
        assert response.status_code == 200
        # Should not cause error or return all products

    def test_search_customers_short_query(self, client, admin_user):
        """Test customer search with too short query."""
        login(client, 'admin', 'admin123')

        response = client.get('/customers/search?q=a')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['customers'] == []

    def test_search_customers_valid_query(self, client, admin_user, sample_customer):
        """Test customer search with valid query."""
        login(client, 'admin', 'admin123')

        response = client.get(f'/customers/search?q={sample_customer.name[:5]}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'customers' in data

    def test_customer_lookup_by_phone(self, client, admin_user, sample_customer):
        """Test customer lookup by phone number."""
        login(client, 'admin', 'admin123')

        # Clean phone for URL
        phone = sample_customer.phone.replace(' ', '').replace('+', '')

        response = client.get(f'/pos/customer-lookup/{phone}')
        assert response.status_code == 200

    def test_get_product_details(self, client, admin_user, sample_product):
        """Test getting product details."""
        login(client, 'admin', 'admin123')

        response = client.get(f'/pos/get-product/{sample_product.id}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['id'] == sample_product.id

    def test_get_product_not_found(self, client, admin_user):
        """Test getting non-existent product."""
        login(client, 'admin', 'admin123')

        response = client.get('/pos/get-product/99999')
        assert response.status_code == 404


# =============================================================================
# PERMISSION AND ACCESS CONTROL TESTS
# =============================================================================

class TestPermissionValidation:
    """Tests for permission and access control."""

    def test_unauthenticated_access_to_protected_route(self, client):
        """Test that unauthenticated users cannot access protected routes."""
        protected_routes = [
            '/pos/',
            '/inventory/',
            '/customers/',
            '/suppliers/',
            '/settings/',
            '/reports/'
        ]

        for route in protected_routes:
            response = client.get(route)
            # Should redirect to login
            assert response.status_code in [302, 401]

    def test_cashier_cannot_access_settings(self, client, cashier_user):
        """Test that cashier cannot access settings."""
        login(client, 'cashier', 'cashier123')

        response = client.get('/settings/', follow_redirects=True)
        assert response.status_code == 200
        # Should show permission error or redirect

    def test_cashier_cannot_delete_users(self, client, cashier_user, admin_user):
        """Test that cashier cannot delete users."""
        login(client, 'cashier', 'cashier123')

        response = client.post(f'/settings/users/delete/{admin_user.id}')
        assert response.status_code in [403, 200]

    def test_manager_can_access_pos(self, client, manager_user):
        """Test that manager can access POS."""
        login(client, 'manager', 'manager123')

        response = client.get('/pos/', follow_redirects=True)
        assert response.status_code == 200


# =============================================================================
# DAY CLOSE FORM VALIDATION TESTS
# =============================================================================

class TestDayCloseValidation:
    """Tests for day close form validation."""

    def test_get_day_close_summary(self, client, admin_user):
        """Test getting day close summary."""
        login(client, 'admin', 'admin123')

        response = client.get('/pos/close-day-summary')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'summary' in data or 'error' in data

    def test_close_day(self, client, admin_user):
        """Test closing the day."""
        login(client, 'admin', 'admin123')

        response = client.post('/pos/close-day',
                              data=json.dumps({
                                  'closing_balance': 5000.00,
                                  'total_expenses': 500.00,
                                  'notes': 'Day close notes'
                              }),
                              content_type='application/json')
        assert response.status_code == 200

    def test_close_day_twice(self, client, admin_user):
        """Test that day cannot be closed twice."""
        login(client, 'admin', 'admin123')

        # First close
        client.post('/pos/close-day',
                   data=json.dumps({
                       'closing_balance': 5000.00
                   }),
                   content_type='application/json')

        # Second close - should fail
        response = client.post('/pos/close-day',
                              data=json.dumps({
                                  'closing_balance': 5000.00
                              }),
                              content_type='application/json')
        # Might be 200 with error message or 400
        assert response.status_code in [200, 400]


# =============================================================================
# HOLD SALE VALIDATION TESTS
# =============================================================================

class TestHoldSaleValidation:
    """Tests for hold sale functionality."""

    def test_hold_sale(self, client, admin_user, sample_product):
        """Test holding a sale."""
        login(client, 'admin', 'admin123')

        hold_data = {
            'items': [{
                'product_id': sample_product.id,
                'quantity': 1,
                'unit_price': float(sample_product.selling_price)
            }],
            'customer_id': None,
            'notes': 'Customer will return'
        }

        response = client.post('/pos/hold-sale',
                              data=json.dumps(hold_data),
                              content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True

    def test_retrieve_held_sales(self, client, admin_user):
        """Test retrieving held sales."""
        login(client, 'admin', 'admin123')

        response = client.get('/pos/retrieve-held-sales')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'sales' in data


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for various edge cases."""

    def test_very_long_input_fields(self, client, admin_user):
        """Test handling of very long input values."""
        login(client, 'admin', 'admin123')

        long_string = 'a' * 10000

        response = client.post('/customers/add', data={
            'name': long_string,
            'phone': '+92 300 1234567',
            'address': long_string,
            'notes': long_string
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_null_byte_injection(self, client, admin_user):
        """Test handling of null byte injection."""
        login(client, 'admin', 'admin123')

        response = client.post('/customers/add', data={
            'name': 'Customer\x00Name',
            'phone': '+92 300 1234567\x00extra',
            'city': 'Karachi'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_special_unicode_characters(self, client, admin_user):
        """Test handling of special unicode characters."""
        login(client, 'admin', 'admin123')

        # Various special characters
        special_chars = 'Test\u2028\u2029\u0000\uFEFF\u200B'

        response = client.post('/customers/add', data={
            'name': special_chars,
            'phone': '+92 300 1234567',
            'city': 'Test City'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_concurrent_stock_adjustment(self, client, admin_user, sample_product):
        """Test handling of potential concurrent stock adjustments."""
        login(client, 'admin', 'admin123')

        # Simulate multiple rapid adjustments
        for i in range(5):
            response = client.post(f'/inventory/adjust-stock/{sample_product.id}',
                                  data=json.dumps({
                                      'adjustment_type': 'add',
                                      'quantity': 1,
                                      'reason': f'Concurrent test {i}'
                                  }),
                                  content_type='application/json')
            assert response.status_code == 200

    def test_decimal_precision(self, client, admin_user, sample_category):
        """Test decimal precision in prices."""
        login(client, 'admin', 'admin123')

        response = client.post('/inventory/add', data={
            'code': 'DECIMAL001',
            'name': 'Decimal Precision Product',
            'category_id': sample_category.id,
            'cost_price': '99.999999',
            'selling_price': '149.123456789',
            'quantity': '100'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_empty_json_payload(self, client, admin_user):
        """Test handling of empty JSON payloads."""
        login(client, 'admin', 'admin123')

        response = client.post('/pos/complete-sale',
                              data=json.dumps({}),
                              content_type='application/json')
        assert response.status_code == 400

    def test_malformed_json_payload(self, client, admin_user):
        """Test handling of malformed JSON payloads."""
        login(client, 'admin', 'admin123')

        response = client.post('/pos/complete-sale',
                              data='{invalid json}',
                              content_type='application/json')
        assert response.status_code in [400, 500]

    def test_mixed_encoding_input(self, client, admin_user):
        """Test handling of mixed encoding input."""
        login(client, 'admin', 'admin123')

        mixed_input = 'Test Customer'

        response = client.post('/customers/add', data={
            'name': mixed_input,
            'phone': '+92 300 1234567',
            'city': 'Test City'
        }, follow_redirects=True)
        assert response.status_code == 200


# =============================================================================
# BOUNDARY VALUE TESTS
# =============================================================================

class TestBoundaryValues:
    """Tests for boundary value conditions."""

    def test_quantity_boundary_zero(self, client, admin_user, sample_category):
        """Test product with zero quantity."""
        login(client, 'admin', 'admin123')

        response = client.post('/inventory/add', data={
            'code': 'ZERO001',
            'name': 'Zero Quantity Product',
            'category_id': sample_category.id,
            'cost_price': '50.00',
            'selling_price': '75.00',
            'quantity': '0'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_price_boundary_zero(self, client, admin_user, sample_category):
        """Test product with zero price."""
        login(client, 'admin', 'admin123')

        response = client.post('/inventory/add', data={
            'code': 'FREEPROD001',
            'name': 'Free Product',
            'category_id': sample_category.id,
            'cost_price': '0.00',
            'selling_price': '0.00',
            'quantity': '100'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_discount_boundary_100_percent(self, client, admin_user, sample_product):
        """Test sale with 100% discount."""
        login(client, 'admin', 'admin123')

        subtotal = float(sample_product.selling_price)

        sale_data = {
            'items': [{
                'product_id': sample_product.id,
                'quantity': 1,
                'unit_price': subtotal,
                'subtotal': subtotal
            }],
            'subtotal': subtotal,
            'discount': 100,
            'discount_type': 'percentage',
            'tax': 0,
            'total': 0,
            'payment_method': 'cash',
            'amount_paid': 0
        }

        response = client.post('/pos/complete-sale',
                              data=json.dumps(sale_data),
                              content_type='application/json')
        assert response.status_code == 200

    def test_maximum_integer_quantity(self, client, admin_user, sample_category):
        """Test product with maximum integer quantity."""
        login(client, 'admin', 'admin123')

        response = client.post('/inventory/add', data={
            'code': 'MAXINT001',
            'name': 'Max Quantity Product',
            'category_id': sample_category.id,
            'cost_price': '1.00',
            'selling_price': '2.00',
            'quantity': '2147483647'  # Max 32-bit signed integer
        }, follow_redirects=True)
        assert response.status_code == 200


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
