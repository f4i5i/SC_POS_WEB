"""
Expense Tracking Routes
Manage shop expenses with categories
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
from app.models import db
from app.models_extended import Expense, ExpenseCategory
from app.utils.permissions import permission_required, Permissions
from app.utils.feature_flags import feature_required, Features

bp = Blueprint('expenses', __name__)


def generate_expense_number():
    """Generate unique expense number"""
    today = date.today().strftime('%Y%m%d')
    last_expense = Expense.query.filter(
        Expense.expense_number.like(f'EXP-{today}%')
    ).order_by(Expense.expense_number.desc()).first()

    if last_expense:
        last_num = int(last_expense.expense_number.split('-')[-1])
        new_num = last_num + 1
    else:
        new_num = 1

    return f'EXP-{today}-{new_num:04d}'


@bp.route('/')
@login_required
@feature_required(Features.EXPENSE_TRACKING)
def index():
    """Expense list with filters - filtered by location for store managers"""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # Filters
    category_id = request.args.get('category', type=int)
    status = request.args.get('status', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    search = request.args.get('search', '')

    query = Expense.query

    # Filter by location for store managers (not admin/accountant)
    if not current_user.is_global_admin and current_user.role in ['manager', 'kiosk_manager']:
        if current_user.location_id:
            query = query.filter(Expense.location_id == current_user.location_id)
        else:
            query = query.filter(False)  # No location = no data

    if category_id:
        query = query.filter_by(category_id=category_id)
    if status:
        query = query.filter_by(status=status)
    if date_from:
        query = query.filter(Expense.expense_date >= date_from)
    if date_to:
        query = query.filter(Expense.expense_date <= date_to)
    if search:
        query = query.filter(Expense.description.ilike(f'%{search}%'))

    expenses = query.order_by(Expense.expense_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    categories = ExpenseCategory.query.filter_by(is_active=True).all()

    # Calculate totals for current filters
    total_amount = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.id.in_([e.id for e in query.all()])
    ).scalar() or 0

    # Monthly summary
    first_of_month = date.today().replace(day=1)
    monthly_total = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.expense_date >= first_of_month,
        Expense.status == 'approved'
    ).scalar() or 0

    return render_template('expenses/index.html',
                         expenses=expenses,
                         categories=categories,
                         total_amount=total_amount,
                         monthly_total=monthly_total)


@bp.route('/add', methods=['GET', 'POST'])
@login_required
@feature_required(Features.EXPENSE_TRACKING)
def add_expense():
    """Add new expense"""
    if request.method == 'POST':
        try:
            expense = Expense(
                expense_number=generate_expense_number(),
                category_id=request.form.get('category_id'),
                description=request.form.get('description'),
                amount=Decimal(request.form.get('amount')),
                expense_date=datetime.strptime(request.form.get('expense_date'), '%Y-%m-%d').date(),
                payment_method=request.form.get('payment_method', 'cash'),
                reference=request.form.get('reference'),
                vendor_name=request.form.get('vendor_name'),
                notes=request.form.get('notes'),
                created_by=current_user.id,
                location_id=current_user.location_id,  # Link to user's location
                status='pending' if current_user.role in ['cashier', 'manager', 'kiosk_manager'] else 'approved'
            )

            # Auto-approve for admins only (store managers create pending expenses)
            if current_user.role == 'admin' or current_user.is_global_admin:
                expense.status = 'approved'
                expense.approved_by = current_user.id

            db.session.add(expense)
            db.session.commit()

            flash(f'Expense {expense.expense_number} added successfully.', 'success')
            return redirect(url_for('expenses.index'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error adding expense: {str(e)}', 'danger')

    categories = ExpenseCategory.query.filter_by(is_active=True).all()
    return render_template('expenses/add.html', categories=categories)


@bp.route('/edit/<int:expense_id>', methods=['GET', 'POST'])
@login_required
@feature_required(Features.EXPENSE_TRACKING)
def edit_expense(expense_id):
    """Edit expense - Admin/Accountant only"""
    # Store managers can only add, not edit expenses
    if current_user.role in ['manager', 'kiosk_manager'] and not current_user.is_global_admin:
        flash('You do not have permission to edit expenses.', 'danger')
        return redirect(url_for('expenses.index'))

    expense = Expense.query.get_or_404(expense_id)

    if request.method == 'POST':
        try:
            expense.category_id = request.form.get('category_id')
            expense.description = request.form.get('description')
            expense.amount = Decimal(request.form.get('amount'))
            expense.expense_date = datetime.strptime(request.form.get('expense_date'), '%Y-%m-%d').date()
            expense.payment_method = request.form.get('payment_method', 'cash')
            expense.reference = request.form.get('reference')
            expense.vendor_name = request.form.get('vendor_name')
            expense.notes = request.form.get('notes')

            db.session.commit()
            flash('Expense updated successfully.', 'success')
            return redirect(url_for('expenses.index'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating expense: {str(e)}', 'danger')

    categories = ExpenseCategory.query.filter_by(is_active=True).all()
    return render_template('expenses/edit.html', expense=expense, categories=categories)


@bp.route('/approve/<int:expense_id>', methods=['POST'])
@login_required
@feature_required(Features.EXPENSE_TRACKING)
def approve_expense(expense_id):
    """Approve an expense"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    expense = Expense.query.get_or_404(expense_id)
    expense.status = 'approved'
    expense.approved_by = current_user.id
    db.session.commit()

    return jsonify({'success': True, 'message': 'Expense approved'})


