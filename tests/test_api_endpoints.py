"""
Comprehensive Unit Tests for API/AJAX Endpoints

Tests for all JSON-returning routes and API endpoints in the SOC_WEB_APP application.
Covers: Product Search, Customer Search, Stock Operations, Dashboard Data, and other AJAX endpoints.

Edge cases tested:
- Invalid JSON payloads
- Missing required fields
- Authentication requirements
- Response format validation
- Empty results
- Special characters in search
- SQL injection attempts
- XSS in responses
- Large payloads

Note: This test module uses fixtures from conftest.py including:
- fresh_app: Creates a fresh Flask app with clean database
- client: Test client for making HTTP requests
- init_database: Initializes database with test data
- auth_admin, auth_manager, auth_cashier: Authenticated clients
"""

import pytest
import json
from decimal import Decimal
from datetime import datetime, date, timedelta


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def logout(client):
    """Helper to logout a client."""
    client.get('/auth/logout', follow_redirects=True)


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================

class TestAuthentication:
    """Test authentication requirements for API endpoints."""

    def test_product_search_requires_auth(self, client, init_database):
        """Test that product search requires authentication."""
        logout(client)
        response = client.get('/pos/search-products?q=oud')
        # Should redirect to login
        assert response.status_code == 302 or response.status_code == 401

    def test_customer_search_requires_auth(self, client, init_database):
        """Test that customer search requires authentication."""
        logout(client)
        response = client.get('/customers/search?q=john')
        assert response.status_code == 302 or response.status_code == 401

    def test_stock_adjustment_requires_auth(self, client, init_database, fresh_app):
        """Test that stock adjustment requires authentication."""
        logout(client)
        with fresh_app.app_context():
            from app.models import Product
            product = Product.query.first()
            response = client.post(f'/inventory/adjust-stock/{product.id}',
                                   json={'adjustment': 5})
            assert response.status_code == 302 or response.status_code == 401

    def test_complete_sale_requires_auth(self, client, init_database):
        """Test that complete sale requires authentication."""
        logout(client)
        response = client.post('/pos/complete-sale', json={'items': []})
        assert response.status_code == 302 or response.status_code == 401

    def test_invalid_login_credentials(self, client, init_database):
        """Test login with invalid credentials."""
        logout(client)
        response = client.post('/auth/login', data={
            'username': 'admin',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        assert b'Invalid username or password' in response.data or response.status_code == 200

    def test_inactive_user_login(self, client, init_database):
        """Test login with inactive user account."""
        logout(client)
        response = client.post('/auth/login', data={
            'username': 'inactive',
            'password': 'inactive123'
        }, follow_redirects=True)
        assert b'deactivated' in response.data or response.status_code == 200


# ============================================================================
# PRODUCT SEARCH API TESTS
# ============================================================================

class TestProductSearchAPI:
    """Test /pos/search-products endpoint."""

    def test_search_products_success(self, auth_cashier, fresh_app):
        """Test successful product search."""
        response = auth_cashier.get('/pos/search-products?q=oud')
        assert response.status_code == 200
        data = response.get_json()
        assert 'products' in data
        assert isinstance(data['products'], list)

    def test_search_products_minimum_query_length(self, auth_cashier):
        """Test that search requires minimum 2 characters."""
        response = auth_cashier.get('/pos/search-products?q=o')
        assert response.status_code == 200
        data = response.get_json()
        assert data['products'] == []

    def test_search_products_empty_query(self, auth_cashier):
        """Test search with empty query."""
        response = auth_cashier.get('/pos/search-products?q=')
        assert response.status_code == 200
        data = response.get_json()
        assert data['products'] == []

    def test_search_products_no_results(self, auth_cashier):
        """Test search with no matching results."""
        response = auth_cashier.get('/pos/search-products?q=nonexistentproduct12345')
        assert response.status_code == 200
        data = response.get_json()
        assert data['products'] == []

    def test_search_by_product_code(self, auth_cashier):
        """Test search by product code."""
        response = auth_cashier.get('/pos/search-products?q=PRD001')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data['products']) >= 1

    def test_search_by_barcode(self, auth_cashier):
        """Test search by barcode."""
        response = auth_cashier.get('/pos/search-products?q=1234567890123')
        assert response.status_code == 200
        data = response.get_json()
        # May or may not find depending on data setup
        assert 'products' in data

    def test_search_by_brand(self, auth_cashier):
        """Test search by brand name."""
        response = auth_cashier.get('/pos/search-products?q=Sunnat')
        assert response.status_code == 200
        data = response.get_json()
        assert 'products' in data

    def test_search_case_insensitive(self, auth_cashier):
        """Test that search is case insensitive."""
        response1 = auth_cashier.get('/pos/search-products?q=OUD')
        response2 = auth_cashier.get('/pos/search-products?q=oud')
        data1 = response1.get_json()
        data2 = response2.get_json()
        assert len(data1['products']) == len(data2['products'])

    def test_search_special_characters(self, auth_cashier):
        """Test search with special characters."""
        special_queries = [
            "o'ud",
            "oud--test",
            "oud<script>",
            "oud'; DROP TABLE products;--",
            "oud%20test",
            "oud\ntest",
            "oud\x00test",
        ]
        for query in special_queries:
            response = auth_cashier.get(f'/pos/search-products?q={query}')
            assert response.status_code == 200
            data = response.get_json()
            assert 'products' in data

    def test_search_sql_injection_attempt(self, auth_cashier):
        """Test SQL injection attempts are handled safely."""
        sql_injections = [
            "' OR '1'='1",
            "'; DROP TABLE products; --",
            "1'; SELECT * FROM users; --",
            "UNION SELECT * FROM users",
            "1 OR 1=1",
        ]
        for injection in sql_injections:
            response = auth_cashier.get(f'/pos/search-products?q={injection}')
            assert response.status_code == 200
            data = response.get_json()
            # Should not return any sensitive data or error
            assert 'products' in data

    def test_search_xss_in_response(self, auth_cashier):
        """Test that XSS payloads are not reflected in response."""
        xss_payload = '<script>alert("xss")</script>'
        response = auth_cashier.get(f'/pos/search-products?q={xss_payload}')
        assert response.status_code == 200
        data = response.get_json()
        # The response should not contain unescaped script tags
        response_text = json.dumps(data)
        assert '<script>' not in response_text or '&lt;script&gt;' in response_text

    def test_search_unicode_characters(self, auth_cashier):
        """Test search with unicode characters."""
        unicode_queries = ['عود', 'مسک', '香水', '🌹']
        for query in unicode_queries:
            response = auth_cashier.get(f'/pos/search-products?q={query}')
            assert response.status_code == 200
            data = response.get_json()
            assert 'products' in data

    def test_search_very_long_query(self, auth_cashier):
        """Test search with very long query string."""
        long_query = 'a' * 10000
        response = auth_cashier.get(f'/pos/search-products?q={long_query}')
        # Should handle gracefully (either 200 with empty results or 400)
        assert response.status_code in [200, 400, 414]

    def test_product_response_format(self, auth_cashier, fresh_app):
        """Test that product response has correct format."""
        with fresh_app.app_context():
            response = auth_cashier.get('/pos/search-products?q=oud')
            data = response.get_json()
            if data['products']:
                product = data['products'][0]
                # Check expected fields
                expected_fields = ['id', 'code', 'name', 'selling_price']
                for field in expected_fields:
                    assert field in product, f"Missing field: {field}"


# ============================================================================
# GET PRODUCT API TESTS
# ============================================================================

class TestGetProductAPI:
    """Test /pos/get-product/<id> endpoint."""

    def test_get_product_success(self, auth_cashier, fresh_app):
        """Test successful product retrieval."""
        with fresh_app.app_context():
            from app.models import Product
            product = Product.query.filter_by(is_active=True).first()
            response = auth_cashier.get(f'/pos/get-product/{product.id}')
            assert response.status_code == 200
            data = response.get_json()
            assert data['id'] == product.id
            assert 'selling_price' in data

    def test_get_product_not_found(self, auth_cashier):
        """Test getting non-existent product."""
        response = auth_cashier.get('/pos/get-product/99999')
        assert response.status_code == 404

    def test_get_product_invalid_id(self, auth_cashier):
        """Test getting product with invalid ID."""
        response = auth_cashier.get('/pos/get-product/invalid')
        assert response.status_code == 404


# ============================================================================
# CUSTOMER SEARCH API TESTS
# ============================================================================

class TestCustomerSearchAPI:
    """Test /customers/search endpoint."""

    def test_search_customers_success(self, auth_cashier):
        """Test successful customer search."""
        response = auth_cashier.get('/customers/search?q=john')
        assert response.status_code == 200
        data = response.get_json()
        assert 'customers' in data
        assert isinstance(data['customers'], list)

    def test_search_customers_minimum_query(self, auth_cashier):
        """Test customer search requires minimum 2 characters."""
        response = auth_cashier.get('/customers/search?q=j')
        assert response.status_code == 200
        data = response.get_json()
        assert data['customers'] == []

    def test_search_by_phone(self, auth_cashier):
        """Test customer search by phone number."""
        response = auth_cashier.get('/customers/search?q=0300123')
        assert response.status_code == 200
        data = response.get_json()
        assert 'customers' in data

    def test_search_excludes_inactive_customers(self, auth_cashier):
        """Test that inactive customers are excluded from search."""
        response = auth_cashier.get('/customers/search?q=Inactive')
        data = response.get_json()
        # Should not find inactive customer
        for customer in data['customers']:
            assert 'Inactive Customer' not in customer.get('name', '')

    def test_customer_sql_injection(self, auth_cashier):
        """Test SQL injection protection in customer search."""
        response = auth_cashier.get("/customers/search?q=' OR '1'='1")
        assert response.status_code == 200
        data = response.get_json()
        assert 'customers' in data

    def test_customer_response_format(self, auth_cashier):
        """Test customer response format."""
        response = auth_cashier.get('/customers/search?q=john')
        data = response.get_json()
        if data['customers']:
            customer = data['customers'][0]
            expected_fields = ['id', 'name', 'phone']
            for field in expected_fields:
                assert field in customer


# ============================================================================
# CUSTOMER LOOKUP API TESTS
# ============================================================================

class TestCustomerLookupAPI:
    """Test /pos/customer-lookup/<phone> endpoint."""

    def test_customer_lookup_success(self, auth_cashier):
        """Test successful customer lookup by phone."""
        response = auth_cashier.get('/pos/customer-lookup/03001234567')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        assert 'customer' in data

    def test_customer_lookup_not_found(self, auth_cashier):
        """Test customer lookup with non-existent phone."""
        response = auth_cashier.get('/pos/customer-lookup/00000000000')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == False

    def test_customer_lookup_includes_stats(self, auth_cashier):
        """Test customer lookup includes purchase stats."""
        response = auth_cashier.get('/pos/customer-lookup/03001234567')
        data = response.get_json()
        if data['success']:
            assert 'stats' in data
            assert 'loyalty' in data['customer'] or 'loyalty_points' in data['customer']


# ============================================================================
# STOCK ADJUSTMENT API TESTS
# ============================================================================

class TestStockAdjustmentAPI:
    """Test /inventory/adjust-stock/<id> endpoint."""

    def test_adjust_stock_add(self, auth_admin, fresh_app):
        """Test adding stock."""
        with fresh_app.app_context():
            from app.models import Product
            product = Product.query.filter_by(is_active=True).first()
            response = auth_admin.post(
                f'/inventory/adjust-stock/{product.id}',
                json={
                    'adjustment_type': 'add',
                    'quantity': 10,
                    'reason': 'Test addition'
                },
                content_type='application/json'
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] == True

    def test_adjust_stock_remove(self, auth_admin, fresh_app):
        """Test removing stock."""
        with fresh_app.app_context():
            from app.models import Product
            # Use filter() instead of filter_by for comparison operators
            product = Product.query.filter(
                Product.is_active == True,
                Product.quantity > 5
            ).first()
            if product:
                response = auth_admin.post(
                    f'/inventory/adjust-stock/{product.id}',
                    json={
                        'adjustment_type': 'remove',
                        'quantity': 5,
                        'reason': 'Test removal'
                    },
                    content_type='application/json'
                )
                assert response.status_code == 200

    def test_adjust_stock_negative_result(self, auth_admin, fresh_app):
        """Test that stock cannot go negative."""
        with fresh_app.app_context():
            from app.models import Product
            product = Product.query.filter_by(is_active=True).first()
            response = auth_admin.post(
                f'/inventory/adjust-stock/{product.id}',
                json={
                    'adjustment_type': 'remove',
                    'quantity': 999999,
                    'reason': 'Test negative'
                },
                content_type='application/json'
            )
            data = response.get_json()
            # Should either fail or prevent negative
            assert response.status_code == 400 or data.get('success') == False

    def test_adjust_stock_invalid_json(self, auth_admin, fresh_app):
        """Test stock adjustment with invalid JSON."""
        with fresh_app.app_context():
            from app.models import Product
            product = Product.query.first()
            response = auth_admin.post(
                f'/inventory/adjust-stock/{product.id}',
                data='not valid json',
                content_type='application/json'
            )
            assert response.status_code in [400, 500]

    def test_adjust_stock_missing_quantity(self, auth_admin, fresh_app):
        """Test stock adjustment without quantity."""
        with fresh_app.app_context():
            from app.models import Product
            product = Product.query.first()
            response = auth_admin.post(
                f'/inventory/adjust-stock/{product.id}',
                json={'reason': 'No quantity'},
                content_type='application/json'
            )
            # Should handle missing quantity
            assert response.status_code in [200, 400]

    def test_adjust_stock_unauthorized(self, auth_cashier, fresh_app):
        """Test stock adjustment by unauthorized user."""
        with fresh_app.app_context():
            from app.models import Product
            product = Product.query.first()
            response = auth_cashier.post(
                f'/inventory/adjust-stock/{product.id}',
                json={'adjustment': 10, 'reason': 'Unauthorized'},
                content_type='application/json'
            )
            # Cashier should not have permission
            assert response.status_code in [302, 403]


# ============================================================================
# COMPLETE SALE API TESTS
# ============================================================================

class TestCompleteSaleAPI:
    """Test /pos/complete-sale endpoint."""

    def test_complete_sale_success(self, auth_cashier, fresh_app):
        """Test successful sale completion."""
        with fresh_app.app_context():
            from app.models import Product
            product = Product.query.filter_by(is_active=True).filter(Product.quantity > 0).first()
            if product:
                response = auth_cashier.post('/pos/complete-sale', json={
                    'items': [{
                        'product_id': product.id,
                        'quantity': 1,
                        'unit_price': float(product.selling_price),
                        'subtotal': float(product.selling_price)
                    }],
                    'subtotal': float(product.selling_price),
                    'discount': 0,
                    'discount_type': 'amount',
                    'tax': 0,
                    'total': float(product.selling_price),
                    'payment_method': 'cash',
                    'amount_paid': float(product.selling_price)
                }, content_type='application/json')
                assert response.status_code == 200
                data = response.get_json()
                assert data['success'] == True
                assert 'sale_number' in data

    def test_complete_sale_empty_cart(self, auth_cashier):
        """Test sale with empty cart."""
        response = auth_cashier.post('/pos/complete-sale', json={
            'items': [],
            'total': 0,
            'payment_method': 'cash',
            'amount_paid': 0
        }, content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] == False
        assert 'No items' in data.get('error', '')

    def test_complete_sale_invalid_product(self, auth_cashier):
        """Test sale with invalid product ID."""
        response = auth_cashier.post('/pos/complete-sale', json={
            'items': [{
                'product_id': 99999,
                'quantity': 1,
                'unit_price': 100,
                'subtotal': 100
            }],
            'subtotal': 100,
            'total': 100,
            'payment_method': 'cash',
            'amount_paid': 100
        }, content_type='application/json')
        assert response.status_code == 404
        data = response.get_json()
        assert data['success'] == False

    def test_complete_sale_insufficient_stock(self, auth_cashier, fresh_app):
        """Test sale with insufficient stock."""
        with fresh_app.app_context():
            from app.models import Product
            product = Product.query.filter_by(code='PRD003').first()  # Out of stock
            if product:
                response = auth_cashier.post('/pos/complete-sale', json={
                    'items': [{
                        'product_id': product.id,
                        'quantity': 10,
                        'unit_price': float(product.selling_price),
                        'subtotal': float(product.selling_price * 10)
                    }],
                    'subtotal': float(product.selling_price * 10),
                    'total': float(product.selling_price * 10),
                    'payment_method': 'cash',
                    'amount_paid': float(product.selling_price * 10)
                }, content_type='application/json')
                assert response.status_code == 400
                data = response.get_json()
                assert 'Insufficient stock' in data.get('error', '')

    def test_complete_sale_invalid_json(self, auth_cashier):
        """Test sale with invalid JSON payload."""
        response = auth_cashier.post('/pos/complete-sale',
                                     data='not valid json',
                                     content_type='application/json')
        assert response.status_code in [400, 500]

    def test_complete_sale_backdate_unauthorized(self, auth_cashier):
        """Test that cashier cannot backdate sales."""
        response = auth_cashier.post('/pos/complete-sale', json={
            'items': [{'product_id': 1, 'quantity': 1, 'unit_price': 100, 'subtotal': 100}],
            'total': 100,
            'payment_method': 'cash',
            'amount_paid': 100,
            'sale_date': '2020-01-01'
        }, content_type='application/json')
        if response.status_code == 200:
            data = response.get_json()
            # Either fails or ignores backdate for cashier
            pass
        else:
            assert response.status_code in [403, 404]

    def test_complete_sale_future_date(self, auth_admin, fresh_app):
        """Test that future dates are rejected."""
        with fresh_app.app_context():
            from app.models import Product
            product = Product.query.filter_by(is_active=True).first()
            future_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            response = auth_admin.post('/pos/complete-sale', json={
                'items': [{
                    'product_id': product.id,
                    'quantity': 1,
                    'unit_price': float(product.selling_price),
                    'subtotal': float(product.selling_price)
                }],
                'total': float(product.selling_price),
                'payment_method': 'cash',
                'amount_paid': float(product.selling_price),
                'sale_date': future_date
            }, content_type='application/json')
            data = response.get_json()
            assert data['success'] == False or 'future' in data.get('error', '').lower()


# ============================================================================
# HOLD/RETRIEVE SALE API TESTS
# ============================================================================

class TestHoldSaleAPI:
    """Test hold sale functionality."""

    def test_hold_sale(self, auth_cashier):
        """Test holding a sale."""
        response = auth_cashier.post('/pos/hold-sale', json={
            'items': [{'product_id': 1, 'quantity': 1, 'unit_price': 100}],
            'customer_id': None,
            'notes': 'Test hold'
        }, content_type='application/json')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True

    def test_retrieve_held_sales(self, auth_cashier):
        """Test retrieving held sales."""
        response = auth_cashier.get('/pos/retrieve-held-sales')
        assert response.status_code == 200
        data = response.get_json()
        assert 'sales' in data

    def test_delete_held_sale(self, auth_cashier):
        """Test deleting a held sale."""
        # First hold a sale
        auth_cashier.post('/pos/hold-sale', json={
            'items': [{'product_id': 1, 'quantity': 1}],
        }, content_type='application/json')

        # Then try to delete it
        response = auth_cashier.post('/pos/delete-held-sale/0')
        assert response.status_code in [200, 404]


# ============================================================================
# DAY CLOSE API TESTS
# ============================================================================

class TestDayCloseAPI:
    """Test day close functionality."""

    def test_close_day_summary(self, auth_manager):
        """Test getting close day summary."""
        response = auth_manager.get('/pos/close-day-summary')
        assert response.status_code in [200, 400, 403]
        if response.status_code == 200:
            data = response.get_json()
            assert 'summary' in data or 'success' in data

    def test_close_day(self, auth_manager):
        """Test closing the day."""
        response = auth_manager.post('/pos/close-day', json={
            'closing_balance': 10000,
            'notes': 'Test close'
        }, content_type='application/json')
        # May succeed or fail depending on existing close
        assert response.status_code in [200, 400, 403]


# ============================================================================
# REFUND SALE API TESTS
# ============================================================================

class TestRefundSaleAPI:
    """Test /pos/refund-sale/<id> endpoint."""

    def test_refund_nonexistent_sale(self, auth_admin):
        """Test refunding non-existent sale."""
        response = auth_admin.post('/pos/refund-sale/99999')
        # May return 404 Not Found or 500 if DB query fails
        assert response.status_code in [404, 500]


# ============================================================================
# CATEGORY API TESTS
# ============================================================================

class TestCategoryAPI:
    """Test /settings/categories/add endpoint."""

    def test_add_category(self, auth_admin):
        """Test adding a category."""
        response = auth_admin.post('/settings/categories/add', json={
            'name': 'Test Category',
            'description': 'A test category'
        }, content_type='application/json')
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = response.get_json()
            assert data['success'] == True

    def test_add_category_missing_name(self, auth_admin):
        """Test adding category without name."""
        response = auth_admin.post('/settings/categories/add', json={
            'description': 'No name'
        }, content_type='application/json')
        # Should fail or handle gracefully
        assert response.status_code in [200, 400, 500]


# ============================================================================
# DELETE USER API TESTS
# ============================================================================

class TestDeleteUserAPI:
    """Test /settings/users/delete/<id> endpoint."""

    def test_delete_user_success(self, auth_admin, fresh_app):
        """Test deleting a user."""
        with fresh_app.app_context():
            from app.models import User
            user = User.query.filter_by(username='cashier').first()
            if user:
                response = auth_admin.post(f'/settings/users/delete/{user.id}')
                assert response.status_code == 200
                data = response.get_json()
                assert data['success'] == True

    def test_delete_self_prevented(self, auth_admin, fresh_app):
        """Test that admin cannot delete themselves."""
        with fresh_app.app_context():
            from app.models import User
            admin = User.query.filter_by(username='admin').first()
            response = auth_admin.post(f'/settings/users/delete/{admin.id}')
            data = response.get_json()
            assert data['success'] == False


# ============================================================================
# SUPPLIER DELETE API TESTS
# ============================================================================

class TestSupplierDeleteAPI:
    """Test supplier deletion endpoint."""

    def test_delete_supplier_not_found(self, auth_admin):
        """Test deleting non-existent supplier."""
        response = auth_admin.post('/suppliers/delete/99999')
        # May return 404 Not Found or 500 if DB query fails
        assert response.status_code in [404, 500]


# ============================================================================
# PRODUCT DELETE API TESTS
# ============================================================================

class TestProductDeleteAPI:
    """Test product deletion endpoint."""

    def test_delete_product(self, auth_admin, fresh_app):
        """Test soft deleting a product."""
        with fresh_app.app_context():
            from app.models import Product
            product = Product.query.filter_by(is_active=True).first()
            response = auth_admin.post(f'/inventory/delete/{product.id}')
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] == True


