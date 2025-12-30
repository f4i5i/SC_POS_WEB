"""
Customer Management Routes
Handles customer CRUD operations and customer-related features
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date
from decimal import Decimal
from app.models import db, Customer, Sale, SyncQueue
from app.utils.helpers import has_permission
from app.utils.permissions import permission_required, Permissions
from app.utils.birthday_gifts import (
    get_eligible_birthday_customers,
    get_tomorrow_birthday_notifications,
    get_premium_birthday_gift,
    calculate_customer_purchase_stats
)
from sqlalchemy import extract, func
import json

bp = Blueprint('customers', __name__)


@bp.route('/')
@login_required
@permission_required(Permissions.CUSTOMER_VIEW)
def index():
    """List all customers"""
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config['ITEMS_PER_PAGE']
    search = request.args.get('search', '').strip()

    query = Customer.query.filter_by(is_active=True)

    if search:
        query = query.filter(
            db.or_(
                Customer.name.ilike(f'%{search}%'),
                Customer.phone.ilike(f'%{search}%'),
                Customer.email.ilike(f'%{search}%')
            )
        )

    customers = query.order_by(Customer.name).paginate(page=page, per_page=per_page, error_out=False)

    return render_template('customers/index.html', customers=customers)


@bp.route('/add', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.CUSTOMER_CREATE)
def add_customer():
    """Add new customer"""
    if request.method == 'POST':
        try:
            customer = Customer(
                name=request.form.get('name'),
                phone=request.form.get('phone'),
                email=request.form.get('email'),
                address=request.form.get('address'),
                city=request.form.get('city'),
                postal_code=request.form.get('postal_code'),
                customer_type=request.form.get('customer_type', 'regular'),
                notes=request.form.get('notes')
            )

            # Parse birthday if provided
            birthday = request.form.get('birthday')
            if birthday:
                customer.birthday = datetime.strptime(birthday, '%Y-%m-%d').date()

            db.session.add(customer)
            db.session.flush()

            # Queue for sync
            sync_item = SyncQueue(
                table_name='customers',
                operation='insert',
                record_id=customer.id,
                data_json=json.dumps({'customer_id': customer.id})
            )
            db.session.add(sync_item)

            db.session.commit()
            flash(f'Customer {customer.name} added successfully', 'success')
            return redirect(url_for('customers.index'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error adding customer: {str(e)}', 'danger')

    return render_template('customers/add_customer.html')


@bp.route('/edit/<int:customer_id>', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.CUSTOMER_EDIT)
def edit_customer(customer_id):
    """Edit existing customer"""
    customer = Customer.query.get_or_404(customer_id)

    if request.method == 'POST':
        try:
            customer.name = request.form.get('name')
            customer.phone = request.form.get('phone')
            customer.email = request.form.get('email')
            customer.address = request.form.get('address')
            customer.city = request.form.get('city')
            customer.postal_code = request.form.get('postal_code')
            customer.customer_type = request.form.get('customer_type', 'regular')
            customer.notes = request.form.get('notes')

            # Parse birthday if provided
            birthday = request.form.get('birthday')
            if birthday:
                customer.birthday = datetime.strptime(birthday, '%Y-%m-%d').date()

            # Queue for sync
            sync_item = SyncQueue(
                table_name='customers',
                operation='update',
                record_id=customer.id,
                data_json=json.dumps({'customer_id': customer.id})
            )
            db.session.add(sync_item)

            db.session.commit()
            flash(f'Customer {customer.name} updated successfully', 'success')
            return redirect(url_for('customers.index'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating customer: {str(e)}', 'danger')

    return render_template('customers/edit_customer.html', customer=customer)


@bp.route('/delete/<int:customer_id>', methods=['POST'])
@login_required
@permission_required(Permissions.CUSTOMER_DELETE)
def delete_customer(customer_id):
    """Delete customer (soft delete)"""
    try:
        customer = Customer.query.get_or_404(customer_id)
        customer.is_active = False

        # Queue for sync
        sync_item = SyncQueue(
            table_name='customers',
            operation='update',
            record_id=customer.id,
            data_json=json.dumps({'is_active': False})
        )
        db.session.add(sync_item)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Customer deleted successfully'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/view/<int:customer_id>')
@login_required
def view_customer(customer_id):
    """View customer details and purchase history"""
    customer = Customer.query.get_or_404(customer_id)
    sales = Sale.query.filter_by(customer_id=customer_id)\
        .order_by(Sale.sale_date.desc()).limit(50).all()

    return render_template('customers/view_customer.html', customer=customer, sales=sales)


@bp.route('/search')
@login_required
def search_customers():
    """Search customers (AJAX endpoint)"""
    query = request.args.get('q', '').strip()

    if len(query) < 2:
        return jsonify({'customers': []})

    customers = Customer.query.filter(
        db.and_(
            Customer.is_active == True,
            db.or_(
                Customer.name.ilike(f'%{query}%'),
                Customer.phone.ilike(f'%{query}%')
            )
        )
    ).limit(10).all()

    results = []
    for customer in customers:
        results.append({
            'id': customer.id,
            'name': customer.name,
            'phone': customer.phone,
            'email': customer.email,
            'customer_type': customer.customer_type
        })

    return jsonify({'customers': results})


@bp.route('/birthdays')
@login_required
@permission_required(Permissions.CUSTOMER_VIEW)
def birthdays():
    """Birthday calendar and upcoming birthdays"""
    today = date.today()
    current_month = today.month
    current_day = today.day

    # Get customers with birthdays this month
    this_month_birthdays = Customer.query.filter(
        Customer.is_active == True,
        Customer.birthday.isnot(None),
        extract('month', Customer.birthday) == current_month
    ).order_by(extract('day', Customer.birthday)).all()

    # Get today's birthdays
    todays_birthdays = [c for c in this_month_birthdays if c.birthday.day == current_day]

    # Get upcoming birthdays (next 30 days)
    upcoming_birthdays = []
    for customer in Customer.query.filter(
        Customer.is_active == True,
        Customer.birthday.isnot(None)
    ).all():
        if customer.birthday:
            # Calculate next birthday
            next_birthday = customer.birthday.replace(year=today.year)
            if next_birthday < today:
                next_birthday = next_birthday.replace(year=today.year + 1)

            days_until = (next_birthday - today).days
            if 0 <= days_until <= 30:
                upcoming_birthdays.append({
                    'customer': customer,
                    'days_until': days_until,
                    'next_birthday': next_birthday
                })

    # Sort by days until birthday
    upcoming_birthdays.sort(key=lambda x: x['days_until'])

    # Calculate birthday statistics
    total_with_birthdays = Customer.query.filter(
        Customer.is_active == True,
        Customer.birthday.isnot(None)
    ).count()

    total_customers = Customer.query.filter(Customer.is_active == True).count()
    birthday_coverage = (total_with_birthdays / total_customers * 100) if total_customers > 0 else 0

    return render_template('customers/birthdays.html',
                         todays_birthdays=todays_birthdays,
                         this_month_birthdays=this_month_birthdays,
                         upcoming_birthdays=upcoming_birthdays,
                         total_with_birthdays=total_with_birthdays,
                         birthday_coverage=birthday_coverage,
                         current_month=current_month,
                         today=today)


@bp.route('/birthday-gift/<int:customer_id>', methods=['POST'])
@login_required
@permission_required(Permissions.CUSTOMER_EDIT)
def apply_birthday_gift(customer_id):
    """Apply birthday gift/discount to customer"""
    customer = Customer.query.get_or_404(customer_id)

    if not customer.birthday:
        return jsonify({'error': 'Customer has no birthday on record'}), 400

    today = date.today()

    # Check if today is customer's birthday (month and day)
    is_birthday = (customer.birthday.month == today.month and
                   customer.birthday.day == today.day)

    if not is_birthday:
        return jsonify({'error': 'Today is not customer\'s birthday'}), 400

    # Determine birthday gift based on loyalty tier
    gift_data = get_birthday_gift_by_tier(customer.loyalty_tier)

    return jsonify({
        'success': True,
        'customer': {
            'id': customer.id,
            'name': customer.name,
            'loyalty_tier': customer.loyalty_tier
        },
        'gift': gift_data,
        'message': f'🎂 Happy Birthday {customer.name}! {gift_data["message"]}'
    })


def get_birthday_gift_by_tier(loyalty_tier):
    """Get birthday gift configuration based on loyalty tier"""
    gifts = {
        'Platinum': {
            'type': 'discount',
            'value': 25,
            'unit': 'percent',
            'message': 'Enjoy 25% off your birthday purchase!',
            'bonus_points': 500
        },
        'Gold': {
            'type': 'discount',
            'value': 20,
            'unit': 'percent',
            'message': 'Get 20% off on your special day!',
            'bonus_points': 300
        },
        'Silver': {
            'type': 'discount',
            'value': 15,
            'unit': 'percent',
            'message': 'Celebrate with 15% off!',
            'bonus_points': 200
        },
        'Bronze': {
            'type': 'discount',
            'value': 10,
            'unit': 'percent',
            'message': 'Happy Birthday! 10% off for you!',
            'bonus_points': 100
        }
    }

    return gifts.get(loyalty_tier, {
        'type': 'discount',
        'value': 10,
        'unit': 'percent',
        'message': 'Happy Birthday! Enjoy 10% off!',
        'bonus_points': 50
    })


@bp.route('/send-birthday-wishes', methods=['POST'])
@login_required
@permission_required(Permissions.CUSTOMER_EDIT)
def send_birthday_wishes():
    """Send birthday wishes to customers"""
    data = request.get_json()
    customer_ids = data.get('customer_ids', [])

    if not customer_ids:
        return jsonify({'error': 'No customers selected'}), 400

    sent_count = 0
    errors = []

    for customer_id in customer_ids:
        customer = Customer.query.get(customer_id)
        if customer and customer.birthday:
            try:
                # Send SMS or Email (integrate with your messaging service)
                send_birthday_message(customer)
                sent_count += 1
            except Exception as e:
                errors.append(f"Failed to send to {customer.name}: {str(e)}")

    return jsonify({
        'success': True,
        'sent_count': sent_count,
        'errors': errors,
        'message': f'Birthday wishes sent to {sent_count} customers'
    })


def send_birthday_message(customer):
    """Send birthday message via SMS/Email"""
    # Get birthday gift info
    gift = get_birthday_gift_by_tier(customer.loyalty_tier)

    message = f"""
