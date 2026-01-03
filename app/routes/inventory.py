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
import pandas as pd
from app.models import db, Product, Category, Supplier, StockMovement, SyncQueue
from app.utils.helpers import has_permission, allowed_file
from app.utils.permissions import permission_required, Permissions
import json

bp = Blueprint('inventory', __name__)


@bp.route('/')
@login_required
@permission_required(Permissions.INVENTORY_VIEW)
def index():
    """List all products"""
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config['ITEMS_PER_PAGE']

    # Filters
    category_id = request.args.get('category')
    supplier_id = request.args.get('supplier')
    search = request.args.get('search', '').strip()
    stock_status = request.args.get('stock_status')  # low, out, all

    query = Product.query

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
    if stock_status == 'low':
        query = query.filter(Product.quantity <= Product.reorder_level)
    elif stock_status == 'out':
        query = query.filter(Product.quantity == 0)

    products = query.order_by(Product.name).paginate(page=page, per_page=per_page, error_out=False)

    # Get categories and suppliers for filters
    categories = Category.query.all()
    suppliers = Supplier.query.filter_by(is_active=True).all()

    return render_template('inventory/index.html',
                         products=products,
                         categories=categories,
                         suppliers=suppliers)


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
                cost_price=Decimal(request.form.get('cost_price', 0)),
                selling_price=Decimal(request.form.get('selling_price', 0)),
                tax_rate=Decimal(request.form.get('tax_rate', 0)),
                quantity=int(request.form.get('quantity', 0)),
                reorder_level=int(request.form.get('reorder_level', 10)),
                reorder_quantity=int(request.form.get('reorder_quantity', 50)),
                batch_number=request.form.get('batch_number'),
                expiry_date=expiry_date,
                image_url=image_url
            )

            db.session.add(product)
            db.session.flush()

            # Create initial stock movement
            if product.quantity > 0:
                stock_movement = StockMovement(
                    product_id=product.id,
                    user_id=current_user.id,
                    movement_type='adjustment',
                    quantity=product.quantity,
                    reference='INITIAL_STOCK',
                    notes='Initial stock entry'
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
            flash(f'Product {product.name} added successfully', 'success')
            return redirect(url_for('inventory.index'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error adding product: {str(e)}', 'danger')

    categories = Category.query.all()
    suppliers = Supplier.query.filter_by(is_active=True).all()
    return render_template('inventory/add_product.html', categories=categories, suppliers=suppliers)


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

    if location:
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
            product.cost_price = Decimal(request.form.get('cost_price', 0))
            product.selling_price = Decimal(request.form.get('selling_price', 0))
            product.tax_rate = Decimal(request.form.get('tax_rate', 0))
            product.reorder_level = int(request.form.get('reorder_level', 10))
            product.reorder_quantity = int(request.form.get('reorder_quantity', 50))
            product.batch_number = request.form.get('batch_number')

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
        # Read CSV
        df = pd.read_csv(file)

        # Expected columns: code, barcode, name, brand, category, supplier, cost_price, selling_price, quantity
        imported = 0
        errors = []

        for index, row in df.iterrows():
            try:
                # Check if product already exists
                existing = Product.query.filter_by(code=row['code']).first()
                if existing:
                    errors.append(f"Row {index + 1}: Product code {row['code']} already exists")
                    continue

                product = Product(
                    code=row['code'],
                    barcode=row.get('barcode'),
                    name=row['name'],
                    brand=row.get('brand'),
                    cost_price=Decimal(str(row.get('cost_price', 0))),
                    selling_price=Decimal(str(row.get('selling_price', 0))),
                    quantity=int(row.get('quantity', 0))
                )

                db.session.add(product)
                imported += 1

            except Exception as e:
                errors.append(f"Row {index + 1}: {str(e)}")

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
    product = Product.query.get_or_404(product_id)
    movements = StockMovement.query.filter_by(product_id=product_id)\
        .order_by(StockMovement.timestamp.desc()).all()
    return render_template('inventory/stock_movements.html', product=product, movements=movements)


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
