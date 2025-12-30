#!/usr/bin/env python3
"""
Script to apply RBAC permission decorators to remaining route files
"""

import re

# Route file mappings: file -> list of (route_pattern, permission)
ROUTE_UPDATES = {
    'app/routes/customers.py': {
        'imports': "from app.utils.permissions import permission_required, Permissions\n",
        'routes': [
            ("@bp.route('/')\n@login_required\ndef index():",
             "@bp.route('/')\n@login_required\n@permission_required(Permissions.CUSTOMER_VIEW)\ndef index():"),
            ("@bp.route('/add', methods=['GET', 'POST'])\n@login_required\ndef add_customer():",
             "@bp.route('/add', methods=['GET', 'POST'])\n@login_required\n@permission_required(Permissions.CUSTOMER_CREATE)\ndef add_customer():"),
            ("@bp.route('/edit/<int:customer_id>', methods=['GET', 'POST'])\n@login_required\ndef edit_customer(customer_id):",
             "@bp.route('/edit/<int:customer_id>', methods=['GET', 'POST'])\n@login_required\n@permission_required(Permissions.CUSTOMER_EDIT)\ndef edit_customer(customer_id):"),
            ("@bp.route('/delete/<int:customer_id>', methods=['POST'])\n@login_required\ndef delete_customer(customer_id):",
             "@bp.route('/delete/<int:customer_id>', methods=['POST'])\n@login_required\n@permission_required(Permissions.CUSTOMER_DELETE)\ndef delete_customer(customer_id):"),
            ("@bp.route('/search')\n@login_required\ndef search():",
             "@bp.route('/search')\n@login_required\n@permission_required(Permissions.CUSTOMER_VIEW)\ndef search():"),
            ("@bp.route('/birthdays')\n@login_required\ndef birthdays():",
             "@bp.route('/birthdays')\n@login_required\n@permission_required(Permissions.CUSTOMER_VIEW)\ndef birthdays():"),
            ("@bp.route('/birthday-gift/<int:customer_id>', methods=['POST'])\n@login_required\ndef apply_birthday_gift(customer_id):",
             "@bp.route('/birthday-gift/<int:customer_id>', methods=['POST'])\n@login_required\n@permission_required(Permissions.CUSTOMER_EDIT)\ndef apply_birthday_gift(customer_id):"),
            ("@bp.route('/send-birthday-wishes', methods=['POST'])\n@login_required\ndef send_birthday_wishes():",
             "@bp.route('/send-birthday-wishes', methods=['POST'])\n@login_required\n@permission_required(Permissions.CUSTOMER_EDIT)\ndef send_birthday_wishes():"),
        ]
    },
    'app/routes/suppliers.py': {
        'imports': "from app.utils.permissions import permission_required, Permissions\n",
        'routes': [
            ("@bp.route('/')\n@login_required\ndef index():",
             "@bp.route('/')\n@login_required\n@permission_required(Permissions.SUPPLIER_VIEW)\ndef index():"),
            ("@bp.route('/add', methods=['GET', 'POST'])\n@login_required\ndef add_supplier():",
             "@bp.route('/add', methods=['GET', 'POST'])\n@login_required\n@permission_required(Permissions.SUPPLIER_CREATE)\ndef add_supplier():"),
            ("@bp.route('/edit/<int:supplier_id>', methods=['GET', 'POST'])\n@login_required\ndef edit_supplier(supplier_id):",
             "@bp.route('/edit/<int:supplier_id>', methods=['GET', 'POST'])\n@login_required\n@permission_required(Permissions.SUPPLIER_EDIT)\ndef edit_supplier(supplier_id):"),
            ("@bp.route('/delete/<int:supplier_id>', methods=['POST'])\n@login_required\ndef delete_supplier(supplier_id):",
             "@bp.route('/delete/<int:supplier_id>', methods=['POST'])\n@login_required\n@permission_required(Permissions.SUPPLIER_DELETE)\ndef delete_supplier(supplier_id):"),
        ]
    },
    'app/routes/reports.py': {
        'imports': "from app.utils.permissions import permission_required, Permissions\n",
        'routes': [
            ("@bp.route('/')\n@login_required\ndef index():",
             "@bp.route('/')\n@login_required\n@permission_required(Permissions.REPORT_VIEW_SALES)\ndef index():"),
            ("@bp.route('/daily')\n@login_required\ndef daily_report():",
             "@bp.route('/daily')\n@login_required\n@permission_required(Permissions.REPORT_VIEW_SALES)\ndef daily_report():"),
            ("@bp.route('/weekly')\n@login_required\ndef weekly_report():",
             "@bp.route('/weekly')\n@login_required\n@permission_required(Permissions.REPORT_VIEW_SALES)\ndef weekly_report():"),
            ("@bp.route('/monthly')\n@login_required\ndef monthly_report():",
             "@bp.route('/monthly')\n@login_required\n@permission_required(Permissions.REPORT_VIEW_SALES)\ndef monthly_report():"),
            ("@bp.route('/custom')\n@login_required\ndef custom_report():",
             "@bp.route('/custom')\n@login_required\n@permission_required(Permissions.REPORT_VIEW_SALES)\ndef custom_report():"),
            ("@bp.route('/inventory-valuation')\n@login_required\ndef inventory_valuation():",
             "@bp.route('/inventory-valuation')\n@login_required\n@permission_required(Permissions.REPORT_VIEW_INVENTORY)\ndef inventory_valuation():"),
            ("@bp.route('/employee-performance')\n@login_required\ndef employee_performance():",
             "@bp.route('/employee-performance')\n@login_required\n@permission_required(Permissions.REPORT_VIEW_SALES)\ndef employee_performance():"),
            ("@bp.route('/product-performance')\n@login_required\ndef product_performance():",
             "@bp.route('/product-performance')\n@login_required\n@permission_required(Permissions.REPORT_VIEW_SALES)\ndef product_performance():"),
            ("@bp.route('/sales-by-category')\n@login_required\ndef sales_by_category():",
             "@bp.route('/sales-by-category')\n@login_required\n@permission_required(Permissions.REPORT_VIEW_SALES)\ndef sales_by_category():"),
            ("@bp.route('/profit-loss')\n@login_required\ndef profit_loss():",
             "@bp.route('/profit-loss')\n@login_required\n@permission_required(Permissions.REPORT_VIEW_FINANCIAL)\ndef profit_loss():"),
            ("@bp.route('/customer-analysis')\n@login_required\ndef customer_analysis():",
             "@bp.route('/customer-analysis')\n@login_required\n@permission_required(Permissions.REPORT_VIEW_SALES)\ndef customer_analysis():"),
            ("@bp.route('/export-daily-pdf')\n@login_required\ndef export_daily_pdf():",
             "@bp.route('/export-daily-pdf')\n@login_required\n@permission_required(Permissions.REPORT_EXPORT)\ndef export_daily_pdf():"),
        ]
    },
    'app/routes/settings.py': {
        'imports': "from app.utils.permissions import permission_required, Permissions\n",
        'routes': [
            ("@bp.route('/')\n@login_required\ndef index():",
             "@bp.route('/')\n@login_required\n@permission_required(Permissions.SETTINGS_VIEW)\ndef index():"),
            ("@bp.route('/update', methods=['POST'])\n@login_required\ndef update_settings():",
             "@bp.route('/update', methods=['POST'])\n@login_required\n@permission_required(Permissions.SETTINGS_EDIT)\ndef update_settings():"),
            ("@bp.route('/users')\n@login_required\ndef users():",
             "@bp.route('/users')\n@login_required\n@permission_required(Permissions.SETTINGS_MANAGE_USERS)\ndef users():"),
            ("@bp.route('/users/add', methods=['GET', 'POST'])\n@login_required\ndef add_user():",
             "@bp.route('/users/add', methods=['GET', 'POST'])\n@login_required\n@permission_required(Permissions.SETTINGS_MANAGE_USERS)\ndef add_user():"),
            ("@bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])\n@login_required\ndef edit_user(user_id):",
             "@bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])\n@login_required\n@permission_required(Permissions.SETTINGS_MANAGE_USERS)\ndef edit_user(user_id):"),
            ("@bp.route('/users/delete/<int:user_id>', methods=['POST'])\n@login_required\ndef delete_user(user_id):",
             "@bp.route('/users/delete/<int:user_id>', methods=['POST'])\n@login_required\n@permission_required(Permissions.SETTINGS_MANAGE_USERS)\ndef delete_user(user_id):"),
        ]
    }
}


