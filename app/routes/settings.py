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
                is_developer=request.form.get('is_developer') == 'on',
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

            # Update global admin and developer status
            user.is_global_admin = request.form.get('is_global_admin') == 'on'
            user.is_developer = request.form.get('is_developer') == 'on'

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
    if not (current_user.role in ['admin', 'manager'] or current_user.is_global_admin):
        flash('You do not have permission to manage categories', 'danger')
        return redirect(url_for('index'))

    categories = Category.query.all()
    return render_template('settings/categories.html', categories=categories)


@bp.route('/categories/add', methods=['POST'])
@login_required
def add_category():
    """Add new category"""
    if not (current_user.role in ['admin', 'manager'] or current_user.is_global_admin):
        if request.is_json:
            return jsonify({'success': False, 'error': 'Permission denied'}), 403
        flash('Permission denied', 'danger')
        return redirect(url_for('settings.categories'))

    try:
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
            name = data.get('name')
            description = data.get('description')
        else:
            name = request.form.get('name')
            description = request.form.get('description')

        if not name:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Category name is required'}), 400
            flash('Category name is required', 'danger')
            return redirect(url_for('settings.categories'))

        category = Category(
            name=name,
            description=description
        )

        db.session.add(category)
        db.session.commit()

        if request.is_json:
            return jsonify({
                'success': True,
                'category': {
                    'id': category.id,
                    'name': category.name
                }
            })

        flash(f'Category "{name}" added successfully!', 'success')
        return redirect(url_for('settings.categories'))

    except Exception as e:
        db.session.rollback()
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Error adding category: {str(e)}', 'danger')
        return redirect(url_for('settings.categories'))


@bp.route('/categories/delete/<int:category_id>', methods=['POST'])
@login_required
def delete_category(category_id):
    """Delete a category"""
    if not (current_user.role in ['admin', 'manager'] or current_user.is_global_admin):
        if request.is_json:
            return jsonify({'success': False, 'error': 'Permission denied'}), 403
        flash('Permission denied', 'danger')
        return redirect(url_for('settings.categories'))

    try:
        category = Category.query.get_or_404(category_id)
        category_name = category.name

        # Check if category has products
        if hasattr(category, 'products') and category.products:
            error_msg = f'Cannot delete category with {len(category.products)} products. Move products first.'
            if request.is_json:
                return jsonify({'success': False, 'error': error_msg}), 400
            flash(error_msg, 'danger')
            return redirect(url_for('settings.categories'))

        db.session.delete(category)
        db.session.commit()

        if request.is_json:
            return jsonify({'success': True})

        flash(f'Category "{category_name}" deleted successfully!', 'success')
        return redirect(url_for('settings.categories'))
    except Exception as e:
        db.session.rollback()
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Error deleting category: {str(e)}', 'danger')
        return redirect(url_for('settings.categories'))


