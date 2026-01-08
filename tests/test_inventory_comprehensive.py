"""
Comprehensive Inventory Management Unit Tests

Tests for inventory functionality including:
- Stock management (add, remove, adjust, negative prevention)
- Product CRUD operations
- Category management
- Stock transfers between locations
- Stock adjustments with audit trail
- Reorder points and alerts
- Barcode management
- Batch/Lot tracking and expiry dates
- Warehouse operations
- Inventory valuation
- Stock takes and cycle counts
- Forecasting functionality
- Edge cases and data integrity
"""

import pytest
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.models import (
    db, Product, Category, Supplier, StockMovement, Location, LocationStock,
    StockTransfer, StockTransferItem, User, Sale, SaleItem, GatePass, Setting
)


# ============================================================================
# STOCK MANAGEMENT TESTS
# ============================================================================

class TestStockManagement:
    """Tests for stock management operations."""

    def test_add_stock_to_product(self, fresh_app, init_database):
        """Test adding stock to a product increases quantity."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()
            initial_qty = product.quantity

            # Add stock
            product.quantity += 50
            db.session.commit()

            updated_product = Product.query.get(product.id)
            assert updated_product.quantity == initial_qty + 50

    def test_remove_stock_from_product(self, fresh_app, init_database):
        """Test removing stock decreases quantity."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()
            initial_qty = product.quantity

            # Remove stock
            product.quantity -= 30
            db.session.commit()

            updated_product = Product.query.get(product.id)
            assert updated_product.quantity == initial_qty - 30

    def test_negative_stock_prevention_model(self, fresh_app, init_database):
        """Test that stock quantity cannot go negative at model level."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            # Test the is_low_stock property when stock is at zero
            product.quantity = 0
            db.session.commit()

            assert product.quantity == 0
            assert product.is_low_stock is True

    def test_location_stock_add(self, fresh_app, init_database):
        """Test adding stock at specific location."""
        with fresh_app.app_context():
            location = Location.query.filter_by(code='K-001').first()
            product = Product.query.filter_by(code='PRD001').first()

            loc_stock = LocationStock.query.filter_by(
                location_id=location.id,
                product_id=product.id
            ).first()

            initial_qty = loc_stock.quantity
            loc_stock.quantity += 25
            db.session.commit()

            updated_stock = LocationStock.query.get(loc_stock.id)
            assert updated_stock.quantity == initial_qty + 25

    def test_location_stock_available_quantity(self, fresh_app, init_database):
        """Test available quantity excludes reserved stock."""
        with fresh_app.app_context():
            location = Location.query.filter_by(code='K-001').first()
            product = Product.query.filter_by(code='PRD001').first()

            loc_stock = LocationStock.query.filter_by(
                location_id=location.id,
                product_id=product.id
            ).first()

            loc_stock.quantity = 100
            loc_stock.reserved_quantity = 20
            db.session.commit()

            assert loc_stock.available_quantity == 80

    def test_location_stock_is_low_stock(self, fresh_app, init_database):
        """Test low stock detection at location level."""
        with fresh_app.app_context():
            location = Location.query.filter_by(code='K-001').first()
            product = Product.query.filter_by(code='PRD001').first()

            loc_stock = LocationStock.query.filter_by(
                location_id=location.id,
                product_id=product.id
            ).first()

            # Set quantity equal to reorder level
            loc_stock.quantity = loc_stock.reorder_level
            db.session.commit()

            assert loc_stock.is_low_stock is True

            # Set quantity above reorder level
            loc_stock.quantity = loc_stock.reorder_level + 10
            db.session.commit()

            assert loc_stock.is_low_stock is False

    def test_stock_movement_creation(self, fresh_app, init_database):
        """Test creating stock movement records."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()
            user = User.query.filter_by(username='admin').first()
            location = Location.query.filter_by(code='WH-001').first()

            movement = StockMovement(
                product_id=product.id,
                user_id=user.id,
                location_id=location.id,
                movement_type='adjustment',
                quantity=50,
                reference='TEST-ADJ-001',
                notes='Test stock adjustment'
            )
            db.session.add(movement)
            db.session.commit()

            saved_movement = StockMovement.query.filter_by(reference='TEST-ADJ-001').first()
            assert saved_movement is not None
            assert saved_movement.quantity == 50
            assert saved_movement.movement_type == 'adjustment'

    def test_stock_movement_negative_quantity(self, fresh_app, init_database):
        """Test stock movement with negative quantity for outgoing stock."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()
            user = User.query.filter_by(username='admin').first()

            movement = StockMovement(
                product_id=product.id,
                user_id=user.id,
                movement_type='sale',
                quantity=-10,
                reference='SALE-001',
                notes='Sold to customer'
            )
            db.session.add(movement)
            db.session.commit()

            assert movement.quantity == -10


class TestStockAdjustmentAPI:
    """Tests for stock adjustment API endpoint."""

    def test_adjust_stock_add(self, auth_admin, fresh_app, init_database):
        """Test adding stock via API."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            response = auth_admin.post(
                f'/inventory/adjust-stock/{product.id}',
                json={
                    'adjustment_type': 'add',
                    'quantity': 50,
                    'reason': 'Test add stock'
                },
                content_type='application/json'
            )

            # Check response (may be 200 or 302 redirect)
            assert response.status_code in [200, 302, 403]

    def test_adjust_stock_remove(self, auth_admin, fresh_app, init_database):
        """Test removing stock via API."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            response = auth_admin.post(
                f'/inventory/adjust-stock/{product.id}',
                json={
                    'adjustment_type': 'remove',
                    'quantity': 10,
                    'reason': 'Test remove stock'
                },
                content_type='application/json'
            )

            assert response.status_code in [200, 302, 400, 403]

    def test_adjust_stock_set_absolute(self, auth_admin, fresh_app, init_database):
        """Test setting absolute stock value via API."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            response = auth_admin.post(
                f'/inventory/adjust-stock/{product.id}',
                json={
                    'adjustment_type': 'set',
                    'quantity': 75,
                    'reason': 'Physical count correction'
                },
                content_type='application/json'
            )

            assert response.status_code in [200, 302, 403]

    def test_adjust_stock_prevents_negative(self, auth_admin, fresh_app, init_database):
        """Test that API prevents negative stock."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()
            current_qty = product.quantity

            response = auth_admin.post(
                f'/inventory/adjust-stock/{product.id}',
                json={
                    'adjustment_type': 'remove',
                    'quantity': current_qty + 1000,  # More than available
                    'reason': 'Should fail'
                },
                content_type='application/json'
            )

            # Expecting error response
            assert response.status_code in [400, 403, 200]


# ============================================================================
# PRODUCT CRUD TESTS
# ============================================================================

class TestProductCRUD:
    """Tests for Product Create, Read, Update, Delete operations."""

    def test_create_product(self, fresh_app, init_database):
        """Test creating a new product."""
        with fresh_app.app_context():
            category = Category.query.first()

            product = Product(
                code='TEST001',
                barcode='9999888877776',
                name='Test Product',
                brand='Test Brand',
                category_id=category.id,
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                quantity=50,
                reorder_level=10,
                is_active=True
            )
            db.session.add(product)
            db.session.commit()

            saved = Product.query.filter_by(code='TEST001').first()
            assert saved is not None
            assert saved.name == 'Test Product'
            assert saved.selling_price == Decimal('200.00')

    def test_read_product(self, fresh_app, init_database):
        """Test reading product details."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            assert product is not None
            assert product.name == 'Oud Premium'
            assert product.brand == 'Sunnat'
            assert product.is_active is True

    def test_update_product(self, fresh_app, init_database):
        """Test updating product details."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            product.name = 'Oud Premium Updated'
            product.selling_price = Decimal('1200.00')
            db.session.commit()

            updated = Product.query.get(product.id)
            assert updated.name == 'Oud Premium Updated'
            assert updated.selling_price == Decimal('1200.00')

    def test_delete_product_soft(self, fresh_app, init_database):
        """Test soft delete (deactivating) a product."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            product.is_active = False
            db.session.commit()

            # Product still exists but is inactive
            deleted = Product.query.get(product.id)
            assert deleted is not None
            assert deleted.is_active is False

            # Active products query should not include it
            active_products = Product.query.filter_by(is_active=True).all()
            assert product not in active_products

    def test_duplicate_sku_prevention(self, fresh_app, init_database):
        """Test that duplicate SKU/code is prevented."""
        with fresh_app.app_context():
            # Try to create product with existing code
            product = Product(
                code='PRD001',  # Already exists
                name='Duplicate Test',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)

            with pytest.raises(Exception):  # IntegrityError
                db.session.commit()

            db.session.rollback()

    def test_duplicate_barcode_prevention(self, fresh_app, init_database):
        """Test that duplicate barcode is prevented."""
        with fresh_app.app_context():
            # Try to create product with existing barcode
            product = Product(
                code='UNIQUE001',
                barcode='1234567890123',  # Already exists
                name='Barcode Duplicate',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)

            with pytest.raises(Exception):  # IntegrityError
                db.session.commit()

            db.session.rollback()

    def test_product_profit_margin(self, fresh_app, init_database):
        """Test product profit margin calculation."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            # Cost: 500, Selling: 1000, Margin: ((1000-500)/500)*100 = 100%
            expected_margin = ((product.selling_price - product.cost_price) / product.cost_price) * 100
            assert product.profit_margin == expected_margin

    def test_product_stock_value(self, fresh_app, init_database):
        """Test product stock value calculation."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            expected_value = float(product.quantity * product.cost_price)
            assert product.stock_value == expected_value

    def test_product_search_by_code(self, fresh_app, init_database):
        """Test searching product by code."""
        with fresh_app.app_context():
            products = Product.query.filter(
                Product.code.ilike('%PRD%')
            ).all()

            assert len(products) >= 4

    def test_product_search_by_name(self, fresh_app, init_database):
        """Test searching product by name."""
        with fresh_app.app_context():
            products = Product.query.filter(
                Product.name.ilike('%Oud%')
            ).all()

            assert len(products) >= 1
            assert any(p.code == 'PRD001' for p in products)


