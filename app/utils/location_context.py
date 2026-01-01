"""
Location Context Utilities for Multi-Kiosk Support

This module provides utilities for managing location context across the application,
including decorators for location-based access control and query filtering.
"""

from functools import wraps
from flask import g, session, flash, redirect, url_for, request, jsonify
from flask_login import current_user


def get_current_location():
    """
    Get the current user's assigned location.

    Returns:
        Location object or None if user has no assigned location
    """
    if not current_user.is_authenticated:
        return None

    # Import here to avoid circular imports
    from app.models import Location

    # Return user's assigned location
    if current_user.location_id:
        return Location.query.get(current_user.location_id)

    return None


def get_user_locations():
    """
    Get all locations the current user can access.

    Returns:
        List of Location objects
    """
    if not current_user.is_authenticated:
        return []

    return current_user.get_accessible_locations()


def set_location_context():
    """
    Set location context in Flask's g object.
    Call this in before_request to make location available throughout the request.
    """
    if current_user.is_authenticated:
        g.current_location = get_current_location()
        g.user_locations = get_user_locations()
        g.is_global_admin = current_user.is_global_admin
    else:
        g.current_location = None
        g.user_locations = []
        g.is_global_admin = False


def location_required(f):
    """
    Decorator to ensure user has a location assigned.

    Usage:
        @location_required
        def my_view():
            # g.current_location is guaranteed to be set
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.is_json:
                return jsonify({'error': 'Authentication required'}), 401
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))

        location = get_current_location()
        if not location and not current_user.is_global_admin:
            if request.is_json:
                return jsonify({'error': 'No location assigned'}), 403
            flash('You must be assigned to a location to access this page.', 'warning')
            return redirect(url_for('index'))

        g.current_location = location
        return f(*args, **kwargs)
    return decorated_function


def warehouse_required(f):
    """
    Decorator to ensure user is assigned to a warehouse location.

    Usage:
        @warehouse_required
        def warehouse_dashboard():
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.is_json:
                return jsonify({'error': 'Authentication required'}), 401
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))

        location = get_current_location()
        if not location:
            if current_user.is_global_admin:
                # Global admin can access warehouse features
                g.current_location = None
                return f(*args, **kwargs)
            if request.is_json:
                return jsonify({'error': 'No location assigned'}), 403
            flash('You must be assigned to a location.', 'warning')
            return redirect(url_for('index'))

        if not location.is_warehouse:
            if request.is_json:
                return jsonify({'error': 'Warehouse access required'}), 403
            flash('This page is only accessible to warehouse users.', 'warning')
            return redirect(url_for('index'))

        g.current_location = location
        return f(*args, **kwargs)
    return decorated_function


