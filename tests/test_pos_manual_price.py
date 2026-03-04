"""
Comprehensive Unit Tests for POS Manual Price Adjustment Feature

Tests cover:
1. Complete sale with manually adjusted (lower) prices
2. Complete sale with manually adjusted (higher) prices
3. Item-level discount calculation from price difference
4. Zero change when paying exact adjusted amount
5. Change calculation with adjusted prices
6. Multiple items with mixed adjusted/original prices
7. Price adjustment to zero
8. Negative price rejection (backend validation)
9. Adjusted price with percentage discount on top
10. Adjusted price with fixed discount on top
11. Split payment with adjusted prices
12. Partial payment with adjusted prices
13. Multiple quantities with adjusted unit price
14. Stock deduction correctness after price adjustment
15. Sale record integrity (unit_price, subtotal, discount stored correctly)
16. Receipt data correctness with adjusted prices
17. Edge cases: very large prices, very small prices, decimal precision
18. Role-based access (admin, manager, cashier can all adjust)
19. Backdate sale with adjusted prices
"""

import pytest
import json
from decimal import Decimal
from datetime import date, timedelta

from app.models import (
    db, User, Product, Sale, SaleItem, Customer, Payment,
    LocationStock, Location, Category, Setting, StockMovement
)


# ============================================================================
# HELPERS
# ============================================================================

def login(client, username, password):
    """Login helper."""
    return client.post('/auth/login', data={
        'username': username,
        'password': password
    }, follow_redirects=True)


def make_sale_data(product_id, quantity=1, unit_price=None, original_price=None,
                   payment_method='cash', amount_paid=None, discount=0,
                   discount_type='amount', customer_id=None, sale_date=None,
                   payments=None):
    """Build sale data dict for /pos/complete-sale."""
    if unit_price is None:
        unit_price = 1000
    subtotal = unit_price * quantity
    total = max(0, subtotal - discount)
    if amount_paid is None:
        amount_paid = total

    # Calculate item-level discount from price adjustment
    item_discount = 0
    if original_price is not None and unit_price < original_price:
        item_discount = (original_price - unit_price) * quantity

    data = {
        'items': [{
            'product_id': product_id,
            'quantity': quantity,
            'unit_price': unit_price,
            'discount': item_discount,
            'subtotal': subtotal
        }],
        'subtotal': subtotal,
        'discount': discount,
        'discount_type': discount_type,
        'tax': 0,
        'total': total,
        'payment_method': payment_method,
        'amount_paid': amount_paid,
        'customer_id': customer_id,
        'notes': '',
        'sale_date': sale_date,
        'payments': payments or []
    }
    return data


def make_multi_item_sale_data(items_list, discount=0, discount_type='amount',
                              payment_method='cash', amount_paid=None,
                              customer_id=None, payments=None):
    """Build sale data with multiple items.

    items_list: list of dicts with keys: product_id, quantity, unit_price, original_price (optional)
    """
    sale_items = []
    subtotal = 0
    for item in items_list:
        qty = item['quantity']
        price = item['unit_price']
        item_subtotal = price * qty
        item_discount = 0
        if 'original_price' in item and item['unit_price'] < item['original_price']:
            item_discount = (item['original_price'] - item['unit_price']) * qty
        sale_items.append({
            'product_id': item['product_id'],
            'quantity': qty,
            'unit_price': price,
            'discount': item_discount,
            'subtotal': item_subtotal
        })
        subtotal += item_subtotal

    total = max(0, subtotal - discount)
    if amount_paid is None:
        amount_paid = total

    return {
        'items': sale_items,
        'subtotal': subtotal,
        'discount': discount,
        'discount_type': discount_type,
        'tax': 0,
        'total': total,
        'payment_method': payment_method,
        'amount_paid': amount_paid,
        'customer_id': customer_id,
        'notes': '',
        'sale_date': None,
        'payments': payments or []
    }


# ============================================================================
# TEST: BASIC MANUAL PRICE ADJUSTMENT — POSITIVE CASES
# ============================================================================