@bp.route('/activity-log')
@login_required
def activity_log():
    """View activity log with filters"""
    if not current_user.role == 'admin':
        flash('You do not have permission to view activity log', 'danger')
        return redirect(url_for('index'))

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    # Get filter parameters
    user_id = request.args.get('user_id', type=int)
    action_type = request.args.get('action_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    # Build query with filters
    query = ActivityLog.query

    if user_id:
        query = query.filter(ActivityLog.user_id == user_id)

    if action_type:
        query = query.filter(ActivityLog.action == action_type)

    if date_from:
        from datetime import datetime
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(ActivityLog.timestamp >= date_from_obj)
        except ValueError:
            pass

    if date_to:
        from datetime import datetime, timedelta
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(ActivityLog.timestamp < date_to_obj)
        except ValueError:
            pass

    logs = query.order_by(ActivityLog.timestamp.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)

    # Get unique action types for filter dropdown
    action_types = db.session.query(ActivityLog.action).distinct().all()
    action_types = [a[0] for a in action_types if a[0]]

    # Get users for filter dropdown
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()

    # Get security stats
    from datetime import datetime, timedelta
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    failed_logins_today = ActivityLog.query.filter(
        ActivityLog.action == 'failed_login',
        ActivityLog.timestamp >= today
    ).count()

    locked_accounts = User.query.filter(
        User.locked_until > datetime.utcnow()
    ).count()

    return render_template('settings/activity_log.html',
                         logs=logs,
                         users=users,
                         action_types=action_types,
                         current_filters={
                             'user_id': user_id,
                             'action_type': action_type,
                             'date_from': date_from,
                             'date_to': date_to,
                             'per_page': per_page
                         },
                         failed_logins_today=failed_logins_today,
                         locked_accounts=locked_accounts)


@bp.route('/activity-log/export')
@login_required
def export_activity_log():
    """Export activity log to CSV"""
    if not current_user.role == 'admin':
        flash('You do not have permission to export activity log', 'danger')
        return redirect(url_for('index'))

    import csv
    from io import StringIO
    from flask import Response

    # Get filter parameters
    user_id = request.args.get('user_id', type=int)
    action_type = request.args.get('action_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = ActivityLog.query

    if user_id:
        query = query.filter(ActivityLog.user_id == user_id)
    if action_type:
        query = query.filter(ActivityLog.action == action_type)
    if date_from:
        from datetime import datetime
        try:
            query = query.filter(ActivityLog.timestamp >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        from datetime import datetime, timedelta
        try:
            query = query.filter(ActivityLog.timestamp < datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
        except ValueError:
            pass

    logs = query.order_by(ActivityLog.timestamp.desc()).limit(10000).all()

    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Timestamp', 'User', 'Action', 'Entity Type', 'Entity ID', 'Details', 'IP Address'])

    for log in logs:
        writer.writerow([
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            log.user.full_name if log.user else 'System',
            log.action,
            log.entity_type or '',
            log.entity_id or '',
            log.details or '',
            log.ip_address or ''
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=activity_log.csv'}
    )


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


@bp.route('/backup')
@login_required
@permission_required(Permissions.SETTINGS_VIEW)
def backup():
    """Backup management dashboard"""
    if not current_user.role == 'admin':
        flash('You do not have permission to manage backups', 'danger')
        return redirect(url_for('index'))

    from app.services.backup_service import BackupService

    backup_service = BackupService(current_app)
    backups = backup_service.list_backups()

    # Get backup settings
    backup_settings = {
        'enabled': current_app.config.get('BACKUP_ENABLED', True),
        'time': current_app.config.get('BACKUP_TIME', '23:00'),
        'retention_days': current_app.config.get('BACKUP_RETENTION_DAYS', 30),
        'folder': current_app.config.get('BACKUP_FOLDER', 'backups')
    }

    return render_template('settings/backup.html',
                         backups=backups,
                         backup_settings=backup_settings)


@bp.route('/backup/create', methods=['POST'])
@login_required
@permission_required(Permissions.SETTINGS_VIEW)
def create_backup():
    """Create a new backup"""
    if not current_user.role == 'admin':
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    try:
        from app.services.backup_service import BackupService

        backup_service = BackupService(current_app)
        backup_path = backup_service.backup_database()

        if backup_path:
            # Log the action
            log = ActivityLog(
                user_id=current_user.id,
                action='backup_created',
                entity_type='system',
                details=f"Database backup created: {backup_path.split('/')[-1]}",
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Backup created successfully',
                'filename': backup_path.split('/')[-1]
            })
        else:
            return jsonify({'success': False, 'error': 'Backup failed'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/backup/restore/<filename>', methods=['POST'])
@login_required
@permission_required(Permissions.SETTINGS_VIEW)
def restore_backup(filename):
    """Restore database from backup"""
    if not current_user.role == 'admin':
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    try:
        from app.services.backup_service import BackupService

        backup_service = BackupService(current_app)
        success = backup_service.restore_backup(filename)

        if success:
            # Log the action
            log = ActivityLog(
                user_id=current_user.id,
                action='backup_restored',
                entity_type='system',
                details=f"Database restored from backup: {filename}",
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Database restored successfully. Please reload the page.'
            })
        else:
            return jsonify({'success': False, 'error': 'Restore failed'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/backup/download/<filename>')
@login_required
@permission_required(Permissions.SETTINGS_VIEW)
def download_backup(filename):
    """Download a backup file"""
    if not current_user.role == 'admin':
        flash('You do not have permission to download backups', 'danger')
        return redirect(url_for('settings.backup'))

    from flask import send_file
    import os

    backup_folder = current_app.config.get('BACKUP_FOLDER')
    backup_path = os.path.join(backup_folder, filename)

    if os.path.exists(backup_path) and filename.startswith('backup_'):
        return send_file(
            backup_path,
            as_attachment=True,
            download_name=filename
        )
    else:
        flash('Backup file not found', 'danger')
        return redirect(url_for('settings.backup'))


@bp.route('/backup/delete/<filename>', methods=['POST'])
@login_required
@permission_required(Permissions.SETTINGS_VIEW)
def delete_backup(filename):
    """Delete a backup file"""
    if not current_user.role == 'admin':
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    import os

    try:
        backup_folder = current_app.config.get('BACKUP_FOLDER')
        backup_path = os.path.join(backup_folder, filename)

        if os.path.exists(backup_path) and filename.startswith('backup_'):
            os.remove(backup_path)

            # Log the action
            log = ActivityLog(
                user_id=current_user.id,
                action='backup_deleted',
                entity_type='system',
                details=f"Backup deleted: {filename}",
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()

            return jsonify({'success': True, 'message': 'Backup deleted successfully'})
        else:
            return jsonify({'success': False, 'error': 'Backup not found'}), 404

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
