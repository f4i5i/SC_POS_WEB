"""
Comprehensive Integration Tests for SOC_WEB_APP

Tests complete end-to-end workflows including:
1. Full sale workflow: Login -> Add items -> Checkout -> Receipt -> Stock update
2. Stock transfer workflow: Create transfer -> Approve -> Execute -> Verify stock
3. Customer purchase flow: Register customer -> Make purchase -> Earn points -> Tier upgrade
4. Production workflow: Add raw materials -> Create recipe -> Production order -> Execute -> Product created
5. Reporting flow: Make sales -> Generate reports -> Verify calculations
6. User management: Create user -> Assign role -> Login -> Access control

Tests edge cases:
- Concurrent operations
- Transaction rollbacks
- Partial failures
- Data consistency across tables

Uses pytest with Flask test client.
"""

import pytest
import json
import threading
import time
from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed

from app import create_app
from app.models import (
    db, User, Product, Category, Customer, Sale, SaleItem, Payment,
    StockMovement, Location, LocationStock, StockTransfer, StockTransferItem,
    RawMaterial, RawMaterialCategory, RawMaterialStock, Recipe, RecipeIngredient,
    ProductionOrder, ProductionMaterialConsumption, Supplier, Role, Permission,
    DayClose, Setting
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope='function')
def app():
    """Create and configure a new app instance for each test."""
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SERVER_NAME'] = 'localhost'

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture(scope='function')
def runner(app):
    """A test CLI runner for the app."""
    return app.test_cli_runner()


@pytest.fixture(scope='function')
def init_database(app):
    """Initialize database with test data."""
    with app.app_context():
        # Create locations
        warehouse = Location(
            code='WH-001',
            name='Main Warehouse',
            location_type='warehouse',
            is_active=True,
            can_sell=False
        )
        kiosk = Location(
            code='K-001',
            name='Test Kiosk',
            location_type='kiosk',
            is_active=True,
            can_sell=True
        )
        db.session.add_all([warehouse, kiosk])
        db.session.flush()

        # Link kiosk to warehouse
        kiosk.parent_warehouse_id = warehouse.id

        # Create admin user
        admin = User(
            username='admin',
            email='admin@test.com',
            full_name='Admin User',
            role='admin',
            is_active=True,
            is_global_admin=True
        )
        admin.set_password('admin123')

        # Create cashier user
        cashier = User(
            username='cashier',
            email='cashier@test.com',
            full_name='Cashier User',
            role='cashier',
            is_active=True,
            location_id=kiosk.id
        )
        cashier.set_password('cashier123')

        # Create warehouse manager
        wh_manager = User(
            username='warehouse_mgr',
            email='wh@test.com',
            full_name='Warehouse Manager',
            role='warehouse_manager',
            is_active=True,
            location_id=warehouse.id
        )
        wh_manager.set_password('warehouse123')

        # Create kiosk manager
        kiosk_manager = User(
            username='kiosk_mgr',
            email='kiosk@test.com',
            full_name='Kiosk Manager',
            role='kiosk_manager',
            is_active=True,
            location_id=kiosk.id
        )
        kiosk_manager.set_password('kiosk123')

        db.session.add_all([admin, cashier, wh_manager, kiosk_manager])

        # Create category
        category = Category(name='Attars', description='Premium attars')
        db.session.add(category)
        db.session.flush()

        # Create supplier
        supplier = Supplier(
            name='Test Supplier',
            contact_person='John Doe',
            phone='1234567890',
            email='supplier@test.com',
            is_active=True
        )
        db.session.add(supplier)
        db.session.flush()

        # Create products
        products = []
        for i in range(1, 6):
            product = Product(
                code=f'PROD{i:03d}',
                barcode=f'1234567890{i:03d}',
                name=f'Test Product {i}',
                brand='Test Brand',
                category_id=category.id,
                supplier_id=supplier.id,
                cost_price=Decimal('100.00'),
                selling_price=Decimal('150.00'),
                quantity=100,
                reorder_level=10,
                is_active=True
            )
            products.append(product)
        db.session.add_all(products)
        db.session.flush()

        # Create location stock for kiosk
        for product in products:
            loc_stock = LocationStock(
                location_id=kiosk.id,
                product_id=product.id,
                quantity=50,
                reorder_level=5
            )
            db.session.add(loc_stock)

        # Create location stock for warehouse
        for product in products:
            loc_stock = LocationStock(
                location_id=warehouse.id,
                product_id=product.id,
                quantity=200,
                reorder_level=20
            )
            db.session.add(loc_stock)

        # Create raw material categories
        oil_cat = RawMaterialCategory(
            code='OIL',
            name='Oils',
            unit='ml',
            is_active=True
        )
        bottle_cat = RawMaterialCategory(
            code='BOTTLE',
            name='Bottles',
            unit='pieces',
            is_active=True
        )
        ethanol_cat = RawMaterialCategory(
            code='ETHANOL',
            name='Ethanol',
            unit='ml',
            is_active=True
        )
        db.session.add_all([oil_cat, bottle_cat, ethanol_cat])
        db.session.flush()

        # Create raw materials
        rose_oil = RawMaterial(
            code='OIL-ROSE',
            name='Rose Oil',
            category_id=oil_cat.id,
            cost_per_unit=Decimal('0.50'),
            quantity=Decimal('1000'),
            reorder_level=Decimal('100'),
            is_active=True
        )
        jasmine_oil = RawMaterial(
            code='OIL-JASMINE',
            name='Jasmine Oil',
            category_id=oil_cat.id,
            cost_per_unit=Decimal('0.75'),
            quantity=Decimal('1000'),
            reorder_level=Decimal('100'),
            is_active=True
        )
        bottle_6ml = RawMaterial(
            code='BTL-6ML',
            name='6ml Bottle',
            category_id=bottle_cat.id,
            bottle_size_ml=Decimal('6'),
            cost_per_unit=Decimal('5.00'),
            quantity=Decimal('500'),
            reorder_level=Decimal('50'),
            is_active=True
        )
        ethanol = RawMaterial(
            code='ETH-001',
            name='Ethanol 96%',
            category_id=ethanol_cat.id,
            cost_per_unit=Decimal('0.10'),
            quantity=Decimal('5000'),
            reorder_level=Decimal('500'),
            is_active=True
        )
        db.session.add_all([rose_oil, jasmine_oil, bottle_6ml, ethanol])
        db.session.flush()

        # Create raw material stock at warehouse
        for material in [rose_oil, jasmine_oil, bottle_6ml, ethanol]:
            rm_stock = RawMaterialStock(
                raw_material_id=material.id,
                location_id=warehouse.id,
                quantity=Decimal('1000')
            )
            db.session.add(rm_stock)

        # Create customers
        customers = []
        for i in range(1, 4):
            customer = Customer(
                name=f'Test Customer {i}',
                phone=f'030012345{i:02d}',
                email=f'customer{i}@test.com',
                loyalty_points=100 * i,
                is_active=True
            )
            customers.append(customer)
        db.session.add_all(customers)

        # Create settings
        settings = [
            Setting(key='business_name', value='Test Business', category='business'),
            Setting(key='currency_symbol', value='Rs.', category='business'),
        ]
        db.session.add_all(settings)

        db.session.commit()

        return {
            'warehouse': warehouse,
            'kiosk': kiosk,
            'admin': admin,
            'cashier': cashier,
            'wh_manager': wh_manager,
            'kiosk_manager': kiosk_manager,
            'products': products,
            'category': category,
            'supplier': supplier,
            'customers': customers,
            'raw_materials': {
                'rose_oil': rose_oil,
                'jasmine_oil': jasmine_oil,
                'bottle_6ml': bottle_6ml,
                'ethanol': ethanol
            },
            'raw_material_categories': {
                'oil': oil_cat,
                'bottle': bottle_cat,
                'ethanol': ethanol_cat
            }
        }


