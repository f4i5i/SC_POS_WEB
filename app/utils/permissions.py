"""
Permission Decorators and RBAC Utilities
"""

from functools import wraps
from flask import abort, flash, redirect, url_for, jsonify, request
from flask_login import current_user


def permission_required(permission_name):
    """
    Decorator to require a specific permission for a route

    Usage:
        @permission_required('pos.create_sale')
        def create_sale():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.is_json:
                    return jsonify({'error': 'Authentication required'}), 401
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login'))

            if not current_user.has_permission(permission_name):
                if request.is_json:
                    return jsonify({'error': 'Insufficient permissions'}), 403
                flash('You do not have permission to perform this action.', 'danger')
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def role_required(role_name):
    """
    Decorator to require a specific role for a route

    Usage:
        @role_required('admin')
        def admin_dashboard():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.is_json:
                    return jsonify({'error': 'Authentication required'}), 401
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login'))

            if not current_user.has_role(role_name):
                if request.is_json:
                    return jsonify({'error': f'Role {role_name} required'}), 403
                flash(f'This page requires {role_name} role.', 'danger')
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def any_permission_required(*permission_names):
    """
    Decorator to require ANY of the specified permissions

    Usage:
        @any_permission_required('pos.create_sale', 'pos.view_sales')
        def view_sales():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.is_json:
                    return jsonify({'error': 'Authentication required'}), 401
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login'))

            has_permission = any(current_user.has_permission(perm) for perm in permission_names)
            if not has_permission:
                if request.is_json:
                    return jsonify({'error': 'Insufficient permissions'}), 403
                flash('You do not have permission to perform this action.', 'danger')
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def all_permissions_required(*permission_names):
    """
    Decorator to require ALL of the specified permissions

    Usage:
        @all_permissions_required('inventory.view', 'inventory.edit')
        def edit_inventory():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.is_json:
                    return jsonify({'error': 'Authentication required'}), 401
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login'))

            has_all_permissions = all(current_user.has_permission(perm) for perm in permission_names)
            if not has_all_permissions:
                if request.is_json:
                    return jsonify({'error': 'Insufficient permissions'}), 403
                flash('You do not have all required permissions.', 'danger')
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """
    Decorator to require admin role or global admin status
    Shortcut for @role_required('admin')

    Usage:
        @admin_required
        def admin_settings():
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.is_json:
                return jsonify({'error': 'Authentication required'}), 401
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))

        # Check for admin role OR global admin status
        is_admin = current_user.has_role('admin') or getattr(current_user, 'is_global_admin', False)
        if not is_admin:
            if request.is_json:
                return jsonify({'error': 'Admin access required'}), 403
            flash('This page requires administrator access.', 'danger')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


# Permission Constants
class Permissions:
    """Permission name constants to avoid typos"""

    # POS Permissions
    POS_VIEW = 'pos.view'
    POS_CREATE_SALE = 'pos.create_sale'
    POS_VOID_SALE = 'pos.void_sale'
    POS_REFUND = 'pos.refund'
    POS_CLOSE_DAY = 'pos.close_day'
    POS_HOLD_SALE = 'pos.hold_sale'
    POS_APPLY_DISCOUNT = 'pos.apply_discount'

    # Inventory Permissions
    INVENTORY_VIEW = 'inventory.view'
    INVENTORY_CREATE = 'inventory.create'
    INVENTORY_EDIT = 'inventory.edit'
    INVENTORY_DELETE = 'inventory.delete'
    INVENTORY_ADJUST = 'inventory.adjust_stock'
    INVENTORY_TRANSFER = 'inventory.transfer'

    # Customer Permissions
    CUSTOMER_VIEW = 'customer.view'
    CUSTOMER_CREATE = 'customer.create'
    CUSTOMER_EDIT = 'customer.edit'
    CUSTOMER_DELETE = 'customer.delete'
    CUSTOMER_VIEW_HISTORY = 'customer.view_history'

    # Supplier Permissions
    SUPPLIER_VIEW = 'supplier.view'
    SUPPLIER_CREATE = 'supplier.create'
    SUPPLIER_EDIT = 'supplier.edit'
    SUPPLIER_DELETE = 'supplier.delete'

    # Report Permissions
    REPORT_VIEW_SALES = 'report.view_sales'
    REPORT_VIEW_INVENTORY = 'report.view_inventory'
    REPORT_VIEW_FINANCIAL = 'report.view_financial'
    REPORT_EXPORT = 'report.export'

    # Settings Permissions
    SETTINGS_VIEW = 'settings.view'
    SETTINGS_EDIT = 'settings.edit'
    SETTINGS_MANAGE_USERS = 'settings.manage_users'
    SETTINGS_MANAGE_ROLES = 'settings.manage_roles'

    # Purchase Order Permissions
    PO_VIEW = 'purchase_order.view'
    PO_CREATE = 'purchase_order.create'
    PO_APPROVE = 'purchase_order.approve'
    PO_RECEIVE = 'purchase_order.receive'

    # Location Permissions (Multi-Kiosk)
    LOCATION_VIEW = 'location.view'
    LOCATION_CREATE = 'location.create'
    LOCATION_EDIT = 'location.edit'
    LOCATION_DELETE = 'location.delete'
    LOCATION_VIEW_ALL = 'location.view_all'

    # Stock Transfer Permissions
    TRANSFER_VIEW = 'transfer.view'
    TRANSFER_REQUEST = 'transfer.request'
    TRANSFER_APPROVE = 'transfer.approve'
    TRANSFER_DISPATCH = 'transfer.dispatch'
    TRANSFER_RECEIVE = 'transfer.receive'
    TRANSFER_CANCEL = 'transfer.cancel'
    TRANSFER_VIEW_ALL = 'transfer.view_all'

    # Warehouse Permissions
    WAREHOUSE_VIEW = 'warehouse.view'
    WAREHOUSE_MANAGE_STOCK = 'warehouse.manage_stock'
    WAREHOUSE_APPROVE_REQUESTS = 'warehouse.approve_requests'

    # Multi-Location Reports
    REPORT_VIEW_ALL_LOCATIONS = 'report.view_all_locations'
    REPORT_COMPARE_LOCATIONS = 'report.compare_locations'

    # Expense Permissions
    EXPENSE_VIEW = 'expense.view'
    EXPENSE_CREATE = 'expense.create'
    EXPENSE_EDIT = 'expense.edit'
    EXPENSE_DELETE = 'expense.delete'

    # Returns Permissions
    RETURNS_VIEW = 'returns.view'
    RETURNS_CREATE = 'returns.create'
    RETURNS_APPROVE = 'returns.approve'

    # Production Permissions
    PRODUCTION_VIEW = 'production.view'
    PRODUCTION_CREATE = 'production.create_order'
    PRODUCTION_APPROVE = 'production.approve_order'
    PRODUCTION_EXECUTE = 'production.execute'

    # Raw Material Permissions
    RAW_MATERIAL_VIEW = 'raw_material.view'
    RAW_MATERIAL_CREATE = 'raw_material.create'
    RAW_MATERIAL_ADJUST = 'raw_material.adjust_stock'

    # Recipe Permissions
    RECIPE_VIEW = 'recipe.view'
    RECIPE_CREATE = 'recipe.create'
    RECIPE_EDIT = 'recipe.edit'
    RECIPE_DELETE = 'recipe.delete'


def get_all_permissions():
    """Get all defined permissions as a list of tuples (name, display_name, module)"""
    permissions = [
        # POS
        ('pos.view', 'View POS', 'pos'),
        ('pos.create_sale', 'Create Sales', 'pos'),
        ('pos.void_sale', 'Void Sales', 'pos'),
        ('pos.refund', 'Process Refunds', 'pos'),
        ('pos.close_day', 'Close Day', 'pos'),
        ('pos.hold_sale', 'Hold Sales', 'pos'),
        ('pos.apply_discount', 'Apply Discounts', 'pos'),

        # Inventory
        ('inventory.view', 'View Inventory', 'inventory'),
        ('inventory.create', 'Add Products', 'inventory'),
        ('inventory.edit', 'Edit Products', 'inventory'),
        ('inventory.delete', 'Delete Products', 'inventory'),
        ('inventory.adjust_stock', 'Adjust Stock', 'inventory'),
        ('inventory.transfer', 'Transfer Stock', 'inventory'),

        # Customers
        ('customer.view', 'View Customers', 'customers'),
        ('customer.create', 'Add Customers', 'customers'),
        ('customer.edit', 'Edit Customers', 'customers'),
        ('customer.delete', 'Delete Customers', 'customers'),
        ('customer.view_history', 'View Customer History', 'customers'),

        # Suppliers
        ('supplier.view', 'View Suppliers', 'suppliers'),
        ('supplier.create', 'Add Suppliers', 'suppliers'),
        ('supplier.edit', 'Edit Suppliers', 'suppliers'),
        ('supplier.delete', 'Delete Suppliers', 'suppliers'),

        # Reports
        ('report.view_sales', 'View Sales Reports', 'reports'),
        ('report.view_inventory', 'View Inventory Reports', 'reports'),
        ('report.view_financial', 'View Financial Reports', 'reports'),
        ('report.export', 'Export Reports', 'reports'),

        # Settings
        ('settings.view', 'View Settings', 'settings'),
        ('settings.edit', 'Edit Settings', 'settings'),
        ('settings.manage_users', 'Manage Users', 'settings'),
        ('settings.manage_roles', 'Manage Roles', 'settings'),

        # Purchase Orders
        ('purchase_order.view', 'View Purchase Orders', 'purchase_orders'),
        ('purchase_order.create', 'Create Purchase Orders', 'purchase_orders'),
        ('purchase_order.approve', 'Approve Purchase Orders', 'purchase_orders'),
        ('purchase_order.receive', 'Receive Purchase Orders', 'purchase_orders'),

        # Locations (Multi-Kiosk)
        ('location.view', 'View Locations', 'locations'),
        ('location.create', 'Create Locations', 'locations'),
        ('location.edit', 'Edit Locations', 'locations'),
        ('location.delete', 'Delete Locations', 'locations'),
        ('location.view_all', 'View All Locations', 'locations'),

        # Stock Transfers
        ('transfer.view', 'View Transfers', 'transfers'),
        ('transfer.request', 'Request Transfers', 'transfers'),
        ('transfer.approve', 'Approve Transfers', 'transfers'),
        ('transfer.dispatch', 'Dispatch Transfers', 'transfers'),
        ('transfer.receive', 'Receive Transfers', 'transfers'),
        ('transfer.cancel', 'Cancel Transfers', 'transfers'),
        ('transfer.view_all', 'View All Transfers', 'transfers'),

        # Warehouse
        ('warehouse.view', 'View Warehouse', 'warehouse'),
        ('warehouse.manage_stock', 'Manage Warehouse Stock', 'warehouse'),
        ('warehouse.approve_requests', 'Approve Stock Requests', 'warehouse'),

        # Multi-Location Reports
        ('report.view_all_locations', 'View All Location Reports', 'reports'),
        ('report.compare_locations', 'Compare Location Reports', 'reports'),

        # Production
        ('production.view', 'View Production', 'production'),
        ('production.create_order', 'Create Production Orders', 'production'),
        ('production.approve_order', 'Approve Production Orders', 'production'),
        ('production.execute', 'Execute Production', 'production'),

        # Raw Materials
        ('raw_material.view', 'View Raw Materials', 'production'),
        ('raw_material.create', 'Create Raw Materials', 'production'),
        ('raw_material.adjust_stock', 'Adjust Raw Material Stock', 'production'),

        # Recipes
        ('recipe.view', 'View Recipes', 'production'),
        ('recipe.create', 'Create Recipes', 'production'),
        ('recipe.edit', 'Edit Recipes', 'production'),
    ]

    return permissions


def get_default_roles():
    """Get default role definitions with their permissions"""
    all_pos = ['pos.view', 'pos.create_sale', 'pos.hold_sale']
    all_inventory = ['inventory.view', 'inventory.create', 'inventory.edit', 'inventory.adjust_stock']
    all_customer = ['customer.view', 'customer.create', 'customer.edit', 'customer.view_history']
    all_reports = ['report.view_sales', 'report.view_inventory', 'report.export']

    roles = {
        'admin': {
            'display_name': 'Administrator',
            'description': 'Full system access with all permissions',
            'permissions': [perm[0] for perm in get_all_permissions()],
            'is_system': True
        },
        'manager': {
            'display_name': 'Manager',
            'description': 'Manage store/kiosk operations, process returns and refunds, view sales reports, handle expenses and production',
            'permissions': [
                # POS - can sell, close day, apply discount, refund
                'pos.view', 'pos.create_sale', 'pos.close_day', 'pos.hold_sale', 'pos.apply_discount', 'pos.refund',
                # Inventory - view and adjust stock for own store
                'inventory.view', 'inventory.adjust_stock',
                # Customers - full access
                'customer.view', 'customer.create', 'customer.edit', 'customer.view_history',
                # Transfers - can request and receive stock
                'transfer.view', 'transfer.request', 'transfer.receive',
                # Location - view own location only
                'location.view',
                # Reports - sales reports (daily, weekly, monthly)
                'report.view_sales',
                # Expenses - can view and create expenses
                'expense.view', 'expense.create',
                # Returns - can process returns
                'returns.view', 'returns.create',
                # Production - can view, create orders, and execute attar production
                'production.view', 'production.create_order', 'production.execute',
                'raw_material.view', 'raw_material.adjust_stock',
                'recipe.view'
            ],
            'is_system': True
        },
        'store_manager': {
            'display_name': 'Store Manager',
            'description': 'View-only access to daily sales reports for their location',
            'permissions': [
                # Reports - daily sales only
                'report.view_sales'
            ],
            'is_system': True
        },
        'cashier': {
            'display_name': 'Cashier',
            'description': 'Process sales, add customers (cannot edit)',
            'permissions': [
                'pos.view', 'pos.create_sale', 'pos.hold_sale',
                'customer.view', 'customer.create', 'customer.view_history'
                # NO customer.edit - only managers can update customer details
            ],
            'is_system': True
        },
        'inventory_manager': {
            'display_name': 'Inventory Manager',
            'description': 'Manage inventory and purchase orders',
            'permissions': all_inventory + [
                'inventory.delete', 'inventory.transfer',
                'supplier.view', 'supplier.create', 'supplier.edit',
                'purchase_order.view', 'purchase_order.create', 'purchase_order.receive',
                'report.view_inventory'
            ],
            'is_system': True
        },
        'accountant': {
            'display_name': 'Accountant',
            'description': 'View financial reports and sales data',
            'permissions': [
                'report.view_sales', 'report.view_inventory', 'report.view_financial', 'report.export',
                'customer.view', 'supplier.view', 'purchase_order.view'
            ],
            'is_system': True
        },
        'warehouse_manager': {
            'display_name': 'Warehouse Manager',
            'description': 'Manages central warehouse operations, approves stock transfers, and production',
            'permissions': [
                'warehouse.view', 'warehouse.manage_stock', 'warehouse.approve_requests',
                'inventory.view', 'inventory.create', 'inventory.edit', 'inventory.adjust_stock',
                'transfer.view', 'transfer.approve', 'transfer.dispatch', 'transfer.view_all',
                'location.view', 'location.view_all',
                'report.view_inventory', 'report.view_all_locations',
                # Production - full access
                'production.view', 'production.create_order', 'production.approve_order', 'production.execute',
                'raw_material.view', 'raw_material.create', 'raw_material.adjust_stock',
                'recipe.view', 'recipe.create', 'recipe.edit'
            ],
            'is_system': True
        },
        'regional_manager': {
            'display_name': 'Regional Manager',
            'description': 'Oversees multiple kiosk locations in a region',
            'permissions': [
                'pos.view', 'pos.create_sale', 'pos.void_sale', 'pos.refund', 'pos.close_day',
                'pos.hold_sale', 'pos.apply_discount',
                'inventory.view', 'inventory.adjust_stock',
                'customer.view', 'customer.create', 'customer.edit', 'customer.view_history',
                'transfer.view', 'transfer.request', 'transfer.receive', 'transfer.approve', 'transfer.view_all',
                'location.view', 'location.view_all',
                'report.view_sales', 'report.view_inventory', 'report.view_all_locations', 'report.compare_locations',
                'settings.view'
            ],
            'is_system': True
        }
    }

    return roles
