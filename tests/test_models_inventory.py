"""
Comprehensive Unit Tests for Location, Customer, and Inventory Models
Tests cover: Location, Customer, LocationStock, StockMovement, and SaleItem models
"""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from app import create_app
from app.models import (
    db, Location, Customer, LocationStock, StockMovement,
    SaleItem, Sale, Product, User, Category, StockTransfer,
    StockTransferItem
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope='function')
def app():
    """Create application for testing"""
    app = create_app('testing')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture(scope='function')
def session(app):
    """Create database session"""
    with app.app_context():
        yield db.session


@pytest.fixture
def sample_category(session):
    """Create a sample category"""
    category = Category(
        name='Test Category',
        description='Test category description'
    )
    session.add(category)
    session.commit()
    return category


@pytest.fixture
def sample_user(session):
    """Create a sample user"""
    user = User(
        username='testuser',
        email='test@example.com',
        full_name='Test User',
        role='admin'
    )
    user.set_password('password123')
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def warehouse_location(session):
    """Create a warehouse location"""
    warehouse = Location(
        code='WH-001',
        name='Main Warehouse',
        location_type='warehouse',
        address='123 Warehouse St',
        city='Wah Cantt',
        phone='0300-1234567',
        email='warehouse@test.com',
        is_active=True,
        can_sell=False
    )
    session.add(warehouse)
    session.commit()
    return warehouse


@pytest.fixture
def kiosk_location(session, warehouse_location):
    """Create a kiosk location"""
    kiosk = Location(
        code='K-001',
        name='Mall Kiosk',
        location_type='kiosk',
        address='Mall of Wah',
        city='Wah Cantt',
        phone='0300-7654321',
        email='kiosk@test.com',
        parent_warehouse_id=warehouse_location.id,
        is_active=True,
        can_sell=True
    )
    session.add(kiosk)
    session.commit()
    return kiosk


@pytest.fixture
def second_kiosk_location(session, warehouse_location):
    """Create a second kiosk location"""
    kiosk = Location(
        code='K-002',
        name='Second Kiosk',
        location_type='kiosk',
        address='City Center',
        city='Islamabad',
        is_active=True,
        can_sell=True,
        parent_warehouse_id=warehouse_location.id
    )
    session.add(kiosk)
    session.commit()
    return kiosk


@pytest.fixture
def sample_product(session, sample_category):
    """Create a sample product"""
    product = Product(
        code='PROD-001',
        barcode='1234567890123',
        name='Test Attar',
        category_id=sample_category.id,
        cost_price=Decimal('500.00'),
        selling_price=Decimal('750.00'),
        quantity=100,
        reorder_level=10,
        reorder_quantity=50,
        unit='piece',
        is_active=True
    )
    session.add(product)
    session.commit()
    return product


@pytest.fixture
def sample_customer(session):
    """Create a sample customer"""
    customer = Customer(
        name='Test Customer',
        phone='0300-1111111',
        email='customer@test.com',
        address='123 Customer St',
        city='Wah Cantt',
        postal_code='47040',
        customer_type='regular',
        loyalty_points=0,
        is_active=True
    )
    session.add(customer)
    session.commit()
    return customer


@pytest.fixture
def sample_sale(session, sample_user, sample_customer, kiosk_location):
    """Create a sample sale"""
    sale = Sale(
        sale_number='SALE-001',
        customer_id=sample_customer.id,
        user_id=sample_user.id,
        location_id=kiosk_location.id,
        subtotal=Decimal('750.00'),
        total=Decimal('750.00'),
        payment_method='cash',
        payment_status='paid',
        status='completed'
    )
    session.add(sale)
    session.commit()
    return sale


@pytest.fixture
def location_stock(session, kiosk_location, sample_product):
    """Create a location stock entry"""
    stock = LocationStock(
        location_id=kiosk_location.id,
        product_id=sample_product.id,
        quantity=50,
        reserved_quantity=0,
        reorder_level=10
    )
    session.add(stock)
    session.commit()
    return stock


# =============================================================================
# LOCATION MODEL TESTS
# =============================================================================

