"""
Production Routes

Handles attar and perfume production:
- Raw materials management (oils, ethanol, bottles)
- Recipe/formula management
- Production orders workflow
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from decimal import Decimal

from app.models import (
    db, Product, Location, LocationStock, RawMaterial, RawMaterialCategory,
    RawMaterialStock, RawMaterialMovement, Recipe, RecipeIngredient,
    ProductionOrder, ProductionMaterialConsumption
)
from app.utils.permissions import permission_required, Permissions
from app.utils.location_context import get_current_location

from app.services.production_service import ProductionService

bp = Blueprint('production', __name__, url_prefix='/production')


def init_raw_material_categories():
    """Initialize default raw material categories if they don't exist"""
    default_categories = [
        {'code': 'OIL', 'name': 'Base Oils', 'unit': 'grams', 'description': 'Essential and fragrance oils'},
        {'code': 'ETHANOL', 'name': 'Ethanol/Alcohol', 'unit': 'ml', 'description': 'Perfume grade ethanol'},
        {'code': 'BOTTLE', 'name': 'Bottles & Packaging', 'unit': 'pieces', 'description': 'Bottles, caps, and packaging'},
    ]

    for cat_data in default_categories:
        existing = RawMaterialCategory.query.filter_by(code=cat_data['code']).first()
        if not existing:
            category = RawMaterialCategory(
                code=cat_data['code'],
                name=cat_data['name'],
                unit=cat_data['unit'],
                description=cat_data['description'],
                is_active=True
            )
            db.session.add(category)

    db.session.commit()


# ============================================================
# Dashboard
# ============================================================

@bp.route('/')
@login_required
@permission_required(Permissions.PRODUCTION_VIEW)
def index():
    """Production dashboard"""
    location = get_current_location()
    location_id = location.id if location else None

    stats = ProductionService.get_production_stats(location_id)
    low_stock = ProductionService.get_low_stock_materials(location_id)

    # Get recent orders
    query = ProductionOrder.query
    if location_id:
        query = query.filter_by(location_id=location_id)

    recent_orders = query.order_by(ProductionOrder.created_at.desc()).limit(10).all()

    return render_template('production/index.html',
                           stats=stats,
                           low_stock=low_stock[:5],
                           recent_orders=recent_orders,
                           current_location=location)


# ============================================================
# Raw Materials
# ============================================================

@bp.route('/raw-materials')
@login_required
@permission_required(Permissions.RAW_MATERIAL_VIEW)
def raw_materials():
    """List all raw materials"""
    location = get_current_location()

    # Initialize default categories if none exist
    if RawMaterialCategory.query.count() == 0:
        init_raw_material_categories()

    categories = RawMaterialCategory.query.filter_by(is_active=True).all()
    category_filter = request.args.get('category')

    query = RawMaterial.query.filter_by(is_active=True)
    if category_filter:
        query = query.filter_by(category_id=category_filter)

    materials = query.order_by(RawMaterial.name).all()

    # Get stock levels for current location
    stock_levels = {}
    if location:
        for material in materials:
            stock = RawMaterialStock.query.filter_by(
                raw_material_id=material.id,
                location_id=location.id
            ).first()
            stock_levels[material.id] = {
                'quantity': float(stock.quantity) if stock else 0,
                'available': stock.available_quantity if stock else 0,
                'is_low': stock.is_low_stock if stock else True
            }

    return render_template('production/raw_materials/index.html',
                           materials=materials,
                           categories=categories,
                           stock_levels=stock_levels,
                           current_location=location,
                           current_category=category_filter)


