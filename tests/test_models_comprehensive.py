"""
Comprehensive Unit Tests for SOC_WEB_APP Models

This module provides exhaustive test coverage for all SQLAlchemy models in the application.
Tests cover:
- Model creation and basic CRUD operations
- Field validations and constraints
- Relationships and foreign keys
- Edge cases and boundary conditions
- Security tests (SQL injection, XSS attempts)
- Concurrent access simulation
- Unicode and special character handling

Author: Test Engineer
"""

import pytest
import threading
import time
from decimal import Decimal, InvalidOperation
from datetime import datetime, date, timedelta
from sqlalchemy.exc import IntegrityError, DataError
from sqlalchemy import text
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import (
    db, User, Role, Permission, Category, Supplier, Product, Customer,
    Sale, SaleItem, Payment, StockMovement, PurchaseOrder, PurchaseOrderItem,
    SyncQueue, Setting, ActivityLog, Report, DayClose, Location, LocationStock,
    StockTransfer, StockTransferItem, GatePass, RawMaterialCategory, RawMaterial,
    RawMaterialStock, RawMaterialMovement, Recipe, RecipeIngredient,
    ProductionOrder, ProductionMaterialConsumption, TransferRequest,
    user_roles, role_permissions
)

from app.models_extended import (
    FeatureFlag, SMSTemplate, SMSLog, WhatsAppTemplate, WhatsAppLog,
    ExpenseCategory, Expense, ProductVariant, Promotion, PromotionUsage,
    GiftVoucher, GiftVoucherTransaction, Quotation, QuotationItem,
    Return, ReturnItem, SupplierPayment, SupplierLedger, CustomerCredit,
    DuePayment, DuePaymentInstallment, TaxRate, TaxReport,
    NotificationSetting, ScheduledTask
)


# =============================================================================
# USER MODEL TESTS
# =============================================================================

class TestUserModel:
    """Comprehensive tests for the User model."""

    def test_user_creation_basic(self, fresh_app):
        """Test basic user creation with required fields."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='testuser',
                email='test@example.com',
                full_name='Test User',
                role='cashier'
            )
            user.set_password('password123')
            db.session.add(user)
            db.session.commit()

            assert user.id is not None
            assert user.username == 'testuser'
            assert user.email == 'test@example.com'
            assert user.role == 'cashier'
            assert user.is_active is True
            assert user.is_global_admin is False

    def test_user_password_hashing(self, fresh_app):
        """Test password hashing and verification."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='hashtest',
                email='hash@test.com',
                full_name='Hash Test'
            )
            user.set_password('mypassword123')
            db.session.add(user)
            db.session.commit()

            # Password should be hashed
            assert user.password_hash != 'mypassword123'
            assert user.password_hash is not None
            assert len(user.password_hash) > 20

            # Verify correct password
            assert user.check_password('mypassword123') is True

            # Verify incorrect passwords
            assert user.check_password('wrongpassword') is False
            assert user.check_password('') is False
            assert user.check_password('MYPASSWORD123') is False  # Case sensitive

    @pytest.mark.parametrize('password', [
        '',
        ' ',
        'a',
        'ab',
        'abc',
        'a' * 1000,  # Very long password
        'password with spaces',
        'p@ssw0rd!#$%^&*()',
        '12345678',
        '\x00\x00\x00',  # Null bytes
        '\n\r\t',  # Whitespace characters
    ])
    def test_user_password_edge_cases(self, fresh_app, password):
        """Test password handling for various edge cases."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username=f'edgeuser_{hash(password) % 10000}',
                email=f'edge{hash(password) % 10000}@test.com',
                full_name='Edge Test'
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            # Should be able to verify the password
            assert user.check_password(password) is True

    def test_user_unique_username(self, fresh_app):
        """Test unique constraint on username."""
        with fresh_app.app_context():
            db.create_all()
            user1 = User(
                username='uniquetest',
                email='unique1@test.com',
                full_name='User 1'
            )
            user1.set_password('pass123')
            db.session.add(user1)
            db.session.commit()

            user2 = User(
                username='uniquetest',  # Duplicate username
                email='unique2@test.com',
                full_name='User 2'
            )
            user2.set_password('pass123')
            db.session.add(user2)

            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_user_unique_email(self, fresh_app):
        """Test unique constraint on email."""
        with fresh_app.app_context():
            db.create_all()
            user1 = User(
                username='emailtest1',
                email='duplicate@test.com',
                full_name='User 1'
            )
            user1.set_password('pass123')
            db.session.add(user1)
            db.session.commit()

            user2 = User(
                username='emailtest2',
                email='duplicate@test.com',  # Duplicate email
                full_name='User 2'
            )
            user2.set_password('pass123')
            db.session.add(user2)

            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_user_null_required_fields(self, fresh_app):
        """Test that required fields cannot be null."""
        with fresh_app.app_context():
            db.create_all()

            # Test null username
            user = User(
                username=None,
                email='null@test.com',
                full_name='Null Test'
            )
            user.set_password('pass123')
            db.session.add(user)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()

            # Test null email
            user2 = User(
                username='nullemail',
                email=None,
                full_name='Null Test'
            )
            user2.set_password('pass123')
            db.session.add(user2)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()

            # Test null full_name
            user3 = User(
                username='nullname',
                email='nullname@test.com',
                full_name=None
            )
            user3.set_password('pass123')
            db.session.add(user3)
            with pytest.raises(IntegrityError):
                db.session.commit()

    @pytest.mark.parametrize('role', [
        'admin',
        'manager',
        'cashier',
        'stock_manager',
        'accountant',
        'warehouse_manager',
        'kiosk_manager',
    ])
    def test_user_valid_roles(self, fresh_app, role):
        """Test user creation with all valid roles."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username=f'role_{role}',
                email=f'{role}@test.com',
                full_name=f'{role.title()} User',
                role=role
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            assert user.role == role

    def test_user_default_role(self, fresh_app):
        """Test default role assignment."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='defaultrole',
                email='default@test.com',
                full_name='Default Role'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            assert user.role == 'cashier'

    def test_user_is_active_default(self, fresh_app):
        """Test default is_active value."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='activetest',
                email='active@test.com',
                full_name='Active Test'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            assert user.is_active is True

    def test_user_inactive_state(self, fresh_app):
        """Test inactive user state."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='inactiveuser',
                email='inactive@test.com',
                full_name='Inactive User',
                is_active=False
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            assert user.is_active is False

    def test_user_global_admin_permissions(self, fresh_app):
        """Test global admin has all permissions."""
        with fresh_app.app_context():
            db.create_all()
            admin = User(
                username='globaladmin',
                email='globaladmin@test.com',
                full_name='Global Admin',
                role='cashier',  # Even with cashier role
                is_global_admin=True
            )
            admin.set_password('pass123')
            db.session.add(admin)
            db.session.commit()

            # Global admin should have all permissions
            assert admin.has_permission('any_permission') is True
            assert admin.has_permission('admin_only_permission') is True

    def test_user_admin_role_permissions(self, fresh_app):
        """Test admin role has all permissions."""
        with fresh_app.app_context():
            db.create_all()
            admin = User(
                username='roleadmin',
                email='roleadmin@test.com',
                full_name='Role Admin',
                role='admin'
            )
            admin.set_password('pass123')
            db.session.add(admin)
            db.session.commit()

            # Admin role should have all permissions
            assert admin.has_permission('any_permission') is True

    def test_user_location_access_global_admin(self, fresh_app):
        """Test global admin can access all locations."""
        with fresh_app.app_context():
            db.create_all()
            location = Location(
                code='LOC-001',
                name='Test Location',
                location_type='kiosk'
            )
            db.session.add(location)
            db.session.commit()

            admin = User(
                username='locadmin',
                email='locadmin@test.com',
                full_name='Location Admin',
                is_global_admin=True
            )
            admin.set_password('pass123')
            db.session.add(admin)
            db.session.commit()

            assert admin.can_access_location(location.id) is True
            assert admin.can_access_location(9999) is True  # Any location

    def test_user_location_access_regular_user(self, fresh_app):
        """Test regular user location access."""
        with fresh_app.app_context():
            db.create_all()
            location1 = Location(
                code='LOC-001',
                name='Location 1',
                location_type='kiosk'
            )
            location2 = Location(
                code='LOC-002',
                name='Location 2',
                location_type='kiosk'
            )
            db.session.add_all([location1, location2])
            db.session.commit()

            user = User(
                username='regularuser',
                email='regular@test.com',
                full_name='Regular User',
                location_id=location1.id
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            assert user.can_access_location(location1.id) is True
            assert user.can_access_location(location2.id) is False

    def test_user_timestamps(self, fresh_app):
        """Test created_at and updated_at timestamps."""
        with fresh_app.app_context():
            db.create_all()
            before_create = datetime.utcnow()

            user = User(
                username='timestamptest',
                email='timestamp@test.com',
                full_name='Timestamp Test'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            after_create = datetime.utcnow()

            assert user.created_at is not None
            assert before_create <= user.created_at <= after_create

    def test_user_repr(self, fresh_app):
        """Test user string representation."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='reprtest',
                email='repr@test.com',
                full_name='Repr Test'
            )
            user.set_password('pass123')

            assert repr(user) == '<User reprtest>'

    @pytest.mark.parametrize('username', [
        'a' * 64,  # Max length
        'user_with_underscore',
        'user123',
        'user-dash',
    ])
    def test_user_username_valid_formats(self, fresh_app, username):
        """Test valid username formats."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username=username,
                email=f'{hash(username) % 10000}@test.com',
                full_name='Format Test'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            assert user.username == username

    @pytest.mark.security
    @pytest.mark.parametrize('malicious_input', [
        "'; DROP TABLE users; --",
        "<script>alert('xss')</script>",
        "admin'--",
        "1 OR 1=1",
        "${7*7}",
        "{{7*7}}",
        "../../../etc/passwd",
        "\x00",  # Null byte
    ])
    def test_user_sql_injection_prevention(self, fresh_app, malicious_input):
        """Test SQL injection prevention in username/email."""
        with fresh_app.app_context():
            db.create_all()
            # These should be stored as-is, not executed
            user = User(
                username=f'sqltest_{hash(malicious_input) % 10000}',
                email=f'sql{hash(malicious_input) % 10000}@test.com',
                full_name=malicious_input
            )
            user.set_password(malicious_input)
            db.session.add(user)
            db.session.commit()

            # Verify data stored correctly (not executed)
            retrieved = User.query.get(user.id)
            assert retrieved.full_name == malicious_input

    @pytest.mark.parametrize('unicode_input', [
        'user_',
        '',
        '',
        '',
        '',
        '',
    ])
    def test_user_unicode_handling(self, fresh_app, unicode_input):
        """Test Unicode character handling in user fields."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username=f'unicode_{hash(unicode_input) % 10000}',
                email=f'unicode{hash(unicode_input) % 10000}@test.com',
                full_name=unicode_input
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            retrieved = User.query.get(user.id)
            assert retrieved.full_name == unicode_input


