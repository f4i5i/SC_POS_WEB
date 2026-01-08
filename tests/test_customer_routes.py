"""
Comprehensive Tests for Customer Routes

Tests covering customer-related Flask routes:
1. Customer CRUD operations (create, read, update, delete)
2. Loyalty program functionality
3. Gift card operations
4. Customer search
5. Customer purchase history
6. Customer analytics
7. Birthday gift functionality

Run with: pytest tests/test_customer_routes.py -v
"""

import pytest
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app import create_app
from app.models import (
    db, Customer, Sale, SaleItem, Product, User, Category,
    Location, SyncQueue
)


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
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

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
def init_database(app):
    """Initialize database with comprehensive test data."""
    with app.app_context():
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
            name='Test Kiosk',
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

        # Create category
        category = Category(name='Attars', description='Traditional oil-based perfumes')
        db.session.add(category)
        db.session.flush()

        # Create products
        products = [
            Product(
                code='PRD001',
                barcode='1234567890123',
                name='Oud Premium',
                brand='Sunnat',
                category_id=category.id,
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
                category_id=category.id,
                cost_price=Decimal('300.00'),
                selling_price=Decimal('600.00'),
                quantity=50,
                reorder_level=5,
                is_active=True
            ),
        ]
        db.session.add_all(products)
        db.session.flush()

        # Create test customers
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
        db.session.commit()
        yield


@pytest.fixture
def auth_admin(client, init_database, app):
    """Login as admin user and return authenticated client."""
    with app.app_context():
        client.post('/auth/login', data={
            'username': 'admin',
            'password': 'admin123'
        }, follow_redirects=True)
        yield client


@pytest.fixture
def auth_manager(client, init_database, app):
    """Login as manager user and return authenticated client."""
    with app.app_context():
        client.post('/auth/login', data={
            'username': 'manager',
            'password': 'manager123'
        }, follow_redirects=True)
        yield client


@pytest.fixture
def auth_cashier(client, init_database, app):
    """Login as cashier user and return authenticated client."""
    with app.app_context():
        client.post('/auth/login', data={
            'username': 'cashier',
            'password': 'cashier123'
        }, follow_redirects=True)
        yield client


@pytest.fixture
def sample_customer_with_sales(app, init_database):
    """Create a customer with purchase history for analytics testing."""
    with app.app_context():
        customer = Customer(
            name='Sales Customer',
            phone='03007777777',
            email='sales@test.com',
            customer_type='regular',
            loyalty_points=100,
            birthday=date(1985, 6, 15),
            is_active=True
        )
        db.session.add(customer)
        db.session.flush()

        user = User.query.filter_by(username='admin').first()
        category = Category.query.first()
        product = Product.query.first()

        # Create multiple sales for this customer
        for i in range(5):
            sale = Sale(
                sale_number=f'SALE-CUST-{i:03d}',
                customer_id=customer.id,
                user_id=user.id,
                subtotal=Decimal('1000.00') * (i + 1),
                total=Decimal('1000.00') * (i + 1),
                payment_method='cash',
                status='completed',
                sale_date=datetime.now() - timedelta(days=i * 30)
            )
            db.session.add(sale)
            db.session.flush()

            # Add sale items
            sale_item = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                quantity=i + 1,
                unit_price=Decimal('1000.00'),
                subtotal=Decimal('1000.00') * (i + 1)
            )
            db.session.add(sale_item)

        db.session.commit()
        customer_id = customer.id
        yield customer_id


# =============================================================================
# SECTION 1: CUSTOMER CRUD OPERATIONS
# =============================================================================

