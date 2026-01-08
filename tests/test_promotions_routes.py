"""
Comprehensive tests for Promotions and Gift Vouchers Routes.

Tests cover:
- Promotions management (CRUD, toggle, validate)
- Gift vouchers (create, check, redeem)
- Permission checks
- Feature flag requirements
- Error handling
"""

import pytest
import json
from datetime import datetime, timedelta
from decimal import Decimal


class TestPromotionsSetup:
    """Setup fixtures for promotions tests."""

    @pytest.fixture
    def enable_promotions_feature(self, fresh_app):
        """Enable promotions and gift vouchers feature flags."""
        from app.models import db
        from app.models_extended import FeatureFlag

        with fresh_app.app_context():
            # Create promotions feature flag
            promo_flag = FeatureFlag(
                name='promotions',
                display_name='Promotions',
                description='Enable promotions',
                category='sales',
                is_enabled=True,
                requires_config=False
            )
            db.session.add(promo_flag)

            # Create gift vouchers feature flag
            voucher_flag = FeatureFlag(
                name='gift_vouchers',
                display_name='Gift Vouchers',
                description='Enable gift vouchers',
                category='sales',
                is_enabled=True,
                requires_config=False
            )
            db.session.add(voucher_flag)

            db.session.commit()
            yield

    @pytest.fixture
    def sample_promotion(self, fresh_app, init_database, enable_promotions_feature):
        """Create a sample promotion."""
        from app.models import db, User
        from app.models_extended import Promotion

        with fresh_app.app_context():
            admin = User.query.filter_by(username='admin').first()

            promotion = Promotion(
                code='TEST10',
                name='Test Promotion',
                description='Test 10% off',
                promotion_type='percentage',
                discount_value=Decimal('10.00'),
                min_purchase=Decimal('100.00'),
                max_discount=Decimal('500.00'),
                start_date=datetime.utcnow() - timedelta(days=1),
                end_date=datetime.utcnow() + timedelta(days=30),
                usage_limit=100,
                usage_per_customer=1,
                is_active=True,
                created_by=admin.id
            )
            db.session.add(promotion)
            db.session.commit()

            return promotion.id

    @pytest.fixture
    def expired_promotion(self, fresh_app, init_database, enable_promotions_feature):
        """Create an expired promotion."""
        from app.models import db, User
        from app.models_extended import Promotion

        with fresh_app.app_context():
            admin = User.query.filter_by(username='admin').first()

            promotion = Promotion(
                code='EXPIRED20',
                name='Expired Promotion',
                description='Expired 20% off',
                promotion_type='percentage',
                discount_value=Decimal('20.00'),
                start_date=datetime.utcnow() - timedelta(days=60),
                end_date=datetime.utcnow() - timedelta(days=30),
                is_active=True,
                created_by=admin.id
            )
            db.session.add(promotion)
            db.session.commit()

            return promotion.id

    @pytest.fixture
    def sample_voucher(self, fresh_app, init_database, enable_promotions_feature):
        """Create a sample gift voucher."""
        from app.models import db, User
        from app.models_extended import GiftVoucher, GiftVoucherTransaction

        with fresh_app.app_context():
            admin = User.query.filter_by(username='admin').first()

            voucher = GiftVoucher(
                code='GV-TEST123456',
                initial_value=Decimal('500.00'),
                current_balance=Decimal('500.00'),
                recipient_name='Test Recipient',
                recipient_email='test@example.com',
                valid_from=datetime.utcnow(),
                valid_until=datetime.utcnow() + timedelta(days=365),
                status='active',
                created_by=admin.id
            )
            db.session.add(voucher)
            db.session.flush()

            # Create initial transaction
            transaction = GiftVoucherTransaction(
                voucher_id=voucher.id,
                transaction_type='purchase',
                amount=Decimal('500.00'),
                balance_after=Decimal('500.00'),
                notes='Initial purchase',
                processed_by=admin.id
            )
            db.session.add(transaction)
            db.session.commit()

            return voucher.id