class TestLocationModel:
    """Tests for Location model"""

    def test_create_warehouse_location(self, session):
        """Test creating a warehouse location"""
        warehouse = Location(
            code='WH-TEST',
            name='Test Warehouse',
            location_type='warehouse',
            address='Test Address',
            city='Test City',
            is_active=True,
            can_sell=False
        )
        session.add(warehouse)
        session.commit()

        assert warehouse.id is not None
        assert warehouse.code == 'WH-TEST'
        assert warehouse.location_type == 'warehouse'
        assert warehouse.is_warehouse is True
        assert warehouse.is_kiosk is False
        assert warehouse.can_sell is False

    def test_create_kiosk_location(self, session, warehouse_location):
        """Test creating a kiosk location with parent warehouse"""
        kiosk = Location(
            code='K-TEST',
            name='Test Kiosk',
            location_type='kiosk',
            parent_warehouse_id=warehouse_location.id,
            is_active=True,
            can_sell=True
        )
        session.add(kiosk)
        session.commit()

        assert kiosk.id is not None
        assert kiosk.is_kiosk is True
        assert kiosk.is_warehouse is False
        assert kiosk.can_sell is True
        assert kiosk.parent_warehouse_id == warehouse_location.id
        assert kiosk.parent_warehouse.name == 'Main Warehouse'

    def test_location_type_validation(self, session):
        """Test location type values - warehouse and kiosk"""
        # Valid warehouse
        warehouse = Location(
            code='WH-VALID',
            name='Valid Warehouse',
            location_type='warehouse'
        )
        session.add(warehouse)
        session.commit()
        assert warehouse.location_type == 'warehouse'

        # Valid kiosk
        kiosk = Location(
            code='K-VALID',
            name='Valid Kiosk',
            location_type='kiosk'
        )
        session.add(kiosk)
        session.commit()
        assert kiosk.location_type == 'kiosk'

    def test_invalid_location_type_behavior(self, session):
        """Test that invalid location types behave correctly with properties"""
        # Note: SQLAlchemy doesn't enforce enum values by default in SQLite
        # This test verifies the is_warehouse and is_kiosk properties
        location = Location(
            code='INVALID-001',
            name='Invalid Type Location',
            location_type='invalid_type'  # Invalid type
        )
        session.add(location)
        session.commit()

        # Properties should return False for invalid type
        assert location.is_warehouse is False
        assert location.is_kiosk is False

    def test_location_unique_code_constraint(self, session, warehouse_location):
        """Test that location codes must be unique"""
        duplicate = Location(
            code='WH-001',  # Same code as warehouse_location
            name='Duplicate Location',
            location_type='warehouse'
        )
        session.add(duplicate)

        with pytest.raises(Exception):  # IntegrityError
            session.commit()
        session.rollback()

    def test_warehouse_kiosk_relationship(self, session, warehouse_location, kiosk_location):
        """Test parent-child relationship between warehouse and kiosks"""
        # Warehouse should have kiosk in child_kiosks
        assert kiosk_location in warehouse_location.child_kiosks

        # Kiosk should reference parent warehouse
        assert kiosk_location.parent_warehouse == warehouse_location

    def test_location_get_stock_for_product_existing(self, session, kiosk_location, sample_product, location_stock):
        """Test getting stock level for existing product at location"""
        stock_level = kiosk_location.get_stock_for_product(sample_product.id)
        assert stock_level == 50  # From location_stock fixture

    def test_location_get_stock_for_product_nonexistent(self, session, kiosk_location, sample_product):
        """Test getting stock level for product not at location"""
        # No stock entry exists, should return 0
        stock_level = kiosk_location.get_stock_for_product(sample_product.id)
        assert stock_level == 0

    def test_location_manager_assignment(self, session, warehouse_location, sample_user):
        """Test assigning a manager to a location"""
        warehouse_location.manager_id = sample_user.id
        session.commit()

        assert warehouse_location.manager == sample_user
        assert warehouse_location in sample_user.managed_locations

    def test_location_timestamps(self, session):
        """Test that timestamps are set correctly"""
        location = Location(
            code='TS-001',
            name='Timestamp Test',
            location_type='kiosk'
        )
        session.add(location)
        session.commit()

        assert location.created_at is not None
        assert location.updated_at is not None
        assert isinstance(location.created_at, datetime)

    def test_location_repr(self, warehouse_location):
        """Test string representation of location"""
        repr_str = repr(warehouse_location)
        assert 'WH-001' in repr_str
        assert 'Main Warehouse' in repr_str


# =============================================================================
# CUSTOMER MODEL TESTS
# =============================================================================

