"""
Warehouse Dashboard Routes

Provides warehouse-specific views for managing central stock,
approving transfer requests, and monitoring distribution.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func

from app.models import (db, Location, LocationStock, Product, StockTransfer,
                        StockTransferItem, StockMovement, Sale, GatePass, TransferRequest)
from app.utils.permissions import permission_required, Permissions
from app.utils.location_context import get_current_location, warehouse_required

bp = Blueprint('warehouse', __name__, url_prefix='/warehouse')


@bp.route('/')
@login_required
@permission_required(Permissions.WAREHOUSE_VIEW)
def index():
    """Warehouse dashboard overview"""
    location = get_current_location()

    # For warehouse-specific view
    if location and location.is_warehouse:
        warehouse = location
    elif current_user.is_global_admin:
        # Admin can select warehouse
        warehouse = Location.query.filter_by(location_type='warehouse', is_active=True).first()
    else:
        flash('Warehouse access required.', 'warning')
        return redirect(url_for('index'))

    if not warehouse:
        flash('No warehouse configured in the system.', 'warning')
        return redirect(url_for('index'))

    # Get warehouse stats
    total_products = LocationStock.query.filter_by(location_id=warehouse.id).count()
    low_stock_count = LocationStock.query.filter_by(location_id=warehouse.id).filter(
        LocationStock.quantity <= LocationStock.reorder_level
    ).count()

    # Get total stock value
    stock_value = db.session.query(
        func.sum(LocationStock.quantity * Product.cost_price)
    ).join(Product).filter(LocationStock.location_id == warehouse.id).scalar() or 0

    # Pending transfer requests
    pending_requests = StockTransfer.query.filter_by(
        source_location_id=warehouse.id,
        status='requested'
    ).count()

    # Recent transfers
    recent_transfers = StockTransfer.query.filter(
        db.or_(
            StockTransfer.source_location_id == warehouse.id,
            StockTransfer.destination_location_id == warehouse.id
        )
    ).order_by(StockTransfer.created_at.desc()).limit(10).all()

    # Child kiosks
    child_kiosks = Location.query.filter_by(
        parent_warehouse_id=warehouse.id,
        is_active=True
    ).all()

    # Low stock items
    low_stock_items = db.session.query(LocationStock, Product).join(
        Product, LocationStock.product_id == Product.id
    ).filter(
        LocationStock.location_id == warehouse.id,
        LocationStock.quantity <= LocationStock.reorder_level
    ).order_by(LocationStock.quantity).limit(10).all()

    return render_template('warehouse/dashboard.html',
                           warehouse=warehouse,
                           total_products=total_products,
                           low_stock_count=low_stock_count,
                           stock_value=stock_value,
                           pending_requests=pending_requests,
                           recent_transfers=recent_transfers,
                           child_kiosks=child_kiosks,
                           low_stock_items=low_stock_items)


@bp.route('/stock')
@login_required
@permission_required(Permissions.WAREHOUSE_VIEW)
def stock():
    """View all warehouse stock"""
    location = get_current_location()

    if location and location.is_warehouse:
        warehouse = location
    elif current_user.is_global_admin:
        warehouse_id = request.args.get('warehouse_id', type=int)
        if warehouse_id:
            warehouse = Location.query.get_or_404(warehouse_id)
        else:
            warehouse = Location.query.filter_by(location_type='warehouse', is_active=True).first()
    else:
        flash('Warehouse access required.', 'warning')
        return redirect(url_for('index'))

    if not warehouse:
        flash('No warehouse found.', 'warning')
        return redirect(url_for('index'))

    # Get stock with filters
    category_id = request.args.get('category_id', type=int)
    stock_status = request.args.get('stock_status', '')
    search = request.args.get('search', '').strip()

    query = db.session.query(LocationStock, Product).join(
        Product, LocationStock.product_id == Product.id
    ).filter(LocationStock.location_id == warehouse.id)

    if category_id:
        query = query.filter(Product.category_id == category_id)

    if stock_status == 'low':
        query = query.filter(LocationStock.quantity <= LocationStock.reorder_level)
    elif stock_status == 'out':
        query = query.filter(LocationStock.quantity == 0)
    elif stock_status == 'ok':
        query = query.filter(LocationStock.quantity > LocationStock.reorder_level)

    if search:
        query = query.filter(db.or_(
            Product.code.ilike(f'%{search}%'),
            Product.name.ilike(f'%{search}%'),
            Product.barcode.ilike(f'%{search}%')
        ))

    stock_items = query.order_by(Product.name).all()

    # Get all warehouses for admin
    warehouses = []
    if current_user.is_global_admin:
        warehouses = Location.query.filter_by(location_type='warehouse', is_active=True).all()

    return render_template('warehouse/stock.html',
                           warehouse=warehouse,
                           warehouses=warehouses,
                           stock_items=stock_items,
                           filters={
                               'category_id': category_id,
                               'stock_status': stock_status,
                               'search': search
                           })


@bp.route('/requests')
@login_required
@permission_required(Permissions.WAREHOUSE_APPROVE_REQUESTS)
def requests():
    """View pending stock transfer requests"""
    location = get_current_location()

    if location and location.is_warehouse:
        warehouse = location
    elif current_user.is_global_admin:
        warehouse = None  # Show all pending
    else:
        flash('Warehouse access required.', 'warning')
        return redirect(url_for('index'))

    # Get pending requests
    query = StockTransfer.query.filter_by(status='requested')
    if warehouse:
        query = query.filter_by(source_location_id=warehouse.id)

    pending = query.order_by(
        StockTransfer.priority.desc(),
        StockTransfer.requested_at
    ).all()

    # Get approved but not dispatched
    query = StockTransfer.query.filter_by(status='approved')
    if warehouse:
        query = query.filter_by(source_location_id=warehouse.id)

    approved = query.order_by(StockTransfer.approved_at).all()

    return render_template('warehouse/requests.html',
                           warehouse=warehouse,
                           pending=pending,
                           approved=approved)


@bp.route('/analytics')
@login_required
@permission_required(Permissions.WAREHOUSE_VIEW)
def analytics():
    """Warehouse analytics and distribution insights"""
    location = get_current_location()

    if location and location.is_warehouse:
        warehouse = location
    elif current_user.is_global_admin:
        warehouse = Location.query.filter_by(location_type='warehouse', is_active=True).first()
    else:
        flash('Warehouse access required.', 'warning')
        return redirect(url_for('index'))

    if not warehouse:
        flash('No warehouse found.', 'warning')
        return redirect(url_for('index'))

    # Get child kiosks with their stats
    kiosks = Location.query.filter_by(
        parent_warehouse_id=warehouse.id,
        is_active=True
    ).all()

    kiosk_stats = []
    for kiosk in kiosks:
        # Calculate kiosk metrics
        total_stock = db.session.query(func.sum(LocationStock.quantity)).filter_by(
            location_id=kiosk.id
        ).scalar() or 0

        low_stock = LocationStock.query.filter_by(location_id=kiosk.id).filter(
            LocationStock.quantity <= LocationStock.reorder_level
        ).count()

        # Recent sales (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        sales_count = Sale.query.filter(
            Sale.location_id == kiosk.id,
            Sale.sale_date >= thirty_days_ago
        ).count()

        sales_revenue = db.session.query(func.sum(Sale.total)).filter(
            Sale.location_id == kiosk.id,
            Sale.sale_date >= thirty_days_ago
        ).scalar() or 0

        # Pending transfers to this kiosk
        pending_transfers = StockTransfer.query.filter(
            StockTransfer.destination_location_id == kiosk.id,
            StockTransfer.status.in_(['requested', 'approved', 'dispatched'])
        ).count()

        kiosk_stats.append({
            'kiosk': kiosk,
            'total_stock': total_stock,
            'low_stock': low_stock,
            'sales_count': sales_count,
            'sales_revenue': float(sales_revenue),
            'pending_transfers': pending_transfers
        })

    # Transfer statistics
    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    transfers_this_week = StockTransfer.query.filter(
        StockTransfer.source_location_id == warehouse.id,
        StockTransfer.created_at >= datetime.combine(week_ago, datetime.min.time())
    ).count()

    transfers_this_month = StockTransfer.query.filter(
        StockTransfer.source_location_id == warehouse.id,
        StockTransfer.created_at >= datetime.combine(month_ago, datetime.min.time())
    ).count()

    # Top requested products
    top_products = db.session.query(
        Product,
        func.sum(StockTransferItem.quantity_requested).label('total_requested')
    ).join(
        StockTransferItem, Product.id == StockTransferItem.product_id
    ).join(
        StockTransfer, StockTransferItem.transfer_id == StockTransfer.id
    ).filter(
        StockTransfer.source_location_id == warehouse.id,
        StockTransfer.created_at >= datetime.combine(month_ago, datetime.min.time())
    ).group_by(Product.id).order_by(
        func.sum(StockTransferItem.quantity_requested).desc()
    ).limit(10).all()

    return render_template('warehouse/analytics.html',
                           warehouse=warehouse,
                           kiosk_stats=kiosk_stats,
                           transfers_this_week=transfers_this_week,
                           transfers_this_month=transfers_this_month,
                           top_products=top_products)


@bp.route('/bulk-transfer', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.WAREHOUSE_MANAGE_STOCK)
def bulk_transfer():
    """Create bulk transfers to multiple kiosks"""
    location = get_current_location()

    if location and location.is_warehouse:
        warehouse = location
    elif current_user.is_global_admin:
        warehouse = Location.query.filter_by(location_type='warehouse', is_active=True).first()
    else:
        flash('Warehouse access required.', 'warning')
        return redirect(url_for('index'))

    if not warehouse:
        flash('No warehouse found.', 'warning')
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            # Get form data
            product_id = request.form.get('product_id', type=int)
            kiosk_ids = request.form.getlist('kiosk_id[]')
            quantities = request.form.getlist('quantity[]')
            notes = request.form.get('notes', '').strip()

            if not product_id:
                flash('Please select a product.', 'danger')
                return redirect(url_for('warehouse.bulk_transfer'))

            product = Product.query.get_or_404(product_id)

            # Check warehouse stock
            warehouse_stock = LocationStock.query.filter_by(
                location_id=warehouse.id,
                product_id=product_id
            ).first()

            if not warehouse_stock:
                flash('Product not available in warehouse.', 'danger')
                return redirect(url_for('warehouse.bulk_transfer'))

            total_qty = sum(int(q) for q in quantities if q)
            if total_qty > warehouse_stock.available_quantity:
                flash(f'Insufficient stock. Available: {warehouse_stock.available_quantity}', 'danger')
                return redirect(url_for('warehouse.bulk_transfer'))

            # Create transfers for each kiosk
            from app.utils.location_context import generate_transfer_number

            created = 0
            for i, kiosk_id in enumerate(kiosk_ids):
                if kiosk_id and i < len(quantities) and quantities[i]:
                    qty = int(quantities[i])
                    if qty > 0:
                        transfer = StockTransfer(
                            transfer_number=generate_transfer_number(),
                            source_location_id=warehouse.id,
                            destination_location_id=int(kiosk_id),
                            status='approved',  # Pre-approved by warehouse
                            priority='normal',
                            requested_by=current_user.id,
                            requested_at=datetime.utcnow(),
                            approved_by=current_user.id,
                            approved_at=datetime.utcnow(),
                            request_notes=notes
                        )
                        db.session.add(transfer)
                        db.session.flush()

                        item = StockTransferItem(
                            transfer_id=transfer.id,
                            product_id=product_id,
                            quantity_requested=qty,
                            quantity_approved=qty
                        )
                        db.session.add(item)

                        # Reserve stock
                        warehouse_stock.reserved_quantity += qty
                        created += 1

            db.session.commit()
            flash(f'Created {created} transfer(s) for {product.name}.', 'success')
            return redirect(url_for('warehouse.requests'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating transfers: {str(e)}', 'danger')

    # GET - show form
    kiosks = Location.query.filter_by(
        parent_warehouse_id=warehouse.id,
        is_active=True
    ).order_by(Location.name).all()

    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()

    return render_template('warehouse/bulk_transfer.html',
                           warehouse=warehouse,
                           kiosks=kiosks,
                           products=products)


@bp.route('/api/stock/<int:product_id>')
@login_required
def api_product_stock(product_id):
    """Get warehouse stock for a product"""
    location = get_current_location()

    if location and location.is_warehouse:
        warehouse = location
    elif current_user.is_global_admin:
        warehouse_id = request.args.get('warehouse_id', type=int)
        warehouse = Location.query.get(warehouse_id) if warehouse_id else None
    else:
        return jsonify({'error': 'Access denied'}), 403

    if not warehouse:
        return jsonify({'error': 'Warehouse not found'}), 404

    stock = LocationStock.query.filter_by(
        location_id=warehouse.id,
        product_id=product_id
    ).first()

    product = Product.query.get_or_404(product_id)

    return jsonify({
        'product': {
            'id': product.id,
            'code': product.code,
            'name': product.name
        },
        'stock': {
            'quantity': stock.quantity if stock else 0,
            'available': stock.available_quantity if stock else 0,
            'reserved': stock.reserved_quantity if stock else 0
        }
    })


# ============================================================================
# GATE PASS MANAGEMENT
# ============================================================================

def generate_gate_pass_number():
    """Generate unique gate pass number"""
    today = datetime.utcnow()
    prefix = f"GP-{today.strftime('%Y%m%d')}"

    # Find last gate pass today
    last_gp = GatePass.query.filter(
        GatePass.gate_pass_number.like(f'{prefix}%')
    ).order_by(GatePass.id.desc()).first()

    if last_gp:
        try:
            last_num = int(last_gp.gate_pass_number.split('-')[-1])
            new_num = last_num + 1
        except:
            new_num = 1
    else:
        new_num = 1

    return f"{prefix}-{new_num:04d}"


@bp.route('/gate-passes')
@login_required
@permission_required(Permissions.WAREHOUSE_VIEW)
def gate_passes():
    """List all gate passes"""
    location = get_current_location()

    if location and location.is_warehouse:
        warehouse = location
    elif current_user.is_global_admin:
        warehouse = None  # Show all
    else:
        flash('Warehouse access required.', 'warning')
        return redirect(url_for('index'))

    # Filter by status
    status = request.args.get('status', '')
    search = request.args.get('search', '').strip()

    query = GatePass.query

    if warehouse:
        query = query.join(StockTransfer).filter(
            StockTransfer.source_location_id == warehouse.id
        )

    if status:
        query = query.filter(GatePass.status == status)

    if search:
        query = query.filter(db.or_(
            GatePass.gate_pass_number.ilike(f'%{search}%'),
            GatePass.vehicle_number.ilike(f'%{search}%'),
            GatePass.driver_name.ilike(f'%{search}%')
        ))

    gate_passes = query.order_by(GatePass.created_at.desc()).limit(100).all()

    return render_template('warehouse/gate_passes.html',
                           warehouse=warehouse,
                           gate_passes=gate_passes,
                           filters={'status': status, 'search': search})


@bp.route('/gate-pass/<int:id>')
@login_required
@permission_required(Permissions.WAREHOUSE_VIEW)
def view_gate_pass(id):
    """View gate pass details"""
    gate_pass = GatePass.query.get_or_404(id)

    # Get items with product details
    items = []
    if gate_pass.transfer:
        for item in gate_pass.transfer.items:
            product = Product.query.get(item.product_id)
            items.append({
                'item': item,
                'product': product
            })

    return render_template('warehouse/gate_pass_view.html',
                           gate_pass=gate_pass,
                           items=items)


@bp.route('/gate-pass/<int:id>/print')
@login_required
@permission_required(Permissions.WAREHOUSE_VIEW)
def print_gate_pass(id):
    """Printable gate pass"""
    gate_pass = GatePass.query.get_or_404(id)

    # Get items with product details
    items = []
    if gate_pass.transfer:
        for item in gate_pass.transfer.items:
            product = Product.query.get(item.product_id)
            items.append({
                'item': item,
                'product': product
            })

    # Get business info from settings
    from app.models import Setting
    business_name = Setting.query.filter_by(key='business_name').first()
    business_address = Setting.query.filter_by(key='business_address').first()
    business_phone = Setting.query.filter_by(key='business_phone').first()

    return render_template('warehouse/gate_pass_print.html',
                           gate_pass=gate_pass,
                           items=items,
                           business_name=business_name.value if business_name else 'Warehouse',
                           business_address=business_address.value if business_address else '',
                           business_phone=business_phone.value if business_phone else '')


@bp.route('/gate-pass/create/<int:transfer_id>', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.TRANSFER_DISPATCH)
def create_gate_pass(transfer_id):
    """Create gate pass for a transfer"""
    transfer = StockTransfer.query.get_or_404(transfer_id)

    # Check if gate pass already exists
    if transfer.gate_pass:
        flash('Gate pass already exists for this transfer.', 'warning')
        return redirect(url_for('warehouse.view_gate_pass', id=transfer.gate_pass.id))

    # Check transfer status
    if transfer.status not in ['approved', 'dispatched']:
        flash('Cannot create gate pass for this transfer status.', 'warning')
        return redirect(url_for('transfers.view', id=transfer_id))

    if request.method == 'POST':
        try:
            gate_pass = GatePass(
                gate_pass_number=generate_gate_pass_number(),
                transfer_id=transfer_id,
                vehicle_number=request.form.get('vehicle_number', '').strip().upper(),
                vehicle_type=request.form.get('vehicle_type', ''),
                driver_name=request.form.get('driver_name', '').strip(),
                driver_phone=request.form.get('driver_phone', '').strip(),
                driver_cnic=request.form.get('driver_cnic', '').strip(),
                expected_arrival=datetime.strptime(
                    request.form.get('expected_arrival'), '%Y-%m-%dT%H:%M'
                ) if request.form.get('expected_arrival') else None,
                security_seal_number=request.form.get('security_seal_number', '').strip(),
                dispatch_notes=request.form.get('dispatch_notes', '').strip(),
                special_instructions=request.form.get('special_instructions', '').strip(),
                created_by=current_user.id,
                status='issued'
            )
            gate_pass.calculate_totals()
            db.session.add(gate_pass)
            db.session.commit()

            flash(f'Gate pass {gate_pass.gate_pass_number} created successfully.', 'success')
            return redirect(url_for('warehouse.view_gate_pass', id=gate_pass.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating gate pass: {str(e)}', 'danger')

    # GET - show form
    items = []
    for item in transfer.items:
        product = Product.query.get(item.product_id)
        items.append({
            'item': item,
            'product': product
        })

    return render_template('warehouse/gate_pass_create.html',
                           transfer=transfer,
                           items=items)


@bp.route('/gate-pass/<int:id>/update-status', methods=['POST'])
@login_required
@permission_required(Permissions.WAREHOUSE_MANAGE_STOCK)
def update_gate_pass_status(id):
    """Update gate pass status"""
    gate_pass = GatePass.query.get_or_404(id)

    new_status = request.form.get('status')
    valid_statuses = ['issued', 'in_transit', 'delivered', 'verified', 'discrepancy']

    if new_status not in valid_statuses:
        flash('Invalid status.', 'danger')
        return redirect(url_for('warehouse.view_gate_pass', id=id))

    try:
        gate_pass.status = new_status

        if new_status == 'delivered':
            gate_pass.actual_arrival = datetime.utcnow()
        elif new_status == 'verified':
            gate_pass.verified_by = current_user.id
            gate_pass.verification_notes = request.form.get('notes', '').strip()

        db.session.commit()
        flash(f'Gate pass status updated to {new_status}.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error updating status: {str(e)}', 'danger')

    return redirect(url_for('warehouse.view_gate_pass', id=id))


# ============================================================================
# DETAILED REQUEST MANAGEMENT
# ============================================================================

@bp.route('/request/<int:id>')
@login_required
@permission_required(Permissions.WAREHOUSE_VIEW)
def view_request(id):
    """View detailed transfer request"""
    transfer = StockTransfer.query.get_or_404(id)

    # Get items with full product details
    items = []
    for item in transfer.items:
        product = Product.query.get(item.product_id)

        # Get stock at source and destination
        source_stock = LocationStock.query.filter_by(
            location_id=transfer.source_location_id,
            product_id=item.product_id
        ).first()

        dest_stock = LocationStock.query.filter_by(
            location_id=transfer.destination_location_id,
            product_id=item.product_id
        ).first()

        items.append({
            'item': item,
            'product': product,
            'source_stock': source_stock.quantity if source_stock else 0,
            'source_available': source_stock.available_quantity if source_stock else 0,
            'dest_stock': dest_stock.quantity if dest_stock else 0,
            'unit_value': float(product.cost_price) if product else 0,
            'total_value': float(product.cost_price) * (item.quantity_approved or item.quantity_requested) if product else 0
        })

    # Calculate totals
    total_qty_requested = sum(item['item'].quantity_requested for item in items)
    total_qty_approved = sum(item['item'].quantity_approved or 0 for item in items)
    total_value = sum(item['total_value'] for item in items)

    # Get transfer request details if exists
    request_details = transfer.request_details if hasattr(transfer, 'request_details') else None

    # Get related stock movements
    movements = StockMovement.query.filter_by(transfer_id=transfer.id).order_by(
        StockMovement.timestamp
    ).all()

    return render_template('warehouse/request_details.html',
                           transfer=transfer,
                           items=items,
                           total_qty_requested=total_qty_requested,
                           total_qty_approved=total_qty_approved,
                           total_value=total_value,
                           request_details=request_details,
                           movements=movements)


@bp.route('/request/<int:id>/dispatch', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.TRANSFER_DISPATCH)
def dispatch_request(id):
    """Dispatch transfer with gate pass creation"""
    transfer = StockTransfer.query.get_or_404(id)

    if not transfer.can_dispatch:
        flash('This transfer cannot be dispatched.', 'warning')
        return redirect(url_for('warehouse.view_request', id=id))

    location = get_current_location()
    if not current_user.is_global_admin:
        if not location or location.id != transfer.source_location_id:
            flash('Only source warehouse can dispatch this transfer.', 'danger')
            return redirect(url_for('warehouse.view_request', id=id))

    if request.method == 'POST':
        try:
            # Create gate pass first
            gate_pass = GatePass(
                gate_pass_number=generate_gate_pass_number(),
                transfer_id=transfer.id,
                vehicle_number=request.form.get('vehicle_number', '').strip().upper(),
                vehicle_type=request.form.get('vehicle_type', ''),
                driver_name=request.form.get('driver_name', '').strip(),
                driver_phone=request.form.get('driver_phone', '').strip(),
                driver_cnic=request.form.get('driver_cnic', '').strip(),
                expected_arrival=datetime.strptime(
                    request.form.get('expected_arrival'), '%Y-%m-%dT%H:%M'
                ) if request.form.get('expected_arrival') else None,
                security_seal_number=request.form.get('security_seal_number', '').strip(),
                dispatch_notes=request.form.get('dispatch_notes', '').strip(),
                special_instructions=request.form.get('special_instructions', '').strip(),
                created_by=current_user.id,
                status='issued'
            )

            # Deduct stock and mark dispatched
            for item in transfer.items:
                qty = item.quantity_approved or item.quantity_requested
                item.quantity_dispatched = qty

                source_stock = LocationStock.query.filter_by(
                    location_id=transfer.source_location_id,
                    product_id=item.product_id
                ).first()

                if source_stock:
                    source_stock.quantity -= qty
                    source_stock.reserved_quantity -= qty
                    if source_stock.quantity < 0:
                        source_stock.quantity = 0
                    if source_stock.reserved_quantity < 0:
                        source_stock.reserved_quantity = 0
                    source_stock.last_movement_at = datetime.utcnow()

                # Create stock movement
                movement = StockMovement(
                    product_id=item.product_id,
                    user_id=current_user.id,
                    movement_type='transfer_out',
                    quantity=-qty,
                    reference=transfer.transfer_number,
                    notes=f'Transfer to {transfer.destination_location.name}',
                    location_id=transfer.source_location_id,
                    transfer_id=transfer.id
                )
                db.session.add(movement)

            transfer.status = 'dispatched'
            transfer.dispatched_by = current_user.id
            transfer.dispatched_at = datetime.utcnow()
            transfer.dispatch_notes = request.form.get('dispatch_notes', '').strip()

            gate_pass.calculate_totals()
            db.session.add(gate_pass)
            db.session.commit()

            flash(f'Transfer dispatched. Gate pass {gate_pass.gate_pass_number} created.', 'success')
            return redirect(url_for('warehouse.print_gate_pass', id=gate_pass.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error dispatching: {str(e)}', 'danger')

    # GET - show dispatch form
    items = []
    for item in transfer.items:
        product = Product.query.get(item.product_id)
        source_stock = LocationStock.query.filter_by(
            location_id=transfer.source_location_id,
            product_id=item.product_id
        ).first()
        items.append({
            'item': item,
            'product': product,
            'available': source_stock.available_quantity if source_stock else 0
        })

    return render_template('warehouse/dispatch_form.html',
                           transfer=transfer,
                           items=items)
