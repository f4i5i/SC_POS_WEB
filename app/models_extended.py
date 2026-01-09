"""
Extended Models for Advanced Features
Feature Flags, SMS, WhatsApp, Expenses, Promotions, Gift Vouchers, etc.
"""

from datetime import datetime, date
from decimal import Decimal
from app.models import db


# ============================================================
# FEATURE FLAGS SYSTEM
# ============================================================

class FeatureFlag(db.Model):
    """Feature flags for enabling/disabling features dynamically"""
    __tablename__ = 'feature_flags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(64), default='general')  # notifications, sales, inventory, etc.

    is_enabled = db.Column(db.Boolean, default=False)
    requires_config = db.Column(db.Boolean, default=False)  # Needs API keys or settings
    is_configured = db.Column(db.Boolean, default=False)  # Has been configured

    # Configuration JSON (API keys, settings, etc.)
    config = db.Column(db.JSON, default={})

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    enabled_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    enabled_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<FeatureFlag {self.name}: {"ON" if self.is_enabled else "OFF"}>'

    @staticmethod
    def is_feature_enabled(feature_name):
        """Check if a feature is enabled"""
        flag = FeatureFlag.query.filter_by(name=feature_name).first()
        if flag:
            return flag.is_enabled and (not flag.requires_config or flag.is_configured)
        return False

    @staticmethod
    def get_config(feature_name, key=None):
        """Get configuration for a feature"""
        flag = FeatureFlag.query.filter_by(name=feature_name).first()
        if flag and flag.config:
            if key:
                return flag.config.get(key)
            return flag.config
        return None


# ============================================================
# SMS NOTIFICATIONS
# ============================================================

class SMSTemplate(db.Model):
    """SMS message templates"""
    __tablename__ = 'sms_templates'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    template_type = db.Column(db.String(32), nullable=False)
    # Types: birthday, payment_reminder, promotion, order_confirmation, welcome, custom

    message = db.Column(db.Text, nullable=False)  # Use {customer_name}, {amount}, etc. for placeholders
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<SMSTemplate {self.name}>'


class SMSLog(db.Model):
    """Log of sent SMS messages"""
    __tablename__ = 'sms_logs'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    phone_number = db.Column(db.String(20), nullable=False)

    message = db.Column(db.Text, nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('sms_templates.id'))

    status = db.Column(db.String(32), default='pending')  # pending, sent, delivered, failed
    provider_response = db.Column(db.JSON)  # Response from SMS provider
    error_message = db.Column(db.Text)

    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered_at = db.Column(db.DateTime)

    sent_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    customer = db.relationship('Customer')
    template = db.relationship('SMSTemplate')

    def __repr__(self):
        return f'<SMSLog {self.phone_number} - {self.status}>'


# ============================================================
# WHATSAPP INTEGRATION
# ============================================================

class WhatsAppTemplate(db.Model):
    """WhatsApp message templates"""
    __tablename__ = 'whatsapp_templates'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    template_type = db.Column(db.String(32), nullable=False)
    # Types: birthday, payment_reminder, promotion, order_confirmation, welcome, custom

    message = db.Column(db.Text, nullable=False)
    has_media = db.Column(db.Boolean, default=False)
    media_url = db.Column(db.String(512))  # Image/video URL

    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<WhatsAppTemplate {self.name}>'


class WhatsAppLog(db.Model):
    """Log of sent WhatsApp messages"""
    __tablename__ = 'whatsapp_logs'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    phone_number = db.Column(db.String(20), nullable=False)

    message = db.Column(db.Text, nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('whatsapp_templates.id'))

    status = db.Column(db.String(32), default='pending')  # pending, sent, delivered, read, failed
    message_id = db.Column(db.String(128))  # WhatsApp message ID
    provider_response = db.Column(db.JSON)
    error_message = db.Column(db.Text)

    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered_at = db.Column(db.DateTime)
    read_at = db.Column(db.DateTime)

    sent_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    customer = db.relationship('Customer')
    template = db.relationship('WhatsAppTemplate')

    def __repr__(self):
        return f'<WhatsAppLog {self.phone_number} - {self.status}>'


# ============================================================
# EXPENSE TRACKING
# ============================================================

class ExpenseCategory(db.Model):
    """Categories for expenses"""
    __tablename__ = 'expense_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(32), default='money-bill')
    color = db.Column(db.String(7), default='#6B7280')

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    expenses = db.relationship('Expense', backref='category', lazy='dynamic')

    def __repr__(self):
        return f'<ExpenseCategory {self.name}>'