class TestCustomerModel:
    """Tests for Customer model"""

    def test_create_customer(self, session):
        """Test creating a customer"""
        customer = Customer(
            name='New Customer',
            phone='0300-9999999',
            email='new@test.com',
            customer_type='regular'
        )
        session.add(customer)
        session.commit()

        assert customer.id is not None
        assert customer.name == 'New Customer'
        assert customer.loyalty_points == 0

    def test_customer_phone_unique_constraint(self, session, sample_customer):
        """Test that phone numbers must be unique"""
        duplicate = Customer(
            name='Duplicate Phone Customer',
            phone='0300-1111111'  # Same as sample_customer
        )
        session.add(duplicate)

        with pytest.raises(Exception):  # IntegrityError
            session.commit()
        session.rollback()

    def test_phone_validation_format(self, session):
        """Test various phone number formats"""
        # Test with different formats
        formats = [
            '0300-1234567',
            '+92-300-1234567',
            '03001234567',
            '+923001234567'
        ]

        for i, phone in enumerate(formats):
            customer = Customer(
                name=f'Phone Test {i}',
                phone=phone
            )
            session.add(customer)
            session.commit()
            assert customer.phone == phone

    def test_email_validation_format(self, session):
        """Test email field accepts various formats"""
        # Note: SQLAlchemy doesn't validate email format by default
        customer = Customer(
            name='Email Test',
            phone='0300-5555555',
            email='valid.email@domain.com'
        )
        session.add(customer)
        session.commit()
        assert customer.email == 'valid.email@domain.com'

    def test_loyalty_tier_bronze(self, session):
        """Test Bronze tier (0-499 points)"""
        customer = Customer(
            name='Bronze Customer',
            phone='0300-1000001',
            loyalty_points=0
        )
        session.add(customer)
        session.commit()

        assert customer.loyalty_tier == 'Bronze'
        assert customer.loyalty_tier_color == 'info'
        assert customer.points_to_next_tier == 500
        assert customer.next_tier_name == 'Silver'

    def test_loyalty_tier_silver(self, session):
        """Test Silver tier (500-999 points)"""
        customer = Customer(
            name='Silver Customer',
            phone='0300-1000002',
            loyalty_points=500
        )
        session.add(customer)
        session.commit()

        assert customer.loyalty_tier == 'Silver'
        assert customer.loyalty_tier_color == 'secondary'
        assert customer.points_to_next_tier == 500
        assert customer.next_tier_name == 'Gold'

    def test_loyalty_tier_gold(self, session):
        """Test Gold tier (1000-2499 points)"""
        customer = Customer(
            name='Gold Customer',
            phone='0300-1000003',
            loyalty_points=1000
        )
        session.add(customer)
        session.commit()

        assert customer.loyalty_tier == 'Gold'
        assert customer.loyalty_tier_color == 'warning'
        assert customer.points_to_next_tier == 1500
        assert customer.next_tier_name == 'Platinum'

    def test_loyalty_tier_platinum(self, session):
        """Test Platinum tier (2500+ points)"""
        customer = Customer(
            name='Platinum Customer',
            phone='0300-1000004',
            loyalty_points=2500
        )
        session.add(customer)
        session.commit()

        assert customer.loyalty_tier == 'Platinum'
        assert customer.loyalty_tier_color == 'dark'
        assert customer.points_to_next_tier == 0
        assert customer.next_tier_name is None

    def test_loyalty_tier_transition_bronze_to_silver(self, session):
        """Test tier transition from Bronze to Silver"""
        customer = Customer(
            name='Transition Customer',
            phone='0300-1000005',
            loyalty_points=499
        )
        session.add(customer)
        session.commit()

        assert customer.loyalty_tier == 'Bronze'

        # Add points to transition to Silver
        customer.loyalty_points = 500
        session.commit()

        assert customer.loyalty_tier == 'Silver'

    def test_loyalty_tier_boundary_values(self, session):
        """Test loyalty tier at exact boundary values"""
        test_cases = [
            (499, 'Bronze'),
            (500, 'Silver'),
            (999, 'Silver'),
            (1000, 'Gold'),
            (2499, 'Gold'),
            (2500, 'Platinum'),
            (10000, 'Platinum')
        ]

        for i, (points, expected_tier) in enumerate(test_cases):
            customer = Customer(
                name=f'Boundary Customer {i}',
                phone=f'0300-200000{i}',
                loyalty_points=points
            )
            session.add(customer)
            session.commit()

            assert customer.loyalty_tier == expected_tier, \
                f"Expected {expected_tier} for {points} points, got {customer.loyalty_tier}"

    def test_add_loyalty_points(self, session):
        """Test adding loyalty points based on purchase amount"""
        customer = Customer(
            name='Points Customer',
            phone='0300-3000001',
            loyalty_points=0
        )
        session.add(customer)
        session.commit()

        # 1 point per Rs. 100 spent
        points_earned = customer.add_loyalty_points(1000)  # Rs. 1000 purchase
        session.commit()

        assert points_earned == 10
        assert customer.loyalty_points == 10

    def test_add_loyalty_points_partial(self, session):
        """Test adding loyalty points with non-round amounts"""
        customer = Customer(
            name='Partial Points Customer',
            phone='0300-3000002',
            loyalty_points=0
        )
        session.add(customer)
        session.commit()

        # Rs. 550 should earn 5 points (not 5.5)
        points_earned = customer.add_loyalty_points(550)
        session.commit()

        assert points_earned == 5
        assert customer.loyalty_points == 5

    def test_redeem_points_success(self, session):
        """Test successful points redemption"""
        customer = Customer(
            name='Redeem Customer',
            phone='0300-3000003',
            loyalty_points=500
        )
        session.add(customer)
        session.commit()

        success, discount = customer.redeem_points(200)
        session.commit()

        assert success is True
        assert discount == 200  # 1:1 ratio with PKR
        assert customer.loyalty_points == 300

    def test_redeem_points_insufficient(self, session):
        """Test redemption with insufficient points"""
        customer = Customer(
            name='Insufficient Points Customer',
            phone='0300-3000004',
            loyalty_points=100
        )
        session.add(customer)
        session.commit()

        success, message = customer.redeem_points(200)

        assert success is False
        assert 'Insufficient' in message
        assert customer.loyalty_points == 100  # Unchanged

    def test_redeem_points_minimum(self, session):
        """Test minimum redemption requirement (100 points)"""
        customer = Customer(
            name='Min Redeem Customer',
            phone='0300-3000005',
            loyalty_points=500
        )
        session.add(customer)
        session.commit()

        # Try to redeem less than minimum
        success, message = customer.redeem_points(50)

        assert success is False
        assert '100 points' in message
        assert customer.loyalty_points == 500  # Unchanged

    def test_points_value_pkr(self, session):
        """Test PKR value calculation of loyalty points"""
        customer = Customer(
            name='Value Customer',
            phone='0300-3000006',
            loyalty_points=500
        )
        session.add(customer)
        session.commit()

        # 100 points = Rs. 100
        assert customer.points_value_pkr == 500

    def test_customer_types(self, session):
        """Test different customer types"""
        types = ['regular', 'vip', 'wholesale']

        for i, ctype in enumerate(types):
            customer = Customer(
                name=f'{ctype.title()} Customer',
                phone=f'0300-400000{i}',
                customer_type=ctype
            )
            session.add(customer)
            session.commit()

            assert customer.customer_type == ctype

    def test_customer_account_balance(self, session):
        """Test customer account balance (for credit customers)"""
        customer = Customer(
            name='Credit Customer',
            phone='0300-5000001',
            account_balance=Decimal('5000.00')
        )
        session.add(customer)
        session.commit()

        assert customer.account_balance == Decimal('5000.00')

    def test_negative_loyalty_points_protection(self, session):
        """Test that loyalty points don't go negative through redemption"""
        customer = Customer(
            name='Negative Test Customer',
            phone='0300-6000001',
            loyalty_points=100
        )
        session.add(customer)
        session.commit()

        # Try to redeem more than available
        success, message = customer.redeem_points(150)

        assert success is False
        assert customer.loyalty_points == 100  # Should not go negative


