"""
Returns Management Routes
Handle product returns, refunds, and exchanges
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, date
from decimal import Decimal
from app.models import db, Sale, SaleItem, Product, Customer, StockMovement, LocationStock
from app.models_extended import Return, ReturnItem, CustomerCredit
from app.utils.permissions import permission_required, Permissions
from app.utils.feature_flags import feature_required, Features

bp = Blueprint('returns', __name__)


def generate_return_number():
    """Generate unique return number"""
    today = date.today().strftime('%Y%m%d')
    last_return = Return.query.filter(
        Return.return_number.like(f'RET-{today}%')
    ).order_by(Return.return_number.desc()).first()

    if last_return:
        last_num = int(last_return.return_number.split('-')[-1])
        new_num = last_num + 1
    else:
        new_num = 1

    return f'RET-{today}-{new_num:04d}'


@bp.route('/')
@login_required
@feature_required(Features.RETURNS_MANAGEMENT)
def index():
    """List all returns - filtered by location for store managers"""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    return_type = request.args.get('type', '')

    query = Return.query

    # Filter by location for store managers
    if not current_user.is_global_admin and current_user.role in ['manager', 'kiosk_manager', 'cashier']:
        if current_user.location_id:
            query = query.filter(Return.location_id == current_user.location_id)
        else:
            query = query.filter(False)  # No location = no data

    if status:
        query = query.filter_by(status=status)
    if return_type:
        query = query.filter_by(return_type=return_type)

    returns = query.order_by(Return.return_date.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    # Stats - also filter by location for store managers
    today = date.today()
    stats_query = Return.query
    if not current_user.is_global_admin and current_user.role in ['manager', 'kiosk_manager', 'cashier']:
        if current_user.location_id:
            stats_query = stats_query.filter(Return.location_id == current_user.location_id)

    today_returns = stats_query.filter(
        db.func.date(Return.return_date) == today
    ).count()

    pending_returns = stats_query.filter_by(status='pending').count()

    total_returns = stats_query.count()

    # Calculate total refunded amount
    total_refunded = db.session.query(
        db.func.coalesce(db.func.sum(Return.refund_amount), 0)
    ).filter(Return.status == 'completed')
    if not current_user.is_global_admin and current_user.role in ['manager', 'kiosk_manager', 'cashier']:
        if current_user.location_id:
            total_refunded = total_refunded.filter(Return.location_id == current_user.location_id)
    total_refunded = total_refunded.scalar() or 0

    return render_template('returns/index.html',
                         returns=returns,
                         today_returns=today_returns,
                         pending_returns=pending_returns,
                         total_returns=total_returns,
                         total_refunded=total_refunded)


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@feature_required(Features.RETURNS_MANAGEMENT)
def create():
    """Create new return"""
    sale_id = request.args.get('sale_id', type=int)
    sale = None

    if sale_id:
        sale = Sale.query.get_or_404(sale_id)

    if request.method == 'POST':
        try:
            data = request.get_json()

            sale = Sale.query.get_or_404(data.get('sale_id'))

            ret = Return(
                return_number=generate_return_number(),
                sale_id=sale.id,
                customer_id=sale.customer_id,
                return_type=data.get('return_type'),  # refund, exchange, credit
                return_reason=data.get('return_reason'),
                notes=data.get('notes'),
                processed_by=current_user.id,
                location_id=current_user.location_id,  # Link to user's location
                status='pending'
            )

            db.session.add(ret)
            db.session.flush()

            # Add return items
            total_amount = Decimal('0')
            for item_data in data.get('items', []):
                sale_item = SaleItem.query.get(item_data['sale_item_id'])
                if sale_item:
                    qty = int(item_data['quantity'])
                    subtotal = qty * sale_item.unit_price

                    return_item = ReturnItem(
                        return_id=ret.id,
                        sale_item_id=sale_item.id,
                        product_id=sale_item.product_id,
                        quantity=qty,
                        unit_price=sale_item.unit_price,
                        subtotal=subtotal,
                        condition=item_data.get('condition', 'good'),
                        restock=item_data.get('restock', True),
                        notes=item_data.get('notes')
                    )
                    db.session.add(return_item)
                    total_amount += subtotal

            ret.total_amount = total_amount

            # Set refund/credit amount based on return type
            if ret.return_type == 'refund':
                ret.refund_amount = total_amount
            elif ret.return_type == 'credit':
                ret.credit_issued = total_amount

            db.session.commit()

            return jsonify({
                'success': True,
                'return_number': ret.return_number,
                'id': ret.id
            })

        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400

    return render_template('returns/create.html', sale=sale)


@bp.route('/view/<int:return_id>')
@login_required
@feature_required(Features.RETURNS_MANAGEMENT)
def view(return_id):
    """View return details"""
    ret = Return.query.get_or_404(return_id)
    items = ret.items.all()

    return render_template('returns/view.html',
                         return_obj=ret,
                         return_order=ret,
                         items=items)


@bp.route('/approve/<int:return_id>', methods=['POST'])
@login_required
@feature_required(Features.RETURNS_MANAGEMENT)
def approve(return_id):
    """Approve return"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    ret = Return.query.get_or_404(return_id)

    if ret.status != 'pending':
        return jsonify({'success': False, 'error': 'Return is not pending'}), 400

    ret.status = 'approved'
    ret.approved_by = current_user.id
    db.session.commit()

    return jsonify({'success': True})


