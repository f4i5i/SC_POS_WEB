"""
Model Registry Utility
Auto-discovers all SQLAlchemy models and provides introspection utilities
for the developer DB browser (Django admin-like interface).
"""

from app.models import db
import sqlalchemy as sa


# Model category mapping: tablename -> category
CATEGORY_MAP = {
    # Auth & Users
    'users': 'Auth & Users',
    'roles': 'Auth & Users',
    'permissions': 'Auth & Users',

    # Products & Inventory
    'categories': 'Products & Inventory',
    'products': 'Products & Inventory',
    'product_variants': 'Products & Inventory',
    'stock_movements': 'Products & Inventory',
    'location_stocks': 'Products & Inventory',
    'location_stock': 'Products & Inventory',
    'inventory_spot_checks': 'Products & Inventory',
    'inventory_spot_check_items': 'Products & Inventory',
    'product_batches': 'Products & Inventory',
    'batch_movements': 'Products & Inventory',
    'expiry_alerts': 'Products & Inventory',

    # Sales & POS
    'sales': 'Sales & POS',
    'sale_items': 'Sales & POS',
    'payments': 'Sales & POS',
    'digital_receipts': 'Sales & POS',
    'returns': 'Sales & POS',
    'return_items': 'Sales & POS',
    'day_closes': 'Sales & POS',
    'void_refund_logs': 'Sales & POS',
    'discount_logs': 'Sales & POS',

    # Customers
    'customers': 'Customers',
    'customer_credits': 'Customers',
    'due_payments': 'Customers',
    'due_payment_installments': 'Customers',
    'referrals': 'Customers',

    # Suppliers & Purchasing
    'suppliers': 'Suppliers & Purchasing',
    'purchase_orders': 'Suppliers & Purchasing',
    'purchase_order_items': 'Suppliers & Purchasing',
    'supplier_payments': 'Suppliers & Purchasing',
    'supplier_ledger': 'Suppliers & Purchasing',
    'supplier_ledgers': 'Suppliers & Purchasing',

    # Locations & Transfers
    'locations': 'Locations & Transfers',
    'stock_transfers': 'Locations & Transfers',
    'stock_transfer_items': 'Locations & Transfers',
    'transfer_requests': 'Locations & Transfers',
    'gate_passes': 'Locations & Transfers',

    # Production
    'raw_material_categories': 'Production',
    'raw_materials': 'Production',
    'raw_material_stocks': 'Production',
    'raw_material_stock': 'Production',
    'raw_material_movements': 'Production',
    'recipes': 'Production',
    'recipe_ingredients': 'Production',
    'production_orders': 'Production',
    'production_material_consumption': 'Production',
    'production_material_consumptions': 'Production',

    # Finance
    'expense_categories': 'Finance',
    'expenses': 'Finance',
    'product_cost_history': 'Finance',
    'location_product_costs': 'Finance',
    'tax_rates': 'Finance',
    'tax_reports': 'Finance',
    'price_change_logs': 'Finance',
    'price_change_rules': 'Finance',

    # Marketing & Loyalty
    'promotions': 'Marketing & Loyalty',
    'promotion_usages': 'Marketing & Loyalty',
    'gift_vouchers': 'Marketing & Loyalty',
    'gift_voucher_transactions': 'Marketing & Loyalty',
    'loyalty_badges': 'Marketing & Loyalty',
    'customer_badges': 'Marketing & Loyalty',
    'loyalty_challenges': 'Marketing & Loyalty',
    'customer_challenge_progress': 'Marketing & Loyalty',
    'sms_campaigns': 'Marketing & Loyalty',
    'automated_triggers': 'Marketing & Loyalty',
    'trigger_logs': 'Marketing & Loyalty',

    # Notifications & Messaging
    'sms_templates': 'Notifications & Messaging',
    'sms_logs': 'Notifications & Messaging',
    'whatsapp_templates': 'Notifications & Messaging',
    'whatsapp_logs': 'Notifications & Messaging',
    'notification_settings': 'Notifications & Messaging',

    # System
    'settings': 'System',
    'feature_flags': 'System',
    'activity_logs': 'System',
    'error_logs': 'System',
    'sync_queue': 'System',
    'reports': 'System',
    'quotations': 'System',
    'quotation_items': 'System',
    'scheduled_tasks': 'System',

    # Controls & Approvals
    'discount_limits': 'Controls & Approvals',
    'discount_approvals': 'Controls & Approvals',
    'void_refund_limits': 'Controls & Approvals',
    'void_refund_approvals': 'Controls & Approvals',
}