# =============================================================================
# LOCATION STOCK MODEL TESTS
# =============================================================================

class TestLocationStockModel:
    """Tests for LocationStock model"""

    def test_create_location_stock(self, session, kiosk_location, sample_product):
        """Test creating a location stock entry"""
        stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=100,
            reserved_quantity=10,
            reorder_level=15
        )
        session.add(stock)
        session.commit()

        assert stock.id is not None
        assert stock.quantity == 100
        assert stock.reserved_quantity == 10

    def test_available_quantity_calculation(self, session, kiosk_location, sample_product):
        """Test available quantity (total - reserved)"""
        stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=100,
            reserved_quantity=25
        )
        session.add(stock)
        session.commit()

        assert stock.available_quantity == 75

    def test_available_quantity_all_reserved(self, session, kiosk_location, sample_product):
        """Test available quantity when all stock is reserved"""
        stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=50,
            reserved_quantity=50
        )
        session.add(stock)
        session.commit()

        assert stock.available_quantity == 0

    def test_available_quantity_over_reserved(self, session, kiosk_location, sample_product):
        """Test available quantity when reserved exceeds quantity (edge case)"""
        stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=50,
            reserved_quantity=60  # Over-reserved
        )
        session.add(stock)
        session.commit()

        # Should return 0, not negative
        assert stock.available_quantity == 0

    def test_is_low_stock_true(self, session, kiosk_location, sample_product):
        """Test low stock detection when below reorder level"""
        stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=15,
            reserved_quantity=10,  # Available = 5
            reorder_level=10
        )
        session.add(stock)
        session.commit()

        assert stock.is_low_stock is True

    def test_is_low_stock_false(self, session, kiosk_location, sample_product):
        """Test low stock detection when above reorder level"""
        stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=100,
            reserved_quantity=0,
            reorder_level=10
        )
        session.add(stock)
        session.commit()

        assert stock.is_low_stock is False

    def test_is_low_stock_boundary(self, session, kiosk_location, sample_product):
        """Test low stock at exactly reorder level"""
        stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=10,
            reserved_quantity=0,
            reorder_level=10
        )
        session.add(stock)
        session.commit()

        # At exactly reorder level should be considered low stock
        assert stock.is_low_stock is True

    def test_stock_value_calculation(self, session, kiosk_location, sample_product):
        """Test stock value calculation at cost price"""
        stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=20
        )
        session.add(stock)
        session.commit()

        # Product cost price is 500.00
        expected_value = 20 * 500.00
        assert stock.stock_value == expected_value

    def test_unique_location_product_constraint(self, session, kiosk_location, sample_product):
        """Test that location-product combination must be unique"""
        stock1 = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=50
        )
        session.add(stock1)
        session.commit()

        # Try to create duplicate
        stock2 = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=30
        )
        session.add(stock2)

        with pytest.raises(Exception):  # IntegrityError
            session.commit()
        session.rollback()

    def test_stock_negative_quantity_behavior(self, session, kiosk_location, sample_product):
        """Test behavior with negative stock quantity (edge case)"""
        # Note: This tests what happens, not what should be allowed
        stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=-10,  # Negative stock
            reserved_quantity=0
        )
        session.add(stock)
        session.commit()

        # Available quantity should handle this gracefully
        assert stock.available_quantity == 0  # max(0, -10 - 0)

    def test_location_stock_timestamps(self, session, kiosk_location, sample_product):
        """Test timestamp fields"""
        stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=50
        )
        session.add(stock)
        session.commit()

        assert stock.created_at is not None
        assert stock.updated_at is not None

    def test_last_movement_tracking(self, session, kiosk_location, sample_product):
        """Test last movement timestamp tracking"""
        movement_time = datetime.utcnow()

        stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=50,
            last_movement_at=movement_time
        )
        session.add(stock)
        session.commit()

        assert stock.last_movement_at is not None

    def test_decimal_quantity_precision(self, session, kiosk_location, sample_product):
        """Test that integer quantities are handled correctly"""
        # LocationStock uses Integer for quantity
        stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=100
        )
        session.add(stock)
        session.commit()

        assert stock.quantity == 100
        assert isinstance(stock.quantity, int)