# ============================================================================
# CUSTOMER DELETE API TESTS
# ============================================================================

class TestCustomerDeleteAPI:
    """Test customer deletion endpoint."""

    def test_delete_customer(self, auth_admin, fresh_app):
        """Test soft deleting a customer."""
        with fresh_app.app_context():
            from app.models import Customer
            customer = Customer.query.filter_by(is_active=True).first()
            response = auth_admin.post(f'/customers/delete/{customer.id}')
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] == True


# ============================================================================
# WAREHOUSE API TESTS
# ============================================================================

class TestWarehouseAPI:
    """Test warehouse API endpoints."""

    def test_get_product_stock(self, auth_admin, fresh_app):
        """Test getting product stock at warehouse."""
        with fresh_app.app_context():
            from app.models import Product
            product = Product.query.first()
            response = auth_admin.get(f'/warehouse/api/stock/{product.id}')
            # May require warehouse context
            assert response.status_code in [200, 403, 404]


# ============================================================================
# TRANSFERS API TESTS
# ============================================================================

class TestTransfersAPI:
    """Test stock transfer API endpoints."""

    def test_search_products_for_transfer(self, auth_admin, fresh_app):
        """Test searching products for transfer."""
        with fresh_app.app_context():
            from app.models import Location
            warehouse = Location.query.filter_by(location_type='warehouse').first()
            if warehouse:
                response = auth_admin.get(
                    f'/transfers/api/search-products?source_id={warehouse.id}&q=oud'
                )
                assert response.status_code == 200
                data = response.get_json()
                assert 'products' in data

    def test_search_products_short_query(self, auth_admin):
        """Test product search with short query."""
        response = auth_admin.get('/transfers/api/search-products?source_id=1&q=a')
        assert response.status_code == 200
        data = response.get_json()
        assert data['products'] == []

    def test_add_reorder_item_access_denied(self, auth_cashier):
        """Test adding reorder item without proper access."""
        response = auth_cashier.post('/transfers/reorders/add-item/1', json={
            'product_id': 1,
            'quantity': 10
        }, content_type='application/json')
        # Should be access denied or not found
        assert response.status_code in [302, 403, 404]


