"""
Utility functions for OEM Reporting
"""
from django.conf import settings


def get_database_for_oem():
    """
    Get the appropriate database for OEM reporting.

    In development (DEBUG=True), use 'default' database if oem_sync_db fails.
    In production (DEBUG=False), use 'oem_sync_db'.

    This allows local development to work even when remote MySQL is not accessible.
    """
    if settings.DEBUG:
        # Development: Try oem_sync_db first, fall back to default
        try:
            from django.db import connections
            conn = connections['oem_sync_db']
            conn.ensure_connection()
            return 'oem_sync_db'
        except Exception:
            # Can't connect to online DB, use local
            return 'default'
    else:
        # Production: Always use oem_sync_db
        return 'oem_sync_db'


def can_connect_to_oem_db():
    """
    Check if we can connect to the OEM sync database.
    Returns True if connection successful, False otherwise.
    """
    try:
        from django.db import connections
        conn = connections['oem_sync_db']
        conn.ensure_connection()
        return True
    except Exception:
        return False