# =============================================================================
# STOCK MOVEMENT MODEL TESTS
# =============================================================================

class TestStockMovementModel:
    """Tests for StockMovement model"""

    def test_create_purchase_movement(self, session, sample_product, warehouse_location, sample_user):
        """Test creating a purchase stock movement"""
        movement = StockMovement(
            product_id=sample_product.id,
            user_id=sample_user.id,
            location_id=warehouse_location.id,
            movement_type='purchase',
            quantity=50,
            reference='PO-001',
            notes='Initial stock purchase'
        )
        session.add(movement)
        session.commit()

        assert movement.id is not None
        assert movement.movement_type == 'purchase'
        assert movement.quantity == 50  # Positive for incoming

    def test_create_sale_movement(self, session, sample_product, kiosk_location, sample_user):
        """Test creating a sale stock movement"""
        movement = StockMovement(
            product_id=sample_product.id,
            user_id=sample_user.id,
            location_id=kiosk_location.id,
            movement_type='sale',
            quantity=-5,  # Negative for outgoing
            reference='SALE-001'
        )
        session.add(movement)
        session.commit()

        assert movement.movement_type == 'sale'
        assert movement.quantity == -5

    def test_create_adjustment_movement(self, session, sample_product, warehouse_location, sample_user):
        """Test creating an adjustment stock movement"""
        movement = StockMovement(
            product_id=sample_product.id,
            user_id=sample_user.id,
            location_id=warehouse_location.id,
            movement_type='adjustment',
            quantity=-3,  # Negative adjustment (damage/loss)
            notes='Physical count adjustment'
        )
        session.add(movement)
        session.commit()

        assert movement.movement_type == 'adjustment'

    def test_create_transfer_out_movement(self, session, sample_product, warehouse_location, sample_user):
        """Test creating a transfer out movement"""
        movement = StockMovement(
            product_id=sample_product.id,
            user_id=sample_user.id,
            location_id=warehouse_location.id,
            movement_type='transfer_out',
            quantity=-20,
            reference='TF-001'
        )
        session.add(movement)
        session.commit()

        assert movement.movement_type == 'transfer_out'
        assert movement.quantity < 0

    def test_create_transfer_in_movement(self, session, sample_product, kiosk_location, sample_user):
        """Test creating a transfer in movement"""
        movement = StockMovement(
            product_id=sample_product.id,
            user_id=sample_user.id,
            location_id=kiosk_location.id,
            movement_type='transfer_in',
            quantity=20,
            reference='TF-001'
        )
        session.add(movement)
        session.commit()

        assert movement.movement_type == 'transfer_in'
        assert movement.quantity > 0

    def test_movement_types(self, session, sample_product, warehouse_location, sample_user):
        """Test all valid movement types"""
        movement_types = [
            'purchase', 'sale', 'adjustment', 'return',
            'damage', 'transfer_in', 'transfer_out'
        ]

        for i, mtype in enumerate(movement_types):
            movement = StockMovement(
                product_id=sample_product.id,
                user_id=sample_user.id,
                location_id=warehouse_location.id,
                movement_type=mtype,
                quantity=1 if mtype in ['purchase', 'return', 'transfer_in'] else -1,
                reference=f'REF-{i}'
            )
            session.add(movement)
            session.commit()

            assert movement.movement_type == mtype

    def test_movement_audit_trail(self, session, sample_product, warehouse_location, sample_user):
        """Test that movements create an audit trail"""
        # Create multiple movements
        movements = []
        for i in range(3):
            movement = StockMovement(
                product_id=sample_product.id,
                user_id=sample_user.id,
                location_id=warehouse_location.id,
                movement_type='adjustment',
                quantity=i + 1,
                reference=f'ADJ-{i}'
            )
            session.add(movement)
            movements.append(movement)
        session.commit()

        # Verify all movements exist
        product_movements = StockMovement.query.filter_by(
            product_id=sample_product.id
        ).all()

        assert len(product_movements) == 3
        # Check timestamps are recorded
        for m in product_movements:
            assert m.timestamp is not None
            assert m.user_id == sample_user.id

    def test_movement_timestamp_auto_set(self, session, sample_product, warehouse_location, sample_user):
        """Test that timestamp is automatically set"""
        movement = StockMovement(
            product_id=sample_product.id,
            user_id=sample_user.id,
            location_id=warehouse_location.id,
            movement_type='purchase',
            quantity=10
        )
        session.add(movement)
        session.commit()

        assert movement.timestamp is not None
        assert isinstance(movement.timestamp, datetime)

    def test_movement_location_relationship(self, session, sample_product, kiosk_location, sample_user):
        """Test movement-location relationship"""
        movement = StockMovement(
            product_id=sample_product.id,
            user_id=sample_user.id,
            location_id=kiosk_location.id,
            movement_type='sale',
            quantity=-1
        )
        session.add(movement)
        session.commit()

        assert movement.location == kiosk_location
        assert movement in kiosk_location.stock_movements.all()

    def test_movement_product_relationship(self, session, sample_product, warehouse_location, sample_user):
        """Test movement-product relationship"""
        movement = StockMovement(
            product_id=sample_product.id,
            user_id=sample_user.id,
            location_id=warehouse_location.id,
            movement_type='purchase',
            quantity=10
        )
        session.add(movement)
        session.commit()

        assert movement.product == sample_product
        assert movement in sample_product.stock_movements.all()