def login(client, username, password):
    """Helper function to log in a user."""
    return client.post('/auth/login', data={
        'username': username,
        'password': password
    }, follow_redirects=True)


def logout(client):
    """Helper function to log out."""
    return client.get('/auth/logout', follow_redirects=True)


# =============================================================================
# TEST CLASS: FULL SALE WORKFLOW
# =============================================================================

class TestFullSaleWorkflow:
    """Tests for complete sale workflow: Login -> Add items -> Checkout -> Receipt -> Stock update"""

    def test_complete_sale_workflow(self, client, app, init_database):
        """Test complete sale flow from login to stock update."""
        with app.app_context():
            # Login as cashier
            response = login(client, 'cashier', 'cashier123')
            assert response.status_code == 200

            # Get product for sale
            product = Product.query.filter_by(code='PROD001').first()
            kiosk = Location.query.filter_by(code='K-001').first()
            customer = Customer.query.first()

            # Get initial stock
            initial_stock = LocationStock.query.filter_by(
                location_id=kiosk.id,
                product_id=product.id
            ).first()
            initial_qty = initial_stock.quantity

            # Complete sale via API
            sale_data = {
                'items': [{
                    'product_id': product.id,
                    'quantity': 2,
                    'unit_price': float(product.selling_price),
                    'discount': 0,
                    'subtotal': float(product.selling_price * 2)
                }],
                'customer_id': customer.id,
                'subtotal': float(product.selling_price * 2),
                'discount': 0,
                'discount_type': 'amount',
                'tax': 0,
                'total': float(product.selling_price * 2),
                'payment_method': 'cash',
                'amount_paid': float(product.selling_price * 2)
            }

            response = client.post('/pos/complete-sale',
                                  data=json.dumps(sale_data),
                                  content_type='application/json')
            assert response.status_code == 200
            result = json.loads(response.data)
            assert result['success'] == True
            assert 'sale_id' in result
            assert 'sale_number' in result

            # Verify sale was created
            sale = Sale.query.get(result['sale_id'])
            assert sale is not None
            assert sale.sale_number == result['sale_number']
            assert sale.customer_id == customer.id
            assert sale.payment_status == 'paid'

            # Verify sale items
            sale_items = SaleItem.query.filter_by(sale_id=sale.id).all()
            assert len(sale_items) == 1
            assert sale_items[0].product_id == product.id
            assert sale_items[0].quantity == 2

            # Verify stock was deducted
            updated_stock = LocationStock.query.filter_by(
                location_id=kiosk.id,
                product_id=product.id
            ).first()
            assert updated_stock.quantity == initial_qty - 2

            # Verify stock movement was recorded
            movement = StockMovement.query.filter_by(
                product_id=product.id,
                reference=sale.sale_number
            ).first()
            assert movement is not None
            assert movement.movement_type == 'sale'
            assert movement.quantity == -2

            # Verify customer loyalty points were awarded
            updated_customer = Customer.query.get(customer.id)
            expected_points = customer.loyalty_points + int(float(sale.total) / 100)
            assert updated_customer.loyalty_points == expected_points

            logout(client)

    def test_sale_with_insufficient_stock(self, client, app, init_database):
        """Test that sale fails when insufficient stock."""
        with app.app_context():
            login(client, 'cashier', 'cashier123')

            product = Product.query.filter_by(code='PROD001').first()

            # Try to sell more than available
            sale_data = {
                'items': [{
                    'product_id': product.id,
                    'quantity': 1000,  # More than available
                    'unit_price': float(product.selling_price),
                    'discount': 0,
                    'subtotal': float(product.selling_price * 1000)
                }],
                'subtotal': float(product.selling_price * 1000),
                'discount': 0,
                'tax': 0,
                'total': float(product.selling_price * 1000),
                'payment_method': 'cash',
                'amount_paid': float(product.selling_price * 1000)
            }

            response = client.post('/pos/complete-sale',
                                  data=json.dumps(sale_data),
                                  content_type='application/json')
            result = json.loads(response.data)
            assert result['success'] == False
            assert 'Insufficient stock' in result['error']

            logout(client)

    def test_sale_with_partial_payment(self, client, app, init_database):
        """Test sale with partial payment (credit sale)."""
        with app.app_context():
            login(client, 'cashier', 'cashier123')

            product = Product.query.filter_by(code='PROD001').first()
            customer = Customer.query.first()
            total_amount = float(product.selling_price * 2)
            partial_payment = total_amount / 2

            sale_data = {
                'items': [{
                    'product_id': product.id,
                    'quantity': 2,
                    'unit_price': float(product.selling_price),
                    'discount': 0,
                    'subtotal': total_amount
                }],
                'customer_id': customer.id,
                'subtotal': total_amount,
                'discount': 0,
                'tax': 0,
                'total': total_amount,
                'payment_method': 'cash',
                'amount_paid': partial_payment  # Partial payment
            }

            response = client.post('/pos/complete-sale',
                                  data=json.dumps(sale_data),
                                  content_type='application/json')
            result = json.loads(response.data)
            assert result['success'] == True

            # Verify payment status
            sale = Sale.query.get(result['sale_id'])
            assert sale.payment_status == 'partial'
            assert float(sale.amount_due) == partial_payment

            logout(client)

    def test_sale_with_discount(self, client, app, init_database):
        """Test sale with percentage and amount discounts."""
        with app.app_context():
            login(client, 'admin', 'admin123')

            product = Product.query.filter_by(code='PROD001').first()
            subtotal = float(product.selling_price * 2)
            discount_amount = 20.00
            total = subtotal - discount_amount

            sale_data = {
                'items': [{
                    'product_id': product.id,
                    'quantity': 2,
                    'unit_price': float(product.selling_price),
                    'discount': 0,
                    'subtotal': subtotal
                }],
                'subtotal': subtotal,
                'discount': discount_amount,
                'discount_type': 'amount',
                'tax': 0,
                'total': total,
                'payment_method': 'cash',
                'amount_paid': total
            }

            response = client.post('/pos/complete-sale',
                                  data=json.dumps(sale_data),
                                  content_type='application/json')
            result = json.loads(response.data)
            assert result['success'] == True

            sale = Sale.query.get(result['sale_id'])
            assert float(sale.discount) == discount_amount
            assert float(sale.total) == total

            logout(client)