# =============================================================================
# ROLE AND PERMISSION MODEL TESTS
# =============================================================================

class TestRoleModel:
    """Tests for the Role model."""

    def test_role_creation(self, fresh_app):
        """Test basic role creation."""
        with fresh_app.app_context():
            db.create_all()
            role = Role(
                name='test_role',
                display_name='Test Role',
                description='A test role'
            )
            db.session.add(role)
            db.session.commit()

            assert role.id is not None
            assert role.name == 'test_role'
            assert role.is_system is False

    def test_role_unique_name(self, fresh_app):
        """Test unique constraint on role name."""
        with fresh_app.app_context():
            db.create_all()
            role1 = Role(name='unique_role', display_name='Unique Role')
            db.session.add(role1)
            db.session.commit()

            role2 = Role(name='unique_role', display_name='Duplicate')
            db.session.add(role2)
            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_role_system_flag(self, fresh_app):
        """Test system role flag."""
        with fresh_app.app_context():
            db.create_all()
            system_role = Role(
                name='system_admin',
                display_name='System Admin',
                is_system=True
            )
            db.session.add(system_role)
            db.session.commit()

            assert system_role.is_system is True

    def test_role_permission_relationship(self, fresh_app):
        """Test role-permission many-to-many relationship."""
        with fresh_app.app_context():
            db.create_all()
            role = Role(name='perm_test', display_name='Permission Test')
            perm1 = Permission(name='view_sales', display_name='View Sales')
            perm2 = Permission(name='create_sales', display_name='Create Sales')

            role.permissions.append(perm1)
            role.permissions.append(perm2)

            db.session.add(role)
            db.session.commit()

            assert len(role.permissions) == 2
            assert role.has_permission('view_sales') is True
            assert role.has_permission('create_sales') is True
            assert role.has_permission('delete_sales') is False


class TestPermissionModel:
    """Tests for the Permission model."""

    def test_permission_creation(self, fresh_app):
        """Test basic permission creation."""
        with fresh_app.app_context():
            db.create_all()
            perm = Permission(
                name='test_permission',
                display_name='Test Permission',
                description='A test permission',
                module='sales'
            )
            db.session.add(perm)
            db.session.commit()

            assert perm.id is not None
            assert perm.module == 'sales'

    def test_permission_unique_name(self, fresh_app):
        """Test unique constraint on permission name."""
        with fresh_app.app_context():
            db.create_all()
            perm1 = Permission(name='unique_perm', display_name='Unique')
            db.session.add(perm1)
            db.session.commit()

            perm2 = Permission(name='unique_perm', display_name='Duplicate')
            db.session.add(perm2)
            with pytest.raises(IntegrityError):
                db.session.commit()


# =============================================================================
# PRODUCT MODEL TESTS
# =============================================================================

