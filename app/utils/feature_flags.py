"""
Feature Flags Utility
Manage feature toggles for the application
"""

from functools import wraps
from flask import abort, flash, redirect, url_for, request, jsonify, g
from flask_login import current_user


def is_feature_enabled(feature_name):
    """
    Check if a feature is enabled

    Args:
        feature_name: Name of the feature flag

    Returns:
        bool: True if feature is enabled and configured (if required)
    """
    from app.models_extended import FeatureFlag

    flag = FeatureFlag.query.filter_by(name=feature_name).first()
    if flag:
        # Feature must be enabled AND configured (if required)
        if flag.requires_config:
            return flag.is_enabled and flag.is_configured
        return flag.is_enabled
    return False


def get_feature_config(feature_name, key=None, default=None):
    """
    Get configuration for a feature

    Args:
        feature_name: Name of the feature flag
        key: Optional specific config key
        default: Default value if not found

    Returns:
        Configuration value or dict
    """
    from app.models_extended import FeatureFlag

    flag = FeatureFlag.query.filter_by(name=feature_name).first()
    if flag and flag.config:
        if key:
            return flag.config.get(key, default)
        return flag.config
    return default


def set_feature_enabled(feature_name, enabled, user_id=None):
    """
    Enable or disable a feature

    Args:
        feature_name: Name of the feature flag
        enabled: Boolean to enable/disable
        user_id: User who changed the setting
    """
    from app.models_extended import FeatureFlag
    from app.models import db
    from datetime import datetime

    flag = FeatureFlag.query.filter_by(name=feature_name).first()
    if flag:
        flag.is_enabled = enabled
        if enabled:
            flag.enabled_by = user_id
            flag.enabled_at = datetime.utcnow()
        db.session.commit()
        return True
    return False


def update_feature_config(feature_name, config_updates):
    """
    Update configuration for a feature

    Args:
        feature_name: Name of the feature flag
        config_updates: Dict of config updates
    """
    from app.models_extended import FeatureFlag
    from app.models import db

    flag = FeatureFlag.query.filter_by(name=feature_name).first()
    if flag:
        if flag.config is None:
            flag.config = {}

        # Merge updates into existing config
        current_config = dict(flag.config)
        current_config.update(config_updates)
        flag.config = current_config

        # Check if all required config is present
        if flag.requires_config:
            # Consider it configured if any non-empty values exist
            has_config = any(v for v in current_config.values() if v)
            flag.is_configured = has_config

        db.session.commit()
        return True
    return False


def get_all_features(category=None):
    """
    Get all feature flags

    Args:
        category: Optional category filter

    Returns:
        List of FeatureFlag objects
    """
    from app.models_extended import FeatureFlag

    query = FeatureFlag.query
    if category:
        query = query.filter_by(category=category)
    return query.order_by(FeatureFlag.category, FeatureFlag.display_name).all()


def get_enabled_features():
    """Get list of enabled feature names"""
    from app.models_extended import FeatureFlag

    flags = FeatureFlag.query.filter_by(is_enabled=True).all()
    enabled = []
    for flag in flags:
        if flag.requires_config:
            if flag.is_configured:
                enabled.append(flag.name)
        else:
            enabled.append(flag.name)
    return enabled


def feature_required(feature_name):
    """
    Decorator to require a feature to be enabled for a route

    Usage:
        @feature_required('sms_notifications')
        def send_sms():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not is_feature_enabled(feature_name):
                if request.is_json:
                    return jsonify({
                        'error': 'Feature not enabled',
                        'feature': feature_name
                    }), 403
                flash(f'This feature ({feature_name}) is not enabled. Contact admin to enable it.', 'warning')
                return redirect(url_for('main.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def feature_or_404(feature_name):
    """
    Abort with 404 if feature is not enabled
    Use inside route functions for conditional logic
    """
    if not is_feature_enabled(feature_name):
        abort(404)


def inject_feature_flags():
    """
    Inject feature flags into template context
    Call this in app context processor
    """
    return {
        'is_feature_enabled': is_feature_enabled,
        'enabled_features': get_enabled_features()
    }


# Feature flag names as constants
class Features:
    """Feature flag name constants"""
    SMS_NOTIFICATIONS = 'sms_notifications'
    WHATSAPP_NOTIFICATIONS = 'whatsapp_notifications'
    EMAIL_NOTIFICATIONS = 'email_notifications'
    PROMOTIONS = 'promotions'
    GIFT_VOUCHERS = 'gift_vouchers'
    QUOTATIONS = 'quotations'
    RETURNS_MANAGEMENT = 'returns_management'
    DUE_PAYMENTS = 'due_payments'
    PRODUCT_VARIANTS = 'product_variants'
    BARCODE_PRINTING = 'barcode_printing'
    EXPENSE_TRACKING = 'expense_tracking'
    SUPPLIER_PAYMENTS = 'supplier_payments'
    TAX_REPORTS = 'tax_reports'
    CUSTOMER_CREDIT = 'customer_credit'
    BIRTHDAY_AUTOMATION = 'birthday_automation'


def init_default_flags():
    """Initialize default feature flags in database"""
    from app.models_extended import init_feature_flags
    return init_feature_flags()


def get_feature_status_summary():
    """Get summary of all features for dashboard/settings"""
    from app.models_extended import FeatureFlag

    flags = FeatureFlag.query.all()

    summary = {
        'total': len(flags),
        'enabled': 0,
        'disabled': 0,
        'needs_config': 0,
        'by_category': {}
    }

    for flag in flags:
        if flag.is_enabled and (not flag.requires_config or flag.is_configured):
            summary['enabled'] += 1
        else:
            summary['disabled'] += 1

        if flag.requires_config and not flag.is_configured:
            summary['needs_config'] += 1

        if flag.category not in summary['by_category']:
            summary['by_category'][flag.category] = {'enabled': 0, 'total': 0}

        summary['by_category'][flag.category]['total'] += 1
        if flag.is_enabled and (not flag.requires_config or flag.is_configured):
            summary['by_category'][flag.category]['enabled'] += 1

    return summary