class Expense(db.Model):
    """Shop expenses tracking"""
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True)
    expense_number = db.Column(db.String(64), unique=True, nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_categories.id'), nullable=False)

    description = db.Column(db.String(256), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)

    expense_date = db.Column(db.Date, default=date.today, index=True)
    payment_method = db.Column(db.String(32), default='cash')  # cash, bank, card
    reference = db.Column(db.String(128))  # Bill number, invoice, etc.

    vendor_name = db.Column(db.String(128))
    receipt_image = db.Column(db.String(512))  # Path to receipt image

    is_recurring = db.Column(db.Boolean, default=False)
    recurring_frequency = db.Column(db.String(32))  # daily, weekly, monthly, yearly

    notes = db.Column(db.Text)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    status = db.Column(db.String(32), default='pending')  # pending, approved, rejected

    # Multi-kiosk support
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by])
    approver = db.relationship('User', foreign_keys=[approved_by])
    location = db.relationship('Location', foreign_keys=[location_id])

    def __repr__(self):
        return f'<Expense {self.expense_number} - Rs.{self.amount}>'


# ============================================================
# PRODUCT VARIANTS (Sizes)
# ============================================================

class ProductVariant(db.Model):
    """Product variants (different sizes of same product)"""
    __tablename__ = 'product_variants'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)

    sku = db.Column(db.String(64), unique=True, nullable=False, index=True)
    barcode = db.Column(db.String(64), unique=True, index=True)

    size = db.Column(db.String(32), nullable=False)  # 50ml, 100ml, 200ml
    size_value = db.Column(db.Numeric(10, 2))  # Numeric value for sorting
    size_unit = db.Column(db.String(16), default='ml')  # ml, oz, g

    cost_price = db.Column(db.Numeric(10, 2), nullable=False)
    selling_price = db.Column(db.Numeric(10, 2), nullable=False)

    quantity = db.Column(db.Integer, default=0)
    reorder_level = db.Column(db.Integer, default=5)

    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    product = db.relationship('Product', backref=db.backref('variants', lazy='dynamic'))

    @property
    def profit_margin(self):
        if self.cost_price and self.cost_price > 0:
            return ((self.selling_price - self.cost_price) / self.cost_price) * 100
        return 0

    @property
    def is_low_stock(self):
        return self.quantity <= self.reorder_level

    def __repr__(self):
        return f'<ProductVariant {self.sku} - {self.size}>'


# ============================================================
# PROMOTIONS & OFFERS
# ============================================================

class Promotion(db.Model):
    """Promotional offers and discounts"""
    __tablename__ = 'promotions'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)

    promotion_type = db.Column(db.String(32), nullable=False)
    # Types: percentage, fixed_amount, buy_x_get_y, bundle, free_shipping

    discount_value = db.Column(db.Numeric(10, 2))  # Percentage or fixed amount
    buy_quantity = db.Column(db.Integer)  # For buy X get Y
    get_quantity = db.Column(db.Integer)  # For buy X get Y

    min_purchase = db.Column(db.Numeric(10, 2), default=0)  # Minimum purchase amount
    max_discount = db.Column(db.Numeric(10, 2))  # Maximum discount cap

    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)

    usage_limit = db.Column(db.Integer)  # Total times this can be used
    usage_per_customer = db.Column(db.Integer, default=1)  # Times per customer
    times_used = db.Column(db.Integer, default=0)

    # Applicable to
    applies_to = db.Column(db.String(32), default='all')  # all, category, product, customer_type
    applicable_ids = db.Column(db.JSON)  # List of category/product/customer IDs

    is_active = db.Column(db.Boolean, default=True)
    is_stackable = db.Column(db.Boolean, default=False)  # Can combine with other promotions

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Promotion {self.code} - {self.name}>'

    @property
    def is_valid(self):
        now = datetime.utcnow()
        return (
            self.is_active and
            self.start_date <= now <= self.end_date and
            (self.usage_limit is None or self.times_used < self.usage_limit)
        )


class PromotionUsage(db.Model):
    """Track promotion usage by customers"""
    __tablename__ = 'promotion_usages'

    id = db.Column(db.Integer, primary_key=True)
    promotion_id = db.Column(db.Integer, db.ForeignKey('promotions.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'))

    discount_amount = db.Column(db.Numeric(10, 2), nullable=False)
    used_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    promotion = db.relationship('Promotion', backref=db.backref('usages', lazy='dynamic'))
    customer = db.relationship('Customer')
    sale = db.relationship('Sale')

    def __repr__(self):
        return f'<PromotionUsage {self.promotion_id} - {self.discount_amount}>'


# ============================================================
# GIFT VOUCHERS
# ============================================================

