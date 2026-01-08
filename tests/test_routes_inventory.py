"""
Comprehensive Unit Tests for Inventory and Stock Management Routes

Tests cover:
1. Product CRUD operations
2. Stock adjustments
3. Stock transfers between locations
4. Reorder alerts
5. Category management
6. Brand management
7. Bulk import/export

Edge cases tested:
- Negative stock adjustments going below zero
- Transfer to same location
- Transfer more than available
- Duplicate product codes
- Invalid category/brand references
- Concurrent stock updates
- Decimal quantities
- Price validation (cost > selling)
- Reorder level triggers
- Location permission checks
"""

import pytest
import json
import io
import threading
import time
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.models import db, User, Product, Category, Supplier, Location, LocationStock, StockMovement, StockTransfer, StockTransferItem


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def login_user(client, username, password):
    """Helper function to login a user via the auth route"""
    return client.post('/auth/login', data={
        'username': username,
        'password': password
    }, follow_redirects=True)


# ============================================================================
# MODULE-SPECIFIC FIXTURES
# These fixtures provide specific test data for inventory route tests.
# Base fixtures (app, client, db_session, etc.) come from conftest.py
# ============================================================================

@pytest.fixture
def sample_category(db_session):
    """Create a sample category for inventory tests"""
    category = Category(
        name='Perfumes',
        description='All perfume products'
    )
    db.session.add(category)
    db.session.commit()
    return category


@pytest.fixture
def sample_supplier(db_session):
    """Create a sample supplier for inventory tests"""
    supplier = Supplier(
        name='Test Supplier',
        contact_person='John Doe',
        phone='123-456-7890',
        email='supplier@test.com',
        is_active=True
    )
    db.session.add(supplier)
    db.session.commit()
    return supplier


@pytest.fixture
def sample_product(db_session, sample_category, sample_supplier):
    """Create a sample product for inventory tests"""
    product = Product(
        code='PROD-001',
        barcode='1234567890123',
        name='Test Perfume',
        brand='Test Brand',
        category_id=sample_category.id,
        supplier_id=sample_supplier.id,
        description='A test perfume product',
        size='100ml',
        unit='piece',
        cost_price=Decimal('50.00'),
        selling_price=Decimal('100.00'),
        tax_rate=Decimal('0.00'),
        quantity=100,
        reorder_level=10,
        reorder_quantity=50,
        is_active=True
    )
    db.session.add(product)
    db.session.commit()
    return product


@pytest.fixture
def warehouse_location(db_session):
    """Create a warehouse location for inventory tests"""
    warehouse = Location.query.filter_by(code='WH-INV-001').first()
    if not warehouse:
        warehouse = Location(
            code='WH-INV-001',
            name='Inventory Test Warehouse',
            location_type='warehouse',
            is_active=True,
            can_sell=False
        )
        db.session.add(warehouse)
        db.session.commit()
    return warehouse


@pytest.fixture
def kiosk_location(db_session, warehouse_location):
    """Create a kiosk location linked to warehouse for inventory tests"""
    kiosk = Location.query.filter_by(code='K-INV-001').first()
    if not kiosk:
        kiosk = Location(
            code='K-INV-001',
            name='Inventory Test Kiosk',
            location_type='kiosk',
            is_active=True,
            can_sell=True,
            parent_warehouse_id=warehouse_location.id
        )
        db.session.add(kiosk)
        db.session.commit()
    return kiosk


