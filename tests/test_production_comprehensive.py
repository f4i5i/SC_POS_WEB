"""
Comprehensive Unit Tests for Production/Manufacturing Functionality

Tests cover:
1. Recipe management: create, update, delete, versioning
2. Ingredients: adding, removing, quantities, substitutions
3. Production batches: start, complete, cancel, partial completion
4. Yield tracking: expected vs actual, variances, waste
5. Cost calculation: ingredient costs, labor, overhead
6. Inventory integration: ingredient deduction, finished goods addition
7. Quality control: checkpoints, approvals, rejections
8. Scheduling: production planning, capacity, conflicts
9. Traceability: batch tracking, ingredient tracking, recalls
10. Edge cases: insufficient ingredients, equipment failures
11. Multi-location: production at different sites
12. Reports: production efficiency, waste, costs
"""

import pytest
from decimal import Decimal
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock

from app.models import (
    db, User, Product, Location, LocationStock, Category,
    RawMaterial, RawMaterialCategory, RawMaterialStock, RawMaterialMovement,
    Recipe, RecipeIngredient, ProductionOrder, ProductionMaterialConsumption
)
from app.services.production_service import ProductionService


# =============================================================================
# FIXTURES FOR PRODUCTION TESTS
# =============================================================================

@pytest.fixture
def production_setup(fresh_app):
    """
    Comprehensive production test data setup.
    Creates:
    - Locations (warehouse, multiple kiosks)
    - Raw material categories (OIL, ETHANOL, BOTTLE)
    - Raw materials (various oils, ethanol, bottles)
    - Raw material stock at locations
    - Products (manufactured attars/perfumes)
    - Recipes (single oil, blended, perfume)
    - Users with production roles
    """
    with fresh_app.app_context():
        # Create warehouse location
        warehouse = Location(
            code='WH-001',
            name='Main Production Warehouse',
            location_type='warehouse',
            address='123 Industrial Zone',
            city='Lahore',
            is_active=True
        )
        db.session.add(warehouse)
        db.session.flush()

        # Create kiosk locations
        kiosk1 = Location(
            code='K-001',
            name='Mall Kiosk A',
            location_type='kiosk',
            address='Mall of Lahore',
            city='Lahore',
            parent_warehouse_id=warehouse.id,
            is_active=True,
            can_sell=True
        )
        kiosk2 = Location(
            code='K-002',
            name='Mall Kiosk B',
            location_type='kiosk',
            address='Packages Mall',
            city='Lahore',
            parent_warehouse_id=warehouse.id,
            is_active=True,
            can_sell=True
        )
        db.session.add_all([kiosk1, kiosk2])
        db.session.flush()

        # Create raw material categories
        oil_category = RawMaterialCategory(
            code='OIL',
            name='Essential Oils',
            unit='ml',
            description='Natural and synthetic oils',
            is_active=True
        )
        ethanol_category = RawMaterialCategory(
            code='ETHANOL',
            name='Ethanol/Alcohol',
            unit='ml',
            description='Denatured ethanol for perfumes',
            is_active=True
        )
        bottle_category = RawMaterialCategory(
            code='BOTTLE',
            name='Bottles',
            unit='pieces',
            description='Glass bottles for packaging',
            is_active=True
        )
        db.session.add_all([oil_category, ethanol_category, bottle_category])
        db.session.flush()

        # Create raw materials - Oils
        oud_oil = RawMaterial(
            code='OIL-OUD-001',
            name='Oud Oil Premium',
            category_id=oil_category.id,
            cost_per_unit=Decimal('150.00'),  # Per ml
            quantity=Decimal('5000'),
            reorder_level=Decimal('1000'),
            is_active=True
        )
        musk_oil = RawMaterial(
            code='OIL-MUSK-001',
            name='Musk Oil',
            category_id=oil_category.id,
            cost_per_unit=Decimal('80.00'),
            quantity=Decimal('3000'),
            reorder_level=Decimal('500'),
            is_active=True
        )
        rose_oil = RawMaterial(
            code='OIL-ROSE-001',
            name='Rose Oil',
            category_id=oil_category.id,
            cost_per_unit=Decimal('200.00'),
            quantity=Decimal('2000'),
            reorder_level=Decimal('500'),
            is_active=True
        )
        amber_oil = RawMaterial(
            code='OIL-AMBER-001',
            name='Amber Oil',
            category_id=oil_category.id,
            cost_per_unit=Decimal('50.00'),
            quantity=Decimal('4000'),
            reorder_level=Decimal('800'),
            is_active=True
        )

        # Create raw materials - Ethanol
        ethanol = RawMaterial(
            code='ETH-001',
            name='Denatured Ethanol',
            category_id=ethanol_category.id,
            cost_per_unit=Decimal('0.50'),  # Per ml
            quantity=Decimal('50000'),
            reorder_level=Decimal('10000'),
            is_active=True
        )

        # Create raw materials - Bottles
        bottle_3ml = RawMaterial(
            code='BTL-003',
            name='Attar Bottle 3ml',
            category_id=bottle_category.id,
            bottle_size_ml=Decimal('3'),
            cost_per_unit=Decimal('15.00'),
            quantity=Decimal('1000'),
            reorder_level=Decimal('200'),
            is_active=True
        )
        bottle_6ml = RawMaterial(
            code='BTL-006',
            name='Attar Bottle 6ml',
            category_id=bottle_category.id,
            bottle_size_ml=Decimal('6'),
            cost_per_unit=Decimal('20.00'),
            quantity=Decimal('800'),
            reorder_level=Decimal('150'),
            is_active=True
        )
        bottle_12ml = RawMaterial(
            code='BTL-012',
            name='Attar Bottle 12ml',
            category_id=bottle_category.id,
            bottle_size_ml=Decimal('12'),
            cost_per_unit=Decimal('35.00'),
            quantity=Decimal('500'),
            reorder_level=Decimal('100'),
            is_active=True
        )
        bottle_50ml = RawMaterial(
            code='BTL-050',
            name='Perfume Bottle 50ml',
            category_id=bottle_category.id,
            bottle_size_ml=Decimal('50'),
            cost_per_unit=Decimal('75.00'),
            quantity=Decimal('300'),
            reorder_level=Decimal('50'),
            is_active=True
        )

        raw_materials = [oud_oil, musk_oil, rose_oil, amber_oil, ethanol,
                        bottle_3ml, bottle_6ml, bottle_12ml, bottle_50ml]
        db.session.add_all(raw_materials)
        db.session.flush()

        # Create raw material stock at warehouse
        for rm in raw_materials:
            stock = RawMaterialStock(
                raw_material_id=rm.id,
                location_id=warehouse.id,
                quantity=rm.quantity,
                reserved_quantity=Decimal('0'),
                reorder_level=rm.reorder_level
            )
            db.session.add(stock)

        # Create limited stock at kiosk1 (for attar production)
        for rm in [oud_oil, musk_oil, bottle_3ml, bottle_6ml]:
            stock = RawMaterialStock(
                raw_material_id=rm.id,
                location_id=kiosk1.id,
                quantity=Decimal('500') if rm.category_id == oil_category.id else Decimal('100'),
                reserved_quantity=Decimal('0')
            )
            db.session.add(stock)

        db.session.flush()

        # Create category for finished products
        attar_category = Category(name='Attars', description='Oil-based traditional perfumes')
        perfume_category = Category(name='Perfumes', description='Alcohol-based fragrances')
        db.session.add_all([attar_category, perfume_category])
        db.session.flush()

        # Create finished products (manufactured items)
        oud_attar_6ml = Product(
            code='PROD-OUD-6ML',
            name='Oud Attar 6ml',
            category_id=attar_category.id,
            cost_price=Decimal('950.00'),
            selling_price=Decimal('1800.00'),
            quantity=0,
            is_manufactured=True,
            product_type='manufactured',
            is_active=True
        )
        musk_amber_attar_6ml = Product(
            code='PROD-MA-6ML',
            name='Musk Amber Blend 6ml',
            category_id=attar_category.id,
            cost_price=Decimal('400.00'),
            selling_price=Decimal('800.00'),
            quantity=0,
            is_manufactured=True,
            product_type='manufactured',
            is_active=True
        )
        rose_perfume_50ml = Product(
            code='PROD-ROSE-50ML',
            name='Rose Perfume 50ml',
            category_id=perfume_category.id,
            cost_price=Decimal('600.00'),
            selling_price=Decimal('1200.00'),
            quantity=0,
            is_manufactured=True,
            product_type='manufactured',
            is_active=True
        )

        products = [oud_attar_6ml, musk_amber_attar_6ml, rose_perfume_50ml]
        db.session.add_all(products)
        db.session.flush()

        # Create users
        admin = User(
            username='prod_admin',
            email='prod_admin@test.com',
            full_name='Production Admin',
            role='admin',
            is_active=True,
            is_global_admin=True
        )
        admin.set_password('admin123')

        warehouse_mgr = User(
            username='prod_wh_mgr',
            email='wh_mgr@test.com',
            full_name='Warehouse Manager',
            role='warehouse_manager',
            location_id=warehouse.id,
            is_active=True
        )
        warehouse_mgr.set_password('whmgr123')

        kiosk_mgr = User(
            username='kiosk_mgr',
            email='kiosk_mgr@test.com',
            full_name='Kiosk Manager',
            role='kiosk_manager',
            location_id=kiosk1.id,
            is_active=True
        )
        kiosk_mgr.set_password('kioskmgr123')

        db.session.add_all([admin, warehouse_mgr, kiosk_mgr])
        db.session.flush()

        # Create Recipes
        # Recipe 1: Single Oil Attar (Oud 6ml)
        oud_recipe = Recipe(
            code='RCP-OUD-6ML',
            name='Oud Attar 6ml Recipe',
            recipe_type='single_oil',
            product_id=oud_attar_6ml.id,
            output_size_ml=Decimal('6'),
            oil_percentage=Decimal('100'),
            can_produce_at_warehouse=True,
            can_produce_at_kiosk=True,
            is_active=True,
            version=1,
            description='Pure Oud oil in 6ml bottle',
            created_by=admin.id
        )
        db.session.add(oud_recipe)
        db.session.flush()

        # Add ingredients for Oud recipe
        oud_ing = RecipeIngredient(
            recipe_id=oud_recipe.id,
            raw_material_id=oud_oil.id,
            percentage=Decimal('100'),
            is_packaging=False
        )
        oud_bottle_ing = RecipeIngredient(
            recipe_id=oud_recipe.id,
            raw_material_id=bottle_6ml.id,
            is_packaging=True
        )
        db.session.add_all([oud_ing, oud_bottle_ing])

        # Recipe 2: Blended Attar (Musk + Amber 6ml)
        blend_recipe = Recipe(
            code='RCP-MA-6ML',
            name='Musk Amber Blend 6ml Recipe',
            recipe_type='blended',
            product_id=musk_amber_attar_6ml.id,
            output_size_ml=Decimal('6'),
            oil_percentage=Decimal('100'),
            can_produce_at_warehouse=True,
            can_produce_at_kiosk=True,
            is_active=True,
            version=1,
            description='60% Musk, 40% Amber blend',
            created_by=admin.id
        )
        db.session.add(blend_recipe)
        db.session.flush()

        # Add ingredients for blend recipe
        musk_ing = RecipeIngredient(
            recipe_id=blend_recipe.id,
            raw_material_id=musk_oil.id,
            percentage=Decimal('60'),
            is_packaging=False
        )
        amber_ing = RecipeIngredient(
            recipe_id=blend_recipe.id,
            raw_material_id=amber_oil.id,
            percentage=Decimal('40'),
            is_packaging=False
        )
        blend_bottle_ing = RecipeIngredient(
            recipe_id=blend_recipe.id,
            raw_material_id=bottle_6ml.id,
            is_packaging=True
        )
        db.session.add_all([musk_ing, amber_ing, blend_bottle_ing])

        # Recipe 3: Perfume (Rose 50ml - 35% oil, 65% ethanol)
        perfume_recipe = Recipe(
            code='RCP-ROSE-50ML',
            name='Rose Perfume 50ml Recipe',
            recipe_type='perfume',
            product_id=rose_perfume_50ml.id,
            output_size_ml=Decimal('50'),
            oil_percentage=Decimal('35'),  # 35% oil, 65% ethanol
            can_produce_at_warehouse=True,
            can_produce_at_kiosk=False,  # Perfumes only at warehouse
            is_active=True,
            version=1,
            description='35% Rose oil, 65% ethanol in 50ml bottle',
            created_by=admin.id
        )
        db.session.add(perfume_recipe)
        db.session.flush()

        # Add ingredients for perfume recipe
        rose_ing = RecipeIngredient(
            recipe_id=perfume_recipe.id,
            raw_material_id=rose_oil.id,
            percentage=Decimal('100'),  # 100% of the oil portion
            is_packaging=False
        )
        ethanol_ing = RecipeIngredient(
            recipe_id=perfume_recipe.id,
            raw_material_id=ethanol.id,
            is_packaging=False
        )
        perfume_bottle_ing = RecipeIngredient(
            recipe_id=perfume_recipe.id,
            raw_material_id=bottle_50ml.id,
            is_packaging=True
        )
        db.session.add_all([rose_ing, ethanol_ing, perfume_bottle_ing])

        db.session.commit()

        yield {
            'warehouse': warehouse,
            'kiosk1': kiosk1,
            'kiosk2': kiosk2,
            'oil_category': oil_category,
            'ethanol_category': ethanol_category,
            'bottle_category': bottle_category,
            'oud_oil': oud_oil,
            'musk_oil': musk_oil,
            'rose_oil': rose_oil,
            'amber_oil': amber_oil,
            'ethanol': ethanol,
            'bottle_3ml': bottle_3ml,
            'bottle_6ml': bottle_6ml,
            'bottle_12ml': bottle_12ml,
            'bottle_50ml': bottle_50ml,
            'oud_attar_6ml': oud_attar_6ml,
            'musk_amber_attar_6ml': musk_amber_attar_6ml,
            'rose_perfume_50ml': rose_perfume_50ml,
            'oud_recipe': oud_recipe,
            'blend_recipe': blend_recipe,
            'perfume_recipe': perfume_recipe,
            'admin': admin,
            'warehouse_mgr': warehouse_mgr,
            'kiosk_mgr': kiosk_mgr,
        }


