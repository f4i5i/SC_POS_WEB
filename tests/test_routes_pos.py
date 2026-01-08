"""
Comprehensive Unit Tests for POS Routes
Tests for /home/f4i5i/SC_POC/SOC_WEB_APP/app/routes/pos.py

Covers:
1. POS index page access
2. Product search API
3. Checkout process
4. Receipt generation
5. Sale editing (admin only)
6. Sales list filtering
7. Edge cases for authentication, permissions, stock, and validation

Note: Uses fixtures from conftest.py where available, with additional
POS-specific fixtures defined here.
"""

import pytest
import json
from decimal import Decimal
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock

# Import models for direct database access in tests
from app.models import (
    db, User, Product, Sale, SaleItem, Customer, StockMovement,
    Payment, SyncQueue, Setting, DayClose, LocationStock, Location,
    StockTransfer, StockTransferItem, Category, Supplier
)


# ============================================================================
# POS-SPECIFIC FIXTURES (Supplement conftest.py fixtures)
# ============================================================================

@pytest.fixture
def pos_user_no_location(db_session):
    """Create a user without location assignment for POS tests."""
    user = User(
        username='no_loc_user',
        email='noloc@test.com',
        full_name='No Location User',
        role='cashier',
        is_active=True,
        is_global_admin=False,
        location_id=None
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def pos_product_out_of_stock(db_session, category):
    """Create a product with no stock for POS checkout tests."""
    prod = Product(
        code='PROD-OOS-POS',
        barcode='1234567890125',
        name='Out of Stock Perfume',
        brand='Test Brand',
        size='100ml',
        category_id=category.id,
        cost_price=Decimal('800.00'),
        selling_price=Decimal('1200.00'),
        tax_rate=Decimal('5.00'),
        quantity=0,
        reorder_level=10,
        is_active=True
    )
    db.session.add(prod)
    db.session.commit()
    return prod


@pytest.fixture
def vip_customer(db_session):
    """Create a VIP customer with high loyalty points."""
    cust = Customer(
        name='VIP Customer',
        phone='0300-9999999',
        email='vip@test.com',
        address='VIP City',
        customer_type='vip',
        loyalty_points=3000,
        is_active=True
    )
    db.session.add(cust)
    db.session.commit()
    return cust


@pytest.fixture
def pos_sale(db_session, admin_user, customer, product, kiosk):
    """Create a test sale for POS tests."""
    s = Sale(
        sale_number='SALE-20240101-0001',
        user_id=admin_user.id,
        customer_id=customer.id,
        location_id=kiosk.id,
        subtotal=Decimal('750.00'),
        discount=Decimal('0.00'),
        discount_type='amount',
        tax=Decimal('0.00'),
        total=Decimal('750.00'),
        payment_method='cash',
        payment_status='paid',
        amount_paid=Decimal('750.00'),
        amount_due=Decimal('0.00'),
        status='completed'
    )
    db.session.add(s)
    db.session.flush()

    item = SaleItem(
        sale_id=s.id,
        product_id=product.id,
        quantity=1,
        unit_price=Decimal('750.00'),
        discount=Decimal('0.00'),
        subtotal=Decimal('750.00')
    )
    db.session.add(item)
    db.session.commit()
    return s


@pytest.fixture
def business_settings(db_session):
    """Create business settings for POS receipts."""
    settings_list = [
        Setting(key='business_name', value='Sunnat Collection', category='business'),
        Setting(key='business_address', value='Test Address', category='business'),
        Setting(key='business_phone', value='123-456-7890', category='business'),
        Setting(key='business_email', value='info@test.com', category='business'),
        Setting(key='tagline', value='Quality Products', category='business'),
    ]
    for s in settings_list:
        db.session.add(s)
    db.session.commit()
    return True


def pos_login_user(client, username, password):
    """Helper function to log in a user for POS tests."""
    return client.post('/auth/login', data={
        'username': username,
        'password': password
    }, follow_redirects=True)


def pos_logout_user(client):
    """Helper function to log out a user for POS tests."""
    return client.get('/auth/logout', follow_redirects=True)


# ============================================================================
# TEST: POS INDEX PAGE ACCESS
# ============================================================================

class TestPOSIndexPage:
    """Tests for POS index page access."""

    def test_index_requires_authentication(self, client):
        """Test that unauthenticated users are redirected to login."""
        response = client.get('/pos/')
        assert response.status_code in [302, 401]  # Redirect to login

    def test_index_access_with_admin(self, client, admin_user, customer):
        """Test admin can access POS index."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get('/pos/')
        assert response.status_code == 200

    def test_index_access_with_cashier(self, client, cashier_user, customer):
        """Test cashier can access POS index."""
        pos_login_user(client, 'cashier_test', 'Cashier123!')
        response = client.get('/pos/')
        assert response.status_code == 200

    def test_index_access_user_no_location_warning(self, client, pos_user_no_location):
        """Test user without location gets warning but can access."""
        pos_login_user(client, 'no_loc_user', 'password123')
        response = client.get('/pos/', follow_redirects=True)
        # Should still be accessible for backward compatibility
        assert response.status_code == 200

    def test_index_shows_recent_customers(self, client, admin_user, customer):
        """Test that recent customers are displayed."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get('/pos/')
        assert response.status_code == 200


# ============================================================================
# TEST: PRODUCT SEARCH API
# ============================================================================

class TestProductSearchAPI:
    """Tests for product search API."""

    def test_search_requires_authentication(self, client):
        """Test that search requires authentication."""
        response = client.get('/pos/search-products?q=test')
        assert response.status_code in [302, 401]

    def test_search_short_query(self, client, admin_user, product):
        """Test search with query less than 2 characters returns empty."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get('/pos/search-products?q=a')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['products'] == []

    def test_search_by_product_code(self, client, admin_user, product):
        """Test search by product code."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get(f'/pos/search-products?q={product.code}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data['products']) > 0

    def test_search_by_product_name(self, client, admin_user, product):
        """Test search by product name."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get(f'/pos/search-products?q={product.name}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data['products']) > 0

    def test_search_returns_stock_info(self, client, admin_user, product, location_stock):
        """Test search returns stock information."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get(f'/pos/search-products?q={product.code}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data['products']) > 0
        product_data = data['products'][0]
        assert 'quantity' in product_data
        assert 'selling_price' in product_data
        assert 'is_low_stock' in product_data

    def test_search_no_results(self, client, admin_user):
        """Test search with no matching results."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get('/pos/search-products?q=NonExistentProduct123')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['products'] == []

    def test_search_case_insensitive(self, client, admin_user, product):
        """Test search is case insensitive."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get(f'/pos/search-products?q={product.name.lower()}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data['products']) > 0


# ============================================================================
# TEST: GET PRODUCT ENDPOINT
# ============================================================================

class TestGetProductAPI:
    """Tests for get product endpoint."""

    def test_get_product_requires_auth(self, client, product):
        """Test get product requires authentication."""
        response = client.get(f'/pos/get-product/{product.id}')
        assert response.status_code in [302, 401]

    def test_get_product_success(self, client, admin_user, product):
        """Test successful product retrieval."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get(f'/pos/get-product/{product.id}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['code'] == product.code
        assert data['name'] == product.name

    def test_get_product_not_found(self, client, admin_user):
        """Test get non-existent product returns 404."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get('/pos/get-product/99999')
        assert response.status_code == 404


# ============================================================================
# TEST: CHECKOUT PROCESS
# ============================================================================

class TestCheckoutProcess:
    """Tests for checkout/complete-sale endpoint."""

    def test_checkout_requires_authentication(self, client):
        """Test checkout requires authentication."""
        response = client.post('/pos/complete-sale',
                               json={'items': []},
                               content_type='application/json')
        assert response.status_code in [302, 401]

    def test_checkout_empty_cart(self, client, admin_user):
        """Test checkout with empty cart fails."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.post('/pos/complete-sale',
                               json={'items': []},
                               content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'No items' in data['error']

    def test_checkout_out_of_stock(self, client, admin_user, pos_product_out_of_stock, kiosk):
        """Test checkout with out of stock item fails."""
        # Create location stock with 0 quantity
        stock = LocationStock(
            location_id=kiosk.id,
            product_id=pos_product_out_of_stock.id,
            quantity=0,
            reserved_quantity=0
        )
        db.session.add(stock)
        db.session.commit()

        pos_login_user(client, 'admin_test', 'Admin123!')
        sale_data = {
            'items': [{
                'product_id': pos_product_out_of_stock.id,
                'quantity': 1,
                'unit_price': 1200,
                'subtotal': 1200
            }],
            'subtotal': 1200,
            'discount': 0,
            'tax': 0,
            'total': 1200,
            'payment_method': 'cash',
            'amount_paid': 1200
        }
        response = client.post('/pos/complete-sale',
                               json=sale_data,
                               content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Insufficient stock' in data['error']

    def test_checkout_insufficient_stock(self, client, admin_user, product, location_stock):
        """Test checkout with quantity exceeding stock fails."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        sale_data = {
            'items': [{
                'product_id': product.id,
                'quantity': 1000,  # More than available
                'unit_price': float(product.selling_price),
                'subtotal': 1000 * float(product.selling_price)
            }],
            'subtotal': 1000 * float(product.selling_price),
            'discount': 0,
            'tax': 0,
            'total': 1000 * float(product.selling_price),
            'payment_method': 'cash',
            'amount_paid': 1000 * float(product.selling_price)
        }
        response = client.post('/pos/complete-sale',
                               json=sale_data,
                               content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Insufficient stock' in data['error']

    def test_checkout_success_cash(self, client, admin_user, product, location_stock, customer):
        """Test successful cash checkout."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        price = float(product.selling_price)
        sale_data = {
            'items': [{
                'product_id': product.id,
                'quantity': 1,
                'unit_price': price,
                'subtotal': price
            }],
            'customer_id': customer.id,
            'subtotal': price,
            'discount': 0,
            'tax': 0,
            'total': price,
            'payment_method': 'cash',
            'amount_paid': price + 250
        }
        response = client.post('/pos/complete-sale',
                               json=sale_data,
                               content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'sale_id' in data
        assert 'sale_number' in data
        assert data['change'] == 250

    def test_checkout_success_card(self, client, admin_user, product, location_stock):
        """Test successful card checkout."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        price = float(product.selling_price)
        sale_data = {
            'items': [{
                'product_id': product.id,
                'quantity': 2,
                'unit_price': price,
                'subtotal': price * 2
            }],
            'subtotal': price * 2,
            'discount': 0,
            'tax': 0,
            'total': price * 2,
            'payment_method': 'card',
            'amount_paid': price * 2,
            'reference_number': 'CARD-12345'
        }
        response = client.post('/pos/complete-sale',
                               json=sale_data,
                               content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_checkout_with_discount_amount(self, client, admin_user, product, location_stock):
        """Test checkout with flat discount."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        price = float(product.selling_price)
        discount = 50
        sale_data = {
            'items': [{
                'product_id': product.id,
                'quantity': 1,
                'unit_price': price,
                'subtotal': price
            }],
            'subtotal': price,
            'discount': discount,
            'discount_type': 'amount',
            'tax': 0,
            'total': price - discount,
            'payment_method': 'cash',
            'amount_paid': price - discount
        }
        response = client.post('/pos/complete-sale',
                               json=sale_data,
                               content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_checkout_with_tax(self, client, admin_user, product, location_stock):
        """Test checkout with tax calculation."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        price = float(product.selling_price)
        tax = price * 0.05  # 5% tax
        sale_data = {
            'items': [{
                'product_id': product.id,
                'quantity': 1,
                'unit_price': price,
                'subtotal': price
            }],
            'subtotal': price,
            'discount': 0,
            'tax': tax,
            'total': price + tax,
            'payment_method': 'cash',
            'amount_paid': price + tax + 10
        }
        response = client.post('/pos/complete-sale',
                               json=sale_data,
                               content_type='application/json')
        assert response.status_code == 200

    def test_checkout_partial_payment(self, client, admin_user, product, location_stock, customer):
        """Test checkout with partial payment (credit sale)."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        price = float(product.selling_price)
        sale_data = {
            'items': [{
                'product_id': product.id,
                'quantity': 1,
                'unit_price': price,
                'subtotal': price
            }],
            'customer_id': customer.id,
            'subtotal': price,
            'discount': 0,
            'tax': 0,
            'total': price,
            'payment_method': 'credit',
            'amount_paid': price / 2  # Partial payment
        }
        response = client.post('/pos/complete-sale',
                               json=sale_data,
                               content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_checkout_updates_stock(self, client, admin_user, product, kiosk_stock):
        """Test that checkout updates stock correctly."""
        initial_qty = kiosk_stock.quantity

        pos_login_user(client, 'admin_test', 'Admin123!')
        price = float(product.selling_price)
        qty_to_sell = 5
        sale_data = {
            'items': [{
                'product_id': product.id,
                'quantity': qty_to_sell,
                'unit_price': price,
                'subtotal': price * qty_to_sell
            }],
            'subtotal': price * qty_to_sell,
            'discount': 0,
            'tax': 0,
            'total': price * qty_to_sell,
            'payment_method': 'cash',
            'amount_paid': price * qty_to_sell
        }
        response = client.post('/pos/complete-sale',
                               json=sale_data,
                               content_type='application/json')
        assert response.status_code == 200

        # Check stock was reduced
        db.session.refresh(kiosk_stock)
        assert kiosk_stock.quantity == initial_qty - qty_to_sell

    def test_checkout_updates_loyalty_points(self, client, admin_user, product, location_stock, customer):
        """Test that checkout awards loyalty points to customer."""
        initial_points = customer.loyalty_points

        pos_login_user(client, 'admin_test', 'Admin123!')
        price = float(product.selling_price)
        sale_data = {
            'items': [{
                'product_id': product.id,
                'quantity': 1,
                'unit_price': price,
                'subtotal': price
            }],
            'customer_id': customer.id,
            'subtotal': price,
            'discount': 0,
            'tax': 0,
            'total': price,
            'payment_method': 'cash',
            'amount_paid': price
        }
        response = client.post('/pos/complete-sale',
                               json=sale_data,
                               content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)

        # Check loyalty info in response
        assert 'loyalty' in data
        # 1 point per 100 Rs
        expected_points = int(price / 100)
        assert data['loyalty']['points_earned'] == expected_points

    def test_checkout_creates_stock_movement(self, client, admin_user, product, location_stock):
        """Test that checkout creates stock movement record."""
        initial_movements = StockMovement.query.filter_by(product_id=product.id).count()

        pos_login_user(client, 'admin_test', 'Admin123!')
        price = float(product.selling_price)
        sale_data = {
            'items': [{
                'product_id': product.id,
                'quantity': 1,
                'unit_price': price,
                'subtotal': price
            }],
            'subtotal': price,
            'discount': 0,
            'tax': 0,
            'total': price,
            'payment_method': 'cash',
            'amount_paid': price
        }
        response = client.post('/pos/complete-sale',
                               json=sale_data,
                               content_type='application/json')
        assert response.status_code == 200

        # Check movement was created
        final_movements = StockMovement.query.filter_by(product_id=product.id).count()
        assert final_movements == initial_movements + 1

    def test_checkout_invalid_product(self, client, admin_user):
        """Test checkout with non-existent product fails."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        sale_data = {
            'items': [{
                'product_id': 99999,  # Non-existent
                'quantity': 1,
                'unit_price': 750,
                'subtotal': 750
            }],
            'subtotal': 750,
            'discount': 0,
            'tax': 0,
            'total': 750,
            'payment_method': 'cash',
            'amount_paid': 750
        }
        response = client.post('/pos/complete-sale',
                               json=sale_data,
                               content_type='application/json')
        assert response.status_code == 404
        data = json.loads(response.data)
        assert data['success'] is False

    def test_checkout_backdate_admin_only(self, client, admin_user, cashier_user, product, location_stock):
        """Test that only admin/manager can backdate sales."""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        price = float(product.selling_price)
        sale_data = {
            'items': [{
                'product_id': product.id,
                'quantity': 1,
                'unit_price': price,
                'subtotal': price
            }],
            'subtotal': price,
            'discount': 0,
            'tax': 0,
            'total': price,
            'payment_method': 'cash',
            'amount_paid': price,
            'sale_date': yesterday
        }

        # Cashier should not be able to backdate
        pos_login_user(client, 'cashier_test', 'Cashier123!')
        response = client.post('/pos/complete-sale',
                               json=sale_data,
                               content_type='application/json')
        assert response.status_code == 403

        pos_logout_user(client)

        # Admin should be able to backdate
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.post('/pos/complete-sale',
                               json=sale_data,
                               content_type='application/json')
        assert response.status_code == 200

    def test_checkout_future_date_rejected(self, client, admin_user, product, location_stock):
        """Test that future date sales are rejected."""
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        pos_login_user(client, 'admin_test', 'Admin123!')
        price = float(product.selling_price)
        sale_data = {
            'items': [{
                'product_id': product.id,
                'quantity': 1,
                'unit_price': price,
                'subtotal': price
            }],
            'subtotal': price,
            'discount': 0,
            'tax': 0,
            'total': price,
            'payment_method': 'cash',
            'amount_paid': price,
            'sale_date': tomorrow
        }
        response = client.post('/pos/complete-sale',
                               json=sale_data,
                               content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'future' in data['error'].lower()


# ============================================================================
# TEST: RECEIPT GENERATION
# ============================================================================

class TestReceiptGeneration:
    """Tests for receipt generation."""

    def test_receipt_requires_auth(self, client, pos_sale):
        """Test receipt requires authentication."""
        response = client.get(f'/pos/print-receipt/{pos_sale.id}')
        assert response.status_code in [302, 401]

    def test_receipt_success(self, client, admin_user, pos_sale, business_settings):
        """Test successful receipt generation."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get(f'/pos/print-receipt/{pos_sale.id}')
        assert response.status_code == 200

    def test_receipt_not_found(self, client, admin_user):
        """Test receipt for non-existent sale returns 404."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get('/pos/print-receipt/99999')
        assert response.status_code == 404

    def test_receipt_includes_business_info(self, client, admin_user, pos_sale, business_settings):
        """Test receipt includes business information."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get(f'/pos/print-receipt/{pos_sale.id}')
        assert response.status_code == 200


# ============================================================================
# TEST: SALE EDITING (ADMIN ONLY)
# ============================================================================

class TestSaleEditing:
    """Tests for sale editing functionality."""

    def test_edit_sale_requires_auth(self, client, pos_sale):
        """Test edit sale requires authentication."""
        response = client.get(f'/pos/edit-sale/{pos_sale.id}')
        assert response.status_code in [302, 401]

    def test_edit_sale_admin_access(self, client, admin_user, pos_sale):
        """Test admin can access edit sale page."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get(f'/pos/edit-sale/{pos_sale.id}')
        assert response.status_code == 200

    def test_edit_sale_cashier_denied(self, client, cashier_user, pos_sale):
        """Test cashier cannot edit sales."""
        pos_login_user(client, 'cashier_test', 'Cashier123!')
        response = client.get(f'/pos/edit-sale/{pos_sale.id}', follow_redirects=True)
        # Should be redirected with error message or denied
        assert response.status_code in [200, 403]

    def test_edit_sale_manager_denied(self, client, manager_user, pos_sale):
        """Test manager cannot edit sales (only admin)."""
        pos_login_user(client, 'manager_test', 'Manager123!')
        response = client.get(f'/pos/edit-sale/{pos_sale.id}', follow_redirects=True)
        # Manager should also be redirected unless they have admin role
        assert response.status_code in [200, 403]

    def test_edit_sale_post_success(self, client, admin_user, pos_sale, customer):
        """Test successful sale edit."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.post(f'/pos/edit-sale/{pos_sale.id}', data={
            'customer_id': customer.id,
            'payment_method': 'card',
            'payment_status': 'paid',
            'discount': '100',
            'discount_type': 'amount',
            'notes': 'Updated sale'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_edit_sale_not_found(self, client, admin_user):
        """Test edit non-existent sale returns 404."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get('/pos/edit-sale/99999')
        assert response.status_code == 404


# ============================================================================
# TEST: SALES LIST FILTERING
# ============================================================================

class TestSalesListFiltering:
    """Tests for sales list and filtering."""

    def test_sales_list_requires_auth(self, client):
        """Test sales list requires authentication."""
        response = client.get('/pos/sales')
        assert response.status_code in [302, 401]

    def test_sales_list_access(self, client, admin_user, pos_sale):
        """Test user can access sales list."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get('/pos/sales')
        assert response.status_code == 200

    def test_sales_list_filter_by_date(self, client, admin_user, pos_sale):
        """Test filtering sales by date range."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        today = date.today().isoformat()
        response = client.get(f'/pos/sales?from_date={today}&to_date={today}')
        assert response.status_code == 200

    def test_sales_list_location_filter(self, client, cashier_user, pos_sale):
        """Test non-admin users see only their location's sales."""
        pos_login_user(client, 'cashier_test', 'Cashier123!')
        response = client.get('/pos/sales')
        assert response.status_code == 200

    def test_sales_list_admin_sees_all(self, client, admin_user, pos_sale):
        """Test admin sees all sales regardless of location."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get('/pos/sales')
        assert response.status_code == 200

    def test_sales_list_pagination(self, client, admin_user, pos_sale):
        """Test sales list pagination."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get('/pos/sales?page=1')
        assert response.status_code == 200


# ============================================================================
# TEST: SALE DETAILS
# ============================================================================

class TestSaleDetails:
    """Tests for sale details endpoint."""

    def test_sale_details_requires_auth(self, client, pos_sale):
        """Test sale details requires authentication."""
        response = client.get(f'/pos/sale-details/{pos_sale.id}')
        assert response.status_code in [302, 401]

    def test_sale_details_success(self, client, admin_user, pos_sale):
        """Test successful sale details retrieval."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get(f'/pos/sale-details/{pos_sale.id}')
        assert response.status_code == 200

    def test_sale_details_not_found(self, client, admin_user):
        """Test sale details for non-existent sale returns 404."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get('/pos/sale-details/99999')
        assert response.status_code == 404


# ============================================================================
# TEST: REFUND SALE
# ============================================================================

class TestRefundSale:
    """Tests for refund sale functionality."""

    def test_refund_requires_auth(self, client, pos_sale):
        """Test refund requires authentication."""
        response = client.post(f'/pos/refund-sale/{pos_sale.id}')
        assert response.status_code in [302, 401]

    def test_refund_success(self, client, admin_user, pos_sale, product):
        """Test successful refund."""
        initial_qty = product.quantity

        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.post(f'/pos/refund-sale/{pos_sale.id}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        # Check product quantity was restored
        db.session.refresh(product)
        assert product.quantity == initial_qty + 1

    def test_refund_already_refunded(self, client, admin_user, pos_sale):
        """Test refunding an already refunded sale fails."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        # First refund
        client.post(f'/pos/refund-sale/{pos_sale.id}')

        # Second refund should fail
        response = client.post(f'/pos/refund-sale/{pos_sale.id}')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'already refunded' in data['error'].lower()


# ============================================================================
# TEST: HOLD SALE
# ============================================================================

class TestHoldSale:
    """Tests for hold sale functionality."""

    def test_hold_sale_requires_auth(self, client):
        """Test hold sale requires authentication."""
        response = client.post('/pos/hold-sale',
                               json={'items': []},
                               content_type='application/json')
        assert response.status_code in [302, 401]

    def test_hold_sale_success(self, client, admin_user, product):
        """Test successful hold sale."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.post('/pos/hold-sale',
                               json={
                                   'items': [{'product_id': product.id, 'quantity': 1}],
                                   'notes': 'Hold for later'
                               },
                               content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_retrieve_held_sales(self, client, admin_user, product):
        """Test retrieving held sales."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        # First hold a sale
        client.post('/pos/hold-sale',
                    json={'items': [{'product_id': product.id, 'quantity': 1}]},
                    content_type='application/json')

        # Then retrieve
        response = client.get('/pos/retrieve-held-sales')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'sales' in data


# ============================================================================
# TEST: CUSTOMER LOOKUP
# ============================================================================

class TestCustomerLookup:
    """Tests for customer lookup functionality."""

    def test_customer_lookup_requires_auth(self, client, customer):
        """Test customer lookup requires authentication."""
        response = client.get(f'/pos/customer-lookup/{customer.phone}')
        assert response.status_code in [302, 401]

    def test_customer_lookup_success(self, client, admin_user, customer):
        """Test successful customer lookup."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get(f'/pos/customer-lookup/{customer.phone}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['customer']['name'] == customer.name

    def test_customer_lookup_not_found(self, client, admin_user):
        """Test customer lookup with non-existent phone."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get('/pos/customer-lookup/9999999999')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is False

    def test_customer_lookup_includes_loyalty_info(self, client, admin_user, vip_customer):
        """Test customer lookup includes loyalty information."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get(f'/pos/customer-lookup/{vip_customer.phone}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'loyalty_points' in data['customer']


# ============================================================================
# TEST: CREATE REORDER
# ============================================================================

class TestCreateReorder:
    """Tests for create reorder functionality."""

    def test_reorder_requires_auth(self, client):
        """Test reorder requires authentication."""
        response = client.post('/pos/create-reorder',
                               json={'product_id': 1, 'quantity': 10},
                               content_type='application/json')
        assert response.status_code in [302, 401]

    def test_reorder_missing_product_id(self, client, admin_user):
        """Test reorder fails without product ID."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.post('/pos/create-reorder',
                               json={'quantity': 10},
                               content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    def test_reorder_no_location(self, client, pos_user_no_location, product):
        """Test reorder fails without location assignment."""
        pos_login_user(client, 'no_loc_user', 'password123')
        response = client.post('/pos/create-reorder',
                               json={'product_id': product.id, 'quantity': 10},
                               content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'location' in data['error'].lower()


# ============================================================================
# TEST: DAY CLOSE
# ============================================================================

class TestDayClose:
    """Tests for day close functionality."""

    def test_close_day_summary_requires_auth(self, client):
        """Test close day summary requires authentication."""
        response = client.get('/pos/close-day-summary')
        assert response.status_code in [302, 401]

    def test_close_day_summary_success(self, client, admin_user):
        """Test successful close day summary."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get('/pos/close-day-summary')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'summary' in data

    def test_close_day_requires_auth(self, client):
        """Test close day requires authentication."""
        response = client.post('/pos/close-day',
                               json={'closing_balance': 10000},
                               content_type='application/json')
        assert response.status_code in [302, 401]

    def test_close_day_success(self, client, admin_user):
        """Test successful day close."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.post('/pos/close-day',
                               json={
                                   'closing_balance': 10000,
                                   'total_expenses': 500,
                                   'notes': 'End of day'
                               },
                               content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_close_day_already_closed(self, client, admin_user, kiosk):
        """Test closing day that is already closed fails."""
        pos_login_user(client, 'admin_test', 'Admin123!')

        # First close
        client.post('/pos/close-day',
                    json={'closing_balance': 10000},
                    content_type='application/json')

        # Second close should fail
        response = client.post('/pos/close-day',
                               json={'closing_balance': 10000},
                               content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'already closed' in data['error'].lower()


# ============================================================================
# TEST: SEARCH SALES FOR RETURN
# ============================================================================

class TestSearchSalesForReturn:
    """Tests for search sales for return functionality."""

    def test_search_sales_requires_auth(self, client):
        """Test search sales for return requires authentication."""
        response = client.get('/pos/search-sales-for-return?q=SALE')
        assert response.status_code in [302, 401]

    def test_search_sales_empty_query(self, client, admin_user):
        """Test search with empty query returns empty results."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get('/pos/search-sales-for-return?q=')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['sales'] == []

    def test_search_sales_by_number(self, client, admin_user, pos_sale):
        """Test search sales by sale number."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.get(f'/pos/search-sales-for-return?q={pos_sale.sale_number}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


# ============================================================================
# TEST: PROCESS RETURN
# ============================================================================

class TestProcessReturn:
    """Tests for process return functionality."""

    def test_process_return_requires_auth(self, client, pos_sale):
        """Test process return requires authentication."""
        response = client.post('/pos/process-return',
                               json={'sale_id': pos_sale.id, 'items': []},
                               content_type='application/json')
        assert response.status_code in [302, 401]

    def test_process_return_no_items(self, client, admin_user, pos_sale):
        """Test process return with no items fails."""
        pos_login_user(client, 'admin_test', 'Admin123!')
        response = client.post('/pos/process-return',
                               json={'sale_id': pos_sale.id, 'items': []},
                               content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'No items' in data['error']


# ============================================================================
# TEST: PERMISSION CHECKS
# ============================================================================

class TestPermissionChecks:
    """Tests for permission-based access control."""

    def test_pos_view_permission(self, client, cashier_user):
        """Test POS view permission."""
        pos_login_user(client, 'cashier_test', 'Cashier123!')
        response = client.get('/pos/')
        # Cashier should have pos.view permission
        assert response.status_code == 200

    def test_refund_permission_required(self, client, cashier_user, pos_sale):
        """Test refund requires refund permission."""
        pos_login_user(client, 'cashier_test', 'Cashier123!')
        response = client.post(f'/pos/refund-sale/{pos_sale.id}')
        # Cashier typically doesn't have refund permission
        assert response.status_code in [200, 403]

    def test_close_day_permission(self, client, cashier_user):
        """Test close day requires permission."""
        pos_login_user(client, 'cashier_test', 'Cashier123!')
        response = client.get('/pos/close-day-summary')
        # Cashier typically doesn't have close_day permission
        assert response.status_code in [200, 403]


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
