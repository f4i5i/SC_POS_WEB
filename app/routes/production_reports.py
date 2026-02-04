"""
Production Reports Routes
Yield Variance Tracking and Batch Costing Analysis
"""

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import func, and_
from app.models import (db, ProductionOrder, ProductionMaterialConsumption, Recipe,
                        RecipeIngredient, RawMaterial, Product, Location)
from app.utils.permissions import permission_required, Permissions
from app.utils.location_context import get_current_location

bp = Blueprint('production_reports', __name__, url_prefix='/production-reports')


# ============================================================================
# YIELD VARIANCE TRACKING
# ============================================================================

@bp.route('/yield-variance')
@login_required
@permission_required(Permissions.PRODUCTION_VIEW)
def yield_variance():
    """Yield variance analysis - compare expected vs actual output"""
    location = get_current_location()

    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    recipe_id = request.args.get('recipe_id', type=int)

    if not from_date:
        from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')

    start_date = datetime.strptime(from_date, '%Y-%m-%d')
    end_date = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)

    # Get completed production orders
    query = ProductionOrder.query.filter(
        ProductionOrder.status == 'completed',
        ProductionOrder.created_at >= start_date,
        ProductionOrder.created_at < end_date
    )

    if location and not current_user.is_global_admin:
        query = query.filter(ProductionOrder.location_id == location.id)

    if recipe_id:
        query = query.filter(ProductionOrder.recipe_id == recipe_id)

    orders = query.order_by(ProductionOrder.created_at.desc()).all()

    # Calculate variance for each order
    variance_data = []
    total_expected = Decimal('0')
    total_actual = Decimal('0')
    total_variance = Decimal('0')
    total_variance_cost = Decimal('0')

    for order in orders:
        # Expected output from recipe
        recipe = order.recipe
        expected_qty = Decimal(str(order.planned_quantity or 0))

        # Actual output
        actual_qty = Decimal(str(order.actual_quantity or order.planned_quantity or 0))

        # Variance
        variance_qty = actual_qty - expected_qty
        variance_pct = ((variance_qty / expected_qty) * 100) if expected_qty > 0 else Decimal('0')

        # Cost of variance
        unit_cost = order.unit_cost or Decimal('0')
        variance_cost = variance_qty * unit_cost

        # Material consumption variance
        material_variance = calculate_material_variance(order)

        variance_data.append({
            'order': order,
            'recipe': recipe,
            'expected_qty': expected_qty,
            'actual_qty': actual_qty,
            'variance_qty': variance_qty,
            'variance_pct': variance_pct,
            'variance_cost': variance_cost,
            'material_variance': material_variance,
            'unit_cost': unit_cost
        })

        total_expected += expected_qty
        total_actual += actual_qty
        total_variance += variance_qty
        total_variance_cost += variance_cost

    # Overall variance
    overall_variance_pct = ((total_actual - total_expected) / total_expected * 100) if total_expected > 0 else 0

    # Group by recipe for summary
    recipe_summary = {}
    for item in variance_data:
        rid = item['recipe'].id if item['recipe'] else 0
        if rid not in recipe_summary:
            recipe_summary[rid] = {
                'recipe': item['recipe'],
                'orders': 0,
                'expected': Decimal('0'),
                'actual': Decimal('0'),
                'variance': Decimal('0')
            }
        recipe_summary[rid]['orders'] += 1
        recipe_summary[rid]['expected'] += item['expected_qty']
        recipe_summary[rid]['actual'] += item['actual_qty']
        recipe_summary[rid]['variance'] += item['variance_qty']

    recipes = Recipe.query.filter_by(is_active=True).order_by(Recipe.name).all()

    return render_template('production_reports/yield_variance.html',
                         variance_data=variance_data,
                         total_expected=total_expected,
                         total_actual=total_actual,
                         total_variance=total_variance,
                         total_variance_cost=total_variance_cost,
                         overall_variance_pct=overall_variance_pct,
                         recipe_summary=recipe_summary,
                         recipes=recipes,
                         recipe_id=recipe_id,
                         from_date=from_date,
                         to_date=to_date,
                         location=location)


