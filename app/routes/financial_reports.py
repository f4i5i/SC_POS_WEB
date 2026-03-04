"""
Financial Reports Routes
Comprehensive financial reporting including:
- Dead Stock Report
- Cash Flow Report
- Profit Margin Analysis
- Exception Reports Dashboard
"""

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import func, and_, or_, case
from app.models import (db, Product, Sale, SaleItem, Location, LocationStock,
                        Category, DayClose, DiscountLog, VoidRefundLog,
                        PriceChangeLog, Customer, User, Payment,
                        ProductionOrder, ProductionMaterialConsumption,
                        Recipe, RecipeIngredient, RawMaterial,
                        StockMovement, InventorySpotCheck, InventorySpotCheckItem,
                        Supplier)
from app.models_extended import (Expense, ExpenseCategory, SupplierPayment,
                                 ProductCostHistory,
                                 GiftVoucher, GiftVoucherTransaction,
                                 Promotion, PromotionUsage, TaxReport,
                                 DuePayment, DuePaymentInstallment)
from app.utils.permissions import permission_required, Permissions
from app.utils.location_context import get_current_location

bp = Blueprint('financial_reports', __name__, url_prefix='/financial-reports')


# ============================================================================
# DEAD STOCK REPORT
# ============================================================================

@bp.route('/dead-stock')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def dead_stock():
    """Dead stock report - products with no or very low sales"""
    location = get_current_location()

    # Parameters
    days = request.args.get('days', 90, type=int)  # No sales in X days
    include_zero_stock = request.args.get('include_zero', 'false') == 'true'
    min_value = request.args.get('min_value', 0, type=float)
    category_id = request.args.get('category_id', type=int)

    cutoff_date = date.today() - timedelta(days=days)

    # Get products with their last sale date
    subquery = db.session.query(
        SaleItem.product_id,
        func.max(Sale.sale_date).label('last_sale_date'),
        func.sum(SaleItem.quantity).label('total_sold')
    ).join(Sale).filter(
        Sale.status == 'completed',
        Sale.sale_date >= cutoff_date
    )

    if location and not current_user.is_global_admin:
        subquery = subquery.filter(Sale.location_id == location.id)

    subquery = subquery.group_by(SaleItem.product_id).subquery()

    # Get products with stock
    query = db.session.query(
        Product,
        func.coalesce(LocationStock.quantity, 0).label('stock_qty'),
        subquery.c.last_sale_date,
        func.coalesce(subquery.c.total_sold, 0).label('recent_sales')
    ).outerjoin(
        LocationStock, and_(
            LocationStock.product_id == Product.id,
            LocationStock.location_id == location.id if location else True
        )
    ).outerjoin(
        subquery, Product.id == subquery.c.product_id
    ).filter(
        Product.is_active == True
    )

    # Filter products with no recent sales
    query = query.filter(
        or_(
            subquery.c.total_sold.is_(None),
            subquery.c.total_sold == 0
        )
    )

    if not include_zero_stock:
        query = query.filter(func.coalesce(LocationStock.quantity, 0) > 0)

    if category_id:
        query = query.filter(Product.category_id == category_id)

    results = query.all()

    # Calculate values
    dead_stock_items = []
    total_dead_stock_value = Decimal('0')
    total_dead_stock_units = 0

    for product, stock_qty, last_sale, recent_sales in results:
        cost = product.cost_price or Decimal('0')
        value = cost * Decimal(str(stock_qty))

        if value >= min_value:
            # Get all-time last sale
            last_sale_ever = db.session.query(func.max(Sale.sale_date)).join(
                SaleItem
            ).filter(SaleItem.product_id == product.id).scalar()

            days_since_sale = None
            if last_sale_ever:
                days_since_sale = (date.today() - last_sale_ever.date()).days

            dead_stock_items.append({
                'product': product,
                'stock_qty': stock_qty,
                'cost_price': cost,
                'stock_value': value,
                'last_sale_date': last_sale_ever,
                'days_since_sale': days_since_sale,
                'recent_sales': recent_sales
            })

            total_dead_stock_value += value
            total_dead_stock_units += stock_qty

    # Sort by value descending
    dead_stock_items.sort(key=lambda x: x['stock_value'], reverse=True)

    categories = Category.query.order_by(Category.name).all()

    return render_template('financial_reports/dead_stock.html',
                         items=dead_stock_items,
                         total_value=total_dead_stock_value,
                         total_units=total_dead_stock_units,
                         days=days,
                         categories=categories,
                         category_id=category_id,
                         include_zero_stock=include_zero_stock,
                         min_value=min_value,
                         location=location)


# ============================================================================
# CASH FLOW REPORT
# ============================================================================

