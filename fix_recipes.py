#!/usr/bin/env python3
"""
Fix script to activate all recipes.
Run in production: python fix_recipes.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import Recipe

app = create_app()

with app.app_context():
    # Count inactive recipes
    inactive_count = Recipe.query.filter_by(is_active=False).count()
    print(f"Found {inactive_count} inactive recipes")

    if inactive_count == 0:
        print("All recipes are already active!")
        sys.exit(0)

    # Show what will be activated
    print("\nRecipes to activate:")
    for r in Recipe.query.filter_by(is_active=False).all():
        print(f"  - {r.code}: {r.name}")

    # Confirm
    confirm = input("\nActivate all these recipes? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Cancelled.")
        sys.exit(0)

    # Activate all recipes
    Recipe.query.filter_by(is_active=False).update({'is_active': True})
    db.session.commit()

    print(f"\n✓ Activated {inactive_count} recipes successfully!")
    print("You should now see recipes when creating production orders.")
