"""
Database Models
SQLAlchemy ORM models for the POS system
"""

from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """User model for authentication and authorization"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(32), nullable=False, default='cashier')
    # Roles: admin, manager, store_manager, cashier, inventory_manager, accountant, warehouse_manager, regional_manager
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Account lockout fields for security
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)

    # Force password change on first login
    force_password_change = db.Column(db.Boolean, default=False)
    password_changed_at = db.Column(db.DateTime)

    # Multi-kiosk support
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))  # Assigned kiosk/warehouse
    is_global_admin = db.Column(db.Boolean, default=False)  # Can access all locations

    # Relationships
    sales = db.relationship('Sale', backref='cashier', lazy='dynamic', foreign_keys='Sale.user_id')
    stock_movements = db.relationship('StockMovement', backref='user', lazy='dynamic', foreign_keys='StockMovement.user_id')
    location = db.relationship('Location', foreign_keys=[location_id], backref=db.backref('users', lazy='dynamic'))

    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)

    def has_permission(self, permission):
        """Check if user has specific permission based on role"""
        from app.utils.permissions import get_default_roles

        # Global admin has all permissions
        if self.is_global_admin:
            return True

        # Admin role has all permissions
        if self.role == 'admin':
            return True

        # Try RBAC system first (may not be set up)
        try:
            if self.has_rbac_permission(permission):
                return True
        except Exception:
            pass  # RBAC tables may not exist

        # Check permission against role's default permissions
        default_roles = get_default_roles()
        if self.role in default_roles:
            role_permissions = default_roles[self.role].get('permissions', [])
            return permission in role_permissions

        return False

    def has_rbac_permission(self, permission_name):
        """Check if user has permission through RBAC roles"""
        for role in self.roles:
            if role.has_permission(permission_name):
                return True
        return False

    def has_role(self, role_name):
        """Check if user has a specific role"""
        # Check the simple role string field first
        if self.role == role_name:
            return True
        # Also check global admin for admin role requests
        if role_name == 'admin' and getattr(self, 'is_global_admin', False):
            return True
        # Check the roles relationship if it exists
        return any(role.name == role_name for role in self.roles)

    def get_all_permissions(self):
        """Get all permissions from all roles"""
        permissions = set()
        for role in self.roles:
            for perm in role.permissions:
                permissions.add(perm.name)
        return list(permissions)

    def can_access_location(self, location_id):
        """Check if user can access a specific location"""
        if self.is_global_admin:
            return True
        return self.location_id == location_id

    def get_accessible_locations(self):
        """Get all locations user can access"""
        if self.is_global_admin:
            return Location.query.filter_by(is_active=True).all()
        if self.location:
            return [self.location]
        return []

    def __repr__(self):
        return f'<User {self.username}>'


# RBAC Association Tables
user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True),
    db.Column('assigned_at', db.DateTime, default=datetime.utcnow)
)

role_permissions = db.Table('role_permissions',
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permissions.id'), primary_key=True),
    db.Column('assigned_at', db.DateTime, default=datetime.utcnow)
)


class Role(db.Model):
    """User roles for RBAC"""
    __tablename__ = 'roles'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)
    is_system = db.Column(db.Boolean, default=False)  # System roles can't be deleted
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    users = db.relationship('User', secondary=user_roles, backref=db.backref('roles', lazy='dynamic'))
    permissions = db.relationship('Permission', secondary=role_permissions, backref=db.backref('roles', lazy='dynamic'))

    def has_permission(self, permission_name):
        """Check if role has a specific permission"""
        return any(perm.name == permission_name for perm in self.permissions)

    def __repr__(self):
        return f'<Role {self.name}>'


class Permission(db.Model):
    """System permissions for RBAC"""
    __tablename__ = 'permissions'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)
    module = db.Column(db.String(64))  # pos, inventory, customers, reports, etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Permission {self.name}>'


class Category(db.Model):
    """Product categories"""
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    description = db.Column(db.Text)
    parent_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Self-referential relationship for subcategories
    subcategories = db.relationship('Category', backref=db.backref('parent', remote_side=[id]))
    products = db.relationship('Product', backref='category', lazy='dynamic')

    def __repr__(self):
        return f'<Category {self.name}>'


class Supplier(db.Model):
    """Supplier/Vendor management"""
    __tablename__ = 'suppliers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True, index=True)
    contact_person = db.Column(db.String(128))
    phone = db.Column(db.String(32))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    payment_terms = db.Column(db.String(128))  # e.g., "Net 30", "Cash on delivery"
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)

    # Payment tracking
    credit_limit = db.Column(db.Numeric(12, 2), default=0.00)
    current_balance = db.Column(db.Numeric(12, 2), default=0.00)  # Outstanding amount
    payment_due_days = db.Column(db.Integer, default=30)  # Days for payment
    reminder_enabled = db.Column(db.Boolean, default=True)
    last_payment_date = db.Column(db.Date)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    products = db.relationship('Product', backref='supplier', lazy='dynamic')
    purchase_orders = db.relationship('PurchaseOrder', backref='supplier', lazy='dynamic')

    @property
    def is_over_credit_limit(self):
        """Check if supplier is over credit limit"""
        if not self.credit_limit or self.credit_limit <= 0:
            return False
        return (self.current_balance or 0) > self.credit_limit

    def __repr__(self):
        return f'<Supplier {self.name}>'


class Product(db.Model):
    """Product/Inventory items"""
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    barcode = db.Column(db.String(128), unique=True, index=True)
    name = db.Column(db.String(256), nullable=False, index=True)
    brand = db.Column(db.String(128))
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))

    # Product details
    description = db.Column(db.Text)
    size = db.Column(db.String(32))  # e.g., "100ml", "6oz"
    unit = db.Column(db.String(32), default='piece')  # piece, ml, box, etc.
    image_url = db.Column(db.String(512))

    # Pricing - Cost Breakdown
    base_cost = db.Column(db.Numeric(10, 2), default=0.00)  # Supplier price
    packaging_cost = db.Column(db.Numeric(10, 2), default=0.00)  # Box, wrapper, etc.
    delivery_cost = db.Column(db.Numeric(10, 2), default=0.00)  # Freight per unit
    bottle_cost = db.Column(db.Numeric(10, 2), default=0.00)  # Optional bottle cost
    kiosk_cost = db.Column(db.Numeric(10, 2), default=0.00)  # Kiosk/store margin

    # Computed/cached landed cost (for backward compatibility)
    cost_price = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    selling_price = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    tax_rate = db.Column(db.Numeric(5, 2), default=0.00)

    # Stock
    quantity = db.Column(db.Integer, default=0)
    reorder_level = db.Column(db.Integer, default=10)
    reorder_quantity = db.Column(db.Integer, default=50)

    # Additional fields
    batch_number = db.Column(db.String(64))
    expiry_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)

    # Manufacturing fields
    product_type = db.Column(db.String(32), default='retail')  # 'retail', 'manufactured'
    is_manufactured = db.Column(db.Boolean, default=False)  # True for attars/perfumes made in-house
    can_be_reordered = db.Column(db.Boolean, default=True)  # False for manufactured products
    is_made_to_order = db.Column(db.Boolean, default=False)  # Auto-deduct raw materials on sale

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sale_items = db.relationship('SaleItem', backref='product', lazy='dynamic')
    stock_movements = db.relationship('StockMovement', backref='product', lazy='dynamic')

    @property
    def landed_cost(self):
        """Calculate total landed cost from all cost components"""
        from decimal import Decimal
        return (
            (self.base_cost or Decimal('0')) +
            (self.packaging_cost or Decimal('0')) +
            (self.delivery_cost or Decimal('0')) +
            (self.bottle_cost or Decimal('0')) +
            (self.kiosk_cost or Decimal('0'))
        )

    def update_cost_price(self):
        """Update cached cost_price from landed_cost components"""
        self.cost_price = self.landed_cost

    @property
    def profit_margin(self):
        """Calculate profit margin percentage"""
        if self.cost_price and self.cost_price > 0:
            return ((self.selling_price - self.cost_price) / self.cost_price) * 100
        return 0

    @property
    def is_low_stock(self):
        """Check if product is below reorder level"""
        return self.quantity <= self.reorder_level

    @property
    def stock_value(self):
        """Calculate total stock value at cost price"""
        return float(self.quantity * self.cost_price)

    @property
    def days_until_expiry(self):
        """Calculate days until product expires"""
        if not self.expiry_date:
            return None
        from datetime import date
        delta = self.expiry_date - date.today()
        return delta.days

    @property
    def is_expired(self):
        """Check if product has expired"""
        if not self.expiry_date:
            return False
        from datetime import date
        return date.today() > self.expiry_date

    @property
    def is_expiring_soon(self):
        """Check if product is expiring within 30 days"""
        days = self.days_until_expiry
        return days is not None and 0 < days <= 30

    @property
    def is_expiring_critical(self):
        """Check if product is expiring within 7 days"""
        days = self.days_until_expiry
        return days is not None and 0 < days <= 7

    @property
    def expiry_status(self):
        """Get expiry status string"""
        if not self.expiry_date:
            return 'no_expiry'
        if self.is_expired:
            return 'expired'
        if self.is_expiring_critical:
            return 'critical'
        if self.is_expiring_soon:
            return 'warning'
        return 'good'

    @property
    def expiry_badge_class(self):
        """Get Bootstrap badge class based on expiry status"""
        status_classes = {
            'expired': 'danger',
            'critical': 'danger',
            'warning': 'warning',
            'good': 'success',
            'no_expiry': 'secondary'
        }
        return status_classes.get(self.expiry_status, 'secondary')

    @property
    def sales_velocity_30d(self):
        """Calculate average daily sales over last 30 days"""
        from datetime import datetime, timedelta
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)

        total_sold = db.session.query(db.func.sum(SaleItem.quantity))\
            .join(Sale)\
            .filter(SaleItem.product_id == self.id)\
            .filter(Sale.sale_date >= thirty_days_ago)\
            .scalar() or 0

        return total_sold / 30.0  # Average per day

    @property
    def days_until_stockout(self):
        """Estimate days until product runs out of stock based on sales velocity"""
        velocity = self.sales_velocity_30d
        if velocity <= 0:
            return None  # No sales history
        return int(self.quantity / velocity)

    @property
    def suggested_reorder_quantity(self):
        """Calculate suggested reorder quantity based on sales velocity"""
        velocity = self.sales_velocity_30d
        if velocity <= 0:
            return self.reorder_quantity  # Default reorder quantity

        # Order enough for 60 days based on sales velocity
        suggested = int(velocity * 60)
        return max(suggested, self.reorder_quantity)  # At least the default reorder quantity

    @property
    def needs_reorder(self):
        """Check if product needs to be reordered"""
        # Reorder if low stock OR will run out within 14 days
        if self.is_low_stock:
            return True
        days_left = self.days_until_stockout
        return days_left is not None and days_left <= 14

    @property
    def alert_priority(self):
        """Get alert priority: critical, high, medium, low"""
        if self.quantity == 0 or self.is_expired:
            return 'critical'
        if self.is_low_stock or self.is_expiring_critical:
            return 'high'
        if self.needs_reorder or self.is_expiring_soon:
            return 'medium'
        return 'low'

    def get_recipe(self):
        """Get the linked recipe for this product"""
        if self.recipes:
            return self.recipes[0] if isinstance(self.recipes, list) else self.recipes
        return None

    def get_raw_material_usage(self, quantity=1):
        """
        Calculate raw material usage for producing given quantity of this product.
        Returns list of dicts: [{'raw_material': obj, 'quantity': float, 'unit': str}, ...]
        """
        recipe = self.get_recipe()
        if not recipe:
            return []

        usage = []
        output_ml = float(recipe.output_size_ml or 0)
        oil_percentage = float(recipe.oil_percentage or 100) / 100

        for ingredient in recipe.ingredients:
            raw_material = ingredient.raw_material
            if not raw_material:
                continue

            if ingredient.is_packaging:
                # Bottle: 1 per unit produced
                usage.append({
                    'raw_material': raw_material,
                    'quantity': quantity,
                    'unit': 'pcs'
                })
            else:
                # Oil: calculate based on percentage and output size
                # For blended attars: each oil's percentage of the total
                # For perfumes: oil_percentage determines how much is oil vs ethanol
                percentage = float(ingredient.percentage or 100) / 100
                oil_ml = output_ml * oil_percentage * percentage * quantity
                usage.append({
                    'raw_material': raw_material,
                    'quantity': oil_ml,
                    'unit': 'ml'
                })

        return usage

    def check_raw_material_availability(self, quantity=1):
        """
        Check if raw materials are available to produce given quantity.
        Returns: {'available': bool, 'shortages': [{'material': obj, 'required': float, 'available': float}]}
        """
        usage = self.get_raw_material_usage(quantity)
        shortages = []

        for item in usage:
            rm = item['raw_material']
            required = item['quantity']
            available = float(rm.quantity_in_stock or 0)

            if available < required:
                shortages.append({
                    'material': rm,
                    'required': required,
                    'available': available,
                    'unit': item['unit']
                })

        return {
            'available': len(shortages) == 0,
            'shortages': shortages,
            'usage': usage
        }

    def deduct_raw_materials(self, quantity=1, location_id=None, sale_id=None):
        """
        Deduct raw materials from stock for producing given quantity.
        Returns: {'success': bool, 'message': str, 'deductions': list}
        """
        availability = self.check_raw_material_availability(quantity)

        if not availability['available']:
            shortage_msgs = []
            for s in availability['shortages']:
                shortage_msgs.append(f"{s['material'].name}: need {s['required']:.2f} {s['unit']}, have {s['available']:.2f}")
            return {
                'success': False,
                'message': f"Insufficient raw materials: {'; '.join(shortage_msgs)}",
                'deductions': []
            }

        deductions = []
        for item in availability['usage']:
            rm = item['raw_material']
            qty = item['quantity']

            # Deduct from raw material stock
            rm.quantity_in_stock = float(rm.quantity_in_stock or 0) - qty
            deductions.append({
                'material_id': rm.id,
                'material_name': rm.name,
                'quantity': qty,
                'unit': item['unit']
            })

        return {
            'success': True,
            'message': f"Deducted raw materials for {quantity} unit(s)",
            'deductions': deductions
        }

    def __repr__(self):
        return f'<Product {self.code} - {self.name}>'


class Customer(db.Model):
    """Customer management"""
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, index=True)
    phone = db.Column(db.String(32), unique=True, index=True)
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    city = db.Column(db.String(64))
    postal_code = db.Column(db.String(16))

    # Customer type and loyalty
    customer_type = db.Column(db.String(32), default='regular')  # regular, vip, wholesale
    loyalty_points = db.Column(db.Integer, default=0)
    account_balance = db.Column(db.Numeric(10, 2), default=0.00)  # For credit customers

    # Marketing
    birthday = db.Column(db.Date)
    anniversary = db.Column(db.Date)
    notes = db.Column(db.Text)

    # Receipt preferences
    receipt_preference = db.Column(db.String(32), default='print')  # print, email, whatsapp, none
    whatsapp_optin = db.Column(db.Boolean, default=False)
    email_optin = db.Column(db.Boolean, default=False)
    sms_optin = db.Column(db.Boolean, default=True)

    # Referral system
    referral_code = db.Column(db.String(16), unique=True, index=True)
    referred_by_id = db.Column(db.Integer, db.ForeignKey('customers.id'))

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sales = db.relationship('Sale', backref='customer', lazy='dynamic')

    @property
    def total_purchases(self):
        """Calculate total purchase amount"""
        return db.session.query(db.func.sum(Sale.total))\
            .filter(Sale.customer_id == self.id)\
            .scalar() or 0

    @property
    def loyalty_tier(self):
        """Get customer loyalty tier based on points"""
        if self.loyalty_points >= 2500:
            return 'Platinum'
        elif self.loyalty_points >= 1000:
            return 'Gold'
        elif self.loyalty_points >= 500:
            return 'Silver'
        else:
            return 'Bronze'

    @property
    def loyalty_tier_color(self):
        """Get color for loyalty tier badge"""
        tier_colors = {
            'Platinum': 'dark',
            'Gold': 'warning',
            'Silver': 'secondary',
            'Bronze': 'info'
        }
        return tier_colors.get(self.loyalty_tier, 'secondary')

    @property
    def points_to_next_tier(self):
        """Calculate points needed for next tier"""
        if self.loyalty_points >= 2500:
            return 0  # Already at highest tier
        elif self.loyalty_points >= 1000:
            return 2500 - self.loyalty_points
        elif self.loyalty_points >= 500:
            return 1000 - self.loyalty_points
        else:
            return 500 - self.loyalty_points

    @property
    def next_tier_name(self):
        """Get name of next loyalty tier"""
        if self.loyalty_points >= 2500:
            return None
        elif self.loyalty_points >= 1000:
            return 'Platinum'
        elif self.loyalty_points >= 500:
            return 'Gold'
        else:
            return 'Silver'

    @property
    def points_value_pkr(self):
        """Get PKR value of current loyalty points (100 points = Rs. 100)"""
        return self.loyalty_points

    def add_loyalty_points(self, amount_spent):
        """Add loyalty points based on purchase amount (1 point per Rs. 100)"""
        points_earned = int(amount_spent / 100)
        self.loyalty_points += points_earned
        return points_earned

    def redeem_points(self, points_to_redeem):
        """Redeem loyalty points (100 points = Rs. 100 discount)"""
        if points_to_redeem > self.loyalty_points:
            return False, "Insufficient loyalty points"
        if points_to_redeem < 100:
            return False, "Minimum 100 points required for redemption"
        self.loyalty_points -= points_to_redeem
        discount_amount = points_to_redeem  # 1:1 ratio with PKR
        return True, discount_amount

    def __repr__(self):
        return f'<Customer {self.name}>'


class Sale(db.Model):
    """Sales transactions"""
    __tablename__ = 'sales'

    id = db.Column(db.Integer, primary_key=True)
    sale_number = db.Column(db.String(64), unique=True, nullable=False, index=True)
    sale_date = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # References
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), index=True)  # Kiosk where sale occurred

    # Amounts
    subtotal = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    discount = db.Column(db.Numeric(10, 2), default=0.00)
    discount_type = db.Column(db.String(16), default='amount')  # amount or percentage
    tax = db.Column(db.Numeric(10, 2), default=0.00)
    total = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)

    # Payment
    payment_method = db.Column(db.String(32), nullable=False)
    # cash, card, bank_transfer, easypaisa, jazzcash, credit
    payment_status = db.Column(db.String(32), default='paid')  # paid, partial, pending
    amount_paid = db.Column(db.Numeric(10, 2), default=0.00)
    amount_due = db.Column(db.Numeric(10, 2), default=0.00)
    is_split_payment = db.Column(db.Boolean, default=False)  # True if paid with multiple methods

    # Status
    status = db.Column(db.String(32), default='completed')  # completed, refunded, cancelled, held
    notes = db.Column(db.Text)

    # Sync tracking
    synced = db.Column(db.Boolean, default=False)
    synced_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    items = db.relationship('SaleItem', backref='sale', lazy='dynamic', cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='sale', lazy='dynamic', cascade='all, delete-orphan')
    location = db.relationship('Location', backref=db.backref('sales', lazy='dynamic'))

    def calculate_totals(self):
        """Calculate sale totals from items"""
        from decimal import Decimal

        # Sum item subtotals, ensure Decimal
        self.subtotal = sum((item.subtotal or Decimal('0')) for item in self.items)
        if not isinstance(self.subtotal, Decimal):
            self.subtotal = Decimal(str(self.subtotal))

        # Ensure discount is Decimal
        discount = self.discount if isinstance(self.discount, Decimal) else Decimal(str(self.discount or 0))

        # Apply discount
        if self.discount_type == 'percentage':
            discount_amount = (self.subtotal * discount) / Decimal('100')
        else:
            discount_amount = discount

        # Calculate tax
        taxable_amount = self.subtotal - discount_amount
        tax_rate = Decimal(str(self.tax or 0))
        tax_amount = (taxable_amount * tax_rate) / Decimal('100')

        self.total = self.subtotal - discount_amount + tax_amount
        return self.total

    def __repr__(self):
        return f'<Sale {self.sale_number}>'


class SaleItem(db.Model):
    """Individual items in a sale"""
    __tablename__ = 'sale_items'

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)

    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    discount = db.Column(db.Numeric(10, 2), default=0.00)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def calculate_subtotal(self):
        """Calculate item subtotal"""
        from decimal import Decimal
        qty = Decimal(str(self.quantity or 0))
        price = self.unit_price if isinstance(self.unit_price, Decimal) else Decimal(str(self.unit_price or 0))
        disc = self.discount if isinstance(self.discount, Decimal) else Decimal(str(self.discount or 0))
        self.subtotal = (qty * price) - disc
        return self.subtotal

    def __repr__(self):
        return f'<SaleItem {self.id}>'


class Payment(db.Model):
    """Payment transactions for sales"""
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)

    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(32), nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    reference_number = db.Column(db.String(128))  # Transaction ID, check number, etc.
    notes = db.Column(db.Text)
    payment_order = db.Column(db.Integer, default=1)  # Order in split payment sequence

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Payment {self.id} - {self.amount}>'


class DigitalReceipt(db.Model):
    """Track digital receipts sent to customers"""
    __tablename__ = 'digital_receipts'

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))

    delivery_method = db.Column(db.String(32), nullable=False)  # email, whatsapp, sms, qr_code
    recipient = db.Column(db.String(256), nullable=False)  # Email or phone number

    status = db.Column(db.String(32), default='pending')  # pending, sent, delivered, failed
    sent_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)

    # For QR code receipt lookup
    receipt_token = db.Column(db.String(64), unique=True, index=True)
    qr_code_path = db.Column(db.String(512))

    # Error tracking
    error_message = db.Column(db.Text)
    provider_response = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    sale = db.relationship('Sale', backref=db.backref('digital_receipts', lazy='dynamic'))
    customer = db.relationship('Customer', backref=db.backref('digital_receipts', lazy='dynamic'))

    def __repr__(self):
        return f'<DigitalReceipt {self.id} - {self.delivery_method}>'


class StockMovement(db.Model):
    """Track all stock movements (in/out/adjustment)"""
    __tablename__ = 'stock_movements'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    movement_type = db.Column(db.String(32), nullable=False)
    # Types: purchase, sale, adjustment, return, damage, transfer_in, transfer_out
    quantity = db.Column(db.Integer, nullable=False)  # Positive for in, negative for out
    reference = db.Column(db.String(128))  # Reference to sale, PO, transfer, etc.
    notes = db.Column(db.Text)

    # Multi-kiosk support
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), index=True)  # Location where movement occurred
    transfer_id = db.Column(db.Integer, db.ForeignKey('stock_transfers.id'))  # Reference to transfer if applicable

    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationships
    location = db.relationship('Location', backref=db.backref('stock_movements', lazy='dynamic'))
    transfer = db.relationship('StockTransfer', backref=db.backref('movements', lazy='dynamic'))

    def __repr__(self):
        return f'<StockMovement {self.movement_type} - {self.quantity}>'


class PurchaseOrder(db.Model):
    """Purchase orders from suppliers"""
    __tablename__ = 'purchase_orders'

    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(64), unique=True, nullable=False, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    expected_date = db.Column(db.DateTime)
    received_date = db.Column(db.DateTime)

    # Basic totals
    subtotal = db.Column(db.Numeric(10, 2), default=0.00)
    tax = db.Column(db.Numeric(10, 2), default=0.00)
    total = db.Column(db.Numeric(10, 2), default=0.00)

    # Cost breakdown totals
    total_packaging_cost = db.Column(db.Numeric(10, 2), default=0.00)
    total_delivery_cost = db.Column(db.Numeric(10, 2), default=0.00)
    total_bottle_cost = db.Column(db.Numeric(10, 2), default=0.00)
    grand_total_landed = db.Column(db.Numeric(12, 2), default=0.00)

    # Warehouse receiving
    receiving_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))

    # Payment tracking
    amount_paid = db.Column(db.Numeric(12, 2), default=0.00)
    amount_due = db.Column(db.Numeric(12, 2), default=0.00)
    payment_status = db.Column(db.String(32), default='unpaid')  # unpaid, partial, paid

    status = db.Column(db.String(32), default='pending')
    # draft, pending, ordered, partial, received, cancelled
    notes = db.Column(db.Text)

    # Auto-reorder support
    is_auto_generated = db.Column(db.Boolean, default=False)
    source_type = db.Column(db.String(32), default='manual')  # manual, auto_reorder

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    items = db.relationship('PurchaseOrderItem', backref='purchase_order', lazy='dynamic',
                          cascade='all, delete-orphan')
    receiving_location = db.relationship('Location', foreign_keys=[receiving_location_id])

    def calculate_totals(self):
        """Calculate all totals from items"""
        from decimal import Decimal
        total_base = Decimal('0')
        total_packaging = Decimal('0')
        total_delivery = Decimal('0')
        total_bottle = Decimal('0')

        for item in self.items:
            qty = item.quantity_received or item.quantity_ordered
            total_base += (item.base_cost or Decimal('0')) * qty
            total_packaging += (item.packaging_cost or Decimal('0')) * qty
            total_delivery += (item.delivery_cost or Decimal('0')) * qty
            total_bottle += (item.bottle_cost or Decimal('0')) * qty

        self.subtotal = total_base
        self.total_packaging_cost = total_packaging
        self.total_delivery_cost = total_delivery
        self.total_bottle_cost = total_bottle
        self.grand_total_landed = total_base + total_packaging + total_delivery + total_bottle
        self.total = self.grand_total_landed + (self.tax or Decimal('0'))
        self.amount_due = self.total - (self.amount_paid or Decimal('0'))

    def __repr__(self):
        return f'<PurchaseOrder {self.po_number}>'


class PurchaseOrderItem(db.Model):
    """Items in a purchase order"""
    __tablename__ = 'purchase_order_items'

    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)

    quantity_ordered = db.Column(db.Integer, nullable=False)
    quantity_received = db.Column(db.Integer, default=0)
    unit_cost = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)

    # Cost breakdown per item (at time of receiving)
    base_cost = db.Column(db.Numeric(10, 2), default=0.00)
    packaging_cost = db.Column(db.Numeric(10, 2), default=0.00)
    delivery_cost = db.Column(db.Numeric(10, 2), default=0.00)
    bottle_cost = db.Column(db.Numeric(10, 2), default=0.00)
    landed_cost = db.Column(db.Numeric(10, 2), default=0.00)  # Total per unit

    # Receiving details
    received_at = db.Column(db.DateTime)
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    receiving_notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    product = db.relationship('Product')
    receiver = db.relationship('User', foreign_keys=[received_by])

    def calculate_landed_cost(self):
        """Calculate landed cost from components"""
        from decimal import Decimal
        self.landed_cost = (
            (self.base_cost or Decimal('0')) +
            (self.packaging_cost or Decimal('0')) +
            (self.delivery_cost or Decimal('0')) +
            (self.bottle_cost or Decimal('0'))
        )
        return self.landed_cost

    def __repr__(self):
        return f'<PurchaseOrderItem {self.id}>'


class SyncQueue(db.Model):
    """Queue for offline operations to sync when online"""
    __tablename__ = 'sync_queue'

    id = db.Column(db.Integer, primary_key=True)
    table_name = db.Column(db.String(64), nullable=False)
    operation = db.Column(db.String(32), nullable=False)  # insert, update, delete
    record_id = db.Column(db.Integer, nullable=False)
    data_json = db.Column(db.Text)  # JSON serialized data

    status = db.Column(db.String(32), default='pending')  # pending, synced, failed
    error_message = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    synced_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<SyncQueue {self.table_name} - {self.operation}>'


class Setting(db.Model):
    """Application settings and configuration"""
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(128), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    category = db.Column(db.String(64))  # business, email, sync, pos, etc.
    description = db.Column(db.Text)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Setting {self.key}>'


class ActivityLog(db.Model):
    """Log of all critical activities"""
    __tablename__ = 'activity_logs'
    __table_args__ = (
        db.Index('ix_activity_logs_user_timestamp', 'user_id', 'timestamp'),
        db.Index('ix_activity_logs_action_timestamp', 'action', 'timestamp'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    action = db.Column(db.String(128), nullable=False, index=True)
    entity_type = db.Column(db.String(64))  # sale, product, user, etc.
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(64))

    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationship
    user = db.relationship('User')

    def __repr__(self):
        return f'<ActivityLog {self.action}>'


class Report(db.Model):
    """Generated reports log"""
    __tablename__ = 'reports'

    id = db.Column(db.Integer, primary_key=True)
    report_type = db.Column(db.String(64), nullable=False)  # daily, weekly, monthly, custom
    report_date = db.Column(db.Date, nullable=False)
    generated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    file_path = db.Column(db.String(512))

    sent_to = db.Column(db.Text)  # Comma-separated email addresses
    status = db.Column(db.String(32), default='generated')  # generated, sent, failed

    generated_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationship
    user = db.relationship('User')

    def __repr__(self):
        return f'<Report {self.report_type} - {self.report_date}>'


class DayClose(db.Model):
    """End-of-day sales closure tracking"""
    __tablename__ = 'day_closes'

    id = db.Column(db.Integer, primary_key=True)
    close_date = db.Column(db.Date, nullable=False, index=True)
    closed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), index=True)  # Kiosk for day close

    # Unique constraint: one day close per date per location
    __table_args__ = (
        db.UniqueConstraint('close_date', 'location_id', name='uix_dayclose_location'),
    )

    # Sales summary
    total_sales = db.Column(db.Integer, default=0)  # Number of transactions
    total_revenue = db.Column(db.Numeric(12, 2), default=0.00)
    total_cash = db.Column(db.Numeric(12, 2), default=0.00)
    total_card = db.Column(db.Numeric(12, 2), default=0.00)
    total_other = db.Column(db.Numeric(12, 2), default=0.00)

    # Expenses
    total_expenses = db.Column(db.Numeric(12, 2), default=0.00)

    # Cash drawer
    opening_balance = db.Column(db.Numeric(12, 2), default=0.00)
    closing_balance = db.Column(db.Numeric(12, 2), default=0.00)
    expected_cash = db.Column(db.Numeric(12, 2), default=0.00)
    cash_variance = db.Column(db.Numeric(12, 2), default=0.00)  # Difference between actual and expected

    # Denomination counting (Pakistani currency)
    denom_5000 = db.Column(db.Integer, default=0)  # Rs. 5000 notes
    denom_1000 = db.Column(db.Integer, default=0)  # Rs. 1000 notes
    denom_500 = db.Column(db.Integer, default=0)   # Rs. 500 notes
    denom_100 = db.Column(db.Integer, default=0)   # Rs. 100 notes
    denom_50 = db.Column(db.Integer, default=0)    # Rs. 50 notes
    denom_20 = db.Column(db.Integer, default=0)    # Rs. 20 notes
    denom_10 = db.Column(db.Integer, default=0)    # Rs. 10 notes/coins
    denom_5 = db.Column(db.Integer, default=0)     # Rs. 5 coins
    denom_2 = db.Column(db.Integer, default=0)     # Rs. 2 coins
    denom_1 = db.Column(db.Integer, default=0)     # Rs. 1 coins
    counted_total = db.Column(db.Numeric(12, 2), default=0.00)  # Total from denomination count

    # Cash movements during the day
    cash_in = db.Column(db.Numeric(12, 2), default=0.00)   # Cash added to drawer (e.g., change)
    cash_out = db.Column(db.Numeric(12, 2), default=0.00)  # Cash removed (e.g., expenses, deposits)

    # Variance approval (for discrepancies)
    variance_status = db.Column(db.String(32), default='pending')  # pending, approved, rejected
    variance_approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    variance_approved_at = db.Column(db.DateTime)
    variance_reason = db.Column(db.Text)  # Explanation for variance

    # Detailed payment breakdown for Z-Report
    total_easypaisa = db.Column(db.Numeric(12, 2), default=0.00)
    total_jazzcash = db.Column(db.Numeric(12, 2), default=0.00)
    total_bank_transfer = db.Column(db.Numeric(12, 2), default=0.00)
    total_credit = db.Column(db.Numeric(12, 2), default=0.00)

    # Sales reconciliation for Z-Report
    gross_sales = db.Column(db.Numeric(12, 2), default=0.00)  # Before discounts
    total_discounts = db.Column(db.Numeric(12, 2), default=0.00)
    total_tax = db.Column(db.Numeric(12, 2), default=0.00)
    net_sales = db.Column(db.Numeric(12, 2), default=0.00)  # After discounts + tax
    total_refunds = db.Column(db.Numeric(12, 2), default=0.00)

    # Z-Report tracking
    z_report_number = db.Column(db.String(32))  # Z-001, Z-002, etc.
    shift_count = db.Column(db.Integer, default=1)  # Number of shifts that day

    # Report
    report_generated = db.Column(db.Boolean, default=False)
    report_path = db.Column(db.String(512))
    report_sent = db.Column(db.Boolean, default=False)
    sent_to = db.Column(db.String(256))  # Email address(es)

    notes = db.Column(db.Text)
    closed_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship('User', foreign_keys=[closed_by])
    location = db.relationship('Location', backref=db.backref('day_closes', lazy='dynamic'))
    approved_by_user = db.relationship('User', foreign_keys=[variance_approved_by])

    def __repr__(self):
        return f'<DayClose {self.close_date}>'

    def calculate_denomination_total(self):
        """Calculate total from denomination counts"""
        total = (
            (self.denom_5000 or 0) * 5000 +
            (self.denom_1000 or 0) * 1000 +
            (self.denom_500 or 0) * 500 +
            (self.denom_100 or 0) * 100 +
            (self.denom_50 or 0) * 50 +
            (self.denom_20 or 0) * 20 +
            (self.denom_10 or 0) * 10 +
            (self.denom_5 or 0) * 5 +
            (self.denom_2 or 0) * 2 +
            (self.denom_1 or 0) * 1
        )
        return total


class InventorySpotCheck(db.Model):
    """Inventory spot check during day close - for daily/fortnightly verification"""
    __tablename__ = 'inventory_spot_checks'

    id = db.Column(db.Integer, primary_key=True)
    day_close_id = db.Column(db.Integer, db.ForeignKey('day_closes.id'), index=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False, index=True)
    checked_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    check_date = db.Column(db.Date, nullable=False, index=True)
    check_type = db.Column(db.String(32), default='daily')  # daily, weekly, fortnightly, monthly, random

    # Summary
    total_items_checked = db.Column(db.Integer, default=0)
    items_matched = db.Column(db.Integer, default=0)
    items_variance = db.Column(db.Integer, default=0)
    total_variance_value = db.Column(db.Numeric(12, 2), default=0.00)

    # Status
    status = db.Column(db.String(32), default='pending')  # pending, completed, approved, rejected
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    day_close = db.relationship('DayClose', backref=db.backref('inventory_checks', lazy='dynamic'))
    location = db.relationship('Location', backref=db.backref('spot_checks', lazy='dynamic'))
    user = db.relationship('User', foreign_keys=[checked_by])
    approver = db.relationship('User', foreign_keys=[approved_by])
    items = db.relationship('InventorySpotCheckItem', backref='spot_check', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<InventorySpotCheck {self.check_date} - {self.location_id}>'


class InventorySpotCheckItem(db.Model):
    """Individual item in inventory spot check"""
    __tablename__ = 'inventory_spot_check_items'

    id = db.Column(db.Integer, primary_key=True)
    spot_check_id = db.Column(db.Integer, db.ForeignKey('inventory_spot_checks.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), index=True)
    raw_material_id = db.Column(db.Integer, db.ForeignKey('raw_materials.id'), index=True)

    # Quantities
    system_quantity = db.Column(db.Numeric(10, 2), default=0)  # What system says we have
    physical_quantity = db.Column(db.Numeric(10, 2), default=0)  # What was actually counted
    variance = db.Column(db.Numeric(10, 2), default=0)  # physical - system

    # Values
    unit_cost = db.Column(db.Numeric(10, 2), default=0)
    variance_value = db.Column(db.Numeric(10, 2), default=0)  # variance * unit_cost

    # Variance reason
    variance_reason = db.Column(db.String(128))  # theft, damage, counting_error, system_error, etc.
    notes = db.Column(db.Text)

    # Relationships
    product = db.relationship('Product')
    raw_material = db.relationship('RawMaterial')

    def __repr__(self):
        return f'<InventorySpotCheckItem {self.id}>'

    def calculate_variance(self):
        """Calculate variance between physical and system quantity"""
        self.variance = (self.physical_quantity or 0) - (self.system_quantity or 0)
        self.variance_value = self.variance * (self.unit_cost or 0)
        return self.variance


# ============================================================================
# MULTI-KIOSK SUPPORT MODELS
# ============================================================================

class Location(db.Model):
    """Represents a physical location (kiosk or warehouse)"""
    __tablename__ = 'locations'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)  # e.g., "WH-001", "K-001"
    name = db.Column(db.String(128), nullable=False)
    location_type = db.Column(db.String(32), nullable=False)  # 'warehouse' or 'kiosk'

    # Address details
    address = db.Column(db.Text)
    city = db.Column(db.String(64))
    phone = db.Column(db.String(32))
    email = db.Column(db.String(120))

    # Warehouse reference (for kiosks - which warehouse supplies this kiosk)
    parent_warehouse_id = db.Column(db.Integer, db.ForeignKey('locations.id'))

    # Manager assignment
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Settings
    is_active = db.Column(db.Boolean, default=True)
    can_sell = db.Column(db.Boolean, default=True)  # Kiosks can sell, warehouses typically cannot

    # Kiosk charges (per-location pricing)
    kiosk_charge_rate = db.Column(db.Numeric(5, 2), default=0.00)  # Percentage (0-100)
    kiosk_charge_type = db.Column(db.String(32), default='percentage')  # 'percentage' or 'fixed'

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Self-referential relationship for warehouse -> kiosks
    parent_warehouse = db.relationship('Location', remote_side=[id], backref='child_kiosks')
    manager = db.relationship('User', foreign_keys=[manager_id], backref='managed_locations')

    @property
    def is_warehouse(self):
        """Check if this location is a warehouse"""
        return self.location_type == 'warehouse'

    @property
    def is_kiosk(self):
        """Check if this location is a kiosk"""
        return self.location_type == 'kiosk'

    def get_final_cost_for_product(self, product):
        """Calculate final cost including kiosk charges"""
        landed_cost = float(product.landed_cost or product.cost_price or 0)
        if self.kiosk_charge_type == 'percentage':
            return landed_cost + (landed_cost * float(self.kiosk_charge_rate or 0) / 100)
        else:
            return landed_cost + float(self.kiosk_charge_rate or 0)

    def get_stock_for_product(self, product_id):
        """Get stock level for a specific product at this location"""
        stock = LocationStock.query.filter_by(
            location_id=self.id,
            product_id=product_id
        ).first()
        return stock.available_quantity if stock else 0

    def __repr__(self):
        return f'<Location {self.code} - {self.name}>'


class LocationStock(db.Model):
    """Stock levels per product per location"""
    __tablename__ = 'location_stock'

    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)

    quantity = db.Column(db.Integer, default=0)
    reserved_quantity = db.Column(db.Integer, default=0)  # Stock reserved for pending transfers
    reorder_level = db.Column(db.Integer, default=10)  # Location-specific reorder level

    # Last stock activity
    last_movement_at = db.Column(db.DateTime)
    last_count_at = db.Column(db.DateTime)  # Physical inventory count

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: one stock record per product per location
    __table_args__ = (
        db.UniqueConstraint('location_id', 'product_id', name='uix_location_product'),
    )

    # Relationships
    location = db.relationship('Location', backref=db.backref('stock', lazy='dynamic'))
    product = db.relationship('Product', backref=db.backref('location_stocks', lazy='dynamic'))

    @property
    def available_quantity(self):
        """Quantity available for sale (excludes reserved)"""
        return max(0, self.quantity - self.reserved_quantity)

    @property
    def is_low_stock(self):
        """Check if stock is below reorder level"""
        return self.available_quantity <= self.reorder_level

    @property
    def stock_value(self):
        """Calculate stock value at cost price"""
        if self.product:
            return float(self.quantity * self.product.cost_price)
        return 0

    def __repr__(self):
        return f'<LocationStock {self.location_id}:{self.product_id} qty={self.quantity}>'


class StockTransfer(db.Model):
    """Stock transfer between locations"""
    __tablename__ = 'stock_transfers'

    id = db.Column(db.Integer, primary_key=True)
    transfer_number = db.Column(db.String(64), unique=True, nullable=False, index=True)

    # Locations
    source_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    destination_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)

    # Status workflow: draft -> requested -> approved -> dispatched -> received
    #                           \-> rejected
    #                  any (before dispatched) -> cancelled
    status = db.Column(db.String(32), default='draft', index=True)
    # Statuses: draft, requested, approved, dispatched, received, rejected, cancelled

    # Priority
    priority = db.Column(db.String(16), default='normal')  # low, normal, high, urgent
    expected_delivery_date = db.Column(db.Date)

    # Timestamps for workflow
    requested_at = db.Column(db.DateTime)
    approved_at = db.Column(db.DateTime)
    dispatched_at = db.Column(db.DateTime)
    received_at = db.Column(db.DateTime)

    # Users involved
    requested_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    dispatched_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Notes
    request_notes = db.Column(db.Text)
    approval_notes = db.Column(db.Text)
    dispatch_notes = db.Column(db.Text)
    receive_notes = db.Column(db.Text)
    rejection_reason = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    source_location = db.relationship('Location', foreign_keys=[source_location_id],
                                       backref=db.backref('outgoing_transfers', lazy='dynamic'))
    destination_location = db.relationship('Location', foreign_keys=[destination_location_id],
                                            backref=db.backref('incoming_transfers', lazy='dynamic'))
    requester = db.relationship('User', foreign_keys=[requested_by], backref='transfer_requests')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='transfer_approvals')
    dispatcher = db.relationship('User', foreign_keys=[dispatched_by], backref='transfer_dispatches')
    receiver = db.relationship('User', foreign_keys=[received_by], backref='transfer_receipts')
    items = db.relationship('StockTransferItem', backref='transfer', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def total_items(self):
        """Get total number of items in transfer"""
        return self.items.count()

    @property
    def items_list(self):
        """Get items as a list (for template iteration)"""
        return list(self.items)

    @property
    def total_quantity_requested(self):
        """Get total quantity requested across all items"""
        return sum(item.quantity_requested for item in self.items) or 0

    @property
    def total_quantity_approved(self):
        """Get total quantity approved across all items"""
        return sum(item.quantity_approved or 0 for item in self.items)

    @property
    def total_quantity_received(self):
        """Get total quantity received across all items"""
        return sum(item.quantity_received or 0 for item in self.items)

    @property
    def status_badge_class(self):
        """Get Bootstrap badge class for status"""
        status_classes = {
            'draft': 'secondary',
            'requested': 'info',
            'approved': 'primary',
            'dispatched': 'warning',
            'received': 'success',
            'rejected': 'danger',
            'cancelled': 'dark'
        }
        return status_classes.get(self.status, 'secondary')

    @property
    def can_approve(self):
        """Check if transfer can be approved"""
        return self.status == 'requested'

    @property
    def can_dispatch(self):
        """Check if transfer can be dispatched"""
        return self.status == 'approved'

    @property
    def can_receive(self):
        """Check if transfer can be received"""
        return self.status == 'dispatched'

    @property
    def can_cancel(self):
        """Check if transfer can be cancelled"""
        return self.status in ['draft', 'requested', 'approved']

    def __repr__(self):
        return f'<StockTransfer {self.transfer_number} {self.status}>'


class StockTransferItem(db.Model):
    """Individual items in a stock transfer"""
    __tablename__ = 'stock_transfer_items'

    id = db.Column(db.Integer, primary_key=True)
    transfer_id = db.Column(db.Integer, db.ForeignKey('stock_transfers.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)

    quantity_requested = db.Column(db.Integer, nullable=False)
    quantity_approved = db.Column(db.Integer)  # May differ from requested
    quantity_dispatched = db.Column(db.Integer)  # Actually sent
    quantity_received = db.Column(db.Integer)  # Actually received (for discrepancy tracking)

    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    product = db.relationship('Product', backref=db.backref('transfer_items', lazy='dynamic'))

    @property
    def has_discrepancy(self):
        """Check if there's a discrepancy between dispatched and received"""
        if self.quantity_dispatched and self.quantity_received:
            return self.quantity_dispatched != self.quantity_received
        return False

    @property
    def discrepancy_amount(self):
        """Get the discrepancy amount (positive = received more, negative = received less)"""
        if self.quantity_dispatched and self.quantity_received:
            return self.quantity_received - self.quantity_dispatched
        return 0

    def __repr__(self):
        return f'<StockTransferItem {self.id} product={self.product_id} qty={self.quantity_requested}>'