@bp.route('/cash-flow')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def cash_flow():
    """Cash flow report - inflows and outflows including supplier payments"""
    location = get_current_location()

    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    location_id = request.args.get('location_id', type=int)

    if not from_date:
        from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')

    start_date = datetime.strptime(from_date, '%Y-%m-%d')
    end_date = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)

    # Location filter — admin can pick, non-admin sees own location
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    effective_location_id = None
    if not current_user.is_global_admin:
        if current_user.location_id:
            effective_location_id = current_user.location_id
    elif location_id:
        effective_location_id = location_id

    sale_location_filter = []
    if effective_location_id:
        sale_location_filter.append(Sale.location_id == effective_location_id)

    # ── INFLOWS ──────────────────────────────────────────────────
    # For non-split sales: attribute Sale.total to Sale.payment_method
    # For split sales: use Payment model to get per-channel amounts
    base_sale_filter = [
        Sale.sale_date >= start_date,
        Sale.sale_date < end_date,
        Sale.status == 'completed',
    ]

    # Non-split sales by payment method
    def non_split_sum(method_filter):
        return db.session.query(
            func.coalesce(func.sum(Sale.total), 0)
        ).filter(
            *base_sale_filter,
            Sale.payment_method != 'split',
            method_filter,
            *sale_location_filter
        ).scalar() or Decimal('0')

    cash_sales = non_split_sum(Sale.payment_method == 'cash')
    card_sales = non_split_sum(Sale.payment_method == 'card')
    digital_sales = non_split_sum(Sale.payment_method.in_(['easypaisa', 'jazzcash']))
    bank_sales = non_split_sum(Sale.payment_method == 'bank_transfer')

    # Split sales — get per-channel amounts from Payment model
    split_sale_ids = db.session.query(Sale.id).filter(
        *base_sale_filter,
        Sale.payment_method == 'split',
        *sale_location_filter
    ).subquery()

    split_by_method = db.session.query(
        Payment.payment_method,
        func.coalesce(func.sum(Payment.amount), 0)
    ).filter(
        Payment.sale_id.in_(db.session.query(split_sale_ids))
    ).group_by(Payment.payment_method).all()

    for method, amount in split_by_method:
        amount = Decimal(str(amount))
        if method == 'cash':
            cash_sales += amount
        elif method == 'card':
            card_sales += amount
        elif method in ('easypaisa', 'jazzcash'):
            digital_sales += amount
        elif method == 'bank_transfer':
            bank_sales += amount

    total_inflow = cash_sales + card_sales + digital_sales + bank_sales

    # ── OUTFLOWS ─────────────────────────────────────────────────
    # 1. Expenses
    expense_filter = [
        Expense.expense_date >= start_date.date(),
        Expense.expense_date <= end_date.date()
    ]
    if effective_location_id:
        expense_filter.append(Expense.location_id == effective_location_id)

    total_expenses = db.session.query(
        func.sum(Expense.amount)
    ).filter(*expense_filter).scalar() or Decimal('0')

    # 2. Refunds (cash refunds only)
    refund_filter = [
        VoidRefundLog.created_at >= start_date,
        VoidRefundLog.created_at < end_date,
        VoidRefundLog.action_type.in_(['refund', 'partial_refund']),
        VoidRefundLog.refund_method == 'cash'
    ]
    if effective_location_id:
        refund_filter.append(VoidRefundLog.location_id == effective_location_id)

    total_refunds = db.session.query(
        func.sum(VoidRefundLog.voided_refunded_amount)
    ).filter(*refund_filter).scalar() or Decimal('0')

    # 3. Supplier Payments
    supplier_payment_filter = [
        SupplierPayment.payment_date >= start_date.date(),
        SupplierPayment.payment_date <= end_date.date(),
        SupplierPayment.status == 'completed'
    ]

    total_supplier_payments = db.session.query(
        func.sum(SupplierPayment.amount)
    ).filter(*supplier_payment_filter).scalar() or Decimal('0')

    # Supplier payment breakdown by method
    supplier_by_method = db.session.query(
        SupplierPayment.payment_method,
        func.sum(SupplierPayment.amount).label('total')
    ).filter(*supplier_payment_filter).group_by(SupplierPayment.payment_method).all()

    total_outflow = total_expenses + total_refunds + total_supplier_payments

    # Net Cash Flow
    net_cash_flow = total_inflow - total_outflow

    # ── DAILY BREAKDOWN ──────────────────────────────────────────
    daily_data = []
    current_date = start_date.date()
    while current_date < end_date.date():
        day_start = datetime.combine(current_date, datetime.min.time())
        day_end = day_start + timedelta(days=1)

        day_sales = db.session.query(
            func.sum(Sale.total)
        ).filter(
            Sale.sale_date >= day_start,
            Sale.sale_date < day_end,
            Sale.status == 'completed',
            *sale_location_filter
        ).scalar() or Decimal('0')

        day_expense_filter = [Expense.expense_date == current_date]
        if effective_location_id:
            day_expense_filter.append(Expense.location_id == effective_location_id)

        day_expenses = db.session.query(
            func.sum(Expense.amount)
        ).filter(*day_expense_filter).scalar() or Decimal('0')

        day_supplier = db.session.query(
            func.sum(SupplierPayment.amount)
        ).filter(
            SupplierPayment.payment_date == current_date,
            SupplierPayment.status == 'completed'
        ).scalar() or Decimal('0')

        day_outflow = day_expenses + day_supplier

        daily_data.append({
            'date': current_date.strftime('%Y-%m-%d'),
            'date_obj': current_date,
            'inflow': float(day_sales),
            'outflow': float(day_outflow),
            'expenses': float(day_expenses),
            'supplier_payments': float(day_supplier),
            'net': float(day_sales - day_outflow)
        })

        current_date += timedelta(days=1)

    # Expense breakdown by category
    expense_by_category = db.session.query(
        ExpenseCategory.name,
        func.sum(Expense.amount).label('total')
    ).join(ExpenseCategory, Expense.category_id == ExpenseCategory.id).filter(
        *expense_filter
    ).group_by(ExpenseCategory.id).all()

    return render_template('financial_reports/cash_flow.html',
                         from_date=from_date,
                         to_date=to_date,
                         cash_sales=cash_sales,
                         card_sales=card_sales,
                         digital_sales=digital_sales,
                         bank_sales=bank_sales,
                         total_inflow=total_inflow,
                         total_expenses=total_expenses,
                         total_refunds=total_refunds,
                         total_supplier_payments=total_supplier_payments,
                         supplier_by_method=supplier_by_method,
                         total_outflow=total_outflow,
                         net_cash_flow=net_cash_flow,
                         daily_data=daily_data,
                         expense_by_category=expense_by_category,
                         locations=locations,
                         selected_location_id=effective_location_id,
                         location=location)


# ============================================================================
# PROFIT MARGIN ANALYSIS
# ============================================================================

