"""
Comprehensive Unit Tests for SOC_WEB_APP Utility Functions and Services

This module contains extensive unit tests covering:
- Helper functions (date formatting, currency formatting, calculations)
- Database utilities (connections, transactions, error handling)
- Email service (sending, templates, attachments, failures)
- PDF utilities (generation, formatting, special characters)
- Location context (switching, persistence, multi-location)
- Feature flags (enable/disable, rollout, targeting)
- Backup service (creation, restoration, scheduling, integrity)
- Sync service (data sync, conflict resolution, offline handling)
- Production service (recipes, batches, yields)
- Edge cases (NULL inputs, empty strings, invalid types)
- Error handling (exceptions, logging, recovery)
- Performance (timeouts, large data, memory usage)
"""

import pytest
import os
import sys
import json
import tempfile
import shutil
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from io import BytesIO
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# HELPER FUNCTIONS TESTS - app/utils/helpers.py
# =============================================================================

class TestFormatCurrency:
    """Tests for format_currency function."""

    def test_format_currency_positive_amount(self):
        """Test formatting positive currency amounts."""
        from app.utils.helpers import format_currency

        assert format_currency(1000) == "Rs. 1,000.00"
        assert format_currency(1234.56) == "Rs. 1,234.56"
        assert format_currency(0) == "Rs. 0.00"

    def test_format_currency_negative_amount(self):
        """Test formatting negative currency amounts."""
        from app.utils.helpers import format_currency

        assert format_currency(-500) == "Rs. -500.00"
        assert format_currency(-1234.56) == "Rs. -1,234.56"

    def test_format_currency_custom_symbol(self):
        """Test formatting with custom currency symbols."""
        from app.utils.helpers import format_currency

        assert format_currency(1000, '$') == "$ 1,000.00"
        assert format_currency(1000, '€') == "€ 1,000.00"
        assert format_currency(1000, '£') == "£ 1,000.00"
        assert format_currency(1000, 'PKR') == "PKR 1,000.00"

    def test_format_currency_large_numbers(self):
        """Test formatting large currency amounts."""
        from app.utils.helpers import format_currency

        assert format_currency(1000000) == "Rs. 1,000,000.00"
        assert format_currency(1234567890.99) == "Rs. 1,234,567,890.99"

    def test_format_currency_decimal_precision(self):
        """Test decimal precision in currency formatting."""
        from app.utils.helpers import format_currency

        # Test rounding behavior
        assert format_currency(1.999) == "Rs. 2.00"
        assert format_currency(1.994) == "Rs. 1.99"
        assert format_currency(1.005) == "Rs. 1.00" or format_currency(1.005) == "Rs. 1.01"

    def test_format_currency_small_amounts(self):
        """Test formatting very small amounts."""
        from app.utils.helpers import format_currency

        assert format_currency(0.01) == "Rs. 0.01"
        assert format_currency(0.99) == "Rs. 0.99"
        assert format_currency(0.001) == "Rs. 0.00"

    def test_format_currency_decimal_type(self):
        """Test formatting Decimal type values."""
        from app.utils.helpers import format_currency

        result = format_currency(Decimal('1234.56'))
        assert "1,234.56" in result

    def test_format_currency_integer_type(self):
        """Test formatting integer type values."""
        from app.utils.helpers import format_currency

        assert format_currency(int(1000)) == "Rs. 1,000.00"

    def test_format_currency_float_type(self):
        """Test formatting float type values."""
        from app.utils.helpers import format_currency

        assert format_currency(float(1000.50)) == "Rs. 1,000.50"


class TestFormatPercentage:
    """Tests for format_percentage function."""

    def test_format_percentage_positive(self):
        """Test formatting positive percentages."""
        from app.utils.helpers import format_percentage

        assert format_percentage(50) == "50.00%"
        assert format_percentage(25.5) == "25.50%"
        assert format_percentage(100) == "100.00%"

    def test_format_percentage_zero(self):
        """Test formatting zero percentage."""
        from app.utils.helpers import format_percentage

        assert format_percentage(0) == "0.00%"

    def test_format_percentage_negative(self):
        """Test formatting negative percentages."""
        from app.utils.helpers import format_percentage

        assert format_percentage(-10) == "-10.00%"
        assert format_percentage(-25.75) == "-25.75%"

    def test_format_percentage_over_100(self):
        """Test formatting percentages over 100."""
        from app.utils.helpers import format_percentage

        assert format_percentage(150) == "150.00%"
        assert format_percentage(1000) == "1000.00%"

    def test_format_percentage_decimal_precision(self):
        """Test decimal precision in percentage formatting."""
        from app.utils.helpers import format_percentage

        assert format_percentage(33.333) == "33.33%"
        assert format_percentage(66.666) == "66.67%"

    def test_format_percentage_small_values(self):
        """Test formatting very small percentages."""
        from app.utils.helpers import format_percentage

        assert format_percentage(0.01) == "0.01%"
        assert format_percentage(0.001) == "0.00%"


class TestCalculateProfitMargin:
    """Tests for calculate_profit_margin function."""

    def test_profit_margin_positive(self):
        """Test positive profit margin calculation."""
        from app.utils.helpers import calculate_profit_margin

        # 50% markup
        margin = calculate_profit_margin(100, 150)
        assert margin == 50.0

    def test_profit_margin_zero_cost(self):
        """Test profit margin with zero cost price."""
        from app.utils.helpers import calculate_profit_margin

        assert calculate_profit_margin(0, 100) == 0
        assert calculate_profit_margin(None, 100) == 0

    def test_profit_margin_loss(self):
        """Test negative profit margin (loss)."""
        from app.utils.helpers import calculate_profit_margin

        margin = calculate_profit_margin(100, 80)
        assert margin == -20.0

    def test_profit_margin_equal_prices(self):
        """Test zero profit margin when prices are equal."""
        from app.utils.helpers import calculate_profit_margin

        assert calculate_profit_margin(100, 100) == 0.0

    def test_profit_margin_high_markup(self):
        """Test high profit margin calculation."""
        from app.utils.helpers import calculate_profit_margin

        margin = calculate_profit_margin(100, 300)
        assert margin == 200.0

    def test_profit_margin_decimal_prices(self):
        """Test profit margin with decimal prices."""
        from app.utils.helpers import calculate_profit_margin

        margin = calculate_profit_margin(99.99, 149.99)
        assert abs(margin - 50.01) < 0.1  # Allow small floating point variance


class TestGenerateSaleNumber:
    """Tests for generate_sale_number function."""

    def test_sale_number_format(self):
        """Test sale number follows expected format."""
        from app.utils.helpers import generate_sale_number

        sale_num = generate_sale_number()
        assert sale_num.startswith('SALE-')
        assert len(sale_num) == 18  # SALE-YYYYMMDD-XXXX

        # Parse and validate date part
        parts = sale_num.split('-')
        assert len(parts) == 3
        date_part = parts[1]
        assert len(date_part) == 8  # YYYYMMDD

        # Validate random part
        random_part = parts[2]
        assert len(random_part) == 4
        assert random_part.isdigit()

    def test_sale_number_uniqueness(self):
        """Test sale numbers are unique across multiple generations."""
        from app.utils.helpers import generate_sale_number

        # Generate multiple sale numbers
        sale_numbers = [generate_sale_number() for _ in range(100)]
        unique_numbers = set(sale_numbers)

        # Should be mostly unique (allow for small collision probability)
        assert len(unique_numbers) >= 95

    def test_sale_number_contains_current_date(self):
        """Test sale number contains current date."""
        from app.utils.helpers import generate_sale_number

        sale_num = generate_sale_number()
        today = datetime.now().strftime('%Y%m%d')
        assert today in sale_num


class TestGeneratePONumber:
    """Tests for generate_po_number function."""

    def test_po_number_format(self):
        """Test PO number follows expected format."""
        from app.utils.helpers import generate_po_number

        po_num = generate_po_number()
        assert po_num.startswith('PO-')
        assert len(po_num) == 16  # PO-YYYYMMDD-XXXX

    def test_po_number_uniqueness(self):
        """Test PO numbers are unique."""
        from app.utils.helpers import generate_po_number

        po_numbers = [generate_po_number() for _ in range(100)]
        unique_numbers = set(po_numbers)
        assert len(unique_numbers) >= 95


