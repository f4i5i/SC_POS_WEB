"""
Void/Refund Controls Routes
Handles void/refund limits, approvals, and audit logging
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import func, and_, or_
from app.models import db, VoidRefundLimit, VoidRefundApproval, VoidRefundLog, Sale, User, Location
from app.utils.permissions import permission_required, Permissions
from app.utils.location_context import get_current_location
import json

bp = Blueprint('void_refund_controls', __name__, url_prefix='/void-refund-controls')


# ============================================================================
# VOID/REFUND LIMITS MANAGEMENT
# ============================================================================

@bp.route('/limits')
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def limits():
    """View and manage void/refund limits by role"""
    limits = VoidRefundLimit.query.order_by(VoidRefundLimit.role).all()

    from app.utils.permissions import get_default_roles
    default_roles = get_default_roles()

    return render_template('void_refund_controls/limits.html',
                         limits=limits,
                         default_roles=default_roles)


@bp.route('/limits/edit/<role>', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def edit_limit(role):
    """Edit void/refund limit for a role"""
    limit = VoidRefundLimit.query.filter_by(role=role).first()

    if not limit:
        limit = VoidRefundLimit(role=role)

    if request.method == 'POST':
        # Void settings
        limit.can_void_sale = request.form.get('can_void_sale') == 'on'
        limit.void_time_limit_hours = int(request.form.get('void_time_limit_hours', '24') or '24')

        max_void = request.form.get('max_void_amount', '')
        limit.max_void_amount = Decimal(max_void) if max_void else None

        void_approval = request.form.get('void_requires_approval_above', '')
        limit.void_requires_approval_above = Decimal(void_approval) if void_approval else None

        # Refund settings
        limit.can_refund = request.form.get('can_refund') == 'on'
        limit.refund_time_limit_days = int(request.form.get('refund_time_limit_days', '7') or '7')

        max_refund = request.form.get('max_refund_amount', '')
        limit.max_refund_amount = Decimal(max_refund) if max_refund else None

        refund_approval = request.form.get('refund_requires_approval_above', '')
        limit.refund_requires_approval_above = Decimal(refund_approval) if refund_approval else None

        # Daily limits
        daily_void_count = request.form.get('max_daily_void_count', '')
        limit.max_daily_void_count = int(daily_void_count) if daily_void_count else None

        daily_void_amount = request.form.get('max_daily_void_amount', '')
        limit.max_daily_void_amount = Decimal(daily_void_amount) if daily_void_amount else None

        daily_refund_count = request.form.get('max_daily_refund_count', '')
        limit.max_daily_refund_count = int(daily_refund_count) if daily_refund_count else None

        daily_refund_amount = request.form.get('max_daily_refund_amount', '')
        limit.max_daily_refund_amount = Decimal(daily_refund_amount) if daily_refund_amount else None

        # Requirements
        limit.requires_reason = request.form.get('requires_reason') == 'on'
        limit.requires_customer_signature = request.form.get('requires_customer_signature') == 'on'
        limit.requires_receipt_return = request.form.get('requires_receipt_return') == 'on'

        # Allowed reasons
        reasons = request.form.getlist('allowed_reasons[]')
        custom_reasons = request.form.get('custom_reasons', '')
        if custom_reasons:
            reasons.extend([r.strip() for r in custom_reasons.split(',') if r.strip()])
        limit.allowed_refund_reasons = json.dumps(reasons) if reasons else None

        limit.is_active = request.form.get('is_active') == 'on'

        if limit.id is None:
            db.session.add(limit)

        db.session.commit()
        flash(f'Void/Refund limits for {role} updated successfully', 'success')
        return redirect(url_for('void_refund_controls.limits'))

    # Default refund reasons
    default_reasons = [
        'Defective Product',
        'Wrong Item',
        'Customer Changed Mind',
        'Size Issue',
        'Quality Issue',
        'Duplicate Sale',
        'Price Error',
        'Expired Product',
        'Not as Described',
        'Customer Dissatisfied',
        'Other'
    ]

    return render_template('void_refund_controls/edit_limit.html',
                         limit=limit,
                         role=role,
                         default_reasons=default_reasons)


@bp.route('/limits/delete/<role>', methods=['POST'])
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def delete_limit(role):
    """Delete void/refund limit for a role"""
    limit = VoidRefundLimit.query.filter_by(role=role).first()
    if limit:
        db.session.delete(limit)
        db.session.commit()
        flash(f'Void/Refund limits for {role} deleted', 'success')
    return redirect(url_for('void_refund_controls.limits'))


# ============================================================================
# APPROVAL ROUTES
# ============================================================================

@bp.route('/approvals')
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def approvals():
    """View pending and recent void/refund approvals"""
    location = get_current_location()

    query = VoidRefundApproval.query

    if location and not current_user.is_global_admin:
        query = query.filter_by(location_id=location.id)

    status_filter = request.args.get('status', 'pending')
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)

    request_type = request.args.get('type')
    if request_type:
        query = query.filter_by(request_type=request_type)

    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    if from_date:
        query = query.filter(VoidRefundApproval.created_at >= datetime.strptime(from_date, '%Y-%m-%d'))
    if to_date:
        query = query.filter(VoidRefundApproval.created_at <= datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1))

    approvals = query.order_by(VoidRefundApproval.created_at.desc()).limit(100).all()

    pending_count = VoidRefundApproval.query.filter_by(status='pending').count()
    locations = Location.query.filter_by(is_active=True, can_sell=True).order_by(Location.name).all()

    return render_template('void_refund_controls/approvals.html',
                         approvals=approvals,
                         status_filter=status_filter,
                         request_type=request_type,
                         pending_count=pending_count,
                         locations=locations,
                         from_date=from_date,
                         to_date=to_date)


@bp.route('/approvals/<int:approval_id>/process', methods=['POST'])
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def process_approval(approval_id):
    """Approve or reject a void/refund request"""
    approval = VoidRefundApproval.query.get_or_404(approval_id)

    action = request.form.get('action')

    if action == 'approve':
        approval.status = 'approved'
        approval.approved_by = current_user.id
        approval.approved_at = datetime.utcnow()
        flash('Request approved', 'success')
    elif action == 'reject':
        approval.status = 'rejected'
        approval.approved_by = current_user.id
        approval.approved_at = datetime.utcnow()
        approval.rejection_reason = request.form.get('rejection_reason', '')
        flash('Request rejected', 'warning')

    db.session.commit()

    if request.is_json:
        return jsonify({'success': True, 'status': approval.status})

    return redirect(url_for('void_refund_controls.approvals'))


@bp.route('/approvals/verify', methods=['POST'])
@login_required
def verify_approval_code():
    """Verify approval code for void/refund at POS"""
    data = request.get_json()
    code = data.get('code', '').upper()

    approval = VoidRefundApproval.query.filter_by(
        approval_code=code,
        status='pending'
    ).first()

    if not approval:
        return jsonify({'valid': False, 'error': 'Invalid approval code'})

    if approval.is_expired():
        approval.status = 'expired'
        db.session.commit()
        return jsonify({'valid': False, 'error': 'Approval code has expired'})

    approval.status = 'approved'
    approval.approved_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'valid': True,
        'request_type': approval.request_type,
        'amount': float(approval.amount),
        'approval_id': approval.id
    })


# ============================================================================
# AUDIT LOG ROUTES
# ============================================================================

@bp.route('/logs')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def logs():
    """View void/refund audit logs"""
    location = get_current_location()

    query = VoidRefundLog.query

    if location and not current_user.is_global_admin:
        query = query.filter_by(location_id=location.id)

    user_id = request.args.get('user_id', type=int)
    action_type = request.args.get('type')
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    min_amount = request.args.get('min_amount', type=float)

    if user_id:
        query = query.filter_by(user_id=user_id)
    if action_type:
        query = query.filter_by(action_type=action_type)
    if from_date:
        query = query.filter(VoidRefundLog.created_at >= datetime.strptime(from_date, '%Y-%m-%d'))
    if to_date:
        query = query.filter(VoidRefundLog.created_at <= datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1))
    if min_amount:
        query = query.filter(VoidRefundLog.voided_refunded_amount >= min_amount)

    logs = query.order_by(VoidRefundLog.created_at.desc()).limit(200).all()

    total_voided = sum(float(l.voided_refunded_amount or 0) for l in logs if l.action_type == 'void')
    total_refunded = sum(float(l.voided_refunded_amount or 0) for l in logs if l.action_type in ['refund', 'partial_refund'])

    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()

    return render_template('void_refund_controls/logs.html',
                         logs=logs,
                         total_voided=total_voided,
                         total_refunded=total_refunded,
                         users=users,
                         user_id=user_id,
                         action_type=action_type,
                         from_date=from_date,
                         to_date=to_date,
                         min_amount=min_amount)


@bp.route('/summary')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def summary():
    """Void/Refund summary report"""
    location = get_current_location()

    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    if not from_date:
        from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')

    start_date = datetime.strptime(from_date, '%Y-%m-%d')
    end_date = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)

    base_filter = [
        VoidRefundLog.created_at >= start_date,
        VoidRefundLog.created_at < end_date
    ]
    if location and not current_user.is_global_admin:
        base_filter.append(VoidRefundLog.location_id == location.id)

    # Totals
    void_result = db.session.query(
        func.sum(VoidRefundLog.voided_refunded_amount).label('total'),
        func.count(VoidRefundLog.id).label('count')
    ).filter(*base_filter, VoidRefundLog.action_type == 'void').first()

    refund_result = db.session.query(
        func.sum(VoidRefundLog.voided_refunded_amount).label('total'),
        func.count(VoidRefundLog.id).label('count')
    ).filter(*base_filter, VoidRefundLog.action_type.in_(['refund', 'partial_refund'])).first()

    total_void_amount = float(void_result.total or 0)
    total_void_count = void_result.count or 0
    total_refund_amount = float(refund_result.total or 0)
    total_refund_count = refund_result.count or 0

    # By user
    by_user = db.session.query(
        User.full_name,
        VoidRefundLog.action_type,
        func.sum(VoidRefundLog.voided_refunded_amount).label('total'),
        func.count(VoidRefundLog.id).label('count')
    ).join(VoidRefundLog.user).filter(*base_filter).group_by(
        User.id, VoidRefundLog.action_type
    ).order_by(func.sum(VoidRefundLog.voided_refunded_amount).desc()).all()

    # By reason
    by_reason = db.session.query(
        VoidRefundLog.reason,
        VoidRefundLog.action_type,
        func.sum(VoidRefundLog.voided_refunded_amount).label('total'),
        func.count(VoidRefundLog.id).label('count')
    ).filter(*base_filter).group_by(
        VoidRefundLog.reason, VoidRefundLog.action_type
    ).order_by(func.sum(VoidRefundLog.voided_refunded_amount).desc()).all()

    # By day
    by_day = db.session.query(
        func.date(VoidRefundLog.created_at).label('date'),
        VoidRefundLog.action_type,
        func.sum(VoidRefundLog.voided_refunded_amount).label('total'),
        func.count(VoidRefundLog.id).label('count')
    ).filter(*base_filter).group_by(
        func.date(VoidRefundLog.created_at), VoidRefundLog.action_type
    ).order_by(func.date(VoidRefundLog.created_at)).all()

    # High-value voids/refunds
    high_value = VoidRefundLog.query.filter(
        *base_filter,
        VoidRefundLog.voided_refunded_amount >= 5000
    ).order_by(VoidRefundLog.voided_refunded_amount.desc()).limit(20).all()

    # Timing analysis (how long after sale)
    quick_voids = VoidRefundLog.query.filter(
        *base_filter,
        VoidRefundLog.action_type == 'void',
        VoidRefundLog.hours_since_sale < 1
    ).count()

    same_day_voids = VoidRefundLog.query.filter(
        *base_filter,
        VoidRefundLog.action_type == 'void',
        VoidRefundLog.hours_since_sale < 24
    ).count()

    return render_template('void_refund_controls/summary.html',
                         from_date=from_date,
                         to_date=to_date,
                         total_void_amount=total_void_amount,
                         total_void_count=total_void_count,
                         total_refund_amount=total_refund_amount,
                         total_refund_count=total_refund_count,
                         by_user=by_user,
                         by_reason=by_reason,
                         by_day=by_day,
                         high_value=high_value,
                         quick_voids=quick_voids,
                         same_day_voids=same_day_voids)


# ============================================================================
# API ENDPOINTS FOR POS
# ============================================================================

@bp.route('/api/check-void', methods=['POST'])
@login_required
def check_void_limit():
    """Check if user can void a sale - called from POS"""
    data = request.get_json()

    sale_id = data.get('sale_id')
    sale_total = Decimal(str(data.get('sale_total', 0)))
    sale_date_str = data.get('sale_date')

    if sale_date_str:
        sale_date = datetime.strptime(sale_date_str, '%Y-%m-%d %H:%M:%S')
    else:
        sale_date = datetime.utcnow()

    hours_since_sale = (datetime.utcnow() - sale_date).total_seconds() / 3600

    limit = VoidRefundLimit.query.filter_by(role=current_user.role, is_active=True).first()

    result = {
        'allowed': True,
        'requires_approval': False,
        'message': '',
        'hours_since_sale': hours_since_sale
    }

    # Managers/admins can void without limit by default
    if current_user.role in ['admin', 'manager'] or current_user.is_global_admin:
        return jsonify(result)

    if not limit:
        result['allowed'] = False
        result['message'] = 'No void/refund permissions configured for your role.'
        return jsonify(result)

    if not limit.can_void_sale:
        result['allowed'] = False
        result['message'] = 'You do not have permission to void sales.'
        return jsonify(result)

    # Check time limit
    if limit.void_time_limit_hours and hours_since_sale > limit.void_time_limit_hours:
        result['allowed'] = False
        result['message'] = f'Sale is too old to void. Maximum {limit.void_time_limit_hours} hours allowed.'
        return jsonify(result)

    # Check amount limit
    if limit.max_void_amount and sale_total > limit.max_void_amount:
        if limit.void_requires_approval_above:
            result['requires_approval'] = True
            result['message'] = f'Void amount exceeds your limit. Manager approval required.'
        else:
            result['allowed'] = False
            result['message'] = f'Maximum void amount is Rs. {limit.max_void_amount}'
        return jsonify(result)

    # Check approval threshold
    if limit.void_requires_approval_above and sale_total > limit.void_requires_approval_above:
        result['requires_approval'] = True
        result['message'] = 'Manager approval required for this void.'
        return jsonify(result)

    # Check daily limits
    if limit.max_daily_void_count or limit.max_daily_void_amount:
        today_start = datetime.combine(date.today(), datetime.min.time())
        today_logs = VoidRefundLog.query.filter(
            VoidRefundLog.user_id == current_user.id,
            VoidRefundLog.action_type == 'void',
            VoidRefundLog.created_at >= today_start
        ).all()

        if limit.max_daily_void_count and len(today_logs) >= limit.max_daily_void_count:
            result['allowed'] = False
            result['message'] = f'Daily void limit reached ({limit.max_daily_void_count})'
            return jsonify(result)

        if limit.max_daily_void_amount:
            today_total = sum(float(l.voided_refunded_amount or 0) for l in today_logs)
            if today_total + float(sale_total) > float(limit.max_daily_void_amount):
                result['allowed'] = False
                result['message'] = f'Daily void amount limit reached (Rs. {limit.max_daily_void_amount})'
                return jsonify(result)

    return jsonify(result)


@bp.route('/api/check-refund', methods=['POST'])
@login_required
def check_refund_limit():
    """Check if user can process a refund - called from POS"""
    data = request.get_json()

    refund_amount = Decimal(str(data.get('refund_amount', 0)))
    sale_total = Decimal(str(data.get('sale_total', 0)))
    sale_date_str = data.get('sale_date')
    reason = data.get('reason', '')

    if sale_date_str:
        sale_date = datetime.strptime(sale_date_str, '%Y-%m-%d %H:%M:%S')
    else:
        sale_date = datetime.utcnow()

    days_since_sale = (datetime.utcnow() - sale_date).days

    limit = VoidRefundLimit.query.filter_by(role=current_user.role, is_active=True).first()

    result = {
        'allowed': True,
        'requires_approval': False,
        'message': '',
        'days_since_sale': days_since_sale
    }

    # Managers/admins can refund without limit by default
    if current_user.role in ['admin', 'manager'] or current_user.is_global_admin:
        return jsonify(result)

    if not limit:
        result['allowed'] = False
        result['message'] = 'No void/refund permissions configured for your role.'
        return jsonify(result)

    if not limit.can_refund:
        result['allowed'] = False
        result['message'] = 'You do not have permission to process refunds.'
        return jsonify(result)

    # Check time limit
    if limit.refund_time_limit_days and days_since_sale > limit.refund_time_limit_days:
        result['allowed'] = False
        result['message'] = f'Sale is too old to refund. Maximum {limit.refund_time_limit_days} days allowed.'
        return jsonify(result)

    # Check amount limit
    if limit.max_refund_amount and refund_amount > limit.max_refund_amount:
        if limit.refund_requires_approval_above:
            result['requires_approval'] = True
            result['message'] = 'Refund amount exceeds your limit. Manager approval required.'
        else:
            result['allowed'] = False
            result['message'] = f'Maximum refund amount is Rs. {limit.max_refund_amount}'
        return jsonify(result)

    # Check approval threshold
    if limit.refund_requires_approval_above and refund_amount > limit.refund_requires_approval_above:
        result['requires_approval'] = True
        result['message'] = 'Manager approval required for this refund.'
        return jsonify(result)

    # Check reason requirement
    if limit.requires_reason and not reason:
        result['allowed'] = False
        result['message'] = 'Refund reason is required.'
        return jsonify(result)

    # Check allowed reasons
    if limit.allowed_refund_reasons and reason:
        allowed = limit.get_allowed_reasons()
        if allowed and reason not in allowed:
            result['allowed'] = False
            result['message'] = f'Reason "{reason}" is not allowed.'
            return jsonify(result)

    # Check daily limits
    if limit.max_daily_refund_count or limit.max_daily_refund_amount:
        today_start = datetime.combine(date.today(), datetime.min.time())
        today_logs = VoidRefundLog.query.filter(
            VoidRefundLog.user_id == current_user.id,
            VoidRefundLog.action_type.in_(['refund', 'partial_refund']),
            VoidRefundLog.created_at >= today_start
        ).all()

        if limit.max_daily_refund_count and len(today_logs) >= limit.max_daily_refund_count:
            result['allowed'] = False
            result['message'] = f'Daily refund limit reached ({limit.max_daily_refund_count})'
            return jsonify(result)

        if limit.max_daily_refund_amount:
            today_total = sum(float(l.voided_refunded_amount or 0) for l in today_logs)
            if today_total + float(refund_amount) > float(limit.max_daily_refund_amount):
                result['allowed'] = False
                result['message'] = f'Daily refund amount limit reached (Rs. {limit.max_daily_refund_amount})'
                return jsonify(result)

    return jsonify(result)


@bp.route('/api/request-approval', methods=['POST'])
@login_required
def request_approval():
    """Request void/refund approval from manager"""
    data = request.get_json()

    location = get_current_location()
    if not location:
        return jsonify({'success': False, 'error': 'Location not set'})

    approval = VoidRefundApproval(
        sale_id=data.get('sale_id'),
        request_type=data.get('request_type', 'void'),
        requested_by=current_user.id,
        location_id=location.id,
        amount=Decimal(str(data.get('amount', 0))),
        original_sale_total=Decimal(str(data.get('sale_total', 0))),
        reason=data.get('reason', 'Other'),
        reason_details=data.get('reason_details', ''),
        expires_at=datetime.utcnow() + timedelta(minutes=30)
    )

    approval.generate_approval_code()

    db.session.add(approval)
    db.session.commit()

    return jsonify({
        'success': True,
        'approval_id': approval.id,
        'approval_code': approval.approval_code,
        'message': f'Ask manager to enter code: {approval.approval_code}'
    })


@bp.route('/api/log', methods=['POST'])
@login_required
def log_void_refund():
    """Log a void/refund action - called after processing"""
    data = request.get_json()

    location = get_current_location()
    sale_date = None
    if data.get('sale_date'):
        sale_date = datetime.strptime(data['sale_date'], '%Y-%m-%d %H:%M:%S')

    hours_since = None
    if sale_date:
        hours_since = (datetime.utcnow() - sale_date).total_seconds() / 3600

    log = VoidRefundLog(
        sale_id=data.get('sale_id'),
        return_id=data.get('return_id'),
        action_type=data.get('action_type', 'void'),
        user_id=current_user.id,
        location_id=location.id if location else None,
        sale_number=data.get('sale_number'),
        sale_date=sale_date,
        original_amount=Decimal(str(data.get('original_amount', 0))),
        voided_refunded_amount=Decimal(str(data.get('amount', 0))),
        hours_since_sale=hours_since,
        reason=data.get('reason', 'Other'),
        reason_details=data.get('reason_details'),
        required_approval=data.get('required_approval', False),
        approval_id=data.get('approval_id'),
        approved_by=data.get('approved_by'),
        refund_method=data.get('refund_method'),
        customer_id=data.get('customer_id'),
        customer_name=data.get('customer_name'),
        items_json=json.dumps(data.get('items', [])) if data.get('items') else None
    )

    db.session.add(log)
    db.session.commit()

    return jsonify({'success': True, 'log_id': log.id})