def calculate_material_variance(order):
    """Calculate material consumption variance for an order"""
    variance = {
        'items': [],
        'total_variance_cost': Decimal('0')
    }

    # Get actual consumption
    consumptions = ProductionMaterialConsumption.query.filter_by(
        production_order_id=order.id
    ).all()

    for consumption in consumptions:
        # Get expected from recipe
        if order.recipe:
            ingredient = RecipeIngredient.query.filter_by(
                recipe_id=order.recipe.id,
                raw_material_id=consumption.raw_material_id
            ).first()

            if ingredient:
                # Calculate expected quantity based on order quantity
                expected_qty = (Decimal(str(ingredient.quantity)) *
                              Decimal(str(order.planned_quantity or 1)))
                actual_qty = consumption.quantity

                variance_qty = actual_qty - expected_qty
                variance_cost = variance_qty * (consumption.unit_cost or Decimal('0'))

                variance['items'].append({
                    'material': consumption.raw_material,
                    'expected': expected_qty,
                    'actual': actual_qty,
                    'variance': variance_qty,
                    'variance_cost': variance_cost
                })

                variance['total_variance_cost'] += variance_cost

    return variance


# ============================================================================
# BATCH COSTING
# ============================================================================

@bp.route('/batch-costing')
@login_required
@permission_required(Permissions.PRODUCTION_VIEW)
def batch_costing():
    """Batch costing analysis - detailed cost breakdown per production batch"""
    location = get_current_location()

    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    recipe_id = request.args.get('recipe_id', type=int)

    if not from_date:
        from_date = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = date.today().strftime('%Y-%m-%d')

    start_date = datetime.strptime(from_date, '%Y-%m-%d')
    end_date = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)

    # Get completed production orders
    query = ProductionOrder.query.filter(
        ProductionOrder.status == 'completed',
        ProductionOrder.created_at >= start_date,
        ProductionOrder.created_at < end_date
    )

    if location and not current_user.is_global_admin:
        query = query.filter(ProductionOrder.location_id == location.id)

    if recipe_id:
        query = query.filter(ProductionOrder.recipe_id == recipe_id)

    orders = query.order_by(ProductionOrder.created_at.desc()).all()

    # Calculate detailed costing for each batch
    batch_costs = []
    total_material_cost = Decimal('0')
    total_labor_cost = Decimal('0')
    total_overhead = Decimal('0')
    total_cost = Decimal('0')
    total_units = Decimal('0')

    for order in orders:
        cost_breakdown = calculate_batch_cost(order)
        batch_costs.append({
            'order': order,
            'cost_breakdown': cost_breakdown
        })

        total_material_cost += cost_breakdown['material_cost']
        total_labor_cost += cost_breakdown['labor_cost']
        total_overhead += cost_breakdown['overhead_cost']
        total_cost += cost_breakdown['total_cost']
        total_units += Decimal(str(order.actual_quantity or order.planned_quantity or 0))

    # Average cost per unit
    avg_unit_cost = total_cost / total_units if total_units > 0 else Decimal('0')

    # Cost trend data
    cost_trend = []
    current_date = start_date.date()
    while current_date < end_date.date():
        day_orders = [o for o in orders
                     if o.completed_at and o.completed_at.date() == current_date]
        day_cost = sum(float(o.total_cost or 0) for o in day_orders)
        day_units = sum(float(o.actual_quantity or o.planned_quantity or 0) for o in day_orders)

        cost_trend.append({
            'date': current_date.isoformat(),
            'total_cost': day_cost,
            'units': day_units,
            'avg_cost': day_cost / day_units if day_units > 0 else 0
        })
        current_date += timedelta(days=1)

    recipes = Recipe.query.filter_by(is_active=True).order_by(Recipe.name).all()

    return render_template('production_reports/batch_costing.html',
                         batch_costs=batch_costs,
                         total_material_cost=total_material_cost,
                         total_labor_cost=total_labor_cost,
                         total_overhead=total_overhead,
                         total_cost=total_cost,
                         total_units=total_units,
                         avg_unit_cost=avg_unit_cost,
                         cost_trend=cost_trend,
                         recipes=recipes,
                         recipe_id=recipe_id,
                         from_date=from_date,
                         to_date=to_date,
                         location=location)