def kiosk_required(f):
    """
    Decorator to ensure user is assigned to a kiosk location.

    Usage:
        @kiosk_required
        def pos_view():
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.is_json:
                return jsonify({'error': 'Authentication required'}), 401
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))

        location = get_current_location()
        if not location:
            if current_user.is_global_admin:
                # Global admin can access but should select a kiosk for operations
                g.current_location = None
                return f(*args, **kwargs)
            if request.is_json:
                return jsonify({'error': 'No location assigned'}), 403
            flash('You must be assigned to a kiosk.', 'warning')
            return redirect(url_for('index'))

        if not location.is_kiosk:
            if request.is_json:
                return jsonify({'error': 'Kiosk access required'}), 403
            flash('This page is only accessible to kiosk users.', 'warning')
            return redirect(url_for('index'))

        g.current_location = location
        return f(*args, **kwargs)
    return decorated_function


def can_access_location(location_id):
    """
    Check if current user can access a specific location.

    Args:
        location_id: ID of the location to check access for

    Returns:
        Boolean indicating if user can access the location
    """
    if not current_user.is_authenticated:
        return False

    return current_user.can_access_location(location_id)


def filter_by_location(query, model, location_field='location_id'):
    """
    Filter a query by the current user's location.
    Global admins see all data, others see only their location's data.

    Args:
        query: SQLAlchemy query object
        model: The model class being queried
        location_field: Name of the location_id field on the model

    Returns:
        Filtered query
    """
    if not current_user.is_authenticated:
        return query.filter(False)  # Return empty result

    if current_user.is_global_admin:
        return query  # Admin sees all

    location = get_current_location()
    if not location:
        return query.filter(False)  # No location = no data

    # Filter by location
    location_column = getattr(model, location_field, None)
    if location_column is not None:
        return query.filter(location_column == location.id)

    return query


def get_location_stock(product_id, location_id=None):
    """
    Get stock level for a product at a specific location or current location.

    Args:
        product_id: ID of the product
        location_id: Optional location ID, defaults to current location

    Returns:
        LocationStock object or None
    """
    from app.models import LocationStock

    if location_id is None:
        location = get_current_location()
        if not location:
            return None
        location_id = location.id

    return LocationStock.query.filter_by(
        location_id=location_id,
        product_id=product_id
    ).first()


def get_or_create_location_stock(product_id, location_id=None):
    """
    Get or create a LocationStock record for a product at a location.

    Args:
        product_id: ID of the product
        location_id: Optional location ID, defaults to current location

    Returns:
        LocationStock object
    """
    from app.models import db, LocationStock, Product

    if location_id is None:
        location = get_current_location()
        if not location:
            raise ValueError("No location specified and no current location set")
        location_id = location.id

    stock = LocationStock.query.filter_by(
        location_id=location_id,
        product_id=product_id
    ).first()

    if not stock:
        # Get reorder level from product
        product = Product.query.get(product_id)
        stock = LocationStock(
            location_id=location_id,
            product_id=product_id,
            quantity=0,
            reorder_level=product.reorder_level if product else 10
        )
        db.session.add(stock)
        db.session.flush()

    return stock


def update_location_stock(product_id, quantity_change, location_id=None, movement_type='adjustment', reference=None, notes=None):
    """
    Update stock at a location and create a stock movement record.

    Args:
        product_id: ID of the product
        quantity_change: Amount to add (positive) or remove (negative)
        location_id: Optional location ID, defaults to current location
        movement_type: Type of movement (sale, purchase, adjustment, return, transfer_in, transfer_out)
        reference: Reference string (sale number, PO number, etc.)
        notes: Additional notes

    Returns:
        Tuple of (LocationStock, StockMovement) objects
    """
    from app.models import db, StockMovement
    from datetime import datetime

    if location_id is None:
        location = get_current_location()
        if not location:
            raise ValueError("No location specified and no current location set")
        location_id = location.id

    # Get or create stock record
    stock = get_or_create_location_stock(product_id, location_id)

    # Update quantity
    stock.quantity += quantity_change
    stock.last_movement_at = datetime.utcnow()

    # Ensure quantity doesn't go negative
    if stock.quantity < 0:
        stock.quantity = 0

    # Create movement record
    movement = StockMovement(
        product_id=product_id,
        user_id=current_user.id if current_user.is_authenticated else None,
        movement_type=movement_type,
        quantity=quantity_change,
        reference=reference,
        notes=notes,
        location_id=location_id
    )
    db.session.add(movement)

    return stock, movement


def generate_transfer_number():
    """
    Generate a unique transfer number.

    Returns:
        String like "TRF-20231215-001"
    """
    from app.models import StockTransfer
    from datetime import datetime

    today = datetime.utcnow().strftime('%Y%m%d')
    prefix = f"TRF-{today}-"

    # Find the last transfer number for today
    last_transfer = StockTransfer.query.filter(
        StockTransfer.transfer_number.like(f"{prefix}%")
    ).order_by(StockTransfer.transfer_number.desc()).first()

    if last_transfer:
        try:
            last_num = int(last_transfer.transfer_number.split('-')[-1])
            new_num = last_num + 1
        except (ValueError, IndexError):
            new_num = 1
    else:
        new_num = 1

    return f"{prefix}{new_num:03d}"
