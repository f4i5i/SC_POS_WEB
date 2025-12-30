"""
Database Initialization Script
Run this script to initialize the database with default settings and admin user
"""

from app import create_app
from app.models import db, User, Setting, Category
from werkzeug.security import generate_password_hash
from datetime import datetime

def init_database():
    """Initialize database with default data"""
    app = create_app()

    with app.app_context():
        # Create all tables
        print("Creating database tables...")
        db.create_all()

        # Check if admin user exists
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            print("Creating default admin user...")
            admin = User(
                username='admin',
                password_hash=generate_password_hash('admin123'),
                full_name='System Administrator',
                email='admin@sunnatcollection.com',
                role='admin',
                is_active=True,
                created_at=datetime.utcnow()
            )
            db.session.add(admin)
            print("✓ Admin user created (username: admin, password: admin123)")
        else:
            print("✓ Admin user already exists")

        # Initialize default business settings
        default_settings = {
            'business_name': 'Sunnat Collection',
            'business_address': 'First Floor, Mall of Wah, G.T Road',
            'business_phone': '',
            'business_email': '',
            'currency': 'PKR',
            'currency_symbol': 'Rs.',
            'tax_rate': '0',
            'tagline': 'Quality Perfumes at Best Prices'
        }

        print("Setting up business configuration...")
        for key, value in default_settings.items():
            setting = Setting.query.filter_by(key=key).first()
            if not setting:
                setting = Setting(key=key, value=value)
                db.session.add(setting)
                print(f"  ✓ {key}: {value}")
            else:
                print(f"  - {key} already configured")

        # Initialize default categories
        default_categories = [
            'Perfumes - Men',
            'Perfumes - Women',
            'Perfumes - Unisex',
            'Attars',
            'Body Sprays',
            'Gift Sets',
            'Accessories'
        ]

        print("Setting up product categories...")
        for category_name in default_categories:
            category = Category.query.filter_by(name=category_name).first()
            if not category:
                category = Category(
                    name=category_name,
                    description=f'{category_name} products',
                    is_active=True
                )
                db.session.add(category)
                print(f"  ✓ {category_name}")
            else:
                print(f"  - {category_name} already exists")

        # Commit all changes
        db.session.commit()
        print("\n" + "="*50)
        print("Database initialization completed successfully!")
        print("="*50)
        print("\nDefault Login Credentials:")
        print("  Username: admin")
        print("  Password: admin123")
        print("\nIMPORTANT: Change the admin password after first login!")
        print("\nBusiness Address: First Floor, Mall of Wah, G.T Road")
        print("You can update business settings from the Settings menu.")
        print("="*50)

if __name__ == '__main__':
    init_database()
