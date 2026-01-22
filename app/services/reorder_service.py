"""
Reorder Service
Handles automatic detection of low stock and draft PO generation
"""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import and_
from app.models import db, Product, Supplier, PurchaseOrder, PurchaseOrderItem


def generate_po_number():
    """Generate unique PO number"""
    today = datetime.utcnow()
    prefix = f"PO-{today.strftime('%Y%m%d')}"

    last_po = PurchaseOrder.query.filter(
        PurchaseOrder.po_number.like(f'{prefix}%')
    ).order_by(PurchaseOrder.id.desc()).first()

    if last_po:
        try:
            last_num = int(last_po.po_number.split('-')[-1])
            new_num = last_num + 1
        except:
            new_num = 1
    else:
        new_num = 1

    return f"{prefix}-{new_num:04d}"


def detect_low_stock(include_zero_stock=True):
    """
    Find all products that are at or below their reorder level.

    Returns:
        List of Product objects with low stock, grouped by supplier_id
    """
    query = Product.query.filter(
        Product.is_active == True,
        Product.supplier_id.isnot(None),
        Product.can_be_reordered == True
    )

    if include_zero_stock:
        query = query.filter(Product.quantity <= Product.reorder_level)
    else:
        query = query.filter(
            Product.quantity <= Product.reorder_level,
            Product.quantity > 0
        )

    return query.order_by(Product.supplier_id, Product.name).all()


def get_low_stock_by_supplier():
    """
    Get low stock products grouped by supplier.

    Returns:
        Dictionary: {supplier_id: {'supplier': Supplier, 'products': [Product, ...]}}
    """
    low_stock_products = detect_low_stock()

    grouped = {}
    for product in low_stock_products:
        if product.supplier_id not in grouped:
            supplier = Supplier.query.get(product.supplier_id)
            grouped[product.supplier_id] = {
                'supplier': supplier,
                'products': []
            }
        grouped[product.supplier_id]['products'].append(product)

    return grouped


def get_or_create_draft_po(supplier_id, user_id=None):
    """
    Get existing draft PO for supplier or create new one.

    Args:
        supplier_id: ID of the supplier
        user_id: ID of the user creating the PO (optional)

    Returns:
        PurchaseOrder: Draft PO (existing or newly created)
    """
    # Look for existing draft PO for this supplier
    draft_po = PurchaseOrder.query.filter(
        PurchaseOrder.supplier_id == supplier_id,
        PurchaseOrder.status == 'draft',
        PurchaseOrder.is_auto_generated == True
    ).first()

    if draft_po:
        return draft_po

    # Create new draft PO
    draft_po = PurchaseOrder(
        po_number=generate_po_number(),
        supplier_id=supplier_id,
        user_id=user_id,
        status='draft',
        is_auto_generated=True,
        source_type='auto_reorder',
        order_date=datetime.utcnow(),
        notes='Auto-generated from low stock detection'
    )
    db.session.add(draft_po)
    db.session.flush()  # Get the ID without committing

    return draft_po