class GatePass(db.Model):
    """Gate Pass for stock dispatch from warehouse"""
    __tablename__ = 'gate_passes'

    id = db.Column(db.Integer, primary_key=True)
    gate_pass_number = db.Column(db.String(64), unique=True, nullable=False, index=True)
    transfer_id = db.Column(db.Integer, db.ForeignKey('stock_transfers.id'), nullable=False)

    # Vehicle/Carrier Details
    vehicle_number = db.Column(db.String(32))
    vehicle_type = db.Column(db.String(32))  # bike, car, van, truck
    driver_name = db.Column(db.String(128))
    driver_phone = db.Column(db.String(32))
    driver_cnic = db.Column(db.String(20))

    # Dispatch Details
    dispatch_date = db.Column(db.DateTime, default=datetime.utcnow)
    expected_arrival = db.Column(db.DateTime)
    actual_arrival = db.Column(db.DateTime)

    # Security/Verification
    security_seal_number = db.Column(db.String(64))
    verified_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    verification_notes = db.Column(db.Text)

    # Status
    status = db.Column(db.String(32), default='issued')
    # Statuses: issued, in_transit, delivered, verified, discrepancy

    # Totals (calculated from transfer items)
    total_items = db.Column(db.Integer, default=0)
    total_quantity = db.Column(db.Integer, default=0)
    total_value = db.Column(db.Numeric(12, 2), default=0.00)

    # Notes
    dispatch_notes = db.Column(db.Text)
    delivery_notes = db.Column(db.Text)
    special_instructions = db.Column(db.Text)

    # Timestamps
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    transfer = db.relationship('StockTransfer', backref=db.backref('gate_pass', uselist=False))
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_gate_passes')
    verifier = db.relationship('User', foreign_keys=[verified_by], backref='verified_gate_passes')

    @property
    def status_badge_class(self):
        """Get Bootstrap badge class for status"""
        status_classes = {
            'issued': 'info',
            'in_transit': 'warning',
            'delivered': 'primary',
            'verified': 'success',
            'discrepancy': 'danger'
        }
        return status_classes.get(self.status, 'secondary')

    @property
    def is_editable(self):
        """Check if gate pass can still be edited"""
        return self.status in ['issued']

    def calculate_totals(self):
        """Calculate totals from transfer items"""
        if self.transfer:
            self.total_items = self.transfer.items.count()
            self.total_quantity = sum(
                item.quantity_dispatched or item.quantity_approved or 0
                for item in self.transfer.items
            )
            self.total_value = sum(
                (item.quantity_dispatched or item.quantity_approved or 0) * float(item.product.cost_price)
                for item in self.transfer.items
                if item.product
            )

    def __repr__(self):
        return f'<GatePass {self.gate_pass_number}>'


