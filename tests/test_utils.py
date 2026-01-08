"""
Comprehensive Unit Tests for Utility Functions and Helpers

Tests cover:
- Permission utilities and decorators
- Helper functions
- Template filters/context processors
- Feature flags
- Location context
- Database utilities
- Date range calculations
- Currency formatting
- Inventory forecasting calculations

Author: Auto-generated
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, date, timedelta
from decimal import Decimal
from functools import wraps
import sys
import os

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_current_user():
    """Create a mock current user"""
    user = Mock()
    user.is_authenticated = True
    user.id = 1
    user.username = 'testuser'
    user.location_id = 1
    user.is_global_admin = False
    user.has_permission = Mock(return_value=True)
    user.has_role = Mock(return_value=True)
    user.can_access_location = Mock(return_value=True)
    user.get_accessible_locations = Mock(return_value=[])
    return user


@pytest.fixture
def mock_unauthenticated_user():
    """Create a mock unauthenticated user"""
    user = Mock()
    user.is_authenticated = False
    return user


@pytest.fixture
def mock_flask_app():
    """Create a mock Flask application"""
    app = Mock()
    app.config = {
        'ALLOWED_EXTENSIONS': {'png', 'jpg', 'jpeg', 'gif'},
        'CURRENCY_SYMBOL': 'Rs.',
        'BUSINESS_NAME': 'Test Business'
    }
    return app


@pytest.fixture
def mock_request_json():
    """Create a mock JSON request"""
    request = Mock()
    request.is_json = True
    return request


@pytest.fixture
def mock_request_html():
    """Create a mock HTML request"""
    request = Mock()
    request.is_json = False
    return request


@pytest.fixture
def mock_location():
    """Create a mock location"""
    location = Mock()
    location.id = 1
    location.name = 'Test Location'
    location.is_warehouse = False
    location.is_kiosk = True
    return location


@pytest.fixture
def mock_warehouse_location():
    """Create a mock warehouse location"""
    location = Mock()
    location.id = 2
    location.name = 'Test Warehouse'
    location.is_warehouse = True
    location.is_kiosk = False
    return location


# ============================================================================
# Test: helpers.py - format_currency
# ============================================================================

class TestFormatCurrency:
    """Tests for format_currency function"""

    def test_format_currency_positive_value(self):
        """Test formatting positive currency amount"""
        from app.utils.helpers import format_currency
        result = format_currency(1000)
        assert result == "Rs. 1,000.00"

    def test_format_currency_zero(self):
        """Test formatting zero amount"""
        from app.utils.helpers import format_currency
        result = format_currency(0)
        assert result == "Rs. 0.00"

    def test_format_currency_negative_value(self):
        """Test formatting negative currency amount"""
        from app.utils.helpers import format_currency
        result = format_currency(-500)
        assert result == "Rs. -500.00"

    def test_format_currency_decimal_value(self):
        """Test formatting decimal currency amount"""
        from app.utils.helpers import format_currency
        result = format_currency(1234.56)
        assert result == "Rs. 1,234.56"

    def test_format_currency_large_value(self):
        """Test formatting large currency amount"""
        from app.utils.helpers import format_currency
        result = format_currency(1000000)
        assert result == "Rs. 1,000,000.00"

    def test_format_currency_custom_symbol(self):
        """Test formatting with custom currency symbol"""
        from app.utils.helpers import format_currency
        result = format_currency(100, currency_symbol='$')
        assert result == "$ 100.00"

    def test_format_currency_empty_symbol(self):
        """Test formatting with empty currency symbol"""
        from app.utils.helpers import format_currency
        result = format_currency(100, currency_symbol='')
        assert result == " 100.00"


# ============================================================================
# Test: helpers.py - format_percentage
# ============================================================================

class TestFormatPercentage:
    """Tests for format_percentage function"""

    def test_format_percentage_positive(self):
        """Test formatting positive percentage"""
        from app.utils.helpers import format_percentage
        result = format_percentage(75.5)
        assert result == "75.50%"

    def test_format_percentage_zero(self):
        """Test formatting zero percentage"""
        from app.utils.helpers import format_percentage
        result = format_percentage(0)
        assert result == "0.00%"

    def test_format_percentage_negative(self):
        """Test formatting negative percentage"""
        from app.utils.helpers import format_percentage
        result = format_percentage(-10.5)
        assert result == "-10.50%"

    def test_format_percentage_whole_number(self):
        """Test formatting whole number percentage"""
        from app.utils.helpers import format_percentage
        result = format_percentage(100)
        assert result == "100.00%"

    def test_format_percentage_many_decimals(self):
        """Test formatting percentage with many decimals (truncation)"""
        from app.utils.helpers import format_percentage
        result = format_percentage(33.333333)
        assert result == "33.33%"


# ============================================================================
# Test: helpers.py - calculate_profit_margin
# ============================================================================

class TestCalculateProfitMargin:
    """Tests for calculate_profit_margin function"""

    def test_profit_margin_normal(self):
        """Test normal profit margin calculation"""
        from app.utils.helpers import calculate_profit_margin
        result = calculate_profit_margin(100, 150)
        assert result == 50.0

    def test_profit_margin_zero_cost(self):
        """Test profit margin with zero cost price"""
        from app.utils.helpers import calculate_profit_margin
        result = calculate_profit_margin(0, 100)
        assert result == 0

    def test_profit_margin_none_cost(self):
        """Test profit margin with None cost price"""
        from app.utils.helpers import calculate_profit_margin
        result = calculate_profit_margin(None, 100)
        assert result == 0

    def test_profit_margin_negative(self):
        """Test negative profit margin (loss)"""
        from app.utils.helpers import calculate_profit_margin
        result = calculate_profit_margin(100, 80)
        assert result == -20.0

    def test_profit_margin_equal_prices(self):
        """Test profit margin with equal cost and selling price"""
        from app.utils.helpers import calculate_profit_margin
        result = calculate_profit_margin(100, 100)
        assert result == 0.0

    def test_profit_margin_decimal_values(self):
        """Test profit margin with decimal values"""
        from app.utils.helpers import calculate_profit_margin
        result = calculate_profit_margin(50.50, 75.75)
        expected = ((75.75 - 50.50) / 50.50) * 100
        assert abs(result - expected) < 0.01


# ============================================================================
# Test: helpers.py - generate_sale_number
# ============================================================================

class TestGenerateSaleNumber:
    """Tests for generate_sale_number function"""

    def test_generate_sale_number_format(self):
        """Test sale number format"""
        from app.utils.helpers import generate_sale_number
        result = generate_sale_number()
        # Format: SALE-YYYYMMDD-XXXX
        assert result.startswith('SALE-')
        parts = result.split('-')
        assert len(parts) == 3
        assert len(parts[1]) == 8  # YYYYMMDD
        assert len(parts[2]) == 4  # Random digits

    def test_generate_sale_number_uniqueness(self):
        """Test that generated sale numbers are likely unique"""
        from app.utils.helpers import generate_sale_number
        numbers = [generate_sale_number() for _ in range(100)]
        # While not guaranteed unique, duplicates should be rare
        unique_numbers = set(numbers)
        assert len(unique_numbers) >= 95  # Allow small chance of collision

    def test_generate_sale_number_date_part(self):
        """Test that sale number contains current date"""
        from app.utils.helpers import generate_sale_number
        result = generate_sale_number()
        date_part = datetime.now().strftime('%Y%m%d')
        assert date_part in result


# ============================================================================
# Test: helpers.py - generate_po_number
# ============================================================================

class TestGeneratePONumber:
    """Tests for generate_po_number function"""

    def test_generate_po_number_format(self):
        """Test PO number format"""
        from app.utils.helpers import generate_po_number
        result = generate_po_number()
        # Format: PO-YYYYMMDD-XXXX
        assert result.startswith('PO-')
        parts = result.split('-')
        assert len(parts) == 3
        assert len(parts[1]) == 8
        assert len(parts[2]) == 4


# ============================================================================
# Test: helpers.py - generate_product_code
# ============================================================================

class TestGenerateProductCode:
    """Tests for generate_product_code function"""

    def test_generate_product_code_format(self):
        """Test product code format"""
        from app.utils.helpers import generate_product_code
        result = generate_product_code()
        # Format: PROD-XXXXXXXX
        assert result.startswith('PROD-')
        parts = result.split('-')
        assert len(parts) == 2
        assert len(parts[1]) == 8

    def test_generate_product_code_alphanumeric(self):
        """Test product code contains only alphanumeric characters"""
        from app.utils.helpers import generate_product_code
        result = generate_product_code()
        random_part = result.split('-')[1]
        assert random_part.isalnum()
        assert random_part.isupper() or random_part.isdigit()


# ============================================================================
# Test: helpers.py - allowed_file
# ============================================================================

class TestAllowedFile:
    """Tests for allowed_file function (requires app context)"""

    def test_allowed_file_valid_extension(self, db_session):
        """Test allowed file with valid extension"""
        from app.utils.helpers import allowed_file
        assert allowed_file('image.png') is True
        assert allowed_file('photo.jpg') is True

    def test_allowed_file_invalid_extension(self, db_session):
        """Test allowed file with invalid extension"""
        from app.utils.helpers import allowed_file
        assert allowed_file('document.exe') is False
        assert allowed_file('script.bat') is False

    def test_allowed_file_no_extension(self, db_session):
        """Test allowed file without extension"""
        from app.utils.helpers import allowed_file
        assert allowed_file('noextension') is False

    def test_allowed_file_case_insensitive(self, db_session):
        """Test allowed file extension is case insensitive"""
        from app.utils.helpers import allowed_file
        assert allowed_file('IMAGE.PNG') is True
        assert allowed_file('Photo.JPG') is True

    def test_allowed_file_empty_string(self, db_session):
        """Test allowed file with empty string"""
        from app.utils.helpers import allowed_file
        assert allowed_file('') is False

    def test_allowed_file_multiple_dots(self, db_session):
        """Test allowed file with multiple dots in name"""
        from app.utils.helpers import allowed_file
        assert allowed_file('my.image.file.png') is True


# ============================================================================
# Test: helpers.py - get_date_range
# ============================================================================

class TestGetDateRange:
    """Tests for get_date_range function"""

    def test_get_date_range_today(self):
        """Test date range for today"""
        from app.utils.helpers import get_date_range
        start, end = get_date_range('today')
        today = datetime.now().date()
        assert start == today
        assert end == today

    def test_get_date_range_yesterday(self):
        """Test date range for yesterday"""
        from app.utils.helpers import get_date_range
        start, end = get_date_range('yesterday')
        yesterday = datetime.now().date() - timedelta(days=1)
        assert start == yesterday
        assert end == yesterday

    def test_get_date_range_this_week(self):
        """Test date range for this week"""
        from app.utils.helpers import get_date_range
        start, end = get_date_range('this_week')
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        assert start == week_start
        assert end == today

    def test_get_date_range_last_week(self):
        """Test date range for last week"""
        from app.utils.helpers import get_date_range
        start, end = get_date_range('last_week')
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday() + 7)
        week_end = week_start + timedelta(days=6)
        assert start == week_start
        assert end == week_end

    def test_get_date_range_this_month(self):
        """Test date range for this month"""
        from app.utils.helpers import get_date_range
        start, end = get_date_range('this_month')
        today = datetime.now().date()
        month_start = today.replace(day=1)
        assert start == month_start
        assert end == today

    def test_get_date_range_last_month(self):
        """Test date range for last month"""
        from app.utils.helpers import get_date_range
        start, end = get_date_range('last_month')
        today = datetime.now().date()
        last_month_end = today.replace(day=1) - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        assert start == last_month_start
        assert end == last_month_end

    def test_get_date_range_invalid_period(self):
        """Test date range with invalid period defaults to today"""
        from app.utils.helpers import get_date_range
        start, end = get_date_range('invalid_period')
        today = datetime.now().date()
        assert start == today
        assert end == today

    def test_get_date_range_empty_string(self):
        """Test date range with empty string defaults to today"""
        from app.utils.helpers import get_date_range
        start, end = get_date_range('')
        today = datetime.now().date()
        assert start == today
        assert end == today


# ============================================================================
# Test: helpers.py - sanitize_filename
# ============================================================================

class TestSanitizeFilename:
    """Tests for sanitize_filename function"""

    def test_sanitize_filename_normal(self):
        """Test sanitizing normal filename"""
        from app.utils.helpers import sanitize_filename
        result = sanitize_filename('my_file.txt')
        assert result == 'my_file.txt'

    def test_sanitize_filename_with_spaces(self):
        """Test sanitizing filename with spaces"""
        from app.utils.helpers import sanitize_filename
        result = sanitize_filename('my file.txt')
        assert result == 'my_file.txt'

    def test_sanitize_filename_path_traversal(self):
        """Test sanitizing filename with path traversal attempt"""
        from app.utils.helpers import sanitize_filename
        result = sanitize_filename('../../../etc/passwd')
        assert '..' not in result
        assert '/' not in result

    def test_sanitize_filename_special_characters(self):
        """Test sanitizing filename with special characters"""
        from app.utils.helpers import sanitize_filename
        result = sanitize_filename('file<>:"/\\|?*.txt')
        # secure_filename removes or replaces these
        assert '<' not in result
        assert '>' not in result


# ============================================================================
# Test: helpers.py - has_permission
# ============================================================================

class TestHasPermission:
    """Tests for has_permission function"""

    def test_has_permission_function_exists(self):
        """Test has_permission function exists and is callable"""
        from app.utils.helpers import has_permission
        assert callable(has_permission)


# ============================================================================
# Test: permissions.py - Permissions class constants
# ============================================================================

class TestPermissionsConstants:
    """Tests for Permissions class constants"""

    def test_pos_permissions_exist(self):
        """Test POS permission constants exist"""
        from app.utils.permissions import Permissions
        assert hasattr(Permissions, 'POS_VIEW')
        assert hasattr(Permissions, 'POS_CREATE_SALE')
        assert hasattr(Permissions, 'POS_VOID_SALE')
        assert hasattr(Permissions, 'POS_REFUND')

    def test_inventory_permissions_exist(self):
        """Test Inventory permission constants exist"""
        from app.utils.permissions import Permissions
        assert hasattr(Permissions, 'INVENTORY_VIEW')
        assert hasattr(Permissions, 'INVENTORY_CREATE')
        assert hasattr(Permissions, 'INVENTORY_EDIT')
        assert hasattr(Permissions, 'INVENTORY_DELETE')

    def test_permission_values_are_strings(self):
        """Test permission values are strings with correct format"""
        from app.utils.permissions import Permissions
        assert Permissions.POS_VIEW == 'pos.view'
        assert Permissions.INVENTORY_VIEW == 'inventory.view'
        assert Permissions.CUSTOMER_CREATE == 'customer.create'


# ============================================================================
# Test: permissions.py - get_all_permissions
# ============================================================================

class TestGetAllPermissions:
    """Tests for get_all_permissions function"""

    def test_get_all_permissions_returns_list(self):
        """Test get_all_permissions returns a list"""
        from app.utils.permissions import get_all_permissions
        result = get_all_permissions()
        assert isinstance(result, list)

    def test_get_all_permissions_tuple_format(self):
        """Test each permission is a tuple of (name, display_name, module)"""
        from app.utils.permissions import get_all_permissions
        result = get_all_permissions()
        for perm in result:
            assert isinstance(perm, tuple)
            assert len(perm) == 3
            assert isinstance(perm[0], str)  # name
            assert isinstance(perm[1], str)  # display_name
            assert isinstance(perm[2], str)  # module

    def test_get_all_permissions_not_empty(self):
        """Test get_all_permissions returns non-empty list"""
        from app.utils.permissions import get_all_permissions
        result = get_all_permissions()
        assert len(result) > 0

    def test_get_all_permissions_has_pos_permissions(self):
        """Test get_all_permissions includes POS permissions"""
        from app.utils.permissions import get_all_permissions
        result = get_all_permissions()
        perm_names = [p[0] for p in result]
        assert 'pos.view' in perm_names
        assert 'pos.create_sale' in perm_names


# ============================================================================
# Test: permissions.py - get_default_roles
# ============================================================================

class TestGetDefaultRoles:
    """Tests for get_default_roles function"""

    def test_get_default_roles_returns_dict(self):
        """Test get_default_roles returns a dictionary"""
        from app.utils.permissions import get_default_roles
        result = get_default_roles()
        assert isinstance(result, dict)

    def test_get_default_roles_has_admin(self):
        """Test get_default_roles includes admin role"""
        from app.utils.permissions import get_default_roles
        result = get_default_roles()
        assert 'admin' in result

    def test_get_default_roles_has_required_keys(self):
        """Test each role has required keys"""
        from app.utils.permissions import get_default_roles
        result = get_default_roles()
        required_keys = ['display_name', 'description', 'permissions', 'is_system']
        for role_name, role_info in result.items():
            for key in required_keys:
                assert key in role_info, f"Role {role_name} missing key {key}"

    def test_get_default_roles_admin_has_all_permissions(self):
        """Test admin role has all permissions"""
        from app.utils.permissions import get_default_roles, get_all_permissions
        roles = get_default_roles()
        all_perms = [p[0] for p in get_all_permissions()]
        admin_perms = roles['admin']['permissions']
        # Admin should have all permissions
        for perm in all_perms:
            assert perm in admin_perms, f"Admin missing permission: {perm}"

    def test_get_default_roles_cashier_has_limited_permissions(self):
        """Test cashier role has limited permissions"""
        from app.utils.permissions import get_default_roles
        roles = get_default_roles()
        cashier_perms = roles['cashier']['permissions']
        # Cashier should have POS access but not admin settings
        assert 'pos.view' in cashier_perms
        assert 'pos.create_sale' in cashier_perms
        assert 'settings.manage_users' not in cashier_perms
        assert 'settings.manage_roles' not in cashier_perms


# ============================================================================
# Test: permissions.py - permission_required decorator
# ============================================================================

class TestPermissionRequiredDecorator:
    """Tests for permission_required decorator"""

    def test_permission_required_decorator_exists(self):
        """Test permission_required decorator exists and is callable"""
        from app.utils.permissions import permission_required
        assert callable(permission_required)

        @permission_required('pos.view')
        def test_view():
            return 'success'

        assert callable(test_view)
        assert test_view.__name__ == 'test_view'


# ============================================================================
# Test: permissions.py - role_required decorator
# ============================================================================

class TestRoleRequiredDecorator:
    """Tests for role_required decorator"""

    def test_role_required_decorator_exists(self):
        """Test role_required decorator exists and is callable"""
        from app.utils.permissions import role_required
        assert callable(role_required)

        @role_required('admin')
        def admin_view():
            return 'admin_access'

        assert callable(admin_view)
        assert admin_view.__name__ == 'admin_view'


# ============================================================================
# Test: permissions.py - any_permission_required decorator
# ============================================================================

class TestAnyPermissionRequiredDecorator:
    """Tests for any_permission_required decorator"""

    def test_any_permission_decorator_exists(self):
        """Test that any_permission_required decorator exists and is callable"""
        from app.utils.permissions import any_permission_required
        assert callable(any_permission_required)

        # Create decorated function
        @any_permission_required('pos.view', 'pos.create_sale')
        def test_view():
            return 'success'

        assert callable(test_view)


# ============================================================================
# Test: permissions.py - all_permissions_required decorator
# ============================================================================

class TestAllPermissionsRequiredDecorator:
    """Tests for all_permissions_required decorator"""

    def test_all_permissions_decorator_exists(self):
        """Test that all_permissions_required decorator exists and is callable"""
        from app.utils.permissions import all_permissions_required
        assert callable(all_permissions_required)

        @all_permissions_required('inventory.view', 'inventory.edit')
        def edit_inventory():
            return 'success'

        assert callable(edit_inventory)


# ============================================================================
# Test: permissions.py - admin_required decorator
# ============================================================================

class TestAdminRequiredDecorator:
    """Tests for admin_required decorator"""

    def test_admin_required_decorator_exists(self):
        """Test that admin_required decorator exists and is callable"""
        from app.utils.permissions import admin_required
        assert callable(admin_required)

        @admin_required
        def admin_settings():
            return 'admin_access'

        assert callable(admin_settings)


# ============================================================================
# Test: feature_flags.py - Features class
# ============================================================================

class TestFeaturesClass:
    """Tests for Features class constants"""

    def test_feature_constants_exist(self):
        """Test feature flag constants exist"""
        from app.utils.feature_flags import Features
        assert hasattr(Features, 'SMS_NOTIFICATIONS')
        assert hasattr(Features, 'WHATSAPP_NOTIFICATIONS')
        assert hasattr(Features, 'EMAIL_NOTIFICATIONS')
        assert hasattr(Features, 'PROMOTIONS')

    def test_feature_constants_are_strings(self):
        """Test feature flag constants are strings"""
        from app.utils.feature_flags import Features
        assert isinstance(Features.SMS_NOTIFICATIONS, str)
        assert isinstance(Features.EMAIL_NOTIFICATIONS, str)


# ============================================================================
# Test: feature_flags.py - is_feature_enabled
# ============================================================================

class TestIsFeatureEnabled:
    """Tests for is_feature_enabled function"""

    @patch('app.models_extended.FeatureFlag')
    def test_feature_enabled_no_config_required(self, mock_model):
        """Test feature enabled without config requirement"""
        mock_flag = Mock()
        mock_flag.is_enabled = True
        mock_flag.requires_config = False
        mock_model.query.filter_by.return_value.first.return_value = mock_flag

        from app.utils.feature_flags import is_feature_enabled
        assert is_feature_enabled('test_feature') is True

    @patch('app.models_extended.FeatureFlag')
    def test_feature_enabled_config_required_and_configured(self, mock_model):
        """Test feature enabled with config requirement when configured"""
        mock_flag = Mock()
        mock_flag.is_enabled = True
        mock_flag.requires_config = True
        mock_flag.is_configured = True
        mock_model.query.filter_by.return_value.first.return_value = mock_flag

        from app.utils.feature_flags import is_feature_enabled
        assert is_feature_enabled('test_feature') is True

    @patch('app.models_extended.FeatureFlag')
    def test_feature_enabled_config_required_not_configured(self, mock_model):
        """Test feature enabled with config requirement when not configured"""
        mock_flag = Mock()
        mock_flag.is_enabled = True
        mock_flag.requires_config = True
        mock_flag.is_configured = False
        mock_model.query.filter_by.return_value.first.return_value = mock_flag

        from app.utils.feature_flags import is_feature_enabled
        assert is_feature_enabled('test_feature') is False

    @patch('app.models_extended.FeatureFlag')
    def test_feature_disabled(self, mock_model):
        """Test feature that is disabled"""
        mock_flag = Mock()
        mock_flag.is_enabled = False
        mock_flag.requires_config = False
        mock_model.query.filter_by.return_value.first.return_value = mock_flag

        from app.utils.feature_flags import is_feature_enabled
        assert is_feature_enabled('test_feature') is False

    @patch('app.models_extended.FeatureFlag')
    def test_feature_not_found(self, mock_model):
        """Test feature that doesn't exist"""
        mock_model.query.filter_by.return_value.first.return_value = None

        from app.utils.feature_flags import is_feature_enabled
        assert is_feature_enabled('nonexistent_feature') is False


