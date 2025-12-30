#!/usr/bin/env python3
"""
Clean up old has_permission checks that are now redundant with RBAC decorators
"""

import re
import os

def remove_old_permission_checks(filepath):
    """Remove redundant has_permission checks from file"""
    print(f"Processing {filepath}...")

    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()

        new_lines = []
        skip_until = -1
        removed_count = 0

        for i, line in enumerate(lines):
            # Skip lines if we're in a block to remove
            if i < skip_until:
                continue

            # Check for old permission check pattern
            if 'if not has_permission(' in line:
                # Look ahead to find the end of this block
                indent = len(line) - len(line.lstrip())
                block_end = i + 1

                # Find the end of the if block (next line with same or less indentation)
                while block_end < len(lines):
                    next_line = lines[block_end]
                    if next_line.strip() and not next_line.strip().startswith('#'):
                        next_indent = len(next_line) - len(next_line.lstrip())
                        if next_indent <= indent:
                            break
                    block_end += 1

                # Skip this block
                skip_until = block_end
                removed_count += 1
                print(f"  ✓ Removed redundant permission check at line {i+1}")
                continue

            new_lines.append(line)

        # Write back if changes were made
        if removed_count > 0:
            with open(filepath, 'w') as f:
                f.writelines(new_lines)
            print(f"✓ Removed {removed_count} redundant checks from {filepath}")
        else:
            print(f"  No redundant checks found")

        return removed_count

    except Exception as e:
        print(f"✗ Error: {e}")
        return 0


def main():
    """Main execution"""
    print("=" * 60)
    print("Cleaning Up Redundant Permission Checks")
    print("=" * 60)

    route_files = [
        'app/routes/customers.py',
        'app/routes/reports.py',
    ]

    total_removed = 0
    for filepath in route_files:
        if os.path.exists(filepath):
            count = remove_old_permission_checks(filepath)
            total_removed += count
        else:
            print(f"File not found: {filepath}")

    print("\n" + "=" * 60)
    print(f"Total: Removed {total_removed} redundant permission checks")
    print("=" * 60)


if __name__ == '__main__':
    main()
