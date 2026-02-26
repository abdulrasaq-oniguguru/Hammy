"""
OEM Reporting API Views
Comprehensive REST API for OEM/Inventory/Sales Reporting System

Security Features:
- JWT token authentication required
- Rate limiting per user
- Read-only access (no data modification)
- Audit logging for all requests
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Avg, Count, Q, F, Case, When, DecimalField
from django.utils import timezone
from django.http import HttpResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from datetime import datetime, timedelta
from decimal import Decimal
import csv
import logging
import json
from rest_framework_simplejwt.tokens import RefreshToken

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
)

from .serializers import (
    InventorySnapshotSerializer,
    SalesSummarySerializer,
    TopSellingProductSerializer,
    LowStockAlertSerializer,
    CategoryPerformanceSerializer,
    ShopPerformanceSerializer,
    SyncMetadataSerializer,
    SalesReportMonthlySerializer,
    SalesByDayOfWeekSerializer,
    SalesByHourSerializer,
    ProductSalesDetailSerializer,
    SalesTrendSerializer,
    ComparisonReportSerializer,
)

logger = logging.getLogger(__name__)


# ===========================
# DASHBOARD VIEW
# ===========================

@login_required
def dashboard(request):
    """
    Mobile-First Business Dashboard
    Quick overview of today's business - optimized for on-the-go viewing
    """
    from store.models import Product, Receipt, Sale
    from django.db.models import Sum, Q
    from datetime import date, timedelta, datetime

    try:
        # Get today and week range
        today = date.today()
        week_ago = today - timedelta(days=7)

        # Convert to datetime for filtering
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())
        week_ago_start = datetime.combine(week_ago, datetime.min.time())

        # Basic counts - only products with quantity > 0
        total_products = Product.objects.filter(quantity__gt=0).count()

        # FIXED: Use Sale.sale_date instead of Receipt.date (more accurate)
        # Also filter out NULL dates
        daily_sales_qs = Sale.objects.filter(
            sale_date__isnull=False,
            sale_date__gte=today_start,
            sale_date__lte=today_end
        )
        daily_sales = daily_sales_qs.aggregate(total=Sum('total_price'))['total'] or 0
        daily_count = daily_sales_qs.count()

        # Get weekly sales
        weekly_sales_qs = Sale.objects.filter(
            sale_date__isnull=False,
            sale_date__gte=week_ago_start
        )
        weekly_sales = weekly_sales_qs.aggregate(total=Sum('total_price'))['total'] or 0
        weekly_count = weekly_sales_qs.count()

        # Get all-time total sales (exclude NULL dates)
        all_sales_qs = Sale.objects.filter(sale_date__isnull=False)
        total_sales = all_sales_qs.aggregate(total=Sum('total_price'))['total'] or 0
        total_count = all_sales_qs.count()

        # Get receipts for display (filter out NULL dates)
        daily_receipts = Receipt.objects.filter(
            Q(date__gte=today_start, date__lte=today_end) |
            Q(sales__sale_date__gte=today_start, sales__sale_date__lte=today_end)
        ).distinct()[:10]

        weekly_receipts = Receipt.objects.filter(
            Q(date__gte=week_ago_start) |
            Q(sales__sale_date__gte=week_ago_start)
        ).distinct()[:10]

        # Low stock alerts - critical items (quantity > 0 but < 10)
        low_stock_count = Product.objects.filter(quantity__gt=0, quantity__lt=10).count()
        low_stock_items = Product.objects.filter(quantity__gt=0, quantity__lt=10).order_by('quantity')[:5]

        context = {
            'today': today,
            'daily_sales': daily_sales,
            'daily_count': daily_count,
            'weekly_sales': weekly_sales,
            'weekly_count': weekly_count,
            'total_sales': total_sales,
            'total_count': total_count,
            'daily_receipts': daily_receipts,
            'weekly_receipts': weekly_receipts,
            'total_products': total_products,
            'low_stock_count': low_stock_count,
            'low_stock_items': low_stock_items,
            'currency_symbol': '₦',
        }

        # Use mobile-friendly template
        return render(request, 'oem_reporting/dashboard_mobile.html', context)

    except Exception as e:
        logger.error(f"Dashboard error: {e}", exc_info=True)
        return render(request, 'oem_reporting/dashboard_mobile.html', {
            'error': True,
            'error_message': str(e),
            'currency_symbol': '₦',
        })


@login_required
def reports_menu(request):
    """
    Main reports menu - Hub for all OEM reports
    Access: /oem/reports/
    """
    from datetime import datetime

    # Use main Store database for all stats (individual sales sync)
    from store.models import Product, Receipt
    from django.utils import timezone

    today = timezone.now().date()
    week_ago = today - timedelta(days=7)

    # Product statistics
    total_products = Product.objects.count()  # Number of different product types
    total_inventory_units = Product.objects.aggregate(total=Sum('quantity'))['total'] or 0  # Total pieces in stock

    # Get daily sales (today)
    daily_receipts = Receipt.objects.filter(date__date=today)
    daily_sales = daily_receipts.aggregate(total=Sum('total_with_delivery'))['total'] or 0
    daily_transactions = daily_receipts.count()

    # Calculate daily discounts (line discounts + payment discounts)
    from store.models import Sale, Payment
    from collections import defaultdict

    daily_sales_qs = Sale.objects.filter(
        sale_date__isnull=False,
        sale_date__date=today
    ).select_related('payment', 'receipt')

    daily_grouped = defaultdict(list)
    for sale in daily_sales_qs:
        if sale.receipt:
            daily_grouped[sale.receipt].append(sale)

    daily_payment_discounts = 0
    daily_line_discounts = 0
    for receipt, sale_list in daily_grouped.items():
        # Payment discount (once per receipt)
        first_sale = sale_list[0] if sale_list else None
        if first_sale and first_sale.payment and first_sale.payment.discount_amount:
            daily_payment_discounts += first_sale.payment.discount_amount
        # Line discounts (sum all items)
        for sale in sale_list:
            if sale.discount_amount:
                daily_line_discounts += sale.discount_amount

    daily_discounts = daily_payment_discounts + daily_line_discounts

    # Get weekly sales (current week: Sunday to today)
    # Calculate the most recent Sunday as week start
    days_since_sunday = (today.weekday() + 1) % 7  # Monday=0, Sunday=6 -> convert to days since Sunday
    week_start = today - timedelta(days=days_since_sunday)
    week_end = today
    weekly_receipts = Receipt.objects.filter(date__date__gte=week_start, date__date__lte=week_end)
    weekly_sales = weekly_receipts.aggregate(total=Sum('total_with_delivery'))['total'] or 0
    weekly_date_range = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}"

    # Get all-time stats
    all_receipts = Receipt.objects.all()
    total_revenue = all_receipts.aggregate(total=Sum('total_with_delivery'))['total'] or 0
    total_transactions = all_receipts.count()

    # Get last sync time (from file if available)
    last_sync_time = None
    try:
        sync_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.last_sync_time.txt')
        if os.path.exists(sync_file):
            with open(sync_file, 'r') as f:
                from datetime import datetime
                last_sync_time = datetime.fromisoformat(f.read().strip())
    except:
        pass

    context = {
        'current_date': datetime.now(),
        'current_time': datetime.now(),
        'total_products': total_products,
        'total_inventory_units': total_inventory_units,
        'total_revenue': total_revenue,
        'total_transactions': total_transactions,
        'daily_sales': daily_sales,
        'daily_transactions': daily_transactions,
        'daily_discounts': daily_discounts,
        'weekly_sales': weekly_sales,
        'weekly_date_range': weekly_date_range,
        'last_sync_time': last_sync_time,
    }

    return render(request, 'oem_reporting/reports_menu.html', context)


@login_required
def bi_dashboard(request):
    """
    Business Intelligence Dashboard - Comprehensive analytics
    Similar to offline store dashboard but for OEM data
    Access: /oem/reports/bi-dashboard/
    """
    from datetime import datetime
    from django.db.models.functions import TruncMonth

    # Get filter type
    filter_type = request.GET.get('filter', 'this_month')
    end_date = datetime.now().date()

    # Calculate date range based on filter
    if filter_type == 'today':
        start_date = end_date
    elif filter_type == 'this_week':
        start_date = end_date - timedelta(days=7)
    elif filter_type == 'this_month':
        start_date = end_date - timedelta(days=30)
    elif filter_type == 'this_year':
        start_date = end_date - timedelta(days=365)
    elif filter_type == 'custom':
        start_date = request.GET.get('start_date', end_date - timedelta(days=30))
        end_date = request.GET.get('end_date', end_date)
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    else:
        start_date = end_date - timedelta(days=30)

    # Check if OEM sync DB is accessible
    try:
        test_connection = InventorySnapshot.objects.using('oem_sync_db').first()
        use_oem_db = True
    except Exception as e:
        logger.warning(f"OEM sync DB not accessible, using local store data: {e}")
        use_oem_db = False

    if not use_oem_db:
        # Use local store database for development
        from store.models import Product, Sale, Receipt

        total_products = Product.objects.count()
        low_stock_count = Product.objects.filter(quantity__lt=10).count()

        # Get sales from local store
        receipts = Receipt.objects.filter(
            date__gte=start_date,
            date__lte=end_date
        )

        total_revenue = receipts.aggregate(total=Sum('total_with_delivery'))['total'] or 0
        total_sales_count = receipts.count()
        avg_order_value = total_revenue / total_sales_count if total_sales_count > 0 else 0

        # Get product sales for tables
        from django.db.models.functions import TruncMonth

        sales = Sale.objects.filter(
            receipt__date__gte=start_date,
            receipt__date__lte=end_date
        )

        top_products = sales.values('product__brand', 'product__category').annotate(
            brand=F('product__brand'),
            category=F('product__category'),
            total_units_sold=Sum('quantity'),
            total_revenue=Sum('total_price')
        ).order_by('-total_revenue')[:10]

        low_stock_items = Product.objects.filter(quantity__lt=10).order_by('quantity')[:10]

        context = {
            'filter_type': filter_type,
            'start_date': start_date,
            'end_date': end_date,
            'total_revenue': total_revenue,
            'total_sales_count': total_sales_count,
            'avg_order_value': avg_order_value,
            'low_stock_count': low_stock_count,
            'monthly_labels': json.dumps([]),
            'monthly_revenue': json.dumps([]),
            'category_labels': json.dumps([]),
            'category_data': json.dumps([]),
            'top_products': list(top_products),
            'recent_sales': [],
            'location_performance': [],
            'category_stats': [],
            'low_stock_alerts': list(low_stock_items),
            'using_local_data': True,
            'db_message': 'Using local store data (Online OEM database not accessible)'
        }
        return render(request, 'oem_reporting/bi_dashboard.html', context)

    # Get sales data for the period
    sales_data = SalesSummaryDaily.objects.using('oem_sync_db').filter(
        summary_date__gte=start_date,
        summary_date__lte=end_date
    )

    # Calculate summary metrics
    total_revenue = sales_data.aggregate(total=Sum('total_revenue'))['total'] or 0
    total_sales_count = sales_data.aggregate(total=Sum('total_transactions'))['total'] or 0
    avg_order_value = total_revenue / total_sales_count if total_sales_count > 0 else 0

    # Low stock count
    low_stock_count = InventorySnapshot.objects.using('oem_sync_db').filter(
        is_low_stock=True
    ).count()

    # Monthly data for revenue chart
    try:
        monthly_data = sales_data.annotate(
            month=TruncMonth('summary_date')
        ).values('month').annotate(
            revenue=Sum('total_revenue')
        ).order_by('month')

        monthly_labels = [item['month'].strftime('%b %Y') for item in monthly_data] if monthly_data else []
        monthly_revenue = [float(item['revenue'] or 0) for item in monthly_data] if monthly_data else []
    except Exception as e:
        logger.error(f"Error getting monthly data: {e}")
        monthly_labels = []
        monthly_revenue = []

    # Category data for pie chart
    try:
        category_data = sales_data.values('category').annotate(
            total=Sum('total_revenue')
        ).order_by('-total')[:7]

        category_labels = [item['category'] or 'Uncategorized' for item in category_data] if category_data else []
        category_values = [float(item['total'] or 0) for item in category_data] if category_data else []
    except Exception as e:
        logger.error(f"Error getting category data: {e}")
        category_labels = []
        category_values = []

    # Top selling products - get from aggregated sales data
    try:
        top_products = sales_data.values('brand', 'category').annotate(
            total_units_sold=Sum('total_units_sold'),
            total_revenue=Sum('total_revenue')
        ).order_by('-total_revenue')[:10]
    except Exception as e:
        logger.error(f"Error getting top products: {e}")
        top_products = []

    # Recent sales
    try:
        recent_sales = sales_data.order_by('-summary_date')[:10]
    except Exception as e:
        logger.error(f"Error getting recent sales: {e}")
        recent_sales = []

    # Location performance
    try:
        location_performance = sales_data.values('location').annotate(
            total_units=Sum('total_units_sold'),
            total_revenue=Sum('total_revenue'),
            transaction_count=Sum('total_transactions')
        ).annotate(
            avg_per_transaction=Case(
                When(transaction_count__gt=0, then=F('total_revenue') / F('transaction_count')),
                default=0,
                output_field=DecimalField()
            )
        ).order_by('-total_revenue')
    except Exception as e:
        logger.error(f"Error getting location performance: {e}")
        location_performance = []

    # Category statistics from inventory
    try:
        category_stats = InventorySnapshot.objects.using('oem_sync_db').values('category').annotate(
            product_count=Count('id'),
            total_quantity=Sum('quantity_available'),
            total_value=Sum(F('quantity_available') * F('unit_price'))
        ).order_by('-total_quantity')[:10]
    except Exception as e:
        logger.error(f"Error getting category stats: {e}")
        category_stats = []

    # Low stock alerts
    try:
        low_stock_alerts = InventorySnapshot.objects.using('oem_sync_db').filter(
            is_low_stock=True
        ).order_by('quantity_available')[:10]
    except Exception as e:
        logger.error(f"Error getting low stock alerts: {e}")
        low_stock_alerts = []

    context = {
        'filter_type': filter_type,
        'start_date': start_date,
        'end_date': end_date,
        'total_revenue': total_revenue,
        'total_sales_count': total_sales_count,
        'avg_order_value': avg_order_value,
        'low_stock_count': low_stock_count,
        'monthly_labels': json.dumps(monthly_labels),
        'monthly_revenue': json.dumps(monthly_revenue),
        'category_labels': json.dumps(category_labels),
        'category_data': json.dumps(category_values),
        'top_products': list(top_products),
        'recent_sales': list(recent_sales),
        'location_performance': list(location_performance),
        'category_stats': list(category_stats),
        'low_stock_alerts': list(low_stock_alerts),
    }

    return render(request, 'oem_reporting/bi_dashboard.html', context)


@login_required
def sales_report(request):
    """
    Comprehensive Sales Report - Replicates local sales report structure
    Shows grouped sales by receipt with full details
    """
    from datetime import datetime
    from collections import defaultdict
    from store.models import Sale, Receipt, PaymentMethod

    try:
        # Get filters
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        payment_method_filter = request.GET.get('payment_method')
        shop_type = request.GET.get('shop_type')
        export_format = request.GET.get('export')

        # Base queryset with select/prefetch - same as local
        sales = Sale.objects.select_related(
            'product', 'receipt', 'payment', 'delivery', 'customer'
        ).prefetch_related(
            'payment__payment_methods'
        ).order_by('-sale_date')

        # Apply filters
        start_date_obj = None
        end_date_obj = None
        if start_date and end_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1) - timedelta(seconds=1)
                sales = sales.filter(sale_date__range=[start_date_obj, end_date_obj])
            except ValueError:
                start_date_obj = None
                end_date_obj = None

        if shop_type:
            sales = sales.filter(product__shop=shop_type)

        if payment_method_filter:
            sales = sales.filter(payment__payment_methods__payment_method=payment_method_filter).distinct()

        # Group sales by receipt - EXACTLY like local report
        grouped_sales = defaultdict(list)
        for sale in sales:
            grouped_sales[sale.receipt].append(sale)

        # Convert to list of tuples for template iteration
        grouped_sales = sorted(
            grouped_sales.items(),
            key=lambda x: x[1][0].sale_date if x[1] else timezone.now(),
            reverse=True
        )

        # Calculate total sales using receipt.total_with_delivery (NET revenue after discounts)
        unique_receipts = Receipt.objects.filter(sales__in=sales).distinct()
        total_sales = sum(receipt.total_with_delivery for receipt in unique_receipts if receipt.total_with_delivery)

        # Calculate discount and delivery totals - same as local sales_report
        total_payment_discounts = 0
        total_line_discounts = 0
        total_delivery_fees = 0

        for receipt, sale_list in grouped_sales:
            # Payment discounts (once per receipt)
            first_sale = sale_list[0] if sale_list else None
            if first_sale and first_sale.payment and first_sale.payment.discount_amount:
                total_payment_discounts += first_sale.payment.discount_amount

            # Line discounts (sum all items)
            for sale in sale_list:
                if sale.discount_amount:
                    total_line_discounts += sale.discount_amount

            # Delivery fees
            if receipt and receipt.delivery_cost:
                total_delivery_fees += receipt.delivery_cost

        total_all_discounts = total_payment_discounts + total_line_discounts

        payment_methods = PaymentMethod.PAYMENT_METHODS
        # Define shop types inline to avoid import errors
        shop_types = [('STORE', 'Store (Shop Floor)'), ('WAREHOUSE', 'Warehouse')]

        # Get yesterday's date for daily report form
        yesterday = datetime.now().date() - timedelta(days=1)

        context = {
            'grouped_sales': grouped_sales,
            'start_date': start_date,
            'end_date': end_date,
            'total_sales': total_sales,
            'total_all_discounts': total_all_discounts,
            'total_delivery_fees': total_delivery_fees,
            'payment_methods': payment_methods,
            'selected_payment_method': payment_method_filter,
            'shop_types': shop_types,
            'selected_shop_type': shop_type,
            'yesterday': yesterday,
            'currency_symbol': '₦',
        }

        return render(request, 'oem_reporting/sales_report.html', context)

    except Exception as e:
        logger.error(f"Error in sales_report: {e}", exc_info=True)
        # Return error page with context
        context = {
            'error': True,
            'error_message': str(e),
            'grouped_sales': [],
            'total_sales': 0,
            'payment_methods': [],
            'shop_types': [('STORE', 'Store (Shop Floor)'), ('WAREHOUSE', 'Warehouse')],
            'currency_symbol': '₦',
        }
        return render(request, 'oem_reporting/sales_report.html', context)


@login_required
def inventory_report(request):
    """
    Comprehensive Inventory Report - Replicates local inventory report
    Shows product details with cost price, selling price, markup, and stock status
    """
    from store.models import Product
    from store.choices import ProductChoices
    from decimal import Decimal
    from django.db.models import Q

    try:
        # Get filters
        category = request.GET.get('category')
        low_stock = request.GET.get('low_stock')
        search_query = request.GET.get('search', '').strip()

        # Get products with calculated values - EXACTLY like local report
        # IMPORTANT: Only show products with quantity > 0
        products = Product.objects.filter(quantity__gt=0).annotate(
            total_value=F('quantity') * F('price')
        )

        # Apply search filter
        if search_query:
            products = products.filter(
                Q(brand__icontains=search_query) |
                Q(barcode_number__icontains=search_query) |
                Q(category__icontains=search_query) |
                Q(size__icontains=search_query) |
                Q(color__icontains=search_query) |
                Q(design__icontains=search_query)
            )

        # Apply category filter
        if category:
            products = products.filter(category=category)

        # Apply low stock filter
        if low_stock:
            products = products.filter(quantity__lt=10)

        # Calculate summary stats
        total_value = products.aggregate(total=Sum('total_value'))['total'] or 0
        low_stock_count = products.filter(quantity__lt=10).count()

        # Calculate average markup
        products_with_markup = products.exclude(markup=0)
        if products_with_markup.count() > 0:
            avg_markup = products_with_markup.aggregate(avg=Avg('markup'))['avg'] or 0
        else:
            avg_markup = 0

        # Get all categories for filter dropdown
        categories = ProductChoices.CATEGORY_CHOICES

        context = {
            'products': products,
            'total_value': total_value,
            'low_stock_count': low_stock_count,
            'avg_markup': avg_markup,
            'categories': categories,
            'selected_category': category,
            'show_low_stock': low_stock,
            'search_query': search_query,
            'currency_symbol': '₦',
        }

        return render(request, 'oem_reporting/inventory_report.html', context)

    except Exception as e:
        logger.error(f"Inventory report error: {e}", exc_info=True)
        context = {
            'error': True,
            'error_message': str(e),
            'products': [],
            'total_value': 0,
            'categories': [],
            'currency_symbol': '₦',
        }
        return render(request, 'oem_reporting/inventory_report.html', context)


@login_required
def financial_report(request):
    """
    Financial Report - Replicates local financial report structure
    Payment method breakdown, discount analysis, and financial trends
    """
    from datetime import datetime
    from store.models import Sale, Payment, Receipt
    from django.db.models.functions import TruncMonth

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    report_type = request.GET.get('report_type', 'revenue')

    # Use EXACT same query as sales_report
    sales = Sale.objects.select_related(
        'product', 'receipt', 'payment', 'delivery', 'customer'
    ).prefetch_related(
        'payment__payment_methods'
    ).order_by('-sale_date')

    # Apply filters - EXACT same as sales_report
    start_date_obj = None
    end_date_obj = None
    if start_date and end_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            # CRITICAL: Use same date range calculation as sales_report
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1) - timedelta(seconds=1)
            sales = sales.filter(sale_date__range=[start_date_obj, end_date_obj])
        except ValueError:
            start_date_obj = None
            end_date_obj = None

    # Filter out sales without products or receipts to avoid errors
    sales = sales.filter(product__isnull=False, receipt__isnull=False)

    # Get unique receipts - EXACT same as sales_report
    unique_receipts = Receipt.objects.filter(sales__in=sales).distinct()

    # Get unique payments for payment method breakdown
    unique_payments = Payment.objects.filter(sale__in=sales).distinct()

    # 1. Revenue Analysis - Use EXACT same calculation as sales_report
    # NET Revenue = Total money received (after discounts, including delivery)
    # CRITICAL: Use same calculation as sales_report
    net_revenue = sum(receipt.total_with_delivery for receipt in unique_receipts if receipt.total_with_delivery)

    # Gross revenue = price before any discounts (for comparison)
    gross_revenue = sum(sale.product.selling_price * sale.quantity for sale in sales)

    # 2. Discount Analysis - Group by receipt to avoid double-counting payment discounts
    from collections import defaultdict
    grouped_sales = defaultdict(list)
    for sale in sales:
        grouped_sales[sale.receipt].append(sale)

    total_payment_discounts = 0
    total_item_discounts = 0
    for receipt, sale_list in grouped_sales.items():
        # Payment discount (once per receipt)
        first_sale = sale_list[0] if sale_list else None
        if first_sale and first_sale.payment and first_sale.payment.discount_amount:
            total_payment_discounts += first_sale.payment.discount_amount

        # Line discounts (sum all items)
        for sale in sale_list:
            if sale.discount_amount:
                total_item_discounts += sale.discount_amount

    total_discounts = total_item_discounts + total_payment_discounts

    # 3. Delivery Fee Analysis - Use receipts
    total_delivery_fees = sum(receipt.delivery_cost or 0 for receipt in unique_receipts)

    # 4. Cost and Profit Analysis
    total_cost = sum(sale.product.price * sale.quantity for sale in sales)
    # Profit = NET Revenue - Costs
    total_profit = net_revenue - total_cost
    profit_margin = (total_profit / net_revenue * 100) if net_revenue > 0 else 0

    # 5. DETAILED PAYMENT METHOD BREAKDOWN
    payment_method_breakdown = {}

    for payment in unique_payments:
        for pm in payment.payment_methods.filter(status='completed'):
            method_name = pm.get_payment_method_display()

            if method_name not in payment_method_breakdown:
                payment_method_breakdown[method_name] = {
                    'total_amount': 0,
                    'transaction_count': 0,
                    'avg_transaction': 0
                }

            payment_method_breakdown[method_name]['total_amount'] += float(pm.amount)
            payment_method_breakdown[method_name]['transaction_count'] += 1

    # Calculate averages
    for method, data in payment_method_breakdown.items():
        if data['transaction_count'] > 0:
            data['avg_transaction'] = data['total_amount'] / data['transaction_count']

    # Sort by total amount
    payment_method_breakdown = dict(sorted(
        payment_method_breakdown.items(),
        key=lambda x: x[1]['total_amount'],
        reverse=True
    ))

    # 6. Payment Status Analysis
    payment_status_breakdown = {
        'completed': unique_payments.filter(payment_status='completed').count(),
        'partial': unique_payments.filter(payment_status='partial').count(),
        'pending': unique_payments.filter(payment_status='pending').count(),
        'failed': unique_payments.filter(payment_status='failed').count(),
    }

    completed_amount = sum(p.total_amount for p in unique_payments.filter(payment_status='completed'))
    partial_amount = sum(p.total_paid for p in unique_payments.filter(payment_status='partial'))
    pending_amount = sum(p.total_amount for p in unique_payments.filter(payment_status='pending'))

    # 7. Monthly Revenue Trend
    monthly_data = []
    monthly_raw = (
        Payment.objects
        .filter(sale__in=sales)
        .annotate(month=TruncMonth('sale__sale_date'))
        .values('month')
        .annotate(
            revenue=Sum('total_amount'),
            discount_amount=Sum('discount_amount'),
            transaction_count=Count('id', distinct=True)
        )
        .order_by('month')
    )

    for month in monthly_raw:
        month_receipts = unique_receipts.filter(date__month=month['month'].month, date__year=month['month'].year)
        delivery_fees = sum(r.delivery_cost or 0 for r in month_receipts)

        monthly_data.append({
            'month': month['month'],
            'revenue': month['revenue'],
            'discount_amount': month['discount_amount'] or 0,
            'delivery_fees': delivery_fees,
            'transaction_count': month['transaction_count'],
            'net_revenue': (month['revenue'] or 0) - delivery_fees
        })

    # 8. Discount Analysis by Type
    discount_breakdown = {
        'item_level_discounts': total_item_discounts,
        'payment_level_discounts': total_payment_discounts,
        'total_discounts': total_discounts,
        'discount_rate': (total_discounts / gross_revenue * 100) if gross_revenue > 0 else 0
    }

    context = {
        # Revenue Metrics
        'gross_revenue': gross_revenue,
        'total_revenue': net_revenue,  # Use NET revenue for total (after discounts + delivery)
        'net_revenue': net_revenue,
        'total_cost': total_cost,
        'total_profit': total_profit,
        'profit_margin': profit_margin,

        # Discount & Fees
        'discount_breakdown': discount_breakdown,
        'total_delivery_fees': total_delivery_fees,

        # Payment Analysis
        'payment_method_breakdown': payment_method_breakdown,
        'payment_status_breakdown': payment_status_breakdown,
        'completed_amount': completed_amount,
        'partial_amount': partial_amount,
        'pending_amount': pending_amount,

        # Trends
        'monthly_data': monthly_data,

        # Filters
        'start_date': start_date,
        'end_date': end_date,
        'report_type': report_type,

        # Summary Stats
        'total_transactions': unique_payments.count(),
        'avg_transaction_value': net_revenue / unique_payments.count() if unique_payments.count() > 0 else 0,
        'currency_symbol': '₦',
    }

    return render(request, 'oem_reporting/financial_report.html', context)


@login_required
def stock_alerts(request):
    """
    Mobile-Friendly Stock Alerts
    Critical and low stock items requiring attention
    """
    from store.models import Product

    try:
        # Get filters
        location = request.GET.get('location')
        category = request.GET.get('category')
        severity = request.GET.get('severity')  # 'critical', 'low', 'all'

        # Use local store data - simple and reliable
        low_stock = Product.objects.filter(quantity__lt=10)

        if location:
            low_stock = low_stock.filter(location=location)
        if category:
            low_stock = low_stock.filter(category=category)
        if severity == 'critical':
            low_stock = low_stock.filter(quantity__lt=5)

        critical_count = low_stock.filter(quantity__lt=5).count()
        low_count = low_stock.filter(quantity__gte=5, quantity__lt=10).count()

        # Get categories and locations for filters
        categories = list(Product.objects.values_list('category', flat=True).distinct().order_by('category'))
        locations = [('ABUJA', 'Abuja'), ('LAGOS', 'Lagos')]

        context = {
            'alerts': low_stock.order_by('quantity')[:50],  # Limit for mobile
            'critical_count': critical_count,
            'low_count': low_count,
            'total_alerts': low_stock.count(),
            'categories': categories,
            'locations': locations,
            'selected_location': location,
            'selected_category': category,
            'selected_severity': severity,
            'currency_symbol': '₦',
        }
        return render(request, 'oem_reporting/stock_alerts.html', context)

    except Exception as e:
        logger.error(f"Stock alerts error: {e}", exc_info=True)
        context = {
            'error': True,
            'error_message': str(e),
            'alerts': [],
            'critical_count': 0,
            'low_count': 0,
            'total_alerts': 0,
            'currency_symbol': '₦',
        }
        return render(request, 'oem_reporting/stock_alerts.html', context)


# Removed old OEM sync DB code and performance_analytics


@login_required
def performance_analytics(request):
    """
    Performance Analytics Report
    Category performance, shop performance, and comparative analysis
    """
    from datetime import datetime

    # Get filters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    metric = request.GET.get('metric', 'revenue')  # 'revenue', 'quantity', 'profit'

    # Default to last 30 days
    if not end_date:
        end_date = datetime.now().date()
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

    if not start_date:
        start_date = end_date - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()

    # Check database availability
    try:
        test_connection = CategoryPerformance.objects.using('oem_sync_db').first()
        use_oem_db = True
    except Exception as e:
        logger.warning(f"OEM sync DB not accessible: {e}")
        use_oem_db = False

    if not use_oem_db:
        # Use local store data
        from store.models import Sale

        sales = Sale.objects.filter(
            sale_date__gte=start_date,
            sale_date__lte=end_date
        )

        # Category performance
        category_perf = sales.values('product__category').annotate(
            category=F('product__category'),
            total_revenue=Sum('total_price'),
            total_quantity=Sum('quantity'),
            transaction_count=Count('id')
        ).order_by('-total_revenue')[:10]

        # Location performance
        location_perf = sales.values('product__location').annotate(
            location=F('product__location'),
            total_revenue=Sum('total_price'),
            total_quantity=Sum('quantity')
        ).order_by('-total_revenue')

        context = {
            'category_performance': category_perf,
            'location_performance': location_perf,
            'start_date': start_date,
            'end_date': end_date,
            'using_local_data': True,
        }
        return render(request, 'oem_reporting/performance_analytics.html', context)

    # Get performance data from OEM sync DB
    # Category Performance
    category_performance = CategoryPerformance.objects.using('oem_sync_db').filter(
        last_updated__gte=start_date
    ).order_by('-total_revenue')[:15]

    # Shop Performance
    shop_performance = ShopPerformance.objects.using('oem_sync_db').filter(
        last_updated__gte=start_date
    ).order_by('-total_revenue')[:10]

    # Top selling products
    top_products = TopSellingProduct.objects.using('oem_sync_db').filter(
        last_updated__gte=start_date
    ).order_by('-total_revenue')[:10]

    # Sales trends
    try:
        trends = SalesSummaryDaily.objects.using('oem_sync_db').filter(
            summary_date__gte=start_date,
            summary_date__lte=end_date
        ).values('summary_date').annotate(
            revenue=Sum('total_revenue'),
            transactions=Sum('total_transactions'),
            units=Sum('total_units_sold')
        ).order_by('summary_date')
    except Exception as e:
        logger.error(f"Error getting trends: {e}")
        trends = []

    # Performance comparison (current period vs previous period)
    period_days = (end_date - start_date).days
    prev_start = start_date - timedelta(days=period_days)
    prev_end = start_date - timedelta(days=1)

    current_sales = SalesSummaryDaily.objects.using('oem_sync_db').filter(
        summary_date__gte=start_date,
        summary_date__lte=end_date
    ).aggregate(
        revenue=Sum('total_revenue'),
        transactions=Sum('total_transactions')
    )

    prev_sales = SalesSummaryDaily.objects.using('oem_sync_db').filter(
        summary_date__gte=prev_start,
        summary_date__lte=prev_end
    ).aggregate(
        revenue=Sum('total_revenue'),
        transactions=Sum('total_transactions')
    )

    # Calculate growth
    current_revenue = current_sales['revenue'] or 0
    prev_revenue = prev_sales['revenue'] or 0
    revenue_growth = ((current_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else 0

    context = {
        'category_performance': category_performance,
        'shop_performance': shop_performance,
        'top_products': top_products,
        'trends': list(trends),
        'current_revenue': current_revenue,
        'prev_revenue': prev_revenue,
        'revenue_growth': revenue_growth,
        'start_date': start_date,
        'end_date': end_date,
        'metric_filter': metric,
        'using_local_data': False,
    }

    return render(request, 'oem_reporting/performance_analytics.html', context)


# ===========================
# CORE API VIEWS
# ===========================

@api_view(['GET'])
def api_root(request):
    """
    API Root - Lists available endpoints
    """
    return Response({
        'message': 'OEM/Inventory Reporting API',
        'version': '1.0.0',
        'endpoints': {
            'inventory': {
                'summary': '/api/oem/inventory/summary/',
                'by_category': '/api/oem/inventory/by-category/',
                'by_location': '/api/oem/inventory/by-location/',
                'low_stock': '/api/oem/inventory/low-stock/',
                'search': '/api/oem/inventory/search/?q=brand_name',
            },
            'sales': {
                'summary': '/api/oem/sales/summary/',
                'daily': '/api/oem/sales/daily/',
                'trends': '/api/oem/sales/trends/',
                'top_products': '/api/oem/sales/top-products/',
            },
            'reports': {
                'monthly': '/api/oem/reports/sales/monthly/',
                'by_day_of_week': '/api/oem/reports/sales/by-day-of-week/',
                'by_hour': '/api/oem/reports/sales/by-hour/',
                'product_details': '/api/oem/reports/sales/product-details/',
                'trends': '/api/oem/reports/sales/trends/',
                'comparisons': '/api/oem/reports/comparisons/',
            },
            'performance': {
                'categories': '/api/oem/performance/categories/',
                'shops': '/api/oem/performance/shops/',
            },
            'alerts': {
                'low_stock': '/api/oem/alerts/low-stock/',
                'critical': '/api/oem/alerts/critical/',
            },
            'status': '/api/oem/status/',
            'search': '/api/oem/search/',
        }
    })


@api_view(['GET'])
def sync_status(request):
    """
    Get current sync status and last sync time
    GET /api/oem/status/
    """
    try:
        metadata = SyncMetadata.objects.using('oem_sync_db').filter(
            sync_type='full_sync'
        ).first()

        if metadata:
            return Response({
                'last_sync': metadata.last_sync_time,
                'status': metadata.sync_status,
                'records_synced': metadata.records_synced,
                'healthy': metadata.sync_status == 'success',
                'error': metadata.error_message if metadata.sync_status == 'failed' else None
            })
        else:
            return Response({
                'message': 'No sync has been performed yet',
                'healthy': False
            }, status=status.HTTP_404_NOT_FOUND)

    except Exception as e:
        logger.error(f"Error getting sync status: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================
# INVENTORY ENDPOINTS
# ===========================

@api_view(['GET'])
def inventory_summary(request):
    """
    Get overall inventory summary
    GET /api/oem/inventory/summary/
    Query params:
        - location: Filter by location (ABUJA/LAGOS)
    """
    try:
        queryset = InventorySnapshot.objects.using('oem_sync_db').all()

        # Filter by location if provided
        location = request.query_params.get('location')
        if location:
            queryset = queryset.filter(location=location.upper())

        # Calculate totals
        total_products = queryset.count()
        total_stock = queryset.aggregate(total=Sum('quantity_available'))['total'] or 0
        low_stock_count = queryset.filter(is_low_stock=True).count()
        out_of_stock_count = queryset.filter(is_out_of_stock=True).count()

        # By category
        by_category = queryset.values('category').annotate(
            total_quantity=Sum('quantity_available'),
            product_count=Count('id')
        ).order_by('-total_quantity')[:10]

        # By location
        by_location = queryset.values('location').annotate(
            total_quantity=Sum('quantity_available'),
            product_count=Count('id')
        )

        return Response({
            'summary': {
                'total_products': total_products,
                'total_stock_units': total_stock,
                'low_stock_alerts': low_stock_count,
                'out_of_stock': out_of_stock_count,
            },
            'by_category': list(by_category),
            'by_location': list(by_location),
            'timestamp': timezone.now()
        })

    except Exception as e:
        logger.error(f"Error in inventory_summary: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def inventory_by_category(request):
    """
    Get inventory grouped by category
    GET /api/oem/inventory/by-category/
    Query params:
        - location: Filter by location
    """
    try:
        queryset = InventorySnapshot.objects.using('oem_sync_db').all()

        location = request.query_params.get('location')
        if location:
            queryset = queryset.filter(location=location.upper())

        categories = queryset.values('category', 'location').annotate(
            total_quantity=Sum('quantity_available'),
            product_count=Count('id'),
            low_stock_count=Count('id', filter=Q(is_low_stock=True)),
            out_of_stock_count=Count('id', filter=Q(is_out_of_stock=True))
        ).order_by('category')

        return Response({
            'categories': list(categories),
            'total_categories': len(categories)
        })

    except Exception as e:
        logger.error(f"Error in inventory_by_category: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================
# ALERT ENDPOINTS
# ===========================

@api_view(['GET'])
def low_stock_alerts(request):
    """
    Get low stock alerts
    GET /api/oem/alerts/low-stock/
    Query params:
        - location: Filter by location
        - level: Filter by alert level (low/critical/out)
        - resolved: true/false
    """
    try:
        queryset = LowStockAlert.objects.using('oem_sync_db').all()

        # Filters
        location = request.query_params.get('location')
        if location:
            queryset = queryset.filter(location=location.upper())

        alert_level = request.query_params.get('level')
        if alert_level:
            queryset = queryset.filter(alert_level=alert_level)

        resolved = request.query_params.get('resolved')
        if resolved is not None:
            is_resolved = resolved.lower() == 'true'
            queryset = queryset.filter(is_resolved=is_resolved)

        # Order by most critical first
        queryset = queryset.order_by('current_quantity', '-alert_date')

        serializer = LowStockAlertSerializer(queryset, many=True)

        return Response({
            'alerts': serializer.data,
            'total_alerts': len(serializer.data)
        })

    except Exception as e:
        logger.error(f"Error in low_stock_alerts: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================
# SALES ENDPOINTS
# ===========================

@api_view(['GET'])
def sales_summary(request):
    """
    Get sales summary
    GET /api/oem/sales/summary/
    Query params:
        - days: Number of days to look back (default: 30)
        - location: Filter by location
    """
    try:
        days = int(request.query_params.get('days', 30))
        start_date = (timezone.now() - timedelta(days=days)).date()

        queryset = SalesSummaryDaily.objects.using('oem_sync_db').filter(
            summary_date__gte=start_date
        )

        location = request.query_params.get('location')
        if location:
            queryset = queryset.filter(location=location.upper())

        # Overall totals
        totals = queryset.aggregate(
            total_units=Sum('total_units_sold'),
            total_transactions=Sum('total_transactions'),
            total_revenue=Sum('total_revenue')
        )

        # By category
        by_category = queryset.values('category').annotate(
            total_units=Sum('total_units_sold'),
            total_revenue=Sum('total_revenue')
        ).order_by('-total_units')[:10]

        # By location
        by_location = queryset.values('location').annotate(
            total_units=Sum('total_units_sold'),
            total_revenue=Sum('total_revenue')
        )

        # Daily trend
        daily_trend = queryset.values('summary_date').annotate(
            total_units=Sum('total_units_sold'),
            total_revenue=Sum('total_revenue')
        ).order_by('summary_date')

        return Response({
            'period': {
                'start_date': start_date,
                'end_date': timezone.now().date(),
                'days': days
            },
            'totals': totals,
            'by_category': list(by_category),
            'by_location': list(by_location),
            'daily_trend': list(daily_trend)
        })

    except Exception as e:
        logger.error(f"Error in sales_summary: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def top_selling_products(request):
    """
    Get top selling products
    GET /api/oem/sales/top-products/
    Query params:
        - period: daily/weekly/monthly (default: weekly)
        - location: Filter by location
        - limit: Number of products (default: 20)
    """
    try:
        period = request.query_params.get('period', 'weekly')
        limit = int(request.query_params.get('limit', 20))

        queryset = TopSellingProduct.objects.using('oem_sync_db').filter(
            period_type=period
        )

        location = request.query_params.get('location')
        if location:
            queryset = queryset.filter(location=location.upper())

        # Get latest period
        latest_period = queryset.order_by('-period_end').first()

        if latest_period:
            queryset = queryset.filter(
                period_start=latest_period.period_start,
                period_end=latest_period.period_end
            ).order_by('rank')[:limit]

            serializer = TopSellingProductSerializer(queryset, many=True)

            return Response({
                'period': {
                    'type': period,
                    'start': latest_period.period_start,
                    'end': latest_period.period_end
                },
                'products': serializer.data
            })
        else:
            return Response({
                'message': 'No data available for this period',
                'products': []
            })

    except Exception as e:
        logger.error(f"Error in top_selling_products: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================
# PERFORMANCE ENDPOINTS
# ===========================

@api_view(['GET'])
def category_performance(request):
    """
    Get category performance metrics
    GET /api/oem/performance/categories/
    Query params:
        - location: Filter by location
    """
    try:
        queryset = CategoryPerformance.objects.using('oem_sync_db').all()

        location = request.query_params.get('location')
        if location:
            queryset = queryset.filter(location=location.upper())

        # Get latest period
        latest = queryset.order_by('-period_end').first()

        if latest:
            queryset = queryset.filter(
                period_start=latest.period_start,
                period_end=latest.period_end
            ).order_by('-total_units_sold')

            serializer = CategoryPerformanceSerializer(queryset, many=True)

            return Response({
                'period': {
                    'start': latest.period_start,
                    'end': latest.period_end
                },
                'performance': serializer.data
            })
        else:
            return Response({
                'message': 'No performance data available',
                'performance': []
            })

    except Exception as e:
        logger.error(f"Error in category_performance: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def shop_performance(request):
    """
    Get shop/OEM performance metrics
    GET /api/oem/performance/shops/
    Query params:
        - location: Filter by location
    """
    try:
        queryset = ShopPerformance.objects.using('oem_sync_db').all()

        location = request.query_params.get('location')
        if location:
            queryset = queryset.filter(location=location.upper())

        # Get latest period
        latest = queryset.order_by('-period_end').first()

        if latest:
            queryset = queryset.filter(
                period_start=latest.period_start,
                period_end=latest.period_end
            ).order_by('-total_units_sold')

            serializer = ShopPerformanceSerializer(queryset, many=True)

            return Response({
                'period': {
                    'start': latest.period_start,
                    'end': latest.period_end
                },
                'performance': serializer.data
            })
        else:
            return Response({
                'message': 'No performance data available',
                'performance': []
            })

    except Exception as e:
        logger.error(f"Error in shop_performance: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================
# ENHANCED SALES REPORT ENDPOINTS
# ===========================

@api_view(['GET'])
def sales_report_monthly(request):
    """
    Get comprehensive monthly sales reports

    GET /api/oem/reports/sales/monthly/

    Query params:
        - months: Number of months to retrieve (default: 6)
        - category: Filter by category
        - shop: Filter by shop
        - location: Filter by location (ABUJA/LAGOS)
        - start_date: Start date (YYYY-MM-DD)
        - end_date: End date (YYYY-MM-DD)
        - format: 'json' or 'csv' (default: json)
    """
    try:
        # Parse filters
        months = int(request.query_params.get('months', 6))
        category = request.query_params.get('category')
        shop = request.query_params.get('shop')
        location = request.query_params.get('location')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        output_format = request.query_params.get('format', 'json')

        # Build queryset
        queryset = SalesReportMonthly.objects.using('oem_sync_db').all()

        # Apply filters
        if start_date and end_date:
            queryset = queryset.filter(
                report_month__gte=start_date,
                report_month__lte=end_date
            )
        else:
            # Default to last N months
            end = timezone.now().date()
            start = end - timedelta(days=months * 30)
            queryset = queryset.filter(report_month__gte=start)

        if category:
            queryset = queryset.filter(category=category)
        if shop:
            queryset = queryset.filter(shop=shop)
        if location:
            queryset = queryset.filter(location=location.upper())

        queryset = queryset.order_by('-report_month')

        # Export to CSV if requested
        if output_format == 'csv':
            return export_to_csv(queryset, 'monthly_sales_report')

        # JSON response
        serializer = SalesReportMonthlySerializer(queryset, many=True)

        # Calculate summary statistics
        totals = queryset.aggregate(
            total_revenue=Sum('total_revenue'),
            total_units=Sum('total_units_sold'),
            total_transactions=Sum('total_transactions'),
            avg_transaction_value=Avg('average_transaction_value')
        )

        return Response({
            'report_type': 'monthly_sales',
            'filters': {
                'category': category,
                'shop': shop,
                'location': location,
                'months': months
            },
            'summary': totals,
            'data': serializer.data,
            'record_count': len(serializer.data)
        })

    except Exception as e:
        logger.error(f"Error in sales_report_monthly: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def sales_by_day_of_week(request):
    """
    Get sales patterns by day of week

    GET /api/oem/reports/sales/by-day-of-week/

    Query params:
        - days: Number of days to analyze (default: 30)
        - location: Filter by location
    """
    try:
        days = int(request.query_params.get('days', 30))
        location = request.query_params.get('location')

        queryset = SalesByDayOfWeek.objects.using('oem_sync_db').all()

        # Filter by date range
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        queryset = queryset.filter(
            period_start__gte=start_date,
            period_end__lte=end_date
        )

        if location:
            queryset = queryset.filter(location=location.upper())

        # Aggregate by day of week
        day_summary = queryset.values('day_of_week').annotate(
            total_transactions=Sum('total_transactions'),
            total_units=Sum('total_units_sold'),
            total_revenue=Sum('total_revenue'),
            avg_transactions=Avg('total_transactions')
        ).order_by('day_of_week')

        # Find best day
        best_day = max(day_summary, key=lambda x: x['total_revenue']) if day_summary else None

        serializer = SalesByDayOfWeekSerializer(queryset, many=True)

        return Response({
            'report_type': 'sales_by_day_of_week',
            'period': {
                'start': start_date,
                'end': end_date,
                'days_analyzed': days
            },
            'summary_by_day': list(day_summary),
            'best_performing_day': best_day,
            'detailed_data': serializer.data
        })

    except Exception as e:
        logger.error(f"Error in sales_by_day_of_week: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def sales_by_hour(request):
    """
    Get sales patterns by hour of day

    GET /api/oem/reports/sales/by-hour/

    Query params:
        - days: Number of days to analyze (default: 30)
        - location: Filter by location
    """
    try:
        days = int(request.query_params.get('days', 30))
        location = request.query_params.get('location')

        queryset = SalesByHour.objects.using('oem_sync_db').all()

        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        queryset = queryset.filter(
            period_start__gte=start_date,
            period_end__lte=end_date
        )

        if location:
            queryset = queryset.filter(location=location.upper())

        # Aggregate by hour
        hour_summary = queryset.values('hour').annotate(
            total_transactions=Sum('total_transactions'),
            total_units=Sum('total_units_sold'),
            total_revenue=Sum('total_revenue')
        ).order_by('hour')

        # Find peak hours
        peak_hour = max(hour_summary, key=lambda x: x['total_transactions']) if hour_summary else None

        serializer = SalesByHourSerializer(queryset, many=True)

        return Response({
            'report_type': 'sales_by_hour',
            'period': {
                'start': start_date,
                'end': end_date
            },
            'summary_by_hour': list(hour_summary),
            'peak_hour': peak_hour,
            'detailed_data': serializer.data
        })

    except Exception as e:
        logger.error(f"Error in sales_by_hour: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def product_sales_detail(request):
    """
    Get detailed sales data for specific products

    GET /api/oem/reports/sales/product-details/

    Query params:
        - days: Number of days (default: 30)
        - category: Filter by category
        - brand: Filter by brand
        - shop: Filter by shop
        - location: Filter by location
        - min_units: Minimum units sold
        - sort: 'revenue', 'units', 'transactions' (default: revenue)
        - limit: Number of products (default: 100)
        - format: 'json' or 'csv'
    """
    try:
        days = int(request.query_params.get('days', 30))
        category = request.query_params.get('category')
        brand = request.query_params.get('brand')
        shop = request.query_params.get('shop')
        location = request.query_params.get('location')
        min_units = request.query_params.get('min_units')
        sort_by = request.query_params.get('sort', 'revenue')
        limit = int(request.query_params.get('limit', 100))
        output_format = request.query_params.get('format', 'json')

        queryset = ProductSalesDetail.objects.using('oem_sync_db').all()

        # Date filter
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        queryset = queryset.filter(
            period_start__gte=start_date,
            period_end__lte=end_date
        )

        # Apply filters
        if category:
            queryset = queryset.filter(category=category)
        if brand:
            queryset = queryset.filter(brand__icontains=brand)
        if shop:
            queryset = queryset.filter(shop=shop)
        if location:
            queryset = queryset.filter(location=location.upper())
        if min_units:
            queryset = queryset.filter(units_sold__gte=int(min_units))

        # Sort
        sort_fields = {
            'revenue': '-total_revenue',
            'units': '-units_sold',
            'transactions': '-transactions_count'
        }
        queryset = queryset.order_by(sort_fields.get(sort_by, '-total_revenue'))[:limit]

        # Export to CSV if requested
        if output_format == 'csv':
            return export_to_csv(queryset, 'product_sales_detail')

        serializer = ProductSalesDetailSerializer(queryset, many=True)

        # Calculate totals
        totals = queryset.aggregate(
            total_revenue=Sum('total_revenue'),
            total_units=Sum('units_sold'),
            total_transactions=Sum('transactions_count')
        )

        return Response({
            'report_type': 'product_sales_detail',
            'filters_applied': {
                'days': days,
                'category': category,
                'brand': brand,
                'shop': shop,
                'location': location
            },
            'summary': totals,
            'products': serializer.data,
            'product_count': len(serializer.data)
        })

    except Exception as e:
        logger.error(f"Error in product_sales_detail: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def sales_trends(request):
    """
    Get sales trends with forecasting indicators

    GET /api/oem/reports/sales/trends/

    Query params:
        - period: 'daily', 'weekly', 'monthly' (default: daily)
        - days: Number of days to analyze (default: 30)
        - category: Filter by category
        - location: Filter by location
    """
    try:
        period_type = request.query_params.get('period', 'daily')
        days = int(request.query_params.get('days', 30))
        category = request.query_params.get('category')
        location = request.query_params.get('location')

        queryset = SalesTrend.objects.using('oem_sync_db').filter(
            period_type=period_type
        )

        # Date range
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        queryset = queryset.filter(
            period_date__gte=start_date,
            period_date__lte=end_date
        )

        if category:
            queryset = queryset.filter(category=category)
        if location:
            queryset = queryset.filter(location=location.upper())

        queryset = queryset.order_by('period_date')

        serializer = SalesTrendSerializer(queryset, many=True)

        # Analyze trend direction
        if len(serializer.data) > 1:
            first_revenue = float(serializer.data[0]['revenue'])
            last_revenue = float(serializer.data[-1]['revenue'])
            overall_trend = "increasing" if last_revenue > first_revenue else "decreasing" if last_revenue < first_revenue else "stable"
            trend_percentage = ((last_revenue - first_revenue) / first_revenue * 100) if first_revenue > 0 else 0
        else:
            overall_trend = "insufficient_data"
            trend_percentage = 0

        return Response({
            'report_type': 'sales_trends',
            'period_type': period_type,
            'date_range': {
                'start': start_date,
                'end': end_date
            },
            'overall_trend': {
                'direction': overall_trend,
                'change_percentage': f"{trend_percentage:.2f}%"
            },
            'data_points': serializer.data,
            'data_point_count': len(serializer.data)
        })

    except Exception as e:
        logger.error(f"Error in sales_trends: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def comparison_reports(request):
    """
    Get comparison reports (location vs location, period vs period, etc.)

    GET /api/oem/reports/comparisons/

    Query params:
        - type: 'location', 'period', 'category', 'shop' (default: location)
        - days: Number of days to look back (default: 30)
    """
    try:
        comparison_type = request.query_params.get('type', 'location')
        days = int(request.query_params.get('days', 30))

        queryset = ComparisonReport.objects.using('oem_sync_db').filter(
            comparison_type=comparison_type
        )

        # Date filter
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        queryset = queryset.filter(
            report_date__gte=start_date
        )

        queryset = queryset.order_by('-report_date')

        serializer = ComparisonReportSerializer(queryset, many=True)

        return Response({
            'report_type': 'comparison',
            'comparison_type': comparison_type,
            'comparisons': serializer.data,
            'comparison_count': len(serializer.data)
        })

    except Exception as e:
        logger.error(f"Error in comparison_reports: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================
# ADVANCED SEARCH
# ===========================

@api_view(['GET'])
def advanced_search(request):
    """
    Advanced search across all reports

    GET /api/oem/search/

    Query params:
        - q: Search query (searches brand, category)
        - type: 'inventory', 'sales', 'products'
        - location: Filter by location
        - date_from: Start date
        - date_to: End date
        - limit: Results limit (default: 50)
    """
    try:
        query = request.query_params.get('q', '')
        search_type = request.query_params.get('type', 'inventory')
        location = request.query_params.get('location')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        limit = int(request.query_params.get('limit', 50))

        results = {}

        if search_type == 'inventory' or not search_type:
            # Search inventory
            inventory = InventorySnapshot.objects.using('oem_sync_db').filter(
                Q(brand__icontains=query) | Q(category__icontains=query)
            )
            if location:
                inventory = inventory.filter(location=location.upper())

            results['inventory'] = InventorySnapshotSerializer(
                inventory[:limit], many=True
            ).data

        if search_type == 'products' or not search_type:
            # Search product sales
            products = ProductSalesDetail.objects.using('oem_sync_db').filter(
                Q(brand__icontains=query) | Q(category__icontains=query)
            )
            if location:
                products = products.filter(location=location.upper())
            if date_from:
                products = products.filter(period_start__gte=date_from)
            if date_to:
                products = products.filter(period_end__lte=date_to)

            results['products'] = ProductSalesDetailSerializer(
                products[:limit], many=True
            ).data

        return Response({
            'search_query': query,
            'search_type': search_type,
            'results': results,
            'result_count': sum(len(v) for v in results.values())
        })

    except Exception as e:
        logger.error(f"Error in advanced_search: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================
# EXPORT UTILITIES
# ===========================

def export_to_csv(queryset, filename):
    """
    Export queryset to CSV file
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}_{timezone.now().strftime("%Y%m%d")}.csv"'

    writer = csv.writer(response)

    # Get model fields
    if queryset.exists():
        model = queryset.model
        fields = [f.name for f in model._meta.fields]

        # Write header
        writer.writerow(fields)

        # Write data
        for obj in queryset:
            writer.writerow([getattr(obj, field) for field in fields])

    return response


