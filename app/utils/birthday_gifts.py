"""
Birthday Gift System for Loyal Customers
Automatically identifies and rewards loyal customers on their birthdays
"""

from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import func, and_, extract
from app.models import db, Customer, Sale, SaleItem, Product


def get_eligible_birthday_customers(notification_days=1):
    """
    Get customers eligible for birthday gifts

    Criteria:
    - Has birthday on file
    - Active customer
    - Purchases 2+ perfumes per month minimum (on average)
    - Good purchase history
    - Birthday is within notification_days

    Args:
        notification_days: Number of days ahead to check for birthdays (1 = tomorrow)

    Returns:
        List of tuples: (customer, eligibility_score, stats)
    """
    today = date.today()
    target_date = today + timedelta(days=notification_days)

    # Get customers with birthdays on target date
    customers_with_birthday = Customer.query.filter(
        and_(
            Customer.is_active == True,
            Customer.birthday.isnot(None),
            extract('month', Customer.birthday) == target_date.month,
            extract('day', Customer.birthday) == target_date.day
        )
    ).all()

    eligible_customers = []

    for customer in customers_with_birthday:
        # Calculate purchase statistics
        stats = calculate_customer_purchase_stats(customer.id)

        # Check eligibility criteria
        if is_customer_eligible_for_gift(stats):
            # Calculate eligibility score (higher = more valuable customer)
            score = calculate_eligibility_score(stats)
            eligible_customers.append((customer, score, stats))

    # Sort by eligibility score (descending)
    eligible_customers.sort(key=lambda x: x[1], reverse=True)

    return eligible_customers


def calculate_customer_purchase_stats(customer_id):
    """
    Calculate comprehensive purchase statistics for a customer

    Returns:
        dict with:
            - total_purchases: Total amount spent
            - total_orders: Number of orders
            - avg_order_value: Average order amount
            - perfumes_per_month: Average perfumes bought per month
            - months_active: Number of months customer has been active
            - last_purchase_date: Date of last purchase
            - high_value_purchases: Number of purchases over Rs. 5000
    """
    from dateutil.relativedelta import relativedelta

    # Get customer creation date
    customer = Customer.query.get(customer_id)
    if not customer:
        return None

    created_date = customer.created_at.date() if customer.created_at else date.today()
    months_active = max(1, (date.today() - created_date).days / 30.0)

    # Get all sales for this customer
    sales = Sale.query.filter_by(customer_id=customer_id).all()

    if not sales:
        return {
            'total_purchases': 0,
            'total_orders': 0,
            'avg_order_value': 0,
            'perfumes_per_month': 0,
            'months_active': months_active,
            'last_purchase_date': None,
            'high_value_purchases': 0,
            'recent_6month_purchases': 0,
            'is_regular_customer': False
        }

    # Calculate statistics
    total_purchases = sum(float(sale.total) for sale in sales)
    total_orders = len(sales)
    avg_order_value = total_purchases / total_orders if total_orders > 0 else 0
    high_value_purchases = sum(1 for sale in sales if float(sale.total) > 5000)

    # Get last purchase date
    last_sale = max(sales, key=lambda s: s.sale_date)
    last_purchase_date = last_sale.sale_date.date() if last_sale else None

    # Calculate perfume purchases (products with 'perfume', 'fragrance', 'scent' in name/category)
    perfume_keywords = ['perfume', 'fragrance', 'scent', 'eau de', 'cologne', 'attar']

    total_perfumes = 0
    for sale in sales:
        for item in sale.items:
            product_name = item.product.name.lower() if item.product else ''
            category_name = item.product.category.name.lower() if item.product and item.product.category else ''

            # Check if it's a perfume
            is_perfume = any(keyword in product_name or keyword in category_name
                           for keyword in perfume_keywords)

            if is_perfume:
                total_perfumes += item.quantity

    perfumes_per_month = total_perfumes / months_active if months_active > 0 else 0

    # Recent purchase activity (last 6 months)
    six_months_ago = date.today() - timedelta(days=180)
    recent_sales = [s for s in sales if s.sale_date.date() >= six_months_ago]
    recent_6month_purchases = sum(float(sale.total) for sale in recent_sales)

    # Check if regular customer (purchased in last 3 months)
    three_months_ago = date.today() - timedelta(days=90)
    is_regular_customer = any(s.sale_date.date() >= three_months_ago for s in sales)

    return {
        'total_purchases': total_purchases,
        'total_orders': total_orders,
        'avg_order_value': avg_order_value,
        'perfumes_per_month': perfumes_per_month,
        'months_active': months_active,
        'last_purchase_date': last_purchase_date,
        'high_value_purchases': high_value_purchases,
        'recent_6month_purchases': recent_6month_purchases,
        'is_regular_customer': is_regular_customer,
        'total_perfumes': total_perfumes
    }