def calculate_batch_cost(order):
    """Calculate detailed cost breakdown for a production batch"""
    cost = {
        'materials': [],
        'material_cost': Decimal('0'),
        'labor_cost': Decimal('0'),
        'overhead_cost': Decimal('0'),
        'total_cost': Decimal('0'),
        'unit_cost': Decimal('0')
    }

    # Material costs from consumption records
    consumptions = ProductionMaterialConsumption.query.filter_by(
        production_order_id=order.id
    ).all()

    for c in consumptions:
        material_total = (c.quantity or Decimal('0')) * (c.unit_cost or Decimal('0'))
        cost['materials'].append({
            'material': c.raw_material,
            'quantity': c.quantity,
            'unit_cost': c.unit_cost,
            'total_cost': material_total
        })
        cost['material_cost'] += material_total

    # Labor cost (if recorded)
    cost['labor_cost'] = order.labor_cost or Decimal('0')

    # Overhead cost (percentage of material cost, default 10%)
    overhead_rate = Decimal('0.10')  # Can be made configurable
    cost['overhead_cost'] = cost['material_cost'] * overhead_rate

    # Total cost
    cost['total_cost'] = cost['material_cost'] + cost['labor_cost'] + cost['overhead_cost']

    # Unit cost
    units = Decimal(str(order.actual_quantity or order.planned_quantity or 1))
    cost['unit_cost'] = cost['total_cost'] / units if units > 0 else Decimal('0')

    return cost


@bp.route('/batch/<int:order_id>')
@login_required
@permission_required(Permissions.PRODUCTION_VIEW)
def batch_detail(order_id):
    """Detailed cost breakdown for a specific production batch"""
    order = ProductionOrder.query.get_or_404(order_id)
    cost_breakdown = calculate_batch_cost(order)
    material_variance = calculate_material_variance(order)

    return render_template('production_reports/batch_detail.html',
                         order=order,
                         cost_breakdown=cost_breakdown,
                         material_variance=material_variance)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@bp.route('/api/yield-summary')
@login_required
@permission_required(Permissions.PRODUCTION_VIEW)
def api_yield_summary():
    """API endpoint for yield variance summary"""
    location = get_current_location()
    days = request.args.get('days', 30, type=int)

    start_date = datetime.now() - timedelta(days=days)

    query = ProductionOrder.query.filter(
        ProductionOrder.status == 'completed',
        ProductionOrder.created_at >= start_date
    )

    if location and not current_user.is_global_admin:
        query = query.filter(ProductionOrder.location_id == location.id)

    orders = query.all()

    total_expected = sum(float(o.planned_quantity or 0) for o in orders)
    total_actual = sum(float(o.actual_quantity or o.planned_quantity or 0) for o in orders)

    variance = total_actual - total_expected
    variance_pct = (variance / total_expected * 100) if total_expected > 0 else 0

    return jsonify({
        'period_days': days,
        'total_batches': len(orders),
        'total_expected': total_expected,
        'total_actual': total_actual,
        'variance': variance,
        'variance_percentage': round(variance_pct, 2)
    })


@bp.route('/api/cost-summary')
@login_required
@permission_required(Permissions.PRODUCTION_VIEW)
def api_cost_summary():
    """API endpoint for batch costing summary"""
    location = get_current_location()
    days = request.args.get('days', 30, type=int)

    start_date = datetime.now() - timedelta(days=days)

    query = ProductionOrder.query.filter(
        ProductionOrder.status == 'completed',
        ProductionOrder.created_at >= start_date
    )

    if location and not current_user.is_global_admin:
        query = query.filter(ProductionOrder.location_id == location.id)

    orders = query.all()

    total_cost = sum(float(o.total_cost or 0) for o in orders)
    total_units = sum(float(o.actual_quantity or o.planned_quantity or 0) for o in orders)

    avg_cost = total_cost / total_units if total_units > 0 else 0

    return jsonify({
        'period_days': days,
        'total_batches': len(orders),
        'total_cost': total_cost,
        'total_units': total_units,
        'average_cost_per_unit': round(avg_cost, 2)
    })