def add_to_draft_po(draft_po, product, quantity=None):
    """
    Add or update a product in a draft PO.

    Args:
        draft_po: PurchaseOrder object (draft status)
        product: Product object to add
        quantity: Quantity to order (defaults to product.reorder_quantity)

    Returns:
        PurchaseOrderItem: The created or updated item
    """
    if quantity is None:
        quantity = product.reorder_quantity or 50

    # Check if product already exists in this PO
    existing_item = PurchaseOrderItem.query.filter(
        PurchaseOrderItem.po_id == draft_po.id,
        PurchaseOrderItem.product_id == product.id
    ).first()

    if existing_item:
        # Update quantity - add to existing
        existing_item.quantity_ordered = quantity
        existing_item.unit_cost = product.base_cost or Decimal('0')
        existing_item.subtotal = existing_item.unit_cost * quantity
        existing_item.base_cost = product.base_cost or Decimal('0')
        existing_item.packaging_cost = product.packaging_cost or Decimal('0')
        existing_item.delivery_cost = product.delivery_cost or Decimal('0')
        existing_item.bottle_cost = product.bottle_cost or Decimal('0')
        existing_item.calculate_landed_cost()
        return existing_item

    # Create new item
    item = PurchaseOrderItem(
        po_id=draft_po.id,
        product_id=product.id,
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

    return item


def generate_draft_pos_from_low_stock(user_id=None):
    """
    Main workflow: Detect low stock items and create/update draft POs.

    This function:
    1. Finds all products at or below reorder level
    2. Groups them by supplier
    3. Creates or updates draft POs for each supplier
    4. Adds items to the draft POs

    Args:
        user_id: ID of the user triggering the generation (optional)

    Returns:
        Dictionary with generation results:
        {
            'success': bool,
            'draft_pos_created': int,
            'draft_pos_updated': int,
            'items_added': int,
            'suppliers_affected': list,
            'errors': list
        }
    """
    result = {
        'success': True,
        'draft_pos_created': 0,
        'draft_pos_updated': 0,
        'items_added': 0,
        'suppliers_affected': [],
        'errors': []
    }

    try:
        # Get low stock products grouped by supplier
        grouped_products = get_low_stock_by_supplier()

        if not grouped_products:
            result['message'] = 'No low stock items found'
            return result

        for supplier_id, data in grouped_products.items():
            supplier = data['supplier']
            products = data['products']

            if not supplier or not supplier.is_active:
                result['errors'].append(f'Skipped inactive supplier ID {supplier_id}')
                continue

            # Check if draft PO exists before creating
            existing_draft = PurchaseOrder.query.filter(
                PurchaseOrder.supplier_id == supplier_id,
                PurchaseOrder.status == 'draft',
                PurchaseOrder.is_auto_generated == True
            ).first()

            is_new_po = existing_draft is None

            # Get or create draft PO
            draft_po = get_or_create_draft_po(supplier_id, user_id)

            if is_new_po:
                result['draft_pos_created'] += 1
            else:
                result['draft_pos_updated'] += 1

            # Add each low stock product to the draft PO
            for product in products:
                add_to_draft_po(draft_po, product)
                result['items_added'] += 1

            # Recalculate PO totals
            draft_po.calculate_totals()

            result['suppliers_affected'].append({
                'id': supplier.id,
                'name': supplier.name,
                'po_number': draft_po.po_number,
                'items_count': len(products)
            })

        db.session.commit()
        result['message'] = f"Generated {result['draft_pos_created']} new draft POs, updated {result['draft_pos_updated']} existing drafts"

    except Exception as e:
        db.session.rollback()
        result['success'] = False
        result['errors'].append(str(e))

    return result


def get_draft_pos_for_review():
    """
    Get all draft POs for warehouse review.

    Returns:
        List of draft PurchaseOrder objects with related data
    """
    return PurchaseOrder.query.filter(
        PurchaseOrder.status == 'draft'
    ).order_by(PurchaseOrder.created_at.desc()).all()


def submit_draft_po(po_id, user_id=None):
    """
    Submit a draft PO - changes status from 'draft' to 'ordered'.

    Args:
        po_id: ID of the PurchaseOrder to submit
        user_id: ID of the user submitting (optional)

    Returns:
        Dictionary with result
    """
    po = PurchaseOrder.query.get(po_id)

    if not po:
        return {'success': False, 'error': 'Purchase Order not found'}

    if po.status != 'draft':
        return {'success': False, 'error': f'Cannot submit PO with status: {po.status}'}

    if not po.items.count():
        return {'success': False, 'error': 'Cannot submit PO with no items'}

    try:
        po.status = 'ordered'
        po.order_date = datetime.utcnow()
        if user_id:
            po.user_id = user_id

        # Update supplier balance (add to amount owed)
        supplier = po.supplier
        if supplier:
            supplier.current_balance = (supplier.current_balance or Decimal('0')) + (po.total or Decimal('0'))

        db.session.commit()
        return {'success': True, 'po_number': po.po_number}

    except Exception as e:
        db.session.rollback()
        return {'success': False, 'error': str(e)}


def delete_draft_po(po_id):
    """
    Delete a draft PO (only if status is 'draft').

    Args:
        po_id: ID of the PurchaseOrder to delete

    Returns:
        Dictionary with result
    """
    po = PurchaseOrder.query.get(po_id)

    if not po:
        return {'success': False, 'error': 'Purchase Order not found'}

    if po.status != 'draft':
        return {'success': False, 'error': 'Can only delete draft POs'}

    try:
        # Items will be cascade deleted
        db.session.delete(po)
        db.session.commit()
        return {'success': True, 'message': f'Draft PO {po.po_number} deleted'}

    except Exception as e:
        db.session.rollback()
        return {'success': False, 'error': str(e)}


def get_supplier_order_summary(supplier_id):
    """
    Get order summary for a supplier.

    Returns:
        Dictionary with order statistics
    """
    supplier = Supplier.query.get(supplier_id)
    if not supplier:
        return None

    # Count POs by status
    draft_count = PurchaseOrder.query.filter_by(
        supplier_id=supplier_id, status='draft'
    ).count()

    ordered_count = PurchaseOrder.query.filter_by(
        supplier_id=supplier_id, status='ordered'
    ).count()

    received_count = PurchaseOrder.query.filter_by(
        supplier_id=supplier_id, status='received'
    ).count()

    # Total spent (received orders)
    from sqlalchemy import func
    total_spent = db.session.query(
        func.sum(PurchaseOrder.total)
    ).filter(
        PurchaseOrder.supplier_id == supplier_id,
        PurchaseOrder.status == 'received'
    ).scalar() or Decimal('0')

    return {
        'supplier': supplier,
        'draft_count': draft_count,
        'ordered_count': ordered_count,
        'received_count': received_count,
        'total_spent': float(total_spent),
        'current_balance': float(supplier.current_balance or 0)
    }