class GiftVoucher(db.Model):
    """Gift vouchers/cards"""
    __tablename__ = 'gift_vouchers'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)

    initial_value = db.Column(db.Numeric(10, 2), nullable=False)
    current_balance = db.Column(db.Numeric(10, 2), nullable=False)

    purchased_by = db.Column(db.Integer, db.ForeignKey('customers.id'))
    recipient_name = db.Column(db.String(128))
    recipient_email = db.Column(db.String(128))
    recipient_phone = db.Column(db.String(20))
    personal_message = db.Column(db.Text)

    valid_from = db.Column(db.DateTime, default=datetime.utcnow)
    valid_until = db.Column(db.DateTime, nullable=False)

    status = db.Column(db.String(32), default='active')  # active, used, expired, cancelled

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    purchaser = db.relationship('Customer')
    creator = db.relationship('User')

    @property
    def is_valid(self):
        now = datetime.utcnow()
        return (
            self.status == 'active' and
            self.valid_from <= now <= self.valid_until and
            self.current_balance > 0
        )

    def __repr__(self):
        return f'<GiftVoucher {self.code} - Rs.{self.current_balance}>'


class GiftVoucherTransaction(db.Model):
    """Gift voucher usage transactions"""
    __tablename__ = 'gift_voucher_transactions'

    id = db.Column(db.Integer, primary_key=True)
    voucher_id = db.Column(db.Integer, db.ForeignKey('gift_vouchers.id'), nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'))

    transaction_type = db.Column(db.String(32), nullable=False)  # purchase, redemption, refund, adjustment
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    balance_after = db.Column(db.Numeric(10, 2), nullable=False)

    notes = db.Column(db.Text)
    processed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    processed_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    voucher = db.relationship('GiftVoucher', backref=db.backref('transactions', lazy='dynamic'))
    sale = db.relationship('Sale')

    def __repr__(self):
        return f'<GiftVoucherTransaction {self.transaction_type} - Rs.{self.amount}>'


# ============================================================
# QUOTATIONS / ESTIMATES
# ============================================================

class Quotation(db.Model):
    """Sales quotations/estimates"""
    __tablename__ = 'quotations'

    id = db.Column(db.Integer, primary_key=True)
    quotation_number = db.Column(db.String(64), unique=True, nullable=False, index=True)

    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    customer_name = db.Column(db.String(128))  # For walk-in customers
    customer_phone = db.Column(db.String(20))
    customer_email = db.Column(db.String(128))

    quotation_date = db.Column(db.DateTime, default=datetime.utcnow)
    valid_until = db.Column(db.DateTime, nullable=False)

    subtotal = db.Column(db.Numeric(12, 2), default=0.00)
    discount = db.Column(db.Numeric(10, 2), default=0.00)
    discount_type = db.Column(db.String(16), default='amount')  # amount, percentage
    tax = db.Column(db.Numeric(10, 2), default=0.00)
    total = db.Column(db.Numeric(12, 2), default=0.00)

    status = db.Column(db.String(32), default='draft')
    # draft, sent, accepted, rejected, expired, converted

    converted_to_sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'))
    converted_at = db.Column(db.DateTime)

    notes = db.Column(db.Text)
    terms_conditions = db.Column(db.Text)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customer = db.relationship('Customer')
    creator = db.relationship('User')
    converted_sale = db.relationship('Sale')
    items = db.relationship('QuotationItem', backref='quotation', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Quotation {self.quotation_number}>'


class QuotationItem(db.Model):
    """Items in a quotation"""
    __tablename__ = 'quotation_items'

    id = db.Column(db.Integer, primary_key=True)
    quotation_id = db.Column(db.Integer, db.ForeignKey('quotations.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'))

    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    discount = db.Column(db.Numeric(10, 2), default=0.00)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)

    notes = db.Column(db.Text)

    # Relationships
    product = db.relationship('Product')
    variant = db.relationship('ProductVariant')

    def __repr__(self):
        return f'<QuotationItem {self.id}>'


# ============================================================
# RETURNS MANAGEMENT
# ============================================================

class Return(db.Model):
    """Product returns"""
    __tablename__ = 'returns'

    id = db.Column(db.Integer, primary_key=True)
    return_number = db.Column(db.String(64), unique=True, nullable=False, index=True)

    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))

    return_type = db.Column(db.String(32), nullable=False)  # refund, exchange, credit
    return_reason = db.Column(db.String(64), nullable=False)
    # damaged, wrong_item, not_satisfied, defective, other

    total_amount = db.Column(db.Numeric(12, 2), default=0.00)
    refund_amount = db.Column(db.Numeric(12, 2), default=0.00)
    credit_issued = db.Column(db.Numeric(12, 2), default=0.00)
    exchange_sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'))

    status = db.Column(db.String(32), default='pending')
    # pending, approved, completed, rejected

    notes = db.Column(db.Text)

    processed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Multi-kiosk support
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))

    return_date = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    # Relationships
    sale = db.relationship('Sale', foreign_keys=[sale_id])
    customer = db.relationship('Customer')
    exchange_sale = db.relationship('Sale', foreign_keys=[exchange_sale_id])
    processor = db.relationship('User', foreign_keys=[processed_by])
    approver = db.relationship('User', foreign_keys=[approved_by])
    location = db.relationship('Location', foreign_keys=[location_id])
    items = db.relationship('ReturnItem', backref='return_order', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Return {self.return_number}>'


class ReturnItem(db.Model):
    """Items in a return"""
    __tablename__ = 'return_items'

    id = db.Column(db.Integer, primary_key=True)
    return_id = db.Column(db.Integer, db.ForeignKey('returns.id'), nullable=False)
    sale_item_id = db.Column(db.Integer, db.ForeignKey('sale_items.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)

    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)

    condition = db.Column(db.String(32), default='good')  # good, damaged, opened
    restock = db.Column(db.Boolean, default=True)  # Should item be restocked?

    notes = db.Column(db.Text)

    # Relationships
    sale_item = db.relationship('SaleItem')
    product = db.relationship('Product')

    def __repr__(self):
        return f'<ReturnItem {self.id}>'


# ============================================================
# SUPPLIER PAYMENTS
# ============================================================

class SupplierPayment(db.Model):
    """Track payments to suppliers"""
    __tablename__ = 'supplier_payments'

    id = db.Column(db.Integer, primary_key=True)
    payment_number = db.Column(db.String(64), unique=True, nullable=False, index=True)

    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'))

    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_method = db.Column(db.String(32), nullable=False)  # cash, bank_transfer, cheque

    payment_date = db.Column(db.Date, nullable=False, index=True)
    reference_number = db.Column(db.String(128))  # Cheque number, transaction ID

    status = db.Column(db.String(32), default='completed')  # pending, completed, bounced, cancelled

    notes = db.Column(db.Text)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    supplier = db.relationship('Supplier')
    purchase_order = db.relationship('PurchaseOrder')
    creator = db.relationship('User')

    def __repr__(self):
        return f'<SupplierPayment {self.payment_number} - Rs.{self.amount}>'


class SupplierLedger(db.Model):
    """Supplier account ledger for tracking dues"""
    __tablename__ = 'supplier_ledgers'

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)

    transaction_type = db.Column(db.String(32), nullable=False)  # purchase, payment, adjustment
    reference_id = db.Column(db.Integer)  # PO ID or Payment ID
    reference_number = db.Column(db.String(64))

    debit = db.Column(db.Numeric(12, 2), default=0.00)  # Amount owed (purchases)
    credit = db.Column(db.Numeric(12, 2), default=0.00)  # Amount paid
    balance = db.Column(db.Numeric(12, 2), nullable=False)  # Running balance

    description = db.Column(db.String(256))
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationships
    supplier = db.relationship('Supplier', backref=db.backref('ledger_entries', lazy='dynamic'))

    def __repr__(self):
        return f'<SupplierLedger {self.supplier_id} - Balance: Rs.{self.balance}>'


# ============================================================
# CUSTOMER CREDIT & DUE PAYMENTS
# ============================================================

class CustomerCredit(db.Model):
    """Customer credit/store credit"""
    __tablename__ = 'customer_credits'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)

    credit_type = db.Column(db.String(32), nullable=False)  # return_credit, gift, adjustment, payment
    reference_id = db.Column(db.Integer)  # Return ID, etc.

    amount = db.Column(db.Numeric(10, 2), nullable=False)
    balance_after = db.Column(db.Numeric(10, 2), nullable=False)

    description = db.Column(db.String(256))
    expires_at = db.Column(db.DateTime)  # Optional expiry

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    customer = db.relationship('Customer', backref=db.backref('credit_history', lazy='dynamic'))

    def __repr__(self):
        return f'<CustomerCredit {self.customer_id} - Rs.{self.amount}>'


