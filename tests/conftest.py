"""
Shared pytest fixtures and configuration for all tests.

Provides common fixtures for Flask application testing, database sessions,
authentication, and test data initialization.
"""

import pytest
import sys
import os
from decimal import Decimal
from datetime import date

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db


@pytest.fixture(scope='session')
def app_factory():
    """Factory fixture for creating test app instances."""
    def _create_app(config='testing'):
        app = create_app(config)
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SERVER_NAME'] = 'localhost'
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['ITEMS_PER_PAGE'] = 20
        return app
    return _create_app


@pytest.fixture(scope='session')
def app(app_factory):
    """Create application for testing session."""
    return app_factory()


@pytest.fixture(scope='function')
def fresh_app(app_factory):
    """Create a fresh application for each test with clean database."""
    app = app_factory()

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope='function')
def client(fresh_app):
    """Create a test client for each test."""
    return fresh_app.test_client()


@pytest.fixture(scope='function')
def db_session(fresh_app):
    """Provide a database session for testing."""
    with fresh_app.app_context():
        yield db.session
        db.session.rollback()


@pytest.fixture(scope='function')
def init_database(fresh_app):
    """
    Initialize database with comprehensive test data.

    Creates:
    - Locations (warehouse, kiosk)
    - Users (admin, manager, cashier, inactive)
    - Categories
    - Products (active, inactive, out-of-stock)
    - Customers (regular, VIP, inactive)
    - Location Stock
    - Settings
    """
    from app.models import (
        User, Product, Customer, Location, LocationStock,
        Category, Setting
    )

    with fresh_app.app_context():
        # Create warehouse location
        warehouse = Location(
            code='WH-001',
            name='Main Warehouse',
            location_type='warehouse',
            address='123 Warehouse St',
            city='Wah',
            is_active=True
        )
        db.session.add(warehouse)
        db.session.flush()

        # Create kiosk location
        kiosk = Location(
            code='K-001',
            name='Mall Kiosk',
            location_type='kiosk',
            address='Mall of Wah',
            city='Wah',
            parent_warehouse_id=warehouse.id,
            is_active=True,
            can_sell=True
        )
        db.session.add(kiosk)
        db.session.flush()

        # Create admin user (global admin)
        admin = User(
            username='admin',
            email='admin@test.com',
            full_name='Admin User',
            role='admin',
            is_active=True,
            is_global_admin=True
        )
        admin.set_password('admin123')
        db.session.add(admin)

        # Create manager user
        manager = User(
            username='manager',
            email='manager@test.com',
            full_name='Manager User',
            role='manager',
            location_id=kiosk.id,
            is_active=True
        )
        manager.set_password('manager123')
        db.session.add(manager)

        # Create cashier user
        cashier = User(
            username='cashier',
            email='cashier@test.com',
            full_name='Cashier User',
            role='cashier',
            location_id=kiosk.id,
            is_active=True
        )
        cashier.set_password('cashier123')
        db.session.add(cashier)

        # Create warehouse manager
        warehouse_manager = User(
            username='warehouse_mgr',
            email='whmgr@test.com',
            full_name='Warehouse Manager',
            role='warehouse_manager',
            location_id=warehouse.id,
            is_active=True
        )
        warehouse_manager.set_password('warehouse123')
        db.session.add(warehouse_manager)

        # Create inactive user
        inactive_user = User(
            username='inactive',
            email='inactive@test.com',
            full_name='Inactive User',
            role='cashier',
            is_active=False
        )
        inactive_user.set_password('inactive123')
        db.session.add(inactive_user)

        # Create categories
        category1 = Category(name='Attars', description='Traditional oil-based perfumes')
        category2 = Category(name='Perfumes', description='Alcohol-based fragrances')
        db.session.add_all([category1, category2])
        db.session.flush()

        # Create products
        products = [
            Product(
                code='PRD001',
                barcode='1234567890123',
                name='Oud Premium',
                brand='Sunnat',
                category_id=category1.id,
                cost_price=Decimal('500.00'),
                selling_price=Decimal('1000.00'),
                quantity=100,
                reorder_level=10,
                is_active=True
            ),
            Product(
                code='PRD002',
                barcode='1234567890124',
                name='Musk Amber',
                brand='Sunnat',
                category_id=category1.id,
                cost_price=Decimal('300.00'),
                selling_price=Decimal('600.00'),
                quantity=50,
                reorder_level=5,
                is_active=True
            ),
            Product(
                code='PRD003',
                barcode='1234567890125',
                name='Rose Attar',
                brand='Classic',
                category_id=category1.id,
                cost_price=Decimal('200.00'),
                selling_price=Decimal('400.00'),
                quantity=0,  # Out of stock
                reorder_level=10,
                is_active=True
            ),
            Product(
                code='PRD004',
                barcode='1234567890126',
                name='Sandalwood Special',
                brand='Premium',
                category_id=category2.id,
                cost_price=Decimal('800.00'),
                selling_price=Decimal('1500.00'),
                quantity=25,
                reorder_level=5,
                is_active=True
            ),
            Product(
                code='PRD_INACTIVE',
                barcode='9999999999999',
                name='Discontinued Product',
                brand='Old',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                quantity=10,
                is_active=False
            ),
        ]
        db.session.add_all(products)
        db.session.flush()

        # Create location stock for both locations
        for product in products[:4]:  # Only active products
            # Warehouse stock
            warehouse_stock = LocationStock(
                location_id=warehouse.id,
                product_id=product.id,
                quantity=product.quantity * 2,
                reorder_level=product.reorder_level * 2
            )
            db.session.add(warehouse_stock)

            # Kiosk stock (less than warehouse)
            kiosk_stock = LocationStock(
                location_id=kiosk.id,
                product_id=product.id,
                quantity=product.quantity,
                reorder_level=product.reorder_level
            )
            db.session.add(kiosk_stock)

        # Create customers
        customers = [
            Customer(
                name='John Doe',
                phone='03001234567',
                email='john@test.com',
                address='123 Main St',
                city='Wah',
                customer_type='regular',
                loyalty_points=500,
                is_active=True
            ),
            Customer(
                name='Jane Smith',
                phone='03001234568',
                email='jane@test.com',
                address='456 Oak Ave',
                city='Islamabad',
                customer_type='vip',
                loyalty_points=2500,
                birthday=date(1990, 1, 15),
                is_active=True
            ),
            Customer(
                name='Ahmed Khan',
                phone='03001234569',
                email='ahmed@test.com',
                customer_type='wholesale',
                loyalty_points=1000,
                is_active=True
            ),
            Customer(
                name='Inactive Customer',
                phone='03009999999',
                is_active=False
            ),
        ]
        db.session.add_all(customers)

        # Create settings
        settings = [
            Setting(key='business_name', value='Sunnat Collection', category='business'),
            Setting(key='business_address', value='Mall of Wah, Pakistan', category='business'),
            Setting(key='business_phone', value='+92-51-1234567', category='business'),
            Setting(key='currency', value='PKR', category='business'),
            Setting(key='currency_symbol', value='Rs.', category='business'),
            Setting(key='tax_rate', value='0', category='business'),
        ]
        db.session.add_all(settings)

        db.session.commit()
        yield

        # Cleanup is handled by fresh_app fixture