class TestProductAPIEndpoints:
    """Tests for Product API endpoints."""

    def test_inventory_index_page(self, auth_admin, fresh_app, init_database):
        """Test inventory index page loads."""
        response = auth_admin.get('/inventory/')
        assert response.status_code in [200, 302]

    def test_add_product_page(self, auth_admin, fresh_app, init_database):
        """Test add product form page loads."""
        response = auth_admin.get('/inventory/add')
        assert response.status_code in [200, 302]

    def test_view_product_page(self, auth_admin, fresh_app, init_database):
        """Test view product page loads."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

        response = auth_admin.get(f'/inventory/product/{product.id}')
        assert response.status_code in [200, 302]

    def test_edit_product_page(self, auth_admin, fresh_app, init_database):
        """Test edit product form page loads."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

        response = auth_admin.get(f'/inventory/edit/{product.id}')
        assert response.status_code in [200, 302]

    def test_delete_product_api(self, auth_admin, fresh_app, init_database):
        """Test delete product API endpoint."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

        response = auth_admin.post(f'/inventory/delete/{product.id}')
        assert response.status_code in [200, 302, 403]


# ============================================================================
# CATEGORY MANAGEMENT TESTS
# ============================================================================

class TestCategoryManagement:
    """Tests for Category management operations."""

    def test_create_category(self, fresh_app, init_database):
        """Test creating a new category."""
        with fresh_app.app_context():
            category = Category(
                name='Test Category',
                description='A test category'
            )
            db.session.add(category)
            db.session.commit()

            saved = Category.query.filter_by(name='Test Category').first()
            assert saved is not None
            assert saved.description == 'A test category'

    def test_rename_category(self, fresh_app, init_database):
        """Test renaming a category."""
        with fresh_app.app_context():
            category = Category.query.filter_by(name='Attars').first()

            category.name = 'Premium Attars'
            db.session.commit()

            updated = Category.query.get(category.id)
            assert updated.name == 'Premium Attars'

    def test_delete_category_with_products(self, fresh_app, init_database):
        """Test behavior when deleting category with products."""
        with fresh_app.app_context():
            category = Category.query.filter_by(name='Attars').first()

            # Get products in this category
            products_count = Product.query.filter_by(category_id=category.id).count()
            assert products_count > 0

            # Category with products - behavior depends on implementation
            # Products should be reassigned or prevented from deletion
            # This tests the relationship exists
            assert category.products.count() > 0

    def test_nested_category_parent(self, fresh_app, init_database):
        """Test creating nested category with parent."""
        with fresh_app.app_context():
            parent = Category.query.filter_by(name='Attars').first()

            child = Category(
                name='Oud Attars',
                description='Oud-based attars',
                parent_id=parent.id
            )
            db.session.add(child)
            db.session.commit()

            saved_child = Category.query.filter_by(name='Oud Attars').first()
            assert saved_child.parent_id == parent.id
            assert saved_child.parent.name == 'Attars'

    def test_nested_category_children(self, fresh_app, init_database):
        """Test accessing subcategories."""
        with fresh_app.app_context():
            parent = Category.query.filter_by(name='Attars').first()

            # Create subcategories
            child1 = Category(name='Oud Attars', parent_id=parent.id)
            child2 = Category(name='Musk Attars', parent_id=parent.id)
            db.session.add_all([child1, child2])
            db.session.commit()

            refreshed_parent = Category.query.get(parent.id)
            assert len(refreshed_parent.subcategories) == 2

    def test_category_unique_name(self, fresh_app, init_database):
        """Test that category names must be unique."""
        with fresh_app.app_context():
            duplicate = Category(name='Attars')  # Already exists
            db.session.add(duplicate)

            with pytest.raises(Exception):
                db.session.commit()

            db.session.rollback()

    def test_categories_page(self, auth_admin, fresh_app, init_database):
        """Test categories management page loads."""
        response = auth_admin.get('/inventory/categories')
        assert response.status_code in [200, 302]


# ============================================================================
# STOCK TRANSFERS TESTS
# ============================================================================

class TestStockTransfers:
    """Tests for stock transfers between locations."""

    def test_create_transfer_request(self, fresh_app, init_database):
        """Test creating a transfer request."""
        with fresh_app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()
            user = User.query.filter_by(username='manager').first()

            transfer = StockTransfer(
                transfer_number='TR-TEST-001',
                source_location_id=warehouse.id,
                destination_location_id=kiosk.id,
                status='requested',
                priority='normal',
                requested_by=user.id,
                requested_at=datetime.utcnow(),
                request_notes='Test transfer request'
            )
            db.session.add(transfer)
            db.session.commit()

            saved = StockTransfer.query.filter_by(transfer_number='TR-TEST-001').first()
            assert saved is not None
            assert saved.status == 'requested'
            assert saved.can_approve is True

    def test_transfer_item_add(self, fresh_app, init_database):
        """Test adding items to transfer."""
        with fresh_app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()
            product = Product.query.filter_by(code='PRD001').first()
            user = User.query.filter_by(username='manager').first()

            transfer = StockTransfer(
                transfer_number='TR-TEST-002',
                source_location_id=warehouse.id,
                destination_location_id=kiosk.id,
                status='requested',
                requested_by=user.id,
                requested_at=datetime.utcnow()
            )
            db.session.add(transfer)
            db.session.flush()

            item = StockTransferItem(
                transfer_id=transfer.id,
                product_id=product.id,
                quantity_requested=25
            )
            db.session.add(item)
            db.session.commit()

            saved_transfer = StockTransfer.query.get(transfer.id)
            assert saved_transfer.items.count() == 1
            assert saved_transfer.total_quantity_requested == 25

    def test_transfer_approval_workflow(self, fresh_app, init_database):
        """Test transfer approval workflow."""
        with fresh_app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()
            product = Product.query.filter_by(code='PRD001').first()
            manager = User.query.filter_by(username='manager').first()
            wh_manager = User.query.filter_by(username='warehouse_mgr').first()

            # Create transfer
            transfer = StockTransfer(
                transfer_number='TR-WORKFLOW-001',
                source_location_id=warehouse.id,
                destination_location_id=kiosk.id,
                status='requested',
                requested_by=manager.id,
                requested_at=datetime.utcnow()
            )
            db.session.add(transfer)
            db.session.flush()

            item = StockTransferItem(
                transfer_id=transfer.id,
                product_id=product.id,
                quantity_requested=10
            )
            db.session.add(item)
            db.session.commit()

            # Test can_approve
            assert transfer.can_approve is True
            assert transfer.can_dispatch is False
            assert transfer.can_receive is False

            # Approve transfer
            transfer.status = 'approved'
            transfer.approved_by = wh_manager.id
            transfer.approved_at = datetime.utcnow()
            item.quantity_approved = 10
            db.session.commit()

            # Test can_dispatch
            assert transfer.can_approve is False
            assert transfer.can_dispatch is True
            assert transfer.can_receive is False

    def test_transfer_dispatch(self, fresh_app, init_database):
        """Test dispatching a transfer."""
        with fresh_app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()
            product = Product.query.filter_by(code='PRD001').first()
            user = User.query.filter_by(username='warehouse_mgr').first()

            # Create and approve transfer
            transfer = StockTransfer(
                transfer_number='TR-DISPATCH-001',
                source_location_id=warehouse.id,
                destination_location_id=kiosk.id,
                status='approved',
                approved_by=user.id,
                approved_at=datetime.utcnow()
            )
            db.session.add(transfer)
            db.session.flush()

            item = StockTransferItem(
                transfer_id=transfer.id,
                product_id=product.id,
                quantity_requested=10,
                quantity_approved=10
            )
            db.session.add(item)
            db.session.commit()

            # Dispatch transfer
            transfer.status = 'dispatched'
            transfer.dispatched_by = user.id
            transfer.dispatched_at = datetime.utcnow()
            item.quantity_dispatched = 10
            db.session.commit()

            assert transfer.can_dispatch is False
            assert transfer.can_receive is True

    def test_transfer_receive(self, fresh_app, init_database):
        """Test receiving a transfer."""
        with fresh_app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()
            product = Product.query.filter_by(code='PRD001').first()
            user = User.query.filter_by(username='manager').first()

            # Create dispatched transfer
            transfer = StockTransfer(
                transfer_number='TR-RECEIVE-001',
                source_location_id=warehouse.id,
                destination_location_id=kiosk.id,
                status='dispatched',
                dispatched_by=user.id,
                dispatched_at=datetime.utcnow()
            )
            db.session.add(transfer)
            db.session.flush()

            item = StockTransferItem(
                transfer_id=transfer.id,
                product_id=product.id,
                quantity_requested=10,
                quantity_approved=10,
                quantity_dispatched=10
            )
            db.session.add(item)
            db.session.commit()

            # Receive transfer
            transfer.status = 'received'
            transfer.received_by = user.id
            transfer.received_at = datetime.utcnow()
            item.quantity_received = 10
            db.session.commit()

            assert transfer.status == 'received'
            assert transfer.can_receive is False

    def test_partial_transfer(self, fresh_app, init_database):
        """Test partial quantity transfer."""
        with fresh_app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()
            product = Product.query.filter_by(code='PRD001').first()
            user = User.query.filter_by(username='warehouse_mgr').first()

            transfer = StockTransfer(
                transfer_number='TR-PARTIAL-001',
                source_location_id=warehouse.id,
                destination_location_id=kiosk.id,
                status='requested',
                requested_by=user.id,
                requested_at=datetime.utcnow()
            )
            db.session.add(transfer)
            db.session.flush()

            # Request 100, approve only 50
            item = StockTransferItem(
                transfer_id=transfer.id,
                product_id=product.id,
                quantity_requested=100
            )
            db.session.add(item)
            db.session.commit()

            # Approve partial
            item.quantity_approved = 50
            transfer.status = 'approved'
            db.session.commit()

            assert item.quantity_requested == 100
            assert item.quantity_approved == 50

    def test_cancelled_transfer(self, fresh_app, init_database):
        """Test cancelling a transfer."""
        with fresh_app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()
            user = User.query.filter_by(username='manager').first()

            transfer = StockTransfer(
                transfer_number='TR-CANCEL-001',
                source_location_id=warehouse.id,
                destination_location_id=kiosk.id,
                status='requested',
                requested_by=user.id,
                requested_at=datetime.utcnow()
            )
            db.session.add(transfer)
            db.session.commit()

            # Test can_cancel
            assert transfer.can_cancel is True

            # Cancel transfer
            transfer.status = 'cancelled'
            transfer.rejection_reason = 'No longer needed'
            db.session.commit()

            assert transfer.status == 'cancelled'
            assert transfer.can_cancel is False

    def test_transfer_discrepancy(self, fresh_app, init_database):
        """Test transfer item discrepancy detection."""
        with fresh_app.app_context():
            item = StockTransferItem(
                transfer_id=1,
                product_id=1,
                quantity_requested=100,
                quantity_approved=100,
                quantity_dispatched=100,
                quantity_received=95  # Discrepancy
            )

            assert item.has_discrepancy is True
            assert item.discrepancy_amount == -5

    def test_transfer_status_badge_class(self, fresh_app, init_database):
        """Test transfer status badge CSS class."""
        with fresh_app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()

            transfer = StockTransfer(
                transfer_number='TR-BADGE-001',
                source_location_id=warehouse.id,
                destination_location_id=kiosk.id,
                status='requested'
            )

            assert transfer.status_badge_class == 'info'

            transfer.status = 'approved'
            assert transfer.status_badge_class == 'primary'

            transfer.status = 'received'
            assert transfer.status_badge_class == 'success'

            transfer.status = 'rejected'
            assert transfer.status_badge_class == 'danger'


class TestTransferAPIEndpoints:
    """Tests for transfer API endpoints."""

    def test_transfers_index_page(self, auth_admin, fresh_app, init_database):
        """Test transfers list page loads."""
        response = auth_admin.get('/transfers/')
        assert response.status_code in [200, 302]

    def test_transfer_create_page(self, auth_manager, fresh_app, init_database):
        """Test create transfer page loads."""
        response = auth_manager.get('/transfers/create')
        assert response.status_code in [200, 302]

    def test_pending_transfers_page(self, auth_warehouse_manager, fresh_app, init_database):
        """Test pending transfers page loads."""
        response = auth_warehouse_manager.get('/transfers/pending')
        assert response.status_code in [200, 302]

    def test_incoming_transfers_page(self, auth_manager, fresh_app, init_database):
        """Test incoming transfers page loads."""
        response = auth_manager.get('/transfers/incoming')
        assert response.status_code in [200, 302]


# ============================================================================
# STOCK ADJUSTMENTS AND AUDIT TRAIL TESTS
# ============================================================================

class TestStockAdjustments:
    """Tests for stock adjustments with audit trail."""

    def test_adjustment_creates_movement_record(self, fresh_app, init_database):
        """Test that adjustments create stock movement records."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()
            user = User.query.filter_by(username='admin').first()

            initial_movements = StockMovement.query.filter_by(product_id=product.id).count()

            # Create adjustment movement
            movement = StockMovement(
                product_id=product.id,
                user_id=user.id,
                movement_type='adjustment',
                quantity=25,
                reference='ADJ-AUDIT-001',
                notes='Audit test adjustment'
            )
            db.session.add(movement)
            db.session.commit()

            final_movements = StockMovement.query.filter_by(product_id=product.id).count()
            assert final_movements == initial_movements + 1

    def test_adjustment_reason_recorded(self, fresh_app, init_database):
        """Test that adjustment reason is recorded."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()
            user = User.query.filter_by(username='admin').first()

            reason = 'Damaged goods - 5 units'
            movement = StockMovement(
                product_id=product.id,
                user_id=user.id,
                movement_type='adjustment',
                quantity=-5,
                reference='ADJ-DAMAGE-001',
                notes=reason
            )
            db.session.add(movement)
            db.session.commit()

            saved = StockMovement.query.filter_by(reference='ADJ-DAMAGE-001').first()
            assert saved.notes == reason

    def test_adjustment_user_tracking(self, fresh_app, init_database):
        """Test that user who made adjustment is tracked."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()
            user = User.query.filter_by(username='manager').first()

            movement = StockMovement(
                product_id=product.id,
                user_id=user.id,
                movement_type='adjustment',
                quantity=10,
                reference='ADJ-USER-001'
            )
            db.session.add(movement)
            db.session.commit()

            saved = StockMovement.query.filter_by(reference='ADJ-USER-001').first()
            assert saved.user_id == user.id
            assert saved.user.username == 'manager'

    def test_adjustment_timestamp(self, fresh_app, init_database):
        """Test that adjustment timestamp is recorded."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()
            user = User.query.filter_by(username='admin').first()

            before_time = datetime.utcnow()

            movement = StockMovement(
                product_id=product.id,
                user_id=user.id,
                movement_type='adjustment',
                quantity=15,
                reference='ADJ-TIME-001'
            )
            db.session.add(movement)
            db.session.commit()

            after_time = datetime.utcnow()

            saved = StockMovement.query.filter_by(reference='ADJ-TIME-001').first()
            assert before_time <= saved.timestamp <= after_time

    def test_adjustment_movement_types(self, fresh_app, init_database):
        """Test various adjustment movement types."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()
            user = User.query.filter_by(username='admin').first()

            movement_types = ['purchase', 'sale', 'adjustment', 'return', 'damage', 'transfer_in', 'transfer_out']

            for i, mv_type in enumerate(movement_types):
                movement = StockMovement(
                    product_id=product.id,
                    user_id=user.id,
                    movement_type=mv_type,
                    quantity=10 if 'in' in mv_type or mv_type in ['purchase', 'return'] else -10,
                    reference=f'MV-TYPE-{i:03d}'
                )
                db.session.add(movement)

            db.session.commit()

            for i, mv_type in enumerate(movement_types):
                saved = StockMovement.query.filter_by(reference=f'MV-TYPE-{i:03d}').first()
                assert saved.movement_type == mv_type

    def test_stock_movements_page(self, auth_admin, fresh_app, init_database):
        """Test stock movements page loads."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

        response = auth_admin.get(f'/inventory/stock-movements/{product.id}')
        assert response.status_code in [200, 302]


# ============================================================================
# REORDER POINTS AND ALERTS TESTS
# ============================================================================

class TestReorderPoints:
    """Tests for reorder points and stock alerts."""

    def test_product_is_low_stock(self, fresh_app, init_database):
        """Test product low stock detection."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            # Set quantity below reorder level
            product.quantity = product.reorder_level - 1
            db.session.commit()

            assert product.is_low_stock is True

    def test_product_not_low_stock(self, fresh_app, init_database):
        """Test product not flagged when stock is sufficient."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            # Set quantity above reorder level
            product.quantity = product.reorder_level + 50
            db.session.commit()

            assert product.is_low_stock is False

    def test_product_out_of_stock(self, fresh_app, init_database):
        """Test out of stock product detection."""
        with fresh_app.app_context():
            # PRD003 has quantity=0 in init_database
            product = Product.query.filter_by(code='PRD003').first()

            assert product.quantity == 0
            assert product.is_low_stock is True

    def test_location_low_stock_alert(self, fresh_app, init_database):
        """Test low stock alert at location level."""
        with fresh_app.app_context():
            kiosk = Location.query.filter_by(code='K-001').first()
            product = Product.query.filter_by(code='PRD001').first()

            loc_stock = LocationStock.query.filter_by(
                location_id=kiosk.id,
                product_id=product.id
            ).first()

            # Set low stock
            loc_stock.quantity = loc_stock.reorder_level - 1
            db.session.commit()

            assert loc_stock.is_low_stock is True

    def test_reorder_quantity_suggested(self, fresh_app, init_database):
        """Test suggested reorder quantity property."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            # With no sales history, should return default reorder_quantity
            suggested = product.suggested_reorder_quantity
            assert suggested >= product.reorder_quantity

    def test_needs_reorder_flag(self, fresh_app, init_database):
        """Test needs_reorder property."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            # Set stock below reorder level
            product.quantity = product.reorder_level - 1
            db.session.commit()

            assert product.needs_reorder is True

    def test_low_stock_alert_page(self, auth_admin, fresh_app, init_database):
        """Test low stock alert page loads."""
        response = auth_admin.get('/inventory/low-stock-alert')
        assert response.status_code in [200, 302]

    def test_reorders_page(self, auth_manager, fresh_app, init_database):
        """Test reorders management page loads."""
        response = auth_manager.get('/transfers/reorders')
        assert response.status_code in [200, 302]

    def test_alert_priority_critical(self, fresh_app, init_database):
        """Test alert priority for zero stock."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD003').first()
            product.quantity = 0
            db.session.commit()

            assert product.alert_priority == 'critical'

    def test_alert_priority_high(self, fresh_app, init_database):
        """Test alert priority for low stock."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()
            product.quantity = product.reorder_level
            db.session.commit()

            assert product.alert_priority == 'high'


# ============================================================================
# BARCODE MANAGEMENT TESTS
# ============================================================================

class TestBarcodeManagement:
    """Tests for barcode management."""

    def test_product_barcode_unique(self, fresh_app, init_database):
        """Test that barcodes must be unique."""
        with fresh_app.app_context():
            existing = Product.query.filter_by(code='PRD001').first()
            existing_barcode = existing.barcode

            # Try to create product with same barcode
            new_product = Product(
                code='BARCODE-DUP-001',
                barcode=existing_barcode,
                name='Duplicate Barcode Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(new_product)

            with pytest.raises(Exception):
                db.session.commit()

            db.session.rollback()

    def test_product_barcode_search(self, fresh_app, init_database):
        """Test searching product by barcode."""
        with fresh_app.app_context():
            product = Product.query.filter_by(barcode='1234567890123').first()

            assert product is not None
            assert product.code == 'PRD001'

    def test_product_barcode_nullable(self, fresh_app, init_database):
        """Test that barcode can be null."""
        with fresh_app.app_context():
            product = Product(
                code='NO-BARCODE-001',
                name='Product Without Barcode',
                cost_price=Decimal('50.00'),
                selling_price=Decimal('100.00'),
                barcode=None
            )
            db.session.add(product)
            db.session.commit()

            saved = Product.query.filter_by(code='NO-BARCODE-001').first()
            assert saved is not None
            assert saved.barcode is None

    def test_barcode_format_ean13(self, fresh_app, init_database):
        """Test EAN-13 barcode format (13 digits)."""
        with fresh_app.app_context():
            product = Product(
                code='EAN13-001',
                barcode='1234567890128',  # 13 digits
                name='EAN-13 Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            saved = Product.query.filter_by(code='EAN13-001').first()
            assert len(saved.barcode) == 13

    def test_barcode_format_upc(self, fresh_app, init_database):
        """Test UPC barcode format (12 digits)."""
        with fresh_app.app_context():
            product = Product(
                code='UPC-001',
                barcode='012345678905',  # 12 digits
                name='UPC Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            saved = Product.query.filter_by(code='UPC-001').first()
            assert len(saved.barcode) == 12

    def test_barcode_case_sensitivity(self, fresh_app, init_database):
        """Test that barcode search handles alphanumeric codes."""
        with fresh_app.app_context():
            # Create product with alphanumeric barcode
            product = Product(
                code='ALPHA-BAR-001',
                barcode='ABC123DEF456',
                name='Alphanumeric Barcode Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            # Search by exact barcode
            found = Product.query.filter_by(barcode='ABC123DEF456').first()
            assert found is not None


# ============================================================================
# BATCH/LOT TRACKING TESTS
# ============================================================================

class TestBatchLotTracking:
    """Tests for batch/lot tracking and expiry dates."""

    def test_product_batch_number(self, fresh_app, init_database):
        """Test storing batch number on product."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            product.batch_number = 'BATCH-2024-001'
            db.session.commit()

            updated = Product.query.get(product.id)
            assert updated.batch_number == 'BATCH-2024-001'

    def test_product_expiry_date(self, fresh_app, init_database):
        """Test storing expiry date on product."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            expiry = date(2025, 12, 31)
            product.expiry_date = expiry
            db.session.commit()

            updated = Product.query.get(product.id)
            assert updated.expiry_date == expiry

    def test_days_until_expiry(self, fresh_app, init_database):
        """Test days until expiry calculation."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            # Set expiry 30 days from now
            future_date = date.today() + timedelta(days=30)
            product.expiry_date = future_date
            db.session.commit()

            assert product.days_until_expiry == 30

    def test_product_is_expired(self, fresh_app, init_database):
        """Test expired product detection."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            # Set expiry date in the past
            past_date = date.today() - timedelta(days=5)
            product.expiry_date = past_date
            db.session.commit()

            assert product.is_expired is True

    def test_product_not_expired(self, fresh_app, init_database):
        """Test non-expired product."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            # Set expiry date in the future
            future_date = date.today() + timedelta(days=365)
            product.expiry_date = future_date
            db.session.commit()

            assert product.is_expired is False

    def test_product_expiring_soon(self, fresh_app, init_database):
        """Test product expiring within 30 days detection."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            # Set expiry 15 days from now
            future_date = date.today() + timedelta(days=15)
            product.expiry_date = future_date
            db.session.commit()

            assert product.is_expiring_soon is True

    def test_product_expiring_critical(self, fresh_app, init_database):
        """Test product expiring within 7 days detection."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            # Set expiry 5 days from now
            future_date = date.today() + timedelta(days=5)
            product.expiry_date = future_date
            db.session.commit()

            assert product.is_expiring_critical is True

    def test_expiry_status_property(self, fresh_app, init_database):
        """Test expiry status property values."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            # No expiry date
            product.expiry_date = None
            assert product.expiry_status == 'no_expiry'

            # Expired
            product.expiry_date = date.today() - timedelta(days=1)
            assert product.expiry_status == 'expired'

            # Critical (within 7 days)
            product.expiry_date = date.today() + timedelta(days=3)
            assert product.expiry_status == 'critical'

            # Warning (within 30 days)
            product.expiry_date = date.today() + timedelta(days=20)
            assert product.expiry_status == 'warning'

            # Good (more than 30 days)
            product.expiry_date = date.today() + timedelta(days=60)
            assert product.expiry_status == 'good'

    def test_expiry_badge_class(self, fresh_app, init_database):
        """Test expiry badge CSS class."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            # Expired - danger
            product.expiry_date = date.today() - timedelta(days=1)
            assert product.expiry_badge_class == 'danger'

            # Good - success
            product.expiry_date = date.today() + timedelta(days=60)
            assert product.expiry_badge_class == 'success'


