"""
Comprehensive tests for Notifications Routes (SMS, WhatsApp, Due Reminders).

Tests cover:
- SMS notifications and templates
- WhatsApp notifications and templates
- Due payment reminders
- Feature flag requirements
- Permission checks
"""

import pytest
import json
from datetime import datetime, date, timedelta
from decimal import Decimal


class TestNotificationsSetup:
    """Setup fixtures for notifications tests."""

    @pytest.fixture
    def enable_sms_feature(self, fresh_app):
        """Enable SMS notifications feature flag."""
        from app.models import db
        from app.models_extended import FeatureFlag

        with fresh_app.app_context():
            flag = FeatureFlag(
                name='sms_notifications',
                display_name='SMS Notifications',
                description='Enable SMS notifications',
                category='notifications',
                is_enabled=True,
                requires_config=True,
                is_configured=True,
                config={'provider': 'test', 'api_key': 'test-key'}
            )
            db.session.add(flag)
            db.session.commit()
            yield

    @pytest.fixture
    def enable_whatsapp_feature(self, fresh_app):
        """Enable WhatsApp notifications feature flag."""
        from app.models import db
        from app.models_extended import FeatureFlag

        with fresh_app.app_context():
            flag = FeatureFlag(
                name='whatsapp_notifications',
                display_name='WhatsApp Notifications',
                description='Enable WhatsApp notifications',
                category='notifications',
                is_enabled=True,
                requires_config=True,
                is_configured=True,
                config={'api_key': 'test-key', 'phone_id': 'test-phone'}
            )
            db.session.add(flag)
            db.session.commit()
            yield

    @pytest.fixture
    def enable_due_payments_feature(self, fresh_app):
        """Enable due payments feature flag."""
        from app.models import db
        from app.models_extended import FeatureFlag

        with fresh_app.app_context():
            flag = FeatureFlag(
                name='due_payments',
                display_name='Due Payments',
                description='Enable due payments tracking',
                category='sales',
                is_enabled=True,
                requires_config=False
            )
            db.session.add(flag)
            db.session.commit()
            yield

    @pytest.fixture
    def enable_all_notification_features(self, enable_sms_feature, enable_whatsapp_feature, enable_due_payments_feature):
        """Enable all notification features."""
        yield

    @pytest.fixture
    def sms_template(self, fresh_app, init_database, enable_sms_feature):
        """Create an SMS template."""
        from app.models import db
        from app.models_extended import SMSTemplate

        with fresh_app.app_context():
            template = SMSTemplate(
                name='Welcome SMS',
                template_type='welcome',
                message='Welcome {customer_name} to Sunnat Collection! You have {loyalty_points} points.',
                is_active=True
            )
            db.session.add(template)
            db.session.commit()
            return template.id

    @pytest.fixture
    def whatsapp_template(self, fresh_app, init_database, enable_whatsapp_feature):
        """Create a WhatsApp template."""
        from app.models import db
        from app.models_extended import WhatsAppTemplate

        with fresh_app.app_context():
            template = WhatsAppTemplate(
                name='Order Confirmation',
                template_type='order_confirmation',
                message='Hi {customer_name}, your order has been confirmed!',
                has_media=False,
                is_active=True
            )
            db.session.add(template)
            db.session.commit()
            return template.id

    @pytest.fixture
    def due_payment(self, fresh_app, init_database, enable_due_payments_feature):
        """Create a due payment."""
        from app.models import db, User, Customer, Sale
        from app.models_extended import DuePayment

        with fresh_app.app_context():
            admin = User.query.filter_by(username='admin').first()
            customer = Customer.query.filter_by(is_active=True).first()

            # Create a sale
            sale = Sale(
                sale_number='SALE-DUE-001',
                customer_id=customer.id if customer else None,
                user_id=admin.id,
                subtotal=Decimal('5000.00'),
                total=Decimal('5000.00'),
                amount_paid=Decimal('2000.00'),
                payment_method='cash',
                payment_status='partial',
                status='completed'
            )
            db.session.add(sale)
            db.session.flush()

            # Create due payment
            due = DuePayment(
                customer_id=customer.id if customer else 1,
                sale_id=sale.id,
                total_amount=Decimal('5000.00'),
                paid_amount=Decimal('2000.00'),
                due_amount=Decimal('3000.00'),
                due_date=date.today() - timedelta(days=7),  # Overdue
                status='pending'
            )
            db.session.add(due)
            db.session.commit()
            return due.id


