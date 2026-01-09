"""
Twilio Service for WhatsApp and SMS
Handles sending messages via Twilio API
"""

from flask import current_app


def get_twilio_config():
    """Get Twilio configuration from app config or feature flags"""
    config = {
        'account_sid': current_app.config.get('TWILIO_ACCOUNT_SID'),
        'auth_token': current_app.config.get('TWILIO_AUTH_TOKEN'),
        'whatsapp_number': current_app.config.get('TWILIO_WHATSAPP_NUMBER'),
        'sms_number': current_app.config.get('TWILIO_SMS_NUMBER')
    }

    # Try feature flags if not in app config
    if not config['account_sid']:
        try:
            from app.models_extended import FeatureFlag
            from app.utils.feature_flags import Features

            flag = FeatureFlag.query.filter_by(name=Features.WHATSAPP_NOTIFICATIONS).first()
            if flag and flag.config:
                config.update(flag.config)
        except Exception:
            pass

    return config


def send_whatsapp_message(phone, message, media_url=None):
    """
    Send WhatsApp message via Twilio API

    Args:
        phone: Phone number (without + prefix, e.g., '923001234567')
        message: Text message to send
        media_url: Optional media URL to attach

    Returns:
        dict with success status and message_sid or error
    """
    config = get_twilio_config()

    if not config.get('account_sid') or not config.get('auth_token'):
        return {
            'success': False,
            'error': 'Twilio credentials not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.'
        }

    try:
        from twilio.rest import Client

        client = Client(config['account_sid'], config['auth_token'])

        # Format phone numbers
        from_number = config.get('whatsapp_number', '+14155238886')  # Twilio sandbox default
        if not from_number.startswith('whatsapp:'):
            from_number = f'whatsapp:{from_number}'

        to_number = f'whatsapp:+{phone}'

        # Build message params
        msg_params = {
            'body': message,
            'from_': from_number,
            'to': to_number
        }

        if media_url:
            msg_params['media_url'] = [media_url]

        # Send message
        twilio_message = client.messages.create(**msg_params)

        return {
            'success': True,
            'message_sid': twilio_message.sid,
            'status': twilio_message.status,
            'method': 'twilio_api'
        }

    except ImportError:
        return {
            'success': False,
            'error': 'Twilio library not installed. Run: pip install twilio'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def send_sms(phone, message):
    """
    Send SMS via Twilio API

    Args:
        phone: Phone number (without + prefix)
        message: Text message to send

    Returns:
        dict with success status and message_sid or error
    """
    config = get_twilio_config()

    if not config.get('account_sid') or not config.get('auth_token'):
        return {
            'success': False,
            'error': 'Twilio credentials not configured.'
        }

    try:
        from twilio.rest import Client

        client = Client(config['account_sid'], config['auth_token'])

        from_number = config.get('sms_number')
        if not from_number:
            return {
                'success': False,
                'error': 'SMS phone number not configured. Set TWILIO_SMS_NUMBER.'
            }

        twilio_message = client.messages.create(
            body=message,
            from_=from_number,
            to=f'+{phone}'
        )

        return {
            'success': True,
            'message_sid': twilio_message.sid,
            'status': twilio_message.status
        }

    except ImportError:
        return {
            'success': False,
            'error': 'Twilio library not installed. Run: pip install twilio'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def get_whatsapp_web_link(phone, message):
    """
    Generate WhatsApp Web link for manual sending

    Args:
        phone: Phone number (without + prefix)
        message: Text message

    Returns:
        WhatsApp Web URL
    """
    import urllib.parse
    encoded_message = urllib.parse.quote(message)
    return f'https://wa.me/{phone}?text={encoded_message}'