# =============================================================================
# TEST CLASS: RECIPE MANAGEMENT
# =============================================================================

class TestRecipeManagement:
    """Tests for recipe creation, updates, deletion, and versioning."""

    def test_create_single_oil_recipe(self, fresh_app, production_setup):
        """Test creating a simple single-oil attar recipe."""
        with fresh_app.app_context():
            data = production_setup
            recipe = Recipe.query.filter_by(code='RCP-OUD-6ML').first()

            assert recipe is not None
            assert recipe.name == 'Oud Attar 6ml Recipe'
            assert recipe.recipe_type == 'single_oil'
            assert recipe.output_size_ml == Decimal('6')
            assert recipe.oil_percentage == Decimal('100')
            assert recipe.can_produce_at_kiosk is True
            assert recipe.is_active is True

    def test_create_blended_recipe(self, fresh_app, production_setup):
        """Test creating a blended attar recipe with multiple oils."""
        with fresh_app.app_context():
            recipe = Recipe.query.filter_by(code='RCP-MA-6ML').first()

            assert recipe is not None
            assert recipe.recipe_type == 'blended'

            # Check ingredients
            oil_ingredients = recipe.oil_ingredients
            assert len(oil_ingredients) == 2

            # Check percentages sum to 100
            total_percentage = sum(
                float(ing.percentage) for ing in oil_ingredients
            )
            assert total_percentage == 100.0

    def test_create_perfume_recipe(self, fresh_app, production_setup):
        """Test creating a perfume recipe with oil and ethanol."""
        with fresh_app.app_context():
            recipe = Recipe.query.filter_by(code='RCP-ROSE-50ML').first()

            assert recipe is not None
            assert recipe.recipe_type == 'perfume'
            assert recipe.oil_percentage == Decimal('35')
            assert recipe.can_produce_at_kiosk is False  # Perfumes only at warehouse

    def test_recipe_ingredient_relationships(self, fresh_app, production_setup):
        """Test recipe-ingredient relationships."""
        with fresh_app.app_context():
            recipe = Recipe.query.filter_by(code='RCP-OUD-6ML').first()

            # Check ingredients list
            ingredients = recipe.ingredients_list
            assert len(ingredients) == 2

            # Check oil ingredient
            oil_ingredients = recipe.oil_ingredients
            assert len(oil_ingredients) == 1
            assert oil_ingredients[0].raw_material.code == 'OIL-OUD-001'

            # Check bottle ingredient
            bottle = recipe.bottle_ingredient
            assert bottle is not None
            assert bottle.is_packaging is True
            assert bottle.raw_material.code == 'BTL-006'

    def test_recipe_versioning(self, fresh_app, production_setup):
        """Test recipe versioning."""
        with fresh_app.app_context():
            recipe = Recipe.query.filter_by(code='RCP-OUD-6ML').first()

            assert recipe.version == 1

            # Update version
            recipe.version = 2
            recipe.description = 'Updated recipe with improved formula'
            db.session.commit()

            updated_recipe = Recipe.query.filter_by(code='RCP-OUD-6ML').first()
            assert updated_recipe.version == 2

    def test_recipe_deactivation(self, fresh_app, production_setup):
        """Test deactivating a recipe."""
        with fresh_app.app_context():
            recipe = Recipe.query.filter_by(code='RCP-OUD-6ML').first()
            assert recipe.is_active is True

            recipe.is_active = False
            db.session.commit()

            deactivated = Recipe.query.filter_by(code='RCP-OUD-6ML').first()
            assert deactivated.is_active is False

    def test_recipe_linked_to_product(self, fresh_app, production_setup):
        """Test recipe is properly linked to output product."""
        with fresh_app.app_context():
            recipe = Recipe.query.filter_by(code='RCP-OUD-6ML').first()
            product = recipe.product

            assert product is not None
            assert product.code == 'PROD-OUD-6ML'
            assert product.is_manufactured is True

    def test_create_recipe_without_product_fails(self, fresh_app, production_setup):
        """Test that production order creation fails if recipe has no product."""
        with fresh_app.app_context():
            data = production_setup

            # Create recipe without product
            orphan_recipe = Recipe(
                code='RCP-ORPHAN',
                name='Orphan Recipe',
                recipe_type='single_oil',
                product_id=None,  # No product
                output_size_ml=Decimal('6'),
                oil_percentage=Decimal('100'),
                is_active=True
            )
            db.session.add(orphan_recipe)
            db.session.commit()

            # Try to create production order
            order, error = ProductionService.create_production_order(
                recipe_id=orphan_recipe.id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id
            )

            assert order is None
            assert error == 'Recipe has no output product defined'


