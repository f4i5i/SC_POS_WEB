"""
Error Logger Utility
Captures application errors to the database with full request context,
source file/line information, and structured traceback.
"""

import traceback
import sys
import json
import os
from datetime import datetime
from flask import request, has_request_context, current_app
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
            sanitized[key] = str(value)[:500]
    return sanitized


def _extract_source_info(error):
    """
    Extract source file, line number, and function name from the exception.
    Returns (file_path, line_number, function_name, code_line).
    """
    file_path = None
    line_number = None
    function_name = None
    code_line = None

    try:
        # Try to get from current exception info
        exc_type, exc_value, exc_tb = sys.exc_info()

        if exc_tb is not None:
            # Walk to the innermost frame (actual error location)
            tb = exc_tb
            while tb.tb_next:
                tb = tb.tb_next

            frame = tb.tb_frame
            file_path = frame.f_code.co_filename
            line_number = tb.tb_lineno
            function_name = frame.f_code.co_name

            # Try to get the actual code line
            try:
                import linecache
                code_line = linecache.getline(file_path, line_number).strip()
            except Exception:
                pass

        elif hasattr(error, '__traceback__') and error.__traceback__:
            # Fallback: get from the error's own traceback
            tb = error.__traceback__
            while tb.tb_next:
                tb = tb.tb_next

            frame = tb.tb_frame
            file_path = frame.f_code.co_filename
            line_number = tb.tb_lineno
            function_name = frame.f_code.co_name

            try:
                import linecache
                code_line = linecache.getline(file_path, line_number).strip()
            except Exception:
                pass

    except Exception:
        pass

    # Make file path relative to project root for readability
    if file_path:
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if file_path.startswith(project_root):
                file_path = file_path[len(project_root) + 1:]
        except Exception:
            pass

    return file_path, line_number, function_name, code_line


def _get_full_traceback(error):
    """
    Get the full formatted traceback string.
    Tries multiple methods to ensure we capture it.
    """
    # Method 1: format_exc from current exception context
    tb_str = traceback.format_exc()
    if tb_str and tb_str != 'NoneType: None\n':
        return tb_str[:8000]

    # Method 2: format from error's own traceback
    if hasattr(error, '__traceback__') and error.__traceback__:
        lines = traceback.format_exception(type(error), error, error.__traceback__)
        return ''.join(lines)[:8000]

    # Method 3: basic string representation
    return f"{type(error).__name__}: {str(error)}"


def _get_request_context():
    """Extract all useful request context information."""
    context = {
        'url': None,
        'method': None,
        'data': None,
        'user_id': None,
        'ip_address': None,
        'user_agent': None,
        'blueprint': None,
        'endpoint': None,
        'referrer': None,
        'headers_summary': None,
    }

    if not has_request_context():
        return context

    try:
        context['url'] = request.url[:512] if request.url else None
        context['method'] = request.method
        context['ip_address'] = request.remote_addr
        context['user_agent'] = str(request.user_agent)[:512] if request.user_agent else None
        context['blueprint'] = request.blueprints[0] if request.blueprints else None
        context['endpoint'] = request.endpoint
        context['referrer'] = request.referrer[:512] if request.referrer else None
    except Exception:
        pass

    # Request data (sanitized)
    try:
        raw_data = {}
        if request.form:
            raw_data['form'] = dict(request.form)
        if request.args:
            raw_data['args'] = dict(request.args)
        if request.is_json and request.get_json(silent=True):
            raw_data['json'] = request.get_json(silent=True)
        if raw_data:
            context['data'] = json.dumps(_sanitize_data(raw_data))[:4000]
    except Exception:
        pass

    # User ID
    try:
        if current_user and current_user.is_authenticated:
            context['user_id'] = current_user.id
    except Exception:
        pass

    return context


def log_error(error, status_code=500):
    """
    Log an error to the database with full context.

    Captures:
    - Error type, message, and full traceback
    - Source file, line number, function name, and offending code line
    - Request URL, method, parameters, referrer
    - User identity, IP address, browser info
    - Blueprint and endpoint names

    This function is safe to call from error handlers — it catches
    all internal exceptions so it never crashes the app.

    Args:
        error: The exception or error object
        status_code: HTTP status code (default 500)
    """
    try:
        from app.models import db, ErrorLog

        # Error basics
        error_type = type(error).__name__ if hasattr(error, '__class__') else 'Unknown'
        error_message = str(error)[:2000]

        # Full traceback
        tb = _get_full_traceback(error)

        # Source location
        source_file, source_line, source_function, code_line = _extract_source_info(error)

        # Build enhanced error message with source info
        enhanced_message = error_message
        if source_file and source_line:
            location_str = f"\n\n--- Source ---\nFile: {source_file}\nLine: {source_line}\nFunction: {source_function or 'unknown'}"
            if code_line:
                location_str += f"\nCode: {code_line}"
            enhanced_message = enhanced_message + location_str

        # Request context
        ctx = _get_request_context()

        # Also log to Flask logger for console/file output
        try:
            log_parts = [
                f"\n{'='*70}",
                f"ERROR [{status_code}] {error_type}: {error_message}",
            ]
            if source_file and source_line:
                log_parts.append(f"  File: {source_file}:{source_line} in {source_function or '?'}()")
                if code_line:
                    log_parts.append(f"  Code: {code_line}")
            if ctx['url']:
                log_parts.append(f"  URL: {ctx['method']} {ctx['url']}")
            if ctx['user_id']:
                log_parts.append(f"  User: {ctx['user_id']}")
            log_parts.append(f"{'='*70}")
            current_app.logger.error('\n'.join(log_parts))
        except Exception:
            pass

        error_log = ErrorLog(
            timestamp=datetime.utcnow(),
            error_type=error_type,
            error_message=enhanced_message[:2000],
            traceback=tb,
            request_url=ctx['url'],
            request_method=ctx['method'],
            request_data=ctx['data'],
            user_id=ctx['user_id'],
            ip_address=ctx['ip_address'],
            user_agent=ctx['user_agent'],
            status_code=status_code,
            blueprint=ctx['blueprint'],
            endpoint=ctx['endpoint'],
            is_resolved=False
        )

        db.session.add(error_log)
        db.session.commit()
        return error_log

    except Exception as log_error_exc:
        # Never let the error logger crash the app
        try:
            # At least print to stderr so it's not completely silent
            print(f"[ERROR LOGGER FAILED] Original error: {error}", file=sys.stderr)
            print(f"[ERROR LOGGER FAILED] Logger error: {log_error_exc}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            from app.models import db
            db.session.rollback()
        except Exception:
            pass
        return None