# ============================================================================
# Test: feature_flags.py - get_feature_config
# ============================================================================

class TestGetFeatureConfig:
    """Tests for get_feature_config function"""

    @patch('app.models_extended.FeatureFlag')
    def test_get_full_config(self, mock_model):
        """Test getting full configuration"""
        mock_flag = Mock()
        mock_flag.config = {'key1': 'value1', 'key2': 'value2'}
        mock_model.query.filter_by.return_value.first.return_value = mock_flag

        from app.utils.feature_flags import get_feature_config
        result = get_feature_config('test_feature')
        assert result == {'key1': 'value1', 'key2': 'value2'}

    @patch('app.models_extended.FeatureFlag')
    def test_get_specific_config_key(self, mock_model):
        """Test getting specific configuration key"""
        mock_flag = Mock()
        mock_flag.config = {'key1': 'value1', 'key2': 'value2'}
        mock_model.query.filter_by.return_value.first.return_value = mock_flag

        from app.utils.feature_flags import get_feature_config
        result = get_feature_config('test_feature', key='key1')
        assert result == 'value1'

    @patch('app.models_extended.FeatureFlag')
    def test_get_missing_config_key_with_default(self, mock_model):
        """Test getting missing configuration key with default"""
        mock_flag = Mock()
        mock_flag.config = {'key1': 'value1'}
        mock_model.query.filter_by.return_value.first.return_value = mock_flag

        from app.utils.feature_flags import get_feature_config
        result = get_feature_config('test_feature', key='missing_key', default='default_value')
        assert result == 'default_value'

    @patch('app.models_extended.FeatureFlag')
    def test_get_config_feature_not_found(self, mock_model):
        """Test getting configuration for non-existent feature"""
        mock_model.query.filter_by.return_value.first.return_value = None

        from app.utils.feature_flags import get_feature_config
        result = get_feature_config('nonexistent', default='default')
        assert result == 'default'

    @patch('app.models_extended.FeatureFlag')
    def test_get_config_null_config(self, mock_model):
        """Test getting configuration when config is null"""
        mock_flag = Mock()
        mock_flag.config = None
        mock_model.query.filter_by.return_value.first.return_value = mock_flag

        from app.utils.feature_flags import get_feature_config
        result = get_feature_config('test_feature', default='fallback')
        assert result == 'fallback'