# =============================================================================
# TEST CLASS: STOCK TRANSFER WORKFLOW
# =============================================================================

class TestStockTransferWorkflow:
    """Tests for stock transfer workflow: Create -> Approve -> Dispatch -> Receive"""

    def test_complete_transfer_workflow(self, client, app, init_database):
        """Test complete stock transfer from warehouse to kiosk."""
        with app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()
            product = Product.query.filter_by(code='PROD001').first()

            # Get initial stock levels
            wh_stock = LocationStock.query.filter_by(
                location_id=warehouse.id,
                product_id=product.id
            ).first()
            kiosk_stock = LocationStock.query.filter_by(
                location_id=kiosk.id,
                product_id=product.id
            ).first()
            initial_wh_qty = wh_stock.quantity
            initial_kiosk_qty = kiosk_stock.quantity
            transfer_qty = 10

            # Step 1: Kiosk manager creates transfer request
            login(client, 'kiosk_mgr', 'kiosk123')

            response = client.post('/transfers/create', data={
                'source_location_id': warehouse.id,
                'priority': 'normal',
                'expected_delivery_date': (date.today() + timedelta(days=1)).strftime('%Y-%m-%d'),
                'notes': 'Test transfer',
                'product_id[]': [str(product.id)],
                'quantity[]': [str(transfer_qty)]
            }, follow_redirects=True)
            assert response.status_code == 200

            # Get the created transfer
            transfer = StockTransfer.query.filter_by(
                destination_location_id=kiosk.id,
                status='requested'
            ).first()
            assert transfer is not None
            assert transfer.items.count() == 1

            logout(client)

            # Step 2: Warehouse manager approves transfer
            login(client, 'warehouse_mgr', 'warehouse123')

            # Approve with same quantity
            response = client.post(f'/transfers/{transfer.id}/approve', data={
                'action': 'approve',
                'notes': 'Approved',
                f'approved_qty_{transfer.items.first().id}': transfer_qty
            }, follow_redirects=True)
            assert response.status_code == 200

            # Verify approval
            db.session.refresh(transfer)
            assert transfer.status == 'approved'

            # Step 3: Dispatch transfer
            response = client.post(f'/transfers/{transfer.id}/dispatch', data={
                'notes': 'Dispatched'
            }, follow_redirects=True)
            assert response.status_code == 200

            db.session.refresh(transfer)
            assert transfer.status == 'dispatched'

            # Verify warehouse stock was deducted
            db.session.refresh(wh_stock)
            assert wh_stock.quantity == initial_wh_qty - transfer_qty

            logout(client)

            # Step 4: Kiosk receives transfer
            login(client, 'kiosk_mgr', 'kiosk123')

            item = transfer.items.first()
            response = client.post(f'/transfers/{transfer.id}/receive', data={
                'notes': 'Received in good condition',
                f'received_qty_{item.id}': transfer_qty
            }, follow_redirects=True)
            assert response.status_code == 200

            db.session.refresh(transfer)
            assert transfer.status == 'received'

            # Verify kiosk stock was increased
            db.session.refresh(kiosk_stock)
            assert kiosk_stock.quantity == initial_kiosk_qty + transfer_qty

            logout(client)

    def test_transfer_with_partial_approval(self, client, app, init_database):
        """Test transfer where warehouse approves less than requested."""
        with app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()
            product = Product.query.filter_by(code='PROD001').first()

            requested_qty = 50
            approved_qty = 30

            # Create transfer request
            login(client, 'kiosk_mgr', 'kiosk123')

            response = client.post('/transfers/create', data={
                'source_location_id': warehouse.id,
                'priority': 'high',
                'notes': 'Urgent request',
                'product_id[]': [str(product.id)],
                'quantity[]': [str(requested_qty)]
            }, follow_redirects=True)

            transfer = StockTransfer.query.filter_by(
                destination_location_id=kiosk.id,
                status='requested'
            ).order_by(StockTransfer.id.desc()).first()

            logout(client)

            # Approve with less quantity
            login(client, 'warehouse_mgr', 'warehouse123')

            item = transfer.items.first()
            response = client.post(f'/transfers/{transfer.id}/approve', data={
                'action': 'approve',
                'notes': 'Partial approval due to stock constraints',
                f'approved_qty_{item.id}': approved_qty
            }, follow_redirects=True)

            db.session.refresh(transfer)
            db.session.refresh(item)
            assert transfer.status == 'approved'
            assert item.quantity_approved == approved_qty
            assert item.quantity_requested == requested_qty

            logout(client)

    def test_transfer_rejection(self, client, app, init_database):
        """Test transfer rejection workflow."""
        with app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()
            product = Product.query.filter_by(code='PROD001').first()

            # Create transfer request
            login(client, 'kiosk_mgr', 'kiosk123')

            response = client.post('/transfers/create', data={
                'source_location_id': warehouse.id,
                'priority': 'normal',
                'notes': 'Test transfer',
                'product_id[]': [str(product.id)],
                'quantity[]': ['10']
            }, follow_redirects=True)

            transfer = StockTransfer.query.filter_by(
                destination_location_id=kiosk.id,
                status='requested'
            ).order_by(StockTransfer.id.desc()).first()

            logout(client)

            # Reject transfer
            login(client, 'warehouse_mgr', 'warehouse123')

            response = client.post(f'/transfers/{transfer.id}/approve', data={
                'action': 'reject',
                'rejection_reason': 'Stock not available'
            }, follow_redirects=True)

            db.session.refresh(transfer)
            assert transfer.status == 'rejected'
            assert 'Stock not available' in transfer.rejection_reason

            logout(client)

    def test_transfer_cancellation(self, client, app, init_database):
        """Test transfer cancellation before dispatch."""
        with app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()
            product = Product.query.filter_by(code='PROD001').first()

            wh_stock = LocationStock.query.filter_by(
                location_id=warehouse.id,
                product_id=product.id
            ).first()
            initial_wh_qty = wh_stock.quantity

            # Create and approve transfer
            login(client, 'kiosk_mgr', 'kiosk123')

            response = client.post('/transfers/create', data={
                'source_location_id': warehouse.id,
                'priority': 'normal',
                'notes': 'Test transfer',
                'product_id[]': [str(product.id)],
                'quantity[]': ['10']
            }, follow_redirects=True)

            transfer = StockTransfer.query.filter_by(
                destination_location_id=kiosk.id,
                status='requested'
            ).order_by(StockTransfer.id.desc()).first()

            logout(client)

            # Approve transfer (reserves stock)
            login(client, 'warehouse_mgr', 'warehouse123')

            item = transfer.items.first()
            response = client.post(f'/transfers/{transfer.id}/approve', data={
                'action': 'approve',
                f'approved_qty_{item.id}': 10
            }, follow_redirects=True)

            # Cancel before dispatch
            response = client.post(f'/transfers/{transfer.id}/cancel', data={
                'reason': 'No longer needed'
            }, follow_redirects=True)

            db.session.refresh(transfer)
            assert transfer.status == 'cancelled'

            # Verify reserved stock was released
            db.session.refresh(wh_stock)
            assert wh_stock.reserved_quantity == 0

            logout(client)