class DuePayment(db.Model):
    """Track customer due payments"""
    __tablename__ = 'due_payments'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)

    total_amount = db.Column(db.Numeric(12, 2), nullable=False)
    paid_amount = db.Column(db.Numeric(12, 2), default=0.00)
    due_amount = db.Column(db.Numeric(12, 2), nullable=False)

    due_date = db.Column(db.Date, nullable=False, index=True)

    status = db.Column(db.String(32), default='pending')  # pending, partial, paid, overdue

    reminder_sent = db.Column(db.Boolean, default=False)
    reminder_count = db.Column(db.Integer, default=0)
    last_reminder_at = db.Column(db.DateTime)

    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customer = db.relationship('Customer', backref=db.backref('due_payments', lazy='dynamic'))
    sale = db.relationship('Sale')

    @property
    def is_overdue(self):
        return self.status != 'paid' and date.today() > self.due_date

    @property
    def days_overdue(self):
        if self.is_overdue:
            return (date.today() - self.due_date).days
        return 0

    def __repr__(self):
        return f'<DuePayment {self.customer_id} - Rs.{self.due_amount}>'


class DuePaymentInstallment(db.Model):
    """Installment payments for dues"""
    __tablename__ = 'due_payment_installments'

    id = db.Column(db.Integer, primary_key=True)
    due_payment_id = db.Column(db.Integer, db.ForeignKey('due_payments.id'), nullable=False)

    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_method = db.Column(db.String(32), nullable=False)
    reference = db.Column(db.String(128))

    paid_at = db.Column(db.DateTime, default=datetime.utcnow)
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    notes = db.Column(db.Text)

    # Relationships
    due_payment = db.relationship('DuePayment', backref=db.backref('installments', lazy='dynamic'))
    receiver = db.relationship('User')

    def __repr__(self):
        return f'<DuePaymentInstallment Rs.{self.amount}>'