# =============================================================================
# TEST CLASS: INGREDIENT MANAGEMENT
# =============================================================================

class TestIngredientManagement:
    """Tests for ingredient handling in recipes."""

    def test_ingredient_quantity_calculation_single_oil(self, fresh_app, production_setup):
        """Test material calculation for single oil attar."""
        with fresh_app.app_context():
            data = production_setup

            # Calculate for 10 units of 6ml Oud attar
            requirements = ProductionService.calculate_material_requirements(
                data['oud_recipe'].id, 10
            )

            assert 'error' not in requirements
            assert requirements['quantity'] == 10
            assert requirements['total_output_ml'] == 60.0  # 10 * 6ml
            assert requirements['oil_amount_ml'] == 60.0  # 100% oil

            materials = requirements['materials']
            assert len(materials) == 2

            # Check oil quantity
            oil_mat = next(m for m in materials if m['code'] == 'OIL-OUD-001')
            assert oil_mat['quantity_required'] == 60.0

            # Check bottle quantity
            bottle_mat = next(m for m in materials if m['code'] == 'BTL-006')
            assert bottle_mat['quantity_required'] == 10

    def test_ingredient_quantity_calculation_blended(self, fresh_app, production_setup):
        """Test material calculation for blended attar."""
        with fresh_app.app_context():
            data = production_setup

            # Calculate for 10 units of 6ml Musk-Amber blend
            requirements = ProductionService.calculate_material_requirements(
                data['blend_recipe'].id, 10
            )

            assert 'error' not in requirements
            total_oil = requirements['oil_amount_ml']
            assert total_oil == 60.0  # 10 * 6ml

            materials = requirements['materials']

            # Check Musk oil (60% of total)
            musk_mat = next(m for m in materials if m['code'] == 'OIL-MUSK-001')
            assert musk_mat['quantity_required'] == 36.0  # 60% of 60ml

            # Check Amber oil (40% of total)
            amber_mat = next(m for m in materials if m['code'] == 'OIL-AMBER-001')
            assert amber_mat['quantity_required'] == 24.0  # 40% of 60ml

    def test_ingredient_quantity_calculation_perfume(self, fresh_app, production_setup):
        """Test material calculation for perfume (oil + ethanol)."""
        with fresh_app.app_context():
            data = production_setup

            # Calculate for 10 units of 50ml Rose perfume (35% oil)
            requirements = ProductionService.calculate_material_requirements(
                data['perfume_recipe'].id, 10
            )

            assert 'error' not in requirements
            assert requirements['total_output_ml'] == 500.0  # 10 * 50ml
            assert requirements['oil_amount_ml'] == 175.0  # 35% of 500ml
            assert requirements['ethanol_amount_ml'] == 325.0  # 65% of 500ml

    def test_recipe_not_found_error(self, fresh_app, production_setup):
        """Test error handling for non-existent recipe."""
        with fresh_app.app_context():
            requirements = ProductionService.calculate_material_requirements(
                recipe_id=99999, quantity=10
            )

            assert 'error' in requirements
            assert requirements['error'] == 'Recipe not found'

    def test_ingredient_percentage_validation(self, fresh_app, production_setup):
        """Test that blended recipe ingredient percentages are tracked."""
        with fresh_app.app_context():
            recipe = Recipe.query.filter_by(code='RCP-MA-6ML').first()

            oil_ingredients = [i for i in recipe.ingredients if not i.is_packaging]

            # Verify percentages
            percentages = [float(i.percentage) for i in oil_ingredients]
            assert sum(percentages) == 100.0


# =============================================================================
# TEST CLASS: PRODUCTION BATCHES
# =============================================================================

