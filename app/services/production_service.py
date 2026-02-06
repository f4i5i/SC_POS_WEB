"""
Production Service
Handles attar and perfume production logic including:
- Material requirements calculation
- Availability checking
- Production execution with stock updates
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from sqlalchemy import func

from app.models import (
    db, Product, Recipe, RecipeIngredient, RawMaterial, RawMaterialStock,
    RawMaterialMovement, ProductionOrder, ProductionMaterialConsumption,
    LocationStock, Location, RawMaterialCategory
)

logger = logging.getLogger(__name__)


class ProductionService:
    """Service for managing production operations"""

    @staticmethod
    def generate_order_number() -> str:
        """Generate unique production order number"""
        today = datetime.now()
        prefix = f"PRD{today.strftime('%Y%m%d')}"

        # Find latest order number for today
        latest = ProductionOrder.query.filter(
            ProductionOrder.order_number.like(f"{prefix}%")
        ).order_by(ProductionOrder.order_number.desc()).first()

        if latest:
            try:
                last_num = int(latest.order_number[-4:])
                new_num = last_num + 1
            except ValueError:
                new_num = 1
        else:
            new_num = 1

        return f"{prefix}{new_num:04d}"

    @staticmethod
    def calculate_material_requirements(
        recipe_id: int,
        quantity: int
    ) -> Dict[str, any]:
        """
        Calculate all raw materials needed for production

        Args:
            recipe_id: The recipe to use
            quantity: Number of units to produce

        Returns:
            Dict with materials list and totals

        Example for 10 bottles of 50ml perfume (35% oil):
            - Total output: 500ml
            - Oil needed: 175ml (500 * 0.35)
            - Ethanol needed: 325ml (500 * 0.65)
            - Bottles: 10
        """
        recipe = Recipe.query.get(recipe_id)
        if not recipe:
            return {'error': 'Recipe not found', 'materials': []}

        materials = []
        total_ml = float(recipe.output_size_ml or 0) * quantity

        # For single_oil and blended attars, oil percentage is always 100%
        # Only perfumes have partial oil percentage (rest is ethanol)
        if recipe.recipe_type in ('single_oil', 'blended'):
            oil_percentage = 1.0  # 100% oil for attars
        else:
            oil_percentage = float(recipe.oil_percentage or 100) / 100

        # Calculate oil amount needed
        oil_amount_ml = total_ml * oil_percentage

        # For perfumes, calculate ethanol needed
        ethanol_amount_ml = 0
        if recipe.recipe_type == 'perfume':
            ethanol_amount_ml = total_ml * (1 - oil_percentage)

        # Count oil ingredients (non-packaging, non-ethanol)
        oil_ingredients = [
            ing for ing in recipe.ingredients
            if not ing.is_packaging and ing.raw_material and
               not (ing.raw_material.category and ing.raw_material.category.code == 'ETHANOL')
        ]
        is_single_oil = len(oil_ingredients) == 1

        # Process each ingredient
        for ingredient in recipe.ingredients:
            material = ingredient.raw_material
            if not material:
                continue

            # Determine type by material category (more reliable than is_packaging flag)
            mat_category = material.category.code if material.category else None

            if mat_category == 'BOTTLE' or (ingredient.is_packaging and mat_category != 'OIL'):
                # Bottles/packaging - one per unit produced
                required_qty = quantity
                unit = 'pcs'
            elif mat_category == 'ETHANOL':
                # Ethanol for perfumes
                required_qty = ethanol_amount_ml
                unit = 'ml'
            else:
                # Oil ingredients
                if recipe.recipe_type == 'single_oil' or is_single_oil:
                    # Single oil attar OR perfume with single oil - all oil is this ingredient
                    required_qty = oil_amount_ml
                else:
                    # Blended - calculate based on percentage
                    ing_percentage = float(ingredient.percentage or 0) / 100
                    required_qty = oil_amount_ml * ing_percentage
                unit = 'ml'

            # Determine display unit
            if mat_category == 'BOTTLE' or (ingredient.is_packaging and mat_category != 'OIL'):
                display_unit = 'pcs'
            elif mat_category in ('OIL', 'ETHANOL'):
                display_unit = 'ml'
            else:
                display_unit = material.unit or 'ml'

            is_pack = mat_category == 'BOTTLE' or (ingredient.is_packaging and mat_category != 'OIL')
            materials.append({
                'raw_material_id': material.id,
                'raw_material': material,
                'code': material.code,
                'name': material.name,
                'unit': display_unit,
                'quantity_required': round(required_qty, 4),
                'is_packaging': is_pack,
                'percentage': float(ingredient.percentage or 0) if not is_pack else None
            })

        # Add ethanol if perfume and not already in ingredients
        if recipe.recipe_type == 'perfume' and ethanol_amount_ml > 0:
            ethanol_in_recipe = any(
                m['raw_material'].category and m['raw_material'].category.code == 'ETHANOL'
                for m in materials
            )
            if not ethanol_in_recipe:
                # Find ethanol material
                ethanol_cat = RawMaterialCategory.query.filter_by(code='ETHANOL').first()
                if ethanol_cat:
                    ethanol = RawMaterial.query.filter_by(category_id=ethanol_cat.id).first()
                    if ethanol:
                        materials.append({
                            'raw_material_id': ethanol.id,
                            'raw_material': ethanol,
                            'code': ethanol.code,
                            'name': ethanol.name,
                            'unit': ethanol.unit,
                            'quantity_required': round(ethanol_amount_ml, 4),
                            'is_packaging': False,
                            'percentage': None
                        })

        return {
            'recipe': recipe,
            'quantity': quantity,
            'total_output_ml': total_ml,
            'oil_amount_ml': oil_amount_ml,
            'ethanol_amount_ml': ethanol_amount_ml,
            'materials': materials
        }

    @staticmethod
    def check_material_availability(
        recipe_id: int,
        quantity: int,
        location_id: int
    ) -> Dict[str, any]:
        """
        Check if all materials are available at location

        Returns:
            Dict with availability status and details per material
        """
        requirements = ProductionService.calculate_material_requirements(recipe_id, quantity)

        if 'error' in requirements:
            return requirements

        location = Location.query.get(location_id)
        if not location:
            return {'error': 'Location not found', 'materials': []}

        # Check production constraints
        recipe = requirements['recipe']
        if not recipe.can_produce_at_warehouse and location.location_type == 'warehouse':
            return {'error': 'This recipe cannot be produced at warehouse', 'materials': []}
        if not recipe.can_produce_at_kiosk and location.location_type == 'kiosk':
            return {'error': 'This recipe can only be produced at warehouse', 'materials': []}

        availability = []
        all_available = True

        for material in requirements['materials']:
            stock = RawMaterialStock.query.filter_by(
                raw_material_id=material['raw_material_id'],
                location_id=location_id
            ).first()

            available_qty = float(stock.available_quantity) if stock else 0
            required_qty = material['quantity_required']
            is_available = available_qty >= required_qty

            if not is_available:
                all_available = False

            availability.append({
                **material,
                'available_quantity': available_qty,
                'is_available': is_available,
                'shortage': max(0, required_qty - available_qty)
            })

        return {
            'location': location,
            'recipe': recipe,
            'quantity': quantity,
            'all_available': all_available,
            'materials': availability
        }

    @staticmethod
    def create_production_order(
        recipe_id: int,
        quantity: int,
        location_id: int,
        user_id: int,
        priority: str = 'normal',
        due_date=None,
        notes: str = None,
        auto_submit: bool = False
    ) -> Tuple[Optional[ProductionOrder], Optional[str]]:
        """
        Create a new production order

        Returns:
            Tuple of (ProductionOrder, error_message)
        """
        try:
            recipe = Recipe.query.get(recipe_id)
            if not recipe:
                return None, 'Recipe not found'

            if not recipe.product_id:
                return None, 'Recipe has no output product defined'

            location = Location.query.get(location_id)
            if not location:
                return None, 'Location not found'

            # Check production constraints based on recipe flags
            if location.location_type == 'kiosk' and not recipe.can_produce_at_kiosk:
                return None, 'This recipe cannot be produced at kiosk'
            if location.location_type == 'warehouse' and not recipe.can_produce_at_warehouse:
                return None, 'This recipe cannot be produced at warehouse'

            # Create order
            order = ProductionOrder(
                order_number=ProductionService.generate_order_number(),
                recipe_id=recipe_id,
                product_id=recipe.product_id,
                location_id=location_id,
                quantity_ordered=quantity,
                status='draft',
                priority=priority,
                due_date=due_date,
                notes=notes,
                requested_by=user_id,
                requested_at=datetime.utcnow() if auto_submit else None
            )

            if auto_submit:
                order.status = 'pending'

            db.session.add(order)
            db.session.commit()

            logger.info(f"Production order {order.order_number} created")
            return order, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating production order: {e}")
            return None, str(e)

    @staticmethod
    def submit_order(order_id: int) -> Tuple[bool, Optional[str]]:
        """Submit draft order for approval"""
        try:
            order = ProductionOrder.query.get(order_id)
            if not order:
                return False, 'Order not found'

            if order.status != 'draft':
                return False, f'Order cannot be submitted (status: {order.status})'

            order.status = 'pending'
            order.requested_at = datetime.utcnow()
            db.session.commit()

            return True, None

        except Exception as e:
            db.session.rollback()
            return False, str(e)

    @staticmethod
    def approve_order(
        order_id: int,
        user_id: int
    ) -> Tuple[bool, Optional[str]]:
        """Approve a pending production order"""
        try:
            order = ProductionOrder.query.get(order_id)
            if not order:
                return False, 'Order not found'

            if not order.can_approve:
                return False, f'Order cannot be approved (status: {order.status})'

            # Check material availability
            availability = ProductionService.check_material_availability(
                order.recipe_id, order.quantity_ordered, order.location_id
            )

            if 'error' in availability:
                return False, availability['error']

            if not availability['all_available']:
                shortages = [
                    f"{m['name']}: need {m['quantity_required']}, have {m['available_quantity']}"
                    for m in availability['materials'] if not m['is_available']
                ]
                return False, f"Insufficient materials: {'; '.join(shortages)}"

            # Reserve materials
            for material in availability['materials']:
                stock = RawMaterialStock.query.filter_by(
                    raw_material_id=material['raw_material_id'],
                    location_id=order.location_id
                ).first()

                if stock:
                    stock.reserved_quantity = float(stock.reserved_quantity or 0) + material['quantity_required']

            order.status = 'approved'
            order.approved_at = datetime.utcnow()
            order.approved_by = user_id
            db.session.commit()

            logger.info(f"Production order {order.order_number} approved")
            return True, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error approving order: {e}")
            return False, str(e)

    @staticmethod
    def reject_order(
        order_id: int,
        user_id: int,
        reason: str
    ) -> Tuple[bool, Optional[str]]:
        """Reject a pending production order"""
        try:
            order = ProductionOrder.query.get(order_id)
            if not order:
                return False, 'Order not found'

            if not order.can_approve:
                return False, f'Order cannot be rejected (status: {order.status})'

            order.status = 'rejected'
            order.approved_by = user_id
            order.approved_at = datetime.utcnow()
            order.rejection_reason = reason
            db.session.commit()

            logger.info(f"Production order {order.order_number} rejected")
            return True, None

        except Exception as e:
            db.session.rollback()
            return False, str(e)

    @staticmethod
    def start_production(
        order_id: int,
        user_id: int
    ) -> Tuple[bool, Optional[str]]:
        """Start production (move from approved to in_progress)"""
        try:
            order = ProductionOrder.query.get(order_id)
            if not order:
                return False, 'Order not found'

            if not order.can_start:
                return False, f'Production cannot be started (status: {order.status})'

            order.status = 'in_progress'
            order.started_at = datetime.utcnow()
            order.produced_by = user_id
            db.session.commit()

            logger.info(f"Production started: {order.order_number}")
            return True, None

        except Exception as e:
            db.session.rollback()
            return False, str(e)

    @staticmethod
    def execute_production(
        order_id: int,
        user_id: int,
        quantity_produced: int = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Complete production: deduct raw materials, add finished products

        Args:
            order_id: The production order to complete
            user_id: User executing the production
            quantity_produced: Actual quantity produced (defaults to ordered qty)
        """
        try:
            order = ProductionOrder.query.get(order_id)
            if not order:
                return False, 'Order not found'

            if not order.can_complete:
                return False, f'Production cannot be completed (status: {order.status})'

            qty_produced = quantity_produced or order.quantity_ordered

            # Calculate materials based on actual quantity produced
            requirements = ProductionService.calculate_material_requirements(
                order.recipe_id, qty_produced
            )

            if 'error' in requirements:
                return False, requirements['error']

            # Deduct raw materials
            for material in requirements['materials']:
                raw_mat_id = material['raw_material_id']
                qty_required = Decimal(str(material['quantity_required']))

                # Get or create stock record
                stock = RawMaterialStock.query.filter_by(
                    raw_material_id=raw_mat_id,
                    location_id=order.location_id
                ).first()

                if not stock:
                    return False, f"No stock record for {material['name']} at this location"

                # Check total quantity (includes reserved for this order)
                if float(stock.quantity or 0) < float(qty_required):
                    return False, f"Insufficient {material['name']}: need {qty_required}, have {stock.quantity}"

                # Deduct from stock
                stock.quantity = Decimal(str(stock.quantity)) - qty_required

                # Release reserved quantity
                reserved_to_release = min(
                    float(stock.reserved_quantity or 0),
                    float(qty_required)
                )
                stock.reserved_quantity = Decimal(str(stock.reserved_quantity or 0)) - Decimal(str(reserved_to_release))
                stock.last_movement_at = datetime.utcnow()

                # Create movement record
                movement = RawMaterialMovement(
                    raw_material_id=raw_mat_id,
                    location_id=order.location_id,
                    user_id=user_id,
                    movement_type='production_consumption',
                    quantity=-qty_required,  # Negative for consumption
                    reference=order.order_number,
                    production_order_id=order.id,
                    notes=f"Production of {qty_produced} units"
                )
                db.session.add(movement)

                # Record consumption
                consumption = ProductionMaterialConsumption(
                    production_order_id=order.id,
                    raw_material_id=raw_mat_id,
                    quantity_required=qty_required,
                    quantity_consumed=qty_required,
                    unit=material['unit']
                )
                db.session.add(consumption)

            # Add finished products to location stock
            location_stock = LocationStock.query.filter_by(
                product_id=order.product_id,
                location_id=order.location_id
            ).first()

            if not location_stock:
                location_stock = LocationStock(
                    product_id=order.product_id,
                    location_id=order.location_id,
                    quantity=0
                )
                db.session.add(location_stock)

            location_stock.quantity += qty_produced
            location_stock.last_movement_at = datetime.utcnow()

            # Update global product stock
            product = Product.query.get(order.product_id)
            if product:
                product.quantity = (product.quantity or 0) + qty_produced

            # Update order
            order.status = 'completed'
            order.quantity_produced = qty_produced
            order.completed_at = datetime.utcnow()
            order.produced_by = user_id

            db.session.commit()

            logger.info(f"Production completed: {order.order_number}, produced {qty_produced} units")
            return True, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error executing production: {e}")
            return False, str(e)

    @staticmethod
    def cancel_order(
        order_id: int,
        user_id: int,
        reason: str = None
    ) -> Tuple[bool, Optional[str]]:
        """Cancel a production order and release reserved materials"""
        try:
            order = ProductionOrder.query.get(order_id)
            if not order:
                return False, 'Order not found'

            if not order.can_cancel:
                return False, f'Order cannot be cancelled (status: {order.status})'

            # Release reserved materials if order was approved
            if order.status == 'approved':
                requirements = ProductionService.calculate_material_requirements(
                    order.recipe_id, order.quantity_ordered
                )

                for material in requirements.get('materials', []):
                    stock = RawMaterialStock.query.filter_by(
                        raw_material_id=material['raw_material_id'],
                        location_id=order.location_id
                    ).first()

                    if stock and stock.reserved_quantity:
                        release_qty = min(
                            float(stock.reserved_quantity),
                            material['quantity_required']
                        )
                        stock.reserved_quantity = Decimal(str(stock.reserved_quantity)) - Decimal(str(release_qty))

            order.status = 'cancelled'
            order.rejection_reason = reason or 'Cancelled by user'
            db.session.commit()

            logger.info(f"Production order {order.order_number} cancelled")
            return True, None

        except Exception as e:
            db.session.rollback()
            return False, str(e)

    @staticmethod
    def get_production_stats(location_id: int = None) -> Dict:
        """Get production statistics"""
        query = ProductionOrder.query

        if location_id:
            query = query.filter_by(location_id=location_id)

        # Count by status
        status_counts = db.session.query(
            ProductionOrder.status,
            func.count(ProductionOrder.id)
        )
        if location_id:
            status_counts = status_counts.filter(ProductionOrder.location_id == location_id)
        status_counts = dict(status_counts.group_by(ProductionOrder.status).all())

        # Recent completed orders
        recent_completed = query.filter_by(status='completed').order_by(
            ProductionOrder.completed_at.desc()
        ).limit(5).all()

        # Total produced this month
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_total = db.session.query(func.sum(ProductionOrder.quantity_produced)).filter(
            ProductionOrder.status == 'completed',
            ProductionOrder.completed_at >= month_start
        )
        if location_id:
            month_total = month_total.filter(ProductionOrder.location_id == location_id)
        month_total = month_total.scalar() or 0

        return {
            'status_counts': status_counts,
            'pending_count': status_counts.get('pending', 0),
            'in_progress_count': status_counts.get('in_progress', 0),
            'completed_count': status_counts.get('completed', 0),
            'recent_completed': recent_completed,
            'month_total_produced': month_total
        }

    @staticmethod
    def get_low_stock_materials(location_id: int = None) -> List[Dict]:
        """Get raw materials that are below reorder level"""
        query = RawMaterialStock.query

        if location_id:
            query = query.filter_by(location_id=location_id)

        low_stock = []
        for stock in query.all():
            if stock.is_low_stock:
                low_stock.append({
                    'material': stock.raw_material,
                    'location': stock.location,
                    'quantity': float(stock.quantity),
                    'available': stock.available_quantity,
                    'reorder_level': float(stock.reorder_level or stock.raw_material.reorder_level or 0)
                })

        return low_stock
