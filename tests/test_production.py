"""
Comprehensive Unit Tests for Production System

Tests cover:
1. Raw material management
2. Recipe creation and validation
3. Production order workflow
4. Material consumption calculations
5. Perfume vs Attar production rules
6. Location restrictions (perfumes at warehouse only)

Edge cases tested:
- Insufficient raw materials
- Invalid oil percentages (not summing to 100%)
- Perfume production at kiosk (should fail)
- Recipe ingredient validation
- Production order status transitions
- Concurrent material consumption
- Decimal precision in formulas
- Zero quantity production
- Cost calculations
"""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app import create_app
from app.models import (
    db, User, Product, Location, LocationStock,
    RawMaterial, RawMaterialCategory, RawMaterialStock, RawMaterialMovement,
    Recipe, RecipeIngredient, ProductionOrder, ProductionMaterialConsumption
)
from app.services.production_service import ProductionService


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope='function')
def app():
    """Create application for testing"""
    app = create_app('testing')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['TESTING'] = True

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture(scope='function')
def db_session(app):
    """Create database session for testing"""
    with app.app_context():
        yield db.session


@pytest.fixture
def warehouse_location(app):
    """Create a warehouse location"""
    with app.app_context():
        warehouse = Location(
            code='WH-001',
            name='Main Warehouse',
            location_type='warehouse',
            is_active=True,
            can_sell=False
        )
        db.session.add(warehouse)
        db.session.commit()
        db.session.refresh(warehouse)
        return warehouse


@pytest.fixture
def kiosk_location(app, warehouse_location):
    """Create a kiosk location"""
    with app.app_context():
        kiosk = Location(
            code='K-001',
            name='Mall Kiosk',
            location_type='kiosk',
            is_active=True,
            can_sell=True,
            parent_warehouse_id=warehouse_location.id
        )
        db.session.add(kiosk)
        db.session.commit()
        db.session.refresh(kiosk)
        return kiosk


@pytest.fixture
def test_user(app):
    """Create a test user"""
    with app.app_context():
        user = User(
            username='testuser',
            email='test@test.com',
            full_name='Test User',
            role='admin',
            is_active=True,
            is_global_admin=True
        )
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        db.session.refresh(user)
        return user


@pytest.fixture
def raw_material_categories(app):
    """Create raw material categories: OIL, ETHANOL, BOTTLE"""
    with app.app_context():
        categories = []

        oil_cat = RawMaterialCategory(
            code='OIL',
            name='Fragrance Oils',
            unit='ml',
            is_active=True
        )
        db.session.add(oil_cat)

        ethanol_cat = RawMaterialCategory(
            code='ETHANOL',
            name='Ethanol/Alcohol',
            unit='ml',
            is_active=True
        )
        db.session.add(ethanol_cat)

        bottle_cat = RawMaterialCategory(
            code='BOTTLE',
            name='Bottles',
            unit='pieces',
            is_active=True
        )
        db.session.add(bottle_cat)

        db.session.commit()

        # Refresh to get IDs
        db.session.refresh(oil_cat)
        db.session.refresh(ethanol_cat)
        db.session.refresh(bottle_cat)

        return {
            'oil': oil_cat,
            'ethanol': ethanol_cat,
            'bottle': bottle_cat
        }


@pytest.fixture
def raw_materials(app, raw_material_categories):
    """Create test raw materials"""
    with app.app_context():
        materials = {}

        # Oils
        oud_oil = RawMaterial(
            code='OIL-OUD',
            name='Oud Oil',
            category_id=raw_material_categories['oil'].id,
            cost_per_unit=Decimal('50.00'),
            reorder_level=100,
            is_active=True
        )
        db.session.add(oud_oil)

        rose_oil = RawMaterial(
            code='OIL-ROSE',
            name='Rose Oil',
            category_id=raw_material_categories['oil'].id,
            cost_per_unit=Decimal('30.00'),
            reorder_level=100,
            is_active=True
        )
        db.session.add(rose_oil)

        musk_oil = RawMaterial(
            code='OIL-MUSK',
            name='Musk Oil',
            category_id=raw_material_categories['oil'].id,
            cost_per_unit=Decimal('25.00'),
            reorder_level=100,
            is_active=True
        )
        db.session.add(musk_oil)

        # Ethanol
        ethanol = RawMaterial(
            code='ETHANOL-PURE',
            name='Pure Ethanol',
            category_id=raw_material_categories['ethanol'].id,
            cost_per_unit=Decimal('5.00'),
            reorder_level=1000,
            is_active=True
        )
        db.session.add(ethanol)

        # Bottles
        bottle_6ml = RawMaterial(
            code='BTL-6ML',
            name='6ml Attar Bottle',
            category_id=raw_material_categories['bottle'].id,
            bottle_size_ml=Decimal('6'),
            cost_per_unit=Decimal('10.00'),
            reorder_level=200,
            is_active=True
        )
        db.session.add(bottle_6ml)

        bottle_50ml = RawMaterial(
            code='BTL-50ML',
            name='50ml Perfume Bottle',
            category_id=raw_material_categories['bottle'].id,
            bottle_size_ml=Decimal('50'),
            cost_per_unit=Decimal('50.00'),
            reorder_level=100,
            is_active=True
        )
        db.session.add(bottle_50ml)

        db.session.commit()

        # Refresh all
        for material in [oud_oil, rose_oil, musk_oil, ethanol, bottle_6ml, bottle_50ml]:
            db.session.refresh(material)

        materials = {
            'oud_oil': oud_oil,
            'rose_oil': rose_oil,
            'musk_oil': musk_oil,
            'ethanol': ethanol,
            'bottle_6ml': bottle_6ml,
            'bottle_50ml': bottle_50ml
        }

        return materials


