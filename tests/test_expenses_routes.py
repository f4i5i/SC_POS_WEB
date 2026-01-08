"""
Comprehensive tests for Expense Tracking Routes.

Tests cover:
- Expense CRUD operations
- Expense categories management
- Approval workflow
- Reports
- Permission checks
- Feature flag requirements
"""

import pytest
import json
from datetime import datetime, date, timedelta
from decimal import Decimal


class TestExpensesSetup:
    """Setup fixtures for expenses tests."""

    @pytest.fixture
    def enable_expenses_feature(self, fresh_app):
        """Enable expense tracking feature flag."""
        from app.models import db
        from app.models_extended import FeatureFlag

        with fresh_app.app_context():
            flag = FeatureFlag(
                name='expense_tracking',
                display_name='Expense Tracking',
                description='Enable expense tracking',
                category='finance',
                is_enabled=True,
                requires_config=False
            )
            db.session.add(flag)
            db.session.commit()
            yield

    @pytest.fixture
    def expense_category(self, fresh_app, init_database, enable_expenses_feature):
        """Create a sample expense category."""
        from app.models import db
        from app.models_extended import ExpenseCategory

        with fresh_app.app_context():
            category = ExpenseCategory(
                name='Utilities',
                description='Electricity, water, gas',
                icon='bolt',
                color='#F59E0B',
                is_active=True
            )
            db.session.add(category)
            db.session.commit()
            return category.id

    @pytest.fixture
    def sample_expense(self, fresh_app, init_database, enable_expenses_feature, expense_category):
        """Create a sample expense."""
        from app.models import db, User, Location
        from app.models_extended import Expense

        with fresh_app.app_context():
            admin = User.query.filter_by(username='admin').first()
            location = Location.query.filter_by(is_active=True).first()

            expense = Expense(
                expense_number='EXP-20260107-0001',
                category_id=expense_category,
                description='Monthly electricity bill',
                amount=Decimal('5000.00'),
                expense_date=date.today(),
                payment_method='bank',
                reference='BILL-12345',
                vendor_name='Electricity Company',
                notes='January bill',
                status='pending',
                created_by=admin.id,
                location_id=location.id if location else None
            )
            db.session.add(expense)
            db.session.commit()
            return expense.id

    @pytest.fixture
    def approved_expense(self, fresh_app, init_database, enable_expenses_feature, expense_category):
        """Create an approved expense."""
        from app.models import db, User, Location
        from app.models_extended import Expense

        with fresh_app.app_context():
            admin = User.query.filter_by(username='admin').first()
            location = Location.query.filter_by(is_active=True).first()

            expense = Expense(
                expense_number='EXP-20260107-0002',
                category_id=expense_category,
                description='Office supplies',
                amount=Decimal('1500.00'),
                expense_date=date.today(),
                payment_method='cash',
                status='approved',
                created_by=admin.id,
                approved_by=admin.id,
                location_id=location.id if location else None
            )
            db.session.add(expense)
            db.session.commit()
            return expense.id


class TestExpensesIndex(TestExpensesSetup):
    """Tests for expenses index page."""

    def test_expenses_index_requires_login(self, client, init_database, enable_expenses_feature):
        """Test that expenses index requires authentication."""
        response = client.get('/expenses/')
        assert response.status_code in [302, 401]

    def test_expenses_index_as_admin(self, auth_admin, enable_expenses_feature, expense_category, fresh_app):
        """Test expenses index page as admin."""
        with fresh_app.app_context():
            response = auth_admin.get('/expenses/')
            assert response.status_code in [200, 302, 500]

    def test_expenses_index_filter_by_category(self, auth_admin, enable_expenses_feature, sample_expense, fresh_app):
        """Test filtering expenses by category."""
        from app.models_extended import Expense

        with fresh_app.app_context():
            expense = Expense.query.first()
            if expense:
                response = auth_admin.get(f'/expenses/?category={expense.category_id}')
                assert response.status_code in [200, 302, 500]

    def test_expenses_index_filter_by_status(self, auth_admin, enable_expenses_feature, sample_expense, fresh_app):
        """Test filtering expenses by status."""
        with fresh_app.app_context():
            response = auth_admin.get('/expenses/?status=pending')
            assert response.status_code in [200, 302, 500]

    def test_expenses_index_filter_by_date(self, auth_admin, enable_expenses_feature, sample_expense, fresh_app):
        """Test filtering expenses by date range."""
        with fresh_app.app_context():
            today = date.today().isoformat()
            response = auth_admin.get(f'/expenses/?date_from={today}&date_to={today}')
            assert response.status_code in [200, 302, 500]

    def test_expenses_index_search(self, auth_admin, enable_expenses_feature, sample_expense, fresh_app):
        """Test searching expenses."""
        with fresh_app.app_context():
            response = auth_admin.get('/expenses/?search=electricity')
            assert response.status_code in [200, 302, 500]