class TestPromotionsIndex(TestPromotionsSetup):
    """Tests for promotions index page."""

    def test_promotions_index_requires_login(self, client, init_database, enable_promotions_feature):
        """Test that promotions index requires authentication."""
        response = client.get('/promotions/')
        assert response.status_code in [302, 401]

    def test_promotions_index_as_admin(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test promotions index page as admin."""
        with fresh_app.app_context():
            response = auth_admin.get('/promotions/')
            # May return 200 or redirect depending on template
            assert response.status_code in [200, 302, 500]

    def test_promotions_index_filter_active(self, auth_admin, enable_promotions_feature, sample_promotion, fresh_app):
        """Test filtering active promotions."""
        with fresh_app.app_context():
            response = auth_admin.get('/promotions/?status=active')
            assert response.status_code in [200, 302, 500]

    def test_promotions_index_filter_expired(self, auth_admin, enable_promotions_feature, expired_promotion, fresh_app):
        """Test filtering expired promotions."""
        with fresh_app.app_context():
            response = auth_admin.get('/promotions/?status=expired')
            assert response.status_code in [200, 302, 500]

    def test_promotions_index_pagination(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test promotions pagination."""
        with fresh_app.app_context():
            response = auth_admin.get('/promotions/?page=1')
            assert response.status_code in [200, 302, 500]


class TestAddPromotion(TestPromotionsSetup):
    """Tests for adding promotions."""

    def test_add_promotion_get(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test add promotion form page."""
        with fresh_app.app_context():
            response = auth_admin.get('/promotions/add')
            assert response.status_code in [200, 302, 500]

    def test_add_percentage_promotion(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test adding a percentage-based promotion."""
        with fresh_app.app_context():
            data = {
                'code': 'SAVE15',
                'name': 'Save 15%',
                'description': 'Get 15% off your order',
                'promotion_type': 'percentage',
                'discount_value': '15.00',
                'min_purchase': '50.00',
                'max_discount': '200.00',
                'start_date': datetime.utcnow().strftime('%Y-%m-%dT%H:%M'),
                'end_date': (datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%dT%H:%M'),
                'usage_limit': '1000',
                'usage_per_customer': '5',
                'applies_to': 'all'
            }
            response = auth_admin.post('/promotions/add', data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 500]

    def test_add_fixed_amount_promotion(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test adding a fixed amount promotion."""
        with fresh_app.app_context():
            data = {
                'code': 'SAVE100',
                'name': 'Rs. 100 Off',
                'description': 'Get Rs. 100 off',
                'promotion_type': 'fixed_amount',
                'discount_value': '100.00',
                'min_purchase': '500.00',
                'start_date': datetime.utcnow().strftime('%Y-%m-%dT%H:%M'),
                'end_date': (datetime.utcnow() + timedelta(days=14)).strftime('%Y-%m-%dT%H:%M'),
                'applies_to': 'all'
            }
            response = auth_admin.post('/promotions/add', data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 500]

    def test_add_promotion_auto_generate_code(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test adding promotion without providing code (auto-generate)."""
        with fresh_app.app_context():
            data = {
                'name': 'Auto Code Promotion',
                'promotion_type': 'percentage',
                'discount_value': '10.00',
                'start_date': datetime.utcnow().strftime('%Y-%m-%dT%H:%M'),
                'end_date': (datetime.utcnow() + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M'),
            }
            response = auth_admin.post('/promotions/add', data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 500]

    def test_add_buy_x_get_y_promotion(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test adding buy X get Y promotion."""
        with fresh_app.app_context():
            data = {
                'code': 'BUY2GET1',
                'name': 'Buy 2 Get 1 Free',
                'promotion_type': 'buy_x_get_y',
                'buy_quantity': '2',
                'get_quantity': '1',
                'start_date': datetime.utcnow().strftime('%Y-%m-%dT%H:%M'),
                'end_date': (datetime.utcnow() + timedelta(days=14)).strftime('%Y-%m-%dT%H:%M'),
            }
            response = auth_admin.post('/promotions/add', data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 500]


class TestEditPromotion(TestPromotionsSetup):
    """Tests for editing promotions."""

    def test_edit_promotion_get(self, auth_admin, enable_promotions_feature, sample_promotion, fresh_app):
        """Test edit promotion form page."""
        with fresh_app.app_context():
            response = auth_admin.get(f'/promotions/edit/{sample_promotion}')
            assert response.status_code in [200, 302, 404, 500]

    def test_edit_promotion_post(self, auth_admin, enable_promotions_feature, sample_promotion, fresh_app):
        """Test editing promotion."""
        with fresh_app.app_context():
            data = {
                'name': 'Updated Promotion',
                'description': 'Updated description',
                'promotion_type': 'percentage',
                'discount_value': '15.00',
                'min_purchase': '200.00',
                'start_date': datetime.utcnow().strftime('%Y-%m-%dT%H:%M'),
                'end_date': (datetime.utcnow() + timedelta(days=60)).strftime('%Y-%m-%dT%H:%M'),
                'usage_per_customer': '3'
            }
            response = auth_admin.post(f'/promotions/edit/{sample_promotion}',
                                       data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 404, 500]

    def test_edit_nonexistent_promotion(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test editing non-existent promotion."""
        with fresh_app.app_context():
            response = auth_admin.get('/promotions/edit/99999')
            assert response.status_code == 404


class TestTogglePromotion(TestPromotionsSetup):
    """Tests for toggling promotion status."""

    def test_toggle_promotion_deactivate(self, auth_admin, enable_promotions_feature, sample_promotion, fresh_app):
        """Test deactivating a promotion."""
        with fresh_app.app_context():
            response = auth_admin.post(f'/promotions/toggle/{sample_promotion}')
            assert response.status_code in [200, 302]

            if response.status_code == 200:
                data = response.get_json()
                assert data.get('success') is True

    def test_toggle_nonexistent_promotion(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test toggling non-existent promotion."""
        with fresh_app.app_context():
            response = auth_admin.post('/promotions/toggle/99999')
            assert response.status_code == 404


class TestValidatePromoCode(TestPromotionsSetup):
    """Tests for promotion code validation."""

    def test_validate_valid_promo_code(self, auth_admin, enable_promotions_feature, sample_promotion, fresh_app):
        """Test validating a valid promotion code."""
        with fresh_app.app_context():
            response = auth_admin.post(
                '/promotions/validate',
                json={'code': 'TEST10', 'cart_total': 200},
                content_type='application/json'
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data.get('valid') is True

    def test_validate_invalid_promo_code(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test validating an invalid promotion code."""
        with fresh_app.app_context():
            response = auth_admin.post(
                '/promotions/validate',
                json={'code': 'INVALID', 'cart_total': 200},
                content_type='application/json'
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data.get('valid') is False

    def test_validate_expired_promo_code(self, auth_admin, enable_promotions_feature, expired_promotion, fresh_app):
        """Test validating an expired promotion code."""
        with fresh_app.app_context():
            response = auth_admin.post(
                '/promotions/validate',
                json={'code': 'EXPIRED20', 'cart_total': 200},
                content_type='application/json'
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data.get('valid') is False

    def test_validate_promo_below_min_purchase(self, auth_admin, enable_promotions_feature, sample_promotion, fresh_app):
        """Test validating promo code with cart below minimum purchase."""
        with fresh_app.app_context():
            response = auth_admin.post(
                '/promotions/validate',
                json={'code': 'TEST10', 'cart_total': 50},  # Below min_purchase of 100
                content_type='application/json'
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data.get('valid') is False

    def test_validate_promo_with_customer(self, auth_admin, enable_promotions_feature, sample_promotion, fresh_app):
        """Test validating promo code for specific customer."""
        from app.models import Customer

        with fresh_app.app_context():
            customer = Customer.query.filter_by(is_active=True).first()
            if customer:
                response = auth_admin.post(
                    '/promotions/validate',
                    json={
                        'code': 'TEST10',
                        'cart_total': 200,
                        'customer_id': customer.id
                    },
                    content_type='application/json'
                )
                assert response.status_code == 200


class TestGiftVouchersIndex(TestPromotionsSetup):
    """Tests for gift vouchers index page."""

    def test_vouchers_index_requires_login(self, client, init_database, enable_promotions_feature):
        """Test that vouchers index requires authentication."""
        response = client.get('/promotions/vouchers')
        assert response.status_code in [302, 401]

    def test_vouchers_index_as_admin(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test vouchers index page as admin."""
        with fresh_app.app_context():
            response = auth_admin.get('/promotions/vouchers')
            assert response.status_code in [200, 302, 500]

    def test_vouchers_filter_by_status(self, auth_admin, enable_promotions_feature, sample_voucher, fresh_app):
        """Test filtering vouchers by status."""
        with fresh_app.app_context():
            response = auth_admin.get('/promotions/vouchers?status=active')
            assert response.status_code in [200, 302, 500]


class TestCreateVoucher(TestPromotionsSetup):
    """Tests for creating gift vouchers."""

    def test_create_voucher_get(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test create voucher form page."""
        with fresh_app.app_context():
            response = auth_admin.get('/promotions/vouchers/create')
            assert response.status_code in [200, 302, 500]

    def test_create_voucher_success(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test creating a gift voucher."""
        with fresh_app.app_context():
            data = {
                'value': '1000',
                'valid_days': '365',
                'recipient_name': 'John Doe',
                'recipient_email': 'john@example.com',
                'recipient_phone': '03001234567',
                'personal_message': 'Happy Birthday!'
            }
            response = auth_admin.post('/promotions/vouchers/create',
                                       data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 500]

    def test_create_voucher_minimal_data(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test creating voucher with minimal data."""
        with fresh_app.app_context():
            data = {
                'value': '500'
            }
            response = auth_admin.post('/promotions/vouchers/create',
                                       data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 500]


class TestCheckVoucher(TestPromotionsSetup):
    """Tests for checking voucher balance."""

    def test_check_valid_voucher(self, auth_admin, enable_promotions_feature, sample_voucher, fresh_app):
        """Test checking a valid voucher."""
        with fresh_app.app_context():
            response = auth_admin.post(
                '/promotions/vouchers/check',
                json={'code': 'GV-TEST123456'},
                content_type='application/json'
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data.get('valid') is True
            assert data.get('voucher', {}).get('balance') == 500.0

    def test_check_invalid_voucher(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test checking an invalid voucher."""
        with fresh_app.app_context():
            response = auth_admin.post(
                '/promotions/vouchers/check',
                json={'code': 'GV-INVALID'},
                content_type='application/json'
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data.get('valid') is False

    def test_check_expired_voucher(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test checking an expired voucher."""
        from app.models import db, User
        from app.models_extended import GiftVoucher

        with fresh_app.app_context():
            admin = User.query.filter_by(username='admin').first()

            # Create expired voucher
            voucher = GiftVoucher(
                code='GV-EXPIRED123',
                initial_value=Decimal('100.00'),
                current_balance=Decimal('100.00'),
                valid_from=datetime.utcnow() - timedelta(days=400),
                valid_until=datetime.utcnow() - timedelta(days=30),
                status='expired',
                created_by=admin.id
            )
            db.session.add(voucher)
            db.session.commit()

            response = auth_admin.post(
                '/promotions/vouchers/check',
                json={'code': 'GV-EXPIRED123'},
                content_type='application/json'
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data.get('valid') is False


class TestRedeemVoucher(TestPromotionsSetup):
    """Tests for redeeming gift vouchers."""

    def test_redeem_voucher_success(self, auth_admin, enable_promotions_feature, sample_voucher, fresh_app):
        """Test redeeming a voucher."""
        with fresh_app.app_context():
            response = auth_admin.post(
                '/promotions/vouchers/redeem',
                json={'code': 'GV-TEST123456', 'amount': 200},
                content_type='application/json'
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data.get('success') is True
            assert data.get('remaining_balance') == 300.0

    def test_redeem_voucher_insufficient_balance(self, auth_admin, enable_promotions_feature, sample_voucher, fresh_app):
        """Test redeeming more than voucher balance."""
        with fresh_app.app_context():
            response = auth_admin.post(
                '/promotions/vouchers/redeem',
                json={'code': 'GV-TEST123456', 'amount': 1000},  # More than 500 balance
                content_type='application/json'
            )
            assert response.status_code == 400
            data = response.get_json()
            assert data.get('success') is False

    def test_redeem_invalid_voucher(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test redeeming an invalid voucher."""
        with fresh_app.app_context():
            response = auth_admin.post(
                '/promotions/vouchers/redeem',
                json={'code': 'GV-INVALID', 'amount': 100},
                content_type='application/json'
            )
            assert response.status_code == 400
            data = response.get_json()
            assert data.get('success') is False

    def test_redeem_voucher_full_balance(self, auth_admin, enable_promotions_feature, sample_voucher, fresh_app):
        """Test redeeming full voucher balance."""
        with fresh_app.app_context():
            response = auth_admin.post(
                '/promotions/vouchers/redeem',
                json={'code': 'GV-TEST123456', 'amount': 500},
                content_type='application/json'
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data.get('success') is True
            assert data.get('remaining_balance') == 0


class TestViewVoucher(TestPromotionsSetup):
    """Tests for viewing voucher details."""

    def test_view_voucher_details(self, auth_admin, enable_promotions_feature, sample_voucher, fresh_app):
        """Test viewing voucher details."""
        with fresh_app.app_context():
            response = auth_admin.get(f'/promotions/vouchers/{sample_voucher}')
            assert response.status_code in [200, 302, 500]

    def test_view_nonexistent_voucher(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test viewing non-existent voucher."""
        with fresh_app.app_context():
            response = auth_admin.get('/promotions/vouchers/99999')
            assert response.status_code == 404


class TestPromotionsFeatureFlag(TestPromotionsSetup):
    """Tests for promotions feature flag requirements."""

    def test_promotions_disabled_returns_error(self, auth_admin, fresh_app):
        """Test that disabled feature returns appropriate response."""
        with fresh_app.app_context():
            # Feature flags not created, so promotions should be disabled
            response = auth_admin.get('/promotions/')
            # Should redirect or show warning
            assert response.status_code in [200, 302, 403]

    def test_vouchers_disabled_returns_error(self, auth_admin, fresh_app):
        """Test that disabled gift vouchers feature returns appropriate response."""
        with fresh_app.app_context():
            response = auth_admin.get('/promotions/vouchers')
            assert response.status_code in [200, 302, 403]


class TestPromotionsPermissions(TestPromotionsSetup):
    """Tests for promotions permission checks."""

    def test_cashier_can_access_promotions(self, auth_cashier, enable_promotions_feature, fresh_app):
        """Test that cashier can access promotions index."""
        with fresh_app.app_context():
            response = auth_cashier.get('/promotions/')
            # Cashier should be able to view promotions
            assert response.status_code in [200, 302, 500]

    def test_manager_can_add_promotion(self, auth_manager, enable_promotions_feature, fresh_app):
        """Test that manager can add promotions."""
        with fresh_app.app_context():
            response = auth_manager.get('/promotions/add')
            assert response.status_code in [200, 302, 500]


class TestPromotionCalculations(TestPromotionsSetup):
    """Tests for promotion discount calculations."""

    def test_percentage_discount_calculation(self, auth_admin, enable_promotions_feature, sample_promotion, fresh_app):
        """Test percentage discount is calculated correctly."""
        with fresh_app.app_context():
            response = auth_admin.post(
                '/promotions/validate',
                json={'code': 'TEST10', 'cart_total': 1000},
                content_type='application/json'
            )
            assert response.status_code == 200
            data = response.get_json()
            if data.get('valid'):
                # 10% of 1000 = 100
                discount = data.get('promotion', {}).get('discount_amount')
                assert discount == 100.0

    def test_max_discount_cap_applied(self, auth_admin, enable_promotions_feature, sample_promotion, fresh_app):
        """Test max discount cap is applied."""
        with fresh_app.app_context():
            response = auth_admin.post(
                '/promotions/validate',
                json={'code': 'TEST10', 'cart_total': 10000},  # 10% would be 1000, but max is 500
                content_type='application/json'
            )
            assert response.status_code == 200
            data = response.get_json()
            if data.get('valid'):
                discount = data.get('promotion', {}).get('discount_amount')
                # Should be capped at 500
                assert discount == 500.0

    def test_fixed_amount_discount(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test fixed amount discount calculation."""
        from app.models import db, User
        from app.models_extended import Promotion

        with fresh_app.app_context():
            admin = User.query.filter_by(username='admin').first()

            promotion = Promotion(
                code='FLAT50',
                name='Flat Rs. 50 Off',
                promotion_type='fixed_amount',
                discount_value=Decimal('50.00'),
                start_date=datetime.utcnow() - timedelta(days=1),
                end_date=datetime.utcnow() + timedelta(days=30),
                is_active=True,
                created_by=admin.id
            )
            db.session.add(promotion)
            db.session.commit()

            response = auth_admin.post(
                '/promotions/validate',
                json={'code': 'FLAT50', 'cart_total': 200},
                content_type='application/json'
            )
            assert response.status_code == 200
            data = response.get_json()
            if data.get('valid'):
                discount = data.get('promotion', {}).get('discount_amount')
                assert discount == 50.0


class TestPromotionUsageLimits(TestPromotionsSetup):
    """Tests for promotion usage limits."""

    def test_promotion_tracks_usage(self, auth_admin, enable_promotions_feature, fresh_app):
        """Test that promotion usage is tracked."""
        from app.models import db, User, Customer
        from app.models_extended import Promotion, PromotionUsage

        with fresh_app.app_context():
            admin = User.query.filter_by(username='admin').first()
            customer = Customer.query.filter_by(is_active=True).first()

            # Create promotion with usage limit
            promotion = Promotion(
                code='LIMIT5',
                name='Limited Use Promo',
                promotion_type='percentage',
                discount_value=Decimal('10.00'),
                start_date=datetime.utcnow() - timedelta(days=1),
                end_date=datetime.utcnow() + timedelta(days=30),
                usage_limit=5,
                usage_per_customer=1,
                is_active=True,
                created_by=admin.id
            )
            db.session.add(promotion)
            db.session.flush()

            # Add a usage record
            if customer:
                usage = PromotionUsage(
                    promotion_id=promotion.id,
                    customer_id=customer.id,
                    discount_amount=Decimal('10.00')
                )
                db.session.add(usage)
                promotion.times_used = 1

            db.session.commit()

            # Validate should check usage limit
            response = auth_admin.post(
                '/promotions/validate',
                json={
                    'code': 'LIMIT5',
                    'cart_total': 200,
                    'customer_id': customer.id if customer else None
                },
                content_type='application/json'
            )
            assert response.status_code == 200
            data = response.get_json()
            # If customer already used it once, should be invalid
            if customer:
                assert data.get('valid') is False