@bp.route('/raw-materials/add', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.RAW_MATERIAL_CREATE)
def add_raw_material():
    """Add new raw material"""
    if request.method == 'POST':
        try:
            code = request.form.get('code', '').strip().upper()
            name = request.form.get('name', '').strip()
            category_id = request.form.get('category_id', type=int)
            cost_per_unit = request.form.get('cost_per_unit', type=float, default=0)
            reorder_level = request.form.get('reorder_level', type=float, default=100)
            bottle_size_ml = request.form.get('bottle_size_ml', type=float)

            if not code or not name or not category_id:
                flash('Please fill all required fields.', 'danger')
                return redirect(url_for('production.add_raw_material'))

            # Check if code exists
            if RawMaterial.query.filter_by(code=code).first():
                flash('A material with this code already exists.', 'danger')
                return redirect(url_for('production.add_raw_material'))

            material = RawMaterial(
                code=code,
                name=name,
                category_id=category_id,
                cost_per_unit=cost_per_unit,
                reorder_level=reorder_level,
                bottle_size_ml=bottle_size_ml if bottle_size_ml else None
            )
            db.session.add(material)
            db.session.commit()

            flash(f'Raw material "{name}" added successfully.', 'success')
            return redirect(url_for('production.raw_materials'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error adding material: {str(e)}', 'danger')

    # Initialize default categories if none exist
    if RawMaterialCategory.query.count() == 0:
        init_raw_material_categories()

    categories = RawMaterialCategory.query.filter_by(is_active=True).all()
    return render_template('production/raw_materials/add.html', categories=categories)


@bp.route('/raw-materials/<int:id>')
@login_required
@permission_required(Permissions.RAW_MATERIAL_VIEW)
def view_raw_material(id):
    """View raw material details"""
    material = RawMaterial.query.get_or_404(id)
    location = get_current_location()

    # For global admin, get all locations for stock adjustment
    available_locations = None
    if current_user.is_global_admin:
        available_locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
        # Default to warehouse if no location assigned
        if not location:
            location = Location.query.filter_by(location_type='warehouse', is_active=True).first()

    # Get stock at all locations
    stock_by_location = RawMaterialStock.query.filter_by(
        raw_material_id=id
    ).all()

    # Get recent movements
    movements = RawMaterialMovement.query.filter_by(
        raw_material_id=id
    ).order_by(RawMaterialMovement.timestamp.desc()).limit(20).all()

    return render_template('production/raw_materials/view.html',
                           material=material,
                           stock_by_location=stock_by_location,
                           movements=movements,
                           current_location=location,
                           available_locations=available_locations,
                           is_global_admin=current_user.is_global_admin)


@bp.route('/raw-materials/<int:id>/adjust', methods=['POST'])
@login_required
@permission_required(Permissions.RAW_MATERIAL_ADJUST)
def adjust_raw_material(id):
    """Adjust raw material stock"""
    material = RawMaterial.query.get_or_404(id)
    location = get_current_location()

    # For global admin, allow selecting location or default to warehouse
    if not location and current_user.is_global_admin:
        location_id = request.form.get('location_id', type=int)
        if location_id:
            location = Location.query.get(location_id)
        else:
            location = Location.query.filter_by(location_type='warehouse', is_active=True).first()

    if not location:
        flash('You must be assigned to a location.', 'danger')
        return redirect(url_for('production.view_raw_material', id=id))

    try:
        adjustment = request.form.get('adjustment', type=float)
        adjustment_type = request.form.get('type', 'adjustment')
        notes = request.form.get('notes', '').strip()

        if not adjustment:
            flash('Please enter an adjustment amount.', 'danger')
            return redirect(url_for('production.view_raw_material', id=id))

        # Get or create stock record
        stock = RawMaterialStock.query.filter_by(
            raw_material_id=id,
            location_id=location.id
        ).first()

        if not stock:
            stock = RawMaterialStock(
                raw_material_id=id,
                location_id=location.id,
                quantity=0
            )
            db.session.add(stock)

        # Update stock
        stock.quantity = Decimal(str(stock.quantity or 0)) + Decimal(str(adjustment))
        stock.last_movement_at = datetime.utcnow()

        # Create movement record
        movement = RawMaterialMovement(
            raw_material_id=id,
            location_id=location.id,
            user_id=current_user.id,
            movement_type=adjustment_type,
            quantity=adjustment,
            notes=notes
        )
        db.session.add(movement)
        db.session.commit()

        flash(f'Stock adjusted by {adjustment} {material.unit}.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('production.view_raw_material', id=id))


@bp.route('/raw-materials/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.RAW_MATERIAL_EDIT)
def edit_raw_material(id):
    """Edit raw material"""
    material = RawMaterial.query.get_or_404(id)

    if request.method == 'POST':
        try:
            material.name = request.form.get('name', '').strip()
            material.category_id = request.form.get('category_id', type=int)
            material.cost_per_unit = request.form.get('cost_per_unit', type=float, default=0)
            material.reorder_level = request.form.get('reorder_level', type=float, default=100)
            material.bottle_size_ml = request.form.get('bottle_size_ml', type=float) or None

            if not material.name or not material.category_id:
                flash('Please fill all required fields.', 'danger')
                return redirect(url_for('production.edit_raw_material', id=id))

            db.session.commit()
            flash(f'Raw material "{material.name}" updated successfully.', 'success')
            return redirect(url_for('production.view_raw_material', id=id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating material: {str(e)}', 'danger')

    categories = RawMaterialCategory.query.filter_by(is_active=True).all()
    return render_template('production/raw_materials/edit.html',
                           material=material,
                           categories=categories)


@bp.route('/raw-materials/<int:id>/delete', methods=['POST'])
@login_required
@permission_required(Permissions.RAW_MATERIAL_DELETE)
def delete_raw_material(id):
    """Delete raw material"""
    material = RawMaterial.query.get_or_404(id)

    try:
        # Check if material is used in any recipes
        if material.recipe_ingredients:
            flash('Cannot delete material that is used in recipes.', 'danger')
            return redirect(url_for('production.view_raw_material', id=id))

        # Check if there is stock
        total_stock = sum(s.quantity for s in material.stock_levels)
        if total_stock > 0:
            flash('Cannot delete material with existing stock. Please adjust stock to 0 first.', 'danger')
            return redirect(url_for('production.view_raw_material', id=id))

        db.session.delete(material)
        db.session.commit()
        flash(f'Raw material "{material.name}" deleted successfully.', 'success')
        return redirect(url_for('production.raw_materials'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting material: {str(e)}', 'danger')
        return redirect(url_for('production.view_raw_material', id=id))


# ============================================================
# Recipes
# ============================================================

@bp.route('/recipes')
@login_required
@permission_required(Permissions.RECIPE_VIEW)
def recipes():
    """List all recipes"""
    recipe_type = request.args.get('type')

    query = Recipe.query.filter_by(is_active=True)
    if recipe_type:
        query = query.filter_by(recipe_type=recipe_type)

    recipes = query.order_by(Recipe.name).all()

    return render_template('production/recipes/index.html',
                           recipes=recipes,
                           current_type=recipe_type)


@bp.route('/recipes/add', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.RECIPE_CREATE)
def add_recipe():
    """Create new recipe"""
    if request.method == 'POST':
        try:
            code = request.form.get('code', '').strip().upper()
            name = request.form.get('name', '').strip()
            recipe_type = request.form.get('recipe_type')
            product_id = request.form.get('product_id', type=int)
            output_size_ml = request.form.get('output_size_ml', type=float)
            oil_percentage = request.form.get('oil_percentage', type=float, default=100)
            can_produce_at_kiosk = request.form.get('can_produce_at_kiosk') == 'on'
            description = request.form.get('description', '').strip()

            if not code or not name or not recipe_type:
                flash('Please fill all required fields.', 'danger')
                return redirect(url_for('production.add_recipe'))

            # Check if code exists
            if Recipe.query.filter_by(code=code).first():
                flash('A recipe with this code already exists.', 'danger')
                return redirect(url_for('production.add_recipe'))

            # For attars (single_oil, blended), oil percentage is always 100%
            # Only perfumes have partial oil percentage
            if recipe_type in ('single_oil', 'blended'):
                oil_percentage = 100.0
            elif recipe_type == 'perfume' and not oil_percentage:
                oil_percentage = 35.0

            recipe = Recipe(
                code=code,
                name=name,
                recipe_type=recipe_type,
                product_id=product_id if product_id else None,
                output_size_ml=output_size_ml,
                oil_percentage=oil_percentage,
                can_produce_at_warehouse=True,
                can_produce_at_kiosk=can_produce_at_kiosk,
                description=description,
                created_by=current_user.id
            )
            db.session.add(recipe)
            db.session.flush()

            # Add ingredients
            ingredient_ids = request.form.getlist('ingredient_id[]')
            percentages = request.form.getlist('percentage[]')
            is_packaging_list = request.form.getlist('is_packaging[]')

            for i, mat_id in enumerate(ingredient_ids):
                if mat_id:
                    # Auto-detect packaging from material category
                    material = RawMaterial.query.get(int(mat_id))
                    mat_cat = material.category.code if material and material.category else None
                    is_pack = mat_cat == 'BOTTLE'
                    pct = float(percentages[i]) if i < len(percentages) and percentages[i] else None

                    ingredient = RecipeIngredient(
                        recipe_id=recipe.id,
                        raw_material_id=int(mat_id),
                        percentage=pct if not is_pack else None,
                        is_packaging=is_pack
                    )
                    db.session.add(ingredient)

            db.session.commit()
            flash(f'Recipe "{name}" created successfully.', 'success')
            return redirect(url_for('production.view_recipe', id=recipe.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating recipe: {str(e)}', 'danger')

    # Get data for form - show all active products as potential recipe outputs
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    oils = RawMaterial.query.join(RawMaterialCategory).filter(
        RawMaterialCategory.code == 'OIL'
    ).order_by(RawMaterial.name).all()
    bottles = RawMaterial.query.join(RawMaterialCategory).filter(
        RawMaterialCategory.code == 'BOTTLE'
    ).order_by(RawMaterial.bottle_size_ml).all()

    return render_template('production/recipes/add.html',
                           products=products,
                           oils=oils,
                           bottles=bottles)


@bp.route('/recipes/<int:id>')
@login_required
@permission_required(Permissions.RECIPE_VIEW)
def view_recipe(id):
    """View recipe details"""
    recipe = Recipe.query.get_or_404(id)
    location = get_current_location()

    # Calculate materials for sample quantity
    sample_qty = 10
    requirements = ProductionService.calculate_material_requirements(id, sample_qty)

    # Check availability if at a location
    availability = None
    if location:
        availability = ProductionService.check_material_availability(id, sample_qty, location.id)

    return render_template('production/recipes/view.html',
                           recipe=recipe,
                           requirements=requirements,
                           availability=availability,
                           sample_qty=sample_qty,
                           current_location=location)


@bp.route('/recipes/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.RECIPE_EDIT)
def edit_recipe(id):
    """Edit existing recipe"""
    recipe = Recipe.query.get_or_404(id)

    if request.method == 'POST':
        try:
            recipe.name = request.form.get('name', '').strip()
            recipe.recipe_type = request.form.get('recipe_type')
            recipe.product_id = request.form.get('product_id', type=int) or None
            recipe.output_size_ml = request.form.get('output_size_ml', type=float)
            recipe.can_produce_at_kiosk = request.form.get('can_produce_at_kiosk') == 'on'
            recipe.description = request.form.get('description', '').strip()

            # For attars (single_oil, blended), oil percentage is always 100%
            # Only perfumes have partial oil percentage
            if recipe.recipe_type in ('single_oil', 'blended'):
                recipe.oil_percentage = 100.0
            else:
                recipe.oil_percentage = request.form.get('oil_percentage', type=float, default=35)

            # Delete old ingredients
            RecipeIngredient.query.filter_by(recipe_id=recipe.id).delete()

            # Add new ingredients
            ingredient_ids = request.form.getlist('ingredient_id[]')
            percentages = request.form.getlist('percentage[]')
            is_packaging_list = request.form.getlist('is_packaging[]')

            for i, mat_id in enumerate(ingredient_ids):
                if mat_id:
                    # Auto-detect packaging from material category
                    material = RawMaterial.query.get(int(mat_id))
                    mat_cat = material.category.code if material and material.category else None
                    is_pack = mat_cat == 'BOTTLE'
                    pct = float(percentages[i]) if i < len(percentages) and percentages[i] else None

                    ingredient = RecipeIngredient(
                        recipe_id=recipe.id,
                        raw_material_id=int(mat_id),
                        percentage=pct if not is_pack else None,
                        is_packaging=is_pack
                    )
                    db.session.add(ingredient)

            db.session.commit()
            flash(f'Recipe "{recipe.name}" updated successfully.', 'success')
            return redirect(url_for('production.view_recipe', id=recipe.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating recipe: {str(e)}', 'danger')

    # Get data for form - show all active products as potential recipe outputs
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    oils = RawMaterial.query.join(RawMaterialCategory).filter(
        RawMaterialCategory.code == 'OIL'
    ).order_by(RawMaterial.name).all()
    bottles = RawMaterial.query.join(RawMaterialCategory).filter(
        RawMaterialCategory.code == 'BOTTLE'
    ).order_by(RawMaterial.bottle_size_ml).all()

    return render_template('production/recipes/edit.html',
                           recipe=recipe,
                           products=products,
                           oils=oils,
                           bottles=bottles)


@bp.route('/recipes/<int:id>/delete', methods=['POST'])
@login_required
@permission_required(Permissions.RECIPE_DELETE)
def delete_recipe(id):
    """Delete a recipe"""
    try:
        recipe = Recipe.query.get_or_404(id)

        # Check if recipe has production orders
        if recipe.production_orders.count() > 0:
            flash('Cannot delete recipe with existing production orders.', 'danger')
            return redirect(url_for('production.view_recipe', id=id))

        # Delete ingredients first
        RecipeIngredient.query.filter_by(recipe_id=id).delete()

        # Delete recipe
        db.session.delete(recipe)
        db.session.commit()

        flash(f'Recipe "{recipe.name}" deleted successfully.', 'success')
        return redirect(url_for('production.recipes'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting recipe: {str(e)}', 'danger')
        return redirect(url_for('production.view_recipe', id=id))


# ============================================================
# Production Orders
# ============================================================

@bp.route('/orders')
@login_required
@permission_required(Permissions.PRODUCTION_VIEW)
def orders():
    """List production orders"""
    location = get_current_location()
    status_filter = request.args.get('status')

    query = ProductionOrder.query

    if location and not current_user.is_global_admin:
        query = query.filter_by(location_id=location.id)

    if status_filter:
        query = query.filter_by(status=status_filter)

    orders = query.order_by(ProductionOrder.created_at.desc()).all()

    return render_template('production/orders/index.html',
                           orders=orders,
                           current_location=location,
                           current_status=status_filter)


@bp.route('/orders/create', methods=['GET', 'POST'])
@login_required
@permission_required(Permissions.PRODUCTION_CREATE)
def create_order():
    """Create new production order"""
    location = get_current_location()

    # For global admin without assigned location, allow selecting location or default to warehouse
    if not location and current_user.is_global_admin:
        # Check if admin selected a specific location
        selected_location_id = request.args.get('location_id', type=int) or request.form.get('location_id', type=int)
        if selected_location_id:
            location = Location.query.get(selected_location_id)
        else:
            # Default to warehouse for global admin
            location = Location.query.filter_by(location_type='warehouse', is_active=True).first()

    if not location:
        flash('You must be assigned to a location to create production orders.', 'warning')
        return redirect(url_for('production.orders'))

    if request.method == 'POST':
        try:
            recipe_id = request.form.get('recipe_id', type=int)
            quantity = request.form.get('quantity', type=int)
            priority = request.form.get('priority', 'normal')
            due_date_str = request.form.get('due_date')
            notes = request.form.get('notes', '').strip()

            if not recipe_id or not quantity:
                flash('Please select a recipe and quantity.', 'danger')
                return redirect(url_for('production.create_order'))

            due_date = None
            if due_date_str:
                due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()

            # Check availability first
            availability = ProductionService.check_material_availability(
                recipe_id, quantity, location.id
            )

            if 'error' in availability:
                flash(availability['error'], 'danger')
                return redirect(url_for('production.create_order'))

            if not availability['all_available']:
                shortages = [
                    f"{m['name']}: need {m['quantity_required']:.2f}, have {m['available_quantity']:.2f}"
                    for m in availability['materials'] if not m['is_available']
                ]
                flash(f"Insufficient materials: {', '.join(shortages)}", 'warning')
                # Still allow creation but warn

            order, error = ProductionService.create_production_order(
                recipe_id=recipe_id,
                quantity=quantity,
                location_id=location.id,
                user_id=current_user.id,
                priority=priority,
                due_date=due_date,
                notes=notes,
                auto_submit=True
            )

            if error:
                flash(f'Error: {error}', 'danger')
                return redirect(url_for('production.create_order'))

            flash(f'Production order {order.order_number} created.', 'success')
            return redirect(url_for('production.view_order', id=order.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')

    # Get recipes available at this location
    # Global admin at warehouse can see all recipes
    # Kiosk can only produce recipes marked as can_produce_at_kiosk
    recipes_query = Recipe.query.filter_by(is_active=True)
    if location.location_type == 'kiosk':
        recipes_query = recipes_query.filter_by(can_produce_at_kiosk=True)
    recipes = recipes_query.order_by(Recipe.name).all()

    # For global admin, get all locations they can produce at
    available_locations = None
    if current_user.is_global_admin:
        available_locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    return render_template('production/orders/create.html',
                           recipes=recipes,
                           current_location=location,
                           available_locations=available_locations,
                           is_global_admin=current_user.is_global_admin)


@bp.route('/orders/<int:id>')
@login_required
@permission_required(Permissions.PRODUCTION_VIEW)
def view_order(id):
    """View production order details"""
    order = ProductionOrder.query.get_or_404(id)

    # Calculate requirements
    requirements = ProductionService.calculate_material_requirements(
        order.recipe_id, order.quantity_ordered
    )

    # Check availability
    availability = ProductionService.check_material_availability(
        order.recipe_id, order.quantity_ordered, order.location_id
    )

    return render_template('production/orders/view.html',
                           order=order,
                           requirements=requirements,
                           availability=availability)


@bp.route('/orders/<int:id>/approve', methods=['POST'])
@login_required
@permission_required(Permissions.PRODUCTION_APPROVE)
def approve_order(id):
    """Approve a pending production order"""
    action = request.form.get('action')

    if action == 'approve':
        success, error = ProductionService.approve_order(id, current_user.id)
        if success:
            flash('Production order approved.', 'success')
        else:
            flash(f'Cannot approve: {error}', 'danger')

    elif action == 'reject':
        reason = request.form.get('reason', 'Rejected by approver')
        success, error = ProductionService.reject_order(id, current_user.id, reason)
        if success:
            flash('Production order rejected.', 'info')
        else:
            flash(f'Cannot reject: {error}', 'danger')

    return redirect(url_for('production.view_order', id=id))


@bp.route('/orders/<int:id>/start', methods=['POST'])
@login_required
@permission_required(Permissions.PRODUCTION_EXECUTE)
def start_order(id):
    """Start production"""
    success, error = ProductionService.start_production(id, current_user.id)

    if success:
        flash('Production started.', 'success')
    else:
        flash(f'Cannot start: {error}', 'danger')

    return redirect(url_for('production.view_order', id=id))


@bp.route('/orders/<int:id>/complete', methods=['POST'])
@login_required
@permission_required(Permissions.PRODUCTION_EXECUTE)
def complete_order(id):
    """Complete production - deduct materials, add products"""
    quantity_produced = request.form.get('quantity_produced', type=int)

    success, error = ProductionService.execute_production(
        id, current_user.id, quantity_produced
    )

    if success:
        flash('Production completed! Materials deducted and products added to inventory.', 'success')
    else:
        flash(f'Cannot complete: {error}', 'danger')

    return redirect(url_for('production.view_order', id=id))


@bp.route('/orders/<int:id>/cancel', methods=['POST'])
@login_required
@permission_required(Permissions.PRODUCTION_CREATE)
def cancel_order(id):
    """Cancel a production order"""
    reason = request.form.get('reason', '')

    success, error = ProductionService.cancel_order(id, current_user.id, reason)

    if success:
        flash('Production order cancelled.', 'info')
    else:
        flash(f'Cannot cancel: {error}', 'danger')

    return redirect(url_for('production.view_order', id=id))


# ============================================================
# API Endpoints
# ============================================================

@bp.route('/api/calculate-requirements')
@login_required
def api_calculate_requirements():
    """API: Calculate material requirements for a recipe"""
    recipe_id = request.args.get('recipe_id', type=int)
    quantity = request.args.get('quantity', type=int, default=1)

    if not recipe_id:
        return jsonify({'error': 'Recipe ID required'}), 400

    requirements = ProductionService.calculate_material_requirements(recipe_id, quantity)

    if 'error' in requirements:
        return jsonify(requirements), 400

    # Format for JSON
    materials = []
    for m in requirements.get('materials', []):
        materials.append({
            'id': m['raw_material_id'],
            'code': m['code'],
            'name': m['name'],
            'unit': m['unit'],
            'quantity_required': m['quantity_required'],
            'is_packaging': m['is_packaging']
        })

    return jsonify({
        'quantity': quantity,
        'total_output_ml': requirements.get('total_output_ml', 0),
        'oil_amount_ml': requirements.get('oil_amount_ml', 0),
        'ethanol_amount_ml': requirements.get('ethanol_amount_ml', 0),
        'materials': materials
    })


@bp.route('/api/check-availability')
@login_required
def api_check_availability():
    """API: Check material availability for production"""
    recipe_id = request.args.get('recipe_id', type=int)
    quantity = request.args.get('quantity', type=int, default=1)
    location_id = request.args.get('location_id', type=int)

    if not recipe_id:
        return jsonify({'error': 'Recipe ID required'}), 400

    location = get_current_location()
    loc_id = location_id or (location.id if location else None)

    if not loc_id:
        return jsonify({'error': 'Location required'}), 400

    availability = ProductionService.check_material_availability(recipe_id, quantity, loc_id)

    if 'error' in availability:
        return jsonify(availability), 400

    materials = []
    for m in availability.get('materials', []):
        materials.append({
            'id': m['raw_material_id'],
            'name': m['name'],
            'unit': m['unit'],
            'quantity_required': m['quantity_required'],
            'available_quantity': m['available_quantity'],
            'is_available': m['is_available'],
            'shortage': m['shortage']
        })

    return jsonify({
        'all_available': availability['all_available'],
        'materials': materials
    })
