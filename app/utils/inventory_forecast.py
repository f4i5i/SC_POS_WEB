"""
Inventory Forecasting Utilities
Calculates demand forecasting, safety stock, reorder points, and stock alerts
"""

from datetime import datetime, timedelta
from sqlalchemy import func, and_
from app.models import db, Sale, SaleItem, Product, LocationStock


def get_product_sales_stats(product_id, location_id, days=30):
    """
    Get sales statistics for a product at a location over the specified period.

    Returns dict with:
    - total_sold: Total units sold in period
    - avg_daily_sales: Average daily sales
    - max_daily_sales: Maximum daily sales (for safety stock calc)
    - min_daily_sales: Minimum daily sales
    - sale_days: Number of days with at least one sale
    """
    from_date = datetime.utcnow() - timedelta(days=days)

    # Get daily sales data
    daily_sales = db.session.query(
        func.date(Sale.sale_date).label('sale_date'),
        func.sum(SaleItem.quantity).label('qty_sold')
    ).join(SaleItem, Sale.id == SaleItem.sale_id)\
     .filter(
        SaleItem.product_id == product_id,
        Sale.location_id == location_id,
        Sale.sale_date >= from_date,
        Sale.status == 'completed'
    ).group_by(func.date(Sale.sale_date)).all()

    if not daily_sales:
        return {
            'total_sold': 0,
            'avg_daily_sales': 0,
            'max_daily_sales': 0,
            'min_daily_sales': 0,
            'sale_days': 0,
            'days_analyzed': days
        }

    quantities = [row.qty_sold for row in daily_sales]
    total_sold = sum(quantities)

    return {
        'total_sold': total_sold,
        'avg_daily_sales': round(total_sold / days, 2),  # Average over full period
        'max_daily_sales': max(quantities),
        'min_daily_sales': min(quantities),
        'sale_days': len(daily_sales),
        'days_analyzed': days
    }


def calculate_safety_stock(product_id, location_id, lead_time_days=3, days=30):
    """
    Calculate safety stock using the formula:
    Safety Stock = (Max Daily Sales × Max Lead Time) - (Avg Daily Sales × Avg Lead Time)

    Args:
        product_id: Product ID
        location_id: Location ID
        lead_time_days: Average lead time for restocking (default 3 days)
        days: Days of sales history to analyze (default 30)

    Returns:
        int: Recommended safety stock quantity
    """
    stats = get_product_sales_stats(product_id, location_id, days)

    if stats['avg_daily_sales'] == 0:
        # No sales history - use a default minimum
        return 5

    avg_daily = stats['avg_daily_sales']
    max_daily = stats['max_daily_sales']

    # Assume max lead time is 1.5x average lead time
    max_lead_time = lead_time_days * 1.5

    # Safety stock formula
    safety_stock = (max_daily * max_lead_time) - (avg_daily * lead_time_days)

    # Ensure minimum safety stock
    return max(int(safety_stock), 3)


def calculate_reorder_point(product_id, location_id, lead_time_days=3, days=30):
    """
    Calculate reorder point using the formula:
    Reorder Point = (Avg Daily Sales × Lead Time) + Safety Stock

    Args:
        product_id: Product ID
        location_id: Location ID
        lead_time_days: Average lead time for restocking
        days: Days of sales history to analyze

    Returns:
        int: Recommended reorder point
    """
    stats = get_product_sales_stats(product_id, location_id, days)
    safety_stock = calculate_safety_stock(product_id, location_id, lead_time_days, days)

    lead_time_demand = stats['avg_daily_sales'] * lead_time_days
    reorder_point = lead_time_demand + safety_stock

    return max(int(reorder_point), safety_stock)


def calculate_days_of_stock(product_id, location_id, days=30):
    """
    Calculate how many days of stock remain based on average daily sales.

    Returns:
        float: Days of stock remaining (None if no sales history)
    """
    stats = get_product_sales_stats(product_id, location_id, days)

    if stats['avg_daily_sales'] == 0:
        return None  # Cannot calculate without sales history

    # Get current stock
    location_stock = LocationStock.query.filter_by(
        product_id=product_id,
        location_id=location_id
    ).first()

    current_stock = location_stock.quantity if location_stock else 0

    if current_stock <= 0:
        return 0

    days_remaining = current_stock / stats['avg_daily_sales']
    return round(days_remaining, 1)


def calculate_suggested_reorder_qty(product_id, location_id, target_days=14, lead_time_days=3, days=30):
    """
    Calculate suggested reorder quantity to maintain target days of stock.

    Formula: Suggested Qty = (Avg Daily Sales × Target Days) + Safety Stock - Current Stock

    Args:
        product_id: Product ID
        location_id: Location ID
        target_days: Target days of stock to maintain (default 14 days = 2 weeks)
        lead_time_days: Lead time for delivery
        days: Days of sales history to analyze

    Returns:
        int: Suggested reorder quantity
    """
    stats = get_product_sales_stats(product_id, location_id, days)
    safety_stock = calculate_safety_stock(product_id, location_id, lead_time_days, days)

    # Get current stock
    location_stock = LocationStock.query.filter_by(
        product_id=product_id,
        location_id=location_id
    ).first()
    current_stock = location_stock.quantity if location_stock else 0

    # Target stock level
    target_stock = (stats['avg_daily_sales'] * target_days) + safety_stock

    # Suggested order quantity
    suggested_qty = target_stock - current_stock

    # Minimum order quantity (at least 1 week of stock)
    min_order = max(int(stats['avg_daily_sales'] * 7), 10)

    return max(int(suggested_qty), min_order) if suggested_qty > 0 else 0