# ============================================================
# PRODUCTION SYSTEM MODELS
# For Attar and Perfume Manufacturing
# ============================================================

class RawMaterialCategory(db.Model):
    """Categories for raw materials: OIL, ETHANOL, BOTTLE"""
    __tablename__ = 'raw_material_categories'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)  # OIL, ETHANOL, BOTTLE
    name = db.Column(db.String(128), nullable=False)
    unit = db.Column(db.String(32), nullable=False)  # grams, ml, pieces
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    materials = db.relationship('RawMaterial', backref='category', lazy='dynamic')

    def __repr__(self):
        return f'<RawMaterialCategory {self.code}>'


class RawMaterial(db.Model):
    """Raw materials for production: oils, ethanol, bottles"""
    __tablename__ = 'raw_materials'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(256), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('raw_material_categories.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))

    # For bottles - size specification in ml
    bottle_size_ml = db.Column(db.Numeric(10, 2))  # 3ml, 6ml, 12ml, 30ml, 50ml, 100ml

    # Pricing (for raw material purchases)
    cost_per_unit = db.Column(db.Numeric(10, 4), nullable=False, default=0.00)

    # Global Stock (backup, main tracking via RawMaterialStock)
    quantity = db.Column(db.Numeric(12, 4), default=0)  # Supports decimal for grams/ml
    reorder_level = db.Column(db.Numeric(12, 4), default=100)
    reorder_quantity = db.Column(db.Numeric(12, 4), default=500)

    # Tracking
    batch_number = db.Column(db.String(64))
    expiry_date = db.Column(db.Date)

    # Status
    is_active = db.Column(db.Boolean, default=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    supplier = db.relationship('Supplier', backref='raw_materials')

    @property
    def is_low_stock(self):
        """Check if stock is below reorder level"""
        return self.quantity <= self.reorder_level

    @property
    def unit(self):
        """Get unit from category"""
        return self.category.unit if self.category else 'units'

    def __repr__(self):
        return f'<RawMaterial {self.code} - {self.name}>'


class RawMaterialStock(db.Model):
    """Location-specific stock for raw materials"""
    __tablename__ = 'raw_material_stock'

    id = db.Column(db.Integer, primary_key=True)
    raw_material_id = db.Column(db.Integer, db.ForeignKey('raw_materials.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)

    quantity = db.Column(db.Numeric(12, 4), default=0)
    reserved_quantity = db.Column(db.Numeric(12, 4), default=0)  # For pending production
    reorder_level = db.Column(db.Numeric(12, 4))

    last_movement_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    raw_material = db.relationship('RawMaterial', backref='location_stocks')
    location = db.relationship('Location', backref='raw_material_stocks')

    __table_args__ = (
        db.UniqueConstraint('raw_material_id', 'location_id', name='uix_rawmaterial_location'),
    )

    @property
    def available_quantity(self):
        """Get available quantity (total - reserved)"""
        return float(self.quantity or 0) - float(self.reserved_quantity or 0)

    @property
    def is_low_stock(self):
        """Check if below reorder level"""
        reorder = self.reorder_level or (self.raw_material.reorder_level if self.raw_material else 100)
        return self.quantity <= reorder

    def __repr__(self):
        return f'<RawMaterialStock {self.raw_material_id}@{self.location_id} qty={self.quantity}>'


class RawMaterialMovement(db.Model):
    """Track all raw material stock movements"""
    __tablename__ = 'raw_material_movements'

    id = db.Column(db.Integer, primary_key=True)
    raw_material_id = db.Column(db.Integer, db.ForeignKey('raw_materials.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    movement_type = db.Column(db.String(32), nullable=False)
    # Types: purchase, production_consumption, adjustment, transfer_in, transfer_out, damage

    quantity = db.Column(db.Numeric(12, 4), nullable=False)  # Positive for in, negative for out
    reference = db.Column(db.String(128))  # PO number, Production Order number
    notes = db.Column(db.Text)

    production_order_id = db.Column(db.Integer, db.ForeignKey('production_orders.id'))

    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationships
    raw_material = db.relationship('RawMaterial', backref='movements')
    location = db.relationship('Location', backref='raw_material_movements')
    user = db.relationship('User', backref='raw_material_movements')

    def __repr__(self):
        return f'<RawMaterialMovement {self.movement_type} {self.quantity}>'


class Recipe(db.Model):
    """Production recipe/formula for finished products (attars/perfumes)"""
    __tablename__ = 'recipes'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(256), nullable=False)

    # Recipe Type: single_oil, blended, perfume
    recipe_type = db.Column(db.String(32), nullable=False)

    # Output Product (the finished attar/perfume)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))

    # Output specifications
    output_size_ml = db.Column(db.Numeric(10, 2))  # e.g., 6ml, 30ml, 50ml

    # For perfumes: oil percentage (rest is ethanol)
    # 100% for attars, 35% for perfumes
    oil_percentage = db.Column(db.Numeric(5, 2), default=100.00)

    # Production constraints
    can_produce_at_warehouse = db.Column(db.Boolean, default=True)
    can_produce_at_kiosk = db.Column(db.Boolean, default=True)

    # Status
    is_active = db.Column(db.Boolean, default=True)
    version = db.Column(db.Integer, default=1)

    # Notes
    description = db.Column(db.Text)
    instructions = db.Column(db.Text)

    # Audit
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    product = db.relationship('Product', backref='recipes')
    ingredients = db.relationship('RecipeIngredient', backref='recipe', lazy='dynamic', cascade='all, delete-orphan')
    creator = db.relationship('User', backref='created_recipes')

    @property
    def ingredients_list(self):
        """Get ingredients as list for easy iteration"""
        return list(self.ingredients)

    @property
    def oil_ingredients(self):
        """Get only oil ingredients (not bottles)"""
        return [i for i in self.ingredients if not i.is_packaging]

    @property
    def bottle_ingredient(self):
        """Get the bottle/packaging ingredient"""
        for i in self.ingredients:
            if i.is_packaging:
                return i
        return None

    def __repr__(self):
        return f'<Recipe {self.code} - {self.name}>'


class RecipeIngredient(db.Model):
    """Ingredients in a recipe"""
    __tablename__ = 'recipe_ingredients'

    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    raw_material_id = db.Column(db.Integer, db.ForeignKey('raw_materials.id'), nullable=False)

    # For blended: percentage of total oil component (should sum to 100%)
    percentage = db.Column(db.Numeric(5, 2))  # e.g., 40.00 for 40%

    # For bottles - one bottle per product
    is_packaging = db.Column(db.Boolean, default=False)

    notes = db.Column(db.Text)

    # Relationships
    raw_material = db.relationship('RawMaterial', backref='recipe_usages')

    def __repr__(self):
        return f'<RecipeIngredient {self.raw_material_id} {self.percentage}%>'


class ProductionOrder(db.Model):
    """Production/Manufacturing order"""
    __tablename__ = 'production_orders'

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(64), unique=True, nullable=False, index=True)

    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)

    # Quantities
    quantity_ordered = db.Column(db.Integer, nullable=False)  # Number of units to produce
    quantity_produced = db.Column(db.Integer, default=0)  # Actual produced

    # Status workflow: draft -> pending -> approved -> in_progress -> completed
    #                              \-> rejected
    #                  cancelled <-/
    status = db.Column(db.String(32), default='draft', index=True)

    # Priority
    priority = db.Column(db.String(16), default='normal')  # low, normal, high, urgent
    due_date = db.Column(db.Date)

    # Timestamps
    requested_at = db.Column(db.DateTime)
    approved_at = db.Column(db.DateTime)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    # Users
    requested_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    produced_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Notes
    notes = db.Column(db.Text)
    rejection_reason = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    recipe = db.relationship('Recipe', backref='production_orders')
    product = db.relationship('Product', backref='production_orders')
    location = db.relationship('Location', backref='production_orders')
    requester = db.relationship('User', foreign_keys=[requested_by], backref='requested_productions')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='approved_productions')
    producer = db.relationship('User', foreign_keys=[produced_by], backref='executed_productions')
    material_consumptions = db.relationship('ProductionMaterialConsumption', backref='production_order',
                                            lazy='dynamic', cascade='all, delete-orphan')

    @property
    def status_badge_class(self):
        """Get Bootstrap badge class for status"""
        status_classes = {
            'draft': 'secondary',
            'pending': 'info',
            'approved': 'primary',
            'in_progress': 'warning',
            'completed': 'success',
            'rejected': 'danger',
            'cancelled': 'dark'
        }
        return status_classes.get(self.status, 'secondary')

    @property
    def can_approve(self):
        return self.status == 'pending'

    @property
    def can_start(self):
        return self.status == 'approved'

    @property
    def can_complete(self):
        return self.status == 'in_progress'

    @property
    def can_cancel(self):
        return self.status in ['draft', 'pending', 'approved']

    def __repr__(self):
        return f'<ProductionOrder {self.order_number} {self.status}>'


class ProductionMaterialConsumption(db.Model):
    """Track raw materials consumed in production"""
    __tablename__ = 'production_material_consumptions'

    id = db.Column(db.Integer, primary_key=True)
    production_order_id = db.Column(db.Integer, db.ForeignKey('production_orders.id'), nullable=False)
    raw_material_id = db.Column(db.Integer, db.ForeignKey('raw_materials.id'), nullable=False)

    quantity_required = db.Column(db.Numeric(12, 4), nullable=False)
    quantity_consumed = db.Column(db.Numeric(12, 4), default=0)

    unit = db.Column(db.String(32))  # grams, ml, pieces

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    raw_material = db.relationship('RawMaterial', backref='consumptions')

    def __repr__(self):
        return f'<ProductionConsumption {self.raw_material_id} qty={self.quantity_required}>'


class TransferRequest(db.Model):
    """Detailed transfer request with approval workflow"""
    __tablename__ = 'transfer_requests'

    id = db.Column(db.Integer, primary_key=True)
    request_number = db.Column(db.String(64), unique=True, nullable=False, index=True)
    transfer_id = db.Column(db.Integer, db.ForeignKey('stock_transfers.id'))

    # Request Type
    request_type = db.Column(db.String(32), default='regular')
    # Types: regular, urgent, emergency, scheduled, return

    # Justification
    reason = db.Column(db.Text, nullable=False)  # Why stock is needed
    justification = db.Column(db.Text)  # Business justification
    expected_usage_date = db.Column(db.Date)  # When stock will be used

    # Current Stock Info (at time of request)
    current_stock_level = db.Column(db.Text)  # JSON of current stock levels
    sales_forecast = db.Column(db.Text)  # Sales forecast data

    # Approval Workflow
    approval_level = db.Column(db.Integer, default=1)  # 1=Manager, 2=Regional, 3=Admin
    approved_by_manager = db.Column(db.Integer, db.ForeignKey('users.id'))
    manager_approval_date = db.Column(db.DateTime)
    manager_comments = db.Column(db.Text)

    approved_by_regional = db.Column(db.Integer, db.ForeignKey('users.id'))
    regional_approval_date = db.Column(db.DateTime)
    regional_comments = db.Column(db.Text)

    # Final Decision
    final_status = db.Column(db.String(32), default='pending')
    # Statuses: pending, manager_approved, regional_approved, approved, rejected, cancelled

    rejection_reason = db.Column(db.Text)

    # SLA Tracking
    requested_delivery_date = db.Column(db.Date)
    promised_delivery_date = db.Column(db.Date)
    actual_delivery_date = db.Column(db.Date)
    sla_met = db.Column(db.Boolean)

    # Timestamps
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    transfer = db.relationship('StockTransfer', backref=db.backref('request_details', uselist=False))
    creator = db.relationship('User', foreign_keys=[created_by], backref='transfer_requests_created')
    manager_approver = db.relationship('User', foreign_keys=[approved_by_manager])
    regional_approver = db.relationship('User', foreign_keys=[approved_by_regional])

    @property
    def is_overdue(self):
        """Check if request is overdue"""
        if self.requested_delivery_date and self.final_status not in ['approved', 'rejected', 'cancelled']:
            from datetime import date
            return date.today() > self.requested_delivery_date
        return False

    @property
    def days_pending(self):
        """Get number of days request has been pending"""
        if self.created_at:
            from datetime import datetime
            delta = datetime.utcnow() - self.created_at
            return delta.days
        return 0

    def __repr__(self):
        return f'<TransferRequest {self.request_number}>'


# ============================================================================
# DISCOUNT CONTROL MODELS
# ============================================================================

class DiscountLimit(db.Model):
    """Discount limits per role - controls maximum discount each role can apply"""
    __tablename__ = 'discount_limits'

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(64), nullable=False, unique=True, index=True)  # cashier, store_manager, etc.

    # Discount limits
    max_percentage = db.Column(db.Numeric(5, 2), default=0.00)  # Max % discount allowed
    max_amount = db.Column(db.Numeric(10, 2), default=0.00)  # Max amount discount allowed
    max_per_item_percentage = db.Column(db.Numeric(5, 2), default=0.00)  # Max % per item

    # Approval thresholds
    requires_approval_above = db.Column(db.Numeric(5, 2))  # Needs approval if discount % above this

    # Daily limits
    max_daily_discount_amount = db.Column(db.Numeric(12, 2))  # Max total discounts per day
    max_daily_discount_count = db.Column(db.Integer)  # Max number of discounts per day

    # Restrictions
    can_give_free_items = db.Column(db.Boolean, default=False)  # Can give 100% discount
    requires_reason = db.Column(db.Boolean, default=True)  # Must provide reason for discount
    allowed_reasons = db.Column(db.Text)  # JSON list of allowed discount reasons

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_allowed_reasons(self):
        """Get list of allowed discount reasons"""
        import json
        if self.allowed_reasons:
            try:
                return json.loads(self.allowed_reasons)
            except:
                return []
        return []

    def __repr__(self):
        return f'<DiscountLimit {self.role}>'


class DiscountApproval(db.Model):
    """Tracks discount approval requests and approvals"""
    __tablename__ = 'discount_approvals'

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), index=True)

    # Request details
    requested_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False, index=True)

    # Discount details
    discount_amount = db.Column(db.Numeric(10, 2), nullable=False)
    discount_percentage = db.Column(db.Numeric(5, 2))
    discount_type = db.Column(db.String(16), default='amount')  # amount or percentage
    original_total = db.Column(db.Numeric(12, 2), nullable=False)  # Sale total before discount
    final_total = db.Column(db.Numeric(12, 2))  # Sale total after discount

    # Reason
    discount_reason = db.Column(db.String(128), nullable=False)
    reason_details = db.Column(db.Text)

    # Status
    status = db.Column(db.String(32), default='pending')  # pending, approved, rejected, expired
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)

    # Approval code (for manager approval at POS)
    approval_code = db.Column(db.String(32))  # Manager enters this code to approve
    expires_at = db.Column(db.DateTime)  # Approval request expires after X minutes

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    sale = db.relationship('Sale', backref=db.backref('discount_approvals', lazy='dynamic'))
    requester = db.relationship('User', foreign_keys=[requested_by], backref='discount_requests')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='discount_approvals')
    location = db.relationship('Location', backref=db.backref('discount_approvals', lazy='dynamic'))

    def generate_approval_code(self):
        """Generate a random approval code"""
        import secrets
        self.approval_code = secrets.token_hex(4).upper()  # 8 character code
        return self.approval_code

    def is_expired(self):
        """Check if approval request has expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False

    def __repr__(self):
        return f'<DiscountApproval {self.id} - {self.status}>'


# ============================================================================
# VOID/REFUND CONTROL MODELS
# ============================================================================

class VoidRefundLimit(db.Model):
    """Void/Refund limits per role"""
    __tablename__ = 'void_refund_limits'

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(64), nullable=False, unique=True, index=True)

    # Void limits
    can_void_sale = db.Column(db.Boolean, default=False)
    void_time_limit_hours = db.Column(db.Integer, default=24)  # Can only void within X hours
    max_void_amount = db.Column(db.Numeric(12, 2))  # Max sale amount that can be voided
    void_requires_approval_above = db.Column(db.Numeric(12, 2))  # Needs approval for amounts above

    # Refund limits
    can_refund = db.Column(db.Boolean, default=False)
    refund_time_limit_days = db.Column(db.Integer, default=7)  # Refund within X days
    max_refund_amount = db.Column(db.Numeric(12, 2))  # Max refund amount per transaction
    refund_requires_approval_above = db.Column(db.Numeric(12, 2))  # Needs approval above

    # Daily limits
    max_daily_void_count = db.Column(db.Integer)
    max_daily_void_amount = db.Column(db.Numeric(12, 2))
    max_daily_refund_count = db.Column(db.Integer)
    max_daily_refund_amount = db.Column(db.Numeric(12, 2))

    # Requirements
    requires_reason = db.Column(db.Boolean, default=True)
    requires_customer_signature = db.Column(db.Boolean, default=False)
    requires_receipt_return = db.Column(db.Boolean, default=True)

    allowed_refund_reasons = db.Column(db.Text)  # JSON list

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_allowed_reasons(self):
        """Get list of allowed refund reasons"""
        import json
        if self.allowed_refund_reasons:
            try:
                return json.loads(self.allowed_refund_reasons)
            except:
                return []
        return []

    def __repr__(self):
        return f'<VoidRefundLimit {self.role}>'


class VoidRefundApproval(db.Model):
    """Tracks void/refund approval requests"""
    __tablename__ = 'void_refund_approvals'

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False, index=True)
    return_id = db.Column(db.Integer, index=True)  # If linked to returns table

    # Request type
    request_type = db.Column(db.String(32), nullable=False)  # void, refund, partial_refund

    # Requester
    requested_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False, index=True)

    # Amount
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    original_sale_total = db.Column(db.Numeric(12, 2), nullable=False)

    # Reason
    reason = db.Column(db.String(128), nullable=False)
    reason_details = db.Column(db.Text)

    # Status
    status = db.Column(db.String(32), default='pending')  # pending, approved, rejected, expired
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)

    # Approval code for manager
    approval_code = db.Column(db.String(32))
    expires_at = db.Column(db.DateTime)

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    sale = db.relationship('Sale', backref=db.backref('void_refund_approvals', lazy='dynamic'))
    requester = db.relationship('User', foreign_keys=[requested_by])
    approver = db.relationship('User', foreign_keys=[approved_by])
    location = db.relationship('Location', backref=db.backref('void_refund_approvals', lazy='dynamic'))

    def generate_approval_code(self):
        """Generate approval code"""
        import secrets
        self.approval_code = secrets.token_hex(4).upper()
        return self.approval_code

    def is_expired(self):
        """Check if request has expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False

    def __repr__(self):
        return f'<VoidRefundApproval {self.id} - {self.request_type}>'