@pytest.fixture
def auth_admin(client, init_database):
    """
    Login as admin user and return authenticated client.
    Admin has global access to all features.
    """
    client.post('/auth/login', data={
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    return client


@pytest.fixture
def auth_manager(client, init_database):
    """
    Login as manager user and return authenticated client.
    Manager has location-based access with elevated privileges.
    """
    client.post('/auth/login', data={
        'username': 'manager',
        'password': 'manager123'
    }, follow_redirects=True)
    return client


@pytest.fixture
def auth_cashier(client, init_database):
    """
    Login as cashier user and return authenticated client.
    Cashier has limited access to POS functions.
    """
    client.post('/auth/login', data={
        'username': 'cashier',
        'password': 'cashier123'
    }, follow_redirects=True)
    return client


@pytest.fixture
def auth_warehouse_manager(client, init_database):
    """
    Login as warehouse manager user and return authenticated client.
    Warehouse manager has access to warehouse operations.
    """
    client.post('/auth/login', data={
        'username': 'warehouse_mgr',
        'password': 'warehouse123'
    }, follow_redirects=True)
    return client


def logout_client(client):
    """Helper function to logout a client."""
    client.get('/auth/logout', follow_redirects=True)


# Pytest configuration
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "security: marks tests as security-related"
    )
    config.addinivalue_line(
        "markers", "api: marks tests as API endpoint tests"
    )
    config.addinivalue_line(
        "markers", "auth: marks tests as authentication tests"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically add markers based on test class/function names."""
    for item in items:
        # Add api marker to all API tests
        if 'API' in item.nodeid or 'api' in item.nodeid.lower():
            item.add_marker(pytest.mark.api)

        # Add security marker to security tests
        keywords = ['injection', 'xss', 'csrf', 'sql', 'security']
        if any(kw in item.name.lower() for kw in keywords):
            item.add_marker(pytest.mark.security)

        # Add auth marker to authentication tests
        if 'auth' in item.name.lower() or 'login' in item.name.lower():
            item.add_marker(pytest.mark.auth)