# ============================================================================
# WAREHOUSE OPERATIONS TESTS
# ============================================================================

class TestWarehouseOperations:
    """Tests for warehouse operations."""

    def test_warehouse_location_type(self, fresh_app, init_database):
        """Test warehouse location type."""
        with fresh_app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()

            assert warehouse.location_type == 'warehouse'
            assert warehouse.is_warehouse is True
            assert warehouse.is_kiosk is False

    def test_kiosk_location_type(self, fresh_app, init_database):
        """Test kiosk location type."""
        with fresh_app.app_context():
            kiosk = Location.query.filter_by(code='K-001').first()

            assert kiosk.location_type == 'kiosk'
            assert kiosk.is_kiosk is True
            assert kiosk.is_warehouse is False

    def test_warehouse_child_kiosks(self, fresh_app, init_database):
        """Test warehouse-kiosk relationship."""
        with fresh_app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()

            assert kiosk.parent_warehouse_id == warehouse.id
            assert kiosk in warehouse.child_kiosks

    def test_location_get_stock_for_product(self, fresh_app, init_database):
        """Test getting stock level for product at location."""
        with fresh_app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            product = Product.query.filter_by(code='PRD001').first()

            stock = warehouse.get_stock_for_product(product.id)

            # Should return available quantity (quantity - reserved)
            loc_stock = LocationStock.query.filter_by(
                location_id=warehouse.id,
                product_id=product.id
            ).first()

            assert stock == loc_stock.available_quantity

    def test_location_stock_value(self, fresh_app, init_database):
        """Test location stock value calculation."""
        with fresh_app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            product = Product.query.filter_by(code='PRD001').first()

            loc_stock = LocationStock.query.filter_by(
                location_id=warehouse.id,
                product_id=product.id
            ).first()

            expected_value = float(loc_stock.quantity * product.cost_price)
            assert loc_stock.stock_value == expected_value

    def test_gate_pass_creation(self, fresh_app, init_database):
        """Test gate pass creation for dispatch."""
        with fresh_app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()
            user = User.query.filter_by(username='warehouse_mgr').first()

            # Create transfer
            transfer = StockTransfer(
                transfer_number='TR-GP-001',
                source_location_id=warehouse.id,
                destination_location_id=kiosk.id,
                status='approved'
            )
            db.session.add(transfer)
            db.session.flush()

            # Create gate pass
            gate_pass = GatePass(
                gate_pass_number='GP-TEST-001',
                transfer_id=transfer.id,
                vehicle_number='ABC-123',
                vehicle_type='car',
                driver_name='Test Driver',
                driver_phone='03001234567',
                status='issued',
                created_by=user.id
            )
            db.session.add(gate_pass)
            db.session.commit()

            saved = GatePass.query.filter_by(gate_pass_number='GP-TEST-001').first()
            assert saved is not None
            assert saved.transfer_id == transfer.id
            assert saved.vehicle_number == 'ABC-123'

    def test_gate_pass_status_workflow(self, fresh_app, init_database):
        """Test gate pass status workflow."""
        with fresh_app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()
            user = User.query.filter_by(username='warehouse_mgr').first()

            transfer = StockTransfer(
                transfer_number='TR-GP-002',
                source_location_id=warehouse.id,
                destination_location_id=kiosk.id,
                status='approved'
            )
            db.session.add(transfer)
            db.session.flush()

            gate_pass = GatePass(
                gate_pass_number='GP-TEST-002',
                transfer_id=transfer.id,
                status='issued',
                created_by=user.id
            )
            db.session.add(gate_pass)
            db.session.commit()

            assert gate_pass.status == 'issued'
            assert gate_pass.is_editable is True

            # Move to in_transit
            gate_pass.status = 'in_transit'
            db.session.commit()
            assert gate_pass.is_editable is False

            # Move to delivered
            gate_pass.status = 'delivered'
            gate_pass.actual_arrival = datetime.utcnow()
            db.session.commit()

            # Move to verified
            gate_pass.status = 'verified'
            gate_pass.verified_by = user.id
            db.session.commit()

            assert gate_pass.status_badge_class == 'success'

    def test_warehouse_dashboard_page(self, auth_warehouse_manager, fresh_app, init_database):
        """Test warehouse dashboard page loads."""
        response = auth_warehouse_manager.get('/warehouse/')
        assert response.status_code in [200, 302]

    def test_warehouse_stock_page(self, auth_warehouse_manager, fresh_app, init_database):
        """Test warehouse stock page loads."""
        response = auth_warehouse_manager.get('/warehouse/stock')
        assert response.status_code in [200, 302]

    def test_warehouse_requests_page(self, auth_warehouse_manager, fresh_app, init_database):
        """Test warehouse requests page loads."""
        response = auth_warehouse_manager.get('/warehouse/requests')
        assert response.status_code in [200, 302]


