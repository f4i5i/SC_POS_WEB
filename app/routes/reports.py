"""
Reports and Analytics Routes
Handles generation and display of various business reports
"""

from flask import Blueprint, render_template, request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_, extract, case
from app.models import db, Sale, SaleItem, Product, Customer, StockMovement, Location, LocationStock, ProductionOrder, RawMaterialStock, RawMaterial, RawMaterialMovement, RawMaterialCategory, PurchaseOrder, PurchaseOrderItem, StockTransfer, StockTransferItem, DayClose
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

    # Build query with location filter - include both completed and refunded
    query = Sale.query.filter(
        and_(
            func.date(Sale.sale_date) == report_date,
            Sale.status.in_(['completed', 'refunded'])
        )
    )

    # Filter by location for non-global admins
    user_location = None
    if not current_user.is_global_admin:
        if current_user.location_id:
            query = query.filter(Sale.location_id == current_user.location_id)
            user_location = Location.query.get(current_user.location_id)
        else:
            query = query.filter(False)  # No location = no data

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
    if not current_user.is_global_admin and current_user.location_id:
        top_products_query = top_products_query.filter(Sale.location_id == current_user.location_id)
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
    if not current_user.is_global_admin and current_user.location_id:
        hourly_sales_query = hourly_sales_query.filter(Sale.location_id == current_user.location_id)
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
    if not current_user.is_global_admin and current_user.location_id:
        # Get low stock for this location
        location_stock = LocationStock.query.filter(
            LocationStock.location_id == current_user.location_id,
            LocationStock.quantity <= LocationStock.reorder_level,
            LocationStock.quantity > 0
        ).all()
        low_stock = [ls.product for ls in location_stock if ls.product]
        out_of_stock_ls = LocationStock.query.filter(
            LocationStock.location_id == current_user.location_id,
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
                         user_location=user_location)


@bp.route('/weekly')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def weekly_report():
    """Weekly sales comparison report - filtered by location"""
    from app.models import Location

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

    # Filter by location for non-global admins
    user_location = None
    if not current_user.is_global_admin:
        if current_user.location_id:
            current_query = current_query.filter(Sale.location_id == current_user.location_id)
            user_location = Location.query.get(current_user.location_id)
        else:
            current_query = current_query.filter(False)

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
    if not current_user.is_global_admin and current_user.location_id:
        prev_query = prev_query.filter(Sale.location_id == current_user.location_id)
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
    if not current_user.is_global_admin and current_user.location_id:
        daily_query = daily_query.filter(Sale.location_id == current_user.location_id)
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
                         user_location=user_location)


@bp.route('/monthly')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def monthly_report():
    """Monthly comprehensive report - filtered by location"""
    from app.models import Location

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

    # Filter by location for non-global admins
    user_location = None
    if not current_user.is_global_admin:
        if current_user.location_id:
            query = query.filter(Sale.location_id == current_user.location_id)
            user_location = Location.query.get(current_user.location_id)
        else:
            query = query.filter(False)

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
    if not current_user.is_global_admin and current_user.location_id:
        category_query = category_query.filter(Sale.location_id == current_user.location_id)
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
    if not current_user.is_global_admin and current_user.location_id:
        customers_query = customers_query.filter(Sale.location_id == current_user.location_id)
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
                         user_location=user_location)


@bp.route('/custom')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def custom_report():
    """Custom date range report - filtered by location"""
    from app.models import Location

    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    # Get user location for display
    user_location = None
    if not current_user.is_global_admin and current_user.location_id:
        user_location = Location.query.get(current_user.location_id)

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
        if not current_user.is_global_admin and current_user.location_id:
            product_query = product_query.filter(Sale.location_id == current_user.location_id)
        product_performance = product_query.group_by(Product.id).order_by(func.sum(SaleItem.subtotal).desc()).all()

        return render_template('reports/custom_report.html',
                             from_date=from_date,
                             to_date=to_date,
                             total_sales=total_sales,
                             total_transactions=total_transactions,
                             product_performance=product_performance,
                             user_location=user_location)

    return render_template('reports/custom_report.html', user_location=user_location)


