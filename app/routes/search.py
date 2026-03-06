"""
Global Search API
Provides unified search across pages, products, customers, and suppliers
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import or_
from app.models import db, Product, Customer, Supplier

bp = Blueprint('search', __name__, url_prefix='/api')

# Navigation pages with permission requirements
NAVIGATION_PAGES = [
    {'name': 'Dashboard', 'url': '/', 'icon': 'fas fa-tachometer-alt', 'permission': None, 'keywords': 'home main overview'},
    {'name': 'POS - Point of Sale', 'url': '/pos', 'icon': 'fas fa-cash-register', 'permission': 'pos.view', 'keywords': 'sell sale checkout cart'},
    {'name': 'Sales List', 'url': '/pos/sales', 'icon': 'fas fa-list', 'permission': 'pos.view', 'keywords': 'transactions orders history'},
    {'name': 'Products', 'url': '/inventory', 'icon': 'fas fa-boxes', 'permission': 'inventory.view', 'keywords': 'items stock inventory products'},
    {'name': 'Add New Product', 'url': '/inventory/add', 'icon': 'fas fa-plus-circle', 'permission': 'inventory.add', 'keywords': 'create new product item'},
    {'name': 'Transfers', 'url': '/transfers', 'icon': 'fas fa-exchange-alt', 'permission': 'transfer.view', 'keywords': 'stock transfer move'},
    {'name': 'Customers', 'url': '/customers', 'icon': 'fas fa-users', 'permission': 'customer.view', 'keywords': 'clients buyers loyalty'},
    {'name': 'Reports', 'url': '/reports', 'icon': 'fas fa-chart-bar', 'permission': 'report.view_sales', 'keywords': 'analytics stats report daily weekly monthly'},
    {'name': 'Financial Reports', 'url': '/financial-reports/', 'icon': 'fas fa-file-invoice-dollar', 'permission': 'report.view_sales', 'keywords': 'cash flow profit margin tax'},
    {'name': 'Expenses', 'url': '/expenses', 'icon': 'fas fa-receipt', 'permission': 'expense.view', 'keywords': 'spending bills costs payments'},
    {'name': 'Add Expense', 'url': '/expenses/add', 'icon': 'fas fa-plus-circle', 'permission': 'expense.add', 'keywords': 'new expense bill'},
    {'name': 'Suppliers', 'url': '/suppliers', 'icon': 'fas fa-truck', 'permission': None, 'keywords': 'vendors providers'},
    {'name': 'Purchase Orders', 'url': '/purchase-orders/', 'icon': 'fas fa-file-alt', 'permission': 'po.view', 'keywords': 'PO orders buy reorder'},
    {'name': 'Create Purchase Order', 'url': '/purchase-orders/create', 'icon': 'fas fa-plus-circle', 'permission': 'po.create', 'keywords': 'new PO buy order'},
    {'name': 'Draft Purchase Orders', 'url': '/purchase-orders/drafts', 'icon': 'fas fa-file', 'permission': 'po.view', 'keywords': 'draft auto reorder low stock'},
    {'name': 'Supplier Payments', 'url': '/supplier-payments/', 'icon': 'fas fa-money-check', 'permission': None, 'keywords': 'pay supplier vendor payment'},
    {'name': 'Production Dashboard', 'url': '/production', 'icon': 'fas fa-industry', 'permission': 'production.view', 'keywords': 'manufacturing batch order'},
    {'name': 'Raw Materials', 'url': '/production/raw-materials', 'icon': 'fas fa-flask', 'permission': 'production.view', 'keywords': 'oil ingredient material'},
    {'name': 'Recipes', 'url': '/production/recipes', 'icon': 'fas fa-book', 'permission': 'production.view', 'keywords': 'formula blend mix recipe'},
    {'name': 'Production Orders', 'url': '/production/orders', 'icon': 'fas fa-clipboard-list', 'permission': 'production.view', 'keywords': 'batch production order'},
    {'name': 'Promotions', 'url': '/promotions', 'icon': 'fas fa-tags', 'permission': None, 'keywords': 'discount offer promo sale'},
    {'name': 'Locations', 'url': '/locations', 'icon': 'fas fa-map-marker-alt', 'permission': None, 'keywords': 'kiosk warehouse store branch'},
    {'name': 'Settings', 'url': '/settings', 'icon': 'fas fa-cog', 'permission': None, 'keywords': 'config preferences setup'},
    {'name': 'Features', 'url': '/features', 'icon': 'fas fa-toggle-on', 'permission': None, 'keywords': 'feature flags enable disable'},
    {'name': 'Returns & Refunds', 'url': '/returns', 'icon': 'fas fa-undo', 'permission': 'pos.refund', 'keywords': 'return refund void'},
    {'name': 'Quotations', 'url': '/quotations', 'icon': 'fas fa-file-invoice', 'permission': None, 'keywords': 'quote estimate proposal'},
    {'name': 'Day Close', 'url': '/day-close/', 'icon': 'fas fa-door-closed', 'permission': None, 'keywords': 'close day end shift reconcile'},
    {'name': 'Low Stock Report', 'url': '/inventory/print-stock-report?type=low', 'icon': 'fas fa-exclamation-triangle', 'permission': 'inventory.view', 'keywords': 'low stock alert reorder'},
]


@bp.route('/search')
@login_required
def global_search():
    """Global search across pages, products, customers, suppliers"""
    query = request.args.get('q', '').strip()

    if not query or len(query) < 1:
        return jsonify({'pages': [], 'products': [], 'customers': [], 'suppliers': []})

    q_lower = query.lower()
    results = {}

    # 1. Search navigation pages (client-filtered by permission)
    matched_pages = []
    for page in NAVIGATION_PAGES:
        # Check permission
        if page['permission'] and not current_user.has_permission(page['permission']):
            continue
        # Admin-only pages
        if page['url'] in ['/settings', '/features'] and not (current_user.role == 'admin' or current_user.is_global_admin):
            continue

        # Match against name and keywords
        if q_lower in page['name'].lower() or q_lower in page.get('keywords', '').lower():
            matched_pages.append({
                'name': page['name'],
                'url': page['url'],
                'icon': page['icon'],
                'type': 'page'
            })
    results['pages'] = matched_pages[:8]

    # 2. Search products (by name, code, barcode)
    if len(query) >= 2:
        products = Product.query.filter(
            Product.is_active == True,
            or_(
                Product.name.ilike(f'%{query}%'),
                Product.code.ilike(f'%{query}%'),
                Product.barcode.ilike(f'%{query}%'),
                Product.brand.ilike(f'%{query}%')
            )
        ).limit(5).all()

        results['products'] = [{
            'name': p.name,
            'url': f'/inventory/edit/{p.id}',
            'icon': 'fas fa-box',
            'type': 'product',
            'subtitle': f'{p.code} • Rs. {p.selling_price:,.0f}'
        } for p in products]
    else:
        results['products'] = []

    # 3. Search customers (by name, phone)
    if len(query) >= 2:
        customers = Customer.query.filter(
            or_(
                Customer.name.ilike(f'%{query}%'),
                Customer.phone.ilike(f'%{query}%')
            )
        ).limit(5).all()

        results['customers'] = [{
            'name': c.name,
            'url': f'/customers/{c.id}',
            'icon': 'fas fa-user',
            'type': 'customer',
            'subtitle': c.phone or ''
        } for c in customers]
    else:
        results['customers'] = []

    # 4. Search suppliers (by name)
    if len(query) >= 2:
        suppliers = Supplier.query.filter(
            Supplier.is_active == True,
            Supplier.name.ilike(f'%{query}%')
        ).limit(5).all()

        results['suppliers'] = [{
            'name': s.name,
            'url': f'/suppliers/{s.id}',
            'icon': 'fas fa-truck',
            'type': 'supplier',
            'subtitle': s.phone or ''
        } for s in suppliers]
    else:
        results['suppliers'] = []

    return jsonify(results)