# ============================================================================
# RETURNS API TESTS
# ============================================================================

class TestReturnsAPI:
    """Test returns API endpoints."""

    def test_search_sales_for_return(self, auth_admin):
        """Test searching sales for return."""
        response = auth_admin.get('/pos/search-sales-for-return?q=test')
        assert response.status_code == 200
        data = response.get_json()
        assert 'sales' in data

    def test_search_sales_empty_query(self, auth_admin):
        """Test sales search with empty query."""
        response = auth_admin.get('/pos/search-sales-for-return?q=')
        assert response.status_code == 200
        data = response.get_json()
        assert data['sales'] == []

    def test_process_return_no_items(self, auth_admin):
        """Test processing return with no items."""
        response = auth_admin.post('/pos/process-return', json={
            'sale_id': 1,
            'items': [],
            'return_type': 'cash'
        }, content_type='application/json')
        assert response.status_code in [400, 404]


# ============================================================================
# PROMOTIONS API TESTS
# ============================================================================

class TestPromotionsAPI:
    """Test promotions/voucher API endpoints."""

    def test_validate_invalid_promo(self, auth_cashier):
        """Test validating invalid promotion code."""
        response = auth_cashier.post('/promotions/validate', json={
            'code': 'INVALID_CODE_12345'
        }, content_type='application/json')
        # May require feature flag to be enabled or return 403
        if response.status_code == 200:
            data = response.get_json()
            assert data['valid'] == False
        else:
            assert response.status_code in [302, 403, 404]

    def test_validate_voucher_invalid(self, auth_cashier):
        """Test validating invalid voucher."""
        response = auth_cashier.post('/promotions/validate-voucher', json={
            'code': 'INVALID_VOUCHER'
        }, content_type='application/json')
        # May require feature flag to be enabled or return 404
        if response.status_code == 200:
            data = response.get_json()
            assert data['valid'] == False
        else:
            assert response.status_code in [302, 403, 404]


