from django.contrib import admin
from .models import (
    Product, WarehouseInventory, PrinterConfiguration, PrintJob, PrinterTaskMapping,
    StoreConfiguration, ActivityLog, LoyaltyConfiguration,
    CustomerLoyaltyAccount, LoyaltyTransaction, Customer, Receipt, PartialPayment
)
from django.utils.html import format_html


class ProductAdmin(admin.ModelAdmin):
    list_display = ['brand', 'category', 'price', 'barcode_image_tag']
    readonly_fields = ['barcode_image_tag']

    def barcode_image_tag(self, obj):
        if obj.barcode_image:
            return f'<img src="{obj.barcode_image.url}" width="150" height="50" />'
        return "No barcode"

    barcode_image_tag.allow_tags = True
    barcode_image_tag.short_description = 'Barcode'


class PrinterConfigurationAdmin(admin.ModelAdmin):
    list_display = ['name', 'printer_type', 'system_printer_name', 'is_default', 'is_active', 'auto_print']
    list_filter = ['printer_type', 'is_default', 'is_active', 'auto_print']
    search_fields = ['name', 'system_printer_name']
    readonly_fields = ['created_at', 'updated_at', 'created_by']


class PrintJobAdmin(admin.ModelAdmin):
    list_display = ['id', 'document_type', 'document_id', 'printer', 'status', 'created_at', 'created_by']
    list_filter = ['status', 'document_type', 'printer__printer_type']
    search_fields = ['document_id', 'error_message']
    readonly_fields = ['created_at', 'completed_at', 'created_by']
    date_hierarchy = 'created_at'


class PrinterTaskMappingAdmin(admin.ModelAdmin):
    list_display = ['task_name', 'printer', 'is_active', 'auto_print', 'copies']
    list_filter = ['is_active', 'auto_print', 'printer__printer_type']
    search_fields = ['task_name', 'notes']
    readonly_fields = ['created_at', 'updated_at']


class StoreConfigurationAdmin(admin.ModelAdmin):
    list_display = ['deployment_name', 'store_name', 'email', 'phone', 'currency_code', 'is_active', 'updated_at']
    list_filter = ['is_active', 'currency_code', 'country']
    search_fields = ['store_name', 'deployment_name', 'email', 'phone', 'city']
    readonly_fields = ['created_at', 'updated_at', 'updated_by']

    fieldsets = (
        ('Store Identity', {
            'fields': ('store_name', 'tagline', 'deployment_name')
        }),
        ('Contact Information', {
            'fields': ('email', 'phone', 'phone_2')
        }),
        ('Address', {
            'fields': ('address_line_1', 'address_line_2', 'city', 'state', 'country', 'postal_code')
        }),
        ('Business Information', {
            'fields': ('tax_id', 'website', 'business_hours')
        }),
        ('Branding', {
            'fields': ('logo', 'receipt_logo', 'favicon')
        }),
        ('Currency & Localization', {
            'fields': ('currency_symbol', 'currency_code', 'timezone', 'date_format')
        }),
        ('Receipt Settings', {
            'fields': ('receipt_header_text', 'receipt_footer_text', 'show_receipt_tax_id')
        }),
        ('Social Media', {
            'fields': ('facebook_url', 'instagram_url', 'twitter_url')
        }),
        ('System', {
            'fields': ('is_active', 'created_at', 'updated_at', 'updated_by')
        }),
    )


class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'username', 'action_display', 'description', 'ip_address', 'success']
    list_filter = ['action', 'success', 'created_at', 'model_name']
    search_fields = ['username', 'description', 'ip_address', 'object_repr']
    readonly_fields = ['created_at', 'user', 'username', 'action', 'action_display', 'description',
                       'model_name', 'object_id', 'object_repr', 'ip_address', 'user_agent',
                       'extra_data', 'success', 'error_message']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']

    def has_add_permission(self, request):
        # Activity logs should only be created programmatically
        return False

    def has_change_permission(self, request, obj=None):
        # Activity logs should be read-only
        return False

    def has_delete_permission(self, request, obj=None):
        # Only superusers can delete activity logs
        return request.user.is_superuser


# =====================================
# LOYALTY PROGRAM ADMIN
# =====================================