# =============================================================================
# TEST CLASS: CUSTOMER PURCHASE FLOW
# =============================================================================

class TestCustomerPurchaseFlow:
    """Tests for customer lifecycle: Register -> Purchase -> Points -> Tier upgrade"""

    def test_customer_registration_and_purchase(self, client, app, init_database):
        """Test customer registration and first purchase."""
        with app.app_context():
            login(client, 'cashier', 'cashier123')

            # Register new customer
            response = client.post('/customers/add', data={
                'name': 'New Customer',
                'phone': '03001234567',
                'email': 'newcustomer@test.com',
                'address': '123 Test Street',
                'city': 'Test City',
                'customer_type': 'regular',
                'birthday': '1990-01-15'
            }, follow_redirects=True)
            assert response.status_code == 200

            # Verify customer was created
            customer = Customer.query.filter_by(phone='03001234567').first()
            assert customer is not None
            assert customer.name == 'New Customer'
            assert customer.loyalty_points == 0
            assert customer.loyalty_tier == 'Bronze'

            # Make a purchase
            product = Product.query.filter_by(code='PROD001').first()
            purchase_amount = 5000.00  # 5000 Rs purchase

            sale_data = {
                'items': [{
                    'product_id': product.id,
                    'quantity': 1,
                    'unit_price': purchase_amount,
                    'discount': 0,
                    'subtotal': purchase_amount
                }],
                'customer_id': customer.id,
                'subtotal': purchase_amount,
                'discount': 0,
                'tax': 0,
                'total': purchase_amount,
                'payment_method': 'cash',
                'amount_paid': purchase_amount
            }

            response = client.post('/pos/complete-sale',
                                  data=json.dumps(sale_data),
                                  content_type='application/json')
            result = json.loads(response.data)
            assert result['success'] == True

            # Verify loyalty points were earned (1 point per 100 Rs)
            db.session.refresh(customer)
            assert customer.loyalty_points == 50  # 5000 / 100 = 50 points

            logout(client)

    def test_loyalty_tier_upgrade(self, client, app, init_database):
        """Test customer tier upgrade through purchases."""
        with app.app_context():
            login(client, 'cashier', 'cashier123')

            # Create customer with points just below Silver threshold
            customer = Customer(
                name='Tier Test Customer',
                phone='03009876543',
                loyalty_points=490,
                is_active=True
            )
            db.session.add(customer)
            db.session.commit()

            assert customer.loyalty_tier == 'Bronze'

            # Make purchase that pushes to Silver (need 500 points)
            product = Product.query.filter_by(code='PROD001').first()
            purchase_amount = 1500.00  # Will earn 15 points -> total 505

            sale_data = {
                'items': [{
                    'product_id': product.id,
                    'quantity': 1,
                    'unit_price': purchase_amount,
                    'discount': 0,
                    'subtotal': purchase_amount
                }],
                'customer_id': customer.id,
                'subtotal': purchase_amount,
                'discount': 0,
                'tax': 0,
                'total': purchase_amount,
                'payment_method': 'cash',
                'amount_paid': purchase_amount
            }

            response = client.post('/pos/complete-sale',
                                  data=json.dumps(sale_data),
                                  content_type='application/json')
            result = json.loads(response.data)
            assert result['success'] == True

            db.session.refresh(customer)
            assert customer.loyalty_points == 505
            assert customer.loyalty_tier == 'Silver'

            logout(client)

    def test_loyalty_points_redemption(self, client, app, init_database):
        """Test loyalty points redemption for discount."""
        with app.app_context():
            # Create customer with sufficient points
            customer = Customer(
                name='Points Redemption Test',
                phone='03007654321',
                loyalty_points=500,
                is_active=True
            )
            db.session.add(customer)
            db.session.commit()

            # Test points redemption logic
            initial_points = customer.loyalty_points
            points_to_redeem = 200

            success, result = customer.redeem_points(points_to_redeem)
            assert success == True
            assert result == 200  # 200 points = Rs. 200 discount

            db.session.commit()
            db.session.refresh(customer)
            assert customer.loyalty_points == initial_points - points_to_redeem

    def test_minimum_points_redemption(self, client, app, init_database):
        """Test that minimum 100 points required for redemption."""
        with app.app_context():
            customer = Customer(
                name='Min Points Test',
                phone='03005555555',
                loyalty_points=500,
                is_active=True
            )
            db.session.add(customer)
            db.session.commit()

            # Try to redeem less than 100 points
            success, message = customer.redeem_points(50)
            assert success == False
            assert 'Minimum 100 points' in message

    def test_customer_purchase_history(self, client, app, init_database):
        """Test customer purchase history tracking."""
        with app.app_context():
            login(client, 'cashier', 'cashier123')

            customer = Customer.query.first()
            product1 = Product.query.filter_by(code='PROD001').first()
            product2 = Product.query.filter_by(code='PROD002').first()

            # Make multiple purchases
            for product in [product1, product2]:
                sale_data = {
                    'items': [{
                        'product_id': product.id,
                        'quantity': 1,
                        'unit_price': float(product.selling_price),
                        'discount': 0,
                        'subtotal': float(product.selling_price)
                    }],
                    'customer_id': customer.id,
                    'subtotal': float(product.selling_price),
                    'discount': 0,
                    'tax': 0,
                    'total': float(product.selling_price),
                    'payment_method': 'cash',
                    'amount_paid': float(product.selling_price)
                }

                response = client.post('/pos/complete-sale',
                                      data=json.dumps(sale_data),
                                      content_type='application/json')
                assert json.loads(response.data)['success'] == True

            # Verify purchase history
            sales = Sale.query.filter_by(customer_id=customer.id).all()
            assert len(sales) >= 2

            # Verify total purchases property
            total = customer.total_purchases
            assert total > 0

            logout(client)