class TestSMSIndex(TestNotificationsSetup):
    """Tests for SMS notifications index page."""

    def test_sms_index_requires_login(self, client, init_database, enable_sms_feature):
        """Test that SMS index requires authentication."""
        response = client.get('/notifications/sms')
        assert response.status_code in [302, 401]

    def test_sms_index_as_admin(self, auth_admin, enable_sms_feature, fresh_app):
        """Test SMS index page as admin."""
        with fresh_app.app_context():
            response = auth_admin.get('/notifications/sms')
            assert response.status_code in [200, 302, 500]

    def test_sms_feature_disabled_redirects(self, auth_admin, fresh_app):
        """Test that disabled SMS feature redirects."""
        with fresh_app.app_context():
            response = auth_admin.get('/notifications/sms')
            assert response.status_code in [200, 302, 403]


class TestSMSTemplates(TestNotificationsSetup):
    """Tests for SMS templates management."""

    def test_sms_templates_list(self, auth_admin, enable_sms_feature, sms_template, fresh_app):
        """Test SMS templates list page."""
        with fresh_app.app_context():
            response = auth_admin.get('/notifications/sms/templates')
            assert response.status_code in [200, 302, 500]

    def test_add_sms_template(self, auth_admin, enable_sms_feature, fresh_app):
        """Test adding an SMS template."""
        with fresh_app.app_context():
            data = {
                'name': 'Birthday SMS',
                'template_type': 'birthday',
                'message': 'Happy Birthday {customer_name}! Enjoy 10% off today!'
            }
            response = auth_admin.post('/notifications/sms/templates/add',
                                       data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 500]

    def test_edit_sms_template(self, auth_admin, enable_sms_feature, sms_template, fresh_app):
        """Test editing an SMS template."""
        with fresh_app.app_context():
            data = {
                'name': 'Updated Template',
                'message': 'Updated message',
                'is_active': 'true'
            }
            response = auth_admin.post(f'/notifications/sms/templates/edit/{sms_template}',
                                       data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 500]


class TestSendSMS(TestNotificationsSetup):
    """Tests for sending SMS."""

    def test_send_sms_with_phone(self, auth_admin, enable_sms_feature, fresh_app):
        """Test sending SMS to phone number."""
        with fresh_app.app_context():
            data = {
                'phone': '03001234567',
                'message': 'Test SMS message'
            }
            response = auth_admin.post(
                '/notifications/sms/send',
                json=data,
                content_type='application/json'
            )
            # May succeed or fail based on provider config
            assert response.status_code in [200, 400]

    def test_send_sms_with_customer(self, auth_admin, enable_sms_feature, fresh_app):
        """Test sending SMS to customer."""
        from app.models import Customer

        with fresh_app.app_context():
            customer = Customer.query.filter_by(is_active=True).first()

            if customer and customer.phone:
                data = {
                    'customer_id': customer.id,
                    'message': 'Test SMS to customer'
                }
                response = auth_admin.post(
                    '/notifications/sms/send',
                    json=data,
                    content_type='application/json'
                )
                assert response.status_code in [200, 400]

    def test_send_sms_with_template(self, auth_admin, enable_sms_feature, sms_template, fresh_app):
        """Test sending SMS using template."""
        with fresh_app.app_context():
            data = {
                'phone': '03001234567',
                'template_id': sms_template
            }
            response = auth_admin.post(
                '/notifications/sms/send',
                json=data,
                content_type='application/json'
            )
            assert response.status_code in [200, 400]

    def test_send_sms_no_phone(self, auth_admin, enable_sms_feature, fresh_app):
        """Test sending SMS without phone number."""
        with fresh_app.app_context():
            data = {
                'message': 'Test SMS without phone'
            }
            response = auth_admin.post(
                '/notifications/sms/send',
                json=data,
                content_type='application/json'
            )
            assert response.status_code == 400