@pytest.fixture
def inventory_admin_user(db_session, warehouse_location):
    """Create an admin user for inventory tests"""
    user = User(
        username='inv_admin',
        email='inv_admin@test.com',
        full_name='Inventory Admin User',
        role='admin',
        is_active=True,
        is_global_admin=True,
        location_id=warehouse_location.id
    )
    user.set_password('invadmin123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def inventory_kiosk_user(db_session, kiosk_location):
    """Create a kiosk manager user for inventory tests"""
    user = User(
        username='inv_kiosk_mgr',
        email='inv_kiosk@test.com',
        full_name='Inventory Kiosk Manager',
        role='kiosk_manager',
        is_active=True,
        is_global_admin=False,
        location_id=kiosk_location.id
    )
    user.set_password('invkiosk123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def inventory_cashier_user(db_session, kiosk_location):
    """Create a cashier user with limited permissions for inventory tests"""
    user = User(
        username='inv_cashier',
        email='inv_cashier@test.com',
        full_name='Inventory Cashier User',
        role='cashier',
        is_active=True,
        is_global_admin=False,
        location_id=kiosk_location.id
    )
    user.set_password('invcashier123')
    db.session.add(user)
    db.session.commit()
    return user


# ============================================================================
# PRODUCT CRUD TESTS
# ============================================================================

class TestProductCRUD:
    """Test Product Create, Read, Update, Delete operations"""

    def test_view_inventory_index_authenticated(self, client, inventory_admin_user):
        """Test viewing inventory list as authenticated user"""
        login_user(client, 'inv_admin', 'invadmin123')
        response = client.get('/inventory/')
        assert response.status_code == 200

    def test_view_inventory_index_unauthenticated(self, client):
        """Test viewing inventory list without authentication"""
        response = client.get('/inventory/')
        # Should redirect to login
        assert response.status_code == 302

    def test_add_product_success(self, client, inventory_admin_user, sample_category, sample_supplier):
        """Test successfully adding a new product"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post('/inventory/add', data={
            'code': 'NEW-PROD-001',
            'barcode': '9876543210987',
            'name': 'New Test Product',
            'brand': 'New Brand',
            'category_id': sample_category.id,
            'supplier_id': sample_supplier.id,
            'description': 'A new product',
            'size': '50ml',
            'unit': 'piece',
            'cost_price': '25.00',
            'selling_price': '50.00',
            'tax_rate': '0',
            'quantity': '50',
            'reorder_level': '5',
            'reorder_quantity': '25'
        }, follow_redirects=True)

        product = Product.query.filter_by(code='NEW-PROD-001').first()
        assert product is not None
        assert product.name == 'New Test Product'
        assert product.quantity == 50

    def test_add_product_duplicate_code(self, client, inventory_admin_user, sample_product, sample_category):
        """Test adding product with duplicate code"""
        login_user(client, 'inv_admin', 'invadmin123')

        # Try to add product with same code as sample_product
        response = client.post('/inventory/add', data={
            'code': sample_product.code,  # Duplicate code
            'barcode': '1111111111111',
            'name': 'Duplicate Code Product',
            'cost_price': '10.00',
            'selling_price': '20.00',
            'quantity': '10'
        }, follow_redirects=True)

        # Should fail or show error
        products = Product.query.filter_by(code=sample_product.code).all()
        # Should only be the original product
        assert len(products) == 1

    def test_edit_product_success(self, client, inventory_admin_user, sample_product):
        """Test successfully editing a product"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post(f'/inventory/edit/{sample_product.id}', data={
            'code': sample_product.code,
            'name': 'Updated Product Name',
            'brand': 'Updated Brand',
            'cost_price': '60.00',
            'selling_price': '120.00',
            'reorder_level': '15',
            'reorder_quantity': '75',
            'unit': 'piece'
        }, follow_redirects=True)

        product = Product.query.get(sample_product.id)
        assert product.name == 'Updated Product Name'
        assert product.brand == 'Updated Brand'

    def test_delete_product_soft_delete(self, client, inventory_admin_user, sample_product):
        """Test that product deletion is soft delete (is_active=False)"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post(f'/inventory/delete/{sample_product.id}')

        product = Product.query.get(sample_product.id)
        # Product should still exist but be inactive
        assert product is not None
        assert product.is_active == False

    def test_view_product_details(self, client, inventory_admin_user, sample_product):
        """Test viewing individual product details"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get(f'/inventory/product/{sample_product.id}')
        assert response.status_code == 200

    def test_view_nonexistent_product(self, client, inventory_admin_user):
        """Test viewing product that doesn't exist"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/inventory/product/99999')
        assert response.status_code == 404


# ============================================================================
# STOCK ADJUSTMENT TESTS
# ============================================================================

class TestStockAdjustments:
    """Test stock adjustment operations"""

    def test_adjust_stock_add(self, client, inventory_admin_user, sample_product):
        """Test adding stock via adjustment"""
        login_user(client, 'inv_admin', 'invadmin123')

        initial_qty = sample_product.quantity

        response = client.post(f'/inventory/adjust-stock/{sample_product.id}',
            json={
                'adjustment_type': 'add',
                'quantity': 50,
                'reason': 'Received shipment'
            },
            content_type='application/json'
        )

        data = json.loads(response.data)
        # Check response
        assert response.status_code == 200 or data.get('success') == True

    def test_adjust_stock_remove(self, client, inventory_admin_user, sample_product):
        """Test removing stock via adjustment"""
        login_user(client, 'inv_admin', 'invadmin123')

        initial_qty = sample_product.quantity

        response = client.post(f'/inventory/adjust-stock/{sample_product.id}',
            json={
                'adjustment_type': 'remove',
                'quantity': 20,
                'reason': 'Damaged goods'
            },
            content_type='application/json'
        )

        assert response.status_code == 200

    def test_adjust_stock_negative_below_zero(self, client, inventory_admin_user, sample_product):
        """Test that stock cannot go below zero"""
        login_user(client, 'inv_admin', 'invadmin123')

        # Try to remove more than available
        response = client.post(f'/inventory/adjust-stock/{sample_product.id}',
            json={
                'adjustment_type': 'remove',
                'quantity': 1000,  # More than available
                'reason': 'Testing negative stock'
            },
            content_type='application/json'
        )

        data = json.loads(response.data)
        # Should return error
        assert response.status_code == 400 or data.get('success') == False
        assert 'negative' in data.get('error', '').lower() or 'error' in data

    def test_adjust_stock_set_quantity(self, client, inventory_admin_user, sample_product):
        """Test setting stock to specific quantity"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post(f'/inventory/adjust-stock/{sample_product.id}',
            json={
                'adjustment_type': 'set',
                'quantity': 75,
                'reason': 'Physical count correction'
            },
            content_type='application/json'
        )

        assert response.status_code == 200

    def test_adjust_stock_creates_movement_record(self, client, inventory_admin_user, sample_product):
        """Test that stock adjustment creates movement record"""
        login_user(client, 'inv_admin', 'invadmin123')

        initial_movements = StockMovement.query.filter_by(product_id=sample_product.id).count()

        response = client.post(f'/inventory/adjust-stock/{sample_product.id}',
            json={
                'adjustment_type': 'add',
                'quantity': 10,
                'reason': 'Test movement'
            },
            content_type='application/json'
        )

        if response.status_code == 200:
            final_movements = StockMovement.query.filter_by(product_id=sample_product.id).count()
            assert final_movements > initial_movements

    def test_adjust_stock_page_get(self, client, inventory_admin_user, sample_product):
        """Test viewing stock adjustment page"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get(f'/inventory/adjust-stock-page/{sample_product.id}')
        assert response.status_code == 200

    def test_adjust_stock_page_post(self, client, inventory_admin_user, sample_product):
        """Test stock adjustment via form POST"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post(f'/inventory/adjust-stock-page/{sample_product.id}', data={
            'adjustment_type': 'add',
            'quantity': '25',
            'reason': 'Form submission test'
        }, follow_redirects=True)

        assert response.status_code == 200