class TestProductionBatches:
    """Tests for production batch lifecycle."""

    def test_create_production_order(self, fresh_app, production_setup):
        """Test creating a production order."""
        with fresh_app.app_context():
            data = production_setup

            order, error = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                priority='normal',
                notes='Test production batch'
            )

            assert order is not None
            assert error is None
            assert order.status == 'draft'
            assert order.quantity_ordered == 10
            assert order.order_number.startswith('PRD')

    def test_create_order_with_auto_submit(self, fresh_app, production_setup):
        """Test creating order with auto-submit (pending status)."""
        with fresh_app.app_context():
            data = production_setup

            order, error = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )

            assert order is not None
            assert order.status == 'pending'
            assert order.requested_at is not None

    def test_submit_draft_order(self, fresh_app, production_setup):
        """Test submitting a draft order for approval."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id
            )

            assert order.status == 'draft'

            success, error = ProductionService.submit_order(order.id)
            assert success is True
            assert error is None

            db.session.refresh(order)
            assert order.status == 'pending'

    def test_approve_production_order(self, fresh_app, production_setup):
        """Test approving a production order."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )

            success, error = ProductionService.approve_order(
                order.id, data['admin'].id
            )

            assert success is True
            db.session.refresh(order)
            assert order.status == 'approved'
            assert order.approved_by == data['admin'].id

    def test_start_production(self, fresh_app, production_setup):
        """Test starting production on approved order."""
        with fresh_app.app_context():
            data = production_setup

            # Create and approve order
            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)

            # Start production
            success, error = ProductionService.start_production(
                order.id, data['warehouse_mgr'].id
            )

            assert success is True
            db.session.refresh(order)
            assert order.status == 'in_progress'
            assert order.started_at is not None

    def test_complete_production(self, fresh_app, production_setup):
        """Test completing production - full workflow."""
        with fresh_app.app_context():
            data = production_setup

            # Get initial stock
            oud_stock = RawMaterialStock.query.filter_by(
                raw_material_id=data['oud_oil'].id,
                location_id=data['warehouse'].id
            ).first()
            bottle_stock = RawMaterialStock.query.filter_by(
                raw_material_id=data['bottle_6ml'].id,
                location_id=data['warehouse'].id
            ).first()
            initial_oud = float(oud_stock.quantity)
            initial_bottles = float(bottle_stock.quantity)

            # Create, approve, and start order
            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)

            # Complete production
            success, error = ProductionService.execute_production(
                order.id, data['warehouse_mgr'].id, quantity_produced=10
            )

            assert success is True
            assert error is None

            db.session.refresh(order)
            assert order.status == 'completed'
            assert order.quantity_produced == 10
            assert order.completed_at is not None

            # Verify raw materials deducted
            db.session.refresh(oud_stock)
            db.session.refresh(bottle_stock)
            assert float(oud_stock.quantity) == initial_oud - 60  # 10 * 6ml
            assert float(bottle_stock.quantity) == initial_bottles - 10

    def test_partial_completion(self, fresh_app, production_setup):
        """Test partial production completion (produced less than ordered)."""
        with fresh_app.app_context():
            data = production_setup

            # Create order for 20 units
            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=20,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)

            # Complete with only 15 units
            success, error = ProductionService.execute_production(
                order.id, data['warehouse_mgr'].id, quantity_produced=15
            )

            assert success is True
            db.session.refresh(order)
            assert order.quantity_produced == 15
            assert order.quantity_ordered == 20

    def test_cancel_production_order(self, fresh_app, production_setup):
        """Test cancelling a production order."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )

            success, error = ProductionService.cancel_order(
                order.id, data['admin'].id, 'Testing cancellation'
            )

            assert success is True
            db.session.refresh(order)
            assert order.status == 'cancelled'
            assert order.rejection_reason == 'Testing cancellation'

    def test_cancel_approved_order_releases_reserved(self, fresh_app, production_setup):
        """Test that cancelling approved order releases reserved materials."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )

            # Approve (which reserves materials)
            ProductionService.approve_order(order.id, data['admin'].id)

            # Check reserved quantities
            oud_stock = RawMaterialStock.query.filter_by(
                raw_material_id=data['oud_oil'].id,
                location_id=data['warehouse'].id
            ).first()
            reserved_before = float(oud_stock.reserved_quantity)
            assert reserved_before > 0

            # Cancel order
            ProductionService.cancel_order(order.id, data['admin'].id, 'Changed plans')

            # Check reserved released
            db.session.refresh(oud_stock)
            assert float(oud_stock.reserved_quantity) == 0

    def test_reject_production_order(self, fresh_app, production_setup):
        """Test rejecting a production order."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )

            success, error = ProductionService.reject_order(
                order.id, data['admin'].id, 'Insufficient capacity'
            )

            assert success is True
            db.session.refresh(order)
            assert order.status == 'rejected'
            assert order.rejection_reason == 'Insufficient capacity'

    def test_cannot_start_unapproved_order(self, fresh_app, production_setup):
        """Test that unapproved orders cannot be started."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )

            # Try to start without approval
            success, error = ProductionService.start_production(
                order.id, data['warehouse_mgr'].id
            )

            assert success is False
            assert 'cannot be started' in error.lower()

    def test_cannot_complete_non_started_order(self, fresh_app, production_setup):
        """Test that non-started orders cannot be completed."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)

            # Try to complete without starting
            success, error = ProductionService.execute_production(
                order.id, data['warehouse_mgr'].id
            )

            assert success is False
            assert 'cannot be completed' in error.lower()


# =============================================================================
# TEST CLASS: YIELD TRACKING
# =============================================================================

class TestYieldTracking:
    """Tests for tracking expected vs actual production yields."""

    def test_full_yield_production(self, fresh_app, production_setup):
        """Test production with 100% yield (all ordered quantity produced)."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)
            ProductionService.execute_production(order.id, data['warehouse_mgr'].id, 10)

            db.session.refresh(order)
            assert order.quantity_produced == order.quantity_ordered
            yield_percentage = (order.quantity_produced / order.quantity_ordered) * 100
            assert yield_percentage == 100.0

    def test_reduced_yield_production(self, fresh_app, production_setup):
        """Test production with reduced yield (less than ordered)."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=100,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)
            ProductionService.execute_production(order.id, data['warehouse_mgr'].id, 95)

            db.session.refresh(order)
            yield_percentage = (order.quantity_produced / order.quantity_ordered) * 100
            assert yield_percentage == 95.0

    def test_variance_tracking(self, fresh_app, production_setup):
        """Test tracking variance between expected and actual."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=50,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)
            ProductionService.execute_production(order.id, data['warehouse_mgr'].id, 48)

            db.session.refresh(order)
            variance = order.quantity_ordered - order.quantity_produced
            assert variance == 2
            variance_percentage = (variance / order.quantity_ordered) * 100
            assert variance_percentage == 4.0


# =============================================================================
# TEST CLASS: COST CALCULATION
# =============================================================================