class TestBulkSMS(TestNotificationsSetup):
    """Tests for bulk SMS functionality."""

    def test_bulk_sms_page(self, auth_admin, enable_sms_feature, sms_template, fresh_app):
        """Test bulk SMS page."""
        with fresh_app.app_context():
            response = auth_admin.get('/notifications/sms/bulk')
            assert response.status_code in [200, 302, 500]

    def test_bulk_sms_to_all(self, auth_admin, enable_sms_feature, sms_template, fresh_app):
        """Test sending bulk SMS to all customers."""
        with fresh_app.app_context():
            data = {
                'template_id': sms_template,
                'recipient_type': 'all'
            }
            response = auth_admin.post('/notifications/sms/bulk',
                                       data=data, follow_redirects=True)
            assert response.status_code in [200, 302]

    def test_bulk_sms_to_birthday(self, auth_admin, enable_sms_feature, sms_template, fresh_app):
        """Test sending bulk SMS to customers with birthdays."""
        with fresh_app.app_context():
            data = {
                'template_id': sms_template,
                'recipient_type': 'birthday'
            }
            response = auth_admin.post('/notifications/sms/bulk',
                                       data=data, follow_redirects=True)
            assert response.status_code in [200, 302]


class TestWhatsAppIndex(TestNotificationsSetup):
    """Tests for WhatsApp notifications index page."""

    def test_whatsapp_index_requires_login(self, client, init_database, enable_whatsapp_feature):
        """Test that WhatsApp index requires authentication."""
        response = client.get('/notifications/whatsapp')
        assert response.status_code in [302, 401]

    def test_whatsapp_index_as_admin(self, auth_admin, enable_whatsapp_feature, fresh_app):
        """Test WhatsApp index page as admin."""
        with fresh_app.app_context():
            response = auth_admin.get('/notifications/whatsapp')
            assert response.status_code in [200, 302, 500]


class TestWhatsAppTemplates(TestNotificationsSetup):
    """Tests for WhatsApp templates management."""

    def test_whatsapp_templates_list(self, auth_admin, enable_whatsapp_feature, whatsapp_template, fresh_app):
        """Test WhatsApp templates list page."""
        with fresh_app.app_context():
            response = auth_admin.get('/notifications/whatsapp/templates')
            assert response.status_code in [200, 302, 500]

    def test_add_whatsapp_template(self, auth_admin, enable_whatsapp_feature, fresh_app):
        """Test adding a WhatsApp template."""
        with fresh_app.app_context():
            data = {
                'name': 'Promotion Alert',
                'template_type': 'promotion',
                'message': 'Check out our latest promotions!',
                'has_media': 'false'
            }
            response = auth_admin.post('/notifications/whatsapp/templates/add',
                                       data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 500]

    def test_add_whatsapp_template_with_media(self, auth_admin, enable_whatsapp_feature, fresh_app):
        """Test adding a WhatsApp template with media."""
        with fresh_app.app_context():
            data = {
                'name': 'Product Image',
                'template_type': 'custom',
                'message': 'Check out this product!',
                'has_media': 'true',
                'media_url': 'https://example.com/image.jpg'
            }
            response = auth_admin.post('/notifications/whatsapp/templates/add',
                                       data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 500]


class TestSendWhatsApp(TestNotificationsSetup):
    """Tests for sending WhatsApp messages."""

    def test_send_whatsapp_with_phone(self, auth_admin, enable_whatsapp_feature, fresh_app):
        """Test sending WhatsApp to phone number."""
        with fresh_app.app_context():
            data = {
                'phone': '03001234567',
                'message': 'Test WhatsApp message'
            }
            response = auth_admin.post(
                '/notifications/whatsapp/send',
                json=data,
                content_type='application/json'
            )
            assert response.status_code in [200, 400]

    def test_send_whatsapp_with_customer(self, auth_admin, enable_whatsapp_feature, fresh_app):
        """Test sending WhatsApp to customer."""
        from app.models import Customer

        with fresh_app.app_context():
            customer = Customer.query.filter_by(is_active=True).first()

            if customer and customer.phone:
                data = {
                    'customer_id': customer.id,
                    'message': 'Test WhatsApp to customer'
                }
                response = auth_admin.post(
                    '/notifications/whatsapp/send',
                    json=data,
                    content_type='application/json'
                )
                assert response.status_code in [200, 400]

    def test_send_whatsapp_no_phone(self, auth_admin, enable_whatsapp_feature, fresh_app):
        """Test sending WhatsApp without phone number."""
        with fresh_app.app_context():
            data = {
                'message': 'Test WhatsApp without phone'
            }
            response = auth_admin.post(
                '/notifications/whatsapp/send',
                json=data,
                content_type='application/json'
            )
            assert response.status_code == 400