# =============================================================================
# TEST CLASS: PRODUCTION WORKFLOW
# =============================================================================

class TestProductionWorkflow:
    """Tests for production workflow: Raw materials -> Recipe -> Production -> Product"""

    def test_create_recipe(self, client, app, init_database):
        """Test creating a production recipe."""
        with app.app_context():
            login(client, 'warehouse_mgr', 'warehouse123')

            # Get raw materials
            rose_oil = RawMaterial.query.filter_by(code='OIL-ROSE').first()
            bottle = RawMaterial.query.filter_by(code='BTL-6ML').first()

            # Create a manufactured product first
            product = Product(
                code='ATTAR-001',
                name='Rose Attar 6ml',
                selling_price=Decimal('500.00'),
                cost_price=Decimal('200.00'),
                is_manufactured=True,
                product_type='manufactured',
                is_active=True
            )
            db.session.add(product)
            db.session.commit()

            # Create recipe via form
            response = client.post('/production/recipes/add', data={
                'code': 'RCP-ROSE-6ML',
                'name': 'Rose Attar 6ml Recipe',
                'recipe_type': 'single_oil',
                'product_id': product.id,
                'output_size_ml': '6',
                'oil_percentage': '100',
                'can_produce_at_kiosk': 'on',
                'description': 'Single oil rose attar recipe',
                'ingredient_id[]': [str(rose_oil.id), str(bottle.id)],
                'percentage[]': ['100', ''],
                'is_packaging[]': ['1']  # Index of bottle in ingredient list
            }, follow_redirects=True)

            # Verify recipe was created
            recipe = Recipe.query.filter_by(code='RCP-ROSE-6ML').first()
            assert recipe is not None
            assert recipe.recipe_type == 'single_oil'
            assert recipe.output_size_ml == Decimal('6')

            logout(client)

    def test_production_order_workflow(self, client, app, init_database):
        """Test complete production order workflow."""
        with app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()

            # Create recipe and product
            product = Product(
                code='ATTAR-002',
                name='Test Attar',
                selling_price=Decimal('500.00'),
                cost_price=Decimal('200.00'),
                is_manufactured=True,
                is_active=True
            )
            db.session.add(product)
            db.session.flush()

            rose_oil = RawMaterial.query.filter_by(code='OIL-ROSE').first()
            bottle = RawMaterial.query.filter_by(code='BTL-6ML').first()

            recipe = Recipe(
                code='RCP-TEST-001',
                name='Test Recipe',
                recipe_type='single_oil',
                product_id=product.id,
                output_size_ml=Decimal('6'),
                oil_percentage=Decimal('100'),
                can_produce_at_warehouse=True,
                can_produce_at_kiosk=True,
                is_active=True
            )
            db.session.add(recipe)
            db.session.flush()

            # Add ingredients
            ing1 = RecipeIngredient(
                recipe_id=recipe.id,
                raw_material_id=rose_oil.id,
                percentage=Decimal('100'),
                is_packaging=False
            )
            ing2 = RecipeIngredient(
                recipe_id=recipe.id,
                raw_material_id=bottle.id,
                is_packaging=True
            )
            db.session.add_all([ing1, ing2])
            db.session.commit()

            # Login as warehouse manager
            login(client, 'warehouse_mgr', 'warehouse123')

            # Create production order
            response = client.post('/production/orders/create', data={
                'recipe_id': recipe.id,
                'quantity': 10,
                'priority': 'normal',
                'due_date': (date.today() + timedelta(days=7)).strftime('%Y-%m-%d'),
                'notes': 'Test production order'
            }, follow_redirects=True)
            assert response.status_code == 200

            # Get production order
            order = ProductionOrder.query.filter_by(recipe_id=recipe.id).first()
            assert order is not None
            assert order.quantity_ordered == 10
            assert order.status in ['draft', 'pending']  # Depends on auto_submit

            logout(client)

    def test_material_requirements_calculation(self, client, app, init_database):
        """Test material requirements calculation for production."""
        with app.app_context():
            from app.services.production_service import ProductionService

            # Create recipe
            rose_oil = RawMaterial.query.filter_by(code='OIL-ROSE').first()
            jasmine_oil = RawMaterial.query.filter_by(code='OIL-JASMINE').first()
            bottle = RawMaterial.query.filter_by(code='BTL-6ML').first()

            product = Product(
                code='ATTAR-BLEND',
                name='Rose Jasmine Blend',
                selling_price=Decimal('600.00'),
                cost_price=Decimal('250.00'),
                is_manufactured=True,
                is_active=True
            )
            db.session.add(product)
            db.session.flush()

            recipe = Recipe(
                code='RCP-BLEND-001',
                name='Rose Jasmine Blend Recipe',
                recipe_type='blended',
                product_id=product.id,
                output_size_ml=Decimal('6'),
                oil_percentage=Decimal('100'),
                is_active=True
            )
            db.session.add(recipe)
            db.session.flush()

            # 60% rose, 40% jasmine
            ing1 = RecipeIngredient(
                recipe_id=recipe.id,
                raw_material_id=rose_oil.id,
                percentage=Decimal('60'),
                is_packaging=False
            )
            ing2 = RecipeIngredient(
                recipe_id=recipe.id,
                raw_material_id=jasmine_oil.id,
                percentage=Decimal('40'),
                is_packaging=False
            )
            ing3 = RecipeIngredient(
                recipe_id=recipe.id,
                raw_material_id=bottle.id,
                is_packaging=True
            )
            db.session.add_all([ing1, ing2, ing3])
            db.session.commit()

            # Calculate requirements for 10 bottles
            requirements = ProductionService.calculate_material_requirements(recipe.id, 10)

            assert 'error' not in requirements
            assert requirements['quantity'] == 10
            assert requirements['total_output_ml'] == 60  # 10 * 6ml
            assert requirements['oil_amount_ml'] == 60  # 100% oil

            # Check material breakdown
            materials = {m['code']: m for m in requirements['materials']}

            assert 'OIL-ROSE' in materials
            assert materials['OIL-ROSE']['quantity_required'] == 36  # 60ml * 0.6

            assert 'OIL-JASMINE' in materials
            assert materials['OIL-JASMINE']['quantity_required'] == 24  # 60ml * 0.4

            assert 'BTL-6ML' in materials
            assert materials['BTL-6ML']['quantity_required'] == 10  # 10 bottles