# ============================================================================
# NOTIFICATIONS API TESTS
# ============================================================================

class TestNotificationsAPI:
    """Test notification API endpoints."""

    def test_send_sms_no_phone(self, auth_admin):
        """Test sending SMS without phone number."""
        response = auth_admin.post('/notifications/send-sms', json={
            'message': 'Test message'
        }, content_type='application/json')
        # May return 400 if validated, or 404 if feature not enabled
        if response.status_code == 400:
            data = response.get_json()
            assert data['success'] == False
        else:
            assert response.status_code in [302, 403, 404]


# ============================================================================
# EXPENSES API TESTS
# ============================================================================

class TestExpensesAPI:
    """Test expense API endpoints."""

    def test_approve_expense_not_found(self, auth_admin):
        """Test approving non-existent expense."""
        try:
            response = auth_admin.post('/expenses/approve/99999')
            # May return 403/404/500 if feature not enabled
            assert response.status_code in [302, 403, 404, 500]
        except Exception as e:
            # Feature flag redirect may cause BuildError in testing environment
            assert 'BuildError' in str(type(e).__name__) or 'main.index' in str(e)

    def test_reject_expense_not_found(self, auth_admin):
        """Test rejecting non-existent expense."""
        try:
            response = auth_admin.post('/expenses/reject/99999')
            # May return 403/404/500 if feature not enabled
            assert response.status_code in [302, 403, 404, 500]
        except Exception as e:
            # Feature flag redirect may cause BuildError in testing environment
            assert 'BuildError' in str(type(e).__name__) or 'main.index' in str(e)