@pytest.fixture
def stock_at_warehouse(app, raw_materials, warehouse_location):
    """Create initial stock at warehouse"""
    with app.app_context():
        stocks = {}

        for key, material in raw_materials.items():
            stock = RawMaterialStock(
                raw_material_id=material.id,
                location_id=warehouse_location.id,
                quantity=Decimal('1000') if 'bottle' not in key else Decimal('500'),
                reserved_quantity=Decimal('0')
            )
            db.session.add(stock)
            stocks[key] = stock

        db.session.commit()

        for stock in stocks.values():
            db.session.refresh(stock)

        return stocks


@pytest.fixture
def test_product(app):
    """Create a test product for production output"""
    with app.app_context():
        product = Product(
            code='PRD-OUD-6ML',
            name='Oud Attar 6ml',
            selling_price=Decimal('500.00'),
            cost_price=Decimal('200.00'),
            is_active=True,
            is_manufactured=True,
            product_type='manufactured'
        )
        db.session.add(product)
        db.session.commit()
        db.session.refresh(product)
        return product


@pytest.fixture
def perfume_product(app):
    """Create a perfume product"""
    with app.app_context():
        product = Product(
            code='PRD-PERF-50ML',
            name='Oud Perfume 50ml',
            selling_price=Decimal('1500.00'),
            cost_price=Decimal('500.00'),
            is_active=True,
            is_manufactured=True,
            product_type='manufactured'
        )
        db.session.add(product)
        db.session.commit()
        db.session.refresh(product)
        return product


@pytest.fixture
def single_oil_recipe(app, test_product, raw_materials, test_user):
    """Create a single oil attar recipe"""
    with app.app_context():
        recipe = Recipe(
            code='RCP-OUD-6ML',
            name='Pure Oud Attar 6ml',
            recipe_type='single_oil',
            product_id=test_product.id,
            output_size_ml=Decimal('6'),
            oil_percentage=Decimal('100'),
            can_produce_at_warehouse=True,
            can_produce_at_kiosk=True,
            is_active=True,
            created_by=test_user.id
        )
        db.session.add(recipe)
        db.session.flush()

        # Add oil ingredient (100%)
        oil_ingredient = RecipeIngredient(
            recipe_id=recipe.id,
            raw_material_id=raw_materials['oud_oil'].id,
            percentage=Decimal('100'),
            is_packaging=False
        )
        db.session.add(oil_ingredient)

        # Add bottle packaging
        bottle_ingredient = RecipeIngredient(
            recipe_id=recipe.id,
            raw_material_id=raw_materials['bottle_6ml'].id,
            is_packaging=True
        )
        db.session.add(bottle_ingredient)

        db.session.commit()
        db.session.refresh(recipe)
        return recipe


@pytest.fixture
def blended_recipe(app, test_product, raw_materials, test_user):
    """Create a blended oil attar recipe"""
    with app.app_context():
        recipe = Recipe(
            code='RCP-BLEND-6ML',
            name='Blended Attar 6ml',
            recipe_type='blended',
            product_id=test_product.id,
            output_size_ml=Decimal('6'),
            oil_percentage=Decimal('100'),
            can_produce_at_warehouse=True,
            can_produce_at_kiosk=True,
            is_active=True,
            created_by=test_user.id
        )
        db.session.add(recipe)
        db.session.flush()

        # Oud 40%
        oud_ing = RecipeIngredient(
            recipe_id=recipe.id,
            raw_material_id=raw_materials['oud_oil'].id,
            percentage=Decimal('40'),
            is_packaging=False
        )
        db.session.add(oud_ing)

        # Rose 35%
        rose_ing = RecipeIngredient(
            recipe_id=recipe.id,
            raw_material_id=raw_materials['rose_oil'].id,
            percentage=Decimal('35'),
            is_packaging=False
        )
        db.session.add(rose_ing)

        # Musk 25%
        musk_ing = RecipeIngredient(
            recipe_id=recipe.id,
            raw_material_id=raw_materials['musk_oil'].id,
            percentage=Decimal('25'),
            is_packaging=False
        )
        db.session.add(musk_ing)

        # Bottle
        bottle_ing = RecipeIngredient(
            recipe_id=recipe.id,
            raw_material_id=raw_materials['bottle_6ml'].id,
            is_packaging=True
        )
        db.session.add(bottle_ing)

        db.session.commit()
        db.session.refresh(recipe)
        return recipe


@pytest.fixture
def perfume_recipe(app, perfume_product, raw_materials, test_user):
    """Create a perfume recipe (35% oil, 65% ethanol)"""
    with app.app_context():
        recipe = Recipe(
            code='RCP-PERF-50ML',
            name='Oud Perfume 50ml',
            recipe_type='perfume',
            product_id=perfume_product.id,
            output_size_ml=Decimal('50'),
            oil_percentage=Decimal('35'),  # 35% oil, 65% ethanol
            can_produce_at_warehouse=True,
            can_produce_at_kiosk=False,  # Perfumes only at warehouse
            is_active=True,
            created_by=test_user.id
        )
        db.session.add(recipe)
        db.session.flush()

        # Oud oil (100% of the oil portion)
        oud_ing = RecipeIngredient(
            recipe_id=recipe.id,
            raw_material_id=raw_materials['oud_oil'].id,
            percentage=Decimal('100'),
            is_packaging=False
        )
        db.session.add(oud_ing)

        # Ethanol
        ethanol_ing = RecipeIngredient(
            recipe_id=recipe.id,
            raw_material_id=raw_materials['ethanol'].id,
            is_packaging=False
        )
        db.session.add(ethanol_ing)

        # Bottle
        bottle_ing = RecipeIngredient(
            recipe_id=recipe.id,
            raw_material_id=raw_materials['bottle_50ml'].id,
            is_packaging=True
        )
        db.session.add(bottle_ing)

        db.session.commit()
        db.session.refresh(recipe)
        return recipe