def is_customer_eligible_for_gift(stats):
    """
    Check if customer meets criteria for birthday gift

    Criteria:
    - Minimum 2 perfumes per month on average
    - Has made at least one purchase
    - Is a regular customer (purchased in last 3 months)

    Args:
        stats: Dictionary from calculate_customer_purchase_stats

    Returns:
        bool: True if eligible
    """
    if not stats:
        return False

    # Minimum criteria
    min_perfumes_per_month = 2.0
    min_total_orders = 1

    return (
        stats['perfumes_per_month'] >= min_perfumes_per_month and
        stats['total_orders'] >= min_total_orders and
        stats['is_regular_customer']
    )


def calculate_eligibility_score(stats):
    """
    Calculate a score representing customer value for prioritization

    Higher score = more valuable customer

    Score components:
    - Total purchases (weighted heavily)
    - Frequency of high-value purchases
    - Recent activity
    - Average perfumes per month

    Returns:
        float: Eligibility score
    """
    if not stats:
        return 0

    score = 0

    # Total purchases (1 point per Rs. 100)
    score += stats['total_purchases'] / 100

    # High-value purchases (50 points each)
    score += stats['high_value_purchases'] * 50

    # Recent activity (1 point per Rs. 10 in last 6 months)
    score += stats['recent_6month_purchases'] / 10

    # Perfumes per month (10 points per perfume/month)
    score += stats['perfumes_per_month'] * 10

    # Regularity bonus (100 points if regular customer)
    if stats['is_regular_customer']:
        score += 100

    return score


def get_premium_birthday_gift(customer, stats):
    """
    Determine premium birthday gift based on customer value

    Gift tiers:
    - VIP Elite (Top 10%): 30% off + Rs. 1000 voucher + 1000 bonus points
    - VIP Gold (Top 25%): 25% off + Rs. 500 voucher + 500 bonus points
    - VIP Silver (Top 50%): 20% off + 300 bonus points
    - Loyal Customer: 15% off + 200 bonus points

    Args:
        customer: Customer model instance
        stats: Purchase statistics dictionary

    Returns:
        dict: Gift details
    """
    score = calculate_eligibility_score(stats)

    # Determine tier based on score
    if score >= 1000:  # VIP Elite
        return {
            'tier': 'VIP Elite',
            'discount_percentage': 30,
            'voucher_amount': 1000,
            'bonus_points': 1000,
            'special_gift': 'Free premium perfume sample set',
            'message': f'🎉 {customer.name}, you are our VIP Elite customer! Enjoy 30% off + Rs. 1000 voucher + premium gift!',
            'color': 'gold',
            'priority': 1
        }
    elif score >= 500:  # VIP Gold
        return {
            'tier': 'VIP Gold',
            'discount_percentage': 25,
            'voucher_amount': 500,
            'bonus_points': 500,
            'special_gift': 'Free perfume sample',
            'message': f'🎂 {customer.name}, you are our VIP Gold customer! Enjoy 25% off + Rs. 500 voucher!',
            'color': 'orange',
            'priority': 2
        }
    elif score >= 250:  # VIP Silver
        return {
            'tier': 'VIP Silver',
            'discount_percentage': 20,
            'voucher_amount': 0,
            'bonus_points': 300,
            'special_gift': None,
            'message': f'🎁 {customer.name}, you are our valued VIP Silver customer! Enjoy 20% off!',
            'color': 'silver',
            'priority': 3
        }
    else:  # Loyal Customer
        return {
            'tier': 'Loyal Customer',
            'discount_percentage': 15,
            'voucher_amount': 0,
            'bonus_points': 200,
            'special_gift': None,
            'message': f'🎈 {customer.name}, thank you for being a loyal customer! Enjoy 15% off!',
            'color': 'blue',
            'priority': 4
        }