# =============================================================================
# STOCK TRANSFER MODEL TESTS
# =============================================================================

class TestStockTransferModel:
    """Tests for StockTransfer model"""

    def test_create_stock_transfer(self, session, warehouse_location, kiosk_location, sample_user):
        """Test creating a stock transfer"""
        transfer = StockTransfer(
            transfer_number='TF-001',
            source_location_id=warehouse_location.id,
            destination_location_id=kiosk_location.id,
            status='draft',
            requested_by=sample_user.id
        )
        session.add(transfer)
        session.commit()

        assert transfer.id is not None
        assert transfer.transfer_number == 'TF-001'
        assert transfer.status == 'draft'

    def test_transfer_between_same_location_allowed(self, session, warehouse_location, sample_user):
        """Test transfer between same location (edge case - may be invalid business logic)"""
        # Note: The model doesn't prevent this, but business logic should
        transfer = StockTransfer(
            transfer_number='TF-SAME',
            source_location_id=warehouse_location.id,
            destination_location_id=warehouse_location.id,  # Same location
            status='draft'
        )
        session.add(transfer)
        session.commit()

        # Model allows it - validation should be at business logic level
        assert transfer.source_location_id == transfer.destination_location_id

    def test_transfer_status_workflow(self, session, warehouse_location, kiosk_location, sample_user):
        """Test transfer status workflow properties"""
        transfer = StockTransfer(
            transfer_number='TF-WORKFLOW',
            source_location_id=warehouse_location.id,
            destination_location_id=kiosk_location.id,
            status='requested'
        )
        session.add(transfer)
        session.commit()

        # Test can_approve
        assert transfer.can_approve is True

        transfer.status = 'approved'
        session.commit()
        assert transfer.can_approve is False
        assert transfer.can_dispatch is True

        transfer.status = 'dispatched'
        session.commit()
        assert transfer.can_dispatch is False
        assert transfer.can_receive is True

    def test_transfer_can_cancel(self, session, warehouse_location, kiosk_location):
        """Test which statuses allow cancellation"""
        cancellable_statuses = ['draft', 'requested', 'approved']
        non_cancellable_statuses = ['dispatched', 'received', 'rejected', 'cancelled']

        for status in cancellable_statuses:
            transfer = StockTransfer(
                transfer_number=f'TF-CAN-{status}',
                source_location_id=warehouse_location.id,
                destination_location_id=kiosk_location.id,
                status=status
            )
            session.add(transfer)
            session.commit()
            assert transfer.can_cancel is True

        for status in non_cancellable_statuses:
            transfer = StockTransfer(
                transfer_number=f'TF-NOCAN-{status}',
                source_location_id=warehouse_location.id,
                destination_location_id=kiosk_location.id,
                status=status
            )
            session.add(transfer)
            session.commit()
            assert transfer.can_cancel is False

    def test_transfer_status_badge_class(self, session, warehouse_location, kiosk_location):
        """Test status badge CSS class mapping"""
        status_badge_mapping = {
            'draft': 'secondary',
            'requested': 'info',
            'approved': 'primary',
            'dispatched': 'warning',
            'received': 'success',
            'rejected': 'danger',
            'cancelled': 'dark'
        }

        for status, expected_class in status_badge_mapping.items():
            transfer = StockTransfer(
                transfer_number=f'TF-BADGE-{status}',
                source_location_id=warehouse_location.id,
                destination_location_id=kiosk_location.id,
                status=status
            )
            session.add(transfer)
            session.commit()
            assert transfer.status_badge_class == expected_class

    def test_transfer_total_quantities(self, session, warehouse_location, kiosk_location, sample_product):
        """Test total quantity calculations"""
        transfer = StockTransfer(
            transfer_number='TF-QTY',
            source_location_id=warehouse_location.id,
            destination_location_id=kiosk_location.id,
            status='draft'
        )
        session.add(transfer)
        session.commit()

        # Add items
        item1 = StockTransferItem(
            transfer_id=transfer.id,
            product_id=sample_product.id,
            quantity_requested=10,
            quantity_approved=8,
            quantity_received=8
        )
        session.add(item1)
        session.commit()

        assert transfer.total_quantity_requested == 10
        assert transfer.total_quantity_approved == 8
        assert transfer.total_quantity_received == 8


# =============================================================================
# SALE ITEM MODEL TESTS
# =============================================================================