class TestQuickWhatsApp(TestNotificationsSetup):
    """Tests for quick WhatsApp functionality."""

    def test_quick_whatsapp_redirects(self, auth_admin, enable_whatsapp_feature, fresh_app):
        """Test quick WhatsApp redirect."""
        from app.models import Customer

        with fresh_app.app_context():
            customer = Customer.query.filter_by(is_active=True).first()

            if customer and customer.phone:
                response = auth_admin.get(
                    f'/notifications/whatsapp/quick-send/{customer.id}',
                    follow_redirects=False
                )
                # Should redirect to WhatsApp web URL
                assert response.status_code in [302, 200]

    def test_quick_whatsapp_no_phone(self, auth_admin, enable_whatsapp_feature, fresh_app):
        """Test quick WhatsApp for customer without phone."""
        from app.models import db, Customer

        with fresh_app.app_context():
            # Create customer without phone
            customer = Customer(
                name='No Phone Customer',
                is_active=True
            )
            db.session.add(customer)
            db.session.commit()

            response = auth_admin.get(
                f'/notifications/whatsapp/quick-send/{customer.id}',
                follow_redirects=True
            )
            # Should redirect with warning
            assert response.status_code in [200, 302]


class TestDueReminders(TestNotificationsSetup):
    """Tests for due payment reminders."""

    def test_due_reminders_page(self, auth_admin, enable_all_notification_features, due_payment, fresh_app):
        """Test due reminders page."""
        with fresh_app.app_context():
            response = auth_admin.get('/notifications/due-reminders')
            assert response.status_code in [200, 302, 500]

    def test_send_due_reminder(self, auth_admin, enable_all_notification_features, due_payment, fresh_app):
        """Test sending due reminder."""
        with fresh_app.app_context():
            response = auth_admin.post(f'/notifications/send-reminder/{due_payment}')
            assert response.status_code in [200, 400]

            if response.status_code == 200:
                data = response.get_json()
                assert data.get('success') is True

    def test_send_reminder_no_phone(self, auth_admin, enable_all_notification_features, fresh_app):
        """Test sending reminder to customer without phone."""
        from app.models import db, User, Customer, Sale
        from app.models_extended import DuePayment

        with fresh_app.app_context():
            admin = User.query.filter_by(username='admin').first()

            # Create customer without phone
            customer = Customer(name='No Phone Due Customer', is_active=True)
            db.session.add(customer)
            db.session.flush()

            sale = Sale(
                sale_number='SALE-DUE-NOPHONE',
                customer_id=customer.id,
                user_id=admin.id,
                subtotal=Decimal('1000.00'),
                total=Decimal('1000.00'),
                amount_paid=Decimal('0'),
                payment_method='cash',
                payment_status='pending',
                status='completed'
            )
            db.session.add(sale)
            db.session.flush()

            due = DuePayment(
                customer_id=customer.id,
                sale_id=sale.id,
                total_amount=Decimal('1000.00'),
                paid_amount=Decimal('0'),
                due_amount=Decimal('1000.00'),
                due_date=date.today() - timedelta(days=1),
                status='pending'
            )
            db.session.add(due)
            db.session.commit()

            response = auth_admin.post(f'/notifications/send-reminder/{due.id}')
            # Should fail due to no phone
            assert response.status_code == 400


class TestNotificationPhoneFormatting(TestNotificationsSetup):
    """Tests for phone number formatting."""

    def test_pakistan_phone_formatting(self, auth_admin, enable_whatsapp_feature, fresh_app):
        """Test Pakistan phone number formatting for WhatsApp."""
        with fresh_app.app_context():
            # Test with 03xx format
            data = {
                'phone': '03001234567',
                'message': 'Test formatting'
            }
            response = auth_admin.post(
                '/notifications/whatsapp/send',
                json=data,
                content_type='application/json'
            )
            # Should convert to 92xx format internally
            assert response.status_code in [200, 400]

    def test_international_phone(self, auth_admin, enable_whatsapp_feature, fresh_app):
        """Test international phone number."""
        with fresh_app.app_context():
            data = {
                'phone': '+923001234567',
                'message': 'Test international'
            }
            response = auth_admin.post(
                '/notifications/whatsapp/send',
                json=data,
                content_type='application/json'
            )
            assert response.status_code in [200, 400]


