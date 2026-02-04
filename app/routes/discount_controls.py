"""
Discount Controls Routes
Handles discount limits, approvals, and audit logging
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import func, and_, or_
from app.models import db, DiscountLimit, DiscountApproval, DiscountLog, Sale, User, Location, Product
from app.utils.permissions import permission_required, Permissions
from app.utils.location_context import get_current_location
import json

bp = Blueprint('discount_controls', __name__, url_prefix='/discount-controls')


# ============================================================================
# DISCOUNT LIMITS MANAGEMENT
# ============================================================================

@bp.route('/limits')
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def limits():
    """View and manage discount limits by role"""
    limits = DiscountLimit.query.order_by(DiscountLimit.role).all()

    # Get default roles for reference
    from app.utils.permissions import get_default_roles
    default_roles = get_default_roles()

    return render_template('discount_controls/limits.html',
                         limits=limits,
                         default_roles=default_roles)


@bp.route('/limits/edit/<role>', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def edit_limit(role):
    """Edit discount limit for a role"""
    limit = DiscountLimit.query.filter_by(role=role).first()

    if not limit:
        # Create new limit for this role
        limit = DiscountLimit(role=role)

    if request.method == 'POST':
        limit.max_percentage = Decimal(request.form.get('max_percentage', '0') or '0')
        limit.max_amount = Decimal(request.form.get('max_amount', '0') or '0')
        limit.max_per_item_percentage = Decimal(request.form.get('max_per_item_percentage', '0') or '0')

        # Approval threshold
        approval_threshold = request.form.get('requires_approval_above', '')
        limit.requires_approval_above = Decimal(approval_threshold) if approval_threshold else None

        # Daily limits
        daily_amount = request.form.get('max_daily_discount_amount', '')
        limit.max_daily_discount_amount = Decimal(daily_amount) if daily_amount else None

        daily_count = request.form.get('max_daily_discount_count', '')
        limit.max_daily_discount_count = int(daily_count) if daily_count else None

        # Restrictions
        limit.can_give_free_items = request.form.get('can_give_free_items') == 'on'
        limit.requires_reason = request.form.get('requires_reason') == 'on'

        # Allowed reasons
        reasons = request.form.getlist('allowed_reasons[]')
        custom_reasons = request.form.get('custom_reasons', '')
        if custom_reasons:
            reasons.extend([r.strip() for r in custom_reasons.split(',') if r.strip()])
        limit.allowed_reasons = json.dumps(reasons) if reasons else None

        limit.is_active = request.form.get('is_active') == 'on'

        if limit.id is None:
            db.session.add(limit)

        db.session.commit()
        flash(f'Discount limits for {role} updated successfully', 'success')
        return redirect(url_for('discount_controls.limits'))

    # Default discount reasons
    default_reasons = [
        'Customer Loyalty',
        'Bulk Purchase',
        'Damaged Packaging',
        'Price Match',
        'Promotional Offer',
        'Manager Discretion',
        'Return Customer',
        'Staff Discount',
        'Clearance Sale',
        'Negotiated Price',
        'Other'
    ]

    return render_template('discount_controls/edit_limit.html',
                         limit=limit,
                         role=role,
                         default_reasons=default_reasons)


@bp.route('/limits/delete/<role>', methods=['POST'])
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def delete_limit(role):
    """Delete discount limit for a role"""
    limit = DiscountLimit.query.filter_by(role=role).first()
    if limit:
        db.session.delete(limit)
        db.session.commit()
        flash(f'Discount limits for {role} deleted', 'success')
    return redirect(url_for('discount_controls.limits'))


# ============================================================================
# DISCOUNT APPROVAL ROUTES
# ============================================================================

@bp.route('/approvals')
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def approvals():
    """View pending and recent discount approvals"""
    location = get_current_location()

    # Build query
    query = DiscountApproval.query

    if location and not current_user.is_global_admin:
        query = query.filter_by(location_id=location.id)

    # Status filter
    status_filter = request.args.get('status', 'pending')
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)

    # Date filter
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    if from_date:
        query = query.filter(DiscountApproval.created_at >= datetime.strptime(from_date, '%Y-%m-%d'))
    if to_date:
        query = query.filter(DiscountApproval.created_at <= datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1))

    approvals = query.order_by(DiscountApproval.created_at.desc()).limit(100).all()

    # Count pending
    pending_count = DiscountApproval.query.filter_by(status='pending').count()

    # Get locations for filter
    locations = Location.query.filter_by(is_active=True, can_sell=True).order_by(Location.name).all()

    return render_template('discount_controls/approvals.html',
                         approvals=approvals,
                         status_filter=status_filter,
                         pending_count=pending_count,
                         locations=locations,
                         from_date=from_date,
                         to_date=to_date)


@bp.route('/approvals/<int:approval_id>/process', methods=['POST'])
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def process_approval(approval_id):
    """Approve or reject a discount request"""
    approval = DiscountApproval.query.get_or_404(approval_id)

    action = request.form.get('action')

    if action == 'approve':
        approval.status = 'approved'
        approval.approved_by = current_user.id
        approval.approved_at = datetime.utcnow()
        flash('Discount approved', 'success')
    elif action == 'reject':
        approval.status = 'rejected'
        approval.approved_by = current_user.id
        approval.approved_at = datetime.utcnow()
        approval.rejection_reason = request.form.get('rejection_reason', '')
        flash('Discount rejected', 'warning')

    db.session.commit()

    # Return JSON if API call
    if request.is_json:
        return jsonify({'success': True, 'status': approval.status})

    return redirect(url_for('discount_controls.approvals'))


@bp.route('/approvals/verify', methods=['POST'])
@login_required
def verify_approval_code():
    """Verify approval code for discount at POS"""
    data = request.get_json()
    code = data.get('code', '').upper()
    sale_id = data.get('sale_id')

    approval = DiscountApproval.query.filter_by(
        approval_code=code,
        status='pending'
    ).first()

    if not approval:
        return jsonify({'valid': False, 'error': 'Invalid approval code'})

    if approval.is_expired():
        approval.status = 'expired'
        db.session.commit()
        return jsonify({'valid': False, 'error': 'Approval code has expired'})

    # Mark as approved
    approval.status = 'approved'
    approval.approved_at = datetime.utcnow()
    if sale_id:
        approval.sale_id = sale_id
    db.session.commit()

    return jsonify({
        'valid': True,
        'discount_amount': float(approval.discount_amount),
        'discount_type': approval.discount_type,
        'approver': approval.approver.full_name if approval.approver else 'Manager'
    })


# ============================================================================
# DISCOUNT LOG/AUDIT ROUTES
# ============================================================================

@bp.route('/logs')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def logs():
    """View discount audit logs"""
    location = get_current_location()

    # Build query
    query = DiscountLog.query

    if location and not current_user.is_global_admin:
        query = query.filter_by(location_id=location.id)

    # Filters
    user_id = request.args.get('user_id', type=int)
    reason = request.args.get('reason')
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    min_amount = request.args.get('min_amount', type=float)

    if user_id:
        query = query.filter_by(user_id=user_id)
    if reason:
        query = query.filter_by(discount_reason=reason)
    if from_date:
        query = query.filter(DiscountLog.created_at >= datetime.strptime(from_date, '%Y-%m-%d'))
    if to_date:
        query = query.filter(DiscountLog.created_at <= datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1))
    if min_amount:
        query = query.filter(DiscountLog.discount_amount >= min_amount)

    logs = query.order_by(DiscountLog.created_at.desc()).limit(200).all()

    # Calculate totals
    total_discounts = sum(float(l.discount_amount or 0) for l in logs)

    # Get users for filter
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()

    # Get unique reasons
    reasons_query = db.session.query(DiscountLog.discount_reason).distinct().all()
    unique_reasons = [r[0] for r in reasons_query if r[0]]

    return render_template('discount_controls/logs.html',
                         logs=logs,
                         total_discounts=total_discounts,
                         users=users,
                         unique_reasons=unique_reasons,
                         user_id=user_id,
                         reason=reason,
                         from_date=from_date,
                         to_date=to_date,
                         min_amount=min_amount)


@bp.route('/summary')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def summary():
    """Discount summary report"""
    location = get_current_location()

    # Date range
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    if not from_date:
        from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')

    start_date = datetime.strptime(from_date, '%Y-%m-%d')
    end_date = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)

    # Base query filter
    base_filter = [
        DiscountLog.created_at >= start_date,
        DiscountLog.created_at < end_date
    ]
    if location and not current_user.is_global_admin:
        base_filter.append(DiscountLog.location_id == location.id)

    # Total discounts
    total_result = db.session.query(
        func.sum(DiscountLog.discount_amount).label('total'),
        func.count(DiscountLog.id).label('count')
    ).filter(*base_filter).first()

    total_discount_amount = float(total_result.total or 0)
    total_discount_count = total_result.count or 0

    # Discounts by user
    by_user = db.session.query(
        User.full_name,
        func.sum(DiscountLog.discount_amount).label('total'),
        func.count(DiscountLog.id).label('count')
    ).join(DiscountLog.user).filter(*base_filter).group_by(User.id).order_by(
        func.sum(DiscountLog.discount_amount).desc()
    ).all()

    # Discounts by reason
    by_reason = db.session.query(
        DiscountLog.discount_reason,
        func.sum(DiscountLog.discount_amount).label('total'),
        func.count(DiscountLog.id).label('count')
    ).filter(*base_filter).group_by(DiscountLog.discount_reason).order_by(
        func.sum(DiscountLog.discount_amount).desc()
    ).all()

    # Discounts by day
    by_day = db.session.query(
        func.date(DiscountLog.created_at).label('date'),
        func.sum(DiscountLog.discount_amount).label('total'),
        func.count(DiscountLog.id).label('count')
    ).filter(*base_filter).group_by(func.date(DiscountLog.created_at)).order_by(
        func.date(DiscountLog.created_at)
    ).all()

    # High-value discounts (above 1000)
    high_value = DiscountLog.query.filter(
        *base_filter,
        DiscountLog.discount_amount >= 1000
    ).order_by(DiscountLog.discount_amount.desc()).limit(20).all()

    # Approved vs Unapproved
    approved_count = DiscountLog.query.filter(
        *base_filter,
        DiscountLog.required_approval == True,
        DiscountLog.approval_id.isnot(None)
    ).count()

    unapproved_count = DiscountLog.query.filter(
        *base_filter,
        DiscountLog.required_approval == False
    ).count()

    return render_template('discount_controls/summary.html',
                         from_date=from_date,
                         to_date=to_date,
                         total_discount_amount=total_discount_amount,
                         total_discount_count=total_discount_count,
                         by_user=by_user,
                         by_reason=by_reason,
                         by_day=by_day,
                         high_value=high_value,
                         approved_count=approved_count,
                         unapproved_count=unapproved_count)


# ============================================================================
# API ENDPOINTS FOR POS
# ============================================================================

@bp.route('/api/check-limit', methods=['POST'])
@login_required
def check_discount_limit():
    """Check if a discount is within user's limit - called from POS"""
    data = request.get_json()

    discount_amount = Decimal(str(data.get('discount_amount', 0)))
    discount_percentage = Decimal(str(data.get('discount_percentage', 0)))
    sale_total = Decimal(str(data.get('sale_total', 0)))
    reason = data.get('reason', '')

    # Get user's discount limit
    limit = DiscountLimit.query.filter_by(role=current_user.role, is_active=True).first()

    result = {
        'allowed': True,
        'requires_approval': False,
        'message': '',
        'max_allowed_percentage': None,
        'max_allowed_amount': None
    }

    if not limit:
        # No limit defined - use defaults for non-admin roles
        if current_user.role in ['cashier']:
            result['allowed'] = False
            result['message'] = 'No discount limits configured for your role. Please contact manager.'
            return jsonify(result)
        else:
            # Managers/admins can give any discount
            return jsonify(result)

    # Check percentage limit
    if limit.max_percentage and discount_percentage > limit.max_percentage:
        if limit.requires_approval_above and discount_percentage > limit.requires_approval_above:
            result['requires_approval'] = True
            result['message'] = f'Discount of {discount_percentage}% exceeds your limit of {limit.max_percentage}%. Manager approval required.'
        else:
            result['allowed'] = False
            result['message'] = f'Maximum discount allowed is {limit.max_percentage}%'
        result['max_allowed_percentage'] = float(limit.max_percentage)

    # Check amount limit
    if limit.max_amount and discount_amount > limit.max_amount:
        if limit.requires_approval_above:
            result['requires_approval'] = True
            result['message'] = f'Discount of Rs. {discount_amount} exceeds your limit. Manager approval required.'
        else:
            result['allowed'] = False
            result['message'] = f'Maximum discount allowed is Rs. {limit.max_amount}'
        result['max_allowed_amount'] = float(limit.max_amount)

    # Check if 100% discount requires permission
    if discount_percentage >= 100 and not limit.can_give_free_items:
        result['allowed'] = False
        result['message'] = 'Free items require manager approval'
        result['requires_approval'] = True

    # Check if reason is required
    if limit.requires_reason and not reason:
        result['allowed'] = False
        result['message'] = 'Discount reason is required'

    # Check if reason is in allowed list
    if limit.allowed_reasons and reason:
        allowed_reasons = limit.get_allowed_reasons()
        if allowed_reasons and reason not in allowed_reasons:
            result['allowed'] = False
            result['message'] = f'Reason "{reason}" is not in the allowed list'

    # Check daily limits
    if limit.max_daily_discount_count or limit.max_daily_discount_amount:
        today_start = datetime.combine(date.today(), datetime.min.time())
        today_end = datetime.combine(date.today(), datetime.max.time())

        today_logs = DiscountLog.query.filter(
            DiscountLog.user_id == current_user.id,
            DiscountLog.created_at >= today_start,
            DiscountLog.created_at <= today_end
        ).all()

        if limit.max_daily_discount_count:
            if len(today_logs) >= limit.max_daily_discount_count:
                result['allowed'] = False
                result['message'] = f'Daily discount limit reached ({limit.max_daily_discount_count} discounts)'

        if limit.max_daily_discount_amount:
            today_total = sum(float(l.discount_amount or 0) for l in today_logs)
            if today_total + float(discount_amount) > float(limit.max_daily_discount_amount):
                result['allowed'] = False
                result['message'] = f'Daily discount amount limit reached (Rs. {limit.max_daily_discount_amount})'

    return jsonify(result)