# ============================================================
# Test Classes
# ============================================================

class TestRawMaterialManagement:
    """Tests for raw material management"""

    def test_create_raw_material_category(self, app):
        """Test creating raw material category"""
        with app.app_context():
            category = RawMaterialCategory(
                code='TEST',
                name='Test Category',
                unit='ml',
                is_active=True
            )
            db.session.add(category)
            db.session.commit()

            saved = RawMaterialCategory.query.filter_by(code='TEST').first()
            assert saved is not None
            assert saved.name == 'Test Category'
            assert saved.unit == 'ml'

    def test_create_raw_material(self, app, raw_material_categories):
        """Test creating raw material"""
        with app.app_context():
            material = RawMaterial(
                code='TEST-OIL',
                name='Test Oil',
                category_id=raw_material_categories['oil'].id,
                cost_per_unit=Decimal('100.00'),
                reorder_level=50,
                is_active=True
            )
            db.session.add(material)
            db.session.commit()

            saved = RawMaterial.query.filter_by(code='TEST-OIL').first()
            assert saved is not None
            assert saved.name == 'Test Oil'
            assert float(saved.cost_per_unit) == 100.00
            assert saved.unit == 'ml'  # From category

    def test_raw_material_stock_tracking(self, app, raw_materials, warehouse_location):
        """Test raw material stock tracking at location"""
        with app.app_context():
            # Create stock record
            stock = RawMaterialStock(
                raw_material_id=raw_materials['oud_oil'].id,
                location_id=warehouse_location.id,
                quantity=Decimal('500'),
                reserved_quantity=Decimal('100')
            )
            db.session.add(stock)
            db.session.commit()

            saved = RawMaterialStock.query.filter_by(
                raw_material_id=raw_materials['oud_oil'].id,
                location_id=warehouse_location.id
            ).first()

            assert saved is not None
            assert float(saved.quantity) == 500
            assert float(saved.reserved_quantity) == 100
            assert saved.available_quantity == 400  # 500 - 100

    def test_raw_material_low_stock_detection(self, app, raw_materials, warehouse_location):
        """Test low stock detection"""
        with app.app_context():
            # Create stock below reorder level
            stock = RawMaterialStock(
                raw_material_id=raw_materials['oud_oil'].id,
                location_id=warehouse_location.id,
                quantity=Decimal('50'),  # Below reorder level of 100
                reserved_quantity=Decimal('0')
            )
            db.session.add(stock)
            db.session.commit()

            saved = RawMaterialStock.query.filter_by(
                raw_material_id=raw_materials['oud_oil'].id
            ).first()

            assert saved.is_low_stock is True

    def test_raw_material_movement_recording(self, app, raw_materials, warehouse_location, test_user):
        """Test recording raw material movements"""
        with app.app_context():
            movement = RawMaterialMovement(
                raw_material_id=raw_materials['oud_oil'].id,
                location_id=warehouse_location.id,
                user_id=test_user.id,
                movement_type='purchase',
                quantity=Decimal('500'),
                reference='PO-001',
                notes='Initial purchase'
            )
            db.session.add(movement)
            db.session.commit()

            saved = RawMaterialMovement.query.first()
            assert saved is not None
            assert saved.movement_type == 'purchase'
            assert float(saved.quantity) == 500

    def test_decimal_precision_in_quantities(self, app, raw_materials, warehouse_location):
        """Test decimal precision for quantities (e.g., 0.0001)"""
        with app.app_context():
            stock = RawMaterialStock(
                raw_material_id=raw_materials['oud_oil'].id,
                location_id=warehouse_location.id,
                quantity=Decimal('123.4567'),
                reserved_quantity=Decimal('0.1234')
            )
            db.session.add(stock)
            db.session.commit()

            saved = RawMaterialStock.query.first()
            # Check precision is maintained
            assert Decimal(str(saved.quantity)) == Decimal('123.4567')
            assert Decimal(str(saved.reserved_quantity)) == Decimal('0.1234')


