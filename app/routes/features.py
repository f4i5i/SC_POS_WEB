"""
Feature Flags Management Routes
Admin interface for enabling/disabling features
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import db
from app.models_extended import FeatureFlag
from app.utils.permissions import permission_required, admin_required, Permissions
from app.utils.feature_flags import (
    is_feature_enabled, set_feature_enabled, update_feature_config,
    get_all_features, get_feature_status_summary, init_default_flags
)

bp = Blueprint('features', __name__)


@bp.route('/')
@login_required
@admin_required
def index():
    """Feature flags management dashboard"""
    # Initialize default flags if needed
    existing_count = FeatureFlag.query.count()
    if existing_count == 0:
        init_default_flags()

    features = get_all_features()
    summary = get_feature_status_summary()

    # Group features by category
    categories = {}
    for feature in features:
        if feature.category not in categories:
            categories[feature.category] = []
        categories[feature.category].append(feature)

    return render_template('features/index.html',
                         features=features,
                         categories=categories,
                         summary=summary)


@bp.route('/toggle/<int:feature_id>', methods=['POST'])
@login_required
@admin_required
def toggle_feature(feature_id):
    """Toggle a feature on/off"""
    feature = FeatureFlag.query.get_or_404(feature_id)

    # Check if feature requires configuration before enabling
    if not feature.is_enabled and feature.requires_config and not feature.is_configured:
        return jsonify({
            'success': False,
            'error': 'This feature requires configuration before enabling. Please configure it first.'
        }), 400

    feature.is_enabled = not feature.is_enabled
    if feature.is_enabled:
        from datetime import datetime
        feature.enabled_by = current_user.id
        feature.enabled_at = datetime.utcnow()

    db.session.commit()

    # Log activity
    import json
    from app.models import ActivityLog
    log = ActivityLog(
        user_id=current_user.id,
        action='feature_toggled',
        entity_type='feature_flag',
        entity_id=feature.id,
        details=json.dumps({'feature': feature.name, 'enabled': feature.is_enabled})
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({
        'success': True,
        'enabled': feature.is_enabled,
        'message': f'Feature "{feature.display_name}" has been {"enabled" if feature.is_enabled else "disabled"}'
    })


@bp.route('/configure/<int:feature_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def configure_feature(feature_id):
    """Configure a feature"""
    feature = FeatureFlag.query.get_or_404(feature_id)

    if request.method == 'POST':
        config_data = {}

        # Get all config fields from the form
        for key in request.form:
            if key.startswith('config_'):
                config_key = key[7:]  # Remove 'config_' prefix
                config_data[config_key] = request.form[key]

        # Update configuration
        if feature.config is None:
            feature.config = {}

        current_config = dict(feature.config)
        current_config.update(config_data)
        feature.config = current_config

        # Check if configuration is complete
        if feature.requires_config:
            has_config = any(v for v in current_config.values() if v)
            feature.is_configured = has_config

        db.session.commit()

        flash(f'Configuration for "{feature.display_name}" has been updated.', 'success')
        return redirect(url_for('features.index'))

    return render_template('features/configure.html', feature=feature)


@bp.route('/init', methods=['POST'])
@login_required
@admin_required
def initialize_flags():
    """Initialize default feature flags"""
    try:
        count = init_default_flags()
        flash(f'Initialized {count} feature flags.', 'success')
    except Exception as e:
        flash(f'Error initializing feature flags: {str(e)}', 'danger')

    return redirect(url_for('features.index'))


@bp.route('/api/status')
@login_required
def api_feature_status():
    """API endpoint to get feature status"""
    features = get_all_features()
    return jsonify({
        'features': [{
            'name': f.name,
            'display_name': f.display_name,
            'is_enabled': f.is_enabled,
            'requires_config': f.requires_config,
            'is_configured': f.is_configured,
            'category': f.category
        } for f in features]
    })


@bp.route('/api/check/<feature_name>')
@login_required
def api_check_feature(feature_name):
    """API endpoint to check if a specific feature is enabled"""
    enabled = is_feature_enabled(feature_name)
    return jsonify({
        'feature': feature_name,
        'enabled': enabled
    })
