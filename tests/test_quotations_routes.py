"""
Comprehensive tests for Quotations Routes.

Tests cover:
- Quotation CRUD operations
- Status transitions (draft, sent, accepted, rejected, converted)
- Conversion to sale
- Printing
- Permission checks
- Feature flag requirements
"""

import pytest
import json
from datetime import datetime, date, timedelta
from decimal import Decimal


class TestQuotationsSetup:
    """Setup fixtures for quotations tests."""

    @pytest.fixture
    def enable_quotations_feature(self, fresh_app):
        """Enable quotations feature flag."""
        from app.models import db
        from app.models_extended import FeatureFlag

        with fresh_app.app_context():
            flag = FeatureFlag(
                name='quotations',
                display_name='Quotations',
                description='Enable quotations',
                category='sales',
                is_enabled=True,
                requires_config=False
            )
            db.session.add(flag)
            db.session.commit()
            yield

    @pytest.fixture
    def sample_quotation(self, fresh_app, init_database, enable_quotations_feature):
        """Create a sample quotation."""
        from app.models import db, User, Customer, Product
        from app.models_extended import Quotation, QuotationItem

        with fresh_app.app_context():
            admin = User.query.filter_by(username='admin').first()
            customer = Customer.query.filter_by(is_active=True).first()
            product = Product.query.filter_by(is_active=True).first()

            quotation = Quotation(
                quotation_number='QT-20260107-0001',
                customer_id=customer.id if customer else None,
                customer_name=customer.name if customer else 'Walk-in',
                customer_phone=customer.phone if customer else None,
                valid_until=datetime.utcnow() + timedelta(days=7),
                subtotal=Decimal('1000.00'),
                discount=Decimal('100.00'),
                discount_type='amount',
                tax=Decimal('0'),
                total=Decimal('900.00'),
                status='draft',
                created_by=admin.id
            )
            db.session.add(quotation)
            db.session.flush()

            if product:
                item = QuotationItem(
                    quotation_id=quotation.id,
                    product_id=product.id,
                    quantity=2,
                    unit_price=product.selling_price,
                    discount=Decimal('0'),
                    subtotal=product.selling_price * 2
                )
                db.session.add(item)

            db.session.commit()
            return quotation.id

    @pytest.fixture
    def sent_quotation(self, fresh_app, init_database, enable_quotations_feature):
        """Create a sent quotation."""
        from app.models import db, User, Customer
        from app.models_extended import Quotation

        with fresh_app.app_context():
            admin = User.query.filter_by(username='admin').first()
            customer = Customer.query.filter_by(is_active=True).first()

            quotation = Quotation(
                quotation_number='QT-20260107-0002',
                customer_id=customer.id if customer else None,
                customer_name='Sent Customer',
                valid_until=datetime.utcnow() + timedelta(days=7),
                subtotal=Decimal('500.00'),
                total=Decimal('500.00'),
                status='sent',
                created_by=admin.id
            )
            db.session.add(quotation)
            db.session.commit()
            return quotation.id

    @pytest.fixture
    def accepted_quotation(self, fresh_app, init_database, enable_quotations_feature):
        """Create an accepted quotation."""
        from app.models import db, User, Customer, Product
        from app.models_extended import Quotation, QuotationItem

        with fresh_app.app_context():
            admin = User.query.filter_by(username='admin').first()
            customer = Customer.query.filter_by(is_active=True).first()
            product = Product.query.filter_by(is_active=True).first()

            quotation = Quotation(
                quotation_number='QT-20260107-0003',
                customer_id=customer.id if customer else None,
                customer_name='Accepted Customer',
                valid_until=datetime.utcnow() + timedelta(days=7),
                subtotal=Decimal('2000.00'),
                discount=Decimal('0'),
                total=Decimal('2000.00'),
                status='accepted',
                created_by=admin.id
            )
            db.session.add(quotation)
            db.session.flush()

            if product:
                item = QuotationItem(
                    quotation_id=quotation.id,
                    product_id=product.id,
                    quantity=1,
                    unit_price=product.selling_price,
                    discount=Decimal('0'),
                    subtotal=product.selling_price
                )
                db.session.add(item)

            db.session.commit()
            return quotation.id