# ============================================================
# TAX MANAGEMENT
# ============================================================

class TaxRate(db.Model):
    """Tax rates configuration"""
    __tablename__ = 'tax_rates'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)  # GST, VAT, Sales Tax
    rate = db.Column(db.Numeric(5, 2), nullable=False)  # Percentage

    applies_to = db.Column(db.String(32), default='all')  # all, category, product
    applicable_ids = db.Column(db.JSON)  # Category/Product IDs

    is_default = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    effective_from = db.Column(db.Date, nullable=False)
    effective_until = db.Column(db.Date)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<TaxRate {self.name} - {self.rate}%>'


class TaxReport(db.Model):
    """Generated tax reports"""
    __tablename__ = 'tax_reports'

    id = db.Column(db.Integer, primary_key=True)
    report_period = db.Column(db.String(32), nullable=False)  # monthly, quarterly, yearly
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)

    total_sales = db.Column(db.Numeric(14, 2), default=0.00)
    taxable_sales = db.Column(db.Numeric(14, 2), default=0.00)
    total_tax_collected = db.Column(db.Numeric(12, 2), default=0.00)

    total_purchases = db.Column(db.Numeric(14, 2), default=0.00)
    input_tax = db.Column(db.Numeric(12, 2), default=0.00)

    net_tax_liability = db.Column(db.Numeric(12, 2), default=0.00)

    status = db.Column(db.String(32), default='draft')  # draft, finalized, submitted

    report_data = db.Column(db.JSON)  # Detailed breakdown
    file_path = db.Column(db.String(512))

    generated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime)

    # Relationships
    generator = db.relationship('User')

    def __repr__(self):
        return f'<TaxReport {self.period_start} to {self.period_end}>'


# ============================================================
# NOTIFICATION SETTINGS
# ============================================================

class NotificationSetting(db.Model):
    """User notification preferences"""
    __tablename__ = 'notification_settings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)

    # Email notifications
    email_daily_report = db.Column(db.Boolean, default=True)
    email_low_stock = db.Column(db.Boolean, default=True)
    email_large_sales = db.Column(db.Boolean, default=False)
    email_threshold_amount = db.Column(db.Numeric(10, 2), default=10000)

    # SMS notifications (for business owner)
    sms_daily_summary = db.Column(db.Boolean, default=False)
    sms_large_sales = db.Column(db.Boolean, default=False)

    # In-app notifications
    notify_low_stock = db.Column(db.Boolean, default=True)
    notify_due_payments = db.Column(db.Boolean, default=True)
    notify_birthdays = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref=db.backref('notification_settings', uselist=False))

    def __repr__(self):
        return f'<NotificationSetting User:{self.user_id}>'


# ============================================================
# SCHEDULED TASKS / AUTOMATION
# ============================================================

class ScheduledTask(db.Model):
    """Scheduled automation tasks"""
    __tablename__ = 'scheduled_tasks'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    task_type = db.Column(db.String(64), nullable=False)
    # birthday_sms, payment_reminder, report_generation, backup, etc.

    schedule = db.Column(db.String(64), nullable=False)  # Cron expression or interval
    is_active = db.Column(db.Boolean, default=True)

    last_run = db.Column(db.DateTime)
    next_run = db.Column(db.DateTime)
    last_status = db.Column(db.String(32))  # success, failed
    last_error = db.Column(db.Text)

    config = db.Column(db.JSON, default={})

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<ScheduledTask {self.name}>'


# ============================================================
# GAMIFIED LOYALTY SYSTEM
# ============================================================

