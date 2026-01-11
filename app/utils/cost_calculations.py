"""
Cost Calculation Utilities

Functions for calculating product costs, location-specific pricing,
and supplier payment management.
"""

from datetime import datetime, date
from decimal import Decimal

from app.models import db, Product, Location, Supplier, PurchaseOrder
from app.models_extended import LocationProductCost, ProductCostHistory


def calculate_landed_cost(base_cost, packaging_cost=0, delivery_cost=0, bottle_cost=0):
    """
    Calculate landed cost from cost components.

    Args:
        base_cost: Base supplier price
        packaging_cost: Packaging/box cost
        delivery_cost: Freight/delivery per unit
        bottle_cost: Bottle cost (for perfumes/attars)

    Returns:
        Decimal: Total landed cost
    """
    return (
        Decimal(str(base_cost or 0)) +
        Decimal(str(packaging_cost or 0)) +
        Decimal(str(delivery_cost or 0)) +
        Decimal(str(bottle_cost or 0))
    )


def calculate_final_cost_for_location(landed_cost, location):
    """
    Calculate final cost for a specific location including kiosk charges.

    Args:
        landed_cost: Product's landed cost
        location: Location object

    Returns:
        Decimal: Final cost with kiosk charges applied
    """
    landed = Decimal(str(landed_cost or 0))

    if not location or not location.kiosk_charge_rate:
        return landed

    charge_rate = Decimal(str(location.kiosk_charge_rate or 0))

    if location.kiosk_charge_type == 'percentage':
        kiosk_charge = landed * (charge_rate / 100)
    else:  # fixed
        kiosk_charge = charge_rate

    return landed + kiosk_charge


def recalculate_location_costs(location_id, products=None):
    """
    Recalculate all product costs for a location based on kiosk charge rate.

    Args:
        location_id: Location ID
        products: Optional list of products (if None, all products are recalculated)

    Returns:
        int: Number of products updated
    """
    location = Location.query.get(location_id)
    if not location:
        return 0

    if products is None:
        products = Product.query.filter_by(is_active=True).all()

    count = 0
    for product in products:
        landed_cost = product.landed_cost
        final_cost = calculate_final_cost_for_location(landed_cost, location)

        # Calculate kiosk charge amount
        if location.kiosk_charge_type == 'percentage':
            kiosk_charge = float(landed_cost) * float(location.kiosk_charge_rate or 0) / 100
        else:
            kiosk_charge = float(location.kiosk_charge_rate or 0)

        # Calculate suggested selling price (e.g., 30% margin)
        margin_percentage = Decimal('30')
        suggested_price = final_cost * (1 + margin_percentage / 100)

        # Update or create LocationProductCost record
        lpc = LocationProductCost.query.filter_by(
            location_id=location_id,
            product_id=product.id
        ).first()

        if not lpc:
            lpc = LocationProductCost(
                location_id=location_id,
                product_id=product.id
            )
            db.session.add(lpc)

        lpc.landed_cost = landed_cost
        lpc.kiosk_charge = kiosk_charge
        lpc.final_cost = final_cost
        lpc.suggested_selling_price = suggested_price
        lpc.margin_percentage = margin_percentage
        lpc.last_updated = datetime.utcnow()

        count += 1

    db.session.commit()
    return count


def update_product_cost_history(product_id, user_id=None, po_id=None, reason=None):
    """
    Record cost history when product costs change.

    Args:
        product_id: Product ID
        user_id: User who made the change
        po_id: Purchase order ID (if cost came from PO)
        reason: Reason for the change

    Returns:
        ProductCostHistory: Created history record
    """
    product = Product.query.get(product_id)
    if not product:
        return None

    history = ProductCostHistory(
        product_id=product_id,
        purchase_order_id=po_id,
        base_cost=product.base_cost,
        packaging_cost=product.packaging_cost,
        delivery_cost=product.delivery_cost,
        bottle_cost=product.bottle_cost,
        landed_cost=product.landed_cost,
        effective_date=datetime.utcnow(),
        changed_by=user_id,
        change_reason=reason or 'Cost update'
    )

    db.session.add(history)
    db.session.commit()

    return history


def generate_payment_number():
    """
    Generate unique payment number in format PAY-YYYYMMDD-XXXX.

    Returns:
        str: Unique payment number
    """
    from app.models_extended import SupplierPayment

    today = date.today()
    prefix = f"PAY-{today.strftime('%Y%m%d')}-"

    # Find the last payment number for today
    last_payment = SupplierPayment.query.filter(
        SupplierPayment.payment_number.like(f"{prefix}%")
    ).order_by(SupplierPayment.payment_number.desc()).first()

    if last_payment:
        try:
            last_num = int(last_payment.payment_number.split('-')[-1])
            new_num = last_num + 1
        except ValueError:
            new_num = 1
    else:
        new_num = 1

    return f"{prefix}{new_num:04d}"