class TestProductModel:
    """Comprehensive tests for the Product model."""

    def test_product_creation_basic(self, fresh_app):
        """Test basic product creation."""
        with fresh_app.app_context():
            db.create_all()
            product = Product(
                code='TEST001',
                name='Test Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            assert product.id is not None
            assert product.code == 'TEST001'
            assert product.is_active is True

    def test_product_unique_code(self, fresh_app):
        """Test unique constraint on product code."""
        with fresh_app.app_context():
            db.create_all()
            product1 = Product(
                code='UNIQUE001',
                name='Product 1',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product1)
            db.session.commit()

            product2 = Product(
                code='UNIQUE001',  # Duplicate code
                name='Product 2',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product2)
            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_product_unique_barcode(self, fresh_app):
        """Test unique constraint on barcode."""
        with fresh_app.app_context():
            db.create_all()
            product1 = Product(
                code='BARCODE001',
                barcode='1234567890123',
                name='Product 1',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product1)
            db.session.commit()

            product2 = Product(
                code='BARCODE002',
                barcode='1234567890123',  # Duplicate barcode
                name='Product 2',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product2)
            with pytest.raises(IntegrityError):
                db.session.commit()

    @pytest.mark.parametrize('cost,sell,expected_margin', [
        (Decimal('100.00'), Decimal('200.00'), 100.0),  # 100% margin
        (Decimal('100.00'), Decimal('150.00'), 50.0),   # 50% margin
        (Decimal('100.00'), Decimal('100.00'), 0.0),    # 0% margin
        (Decimal('200.00'), Decimal('100.00'), -50.0),  # Negative margin
        (Decimal('0.01'), Decimal('0.02'), 100.0),      # Small amounts
    ])
    def test_product_profit_margin(self, fresh_app, cost, sell, expected_margin):
        """Test profit margin calculation."""
        with fresh_app.app_context():
            db.create_all()
            product = Product(
                code=f'MARGIN_{hash((cost, sell)) % 10000}',
                name='Margin Test',
                cost_price=cost,
                selling_price=sell
            )
            db.session.add(product)
            db.session.commit()

            assert product.profit_margin == expected_margin

    def test_product_profit_margin_zero_cost(self, fresh_app):
        """Test profit margin with zero cost price."""
        with fresh_app.app_context():
            db.create_all()
            product = Product(
                code='ZEROCOST',
                name='Zero Cost',
                cost_price=Decimal('0.00'),
                selling_price=Decimal('100.00')
            )
            db.session.add(product)
            db.session.commit()

            assert product.profit_margin == 0

    @pytest.mark.parametrize('quantity,reorder,expected', [
        (5, 10, True),   # Below reorder level
        (10, 10, True),  # At reorder level
        (15, 10, False), # Above reorder level
        (0, 10, True),   # Zero stock
        (0, 0, True),    # Both zero
    ])
    def test_product_is_low_stock(self, fresh_app, quantity, reorder, expected):
        """Test low stock detection."""
        with fresh_app.app_context():
            db.create_all()
            product = Product(
                code=f'LOWSTOCK_{quantity}_{reorder}',
                name='Low Stock Test',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                quantity=quantity,
                reorder_level=reorder
            )
            db.session.add(product)
            db.session.commit()

            assert product.is_low_stock == expected

    def test_product_stock_value(self, fresh_app):
        """Test stock value calculation."""
        with fresh_app.app_context():
            db.create_all()
            product = Product(
                code='STOCKVAL',
                name='Stock Value Test',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                quantity=50
            )
            db.session.add(product)
            db.session.commit()

            assert product.stock_value == 5000.0  # 50 * 100

    def test_product_expiry_date_handling(self, fresh_app):
        """Test expiry date calculations."""
        with fresh_app.app_context():
            db.create_all()

            # Product with no expiry
            no_expiry = Product(
                code='NOEXPIRY',
                name='No Expiry',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(no_expiry)
            db.session.commit()

            assert no_expiry.days_until_expiry is None
            assert no_expiry.is_expired is False
            assert no_expiry.expiry_status == 'no_expiry'

    def test_product_expired(self, fresh_app):
        """Test expired product detection."""
        with fresh_app.app_context():
            db.create_all()

            # Expired product
            expired = Product(
                code='EXPIRED',
                name='Expired Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                expiry_date=date.today() - timedelta(days=1)
            )
            db.session.add(expired)
            db.session.commit()

            assert expired.is_expired is True
            assert expired.days_until_expiry < 0
            assert expired.expiry_status == 'expired'

    def test_product_expiring_soon(self, fresh_app):
        """Test expiring soon detection."""
        with fresh_app.app_context():
            db.create_all()

            # Expiring in 15 days
            expiring = Product(
                code='EXPIRING',
                name='Expiring Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                expiry_date=date.today() + timedelta(days=15)
            )
            db.session.add(expiring)
            db.session.commit()

            assert expiring.is_expiring_soon is True
            assert expiring.is_expiring_critical is False
            assert expiring.expiry_status == 'warning'

    def test_product_expiring_critical(self, fresh_app):
        """Test critical expiry detection."""
        with fresh_app.app_context():
            db.create_all()

            # Expiring in 3 days
            critical = Product(
                code='CRITICAL',
                name='Critical Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                expiry_date=date.today() + timedelta(days=3)
            )
            db.session.add(critical)
            db.session.commit()

            assert critical.is_expiring_critical is True
            assert critical.expiry_status == 'critical'

    def test_product_category_relationship(self, fresh_app):
        """Test product-category relationship."""
        with fresh_app.app_context():
            db.create_all()
            category = Category(name='Test Category')
            db.session.add(category)
            db.session.commit()

            product = Product(
                code='CATREL',
                name='Category Relationship',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                category_id=category.id
            )
            db.session.add(product)
            db.session.commit()

            assert product.category == category
            assert product in category.products.all()

    def test_product_supplier_relationship(self, fresh_app):
        """Test product-supplier relationship."""
        with fresh_app.app_context():
            db.create_all()
            supplier = Supplier(name='Test Supplier')
            db.session.add(supplier)
            db.session.commit()

            product = Product(
                code='SUPREL',
                name='Supplier Relationship',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                supplier_id=supplier.id
            )
            db.session.add(product)
            db.session.commit()

            assert product.supplier == supplier
            assert product in supplier.products.all()

    @pytest.mark.parametrize('price', [
        Decimal('0.00'),
        Decimal('0.01'),
        Decimal('9999999.99'),
        Decimal('1234567.89'),
    ])
    def test_product_price_boundaries(self, fresh_app, price):
        """Test price boundary values."""
        with fresh_app.app_context():
            db.create_all()
            product = Product(
                code=f'PRICE_{hash(str(price)) % 10000}',
                name='Price Test',
                cost_price=price,
                selling_price=price
            )
            db.session.add(product)
            db.session.commit()

            assert product.cost_price == price
            assert product.selling_price == price

    @pytest.mark.parametrize('quantity', [
        0,
        1,
        -1,  # Negative stock (edge case)
        2147483647,  # Max int
    ])
    def test_product_quantity_boundaries(self, fresh_app, quantity):
        """Test quantity boundary values."""
        with fresh_app.app_context():
            db.create_all()
            product = Product(
                code=f'QTY_{quantity}',
                name='Quantity Test',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                quantity=quantity
            )
            db.session.add(product)
            db.session.commit()

            assert product.quantity == quantity

    def test_product_manufactured_type(self, fresh_app):
        """Test manufactured product type."""
        with fresh_app.app_context():
            db.create_all()
            product = Product(
                code='MANUF001',
                name='Manufactured Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                product_type='manufactured',
                is_manufactured=True,
                can_be_reordered=False
            )
            db.session.add(product)
            db.session.commit()

            assert product.product_type == 'manufactured'
            assert product.is_manufactured is True
            assert product.can_be_reordered is False


# =============================================================================
# CATEGORY MODEL TESTS
# =============================================================================

class TestCategoryModel:
    """Tests for the Category model."""

    def test_category_creation(self, fresh_app):
        """Test basic category creation."""
        with fresh_app.app_context():
            db.create_all()
            category = Category(
                name='Test Category',
                description='A test category'
            )
            db.session.add(category)
            db.session.commit()

            assert category.id is not None
            assert category.name == 'Test Category'

    def test_category_unique_name(self, fresh_app):
        """Test unique constraint on category name."""
        with fresh_app.app_context():
            db.create_all()
            cat1 = Category(name='Unique Category')
            db.session.add(cat1)
            db.session.commit()

            cat2 = Category(name='Unique Category')
            db.session.add(cat2)
            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_category_hierarchy(self, fresh_app):
        """Test category parent-child relationship."""
        with fresh_app.app_context():
            db.create_all()
            parent = Category(name='Parent Category')
            db.session.add(parent)
            db.session.commit()

            child = Category(
                name='Child Category',
                parent_id=parent.id
            )
            db.session.add(child)
            db.session.commit()

            assert child.parent == parent
            assert child in parent.subcategories


# =============================================================================
# SUPPLIER MODEL TESTS
# =============================================================================

class TestSupplierModel:
    """Tests for the Supplier model."""

    def test_supplier_creation(self, fresh_app):
        """Test basic supplier creation."""
        with fresh_app.app_context():
            db.create_all()
            supplier = Supplier(
                name='Test Supplier',
                contact_person='John Doe',
                phone='+92-300-1234567',
                email='supplier@test.com',
                payment_terms='Net 30'
            )
            db.session.add(supplier)
            db.session.commit()

            assert supplier.id is not None
            assert supplier.is_active is True

    def test_supplier_unique_name(self, fresh_app):
        """Test unique constraint on supplier name."""
        with fresh_app.app_context():
            db.create_all()
            sup1 = Supplier(name='Unique Supplier')
            db.session.add(sup1)
            db.session.commit()

            sup2 = Supplier(name='Unique Supplier')
            db.session.add(sup2)
            with pytest.raises(IntegrityError):
                db.session.commit()


# =============================================================================
# CUSTOMER MODEL TESTS
# =============================================================================

class TestCustomerModel:
    """Comprehensive tests for the Customer model."""

    def test_customer_creation(self, fresh_app):
        """Test basic customer creation."""
        with fresh_app.app_context():
            db.create_all()
            customer = Customer(
                name='Test Customer',
                phone='03001234567',
                email='customer@test.com'
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.id is not None
            assert customer.customer_type == 'regular'
            assert customer.loyalty_points == 0

    def test_customer_unique_phone(self, fresh_app):
        """Test unique constraint on phone number."""
        with fresh_app.app_context():
            db.create_all()
            cust1 = Customer(name='Customer 1', phone='03001234567')
            db.session.add(cust1)
            db.session.commit()

            cust2 = Customer(name='Customer 2', phone='03001234567')
            db.session.add(cust2)
            with pytest.raises(IntegrityError):
                db.session.commit()

    @pytest.mark.parametrize('points,expected_tier', [
        (0, 'Bronze'),
        (499, 'Bronze'),
        (500, 'Silver'),
        (999, 'Silver'),
        (1000, 'Gold'),
        (2499, 'Gold'),
        (2500, 'Platinum'),
        (5000, 'Platinum'),
    ])
    def test_customer_loyalty_tier(self, fresh_app, points, expected_tier):
        """Test loyalty tier calculation."""
        with fresh_app.app_context():
            db.create_all()
            customer = Customer(
                name=f'Tier Test {points}',
                phone=f'0300{points:07d}',
                loyalty_points=points
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == expected_tier

    @pytest.mark.parametrize('points,expected_points_to_next', [
        (0, 500),      # Bronze -> Silver
        (499, 1),      # Bronze -> Silver
        (500, 500),    # Silver -> Gold
        (999, 1),      # Silver -> Gold
        (1000, 1500),  # Gold -> Platinum
        (2500, 0),     # Platinum (no next tier)
        (5000, 0),     # Platinum (no next tier)
    ])
    def test_customer_points_to_next_tier(self, fresh_app, points, expected_points_to_next):
        """Test points to next tier calculation."""
        with fresh_app.app_context():
            db.create_all()
            customer = Customer(
                name=f'Points Test {points}',
                phone=f'0300{points:07d}',
                loyalty_points=points
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.points_to_next_tier == expected_points_to_next

    def test_customer_add_loyalty_points(self, fresh_app):
        """Test adding loyalty points."""
        with fresh_app.app_context():
            db.create_all()
            customer = Customer(
                name='Points Test',
                phone='03009999999',
                loyalty_points=0
            )
            db.session.add(customer)
            db.session.commit()

            # Rs. 500 purchase = 5 points
            points_earned = customer.add_loyalty_points(500)
            assert points_earned == 5
            assert customer.loyalty_points == 5

            # Rs. 1000 purchase = 10 points
            points_earned = customer.add_loyalty_points(1000)
            assert points_earned == 10
            assert customer.loyalty_points == 15

    @pytest.mark.parametrize('initial_points,redeem,expected_success', [
        (500, 100, True),    # Valid redemption
        (500, 500, True),    # Redeem all points
        (500, 600, False),   # Insufficient points
        (100, 99, False),    # Below minimum (100)
        (0, 100, False),     # No points
    ])
    def test_customer_redeem_points(self, fresh_app, initial_points, redeem, expected_success):
        """Test redeeming loyalty points."""
        with fresh_app.app_context():
            db.create_all()
            customer = Customer(
                name=f'Redeem Test {initial_points}_{redeem}',
                phone=f'0300{initial_points:04d}{redeem:04d}',
                loyalty_points=initial_points
            )
            db.session.add(customer)
            db.session.commit()

            success, result = customer.redeem_points(redeem)
            assert success == expected_success

            if expected_success:
                assert customer.loyalty_points == initial_points - redeem
                assert result == redeem  # Discount amount

    def test_customer_types(self, fresh_app):
        """Test different customer types."""
        with fresh_app.app_context():
            db.create_all()
            types = ['regular', 'vip', 'wholesale']

            for ctype in types:
                customer = Customer(
                    name=f'{ctype.title()} Customer',
                    phone=f'030012345{types.index(ctype)}',
                    customer_type=ctype
                )
                db.session.add(customer)

            db.session.commit()

            for ctype in types:
                cust = Customer.query.filter_by(customer_type=ctype).first()
                assert cust is not None
                assert cust.customer_type == ctype

    def test_customer_birthday(self, fresh_app):
        """Test customer birthday field."""
        with fresh_app.app_context():
            db.create_all()
            customer = Customer(
                name='Birthday Test',
                phone='03008888888',
                birthday=date(1990, 5, 15)
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.birthday == date(1990, 5, 15)

    def test_customer_account_balance(self, fresh_app):
        """Test customer account balance."""
        with fresh_app.app_context():
            db.create_all()
            customer = Customer(
                name='Balance Test',
                phone='03007777777',
                account_balance=Decimal('5000.50')
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.account_balance == Decimal('5000.50')


# =============================================================================
# SALE AND SALE ITEM MODEL TESTS
# =============================================================================

class TestSaleModel:
    """Comprehensive tests for the Sale model."""

    def test_sale_creation(self, fresh_app):
        """Test basic sale creation."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='saleuser',
                email='sale@test.com',
                full_name='Sale User'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            sale = Sale(
                sale_number='SALE-001',
                user_id=user.id,
                payment_method='cash',
                total=Decimal('1000.00')
            )
            db.session.add(sale)
            db.session.commit()

            assert sale.id is not None
            assert sale.status == 'completed'
            assert sale.payment_status == 'paid'

    def test_sale_unique_number(self, fresh_app):
        """Test unique constraint on sale number."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='uniquesale',
                email='unique@test.com',
                full_name='Unique Sale'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            sale1 = Sale(
                sale_number='UNIQUE-001',
                user_id=user.id,
                payment_method='cash'
            )
            db.session.add(sale1)
            db.session.commit()

            sale2 = Sale(
                sale_number='UNIQUE-001',
                user_id=user.id,
                payment_method='cash'
            )
            db.session.add(sale2)
            with pytest.raises(IntegrityError):
                db.session.commit()

    @pytest.mark.parametrize('payment_method', [
        'cash',
        'card',
        'bank_transfer',
        'easypaisa',
        'jazzcash',
        'credit',
    ])
    def test_sale_payment_methods(self, fresh_app, payment_method):
        """Test various payment methods."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username=f'payuser_{payment_method}',
                email=f'{payment_method}@test.com',
                full_name='Payment User'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            sale = Sale(
                sale_number=f'PAY-{payment_method.upper()}',
                user_id=user.id,
                payment_method=payment_method
            )
            db.session.add(sale)
            db.session.commit()

            assert sale.payment_method == payment_method

    @pytest.mark.parametrize('status', [
        'completed',
        'refunded',
        'cancelled',
        'held',
    ])
    def test_sale_statuses(self, fresh_app, status):
        """Test sale status values."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username=f'statususer_{status}',
                email=f'{status}@test.com',
                full_name='Status User'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            sale = Sale(
                sale_number=f'STATUS-{status.upper()}',
                user_id=user.id,
                payment_method='cash',
                status=status
            )
            db.session.add(sale)
            db.session.commit()

            assert sale.status == status

    def test_sale_calculate_totals(self, fresh_app):
        """Test sale total calculation."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='totaluser',
                email='total@test.com',
                full_name='Total User'
            )
            user.set_password('pass123')
            db.session.add(user)

            product = Product(
                code='SALEP001',
                name='Sale Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            sale = Sale(
                sale_number='TOTAL-001',
                user_id=user.id,
                payment_method='cash'
            )
            db.session.add(sale)
            db.session.flush()

            # Add items
            item1 = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                quantity=2,
                unit_price=Decimal('200.00'),
                subtotal=Decimal('400.00')
            )
            item2 = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                quantity=1,
                unit_price=Decimal('200.00'),
                subtotal=Decimal('200.00')
            )
            db.session.add_all([item1, item2])
            db.session.commit()

            sale.calculate_totals()
            assert sale.subtotal == Decimal('600.00')

    def test_sale_discount_amount(self, fresh_app):
        """Test sale discount as amount."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='discountuser',
                email='discount@test.com',
                full_name='Discount User'
            )
            user.set_password('pass123')
            db.session.add(user)

            product = Product(
                code='DISCP001',
                name='Discount Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('1000.00')
            )
            db.session.add(product)
            db.session.commit()

            sale = Sale(
                sale_number='DISC-001',
                user_id=user.id,
                payment_method='cash',
                discount=Decimal('100.00'),
                discount_type='amount'
            )
            db.session.add(sale)
            db.session.flush()

            item = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                quantity=1,
                unit_price=Decimal('1000.00'),
                subtotal=Decimal('1000.00')
            )
            db.session.add(item)
            db.session.commit()

            sale.calculate_totals()
            assert sale.total == Decimal('900.00')  # 1000 - 100

    def test_sale_discount_percentage(self, fresh_app):
        """Test sale discount as percentage."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='percuser',
                email='perc@test.com',
                full_name='Percentage User'
            )
            user.set_password('pass123')
            db.session.add(user)

            product = Product(
                code='PERCP001',
                name='Percentage Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('1000.00')
            )
            db.session.add(product)
            db.session.commit()

            sale = Sale(
                sale_number='PERC-001',
                user_id=user.id,
                payment_method='cash',
                discount=Decimal('10.00'),  # 10%
                discount_type='percentage'
            )
            db.session.add(sale)
            db.session.flush()

            item = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                quantity=1,
                unit_price=Decimal('1000.00'),
                subtotal=Decimal('1000.00')
            )
            db.session.add(item)
            db.session.commit()

            sale.calculate_totals()
            assert sale.total == Decimal('900.00')  # 1000 - 10%

    def test_sale_with_customer(self, fresh_app):
        """Test sale with customer relationship."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='custuser',
                email='cust@test.com',
                full_name='Customer User'
            )
            user.set_password('pass123')

            customer = Customer(name='Sale Customer', phone='03001111111')
            db.session.add_all([user, customer])
            db.session.commit()

            sale = Sale(
                sale_number='CUST-001',
                user_id=user.id,
                customer_id=customer.id,
                payment_method='cash'
            )
            db.session.add(sale)
            db.session.commit()

            assert sale.customer == customer
            assert sale in customer.sales.all()


class TestSaleItemModel:
    """Tests for the SaleItem model."""

    def test_sale_item_creation(self, fresh_app):
        """Test basic sale item creation."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='itemuser',
                email='item@test.com',
                full_name='Item User'
            )
            user.set_password('pass123')

            product = Product(
                code='ITEM001',
                name='Item Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add_all([user, product])
            db.session.commit()

            sale = Sale(
                sale_number='ITEM-001',
                user_id=user.id,
                payment_method='cash'
            )
            db.session.add(sale)
            db.session.flush()

            item = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                quantity=5,
                unit_price=Decimal('200.00'),
                subtotal=Decimal('1000.00')
            )
            db.session.add(item)
            db.session.commit()

            assert item.id is not None
            assert item.sale == sale
            assert item.product == product

    def test_sale_item_calculate_subtotal(self, fresh_app):
        """Test sale item subtotal calculation."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='subuser',
                email='sub@test.com',
                full_name='Subtotal User'
            )
            user.set_password('pass123')

            product = Product(
                code='SUB001',
                name='Subtotal Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add_all([user, product])
            db.session.commit()

            sale = Sale(
                sale_number='SUB-001',
                user_id=user.id,
                payment_method='cash'
            )
            db.session.add(sale)
            db.session.flush()

            item = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                quantity=3,
                unit_price=Decimal('200.00'),
                discount=Decimal('50.00'),
                subtotal=Decimal('550.00')
            )
            db.session.add(item)
            db.session.commit()

            item.calculate_subtotal()
            assert item.subtotal == Decimal('550.00')  # (3 * 200) - 50

    def test_sale_item_cascade_delete(self, fresh_app):
        """Test cascade delete of sale items."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='cascadeuser',
                email='cascade@test.com',
                full_name='Cascade User'
            )
            user.set_password('pass123')

            product = Product(
                code='CASC001',
                name='Cascade Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add_all([user, product])
            db.session.commit()

            sale = Sale(
                sale_number='CASC-001',
                user_id=user.id,
                payment_method='cash'
            )
            db.session.add(sale)
            db.session.flush()

            item = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                quantity=1,
                unit_price=Decimal('200.00'),
                subtotal=Decimal('200.00')
            )
            db.session.add(item)
            db.session.commit()

            item_id = item.id

            # Delete sale should cascade to items
            db.session.delete(sale)
            db.session.commit()

            assert SaleItem.query.get(item_id) is None


# =============================================================================
# PAYMENT MODEL TESTS
# =============================================================================

class TestPaymentModel:
    """Tests for the Payment model."""

    def test_payment_creation(self, fresh_app):
        """Test basic payment creation."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='paymentuser',
                email='payment@test.com',
                full_name='Payment User'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            sale = Sale(
                sale_number='PAYMENT-001',
                user_id=user.id,
                payment_method='cash'
            )
            db.session.add(sale)
            db.session.commit()

            payment = Payment(
                sale_id=sale.id,
                amount=Decimal('500.00'),
                payment_method='cash',
                reference_number='REF123'
            )
            db.session.add(payment)
            db.session.commit()

            assert payment.id is not None
            assert payment.sale == sale


# =============================================================================
# STOCK MOVEMENT MODEL TESTS
# =============================================================================

class TestStockMovementModel:
    """Tests for the StockMovement model."""

    def test_stock_movement_creation(self, fresh_app):
        """Test basic stock movement creation."""
        with fresh_app.app_context():
            db.create_all()
            product = Product(
                code='MOVE001',
                name='Movement Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            movement = StockMovement(
                product_id=product.id,
                movement_type='purchase',
                quantity=100,
                reference='PO-001'
            )
            db.session.add(movement)
            db.session.commit()

            assert movement.id is not None
            assert movement.product == product

    @pytest.mark.parametrize('movement_type', [
        'purchase',
        'sale',
        'adjustment',
        'return',
        'damage',
        'transfer_in',
        'transfer_out',
    ])
    def test_stock_movement_types(self, fresh_app, movement_type):
        """Test various movement types."""
        with fresh_app.app_context():
            db.create_all()
            product = Product(
                code=f'MOVE_{movement_type}',
                name=f'Movement {movement_type}',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            movement = StockMovement(
                product_id=product.id,
                movement_type=movement_type,
                quantity=10 if movement_type in ['purchase', 'return', 'transfer_in'] else -10
            )
            db.session.add(movement)
            db.session.commit()

            assert movement.movement_type == movement_type


# =============================================================================
# LOCATION MODEL TESTS
# =============================================================================

class TestLocationModel:
    """Comprehensive tests for the Location model."""

    def test_location_creation(self, fresh_app):
        """Test basic location creation."""
        with fresh_app.app_context():
            db.create_all()
            location = Location(
                code='WH-TEST',
                name='Test Warehouse',
                location_type='warehouse',
                address='123 Test St',
                city='Test City'
            )
            db.session.add(location)
            db.session.commit()

            assert location.id is not None
            assert location.is_warehouse is True
            assert location.is_kiosk is False

    def test_location_unique_code(self, fresh_app):
        """Test unique constraint on location code."""
        with fresh_app.app_context():
            db.create_all()
            loc1 = Location(
                code='UNIQUE-LOC',
                name='Location 1',
                location_type='warehouse'
            )
            db.session.add(loc1)
            db.session.commit()

            loc2 = Location(
                code='UNIQUE-LOC',
                name='Location 2',
                location_type='kiosk'
            )
            db.session.add(loc2)
            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_location_warehouse_kiosk_relationship(self, fresh_app):
        """Test warehouse-kiosk parent-child relationship."""
        with fresh_app.app_context():
            db.create_all()
            warehouse = Location(
                code='WH-PARENT',
                name='Parent Warehouse',
                location_type='warehouse'
            )
            db.session.add(warehouse)
            db.session.commit()

            kiosk = Location(
                code='K-CHILD',
                name='Child Kiosk',
                location_type='kiosk',
                parent_warehouse_id=warehouse.id
            )
            db.session.add(kiosk)
            db.session.commit()

            assert kiosk.parent_warehouse == warehouse
            assert kiosk in warehouse.child_kiosks


# =============================================================================
# LOCATION STOCK MODEL TESTS
# =============================================================================

class TestLocationStockModel:
    """Tests for the LocationStock model."""

    def test_location_stock_creation(self, fresh_app):
        """Test basic location stock creation."""
        with fresh_app.app_context():
            db.create_all()
            location = Location(
                code='LS-LOC',
                name='Stock Location',
                location_type='warehouse'
            )
            product = Product(
                code='LS-PROD',
                name='Stock Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add_all([location, product])
            db.session.commit()

            stock = LocationStock(
                location_id=location.id,
                product_id=product.id,
                quantity=100,
                reserved_quantity=10
            )
            db.session.add(stock)
            db.session.commit()

            assert stock.id is not None
            assert stock.available_quantity == 90  # 100 - 10

    def test_location_stock_unique_constraint(self, fresh_app):
        """Test unique constraint on location-product combination."""
        with fresh_app.app_context():
            db.create_all()
            location = Location(
                code='UNIQUE-LS',
                name='Unique Location',
                location_type='warehouse'
            )
            product = Product(
                code='UNIQUE-LP',
                name='Unique Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add_all([location, product])
            db.session.commit()

            stock1 = LocationStock(
                location_id=location.id,
                product_id=product.id,
                quantity=100
            )
            db.session.add(stock1)
            db.session.commit()

            stock2 = LocationStock(
                location_id=location.id,
                product_id=product.id,
                quantity=50
            )
            db.session.add(stock2)
            with pytest.raises(IntegrityError):
                db.session.commit()

    @pytest.mark.parametrize('quantity,reserved,expected_available', [
        (100, 0, 100),
        (100, 50, 50),
        (100, 100, 0),
        (100, 150, 0),  # More reserved than available - should return 0
        (0, 0, 0),
    ])
    def test_location_stock_available_quantity(self, fresh_app, quantity, reserved, expected_available):
        """Test available quantity calculation."""
        with fresh_app.app_context():
            db.create_all()
            location = Location(
                code=f'AVAIL-{quantity}-{reserved}',
                name='Availability Location',
                location_type='warehouse'
            )
            product = Product(
                code=f'AVAIL-P-{quantity}-{reserved}',
                name='Availability Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add_all([location, product])
            db.session.commit()

            stock = LocationStock(
                location_id=location.id,
                product_id=product.id,
                quantity=quantity,
                reserved_quantity=reserved
            )
            db.session.add(stock)
            db.session.commit()

            assert stock.available_quantity == expected_available


# =============================================================================
# STOCK TRANSFER MODEL TESTS
# =============================================================================

class TestStockTransferModel:
    """Tests for the StockTransfer model."""

    def test_transfer_creation(self, fresh_app):
        """Test basic stock transfer creation."""
        with fresh_app.app_context():
            db.create_all()
            source = Location(
                code='TRANS-SRC',
                name='Source Location',
                location_type='warehouse'
            )
            dest = Location(
                code='TRANS-DST',
                name='Destination Location',
                location_type='kiosk'
            )
            db.session.add_all([source, dest])
            db.session.commit()

            transfer = StockTransfer(
                transfer_number='TRF-001',
                source_location_id=source.id,
                destination_location_id=dest.id
            )
            db.session.add(transfer)
            db.session.commit()

            assert transfer.id is not None
            assert transfer.status == 'draft'

    def test_transfer_unique_number(self, fresh_app):
        """Test unique constraint on transfer number."""
        with fresh_app.app_context():
            db.create_all()
            source = Location(
                code='TRF-UNQ-SRC',
                name='Source',
                location_type='warehouse'
            )
            dest = Location(
                code='TRF-UNQ-DST',
                name='Dest',
                location_type='kiosk'
            )
            db.session.add_all([source, dest])
            db.session.commit()

            transfer1 = StockTransfer(
                transfer_number='UNIQUE-TRF',
                source_location_id=source.id,
                destination_location_id=dest.id
            )
            db.session.add(transfer1)
            db.session.commit()

            transfer2 = StockTransfer(
                transfer_number='UNIQUE-TRF',
                source_location_id=source.id,
                destination_location_id=dest.id
            )
            db.session.add(transfer2)
            with pytest.raises(IntegrityError):
                db.session.commit()

    @pytest.mark.parametrize('status,can_approve,can_dispatch,can_receive,can_cancel', [
        ('draft', False, False, False, True),
        ('requested', True, False, False, True),
        ('approved', False, True, False, True),
        ('dispatched', False, False, True, False),
        ('received', False, False, False, False),
        ('rejected', False, False, False, False),
        ('cancelled', False, False, False, False),
    ])
    def test_transfer_status_workflow(self, fresh_app, status, can_approve, can_dispatch, can_receive, can_cancel):
        """Test transfer status workflow flags."""
        with fresh_app.app_context():
            db.create_all()
            source = Location(
                code=f'WF-SRC-{status}',
                name='Source',
                location_type='warehouse'
            )
            dest = Location(
                code=f'WF-DST-{status}',
                name='Dest',
                location_type='kiosk'
            )
            db.session.add_all([source, dest])
            db.session.commit()

            transfer = StockTransfer(
                transfer_number=f'WF-{status}',
                source_location_id=source.id,
                destination_location_id=dest.id,
                status=status
            )
            db.session.add(transfer)
            db.session.commit()

            assert transfer.can_approve == can_approve
            assert transfer.can_dispatch == can_dispatch
            assert transfer.can_receive == can_receive
            assert transfer.can_cancel == can_cancel


# =============================================================================
# PURCHASE ORDER MODEL TESTS
# =============================================================================

class TestPurchaseOrderModel:
    """Tests for the PurchaseOrder model."""

    def test_po_creation(self, fresh_app):
        """Test basic purchase order creation."""
        with fresh_app.app_context():
            db.create_all()
            supplier = Supplier(name='PO Supplier')
            db.session.add(supplier)
            db.session.commit()

            po = PurchaseOrder(
                po_number='PO-001',
                supplier_id=supplier.id
            )
            db.session.add(po)
            db.session.commit()

            assert po.id is not None
            assert po.status == 'pending'

    def test_po_unique_number(self, fresh_app):
        """Test unique constraint on PO number."""
        with fresh_app.app_context():
            db.create_all()
            supplier = Supplier(name='Unique PO Supplier')
            db.session.add(supplier)
            db.session.commit()

            po1 = PurchaseOrder(
                po_number='UNIQUE-PO',
                supplier_id=supplier.id
            )
            db.session.add(po1)
            db.session.commit()

            po2 = PurchaseOrder(
                po_number='UNIQUE-PO',
                supplier_id=supplier.id
            )
            db.session.add(po2)
            with pytest.raises(IntegrityError):
                db.session.commit()


# =============================================================================
# DAY CLOSE MODEL TESTS
# =============================================================================

class TestDayCloseModel:
    """Tests for the DayClose model."""

    def test_dayclose_creation(self, fresh_app):
        """Test basic day close creation."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='closeuser',
                email='close@test.com',
                full_name='Close User'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            dayclose = DayClose(
                close_date=date.today(),
                closed_by=user.id,
                total_sales=50,
                total_revenue=Decimal('50000.00')
            )
            db.session.add(dayclose)
            db.session.commit()

            assert dayclose.id is not None

    def test_dayclose_unique_per_location(self, fresh_app):
        """Test unique constraint per date and location."""
        with fresh_app.app_context():
            db.create_all()
            location = Location(
                code='DC-LOC',
                name='Day Close Location',
                location_type='kiosk'
            )
            user = User(
                username='dcuser',
                email='dc@test.com',
                full_name='DC User'
            )
            user.set_password('pass123')
            db.session.add_all([location, user])
            db.session.commit()

            dc1 = DayClose(
                close_date=date.today(),
                closed_by=user.id,
                location_id=location.id
            )
            db.session.add(dc1)
            db.session.commit()

            dc2 = DayClose(
                close_date=date.today(),
                closed_by=user.id,
                location_id=location.id
            )
            db.session.add(dc2)
            with pytest.raises(IntegrityError):
                db.session.commit()


# =============================================================================
# EXTENDED MODELS TESTS
# =============================================================================

class TestFeatureFlagModel:
    """Tests for the FeatureFlag model."""

    def test_feature_flag_creation(self, fresh_app):
        """Test basic feature flag creation."""
        with fresh_app.app_context():
            db.create_all()
            flag = FeatureFlag(
                name='test_feature',
                display_name='Test Feature',
                description='A test feature',
                category='general'
            )
            db.session.add(flag)
            db.session.commit()

            assert flag.id is not None
            assert flag.is_enabled is False

    def test_feature_flag_unique_name(self, fresh_app):
        """Test unique constraint on feature flag name."""
        with fresh_app.app_context():
            db.create_all()
            flag1 = FeatureFlag(
                name='unique_flag',
                display_name='Unique Flag'
            )
            db.session.add(flag1)
            db.session.commit()

            flag2 = FeatureFlag(
                name='unique_flag',
                display_name='Duplicate'
            )
            db.session.add(flag2)
            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_feature_flag_is_enabled_check(self, fresh_app):
        """Test is_feature_enabled static method."""
        with fresh_app.app_context():
            db.create_all()

            # Non-existent feature
            assert FeatureFlag.is_feature_enabled('nonexistent') is False

            # Disabled feature
            disabled = FeatureFlag(
                name='disabled_feature',
                display_name='Disabled',
                is_enabled=False
            )
            db.session.add(disabled)
            db.session.commit()
            assert FeatureFlag.is_feature_enabled('disabled_feature') is False

            # Enabled feature without config requirement
            enabled = FeatureFlag(
                name='enabled_feature',
                display_name='Enabled',
                is_enabled=True,
                requires_config=False
            )
            db.session.add(enabled)
            db.session.commit()
            assert FeatureFlag.is_feature_enabled('enabled_feature') is True

            # Feature requiring config but not configured
            needs_config = FeatureFlag(
                name='needs_config',
                display_name='Needs Config',
                is_enabled=True,
                requires_config=True,
                is_configured=False
            )
            db.session.add(needs_config)
            db.session.commit()
            assert FeatureFlag.is_feature_enabled('needs_config') is False


class TestPromotionModel:
    """Tests for the Promotion model."""

    def test_promotion_creation(self, fresh_app):
        """Test basic promotion creation."""
        with fresh_app.app_context():
            db.create_all()
            promo = Promotion(
                code='PROMO001',
                name='Test Promotion',
                promotion_type='percentage',
                discount_value=Decimal('10.00'),
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=30)
            )
            db.session.add(promo)
            db.session.commit()

            assert promo.id is not None
            assert promo.is_active is True

    def test_promotion_unique_code(self, fresh_app):
        """Test unique constraint on promotion code."""
        with fresh_app.app_context():
            db.create_all()
            promo1 = Promotion(
                code='UNIQUE-PROMO',
                name='Promo 1',
                promotion_type='percentage',
                discount_value=Decimal('10.00'),
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=30)
            )
            db.session.add(promo1)
            db.session.commit()

            promo2 = Promotion(
                code='UNIQUE-PROMO',
                name='Promo 2',
                promotion_type='fixed_amount',
                discount_value=Decimal('100.00'),
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=30)
            )
            db.session.add(promo2)
            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_promotion_is_valid(self, fresh_app):
        """Test promotion validity check."""
        with fresh_app.app_context():
            db.create_all()

            # Valid promotion
            valid_promo = Promotion(
                code='VALID-PROMO',
                name='Valid',
                promotion_type='percentage',
                discount_value=Decimal('10.00'),
                start_date=datetime.utcnow() - timedelta(days=1),
                end_date=datetime.utcnow() + timedelta(days=30),
                is_active=True
            )
            db.session.add(valid_promo)
            db.session.commit()
            assert valid_promo.is_valid is True

            # Expired promotion
            expired_promo = Promotion(
                code='EXPIRED-PROMO',
                name='Expired',
                promotion_type='percentage',
                discount_value=Decimal('10.00'),
                start_date=datetime.utcnow() - timedelta(days=60),
                end_date=datetime.utcnow() - timedelta(days=30),
                is_active=True
            )
            db.session.add(expired_promo)
            db.session.commit()
            assert expired_promo.is_valid is False

            # Inactive promotion
            inactive_promo = Promotion(
                code='INACTIVE-PROMO',
                name='Inactive',
                promotion_type='percentage',
                discount_value=Decimal('10.00'),
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=30),
                is_active=False
            )
            db.session.add(inactive_promo)
            db.session.commit()
            assert inactive_promo.is_valid is False


class TestGiftVoucherModel:
    """Tests for the GiftVoucher model."""

    def test_voucher_creation(self, fresh_app):
        """Test basic gift voucher creation."""
        with fresh_app.app_context():
            db.create_all()
            voucher = GiftVoucher(
                code='GIFT001',
                initial_value=Decimal('1000.00'),
                current_balance=Decimal('1000.00'),
                valid_until=datetime.utcnow() + timedelta(days=365)
            )
            db.session.add(voucher)
            db.session.commit()

            assert voucher.id is not None
            assert voucher.status == 'active'

    def test_voucher_unique_code(self, fresh_app):
        """Test unique constraint on voucher code."""
        with fresh_app.app_context():
            db.create_all()
            voucher1 = GiftVoucher(
                code='UNIQUE-GIFT',
                initial_value=Decimal('1000.00'),
                current_balance=Decimal('1000.00'),
                valid_until=datetime.utcnow() + timedelta(days=365)
            )
            db.session.add(voucher1)
            db.session.commit()

            voucher2 = GiftVoucher(
                code='UNIQUE-GIFT',
                initial_value=Decimal('500.00'),
                current_balance=Decimal('500.00'),
                valid_until=datetime.utcnow() + timedelta(days=365)
            )
            db.session.add(voucher2)
            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_voucher_is_valid(self, fresh_app):
        """Test voucher validity check."""
        with fresh_app.app_context():
            db.create_all()

            # Valid voucher
            valid_voucher = GiftVoucher(
                code='VALID-GIFT',
                initial_value=Decimal('1000.00'),
                current_balance=Decimal('1000.00'),
                valid_from=datetime.utcnow() - timedelta(days=1),
                valid_until=datetime.utcnow() + timedelta(days=365),
                status='active'
            )
            db.session.add(valid_voucher)
            db.session.commit()
            assert valid_voucher.is_valid is True

            # Zero balance voucher
            zero_voucher = GiftVoucher(
                code='ZERO-GIFT',
                initial_value=Decimal('1000.00'),
                current_balance=Decimal('0.00'),
                valid_until=datetime.utcnow() + timedelta(days=365),
                status='active'
            )
            db.session.add(zero_voucher)
            db.session.commit()
            assert zero_voucher.is_valid is False


class TestDuePaymentModel:
    """Tests for the DuePayment model."""

    def test_due_payment_creation(self, fresh_app):
        """Test basic due payment creation."""
        with fresh_app.app_context():
            db.create_all()
            customer = Customer(name='Due Customer', phone='03001112222')
            user = User(
                username='dueuser',
                email='due@test.com',
                full_name='Due User'
            )
            user.set_password('pass123')
            db.session.add_all([customer, user])
            db.session.commit()

            sale = Sale(
                sale_number='DUE-001',
                user_id=user.id,
                payment_method='credit'
            )
            db.session.add(sale)
            db.session.commit()

            due_payment = DuePayment(
                customer_id=customer.id,
                sale_id=sale.id,
                total_amount=Decimal('5000.00'),
                due_amount=Decimal('5000.00'),
                due_date=date.today() + timedelta(days=30)
            )
            db.session.add(due_payment)
            db.session.commit()

            assert due_payment.id is not None
            assert due_payment.status == 'pending'

    def test_due_payment_overdue(self, fresh_app):
        """Test overdue detection."""
        with fresh_app.app_context():
            db.create_all()
            customer = Customer(name='Overdue Customer', phone='03003334444')
            user = User(
                username='overdueuser',
                email='overdue@test.com',
                full_name='Overdue User'
            )
            user.set_password('pass123')
            db.session.add_all([customer, user])
            db.session.commit()

            sale = Sale(
                sale_number='OVERDUE-001',
                user_id=user.id,
                payment_method='credit'
            )
            db.session.add(sale)
            db.session.commit()

            # Overdue payment
            overdue = DuePayment(
                customer_id=customer.id,
                sale_id=sale.id,
                total_amount=Decimal('5000.00'),
                due_amount=Decimal('5000.00'),
                due_date=date.today() - timedelta(days=10)
            )
            db.session.add(overdue)
            db.session.commit()

            assert overdue.is_overdue is True
            assert overdue.days_overdue == 10


# =============================================================================
# PRODUCTION MODELS TESTS
# =============================================================================

class TestRawMaterialModel:
    """Tests for the RawMaterial model."""

    def test_raw_material_creation(self, fresh_app):
        """Test basic raw material creation."""
        with fresh_app.app_context():
            db.create_all()
            category = RawMaterialCategory(
                code='OIL',
                name='Oils',
                unit='ml'
            )
            db.session.add(category)
            db.session.commit()

            material = RawMaterial(
                code='OIL-001',
                name='Rose Oil',
                category_id=category.id,
                cost_per_unit=Decimal('500.00')
            )
            db.session.add(material)
            db.session.commit()

            assert material.id is not None
            assert material.unit == 'ml'


class TestRecipeModel:
    """Tests for the Recipe model."""

    def test_recipe_creation(self, fresh_app):
        """Test basic recipe creation."""
        with fresh_app.app_context():
            db.create_all()
            recipe = Recipe(
                code='RCP-001',
                name='Rose Attar 6ml',
                recipe_type='single_oil',
                output_size_ml=Decimal('6.00'),
                oil_percentage=Decimal('100.00')
            )
            db.session.add(recipe)
            db.session.commit()

            assert recipe.id is not None
            assert recipe.is_active is True


class TestProductionOrderModel:
    """Tests for the ProductionOrder model."""

    def test_production_order_creation(self, fresh_app):
        """Test basic production order creation."""
        with fresh_app.app_context():
            db.create_all()
            location = Location(
                code='PROD-LOC',
                name='Production Location',
                location_type='warehouse'
            )
            recipe = Recipe(
                code='RCP-PROD',
                name='Production Recipe',
                recipe_type='single_oil'
            )
            product = Product(
                code='PROD-001',
                name='Production Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add_all([location, recipe, product])
            db.session.commit()

            order = ProductionOrder(
                order_number='PRD-001',
                recipe_id=recipe.id,
                product_id=product.id,
                location_id=location.id,
                quantity_ordered=100
            )
            db.session.add(order)
            db.session.commit()

            assert order.id is not None
            assert order.status == 'draft'

    @pytest.mark.parametrize('status,can_approve,can_start,can_complete,can_cancel', [
        ('draft', False, False, False, True),
        ('pending', True, False, False, True),
        ('approved', False, True, False, True),
        ('in_progress', False, False, True, False),
        ('completed', False, False, False, False),
        ('rejected', False, False, False, False),
        ('cancelled', False, False, False, False),
    ])
    def test_production_status_workflow(self, fresh_app, status, can_approve, can_start, can_complete, can_cancel):
        """Test production order status workflow."""
        with fresh_app.app_context():
            db.create_all()
            location = Location(
                code=f'PROD-WF-{status}',
                name='Workflow Location',
                location_type='warehouse'
            )
            recipe = Recipe(
                code=f'RCP-WF-{status}',
                name='Workflow Recipe',
                recipe_type='single_oil'
            )
            product = Product(
                code=f'PROD-WF-{status}',
                name='Workflow Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add_all([location, recipe, product])
            db.session.commit()

            order = ProductionOrder(
                order_number=f'PRD-WF-{status}',
                recipe_id=recipe.id,
                product_id=product.id,
                location_id=location.id,
                quantity_ordered=100,
                status=status
            )
            db.session.add(order)
            db.session.commit()

            assert order.can_approve == can_approve
            assert order.can_start == can_start
            assert order.can_complete == can_complete
            assert order.can_cancel == can_cancel


# =============================================================================
# CONCURRENT ACCESS TESTS
# =============================================================================

class TestConcurrentAccess:
    """Tests for concurrent database access scenarios."""

    @pytest.mark.slow
    def test_concurrent_product_update(self, fresh_app):
        """Test concurrent product updates."""
        with fresh_app.app_context():
            db.create_all()
            product = Product(
                code='CONC-001',
                name='Concurrent Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                quantity=100
            )
            db.session.add(product)
            db.session.commit()
            product_id = product.id

        results = []
        errors = []

        def update_stock(increment):
            try:
                with fresh_app.app_context():
                    prod = Product.query.get(product_id)
                    if prod:
                        prod.quantity += increment
                        db.session.commit()
                        results.append(prod.quantity)
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(5):
            t = threading.Thread(target=update_stock, args=(10,))
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Verify no errors occurred
        assert len(errors) == 0

    @pytest.mark.slow
    def test_concurrent_user_creation(self, fresh_app):
        """Test concurrent user creation with unique constraints."""
        errors = []
        successes = []

        def create_user(index):
            try:
                with fresh_app.app_context():
                    user = User(
                        username=f'concurrent_user_{index}',
                        email=f'concurrent{index}@test.com',
                        full_name=f'Concurrent User {index}'
                    )
                    user.set_password('pass123')
                    db.session.add(user)
                    db.session.commit()
                    successes.append(index)
            except Exception as e:
                errors.append(str(e))

        with fresh_app.app_context():
            db.create_all()

        threads = []
        for i in range(10):
            t = threading.Thread(target=create_user, args=(i,))
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # All should succeed with unique indices
        assert len(errors) == 0
        assert len(successes) == 10


# =============================================================================
# EDGE CASE AND BOUNDARY TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for various edge cases and boundary conditions."""

    def test_empty_string_handling(self, fresh_app):
        """Test handling of empty strings."""
        with fresh_app.app_context():
            db.create_all()

            # Empty string for optional fields should work
            product = Product(
                code='EMPTY001',
                name='Empty Test',
                description='',  # Empty description
                brand='',  # Empty brand
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            assert product.description == ''
            assert product.brand == ''

    def test_very_long_text_fields(self, fresh_app):
        """Test handling of very long text fields."""
        with fresh_app.app_context():
            db.create_all()
            long_text = 'A' * 10000

            product = Product(
                code='LONG001',
                name='Long Test',
                description=long_text,
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            assert len(product.description) == 10000

    @pytest.mark.security
    def test_xss_attempt_storage(self, fresh_app):
        """Test that XSS attempts are stored as-is (not executed on storage)."""
        with fresh_app.app_context():
            db.create_all()
            xss_payload = '<script>alert("xss")</script>'

            customer = Customer(
                name=xss_payload,
                phone='03005555555',
                address=xss_payload
            )
            db.session.add(customer)
            db.session.commit()

            retrieved = Customer.query.get(customer.id)
            # Should be stored as-is
            assert retrieved.name == xss_payload
            assert retrieved.address == xss_payload

    def test_decimal_precision(self, fresh_app):
        """Test decimal precision for monetary fields."""
        with fresh_app.app_context():
            db.create_all()
            product = Product(
                code='PREC001',
                name='Precision Test',
                cost_price=Decimal('123.456'),  # More than 2 decimal places
                selling_price=Decimal('0.01')   # Minimum positive value
            )
            db.session.add(product)
            db.session.commit()

            # Check rounding behavior
            assert product.cost_price == Decimal('123.46') or product.cost_price == Decimal('123.456')

    def test_null_foreign_key(self, fresh_app):
        """Test nullable foreign key handling."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='nullfk',
                email='nullfk@test.com',
                full_name='Null FK Test',
                location_id=None  # Nullable FK
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            assert user.location_id is None
            assert user.location is None

    def test_orphan_handling(self, fresh_app):
        """Test orphan record handling."""
        with fresh_app.app_context():
            db.create_all()
            supplier = Supplier(name='Orphan Supplier')
            db.session.add(supplier)
            db.session.commit()
            supplier_id = supplier.id

            product = Product(
                code='ORPHAN001',
                name='Orphan Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                supplier_id=supplier_id
            )
            db.session.add(product)
            db.session.commit()

            # Delete supplier - product should have null reference
            # Note: This depends on cascade behavior in the model
            db.session.delete(supplier)
            try:
                db.session.commit()
                # If no error, check product
                retrieved = Product.query.filter_by(code='ORPHAN001').first()
                # Either product was deleted (cascade) or supplier_id is null
            except IntegrityError:
                # Foreign key constraint prevents deletion
                db.session.rollback()

    def test_boolean_field_defaults(self, fresh_app):
        """Test boolean field default values."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='booltest',
                email='bool@test.com',
                full_name='Bool Test'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            assert user.is_active is True
            assert user.is_global_admin is False

    def test_datetime_default_values(self, fresh_app):
        """Test datetime default values."""
        with fresh_app.app_context():
            db.create_all()
            before = datetime.utcnow()

            product = Product(
                code='DATETIME001',
                name='Datetime Test',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            after = datetime.utcnow()

            assert product.created_at is not None
            assert before <= product.created_at <= after


# =============================================================================
# SETTING MODEL TESTS
# =============================================================================

class TestSettingModel:
    """Tests for the Setting model."""

    def test_setting_creation(self, fresh_app):
        """Test basic setting creation."""
        with fresh_app.app_context():
            db.create_all()
            setting = Setting(
                key='test_setting',
                value='test_value',
                category='general',
                description='A test setting'
            )
            db.session.add(setting)
            db.session.commit()

            assert setting.id is not None
            assert setting.key == 'test_setting'

    def test_setting_unique_key(self, fresh_app):
        """Test unique constraint on setting key."""
        with fresh_app.app_context():
            db.create_all()
            setting1 = Setting(key='unique_key', value='value1')
            db.session.add(setting1)
            db.session.commit()

            setting2 = Setting(key='unique_key', value='value2')
            db.session.add(setting2)
            with pytest.raises(IntegrityError):
                db.session.commit()


# =============================================================================
# ACTIVITY LOG MODEL TESTS
# =============================================================================

class TestActivityLogModel:
    """Tests for the ActivityLog model."""

    def test_activity_log_creation(self, fresh_app):
        """Test basic activity log creation."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='loguser',
                email='log@test.com',
                full_name='Log User'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            log = ActivityLog(
                user_id=user.id,
                action='created_product',
                entity_type='product',
                entity_id=1,
                details='Created product PRD001',
                ip_address='192.168.1.1'
            )
            db.session.add(log)
            db.session.commit()

            assert log.id is not None
            assert log.user == user


# =============================================================================
# REPORT MODEL TESTS
# =============================================================================

class TestReportModel:
    """Tests for the Report model."""

    def test_report_creation(self, fresh_app):
        """Test basic report creation."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='reportuser',
                email='report@test.com',
                full_name='Report User'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            report = Report(
                report_type='daily',
                report_date=date.today(),
                generated_by=user.id
            )
            db.session.add(report)
            db.session.commit()

            assert report.id is not None
            assert report.status == 'generated'


# =============================================================================
# SYNC QUEUE MODEL TESTS
# =============================================================================

class TestSyncQueueModel:
    """Tests for the SyncQueue model."""

    def test_sync_queue_creation(self, fresh_app):
        """Test basic sync queue entry creation."""
        with fresh_app.app_context():
            db.create_all()
            sync = SyncQueue(
                table_name='products',
                operation='insert',
                record_id=1,
                data_json='{"code": "PRD001"}'
            )
            db.session.add(sync)
            db.session.commit()

            assert sync.id is not None
            assert sync.status == 'pending'


# =============================================================================
# TAX MODELS TESTS
# =============================================================================

class TestTaxModels:
    """Tests for tax-related models."""

    def test_tax_rate_creation(self, fresh_app):
        """Test basic tax rate creation."""
        with fresh_app.app_context():
            db.create_all()
            tax = TaxRate(
                name='GST',
                rate=Decimal('17.00'),
                effective_from=date.today()
            )
            db.session.add(tax)
            db.session.commit()

            assert tax.id is not None
            assert tax.is_active is True


# =============================================================================
# NOTIFICATION MODELS TESTS
# =============================================================================

class TestNotificationModels:
    """Tests for notification-related models."""

    def test_notification_setting_creation(self, fresh_app):
        """Test notification setting creation."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='notifuser',
                email='notif@test.com',
                full_name='Notification User'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            setting = NotificationSetting(
                user_id=user.id,
                email_daily_report=True,
                sms_daily_summary=False
            )
            db.session.add(setting)
            db.session.commit()

            assert setting.id is not None

    def test_notification_setting_unique_user(self, fresh_app):
        """Test unique constraint on notification setting per user."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='uniqnotif',
                email='uniqnotif@test.com',
                full_name='Unique Notif User'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            setting1 = NotificationSetting(user_id=user.id)
            db.session.add(setting1)
            db.session.commit()

            setting2 = NotificationSetting(user_id=user.id)
            db.session.add(setting2)
            with pytest.raises(IntegrityError):
                db.session.commit()


# =============================================================================
# EXPENSE MODELS TESTS
# =============================================================================

class TestExpenseModels:
    """Tests for expense-related models."""

    def test_expense_category_creation(self, fresh_app):
        """Test expense category creation."""
        with fresh_app.app_context():
            db.create_all()
            category = ExpenseCategory(
                name='Utilities',
                description='Utility bills',
                icon='bolt',
                color='#3B82F6'
            )
            db.session.add(category)
            db.session.commit()

            assert category.id is not None
            assert category.is_active is True

    def test_expense_creation(self, fresh_app):
        """Test expense creation."""
        with fresh_app.app_context():
            db.create_all()
            category = ExpenseCategory(name='Test Category')
            user = User(
                username='expuser',
                email='exp@test.com',
                full_name='Expense User'
            )
            user.set_password('pass123')
            db.session.add_all([category, user])
            db.session.commit()

            expense = Expense(
                expense_number='EXP-001',
                category_id=category.id,
                description='Office supplies',
                amount=Decimal('5000.00'),
                created_by=user.id
            )
            db.session.add(expense)
            db.session.commit()

            assert expense.id is not None
            assert expense.status == 'pending'


# =============================================================================
# RETURN MODELS TESTS
# =============================================================================

class TestReturnModels:
    """Tests for return-related models."""

    def test_return_creation(self, fresh_app):
        """Test return creation."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='returnuser',
                email='return@test.com',
                full_name='Return User'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            sale = Sale(
                sale_number='RETURN-SALE-001',
                user_id=user.id,
                payment_method='cash'
            )
            db.session.add(sale)
            db.session.commit()

            return_order = Return(
                return_number='RET-001',
                sale_id=sale.id,
                return_type='refund',
                return_reason='damaged',
                processed_by=user.id
            )
            db.session.add(return_order)
            db.session.commit()

            assert return_order.id is not None
            assert return_order.status == 'pending'


# =============================================================================
# QUOTATION MODELS TESTS
# =============================================================================

class TestQuotationModels:
    """Tests for quotation-related models."""

    def test_quotation_creation(self, fresh_app):
        """Test quotation creation."""
        with fresh_app.app_context():
            db.create_all()
            user = User(
                username='quoteuser',
                email='quote@test.com',
                full_name='Quote User'
            )
            user.set_password('pass123')
            db.session.add(user)
            db.session.commit()

            quotation = Quotation(
                quotation_number='QT-001',
                customer_name='Walk-in Customer',
                valid_until=datetime.utcnow() + timedelta(days=30),
                created_by=user.id
            )
            db.session.add(quotation)
            db.session.commit()

            assert quotation.id is not None
            assert quotation.status == 'draft'


# =============================================================================
# SMS AND WHATSAPP MODELS TESTS
# =============================================================================

class TestMessagingModels:
    """Tests for SMS and WhatsApp models."""

    def test_sms_template_creation(self, fresh_app):
        """Test SMS template creation."""
        with fresh_app.app_context():
            db.create_all()
            template = SMSTemplate(
                name='birthday_wish',
                template_type='birthday',
                message='Happy Birthday {customer_name}!'
            )
            db.session.add(template)
            db.session.commit()

            assert template.id is not None
            assert template.is_active is True

    def test_whatsapp_template_creation(self, fresh_app):
        """Test WhatsApp template creation."""
        with fresh_app.app_context():
            db.create_all()
            template = WhatsAppTemplate(
                name='order_confirmation',
                template_type='order_confirmation',
                message='Your order {order_number} has been confirmed!'
            )
            db.session.add(template)
            db.session.commit()

            assert template.id is not None


# =============================================================================
# SUPPLIER PAYMENT MODELS TESTS
# =============================================================================

class TestSupplierPaymentModels:
    """Tests for supplier payment models."""

    def test_supplier_payment_creation(self, fresh_app):
        """Test supplier payment creation."""
        with fresh_app.app_context():
            db.create_all()
            supplier = Supplier(name='Payment Supplier')
            user = User(
                username='suppayuser',
                email='suppay@test.com',
                full_name='Supplier Pay User'
            )
            user.set_password('pass123')
            db.session.add_all([supplier, user])
            db.session.commit()

            payment = SupplierPayment(
                payment_number='SP-001',
                supplier_id=supplier.id,
                amount=Decimal('50000.00'),
                payment_method='bank_transfer',
                payment_date=date.today(),
                created_by=user.id
            )
            db.session.add(payment)
            db.session.commit()

            assert payment.id is not None
            assert payment.status == 'completed'

    def test_supplier_ledger_creation(self, fresh_app):
        """Test supplier ledger entry creation."""
        with fresh_app.app_context():
            db.create_all()
            supplier = Supplier(name='Ledger Supplier')
            db.session.add(supplier)
            db.session.commit()

            ledger = SupplierLedger(
                supplier_id=supplier.id,
                transaction_type='purchase',
                debit=Decimal('50000.00'),
                balance=Decimal('50000.00'),
                description='Initial purchase'
            )
            db.session.add(ledger)
            db.session.commit()

            assert ledger.id is not None


# =============================================================================
# SCHEDULED TASK MODEL TESTS
# =============================================================================

class TestScheduledTaskModel:
    """Tests for the ScheduledTask model."""

    def test_scheduled_task_creation(self, fresh_app):
        """Test scheduled task creation."""
        with fresh_app.app_context():
            db.create_all()
            task = ScheduledTask(
                name='Daily Report',
                task_type='report_generation',
                schedule='0 9 * * *',  # 9 AM daily
                config={'report_type': 'daily'}
            )
            db.session.add(task)
            db.session.commit()

            assert task.id is not None
            assert task.is_active is True


# =============================================================================
# PRODUCT VARIANT TESTS
# =============================================================================

class TestProductVariantModel:
    """Tests for the ProductVariant model."""

    def test_variant_creation(self, fresh_app):
        """Test product variant creation."""
        with fresh_app.app_context():
            db.create_all()
            product = Product(
                code='VAR-PROD',
                name='Variant Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            variant = ProductVariant(
                product_id=product.id,
                sku='VAR-001-50ML',
                size='50ml',
                size_value=Decimal('50.00'),
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                quantity=50
            )
            db.session.add(variant)
            db.session.commit()

            assert variant.id is not None
            assert variant.product == product

    def test_variant_unique_sku(self, fresh_app):
        """Test unique constraint on variant SKU."""
        with fresh_app.app_context():
            db.create_all()
            product = Product(
                code='VAR-UNQ-PROD',
                name='Unique Variant Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            var1 = ProductVariant(
                product_id=product.id,
                sku='UNIQUE-SKU',
                size='50ml',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(var1)
            db.session.commit()

            var2 = ProductVariant(
                product_id=product.id,
                sku='UNIQUE-SKU',
                size='100ml',
                cost_price=Decimal('200.00'),
                selling_price=Decimal('400.00')
            )
            db.session.add(var2)
            with pytest.raises(IntegrityError):
                db.session.commit()


# =============================================================================
# GATE PASS MODEL TESTS
# =============================================================================

class TestGatePassModel:
    """Tests for the GatePass model."""

    def test_gate_pass_creation(self, fresh_app):
        """Test gate pass creation."""
        with fresh_app.app_context():
            db.create_all()
            source = Location(
                code='GP-SRC',
                name='Source',
                location_type='warehouse'
            )
            dest = Location(
                code='GP-DST',
                name='Dest',
                location_type='kiosk'
            )
            db.session.add_all([source, dest])
            db.session.commit()

            transfer = StockTransfer(
                transfer_number='GP-TRF-001',
                source_location_id=source.id,
                destination_location_id=dest.id
            )
            db.session.add(transfer)
            db.session.commit()

            gate_pass = GatePass(
                gate_pass_number='GP-001',
                transfer_id=transfer.id,
                vehicle_number='ABC-123',
                driver_name='Test Driver'
            )
            db.session.add(gate_pass)
            db.session.commit()

            assert gate_pass.id is not None
            assert gate_pass.status == 'issued'

    def test_gate_pass_unique_number(self, fresh_app):
        """Test unique constraint on gate pass number."""
        with fresh_app.app_context():
            db.create_all()
            source = Location(
                code='GP-UNQ-SRC',
                name='Source',
                location_type='warehouse'
            )
            dest = Location(
                code='GP-UNQ-DST',
                name='Dest',
                location_type='kiosk'
            )
            db.session.add_all([source, dest])
            db.session.commit()

            transfer = StockTransfer(
                transfer_number='GP-UNQ-TRF',
                source_location_id=source.id,
                destination_location_id=dest.id
            )
            db.session.add(transfer)
            db.session.commit()

            gp1 = GatePass(
                gate_pass_number='UNIQUE-GP',
                transfer_id=transfer.id
            )
            db.session.add(gp1)
            db.session.commit()

            gp2 = GatePass(
                gate_pass_number='UNIQUE-GP',
                transfer_id=transfer.id
            )
            db.session.add(gp2)
            with pytest.raises(IntegrityError):
                db.session.commit()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
