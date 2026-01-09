"""
WhatsApp Cloud API Integration
Free Meta WhatsApp Business Platform API for sending receipts
https://developers.facebook.com/docs/whatsapp/cloud-api
"""

import requests
import json
from flask import current_app
from datetime import datetime


class WhatsAppCloudAPI:
    """
    WhatsApp Cloud API wrapper for sending messages

    Free tier includes:
    - Unlimited messages to 5 verified test numbers
    - Free service conversations (customer-initiated)
    - Free utility templates within 24-hour window
    """

    BASE_URL = "https://graph.facebook.com/v18.0"

    def __init__(self, phone_number_id=None, access_token=None):
        """
        Initialize WhatsApp Cloud API

        Args:
            phone_number_id: Your WhatsApp Business Phone Number ID
            access_token: Your permanent access token from Meta
        """
        self.phone_number_id = phone_number_id or current_app.config.get('WHATSAPP_PHONE_NUMBER_ID')
        self.access_token = access_token or current_app.config.get('WHATSAPP_ACCESS_TOKEN')
        self.api_url = f"{self.BASE_URL}/{self.phone_number_id}/messages"

    def _get_headers(self):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def _format_phone(self, phone):
        """
        Format phone number to international format
        Converts Pakistani numbers to 92xxxxxxxxxx format
        """
        phone = ''.join(filter(str.isdigit, str(phone)))

        # Remove leading zeros
        phone = phone.lstrip('0')

        # Add Pakistan country code if not present
        if not phone.startswith('92'):
            if phone.startswith('3'):  # Pakistani mobile numbers start with 3
                phone = '92' + phone

        return phone

    def send_text_message(self, to, message):
        """
        Send a simple text message

        Args:
            to: Recipient phone number
            message: Text message content

        Returns:
            dict: API response with success status
        """
        if not self.phone_number_id or not self.access_token:
            return {
                'success': False,
                'error': 'WhatsApp Cloud API not configured. Please add WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN to your configuration.'
            }

        phone = self._format_phone(to)

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message
            }
        }

        try:
            response = requests.post(
                self.api_url,
                headers=self._get_headers(),
                json=payload,
                timeout=30
            )

            result = response.json()

            if response.status_code == 200:
                return {
                    'success': True,
                    'message_id': result.get('messages', [{}])[0].get('id'),
                    'phone': phone
                }
            else:
                error_msg = result.get('error', {}).get('message', 'Unknown error')
                return {
                    'success': False,
                    'error': error_msg,
                    'details': result
                }

        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Request timeout'}
        except requests.exceptions.RequestException as e:
            return {'success': False, 'error': str(e)}

    def send_template_message(self, to, template_name, language_code="en", components=None):
        """
        Send a pre-approved template message

        Args:
            to: Recipient phone number
            template_name: Name of the approved template
            language_code: Template language (default: en)
            components: Template components (header, body, buttons)

        Returns:
            dict: API response
        """
        if not self.phone_number_id or not self.access_token:
            return {
                'success': False,
                'error': 'WhatsApp Cloud API not configured'
            }

        phone = self._format_phone(to)

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language_code
                }
            }
        }

        if components:
            payload["template"]["components"] = components

        try:
            response = requests.post(
                self.api_url,
                headers=self._get_headers(),
                json=payload,
                timeout=30
            )

            result = response.json()

            if response.status_code == 200:
                return {
                    'success': True,
                    'message_id': result.get('messages', [{}])[0].get('id'),
                    'phone': phone
                }
            else:
                return {
                    'success': False,
                    'error': result.get('error', {}).get('message', 'Unknown error'),
                    'details': result
                }

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def send_receipt(self, to, sale):
        """
        Send a formatted receipt message

        Args:
            to: Recipient phone number
            sale: Sale object with items, total, etc.

        Returns:
            dict: API response
        """
        # Format receipt message
        message = self._format_receipt(sale)
        return self.send_text_message(to, message)

    def _format_receipt(self, sale):
        """Format sale data into a WhatsApp-friendly receipt"""
        from app.models import Setting

        # Get business settings
        try:
            settings = {s.key: s.value for s in Setting.query.all()}
            business_name = settings.get('business_name', 'Sunnat Collection')
        except:
            business_name = 'Sunnat Collection'

        lines = [
            f"*{business_name}*",
            "━━━━━━━━━━━━━━━━━━━━",
            f"📄 Receipt: *{sale.sale_number}*",
            f"📅 Date: {sale.sale_date.strftime('%d %b %Y, %I:%M %p')}",
            "",
            "*Items:*"
        ]

        # Add items
        for item in sale.items:
            lines.append(f"• {item.product.name}")
            lines.append(f"  {item.quantity} × Rs.{item.unit_price:,.0f} = Rs.{item.subtotal:,.0f}")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")

        # Subtotal
        if hasattr(sale, 'subtotal') and sale.subtotal:
            lines.append(f"Subtotal: Rs.{sale.subtotal:,.2f}")

        # Discount
        if sale.discount and sale.discount > 0:
            lines.append(f"Discount: -Rs.{sale.discount:,.2f}")

        # Total
        lines.append(f"*TOTAL: Rs.{sale.total:,.2f}*")
        lines.append("")

        # Payment method
        if sale.is_split_payment:
            lines.append("💳 *Split Payment*")
            for payment in sale.payments:
                lines.append(f"  • {payment.payment_method.title()}: Rs.{payment.amount:,.0f}")
        else:
            lines.append(f"💳 Paid by: {(sale.payment_method or 'Cash').title()}")

        # Customer info
        if sale.customer:
            lines.append("")
            lines.append(f"👤 {sale.customer.name}")
            if sale.customer.loyalty_points:
                lines.append(f"⭐ Loyalty Points: {sale.customer.loyalty_points}")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("Thank you for shopping with us! 🙏")

        return "\n".join(lines)


# Convenience function
def send_whatsapp_receipt(phone, sale):
    """
    Send receipt via WhatsApp Cloud API

    Args:
        phone: Customer phone number
        sale: Sale object

    Returns:
        dict: Result with success status
    """
    api = WhatsAppCloudAPI()
    return api.send_receipt(phone, sale)


def send_whatsapp_message(phone, message):
    """
    Send a text message via WhatsApp Cloud API

    Args:
        phone: Recipient phone number
        message: Message text

    Returns:
        dict: Result with success status
    """
    api = WhatsAppCloudAPI()
    return api.send_text_message(phone, message)


def is_whatsapp_configured():
    """Check if WhatsApp Cloud API is configured"""
    try:
        phone_id = current_app.config.get('WHATSAPP_PHONE_NUMBER_ID')
        token = current_app.config.get('WHATSAPP_ACCESS_TOKEN')
        return bool(phone_id and token)
    except:
        return False
