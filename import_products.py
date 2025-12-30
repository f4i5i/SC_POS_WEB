"""
Import Products from Lattafa Excel File
Imports products from various sheets with pricing and details
"""

import pandas as pd
import sys
from decimal import Decimal
from datetime import datetime
import hashlib

# Add app to path
sys.path.insert(0, '/home/f4i5i/SC_POC/SOC_WEB_APP')

from app import create_app, db
from app.models import Product, Category, Supplier


def get_or_create_category(name, description=None):
    """Get existing category or create new one"""
    category = Category.query.filter_by(name=name).first()
    if not category:
        category = Category(name=name, description=description)
        db.session.add(category)
        db.session.commit()
        print(f"  Created category: {name}")
    return category


def get_or_create_supplier(name):
    """Get existing supplier or create new one"""
    supplier = Supplier.query.filter_by(name=name).first()
    if not supplier:
        supplier = Supplier(
            name=name,
            contact_person="Lattafa Stores",
            is_active=True
        )
        db.session.add(supplier)
        db.session.commit()
        print(f"  Created supplier: {name}")
    return supplier


def safe_decimal(value, default=0.0):
    """Safely convert value to Decimal"""
    try:
        if pd.isna(value) or value == '' or value is None:
            return Decimal(str(default))
        return Decimal(str(float(value)))
    except (ValueError, TypeError):
        return Decimal(str(default))


def generate_unique_code(base_code, full_name):
    """Generate unique product code"""
    # Check if code already exists
    existing = Product.query.filter_by(code=base_code).first()

    if not existing:
        return base_code

    # Code exists, add hash of full name for uniqueness
    name_hash = hashlib.md5(full_name.encode()).hexdigest()[:4].upper()
    unique_code = f"{base_code}-{name_hash}"

    # If still exists (very unlikely), add counter
    counter = 1
    while Product.query.filter_by(code=unique_code).first():
        unique_code = f"{base_code}-{name_hash}-{counter}"
        counter += 1

    return unique_code


def import_tasbee_list(excel_file):
    """Import Tasbee (Prayer Beads) products"""
    print("\n" + "="*60)
    print("Importing Tasbee List...")
    print("="*60)

    df = pd.read_excel(excel_file, sheet_name='tasbee list')
    category = get_or_create_category('Tasbee (Prayer Beads)', 'Islamic prayer beads in various sizes and materials')
    supplier = get_or_create_supplier('Lattafa Stores')

    imported = 0
    skipped = 0

    for _, row in df.iterrows():
        try:
            size = str(row['Tasbee size']).strip()
            name = str(row['tasbee name']).strip()
            product_name = f"{name} Tasbee {size}"

            # Check if product already exists
            existing = Product.query.filter_by(name=product_name).first()
            if existing:
                skipped += 1
                continue

            wholesale_price = safe_decimal(row['whole sale price'])
            selling_price = safe_decimal(row['Tasbee selling price'])
            discount_price = safe_decimal(row['12% discount'])

            product = Product(
                name=product_name,
                code=f"TASBEE-{size}-{name[:3].upper()}",
                category_id=category.id,
                supplier_id=supplier.id,
                cost_price=wholesale_price,
                selling_price=selling_price,
                quantity=0,  # Set initial quantity to 0
                reorder_level=5,
                unit='piece',
                description=f"{size} {name} Prayer Beads",
                is_active=True
            )

            db.session.add(product)
            imported += 1

        except Exception as e:
            print(f"  Error importing tasbee {row.get('tasbee name', 'Unknown')}: {e}")
            continue

    db.session.commit()
    print(f"✓ Imported {imported} tasbee products (skipped {skipped} existing)")