class TestRecipeCreationAndValidation:
    """Tests for recipe creation and validation"""

    def test_create_single_oil_recipe(self, app, test_product, raw_materials, test_user):
        """Test creating a single oil recipe"""
        with app.app_context():
            recipe = Recipe(
                code='RCP-TEST',
                name='Test Single Oil',
                recipe_type='single_oil',
                product_id=test_product.id,
                output_size_ml=Decimal('6'),
                oil_percentage=Decimal('100'),
                can_produce_at_warehouse=True,
                can_produce_at_kiosk=True,
                is_active=True,
                created_by=test_user.id
            )
            db.session.add(recipe)
            db.session.commit()

            saved = Recipe.query.filter_by(code='RCP-TEST').first()
            assert saved is not None
            assert saved.recipe_type == 'single_oil'
            assert float(saved.oil_percentage) == 100

    def test_create_blended_recipe(self, app, test_product, raw_materials, test_user):
        """Test creating a blended recipe with multiple oils"""
        with app.app_context():
            recipe = Recipe(
                code='RCP-BLEND',
                name='Blended Test',
                recipe_type='blended',
                product_id=test_product.id,
                output_size_ml=Decimal('6'),
                oil_percentage=Decimal('100'),
                is_active=True,
                created_by=test_user.id
            )
            db.session.add(recipe)
            db.session.flush()

            # Add ingredients with percentages summing to 100%
            percentages = [40, 35, 25]  # Should sum to 100
            oils = [raw_materials['oud_oil'], raw_materials['rose_oil'], raw_materials['musk_oil']]

            for oil, pct in zip(oils, percentages):
                ing = RecipeIngredient(
                    recipe_id=recipe.id,
                    raw_material_id=oil.id,
                    percentage=Decimal(str(pct)),
                    is_packaging=False
                )
                db.session.add(ing)

            db.session.commit()

            # Verify ingredients sum to 100%
            total_pct = sum(float(i.percentage or 0) for i in recipe.oil_ingredients)
            assert total_pct == 100

    def test_recipe_with_invalid_percentages_not_100(self, app, test_product, raw_materials, test_user):
        """Test that we can detect when oil percentages don't sum to 100%"""
        with app.app_context():
            recipe = Recipe(
                code='RCP-INVALID',
                name='Invalid Blend',
                recipe_type='blended',
                product_id=test_product.id,
                output_size_ml=Decimal('6'),
                oil_percentage=Decimal('100'),
                is_active=True,
                created_by=test_user.id
            )
            db.session.add(recipe)
            db.session.flush()

            # Add ingredients with percentages NOT summing to 100%
            percentages = [40, 30, 20]  # Sum is 90%, not 100%
            oils = [raw_materials['oud_oil'], raw_materials['rose_oil'], raw_materials['musk_oil']]

            for oil, pct in zip(oils, percentages):
                ing = RecipeIngredient(
                    recipe_id=recipe.id,
                    raw_material_id=oil.id,
                    percentage=Decimal(str(pct)),
                    is_packaging=False
                )
                db.session.add(ing)

            db.session.commit()

            # Verify percentages don't sum to 100%
            total_pct = sum(float(i.percentage or 0) for i in recipe.oil_ingredients)
            assert total_pct != 100  # Should be 90
            assert total_pct == 90

    def test_perfume_recipe_oil_percentage(self, app, perfume_product, raw_materials, test_user):
        """Test perfume recipe with oil percentage (35% oil, 65% ethanol)"""
        with app.app_context():
            recipe = Recipe(
                code='RCP-PERF-TEST',
                name='Test Perfume',
                recipe_type='perfume',
                product_id=perfume_product.id,
                output_size_ml=Decimal('50'),
                oil_percentage=Decimal('35'),
                can_produce_at_warehouse=True,
                can_produce_at_kiosk=False,
                is_active=True,
                created_by=test_user.id
            )
            db.session.add(recipe)
            db.session.commit()

            saved = Recipe.query.filter_by(code='RCP-PERF-TEST').first()
            assert saved.recipe_type == 'perfume'
            assert float(saved.oil_percentage) == 35
            assert saved.can_produce_at_kiosk is False  # Perfumes only at warehouse

    def test_recipe_ingredient_list(self, app, single_oil_recipe):
        """Test getting ingredients list from recipe"""
        with app.app_context():
            recipe = Recipe.query.get(single_oil_recipe.id)

            ingredients = recipe.ingredients_list
            assert len(ingredients) == 2  # Oil + Bottle

            oil_ingredients = recipe.oil_ingredients
            assert len(oil_ingredients) == 1

            bottle = recipe.bottle_ingredient
            assert bottle is not None
            assert bottle.is_packaging is True


class TestMaterialRequirementsCalculation:
    """Tests for material requirements calculation"""

    def test_calculate_single_oil_requirements(self, app, single_oil_recipe):
        """Test calculating requirements for single oil attar"""
        with app.app_context():
            # Produce 10 bottles of 6ml attar
            result = ProductionService.calculate_material_requirements(
                single_oil_recipe.id, 10
            )

            assert 'error' not in result
            assert result['quantity'] == 10
            assert result['total_output_ml'] == 60  # 10 * 6ml
            assert result['oil_amount_ml'] == 60  # 100% oil
            assert result['ethanol_amount_ml'] == 0  # No ethanol for attars

            # Check materials
            materials = result['materials']
            oil_mat = next((m for m in materials if not m['is_packaging']), None)
            bottle_mat = next((m for m in materials if m['is_packaging']), None)

            assert oil_mat is not None
            assert oil_mat['quantity_required'] == 60  # 60ml of oil

            assert bottle_mat is not None
            assert bottle_mat['quantity_required'] == 10  # 10 bottles

    def test_calculate_blended_requirements(self, app, blended_recipe):
        """Test calculating requirements for blended attar"""
        with app.app_context():
            # Produce 10 bottles of 6ml blended attar
            result = ProductionService.calculate_material_requirements(
                blended_recipe.id, 10
            )

            assert 'error' not in result
            assert result['total_output_ml'] == 60  # 10 * 6ml

            materials = result['materials']
            oil_materials = [m for m in materials if not m['is_packaging']]

            # Check percentages
            # Oud: 40% of 60ml = 24ml
            # Rose: 35% of 60ml = 21ml
            # Musk: 25% of 60ml = 15ml
            oud_mat = next((m for m in oil_materials if 'Oud' in m['name']), None)
            rose_mat = next((m for m in oil_materials if 'Rose' in m['name']), None)
            musk_mat = next((m for m in oil_materials if 'Musk' in m['name']), None)

            assert oud_mat is not None
            assert oud_mat['quantity_required'] == 24  # 40% of 60ml

            assert rose_mat is not None
            assert rose_mat['quantity_required'] == 21  # 35% of 60ml

            assert musk_mat is not None
            assert musk_mat['quantity_required'] == 15  # 25% of 60ml

    def test_calculate_perfume_requirements(self, app, perfume_recipe):
        """Test calculating requirements for perfume (oil + ethanol)"""
        with app.app_context():
            # Produce 10 bottles of 50ml perfume (35% oil, 65% ethanol)
            result = ProductionService.calculate_material_requirements(
                perfume_recipe.id, 10
            )

            assert 'error' not in result
            assert result['total_output_ml'] == 500  # 10 * 50ml
            assert result['oil_amount_ml'] == 175  # 35% of 500ml
            assert result['ethanol_amount_ml'] == 325  # 65% of 500ml

    def test_calculate_zero_quantity(self, app, single_oil_recipe):
        """Test calculating requirements for zero quantity"""
        with app.app_context():
            result = ProductionService.calculate_material_requirements(
                single_oil_recipe.id, 0
            )

            assert 'error' not in result
            assert result['total_output_ml'] == 0
            assert result['oil_amount_ml'] == 0

    def test_calculate_nonexistent_recipe(self, app):
        """Test calculating requirements for non-existent recipe"""
        with app.app_context():
            result = ProductionService.calculate_material_requirements(99999, 10)
            assert 'error' in result
            assert result['error'] == 'Recipe not found'

    def test_decimal_precision_in_calculations(self, app, blended_recipe):
        """Test decimal precision is maintained in calculations"""
        with app.app_context():
            # Produce 3 bottles - will create non-integer oil amounts
            result = ProductionService.calculate_material_requirements(
                blended_recipe.id, 3
            )

            # Total: 3 * 6ml = 18ml
            # Oud (40%): 7.2ml
            # Rose (35%): 6.3ml
            # Musk (25%): 4.5ml

            materials = result['materials']
            oud_mat = next((m for m in materials if 'Oud' in m['name'] and not m['is_packaging']), None)

            # Should be precise
            assert oud_mat['quantity_required'] == 7.2


