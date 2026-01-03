"""
Authentication Routes
Handles user login, logout, and authentication
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from app.models import db, User, ActivityLog

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)

        user = User.query.filter_by(username=username).first()

        if user is None or not user.check_password(password):
            flash('Invalid username or password', 'danger')
            log_activity(None, 'failed_login', 'user', None, f'Failed login attempt for username: {username}')
            return redirect(url_for('auth.login'))

        if not user.is_active:
            flash('Your account has been deactivated. Please contact administrator.', 'warning')
            return redirect(url_for('auth.login'))

        # Login successful
        login_user(user, remember=remember)
        user.last_login = datetime.utcnow()
        db.session.commit()

        log_activity(user.id, 'login', 'user', user.id, 'User logged in')

        # Set current location in session
        if user.location_id:
            session['current_location_id'] = user.location_id
            location_name = user.location.name if user.location else 'Unknown'
            flash(f'Welcome! You are logged in at: {location_name}', 'success')
        elif user.is_global_admin:
            flash('Welcome! You have Global Admin access to all locations.', 'success')
        else:
            flash('Welcome! No location assigned - please contact admin.', 'warning')

        # Redirect to next page or role-based dashboard
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)

        # Role-based redirect
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


@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change user password"""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Validate current password
        if not current_user.check_password(current_password):
            flash('Current password is incorrect', 'danger')
            return redirect(url_for('auth.change_password'))

        # Validate new password
        if len(new_password) < 6:
            flash('New password must be at least 6 characters long', 'danger')
            return redirect(url_for('auth.change_password'))

        if new_password != confirm_password:
            flash('New passwords do not match', 'danger')
            return redirect(url_for('auth.change_password'))

        # Update password
        current_user.set_password(new_password)
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