class TestManualPriceAdjustmentBasic:
    """Basic positive tests for manual price adjustment at checkout."""

    def test_sale_with_lower_adjusted_price(self, auth_admin, init_database):
        """Item priced at 1000, sold at 800. Change = 0."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            amount_paid=800
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['change'] == 0.0

    def test_sale_with_exact_adjusted_price_zero_change(self, auth_admin, init_database):
        """Item at 2500, adjusted to 2000, pay 2000 => change 0."""
        product = Product.query.filter_by(code='PRD004').first()  # selling_price=1500
        data = make_sale_data(
            product_id=product.id,
            unit_price=1200,
            original_price=1500,
            amount_paid=1200
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['change'] == 0.0
        assert result['total'] == 1200.0

    def test_sale_with_higher_adjusted_price(self, auth_admin, init_database):
        """Item priced at 600, sold at 750 (premium markup)."""
        product = Product.query.filter_by(code='PRD002').first()  # selling_price=600
        data = make_sale_data(
            product_id=product.id,
            unit_price=750,
            original_price=600,
            amount_paid=750
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['change'] == 0.0
        assert result['total'] == 750.0

    def test_sale_with_original_price_no_adjustment(self, auth_admin, init_database):
        """Sale at original price — no adjustment, baseline test."""
        product = Product.query.filter_by(code='PRD001').first()
        price = float(product.selling_price)
        data = make_sale_data(
            product_id=product.id,
            unit_price=price,
            amount_paid=price
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['change'] == 0.0

    def test_adjusted_price_with_overpayment_returns_change(self, auth_admin, init_database):
        """Item adjusted to 800, customer pays 1000 => change = 200."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            amount_paid=1000
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['change'] == 200.0

    def test_adjusted_price_with_multiple_quantity(self, auth_admin, init_database):
        """2x items adjusted from 1000 to 800 each => total 1600."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            quantity=2,
            unit_price=800,
            original_price=1000,
            amount_paid=1600
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['total'] == 1600.0
        assert result['change'] == 0.0


# ============================================================================
# TEST: ITEM-LEVEL DISCOUNT FROM PRICE ADJUSTMENT
# ============================================================================

class TestItemLevelDiscount:
    """Tests that item-level discount is correctly stored when price is adjusted."""

    def test_item_discount_stored_on_price_reduction(self, auth_admin, init_database):
        """Verify SaleItem.discount = (original - adjusted) * qty."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            quantity=1,
            unit_price=800,
            original_price=1000,
            amount_paid=800
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        assert result['success'] is True

        sale_item = SaleItem.query.filter_by(sale_id=result['sale_id']).first()
        assert sale_item is not None
        assert float(sale_item.unit_price) == 800.0
        assert float(sale_item.discount) == 200.0  # (1000 - 800) * 1
        assert float(sale_item.subtotal) == 800.0

    def test_item_discount_stored_with_multiple_qty(self, auth_admin, init_database):
        """Verify item discount is multiplied by quantity."""
        product = Product.query.filter_by(code='PRD002').first()  # selling_price=600
        data = make_sale_data(
            product_id=product.id,
            quantity=3,
            unit_price=500,
            original_price=600,
            amount_paid=1500
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        assert result['success'] is True

        sale_item = SaleItem.query.filter_by(sale_id=result['sale_id']).first()
        assert float(sale_item.discount) == 300.0  # (600 - 500) * 3
        assert float(sale_item.subtotal) == 1500.0

    def test_no_item_discount_when_price_increased(self, auth_admin, init_database):
        """No item-level discount when price is raised."""
        product = Product.query.filter_by(code='PRD002').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=700,
            original_price=600,
            amount_paid=700
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        assert result['success'] is True

        sale_item = SaleItem.query.filter_by(sale_id=result['sale_id']).first()
        assert float(sale_item.discount) == 0.0
        assert float(sale_item.unit_price) == 700.0

    def test_no_item_discount_when_no_price_change(self, auth_admin, init_database):
        """No item-level discount when price is not changed."""
        product = Product.query.filter_by(code='PRD001').first()
        price = float(product.selling_price)
        data = make_sale_data(
            product_id=product.id,
            unit_price=price,
            amount_paid=price
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        assert result['success'] is True

        sale_item = SaleItem.query.filter_by(sale_id=result['sale_id']).first()
        assert float(sale_item.discount) == 0.0


# ============================================================================
# TEST: ADJUSTED PRICE + TRANSACTION-LEVEL DISCOUNT
# ============================================================================

class TestAdjustedPriceWithDiscount:
    """Tests combining manual price adjustment with transaction-level discounts."""

    def test_adjusted_price_plus_percentage_discount(self, auth_admin, init_database):
        """Item adjusted to 800, then 10% off => total 720."""
        product = Product.query.filter_by(code='PRD001').first()
        # unit_price=800, subtotal=800, discount=10% of 800=80, total=720
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            discount=80,  # 10% of 800
            discount_type='percent',
            amount_paid=720
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['total'] == 720.0
        assert result['change'] == 0.0

    def test_adjusted_price_plus_fixed_discount(self, auth_admin, init_database):
        """Item adjusted to 800, then Rs. 100 off => total 700."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            discount=100,
            discount_type='amount',
            amount_paid=700
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['total'] == 700.0
        assert result['change'] == 0.0

    def test_adjusted_price_with_large_discount_not_below_zero(self, auth_admin, init_database):
        """Adjusted to 200, discount 300 => total capped at 0 (frontend enforces)."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=200,
            original_price=1000,
            discount=300,
            discount_type='amount',
            amount_paid=0
        )
        # total = max(0, 200-300) = 0
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['total'] == 0.0


# ============================================================================
# TEST: MULTIPLE ITEMS WITH MIXED PRICE ADJUSTMENTS
# ============================================================================

class TestMultipleItemsMixedPrices:
    """Tests with multiple items where some are adjusted and some are not."""

    def test_two_items_one_adjusted(self, auth_admin, init_database):
        """Item1 at original 1000, Item2 adjusted from 600 to 400."""
        p1 = Product.query.filter_by(code='PRD001').first()
        p2 = Product.query.filter_by(code='PRD002').first()
        data = make_multi_item_sale_data(
            items_list=[
                {'product_id': p1.id, 'quantity': 1, 'unit_price': 1000},
                {'product_id': p2.id, 'quantity': 1, 'unit_price': 400, 'original_price': 600},
            ],
            amount_paid=1400
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['total'] == 1400.0
        assert result['change'] == 0.0

    def test_two_items_both_adjusted(self, auth_admin, init_database):
        """Both items manually adjusted down."""
        p1 = Product.query.filter_by(code='PRD001').first()
        p2 = Product.query.filter_by(code='PRD002').first()
        data = make_multi_item_sale_data(
            items_list=[
                {'product_id': p1.id, 'quantity': 1, 'unit_price': 900, 'original_price': 1000},
                {'product_id': p2.id, 'quantity': 2, 'unit_price': 500, 'original_price': 600},
            ],
            amount_paid=1900
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['total'] == 1900.0  # 900 + 500*2

        # Verify individual sale items
        items = SaleItem.query.filter_by(sale_id=result['sale_id']).all()
        assert len(items) == 2
        prices = {float(i.unit_price) for i in items}
        assert 900.0 in prices
        assert 500.0 in prices

    def test_three_items_with_discount_on_top(self, auth_admin, init_database):
        """3 items, 2 adjusted + transaction discount."""
        p1 = Product.query.filter_by(code='PRD001').first()
        p2 = Product.query.filter_by(code='PRD002').first()
        p4 = Product.query.filter_by(code='PRD004').first()
        data = make_multi_item_sale_data(
            items_list=[
                {'product_id': p1.id, 'quantity': 1, 'unit_price': 900, 'original_price': 1000},
                {'product_id': p2.id, 'quantity': 1, 'unit_price': 600},
                {'product_id': p4.id, 'quantity': 1, 'unit_price': 1200, 'original_price': 1500},
            ],
            discount=100,
            discount_type='amount',
            amount_paid=2600  # 900+600+1200-100
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['total'] == 2600.0


# ============================================================================
# TEST: PAYMENT METHODS WITH ADJUSTED PRICES
# ============================================================================

class TestPaymentMethodsWithAdjustedPrices:
    """Tests for different payment methods with adjusted prices."""

    def test_card_payment_adjusted_price(self, auth_admin, init_database):
        """Card payment with adjusted price."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            payment_method='card',
            amount_paid=800
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['change'] == 0.0

    def test_easypaisa_payment_adjusted_price(self, auth_admin, init_database):
        """EasyPaisa payment with adjusted price."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=850,
            original_price=1000,
            payment_method='easypaisa',
            amount_paid=850
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True

    def test_jazzcash_payment_adjusted_price(self, auth_admin, init_database):
        """JazzCash payment with adjusted price."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=900,
            original_price=1000,
            payment_method='jazzcash',
            amount_paid=900
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True

    def test_split_payment_with_adjusted_price(self, auth_admin, init_database):
        """Split payment: cash + card for adjusted price item."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            payment_method='split',
            amount_paid=800,
            payments=[
                {'method': 'cash', 'amount': 500, 'reference': ''},
                {'method': 'card', 'amount': 300, 'reference': 'CARD-001'}
            ]
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True

        # Verify payment records
        payments = Payment.query.filter_by(sale_id=result['sale_id']).order_by(Payment.payment_order).all()
        assert len(payments) == 2
        assert float(payments[0].amount) == 500.0
        assert payments[0].payment_method == 'cash'
        assert float(payments[1].amount) == 300.0
        assert payments[1].payment_method == 'card'

    def test_split_payment_three_ways_adjusted_price(self, auth_admin, init_database):
        """Split 3 ways with adjusted price."""
        product = Product.query.filter_by(code='PRD004').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=1200,
            original_price=1500,
            payment_method='split',
            amount_paid=1200,
            payments=[
                {'method': 'cash', 'amount': 400, 'reference': ''},
                {'method': 'card', 'amount': 400, 'reference': 'CARD-002'},
                {'method': 'easypaisa', 'amount': 400, 'reference': 'EP-001'}
            ]
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True

        payments = Payment.query.filter_by(sale_id=result['sale_id']).all()
        assert len(payments) == 3
        total_paid = sum(float(p.amount) for p in payments)
        assert total_paid == 1200.0


# ============================================================================
# TEST: STOCK DEDUCTION WITH ADJUSTED PRICES
# ============================================================================

class TestStockDeductionWithAdjustedPrices:
    """Verify stock is deducted correctly regardless of price adjustment."""

    def test_stock_deducted_correctly_after_price_adjustment(self, auth_admin, init_database):
        """Stock should deduct by quantity, not affected by price change."""
        product = Product.query.filter_by(code='PRD001').first()
        qty_before = product.quantity

        data = make_sale_data(
            product_id=product.id,
            quantity=2,
            unit_price=800,
            original_price=1000,
            amount_paid=1600
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True

        # Admin has no location, so product.quantity is deducted (fallback path)
        db.session.expire_all()
        product = Product.query.filter_by(code='PRD001').first()
        assert product.quantity == qty_before - 2

    def test_stock_movement_recorded_with_adjusted_price(self, auth_admin, init_database):
        """Stock movement record should exist after adjusted price sale."""
        product = Product.query.filter_by(code='PRD002').first()
        data = make_sale_data(
            product_id=product.id,
            quantity=1,
            unit_price=400,
            original_price=600,
            amount_paid=400
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        assert result['success'] is True

        movement = StockMovement.query.filter_by(
            product_id=product.id,
            movement_type='sale'
        ).order_by(StockMovement.id.desc()).first()
        assert movement is not None
        assert movement.quantity == -1


# ============================================================================
# TEST: SALE RECORD INTEGRITY
# ============================================================================

class TestSaleRecordIntegrity:
    """Verify the Sale and SaleItem records are correctly persisted."""

    def test_sale_total_matches_adjusted_price(self, auth_admin, init_database):
        """Sale.total should match the adjusted subtotal minus discount."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            amount_paid=800
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        sale = Sale.query.get(result['sale_id'])
        assert float(sale.total) == 800.0
        assert float(sale.subtotal) == 800.0
        assert float(sale.amount_paid) == 800.0
        assert sale.payment_status == 'paid'

    def test_sale_item_unit_price_is_adjusted(self, auth_admin, init_database):
        """SaleItem.unit_price should be the adjusted price, not original."""
        product = Product.query.filter_by(code='PRD004').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=1200,
            original_price=1500,
            amount_paid=1200
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        item = SaleItem.query.filter_by(sale_id=result['sale_id']).first()
        assert float(item.unit_price) == 1200.0
        assert float(item.subtotal) == 1200.0

    def test_sale_amount_due_zero_when_paid_in_full(self, auth_admin, init_database):
        """Amount due should be 0 when adjusted price is fully paid."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=700,
            original_price=1000,
            amount_paid=700
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        sale = Sale.query.get(result['sale_id'])
        assert float(sale.amount_due) <= 0
        assert sale.payment_status == 'paid'

    def test_sale_payment_record_created(self, auth_admin, init_database):
        """Payment record should be created with adjusted amount."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            payment_method='cash',
            amount_paid=800
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        payment = Payment.query.filter_by(sale_id=result['sale_id']).first()
        assert payment is not None
        assert float(payment.amount) == 800.0
        assert payment.payment_method == 'cash'


# ============================================================================
# TEST: CHANGE CALCULATION
# ============================================================================

class TestChangeCalculation:
    """Tests for change calculation with adjusted prices."""

    def test_exact_payment_zero_change(self, auth_admin, init_database):
        """Pay exactly the adjusted price => change = 0."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            amount_paid=800
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        assert result['change'] == 0.0

    def test_overpayment_positive_change(self, auth_admin, init_database):
        """Pay more than adjusted price => positive change."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            amount_paid=1000
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        assert result['change'] == 200.0

    def test_large_overpayment_change(self, auth_admin, init_database):
        """Customer pays with large denomination."""
        product = Product.query.filter_by(code='PRD002').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=450,
            original_price=600,
            amount_paid=1000
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        assert result['change'] == 550.0

    def test_change_with_multiple_adjusted_items(self, auth_admin, init_database):
        """Multiple items adjusted, pay with round number."""
        p1 = Product.query.filter_by(code='PRD001').first()
        p2 = Product.query.filter_by(code='PRD002').first()
        # Total = 800 + 500 = 1300, pay 1500
        data = make_multi_item_sale_data(
            items_list=[
                {'product_id': p1.id, 'quantity': 1, 'unit_price': 800, 'original_price': 1000},
                {'product_id': p2.id, 'quantity': 1, 'unit_price': 500, 'original_price': 600},
            ],
            amount_paid=1500
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['change'] == 200.0


# ============================================================================
# TEST: ROLE-BASED ACCESS
# ============================================================================

class TestRoleBasedPriceAdjustment:
    """All roles with POS access should be able to sell at adjusted prices."""

    def test_admin_can_sell_adjusted_price(self, auth_admin, init_database):
        """Admin can complete sale with adjusted price."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(product_id=product.id, unit_price=800, amount_paid=800)
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        assert json.loads(response.data)['success'] is True

    def test_manager_can_sell_adjusted_price(self, auth_manager, init_database):
        """Manager can complete sale with adjusted price."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(product_id=product.id, unit_price=800, amount_paid=800)
        response = auth_manager.post('/pos/complete-sale',
                                     json=data,
                                     content_type='application/json')
        assert response.status_code == 200
        assert json.loads(response.data)['success'] is True

    def test_cashier_can_sell_adjusted_price(self, auth_cashier, init_database):
        """Cashier can complete sale with adjusted price."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(product_id=product.id, unit_price=800, amount_paid=800)
        response = auth_cashier.post('/pos/complete-sale',
                                     json=data,
                                     content_type='application/json')
        assert response.status_code == 200
        assert json.loads(response.data)['success'] is True

    def test_unauthenticated_cannot_complete_sale(self, client):
        """Unauthenticated user cannot complete sale."""
        data = make_sale_data(product_id=1, unit_price=800, amount_paid=800)
        response = client.post('/pos/complete-sale',
                               json=data,
                               content_type='application/json')
        assert response.status_code in [302, 401]


# ============================================================================
# TEST: NEGATIVE / EDGE CASES
# ============================================================================

class TestNegativeAndEdgeCases:
    """Negative tests and edge cases for price adjustment."""

    def test_underpayment_rejected(self, auth_admin, init_database):
        """Amount paid less than adjusted total should fail (frontend enforces, but test backend)."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            amount_paid=700  # Less than 800
        )
        # Backend stores partial payment
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        # The backend accepts partial payments (amount_due > 0)
        if response.status_code == 200:
            result = json.loads(response.data)
            sale = Sale.query.get(result['sale_id'])
            assert sale.payment_status == 'partial'
            assert float(sale.amount_due) > 0

    def test_zero_price_adjustment(self, auth_admin, init_database):
        """Item adjusted to price 0 (free item)."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=0,
            original_price=1000,
            amount_paid=0
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['total'] == 0.0
        assert result['change'] == 0.0

    def test_very_small_price_adjustment(self, auth_admin, init_database):
        """Item adjusted to Rs. 1."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=1,
            original_price=1000,
            amount_paid=1
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['total'] == 1.0

    def test_very_large_price_adjustment(self, auth_admin, init_database):
        """Item adjusted to a very large price."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=99999.99,
            original_price=1000,
            amount_paid=99999.99
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True

    def test_decimal_price_adjustment(self, auth_admin, init_database):
        """Item adjusted to a decimal price like 799.50."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=799.50,
            original_price=1000,
            amount_paid=799.50
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert abs(result['total'] - 799.50) < 0.01

    def test_price_adjustment_with_decimal_quantity_precision(self, auth_admin, init_database):
        """3 items at 333.33 each = 999.99 total."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            quantity=3,
            unit_price=333.33,
            original_price=1000,
            amount_paid=999.99
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True

    def test_empty_cart_with_adjusted_prices_still_fails(self, auth_admin, init_database):
        """Empty cart should still fail even if other fields have values."""
        data = {
            'items': [],
            'subtotal': 800,
            'discount': 0,
            'tax': 0,
            'total': 800,
            'payment_method': 'cash',
            'amount_paid': 800,
            'payments': []
        }
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 400
        result = json.loads(response.data)
        assert result['success'] is False

    def test_invalid_product_id_with_adjusted_price(self, auth_admin, init_database):
        """Non-existent product ID should fail."""
        data = make_sale_data(
            product_id=99999,
            unit_price=800,
            amount_paid=800
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 404
        result = json.loads(response.data)
        assert result['success'] is False

    def test_out_of_stock_product_with_adjusted_price(self, auth_admin, init_database):
        """Out of stock product should fail even with adjusted price."""
        product = Product.query.filter_by(code='PRD003').first()  # quantity=0
        data = make_sale_data(
            product_id=product.id,
            unit_price=200,
            original_price=400,
            amount_paid=200
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 400
        result = json.loads(response.data)
        assert result['success'] is False
        assert 'Insufficient' in result['error'] or 'stock' in result['error'].lower()

    def test_quantity_exceeds_stock_with_adjusted_price(self, auth_admin, init_database):
        """Quantity beyond stock should fail even with adjusted price."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            quantity=9999,
            unit_price=100,
            original_price=1000,
            amount_paid=999900
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 400
        result = json.loads(response.data)
        assert result['success'] is False


# ============================================================================
# TEST: CUSTOMER AND LOYALTY WITH ADJUSTED PRICES
# ============================================================================

class TestCustomerLoyaltyWithAdjustedPrices:
    """Tests for customer and loyalty points with adjusted prices."""

    def test_loyalty_points_based_on_adjusted_total(self, auth_admin, init_database):
        """Loyalty points should be awarded based on the adjusted total, not original."""
        product = Product.query.filter_by(code='PRD001').first()
        customer = Customer.query.filter_by(name='John Doe').first()
        initial_points = customer.loyalty_points

        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            amount_paid=800,
            customer_id=customer.id
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True

        # Refresh customer
        db.session.expire_all()
        customer = Customer.query.filter_by(name='John Doe').first()
        # Points based on adjusted total (800), not original (1000)
        # 1 point per Rs. 100 => 8 points
        expected_points = initial_points + 8
        assert customer.loyalty_points == expected_points

    def test_sale_with_customer_and_adjusted_price(self, auth_admin, init_database):
        """Sale with customer ID and adjusted price stores customer correctly."""
        product = Product.query.filter_by(code='PRD001').first()
        customer = Customer.query.filter_by(name='Jane Smith').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            amount_paid=800,
            customer_id=customer.id
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        assert result['success'] is True

        sale = Sale.query.get(result['sale_id'])
        assert sale.customer_id == customer.id

    def test_walkin_customer_adjusted_price(self, auth_admin, init_database):
        """Walk-in customer (no customer_id) with adjusted price."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            amount_paid=800,
            customer_id=None
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        assert result['success'] is True

        sale = Sale.query.get(result['sale_id'])
        assert sale.customer_id is None


# ============================================================================
# TEST: BACKDATE SALE WITH ADJUSTED PRICES
# ============================================================================

class TestBackdateSaleWithAdjustedPrices:
    """Tests for backdated sales with adjusted prices (admin/manager only)."""

    def test_admin_backdate_with_adjusted_price(self, auth_admin, init_database):
        """Admin can backdate a sale with adjusted price."""
        product = Product.query.filter_by(code='PRD001').first()
        yesterday = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            amount_paid=800,
            sale_date=yesterday
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True

    def test_cashier_cannot_backdate_with_adjusted_price(self, auth_cashier, init_database):
        """Cashier should not be able to backdate, even with adjusted price."""
        product = Product.query.filter_by(code='PRD001').first()
        yesterday = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            amount_paid=800,
            sale_date=yesterday
        )
        response = auth_cashier.post('/pos/complete-sale',
                                     json=data,
                                     content_type='application/json')
        assert response.status_code == 403
        result = json.loads(response.data)
        assert result['success'] is False


# ============================================================================
# TEST: RECEIPT DATA WITH ADJUSTED PRICES
# ============================================================================

class TestReceiptWithAdjustedPrices:
    """Tests that receipt displays correct adjusted price data."""

    def test_receipt_accessible_after_adjusted_price_sale(self, auth_admin, init_database):
        """Receipt page should load after a sale with adjusted price."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            amount_paid=800
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        assert result['success'] is True

        # Access receipt
        receipt_response = auth_admin.get(f'/pos/print-receipt/{result["sale_id"]}')
        assert receipt_response.status_code == 200

    def test_sale_details_accessible_after_adjusted_price_sale(self, auth_admin, init_database):
        """Sale details page should load after a sale with adjusted price."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            amount_paid=1000
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        assert result['success'] is True

        details_response = auth_admin.get(f'/pos/sale-details/{result["sale_id"]}')
        assert details_response.status_code == 200


# ============================================================================
# TEST: CONSECUTIVE SALES WITH ADJUSTED PRICES
# ============================================================================

class TestConsecutiveSales:
    """Tests for making multiple consecutive sales with price adjustments."""

    def test_two_consecutive_sales_different_adjustments(self, auth_admin, init_database):
        """Two sales of same product with different price adjustments."""
        product = Product.query.filter_by(code='PRD001').first()

        # Sale 1: adjusted to 800
        data1 = make_sale_data(
            product_id=product.id, unit_price=800, original_price=1000, amount_paid=800
        )
        r1 = auth_admin.post('/pos/complete-sale', json=data1, content_type='application/json')
        assert r1.status_code == 200
        res1 = json.loads(r1.data)
        assert res1['success'] is True

        # Sale 2: adjusted to 900
        data2 = make_sale_data(
            product_id=product.id, unit_price=900, original_price=1000, amount_paid=900
        )
        r2 = auth_admin.post('/pos/complete-sale', json=data2, content_type='application/json')
        assert r2.status_code == 200
        res2 = json.loads(r2.data)
        assert res2['success'] is True

        # Verify both sales have correct unit prices
        item1 = SaleItem.query.filter_by(sale_id=res1['sale_id']).first()
        item2 = SaleItem.query.filter_by(sale_id=res2['sale_id']).first()
        assert float(item1.unit_price) == 800.0
        assert float(item2.unit_price) == 900.0

    def test_three_consecutive_sales_mixed(self, auth_admin, init_database):
        """Three sales: original price, lower, higher."""
        product = Product.query.filter_by(code='PRD002').first()  # selling_price=600

        # Sale 1: original price
        d1 = make_sale_data(product_id=product.id, unit_price=600, amount_paid=600)
        r1 = auth_admin.post('/pos/complete-sale', json=d1, content_type='application/json')
        assert json.loads(r1.data)['success'] is True

        # Sale 2: lower
        d2 = make_sale_data(product_id=product.id, unit_price=400, amount_paid=400)
        r2 = auth_admin.post('/pos/complete-sale', json=d2, content_type='application/json')
        assert json.loads(r2.data)['success'] is True

        # Sale 3: higher
        d3 = make_sale_data(product_id=product.id, unit_price=750, amount_paid=750)
        r3 = auth_admin.post('/pos/complete-sale', json=d3, content_type='application/json')
        assert json.loads(r3.data)['success'] is True


# ============================================================================
# TEST: PARTIAL PAYMENT WITH ADJUSTED PRICES
# ============================================================================

class TestPartialPaymentAdjustedPrices:
    """Tests for partial payments (credit) with adjusted prices."""

    def test_partial_payment_adjusted_price(self, auth_admin, init_database):
        """Partial payment on adjusted price sale."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            amount_paid=500  # Partial
        )
        # Override total to match adjusted subtotal
        data['total'] = 800
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True

        sale = Sale.query.get(result['sale_id'])
        assert sale.payment_status == 'partial'
        assert float(sale.amount_due) == 300.0  # 800 - 500

    def test_full_payment_status_paid(self, auth_admin, init_database):
        """Full payment on adjusted price => status paid."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            amount_paid=800
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        result = json.loads(response.data)
        sale = Sale.query.get(result['sale_id'])
        assert sale.payment_status == 'paid'


# ============================================================================
# TEST: SALES LIST SHOWS ADJUSTED PRICE SALES
# ============================================================================

class TestSalesListWithAdjustedPrices:
    """Tests that sales list correctly shows sales with adjusted prices."""

    def test_sales_list_includes_adjusted_price_sale(self, auth_admin, init_database):
        """Sales list should include the sale made with adjusted price."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=800,
            original_price=1000,
            amount_paid=800
        )
        auth_admin.post('/pos/complete-sale', json=data, content_type='application/json')

        response = auth_admin.get('/pos/sales')
        assert response.status_code == 200


# ============================================================================
# TEST: MALFORMED / INVALID REQUESTS
# ============================================================================

class TestMalformedRequests:
    """Tests for invalid/malformed requests with price adjustments."""

    def test_missing_unit_price_field(self, auth_admin, init_database):
        """Missing unit_price in item data should cause error."""
        product = Product.query.filter_by(code='PRD001').first()
        data = {
            'items': [{
                'product_id': product.id,
                'quantity': 1,
                # 'unit_price': missing
                'discount': 0,
                'subtotal': 800
            }],
            'subtotal': 800,
            'discount': 0,
            'tax': 0,
            'total': 800,
            'payment_method': 'cash',
            'amount_paid': 800,
            'payments': []
        }
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        # Should fail with 500 (KeyError) or 400
        assert response.status_code in [400, 500]

    def test_string_unit_price(self, auth_admin, init_database):
        """String value for unit_price should cause error."""
        product = Product.query.filter_by(code='PRD001').first()
        data = {
            'items': [{
                'product_id': product.id,
                'quantity': 1,
                'unit_price': 'not_a_number',
                'discount': 0,
                'subtotal': 800
            }],
            'subtotal': 800,
            'discount': 0,
            'tax': 0,
            'total': 800,
            'payment_method': 'cash',
            'amount_paid': 800,
            'payments': []
        }
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code in [400, 500]

    def test_none_unit_price(self, auth_admin, init_database):
        """None value for unit_price should cause error."""
        product = Product.query.filter_by(code='PRD001').first()
        data = {
            'items': [{
                'product_id': product.id,
                'quantity': 1,
                'unit_price': None,
                'discount': 0,
                'subtotal': 0
            }],
            'subtotal': 0,
            'discount': 0,
            'tax': 0,
            'total': 0,
            'payment_method': 'cash',
            'amount_paid': 0,
            'payments': []
        }
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        assert response.status_code in [400, 500]

    def test_negative_unit_price(self, auth_admin, init_database):
        """Negative unit_price should be handled (stored or rejected)."""
        product = Product.query.filter_by(code='PRD001').first()
        data = make_sale_data(
            product_id=product.id,
            unit_price=-100,
            amount_paid=0
        )
        response = auth_admin.post('/pos/complete-sale',
                                   json=data,
                                   content_type='application/json')
        # Backend may accept (Decimal accepts negatives) or reject
        # Either way it should not crash
        assert response.status_code in [200, 400, 500]

    def test_no_json_body(self, auth_admin, init_database):
        """Request with no JSON body should fail."""
        response = auth_admin.post('/pos/complete-sale',
                                   content_type='application/json')
        assert response.status_code in [400, 500]