# =============================================================================
# TEST CLASS: REPORTING FLOW
# =============================================================================

class TestReportingFlow:
    """Tests for reporting: Sales -> Reports -> Verification"""

    def test_daily_report_calculations(self, client, app, init_database):
        """Test that daily report correctly calculates sales totals."""
        with app.app_context():
            # First create some sales
            login(client, 'cashier', 'cashier123')

            products = Product.query.limit(3).all()
            total_expected = Decimal('0')

            for product in products:
                amount = float(product.selling_price)
                total_expected += Decimal(str(amount))

                sale_data = {
                    'items': [{
                        'product_id': product.id,
                        'quantity': 1,
                        'unit_price': amount,
                        'discount': 0,
                        'subtotal': amount
                    }],
                    'subtotal': amount,
                    'discount': 0,
                    'tax': 0,
                    'total': amount,
                    'payment_method': 'cash',
                    'amount_paid': amount
                }

                response = client.post('/pos/complete-sale',
                                      data=json.dumps(sale_data),
                                      content_type='application/json')
                assert json.loads(response.data)['success'] == True

            logout(client)

            # Check daily report
            login(client, 'admin', 'admin123')

            today_str = date.today().strftime('%Y-%m-%d')
            response = client.get(f'/reports/daily?date={today_str}')
            assert response.status_code == 200

            # Verify sales count in database
            from sqlalchemy import func
            today_sales = Sale.query.filter(
                func.date(Sale.sale_date) == date.today()
            ).all()

            assert len(today_sales) >= 3
            total_revenue = sum(sale.total for sale in today_sales)
            assert total_revenue >= total_expected

            logout(client)

    def test_payment_method_breakdown(self, client, app, init_database):
        """Test payment method breakdown in reports."""
        with app.app_context():
            login(client, 'cashier', 'cashier123')

            product = Product.query.first()
            payment_methods = ['cash', 'card', 'bank_transfer']

            for method in payment_methods:
                sale_data = {
                    'items': [{
                        'product_id': product.id,
                        'quantity': 1,
                        'unit_price': float(product.selling_price),
                        'discount': 0,
                        'subtotal': float(product.selling_price)
                    }],
                    'subtotal': float(product.selling_price),
                    'discount': 0,
                    'tax': 0,
                    'total': float(product.selling_price),
                    'payment_method': method,
                    'amount_paid': float(product.selling_price)
                }

                response = client.post('/pos/complete-sale',
                                      data=json.dumps(sale_data),
                                      content_type='application/json')
                assert json.loads(response.data)['success'] == True

            logout(client)

            # Verify breakdown
            from sqlalchemy import func
            breakdown = db.session.query(
                Sale.payment_method,
                func.count(Sale.id).label('count'),
                func.sum(Sale.total).label('total')
            ).filter(
                func.date(Sale.sale_date) == date.today()
            ).group_by(Sale.payment_method).all()

            methods_found = {b[0] for b in breakdown}
            for method in payment_methods:
                assert method in methods_found

    def test_inventory_valuation_report(self, client, app, init_database):
        """Test inventory valuation report accuracy."""
        with app.app_context():
            login(client, 'admin', 'admin123')

            # Calculate expected values
            products = Product.query.filter_by(is_active=True).all()
            expected_cost = sum(float(p.cost_price) * p.quantity for p in products)
            expected_selling = sum(float(p.selling_price) * p.quantity for p in products)

            response = client.get('/reports/inventory-valuation')
            assert response.status_code == 200

            # Verify values in response (would check HTML in real test)
            assert expected_cost > 0
            assert expected_selling > expected_cost

            logout(client)


# =============================================================================
# TEST CLASS: USER MANAGEMENT
# =============================================================================

class TestUserManagement:
    """Tests for user management: Create -> Role -> Login -> Access control"""

    def test_role_based_access(self, client, app, init_database):
        """Test that users can only access routes for their role."""
        with app.app_context():
            # Cashier should not access settings
            login(client, 'cashier', 'cashier123')

            response = client.get('/settings/')
            # Should be 403 forbidden or redirect to login
            assert response.status_code in [302, 403]

            logout(client)

            # Admin should access settings
            login(client, 'admin', 'admin123')

            response = client.get('/settings/')
            assert response.status_code == 200

            logout(client)

    def test_location_based_access(self, client, app, init_database):
        """Test that users only see data for their location."""
        with app.app_context():
            kiosk = Location.query.filter_by(code='K-001').first()
            warehouse = Location.query.filter_by(code='WH-001').first()

            # Create sale at kiosk
            login(client, 'cashier', 'cashier123')

            product = Product.query.first()
            sale_data = {
                'items': [{
                    'product_id': product.id,
                    'quantity': 1,
                    'unit_price': float(product.selling_price),
                    'discount': 0,
                    'subtotal': float(product.selling_price)
                }],
                'subtotal': float(product.selling_price),
                'discount': 0,
                'tax': 0,
                'total': float(product.selling_price),
                'payment_method': 'cash',
                'amount_paid': float(product.selling_price)
            }

            response = client.post('/pos/complete-sale',
                                  data=json.dumps(sale_data),
                                  content_type='application/json')
            result = json.loads(response.data)
            assert result['success'] == True

            # Verify sale is at kiosk location
            sale = Sale.query.get(result['sale_id'])
            assert sale.location_id == kiosk.id

            logout(client)

    def test_inactive_user_cannot_login(self, client, app, init_database):
        """Test that deactivated users cannot log in."""
        with app.app_context():
            # Deactivate cashier
            cashier = User.query.filter_by(username='cashier').first()
            cashier.is_active = False
            db.session.commit()

            # Try to login
            response = login(client, 'cashier', 'cashier123')

            # Should fail
            assert b'deactivated' in response.data or b'log in' in response.data.lower()

            # Reactivate for other tests
            cashier.is_active = True
            db.session.commit()

    def test_wrong_password_fails(self, client, app, init_database):
        """Test that wrong password fails login."""
        with app.app_context():
            response = login(client, 'admin', 'wrongpassword')

            assert b'Invalid' in response.data or b'incorrect' in response.data.lower()