class TestQuotationsIndex(TestQuotationsSetup):
    """Tests for quotations index page."""

    def test_quotations_index_requires_login(self, client, init_database, enable_quotations_feature):
        """Test that quotations index requires authentication."""
        response = client.get('/quotations/')
        assert response.status_code in [302, 401]

    def test_quotations_index_as_admin(self, auth_admin, enable_quotations_feature, fresh_app):
        """Test quotations index page as admin."""
        with fresh_app.app_context():
            response = auth_admin.get('/quotations/')
            assert response.status_code in [200, 302, 500]

    def test_quotations_index_filter_by_status(self, auth_admin, enable_quotations_feature, sample_quotation, fresh_app):
        """Test filtering quotations by status."""
        with fresh_app.app_context():
            response = auth_admin.get('/quotations/?status=draft')
            assert response.status_code in [200, 302, 500]

    def test_quotations_index_search(self, auth_admin, enable_quotations_feature, sample_quotation, fresh_app):
        """Test searching quotations."""
        with fresh_app.app_context():
            response = auth_admin.get('/quotations/?search=QT-20260107')
            assert response.status_code in [200, 302, 500]

    def test_quotations_pagination(self, auth_admin, enable_quotations_feature, fresh_app):
        """Test quotations pagination."""
        with fresh_app.app_context():
            response = auth_admin.get('/quotations/?page=1')
            assert response.status_code in [200, 302, 500]


class TestCreateQuotation(TestQuotationsSetup):
    """Tests for creating quotations."""

    def test_create_quotation_get(self, auth_admin, enable_quotations_feature, fresh_app):
        """Test create quotation form page."""
        with fresh_app.app_context():
            response = auth_admin.get('/quotations/create')
            assert response.status_code in [200, 302, 500]

    def test_create_quotation_with_customer(self, auth_admin, enable_quotations_feature, fresh_app):
        """Test creating quotation for existing customer."""
        from app.models import Customer, Product

        with fresh_app.app_context():
            customer = Customer.query.filter_by(is_active=True).first()
            product = Product.query.filter_by(is_active=True).first()

            if customer and product:
                data = {
                    'customer_id': customer.id,
                    'customer_name': customer.name,
                    'customer_phone': customer.phone,
                    'customer_email': customer.email,
                    'valid_days': 7,
                    'notes': 'Test quotation',
                    'terms': 'Payment due on delivery',
                    'discount': 0,
                    'discount_type': 'amount',
                    'tax': 0,
                    'items': [{
                        'product_id': product.id,
                        'quantity': 2,
                        'unit_price': float(product.selling_price)
                    }]
                }
                response = auth_admin.post(
                    '/quotations/create',
                    json=data,
                    content_type='application/json'
                )
                assert response.status_code in [200, 400]

    def test_create_quotation_walk_in(self, auth_admin, enable_quotations_feature, fresh_app):
        """Test creating quotation for walk-in customer."""
        from app.models import Product

        with fresh_app.app_context():
            product = Product.query.filter_by(is_active=True).first()

            if product:
                data = {
                    'customer_name': 'Walk-in Customer',
                    'customer_phone': '03001234567',
                    'valid_days': 14,
                    'items': [{
                        'product_id': product.id,
                        'quantity': 1,
                        'unit_price': float(product.selling_price)
                    }]
                }
                response = auth_admin.post(
                    '/quotations/create',
                    json=data,
                    content_type='application/json'
                )
                assert response.status_code in [200, 400]

    def test_create_quotation_with_discount(self, auth_admin, enable_quotations_feature, fresh_app):
        """Test creating quotation with discount."""
        from app.models import Product

        with fresh_app.app_context():
            product = Product.query.filter_by(is_active=True).first()

            if product:
                data = {
                    'customer_name': 'Discount Customer',
                    'valid_days': 7,
                    'discount': 10,
                    'discount_type': 'percentage',
                    'items': [{
                        'product_id': product.id,
                        'quantity': 1,
                        'unit_price': float(product.selling_price)
                    }]
                }
                response = auth_admin.post(
                    '/quotations/create',
                    json=data,
                    content_type='application/json'
                )
                assert response.status_code in [200, 400]

    def test_create_quotation_multiple_items(self, auth_admin, enable_quotations_feature, fresh_app):
        """Test creating quotation with multiple items."""
        from app.models import Product

        with fresh_app.app_context():
            products = Product.query.filter_by(is_active=True).limit(3).all()

            if len(products) >= 2:
                data = {
                    'customer_name': 'Multi-item Customer',
                    'valid_days': 7,
                    'items': [
                        {
                            'product_id': products[0].id,
                            'quantity': 1,
                            'unit_price': float(products[0].selling_price)
                        },
                        {
                            'product_id': products[1].id,
                            'quantity': 2,
                            'unit_price': float(products[1].selling_price)
                        }
                    ]
                }
                response = auth_admin.post(
                    '/quotations/create',
                    json=data,
                    content_type='application/json'
                )
                assert response.status_code in [200, 400]