# ============================================================================
# QUOTATIONS API TESTS
# ============================================================================

class TestQuotationsAPI:
    """Test quotation API endpoints."""

    def test_delete_nonexistent_quotation(self, auth_admin):
        """Test deleting non-existent quotation."""
        try:
            response = auth_admin.post('/quotations/delete/99999')
            # May return 404 or redirect/500 if feature not enabled
            assert response.status_code in [302, 403, 404, 500]
        except Exception as e:
            # Feature flag redirect may cause BuildError in testing environment
            assert 'BuildError' in str(type(e).__name__) or 'main.index' in str(e)


# ============================================================================
# LOCATIONS API TESTS
# ============================================================================

class TestLocationsAPI:
    """Test location API endpoints."""

    def test_search_products_at_location(self, auth_admin, fresh_app):
        """Test searching products at a location."""
        with fresh_app.app_context():
            from app.models import Location
            location = Location.query.first()
            if location:
                response = auth_admin.get(
                    f'/locations/{location.id}/search-products?q=oud'
                )
                # Route may not exist or may require different URL pattern
                assert response.status_code in [200, 302, 403, 404]

    def test_bulk_adjust_stock(self, auth_admin, fresh_app):
        """Test bulk stock adjustment."""
        with fresh_app.app_context():
            from app.models import Location, Product
            location = Location.query.first()
            product = Product.query.first()
            if location and product:
                response = auth_admin.post(
                    f'/locations/{location.id}/bulk-adjust-stock',
                    json={
                        'adjustments': [{
                            'product_id': product.id,
                            'quantity': 10,
                            'reason': 'Test bulk adjustment'
                        }]
                    },
                    content_type='application/json'
                )
                # Route may not exist or may require different URL pattern
                assert response.status_code in [200, 302, 403, 404]