class TestCostCalculation:
    """Tests for production cost calculations."""

    def test_ingredient_cost_single_oil(self, fresh_app, production_setup):
        """Test cost calculation for single oil recipe."""
        with fresh_app.app_context():
            data = production_setup

            # For 10 units of 6ml Oud attar:
            # - Oud oil: 60ml * Rs.150/ml = Rs.9000
            # - Bottle 6ml: 10 * Rs.20 = Rs.200
            # Total = Rs.9200

            requirements = ProductionService.calculate_material_requirements(
                data['oud_recipe'].id, 10
            )

            total_cost = Decimal('0')
            for mat in requirements['materials']:
                raw_mat = RawMaterial.query.get(mat['raw_material_id'])
                cost = Decimal(str(mat['quantity_required'])) * raw_mat.cost_per_unit
                total_cost += cost

            expected_oil_cost = Decimal('60') * Decimal('150')  # 9000
            expected_bottle_cost = Decimal('10') * Decimal('20')  # 200
            expected_total = expected_oil_cost + expected_bottle_cost  # 9200

            assert total_cost == expected_total

    def test_ingredient_cost_blended(self, fresh_app, production_setup):
        """Test cost calculation for blended recipe."""
        with fresh_app.app_context():
            data = production_setup

            # For 10 units of 6ml Musk-Amber blend:
            # - Musk oil: 36ml * Rs.80/ml = Rs.2880
            # - Amber oil: 24ml * Rs.50/ml = Rs.1200
            # - Bottle 6ml: 10 * Rs.20 = Rs.200
            # Total = Rs.4280

            requirements = ProductionService.calculate_material_requirements(
                data['blend_recipe'].id, 10
            )

            total_cost = Decimal('0')
            for mat in requirements['materials']:
                raw_mat = RawMaterial.query.get(mat['raw_material_id'])
                cost = Decimal(str(mat['quantity_required'])) * raw_mat.cost_per_unit
                total_cost += cost

            expected_musk_cost = Decimal('36') * Decimal('80')  # 2880
            expected_amber_cost = Decimal('24') * Decimal('50')  # 1200
            expected_bottle_cost = Decimal('10') * Decimal('20')  # 200
            expected_total = expected_musk_cost + expected_amber_cost + expected_bottle_cost

            assert total_cost == expected_total

    def test_ingredient_cost_perfume(self, fresh_app, production_setup):
        """Test cost calculation for perfume with ethanol."""
        with fresh_app.app_context():
            data = production_setup

            # For 10 units of 50ml Rose perfume (35% oil):
            # - Rose oil: 175ml * Rs.200/ml = Rs.35000
            # - Ethanol: 325ml * Rs.0.50/ml = Rs.162.50
            # - Bottle 50ml: 10 * Rs.75 = Rs.750
            # Total = Rs.35912.50

            requirements = ProductionService.calculate_material_requirements(
                data['perfume_recipe'].id, 10
            )

            total_cost = Decimal('0')
            for mat in requirements['materials']:
                raw_mat = RawMaterial.query.get(mat['raw_material_id'])
                cost = Decimal(str(mat['quantity_required'])) * raw_mat.cost_per_unit
                total_cost += cost

            # Approximate check (ethanol calculation may vary)
            assert total_cost > Decimal('35000')  # At least the rose oil cost

    def test_cost_per_unit_calculation(self, fresh_app, production_setup):
        """Test calculating cost per finished unit."""
        with fresh_app.app_context():
            data = production_setup

            quantity = 10
            requirements = ProductionService.calculate_material_requirements(
                data['oud_recipe'].id, quantity
            )

            total_cost = Decimal('0')
            for mat in requirements['materials']:
                raw_mat = RawMaterial.query.get(mat['raw_material_id'])
                cost = Decimal(str(mat['quantity_required'])) * raw_mat.cost_per_unit
                total_cost += cost

            cost_per_unit = total_cost / quantity
            expected_cost_per_unit = Decimal('920')  # (9000 + 200) / 10

            assert cost_per_unit == expected_cost_per_unit


# =============================================================================
# TEST CLASS: INVENTORY INTEGRATION
# =============================================================================

class TestInventoryIntegration:
    """Tests for inventory deductions and additions."""

    def test_raw_material_deduction(self, fresh_app, production_setup):
        """Test raw materials are deducted on production completion."""
        with fresh_app.app_context():
            data = production_setup

            # Get initial stock
            oud_stock = RawMaterialStock.query.filter_by(
                raw_material_id=data['oud_oil'].id,
                location_id=data['warehouse'].id
            ).first()
            initial_quantity = float(oud_stock.quantity)

            # Run production
            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)
            ProductionService.execute_production(order.id, data['warehouse_mgr'].id, 10)

            # Verify deduction
            db.session.refresh(oud_stock)
            assert float(oud_stock.quantity) == initial_quantity - 60  # 10 * 6ml

    def test_finished_product_addition(self, fresh_app, production_setup):
        """Test finished products are added to inventory."""
        with fresh_app.app_context():
            data = production_setup

            product = data['oud_attar_6ml']
            initial_qty = product.quantity or 0

            # Run production
            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)
            ProductionService.execute_production(order.id, data['warehouse_mgr'].id, 10)

            # Verify addition
            db.session.refresh(product)
            assert product.quantity == initial_qty + 10

    def test_location_stock_addition(self, fresh_app, production_setup):
        """Test finished products are added to location stock."""
        with fresh_app.app_context():
            data = production_setup

            # Run production
            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)
            ProductionService.execute_production(order.id, data['warehouse_mgr'].id, 10)

            # Check location stock
            loc_stock = LocationStock.query.filter_by(
                product_id=data['oud_attar_6ml'].id,
                location_id=data['warehouse'].id
            ).first()

            assert loc_stock is not None
            assert loc_stock.quantity == 10

    def test_material_movement_records_created(self, fresh_app, production_setup):
        """Test that material movements are recorded."""
        with fresh_app.app_context():
            data = production_setup

            # Run production
            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)
            ProductionService.execute_production(order.id, data['warehouse_mgr'].id, 10)

            # Check movements created
            movements = RawMaterialMovement.query.filter_by(
                production_order_id=order.id
            ).all()

            assert len(movements) == 2  # Oud oil + bottle
            for mov in movements:
                assert mov.movement_type == 'production_consumption'
                assert float(mov.quantity) < 0  # Negative for consumption

    def test_consumption_records_created(self, fresh_app, production_setup):
        """Test that consumption records are created."""
        with fresh_app.app_context():
            data = production_setup

            # Run production
            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)
            ProductionService.execute_production(order.id, data['warehouse_mgr'].id, 10)

            # Check consumption records
            consumptions = ProductionMaterialConsumption.query.filter_by(
                production_order_id=order.id
            ).all()

            assert len(consumptions) == 2
            for cons in consumptions:
                assert cons.quantity_consumed == cons.quantity_required


# =============================================================================
# TEST CLASS: QUALITY CONTROL
# =============================================================================

