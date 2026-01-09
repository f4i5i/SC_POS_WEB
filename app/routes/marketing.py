"""
Marketing Routes
SMS/WhatsApp campaign management and automated triggers
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import db, Customer, Sale
from app.models_extended import (
    SMSCampaign, AutomatedTrigger, TriggerLog, SMSTemplate, SMSLog
)
from datetime import datetime, timedelta
from sqlalchemy import func

bp = Blueprint('marketing', __name__)


# Campaign Management
@bp.route('/campaigns')
@login_required
def campaigns():
    """List all marketing campaigns"""
    if current_user.role not in ['admin', 'manager']:
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    campaigns = SMSCampaign.query.order_by(SMSCampaign.created_at.desc()).all()
    templates = SMSTemplate.query.filter_by(is_active=True).all()

    return render_template('marketing/campaigns.html',
                         campaigns=campaigns,
                         templates=templates)


@bp.route('/campaigns/create', methods=['GET', 'POST'])
@login_required
def create_campaign():
    """Create a new marketing campaign"""
    if current_user.role not in ['admin', 'manager']:
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        campaign = SMSCampaign(
            name=request.form.get('name'),
            campaign_type=request.form.get('campaign_type', 'one_time'),
            template_id=int(request.form.get('template_id')) if request.form.get('template_id') else None,
            target_audience=request.form.get('target_audience', 'all'),
            target_criteria=request.form.get('target_criteria', '{}'),
            scheduled_at=datetime.strptime(request.form.get('scheduled_at'), '%Y-%m-%dT%H:%M') if request.form.get('scheduled_at') else None,
            status='draft',
            channel=request.form.get('channel', 'sms'),
            created_by_id=current_user.id
        )
        db.session.add(campaign)
        db.session.commit()

        flash(f'Campaign "{campaign.name}" created successfully!', 'success')
        return redirect(url_for('marketing.campaigns'))

    templates = SMSTemplate.query.filter_by(is_active=True).all()
    return render_template('marketing/create_campaign.html', templates=templates)


@bp.route('/campaigns/<int:campaign_id>/send', methods=['POST'])
@login_required
def send_campaign(campaign_id):
    """Execute/send a campaign"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    campaign = SMSCampaign.query.get_or_404(campaign_id)

    if campaign.status == 'completed':
        return jsonify({'success': False, 'error': 'Campaign already completed'}), 400

    # Get target customers
    customers = get_campaign_targets(campaign)

    if not customers:
        return jsonify({'success': False, 'error': 'No customers match the target criteria'}), 400

    # Get template
    template = SMSTemplate.query.get(campaign.template_id) if campaign.template_id else None
    message = template.message if template else 'Thank you for being a valued customer!'

    # Send messages
    sent_count = 0
    failed_count = 0

    for customer in customers:
        try:
            # Personalize message
            personalized_msg = personalize_message(message, customer)

            # Send via appropriate channel
            if campaign.channel in ['sms', 'both']:
                send_sms_to_customer(customer, personalized_msg, campaign.id)
                sent_count += 1

            if campaign.channel in ['whatsapp', 'both']:
                send_whatsapp_to_customer(customer, personalized_msg, campaign.id)
                sent_count += 1

        except Exception as e:
            failed_count += 1
            continue

    # Update campaign status
    campaign.status = 'completed'
    campaign.sent_count = sent_count
    campaign.failed_count = failed_count
    campaign.completed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'sent': sent_count,
        'failed': failed_count,
        'message': f'Campaign sent to {sent_count} customers'
    })


@bp.route('/campaigns/<int:campaign_id>/preview')
@login_required
def preview_campaign(campaign_id):
    """Preview campaign recipients"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    campaign = SMSCampaign.query.get_or_404(campaign_id)
    customers = get_campaign_targets(campaign)

    return jsonify({
        'success': True,
        'count': len(customers),
        'preview': [{
            'id': c.id,
            'name': c.name,
            'phone': c.phone,
            'tier': c.loyalty_tier
        } for c in customers[:20]]  # Show first 20
    })


@bp.route('/campaigns/<int:campaign_id>/delete', methods=['POST'])
@login_required
def delete_campaign(campaign_id):
    """Delete a campaign"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    campaign = SMSCampaign.query.get_or_404(campaign_id)

    if campaign.status == 'completed':
        return jsonify({'success': False, 'error': 'Cannot delete completed campaigns'}), 400

    db.session.delete(campaign)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Campaign deleted'})