class LoyaltyConfigurationAdmin(admin.ModelAdmin):
    list_display = [
        'program_name', 'is_active', 'calculation_type',
        'points_per_transaction', 'display_per_amount_rule',
        'minimum_points_for_redemption', 'updated_at'
    ]
    list_filter = ['is_active', 'calculation_type', 'points_expire', 'send_points_earned_email']
    search_fields = ['program_name']
    readonly_fields = ['created_at', 'updated_at', 'created_by']

    fieldsets = (
        ('Program Settings', {
            'fields': ('program_name', 'is_active')
        }),
        ('Point Earning Rules', {
            'fields': (
                'calculation_type',
                'points_per_transaction',
                'points_per_currency_unit',
                'currency_unit_value'
            ),
            'description': 'Configure how customers earn points'
        }),
        ('Point Redemption Rules', {
            'fields': (
                'points_to_currency_rate',
                'minimum_points_for_redemption',
                'maximum_discount_percentage'
            ),
            'description': 'Configure how customers redeem points'
        }),
        ('Point Expiration', {
            'fields': ('points_expire', 'points_expiry_days'),
            'description': 'Configure if and when points expire'
        }),
        ('Email Notifications', {
            'fields': (
                'send_welcome_email',
                'send_points_earned_email',
                'send_points_redeemed_email',
                'send_expiry_reminder_email',
                'expiry_reminder_days'
            ),
            'description': 'Configure email notifications'
        }),
        ('Advanced', {
            'fields': ('enable_bonus_multipliers',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )

    def display_per_amount_rule(self, obj):
        return f"{obj.points_per_currency_unit} pts / ₦{obj.currency_unit_value}"
    display_per_amount_rule.short_description = 'Per Amount Rule'

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class LoyaltyTransactionInline(admin.TabularInline):
    model = LoyaltyTransaction
    extra = 0
    readonly_fields = ['transaction_type', 'points', 'balance_after', 'description', 'receipt', 'created_at']
    can_delete = False
    max_num = 10

    def has_add_permission(self, request, obj=None):
        return False


class CustomerLoyaltyAccountAdmin(admin.ModelAdmin):
    list_display = [
        'customer_name', 'customer_email', 'current_balance',
        'total_points_earned', 'total_points_redeemed',
        'display_redeemable_value', 'tier', 'is_active', 'last_transaction_date'
    ]
    list_filter = ['is_active', 'tier', 'enrollment_date']
    search_fields = ['customer__name', 'customer__email', 'customer__phone_number']
    readonly_fields = [
        'customer', 'total_points_earned', 'total_points_redeemed',
        'enrollment_date', 'last_transaction_date', 'updated_at',
        'display_redeemable_value'
    ]
    inlines = [LoyaltyTransactionInline]

    fieldsets = (
        ('Customer', {
            'fields': ('customer',)
        }),
        ('Points Balance', {
            'fields': (
                'current_balance',
                'total_points_earned',
                'total_points_redeemed',
                'display_redeemable_value'
            )
        }),
        ('Status', {
            'fields': ('is_active', 'tier')
        }),
        ('Dates', {
            'fields': ('enrollment_date', 'last_transaction_date', 'updated_at')
        }),
    )

    def customer_name(self, obj):
        return obj.customer.name
    customer_name.short_description = 'Customer'
    customer_name.admin_order_field = 'customer__name'

    def customer_email(self, obj):
        return obj.customer.email or '-'
    customer_email.short_description = 'Email'
    customer_email.admin_order_field = 'customer__email'

    def display_redeemable_value(self, obj):
        value = obj.get_redeemable_value()
        return format_html('<strong>₦{:.2f}</strong>', value)
    display_redeemable_value.short_description = 'Redeemable Value'


class LoyaltyTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'customer_name', 'transaction_type',
        'points', 'balance_after', 'receipt_number', 'monetary_value'
    ]
    list_filter = ['transaction_type', 'created_at', 'is_expired']
    search_fields = [
        'loyalty_account__customer__name',
        'loyalty_account__customer__email',
        'receipt__receipt_number',
        'description'
    ]
    readonly_fields = [
        'loyalty_account', 'transaction_type', 'points', 'balance_after',
        'description', 'receipt', 'monetary_value', 'created_at',
        'created_by', 'expires_at', 'is_expired'
    ]
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Transaction Details', {
            'fields': (
                'loyalty_account',
                'transaction_type',
                'points',
                'balance_after',
                'monetary_value'
            )
        }),
        ('Related Records', {
            'fields': ('receipt', 'created_by')
        }),
        ('Description', {
            'fields': ('description',)
        }),
        ('Dates & Expiration', {
            'fields': ('created_at', 'expires_at', 'is_expired')
        }),
    )

    def customer_name(self, obj):
        return obj.loyalty_account.customer.name
    customer_name.short_description = 'Customer'

    def receipt_number(self, obj):
        if obj.receipt:
            return obj.receipt.receipt_number
        return '-'
    receipt_number.short_description = 'Receipt'

    def has_add_permission(self, request):
        # Transactions should only be created through the system
        return False

    def has_delete_permission(self, request, obj=None):
        # Only superusers can delete transactions
        return request.user.is_superuser