# Columns that should be hidden in forms (contain sensitive data)
HIDDEN_COLUMNS = {'password_hash'}

# Columns that should be read-only in forms
READONLY_COLUMNS = {'id', 'created_at', 'updated_at'}


def _get_all_subclasses(cls):
    """Recursively get all subclasses of a class."""
    result = []
    for subclass in cls.__subclasses__():
        result.append(subclass)
        result.extend(_get_all_subclasses(subclass))
    return result


def get_all_models():
    """
    Discover all SQLAlchemy models at runtime.

    Returns:
        dict: {tablename: model_class}
    """
    # Ensure models_extended is imported so its subclasses are registered
    try:
        import app.models_extended  # noqa: F401
    except ImportError:
        pass

    models = {}
    for model_class in _get_all_subclasses(db.Model):
        if hasattr(model_class, '__tablename__'):
            models[model_class.__tablename__] = model_class
    return models


def get_models_by_category():
    """
    Get all models organized by category.

    Returns:
        dict: {category_name: [{name, tablename, model_class, record_count}]}
    """
    models = get_all_models()
    categories = {}

    for tablename, model_class in sorted(models.items()):
        category = CATEGORY_MAP.get(tablename, 'Other')
        if category not in categories:
            categories[category] = []

        try:
            count = model_class.query.count()
        except Exception:
            count = 0

        categories[category].append({
            'name': model_class.__name__,
            'tablename': tablename,
            'model_class': model_class,
            'record_count': count,
        })

    # Sort categories, putting "Other" last
    sorted_categories = {}
    for key in sorted(categories.keys(), key=lambda x: (x == 'Other', x)):
        sorted_categories[key] = categories[key]
    return sorted_categories


def get_model_by_tablename(tablename):
    """Get a model class by its table name."""
    models = get_all_models()
    return models.get(tablename)


def get_column_info(model_class):
    """
    Get column metadata for a model.

    Returns:
        list of dicts with: name, type, python_type, nullable, primary_key,
        foreign_key, default, input_type, is_hidden, is_readonly
    """
    columns = []
    for col in model_class.__table__.columns:
        col_type = type(col.type)
        input_type = 'text'

        if col_type in (sa.Integer, sa.SmallInteger, sa.BigInteger):
            input_type = 'number'
        elif col_type in (sa.Numeric, sa.Float):
            input_type = 'number'
        elif col_type == sa.Boolean:
            input_type = 'checkbox'
        elif col_type == sa.Text:
            input_type = 'textarea'
        elif col_type in (sa.DateTime, sa.TIMESTAMP):
            input_type = 'datetime-local'
        elif col_type == sa.Date:
            input_type = 'date'
        elif col_type == sa.Time:
            input_type = 'time'
        elif col_type == sa.JSON:
            input_type = 'textarea'

        fk = None
        if col.foreign_keys:
            fk_col = list(col.foreign_keys)[0]
            fk = str(fk_col.target_fullname)

        columns.append({
            'name': col.name,
            'type': str(col.type),
            'python_type': col_type.__name__,
            'nullable': col.nullable,
            'primary_key': col.primary_key,
            'foreign_key': fk,
            'default': str(col.default.arg) if col.default and hasattr(col.default, 'arg') and not callable(col.default.arg) else None,
            'input_type': input_type,
            'is_hidden': col.name in HIDDEN_COLUMNS,
            'is_readonly': col.name in READONLY_COLUMNS,
        })

    return columns


def get_string_columns(model_class):
    """Get column names that are string-type (for search)."""
    string_types = (sa.String, sa.Text)
    return [
        col.name for col in model_class.__table__.columns
        if isinstance(col.type, string_types)
    ]


def coerce_value(value, col_info):
    """Coerce a form value to the correct Python type for a column."""
    if value == '' or value is None:
        return None

    python_type = col_info['python_type']

    if python_type == 'Boolean':
        return value in ('on', 'true', 'True', '1', True)
    elif python_type in ('Integer', 'SmallInteger', 'BigInteger'):
        return int(value)
    elif python_type in ('Numeric', 'Float'):
        from decimal import Decimal
        return Decimal(str(value))
    elif python_type in ('DateTime', 'TIMESTAMP'):
        from datetime import datetime
        try:
            return datetime.strptime(value, '%Y-%m-%dT%H:%M')
        except ValueError:
            try:
                return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return None
    elif python_type == 'Date':
        from datetime import datetime
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            return None
    elif python_type == 'JSON':
        import json
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    return value