@bp.route('/inventory-valuation')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def inventory_valuation():
    """Stock valuation report"""
    products = Product.query.filter_by(is_active=True).all()

    total_cost_value = sum(float(p.cost_price) * p.quantity for p in products)
    total_selling_value = sum(float(p.selling_price) * p.quantity for p in products)
    potential_profit = total_selling_value - total_cost_value

    return render_template('reports/inventory_valuation.html',
                         products=products,
                         total_cost_value=total_cost_value,
                         total_selling_value=total_selling_value,
                         potential_profit=potential_profit)


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
    if not current_user.is_global_admin and current_user.location_id:
        user_location = Location.query.get(current_user.location_id)

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

    # Add location filter for non-global admins
    if not current_user.is_global_admin and current_user.location_id:
        base_filter = and_(base_filter, Sale.location_id == current_user.location_id)

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
    total_revenue = sum(emp.total_revenue or 0 for emp in employee_stats)
    total_sales_count = sum(emp.total_sales or 0 for emp in employee_stats)

    return render_template('reports/employee_performance.html',
                         start_date=start_date,
                         end_date=end_date,
                         employee_stats=employee_stats,
                         total_revenue=total_revenue,
                         total_sales_count=total_sales_count,
                         user_location=user_location)


@bp.route('/product-performance')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def product_performance():
    """Product performance analysis - filtered by location"""
    from app.models import Location

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
    if not current_user.is_global_admin and current_user.location_id:
        user_location = Location.query.get(current_user.location_id)

    # Build base filter
    base_filter = and_(
        Sale.sale_date >= start_date,
        Sale.sale_date <= end_date,
        Sale.status == 'completed'
    )
    # Add location filter for non-global admins
    if not current_user.is_global_admin and current_user.location_id:
        base_filter = and_(base_filter, Sale.location_id == current_user.location_id)

    # Top performing products
    top_products = db.session.query(
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
    ).filter(base_filter).group_by(Product.id).order_by(func.sum(SaleItem.subtotal).desc()).limit(20).all()

    # Worst performing products (sold but low revenue)
    worst_products = db.session.query(
        Product.name,
        Product.code,
        Product.brand,
        func.sum(SaleItem.quantity).label('units_sold'),
        func.sum(SaleItem.subtotal).label('revenue')
    ).select_from(Product).join(
        SaleItem, SaleItem.product_id == Product.id
    ).join(
        Sale, Sale.id == SaleItem.sale_id
    ).filter(base_filter).group_by(Product.id).order_by(func.sum(SaleItem.subtotal).asc()).limit(10).all()

    # Never sold products - also filter by location
    sold_product_ids = db.session.query(func.distinct(SaleItem.product_id)).join(Sale).filter(
        base_filter
    ).subquery()

    never_sold = Product.query.filter(
        ~Product.id.in_(sold_product_ids),
        Product.is_active == True
    ).limit(20).all()

    return render_template('reports/product_performance.html',
                         start_date=start_date,
                         end_date=end_date,
                         top_products=top_products,
                         worst_products=worst_products,
                         never_sold=never_sold,
                         user_location=user_location)


@bp.route('/sales-by-category')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def sales_by_category():
    """Sales breakdown by product category - filtered by location"""
    from app.models import Category, Location

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
    if not current_user.is_global_admin and current_user.location_id:
        user_location = Location.query.get(current_user.location_id)

    # Build base filter
    base_filter = and_(
        Sale.sale_date >= start_date,
        Sale.sale_date <= end_date,
        Sale.status == 'completed'
    )
    # Add location filter for non-global admins
    if not current_user.is_global_admin and current_user.location_id:
        base_filter = and_(base_filter, Sale.location_id == current_user.location_id)

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
                         user_location=user_location)


