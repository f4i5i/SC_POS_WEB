"""
Notifications Routes
SMS and WhatsApp integration with feature flags
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from app.models import db, Customer
from app.models_extended import (
    SMSTemplate, SMSLog, WhatsAppTemplate, WhatsAppLog,
    DuePayment, FeatureFlag
)
from app.utils.permissions import permission_required, Permissions
from app.utils.feature_flags import (
    feature_required, Features, is_feature_enabled, get_feature_config
)

bp = Blueprint('notifications', __name__)


# ============================================================
# SMS NOTIFICATIONS
# ============================================================

@bp.route('/sms')
@login_required
@feature_required(Features.SMS_NOTIFICATIONS)
def sms_index():
    """SMS notifications dashboard"""
    templates = SMSTemplate.query.all()
    recent_logs = SMSLog.query.order_by(SMSLog.sent_at.desc()).limit(50).all()

    # Stats
    today = date.today()
    today_sent = SMSLog.query.filter(
        db.func.date(SMSLog.sent_at) == today,
        SMSLog.status == 'sent'
    ).count()

    return render_template('notifications/sms_index.html',
                         templates=templates,
                         recent_logs=recent_logs,
                         today_sent=today_sent)


@bp.route('/sms/templates')
@login_required
@feature_required(Features.SMS_NOTIFICATIONS)
def sms_templates():
    """Manage SMS templates"""
    templates = SMSTemplate.query.all()
    return render_template('notifications/sms_templates.html', templates=templates)


@bp.route('/sms/templates/add', methods=['POST'])
@login_required
@feature_required(Features.SMS_NOTIFICATIONS)
def add_sms_template():
    """Add SMS template"""
    try:
        template = SMSTemplate(
            name=request.form.get('name'),
            template_type=request.form.get('template_type'),
            message=request.form.get('message'),
            is_active=True
        )
        db.session.add(template)
        db.session.commit()

        return jsonify({'success': True, 'id': template.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@bp.route('/sms/templates/edit/<int:template_id>', methods=['POST'])
@login_required
@feature_required(Features.SMS_NOTIFICATIONS)
def edit_sms_template(template_id):
    """Edit SMS template"""
    template = SMSTemplate.query.get_or_404(template_id)

    template.name = request.form.get('name', template.name)
    template.message = request.form.get('message', template.message)
    template.is_active = request.form.get('is_active') == 'true'

    db.session.commit()
    return jsonify({'success': True})


@bp.route('/sms/send', methods=['POST'])
@login_required
@feature_required(Features.SMS_NOTIFICATIONS)
def send_sms():
    """Send SMS to customer"""
    data = request.get_json()

    customer_id = data.get('customer_id')
    phone = data.get('phone')
    message = data.get('message')
    template_id = data.get('template_id')

    if not phone and not customer_id:
        return jsonify({'success': False, 'error': 'Phone number required'}), 400

    if customer_id:
        customer = Customer.query.get(customer_id)
        if customer:
            phone = customer.phone

    # Get SMS provider config
    config = get_feature_config(Features.SMS_NOTIFICATIONS)
    provider = config.get('provider', '') if config else ''
    api_key = config.get('api_key', '') if config else ''

    if not provider or not api_key:
        return jsonify({'success': False, 'error': 'SMS provider not configured'}), 400

    # Process template placeholders if template used
    if template_id:
        template = SMSTemplate.query.get(template_id)
        if template:
            message = template.message

    # Replace placeholders
    if customer_id:
        customer = Customer.query.get(customer_id)
        if customer:
            message = message.replace('{customer_name}', customer.name or '')
            message = message.replace('{loyalty_points}', str(customer.loyalty_points or 0))

    # Log the SMS (actual sending would be done via provider API)
    log = SMSLog(
        customer_id=customer_id,
        phone_number=phone,
        message=message,
        template_id=template_id,
        status='pending',
        sent_by=current_user.id
    )
    db.session.add(log)
    db.session.commit()

    # Here you would integrate with actual SMS provider
    # For now, we'll simulate success
    result = send_sms_via_provider(phone, message, provider, api_key)

    if result['success']:
        log.status = 'sent'
        log.provider_response = result.get('response')
    else:
        log.status = 'failed'
        log.error_message = result.get('error')

    db.session.commit()

    return jsonify(result)


def send_sms_via_provider(phone, message, provider, api_key):
    """Send SMS via configured provider"""
    # This is a placeholder - implement actual provider integration
    # Supported providers: Twilio, MessageBird, local Pakistani providers

    try:
        # Example for demonstration
        # In production, integrate with actual SMS API

        # For Pakistani providers like Jazz, Telenor, etc.
        # or international like Twilio

        # Simulate success for now
        return {
            'success': True,
            'message_id': f'MSG-{datetime.now().strftime("%Y%m%d%H%M%S")}',
            'response': {'provider': provider, 'status': 'queued'}
        }

    except Exception as e:
        return {'success': False, 'error': str(e)}


@bp.route('/sms/bulk', methods=['GET', 'POST'])
@login_required
@feature_required(Features.SMS_NOTIFICATIONS)
def bulk_sms():
    """Send bulk SMS"""
    if request.method == 'POST':
        template_id = request.form.get('template_id')
        recipient_type = request.form.get('recipient_type')  # all, birthday, due_payment

        customers = []

        if recipient_type == 'all':
            customers = Customer.query.filter_by(is_active=True).all()
        elif recipient_type == 'birthday':
            # Tomorrow's birthdays
            tomorrow = date.today() + timedelta(days=1)
            customers = Customer.query.filter(
                db.extract('month', Customer.birthday) == tomorrow.month,
                db.extract('day', Customer.birthday) == tomorrow.day,
                Customer.is_active == True
            ).all()
        elif recipient_type == 'due_payment':
            # Customers with overdue payments
            overdue = DuePayment.query.filter(
                DuePayment.status != 'paid',
                DuePayment.due_date < date.today()
            ).all()
            customer_ids = [d.customer_id for d in overdue]
            customers = Customer.query.filter(Customer.id.in_(customer_ids)).all()

        sent_count = 0
        for customer in customers:
            if customer.phone:
                # Queue SMS (simplified - in production use async task queue)
                log = SMSLog(
                    customer_id=customer.id,
                    phone_number=customer.phone,
                    message='Bulk message',  # Would be processed from template
                    template_id=template_id,
                    status='pending',
                    sent_by=current_user.id
                )
                db.session.add(log)
                sent_count += 1

        db.session.commit()
        flash(f'Queued {sent_count} SMS messages for sending.', 'success')
        return redirect(url_for('notifications.sms_index'))

    templates = SMSTemplate.query.filter_by(is_active=True).all()
    return render_template('notifications/bulk_sms.html', templates=templates)


# ============================================================
# WHATSAPP NOTIFICATIONS
# ============================================================

@bp.route('/whatsapp')
@login_required
@feature_required(Features.WHATSAPP_NOTIFICATIONS)
def whatsapp_index():
    """WhatsApp notifications dashboard"""
    templates = WhatsAppTemplate.query.all()
    recent_logs = WhatsAppLog.query.order_by(WhatsAppLog.sent_at.desc()).limit(50).all()

    return render_template('notifications/whatsapp_index.html',
                         templates=templates,
                         recent_logs=recent_logs)


@bp.route('/whatsapp/templates')
@login_required
@feature_required(Features.WHATSAPP_NOTIFICATIONS)
def whatsapp_templates():
    """Manage WhatsApp templates"""
    templates = WhatsAppTemplate.query.all()
    return render_template('notifications/whatsapp_templates.html', templates=templates)


@bp.route('/whatsapp/templates/add', methods=['POST'])
@login_required
@feature_required(Features.WHATSAPP_NOTIFICATIONS)
def add_whatsapp_template():
    """Add WhatsApp template"""
    try:
        template = WhatsAppTemplate(
            name=request.form.get('name'),
            template_type=request.form.get('template_type'),
            message=request.form.get('message'),
            has_media=request.form.get('has_media') == 'true',
            media_url=request.form.get('media_url'),
            is_active=True
        )
        db.session.add(template)
        db.session.commit()

        return jsonify({'success': True, 'id': template.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@bp.route('/whatsapp/send', methods=['POST'])
@login_required
@feature_required(Features.WHATSAPP_NOTIFICATIONS)
def send_whatsapp():
    """Send WhatsApp message"""
    data = request.get_json()

    customer_id = data.get('customer_id')
    phone = data.get('phone')
    message = data.get('message')
    template_id = data.get('template_id')

    if not phone and not customer_id:
        return jsonify({'success': False, 'error': 'Phone number required'}), 400

    if customer_id:
        customer = Customer.query.get(customer_id)
        if customer:
            phone = customer.phone

    # Format phone for WhatsApp (add country code)
    if phone.startswith('03'):
        phone = '92' + phone[1:]
    elif not phone.startswith('+') and not phone.startswith('92'):
        phone = '92' + phone

    # Get WhatsApp config
    config = get_feature_config(Features.WHATSAPP_NOTIFICATIONS)

    # Log the message
    log = WhatsAppLog(
        customer_id=customer_id,
        phone_number=phone,
        message=message,
        template_id=template_id,
        status='pending',
        sent_by=current_user.id
    )
    db.session.add(log)
    db.session.commit()

    # Send via WhatsApp Business API
    result = send_whatsapp_via_api(phone, message, config)

    if result['success']:
        log.status = 'sent'
        log.message_id = result.get('message_id')
        log.provider_response = result.get('response')
    else:
        log.status = 'failed'
        log.error_message = result.get('error')

    db.session.commit()

    return jsonify(result)


def send_whatsapp_via_api(phone, message, config):
    """Send WhatsApp message via Business API"""
    # This is a placeholder - implement actual WhatsApp Business API integration
    # Options: Meta Business API, Twilio for WhatsApp, MessageBird

    try:
        # Simulate success for demonstration
        return {
            'success': True,
            'message_id': f'WA-{datetime.now().strftime("%Y%m%d%H%M%S")}',
            'response': {'status': 'sent'}
        }

    except Exception as e:
        return {'success': False, 'error': str(e)}


@bp.route('/whatsapp/quick-send/<int:customer_id>')
@login_required
@feature_required(Features.WHATSAPP_NOTIFICATIONS)
def quick_whatsapp(customer_id):
    """Quick send WhatsApp - opens WhatsApp web"""
    customer = Customer.query.get_or_404(customer_id)

    if not customer.phone:
        flash('Customer does not have a phone number.', 'warning')
        return redirect(url_for('customers.view_customer', customer_id=customer_id))

    # Format phone for WhatsApp
    phone = customer.phone
    if phone.startswith('03'):
        phone = '92' + phone[1:]
    elif phone.startswith('0'):
        phone = '92' + phone[1:]

    # Generate WhatsApp web URL
    whatsapp_url = f'https://wa.me/{phone}'

    return redirect(whatsapp_url)


# ============================================================
# DUE PAYMENT REMINDERS
# ============================================================

@bp.route('/due-reminders')
@login_required
@feature_required(Features.DUE_PAYMENTS)
def due_reminders():
    """View and send due payment reminders"""
    # Get overdue payments
    overdue = DuePayment.query.filter(
        DuePayment.status != 'paid',
        DuePayment.due_date < date.today()
    ).order_by(DuePayment.due_date).all()

    # Get upcoming due
    upcoming = DuePayment.query.filter(
        DuePayment.status != 'paid',
        DuePayment.due_date >= date.today(),
        DuePayment.due_date <= date.today() + timedelta(days=7)
    ).order_by(DuePayment.due_date).all()

    return render_template('notifications/due_reminders.html',
                         overdue=overdue,
                         upcoming=upcoming)


@bp.route('/send-reminder/<int:due_id>', methods=['POST'])
@login_required
def send_due_reminder(due_id):
    """Send reminder for a due payment"""
    due = DuePayment.query.get_or_404(due_id)
    customer = due.customer

    if not customer.phone:
        return jsonify({'success': False, 'error': 'Customer has no phone number'}), 400

    message = f"Dear {customer.name}, this is a friendly reminder that Rs. {due.due_amount} is due since {due.due_date}. Please visit Sunnat Collection to settle your account. Thank you!"

    # Check which notification methods are available
    result = {'sms': False, 'whatsapp': False}

    if is_feature_enabled(Features.SMS_NOTIFICATIONS):
        # Send SMS
        sms_result = send_sms_via_provider(
            customer.phone,
            message,
            get_feature_config(Features.SMS_NOTIFICATIONS, 'provider'),
            get_feature_config(Features.SMS_NOTIFICATIONS, 'api_key')
        )
        result['sms'] = sms_result['success']

    if is_feature_enabled(Features.WHATSAPP_NOTIFICATIONS):
        # Send WhatsApp
        wa_result = send_whatsapp_via_api(
            customer.phone,
            message,
            get_feature_config(Features.WHATSAPP_NOTIFICATIONS)
        )
        result['whatsapp'] = wa_result['success']

    # Update reminder tracking
    due.reminder_sent = True
    due.reminder_count += 1
    due.last_reminder_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'result': result
    })
