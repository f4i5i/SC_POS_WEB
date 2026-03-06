"""
Reports and Analytics Routes
Handles generation and display of various business reports
"""

from flask import Blueprint, render_template, request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_, extract, case
from app.models import db, Sale, SaleItem, Product, Customer, StockMovement, Location, LocationStock, ProductionOrder, RawMaterialStock, RawMaterial, RawMaterialMovement, RawMaterialCategory, PurchaseOrder, PurchaseOrderItem, StockTransfer, StockTransferItem, DayClose, Recipe, Category
from app.utils.helpers import has_permission
from app.utils.permissions import permission_required, Permissions
from app.utils.pdf_utils import generate_daily_report, generate_sales_report
import json

bp = Blueprint('reports', __name__)


@bp.route('/')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def index():
    """Reports dashboard"""
    return render_template('reports/index.html')


@bp.route('/daily')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def daily_report():
    """Daily sales report - filtered by location for non-global admins"""
    from app.models import Location

    # Get date from request or use today
    date_str = request.args.get('date')
    if date_str:
        report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        report_date = datetime.now().date()

    # Location filter support
    location_id = request.args.get('location_id', type=int)
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    # Build query with location filter - include both completed and refunded
    query = Sale.query.filter(
        and_(
            func.date(Sale.sale_date) == report_date,
            Sale.status.in_(['completed', 'refunded'])
        )
    )

    # Filter by location for non-global admins, or by selected location for admins
    user_location = None
    effective_location_id = None
    if not current_user.is_global_admin:
        if current_user.location_id:
            effective_location_id = current_user.location_id
            query = query.filter(Sale.location_id == current_user.location_id)
            user_location = Location.query.get(current_user.location_id)
        else:
            query = query.filter(False)  # No location = no data
    elif location_id:
        effective_location_id = location_id
        query = query.filter(Sale.location_id == location_id)
        user_location = Location.query.get(location_id)

    # Get sales for the day
    all_sales = query.all()

    # Separate completed and refunded sales
    completed_sales = [s for s in all_sales if s.status == 'completed']
    refunded_sales = [s for s in all_sales if s.status == 'refunded']

    # Calculate summary for completed sales
    total_sales = sum(sale.total or 0 for sale in completed_sales)
    total_transactions = len(completed_sales)
    avg_transaction = total_sales / total_transactions if total_transactions > 0 else 0

    # Calculate refund summary
    total_refunds = sum(sale.total or 0 for sale in refunded_sales)
    refund_count = len(refunded_sales)

    # Net sales = total - refunds
    net_sales = total_sales - total_refunds

    # Payment method breakdown (for completed sales only)
    payment_methods = {}
    for sale in completed_sales:
        method = sale.payment_method
        if method not in payment_methods:
            payment_methods[method] = 0
        payment_methods[method] += float(sale.total or 0)

    # Top products - filter by location
    top_products_query = db.session.query(
        Product.name,
        Product.brand,
        func.sum(SaleItem.quantity).label('total_quantity'),
        func.sum(SaleItem.subtotal).label('total_sales')
    ).join(SaleItem).join(Sale).filter(
        func.date(Sale.sale_date) == report_date
    )
    if effective_location_id:
        top_products_query = top_products_query.filter(Sale.location_id == effective_location_id)
    top_products_rows = top_products_query.group_by(Product.id).order_by(func.sum(SaleItem.quantity).desc()).limit(10).all()
    # Convert to serializable list
    top_products = [
        {
            'name': row.name,
            'brand': row.brand,
            'total_quantity': int(row.total_quantity) if row.total_quantity else 0,
            'total_sales': float(row.total_sales) if row.total_sales else 0
        }
        for row in top_products_rows
    ]

    # Hourly sales - filter by location
    hourly_sales_query = db.session.query(
        extract('hour', Sale.sale_date).label('hour'),
        func.count(Sale.id).label('count'),
        func.sum(Sale.total).label('total')
    ).filter(
        func.date(Sale.sale_date) == report_date
    )
    if effective_location_id:
        hourly_sales_query = hourly_sales_query.filter(Sale.location_id == effective_location_id)
    hourly_sales_rows = hourly_sales_query.group_by(extract('hour', Sale.sale_date)).all()
    # Convert to serializable list
    hourly_sales = [
        {
            'hour': int(row.hour) if row.hour else 0,
            'count': int(row.count) if row.count else 0,
            'total': float(row.total) if row.total else 0
        }
        for row in hourly_sales_rows
    ]

    # Low stock alerts - use LocationStock for per-location data
    from app.models import LocationStock
    if effective_location_id:
        # Get low stock for this location
        location_stock = LocationStock.query.filter(
            LocationStock.location_id == effective_location_id,
            LocationStock.quantity <= LocationStock.reorder_level,
            LocationStock.quantity > 0
        ).all()
        low_stock = [ls.product for ls in location_stock if ls.product]
        out_of_stock_ls = LocationStock.query.filter(
            LocationStock.location_id == effective_location_id,
            LocationStock.quantity == 0
        ).all()
        out_of_stock = [ls.product for ls in out_of_stock_ls if ls.product]
    else:
        low_stock = Product.query.filter(Product.quantity <= Product.reorder_level).all()
        out_of_stock = Product.query.filter(Product.quantity == 0).all()

    return render_template('reports/daily_report.html',
                         report_date=report_date,
                         sales=all_sales,
                         completed_sales=completed_sales,
                         refunded_sales=refunded_sales,
                         total_sales=total_sales,
                         total_refunds=total_refunds,
                         refund_count=refund_count,
                         net_sales=net_sales,
                         total_transactions=total_transactions,
                         avg_transaction=avg_transaction,
                         payment_methods=payment_methods,
                         top_products=top_products,
                         hourly_sales=hourly_sales,
                         low_stock=low_stock,
                         out_of_stock=out_of_stock,
                         user_location=user_location,
                         locations=locations,
                         selected_location_id=location_id)


@bp.route('/weekly')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def weekly_report():
    """Weekly sales comparison report - filtered by location"""
    from app.models import Location

    # Location filter support
    location_id = request.args.get('location_id', type=int)
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    # Get week ending date
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=7)

    # Build base query with location filter
    current_query = Sale.query.filter(
        and_(
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
            Sale.status == 'completed'
        )
    )

    # Filter by location for non-global admins, or by selected location for admins
    user_location = None
    effective_location_id = None
    if not current_user.is_global_admin:
        if current_user.location_id:
            effective_location_id = current_user.location_id
            current_query = current_query.filter(Sale.location_id == current_user.location_id)
            user_location = Location.query.get(current_user.location_id)
        else:
            current_query = current_query.filter(False)
    elif location_id:
        effective_location_id = location_id
        current_query = current_query.filter(Sale.location_id == location_id)
        user_location = Location.query.get(location_id)

    current_week_sales = current_query.all()

    # Sales for previous week
    prev_end_date = start_date - timedelta(days=1)
    prev_start_date = prev_end_date - timedelta(days=7)
    prev_query = Sale.query.filter(
        and_(
            Sale.sale_date >= prev_start_date,
            Sale.sale_date <= prev_end_date,
            Sale.status == 'completed'
        )
    )
    if effective_location_id:
        prev_query = prev_query.filter(Sale.location_id == effective_location_id)
    previous_week_sales = prev_query.all()

    # Calculate metrics
    current_total = sum(sale.total for sale in current_week_sales)
    previous_total = sum(sale.total for sale in previous_week_sales)

    change_percent = 0
    if previous_total > 0:
        change_percent = ((current_total - previous_total) / previous_total) * 100

    # Daily breakdown with location filter
    daily_query = db.session.query(
        func.date(Sale.sale_date).label('date'),
        func.count(Sale.id).label('count'),
        func.sum(Sale.total).label('total')
    ).filter(
        and_(
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
            Sale.status == 'completed'
        )
    )
    if effective_location_id:
        daily_query = daily_query.filter(Sale.location_id == effective_location_id)
    daily_sales_raw = daily_query.group_by(func.date(Sale.sale_date)).all()

    # Convert to list of dicts with proper date objects
    daily_sales = []
    for row in daily_sales_raw:
        # Handle both string and date objects from different DB drivers
        if isinstance(row.date, str):
            from datetime import datetime as dt
            date_obj = dt.strptime(row.date, '%Y-%m-%d').date()
        else:
            date_obj = row.date
        daily_sales.append({
            'date': date_obj,
            'count': row.count or 0,
            'total': float(row.total or 0)
        })

    return render_template('reports/weekly_report.html',
                         start_date=start_date,
                         end_date=end_date,
                         current_total=current_total,
                         previous_total=previous_total,
                         change_percent=change_percent,
                         daily_sales=daily_sales,
                         user_location=user_location,
                         locations=locations,
                         selected_location_id=location_id)


@bp.route('/monthly')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def monthly_report():
    """Monthly comprehensive report - filtered by location"""
    from app.models import Location

    # Location filter support
    location_id = request.args.get('location_id', type=int)
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    # Get month from request or use current month
    month_str = request.args.get('month')
    if month_str:
        report_date = datetime.strptime(month_str, '%Y-%m')
    else:
        report_date = datetime.now()

    year = report_date.year
    month = report_date.month

    # Build base query with location filter
    query = Sale.query.filter(
        and_(
            extract('year', Sale.sale_date) == year,
            extract('month', Sale.sale_date) == month,
            Sale.status == 'completed'
        )
    )

    # Filter by location
    user_location = None
    effective_location_id = None
    if not current_user.is_global_admin:
        if current_user.location_id:
            effective_location_id = current_user.location_id
            query = query.filter(Sale.location_id == current_user.location_id)
            user_location = Location.query.get(current_user.location_id)
        else:
            query = query.filter(False)
    elif location_id:
        effective_location_id = location_id
        query = query.filter(Sale.location_id == location_id)
        user_location = Location.query.get(location_id)

    sales = query.all()

    # Calculate totals
    total_revenue = sum(sale.total for sale in sales)
    total_transactions = len(sales)

    # Sales by category - with location filter
    category_query = db.session.query(
        db.func.coalesce(db.text("categories.name"), 'Uncategorized').label('category'),
        func.sum(SaleItem.subtotal).label('total')
    ).select_from(SaleItem).join(Sale).join(Product)\
    .outerjoin(Product.category).filter(
        and_(
            extract('year', Sale.sale_date) == year,
            extract('month', Sale.sale_date) == month,
            Sale.status == 'completed'
        )
    )
    if effective_location_id:
        category_query = category_query.filter(Sale.location_id == effective_location_id)
    category_sales_rows = category_query.group_by('category').all()
    # Convert to serializable format
    category_sales = [
        {'category': row.category or 'Uncategorized', 'total': float(row.total or 0)}
        for row in category_sales_rows
    ]

    # Top customers - with location filter
    customers_query = db.session.query(
        Customer.name,
        func.count(Sale.id).label('transactions'),
        func.sum(Sale.total).label('total')
    ).join(Sale).filter(
        and_(
            extract('year', Sale.sale_date) == year,
            extract('month', Sale.sale_date) == month,
            Sale.status == 'completed'
        )
    )
    if effective_location_id:
        customers_query = customers_query.filter(Sale.location_id == effective_location_id)
    top_customers_rows = customers_query.group_by(Customer.id).order_by(func.sum(Sale.total).desc()).limit(10).all()
    # Convert to serializable format
    top_customers = [
        {'name': row.name or 'Unknown', 'transactions': int(row.transactions or 0), 'total': float(row.total or 0)}
        for row in top_customers_rows
    ]

    return render_template('reports/monthly_report.html',
                         year=year,
                         month=month,
                         total_revenue=total_revenue,
                         total_transactions=total_transactions,
                         category_sales=category_sales,
                         top_customers=top_customers,
                         user_location=user_location,
                         locations=locations,
                         selected_location_id=location_id)


@bp.route('/custom')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def custom_report():
    """Custom date range report - filtered by location"""
    from app.models import Location

    # Location filter support
    location_id = request.args.get('location_id', type=int)
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    # Get user location for display
    user_location = None
    effective_location_id = None
    if not current_user.is_global_admin and current_user.location_id:
        effective_location_id = current_user.location_id
        user_location = Location.query.get(current_user.location_id)
    elif current_user.is_global_admin and location_id:
        effective_location_id = location_id
        user_location = Location.query.get(location_id)

    if from_date and to_date:
        from_dt = datetime.strptime(from_date, '%Y-%m-%d')
        to_dt = datetime.strptime(to_date, '%Y-%m-%d')

        # Build query with location filter
        query = Sale.query.filter(
            and_(
                Sale.sale_date >= from_dt,
                Sale.sale_date <= to_dt,
                Sale.status == 'completed'
            )
        )
        if not current_user.is_global_admin:
            if current_user.location_id:
                query = query.filter(Sale.location_id == current_user.location_id)
            else:
                query = query.filter(False)
        elif effective_location_id:
            query = query.filter(Sale.location_id == effective_location_id)

        sales = query.all()

        total_sales = sum(sale.total for sale in sales)
        total_transactions = len(sales)

        # Product performance - with location filter
        product_query = db.session.query(
            Product.name,
            Product.brand,
            func.sum(SaleItem.quantity).label('quantity'),
            func.sum(SaleItem.subtotal).label('revenue'),
            func.sum((SaleItem.unit_price - Product.cost_price) * SaleItem.quantity).label('profit')
        ).join(SaleItem).join(Sale).filter(
            and_(
                Sale.sale_date >= from_dt,
                Sale.sale_date <= to_dt,
                Sale.status == 'completed'
            )
        )
        if effective_location_id:
            product_query = product_query.filter(Sale.location_id == effective_location_id)
        product_performance = product_query.group_by(Product.id).order_by(func.sum(SaleItem.subtotal).desc()).all()

        return render_template('reports/custom_report.html',
                             from_date=from_date,
                             to_date=to_date,
                             total_sales=total_sales,
                             total_transactions=total_transactions,
                             product_performance=product_performance,
                             user_location=user_location,
                             locations=locations,
                             selected_location_id=location_id)

    return render_template('reports/custom_report.html',
                         user_location=user_location,
                         locations=locations,
                         selected_location_id=location_id)


