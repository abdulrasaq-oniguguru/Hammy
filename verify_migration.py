#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Django Migration Verification Script
Verifies data integrity after migration from MS SQL Server to PostgreSQL.
Checks record counts, Unicode preservation, and data integrity.
"""

import os
import sys
import json
import django
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mystore.settings')
django.setup()

from django.apps import apps
from django.db import connection
from django.core.exceptions import FieldDoesNotExist


class MigrationVerifier:
    """Verifies data integrity after migration to PostgreSQL."""

    def __init__(self, backup_file='data_backup.json'):
        self.backup_file = backup_file
        self.backup_data = None
        self.results = {
            'models_checked': 0,
            'total_backup_records': 0,
            'total_db_records': 0,
            'models_matched': 0,
            'models_mismatched': 0,
            'unicode_checks_passed': 0,
            'unicode_checks_failed': 0,
            'errors': []
        }
        self.model_details = []

    def print_header(self):
        """Display verification header."""
        print("=" * 80)
        print("Django Migration Verification")
        print("=" * 80)
        print(f"Database: {connection.settings_dict['NAME']}")
        print(f"Backup File: {self.backup_file}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        print()

    def verify_database_connection(self):
        """Verify PostgreSQL connection and encoding."""
        print("🔍 Verifying database connection...")
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version()")
                version = cursor.fetchone()[0][:80]
                print(f"✓ Database: {version}...")

                cursor.execute("SHOW client_encoding")
                encoding = cursor.fetchone()[0]
                print(f"✓ Encoding: {encoding}")

                if encoding.upper() != 'UTF8':
                    print(f"⚠ Warning: Expected UTF8, got {encoding}")
                    self.results['errors'].append(f"Database encoding is {encoding}, not UTF8")

                print()
                return True

        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False

    def load_backup_data(self):
        """Load and parse backup JSON file."""
        print(f"📂 Loading backup file: {self.backup_file}")

        if not os.path.exists(self.backup_file):
            print(f"✗ Backup file not found: {self.backup_file}")
            return False

        try:
            with open(self.backup_file, 'r', encoding='utf-8') as f:
                self.backup_data = json.load(f)

            self.results['total_backup_records'] = len(self.backup_data)
            print(f"✓ Loaded {self.results['total_backup_records']:,} records from backup")
            print()
            return True

        except Exception as e:
            print(f"✗ Failed to load backup: {e}")
            return False

    def group_backup_by_model(self):
        """Group backup records by model."""
        grouped = defaultdict(list)

        for record in self.backup_data:
            model_name = record.get('model')
            if model_name:
                grouped[model_name].append(record)

        return grouped

    def get_model_from_name(self, model_name):
        """Get Django model class from 'app.model' string."""
        try:
            app_label, model_label = model_name.split('.')
            return apps.get_model(app_label, model_label)
        except (ValueError, LookupError):
            return None

    def verify_record_counts(self):
        """Compare record counts between backup and database."""
        print("📊 Verifying record counts...")
        print()

        grouped_backup = self.group_backup_by_model()

        # Sort models for consistent output
        model_names = sorted(grouped_backup.keys())

        for model_name in model_names:
            self.results['models_checked'] += 1

            backup_records = grouped_backup[model_name]
            backup_count = len(backup_records)

            # Get model class
            model_class = self.get_model_from_name(model_name)

            if model_class is None:
                print(f"⚠ {model_name:40} - Model not found in current app")
                self.results['errors'].append(f"Model {model_name} not found")
                continue

            # Get database count
            try:
                db_count = model_class.objects.count()
            except Exception as e:
                print(f"✗ {model_name:40} - Error querying: {e}")
                self.results['errors'].append(f"{model_name}: {e}")
                continue

            # Compare counts
            status = "✓" if backup_count == db_count else "✗"
            match = backup_count == db_count

            if match:
                self.results['models_matched'] += 1
            else:
                self.results['models_mismatched'] += 1

            self.results['total_db_records'] += db_count

            # Store details
            detail = {
                'model': model_name,
                'backup_count': backup_count,
                'db_count': db_count,
                'match': match,
                'difference': db_count - backup_count
            }
            self.model_details.append(detail)

            # Print status
            diff_str = ""
            if not match:
                diff = db_count - backup_count
                diff_str = f" (diff: {diff:+d})"

            print(f"{status} {model_name:40} Backup: {backup_count:6,} | DB: {db_count:6,}{diff_str}")

        print()

    def verify_unicode_in_database(self):
        """Verify Unicode characters (especially ₦) in database."""
        print("🔍 Verifying Unicode character preservation...")
        print()

        # Look for models that might contain currency or Unicode
        test_models = []

        for model in apps.get_models():
            # Get text/char fields
            for field in model._meta.get_fields():
                if hasattr(field, 'get_internal_type'):
                    field_type = field.get_internal_type()
                    if field_type in ['CharField', 'TextField']:
                        test_models.append((model, field.name))
                        break

        if not test_models:
            print("ℹ No text fields found to test")
            return

        # Sample check for Naira symbol
        naira_found = False
        models_with_naira = []

        for model_class, field_name in test_models:
            try:
                # Check if any record contains Naira symbol
                filter_kwargs = {f"{field_name}__contains": "₦"}
                count = model_class.objects.filter(**filter_kwargs).count()

                if count > 0:
                    naira_found = True
                    models_with_naira.append((model_class.__name__, count))
                    self.results['unicode_checks_passed'] += 1

            except Exception:
                # Field might not support this query
                continue

        if naira_found:
            print("✓ Nigerian Naira symbol (₦) found in database:")
            for model_name, count in models_with_naira:
                print(f"  • {model_name}: {count} record(s)")
            print()
        else:
            # Check if it was in the backup
            backup_text = json.dumps(self.backup_data)
            if '₦' in backup_text:
                print("⚠ Naira symbol (₦) was in backup but not found in database")
                print("  This could indicate a Unicode preservation issue!")
                self.results['unicode_checks_failed'] += 1
                self.results['errors'].append("Naira symbol not preserved in migration")
            else:
                print("ℹ No Naira symbols (₦) in original data")
                print("  (This is okay if your data doesn't contain currency)")

    def verify_sample_records(self):
        """Verify a sample of actual record data."""
        print("\n🔬 Performing sample data verification...")
        print()

        grouped_backup = self.group_backup_by_model()

        # Pick a few models to sample
        sample_count = 0
        max_samples = 5

        for model_name, records in grouped_backup.items():
            if sample_count >= max_samples:
                break

            if not records:
                continue

            model_class = self.get_model_from_name(model_name)
            if not model_class:
                continue

            # Take first record from backup
            sample_record = records[0]
            pk_value = sample_record.get('pk')

            if pk_value is None:
                continue

            try:
                # Try to fetch from database
                db_record = model_class.objects.get(pk=pk_value)
                print(f"✓ {model_name} (pk={pk_value}): Record exists in database")
                sample_count += 1

            except model_class.DoesNotExist:
                print(f"✗ {model_name} (pk={pk_value}): Record missing from database")
                self.results['errors'].append(f"{model_name} pk={pk_value} missing")

            except Exception as e:
                print(f"⚠ {model_name} (pk={pk_value}): Error checking - {e}")

        print()

    def generate_detailed_report(self):
        """Generate detailed verification report."""
        print("\n" + "=" * 80)
        print("DETAILED VERIFICATION REPORT")
        print("=" * 80)
        print()

        # Overall statistics
        print("Overall Statistics:")
        print(f"  Models Checked: {self.results['models_checked']}")
        print(f"  Total Backup Records: {self.results['total_backup_records']:,}")
        print(f"  Total Database Records: {self.results['total_db_records']:,}")
        print()

        # Count comparison
        print("Record Count Comparison:")
        print(f"  ✓ Matched Models: {self.results['models_matched']}")
        print(f"  ✗ Mismatched Models: {self.results['models_mismatched']}")

        if self.results['models_mismatched'] > 0:
            print("\n  Mismatched Details:")
            for detail in self.model_details:
                if not detail['match']:
                    print(f"    • {detail['model']:40} "
                          f"Backup: {detail['backup_count']:6,} | "
                          f"DB: {detail['db_count']:6,} | "
                          f"Diff: {detail['difference']:+6,}")

        print()

        # Unicode verification
        print("Unicode Verification:")
        print(f"  ✓ Checks Passed: {self.results['unicode_checks_passed']}")
        print(f"  ✗ Checks Failed: {self.results['unicode_checks_failed']}")
        print()

        # Errors
        if self.results['errors']:
            print(f"Errors Found ({len(self.results['errors'])}):")
            for error in self.results['errors'][:10]:  # Show first 10
                print(f"  • {error}")
            if len(self.results['errors']) > 10:
                print(f"  ... and {len(self.results['errors']) - 10} more")
            print()

    def generate_summary(self):
        """Generate final summary."""
        print("=" * 80)
        print("MIGRATION VERIFICATION SUMMARY")
        print("=" * 80)
        print()

        # Determine overall status
        critical_issues = (
            self.results['models_mismatched'] > 0 or
            self.results['unicode_checks_failed'] > 0 or
            len(self.results['errors']) > 0
        )

        if critical_issues:
            print("Status: ⚠ ISSUES FOUND")
            print()
            print("Migration completed but with issues:")

            if self.results['models_mismatched'] > 0:
                print(f"  • {self.results['models_mismatched']} model(s) have mismatched record counts")

            if self.results['unicode_checks_failed'] > 0:
                print(f"  • {self.results['unicode_checks_failed']} Unicode check(s) failed")

            if self.results['errors']:
                print(f"  • {len(self.results['errors'])} error(s) logged")

            print()
            print("Recommendations:")
            print("  1. Review mismatched models above")
            print("  2. Check for import errors in import_log.json")
            print("  3. Verify Unicode settings in PostgreSQL")
            print("  4. Consider re-running import if issues are critical")

        else:
            print("Status: ✓ SUCCESS")
            print()
            print("Migration verified successfully!")
            print(f"  • All {self.results['models_checked']} models matched")
            print(f"  • {self.results['total_db_records']:,} records in database")
            print("  • Unicode characters preserved")
            print()
            print("✓ Your application is ready to use with PostgreSQL!")

        print("=" * 80)

    def save_verification_report(self):
        """Save verification results to JSON file."""
        report = {
            'verification_date': datetime.now().isoformat(),
            'database': connection.settings_dict['NAME'],
            'backup_file': self.backup_file,
            'results': self.results,
            'model_details': self.model_details
        }

        report_file = 'verification_report.json'
        print(f"\n💾 Saving verification report: {report_file}")

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"✓ Report saved to {report_file}")

    def run(self):
        """Execute the complete verification process."""
        self.print_header()

        # Verify connection
        if not self.verify_database_connection():
            return False

        # Load backup
        if not self.load_backup_data():
            return False

        # Run verifications
        self.verify_record_counts()
        self.verify_unicode_in_database()
        self.verify_sample_records()

        # Generate reports
        self.generate_detailed_report()
        self.generate_summary()
        self.save_verification_report()

        # Return success if no critical issues
        return (
            self.results['models_mismatched'] == 0 and
            self.results['unicode_checks_failed'] == 0 and
            len(self.results['errors']) == 0
        )


def main():
    """Main entry point."""
    verifier = MigrationVerifier(backup_file='data_backup.json')
    success = verifier.run()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