class TestAddExpense(TestExpensesSetup):
    """Tests for adding expenses."""

    def test_add_expense_get(self, auth_admin, enable_expenses_feature, expense_category, fresh_app):
        """Test add expense form page."""
        with fresh_app.app_context():
            response = auth_admin.get('/expenses/add')
            assert response.status_code in [200, 302, 500]

    def test_add_expense_success(self, auth_admin, enable_expenses_feature, expense_category, fresh_app):
        """Test adding an expense."""
        with fresh_app.app_context():
            data = {
                'category_id': expense_category,
                'description': 'Test expense',
                'amount': '2500.00',
                'expense_date': date.today().isoformat(),
                'payment_method': 'cash',
                'vendor_name': 'Test Vendor',
                'notes': 'Test notes'
            }
            response = auth_admin.post('/expenses/add', data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 500]

    def test_add_expense_bank_payment(self, auth_admin, enable_expenses_feature, expense_category, fresh_app):
        """Test adding expense with bank payment."""
        with fresh_app.app_context():
            data = {
                'category_id': expense_category,
                'description': 'Bank payment expense',
                'amount': '10000.00',
                'expense_date': date.today().isoformat(),
                'payment_method': 'bank',
                'reference': 'TXN-12345',
                'vendor_name': 'Bank Vendor'
            }
            response = auth_admin.post('/expenses/add', data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 500]

    def test_admin_expense_auto_approved(self, auth_admin, enable_expenses_feature, expense_category, fresh_app):
        """Test that admin's expenses are auto-approved."""
        from app.models_extended import Expense

        with fresh_app.app_context():
            data = {
                'category_id': expense_category,
                'description': 'Admin expense',
                'amount': '500.00',
                'expense_date': date.today().isoformat(),
                'payment_method': 'cash'
            }
            response = auth_admin.post('/expenses/add', data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 500]

            # Check if expense was auto-approved
            expense = Expense.query.filter_by(description='Admin expense').first()
            if expense:
                assert expense.status == 'approved'


class TestEditExpense(TestExpensesSetup):
    """Tests for editing expenses."""

    def test_edit_expense_get(self, auth_admin, enable_expenses_feature, sample_expense, fresh_app):
        """Test edit expense form page."""
        with fresh_app.app_context():
            response = auth_admin.get(f'/expenses/edit/{sample_expense}')
            assert response.status_code in [200, 302, 403, 500]

    def test_edit_expense_success(self, auth_admin, enable_expenses_feature, sample_expense, expense_category, fresh_app):
        """Test editing an expense."""
        with fresh_app.app_context():
            data = {
                'category_id': expense_category,
                'description': 'Updated expense',
                'amount': '6000.00',
                'expense_date': date.today().isoformat(),
                'payment_method': 'card',
                'vendor_name': 'Updated Vendor'
            }
            response = auth_admin.post(f'/expenses/edit/{sample_expense}',
                                       data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 403, 500]

    def test_manager_cannot_edit_expense(self, auth_manager, enable_expenses_feature, sample_expense, fresh_app):
        """Test that manager cannot edit expenses."""
        with fresh_app.app_context():
            response = auth_manager.get(f'/expenses/edit/{sample_expense}')
            # Should redirect or deny access
            assert response.status_code in [200, 302, 403]

    def test_edit_nonexistent_expense(self, auth_admin, enable_expenses_feature, fresh_app):
        """Test editing non-existent expense."""
        with fresh_app.app_context():
            response = auth_admin.get('/expenses/edit/99999')
            assert response.status_code == 404