@bp.route('/inventory-valuation')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def inventory_valuation():
    """Stock valuation report with cost breakdown"""
    from app.models import Category
    from app.utils.location_context import get_current_location

    user_location = get_current_location()
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    categories = Category.query.order_by(Category.name).all()

    # Filters
    location_id = request.args.get('location_id', type=int)
    category_id = request.args.get('category_id', type=int)
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'name_asc')
    stock_filter = request.args.get('stock_filter', '')

    if current_user.is_global_admin:
        effective_location_id = location_id
    elif user_location:
        effective_location_id = user_location.id
    else:
        effective_location_id = None

    product_query = Product.query.filter_by(is_active=True)
    if category_id:
        product_query = product_query.filter_by(category_id=category_id)
    if search:
        product_query = product_query.filter(
            db.or_(Product.name.ilike(f'%{search}%'), Product.code.ilike(f'%{search}%'))
        )
    products = product_query.all()

    # Build product data with cost breakdown
    product_data = []
    total_base_value = 0
    total_packaging_value = 0
    total_delivery_value = 0
    total_bottle_value = 0
    total_kiosk_value = 0
    total_cost_value = 0
    total_selling_value = 0

    for p in products:
        # Use location-specific stock if location selected
        if effective_location_id:
            ls = LocationStock.query.filter_by(product_id=p.id, location_id=effective_location_id).first()
            qty = float(ls.quantity if ls else 0)
        else:
            qty = float(p.quantity or 0)
        base_cost = float(p.base_cost or 0)
        packaging_cost = float(p.packaging_cost or 0)
        delivery_cost = float(p.delivery_cost or 0)
        bottle_cost = float(p.bottle_cost or 0)
        kiosk_cost = float(p.kiosk_cost or 0)
        total_cost = base_cost + packaging_cost + delivery_cost + bottle_cost + kiosk_cost
        selling_price = float(p.selling_price or 0)

        # Calculate values
        base_value = qty * base_cost
        packaging_value = qty * packaging_cost
        delivery_value = qty * delivery_cost
        bottle_value = qty * bottle_cost
        kiosk_value = qty * kiosk_cost
        cost_value = qty * total_cost
        sell_value = qty * selling_price

        product_data.append({
            'product': p,
            'quantity': p.quantity,
            # Per unit costs
            'base_cost': base_cost,
            'packaging_cost': packaging_cost,
            'delivery_cost': delivery_cost,
            'bottle_cost': bottle_cost,
            'kiosk_cost': kiosk_cost,
            'total_cost': total_cost,
            'selling_price': selling_price,
            # Total values
            'base_value': base_value,
            'packaging_value': packaging_value,
            'delivery_value': delivery_value,
            'bottle_value': bottle_value,
            'kiosk_value': kiosk_value,
            'cost_value': cost_value,
            'selling_value': sell_value,
            'profit': sell_value - cost_value
        })

        # Accumulate totals
        total_base_value += base_value
        total_packaging_value += packaging_value
        total_delivery_value += delivery_value
        total_bottle_value += bottle_value
        total_kiosk_value += kiosk_value
        total_cost_value += cost_value
        total_selling_value += sell_value

    potential_profit = total_selling_value - total_cost_value

    # Apply stock filter
    if stock_filter == 'in_stock':
        product_data = [d for d in product_data if d['quantity'] and d['quantity'] > 0]
    elif stock_filter == 'out_of_stock':
        product_data = [d for d in product_data if not d['quantity'] or d['quantity'] == 0]

    # Sort
    val_sort_options = {
        'name_asc': lambda x: x['product'].name.lower(),
        'name_desc': lambda x: x['product'].name.lower(),
        'cost_value_desc': lambda x: -x['cost_value'],
        'cost_value_asc': lambda x: x['cost_value'],
        'selling_value_desc': lambda x: -x['selling_value'],
        'profit_desc': lambda x: -x['profit'],
        'profit_asc': lambda x: x['profit'],
        'quantity_desc': lambda x: -(x['quantity'] or 0),
        'quantity_asc': lambda x: (x['quantity'] or 0),
    }
    sort_fn = val_sort_options.get(sort_by, val_sort_options['name_asc'])
    product_data.sort(key=sort_fn, reverse=(sort_by == 'name_desc'))

    return render_template('reports/inventory_valuation.html',
                         products=products,
                         product_data=product_data,
                         total_base_value=total_base_value,
                         total_packaging_value=total_packaging_value,
                         total_delivery_value=total_delivery_value,
                         total_bottle_value=total_bottle_value,
                         total_kiosk_value=total_kiosk_value,
                         total_cost_value=total_cost_value,
                         total_selling_value=total_selling_value,
                         potential_profit=potential_profit,
                         locations=locations,
                         categories=categories,
                         selected_location_id=location_id,
                         selected_category_id=category_id,
                         user_location=user_location,
                         search=search,
                         sort_by=sort_by,
                         stock_filter=stock_filter)


@bp.route('/export-daily-pdf')
@login_required
@permission_required(Permissions.REPORT_EXPORT)
def export_daily_pdf():
    """Export daily report as PDF"""
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    pdf_path = generate_daily_report(date_str)
    return send_file(pdf_path, as_attachment=True)


@bp.route('/employee-performance')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def employee_performance():
    """Employee performance and sales report - filtered by location"""
    from app.models import User, Location

    # Location filter support
    location_id = request.args.get('location_id', type=int)
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    sort_by = request.args.get('sort_by', 'revenue_desc')
    search = request.args.get('search', '').strip()

    # Get date range from request or default to current month
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    else:
        # Default to current month
        today = datetime.now()
        start_date = today.replace(day=1)
        end_date = today

    # Get user location for display
    user_location = None
    effective_location_id = None
    if not current_user.is_global_admin and current_user.location_id:
        effective_location_id = current_user.location_id
        user_location = Location.query.get(current_user.location_id)
    elif current_user.is_global_admin and location_id:
        effective_location_id = location_id
        user_location = Location.query.get(location_id)

    # Employee sales performance
    # Subquery to count items per sale
    items_subquery = db.session.query(
        SaleItem.sale_id,
        func.sum(SaleItem.quantity).label('item_count')
    ).group_by(SaleItem.sale_id).subquery()

    # Build base query
    base_filter = and_(
        Sale.sale_date >= start_date,
        Sale.sale_date <= end_date,
        Sale.status == 'completed'
    )

    # Add location filter
    if effective_location_id:
        base_filter = and_(base_filter, Sale.location_id == effective_location_id)

    employee_stats = db.session.query(
        User.full_name,
        User.username,
        func.count(Sale.id).label('total_sales'),
        func.sum(Sale.total).label('total_revenue'),
        func.avg(Sale.total).label('avg_sale'),
        func.coalesce(func.sum(items_subquery.c.item_count), 0).label('items_sold')
    ).join(Sale, Sale.user_id == User.id).outerjoin(
        items_subquery, items_subquery.c.sale_id == Sale.id
    ).filter(base_filter).group_by(User.id).order_by(func.sum(Sale.total).desc()).all()

    # Calculate totals
    total_revenue = float(sum(emp.total_revenue or 0 for emp in employee_stats))
    total_sales_count = sum(emp.total_sales or 0 for emp in employee_stats)

    # Convert Row objects to dicts for tojson serialization in template
    employee_stats_serializable = [
        {
            'full_name': emp.full_name or emp.username,
            'username': emp.username,
            'total_sales': emp.total_sales or 0,
            'total_revenue': float(emp.total_revenue or 0),
            'avg_sale': float(emp.avg_sale or 0),
            'items_sold': int(emp.items_sold or 0)
        }
        for emp in employee_stats
    ]

    # Apply search filter
    if search:
        employee_stats_serializable = [e for e in employee_stats_serializable
                                       if search.lower() in e['full_name'].lower()]

    # Apply sorting
    emp_sort_options = {
        'revenue_desc': lambda x: -x['total_revenue'],
        'revenue_asc': lambda x: x['total_revenue'],
        'sales_count_desc': lambda x: -x['total_sales'],
        'name_asc': lambda x: x['full_name'].lower(),
    }
    sort_fn = emp_sort_options.get(sort_by, emp_sort_options['revenue_desc'])
    employee_stats_serializable.sort(key=sort_fn)

    return render_template('reports/employee_performance.html',
                         start_date=start_date,
                         end_date=end_date,
                         employee_stats=employee_stats_serializable,
                         total_revenue=total_revenue,
                         total_sales_count=total_sales_count,
                         user_location=user_location,
                         locations=locations,
                         selected_location_id=location_id,
                         sort_by=sort_by,
                         search=search)


@bp.route('/product-performance')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def product_performance():
    """Product performance analysis - filtered by location"""
    from app.models import Location, Category

    # Location filter support
    location_id = request.args.get('location_id', type=int)
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    sort_by = request.args.get('sort_by', 'revenue_desc')
    search = request.args.get('search', '').strip()
    category_id = request.args.get('category_id', type=int)

    # Get categories for filter
    categories = Category.query.order_by(Category.name).all()

    # Get date range
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    else:
        # Default to last 30 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

    # Get user location for display
    user_location = None
    effective_location_id = None
    if not current_user.is_global_admin and current_user.location_id:
        effective_location_id = current_user.location_id
        user_location = Location.query.get(current_user.location_id)
    elif current_user.is_global_admin and location_id:
        effective_location_id = location_id
        user_location = Location.query.get(location_id)

    # Build base filter
    base_filter = and_(
        Sale.sale_date >= start_date,
        Sale.sale_date <= end_date,
        Sale.status == 'completed'
    )
    # Add location filter
    if effective_location_id:
        base_filter = and_(base_filter, Sale.location_id == effective_location_id)

    # Add category filter to base
    product_filter = base_filter
    if category_id:
        product_filter = and_(product_filter, Product.category_id == category_id)

    # Top performing products
    top_products_query = db.session.query(
        Product.name,
        Product.code,
        Product.brand,
        func.sum(SaleItem.quantity).label('units_sold'),
        func.sum(SaleItem.subtotal).label('revenue'),
        func.sum((SaleItem.unit_price - Product.cost_price) * SaleItem.quantity).label('profit'),
        func.count(func.distinct(Sale.id)).label('transactions')
    ).select_from(Product).join(
        SaleItem, SaleItem.product_id == Product.id
    ).join(
        Sale, Sale.id == SaleItem.sale_id
    ).filter(product_filter).group_by(Product.id).order_by(func.sum(SaleItem.subtotal).desc()).limit(20).all()

    # Convert to dicts for filtering/sorting
    top_products = [
        {'name': p.name, 'code': p.code, 'brand': p.brand,
         'units_sold': int(p.units_sold or 0), 'revenue': float(p.revenue or 0),
         'profit': float(p.profit or 0), 'transactions': int(p.transactions or 0)}
        for p in top_products_query
    ]

    # Worst performing products (sold but low revenue)
    worst_products_query = db.session.query(
        Product.name,
        Product.code,
        Product.brand,
        func.sum(SaleItem.quantity).label('units_sold'),
        func.sum(SaleItem.subtotal).label('revenue')
    ).select_from(Product).join(
        SaleItem, SaleItem.product_id == Product.id
    ).join(
        Sale, Sale.id == SaleItem.sale_id
    ).filter(product_filter).group_by(Product.id).order_by(func.sum(SaleItem.subtotal).asc()).limit(10).all()

    worst_products = [
        {'name': p.name, 'code': p.code, 'brand': p.brand,
         'units_sold': int(p.units_sold or 0), 'revenue': float(p.revenue or 0)}
        for p in worst_products_query
    ]

    # Never sold products - also filter by location
    sold_product_ids = db.session.query(func.distinct(SaleItem.product_id)).join(Sale).filter(
        base_filter
    )

    never_sold_query = Product.query.filter(
        ~Product.id.in_(sold_product_ids.subquery().select()),
        Product.is_active == True
    )
    if category_id:
        never_sold_query = never_sold_query.filter_by(category_id=category_id)
    never_sold = never_sold_query.limit(20).all()

    # Apply search filter
    if search:
        search_lower = search.lower()
        top_products = [p for p in top_products if search_lower in p['name'].lower() or search_lower in (p['code'] or '').lower()]
        worst_products = [p for p in worst_products if search_lower in p['name'].lower() or search_lower in (p['code'] or '').lower()]
        never_sold = [p for p in never_sold if search_lower in p.name.lower() or search_lower in (p.code or '').lower()]

    # Apply sorting to top_products
    prod_sort_options = {
        'quantity_desc': lambda x: -x['units_sold'],
        'revenue_desc': lambda x: -x['revenue'],
        'name_asc': lambda x: x['name'].lower(),
    }
    sort_fn = prod_sort_options.get(sort_by, prod_sort_options['revenue_desc'])
    top_products.sort(key=sort_fn)

    return render_template('reports/product_performance.html',
                         start_date=start_date,
                         end_date=end_date,
                         top_products=top_products,
                         worst_products=worst_products,
                         never_sold=never_sold,
                         user_location=user_location,
                         locations=locations,
                         selected_location_id=location_id,
                         categories=categories,
                         selected_category_id=category_id,
                         sort_by=sort_by,
                         search=search)


@bp.route('/sales-by-category')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def sales_by_category():
    """Sales breakdown by product category - filtered by location"""
    from app.models import Category, Location

    # Location filter support
    location_id = request.args.get('location_id', type=int)
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    # Get date range
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    else:
        # Default to current month
        today = datetime.now()
        start_date = today.replace(day=1)
        end_date = today

    # Get user location for display
    user_location = None
    effective_location_id = None
    if not current_user.is_global_admin and current_user.location_id:
        effective_location_id = current_user.location_id
        user_location = Location.query.get(current_user.location_id)
    elif current_user.is_global_admin and location_id:
        effective_location_id = location_id
        user_location = Location.query.get(location_id)

    # Build base filter
    base_filter = and_(
        Sale.sale_date >= start_date,
        Sale.sale_date <= end_date,
        Sale.status == 'completed'
    )
    # Add location filter
    if effective_location_id:
        base_filter = and_(base_filter, Sale.location_id == effective_location_id)

    # Sales by category
    category_sales_rows = db.session.query(
        func.coalesce(Category.name, 'Uncategorized').label('category'),
        func.sum(SaleItem.quantity).label('units_sold'),
        func.sum(SaleItem.subtotal).label('revenue'),
        func.count(func.distinct(Sale.id)).label('transactions'),
        func.sum((SaleItem.unit_price - Product.cost_price) * SaleItem.quantity).label('profit')
    ).select_from(SaleItem).join(Sale).join(Product).outerjoin(Category).filter(
        base_filter
    ).group_by('category').order_by(func.sum(SaleItem.subtotal).desc()).all()

    # Convert to serializable format
    category_sales = [
        {
            'category': row.category or 'Uncategorized',
            'units_sold': int(row.units_sold or 0),
            'revenue': float(row.revenue or 0),
            'transactions': int(row.transactions or 0),
            'profit': float(row.profit or 0)
        }
        for row in category_sales_rows
    ]

    # Calculate totals
    total_revenue = sum(cat['revenue'] for cat in category_sales)
    total_profit = sum(cat['profit'] for cat in category_sales)
    total_units = sum(cat['units_sold'] for cat in category_sales)

    return render_template('reports/sales_by_category.html',
                         start_date=start_date,
                         end_date=end_date,
                         category_sales=category_sales,
                         total_revenue=total_revenue,
                         total_profit=total_profit,
                         total_units=total_units,
                         user_location=user_location,
                         locations=locations,
                         selected_location_id=location_id)