class VoidRefundLog(db.Model):
    """Audit log for all voids and refunds"""
    __tablename__ = 'void_refund_logs'

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False, index=True)
    return_id = db.Column(db.Integer, index=True)

    # Type
    action_type = db.Column(db.String(32), nullable=False)  # void, refund, partial_refund

    # Who and where
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False, index=True)

    # Sale details
    sale_number = db.Column(db.String(64))
    sale_date = db.Column(db.DateTime)
    original_amount = db.Column(db.Numeric(12, 2), nullable=False)
    voided_refunded_amount = db.Column(db.Numeric(12, 2), nullable=False)

    # Timing
    hours_since_sale = db.Column(db.Float)  # How many hours after sale

    # Reason
    reason = db.Column(db.String(128), nullable=False)
    reason_details = db.Column(db.Text)

    # Approval
    required_approval = db.Column(db.Boolean, default=False)
    approval_id = db.Column(db.Integer, db.ForeignKey('void_refund_approvals.id'))
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Refund method
    refund_method = db.Column(db.String(32))  # cash, store_credit, original_payment

    # Customer
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    customer_name = db.Column(db.String(256))

    # Items voided/refunded
    items_json = db.Column(db.Text)  # JSON list of items

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationships
    sale = db.relationship('Sale', backref=db.backref('void_refund_logs', lazy='dynamic'))
    user = db.relationship('User', foreign_keys=[user_id])
    location = db.relationship('Location', backref=db.backref('void_refund_logs', lazy='dynamic'))
    approval = db.relationship('VoidRefundApproval')
    approver_user = db.relationship('User', foreign_keys=[approved_by])

    def __repr__(self):
        return f'<VoidRefundLog {self.id} - {self.action_type}>'