# ============================================================================
# Test: feature_flags.py - feature_required decorator
# ============================================================================

class TestFeatureRequiredDecorator:
    """Tests for feature_required decorator"""

    def test_feature_required_decorator_exists(self):
        """Test that feature_required decorator exists and is callable"""
        from app.utils.feature_flags import feature_required
        assert callable(feature_required)

        @feature_required('test_feature')
        def test_view():
            return 'feature_active'

        assert callable(test_view)


# ============================================================================
# Test: feature_flags.py - feature_or_404
# ============================================================================

class TestFeatureOr404:
    """Tests for feature_or_404 function"""

    @patch('app.utils.feature_flags.is_feature_enabled')
    def test_feature_or_404_enabled(self, mock_is_enabled):
        """Test feature_or_404 when feature is enabled (no abort)"""
        mock_is_enabled.return_value = True

        from app.utils.feature_flags import feature_or_404
        # Should not raise
        feature_or_404('enabled_feature')

    @patch('app.utils.feature_flags.is_feature_enabled')
    @patch('app.utils.feature_flags.abort')
    def test_feature_or_404_disabled(self, mock_abort, mock_is_enabled):
        """Test feature_or_404 when feature is disabled"""
        mock_is_enabled.return_value = False

        from app.utils.feature_flags import feature_or_404
        feature_or_404('disabled_feature')
        mock_abort.assert_called_with(404)