@bp.route('/profit-margin')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def profit_margin():
    """Profit margin analysis by product/category"""
    location = get_current_location()

    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    category_id = request.args.get('category_id', type=int)
    group_by = request.args.get('group_by', 'product')  # product, category

    if not from_date:
        from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')

    start_date = datetime.strptime(from_date, '%Y-%m-%d')
    end_date = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)

    base_filter = [
        Sale.sale_date >= start_date,
        Sale.sale_date < end_date,
        Sale.status == 'completed'
    ]
    if location and not current_user.is_global_admin:
        base_filter.append(Sale.location_id == location.id)
    if category_id:
        base_filter.append(Product.category_id == category_id)

    if group_by == 'category':
        # Group by category
        results = db.session.query(
            Category.name.label('name'),
            func.sum(SaleItem.quantity).label('qty_sold'),
            func.sum(SaleItem.subtotal).label('revenue'),
            func.sum(SaleItem.quantity * Product.cost_price).label('cost')
        ).select_from(SaleItem).join(Sale).join(Product).outerjoin(
            Category, Product.category_id == Category.id
        ).filter(*base_filter).group_by(Category.id).all()
    else:
        # Group by product
        results = db.session.query(
            Product.name.label('name'),
            Product.barcode.label('barcode'),
            func.sum(SaleItem.quantity).label('qty_sold'),
            func.sum(SaleItem.subtotal).label('revenue'),
            func.sum(SaleItem.quantity * Product.cost_price).label('cost')
        ).select_from(SaleItem).join(Sale).join(Product).filter(
            *base_filter
        ).group_by(Product.id).all()

    # Calculate margins
    margin_data = []
    total_revenue = Decimal('0')
    total_cost = Decimal('0')
    total_profit = Decimal('0')

    for row in results:
        revenue = row.revenue or Decimal('0')
        cost = row.cost or Decimal('0')
        profit = revenue - cost
        margin_pct = (profit / revenue * 100) if revenue else Decimal('0')

        margin_data.append({
            'name': row.name or 'Uncategorized',
            'barcode': getattr(row, 'barcode', None),
            'qty_sold': row.qty_sold or 0,
            'revenue': revenue,
            'cost': cost,
            'profit': profit,
            'margin_pct': margin_pct
        })

        total_revenue += revenue
        total_cost += cost
        total_profit += profit

    # Sort by profit descending
    margin_data.sort(key=lambda x: x['profit'], reverse=True)

    overall_margin = (total_profit / total_revenue * 100) if total_revenue else Decimal('0')

    # Top performers (highest margin %)
    top_margin = sorted([m for m in margin_data if m['revenue'] > 0],
                       key=lambda x: x['margin_pct'], reverse=True)[:10]

    # Low performers (lowest margin %)
    low_margin = sorted([m for m in margin_data if m['revenue'] > 0],
                       key=lambda x: x['margin_pct'])[:10]

    categories = Category.query.order_by(Category.name).all()

    return render_template('financial_reports/profit_margin.html',
                         from_date=from_date,
                         to_date=to_date,
                         group_by=group_by,
                         margin_data=margin_data,
                         total_revenue=total_revenue,
                         total_cost=total_cost,
                         total_profit=total_profit,
                         overall_margin=overall_margin,
                         top_margin=top_margin,
                         low_margin=low_margin,
                         categories=categories,
                         category_id=category_id,
                         location=location)


# ============================================================================
# EXCEPTION REPORTS DASHBOARD
# ============================================================================

@bp.route('/exceptions')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def exceptions_dashboard():
    """Exception reports dashboard - unusual activities requiring attention"""
    location = get_current_location()

    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    if not from_date:
        from_date = (date.today() - timedelta(days=7)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')

    start_date = datetime.strptime(from_date, '%Y-%m-%d')
    end_date = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)

    location_filter = []
    if location and not current_user.is_global_admin:
        location_filter = [Sale.location_id == location.id]

    exceptions = []

    # 1. High Discount Sales (>15% discount)
    high_discount_sales = Sale.query.filter(
        Sale.sale_date >= start_date,
        Sale.sale_date < end_date,
        Sale.status == 'completed',
        Sale.discount_type == 'percentage',
        Sale.discount > 15,
        *location_filter
    ).order_by(Sale.discount.desc()).limit(20).all()

    if high_discount_sales:
        exceptions.append({
            'type': 'high_discount',
            'title': 'High Discount Sales (>15%)',
            'count': len(high_discount_sales),
            'severity': 'warning',
            'items': [{'sale': s, 'value': f'{s.discount}%'} for s in high_discount_sales]
        })

    # 2. Voided Sales
    voided_sales = VoidRefundLog.query.filter(
        VoidRefundLog.created_at >= start_date,
        VoidRefundLog.created_at < end_date,
        VoidRefundLog.action_type == 'void'
    ).order_by(VoidRefundLog.voided_refunded_amount.desc()).limit(20).all()

    if voided_sales:
        total_voided = sum(float(v.voided_refunded_amount or 0) for v in voided_sales)
        exceptions.append({
            'type': 'voided_sales',
            'title': 'Voided Sales',
            'count': len(voided_sales),
            'total': total_voided,
            'severity': 'danger',
            'items': voided_sales
        })

    # 3. Large Refunds (>Rs. 5000)
    large_refunds = VoidRefundLog.query.filter(
        VoidRefundLog.created_at >= start_date,
        VoidRefundLog.created_at < end_date,
        VoidRefundLog.action_type.in_(['refund', 'partial_refund']),
        VoidRefundLog.voided_refunded_amount >= 5000
    ).order_by(VoidRefundLog.voided_refunded_amount.desc()).limit(20).all()

    if large_refunds:
        exceptions.append({
            'type': 'large_refunds',
            'title': 'Large Refunds (>Rs. 5,000)',
            'count': len(large_refunds),
            'severity': 'danger',
            'items': large_refunds
        })

    # 4. Large Price Changes (>20%)
    large_price_changes = PriceChangeLog.query.filter(
        PriceChangeLog.changed_at >= start_date,
        PriceChangeLog.changed_at < end_date,
        func.abs(PriceChangeLog.change_percentage) >= 20
    ).order_by(func.abs(PriceChangeLog.change_percentage).desc()).limit(20).all()

    if large_price_changes:
        exceptions.append({
            'type': 'price_changes',
            'title': 'Large Price Changes (>20%)',
            'count': len(large_price_changes),
            'severity': 'warning',
            'items': large_price_changes
        })

    # 5. Cash Variances
    cash_variances = DayClose.query.filter(
        DayClose.close_date >= start_date.date(),
        DayClose.close_date <= end_date.date(),
        DayClose.cash_variance != 0
    ).order_by(func.abs(DayClose.cash_variance).desc()).limit(20).all()

    if cash_variances:
        total_variance = sum(float(abs(d.cash_variance or 0)) for d in cash_variances)
        exceptions.append({
            'type': 'cash_variance',
            'title': 'Cash Variances',
            'count': len(cash_variances),
            'total': total_variance,
            'severity': 'danger',
            'items': cash_variances
        })

    # 6. Credit Sales Without Customer
    credit_sales_no_customer = Sale.query.filter(
        Sale.sale_date >= start_date,
        Sale.sale_date < end_date,
        Sale.payment_method == 'credit',
        Sale.customer_id.is_(None),
        *location_filter
    ).limit(20).all()

    if credit_sales_no_customer:
        exceptions.append({
            'type': 'credit_no_customer',
            'title': 'Credit Sales Without Customer',
            'count': len(credit_sales_no_customer),
            'severity': 'warning',
            'items': [{'sale': s} for s in credit_sales_no_customer]
        })

    # 7. Multiple Discounts by Same Cashier (same day)
    discount_abuse = db.session.query(
        DiscountLog.user_id,
        func.date(DiscountLog.created_at).label('date'),
        func.count(DiscountLog.id).label('count'),
        func.sum(DiscountLog.discount_amount).label('total')
    ).filter(
        DiscountLog.created_at >= start_date,
        DiscountLog.created_at < end_date
    ).group_by(
        DiscountLog.user_id,
        func.date(DiscountLog.created_at)
    ).having(func.count(DiscountLog.id) > 10).all()

    if discount_abuse:
        abuse_items = []
        for row in discount_abuse:
            user = User.query.get(row.user_id)
            abuse_items.append({
                'user': user,
                'date': row.date,
                'count': row.count,
                'total': row.total
            })
        exceptions.append({
            'type': 'discount_abuse',
            'title': 'Excessive Discounts (>10/day)',
            'count': len(discount_abuse),
            'severity': 'danger',
            'items': abuse_items
        })

    # Summary stats
    summary = {
        'total_exceptions': sum(e['count'] for e in exceptions),
        'high_severity': sum(e['count'] for e in exceptions if e['severity'] == 'danger'),
        'medium_severity': sum(e['count'] for e in exceptions if e['severity'] == 'warning')
    }

    return render_template('financial_reports/exceptions.html',
                         from_date=from_date,
                         to_date=to_date,
                         exceptions=exceptions,
                         summary=summary,
                         location=location)


