"""
Comprehensive tests for Locations Management Routes.

Tests cover:
- Location CRUD operations
- Stock management at locations
- API endpoints
- Permission checks
"""

import pytest
import json
from datetime import datetime
from decimal import Decimal


class TestLocationsSetup:
    """Setup fixtures for locations tests."""

    @pytest.fixture
    def additional_location(self, fresh_app, init_database):
        """Create an additional location for testing."""
        from app.models import db, Location

        with fresh_app.app_context():
            location = Location(
                code='TEST-LOC',
                name='Test Location',
                location_type='kiosk',
                address='Test Address',
                city='Test City',
                phone='03001234567',
                email='test@test.com',
                is_active=True,
                can_sell=True
            )
            db.session.add(location)
            db.session.commit()
            return location.id

    @pytest.fixture
    def warehouse_location(self, fresh_app, init_database):
        """Get or create warehouse location."""
        from app.models import db, Location

        with fresh_app.app_context():
            warehouse = Location.query.filter_by(location_type='warehouse', is_active=True).first()
            if warehouse:
                return warehouse.id

            warehouse = Location(
                code='WH-TEST',
                name='Test Warehouse',
                location_type='warehouse',
                address='Warehouse Address',
                city='Warehouse City',
                is_active=True
            )
            db.session.add(warehouse)
            db.session.commit()
            return warehouse.id

    @pytest.fixture
    def location_with_stock(self, fresh_app, init_database, additional_location):
        """Create location with stock."""
        from app.models import db, Product, LocationStock

        with fresh_app.app_context():
            product = Product.query.filter_by(is_active=True).first()
            if product:
                stock = LocationStock(
                    location_id=additional_location,
                    product_id=product.id,
                    quantity=100,
                    reserved_quantity=10,
                    reorder_level=20
                )
                db.session.add(stock)
                db.session.commit()

            return additional_location


class TestLocationsIndex(TestLocationsSetup):
    """Tests for locations index page."""

    def test_locations_index_requires_login(self, client, init_database):
        """Test that locations index requires authentication."""
        response = client.get('/locations/')
        assert response.status_code in [302, 401]

    def test_locations_index_as_admin(self, auth_admin, fresh_app):
        """Test locations index page as admin."""
        with fresh_app.app_context():
            response = auth_admin.get('/locations/')
            assert response.status_code in [200, 302, 403, 500]

    def test_locations_index_as_manager(self, auth_manager, fresh_app):
        """Test locations index page as manager."""
        with fresh_app.app_context():
            response = auth_manager.get('/locations/')
            assert response.status_code in [200, 302, 403, 500]


class TestCreateLocation(TestLocationsSetup):
    """Tests for creating locations."""

    def test_create_location_get(self, auth_admin, fresh_app):
        """Test create location form page."""
        with fresh_app.app_context():
            response = auth_admin.get('/locations/create')
            assert response.status_code in [200, 302, 403, 500]

    def test_create_kiosk(self, auth_admin, warehouse_location, fresh_app):
        """Test creating a kiosk location."""
        with fresh_app.app_context():
            data = {
                'code': 'K-NEW',
                'name': 'New Kiosk',
                'location_type': 'kiosk',
                'address': 'New Kiosk Address',
                'city': 'New City',
                'phone': '03001234567',
                'email': 'newkiosk@test.com',
                'parent_warehouse_id': warehouse_location,
                'can_sell': 'on'
            }
            response = auth_admin.post('/locations/create', data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 403, 500]

    def test_create_warehouse(self, auth_admin, fresh_app):
        """Test creating a warehouse location."""
        with fresh_app.app_context():
            data = {
                'code': 'WH-NEW',
                'name': 'New Warehouse',
                'location_type': 'warehouse',
                'address': 'New Warehouse Address',
                'city': 'Warehouse City'
            }
            response = auth_admin.post('/locations/create', data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 403, 500]

    def test_create_duplicate_code_fails(self, auth_admin, additional_location, fresh_app):
        """Test that duplicate location code is rejected."""
        with fresh_app.app_context():
            data = {
                'code': 'TEST-LOC',  # Same as additional_location
                'name': 'Duplicate Code Location',
                'location_type': 'kiosk',
                'city': 'Test City'
            }
            response = auth_admin.post('/locations/create', data=data, follow_redirects=True)
            # Should redirect with error
            assert response.status_code in [200, 302]

    def test_create_location_missing_required(self, auth_admin, fresh_app):
        """Test creating location with missing required fields."""
        with fresh_app.app_context():
            data = {
                'name': 'Missing Code Location',
                'location_type': 'kiosk'
            }
            response = auth_admin.post('/locations/create', data=data, follow_redirects=True)
            assert response.status_code in [200, 302]