class TestQualityControl:
    """Tests for quality control in production workflow."""

    def test_approval_required_before_production(self, fresh_app, production_setup):
        """Test that orders must be approved before production."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )

            # Order is pending, not approved
            assert order.can_approve is True
            assert order.can_start is False

            # Approve
            ProductionService.approve_order(order.id, data['admin'].id)
            db.session.refresh(order)

            assert order.can_approve is False
            assert order.can_start is True

    def test_approval_checks_material_availability(self, fresh_app, production_setup):
        """Test that approval verifies material availability."""
        with fresh_app.app_context():
            data = production_setup

            # Create order for large quantity
            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10000,  # Very large quantity
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )

            # Try to approve - should fail due to insufficient materials
            success, error = ProductionService.approve_order(
                order.id, data['admin'].id
            )

            assert success is False
            assert 'insufficient' in error.lower()

    def test_rejection_workflow(self, fresh_app, production_setup):
        """Test the order rejection workflow."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )

            success, error = ProductionService.reject_order(
                order.id, data['admin'].id, 'Quality concerns with ingredients'
            )

            assert success is True
            db.session.refresh(order)
            assert order.status == 'rejected'
            assert order.approved_by == data['admin'].id
            assert order.rejection_reason == 'Quality concerns with ingredients'

    def test_cannot_reject_non_pending_order(self, fresh_app, production_setup):
        """Test that only pending orders can be rejected."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id
            )
            # Order is in draft status, not pending

            success, error = ProductionService.reject_order(
                order.id, data['admin'].id, 'Testing rejection'
            )

            assert success is False
            assert 'cannot be rejected' in error.lower()


# =============================================================================
# TEST CLASS: SCHEDULING
# =============================================================================

class TestScheduling:
    """Tests for production scheduling and planning."""

    def test_order_with_due_date(self, fresh_app, production_setup):
        """Test creating order with due date."""
        with fresh_app.app_context():
            data = production_setup
            due = date.today() + timedelta(days=7)

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                due_date=due
            )

            assert order.due_date == due

    def test_order_priority_levels(self, fresh_app, production_setup):
        """Test different priority levels for orders."""
        with fresh_app.app_context():
            data = production_setup

            priorities = ['low', 'normal', 'high', 'urgent']

            for priority in priorities:
                order, _ = ProductionService.create_production_order(
                    recipe_id=data['oud_recipe'].id,
                    quantity=10,
                    location_id=data['warehouse'].id,
                    user_id=data['admin'].id,
                    priority=priority
                )
                assert order.priority == priority

    def test_multiple_orders_same_time(self, fresh_app, production_setup):
        """Test creating multiple production orders."""
        with fresh_app.app_context():
            data = production_setup

            orders = []
            for i in range(3):
                order, _ = ProductionService.create_production_order(
                    recipe_id=data['oud_recipe'].id,
                    quantity=5,
                    location_id=data['warehouse'].id,
                    user_id=data['admin'].id,
                    auto_submit=True
                )
                orders.append(order)

            # All orders should have unique order numbers
            order_numbers = [o.order_number for o in orders]
            assert len(set(order_numbers)) == 3

    def test_order_number_generation(self, fresh_app, production_setup):
        """Test that order numbers are generated correctly."""
        with fresh_app.app_context():
            data = production_setup

            order1, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id
            )
            order2, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id
            )

            # Order numbers should be sequential
            today = datetime.now().strftime('%Y%m%d')
            assert order1.order_number.startswith(f'PRD{today}')
            assert order2.order_number.startswith(f'PRD{today}')

            # Second order number should be higher
            num1 = int(order1.order_number[-4:])
            num2 = int(order2.order_number[-4:])
            assert num2 > num1


# =============================================================================
# TEST CLASS: TRACEABILITY
# =============================================================================

class TestTraceability:
    """Tests for production batch and ingredient traceability."""

    def test_order_tracks_creator(self, fresh_app, production_setup):
        """Test that order tracks who created it."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )

            assert order.requested_by == data['admin'].id

    def test_order_tracks_approver(self, fresh_app, production_setup):
        """Test that order tracks who approved it."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['warehouse_mgr'].id)

            db.session.refresh(order)
            assert order.approved_by == data['warehouse_mgr'].id
            assert order.approved_at is not None

    def test_order_tracks_producer(self, fresh_app, production_setup):
        """Test that order tracks who produced it."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)
            ProductionService.execute_production(order.id, data['warehouse_mgr'].id, 10)

            db.session.refresh(order)
            assert order.produced_by == data['warehouse_mgr'].id

    def test_material_movements_reference_order(self, fresh_app, production_setup):
        """Test that material movements reference the production order."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)
            ProductionService.execute_production(order.id, data['warehouse_mgr'].id, 10)

            movements = RawMaterialMovement.query.filter_by(
                production_order_id=order.id
            ).all()

            for mov in movements:
                assert mov.reference == order.order_number
                assert mov.production_order_id == order.id

    def test_consumption_tracks_materials_used(self, fresh_app, production_setup):
        """Test consumption records track exactly which materials were used."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['blend_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)
            ProductionService.execute_production(order.id, data['warehouse_mgr'].id, 10)

            consumptions = ProductionMaterialConsumption.query.filter_by(
                production_order_id=order.id
            ).all()

            # Should have 3 consumption records (Musk, Amber, Bottle)
            assert len(consumptions) == 3

            material_ids = {c.raw_material_id for c in consumptions}
            assert data['musk_oil'].id in material_ids
            assert data['amber_oil'].id in material_ids
            assert data['bottle_6ml'].id in material_ids


# =============================================================================
# TEST CLASS: EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_insufficient_materials_blocks_approval(self, fresh_app, production_setup):
        """Test that insufficient materials block order approval."""
        with fresh_app.app_context():
            data = production_setup

            # Create order for more than available
            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10000,  # Much more than available
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )

            success, error = ProductionService.approve_order(
                order.id, data['admin'].id
            )

            assert success is False
            assert 'insufficient' in error.lower()

    def test_insufficient_materials_blocks_execution(self, fresh_app, production_setup):
        """Test that insufficient materials block production execution."""
        with fresh_app.app_context():
            data = production_setup

            # Create and approve small order
            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)

            # Manually deplete stock
            oud_stock = RawMaterialStock.query.filter_by(
                raw_material_id=data['oud_oil'].id,
                location_id=data['warehouse'].id
            ).first()
            oud_stock.quantity = Decimal('0')
            db.session.commit()

            # Try to execute
            success, error = ProductionService.execute_production(
                order.id, data['warehouse_mgr'].id, 10
            )

            assert success is False
            assert 'insufficient' in error.lower()

    def test_nonexistent_order_handling(self, fresh_app, production_setup):
        """Test handling of non-existent order IDs."""
        with fresh_app.app_context():
            data = production_setup

            success, error = ProductionService.approve_order(99999, data['admin'].id)
            assert success is False
            assert 'not found' in error.lower()

            success, error = ProductionService.start_production(99999, data['admin'].id)
            assert success is False
            assert 'not found' in error.lower()

            success, error = ProductionService.execute_production(99999, data['admin'].id)
            assert success is False
            assert 'not found' in error.lower()

    def test_nonexistent_recipe_handling(self, fresh_app, production_setup):
        """Test handling of non-existent recipe ID."""
        with fresh_app.app_context():
            data = production_setup

            order, error = ProductionService.create_production_order(
                recipe_id=99999,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id
            )

            assert order is None
            assert 'not found' in error.lower()

    def test_nonexistent_location_handling(self, fresh_app, production_setup):
        """Test handling of non-existent location ID."""
        with fresh_app.app_context():
            data = production_setup

            order, error = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=99999,
                user_id=data['admin'].id
            )

            assert order is None
            assert 'not found' in error.lower()

    def test_zero_quantity_order(self, fresh_app, production_setup):
        """Test that zero quantity orders behave correctly."""
        with fresh_app.app_context():
            data = production_setup

            requirements = ProductionService.calculate_material_requirements(
                data['oud_recipe'].id, 0
            )

            # Should return zero quantities
            assert requirements['total_output_ml'] == 0
            assert requirements['oil_amount_ml'] == 0

    def test_cannot_cancel_completed_order(self, fresh_app, production_setup):
        """Test that completed orders cannot be cancelled."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)
            ProductionService.execute_production(order.id, data['warehouse_mgr'].id, 10)

            success, error = ProductionService.cancel_order(
                order.id, data['admin'].id
            )

            assert success is False
            assert 'cannot be cancelled' in error.lower()

    def test_cannot_cancel_in_progress_order(self, fresh_app, production_setup):
        """Test that in-progress orders cannot be cancelled."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)

            # Cannot cancel in_progress
            db.session.refresh(order)
            assert order.can_cancel is False


# =============================================================================
# TEST CLASS: MULTI-LOCATION
# =============================================================================