# Automated Triggers Management
@bp.route('/triggers')
@login_required
def triggers():
    """List all automated triggers"""
    if current_user.role not in ['admin', 'manager']:
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    triggers = AutomatedTrigger.query.order_by(AutomatedTrigger.created_at.desc()).all()
    templates = SMSTemplate.query.filter_by(is_active=True).all()

    return render_template('marketing/triggers.html',
                         triggers=triggers,
                         templates=templates)


@bp.route('/triggers/create', methods=['GET', 'POST'])
@login_required
def create_trigger():
    """Create a new automated trigger"""
    if current_user.role not in ['admin', 'manager']:
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        trigger = AutomatedTrigger(
            name=request.form.get('name'),
            trigger_type=request.form.get('trigger_type'),
            trigger_days=int(request.form.get('trigger_days', 0)),
            template_id=int(request.form.get('template_id')) if request.form.get('template_id') else None,
            channel=request.form.get('channel', 'sms'),
            is_active=True
        )
        db.session.add(trigger)
        db.session.commit()

        flash(f'Trigger "{trigger.name}" created successfully!', 'success')
        return redirect(url_for('marketing.triggers'))

    templates = SMSTemplate.query.filter_by(is_active=True).all()
    return render_template('marketing/create_trigger.html', templates=templates)


@bp.route('/triggers/<int:trigger_id>/toggle', methods=['POST'])
@login_required
def toggle_trigger(trigger_id):
    """Toggle trigger active status"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    trigger = AutomatedTrigger.query.get_or_404(trigger_id)
    trigger.is_active = not trigger.is_active
    db.session.commit()

    return jsonify({'success': True, 'is_active': trigger.is_active})


@bp.route('/triggers/<int:trigger_id>/run', methods=['POST'])
@login_required
def run_trigger(trigger_id):
    """Manually run a trigger"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    trigger = AutomatedTrigger.query.get_or_404(trigger_id)

    # Find matching customers and send messages
    result = process_single_trigger(trigger)

    return jsonify({
        'success': True,
        'sent': result['sent'],
        'message': f'Trigger sent to {result["sent"]} customers'
    })


