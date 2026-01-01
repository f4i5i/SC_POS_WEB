#!/usr/bin/env python3
"""
Multi-Kiosk Migration Script

This script migrates the existing single-location POS system to multi-kiosk support.
It creates default warehouse and kiosk, migrates stock data, and updates references.

Run this script after updating the database schema:
    python migrate_to_multi_kiosk.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models import (db, User, Product, Sale, StockMovement, DayClose,
                        Location, LocationStock)
from datetime import datetime


def migrate_to_multi_kiosk():
    """Main migration function"""
    app = create_app()

    with app.app_context():
        print("=" * 60)
        print("Multi-Kiosk Migration Script")
        print("=" * 60)

        # Check if migration already done
        existing_locations = Location.query.count()
        if existing_locations > 0:
            print(f"\nFound {existing_locations} existing location(s).")
            response = input("Continue with migration? This may create duplicates. (y/N): ")
            if response.lower() != 'y':
                print("Migration cancelled.")
                return

        try:
            # Step 1: Create default warehouse
            print("\n[1/7] Creating default warehouse...")
            warehouse = Location.query.filter_by(code='WH-001').first()
            if not warehouse:
                warehouse = Location(
                    code='WH-001',
                    name='Main Warehouse',
                    location_type='warehouse',
                    is_active=True,
                    can_sell=False,
                    city='Main City',
                    address='Central Warehouse Location'
                )
                db.session.add(warehouse)
                db.session.flush()
                print(f"   Created warehouse: {warehouse.name} ({warehouse.code})")
            else:
                print(f"   Warehouse already exists: {warehouse.name}")

            # Step 2: Create default kiosk
            print("\n[2/7] Creating default kiosk...")
            kiosk = Location.query.filter_by(code='K-001').first()
            if not kiosk:
                kiosk = Location(
                    code='K-001',
                    name='Main Store',
                    location_type='kiosk',
                    parent_warehouse_id=warehouse.id,
                    is_active=True,
                    can_sell=True,
                    city='Main City',
                    address='Main Store Location'
                )
                db.session.add(kiosk)
                db.session.flush()
                print(f"   Created kiosk: {kiosk.name} ({kiosk.code})")
            else:
                print(f"   Kiosk already exists: {kiosk.name}")

            # Step 3: Migrate product quantities to LocationStock
            print("\n[3/7] Migrating product stock to LocationStock...")
            products = Product.query.all()
            migrated_count = 0
            for product in products:
                if product.quantity > 0:
                    # Check if stock already exists for this product at kiosk
                    existing_stock = LocationStock.query.filter_by(
                        location_id=kiosk.id,
                        product_id=product.id
                    ).first()

                    if not existing_stock:
                        location_stock = LocationStock(
                            location_id=kiosk.id,
                            product_id=product.id,
                            quantity=product.quantity,
                            reorder_level=product.reorder_level,
                            last_movement_at=datetime.utcnow()
                        )
                        db.session.add(location_stock)
                        migrated_count += 1
            print(f"   Migrated {migrated_count} products to kiosk stock")

            # Step 4: Update users with location_id
            print("\n[4/7] Assigning users to default kiosk...")
            users_updated = 0
            admin_count = 0
            for user in User.query.all():
                if user.location_id is None:
                    user.location_id = kiosk.id
                    users_updated += 1

                # Make admin users global admins
                if user.role == 'admin' and not user.is_global_admin:
                    user.is_global_admin = True
                    admin_count += 1

            print(f"   Assigned {users_updated} users to kiosk")
            print(f"   Marked {admin_count} admin(s) as global admins")

            # Step 5: Update sales with location_id
            print("\n[5/7] Updating sales with location...")
            sales_updated = Sale.query.filter(
                Sale.location_id == None
            ).update({Sale.location_id: kiosk.id})
            print(f"   Updated {sales_updated} sales")

            # Step 6: Update stock movements with location_id
            print("\n[6/7] Updating stock movements with location...")
            movements_updated = StockMovement.query.filter(
                StockMovement.location_id == None
            ).update({StockMovement.location_id: kiosk.id})
            print(f"   Updated {movements_updated} stock movements")

            # Step 7: Update day closes with location_id
            print("\n[7/7] Updating day closes with location...")
            dayclose_updated = DayClose.query.filter(
                DayClose.location_id == None
            ).update({DayClose.location_id: kiosk.id})
            print(f"   Updated {dayclose_updated} day close records")

            # Commit all changes
            db.session.commit()

            print("\n" + "=" * 60)
            print("Migration completed successfully!")
            print("=" * 60)
            print("\nSummary:")
            print(f"  - Warehouse: {warehouse.name} ({warehouse.code})")
            print(f"  - Kiosk: {kiosk.name} ({kiosk.code})")
            print(f"  - Products migrated to kiosk: {migrated_count}")
            print(f"  - Users assigned to kiosk: {users_updated}")
            print(f"  - Sales updated: {sales_updated}")
            print(f"  - Stock movements updated: {movements_updated}")
            print(f"  - Day closes updated: {dayclose_updated}")
            print("\nNext steps:")
            print("  1. Create additional kiosks via the Locations menu")
            print("  2. Assign users to their respective kiosks")
            print("  3. Use transfer requests to move stock between locations")
            print("  4. Update warehouse stock for central inventory")

        except Exception as e:
            db.session.rollback()
            print(f"\nError during migration: {str(e)}")
            raise


def create_sample_kiosks():
    """Create additional sample kiosks (optional)"""
    app = create_app()

    with app.app_context():
        warehouse = Location.query.filter_by(code='WH-001').first()
        if not warehouse:
            print("Error: Run migrate_to_multi_kiosk() first")
            return

        sample_kiosks = [
            ('K-002', 'Mall of Wah Kiosk', 'Wah Cantt'),
            ('K-003', 'Rawalpindi Branch', 'Rawalpindi'),
            ('K-004', 'Islamabad Outlet', 'Islamabad'),
        ]

        for code, name, city in sample_kiosks:
            existing = Location.query.filter_by(code=code).first()
            if not existing:
                kiosk = Location(
                    code=code,
                    name=name,
                    city=city,
                    location_type='kiosk',
                    parent_warehouse_id=warehouse.id,
                    is_active=True,
                    can_sell=True
                )
                db.session.add(kiosk)
                print(f"Created: {name} ({code})")

        db.session.commit()
        print("Sample kiosks created successfully!")


def check_migration_status():
    """Check current migration status"""
    app = create_app()

    with app.app_context():
        print("\n" + "=" * 40)
        print("Multi-Kiosk Migration Status")
        print("=" * 40)

        locations = Location.query.count()
        warehouses = Location.query.filter_by(location_type='warehouse').count()
        kiosks = Location.query.filter_by(location_type='kiosk').count()

        print(f"\nLocations: {locations} total ({warehouses} warehouses, {kiosks} kiosks)")

        location_stock = LocationStock.query.count()
        print(f"LocationStock records: {location_stock}")

        users_with_location = User.query.filter(User.location_id != None).count()
        total_users = User.query.count()
        print(f"Users with location: {users_with_location}/{total_users}")

        sales_with_location = Sale.query.filter(Sale.location_id != None).count()
        total_sales = Sale.query.count()
        print(f"Sales with location: {sales_with_location}/{total_sales}")

        global_admins = User.query.filter_by(is_global_admin=True).count()
        print(f"Global admins: {global_admins}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Multi-Kiosk Migration Tool')
    parser.add_argument('--status', action='store_true', help='Check migration status')
    parser.add_argument('--sample', action='store_true', help='Create sample kiosks')

    args = parser.parse_args()

    if args.status:
        check_migration_status()
    elif args.sample:
        create_sample_kiosks()
    else:
        migrate_to_multi_kiosk()