# ============================================================================
# PRICE CHANGE AUDIT MODELS
# ============================================================================

class PriceChangeLog(db.Model):
    """Audit log for all price changes"""
    __tablename__ = 'price_change_logs'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), index=True)  # For location-specific pricing

    # Who and when
    changed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Price type changed
    price_type = db.Column(db.String(32), nullable=False)  # selling_price, cost_price, base_cost, etc.

    # Old and new values
    old_value = db.Column(db.Numeric(12, 2), nullable=False)
    new_value = db.Column(db.Numeric(12, 2), nullable=False)
    change_amount = db.Column(db.Numeric(12, 2))  # new - old
    change_percentage = db.Column(db.Numeric(8, 2))  # ((new-old)/old)*100

    # Reason
    reason = db.Column(db.String(128))
    reason_details = db.Column(db.Text)

    # Approval (for large changes)
    required_approval = db.Column(db.Boolean, default=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    approval_status = db.Column(db.String(32), default='auto')  # auto, pending, approved, rejected

    # Context
    source = db.Column(db.String(64))  # manual, import, promotion, bulk_update
    batch_id = db.Column(db.String(64))  # For bulk updates

    notes = db.Column(db.Text)

    # Relationships
    product = db.relationship('Product', backref=db.backref('price_changes', lazy='dynamic'))
    location = db.relationship('Location', backref=db.backref('price_changes', lazy='dynamic'))
    user = db.relationship('User', foreign_keys=[changed_by], backref='price_changes_made')
    approver = db.relationship('User', foreign_keys=[approved_by])

    def calculate_change(self):
        """Calculate change amount and percentage"""
        self.change_amount = self.new_value - self.old_value
        if self.old_value and self.old_value != 0:
            self.change_percentage = ((self.new_value - self.old_value) / self.old_value) * 100
        else:
            self.change_percentage = 100 if self.new_value else 0

    def __repr__(self):
        return f'<PriceChangeLog {self.product_id} - {self.price_type}>'


class PriceChangeRule(db.Model):
    """Rules for price change approvals"""
    __tablename__ = 'price_change_rules'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)

    # Rule type
    rule_type = db.Column(db.String(32), nullable=False)  # percentage, amount, any

    # Thresholds
    min_change_percentage = db.Column(db.Numeric(8, 2))  # Trigger if change % >= this
    min_change_amount = db.Column(db.Numeric(12, 2))  # Trigger if change amount >= this

    # Actions
    requires_approval = db.Column(db.Boolean, default=True)
    notify_managers = db.Column(db.Boolean, default=True)
    notify_email = db.Column(db.String(256))  # Comma-separated emails

    # Scope
    applies_to_roles = db.Column(db.Text)  # JSON list of roles this applies to
    applies_to_price_types = db.Column(db.Text)  # JSON list: selling_price, cost_price, etc.

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_roles(self):
        import json
        if self.applies_to_roles:
            try:
                return json.loads(self.applies_to_roles)
            except:
                return []
        return []

    def get_price_types(self):
        import json
        if self.applies_to_price_types:
            try:
                return json.loads(self.applies_to_price_types)
            except:
                return []
        return []

    def __repr__(self):
        return f'<PriceChangeRule {self.name}>'


