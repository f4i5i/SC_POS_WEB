"""
Settings and Configuration Routes
Handles application settings, user management, and system configuration
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from app.models import db, User, Setting, Category, ActivityLog, Location
from app.utils.helpers import has_permission
from app.utils.permissions import permission_required, Permissions
from datetime import datetime

bp = Blueprint('settings', __name__)


@bp.route('/')
@login_required
@permission_required(Permissions.SETTINGS_VIEW)
def index():
    """Settings dashboard"""
    if not current_user.role == 'admin':
        flash('You do not have permission to access settings', 'danger')
        return redirect(url_for('index'))

    return render_template('settings/index.html')


@bp.route('/users')
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def users():
    """User management"""
    if not current_user.role == 'admin':
        flash('You do not have permission to manage users', 'danger')
        return redirect(url_for('index'))

    users = User.query.all()
    return render_template('settings/users.html', users=users)


@bp.route('/users/add', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def add_user():
    """Add new user"""
    if not current_user.role == 'admin':
        flash('You do not have permission to add users', 'danger')
        return redirect(url_for('settings.users'))

    if request.method == 'POST':
        try:
            # Check if username already exists
            existing = User.query.filter_by(username=request.form.get('username')).first()
            if existing:
                flash('Username already exists', 'danger')
                return redirect(url_for('settings.add_user'))

            # Get location_id
            location_id = request.form.get('location_id')
            location_id = int(location_id) if location_id else None

            user = User(
                username=request.form.get('username'),
                email=request.form.get('email'),
                full_name=request.form.get('full_name'),
                role=request.form.get('role'),
                location_id=location_id,
                is_global_admin=request.form.get('is_global_admin') == 'on',
                is_active=True
            )
            user.set_password(request.form.get('password'))

            db.session.add(user)
            db.session.commit()

            flash(f'User {user.username} created successfully', 'success')
            return redirect(url_for('settings.users'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating user: {str(e)}', 'danger')

    # Get all locations for dropdown
    locations = Location.query.filter_by(is_active=True).order_by(Location.location_type, Location.name).all()
    return render_template('settings/add_user.html', locations=locations)


@bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def edit_user(user_id):
    """Edit user"""
    if not current_user.role == 'admin':
        flash('You do not have permission to edit users', 'danger')
        return redirect(url_for('settings.users'))

    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        try:
            user.full_name = request.form.get('full_name')
            user.email = request.form.get('email')
            user.role = request.form.get('role')
            user.is_active = request.form.get('is_active') == 'true'

            # Update location
            location_id = request.form.get('location_id')
            user.location_id = int(location_id) if location_id else None

            # Update global admin status
            user.is_global_admin = request.form.get('is_global_admin') == 'on'

            # Update password if provided
            new_password = request.form.get('password')
            if new_password:
                user.set_password(new_password)

            db.session.commit()
            flash(f'User {user.username} updated successfully', 'success')
            return redirect(url_for('settings.users'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating user: {str(e)}', 'danger')

    # Get all locations for dropdown
    locations = Location.query.filter_by(is_active=True).order_by(Location.location_type, Location.name).all()
    return render_template('settings/edit_user.html', user=user, locations=locations)


@bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def delete_user(user_id):
    """Deactivate user"""
    if not current_user.role == 'admin':
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    try:
        user = User.query.get_or_404(user_id)

        # Don't allow deleting yourself
        if user.id == current_user.id:
            return jsonify({'success': False, 'error': 'Cannot delete your own account'}), 400

        user.is_active = False
        db.session.commit()

        return jsonify({'success': True, 'message': 'User deactivated successfully'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/business')
@login_required
def business_settings():
    """Business configuration"""
    if not current_user.role == 'admin':
        flash('You do not have permission to access business settings', 'danger')
        return redirect(url_for('index'))

    # Get current settings
    settings = {}
    for key in ['business_name', 'business_address', 'business_phone', 'business_email',
                'currency', 'currency_symbol', 'tax_rate']:
        setting = Setting.query.filter_by(key=key).first()
        if setting:
            settings[key] = setting.value

    return render_template('settings/business.html', settings=settings)


@bp.route('/business/update', methods=['POST'])
@login_required
def update_business_settings():
    """Update business settings"""
    if not current_user.role == 'admin':
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    try:
        settings_data = request.form.to_dict()

        for key, value in settings_data.items():
            setting = Setting.query.filter_by(key=key).first()
            if setting:
                setting.value = value
                setting.updated_at = datetime.utcnow()
            else:
                setting = Setting(key=key, value=value, category='business')
                db.session.add(setting)

        db.session.commit()
        flash('Business settings updated successfully', 'success')
        return redirect(url_for('settings.business_settings'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error updating settings: {str(e)}', 'danger')
        return redirect(url_for('settings.business_settings'))


@bp.route('/categories')
@login_required
def categories():
    """Manage product categories"""
    if not current_user.role in ['admin', 'manager']:
        flash('You do not have permission to manage categories', 'danger')
        return redirect(url_for('index'))

    categories = Category.query.all()
    return render_template('settings/categories.html', categories=categories)


@bp.route('/categories/add', methods=['POST'])
@login_required
def add_category():
    """Add new category"""
    if not current_user.role in ['admin', 'manager']:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    try:
        data = request.get_json()
        category = Category(
            name=data.get('name'),
            description=data.get('description'),
            parent_id=data.get('parent_id')
        )

        db.session.add(category)
        db.session.commit()

        return jsonify({
            'success': True,
            'category': {
                'id': category.id,
                'name': category.name
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/activity-log')
@login_required
def activity_log():
    """View activity log"""
    if not current_user.role == 'admin':
        flash('You do not have permission to view activity log', 'danger')
        return redirect(url_for('index'))

    page = request.args.get('page', 1, type=int)
    per_page = current_app.config['ITEMS_PER_PAGE']

    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)

    return render_template('settings/activity_log.html', logs=logs)


@bp.route('/sync-status')
@login_required
def sync_status():
    """View sync status"""
    if not current_user.role == 'admin':
        flash('You do not have permission to view sync status', 'danger')
        return redirect(url_for('index'))

    from app.models import SyncQueue

    pending = SyncQueue.query.filter_by(status='pending').count()
    synced = SyncQueue.query.filter_by(status='synced').count()
    failed = SyncQueue.query.filter_by(status='failed').count()

    recent_syncs = SyncQueue.query.order_by(SyncQueue.created_at.desc()).limit(50).all()

    return render_template('settings/sync_status.html',
                         pending=pending,
                         synced=synced,
                         failed=failed,
                         recent_syncs=recent_syncs)