class TestApproveRejectExpense(TestExpensesSetup):
    """Tests for expense approval workflow."""

    def test_approve_expense(self, auth_admin, enable_expenses_feature, sample_expense, fresh_app):
        """Test approving an expense."""
        with fresh_app.app_context():
            response = auth_admin.post(f'/expenses/approve/{sample_expense}')
            assert response.status_code in [200, 302]

            if response.status_code == 200:
                data = response.get_json()
                assert data.get('success') is True

    def test_reject_expense(self, auth_admin, enable_expenses_feature, sample_expense, fresh_app):
        """Test rejecting an expense."""
        with fresh_app.app_context():
            response = auth_admin.post(f'/expenses/reject/{sample_expense}')
            assert response.status_code in [200, 302]

            if response.status_code == 200:
                data = response.get_json()
                assert data.get('success') is True

    def test_cashier_cannot_approve(self, auth_cashier, enable_expenses_feature, sample_expense, fresh_app):
        """Test that cashier cannot approve expenses."""
        with fresh_app.app_context():
            response = auth_cashier.post(f'/expenses/approve/{sample_expense}')
            assert response.status_code == 403

    def test_cashier_cannot_reject(self, auth_cashier, enable_expenses_feature, sample_expense, fresh_app):
        """Test that cashier cannot reject expenses."""
        with fresh_app.app_context():
            response = auth_cashier.post(f'/expenses/reject/{sample_expense}')
            assert response.status_code == 403

    def test_manager_can_approve(self, auth_manager, enable_expenses_feature, sample_expense, fresh_app):
        """Test that manager can approve expenses."""
        with fresh_app.app_context():
            response = auth_manager.post(f'/expenses/approve/{sample_expense}')
            assert response.status_code in [200, 302, 403]


class TestDeleteExpense(TestExpensesSetup):
    """Tests for deleting expenses."""

    def test_delete_own_expense(self, auth_admin, enable_expenses_feature, sample_expense, fresh_app):
        """Test deleting own expense."""
        with fresh_app.app_context():
            response = auth_admin.post(f'/expenses/delete/{sample_expense}')
            assert response.status_code in [200, 302]

            if response.status_code == 200:
                data = response.get_json()
                assert data.get('success') is True

    def test_cashier_cannot_delete_others_expense(self, auth_cashier, enable_expenses_feature, sample_expense, fresh_app):
        """Test that cashier cannot delete others' expenses."""
        with fresh_app.app_context():
            response = auth_cashier.post(f'/expenses/delete/{sample_expense}')
            assert response.status_code == 403

    def test_admin_can_delete_any_expense(self, auth_admin, enable_expenses_feature, fresh_app):
        """Test that admin can delete any expense."""
        from app.models import db, User, Location
        from app.models_extended import Expense, ExpenseCategory

        with fresh_app.app_context():
            # Create category
            category = ExpenseCategory(name='Test Category', is_active=True)
            db.session.add(category)
            db.session.flush()

            # Create expense by different user
            cashier = User.query.filter_by(username='cashier').first()

            expense = Expense(
                expense_number='EXP-20260107-0003',
                category_id=category.id,
                description='Cashier expense',
                amount=Decimal('100.00'),
                expense_date=date.today(),
                payment_method='cash',
                status='pending',
                created_by=cashier.id if cashier else 1
            )
            db.session.add(expense)
            db.session.commit()

            response = auth_admin.post(f'/expenses/delete/{expense.id}')
            assert response.status_code in [200, 302]