@bp.route('/profit-loss')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def profit_loss():
    """Profit and Loss (P&L) statement with daily/weekly/monthly presets"""
    from app.models import Location
    from calendar import monthrange

    # Get period type: daily, weekly, monthly, custom
    period = request.args.get('period', 'daily')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    today = datetime.now()

    # Determine date range based on period
    if period == 'daily':
        # Single day - today or specified date
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        else:
            start_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date.replace(hour=23, minute=59, second=59)
        period_label = start_date.strftime('%B %d, %Y')

    elif period == 'weekly':
        # Current week (Monday to Sunday)
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        else:
            start_date = today - timedelta(days=today.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=6)
        end_date = end_date.replace(hour=23, minute=59, second=59)
        period_label = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"

    elif period == 'monthly':
        # Current month or specified month
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
    location_filter = True  # Default: no filter
    if not current_user.is_global_admin:
        if current_user.location_id:
            location_filter = Sale.location_id == current_user.location_id
            user_location = Location.query.get(current_user.location_id)
        else:
            location_filter = False

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
    if not current_user.is_global_admin and current_user.location_id:
        cogs_query = cogs_query.filter(Sale.location_id == current_user.location_id)
    cogs = float(cogs_query.scalar() or 0)

    # ===== GROSS PROFIT =====
    gross_profit = net_revenue - cogs
    gross_margin = (gross_profit / net_revenue * 100) if net_revenue > 0 else 0

    # ===== GROWTH SHARE (20% of Gross Profit) =====
    growth_share_percent = 20  # Can be made configurable later
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
        if not current_user.is_global_admin and current_user.location_id:
            expense_query = expense_query.filter(Expense.location_id == current_user.location_id)

        expenses = expense_query.all()
        total_expenses = sum(float(exp.amount or 0) for exp in expenses)

        # Expenses by category
        expense_by_category = db.session.query(
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
        if not current_user.is_global_admin and current_user.location_id:
            expense_by_category = expense_by_category.filter(Expense.location_id == current_user.location_id)
        expense_by_category = expense_by_category.group_by(ExpenseCategory.id).all()
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
    if not current_user.is_global_admin and current_user.location_id:
        top_products_query = top_products_query.filter(Sale.location_id == current_user.location_id)
    top_products = top_products_query.group_by(Product.id).order_by(
        func.sum((SaleItem.unit_price - Product.cost_price) * SaleItem.quantity).desc()
    ).limit(10).all()

    # ===== COMPARISON WITH PREVIOUS PERIOD =====
    period_duration = (end_date - start_date).days + 1
    prev_start = start_date - timedelta(days=period_duration)
    prev_end = start_date - timedelta(seconds=1)

    prev_query = Sale.query.filter(
        and_(
            Sale.sale_date >= prev_start,
            Sale.sale_date <= prev_end,
            Sale.status == 'completed'
        )
    )
    if not current_user.is_global_admin and current_user.location_id:
        prev_query = prev_query.filter(Sale.location_id == current_user.location_id)
    prev_sales = prev_query.all()
    prev_revenue = sum(float(s.total or 0) for s in prev_sales)

    revenue_change = 0
    if prev_revenue > 0:
        revenue_change = ((net_revenue - prev_revenue) / prev_revenue) * 100

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
                         # Comparison
                         prev_revenue=prev_revenue,
                         revenue_change=revenue_change,
                         # Location
                         user_location=user_location)


@bp.route('/customer-analysis')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def customer_analysis():
    """Customer purchase behavior analysis - filtered by location"""
    from app.models import Location

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
    if not current_user.is_global_admin and current_user.location_id:
        user_location = Location.query.get(current_user.location_id)

    # Build base filter for sales
    base_filter = and_(
        Sale.sale_date >= start_date,
        Sale.sale_date <= end_date,
        Sale.status == 'completed'
    )
    # Add location filter for non-global admins
    if not current_user.is_global_admin and current_user.location_id:
        base_filter = and_(base_filter, Sale.location_id == current_user.location_id)

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
    ).filter(base_filter).group_by(Customer.id).order_by(func.sum(Sale.total).desc()).limit(20).all()

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
                         user_location=user_location)


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
                    cost_val = float(stock.quantity) * float(stock.product.cost_price or 0)
                    sell_val = float(stock.quantity) * float(stock.product.selling_price or 0)
                    location_stock_details.append({
                        'product': stock.product,
                        'quantity': stock.quantity,
                        'cost_price': float(stock.product.cost_price or 0),
                        'selling_price': float(stock.product.selling_price or 0),
                        'cost_value': cost_val,
                        'selling_value': sell_val,
                        'profit': sell_val - cost_val
                    })

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
                         raw_material_value=float(raw_material_value))