def apply_rbac_to_file(filepath, config):
    """Apply RBAC decorators to a single file"""
    print(f"\nProcessing {filepath}...")

    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Add imports if not already present
        if 'from app.utils.permissions import' not in content:
            # Find the import section (after other app imports)
            import_pattern = r'(from app\.utils\.helpers import[^\n]+\n)'
            if re.search(import_pattern, content):
                content = re.sub(import_pattern, r'\1' + config['imports'], content)
            else:
                # Fallback: add after all imports
                import_pattern = r'(import json\n)'
                if re.search(import_pattern, content):
                    content = re.sub(import_pattern, r'\1' + config['imports'], content)

        # Apply route decorators
        for old_pattern, new_pattern in config['routes']:
            if old_pattern in content:
                content = content.replace(old_pattern, new_pattern)
                print(f"  ✓ Updated route")
            else:
                print(f"  ⚠ Route pattern not found (may already be updated)")

        # Write back
        with open(filepath, 'w') as f:
            f.write(content)

        print(f"✓ Completed {filepath}")
        return True

    except Exception as e:
        print(f"✗ Error processing {filepath}: {e}")
        return False


def main():
    """Main execution"""
    print("=" * 60)
    print("Applying RBAC Permission Decorators to Routes")
    print("=" * 60)

    success_count = 0
    total_count = len(ROUTE_UPDATES)

    for filepath, config in ROUTE_UPDATES.items():
        if apply_rbac_to_file(filepath, config):
            success_count += 1

    print("\n" + "=" * 60)
    print(f"Completed: {success_count}/{total_count} files updated successfully")
    print("=" * 60)


if __name__ == '__main__':
    main()
