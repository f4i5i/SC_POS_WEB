"""
Promotions & Gift Vouchers Routes
Manage promotional offers and gift cards
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
import secrets
import string
from app.models import db
from app.models_extended import Promotion, PromotionUsage, GiftVoucher, GiftVoucherTransaction
from app.utils.permissions import permission_required, Permissions
from app.utils.feature_flags import feature_required, Features

bp = Blueprint('promotions', __name__)


def generate_promo_code(length=8):
    """Generate unique promotion code"""
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(secrets.choice(chars) for _ in range(length))
        if not Promotion.query.filter_by(code=code).first():
            return code


def generate_voucher_code():
    """Generate unique gift voucher code"""
    while True:
        code = 'GV-' + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
        if not GiftVoucher.query.filter_by(code=code).first():
            return code


# ============================================================
# PROMOTIONS
# ============================================================

@bp.route('/')
@login_required
@feature_required(Features.PROMOTIONS)
def index():
    """List all promotions"""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')

    query = Promotion.query

    if status == 'active':
        now = datetime.utcnow()
        query = query.filter(
            Promotion.is_active == True,
            Promotion.start_date <= now,
            Promotion.end_date >= now
        )
    elif status == 'expired':
        query = query.filter(Promotion.end_date < datetime.utcnow())
    elif status == 'upcoming':
        query = query.filter(Promotion.start_date > datetime.utcnow())

    promotions = query.order_by(Promotion.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    return render_template('promotions/index.html', promotions=promotions)


@bp.route('/add', methods=['GET', 'POST'])
@login_required
@feature_required(Features.PROMOTIONS)
def add():
    """Create new promotion"""
    if request.method == 'POST':
        try:
            promotion = Promotion(
                code=request.form.get('code') or generate_promo_code(),
                name=request.form.get('name'),
                description=request.form.get('description'),
                promotion_type=request.form.get('promotion_type'),
                discount_value=Decimal(request.form.get('discount_value', 0)),
                buy_quantity=request.form.get('buy_quantity', type=int),
                get_quantity=request.form.get('get_quantity', type=int),
                min_purchase=Decimal(request.form.get('min_purchase', 0)),
                max_discount=Decimal(request.form.get('max_discount', 0)) if request.form.get('max_discount') else None,
                start_date=datetime.strptime(request.form.get('start_date'), '%Y-%m-%dT%H:%M'),
                end_date=datetime.strptime(request.form.get('end_date'), '%Y-%m-%dT%H:%M'),
                usage_limit=request.form.get('usage_limit', type=int),
                usage_per_customer=request.form.get('usage_per_customer', 1, type=int),
                applies_to=request.form.get('applies_to', 'all'),
                is_active=True,
                created_by=current_user.id
            )

            db.session.add(promotion)
            db.session.commit()

            flash(f'Promotion "{promotion.name}" created with code: {promotion.code}', 'success')
            return redirect(url_for('promotions.index'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating promotion: {str(e)}', 'danger')

    return render_template('promotions/add.html')


@bp.route('/edit/<int:promotion_id>', methods=['GET', 'POST'])
@login_required
@feature_required(Features.PROMOTIONS)
def edit(promotion_id):
    """Edit promotion"""
    promotion = Promotion.query.get_or_404(promotion_id)

    if request.method == 'POST':
        try:
            promotion.name = request.form.get('name')
            promotion.description = request.form.get('description')
            promotion.promotion_type = request.form.get('promotion_type')
            promotion.discount_value = Decimal(request.form.get('discount_value', 0))
            promotion.buy_quantity = request.form.get('buy_quantity', type=int)
            promotion.get_quantity = request.form.get('get_quantity', type=int)
            promotion.min_purchase = Decimal(request.form.get('min_purchase', 0))
            promotion.max_discount = Decimal(request.form.get('max_discount', 0)) if request.form.get('max_discount') else None
            promotion.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%dT%H:%M')
            promotion.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%dT%H:%M')
            promotion.usage_limit = request.form.get('usage_limit', type=int)
            promotion.usage_per_customer = request.form.get('usage_per_customer', 1, type=int)

            db.session.commit()
            flash('Promotion updated successfully.', 'success')
            return redirect(url_for('promotions.index'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating promotion: {str(e)}', 'danger')

    return render_template('promotions/edit.html', promotion=promotion)


@bp.route('/toggle/<int:promo_id>', methods=['POST'])
@login_required
@feature_required(Features.PROMOTIONS)
def toggle_promotion(promo_id):
    """Toggle promotion active status"""
    promotion = Promotion.query.get_or_404(promo_id)
    promotion.is_active = not promotion.is_active
    db.session.commit()

    return jsonify({
        'success': True,
        'is_active': promotion.is_active
    })


@bp.route('/validate', methods=['POST'])
@login_required
@feature_required(Features.PROMOTIONS)
def validate_promo_code():
    """Validate a promotion code for POS"""
    data = request.get_json()
    code = data.get('code', '').upper()
    cart_total = Decimal(data.get('cart_total', 0))
    customer_id = data.get('customer_id')

    promotion = Promotion.query.filter_by(code=code).first()

    if not promotion:
        return jsonify({'valid': False, 'error': 'Invalid promotion code'})

    if not promotion.is_valid:
        return jsonify({'valid': False, 'error': 'This promotion has expired or is no longer active'})

    if promotion.min_purchase and cart_total < promotion.min_purchase:
        return jsonify({
            'valid': False,
            'error': f'Minimum purchase of Rs. {promotion.min_purchase} required'
        })

    # Check per-customer usage
    if customer_id and promotion.usage_per_customer:
        usage_count = PromotionUsage.query.filter_by(
            promotion_id=promotion.id,
            customer_id=customer_id
        ).count()
        if usage_count >= promotion.usage_per_customer:
            return jsonify({'valid': False, 'error': 'You have already used this promotion'})

    # Calculate discount
    discount_amount = 0
    if promotion.promotion_type == 'percentage':
        discount_amount = float(cart_total) * float(promotion.discount_value) / 100
        if promotion.max_discount:
            discount_amount = min(discount_amount, float(promotion.max_discount))
    elif promotion.promotion_type == 'fixed_amount':
        discount_amount = float(promotion.discount_value)

    return jsonify({
        'valid': True,
        'promotion': {
            'id': promotion.id,
            'code': promotion.code,
            'name': promotion.name,
            'type': promotion.promotion_type,
            'discount_amount': discount_amount
        }
    })


# ============================================================
# GIFT VOUCHERS
# ============================================================

@bp.route('/vouchers')
@login_required
@feature_required(Features.GIFT_VOUCHERS)
def vouchers():
    """List all gift vouchers"""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')

    query = GiftVoucher.query

    if status:
        query = query.filter_by(status=status)

    vouchers = query.order_by(GiftVoucher.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    return render_template('promotions/vouchers.html', vouchers=vouchers)


@bp.route('/vouchers/create', methods=['GET', 'POST'])
@login_required
@feature_required(Features.GIFT_VOUCHERS)
def create_voucher():
    """Create new gift voucher"""
    if request.method == 'POST':
        try:
            value = Decimal(request.form.get('value'))
            valid_days = int(request.form.get('valid_days', 365))

            voucher = GiftVoucher(
                code=generate_voucher_code(),
                initial_value=value,
                current_balance=value,
                recipient_name=request.form.get('recipient_name'),
                recipient_email=request.form.get('recipient_email'),
                recipient_phone=request.form.get('recipient_phone'),
                personal_message=request.form.get('personal_message'),
                valid_from=datetime.utcnow(),
                valid_until=datetime.utcnow() + timedelta(days=valid_days),
                created_by=current_user.id
            )

            db.session.add(voucher)
            db.session.flush()

            # Create initial transaction
            transaction = GiftVoucherTransaction(
                voucher_id=voucher.id,
                transaction_type='purchase',
                amount=value,
                balance_after=value,
                notes='Initial purchase',
                processed_by=current_user.id
            )
            db.session.add(transaction)
            db.session.commit()

            flash(f'Gift voucher created: {voucher.code}', 'success')
            return redirect(url_for('promotions.vouchers'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating voucher: {str(e)}', 'danger')

    return render_template('promotions/create_voucher.html')


@bp.route('/vouchers/check', methods=['POST'])
@login_required
@feature_required(Features.GIFT_VOUCHERS)
def check_voucher():
    """Check gift voucher balance"""
    data = request.get_json()
    code = data.get('code', '').upper()

    voucher = GiftVoucher.query.filter_by(code=code).first()

    if not voucher:
        return jsonify({'valid': False, 'error': 'Invalid voucher code'})

    if not voucher.is_valid:
        if voucher.status == 'expired':
            return jsonify({'valid': False, 'error': 'This voucher has expired'})
        elif voucher.current_balance <= 0:
            return jsonify({'valid': False, 'error': 'This voucher has been fully used'})
        else:
            return jsonify({'valid': False, 'error': 'This voucher is not valid'})

    return jsonify({
        'valid': True,
        'voucher': {
            'id': voucher.id,
            'code': voucher.code,
            'balance': float(voucher.current_balance),
            'valid_until': voucher.valid_until.isoformat()
        }
    })


@bp.route('/vouchers/redeem', methods=['POST'])
@login_required
@feature_required(Features.GIFT_VOUCHERS)
def redeem_voucher():
    """Redeem gift voucher"""
    data = request.get_json()
    code = data.get('code', '').upper()
    amount = Decimal(data.get('amount', 0))
    sale_id = data.get('sale_id')

    voucher = GiftVoucher.query.filter_by(code=code).first()

    if not voucher or not voucher.is_valid:
        return jsonify({'success': False, 'error': 'Invalid voucher'}), 400

    if amount > voucher.current_balance:
        return jsonify({'success': False, 'error': 'Insufficient balance'}), 400

    try:
        voucher.current_balance -= amount

        if voucher.current_balance <= 0:
            voucher.status = 'used'

        transaction = GiftVoucherTransaction(
            voucher_id=voucher.id,
            sale_id=sale_id,
            transaction_type='redemption',
            amount=amount,
            balance_after=voucher.current_balance,
            processed_by=current_user.id
        )
        db.session.add(transaction)
        db.session.commit()

        return jsonify({
            'success': True,
            'remaining_balance': float(voucher.current_balance)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/vouchers/<int:voucher_id>')
@login_required
@feature_required(Features.GIFT_VOUCHERS)
def view_voucher(voucher_id):
    """View voucher details and transaction history"""
    voucher = GiftVoucher.query.get_or_404(voucher_id)
    transactions = voucher.transactions.order_by(GiftVoucherTransaction.processed_at.desc()).all()

    return render_template('promotions/view_voucher.html',
                         voucher=voucher,
                         transactions=transactions)