# ===========================
# SYNC FUNCTIONALITY
# ===========================

@login_required
def trigger_sync(request):
    """
    Manually trigger data sync from main store to OEM database
    GET /api/oem/sync/trigger/
    """
    from .sync import OEMDataSyncManager
    from django.http import JsonResponse

    try:
        sync_manager = OEMDataSyncManager()
        result = sync_manager.sync_all()

        return JsonResponse({
            'status': 'success',
            'message': 'Data sync completed successfully',
            'details': result
        })
    except Exception as e:
        logger.error(f"Sync trigger error: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


# ===========================
# DATA SYNC ENDPOINTS
# ===========================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_inventory_data(request):
    """
    Receive inventory data from local system
    POST /api/oem/sync/inventory/

    Body: {
        "items": [
            {
                "product_id": 1,
                "brand": "Nike",
                "category": "SHOE",
                "quantity": 10,
                ...
            }
        ]
    }
    """
    try:
        items = request.data.get('items', [])

        if not items:
            return Response({
                'status': 'error',
                'message': 'No items provided'
            }, status=status.HTTP_400_BAD_REQUEST)

        created_count = 0
        updated_count = 0

        for item in items:
            product_id = item.get('product_id')
            if not product_id:
                continue

            # Determine stock status
            quantity = item.get('quantity', 0)
            is_out_of_stock = quantity == 0
            is_low_stock = quantity > 0 and quantity <= 10

            # Update or create inventory snapshot
            obj, created = InventorySnapshot.objects.update_or_create(
                product_id=product_id,
                defaults={
                    'brand': item.get('brand', ''),
                    'category': item.get('category', ''),
                    'size': item.get('size', ''),
                    'color': item.get('color', ''),
                    'design': item.get('design', ''),
                    'quantity_available': quantity,
                    'location': item.get('location', ''),
                    'shop': item.get('shop', ''),
                    'is_low_stock': is_low_stock,
                    'is_out_of_stock': is_out_of_stock,
                    'data_source_timestamp': timezone.now(),
                }
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        logger.info(f"Inventory sync: {created_count} created, {updated_count} updated")

        return Response({
            'status': 'success',
            'message': 'Inventory data synced',
            'created': created_count,
            'updated': updated_count,
            'total': len(items)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Inventory sync error: {e}", exc_info=True)
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_sales_data(request):
    """
    Receive sales data from local system
    POST /api/oem/sync/sales/

    Body: {
        "sales": [
            {
                "sale_id": 1,
                "product_id": 1,
                "quantity": 2,
                "total_price": 100.00,
                "sale_date": "2025-10-24T10:30:00Z",
                ...
            }
        ]
    }
    """
    try:
        sales_list = request.data.get('sales', [])

        if not sales_list:
            return Response({
                'status': 'error',
                'message': 'No sales data provided'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Aggregate sales by date, category, location
        from collections import defaultdict
        aggregated = defaultdict(lambda: {
            'units': 0,
            'transactions': 0,
            'revenue': Decimal('0.00')
        })

        for sale in sales_list:
            sale_date = sale.get('sale_date', '')
            if sale_date:
                # Parse date
                sale_datetime = datetime.fromisoformat(sale_date.replace('Z', '+00:00'))
                date_key = sale_datetime.date()
            else:
                date_key = timezone.now().date()

            category = sale.get('product_category', '')
            location = sale.get('location', '')
            shop = sale.get('product_brand', '')  # Using brand as shop identifier

            key = (date_key, category, location, shop)

            aggregated[key]['units'] += sale.get('quantity', 0)
            aggregated[key]['transactions'] += 1
            aggregated[key]['revenue'] += Decimal(str(sale.get('total_price', 0)))

        # Save aggregated data
        created_count = 0
        for key, data in aggregated.items():
            date_val, category, location, shop = key

            SalesSummaryDaily.objects.update_or_create(
                summary_date=date_val,
                category=category,
                location=location,
                shop=shop,
                defaults={
                    'total_units_sold': data['units'],
                    'total_transactions': data['transactions'],
                    'total_revenue': data['revenue']
                }
            )
            created_count += 1

        logger.info(f"Sales sync: {created_count} daily summaries updated")

        return Response({
            'status': 'success',
            'message': 'Sales data synced',
            'summaries_updated': created_count,
            'sales_processed': len(sales_list)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Sales sync error: {e}", exc_info=True)
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================
# FULL DATA SYNC ENDPOINTS
# ===========================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_products_full(request):
    """
    Receive complete product data from local system
    POST /api/oem/sync/products/

    Syncs to store.Product model for full reporting
    """
    try:
        from store.models import Product

        products = request.data.get('products', [])

        if not products:
            return Response({
                'status': 'error',
                'message': 'No products provided'
            }, status=status.HTTP_400_BAD_REQUEST)

        created_count = 0
        updated_count = 0

        for prod in products:
            # Use barcode_number as natural key if available, otherwise use combination of fields
            barcode = prod.get('barcode_number', '')

            if barcode:
                # If barcode exists, use it as the unique identifier
                obj, created = Product.objects.update_or_create(
                    barcode_number=barcode,
                    defaults={
                        'brand': prod.get('brand', ''),
                        'category': prod.get('category', ''),
                        'size': prod.get('size', ''),
                        'color': prod.get('color', ''),
                        'design': prod.get('design', ''),
                        'quantity': prod.get('quantity', 0),
                        'location': prod.get('location', ''),
                        'shop': prod.get('shop', ''),
                        'price': Decimal(str(prod.get('price', 0))),
                        'selling_price': Decimal(str(prod.get('selling_price', 0))),
                        'markup': Decimal(str(prod.get('markup', 0))),
                        'markup_type': prod.get('markup_type', 'percentage'),
                    }
                )
            else:
                # If no barcode, use combination of brand, size, color, location as natural key
                obj, created = Product.objects.update_or_create(
                    brand=prod.get('brand', ''),
                    size=prod.get('size', ''),
                    color=prod.get('color', ''),
                    location=prod.get('location', ''),
                    shop=prod.get('shop', ''),
                    defaults={
                        'category': prod.get('category', ''),
                        'design': prod.get('design', ''),
                        'quantity': prod.get('quantity', 0),
                        'price': Decimal(str(prod.get('price', 0))),
                        'selling_price': Decimal(str(prod.get('selling_price', 0))),
                        'markup': Decimal(str(prod.get('markup', 0))),
                        'markup_type': prod.get('markup_type', 'percentage'),
                        'barcode_number': barcode,
                    }
                )

            if created:
                created_count += 1
            else:
                updated_count += 1

        logger.info(f"Products sync: {created_count} created, {updated_count} updated")

        return Response({
            'status': 'success',
            'message': 'Products synced',
            'created': created_count,
            'updated': updated_count,
            'total': len(products)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Products sync error: {e}", exc_info=True)
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_customers_full(request):
    """
    Receive customer data from local system
    POST /api/oem/sync/customers/
    """
    try:
        from store.models import Customer

        customers = request.data.get('customers', [])

        if not customers:
            return Response({
                'status': 'success',
                'message': 'No customers to sync'
            }, status=status.HTTP_200_OK)

        created_count = 0
        updated_count = 0

        for cust in customers:
            # Use phone_number as natural key if available, otherwise use name
            phone = cust.get('phone_number', '').strip()
            name = cust.get('name', '').strip()

            try:
                if phone:
                    # Use phone number as unique identifier
                    # Handle multiple customers with same phone by getting the first one
                    existing = Customer.objects.filter(phone_number=phone).first()

                    if existing:
                        # Update existing customer
                        existing.name = name or existing.name
                        existing.email = cust.get('email', '') or existing.email
                        existing.address = cust.get('address', '') or existing.address
                        existing.save()
                        obj = existing
                        created = False
                    else:
                        # Create new customer
                        obj = Customer.objects.create(
                            phone_number=phone,
                            name=name,
                            email=cust.get('email', ''),
                            address=cust.get('address', '')
                        )
                        created = True

                elif name:
                    # If no phone, use name (less reliable but better than nothing)
                    existing = Customer.objects.filter(name=name).first()

                    if existing:
                        # Update existing customer
                        existing.phone_number = phone or existing.phone_number
                        existing.email = cust.get('email', '') or existing.email
                        existing.address = cust.get('address', '') or existing.address
                        existing.save()
                        obj = existing
                        created = False
                    else:
                        # Create new customer
                        obj = Customer.objects.create(
                            name=name,
                            phone_number=phone,
                            email=cust.get('email', ''),
                            address=cust.get('address', '')
                        )
                        created = True
                else:
                    # Skip customers without phone or name
                    logger.warning("Skipping customer without phone or name")
                    continue

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            except Exception as e:
                logger.error(f"Error syncing customer {name or phone}: {e}")
                continue

        logger.info(f"Customers sync: {created_count} created, {updated_count} updated")

        return Response({
            'status': 'success',
            'message': 'Customers synced',
            'created': created_count,
            'updated': updated_count
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Customers sync error: {e}", exc_info=True)
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_receipts_full(request):
    """
    Receive receipts with sales and payments
    POST /api/oem/sync/receipts/
    """
    try:
        from store.models import Receipt, Sale, Payment, PaymentMethod, Product, Customer

        receipts = request.data.get('receipts', [])

        if not receipts:
            return Response({
                'status': 'success',
                'message': 'No receipts to sync'
            }, status=status.HTTP_200_OK)

        synced_count = 0
        new_sales_count = 0
        new_payments_count = 0

        for receipt_data in receipts:
            # Get local IDs to track what's already synced
            local_receipt_id = receipt_data.get('local_receipt_id')
            receipt_number = receipt_data.get('receipt_number', '')

            if not receipt_number:
                logger.warning("Skipping receipt without receipt_number")
                continue

            # Parse receipt date safely
            receipt_date_str = receipt_data.get('date')
            if receipt_date_str:
                try:
                    receipt_date = datetime.fromisoformat(receipt_date_str.replace('Z', '+00:00'))
                except (ValueError, AttributeError, TypeError):
                    receipt_date = timezone.now()
            else:
                receipt_date = timezone.now()

            # ADDITIVE APPROACH: Check if receipt already synced by local_receipt_id
            if local_receipt_id:
                receipt = Receipt.objects.filter(local_receipt_id=local_receipt_id).first()
                if not receipt:
                    # New receipt - create it
                    receipt = Receipt.objects.create(
                        receipt_number=receipt_number,
                        local_receipt_id=local_receipt_id,
                        date=receipt_date,
                    )
                # If receipt exists, we skip it (already synced)
            else:
                # Fallback: use receipt_number if no local_receipt_id provided
                receipt, created = Receipt.objects.get_or_create(
                    receipt_number=receipt_number,
                    defaults={
                        'date': receipt_date,
                    }
                )

            # ADDITIVE: Sync sales only if they don't exist yet
            for sale_data in receipt_data.get('sales', []):
                local_sale_id = sale_data.get('local_sale_id')

                # Check if this sale already synced
                if local_sale_id and Sale.objects.filter(local_sale_id=local_sale_id).exists():
                    continue  # Skip - already synced

                # CRITICAL FIX: Find product by barcode or brand+size+color+location
                # (Product IDs differ between local and remote)
                product_barcode = sale_data.get('product_barcode')
                product_brand = sale_data.get('product_brand')
                product_category = sale_data.get('product_category')
                product_size = sale_data.get('product_size')
                product_color = sale_data.get('product_color', '')
                product_location = sale_data.get('product_location')

                product = None

                # Try to find by barcode first (most reliable)
                if product_barcode:
                    product = Product.objects.filter(barcode_number=product_barcode).first()

                # Fallback: find by brand+category+size+color+location
                if not product and product_brand and product_category and product_size and product_location:
                    product = Product.objects.filter(
                        brand=product_brand,
                        category=product_category,
                        size=product_size,
                        color=product_color,
                        location=product_location
                    ).first()

                if not product:
                    logger.warning(f"Product not found for sale (barcode: {product_barcode}, brand: {product_brand}, size: {product_size}), skipping")
                    continue

                # Create new sale (ADDITIVE - never replace)
                # Parse sale date safely
                sale_date_str = sale_data.get('sale_date')
                if sale_date_str:
                    try:
                        sale_date_value = datetime.fromisoformat(sale_date_str.replace('Z', '+00:00'))
                    except (ValueError, AttributeError, TypeError):
                        sale_date_value = timezone.now()
                else:
                    sale_date_value = timezone.now()

                Sale.objects.create(
                    receipt=receipt,
                    product=product,
                    quantity=sale_data.get('quantity', 0),
                    total_price=Decimal(str(sale_data.get('total_price', 0))),
                    discount_amount=Decimal(str(sale_data.get('discount_amount', 0))) if sale_data.get('discount_amount') else Decimal('0'),
                    sale_date=sale_date_value,
                    local_sale_id=local_sale_id,
                )
                new_sales_count += 1

            # ADDITIVE: Sync payment only if it doesn't exist yet
            payment_data = receipt_data.get('payment')
            if payment_data:
                local_payment_id = payment_data.get('local_payment_id')

                # Check if payment already synced - if so, skip creating it but continue processing receipt
                if not (local_payment_id and Payment.objects.filter(local_payment_id=local_payment_id).exists()):
                    # Payment doesn't exist yet, create it

                    # Parse payment date safely
                    payment_date_str = payment_data.get('payment_date')
                    if payment_date_str:
                        try:
                            payment_date_value = datetime.fromisoformat(payment_date_str.replace('Z', '+00:00'))
                        except (ValueError, AttributeError):
                            payment_date_value = timezone.now()
                    else:
                        payment_date_value = timezone.now()

                    payment = Payment.objects.create(
                        payment_status=payment_data.get('payment_status', 'pending'),
                        total_amount=Decimal(str(payment_data.get('total_amount', 0))),
                        total_paid=Decimal(str(payment_data.get('total_paid', 0))),
                        discount_percentage=Decimal(str(payment_data.get('discount_percentage', 0))) if payment_data.get('discount_percentage') else 0,
                        discount_amount=Decimal(str(payment_data.get('discount_amount', 0))) if payment_data.get('discount_amount') else 0,
                        payment_date=payment_date_value,
                        local_payment_id=local_payment_id,
                    )
                    new_payments_count += 1

                    # Link payment to sales from this receipt
                    for sale in receipt.sales.all():
                        sale.payment = payment
                        sale.save()

                    # Sync payment methods
                    for pm_data in payment_data.get('payment_methods', []):
                        PaymentMethod.objects.create(
                            payment=payment,
                            payment_method=pm_data.get('method'),
                            amount=Decimal(str(pm_data.get('amount', 0))),
                            status='completed'
                        )

            # CRITICAL FIX: Calculate and save receipt totals after syncing all sales
            # This ensures the sales report displays correct amounts with discount and delivery
            receipt_sales = receipt.sales.all()
            if receipt_sales.exists():
                subtotal = sum(sale.total_price for sale in receipt_sales)
                receipt.subtotal = subtotal

                # Sync delivery cost if provided
                delivery_cost = Decimal(str(receipt_data.get('delivery_cost', 0))) if receipt_data.get('delivery_cost') else 0
                receipt.delivery_cost = delivery_cost

                # Use receipt.calculate_total() to properly calculate: subtotal - discount + delivery
                receipt.calculate_total()
                receipt.save()

            synced_count += 1

        logger.info(f"Receipts sync: {synced_count} receipts, {new_sales_count} new sales, {new_payments_count} new payments")

        return Response({
            'status': 'success',
            'message': 'Receipts synced (ADDITIVE - no replacements)',
            'synced': synced_count,
            'new_sales': new_sales_count,
            'new_payments': new_payments_count
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Receipts sync error: {e}", exc_info=True)
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