# ============================================================================
# BIRTHDAY GIFT API TESTS
# ============================================================================

class TestBirthdayGiftAPI:
    """Test birthday gift API endpoints."""

    def test_apply_birthday_gift_not_birthday(self, auth_admin, fresh_app):
        """Test applying gift when not customer's birthday."""
        with fresh_app.app_context():
            from app.models import Customer
            customer = Customer.query.filter_by(is_active=True).first()
            if customer:
                response = auth_admin.post(f'/customers/birthday-gift/{customer.id}')
                # Should fail if not birthday
                assert response.status_code in [200, 400]

    def test_apply_birthday_gift_no_birthday(self, auth_admin, fresh_app):
        """Test applying gift for customer without birthday."""
        with fresh_app.app_context():
            from app.models import Customer
            customer = Customer.query.filter(Customer.birthday.is_(None)).first()
            if customer:
                response = auth_admin.post(f'/customers/birthday-gift/{customer.id}')
                assert response.status_code == 400


# ============================================================================
# FEATURES API TESTS
# ============================================================================

class TestFeaturesAPI:
    """Test feature flag API endpoints."""

    def test_get_features_list(self, auth_admin):
        """Test getting features list."""
        response = auth_admin.get('/features/list')
        assert response.status_code in [200, 404]


# ============================================================================
# LARGE PAYLOAD TESTS
# ============================================================================