@bp.route('/triggers/<int:trigger_id>/delete', methods=['POST'])
@login_required
def delete_trigger(trigger_id):
    """Delete a trigger"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    trigger = AutomatedTrigger.query.get_or_404(trigger_id)

    # Delete associated logs first
    TriggerLog.query.filter_by(trigger_id=trigger_id).delete()

    db.session.delete(trigger)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Trigger deleted'})


# Helper functions
def get_campaign_targets(campaign):
    """Get list of customers matching campaign criteria"""
    query = Customer.query.filter_by(is_active=True)

    if campaign.target_audience == 'all':
        query = query.filter(Customer.sms_optin == True)

    elif campaign.target_audience == 'loyalty_tier':
        import json
        criteria = json.loads(campaign.target_criteria or '{}')
        tier = criteria.get('tier', 'Bronze')
        query = query.filter(Customer.sms_optin == True)
        # Filter by loyalty tier based on points
        if tier == 'Platinum':
            query = query.filter(Customer.loyalty_points >= 2500)
        elif tier == 'Gold':
            query = query.filter(Customer.loyalty_points >= 1000, Customer.loyalty_points < 2500)
        elif tier == 'Silver':
            query = query.filter(Customer.loyalty_points >= 500, Customer.loyalty_points < 1000)
        else:
            query = query.filter(Customer.loyalty_points < 500)

    elif campaign.target_audience == 'inactive':
        # Customers with no purchase in last 30 days
        import json
        criteria = json.loads(campaign.target_criteria or '{}')
        days = criteria.get('days', 30)
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Get active customer IDs
        active_customer_ids = db.session.query(Sale.customer_id).filter(
            Sale.created_at >= cutoff_date,
            Sale.customer_id.isnot(None)
        ).distinct().subquery()

        query = query.filter(
            Customer.sms_optin == True,
            ~Customer.id.in_(active_customer_ids)
        )

    elif campaign.target_audience == 'birthday_month':
        current_month = datetime.utcnow().month
        query = query.filter(
            Customer.sms_optin == True,
            func.extract('month', Customer.birthday) == current_month
        )

    return query.all()


def personalize_message(message, customer):
    """Replace placeholders with customer data"""
    return message.replace('{name}', customer.name or 'Valued Customer')\
                  .replace('{phone}', customer.phone or '')\
                  .replace('{points}', str(customer.loyalty_points or 0))\
                  .replace('{tier}', customer.loyalty_tier or 'Bronze')


def send_sms_to_customer(customer, message, campaign_id=None):
    """Send SMS to a customer and log it"""
    if not customer.phone or not customer.sms_optin:
        return False

    # Log the SMS
    sms_log = SMSLog(
        customer_id=customer.id,
        phone=customer.phone,
        message=message,
        status='pending',
        sent_at=datetime.utcnow()
    )
    db.session.add(sms_log)

    # Try to send via configured provider
    try:
        from app.utils.twilio_service import send_sms
        result = send_sms(customer.phone, message)
        if result.get('success'):
            sms_log.status = 'sent'
            sms_log.provider_message_id = result.get('message_sid')
        else:
            sms_log.status = 'failed'
            sms_log.error_message = result.get('error')
    except Exception as e:
        sms_log.status = 'failed'
        sms_log.error_message = str(e)

    db.session.commit()
    return sms_log.status == 'sent'


def send_whatsapp_to_customer(customer, message, campaign_id=None):
    """Send WhatsApp to a customer"""
    if not customer.phone or not customer.whatsapp_optin:
        return False

    try:
        from app.utils.twilio_service import send_whatsapp_message
        result = send_whatsapp_message(customer.phone, message)
        return result.get('success', False)
    except Exception as e:
        return False


def process_single_trigger(trigger):
    """Process a single automated trigger"""
    sent = 0
    template = SMSTemplate.query.get(trigger.template_id) if trigger.template_id else None
    message = template.message if template else 'Thank you for being a valued customer!'

    customers = []

    if trigger.trigger_type == 'no_purchase_days':
        # Customers with no purchase in X days
        cutoff_date = datetime.utcnow() - timedelta(days=trigger.trigger_days)

        # Get customers who haven't purchased since cutoff
        active_customer_ids = db.session.query(Sale.customer_id).filter(
            Sale.created_at >= cutoff_date,
            Sale.customer_id.isnot(None)
        ).distinct()

        customers = Customer.query.filter(
            Customer.is_active == True,
            Customer.sms_optin == True,
            ~Customer.id.in_(active_customer_ids)
        ).all()

    elif trigger.trigger_type == 'birthday_reminder':
        # Customers with birthday in X days
        target_date = datetime.utcnow().date() + timedelta(days=trigger.trigger_days)
        customers = Customer.query.filter(
            Customer.is_active == True,
            Customer.sms_optin == True,
            func.extract('month', Customer.birthday) == target_date.month,
            func.extract('day', Customer.birthday) == target_date.day
        ).all()

    elif trigger.trigger_type == 'loyalty_milestone':
        # Customers who just reached a milestone (handled during sale)
        pass

    # Send messages
    for customer in customers:
        # Check if already triggered today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        existing = TriggerLog.query.filter(
            TriggerLog.trigger_id == trigger.id,
            TriggerLog.customer_id == customer.id,
            TriggerLog.triggered_at >= today_start
        ).first()

        if existing:
            continue

        personalized_msg = personalize_message(message, customer)

        success = False
        if trigger.channel in ['sms', 'both']:
            success = send_sms_to_customer(customer, personalized_msg)

        if trigger.channel in ['whatsapp', 'both']:
            success = send_whatsapp_to_customer(customer, personalized_msg) or success

        # Log the trigger
        trigger_log = TriggerLog(
            trigger_id=trigger.id,
            customer_id=customer.id,
            triggered_at=datetime.utcnow(),
            message_sent=success,
            channel_used=trigger.channel
        )
        db.session.add(trigger_log)

        if success:
            sent += 1

    # Update trigger stats
    trigger.times_triggered = (trigger.times_triggered or 0) + sent
    trigger.last_triggered_at = datetime.utcnow()
    db.session.commit()

    return {'sent': sent}


# Background task to process all triggers (called by cron/scheduler)
def process_all_triggers():
    """Process all active automated triggers"""
    active_triggers = AutomatedTrigger.query.filter_by(is_active=True).all()
    total_sent = 0

    for trigger in active_triggers:
        result = process_single_trigger(trigger)
        total_sent += result['sent']

    return total_sent