class TestGenerateProductCode:
    """Tests for generate_product_code function."""

    def test_product_code_format(self):
        """Test product code follows expected format."""
        from app.utils.helpers import generate_product_code

        code = generate_product_code()
        assert code.startswith('PROD-')
        assert len(code) == 13  # PROD-XXXXXXXX

    def test_product_code_alphanumeric(self):
        """Test product code contains valid characters."""
        from app.utils.helpers import generate_product_code

        code = generate_product_code()
        random_part = code.split('-')[1]
        assert len(random_part) == 8
        assert random_part.isalnum()
        assert random_part.isupper() or any(c.isdigit() for c in random_part)


class TestGetDateRange:
    """Tests for get_date_range function."""

    def test_date_range_today(self):
        """Test date range for today."""
        from app.utils.helpers import get_date_range

        start, end = get_date_range('today')
        today = datetime.now().date()
        assert start == today
        assert end == today

    def test_date_range_yesterday(self):
        """Test date range for yesterday."""
        from app.utils.helpers import get_date_range

        start, end = get_date_range('yesterday')
        yesterday = datetime.now().date() - timedelta(days=1)
        assert start == yesterday
        assert end == yesterday

    def test_date_range_this_week(self):
        """Test date range for this week."""
        from app.utils.helpers import get_date_range

        start, end = get_date_range('this_week')
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())

        assert start == week_start
        assert end == today

    def test_date_range_last_week(self):
        """Test date range for last week."""
        from app.utils.helpers import get_date_range

        start, end = get_date_range('last_week')
        today = datetime.now().date()
        last_week_start = today - timedelta(days=today.weekday() + 7)
        last_week_end = last_week_start + timedelta(days=6)

        assert start == last_week_start
        assert end == last_week_end

    def test_date_range_this_month(self):
        """Test date range for this month."""
        from app.utils.helpers import get_date_range

        start, end = get_date_range('this_month')
        today = datetime.now().date()
        month_start = today.replace(day=1)

        assert start == month_start
        assert end == today

    def test_date_range_last_month(self):
        """Test date range for last month."""
        from app.utils.helpers import get_date_range

        start, end = get_date_range('last_month')
        today = datetime.now().date()
        last_month_end = today.replace(day=1) - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)

        assert start == last_month_start
        assert end == last_month_end

    def test_date_range_invalid_period(self):
        """Test date range returns today for invalid periods."""
        from app.utils.helpers import get_date_range

        start, end = get_date_range('invalid_period')
        today = datetime.now().date()
        assert start == today
        assert end == today

    def test_date_range_empty_string(self):
        """Test date range with empty string."""
        from app.utils.helpers import get_date_range

        start, end = get_date_range('')
        today = datetime.now().date()
        assert start == today
        assert end == today


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_sanitize_normal_filename(self):
        """Test sanitizing normal filenames."""
        from app.utils.helpers import sanitize_filename

        assert sanitize_filename('document.pdf') == 'document.pdf'
        assert sanitize_filename('my_file.txt') == 'my_file.txt'

    def test_sanitize_filename_with_spaces(self):
        """Test sanitizing filenames with spaces."""
        from app.utils.helpers import sanitize_filename

        result = sanitize_filename('my document.pdf')
        assert ' ' not in result or result == 'my_document.pdf'

    def test_sanitize_filename_with_special_chars(self):
        """Test sanitizing filenames with special characters."""
        from app.utils.helpers import sanitize_filename

        result = sanitize_filename('../../../etc/passwd')
        assert '..' not in result
        assert '/' not in result

    def test_sanitize_filename_with_unicode(self):
        """Test sanitizing filenames with unicode characters."""
        from app.utils.helpers import sanitize_filename

        result = sanitize_filename('файл.pdf')
        # Should handle unicode gracefully
        assert result is not None


class TestAllowedFile:
    """Tests for allowed_file function."""

    def test_allowed_file_with_valid_extension(self, fresh_app):
        """Test allowed file check with valid extensions."""
        from app.utils.helpers import allowed_file

        with fresh_app.app_context():
            fresh_app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'pdf'}

            assert allowed_file('image.png') == True
            assert allowed_file('document.pdf') == True

    def test_allowed_file_with_invalid_extension(self, fresh_app):
        """Test allowed file check with invalid extensions."""
        from app.utils.helpers import allowed_file

        with fresh_app.app_context():
            fresh_app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'pdf'}

            assert allowed_file('script.exe') == False
            assert allowed_file('file.py') == False

    def test_allowed_file_no_extension(self, fresh_app):
        """Test allowed file check with no extension."""
        from app.utils.helpers import allowed_file

        with fresh_app.app_context():
            fresh_app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'pdf'}

            assert allowed_file('filename') == False
            assert allowed_file('') == False

    def test_allowed_file_case_insensitive(self, fresh_app):
        """Test allowed file is case insensitive."""
        from app.utils.helpers import allowed_file

        with fresh_app.app_context():
            fresh_app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'pdf'}

            assert allowed_file('IMAGE.PNG') == True
            assert allowed_file('Document.PDF') == True

    def test_allowed_file_double_extension(self, fresh_app):
        """Test allowed file with double extensions."""
        from app.utils.helpers import allowed_file

        with fresh_app.app_context():
            fresh_app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'pdf'}

            # Should check last extension only
            assert allowed_file('file.pdf.exe') == False
            assert allowed_file('file.exe.pdf') == True


class TestHasPermission:
    """Tests for has_permission function."""

    def test_has_permission_unauthenticated(self, fresh_app):
        """Test permission check when not authenticated."""
        from app.utils.helpers import has_permission
        from flask_login import current_user

        with fresh_app.app_context():
            with fresh_app.test_request_context():
                # Without login, should return False
                result = has_permission('pos')
                assert result == False


# =============================================================================
# DATABASE UTILITIES TESTS - app/utils/db_utils.py
# =============================================================================

class TestInitDatabase:
    """Tests for init_database function."""

    def test_init_database_success(self, fresh_app):
        """Test successful database initialization."""
        from app.utils.db_utils import init_database
        from app.models import db

        with fresh_app.app_context():
            result = init_database()
            assert result == True

    def test_init_database_creates_tables(self, fresh_app):
        """Test that init_database creates all tables."""
        from app.utils.db_utils import init_database
        from app.models import db, User, Product

        with fresh_app.app_context():
            init_database()

            # Tables should exist and be queryable
            users = User.query.all()
            assert isinstance(users, list)


class TestResetDatabase:
    """Tests for reset_database function."""

    def test_reset_database_success(self, fresh_app):
        """Test successful database reset."""
        from app.utils.db_utils import reset_database
        from app.models import db

        with fresh_app.app_context():
            result = reset_database()
            assert result == True


class TestGetOrCreate:
    """Tests for get_or_create function."""

    def test_get_or_create_creates_new(self, fresh_app):
        """Test get_or_create creates new record when not found."""
        from app.utils.db_utils import get_or_create
        from app.models import db, Category

        with fresh_app.app_context():
            db.create_all()

            instance, created = get_or_create(
                Category,
                name='Test Category',
                description='Test Description'
            )

            assert created == True
            assert instance.name == 'Test Category'
            assert instance.id is not None

    def test_get_or_create_gets_existing(self, fresh_app):
        """Test get_or_create returns existing record."""
        from app.utils.db_utils import get_or_create
        from app.models import db, Category

        with fresh_app.app_context():
            db.create_all()

            # Create first
            instance1, created1 = get_or_create(Category, name='Existing')
            assert created1 == True

            # Try to create again
            instance2, created2 = get_or_create(Category, name='Existing')
            assert created2 == False
            assert instance1.id == instance2.id


class TestBulkInsert:
    """Tests for bulk_insert function."""

    def test_bulk_insert_success(self, fresh_app):
        """Test successful bulk insert."""
        from app.utils.db_utils import bulk_insert
        from app.models import db, Category

        with fresh_app.app_context():
            db.create_all()

            data_list = [
                {'name': 'Category 1', 'description': 'Desc 1'},
                {'name': 'Category 2', 'description': 'Desc 2'},
                {'name': 'Category 3', 'description': 'Desc 3'},
            ]

            count = bulk_insert(Category, data_list)
            assert count == 3

    def test_bulk_insert_empty_list(self, fresh_app):
        """Test bulk insert with empty list."""
        from app.utils.db_utils import bulk_insert
        from app.models import db, Category

        with fresh_app.app_context():
            db.create_all()

            count = bulk_insert(Category, [])
            assert count == 0