@bp.route('/profit-loss')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def profit_loss():
    """Profit and Loss (P&L) statement with daily/weekly/monthly presets"""
    from app.models import Location, Category
    from calendar import monthrange

    # Location filter support
    location_id = request.args.get('location_id', type=int)
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    # Get period type: daily, weekly, monthly, custom
    period = request.args.get('period', 'daily')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    today = datetime.now()

    # Determine date range based on period
    if period == 'daily':
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        else:
            start_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date.replace(hour=23, minute=59, second=59)
        period_label = start_date.strftime('%B %d, %Y')
    elif period == 'weekly':
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        else:
            start_date = today - timedelta(days=today.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=6)
        end_date = end_date.replace(hour=23, minute=59, second=59)
        period_label = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
    elif period == 'monthly':
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        else:
            start_date = today.replace(day=1)
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        _, last_day = monthrange(start_date.year, start_date.month)
        end_date = start_date.replace(day=last_day, hour=23, minute=59, second=59)
        period_label = start_date.strftime('%B %Y')
    else:  # custom
        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            end_date = end_date.replace(hour=23, minute=59, second=59)
        else:
            start_date = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = today.replace(hour=23, minute=59, second=59)
        period_label = f"{start_date.strftime('%b %d, %Y')} - {end_date.strftime('%b %d, %Y')}"

    # Get user location for filtering
    user_location = None
    effective_location_id = None
    location_filter = True  # Default: no filter
    if not current_user.is_global_admin:
        if current_user.location_id:
            effective_location_id = current_user.location_id
            location_filter = Sale.location_id == current_user.location_id
            user_location = Location.query.get(current_user.location_id)
        else:
            location_filter = False
    elif location_id:
        effective_location_id = location_id
        location_filter = Sale.location_id == location_id
        user_location = Location.query.get(location_id)

    # ===== REVENUE SECTION =====
    sales = Sale.query.filter(
        and_(
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
            Sale.status == 'completed',
            location_filter
        )
    ).all()

    gross_revenue = sum(float(sale.subtotal or 0) for sale in sales)
    total_discounts = sum(float(sale.discount or 0) for sale in sales)
    net_revenue = sum(float(sale.total or 0) for sale in sales)
    total_transactions = len(sales)

    # ===== COST OF GOODS SOLD =====
    cogs_query = db.session.query(
        func.sum(Product.cost_price * SaleItem.quantity)
    ).join(SaleItem).join(Sale).filter(
        and_(
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
            Sale.status == 'completed'
        )
    )
    if effective_location_id:
        cogs_query = cogs_query.filter(Sale.location_id == effective_location_id)
    elif not current_user.is_global_admin and not current_user.location_id:
        cogs_query = cogs_query.filter(False)
    cogs = float(cogs_query.scalar() or 0)

    # ===== COGS BREAKDOWN BY COST COMPONENT =====
    cogs_detail_query = db.session.query(
        func.sum(func.coalesce(Product.base_cost, 0) * SaleItem.quantity).label('base_cost'),
        func.sum(func.coalesce(Product.packaging_cost, 0) * SaleItem.quantity).label('packaging_cost'),
        func.sum(func.coalesce(Product.delivery_cost, 0) * SaleItem.quantity).label('delivery_cost'),
        func.sum(func.coalesce(Product.bottle_cost, 0) * SaleItem.quantity).label('bottle_cost'),
        func.sum(func.coalesce(Product.kiosk_cost, 0) * SaleItem.quantity).label('kiosk_cost'),
        func.sum(SaleItem.quantity).label('total_units')
    ).select_from(SaleItem).join(Sale).join(Product).filter(
        and_(
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
            Sale.status == 'completed'
        )
    )
    if effective_location_id:
        cogs_detail_query = cogs_detail_query.filter(Sale.location_id == effective_location_id)
    elif not current_user.is_global_admin and not current_user.location_id:
        cogs_detail_query = cogs_detail_query.filter(False)
    cogs_row = cogs_detail_query.first()
    cogs_breakdown = {
        'base_cost': float(cogs_row.base_cost or 0) if cogs_row else 0,
        'packaging_cost': float(cogs_row.packaging_cost or 0) if cogs_row else 0,
        'delivery_cost': float(cogs_row.delivery_cost or 0) if cogs_row else 0,
        'bottle_cost': float(cogs_row.bottle_cost or 0) if cogs_row else 0,
        'kiosk_cost': float(cogs_row.kiosk_cost or 0) if cogs_row else 0,
        'total_units': int(cogs_row.total_units or 0) if cogs_row else 0
    }

    # ===== GROSS PROFIT =====
    # Exclude kiosk_cost from COGS (it's rent recovery built into pricing,
    # actual rent is tracked in Operating Expenses to avoid double-counting)
    direct_cogs = cogs - cogs_breakdown.get('kiosk_cost', 0)
    gross_profit = net_revenue - direct_cogs
    gross_margin = (gross_profit / net_revenue * 100) if net_revenue > 0 else 0

    # ===== GROWTH SHARE (20% of Gross Profit) =====
    growth_share_percent = 20
    growth_share = (gross_profit * growth_share_percent / 100) if gross_profit > 0 else 0
    profit_after_growth_share = gross_profit - growth_share

    # ===== EXPENSES SECTION =====
    try:
        from app.models_extended import Expense, ExpenseCategory
        expense_query = Expense.query.filter(
            and_(
                Expense.expense_date >= start_date.date(),
                Expense.expense_date <= end_date.date()
            )
        )
        if effective_location_id:
            expense_query = expense_query.filter(Expense.location_id == effective_location_id)
        elif not current_user.is_global_admin and not current_user.location_id:
            expense_query = expense_query.filter(False)

        expenses = expense_query.all()
        total_expenses = sum(float(exp.amount or 0) for exp in expenses)

        # Expenses by category
        expense_by_cat_query = db.session.query(
            ExpenseCategory.name,
            ExpenseCategory.icon,
            ExpenseCategory.color,
            func.sum(Expense.amount).label('total')
        ).join(Expense).filter(
            and_(
                Expense.expense_date >= start_date.date(),
                Expense.expense_date <= end_date.date()
            )
        )
        if effective_location_id:
            expense_by_cat_query = expense_by_cat_query.filter(Expense.location_id == effective_location_id)
        elif not current_user.is_global_admin and not current_user.location_id:
            expense_by_cat_query = expense_by_cat_query.filter(False)
        expense_by_category = expense_by_cat_query.group_by(ExpenseCategory.id).all()
    except:
        expenses = []
        total_expenses = 0
        expense_by_category = []

    # ===== NET PROFIT =====
    net_profit = profit_after_growth_share - total_expenses
    net_margin = (net_profit / net_revenue * 100) if net_revenue > 0 else 0

    # ===== PAYMENT METHOD BREAKDOWN =====
    payment_breakdown = {}
    for sale in sales:
        method = sale.payment_method or 'cash'
        if method not in payment_breakdown:
            payment_breakdown[method] = {'count': 0, 'total': 0}
        payment_breakdown[method]['count'] += 1
        payment_breakdown[method]['total'] += float(sale.total or 0)

    # ===== DAILY BREAKDOWN (for charts) =====
    daily_data = {}
    for sale in sales:
        day_key = sale.sale_date.strftime('%Y-%m-%d')
        if day_key not in daily_data:
            daily_data[day_key] = {'revenue': 0, 'transactions': 0}
        daily_data[day_key]['revenue'] += float(sale.total or 0)
        daily_data[day_key]['transactions'] += 1

    # ===== TOP PRODUCTS BY PROFIT =====
    top_products_query = db.session.query(
        Product.name,
        Product.code,
        func.sum(SaleItem.quantity).label('qty_sold'),
        func.sum(SaleItem.subtotal).label('revenue'),
        func.sum((SaleItem.unit_price - Product.cost_price) * SaleItem.quantity).label('profit')
    ).join(SaleItem).join(Sale).filter(
        and_(
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
            Sale.status == 'completed'
        )
    )
    if effective_location_id:
        top_products_query = top_products_query.filter(Sale.location_id == effective_location_id)
    top_products = top_products_query.group_by(Product.id).order_by(
        func.sum((SaleItem.unit_price - Product.cost_price) * SaleItem.quantity).desc()
    ).limit(10).all()

    # ===== CATEGORY BREAKDOWN =====
    category_breakdown = []
    try:
        cat_query = db.session.query(
            func.coalesce(Category.name, 'Uncategorized').label('category'),
            func.sum(SaleItem.subtotal).label('revenue'),
            func.sum(Product.cost_price * SaleItem.quantity).label('cogs'),
            func.sum((SaleItem.unit_price - Product.cost_price) * SaleItem.quantity).label('profit'),
            func.sum(SaleItem.quantity).label('units_sold')
        ).select_from(SaleItem).join(Sale).join(Product).outerjoin(Category).filter(
            and_(
                Sale.sale_date >= start_date,
                Sale.sale_date <= end_date,
                Sale.status == 'completed'
            )
        )
        if effective_location_id:
            cat_query = cat_query.filter(Sale.location_id == effective_location_id)
        elif not current_user.is_global_admin and not current_user.location_id:
            cat_query = cat_query.filter(False)
        cat_rows = cat_query.group_by('category').order_by(func.sum(SaleItem.subtotal).desc()).all()
        for row in cat_rows:
            rev = float(row.revenue or 0)
            cost = float(row.cogs or 0)
            profit = float(row.profit or 0)
            category_breakdown.append({
                'category': row.category or 'Uncategorized',
                'revenue': rev,
                'cogs': cost,
                'gross_profit': profit,
                'margin': (profit / rev * 100) if rev > 0 else 0,
                'units_sold': int(row.units_sold or 0)
            })
    except:
        category_breakdown = []

    # ===== COMPARISON WITH PREVIOUS PERIOD (full metrics) =====
    period_duration = (end_date - start_date).days + 1
    prev_start = start_date - timedelta(days=period_duration)
    prev_end = start_date - timedelta(seconds=1)

    prev_sale_filter = and_(
        Sale.sale_date >= prev_start,
        Sale.sale_date <= prev_end,
        Sale.status == 'completed'
    )

    prev_query = Sale.query.filter(prev_sale_filter)
    if effective_location_id:
        prev_query = prev_query.filter(Sale.location_id == effective_location_id)
    elif not current_user.is_global_admin and current_user.location_id:
        prev_query = prev_query.filter(Sale.location_id == current_user.location_id)
    prev_sales = prev_query.all()
    prev_revenue = sum(float(s.total or 0) for s in prev_sales)
    prev_gross_revenue = sum(float(s.subtotal or 0) for s in prev_sales)
    prev_discounts = sum(float(s.discount or 0) for s in prev_sales)
    prev_transactions = len(prev_sales)

    # Previous COGS
    prev_cogs_query = db.session.query(
        func.sum(Product.cost_price * SaleItem.quantity)
    ).join(SaleItem).join(Sale).filter(prev_sale_filter)
    if effective_location_id:
        prev_cogs_query = prev_cogs_query.filter(Sale.location_id == effective_location_id)
    elif not current_user.is_global_admin and current_user.location_id:
        prev_cogs_query = prev_cogs_query.filter(Sale.location_id == current_user.location_id)
    prev_cogs = float(prev_cogs_query.scalar() or 0)
    prev_gross_profit = prev_revenue - prev_cogs

    # Previous expenses
    prev_expenses_total = 0
    try:
        from app.models_extended import Expense as Exp2
        prev_exp_query = Exp2.query.filter(
            and_(
                Exp2.expense_date >= prev_start.date(),
                Exp2.expense_date <= prev_end.date()
            )
        )
        if effective_location_id:
            prev_exp_query = prev_exp_query.filter(Exp2.location_id == effective_location_id)
        elif not current_user.is_global_admin and current_user.location_id:
            prev_exp_query = prev_exp_query.filter(Exp2.location_id == current_user.location_id)
        prev_expenses_total = sum(float(e.amount or 0) for e in prev_exp_query.all())
    except:
        prev_expenses_total = 0

    prev_growth_share = (prev_gross_profit * growth_share_percent / 100) if prev_gross_profit > 0 else 0
    prev_net_profit = (prev_gross_profit - prev_growth_share) - prev_expenses_total

    def pct_change(current, previous):
        if previous > 0:
            return ((current - previous) / previous) * 100
        return 0

    period_comparison = {
        'prev_label': f"{prev_start.strftime('%b %d')} - {prev_end.strftime('%b %d, %Y')}",
        'revenue': {'current': net_revenue, 'previous': prev_revenue, 'change': pct_change(net_revenue, prev_revenue)},
        'gross_revenue': {'current': gross_revenue, 'previous': prev_gross_revenue, 'change': pct_change(gross_revenue, prev_gross_revenue)},
        'discounts': {'current': total_discounts, 'previous': prev_discounts, 'change': pct_change(total_discounts, prev_discounts)},
        'cogs': {'current': cogs, 'previous': prev_cogs, 'change': pct_change(cogs, prev_cogs)},
        'gross_profit': {'current': gross_profit, 'previous': prev_gross_profit, 'change': pct_change(gross_profit, prev_gross_profit)},
        'expenses': {'current': total_expenses, 'previous': prev_expenses_total, 'change': pct_change(total_expenses, prev_expenses_total)},
        'net_profit': {'current': net_profit, 'previous': prev_net_profit, 'change': pct_change(net_profit, prev_net_profit)},
        'transactions': {'current': total_transactions, 'previous': prev_transactions, 'change': pct_change(total_transactions, prev_transactions)},
    }

    revenue_change = pct_change(net_revenue, prev_revenue)

    return render_template('reports/profit_loss.html',
                         period=period,
                         period_label=period_label,
                         start_date=start_date,
                         end_date=end_date,
                         # Revenue
                         gross_revenue=gross_revenue,
                         total_discounts=total_discounts,
                         net_revenue=net_revenue,
                         total_transactions=total_transactions,
                         # Costs
                         cogs=cogs,
                         direct_cogs=direct_cogs,
                         cogs_breakdown=cogs_breakdown,
                         # Growth Share
                         growth_share_percent=growth_share_percent,
                         growth_share=growth_share,
                         profit_after_growth_share=profit_after_growth_share,
                         # Expenses
                         total_expenses=total_expenses,
                         expense_by_category=expense_by_category,
                         # Profit
                         gross_profit=gross_profit,
                         gross_margin=gross_margin,
                         net_profit=net_profit,
                         net_margin=net_margin,
                         # Breakdowns
                         payment_breakdown=payment_breakdown,
                         daily_data=daily_data,
                         top_products=top_products,
                         category_breakdown=category_breakdown,
                         # Comparison
                         prev_revenue=prev_revenue,
                         revenue_change=revenue_change,
                         period_comparison=period_comparison,
                         # Location
                         user_location=user_location,
                         locations=locations,
                         selected_location_id=location_id)