# ============================================================================
# Test: feature_flags.py - inject_feature_flags
# ============================================================================

class TestInjectFeatureFlags:
    """Tests for inject_feature_flags function"""

    @patch('app.utils.feature_flags.get_enabled_features')
    @patch('app.utils.feature_flags.is_feature_enabled')
    def test_inject_feature_flags_returns_dict(self, mock_is_enabled, mock_get_enabled):
        """Test inject_feature_flags returns correct dictionary"""
        mock_get_enabled.return_value = ['feature1', 'feature2']

        from app.utils.feature_flags import inject_feature_flags
        result = inject_feature_flags()

        assert 'is_feature_enabled' in result
        assert 'enabled_features' in result
        assert result['enabled_features'] == ['feature1', 'feature2']


# ============================================================================
# Test: location_context.py - get_current_location
# ============================================================================

class TestGetCurrentLocation:
    """Tests for get_current_location function"""

    def test_get_current_location_function_exists(self):
        """Test get_current_location function exists and is callable"""
        from app.utils.location_context import get_current_location
        assert callable(get_current_location)


# ============================================================================
# Test: location_context.py - get_user_locations
# ============================================================================

class TestGetUserLocations:
    """Tests for get_user_locations function"""

    def test_get_user_locations_function_exists(self):
        """Test get_user_locations function exists and is callable"""
        from app.utils.location_context import get_user_locations
        assert callable(get_user_locations)


