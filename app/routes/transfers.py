"""
Stock Transfer Routes

Handles the complete stock transfer workflow between locations:
Request -> Approve -> Dispatch -> Receive
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime

from app.models import (db, Location, LocationStock, Product, StockTransfer,
                        StockTransferItem, StockMovement)
from app.utils.permissions import permission_required, Permissions
from app.utils.location_context import (get_current_location, can_access_location,
                                         generate_transfer_number)

bp = Blueprint('transfers', __name__, url_prefix='/transfers')


@bp.route('/')
@login_required
@permission_required(Permissions.TRANSFER_VIEW)
def index():
    """List transfers for current location or all if admin"""
    location = get_current_location()

    if current_user.is_global_admin or current_user.has_permission(Permissions.TRANSFER_VIEW_ALL):
        # Show all transfers
        transfers = StockTransfer.query.order_by(StockTransfer.created_at.desc()).limit(100).all()
    elif location:
        # Show transfers for current location (incoming and outgoing)
        transfers = StockTransfer.query.filter(
            db.or_(
                StockTransfer.source_location_id == location.id,
                StockTransfer.destination_location_id == location.id
            )
        ).order_by(StockTransfer.created_at.desc()).limit(100).all()
    else:
        transfers = []

    return render_template('transfers/index.html',
                           transfers=transfers,
                           current_location=location)


@bp.route('/pending')
@login_required
@permission_required(Permissions.TRANSFER_APPROVE)
def pending():
    """List pending transfers waiting for approval (for warehouse)"""
    location = get_current_location()

    if current_user.is_global_admin or current_user.has_permission(Permissions.TRANSFER_VIEW_ALL):
        # Show all pending
        transfers = StockTransfer.query.filter_by(status='requested').order_by(
            StockTransfer.priority.desc(),
            StockTransfer.requested_at
        ).all()
    elif location and location.is_warehouse:
        # Show pending for this warehouse
        transfers = StockTransfer.query.filter_by(
            source_location_id=location.id,
            status='requested'
        ).order_by(
            StockTransfer.priority.desc(),
            StockTransfer.requested_at
        ).all()
    else:
        transfers = []

    return render_template('transfers/pending.html',
                           transfers=transfers,
                           current_location=location)


@bp.route('/incoming')
@login_required
@permission_required(Permissions.TRANSFER_RECEIVE)
def incoming():
    """List incoming transfers waiting to be received (for kiosk)"""
    location = get_current_location()

    if not location:
        flash('You must be assigned to a location.', 'warning')
        return redirect(url_for('index'))

    # Show dispatched transfers to this location
    transfers = StockTransfer.query.filter_by(
        destination_location_id=location.id,
        status='dispatched'
    ).order_by(StockTransfer.dispatched_at).all()

    return render_template('transfers/incoming.html',
                           transfers=transfers,
                           current_location=location)


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.TRANSFER_REQUEST)
def create():
    """Create a new transfer request"""
    location = get_current_location()

    if not location:
        flash('You must be assigned to a location to request a transfer.', 'warning')
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            # Get form data
            source_location_id = request.form.get('source_location_id', type=int)
            priority = request.form.get('priority', 'normal')
            expected_date = request.form.get('expected_delivery_date')
            notes = request.form.get('notes', '').strip()

            # Items data
            product_ids = request.form.getlist('product_id[]')
            quantities = request.form.getlist('quantity[]')

            if not source_location_id:
                flash('Please select a source warehouse.', 'danger')
                return redirect(url_for('transfers.create'))

            if not product_ids or not any(q and int(q) > 0 for q in quantities):
                flash('Please add at least one product to the transfer.', 'danger')
                return redirect(url_for('transfers.create'))

            # Create transfer
            transfer = StockTransfer(
                transfer_number=generate_transfer_number(),
                source_location_id=source_location_id,
                destination_location_id=location.id,
                status='requested',
                priority=priority,
                expected_delivery_date=datetime.strptime(expected_date, '%Y-%m-%d').date() if expected_date else None,
                requested_by=current_user.id,
                requested_at=datetime.utcnow(),
                request_notes=notes
            )
            db.session.add(transfer)
            db.session.flush()

            # Add items
            for i, product_id in enumerate(product_ids):
                if product_id and i < len(quantities) and quantities[i]:
                    qty = int(quantities[i])
                    if qty > 0:
                        item = StockTransferItem(
                            transfer_id=transfer.id,
                            product_id=int(product_id),
                            quantity_requested=qty
                        )
                        db.session.add(item)

            db.session.commit()

            flash(f'Transfer request {transfer.transfer_number} created successfully.', 'success')
            return redirect(url_for('transfers.view', id=transfer.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating transfer: {str(e)}', 'danger')
            return redirect(url_for('transfers.create'))

    # GET - show form
    # Get warehouses that can supply this location
    if location.parent_warehouse_id:
        warehouses = [Location.query.get(location.parent_warehouse_id)]
    else:
        warehouses = Location.query.filter_by(location_type='warehouse', is_active=True).all()

    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()

    return render_template('transfers/create.html',
                           current_location=location,
                           warehouses=warehouses,
                           products=products)


@bp.route('/<int:id>')
@login_required
@permission_required(Permissions.TRANSFER_VIEW)
def view(id):
    """View transfer details"""
    transfer = StockTransfer.query.get_or_404(id)

    # Check access
    location = get_current_location()
    if not current_user.is_global_admin and not current_user.has_permission(Permissions.TRANSFER_VIEW_ALL):
        if location:
            if transfer.source_location_id != location.id and transfer.destination_location_id != location.id:
                flash('You do not have permission to view this transfer.', 'danger')
                return redirect(url_for('transfers.index'))
        else:
            flash('Access denied.', 'danger')
            return redirect(url_for('index'))

    # Get items with product details
    items = db.session.query(StockTransferItem, Product).join(
        Product, StockTransferItem.product_id == Product.id
    ).filter(StockTransferItem.transfer_id == id).all()

    return render_template('transfers/view.html',
                           transfer=transfer,
                           items=items,
                           current_location=location)


@bp.route('/<int:id>/approve', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.TRANSFER_APPROVE)
def approve(id):
    """Approve a transfer request"""
    transfer = StockTransfer.query.get_or_404(id)

    if not transfer.can_approve:
        flash('This transfer cannot be approved.', 'warning')
        return redirect(url_for('transfers.view', id=id))

    # Check access - must be at source location (warehouse)
    location = get_current_location()
    if not current_user.is_global_admin:
        if not location or location.id != transfer.source_location_id:
            flash('Only source warehouse can approve this transfer.', 'danger')
            return redirect(url_for('transfers.view', id=id))

    if request.method == 'POST':
        try:
            action = request.form.get('action')

            if action == 'reject':
                # Reject transfer
                transfer.status = 'rejected'
                transfer.rejection_reason = request.form.get('rejection_reason', '').strip()
                db.session.commit()

                flash(f'Transfer {transfer.transfer_number} has been rejected.', 'warning')
                return redirect(url_for('transfers.pending'))

            # Approve transfer
            notes = request.form.get('notes', '').strip()

            # Update approved quantities
            for item in transfer.items:
                approved_qty = request.form.get(f'approved_qty_{item.id}', type=int)
                if approved_qty is not None:
                    item.quantity_approved = approved_qty

                    # Reserve stock at source
                    if approved_qty > 0:
                        source_stock = LocationStock.query.filter_by(
                            location_id=transfer.source_location_id,
                            product_id=item.product_id
                        ).first()
                        if source_stock:
                            source_stock.reserved_quantity += approved_qty

            transfer.status = 'approved'
            transfer.approved_by = current_user.id
            transfer.approved_at = datetime.utcnow()
            transfer.approval_notes = notes
            db.session.commit()

            flash(f'Transfer {transfer.transfer_number} has been approved.', 'success')
            return redirect(url_for('transfers.view', id=id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error approving transfer: {str(e)}', 'danger')

    # GET - show approval form
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

    return render_template('transfers/approve.html',
                           transfer=transfer,
                           items=items)


@bp.route('/<int:id>/dispatch', methods=['POST'])
@login_required
@permission_required(Permissions.TRANSFER_DISPATCH)
def dispatch(id):
    """Mark transfer as dispatched"""
    transfer = StockTransfer.query.get_or_404(id)

    if not transfer.can_dispatch:
        flash('This transfer cannot be dispatched.', 'warning')
        return redirect(url_for('transfers.view', id=id))

    # Check access - must be at source location
    location = get_current_location()
    if not current_user.is_global_admin:
        if not location or location.id != transfer.source_location_id:
            flash('Only source location can dispatch this transfer.', 'danger')
            return redirect(url_for('transfers.view', id=id))

    try:
        notes = request.form.get('notes', '').strip()

        # Deduct stock from source and update dispatched quantities
        for item in transfer.items:
            qty = item.quantity_approved or item.quantity_requested
            item.quantity_dispatched = qty

            # Deduct from source stock
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

            # Create stock movement for outgoing
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
        transfer.dispatch_notes = notes
        db.session.commit()

        flash(f'Transfer {transfer.transfer_number} has been dispatched.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error dispatching transfer: {str(e)}', 'danger')

    return redirect(url_for('transfers.view', id=id))


@bp.route('/<int:id>/receive', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.TRANSFER_RECEIVE)
def receive(id):
    """Receive a transfer at destination"""
    transfer = StockTransfer.query.get_or_404(id)

    if not transfer.can_receive:
        flash('This transfer cannot be received.', 'warning')
        return redirect(url_for('transfers.view', id=id))

    # Check access - must be at destination location
    location = get_current_location()
    if not current_user.is_global_admin:
        if not location or location.id != transfer.destination_location_id:
            flash('Only destination location can receive this transfer.', 'danger')
            return redirect(url_for('transfers.view', id=id))

    if request.method == 'POST':
        try:
            notes = request.form.get('notes', '').strip()

            # Update received quantities and add to destination stock
            for item in transfer.items:
                received_qty = request.form.get(f'received_qty_{item.id}', type=int)
                if received_qty is None:
                    received_qty = item.quantity_dispatched

                item.quantity_received = received_qty

                if received_qty > 0:
                    # Get or create destination stock
                    dest_stock = LocationStock.query.filter_by(
                        location_id=transfer.destination_location_id,
                        product_id=item.product_id
                    ).first()

                    if not dest_stock:
                        product = Product.query.get(item.product_id)
                        dest_stock = LocationStock(
                            location_id=transfer.destination_location_id,
                            product_id=item.product_id,
                            quantity=0,
                            reorder_level=product.reorder_level if product else 10
                        )
                        db.session.add(dest_stock)

                    dest_stock.quantity += received_qty
                    dest_stock.last_movement_at = datetime.utcnow()

                    # Create stock movement for incoming
                    movement = StockMovement(
                        product_id=item.product_id,
                        user_id=current_user.id,
                        movement_type='transfer_in',
                        quantity=received_qty,
                        reference=transfer.transfer_number,
                        notes=f'Transfer from {transfer.source_location.name}',
                        location_id=transfer.destination_location_id,
                        transfer_id=transfer.id
                    )
                    db.session.add(movement)

            transfer.status = 'received'
            transfer.received_by = current_user.id
            transfer.received_at = datetime.utcnow()
            transfer.receive_notes = notes
            db.session.commit()

            flash(f'Transfer {transfer.transfer_number} has been received successfully.', 'success')
            return redirect(url_for('transfers.view', id=id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error receiving transfer: {str(e)}', 'danger')

    # GET - show receive form
    items = []
    for item in transfer.items:
        product = Product.query.get(item.product_id)
        items.append({
            'item': item,
            'product': product
        })

    return render_template('transfers/receive.html',
                           transfer=transfer,
                           items=items)


@bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
@permission_required(Permissions.TRANSFER_CANCEL)
def cancel(id):
    """Cancel a transfer"""
    transfer = StockTransfer.query.get_or_404(id)

    if not transfer.can_cancel:
        flash('This transfer cannot be cancelled.', 'warning')
        return redirect(url_for('transfers.view', id=id))

    try:
        reason = request.form.get('reason', '').strip()

        # Release reserved stock if transfer was approved
        if transfer.status == 'approved':
            for item in transfer.items:
                if item.quantity_approved:
                    source_stock = LocationStock.query.filter_by(
                        location_id=transfer.source_location_id,
                        product_id=item.product_id
                    ).first()
                    if source_stock:
                        source_stock.reserved_quantity -= item.quantity_approved
                        if source_stock.reserved_quantity < 0:
                            source_stock.reserved_quantity = 0

        transfer.status = 'cancelled'
        transfer.rejection_reason = reason
        db.session.commit()

        flash(f'Transfer {transfer.transfer_number} has been cancelled.', 'warning')

    except Exception as e:
        db.session.rollback()
        flash(f'Error cancelling transfer: {str(e)}', 'danger')

    return redirect(url_for('transfers.view', id=id))


@bp.route('/api/search-products')
@login_required
def api_search_products():
    """Search products for transfer with stock at source location"""
    source_id = request.args.get('source_id', type=int)
    query = request.args.get('q', '').strip()

    if not source_id or len(query) < 2:
        return jsonify({'products': []})

    # Search products with stock at source location
    products = db.session.query(Product, LocationStock).outerjoin(
        LocationStock,
        db.and_(
            LocationStock.product_id == Product.id,
            LocationStock.location_id == source_id
        )
    ).filter(
        Product.is_active == True,
        db.or_(
            Product.code.ilike(f'%{query}%'),
            Product.name.ilike(f'%{query}%'),
            Product.barcode.ilike(f'%{query}%')
        )
    ).limit(20).all()

    results = []
    for product, stock in products:
        available = stock.available_quantity if stock else 0
        if available > 0:  # Only show products with available stock
            results.append({
                'id': product.id,
                'code': product.code,
                'name': product.name,
                'barcode': product.barcode,
                'available': available
            })

    return jsonify({'products': results})