# ============================================================================
# PRODUCTION COST ACTUALS REPORT
# ============================================================================

@bp.route('/production-cost')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def production_cost():
    """Production cost actuals — recipe cost vs actual, total oil consumed"""
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    location_id = request.args.get('location_id', type=int)

    if not from_date:
        from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')

    start_date = datetime.strptime(from_date, '%Y-%m-%d')
    end_date = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)

    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    effective_location_id = None
    if not current_user.is_global_admin:
        if current_user.location_id:
            effective_location_id = current_user.location_id
    elif location_id:
        effective_location_id = location_id

    # Get completed production orders in date range
    order_filter = [
        ProductionOrder.status == 'completed',
        ProductionOrder.completed_at >= start_date,
        ProductionOrder.completed_at < end_date
    ]
    if effective_location_id:
        order_filter.append(ProductionOrder.location_id == effective_location_id)

    orders = ProductionOrder.query.filter(*order_filter).all()

    production_data = []
    total_recipe_cost = Decimal('0')
    total_actual_cost = Decimal('0')
    total_units_produced = 0
    material_totals = {}  # {raw_material_id: {name, total_consumed, unit, cost_per_unit, total_cost}}

    for order in orders:
        recipe = order.recipe
        product = order.product
        qty_produced = order.quantity_produced or 0

        if qty_produced == 0:
            continue

        # Expected cost per unit from recipe ingredients
        recipe_cost_per_unit = Decimal('0')
        ingredients = list(RecipeIngredient.query.filter_by(recipe_id=recipe.id).all())
        for ing in ingredients:
            rm = ing.raw_material
            if ing.is_packaging:
                recipe_cost_per_unit += rm.cost_per_unit or Decimal('0')
            else:
                oil_pct = float(recipe.oil_percentage or 100) / 100.0
                output_ml = float(recipe.output_size_ml or 0)
                pct = float(ing.percentage or 100) / 100.0
                ml_needed = output_ml * oil_pct * pct
                recipe_cost_per_unit += Decimal(str(ml_needed)) * (rm.cost_per_unit or Decimal('0'))

        expected_total = recipe_cost_per_unit * qty_produced

        # Actual cost from material consumptions
        consumptions = ProductionMaterialConsumption.query.filter_by(
            production_order_id=order.id
        ).all()

        actual_total = Decimal('0')
        for c in consumptions:
            rm = c.raw_material
            consumed = c.quantity_consumed or c.quantity_required or Decimal('0')
            cost = consumed * (rm.cost_per_unit or Decimal('0'))
            actual_total += cost

            # Track material totals
            if rm.id not in material_totals:
                material_totals[rm.id] = {
                    'name': rm.name,
                    'code': rm.code,
                    'total_consumed': Decimal('0'),
                    'cost_per_unit': rm.cost_per_unit or Decimal('0'),
                    'total_cost': Decimal('0'),
                    'unit': c.unit or 'ml'
                }
            material_totals[rm.id]['total_consumed'] += consumed
            material_totals[rm.id]['total_cost'] += cost

        variance = actual_total - expected_total
        actual_per_unit = actual_total / qty_produced if qty_produced else Decimal('0')

        production_data.append({
            'order_number': order.order_number,
            'product_name': product.name if product else 'Unknown',
            'recipe_name': recipe.name,
            'recipe_type': recipe.recipe_type,
            'qty_produced': qty_produced,
            'recipe_cost_per_unit': float(recipe_cost_per_unit),
            'actual_cost_per_unit': float(actual_per_unit),
            'expected_total': float(expected_total),
            'actual_total': float(actual_total),
            'variance': float(variance),
            'variance_pct': float(variance / expected_total * 100) if expected_total else 0,
            'completed_at': order.completed_at
        })

        total_recipe_cost += expected_total
        total_actual_cost += actual_total
        total_units_produced += qty_produced

    # Sort materials by total cost descending
    material_list = sorted(material_totals.values(), key=lambda x: x['total_cost'], reverse=True)

    return render_template('financial_reports/production_cost.html',
                         from_date=from_date,
                         to_date=to_date,
                         production_data=production_data,
                         material_list=material_list,
                         total_recipe_cost=float(total_recipe_cost),
                         total_actual_cost=float(total_actual_cost),
                         total_variance=float(total_actual_cost - total_recipe_cost),
                         total_units_produced=total_units_produced,
                         locations=locations,
                         selected_location_id=effective_location_id)