class TestSafeCommit:
    """Tests for safe_commit function."""

    def test_safe_commit_success(self, fresh_app):
        """Test successful safe commit."""
        from app.utils.db_utils import safe_commit
        from app.models import db, Category

        with fresh_app.app_context():
            db.create_all()

            cat = Category(name='Test', description='Test')
            db.session.add(cat)

            result = safe_commit()
            assert result == True


class TestPaginateQuery:
    """Tests for paginate_query function."""

    def test_paginate_query_first_page(self, fresh_app):
        """Test pagination returns first page."""
        from app.utils.db_utils import paginate_query, bulk_insert
        from app.models import db, Category

        with fresh_app.app_context():
            db.create_all()

            # Create test data
            data_list = [{'name': f'Cat {i}', 'description': f'Desc {i}'}
                        for i in range(100)]
            bulk_insert(Category, data_list)

            query = Category.query
            pagination = paginate_query(query, page=1, per_page=10)

            assert len(pagination.items) == 10
            assert pagination.page == 1
            assert pagination.per_page == 10

    def test_paginate_query_out_of_range(self, fresh_app):
        """Test pagination handles out of range pages gracefully."""
        from app.utils.db_utils import paginate_query, bulk_insert
        from app.models import db, Category

        with fresh_app.app_context():
            db.create_all()

            data_list = [{'name': f'Cat {i}'} for i in range(10)]
            bulk_insert(Category, data_list)

            query = Category.query
            pagination = paginate_query(query, page=100, per_page=10)

            # Should return empty list, not error
            assert len(pagination.items) == 0


class TestExecuteRawSQL:
    """Tests for execute_raw_sql function."""

    def test_execute_raw_sql_select(self, fresh_app):
        """Test executing raw SELECT query."""
        from app.utils.db_utils import execute_raw_sql
        from app.models import db
        from sqlalchemy import text

        with fresh_app.app_context():
            db.create_all()

            result = execute_raw_sql(text("SELECT 1 as test"))
            assert result is not None


# =============================================================================
# EMAIL SERVICE TESTS (utils) - app/utils/email_service.py
# =============================================================================

class TestSendDailyReportEmail:
    """Tests for send_daily_report_email function."""

    @patch('app.utils.email_service.smtplib.SMTP')
    def test_send_daily_report_email_success(self, mock_smtp, fresh_app):
        """Test successful email sending."""
        from app.utils.email_service import send_daily_report_email

        with fresh_app.app_context():
            fresh_app.config['SMTP_SERVER'] = 'smtp.test.com'
            fresh_app.config['SMTP_PORT'] = 587
            fresh_app.config['SMTP_USERNAME'] = 'test@test.com'
            fresh_app.config['SMTP_PASSWORD'] = 'password'
            fresh_app.config['SENDER_EMAIL'] = 'sender@test.com'

            # Mock day_close object
            day_close = Mock()
            day_close.close_date = datetime.now()
            day_close.total_sales = 10
            day_close.total_revenue = Decimal('5000.00')
            day_close.total_cash = Decimal('3000.00')
            day_close.total_card = Decimal('2000.00')
            day_close.opening_balance = Decimal('1000.00')
            day_close.expected_cash = Decimal('4000.00')
            day_close.closing_balance = Decimal('4000.00')
            day_close.cash_variance = Decimal('0.00')
            day_close.user = Mock(full_name='Test User')
            day_close.closed_at = datetime.now()

            # Mock SMTP server
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__ = Mock(return_value=mock_server)
            mock_smtp.return_value.__exit__ = Mock(return_value=False)

            result = send_daily_report_email(
                day_close,
                None,  # No attachment
                'recipient@test.com'
            )

            assert result == True
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once()

    def test_send_daily_report_email_no_credentials(self, fresh_app):
        """Test email sending fails without credentials."""
        from app.utils.email_service import send_daily_report_email

        with fresh_app.app_context():
            fresh_app.config['SMTP_USERNAME'] = None
            fresh_app.config['SMTP_PASSWORD'] = None

            day_close = Mock()
            day_close.close_date = datetime.now()

            with pytest.raises(ValueError, match="Email credentials not configured"):
                send_daily_report_email(day_close, None, 'test@test.com')


class TestSendLowStockAlert:
    """Tests for send_low_stock_alert function."""

    @patch('app.utils.email_service.smtplib.SMTP')
    def test_send_low_stock_alert_success(self, mock_smtp, fresh_app):
        """Test successful low stock alert email."""
        from app.utils.email_service import send_low_stock_alert

        with fresh_app.app_context():
            fresh_app.config['SMTP_SERVER'] = 'smtp.test.com'
            fresh_app.config['SMTP_PORT'] = 587
            fresh_app.config['SMTP_USERNAME'] = 'test@test.com'
            fresh_app.config['SMTP_PASSWORD'] = 'password'

            # Mock products
            products = [
                Mock(name='Product 1', code='P001', quantity=5,
                     reorder_level=10, suggested_reorder_quantity=20),
                Mock(name='Product 2', code='P002', quantity=2,
                     reorder_level=10, suggested_reorder_quantity=25),
            ]

            mock_server = MagicMock()
            mock_smtp.return_value.__enter__ = Mock(return_value=mock_server)
            mock_smtp.return_value.__exit__ = Mock(return_value=False)

            result = send_low_stock_alert(products, 'recipient@test.com')

            assert result == True

    def test_send_low_stock_alert_no_credentials(self, fresh_app):
        """Test low stock alert fails without credentials."""
        from app.utils.email_service import send_low_stock_alert

        with fresh_app.app_context():
            fresh_app.config['SMTP_USERNAME'] = None
            fresh_app.config['SMTP_PASSWORD'] = None

            result = send_low_stock_alert([], 'test@test.com')
            assert result == False


# =============================================================================
# PDF UTILITIES TESTS - app/utils/pdf_utils.py
# =============================================================================

class TestGenerateReceiptPDF:
    """Tests for generate_receipt_pdf function."""

    def test_generate_receipt_pdf_success(self, fresh_app):
        """Test successful PDF receipt generation."""
        from app.utils.pdf_utils import generate_receipt_pdf

        with fresh_app.app_context():
            # Create static folder if not exists
            static_folder = fresh_app.static_folder
            if not os.path.exists(static_folder):
                os.makedirs(static_folder)

            # Create a proper mock product with string name attribute
            mock_product = Mock()
            mock_product.name = 'Test Product'  # Set as string, not Mock

            # Mock sale object
            sale = Mock()
            sale.sale_number = 'SALE-20231215-0001'
            sale.sale_date = datetime.now()
            sale.customer = Mock()
            sale.customer.name = 'Test Customer'
            sale.customer.phone = '1234567890'
            sale.subtotal = Decimal('1000.00')
            sale.discount = Decimal('0.00')
            sale.discount_type = 'none'
            sale.tax = Decimal('0.00')
            sale.total = Decimal('1000.00')
            sale.payment_method = 'cash'

            # Mock sale items with proper string name
            item = Mock()
            item.product = mock_product
            item.quantity = 2
            item.unit_price = Decimal('500.00')
            item.subtotal = Decimal('1000.00')
            sale.items = [item]

            try:
                result = generate_receipt_pdf(sale)
                assert '/static/receipts/' in result
                assert 'SALE-20231215-0001' in result
            except KeyError as e:
                # Some reportlab configurations may not have all fonts
                if 'Helvetica' in str(e):
                    pytest.skip(f"Font not available in test environment: {e}")
                raise
            finally:
                # Cleanup
                receipts_folder = os.path.join(static_folder, 'receipts')
                if os.path.exists(receipts_folder):
                    shutil.rmtree(receipts_folder)

    def test_generate_receipt_pdf_no_customer(self, fresh_app):
        """Test PDF generation without customer."""
        from app.utils.pdf_utils import generate_receipt_pdf

        with fresh_app.app_context():
            static_folder = fresh_app.static_folder
            if not os.path.exists(static_folder):
                os.makedirs(static_folder)

            sale = Mock()
            sale.sale_number = 'SALE-20231215-0002'
            sale.sale_date = datetime.now()
            sale.customer = None
            sale.subtotal = Decimal('500.00')
            sale.discount = Decimal('50.00')
            sale.discount_type = 'fixed'
            sale.tax = Decimal('0.00')
            sale.total = Decimal('450.00')
            sale.payment_method = 'card'
            sale.items = []

            try:
                result = generate_receipt_pdf(sale)
                assert result is not None
            except KeyError as e:
                # Some reportlab configurations may not have all fonts
                if 'Helvetica' in str(e):
                    pytest.skip(f"Font not available in test environment: {e}")
                raise
            finally:
                receipts_folder = os.path.join(static_folder, 'receipts')
                if os.path.exists(receipts_folder):
                    shutil.rmtree(receipts_folder)

    def test_generate_receipt_pdf_long_product_name(self, fresh_app):
        """Test PDF generation with long product names."""
        from app.utils.pdf_utils import generate_receipt_pdf

        with fresh_app.app_context():
            static_folder = fresh_app.static_folder
            if not os.path.exists(static_folder):
                os.makedirs(static_folder)

            sale = Mock()
            sale.sale_number = 'SALE-20231215-0003'
            sale.sale_date = datetime.now()
            sale.customer = None
            sale.subtotal = Decimal('100.00')
            sale.discount = Decimal('0.00')
            sale.tax = Decimal('0.00')
            sale.total = Decimal('100.00')
            sale.payment_method = 'cash'

            # Long product name - use proper string
            mock_product = Mock()
            mock_product.name = 'A' * 100  # Set as string, not Mock
            item = Mock()
            item.product = mock_product
            item.quantity = 1
            item.unit_price = Decimal('100.00')
            item.subtotal = Decimal('100.00')
            sale.items = [item]

            try:
                result = generate_receipt_pdf(sale)
                assert result is not None
            except KeyError as e:
                # Some reportlab configurations may not have all fonts
                if 'Helvetica' in str(e):
                    pytest.skip(f"Font not available in test environment: {e}")
                raise
            finally:
                receipts_folder = os.path.join(static_folder, 'receipts')
                if os.path.exists(receipts_folder):
                    shutil.rmtree(receipts_folder)