def import_nimaz_caps(excel_file):
    """Import Nimaz (Prayer) Caps"""
    print("\n" + "="*60)
    print("Importing Nimaz Caps...")
    print("="*60)

    df = pd.read_excel(excel_file, sheet_name='Nimaz caps', header=0)
    # Skip the header row since it's in the first data row
    df = df[1:].reset_index(drop=True)

    # Rename columns based on expected structure
    expected_cols = ['cap color', 'whole sale price', 'Qty', 'cap labels',
                     'Packaging', 'Kisok', 'cap total price', 'cap selling price', '12% discount', 'profit']

    if len(df.columns) >= len(expected_cols):
        df.columns = expected_cols + list(df.columns[len(expected_cols):])

    category = get_or_create_category('Prayer Caps', 'Islamic prayer caps (Nimaz Topi)')
    supplier = get_or_create_supplier('Lattafa Stores')

    imported = 0
    skipped = 0

    for _, row in df.iterrows():
        try:
            color = str(row['cap color']).strip()
            if color.lower() == 'nan' or color == '' or pd.isna(row['cap color']):
                continue

            product_name = f"Nimaz Cap - {color.title()}"

            # Check if product already exists
            existing = Product.query.filter_by(name=product_name).first()
            if existing:
                skipped += 1
                continue

            wholesale_price = safe_decimal(row['whole sale price'])
            selling_price = safe_decimal(row['cap selling price'])

            # Generate unique code
            base_code = f"CAP-{color[:3].upper()}"
            unique_code = generate_unique_code(base_code, product_name)

            product = Product(
                name=product_name,
                code=unique_code,
                category_id=category.id,
                supplier_id=supplier.id,
                cost_price=wholesale_price,
                selling_price=selling_price,
                quantity=0,
                reorder_level=10,
                unit='piece',
                description=f"{color.title()} Prayer Cap",
                is_active=True
            )

            db.session.add(product)
            imported += 1

        except Exception as e:
            print(f"  Error importing cap ({row.get('cap color', 'unknown')}): {e}")
            db.session.rollback()
            continue

    db.session.commit()
    print(f"✓ Imported {imported} nimaz caps (skipped {skipped} existing)")


def import_bakhoor_burners(excel_file):
    """Import Bakhoor Burners"""
    print("\n" + "="*60)
    print("Importing Bakhoor Burners...")
    print("="*60)

    df = pd.read_excel(excel_file, sheet_name='bhakkor Burner')
    category = get_or_create_category('Bakhoor Burners', 'Incense burners for bakhoor/bukhoor')
    supplier = get_or_create_supplier('Lattafa Stores')

    imported = 0
    skipped = 0

    for _, row in df.iterrows():
        try:
            sr_no = str(row['Burner Sr No ']).strip()
            product_name = f"Bakhoor Burner {sr_no}"

            # Check if product already exists
            existing = Product.query.filter_by(name=product_name).first()
            if existing:
                skipped += 1
                continue

            wholesale_price = safe_decimal(row['whole sale price'])
            selling_price = safe_decimal(row['Burner selling price'])
            discount_price = safe_decimal(row['12% discount'])

            product = Product(
                name=product_name,
                code=f"BURNER-{sr_no}",
                category_id=category.id,
                supplier_id=supplier.id,
                cost_price=wholesale_price,
                selling_price=selling_price,
                quantity=0,
                reorder_level=3,
                unit='piece',
                description=f"Bakhoor Burner Model {sr_no}",
                is_active=True
            )

            db.session.add(product)
            imported += 1

        except Exception as e:
            print(f"  Error importing burner: {e}")
            continue

    db.session.commit()
    print(f"✓ Imported {imported} bakhoor burners (skipped {skipped} existing)")


def import_bakhoor_tiki(excel_file):
    """Import Bakhoor Tiki (Incense)"""
    print("\n" + "="*60)
    print("Importing Bakhoor Tiki...")
    print("="*60)

    df = pd.read_excel(excel_file, sheet_name='Bhakoor tiki')
    # First row is headers
    df.columns = df.iloc[0]
    df = df[1:].reset_index(drop=True)

    category = get_or_create_category('Bakhoor/Bukhoor', 'Traditional Arabian incense')
    supplier = get_or_create_supplier('Lattafa Stores')

    imported = 0
    skipped = 0

    for _, row in df.iterrows():
        try:
            name = str(row['Bhakoor tiki Name']).strip()
            if name.lower() == 'nan' or name == '':
                continue

            product_name = name.title()

            # Check if product already exists
            existing = Product.query.filter_by(name=product_name).first()
            if existing:
                skipped += 1
                continue

            wholesale_price = safe_decimal(row['whole sale price'])
            selling_price = safe_decimal(row['bhakoor selling price'])
            discount_price = safe_decimal(row['12% discount'])

            # Extract weight from name if possible
            weight = ''
            if 'gram' in name.lower():
                weight = name.lower().split('gram')[0].strip().split()[-1]

            product = Product(
                name=product_name,
                code=f"BAKHOOR-{weight}G" if weight else f"BAKHOOR-{name[:5].upper()}",
                category_id=category.id,
                supplier_id=supplier.id,
                cost_price=wholesale_price,
                selling_price=selling_price,
                quantity=0,
                reorder_level=5,
                unit='pack',
                description=f"Bakhoor Incense {weight}g" if weight else "Bakhoor Incense",
                is_active=True
            )

            db.session.add(product)
            imported += 1

        except Exception as e:
            print(f"  Error importing bakhoor tiki: {e}")
            continue

    db.session.commit()
    print(f"✓ Imported {imported} bakhoor tiki products (skipped {skipped} existing)")


