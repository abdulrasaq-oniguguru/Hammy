"""
Database Router for OEM Reporting System
Routes all oem_reporting models to separate online database while keeping main models in local database

Configuration:
Add to settings.py:
    DATABASE_ROUTERS = ['oem_reporting.database_router.OEMSyncRouter']
"""


class OEMSyncRouter:
    """
    Routes database operations for OEM reporting models to separate database
    All models in oem_reporting app are routed to oem_sync_db
    """

    # OEM reporting app label
    oem_app_label = 'oem_reporting'
    oem_database = 'oem_sync_db'

    # List of all sync model classes (for backward compatibility)
    sync_models = {
        'SyncMetadata',
        'InventorySnapshot',
        'SalesSummaryDaily',
        'SalesReportMonthly',
        'SalesByDayOfWeek',
        'SalesByHour',
        'ProductSalesDetail',
        'SalesTrend',
        'ComparisonReport',
        'TopSellingProduct',
        'LowStockAlert',
        'CategoryPerformance',
        'ShopPerformance',
        'InventoryTurnoverRate',
    }

    def db_for_read(self, model, **hints):
        """
        Route read operations for oem_reporting models to oem_sync_db
        """
        if model._meta.app_label == self.oem_app_label:
            return self.oem_database
        return None  # Let Django decide

    def db_for_write(self, model, **hints):
        """
        Route write operations for oem_reporting models to oem_sync_db
        """
        if model._meta.app_label == self.oem_app_label:
            return self.oem_database
        return None  # Let Django decide

    def allow_relation(self, obj1, obj2, **hints):
        """
        Allow relations only within same database
        """
        # If both models are from oem_reporting app
        if (obj1._meta.app_label == self.oem_app_label and
            obj2._meta.app_label == self.oem_app_label):
            return True

        # If both are from the same app (not oem_reporting)
        if (obj1._meta.app_label == obj2._meta.app_label and
            obj1._meta.app_label != self.oem_app_label):
            return True

        # Don't allow cross-database relations
        if (obj1._meta.app_label == self.oem_app_label or
            obj2._meta.app_label == self.oem_app_label):
            return False

        return None  # Let Django decide

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Ensure oem_reporting models are only migrated to oem_sync_db
        """
        # OEM reporting models go to oem_sync_db only
        if app_label == self.oem_app_label:
            return db == self.oem_database

        # Main app models go to default database only
        if app_label == 'store':
            return db == 'default'

        # Allow other apps to migrate on default
        return db == 'default'
