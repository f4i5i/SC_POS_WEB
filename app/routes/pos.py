"""
Point of Sale Routes
Handles POS operations, sales, and transactions
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session, current_app, g
from flask_login import login_required, current_user
from datetime import datetime, date
from decimal import Decimal
from app.models import db, Product, Sale, SaleItem, Customer, StockMovement, Payment, SyncQueue, Setting, DayClose, LocationStock, StockTransfer, StockTransferItem, Location
from app.utils.helpers import generate_sale_number, has_permission
from app.utils.pdf_utils import generate_receipt_pdf
from app.utils.permissions import permission_required, Permissions
from app.utils.location_context import get_current_location, location_required, get_or_create_location_stock
import json

# Try to import Return models (may not exist in all setups)
try:
    from app.models_extended import Return, ReturnItem, CustomerCredit
    RETURNS_ENABLED = True
except ImportError:
    RETURNS_ENABLED = False

bp = Blueprint('pos', __name__)


@bp.route('/')
@login_required
@permission_required(Permissions.POS_VIEW)
def index():
    """POS interface"""
    # Get current location for multi-kiosk support
    location = get_current_location()

    # Warn if no location assigned (but allow access for backward compatibility)
    if not location and not current_user.is_global_admin:
        flash('You are not assigned to a location. Some features may be limited.', 'warning')

    # Get recent customers for quick selection
    recent_customers = Customer.query.filter_by(is_active=True).order_by(Customer.created_at.desc()).limit(10).all()

    return render_template('pos/index.html',
                           customers=recent_customers,
                           today=date.today().isoformat(),
                           current_location=location)


@bp.route('/search-products')
@login_required
@permission_required(Permissions.POS_VIEW)
def search_products():
    """Search products for POS with location-aware stock"""
    query = request.args.get('q', '').strip()

    if len(query) < 2:
        return jsonify({'products': []})

    # Get current location for stock lookup
    location = get_current_location()

    # Check if reorders can be created from this location
    can_reorder = False
    if location and location.location_type == 'kiosk' and location.parent_warehouse_id:
        can_reorder = True

    # Search by code, barcode, name, or brand
    if location:
        # Location-aware query with stock from LocationStock
        products = db.session.query(Product, LocationStock).outerjoin(
            LocationStock,
            db.and_(
                LocationStock.product_id == Product.id,
                LocationStock.location_id == location.id
            )
        ).filter(
            Product.is_active == True,
            db.or_(
                Product.code.ilike(f'%{query}%'),
                Product.barcode.ilike(f'%{query}%'),
                Product.name.ilike(f'%{query}%'),
                Product.brand.ilike(f'%{query}%')
            )
        ).limit(20).all()

        results = []
        for product, stock in products:
            qty = stock.available_quantity if stock else 0
            reorder_level = stock.reorder_level if stock else product.reorder_level
            is_low = stock.is_low_stock if stock else (qty <= reorder_level)
            results.append({
                'id': product.id,
                'code': product.code,
                'barcode': product.barcode,
                'name': product.name,
                'brand': product.brand,
                'size': product.size,
                'selling_price': float(product.selling_price),
                'quantity': qty,
                'is_low_stock': is_low,
                'reorder_level': reorder_level,
                'suggested_reorder_qty': product.suggested_reorder_quantity if hasattr(product, 'suggested_reorder_quantity') else 10,
                'can_reorder': can_reorder,
                'image_url': product.image_url
            })
    else:
        # Fallback: use product.quantity for backward compatibility
        products = Product.query.filter(
            db.and_(
                Product.is_active == True,
                db.or_(
                    Product.code.ilike(f'%{query}%'),
                    Product.barcode.ilike(f'%{query}%'),
                    Product.name.ilike(f'%{query}%'),
                    Product.brand.ilike(f'%{query}%')
                )
            )
        ).limit(20).all()

        results = []
        for product in products:
            results.append({
                'id': product.id,
                'code': product.code,
                'barcode': product.barcode,
                'name': product.name,
                'brand': product.brand,
                'size': product.size,
                'selling_price': float(product.selling_price),
                'quantity': product.quantity,
                'is_low_stock': product.is_low_stock,
                'reorder_level': product.reorder_level,
                'suggested_reorder_qty': product.suggested_reorder_quantity if hasattr(product, 'suggested_reorder_quantity') else 10,
                'can_reorder': False,  # No reorder without location
                'image_url': product.image_url
            })

    return jsonify({'products': results})


@bp.route('/get-product/<int:product_id>')
@login_required
@permission_required(Permissions.POS_VIEW)
def get_product(product_id):
    """Get product details with location-aware stock"""
    product = Product.query.get_or_404(product_id)

    # Get stock for current location
    location = get_current_location()
    if location:
        stock = LocationStock.query.filter_by(
            location_id=location.id,
            product_id=product_id
        ).first()
        qty = stock.available_quantity if stock else 0
        is_low_stock = stock.is_low_stock if stock else (qty <= 10)
    else:
        # Fallback for backward compatibility
        qty = product.quantity
        is_low_stock = product.is_low_stock

    return jsonify({
        'id': product.id,
        'code': product.code,
        'barcode': product.barcode,
        'name': product.name,
        'brand': product.brand,
        'size': product.size,
        'selling_price': float(product.selling_price),
        'tax_rate': float(product.tax_rate),
        'quantity': qty,
        'is_low_stock': is_low_stock,
        'image_url': product.image_url
    })


def generate_transfer_number():
    """Generate unique transfer number for reorders"""
    today = date.today().strftime('%Y%m%d')
    last_transfer = StockTransfer.query.filter(
        StockTransfer.transfer_number.like(f'TRF-{today}%')
    ).order_by(StockTransfer.transfer_number.desc()).first()

    if last_transfer:
        last_num = int(last_transfer.transfer_number.split('-')[-1])
        new_num = last_num + 1
    else:
        new_num = 1

    return f'TRF-{today}-{new_num:04d}'


@bp.route('/create-reorder', methods=['POST'])
@login_required
@permission_required(Permissions.POS_VIEW)
def create_reorder():
    """Create a draft reorder request from POS for low-stock product"""
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        quantity = data.get('quantity', 10)

        if not product_id:
            return jsonify({'success': False, 'error': 'Product ID required'}), 400

        location = get_current_location()
        if not location:
            return jsonify({'success': False, 'error': 'No location assigned'}), 400

        # Only kiosks can create reorders
        if location.location_type != 'kiosk':
            return jsonify({'success': False, 'error': 'Reorders can only be created from kiosks'}), 400

        # Get source warehouse
        if not location.parent_warehouse_id:
            return jsonify({'success': False, 'error': 'No warehouse configured for this location'}), 400

        # Check if a draft reorder already exists for this location
        existing = StockTransfer.query.filter_by(
            destination_location_id=location.id,
            status='draft'
        ).first()

        if existing:
            # Check if this product is already in the draft
            existing_item = StockTransferItem.query.filter_by(
                transfer_id=existing.id,
                product_id=product_id
            ).first()

            if existing_item:
                # Update quantity
                existing_item.quantity_requested = quantity
                db.session.commit()
                return jsonify({
                    'success': True,
                    'transfer_id': existing.id,
                    'transfer_number': existing.transfer_number,
                    'message': 'Reorder quantity updated'
                })
            else:
                # Add to existing draft
                item = StockTransferItem(
                    transfer_id=existing.id,
                    product_id=product_id,
                    quantity_requested=quantity
                )
                db.session.add(item)
                db.session.commit()
                return jsonify({
                    'success': True,
                    'transfer_id': existing.id,
                    'transfer_number': existing.transfer_number,
                    'message': 'Product added to existing draft reorder'
                })

        # Create new draft transfer
        transfer = StockTransfer(
            transfer_number=generate_transfer_number(),
            source_location_id=location.parent_warehouse_id,
            destination_location_id=location.id,
            status='draft',
            priority='normal',
            requested_by=current_user.id,
            request_notes='Auto-created from POS low-stock alert'
        )
        db.session.add(transfer)
        db.session.flush()

        # Add the item
        item = StockTransferItem(
            transfer_id=transfer.id,
            product_id=product_id,
            quantity_requested=quantity
        )
        db.session.add(item)
        db.session.commit()

        return jsonify({
            'success': True,
            'transfer_id': transfer.id,
            'transfer_number': transfer.transfer_number,
            'message': 'Reorder request created. Manager will review.'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/complete-sale', methods=['POST'])
@login_required
@permission_required(Permissions.POS_CREATE_SALE)
def complete_sale():
    """Complete a sale transaction with location-aware stock"""
    try:
        data = request.get_json()

        # Validate data
        items = data.get('items', [])
        if not items:
            return jsonify({'success': False, 'error': 'No items in cart'}), 400

        # Get current location for multi-kiosk support
        location = get_current_location()

        # Handle backdate sales (admin/manager only)
        sale_date = None
        backdate_str = data.get('sale_date')
        if backdate_str:
            # Check if user has permission to backdate
            if current_user.role not in ['admin', 'manager']:
                return jsonify({'success': False, 'error': 'Only admin/manager can backdate sales'}), 403
            try:
                sale_date = datetime.strptime(backdate_str, '%Y-%m-%d')
                # Don't allow future dates
                if sale_date.date() > date.today():
                    return jsonify({'success': False, 'error': 'Cannot create sales with future dates'}), 400
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        # Create sale
        sale = Sale(
            sale_number=generate_sale_number(),
            user_id=current_user.id,
            customer_id=data.get('customer_id'),
            location_id=location.id if location else None,  # Multi-kiosk support
            subtotal=Decimal(str(data.get('subtotal', 0))),
            discount=Decimal(str(data.get('discount', 0))),
            discount_type=data.get('discount_type', 'amount'),
            tax=Decimal(str(data.get('tax', 0))),
            total=Decimal(str(data.get('total', 0))),
            payment_method=data.get('payment_method', 'cash'),
            amount_paid=Decimal(str(data.get('amount_paid', 0))),
            notes=data.get('notes', '')
        )

        # Set sale date if backdating
        if sale_date:
            sale.sale_date = sale_date

        # Calculate amount due
        sale.amount_due = sale.total - sale.amount_paid
        if sale.amount_due > 0:
            sale.payment_status = 'partial'
        else:
            sale.payment_status = 'paid'

        db.session.add(sale)
        db.session.flush()  # Get sale ID

        # Add sale items and update stock
        for item_data in items:
            product = Product.query.get(item_data['product_id'])
            if not product:
                db.session.rollback()
                return jsonify({'success': False, 'error': f'Product {item_data["product_id"]} not found'}), 404

            quantity = int(item_data['quantity'])

            # Check stock availability - location-aware
            if location:
                # Use LocationStock for multi-kiosk
                location_stock = LocationStock.query.filter_by(
                    location_id=location.id,
                    product_id=product.id
                ).first()
                available_qty = location_stock.available_quantity if location_stock else 0

                if available_qty < quantity:
                    db.session.rollback()
                    return jsonify({
                        'success': False,
                        'error': f'Insufficient stock for {product.name} at this location. Available: {available_qty}'
                    }), 400
            else:
                # Fallback: use product.quantity
                if product.quantity < quantity:
                    db.session.rollback()
                    return jsonify({
                        'success': False,
                        'error': f'Insufficient stock for {product.name}. Available: {product.quantity}'
                    }), 400

            # Create sale item
            sale_item = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                quantity=quantity,
                unit_price=Decimal(str(item_data['unit_price'])),
                discount=Decimal(str(item_data.get('discount', 0))),
                subtotal=Decimal(str(item_data['subtotal']))
            )
            db.session.add(sale_item)

            # Update stock - location-aware
            if location:
                # Update LocationStock
                if location_stock:
                    location_stock.quantity -= quantity
                    location_stock.last_movement_at = datetime.utcnow()
            else:
                # Fallback: update product.quantity
                product.quantity -= quantity

            # Create stock movement record with location
            stock_movement = StockMovement(
                product_id=product.id,
                user_id=current_user.id,
                movement_type='sale',
                quantity=-quantity,
                reference=sale.sale_number,
                notes=f'Sale {sale.sale_number}',
                location_id=location.id if location else None
            )
            db.session.add(stock_movement)

        # Handle split payments
        payments_data = data.get('payments', [])
        is_split = len(payments_data) > 1

        if is_split:
            # Multiple payment methods
            sale.is_split_payment = True
            sale.payment_method = 'split'  # Indicate split payment

            total_paid = Decimal('0')
            for idx, pmt in enumerate(payments_data, 1):
                pmt_amount = Decimal(str(pmt.get('amount', 0)))
                total_paid += pmt_amount
                payment = Payment(
                    sale_id=sale.id,
                    amount=pmt_amount,
                    payment_method=pmt.get('method', 'cash'),
                    reference_number=pmt.get('reference', ''),
                    notes=pmt.get('notes', ''),
                    payment_order=idx
                )
                db.session.add(payment)

            # Recalculate amount_paid from actual payments
            sale.amount_paid = total_paid
            sale.amount_due = sale.total - total_paid
            sale.payment_status = 'paid' if sale.amount_due <= 0 else 'partial'

        elif sale.amount_paid > 0:
            # Single payment (existing logic)
            payment = Payment(
                sale_id=sale.id,
                amount=sale.amount_paid,
                payment_method=sale.payment_method,
                reference_number=data.get('reference_number', ''),
                notes=data.get('payment_notes', ''),
                payment_order=1
            )
            db.session.add(payment)

        # Queue for sync
        sync_item = SyncQueue(
            table_name='sales',
            operation='insert',
            record_id=sale.id,
            data_json=json.dumps({
                'sale_id': sale.id,
                'sale_number': sale.sale_number
            })
        )
        db.session.add(sync_item)

        # Award loyalty points if customer is selected
        points_earned = 0
        new_badges = []
        completed_challenges = []
        if sale.customer_id:
            customer = Customer.query.get(sale.customer_id)
            if customer:
                # Award 1 point per Rs. 100 spent
                points_earned = customer.add_loyalty_points(float(sale.total))

                # Check and award badges (gamified loyalty)
                try:
                    from app.routes.loyalty import check_and_award_badges, update_challenge_progress
                    new_badges = check_and_award_badges(sale.customer_id, sale)
                    completed_challenges = update_challenge_progress(sale.customer_id, sale)
                except Exception as badge_error:
                    current_app.logger.error(f"Badge checking error: {badge_error}")

        db.session.commit()

        # Get customer loyalty info for response
        customer_info = None
        if sale.customer_id:
            customer = Customer.query.get(sale.customer_id)
            if customer:
                customer_info = {
                    'points_earned': points_earned,
                    'total_points': customer.loyalty_points,
                    'loyalty_tier': customer.loyalty_tier,
                    'points_value': customer.points_value_pkr,
                    'new_badges': new_badges,
                    'completed_challenges': completed_challenges
                }

        return jsonify({
            'success': True,
            'sale_id': sale.id,
            'sale_number': sale.sale_number,
            'total': float(sale.total),
            'change': float(sale.amount_paid - sale.total),
            'loyalty': customer_info
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/print-receipt/<int:sale_id>')
@login_required
@permission_required(Permissions.POS_VIEW)
def print_receipt(sale_id):
    """Generate and display receipt for printing"""
    sale = Sale.query.get_or_404(sale_id)

    # Get business settings
    settings = Setting.query.all()
    settings_dict = {s.key: s.value for s in settings}

    return render_template('pos/receipt.html',
                         sale=sale,
                         business_name=settings_dict.get('business_name', 'Sunnat Collection'),
                         business_address=settings_dict.get('business_address', 'First Floor, Mall of Wah, G.T Road'),
                         business_phone=settings_dict.get('business_phone', ''),
                         business_email=settings_dict.get('business_email', ''),
                         tagline=settings_dict.get('tagline', 'Quality Perfumes at Best Prices'))


@bp.route('/sales')
@login_required
@permission_required(Permissions.POS_VIEW)
def sales_list():
    """List all sales - filtered by location for non-global admins"""
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config['ITEMS_PER_PAGE']

    # Filter by date if provided
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    query = Sale.query.order_by(Sale.sale_date.desc())

    # Filter by location for non-global admins
    if not current_user.is_global_admin:
        if current_user.location_id:
            query = query.filter(Sale.location_id == current_user.location_id)
        else:
            # No location assigned - show no sales
            query = query.filter(False)

    if from_date:
        query = query.filter(Sale.sale_date >= from_date)
    if to_date:
        query = query.filter(Sale.sale_date <= to_date)

    sales = query.paginate(page=page, per_page=per_page, error_out=False)

    # Get location name for display
    from app.models import Location
    user_location = None
    if current_user.location_id:
        user_location = Location.query.get(current_user.location_id)

    return render_template('pos/sales_list.html', sales=sales, user_location=user_location)


@bp.route('/sale-details/<int:sale_id>')
@login_required
@permission_required(Permissions.POS_VIEW)
def sale_details(sale_id):
    """View sale details"""
    sale = Sale.query.get_or_404(sale_id)
    return render_template('pos/sale_details.html', sale=sale)


@bp.route('/refund-sale/<int:sale_id>', methods=['POST'])
@login_required
@permission_required(Permissions.POS_REFUND)
def refund_sale(sale_id):
    """Process sale refund"""
    try:
        sale = Sale.query.get_or_404(sale_id)

        if sale.status == 'refunded':
            return jsonify({'success': False, 'error': 'Sale already refunded'}), 400

        # Restore stock for all items
        for item in sale.items:
            product = Product.query.get(item.product_id)
            if product:
                product.quantity += item.quantity

                # Create stock movement
                stock_movement = StockMovement(
                    product_id=product.id,
                    user_id=current_user.id,
                    movement_type='return',
                    quantity=item.quantity,
                    reference=sale.sale_number,
                    notes=f'Refund for sale {sale.sale_number}'
                )
                db.session.add(stock_movement)

        # Update sale status
        sale.status = 'refunded'

        # Queue for sync
        sync_item = SyncQueue(
            table_name='sales',
            operation='update',
            record_id=sale.id,
            data_json=json.dumps({'status': 'refunded'})
        )
        db.session.add(sync_item)

        db.session.commit()

        return jsonify({'success': True, 'message': 'Sale refunded successfully'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/edit-sale/<int:sale_id>', methods=['GET', 'POST'])
@login_required
def edit_sale(sale_id):
    """Edit sale - Admin only"""
    # Only admin can edit sales
    if not current_user.is_global_admin and current_user.role != 'admin':
        flash('Only administrators can edit sales.', 'danger')
        return redirect(url_for('pos.sale_details', sale_id=sale_id))

    sale = Sale.query.get_or_404(sale_id)
    customers = Customer.query.filter_by(is_active=True).order_by(Customer.name).all()

    if request.method == 'POST':
        try:
            # Track changes for audit
            changes = []

            # Update customer
            new_customer_id = request.form.get('customer_id', type=int)
            if new_customer_id != sale.customer_id:
                old_customer = sale.customer.name if sale.customer else 'Walk-in'
                new_customer = Customer.query.get(new_customer_id).name if new_customer_id else 'Walk-in'
                changes.append(f"Customer: {old_customer} → {new_customer}")
                sale.customer_id = new_customer_id if new_customer_id else None

            # Update payment method
            new_payment_method = request.form.get('payment_method')
            if new_payment_method and new_payment_method != sale.payment_method:
                changes.append(f"Payment: {sale.payment_method} → {new_payment_method}")
                sale.payment_method = new_payment_method

            # Update payment status
            new_payment_status = request.form.get('payment_status')
            if new_payment_status and new_payment_status != sale.payment_status:
                changes.append(f"Status: {sale.payment_status} → {new_payment_status}")
                sale.payment_status = new_payment_status

            # Update discount
            new_discount_str = request.form.get('discount', '0')
            new_discount = Decimal(new_discount_str) if new_discount_str else Decimal('0')
            new_discount_type = request.form.get('discount_type', 'amount')
            if new_discount != sale.discount or new_discount_type != sale.discount_type:
                changes.append(f"Discount: {sale.discount} ({sale.discount_type}) → {new_discount} ({new_discount_type})")
                sale.discount = new_discount
                sale.discount_type = new_discount_type

            # Update notes
            new_notes = request.form.get('notes', '').strip()
            if new_notes != (sale.notes or ''):
                changes.append(f"Notes updated")
                sale.notes = new_notes

            # Update item prices if provided
            for item in sale.items:
                item_price_key = f'item_price_{item.id}'
                item_qty_key = f'item_qty_{item.id}'

                new_price_str = request.form.get(item_price_key)
                new_qty = request.form.get(item_qty_key, type=int)

                if new_price_str:
                    new_price = Decimal(new_price_str)
                    if new_price != item.unit_price:
                        changes.append(f"Item {item.product.code}: Price {item.unit_price} → {new_price}")
                        item.unit_price = new_price
                        item.calculate_subtotal()

                if new_qty is not None and new_qty != item.quantity:
                    # Adjust stock
                    qty_diff = new_qty - item.quantity
                    product = item.product

                    # Check if enough stock for increase
                    if qty_diff > 0 and int(product.quantity or 0) < qty_diff:
                        flash(f'Not enough stock for {product.name}. Available: {product.quantity}', 'danger')
                        return redirect(url_for('pos.edit_sale', sale_id=sale_id))

                    # Update product stock
                    product.quantity = int(product.quantity or 0) - qty_diff

                    # Update location stock if applicable
                    if sale.location_id:
                        loc_stock = LocationStock.query.filter_by(
                            product_id=product.id,
                            location_id=sale.location_id
                        ).first()
                        if loc_stock:
                            loc_stock.quantity = int(loc_stock.quantity or 0) - qty_diff

                    changes.append(f"Item {product.code}: Qty {item.quantity} → {new_qty}")
                    item.quantity = new_qty
                    item.calculate_subtotal()

            # Recalculate sale totals
            sale.calculate_totals()

            # Add edit note with timestamp
            edit_note = f"\n[Edited by {current_user.full_name} on {datetime.now().strftime('%Y-%m-%d %H:%M')}]"
            if changes:
                edit_note += f"\nChanges: {'; '.join(changes)}"

            if sale.notes:
                sale.notes += edit_note
            else:
                sale.notes = edit_note.strip()

            db.session.commit()
            flash('Sale updated successfully.', 'success')
            return redirect(url_for('pos.sale_details', sale_id=sale_id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating sale: {str(e)}', 'danger')

    return render_template('pos/edit_sale.html', sale=sale, customers=customers)


@bp.route('/hold-sale', methods=['POST'])
@login_required
@permission_required(Permissions.POS_HOLD_SALE)
def hold_sale():
    """Hold a sale for later"""
    data = request.get_json()

    # Store in session
    if 'held_sales' not in session:
        session['held_sales'] = []

    session['held_sales'].append({
        'timestamp': datetime.now().isoformat(),
        'items': data.get('items', []),
        'customer_id': data.get('customer_id'),
        'notes': data.get('notes', '')
    })
    session.modified = True

    return jsonify({'success': True, 'message': 'Sale held successfully'})


@bp.route('/retrieve-held-sales')
@login_required
@permission_required(Permissions.POS_VIEW)
def retrieve_held_sales():
    """Get list of held sales"""
    held_sales = session.get('held_sales', [])
    return jsonify({'sales': held_sales})


@bp.route('/delete-held-sale/<int:index>', methods=['POST'])
@login_required
@permission_required(Permissions.POS_HOLD_SALE)
def delete_held_sale(index):
    """Delete a held sale"""
    if 'held_sales' in session and 0 <= index < len(session['held_sales']):
        session['held_sales'].pop(index)
        session.modified = True
        return jsonify({'success': True})

    return jsonify({'success': False, 'error': 'Sale not found'}), 404


@bp.route('/close-day-summary')
@login_required
@permission_required(Permissions.POS_CLOSE_DAY)
def close_day_summary():
    """Get summary data for closing the day"""
    from datetime import date
    from decimal import Decimal
    
    try:
        today = date.today()
        
        # Check if day already closed
        existing_close = DayClose.query.filter_by(close_date=today).first()
        if existing_close:
            return jsonify({
                'success': False,
                'error': 'Day already closed',
                'close_data': {
                    'close_date': existing_close.close_date.isoformat(),
                    'closed_at': existing_close.closed_at.isoformat(),
                    'closed_by': existing_close.user.full_name
                }
            }), 400
        
        # Get today's sales
        today_sales = Sale.query.filter(
            db.func.date(Sale.sale_date) == today
        ).all()
        
        # Calculate totals
        total_sales = len(today_sales)
        total_revenue = sum(sale.total for sale in today_sales)
        total_cash = sum(sale.total for sale in today_sales if sale.payment_method == 'cash')
        total_card = sum(sale.total for sale in today_sales if sale.payment_method == 'card')
        total_other = sum(sale.total for sale in today_sales if sale.payment_method not in ['cash', 'card'])
        
        # Get opening balance (from last close or default)
        last_close = DayClose.query.order_by(DayClose.close_date.desc()).first()
        opening_balance = last_close.closing_balance if last_close else Decimal('0.00')
        
        # Expected cash = opening balance + today's cash sales
        expected_cash = opening_balance + total_cash
        
        return jsonify({
            'success': True,
            'summary': {
                'date': today.isoformat(),
                'total_sales': total_sales,
                'total_revenue': float(total_revenue),
                'total_cash': float(total_cash),
                'total_card': float(total_card),
                'total_other': float(total_other),
                'opening_balance': float(opening_balance),
                'expected_cash': float(expected_cash)
            }
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/close-day', methods=['POST'])
@login_required
@permission_required(Permissions.POS_CLOSE_DAY)
def close_day():
    """Close the day and generate report"""
    from datetime import date
    from decimal import Decimal
    import os
    
    try:
        data = request.get_json()
        today = date.today()
        
        # Check if already closed
        existing_close = DayClose.query.filter_by(close_date=today).first()
        if existing_close:
            return jsonify({'success': False, 'error': 'Day already closed'}), 400
        
        # Get today's sales
        today_sales = Sale.query.filter(
            db.func.date(Sale.sale_date) == today
        ).all()
        
        # Calculate totals
        total_sales = len(today_sales)
        total_revenue = sum(sale.total for sale in today_sales)
        total_cash = sum(sale.total for sale in today_sales if sale.payment_method == 'cash')
        total_card = sum(sale.total for sale in today_sales if sale.payment_method == 'card')
        total_other = sum(sale.total for sale in today_sales if sale.payment_method not in ['cash', 'card'])
        
        # Get balances
        last_close = DayClose.query.order_by(DayClose.close_date.desc()).first()
        opening_balance = last_close.closing_balance if last_close else Decimal('0.00')
        
        closing_balance = Decimal(str(data.get('closing_balance', 0)))
        expected_cash = opening_balance + total_cash
        cash_variance = closing_balance - expected_cash
        
        # Create day close record
        day_close = DayClose(
            close_date=today,
            closed_by=current_user.id,
            total_sales=total_sales,
            total_revenue=total_revenue,
            total_cash=total_cash,
            total_card=total_card,
            total_other=total_other,
            total_expenses=Decimal(str(data.get('total_expenses', 0))),
            opening_balance=opening_balance,
            closing_balance=closing_balance,
            expected_cash=expected_cash,
            cash_variance=cash_variance,
            notes=data.get('notes', '')
        )
        
        db.session.add(day_close)
        db.session.flush()
        
        # Generate report
        report_generated = False
        report_path = None
        
        try:
            from app.utils.reports import generate_daily_report
            report_path = generate_daily_report(day_close, today_sales)
            day_close.report_generated = True
            day_close.report_path = report_path
            report_generated = True
        except Exception as report_error:
            print(f"Error generating report: {report_error}")
        
        # Send email if configured
        email_sent = False
        email_address = data.get('email_to') or current_app.config.get('REPORT_EMAIL')
        
        if email_address and report_generated:
            try:
                from app.utils.email_service import send_daily_report_email
                send_daily_report_email(day_close, report_path, email_address)
                day_close.report_sent = True
                day_close.sent_to = email_address
                email_sent = True
            except Exception as email_error:
                print(f"Error sending email: {email_error}")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Day closed successfully',
            'day_close_id': day_close.id,
            'report_generated': report_generated,
            'email_sent': email_sent,
            'summary': {
                'total_sales': total_sales,
                'total_revenue': float(total_revenue),
                'cash_variance': float(cash_variance)
            }
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/customer-lookup/<phone>')
@login_required
@permission_required(Permissions.POS_VIEW)
def customer_lookup(phone):
    """Look up customer by phone and get their purchase history"""
    try:
        customer = Customer.query.filter_by(phone=phone).first()
        
        if not customer:
            return jsonify({'success': False, 'message': 'Customer not found'})
        
        # Get last order
        last_sale = Sale.query.filter_by(customer_id=customer.id)\
            .order_by(Sale.sale_date.desc()).first()
        
        last_order = None
        if last_sale:
            last_order = {
                'sale_number': last_sale.sale_number,
                'sale_date': last_sale.sale_date.strftime('%d %b %Y %H:%M'),
                'days_ago': (datetime.utcnow() - last_sale.sale_date).days,
                'total': float(last_sale.total),
                'payment_method': last_sale.payment_method,
                'items': [
                    {
                        'product_name': item.product.name if item.product else 'Unknown',
                        'quantity': item.quantity,
                        'unit_price': float(item.unit_price),
                        'subtotal': float(item.subtotal)
                    }
                    for item in last_sale.items.all()
                ]
            }
        
        # Get purchase history (top 5 products)
        from sqlalchemy import func, desc
        top_products = db.session.query(
            Product.id,
            Product.name,
            Product.image_url,
            func.count(SaleItem.id).label('purchase_count'),
            func.sum(SaleItem.quantity).label('total_quantity')
        ).select_from(Product)\
        .join(SaleItem, SaleItem.product_id == Product.id)\
        .join(Sale, Sale.id == SaleItem.sale_id)\
        .filter(Sale.customer_id == customer.id)\
        .group_by(Product.id, Product.name, Product.image_url)\
        .order_by(desc('purchase_count'))\
        .limit(5).all()
        
        frequently_purchased = [
            {
                'product_id': p.id,
                'product_name': p.name,
                'image_url': p.image_url,
                'purchase_count': p.purchase_count,
                'total_quantity': p.total_quantity
            }
            for p in top_products
        ]
        
        # Get recommendations (products similar customers bought)
        recommendations = get_product_recommendations(customer.id)

        # Calculate customer stats
        total_orders = customer.sales.count()
        avg_order_value = float(customer.total_purchases) / total_orders if total_orders > 0 else 0

        # Check for birthday
        is_birthday = False
        birthday_str = None
        if customer.birthday:
            today = datetime.now().date()
            is_birthday = (customer.birthday.month == today.month and customer.birthday.day == today.day)
            birthday_str = customer.birthday.strftime('%d %b')

        # Get preferred payment method
        preferred_payment = db.session.query(
            Sale.payment_method,
            db.func.count(Sale.id).label('count')
        ).filter(Sale.customer_id == customer.id)\
        .group_by(Sale.payment_method)\
        .order_by(db.desc('count')).first()

        return jsonify({
            'success': True,
            'customer': {
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
                'email': customer.email,
                'address': customer.address,
                'loyalty_points': customer.loyalty_points,
                'loyalty_tier': customer.loyalty_tier,
                'loyalty_tier_color': customer.loyalty_tier_color,
                'points_value_pkr': customer.points_value_pkr,
                'points_to_next_tier': customer.points_to_next_tier,
                'total_purchases': float(customer.total_purchases),
                'customer_type': customer.customer_type,
                'account_balance': float(customer.account_balance or 0),
                'notes': customer.notes,
                'birthday': birthday_str,
                'is_birthday': is_birthday
            },
            'stats': {
                'total_orders': total_orders,
                'avg_order_value': round(avg_order_value, 2),
                'preferred_payment': preferred_payment[0] if preferred_payment else 'cash',
                'member_since': customer.created_at.strftime('%b %Y') if customer.created_at else None
            },
            'last_order': last_order,
            'frequently_purchased': frequently_purchased,
            'recommendations': recommendations
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def get_product_recommendations(customer_id, limit=5):
    """Get intelligent product recommendations based on purchase history"""
    from sqlalchemy import func, desc, and_

    try:
        # Get products purchased by this customer
        customer_products = db.session.query(Product.id)\
            .select_from(Product)\
            .join(SaleItem, SaleItem.product_id == Product.id)\
            .join(Sale, Sale.id == SaleItem.sale_id)\
            .filter(Sale.customer_id == customer_id).distinct().subquery()

        # Get popular products not yet purchased by this customer
        recommendations = db.session.query(
            Product.id,
            Product.name,
            Product.selling_price,
            Product.image_url,
            func.count(Sale.id).label('popularity')
        ).select_from(Product)\
        .join(SaleItem, SaleItem.product_id == Product.id)\
        .join(Sale, Sale.id == SaleItem.sale_id)\
        .filter(
            and_(
                Product.is_active == True,
                Product.id.notin_(customer_products),  # Exclude already purchased
                Sale.customer_id != customer_id  # From other customers
            )
        ).group_by(Product.id, Product.name, Product.selling_price, Product.image_url)\
        .order_by(desc('popularity'))\
        .limit(limit).all()

        return [
            {
                'product_id': r.id,
                'product_name': r.name,
                'selling_price': float(r.selling_price),
                'image_url': r.image_url,
                'popularity': r.popularity
            }
            for r in recommendations
        ]
    except Exception:
        # Return empty list if recommendations fail
        return []


# ============================================================
# RETURNS FROM POS
# ============================================================

@bp.route('/search-sales-for-return')
@login_required
@permission_required(Permissions.POS_REFUND)
def search_sales_for_return():
    """Search for sales to process return"""
    query = request.args.get('q', '').strip()

    if not query:
        return jsonify({'success': False, 'sales': []})

    # Search by sale number or customer phone
    sales = Sale.query.filter(
        db.or_(
            Sale.sale_number.ilike(f'%{query}%'),
            Sale.customer.has(Customer.phone.ilike(f'%{query}%')),
            Sale.customer.has(Customer.name.ilike(f'%{query}%'))
        ),
        Sale.status.in_(['completed', 'partial_return'])
    ).order_by(Sale.sale_date.desc()).limit(10).all()

    results = []
    for sale in sales:
        results.append({
            'id': sale.id,
            'sale_number': sale.sale_number,
            'sale_date': sale.sale_date.strftime('%d %b %Y %H:%M'),
            'total': float(sale.total),
            'customer_name': sale.customer.name if sale.customer else 'Walk-in',
            'status': sale.status
        })

    return jsonify({'success': True, 'sales': results})


@bp.route('/sale-items-for-return/<int:sale_id>')
@login_required
@permission_required(Permissions.POS_REFUND)
def sale_items_for_return(sale_id):
    """Get items from a sale for return selection"""
    sale = Sale.query.get_or_404(sale_id)

    items = []
    for item in sale.items:
        # Calculate already returned quantity for this item
        returned_qty = 0
        if RETURNS_ENABLED:
            returned_qty = db.session.query(db.func.coalesce(db.func.sum(ReturnItem.quantity), 0)).filter(
                ReturnItem.sale_item_id == item.id,
                ReturnItem.return_order.has(Return.status.in_(['pending', 'approved', 'completed']))
            ).scalar() or 0

        items.append({
            'sale_item_id': item.id,
            'product_id': item.product_id,
            'product_name': item.product.name if item.product else 'Unknown',
            'product_code': item.product.code if item.product else '',
            'quantity': item.quantity,
            'returned_quantity': int(returned_qty),
            'unit_price': float(item.unit_price),
            'subtotal': float(item.subtotal)
        })

    return jsonify({
        'success': True,
        'sale': {
            'id': sale.id,
            'sale_number': sale.sale_number,
            'sale_date': sale.sale_date.strftime('%d %b %Y %H:%M'),
            'customer_name': sale.customer.name if sale.customer else 'Walk-in',
            'customer_id': sale.customer_id,
            'total': float(sale.total)
        },
        'items': items
    })


def generate_return_number():
    """Generate unique return number"""
    today = date.today().strftime('%Y%m%d')

    if RETURNS_ENABLED:
        last_return = Return.query.filter(
            Return.return_number.like(f'RET-{today}%')
        ).order_by(Return.return_number.desc()).first()

        if last_return:
            last_num = int(last_return.return_number.split('-')[-1])
            new_num = last_num + 1
        else:
            new_num = 1
    else:
        new_num = 1

    return f'RET-{today}-{new_num:04d}'


@bp.route('/process-return', methods=['POST'])
@login_required
@permission_required(Permissions.POS_REFUND)
def process_return():
    """Process a return from POS"""
    try:
        data = request.get_json()

        sale_id = data.get('sale_id')
        return_type = data.get('return_type', 'cash')  # cash or store_credit
        return_reason = data.get('return_reason', '')
        notes = data.get('notes', '')
        items = data.get('items', [])

        if not items:
            return jsonify({'success': False, 'error': 'No items selected for return'}), 400

        sale = Sale.query.get_or_404(sale_id)

        # Calculate total refund amount
        total_refund = Decimal('0')
        for item_data in items:
            qty = int(item_data['quantity'])
            price = Decimal(str(item_data['unit_price']))
            total_refund += qty * price

        if RETURNS_ENABLED:
            # Create return record using the Return model
            ret = Return(
                return_number=generate_return_number(),
                sale_id=sale.id,
                customer_id=sale.customer_id,
                return_type=return_type,
                refund_type=return_type,
                return_reason=return_reason,
                notes=notes,
                processed_by=current_user.id,
                total_amount=total_refund,
                refund_amount=total_refund if return_type == 'cash' else Decimal('0'),
                credit_issued=total_refund if return_type == 'store_credit' else Decimal('0'),
                status='completed'
            )
            db.session.add(ret)
            db.session.flush()

            # Process each return item
            for item_data in items:
                sale_item = SaleItem.query.get(item_data['sale_item_id'])
                if not sale_item:
                    continue

                qty = int(item_data['quantity'])

                # Create return item record
                return_item = ReturnItem(
                    return_id=ret.id,
                    sale_item_id=sale_item.id,
                    product_id=sale_item.product_id,
                    quantity=qty,
                    unit_price=sale_item.unit_price,
                    subtotal=qty * sale_item.unit_price,
                    condition='good',
                    restock=True
                )
                db.session.add(return_item)

                # Restore stock
                product = Product.query.get(sale_item.product_id)
                if product:
                    product.quantity += qty

                    # Create stock movement
                    movement = StockMovement(
                        product_id=product.id,
                        user_id=current_user.id,
                        movement_type='return',
                        quantity=qty,
                        reference=ret.return_number,
                        notes=f'Return from sale {sale.sale_number}'
                    )
                    db.session.add(movement)

            # Handle store credit
            if return_type == 'store_credit' and sale.customer_id:
                customer = Customer.query.get(sale.customer_id)
                if customer:
                    # Get current credit balance
                    last_credit = CustomerCredit.query.filter_by(
                        customer_id=customer.id
                    ).order_by(CustomerCredit.created_at.desc()).first()

                    current_balance = last_credit.balance_after if last_credit else Decimal('0')
                    new_balance = current_balance + total_refund

                    credit = CustomerCredit(
                        customer_id=customer.id,
                        credit_type='return_credit',
                        reference_id=ret.id,
                        amount=total_refund,
                        balance_after=new_balance,
                        description=f'Credit from return {ret.return_number}',
                        created_by=current_user.id
                    )
                    db.session.add(credit)

            return_number = ret.return_number

        else:
            # Fallback: Simple return without Return model
            return_number = generate_return_number()

            for item_data in items:
                sale_item = SaleItem.query.get(item_data['sale_item_id'])
                if not sale_item:
                    continue

                qty = int(item_data['quantity'])

                # Restore stock
                product = Product.query.get(sale_item.product_id)
                if product:
                    product.quantity += qty

                    # Create stock movement
                    movement = StockMovement(
                        product_id=product.id,
                        user_id=current_user.id,
                        movement_type='return',
                        quantity=qty,
                        reference=return_number,
                        notes=f'Return from sale {sale.sale_number} - {return_reason}'
                    )
                    db.session.add(movement)

        # Update sale status if fully returned
        sale.status = 'partial_return'

        db.session.commit()

        return jsonify({
            'success': True,
            'return_number': return_number,
            'return_type': return_type,
            'refund_amount': float(total_refund),
            'message': 'Return processed successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