def import_attar_list(excel_file):
    """Import Attar (Essential Oils) in different sizes"""
    print("\n" + "="*60)
    print("Importing Attar List...")
    print("="*60)

    df = pd.read_excel(excel_file, sheet_name='Attar list')
    category = get_or_create_category('Attar (Essential Oils)', 'Traditional Arabian essential oils and attars')
    supplier = get_or_create_supplier('Lattafa Stores')

    imported = 0
    skipped = 0

    for _, row in df.iterrows():
        try:
            attar_name = str(row['Attar Name ']).strip()

            # Import 3ML variant
            product_name_3ml = f"{attar_name} - 3ML"
            if not Product.query.filter_by(name=product_name_3ml).first():
                cost_price_3ml = safe_decimal(row['3ML Total Price '])
                selling_price_3ml = safe_decimal(row['3ML Selling Price '])

                # Generate unique code
                base_code = f"ATR3-{attar_name[:6].upper().replace(' ', '')}"
                unique_code = generate_unique_code(base_code, product_name_3ml)

                product_3ml = Product(
                    name=product_name_3ml,
                    code=unique_code,
                    category_id=category.id,
                    supplier_id=supplier.id,
                    cost_price=cost_price_3ml,
                    selling_price=selling_price_3ml,
                    quantity=0,
                    reorder_level=10,
                    unit='bottle',
                    description=f"{attar_name} Attar 3ML",
                    is_active=True
                )
                db.session.add(product_3ml)
                imported += 1
            else:
                skipped += 1

            # Import 6ML variant
            product_name_6ml = f"{attar_name} - 6ML"
            if not Product.query.filter_by(name=product_name_6ml).first():
                cost_price_6ml = safe_decimal(row['6ML Total Price '])
                selling_price_6ml = safe_decimal(row['6ML Selling Price '])

                # Generate unique code
                base_code = f"ATR6-{attar_name[:6].upper().replace(' ', '')}"
                unique_code = generate_unique_code(base_code, product_name_6ml)

                product_6ml = Product(
                    name=product_name_6ml,
                    code=unique_code,
                    category_id=category.id,
                    supplier_id=supplier.id,
                    cost_price=cost_price_6ml,
                    selling_price=selling_price_6ml,
                    quantity=0,
                    reorder_level=10,
                    unit='bottle',
                    description=f"{attar_name} Attar 6ML",
                    is_active=True
                )
                db.session.add(product_6ml)
                imported += 1
            else:
                skipped += 1

            # Import 12ML variant
            product_name_12ml = f"{attar_name} - 12ML"
            if not Product.query.filter_by(name=product_name_12ml).first():
                cost_price_12ml = safe_decimal(row['12ML Total Price '])
                selling_price_12ml = safe_decimal(row['12ML Selling Price'])

                # Generate unique code
                base_code = f"ATR12-{attar_name[:6].upper().replace(' ', '')}"
                unique_code = generate_unique_code(base_code, product_name_12ml)

                product_12ml = Product(
                    name=product_name_12ml,
                    code=unique_code,
                    category_id=category.id,
                    supplier_id=supplier.id,
                    cost_price=cost_price_12ml,
                    selling_price=selling_price_12ml,
                    quantity=0,
                    reorder_level=10,
                    unit='bottle',
                    description=f"{attar_name} Attar 12ML",
                    is_active=True
                )
                db.session.add(product_12ml)
                imported += 1
            else:
                skipped += 1

        except Exception as e:
            print(f"  Error importing attar {row.get('Attar Name ', 'Unknown')}: {e}")
            db.session.rollback()  # Rollback on error to continue with next
            continue

    db.session.commit()
    print(f"✓ Imported {imported} attar products (skipped {skipped} existing)")