@bp.route('/customer-analysis')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def customer_analysis():
    """Customer purchase behavior analysis - filtered by location"""
    from app.models import Location

    # Location filter support
    location_id = request.args.get('location_id', type=int)
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    sort_by = request.args.get('sort_by', 'total_spent_desc')
    search = request.args.get('search', '').strip()

    # Get date range
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    else:
        # Default to last 90 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)

    # Get user location for display
    user_location = None
    effective_location_id = None
    if not current_user.is_global_admin and current_user.location_id:
        effective_location_id = current_user.location_id
        user_location = Location.query.get(current_user.location_id)
    elif current_user.is_global_admin and location_id:
        effective_location_id = location_id
        user_location = Location.query.get(location_id)

    # Build base filter for sales
    base_filter = and_(
        Sale.sale_date >= start_date,
        Sale.sale_date <= end_date,
        Sale.status == 'completed'
    )
    # Add location filter
    if effective_location_id:
        base_filter = and_(base_filter, Sale.location_id == effective_location_id)

    # Top customers by revenue - filtered by location
    top_customers = db.session.query(
        Customer.id,
        Customer.name,
        Customer.phone,
        Customer.loyalty_points,
        func.count(Sale.id).label('purchases'),
        func.sum(Sale.total).label('total_spent'),
        func.avg(Sale.total).label('avg_purchase'),
        func.max(Sale.sale_date).label('last_purchase')
    ).select_from(Customer).join(
        Sale, Sale.customer_id == Customer.id
    ).filter(base_filter).group_by(Customer.id).order_by(func.sum(Sale.total).desc()).limit(50).all()

    # Convert to dicts for filtering/sorting
    top_customers_list = [
        {
            'id': c.id, 'name': c.name, 'phone': c.phone,
            'loyalty_points': c.loyalty_points or 0,
            'purchases': int(c.purchases or 0),
            'total_spent': float(c.total_spent or 0),
            'avg_purchase': float(c.avg_purchase or 0),
            'last_purchase': c.last_purchase
        }
        for c in top_customers
    ]

    # Apply search filter
    if search:
        search_lower = search.lower()
        top_customers_list = [c for c in top_customers_list
                              if search_lower in (c['name'] or '').lower() or search_lower in (c['phone'] or '').lower()]

    # Apply sorting
    cust_sort_options = {
        'total_spent_desc': lambda x: -x['total_spent'],
        'visit_count_desc': lambda x: -x['purchases'],
        'name_asc': lambda x: (x['name'] or '').lower(),
        'last_visit_desc': lambda x: (datetime.min if x['last_purchase'] is None else
                                       (x['last_purchase'] if isinstance(x['last_purchase'], datetime) else datetime.combine(x['last_purchase'], datetime.min.time()))),
    }
    sort_fn = cust_sort_options.get(sort_by, cust_sort_options['total_spent_desc'])
    reverse_sort = sort_by == 'last_visit_desc'
    top_customers_list.sort(key=sort_fn, reverse=reverse_sort)

    top_customers = top_customers_list

    # Customer loyalty tier breakdown - use loyalty_points ranges instead of property
    tier_case = case(
        (Customer.loyalty_points >= 2500, 'Platinum'),
        (Customer.loyalty_points >= 1000, 'Gold'),
        (Customer.loyalty_points >= 250, 'Silver'),
        else_='Bronze'
    )

    # Build tier filter with location
    tier_filter = or_(
        Sale.id.is_(None),  # Include customers with no sales
        base_filter
    )

    tier_breakdown = db.session.query(
        tier_case.label('loyalty_tier'),
        func.count(func.distinct(Customer.id)).label('customer_count'),
        func.count(Sale.id).label('total_purchases'),
        func.sum(Sale.total).label('total_revenue')
    ).select_from(Customer).outerjoin(
        Sale, Sale.customer_id == Customer.id
    ).filter(tier_filter).group_by(tier_case).all()

    # New vs returning customers
    new_customers = Customer.query.filter(
        and_(
            Customer.created_at >= start_date,
            Customer.created_at <= end_date
        )
    ).count()

    return render_template('reports/customer_analysis.html',
                         start_date=start_date,
                         end_date=end_date,
                         top_customers=top_customers,
                         tier_breakdown=tier_breakdown,
                         new_customers=new_customers,
                         user_location=user_location,
                         locations=locations,
                         selected_location_id=location_id,
                         sort_by=sort_by,
                         search=search)


@bp.route('/export/<report_type>')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def export_report(report_type):
    """
    Generic export endpoint for reports

    Args:
        report_type: Type of report (daily, weekly, monthly, inventory, customers)

    Query params:
        format: excel or csv (default: excel)
        date: Report date (for daily reports)
        start_date, end_date: Date range (for period reports)
    """
    from app.utils.export import export_to_excel, export_to_csv, export_sales_report, export_inventory_report, export_customer_report
    from app.models import Location

    export_format = request.args.get('format', 'excel')
    date_str = request.args.get('date')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # Determine date range
    if date_str:
        report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        start_date = report_date
        end_date = report_date
    elif start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=7)

    # Location filter for non-global admins
    location_filter = None
    if not current_user.is_global_admin and current_user.location_id:
        location_filter = current_user.location_id

    try:
        if report_type == 'daily' or report_type == 'sales':
            # Sales export
            query = Sale.query.filter(
                func.date(Sale.sale_date) >= start_date,
                func.date(Sale.sale_date) <= end_date,
                Sale.status == 'completed'
            )
            if location_filter:
                query = query.filter(Sale.location_id == location_filter)
            sales = query.order_by(Sale.sale_date.desc()).all()

            output = export_sales_report(sales, format_type=export_format)
            filename = f"sales_report_{start_date}_{end_date}.{'xlsx' if export_format == 'excel' else 'csv'}"
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if export_format == 'excel' else 'text/csv'

        elif report_type == 'inventory':
            # Inventory export
            products = Product.query.filter(Product.is_active == True).order_by(Product.name).all()
            output = export_inventory_report(products, format_type=export_format)
            filename = f"inventory_report_{datetime.now().strftime('%Y%m%d')}.{'xlsx' if export_format == 'excel' else 'csv'}"
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if export_format == 'excel' else 'text/csv'

        elif report_type == 'customers':
            # Customer export
            customers = Customer.query.order_by(Customer.name).all()
            output = export_customer_report(customers, format_type=export_format)
            filename = f"customer_report_{datetime.now().strftime('%Y%m%d')}.{'xlsx' if export_format == 'excel' else 'csv'}"
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if export_format == 'excel' else 'text/csv'

        elif report_type == 'product-performance':
            # Product performance export
            products_query = db.session.query(
                Product.code,
                Product.name,
                Product.brand,
                func.sum(SaleItem.quantity).label('units_sold'),
                func.sum(SaleItem.subtotal).label('revenue'),
                func.count(func.distinct(Sale.id)).label('transactions')
            ).join(SaleItem).join(Sale).filter(
                func.date(Sale.sale_date) >= start_date,
                func.date(Sale.sale_date) <= end_date,
                Sale.status == 'completed'
            )
            if location_filter:
                products_query = products_query.filter(Sale.location_id == location_filter)

            products_data = products_query.group_by(Product.id).order_by(func.sum(SaleItem.subtotal).desc()).all()

            columns = {
                'code': 'Product Code',
                'name': 'Product Name',
                'brand': 'Brand',
                'units_sold': 'Units Sold',
                'revenue': 'Revenue',
                'transactions': 'Transactions'
            }
            data = [{
                'code': p.code,
                'name': p.name,
                'brand': p.brand or '',
                'units_sold': int(p.units_sold) if p.units_sold else 0,
                'revenue': float(p.revenue) if p.revenue else 0,
                'transactions': int(p.transactions) if p.transactions else 0
            } for p in products_data]

            if export_format == 'excel':
                output = export_to_excel(data, columns, title=f"Product Performance Report ({start_date} to {end_date})")
            else:
                output = export_to_csv(data, columns)

            filename = f"product_performance_{start_date}_{end_date}.{'xlsx' if export_format == 'excel' else 'csv'}"
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if export_format == 'excel' else 'text/csv'

        else:
            return jsonify({'error': 'Invalid report type'}), 400

        return send_file(
            output,
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        current_app.logger.error(f"Export error: {str(e)}")
        return jsonify({'error': 'Export failed', 'message': str(e)}), 500


@bp.route('/stock-valuation')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def stock_valuation():
    """Stock valuation report by location - shows cost and selling value"""

    # Get selected location from request
    selected_location_id = request.args.get('location_id', type=int)
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'name_asc')
    category_id = request.args.get('category_id', type=int)

    # Get all locations
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    # Calculate stock values per location
    location_summaries = []
    grand_total_cost = 0
    grand_total_selling = 0
    grand_total_items = 0
    grand_total_quantity = 0

    for loc in locations:
        stocks = LocationStock.query.filter_by(location_id=loc.id).filter(LocationStock.quantity > 0).all()

        loc_cost_value = 0
        loc_selling_value = 0
        loc_item_count = len(stocks)
        loc_total_quantity = 0

        for stock in stocks:
            if stock.product:
                loc_cost_value += float(stock.quantity) * float(stock.product.cost_price or 0)
                loc_selling_value += float(stock.quantity) * float(stock.product.selling_price or 0)
                loc_total_quantity += stock.quantity

        location_summaries.append({
            'location': loc,
            'cost_value': loc_cost_value,
            'selling_value': loc_selling_value,
            'potential_profit': loc_selling_value - loc_cost_value,
            'item_count': loc_item_count,
            'total_quantity': loc_total_quantity
        })

        grand_total_cost += loc_cost_value
        grand_total_selling += loc_selling_value
        grand_total_items += loc_item_count
        grand_total_quantity += loc_total_quantity

    # Get detailed stock for selected location
    selected_location = None
    location_stock_details = []

    if selected_location_id:
        selected_location = Location.query.get(selected_location_id)
        if selected_location:
            stocks = LocationStock.query.filter_by(location_id=selected_location_id)\
                .filter(LocationStock.quantity > 0)\
                .join(Product)\
                .order_by(Product.name).all()

            for stock in stocks:
                if stock.product:
                    # Get individual cost components
                    base_cost = float(stock.product.base_cost or 0)
                    packaging_cost = float(stock.product.packaging_cost or 0)
                    delivery_cost = float(stock.product.delivery_cost or 0)
                    bottle_cost = float(stock.product.bottle_cost or 0)
                    kiosk_cost = float(stock.product.kiosk_cost or 0)
                    total_cost = base_cost + packaging_cost + delivery_cost + bottle_cost + kiosk_cost

                    # Calculate values
                    qty = float(stock.quantity)
                    base_value = qty * base_cost
                    packaging_value = qty * packaging_cost
                    delivery_value = qty * delivery_cost
                    bottle_value = qty * bottle_cost
                    kiosk_value = qty * kiosk_cost
                    cost_val = qty * total_cost
                    sell_val = qty * float(stock.product.selling_price or 0)

                    location_stock_details.append({
                        'product': stock.product,
                        'quantity': stock.quantity,
                        # Per unit costs
                        'base_cost': base_cost,
                        'packaging_cost': packaging_cost,
                        'delivery_cost': delivery_cost,
                        'bottle_cost': bottle_cost,
                        'kiosk_cost': kiosk_cost,
                        'cost_price': total_cost,
                        'selling_price': float(stock.product.selling_price or 0),
                        # Total values
                        'base_value': base_value,
                        'packaging_value': packaging_value,
                        'delivery_value': delivery_value,
                        'bottle_value': bottle_value,
                        'kiosk_value': kiosk_value,
                        'cost_value': cost_val,
                        'selling_value': sell_val,
                        'profit': sell_val - cost_val
                    })

    # Filter detail view by category
    if category_id and location_stock_details:
        location_stock_details = [d for d in location_stock_details
                                  if d['product'].category_id == category_id]

    # Search filter for detail view
    if search and location_stock_details:
        search_lower = search.lower()
        location_stock_details = [d for d in location_stock_details
                                  if search_lower in d['product'].name.lower() or
                                     search_lower in (d['product'].code or '').lower()]

    # Sort detail view
    sort_options = {
        'name_asc': (lambda x: x['product'].name.lower(), False),
        'name_desc': (lambda x: x['product'].name.lower(), True),
        'cost_value_desc': (lambda x: x['cost_value'], True),
        'selling_value_desc': (lambda x: x['selling_value'], True),
        'profit_desc': (lambda x: x['profit'], True),
        'quantity_desc': (lambda x: float(x['quantity']), True),
    }
    if sort_by in sort_options:
        sort_key, sort_reverse = sort_options[sort_by]
        location_stock_details.sort(key=sort_key, reverse=sort_reverse)

    # Get categories for filter dropdown
    categories = Category.query.order_by(Category.name).all()

    # Get production order summary
    production_stats = {
        'total_orders': ProductionOrder.query.count(),
        'completed_orders': ProductionOrder.query.filter_by(status='completed').count(),
        'pending_orders': ProductionOrder.query.filter(ProductionOrder.status.in_(['draft', 'pending', 'approved', 'in_progress'])).count(),
        'total_produced': db.session.query(func.sum(ProductionOrder.quantity_produced)).filter_by(status='completed').scalar() or 0
    }

    # Get raw material stock value
    raw_material_value = 0
    raw_materials_query = db.session.query(
        func.sum(RawMaterialStock.quantity * RawMaterial.cost_per_unit)
    ).join(RawMaterial).filter(RawMaterialStock.quantity > 0)

    if selected_location_id:
        raw_materials_query = raw_materials_query.filter(RawMaterialStock.location_id == selected_location_id)

    raw_material_value = raw_materials_query.scalar() or 0

    return render_template('reports/stock_valuation.html',
                         locations=locations,
                         location_summaries=location_summaries,
                         selected_location=selected_location,
                         selected_location_id=selected_location_id,
                         location_stock_details=location_stock_details,
                         grand_total_cost=grand_total_cost,
                         grand_total_selling=grand_total_selling,
                         grand_total_profit=grand_total_selling - grand_total_cost,
                         grand_total_items=grand_total_items,
                         grand_total_quantity=grand_total_quantity,
                         production_stats=production_stats,
                         raw_material_value=float(raw_material_value),
                         search=search,
                         sort_by=sort_by,
                         categories=categories,
                         selected_category_id=category_id)