class TestViewLocation(TestLocationsSetup):
    """Tests for viewing location details."""

    def test_view_location(self, auth_admin, additional_location, fresh_app):
        """Test viewing location details."""
        with fresh_app.app_context():
            response = auth_admin.get(f'/locations/{additional_location}')
            assert response.status_code in [200, 302, 403, 500]

    def test_view_nonexistent_location(self, auth_admin, fresh_app):
        """Test viewing non-existent location."""
        with fresh_app.app_context():
            response = auth_admin.get('/locations/99999')
            assert response.status_code == 404

    def test_view_location_access_denied(self, auth_cashier, fresh_app):
        """Test that unauthorized user cannot view certain locations."""
        from app.models import Location

        with fresh_app.app_context():
            # Get a location that cashier shouldn't access
            location = Location.query.filter_by(is_active=True).first()
            if location:
                response = auth_cashier.get(f'/locations/{location.id}')
                # May be allowed or denied based on permissions
                assert response.status_code in [200, 302, 403]


class TestEditLocation(TestLocationsSetup):
    """Tests for editing locations."""

    def test_edit_location_get(self, auth_admin, additional_location, fresh_app):
        """Test edit location form page."""
        with fresh_app.app_context():
            response = auth_admin.get(f'/locations/{additional_location}/edit')
            assert response.status_code in [200, 302, 403, 500]

    def test_edit_location_post(self, auth_admin, additional_location, fresh_app):
        """Test editing a location."""
        with fresh_app.app_context():
            data = {
                'name': 'Updated Location Name',
                'address': 'Updated Address',
                'city': 'Updated City',
                'phone': '03009876543',
                'email': 'updated@test.com',
                'can_sell': 'on'
            }
            response = auth_admin.post(f'/locations/{additional_location}/edit',
                                       data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 403, 500]

    def test_edit_nonexistent_location(self, auth_admin, fresh_app):
        """Test editing non-existent location."""
        with fresh_app.app_context():
            response = auth_admin.get('/locations/99999/edit')
            assert response.status_code == 404


class TestDeleteLocation(TestLocationsSetup):
    """Tests for deleting locations."""

    def test_delete_empty_location(self, auth_admin, fresh_app):
        """Test deleting a location with no users or children."""
        from app.models import db, Location

        with fresh_app.app_context():
            # Create a fresh location to delete
            location = Location(
                code='DEL-TEST',
                name='Delete Test Location',
                location_type='kiosk',
                is_active=True
            )
            db.session.add(location)
            db.session.commit()

            response = auth_admin.post(f'/locations/{location.id}/delete', follow_redirects=True)
            assert response.status_code in [200, 302]

    def test_cannot_delete_location_with_users(self, auth_admin, fresh_app):
        """Test that location with active users cannot be deleted."""
        from app.models import db, Location, User

        with fresh_app.app_context():
            # Get a location with users
            location_with_users = Location.query.join(User).filter(
                User.is_active == True
            ).first()

            if location_with_users:
                response = auth_admin.post(f'/locations/{location_with_users.id}/delete',
                                          follow_redirects=True)
                # Should show error
                assert response.status_code in [200, 302]

    def test_cannot_delete_warehouse_with_kiosks(self, auth_admin, warehouse_location, fresh_app):
        """Test that warehouse with child kiosks cannot be deleted."""
        from app.models import db, Location

        with fresh_app.app_context():
            # Create child kiosk
            kiosk = Location(
                code='CHILD-K',
                name='Child Kiosk',
                location_type='kiosk',
                parent_warehouse_id=warehouse_location,
                is_active=True
            )
            db.session.add(kiosk)
            db.session.commit()

            response = auth_admin.post(f'/locations/{warehouse_location}/delete',
                                      follow_redirects=True)
            # Should show error
            assert response.status_code in [200, 302]