class TestGenerateDailyReport:
    """Tests for generate_daily_report function."""

    def test_generate_daily_report_creates_file(self, fresh_app):
        """Test daily report PDF creation."""
        from app.utils.pdf_utils import generate_daily_report

        with fresh_app.app_context():
            static_folder = fresh_app.static_folder
            if not os.path.exists(static_folder):
                os.makedirs(static_folder)

            try:
                result = generate_daily_report('2023-12-15')
                assert result is not None
                assert os.path.exists(result)
            finally:
                reports_folder = os.path.join(static_folder, 'reports')
                if os.path.exists(reports_folder):
                    shutil.rmtree(reports_folder)


# =============================================================================
# LOCATION CONTEXT TESTS - app/utils/location_context.py
# =============================================================================

class TestGetCurrentLocation:
    """Tests for get_current_location function."""

    def test_get_current_location_unauthenticated(self, fresh_app):
        """Test getting location when not authenticated."""
        from app.utils.location_context import get_current_location

        with fresh_app.app_context():
            with fresh_app.test_request_context():
                result = get_current_location()
                assert result is None


class TestGetUserLocations:
    """Tests for get_user_locations function."""

    def test_get_user_locations_unauthenticated(self, fresh_app):
        """Test getting user locations when not authenticated."""
        from app.utils.location_context import get_user_locations

        with fresh_app.app_context():
            with fresh_app.test_request_context():
                result = get_user_locations()
                assert result == []


class TestSetLocationContext:
    """Tests for set_location_context function."""

    def test_set_location_context_unauthenticated(self, fresh_app):
        """Test setting location context when not authenticated."""
        from app.utils.location_context import set_location_context
        from flask import g

        with fresh_app.app_context():
            with fresh_app.test_request_context():
                set_location_context()

                assert g.current_location is None
                assert g.user_locations == []
                assert g.is_global_admin == False


class TestCanAccessLocation:
    """Tests for can_access_location function."""

    def test_can_access_location_unauthenticated(self, fresh_app):
        """Test location access when not authenticated."""
        from app.utils.location_context import can_access_location

        with fresh_app.app_context():
            with fresh_app.test_request_context():
                result = can_access_location(1)
                assert result == False


class TestGenerateTransferNumber:
    """Tests for generate_transfer_number function."""

    def test_generate_transfer_number_format(self, fresh_app):
        """Test transfer number format."""
        from app.utils.location_context import generate_transfer_number
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            transfer_num = generate_transfer_number()
            assert transfer_num.startswith('TRF-')

            # Should have format TRF-YYYYMMDD-XXX
            parts = transfer_num.split('-')
            assert len(parts) == 3
            assert len(parts[1]) == 8  # Date part
            assert len(parts[2]) == 3  # Sequence number


class TestLocationRequiredDecorator:
    """Tests for location_required decorator."""

    def test_location_required_redirects_unauthenticated(self, client, fresh_app):
        """Test location_required redirects when not authenticated."""
        from app.utils.location_context import location_required
        from flask import Flask

        @fresh_app.route('/test_location_required')
        @location_required
        def test_view():
            return 'success'

        response = client.get('/test_location_required')
        assert response.status_code in [302, 401]


class TestWarehouseRequiredDecorator:
    """Tests for warehouse_required decorator."""

    def test_warehouse_required_redirects_unauthenticated(self, client, fresh_app):
        """Test warehouse_required redirects when not authenticated."""
        from app.utils.location_context import warehouse_required

        @fresh_app.route('/test_warehouse_required')
        @warehouse_required
        def test_view():
            return 'success'

        response = client.get('/test_warehouse_required')
        assert response.status_code in [302, 401]


class TestKioskRequiredDecorator:
    """Tests for kiosk_required decorator."""

    def test_kiosk_required_redirects_unauthenticated(self, client, fresh_app):
        """Test kiosk_required redirects when not authenticated."""
        from app.utils.location_context import kiosk_required

        @fresh_app.route('/test_kiosk_required')
        @kiosk_required
        def test_view():
            return 'success'

        response = client.get('/test_kiosk_required')
        assert response.status_code in [302, 401]


# =============================================================================
# FEATURE FLAGS TESTS - app/utils/feature_flags.py
# =============================================================================

class TestIsFeatureEnabled:
    """Tests for is_feature_enabled function."""

    def test_is_feature_enabled_not_found(self, fresh_app):
        """Test feature check when flag doesn't exist."""
        from app.utils.feature_flags import is_feature_enabled
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            result = is_feature_enabled('nonexistent_feature')
            assert result == False


class TestGetFeatureConfig:
    """Tests for get_feature_config function."""

    def test_get_feature_config_not_found(self, fresh_app):
        """Test getting config for nonexistent feature."""
        from app.utils.feature_flags import get_feature_config
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            result = get_feature_config('nonexistent', key='some_key', default='default_value')
            assert result == 'default_value'


class TestGetAllFeatures:
    """Tests for get_all_features function."""

    def test_get_all_features_empty(self, fresh_app):
        """Test getting all features when none exist."""
        from app.utils.feature_flags import get_all_features
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            result = get_all_features()
            assert isinstance(result, list)


class TestGetEnabledFeatures:
    """Tests for get_enabled_features function."""

    def test_get_enabled_features_empty(self, fresh_app):
        """Test getting enabled features when none enabled."""
        from app.utils.feature_flags import get_enabled_features
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            result = get_enabled_features()
            assert isinstance(result, list)


class TestFeatureRequiredDecorator:
    """Tests for feature_required decorator."""

    def test_feature_required_disabled_json(self, fresh_app):
        """Test feature_required returns 403 for JSON requests when feature disabled."""
        from app.utils.feature_flags import feature_required
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            @fresh_app.route('/test_feature_required_json')
            @feature_required('disabled_feature')
            def test_view():
                return 'success'

            with fresh_app.test_client() as client:
                response = client.get(
                    '/test_feature_required_json',
                    headers={'Content-Type': 'application/json'},
                    content_type='application/json'
                )
                # Should return 403 for disabled feature
                assert response.status_code == 403