# ============================================================================
# TAX LIABILITY REPORT
# ============================================================================

@bp.route('/tax-liability')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def tax_liability():
    """Tax liability report — sales tax collected vs input tax"""
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    location_id = request.args.get('location_id', type=int)

    if not from_date:
        from_date = (date.today().replace(day=1)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')

    start_date = datetime.strptime(from_date, '%Y-%m-%d')
    end_date = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)

    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    effective_location_id = None
    if not current_user.is_global_admin:
        if current_user.location_id:
            effective_location_id = current_user.location_id
    elif location_id:
        effective_location_id = location_id

    sale_filter = [
        Sale.sale_date >= start_date,
        Sale.sale_date < end_date,
        Sale.status == 'completed'
    ]
    if effective_location_id:
        sale_filter.append(Sale.location_id == effective_location_id)

    # Total sales
    total_sales = db.session.query(
        func.coalesce(func.sum(Sale.total), 0)
    ).filter(*sale_filter).scalar() or Decimal('0')

    # Tax collected (from Sale.tax_amount if it exists)
    tax_collected = Decimal('0')
    try:
        tax_collected = db.session.query(
            func.coalesce(func.sum(Sale.tax_amount), 0)
        ).filter(*sale_filter).scalar() or Decimal('0')
    except Exception:
        pass  # tax_amount column may not exist

    # Get existing tax reports for reference
    tax_reports = TaxReport.query.filter(
        TaxReport.period_start >= start_date.date(),
        TaxReport.period_end <= end_date.date()
    ).order_by(TaxReport.period_start.desc()).all()

    # Monthly breakdown
    monthly_data = []
    current_month = start_date.replace(day=1)
    while current_month < end_date:
        next_month = (current_month + timedelta(days=32)).replace(day=1)
        month_end = min(next_month, end_date)

        month_filter = list(sale_filter)
        # Replace date filters for this month
        month_sale_filter = [
            Sale.sale_date >= current_month,
            Sale.sale_date < month_end,
            Sale.status == 'completed'
        ]
        if effective_location_id:
            month_sale_filter.append(Sale.location_id == effective_location_id)

        month_sales = db.session.query(
            func.coalesce(func.sum(Sale.total), 0)
        ).filter(*month_sale_filter).scalar() or Decimal('0')

        month_tax = Decimal('0')
        try:
            month_tax = db.session.query(
                func.coalesce(func.sum(Sale.tax_amount), 0)
            ).filter(*month_sale_filter).scalar() or Decimal('0')
        except Exception:
            pass

        monthly_data.append({
            'month': current_month.strftime('%B %Y'),
            'total_sales': float(month_sales),
            'tax_collected': float(month_tax),
            'effective_rate': float(month_tax / month_sales * 100) if month_sales else 0
        })

        current_month = next_month

    return render_template('financial_reports/tax_liability.html',
                         from_date=from_date,
                         to_date=to_date,
                         total_sales=float(total_sales),
                         tax_collected=float(tax_collected),
                         effective_rate=float(tax_collected / total_sales * 100) if total_sales else 0,
                         tax_reports=tax_reports,
                         monthly_data=monthly_data,
                         locations=locations,
                         selected_location_id=effective_location_id)


# ============================================================================
# SUPPLIER PAYABLES AGING REPORT
# ============================================================================

@bp.route('/supplier-aging')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def supplier_aging():
    """Supplier payables aging — 0-30, 31-60, 60+ day buckets"""
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()

    today = date.today()
    aging_data = []
    totals = {'current': Decimal('0'), 'days_30': Decimal('0'),
              'days_60': Decimal('0'), 'days_90': Decimal('0'),
              'over_90': Decimal('0'), 'total': Decimal('0')}

    for supplier in suppliers:
        balance = supplier.current_balance or Decimal('0')
        if balance <= 0:
            continue

        # Get last payment info
        last_payment = SupplierPayment.query.filter_by(
            supplier_id=supplier.id,
            status='completed'
        ).order_by(SupplierPayment.payment_date.desc()).first()

        # Use last_payment_date or default to supplier creation
        last_date = supplier.last_payment_date or (supplier.created_at.date() if supplier.created_at else today)
        days_outstanding = (today - last_date).days if last_date else 0

        # Bucket the balance
        current = Decimal('0')
        d30 = Decimal('0')
        d60 = Decimal('0')
        d90 = Decimal('0')
        over90 = Decimal('0')

        if days_outstanding <= 0:
            current = balance
        elif days_outstanding <= 30:
            d30 = balance
        elif days_outstanding <= 60:
            d60 = balance
        elif days_outstanding <= 90:
            d90 = balance
        else:
            over90 = balance

        aging_data.append({
            'supplier_name': supplier.name,
            'contact': supplier.contact_person or '',
            'phone': supplier.phone or '',
            'current': float(current),
            'days_30': float(d30),
            'days_60': float(d60),
            'days_90': float(d90),
            'over_90': float(over90),
            'total': float(balance),
            'days_outstanding': days_outstanding,
            'last_payment_date': last_payment.payment_date if last_payment else None,
            'credit_limit': float(supplier.credit_limit or 0),
            'over_limit': bool(supplier.current_balance and supplier.credit_limit and
                             supplier.current_balance > supplier.credit_limit)
        })

        totals['current'] += current
        totals['days_30'] += d30
        totals['days_60'] += d60
        totals['days_90'] += d90
        totals['over_90'] += over90
        totals['total'] += balance

    # Sort by total outstanding descending
    aging_data.sort(key=lambda x: x['total'], reverse=True)

    return render_template('financial_reports/supplier_aging.html',
                         aging_data=aging_data,
                         totals={k: float(v) for k, v in totals.items()},
                         supplier_count=len(aging_data))