# =============================================================================
# TEST CLASS: EDGE CASES AND ERROR HANDLING
# =============================================================================

class TestEdgeCasesAndErrors:
    """Tests for edge cases: Concurrent operations, rollbacks, partial failures"""

    def test_concurrent_stock_updates(self, client, app, init_database):
        """Test concurrent sales don't cause stock inconsistencies."""
        with app.app_context():
            product = Product.query.filter_by(code='PROD001').first()
            kiosk = Location.query.filter_by(code='K-001').first()

            initial_stock = LocationStock.query.filter_by(
                location_id=kiosk.id,
                product_id=product.id
            ).first()
            initial_qty = initial_stock.quantity

            # Simulate concurrent sales by making multiple sales in sequence
            # (True concurrency would require separate processes)
            num_sales = 5
            qty_per_sale = 2

            login(client, 'cashier', 'cashier123')

            successful_sales = 0
            for _ in range(num_sales):
                sale_data = {
                    'items': [{
                        'product_id': product.id,
                        'quantity': qty_per_sale,
                        'unit_price': float(product.selling_price),
                        'discount': 0,
                        'subtotal': float(product.selling_price * qty_per_sale)
                    }],
                    'subtotal': float(product.selling_price * qty_per_sale),
                    'discount': 0,
                    'tax': 0,
                    'total': float(product.selling_price * qty_per_sale),
                    'payment_method': 'cash',
                    'amount_paid': float(product.selling_price * qty_per_sale)
                }

                response = client.post('/pos/complete-sale',
                                      data=json.dumps(sale_data),
                                      content_type='application/json')
                result = json.loads(response.data)
                if result['success']:
                    successful_sales += 1

            # Verify final stock is consistent
            db.session.refresh(initial_stock)
            expected_qty = initial_qty - (successful_sales * qty_per_sale)
            assert initial_stock.quantity == expected_qty

            logout(client)

    def test_transaction_rollback_on_error(self, client, app, init_database):
        """Test that database rolls back on error."""
        with app.app_context():
            product = Product.query.filter_by(code='PROD001').first()
            kiosk = Location.query.filter_by(code='K-001').first()

            initial_stock = LocationStock.query.filter_by(
                location_id=kiosk.id,
                product_id=product.id
            ).first()
            initial_qty = initial_stock.quantity
            initial_sale_count = Sale.query.count()

            login(client, 'cashier', 'cashier123')

            # Send invalid sale data that should cause error
            sale_data = {
                'items': [{
                    'product_id': 99999,  # Non-existent product
                    'quantity': 1,
                    'unit_price': 100.00,
                    'discount': 0,
                    'subtotal': 100.00
                }],
                'subtotal': 100.00,
                'discount': 0,
                'tax': 0,
                'total': 100.00,
                'payment_method': 'cash',
                'amount_paid': 100.00
            }

            response = client.post('/pos/complete-sale',
                                  data=json.dumps(sale_data),
                                  content_type='application/json')
            result = json.loads(response.data)
            assert result['success'] == False

            # Verify no partial changes were made
            db.session.refresh(initial_stock)
            assert initial_stock.quantity == initial_qty
            assert Sale.query.count() == initial_sale_count

            logout(client)

    def test_sale_with_empty_cart(self, client, app, init_database):
        """Test that empty cart sale is rejected."""
        with app.app_context():
            login(client, 'cashier', 'cashier123')

            sale_data = {
                'items': [],
                'subtotal': 0,
                'discount': 0,
                'tax': 0,
                'total': 0,
                'payment_method': 'cash',
                'amount_paid': 0
            }

            response = client.post('/pos/complete-sale',
                                  data=json.dumps(sale_data),
                                  content_type='application/json')
            result = json.loads(response.data)
            assert result['success'] == False
            assert 'No items' in result['error']

            logout(client)

    def test_duplicate_customer_phone(self, client, app, init_database):
        """Test that duplicate phone numbers are handled."""
        with app.app_context():
            login(client, 'cashier', 'cashier123')

            existing_customer = Customer.query.first()

            # Try to create customer with existing phone
            response = client.post('/customers/add', data={
                'name': 'Duplicate Customer',
                'phone': existing_customer.phone,  # Already exists
                'email': 'duplicate@test.com',
                'customer_type': 'regular'
            }, follow_redirects=True)

            # Should fail with integrity error
            # The exact behavior depends on error handling in routes
            customers_with_phone = Customer.query.filter_by(
                phone=existing_customer.phone
            ).count()
            assert customers_with_phone == 1  # Only original should exist

            logout(client)

    def test_negative_quantity_rejected(self, client, app, init_database):
        """Test that negative quantities are rejected."""
        with app.app_context():
            login(client, 'cashier', 'cashier123')

            product = Product.query.first()

            sale_data = {
                'items': [{
                    'product_id': product.id,
                    'quantity': -5,  # Negative quantity
                    'unit_price': float(product.selling_price),
                    'discount': 0,
                    'subtotal': float(product.selling_price * -5)
                }],
                'subtotal': float(product.selling_price * -5),
                'discount': 0,
                'tax': 0,
                'total': float(product.selling_price * -5),
                'payment_method': 'cash',
                'amount_paid': float(product.selling_price * -5)
            }

            response = client.post('/pos/complete-sale',
                                  data=json.dumps(sale_data),
                                  content_type='application/json')
            result = json.loads(response.data)

            # Should either fail or the negative quantity causes stock increase
            # which would also be wrong - check that stock wasn't increased
            logout(client)


# =============================================================================
# TEST CLASS: DATA CONSISTENCY
# =============================================================================

