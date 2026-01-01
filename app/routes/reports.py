"""
Reports and Analytics Routes
Handles generation and display of various business reports
"""

from flask import Blueprint, render_template, request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_, extract, case
from app.models import db, Sale, SaleItem, Product, Customer, StockMovement
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

    # Build query with location filter
    query = Sale.query.filter(
        and_(
            func.date(Sale.sale_date) == report_date,
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
            query = query.filter(False)  # No location = no data

    # Get sales for the day
    sales = query.all()

    # Calculate summary
    total_sales = sum(sale.total for sale in sales)
    total_transactions = len(sales)
    avg_transaction = total_sales / total_transactions if total_transactions > 0 else 0

    # Payment method breakdown
    payment_methods = {}
    for sale in sales:
        method = sale.payment_method
        if method not in payment_methods:
            payment_methods[method] = 0
        payment_methods[method] += float(sale.total)

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
    top_products = top_products_query.group_by(Product.id).order_by(func.sum(SaleItem.quantity).desc()).limit(10).all()

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
    hourly_sales = hourly_sales_query.group_by(extract('hour', Sale.sale_date)).all()

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
                         sales=sales,
                         total_sales=total_sales,
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
    """Weekly sales comparison report"""
    # Get week ending date
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=7)

    # Sales for current week
    current_week_sales = Sale.query.filter(
        and_(
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
            Sale.status == 'completed'
        )
    ).all()

    # Sales for previous week
    prev_end_date = start_date - timedelta(days=1)
    prev_start_date = prev_end_date - timedelta(days=7)
    previous_week_sales = Sale.query.filter(
        and_(
            Sale.sale_date >= prev_start_date,
            Sale.sale_date <= prev_end_date,
            Sale.status == 'completed'
        )
    ).all()

    # Calculate metrics
    current_total = sum(sale.total for sale in current_week_sales)
    previous_total = sum(sale.total for sale in previous_week_sales)

    change_percent = 0
    if previous_total > 0:
        change_percent = ((current_total - previous_total) / previous_total) * 100

    # Daily breakdown
    daily_sales = db.session.query(
        func.date(Sale.sale_date).label('date'),
        func.count(Sale.id).label('count'),
        func.sum(Sale.total).label('total')
    ).filter(
        and_(
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
            Sale.status == 'completed'
        )
    ).group_by(func.date(Sale.sale_date)).all()

    return render_template('reports/weekly_report.html',
                         start_date=start_date,
                         end_date=end_date,
                         current_total=current_total,
                         previous_total=previous_total,
                         change_percent=change_percent,
                         daily_sales=daily_sales)


@bp.route('/monthly')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def monthly_report():
    """Monthly comprehensive report"""
    # Get month from request or use current month
    month_str = request.args.get('month')
    if month_str:
        report_date = datetime.strptime(month_str, '%Y-%m')
    else:
        report_date = datetime.now()

    year = report_date.year
    month = report_date.month

    # Sales for the month
    sales = Sale.query.filter(
        and_(
            extract('year', Sale.sale_date) == year,
            extract('month', Sale.sale_date) == month,
            Sale.status == 'completed'
        )
    ).all()

    # Calculate totals
    total_revenue = sum(sale.total for sale in sales)
    total_transactions = len(sales)

    # Sales by category
    category_sales = db.session.query(
        db.func.coalesce(db.text("categories.name"), 'Uncategorized').label('category'),
        func.sum(SaleItem.subtotal).label('total')
    ).select_from(SaleItem).join(Sale).join(Product)\
    .outerjoin(Product.category).filter(
        and_(
            extract('year', Sale.sale_date) == year,
            extract('month', Sale.sale_date) == month,
            Sale.status == 'completed'
        )
    ).group_by('category').all()

    # Top customers
    top_customers = db.session.query(
        Customer.name,
        func.count(Sale.id).label('transactions'),
        func.sum(Sale.total).label('total')
    ).join(Sale).filter(
        and_(
            extract('year', Sale.sale_date) == year,
            extract('month', Sale.sale_date) == month,
            Sale.status == 'completed'
        )
    ).group_by(Customer.id).order_by(func.sum(Sale.total).desc()).limit(10).all()

    return render_template('reports/monthly_report.html',
                         year=year,
                         month=month,
                         total_revenue=total_revenue,
                         total_transactions=total_transactions,
                         category_sales=category_sales,
                         top_customers=top_customers)


@bp.route('/custom')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def custom_report():
    """Custom date range report"""
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    if from_date and to_date:
        from_dt = datetime.strptime(from_date, '%Y-%m-%d')
        to_dt = datetime.strptime(to_date, '%Y-%m-%d')

        # Get sales in date range
        sales = Sale.query.filter(
            and_(
                Sale.sale_date >= from_dt,
                Sale.sale_date <= to_dt,
                Sale.status == 'completed'
            )
        ).all()

        total_sales = sum(sale.total for sale in sales)
        total_transactions = len(sales)

        # Product performance
        product_performance = db.session.query(
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
        ).group_by(Product.id).order_by(func.sum(SaleItem.subtotal).desc()).all()

        return render_template('reports/custom_report.html',
                             from_date=from_date,
                             to_date=to_date,
                             total_sales=total_sales,
                             total_transactions=total_transactions,
                             product_performance=product_performance)

    return render_template('reports/custom_report.html')


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
    """Employee performance and sales report"""
    from app.models import User

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

    # Employee sales performance
    # Subquery to count items per sale
    items_subquery = db.session.query(
        SaleItem.sale_id,
        func.sum(SaleItem.quantity).label('item_count')
    ).group_by(SaleItem.sale_id).subquery()

    employee_stats = db.session.query(
        User.full_name,
        User.username,
        func.count(Sale.id).label('total_sales'),
        func.sum(Sale.total).label('total_revenue'),
        func.avg(Sale.total).label('avg_sale'),
        func.coalesce(func.sum(items_subquery.c.item_count), 0).label('items_sold')
    ).join(Sale, Sale.user_id == User.id).outerjoin(
        items_subquery, items_subquery.c.sale_id == Sale.id
    ).filter(
        and_(
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
            Sale.status == 'completed'
        )
    ).group_by(User.id).order_by(func.sum(Sale.total).desc()).all()

    # Calculate totals
    total_revenue = sum(emp.total_revenue or 0 for emp in employee_stats)
    total_sales_count = sum(emp.total_sales or 0 for emp in employee_stats)

    return render_template('reports/employee_performance.html',
                         start_date=start_date,
                         end_date=end_date,
                         employee_stats=employee_stats,
                         total_revenue=total_revenue,
                         total_sales_count=total_sales_count)


@bp.route('/product-performance')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def product_performance():
    """Product performance analysis"""
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
    ).filter(
        and_(
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
            Sale.status == 'completed'
        )
    ).group_by(Product.id).order_by(func.sum(SaleItem.subtotal).desc()).limit(20).all()

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
    ).filter(
        and_(
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
            Sale.status == 'completed'
        )
    ).group_by(Product.id).order_by(func.sum(SaleItem.subtotal).asc()).limit(10).all()

    # Never sold products
    sold_product_ids = db.session.query(func.distinct(SaleItem.product_id)).join(Sale).filter(
        and_(
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
            Sale.status == 'completed'
        )
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
                         never_sold=never_sold)