class TestMaterialAvailabilityChecking:
    """Tests for material availability checking"""

    def test_check_availability_all_available(self, app, single_oil_recipe, stock_at_warehouse, warehouse_location):
        """Test checking availability when all materials are available"""
        with app.app_context():
            result = ProductionService.check_material_availability(
                single_oil_recipe.id, 10, warehouse_location.id
            )

            assert 'error' not in result
            assert result['all_available'] is True

            for material in result['materials']:
                assert material['is_available'] is True
                assert material['shortage'] == 0

    def test_check_availability_insufficient_materials(self, app, single_oil_recipe, warehouse_location, raw_materials):
        """Test checking availability with insufficient materials"""
        with app.app_context():
            # Create very limited stock
            stock = RawMaterialStock(
                raw_material_id=raw_materials['oud_oil'].id,
                location_id=warehouse_location.id,
                quantity=Decimal('10'),  # Only 10ml
                reserved_quantity=Decimal('0')
            )
            db.session.add(stock)
            db.session.commit()

            # Try to produce 10 bottles (needs 60ml)
            result = ProductionService.check_material_availability(
                single_oil_recipe.id, 10, warehouse_location.id
            )

            assert result['all_available'] is False

            oil_mat = next((m for m in result['materials'] if 'Oud' in m['name']), None)
            assert oil_mat['is_available'] is False
            assert oil_mat['shortage'] == 50  # Need 60, have 10

    def test_check_availability_perfume_at_kiosk(self, app, perfume_recipe, kiosk_location, stock_at_warehouse):
        """Test that perfume cannot be produced at kiosk"""
        with app.app_context():
            result = ProductionService.check_material_availability(
                perfume_recipe.id, 10, kiosk_location.id
            )

            assert 'error' in result
            assert 'warehouse' in result['error'].lower()

    def test_check_availability_nonexistent_location(self, app, single_oil_recipe):
        """Test checking availability at non-existent location"""
        with app.app_context():
            result = ProductionService.check_material_availability(
                single_oil_recipe.id, 10, 99999
            )

            assert 'error' in result
            assert result['error'] == 'Location not found'

    def test_reserved_quantity_affects_availability(self, app, single_oil_recipe, warehouse_location, raw_materials):
        """Test that reserved quantity affects available quantity"""
        with app.app_context():
            # Create stock with most reserved
            stock = RawMaterialStock(
                raw_material_id=raw_materials['oud_oil'].id,
                location_id=warehouse_location.id,
                quantity=Decimal('100'),
                reserved_quantity=Decimal('90')  # Only 10 available
            )
            db.session.add(stock)
            db.session.commit()

            # Try to produce 10 bottles (needs 60ml)
            result = ProductionService.check_material_availability(
                single_oil_recipe.id, 10, warehouse_location.id
            )

            assert result['all_available'] is False


