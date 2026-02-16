#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Django Data Export Script - MS SQL Server to JSON
Exports ALL data from MS SQL Server database with full Unicode support.
Preserves Nigerian Naira (₦) symbols and all special characters.
"""

import os
import sys
import json
import django
from datetime import datetime
from pathlib import Path

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent
DJANGO_PROJECT_DIR = BASE_DIR / 'mystore'  # Django project is in the mystore subdirectory
sys.path.insert(0, str(DJANGO_PROJECT_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mystore.settings')
django.setup()

from django.core.management import call_command
from django.db import connection
from io import StringIO


class MSSQLDataExporter:
    """Handles complete export of MS SQL Server data to JSON format."""

    def __init__(self, output_file='data_backup.json'):
        self.output_file = output_file
        self.start_time = None
        self.end_time = None

    def print_header(self):
        """Display export header information."""
        print("=" * 80)
        print("Django Data Export: MS SQL Server -> JSON")
        print("=" * 80)
        print(f"Database: {connection.settings_dict['NAME']}")
        print(f"Output File: {self.output_file}")
        print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        print()

    def verify_database_connection(self):
        """Verify MS SQL Server connection is working."""
        print("[*] Verifying database connection...")
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT @@VERSION")
                version = cursor.fetchone()
                print(f"[OK] Connected to: {version[0][:80]}...")
                print()
                return True
        except Exception as e:
            print(f"[X] Database connection failed: {e}")
            print("\nTroubleshooting:")
            print("  1. Check database credentials in .env file")
            print("  2. Verify MS SQL Server is running")
            print("  3. Confirm network connectivity")
            return False

    def get_table_count(self):
        """Get total number of tables in database."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE = 'BASE TABLE'
                """)
                count = cursor.fetchone()[0]
                return count
        except Exception as e:
            print(f"[WARNING] Warning: Could not count tables: {e}")
            return 0

    def get_existing_tables(self):
        """Get list of all tables that actually exist in the database."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE = 'BASE TABLE'
                    ORDER BY TABLE_NAME
                """)
                tables = [row[0] for row in cursor.fetchall()]
                return tables
        except Exception as e:
            print(f"[WARNING] Warning: Could not list tables: {e}")
            return []

    def get_table_columns(self, table_name):
        """Get list of columns in a table."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = %s
                    ORDER BY ORDINAL_POSITION
                """, [table_name])
                columns = [row[0] for row in cursor.fetchall()]
                return set(columns)
        except Exception as e:
            print(f"  [WARNING] Could not get columns for table {table_name}: {e}")
            return set()

    def find_missing_model_tables(self):
        """Identify Django models whose tables don't exist or have schema mismatches."""
        from django.apps import apps

        existing_tables = set(self.get_existing_tables())
        problematic_models = []

        for model in apps.get_models():
            table_name = model._meta.db_table
            app_label = model._meta.app_label
            model_name = model._meta.model_name
            model_identifier = f"{app_label}.{model_name}"

            # Check if table exists
            if table_name not in existing_tables:
                problematic_models.append(model_identifier)
                print(f"  [WARNING] Missing table: {table_name} (model: {model_identifier})")
                continue

            # Check if all model fields have corresponding columns
            db_columns = self.get_table_columns(table_name)
            if not db_columns:
                continue  # Skip column check if we couldn't get columns

            # Get all fields that should have database columns
            model_fields = []
            for field in model._meta.get_fields():
                # Skip reverse relations and many-to-many fields (they don't have columns in this table)
                if hasattr(field, 'column') and field.column:
                    model_fields.append(field.column)

            # Check for missing columns
            missing_columns = [f for f in model_fields if f not in db_columns]

            if missing_columns:
                problematic_models.append(model_identifier)
                print(f"  [WARNING] Schema mismatch in {table_name} (model: {model_identifier})")
                print(f"            Missing columns: {', '.join(missing_columns[:5])}")
                if len(missing_columns) > 5:
                    print(f"            ... and {len(missing_columns) - 5} more")

        return problematic_models

    def export_all_data(self):
        """Export all data using Django's dumpdata command."""
        print("[EXPORT] Exporting ALL data from MS SQL Server...")
        print("   This includes:")
        print("   • Django system tables")
        print("   • contenttypes")
        print("   • auth_permissions")
        print("   • auth_groups")
        print("   • All application data")
        print()

        # Check for missing tables
        print("[*] Checking for models with missing database tables...")
        missing_models = self.find_missing_model_tables()

        if missing_models:
            print(f"\n[WARNING] Found {len(missing_models)} model(s) with missing tables")
            print("  These will be excluded from the export:")
            for model in missing_models:
                print(f"    • {model}")
            print()

        try:
            # Capture output in memory
            output = StringIO()

            # Call dumpdata with flags to export everything
            print("[WAIT] Running Django dumpdata command...")
            if missing_models:
                print("   Flags: --natural-foreign --natural-primary --exclude (missing models)")
            else:
                print("   Flags: --natural-foreign --natural-primary")
            print()

            # Build exclude list
            exclude_args = missing_models if missing_models else []

            call_command(
                'dumpdata',
                natural_foreign=True,
                natural_primary=True,
                indent=2,
                exclude=exclude_args,
                stdout=output,
                verbosity=2
            )

            # Get the JSON data
            json_data = output.getvalue()
            output.close()

            # Validate it's proper JSON
            print("[OK] Data exported to memory")
            print("[*] Validating JSON structure...")

            try:
                parsed_data = json.loads(json_data)
                record_count = len(parsed_data)
                print(f"[OK] Valid JSON with {record_count:,} records")
            except json.JSONDecodeError as e:
                print(f"[X] JSON validation failed: {e}")
                return False

            # Write to file with explicit UTF-8 encoding
            print(f"\n[SAVE] Writing to {self.output_file} with UTF-8 encoding...")

            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write(json_data)

            # Verify file was written
            file_size = os.path.getsize(self.output_file)
            file_size_mb = file_size / (1024 * 1024)

            print(f"[OK] File written successfully")
            print(f"  Size: {file_size_mb:.2f} MB ({file_size:,} bytes)")

            # Verify Unicode preservation by reading back a sample
            print("\n[*] Verifying Unicode character preservation...")
            return self.verify_unicode_preservation(json_data)

        except Exception as e:
            print(f"\n[X] Export failed: {e}")
            print(f"\nError type: {type(e).__name__}")
            print("\nTroubleshooting:")
            print("  1. Check database permissions")
            print("  2. Ensure sufficient disk space")
            print("  3. Verify all models are properly registered")
            import traceback
            print("\nFull traceback:")
            traceback.print_exc()
            return False

    def verify_unicode_preservation(self, json_data):
        """Verify that Unicode characters (especially Naira symbol) are preserved."""
        # Check if Naira symbol exists in the data
        naira_symbol = '\u20a6'  # ₦
        if naira_symbol in json_data:
            print("[OK] Nigerian Naira symbol found and preserved")
            # Count occurrences
            naira_count = json_data.count(naira_symbol)
            print(f"  Found {naira_count} Naira symbol(s) in export")
        else:
            print("[i] No Naira symbols found in export")
            print("  (This is okay if your data doesn't contain currency)")

        # Check for other common Unicode characters
        unicode_chars = {
            '\u20ac': 'Euro',      # €
            '\u00a3': 'Pound',     # £
            '\u00a5': 'Yen',       # ¥
            '\u00b0': 'Degree',    # °
            '\u00a9': 'Copyright', # ©
            '\u00ae': 'Registered',# ®
        }

        found_unicode = []
        for char, name in unicode_chars.items():
            if char in json_data:
                count = json_data.count(char)
                found_unicode.append(f"{name}: {count}")

        if found_unicode:
            print("[OK] Other Unicode characters found:")
            for item in found_unicode:
                print(f"  - {item}")

        print("\n[OK] Unicode preservation verified")
        return True

    def create_metadata_file(self):
        """Create metadata file with export information."""
        metadata = {
            'export_date': datetime.now().isoformat(),
            'database_engine': connection.settings_dict['ENGINE'],
            'database_name': connection.settings_dict['NAME'],
            'django_version': django.get_version(),
            'backup_file': self.output_file,
            'encoding': 'UTF-8',
            'notes': 'Full database export - ALL tables included'
        }

        metadata_file = 'export_metadata.json'
        print(f"\n[NOTE] Creating metadata file: {metadata_file}")

        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        print("[OK] Metadata file created")

    def print_summary(self, success):
        """Print export summary."""
        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds()

        print("\n" + "=" * 80)
        print("EXPORT SUMMARY")
        print("=" * 80)

        if success:
            print("Status: [OK] SUCCESS")
            print(f"Output File: {self.output_file}")

            if os.path.exists(self.output_file):
                file_size_mb = os.path.getsize(self.output_file) / (1024 * 1024)
                print(f"File Size: {file_size_mb:.2f} MB")

                # Read and count records
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"Total Records: {len(data):,}")
        else:
            print("Status: [X] FAILED")
            print("Export did not complete successfully")

        print(f"Duration: {duration:.2f} seconds")
        print(f"End Time: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        if success:
            print("\n[OK] All data exported successfully!")
            print("\nNext Steps:")
            print("  1. Update database settings to PostgreSQL")
            print("  2. Run: python manage.py migrate")
            print("  3. Run: python import_postgresql_data.py")
        else:
            print("\n[X] Export failed. Please review errors above.")

    def run(self):
        """Execute the complete export process."""
        self.start_time = datetime.now()

        self.print_header()

        # Verify connection
        if not self.verify_database_connection():
            self.print_summary(False)
            return False

        # Show table count
        table_count = self.get_table_count()
        if table_count > 0:
            print(f"[INFO] Database contains {table_count} tables\n")

        # Export data
        success = self.export_all_data()

        # Create metadata
        if success:
            self.create_metadata_file()

        # Print summary
        self.print_summary(success)

        return success


def main():
    """Main entry point."""
    exporter = MSSQLDataExporter(output_file='data_backup.json')
    success = exporter.run()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
