"""
OEM/Inventory Sync Models
These models represent the data structure for the SEPARATE online database.
They contain only non-sensitive, aggregated data for reporting purposes.

SECURITY: This module is designed to be deployed to a SEPARATE database.
NO sensitive customer information, payment details, or transaction logs are included.
"""

from django.db import models
from django.utils import timezone
from decimal import Decimal


class SyncMetadata(models.Model):
    """
    Tracks when data was last synced from main system
    """
    sync_type = models.CharField(
        max_length=50,
        unique=True,
        help_text="Type of data synced (inventory, sales, etc.)"
    )
    last_sync_time = models.DateTimeField(
        help_text="When this data was last updated"
    )
    sync_status = models.CharField(
        max_length=20,
        choices=[
            ('success', 'Success'),
            ('failed', 'Failed'),
            ('in_progress', 'In Progress'),
        ],
        default='success'
    )
    records_synced = models.IntegerField(
        default=0,
        help_text="Number of records updated in last sync"
    )
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'sync_metadata'
        verbose_name = "Sync Metadata"
        verbose_name_plural = "Sync Metadata"

    def __str__(self):
        return f"{self.sync_type} - Last synced: {self.last_sync_time}"


class InventorySnapshot(models.Model):
    """
    Current inventory levels - updated every sync
    NO PRICING INFORMATION (optional - can be included if needed)
    """
    # Product Identification (no sensitive SKU/internal codes)
    product_id = models.IntegerField(
        help_text="Reference ID from main system (for updates)"
    )
    brand = models.CharField(max_length=100)
    category = models.CharField(max_length=100)
    size = models.CharField(max_length=10)
    color = models.CharField(max_length=50, blank=True, null=True)
    design = models.CharField(max_length=50, blank=True, null=True)

    # Inventory Data
    quantity_available = models.IntegerField(
        help_text="Current stock level"
    )
    location = models.CharField(
        max_length=10,
        choices=[('ABUJA', 'Abuja'), ('LAGOS', 'Lagos')]
    )
    shop = models.CharField(max_length=100)

    # Status flags
    is_low_stock = models.BooleanField(
        default=False,
        help_text="Flagged if quantity below threshold"
    )
    is_out_of_stock = models.BooleanField(
        default=False,
        help_text="Flagged if quantity is zero"
    )

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)
    data_source_timestamp = models.DateTimeField(
        help_text="When this data was extracted from main system"
    )

    class Meta:
        db_table = 'inventory_snapshot'
        verbose_name = "Inventory Snapshot"
        verbose_name_plural = "Inventory Snapshots"
        indexes = [
            models.Index(fields=['brand']),
            models.Index(fields=['category']),
            models.Index(fields=['location']),
            models.Index(fields=['shop']),
            models.Index(fields=['is_low_stock']),
            models.Index(fields=['product_id']),
        ]
        # Ensure each product_id is unique in snapshot
        unique_together = ['product_id']

    def __str__(self):
        return f"{self.brand} - {self.category} ({self.location})"


class SalesSummaryDaily(models.Model):
    """
    Aggregated daily sales statistics
    NO individual transactions, NO customer data, NO payment details
    """
    summary_date = models.DateField()

    # Aggregation dimensions
    category = models.CharField(max_length=100, blank=True, null=True)
    shop = models.CharField(max_length=100, blank=True, null=True)
    location = models.CharField(
        max_length=10,
        choices=[('ABUJA', 'Abuja'), ('LAGOS', 'Lagos')],
        blank=True,
        null=True
    )

    # Metrics
    total_units_sold = models.IntegerField(default=0)
    total_transactions = models.IntegerField(
        default=0,
        help_text="Number of sales transactions (not individual customers)"
    )

    # Optional: Revenue (can be excluded if too sensitive)
    total_revenue = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        blank=True,
        null=True,
        help_text="Total revenue for this period (optional)"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sales_summary_daily'
        verbose_name = "Daily Sales Summary"
        verbose_name_plural = "Daily Sales Summaries"
        indexes = [
            models.Index(fields=['summary_date']),
            models.Index(fields=['category']),
            models.Index(fields=['shop']),
            models.Index(fields=['location']),
        ]
        # Prevent duplicate summaries for same date/category/shop/location
        unique_together = [['summary_date', 'category', 'shop', 'location']]

    def __str__(self):
        return f"{self.summary_date} - {self.category or 'All'} ({self.total_units_sold} units)"