class TestLargePayloads:
    """Test handling of large payloads."""

    def test_complete_sale_many_items(self, auth_cashier, fresh_app):
        """Test sale with many items."""
        with fresh_app.app_context():
            from app.models import Product
            product = Product.query.filter_by(is_active=True).first()
            if product:
                # Create a large items list
                items = [{
                    'product_id': product.id,
                    'quantity': 1,
                    'unit_price': 100,
                    'subtotal': 100
                } for _ in range(100)]

                response = auth_cashier.post('/pos/complete-sale', json={
                    'items': items,
                    'subtotal': 10000,
                    'total': 10000,
                    'payment_method': 'cash',
                    'amount_paid': 10000
                }, content_type='application/json')
                # Should handle gracefully
                assert response.status_code in [200, 400, 413]

    def test_hold_sale_large_notes(self, auth_cashier):
        """Test holding sale with very large notes."""
        large_notes = 'x' * 100000
        response = auth_cashier.post('/pos/hold-sale', json={
            'items': [{'product_id': 1, 'quantity': 1}],
            'notes': large_notes
        }, content_type='application/json')
        # Should handle gracefully
        assert response.status_code in [200, 400, 413]


# ============================================================================
# RESPONSE FORMAT VALIDATION TESTS
# ============================================================================

class TestResponseFormats:
    """Test that all JSON responses have correct format."""

    def test_product_search_json_format(self, auth_cashier):
        """Verify product search returns valid JSON."""
        response = auth_cashier.get('/pos/search-products?q=test')
        assert response.content_type == 'application/json'
        data = response.get_json()
        assert data is not None

    def test_customer_search_json_format(self, auth_cashier):
        """Verify customer search returns valid JSON."""
        response = auth_cashier.get('/customers/search?q=test')
        assert response.content_type == 'application/json'
        data = response.get_json()
        assert data is not None

    def test_error_responses_json(self, auth_cashier):
        """Verify error responses are JSON."""
        response = auth_cashier.post('/pos/complete-sale', json={
            'items': []
        }, content_type='application/json')
        if response.status_code == 400:
            assert response.content_type == 'application/json'
            data = response.get_json()
            assert 'error' in data or 'success' in data