@bp.route('/api/request-approval', methods=['POST'])
@login_required
def request_approval():
    """Request discount approval from manager - called from POS"""
    data = request.get_json()

    location = get_current_location()
    if not location:
        return jsonify({'success': False, 'error': 'Location not set'})

    # Create approval request
    approval = DiscountApproval(
        requested_by=current_user.id,
        location_id=location.id,
        discount_amount=Decimal(str(data.get('discount_amount', 0))),
        discount_percentage=Decimal(str(data.get('discount_percentage', 0))),
        discount_type=data.get('discount_type', 'amount'),
        original_total=Decimal(str(data.get('sale_total', 0))),
        discount_reason=data.get('reason', 'Other'),
        reason_details=data.get('reason_details', ''),
        expires_at=datetime.utcnow() + timedelta(minutes=30)  # Expires in 30 min
    )

    # Generate approval code
    approval.generate_approval_code()

    db.session.add(approval)
    db.session.commit()

    return jsonify({
        'success': True,
        'approval_id': approval.id,
        'approval_code': approval.approval_code,
        'message': f'Ask manager to enter code: {approval.approval_code}'
    })


@bp.route('/api/log-discount', methods=['POST'])
@login_required
def log_discount():
    """Log a discount that was applied - called from POS after sale"""
    data = request.get_json()

    location = get_current_location()

    log = DiscountLog(
        sale_id=data.get('sale_id'),
        sale_item_id=data.get('sale_item_id'),
        user_id=current_user.id,
        location_id=location.id if location else None,
        discount_amount=Decimal(str(data.get('discount_amount', 0))),
        discount_percentage=Decimal(str(data.get('discount_percentage', 0))),
        discount_type=data.get('discount_type', 'amount'),
        original_price=Decimal(str(data.get('original_price', 0))),
        discounted_price=Decimal(str(data.get('discounted_price', 0))),
        product_id=data.get('product_id'),
        product_name=data.get('product_name'),
        discount_reason=data.get('reason', 'Other'),
        reason_details=data.get('reason_details'),
        required_approval=data.get('required_approval', False),
        approval_id=data.get('approval_id'),
        approved_by=data.get('approved_by'),
        promotion_id=data.get('promotion_id'),
        coupon_code=data.get('coupon_code')
    )

    db.session.add(log)
    db.session.commit()

    return jsonify({'success': True, 'log_id': log.id})