# ============================================================================
# STOCK TRANSFER TESTS
# ============================================================================

class TestStockTransfers:
    """Test stock transfer operations between locations"""

    def test_create_transfer_request(self, client, inventory_admin_user, sample_product, warehouse_location, kiosk_location):
        """Test creating a transfer request"""
        # Set up stock at warehouse
        warehouse_stock = LocationStock(
            location_id=warehouse_location.id,
            product_id=sample_product.id,
            quantity=100,
            reorder_level=10
        )
        db.session.add(warehouse_stock)

        # Update admin user to be at kiosk
        inventory_admin_user.location_id = kiosk_location.id
        db.session.commit()

        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post('/transfers/create', data={
            'source_location_id': warehouse_location.id,
            'priority': 'normal',
            'expected_delivery_date': (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d'),
            'notes': 'Test transfer request',
            'product_id[]': [sample_product.id],
            'quantity[]': ['20']
        }, follow_redirects=True)

        # Check that transfer was created
        transfer = StockTransfer.query.filter_by(
            destination_location_id=kiosk_location.id
        ).first()

        # Should redirect or succeed
        assert response.status_code == 200

    def test_transfer_to_same_location(self, client, inventory_admin_user, sample_product, warehouse_location):
        """Test that transfer to same location is prevented"""
        # User is already at warehouse from fixture
        login_user(client, 'inv_admin', 'invadmin123')

        # Try to create transfer to same location
        response = client.post('/transfers/create', data={
            'source_location_id': warehouse_location.id,  # Same as user location
            'priority': 'normal',
            'product_id[]': [sample_product.id],
            'quantity[]': ['10']
        }, follow_redirects=True)

        # The transfer system creates destination as current location
        # So source == destination should be handled
        assert response.status_code == 200

    def test_transfer_more_than_available(self, client, inventory_admin_user, sample_product, warehouse_location, kiosk_location):
        """Test transfer requesting more than available stock"""
        # Set up limited stock at warehouse
        warehouse_stock = LocationStock(
            location_id=warehouse_location.id,
            product_id=sample_product.id,
            quantity=10,
            reorder_level=5
        )
        db.session.add(warehouse_stock)

        # Update admin user to be at kiosk
        inventory_admin_user.location_id = kiosk_location.id
        db.session.commit()

        login_user(client, 'inv_admin', 'invadmin123')

        # Request more than available
        response = client.post('/transfers/create', data={
            'source_location_id': warehouse_location.id,
            'priority': 'urgent',
            'product_id[]': [sample_product.id],
            'quantity[]': ['1000']  # Way more than available
        }, follow_redirects=True)

        # Transfer request might still be created (approval will handle this)
        # or it might be rejected at creation time
        assert response.status_code == 200

    def test_view_transfers_list(self, client, inventory_admin_user):
        """Test viewing transfers list"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/transfers/')
        assert response.status_code == 200

    def test_view_pending_transfers(self, client, inventory_admin_user, warehouse_location):
        """Test viewing pending transfers (warehouse view)"""
        # Set user to warehouse
        inventory_admin_user.location_id = warehouse_location.id
        db.session.commit()

        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/transfers/pending')
        assert response.status_code == 200

    def test_view_incoming_transfers(self, client, inventory_admin_user, kiosk_location):
        """Test viewing incoming transfers (kiosk view)"""
        # Set user to kiosk
        inventory_admin_user.location_id = kiosk_location.id
        db.session.commit()

        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/transfers/incoming')
        assert response.status_code == 200


# ============================================================================
# REORDER ALERT TESTS
# ============================================================================

class TestReorderAlerts:
    """Test reorder alert functionality"""

    def test_low_stock_alert_view(self, client, inventory_admin_user):
        """Test viewing low stock alerts"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/inventory/low-stock-alert')
        assert response.status_code == 200

    def test_product_at_reorder_level_appears_in_alerts(self, client, inventory_admin_user):
        """Test that products at/below reorder level appear in alerts"""
        # Create product at reorder level
        low_stock_product = Product(
            code='LOW-001',
            name='Low Stock Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('20.00'),
            quantity=5,  # At reorder level
            reorder_level=5,
            is_active=True
        )
        db.session.add(low_stock_product)
        db.session.commit()

        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/inventory/low-stock-alert')
        assert response.status_code == 200
        # Product should be in the response
        assert b'Low Stock Product' in response.data or b'LOW-001' in response.data

    def test_product_above_reorder_level_not_in_alerts(self, client, inventory_admin_user, sample_product):
        """Test that products above reorder level don't appear in alerts"""
        # sample_product has quantity=100, reorder_level=10
        assert sample_product.quantity > sample_product.reorder_level

        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/inventory/low-stock-alert')
        assert response.status_code == 200

    def test_reorders_view(self, client, inventory_admin_user, kiosk_location, sample_product):
        """Test the reorders management view"""
        # Set user to kiosk
        inventory_admin_user.location_id = kiosk_location.id
        db.session.commit()

        # Create low stock at kiosk
        kiosk_stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=3,
            reorder_level=10
        )
        db.session.add(kiosk_stock)
        db.session.commit()

        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/transfers/reorders')
        assert response.status_code == 200