@bp.route('/stock-reconciliation')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def stock_reconciliation():
    """Stock Reconciliation Report - Raw materials and purchased products (excludes recipe outputs)"""
    from datetime import date

    # Get filters
    selected_location_id = request.args.get('location_id', type=int)
    from_date_str = request.args.get('from_date')
    to_date_str = request.args.get('to_date')
    show_type = request.args.get('show_type', 'all')  # 'all', 'raw_materials', 'products'
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'name_asc')

    # Default to current month
    today = date.today()
    if from_date_str:
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
    else:
        from_date = today.replace(day=1)

    if to_date_str:
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
    else:
        to_date = today

    # Get all locations
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    # Get product IDs that are recipe outputs (produced items) - exclude these
    recipe_output_product_ids = [r.product_id for r in Recipe.query.filter(Recipe.product_id.isnot(None)).all()]

    # ============================================================
    # RAW MATERIALS RECONCILIATION
    # ============================================================
    raw_material_data = []
    total_raw_material_value = 0

    if show_type in ['all', 'raw_materials']:
        raw_materials = RawMaterial.query.filter_by(is_active=True).order_by(RawMaterial.name).all()

        for material in raw_materials:
            # Get current stock at location(s)
            if selected_location_id:
                stock = RawMaterialStock.query.filter_by(
                    raw_material_id=material.id,
                    location_id=selected_location_id
                ).first()
                current_qty = float(stock.quantity) if stock else 0
            else:
                current_qty = db.session.query(func.sum(RawMaterialStock.quantity)).filter_by(
                    raw_material_id=material.id
                ).scalar() or 0
                current_qty = float(current_qty)

            # Get movements in date range
            movements_query = RawMaterialMovement.query.filter(
                RawMaterialMovement.raw_material_id == material.id,
                RawMaterialMovement.timestamp >= datetime.combine(from_date, datetime.min.time()),
                RawMaterialMovement.timestamp <= datetime.combine(to_date, datetime.max.time())
            )
            if selected_location_id:
                movements_query = movements_query.filter_by(location_id=selected_location_id)

            movements = movements_query.all()

            # Categorize movements
            purchases_in = sum(float(m.quantity) for m in movements if m.movement_type == 'purchase' and float(m.quantity) > 0)
            production_out = abs(sum(float(m.quantity) for m in movements if m.movement_type == 'production_consumption' and float(m.quantity) < 0))
            adjustments = sum(float(m.quantity) for m in movements if m.movement_type == 'adjustment')
            transfers_in = sum(float(m.quantity) for m in movements if m.movement_type == 'transfer_in' and float(m.quantity) > 0)
            transfers_out = abs(sum(float(m.quantity) for m in movements if m.movement_type == 'transfer_out' and float(m.quantity) < 0))
            damage_out = abs(sum(float(m.quantity) for m in movements if m.movement_type == 'damage' and float(m.quantity) < 0))

            # Only include materials with activity or stock
            if current_qty > 0 or purchases_in > 0 or production_out > 0:
                cost_per_unit = float(material.cost_per_unit or 0)
                stock_value = current_qty * cost_per_unit

                raw_material_data.append({
                    'material': material,
                    'category': material.category.name if material.category else 'Unknown',
                    'unit': material.unit,
                    'current_stock': current_qty,
                    'purchases_in': purchases_in,
                    'production_out': production_out,
                    'adjustments': adjustments,
                    'transfers_in': transfers_in,
                    'transfers_out': transfers_out,
                    'damage_out': damage_out,
                    'cost_per_unit': cost_per_unit,
                    'stock_value': stock_value
                })

                total_raw_material_value += stock_value

    # ============================================================
    # PURCHASED PRODUCTS (Exclude recipe outputs)
    # ============================================================
    product_data = []
    total_product_value = 0

    if show_type in ['all', 'products']:
        # Only get products that are NOT recipe outputs (directly purchased products)
        products_query = Product.query.filter_by(is_active=True)
        if recipe_output_product_ids:
            products_query = products_query.filter(~Product.id.in_(recipe_output_product_ids))
        products = products_query.order_by(Product.name).all()

        for product in products:
            # Get current stock at location(s)
            if selected_location_id:
                stock = LocationStock.query.filter_by(
                    product_id=product.id,
                    location_id=selected_location_id
                ).first()
                current_qty = stock.quantity if stock else 0
            else:
                current_qty = db.session.query(func.sum(LocationStock.quantity)).filter_by(
                    product_id=product.id
                ).scalar() or 0

            # Get movements in date range
            movements_query = StockMovement.query.filter(
                StockMovement.product_id == product.id,
                StockMovement.timestamp >= datetime.combine(from_date, datetime.min.time()),
                StockMovement.timestamp <= datetime.combine(to_date, datetime.max.time())
            )
            if selected_location_id:
                movements_query = movements_query.filter_by(location_id=selected_location_id)

            movements = movements_query.all()

            # Categorize movements
            purchases_in = sum(m.quantity for m in movements if m.movement_type == 'purchase' and m.quantity > 0)
            sales_out = abs(sum(m.quantity for m in movements if m.movement_type == 'sale' and m.quantity < 0))
            adjustments = sum(m.quantity for m in movements if m.movement_type == 'adjustment')
            transfers_in = sum(m.quantity for m in movements if m.movement_type == 'transfer_in' and m.quantity > 0)
            transfers_out = abs(sum(m.quantity for m in movements if m.movement_type == 'transfer_out' and m.quantity < 0))
            returns_in = sum(m.quantity for m in movements if m.movement_type == 'return' and m.quantity > 0)
            damage_out = abs(sum(m.quantity for m in movements if m.movement_type == 'damage' and m.quantity < 0))

            # Only include products with activity or stock
            if current_qty > 0 or purchases_in > 0 or sales_out > 0:
                # Get individual cost components
                base_cost = float(product.base_cost or 0)
                packaging_cost = float(product.packaging_cost or 0)
                delivery_cost = float(product.delivery_cost or 0)
                bottle_cost = float(product.bottle_cost or 0)
                kiosk_cost = float(product.kiosk_cost or 0)
                total_cost = base_cost + packaging_cost + delivery_cost + bottle_cost + kiosk_cost

                # Calculate values based on current stock
                base_value = float(current_qty) * base_cost
                packaging_value = float(current_qty) * packaging_cost
                delivery_value = float(current_qty) * delivery_cost
                bottle_value = float(current_qty) * bottle_cost
                kiosk_value = float(current_qty) * kiosk_cost
                stock_value = float(current_qty) * total_cost

                product_data.append({
                    'product': product,
                    'current_stock': current_qty,
                    'purchases_in': purchases_in,
                    'sales_out': sales_out,
                    'adjustments': adjustments,
                    'transfers_in': transfers_in,
                    'transfers_out': transfers_out,
                    'returns_in': returns_in,
                    'damage_out': damage_out,
                    # Cost breakdown per unit
                    'base_cost': base_cost,
                    'packaging_cost': packaging_cost,
                    'delivery_cost': delivery_cost,
                    'bottle_cost': bottle_cost,
                    'kiosk_cost': kiosk_cost,
                    'total_cost': total_cost,
                    # Value breakdown (quantity * cost)
                    'base_value': base_value,
                    'packaging_value': packaging_value,
                    'delivery_value': delivery_value,
                    'bottle_value': bottle_value,
                    'kiosk_value': kiosk_value,
                    'stock_value': stock_value
                })

                total_product_value += stock_value

    # Get purchase summary for the period
    purchase_summary = {
        'total_orders': PurchaseOrder.query.filter(
            PurchaseOrder.order_date >= from_date,
            PurchaseOrder.order_date <= to_date,
            PurchaseOrder.status.in_(['received', 'partial'])
        ).count(),
        'total_value': db.session.query(func.sum(PurchaseOrder.grand_total_landed)).filter(
            PurchaseOrder.order_date >= from_date,
            PurchaseOrder.order_date <= to_date,
            PurchaseOrder.status.in_(['received', 'partial'])
        ).scalar() or 0,
        'total_paid': db.session.query(func.sum(PurchaseOrder.amount_paid)).filter(
            PurchaseOrder.order_date >= from_date,
            PurchaseOrder.order_date <= to_date
        ).scalar() or 0,
        'total_due': db.session.query(func.sum(PurchaseOrder.amount_due)).filter(
            PurchaseOrder.order_date >= from_date,
            PurchaseOrder.order_date <= to_date
        ).scalar() or 0
    }

    # Get production summary
    production_summary = {
        'total_orders': ProductionOrder.query.filter(
            ProductionOrder.created_at >= datetime.combine(from_date, datetime.min.time()),
            ProductionOrder.created_at <= datetime.combine(to_date, datetime.max.time())
        ).count(),
        'completed_orders': ProductionOrder.query.filter(
            ProductionOrder.created_at >= datetime.combine(from_date, datetime.min.time()),
            ProductionOrder.created_at <= datetime.combine(to_date, datetime.max.time()),
            ProductionOrder.status == 'completed'
        ).count(),
        'total_produced': db.session.query(func.sum(ProductionOrder.quantity_produced)).filter(
            ProductionOrder.created_at >= datetime.combine(from_date, datetime.min.time()),
            ProductionOrder.created_at <= datetime.combine(to_date, datetime.max.time()),
            ProductionOrder.status == 'completed'
        ).scalar() or 0
    }

    selected_location = Location.query.get(selected_location_id) if selected_location_id else None

    # Search filter
    if search:
        search_lower = search.lower()
        raw_material_data = [d for d in raw_material_data
                            if search_lower in d['material'].name.lower()]
        product_data = [d for d in product_data
                       if search_lower in d['product'].name.lower() or
                          search_lower in (d['product'].code or '').lower()]

    # Sort
    sort_options_rm = {
        'name_asc': (lambda x: x['material'].name.lower(), False),
        'stock_value_desc': (lambda x: x['stock_value'], True),
        'stock_desc': (lambda x: x['current_stock'], True),
        'consumed_desc': (lambda x: x['production_out'], True),
    }
    sort_options_prod = {
        'name_asc': (lambda x: x['product'].name.lower(), False),
        'stock_value_desc': (lambda x: x['stock_value'], True),
        'stock_desc': (lambda x: float(x['current_stock']), True),
        'consumed_desc': (lambda x: x['sales_out'], True),
    }
    if sort_by in sort_options_rm:
        sort_key, sort_reverse = sort_options_rm[sort_by]
        raw_material_data.sort(key=sort_key, reverse=sort_reverse)
    if sort_by in sort_options_prod:
        sort_key, sort_reverse = sort_options_prod[sort_by]
        product_data.sort(key=sort_key, reverse=sort_reverse)

    return render_template('reports/stock_reconciliation.html',
                         locations=locations,
                         selected_location=selected_location,
                         selected_location_id=selected_location_id,
                         from_date=from_date,
                         to_date=to_date,
                         show_type=show_type,
                         raw_material_data=raw_material_data,
                         product_data=product_data,
                         total_raw_material_value=total_raw_material_value,
                         total_product_value=total_product_value,
                         purchase_summary=purchase_summary,
                         production_summary=production_summary,
                         search=search,
                         sort_by=sort_by)


@bp.route('/purchase-register')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def purchase_register():
    """Purchase Register - All purchases with payment status"""
    from_date_str = request.args.get('from_date')
    to_date_str = request.args.get('to_date')
    payment_status = request.args.get('payment_status')
    supplier_id = request.args.get('supplier_id', type=int)
    location_id = request.args.get('location_id', type=int)
    sort_by = request.args.get('sort_by', 'date_desc')
    search = request.args.get('search', '').strip()

    # Default to current month
    today = datetime.now().date()
    if from_date_str:
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
    else:
        from_date = today.replace(day=1)

    if to_date_str:
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
    else:
        to_date = today

    # Build query
    query = PurchaseOrder.query.filter(
        PurchaseOrder.order_date >= from_date,
        PurchaseOrder.order_date <= to_date
    )

    if payment_status:
        query = query.filter_by(payment_status=payment_status)

    if supplier_id:
        query = query.filter_by(supplier_id=supplier_id)

    if location_id:
        query = query.filter_by(receiving_location_id=location_id)

    purchases = query.order_by(PurchaseOrder.order_date.desc()).all()

    # Apply search filter (supplier name or PO number)
    if search:
        search_lower = search.lower()
        purchases = [p for p in purchases
                     if search_lower in (p.po_number or '').lower()
                     or (p.supplier and search_lower in (p.supplier.name or '').lower())]

    # Apply sorting
    purchase_sort_options = {
        'date_desc': lambda x: x.order_date or datetime.min,
        'date_asc': lambda x: x.order_date or datetime.min,
        'amount_desc': lambda x: float(x.grand_total_landed or 0),
        'supplier_asc': lambda x: (x.supplier.name if x.supplier else '').lower(),
    }
    sort_fn = purchase_sort_options.get(sort_by, purchase_sort_options['date_desc'])
    reverse_sort = sort_by in ('date_desc', 'amount_desc')
    purchases.sort(key=sort_fn, reverse=reverse_sort)

    # Calculate totals
    totals = {
        'count': len(purchases),
        'ordered_value': sum(float(p.grand_total_landed or 0) for p in purchases),
        'received_value': sum(float(p.grand_total_landed or 0) for p in purchases if p.status == 'received'),
        'paid': sum(float(p.amount_paid or 0) for p in purchases),
        'due': sum(float(p.amount_due or 0) for p in purchases),
        'unpaid_count': len([p for p in purchases if p.payment_status == 'unpaid']),
        'partial_count': len([p for p in purchases if p.payment_status == 'partial']),
        'paid_count': len([p for p in purchases if p.payment_status == 'paid'])
    }

    # Get suppliers for filter
    from app.models import Supplier
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()

    # Get locations for filter
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    return render_template('reports/purchase_register.html',
                         purchases=purchases,
                         totals=totals,
                         suppliers=suppliers,
                         from_date=from_date,
                         to_date=to_date,
                         selected_payment_status=payment_status,
                         selected_supplier_id=supplier_id,
                         locations=locations,
                         selected_location_id=location_id,
                         sort_by=sort_by,
                         search=search)


@bp.route('/stock-movement-audit')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def stock_movement_audit():
    """Stock Movement Audit Trail - Complete history of stock changes"""
    from_date_str = request.args.get('from_date')
    to_date_str = request.args.get('to_date')
    product_id = request.args.get('product_id', type=int)
    location_id = request.args.get('location_id', type=int)
    movement_type = request.args.get('movement_type')
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'date_desc')

    # Default to last 7 days
    today = datetime.now()
    if from_date_str:
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d')
    else:
        from_date = today - timedelta(days=7)

    if to_date_str:
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    else:
        to_date = today

    # Build query
    query = StockMovement.query.filter(
        StockMovement.timestamp >= from_date,
        StockMovement.timestamp <= to_date
    )

    if product_id:
        query = query.filter_by(product_id=product_id)

    if location_id:
        query = query.filter_by(location_id=location_id)

    if movement_type:
        query = query.filter_by(movement_type=movement_type)

    movements = query.order_by(StockMovement.timestamp.desc()).limit(500).all()

    # Search filter
    if search:
        search_lower = search.lower()
        movements = [m for m in movements
                    if (m.product and search_lower in m.product.name.lower()) or
                       (m.reference and search_lower in m.reference.lower())]

    # Sort
    if sort_by == 'date_asc':
        movements.sort(key=lambda x: x.timestamp or datetime.min)
    elif sort_by == 'quantity_desc':
        movements.sort(key=lambda x: abs(x.quantity or 0), reverse=True)
    elif sort_by == 'product_asc':
        movements.sort(key=lambda x: (x.product.name if x.product else '').lower())
    elif sort_by == 'type_asc':
        movements.sort(key=lambda x: (x.movement_type or '').lower())
    # else: default date_desc from query

    # Calculate summary by type
    summary_by_type = {}
    for m in movements:
        if m.movement_type not in summary_by_type:
            summary_by_type[m.movement_type] = {'count': 0, 'quantity': 0}
        summary_by_type[m.movement_type]['count'] += 1
        summary_by_type[m.movement_type]['quantity'] += m.quantity

    # Get filter options
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    movement_types = ['purchase', 'sale', 'adjustment', 'return', 'damage', 'transfer_in', 'transfer_out', 'production']

    return render_template('reports/stock_movement_audit.html',
                         movements=movements,
                         summary_by_type=summary_by_type,
                         products=products,
                         locations=locations,
                         movement_types=movement_types,
                         from_date=from_date,
                         to_date=to_date,
                         selected_product_id=product_id,
                         selected_location_id=location_id,
                         selected_movement_type=movement_type,
                         search=search,
                         sort_by=sort_by)