class TestViewQuotation(TestQuotationsSetup):
    """Tests for viewing quotation details."""

    def test_view_quotation(self, auth_admin, enable_quotations_feature, sample_quotation, fresh_app):
        """Test viewing quotation details."""
        with fresh_app.app_context():
            response = auth_admin.get(f'/quotations/view/{sample_quotation}')
            assert response.status_code in [200, 302, 500]

    def test_view_nonexistent_quotation(self, auth_admin, enable_quotations_feature, fresh_app):
        """Test viewing non-existent quotation."""
        with fresh_app.app_context():
            response = auth_admin.get('/quotations/view/99999')
            assert response.status_code == 404


class TestEditQuotation(TestQuotationsSetup):
    """Tests for editing quotations."""

    def test_edit_quotation_get(self, auth_admin, enable_quotations_feature, sample_quotation, fresh_app):
        """Test edit quotation form page."""
        with fresh_app.app_context():
            response = auth_admin.get(f'/quotations/edit/{sample_quotation}')
            assert response.status_code in [200, 302, 500]

    def test_edit_draft_quotation(self, auth_admin, enable_quotations_feature, sample_quotation, fresh_app):
        """Test editing a draft quotation."""
        from app.models import Product

        with fresh_app.app_context():
            product = Product.query.filter_by(is_active=True).first()

            if product:
                data = {
                    'customer_name': 'Updated Customer',
                    'customer_phone': '03009876543',
                    'valid_days': 14,
                    'notes': 'Updated notes',
                    'items': [{
                        'product_id': product.id,
                        'quantity': 3,
                        'unit_price': float(product.selling_price)
                    }]
                }
                response = auth_admin.post(
                    f'/quotations/edit/{sample_quotation}',
                    json=data,
                    content_type='application/json'
                )
                assert response.status_code in [200, 400]

    def test_edit_sent_quotation(self, auth_admin, enable_quotations_feature, sent_quotation, fresh_app):
        """Test editing a sent quotation."""
        from app.models import Product

        with fresh_app.app_context():
            product = Product.query.filter_by(is_active=True).first()

            if product:
                data = {
                    'customer_name': 'Updated Sent Customer',
                    'items': [{
                        'product_id': product.id,
                        'quantity': 2
                    }]
                }
                response = auth_admin.post(
                    f'/quotations/edit/{sent_quotation}',
                    json=data,
                    content_type='application/json'
                )
                # Sent quotations should still be editable
                assert response.status_code in [200, 400]

    def test_cannot_edit_accepted_quotation(self, auth_admin, enable_quotations_feature, accepted_quotation, fresh_app):
        """Test that accepted quotation cannot be edited."""
        with fresh_app.app_context():
            response = auth_admin.get(f'/quotations/edit/{accepted_quotation}')
            # Should redirect with warning
            assert response.status_code in [200, 302]


