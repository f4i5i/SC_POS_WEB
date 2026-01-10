"""
Authentication Routes
Handles user login, logout, and authentication
"""

import re
from urllib.parse import urlparse, urljoin
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, current_user, login_required
from flask_wtf.csrf import generate_csrf
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from app.models import db, User, ActivityLog

bp = Blueprint('auth', __name__)

# Try to import rate limiter
try:
    from app import limiter, LIMITER_AVAILABLE
except ImportError:
    limiter = None
    LIMITER_AVAILABLE = False


def is_safe_url(target):
    """
    Validate redirect URL to prevent open redirect attacks.
    Only allows redirects to same host.
    """
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


def validate_password_strength(password):
    """
    Validate password meets security requirements:
    - At least 8 characters
    - Contains uppercase and lowercase letters
    - Contains at least one digit
    - Contains at least one special character
    Returns (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one digit"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character (!@#$%^&*(),.?\":{}|<>)"
    return True, None


def check_account_lockout(user):
    """
    Check if account is locked due to too many failed attempts.
    Returns (is_locked, remaining_minutes)
    """
    if not user:
        return False, 0

    max_attempts = current_app.config.get('LOGIN_ATTEMPTS_LIMIT', 5)
    lockout_minutes = current_app.config.get('LOGIN_TIMEOUT_MINUTES', 15)

    # Check if user has failed_login_attempts and locked_until attributes
    failed_attempts = getattr(user, 'failed_login_attempts', 0) or 0
    locked_until = getattr(user, 'locked_until', None)

    if locked_until and locked_until > datetime.utcnow():
        remaining = (locked_until - datetime.utcnow()).total_seconds() / 60
        return True, int(remaining) + 1

    # Reset lock if lockout period has passed
    if locked_until and locked_until <= datetime.utcnow():
        user.failed_login_attempts = 0
        user.locked_until = None
        db.session.commit()

    return False, 0


def record_failed_login(user):
    """Record a failed login attempt and lock account if threshold exceeded."""
    if not user:
        return

    max_attempts = current_app.config.get('LOGIN_ATTEMPTS_LIMIT', 5)
    lockout_minutes = current_app.config.get('LOGIN_TIMEOUT_MINUTES', 15)

    # Ensure user has the required attributes
    if not hasattr(user, 'failed_login_attempts'):
        return

    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1

    if user.failed_login_attempts >= max_attempts:
        user.locked_until = datetime.utcnow() + timedelta(minutes=lockout_minutes)

    db.session.commit()


def reset_failed_login_attempts(user):
    """Reset failed login attempts after successful login."""
    if user and hasattr(user, 'failed_login_attempts'):
        user.failed_login_attempts = 0
        user.locked_until = None
        db.session.commit()


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login with security protections"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    # Ensure session is established for CSRF token persistence
    # This fixes "CSRF session token is missing" errors by explicitly
    # generating and storing the CSRF token in the session before rendering
    if request.method == 'GET':
        generate_csrf()  # Forces CSRF token creation and session save

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)

        # Generic error message to prevent user enumeration
        generic_error = 'Invalid username or password'

        # Input validation
        if not username or not password:
            flash(generic_error, 'danger')
            return redirect(url_for('auth.login'))

        user = User.query.filter_by(username=username).first()

        # Check account lockout (only if user exists)
        if user:
            is_locked, remaining_minutes = check_account_lockout(user)
            if is_locked:
                flash(f'Account is temporarily locked. Please try again in {remaining_minutes} minutes.', 'danger')
                log_activity(None, 'locked_login_attempt', 'user', user.id,
                           f'Login attempt on locked account: {username}')
                return redirect(url_for('auth.login'))

        # Validate credentials - use generic error to prevent enumeration
        if user is None or not user.check_password(password):
            flash(generic_error, 'danger')
            log_activity(None, 'failed_login', 'user', None,
                        f'Failed login attempt for username: {username}')
            # Record failed attempt for existing users
            if user:
                record_failed_login(user)
            return redirect(url_for('auth.login'))

        # Check if account is active
        if not user.is_active:
            flash('Your account has been deactivated. Please contact administrator.', 'warning')
            return redirect(url_for('auth.login'))

        # Login successful - reset failed attempts
        reset_failed_login_attempts(user)
        login_user(user, remember=remember)
        user.last_login = datetime.utcnow()
        db.session.commit()

        log_activity(user.id, 'login', 'user', user.id, 'User logged in')

        # Check if user must change password
        if user.force_password_change:
            flash('You must change your password before continuing.', 'warning')
            return redirect(url_for('auth.change_password'))

        # Set current location in session
        if user.location_id:
            session['current_location_id'] = user.location_id
            location_name = user.location.name if user.location else 'Unknown'
            flash(f'Welcome! You are logged in at: {location_name}', 'success')
        elif user.is_global_admin:
            flash('Welcome! You have Global Admin access to all locations.', 'success')
        else:
            flash('Welcome! No location assigned - please contact admin.', 'warning')

        # Validate and redirect to next page (prevent open redirect)
        next_page = request.args.get('next')
        if next_page and is_safe_url(next_page):
            return redirect(next_page)

        # Role-based redirect (fallback)
        if user.role == 'cashier':
            return redirect(url_for('pos.index'))
        elif user.role == 'warehouse_manager':
            return redirect(url_for('warehouse.index'))
        elif user.role in ['manager', 'kiosk_manager']:
            # Store managers go to their store dashboard (sales list)
            return redirect(url_for('pos.sales_list'))
        else:
            return redirect(url_for('index'))

    return render_template('auth/login.html')


@bp.route('/logout')
@login_required
def logout():
    """User logout"""
    log_activity(current_user.id, 'logout', 'user', current_user.id, 'User logged out')
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


@bp.route('/keepalive', methods=['POST'])
@login_required
def keepalive():
    """Extend session - called by session timeout warning"""
    from flask import jsonify
    session.modified = True
    return jsonify({'status': 'ok', 'message': 'Session extended'})


@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change user password with security validation"""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validate current password
        if not current_user.check_password(current_password):
            flash('Current password is incorrect', 'danger')
            return redirect(url_for('auth.change_password'))

        # Validate new password strength
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            flash(error_msg, 'danger')
            return redirect(url_for('auth.change_password'))

        # Check passwords match
        if new_password != confirm_password:
            flash('New passwords do not match', 'danger')
            return redirect(url_for('auth.change_password'))

        # Prevent reusing the same password
        if current_user.check_password(new_password):
            flash('New password cannot be the same as your current password', 'danger')
            return redirect(url_for('auth.change_password'))

        # Update password
        current_user.set_password(new_password)
        current_user.force_password_change = False
        current_user.password_changed_at = datetime.utcnow()
        db.session.commit()

        log_activity(current_user.id, 'password_change', 'user', current_user.id, 'Password changed')
        flash('Password changed successfully', 'success')
        return redirect(url_for('index'))

    return render_template('auth/change_password.html')


def log_activity(user_id, action, entity_type, entity_id, details):
    """Helper function to log user activities"""
    try:
        log = ActivityLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip_address=request.remote_addr if request else None
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        # Don't fail the request if logging fails
        db.session.rollback()
        print(f"Error logging activity: {e}")