@bp.route('/transfer-discrepancy')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def transfer_discrepancy():
    """Transfer Discrepancy Report - Shows variances in stock transfers"""
    from_date_str = request.args.get('from_date')
    to_date_str = request.args.get('to_date')
    show_only_discrepancies = request.args.get('discrepancies_only', 'false') == 'true'
    location_id = request.args.get('location_id', type=int)
    sort_by = request.args.get('sort_by', 'date_desc')
    search = request.args.get('search', '').strip()

    # Default to last 30 days
    today = datetime.now().date()
    if from_date_str:
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
    else:
        from_date = today - timedelta(days=30)

    if to_date_str:
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
    else:
        to_date = today

    # Get completed transfers
    transfer_query = StockTransfer.query.filter(
        StockTransfer.created_at >= datetime.combine(from_date, datetime.min.time()),
        StockTransfer.created_at <= datetime.combine(to_date, datetime.max.time()),
        StockTransfer.status == 'received'
    )
    if location_id:
        transfer_query = transfer_query.filter(
            db.or_(StockTransfer.source_location_id == location_id,
                   StockTransfer.destination_location_id == location_id)
        )
    transfers = transfer_query.order_by(StockTransfer.created_at.desc()).all()

    # Build discrepancy data
    transfer_data = []
    total_discrepancies = 0
    total_discrepancy_value = 0

    for transfer in transfers:
        items_with_discrepancy = []
        transfer_has_discrepancy = False

        for item in transfer.items:
            dispatched = item.quantity_dispatched or 0
            received = item.quantity_received or 0
            variance = received - dispatched

            if variance != 0:
                transfer_has_discrepancy = True
                total_discrepancies += 1
                if item.product:
                    total_discrepancy_value += abs(variance) * float(item.product.cost_price or 0)

            if not show_only_discrepancies or variance != 0:
                items_with_discrepancy.append({
                    'product': item.product,
                    'dispatched': dispatched,
                    'received': received,
                    'variance': variance,
                    'variance_value': abs(variance) * float(item.product.cost_price or 0) if item.product else 0
                })

        if not show_only_discrepancies or transfer_has_discrepancy:
            transfer_data.append({
                'transfer': transfer,
                'items': items_with_discrepancy,
                'has_discrepancy': transfer_has_discrepancy
            })

    # Apply search filter on product names within transfer items
    if search:
        search_lower = search.lower()
        for td in transfer_data:
            td['items'] = [item for item in td['items']
                          if item['product'] and search_lower in item['product'].name.lower()]
        # Remove transfers with no matching items
        transfer_data = [td for td in transfer_data if td['items']]

    # Apply sorting
    if sort_by == 'variance_desc':
        transfer_data.sort(key=lambda x: sum(abs(item['variance']) for item in x['items']), reverse=True)
    elif sort_by == 'value_desc':
        transfer_data.sort(key=lambda x: sum(item['variance_value'] for item in x['items']), reverse=True)
    # else date_desc is already the default from the query

    # Get locations for filter
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    return render_template('reports/transfer_discrepancy.html',
                         transfer_data=transfer_data,
                         total_discrepancies=total_discrepancies,
                         total_discrepancy_value=total_discrepancy_value,
                         from_date=from_date,
                         to_date=to_date,
                         show_only_discrepancies=show_only_discrepancies,
                         locations=locations,
                         selected_location_id=location_id,
                         sort_by=sort_by,
                         search=search)


@bp.route('/raw-material-stock')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def raw_material_stock():
    """Raw Material Stock Report - Track oils, ethanol, bottles used in production"""
    from datetime import date

    # Get filters
    selected_location_id = request.args.get('location_id', type=int)
    selected_category_id = request.args.get('category_id', type=int)
    from_date_str = request.args.get('from_date')
    to_date_str = request.args.get('to_date')
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'name_asc')

    # Default to current month
    today = date.today()
    if from_date_str:
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
    else:
        from_date = today.replace(day=1)

    if to_date_str:
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
    else:
        to_date = today

    # Get all locations and categories
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    categories = RawMaterialCategory.query.filter_by(is_active=True).all()

    # Build raw material data
    raw_material_data = []
    total_stock_value = 0
    total_purchased_value = 0
    total_consumed_value = 0

    # Get raw materials
    materials_query = RawMaterial.query.filter_by(is_active=True)
    if selected_category_id:
        materials_query = materials_query.filter_by(category_id=selected_category_id)
    materials = materials_query.order_by(RawMaterial.name).all()

    for material in materials:
        # Get current stock at location(s)
        if selected_location_id:
            stock = RawMaterialStock.query.filter_by(
                raw_material_id=material.id,
                location_id=selected_location_id
            ).first()
            current_qty = float(stock.quantity) if stock else 0
        else:
            # Sum across all locations
            current_qty = db.session.query(func.sum(RawMaterialStock.quantity)).filter_by(
                raw_material_id=material.id
            ).scalar() or 0
            current_qty = float(current_qty)

        # Get movements in date range
        movements_query = RawMaterialMovement.query.filter(
            RawMaterialMovement.raw_material_id == material.id,
            RawMaterialMovement.timestamp >= datetime.combine(from_date, datetime.min.time()),
            RawMaterialMovement.timestamp <= datetime.combine(to_date, datetime.max.time())
        )
        if selected_location_id:
            movements_query = movements_query.filter_by(location_id=selected_location_id)

        movements = movements_query.all()

        # Categorize movements
        purchases_in = sum(float(m.quantity) for m in movements if m.movement_type == 'purchase' and float(m.quantity) > 0)
        production_out = abs(sum(float(m.quantity) for m in movements if m.movement_type == 'production_consumption' and float(m.quantity) < 0))
        adjustments = sum(float(m.quantity) for m in movements if m.movement_type == 'adjustment')
        transfers_in = sum(float(m.quantity) for m in movements if m.movement_type == 'transfer_in' and float(m.quantity) > 0)
        transfers_out = abs(sum(float(m.quantity) for m in movements if m.movement_type == 'transfer_out' and float(m.quantity) < 0))
        damage_out = abs(sum(float(m.quantity) for m in movements if m.movement_type == 'damage' and float(m.quantity) < 0))

        # Calculate values
        cost_per_unit = float(material.cost_per_unit or 0)
        stock_value = current_qty * cost_per_unit
        purchased_value = purchases_in * cost_per_unit
        consumed_value = production_out * cost_per_unit

        # Only include materials with activity or stock
        if current_qty > 0 or purchases_in > 0 or production_out > 0:
            raw_material_data.append({
                'material': material,
                'category': material.category.name if material.category else 'Unknown',
                'unit': material.unit,
                'current_stock': current_qty,
                'purchases_in': purchases_in,
                'production_out': production_out,
                'adjustments': adjustments,
                'transfers_in': transfers_in,
                'transfers_out': transfers_out,
                'damage_out': damage_out,
                'cost_per_unit': cost_per_unit,
                'stock_value': stock_value,
                'purchased_value': purchased_value,
                'consumed_value': consumed_value
            })

            total_stock_value += stock_value
            total_purchased_value += purchased_value
            total_consumed_value += consumed_value

    # Get category-wise summary
    category_summary = {}
    for item in raw_material_data:
        cat = item['category']
        if cat not in category_summary:
            category_summary[cat] = {'stock_value': 0, 'purchased_value': 0, 'consumed_value': 0, 'item_count': 0}
        category_summary[cat]['stock_value'] += item['stock_value']
        category_summary[cat]['purchased_value'] += item['purchased_value']
        category_summary[cat]['consumed_value'] += item['consumed_value']
        category_summary[cat]['item_count'] += 1

    # Get production orders summary
    production_query = ProductionOrder.query.filter(
        ProductionOrder.created_at >= datetime.combine(from_date, datetime.min.time()),
        ProductionOrder.created_at <= datetime.combine(to_date, datetime.max.time())
    )
    if selected_location_id:
        production_query = production_query.filter_by(location_id=selected_location_id)

    production_summary = {
        'total_orders': production_query.count(),
        'completed_orders': production_query.filter_by(status='completed').count(),
        'total_produced': db.session.query(func.sum(ProductionOrder.quantity_produced)).filter(
            ProductionOrder.created_at >= datetime.combine(from_date, datetime.min.time()),
            ProductionOrder.created_at <= datetime.combine(to_date, datetime.max.time()),
            ProductionOrder.status == 'completed'
        ).scalar() or 0
    }

    selected_location = Location.query.get(selected_location_id) if selected_location_id else None

    # Search filter
    if search:
        search_lower = search.lower()
        raw_material_data = [d for d in raw_material_data
                            if search_lower in d['material'].name.lower()]

    # Sort
    sort_options = {
        'name_asc': (lambda x: x['material'].name.lower(), False),
        'name_desc': (lambda x: x['material'].name.lower(), True),
        'stock_value_desc': (lambda x: x['stock_value'], True),
        'stock_desc': (lambda x: x['current_stock'], True),
        'consumed_desc': (lambda x: x['production_out'], True),
        'purchased_desc': (lambda x: x['purchases_in'], True),
        'category_asc': (lambda x: x['category'].lower(), False),
    }
    if sort_by in sort_options:
        sort_key, sort_reverse = sort_options[sort_by]
        raw_material_data.sort(key=sort_key, reverse=sort_reverse)

    return render_template('reports/raw_material_stock.html',
                         locations=locations,
                         categories=categories,
                         selected_location=selected_location,
                         selected_location_id=selected_location_id,
                         selected_category_id=selected_category_id,
                         from_date=from_date,
                         to_date=to_date,
                         raw_material_data=raw_material_data,
                         category_summary=category_summary,
                         total_stock_value=total_stock_value,
                         total_purchased_value=total_purchased_value,
                         total_consumed_value=total_consumed_value,
                         production_summary=production_summary,
                         search=search,
                         sort_by=sort_by)


@bp.route('/stock-in-out')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def stock_in_out():
    """Stock In/Out Comparison Report - Purchase vs Sale analysis with movement breakdown"""
    from app.models import Category

    # Filters
    from_date_str = request.args.get('from_date')
    to_date_str = request.args.get('to_date')
    location_id = request.args.get('location_id', type=int)
    category_id = request.args.get('category_id', type=int)
    view_mode = request.args.get('view', 'summary')  # summary or detailed
    sort_by = request.args.get('sort_by', 'name_asc')
    search = request.args.get('search', '').strip()

    today = datetime.now().date()
    from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date() if from_date_str else today - timedelta(days=30)
    to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date() if to_date_str else today

    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    categories = Category.query.order_by(Category.name).all()

    # Determine effective location
    effective_location_id = None
    if not current_user.is_global_admin and current_user.location_id:
        effective_location_id = current_user.location_id
    elif current_user.is_global_admin and location_id:
        effective_location_id = location_id

    # Build movement query with all types as separate columns using CASE
    movement_types = ['purchase', 'sale', 'transfer_in', 'transfer_out', 'adjustment', 'damage', 'production', 'return']

    base_filter = [
        StockMovement.timestamp >= datetime.combine(from_date, datetime.min.time()),
        StockMovement.timestamp <= datetime.combine(to_date, datetime.max.time())
    ]
    if effective_location_id:
        base_filter.append(StockMovement.location_id == effective_location_id)

    # Query: per-product breakdown by movement type
    columns = [
        Product.id.label('product_id'),
        Product.name.label('product_name'),
        Product.code.label('product_code'),
    ]
    for mt in movement_types:
        columns.append(
            func.coalesce(func.sum(case(
                (StockMovement.movement_type == mt, StockMovement.quantity),
                else_=0
            )), 0).label(mt)
        )
    columns.append(func.sum(StockMovement.quantity).label('net_change'))

    query = db.session.query(*columns).select_from(StockMovement).join(
        Product, Product.id == StockMovement.product_id
    ).filter(*base_filter)

    if category_id:
        query = query.filter(Product.category_id == category_id)

    product_movements = query.group_by(Product.id).order_by(Product.name).all()

    # Build result data
    product_data = []
    totals = {mt: 0 for mt in movement_types}
    totals['net_change'] = 0
    totals['stock_in'] = 0
    totals['stock_out'] = 0

    in_types = {'purchase', 'transfer_in', 'return', 'production'}
    out_types = {'sale', 'transfer_out', 'damage'}

    for row in product_movements:
        item = {
            'product_id': row.product_id,
            'product_name': row.product_name,
            'product_code': row.product_code,
            'net_change': float(row.net_change or 0),
        }
        stock_in = 0
        stock_out = 0
        for mt in movement_types:
            val = float(getattr(row, mt) or 0)
            item[mt] = val
            totals[mt] += val
            if mt in in_types:
                stock_in += val
            elif mt in out_types:
                stock_out += abs(val)

        item['stock_in'] = stock_in
        item['stock_out'] = stock_out
        totals['stock_in'] += stock_in
        totals['stock_out'] += stock_out
        totals['net_change'] += item['net_change']

        # Get current stock
        if effective_location_id:
            ls = LocationStock.query.filter_by(
                product_id=row.product_id, location_id=effective_location_id
            ).first()
            item['current_stock'] = float(ls.quantity) if ls else 0
        else:
            product = Product.query.get(row.product_id)
            item['current_stock'] = float(product.quantity) if product else 0

        product_data.append(item)

    # Apply search filter
    if search:
        search_lower = search.lower()
        product_data = [p for p in product_data
                       if search_lower in p['product_name'].lower() or search_lower in (p['product_code'] or '').lower()]

    # Apply sorting
    sio_sort_options = {
        'name_asc': lambda x: x['product_name'].lower(),
        'net_change_desc': lambda x: -abs(x['net_change']),
        'purchase_desc': lambda x: -x.get('purchase', 0),
        'sale_desc': lambda x: -abs(x.get('sale', 0)),
    }
    sort_fn = sio_sort_options.get(sort_by, sio_sort_options['name_asc'])
    product_data.sort(key=sort_fn)

    return render_template('reports/stock_in_out.html',
                         from_date=from_date,
                         to_date=to_date,
                         locations=locations,
                         categories=categories,
                         selected_location_id=location_id,
                         selected_category_id=category_id,
                         view_mode=view_mode,
                         product_data=product_data,
                         totals=totals,
                         movement_types=movement_types,
                         sort_by=sort_by,
                         search=search)