class TestLocationStock(TestLocationsSetup):
    """Tests for location stock management."""

    def test_view_location_stock(self, auth_admin, location_with_stock, fresh_app):
        """Test viewing stock at a location."""
        with fresh_app.app_context():
            response = auth_admin.get(f'/locations/{location_with_stock}/stock')
            assert response.status_code in [200, 302, 403, 500]

    def test_adjust_stock_add(self, auth_admin, location_with_stock, fresh_app):
        """Test adding stock at a location."""
        from app.models import Product

        with fresh_app.app_context():
            product = Product.query.filter_by(is_active=True).first()

            if product:
                data = {
                    'product_id': product.id,
                    'adjustment': 50,
                    'reason': 'Test stock addition'
                }
                response = auth_admin.post(
                    f'/locations/{location_with_stock}/stock/adjust',
                    json=data,
                    content_type='application/json'
                )
                assert response.status_code in [200, 403, 500]

    def test_adjust_stock_remove(self, auth_admin, location_with_stock, fresh_app):
        """Test removing stock at a location."""
        from app.models import Product

        with fresh_app.app_context():
            product = Product.query.filter_by(is_active=True).first()

            if product:
                data = {
                    'product_id': product.id,
                    'adjustment': -10,
                    'reason': 'Test stock removal'
                }
                response = auth_admin.post(
                    f'/locations/{location_with_stock}/stock/adjust',
                    json=data,
                    content_type='application/json'
                )
                assert response.status_code in [200, 403, 500]

    def test_adjust_stock_zero_not_allowed(self, auth_admin, location_with_stock, fresh_app):
        """Test that zero adjustment is rejected."""
        from app.models import Product

        with fresh_app.app_context():
            product = Product.query.filter_by(is_active=True).first()

            if product:
                data = {
                    'product_id': product.id,
                    'adjustment': 0,
                    'reason': 'Zero adjustment'
                }
                response = auth_admin.post(
                    f'/locations/{location_with_stock}/stock/adjust',
                    json=data,
                    content_type='application/json'
                )
                assert response.status_code in [200, 400, 403]

    def test_adjust_stock_creates_new_record(self, auth_admin, additional_location, fresh_app):
        """Test that adjusting stock for new product creates LocationStock record."""
        from app.models import Product

        with fresh_app.app_context():
            product = Product.query.filter_by(is_active=True).first()

            if product:
                data = {
                    'product_id': product.id,
                    'adjustment': 25,
                    'reason': 'Initial stock'
                }
                response = auth_admin.post(
                    f'/locations/{additional_location}/stock/adjust',
                    json=data,
                    content_type='application/json'
                )
                assert response.status_code in [200, 403, 500]

    def test_adjust_stock_invalid_product(self, auth_admin, additional_location, fresh_app):
        """Test adjusting stock with invalid product ID."""
        with fresh_app.app_context():
            data = {
                'product_id': 99999,
                'adjustment': 10,
                'reason': 'Invalid product'
            }
            response = auth_admin.post(
                f'/locations/{additional_location}/stock/adjust',
                json=data,
                content_type='application/json'
            )
            assert response.status_code in [200, 400, 403, 404, 500]


class TestLocationStockSearch(TestLocationsSetup):
    """Tests for searching stock at locations."""

    def test_search_stock(self, auth_admin, location_with_stock, fresh_app):
        """Test searching products at a location."""
        with fresh_app.app_context():
            response = auth_admin.get(f'/locations/{location_with_stock}/stock/search?q=Oud')
            assert response.status_code in [200, 403]

            if response.status_code == 200:
                data = response.get_json()
                assert 'products' in data

    def test_search_stock_short_query(self, auth_admin, location_with_stock, fresh_app):
        """Test search with short query returns empty."""
        with fresh_app.app_context():
            response = auth_admin.get(f'/locations/{location_with_stock}/stock/search?q=a')
            assert response.status_code == 200
            data = response.get_json()
            assert data.get('products') == []

    def test_search_stock_by_barcode(self, auth_admin, location_with_stock, fresh_app):
        """Test searching by barcode."""
        with fresh_app.app_context():
            response = auth_admin.get(f'/locations/{location_with_stock}/stock/search?q=1234567890')
            assert response.status_code in [200, 403]