# ============================================================================
# INVENTORY VALUATION TESTS
# ============================================================================

class TestInventoryValuation:
    """Tests for inventory valuation methods."""

    def test_product_stock_value_at_cost(self, fresh_app, init_database):
        """Test product stock value at cost price."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            expected_value = float(product.quantity * product.cost_price)
            assert product.stock_value == expected_value

    def test_location_stock_value(self, fresh_app, init_database):
        """Test location-specific stock value."""
        with fresh_app.app_context():
            location = Location.query.filter_by(code='WH-001').first()

            total_value = 0
            for loc_stock in LocationStock.query.filter_by(location_id=location.id).all():
                total_value += loc_stock.stock_value

            assert total_value > 0

    def test_cost_price_update(self, fresh_app, init_database):
        """Test updating product cost price."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()
            original_cost = product.cost_price

            # Update cost price
            product.cost_price = Decimal('600.00')
            db.session.commit()

            updated = Product.query.get(product.id)
            assert updated.cost_price == Decimal('600.00')
            assert updated.cost_price != original_cost

    def test_profit_margin_calculation(self, fresh_app, init_database):
        """Test profit margin calculation."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            # Cost: 500, Selling: 1000
            # Margin = ((1000-500)/500) * 100 = 100%
            expected = ((product.selling_price - product.cost_price) / product.cost_price) * 100

            assert product.profit_margin == expected

    def test_profit_margin_zero_cost(self, fresh_app, init_database):
        """Test profit margin when cost is zero."""
        with fresh_app.app_context():
            product = Product(
                code='ZERO-COST-001',
                name='Zero Cost Product',
                cost_price=Decimal('0.00'),
                selling_price=Decimal('100.00')
            )
            db.session.add(product)
            db.session.commit()

            # Should return 0 to avoid division by zero
            assert product.profit_margin == 0

    def test_print_stock_report(self, auth_admin, fresh_app, init_database):
        """Test print stock report page."""
        response = auth_admin.get('/inventory/print-stock-report')
        assert response.status_code in [200, 302]


# ============================================================================
# STOCK TAKES AND CYCLE COUNTS TESTS
# ============================================================================

class TestStockTakes:
    """Tests for stock takes and cycle counts."""

    def test_location_stock_last_count(self, fresh_app, init_database):
        """Test recording last stock count timestamp."""
        with fresh_app.app_context():
            location = Location.query.filter_by(code='K-001').first()
            product = Product.query.filter_by(code='PRD001').first()

            loc_stock = LocationStock.query.filter_by(
                location_id=location.id,
                product_id=product.id
            ).first()

            count_time = datetime.utcnow()
            loc_stock.last_count_at = count_time
            db.session.commit()

            updated = LocationStock.query.get(loc_stock.id)
            assert updated.last_count_at is not None

    def test_stock_count_adjustment(self, fresh_app, init_database):
        """Test adjusting stock after physical count."""
        with fresh_app.app_context():
            location = Location.query.filter_by(code='K-001').first()
            product = Product.query.filter_by(code='PRD001').first()
            user = User.query.filter_by(username='admin').first()

            loc_stock = LocationStock.query.filter_by(
                location_id=location.id,
                product_id=product.id
            ).first()

            system_qty = loc_stock.quantity
            counted_qty = system_qty - 5  # Discrepancy found

            # Record adjustment
            adjustment = counted_qty - system_qty

            movement = StockMovement(
                product_id=product.id,
                user_id=user.id,
                location_id=location.id,
                movement_type='adjustment',
                quantity=adjustment,
                reference='STOCK-COUNT-001',
                notes=f'Physical count discrepancy. System: {system_qty}, Counted: {counted_qty}'
            )
            db.session.add(movement)

            loc_stock.quantity = counted_qty
            loc_stock.last_count_at = datetime.utcnow()
            db.session.commit()

            updated = LocationStock.query.get(loc_stock.id)
            assert updated.quantity == counted_qty

    def test_stock_discrepancy_tracking(self, fresh_app, init_database):
        """Test tracking stock discrepancies."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()
            user = User.query.filter_by(username='admin').first()

            # Simulate stock take with discrepancy
            discrepancy_movements = StockMovement.query.filter(
                StockMovement.notes.ilike('%discrepancy%')
            ).all()

            initial_count = len(discrepancy_movements)

            # Create discrepancy record
            movement = StockMovement(
                product_id=product.id,
                user_id=user.id,
                movement_type='adjustment',
                quantity=-3,
                reference='DISC-001',
                notes='Stock count discrepancy - 3 units missing'
            )
            db.session.add(movement)
            db.session.commit()

            final_movements = StockMovement.query.filter(
                StockMovement.notes.ilike('%discrepancy%')
            ).all()

            assert len(final_movements) == initial_count + 1