class DiscountLog(db.Model):
    """Audit log for all discounts applied in the system"""
    __tablename__ = 'discount_logs'

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), index=True)
    sale_item_id = db.Column(db.Integer, db.ForeignKey('sale_items.id'), index=True)

    # Who and where
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False, index=True)

    # Discount details
    discount_amount = db.Column(db.Numeric(10, 2), nullable=False)
    discount_percentage = db.Column(db.Numeric(5, 2))
    discount_type = db.Column(db.String(16), default='amount')  # amount, percentage, free_item

    # Context
    original_price = db.Column(db.Numeric(12, 2))  # Price before discount
    discounted_price = db.Column(db.Numeric(12, 2))  # Price after discount
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), index=True)
    product_name = db.Column(db.String(256))

    # Reason
    discount_reason = db.Column(db.String(128), nullable=False)
    reason_details = db.Column(db.Text)

    # Approval
    required_approval = db.Column(db.Boolean, default=False)
    approval_id = db.Column(db.Integer, db.ForeignKey('discount_approvals.id'))
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Promotion/Coupon link (if applicable)
    promotion_id = db.Column(db.Integer, db.ForeignKey('promotions.id'))
    coupon_code = db.Column(db.String(64))

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationships
    sale = db.relationship('Sale', backref=db.backref('discount_logs', lazy='dynamic'))
    user = db.relationship('User', foreign_keys=[user_id], backref='applied_discounts')
    location = db.relationship('Location', backref=db.backref('discount_logs', lazy='dynamic'))
    product = db.relationship('Product')
    approval = db.relationship('DiscountApproval')
    approver_user = db.relationship('User', foreign_keys=[approved_by])

    def __repr__(self):
        return f'<DiscountLog {self.id} - {self.discount_amount}>'