class TestSaleItemModel:
    """Tests for SaleItem model"""

    def test_create_sale_item(self, session, sample_sale, sample_product):
        """Test creating a sale item"""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=2,
            unit_price=Decimal('750.00'),
            discount=Decimal('0.00'),
            subtotal=Decimal('1500.00')
        )
        session.add(item)
        session.commit()

        assert item.id is not None
        assert item.quantity == 2
        assert item.subtotal == Decimal('1500.00')

    def test_calculate_subtotal_no_discount(self, session, sample_sale, sample_product):
        """Test subtotal calculation without discount"""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=3,
            unit_price=Decimal('100.00'),
            discount=Decimal('0.00')
        )
        session.add(item)

        calculated = item.calculate_subtotal()
        session.commit()

        assert calculated == Decimal('300.00')
        assert item.subtotal == Decimal('300.00')

    def test_calculate_subtotal_with_discount(self, session, sample_sale, sample_product):
        """Test subtotal calculation with discount"""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=5,
            unit_price=Decimal('100.00'),
            discount=Decimal('50.00')
        )
        session.add(item)

        calculated = item.calculate_subtotal()
        session.commit()

        # (5 * 100) - 50 = 450
        assert calculated == Decimal('450.00')

    def test_calculate_subtotal_discount_greater_than_total(self, session, sample_sale, sample_product):
        """Test subtotal when discount exceeds quantity * price"""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=Decimal('100.00'),
            discount=Decimal('150.00')  # Discount > subtotal
        )
        session.add(item)

        calculated = item.calculate_subtotal()
        session.commit()

        # (1 * 100) - 150 = -50
        assert calculated == Decimal('-50.00')

    def test_decimal_precision_unit_price(self, session, sample_sale, sample_product):
        """Test decimal precision for unit price"""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=Decimal('99.99'),
            discount=Decimal('0.00')
        )
        session.add(item)
        item.calculate_subtotal()
        session.commit()

        assert item.unit_price == Decimal('99.99')
        assert item.subtotal == Decimal('99.99')

    def test_decimal_precision_multiple_quantities(self, session, sample_sale, sample_product):
        """Test decimal precision with multiple quantities"""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=7,
            unit_price=Decimal('33.33'),
            discount=Decimal('0.00')
        )
        session.add(item)
        item.calculate_subtotal()
        session.commit()

        # 7 * 33.33 = 233.31
        assert item.subtotal == Decimal('233.31')

    def test_sale_item_quantity_zero(self, session, sample_sale, sample_product):
        """Test sale item with zero quantity"""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=0,
            unit_price=Decimal('100.00'),
            discount=Decimal('0.00')
        )
        session.add(item)
        item.calculate_subtotal()
        session.commit()

        assert item.subtotal == Decimal('0.00')

    def test_sale_item_negative_quantity(self, session, sample_sale, sample_product):
        """Test sale item with negative quantity (returns scenario)"""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=-1,  # Return
            unit_price=Decimal('100.00'),
            discount=Decimal('0.00')
        )
        session.add(item)
        item.calculate_subtotal()
        session.commit()

        assert item.subtotal == Decimal('-100.00')

    def test_sale_item_product_relationship(self, session, sample_sale, sample_product):
        """Test sale item-product relationship"""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=sample_product.selling_price,
            subtotal=sample_product.selling_price
        )
        session.add(item)
        session.commit()

        assert item.product == sample_product
        assert item in sample_product.sale_items.all()

    def test_sale_item_sale_relationship(self, session, sample_sale, sample_product):
        """Test sale item-sale relationship"""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=Decimal('750.00'),
            subtotal=Decimal('750.00')
        )
        session.add(item)
        session.commit()

        assert item.sale == sample_sale
        assert item in sample_sale.items.all()

    def test_sale_calculate_totals(self, session, sample_sale, sample_product, sample_category):
        """Test sale total calculation from multiple items"""
        # Create another product
        product2 = Product(
            code='PROD-002',
            name='Second Product',
            category_id=sample_category.id,
            cost_price=Decimal('200.00'),
            selling_price=Decimal('300.00')
        )
        session.add(product2)
        session.commit()

        # Add items to sale
        item1 = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=2,
            unit_price=Decimal('750.00'),
            discount=Decimal('0.00'),
            subtotal=Decimal('1500.00')
        )
        item2 = SaleItem(
            sale_id=sample_sale.id,
            product_id=product2.id,
            quantity=1,
            unit_price=Decimal('300.00'),
            discount=Decimal('50.00'),
            subtotal=Decimal('250.00')
        )
        session.add_all([item1, item2])
        session.commit()

        # Calculate totals
        sample_sale.discount = Decimal('0.00')
        sample_sale.discount_type = 'amount'
        total = sample_sale.calculate_totals()
        session.commit()

        # 1500 + 250 = 1750
        assert sample_sale.subtotal == Decimal('1750.00')
        assert sample_sale.total == Decimal('1750.00')


