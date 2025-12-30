"""
Initialize RBAC System
Script to create default roles and permissions
"""

from app import create_app, db
from app.models import Role, Permission, User
from app.utils.permissions import get_all_permissions, get_default_roles


def init_permissions():
    """Create all permissions in the database"""
    print("Creating permissions...")

    permissions = get_all_permissions()
    created_count = 0
    updated_count = 0

    for perm_name, display_name, module in permissions:
        existing_perm = Permission.query.filter_by(name=perm_name).first()

        if existing_perm:
            # Update existing permission
            existing_perm.display_name = display_name
            existing_perm.module = module
            updated_count += 1
        else:
            # Create new permission
            new_perm = Permission(
                name=perm_name,
                display_name=display_name,
                module=module
            )
            db.session.add(new_perm)
            created_count += 1

    db.session.commit()
    print(f"✓ Created {created_count} new permissions")
    print(f"✓ Updated {updated_count} existing permissions")
    print(f"✓ Total: {len(permissions)} permissions in system")


def init_roles():
    """Create default roles and assign permissions"""
    print("\nCreating roles...")

    roles_data = get_default_roles()
    created_count = 0
    updated_count = 0

    for role_name, role_info in roles_data.items():
        existing_role = Role.query.filter_by(name=role_name).first()

        if existing_role:
            # Update existing role
            existing_role.display_name = role_info['display_name']
            existing_role.description = role_info['description']
            existing_role.is_system = role_info['is_system']

            # Clear existing permissions
            existing_role.permissions = []

            # Assign permissions
            for perm_name in role_info['permissions']:
                perm = Permission.query.filter_by(name=perm_name).first()
                if perm:
                    existing_role.permissions.append(perm)

            updated_count += 1
            print(f"  Updated role: {role_name} with {len(role_info['permissions'])} permissions")
        else:
            # Create new role
            new_role = Role(
                name=role_name,
                display_name=role_info['display_name'],
                description=role_info['description'],
                is_system=role_info['is_system']
            )

            # Assign permissions
            for perm_name in role_info['permissions']:
                perm = Permission.query.filter_by(name=perm_name).first()
                if perm:
                    new_role.permissions.append(perm)

            db.session.add(new_role)
            created_count += 1
            print(f"  Created role: {role_name} with {len(role_info['permissions'])} permissions")

    db.session.commit()
    print(f"\n✓ Created {created_count} new roles")
    print(f"✓ Updated {updated_count} existing roles")
    print(f"✓ Total: {len(roles_data)} roles in system")


def assign_legacy_roles():
    """
    Assign RBAC roles to existing users based on their legacy role column
    This ensures backward compatibility
    """
    print("\nMigrating legacy user roles to RBAC...")

    # Legacy role to new RBAC role mapping
    role_mapping = {
        'admin': 'admin',
        'manager': 'manager',
        'cashier': 'cashier',
        'stock_manager': 'inventory_manager',
        'accountant': 'accountant'
    }

    users = User.query.all()
    migrated_count = 0

    for user in users:
        # Check if user already has RBAC roles
        if user.roles.count() > 0:
            continue

        # Get the RBAC role based on legacy role
        rbac_role_name = role_mapping.get(user.role)

        if rbac_role_name:
            rbac_role = Role.query.filter_by(name=rbac_role_name).first()
            if rbac_role:
                user.roles.append(rbac_role)
                migrated_count += 1
                print(f"  Assigned {rbac_role_name} role to user: {user.username}")

    db.session.commit()
    print(f"\n✓ Migrated {migrated_count} users to RBAC system")


def create_admin_user():
    """Create default admin user if none exists"""
    print("\nChecking for admin user...")

    admin_role = Role.query.filter_by(name='admin').first()
    if not admin_role:
        print("  ✗ Admin role not found. Run init_roles() first.")
        return

    # Check if any user has admin role
    admin_users = User.query.join(User.roles).filter(Role.name == 'admin').all()

    if admin_users:
        print(f"  ✓ Admin users exist: {', '.join([u.username for u in admin_users])}")
        return

    # Check legacy admin users
    legacy_admin = User.query.filter_by(role='admin').first()
    if legacy_admin:
        print(f"  Found legacy admin: {legacy_admin.username}")
        print("  Run assign_legacy_roles() to migrate")
        return

    # Create new admin user
    print("  Creating default admin user...")
    admin_user = User(
        username='admin',
        email='admin@sunnatcollection.com',
        full_name='System Administrator',
        role='admin'  # Keep legacy role for compatibility
    )
    admin_user.set_password('admin123')  # Change this password immediately!
    admin_user.roles.append(admin_role)

    db.session.add(admin_user)
    db.session.commit()

    print("  ✓ Created default admin user")
    print("     Username: admin")
    print("     Password: admin123")
    print("     ⚠️  CHANGE THIS PASSWORD IMMEDIATELY!")


def init_rbac(create_admin=False):
    """
    Initialize complete RBAC system

    Args:
        create_admin (bool): Whether to create admin user if none exists
    """
    print("=" * 60)
    print("Initializing RBAC System for Sunnat Collection POS")
    print("=" * 60)

    try:
        # Step 1: Create permissions
        init_permissions()

        # Step 2: Create roles
        init_roles()

        # Step 3: Migrate legacy users
        assign_legacy_roles()

        # Step 4: Create admin user if requested
        if create_admin:
            create_admin_user()

        print("\n" + "=" * 60)
        print("RBAC Initialization Complete!")
        print("=" * 60)

        # Print summary
        total_permissions = Permission.query.count()
        total_roles = Role.query.count()
        total_users_with_roles = User.query.join(User.roles).distinct().count()

        print(f"\nSystem Summary:")
        print(f"  Permissions: {total_permissions}")
        print(f"  Roles: {total_roles}")
        print(f"  Users with RBAC roles: {total_users_with_roles}")

    except Exception as e:
        print(f"\n✗ Error during RBAC initialization: {e}")
        db.session.rollback()
        raise


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        init_rbac(create_admin=True)