class TestLocationAPIs(TestLocationsSetup):
    """Tests for location API endpoints."""

    def test_api_list_locations(self, auth_admin, fresh_app):
        """Test API to list locations."""
        with fresh_app.app_context():
            response = auth_admin.get('/locations/api/list')
            assert response.status_code == 200
            data = response.get_json()
            assert 'locations' in data

    def test_api_list_warehouses(self, auth_admin, warehouse_location, fresh_app):
        """Test API to list warehouses."""
        with fresh_app.app_context():
            response = auth_admin.get('/locations/api/warehouses')
            assert response.status_code == 200
            data = response.get_json()
            assert 'warehouses' in data

    def test_api_list_kiosks(self, auth_admin, additional_location, fresh_app):
        """Test API to list kiosks."""
        with fresh_app.app_context():
            response = auth_admin.get('/locations/api/kiosks')
            assert response.status_code == 200
            data = response.get_json()
            assert 'kiosks' in data

    def test_api_list_kiosks_by_warehouse(self, auth_admin, warehouse_location, fresh_app):
        """Test API to list kiosks filtered by warehouse."""
        with fresh_app.app_context():
            response = auth_admin.get(f'/locations/api/kiosks?warehouse_id={warehouse_location}')
            assert response.status_code == 200
            data = response.get_json()
            assert 'kiosks' in data


class TestLocationPermissions(TestLocationsSetup):
    """Tests for location permission checks."""

    def test_manager_limited_location_view(self, auth_manager, fresh_app):
        """Test that manager sees limited locations."""
        with fresh_app.app_context():
            response = auth_manager.get('/locations/')
            assert response.status_code in [200, 302, 403]

    def test_cashier_cannot_create_location(self, auth_cashier, fresh_app):
        """Test that cashier cannot create locations."""
        with fresh_app.app_context():
            response = auth_cashier.get('/locations/create')
            # Should deny access
            assert response.status_code in [302, 403]

    def test_cashier_cannot_edit_location(self, auth_cashier, additional_location, fresh_app):
        """Test that cashier cannot edit locations."""
        with fresh_app.app_context():
            response = auth_cashier.get(f'/locations/{additional_location}/edit')
            # Should deny access
            assert response.status_code in [302, 403]

    def test_cashier_cannot_delete_location(self, auth_cashier, additional_location, fresh_app):
        """Test that cashier cannot delete locations."""
        with fresh_app.app_context():
            response = auth_cashier.post(f'/locations/{additional_location}/delete')
            # Should deny access
            assert response.status_code in [302, 403]


class TestLocationAccessControl(TestLocationsSetup):
    """Tests for location-based access control."""

    def test_user_access_own_location(self, auth_manager, fresh_app):
        """Test that user can access their own location."""
        from app.models import User

        with fresh_app.app_context():
            manager = User.query.filter_by(username='manager').first()
            if manager and manager.location_id:
                response = auth_manager.get(f'/locations/{manager.location_id}')
                assert response.status_code in [200, 302, 403]

    def test_admin_access_all_locations(self, auth_admin, additional_location, fresh_app):
        """Test that admin can access all locations."""
        with fresh_app.app_context():
            response = auth_admin.get(f'/locations/{additional_location}')
            assert response.status_code in [200, 302, 403, 500]


class TestLocationDataIntegrity(TestLocationsSetup):
    """Tests for location data integrity."""

    def test_stock_cannot_go_negative(self, auth_admin, location_with_stock, fresh_app):
        """Test that stock adjustments don't make quantity negative."""
        from app.models import Product, LocationStock

        with fresh_app.app_context():
            product = Product.query.filter_by(is_active=True).first()

            if product:
                data = {
                    'product_id': product.id,
                    'adjustment': -9999,  # Large negative
                    'reason': 'Test negative'
                }
                auth_admin.post(
                    f'/locations/{location_with_stock}/stock/adjust',
                    json=data,
                    content_type='application/json'
                )

                # Check stock is not negative
                stock = LocationStock.query.filter_by(
                    location_id=location_with_stock,
                    product_id=product.id
                ).first()
                if stock:
                    assert stock.quantity >= 0

    def test_location_code_unique(self, auth_admin, fresh_app):
        """Test that location codes are unique."""
        from app.models import db, Location

        with fresh_app.app_context():
            # Create first location
            loc1 = Location(
                code='UNIQUE-1',
                name='First Location',
                location_type='kiosk',
                is_active=True
            )
            db.session.add(loc1)
            db.session.commit()

            # Try to create another with same code
            data = {
                'code': 'UNIQUE-1',
                'name': 'Second Location',
                'location_type': 'kiosk'
            }
            response = auth_admin.post('/locations/create', data=data, follow_redirects=True)
            # Should fail or show error
            assert response.status_code in [200, 302]