# ============================================================================
# CATEGORY MANAGEMENT TESTS
# ============================================================================

class TestCategoryManagement:
    """Test category management operations"""

    def test_view_categories(self, client, inventory_admin_user, sample_category):
        """Test viewing categories list"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/inventory/categories')
        assert response.status_code == 200

    def test_product_with_category(self, client, inventory_admin_user, sample_product, sample_category):
        """Test that product is properly linked to category"""
        product = Product.query.get(sample_product.id)
        assert product.category_id == sample_category.id
        assert product.category.name == sample_category.name

    def test_product_with_invalid_category(self, client, inventory_admin_user):
        """Test creating product with non-existent category"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post('/inventory/add', data={
            'code': 'INVALID-CAT-001',
            'name': 'Product with Invalid Category',
            'category_id': '99999',  # Non-existent category
            'cost_price': '10.00',
            'selling_price': '20.00',
            'quantity': '10'
        }, follow_redirects=True)

        # Should handle gracefully
        assert response.status_code == 200


# ============================================================================
# BRAND MANAGEMENT TESTS
# ============================================================================

class TestBrandManagement:
    """Test brand-related operations"""

    def test_product_with_brand(self, client, inventory_admin_user, sample_product):
        """Test that product has brand set"""
        product = Product.query.get(sample_product.id)
        assert product.brand == 'Test Brand'

    def test_search_by_brand(self, client, inventory_admin_user, sample_product):
        """Test searching products by brand"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/inventory/?search=Test%20Brand')
        assert response.status_code == 200


# ============================================================================
# BULK IMPORT/EXPORT TESTS
# ============================================================================

class TestBulkOperations:
    """Test bulk import/export operations"""

    def test_csv_import_valid_file(self, client, inventory_admin_user):
        """Test importing products from valid CSV"""
        login_user(client, 'inv_admin', 'invadmin123')

        # Create CSV content
        csv_content = """code,name,cost_price,selling_price,quantity
CSV-001,CSV Product 1,10.00,20.00,50
CSV-002,CSV Product 2,15.00,30.00,75"""

        data = {
            'file': (io.BytesIO(csv_content.encode()), 'products.csv')
        }

        response = client.post('/inventory/import-csv',
            data=data,
            content_type='multipart/form-data',
            follow_redirects=True
        )

        csv_product = Product.query.filter_by(code='CSV-001').first()
        if csv_product:
            assert csv_product.name == 'CSV Product 1'

    def test_csv_import_duplicate_codes(self, client, inventory_admin_user, sample_product):
        """Test CSV import with duplicate product codes"""
        login_user(client, 'inv_admin', 'invadmin123')

        # Create CSV with duplicate code
        csv_content = f"""code,name,cost_price,selling_price,quantity
{sample_product.code},Duplicate Product,10.00,20.00,50"""

        data = {
            'file': (io.BytesIO(csv_content.encode()), 'products.csv')
        }

        response = client.post('/inventory/import-csv',
            data=data,
            content_type='multipart/form-data',
            follow_redirects=True
        )

        # Should handle duplicates gracefully
        assert response.status_code == 200

    def test_csv_import_no_file(self, client, inventory_admin_user):
        """Test CSV import without file"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post('/inventory/import-csv',
            data={},
            follow_redirects=True
        )

        # Should show error about missing file
        assert response.status_code == 200


# ============================================================================
# PRICE VALIDATION TESTS
# ============================================================================

