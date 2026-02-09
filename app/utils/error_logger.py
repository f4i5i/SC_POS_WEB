"""
Error Logger Utility
Captures application errors to the database with request context.
"""

import traceback
import json
from datetime import datetime
from flask import request, has_request_context
from flask_login import current_user


# Keys to redact from request data
SENSITIVE_KEYS = {
    'password', 'password_hash', 'token', 'csrf_token', 'secret',
    'api_key', 'authorization', 'cookie', 'session', 'credit_card',
    'card_number', 'cvv', 'pin', 'otp'
}


def _sanitize_data(data):
    """Redact sensitive keys from a dict."""
    if not isinstance(data, dict):
        return data
    sanitized = {}
    for key, value in data.items():
        if any(s in key.lower() for s in SENSITIVE_KEYS):
            sanitized[key] = '[REDACTED]'
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_data(value)
        else:
            sanitized[key] = str(value)[:500]  # Truncate long values
    return sanitized


def log_error(error, status_code=500):
    """
    Log an error to the database.

    This function is safe to call from error handlers - it catches
    all internal exceptions so it never crashes the app.

    Args:
        error: The exception or error object
        status_code: HTTP status code (default 500)
    """
    try:
        from app.models import db, ErrorLog

        error_type = type(error).__name__ if hasattr(error, '__class__') else 'Unknown'
        error_message = str(error)[:2000]
        tb = traceback.format_exc() if traceback.format_exc() != 'NoneType: None\n' else None

        # Get request context info
        request_url = None
        request_method = None
        request_data = None
        user_id = None
        ip_address = None
        user_agent = None
        blueprint_name = None
        endpoint_name = None

        if has_request_context():
            request_url = request.url[:512] if request.url else None
            request_method = request.method
            ip_address = request.remote_addr
            user_agent = str(request.user_agent)[:512] if request.user_agent else None
            blueprint_name = request.blueprints[0] if request.blueprints else None
            endpoint_name = request.endpoint

            # Collect and sanitize request data
            try:
                raw_data = {}
                if request.form:
                    raw_data['form'] = dict(request.form)
                if request.args:
                    raw_data['args'] = dict(request.args)
                if request.is_json and request.get_json(silent=True):
                    raw_data['json'] = request.get_json(silent=True)
                if raw_data:
                    request_data = json.dumps(_sanitize_data(raw_data))[:4000]
            except Exception:
                request_data = None

            # Get user ID safely
            try:
                if current_user and current_user.is_authenticated:
                    user_id = current_user.id
            except Exception:
                user_id = None

        error_log = ErrorLog(
            timestamp=datetime.utcnow(),
            error_type=error_type,
            error_message=error_message,
            traceback=tb,
            request_url=request_url,
            request_method=request_method,
            request_data=request_data,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            status_code=status_code,
            blueprint=blueprint_name,
            endpoint=endpoint_name,
            is_resolved=False
        )

        db.session.add(error_log)
        db.session.commit()
        return error_log

    except Exception:
        # Never let the error logger crash the app
        try:
            from app.models import db
            db.session.rollback()
        except Exception:
            pass
        return None