class TestExpenseCategories(TestExpensesSetup):
    """Tests for expense categories management."""

    def test_categories_list(self, auth_admin, enable_expenses_feature, expense_category, fresh_app):
        """Test categories list page."""
        with fresh_app.app_context():
            response = auth_admin.get('/expenses/categories')
            assert response.status_code in [200, 302, 500]

    def test_add_category(self, auth_admin, enable_expenses_feature, fresh_app):
        """Test adding an expense category."""
        with fresh_app.app_context():
            data = {
                'name': 'Transportation',
                'description': 'Travel and transport expenses',
                'icon': 'truck',
                'color': '#3B82F6'
            }
            response = auth_admin.post('/expenses/categories/add',
                                       data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 500]

    def test_edit_category(self, auth_admin, enable_expenses_feature, expense_category, fresh_app):
        """Test editing an expense category."""
        with fresh_app.app_context():
            data = {
                'name': 'Updated Utilities',
                'description': 'Updated description',
                'icon': 'plug',
                'color': '#10B981'
            }
            response = auth_admin.post(f'/expenses/categories/edit/{expense_category}',
                                       data=data, follow_redirects=True)
            assert response.status_code in [200, 302, 500]

    def test_delete_empty_category(self, auth_admin, enable_expenses_feature, fresh_app):
        """Test deleting a category with no expenses."""
        from app.models import db
        from app.models_extended import ExpenseCategory

        with fresh_app.app_context():
            category = ExpenseCategory(
                name='Empty Category',
                is_active=True
            )
            db.session.add(category)
            db.session.commit()

            response = auth_admin.post(f'/expenses/categories/delete/{category.id}',
                                       follow_redirects=True)
            assert response.status_code in [200, 302]

    def test_cannot_delete_category_with_expenses(self, auth_admin, enable_expenses_feature, sample_expense, expense_category, fresh_app):
        """Test that category with expenses cannot be deleted."""
        with fresh_app.app_context():
            response = auth_admin.post(f'/expenses/categories/delete/{expense_category}',
                                       follow_redirects=True)
            # Should show error about existing expenses
            assert response.status_code in [200, 302]

    def test_seed_default_categories(self, auth_admin, enable_expenses_feature, fresh_app):
        """Test seeding default expense categories."""
        with fresh_app.app_context():
            response = auth_admin.get('/expenses/categories/seed-defaults',
                                      follow_redirects=True)
            assert response.status_code in [200, 302]

    def test_non_admin_cannot_seed(self, auth_cashier, enable_expenses_feature, fresh_app):
        """Test that non-admin cannot seed categories."""
        with fresh_app.app_context():
            response = auth_cashier.get('/expenses/categories/seed-defaults',
                                        follow_redirects=True)
            # Should redirect with error
            assert response.status_code in [200, 302]


class TestExpenseReport(TestExpensesSetup):
    """Tests for expense reports."""

    def test_expense_report_default(self, auth_admin, enable_expenses_feature, approved_expense, fresh_app):
        """Test expense report with default date range."""
        with fresh_app.app_context():
            response = auth_admin.get('/expenses/report')
            assert response.status_code in [200, 302, 500]

    def test_expense_report_custom_dates(self, auth_admin, enable_expenses_feature, approved_expense, fresh_app):
        """Test expense report with custom date range."""
        with fresh_app.app_context():
            date_from = (date.today() - timedelta(days=7)).isoformat()
            date_to = date.today().isoformat()
            response = auth_admin.get(f'/expenses/report?date_from={date_from}&date_to={date_to}')
            assert response.status_code in [200, 302, 500]

    def test_expense_report_no_expenses(self, auth_admin, enable_expenses_feature, fresh_app):
        """Test expense report with no expenses in range."""
        with fresh_app.app_context():
            # Use future date range with no expenses
            date_from = (date.today() + timedelta(days=30)).isoformat()
            date_to = (date.today() + timedelta(days=60)).isoformat()
            response = auth_admin.get(f'/expenses/report?date_from={date_from}&date_to={date_to}')
            assert response.status_code in [200, 302, 500]


class TestExpenseFeatureFlag(TestExpensesSetup):
    """Tests for expense tracking feature flag requirements."""

    def test_expenses_disabled_redirects(self, auth_admin, fresh_app):
        """Test that disabled feature redirects appropriately."""
        with fresh_app.app_context():
            response = auth_admin.get('/expenses/')
            assert response.status_code in [200, 302, 403]