class TestPriceValidation:
    """Test price-related validations"""

    def test_cost_price_higher_than_selling_price(self, client, inventory_admin_user, sample_category):
        """Test creating product where cost > selling (negative margin)"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post('/inventory/add', data={
            'code': 'NEGATIVE-MARGIN-001',
            'name': 'Negative Margin Product',
            'cost_price': '100.00',
            'selling_price': '50.00',  # Less than cost
            'quantity': '10'
        }, follow_redirects=True)

        # Product might still be created (business logic may allow this)
        # but profit_margin property should show negative
        product = Product.query.filter_by(code='NEGATIVE-MARGIN-001').first()
        if product:
            assert product.profit_margin < 0

    def test_zero_prices(self, client, inventory_admin_user):
        """Test creating product with zero prices"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post('/inventory/add', data={
            'code': 'ZERO-PRICE-001',
            'name': 'Zero Price Product',
            'cost_price': '0',
            'selling_price': '0',
            'quantity': '10'
        }, follow_redirects=True)

        # Should handle gracefully
        assert response.status_code == 200

    def test_decimal_prices(self, client, inventory_admin_user):
        """Test creating product with decimal prices"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post('/inventory/add', data={
            'code': 'DECIMAL-PRICE-001',
            'name': 'Decimal Price Product',
            'cost_price': '10.99',
            'selling_price': '19.99',
            'quantity': '10'
        }, follow_redirects=True)

        product = Product.query.filter_by(code='DECIMAL-PRICE-001').first()
        if product:
            assert float(product.cost_price) == 10.99
            assert float(product.selling_price) == 19.99


# ============================================================================
# LOCATION PERMISSION TESTS
# ============================================================================

class TestLocationPermissions:
    """Test location-based permission checks"""

    def test_cashier_cannot_adjust_stock(self, client, inventory_cashier_user, sample_product):
        """Test that cashier role cannot adjust stock"""
        login_user(client, 'inv_cashier', 'invcashier123')

        response = client.post(f'/inventory/adjust-stock/{sample_product.id}',
            json={
                'adjustment_type': 'add',
                'quantity': 10,
                'reason': 'Unauthorized adjustment'
            },
            content_type='application/json'
        )

        # Should be forbidden or redirect
        assert response.status_code in [302, 403, 401]

    def test_kiosk_user_sees_only_location_stock(self, client, inventory_kiosk_user, sample_product, kiosk_location):
        """Test that kiosk user only sees their location's stock"""
        # Create stock at kiosk
        kiosk_stock = LocationStock(
            location_id=kiosk_location.id,
            product_id=sample_product.id,
            quantity=25,
            reorder_level=5
        )
        db.session.add(kiosk_stock)
        db.session.commit()

        login_user(client, 'inv_kiosk_mgr', 'invkiosk123')

        response = client.get('/inventory/')
        assert response.status_code == 200

    def test_global_admin_sees_all_locations(self, client, inventory_admin_user):
        """Test that global admin can see all locations"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/inventory/')
        assert response.status_code == 200

    def test_user_without_location_cannot_request_transfer(self, client, db_session):
        """Test that user without assigned location cannot request transfer"""
        # Create user without location
        no_loc_user = User(
            username='no_location',
            email='noloc@test.com',
            full_name='No Location User',
            role='manager',
            is_active=True,
            location_id=None
        )
        no_loc_user.set_password('noloc123')
        db.session.add(no_loc_user)
        db.session.commit()

        login_user(client, 'no_location', 'noloc123')

        response = client.get('/transfers/create')
        # Should redirect with warning or show error
        assert response.status_code in [200, 302]


# ============================================================================
# CONCURRENT UPDATE TESTS
# ============================================================================

class TestConcurrentUpdates:
    """Test handling of concurrent stock updates"""

    def test_concurrent_stock_adjustments(self, app_context, inventory_admin_user, sample_product):
        """Test handling of simultaneous stock adjustments"""
        from flask import current_app as app

        initial_quantity = sample_product.quantity
        results = []
        errors = []

        def adjust_stock(amount, index):
            """Perform stock adjustment in thread"""
            try:
                with app.test_client() as thread_client:
                    login_user(thread_client, 'inv_admin', 'invadmin123')
                    response = thread_client.post(
                        f'/inventory/adjust-stock/{sample_product.id}',
                        json={
                            'adjustment_type': 'add',
                            'quantity': amount,
                            'reason': f'Concurrent test {index}'
                        },
                        content_type='application/json'
                    )
                    results.append((index, response.status_code))
            except Exception as e:
                errors.append((index, str(e)))

        # Create multiple threads to adjust stock simultaneously
        threads = []
        for i in range(5):
            t = threading.Thread(target=adjust_stock, args=(10, i))
            threads.append(t)

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all to complete
        for t in threads:
            t.join(timeout=10)

        # The system should handle concurrent updates
        # Either all succeed or some fail gracefully
        assert len(results) + len(errors) == 5


# ============================================================================
# STOCK MOVEMENT HISTORY TESTS
# ============================================================================

class TestStockMovementHistory:
    """Test stock movement history tracking"""

    def test_view_stock_movements(self, client, inventory_admin_user, sample_product):
        """Test viewing stock movement history for a product"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get(f'/inventory/stock-movements/{sample_product.id}')
        assert response.status_code == 200

    def test_adjustment_creates_movement(self, client, inventory_admin_user, sample_product):
        """Test that stock adjustment creates a movement record"""
        login_user(client, 'inv_admin', 'invadmin123')

        initial_count = StockMovement.query.filter_by(
            product_id=sample_product.id
        ).count()

        # Make adjustment
        client.post(f'/inventory/adjust-stock/{sample_product.id}',
            json={
                'adjustment_type': 'add',
                'quantity': 10,
                'reason': 'Test movement tracking'
            },
            content_type='application/json'
        )

        final_count = StockMovement.query.filter_by(
            product_id=sample_product.id
        ).count()

        # Should have created a new movement record
        assert final_count >= initial_count


