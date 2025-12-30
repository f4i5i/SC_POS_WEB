"""
Helper Utilities
Common utility functions used across the application
"""

from flask_login import current_user
from datetime import datetime
import random
import string
import os
from werkzeug.utils import secure_filename


def has_permission(permission):
    """
    Check if current user has permission

    Args:
        permission: Permission name (pos, inventory, customers, etc.)

    Returns:
        bool: True if user has permission
    """
    if not current_user.is_authenticated:
        return False

    return current_user.has_permission(permission)


def generate_sale_number():
    """
    Generate unique sale number

    Format: SALE-YYYYMMDD-XXXX
    Where XXXX is a random 4-digit number

    Returns:
        str: Sale number
    """
    date_part = datetime.now().strftime('%Y%m%d')
    random_part = ''.join(random.choices(string.digits, k=4))
    return f"SALE-{date_part}-{random_part}"


def generate_po_number():
    """
    Generate unique purchase order number

    Format: PO-YYYYMMDD-XXXX

    Returns:
        str: PO number
    """
    date_part = datetime.now().strftime('%Y%m%d')
    random_part = ''.join(random.choices(string.digits, k=4))
    return f"PO-{date_part}-{random_part}"


def generate_product_code():
    """
    Generate product code

    Format: PROD-XXXXXXXX (8 random alphanumeric characters)

    Returns:
        str: Product code
    """
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"PROD-{random_part}"


def allowed_file(filename):
    """
    Check if file extension is allowed

    Args:
        filename: Name of file to check

    Returns:
        bool: True if extension is allowed
    """
    from flask import current_app

    if '.' not in filename:
        return False

    ext = filename.rsplit('.', 1)[1].lower()
    return ext in current_app.config.get('ALLOWED_EXTENSIONS', set())


def format_currency(amount, currency_symbol='Rs.'):
    """
    Format amount as currency

    Args:
        amount: Numeric amount
        currency_symbol: Currency symbol

    Returns:
        str: Formatted currency string
    """
    return f"{currency_symbol} {amount:,.2f}"


def format_percentage(value):
    """
    Format value as percentage

    Args:
        value: Numeric value

    Returns:
        str: Formatted percentage
    """
    return f"{value:.2f}%"


def calculate_profit_margin(cost_price, selling_price):
    """
    Calculate profit margin percentage

    Args:
        cost_price: Cost price
        selling_price: Selling price

    Returns:
        float: Profit margin percentage
    """
    if not cost_price or cost_price == 0:
        return 0

    return ((selling_price - cost_price) / cost_price) * 100


def create_sample_products():
    """Create sample products for testing"""
    from app.models import db, Product, Category, Supplier
    from decimal import Decimal

    # Create categories
    perfume_cat = Category(name='Perfumes', description='Attar and perfumes')
    db.session.add(perfume_cat)
    db.session.commit()

    # Create supplier
    supplier = Supplier(
        name='Al Haramain Perfumes',
        contact_person='Ahmed Khan',
        phone='+92-300-1234567',
        email='info@alharamain.pk'
    )
    db.session.add(supplier)
    db.session.commit()

    # Sample perfume products
    sample_products = [
        {
            'code': 'PERF001',
            'barcode': '8906001971011',
            'name': 'Musk Al Madinah',
            'brand': 'Al Haramain',
            'size': '15ml',
            'cost_price': Decimal('500.00'),
            'selling_price': Decimal('750.00'),
            'quantity': 50
        },
        {
            'code': 'PERF002',
            'barcode': '8906001971012',
            'name': 'Choco Musk',
            'brand': 'Nabeel',
            'size': '15ml',
            'cost_price': Decimal('450.00'),
            'selling_price': Decimal('700.00'),
            'quantity': 30
        },
        {
            'code': 'PERF003',
            'barcode': '8906001971013',
            'name': 'La Yuqawam',
            'brand': 'Rasasi',
            'size': '75ml',
            'cost_price': Decimal('2500.00'),
            'selling_price': Decimal('3500.00'),
            'quantity': 20
        },
        {
            'code': 'PERF004',
            'barcode': '8906001971014',
            'name': 'Attar Mubakhar',
            'brand': 'Al Rehab',
            'size': '6ml',
            'cost_price': Decimal('200.00'),
            'selling_price': Decimal('350.00'),
            'quantity': 100
        },
        {
            'code': 'PERF005',
            'barcode': '8906001971015',
            'name': 'Oud Mood',
            'brand': 'Lattafa',
            'size': '100ml',
            'cost_price': Decimal('3000.00'),
            'selling_price': Decimal('4200.00'),
            'quantity': 15
        }
    ]

    for product_data in sample_products:
        product = Product(
            category_id=perfume_cat.id,
            supplier_id=supplier.id,
            **product_data
        )
        db.session.add(product)

    db.session.commit()
    print("Sample products created successfully!")


def create_sample_customers():
    """Create sample customers for testing"""
    from app.models import db, Customer

    sample_customers = [
        {
            'name': 'Muhammad Ali',
            'phone': '+92-300-1111111',
            'email': 'ali@example.com',
            'city': 'Rawalpindi',
            'customer_type': 'regular'
        },
        {
            'name': 'Fatima Khan',
            'phone': '+92-300-2222222',
            'email': 'fatima@example.com',
            'city': 'Islamabad',
            'customer_type': 'vip'
        },
        {
            'name': 'Ahmed Hassan',
            'phone': '+92-300-3333333',
            'email': 'ahmed@example.com',
            'city': 'Wah Cantt',
            'customer_type': 'regular'
        }
    ]

    for customer_data in sample_customers:
        customer = Customer(**customer_data)
        db.session.add(customer)

    db.session.commit()
    print("Sample customers created successfully!")


def get_date_range(period='today'):
    """
    Get date range for reporting

    Args:
        period: today, yesterday, this_week, last_week, this_month, last_month

    Returns:
        tuple: (start_date, end_date)
    """
    from datetime import timedelta

    today = datetime.now().date()

    if period == 'today':
        return today, today

    elif period == 'yesterday':
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday

    elif period == 'this_week':
        start = today - timedelta(days=today.weekday())
        return start, today

    elif period == 'last_week':
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
        return start, end

    elif period == 'this_month':
        start = today.replace(day=1)
        return start, today

    elif period == 'last_month':
        last_month = today.replace(day=1) - timedelta(days=1)
        start = last_month.replace(day=1)
        return start, last_month

    return today, today


def sanitize_filename(filename):
    """
    Sanitize filename for safe storage

    Args:
        filename: Original filename

    Returns:
        str: Safe filename
    """
    return secure_filename(filename)