# ============================================================================
# Test: location_context.py - can_access_location
# ============================================================================

class TestCanAccessLocation:
    """Tests for can_access_location function"""

    def test_can_access_location_function_exists(self):
        """Test can_access_location function exists and is callable"""
        from app.utils.location_context import can_access_location
        assert callable(can_access_location)


# ============================================================================
# Test: location_context.py - location_required decorator
# ============================================================================

class TestLocationRequiredDecorator:
    """Tests for location_required decorator"""

    def test_location_required_decorator_exists(self):
        """Test that location_required decorator exists and is callable"""
        from app.utils.location_context import location_required
        assert callable(location_required)

        @location_required
        def test_view():
            return 'success'

        assert callable(test_view)


# ============================================================================
# Test: location_context.py - warehouse_required decorator
# ============================================================================

class TestWarehouseRequiredDecorator:
    """Tests for warehouse_required decorator"""

    def test_warehouse_required_decorator_exists(self):
        """Test that warehouse_required decorator exists and is callable"""
        from app.utils.location_context import warehouse_required
        assert callable(warehouse_required)

        @warehouse_required
        def warehouse_view():
            return 'warehouse_success'

        assert callable(warehouse_view)


# ============================================================================
# Test: location_context.py - kiosk_required decorator
# ============================================================================

class TestKioskRequiredDecorator:
    """Tests for kiosk_required decorator"""

    def test_kiosk_required_decorator_exists(self):
        """Test that kiosk_required decorator exists and is callable"""
        from app.utils.location_context import kiosk_required
        assert callable(kiosk_required)

        @kiosk_required
        def kiosk_view():
            return 'kiosk_success'

        assert callable(kiosk_view)


# ============================================================================
# Test: location_context.py - generate_transfer_number
# ============================================================================

class TestGenerateTransferNumber:
    """Tests for generate_transfer_number function (requires db session)"""

    def test_generate_transfer_number_format(self, db_session):
        """Test generating transfer number has correct format"""
        from app.utils.location_context import generate_transfer_number
        result = generate_transfer_number()

        today = datetime.utcnow().strftime('%Y%m%d')
        assert result.startswith(f"TRF-{today}-")
        assert len(result) == len(f"TRF-{today}-001")


# ============================================================================
# Test: birthday_gifts.py - is_customer_eligible_for_gift
# ============================================================================

class TestIsCustomerEligibleForGift:
    """Tests for is_customer_eligible_for_gift function"""

    def test_eligible_customer(self):
        """Test customer who meets all criteria"""
        from app.utils.birthday_gifts import is_customer_eligible_for_gift

        stats = {
            'perfumes_per_month': 3.0,
            'total_orders': 5,
            'is_regular_customer': True
        }

        assert is_customer_eligible_for_gift(stats) is True

    def test_ineligible_low_perfume_rate(self):
        """Test customer with low perfume purchase rate"""
        from app.utils.birthday_gifts import is_customer_eligible_for_gift

        stats = {
            'perfumes_per_month': 1.0,  # Below 2.0 threshold
            'total_orders': 5,
            'is_regular_customer': True
        }

        assert is_customer_eligible_for_gift(stats) is False

    def test_ineligible_no_orders(self):
        """Test customer with no orders"""
        from app.utils.birthday_gifts import is_customer_eligible_for_gift

        stats = {
            'perfumes_per_month': 3.0,
            'total_orders': 0,
            'is_regular_customer': True
        }

        assert is_customer_eligible_for_gift(stats) is False

    def test_ineligible_not_regular(self):
        """Test customer who is not a regular customer"""
        from app.utils.birthday_gifts import is_customer_eligible_for_gift

        stats = {
            'perfumes_per_month': 3.0,
            'total_orders': 5,
            'is_regular_customer': False
        }

        assert is_customer_eligible_for_gift(stats) is False

    def test_ineligible_none_stats(self):
        """Test with None stats"""
        from app.utils.birthday_gifts import is_customer_eligible_for_gift
        assert is_customer_eligible_for_gift(None) is False