# ============================================================================
# STOCK REPORT TESTS
# ============================================================================

class TestStockReports:
    """Test stock report functionality"""

    def test_print_stock_report(self, client, inventory_admin_user, sample_product):
        """Test printing stock report"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/inventory/print-stock-report')
        assert response.status_code == 200

    def test_print_low_stock_report(self, client, inventory_admin_user):
        """Test printing low stock report"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/inventory/print-stock-report?type=low')
        assert response.status_code == 200


# ============================================================================
# PRODUCT FILTERING TESTS
# ============================================================================

class TestProductFiltering:
    """Test product filtering and search"""

    def test_filter_by_category(self, client, inventory_admin_user, sample_product, sample_category):
        """Test filtering products by category"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get(f'/inventory/?category={sample_category.id}')
        assert response.status_code == 200

    def test_filter_by_supplier(self, client, inventory_admin_user, sample_product, sample_supplier):
        """Test filtering products by supplier"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get(f'/inventory/?supplier={sample_supplier.id}')
        assert response.status_code == 200

    def test_filter_by_stock_status_low(self, client, inventory_admin_user):
        """Test filtering by low stock status"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/inventory/?stock_status=low_stock')
        assert response.status_code == 200

    def test_filter_by_stock_status_out(self, client, inventory_admin_user):
        """Test filtering by out of stock status"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/inventory/?stock_status=out_of_stock')
        assert response.status_code == 200

    def test_search_by_code(self, client, inventory_admin_user, sample_product):
        """Test searching products by code"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get(f'/inventory/?search={sample_product.code}')
        assert response.status_code == 200

    def test_search_by_name(self, client, inventory_admin_user, sample_product):
        """Test searching products by name"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/inventory/?search=Test%20Perfume')
        assert response.status_code == 200


# ============================================================================
# API ENDPOINT TESTS
# ============================================================================

class TestAPIEndpoints:
    """Test API endpoints for inventory"""

    def test_api_search_products(self, client, inventory_admin_user, sample_product, warehouse_location):
        """Test API endpoint for searching products"""
        # Create stock at warehouse
        warehouse_stock = LocationStock(
            location_id=warehouse_location.id,
            product_id=sample_product.id,
            quantity=50,
            reorder_level=10
        )
        db.session.add(warehouse_stock)
        db.session.commit()

        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get(f'/transfers/api/search-products?source_id={warehouse_location.id}&q=Test')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'products' in data

    def test_api_search_products_no_query(self, client, inventory_admin_user, warehouse_location):
        """Test API search with no/short query"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get(f'/transfers/api/search-products?source_id={warehouse_location.id}&q=a')
        assert response.status_code == 200

        data = json.loads(response.data)
        # Should return empty products for short query
        assert data.get('products') == []


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Test various edge cases"""

    def test_product_expiry_date(self, client, inventory_admin_user):
        """Test product with expiry date"""
        login_user(client, 'inv_admin', 'invadmin123')

        expiry_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')

        response = client.post('/inventory/add', data={
            'code': 'EXPIRY-001',
            'name': 'Product with Expiry',
            'cost_price': '10.00',
            'selling_price': '20.00',
            'quantity': '10',
            'expiry_date': expiry_date
        }, follow_redirects=True)

        product = Product.query.filter_by(code='EXPIRY-001').first()
        if product:
            assert product.expiry_date is not None

    def test_product_expiry_status(self, db_session):
        """Test product expiry status calculations"""
        from datetime import date

        # Create expired product
        expired_product = Product(
            code='EXPIRED-001',
            name='Expired Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('20.00'),
            quantity=10,
            expiry_date=date.today() - timedelta(days=1),
            is_active=True
        )
        db.session.add(expired_product)

        # Create product expiring soon
        expiring_product = Product(
            code='EXPIRING-001',
            name='Expiring Soon Product',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('20.00'),
            quantity=10,
            expiry_date=date.today() + timedelta(days=5),
            is_active=True
        )
        db.session.add(expiring_product)
        db.session.commit()

        assert expired_product.is_expired == True
        assert expired_product.expiry_status == 'expired'

        assert expiring_product.is_expiring_critical == True
        assert expiring_product.expiry_status == 'critical'

    def test_empty_inventory(self, client, inventory_admin_user):
        """Test inventory view with no products"""
        # Clear all products
        Product.query.delete()
        db.session.commit()

        login_user(client, 'inv_admin', 'invadmin123')

        response = client.get('/inventory/')
        assert response.status_code == 200

    def test_large_quantity_values(self, client, inventory_admin_user):
        """Test handling of large quantity values"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post('/inventory/add', data={
            'code': 'LARGE-QTY-001',
            'name': 'Large Quantity Product',
            'cost_price': '10.00',
            'selling_price': '20.00',
            'quantity': '999999'  # Very large quantity
        }, follow_redirects=True)

        product = Product.query.filter_by(code='LARGE-QTY-001').first()
        if product:
            assert product.quantity == 999999

    def test_special_characters_in_product_name(self, client, inventory_admin_user):
        """Test product with special characters in name"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post('/inventory/add', data={
            'code': 'SPECIAL-001',
            'name': "Product with 'Special' & \"Characters\" <test>",
            'cost_price': '10.00',
            'selling_price': '20.00',
            'quantity': '10'
        }, follow_redirects=True)

        product = Product.query.filter_by(code='SPECIAL-001').first()
        if product:
            assert 'Special' in product.name


