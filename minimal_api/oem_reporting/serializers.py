"""
OEM Reporting Serializers
Serializers for all OEM/Inventory/Sales reporting models
"""

from rest_framework import serializers
from .models import (
    InventorySnapshot,
    SalesSummaryDaily,
    TopSellingProduct,
    LowStockAlert,
    CategoryPerformance,
    ShopPerformance,
    SyncMetadata,
    SalesReportMonthly,
    SalesByDayOfWeek,
    SalesByHour,
    ProductSalesDetail,
    SalesTrend,
    ComparisonReport,
    InventoryTurnoverRate,
)


# ===========================
# BASIC SERIALIZERS
# ===========================

class InventorySnapshotSerializer(serializers.ModelSerializer):
    """Serialize inventory data"""

    class Meta:
        model = InventorySnapshot
        fields = [
            'product_id', 'brand', 'category', 'size', 'color', 'design',
            'quantity_available', 'location', 'shop',
            'is_low_stock', 'is_out_of_stock', 'last_updated'
        ]


class SalesSummarySerializer(serializers.ModelSerializer):
    """Serialize sales summary data"""

    class Meta:
        model = SalesSummaryDaily
        fields = [
            'summary_date', 'category', 'shop', 'location',
            'total_units_sold', 'total_transactions', 'total_revenue'
        ]


class TopSellingProductSerializer(serializers.ModelSerializer):
    """Serialize top selling products"""

    class Meta:
        model = TopSellingProduct
        fields = [
            'period_type', 'period_start', 'period_end',
            'brand', 'category', 'location', 'units_sold', 'rank'
        ]


class LowStockAlertSerializer(serializers.ModelSerializer):
    """Serialize stock alerts"""

    class Meta:
        model = LowStockAlert
        fields = [
            'product_id', 'brand', 'category', 'size', 'color', 'location',
            'current_quantity', 'alert_level', 'alert_date', 'is_resolved'
        ]


class CategoryPerformanceSerializer(serializers.ModelSerializer):
    """Serialize category performance"""

    class Meta:
        model = CategoryPerformance
        fields = [
            'period_start', 'period_end', 'category', 'location',
            'total_units_sold', 'total_products_in_category',
            'average_stock_level', 'total_revenue'
        ]


class ShopPerformanceSerializer(serializers.ModelSerializer):
    """Serialize shop/OEM performance"""

    class Meta:
        model = ShopPerformance
        fields = [
            'period_start', 'period_end', 'shop', 'location',
            'total_units_sold', 'unique_products_sold',
            'current_stock_count', 'total_revenue'
        ]


class SyncMetadataSerializer(serializers.ModelSerializer):
    """Serialize sync status"""

    class Meta:
        model = SyncMetadata
        fields = ['sync_type', 'last_sync_time', 'sync_status', 'records_synced']


class InventoryTurnoverRateSerializer(serializers.ModelSerializer):
    """Serialize inventory turnover data"""

    class Meta:
        model = InventoryTurnoverRate
        fields = [
            'period_start', 'period_end', 'category', 'shop', 'location',
            'average_inventory', 'units_sold', 'turnover_rate', 'days_to_sell'
        ]


# ===========================
# ENHANCED SERIALIZERS
# ===========================

class SalesReportMonthlySerializer(serializers.ModelSerializer):
    growth_summary = serializers.SerializerMethodField()

    class Meta:
        model = SalesReportMonthly
        fields = '__all__'

    def get_growth_summary(self, obj):
        return {
            'revenue_growth': f"{obj.revenue_growth_percentage or 0}%",
            'units_growth': f"{obj.units_growth_percentage or 0}%",
        }


class SalesByDayOfWeekSerializer(serializers.ModelSerializer):
    day_name = serializers.CharField(source='get_day_of_week_display', read_only=True)

    class Meta:
        model = SalesByDayOfWeek
        fields = '__all__'


class SalesByHourSerializer(serializers.ModelSerializer):
    hour_label = serializers.SerializerMethodField()

    class Meta:
        model = SalesByHour
        fields = '__all__'

    def get_hour_label(self, obj):
        return f"{obj.hour}:00 - {obj.hour + 1}:00"


class ProductSalesDetailSerializer(serializers.ModelSerializer):
    stock_movement = serializers.SerializerMethodField()

    class Meta:
        model = ProductSalesDetail
        fields = '__all__'

    def get_stock_movement(self, obj):
        movement = obj.stock_at_period_start - obj.stock_at_period_end
        return {
            'units_change': movement,
            'sold_vs_stock': f"{(obj.units_sold / obj.stock_at_period_start * 100):.1f}%" if obj.stock_at_period_start > 0 else "0%"
        }


class SalesTrendSerializer(serializers.ModelSerializer):
    trend_indicator = serializers.SerializerMethodField()

    class Meta:
        model = SalesTrend
        fields = '__all__'

    def get_trend_indicator(self, obj):
        if obj.growth_rate:
            if obj.growth_rate > 5:
                return "Strong Growth"
            elif obj.growth_rate < -5:
                return "Declining"
            else:
                return "Stable"
        return "Stable"


class ComparisonReportSerializer(serializers.ModelSerializer):
    winner_summary = serializers.SerializerMethodField()

    class Meta:
        model = ComparisonReport
        fields = '__all__'

    def get_winner_summary(self, obj):
        return {
            'winner': obj.better_performer,
            'revenue_advantage': f"{abs(obj.revenue_difference):,.2f}",
            'revenue_advantage_percent': f"{abs(obj.revenue_difference_percent):.1f}%",
        }
