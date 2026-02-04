"""
Batch & Expiry Tracking Routes
Track product batches, expiry dates, and manage batch-wise stock
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import func, and_, or_
from app.models import (db, Product, ProductBatch, BatchMovement, ExpiryAlert,
                        Location, LocationStock, Supplier)
from app.utils.permissions import permission_required, Permissions
from app.utils.location_context import get_current_location

bp = Blueprint('batch_tracking', __name__, url_prefix='/batch-tracking')


# ============================================================================
# BATCH TRACKING DASHBOARD
# ============================================================================

@bp.route('/')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def index():
    """Batch tracking dashboard with expiry alerts"""
    location = get_current_location()

    # Get alert counts
    today = date.today()
    warning_date = today + timedelta(days=30)
    critical_date = today + timedelta(days=7)

    base_filter = [ProductBatch.status == 'active']
    if location and not current_user.is_global_admin:
        base_filter.append(ProductBatch.location_id == location.id)

    # Expired batches
    expired_count = ProductBatch.query.filter(
        *base_filter,
        ProductBatch.expiry_date < today,
        ProductBatch.current_quantity > 0
    ).count()

    # Critical (within 7 days)
    critical_count = ProductBatch.query.filter(
        *base_filter,
        ProductBatch.expiry_date >= today,
        ProductBatch.expiry_date <= critical_date,
        ProductBatch.current_quantity > 0
    ).count()

    # Warning (within 30 days)
    warning_count = ProductBatch.query.filter(
        *base_filter,
        ProductBatch.expiry_date > critical_date,
        ProductBatch.expiry_date <= warning_date,
        ProductBatch.current_quantity > 0
    ).count()

    # Recent batches
    recent_batches = ProductBatch.query.filter(
        *base_filter
    ).order_by(ProductBatch.created_at.desc()).limit(10).all()

    # Total batches
    total_batches = ProductBatch.query.filter(*base_filter).count()
    active_batches = ProductBatch.query.filter(
        *base_filter,
        ProductBatch.current_quantity > 0
    ).count()

    return render_template('batch_tracking/index.html',
                         expired_count=expired_count,
                         critical_count=critical_count,
                         warning_count=warning_count,
                         recent_batches=recent_batches,
                         total_batches=total_batches,
                         active_batches=active_batches,
                         location=location)


# ============================================================================
# EXPIRY REPORT
# ============================================================================

@bp.route('/expiry-report')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def expiry_report():
    """View products by expiry status"""
    location = get_current_location()

    status_filter = request.args.get('status', 'all')  # all, expired, critical, warning, ok
    category_id = request.args.get('category_id', type=int)
    days_ahead = request.args.get('days', 30, type=int)

    today = date.today()
    target_date = today + timedelta(days=days_ahead)

    base_filter = [
        ProductBatch.status == 'active',
        ProductBatch.current_quantity > 0
    ]
    if location and not current_user.is_global_admin:
        base_filter.append(ProductBatch.location_id == location.id)

    if status_filter == 'expired':
        base_filter.append(ProductBatch.expiry_date < today)
    elif status_filter == 'critical':
        base_filter.append(ProductBatch.expiry_date >= today)
        base_filter.append(ProductBatch.expiry_date <= today + timedelta(days=7))
    elif status_filter == 'warning':
        base_filter.append(ProductBatch.expiry_date > today + timedelta(days=7))
        base_filter.append(ProductBatch.expiry_date <= today + timedelta(days=30))
    elif status_filter == 'ok':
        base_filter.append(ProductBatch.expiry_date > today + timedelta(days=30))
    else:
        # All - show batches expiring within days_ahead
        base_filter.append(ProductBatch.expiry_date <= target_date)

    query = ProductBatch.query.filter(*base_filter)

    if category_id:
        query = query.join(Product).filter(Product.category_id == category_id)

    batches = query.order_by(
        ProductBatch.expiry_date.asc().nullslast()
    ).all()

    # Group by status
    grouped = {
        'expired': [],
        'critical': [],
        'warning': [],
        'ok': []
    }
    total_value = Decimal('0')

    for batch in batches:
        value = (batch.unit_cost or Decimal('0')) * batch.current_quantity
        total_value += value
        batch.stock_value = value

        if batch.is_expired:
            grouped['expired'].append(batch)
        elif batch.is_critical_expiry:
            grouped['critical'].append(batch)
        elif batch.is_near_expiry:
            grouped['warning'].append(batch)
        else:
            grouped['ok'].append(batch)

    from app.models import Category
    categories = Category.query.order_by(Category.name).all()

    return render_template('batch_tracking/expiry_report.html',
                         batches=batches,
                         grouped=grouped,
                         total_value=total_value,
                         status_filter=status_filter,
                         days_ahead=days_ahead,
                         categories=categories,
                         category_id=category_id,
                         location=location)


# ============================================================================
# BATCH LIST & MANAGEMENT
# ============================================================================

@bp.route('/batches')
@login_required
@permission_required(Permissions.INVENTORY_VIEW)
def batch_list():
    """List all batches with filters"""
    location = get_current_location()

    product_id = request.args.get('product_id', type=int)
    status = request.args.get('status', 'active')
    search = request.args.get('search', '')

    base_filter = []
    if location and not current_user.is_global_admin:
        base_filter.append(ProductBatch.location_id == location.id)

    if status and status != 'all':
        base_filter.append(ProductBatch.status == status)

    query = ProductBatch.query.filter(*base_filter)

    if product_id:
        query = query.filter(ProductBatch.product_id == product_id)

    if search:
        query = query.join(Product).filter(
            or_(
                Product.name.ilike(f'%{search}%'),
                Product.sku.ilike(f'%{search}%'),
                ProductBatch.batch_number.ilike(f'%{search}%')
            )
        )

    batches = query.order_by(
        ProductBatch.expiry_date.asc().nullslast(),
        ProductBatch.created_at.desc()
    ).all()

    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()

    return render_template('batch_tracking/batch_list.html',
                         batches=batches,
                         products=products,
                         product_id=product_id,
                         status=status,
                         search=search,
                         location=location)


@bp.route('/batches/add', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.INVENTORY_CREATE)
def add_batch():
    """Add a new batch"""
    location = get_current_location()

    if request.method == 'POST':
        product_id = request.form.get('product_id', type=int)
        batch_number = request.form.get('batch_number', '').strip()
        quantity = request.form.get('quantity', type=float)
        unit_cost = request.form.get('unit_cost', type=float)
        manufacture_date = request.form.get('manufacture_date')
        expiry_date = request.form.get('expiry_date')
        supplier_id = request.form.get('supplier_id', type=int)
        notes = request.form.get('notes', '')

        if not product_id or not batch_number or not quantity:
            flash('Product, batch number, and quantity are required.', 'error')
            return redirect(url_for('batch_tracking.add_batch'))

        # Check if batch already exists
        existing = ProductBatch.query.filter_by(
            product_id=product_id,
            location_id=location.id if location else None,
            batch_number=batch_number
        ).first()

        if existing:
            flash(f'Batch {batch_number} already exists for this product at this location.', 'error')
            return redirect(url_for('batch_tracking.add_batch'))

        batch = ProductBatch(
            product_id=product_id,
            location_id=location.id if location else 1,
            batch_number=batch_number,
            initial_quantity=Decimal(str(quantity)),
            current_quantity=Decimal(str(quantity)),
            unit_cost=Decimal(str(unit_cost)) if unit_cost else None,
            total_cost=Decimal(str(quantity * unit_cost)) if unit_cost else None,
            supplier_id=supplier_id if supplier_id else None,
            received_by=current_user.id,
            received_date=date.today(),
            notes=notes
        )

        if manufacture_date:
            batch.manufacture_date = datetime.strptime(manufacture_date, '%Y-%m-%d').date()
        if expiry_date:
            batch.expiry_date = datetime.strptime(expiry_date, '%Y-%m-%d').date()

        db.session.add(batch)

        # Update location stock
        loc_stock = LocationStock.query.filter_by(
            product_id=product_id,
            location_id=location.id if location else 1
        ).first()

        if loc_stock:
            loc_stock.quantity = (loc_stock.quantity or 0) + Decimal(str(quantity))
        else:
            loc_stock = LocationStock(
                product_id=product_id,
                location_id=location.id if location else 1,
                quantity=Decimal(str(quantity))
            )
            db.session.add(loc_stock)

        # Log movement
        movement = BatchMovement(
            batch_id=batch.id,
            movement_type='receive',
            quantity=Decimal(str(quantity)),
            quantity_before=0,
            quantity_after=Decimal(str(quantity)),
            user_id=current_user.id,
            reason='Initial batch receipt',
            notes=notes
        )
        db.session.add(movement)

        db.session.commit()

        flash(f'Batch {batch_number} added successfully with {quantity} units.', 'success')
        return redirect(url_for('batch_tracking.batch_list'))

    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()

    return render_template('batch_tracking/add_batch.html',
                         products=products,
                         suppliers=suppliers,
                         location=location)


@bp.route('/batches/<int:batch_id>')
@login_required
@permission_required(Permissions.INVENTORY_VIEW)
def view_batch(batch_id):
    """View batch details and movement history"""
    batch = ProductBatch.query.get_or_404(batch_id)
    movements = batch.movements.order_by(BatchMovement.created_at.desc()).all()

    return render_template('batch_tracking/view_batch.html',
                         batch=batch,
                         movements=movements)


@bp.route('/batches/<int:batch_id>/adjust', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.INVENTORY_ADJUST)
def adjust_batch(batch_id):
    """Adjust batch quantity"""
    batch = ProductBatch.query.get_or_404(batch_id)

    if request.method == 'POST':
        adjustment_type = request.form.get('adjustment_type')  # add, remove, set
        quantity = request.form.get('quantity', type=float)
        reason = request.form.get('reason', '').strip()

        if not quantity or not reason:
            flash('Quantity and reason are required.', 'error')
            return redirect(url_for('batch_tracking.adjust_batch', batch_id=batch_id))

        old_qty = float(batch.current_quantity)

        if adjustment_type == 'add':
            new_qty = old_qty + quantity
            movement_qty = Decimal(str(quantity))
        elif adjustment_type == 'remove':
            new_qty = max(0, old_qty - quantity)
            movement_qty = -Decimal(str(quantity))
        else:  # set
            new_qty = quantity
            movement_qty = Decimal(str(quantity)) - batch.current_quantity

        batch.current_quantity = Decimal(str(new_qty))

        if new_qty == 0:
            batch.status = 'depleted'

        # Log movement
        movement = BatchMovement(
            batch_id=batch.id,
            movement_type='adjustment',
            quantity=movement_qty,
            quantity_before=Decimal(str(old_qty)),
            quantity_after=Decimal(str(new_qty)),
            user_id=current_user.id,
            reason=reason
        )
        db.session.add(movement)

        # Update location stock
        loc_stock = LocationStock.query.filter_by(
            product_id=batch.product_id,
            location_id=batch.location_id
        ).first()

        if loc_stock:
            loc_stock.quantity = (loc_stock.quantity or 0) + movement_qty

        db.session.commit()

        flash(f'Batch quantity adjusted from {old_qty} to {new_qty}.', 'success')
        return redirect(url_for('batch_tracking.view_batch', batch_id=batch_id))

    return render_template('batch_tracking/adjust_batch.html', batch=batch)


@bp.route('/batches/<int:batch_id>/dispose', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.INVENTORY_ADJUST)
def dispose_batch(batch_id):
    """Dispose of a batch (expired, damaged, etc.)"""
    batch = ProductBatch.query.get_or_404(batch_id)

    if request.method == 'POST':
        reason = request.form.get('reason', '').strip()
        disposal_method = request.form.get('disposal_method', '')
        notes = request.form.get('notes', '')

        if not reason:
            flash('Disposal reason is required.', 'error')
            return redirect(url_for('batch_tracking.dispose_batch', batch_id=batch_id))

        old_qty = float(batch.current_quantity)

        # Log movement
        movement = BatchMovement(
            batch_id=batch.id,
            movement_type='disposal',
            quantity=-batch.current_quantity,
            quantity_before=batch.current_quantity,
            quantity_after=0,
            user_id=current_user.id,
            reason=f'{reason} - {disposal_method}',
            notes=notes
        )
        db.session.add(movement)

        # Update location stock
        loc_stock = LocationStock.query.filter_by(
            product_id=batch.product_id,
            location_id=batch.location_id
        ).first()

        if loc_stock:
            loc_stock.quantity = max(0, (loc_stock.quantity or 0) - batch.current_quantity)

        # Update batch status
        batch.current_quantity = 0
        batch.status = 'disposed'
        batch.disposed_date = date.today()
        batch.disposed_by = current_user.id
        batch.disposal_reason = f'{reason} - {disposal_method}. {notes}'

        # Mark any alerts as resolved
        ExpiryAlert.query.filter_by(batch_id=batch_id, is_resolved=False).update({
            'is_resolved': True,
            'resolved_at': datetime.utcnow(),
            'action_taken': 'disposed',
            'action_date': date.today(),
            'action_by': current_user.id
        })

        db.session.commit()

        flash(f'Batch disposed. {old_qty} units removed from inventory.', 'success')
        return redirect(url_for('batch_tracking.batch_list'))

    return render_template('batch_tracking/dispose_batch.html', batch=batch)


# ============================================================================
# FIFO ALLOCATION API
# ============================================================================

@bp.route('/api/allocate', methods=['POST'])
@login_required
@permission_required(Permissions.POS_CREATE_SALE)
def allocate_from_batches():
    """Allocate stock from batches using FIFO"""
    data = request.get_json()
    product_id = data.get('product_id')
    location_id = data.get('location_id') or (get_current_location().id if get_current_location() else 1)
    quantity_needed = Decimal(str(data.get('quantity', 0)))

    if not product_id or quantity_needed <= 0:
        return jsonify({'success': False, 'error': 'Invalid product or quantity'}), 400

    # Get available batches in FIFO order
    batches = ProductBatch.query.filter(
        ProductBatch.product_id == product_id,
        ProductBatch.location_id == location_id,
        ProductBatch.status == 'active',
        ProductBatch.current_quantity > ProductBatch.reserved_quantity,
        or_(
            ProductBatch.expiry_date.is_(None),
            ProductBatch.expiry_date >= date.today()
        )
    ).order_by(
        ProductBatch.expiry_date.asc().nullslast(),
        ProductBatch.received_date.asc()
    ).all()

    allocations = []
    remaining = quantity_needed

    for batch in batches:
        if remaining <= 0:
            break

        available = batch.available_quantity
        if available <= 0:
            continue

        allocate_qty = min(Decimal(str(available)), remaining)
        allocations.append({
            'batch_id': batch.id,
            'batch_number': batch.batch_number,
            'quantity': float(allocate_qty),
            'expiry_date': batch.expiry_date.isoformat() if batch.expiry_date else None,
            'unit_cost': float(batch.unit_cost) if batch.unit_cost else None
        })
        remaining -= allocate_qty

    if remaining > 0:
        return jsonify({
            'success': False,
            'error': f'Insufficient stock. Short by {float(remaining)} units.',
            'available': float(quantity_needed - remaining),
            'partial_allocations': allocations
        }), 400

    return jsonify({
        'success': True,
        'allocations': allocations,
        'total_allocated': float(quantity_needed)
    })


@bp.route('/api/batches/<int:product_id>')
@login_required
def get_product_batches(product_id):
    """Get available batches for a product"""
    location = get_current_location()
    location_id = request.args.get('location_id', type=int) or (location.id if location else None)

    batches = ProductBatch.query.filter(
        ProductBatch.product_id == product_id,
        ProductBatch.status == 'active',
        ProductBatch.current_quantity > 0
    )

    if location_id:
        batches = batches.filter(ProductBatch.location_id == location_id)

    batches = batches.order_by(
        ProductBatch.expiry_date.asc().nullslast()
    ).all()

    return jsonify({
        'success': True,
        'batches': [{
            'id': b.id,
            'batch_number': b.batch_number,
            'quantity': float(b.current_quantity),
            'available': b.available_quantity,
            'expiry_date': b.expiry_date.isoformat() if b.expiry_date else None,
            'days_until_expiry': b.days_until_expiry,
            'expiry_status': b.expiry_status,
            'unit_cost': float(b.unit_cost) if b.unit_cost else None
        } for b in batches]
    })


# ============================================================================
# GENERATE EXPIRY ALERTS (Background task)
# ============================================================================

@bp.route('/generate-alerts', methods=['POST'])
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def generate_alerts():
    """Generate expiry alerts for all batches"""
    today = date.today()
    warning_threshold = 30  # days
    critical_threshold = 7  # days

    # Get batches that need alerts
    batches = ProductBatch.query.filter(
        ProductBatch.status == 'active',
        ProductBatch.current_quantity > 0,
        ProductBatch.expiry_date.isnot(None),
        ProductBatch.expiry_date <= today + timedelta(days=warning_threshold)
    ).all()

    alerts_created = 0

    for batch in batches:
        # Determine alert type
        if batch.is_expired:
            alert_type = 'expired'
        elif batch.is_critical_expiry:
            alert_type = 'critical'
        else:
            alert_type = 'warning'

        # Check if alert already exists
        existing = ExpiryAlert.query.filter_by(
            batch_id=batch.id,
            alert_type=alert_type,
            is_resolved=False
        ).first()

        if not existing:
            alert = ExpiryAlert(
                batch_id=batch.id,
                alert_type=alert_type,
                alert_date=today,
                expiry_date=batch.expiry_date
            )
            db.session.add(alert)
            alerts_created += 1

    db.session.commit()

    flash(f'{alerts_created} new expiry alerts generated.', 'success')
    return redirect(url_for('batch_tracking.index'))
