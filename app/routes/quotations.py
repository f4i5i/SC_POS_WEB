"""
Quotations Routes
Create and manage sales quotations
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
from app.models import db, Product, Customer, Sale, SaleItem
from app.models_extended import Quotation, QuotationItem
from app.utils.permissions import permission_required, Permissions
from app.utils.feature_flags import feature_required, Features

bp = Blueprint('quotations', __name__)


def generate_quotation_number():
    """Generate unique quotation number"""
    today = date.today().strftime('%Y%m%d')
    last_quote = Quotation.query.filter(
        Quotation.quotation_number.like(f'QT-{today}%')
    ).order_by(Quotation.quotation_number.desc()).first()

    if last_quote:
        last_num = int(last_quote.quotation_number.split('-')[-1])
        new_num = last_num + 1
    else:
        new_num = 1

    return f'QT-{today}-{new_num:04d}'


@bp.route('/')
@login_required
@feature_required(Features.QUOTATIONS)
def index():
    """List all quotations"""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    search = request.args.get('search', '')

    query = Quotation.query

    if status:
        query = query.filter_by(status=status)
    if search:
        query = query.filter(
            db.or_(
                Quotation.quotation_number.ilike(f'%{search}%'),
                Quotation.customer_name.ilike(f'%{search}%')
            )
        )

    quotations = query.order_by(Quotation.quotation_date.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    return render_template('quotations/index.html', quotations=quotations)


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@feature_required(Features.QUOTATIONS)
def create():
    """Create new quotation"""
    if request.method == 'POST':
        try:
            data = request.get_json()

            # Create quotation
            quotation = Quotation(
                quotation_number=generate_quotation_number(),
                customer_id=data.get('customer_id'),
                customer_name=data.get('customer_name'),
                customer_phone=data.get('customer_phone'),
                customer_email=data.get('customer_email'),
                valid_until=datetime.utcnow() + timedelta(days=int(data.get('valid_days', 7))),
                notes=data.get('notes'),
                terms_conditions=data.get('terms'),
                created_by=current_user.id
            )

            db.session.add(quotation)
            db.session.flush()

            # Add items
            subtotal = Decimal('0')
            for item in data.get('items', []):
                product = Product.query.get(item['product_id'])
                if product:
                    qty = int(item['quantity'])
                    price = Decimal(str(item.get('unit_price', product.selling_price)))
                    item_discount = Decimal(str(item.get('discount', 0)))
                    item_subtotal = (qty * price) - item_discount

                    quote_item = QuotationItem(
                        quotation_id=quotation.id,
                        product_id=product.id,
                        quantity=qty,
                        unit_price=price,
                        discount=item_discount,
                        subtotal=item_subtotal,
                        notes=item.get('notes')
                    )
                    db.session.add(quote_item)
                    subtotal += item_subtotal

            quotation.subtotal = subtotal

            # Apply discount
            discount = Decimal(str(data.get('discount', 0)))
            discount_type = data.get('discount_type', 'amount')
            quotation.discount = discount
            quotation.discount_type = discount_type

            if discount_type == 'percentage':
                discount_amount = (subtotal * discount) / 100
            else:
                discount_amount = discount

            # Calculate tax
            tax = Decimal(str(data.get('tax', 0)))
            quotation.tax = tax

            # Calculate total
            quotation.total = subtotal - discount_amount + tax
            quotation.status = 'draft'

            db.session.commit()

            return jsonify({
                'success': True,
                'quotation_number': quotation.quotation_number,
                'id': quotation.id
            })

        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400

    customers = Customer.query.filter_by(is_active=True).order_by(Customer.name).all()
    return render_template('quotations/create.html', customers=customers)


@bp.route('/view/<int:quotation_id>')
@login_required
@feature_required(Features.QUOTATIONS)
def view(quotation_id):
    """View quotation details"""
    quotation = Quotation.query.get_or_404(quotation_id)
    items = quotation.items.all()

    return render_template('quotations/view.html',
                         quotation=quotation,
                         items=items)


@bp.route('/edit/<int:quotation_id>', methods=['GET', 'POST'])
@login_required
@feature_required(Features.QUOTATIONS)
def edit(quotation_id):
    """Edit quotation"""
    quotation = Quotation.query.get_or_404(quotation_id)

    if quotation.status not in ['draft', 'sent']:
        flash('Cannot edit a quotation that has been accepted or converted.', 'warning')
        return redirect(url_for('quotations.view', quotation_id=quotation_id))

    if request.method == 'POST':
        try:
            data = request.get_json()

            quotation.customer_id = data.get('customer_id')
            quotation.customer_name = data.get('customer_name')
            quotation.customer_phone = data.get('customer_phone')
            quotation.customer_email = data.get('customer_email')
            quotation.notes = data.get('notes')
            quotation.terms_conditions = data.get('terms')

            if data.get('valid_days'):
                quotation.valid_until = datetime.utcnow() + timedelta(days=int(data.get('valid_days')))

            # Clear existing items
            QuotationItem.query.filter_by(quotation_id=quotation.id).delete()

            # Add updated items
            subtotal = Decimal('0')
            for item in data.get('items', []):
                product = Product.query.get(item['product_id'])
                if product:
                    qty = int(item['quantity'])
                    price = Decimal(str(item.get('unit_price', product.selling_price)))
                    item_discount = Decimal(str(item.get('discount', 0)))
                    item_subtotal = (qty * price) - item_discount

                    quote_item = QuotationItem(
                        quotation_id=quotation.id,
                        product_id=product.id,
                        quantity=qty,
                        unit_price=price,
                        discount=item_discount,
                        subtotal=item_subtotal
                    )
                    db.session.add(quote_item)
                    subtotal += item_subtotal

            quotation.subtotal = subtotal
            quotation.discount = Decimal(str(data.get('discount', 0)))
            quotation.discount_type = data.get('discount_type', 'amount')
            quotation.tax = Decimal(str(data.get('tax', 0)))

            # Recalculate total
            if quotation.discount_type == 'percentage':
                discount_amount = (subtotal * quotation.discount) / 100
            else:
                discount_amount = quotation.discount

            quotation.total = subtotal - discount_amount + quotation.tax

            db.session.commit()

            return jsonify({'success': True})

        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400

    customers = Customer.query.filter_by(is_active=True).order_by(Customer.name).all()
    items = quotation.items.all()

    return render_template('quotations/edit.html',
                         quotation=quotation,
                         items=items,
                         customers=customers)


@bp.route('/send/<int:quotation_id>', methods=['POST'])
@login_required
@feature_required(Features.QUOTATIONS)
def send_quotation(quotation_id):
    """Mark quotation as sent"""
    quotation = Quotation.query.get_or_404(quotation_id)
    quotation.status = 'sent'
    db.session.commit()

    # TODO: Actually send via email/WhatsApp if configured

    return jsonify({'success': True, 'message': 'Quotation marked as sent'})


@bp.route('/accept/<int:quotation_id>', methods=['POST'])
@login_required
@feature_required(Features.QUOTATIONS)
def accept_quotation(quotation_id):
    """Mark quotation as accepted"""
    quotation = Quotation.query.get_or_404(quotation_id)
    quotation.status = 'accepted'
    db.session.commit()

    return jsonify({'success': True})


@bp.route('/reject/<int:quotation_id>', methods=['POST'])
@login_required
@feature_required(Features.QUOTATIONS)
def reject_quotation(quotation_id):
    """Mark quotation as rejected"""
    quotation = Quotation.query.get_or_404(quotation_id)
    quotation.status = 'rejected'
    db.session.commit()

    return jsonify({'success': True})


@bp.route('/convert/<int:quotation_id>', methods=['POST'])
@login_required
@feature_required(Features.QUOTATIONS)
def convert_to_sale(quotation_id):
    """Convert quotation to sale"""
    quotation = Quotation.query.get_or_404(quotation_id)

    if quotation.status == 'converted':
        return jsonify({'success': False, 'error': 'Already converted'}), 400

    try:
        from app.utils.helpers import generate_sale_number

        # Create sale from quotation
        sale = Sale(
            sale_number=generate_sale_number(),
            customer_id=quotation.customer_id,
            user_id=current_user.id,
            subtotal=quotation.subtotal,
            discount=quotation.discount,
            discount_type=quotation.discount_type,
            tax=quotation.tax,
            total=quotation.total,
            payment_method='cash',
            payment_status='pending',
            status='pending',
            notes=f'Converted from quotation {quotation.quotation_number}'
        )

        db.session.add(sale)
        db.session.flush()

        # Copy items
        for quote_item in quotation.items:
            sale_item = SaleItem(
                sale_id=sale.id,
                product_id=quote_item.product_id,
                quantity=quote_item.quantity,
                unit_price=quote_item.unit_price,
                discount=quote_item.discount,
                subtotal=quote_item.subtotal
            )
            db.session.add(sale_item)

        # Update quotation
        quotation.status = 'converted'
        quotation.converted_to_sale_id = sale.id
        quotation.converted_at = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'success': True,
            'sale_id': sale.id,
            'sale_number': sale.sale_number
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/print/<int:quotation_id>')
@login_required
@feature_required(Features.QUOTATIONS)
def print_quotation(quotation_id):
    """Print quotation"""
    quotation = Quotation.query.get_or_404(quotation_id)
    items = quotation.items.all()

    return render_template('quotations/print.html',
                         quotation=quotation,
                         items=items)


@bp.route('/delete/<int:quotation_id>', methods=['POST'])
@login_required
@feature_required(Features.QUOTATIONS)
def delete_quotation(quotation_id):
    """Delete quotation"""
    quotation = Quotation.query.get_or_404(quotation_id)

    if quotation.status == 'converted':
        return jsonify({'success': False, 'error': 'Cannot delete converted quotation'}), 400

    # Delete items first
    QuotationItem.query.filter_by(quotation_id=quotation.id).delete()
    db.session.delete(quotation)
    db.session.commit()

    return jsonify({'success': True})
