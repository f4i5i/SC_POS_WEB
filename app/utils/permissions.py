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
    Decorator to require admin role
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

        if not current_user.has_role('admin'):
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
            'display_name': 'Store Manager',
            'description': 'Manage store operations, inventory, and view reports',
            'permissions': all_pos + all_inventory + all_customer + all_reports + [
                'pos.close_day', 'pos.void_sale', 'pos.refund', 'pos.apply_discount',
                'inventory.delete', 'inventory.transfer',
                'supplier.view', 'supplier.create', 'supplier.edit',
                'purchase_order.view', 'purchase_order.create', 'purchase_order.approve',
                'report.view_financial', 'settings.view'
            ],
            'is_system': True
        },
        'cashier': {
            'display_name': 'Cashier',
            'description': 'Process sales and basic customer management',
            'permissions': all_pos + ['customer.view', 'customer.create', 'customer.view_history'],
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
        }
    }

    return roles