def calculate_po_totals(po):
    """
    Calculate PO totals from item cost breakdowns.

    Args:
        po: PurchaseOrder object

    Returns:
        dict: Dictionary with calculated totals
    """
    total_base = Decimal('0')
    total_packaging = Decimal('0')
    total_delivery = Decimal('0')
    total_bottle = Decimal('0')
    total_landed = Decimal('0')

    for item in po.items:
        qty = Decimal(str(item.quantity_ordered or 0))

        base = Decimal(str(item.base_cost or 0)) * qty
        packaging = Decimal(str(item.packaging_cost or 0)) * qty
        delivery = Decimal(str(item.delivery_cost or 0)) * qty
        bottle = Decimal(str(item.bottle_cost or 0)) * qty
        landed = Decimal(str(item.landed_cost or 0)) * qty

        total_base += base
        total_packaging += packaging
        total_delivery += delivery
        total_bottle += bottle
        total_landed += landed

    return {
        'total_base': float(total_base),
        'total_packaging': float(total_packaging),
        'total_delivery': float(total_delivery),
        'total_bottle': float(total_bottle),
        'total_landed': float(total_landed),
        'grand_total': float(total_landed)
    }


def update_supplier_balance(supplier_id):
    """
    Recalculate supplier balance from ledger entries.

    Args:
        supplier_id: Supplier ID

    Returns:
        Decimal: Updated balance
    """
    from app.models_extended import SupplierLedger

    supplier = Supplier.query.get(supplier_id)
    if not supplier:
        return 0

    # Sum all debits minus credits
    result = db.session.query(
        db.func.coalesce(db.func.sum(SupplierLedger.debit), 0) -
        db.func.coalesce(db.func.sum(SupplierLedger.credit), 0)
    ).filter(
        SupplierLedger.supplier_id == supplier_id
    ).scalar()

    balance = Decimal(str(result or 0))

    supplier.current_balance = balance
    db.session.commit()

    return balance


def get_supplier_payment_reminders(days_threshold=7):
    """
    Get suppliers with upcoming or overdue payments.

    Args:
        days_threshold: Days to look ahead for upcoming payments

    Returns:
        dict: Dictionary with overdue and upcoming lists
    """
    from datetime import timedelta

    today = date.today()
    threshold_date = today + timedelta(days=days_threshold)

    # Get all suppliers with outstanding balance
    suppliers_with_balance = Supplier.query.filter(
        Supplier.is_active == True,
        Supplier.current_balance > 0,
        Supplier.reminder_enabled == True
    ).all()

    overdue = []
    upcoming = []

    for supplier in suppliers_with_balance:
        # Get unpaid POs for this supplier
        unpaid_pos = PurchaseOrder.query.filter(
            PurchaseOrder.supplier_id == supplier.id,
            PurchaseOrder.payment_status.in_(['unpaid', 'partial']),
            PurchaseOrder.status == 'completed'
        ).all()

        for po in unpaid_pos:
            # Calculate due date based on supplier's payment terms
            if po.order_date and supplier.payment_due_days:
                due_date = po.order_date.date() + timedelta(days=supplier.payment_due_days)

                reminder_item = {
                    'supplier': supplier,
                    'po': po,
                    'due_date': due_date,
                    'amount_due': float(po.amount_due or po.total or 0),
                    'days_overdue': (today - due_date).days if today > due_date else 0
                }

                if due_date < today:
                    overdue.append(reminder_item)
                elif due_date <= threshold_date:
                    upcoming.append(reminder_item)

    # Sort by days overdue (descending for overdue, ascending for upcoming)
    overdue.sort(key=lambda x: x['days_overdue'], reverse=True)
    upcoming.sort(key=lambda x: x['due_date'])

    return {
        'overdue': overdue,
        'upcoming': upcoming,
        'total_overdue_count': len(overdue),
        'total_overdue_amount': sum(x['amount_due'] for x in overdue),
        'total_upcoming_count': len(upcoming),
        'total_upcoming_amount': sum(x['amount_due'] for x in upcoming)
    }


def calculate_margin(cost, selling_price):
    """
    Calculate profit margin percentage.

    Args:
        cost: Cost price
        selling_price: Selling price

    Returns:
        float: Margin percentage
    """
    cost = float(cost or 0)
    selling_price = float(selling_price or 0)

    if cost <= 0:
        return 0

    return ((selling_price - cost) / cost) * 100


def calculate_selling_price_from_margin(cost, margin_percentage):
    """
    Calculate selling price from cost and desired margin.

    Args:
        cost: Cost price
        margin_percentage: Desired margin percentage

    Returns:
        float: Calculated selling price
    """
    cost = float(cost or 0)
    margin = float(margin_percentage or 0)

    return cost * (1 + margin / 100)