class TestProductionOrderWorkflow:
    """Tests for production order workflow"""

    def test_create_production_order(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test creating a production order"""
        with app.app_context():
            order, error = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id,
                priority='normal',
                notes='Test production'
            )

            assert error is None
            assert order is not None
            assert order.status == 'draft'
            assert order.quantity_ordered == 10
            assert order.order_number.startswith('PRD')

    def test_create_order_auto_submit(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test creating order with auto-submit"""
        with app.app_context():
            order, error = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id,
                auto_submit=True
            )

            assert error is None
            assert order.status == 'pending'  # Auto-submitted

    def test_create_perfume_order_at_kiosk_fails(self, app, perfume_recipe, kiosk_location, test_user):
        """Test that creating perfume order at kiosk fails"""
        with app.app_context():
            order, error = ProductionService.create_production_order(
                recipe_id=perfume_recipe.id,
                quantity=10,
                location_id=kiosk_location.id,
                user_id=test_user.id
            )

            assert order is None
            assert error is not None
            assert 'warehouse' in error.lower()

    def test_submit_order(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test submitting a draft order"""
        with app.app_context():
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id
            )

            success, error = ProductionService.submit_order(order.id)

            assert success is True
            assert error is None

            db.session.refresh(order)
            assert order.status == 'pending'

    def test_approve_order(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test approving a pending order"""
        with app.app_context():
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id,
                auto_submit=True
            )

            success, error = ProductionService.approve_order(order.id, test_user.id)

            assert success is True
            assert error is None

            db.session.refresh(order)
            assert order.status == 'approved'
            assert order.approved_by == test_user.id

    def test_approve_order_insufficient_materials(self, app, single_oil_recipe, warehouse_location, test_user, raw_materials):
        """Test approving order with insufficient materials fails"""
        with app.app_context():
            # Create very limited stock
            stock = RawMaterialStock(
                raw_material_id=raw_materials['oud_oil'].id,
                location_id=warehouse_location.id,
                quantity=Decimal('10'),
                reserved_quantity=Decimal('0')
            )
            db.session.add(stock)
            db.session.commit()

            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,  # Needs 60ml
                location_id=warehouse_location.id,
                user_id=test_user.id,
                auto_submit=True
            )

            success, error = ProductionService.approve_order(order.id, test_user.id)

            assert success is False
            assert 'insufficient' in error.lower()

    def test_reject_order(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test rejecting an order"""
        with app.app_context():
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id,
                auto_submit=True
            )

            success, error = ProductionService.reject_order(
                order.id, test_user.id, 'Testing rejection'
            )

            assert success is True

            db.session.refresh(order)
            assert order.status == 'rejected'
            assert order.rejection_reason == 'Testing rejection'

    def test_start_production(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test starting production"""
        with app.app_context():
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, test_user.id)

            success, error = ProductionService.start_production(order.id, test_user.id)

            assert success is True

            db.session.refresh(order)
            assert order.status == 'in_progress'
            assert order.started_at is not None

    def test_complete_production(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse, test_product):
        """Test completing production - deducts materials, adds products"""
        with app.app_context():
            # Get initial stock levels
            oil_stock = RawMaterialStock.query.filter_by(
                location_id=warehouse_location.id
            ).filter(RawMaterialStock.raw_material.has(code='OIL-OUD')).first()
            initial_oil_qty = float(oil_stock.quantity)

            # Create and process order
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, test_user.id)
            ProductionService.start_production(order.id, test_user.id)

            success, error = ProductionService.execute_production(
                order.id, test_user.id, quantity_produced=10
            )

            assert success is True

            db.session.refresh(order)
            assert order.status == 'completed'
            assert order.quantity_produced == 10

            # Check materials deducted
            db.session.refresh(oil_stock)
            assert float(oil_stock.quantity) == initial_oil_qty - 60  # 10 * 6ml

            # Check product added to inventory
            product = Product.query.get(test_product.id)
            assert product.quantity >= 10  # At least 10 added

    def test_cancel_order(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test cancelling an order"""
        with app.app_context():
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id,
                auto_submit=True
            )

            success, error = ProductionService.cancel_order(
                order.id, test_user.id, 'Cancelled for testing'
            )

            assert success is True

            db.session.refresh(order)
            assert order.status == 'cancelled'

    def test_cancel_approved_order_releases_reserved(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test cancelling approved order releases reserved materials"""
        with app.app_context():
            # Create and approve order (reserves materials)
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, test_user.id)

            # Check materials are reserved
            oil_stock = RawMaterialStock.query.filter_by(
                location_id=warehouse_location.id
            ).filter(RawMaterialStock.raw_material.has(code='OIL-OUD')).first()
            reserved_before = float(oil_stock.reserved_quantity)
            assert reserved_before > 0

            # Cancel order
            ProductionService.cancel_order(order.id, test_user.id, 'Cancel test')

            # Check reserved released
            db.session.refresh(oil_stock)
            assert float(oil_stock.reserved_quantity) < reserved_before