# ============================================================================
# INVENTORY SHRINKAGE / LOSS REPORT
# ============================================================================

@bp.route('/inventory-shrinkage')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def inventory_shrinkage():
    """Inventory shrinkage — spot check variances + damage movements"""
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    location_id = request.args.get('location_id', type=int)

    if not from_date:
        from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')

    start_date = datetime.strptime(from_date, '%Y-%m-%d')
    end_date = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)

    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    effective_location_id = None
    if not current_user.is_global_admin:
        if current_user.location_id:
            effective_location_id = current_user.location_id
    elif location_id:
        effective_location_id = location_id

    # 1. Spot check variances
    spot_filter = [
        InventorySpotCheck.check_date >= start_date.date(),
        InventorySpotCheck.check_date <= end_date.date()
    ]
    if effective_location_id:
        spot_filter.append(InventorySpotCheck.location_id == effective_location_id)

    spot_checks = InventorySpotCheck.query.filter(*spot_filter).order_by(
        InventorySpotCheck.check_date.desc()
    ).all()

    total_variance_value = sum(float(sc.total_variance_value or 0) for sc in spot_checks)
    total_items_checked = sum(sc.total_items_checked or 0 for sc in spot_checks)
    total_items_variance = sum(sc.items_variance or 0 for sc in spot_checks)

    # 2. Damage movements
    damage_filter = [
        StockMovement.movement_type == 'damage',
        StockMovement.timestamp >= start_date,
        StockMovement.timestamp < end_date
    ]
    if effective_location_id:
        damage_filter.append(StockMovement.location_id == effective_location_id)

    damage_movements = db.session.query(
        Product.name.label('product_name'),
        Product.sku.label('product_code'),
        func.sum(func.abs(StockMovement.quantity)).label('damaged_qty'),
        func.sum(func.abs(StockMovement.quantity) * Product.cost_price).label('damage_value')
    ).join(Product, StockMovement.product_id == Product.id).filter(
        *damage_filter
    ).group_by(Product.id).order_by(
        func.sum(func.abs(StockMovement.quantity) * Product.cost_price).desc()
    ).all()

    total_damage_qty = sum(float(d.damaged_qty or 0) for d in damage_movements)
    total_damage_value = sum(float(d.damage_value or 0) for d in damage_movements)

    total_shrinkage = total_variance_value + total_damage_value

    return render_template('financial_reports/inventory_shrinkage.html',
                         from_date=from_date,
                         to_date=to_date,
                         spot_checks=spot_checks,
                         damage_movements=damage_movements,
                         total_variance_value=total_variance_value,
                         total_items_checked=total_items_checked,
                         total_items_variance=total_items_variance,
                         total_damage_qty=total_damage_qty,
                         total_damage_value=total_damage_value,
                         total_shrinkage=total_shrinkage,
                         locations=locations,
                         selected_location_id=effective_location_id)


# ============================================================================
# PRODUCT COST HISTORY / MARGIN EROSION REPORT
# ============================================================================

@bp.route('/cost-history')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def cost_history():
    """Product cost history — track cost changes and margin erosion"""
    product_id = request.args.get('product_id', type=int)
    category_id = request.args.get('category_id', type=int)

    categories = Category.query.order_by(Category.name).all()

    # Products with cost history
    product_filter = [Product.is_active == True]
    if category_id:
        product_filter.append(Product.category_id == category_id)

    products_with_history = db.session.query(
        Product.id,
        Product.name,
        Product.sku,
        Product.cost_price,
        Product.selling_price,
        func.count(ProductCostHistory.id).label('change_count')
    ).outerjoin(
        ProductCostHistory, ProductCostHistory.product_id == Product.id
    ).filter(*product_filter).group_by(Product.id).having(
        func.count(ProductCostHistory.id) > 0
    ).order_by(func.count(ProductCostHistory.id).desc()).all()

    # If specific product selected, get its full history
    selected_product = None
    history_entries = []
    if product_id:
        selected_product = Product.query.get(product_id)
        if selected_product:
            history_entries = ProductCostHistory.query.filter_by(
                product_id=product_id
            ).order_by(ProductCostHistory.effective_date.desc()).all()

    # Summary: products with biggest cost increases
    margin_erosion = []
    for p in products_with_history:
        if p.selling_price and p.cost_price:
            current_margin = float((p.selling_price - p.cost_price) / p.selling_price * 100)
            # Get oldest cost in history
            oldest = ProductCostHistory.query.filter_by(
                product_id=p.id
            ).order_by(ProductCostHistory.effective_date.asc()).first()

            if oldest and oldest.landed_cost:
                old_margin = float((p.selling_price - oldest.landed_cost) / p.selling_price * 100)
                margin_change = current_margin - old_margin
                margin_erosion.append({
                    'product_name': p.name,
                    'product_code': p.sku,
                    'old_cost': float(oldest.landed_cost),
                    'current_cost': float(p.cost_price),
                    'selling_price': float(p.selling_price),
                    'old_margin': old_margin,
                    'current_margin': current_margin,
                    'margin_change': margin_change,
                    'change_count': p.change_count
                })

    margin_erosion.sort(key=lambda x: x['margin_change'])  # worst erosion first

    return render_template('financial_reports/cost_history.html',
                         products_with_history=products_with_history,
                         selected_product=selected_product,
                         history_entries=history_entries,
                         margin_erosion=margin_erosion,
                         categories=categories,
                         category_id=category_id,
                         product_id=product_id)