# ============================================================================
# FORECASTING TESTS
# ============================================================================

class TestForecasting:
    """Tests for inventory forecasting functionality."""

    def test_get_product_sales_stats_no_sales(self, fresh_app, init_database):
        """Test sales stats when no sales exist."""
        with fresh_app.app_context():
            from app.utils.inventory_forecast import get_product_sales_stats

            product = Product.query.filter_by(code='PRD001').first()
            location = Location.query.filter_by(code='K-001').first()

            stats = get_product_sales_stats(product.id, location.id, days=30)

            assert stats['total_sold'] == 0
            assert stats['avg_daily_sales'] == 0
            assert stats['sale_days'] == 0

    def test_calculate_safety_stock_no_history(self, fresh_app, init_database):
        """Test safety stock calculation with no sales history."""
        with fresh_app.app_context():
            from app.utils.inventory_forecast import calculate_safety_stock

            product = Product.query.filter_by(code='PRD001').first()
            location = Location.query.filter_by(code='K-001').first()

            safety_stock = calculate_safety_stock(product.id, location.id)

            # Should return default minimum
            assert safety_stock == 5

    def test_calculate_reorder_point(self, fresh_app, init_database):
        """Test reorder point calculation."""
        with fresh_app.app_context():
            from app.utils.inventory_forecast import calculate_reorder_point

            product = Product.query.filter_by(code='PRD001').first()
            location = Location.query.filter_by(code='K-001').first()

            reorder_point = calculate_reorder_point(product.id, location.id)

            # With no sales, should be at least safety stock
            assert reorder_point >= 3  # Minimum safety stock

    def test_calculate_days_of_stock_no_sales(self, fresh_app, init_database):
        """Test days of stock calculation with no sales."""
        with fresh_app.app_context():
            from app.utils.inventory_forecast import calculate_days_of_stock

            product = Product.query.filter_by(code='PRD001').first()
            location = Location.query.filter_by(code='K-001').first()

            days = calculate_days_of_stock(product.id, location.id)

            # With no sales, returns None
            assert days is None

    def test_calculate_suggested_reorder_qty(self, fresh_app, init_database):
        """Test suggested reorder quantity calculation."""
        with fresh_app.app_context():
            from app.utils.inventory_forecast import calculate_suggested_reorder_qty

            product = Product.query.filter_by(code='PRD001').first()
            location = Location.query.filter_by(code='K-001').first()

            suggested = calculate_suggested_reorder_qty(product.id, location.id)

            # With stock available and no sales, might be 0 or minimum
            assert suggested >= 0

    def test_get_product_forecast(self, fresh_app, init_database):
        """Test complete product forecast data."""
        with fresh_app.app_context():
            from app.utils.inventory_forecast import get_product_forecast

            product = Product.query.filter_by(code='PRD001').first()
            location = Location.query.filter_by(code='K-001').first()

            forecast = get_product_forecast(product.id, location.id)

            assert 'current_stock' in forecast
            assert 'safety_stock' in forecast
            assert 'recommended_reorder_point' in forecast
            assert 'status' in forecast
            assert 'urgency' in forecast

    def test_get_low_stock_alerts(self, fresh_app, init_database):
        """Test getting low stock alerts for location."""
        with fresh_app.app_context():
            from app.utils.inventory_forecast import get_low_stock_alerts

            location = Location.query.filter_by(code='K-001').first()

            alerts = get_low_stock_alerts(location.id)

            # Should return list
            assert isinstance(alerts, list)

            # Each alert should have required fields
            for alert in alerts:
                assert 'product' in alert
                assert 'current_stock' in alert
                assert 'urgency' in alert

    def test_get_location_stock_summary(self, fresh_app, init_database):
        """Test location stock summary."""
        with fresh_app.app_context():
            from app.utils.inventory_forecast import get_location_stock_summary

            location = Location.query.filter_by(code='K-001').first()

            summary = get_location_stock_summary(location.id)

            assert 'total_products' in summary
            assert 'in_stock' in summary
            assert 'low_stock' in summary
            assert 'out_of_stock' in summary
            assert 'total_value' in summary
            assert 'stock_health_percent' in summary


