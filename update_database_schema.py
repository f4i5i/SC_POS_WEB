#!/usr/bin/env python3
"""
Database Schema Update Script

This script adds the new columns and tables required for multi-kiosk support
to an existing database without losing data.
"""

import sqlite3
import os
import sys
from datetime import datetime

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'pos.db')

def get_connection():
    """Get database connection"""
    if not os.path.exists(DB_PATH):
        print(f"Database not found at: {DB_PATH}")
        sys.exit(1)
    return sqlite3.connect(DB_PATH)

def column_exists(cursor, table, column):
    """Check if a column exists in a table"""
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [info[1] for info in cursor.fetchall()]
    return column in columns

def table_exists(cursor, table):
    """Check if a table exists"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cursor.fetchone() is not None

def run_migration():
    """Run database migration"""
    conn = get_connection()
    cursor = conn.cursor()

    print("=" * 60)
    print("Database Schema Update for Multi-Kiosk Support")
    print("=" * 60)
    print(f"\nDatabase: {DB_PATH}")
    print(f"Time: {datetime.now()}\n")

    changes_made = 0

    try:
        # ============================================
        # 1. Add columns to users table
        # ============================================
        print("[1/8] Checking users table...")

        if not column_exists(cursor, 'users', 'location_id'):
            cursor.execute("ALTER TABLE users ADD COLUMN location_id INTEGER")
            print("  + Added: users.location_id")
            changes_made += 1
        else:
            print("  - users.location_id already exists")

        if not column_exists(cursor, 'users', 'is_global_admin'):
            cursor.execute("ALTER TABLE users ADD COLUMN is_global_admin BOOLEAN DEFAULT 0")
            # Make existing admin users global admins
            cursor.execute("UPDATE users SET is_global_admin = 1 WHERE role = 'admin'")
            print("  + Added: users.is_global_admin")
            changes_made += 1
        else:
            print("  - users.is_global_admin already exists")

        # ============================================
        # 2. Add columns to sales table
        # ============================================
        print("\n[2/8] Checking sales table...")

        if not column_exists(cursor, 'sales', 'location_id'):
            cursor.execute("ALTER TABLE sales ADD COLUMN location_id INTEGER")
            print("  + Added: sales.location_id")
            changes_made += 1
        else:
            print("  - sales.location_id already exists")

        # ============================================
        # 3. Add columns to stock_movements table
        # ============================================
        print("\n[3/8] Checking stock_movements table...")

        if not column_exists(cursor, 'stock_movements', 'location_id'):
            cursor.execute("ALTER TABLE stock_movements ADD COLUMN location_id INTEGER")
            print("  + Added: stock_movements.location_id")
            changes_made += 1
        else:
            print("  - stock_movements.location_id already exists")

        if not column_exists(cursor, 'stock_movements', 'transfer_id'):
            cursor.execute("ALTER TABLE stock_movements ADD COLUMN transfer_id INTEGER")
            print("  + Added: stock_movements.transfer_id")
            changes_made += 1
        else:
            print("  - stock_movements.transfer_id already exists")

        # ============================================
        # 4. Add columns to day_closes table
        # ============================================
        print("\n[4/8] Checking day_closes table...")

        if not column_exists(cursor, 'day_closes', 'location_id'):
            cursor.execute("ALTER TABLE day_closes ADD COLUMN location_id INTEGER")
            print("  + Added: day_closes.location_id")
            changes_made += 1
        else:
            print("  - day_closes.location_id already exists")

        # ============================================
        # 5. Create locations table
        # ============================================
        print("\n[5/8] Checking locations table...")

        if not table_exists(cursor, 'locations'):
            cursor.execute("""
                CREATE TABLE locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code VARCHAR(32) NOT NULL UNIQUE,
                    name VARCHAR(128) NOT NULL,
                    location_type VARCHAR(32) NOT NULL,
                    address TEXT,
                    city VARCHAR(64),
                    phone VARCHAR(32),
                    email VARCHAR(120),
                    parent_warehouse_id INTEGER,
                    manager_id INTEGER,
                    is_active BOOLEAN DEFAULT 1,
                    can_sell BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (parent_warehouse_id) REFERENCES locations (id),
                    FOREIGN KEY (manager_id) REFERENCES users (id)
                )
            """)
            cursor.execute("CREATE INDEX ix_locations_code ON locations (code)")
            print("  + Created: locations table")
            changes_made += 1
        else:
            print("  - locations table already exists")

        # ============================================
        # 6. Create location_stock table
        # ============================================
        print("\n[6/8] Checking location_stock table...")

        if not table_exists(cursor, 'location_stock'):
            cursor.execute("""
                CREATE TABLE location_stock (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    location_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    quantity INTEGER DEFAULT 0,
                    reserved_quantity INTEGER DEFAULT 0,
                    reorder_level INTEGER DEFAULT 10,
                    last_movement_at DATETIME,
                    last_count_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (location_id) REFERENCES locations (id),
                    FOREIGN KEY (product_id) REFERENCES products (id),
                    UNIQUE (location_id, product_id)
                )
            """)
            cursor.execute("CREATE INDEX ix_location_stock_location ON location_stock (location_id)")
            cursor.execute("CREATE INDEX ix_location_stock_product ON location_stock (product_id)")
            print("  + Created: location_stock table")
            changes_made += 1
        else:
            print("  - location_stock table already exists")

        # ============================================
        # 7. Create stock_transfers table
        # ============================================
        print("\n[7/8] Checking stock_transfers table...")

        if not table_exists(cursor, 'stock_transfers'):
            cursor.execute("""
                CREATE TABLE stock_transfers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transfer_number VARCHAR(64) NOT NULL UNIQUE,
                    source_location_id INTEGER NOT NULL,
                    destination_location_id INTEGER NOT NULL,
                    status VARCHAR(32) DEFAULT 'draft',
                    priority VARCHAR(16) DEFAULT 'normal',
                    expected_delivery_date DATE,
                    requested_at DATETIME,
                    approved_at DATETIME,
                    dispatched_at DATETIME,
                    received_at DATETIME,
                    requested_by INTEGER,
                    approved_by INTEGER,
                    dispatched_by INTEGER,
                    received_by INTEGER,
                    request_notes TEXT,
                    approval_notes TEXT,
                    dispatch_notes TEXT,
                    receive_notes TEXT,
                    rejection_reason TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_location_id) REFERENCES locations (id),
                    FOREIGN KEY (destination_location_id) REFERENCES locations (id),
                    FOREIGN KEY (requested_by) REFERENCES users (id),
                    FOREIGN KEY (approved_by) REFERENCES users (id),
                    FOREIGN KEY (dispatched_by) REFERENCES users (id),
                    FOREIGN KEY (received_by) REFERENCES users (id)
                )
            """)
            cursor.execute("CREATE INDEX ix_stock_transfers_number ON stock_transfers (transfer_number)")
            cursor.execute("CREATE INDEX ix_stock_transfers_status ON stock_transfers (status)")
            print("  + Created: stock_transfers table")
            changes_made += 1

            # Create stock_transfer_items table
            cursor.execute("""
                CREATE TABLE stock_transfer_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transfer_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    quantity_requested INTEGER NOT NULL,
                    quantity_approved INTEGER,
                    quantity_dispatched INTEGER,
                    quantity_received INTEGER,
                    notes TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (transfer_id) REFERENCES stock_transfers (id),
                    FOREIGN KEY (product_id) REFERENCES products (id)
                )
            """)
            print("  + Created: stock_transfer_items table")
            changes_made += 1
        else:
            print("  - stock_transfers table already exists")

        # ============================================
        # 8. Create gate_passes table
        # ============================================
        print("\n[8/8] Checking gate_passes table...")

        if not table_exists(cursor, 'gate_passes'):
            cursor.execute("""
                CREATE TABLE gate_passes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gate_pass_number VARCHAR(64) NOT NULL UNIQUE,
                    transfer_id INTEGER NOT NULL,
                    vehicle_number VARCHAR(32),
                    vehicle_type VARCHAR(32),
                    driver_name VARCHAR(128),
                    driver_phone VARCHAR(32),
                    driver_cnic VARCHAR(20),
                    dispatch_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expected_arrival DATETIME,
                    actual_arrival DATETIME,
                    security_seal_number VARCHAR(64),
                    verified_by INTEGER,
                    verification_notes TEXT,
                    status VARCHAR(32) DEFAULT 'issued',
                    total_items INTEGER DEFAULT 0,
                    total_quantity INTEGER DEFAULT 0,
                    total_value DECIMAL(12, 2) DEFAULT 0.00,
                    dispatch_notes TEXT,
                    delivery_notes TEXT,
                    special_instructions TEXT,
                    created_by INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (transfer_id) REFERENCES stock_transfers (id),
                    FOREIGN KEY (verified_by) REFERENCES users (id),
                    FOREIGN KEY (created_by) REFERENCES users (id)
                )
            """)
            cursor.execute("CREATE INDEX ix_gate_passes_number ON gate_passes (gate_pass_number)")
            print("  + Created: gate_passes table")
            changes_made += 1
        else:
            print("  - gate_passes table already exists")

        # ============================================
        # Commit changes
        # ============================================
        conn.commit()

        print("\n" + "=" * 60)
        print(f"Migration completed! {changes_made} changes made.")
        print("=" * 60)

        if changes_made > 0:
            print("\nNext step: Run the multi-kiosk migration script:")
            print("  python migrate_to_multi_kiosk.py")

    except Exception as e:
        conn.rollback()
        print(f"\nError during migration: {str(e)}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