class TestProductionStatusTransitions:
    """Tests for valid and invalid status transitions"""

    def test_valid_status_transitions(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test valid status transition flow"""
        with app.app_context():
            # draft -> pending -> approved -> in_progress -> completed
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id
            )
            assert order.status == 'draft'

            ProductionService.submit_order(order.id)
            db.session.refresh(order)
            assert order.status == 'pending'

            ProductionService.approve_order(order.id, test_user.id)
            db.session.refresh(order)
            assert order.status == 'approved'

            ProductionService.start_production(order.id, test_user.id)
            db.session.refresh(order)
            assert order.status == 'in_progress'

            ProductionService.execute_production(order.id, test_user.id)
            db.session.refresh(order)
            assert order.status == 'completed'

    def test_cannot_approve_draft_order(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test that draft orders cannot be directly approved"""
        with app.app_context():
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id
            )

            success, error = ProductionService.approve_order(order.id, test_user.id)

            assert success is False
            assert 'status' in error.lower()

    def test_cannot_start_pending_order(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test that pending orders cannot be started (must be approved first)"""
        with app.app_context():
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id,
                auto_submit=True
            )

            success, error = ProductionService.start_production(order.id, test_user.id)

            assert success is False

    def test_cannot_complete_approved_order(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test that approved orders cannot be completed (must be in_progress)"""
        with app.app_context():
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, test_user.id)

            success, error = ProductionService.execute_production(order.id, test_user.id)

            assert success is False

    def test_cannot_cancel_completed_order(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test that completed orders cannot be cancelled"""
        with app.app_context():
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, test_user.id)
            ProductionService.start_production(order.id, test_user.id)
            ProductionService.execute_production(order.id, test_user.id)

            success, error = ProductionService.cancel_order(order.id, test_user.id)

            assert success is False


class TestLocationRestrictions:
    """Tests for location restrictions (perfumes at warehouse only)"""

    def test_attar_can_be_produced_at_warehouse(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test that attars can be produced at warehouse"""
        with app.app_context():
            result = ProductionService.check_material_availability(
                single_oil_recipe.id, 10, warehouse_location.id
            )

            assert 'error' not in result

    def test_attar_can_be_produced_at_kiosk(self, app, single_oil_recipe, kiosk_location, test_user, raw_materials):
        """Test that attars can be produced at kiosk"""
        with app.app_context():
            # Create stock at kiosk
            for key, material in raw_materials.items():
                stock = RawMaterialStock(
                    raw_material_id=material.id,
                    location_id=kiosk_location.id,
                    quantity=Decimal('1000'),
                    reserved_quantity=Decimal('0')
                )
                db.session.add(stock)
            db.session.commit()

            result = ProductionService.check_material_availability(
                single_oil_recipe.id, 10, kiosk_location.id
            )

            assert 'error' not in result
            assert result['all_available'] is True

    def test_perfume_can_be_produced_at_warehouse(self, app, perfume_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test that perfumes can be produced at warehouse"""
        with app.app_context():
            result = ProductionService.check_material_availability(
                perfume_recipe.id, 10, warehouse_location.id
            )

            # Should not have location restriction error
            if 'error' in result:
                assert 'warehouse' not in result['error'].lower() or 'cannot' not in result['error'].lower()

    def test_perfume_cannot_be_produced_at_kiosk(self, app, perfume_recipe, kiosk_location, test_user, raw_materials):
        """Test that perfumes CANNOT be produced at kiosk"""
        with app.app_context():
            # Create stock at kiosk
            for key, material in raw_materials.items():
                stock = RawMaterialStock(
                    raw_material_id=material.id,
                    location_id=kiosk_location.id,
                    quantity=Decimal('10000'),
                    reserved_quantity=Decimal('0')
                )
                db.session.add(stock)
            db.session.commit()

            # Try to check availability - should fail due to location restriction
            result = ProductionService.check_material_availability(
                perfume_recipe.id, 10, kiosk_location.id
            )

            assert 'error' in result
            assert 'warehouse' in result['error'].lower()

    def test_perfume_order_at_kiosk_fails(self, app, perfume_recipe, kiosk_location, test_user):
        """Test that creating perfume production order at kiosk fails"""
        with app.app_context():
            order, error = ProductionService.create_production_order(
                recipe_id=perfume_recipe.id,
                quantity=10,
                location_id=kiosk_location.id,
                user_id=test_user.id
            )

            assert order is None
            assert error is not None
            assert 'warehouse' in error.lower()


class TestMaterialConsumption:
    """Tests for material consumption during production"""

    def test_material_consumption_recorded(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test that material consumption is properly recorded"""
        with app.app_context():
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, test_user.id)
            ProductionService.start_production(order.id, test_user.id)
            ProductionService.execute_production(order.id, test_user.id)

            # Check consumption records
            consumptions = ProductionMaterialConsumption.query.filter_by(
                production_order_id=order.id
            ).all()

            assert len(consumptions) > 0

            for consumption in consumptions:
                assert consumption.quantity_consumed > 0
                assert consumption.quantity_required == consumption.quantity_consumed

    def test_material_movement_recorded(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test that material movements are recorded during production"""
        with app.app_context():
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, test_user.id)
            ProductionService.start_production(order.id, test_user.id)
            ProductionService.execute_production(order.id, test_user.id)

            # Check movement records
            movements = RawMaterialMovement.query.filter_by(
                production_order_id=order.id
            ).all()

            assert len(movements) > 0

            for movement in movements:
                assert movement.movement_type == 'production_consumption'
                assert float(movement.quantity) < 0  # Negative for consumption


class TestCostCalculations:
    """Tests for cost calculations in production"""

    def test_raw_material_cost_tracking(self, app, raw_materials):
        """Test that raw material costs are properly tracked"""
        with app.app_context():
            oud = RawMaterial.query.filter_by(code='OIL-OUD').first()

            assert float(oud.cost_per_unit) == 50.00

    def test_production_cost_calculation(self, app, single_oil_recipe, raw_materials):
        """Test calculating total production cost"""
        with app.app_context():
            # Calculate requirements for 10 bottles
            result = ProductionService.calculate_material_requirements(
                single_oil_recipe.id, 10
            )

            # Calculate expected cost
            # Oil: 60ml * 50 Rs/ml = 3000 Rs
            # Bottles: 10 * 10 Rs = 100 Rs
            # Total: 3100 Rs

            total_cost = Decimal('0')
            for material in result['materials']:
                raw_mat = RawMaterial.query.get(material['raw_material_id'])
                cost = Decimal(str(material['quantity_required'])) * raw_mat.cost_per_unit
                total_cost += cost

            # Oud oil: 60 * 50 = 3000
            # Bottle: 10 * 10 = 100
            assert total_cost == Decimal('3100')


class TestEdgeCases:
    """Tests for edge cases"""

    def test_zero_quantity_production(self, app, single_oil_recipe, warehouse_location, test_user):
        """Test handling of zero quantity production"""
        with app.app_context():
            result = ProductionService.calculate_material_requirements(
                single_oil_recipe.id, 0
            )

            assert result['total_output_ml'] == 0
            assert result['oil_amount_ml'] == 0

    def test_very_large_quantity(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test handling of very large production quantities"""
        with app.app_context():
            # Try to produce 1 million bottles
            result = ProductionService.calculate_material_requirements(
                single_oil_recipe.id, 1000000
            )

            assert result['total_output_ml'] == 6000000  # 1M * 6ml
            assert result['oil_amount_ml'] == 6000000

    def test_concurrent_order_creation(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test that order numbers are unique for concurrent orders"""
        with app.app_context():
            orders = []
            for _ in range(5):
                order, _ = ProductionService.create_production_order(
                    recipe_id=single_oil_recipe.id,
                    quantity=10,
                    location_id=warehouse_location.id,
                    user_id=test_user.id
                )
                orders.append(order)

            # All order numbers should be unique
            order_numbers = [o.order_number for o in orders]
            assert len(order_numbers) == len(set(order_numbers))

    def test_partial_production(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test producing less than ordered quantity"""
        with app.app_context():
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, test_user.id)
            ProductionService.start_production(order.id, test_user.id)

            # Produce only 7 out of 10
            success, error = ProductionService.execute_production(
                order.id, test_user.id, quantity_produced=7
            )

            assert success is True

            db.session.refresh(order)
            assert order.quantity_ordered == 10
            assert order.quantity_produced == 7

    def test_recipe_without_product(self, app, raw_materials, test_user, warehouse_location):
        """Test creating order for recipe without output product fails"""
        with app.app_context():
            recipe = Recipe(
                code='RCP-NOPROD',
                name='No Product Recipe',
                recipe_type='single_oil',
                product_id=None,  # No product
                output_size_ml=Decimal('6'),
                oil_percentage=Decimal('100'),
                is_active=True,
                created_by=test_user.id
            )
            db.session.add(recipe)
            db.session.commit()

            order, error = ProductionService.create_production_order(
                recipe_id=recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id
            )

            assert order is None
            assert error is not None
            assert 'product' in error.lower()

    def test_insufficient_stock_for_completion(self, app, single_oil_recipe, warehouse_location, test_user, raw_materials):
        """Test production fails when stock runs out between approval and execution"""
        with app.app_context():
            # Create limited stock
            oil_stock = RawMaterialStock(
                raw_material_id=raw_materials['oud_oil'].id,
                location_id=warehouse_location.id,
                quantity=Decimal('100'),
                reserved_quantity=Decimal('0')
            )
            bottle_stock = RawMaterialStock(
                raw_material_id=raw_materials['bottle_6ml'].id,
                location_id=warehouse_location.id,
                quantity=Decimal('100'),
                reserved_quantity=Decimal('0')
            )
            db.session.add(oil_stock)
            db.session.add(bottle_stock)
            db.session.commit()

            # Create and approve order for 10 bottles (needs 60ml oil)
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id,
                auto_submit=True
            )
            ProductionService.approve_order(order.id, test_user.id)
            ProductionService.start_production(order.id, test_user.id)

            # Reduce stock before execution
            oil_stock.quantity = Decimal('10')  # Not enough
            db.session.commit()

            # Try to execute
            success, error = ProductionService.execute_production(
                order.id, test_user.id
            )

            assert success is False
            assert 'insufficient' in error.lower()


class TestProductionStats:
    """Tests for production statistics"""

    def test_get_production_stats(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test getting production statistics"""
        with app.app_context():
            # Create some orders in different statuses
            for _ in range(3):
                order, _ = ProductionService.create_production_order(
                    recipe_id=single_oil_recipe.id,
                    quantity=10,
                    location_id=warehouse_location.id,
                    user_id=test_user.id,
                    auto_submit=True
                )

            stats = ProductionService.get_production_stats(warehouse_location.id)

            assert 'status_counts' in stats
            assert 'pending_count' in stats
            assert stats['pending_count'] == 3

    def test_get_low_stock_materials(self, app, raw_materials, warehouse_location):
        """Test getting low stock materials"""
        with app.app_context():
            # Create low stock
            stock = RawMaterialStock(
                raw_material_id=raw_materials['oud_oil'].id,
                location_id=warehouse_location.id,
                quantity=Decimal('50'),  # Below reorder level of 100
                reserved_quantity=Decimal('0')
            )
            db.session.add(stock)
            db.session.commit()

            low_stock = ProductionService.get_low_stock_materials(warehouse_location.id)

            assert len(low_stock) > 0
            assert any(item['material'].code == 'OIL-OUD' for item in low_stock)


class TestOrderNumberGeneration:
    """Tests for order number generation"""

    def test_order_number_format(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test order number follows correct format"""
        with app.app_context():
            order, _ = ProductionService.create_production_order(
                recipe_id=single_oil_recipe.id,
                quantity=10,
                location_id=warehouse_location.id,
                user_id=test_user.id
            )

            # Format: PRD + YYYYMMDD + 4-digit sequence
            assert order.order_number.startswith('PRD')
            assert len(order.order_number) == 16  # PRD + 8 date digits + 4 sequence digits

    def test_order_number_sequence(self, app, single_oil_recipe, warehouse_location, test_user, stock_at_warehouse):
        """Test order numbers increment correctly"""
        with app.app_context():
            orders = []
            for _ in range(3):
                order, _ = ProductionService.create_production_order(
                    recipe_id=single_oil_recipe.id,
                    quantity=10,
                    location_id=warehouse_location.id,
                    user_id=test_user.id
                )
                orders.append(order)

            # Extract sequence numbers
            sequences = [int(o.order_number[-4:]) for o in orders]

            # Should be consecutive
            assert sequences == sorted(sequences)
            assert sequences[0] == 1
            assert sequences[1] == 2
            assert sequences[2] == 3


# ============================================================
# Run Tests
# ============================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