# ============================================================================
# Test: birthday_gifts.py - calculate_eligibility_score
# ============================================================================

class TestCalculateEligibilityScore:
    """Tests for calculate_eligibility_score function"""

    def test_calculate_score_basic(self):
        """Test basic score calculation"""
        from app.utils.birthday_gifts import calculate_eligibility_score

        stats = {
            'total_purchases': 10000,  # 100 points
            'high_value_purchases': 2,  # 100 points
            'recent_6month_purchases': 5000,  # 500 points
            'perfumes_per_month': 3,  # 30 points
            'is_regular_customer': True  # 100 points
        }

        score = calculate_eligibility_score(stats)
        expected = (10000/100) + (2*50) + (5000/10) + (3*10) + 100
        assert score == expected

    def test_calculate_score_none_stats(self):
        """Test score calculation with None stats"""
        from app.utils.birthday_gifts import calculate_eligibility_score
        assert calculate_eligibility_score(None) == 0

    def test_calculate_score_not_regular(self):
        """Test score without regular customer bonus"""
        from app.utils.birthday_gifts import calculate_eligibility_score

        stats = {
            'total_purchases': 1000,
            'high_value_purchases': 0,
            'recent_6month_purchases': 0,
            'perfumes_per_month': 0,
            'is_regular_customer': False
        }

        score = calculate_eligibility_score(stats)
        assert score == 10  # Only total_purchases/100


# ============================================================================
# Test: birthday_gifts.py - get_premium_birthday_gift
# ============================================================================

class TestGetPremiumBirthdayGift:
    """Tests for get_premium_birthday_gift function"""

    def test_vip_elite_tier(self):
        """Test VIP Elite tier gift"""
        from app.utils.birthday_gifts import get_premium_birthday_gift

        customer = Mock()
        customer.name = 'Test Customer'

        # Score >= 1000 for VIP Elite
        stats = {
            'total_purchases': 100000,  # 1000 points just from this
            'high_value_purchases': 0,
            'recent_6month_purchases': 0,
            'perfumes_per_month': 0,
            'is_regular_customer': False
        }

        gift = get_premium_birthday_gift(customer, stats)
        assert gift['tier'] == 'VIP Elite'
        assert gift['discount_percentage'] == 30
        assert gift['voucher_amount'] == 1000
        assert gift['bonus_points'] == 1000

    def test_vip_gold_tier(self):
        """Test VIP Gold tier gift"""
        from app.utils.birthday_gifts import get_premium_birthday_gift

        customer = Mock()
        customer.name = 'Test Customer'

        # Score 500-999 for VIP Gold
        stats = {
            'total_purchases': 50000,  # 500 points
            'high_value_purchases': 0,
            'recent_6month_purchases': 0,
            'perfumes_per_month': 0,
            'is_regular_customer': False
        }

        gift = get_premium_birthday_gift(customer, stats)
        assert gift['tier'] == 'VIP Gold'
        assert gift['discount_percentage'] == 25
        assert gift['voucher_amount'] == 500

    def test_vip_silver_tier(self):
        """Test VIP Silver tier gift"""
        from app.utils.birthday_gifts import get_premium_birthday_gift

        customer = Mock()
        customer.name = 'Test Customer'

        # Score 250-499 for VIP Silver
        stats = {
            'total_purchases': 25000,  # 250 points
            'high_value_purchases': 0,
            'recent_6month_purchases': 0,
            'perfumes_per_month': 0,
            'is_regular_customer': False
        }

        gift = get_premium_birthday_gift(customer, stats)
        assert gift['tier'] == 'VIP Silver'
        assert gift['discount_percentage'] == 20
        assert gift['voucher_amount'] == 0

    def test_loyal_customer_tier(self):
        """Test Loyal Customer tier gift"""
        from app.utils.birthday_gifts import get_premium_birthday_gift

        customer = Mock()
        customer.name = 'Test Customer'

        # Score < 250 for Loyal Customer
        stats = {
            'total_purchases': 5000,  # 50 points
            'high_value_purchases': 0,
            'recent_6month_purchases': 0,
            'perfumes_per_month': 0,
            'is_regular_customer': False
        }

        gift = get_premium_birthday_gift(customer, stats)
        assert gift['tier'] == 'Loyal Customer'
        assert gift['discount_percentage'] == 15


# ============================================================================
# Test: birthday_gifts.py - create_notification_message
# ============================================================================

class TestCreateNotificationMessage:
    """Tests for create_notification_message function"""

    def test_create_notification_message_basic(self):
        """Test basic notification message creation"""
        from app.utils.birthday_gifts import create_notification_message

        customer = Mock()
        customer.name = 'John Doe'
        customer.phone = '+92-300-1234567'

        gift = {
            'tier': 'VIP Gold',
            'discount_percentage': 25,
            'voucher_amount': 500,
            'bonus_points': 500,
            'special_gift': 'Free perfume sample',
            'priority': 2
        }

        message = create_notification_message(customer, gift)

        assert 'John Doe' in message
        assert '+92-300-1234567' in message
        assert 'VIP Gold' in message
        assert '25%' in message
        assert 'Rs. 500' in message
        assert '500 Bonus' in message
        assert 'Free perfume sample' in message

    def test_create_notification_message_no_voucher(self):
        """Test notification message without voucher"""
        from app.utils.birthday_gifts import create_notification_message

        customer = Mock()
        customer.name = 'Jane Doe'
        customer.phone = '+92-300-9876543'

        gift = {
            'tier': 'VIP Silver',
            'discount_percentage': 20,
            'voucher_amount': 0,
            'bonus_points': 300,
            'special_gift': None,
            'priority': 3
        }

        message = create_notification_message(customer, gift)

        assert 'Jane Doe' in message
        assert 'VIP Silver' in message
        assert '20%' in message
        assert 'Voucher' not in message or 'Rs. 0' not in message