# ============================================================================
# BATCH & EXPIRY TRACKING
# ============================================================================

class ProductBatch(db.Model):
    """Track individual batches of products with different expiry dates"""
    __tablename__ = 'product_batches'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False, index=True)

    # Batch identification
    batch_number = db.Column(db.String(64), nullable=False, index=True)
    manufacture_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date, index=True)

    # Stock levels
    initial_quantity = db.Column(db.Numeric(12, 4), nullable=False)
    current_quantity = db.Column(db.Numeric(12, 4), nullable=False, default=0)
    reserved_quantity = db.Column(db.Numeric(12, 4), default=0)  # For pending orders

    # Cost tracking
    unit_cost = db.Column(db.Numeric(12, 4))  # Cost when batch was received
    total_cost = db.Column(db.Numeric(14, 2))

    # Source information
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    purchase_order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'))
    received_date = db.Column(db.Date, default=date.today)
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Status
    status = db.Column(db.String(20), default='active')  # active, depleted, expired, disposed
    disposed_date = db.Column(db.Date)
    disposed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    disposal_reason = db.Column(db.Text)

    # Notes
    notes = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    product = db.relationship('Product', backref=db.backref('batches', lazy='dynamic'))
    location = db.relationship('Location', backref=db.backref('product_batches', lazy='dynamic'))
    supplier = db.relationship('Supplier', backref=db.backref('product_batches', lazy='dynamic'))
    received_by_user = db.relationship('User', foreign_keys=[received_by])
    disposed_by_user = db.relationship('User', foreign_keys=[disposed_by])

    __table_args__ = (
        db.UniqueConstraint('product_id', 'location_id', 'batch_number', name='uix_batch_product_location'),
    )

    @property
    def available_quantity(self):
        """Get available quantity (current - reserved)"""
        return float(self.current_quantity or 0) - float(self.reserved_quantity or 0)

    @property
    def days_until_expiry(self):
        """Calculate days until expiry"""
        if not self.expiry_date:
            return None
        delta = self.expiry_date - date.today()
        return delta.days

    @property
    def is_expired(self):
        """Check if batch is expired"""
        if not self.expiry_date:
            return False
        return date.today() > self.expiry_date

    @property
    def is_near_expiry(self):
        """Check if batch is near expiry (within 30 days)"""
        days = self.days_until_expiry
        if days is None:
            return False
        return 0 < days <= 30

    @property
    def is_critical_expiry(self):
        """Check if batch is critical (within 7 days or expired)"""
        days = self.days_until_expiry
        if days is None:
            return False
        return days <= 7

    @property
    def expiry_status(self):
        """Get expiry status string"""
        if not self.expiry_date:
            return 'no_expiry'
        if self.is_expired:
            return 'expired'
        if self.is_critical_expiry:
            return 'critical'
        if self.is_near_expiry:
            return 'warning'
        return 'ok'

    @staticmethod
    def get_oldest_batch(product_id, location_id, required_qty=1):
        """Get oldest non-expired batch with available stock (FIFO)"""
        return ProductBatch.query.filter(
            ProductBatch.product_id == product_id,
            ProductBatch.location_id == location_id,
            ProductBatch.status == 'active',
            ProductBatch.current_quantity > ProductBatch.reserved_quantity,
            db.or_(
                ProductBatch.expiry_date.is_(None),
                ProductBatch.expiry_date >= date.today()
            )
        ).order_by(
            ProductBatch.expiry_date.asc().nullslast(),
            ProductBatch.received_date.asc()
        ).first()

    def __repr__(self):
        return f'<ProductBatch {self.batch_number} - {self.product.name if self.product else self.product_id}>'