def import_perfume_list(excel_file):
    """Import Regular Perfumes (50ML)"""
    print("\n" + "="*60)
    print("Importing Perfume List (50ML)...")
    print("="*60)

    df = pd.read_excel(excel_file, sheet_name='perfume list')
    category = get_or_create_category('Perfumes', 'Arabian and international fragrances')
    supplier = get_or_create_supplier('Lattafa Stores')

    imported = 0
    skipped = 0

    for _, row in df.iterrows():
        try:
            perfume_name = str(row['fawakeh']).strip()
            product_name = f"{perfume_name} - 50ML"

            # Check if product already exists
            existing = Product.query.filter_by(name=product_name).first()
            if existing:
                skipped += 1
                continue

            cost_price = safe_decimal(row['50ML Total Price '])
            selling_price = safe_decimal(row['50ML Selling Price '])

            # Generate unique code
            base_code = f"PERF50-{perfume_name[:6].upper().replace(' ', '')}"
            unique_code = generate_unique_code(base_code, product_name)

            product = Product(
                name=product_name,
                code=unique_code,
                category_id=category.id,
                supplier_id=supplier.id,
                cost_price=cost_price,
                selling_price=selling_price,
                quantity=0,
                reorder_level=5,
                unit='bottle',
                description=f"{perfume_name} Perfume 50ML",
                is_active=True
            )

            db.session.add(product)
            imported += 1

        except Exception as e:
            print(f"  Error importing perfume {row.get('fawakeh', 'Unknown')}: {e}")
            db.session.rollback()
            continue

    db.session.commit()
    print(f"✓ Imported {imported} perfumes (skipped {skipped} existing)")


def import_lattafa_perfumes(excel_file):
    """Import Lattafa Brand Perfumes"""
    print("\n" + "="*60)
    print("Importing Lattafa Perfumes...")
    print("="*60)

    df = pd.read_excel(excel_file, sheet_name='Lataffa perfume', header=0)
    # Skip the header row
    df = df[1:].reset_index(drop=True)

    # Rename columns based on expected structure
    expected_cols = ['PERFUME NAME', 'Qty', 'whole sale price', 'total',
                     'Packaging', 'KISOK', 'Perfume total price', 'Perfume selling price',
                     '12% discount', 'profit', 'Perfume selling price']

    if len(df.columns) >= len(expected_cols):
        df.columns = expected_cols + list(df.columns[len(expected_cols):])

    category = get_or_create_category('Lattafa Perfumes', 'Lattafa branded perfumes')
    supplier = get_or_create_supplier('Lattafa Stores')

    imported = 0
    skipped = 0

    for _, row in df.iterrows():
        try:
            perfume_name = str(row['PERFUME NAME']).strip()
            if perfume_name.lower() == 'nan' or perfume_name == '' or pd.isna(row['PERFUME NAME']):
                continue

            product_name = f"Lattafa - {perfume_name.title()}"

            # Check if product already exists
            existing = Product.query.filter_by(name=product_name).first()
            if existing:
                skipped += 1
                continue

            cost_price = safe_decimal(row['Perfume total price'])
            selling_price = safe_decimal(row['Perfume selling price'])

            # Generate unique code
            base_code = f"LAT-{perfume_name[:6].upper().replace(' ', '')}"
            unique_code = generate_unique_code(base_code, product_name)

            product = Product(
                name=product_name,
                code=unique_code,
                category_id=category.id,
                supplier_id=supplier.id,
                cost_price=cost_price,
                selling_price=selling_price,
                quantity=0,
                reorder_level=3,
                unit='bottle',
                description=f"Lattafa {perfume_name} Perfume",
                is_active=True
            )

            db.session.add(product)
            imported += 1

        except Exception as e:
            print(f"  Error importing Lattafa perfume: {e}")
            db.session.rollback()
            continue

    db.session.commit()
    print(f"✓ Imported {imported} Lattafa perfumes (skipped {skipped} existing)")


def main():
    """Main import function"""
    excel_file = '/home/f4i5i/Downloads/Lattafa Stores Price List 5-11-2025(AutoRecovered)..xlsx'

    print("="*60)
    print("LATTAFA STORES PRODUCT IMPORT")
    print("="*60)
    print(f"Excel File: {excel_file}")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    app = create_app()
    with app.app_context():
        try:
            # Import all product types
            import_tasbee_list(excel_file)
            import_nimaz_caps(excel_file)
            import_bakhoor_burners(excel_file)
            import_bakhoor_tiki(excel_file)
            import_attar_list(excel_file)
            import_perfume_list(excel_file)
            import_lattafa_perfumes(excel_file)

            # Print summary
            print("\n" + "="*60)
            print("IMPORT COMPLETED SUCCESSFULLY!")
            print("="*60)

            total_products = Product.query.count()
            total_categories = Category.query.count()

            print(f"\nDatabase Summary:")
            print(f"  Total Products: {total_products}")
            print(f"  Total Categories: {total_categories}")

            # Show products per category
            print(f"\nProducts per Category:")
            categories = Category.query.all()
            for cat in categories:
                count = Product.query.filter_by(category_id=cat.id).count()
                if count > 0:
                    print(f"  {cat.name}: {count} products")

            print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        except Exception as e:
            print(f"\n✗ Error during import: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()


if __name__ == '__main__':
    main()
