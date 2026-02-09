"""
Developer Tools Routes
Error log viewer and Django admin-like database browser.
Restricted to users with is_developer=True.
"""

from functools import wraps
from datetime import datetime
from flask import (
    Blueprint, render_template, request, jsonify,
    flash, redirect, url_for, abort
)
from flask_login import login_required, current_user
from app.models import db, ErrorLog
from app.utils.model_registry import (
    get_models_by_category, get_model_by_tablename,
    get_column_info, get_string_columns, coerce_value
)

bp = Blueprint('developer', __name__)


def developer_required(f):
    """Decorator to restrict access to developer accounts only."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not getattr(current_user, 'is_developer', False):
            if request.is_json:
                return jsonify({'error': 'Developer access required'}), 403
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


# ============================================================
# ERROR LOG ROUTES
# ============================================================

@bp.route('/errors')
@developer_required
def error_list():
    """Paginated error log list with filters."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)

    # Filters
    error_type = request.args.get('error_type', '')
    status_code = request.args.get('status_code', '', type=str)
    resolved = request.args.get('resolved', '')
    search = request.args.get('search', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = ErrorLog.query

    if error_type:
        query = query.filter(ErrorLog.error_type == error_type)
    if status_code:
        query = query.filter(ErrorLog.status_code == int(status_code))
    if resolved == 'yes':
        query = query.filter(ErrorLog.is_resolved == True)
    elif resolved == 'no':
        query = query.filter(ErrorLog.is_resolved == False)
    if search:
        query = query.filter(
            db.or_(
                ErrorLog.error_message.ilike(f'%{search}%'),
                ErrorLog.request_url.ilike(f'%{search}%'),
                ErrorLog.endpoint.ilike(f'%{search}%')
            )
        )
    if date_from:
        try:
            query = query.filter(ErrorLog.timestamp >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(ErrorLog.timestamp <= datetime.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
        except ValueError:
            pass

    query = query.order_by(ErrorLog.timestamp.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # Get distinct error types and status codes for filter dropdowns
    error_types = db.session.query(ErrorLog.error_type).distinct().order_by(ErrorLog.error_type).all()
    status_codes = db.session.query(ErrorLog.status_code).distinct().order_by(ErrorLog.status_code).all()

    # Stats
    total_errors = ErrorLog.query.count()
    unresolved_count = ErrorLog.query.filter_by(is_resolved=False).count()

    return render_template('developer/error_list.html',
        errors=pagination.items,
        pagination=pagination,
        error_types=[e[0] for e in error_types],
        status_codes=[s[0] for s in status_codes if s[0]],
        filters={
            'error_type': error_type,
            'status_code': status_code,
            'resolved': resolved,
            'search': search,
            'date_from': date_from,
            'date_to': date_to,
        },
        total_errors=total_errors,
        unresolved_count=unresolved_count,
    )


@bp.route('/errors/<int:id>')
@developer_required
def error_detail(id):
    """View full error details."""
    error = ErrorLog.query.get_or_404(id)
    return render_template('developer/error_detail.html', error=error)


@bp.route('/errors/<int:id>/resolve', methods=['POST'])
@developer_required
def resolve_error(id):
    """Mark an error as resolved."""
    error = ErrorLog.query.get_or_404(id)
    error.is_resolved = True
    error.resolved_by = current_user.id
    error.resolved_at = datetime.utcnow()
    error.resolution_notes = request.form.get('resolution_notes', '')
    db.session.commit()
    flash('Error marked as resolved.', 'success')
    return redirect(url_for('developer.error_detail', id=id))


@bp.route('/errors/<int:id>/unresolve', methods=['POST'])
@developer_required
def unresolve_error(id):
    """Mark an error as unresolved."""
    error = ErrorLog.query.get_or_404(id)
    error.is_resolved = False
    error.resolved_by = None
    error.resolved_at = None
    error.resolution_notes = None
    db.session.commit()
    flash('Error marked as unresolved.', 'info')
    return redirect(url_for('developer.error_detail', id=id))


# ============================================================
# DB BROWSER ROUTES
# ============================================================

@bp.route('/db')
@developer_required
def db_dashboard():
    """Dashboard showing all models by category with record counts."""
    categories = get_models_by_category()
    total_models = sum(len(models) for models in categories.values())
    total_records = sum(
        m['record_count'] for models in categories.values() for m in models
    )
    return render_template('developer/db_dashboard.html',
        categories=categories,
        total_models=total_models,
        total_records=total_records,
    )


@bp.route('/db/<tablename>')
@developer_required
def db_table(tablename):
    """Paginated table view with search and sort."""
    model = get_model_by_tablename(tablename)
    if not model:
        abort(404)

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'id')
    sort_dir = request.args.get('dir', 'desc')

    columns = get_column_info(model)
    col_names = [c['name'] for c in columns]

    query = model.query

    # Search across string columns
    if search:
        string_cols = get_string_columns(model)
        if string_cols:
            filters = [getattr(model, col).ilike(f'%{search}%') for col in string_cols]
            query = query.filter(db.or_(*filters))

    # Sort
    if sort_by in col_names:
        sort_col = getattr(model, sort_by)
        query = query.order_by(sort_col.desc() if sort_dir == 'desc' else sort_col.asc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # Limit displayed columns (show first 8 + id)
    display_columns = columns[:8]

    return render_template('developer/db_table.html',
        model=model,
        tablename=tablename,
        columns=columns,
        display_columns=display_columns,
        records=pagination.items,
        pagination=pagination,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@bp.route('/db/<tablename>/<int:record_id>')
@developer_required
def db_record(tablename, record_id):
    """View a single record with all fields."""
    model = get_model_by_tablename(tablename)
    if not model:
        abort(404)

    record = model.query.get_or_404(record_id)
    columns = get_column_info(model)

    return render_template('developer/db_record.html',
        model=model,
        tablename=tablename,
        record=record,
        columns=columns,
    )


@bp.route('/db/<tablename>/create', methods=['GET', 'POST'])
@developer_required
def db_create(tablename):
    """Create a new record."""
    model = get_model_by_tablename(tablename)
    if not model:
        abort(404)

    columns = get_column_info(model)

    if request.method == 'POST':
        try:
            record = model()
            for col in columns:
                if col['is_hidden'] or col['name'] == 'id':
                    continue
                value = request.form.get(col['name'])
                if col['input_type'] == 'checkbox':
                    value = 'on' if col['name'] in request.form else None
                if value is not None and value != '':
                    setattr(record, col['name'], coerce_value(value, col))
                elif col['nullable']:
                    setattr(record, col['name'], None)

            db.session.add(record)
            db.session.commit()
            flash(f'Record created successfully (ID: {record.id}).', 'success')
            return redirect(url_for('developer.db_record', tablename=tablename, record_id=record.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating record: {str(e)}', 'danger')

    return render_template('developer/db_form.html',
        model=model,
        tablename=tablename,
        columns=columns,
        record=None,
        action='create',
    )


@bp.route('/db/<tablename>/<int:record_id>/edit', methods=['GET', 'POST'])
@developer_required
def db_edit(tablename, record_id):
    """Edit an existing record."""
    model = get_model_by_tablename(tablename)
    if not model:
        abort(404)

    record = model.query.get_or_404(record_id)
    columns = get_column_info(model)

    if request.method == 'POST':
        try:
            for col in columns:
                if col['is_hidden'] or col['name'] == 'id':
                    continue
                value = request.form.get(col['name'])
                if col['input_type'] == 'checkbox':
                    value = 'on' if col['name'] in request.form else None
                if value is not None and value != '':
                    setattr(record, col['name'], coerce_value(value, col))
                elif col['nullable']:
                    setattr(record, col['name'], None)

            db.session.commit()
            flash('Record updated successfully.', 'success')
            return redirect(url_for('developer.db_record', tablename=tablename, record_id=record_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating record: {str(e)}', 'danger')

    return render_template('developer/db_form.html',
        model=model,
        tablename=tablename,
        columns=columns,
        record=record,
        action='edit',
    )


@bp.route('/db/<tablename>/<int:record_id>/delete', methods=['POST'])
@developer_required
def db_delete(tablename, record_id):
    """Delete a record."""
    model = get_model_by_tablename(tablename)
    if not model:
        abort(404)

    record = model.query.get_or_404(record_id)
    try:
        db.session.delete(record)
        db.session.commit()
        flash('Record deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting record: {str(e)}', 'danger')

    return redirect(url_for('developer.db_table', tablename=tablename))
