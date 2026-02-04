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
                        PriceChangeLog, Customer, User)
from app.models_extended import Expense
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
    """Cash flow report - inflows and outflows"""
    location = get_current_location()

    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    if not from_date:
        from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')

    start_date = datetime.strptime(from_date, '%Y-%m-%d')
    end_date = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)

    location_filter = []
    if location and not current_user.is_global_admin:
        location_filter.append(Sale.location_id == location.id)

    # Cash Inflows
    # 1. Cash Sales
    cash_sales = db.session.query(
        func.sum(Sale.total)
    ).filter(
        Sale.sale_date >= start_date,
        Sale.sale_date < end_date,
        Sale.status == 'completed',
        Sale.payment_method == 'cash',
        *location_filter
    ).scalar() or Decimal('0')

    # 2. Card Sales
    card_sales = db.session.query(
        func.sum(Sale.total)
    ).filter(
        Sale.sale_date >= start_date,
        Sale.sale_date < end_date,
        Sale.status == 'completed',
        Sale.payment_method == 'card',
        *location_filter
    ).scalar() or Decimal('0')

    # 3. Digital Payments (EasyPaisa, JazzCash)
    digital_sales = db.session.query(
        func.sum(Sale.total)
    ).filter(
        Sale.sale_date >= start_date,
        Sale.sale_date < end_date,
        Sale.status == 'completed',
        Sale.payment_method.in_(['easypaisa', 'jazzcash']),
        *location_filter
    ).scalar() or Decimal('0')

    # 4. Bank Transfers
    bank_sales = db.session.query(
        func.sum(Sale.total)
    ).filter(
        Sale.sale_date >= start_date,
        Sale.sale_date < end_date,
        Sale.status == 'completed',
        Sale.payment_method == 'bank_transfer',
        *location_filter
    ).scalar() or Decimal('0')

    total_inflow = cash_sales + card_sales + digital_sales + bank_sales

    # Cash Outflows
    # 1. Expenses
    expense_filter = [
        Expense.expense_date >= start_date.date(),
        Expense.expense_date <= end_date.date()
    ]
    if location and not current_user.is_global_admin:
        expense_filter.append(Expense.location_id == location.id)

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
    if location and not current_user.is_global_admin:
        refund_filter.append(VoidRefundLog.location_id == location.id)

    total_refunds = db.session.query(
        func.sum(VoidRefundLog.voided_refunded_amount)
    ).filter(*refund_filter).scalar() or Decimal('0')

    total_outflow = total_expenses + total_refunds

    # Net Cash Flow
    net_cash_flow = total_inflow - total_outflow

    # Daily breakdown
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
            *location_filter
        ).scalar() or Decimal('0')

        day_expenses = db.session.query(
            func.sum(Expense.amount)
        ).filter(
            Expense.expense_date == current_date,
            *(expense_filter[2:] if len(expense_filter) > 2 else [])
        ).scalar() or Decimal('0')

        daily_data.append({
            'date': current_date,
            'inflow': float(day_sales),
            'outflow': float(day_expenses),
            'net': float(day_sales - day_expenses)
        })

        current_date += timedelta(days=1)

    # Expense breakdown by category
    expense_by_category = db.session.query(
        Expense.category,
        func.sum(Expense.amount).label('total')
    ).filter(*expense_filter).group_by(Expense.category).all()

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
                         total_outflow=total_outflow,
                         net_cash_flow=net_cash_flow,
                         daily_data=daily_data,
                         expense_by_category=expense_by_category,
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
        ).join(SaleItem.sale).join(SaleItem.product).outerjoin(
            Category, Product.category_id == Category.id
        ).filter(*base_filter).group_by(Category.id).all()
    else:
        # Group by product
        results = db.session.query(
            Product.name.label('name'),
            Product.sku.label('sku'),
            func.sum(SaleItem.quantity).label('qty_sold'),
            func.sum(SaleItem.subtotal).label('revenue'),
            func.sum(SaleItem.quantity * Product.cost_price).label('cost')
        ).join(SaleItem.sale).join(SaleItem.product).filter(
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
            'sku': getattr(row, 'sku', None),
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
