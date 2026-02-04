"""
Price Change Audit Routes
Tracks and manages all price changes in the system
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import func, and_, or_
from app.models import db, PriceChangeLog, PriceChangeRule, Product, User, Location, Category
from app.utils.permissions import permission_required, Permissions
from app.utils.location_context import get_current_location
import json

bp = Blueprint('price_audit', __name__, url_prefix='/price-audit')


@bp.route('/')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def index():
    """View price change audit logs"""
    # Filters
    product_id = request.args.get('product_id', type=int)
    user_id = request.args.get('user_id', type=int)
    price_type = request.args.get('price_type')
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    min_change = request.args.get('min_change', type=float)
    approval_status = request.args.get('approval_status')

    query = PriceChangeLog.query

    if product_id:
        query = query.filter_by(product_id=product_id)
    if user_id:
        query = query.filter_by(changed_by=user_id)
    if price_type:
        query = query.filter_by(price_type=price_type)
    if from_date:
        query = query.filter(PriceChangeLog.changed_at >= datetime.strptime(from_date, '%Y-%m-%d'))
    if to_date:
        query = query.filter(PriceChangeLog.changed_at <= datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1))
    if min_change:
        query = query.filter(func.abs(PriceChangeLog.change_percentage) >= min_change)
    if approval_status:
        query = query.filter_by(approval_status=approval_status)

    logs = query.order_by(PriceChangeLog.changed_at.desc()).limit(200).all()

    # Stats
    total_increases = sum(1 for l in logs if l.change_amount and l.change_amount > 0)
    total_decreases = sum(1 for l in logs if l.change_amount and l.change_amount < 0)
    pending_approvals = PriceChangeLog.query.filter_by(approval_status='pending').count()

    # Get filter options
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    products = Product.query.filter_by(is_active=True).order_by(Product.name).limit(100).all()

    price_types = [
        ('selling_price', 'Selling Price'),
        ('cost_price', 'Cost Price'),
        ('base_cost', 'Base Cost'),
        ('packaging_cost', 'Packaging Cost'),
        ('delivery_cost', 'Delivery Cost'),
        ('bottle_cost', 'Bottle Cost'),
        ('kiosk_cost', 'Kiosk Cost')
    ]

    return render_template('price_audit/index.html',
                         logs=logs,
                         total_increases=total_increases,
                         total_decreases=total_decreases,
                         pending_approvals=pending_approvals,
                         users=users,
                         products=products,
                         price_types=price_types,
                         product_id=product_id,
                         user_id=user_id,
                         price_type=price_type,
                         from_date=from_date,
                         to_date=to_date,
                         min_change=min_change,
                         approval_status=approval_status)


@bp.route('/product/<int:product_id>')
@login_required
@permission_required(Permissions.INVENTORY_VIEW)
def product_history(product_id):
    """View price change history for a specific product"""
    product = Product.query.get_or_404(product_id)

    logs = PriceChangeLog.query.filter_by(product_id=product_id).order_by(
        PriceChangeLog.changed_at.desc()
    ).all()

    # Group by price type
    by_type = {}
    for log in logs:
        if log.price_type not in by_type:
            by_type[log.price_type] = []
        by_type[log.price_type].append(log)

    return render_template('price_audit/product_history.html',
                         product=product,
                         logs=logs,
                         by_type=by_type)


@bp.route('/summary')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def summary():
    """Price change summary report"""
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    if not from_date:
        from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')

    start_date = datetime.strptime(from_date, '%Y-%m-%d')
    end_date = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)

    base_filter = [
        PriceChangeLog.changed_at >= start_date,
        PriceChangeLog.changed_at < end_date
    ]

    # Total changes
    total_changes = PriceChangeLog.query.filter(*base_filter).count()

    # By price type
    by_type = db.session.query(
        PriceChangeLog.price_type,
        func.count(PriceChangeLog.id).label('count'),
        func.avg(PriceChangeLog.change_percentage).label('avg_change')
    ).filter(*base_filter).group_by(PriceChangeLog.price_type).all()

    # By user
    by_user = db.session.query(
        User.full_name,
        func.count(PriceChangeLog.id).label('count')
    ).join(PriceChangeLog.user).filter(*base_filter).group_by(User.id).order_by(
        func.count(PriceChangeLog.id).desc()
    ).all()

    # Large changes (>20%)
    large_changes = PriceChangeLog.query.filter(
        *base_filter,
        func.abs(PriceChangeLog.change_percentage) >= 20
    ).order_by(func.abs(PriceChangeLog.change_percentage).desc()).limit(20).all()

    # By day
    by_day = db.session.query(
        func.date(PriceChangeLog.changed_at).label('date'),
        func.count(PriceChangeLog.id).label('count')
    ).filter(*base_filter).group_by(func.date(PriceChangeLog.changed_at)).order_by(
        func.date(PriceChangeLog.changed_at)
    ).all()

    # Increases vs decreases
    increases = PriceChangeLog.query.filter(
        *base_filter,
        PriceChangeLog.change_amount > 0
    ).count()

    decreases = PriceChangeLog.query.filter(
        *base_filter,
        PriceChangeLog.change_amount < 0
    ).count()

    return render_template('price_audit/summary.html',
                         from_date=from_date,
                         to_date=to_date,
                         total_changes=total_changes,
                         by_type=by_type,
                         by_user=by_user,
                         large_changes=large_changes,
                         by_day=by_day,
                         increases=increases,
                         decreases=decreases)


@bp.route('/rules')
@login_required
@permission_required(Permissions.SETTINGS_EDIT)
def rules():
    """Manage price change rules"""
    rules = PriceChangeRule.query.order_by(PriceChangeRule.name).all()
    return render_template('price_audit/rules.html', rules=rules)


@bp.route('/rules/add', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.SETTINGS_EDIT)
def add_rule():
    """Add a price change rule"""
    if request.method == 'POST':
        rule = PriceChangeRule(
            name=request.form.get('name'),
            description=request.form.get('description'),
            rule_type=request.form.get('rule_type', 'percentage'),
            requires_approval=request.form.get('requires_approval') == 'on',
            notify_managers=request.form.get('notify_managers') == 'on',
            notify_email=request.form.get('notify_email'),
            is_active=request.form.get('is_active') == 'on'
        )

        min_pct = request.form.get('min_change_percentage')
        rule.min_change_percentage = Decimal(min_pct) if min_pct else None

        min_amt = request.form.get('min_change_amount')
        rule.min_change_amount = Decimal(min_amt) if min_amt else None

        roles = request.form.getlist('applies_to_roles[]')
        rule.applies_to_roles = json.dumps(roles) if roles else None

        price_types = request.form.getlist('applies_to_price_types[]')
        rule.applies_to_price_types = json.dumps(price_types) if price_types else None

        db.session.add(rule)
        db.session.commit()

        flash('Price change rule created', 'success')
        return redirect(url_for('price_audit.rules'))

    from app.utils.permissions import get_default_roles
    default_roles = get_default_roles()

    price_types = [
        ('selling_price', 'Selling Price'),
        ('cost_price', 'Cost Price'),
        ('base_cost', 'Base Cost'),
        ('packaging_cost', 'Packaging Cost'),
        ('delivery_cost', 'Delivery Cost'),
        ('bottle_cost', 'Bottle Cost'),
        ('kiosk_cost', 'Kiosk Cost')
    ]

    return render_template('price_audit/add_rule.html',
                         default_roles=default_roles,
                         price_types=price_types)


@bp.route('/rules/<int:rule_id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.SETTINGS_EDIT)
def edit_rule(rule_id):
    """Edit a price change rule"""
    rule = PriceChangeRule.query.get_or_404(rule_id)

    if request.method == 'POST':
        rule.name = request.form.get('name')
        rule.description = request.form.get('description')
        rule.rule_type = request.form.get('rule_type', 'percentage')
        rule.requires_approval = request.form.get('requires_approval') == 'on'
        rule.notify_managers = request.form.get('notify_managers') == 'on'
        rule.notify_email = request.form.get('notify_email')
        rule.is_active = request.form.get('is_active') == 'on'

        min_pct = request.form.get('min_change_percentage')
        rule.min_change_percentage = Decimal(min_pct) if min_pct else None

        min_amt = request.form.get('min_change_amount')
        rule.min_change_amount = Decimal(min_amt) if min_amt else None

        roles = request.form.getlist('applies_to_roles[]')
        rule.applies_to_roles = json.dumps(roles) if roles else None

        price_types = request.form.getlist('applies_to_price_types[]')
        rule.applies_to_price_types = json.dumps(price_types) if price_types else None

        db.session.commit()
        flash('Rule updated', 'success')
        return redirect(url_for('price_audit.rules'))

    from app.utils.permissions import get_default_roles
    default_roles = get_default_roles()

    price_types = [
        ('selling_price', 'Selling Price'),
        ('cost_price', 'Cost Price'),
        ('base_cost', 'Base Cost'),
        ('packaging_cost', 'Packaging Cost'),
        ('delivery_cost', 'Delivery Cost'),
        ('bottle_cost', 'Bottle Cost'),
        ('kiosk_cost', 'Kiosk Cost')
    ]

    return render_template('price_audit/edit_rule.html',
                         rule=rule,
                         default_roles=default_roles,
                         price_types=price_types)


@bp.route('/rules/<int:rule_id>/delete', methods=['POST'])
@login_required
@permission_required(Permissions.SETTINGS_EDIT)
def delete_rule(rule_id):
    """Delete a price change rule"""
    rule = PriceChangeRule.query.get_or_404(rule_id)
    db.session.delete(rule)
    db.session.commit()
    flash('Rule deleted', 'success')
    return redirect(url_for('price_audit.rules'))


@bp.route('/pending')
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def pending_approvals():
    """View pending price change approvals"""
    pending = PriceChangeLog.query.filter_by(approval_status='pending').order_by(
        PriceChangeLog.changed_at.desc()
    ).all()

    return render_template('price_audit/pending.html', pending=pending)


@bp.route('/approve/<int:log_id>', methods=['POST'])
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def approve_change(log_id):
    """Approve or reject a price change"""
    log = PriceChangeLog.query.get_or_404(log_id)

    action = request.form.get('action')

    if action == 'approve':
        log.approval_status = 'approved'
        log.approved_by = current_user.id
        log.approved_at = datetime.utcnow()

        # Apply the price change to product
        product = log.product
        if product:
            setattr(product, log.price_type, log.new_value)
            db.session.commit()

        flash('Price change approved and applied', 'success')
    elif action == 'reject':
        log.approval_status = 'rejected'
        log.approved_by = current_user.id
        log.approved_at = datetime.utcnow()
        log.notes = request.form.get('rejection_reason', '')

        # Revert to old value
        product = log.product
        if product:
            setattr(product, log.price_type, log.old_value)
            db.session.commit()

        flash('Price change rejected', 'warning')

    db.session.commit()
    return redirect(url_for('price_audit.pending_approvals'))


# ============================================================================
# API ENDPOINTS
# ============================================================================

@bp.route('/api/log', methods=['POST'])
@login_required
def log_price_change():
    """Log a price change - called when product price is updated"""
    data = request.get_json()

    product_id = data.get('product_id')
    price_type = data.get('price_type', 'selling_price')
    old_value = Decimal(str(data.get('old_value', 0)))
    new_value = Decimal(str(data.get('new_value', 0)))
    reason = data.get('reason', '')
    source = data.get('source', 'manual')

    if old_value == new_value:
        return jsonify({'success': True, 'message': 'No change'})

    log = PriceChangeLog(
        product_id=product_id,
        location_id=data.get('location_id'),
        changed_by=current_user.id,
        price_type=price_type,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        source=source,
        batch_id=data.get('batch_id')
    )

    log.calculate_change()

    # Check if approval is required
    rules = PriceChangeRule.query.filter_by(is_active=True).all()
    requires_approval = False

    for rule in rules:
        # Check if rule applies to this user's role
        roles = rule.get_roles()
        if roles and current_user.role not in roles:
            continue

        # Check if rule applies to this price type
        price_types = rule.get_price_types()
        if price_types and price_type not in price_types:
            continue

        # Check thresholds
        if rule.rule_type == 'percentage' and rule.min_change_percentage:
            if abs(log.change_percentage) >= float(rule.min_change_percentage):
                requires_approval = rule.requires_approval
                break
        elif rule.rule_type == 'amount' and rule.min_change_amount:
            if abs(log.change_amount) >= float(rule.min_change_amount):
                requires_approval = rule.requires_approval
                break
        elif rule.rule_type == 'any':
            requires_approval = rule.requires_approval
            break

    log.required_approval = requires_approval
    log.approval_status = 'pending' if requires_approval else 'auto'

    db.session.add(log)
    db.session.commit()

    return jsonify({
        'success': True,
        'log_id': log.id,
        'requires_approval': requires_approval,
        'change_percentage': float(log.change_percentage) if log.change_percentage else 0
    })


@bp.route('/api/check', methods=['POST'])
@login_required
def check_price_change():
    """Check if a price change requires approval"""
    data = request.get_json()

    old_value = Decimal(str(data.get('old_value', 0)))
    new_value = Decimal(str(data.get('new_value', 0)))
    price_type = data.get('price_type', 'selling_price')

    if old_value == new_value:
        return jsonify({'requires_approval': False})

    change_amount = new_value - old_value
    change_percentage = ((new_value - old_value) / old_value * 100) if old_value else 100

    rules = PriceChangeRule.query.filter_by(is_active=True).all()

    for rule in rules:
        roles = rule.get_roles()
        if roles and current_user.role not in roles:
            continue

        price_types = rule.get_price_types()
        if price_types and price_type not in price_types:
            continue

        if rule.rule_type == 'percentage' and rule.min_change_percentage:
            if abs(change_percentage) >= float(rule.min_change_percentage):
                return jsonify({
                    'requires_approval': rule.requires_approval,
                    'rule_name': rule.name,
                    'change_percentage': float(change_percentage)
                })
        elif rule.rule_type == 'amount' and rule.min_change_amount:
            if abs(change_amount) >= float(rule.min_change_amount):
                return jsonify({
                    'requires_approval': rule.requires_approval,
                    'rule_name': rule.name,
                    'change_amount': float(change_amount)
                })

    return jsonify({'requires_approval': False, 'change_percentage': float(change_percentage)})
