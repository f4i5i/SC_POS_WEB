"""
Location Management Routes

Handles CRUD operations for locations (kiosks and warehouses),
location stock management, and location-related operations.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime

from app.models import db, Location, LocationStock, Product, User
from app.utils.permissions import permission_required, Permissions
from app.utils.location_context import get_current_location, can_access_location

bp = Blueprint('locations', __name__, url_prefix='/locations')


@bp.route('/')
@login_required
@permission_required(Permissions.LOCATION_VIEW)
def index():
    """List all locations the user can access"""
    if current_user.is_global_admin or current_user.has_permission(Permissions.LOCATION_VIEW_ALL):
        locations = Location.query.filter_by(is_active=True).order_by(Location.location_type, Location.name).all()
    else:
        locations = current_user.get_accessible_locations()

    # Get counts for each location
    warehouses = [loc for loc in locations if loc.is_warehouse]
    kiosks = [loc for loc in locations if loc.is_kiosk]

    return render_template('locations/index.html',
                           locations=locations,
                           warehouses=warehouses,
                           kiosks=kiosks)


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.LOCATION_CREATE)
def create():
    """Create a new location"""
    if request.method == 'POST':
        try:
            # Get form data
            code = request.form.get('code', '').strip().upper()
            name = request.form.get('name', '').strip()
            location_type = request.form.get('location_type', 'kiosk')
            address = request.form.get('address', '').strip()
            city = request.form.get('city', '').strip()
            phone = request.form.get('phone', '').strip()
            email = request.form.get('email', '').strip()
            parent_warehouse_id = request.form.get('parent_warehouse_id')
            manager_id = request.form.get('manager_id')
            can_sell = request.form.get('can_sell') == 'on'

            # Validate required fields
            if not code or not name:
                flash('Code and name are required.', 'danger')
                return redirect(url_for('locations.create'))

            # Check for duplicate code
            existing = Location.query.filter_by(code=code).first()
            if existing:
                flash(f'Location with code {code} already exists.', 'danger')
                return redirect(url_for('locations.create'))

            # Create location
            location = Location(
                code=code,
                name=name,
                location_type=location_type,
                address=address,
                city=city,
                phone=phone,
                email=email,
                parent_warehouse_id=int(parent_warehouse_id) if parent_warehouse_id else None,
                manager_id=int(manager_id) if manager_id else None,
                can_sell=can_sell if location_type == 'kiosk' else False,
                is_active=True
            )

            db.session.add(location)
            db.session.commit()

            flash(f'Location "{name}" created successfully.', 'success')
            return redirect(url_for('locations.view', id=location.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating location: {str(e)}', 'danger')
            return redirect(url_for('locations.create'))

    # GET request - show form
    warehouses = Location.query.filter_by(location_type='warehouse', is_active=True).all()
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()

    return render_template('locations/create.html',
                           warehouses=warehouses,
                           users=users)


@bp.route('/<int:id>')
@login_required
@permission_required(Permissions.LOCATION_VIEW)
def view(id):
    """View location details"""
    location = Location.query.get_or_404(id)

    # Check access
    if not current_user.is_global_admin and not current_user.has_permission(Permissions.LOCATION_VIEW_ALL):
        if not can_access_location(id):
            flash('You do not have permission to view this location.', 'danger')
            return redirect(url_for('locations.index'))

    # Get stock summary for this location
    stock_items = LocationStock.query.filter_by(location_id=id).join(Product).order_by(Product.name).all()
    total_products = len(stock_items)
    low_stock_count = sum(1 for s in stock_items if s.is_low_stock)
    total_stock_value = sum(s.stock_value for s in stock_items)

    # Get users assigned to this location
    assigned_users = User.query.filter_by(location_id=id, is_active=True).all()

    return render_template('locations/view.html',
                           location=location,
                           stock_items=stock_items,
                           total_products=total_products,
                           low_stock_count=low_stock_count,
                           total_stock_value=total_stock_value,
                           assigned_users=assigned_users)


@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.LOCATION_EDIT)
def edit(id):
    """Edit location details"""
    location = Location.query.get_or_404(id)

    if request.method == 'POST':
        try:
            # Get form data
            location.name = request.form.get('name', '').strip()
            location.address = request.form.get('address', '').strip()
            location.city = request.form.get('city', '').strip()
            location.phone = request.form.get('phone', '').strip()
            location.email = request.form.get('email', '').strip()

            parent_warehouse_id = request.form.get('parent_warehouse_id')
            location.parent_warehouse_id = int(parent_warehouse_id) if parent_warehouse_id else None

            manager_id = request.form.get('manager_id')
            location.manager_id = int(manager_id) if manager_id else None

            if location.is_kiosk:
                location.can_sell = request.form.get('can_sell') == 'on'

            db.session.commit()
            flash('Location updated successfully.', 'success')
            return redirect(url_for('locations.view', id=id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating location: {str(e)}', 'danger')

    warehouses = Location.query.filter_by(location_type='warehouse', is_active=True).filter(Location.id != id).all()
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()

    return render_template('locations/edit.html',
                           location=location,
                           warehouses=warehouses,
                           users=users)


@bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@permission_required(Permissions.LOCATION_DELETE)
def delete(id):
    """Deactivate a location (soft delete)"""
    location = Location.query.get_or_404(id)

    try:
        # Check if location has active users
        active_users = User.query.filter_by(location_id=id, is_active=True).count()
        if active_users > 0:
            flash(f'Cannot delete location with {active_users} active users. Reassign them first.', 'danger')
            return redirect(url_for('locations.view', id=id))

        # Check if it's a warehouse with child kiosks
        if location.is_warehouse:
            child_kiosks = Location.query.filter_by(parent_warehouse_id=id, is_active=True).count()
            if child_kiosks > 0:
                flash(f'Cannot delete warehouse with {child_kiosks} active kiosks.', 'danger')
                return redirect(url_for('locations.view', id=id))

        # Soft delete
        location.is_active = False
        db.session.commit()

        flash(f'Location "{location.name}" has been deactivated.', 'success')
        return redirect(url_for('locations.index'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting location: {str(e)}', 'danger')
        return redirect(url_for('locations.view', id=id))


@bp.route('/<int:id>/stock')
@login_required
@permission_required(Permissions.INVENTORY_VIEW)
def stock(id):
    """View stock at a location"""
    location = Location.query.get_or_404(id)

    # Check access
    if not current_user.is_global_admin and not current_user.has_permission(Permissions.LOCATION_VIEW_ALL):
        if not can_access_location(id):
            flash('You do not have permission to view this location.', 'danger')
            return redirect(url_for('locations.index'))

    # Get stock items with product details
    stock_items = db.session.query(LocationStock, Product).join(
        Product, LocationStock.product_id == Product.id
    ).filter(
        LocationStock.location_id == id
    ).order_by(Product.name).all()

    return render_template('locations/stock.html',
                           location=location,
                           stock_items=stock_items)


@bp.route('/<int:id>/stock/adjust', methods=['POST'])
@login_required
@permission_required(Permissions.INVENTORY_ADJUST)
def adjust_stock(id):
    """Adjust stock at a location"""
    location = Location.query.get_or_404(id)

    # Check access
    if not current_user.is_global_admin:
        if not can_access_location(id):
            return jsonify({'error': 'Access denied'}), 403

    try:
        data = request.get_json()
        product_id = data.get('product_id')
        adjustment = int(data.get('adjustment', 0))
        reason = data.get('reason', 'Manual adjustment')

        if not product_id or adjustment == 0:
            return jsonify({'error': 'Invalid adjustment data'}), 400

        # Get or create stock record
        stock = LocationStock.query.filter_by(
            location_id=id,
            product_id=product_id
        ).first()

        if not stock:
            product = Product.query.get(product_id)
            if not product:
                return jsonify({'error': 'Product not found'}), 404

            stock = LocationStock(
                location_id=id,
                product_id=product_id,
                quantity=0,
                reorder_level=product.reorder_level
            )
            db.session.add(stock)

        # Apply adjustment
        old_quantity = stock.quantity
        stock.quantity += adjustment
        if stock.quantity < 0:
            stock.quantity = 0
        stock.last_movement_at = datetime.utcnow()

        # Create stock movement record
        from app.models import StockMovement
        movement = StockMovement(
            product_id=product_id,
            user_id=current_user.id,
            movement_type='adjustment',
            quantity=adjustment,
            reference=f'ADJ-{location.code}',
            notes=reason,
            location_id=id
        )
        db.session.add(movement)
        db.session.commit()

        return jsonify({
            'success': True,
            'old_quantity': old_quantity,
            'new_quantity': stock.quantity,
            'adjustment': adjustment
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/list')
@login_required
def api_list():
    """API endpoint to get locations list"""
    if current_user.is_global_admin or current_user.has_permission(Permissions.LOCATION_VIEW_ALL):
        locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    else:
        locations = current_user.get_accessible_locations()

    return jsonify({
        'locations': [{
            'id': loc.id,
            'code': loc.code,
            'name': loc.name,
            'type': loc.location_type,
            'city': loc.city,
            'can_sell': loc.can_sell
        } for loc in locations]
    })


@bp.route('/api/warehouses')
@login_required
def api_warehouses():
    """API endpoint to get warehouses list"""
    warehouses = Location.query.filter_by(
        location_type='warehouse',
        is_active=True
    ).order_by(Location.name).all()

    return jsonify({
        'warehouses': [{
            'id': wh.id,
            'code': wh.code,
            'name': wh.name,
            'city': wh.city
        } for wh in warehouses]
    })


@bp.route('/api/kiosks')
@login_required
def api_kiosks():
    """API endpoint to get kiosks list"""
    warehouse_id = request.args.get('warehouse_id', type=int)

    query = Location.query.filter_by(location_type='kiosk', is_active=True)
    if warehouse_id:
        query = query.filter_by(parent_warehouse_id=warehouse_id)

    kiosks = query.order_by(Location.name).all()

    return jsonify({
        'kiosks': [{
            'id': k.id,
            'code': k.code,
            'name': k.name,
            'city': k.city,
            'warehouse_id': k.parent_warehouse_id
        } for k in kiosks]
    })


@bp.route('/<int:id>/stock/search')
@login_required
def search_stock(id):
    """Search products and their stock at a location"""
    location = Location.query.get_or_404(id)
    query = request.args.get('q', '').strip()

    if len(query) < 2:
        return jsonify({'products': []})

    # Search products with stock at this location
    products = db.session.query(Product, LocationStock).outerjoin(
        LocationStock,
        db.and_(
            LocationStock.product_id == Product.id,
            LocationStock.location_id == id
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
        results.append({
            'id': product.id,
            'code': product.code,
            'name': product.name,
            'barcode': product.barcode,
            'quantity': stock.quantity if stock else 0,
            'available': stock.available_quantity if stock else 0,
            'reserved': stock.reserved_quantity if stock else 0,
            'is_low_stock': stock.is_low_stock if stock else True
        })

    return jsonify({'products': results})