class TopSellingProduct(models.Model):
    """
    Top performing products (updated daily or weekly)
    """
    PERIOD_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    period_type = models.CharField(max_length=10, choices=PERIOD_CHOICES)
    period_start = models.DateField()
    period_end = models.DateField()

    # Product info (aggregated, no pricing)
    brand = models.CharField(max_length=100)
    category = models.CharField(max_length=100)
    location = models.CharField(
        max_length=10,
        choices=[('ABUJA', 'Abuja'), ('LAGOS', 'Lagos')]
    )

    # Performance metrics
    units_sold = models.IntegerField()
    rank = models.IntegerField(
        help_text="Ranking for this period (1 = best seller)"
    )

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'top_selling_products'
        verbose_name = "Top Selling Product"
        verbose_name_plural = "Top Selling Products"
        indexes = [
            models.Index(fields=['period_type', 'period_start']),
            models.Index(fields=['rank']),
            models.Index(fields=['category']),
        ]
        ordering = ['period_start', 'rank']

    def __str__(self):
        return f"#{self.rank} - {self.brand} ({self.period_type})"


class LowStockAlert(models.Model):
    """
    Products that need restocking
    """
    ALERT_LEVEL_CHOICES = [
        ('low', 'Low Stock'),
        ('critical', 'Critical Stock'),
        ('out', 'Out of Stock'),
    ]

    product_id = models.IntegerField()
    brand = models.CharField(max_length=100)
    category = models.CharField(max_length=100)
    size = models.CharField(max_length=10)
    color = models.CharField(max_length=50, blank=True, null=True)
    location = models.CharField(
        max_length=10,
        choices=[('ABUJA', 'Abuja'), ('LAGOS', 'Lagos')]
    )

    current_quantity = models.IntegerField()
    alert_level = models.CharField(max_length=10, choices=ALERT_LEVEL_CHOICES)

    # Metadata
    alert_date = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(
        default=False,
        help_text="Set to True when restocked"
    )
    resolved_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'low_stock_alerts'
        verbose_name = "Low Stock Alert"
        verbose_name_plural = "Low Stock Alerts"
        indexes = [
            models.Index(fields=['is_resolved']),
            models.Index(fields=['alert_level']),
            models.Index(fields=['location']),
        ]
        ordering = ['-alert_date']

    def __str__(self):
        return f"{self.brand} - {self.alert_level} ({self.current_quantity} left)"


class CategoryPerformance(models.Model):
    """
    Performance metrics by product category
    """
    period_start = models.DateField()
    period_end = models.DateField()

    category = models.CharField(max_length=100)
    location = models.CharField(
        max_length=10,
        choices=[('ABUJA', 'Abuja'), ('LAGOS', 'Lagos')],
        blank=True,
        null=True
    )

    # Metrics
    total_units_sold = models.IntegerField(default=0)
    total_products_in_category = models.IntegerField(
        default=0,
        help_text="Number of different products in this category"
    )
    average_stock_level = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Average inventory level"
    )

    # Optional: Revenue metrics
    total_revenue = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        blank=True,
        null=True
    )

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'category_performance'
        verbose_name = "Category Performance"
        verbose_name_plural = "Category Performance"
        indexes = [
            models.Index(fields=['period_start']),
            models.Index(fields=['category']),
            models.Index(fields=['location']),
        ]
        unique_together = [['period_start', 'period_end', 'category', 'location']]

    def __str__(self):
        return f"{self.category} ({self.period_start} - {self.period_end})"


class ShopPerformance(models.Model):
    """
    OEM/Shop performance metrics
    """
    period_start = models.DateField()
    period_end = models.DateField()

    shop = models.CharField(max_length=100)
    location = models.CharField(
        max_length=10,
        choices=[('ABUJA', 'Abuja'), ('LAGOS', 'Lagos')]
    )

    # Metrics
    total_units_sold = models.IntegerField(default=0)
    unique_products_sold = models.IntegerField(
        default=0,
        help_text="Number of different products sold"
    )
    current_stock_count = models.IntegerField(
        default=0,
        help_text="Current inventory count for this shop"
    )

    # Optional: Revenue
    total_revenue = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        blank=True,
        null=True
    )

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shop_performance'
        verbose_name = "Shop Performance"
        verbose_name_plural = "Shop Performance"
        indexes = [
            models.Index(fields=['period_start']),
            models.Index(fields=['shop']),
            models.Index(fields=['location']),
        ]
        unique_together = [['period_start', 'period_end', 'shop', 'location']]

    def __str__(self):
        return f"{self.shop} - {self.location} ({self.period_start})"