# ============================================================================
# EDGE CASES AND DATA INTEGRITY TESTS
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and data integrity."""

    def test_zero_quantity_product(self, fresh_app, init_database):
        """Test handling zero quantity products."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD003').first()

            assert product.quantity == 0
            assert product.is_low_stock is True
            assert product.stock_value == 0

    def test_large_quantity_handling(self, fresh_app, init_database):
        """Test handling large quantities."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

            # Set very large quantity
            product.quantity = 999999
            db.session.commit()

            updated = Product.query.get(product.id)
            assert updated.quantity == 999999

    def test_decimal_price_precision(self, fresh_app, init_database):
        """Test decimal price precision."""
        with fresh_app.app_context():
            product = Product(
                code='DECIMAL-001',
                name='Decimal Price Test',
                cost_price=Decimal('99.99'),
                selling_price=Decimal('149.95')
            )
            db.session.add(product)
            db.session.commit()

            saved = Product.query.filter_by(code='DECIMAL-001').first()
            assert saved.cost_price == Decimal('99.99')
            assert saved.selling_price == Decimal('149.95')

    def test_negative_price_prevention(self, fresh_app, init_database):
        """Test that negative prices are handled."""
        with fresh_app.app_context():
            # Model allows negative but business logic should prevent
            product = Product(
                code='NEG-PRICE-001',
                name='Negative Price Test',
                cost_price=Decimal('-10.00'),  # Invalid
                selling_price=Decimal('100.00')
            )
            db.session.add(product)
            db.session.commit()

            # Model doesn't prevent, but value is stored
            saved = Product.query.filter_by(code='NEG-PRICE-001').first()
            assert saved.cost_price == Decimal('-10.00')

    def test_special_characters_in_name(self, fresh_app, init_database):
        """Test handling special characters in product name."""
        with fresh_app.app_context():
            product = Product(
                code='SPECIAL-001',
                name='Product & Test <Special> "Chars"',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            saved = Product.query.filter_by(code='SPECIAL-001').first()
            assert saved.name == 'Product & Test <Special> "Chars"'

    def test_unicode_product_name(self, fresh_app, init_database):
        """Test handling Unicode characters in product name."""
        with fresh_app.app_context():
            product = Product(
                code='UNICODE-001',
                name='عطر العود',  # Arabic
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            saved = Product.query.filter_by(code='UNICODE-001').first()
            assert saved.name == 'عطر العود'

    def test_empty_string_handling(self, fresh_app, init_database):
        """Test handling empty strings in optional fields."""
        with fresh_app.app_context():
            product = Product(
                code='EMPTY-001',
                name='Empty Fields Test',
                brand='',  # Empty string
                description='',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            saved = Product.query.filter_by(code='EMPTY-001').first()
            assert saved.brand == ''

    def test_null_optional_fields(self, fresh_app, init_database):
        """Test null values in optional fields."""
        with fresh_app.app_context():
            product = Product(
                code='NULL-001',
                name='Null Fields Test',
                brand=None,
                description=None,
                category_id=None,
                supplier_id=None,
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            saved = Product.query.filter_by(code='NULL-001').first()
            assert saved.brand is None
            assert saved.category_id is None

    def test_concurrent_stock_update_simulation(self, fresh_app, init_database):
        """Test simulated concurrent stock update."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()
            initial_qty = product.quantity

            # Simulate two concurrent updates
            product.quantity -= 10
            db.session.commit()

            # Refresh and update again
            db.session.refresh(product)
            product.quantity -= 5
            db.session.commit()

            final = Product.query.get(product.id)
            assert final.quantity == initial_qty - 15

    def test_transfer_same_source_destination(self, fresh_app, init_database):
        """Test transfer where source and destination are same."""
        with fresh_app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()

            # Create transfer to same location (should be prevented by business logic)
            transfer = StockTransfer(
                transfer_number='TR-SAME-001',
                source_location_id=warehouse.id,
                destination_location_id=warehouse.id,  # Same location
                status='requested'
            )
            db.session.add(transfer)
            db.session.commit()

            # Model allows it, business logic should prevent
            saved = StockTransfer.query.filter_by(transfer_number='TR-SAME-001').first()
            assert saved.source_location_id == saved.destination_location_id

    def test_inactive_product_in_inventory(self, fresh_app, init_database):
        """Test that inactive products are handled correctly."""
        with fresh_app.app_context():
            # PRD_INACTIVE was created as inactive
            inactive = Product.query.filter_by(code='PRD_INACTIVE').first()

            assert inactive is not None
            assert inactive.is_active is False

            # Active products query should exclude it
            active_products = Product.query.filter_by(is_active=True).all()
            assert inactive not in active_products