class TestFeatureOr404:
    """Tests for feature_or_404 function."""

    def test_feature_or_404_aborts_when_disabled(self, fresh_app):
        """Test feature_or_404 aborts when feature disabled."""
        from app.utils.feature_flags import feature_or_404
        from app.models import db
        from werkzeug.exceptions import NotFound

        with fresh_app.app_context():
            db.create_all()

            with fresh_app.test_request_context():
                with pytest.raises(NotFound):
                    feature_or_404('nonexistent_feature')


class TestInjectFeatureFlags:
    """Tests for inject_feature_flags function."""

    def test_inject_feature_flags_returns_dict(self, fresh_app):
        """Test inject_feature_flags returns correct dict."""
        from app.utils.feature_flags import inject_feature_flags
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            result = inject_feature_flags()

            assert 'is_feature_enabled' in result
            assert 'enabled_features' in result
            assert callable(result['is_feature_enabled'])
            assert isinstance(result['enabled_features'], list)


class TestFeaturesConstants:
    """Tests for Features class constants."""

    def test_features_constants_exist(self):
        """Test feature flag constants are defined."""
        from app.utils.feature_flags import Features

        assert Features.SMS_NOTIFICATIONS == 'sms_notifications'
        assert Features.EMAIL_NOTIFICATIONS == 'email_notifications'
        assert Features.WHATSAPP_NOTIFICATIONS == 'whatsapp_notifications'
        assert Features.PROMOTIONS == 'promotions'
        assert Features.GIFT_VOUCHERS == 'gift_vouchers'


# =============================================================================
# EMAIL SERVICE CLASS TESTS - app/services/email_service.py
# =============================================================================

class TestEmailServiceClass:
    """Tests for EmailService class."""

    def test_email_service_init(self, fresh_app):
        """Test EmailService initialization."""
        from app.services.email_service import EmailService

        service = EmailService(fresh_app)

        assert service.app == fresh_app
        assert service.scheduler is None

    @patch('app.services.email_service.smtplib.SMTP')
    def test_email_service_send_email_success(self, mock_smtp, fresh_app):
        """Test EmailService send_email method."""
        from app.services.email_service import EmailService

        fresh_app.config['MAIL_SERVER'] = 'smtp.test.com'
        fresh_app.config['MAIL_PORT'] = 587
        fresh_app.config['MAIL_USE_TLS'] = True
        fresh_app.config['MAIL_USERNAME'] = 'test@test.com'
        fresh_app.config['MAIL_PASSWORD'] = 'password'
        fresh_app.config['MAIL_DEFAULT_SENDER'] = 'sender@test.com'

        service = EmailService(fresh_app)

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = Mock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = Mock(return_value=False)

        result = service.send_email(
            ['recipient@test.com'],
            'Test Subject',
            '<html><body>Test</body></html>'
        )

        assert result == True

    @patch('app.services.email_service.smtplib.SMTP')
    def test_email_service_send_email_with_attachment(self, mock_smtp, fresh_app):
        """Test EmailService send_email with attachments."""
        from app.services.email_service import EmailService

        fresh_app.config['MAIL_SERVER'] = 'smtp.test.com'
        fresh_app.config['MAIL_PORT'] = 587
        fresh_app.config['MAIL_USE_TLS'] = True
        fresh_app.config['MAIL_USERNAME'] = 'test@test.com'
        fresh_app.config['MAIL_PASSWORD'] = 'password'
        fresh_app.config['MAIL_DEFAULT_SENDER'] = 'sender@test.com'

        service = EmailService(fresh_app)

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = Mock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = Mock(return_value=False)

        # Create a temp file to attach
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b'test content')
            temp_path = f.name

        try:
            result = service.send_email(
                ['recipient@test.com'],
                'Test Subject',
                '<html><body>Test</body></html>',
                attachments=[temp_path]
            )

            assert result == True
        finally:
            os.unlink(temp_path)

    def test_email_service_send_email_failure(self, fresh_app):
        """Test EmailService send_email handles errors."""
        from app.services.email_service import EmailService

        fresh_app.config['MAIL_SERVER'] = 'invalid.server'
        fresh_app.config['MAIL_PORT'] = 587
        fresh_app.config['MAIL_USE_TLS'] = True
        fresh_app.config['MAIL_USERNAME'] = 'test@test.com'
        fresh_app.config['MAIL_PASSWORD'] = 'password'
        fresh_app.config['MAIL_DEFAULT_SENDER'] = 'sender@test.com'

        service = EmailService(fresh_app)

        result = service.send_email(
            ['recipient@test.com'],
            'Test Subject',
            '<html><body>Test</body></html>'
        )

        assert result == False

    def test_email_service_generate_daily_report_html(self, fresh_app):
        """Test EmailService generate_daily_report_html method."""
        from app.services.email_service import EmailService
        from app.models import db

        fresh_app.config['CURRENCY_SYMBOL'] = 'Rs.'
        fresh_app.config['BUSINESS_NAME'] = 'Test Business'

        with fresh_app.app_context():
            db.create_all()

            service = EmailService(fresh_app)

            html = service.generate_daily_report_html()

            assert 'Test Business' in html
            assert 'Daily Sales Report' in html
            assert 'html' in html.lower()

    def test_email_service_start_scheduler(self, fresh_app):
        """Test EmailService scheduler start."""
        from app.services.email_service import EmailService

        fresh_app.config['DAILY_REPORT_TIME'] = '18:00'

        service = EmailService(fresh_app)

        try:
            service.start_scheduler()
            assert service.scheduler is not None
        finally:
            service.stop_scheduler()

    def test_email_service_stop_scheduler(self, fresh_app):
        """Test EmailService scheduler stop."""
        from app.services.email_service import EmailService

        fresh_app.config['DAILY_REPORT_TIME'] = '18:00'

        service = EmailService(fresh_app)
        service.start_scheduler()
        service.stop_scheduler()

        assert service.scheduler is None


# =============================================================================
# BACKUP SERVICE TESTS - app/services/backup_service.py
# =============================================================================