@bp.route('/stock-reconciliation')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def stock_reconciliation():
    """Stock Reconciliation Report - Compare expected vs actual stock"""
    from datetime import date

    # Get filters
    selected_location_id = request.args.get('location_id', type=int)
    from_date_str = request.args.get('from_date')
    to_date_str = request.args.get('to_date')

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

    # Build reconciliation data
    reconciliation_data = []
    total_expected = 0
    total_actual = 0
    total_variance = 0
    total_variance_value = 0

    # Get products with stock
    products_query = Product.query.filter_by(is_active=True)
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
            # Sum across all locations
            current_qty = db.session.query(func.sum(LocationStock.quantity)).filter_by(
                product_id=product.id
            ).scalar() or 0

        # Calculate expected stock from movements in date range
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
        production_in = sum(m.quantity for m in movements if m.movement_type == 'production' and m.quantity > 0)
        returns_in = sum(m.quantity for m in movements if m.movement_type == 'return' and m.quantity > 0)
        damage_out = abs(sum(m.quantity for m in movements if m.movement_type == 'damage' and m.quantity < 0))

        # Calculate net movement
        net_in = purchases_in + transfers_in + production_in + returns_in + (adjustments if adjustments > 0 else 0)
        net_out = sales_out + transfers_out + damage_out + (abs(adjustments) if adjustments < 0 else 0)

        # Only include products with activity or stock
        if current_qty > 0 or net_in > 0 or net_out > 0:
            # Variance (positive = excess, negative = shortage)
            # Note: Without opening balance tracking, we show movement summary
            variance = 0  # Would need opening balance to calculate true variance
            variance_value = variance * float(product.cost_price or 0)

            reconciliation_data.append({
                'product': product,
                'current_stock': current_qty,
                'purchases_in': purchases_in,
                'sales_out': sales_out,
                'adjustments': adjustments,
                'transfers_in': transfers_in,
                'transfers_out': transfers_out,
                'production_in': production_in,
                'returns_in': returns_in,
                'damage_out': damage_out,
                'net_in': net_in,
                'net_out': net_out,
                'stock_value': float(current_qty) * float(product.cost_price or 0)
            })

            total_actual += current_qty

    # Get purchase summary for the period
    purchase_query = PurchaseOrder.query.filter(
        PurchaseOrder.order_date >= from_date,
        PurchaseOrder.order_date <= to_date,
        PurchaseOrder.status.in_(['received', 'partial'])
    )
    purchase_summary = {
        'total_orders': purchase_query.count(),
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

    # Get sales summary for the period
    sales_query = Sale.query.filter(
        Sale.sale_date >= datetime.combine(from_date, datetime.min.time()),
        Sale.sale_date <= datetime.combine(to_date, datetime.max.time()),
        Sale.status == 'completed'
    )
    if selected_location_id:
        sales_query = sales_query.filter_by(location_id=selected_location_id)

    sales_summary = {
        'total_transactions': sales_query.count(),
        'total_revenue': db.session.query(func.sum(Sale.total)).filter(
            Sale.sale_date >= datetime.combine(from_date, datetime.min.time()),
            Sale.sale_date <= datetime.combine(to_date, datetime.max.time()),
            Sale.status == 'completed'
        ).scalar() or 0
    }

    selected_location = Location.query.get(selected_location_id) if selected_location_id else None

    return render_template('reports/stock_reconciliation.html',
                         locations=locations,
                         selected_location=selected_location,
                         selected_location_id=selected_location_id,
                         from_date=from_date,
                         to_date=to_date,
                         reconciliation_data=reconciliation_data,
                         total_actual=total_actual,
                         purchase_summary=purchase_summary,
                         sales_summary=sales_summary)


@bp.route('/purchase-register')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def purchase_register():
    """Purchase Register - All purchases with payment status"""
    from_date_str = request.args.get('from_date')
    to_date_str = request.args.get('to_date')
    payment_status = request.args.get('payment_status')
    supplier_id = request.args.get('supplier_id', type=int)

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

    purchases = query.order_by(PurchaseOrder.order_date.desc()).all()

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

    return render_template('reports/purchase_register.html',
                         purchases=purchases,
                         totals=totals,
                         suppliers=suppliers,
                         from_date=from_date,
                         to_date=to_date,
                         selected_payment_status=payment_status,
                         selected_supplier_id=supplier_id)


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
                         selected_movement_type=movement_type)


@bp.route('/transfer-discrepancy')
@login_required
@permission_required(Permissions.REPORT_VIEW_INVENTORY)
def transfer_discrepancy():
    """Transfer Discrepancy Report - Shows variances in stock transfers"""
    from_date_str = request.args.get('from_date')
    to_date_str = request.args.get('to_date')
    show_only_discrepancies = request.args.get('discrepancies_only', 'false') == 'true'

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
    transfers = StockTransfer.query.filter(
        StockTransfer.created_at >= datetime.combine(from_date, datetime.min.time()),
        StockTransfer.created_at <= datetime.combine(to_date, datetime.max.time()),
        StockTransfer.status == 'received'
    ).order_by(StockTransfer.created_at.desc()).all()

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

    return render_template('reports/transfer_discrepancy.html',
                         transfer_data=transfer_data,
                         total_discrepancies=total_discrepancies,
                         total_discrepancy_value=total_discrepancy_value,
                         from_date=from_date,
                         to_date=to_date,
                         show_only_discrepancies=show_only_discrepancies)


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
            category_summary[cat] = {'stock_value': 0, 'purchased_value': 0, 'consumed_value': 0, 'items': 0}
        category_summary[cat]['stock_value'] += item['stock_value']
        category_summary[cat]['purchased_value'] += item['purchased_value']
        category_summary[cat]['consumed_value'] += item['consumed_value']
        category_summary[cat]['items'] += 1

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
                         production_summary=production_summary)