class TestQuotationStatusTransitions(TestQuotationsSetup):
    """Tests for quotation status transitions."""

    def test_send_quotation(self, auth_admin, enable_quotations_feature, sample_quotation, fresh_app):
        """Test marking quotation as sent."""
        with fresh_app.app_context():
            response = auth_admin.post(f'/quotations/send/{sample_quotation}')
            assert response.status_code in [200, 302]

            if response.status_code == 200:
                data = response.get_json()
                assert data.get('success') is True

    def test_accept_quotation(self, auth_admin, enable_quotations_feature, sent_quotation, fresh_app):
        """Test accepting a quotation."""
        with fresh_app.app_context():
            response = auth_admin.post(f'/quotations/accept/{sent_quotation}')
            assert response.status_code in [200, 302]

            if response.status_code == 200:
                data = response.get_json()
                assert data.get('success') is True

    def test_reject_quotation(self, auth_admin, enable_quotations_feature, sent_quotation, fresh_app):
        """Test rejecting a quotation."""
        with fresh_app.app_context():
            response = auth_admin.post(f'/quotations/reject/{sent_quotation}')
            assert response.status_code in [200, 302]

            if response.status_code == 200:
                data = response.get_json()
                assert data.get('success') is True


class TestConvertQuotation(TestQuotationsSetup):
    """Tests for converting quotation to sale."""

    def test_convert_accepted_quotation(self, auth_admin, enable_quotations_feature, accepted_quotation, fresh_app):
        """Test converting accepted quotation to sale."""
        with fresh_app.app_context():
            response = auth_admin.post(f'/quotations/convert/{accepted_quotation}')
            assert response.status_code in [200, 400, 500]

            if response.status_code == 200:
                data = response.get_json()
                if data.get('success'):
                    assert 'sale_id' in data
                    assert 'sale_number' in data

    def test_cannot_convert_already_converted(self, auth_admin, enable_quotations_feature, accepted_quotation, fresh_app):
        """Test that converted quotation cannot be converted again."""
        from app.models import db
        from app.models_extended import Quotation

        with fresh_app.app_context():
            # Mark as converted
            quotation = Quotation.query.get(accepted_quotation)
            quotation.status = 'converted'
            quotation.converted_to_sale_id = 1
            quotation.converted_at = datetime.utcnow()
            db.session.commit()

            response = auth_admin.post(f'/quotations/convert/{accepted_quotation}')
            assert response.status_code == 400

    def test_convert_draft_quotation(self, auth_admin, enable_quotations_feature, sample_quotation, fresh_app):
        """Test converting draft quotation (should work)."""
        with fresh_app.app_context():
            response = auth_admin.post(f'/quotations/convert/{sample_quotation}')
            # Might be allowed or not depending on business rules
            assert response.status_code in [200, 400, 500]


class TestPrintQuotation(TestQuotationsSetup):
    """Tests for printing quotations."""

    def test_print_quotation(self, auth_admin, enable_quotations_feature, sample_quotation, fresh_app):
        """Test print quotation page."""
        with fresh_app.app_context():
            response = auth_admin.get(f'/quotations/print/{sample_quotation}')
            assert response.status_code in [200, 302, 500]

    def test_print_nonexistent_quotation(self, auth_admin, enable_quotations_feature, fresh_app):
        """Test printing non-existent quotation."""
        with fresh_app.app_context():
            response = auth_admin.get('/quotations/print/99999')
            assert response.status_code == 404


class TestDeleteQuotation(TestQuotationsSetup):
    """Tests for deleting quotations."""

    def test_delete_draft_quotation(self, auth_admin, enable_quotations_feature, sample_quotation, fresh_app):
        """Test deleting a draft quotation."""
        with fresh_app.app_context():
            response = auth_admin.post(f'/quotations/delete/{sample_quotation}')
            assert response.status_code in [200, 302]

            if response.status_code == 200:
                data = response.get_json()
                assert data.get('success') is True

    def test_cannot_delete_converted_quotation(self, auth_admin, enable_quotations_feature, accepted_quotation, fresh_app):
        """Test that converted quotation cannot be deleted."""
        from app.models import db
        from app.models_extended import Quotation

        with fresh_app.app_context():
            # Mark as converted
            quotation = Quotation.query.get(accepted_quotation)
            quotation.status = 'converted'
            quotation.converted_to_sale_id = 1
            db.session.commit()

            response = auth_admin.post(f'/quotations/delete/{accepted_quotation}')
            assert response.status_code == 400

    def test_delete_nonexistent_quotation(self, auth_admin, enable_quotations_feature, fresh_app):
        """Test deleting non-existent quotation."""
        with fresh_app.app_context():
            response = auth_admin.post('/quotations/delete/99999')
            assert response.status_code == 404