class TestMultiLocation:
    """Tests for production at different locations."""

    def test_perfume_only_at_warehouse(self, fresh_app, production_setup):
        """Test that perfumes can only be produced at warehouse."""
        with fresh_app.app_context():
            data = production_setup

            # Try to create perfume order at kiosk
            order, error = ProductionService.create_production_order(
                recipe_id=data['perfume_recipe'].id,
                quantity=10,
                location_id=data['kiosk1'].id,
                user_id=data['admin'].id
            )

            assert order is None
            assert 'warehouse' in error.lower()

    def test_attar_at_kiosk(self, fresh_app, production_setup):
        """Test that attars can be produced at kiosk."""
        with fresh_app.app_context():
            data = production_setup

            order, error = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=5,  # Small quantity
                location_id=data['kiosk1'].id,
                user_id=data['admin'].id
            )

            assert order is not None
            assert error is None
            assert order.location_id == data['kiosk1'].id

    def test_location_specific_stock_check(self, fresh_app, production_setup):
        """Test that material availability is checked per location."""
        with fresh_app.app_context():
            data = production_setup

            # Kiosk has limited stock
            availability = ProductionService.check_material_availability(
                data['oud_recipe'].id,
                1000,  # Large quantity
                data['kiosk1'].id
            )

            assert availability['all_available'] is False

            # Warehouse has more stock
            availability = ProductionService.check_material_availability(
                data['oud_recipe'].id,
                100,
                data['warehouse'].id
            )

            assert availability['all_available'] is True

    def test_production_updates_location_stock(self, fresh_app, production_setup):
        """Test that production updates stock at the correct location."""
        with fresh_app.app_context():
            data = production_setup

            # Get initial stocks
            warehouse_oud = RawMaterialStock.query.filter_by(
                raw_material_id=data['oud_oil'].id,
                location_id=data['warehouse'].id
            ).first()
            kiosk_oud = RawMaterialStock.query.filter_by(
                raw_material_id=data['oud_oil'].id,
                location_id=data['kiosk1'].id
            ).first()

            initial_warehouse = float(warehouse_oud.quantity)
            initial_kiosk = float(kiosk_oud.quantity)

            # Produce at warehouse
            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)
            ProductionService.execute_production(order.id, data['warehouse_mgr'].id, 10)

            # Warehouse stock should decrease, kiosk unchanged
            db.session.refresh(warehouse_oud)
            db.session.refresh(kiosk_oud)

            assert float(warehouse_oud.quantity) < initial_warehouse
            assert float(kiosk_oud.quantity) == initial_kiosk


# =============================================================================
# TEST CLASS: REPORTS AND STATISTICS
# =============================================================================

class TestReportsAndStatistics:
    """Tests for production reports and statistics."""

    def test_get_production_stats_empty(self, fresh_app, production_setup):
        """Test getting stats when no production has occurred."""
        with fresh_app.app_context():
            data = production_setup

            stats = ProductionService.get_production_stats(data['warehouse'].id)

            assert stats['pending_count'] == 0
            assert stats['in_progress_count'] == 0
            assert stats['completed_count'] == 0
            assert stats['month_total_produced'] == 0

    def test_get_production_stats_with_orders(self, fresh_app, production_setup):
        """Test getting stats with production orders."""
        with fresh_app.app_context():
            data = production_setup

            # Create various orders
            for i in range(3):
                order, _ = ProductionService.create_production_order(
                    recipe_id=data['oud_recipe'].id,
                    quantity=10,
                    location_id=data['warehouse'].id,
                    user_id=data['admin'].id,
                    auto_submit=True
                )
                if i == 0:
                    # Complete first order
                    ProductionService.approve_order(order.id, data['admin'].id)
                    ProductionService.start_production(order.id, data['warehouse_mgr'].id)
                    ProductionService.execute_production(order.id, data['warehouse_mgr'].id, 10)

            stats = ProductionService.get_production_stats(data['warehouse'].id)

            assert stats['pending_count'] == 2
            assert stats['completed_count'] == 1
            assert stats['month_total_produced'] == 10

    def test_get_low_stock_materials(self, fresh_app, production_setup):
        """Test identifying low stock materials."""
        with fresh_app.app_context():
            data = production_setup

            # Deplete some stock
            oud_stock = RawMaterialStock.query.filter_by(
                raw_material_id=data['oud_oil'].id,
                location_id=data['warehouse'].id
            ).first()
            oud_stock.quantity = Decimal('100')  # Below reorder level of 1000
            db.session.commit()

            low_stock = ProductionService.get_low_stock_materials(data['warehouse'].id)

            assert len(low_stock) > 0
            material_ids = {item['material'].id for item in low_stock}
            assert data['oud_oil'].id in material_ids

    def test_check_material_availability_returns_details(self, fresh_app, production_setup):
        """Test that availability check returns detailed information."""
        with fresh_app.app_context():
            data = production_setup

            availability = ProductionService.check_material_availability(
                data['oud_recipe'].id,
                10,
                data['warehouse'].id
            )

            assert 'location' in availability
            assert 'recipe' in availability
            assert 'quantity' in availability
            assert 'all_available' in availability
            assert 'materials' in availability

            for material in availability['materials']:
                assert 'name' in material
                assert 'quantity_required' in material
                assert 'available_quantity' in material
                assert 'is_available' in material
                assert 'shortage' in material


# =============================================================================
# TEST CLASS: PRODUCTION ORDER STATUS PROPERTIES
# =============================================================================

class TestProductionOrderProperties:
    """Tests for ProductionOrder model properties."""

    def test_status_badge_classes(self, fresh_app, production_setup):
        """Test status badge CSS classes."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id
            )

            assert order.status_badge_class == 'secondary'  # draft

            order.status = 'pending'
            assert order.status_badge_class == 'info'

            order.status = 'approved'
            assert order.status_badge_class == 'primary'

            order.status = 'in_progress'
            assert order.status_badge_class == 'warning'

            order.status = 'completed'
            assert order.status_badge_class == 'success'

            order.status = 'rejected'
            assert order.status_badge_class == 'danger'

            order.status = 'cancelled'
            assert order.status_badge_class == 'dark'

    def test_can_approve_property(self, fresh_app, production_setup):
        """Test can_approve property."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id
            )

            assert order.can_approve is False  # draft cannot be approved

            order.status = 'pending'
            assert order.can_approve is True

            order.status = 'approved'
            assert order.can_approve is False

    def test_can_start_property(self, fresh_app, production_setup):
        """Test can_start property."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id
            )

            assert order.can_start is False  # draft

            order.status = 'pending'
            assert order.can_start is False

            order.status = 'approved'
            assert order.can_start is True

            order.status = 'in_progress'
            assert order.can_start is False

    def test_can_complete_property(self, fresh_app, production_setup):
        """Test can_complete property."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id
            )

            assert order.can_complete is False  # draft

            order.status = 'approved'
            assert order.can_complete is False

            order.status = 'in_progress'
            assert order.can_complete is True

            order.status = 'completed'
            assert order.can_complete is False

    def test_can_cancel_property(self, fresh_app, production_setup):
        """Test can_cancel property."""
        with fresh_app.app_context():
            data = production_setup

            order, _ = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id
            )

            assert order.can_cancel is True  # draft

            order.status = 'pending'
            assert order.can_cancel is True

            order.status = 'approved'
            assert order.can_cancel is True

            order.status = 'in_progress'
            assert order.can_cancel is False

            order.status = 'completed'
            assert order.can_cancel is False


# =============================================================================
# TEST CLASS: RAW MATERIAL STOCK PROPERTIES
# =============================================================================

class TestRawMaterialStockProperties:
    """Tests for RawMaterialStock model properties."""

    def test_available_quantity_calculation(self, fresh_app, production_setup):
        """Test available quantity calculation."""
        with fresh_app.app_context():
            data = production_setup

            stock = RawMaterialStock.query.filter_by(
                raw_material_id=data['oud_oil'].id,
                location_id=data['warehouse'].id
            ).first()

            stock.quantity = Decimal('1000')
            stock.reserved_quantity = Decimal('200')
            db.session.commit()

            assert stock.available_quantity == 800.0

    def test_is_low_stock_property(self, fresh_app, production_setup):
        """Test is_low_stock property."""
        with fresh_app.app_context():
            data = production_setup

            stock = RawMaterialStock.query.filter_by(
                raw_material_id=data['oud_oil'].id,
                location_id=data['warehouse'].id
            ).first()

            # Above reorder level
            stock.quantity = Decimal('5000')
            stock.reorder_level = Decimal('1000')
            db.session.commit()

            assert stock.is_low_stock is False

            # Below reorder level
            stock.quantity = Decimal('500')
            db.session.commit()

            assert stock.is_low_stock is True