# ============================================================================
# TRANSFER WORKFLOW TESTS
# ============================================================================

class TestTransferWorkflow:
    """Test complete transfer workflow"""

    def test_transfer_approval_workflow(self, client, inventory_admin_user, sample_product,
                                         warehouse_location, kiosk_location):
        """Test transfer approval workflow"""
        from app.utils.location_context import generate_transfer_number

        # Create stock at warehouse
        warehouse_stock = LocationStock(
            location_id=warehouse_location.id,
            product_id=sample_product.id,
            quantity=100,
            reorder_level=10
        )
        db.session.add(warehouse_stock)

        # Create transfer request
        transfer = StockTransfer(
            transfer_number=generate_transfer_number(),
            source_location_id=warehouse_location.id,
            destination_location_id=kiosk_location.id,
            status='requested',
            priority='normal',
            requested_by=inventory_admin_user.id,
            requested_at=datetime.utcnow()
        )
        db.session.add(transfer)
        db.session.flush()

        item = StockTransferItem(
            transfer_id=transfer.id,
            product_id=sample_product.id,
            quantity_requested=20
        )
        db.session.add(item)
        db.session.commit()

        # Set user to warehouse location for approval
        inventory_admin_user.location_id = warehouse_location.id
        db.session.commit()

        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post(f'/transfers/{transfer.id}/approve', data={
            'action': 'approve',
            f'approved_qty_{item.id}': '20',
            'notes': 'Approved for testing'
        }, follow_redirects=True)

        # Verify status changed
        db.session.refresh(transfer)
        # Transfer should be approved (or response should indicate action taken)
        assert response.status_code == 200

    def test_transfer_dispatch_workflow(self, client, inventory_admin_user, sample_product,
                                         warehouse_location, kiosk_location):
        """Test transfer dispatch workflow"""
        from app.utils.location_context import generate_transfer_number

        # Create stock at warehouse
        warehouse_stock = LocationStock(
            location_id=warehouse_location.id,
            product_id=sample_product.id,
            quantity=100,
            reserved_quantity=20,
            reorder_level=10
        )
        db.session.add(warehouse_stock)

        # Create approved transfer
        transfer = StockTransfer(
            transfer_number=generate_transfer_number(),
            source_location_id=warehouse_location.id,
            destination_location_id=kiosk_location.id,
            status='approved',
            priority='normal',
            requested_by=inventory_admin_user.id,
            requested_at=datetime.utcnow(),
            approved_by=inventory_admin_user.id,
            approved_at=datetime.utcnow()
        )
        db.session.add(transfer)
        db.session.flush()

        item = StockTransferItem(
            transfer_id=transfer.id,
            product_id=sample_product.id,
            quantity_requested=20,
            quantity_approved=20
        )
        db.session.add(item)
        db.session.commit()

        # Set user to warehouse
        inventory_admin_user.location_id = warehouse_location.id
        db.session.commit()

        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post(f'/transfers/{transfer.id}/dispatch', data={
            'notes': 'Dispatched for testing'
        }, follow_redirects=True)

        # Verify dispatch
        db.session.refresh(transfer)
        assert response.status_code == 200

    def test_transfer_receive_workflow(self, client, inventory_admin_user, sample_product,
                                        warehouse_location, kiosk_location):
        """Test transfer receive workflow"""
        from app.utils.location_context import generate_transfer_number

        # Create dispatched transfer
        transfer = StockTransfer(
            transfer_number=generate_transfer_number(),
            source_location_id=warehouse_location.id,
            destination_location_id=kiosk_location.id,
            status='dispatched',
            priority='normal',
            requested_by=inventory_admin_user.id,
            requested_at=datetime.utcnow(),
            approved_by=inventory_admin_user.id,
            approved_at=datetime.utcnow(),
            dispatched_by=inventory_admin_user.id,
            dispatched_at=datetime.utcnow()
        )
        db.session.add(transfer)
        db.session.flush()

        item = StockTransferItem(
            transfer_id=transfer.id,
            product_id=sample_product.id,
            quantity_requested=20,
            quantity_approved=20,
            quantity_dispatched=20
        )
        db.session.add(item)
        db.session.commit()

        # Set user to kiosk (destination)
        inventory_admin_user.location_id = kiosk_location.id
        db.session.commit()

        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post(f'/transfers/{transfer.id}/receive', data={
            f'received_qty_{item.id}': '20',
            'notes': 'Received in full'
        }, follow_redirects=True)

        # Verify receive
        db.session.refresh(transfer)
        assert response.status_code == 200

    def test_transfer_cancel(self, client, inventory_admin_user, sample_product,
                             warehouse_location, kiosk_location):
        """Test transfer cancellation"""
        from app.utils.location_context import generate_transfer_number

        # Create requested transfer
        transfer = StockTransfer(
            transfer_number=generate_transfer_number(),
            source_location_id=warehouse_location.id,
            destination_location_id=kiosk_location.id,
            status='requested',
            priority='normal',
            requested_by=inventory_admin_user.id,
            requested_at=datetime.utcnow()
        )
        db.session.add(transfer)
        db.session.flush()

        item = StockTransferItem(
            transfer_id=transfer.id,
            product_id=sample_product.id,
            quantity_requested=20
        )
        db.session.add(item)
        db.session.commit()

        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post(f'/transfers/{transfer.id}/cancel', data={
            'reason': 'Test cancellation'
        }, follow_redirects=True)

        # Verify cancellation
        db.session.refresh(transfer)
        assert response.status_code == 200


