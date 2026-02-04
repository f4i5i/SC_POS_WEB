"""
Customer Credit Management Routes
Track customer credit sales, payments, and dues
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import func, and_, or_
from app.models import db, Customer, Sale
from app.models_extended import DuePayment, DuePaymentInstallment, CustomerCredit
from app.utils.permissions import permission_required, Permissions
from app.utils.location_context import get_current_location

bp = Blueprint('customer_credit', __name__, url_prefix='/customer-credit')


# ============================================================================
# DASHBOARD
# ============================================================================

@bp.route('/')
@login_required
@permission_required(Permissions.CUSTOMER_VIEW)
def index():
    """Customer credit management dashboard"""
    location = get_current_location()
    today = date.today()

    # Get summary stats
    total_receivables = db.session.query(
        func.coalesce(func.sum(DuePayment.due_amount), 0)
    ).filter(DuePayment.status != 'paid').scalar() or Decimal('0')

    overdue_amount = db.session.query(
        func.coalesce(func.sum(DuePayment.due_amount), 0)
    ).filter(
        DuePayment.status != 'paid',
        DuePayment.due_date < today
    ).scalar() or Decimal('0')

    customers_with_dues = db.session.query(
        func.count(func.distinct(DuePayment.customer_id))
    ).filter(DuePayment.status != 'paid').scalar() or 0

    overdue_customers = db.session.query(
        func.count(func.distinct(DuePayment.customer_id))
    ).filter(
        DuePayment.status != 'paid',
        DuePayment.due_date < today
    ).scalar() or 0

    # Recent dues
    recent_dues = DuePayment.query.filter(
        DuePayment.status != 'paid'
    ).order_by(DuePayment.due_date.asc()).limit(10).all()

    # Recent payments received
    recent_payments = DuePaymentInstallment.query.order_by(
        DuePaymentInstallment.paid_at.desc()
    ).limit(10).all()

    return render_template('customer_credit/index.html',
                         total_receivables=total_receivables,
                         overdue_amount=overdue_amount,
                         customers_with_dues=customers_with_dues,
                         overdue_customers=overdue_customers,
                         recent_dues=recent_dues,
                         recent_payments=recent_payments,
                         today=today)


# ============================================================================
# DUE PAYMENTS LIST
# ============================================================================

@bp.route('/dues')
@login_required
@permission_required(Permissions.CUSTOMER_VIEW)
def dues_list():
    """List all customer dues"""
    status_filter = request.args.get('status', 'all')
    customer_id = request.args.get('customer_id', type=int)
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'due_date')

    today = date.today()

    query = DuePayment.query

    if status_filter == 'overdue':
        query = query.filter(DuePayment.status != 'paid', DuePayment.due_date < today)
    elif status_filter == 'pending':
        query = query.filter(DuePayment.status == 'pending')
    elif status_filter == 'partial':
        query = query.filter(DuePayment.status == 'partial')
    elif status_filter == 'paid':
        query = query.filter(DuePayment.status == 'paid')
    elif status_filter != 'all':
        query = query.filter(DuePayment.status != 'paid')

    if customer_id:
        query = query.filter(DuePayment.customer_id == customer_id)

    if search:
        query = query.join(Customer).filter(
            or_(
                Customer.name.ilike(f'%{search}%'),
                Customer.phone.ilike(f'%{search}%')
            )
        )

    if sort_by == 'amount':
        query = query.order_by(DuePayment.due_amount.desc())
    elif sort_by == 'customer':
        query = query.join(Customer).order_by(Customer.name)
    else:
        query = query.order_by(DuePayment.due_date.asc())

    dues = query.all()

    # Calculate totals
    total_due = sum(float(d.due_amount or 0) for d in dues if d.status != 'paid')
    total_overdue = sum(float(d.due_amount or 0) for d in dues if d.is_overdue)

    customers = Customer.query.order_by(Customer.name).all()

    return render_template('customer_credit/dues_list.html',
                         dues=dues,
                         total_due=total_due,
                         total_overdue=total_overdue,
                         status_filter=status_filter,
                         customer_id=customer_id,
                         search=search,
                         sort_by=sort_by,
                         customers=customers,
                         today=today)


# ============================================================================
# CUSTOMER LEDGER
# ============================================================================

@bp.route('/customer/<int:customer_id>')
@login_required
@permission_required(Permissions.CUSTOMER_VIEW)
def customer_ledger(customer_id):
    """View customer credit ledger"""
    customer = Customer.query.get_or_404(customer_id)
    today = date.today()

    # Get all dues for this customer
    dues = DuePayment.query.filter_by(customer_id=customer_id).order_by(
        DuePayment.due_date.desc()
    ).all()

    # Get all payments
    payments = DuePaymentInstallment.query.join(DuePayment).filter(
        DuePayment.customer_id == customer_id
    ).order_by(DuePaymentInstallment.paid_at.desc()).all()

    # Get store credits
    credits = CustomerCredit.query.filter_by(customer_id=customer_id).order_by(
        CustomerCredit.created_at.desc()
    ).all()

    # Calculate summary
    total_due = sum(float(d.due_amount or 0) for d in dues if d.status != 'paid')
    total_paid = sum(float(p.amount or 0) for p in payments)
    total_overdue = sum(float(d.due_amount or 0) for d in dues if d.is_overdue)
    store_credit = float(customer.account_balance or 0)

    return render_template('customer_credit/customer_ledger.html',
                         customer=customer,
                         dues=dues,
                         payments=payments,
                         credits=credits,
                         total_due=total_due,
                         total_paid=total_paid,
                         total_overdue=total_overdue,
                         store_credit=store_credit,
                         today=today)


# ============================================================================
# RECORD PAYMENT
# ============================================================================

@bp.route('/dues/<int:due_id>/pay', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.CUSTOMER_EDIT)
def record_payment(due_id):
    """Record payment against a due"""
    due = DuePayment.query.get_or_404(due_id)

    if request.method == 'POST':
        amount = request.form.get('amount', type=float)
        payment_method = request.form.get('payment_method', 'cash')
        reference = request.form.get('reference', '').strip()
        notes = request.form.get('notes', '').strip()

        if not amount or amount <= 0:
            flash('Invalid payment amount.', 'error')
            return redirect(url_for('customer_credit.record_payment', due_id=due_id))

        if Decimal(str(amount)) > due.due_amount:
            flash('Payment amount cannot exceed due amount.', 'error')
            return redirect(url_for('customer_credit.record_payment', due_id=due_id))

        # Create installment
        installment = DuePaymentInstallment(
            due_payment_id=due_id,
            amount=Decimal(str(amount)),
            payment_method=payment_method,
            reference=reference,
            received_by=current_user.id,
            notes=notes
        )
        db.session.add(installment)

        # Update due
        due.paid_amount = (due.paid_amount or Decimal('0')) + Decimal(str(amount))
        due.due_amount = due.total_amount - due.paid_amount

        if due.due_amount <= 0:
            due.status = 'paid'
        else:
            due.status = 'partial'

        # Update customer balance
        customer = due.customer
        customer.account_balance = (customer.account_balance or Decimal('0')) - Decimal(str(amount))

        db.session.commit()

        flash(f'Payment of Rs. {amount:,.2f} recorded successfully.', 'success')
        return redirect(url_for('customer_credit.customer_ledger', customer_id=due.customer_id))

    return render_template('customer_credit/record_payment.html', due=due)


# ============================================================================
# AGING REPORT
# ============================================================================

@bp.route('/aging-report')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def aging_report():
    """Receivables aging report"""
    today = date.today()

    # Get all unpaid dues
    dues = DuePayment.query.filter(DuePayment.status != 'paid').all()

    # Group by aging buckets
    buckets = {
        'current': [],    # Not yet due
        '1_30': [],       # 1-30 days overdue
        '31_60': [],      # 31-60 days overdue
        '61_90': [],      # 61-90 days overdue
        'over_90': []     # Over 90 days overdue
    }

    for due in dues:
        days_overdue = (today - due.due_date).days if due.due_date < today else 0

        due.days_overdue_calc = days_overdue

        if due.due_date >= today:
            buckets['current'].append(due)
        elif days_overdue <= 30:
            buckets['1_30'].append(due)
        elif days_overdue <= 60:
            buckets['31_60'].append(due)
        elif days_overdue <= 90:
            buckets['61_90'].append(due)
        else:
            buckets['over_90'].append(due)

    # Calculate totals
    totals = {
        key: sum(float(d.due_amount or 0) for d in items)
        for key, items in buckets.items()
    }

    grand_total = sum(totals.values())

    # Customer summary
    customer_totals = {}
    for due in dues:
        cid = due.customer_id
        if cid not in customer_totals:
            customer_totals[cid] = {
                'customer': due.customer,
                'total': Decimal('0'),
                'overdue': Decimal('0')
            }
        customer_totals[cid]['total'] += due.due_amount
        if due.is_overdue:
            customer_totals[cid]['overdue'] += due.due_amount

    # Sort customers by total due
    top_customers = sorted(
        customer_totals.values(),
        key=lambda x: float(x['total']),
        reverse=True
    )[:20]

    return render_template('customer_credit/aging_report.html',
                         buckets=buckets,
                         totals=totals,
                         grand_total=grand_total,
                         top_customers=top_customers,
                         today=today)


# ============================================================================
# COLLECTION REMINDERS
# ============================================================================

@bp.route('/reminders')
@login_required
@permission_required(Permissions.CUSTOMER_VIEW)
def reminders():
    """Collection reminders dashboard"""
    today = date.today()

    # Get overdue payments
    overdue = DuePayment.query.filter(
        DuePayment.status != 'paid',
        DuePayment.due_date < today
    ).order_by(DuePayment.due_date.asc()).all()

    # Get upcoming dues (next 7 days)
    upcoming = DuePayment.query.filter(
        DuePayment.status != 'paid',
        DuePayment.due_date >= today,
        DuePayment.due_date <= today + timedelta(days=7)
    ).order_by(DuePayment.due_date.asc()).all()

    # Calculate totals
    overdue_total = sum(float(d.due_amount or 0) for d in overdue)
    upcoming_total = sum(float(d.due_amount or 0) for d in upcoming)

    return render_template('customer_credit/reminders.html',
                         overdue=overdue,
                         upcoming=upcoming,
                         overdue_total=overdue_total,
                         upcoming_total=upcoming_total,
                         today=today)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@bp.route('/api/customer/<int:customer_id>/dues')
@login_required
def api_customer_dues(customer_id):
    """Get customer dues summary"""
    customer = Customer.query.get_or_404(customer_id)

    dues = DuePayment.query.filter(
        DuePayment.customer_id == customer_id,
        DuePayment.status != 'paid'
    ).all()

    return jsonify({
        'customer_id': customer_id,
        'customer_name': customer.name,
        'total_due': sum(float(d.due_amount or 0) for d in dues),
        'overdue_count': sum(1 for d in dues if d.is_overdue),
        'store_credit': float(customer.account_balance or 0),
        'dues': [{
            'id': d.id,
            'sale_id': d.sale_id,
            'total_amount': float(d.total_amount or 0),
            'paid_amount': float(d.paid_amount or 0),
            'due_amount': float(d.due_amount or 0),
            'due_date': d.due_date.isoformat() if d.due_date else None,
            'is_overdue': d.is_overdue,
            'days_overdue': d.days_overdue,
            'status': d.status
        } for d in dues]
    })


@bp.route('/api/summary')
@login_required
def api_summary():
    """Get overall credit summary"""
    today = date.today()

    total_receivables = db.session.query(
        func.coalesce(func.sum(DuePayment.due_amount), 0)
    ).filter(DuePayment.status != 'paid').scalar() or 0

    overdue_amount = db.session.query(
        func.coalesce(func.sum(DuePayment.due_amount), 0)
    ).filter(
        DuePayment.status != 'paid',
        DuePayment.due_date < today
    ).scalar() or 0

    overdue_count = DuePayment.query.filter(
        DuePayment.status != 'paid',
        DuePayment.due_date < today
    ).count()

    return jsonify({
        'total_receivables': float(total_receivables),
        'overdue_amount': float(overdue_amount),
        'overdue_count': overdue_count
    })