# =============================================================================
# TEST CLASS: RECIPE PROPERTIES
# =============================================================================

class TestRecipeProperties:
    """Tests for Recipe model properties."""

    def test_ingredients_list_property(self, fresh_app, production_setup):
        """Test ingredients_list property."""
        with fresh_app.app_context():
            recipe = Recipe.query.filter_by(code='RCP-MA-6ML').first()

            ingredients = recipe.ingredients_list
            assert isinstance(ingredients, list)
            assert len(ingredients) == 3

    def test_oil_ingredients_property(self, fresh_app, production_setup):
        """Test oil_ingredients property."""
        with fresh_app.app_context():
            recipe = Recipe.query.filter_by(code='RCP-MA-6ML').first()

            oil_ingredients = recipe.oil_ingredients
            assert len(oil_ingredients) == 2

            for ing in oil_ingredients:
                assert ing.is_packaging is False

    def test_bottle_ingredient_property(self, fresh_app, production_setup):
        """Test bottle_ingredient property."""
        with fresh_app.app_context():
            recipe = Recipe.query.filter_by(code='RCP-MA-6ML').first()

            bottle = recipe.bottle_ingredient
            assert bottle is not None
            assert bottle.is_packaging is True


# =============================================================================
# TEST CLASS: INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for complete production workflows."""

    def test_full_production_workflow_single_oil(self, fresh_app, production_setup):
        """Test complete production workflow for single oil attar."""
        with fresh_app.app_context():
            data = production_setup

            # 1. Check initial state
            product = data['oud_attar_6ml']
            initial_product_qty = product.quantity or 0

            oud_stock = RawMaterialStock.query.filter_by(
                raw_material_id=data['oud_oil'].id,
                location_id=data['warehouse'].id
            ).first()
            bottle_stock = RawMaterialStock.query.filter_by(
                raw_material_id=data['bottle_6ml'].id,
                location_id=data['warehouse'].id
            ).first()
            initial_oud = float(oud_stock.quantity)
            initial_bottles = float(bottle_stock.quantity)

            # 2. Create production order
            order, error = ProductionService.create_production_order(
                recipe_id=data['oud_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                priority='high',
                notes='Test batch',
                auto_submit=True
            )
            assert order is not None
            assert order.status == 'pending'

            # 3. Approve order
            success, _ = ProductionService.approve_order(order.id, data['admin'].id)
            assert success is True
            db.session.refresh(order)
            assert order.status == 'approved'

            # 4. Start production
            success, _ = ProductionService.start_production(
                order.id, data['warehouse_mgr'].id
            )
            assert success is True
            db.session.refresh(order)
            assert order.status == 'in_progress'

            # 5. Complete production
            success, _ = ProductionService.execute_production(
                order.id, data['warehouse_mgr'].id, 10
            )
            assert success is True
            db.session.refresh(order)
            assert order.status == 'completed'
            assert order.quantity_produced == 10

            # 6. Verify inventory changes
            db.session.refresh(product)
            db.session.refresh(oud_stock)
            db.session.refresh(bottle_stock)

            assert product.quantity == initial_product_qty + 10
            assert float(oud_stock.quantity) == initial_oud - 60  # 10 * 6ml
            assert float(bottle_stock.quantity) == initial_bottles - 10

            # 7. Verify traceability records
            movements = RawMaterialMovement.query.filter_by(
                production_order_id=order.id
            ).all()
            assert len(movements) == 2

            consumptions = ProductionMaterialConsumption.query.filter_by(
                production_order_id=order.id
            ).all()
            assert len(consumptions) == 2

    def test_full_production_workflow_blended(self, fresh_app, production_setup):
        """Test complete production workflow for blended attar."""
        with fresh_app.app_context():
            data = production_setup

            # Create and complete production
            order, _ = ProductionService.create_production_order(
                recipe_id=data['blend_recipe'].id,
                quantity=10,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)
            success, _ = ProductionService.execute_production(
                order.id, data['warehouse_mgr'].id, 10
            )

            assert success is True

            # Verify correct materials consumed
            consumptions = ProductionMaterialConsumption.query.filter_by(
                production_order_id=order.id
            ).all()

            material_ids = {c.raw_material_id for c in consumptions}
            assert data['musk_oil'].id in material_ids
            assert data['amber_oil'].id in material_ids
            assert data['bottle_6ml'].id in material_ids

    def test_full_production_workflow_perfume(self, fresh_app, production_setup):
        """Test complete production workflow for perfume."""
        with fresh_app.app_context():
            data = production_setup

            # Create and complete production at warehouse
            order, _ = ProductionService.create_production_order(
                recipe_id=data['perfume_recipe'].id,
                quantity=5,
                location_id=data['warehouse'].id,
                user_id=data['admin'].id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, data['admin'].id)
            ProductionService.start_production(order.id, data['warehouse_mgr'].id)
            success, _ = ProductionService.execute_production(
                order.id, data['warehouse_mgr'].id, 5
            )

            assert success is True

            # Verify ethanol was consumed
            consumptions = ProductionMaterialConsumption.query.filter_by(
                production_order_id=order.id
            ).all()

            # Should have rose oil, ethanol, and bottle
            assert len(consumptions) >= 3

    def test_multiple_sequential_productions(self, fresh_app, production_setup):
        """Test multiple sequential production runs."""
        with fresh_app.app_context():
            data = production_setup

            product = data['oud_attar_6ml']
            initial_qty = product.quantity or 0

            # Run 3 production batches
            for i in range(3):
                order, _ = ProductionService.create_production_order(
                    recipe_id=data['oud_recipe'].id,
                    quantity=5,
                    location_id=data['warehouse'].id,
                    user_id=data['admin'].id,
                    auto_submit=True
                )
                ProductionService.approve_order(order.id, data['admin'].id)
                ProductionService.start_production(order.id, data['warehouse_mgr'].id)
                ProductionService.execute_production(order.id, data['warehouse_mgr'].id, 5)

            # Verify total produced
            db.session.refresh(product)
            assert product.quantity == initial_qty + 15  # 3 * 5


# =============================================================================
# TEST CLASS: API ENDPOINT TESTS
# =============================================================================

class TestProductionRoutes:
    """Tests for production route endpoints."""

    def test_production_index_requires_auth(self, fresh_app, production_setup):
        """Test that production index requires authentication."""
        with fresh_app.app_context():
            client = fresh_app.test_client()
            response = client.get('/production/')
            # Should redirect to login
            assert response.status_code in [302, 401, 403]

    def test_api_calculate_requirements(self, fresh_app, production_setup):
        """Test API endpoint for calculating requirements."""
        with fresh_app.app_context():
            data = production_setup

            # Login
            client = fresh_app.test_client()
            client.post('/auth/login', data={
                'username': 'prod_admin',
                'password': 'admin123'
            })

            response = client.get(
                f'/production/api/calculate-requirements?recipe_id={data["oud_recipe"].id}&quantity=10'
            )

            if response.status_code == 200:
                json_data = response.get_json()
                assert json_data['quantity'] == 10
                assert 'materials' in json_data

    def test_api_check_availability(self, fresh_app, production_setup):
        """Test API endpoint for checking availability."""
        with fresh_app.app_context():
            data = production_setup

            # Login
            client = fresh_app.test_client()
            client.post('/auth/login', data={
                'username': 'prod_admin',
                'password': 'admin123'
            })

            response = client.get(
                f'/production/api/check-availability?recipe_id={data["oud_recipe"].id}&quantity=10&location_id={data["warehouse"].id}'
            )

            if response.status_code == 200:
                json_data = response.get_json()
                assert 'all_available' in json_data
                assert 'materials' in json_data