@bp.route('/sale-projection')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def sale_projection():
    """Projected Sale Estimation based on available stock and historical sales rate"""
    from app.models import Category

    # Filters
    location_id = request.args.get('location_id', type=int)
    category_id = request.args.get('category_id', type=int)
    lookback_days = request.args.get('lookback_days', 30, type=int)
    sort_by = request.args.get('sort_by', 'days_remaining_asc')
    search = request.args.get('search', '').strip()

    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    categories = Category.query.order_by(Category.name).all()

    # Determine effective location
    effective_location_id = None
    user_location = None
    if not current_user.is_global_admin and current_user.location_id:
        effective_location_id = current_user.location_id
        user_location = Location.query.get(current_user.location_id)
    elif current_user.is_global_admin and location_id:
        effective_location_id = location_id
        user_location = Location.query.get(location_id)

    # Calculate date range for lookback
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)

    # Get average daily sales per product
    sale_filter = [
        Sale.sale_date >= start_date,
        Sale.sale_date <= end_date,
        Sale.status == 'completed'
    ]
    if effective_location_id:
        sale_filter.append(Sale.location_id == effective_location_id)

    sales_query = db.session.query(
        Product.id.label('product_id'),
        Product.name.label('product_name'),
        Product.code.label('product_code'),
        Product.selling_price,
        Product.cost_price,
        Product.category_id,
        func.sum(SaleItem.quantity).label('total_sold')
    ).select_from(SaleItem).join(Sale).join(Product).filter(*sale_filter)

    if category_id:
        sales_query = sales_query.filter(Product.category_id == category_id)

    sales_by_product = {row.product_id: row for row in sales_query.group_by(Product.id).all()}

    # Get all active products with stock
    products_query = Product.query.filter_by(is_active=True)
    if category_id:
        products_query = products_query.filter_by(category_id=category_id)
    all_products = products_query.order_by(Product.name).all()

    product_data = []
    total_projected_revenue = 0
    total_projected_profit = 0
    at_risk_count = 0

    for product in all_products:
        # Get current stock
        if effective_location_id:
            ls = LocationStock.query.filter_by(
                product_id=product.id, location_id=effective_location_id
            ).first()
            current_stock = float(ls.available_quantity) if ls else 0
        else:
            current_stock = float(product.quantity or 0)

        if current_stock <= 0:
            continue

        selling_price = float(product.selling_price or 0)
        cost_price = float(product.cost_price or 0)

        # Get sales data
        sale_data = sales_by_product.get(product.id)
        total_sold = float(sale_data.total_sold) if sale_data else 0
        avg_daily_sales = total_sold / lookback_days if lookback_days > 0 else 0

        # Calculate projections
        if avg_daily_sales > 0:
            days_remaining = current_stock / avg_daily_sales
        else:
            days_remaining = None  # No sales history

        projected_revenue = current_stock * selling_price
        projected_profit = current_stock * (selling_price - cost_price)

        if days_remaining is not None and days_remaining < 7:
            at_risk_count += 1

        # Get category name
        cat_name = product.category.name if product.category else 'Uncategorized'

        product_data.append({
            'product_id': product.id,
            'product_name': product.name,
            'product_code': product.code,
            'category': cat_name,
            'current_stock': current_stock,
            'avg_daily_sales': round(avg_daily_sales, 2),
            'days_remaining': round(days_remaining, 1) if days_remaining is not None else None,
            'projected_revenue': projected_revenue,
            'projected_profit': projected_profit,
            'selling_price': selling_price,
            'cost_price': cost_price,
        })

        total_projected_revenue += projected_revenue
        total_projected_profit += projected_profit

    # Apply search filter
    if search:
        search_lower = search.lower()
        product_data = [p for p in product_data
                       if search_lower in p['product_name'].lower() or search_lower in (p['product_code'] or '').lower()]

    # Apply sorting
    proj_sort_options = {
        'days_remaining_asc': lambda x: (x['days_remaining'] is None, x['days_remaining'] or 0),
        'revenue_desc': lambda x: -x['projected_revenue'],
        'profit_desc': lambda x: -x['projected_profit'],
        'stock_desc': lambda x: -x['current_stock'],
        'name_asc': lambda x: x['product_name'].lower(),
    }
    sort_fn = proj_sort_options.get(sort_by, proj_sort_options['days_remaining_asc'])
    product_data.sort(key=sort_fn)

    # Top 10 by projected revenue for chart
    top_by_revenue = sorted(product_data, key=lambda x: x['projected_revenue'], reverse=True)[:10]

    return render_template('reports/sale_projection.html',
                         locations=locations,
                         categories=categories,
                         selected_location_id=location_id,
                         selected_category_id=category_id,
                         lookback_days=lookback_days,
                         user_location=user_location,
                         product_data=product_data,
                         total_projected_revenue=total_projected_revenue,
                         total_projected_profit=total_projected_profit,
                         at_risk_count=at_risk_count,
                         top_by_revenue=top_by_revenue,
                         sort_by=sort_by,
                         search=search)


@bp.route('/inventory-crosscheck')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def inventory_crosscheck():
    """Inventory cross-check report for manual physical count verification"""
    from app.models import Category, RawMaterialCategory
    from app.utils.location_context import get_current_location

    user_location = get_current_location()

    # Get all active locations
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    # Location filter - admin can pick, others see their own
    location_id = request.args.get('location_id', type=int)
    show_raw = request.args.get('show_raw', '0') == '1'
    category_id = request.args.get('category_id', type=int)
    search = request.args.get('search', '').strip()
    stock_filter = request.args.get('stock_filter', '')  # in_stock, out_of_stock, all
    sort_by = request.args.get('sort_by', 'category')  # category, name, code, stock_desc, stock_asc

    if current_user.is_global_admin and location_id:
        selected_locations = [Location.query.get(location_id)]
    elif current_user.is_global_admin:
        selected_locations = locations
    elif user_location:
        selected_locations = [user_location]
    else:
        selected_locations = locations

    # ===== FINISHED PRODUCTS =====
    categories = Category.query.order_by(Category.name).all()
    product_query = Product.query.filter_by(is_active=True)
    if category_id:
        product_query = product_query.filter_by(category_id=category_id)
    if search:
        product_query = product_query.filter(
            db.or_(Product.name.ilike(f'%{search}%'), Product.code.ilike(f'%{search}%'),
                   Product.barcode.ilike(f'%{search}%'))
        )
    products = product_query.order_by(Product.category_id, Product.name).all()

    # Build product data with per-location stock
    product_data = []
    grand_total_system = 0

    for product in products:
        loc_stocks = {}
        product_total = 0

        for loc in selected_locations:
            ls = LocationStock.query.filter_by(
                product_id=product.id,
                location_id=loc.id
            ).first()
            qty = ls.quantity if ls else 0
            loc_stocks[loc.id] = qty
            product_total += qty

        # Also include global product quantity
        global_qty = product.quantity or 0

        product_data.append({
            'product': product,
            'category_name': product.category.name if product.category else 'Uncategorized',
            'loc_stocks': loc_stocks,
            'location_total': product_total,
            'global_qty': global_qty,
        })
        grand_total_system += product_total

    # Apply stock filter
    if stock_filter == 'out_of_stock':
        product_data = [d for d in product_data if d['location_total'] == 0]
    elif stock_filter == 'in_stock':
        product_data = [d for d in product_data if d['location_total'] > 0]

    # Apply sort
    crosscheck_sorts = {
        'category': lambda x: (x['category_name'].lower(), x['product'].name.lower()),
        'name': lambda x: x['product'].name.lower(),
        'code': lambda x: (x['product'].code or '').lower(),
        'stock_desc': lambda x: -x['location_total'],
        'stock_asc': lambda x: x['location_total'],
    }
    product_data.sort(key=crosscheck_sorts.get(sort_by, crosscheck_sorts['category']))

    # Recalculate grand total after filtering
    grand_total_system = sum(d['location_total'] for d in product_data)

    # ===== RAW MATERIALS =====
    raw_data = []
    raw_grand_total = 0

    if show_raw:
        raw_materials = RawMaterial.query.filter_by(is_active=True).order_by(
            RawMaterial.category_id, RawMaterial.name
        ).all()

        for rm in raw_materials:
            loc_stocks = {}
            rm_total = 0

            for loc in selected_locations:
                rms = RawMaterialStock.query.filter_by(
                    raw_material_id=rm.id,
                    location_id=loc.id
                ).first()
                qty = float(rms.quantity) if rms else 0
                loc_stocks[loc.id] = qty
                rm_total += qty

            raw_data.append({
                'material': rm,
                'category_name': rm.category.name if rm.category else 'Uncategorized',
                'unit': rm.unit,
                'loc_stocks': loc_stocks,
                'location_total': rm_total,
                'global_qty': float(rm.quantity or 0),
            })
            raw_grand_total += rm_total

    return render_template('reports/inventory_crosscheck.html',
                         locations=locations,
                         categories=categories,
                         selected_locations=selected_locations,
                         selected_location_id=location_id,
                         selected_category_id=category_id,
                         user_location=user_location,
                         search=search,
                         stock_filter=stock_filter,
                         sort_by=sort_by,
                         product_data=product_data,
                         grand_total_system=grand_total_system,
                         show_raw=show_raw,
                         raw_data=raw_data,
                         raw_grand_total=raw_grand_total,
                         print_date=datetime.now())


@bp.route('/inventory-turnover')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def inventory_turnover():
    """Inventory turnover analysis - how fast products sell and get replaced"""
    from app.models import Category
    from app.utils.location_context import get_current_location

    user_location = get_current_location()
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    categories = Category.query.order_by(Category.name).all()

    # Filters
    location_id = request.args.get('location_id', type=int)
    category_id = request.args.get('category_id', type=int)
    period_days = request.args.get('period', 90, type=int)  # default 90 days
    speed_filter = request.args.get('speed', '')  # fast, normal, slow, dead
    sort_by = request.args.get('sort_by', 'turnover_desc')
    search = request.args.get('search', '').strip()
    stock_filter = request.args.get('stock_filter', '')  # in_stock, out_of_stock, low_stock
    min_value = request.args.get('min_value', 0, type=float)

    # Determine effective location
    if current_user.is_global_admin:
        effective_location_id = location_id
    elif user_location:
        effective_location_id = user_location.id
    else:
        effective_location_id = None

    end_date = datetime.now()
    start_date = end_date - timedelta(days=period_days)

    # Get sales quantity per product in period
    sales_query = db.session.query(
        SaleItem.product_id,
        func.sum(SaleItem.quantity).label('units_sold'),
        func.sum(SaleItem.subtotal).label('revenue'),
    ).select_from(SaleItem).join(Sale).filter(
        Sale.sale_date >= start_date,
        Sale.sale_date <= end_date,
        Sale.status == 'completed'
    )

    if effective_location_id:
        sales_query = sales_query.filter(Sale.location_id == effective_location_id)

    sales_data = {row.product_id: {
        'units_sold': int(row.units_sold or 0),
        'revenue': float(row.revenue or 0)
    } for row in sales_query.group_by(SaleItem.product_id).all()}

    # Get products
    product_query = Product.query.filter_by(is_active=True)
    if category_id:
        product_query = product_query.filter_by(category_id=category_id)
    if search:
        product_query = product_query.filter(
            db.or_(Product.name.ilike(f'%{search}%'), Product.code.ilike(f'%{search}%'),
                   Product.barcode.ilike(f'%{search}%'))
        )

    products = product_query.order_by(Product.name).all()

    product_data = []
    total_stock_value = 0
    total_cogs = 0
    turnover_buckets = {'fast': 0, 'normal': 0, 'slow': 0, 'dead': 0}

    for p in products:
        # Current stock
        if effective_location_id:
            ls = LocationStock.query.filter_by(product_id=p.id, location_id=effective_location_id).first()
            current_stock = ls.quantity if ls else 0
        else:
            current_stock = p.quantity or 0

        cost_price = float(p.cost_price or 0)
        stock_value = current_stock * cost_price
        total_stock_value += stock_value

        sale_info = sales_data.get(p.id, {'units_sold': 0, 'revenue': 0})
        units_sold = sale_info['units_sold']
        cogs = units_sold * cost_price
        total_cogs += cogs

        # Average inventory = (current stock + estimated start stock) / 2
        # Estimated start = current + sold (simple approximation)
        avg_inventory = (current_stock + (current_stock + units_sold)) / 2
        avg_inventory_value = avg_inventory * cost_price

        # Turnover ratio = COGS / Average Inventory Value
        if avg_inventory_value > 0:
            turnover_ratio = cogs / avg_inventory_value
        else:
            turnover_ratio = 0

        # Days to sell = period_days / turnover_ratio
        if turnover_ratio > 0:
            days_to_sell = period_days / turnover_ratio
        else:
            days_to_sell = None  # infinite / no sales

        # Daily sales rate
        daily_rate = units_sold / period_days if period_days > 0 else 0

        # Days of stock remaining
        if daily_rate > 0:
            days_remaining = current_stock / daily_rate
        else:
            days_remaining = None

        # Classify speed
        if units_sold == 0:
            speed = 'dead'
            turnover_buckets['dead'] += 1
        elif turnover_ratio >= 4:
            speed = 'fast'
            turnover_buckets['fast'] += 1
        elif turnover_ratio >= 1:
            speed = 'normal'
            turnover_buckets['normal'] += 1
        else:
            speed = 'slow'
            turnover_buckets['slow'] += 1

        product_data.append({
            'product': p,
            'category_name': p.category.name if p.category else 'Uncategorized',
            'current_stock': current_stock,
            'stock_value': stock_value,
            'units_sold': units_sold,
            'revenue': sale_info['revenue'],
            'cogs': cogs,
            'turnover_ratio': round(turnover_ratio, 2),
            'days_to_sell': round(days_to_sell, 1) if days_to_sell else None,
            'daily_rate': round(daily_rate, 2),
            'days_remaining': round(days_remaining, 1) if days_remaining else None,
            'speed': speed,
        })

    # Apply speed filter
    if speed_filter:
        product_data = [d for d in product_data if d['speed'] == speed_filter]

    # Apply stock filter
    if stock_filter == 'out_of_stock':
        product_data = [d for d in product_data if d['current_stock'] == 0]
    elif stock_filter == 'in_stock':
        product_data = [d for d in product_data if d['current_stock'] > 0]
    elif stock_filter == 'low_stock':
        product_data = [d for d in product_data if 0 < d['current_stock'] <= (d['product'].reorder_level or 10)]

    # Apply min stock value filter
    if min_value > 0:
        product_data = [d for d in product_data if d['stock_value'] >= min_value]

    # Sort
    sort_options = {
        'turnover_desc': lambda x: (-x['turnover_ratio'], x['product'].name),
        'turnover_asc': lambda x: (x['turnover_ratio'], x['product'].name),
        'revenue_desc': lambda x: -x['revenue'],
        'revenue_asc': lambda x: x['revenue'],
        'stock_value_desc': lambda x: -x['stock_value'],
        'stock_value_asc': lambda x: x['stock_value'],
        'units_sold_desc': lambda x: -x['units_sold'],
        'units_sold_asc': lambda x: x['units_sold'],
        'days_remaining_asc': lambda x: (x['days_remaining'] is None, x['days_remaining'] or 0),
        'days_remaining_desc': lambda x: (x['days_remaining'] is not None, -(x['days_remaining'] or 0)),
        'daily_rate_desc': lambda x: -x['daily_rate'],
        'name_asc': lambda x: x['product'].name.lower(),
        'name_desc': lambda x: x['product'].name.lower(),
        'category_asc': lambda x: (x['category_name'].lower(), x['product'].name.lower()),
    }
    sort_fn = sort_options.get(sort_by, sort_options['turnover_desc'])
    reverse = sort_by == 'name_desc'
    product_data.sort(key=sort_fn, reverse=reverse)

    # Overall turnover
    overall_turnover = total_cogs / total_stock_value if total_stock_value > 0 else 0

    return render_template('reports/inventory_turnover.html',
                         locations=locations,
                         categories=categories,
                         selected_location_id=location_id,
                         selected_category_id=category_id,
                         user_location=user_location,
                         period_days=period_days,
                         speed_filter=speed_filter,
                         sort_by=sort_by,
                         search=search,
                         stock_filter=stock_filter,
                         min_value=min_value,
                         product_data=product_data,
                         total_stock_value=total_stock_value,
                         total_cogs=total_cogs,
                         overall_turnover=round(overall_turnover, 2),
                         turnover_buckets=turnover_buckets,
                         start_date=start_date,
                         end_date=end_date)