class LoyaltyBadge(db.Model):
    """Achievement badges for loyalty program"""
    __tablename__ = 'loyalty_badges'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)

    badge_type = db.Column(db.String(32), nullable=False, default='milestone')
    # Types: purchase, milestone, engagement, special

    icon = db.Column(db.String(64), default='fas fa-award')  # Font Awesome icon class
    color = db.Column(db.String(7), default='#FFD700')  # Badge color (hex)

    # Criteria to earn
    criteria_type = db.Column(db.String(32))
    # first_purchase, spend_amount, purchase_count, loyalty_tier, referral_count
    criteria_value = db.Column(db.Integer)  # e.g., 10000 for "spend Rs.10,000"

    # Rewards
    points_reward = db.Column(db.Integer, default=0)  # Bonus points when earned
    discount_reward = db.Column(db.Numeric(5, 2))  # Percentage discount

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<LoyaltyBadge {self.code}: {self.name}>'


class CustomerBadge(db.Model):
    """Badges earned by customers"""
    __tablename__ = 'customer_badges'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)
    badge_id = db.Column(db.Integer, db.ForeignKey('loyalty_badges.id'), nullable=False)

    earned_at = db.Column(db.DateTime, default=datetime.utcnow)
    notified = db.Column(db.Boolean, default=False)

    # Unique constraint - customer can only earn each badge once
    __table_args__ = (
        db.UniqueConstraint('customer_id', 'badge_id', name='uix_customer_badge'),
    )

    # Relationships
    customer = db.relationship('Customer', backref=db.backref('badges', lazy='dynamic'))
    badge = db.relationship('LoyaltyBadge', backref=db.backref('holders', lazy='dynamic'))

    def __repr__(self):
        return f'<CustomerBadge {self.customer_id}:{self.badge_id}>'


class LoyaltyChallenge(db.Model):
    """Monthly/weekly challenges for customers"""
    __tablename__ = 'loyalty_challenges'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)

    challenge_type = db.Column(db.String(32), nullable=False)
    # Types: spending_goal, visit_count, referral_count, product_category

    # Goal
    target_value = db.Column(db.Integer, nullable=False)  # e.g., Rs. 5000 spending

    # Duration
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

    # Reward
    reward_type = db.Column(db.String(32), default='points')  # points, discount, badge
    reward_value = db.Column(db.Integer)  # Points amount or discount percentage
    badge_id = db.Column(db.Integer, db.ForeignKey('loyalty_badges.id'))  # If reward is a badge

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    badge = db.relationship('LoyaltyBadge')

    def __repr__(self):
        return f'<LoyaltyChallenge {self.name}>'


class CustomerChallengeProgress(db.Model):
    """Track customer progress on challenges"""
    __tablename__ = 'customer_challenge_progress'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('loyalty_challenges.id'), nullable=False)

    current_value = db.Column(db.Integer, default=0)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime)
    reward_claimed = db.Column(db.Boolean, default=False)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('customer_id', 'challenge_id', name='uix_customer_challenge'),
    )

    # Relationships
    customer = db.relationship('Customer', backref=db.backref('challenge_progress', lazy='dynamic'))
    challenge = db.relationship('LoyaltyChallenge', backref=db.backref('participants', lazy='dynamic'))

    @property
    def progress_percentage(self):
        if self.challenge and self.challenge.target_value > 0:
            return min(100, (self.current_value / self.challenge.target_value) * 100)
        return 0

    def __repr__(self):
        return f'<CustomerChallengeProgress {self.customer_id}:{self.challenge_id}>'


class Referral(db.Model):
    """Customer referral tracking"""
    __tablename__ = 'referrals'

    id = db.Column(db.Integer, primary_key=True)
    referrer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)
    referred_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)

    referral_code = db.Column(db.String(32), index=True)

    status = db.Column(db.String(32), default='pending')
    # pending, qualified (made purchase), rewarded

    referrer_reward = db.Column(db.Integer, default=0)  # Points awarded to referrer
    referred_reward = db.Column(db.Integer, default=0)  # Points awarded to referred

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    qualified_at = db.Column(db.DateTime)

    # Relationships
    referrer = db.relationship('Customer', foreign_keys=[referrer_id],
                              backref=db.backref('referrals_made', lazy='dynamic'))
    referred = db.relationship('Customer', foreign_keys=[referred_id],
                              backref=db.backref('referred_by', uselist=False))

    def __repr__(self):
        return f'<Referral {self.referrer_id}->{self.referred_id}>'


# ============================================================
# SMS MARKETING AUTOMATION
# ============================================================