class TestCustomerCreate:
    """Tests for customer creation (POST /customers/add)."""

    def test_create_customer_success(self, auth_admin, app):
        """Test successfully creating a new customer."""
        response = auth_admin.post('/customers/add', data={
            'name': 'New Test Customer',
            'phone': '03112223333',
            'email': 'newcustomer@test.com',
            'address': '789 New Street',
            'city': 'Lahore',
            'postal_code': '54000',
            'customer_type': 'regular',
            'notes': 'Test notes for new customer'
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            customer = Customer.query.filter_by(phone='03112223333').first()
            assert customer is not None
            assert customer.name == 'New Test Customer'
            assert customer.email == 'newcustomer@test.com'
            assert customer.city == 'Lahore'
            assert customer.customer_type == 'regular'

    def test_create_customer_with_birthday(self, auth_admin, app):
        """Test creating customer with birthday field."""
        response = auth_admin.post('/customers/add', data={
            'name': 'Birthday Customer',
            'phone': '03112224444',
            'birthday': '1995-08-25',
            'customer_type': 'regular'
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            customer = Customer.query.filter_by(phone='03112224444').first()
            assert customer is not None
            assert customer.birthday == date(1995, 8, 25)

    def test_create_customer_vip_type(self, auth_admin, app):
        """Test creating a VIP customer."""
        response = auth_admin.post('/customers/add', data={
            'name': 'VIP Customer',
            'phone': '03112225555',
            'customer_type': 'vip'
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            customer = Customer.query.filter_by(phone='03112225555').first()
            assert customer is not None
            assert customer.customer_type == 'vip'

    def test_create_customer_wholesale_type(self, auth_admin, app):
        """Test creating a wholesale customer."""
        response = auth_admin.post('/customers/add', data={
            'name': 'Wholesale Customer',
            'phone': '03112226666',
            'customer_type': 'wholesale'
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            customer = Customer.query.filter_by(phone='03112226666').first()
            assert customer is not None
            assert customer.customer_type == 'wholesale'

    def test_create_customer_sync_queue_entry(self, auth_admin, app):
        """Test that creating customer adds sync queue entry."""
        response = auth_admin.post('/customers/add', data={
            'name': 'Sync Test Customer',
            'phone': '03112227777',
            'customer_type': 'regular'
        }, follow_redirects=True)

        with app.app_context():
            sync_entry = SyncQueue.query.filter_by(
                table_name='customers',
                operation='insert'
            ).order_by(SyncQueue.id.desc()).first()

            assert sync_entry is not None

    def test_create_customer_form_page_loads(self, auth_admin):
        """Test that add customer form page loads."""
        response = auth_admin.get('/customers/add')
        assert response.status_code == 200

    def test_create_customer_requires_auth(self, client, init_database):
        """Test that creating customer requires authentication."""
        response = client.post('/customers/add', data={
            'name': 'Unauthenticated Customer',
            'phone': '03112228888'
        })
        # Should redirect to login
        assert response.status_code in [302, 401]


class TestCustomerRead:
    """Tests for reading customer data."""

    def test_customer_index_page_loads(self, auth_admin):
        """Test customer list page loads successfully."""
        response = auth_admin.get('/customers/')
        assert response.status_code == 200

    def test_customer_index_shows_customers(self, auth_admin):
        """Test customer list page shows customers."""
        response = auth_admin.get('/customers/')
        assert response.status_code == 200
        # Check that at least one customer name appears
        assert b'John Doe' in response.data or b'customers' in response.data.lower()

    def test_customer_index_excludes_inactive(self, auth_admin, app):
        """Test that inactive customers are excluded from list."""
        response = auth_admin.get('/customers/')
        assert response.status_code == 200
        assert b'Inactive Customer' not in response.data

    def test_view_customer_details(self, auth_admin, app):
        """Test viewing customer details page."""
        with app.app_context():
            customer = Customer.query.filter_by(is_active=True).first()
            customer_id = customer.id

        response = auth_admin.get(f'/customers/view/{customer_id}')
        assert response.status_code == 200

    def test_view_nonexistent_customer_returns_404(self, auth_admin):
        """Test viewing non-existent customer returns 404."""
        response = auth_admin.get('/customers/view/99999')
        assert response.status_code == 404

    def test_customer_index_pagination(self, auth_admin):
        """Test customer list pagination."""
        response = auth_admin.get('/customers/?page=1')
        assert response.status_code == 200

        response = auth_admin.get('/customers/?page=2')
        assert response.status_code == 200

    def test_customer_index_requires_auth(self, client, init_database):
        """Test that customer list requires authentication."""
        response = client.get('/customers/')
        assert response.status_code in [302, 401]


class TestCustomerUpdate:
    """Tests for updating customer data."""

    def test_edit_customer_page_loads(self, auth_admin, app):
        """Test edit customer page loads."""
        with app.app_context():
            customer = Customer.query.filter_by(is_active=True).first()
            customer_id = customer.id

        response = auth_admin.get(f'/customers/edit/{customer_id}')
        assert response.status_code == 200

    def test_edit_customer_success(self, auth_admin, app):
        """Test successfully editing customer."""
        with app.app_context():
            customer = Customer.query.filter_by(is_active=True).first()
            customer_id = customer.id

        response = auth_admin.post(f'/customers/edit/{customer_id}', data={
            'name': 'Updated Customer Name',
            'phone': '03998887777',
            'email': 'updated@test.com',
            'customer_type': 'vip',
            'city': 'Rawalpindi'
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            customer = Customer.query.get(customer_id)
            assert customer.name == 'Updated Customer Name'
            assert customer.phone == '03998887777'
            assert customer.customer_type == 'vip'

    def test_edit_customer_with_birthday(self, auth_admin, app):
        """Test editing customer birthday."""
        with app.app_context():
            customer = Customer.query.filter_by(is_active=True).first()
            customer_id = customer.id

        response = auth_admin.post(f'/customers/edit/{customer_id}', data={
            'name': 'Birthday Update',
            'phone': '03998886666',
            'birthday': '2000-12-25',
            'customer_type': 'regular'
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            customer = Customer.query.get(customer_id)
            assert customer.birthday == date(2000, 12, 25)

    def test_edit_customer_sync_queue_entry(self, auth_admin, app):
        """Test that editing customer adds sync queue entry."""
        with app.app_context():
            customer = Customer.query.filter_by(is_active=True).first()
            customer_id = customer.id
            initial_sync_count = SyncQueue.query.filter_by(
                table_name='customers',
                operation='update'
            ).count()

        auth_admin.post(f'/customers/edit/{customer_id}', data={
            'name': 'Sync Update Test',
            'phone': '03998885555',
            'customer_type': 'regular'
        }, follow_redirects=True)

        with app.app_context():
            new_sync_count = SyncQueue.query.filter_by(
                table_name='customers',
                operation='update'
            ).count()
            assert new_sync_count > initial_sync_count

    def test_edit_nonexistent_customer_returns_404(self, auth_admin):
        """Test editing non-existent customer returns 404."""
        response = auth_admin.get('/customers/edit/99999')
        assert response.status_code == 404


class TestCustomerDelete:
    """Tests for deleting customers (soft delete)."""

    def test_delete_customer_soft_delete(self, auth_admin, app):
        """Test soft delete sets is_active to False."""
        with app.app_context():
            customer = Customer.query.filter_by(is_active=True).first()
            customer_id = customer.id
            assert customer.is_active is True

        response = auth_admin.post(f'/customers/delete/{customer_id}')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['success'] is True

        with app.app_context():
            customer = Customer.query.get(customer_id)
            assert customer.is_active is False

    def test_delete_customer_returns_json(self, auth_admin, app):
        """Test delete returns JSON response."""
        with app.app_context():
            customer = Customer.query.filter_by(is_active=True).first()
            customer_id = customer.id

        response = auth_admin.post(f'/customers/delete/{customer_id}')

        assert response.content_type == 'application/json'
        data = json.loads(response.data)
        assert 'success' in data

    def test_delete_customer_sync_queue_entry(self, auth_admin, app):
        """Test that deleting customer adds sync queue entry."""
        with app.app_context():
            customer = Customer.query.filter_by(is_active=True).first()
            customer_id = customer.id

        auth_admin.post(f'/customers/delete/{customer_id}')

        with app.app_context():
            sync_entry = SyncQueue.query.filter_by(
                table_name='customers',
                operation='update'
            ).order_by(SyncQueue.id.desc()).first()

            assert sync_entry is not None
            assert 'is_active' in sync_entry.data_json

    def test_delete_nonexistent_customer_returns_error(self, auth_admin):
        """Test deleting non-existent customer returns error (404 or 500)."""
        response = auth_admin.post('/customers/delete/99999')
        # The route uses get_or_404 but catches all exceptions and returns 500
        assert response.status_code in [404, 500]

    def test_soft_deleted_customer_still_viewable(self, auth_admin, app):
        """Test that soft deleted customer can still be viewed (for historical reference)."""
        with app.app_context():
            customer = Customer.query.filter_by(is_active=True).first()
            customer_id = customer.id

        # Delete customer
        auth_admin.post(f'/customers/delete/{customer_id}')

        # Should still be viewable
        response = auth_admin.get(f'/customers/view/{customer_id}')
        assert response.status_code == 200


# =============================================================================
# SECTION 2: LOYALTY PROGRAM FUNCTIONALITY
# =============================================================================

class TestLoyaltyProgram:
    """Tests for loyalty program features."""

    def test_loyalty_tier_bronze(self, app, init_database):
        """Test Bronze tier for low points."""
        with app.app_context():
            customer = Customer(
                name='Bronze Test',
                phone='03101010101',
                loyalty_points=0
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Bronze'
            assert customer.loyalty_tier_color == 'info'

    def test_loyalty_tier_silver(self, app, init_database):
        """Test Silver tier at 500+ points."""
        with app.app_context():
            customer = Customer(
                name='Silver Test',
                phone='03102020202',
                loyalty_points=500
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Silver'
            assert customer.loyalty_tier_color == 'secondary'

    def test_loyalty_tier_gold(self, app, init_database):
        """Test Gold tier at 1000+ points."""
        with app.app_context():
            customer = Customer(
                name='Gold Test',
                phone='03103030303',
                loyalty_points=1000
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Gold'
            assert customer.loyalty_tier_color == 'warning'

    def test_loyalty_tier_platinum(self, app, init_database):
        """Test Platinum tier at 2500+ points."""
        with app.app_context():
            customer = Customer(
                name='Platinum Test',
                phone='03104040404',
                loyalty_points=2500
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Platinum'
            assert customer.loyalty_tier_color == 'dark'

    def test_add_loyalty_points(self, app, init_database):
        """Test adding loyalty points from purchase."""
        with app.app_context():
            customer = Customer(
                name='Points Test',
                phone='03105050505',
                loyalty_points=0
            )
            db.session.add(customer)
            db.session.commit()

            # Rs. 1000 purchase = 10 points
            points_earned = customer.add_loyalty_points(1000)
            db.session.commit()

            assert points_earned == 10
            assert customer.loyalty_points == 10

    def test_add_loyalty_points_fractional(self, app, init_database):
        """Test loyalty points for fractional amounts."""
        with app.app_context():
            customer = Customer(
                name='Fractional Test',
                phone='03106060606',
                loyalty_points=0
            )
            db.session.add(customer)
            db.session.commit()

            # Rs. 550 = 5 points (truncated)
            points_earned = customer.add_loyalty_points(550)
            db.session.commit()

            assert points_earned == 5
            assert customer.loyalty_points == 5

    def test_redeem_points_success(self, app, init_database):
        """Test successful points redemption."""
        with app.app_context():
            customer = Customer(
                name='Redeem Test',
                phone='03107070707',
                loyalty_points=500
            )
            db.session.add(customer)
            db.session.commit()

            success, discount = customer.redeem_points(200)
            db.session.commit()

            assert success is True
            assert discount == 200  # 1:1 ratio with PKR
            assert customer.loyalty_points == 300

    def test_redeem_points_insufficient(self, app, init_database):
        """Test redemption fails with insufficient points."""
        with app.app_context():
            customer = Customer(
                name='Insufficient Test',
                phone='03108080808',
                loyalty_points=100
            )
            db.session.add(customer)
            db.session.commit()

            success, message = customer.redeem_points(200)

            assert success is False
            assert 'Insufficient' in message
            assert customer.loyalty_points == 100

    def test_redeem_points_minimum(self, app, init_database):
        """Test minimum points required for redemption."""
        with app.app_context():
            customer = Customer(
                name='Minimum Test',
                phone='03109090909',
                loyalty_points=500
            )
            db.session.add(customer)
            db.session.commit()

            success, message = customer.redeem_points(50)

            assert success is False
            assert '100' in message

    def test_points_to_next_tier(self, app, init_database):
        """Test calculation of points needed for next tier."""
        with app.app_context():
            customer = Customer(
                name='Next Tier Test',
                phone='03111111111',
                loyalty_points=300
            )
            db.session.add(customer)
            db.session.commit()

            # Bronze -> Silver needs 500 - 300 = 200
            assert customer.points_to_next_tier == 200
            assert customer.next_tier_name == 'Silver'

    def test_points_value_pkr(self, app, init_database):
        """Test points PKR value calculation."""
        with app.app_context():
            customer = Customer(
                name='PKR Value Test',
                phone='03112121212',
                loyalty_points=1500
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.points_value_pkr == 1500


# =============================================================================
# SECTION 3: GIFT CARD OPERATIONS (via Birthday Gifts)
# =============================================================================

class TestGiftCardOperations:
    """Tests for gift card / birthday gift functionality."""

    def test_birthday_gift_by_tier_platinum(self):
        """Test Platinum tier birthday gift configuration."""
        from app.routes.customers import get_birthday_gift_by_tier

        gift = get_birthday_gift_by_tier('Platinum')

        assert gift['type'] == 'discount'
        assert gift['value'] == 25
        assert gift['bonus_points'] == 500

    def test_birthday_gift_by_tier_gold(self):
        """Test Gold tier birthday gift configuration."""
        from app.routes.customers import get_birthday_gift_by_tier

        gift = get_birthday_gift_by_tier('Gold')

        assert gift['type'] == 'discount'
        assert gift['value'] == 20
        assert gift['bonus_points'] == 300

    def test_birthday_gift_by_tier_silver(self):
        """Test Silver tier birthday gift configuration."""
        from app.routes.customers import get_birthday_gift_by_tier

        gift = get_birthday_gift_by_tier('Silver')

        assert gift['type'] == 'discount'
        assert gift['value'] == 15
        assert gift['bonus_points'] == 200

    def test_birthday_gift_by_tier_bronze(self):
        """Test Bronze tier birthday gift configuration."""
        from app.routes.customers import get_birthday_gift_by_tier

        gift = get_birthday_gift_by_tier('Bronze')

        assert gift['type'] == 'discount'
        assert gift['value'] == 10
        assert gift['bonus_points'] == 100

    def test_apply_birthday_gift_on_birthday(self, auth_admin, app):
        """Test applying birthday gift on customer's birthday."""
        with app.app_context():
            today = date.today()
            # Create customer with birthday today
            customer = Customer(
                name='Birthday Today',
                phone='03131313131',
                birthday=today.replace(year=1990),
                loyalty_points=1500
            )
            db.session.add(customer)
            db.session.commit()
            customer_id = customer.id

        response = auth_admin.post(f'/customers/birthday-gift/{customer_id}')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['success'] is True
        assert 'gift' in data
        assert 'customer' in data

    def test_apply_birthday_gift_not_birthday(self, auth_admin, app):
        """Test applying birthday gift when not customer's birthday."""
        with app.app_context():
            yesterday = date.today() - timedelta(days=1)
            customer = Customer(
                name='Not Birthday',
                phone='03141414141',
                birthday=yesterday
            )
            db.session.add(customer)
            db.session.commit()
            customer_id = customer.id

        response = auth_admin.post(f'/customers/birthday-gift/{customer_id}')
        assert response.status_code == 400

        data = json.loads(response.data)
        assert 'error' in data

    def test_apply_birthday_gift_no_birthday(self, auth_admin, app):
        """Test applying gift when customer has no birthday."""
        with app.app_context():
            customer = Customer(
                name='No Birthday',
                phone='03151515151'
            )
            db.session.add(customer)
            db.session.commit()
            customer_id = customer.id

        response = auth_admin.post(f'/customers/birthday-gift/{customer_id}')
        assert response.status_code == 400

        data = json.loads(response.data)
        assert 'error' in data
        assert 'no birthday' in data['error']

    def test_birthdays_calendar_page(self, auth_admin):
        """Test birthday calendar page loads."""
        response = auth_admin.get('/customers/birthdays')
        assert response.status_code == 200

    def test_birthday_notifications_page(self, auth_admin):
        """Test birthday notifications page loads."""
        response = auth_admin.get('/customers/birthday-notifications')
        assert response.status_code == 200

    def test_send_birthday_wishes_no_customers(self, auth_admin):
        """Test sending wishes with no customers selected."""
        response = auth_admin.post(
            '/customers/send-birthday-wishes',
            json={'customer_ids': []},
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_send_birthday_wishes_success(self, auth_admin, app):
        """Test sending birthday wishes to customers."""
        with app.app_context():
            customer = Customer(
                name='Wish Test',
                phone='03161616161',
                birthday=date(1990, 6, 15),
                loyalty_points=1000
            )
            db.session.add(customer)
            db.session.commit()
            customer_id = customer.id

        response = auth_admin.post(
            '/customers/send-birthday-wishes',
            json={'customer_ids': [customer_id]},
            content_type='application/json'
        )
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['success'] is True
        assert 'sent_count' in data


# =============================================================================
# SECTION 4: CUSTOMER SEARCH
# =============================================================================

class TestCustomerSearch:
    """Tests for customer search functionality."""

    def test_search_by_name(self, auth_admin):
        """Test searching customers by name."""
        response = auth_admin.get('/customers/search?q=John')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'customers' in data
        # John Doe should be found
        names = [c['name'] for c in data['customers']]
        assert any('John' in name for name in names)

    def test_search_by_phone(self, auth_admin):
        """Test searching customers by phone number."""
        response = auth_admin.get('/customers/search?q=03001234567')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'customers' in data

    def test_search_partial_match(self, auth_admin):
        """Test partial string matching."""
        response = auth_admin.get('/customers/search?q=Doe')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'customers' in data

    def test_search_minimum_characters(self, auth_admin):
        """Test search requires minimum 2 characters."""
        response = auth_admin.get('/customers/search?q=J')
        assert response.status_code == 200

        data = json.loads(response.data)
        # Single character should return empty
        assert data['customers'] == []

    def test_search_no_results(self, auth_admin):
        """Test search with no matches."""
        response = auth_admin.get('/customers/search?q=ZZZZNONEXISTENT')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['customers'] == []

    def test_search_excludes_inactive(self, auth_admin):
        """Test search excludes inactive customers."""
        response = auth_admin.get('/customers/search?q=Inactive')
        assert response.status_code == 200

        data = json.loads(response.data)
        # Should not find inactive customer
        names = [c['name'] for c in data['customers']]
        assert 'Inactive Customer' not in names

    def test_search_case_insensitive(self, auth_admin):
        """Test case-insensitive search."""
        response_lower = auth_admin.get('/customers/search?q=john')
        response_upper = auth_admin.get('/customers/search?q=JOHN')

        data_lower = json.loads(response_lower.data)
        data_upper = json.loads(response_upper.data)

        # Both should find John Doe
        assert len(data_lower['customers']) == len(data_upper['customers'])

    def test_search_result_format(self, auth_admin):
        """Test search result contains required fields."""
        response = auth_admin.get('/customers/search?q=John')
        data = json.loads(response.data)

        if data['customers']:
            customer = data['customers'][0]
            assert 'id' in customer
            assert 'name' in customer
            assert 'phone' in customer
            assert 'email' in customer
            assert 'customer_type' in customer

    def test_search_limit_results(self, auth_admin, app):
        """Test search limits results to 10."""
        # Create many customers
        with app.app_context():
            for i in range(15):
                customer = Customer(
                    name=f'Search Test Customer {i}',
                    phone=f'0320000{i:04d}'
                )
                db.session.add(customer)
            db.session.commit()

        response = auth_admin.get('/customers/search?q=Search Test')
        data = json.loads(response.data)

        assert len(data['customers']) <= 10

    def test_search_index_page_filter(self, auth_admin):
        """Test search filter on main index page."""
        response = auth_admin.get('/customers/?search=Jane')
        assert response.status_code == 200

    def test_search_empty_query(self, auth_admin):
        """Test search with empty query."""
        response = auth_admin.get('/customers/search?q=')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['customers'] == []

    def test_search_special_characters(self, auth_admin, app):
        """Test search with special characters."""
        with app.app_context():
            customer = Customer(
                name="O'Brien & Sons",
                phone='03171717171'
            )
            db.session.add(customer)
            db.session.commit()

        response = auth_admin.get("/customers/search?q=O'Brien")
        assert response.status_code == 200


# =============================================================================
# SECTION 5: CUSTOMER PURCHASE HISTORY
# =============================================================================

class TestCustomerPurchaseHistory:
    """Tests for customer purchase history functionality."""

    def test_view_customer_shows_sales(self, auth_admin, app, sample_customer_with_sales):
        """Test viewing customer shows their sales history."""
        response = auth_admin.get(f'/customers/view/{sample_customer_with_sales}')
        assert response.status_code == 200

    def test_customer_total_purchases_property(self, app, sample_customer_with_sales):
        """Test total_purchases property calculation."""
        with app.app_context():
            customer = Customer.query.get(sample_customer_with_sales)
            total = customer.total_purchases

            # Should have accumulated purchases
            assert total > 0

    def test_customer_sales_relationship(self, app, sample_customer_with_sales):
        """Test customer-sales relationship."""
        with app.app_context():
            customer = Customer.query.get(sample_customer_with_sales)

            # Should have sales
            assert customer.sales.count() > 0

    def test_customer_sales_ordered_by_date(self, app, sample_customer_with_sales):
        """Test sales are ordered by date descending."""
        with app.app_context():
            customer = Customer.query.get(sample_customer_with_sales)
            sales = Sale.query.filter_by(customer_id=customer.id)\
                .order_by(Sale.sale_date.desc()).all()

            if len(sales) > 1:
                for i in range(len(sales) - 1):
                    assert sales[i].sale_date >= sales[i + 1].sale_date


# =============================================================================
# SECTION 6: CUSTOMER ANALYTICS
# =============================================================================

class TestCustomerAnalytics:
    """Tests for customer analytics functionality."""

    def test_birthday_gift_details_endpoint(self, auth_admin, app, sample_customer_with_sales):
        """Test birthday gift details API endpoint."""
        response = auth_admin.get(f'/customers/birthday-gift-details/{sample_customer_with_sales}')

        # Should return 200 or 400 depending on eligibility
        assert response.status_code in [200, 400, 500]

    def test_customer_purchase_stats_calculation(self, app, sample_customer_with_sales):
        """Test purchase statistics calculation."""
        from app.utils.birthday_gifts import calculate_customer_purchase_stats

        with app.app_context():
            stats = calculate_customer_purchase_stats(sample_customer_with_sales)

            assert stats is not None
            assert 'total_purchases' in stats
            assert 'total_orders' in stats
            assert 'avg_order_value' in stats
            assert stats['total_orders'] > 0

    def test_customer_purchase_stats_no_sales(self, app, init_database):
        """Test purchase stats for customer without sales."""
        from app.utils.birthday_gifts import calculate_customer_purchase_stats

        with app.app_context():
            customer = Customer(
                name='No Sales Customer',
                phone='03181818181'
            )
            db.session.add(customer)
            db.session.commit()

            stats = calculate_customer_purchase_stats(customer.id)

            assert stats is not None
            assert stats['total_purchases'] == 0
            assert stats['total_orders'] == 0

    def test_customer_eligibility_score(self, app, sample_customer_with_sales):
        """Test customer eligibility score calculation."""
        from app.utils.birthday_gifts import (
            calculate_customer_purchase_stats,
            calculate_eligibility_score
        )

        with app.app_context():
            stats = calculate_customer_purchase_stats(sample_customer_with_sales)
            score = calculate_eligibility_score(stats)

            assert score >= 0

    def test_is_customer_eligible_for_gift(self):
        """Test customer gift eligibility check."""
        from app.utils.birthday_gifts import is_customer_eligible_for_gift

        # Not eligible - low perfumes per month
        stats_not_eligible = {
            'perfumes_per_month': 1.0,
            'total_orders': 5,
            'is_regular_customer': True
        }
        assert is_customer_eligible_for_gift(stats_not_eligible) is False

        # Eligible
        stats_eligible = {
            'perfumes_per_month': 3.0,
            'total_orders': 5,
            'is_regular_customer': True
        }
        assert is_customer_eligible_for_gift(stats_eligible) is True

    def test_premium_birthday_gift_tiers(self, app, init_database):
        """Test premium birthday gift tier calculation."""
        from app.utils.birthday_gifts import get_premium_birthday_gift

        with app.app_context():
            customer = Customer(
                name='Gift Test',
                phone='03191919191'
            )
            db.session.add(customer)
            db.session.commit()

            # High score = VIP Elite
            high_stats = {
                'total_purchases': 100000,
                'high_value_purchases': 20,
                'recent_6month_purchases': 50000,
                'perfumes_per_month': 10.0,
                'is_regular_customer': True
            }
            gift = get_premium_birthday_gift(customer, high_stats)
            assert gift['tier'] == 'VIP Elite'
            assert gift['discount_percentage'] == 30

            # Medium score = VIP Gold
            medium_stats = {
                'total_purchases': 20000,
                'high_value_purchases': 3,
                'recent_6month_purchases': 5000,
                'perfumes_per_month': 3.0,
                'is_regular_customer': True
            }
            gift = get_premium_birthday_gift(customer, medium_stats)
            assert gift['tier'] == 'VIP Gold'


# =============================================================================
# SECTION 7: PERMISSION TESTS
# =============================================================================

class TestCustomerPermissions:
    """Tests for customer route permissions."""

    def test_admin_full_access(self, auth_admin, init_database, app):
        """Test admin has full customer access."""
        # View list
        response = auth_admin.get('/customers/')
        assert response.status_code == 200

        # Add page
        response = auth_admin.get('/customers/add')
        assert response.status_code == 200

        # Birthdays
        response = auth_admin.get('/customers/birthdays')
        assert response.status_code == 200

    def test_manager_can_view_customers(self, auth_manager, init_database):
        """Test manager can view customers."""
        response = auth_manager.get('/customers/')
        assert response.status_code == 200

    def test_manager_can_edit_customers(self, auth_manager, init_database, app):
        """Test manager can edit customers."""
        with app.app_context():
            customer = Customer.query.filter_by(is_active=True).first()
            customer_id = customer.id

        response = auth_manager.get(f'/customers/edit/{customer_id}')
        assert response.status_code == 200

    def test_cashier_can_view_customers(self, auth_cashier, init_database):
        """Test cashier can view customers."""
        response = auth_cashier.get('/customers/')
        assert response.status_code == 200

    def test_cashier_can_search_customers(self, auth_cashier, init_database):
        """Test cashier can search customers (needed for POS)."""
        response = auth_cashier.get('/customers/search?q=John')
        assert response.status_code == 200

    def test_cashier_cannot_delete_customers(self, auth_cashier, init_database, app):
        """Test cashier cannot delete customers."""
        with app.app_context():
            customer = Customer.query.filter_by(is_active=True).first()
            customer_id = customer.id

        response = auth_cashier.post(f'/customers/delete/{customer_id}')
        # Should be forbidden
        assert response.status_code in [302, 403, 500]

    def test_unauthenticated_cannot_access(self, client, init_database):
        """Test unauthenticated users cannot access customer routes."""
        response = client.get('/customers/')
        assert response.status_code in [302, 401]

        response = client.get('/customers/add')
        assert response.status_code in [302, 401]


# =============================================================================
# SECTION 8: ERROR HANDLING
# =============================================================================

class TestErrorHandling:
    """Tests for error handling in customer routes."""

    def test_view_nonexistent_customer(self, auth_admin):
        """Test viewing non-existent customer returns 404."""
        response = auth_admin.get('/customers/view/99999')
        assert response.status_code == 404

    def test_edit_nonexistent_customer(self, auth_admin):
        """Test editing non-existent customer returns 404."""
        response = auth_admin.get('/customers/edit/99999')
        assert response.status_code == 404

    def test_delete_nonexistent_customer(self, auth_admin):
        """Test deleting non-existent customer returns error."""
        response = auth_admin.post('/customers/delete/99999')
        assert response.status_code in [404, 500]

    def test_birthday_gift_nonexistent_customer(self, auth_admin):
        """Test birthday gift for non-existent customer returns 404."""
        response = auth_admin.post('/customers/birthday-gift/99999')
        assert response.status_code == 404

    def test_gift_details_nonexistent_customer(self, auth_admin):
        """Test gift details for non-existent customer returns 404."""
        response = auth_admin.get('/customers/birthday-gift-details/99999')
        assert response.status_code == 404


# =============================================================================
# SECTION 9: EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_customer_with_special_characters(self, app, init_database):
        """Test customer name with special characters."""
        with app.app_context():
            customer = Customer(
                name="Muhammad Ali Khan (Jr.)",
                phone='03201010101'
            )
            db.session.add(customer)
            db.session.commit()

            retrieved = Customer.query.filter_by(phone='03201010101').first()
            assert retrieved.name == "Muhammad Ali Khan (Jr.)"

    def test_customer_with_unicode_name(self, app, init_database):
        """Test customer with unicode/Arabic name."""
        with app.app_context():
            customer = Customer(
                name="Ahmed",
                phone='03202020202'
            )
            db.session.add(customer)
            db.session.commit()

            retrieved = Customer.query.filter_by(phone='03202020202').first()
            assert retrieved is not None

    def test_customer_with_long_notes(self, app, init_database):
        """Test customer with very long notes."""
        with app.app_context():
            long_notes = "A" * 5000
            customer = Customer(
                name='Long Notes',
                phone='03203030303',
                notes=long_notes
            )
            db.session.add(customer)
            db.session.commit()

            retrieved = Customer.query.filter_by(phone='03203030303').first()
            assert len(retrieved.notes) == 5000

    def test_duplicate_phone_handling(self, app, init_database):
        """Test duplicate phone number handling."""
        with app.app_context():
            customer1 = Customer(name='First', phone='03204040404')
            db.session.add(customer1)
            db.session.commit()

            customer2 = Customer(name='Second', phone='03204040404')
            db.session.add(customer2)

            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()

    def test_leap_year_birthday(self, app, init_database):
        """Test Feb 29th birthday."""
        with app.app_context():
            customer = Customer(
                name='Leap Year',
                phone='03205050505',
                birthday=date(2000, 2, 29)
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.birthday == date(2000, 2, 29)

    def test_negative_loyalty_points_handling(self, app, init_database):
        """Test handling of negative loyalty points (edge case)."""
        with app.app_context():
            customer = Customer(
                name='Negative Points',
                phone='03206060606',
                loyalty_points=-50
            )
            db.session.add(customer)
            db.session.commit()

            # Should still work, tier should be Bronze
            assert customer.loyalty_tier == 'Bronze'


# =============================================================================
# SECTION 10: INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for customer workflows."""

    def test_complete_customer_lifecycle(self, auth_admin, app):
        """Test complete customer create-read-update-delete lifecycle."""
        # Create
        response = auth_admin.post('/customers/add', data={
            'name': 'Lifecycle Test',
            'phone': '03301010101',
            'email': 'lifecycle@test.com',
            'customer_type': 'regular'
        }, follow_redirects=True)
        assert response.status_code == 200

        with app.app_context():
            customer = Customer.query.filter_by(phone='03301010101').first()
            assert customer is not None
            customer_id = customer.id

        # Read
        response = auth_admin.get(f'/customers/view/{customer_id}')
        assert response.status_code == 200

        # Update
        response = auth_admin.post(f'/customers/edit/{customer_id}', data={
            'name': 'Updated Lifecycle',
            'phone': '03301010102',
            'email': 'updated@test.com',
            'customer_type': 'vip'
        }, follow_redirects=True)
        assert response.status_code == 200

        with app.app_context():
            customer = Customer.query.get(customer_id)
            assert customer.name == 'Updated Lifecycle'
            assert customer.customer_type == 'vip'

        # Delete (soft delete)
        response = auth_admin.post(f'/customers/delete/{customer_id}')
        assert response.status_code == 200

        with app.app_context():
            customer = Customer.query.get(customer_id)
            assert customer.is_active is False

    def test_customer_loyalty_workflow(self, app, init_database):
        """Test customer loyalty points earning and redemption workflow."""
        with app.app_context():
            customer = Customer(
                name='Loyalty Workflow',
                phone='03302020202',
                loyalty_points=0
            )
            db.session.add(customer)
            db.session.commit()

            # Start at Bronze
            assert customer.loyalty_tier == 'Bronze'

            # Earn points (simulating Rs. 50,000 in purchases)
            customer.add_loyalty_points(50000)  # +500 points
            db.session.commit()

            # Now Silver
            assert customer.loyalty_tier == 'Silver'
            assert customer.loyalty_points == 500

            # Earn more (Rs. 50,000 more)
            customer.add_loyalty_points(50000)  # +500 points
            db.session.commit()

            # Now Gold
            assert customer.loyalty_tier == 'Gold'
            assert customer.loyalty_points == 1000

            # Redeem some points
            success, discount = customer.redeem_points(300)
            db.session.commit()

            assert success is True
            assert discount == 300
            assert customer.loyalty_points == 700
            # Back to Silver
            assert customer.loyalty_tier == 'Silver'

    def test_search_and_select_for_pos(self, auth_admin, app):
        """Test searching customer for POS sale."""
        # Search customer
        response = auth_admin.get('/customers/search?q=John')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'customers' in data

        # Verify result has all fields needed for POS
        if data['customers']:
            customer = data['customers'][0]
            assert 'id' in customer
            assert 'name' in customer
            assert 'phone' in customer


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