# ============================================================================
# Test: inventory_forecast.py - calculate_safety_stock
# ============================================================================

class TestCalculateSafetyStock:
    """Tests for calculate_safety_stock function"""

    @patch('app.utils.inventory_forecast.get_product_sales_stats')
    def test_safety_stock_with_sales(self, mock_stats):
        """Test safety stock calculation with sales history"""
        mock_stats.return_value = {
            'avg_daily_sales': 10,
            'max_daily_sales': 20
        }

        from app.utils.inventory_forecast import calculate_safety_stock
        result = calculate_safety_stock(1, 1, lead_time_days=3)

        # Safety Stock = (max * max_lead) - (avg * avg_lead)
        # = (20 * 4.5) - (10 * 3) = 90 - 30 = 60
        expected = int((20 * 4.5) - (10 * 3))
        assert result == expected

    @patch('app.utils.inventory_forecast.get_product_sales_stats')
    def test_safety_stock_no_sales(self, mock_stats):
        """Test safety stock calculation with no sales"""
        mock_stats.return_value = {
            'avg_daily_sales': 0,
            'max_daily_sales': 0
        }

        from app.utils.inventory_forecast import calculate_safety_stock
        result = calculate_safety_stock(1, 1, lead_time_days=3)

        # Default minimum when no sales
        assert result == 5

    @patch('app.utils.inventory_forecast.get_product_sales_stats')
    def test_safety_stock_minimum(self, mock_stats):
        """Test safety stock calculation returns minimum"""
        mock_stats.return_value = {
            'avg_daily_sales': 1,
            'max_daily_sales': 1
        }

        from app.utils.inventory_forecast import calculate_safety_stock
        result = calculate_safety_stock(1, 1, lead_time_days=3)

        # Should return at least 3 (minimum)
        assert result >= 3


# ============================================================================
# Test: inventory_forecast.py - calculate_reorder_point
# ============================================================================

class TestCalculateReorderPoint:
    """Tests for calculate_reorder_point function"""

    @patch('app.utils.inventory_forecast.calculate_safety_stock')
    @patch('app.utils.inventory_forecast.get_product_sales_stats')
    def test_reorder_point_calculation(self, mock_stats, mock_safety):
        """Test reorder point calculation"""
        mock_stats.return_value = {'avg_daily_sales': 10}
        mock_safety.return_value = 20

        from app.utils.inventory_forecast import calculate_reorder_point
        result = calculate_reorder_point(1, 1, lead_time_days=3)

        # Reorder Point = (avg * lead_time) + safety_stock
        # = (10 * 3) + 20 = 50
        assert result == 50

    @patch('app.utils.inventory_forecast.calculate_safety_stock')
    @patch('app.utils.inventory_forecast.get_product_sales_stats')
    def test_reorder_point_minimum(self, mock_stats, mock_safety):
        """Test reorder point returns at least safety stock"""
        mock_stats.return_value = {'avg_daily_sales': 0}
        mock_safety.return_value = 15

        from app.utils.inventory_forecast import calculate_reorder_point
        result = calculate_reorder_point(1, 1, lead_time_days=3)

        assert result >= 15


# ============================================================================
# Test: inventory_forecast.py - calculate_days_of_stock
# ============================================================================

class TestCalculateDaysOfStock:
    """Tests for calculate_days_of_stock function"""

    @patch('app.utils.inventory_forecast.LocationStock')
    @patch('app.utils.inventory_forecast.get_product_sales_stats')
    def test_days_of_stock_calculation(self, mock_stats, mock_stock_model):
        """Test days of stock calculation"""
        mock_stats.return_value = {'avg_daily_sales': 5}
        mock_stock = Mock()
        mock_stock.quantity = 50
        mock_stock_model.query.filter_by.return_value.first.return_value = mock_stock

        from app.utils.inventory_forecast import calculate_days_of_stock
        result = calculate_days_of_stock(1, 1)

        # 50 / 5 = 10 days
        assert result == 10.0

    @patch('app.utils.inventory_forecast.get_product_sales_stats')
    def test_days_of_stock_no_sales(self, mock_stats):
        """Test days of stock with no sales history"""
        mock_stats.return_value = {'avg_daily_sales': 0}

        from app.utils.inventory_forecast import calculate_days_of_stock
        result = calculate_days_of_stock(1, 1)

        assert result is None

    @patch('app.utils.inventory_forecast.LocationStock')
    @patch('app.utils.inventory_forecast.get_product_sales_stats')
    def test_days_of_stock_zero_stock(self, mock_stats, mock_stock_model):
        """Test days of stock with zero current stock"""
        mock_stats.return_value = {'avg_daily_sales': 5}
        mock_stock = Mock()
        mock_stock.quantity = 0
        mock_stock_model.query.filter_by.return_value.first.return_value = mock_stock

        from app.utils.inventory_forecast import calculate_days_of_stock
        result = calculate_days_of_stock(1, 1)

        assert result == 0


# ============================================================================
# Test: db_utils.py - get_or_create
# ============================================================================

class TestGetOrCreate:
    """Tests for get_or_create function"""

    @patch('app.utils.db_utils.db')
    def test_get_or_create_existing(self, mock_db):
        """Test get_or_create returns existing record"""
        mock_model = Mock()
        mock_instance = Mock()
        mock_model.query.filter_by.return_value.first.return_value = mock_instance

        from app.utils.db_utils import get_or_create
        instance, created = get_or_create(mock_model, name='test')

        assert instance == mock_instance
        assert created is False
        mock_db.session.add.assert_not_called()

    @patch('app.utils.db_utils.db')
    def test_get_or_create_new(self, mock_db):
        """Test get_or_create creates new record"""
        mock_model = Mock()
        mock_model.query.filter_by.return_value.first.return_value = None

        from app.utils.db_utils import get_or_create
        instance, created = get_or_create(mock_model, name='test')

        assert created is True
        mock_db.session.add.assert_called_once()
        mock_db.session.commit.assert_called_once()


# ============================================================================
# Test: db_utils.py - bulk_insert
# ============================================================================