# ============================================================================
# GIFT VOUCHER LIABILITY REPORT
# ============================================================================

@bp.route('/gift-voucher-liability')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def gift_voucher_liability():
    """Gift voucher liability — outstanding balances, redemptions, expired"""
    status_filter = request.args.get('status', '')

    # All vouchers
    query = GiftVoucher.query
    if status_filter:
        query = query.filter(GiftVoucher.status == status_filter)

    vouchers = query.order_by(GiftVoucher.created_at.desc()).all()

    # Summaries
    total_issued = Decimal('0')
    total_redeemed = Decimal('0')
    total_outstanding = Decimal('0')
    total_expired = Decimal('0')
    active_count = 0
    expired_count = 0

    for v in vouchers:
        total_issued += v.initial_value or Decimal('0')
        redeemed = (v.initial_value or Decimal('0')) - (v.current_balance or Decimal('0'))
        total_redeemed += redeemed

        if v.status == 'active':
            total_outstanding += v.current_balance or Decimal('0')
            active_count += 1
        elif v.status == 'expired':
            total_expired += v.current_balance or Decimal('0')
            expired_count += 1

    # Recent transactions
    recent_txns = GiftVoucherTransaction.query.order_by(
        GiftVoucherTransaction.processed_at.desc()
    ).limit(50).all()

    return render_template('financial_reports/gift_voucher_liability.html',
                         vouchers=vouchers,
                         recent_txns=recent_txns,
                         total_issued=float(total_issued),
                         total_redeemed=float(total_redeemed),
                         total_outstanding=float(total_outstanding),
                         total_expired=float(total_expired),
                         active_count=active_count,
                         expired_count=expired_count,
                         status_filter=status_filter)


# ============================================================================
# CONSOLIDATED A/P vs A/R BALANCE SHEET
# ============================================================================

@bp.route('/ap-ar-balance')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def ap_ar_balance():
    """Accounts Payable vs Accounts Receivable balance sheet"""

    # ── ACCOUNTS RECEIVABLE (money owed TO us) ──
    # 1. Customer due payments
    due_payments = DuePayment.query.filter(
        DuePayment.status.in_(['pending', 'partial', 'overdue'])
    ).all()

    total_ar = Decimal('0')
    ar_current = Decimal('0')
    ar_overdue = Decimal('0')
    ar_by_customer = {}

    for dp in due_payments:
        due = dp.due_amount or Decimal('0')
        total_ar += due
        cust_name = dp.customer.name if dp.customer else 'Unknown'

        if dp.is_overdue:
            ar_overdue += due
        else:
            ar_current += due

        if cust_name not in ar_by_customer:
            ar_by_customer[cust_name] = {'current': Decimal('0'), 'overdue': Decimal('0'), 'total': Decimal('0')}
        ar_by_customer[cust_name]['total'] += due
        if dp.is_overdue:
            ar_by_customer[cust_name]['overdue'] += due
        else:
            ar_by_customer[cust_name]['current'] += due

    # 2. Outstanding gift vouchers (liability, not AR — but show for context)
    voucher_liability = db.session.query(
        func.coalesce(func.sum(GiftVoucher.current_balance), 0)
    ).filter(GiftVoucher.status == 'active').scalar() or Decimal('0')

    # ── ACCOUNTS PAYABLE (money WE OWE) ──
    # 1. Supplier balances
    suppliers_with_balance = Supplier.query.filter(
        Supplier.is_active == True,
        Supplier.current_balance > 0
    ).order_by(Supplier.current_balance.desc()).all()

    total_ap = sum(s.current_balance or Decimal('0') for s in suppliers_with_balance)

    # Net position
    net_position = total_ar - total_ap

    # Convert customer dict
    ar_customers = [
        {'name': k, 'current': float(v['current']),
         'overdue': float(v['overdue']), 'total': float(v['total'])}
        for k, v in ar_by_customer.items()
    ]
    ar_customers.sort(key=lambda x: x['total'], reverse=True)

    return render_template('financial_reports/ap_ar_balance.html',
                         total_ar=float(total_ar),
                         ar_current=float(ar_current),
                         ar_overdue=float(ar_overdue),
                         ar_customers=ar_customers,
                         total_ap=float(total_ap),
                         suppliers=suppliers_with_balance,
                         voucher_liability=float(voucher_liability),
                         net_position=float(net_position))


# ============================================================================
# PER-CASHIER EXCEPTION AUDIT REPORT
# ============================================================================