@bp.route('/reject/<int:expense_id>', methods=['POST'])
@login_required
@feature_required(Features.EXPENSE_TRACKING)
def reject_expense(expense_id):
    """Reject an expense"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    expense = Expense.query.get_or_404(expense_id)
    expense.status = 'rejected'
    db.session.commit()

    return jsonify({'success': True, 'message': 'Expense rejected'})


@bp.route('/delete/<int:expense_id>', methods=['POST'])
@login_required
@feature_required(Features.EXPENSE_TRACKING)
def delete_expense(expense_id):
    """Delete an expense"""
    expense = Expense.query.get_or_404(expense_id)

    # Only allow deletion of own expenses or by admin
    if expense.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    db.session.delete(expense)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Expense deleted'})


# ============================================================
# EXPENSE CATEGORIES
# ============================================================

@bp.route('/categories')
@login_required
@feature_required(Features.EXPENSE_TRACKING)
def categories():
    """Manage expense categories"""
    categories = ExpenseCategory.query.all()
    return render_template('expenses/categories.html', categories=categories)


@bp.route('/categories/add', methods=['POST'])
@login_required
@feature_required(Features.EXPENSE_TRACKING)
def add_category():
    """Add expense category"""
    try:
        category = ExpenseCategory(
            name=request.form.get('name'),
            description=request.form.get('description'),
            icon=request.form.get('icon', 'money-bill'),
            color=request.form.get('color', '#6B7280')
        )
        db.session.add(category)
        db.session.commit()

        flash('Category added successfully!', 'success')
        return redirect(url_for('expenses.categories'))
    except Exception as e:
        flash(f'Error adding category: {str(e)}', 'error')
        return redirect(url_for('expenses.categories'))


@bp.route('/categories/edit/<int:category_id>', methods=['POST'])
@login_required
@feature_required(Features.EXPENSE_TRACKING)
def edit_category(category_id):
    """Edit expense category"""
    category = ExpenseCategory.query.get_or_404(category_id)

    category.name = request.form.get('name', category.name)
    category.description = request.form.get('description', category.description)
    category.icon = request.form.get('icon', category.icon)
    category.color = request.form.get('color', category.color)

    db.session.commit()
    flash('Category updated successfully!', 'success')
    return redirect(url_for('expenses.categories'))


@bp.route('/categories/delete/<int:category_id>', methods=['GET', 'POST'])
@login_required
@feature_required(Features.EXPENSE_TRACKING)
def delete_category(category_id):
    """Delete expense category"""
    category = ExpenseCategory.query.get_or_404(category_id)

    if category.expenses.count() > 0:
        flash('Cannot delete category with existing expenses.', 'error')
        return redirect(url_for('expenses.categories'))

    db.session.delete(category)
    db.session.commit()

    flash('Category deleted successfully!', 'success')
    return redirect(url_for('expenses.categories'))


@bp.route('/categories/seed-defaults')
@login_required
@feature_required(Features.EXPENSE_TRACKING)
def seed_default_categories():
    """Seed default expense categories"""
    if current_user.role != 'admin':
        flash('Only admin can seed categories.', 'error')
        return redirect(url_for('expenses.categories'))

    default_categories = [
        {'name': 'Rent', 'description': 'Shop/office rent payments', 'icon': 'home', 'color': '#EF4444'},
        {'name': 'Electricity', 'description': 'Electricity bills', 'icon': 'bolt', 'color': '#F59E0B'},
        {'name': 'Water', 'description': 'Water utility bills', 'icon': 'tint', 'color': '#3B82F6'},
        {'name': 'Gas', 'description': 'Gas utility bills', 'icon': 'fire', 'color': '#F97316'},
        {'name': 'Internet/Phone', 'description': 'Internet and phone bills', 'icon': 'wifi', 'color': '#8B5CF6'},
        {'name': 'Salaries', 'description': 'Employee salaries and wages', 'icon': 'users', 'color': '#10B981'},
        {'name': 'Supplies', 'description': 'Office and shop supplies', 'icon': 'shopping-cart', 'color': '#06B6D4'},
        {'name': 'Transport', 'description': 'Transportation and delivery', 'icon': 'truck', 'color': '#6366F1'},
        {'name': 'Maintenance', 'description': 'Repairs and maintenance', 'icon': 'tools', 'color': '#EC4899'},
        {'name': 'Marketing', 'description': 'Advertising and promotion', 'icon': 'bullhorn', 'color': '#14B8A6'},
        {'name': 'Food/Refreshments', 'description': 'Tea, snacks, meals', 'icon': 'utensils', 'color': '#84CC16'},
        {'name': 'Miscellaneous', 'description': 'Other expenses', 'icon': 'money-bill', 'color': '#6B7280'},
    ]

    added = 0
    for cat_data in default_categories:
        existing = ExpenseCategory.query.filter_by(name=cat_data['name']).first()
        if not existing:
            category = ExpenseCategory(**cat_data)
            db.session.add(category)
            added += 1

    db.session.commit()

    if added > 0:
        flash(f'{added} default categories added successfully!', 'success')
    else:
        flash('All default categories already exist.', 'info')

    return redirect(url_for('expenses.categories'))


# ============================================================
# EXPENSE REPORTS
# ============================================================

@bp.route('/report')
@login_required
@feature_required(Features.EXPENSE_TRACKING)
def expense_report():
    """Expense report"""
    # Date range
    date_from = request.args.get('date_from', (date.today() - timedelta(days=30)).isoformat())
    date_to = request.args.get('date_to', date.today().isoformat())

    # Get expenses in range
    expenses = Expense.query.filter(
        Expense.expense_date >= date_from,
        Expense.expense_date <= date_to,
        Expense.status == 'approved'
    ).all()

    # Calculate totals by category
    category_totals = {}
    for expense in expenses:
        cat_name = expense.category.name if expense.category else 'Uncategorized'
        if cat_name not in category_totals:
            category_totals[cat_name] = 0
        category_totals[cat_name] += float(expense.amount)

    # Calculate totals by payment method
    method_totals = {}
    for expense in expenses:
        method = expense.payment_method or 'Unknown'
        if method not in method_totals:
            method_totals[method] = 0
        method_totals[method] += float(expense.amount)

    total_amount = sum(float(e.amount) for e in expenses)

    return render_template('expenses/report.html',
                         expenses=expenses,
                         category_totals=category_totals,
                         method_totals=method_totals,
                         total_amount=total_amount,
                         date_from=date_from,
                         date_to=date_to)
