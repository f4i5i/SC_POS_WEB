"""
Database Models
SQLAlchemy ORM models for the POS system
"""

from datetime import datetime
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
    # Roles: admin, manager, cashier, stock_manager, accountant
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sales = db.relationship('Sale', backref='cashier', lazy='dynamic')
    stock_movements = db.relationship('StockMovement', backref='user', lazy='dynamic')

    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)

    def has_permission(self, permission):
        """Check if user has specific permission based on role (legacy support)"""
        # First check new RBAC system
        if self.has_rbac_permission(permission):
            return True

        # Fallback to legacy role-based permissions
        permissions = {
            'admin': ['all'],
            'manager': ['pos', 'inventory', 'customers', 'suppliers', 'reports'],
            'cashier': ['pos'],
            'stock_manager': ['inventory'],
            'accountant': ['reports']
        }
        return 'all' in permissions.get(self.role, []) or permission in permissions.get(self.role, [])

    def has_rbac_permission(self, permission_name):
        """Check if user has permission through RBAC roles"""
        for role in self.roles:
            if role.has_permission(permission_name):
                return True
        return False

    def has_role(self, role_name):
        """Check if user has a specific role"""
        return any(role.name == role_name for role in self.roles)

    def get_all_permissions(self):
        """Get all permissions from all roles"""
        permissions = set()
        for role in self.roles:
            for perm in role.permissions:
                permissions.add(perm.name)
        return list(permissions)

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    products = db.relationship('Product', backref='supplier', lazy='dynamic')
    purchase_orders = db.relationship('PurchaseOrder', backref='supplier', lazy='dynamic')

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

    # Pricing
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

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sale_items = db.relationship('SaleItem', backref='product', lazy='dynamic')
    stock_movements = db.relationship('StockMovement', backref='product', lazy='dynamic')

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
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

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

    def calculate_totals(self):
        """Calculate sale totals from items"""
        self.subtotal = sum(item.subtotal for item in self.items)

        # Apply discount
        if self.discount_type == 'percentage':
            discount_amount = (self.subtotal * self.discount) / 100
        else:
            discount_amount = self.discount

        # Calculate tax
        taxable_amount = self.subtotal - discount_amount
        tax_amount = (taxable_amount * float(self.tax or 0)) / 100

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
        self.subtotal = (self.quantity * self.unit_price) - self.discount
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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Payment {self.id} - {self.amount}>'


class StockMovement(db.Model):
    """Track all stock movements (in/out/adjustment)"""
    __tablename__ = 'stock_movements'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    movement_type = db.Column(db.String(32), nullable=False)
    # Types: purchase, sale, adjustment, return, damage, transfer
    quantity = db.Column(db.Integer, nullable=False)  # Positive for in, negative for out
    reference = db.Column(db.String(128))  # Reference to sale, PO, etc.
    notes = db.Column(db.Text)

    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

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

    subtotal = db.Column(db.Numeric(10, 2), default=0.00)
    tax = db.Column(db.Numeric(10, 2), default=0.00)
    total = db.Column(db.Numeric(10, 2), default=0.00)

    status = db.Column(db.String(32), default='pending')
    # pending, ordered, partial, received, cancelled
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    items = db.relationship('PurchaseOrderItem', backref='purchase_order', lazy='dynamic',
                          cascade='all, delete-orphan')

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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    product = db.relationship('Product')

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

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(128), nullable=False)
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
    close_date = db.Column(db.Date, nullable=False, unique=True, index=True)
    closed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

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

    # Report
    report_generated = db.Column(db.Boolean, default=False)
    report_path = db.Column(db.String(512))
    report_sent = db.Column(db.Boolean, default=False)
    sent_to = db.Column(db.String(256))  # Email address(es)

    notes = db.Column(db.Text)
    closed_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    user = db.relationship('User')

    def __repr__(self):
        return f'<DayClose {self.close_date}>'