@bp.route('/cashier-audit')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def cashier_audit():
    """Per-cashier exception audit — discounts, voids, refunds per employee"""
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    location_id = request.args.get('location_id', type=int)

    if not from_date:
        from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')

    start_date = datetime.strptime(from_date, '%Y-%m-%d')
    end_date = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)

    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    effective_location_id = None
    if not current_user.is_global_admin:
        if current_user.location_id:
            effective_location_id = current_user.location_id
    elif location_id:
        effective_location_id = location_id

    # Get all cashiers (users)
    cashier_data = {}

    # 1. Total sales per cashier
    sale_filter = [
        Sale.sale_date >= start_date,
        Sale.sale_date < end_date,
        Sale.status == 'completed'
    ]
    if effective_location_id:
        sale_filter.append(Sale.location_id == effective_location_id)

    sales_by_user = db.session.query(
        Sale.user_id,
        func.count(Sale.id).label('sale_count'),
        func.sum(Sale.total).label('total_sales')
    ).filter(*sale_filter).group_by(Sale.user_id).all()

    for row in sales_by_user:
        user = User.query.get(row.user_id)
        if not user:
            continue
        cashier_data[row.user_id] = {
            'user_name': user.full_name or user.username,
            'sale_count': row.sale_count or 0,
            'total_sales': float(row.total_sales or 0),
            'discount_count': 0,
            'discount_total': 0.0,
            'void_count': 0,
            'void_total': 0.0,
            'refund_count': 0,
            'refund_total': 0.0,
            'price_change_count': 0
        }

    # 2. Discounts per cashier
    discount_by_user = db.session.query(
        DiscountLog.user_id,
        func.count(DiscountLog.id).label('count'),
        func.sum(DiscountLog.discount_amount).label('total')
    ).filter(
        DiscountLog.created_at >= start_date,
        DiscountLog.created_at < end_date
    ).group_by(DiscountLog.user_id).all()

    for row in discount_by_user:
        if row.user_id in cashier_data:
            cashier_data[row.user_id]['discount_count'] = row.count or 0
            cashier_data[row.user_id]['discount_total'] = float(row.total or 0)
        else:
            user = User.query.get(row.user_id)
            if user:
                cashier_data[row.user_id] = {
                    'user_name': user.full_name or user.username,
                    'sale_count': 0, 'total_sales': 0.0,
                    'discount_count': row.count or 0,
                    'discount_total': float(row.total or 0),
                    'void_count': 0, 'void_total': 0.0,
                    'refund_count': 0, 'refund_total': 0.0,
                    'price_change_count': 0
                }

    # 3. Voids and refunds per cashier
    void_refund_by_user = db.session.query(
        VoidRefundLog.user_id,
        VoidRefundLog.action_type,
        func.count(VoidRefundLog.id).label('count'),
        func.sum(VoidRefundLog.voided_refunded_amount).label('total')
    ).filter(
        VoidRefundLog.created_at >= start_date,
        VoidRefundLog.created_at < end_date
    ).group_by(VoidRefundLog.user_id, VoidRefundLog.action_type).all()

    for row in void_refund_by_user:
        if row.user_id not in cashier_data:
            user = User.query.get(row.user_id)
            if not user:
                continue
            cashier_data[row.user_id] = {
                'user_name': user.full_name or user.username,
                'sale_count': 0, 'total_sales': 0.0,
                'discount_count': 0, 'discount_total': 0.0,
                'void_count': 0, 'void_total': 0.0,
                'refund_count': 0, 'refund_total': 0.0,
                'price_change_count': 0
            }
        if row.action_type == 'void':
            cashier_data[row.user_id]['void_count'] = row.count or 0
            cashier_data[row.user_id]['void_total'] = float(row.total or 0)
        elif row.action_type in ('refund', 'partial_refund'):
            cashier_data[row.user_id]['refund_count'] += (row.count or 0)
            cashier_data[row.user_id]['refund_total'] += float(row.total or 0)

    # 4. Price changes per cashier
    price_changes_by_user = db.session.query(
        PriceChangeLog.changed_by,
        func.count(PriceChangeLog.id).label('count')
    ).filter(
        PriceChangeLog.changed_at >= start_date,
        PriceChangeLog.changed_at < end_date
    ).group_by(PriceChangeLog.changed_by).all()

    for row in price_changes_by_user:
        if row.changed_by in cashier_data:
            cashier_data[row.changed_by]['price_change_count'] = row.count or 0

    cashier_list = sorted(cashier_data.values(),
                         key=lambda x: x['discount_total'] + x['void_total'] + x['refund_total'],
                         reverse=True)

    return render_template('financial_reports/cashier_audit.html',
                         from_date=from_date,
                         to_date=to_date,
                         cashier_list=cashier_list,
                         locations=locations,
                         selected_location_id=effective_location_id)


# ============================================================================
# PROMOTION ROI REPORT
# ============================================================================

@bp.route('/promotion-roi')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def promotion_roi():
    """Promotion ROI — discount cost vs revenue driven per promotion"""
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    if not from_date:
        from_date = (date.today() - timedelta(days=90)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')

    start_date = datetime.strptime(from_date, '%Y-%m-%d')
    end_date = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)

    # Get all promotions with usage data
    promotions = Promotion.query.order_by(Promotion.created_at.desc()).all()

    promo_data = []
    total_discount_given = Decimal('0')
    total_revenue_driven = Decimal('0')

    for promo in promotions:
        # Get usages in date range
        usages = PromotionUsage.query.filter(
            PromotionUsage.promotion_id == promo.id,
            PromotionUsage.used_at >= start_date,
            PromotionUsage.used_at < end_date
        ).all()

        if not usages:
            continue

        usage_count = len(usages)
        discount_total = sum(float(u.discount_amount or 0) for u in usages)

        # Get revenue from associated sales
        sale_ids = [u.sale_id for u in usages if u.sale_id]
        revenue = Decimal('0')
        if sale_ids:
            revenue = db.session.query(
                func.coalesce(func.sum(Sale.total), 0)
            ).filter(Sale.id.in_(sale_ids)).scalar() or Decimal('0')

        roi = float((revenue - Decimal(str(discount_total))) / Decimal(str(discount_total)) * 100) if discount_total else 0

        promo_data.append({
            'code': promo.code,
            'name': promo.name,
            'type': promo.promotion_type,
            'discount_value': float(promo.discount_value or 0),
            'usage_count': usage_count,
            'usage_limit': promo.usage_limit,
            'discount_total': discount_total,
            'revenue_driven': float(revenue),
            'roi': roi,
            'start_date': promo.start_date,
            'end_date': promo.end_date,
            'is_active': promo.is_active
        })

        total_discount_given += Decimal(str(discount_total))
        total_revenue_driven += revenue

    # Sort by ROI descending
    promo_data.sort(key=lambda x: x['roi'], reverse=True)

    overall_roi = float((total_revenue_driven - total_discount_given) / total_discount_given * 100) if total_discount_given else 0

    return render_template('financial_reports/promotion_roi.html',
                         from_date=from_date,
                         to_date=to_date,
                         promo_data=promo_data,
                         total_discount_given=float(total_discount_given),
                         total_revenue_driven=float(total_revenue_driven),
                         overall_roi=overall_roi)