@bp.route('/abc-analysis')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def abc_analysis():
    """ABC Analysis - classify products by revenue contribution"""
    from app.models import Category
    from app.utils.location_context import get_current_location

    user_location = get_current_location()
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    categories = Category.query.order_by(Category.name).all()

    # Filters
    location_id = request.args.get('location_id', type=int)
    period_days = request.args.get('period', 90, type=int)
    category_id = request.args.get('category_id', type=int)
    class_filter = request.args.get('class_filter', '')  # A, B, C
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'revenue_desc')
    show_zero = request.args.get('show_zero', '1') == '1'

    if current_user.is_global_admin:
        effective_location_id = location_id
    elif user_location:
        effective_location_id = user_location.id
    else:
        effective_location_id = None

    end_date = datetime.now()
    start_date = end_date - timedelta(days=period_days)

    # Sales revenue per product
    sales_query = db.session.query(
        SaleItem.product_id,
        func.sum(SaleItem.quantity).label('units_sold'),
        func.sum(SaleItem.subtotal).label('revenue'),
        func.count(func.distinct(Sale.id)).label('transaction_count'),
    ).select_from(SaleItem).join(Sale).filter(
        Sale.sale_date >= start_date,
        Sale.sale_date <= end_date,
        Sale.status == 'completed'
    )

    if effective_location_id:
        sales_query = sales_query.filter(Sale.location_id == effective_location_id)

    sales_rows = sales_query.group_by(SaleItem.product_id).all()

    # Build product list with revenue
    product_list = []
    total_revenue = 0

    for row in sales_rows:
        product = Product.query.get(row.product_id)
        if not product or not product.is_active:
            continue
        if category_id and product.category_id != category_id:
            continue
        if search and search.lower() not in product.name.lower() and search.lower() not in (product.code or '').lower():
            continue

        revenue = float(row.revenue or 0)
        units = int(row.units_sold or 0)
        cost_price = float(product.cost_price or 0)

        # Current stock
        if effective_location_id:
            ls = LocationStock.query.filter_by(product_id=product.id, location_id=effective_location_id).first()
            current_stock = ls.quantity if ls else 0
        else:
            current_stock = product.quantity or 0

        stock_value = current_stock * cost_price

        product_list.append({
            'product': product,
            'category_name': product.category.name if product.category else 'Uncategorized',
            'revenue': revenue,
            'units_sold': units,
            'transactions': int(row.transaction_count or 0),
            'current_stock': current_stock,
            'stock_value': stock_value,
            'cost_price': cost_price,
            'profit': revenue - (units * cost_price),
        })
        total_revenue += revenue

    # Also add products with zero sales
    if show_zero:
        sold_product_ids = {row.product_id for row in sales_rows}
        zero_query = Product.query.filter(Product.is_active == True)
        if sold_product_ids:
            zero_query = zero_query.filter(~Product.id.in_(sold_product_ids))
        if category_id:
            zero_query = zero_query.filter_by(category_id=category_id)
        if search:
            zero_query = zero_query.filter(
                db.or_(Product.name.ilike(f'%{search}%'), Product.code.ilike(f'%{search}%'))
            )
        zero_sale_products = zero_query.all()
    else:
        zero_sale_products = []

    for product in zero_sale_products:
        cost_price = float(product.cost_price or 0)
        if effective_location_id:
            ls = LocationStock.query.filter_by(product_id=product.id, location_id=effective_location_id).first()
            current_stock = ls.quantity if ls else 0
        else:
            current_stock = product.quantity or 0

        product_list.append({
            'product': product,
            'category_name': product.category.name if product.category else 'Uncategorized',
            'revenue': 0,
            'units_sold': 0,
            'transactions': 0,
            'current_stock': current_stock,
            'stock_value': current_stock * cost_price,
            'cost_price': cost_price,
            'profit': 0,
        })

    # Sort by revenue descending
    product_list.sort(key=lambda x: -x['revenue'])

    # Assign ABC class based on cumulative revenue
    cumulative = 0
    for item in product_list:
        if total_revenue > 0:
            cumulative += item['revenue']
            pct = (cumulative / total_revenue) * 100
            item['cumulative_pct'] = round(pct, 1)
            item['revenue_pct'] = round((item['revenue'] / total_revenue) * 100, 1)

            if pct <= 80:
                item['abc_class'] = 'A'
            elif pct <= 95:
                item['abc_class'] = 'B'
            else:
                item['abc_class'] = 'C'
        else:
            item['cumulative_pct'] = 0
            item['revenue_pct'] = 0
            item['abc_class'] = 'C'

    # Summary by class (before filtering by class)
    class_summary = {}
    for cls in ['A', 'B', 'C']:
        items = [i for i in product_list if i['abc_class'] == cls]
        class_summary[cls] = {
            'count': len(items),
            'revenue': sum(i['revenue'] for i in items),
            'units': sum(i['units_sold'] for i in items),
            'stock_value': sum(i['stock_value'] for i in items),
            'profit': sum(i['profit'] for i in items),
            'pct_items': round(len(items) / len(product_list) * 100, 1) if product_list else 0,
            'pct_revenue': round(sum(i['revenue'] for i in items) / total_revenue * 100, 1) if total_revenue > 0 else 0,
        }

    # Apply class filter after summary calculation
    if class_filter:
        product_list = [i for i in product_list if i['abc_class'] == class_filter]

    # Apply sort (ABC always starts sorted by revenue desc for classification, but user can re-sort)
    abc_sort_options = {
        'revenue_desc': lambda x: -x['revenue'],
        'revenue_asc': lambda x: x['revenue'],
        'units_desc': lambda x: -x['units_sold'],
        'units_asc': lambda x: x['units_sold'],
        'stock_value_desc': lambda x: -x['stock_value'],
        'stock_value_asc': lambda x: x['stock_value'],
        'profit_desc': lambda x: -x['profit'],
        'profit_asc': lambda x: x['profit'],
        'name_asc': lambda x: x['product'].name.lower(),
        'name_desc': lambda x: x['product'].name.lower(),
        'transactions_desc': lambda x: -x['transactions'],
        'category_asc': lambda x: (x['category_name'].lower(), x['product'].name.lower()),
    }
    sort_fn = abc_sort_options.get(sort_by, abc_sort_options['revenue_desc'])
    reverse = sort_by == 'name_desc'
    product_list.sort(key=sort_fn, reverse=reverse)

    return render_template('reports/abc_analysis.html',
                         locations=locations,
                         categories=categories,
                         selected_location_id=location_id,
                         selected_category_id=category_id,
                         user_location=user_location,
                         period_days=period_days,
                         class_filter=class_filter,
                         search=search,
                         sort_by=sort_by,
                         show_zero=show_zero,
                         product_list=product_list,
                         total_revenue=total_revenue,
                         class_summary=class_summary,
                         start_date=start_date,
                         end_date=end_date)


@bp.route('/stock-accuracy-trend')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def stock_accuracy_trend():
    """Stock accuracy trend from spot check data over time"""
    from app.models import InventorySpotCheck, InventorySpotCheckItem
    from app.utils.location_context import get_current_location

    user_location = get_current_location()
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    # Filters
    location_id = request.args.get('location_id', type=int)
    period_days = request.args.get('period', 180, type=int)  # 6 months default
    group_by = request.args.get('group_by', 'week')  # week or month
    check_type = request.args.get('check_type', '')  # daily, weekly, fortnightly, monthly, random
    status_filter = request.args.get('status_filter', '')  # completed, approved
    sort_worst = request.args.get('sort_worst', 'value_desc')  # value_desc, rate_desc, count_desc

    if current_user.is_global_admin:
        effective_location_id = location_id
    elif user_location:
        effective_location_id = user_location.id
    else:
        effective_location_id = None

    end_date = datetime.now()
    start_date = end_date - timedelta(days=period_days)

    # Get spot checks in period
    status_list = [status_filter] if status_filter else ['completed', 'approved']
    checks_query = InventorySpotCheck.query.filter(
        InventorySpotCheck.check_date >= start_date.date(),
        InventorySpotCheck.check_date <= end_date.date(),
        InventorySpotCheck.status.in_(status_list)
    )

    if effective_location_id:
        checks_query = checks_query.filter(InventorySpotCheck.location_id == effective_location_id)
    if check_type:
        checks_query = checks_query.filter(InventorySpotCheck.check_type == check_type)

    checks = checks_query.order_by(InventorySpotCheck.check_date).all()

    # ===== Trend data by period =====
    from collections import defaultdict
    trend_data = defaultdict(lambda: {
        'total_checked': 0, 'total_matched': 0, 'total_variance': 0,
        'checks_count': 0, 'variance_value': 0
    })

    for check in checks:
        if group_by == 'month':
            period_key = check.check_date.strftime('%Y-%m')
            period_label = check.check_date.strftime('%b %Y')
        else:
            # Week: use ISO week
            iso = check.check_date.isocalendar()
            period_key = f'{iso[0]}-W{iso[1]:02d}'
            period_label = period_key

        trend_data[period_key]['label'] = period_label
        trend_data[period_key]['total_checked'] += check.total_items_checked or 0
        trend_data[period_key]['total_matched'] += check.items_matched or 0
        trend_data[period_key]['total_variance'] += check.items_variance or 0
        trend_data[period_key]['checks_count'] += 1
        trend_data[period_key]['variance_value'] += float(check.total_variance_value or 0)

    # Calculate accuracy percentages
    trend_list = []
    for key in sorted(trend_data.keys()):
        d = trend_data[key]
        accuracy = (d['total_matched'] / d['total_checked'] * 100) if d['total_checked'] > 0 else 100
        trend_list.append({
            'period': key,
            'label': d['label'],
            'total_checked': d['total_checked'],
            'total_matched': d['total_matched'],
            'total_variance': d['total_variance'],
            'checks_count': d['checks_count'],
            'accuracy_pct': round(accuracy, 1),
            'variance_value': round(d['variance_value'], 2),
        })

    # ===== Product-level variance analysis =====
    # Find products with most recurring variances
    item_query = db.session.query(
        InventorySpotCheckItem.product_id,
        func.count(InventorySpotCheckItem.id).label('check_count'),
        func.sum(case(
            (InventorySpotCheckItem.variance != 0, 1),
            else_=0
        )).label('variance_count'),
        func.sum(func.abs(InventorySpotCheckItem.variance)).label('total_abs_variance'),
        func.sum(func.abs(InventorySpotCheckItem.variance_value)).label('total_abs_value'),
    ).join(InventorySpotCheck).filter(
        InventorySpotCheck.check_date >= start_date.date(),
        InventorySpotCheck.check_date <= end_date.date(),
        InventorySpotCheck.status.in_(status_list),
        InventorySpotCheckItem.product_id.isnot(None)
    )

    if effective_location_id:
        item_query = item_query.filter(InventorySpotCheck.location_id == effective_location_id)
    if check_type:
        item_query = item_query.filter(InventorySpotCheck.check_type == check_type)

    # Sort order for worst products
    worst_sort_map = {
        'value_desc': func.sum(func.abs(InventorySpotCheckItem.variance_value)).desc(),
        'rate_desc': (func.sum(case((InventorySpotCheckItem.variance != 0, 1), else_=0)) * 100 / func.count(InventorySpotCheckItem.id)).desc(),
        'count_desc': func.sum(case((InventorySpotCheckItem.variance != 0, 1), else_=0)).desc(),
        'variance_desc': func.sum(func.abs(InventorySpotCheckItem.variance)).desc(),
    }
    worst_order = worst_sort_map.get(sort_worst, worst_sort_map['value_desc'])

    worst_products = []
    for row in item_query.group_by(InventorySpotCheckItem.product_id).having(
        func.sum(case((InventorySpotCheckItem.variance != 0, 1), else_=0)) > 0
    ).order_by(worst_order).limit(20).all():
        product = Product.query.get(row.product_id)
        if product:
            checks_with_variance = int(row.variance_count or 0)
            total_checks = int(row.check_count or 0)
            worst_products.append({
                'product': product,
                'check_count': total_checks,
                'variance_count': checks_with_variance,
                'variance_rate': round(checks_with_variance / total_checks * 100, 1) if total_checks > 0 else 0,
                'total_abs_variance': float(row.total_abs_variance or 0),
                'total_abs_value': float(row.total_abs_value or 0),
            })

    # ===== Variance reason breakdown =====
    reason_query = db.session.query(
        InventorySpotCheckItem.variance_reason,
        func.count(InventorySpotCheckItem.id).label('count'),
        func.sum(func.abs(InventorySpotCheckItem.variance_value)).label('total_value'),
    ).join(InventorySpotCheck).filter(
        InventorySpotCheck.check_date >= start_date.date(),
        InventorySpotCheck.check_date <= end_date.date(),
        InventorySpotCheck.status.in_(status_list),
        InventorySpotCheckItem.variance != 0
    )

    if effective_location_id:
        reason_query = reason_query.filter(InventorySpotCheck.location_id == effective_location_id)
    if check_type:
        reason_query = reason_query.filter(InventorySpotCheck.check_type == check_type)

    reason_breakdown = []
    for row in reason_query.group_by(InventorySpotCheckItem.variance_reason).all():
        reason_breakdown.append({
            'reason': row.variance_reason or 'Not specified',
            'count': int(row.count or 0),
            'total_value': float(row.total_value or 0),
        })
    reason_breakdown.sort(key=lambda x: -x['total_value'])

    # ===== Location comparison =====
    location_accuracy = []
    if current_user.is_global_admin and not effective_location_id:
        loc_query = db.session.query(
            InventorySpotCheck.location_id,
            func.sum(InventorySpotCheck.total_items_checked).label('checked'),
            func.sum(InventorySpotCheck.items_matched).label('matched'),
            func.sum(InventorySpotCheck.items_variance).label('variance'),
            func.sum(InventorySpotCheck.total_variance_value).label('variance_value'),
            func.count(InventorySpotCheck.id).label('checks_count'),
        ).filter(
            InventorySpotCheck.check_date >= start_date.date(),
            InventorySpotCheck.check_date <= end_date.date(),
            InventorySpotCheck.status.in_(status_list)
        )
        if check_type:
            loc_query = loc_query.filter(InventorySpotCheck.check_type == check_type)
        loc_query = loc_query.group_by(InventorySpotCheck.location_id).all()

        for row in loc_query:
            loc = Location.query.get(row.location_id)
            if loc:
                checked = int(row.checked or 0)
                matched = int(row.matched or 0)
                accuracy = (matched / checked * 100) if checked > 0 else 100
                location_accuracy.append({
                    'location': loc,
                    'checks_count': int(row.checks_count or 0),
                    'total_checked': checked,
                    'total_matched': matched,
                    'accuracy_pct': round(accuracy, 1),
                    'variance_value': float(row.variance_value or 0),
                })

    # Overall stats
    overall_checked = sum(c.total_items_checked or 0 for c in checks)
    overall_matched = sum(c.items_matched or 0 for c in checks)
    overall_accuracy = (overall_matched / overall_checked * 100) if overall_checked > 0 else 100
    overall_variance_value = sum(float(c.total_variance_value or 0) for c in checks)

    return render_template('reports/stock_accuracy_trend.html',
                         locations=locations,
                         selected_location_id=location_id,
                         user_location=user_location,
                         period_days=period_days,
                         group_by=group_by,
                         check_type=check_type,
                         status_filter=status_filter,
                         sort_worst=sort_worst,
                         trend_list=trend_list,
                         worst_products=worst_products,
                         reason_breakdown=reason_breakdown,
                         location_accuracy=location_accuracy,
                         overall_checks=len(checks),
                         overall_checked=overall_checked,
                         overall_matched=overall_matched,
                         overall_accuracy=round(overall_accuracy, 1),
                         overall_variance_value=round(overall_variance_value, 2),
                         start_date=start_date,
                         end_date=end_date)