class SMSCampaign(db.Model):
    """SMS marketing campaigns"""
    __tablename__ = 'sms_campaigns'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    campaign_type = db.Column(db.String(32), nullable=False, default='one_time')
    # Types: one_time, scheduled, recurring, automated_trigger

    template_id = db.Column(db.Integer, db.ForeignKey('sms_templates.id'))

    # Targeting
    target_audience = db.Column(db.String(32), default='all')
    # all, loyalty_tier, inactive, birthday_month, custom
    target_criteria = db.Column(db.JSON)  # Filter criteria

    # Scheduling
    scheduled_at = db.Column(db.DateTime)
    recurring_schedule = db.Column(db.String(64))  # Cron expression

    # Status
    status = db.Column(db.String(32), default='draft')
    # draft, scheduled, running, completed, paused, cancelled

    # Stats
    total_recipients = db.Column(db.Integer, default=0)
    sent_count = db.Column(db.Integer, default=0)
    delivered_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)

    # Channel
    channel = db.Column(db.String(32), default='sms')  # sms, whatsapp, both

    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    # Relationships
    template = db.relationship('SMSTemplate')

    def __repr__(self):
        return f'<SMSCampaign {self.name}>'


class AutomatedTrigger(db.Model):
    """Automated SMS/WhatsApp triggers"""
    __tablename__ = 'automated_triggers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    trigger_type = db.Column(db.String(64), nullable=False)
    # Types: no_purchase_days, birthday_reminder, loyalty_milestone,
    #        payment_due, points_expiry, post_purchase

    # Trigger conditions
    trigger_days = db.Column(db.Integer)  # e.g., 30 for "no purchase in 30 days"
    trigger_conditions = db.Column(db.JSON)

    # Message
    template_id = db.Column(db.Integer, db.ForeignKey('sms_templates.id'))
    channel = db.Column(db.String(32), default='sms')  # sms, whatsapp, both

    # Status
    is_active = db.Column(db.Boolean, default=True)

    # Stats
    times_triggered = db.Column(db.Integer, default=0)
    last_triggered_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    template = db.relationship('SMSTemplate')

    def __repr__(self):
        return f'<AutomatedTrigger {self.name}>'


class TriggerLog(db.Model):
    """Log of triggered automations"""
    __tablename__ = 'trigger_logs'

    id = db.Column(db.Integer, primary_key=True)
    trigger_id = db.Column(db.Integer, db.ForeignKey('automated_triggers.id'), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)

    triggered_at = db.Column(db.DateTime, default=datetime.utcnow)
    message_sent = db.Column(db.Boolean, default=False)
    channel_used = db.Column(db.String(32))
    error_message = db.Column(db.Text)

    # Relationships
    trigger = db.relationship('AutomatedTrigger', backref=db.backref('logs', lazy='dynamic'))
    customer = db.relationship('Customer')

    def __repr__(self):
        return f'<TriggerLog {self.trigger_id}:{self.customer_id}>'


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def seed_default_badges():
    """Seed default loyalty badges"""
    default_badges = [
        {
            'code': 'first_purchase',
            'name': 'First Timer',
            'description': 'Made your first purchase',
            'badge_type': 'milestone',
            'icon': 'fas fa-seedling',
            'color': '#4CAF50',
            'criteria_type': 'first_purchase',
            'criteria_value': 1,
            'points_reward': 50
        },
        {
            'code': 'big_spender_5k',
            'name': 'Big Spender',
            'description': 'Total purchases exceed Rs. 5,000',
            'badge_type': 'milestone',
            'icon': 'fas fa-gem',
            'color': '#9C27B0',
            'criteria_type': 'spend_amount',
            'criteria_value': 5000,
            'points_reward': 100
        },
        {
            'code': 'loyal_10',
            'name': 'Loyal Customer',
            'description': 'Made 10 purchases',
            'badge_type': 'milestone',
            'icon': 'fas fa-heart',
            'color': '#E91E63',
            'criteria_type': 'purchase_count',
            'criteria_value': 10,
            'points_reward': 150
        },
        {
            'code': 'silver_member',
            'name': 'Silver Member',
            'description': 'Reached Silver loyalty tier',
            'badge_type': 'milestone',
            'icon': 'fas fa-medal',
            'color': '#9E9E9E',
            'criteria_type': 'loyalty_tier',
            'criteria_value': 2
        },
        {
            'code': 'gold_member',
            'name': 'Gold Member',
            'description': 'Reached Gold loyalty tier',
            'badge_type': 'milestone',
            'icon': 'fas fa-crown',
            'color': '#FFC107',
            'criteria_type': 'loyalty_tier',
            'criteria_value': 3
        },
        {
            'code': 'platinum_member',
            'name': 'Platinum Elite',
            'description': 'Reached Platinum loyalty tier',
            'badge_type': 'milestone',
            'icon': 'fas fa-star',
            'color': '#607D8B',
            'criteria_type': 'loyalty_tier',
            'criteria_value': 4
        },
        {
            'code': 'referrer_3',
            'name': 'Brand Ambassador',
            'description': 'Referred 3 friends',
            'badge_type': 'engagement',
            'icon': 'fas fa-users',
            'color': '#2196F3',
            'criteria_type': 'referral_count',
            'criteria_value': 3,
            'points_reward': 200
        },
        {
            'code': 'big_spender_25k',
            'name': 'VIP Shopper',
            'description': 'Total purchases exceed Rs. 25,000',
            'badge_type': 'milestone',
            'icon': 'fas fa-trophy',
            'color': '#FF5722',
            'criteria_type': 'spend_amount',
            'criteria_value': 25000,
            'points_reward': 500
        },
    ]

    count = 0
    for badge_data in default_badges:
        existing = LoyaltyBadge.query.filter_by(code=badge_data['code']).first()
        if not existing:
            badge = LoyaltyBadge(**badge_data)
            db.session.add(badge)
            count += 1

    db.session.commit()
    return count