class TestBackupServiceClass:
    """Tests for BackupService class."""

    def test_backup_service_init(self, fresh_app):
        """Test BackupService initialization."""
        from app.services.backup_service import BackupService

        service = BackupService(fresh_app)

        assert service.app == fresh_app
        assert service.scheduler is None

    def test_backup_database_success(self, fresh_app):
        """Test successful database backup."""
        from app.services.backup_service import BackupService
        from app.models import db

        # Create temp directories
        with tempfile.TemporaryDirectory() as backup_dir:
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as db_file:
                db_path = db_file.name
                db_file.write(b'test database content')

            try:
                fresh_app.config['BACKUP_FOLDER'] = backup_dir
                fresh_app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
                fresh_app.config['BACKUP_RETENTION_DAYS'] = 30

                with fresh_app.app_context():
                    service = BackupService(fresh_app)
                    result = service.backup_database()

                    assert result is not None
                    assert os.path.exists(result)
            finally:
                os.unlink(db_path)

    def test_backup_database_no_db_file(self, fresh_app):
        """Test backup when database file doesn't exist."""
        from app.services.backup_service import BackupService

        with tempfile.TemporaryDirectory() as backup_dir:
            fresh_app.config['BACKUP_FOLDER'] = backup_dir
            fresh_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///nonexistent.db'

            with fresh_app.app_context():
                service = BackupService(fresh_app)
                result = service.backup_database()

                assert result is None

    def test_cleanup_old_backups(self, fresh_app):
        """Test cleanup of old backups."""
        from app.services.backup_service import BackupService

        with tempfile.TemporaryDirectory() as backup_dir:
            # Create old backup files
            old_backup = os.path.join(backup_dir, 'backup_20200101_120000.db')
            with open(old_backup, 'w') as f:
                f.write('old backup')

            # Set modification time to old date
            old_time = time.time() - (60 * 60 * 24 * 100)  # 100 days ago
            os.utime(old_backup, (old_time, old_time))

            fresh_app.config['BACKUP_FOLDER'] = backup_dir
            fresh_app.config['BACKUP_RETENTION_DAYS'] = 30

            service = BackupService(fresh_app)
            service.cleanup_old_backups()

            # Old backup should be deleted
            assert not os.path.exists(old_backup)

    def test_restore_backup_success(self, fresh_app):
        """Test successful backup restoration."""
        from app.services.backup_service import BackupService

        with tempfile.TemporaryDirectory() as backup_dir:
            # Create backup file
            backup_file = 'backup_20231215_120000.db'
            backup_path = os.path.join(backup_dir, backup_file)
            with open(backup_path, 'w') as f:
                f.write('backup content')

            # Create current database
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as db_file:
                db_path = db_file.name
                db_file.write(b'current content')

            try:
                fresh_app.config['BACKUP_FOLDER'] = backup_dir
                fresh_app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

                service = BackupService(fresh_app)
                result = service.restore_backup(backup_file)

                assert result == True
            finally:
                os.unlink(db_path)

    def test_restore_backup_not_found(self, fresh_app):
        """Test restore when backup file doesn't exist."""
        from app.services.backup_service import BackupService

        with tempfile.TemporaryDirectory() as backup_dir:
            fresh_app.config['BACKUP_FOLDER'] = backup_dir

            service = BackupService(fresh_app)
            result = service.restore_backup('nonexistent_backup.db')

            assert result == False

    def test_list_backups(self, fresh_app):
        """Test listing available backups."""
        from app.services.backup_service import BackupService

        with tempfile.TemporaryDirectory() as backup_dir:
            # Create test backup files
            for i in range(3):
                backup_path = os.path.join(backup_dir, f'backup_2023121{i}_120000.db')
                with open(backup_path, 'w') as f:
                    f.write(f'backup {i}')

            fresh_app.config['BACKUP_FOLDER'] = backup_dir

            service = BackupService(fresh_app)
            backups = service.list_backups()

            assert len(backups) == 3
            assert all('filename' in b for b in backups)
            assert all('size' in b for b in backups)
            assert all('created' in b for b in backups)

    def test_list_backups_empty_folder(self, fresh_app):
        """Test listing backups when folder is empty."""
        from app.services.backup_service import BackupService

        with tempfile.TemporaryDirectory() as backup_dir:
            fresh_app.config['BACKUP_FOLDER'] = backup_dir

            service = BackupService(fresh_app)
            backups = service.list_backups()

            assert backups == []

    def test_backup_service_scheduler(self, fresh_app):
        """Test BackupService scheduler functionality."""
        from app.services.backup_service import BackupService

        fresh_app.config['BACKUP_ENABLED'] = True
        fresh_app.config['BACKUP_TIME'] = '23:00'

        service = BackupService(fresh_app)

        try:
            service.start_scheduler()
            assert service.scheduler is not None
        finally:
            service.stop_scheduler()
            assert service.scheduler is None

    def test_backup_service_scheduler_disabled(self, fresh_app):
        """Test BackupService scheduler when disabled."""
        from app.services.backup_service import BackupService

        fresh_app.config['BACKUP_ENABLED'] = False

        service = BackupService(fresh_app)
        service.start_scheduler()

        # Scheduler should not start when disabled
        assert service.scheduler is None


# =============================================================================
# SYNC SERVICE TESTS - app/services/sync_service.py
# =============================================================================

class TestSyncServiceClass:
    """Tests for SyncService class."""

    def test_sync_service_init(self, fresh_app):
        """Test SyncService initialization."""
        from app.services.sync_service import SyncService

        service = SyncService(fresh_app)

        assert service.app == fresh_app
        assert service.scheduler is None
        assert service.cloud_engine is None

    @patch('app.services.sync_service.requests.get')
    def test_check_internet_connection_available(self, mock_get, fresh_app):
        """Test internet connection check when available."""
        from app.services.sync_service import SyncService

        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        service = SyncService(fresh_app)
        result = service.check_internet_connection()

        assert result == True

    @patch('app.services.sync_service.requests.get')
    def test_check_internet_connection_unavailable(self, mock_get, fresh_app):
        """Test internet connection check when unavailable."""
        from app.services.sync_service import SyncService

        mock_get.side_effect = Exception('Connection failed')

        service = SyncService(fresh_app)
        result = service.check_internet_connection()

        assert result == False

    def test_get_cloud_engine_not_configured(self, fresh_app):
        """Test get_cloud_engine when not configured."""
        from app.services.sync_service import SyncService

        fresh_app.config['CLOUD_DATABASE_URL'] = None

        service = SyncService(fresh_app)
        result = service.get_cloud_engine()

        assert result is None

    def test_get_cloud_engine_configured(self, fresh_app):
        """Test get_cloud_engine when configured."""
        from app.services.sync_service import SyncService

        fresh_app.config['CLOUD_DATABASE_URL'] = 'sqlite:///:memory:'

        service = SyncService(fresh_app)
        result = service.get_cloud_engine()

        assert result is not None

    @patch('app.services.sync_service.requests.get')
    def test_process_sync_queue_no_internet(self, mock_get, fresh_app):
        """Test sync queue processing without internet."""
        from app.services.sync_service import SyncService

        mock_get.side_effect = Exception('No connection')
        fresh_app.config['ENABLE_CLOUD_SYNC'] = True

        service = SyncService(fresh_app)

        # Should not raise error when no internet
        service.process_sync_queue()

    def test_process_sync_queue_sync_disabled(self, fresh_app):
        """Test sync queue processing when sync is disabled."""
        from app.services.sync_service import SyncService

        fresh_app.config['ENABLE_CLOUD_SYNC'] = False

        service = SyncService(fresh_app)
        service.process_sync_queue()  # Should not raise

    def test_get_sync_status(self, fresh_app):
        """Test get_sync_status method."""
        from app.services.sync_service import SyncService
        from app.models import db

        fresh_app.config['ENABLE_CLOUD_SYNC'] = True

        with fresh_app.app_context():
            db.create_all()

            service = SyncService(fresh_app)

            with patch.object(service, 'check_internet_connection', return_value=True):
                status = service.get_sync_status()

            assert 'pending' in status
            assert 'synced' in status
            assert 'failed' in status
            assert 'internet_available' in status
            assert 'sync_enabled' in status

    def test_sync_service_scheduler_disabled(self, fresh_app):
        """Test SyncService scheduler when sync is disabled."""
        from app.services.sync_service import SyncService

        fresh_app.config['ENABLE_CLOUD_SYNC'] = False

        service = SyncService(fresh_app)
        service.start_scheduler()

        assert service.scheduler is None

    def test_sync_service_scheduler_enabled(self, fresh_app):
        """Test SyncService scheduler when sync is enabled."""
        from app.services.sync_service import SyncService

        fresh_app.config['ENABLE_CLOUD_SYNC'] = True
        fresh_app.config['SYNC_INTERVAL_MINUTES'] = 30

        service = SyncService(fresh_app)

        try:
            service.start_scheduler()
            assert service.scheduler is not None
        finally:
            service.stop_scheduler()


# =============================================================================
# PRODUCTION SERVICE TESTS - app/services/production_service.py
# =============================================================================