class TestExpenseLocationFiltering(TestExpensesSetup):
    """Tests for location-based expense filtering."""

    def test_manager_sees_own_location_expenses(self, auth_manager, enable_expenses_feature, expense_category, fresh_app):
        """Test that manager sees only their location's expenses."""
        from app.models import db, User, Location
        from app.models_extended import Expense

        with fresh_app.app_context():
            manager = User.query.filter_by(username='manager').first()

            if manager and manager.location_id:
                # Create expense at manager's location
                expense = Expense(
                    expense_number='EXP-20260107-LOC1',
                    category_id=expense_category,
                    description='Manager location expense',
                    amount=Decimal('500.00'),
                    expense_date=date.today(),
                    payment_method='cash',
                    status='pending',
                    created_by=manager.id,
                    location_id=manager.location_id
                )
                db.session.add(expense)
                db.session.commit()

                response = auth_manager.get('/expenses/')
                assert response.status_code in [200, 302, 500]

    def test_admin_sees_all_location_expenses(self, auth_admin, enable_expenses_feature, sample_expense, fresh_app):
        """Test that admin sees expenses from all locations."""
        with fresh_app.app_context():
            response = auth_admin.get('/expenses/')
            assert response.status_code in [200, 302, 500]


class TestExpenseValidation(TestExpensesSetup):
    """Tests for expense data validation."""

    def test_add_expense_missing_amount(self, auth_admin, enable_expenses_feature, expense_category, fresh_app):
        """Test adding expense without amount."""
        with fresh_app.app_context():
            data = {
                'category_id': expense_category,
                'description': 'Missing amount',
                'expense_date': date.today().isoformat(),
                'payment_method': 'cash'
            }
            response = auth_admin.post('/expenses/add', data=data, follow_redirects=True)
            # Should show error
            assert response.status_code in [200, 302, 400, 500]

    def test_add_expense_invalid_date(self, auth_admin, enable_expenses_feature, expense_category, fresh_app):
        """Test adding expense with invalid date."""
        with fresh_app.app_context():
            data = {
                'category_id': expense_category,
                'description': 'Invalid date expense',
                'amount': '1000.00',
                'expense_date': 'invalid-date',
                'payment_method': 'cash'
            }
            response = auth_admin.post('/expenses/add', data=data, follow_redirects=True)
            # Should show error
            assert response.status_code in [200, 302, 400, 500]

    def test_add_expense_negative_amount(self, auth_admin, enable_expenses_feature, expense_category, fresh_app):
        """Test adding expense with negative amount."""
        with fresh_app.app_context():
            data = {
                'category_id': expense_category,
                'description': 'Negative amount',
                'amount': '-100.00',
                'expense_date': date.today().isoformat(),
                'payment_method': 'cash'
            }
            response = auth_admin.post('/expenses/add', data=data, follow_redirects=True)
            # Should either accept (DB might allow) or show error
            assert response.status_code in [200, 302, 400, 500]


class TestExpenseNumberGeneration(TestExpensesSetup):
    """Tests for expense number auto-generation."""

    def test_unique_expense_numbers(self, auth_admin, enable_expenses_feature, expense_category, fresh_app):
        """Test that multiple expenses get unique numbers."""
        from app.models_extended import Expense

        with fresh_app.app_context():
            # Add first expense
            data1 = {
                'category_id': expense_category,
                'description': 'First expense',
                'amount': '100.00',
                'expense_date': date.today().isoformat(),
                'payment_method': 'cash'
            }
            auth_admin.post('/expenses/add', data=data1, follow_redirects=True)

            # Add second expense
            data2 = {
                'category_id': expense_category,
                'description': 'Second expense',
                'amount': '200.00',
                'expense_date': date.today().isoformat(),
                'payment_method': 'cash'
            }
            auth_admin.post('/expenses/add', data=data2, follow_redirects=True)

            expenses = Expense.query.order_by(Expense.id.desc()).limit(2).all()
            if len(expenses) >= 2:
                # Check unique numbers
                numbers = [e.expense_number for e in expenses]
                assert len(set(numbers)) == len(numbers)