class BatchMovement(db.Model):
    """Track all batch-level stock movements"""
    __tablename__ = 'batch_movements'

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('product_batches.id'), nullable=False, index=True)

    # Movement details
    movement_type = db.Column(db.String(32), nullable=False)  # sale, return, adjustment, transfer, disposal, receive
    quantity = db.Column(db.Numeric(12, 4), nullable=False)  # Positive for in, negative for out
    quantity_before = db.Column(db.Numeric(12, 4), nullable=False)
    quantity_after = db.Column(db.Numeric(12, 4), nullable=False)

    # Reference
    reference_type = db.Column(db.String(32))  # sale, transfer, adjustment, disposal
    reference_id = db.Column(db.Integer)  # sale_id, transfer_id, etc.

    # Who
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Details
    reason = db.Column(db.Text)
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationships
    batch = db.relationship('ProductBatch', backref=db.backref('movements', lazy='dynamic'))
    user = db.relationship('User', backref='batch_movements')

    def __repr__(self):
        return f'<BatchMovement {self.id} - {self.movement_type} {self.quantity}>'


class ExpiryAlert(db.Model):
    """Track expiry alerts and notifications"""
    __tablename__ = 'expiry_alerts'

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('product_batches.id'), nullable=False, index=True)

    alert_type = db.Column(db.String(32), nullable=False)  # warning (30d), critical (7d), expired
    alert_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)

    # Notification tracking
    notification_sent = db.Column(db.Boolean, default=False)
    notification_sent_at = db.Column(db.DateTime)
    notification_method = db.Column(db.String(32))  # email, sms, in_app

    # Action taken
    action_taken = db.Column(db.String(64))  # none, disposed, discounted, sold, returned_to_supplier
    action_date = db.Column(db.Date)
    action_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    action_notes = db.Column(db.Text)

    # Status
    is_resolved = db.Column(db.Boolean, default=False)
    resolved_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    batch = db.relationship('ProductBatch', backref=db.backref('alerts', lazy='dynamic'))
    action_by_user = db.relationship('User')

    def __repr__(self):
        return f'<ExpiryAlert {self.alert_type} - Batch {self.batch_id}>'