class InventoryTurnoverRate(models.Model):
    """
    How quickly inventory is moving
    """
    period_start = models.DateField()
    period_end = models.DateField()

    category = models.CharField(max_length=100, blank=True, null=True)
    shop = models.CharField(max_length=100, blank=True, null=True)
    location = models.CharField(
        max_length=10,
        choices=[('ABUJA', 'Abuja'), ('LAGOS', 'Lagos')],
        blank=True,
        null=True
    )

    # Metrics
    average_inventory = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Average inventory level during period"
    )
    units_sold = models.IntegerField()
    turnover_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Times inventory turned over (higher = faster moving)"
    )
    days_to_sell = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Average days to sell through inventory"
    )

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventory_turnover_rate'
        verbose_name = "Inventory Turnover Rate"
        verbose_name_plural = "Inventory Turnover Rates"
        indexes = [
            models.Index(fields=['period_start']),
            models.Index(fields=['category']),
            models.Index(fields=['shop']),
        ]

    def __str__(self):
        return f"{self.category or 'All'} - Turnover: {self.turnover_rate}x"


class SalesReportMonthly(models.Model):
    """
    Comprehensive monthly sales report
    Aggregated data with NO individual customer or transaction details
    """
    report_month = models.DateField(help_text="First day of the month")

    # Dimensions
    category = models.CharField(max_length=100, blank=True, null=True)
    shop = models.CharField(max_length=100, blank=True, null=True)
    location = models.CharField(
        max_length=10,
        choices=[('ABUJA', 'Abuja'), ('LAGOS', 'Lagos')],
        blank=True,
        null=True
    )

    # Sales Metrics
    total_units_sold = models.IntegerField(default=0)
    total_transactions = models.IntegerField(default=0)
    total_revenue = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    average_transaction_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # Comparison with previous month
    revenue_growth_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Growth % compared to previous month"
    )
    units_growth_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sales_report_monthly'
        verbose_name = "Monthly Sales Report"
        verbose_name_plural = "Monthly Sales Reports"
        indexes = [
            models.Index(fields=['report_month']),
            models.Index(fields=['category']),
            models.Index(fields=['shop']),
            models.Index(fields=['location']),
        ]
        unique_together = [['report_month', 'category', 'shop', 'location']]

    def __str__(self):
        return f"{self.report_month.strftime('%B %Y')} - {self.category or 'All'}"


class SalesByDayOfWeek(models.Model):
    """
    Sales patterns by day of week
    Helps identify peak sales days
    """
    DAYS_OF_WEEK = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]

    period_start = models.DateField()
    period_end = models.DateField()
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK)

    # Dimensions
    location = models.CharField(
        max_length=10,
        choices=[('ABUJA', 'Abuja'), ('LAGOS', 'Lagos')],
        blank=True,
        null=True
    )

    # Metrics
    total_transactions = models.IntegerField(default=0)
    total_units_sold = models.IntegerField(default=0)
    total_revenue = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    average_daily_transactions = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sales_by_day_of_week'
        verbose_name = "Sales by Day of Week"
        verbose_name_plural = "Sales by Day of Week"
        indexes = [
            models.Index(fields=['period_start']),
            models.Index(fields=['day_of_week']),
            models.Index(fields=['location']),
        ]
        unique_together = [['period_start', 'period_end', 'day_of_week', 'location']]

    def __str__(self):
        return f"{self.get_day_of_week_display()} - {self.period_start}"


class SalesByHour(models.Model):
    """
    Sales patterns by hour of day
    Helps identify peak sales hours
    """
    period_start = models.DateField()
    period_end = models.DateField()
    hour = models.IntegerField(help_text="Hour of day (0-23)")

    # Dimensions
    location = models.CharField(
        max_length=10,
        choices=[('ABUJA', 'Abuja'), ('LAGOS', 'Lagos')],
        blank=True,
        null=True
    )

    # Metrics
    total_transactions = models.IntegerField(default=0)
    total_units_sold = models.IntegerField(default=0)
    total_revenue = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sales_by_hour'
        verbose_name = "Sales by Hour"
        verbose_name_plural = "Sales by Hour"
        indexes = [
            models.Index(fields=['period_start']),
            models.Index(fields=['hour']),
            models.Index(fields=['location']),
        ]
        unique_together = [['period_start', 'period_end', 'hour', 'location']]

    def __str__(self):
        return f"Hour {self.hour}:00 - {self.period_start}"