class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone_number', 'email', 'display_loyalty_points', 'frequent_customer', 'created_at']
    list_filter = ['frequent_customer', 'sex', 'created_at']
    search_fields = ['name', 'phone_number', 'email']
    readonly_fields = ['created_at', 'display_loyalty_info']

    fieldsets = (
        ('Customer Information', {
            'fields': ('name', 'phone_number', 'email', 'sex', 'address')
        }),
        ('Status', {
            'fields': ('frequent_customer', 'created_at')
        }),
        ('Loyalty Program', {
            'fields': ('display_loyalty_info',),
            'classes': ('collapse',)
        }),
    )

    def display_loyalty_points(self, obj):
        try:
            account = obj.loyalty_account
            return format_html(
                '<strong>{}</strong> points (₦{:.2f})',
                account.current_balance,
                account.get_redeemable_value()
            )
        except CustomerLoyaltyAccount.DoesNotExist:
            return format_html('<span style="color: gray;">Not enrolled</span>')
    display_loyalty_points.short_description = 'Loyalty Points'

    def display_loyalty_info(self, obj):
        try:
            account = obj.loyalty_account
            html = f"""
            <div style="padding: 10px; background: #f8f9fa; border-radius: 5px;">
                <h3 style="margin-top: 0;">Loyalty Account Summary</h3>
                <table style="width: 100%;">
                    <tr>
                        <td><strong>Current Balance:</strong></td>
                        <td>{account.current_balance} points</td>
                    </tr>
                    <tr>
                        <td><strong>Redeemable Value:</strong></td>
                        <td>₦{account.get_redeemable_value():.2f}</td>
                    </tr>
                    <tr>
                        <td><strong>Total Earned:</strong></td>
                        <td>{account.total_points_earned} points</td>
                    </tr>
                    <tr>
                        <td><strong>Total Redeemed:</strong></td>
                        <td>{account.total_points_redeemed} points</td>
                    </tr>
                    <tr>
                        <td><strong>Tier:</strong></td>
                        <td>{account.tier}</td>
                    </tr>
                    <tr>
                        <td><strong>Status:</strong></td>
                        <td>{'Active' if account.is_active else 'Inactive'}</td>
                    </tr>
                    <tr>
                        <td><strong>Enrolled:</strong></td>
                        <td>{account.enrollment_date.strftime('%Y-%m-%d')}</td>
                    </tr>
                </table>
            </div>
            """
            return format_html(html)
        except CustomerLoyaltyAccount.DoesNotExist:
            return format_html(
                '<div style="padding: 10px; background: #fff3cd; border-radius: 5px;">'
                '<strong>Not enrolled in loyalty program</strong><br>'
                'A loyalty account will be created automatically when this customer makes a purchase.'
                '</div>'
            )
    display_loyalty_info.short_description = 'Loyalty Information'


class WarehouseInventoryAdmin(admin.ModelAdmin):
    list_display = ['brand', 'category', 'size', 'color', 'quantity', 'location', 'price', 'original_barcode']
    list_filter = ['location', 'category']
    search_fields = ['brand', 'category', 'size', 'color', 'original_barcode']
    readonly_fields = ['created_at', 'updated_at']


class PartialPaymentAdmin(admin.ModelAdmin):
    """Admin interface for partial payment tracking"""
    list_display = ['receipt', 'amount', 'payment_method', 'payment_date', 'received_by']
    list_filter = ['payment_method', 'payment_date']
    search_fields = ['receipt__receipt_number', 'notes']
    readonly_fields = ['payment_date']
    date_hierarchy = 'payment_date'

    fieldsets = (
        ('Payment Information', {
            'fields': ('receipt', 'amount', 'payment_method')
        }),
        ('Details', {
            'fields': ('notes', 'received_by', 'payment_date')
        }),
    )


admin.site.register(Product, ProductAdmin)
admin.site.register(WarehouseInventory, WarehouseInventoryAdmin)
admin.site.register(PrinterConfiguration, PrinterConfigurationAdmin)
admin.site.register(PrintJob, PrintJobAdmin)
admin.site.register(PrinterTaskMapping, PrinterTaskMappingAdmin)
admin.site.register(StoreConfiguration, StoreConfigurationAdmin)
admin.site.register(ActivityLog, ActivityLogAdmin)

# Register Loyalty models
admin.site.register(LoyaltyConfiguration, LoyaltyConfigurationAdmin)
admin.site.register(CustomerLoyaltyAccount, CustomerLoyaltyAccountAdmin)
admin.site.register(LoyaltyTransaction, LoyaltyTransactionAdmin)
admin.site.register(Customer, CustomerAdmin)

# Register Debt Management models
admin.site.register(PartialPayment, PartialPaymentAdmin)