def get_tomorrow_birthday_notifications():
    """
    Get list of customers with birthdays tomorrow who are eligible for gifts

    Returns:
        List of dicts with customer info, gift details, and notification data
    """
    eligible_customers = get_eligible_birthday_customers(notification_days=1)

    notifications = []

    for customer, score, stats in eligible_customers:
        gift = get_premium_birthday_gift(customer, stats)

        # Calculate recommended parcel contents
        parcel_recommendations = get_parcel_recommendations(customer, stats)

        notifications.append({
            'customer': customer,
            'score': score,
            'stats': stats,
            'gift': gift,
            'parcel_recommendations': parcel_recommendations,
            'notification_message': create_notification_message(customer, gift)
        })

    return notifications


def get_parcel_recommendations(customer, stats):
    """
    Recommend products to include in birthday parcel

    Based on:
    - Customer's purchase history
    - Popular products
    - Products they haven't tried yet

    Returns:
        List of recommended product IDs
    """
    # Get customer's purchase history
    purchased_products = db.session.query(Product.id)\
        .select_from(Product)\
        .join(SaleItem, Product.id == SaleItem.product_id)\
        .join(Sale, SaleItem.sale_id == Sale.id)\
        .filter(Sale.customer_id == customer.id)\
        .distinct().all()
    purchased_ids = [p[0] for p in purchased_products] if purchased_products else []

    # Get customer's favorite products (most purchased)
    favorites = db.session.query(
        Product.id,
        Product.name,
        func.sum(SaleItem.quantity).label('total_quantity')
    ).select_from(Product)\
    .join(SaleItem, Product.id == SaleItem.product_id)\
    .join(Sale, SaleItem.sale_id == Sale.id)\
    .filter(Sale.customer_id == customer.id)\
    .group_by(Product.id, Product.name)\
    .order_by(func.sum(SaleItem.quantity).desc())\
    .limit(3).all()

    # Get popular products they haven't tried (if any purchased products exist)
    if purchased_ids:
        popular_new = db.session.query(
            Product.id,
            Product.name,
            func.count(Sale.id).label('popularity')
        ).select_from(Product)\
        .join(SaleItem, Product.id == SaleItem.product_id)\
        .join(Sale, SaleItem.sale_id == Sale.id)\
        .filter(Product.id.notin_(purchased_ids))\
        .filter(Product.is_active == True)\
        .group_by(Product.id, Product.name)\
        .order_by(func.count(Sale.id).desc())\
        .limit(2).all()
    else:
        # If no purchased products, get popular products overall
        popular_new = db.session.query(
            Product.id,
            Product.name,
            func.count(Sale.id).label('popularity')
        ).select_from(Product)\
        .join(SaleItem, Product.id == SaleItem.product_id)\
        .join(Sale, SaleItem.sale_id == Sale.id)\
        .filter(Product.is_active == True)\
        .group_by(Product.id, Product.name)\
        .order_by(func.count(Sale.id).desc())\
        .limit(2).all()

    return {
        'favorites': [{'id': f[0], 'name': f[1], 'quantity': int(f[2])} for f in favorites],
        'new_suggestions': [{'id': p[0], 'name': p[1]} for p in popular_new]
    }


def create_notification_message(customer, gift):
    """
    Create notification message for staff

    Returns:
        String message for notification
    """
    tomorrow = date.today() + timedelta(days=1)

    message = f"""
🎂 BIRTHDAY ALERT - Prepare Parcel!

Customer: {customer.name}
Phone: {customer.phone}
Birthday: {tomorrow.strftime('%B %d, %Y')} (TOMORROW)
Gift Tier: {gift['tier']}

Gift Details:
- {gift['discount_percentage']}% Birthday Discount
"""

    if gift['voucher_amount'] > 0:
        message += f"- Rs. {gift['voucher_amount']} Gift Voucher\n"

    message += f"- {gift['bonus_points']} Bonus Loyalty Points\n"

    if gift['special_gift']:
        message += f"- {gift['special_gift']}\n"

    message += f"\n⚡ Priority: {'🔥' * (5 - gift['priority'])} (Tier {gift['priority']})"
    message += f"\n\n📦 ACTION: Prepare birthday parcel for tomorrow delivery!"

    return message
