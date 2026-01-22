"""
Supplier Payment Routes
Handles supplier payments, ledger, and payment reminders
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from decimal import Decimal
from datetime import datetime, date, timedelta
from app.models import db, Supplier, PurchaseOrder
from app.models_extended import SupplierPayment, SupplierLedger
from app.utils.permissions import permission_required, Permissions

bp = Blueprint('supplier_payments', __name__, url_prefix='/supplier-payments')


def generate_payment_number():
    """Generate unique payment number"""
    today = datetime.utcnow()
    prefix = f"PAY-{today.strftime('%Y%m%d')}"

    last_payment = SupplierPayment.query.filter(
        SupplierPayment.payment_number.like(f'{prefix}%')
    ).order_by(SupplierPayment.id.desc()).first()

    if last_payment:
        try:
            last_num = int(last_payment.payment_number.split('-')[-1])
            new_num = last_num + 1
        except:
            new_num = 1
    else:
        new_num = 1

    return f"{prefix}-{new_num:04d}"


@bp.route('/')
@login_required
@permission_required(Permissions.SUPPLIER_VIEW)
def index():
    """List all supplier payments"""
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('ITEMS_PER_PAGE', 20)
    supplier_id = request.args.get('supplier_id', type=int)
    status = request.args.get('status', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    payment_method = request.args.get('payment_method', '')

    query = SupplierPayment.query

    if supplier_id:
        query = query.filter_by(supplier_id=supplier_id)
    if status:
        query = query.filter_by(status=status)
    if payment_method:
        query = query.filter_by(payment_method=payment_method)
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(SupplierPayment.payment_date >= from_date)
        except:
            pass
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(SupplierPayment.payment_date <= to_date)
        except:
            pass

    payments = query.order_by(SupplierPayment.payment_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()

    # Calculate totals for displayed payments
    total_amount = sum(float(p.amount or 0) for p in payments.items)

    return render_template('supplier_payments/index.html',
                          payments=payments,
                          suppliers=suppliers,
                          total_amount=total_amount)


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.SUPPLIER_EDIT)
def create():
    """Create new supplier payment"""
    if request.method == 'POST':
        try:
            supplier_id = request.form.get('supplier_id', type=int)
            amount = Decimal(request.form.get('amount', 0))
            payment_method = request.form.get('payment_method')
            payment_date_str = request.form.get('payment_date')
            reference_number = request.form.get('reference_number', '').strip()
            po_id = request.form.get('purchase_order_id', type=int) or None
            notes = request.form.get('notes', '').strip()

            if not supplier_id or amount <= 0:
                flash('Invalid supplier or amount', 'danger')
                return redirect(url_for('supplier_payments.create'))

            payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()

            # Generate payment number
            payment_number = generate_payment_number()

            # Create payment
            payment = SupplierPayment(
                payment_number=payment_number,
                supplier_id=supplier_id,
                purchase_order_id=po_id,
                amount=amount,
                payment_method=payment_method,
                payment_date=payment_date,
                reference_number=reference_number,
                notes=notes,
                created_by=current_user.id,
                status='completed'
            )
            db.session.add(payment)
            db.session.flush()

            # Update supplier balance
            supplier = Supplier.query.get(supplier_id)
            supplier.current_balance = (supplier.current_balance or Decimal('0')) - amount
            supplier.last_payment_date = payment_date

            # Update PO payment status if linked
            if po_id:
                po = PurchaseOrder.query.get(po_id)
                if po:
                    po.amount_paid = (po.amount_paid or Decimal('0')) + amount
                    po.amount_due = (po.total or Decimal('0')) - po.amount_paid
                    if po.amount_due <= 0:
                        po.payment_status = 'paid'
                    else:
                        po.payment_status = 'partial'

            # Create ledger entry
            ledger_entry = SupplierLedger(
                supplier_id=supplier_id,
                transaction_type='payment',
                reference_id=payment.id,
                reference_number=payment_number,
                credit=amount,
                balance=supplier.current_balance,
                description=f'Payment via {payment_method}' + (f' - Ref: {reference_number}' if reference_number else ''),
                transaction_date=datetime.utcnow()
            )
            db.session.add(ledger_entry)

            db.session.commit()
            flash(f'Payment {payment_number} recorded successfully', 'success')
            return redirect(url_for('supplier_payments.view', id=payment.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error recording payment: {str(e)}', 'danger')

    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()

    # Get suppliers with outstanding balance
    suppliers_with_dues = []
    for s in suppliers:
        if s.current_balance and s.current_balance > 0:
            suppliers_with_dues.append(s)

    return render_template('supplier_payments/create.html',
                          suppliers=suppliers,
                          suppliers_with_dues=suppliers_with_dues)


@bp.route('/<int:id>')
@login_required
@permission_required(Permissions.SUPPLIER_VIEW)
def view(id):
    """View payment details"""
    payment = SupplierPayment.query.get_or_404(id)
    return render_template('supplier_payments/view.html', payment=payment)


@bp.route('/<int:id>/void', methods=['POST'])
@login_required
@permission_required(Permissions.SUPPLIER_EDIT)
def void_payment(id):
    """Void a payment"""
    payment = SupplierPayment.query.get_or_404(id)

    if payment.status == 'cancelled':
        flash('Payment is already voided', 'warning')
        return redirect(url_for('supplier_payments.view', id=id))

    try:
        # Reverse the balance changes
        supplier = payment.supplier
        supplier.current_balance = (supplier.current_balance or Decimal('0')) + payment.amount

        # Reverse PO payment if linked
        if payment.purchase_order_id:
            po = payment.purchase_order
            if po:
                po.amount_paid = (po.amount_paid or Decimal('0')) - payment.amount
                po.amount_due = (po.total or Decimal('0')) - po.amount_paid
                if po.amount_paid <= 0:
                    po.payment_status = 'unpaid'
                elif po.amount_due > 0:
                    po.payment_status = 'partial'

        # Create reversal ledger entry
        ledger_entry = SupplierLedger(
            supplier_id=payment.supplier_id,
            transaction_type='adjustment',
            reference_id=payment.id,
            reference_number=f'VOID-{payment.payment_number}',
            debit=payment.amount,
            balance=supplier.current_balance,
            description=f'Payment voided: {payment.payment_number}',
            transaction_date=datetime.utcnow()
        )
        db.session.add(ledger_entry)

        payment.status = 'cancelled'

        db.session.commit()
        flash(f'Payment {payment.payment_number} has been voided', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error voiding payment: {str(e)}', 'danger')

    return redirect(url_for('supplier_payments.view', id=id))


@bp.route('/supplier/<int:supplier_id>/ledger')
@login_required
@permission_required(Permissions.SUPPLIER_VIEW)
def supplier_ledger(supplier_id):
    """View supplier ledger with running balance"""
    supplier = Supplier.query.get_or_404(supplier_id)

    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = SupplierLedger.query.filter_by(supplier_id=supplier_id)

    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(SupplierLedger.transaction_date >= from_date)
        except:
            pass
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(SupplierLedger.transaction_date <= to_date)
        except:
            pass

    entries = query.order_by(SupplierLedger.transaction_date.desc()).all()

    # Calculate totals
    total_debit = sum(float(e.debit or 0) for e in entries)
    total_credit = sum(float(e.credit or 0) for e in entries)

    # Get unpaid POs
    unpaid_pos = PurchaseOrder.query.filter(
        PurchaseOrder.supplier_id == supplier_id,
        PurchaseOrder.payment_status != 'paid',
        PurchaseOrder.status.in_(['ordered', 'partial', 'received'])
    ).order_by(PurchaseOrder.order_date).all()

    return render_template('supplier_payments/supplier_ledger.html',
                          supplier=supplier,
                          entries=entries,
                          total_debit=total_debit,
                          total_credit=total_credit,
                          unpaid_pos=unpaid_pos)


@bp.route('/supplier/<int:supplier_id>/statement')
@login_required
@permission_required(Permissions.SUPPLIER_VIEW)
def supplier_statement(supplier_id):
    """Generate printable supplier statement"""
    supplier = Supplier.query.get_or_404(supplier_id)

    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = SupplierLedger.query.filter_by(supplier_id=supplier_id)

    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(SupplierLedger.transaction_date >= from_date)
        except:
            pass
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(SupplierLedger.transaction_date <= to_date)
        except:
            pass

    entries = query.order_by(SupplierLedger.transaction_date).all()

    return render_template('supplier_payments/statement.html',
                          supplier=supplier,
                          entries=entries,
                          date_from=date_from,
                          date_to=date_to)


@bp.route('/reminders')
@login_required
@permission_required(Permissions.SUPPLIER_VIEW)
def reminders():
    """Payment reminders dashboard"""
    today = date.today()

    # Get suppliers with overdue payments
    overdue_suppliers = []
    upcoming_suppliers = []

    suppliers = Supplier.query.filter_by(is_active=True, reminder_enabled=True).all()

    for supplier in suppliers:
        if supplier.current_balance and supplier.current_balance > 0:
            # Find oldest unpaid PO
            oldest_unpaid = PurchaseOrder.query.filter(
                PurchaseOrder.supplier_id == supplier.id,
                PurchaseOrder.payment_status != 'paid',
                PurchaseOrder.status.in_(['ordered', 'partial', 'received'])
            ).order_by(PurchaseOrder.order_date).first()

            if oldest_unpaid:
                due_days = supplier.payment_due_days or 30
                due_date = oldest_unpaid.order_date.date() + timedelta(days=due_days)
                days_overdue = (today - due_date).days

                data = {
                    'supplier': supplier,
                    'amount_due': float(supplier.current_balance),
                    'due_date': due_date,
                    'days_overdue': days_overdue,
                    'oldest_po': oldest_unpaid
                }

                if days_overdue > 0:
                    overdue_suppliers.append(data)
                elif days_overdue >= -7:  # Due within 7 days
                    upcoming_suppliers.append(data)

    # Sort by urgency
    overdue_suppliers.sort(key=lambda x: x['days_overdue'], reverse=True)
    upcoming_suppliers.sort(key=lambda x: x['due_date'])

    # Summary stats
    total_overdue = sum(s['amount_due'] for s in overdue_suppliers)
    total_upcoming = sum(s['amount_due'] for s in upcoming_suppliers)

    return render_template('supplier_payments/reminders.html',
                          overdue_suppliers=overdue_suppliers,
                          upcoming_suppliers=upcoming_suppliers,
                          total_overdue=total_overdue,
                          total_upcoming=total_upcoming,
                          today=today)


# API Endpoints

@bp.route('/api/supplier/<int:supplier_id>/balance')
@login_required
def api_supplier_balance(supplier_id):
    """Get supplier current balance"""
    supplier = Supplier.query.get_or_404(supplier_id)
    return jsonify({
        'supplier_id': supplier_id,
        'name': supplier.name,
        'current_balance': float(supplier.current_balance or 0),
        'credit_limit': float(supplier.credit_limit or 0),
        'payment_due_days': supplier.payment_due_days or 30
    })


@bp.route('/api/supplier/<int:supplier_id>/unpaid-pos')
@login_required
def api_supplier_unpaid_pos(supplier_id):
    """Get unpaid POs for a supplier"""
    pos = PurchaseOrder.query.filter(
        PurchaseOrder.supplier_id == supplier_id,
        PurchaseOrder.payment_status != 'paid',
        PurchaseOrder.status.in_(['ordered', 'partial', 'received'])
    ).order_by(PurchaseOrder.order_date).all()

    return jsonify([{
        'id': po.id,
        'po_number': po.po_number,
        'order_date': po.order_date.strftime('%Y-%m-%d') if po.order_date else None,
        'total': float(po.total or 0),
        'amount_paid': float(po.amount_paid or 0),
        'amount_due': float(po.amount_due or 0),
        'payment_status': po.payment_status
    } for po in pos])


@bp.route('/api/overdue-count')
@login_required
def api_overdue_count():
    """Get count of overdue payments for badge"""
    today = date.today()
    count = 0

    suppliers = Supplier.query.filter_by(is_active=True, reminder_enabled=True).all()

    for supplier in suppliers:
        if supplier.current_balance and supplier.current_balance > 0:
            oldest_unpaid = PurchaseOrder.query.filter(
                PurchaseOrder.supplier_id == supplier.id,
                PurchaseOrder.payment_status != 'paid',
                PurchaseOrder.status.in_(['ordered', 'partial', 'received'])
            ).order_by(PurchaseOrder.order_date).first()

            if oldest_unpaid:
                due_days = supplier.payment_due_days or 30
                due_date = oldest_unpaid.order_date.date() + timedelta(days=due_days)
                if today > due_date:
                    count += 1

    return jsonify({'overdue_count': count})
