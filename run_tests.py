#!/usr/bin/env python3
"""
Test Runner Script for Sunnat Collection POS System
====================================================

This script provides various options for running tests:
- All tests
- Unit tests only
- Integration tests only
- Security tests only
- Specific test modules
- With coverage reporting
- Parallel execution

Usage:
    python run_tests.py                    # Run all tests
    python run_tests.py --unit             # Run unit tests only
    python run_tests.py --integration      # Run integration tests only
    python run_tests.py --security         # Run security tests only
    python run_tests.py --coverage         # Run with coverage report
    python run_tests.py --parallel         # Run tests in parallel
    python run_tests.py --smoke            # Run smoke tests only
    python run_tests.py --module models    # Run specific module tests
    python run_tests.py --verbose          # Verbose output
    python run_tests.py --html             # Generate HTML report
"""

import argparse
import subprocess
import sys
import os
from datetime import datetime


def get_test_command(args):
    """Build the pytest command based on arguments."""
    cmd = ['python', '-m', 'pytest']

    # Test selection
    if args.unit:
        cmd.extend(['-m', 'unit or not (integration or security or slow)'])
    elif args.integration:
        cmd.extend(['-m', 'integration'])
    elif args.security:
        cmd.extend(['-m', 'security'])
    elif args.smoke:
        cmd.extend(['-m', 'smoke'])
    elif args.edge_case:
        cmd.extend(['-m', 'edge_case'])
    elif args.slow:
        cmd.extend(['-m', 'slow'])

    # Specific module
    if args.module:
        module_map = {
            'models': 'tests/test_models_core.py tests/test_models_inventory.py',
            'pos': 'tests/test_routes_pos.py',
            'reports': 'tests/test_routes_reports.py',
            'auth': 'tests/test_auth_permissions.py',
            'inventory': 'tests/test_routes_inventory.py',
            'production': 'tests/test_production.py',
            'customers': 'tests/test_customers.py',
            'api': 'tests/test_api_endpoints.py',
            'utils': 'tests/test_utils.py',
            'integration': 'tests/test_integration.py',
            'forms': 'tests/test_forms.py',
            'security': 'tests/test_security.py',
            'edge': 'tests/test_edge_cases.py',
            'db': 'tests/test_database_integrity.py',
        }
        if args.module in module_map:
            cmd.extend(module_map[args.module].split())
        else:
            cmd.append(f'tests/test_{args.module}.py')

    # Coverage
    if args.coverage:
        cmd.extend([
            '--cov=app',
            '--cov-report=term-missing',
            '--cov-report=html:coverage_report',
            '--cov-fail-under=70'
        ])

    # Parallel execution
    if args.parallel:
        cmd.extend(['-n', 'auto'])

    # Verbosity
    if args.verbose:
        cmd.append('-vv')
    else:
        cmd.append('-v')

    # HTML report
    if args.html:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        cmd.extend([f'--html=test_reports/report_{timestamp}.html', '--self-contained-html'])

    # Stop on first failure
    if args.fail_fast:
        cmd.append('-x')

    # Show local variables in tracebacks
    if args.debug:
        cmd.append('-l')

    # Capture output
    if args.no_capture:
        cmd.append('-s')

    # Specific test
    if args.test:
        cmd.extend(['-k', args.test])

    return cmd


def run_tests(cmd):
    """Execute the test command."""
    print("=" * 70)
    print("SUNNAT COLLECTION POS - TEST RUNNER")
    print("=" * 70)
    print(f"Command: {' '.join(cmd)}")
    print("=" * 70)
    print()

    # Ensure test reports directory exists
    os.makedirs('test_reports', exist_ok=True)
    os.makedirs('coverage_report', exist_ok=True)

    # Run pytest
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))

    print()
    print("=" * 70)
    if result.returncode == 0:
        print("ALL TESTS PASSED!")
    else:
        print(f"TESTS FAILED (exit code: {result.returncode})")
    print("=" * 70)

    return result.returncode


def check_dependencies():
    """Check if required test dependencies are installed."""
    required = ['pytest', 'pytest-cov', 'pytest-flask']
    missing = []

    for package in required:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing.append(package)

    if missing:
        print("Missing test dependencies:")
        for pkg in missing:
            print(f"  - {pkg}")
        print("\nInstall with: pip install -r tests/requirements-test.txt")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Run tests for Sunnat Collection POS System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                         Run all tests
  %(prog)s --unit                  Run unit tests only
  %(prog)s --coverage              Run with coverage report
  %(prog)s --module pos            Run POS tests only
  %(prog)s --test "test_checkout"  Run tests matching pattern
  %(prog)s --parallel --coverage   Run in parallel with coverage
        """
    )

    # Test type selection
    test_type = parser.add_mutually_exclusive_group()
    test_type.add_argument('--unit', action='store_true', help='Run unit tests only')
    test_type.add_argument('--integration', action='store_true', help='Run integration tests only')
    test_type.add_argument('--security', action='store_true', help='Run security tests only')
    test_type.add_argument('--smoke', action='store_true', help='Run smoke tests only')
    test_type.add_argument('--edge-case', dest='edge_case', action='store_true', help='Run edge case tests only')
    test_type.add_argument('--slow', action='store_true', help='Run slow tests only')

    # Module selection
    parser.add_argument('--module', '-m', type=str,
                       help='Run specific module (models, pos, reports, auth, inventory, production, customers, api, utils, integration, forms, security, edge, db)')

    # Test pattern
    parser.add_argument('--test', '-t', type=str, help='Run tests matching pattern')

    # Output options
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--coverage', '-c', action='store_true', help='Generate coverage report')
    parser.add_argument('--html', action='store_true', help='Generate HTML report')
    parser.add_argument('--no-capture', action='store_true', help='Don\'t capture stdout/stderr')

    # Execution options
    parser.add_argument('--parallel', '-p', action='store_true', help='Run tests in parallel')
    parser.add_argument('--fail-fast', '-x', action='store_true', help='Stop on first failure')
    parser.add_argument('--debug', '-d', action='store_true', help='Show debug info')

    # Skip dependency check
    parser.add_argument('--skip-check', action='store_true', help='Skip dependency check')

    args = parser.parse_args()

    # Check dependencies
    if not args.skip_check and not check_dependencies():
        sys.exit(1)

    # Build and run command
    cmd = get_test_command(args)
    sys.exit(run_tests(cmd))


if __name__ == '__main__':
    main()