class ProductSalesDetail(models.Model):
    """
    Detailed sales data per product
    NO customer information, only product performance
    """
    period_start = models.DateField()
    period_end = models.DateField()

    # Product identification
    product_id = models.IntegerField()
    brand = models.CharField(max_length=100)
    category = models.CharField(max_length=100)
    size = models.CharField(max_length=10)
    color = models.CharField(max_length=50, blank=True, null=True)
    shop = models.CharField(max_length=100)
    location = models.CharField(
        max_length=10,
        choices=[('ABUJA', 'Abuja'), ('LAGOS', 'Lagos')]
    )

    # Sales metrics
    units_sold = models.IntegerField(default=0)
    transactions_count = models.IntegerField(default=0)
    total_revenue = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    average_units_per_transaction = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # Inventory impact
    stock_at_period_start = models.IntegerField(default=0)
    stock_at_period_end = models.IntegerField(default=0)

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'product_sales_detail'
        verbose_name = "Product Sales Detail"
        verbose_name_plural = "Product Sales Details"
        indexes = [
            models.Index(fields=['period_start']),
            models.Index(fields=['product_id']),
            models.Index(fields=['brand']),
            models.Index(fields=['category']),
            models.Index(fields=['shop']),
            models.Index(fields=['location']),
        ]
        unique_together = [['period_start', 'period_end', 'product_id']]

    def __str__(self):
        return f"{self.brand} - {self.period_start}"


class SalesTrend(models.Model):
    """
    Sales trends and forecasting data
    """
    TREND_PERIOD = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    period_type = models.CharField(max_length=10, choices=TREND_PERIOD)
    period_date = models.DateField()

    # Dimensions
    category = models.CharField(max_length=100, blank=True, null=True)
    location = models.CharField(
        max_length=10,
        choices=[('ABUJA', 'Abuja'), ('LAGOS', 'Lagos')],
        blank=True,
        null=True
    )

    # Metrics
    revenue = models.DecimalField(max_digits=15, decimal_places=2)
    units_sold = models.IntegerField()
    transactions = models.IntegerField()

    # Trend indicators
    revenue_trend = models.CharField(
        max_length=20,
        choices=[
            ('increasing', 'Increasing'),
            ('decreasing', 'Decreasing'),
            ('stable', 'Stable'),
        ],
        blank=True,
        null=True
    )
    growth_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Percentage growth compared to previous period"
    )

    # Moving averages
    moving_average_7day = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        blank=True,
        null=True
    )
    moving_average_30day = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        blank=True,
        null=True
    )

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sales_trend'
        verbose_name = "Sales Trend"
        verbose_name_plural = "Sales Trends"
        indexes = [
            models.Index(fields=['period_date']),
            models.Index(fields=['period_type']),
            models.Index(fields=['category']),
            models.Index(fields=['location']),
        ]
        unique_together = [['period_type', 'period_date', 'category', 'location']]

    def __str__(self):
        return f"{self.period_type} - {self.period_date}"


class ComparisonReport(models.Model):
    """
    Comparative analysis between periods, locations, or categories
    """
    COMPARISON_TYPE = [
        ('location', 'Location Comparison'),
        ('period', 'Period Comparison'),
        ('category', 'Category Comparison'),
        ('shop', 'Shop Comparison'),
    ]

    comparison_type = models.CharField(max_length=20, choices=COMPARISON_TYPE)
    report_date = models.DateField()

    # Comparison dimensions
    dimension_a = models.CharField(max_length=100, help_text="First item being compared")
    dimension_b = models.CharField(max_length=100, help_text="Second item being compared")

    # Metrics for dimension A
    revenue_a = models.DecimalField(max_digits=15, decimal_places=2)
    units_a = models.IntegerField()
    transactions_a = models.IntegerField()

    # Metrics for dimension B
    revenue_b = models.DecimalField(max_digits=15, decimal_places=2)
    units_b = models.IntegerField()
    transactions_b = models.IntegerField()

    # Differences
    revenue_difference = models.DecimalField(max_digits=15, decimal_places=2)
    revenue_difference_percent = models.DecimalField(max_digits=5, decimal_places=2)
    units_difference = models.IntegerField()
    units_difference_percent = models.DecimalField(max_digits=5, decimal_places=2)

    # Winner
    better_performer = models.CharField(max_length=100, help_text="Which dimension performed better")

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'comparison_report'
        verbose_name = "Comparison Report"
        verbose_name_plural = "Comparison Reports"
        indexes = [
            models.Index(fields=['report_date']),
            models.Index(fields=['comparison_type']),
        ]

    def __str__(self):
        return f"{self.get_comparison_type_display()} - {self.dimension_a} vs {self.dimension_b}"


# Summary: What's NOT included (Security)
"""
EXCLUDED FOR SECURITY (Not synced):
- Individual customer names, emails, phone numbers
- Customer addresses
- Payment methods and transaction details
- Payment statuses and amounts per transaction
- Individual sale records with customer linkage
- Receipt numbers and individual transactions
- User/staff information
- Pricing details (optional - can be included if needed for OEM reports)
- Supplier/vendor information
- Invoice details
- Delivery addresses

INCLUDED (Safe for reporting):
- Aggregated sales statistics
- Inventory levels and product information
- Category and shop performance metrics
- Stock alerts
- Trend analysis data
- Top sellers
"""