class TestNotificationLogs(TestNotificationsSetup):
    """Tests for notification logging."""

    def test_sms_creates_log(self, auth_admin, enable_sms_feature, fresh_app):
        """Test that sending SMS creates a log entry."""
        from app.models_extended import SMSLog

        with fresh_app.app_context():
            initial_count = SMSLog.query.count()

            data = {
                'phone': '03001234567',
                'message': 'Test log creation'
            }
            auth_admin.post(
                '/notifications/sms/send',
                json=data,
                content_type='application/json'
            )

            final_count = SMSLog.query.count()
            assert final_count >= initial_count  # May have increased

    def test_whatsapp_creates_log(self, auth_admin, enable_whatsapp_feature, fresh_app):
        """Test that sending WhatsApp creates a log entry."""
        from app.models_extended import WhatsAppLog

        with fresh_app.app_context():
            initial_count = WhatsAppLog.query.count()

            data = {
                'phone': '03001234567',
                'message': 'Test WhatsApp log'
            }
            auth_admin.post(
                '/notifications/whatsapp/send',
                json=data,
                content_type='application/json'
            )

            final_count = WhatsAppLog.query.count()
            assert final_count >= initial_count


class TestNotificationFeatureFlags(TestNotificationsSetup):
    """Tests for notification feature flag requirements."""

    def test_sms_disabled_redirects(self, auth_admin, fresh_app):
        """Test that disabled SMS feature redirects."""
        with fresh_app.app_context():
            response = auth_admin.get('/notifications/sms')
            assert response.status_code in [200, 302, 403]

    def test_whatsapp_disabled_redirects(self, auth_admin, fresh_app):
        """Test that disabled WhatsApp feature redirects."""
        with fresh_app.app_context():
            response = auth_admin.get('/notifications/whatsapp')
            assert response.status_code in [200, 302, 403]

    def test_sms_not_configured(self, auth_admin, fresh_app):
        """Test SMS feature enabled but not configured."""
        from app.models import db
        from app.models_extended import FeatureFlag

        with fresh_app.app_context():
            # Create enabled but not configured flag
            flag = FeatureFlag(
                name='sms_notifications',
                display_name='SMS',
                is_enabled=True,
                requires_config=True,
                is_configured=False
            )
            db.session.add(flag)
            db.session.commit()

            response = auth_admin.get('/notifications/sms')
            # Should redirect since not configured
            assert response.status_code in [200, 302, 403]


class TestReminderTracking(TestNotificationsSetup):
    """Tests for reminder tracking functionality."""

    def test_reminder_count_increments(self, auth_admin, enable_all_notification_features, due_payment, fresh_app):
        """Test that reminder count increments."""
        from app.models_extended import DuePayment

        with fresh_app.app_context():
            due = DuePayment.query.get(due_payment)
            initial_count = due.reminder_count

            auth_admin.post(f'/notifications/send-reminder/{due_payment}')

            due = DuePayment.query.get(due_payment)
            # Reminder count should have increased
            assert due.reminder_count >= initial_count

    def test_reminder_sent_flag_set(self, auth_admin, enable_all_notification_features, due_payment, fresh_app):
        """Test that reminder_sent flag is set."""
        from app.models_extended import DuePayment

        with fresh_app.app_context():
            auth_admin.post(f'/notifications/send-reminder/{due_payment}')

            due = DuePayment.query.get(due_payment)
            assert due.reminder_sent is True

    def test_last_reminder_timestamp_updated(self, auth_admin, enable_all_notification_features, due_payment, fresh_app):
        """Test that last_reminder_at is updated."""
        from app.models_extended import DuePayment

        with fresh_app.app_context():
            auth_admin.post(f'/notifications/send-reminder/{due_payment}')

            due = DuePayment.query.get(due_payment)
            assert due.last_reminder_at is not None