# ============================================================================
# DISCOUNT REASONS MANAGEMENT
# ============================================================================

@bp.route('/reasons')
@login_required
@permission_required(Permissions.SETTINGS_EDIT)
def reasons():
    """Manage discount reasons"""
    # Get all unique reasons from logs
    from_logs = db.session.query(DiscountLog.discount_reason).distinct().all()
    used_reasons = set(r[0] for r in from_logs if r[0])

    # Get reasons from limits
    limits = DiscountLimit.query.filter(DiscountLimit.allowed_reasons.isnot(None)).all()
    configured_reasons = set()
    for limit in limits:
        configured_reasons.update(limit.get_allowed_reasons())

    # Default reasons
    default_reasons = [
        'Customer Loyalty',
        'Bulk Purchase',
        'Damaged Packaging',
        'Price Match',
        'Promotional Offer',
        'Manager Discretion',
        'Return Customer',
        'Staff Discount',
        'Clearance Sale',
        'Negotiated Price',
        'Other'
    ]

    all_reasons = sorted(set(default_reasons) | used_reasons | configured_reasons)

    return render_template('discount_controls/reasons.html',
                         all_reasons=all_reasons,
                         default_reasons=default_reasons,
                         used_reasons=used_reasons,
                         configured_reasons=configured_reasons)