class TestBulkInsert:
    """Tests for bulk_insert function"""

    @patch('app.utils.db_utils.db')
    def test_bulk_insert_success(self, mock_db):
        """Test successful bulk insert"""
        mock_model = Mock()
        data_list = [{'name': 'item1'}, {'name': 'item2'}]

        from app.utils.db_utils import bulk_insert
        result = bulk_insert(mock_model, data_list)

        assert result == 2
        mock_db.session.bulk_save_objects.assert_called_once()
        mock_db.session.commit.assert_called_once()

    @patch('app.utils.db_utils.db')
    def test_bulk_insert_empty_list(self, mock_db):
        """Test bulk insert with empty list"""
        mock_model = Mock()

        from app.utils.db_utils import bulk_insert
        result = bulk_insert(mock_model, [])

        assert result == 0

    @patch('app.utils.db_utils.db')
    def test_bulk_insert_error(self, mock_db):
        """Test bulk insert with error"""
        mock_model = Mock()
        mock_model.side_effect = Exception("DB Error")
        mock_db.session.bulk_save_objects.side_effect = Exception("DB Error")

        from app.utils.db_utils import bulk_insert
        result = bulk_insert(mock_model, [{'name': 'item1'}])

        assert result == 0
        mock_db.session.rollback.assert_called_once()


# ============================================================================
# Test: db_utils.py - safe_commit
# ============================================================================

class TestSafeCommit:
    """Tests for safe_commit function"""

    @patch('app.utils.db_utils.db')
    def test_safe_commit_success(self, mock_db):
        """Test successful safe commit"""
        from app.utils.db_utils import safe_commit
        result = safe_commit()

        assert result is True
        mock_db.session.commit.assert_called_once()

    @patch('app.utils.db_utils.db')
    def test_safe_commit_failure(self, mock_db):
        """Test safe commit with error"""
        mock_db.session.commit.side_effect = Exception("DB Error")

        from app.utils.db_utils import safe_commit
        result = safe_commit()

        assert result is False
        mock_db.session.rollback.assert_called_once()


# ============================================================================
# Test: db_utils.py - paginate_query
# ============================================================================

class TestPaginateQuery:
    """Tests for paginate_query function"""

    def test_paginate_query_defaults(self):
        """Test paginate_query with default values"""
        mock_query = Mock()
        mock_pagination = Mock()
        mock_query.paginate.return_value = mock_pagination

        from app.utils.db_utils import paginate_query
        result = paginate_query(mock_query)

        mock_query.paginate.assert_called_once_with(page=1, per_page=50, error_out=False)
        assert result == mock_pagination

    def test_paginate_query_custom_values(self):
        """Test paginate_query with custom values"""
        mock_query = Mock()
        mock_pagination = Mock()
        mock_query.paginate.return_value = mock_pagination

        from app.utils.db_utils import paginate_query
        result = paginate_query(mock_query, page=3, per_page=20)

        mock_query.paginate.assert_called_once_with(page=3, per_page=20, error_out=False)


# ============================================================================
# Test: Edge Cases and Boundary Conditions
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions"""

    def test_format_currency_very_large_number(self):
        """Test formatting extremely large currency amount"""
        from app.utils.helpers import format_currency
        result = format_currency(999999999999.99)
        assert 'Rs.' in result
        assert '999,999,999,999.99' in result

    def test_format_currency_very_small_decimal(self):
        """Test formatting small decimal amount"""
        from app.utils.helpers import format_currency
        result = format_currency(0.01)
        assert result == "Rs. 0.01"

    def test_profit_margin_large_values(self):
        """Test profit margin with large values"""
        from app.utils.helpers import calculate_profit_margin
        result = calculate_profit_margin(1000000, 2000000)
        assert result == 100.0

    def test_profit_margin_small_values(self):
        """Test profit margin with very small values"""
        from app.utils.helpers import calculate_profit_margin
        result = calculate_profit_margin(0.01, 0.02)
        assert abs(result - 100.0) < 0.01

    def test_allowed_file_edge_cases(self, db_session):
        """Test allowed_file with various edge cases"""
        from app.utils.helpers import allowed_file

        # Double extension
        assert allowed_file('file.tar.png') is True

        # Hidden file
        assert allowed_file('.hidden.png') is True

        # Just extension
        assert allowed_file('.png') is True

    def test_date_range_boundary_dates(self):
        """Test date range at month/year boundaries"""
        from app.utils.helpers import get_date_range

        # These should not raise exceptions
        start, end = get_date_range('this_month')
        assert start is not None
        assert end is not None

        start, end = get_date_range('last_month')
        assert start is not None
        assert end is not None


# ============================================================================
# Test: Exception Handling
# ============================================================================

class TestExceptionHandling:
    """Tests for exception handling"""

    @patch('app.utils.db_utils.db')
    def test_init_database_exception(self, mock_db):
        """Test init_database handles exceptions"""
        mock_db.create_all.side_effect = Exception("DB Error")

        from app.utils.db_utils import init_database
        result = init_database()

        assert result is False

    @patch('app.utils.db_utils.db')
    def test_reset_database_exception(self, mock_db):
        """Test reset_database handles exceptions"""
        mock_db.drop_all.side_effect = Exception("DB Error")

        from app.utils.db_utils import reset_database
        result = reset_database()

        assert result is False

    @patch('app.utils.db_utils.db')
    def test_execute_raw_sql_exception(self, mock_db):
        """Test execute_raw_sql handles exceptions"""
        mock_db.session.execute.side_effect = Exception("SQL Error")

        from app.utils.db_utils import execute_raw_sql
        result = execute_raw_sql("SELECT * FROM table")

        assert result is None
        mock_db.session.rollback.assert_called_once()


# ============================================================================
# Test: Decorator Function Wrapping
# ============================================================================

class TestDecoratorFunctionWrapping:
    """Tests to ensure decorators preserve function metadata"""

    def test_permission_required_preserves_name(self):
        """Test that permission_required preserves function name"""
        from app.utils.permissions import permission_required

        @permission_required('test.permission')
        def my_test_function():
            """Test docstring"""
            return 'result'

        assert my_test_function.__name__ == 'my_test_function'
        assert 'Test docstring' in (my_test_function.__doc__ or '')

    def test_feature_required_preserves_name(self):
        """Test that feature_required preserves function name"""
        from app.utils.feature_flags import feature_required

        @feature_required('test_feature')
        def my_feature_function():
            """Feature docstring"""
            return 'result'

        assert my_feature_function.__name__ == 'my_feature_function'

    def test_location_required_preserves_name(self):
        """Test that location_required preserves function name"""
        from app.utils.location_context import location_required

        @location_required
        def my_location_function():
            """Location docstring"""
            return 'result'

        assert my_location_function.__name__ == 'my_location_function'


# ============================================================================
# Run tests
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