🎉 Happy Birthday {customer.name}! 🎉

Sunnat Collection wishes you a wonderful day filled with joy!

{gift['message']}
Plus {gift['bonus_points']} bonus loyalty points!

Visit us today to redeem your birthday gift.

Best wishes,
Sunnat Collection Team
    """.strip()

    # TODO: Integrate with SMS/Email service
    # For now, just log the message
    current_app.logger.info(f"Birthday message for {customer.name}: {message}")

    # In production, you would use services like:
    # - Twilio for SMS
    # - SendGrid for Email
    # - WhatsApp Business API

    return True


@bp.route('/birthday-notifications')
@login_required
@permission_required(Permissions.CUSTOMER_VIEW)
def birthday_notifications():
    """View tomorrow's birthday notifications for parcel preparation"""
    # Get customers with birthdays tomorrow who are eligible for premium gifts
    notifications = get_tomorrow_birthday_notifications()

    return render_template('customers/birthday_notifications.html',
                         notifications=notifications,
                         tomorrow=date.today() + timedelta(days=1))


@bp.route('/birthday-gift-details/<int:customer_id>')
@login_required
@permission_required(Permissions.CUSTOMER_VIEW)
def birthday_gift_details(customer_id):
    """Get detailed birthday gift information for a customer"""
    customer = Customer.query.get_or_404(customer_id)

    # Calculate purchase stats
    stats = calculate_customer_purchase_stats(customer_id)

    if not stats:
        return jsonify({'error': 'Unable to calculate customer statistics'}), 400

    # Get premium gift details
    gift = get_premium_birthday_gift(customer, stats)

    return jsonify({
        'success': True,
        'customer': {
            'id': customer.id,
            'name': customer.name,
            'phone': customer.phone,
            'email': customer.email,
            'loyalty_tier': customer.loyalty_tier,
            'loyalty_points': customer.loyalty_points
        },
        'stats': {
            'total_purchases': float(stats['total_purchases']),
            'total_orders': stats['total_orders'],
            'avg_order_value': float(stats['avg_order_value']),
            'perfumes_per_month': float(stats['perfumes_per_month']),
            'total_perfumes': stats['total_perfumes'],
            'is_regular_customer': stats['is_regular_customer']
        },
        'gift': gift
    })
