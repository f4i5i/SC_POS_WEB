"""
Purchase Order Routes
Handles purchase orders, draft management, and receiving
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from decimal import Decimal
from datetime import datetime
from app.models import db, Supplier, Product, PurchaseOrder, PurchaseOrderItem, Location, LocationStock
from app.services.reorder_service import (
    generate_draft_pos_from_low_stock,
    get_draft_pos_for_review,
    submit_draft_po,
    delete_draft_po,
    get_low_stock_by_supplier,
    generate_po_number
)
from app.utils.permissions import permission_required, Permissions

bp = Blueprint('purchase_orders', __name__, url_prefix='/purchase-orders')


@bp.route('/')
@login_required
@permission_required(Permissions.PO_VIEW)
def index():
    """List all purchase orders"""
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('ITEMS_PER_PAGE', 20)
    status = request.args.get('status', '')
    supplier_id = request.args.get('supplier_id', type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = PurchaseOrder.query

    if status:
        query = query.filter_by(status=status)
    if supplier_id:
        query = query.filter_by(supplier_id=supplier_id)
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(PurchaseOrder.order_date >= from_date)
        except:
            pass
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(PurchaseOrder.order_date <= to_date)
        except:
            pass

    orders = query.order_by(PurchaseOrder.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()

    # Calculate totals
    total_amount = sum(float(o.total or 0) for o in orders.items)

    return render_template('purchase_orders/index.html',
                          orders=orders,
                          suppliers=suppliers,
                          total_amount=total_amount)


@bp.route('/drafts')
@login_required
@permission_required(Permissions.PO_VIEW)
def drafts():
    """View all draft POs for review"""
    draft_pos = get_draft_pos_for_review()

    # Group by supplier for better organization
    grouped_drafts = {}
    for po in draft_pos:
        supplier_id = po.supplier_id
        if supplier_id not in grouped_drafts:
            grouped_drafts[supplier_id] = {
                'supplier': po.supplier,
                'orders': []
            }
        grouped_drafts[supplier_id]['orders'].append(po)

    # Get low stock items not yet in any draft
    low_stock_data = get_low_stock_by_supplier()

    return render_template('purchase_orders/drafts.html',
                          grouped_drafts=grouped_drafts,
                          low_stock_data=low_stock_data)


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.PO_CREATE)
def create():
    """Create new purchase order manually"""
    if request.method == 'POST':
        try:
            supplier_id = request.form.get('supplier_id', type=int)
            notes = request.form.get('notes', '').strip()
            expected_date_str = request.form.get('expected_date', '')

            if not supplier_id:
                flash('Please select a supplier', 'danger')
                return redirect(url_for('purchase_orders.create'))

            # Create PO
            po = PurchaseOrder(
                po_number=generate_po_number(),
                supplier_id=supplier_id,
                user_id=current_user.id,
                status='draft',
                is_auto_generated=False,
                source_type='manual',
                notes=notes,
                order_date=datetime.utcnow()
            )

            if expected_date_str:
                try:
                    po.expected_date = datetime.strptime(expected_date_str, '%Y-%m-%d')
                except:
                    pass

            db.session.add(po)
            db.session.commit()

            flash(f'Purchase Order {po.po_number} created', 'success')
            return redirect(url_for('purchase_orders.edit', id=po.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating PO: {str(e)}', 'danger')

    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    return render_template('purchase_orders/create.html', suppliers=suppliers)


@bp.route('/<int:id>')
@login_required
@permission_required(Permissions.PO_VIEW)
def view(id):
    """View purchase order details"""
    po = PurchaseOrder.query.get_or_404(id)
    return render_template('purchase_orders/view.html', po=po)


@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.PO_CREATE)
def edit(id):
    """Edit draft purchase order"""
    po = PurchaseOrder.query.get_or_404(id)

    if po.status != 'draft':
        flash('Only draft POs can be edited', 'warning')
        return redirect(url_for('purchase_orders.view', id=id))

    if request.method == 'POST':
        try:
            action = request.form.get('action')

            if action == 'add_item':
                product_id = request.form.get('product_id', type=int)
                quantity = request.form.get('quantity', type=int)

                if not product_id or not quantity or quantity <= 0:
                    flash('Invalid product or quantity', 'danger')
                    return redirect(url_for('purchase_orders.edit', id=id))

                product = Product.query.get(product_id)
                if not product:
                    flash('Product not found', 'danger')
                    return redirect(url_for('purchase_orders.edit', id=id))

                # Check if item already exists
                existing_item = PurchaseOrderItem.query.filter_by(
                    po_id=po.id, product_id=product_id
                ).first()

                if existing_item:
                    existing_item.quantity_ordered = quantity
                    existing_item.unit_cost = product.base_cost or Decimal('0')
                    existing_item.subtotal = existing_item.unit_cost * quantity
                    existing_item.base_cost = product.base_cost or Decimal('0')
                    existing_item.packaging_cost = product.packaging_cost or Decimal('0')
                    existing_item.delivery_cost = product.delivery_cost or Decimal('0')
                    existing_item.bottle_cost = product.bottle_cost or Decimal('0')
                    existing_item.calculate_landed_cost()
                else:
                    item = PurchaseOrderItem(
                        po_id=po.id,
                        product_id=product_id,
                        quantity_ordered=quantity,
                        unit_cost=product.base_cost or Decimal('0'),
                        subtotal=(product.base_cost or Decimal('0')) * quantity,
                        base_cost=product.base_cost or Decimal('0'),
                        packaging_cost=product.packaging_cost or Decimal('0'),
                        delivery_cost=product.delivery_cost or Decimal('0'),
                        bottle_cost=product.bottle_cost or Decimal('0')
                    )
                    item.calculate_landed_cost()
                    db.session.add(item)

                po.calculate_totals()
                db.session.commit()
                flash('Item added to PO', 'success')

            elif action == 'remove_item':
                item_id = request.form.get('item_id', type=int)
                item = PurchaseOrderItem.query.get(item_id)
                if item and item.po_id == po.id:
                    db.session.delete(item)
                    po.calculate_totals()
                    db.session.commit()
                    flash('Item removed from PO', 'success')

            elif action == 'update_quantity':
                item_id = request.form.get('item_id', type=int)
                quantity = request.form.get('quantity', type=int)
                item = PurchaseOrderItem.query.get(item_id)
                if item and item.po_id == po.id and quantity > 0:
                    item.quantity_ordered = quantity
                    item.subtotal = item.unit_cost * quantity
                    po.calculate_totals()
                    db.session.commit()
                    flash('Quantity updated', 'success')

            elif action == 'update_notes':
                po.notes = request.form.get('notes', '').strip()
                expected_date_str = request.form.get('expected_date', '')
                if expected_date_str:
                    try:
                        po.expected_date = datetime.strptime(expected_date_str, '%Y-%m-%d')
                    except:
                        pass
                db.session.commit()
                flash('PO details updated', 'success')

            return redirect(url_for('purchase_orders.edit', id=id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')

    # Get products from this supplier
    products = Product.query.filter_by(
        supplier_id=po.supplier_id,
        is_active=True
    ).order_by(Product.name).all()

    return render_template('purchase_orders/edit.html', po=po, products=products)


@bp.route('/<int:id>/submit', methods=['POST'])
@login_required
@permission_required(Permissions.PO_APPROVE)
def submit(id):
    """Submit draft PO to supplier"""
    result = submit_draft_po(id, current_user.id)

    if result['success']:
        flash(f'Purchase Order {result["po_number"]} submitted to supplier', 'success')
    else:
        flash(f'Error: {result["error"]}', 'danger')

    return redirect(url_for('purchase_orders.view', id=id))


@bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@permission_required(Permissions.PO_CREATE)
def delete(id):
    """Delete draft PO"""
    result = delete_draft_po(id)

    if result['success']:
        flash(result['message'], 'success')
        return redirect(url_for('purchase_orders.drafts'))
    else:
        flash(f'Error: {result["error"]}', 'danger')
        return redirect(url_for('purchase_orders.view', id=id))


@bp.route('/<int:id>/receive', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.PO_RECEIVE)
def receive(id):
    """Receive goods against a PO"""
    po = PurchaseOrder.query.get_or_404(id)

    if po.status not in ['ordered', 'partial']:
        flash('This PO cannot be received', 'warning')
        return redirect(url_for('purchase_orders.view', id=id))

    # Get warehouse location for receiving
    warehouse = Location.query.filter_by(
        location_type='warehouse',
        is_active=True
    ).first()

    if request.method == 'POST':
        try:
            receiving_location_id = request.form.get('receiving_location_id', type=int) or (warehouse.id if warehouse else None)
            po.receiving_location_id = receiving_location_id
            po.received_date = datetime.utcnow()

            all_received = True
            any_received = False

            # Process each item
            for item in po.items:
                qty_received = request.form.get(f'qty_{item.id}', type=int) or 0
                if qty_received > 0:
                    any_received = True
                    item.quantity_received = (item.quantity_received or 0) + qty_received
                    item.received_at = datetime.utcnow()
                    item.received_by = current_user.id

                    # Update cost breakdown from form if provided
                    base_cost = request.form.get(f'base_cost_{item.id}', type=float)
                    packaging_cost = request.form.get(f'packaging_cost_{item.id}', type=float)
                    delivery_cost = request.form.get(f'delivery_cost_{item.id}', type=float)
                    bottle_cost = request.form.get(f'bottle_cost_{item.id}', type=float)

                    if base_cost is not None:
                        item.base_cost = Decimal(str(base_cost))
                    if packaging_cost is not None:
                        item.packaging_cost = Decimal(str(packaging_cost))
                    if delivery_cost is not None:
                        item.delivery_cost = Decimal(str(delivery_cost))
                    if bottle_cost is not None:
                        item.bottle_cost = Decimal(str(bottle_cost))

                    item.calculate_landed_cost()

                    # Update product cost breakdown
                    product = item.product
                    if product:
                        product.base_cost = item.base_cost
                        product.packaging_cost = item.packaging_cost
                        product.delivery_cost = item.delivery_cost
                        product.bottle_cost = item.bottle_cost
                        product.update_cost_price()

                    # Add to warehouse/receiving location stock
                    if receiving_location_id:
                        location_stock = LocationStock.query.filter_by(
                            location_id=receiving_location_id,
                            product_id=item.product_id
                        ).first()

                        if location_stock:
                            location_stock.quantity += qty_received
                        else:
                            location_stock = LocationStock(
                                location_id=receiving_location_id,
                                product_id=item.product_id,
                                quantity=qty_received
                            )
                            db.session.add(location_stock)

                        # Update product's main quantity
                        product.quantity = (product.quantity or 0) + qty_received

                if item.quantity_received < item.quantity_ordered:
                    all_received = False

            # Update PO status
            if all_received:
                po.status = 'received'
            elif any_received:
                po.status = 'partial'

            po.calculate_totals()
            db.session.commit()

            flash('Goods received successfully', 'success')
            return redirect(url_for('purchase_orders.view', id=id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error receiving goods: {str(e)}', 'danger')

    # Get all warehouse locations for selection
    warehouses = Location.query.filter_by(
        location_type='warehouse',
        is_active=True
    ).all()

    return render_template('purchase_orders/receive.html',
                          po=po,
                          warehouses=warehouses,
                          default_warehouse=warehouse)


@bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
@permission_required(Permissions.PO_APPROVE)
def cancel(id):
    """Cancel a PO"""
    po = PurchaseOrder.query.get_or_404(id)

    if po.status in ['received', 'cancelled']:
        flash('This PO cannot be cancelled', 'warning')
        return redirect(url_for('purchase_orders.view', id=id))

    try:
        # If already ordered, reverse the supplier balance
        if po.status == 'ordered':
            supplier = po.supplier
            if supplier:
                supplier.current_balance = (supplier.current_balance or Decimal('0')) - (po.total or Decimal('0'))

        po.status = 'cancelled'
        db.session.commit()
        flash(f'Purchase Order {po.po_number} cancelled', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error cancelling PO: {str(e)}', 'danger')

    return redirect(url_for('purchase_orders.view', id=id))


# API Endpoints

@bp.route('/api/generate-from-low-stock', methods=['POST'])
@login_required
@permission_required(Permissions.PO_CREATE)
def api_generate_from_low_stock():
    """API: Generate draft POs from low stock items"""
    result = generate_draft_pos_from_low_stock(current_user.id)
    return jsonify(result)


@bp.route('/api/low-stock-summary')
@login_required
@permission_required(Permissions.PO_VIEW)
def api_low_stock_summary():
    """API: Get low stock summary grouped by supplier"""
    low_stock_data = get_low_stock_by_supplier()

    summary = []
    for supplier_id, data in low_stock_data.items():
        supplier = data['supplier']
        products = data['products']

        # Check if draft PO exists
        existing_draft = PurchaseOrder.query.filter_by(
            supplier_id=supplier_id,
            status='draft'
        ).first()

        summary.append({
            'supplier_id': supplier_id,
            'supplier_name': supplier.name if supplier else 'Unknown',
            'product_count': len(products),
            'has_draft_po': existing_draft is not None,
            'draft_po_number': existing_draft.po_number if existing_draft else None,
            'products': [{
                'id': p.id,
                'name': p.name,
                'code': p.code,
                'current_stock': p.quantity,
                'reorder_level': p.reorder_level,
                'reorder_quantity': p.reorder_quantity
            } for p in products]
        })

    return jsonify(summary)


@bp.route('/api/supplier/<int:supplier_id>/products')
@login_required
def api_supplier_products(supplier_id):
    """API: Get products for a specific supplier"""
    products = Product.query.filter_by(
        supplier_id=supplier_id,
        is_active=True
    ).order_by(Product.name).all()

    return jsonify([{
        'id': p.id,
        'code': p.code,
        'name': p.name,
        'base_cost': float(p.base_cost or 0),
        'current_stock': p.quantity,
        'reorder_level': p.reorder_level,
        'reorder_quantity': p.reorder_quantity,
        'is_low_stock': p.quantity <= p.reorder_level
    } for p in products])