# =============================================================================
# EDGE CASE AND INTEGRATION TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions"""

    def test_stock_going_negative_through_movement(self, session, sample_product, kiosk_location, sample_user):
        """Test stock movement that would result in negative stock"""
        # Create initial stock
        stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=10
        )
        session.add(stock)
        session.commit()

        # Create movement that exceeds available stock
        movement = StockMovement(
            product_id=sample_product.id,
            user_id=sample_user.id,
            location_id=kiosk_location.id,
            movement_type='sale',
            quantity=-15  # More than available
        )
        session.add(movement)
        session.commit()

        # Movement is recorded (audit trail)
        assert movement.quantity == -15

        # Note: Stock update should be handled by business logic, not model

    def test_large_quantity_values(self, session, kiosk_location, sample_product):
        """Test handling of large quantity values"""
        stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=999999999,  # Large quantity
            reserved_quantity=0
        )
        session.add(stock)
        session.commit()

        assert stock.quantity == 999999999
        assert stock.available_quantity == 999999999

    def test_large_monetary_values(self, session, sample_sale, sample_product):
        """Test handling of large monetary values"""
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=Decimal('99999999.99'),  # Large value
            discount=Decimal('0.00'),
            subtotal=Decimal('99999999.99')
        )
        session.add(item)
        session.commit()

        assert item.subtotal == Decimal('99999999.99')

    def test_customer_with_maximum_loyalty_points(self, session):
        """Test customer with very large loyalty points"""
        customer = Customer(
            name='High Points Customer',
            phone='0300-9999999',
            loyalty_points=2147483647  # Max integer
        )
        session.add(customer)
        session.commit()

        assert customer.loyalty_tier == 'Platinum'
        assert customer.points_to_next_tier == 0

    def test_concurrent_stock_entries(self, session, warehouse_location, kiosk_location, sample_product):
        """Test multiple stock entries at different locations for same product"""
        stock1 = LocationStock(
            location_id=warehouse_location.id,
            product_id=sample_product.id,
            quantity=1000
        )
        stock2 = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=50
        )
        session.add_all([stock1, stock2])
        session.commit()

        # Both should exist
        assert stock1.id is not None
        assert stock2.id is not None
        assert stock1.location_id != stock2.location_id

    def test_empty_string_fields(self, session):
        """Test handling of empty string fields"""
        customer = Customer(
            name='Empty Fields Customer',
            phone='0300-8888888',
            email='',  # Empty email
            address=''  # Empty address
        )
        session.add(customer)
        session.commit()

        assert customer.email == ''
        assert customer.address == ''

    def test_null_optional_fields(self, session, warehouse_location, sample_product):
        """Test null values for optional fields"""
        stock = LocationStock(
            location_id=warehouse_location.id,
            product_id=sample_product.id,
            quantity=100,
            last_movement_at=None,  # Explicitly null
            last_count_at=None
        )
        session.add(stock)
        session.commit()

        assert stock.last_movement_at is None
        assert stock.last_count_at is None


class TestIntegration:
    """Integration tests combining multiple models"""

    def test_full_transfer_workflow(self, session, warehouse_location, kiosk_location, sample_product, sample_user):
        """Test complete stock transfer workflow"""
        # Create initial stock at warehouse
        warehouse_stock = LocationStock(
            location_id=warehouse_location.id,
            product_id=sample_product.id,
            quantity=100
        )
        session.add(warehouse_stock)
        session.commit()

        # Create transfer request
        transfer = StockTransfer(
            transfer_number='TF-FULL-001',
            source_location_id=warehouse_location.id,
            destination_location_id=kiosk_location.id,
            status='draft',
            requested_by=sample_user.id
        )
        session.add(transfer)
        session.commit()

        # Add transfer item
        transfer_item = StockTransferItem(
            transfer_id=transfer.id,
            product_id=sample_product.id,
            quantity_requested=20
        )
        session.add(transfer_item)
        session.commit()

        # Verify relationships
        assert transfer.source_location == warehouse_location
        assert transfer.destination_location == kiosk_location
        assert transfer_item in transfer.items.all()
        assert transfer.total_items == 1
        assert transfer.total_quantity_requested == 20

    def test_customer_sale_loyalty_flow(self, session, sample_customer, sample_sale, sample_product):
        """Test customer purchase and loyalty points flow"""
        initial_points = sample_customer.loyalty_points

        # Add item to sale
        item = SaleItem(
            sale_id=sample_sale.id,
            product_id=sample_product.id,
            quantity=2,
            unit_price=Decimal('750.00'),
            discount=Decimal('0.00'),
            subtotal=Decimal('1500.00')
        )
        session.add(item)
        session.commit()

        # Update sale totals
        sample_sale.calculate_totals()
        session.commit()

        # Add loyalty points based on sale total
        points_earned = sample_customer.add_loyalty_points(float(sample_sale.total))
        session.commit()

        # Verify
        assert points_earned > 0
        assert sample_customer.loyalty_points > initial_points

    def test_location_stock_movement_integration(self, session, kiosk_location, sample_product, sample_user):
        """Test stock movement updates with location stock"""
        # Create location stock
        stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=100
        )
        session.add(stock)
        session.commit()

        # Record sale movement
        movement = StockMovement(
            product_id=sample_product.id,
            user_id=sample_user.id,
            location_id=kiosk_location.id,
            movement_type='sale',
            quantity=-5,
            reference='SALE-INT-001'
        )
        session.add(movement)

        # Simulate stock update (normally done by business logic)
        stock.quantity -= 5
        stock.last_movement_at = datetime.utcnow()
        session.commit()

        # Verify
        assert stock.quantity == 95
        assert movement.location == kiosk_location
        assert stock.last_movement_at is not None


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