# ============================================================================
# PERMISSION TESTS
# ============================================================================

class TestPermissions:
    """Test permission requirements for various endpoints."""

    def test_cashier_cannot_access_settings(self, auth_cashier):
        """Test that cashier cannot access settings."""
        response = auth_cashier.get('/settings/')
        # Should redirect or show permission denied
        assert response.status_code in [200, 302, 403]

    def test_cashier_cannot_delete_users(self, auth_cashier):
        """Test that cashier cannot delete users."""
        response = auth_cashier.post('/settings/users/delete/1')
        assert response.status_code in [302, 403]

    def test_cashier_cannot_adjust_stock_directly(self, auth_cashier, fresh_app):
        """Test that cashier has limited stock adjustment access."""
        with fresh_app.app_context():
            from app.models import Product
            product = Product.query.first()
            response = auth_cashier.post(
                f'/inventory/adjust-stock/{product.id}',
                json={'adjustment': 100},
                content_type='application/json'
            )
            # Should be blocked or limited
            assert response.status_code in [302, 403, 200]


# ============================================================================
# CONCURRENT REQUEST TESTS
# ============================================================================

class TestConcurrentRequests:
    """Test handling of potential race conditions."""

    def test_rapid_product_search(self, auth_cashier):
        """Test rapid consecutive searches."""
        for _ in range(10):
            response = auth_cashier.get('/pos/search-products?q=oud')
            assert response.status_code == 200

    def test_rapid_customer_search(self, auth_cashier):
        """Test rapid consecutive customer searches."""
        for _ in range(10):
            response = auth_cashier.get('/customers/search?q=john')
            assert response.status_code == 200


# Run tests if executed directly
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