def init_feature_flags():
    """Initialize default feature flags"""
    default_flags = [
        # Notifications
        {
            'name': 'sms_notifications',
            'display_name': 'SMS Notifications',
            'description': 'Send SMS notifications for birthdays, payment reminders, and promotions',
            'category': 'notifications',
            'requires_config': True,
            'config': {'provider': '', 'api_key': '', 'sender_id': ''}
        },
        {
            'name': 'whatsapp_notifications',
            'display_name': 'WhatsApp Notifications',
            'description': 'Send WhatsApp messages for customer communication',
            'category': 'notifications',
            'requires_config': True,
            'config': {'provider': '', 'api_key': '', 'phone_number_id': ''}
        },
        {
            'name': 'email_notifications',
            'display_name': 'Email Notifications',
            'description': 'Send email notifications and reports',
            'category': 'notifications',
            'requires_config': True,
            'config': {'smtp_server': '', 'smtp_port': 587, 'username': '', 'password': ''}
        },

        # Sales Features
        {
            'name': 'promotions',
            'display_name': 'Promotions & Offers',
            'description': 'Create and manage promotional discounts and offers',
            'category': 'sales',
            'requires_config': False
        },
        {
            'name': 'gift_vouchers',
            'display_name': 'Gift Vouchers',
            'description': 'Issue and redeem gift vouchers/cards',
            'category': 'sales',
            'requires_config': False
        },
        {
            'name': 'quotations',
            'display_name': 'Quotations/Estimates',
            'description': 'Create quotations and convert to sales',
            'category': 'sales',
            'requires_config': False
        },
        {
            'name': 'returns_management',
            'display_name': 'Returns Management',
            'description': 'Process returns, refunds, and exchanges',
            'category': 'sales',
            'requires_config': False
        },
        {
            'name': 'due_payments',
            'display_name': 'Due Payment Tracking',
            'description': 'Track credit sales and due payments',
            'category': 'sales',
            'requires_config': False
        },

        # Inventory Features
        {
            'name': 'product_variants',
            'display_name': 'Product Variants',
            'description': 'Manage product variants (sizes: 50ml, 100ml, etc.)',
            'category': 'inventory',
            'requires_config': False
        },
        {
            'name': 'barcode_printing',
            'display_name': 'Barcode Printing',
            'description': 'Generate and print product barcodes',
            'category': 'inventory',
            'requires_config': False
        },

        # Finance Features
        {
            'name': 'expense_tracking',
            'display_name': 'Expense Tracking',
            'description': 'Track shop expenses with categories',
            'category': 'finance',
            'requires_config': False
        },
        {
            'name': 'supplier_payments',
            'display_name': 'Supplier Payments',
            'description': 'Track payments to suppliers and dues',
            'category': 'finance',
            'requires_config': False
        },
        {
            'name': 'tax_reports',
            'display_name': 'Tax Reports',
            'description': 'Generate GST/Sales tax reports',
            'category': 'finance',
            'requires_config': False
        },

        # Customer Features
        {
            'name': 'customer_credit',
            'display_name': 'Customer Store Credit',
            'description': 'Manage customer store credits',
            'category': 'customers',
            'requires_config': False
        },
        {
            'name': 'birthday_automation',
            'display_name': 'Birthday Automation',
            'description': 'Automatic birthday wishes and gift notifications',
            'category': 'customers',
            'requires_config': False
        },
    ]

    for flag_data in default_flags:
        existing = FeatureFlag.query.filter_by(name=flag_data['name']).first()
        if not existing:
            flag = FeatureFlag(**flag_data)
            db.session.add(flag)

    db.session.commit()
    return len(default_flags)
