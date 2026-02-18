from django.urls import path
from . import views
from . import views_printer
from . import views_config
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Authentication
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard & Homepage
    path('homepage/', views.homepage, name='homepage'),

    # Customer Management
    path('customers/', views.customer_list, name='customer_list'),
    path('create_customer/', views.create_customer, name='create_customer'),
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('customers/edit/<int:pk>/', views.edit_customer, name='edit_customer'),
    path('customers/<int:customer_id>/history/', views.customer_receipt_history, name='customer_receipt_history'),
    path('customers/delete/<int:pk>/', views.delete_customer, name='delete_customer'),

    # Product Management
    path('products/', views.product_list, name='product_list'),
    path('add_product/', views.add_product, name='add_product'),
    path('products/edit/<int:product_id>/', views.edit_product, name='edit_product'),
    path('products/delete/<int:product_id>/', views.delete_product, name='delete_product'),
    path('products/transfer-to-warehouse/', views.transfer_to_warehouse_view, name='transfer_to_warehouse'),
    path('products/history-report/', views.product_history_report, name='product_history_report'),
    path('update-quantity/', views.update_product_quantity, name='update_product_quantity'),

  # Transfers
    path('transfers/', views.transfer_menu, name='transfer_menu'),
    path('transfers/list/', views.transfer_list_view, name='transfer_list'),
    path('transfers/create/', views.transfer_create_view, name='transfer_create'),
    path('transfers/internal/', views.internal_transfer_create_view, name='internal_transfer_create'),
    path('transfers/<int:transfer_id>/download/<str:format_type>/', views.download_transfer_document,name='download_transfer_document'),

  # Detail & Actions
   path('transfers/<int:transfer_id>/', views.transfer_detail_view, name='transfer_detail'),
   path('transfers/<int:transfer_id>/update-status/', views.update_transfer_status,name='update_transfer_status'),

    # Sales & POS
    path('sales/', views.sell_product, name='sell_product'),
    path('customer-display/', views.customer_display, name='customer_display'),
    path('sale/success/<int:receipt_id>/', views.sale_success, name='sale_success'),
    path('cancel-order/<int:sale_id>/', views.cancel_order, name='cancel_order'),

    # Receipts
    path('receipts/', views.receipt_list, name='receipt_list'),
    path('receipts/<int:pk>/', views.receipt_detail, name='receipt_detail'),
    path('receipt/<int:pk>/send-email/', views.send_receipt_email, name='send_receipt_email'),
    path('receipt/<int:pk>/download-pdf/', views.download_receipt_pdf, name='download_receipt_pdf'),
    path('print-receipt/<int:receipt_id>/', views.print_receipt, name='print_receipt'),
    path('receipt/<int:pk>/print-pos/', views.print_pos_receipt, name='print_pos_receipt'),




    # Reports
    path('sales_report/', views.sales_report, name='sales_report'),
    path('discount_report/', views.discount_report, name='discount_report'),
    path('delivery_report/', views.delivery_report, name='delivery_report'),
    path('reports/dashboard/', views.reports_dashboard, name='reports_dashboard'),
    path('reports/inventory/', views.inventory_report, name='inventory_report'),
    path('reports/financial/', views.financial_report, name='financial_report'),
    path('reports/tax/', views.tax_report, name='tax_report'),
    path('reports/gift/', views.gift_report, name='gift_report'),
    path('reports-menu/', views.reports_menu, name='reports_menu'),

    # Delivery
    path('delivered-items/', views.delivered_items_view, name='delivered_items'),
    path('delivery/update/<int:sale_id>/', views.update_delivery_status, name='update_delivery_status'),
    path('delivery/', views.delivery, name='delivery'),

    # Invoices
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoice/', views.invoice, name='invoice'),
    path('invoice/<int:pk>/pdf/', views.export_invoice_pdf, name='export_invoice_pdf'),
    path('invoice/<int:pk>/excel/', views.export_invoice_excel, name='export_invoice_excel'),

    # Pre-Orders
    path('pre_order/', views.pre_order, name='pre_order'),
    path('pre-orders/', views.pre_order_list, name='pre_order_list'),
    path('pre-order/<int:pre_order_id>/', views.pre_order_detail, name='pre_order_detail'),
    path('pre-orders/<int:pre_order_id>/toggle-delivered/', views.toggle_delivered, name='toggle_delivered'),
    path('pre-orders/<int:pre_order_id>/edit/', views.edit_pre_order, name='edit_pre_order'),
    path('pre-orders/<int:pre_order_id>/delete/', views.delete_pre_order, name='delete_pre_order'),
    path('pre-orders/<int:pre_order_id>/convert/', views.convert_preorder_to_product, name='convert_preorder_to_product'),

    # User Management
    path('users/', views.user_management_dashboard, name='user_management_dashboard'),
    path('users/create/', views.create_user, name='create_user'),
    path('users/edit/<int:user_id>/', views.edit_user, name='edit_user'),
    path('users/toggle-status/<int:user_id>/', views.toggle_user_status, name='toggle_user_status'),
    path('users/delete/<int:user_id>/', views.delete_user, name='delete_user'),
    path('profile/', views.user_profile_view, name='user_profile'),
    path('user-menu/', views.user_menu, name='user_menu'),

    # Tools & Utilities
    path('tools-menu/', views.tools_menu, name='tools_menu'),
    path('inventory-menu/', views.inventory_menu, name='inventory_menu'),
    path('access-denied/', views.access_denied, name='access_denied'),

    # Barcode & Label Printing
    path('lookup-product/', views.lookup_product_by_barcode, name='lookup_product_by_barcode'),
    path('lookup-product-by-barcode/', views.lookup_product_by_barcode, name='lookup_product_by_barcode_alt'),
    path('barcode-lookup/', views.barcode_lookup_page, name='barcode_lookup_page'),
    path('barcode/print/<int:product_id>/', views.print_barcode, name='print_barcode'),
    path('generate-barcodes/', views.generate_barcodes_view, name='generate_barcodes'),
    path('generate-single-barcode/<int:product_id>/', views.generate_single_barcode_ajax, name='generate_single_barcode_ajax'),
    path('generate-barcodes-bulk/', views.generate_barcodes_redirect_view, name='generate_barcodes_bulk'),
    path('barcode-print-manager/', views.barcode_print_manager, name='barcode_print_manager'),
    path('print_multiple_barcodes_directly/', views.print_multiple_barcodes_directly,name='print_multiple_barcodes_directly'),
    path('print_single_barcode_directly/<int:product_id>/', views.print_single_barcode_directly,name='print_single_barcode_directly'),

    # Excel Upload/Download
    path('upload-products/', views.upload_products_excel, name='upload_products'),
    path('download-template/', views.download_excel_template, name='download_template'),
    path('products/upload/', views.upload_products_excel, name='upload_products_excel'),
    path('products/template/', views.download_excel_template, name='download_excel_template'),
    path('products/export/excel/', views.export_products_excel, name='export_products_excel'),
    path('products/export/pdf/', views.export_products_pdf, name='export_products_pdf'),

    # Printer Management
    path('printers/', views_printer.printer_management, name='printer_management'),
    path('printers/add/', views_printer.add_printer, name='add_printer'),
    path('printers/edit/<int:pk>/', views_printer.edit_printer, name='edit_printer'),
    path('printers/delete/<int:pk>/', views_printer.delete_printer, name='delete_printer'),
    path('printers/test/<int:pk>/', views_printer.test_printer, name='test_printer'),
    path('printers/set-default/<int:pk>/', views_printer.set_default_printer, name='set_default_printer'),
    path('printers/toggle-status/<int:pk>/', views_printer.toggle_printer_status, name='toggle_printer_status'),
    path('printers/job-history/', views_printer.print_job_history, name='print_job_history'),
    path('api/printers/system/', views_printer.get_system_printers_ajax, name='get_system_printers_ajax'),

    # Task to Printer Mapping
    path('printers/task-mapping/', views_printer.task_printer_mapping, name='task_printer_mapping'),
    path('printers/task-mapping/add/', views_printer.add_task_mapping, name='add_task_mapping'),
    path('printers/task-mapping/edit/<int:pk>/', views_printer.edit_task_mapping, name='edit_task_mapping'),
    path('printers/task-mapping/delete/<int:pk>/', views_printer.delete_task_mapping, name='delete_task_mapping'),
    path('printers/task-mapping/toggle/<int:pk>/', views_printer.toggle_task_mapping_status, name='toggle_task_mapping_status'),
    path('api/printers/quick-assign/<int:pk>/', views_printer.quick_assign_printer, name='quick_assign_printer'),

    # Configuration Menu
    path('configuration/', views_config.configuration_menu, name='configuration_menu'),

    # Store Configuration Management
    path('config/', views_config.store_configuration, name='store_configuration'),
    path('config/edit/', views_config.edit_configuration, name='edit_configuration'),
    path('config/edit/<int:pk>/', views_config.edit_configuration, name='edit_configuration_pk'),
    path('config/add/', views_config.add_configuration, name='add_configuration'),
    path('config/activate/<int:pk>/', views_config.activate_configuration, name='activate_configuration'),
    path('config/delete/<int:pk>/', views_config.delete_configuration, name='delete_configuration'),
    path('config/preview/<int:pk>/', views_config.preview_configuration, name='preview_configuration'),

    # Loyalty Configuration
    path('config/loyalty/', views_config.loyalty_configuration, name='loyalty_configuration'),
    path('config/loyalty/edit/', views_config.edit_loyalty_configuration, name='edit_loyalty_configuration'),

    # Payment Method Configuration
    path('config/payment-methods/', views_config.payment_method_configuration, name='payment_method_configuration'),
    path('config/payment-methods/add/', views_config.add_payment_method, name='add_payment_method'),
    path('config/payment-methods/edit/<int:pk>/', views_config.edit_payment_method, name='edit_payment_method'),
    path('config/payment-methods/delete/<int:pk>/', views_config.delete_payment_method, name='delete_payment_method'),
    path('config/payment-methods/toggle/<int:pk>/', views_config.toggle_payment_method, name='toggle_payment_method'),
    path('config/payment-methods/sync/', views_config.sync_payment_methods, name='sync_payment_methods'),

    # Tax Configuration
    path('config/tax/', views_config.tax_configuration, name='tax_configuration'),
    path('config/tax/add/', views_config.add_tax, name='add_tax'),
    path('config/tax/edit/<int:pk>/', views_config.edit_tax, name='edit_tax'),
    path('config/tax/delete/<int:pk>/', views_config.delete_tax, name='delete_tax'),
    path('config/tax/toggle/<int:pk>/', views_config.toggle_tax, name='toggle_tax'),

    # Activity Logs
    path('activity-logs/', views.activity_log_list, name='activity_log_list'),
    path('activity-logs/<int:log_id>/', views.activity_log_detail, name='activity_log_detail'),

    # Loyalty Program API Endpoints
    path('api/loyalty/customer/<int:customer_id>/', views.get_customer_loyalty_info, name='get_customer_loyalty_info'),
    path('api/loyalty/apply-discount/', views.apply_loyalty_discount, name='apply_loyalty_discount'),
    path('api/loyalty/enroll/', views.enroll_customer_in_loyalty, name='enroll_customer_in_loyalty'),

    # Returns Management
    path('returns/', views.return_list, name='return_list'),
    path('returns/<int:return_id>/', views.return_detail, name='return_detail'),
    path('returns/search/', views.return_search, name='return_search'),
    path('returns/create/<int:receipt_id>/', views.return_select_items, name='return_select_items'),
    path('returns/select-receipt/<int:receipt_id>/', views.return_select_items, name='return_select_receipt'),
    path('returns/process/<int:receipt_id>/', views.return_select_items, name='return_create'),
    path('returns/<int:return_id>/approve/', views.return_approve, name='return_approve'),
    path('returns/<int:return_id>/reject/', views.return_reject, name='return_reject'),
    path('returns/<int:return_id>/complete/', views.return_complete_form, name='return_complete_form'),
    path('returns/<int:return_id>/cancel/', views.return_cancel, name='return_cancel'),

    # Store Credits
    path('store-credits/', views.store_credit_list, name='store_credit_list'),
    path('store-credits/<int:credit_id>/', views.store_credit_detail, name='store_credit_detail'),
    path('api/store-credit/customer/<int:customer_id>/', views.get_customer_store_credit, name='get_customer_store_credit'),

    # Partial Payments
    path('receipts/<int:receipt_id>/add-payment/', views.add_partial_payment, name='add_partial_payment'),
    path('customer-debt/', views.customer_debt_dashboard, name='customer_debt_dashboard'),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)