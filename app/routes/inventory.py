"""
Inventory Management Routes
Handles product management, stock operations, and inventory tracking
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
from decimal import Decimal
import os
import csv
import io
from app.models import db, Product, Category, Supplier, StockMovement, SyncQueue, Location, LocationStock
from app.utils.helpers import has_permission, allowed_file
from app.utils.permissions import permission_required, Permissions
import json

bp = Blueprint('inventory', __name__)


@bp.route('/')
@login_required
@permission_required(Permissions.INVENTORY_VIEW)
def index():
    """List all products with location-specific stock"""
    from app.models import LocationStock
    from app.utils.location_context import get_current_location
    from sqlalchemy import and_

    page = request.args.get('page', 1, type=int)
    per_page = current_app.config['ITEMS_PER_PAGE']
    location = get_current_location()

    # Filters
    category_id = request.args.get('category')
    supplier_id = request.args.get('supplier')
    search = request.args.get('search', '').strip()
    stock_status = request.args.get('stock_status')  # low, out, all

    query = Product.query.filter(Product.is_active == True)

    if category_id:
        query = query.filter_by(category_id=category_id)
    if supplier_id:
        query = query.filter_by(supplier_id=supplier_id)
    if search:
        query = query.filter(
            db.or_(
                Product.code.ilike(f'%{search}%'),
                Product.name.ilike(f'%{search}%'),
                Product.brand.ilike(f'%{search}%')
            )
        )

    # For location-specific stock filtering, we need to join with LocationStock
    if location and stock_status:
        query = query.outerjoin(
            LocationStock,
            and_(LocationStock.product_id == Product.id, LocationStock.location_id == location.id)
        )
        if stock_status == 'low_stock':
            query = query.filter(
                db.or_(
                    LocationStock.quantity <= LocationStock.reorder_level,
                    LocationStock.quantity == None
                )
            )
        elif stock_status == 'out_of_stock':
            query = query.filter(
                db.or_(
                    LocationStock.quantity == 0,
                    LocationStock.quantity == None
                )
            )
        elif stock_status == 'in_stock':
            query = query.filter(LocationStock.quantity > LocationStock.reorder_level)

    products = query.order_by(Product.name).paginate(page=page, per_page=per_page, error_out=False)

    # Add location-specific stock data to each product
    if location:
        location_stocks = {ls.product_id: ls for ls in LocationStock.query.filter_by(location_id=location.id).all()}
        for product in products.items:
            ls = location_stocks.get(product.id)
            # Store location-specific values (use _loc_ prefix to avoid conflicts with model properties)
            product._loc_quantity = ls.quantity if ls else 0
            product._loc_reorder_level = ls.reorder_level if ls else product.reorder_level
            product._loc_is_low_stock = product._loc_quantity <= product._loc_reorder_level
    else:
        # Global admin - calculate total stock across all locations
        # Get total stock per product from LocationStock
        from sqlalchemy import func
        total_stocks = db.session.query(
            LocationStock.product_id,
            func.sum(LocationStock.quantity).label('total_qty')
        ).group_by(LocationStock.product_id).all()
        total_stock_map = {ts.product_id: int(ts.total_qty or 0) for ts in total_stocks}

        for product in products.items:
            allocated_qty = total_stock_map.get(product.id, 0)
            unallocated_qty = max(0, product.quantity - allocated_qty)

            # Total = allocated (in locations) + unallocated (not yet assigned)
            product._loc_quantity = allocated_qty + unallocated_qty
            product._loc_allocated = allocated_qty  # Stock in locations
            product._loc_unallocated = unallocated_qty  # Stock not yet assigned to locations
            product._loc_reorder_level = product.reorder_level
            product._loc_is_low_stock = product._loc_quantity <= product._loc_reorder_level

    # Get categories and suppliers for filters
    categories = Category.query.all()
    suppliers = Supplier.query.filter_by(is_active=True).all()

    # Get all locations for global admin
    locations = []
    if current_user.is_global_admin:
        locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    return render_template('inventory/index.html',
                         products=products,
                         categories=categories,
                         suppliers=suppliers,
                         location=location,
                         locations=locations)


@bp.route('/allocate-stock', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.INVENTORY_ADJUST)
def allocate_stock():
    """Allocate existing product stock to locations (Global Admin only)"""
    if not current_user.is_global_admin:
        flash('Only global admins can allocate stock to locations', 'danger')
        return redirect(url_for('inventory.index'))

    # Check if specific product is requested
    selected_product_id = request.args.get('product_id', type=int)
    selected_product = None

    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    # Get products with unallocated stock (product.quantity > 0 but no LocationStock entries)
    products_with_stock = Product.query.filter(
        Product.quantity > 0,
        Product.is_active == True
    ).all()

    unallocated_products = []
    for product in products_with_stock:
        # Check if total LocationStock quantity matches product.quantity
        total_allocated = db.session.query(
            db.func.coalesce(db.func.sum(LocationStock.quantity), 0)
        ).filter(LocationStock.product_id == product.id).scalar()

        unallocated_qty = product.quantity - int(total_allocated or 0)
        if unallocated_qty > 0:
            product_data = {
                'product': product,
                'total_stock': product.quantity,
                'allocated': int(total_allocated or 0),
                'unallocated': unallocated_qty
            }
            unallocated_products.append(product_data)

            # If this is the selected product, save it
            if selected_product_id and product.id == selected_product_id:
                selected_product = product_data

    if request.method == 'POST':
        try:
            product_id = request.form.get('product_id', type=int)
            location_id = request.form.get('location_id', type=int)
            quantity = request.form.get('quantity', type=int)

            if not all([product_id, location_id, quantity]):
                flash('Please fill all fields', 'danger')
                return redirect(url_for('inventory.allocate_stock'))

            product = Product.query.get_or_404(product_id)
            location = Location.query.get_or_404(location_id)

            # Check if quantity is valid
            total_allocated = db.session.query(
                db.func.coalesce(db.func.sum(LocationStock.quantity), 0)
            ).filter(LocationStock.product_id == product_id).scalar()
            unallocated = product.quantity - int(total_allocated or 0)

            if quantity > unallocated:
                flash(f'Cannot allocate {quantity} units. Only {unallocated} unallocated.', 'danger')
                return redirect(url_for('inventory.allocate_stock'))

            # Check if LocationStock exists for this product+location
            location_stock = LocationStock.query.filter_by(
                product_id=product_id,
                location_id=location_id
            ).first()

            if location_stock:
                location_stock.quantity += quantity
                location_stock.last_movement_at = datetime.utcnow()
            else:
                location_stock = LocationStock(
                    product_id=product_id,
                    location_id=location_id,
                    quantity=quantity,
                    reorder_level=product.reorder_level,
                    last_movement_at=datetime.utcnow()
                )
                db.session.add(location_stock)

            # Create stock movement record
            stock_movement = StockMovement(
                product_id=product_id,
                user_id=current_user.id,
                movement_type='allocation',
                quantity=quantity,
                reference='STOCK_ALLOCATION',
                notes=f'Stock allocated to {location.name}',
                location_id=location_id
            )
            db.session.add(stock_movement)

            db.session.commit()
            flash(f'Successfully allocated {quantity} units of {product.name} to {location.name}', 'success')

            # Redirect back to product page if came from there
            if selected_product_id:
                return redirect(url_for('inventory.view_product', product_id=product_id))
            return redirect(url_for('inventory.allocate_stock'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error allocating stock: {str(e)}', 'danger')

    return render_template('inventory/allocate_stock.html',
                           locations=locations,
                           unallocated_products=unallocated_products,
                           selected_product=selected_product)


@bp.route('/add', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.INVENTORY_CREATE)
def add_product():
    """Add new product"""
    if request.method == 'POST':
        try:
            # Handle file upload
            image_url = None
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    image_url = f'/static/uploads/{filename}'

            # Parse expiry date if provided
            expiry_date = None
            expiry_date_str = request.form.get('expiry_date')
            if expiry_date_str:
                try:
                    expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass

            # Cost breakdown fields
            base_cost = Decimal(request.form.get('base_cost', 0) or 0)
            packaging_cost = Decimal(request.form.get('packaging_cost', 0) or 0)
            delivery_cost = Decimal(request.form.get('delivery_cost', 0) or 0)
            bottle_cost = Decimal(request.form.get('bottle_cost', 0) or 0)
            kiosk_cost = Decimal(request.form.get('kiosk_cost', 0) or 0)

            # Calculate landed cost (or use manually entered cost_price for backward compatibility)
            cost_price_input = request.form.get('cost_price', 0) or 0
            if base_cost > 0:
                # If cost breakdown is provided, calculate landed cost
                landed_cost = base_cost + packaging_cost + delivery_cost + bottle_cost + kiosk_cost
            else:
                # Fallback: use manual cost_price input
                landed_cost = Decimal(cost_price_input)
                base_cost = landed_cost  # Set base_cost = cost_price for backward compatibility

            product = Product(
                code=request.form.get('code'),
                barcode=request.form.get('barcode'),
                name=request.form.get('name'),
                brand=request.form.get('brand'),
                category_id=request.form.get('category_id') or None,
                supplier_id=request.form.get('supplier_id') or None,
                description=request.form.get('description'),
                size=request.form.get('size'),
                unit=request.form.get('unit', 'piece'),
                base_cost=base_cost,
                packaging_cost=packaging_cost,
                delivery_cost=delivery_cost,
                bottle_cost=bottle_cost,
                kiosk_cost=kiosk_cost,
                cost_price=landed_cost,
                selling_price=Decimal(request.form.get('selling_price', 0)),
                tax_rate=Decimal(request.form.get('tax_rate', 0)),
                quantity=int(request.form.get('quantity', 0)),
                reorder_level=int(request.form.get('reorder_level', 10)),
                reorder_quantity=int(request.form.get('reorder_quantity', 50)),
                batch_number=request.form.get('batch_number'),
                expiry_date=expiry_date,
                image_url=image_url,
                is_made_to_order='is_made_to_order' in request.form,
                is_manufactured='is_manufactured' in request.form
            )

            db.session.add(product)
            db.session.flush()

            # Get location_id if provided (for global admin)
            location_id = request.form.get('location_id', type=int)

            # If location specified, create LocationStock entry
            if location_id and product.quantity > 0:
                location_stock = LocationStock(
                    location_id=location_id,
                    product_id=product.id,
                    quantity=product.quantity,
                    reorder_level=product.reorder_level,
                    last_movement_at=datetime.utcnow()
                )
                db.session.add(location_stock)

                # Create stock movement with location
                stock_movement = StockMovement(
                    product_id=product.id,
                    user_id=current_user.id,
                    movement_type='adjustment',
                    quantity=product.quantity,
                    reference='INITIAL_STOCK',
                    notes='Initial stock entry',
                    location_id=location_id
                )
                db.session.add(stock_movement)
            elif product.quantity > 0:
                # No location specified - create movement without location
                # For non-global admins, use their assigned location
                user_location_id = current_user.location_id if current_user.location_id else None

                if user_location_id:
                    location_stock = LocationStock(
                        location_id=user_location_id,
                        product_id=product.id,
                        quantity=product.quantity,
                        reorder_level=product.reorder_level,
                        last_movement_at=datetime.utcnow()
                    )
                    db.session.add(location_stock)

                stock_movement = StockMovement(
                    product_id=product.id,
                    user_id=current_user.id,
                    movement_type='adjustment',
                    quantity=product.quantity,
                    reference='INITIAL_STOCK',
                    notes='Initial stock entry',
                    location_id=user_location_id
                )
                db.session.add(stock_movement)

            # Queue for sync
            sync_item = SyncQueue(
                table_name='products',
                operation='insert',
                record_id=product.id,
                data_json=json.dumps({'product_id': product.id})
            )
            db.session.add(sync_item)

            db.session.commit()
            location_name = Location.query.get(location_id).name if location_id else 'default'
            flash(f'Product {product.name} added successfully at {location_name}', 'success')
            return redirect(url_for('inventory.index'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error adding product: {str(e)}', 'danger')

    categories = Category.query.all()
    suppliers = Supplier.query.filter_by(is_active=True).all()
    locations = Location.query.filter_by(is_active=True).all() if current_user.is_global_admin else []
    return render_template('inventory/add_product.html',
                           categories=categories,
                           suppliers=suppliers,
                           locations=locations)


@bp.route('/product/<int:product_id>')
@login_required
@permission_required(Permissions.INVENTORY_VIEW)
def view_product(product_id):
    """View product details"""
    from datetime import datetime
    from app.models import SaleItem, LocationStock, Location
    from app.utils.location_context import get_current_location

    product = Product.query.get_or_404(product_id)
    location = get_current_location()

    # Get location-specific stock
    location_stock = None
    store_quantity = product.quantity  # Fallback to global quantity
    location_stocks = []  # For global admin: stock per location
    total_allocated = 0

    if current_user.is_global_admin:
        # Get only store/kiosk locations (exclude warehouses) with their stock for this product
        locations = Location.query.filter(
            Location.is_active == True,
            Location.location_type != 'warehouse'
        ).order_by(Location.name).all()
        all_location_stocks = {ls.location_id: ls for ls in LocationStock.query.filter_by(product_id=product_id).all()}

        for loc in locations:
            ls = all_location_stocks.get(loc.id)
            qty = ls.quantity if ls else 0
            total_allocated += qty
            location_stocks.append({
                'location': loc,
                'location_stock': ls,
                'quantity': qty,
                'reorder_level': ls.reorder_level if ls else product.reorder_level
            })

        # Total stock for global admin
        store_quantity = total_allocated if total_allocated > 0 else product.quantity
    elif location:
        location_stock = LocationStock.query.filter_by(
            location_id=location.id,
            product_id=product_id
        ).first()
        if location_stock:
            store_quantity = location_stock.quantity

    # Get recent stock movements (filtered by location for non-admins)
    movements_query = StockMovement.query.filter_by(product_id=product_id)
    if location and not current_user.is_global_admin:
        movements_query = movements_query.filter_by(location_id=location.id)
    stock_movements = movements_query.order_by(StockMovement.timestamp.desc()).limit(10).all()

    # Get recent sales for this product (filtered by location for non-admins)
    sales_query = db.session.query(SaleItem).filter_by(product_id=product_id)
    recent_sales = sales_query.order_by(SaleItem.id.desc()).limit(10).all()

    return render_template('inventory/view_product.html',
                          product=product,
                          location=location,
                          location_stock=location_stock,
                          location_stocks=location_stocks,
                          store_quantity=store_quantity,
                          stock_movements=stock_movements,
                          recent_sales=recent_sales,
                          now=datetime.now().date())


@bp.route('/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.INVENTORY_EDIT)
def edit_product(product_id):
    """Edit existing product"""
    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':
        try:
            # Handle file upload
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    product.image_url = f'/static/uploads/{filename}'

            # Parse expiry date if provided
            expiry_date_str = request.form.get('expiry_date')
            if expiry_date_str:
                try:
                    product.expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                except ValueError:
                    product.expiry_date = None
            else:
                product.expiry_date = None

            product.code = request.form.get('code')
            product.barcode = request.form.get('barcode')
            product.name = request.form.get('name')
            product.brand = request.form.get('brand')
            product.category_id = request.form.get('category_id') or None
            product.supplier_id = request.form.get('supplier_id') or None
            product.description = request.form.get('description')
            product.size = request.form.get('size')
            product.unit = request.form.get('unit', 'piece')

            # Cost breakdown fields
            base_cost = Decimal(request.form.get('base_cost', 0) or 0)
            packaging_cost = Decimal(request.form.get('packaging_cost', 0) or 0)
            delivery_cost = Decimal(request.form.get('delivery_cost', 0) or 0)
            bottle_cost = Decimal(request.form.get('bottle_cost', 0) or 0)
            kiosk_cost = Decimal(request.form.get('kiosk_cost', 0) or 0)

            # Calculate landed cost (or use manually entered cost_price for backward compatibility)
            cost_price_input = request.form.get('cost_price', 0) or 0
            if base_cost > 0:
                landed_cost = base_cost + packaging_cost + delivery_cost + bottle_cost + kiosk_cost
            else:
                landed_cost = Decimal(cost_price_input)
                base_cost = landed_cost

            product.base_cost = base_cost
            product.packaging_cost = packaging_cost
            product.delivery_cost = delivery_cost
            product.bottle_cost = bottle_cost
            product.kiosk_cost = kiosk_cost
            product.cost_price = landed_cost
            product.selling_price = Decimal(request.form.get('selling_price', 0))
            product.tax_rate = Decimal(request.form.get('tax_rate', 0))
            product.reorder_level = int(request.form.get('reorder_level', 10))
            product.reorder_quantity = int(request.form.get('reorder_quantity', 50))
            product.batch_number = request.form.get('batch_number')
            product.is_made_to_order = 'is_made_to_order' in request.form
            product.is_manufactured = 'is_manufactured' in request.form

            # Queue for sync
            sync_item = SyncQueue(
                table_name='products',
                operation='update',
                record_id=product.id,
                data_json=json.dumps({'product_id': product.id})
            )
            db.session.add(sync_item)

            db.session.commit()
            flash(f'Product {product.name} updated successfully', 'success')
            return redirect(url_for('inventory.index'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating product: {str(e)}', 'danger')

    categories = Category.query.all()
    suppliers = Supplier.query.filter_by(is_active=True).all()
    return render_template('inventory/edit_product.html',
                         product=product,
                         categories=categories,
                         suppliers=suppliers)


@bp.route('/delete/<int:product_id>', methods=['POST'])
@login_required
@permission_required(Permissions.INVENTORY_DELETE)
def delete_product(product_id):
    """Delete product"""
    try:
        product = Product.query.get_or_404(product_id)

        # Soft delete - just mark as inactive
        product.is_active = False

        # Queue for sync
        sync_item = SyncQueue(
            table_name='products',
            operation='update',
            record_id=product.id,
            data_json=json.dumps({'is_active': False})
        )
        db.session.add(sync_item)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Product deleted successfully'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/adjust-stock/<int:product_id>', methods=['POST'])
@login_required
@permission_required(Permissions.INVENTORY_ADJUST)
def adjust_stock(product_id):
    """Adjust product stock for current location"""
    from app.models import LocationStock
    from app.utils.location_context import get_current_location

    try:
        data = request.get_json()
        product = Product.query.get_or_404(product_id)
        location = get_current_location()

        # Get adjustment parameters from frontend
        adjustment_type = data.get('adjustment_type', 'add')
        quantity = int(data.get('quantity', 0))
        reason = data.get('reason', 'Manual adjustment')

        # Also support legacy 'adjustment' parameter
        if 'adjustment' in data:
            adjustment = int(data.get('adjustment', 0))
        else:
            # Calculate adjustment based on type
            if adjustment_type == 'add':
                adjustment = quantity
            elif adjustment_type == 'remove':
                adjustment = -quantity
            elif adjustment_type == 'set':
                # For 'set', we need to calculate the difference
                if location:
                    location_stock = LocationStock.query.filter_by(
                        location_id=location.id, product_id=product_id
                    ).first()
                    current_qty = location_stock.quantity if location_stock else 0
                else:
                    current_qty = product.quantity
                adjustment = quantity - current_qty
            else:
                adjustment = quantity

        # Update location-specific stock if user has a location
        if location:
            location_stock = LocationStock.query.filter_by(
                location_id=location.id, product_id=product_id
            ).first()

            if not location_stock:
                location_stock = LocationStock(
                    location_id=location.id,
                    product_id=product_id,
                    quantity=0,
                    reorder_level=product.reorder_level
                )
                db.session.add(location_stock)

            old_quantity = location_stock.quantity
            location_stock.quantity += adjustment

            if location_stock.quantity < 0:
                return jsonify({'success': False, 'error': 'Stock cannot be negative'}), 400

            new_quantity = location_stock.quantity
        else:
            # Fallback to global product quantity
            old_quantity = product.quantity
            product.quantity += adjustment

            if product.quantity < 0:
                return jsonify({'success': False, 'error': 'Stock cannot be negative'}), 400

            new_quantity = product.quantity

        # Create stock movement
        stock_movement = StockMovement(
            product_id=product.id,
            user_id=current_user.id,
            location_id=location.id if location else None,
            movement_type='adjustment',
            quantity=adjustment,
            reference='STOCK_ADJUSTMENT',
            notes=f'{reason} (Old: {old_quantity}, New: {new_quantity})'
        )
        db.session.add(stock_movement)

        db.session.commit()

        return jsonify({
            'success': True,
            'new_quantity': new_quantity,
            'message': 'Stock adjusted successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/adjust-stock-location/<int:product_id>', methods=['POST'])
@login_required
@permission_required(Permissions.INVENTORY_ADJUST)
def adjust_stock_location(product_id):
    """Adjust product stock for a specific location (Global Admin only)"""
    if not current_user.is_global_admin:
        flash('Only global admins can adjust stock by location', 'danger')
        return redirect(url_for('inventory.view_product', product_id=product_id))

    try:
        product = Product.query.get_or_404(product_id)

        # Accept both form data and JSON
        if request.is_json:
            data = request.get_json()
            location_id = data.get('location_id')
            adjustment_type = data.get('adjustment_type', 'add')
            quantity = int(data.get('quantity', 0))
            reason = data.get('reason', 'Manual adjustment')
            is_ajax = True
        else:
            location_id = request.form.get('location_id')
            adjustment_type = request.form.get('adjustment_type', 'add')
            quantity = int(request.form.get('quantity', 0))
            reason = request.form.get('reason', 'Manual adjustment')
            is_ajax = False

        if not location_id:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Location ID required'}), 400
            flash('Location ID required', 'danger')
            return redirect(url_for('inventory.view_product', product_id=product_id))

        location = Location.query.get_or_404(location_id)

        # Get or create LocationStock
        location_stock = LocationStock.query.filter_by(
            location_id=location_id, product_id=product_id
        ).first()

        if not location_stock:
            location_stock = LocationStock(
                location_id=location_id,
                product_id=product_id,
                quantity=0,
                reorder_level=product.reorder_level
            )
            db.session.add(location_stock)

        old_quantity = location_stock.quantity

        # Calculate adjustment based on type
        if adjustment_type == 'add':
            adjustment = quantity
        elif adjustment_type == 'remove':
            adjustment = -quantity
        elif adjustment_type == 'set':
            adjustment = quantity - old_quantity
        else:
            adjustment = quantity

        location_stock.quantity += adjustment
        location_stock.last_movement_at = datetime.utcnow()

        if location_stock.quantity < 0:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Stock cannot be negative'}), 400
            flash('Stock cannot be negative', 'danger')
            return redirect(url_for('inventory.view_product', product_id=product_id))

        new_quantity = location_stock.quantity

        # Create stock movement
        stock_movement = StockMovement(
            product_id=product_id,
            user_id=current_user.id,
            location_id=location_id,
            movement_type='adjustment',
            quantity=adjustment,
            reference='ADMIN_ADJUSTMENT',
            notes=f'{reason} at {location.name} (Old: {old_quantity}, New: {new_quantity})'
        )
        db.session.add(stock_movement)

        db.session.commit()

        if is_ajax:
            return jsonify({
                'success': True,
                'new_quantity': new_quantity,
                'message': f'Stock adjusted successfully at {location.name}'
            })

        flash(f'Stock adjusted successfully at {location.name}', 'success')
        return redirect(url_for('inventory.view_product', product_id=product_id))

    except Exception as e:
        db.session.rollback()
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Error adjusting stock: {str(e)}', 'danger')
        return redirect(url_for('inventory.view_product', product_id=product_id))


@bp.route('/adjust-stock-page/<int:product_id>', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.INVENTORY_ADJUST)
def adjust_stock_page(product_id):
    """Dedicated page for adjusting product stock"""
    from app.models import LocationStock
    from app.utils.location_context import get_current_location

    product = Product.query.get_or_404(product_id)
    location = get_current_location()

    # Get current stock for this location
    if location:
        location_stock = LocationStock.query.filter_by(
            location_id=location.id, product_id=product_id
        ).first()
        current_stock = location_stock.quantity if location_stock else 0
    else:
        current_stock = product.quantity

    if request.method == 'POST':
        try:
            adjustment_type = request.form.get('adjustment_type', 'add')
            quantity = int(request.form.get('quantity', 0))
            reason = request.form.get('reason', 'Manual adjustment')

            # Calculate adjustment based on type
            if adjustment_type == 'add':
                adjustment = quantity
            elif adjustment_type == 'remove':
                adjustment = -quantity
            elif adjustment_type == 'set':
                adjustment = quantity - current_stock
            else:
                adjustment = quantity

            # Update location-specific stock if user has a location
            if location:
                location_stock = LocationStock.query.filter_by(
                    location_id=location.id, product_id=product_id
                ).first()

                if not location_stock:
                    location_stock = LocationStock(
                        location_id=location.id,
                        product_id=product_id,
                        quantity=0,
                        reorder_level=product.reorder_level
                    )
                    db.session.add(location_stock)

                old_quantity = location_stock.quantity
                location_stock.quantity += adjustment

                if location_stock.quantity < 0:
                    flash('Stock cannot be negative', 'danger')
                    return redirect(url_for('inventory.adjust_stock_page', product_id=product_id))

                new_quantity = location_stock.quantity
            else:
                old_quantity = product.quantity
                product.quantity += adjustment

                if product.quantity < 0:
                    flash('Stock cannot be negative', 'danger')
                    return redirect(url_for('inventory.adjust_stock_page', product_id=product_id))

                new_quantity = product.quantity

            # Create stock movement
            stock_movement = StockMovement(
                product_id=product_id,
                location_id=location.id if location else None,
                quantity=adjustment,
                movement_type='adjustment',
                notes=reason,
                reference=f"ADJ-{product_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                user_id=current_user.id
            )
            db.session.add(stock_movement)
            db.session.commit()

            flash(f'Stock adjusted successfully. New quantity: {new_quantity}', 'success')
            return redirect(url_for('inventory.index'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error adjusting stock: {str(e)}', 'danger')
            return redirect(url_for('inventory.adjust_stock_page', product_id=product_id))

    return render_template('inventory/adjust_stock.html',
                         product=product,
                         current_stock=current_stock,
                         location=location)


@bp.route('/import-csv', methods=['POST'])
@login_required
@permission_required(Permissions.INVENTORY_CREATE)
def import_csv():
    """Bulk import products from CSV"""
    if 'file' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('inventory.index'))

    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('inventory.index'))

    try:
        # Read CSV using built-in csv module
        stream = io.StringIO(file.stream.read().decode('utf-8'))
        reader = csv.DictReader(stream)

        # Expected columns: code, barcode, name, brand, category, supplier, cost_price, selling_price, quantity
        imported = 0
        errors = []

        for index, row in enumerate(reader):
            try:
                # Check if product already exists
                existing = Product.query.filter_by(code=row['code']).first()
                if existing:
                    errors.append(f"Row {index + 2}: Product code {row['code']} already exists")
                    continue

                product = Product(
                    code=row['code'],
                    barcode=row.get('barcode') or None,
                    name=row['name'],
                    brand=row.get('brand') or None,
                    cost_price=Decimal(str(row.get('cost_price') or 0)),
                    selling_price=Decimal(str(row.get('selling_price') or 0)),
                    quantity=int(row.get('quantity') or 0)
                )

                db.session.add(product)
                imported += 1

            except Exception as e:
                errors.append(f"Row {index + 2}: {str(e)}")

        db.session.commit()

        message = f'Successfully imported {imported} products'
        if errors:
            message += f'. {len(errors)} errors occurred.'

        flash(message, 'success' if imported > 0 else 'warning')

    except Exception as e:
        db.session.rollback()
        flash(f'Error importing CSV: {str(e)}', 'danger')

    return redirect(url_for('inventory.index'))


@bp.route('/categories')
@login_required
@permission_required(Permissions.INVENTORY_VIEW)
def categories():
    """Manage categories"""
    categories = Category.query.all()
    return render_template('inventory/categories.html', categories=categories)


@bp.route('/low-stock-alert')
@login_required
@permission_required(Permissions.INVENTORY_VIEW)
def low_stock_alert():
    """View low stock items"""
    low_stock_threshold = current_app.config.get('LOW_STOCK_THRESHOLD', 10)
    products = Product.query.filter(Product.quantity <= Product.reorder_level).all()
    return render_template('inventory/low_stock.html', products=products)


@bp.route('/stock-movements/<int:product_id>')
@login_required
@permission_required(Permissions.INVENTORY_VIEW)
def stock_movements(product_id):
    """View stock movement history for a product"""
    from app.models import LocationStock
    from app.utils.location_context import get_current_location

    product = Product.query.get_or_404(product_id)
    location = get_current_location()

    # Get location-specific stock
    if location:
        location_stock = LocationStock.query.filter_by(
            location_id=location.id, product_id=product_id
        ).first()
        current_stock = location_stock.quantity if location_stock else 0
        reorder_level = location_stock.reorder_level if location_stock else product.reorder_level

        # Filter movements by location
        movements = StockMovement.query.filter_by(
            product_id=product_id, location_id=location.id
        ).order_by(StockMovement.timestamp.desc()).all()
    else:
        current_stock = product.quantity
        reorder_level = product.reorder_level
        movements = StockMovement.query.filter_by(product_id=product_id)\
            .order_by(StockMovement.timestamp.desc()).all()

    return render_template('inventory/stock_movements.html',
                         product=product,
                         movements=movements,
                         current_stock=current_stock,
                         reorder_level=reorder_level,
                         location=location)


@bp.route('/print-stock-report')
@login_required
@permission_required(Permissions.INVENTORY_VIEW)
def print_stock_report():
    """Print stock report for current location"""
    from app.models import Location, LocationStock
    from app.utils.location_context import get_current_location

    location = get_current_location()
    report_type = request.args.get('type', 'all')  # 'all' or 'low'

    stock_items = []
    total_items = 0
    total_quantity = 0
    total_value = 0
    low_stock_count = 0

    if location:
        # Get ALL active products with LEFT JOIN to LocationStock
        # This includes products that don't have a LocationStock entry (0 stock)
        from sqlalchemy import outerjoin, and_

        query = db.session.query(Product, LocationStock).outerjoin(
            LocationStock, and_(
                LocationStock.product_id == Product.id,
                LocationStock.location_id == location.id
            )
        ).filter(
            Product.is_active == True
        )

        results = query.order_by(Product.name).all()

        for product, stock in results:
            # If no LocationStock entry, quantity is 0
            qty = stock.quantity if stock else 0
            reorder = stock.reorder_level if stock else product.reorder_level
            is_low = qty <= reorder

            # For low stock report, only include items at or below reorder level
            if report_type == 'low' and not is_low:
                continue

            stock_items.append({
                'stock': stock,
                'product': product,
                'quantity': qty,
                'reorder_level': reorder,
                'is_low': is_low,
                'value': qty * float(product.cost_price)
            })
            total_quantity += qty
            total_value += qty * float(product.cost_price)
            if is_low:
                low_stock_count += 1

        total_items = len(stock_items)
    else:
        # Fallback: global stock from Product table
        query = Product.query.filter_by(is_active=True)

        if report_type == 'low':
            query = query.filter(Product.quantity <= Product.reorder_level)

        products = query.order_by(Product.name).all()

        for product in products:
            is_low = product.quantity <= product.reorder_level
            stock_items.append({
                'stock': None,
                'product': product,
                'quantity': product.quantity,
                'reorder_level': product.reorder_level,
                'is_low': is_low,
                'value': product.quantity * float(product.cost_price)
            })
            total_quantity += product.quantity
            total_value += product.quantity * float(product.cost_price)
            if is_low:
                low_stock_count += 1

        total_items = len(stock_items)

    # Only admin, warehouse_manager, accountant, inventory_manager can see cost prices
    can_see_cost = current_user.role in ['admin', 'warehouse_manager', 'accountant', 'inventory_manager'] or current_user.is_global_admin

    return render_template('inventory/print_stock_report.html',
                           location=location,
                           stock_items=stock_items,
                           report_type=report_type,
                           total_items=total_items,
                           total_quantity=total_quantity,
                           total_value=total_value,
                           low_stock_count=low_stock_count,
                           can_see_cost=can_see_cost,
                           print_date=datetime.now())