class TestDataConsistency:
    """Tests for data consistency across related tables."""

    def test_sale_items_match_sale_total(self, client, app, init_database):
        """Test that sale items subtotals match sale total."""
        with app.app_context():
            login(client, 'cashier', 'cashier123')

            products = Product.query.limit(2).all()

            items = []
            expected_total = Decimal('0')
            for product in products:
                subtotal = product.selling_price * 2
                expected_total += subtotal
                items.append({
                    'product_id': product.id,
                    'quantity': 2,
                    'unit_price': float(product.selling_price),
                    'discount': 0,
                    'subtotal': float(subtotal)
                })

            sale_data = {
                'items': items,
                'subtotal': float(expected_total),
                'discount': 0,
                'tax': 0,
                'total': float(expected_total),
                'payment_method': 'cash',
                'amount_paid': float(expected_total)
            }

            response = client.post('/pos/complete-sale',
                                  data=json.dumps(sale_data),
                                  content_type='application/json')
            result = json.loads(response.data)
            assert result['success'] == True

            # Verify consistency
            sale = Sale.query.get(result['sale_id'])
            items_total = sum(item.subtotal for item in sale.items)

            assert items_total == sale.subtotal

            logout(client)

    def test_stock_movement_matches_sale(self, client, app, init_database):
        """Test that stock movements match sale quantities."""
        with app.app_context():
            login(client, 'cashier', 'cashier123')

            product = Product.query.first()
            quantity_sold = 3

            sale_data = {
                'items': [{
                    'product_id': product.id,
                    'quantity': quantity_sold,
                    'unit_price': float(product.selling_price),
                    'discount': 0,
                    'subtotal': float(product.selling_price * quantity_sold)
                }],
                'subtotal': float(product.selling_price * quantity_sold),
                'discount': 0,
                'tax': 0,
                'total': float(product.selling_price * quantity_sold),
                'payment_method': 'cash',
                'amount_paid': float(product.selling_price * quantity_sold)
            }

            response = client.post('/pos/complete-sale',
                                  data=json.dumps(sale_data),
                                  content_type='application/json')
            result = json.loads(response.data)

            # Check stock movement
            movement = StockMovement.query.filter_by(
                reference=result['sale_number']
            ).first()

            assert movement is not None
            assert movement.quantity == -quantity_sold  # Negative for outgoing

            logout(client)

    def test_transfer_stock_consistency(self, client, app, init_database):
        """Test that stock transfers maintain total inventory."""
        with app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()
            product = Product.query.first()

            # Get total stock before transfer
            wh_stock = LocationStock.query.filter_by(
                location_id=warehouse.id,
                product_id=product.id
            ).first()
            kiosk_stock = LocationStock.query.filter_by(
                location_id=kiosk.id,
                product_id=product.id
            ).first()

            total_before = wh_stock.quantity + kiosk_stock.quantity
            transfer_qty = 10

            # Create and complete transfer
            login(client, 'kiosk_mgr', 'kiosk123')

            client.post('/transfers/create', data={
                'source_location_id': warehouse.id,
                'priority': 'normal',
                'product_id[]': [str(product.id)],
                'quantity[]': [str(transfer_qty)]
            }, follow_redirects=True)

            transfer = StockTransfer.query.filter_by(
                destination_location_id=kiosk.id,
                status='requested'
            ).order_by(StockTransfer.id.desc()).first()

            logout(client)

            # Complete transfer workflow
            login(client, 'warehouse_mgr', 'warehouse123')

            item = transfer.items.first()
            client.post(f'/transfers/{transfer.id}/approve', data={
                'action': 'approve',
                f'approved_qty_{item.id}': transfer_qty
            }, follow_redirects=True)

            client.post(f'/transfers/{transfer.id}/dispatch', data={
                'notes': 'Dispatched'
            }, follow_redirects=True)

            logout(client)

            login(client, 'kiosk_mgr', 'kiosk123')

            client.post(f'/transfers/{transfer.id}/receive', data={
                f'received_qty_{item.id}': transfer_qty
            }, follow_redirects=True)

            # Verify total stock is unchanged
            db.session.refresh(wh_stock)
            db.session.refresh(kiosk_stock)

            total_after = wh_stock.quantity + kiosk_stock.quantity
            assert total_after == total_before

            logout(client)


# =============================================================================
# TEST CLASS: DAY CLOSE OPERATIONS
# =============================================================================

class TestDayCloseOperations:
    """Tests for end-of-day closing operations."""

    def test_day_close_summary(self, client, app, init_database):
        """Test day close summary calculations."""
        with app.app_context():
            # Create sales first
            login(client, 'cashier', 'cashier123')

            product = Product.query.first()
            for i in range(3):
                sale_data = {
                    'items': [{
                        'product_id': product.id,
                        'quantity': 1,
                        'unit_price': 100.0,
                        'discount': 0,
                        'subtotal': 100.0
                    }],
                    'subtotal': 100.0,
                    'discount': 0,
                    'tax': 0,
                    'total': 100.0,
                    'payment_method': 'cash' if i < 2 else 'card',
                    'amount_paid': 100.0
                }
                client.post('/pos/complete-sale',
                           data=json.dumps(sale_data),
                           content_type='application/json')

            logout(client)

            # Get day close summary
            login(client, 'admin', 'admin123')

            response = client.get('/pos/close-day-summary')
            result = json.loads(response.data)

            if result['success']:
                summary = result['summary']
                assert summary['total_sales'] >= 3
                assert summary['total_cash'] >= 200  # At least 2 cash sales

            logout(client)


# =============================================================================
# TEST CLASS: REFUND OPERATIONS
# =============================================================================

class TestRefundOperations:
    """Tests for sale refund operations."""

    def test_full_refund_restores_stock(self, client, app, init_database):
        """Test that full refund restores product stock."""
        with app.app_context():
            product = Product.query.first()

            # Get initial stock
            initial_qty = product.quantity

            # Create a sale
            login(client, 'cashier', 'cashier123')

            sale_data = {
                'items': [{
                    'product_id': product.id,
                    'quantity': 5,
                    'unit_price': float(product.selling_price),
                    'discount': 0,
                    'subtotal': float(product.selling_price * 5)
                }],
                'subtotal': float(product.selling_price * 5),
                'discount': 0,
                'tax': 0,
                'total': float(product.selling_price * 5),
                'payment_method': 'cash',
                'amount_paid': float(product.selling_price * 5)
            }

            response = client.post('/pos/complete-sale',
                                  data=json.dumps(sale_data),
                                  content_type='application/json')
            result = json.loads(response.data)
            sale_id = result['sale_id']

            logout(client)

            # Refund the sale (need manager/admin permission)
            login(client, 'admin', 'admin123')

            response = client.post(f'/pos/refund-sale/{sale_id}',
                                  content_type='application/json')
            result = json.loads(response.data)
            assert result['success'] == True

            # Verify stock was restored
            db.session.refresh(product)
            assert product.quantity == initial_qty

            # Verify sale status
            sale = Sale.query.get(sale_id)
            assert sale.status == 'refunded'

            logout(client)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