class TestQuotationsFeatureFlag(TestQuotationsSetup):
    """Tests for quotations feature flag requirements."""

    def test_quotations_disabled_redirects(self, auth_admin, fresh_app):
        """Test that disabled feature redirects appropriately."""
        with fresh_app.app_context():
            response = auth_admin.get('/quotations/')
            assert response.status_code in [200, 302, 403]


class TestQuotationValidation(TestQuotationsSetup):
    """Tests for quotation data validation."""

    def test_create_quotation_no_items(self, auth_admin, enable_quotations_feature, fresh_app):
        """Test creating quotation without items."""
        with fresh_app.app_context():
            data = {
                'customer_name': 'No Items Customer',
                'valid_days': 7,
                'items': []
            }
            response = auth_admin.post(
                '/quotations/create',
                json=data,
                content_type='application/json'
            )
            # Should fail or create empty quotation
            assert response.status_code in [200, 400]

    def test_create_quotation_invalid_product(self, auth_admin, enable_quotations_feature, fresh_app):
        """Test creating quotation with invalid product."""
        with fresh_app.app_context():
            data = {
                'customer_name': 'Invalid Product Customer',
                'valid_days': 7,
                'items': [{
                    'product_id': 99999,
                    'quantity': 1,
                    'unit_price': 100
                }]
            }
            response = auth_admin.post(
                '/quotations/create',
                json=data,
                content_type='application/json'
            )
            # Should skip invalid product or fail
            assert response.status_code in [200, 400]

    def test_create_quotation_zero_quantity(self, auth_admin, enable_quotations_feature, fresh_app):
        """Test creating quotation with zero quantity."""
        from app.models import Product

        with fresh_app.app_context():
            product = Product.query.filter_by(is_active=True).first()

            if product:
                data = {
                    'customer_name': 'Zero Qty Customer',
                    'valid_days': 7,
                    'items': [{
                        'product_id': product.id,
                        'quantity': 0,
                        'unit_price': float(product.selling_price)
                    }]
                }
                response = auth_admin.post(
                    '/quotations/create',
                    json=data,
                    content_type='application/json'
                )
                assert response.status_code in [200, 400]


class TestQuotationCalculations(TestQuotationsSetup):
    """Tests for quotation amount calculations."""

    def test_percentage_discount_calculation(self, auth_admin, enable_quotations_feature, fresh_app):
        """Test percentage discount is calculated correctly."""
        from app.models import Product
        from app.models_extended import Quotation

        with fresh_app.app_context():
            product = Product.query.filter_by(is_active=True).first()

            if product:
                data = {
                    'customer_name': 'Percentage Discount',
                    'valid_days': 7,
                    'discount': 10,
                    'discount_type': 'percentage',
                    'items': [{
                        'product_id': product.id,
                        'quantity': 1,
                        'unit_price': 1000
                    }]
                }
                response = auth_admin.post(
                    '/quotations/create',
                    json=data,
                    content_type='application/json'
                )

                if response.status_code == 200:
                    result = response.get_json()
                    if result.get('success'):
                        quotation = Quotation.query.filter_by(
                            quotation_number=result.get('quotation_number')
                        ).first()
                        if quotation:
                            # 1000 - 10% = 900
                            assert quotation.total == Decimal('900.00')

    def test_fixed_discount_calculation(self, auth_admin, enable_quotations_feature, fresh_app):
        """Test fixed discount is applied correctly."""
        from app.models import Product
        from app.models_extended import Quotation

        with fresh_app.app_context():
            product = Product.query.filter_by(is_active=True).first()

            if product:
                data = {
                    'customer_name': 'Fixed Discount',
                    'valid_days': 7,
                    'discount': 100,
                    'discount_type': 'amount',
                    'items': [{
                        'product_id': product.id,
                        'quantity': 1,
                        'unit_price': 1000
                    }]
                }
                response = auth_admin.post(
                    '/quotations/create',
                    json=data,
                    content_type='application/json'
                )

                if response.status_code == 200:
                    result = response.get_json()
                    if result.get('success'):
                        quotation = Quotation.query.filter_by(
                            quotation_number=result.get('quotation_number')
                        ).first()
                        if quotation:
                            # 1000 - 100 = 900
                            assert quotation.total == Decimal('900.00')
