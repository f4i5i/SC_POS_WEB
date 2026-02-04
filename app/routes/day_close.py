"""
Day Close & Cash Reconciliation Routes
Handles end-of-day closing, cash counting, and variance management
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import func, and_, or_
from app.models import db, DayClose, Sale, SaleItem, Location, User, Product, LocationStock, InventorySpotCheck, InventorySpotCheckItem, RawMaterial, RawMaterialStock
from app.utils.permissions import permission_required, Permissions
from app.utils.location_context import get_current_location

bp = Blueprint('day_close', __name__, url_prefix='/day-close')


@bp.route('/')
@login_required
@permission_required(Permissions.POS_CLOSE_DAY)
def index():
    """Day close main page - start closing process"""
    location = get_current_location()

    # For global admin, allow selecting location
    if not location and current_user.is_global_admin:
        selected_location_id = request.args.get('location_id', type=int)
        if selected_location_id:
            location = Location.query.get(selected_location_id)

    # Get all locations for selection (for global admin)
    locations = []
    if current_user.is_global_admin:
        locations = Location.query.filter_by(is_active=True, can_sell=True).order_by(Location.name).all()

    if not location:
        return render_template('day_close/select_location.html', locations=locations)

    today = date.today()

    # Check if day already closed for this location
    existing_close = DayClose.query.filter_by(
        close_date=today,
        location_id=location.id
    ).first()

    if existing_close:
        flash(f'Day already closed for {location.name} on {today}', 'warning')
        return redirect(url_for('day_close.detail', close_id=existing_close.id))

    # Get today's sales for this location
    today_sales = Sale.query.filter(
        func.date(Sale.sale_date) == today,
        Sale.location_id == location.id,
        Sale.status == 'completed'
    ).all()

    # Get refunded sales
    refunded_sales = Sale.query.filter(
        func.date(Sale.sale_date) == today,
        Sale.location_id == location.id,
        Sale.status == 'refunded'
    ).all()

    # Calculate totals
    total_sales = len(today_sales)
    gross_sales = sum(float(sale.subtotal or 0) for sale in today_sales)
    total_discounts = sum(float(sale.discount or 0) for sale in today_sales)
    total_tax = sum(float(sale.tax or 0) for sale in today_sales)
    net_sales = sum(float(sale.total or 0) for sale in today_sales)

    # Payment breakdown
    total_cash = sum(float(sale.total or 0) for sale in today_sales if sale.payment_method == 'cash')
    total_card = sum(float(sale.total or 0) for sale in today_sales if sale.payment_method == 'card')
    total_easypaisa = sum(float(sale.total or 0) for sale in today_sales if sale.payment_method == 'easypaisa')
    total_jazzcash = sum(float(sale.total or 0) for sale in today_sales if sale.payment_method == 'jazzcash')
    total_bank = sum(float(sale.total or 0) for sale in today_sales if sale.payment_method == 'bank_transfer')
    total_credit = sum(float(sale.total or 0) for sale in today_sales if sale.payment_method == 'credit')
    total_other = net_sales - total_cash - total_card - total_easypaisa - total_jazzcash - total_bank - total_credit

    # Refunds
    total_refunds = sum(float(sale.total or 0) for sale in refunded_sales)
    refund_count = len(refunded_sales)

    # Get opening balance (from last close for this location)
    last_close = DayClose.query.filter_by(
        location_id=location.id
    ).order_by(DayClose.close_date.desc()).first()

    opening_balance = float(last_close.closing_balance) if last_close else 0.0

    # Calculate expected cash
    # Expected = Opening + Cash Sales - Cash Refunds - Cash Out + Cash In
    expected_cash = opening_balance + total_cash

    return render_template('day_close/index.html',
                         location=location,
                         today=today,
                         total_sales=total_sales,
                         gross_sales=gross_sales,
                         total_discounts=total_discounts,
                         total_tax=total_tax,
                         net_sales=net_sales,
                         total_cash=total_cash,
                         total_card=total_card,
                         total_easypaisa=total_easypaisa,
                         total_jazzcash=total_jazzcash,
                         total_bank=total_bank,
                         total_credit=total_credit,
                         total_other=total_other,
                         total_refunds=total_refunds,
                         refund_count=refund_count,
                         opening_balance=opening_balance,
                         expected_cash=expected_cash,
                         last_close=last_close)


@bp.route('/close', methods=['POST'])
@login_required
@permission_required(Permissions.POS_CLOSE_DAY)
def close_day():
    """Process day close with cash counting"""
    try:
        location_id = request.form.get('location_id', type=int)
        location = Location.query.get_or_404(location_id)

        today = date.today()

        # Check if already closed
        existing_close = DayClose.query.filter_by(
            close_date=today,
            location_id=location.id
        ).first()

        if existing_close:
            flash('Day already closed for this location', 'error')
            return redirect(url_for('day_close.detail', close_id=existing_close.id))

        # Get today's sales
        today_sales = Sale.query.filter(
            func.date(Sale.sale_date) == today,
            Sale.location_id == location.id,
            Sale.status == 'completed'
        ).all()

        refunded_sales = Sale.query.filter(
            func.date(Sale.sale_date) == today,
            Sale.location_id == location.id,
            Sale.status == 'refunded'
        ).all()

        # Calculate totals
        total_sales = len(today_sales)
        gross_sales = sum(Decimal(str(sale.subtotal or 0)) for sale in today_sales)
        total_discounts = sum(Decimal(str(sale.discount or 0)) for sale in today_sales)
        total_tax = sum(Decimal(str(sale.tax or 0)) for sale in today_sales)
        net_sales = sum(Decimal(str(sale.total or 0)) for sale in today_sales)

        # Payment breakdown
        total_cash = sum(Decimal(str(sale.total or 0)) for sale in today_sales if sale.payment_method == 'cash')
        total_card = sum(Decimal(str(sale.total or 0)) for sale in today_sales if sale.payment_method == 'card')
        total_easypaisa = sum(Decimal(str(sale.total or 0)) for sale in today_sales if sale.payment_method == 'easypaisa')
        total_jazzcash = sum(Decimal(str(sale.total or 0)) for sale in today_sales if sale.payment_method == 'jazzcash')
        total_bank = sum(Decimal(str(sale.total or 0)) for sale in today_sales if sale.payment_method == 'bank_transfer')
        total_credit = sum(Decimal(str(sale.total or 0)) for sale in today_sales if sale.payment_method == 'credit')
        total_other = net_sales - total_cash - total_card - total_easypaisa - total_jazzcash - total_bank - total_credit

        # Refunds
        total_refunds = sum(Decimal(str(sale.total or 0)) for sale in refunded_sales)

        # Get opening balance
        last_close = DayClose.query.filter_by(
            location_id=location.id
        ).order_by(DayClose.close_date.desc()).first()
        opening_balance = Decimal(str(last_close.closing_balance)) if last_close else Decimal('0')

        # Get denomination counts from form
        denom_5000 = request.form.get('denom_5000', 0, type=int)
        denom_1000 = request.form.get('denom_1000', 0, type=int)
        denom_500 = request.form.get('denom_500', 0, type=int)
        denom_100 = request.form.get('denom_100', 0, type=int)
        denom_50 = request.form.get('denom_50', 0, type=int)
        denom_20 = request.form.get('denom_20', 0, type=int)
        denom_10 = request.form.get('denom_10', 0, type=int)
        denom_5 = request.form.get('denom_5', 0, type=int)
        denom_2 = request.form.get('denom_2', 0, type=int)
        denom_1 = request.form.get('denom_1', 0, type=int)

        # Calculate counted total
        counted_total = (
            denom_5000 * 5000 +
            denom_1000 * 1000 +
            denom_500 * 500 +
            denom_100 * 100 +
            denom_50 * 50 +
            denom_20 * 20 +
            denom_10 * 10 +
            denom_5 * 5 +
            denom_2 * 2 +
            denom_1 * 1
        )

        # Get cash movements
        cash_in = Decimal(request.form.get('cash_in', '0') or '0')
        cash_out = Decimal(request.form.get('cash_out', '0') or '0')

        # Calculate expected cash
        expected_cash = opening_balance + total_cash - cash_out + cash_in

        # Closing balance is counted total
        closing_balance = Decimal(str(counted_total))

        # Calculate variance
        cash_variance = closing_balance - expected_cash

        # Generate Z-Report number
        last_z = DayClose.query.filter(
            DayClose.location_id == location.id,
            DayClose.z_report_number.isnot(None)
        ).order_by(DayClose.id.desc()).first()

        if last_z and last_z.z_report_number:
            z_num = int(last_z.z_report_number.split('-')[-1]) + 1
        else:
            z_num = 1
        z_report_number = f"Z-{location.code}-{z_num:04d}"

        # Determine variance status
        variance_status = 'approved' if cash_variance == 0 else 'pending'

        # Create day close record
        day_close = DayClose(
            close_date=today,
            closed_by=current_user.id,
            location_id=location.id,

            # Sales summary
            total_sales=total_sales,
            total_revenue=net_sales,
            total_cash=total_cash,
            total_card=total_card,
            total_other=total_other,

            # Detailed payment breakdown
            total_easypaisa=total_easypaisa,
            total_jazzcash=total_jazzcash,
            total_bank_transfer=total_bank,
            total_credit=total_credit,

            # Sales reconciliation
            gross_sales=gross_sales,
            total_discounts=total_discounts,
            total_tax=total_tax,
            net_sales=net_sales,
            total_refunds=total_refunds,

            # Cash drawer
            opening_balance=opening_balance,
            closing_balance=closing_balance,
            expected_cash=expected_cash,
            cash_variance=cash_variance,

            # Denomination counts
            denom_5000=denom_5000,
            denom_1000=denom_1000,
            denom_500=denom_500,
            denom_100=denom_100,
            denom_50=denom_50,
            denom_20=denom_20,
            denom_10=denom_10,
            denom_5=denom_5,
            denom_2=denom_2,
            denom_1=denom_1,
            counted_total=counted_total,

            # Cash movements
            cash_in=cash_in,
            cash_out=cash_out,

            # Variance status
            variance_status=variance_status,

            # Z-Report
            z_report_number=z_report_number,

            # Notes
            notes=request.form.get('notes', ''),

            closed_at=datetime.utcnow()
        )

        db.session.add(day_close)
        db.session.commit()

        if cash_variance != 0:
            flash(f'Day closed with variance of Rs. {cash_variance:,.2f}. Manager approval required.', 'warning')
        else:
            flash('Day closed successfully with no variance!', 'success')

        return redirect(url_for('day_close.detail', close_id=day_close.id))

    except Exception as e:
        db.session.rollback()
        flash(f'Error closing day: {str(e)}', 'error')
        return redirect(url_for('day_close.index'))


@bp.route('/detail/<int:close_id>')
@login_required
@permission_required(Permissions.POS_CLOSE_DAY)
def detail(close_id):
    """View day close details"""
    day_close = DayClose.query.get_or_404(close_id)

    # Get sales for that day and location
    sales = Sale.query.filter(
        func.date(Sale.sale_date) == day_close.close_date,
        Sale.location_id == day_close.location_id
    ).order_by(Sale.sale_date).all()

    return render_template('day_close/detail.html',
                         day_close=day_close,
                         sales=sales)


@bp.route('/history')
@login_required
@permission_required(Permissions.POS_CLOSE_DAY)
def history():
    """View day close history"""
    location = get_current_location()

    # For global admin, allow selecting location
    selected_location_id = request.args.get('location_id', type=int)
    if current_user.is_global_admin and selected_location_id:
        location = Location.query.get(selected_location_id)

    # Get all locations for filter
    locations = Location.query.filter_by(is_active=True, can_sell=True).order_by(Location.name).all()

    # Date range filter
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    # Build query
    query = DayClose.query

    if location and not current_user.is_global_admin:
        query = query.filter_by(location_id=location.id)
    elif selected_location_id:
        query = query.filter_by(location_id=selected_location_id)

    if from_date:
        query = query.filter(DayClose.close_date >= datetime.strptime(from_date, '%Y-%m-%d').date())
    if to_date:
        query = query.filter(DayClose.close_date <= datetime.strptime(to_date, '%Y-%m-%d').date())

    day_closes = query.order_by(DayClose.close_date.desc()).limit(100).all()

    # Calculate totals
    total_revenue = sum(float(dc.net_sales or 0) for dc in day_closes)
    total_variance = sum(float(dc.cash_variance or 0) for dc in day_closes)
    pending_approvals = len([dc for dc in day_closes if dc.variance_status == 'pending' and dc.cash_variance != 0])

    return render_template('day_close/history.html',
                         day_closes=day_closes,
                         locations=locations,
                         selected_location_id=selected_location_id,
                         from_date=from_date,
                         to_date=to_date,
                         total_revenue=total_revenue,
                         total_variance=total_variance,
                         pending_approvals=pending_approvals)


@bp.route('/approve-variance/<int:close_id>', methods=['POST'])
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)  # Only managers/admins can approve
def approve_variance(close_id):
    """Approve or reject cash variance"""
    day_close = DayClose.query.get_or_404(close_id)

    action = request.form.get('action')  # 'approve' or 'reject'
    reason = request.form.get('reason', '')

    if action == 'approve':
        day_close.variance_status = 'approved'
        flash('Variance approved', 'success')
    elif action == 'reject':
        day_close.variance_status = 'rejected'
        flash('Variance rejected', 'warning')
    else:
        flash('Invalid action', 'error')
        return redirect(url_for('day_close.detail', close_id=close_id))

    day_close.variance_approved_by = current_user.id
    day_close.variance_approved_at = datetime.utcnow()
    day_close.variance_reason = reason

    db.session.commit()

    return redirect(url_for('day_close.detail', close_id=close_id))


@bp.route('/pending-approvals')
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)
def pending_approvals():
    """View all pending variance approvals"""
    pending = DayClose.query.filter(
        DayClose.variance_status == 'pending',
        DayClose.cash_variance != 0
    ).order_by(DayClose.close_date.desc()).all()

    return render_template('day_close/pending_approvals.html', pending=pending)


@bp.route('/z-report/<int:close_id>')
@login_required
@permission_required(Permissions.POS_CLOSE_DAY)
def z_report(close_id):
    """Generate Z-Report (end of day report)"""
    day_close = DayClose.query.get_or_404(close_id)

    # Get hourly sales breakdown
    sales = Sale.query.filter(
        func.date(Sale.sale_date) == day_close.close_date,
        Sale.location_id == day_close.location_id,
        Sale.status == 'completed'
    ).all()

    hourly_sales = {}
    for sale in sales:
        hour = sale.sale_date.hour
        if hour not in hourly_sales:
            hourly_sales[hour] = {'count': 0, 'total': 0}
        hourly_sales[hour]['count'] += 1
        hourly_sales[hour]['total'] += float(sale.total or 0)

    # Get top products
    top_products = db.session.query(
        SaleItem.product_id,
        func.sum(SaleItem.quantity).label('qty'),
        func.sum(SaleItem.subtotal).label('total')
    ).join(Sale).filter(
        func.date(Sale.sale_date) == day_close.close_date,
        Sale.location_id == day_close.location_id,
        Sale.status == 'completed'
    ).group_by(SaleItem.product_id).order_by(func.sum(SaleItem.subtotal).desc()).limit(10).all()

    return render_template('day_close/z_report.html',
                         day_close=day_close,
                         hourly_sales=hourly_sales,
                         top_products=top_products)


# ============================================================================
# INVENTORY SPOT CHECK ROUTES
# ============================================================================

@bp.route('/spot-check')
@login_required
@permission_required(Permissions.POS_CLOSE_DAY)
def spot_check():
    """Start inventory spot check - select items to check"""
    location = get_current_location()

    # For global admin, allow selecting location
    if not location and current_user.is_global_admin:
        selected_location_id = request.args.get('location_id', type=int)
        if selected_location_id:
            location = Location.query.get(selected_location_id)

    locations = []
    if current_user.is_global_admin:
        locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    if not location:
        return render_template('day_close/select_location.html',
                             locations=locations,
                             redirect_to='day_close.spot_check')

    today = date.today()
    check_type = request.args.get('check_type', 'daily')  # daily, fortnightly, random

    # Check if spot check already done today for this location
    existing_check = InventorySpotCheck.query.filter_by(
        check_date=today,
        location_id=location.id,
        check_type=check_type
    ).first()

    if existing_check:
        flash(f'Spot check ({check_type}) already completed for today', 'info')
        return redirect(url_for('day_close.spot_check_detail', check_id=existing_check.id))

    # Get products at this location
    location_stocks = LocationStock.query.filter_by(
        location_id=location.id
    ).join(Product).filter(Product.is_active == True).all()

    products = []
    for ls in location_stocks:
        products.append({
            'id': ls.product_id,
            'name': ls.product.name,
            'sku': ls.product.sku,
            'barcode': ls.product.barcode,
            'system_qty': float(ls.quantity or 0),
            'unit': ls.product.unit or 'pcs',
            'cost': float(ls.product.cost_price or 0)
        })

    # For daily check, randomly select 10-20 items
    # For fortnightly, include all items
    import random
    if check_type == 'daily':
        # Select random items (10-20 or all if less)
        sample_size = min(20, max(10, len(products) // 5))
        if len(products) > sample_size:
            selected_products = random.sample(products, sample_size)
        else:
            selected_products = products
    elif check_type == 'random':
        # Random 5 items for quick check
        sample_size = min(5, len(products))
        selected_products = random.sample(products, sample_size) if products else []
    else:
        # Full check (fortnightly/monthly)
        selected_products = products

    # Also get raw materials for warehouse locations
    raw_materials = []
    if location.location_type == 'warehouse':
        rm_stocks = RawMaterialStock.query.filter_by(
            location_id=location.id
        ).join(RawMaterial).filter(RawMaterial.is_active == True).all()

        for rms in rm_stocks:
            raw_materials.append({
                'id': rms.raw_material_id,
                'name': rms.raw_material.name,
                'sku': rms.raw_material.sku,
                'system_qty': float(rms.quantity or 0),
                'unit': rms.raw_material.unit or 'kg',
                'cost': float(rms.raw_material.cost_per_unit or 0)
            })

        if check_type == 'daily':
            sample_size = min(10, len(raw_materials))
            if len(raw_materials) > sample_size:
                raw_materials = random.sample(raw_materials, sample_size)

    # Get last spot check date
    last_check = InventorySpotCheck.query.filter_by(
        location_id=location.id
    ).order_by(InventorySpotCheck.check_date.desc()).first()

    # Calculate days since last full check
    last_full_check = InventorySpotCheck.query.filter_by(
        location_id=location.id,
        check_type='fortnightly'
    ).order_by(InventorySpotCheck.check_date.desc()).first()

    days_since_full_check = None
    if last_full_check:
        days_since_full_check = (today - last_full_check.check_date).days

    # Alert if fortnightly check overdue (>14 days)
    fortnightly_due = days_since_full_check is None or days_since_full_check >= 14

    return render_template('day_close/spot_check.html',
                         location=location,
                         today=today,
                         check_type=check_type,
                         products=selected_products,
                         raw_materials=raw_materials,
                         total_products=len(products),
                         total_raw_materials=len(raw_materials) if location.location_type == 'warehouse' else 0,
                         last_check=last_check,
                         days_since_full_check=days_since_full_check,
                         fortnightly_due=fortnightly_due)


@bp.route('/spot-check/save', methods=['POST'])
@login_required
@permission_required(Permissions.POS_CLOSE_DAY)
def save_spot_check():
    """Save inventory spot check results"""
    try:
        location_id = request.form.get('location_id', type=int)
        location = Location.query.get_or_404(location_id)
        check_type = request.form.get('check_type', 'daily')
        day_close_id = request.form.get('day_close_id', type=int)

        today = date.today()

        # Create spot check record
        spot_check = InventorySpotCheck(
            location_id=location.id,
            checked_by=current_user.id,
            check_date=today,
            check_type=check_type,
            day_close_id=day_close_id,
            notes=request.form.get('notes', ''),
            status='completed'
        )

        db.session.add(spot_check)
        db.session.flush()  # Get ID

        # Process product items
        product_ids = request.form.getlist('product_ids[]')
        items_checked = 0
        items_matched = 0
        items_with_variance = 0
        total_variance_value = Decimal('0')

        for pid in product_ids:
            pid = int(pid)
            system_qty = Decimal(request.form.get(f'system_qty_{pid}', '0') or '0')
            physical_qty = Decimal(request.form.get(f'physical_qty_{pid}', '0') or '0')
            unit_cost = Decimal(request.form.get(f'unit_cost_{pid}', '0') or '0')
            variance_reason = request.form.get(f'reason_{pid}', '')

            variance = physical_qty - system_qty
            variance_value = variance * unit_cost

            item = InventorySpotCheckItem(
                spot_check_id=spot_check.id,
                product_id=pid,
                system_quantity=system_qty,
                physical_quantity=physical_qty,
                variance=variance,
                unit_cost=unit_cost,
                variance_value=variance_value,
                variance_reason=variance_reason if variance != 0 else None
            )
            db.session.add(item)

            items_checked += 1
            if variance == 0:
                items_matched += 1
            else:
                items_with_variance += 1
                total_variance_value += variance_value

        # Process raw material items (for warehouses)
        rm_ids = request.form.getlist('rm_ids[]')
        for rmid in rm_ids:
            rmid = int(rmid)
            system_qty = Decimal(request.form.get(f'rm_system_qty_{rmid}', '0') or '0')
            physical_qty = Decimal(request.form.get(f'rm_physical_qty_{rmid}', '0') or '0')
            unit_cost = Decimal(request.form.get(f'rm_unit_cost_{rmid}', '0') or '0')
            variance_reason = request.form.get(f'rm_reason_{rmid}', '')

            variance = physical_qty - system_qty
            variance_value = variance * unit_cost

            item = InventorySpotCheckItem(
                spot_check_id=spot_check.id,
                raw_material_id=rmid,
                system_quantity=system_qty,
                physical_quantity=physical_qty,
                variance=variance,
                unit_cost=unit_cost,
                variance_value=variance_value,
                variance_reason=variance_reason if variance != 0 else None
            )
            db.session.add(item)

            items_checked += 1
            if variance == 0:
                items_matched += 1
            else:
                items_with_variance += 1
                total_variance_value += variance_value

        # Update spot check summary
        spot_check.total_items_checked = items_checked
        spot_check.items_matched = items_matched
        spot_check.items_variance = items_with_variance
        spot_check.total_variance_value = total_variance_value

        # Set status based on variance
        if items_with_variance == 0:
            spot_check.status = 'approved'  # Auto-approve if no variance
        else:
            spot_check.status = 'pending'  # Needs manager review

        db.session.commit()

        if items_with_variance > 0:
            flash(f'Spot check completed with {items_with_variance} variance(s) worth Rs. {total_variance_value:,.2f}. Manager approval required.', 'warning')
        else:
            flash('Spot check completed with no variances!', 'success')

        return redirect(url_for('day_close.spot_check_detail', check_id=spot_check.id))

    except Exception as e:
        db.session.rollback()
        flash(f'Error saving spot check: {str(e)}', 'error')
        return redirect(url_for('day_close.spot_check'))


@bp.route('/spot-check/<int:check_id>')
@login_required
@permission_required(Permissions.POS_CLOSE_DAY)
def spot_check_detail(check_id):
    """View spot check details"""
    spot_check = InventorySpotCheck.query.get_or_404(check_id)

    # Get items with products/raw materials
    items = spot_check.items.all()

    product_items = [i for i in items if i.product_id]
    rm_items = [i for i in items if i.raw_material_id]

    return render_template('day_close/spot_check_detail.html',
                         spot_check=spot_check,
                         product_items=product_items,
                         rm_items=rm_items)


@bp.route('/spot-check/<int:check_id>/approve', methods=['POST'])
@login_required
@permission_required(Permissions.SETTINGS_MANAGE_USERS)  # Manager/Admin only
def approve_spot_check(check_id):
    """Approve or reject spot check variance"""
    spot_check = InventorySpotCheck.query.get_or_404(check_id)

    action = request.form.get('action')  # 'approve', 'reject', 'adjust'
    notes = request.form.get('notes', '')

    if action == 'approve':
        spot_check.status = 'approved'
        flash('Spot check variance approved', 'success')
    elif action == 'reject':
        spot_check.status = 'rejected'
        flash('Spot check variance rejected', 'warning')
    elif action == 'adjust':
        # Adjust system inventory to match physical count
        for item in spot_check.items:
            if item.variance != 0:
                if item.product_id:
                    ls = LocationStock.query.filter_by(
                        location_id=spot_check.location_id,
                        product_id=item.product_id
                    ).first()
                    if ls:
                        ls.quantity = item.physical_quantity
                elif item.raw_material_id:
                    rms = RawMaterialStock.query.filter_by(
                        location_id=spot_check.location_id,
                        raw_material_id=item.raw_material_id
                    ).first()
                    if rms:
                        rms.quantity = item.physical_quantity

        spot_check.status = 'approved'
        flash('Inventory adjusted to match physical count', 'success')
    else:
        flash('Invalid action', 'error')
        return redirect(url_for('day_close.spot_check_detail', check_id=check_id))

    spot_check.approved_by = current_user.id
    spot_check.approved_at = datetime.utcnow()
    if notes:
        spot_check.notes = (spot_check.notes or '') + f'\n[Approval Note] {notes}'

    db.session.commit()

    return redirect(url_for('day_close.spot_check_detail', check_id=check_id))


@bp.route('/spot-check/history')
@login_required
@permission_required(Permissions.POS_CLOSE_DAY)
def spot_check_history():
    """View spot check history"""
    location = get_current_location()

    # For global admin, allow selecting location
    selected_location_id = request.args.get('location_id', type=int)
    if current_user.is_global_admin and selected_location_id:
        location = Location.query.get(selected_location_id)

    # Get all locations for filter
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    # Date range filter
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    check_type = request.args.get('check_type')

    # Build query
    query = InventorySpotCheck.query

    if location and not current_user.is_global_admin:
        query = query.filter_by(location_id=location.id)
    elif selected_location_id:
        query = query.filter_by(location_id=selected_location_id)

    if from_date:
        query = query.filter(InventorySpotCheck.check_date >= datetime.strptime(from_date, '%Y-%m-%d').date())
    if to_date:
        query = query.filter(InventorySpotCheck.check_date <= datetime.strptime(to_date, '%Y-%m-%d').date())
    if check_type:
        query = query.filter_by(check_type=check_type)

    spot_checks = query.order_by(InventorySpotCheck.check_date.desc()).limit(100).all()

    # Calculate totals
    total_variance = sum(float(sc.total_variance_value or 0) for sc in spot_checks)
    pending_approvals = len([sc for sc in spot_checks if sc.status == 'pending'])

    return render_template('day_close/spot_check_history.html',
                         spot_checks=spot_checks,
                         locations=locations,
                         selected_location_id=selected_location_id,
                         from_date=from_date,
                         to_date=to_date,
                         check_type=check_type,
                         total_variance=total_variance,
                         pending_approvals=pending_approvals)