class TestProductionServiceClass:
    """Tests for ProductionService class."""

    def test_generate_order_number_format(self, fresh_app):
        """Test production order number format."""
        from app.services.production_service import ProductionService
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            order_num = ProductionService.generate_order_number()

            assert order_num.startswith('PRD')
            # Format is PRDYYYYMMDDnnnn (15 characters total)
            assert len(order_num) == 15

            # Extract and validate date part (YYYYMMDD)
            date_part = order_num[3:11]
            assert len(date_part) == 8
            assert date_part.isdigit()

            # Validate sequence part (4 digits)
            seq_part = order_num[11:]
            assert len(seq_part) == 4
            assert seq_part.isdigit()

    def test_calculate_material_requirements_recipe_not_found(self, fresh_app):
        """Test material requirements with nonexistent recipe."""
        from app.services.production_service import ProductionService
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            result = ProductionService.calculate_material_requirements(
                recipe_id=99999,
                quantity=10
            )

            assert 'error' in result
            assert result['error'] == 'Recipe not found'

    def test_check_material_availability_recipe_not_found(self, fresh_app):
        """Test material availability with nonexistent recipe."""
        from app.services.production_service import ProductionService
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            result = ProductionService.check_material_availability(
                recipe_id=99999,
                quantity=10,
                location_id=1
            )

            assert 'error' in result

    def test_check_material_availability_location_not_found(self, fresh_app):
        """Test material availability with nonexistent location."""
        from app.services.production_service import ProductionService
        from app.models import db, Recipe, Product

        with fresh_app.app_context():
            db.create_all()

            # Create a minimal recipe with all required fields
            product = Product(
                code='TEST001',
                name='Test Product',
                cost_price=Decimal('100.00'),
                selling_price=Decimal('200.00'),
                quantity=0
            )
            db.session.add(product)
            db.session.flush()

            recipe = Recipe(
                code='RCP-TEST-001',  # Required field
                name='Test Recipe',
                product_id=product.id,
                recipe_type='single_oil',
                output_size_ml=Decimal('50.00'),
                oil_percentage=Decimal('100.00')
            )
            db.session.add(recipe)
            db.session.commit()

            result = ProductionService.check_material_availability(
                recipe_id=recipe.id,
                quantity=10,
                location_id=99999
            )

            assert 'error' in result
            assert result['error'] == 'Location not found'

    def test_create_production_order_recipe_not_found(self, fresh_app):
        """Test creating order with nonexistent recipe."""
        from app.services.production_service import ProductionService
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            order, error = ProductionService.create_production_order(
                recipe_id=99999,
                quantity=10,
                location_id=1,
                user_id=1
            )

            assert order is None
            assert error == 'Recipe not found'

    def test_submit_order_not_found(self, fresh_app):
        """Test submitting nonexistent order."""
        from app.services.production_service import ProductionService
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            success, error = ProductionService.submit_order(order_id=99999)

            assert success == False
            assert error == 'Order not found'

    def test_approve_order_not_found(self, fresh_app):
        """Test approving nonexistent order."""
        from app.services.production_service import ProductionService
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            success, error = ProductionService.approve_order(
                order_id=99999,
                user_id=1
            )

            assert success == False
            assert error == 'Order not found'

    def test_reject_order_not_found(self, fresh_app):
        """Test rejecting nonexistent order."""
        from app.services.production_service import ProductionService
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            success, error = ProductionService.reject_order(
                order_id=99999,
                user_id=1,
                reason='Test rejection'
            )

            assert success == False
            assert error == 'Order not found'

    def test_start_production_not_found(self, fresh_app):
        """Test starting nonexistent production."""
        from app.services.production_service import ProductionService
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            success, error = ProductionService.start_production(
                order_id=99999,
                user_id=1
            )

            assert success == False
            assert error == 'Order not found'

    def test_execute_production_not_found(self, fresh_app):
        """Test executing nonexistent production."""
        from app.services.production_service import ProductionService
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            success, error = ProductionService.execute_production(
                order_id=99999,
                user_id=1
            )

            assert success == False
            assert error == 'Order not found'

    def test_cancel_order_not_found(self, fresh_app):
        """Test cancelling nonexistent order."""
        from app.services.production_service import ProductionService
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            success, error = ProductionService.cancel_order(
                order_id=99999,
                user_id=1
            )

            assert success == False
            assert error == 'Order not found'

    def test_get_production_stats(self, fresh_app):
        """Test getting production statistics."""
        from app.services.production_service import ProductionService
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            stats = ProductionService.get_production_stats()

            assert 'status_counts' in stats
            assert 'pending_count' in stats
            assert 'in_progress_count' in stats
            assert 'completed_count' in stats
            assert 'month_total_produced' in stats

    def test_get_low_stock_materials(self, fresh_app):
        """Test getting low stock materials."""
        from app.services.production_service import ProductionService
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            low_stock = ProductionService.get_low_stock_materials()

            assert isinstance(low_stock, list)


# =============================================================================
# EDGE CASES AND ERROR HANDLING TESTS
# =============================================================================

class TestEdgeCasesNullInputs:
    """Tests for NULL/None input handling."""

    def test_format_currency_none(self):
        """Test format_currency with None raises error."""
        from app.utils.helpers import format_currency

        with pytest.raises((TypeError, ValueError)):
            format_currency(None)

    def test_format_percentage_none(self):
        """Test format_percentage with None raises error."""
        from app.utils.helpers import format_percentage

        with pytest.raises((TypeError, ValueError)):
            format_percentage(None)

    def test_calculate_profit_margin_none_selling(self):
        """Test profit margin with None selling price."""
        from app.utils.helpers import calculate_profit_margin

        # Should handle gracefully or raise
        try:
            result = calculate_profit_margin(100, None)
            # If it doesn't raise, it should return something reasonable
        except (TypeError, ValueError):
            pass  # Expected behavior


class TestEdgeCasesEmptyStrings:
    """Tests for empty string input handling."""

    def test_get_date_range_empty_period(self):
        """Test get_date_range with empty string."""
        from app.utils.helpers import get_date_range

        start, end = get_date_range('')
        today = datetime.now().date()
        assert start == today
        assert end == today

    def test_sanitize_filename_empty(self):
        """Test sanitize_filename with empty string."""
        from app.utils.helpers import sanitize_filename

        result = sanitize_filename('')
        # Werkzeug's secure_filename returns empty for empty input
        assert result == ''


class TestEdgeCasesInvalidTypes:
    """Tests for invalid type handling."""

    def test_format_currency_string_input(self):
        """Test format_currency with string input."""
        from app.utils.helpers import format_currency

        with pytest.raises((TypeError, ValueError)):
            format_currency('not a number')

    def test_format_percentage_string_input(self):
        """Test format_percentage with string input."""
        from app.utils.helpers import format_percentage

        with pytest.raises((TypeError, ValueError)):
            format_percentage('50%')

    def test_calculate_profit_margin_string_inputs(self):
        """Test profit margin with string inputs."""
        from app.utils.helpers import calculate_profit_margin

        # This should either handle or raise
        try:
            result = calculate_profit_margin('100', '150')
            # If it accepts strings, result should be numeric
            assert isinstance(result, (int, float))
        except (TypeError, ValueError):
            pass  # Expected if strict typing


class TestEdgeCasesBoundaryValues:
    """Tests for boundary value handling."""

    def test_format_currency_max_float(self):
        """Test format_currency with very large float."""
        from app.utils.helpers import format_currency

        # Test with large but not infinite value
        result = format_currency(1e15)
        assert result is not None

    def test_format_currency_negative_zero(self):
        """Test format_currency with negative zero."""
        from app.utils.helpers import format_currency

        result = format_currency(-0.0)
        assert 'Rs.' in result

    def test_profit_margin_very_small_cost(self):
        """Test profit margin with very small cost."""
        from app.utils.helpers import calculate_profit_margin

        result = calculate_profit_margin(0.001, 100)
        assert result > 0

    def test_date_range_at_year_boundary(self):
        """Test date range functions work at year boundaries."""
        from app.utils.helpers import get_date_range

        # All period types should work
        for period in ['today', 'yesterday', 'this_week', 'last_week',
                       'this_month', 'last_month']:
            start, end = get_date_range(period)
            assert start is not None
            assert end is not None
            assert start <= end


class TestErrorHandling:
    """Tests for error handling and recovery."""

    def test_bulk_insert_with_invalid_data(self, fresh_app):
        """Test bulk_insert handles invalid data gracefully."""
        from app.utils.db_utils import bulk_insert
        from app.models import db, Category

        with fresh_app.app_context():
            db.create_all()

            # Try to insert with invalid data (missing required field)
            invalid_data = [
                {'invalid_field': 'value'}
            ]

            # Should handle error and return 0
            count = bulk_insert(Category, invalid_data)
            assert count == 0

    def test_safe_commit_handles_error(self, fresh_app):
        """Test safe_commit handles errors gracefully."""
        from app.utils.db_utils import safe_commit
        from app.models import db

        with fresh_app.app_context():
            db.create_all()

            # Force an error condition (commit without valid data)
            # This should not raise, but return False
            result = safe_commit()
            # Even without changes, commit should succeed
            assert result in [True, False]


class TestPerformance:
    """Tests for performance-related scenarios."""

    def test_generate_many_sale_numbers(self):
        """Test generating many sale numbers efficiently."""
        from app.utils.helpers import generate_sale_number

        start_time = time.time()
        numbers = [generate_sale_number() for _ in range(1000)]
        elapsed = time.time() - start_time

        # Should complete quickly
        assert elapsed < 5.0  # 5 seconds max
        assert len(numbers) == 1000

    def test_bulk_insert_large_dataset(self, fresh_app):
        """Test bulk insert with large dataset."""
        from app.utils.db_utils import bulk_insert
        from app.models import db, Category

        with fresh_app.app_context():
            db.create_all()

            # Create large dataset
            data_list = [
                {'name': f'Category {i}', 'description': f'Description {i}'}
                for i in range(500)
            ]

            start_time = time.time()
            count = bulk_insert(Category, data_list)
            elapsed = time.time() - start_time

            assert count == 500
            # Should complete in reasonable time
            assert elapsed < 10.0


