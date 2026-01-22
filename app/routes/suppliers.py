"""
Supplier Management Routes
Handles supplier CRUD operations and purchase orders
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from decimal import Decimal
from app.models import db, Supplier, Product, PurchaseOrder, SyncQueue
from app.utils.helpers import has_permission
from app.utils.permissions import permission_required, Permissions
import json

bp = Blueprint('suppliers', __name__)


@bp.route('/')
@login_required
@permission_required(Permissions.SUPPLIER_VIEW)
def index():
    """List all suppliers"""
    if not has_permission('suppliers'):
        flash('You do not have permission to access suppliers', 'danger')
        return redirect(url_for('index'))

    page = request.args.get('page', 1, type=int)
    per_page = current_app.config['ITEMS_PER_PAGE']
    search = request.args.get('search', '').strip()

    query = Supplier.query.filter_by(is_active=True)

    if search:
        query = query.filter(
            db.or_(
                Supplier.name.ilike(f'%{search}%'),
                Supplier.contact_person.ilike(f'%{search}%')
            )
        )

    suppliers = query.order_by(Supplier.name).paginate(page=page, per_page=per_page, error_out=False)

    return render_template('suppliers/index.html', suppliers=suppliers)


@bp.route('/add', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.SUPPLIER_CREATE)
def add_supplier():
    """Add new supplier"""
    if not has_permission('suppliers'):
        flash('You do not have permission to add suppliers', 'danger')
        return redirect(url_for('suppliers.index'))

    if request.method == 'POST':
        try:
            supplier = Supplier(
                name=request.form.get('name'),
                contact_person=request.form.get('contact_person'),
                phone=request.form.get('phone'),
                email=request.form.get('email'),
                address=request.form.get('address'),
                payment_terms=request.form.get('payment_terms'),
                notes=request.form.get('notes')
            )

            db.session.add(supplier)
            db.session.flush()

            # Queue for sync
            sync_item = SyncQueue(
                table_name='suppliers',
                operation='insert',
                record_id=supplier.id,
                data_json=json.dumps({'supplier_id': supplier.id})
            )
            db.session.add(sync_item)

            db.session.commit()
            flash(f'Supplier {supplier.name} added successfully', 'success')
            return redirect(url_for('suppliers.index'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error adding supplier: {str(e)}', 'danger')

    return render_template('suppliers/add_supplier.html')


@bp.route('/edit/<int:supplier_id>', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.SUPPLIER_EDIT)
def edit_supplier(supplier_id):
    """Edit existing supplier"""
    if not has_permission('suppliers'):
        flash('You do not have permission to edit suppliers', 'danger')
        return redirect(url_for('suppliers.index'))

    supplier = Supplier.query.get_or_404(supplier_id)

    if request.method == 'POST':
        try:
            supplier.name = request.form.get('name')
            supplier.contact_person = request.form.get('contact_person')
            supplier.phone = request.form.get('phone')
            supplier.email = request.form.get('email')
            supplier.address = request.form.get('address')
            supplier.payment_terms = request.form.get('payment_terms')
            supplier.notes = request.form.get('notes')

            # Queue for sync
            sync_item = SyncQueue(
                table_name='suppliers',
                operation='update',
                record_id=supplier.id,
                data_json=json.dumps({'supplier_id': supplier.id})
            )
            db.session.add(sync_item)

            db.session.commit()
            flash(f'Supplier {supplier.name} updated successfully', 'success')
            return redirect(url_for('suppliers.index'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating supplier: {str(e)}', 'danger')

    return render_template('suppliers/edit_supplier.html', supplier=supplier)


@bp.route('/delete/<int:supplier_id>', methods=['POST'])
@login_required
@permission_required(Permissions.SUPPLIER_DELETE)
def delete_supplier(supplier_id):
    """Delete supplier (soft delete)"""
    if not has_permission('suppliers'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    try:
        supplier = Supplier.query.get_or_404(supplier_id)
        supplier.is_active = False

        # Queue for sync
        sync_item = SyncQueue(
            table_name='suppliers',
            operation='update',
            record_id=supplier.id,
            data_json=json.dumps({'is_active': False})
        )
        db.session.add(sync_item)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Supplier deleted successfully'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/view/<int:supplier_id>')
@login_required
def view_supplier(supplier_id):
    """View supplier details with dashboard tabs"""
    from app.models_extended import SupplierPayment, SupplierLedger
    from sqlalchemy import func

    supplier = Supplier.query.get_or_404(supplier_id)
    active_tab = request.args.get('tab', 'overview')

    # Pagination for products
    page = request.args.get('page', 1, type=int)
    per_page = 10

    products = Product.query.filter_by(supplier_id=supplier_id).order_by(
        Product.name
    ).paginate(page=page, per_page=per_page, error_out=False)

    # Calculate statistics for all products (not just current page)
    product_count = Product.query.filter_by(supplier_id=supplier_id).count()
    total_cost_value = db.session.query(db.func.sum(Product.cost_price)).filter(
        Product.supplier_id == supplier_id
    ).scalar() or 0

    # Low stock products from this supplier
    low_stock_products = Product.query.filter(
        Product.supplier_id == supplier_id,
        Product.is_active == True,
        Product.quantity <= Product.reorder_level
    ).all()

    # Purchase Orders history
    purchase_orders = PurchaseOrder.query.filter_by(
        supplier_id=supplier_id
    ).order_by(PurchaseOrder.created_at.desc()).limit(20).all()

    # PO statistics
    total_orders = PurchaseOrder.query.filter_by(supplier_id=supplier_id).count()
    pending_orders = PurchaseOrder.query.filter(
        PurchaseOrder.supplier_id == supplier_id,
        PurchaseOrder.status.in_(['draft', 'pending', 'ordered'])
    ).count()

    total_ordered_value = db.session.query(func.sum(PurchaseOrder.total)).filter(
        PurchaseOrder.supplier_id == supplier_id,
        PurchaseOrder.status == 'received'
    ).scalar() or 0

    # Payment history
    payments = SupplierPayment.query.filter_by(
        supplier_id=supplier_id
    ).order_by(SupplierPayment.payment_date.desc()).limit(20).all()

    total_paid = db.session.query(func.sum(SupplierPayment.amount)).filter(
        SupplierPayment.supplier_id == supplier_id,
        SupplierPayment.status == 'completed'
    ).scalar() or 0

    # Ledger entries (last 20)
    ledger_entries = SupplierLedger.query.filter_by(
        supplier_id=supplier_id
    ).order_by(SupplierLedger.transaction_date.desc()).limit(20).all()

    return render_template('suppliers/view_supplier.html',
                         supplier=supplier,
                         products=products,
                         product_count=product_count,
                         total_cost_value=total_cost_value,
                         low_stock_products=low_stock_products,
                         purchase_orders=purchase_orders,
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         total_ordered_value=total_ordered_value,
                         payments=payments,
                         total_paid=total_paid,
                         ledger_entries=ledger_entries,
                         active_tab=active_tab)