def get_product_forecast(product_id, location_id, lead_time_days=3):
    """
    Get complete forecast data for a product at a location.

    Returns dict with all forecasting metrics.
    """
    stats = get_product_sales_stats(product_id, location_id, days=30)

    # Get current stock
    location_stock = LocationStock.query.filter_by(
        product_id=product_id,
        location_id=location_id
    ).first()
    current_stock = location_stock.quantity if location_stock else 0
    current_reorder_level = location_stock.reorder_level if location_stock else 10

    # Calculate forecasting metrics
    safety_stock = calculate_safety_stock(product_id, location_id, lead_time_days)
    recommended_reorder_point = calculate_reorder_point(product_id, location_id, lead_time_days)
    days_of_stock = calculate_days_of_stock(product_id, location_id)
    suggested_reorder_qty = calculate_suggested_reorder_qty(product_id, location_id, target_days=14, lead_time_days=lead_time_days)

    # Determine stock status
    if current_stock == 0:
        status = 'out_of_stock'
        urgency = 'critical'
    elif current_stock <= safety_stock:
        status = 'critical_low'
        urgency = 'high'
    elif current_stock <= current_reorder_level:
        status = 'low_stock'
        urgency = 'medium'
    elif days_of_stock and days_of_stock <= 7:
        status = 'reorder_soon'
        urgency = 'low'
    else:
        status = 'in_stock'
        urgency = 'none'

    return {
        'current_stock': current_stock,
        'current_reorder_level': current_reorder_level,
        'sales_stats': stats,
        'safety_stock': safety_stock,
        'recommended_reorder_point': recommended_reorder_point,
        'days_of_stock': days_of_stock,
        'suggested_reorder_qty': suggested_reorder_qty,
        'status': status,
        'urgency': urgency,
        'lead_time_days': lead_time_days
    }


def get_low_stock_alerts(location_id, include_forecasting=True):
    """
    Get all products that need attention at a location.

    Returns list of products with:
    - Out of stock items
    - Items below reorder level
    - Items with less than 7 days of stock (if forecasting enabled)
    """
    from app.models import Product

    alerts = []

    # Get all active products
    products = Product.query.filter_by(is_active=True).all()

    for product in products:
        location_stock = LocationStock.query.filter_by(
            product_id=product.id,
            location_id=location_id
        ).first()

        current_stock = location_stock.quantity if location_stock else 0
        reorder_level = location_stock.reorder_level if location_stock else product.reorder_level

        # Check if needs attention
        needs_attention = False
        alert_type = None
        urgency = 'none'
        days_of_stock = None
        suggested_qty = 0

        if current_stock == 0:
            needs_attention = True
            alert_type = 'out_of_stock'
            urgency = 'critical'
        elif current_stock <= reorder_level:
            needs_attention = True
            alert_type = 'low_stock'
            urgency = 'high' if current_stock <= reorder_level / 2 else 'medium'

        # Add forecasting data if enabled
        if include_forecasting and (needs_attention or current_stock <= reorder_level * 1.5):
            stats = get_product_sales_stats(product.id, location_id, days=30)
            if stats['avg_daily_sales'] > 0:
                days_of_stock = round(current_stock / stats['avg_daily_sales'], 1) if current_stock > 0 else 0
                suggested_qty = calculate_suggested_reorder_qty(product.id, location_id)

                # Check days of stock
                if not needs_attention and days_of_stock and days_of_stock <= 7:
                    needs_attention = True
                    alert_type = 'running_low'
                    urgency = 'low'

        if needs_attention:
            alerts.append({
                'product': product,
                'current_stock': current_stock,
                'reorder_level': reorder_level,
                'alert_type': alert_type,
                'urgency': urgency,
                'days_of_stock': days_of_stock,
                'suggested_qty': suggested_qty
            })

    # Sort by urgency
    urgency_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    alerts.sort(key=lambda x: urgency_order.get(x['urgency'], 4))

    return alerts


def get_location_stock_summary(location_id):
    """
    Get summary statistics for a location's inventory.
    """
    from app.models import Product

    total_products = Product.query.filter_by(is_active=True).count()

    # Count stock statuses
    out_of_stock = 0
    low_stock = 0
    in_stock = 0
    total_value = 0

    products = Product.query.filter_by(is_active=True).all()
    location_stocks = {ls.product_id: ls for ls in LocationStock.query.filter_by(location_id=location_id).all()}

    for product in products:
        ls = location_stocks.get(product.id)
        qty = ls.quantity if ls else 0
        reorder_level = ls.reorder_level if ls else product.reorder_level

        if qty == 0:
            out_of_stock += 1
        elif qty <= reorder_level:
            low_stock += 1
        else:
            in_stock += 1

        total_value += qty * float(product.cost_price)

    return {
        'total_products': total_products,
        'in_stock': in_stock,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'total_value': round(total_value, 2),
        'stock_health_percent': round((in_stock / total_products * 100) if total_products > 0 else 0, 1)
    }
