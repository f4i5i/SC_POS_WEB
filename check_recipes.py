#!/usr/bin/env python3
"""
Diagnostic script to check why recipes aren't showing in production order creation.
Run this in your production environment:
    python check_recipes.py
"""
import os
import sys

# Add the app to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import Recipe, Product, Location

app = create_app()

with app.app_context():
    print("=" * 60)
    print("PRODUCTION ORDER - RECIPE DIAGNOSTIC")
    print("=" * 60)

    # 1. Check total recipes
    total_recipes = Recipe.query.count()
    print(f"\n1. Total recipes in database: {total_recipes}")

    if total_recipes == 0:
        print("   ⚠️  NO RECIPES FOUND! You need to create recipes first.")
        print("   Go to Production > Recipes > Add Recipe")
        sys.exit(1)

    # 2. Check active recipes
    active_recipes = Recipe.query.filter_by(is_active=True).count()
    print(f"2. Active recipes (is_active=True): {active_recipes}")

    if active_recipes == 0:
        print("   ⚠️  NO ACTIVE RECIPES! All recipes are inactive.")
        print("   To fix: Update recipes to set is_active=True")
        inactive = Recipe.query.filter_by(is_active=False).limit(5).all()
        print("   Inactive recipes:")
        for r in inactive:
            print(f"      - {r.code}: {r.name} (id={r.id})")

    # 3. Check kiosk-producible recipes
    kiosk_recipes = Recipe.query.filter_by(is_active=True, can_produce_at_kiosk=True).count()
    print(f"3. Recipes producible at kiosk: {kiosk_recipes}")

    if kiosk_recipes == 0 and active_recipes > 0:
        print("   ⚠️  No recipes can be produced at kiosk!")
        print("   If you're at a kiosk location, you won't see any recipes.")
        print("   To fix: Set can_produce_at_kiosk=True on recipes")

    # 4. Check warehouse-producible recipes
    warehouse_recipes = Recipe.query.filter_by(is_active=True, can_produce_at_warehouse=True).count()
    print(f"4. Recipes producible at warehouse: {warehouse_recipes}")

    # 5. Check recipes with linked products
    recipes_with_product = Recipe.query.filter(
        Recipe.is_active == True,
        Recipe.product_id.isnot(None)
    ).count()
    print(f"5. Active recipes with linked products: {recipes_with_product}")

    if recipes_with_product < active_recipes:
        print("   ⚠️  Some recipes don't have products linked!")
        unlinked = Recipe.query.filter(
            Recipe.is_active == True,
            Recipe.product_id.is_(None)
        ).all()
        for r in unlinked:
            print(f"      - {r.code}: {r.name} (no product linked)")

    # 6. List all active recipes
    print("\n" + "=" * 60)
    print("ACTIVE RECIPES:")
    print("=" * 60)
    recipes = Recipe.query.filter_by(is_active=True).all()
    if recipes:
        for r in recipes:
            product_name = r.product.name if r.product else "NO PRODUCT LINKED"
            print(f"  ID={r.id} | {r.code} | {r.name}")
            print(f"          Product: {product_name}")
            print(f"          Kiosk: {'Yes' if r.can_produce_at_kiosk else 'No'} | Warehouse: {'Yes' if r.can_produce_at_warehouse else 'No'}")
            print()
    else:
        print("  No active recipes found.")

    # 7. Check locations
    print("\n" + "=" * 60)
    print("ACTIVE LOCATIONS:")
    print("=" * 60)
    locations = Location.query.filter_by(is_active=True).all()
    for loc in locations:
        print(f"  {loc.code} | {loc.name} | Type: {loc.location_type}")

    print("\n" + "=" * 60)
    print("DIAGNOSIS COMPLETE")
    print("=" * 60)