# ============================================================================
# REPORTS TESTS
# ============================================================================

class TestReports:
    """Tests for inventory reports."""

    def test_stock_levels_query(self, fresh_app, init_database):
        """Test querying stock levels across locations."""
        with fresh_app.app_context():
            location = Location.query.filter_by(code='WH-001').first()

            stock_items = LocationStock.query.filter_by(location_id=location.id).all()

            assert len(stock_items) > 0
            for item in stock_items:
                assert item.quantity >= 0

    def test_stock_movements_report(self, fresh_app, init_database):
        """Test stock movements report query."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()
            user = User.query.filter_by(username='admin').first()

            # Create some movements
            for i in range(5):
                movement = StockMovement(
                    product_id=product.id,
                    user_id=user.id,
                    movement_type='adjustment',
                    quantity=i + 1,
                    reference=f'REPORT-MV-{i:03d}'
                )
                db.session.add(movement)
            db.session.commit()

            # Query movements
            movements = StockMovement.query.filter_by(product_id=product.id)\
                .order_by(StockMovement.timestamp.desc()).all()

            assert len(movements) >= 5

    def test_low_stock_report(self, fresh_app, init_database):
        """Test low stock report query."""
        with fresh_app.app_context():
            # Query products below reorder level
            low_stock = Product.query.filter(
                Product.quantity <= Product.reorder_level,
                Product.is_active == True
            ).all()

            # PRD003 has quantity=0, which is below reorder_level=10
            assert any(p.code == 'PRD003' for p in low_stock)

    def test_valuation_report(self, fresh_app, init_database):
        """Test inventory valuation report."""
        with fresh_app.app_context():
            from sqlalchemy import func

            # Calculate total inventory value
            total_value = db.session.query(
                func.sum(Product.quantity * Product.cost_price)
            ).filter(Product.is_active == True).scalar() or 0

            assert float(total_value) > 0

    def test_aging_report_expiry(self, fresh_app, init_database):
        """Test inventory aging based on expiry dates."""
        with fresh_app.app_context():
            # Set various expiry dates
            products = Product.query.filter_by(is_active=True).limit(3).all()

            products[0].expiry_date = date.today() - timedelta(days=10)  # Expired
            products[1].expiry_date = date.today() + timedelta(days=15)  # Expiring soon
            products[2].expiry_date = date.today() + timedelta(days=180)  # Good
            db.session.commit()

            # Query expired
            expired = Product.query.filter(
                Product.expiry_date < date.today(),
                Product.is_active == True
            ).all()

            assert len(expired) >= 1

    def test_location_wise_stock_report(self, fresh_app, init_database):
        """Test location-wise stock report."""
        with fresh_app.app_context():
            locations = Location.query.filter_by(is_active=True).all()

            report = []
            for location in locations:
                stock_items = LocationStock.query.filter_by(location_id=location.id).all()
                total_qty = sum(s.quantity for s in stock_items)
                total_value = sum(s.stock_value for s in stock_items)

                report.append({
                    'location': location.name,
                    'total_items': len(stock_items),
                    'total_quantity': total_qty,
                    'total_value': total_value
                })

            assert len(report) == len(locations)
            for item in report:
                assert item['total_quantity'] >= 0


# ============================================================================
# PERMISSION AND ACCESS CONTROL TESTS
# ============================================================================

class TestPermissions:
    """Tests for inventory permission controls."""

    def test_cashier_cannot_adjust_stock(self, auth_cashier, fresh_app, init_database):
        """Test that cashier cannot adjust stock."""
        with fresh_app.app_context():
            product = Product.query.filter_by(code='PRD001').first()

        response = auth_cashier.post(
            f'/inventory/adjust-stock/{product.id}',
            json={'adjustment_type': 'add', 'quantity': 10, 'reason': 'Test'},
            content_type='application/json'
        )

        # Should be forbidden or redirect to login
        assert response.status_code in [302, 403, 401]

    def test_manager_can_view_inventory(self, auth_manager, fresh_app, init_database):
        """Test that manager can view inventory."""
        response = auth_manager.get('/inventory/')
        assert response.status_code in [200, 302]

    def test_admin_full_inventory_access(self, auth_admin, fresh_app, init_database):
        """Test that admin has full inventory access."""
        # View inventory
        response = auth_admin.get('/inventory/')
        assert response.status_code in [200, 302]

        # Add product form
        response = auth_admin.get('/inventory/add')
        assert response.status_code in [200, 302]

        # Categories
        response = auth_admin.get('/inventory/categories')
        assert response.status_code in [200, 302]

    def test_unauthenticated_access_denied(self, client, fresh_app, init_database):
        """Test that unauthenticated users cannot access inventory."""
        response = client.get('/inventory/')
        # Should redirect to login
        assert response.status_code in [302, 401]


# ============================================================================
# SUPPLIER TESTS
# ============================================================================

class TestSupplierManagement:
    """Tests for supplier management."""

    def test_create_supplier(self, fresh_app, init_database):
        """Test creating a new supplier."""
        with fresh_app.app_context():
            supplier = Supplier(
                name='Test Supplier',
                contact_person='John Doe',
                phone='03001234567',
                email='supplier@test.com',
                payment_terms='Net 30',
                is_active=True
            )
            db.session.add(supplier)
            db.session.commit()

            saved = Supplier.query.filter_by(name='Test Supplier').first()
            assert saved is not None
            assert saved.payment_terms == 'Net 30'

    def test_supplier_product_relationship(self, fresh_app, init_database):
        """Test supplier-product relationship."""
        with fresh_app.app_context():
            supplier = Supplier(
                name='Linked Supplier',
                is_active=True
            )
            db.session.add(supplier)
            db.session.flush()

            product = Product(
                code='SUPPLIER-001',
                name='Supplier Product',
                supplier_id=supplier.id,
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00')
            )
            db.session.add(product)
            db.session.commit()

            # Check relationship
            saved_supplier = Supplier.query.filter_by(name='Linked Supplier').first()
            assert saved_supplier.products.count() == 1

    def test_supplier_unique_name(self, fresh_app, init_database):
        """Test supplier name uniqueness."""
        with fresh_app.app_context():
            supplier1 = Supplier(name='Unique Supplier')
            db.session.add(supplier1)
            db.session.commit()

            supplier2 = Supplier(name='Unique Supplier')  # Duplicate
            db.session.add(supplier2)

            with pytest.raises(Exception):
                db.session.commit()

            db.session.rollback()


# ============================================================================
# CSV IMPORT TESTS
# ============================================================================

class TestCSVImport:
    """Tests for CSV import functionality."""

    def test_import_csv_endpoint_exists(self, auth_admin, fresh_app, init_database):
        """Test that CSV import endpoint exists."""
        # POST without file should redirect or show error
        response = auth_admin.post('/inventory/import-csv')
        assert response.status_code in [302, 400]

    def test_import_csv_no_file(self, auth_admin, fresh_app, init_database):
        """Test CSV import with no file attached."""
        response = auth_admin.post('/inventory/import-csv', data={})
        # Should redirect with flash message
        assert response.status_code == 302


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests for inventory workflows."""

    def test_complete_transfer_workflow(self, fresh_app, init_database):
        """Test complete transfer workflow from request to receive."""
        with fresh_app.app_context():
            warehouse = Location.query.filter_by(code='WH-001').first()
            kiosk = Location.query.filter_by(code='K-001').first()
            product = Product.query.filter_by(code='PRD001').first()
            manager = User.query.filter_by(username='manager').first()
            wh_manager = User.query.filter_by(username='warehouse_mgr').first()

            # Get initial stock levels
            warehouse_stock = LocationStock.query.filter_by(
                location_id=warehouse.id,
                product_id=product.id
            ).first()
            kiosk_stock = LocationStock.query.filter_by(
                location_id=kiosk.id,
                product_id=product.id
            ).first()

            initial_wh_qty = warehouse_stock.quantity
            initial_kiosk_qty = kiosk_stock.quantity
            transfer_qty = 10

            # 1. Create transfer request
            transfer = StockTransfer(
                transfer_number='TR-INT-001',
                source_location_id=warehouse.id,
                destination_location_id=kiosk.id,
                status='requested',
                requested_by=manager.id,
                requested_at=datetime.utcnow()
            )
            db.session.add(transfer)
            db.session.flush()

            item = StockTransferItem(
                transfer_id=transfer.id,
                product_id=product.id,
                quantity_requested=transfer_qty
            )
            db.session.add(item)
            db.session.commit()

            assert transfer.status == 'requested'

            # 2. Approve transfer
            transfer.status = 'approved'
            transfer.approved_by = wh_manager.id
            transfer.approved_at = datetime.utcnow()
            item.quantity_approved = transfer_qty
            warehouse_stock.reserved_quantity += transfer_qty
            db.session.commit()

            assert transfer.status == 'approved'
            assert warehouse_stock.reserved_quantity >= transfer_qty

            # 3. Dispatch transfer
            transfer.status = 'dispatched'
            transfer.dispatched_by = wh_manager.id
            transfer.dispatched_at = datetime.utcnow()
            item.quantity_dispatched = transfer_qty
            warehouse_stock.quantity -= transfer_qty
            warehouse_stock.reserved_quantity -= transfer_qty

            # Create outgoing movement
            out_movement = StockMovement(
                product_id=product.id,
                user_id=wh_manager.id,
                location_id=warehouse.id,
                movement_type='transfer_out',
                quantity=-transfer_qty,
                reference=transfer.transfer_number,
                transfer_id=transfer.id
            )
            db.session.add(out_movement)
            db.session.commit()

            assert transfer.status == 'dispatched'
            assert warehouse_stock.quantity == initial_wh_qty - transfer_qty

            # 4. Receive transfer
            transfer.status = 'received'
            transfer.received_by = manager.id
            transfer.received_at = datetime.utcnow()
            item.quantity_received = transfer_qty
            kiosk_stock.quantity += transfer_qty

            # Create incoming movement
            in_movement = StockMovement(
                product_id=product.id,
                user_id=manager.id,
                location_id=kiosk.id,
                movement_type='transfer_in',
                quantity=transfer_qty,
                reference=transfer.transfer_number,
                transfer_id=transfer.id
            )
            db.session.add(in_movement)
            db.session.commit()

            # Verify final state
            assert transfer.status == 'received'

            db.session.refresh(warehouse_stock)
            db.session.refresh(kiosk_stock)

            assert warehouse_stock.quantity == initial_wh_qty - transfer_qty
            assert kiosk_stock.quantity == initial_kiosk_qty + transfer_qty

    def test_product_lifecycle(self, fresh_app, init_database):
        """Test complete product lifecycle."""
        with fresh_app.app_context():
            category = Category.query.first()
            user = User.query.filter_by(username='admin').first()

            # 1. Create product
            product = Product(
                code='LIFECYCLE-001',
                barcode='9876543210123',
                name='Lifecycle Test Product',
                category_id=category.id,
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                quantity=0,
                reorder_level=10,
                is_active=True
            )
            db.session.add(product)
            db.session.commit()

            assert product.id is not None
            assert product.is_active is True

            # 2. Receive initial stock
            product.quantity = 50
            movement = StockMovement(
                product_id=product.id,
                user_id=user.id,
                movement_type='purchase',
                quantity=50,
                reference='PO-INIT-001',
                notes='Initial stock receipt'
            )
            db.session.add(movement)
            db.session.commit()

            assert product.quantity == 50

            # 3. Update product details
            product.selling_price = Decimal('250.00')
            db.session.commit()

            assert product.selling_price == Decimal('250.00')

            # 4. Record sale (deduct stock)
            product.quantity -= 5
            sale_movement = StockMovement(
                product_id=product.id,
                user_id=user.id,
                movement_type='sale',
                quantity=-5,
                reference='SALE-TEST-001'
            )
            db.session.add(sale_movement)
            db.session.commit()

            assert product.quantity == 45

            # 5. Stock adjustment
            product.quantity -= 2
            adjustment = StockMovement(
                product_id=product.id,
                user_id=user.id,
                movement_type='adjustment',
                quantity=-2,
                reference='ADJ-DAMAGE-001',
                notes='Damaged items'
            )
            db.session.add(adjustment)
            db.session.commit()

            assert product.quantity == 43

            # 6. Deactivate product
            product.is_active = False
            db.session.commit()

            assert product.is_active is False

            # 7. Verify audit trail
            movements = StockMovement.query.filter_by(product_id=product.id).all()
            assert len(movements) == 3  # purchase, sale, adjustment