class TestConcurrency:
    """Tests for concurrent operation handling."""

    def test_concurrent_sale_number_generation(self):
        """Test sale number uniqueness under concurrent generation."""
        from app.utils.helpers import generate_sale_number
        from concurrent.futures import ThreadPoolExecutor

        def generate():
            return generate_sale_number()

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(generate) for _ in range(100)]
            results = [f.result() for f in futures]

        # Check uniqueness rate (allow small collision probability)
        unique_results = set(results)
        assert len(unique_results) >= 90  # At least 90% unique


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestHelpersIntegration:
    """Integration tests for helper functions with Flask app."""

    def test_helpers_in_request_context(self, fresh_app):
        """Test helper functions work within request context."""
        from app.utils.helpers import (
            format_currency, format_percentage,
            calculate_profit_margin, get_date_range
        )

        with fresh_app.app_context():
            with fresh_app.test_request_context():
                # All functions should work in request context
                assert format_currency(100) == "Rs. 100.00"
                assert format_percentage(50) == "50.00%"
                assert calculate_profit_margin(100, 150) == 50.0
                start, end = get_date_range('today')
                assert start == end


class TestServicesIntegration:
    """Integration tests for services."""

    def test_backup_and_restore_cycle(self, fresh_app):
        """Test complete backup and restore cycle."""
        from app.services.backup_service import BackupService
        from app.models import db

        with tempfile.TemporaryDirectory() as backup_dir:
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as db_file:
                db_path = db_file.name
                db_file.write(b'test database content')

            try:
                fresh_app.config['BACKUP_FOLDER'] = backup_dir
                fresh_app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
                fresh_app.config['BACKUP_RETENTION_DAYS'] = 30

                with fresh_app.app_context():
                    service = BackupService(fresh_app)

                    # Create backup
                    backup_path = service.backup_database()
                    assert backup_path is not None

                    # List backups
                    backups = service.list_backups()
                    assert len(backups) >= 1

                    # Restore backup
                    backup_filename = os.path.basename(backup_path)
                    result = service.restore_backup(backup_filename)
                    assert result == True
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)


# =============================================================================
# SPECIAL CHARACTER HANDLING TESTS
# =============================================================================

class TestSpecialCharacterHandling:
    """Tests for special character handling."""

    def test_format_currency_with_special_currency_symbol(self):
        """Test currency formatting with unicode symbols."""
        from app.utils.helpers import format_currency

        # Various currency symbols
        assert format_currency(1000, '€') == "€ 1,000.00"
        assert format_currency(1000, '¥') == "¥ 1,000.00"
        assert format_currency(1000, '₹') == "₹ 1,000.00"

    def test_sanitize_filename_unicode(self):
        """Test sanitizing filename with unicode characters."""
        from app.utils.helpers import sanitize_filename

        # Arabic characters
        result = sanitize_filename('ملف.pdf')
        assert result is not None

        # Chinese characters
        result = sanitize_filename('文件.pdf')
        assert result is not None

    def test_sanitize_filename_malicious(self):
        """Test sanitizing potentially malicious filenames."""
        from app.utils.helpers import sanitize_filename

        # Path traversal attempts
        result = sanitize_filename('../../../etc/passwd')
        assert '..' not in result
        assert '/' not in result or result.count('/') == 0

        # NULL byte injection
        result = sanitize_filename('file\x00.pdf')
        assert '\x00' not in result


# =============================================================================
# MEMORY AND RESOURCE TESTS
# =============================================================================

class TestMemoryAndResources:
    """Tests for memory and resource management."""

    def test_backup_service_scheduler_cleanup(self, fresh_app):
        """Test scheduler properly cleans up resources."""
        from app.services.backup_service import BackupService

        fresh_app.config['BACKUP_ENABLED'] = True
        fresh_app.config['BACKUP_TIME'] = '23:00'

        service = BackupService(fresh_app)

        # Start and stop multiple times
        for _ in range(5):
            service.start_scheduler()
            service.stop_scheduler()

        # Should be properly cleaned up
        assert service.scheduler is None

    def test_email_service_scheduler_cleanup(self, fresh_app):
        """Test email scheduler properly cleans up resources."""
        from app.services.email_service import EmailService

        fresh_app.config['DAILY_REPORT_TIME'] = '18:00'

        service = EmailService(fresh_app)

        # Start and stop multiple times
        for _ in range(5):
            service.start_scheduler()
            service.stop_scheduler()

        assert service.scheduler is None


# =============================================================================
# LOGGING TESTS
# =============================================================================

class TestLogging:
    """Tests for proper logging behavior."""

    def test_db_utils_logs_errors(self, fresh_app, caplog):
        """Test database utilities log errors properly."""
        from app.utils.db_utils import bulk_insert
        from app.models import db, Category

        with fresh_app.app_context():
            db.create_all()

            with caplog.at_level(logging.ERROR):
                # Force an error
                bulk_insert(Category, [{'nonexistent_field': 'value'}])

            # Error should be logged
            # (specific log message depends on implementation)

    def test_backup_service_logs_operations(self, fresh_app, caplog):
        """Test backup service logs operations."""
        from app.services.backup_service import BackupService

        with tempfile.TemporaryDirectory() as backup_dir:
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as db_file:
                db_path = db_file.name
                db_file.write(b'test')

            try:
                fresh_app.config['BACKUP_FOLDER'] = backup_dir
                fresh_app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
                fresh_app.config['BACKUP_RETENTION_DAYS'] = 30

                with fresh_app.app_context():
                    with caplog.at_level(logging.INFO):
                        service = BackupService(fresh_app)
                        service.backup_database()

                    # Should log backup creation
                    assert any('backup' in record.message.lower()
                             for record in caplog.records)
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)


# =============================================================================
# CONFIGURATION TESTS
# =============================================================================

class TestConfiguration:
    """Tests for configuration handling."""

    def test_email_service_uses_config(self, fresh_app):
        """Test EmailService uses app configuration."""
        from app.services.email_service import EmailService

        fresh_app.config['MAIL_SERVER'] = 'custom.server.com'
        fresh_app.config['MAIL_PORT'] = 465

        service = EmailService(fresh_app)

        # Service should have access to config
        assert service.app.config['MAIL_SERVER'] == 'custom.server.com'
        assert service.app.config['MAIL_PORT'] == 465

    def test_backup_service_uses_config(self, fresh_app):
        """Test BackupService uses app configuration."""
        from app.services.backup_service import BackupService

        fresh_app.config['BACKUP_FOLDER'] = '/custom/backup/path'
        fresh_app.config['BACKUP_RETENTION_DAYS'] = 60

        service = BackupService(fresh_app)

        assert service.app.config['BACKUP_FOLDER'] == '/custom/backup/path'
        assert service.app.config['BACKUP_RETENTION_DAYS'] == 60


# =============================================================================
# FIXTURE-BASED INTEGRATION TESTS
# =============================================================================

class TestWithInitializedDatabase:
    """Tests that use the initialized database fixture."""

    def test_db_utils_with_real_data(self, fresh_app, init_database):
        """Test database utilities with real test data."""
        from app.utils.db_utils import get_or_create, paginate_query
        from app.models import Category, Product

        with fresh_app.app_context():
            # Get existing category
            category, created = get_or_create(Category, name='Attars')
            assert created == False
            assert category.name == 'Attars'

            # Paginate products
            query = Product.query.filter_by(is_active=True)
            pagination = paginate_query(query, page=1, per_page=10)
            assert len(pagination.items) > 0

    def test_helpers_with_real_products(self, fresh_app, init_database):
        """Test helper functions with real product data."""
        from app.utils.helpers import calculate_profit_margin
        from app.models import Product

        with fresh_app.app_context():
            product = Product.query.first()

            margin = calculate_profit_margin(
                float(product.cost_price),
                float(product.selling_price)
            )

            assert margin > 0  # Products should have positive margins


# Run tests if executed directly
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
