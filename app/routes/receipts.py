"""
Digital Receipt Routes
Handles email, WhatsApp, and QR code receipt delivery
"""

from flask import Blueprint, render_template, request, jsonify, url_for, current_app
from flask_login import login_required, current_user
from datetime import datetime
import secrets

from app.models import db, Sale, Customer, DigitalReceipt, Setting

bp = Blueprint('receipts', __name__)


def get_business_settings():
    """Get business settings for receipt"""
    settings = Setting.query.all()
    return {s.key: s.value for s in settings}


@bp.route('/send-email/<int:sale_id>', methods=['POST'])
@login_required
def send_email_receipt(sale_id):
    """Send receipt via email"""
    try:
        sale = Sale.query.get_or_404(sale_id)
        data = request.get_json() or {}

        # Get email from request or customer
        email = data.get('email')
        if not email and sale.customer and sale.customer.email:
            email = sale.customer.email

        if not email:
            return jsonify({'success': False, 'error': 'No email address provided'}), 400

        # Generate receipt content
        settings = get_business_settings()
        receipt_html = render_template('receipts/email_receipt.html',
                                       sale=sale,
                                       settings=settings,
                                       business_name=settings.get('business_name', 'Sunnat Collection'))

        # Try to send email
        try:
            from app.utils.email_service import send_email
            result = send_email(
                to=email,
                subject=f"Your Receipt - {sale.sale_number}",
                html_content=receipt_html
            )
            status = 'sent' if result.get('success') else 'failed'
            error_msg = result.get('error') if not result.get('success') else None
        except Exception as e:
            status = 'failed'
            error_msg = str(e)

        # Log the digital receipt
        receipt = DigitalReceipt(
            sale_id=sale.id,
            customer_id=sale.customer_id,
            delivery_method='email',
            recipient=email,
            status=status,
            sent_at=datetime.utcnow() if status == 'sent' else None,
            error_message=error_msg
        )
        db.session.add(receipt)
        db.session.commit()

        if status == 'sent':
            return jsonify({'success': True, 'message': f'Receipt sent to {email}'})
        else:
            return jsonify({'success': False, 'error': error_msg or 'Failed to send email'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/send-whatsapp/<int:sale_id>', methods=['POST'])
@login_required
def send_whatsapp_receipt(sale_id):
    """
    Send receipt via WhatsApp
    Priority: 1. WhatsApp Cloud API (free), 2. Twilio, 3. wa.me link
    """
    try:
        sale = Sale.query.get_or_404(sale_id)
        data = request.get_json() or {}

        # Get phone from request or customer
        phone = data.get('phone')
        if not phone and sale.customer and sale.customer.phone:
            phone = sale.customer.phone

        if not phone:
            return jsonify({'success': False, 'error': 'No phone number provided'}), 400

        # Format phone for WhatsApp (Pakistani format)
        phone = phone.strip().replace(' ', '').replace('-', '')
        if phone.startswith('03'):
            phone = '92' + phone[1:]
        elif phone.startswith('+'):
            phone = phone[1:]

        # Determine which API to use
        use_api = data.get('use_api', True)  # Default to using API if available
        method_used = 'wa_link'
        result = None
        status = 'pending'

        if use_api:
            # Try WhatsApp Cloud API first (FREE)
            try:
                from app.utils.whatsapp_cloud import send_whatsapp_receipt as cloud_send, is_whatsapp_configured
                if is_whatsapp_configured():
                    result = cloud_send(phone, sale)
                    if result.get('success'):
                        status = 'sent'
                        method_used = 'whatsapp_cloud_api'
                        current_app.logger.info(f"Receipt sent via WhatsApp Cloud API to {phone}")
            except Exception as e:
                current_app.logger.warning(f"WhatsApp Cloud API failed: {e}")

            # Fallback to Twilio if Cloud API not configured or failed
            if not result or not result.get('success'):
                try:
                    from app.utils.twilio_service import send_whatsapp_message
                    receipt_text = generate_whatsapp_receipt_text(sale)
                    result = send_whatsapp_message(phone, receipt_text)
                    if result.get('success'):
                        status = 'sent'
                        method_used = 'twilio'
                        current_app.logger.info(f"Receipt sent via Twilio to {phone}")
                except Exception as e:
                    current_app.logger.warning(f"Twilio API failed: {e}")

        # Final fallback: wa.me link (always works)
        if not result or not result.get('success'):
            import urllib.parse
            receipt_text = generate_whatsapp_receipt_text(sale)
            encoded_message = urllib.parse.quote(receipt_text)
            wa_link = f'https://wa.me/{phone}?text={encoded_message}'
            result = {
                'success': True,
                'link': wa_link,
                'method': 'wa_link',
                'message': 'Click the link to send via WhatsApp'
            }
            status = 'pending'
            method_used = 'wa_link'

        # Log the digital receipt
        receipt = DigitalReceipt(
            sale_id=sale.id,
            customer_id=sale.customer_id,
            delivery_method='whatsapp',
            recipient=phone,
            status=status,
            sent_at=datetime.utcnow() if status == 'sent' else None,
            provider_response=f"method: {method_used}"
        )
        db.session.add(receipt)
        db.session.commit()

        # Add method info to response
        result['method'] = method_used
        if status == 'sent':
            result['message'] = f'Receipt sent to WhatsApp ({method_used})'

        return jsonify(result)

    except Exception as e:
        current_app.logger.error(f"WhatsApp receipt error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/generate-qr/<int:sale_id>')
@login_required
def generate_receipt_qr(sale_id):
    """Generate QR code for receipt lookup"""
    try:
        sale = Sale.query.get_or_404(sale_id)

        # Check if QR already exists for this sale
        existing = DigitalReceipt.query.filter_by(
            sale_id=sale_id,
            delivery_method='qr_code'
        ).first()

        if existing and existing.receipt_token:
            token = existing.receipt_token
        else:
            # Generate unique token
            token = secrets.token_urlsafe(16)

            # Log the digital receipt
            receipt = DigitalReceipt(
                sale_id=sale.id,
                customer_id=sale.customer_id,
                delivery_method='qr_code',
                recipient='self-lookup',
                receipt_token=token,
                status='generated'
            )
            db.session.add(receipt)
            db.session.commit()

        # Generate QR code
        receipt_url = url_for('receipts.view_receipt', token=token, _external=True)

        try:
            import qrcode
            import io
            import base64

            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(receipt_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            qr_base64 = base64.b64encode(buffer.getvalue()).decode()

            return jsonify({
                'success': True,
                'qr_code': f'data:image/png;base64,{qr_base64}',
                'token': token,
                'url': receipt_url
            })
        except ImportError:
            # QR code library not installed
            return jsonify({
                'success': True,
                'token': token,
                'url': receipt_url,
                'qr_code': None,
                'message': 'QR code library not installed. Use URL instead.'
            })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/view/<token>')
def view_receipt(token):
    """Public receipt view page (no login required)"""
    receipt = DigitalReceipt.query.filter_by(receipt_token=token).first_or_404()
    sale = receipt.sale

    # Mark as delivered
    if receipt.status != 'delivered':
        receipt.status = 'delivered'
        receipt.delivered_at = datetime.utcnow()
        db.session.commit()

    # Get business settings
    settings = get_business_settings()

    return render_template('receipts/public_receipt.html',
                           sale=sale,
                           settings=settings,
                           business_name=settings.get('business_name', 'Sunnat Collection'))


def generate_whatsapp_receipt_text(sale):
    """Generate formatted receipt text for WhatsApp"""
    settings = get_business_settings()
    business_name = settings.get('business_name', 'SUNNAT COLLECTION')

    lines = []
    lines.append(f"*{business_name}*")
    lines.append("------------------------")
    lines.append(f"Receipt: {sale.sale_number}")
    lines.append(f"Date: {sale.sale_date.strftime('%d %b %Y %H:%M')}")
    lines.append("")
    lines.append("*Items:*")

    for item in sale.items:
        lines.append(f"- {item.product.name}")
        lines.append(f"  Qty: {item.quantity} x Rs.{item.unit_price:,.0f} = Rs.{item.subtotal:,.0f}")

    lines.append("")

    if sale.discount and sale.discount > 0:
        lines.append(f"Subtotal: Rs.{sale.subtotal:,.0f}")
        lines.append(f"Discount: -Rs.{sale.discount:,.0f}")

    lines.append(f"*TOTAL: Rs.{sale.total:,.0f}*")

    # Payment info
    if sale.is_split_payment:
        lines.append("")
        lines.append("*Payment (Split):*")
        for payment in sale.payments:
            lines.append(f"- {payment.payment_method.title()}: Rs.{payment.amount:,.0f}")
    else:
        lines.append(f"Paid by: {sale.payment_method.upper()}")

    # Loyalty info
    if sale.customer:
        lines.append("")
        lines.append(f"Customer: {sale.customer.name}")
        lines.append(f"Loyalty Points: {sale.customer.loyalty_points}")
        lines.append(f"Tier: {sale.customer.loyalty_tier}")

    lines.append("")
    lines.append("Thank you for shopping!")

    return "\n".join(lines)