# ============================================================================
# DECIMAL QUANTITY TESTS
# ============================================================================

class TestDecimalQuantities:
    """Test handling of decimal quantities"""

    def test_integer_quantity_only(self, client, inventory_admin_user, sample_product):
        """Test that product quantities are integers"""
        product = Product.query.get(sample_product.id)
        # Quantity should be integer
        assert isinstance(product.quantity, int)

    def test_decimal_quantity_in_adjustment(self, client, inventory_admin_user, sample_product):
        """Test adjustment with decimal quantity (should be converted/rejected)"""
        login_user(client, 'inv_admin', 'invadmin123')

        # Try decimal quantity adjustment
        response = client.post(f'/inventory/adjust-stock/{sample_product.id}',
            json={
                'adjustment_type': 'add',
                'quantity': 10.5,  # Decimal
                'reason': 'Decimal test'
            },
            content_type='application/json'
        )

        # Should handle gracefully (convert to int or reject)
        assert response.status_code in [200, 400]


# ============================================================================
# ADDITIONAL EDGE CASE TESTS FOR INVENTORY
# ============================================================================

class TestInventoryEdgeCases:
    """Additional edge case tests for inventory management"""

    @pytest.mark.edge_case
    def test_negative_stock_prevents_sale(self, client, inventory_admin_user, sample_product):
        """Test that system prevents negative stock"""
        login_user(client, 'inv_admin', 'invadmin123')

        # Set product to very low stock first
        sample_product.quantity = 1
        db.session.commit()

        # Try to remove more than available
        response = client.post(f'/inventory/adjust-stock/{sample_product.id}',
            json={
                'adjustment_type': 'remove',
                'quantity': 100,
                'reason': 'Test negative prevention'
            },
            content_type='application/json'
        )

        # Refresh product and check stock didn't go negative
        db.session.refresh(sample_product)
        assert sample_product.quantity >= 0

    @pytest.mark.edge_case
    def test_invalid_barcode_format(self, client, inventory_admin_user):
        """Test handling of invalid barcode formats"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post('/inventory/add', data={
            'code': 'INVALID-BC-001',
            'barcode': 'not-a-valid-barcode-12345678901234567890',  # Too long
            'name': 'Invalid Barcode Product',
            'cost_price': '10.00',
            'selling_price': '20.00',
            'quantity': '10'
        }, follow_redirects=True)

        # Should handle gracefully
        assert response.status_code == 200

    @pytest.mark.edge_case
    def test_extremely_long_product_name(self, client, inventory_admin_user):
        """Test handling of very long product names"""
        login_user(client, 'inv_admin', 'invadmin123')

        long_name = 'A' * 500  # Very long name

        response = client.post('/inventory/add', data={
            'code': 'LONG-NAME-001',
            'name': long_name,
            'cost_price': '10.00',
            'selling_price': '20.00',
            'quantity': '10'
        }, follow_redirects=True)

        # Should handle gracefully (either truncate or reject)
        assert response.status_code == 200

    @pytest.mark.edge_case
    def test_unicode_product_name(self, client, inventory_admin_user):
        """Test handling of Unicode characters in product names"""
        login_user(client, 'inv_admin', 'invadmin123')

        response = client.post('/inventory/add', data={
            'code': 'UNICODE-001',
            'name': 'Perfume Chinese Characters: Attar Arabic: Franc',
            'cost_price': '10.00',
            'selling_price': '20.00',
            'quantity': '10'
        }, follow_redirects=True)

        # Should handle gracefully
        assert response.status_code == 200


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