@bp.route('/sales-by-category')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def sales_by_category():
    """Sales breakdown by product category"""
    from app.models import Category

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

    # Sales by category
    category_sales = db.session.query(
        func.coalesce(Category.name, 'Uncategorized').label('category'),
        func.sum(SaleItem.quantity).label('units_sold'),
        func.sum(SaleItem.subtotal).label('revenue'),
        func.count(func.distinct(Sale.id)).label('transactions'),
        func.sum((SaleItem.unit_price - Product.cost_price) * SaleItem.quantity).label('profit')
    ).select_from(SaleItem).join(Sale).join(Product).outerjoin(Category).filter(
        and_(
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
            Sale.status == 'completed'
        )
    ).group_by('category').order_by(func.sum(SaleItem.subtotal).desc()).all()

    # Calculate totals
    total_revenue = sum(cat.revenue or 0 for cat in category_sales)
    total_profit = sum(cat.profit or 0 for cat in category_sales)
    total_units = sum(cat.units_sold or 0 for cat in category_sales)

    return render_template('reports/sales_by_category.html',
                         start_date=start_date,
                         end_date=end_date,
                         category_sales=category_sales,
                         total_revenue=total_revenue,
                         total_profit=total_profit,
                         total_units=total_units)


@bp.route('/profit-loss')
@login_required
@permission_required(Permissions.REPORT_VIEW_FINANCIAL)
def profit_loss():
    """Profit and Loss (P&L) statement"""
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

    # Revenue
    sales = Sale.query.filter(
        and_(
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
            Sale.status == 'completed'
        )
    ).all()

    gross_revenue = sum(sale.subtotal for sale in sales)
    total_discounts = sum(sale.discount for sale in sales)
    net_revenue = sum(sale.total for sale in sales)

    # Cost of Goods Sold
    cogs = db.session.query(
        func.sum(Product.cost_price * SaleItem.quantity)
    ).join(SaleItem).join(Sale).filter(
        and_(
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
            Sale.status == 'completed'
        )
    ).scalar() or 0

    # Gross Profit
    gross_profit = net_revenue - cogs
    gross_margin = (gross_profit / net_revenue * 100) if net_revenue > 0 else 0

    # Payment method breakdown
    payment_breakdown = {}
    for sale in sales:
        method = sale.payment_method
        if method not in payment_breakdown:
            payment_breakdown[method] = 0
        payment_breakdown[method] += float(sale.total)

    return render_template('reports/profit_loss.html',
                         start_date=start_date,
                         end_date=end_date,
                         gross_revenue=gross_revenue,
                         total_discounts=total_discounts,
                         net_revenue=net_revenue,
                         cogs=cogs,
                         gross_profit=gross_profit,
                         gross_margin=gross_margin,
                         payment_breakdown=payment_breakdown,
                         total_transactions=len(sales))


@bp.route('/customer-analysis')
@login_required
@permission_required(Permissions.REPORT_VIEW_SALES)
def customer_analysis():
    """Customer purchase behavior analysis"""
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

    # Top customers by revenue
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
    ).filter(
        and_(
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
            Sale.status == 'completed'
        )
    ).group_by(Customer.id).order_by(func.sum(Sale.total).desc()).limit(20).all()

    # Customer loyalty tier breakdown - use loyalty_points ranges instead of property
    tier_case = case(
        (Customer.loyalty_points >= 2500, 'Platinum'),
        (Customer.loyalty_points >= 1000, 'Gold'),
        (Customer.loyalty_points >= 250, 'Silver'),
        else_='Bronze'
    )

    tier_breakdown = db.session.query(
        tier_case.label('loyalty_tier'),
        func.count(func.distinct(Customer.id)).label('customer_count'),
        func.count(Sale.id).label('total_purchases'),
        func.sum(Sale.total).label('total_revenue')
    ).select_from(Customer).outerjoin(
        Sale, Sale.customer_id == Customer.id
    ).filter(
        or_(
            Sale.id.is_(None),  # Include customers with no sales
            and_(
                Sale.sale_date >= start_date,
                Sale.sale_date <= end_date,
                Sale.status == 'completed'
            )
        )
    ).group_by(tier_case).all()

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
                         new_customers=new_customers)