@bp.route('/complete/<int:return_id>', methods=['POST'])
@login_required
@feature_required(Features.RETURNS_MANAGEMENT)
def complete(return_id):
    """Complete return - process refund/credit and restock"""
    ret = Return.query.get_or_404(return_id)

    if ret.status not in ['pending', 'approved']:
        return jsonify({'success': False, 'error': 'Return cannot be completed'}), 400

    try:
        # Process items
        for item in ret.items:
            if item.restock:
                # Restock to location stock if location is set
                location_id = ret.location_id or current_user.location_id
                if location_id:
                    # Update location stock
                    location_stock = LocationStock.query.filter_by(
                        location_id=location_id,
                        product_id=item.product_id
                    ).first()
                    if location_stock:
                        location_stock.quantity += item.quantity
                    else:
                        # Create location stock if it doesn't exist
                        location_stock = LocationStock(
                            location_id=location_id,
                            product_id=item.product_id,
                            quantity=item.quantity
                        )
                        db.session.add(location_stock)
                else:
                    # Fallback to global product quantity for non-location users
                    product = Product.query.get(item.product_id)
                    if product:
                        product.quantity += item.quantity

                # Create stock movement
                movement = StockMovement(
                    product_id=item.product_id,
                    user_id=current_user.id,
                    movement_type='return',
                    quantity=item.quantity,
                    reference=ret.return_number,
                    location_id=location_id,
                    notes=f'Return from sale {ret.sale.sale_number}'
                )
                db.session.add(movement)

        # Process credit if applicable
        if ret.return_type == 'credit' and ret.credit_issued > 0:
            customer = ret.customer
            if customer:
                # Get current credit balance
                last_credit = CustomerCredit.query.filter_by(
                    customer_id=customer.id
                ).order_by(CustomerCredit.created_at.desc()).first()

                current_balance = last_credit.balance_after if last_credit else Decimal('0')
                new_balance = current_balance + ret.credit_issued

                credit = CustomerCredit(
                    customer_id=customer.id,
                    credit_type='return_credit',
                    reference_id=ret.id,
                    amount=ret.credit_issued,
                    balance_after=new_balance,
                    description=f'Credit from return {ret.return_number}',
                    created_by=current_user.id
                )
                db.session.add(credit)

        ret.status = 'completed'
        ret.completed_at = datetime.utcnow()
        db.session.commit()

        return jsonify({'success': True, 'message': 'Return completed successfully'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/reject/<int:return_id>', methods=['POST'])
@login_required
@feature_required(Features.RETURNS_MANAGEMENT)
def reject(return_id):
    """Reject return"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    ret = Return.query.get_or_404(return_id)
    data = request.get_json()

    ret.status = 'rejected'
    ret.notes = (ret.notes or '') + f'\n\nRejection reason: {data.get("reason", "Not specified")}'
    db.session.commit()

    return jsonify({'success': True})


@bp.route('/find-sale', methods=['GET'])
@login_required
@feature_required(Features.RETURNS_MANAGEMENT)
def find_sale():
    """Find sale for return by sale number or phone - filtered by location"""
    query = request.args.get('q', '').strip()

    if not query:
        return jsonify({'sales': []})

    # Search by sale number
    sales_query = Sale.query.filter(
        db.or_(
            Sale.sale_number.ilike(f'%{query}%'),
            Sale.customer.has(Customer.phone.ilike(f'%{query}%'))
        ),
        Sale.status == 'completed'
    )

    # Filter by location for store managers
    if not current_user.is_global_admin and current_user.role in ['manager', 'kiosk_manager', 'cashier']:
        if current_user.location_id:
            sales_query = sales_query.filter(Sale.location_id == current_user.location_id)

    sales = sales_query.order_by(Sale.sale_date.desc()).limit(10).all()

    results = []
    for sale in sales:
        results.append({
            'id': sale.id,
            'sale_number': sale.sale_number,
            'sale_date': sale.sale_date.strftime('%Y-%m-%d %H:%M'),
            'total': float(sale.total),
            'customer_name': sale.customer.name if sale.customer else 'Walk-in',
            'items_count': sale.items.count()
        })

    return jsonify({'sales': results})


@bp.route('/sale-items/<int:sale_id>')
@login_required
@feature_required(Features.RETURNS_MANAGEMENT)
def get_sale_items(sale_id):
    """Get items from a sale for return selection"""
    sale = Sale.query.get_or_404(sale_id)

    items = []
    for item in sale.items:
        # Calculate already returned quantity for this item
        returned_qty = db.session.query(db.func.sum(ReturnItem.quantity)).filter(
            ReturnItem.sale_item_id == item.id,
            ReturnItem.return_order.has(Return.status.in_(['pending', 'approved', 'completed']))
        ).scalar() or 0

        returnable_qty = item.quantity - returned_qty

        items.append({
            'id': item.id,
            'product_id': item.product_id,
            'product_name': item.product.name,
            'product_code': item.product.code,
            'quantity': item.quantity,
            'returned_quantity': returned_qty,
            'returnable_quantity': returnable_qty,
            'unit_price': float(item.unit_price),
            'subtotal': float(item.subtotal)
        })

    return jsonify({
        'sale': {
            'id': sale.id,
            'sale_number': sale.sale_number,
            'sale_date': sale.sale_date.strftime('%Y-%m-%d %H:%M'),
            'customer_name': sale.customer.name if sale.customer else 'Walk-in'
        },
        'items': items
    })


# ============================================================
# CUSTOMER STORE CREDIT
# ============================================================

@bp.route('/credits')
@login_required
@feature_required(Features.CUSTOMER_CREDIT)
def customer_credits():
    """View customer credits"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')

    # Get customers with credit balance
    query = Customer.query.filter(Customer.is_active == True)

    if search:
        query = query.filter(
            db.or_(
                Customer.name.ilike(f'%{search}%'),
                Customer.phone.ilike(f'%{search}%')
            )
        )

    customers = query.order_by(Customer.name).paginate(
        page=page, per_page=20, error_out=False
    )

    # Calculate credit balances - create credit objects for template
    credits = []
    total_credits = Decimal('0')
    for customer in customers.items:
        last_credit = CustomerCredit.query.filter_by(
            customer_id=customer.id
        ).order_by(CustomerCredit.created_at.desc()).first()

        balance = last_credit.balance_after if last_credit else Decimal('0')
        if balance > 0:
            credits.append({
                'customer': customer,
                'customer_id': customer.id,
                'balance': balance,
                'updated_at': last_credit.created_at if last_credit else None
            })
            total_credits += balance

    customers_with_credit = len(credits)

    return render_template('returns/credits.html',
                         customers=customers,
                         credits=credits,
                         total_credits=total_credits,
                         customers_with_credit=customers_with_credit)


@bp.route('/credits/<int:customer_id>')
@login_required
@feature_required(Features.CUSTOMER_CREDIT)
def customer_credit_history(customer_id):
    """View customer credit history"""
    customer = Customer.query.get_or_404(customer_id)
    credits = CustomerCredit.query.filter_by(
        customer_id=customer_id
    ).order_by(CustomerCredit.created_at.desc()).all()

    # Current balance
    balance = credits[0].balance_after if credits else Decimal('0')

    return render_template('returns/credit_history.html',
                         customer=customer,
                         credits=credits,
                         balance=balance)


@bp.route('/credits/adjust', methods=['POST'])
@login_required
@feature_required(Features.CUSTOMER_CREDIT)
def adjust_credit():
    """Manually adjust customer credit"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    customer_id = data.get('customer_id')
    amount = Decimal(str(data.get('amount', 0)))
    description = data.get('description', 'Manual adjustment')

    customer = Customer.query.get_or_404(customer_id)

    # Get current balance
    last_credit = CustomerCredit.query.filter_by(
        customer_id=customer_id
    ).order_by(CustomerCredit.created_at.desc()).first()

    current_balance = last_credit.balance_after if last_credit else Decimal('0')
    new_balance = current_balance + amount

    credit = CustomerCredit(
        customer_id=customer_id,
        credit_type='adjustment',
        amount=amount,
        balance_after=new_balance,
        description=description,
        created_by=current_user.id
    )
    db.session.add(credit)
    db.session.commit()

    return jsonify({
        'success': True,
        'new_balance': float(new_balance)
    })


@bp.route('/credits/use', methods=['POST'])
@login_required
@feature_required(Features.CUSTOMER_CREDIT)
def use_credit():
    """Use customer credit for a sale"""
    data = request.get_json()
    customer_id = data.get('customer_id')
    amount = Decimal(str(data.get('amount', 0)))
    sale_id = data.get('sale_id')

    customer = Customer.query.get_or_404(customer_id)

    # Get current balance
    last_credit = CustomerCredit.query.filter_by(
        customer_id=customer_id
    ).order_by(CustomerCredit.created_at.desc()).first()

    current_balance = last_credit.balance_after if last_credit else Decimal('0')

    if amount > current_balance:
        return jsonify({'success': False, 'error': 'Insufficient credit balance'}), 400

    new_balance = current_balance - amount

    credit = CustomerCredit(
        customer_id=customer_id,
        credit_type='payment',
        reference_id=sale_id,
        amount=-amount,
        balance_after=new_balance,
        description=f'Used for sale',
        created_by=current_user.id
    )
    db.session.add(credit)
    db.session.commit()

    return jsonify({
        'success': True,
        'amount_used': float(amount),
        'remaining_balance': float(new_balance)
    })
