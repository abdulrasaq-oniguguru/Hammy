# Standard library
import hashlib
import io
import json
import logging
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO

# Third-party libraries
from weasyprint import HTML

# Django imports
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.sites.shortcuts import get_current_site
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db import models, transaction
from django.db.models import Q, F, Sum, Avg, Count, FloatField, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce, TruncMonth, TruncWeek, TruncDay
from django.forms import formset_factory
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import make_aware
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

# Local app imports
from ..choices import ProductChoices
from ..forms import (
    SaleForm, PaymentForm, PaymentValidationForm, PaymentMethodFormSet,
    CustomerForm,
)
from ..models import (
    Product, Customer, Sale, Receipt, Payment, PaymentMethod, Delivery,
    ProductHistory, ActivityLog, StoreConfiguration, LoyaltyConfiguration,
    LoyaltyTransaction, TaxConfiguration, PartialPayment, StoreCredit,
    StoreCreditUsage, PrinterTaskMapping,
)
from ..loyalty_utils import process_sale_loyalty_points
from .auth import is_md, is_cashier, is_superuser, user_required_access

logger = logging.getLogger(__name__)

def send_receipt_email_background(receipt_id, domain, protocol='https', max_retries=2, retry_delay=600):
    """
    Send receipt email in background thread with retries
    """

    def email_task():
        for attempt in range(max_retries + 1):
            try:
                # Import models inside function to avoid import issues in thread
                from ..models import Receipt, Delivery  # Adjust import path as needed

                # Get receipt and related data
                receipt = Receipt.objects.select_related('customer', 'user').get(pk=receipt_id)
                sales = receipt.sales.select_related('product').all()

                if not receipt.customer or not receipt.customer.email:
                    logger.warning(f"Receipt {receipt_id}: No customer email")
                    return

                # Get payment info
                payment = None
                if sales.exists():
                    first_sale = sales.first()
                    if hasattr(first_sale, 'payment') and first_sale.payment:
                        payment = first_sale.payment

                # Calculate totals (gift items count as ₦0)
                has_gifts = any(sale.is_gift for sale in sales)
                total_item_discount = sum(
                    (sale.discount_amount or Decimal('0.00')) * sale.quantity
                    for sale in sales if not sale.is_gift
                )
                total_price_before_discount = sum(
                    sale.product.selling_price * sale.quantity
                    for sale in sales if not sale.is_gift
                )
                total_bill_discount = payment.discount_amount if payment else Decimal('0.00')
                final_subtotal = total_price_before_discount - total_item_discount - total_bill_discount
                subtotal_amount = sum(
                    Decimal('0') if sale.is_gift else sale.total_price for sale in sales
                )

                # Get delivery info
                delivery_cost = Decimal('0.00')
                delivery = None
                if receipt.customer:
                    try:
                        delivery = Delivery.objects.filter(customer=receipt.customer).latest('delivery_date')
                        if delivery.delivery_option == 'delivery':
                            delivery_cost = Decimal(str(delivery.delivery_cost))
                    except Delivery.DoesNotExist:
                        pass

                final_total_with_delivery = final_subtotal + delivery_cost
                logo_url = f'{protocol}://{domain}{static("img/Wlogo.png")}'

                # Payment methods and partial payment history for PDF template
                payments = payment.payment_methods.all() if payment else []
                partial_payments = list(PartialPayment.objects.filter(receipt=receipt).order_by('payment_date'))

                # Get loyalty points information if customer has loyalty account
                loyalty_info = None
                try:
                    from ..loyalty_utils import get_customer_loyalty_summary
                    config = LoyaltyConfiguration.get_active_config()
                    if config.is_active and receipt.customer:
                        loyalty_summary = get_customer_loyalty_summary(receipt.customer)
                        if loyalty_summary['has_account']:
                            # Get the loyalty transaction for this receipt
                            loyalty_transaction = LoyaltyTransaction.objects.filter(
                                receipt=receipt,
                                transaction_type='earned'
                            ).first()

                            if loyalty_transaction:
                                loyalty_info = {
                                    'program_name': config.program_name,
                                    'points_earned': loyalty_transaction.points,
                                    'previous_balance': loyalty_transaction.balance_after - loyalty_transaction.points,
                                    'new_balance': loyalty_transaction.balance_after,
                                    'redeemable_value': receipt.customer.loyalty_account.get_redeemable_value(),
                                    'points_threshold': config.minimum_points_for_redemption,
                                    'discount_percentage': config.maximum_discount_percentage,
                                }
                except Exception as e:
                    logger.error(f"Error fetching loyalty info for receipt email: {e}")

                # Get store configuration
                store_config = StoreConfiguration.get_active_config()

                # Context for templates
                context = {
                    'receipt': receipt,
                    'sales': sales,
                    'payment': payment,
                    'payments': payments,
                    'customer_name': receipt.customer.name,
                    'user': receipt.user,
                    'has_gifts': has_gifts,
                    'total_item_discount': total_item_discount,
                    'total_bill_discount': total_bill_discount,
                    'total_price_before_discount': total_price_before_discount,
                    'subtotal_amount': subtotal_amount,
                    'final_total': final_subtotal,
                    'final_total_with_delivery': final_total_with_delivery,
                    'delivery': delivery,
                    'delivery_cost': delivery_cost,
                    'partial_payments': partial_payments,
                    'logo_url': logo_url,
                    'loyalty_info': loyalty_info,
                    'store_config': store_config,
                    'store_name': store_config.store_name,
                    'store_phone': store_config.phone,
                    'store_email': store_config.email,
                    'currency_symbol': store_config.currency_symbol,
                }

                # Generate email and PDF
                html_message = render_to_string('receipt/receipt_email_template.html', context)
                pdf_html = render_to_string('receipt/receipt_pdf.html', context)

                pdf_file = BytesIO()
                HTML(string=pdf_html).write_pdf(pdf_file)
                pdf_content = pdf_file.getvalue()

                if not pdf_content:
                    raise Exception("Generated PDF is empty")

                # Validate PDF before sending
                from ..pdf_validator import validate_receipt_pdf
                is_valid, error_msg = validate_receipt_pdf(pdf_content, receipt, sales, store_config)

                if not is_valid:
                    raise Exception(f"PDF validation failed: {error_msg}")

                logger.info(f"✅ PDF validation passed for receipt {receipt_id} - all required data present")

                # Send email
                logger.info(f"📧 Preparing to send email for receipt {receipt_id} to {receipt.customer.email}")
                logger.info(f"   Loyalty info included: {bool(loyalty_info)}")
                if loyalty_info:
                    logger.info(f"   Points earned: {loyalty_info['points_earned']}")

                subject = f"Your Receipt #{receipt.receipt_number}"
                email = EmailMessage(
                    subject=subject,
                    body=html_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[receipt.customer.email],
                    attachments=[
                        (f'Receipt_{receipt.receipt_number}.pdf', pdf_content, 'application/pdf')
                    ]
                )
                email.content_subtype = "html"
                email.send()

                logger.info(f"✅ Receipt email sent successfully for receipt {receipt_id} to {receipt.customer.email}")
                logger.info(f"   Email included loyalty points: {bool(loyalty_info)}")
                return  # Success - exit the retry loop

            except Exception as e:
                logger.error(f"❌ Attempt {attempt + 1} failed for receipt {receipt_id}: {str(e)}")
                if attempt < max_retries:
                    logger.info(f"🔄 Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)  # Wait before retry
                else:
                    logger.error(f"💥 Failed to send email for receipt {receipt_id} after {max_retries + 1} attempts")

    # Start the background thread
    thread = threading.Thread(target=email_task)
    thread.daemon = True  # Dies when main program exits
    thread.start()





@login_required(login_url='login')
def sell_product(request):
    from ..models import PaymentMethod, TaxConfiguration

    # Only show products on shop floor (exclude warehouse)
    products = Product.objects.filter(quantity__gt=0, shop='STORE')
    customers = Customer.objects.all()
    SaleFormSet = formset_factory(SaleForm, extra=1)

    # Get dynamic payment method choices
    payment_method_choices = PaymentMethod.get_payment_method_choices()

    # Get active taxes for display
    active_taxes = TaxConfiguration.get_active_taxes()

    if request.method == 'POST':
        # Check if this is a debt payment (outstanding balance payment)
        debt_payment_receipt_id = request.POST.get('debt_payment_receipt_id')

        if debt_payment_receipt_id:
            # Handle debt payment separately
            logger.info("=" * 80)
            logger.info("DEBT PAYMENT PROCESSING STARTED")
            logger.info(f"Receipt ID: {debt_payment_receipt_id}")
            logger.info(f"POST data: {dict(request.POST)}")
            logger.info("=" * 80)

            try:
                outstanding_receipt = Receipt.objects.get(id=debt_payment_receipt_id)
                logger.info(f"Found receipt: {outstanding_receipt.receipt_number}")
                logger.info(f"Current balance: ₦{outstanding_receipt.balance_remaining}")
                logger.info(f"Amount paid so far: ₦{outstanding_receipt.amount_paid}")

                payment_methods_formset = PaymentMethodFormSet(request.POST, prefix='payment_method')
                logger.info(f"Payment formset is_valid: {payment_methods_formset.is_valid()}")

                if not payment_methods_formset.is_valid():
                    logger.error(f"Formset errors: {payment_methods_formset.errors}")
                    logger.error(f"Formset non_form_errors: {payment_methods_formset.non_form_errors()}")

                if payment_methods_formset.is_valid():
                    # Calculate total payment amount
                    total_payment_amount = Decimal('0')
                    logger.info(f"Processing {len(payment_methods_formset)} payment forms")

                    for i, form in enumerate(payment_methods_formset):
                        logger.info(f"Form {i} - cleaned_data: {form.cleaned_data}")
                        if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                            if form.cleaned_data.get('amount'):
                                amount = Decimal(str(form.cleaned_data['amount']))
                                payment_method = form.cleaned_data.get('payment_method', 'N/A')
                                logger.info(f"Form {i} - Method: {payment_method}, Amount: ₦{amount}")
                                total_payment_amount += amount

                    logger.info(f"Total payment amount: ₦{total_payment_amount}")

                    if total_payment_amount <= 0:
                        messages.error(request, 'Payment amount must be greater than zero.')
                        return redirect('customer_debt_dashboard')

                    # Allow small overpayments (tolerance of ₦100 for rounding)
                    overpayment_tolerance = Decimal('100.00')
                    if total_payment_amount > (outstanding_receipt.balance_remaining + overpayment_tolerance):
                        messages.error(request, f'Payment amount (₦{total_payment_amount:,.2f}) significantly exceeds balance due (₦{outstanding_receipt.balance_remaining:,.2f})')
                        return redirect('customer_debt_dashboard')

                    # Create partial payment records
                    for form in payment_methods_formset:
                        if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                            if form.cleaned_data.get('payment_method') and form.cleaned_data.get('amount'):
                                PartialPayment.objects.create(
                                    receipt=outstanding_receipt,
                                    amount=form.cleaned_data['amount'],
                                    payment_method=form.cleaned_data['payment_method'],
                                    received_by=request.user,
                                )

                    # Update receipt
                    outstanding_receipt.amount_paid += total_payment_amount
                    outstanding_receipt.balance_remaining -= total_payment_amount

                    # Ensure balance doesn't go negative
                    if outstanding_receipt.balance_remaining < Decimal('0'):
                        outstanding_receipt.balance_remaining = Decimal('0')
                        outstanding_receipt.payment_status = 'paid'

                    # Use a small tolerance for floating point comparison
                    if outstanding_receipt.balance_remaining <= Decimal('0.01'):
                        outstanding_receipt.payment_status = 'paid'
                        outstanding_receipt.balance_remaining = Decimal('0')
                    else:
                        outstanding_receipt.payment_status = 'partial'

                    outstanding_receipt.save()

                    logger.info("=" * 80)
                    logger.info("DEBT PAYMENT COMPLETED SUCCESSFULLY")
                    logger.info(f"Receipt: {outstanding_receipt.receipt_number}")
                    logger.info(f"Payment recorded: ₦{total_payment_amount}")
                    logger.info(f"New amount paid: ₦{outstanding_receipt.amount_paid}")
                    logger.info(f"New balance: ₦{outstanding_receipt.balance_remaining}")
                    logger.info(f"Payment status: {outstanding_receipt.payment_status}")
                    logger.info("=" * 80)

                    if outstanding_receipt.payment_status == 'paid':
                        success_msg = f'✅ Balance FULLY PAID! Payment of ₦{total_payment_amount:,.2f} recorded for receipt {outstanding_receipt.receipt_number}. Receipt is now settled.'
                    else:
                        success_msg = f'✅ Payment of ₦{total_payment_amount:,.2f} recorded successfully for receipt {outstanding_receipt.receipt_number}. Remaining balance: ₦{outstanding_receipt.balance_remaining:,.2f}'

                    messages.success(request, success_msg)

                    # Return JSON for AJAX submissions, redirect for normal form submissions
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'message': success_msg,
                            'redirect_url': reverse('sale_success', kwargs={'receipt_id': outstanding_receipt.id}),
                            'receipt_id': outstanding_receipt.id,
                        })
                    return redirect('sale_success', receipt_id=outstanding_receipt.id)
                else:
                    logger.error("=" * 80)
                    logger.error("DEBT PAYMENT FAILED - Invalid formset")
                    logger.error(f"Formset errors: {payment_methods_formset.errors}")
                    logger.error("=" * 80)
                    error_msg = 'Invalid payment information. Please check the form and try again.'
                    messages.error(request, error_msg)
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'message': error_msg})
                    return redirect('customer_debt_dashboard')

            except Receipt.DoesNotExist:
                logger.error(f"Receipt not found with ID: {debt_payment_receipt_id}")
                error_msg = 'Receipt not found.'
                messages.error(request, error_msg)
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': error_msg})
                return redirect('customer_debt_dashboard')
            except Exception as e:
                logger.error("=" * 80)
                logger.error("DEBT PAYMENT EXCEPTION")
                logger.error(f"Error: {str(e)}")
                logger.error(f"Error type: {type(e).__name__}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                logger.error("=" * 80)
                error_msg = f'Error processing payment: {str(e)}'
                messages.error(request, error_msg)
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': error_msg})
                return redirect('customer_debt_dashboard')

        # Normal POS sale processing
        formset = SaleFormSet(request.POST, prefix='form')
        payment_form = PaymentForm(request.POST)
        delivery_form = DeliveryForm(request.POST)
        payment_methods_formset = PaymentMethodFormSet(request.POST, prefix='payment_method')
        customer_id = request.POST.get('customer')

        # Extract payment totals for validation
        total_sale_amount = Decimal(request.POST.get('total_price', '0'))
        payment_methods_total = Decimal('0')

        # Calculate total from payment methods
        total_forms = int(request.POST.get('payment_method-TOTAL_FORMS', 0))
        for i in range(total_forms):
            amount_field = f'payment_method-{i}-amount'
            if amount_field in request.POST:
                try:
                    amount_value = request.POST[amount_field]
                    if amount_value:
                        payment_methods_total += Decimal(amount_value)
                except (ValueError, TypeError):
                    pass

        # Check if partial payment is enabled
        enable_partial_payment = request.POST.get('enable_partial_payment') == 'true'

        # Validation form to ensure payment amounts match (skip if partial payment enabled)
        validation_form = PaymentValidationForm({
            'total_sale_amount': total_sale_amount,
            'payment_methods_total': payment_methods_total
        })

        # Detect all-gift sale (total is 0 – no payment required)
        all_gifts_sale = total_sale_amount == Decimal('0')

        # Skip payment validation if partial payment is enabled or all items are gifts
        if enable_partial_payment or all_gifts_sale:
            payment_validation_passed = True
        else:
            payment_validation_passed = validation_form.is_valid()

        # Always call is_valid() so Django populates cleaned_data on every form.
        # For all-gift sales the formset may be empty, so we override the result.
        payment_formset_is_valid = payment_methods_formset.is_valid()
        payment_formset_valid = all_gifts_sale or payment_formset_is_valid

        if (formset.is_valid() and payment_form.is_valid() and
                delivery_form.is_valid() and payment_formset_valid and
                payment_validation_passed):

            try:
                customer = get_object_or_404(Customer, id=customer_id) if customer_id else None

                # Validate stock availability before processing
                stock_errors = []
                for form in formset:
                    if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                        product = form.cleaned_data['product']
                        quantity = form.cleaned_data['quantity']

                        if quantity > product.quantity:
                            stock_errors.append(
                                f"{product.brand} - Size: {product.size} - Color: {product.color}: "
                                f"Requested {quantity}, but only {product.quantity} available"
                            )

                if stock_errors:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': False,
                            'message': 'Please adjust quantities to match available stock.',
                            'errors': stock_errors
                        })
                    else:
                        for error in stock_errors:
                            messages.error(request, error)
                        messages.error(request, "Please adjust quantities to match available stock.")
                        return render(request, 'sales/sell_product_multi_payment.html', {
                            'formset': formset,
                            'payment_form': payment_form,
                            'payment_methods_formset': payment_methods_formset,
                            'delivery_form': delivery_form,
                            'products': products,
                            'customers': customers,
                            'payment_method_choices': payment_method_choices
                        })

                # Validate payment methods
                valid_payment_methods = []
                total_payment_amount = Decimal('0')

                for form in payment_methods_formset:
                    if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                        if form.cleaned_data.get('payment_method') and form.cleaned_data.get('amount'):
                            valid_payment_methods.append(form.cleaned_data)
                            total_payment_amount += Decimal(str(form.cleaned_data['amount']))

                if not valid_payment_methods and not all_gifts_sale:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': False,
                            'message': 'At least one payment method is required.',
                            'errors': ['At least one payment method is required.']
                        })
                    else:
                        messages.error(request, "At least one payment method is required.")
                        return render(request, 'sales/sell_product_multi_payment.html', {
                            'formset': formset,
                            'payment_form': payment_form,
                            'payment_methods_formset': payment_methods_formset,
                            'delivery_form': delivery_form,
                            'products': products,
                            'customers': customers,
                            'payment_method_choices': payment_method_choices
                        })

                # Use database transaction to ensure consistency
                with transaction.atomic():
                    # Create core objects
                    receipt = Receipt.objects.create(
                        date=timezone.now(),
                        user=request.user,
                        customer=customer
                    )

                    # Process delivery
                    delivery = delivery_form.save(commit=False)
                    if delivery.delivery_option == 'delivery':
                        delivery.customer = customer
                        delivery.delivery_date = timezone.now()
                        delivery.save()
                        # Add delivery cost to receipt
                        receipt.delivery_cost = Decimal(str(delivery.delivery_cost))
                    else:
                        # For pickup, set cost to 0
                        delivery.delivery_cost = Decimal('0')
                        delivery.customer = customer
                        delivery.delivery_date = timezone.now()
                        delivery.save()
                        # Ensure receipt delivery cost is also 0
                        receipt.delivery_cost = Decimal('0')

                    # Create main payment record
                    payment = Payment.objects.create(
                        payment_status='pending',
                        discount_percentage=Decimal(str(payment_form.cleaned_data.get('discount_percentage', 0)))
                    )

                    # Process sales (with additional stock validation)
                    sale_items = []
                    subtotal = Decimal('0')

                    for idx, form in enumerate(formset):
                        if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                            product = form.cleaned_data['product']
                            quantity = form.cleaned_data['quantity']

                            # Refresh product from database to get latest stock
                            product.refresh_from_db()

                            if quantity > product.quantity:
                                raise ValidationError(
                                    f"Insufficient stock for {product.brand} - Size: {product.size} - Color: {product.color}. "
                                    f"Available: {product.quantity}, Requested: {quantity}"
                                )

                            # Create and save sale
                            sale = form.save(commit=False)
                            sale.product = product
                            sale.quantity = quantity
                            sale.customer = customer
                            sale.payment = payment
                            sale.delivery = delivery if delivery.delivery_option == 'delivery' else None
                            sale.receipt = receipt
                            sale.save()  # Triggers total_price calculation

                            # Check if this item is marked as gift (admin only)
                            is_gift = request.POST.get(f'is_gift_{idx}') == 'true'
                            if is_gift and request.user.is_superuser:
                                sale.is_gift = True
                                sale.gift_reason = request.POST.get(f'gift_reason_{idx}', '').strip()
                                sale.original_value = sale.total_price  # Store original price before making it ₦0
                                sale.total_price = Decimal('0')  # Gift items are ₦0
                                sale.save()
                                logger.info(f"Item marked as GIFT: {product.brand} - Original value: ₦{sale.original_value}")

                                # Update stock for gift items too
                                product.quantity -= quantity
                                product.save()

                                # Add sale item to list but don't add to subtotal (gifts are ₦0)
                                sale_items.append(sale)
                                subtotal += Decimal('0')
                            else:
                                # Normal sale - update stock and add to subtotal
                                product.quantity -= quantity
                                product.save()

                                # Add sale item to list and update subtotal
                                sale_items.append(sale)
                                subtotal += sale.total_price

                    # ============================================
                    # PRICING CALCULATION WITH TAX SUPPORT
                    # ============================================

                    # Step 1: Calculate items subtotal (products only, no delivery yet)
                    items_subtotal = subtotal  # This is sum of all sale items

                    # Step 2: Add delivery cost
                    delivery_cost = Decimal('0')
                    if delivery.delivery_option == 'delivery':
                        delivery_cost = Decimal(str(delivery.delivery_cost))

                    # Subtotal including delivery
                    subtotal_with_delivery = items_subtotal + delivery_cost

                    # Step 3: Apply discount (on subtotal including delivery)
                    discount_percentage = payment_form.cleaned_data.get('discount_percentage', 0)
                    discount_amount = subtotal_with_delivery * (Decimal(str(discount_percentage)) / 100) if discount_percentage else Decimal('0')
                    amount_after_discount = subtotal_with_delivery - discount_amount

                    # Step 4: Get loyalty redemption data (will apply after total is calculated)
                    loyalty_points_redeemed = int(request.POST.get('loyalty_points_redeemed', 0))
                    loyalty_discount_amount = Decimal(request.POST.get('loyalty_discount_amount', '0'))
                    loyalty_discount_applied = Decimal('0')

                    # Temporarily apply loyalty discount to calculate correct total
                    if loyalty_points_redeemed > 0 and loyalty_discount_amount > 0:
                        loyalty_discount_applied = loyalty_discount_amount
                        amount_after_discount -= loyalty_discount_applied

                    # Step 5: Calculate taxes
                    import json
                    from ..models import TaxConfiguration

                    active_taxes = TaxConfiguration.get_active_taxes()
                    total_tax_amount = Decimal('0')
                    total_exclusive_tax = Decimal('0')
                    total_inclusive_tax = Decimal('0')
                    tax_details = {}

                    # Taxable amount = items after all discounts (excluding delivery)
                    # We tax items only, not delivery cost
                    items_after_discount = amount_after_discount - delivery_cost

                    # Calculate each tax
                    for tax in active_taxes:
                        tax_amount = tax.calculate_tax_amount(items_after_discount)
                        total_tax_amount += tax_amount

                        # Track inclusive vs exclusive separately
                        if tax.calculation_method == 'inclusive':
                            total_inclusive_tax += tax_amount
                        else:
                            total_exclusive_tax += tax_amount

                        # Store tax details for receipt
                        tax_details[tax.code] = {
                            'name': tax.name,
                            'rate': float(tax.rate),
                            'amount': float(tax_amount),
                            'method': tax.calculation_method,
                            'type': tax.tax_type,
                            'taxable_amount': float(items_after_discount)
                        }

                    # Step 6: Calculate final total
                    # IMPORTANT:
                    # - Inclusive tax: Already in the price, so we DON'T add it
                    # - Exclusive tax: Added on top of price, so we DO add it
                    final_total = amount_after_discount + total_exclusive_tax

                    # Step 7: Update receipt with complete pricing breakdown
                    receipt.subtotal = items_subtotal  # Items only, before delivery and tax
                    receipt.tax_amount = total_tax_amount  # Total tax (both inclusive and exclusive)
                    receipt.tax_details = json.dumps(tax_details)  # Detailed tax breakdown
                    receipt.delivery_cost = delivery_cost
                    receipt.loyalty_discount_amount = loyalty_discount_applied  # Track loyalty discount
                    receipt.loyalty_points_redeemed = loyalty_points_redeemed  # Track points redeemed
                    receipt.total_with_delivery = final_total  # Grand total including exclusive tax

                    # Step 8: NOW actually redeem the loyalty points (after total is set)
                    if loyalty_points_redeemed > 0 and customer and loyalty_discount_applied > 0:
                        try:
                            from ..loyalty_utils import apply_loyalty_discount as apply_loyalty_util
                            loyalty_result = apply_loyalty_util(receipt, loyalty_points_redeemed, request.user)

                            if loyalty_result['success']:
                                logger.info(f"Successfully redeemed {loyalty_points_redeemed} loyalty points "
                                          f"(₦{loyalty_discount_applied}) for receipt {receipt.receipt_number}")
                            else:
                                logger.error(f"Failed to redeem loyalty points: {loyalty_result.get('error')}")
                                # Rollback the discount if redemption failed
                                receipt.loyalty_discount_amount = Decimal('0')
                                receipt.loyalty_points_redeemed = 0
                        except Exception as e:
                            logger.error(f"Error redeeming loyalty points for receipt {receipt.receipt_number}: {e}")
                            # Rollback the discount if redemption failed
                            receipt.loyalty_discount_amount = Decimal('0')
                            receipt.loyalty_points_redeemed = 0

                    receipt.save()

                    # ============================================
                    # PARTIAL PAYMENT HANDLING
                    # ============================================
                    enable_partial_payment = request.POST.get('enable_partial_payment') == 'true'

                    # Calculate total amount from all payment methods
                    payment_methods_total = sum([Decimal(str(method['amount'])) for method in valid_payment_methods])

                    if enable_partial_payment:
                        # Partial payment mode - use payment methods total as deposit
                        amount_paying = payment_methods_total

                        # Validate partial payment amount
                        if amount_paying >= final_total:
                            # Paying full amount or more - treat as full payment
                            receipt.payment_status = 'paid'
                            receipt.amount_paid = final_total
                            receipt.balance_remaining = Decimal('0')
                            logger.info(f"Partial payment enabled but full amount paid: ₦{amount_paying}")
                        elif amount_paying <= 0:
                            # No payment made - mark as pending
                            receipt.payment_status = 'pending'
                            receipt.amount_paid = Decimal('0')
                            receipt.balance_remaining = final_total
                            logger.info(f"No initial payment - receipt marked as pending")
                        else:
                            # Actual partial payment (deposit)
                            receipt.payment_status = 'partial'
                            receipt.amount_paid = amount_paying
                            receipt.balance_remaining = final_total - amount_paying

                            # Create initial partial payment record for each payment method
                            for method_data in valid_payment_methods:
                                PartialPayment.objects.create(
                                    receipt=receipt,
                                    amount=Decimal(str(method_data['amount'])),
                                    payment_method=method_data['payment_method'],
                                    notes=f"Initial deposit payment - Total deposit: ₦{amount_paying}, Balance: ₦{receipt.balance_remaining}",
                                    received_by=request.user
                                )
                            logger.info(f"Partial payment (deposit) created: Paid ₦{amount_paying}, Remaining ₦{receipt.balance_remaining}")

                        receipt.save()
                    else:
                        # Full payment mode - payment methods total should match final total
                        receipt.payment_status = 'paid'
                        receipt.amount_paid = final_total
                        receipt.balance_remaining = Decimal('0')
                        receipt.save()

                    # Log pricing breakdown for debugging
                    logger.info(f"Receipt {receipt.receipt_number} - Pricing breakdown:")
                    logger.info(f"  Items subtotal: ₦{items_subtotal}")
                    logger.info(f"  Delivery: ₦{delivery_cost}")
                    logger.info(f"  Discount: -₦{discount_amount}")
                    logger.info(f"  Loyalty discount: -₦{loyalty_discount_applied}")
                    logger.info(f"  Inclusive tax: ₦{total_inclusive_tax} (in price)")
                    logger.info(f"  Exclusive tax: ₦{total_exclusive_tax} (added)")
                    logger.info(f"  Grand total: ₦{final_total}")
                    logger.info(f"  Payment status: {receipt.payment_status}")

                    # Update payment total
                    payment.total_amount = final_total
                    payment.discount_amount = discount_amount
                    payment.loyalty_discount_amount = loyalty_discount_applied
                    payment.save()

                    # Create individual payment method records
                    payment_method_summaries = []
                    for method_data in valid_payment_methods:
                        payment_method = PaymentMethod.objects.create(
                            payment=payment,
                            payment_method=method_data['payment_method'],
                            amount=Decimal(str(method_data['amount'])),
                            reference_number=method_data.get('reference_number', ''),
                            notes=method_data.get('notes', ''),
                            status='completed',
                            # Assuming immediate completion, can be 'pending' if verification needed
                            confirmed_date=timezone.now(),
                            processed_by=request.user
                        )
                        payment_method_summaries.append({
                            'method': payment_method.get_payment_method_display(),
                            'amount': payment_method.amount,
                            'reference': payment_method.reference_number or 'N/A'
                        })

                        # ============================================
                        # STORE CREDIT PAYMENT HANDLING
                        # ============================================
                        if method_data['payment_method'] == 'store_credit':
                            from ..models import StoreCredit, StoreCreditUsage

                            if not customer:
                                raise ValidationError("Customer must be selected to use store credit")

                            # Get customer's active store credits
                            available_credits = StoreCredit.objects.filter(
                                customer=customer,
                                is_active=True,
                                remaining_balance__gt=0
                            ).order_by('issued_date')  # Use oldest credits first (FIFO)

                            # Calculate total available balance
                            total_available = sum([credit.remaining_balance for credit in available_credits])

                            # Validate sufficient balance
                            credit_amount = Decimal(str(method_data['amount']))
                            if credit_amount > total_available:
                                raise ValidationError(
                                    f"Insufficient store credit. Available: ₦{total_available:.2f}, "
                                    f"Requested: ₦{credit_amount:.2f}"
                                )

                            # Deduct from store credits (FIFO - oldest first)
                            remaining_to_deduct = credit_amount
                            for credit in available_credits:
                                if remaining_to_deduct <= 0:
                                    break

                                # Calculate how much to deduct from this credit
                                deduct_amount = min(credit.remaining_balance, remaining_to_deduct)

                                # Create usage record
                                StoreCreditUsage.objects.create(
                                    store_credit=credit,
                                    receipt=receipt,
                                    amount_used=deduct_amount,
                                    used_by=request.user
                                )

                                # Deduct from remaining amount
                                remaining_to_deduct -= deduct_amount

                                logger.info(
                                    f"Store credit used: {credit.credit_number} - "
                                    f"Amount: ₦{deduct_amount:.2f}, "
                                    f"Remaining in credit: ₦{credit.remaining_balance - deduct_amount:.2f}"
                                )

                            logger.info(f"Total store credit applied: ₦{credit_amount:.2f}")

                    # Finalize payment status
                    payment.refresh_from_db()
                    payment.update_payment_status()
                    payment.save()

                    # Log sale creation
                    sale_description = f'Sale created - Receipt #{receipt.receipt_number} - Total: ₦{final_total:.2f}'
                    if customer:
                        sale_description += f' - Customer: {customer.name}'
                    ActivityLog.log_activity(
                        user=request.user,
                        action='sale_create',
                        description=sale_description,
                        model_name='Receipt',
                        object_id=receipt.id,
                        object_repr=f'Receipt #{receipt.receipt_number}',
                        extra_data={
                            'total_amount': float(final_total),
                            'items_count': len(sale_items),
                            'tax_amount': float(total_tax_amount),
                            'discount_amount': float(discount_amount)
                        },
                        request=request
                    )

                    # Prepare success message with tax breakdown
                    payment_details = "; ".join([
                        f"{method['method']}: ₦{method['amount']:.2f} ({method['reference']})"
                        for method in payment_method_summaries
                    ])

                    # Build tax summary for message
                    tax_message = ""
                    if total_tax_amount > 0:
                        tax_parts = []
                        if total_inclusive_tax > 0:
                            tax_parts.append(f"₦{total_inclusive_tax:.2f} incl.")
                        if total_exclusive_tax > 0:
                            tax_parts.append(f"₦{total_exclusive_tax:.2f} excl.")
                        tax_message = f", Tax: {' + '.join(tax_parts)} = ₦{total_tax_amount:.2f}"

                    success_message = (
                        f"Sale completed successfully! "
                        f"Total: ₦{final_total:.2f}"
                        f"{f', Discount: ₦{discount_amount:.2f}' if discount_amount > 0 else ''}"
                        f"{tax_message}. "
                        f"Payment methods: {payment_details}"
                    )

                    # Handle successful transaction based on request type
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        # AJAX request - return JSON response
                        return JsonResponse({
                            'success': True,
                            'message': success_message,
                            'redirect_url': reverse('sale_success', kwargs={'receipt_id': receipt.id}),
                            'receipt_id': receipt.id
                        })
                    else:
                        # Regular form submission - redirect normally
                        messages.success(request, success_message)
                        return redirect('sale_success', receipt_id=receipt.id)

            except ValidationError as ve:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': str(ve),
                        'errors': [str(ve)]
                    })
                else:
                    messages.error(request, str(ve))
            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': f"An error occurred: {str(e)}",
                        'errors': [f"An error occurred: {str(e)}"]
                    })
                else:
                    messages.error(request, f"An error occurred: {str(e)}")
        else:
            # Form validation failed
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                # Collect all error messages for AJAX response
                error_messages = []

                if formset.errors:
                    error_messages.append("Product form errors found")
                    for i, error_dict in enumerate(formset.errors):
                        if error_dict:
                            field_errors = []
                            for field, errors in error_dict.items():
                                if field != 'DELETE':
                                    error_strings = [str(error) for error in errors]
                                    field_errors.append(f"{field}: {', '.join(error_strings)}")

                            if field_errors:
                                error_messages.append(f"Product row {i + 1}: {', '.join(field_errors)}")

                if payment_form.errors:
                    form_errors = []
                    for field, errors in payment_form.errors.items():
                        error_strings = [str(error) for error in errors]
                        form_errors.append(f"{field}: {', '.join(error_strings)}")
                    error_messages.append(f"Payment errors: {', '.join(form_errors)}")

                if payment_methods_formset.errors:
                    error_messages.append("Payment method errors found")
                    for i, error_dict in enumerate(payment_methods_formset.errors):
                        if error_dict:
                            field_errors = []
                            for field, errors in error_dict.items():
                                if field != 'DELETE':
                                    error_strings = [str(error) for error in errors]
                                    field_errors.append(f"{field}: {', '.join(error_strings)}")

                            if field_errors:
                                error_messages.append(f"Payment method {i + 1}: {', '.join(field_errors)}")

                if delivery_form.errors:
                    form_errors = []
                    for field, errors in delivery_form.errors.items():
                        error_strings = [str(error) for error in errors]
                        form_errors.append(f"{field}: {', '.join(error_strings)}")
                    error_messages.append(f"Delivery errors: {', '.join(form_errors)}")

                # Only show validation errors if not in partial payment mode
                if not enable_partial_payment and not validation_form.is_valid():
                    validation_errors = []
                    for field, errors in validation_form.errors.items():
                        error_strings = [str(error) for error in errors]
                        validation_errors.append(f"{field}: {', '.join(error_strings)}")
                    error_messages.extend(validation_errors)

                return JsonResponse({
                    'success': False,
                    'message': 'Please fix the following errors and try again:',
                    'errors': error_messages
                })
            else:
                # Regular form submission - show messages and re-render form
                error_messages = []

                if formset.errors:
                    error_messages.append("Product form errors found")
                    for i, error_dict in enumerate(formset.errors):
                        if error_dict:
                            field_errors = []
                            for field, errors in error_dict.items():
                                if field != 'DELETE':
                                    error_strings = [str(error) for error in errors]
                                    field_errors.append(f"{field}: {', '.join(error_strings)}")

                            if field_errors:
                                error_messages.append(f"Product row {i + 1}: {', '.join(field_errors)}")

                if payment_form.errors:
                    form_errors = []
                    for field, errors in payment_form.errors.items():
                        error_strings = [str(error) for error in errors]
                        form_errors.append(f"{field}: {', '.join(error_strings)}")
                    error_messages.append(f"Payment errors: {', '.join(form_errors)}")

                if payment_methods_formset.errors:
                    error_messages.append("Payment method errors found")
                    for i, error_dict in enumerate(payment_methods_formset.errors):
                        if error_dict:
                            field_errors = []
                            for field, errors in error_dict.items():
                                if field != 'DELETE':
                                    error_strings = [str(error) for error in errors]
                                    field_errors.append(f"{field}: {', '.join(error_strings)}")

                            if field_errors:
                                error_messages.append(f"Payment method {i + 1}: {', '.join(field_errors)}")

                if delivery_form.errors:
                    form_errors = []
                    for field, errors in delivery_form.errors.items():
                        error_strings = [str(error) for error in errors]
                        form_errors.append(f"{field}: {', '.join(error_strings)}")
                    error_messages.append(f"Delivery errors: {', '.join(form_errors)}")

                # Only show validation errors if not in partial payment mode
                if not enable_partial_payment and not validation_form.is_valid():
                    validation_errors = []
                    for field, errors in validation_form.errors.items():
                        error_strings = [str(error) for error in errors]
                        validation_errors.append(f"{field}: {', '.join(error_strings)}")
                    error_messages.extend(validation_errors)

                for error in error_messages:
                    messages.error(request, error)

    else:
        formset = SaleFormSet(prefix='form')
        payment_form = PaymentForm()
        payment_methods_formset = PaymentMethodFormSet(prefix='payment_method')
        delivery_form = DeliveryForm()

    # Check if this is a debt payment from customer debt dashboard
    customer_id_for_debt = request.GET.get('customer_id', '')
    receipt_id_for_debt = request.GET.get('receipt_id', '')

    # Fetch debt information if receipt_id is provided
    debt_info = None
    if receipt_id_for_debt:
        try:
            outstanding_receipt = Receipt.objects.get(id=receipt_id_for_debt)
            # Get partial payment history
            payment_history = PartialPayment.objects.filter(
                receipt=outstanding_receipt
            ).order_by('payment_date')

            debt_info = {
                'receipt': outstanding_receipt,
                'receipt_number': outstanding_receipt.receipt_number,
                'total_amount': outstanding_receipt.amount_paid + outstanding_receipt.balance_remaining,
                'amount_paid': outstanding_receipt.amount_paid,
                'balance_remaining': outstanding_receipt.balance_remaining,
                'customer': outstanding_receipt.customer,
                'payment_history': list(payment_history.values(
                    'amount', 'payment_method', 'payment_date', 'received_by__username'
                )),
                'original_date': outstanding_receipt.date,
            }
        except Receipt.DoesNotExist:
            debt_info = None

    return render(request, 'sales/sell_product.html', {
        'formset': formset,
        'payment_form': payment_form,
        'payment_methods_formset': payment_methods_formset,
        'delivery_form': delivery_form,
        'products': products,
        'customers': customers,
        'payment_method_choices': payment_method_choices,
        'active_taxes': active_taxes,
        # Debt payment information
        'preselect_customer_id': customer_id_for_debt,
        'debt_info': debt_info,
        'is_debt_payment': bool(receipt_id_for_debt),
    })



@login_required(login_url='login')
def sale_success(request, receipt_id):
    receipt = get_object_or_404(Receipt, id=receipt_id)
    payment_history = PartialPayment.objects.filter(receipt=receipt).order_by('payment_date')
    store_config = StoreConfiguration.get_active_config()

    return render(request, 'sales/sale_success.html', {
        'receipt': receipt,
        'payment_history': payment_history,
        'currency_symbol': store_config.currency_symbol,
    })




@login_required(login_url='login')
def payment_details(request, payment_id):
    """View to show detailed payment breakdown"""
    payment = get_object_or_404(Payment, id=payment_id)
    payment_methods = payment.payment_methods.all()

    context = {
        'payment': payment,
        'payment_methods': payment_methods,
        'sales': payment.sale_set.all(),
    }

    return render(request, 'sales/payment_details.html', context)


@login_required(login_url='login')
def update_payment_status(request, payment_method_id):
    """Update individual payment method status (for pending payments)"""
    payment_method = get_object_or_404(PaymentMethod, id=payment_method_id)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        reference = request.POST.get('reference_number', '')
        notes = request.POST.get('notes', '')

        if new_status in dict(PaymentMethod.PAYMENT_STATUS):
            old_status = payment_method.status
            payment_method.status = new_status
            payment_method.reference_number = reference
            payment_method.notes = notes

            if new_status == 'completed':
                payment_method.confirmed_date = timezone.now()

            payment_method.save()

            # Log the status change
            from ..models import PaymentLog
            PaymentLog.objects.create(
                payment_method=payment_method,
                action='status_update',
                previous_status=old_status,
                new_status=new_status,
                notes=f"Updated by {request.user.username}. {notes}",
                user=request.user
            )

            messages.success(request, f"Payment method status updated to {payment_method.get_status_display()}")
        else:
            messages.error(request, "Invalid status provided")

    return redirect('payment_details', payment_id=payment_method.payment.id)


def customer_display(request):
    return render(request, 'sales/customer_display.html')

@login_required(login_url='login')
def delivered_items_view(request):
    status_filter = request.GET.get('status', 'all')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    # Filter deliveries based on status
    deliveries = Delivery.objects.select_related('customer').all()
    if status_filter == 'pending':
        deliveries = deliveries.filter(delivery_status='pending')
    elif status_filter == 'delivered':
        deliveries = deliveries.filter(delivery_status='delivered')

    # Filter by date range if provided
    if start_date and end_date:
        try:
            deliveries = deliveries.filter(delivery_date__range=[start_date, end_date])
        except ValueError:
            messages.error(request, "Invalid date format. Please use YYYY-MM-DD.")

    # Handle status update
    if request.method == 'POST':
        delivery_id = request.POST.get('delivery_id')
        new_status = request.POST.get('delivery_status')
        delivery = Delivery.objects.get(id=delivery_id)
        delivery.delivery_status = new_status
        delivery.save()
        messages.success(request, "Delivery status updated successfully!")
        return redirect('delivered_items')

    return render(request, 'delivery/delivered_items.html', {
        'deliveries': deliveries,
        'status_filter': status_filter,
        'start_date': start_date,
        'end_date': end_date,
    })



def receipt_list(request):
    # Get all filter parameters from GET request
    search_query = request.GET.get('search', '')
    customer_filter = request.GET.get('customer', '')
    payment_status_filter = request.GET.get('payment_status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    amount_min = request.GET.get('amount_min', '')
    amount_max = request.GET.get('amount_max', '')
    sort_by = request.GET.get('sort_by', '-date')  # Default sort by date descending

    # Start with all receipts, prefetch related data for efficiency
    receipts = Receipt.objects.prefetch_related('sales', 'customer', 'partial_payments').order_by('-date')

    # Filter by payment status
    if payment_status_filter:
        receipts = receipts.filter(payment_status=payment_status_filter)

    # Apply filters
    if search_query:
        # Search in receipt number, customer name, or customer phone
        receipts = receipts.filter(
            Q(receipt_number__icontains=search_query) |
            Q(customer__name__icontains=search_query) |
            Q(customer__phone_number__icontains=search_query)
        )

    if customer_filter:
        receipts = receipts.filter(customer__name__icontains=customer_filter)

    # Date filtering
    if date_from:
        try:
            date_from_parsed = datetime.strptime(date_from, '%Y-%m-%d')
            receipts = receipts.filter(date__date__gte=date_from_parsed.date())
        except ValueError:
            pass  # Invalid date format, ignore filter

    if date_to:
        try:
            date_to_parsed = datetime.strptime(date_to, '%Y-%m-%d')
            receipts = receipts.filter(date__date__lte=date_to_parsed.date())
        except ValueError:
            pass  # Invalid date format, ignore filter

    receipt_data = []

    for receipt in receipts:
        total_amount = Decimal('0.00')
        customer_name = "N/A"

        # Safely get customer name
        if hasattr(receipt, 'customer') and receipt.customer:
            customer_name = receipt.customer.name
        elif receipt.customer_id:
            try:
                customer_name = receipt.customer.name
            except AttributeError:
                customer_name = "Unknown Customer"

        # Calculate total amount including delivery cost
        if hasattr(receipt, 'sales'):
            for sale in receipt.sales.all():
                if sale and hasattr(sale, 'total_price') and sale.total_price:
                    total_amount += Decimal(str(sale.total_price))

        # Add delivery cost if exists
        if receipt.delivery_cost:
            total_amount += Decimal(str(receipt.delivery_cost))

        receipt_info = {
            'receipt': receipt,
            'total_amount': total_amount.quantize(Decimal('0.00')),
            'customer_name': customer_name,
            'payment_status': receipt.payment_status,
            'partial_payment_count': receipt.partial_payments.count(),
            'amount_paid': receipt.amount_paid,
            'balance_remaining': receipt.balance_remaining,
        }

        receipt_data.append(receipt_info)

    # Apply amount filtering after calculating totals
    if amount_min:
        try:
            min_amount = Decimal(amount_min)
            receipt_data = [r for r in receipt_data if r['total_amount'] >= min_amount]
        except (ValueError, TypeError):
            pass

    if amount_max:
        try:
            max_amount = Decimal(amount_max)
            receipt_data = [r for r in receipt_data if r['total_amount'] <= max_amount]
        except (ValueError, TypeError):
            pass

    # Apply sorting
    if sort_by == 'receipt_number':
        receipt_data.sort(key=lambda x: x['receipt']['receipt_number'])
    elif sort_by == '-receipt_number':
        receipt_data.sort(key=lambda x: x['receipt']['receipt_number'], reverse=True)
    elif sort_by == 'customer':
        receipt_data.sort(key=lambda x: x['customer_name'])
    elif sort_by == '-customer':
        receipt_data.sort(key=lambda x: x['customer_name'], reverse=True)
    elif sort_by == 'amount':
        receipt_data.sort(key=lambda x: x['total_amount'])
    elif sort_by == '-amount':
        receipt_data.sort(key=lambda x: x['total_amount'], reverse=True)
    elif sort_by == 'date':
        receipt_data.sort(key=lambda x: x['receipt'].date)
    else:  # Default: -date
        receipt_data.sort(key=lambda x: x['receipt'].date, reverse=True)

    # Get unique customers for dropdown filter
    customers = Customer.objects.filter(receipt__isnull=False).distinct().order_by('name')

    # Calculate summary statistics
    total_receipts = len(receipt_data)
    total_revenue = sum(r['total_amount'] for r in receipt_data)

    # Quick filter date calculations
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    context = {
        'receipt_data': receipt_data,
        'search_query': search_query,
        'customer_filter': customer_filter,
        'payment_status_filter': payment_status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'amount_min': amount_min,
        'amount_max': amount_max,
        'sort_by': sort_by,
        'customers': customers,
        'total_receipts': total_receipts,
        'total_revenue': total_revenue,
        'today': today.strftime('%Y-%m-%d'),
        'week_ago': week_ago.strftime('%Y-%m-%d'),
        'month_ago': month_ago.strftime('%Y-%m-%d'),
    }

    return render(request, 'receipt/receipt_list.html', context)


@login_required(login_url='login')
def receipt_detail(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)

    # Log receipt view
    ActivityLog.log_activity(
        user=request.user,
        action='receipt_view',
        description=f'Viewed receipt #{receipt.receipt_number}',
        model_name='Receipt',
        object_id=receipt.id,
        object_repr=f'Receipt #{receipt.receipt_number}',
        request=request
    )

    # Fixed: Remove 'payment__delivery' from select_related since delivery is related to Sale, not Payment
    sales = receipt.sales.select_related('product', 'payment', 'delivery').prefetch_related(
        'payment__payment_methods'
    ).all()

    payment = sales.first().payment if sales.exists() else None
    customer_name = receipt.customer.name if receipt.customer else "No customer"
    user = receipt.user

    # Flag: does this receipt contain any gifted items?
    has_gifts = any(sale.is_gift for sale in sales)

    # Total item-level discounts (gift items have no discount — they're free)
    total_item_discount = sum(
        (sale.discount_amount or Decimal('0.00')) for sale in sales if not sale.is_gift
    )

    # Total before any discount (exclude gift items — they're worth ₦0 on this receipt)
    total_price_before_discount = sum(
        sale.product.selling_price * sale.quantity for sale in sales if not sale.is_gift
    )

    # Bill-level discount
    total_bill_discount = payment.discount_amount if payment else Decimal('0.00')

    # Get delivery cost from the receipt or from sales delivery
    delivery_cost = receipt.delivery_cost or Decimal('0.00')

    # If receipt doesn't have delivery_cost, get it from the first sale's delivery
    if not delivery_cost and sales.exists():
        first_sale_delivery = sales.first().delivery
        if first_sale_delivery:
            delivery_cost = first_sale_delivery.delivery_cost or Decimal('0.00')

    # Final total (after discounts + delivery)
    final_total = payment.total_amount if payment else Decimal('0.00')

    # Total paid via all completed methods
    if payment:
        total_paid = sum(
            pm.amount for pm in payment.payment_methods.filter(status='completed')
        )
        payment_methods = payment.payment_methods.all()
    else:
        total_paid = Decimal('0.00')
        payment_methods = []

    change_amount = max(total_paid - final_total, Decimal('0.00'))

    # Get store configuration
    store_config = StoreConfiguration.get_active_config()

    # Get delivery details
    delivery = None
    if sales.exists():
        first_sale_delivery = sales.first().delivery
        if first_sale_delivery:
            delivery = first_sale_delivery

    # Get partial payments for balance settlements
    partial_payments = list(PartialPayment.objects.filter(receipt=receipt).order_by('payment_date'))

    # Get loyalty info
    loyalty_info = None
    if receipt.customer and hasattr(receipt.customer, 'loyalty_account'):
        try:
            config = LoyaltyConfiguration.get_active_config()
            if config and config.is_active:
                loyalty_transaction = LoyaltyTransaction.objects.filter(
                    loyalty_account__customer=receipt.customer,
                    receipt=receipt
                ).order_by('-created_at').first()

                if loyalty_transaction:
                    loyalty_info = {
                        'program_name': config.program_name,
                        'points_earned': loyalty_transaction.points,
                        'previous_balance': loyalty_transaction.balance_after - loyalty_transaction.points,
                        'new_balance': loyalty_transaction.balance_after,
                        'redeemable_value': receipt.customer.loyalty_account.get_redeemable_value(),
                        'points_threshold': config.minimum_points_for_redemption,
                        'discount_percentage': config.maximum_discount_percentage,
                    }
        except Exception as e:
            logger.error(f"Error fetching loyalty info: {e}")

    # Subtotal from sales (gift items count as ₦0)
    subtotal_amount = sum(
        Decimal('0') if sale.is_gift else sale.total_price for sale in sales
    )

    return render(request, 'receipt/receipt_detail.html', {
        'receipt': receipt,
        'sales': sales,
        'payment': payment,
        'customer_name': customer_name,
        'user': user,
        'total_item_discount': total_item_discount,
        'total_bill_discount': total_bill_discount,
        'total_price_before_discount': total_price_before_discount,
        'subtotal_amount': subtotal_amount,
        'delivery_cost': delivery_cost,
        'final_total': final_total,
        'total_paid': total_paid,
        'change_amount': change_amount,
        'payment_methods': payment_methods,
        'store_config': store_config,
        'store_name': store_config.store_name,
        'store_phone': store_config.phone,
        'store_email': store_config.email,
        'currency_symbol': store_config.currency_symbol,
        'delivery': delivery,
        'loyalty_info': loyalty_info,
        'partial_payments': partial_payments,
        'has_gifts': has_gifts,
    })


@login_required(login_url='login')
def print_pos_receipt(request, pk):
    """Print a receipt directly to the default Windows ESC/POS thermal printer."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    receipt = get_object_or_404(Receipt, pk=pk)

    try:
        from escpos.printer import Win32Raw
        import win32print
        import json as _json

        sales = receipt.sales.select_related('product', 'payment').prefetch_related(
            'payment__payment_methods'
        ).all()
        payment = sales.first().payment if sales.exists() else None
        customer_name = receipt.customer.name if receipt.customer else None
        store_config = StoreConfiguration.get_active_config()
        partial_payments = list(PartialPayment.objects.filter(receipt=receipt).order_by('payment_date'))

        # Resolve receipt printer: task mapping → OS default
        receipt_mapping_printer = PrinterTaskMapping.get_printer_for_task('receipt_pos')
        if receipt_mapping_printer:
            printer_name = receipt_mapping_printer.system_printer_name
        else:
            printer_name = win32print.GetDefaultPrinter()
        p = Win32Raw(printer_name)
        cs = store_config.currency_symbol or '₦'
        W = 42  # receipt width in chars

        def line(text=''):
            p.text(text + '\n')

        def divider(char='-'):
            p.text(char * W + '\n')

        def row(left, right, width=W):
            gap = width - len(left) - len(right)
            p.text(left + ' ' * max(1, gap) + right + '\n')

        # ── Timestamp (right-aligned) ──
        p.set(align='right', bold=False, width=1, height=1)
        line(receipt.date.strftime('%m/%d/%Y, %I:%M %p'))

        # ── Store name ──
        p.set(align='center', bold=True, width=2, height=2)
        line(store_config.store_name)

        # ── Store details ──
        p.set(align='center', bold=False, width=1, height=1)
        line(store_config.address_line_1)
        if store_config.address_line_2:
            line(store_config.address_line_2)
        line(f'Tel: {store_config.phone}')
        line(store_config.email)

        # ── Title ──
        p.set(align='center', bold=True, width=1, height=1)
        divider('-')
        title = 'DEPOSIT RECEIPT' if receipt.payment_status == 'partial' else 'SALES RECEIPT'
        line(title)
        divider('-')

        # ── Receipt info ──
        p.set(align='left', bold=False, width=1, height=1)
        line(f'Date: {receipt.date.strftime("%m/%d/%Y %I:%M %p")}')
        line(f'Sale ID: {receipt.receipt_number}')
        line(f'Employee: {receipt.user.username if receipt.user else "N/A"}')
        if customer_name:
            line(f'Customer: {customer_name}')
            if receipt.customer and receipt.customer.phone_number:
                line(f'Phone: {receipt.customer.phone_number}')

        # ── Items header ──
        p.set(align='left', bold=True, width=1, height=1)
        divider('-')
        # Columns: Item(20) Price(10) Qty(4) Total(8)
        hdr = f'{"Item Name":<20}{"Price":>9} {"Qty":>3} {"Total":>7}'
        line(hdr)
        divider('-')

        # ── Items ──
        p.set(align='left', bold=False, width=1, height=1)
        for sale in sales:
            name  = str(sale.product.brand or '')[:20]
            price = f'{cs}{float(sale.product.selling_price):.2f}'
            qty   = str(sale.quantity)
            total = f'{cs}{float(sale.total_price):.2f}'
            line(f'{name:<20}{price:>9} {qty:>3} {total:>7}')

        divider('-')

        # ── Summary ──
        subtotal = sum(float(s.total_price) for s in sales)
        row('Subtotal:', f'{cs}{subtotal:.2f}')

        if receipt.tax_amount and receipt.tax_amount > 0:
            try:
                tax_data = _json.loads(receipt.tax_details)
                for code, ti in tax_data.items():
                    label = f'{ti["name"]} ({ti["rate"]}% {ti["method"].capitalize()}):'
                    row(label[:W - 12], f'{cs}{float(ti["amount"]):.2f}')
            except Exception:
                pass

        if receipt.delivery_cost and receipt.delivery_cost > 0:
            row('Delivery:', f'+{cs}{float(receipt.delivery_cost):.2f}')

        divider('=')
        p.set(align='left', bold=True, width=1, height=1)
        final_total = float(payment.total_amount) if payment else subtotal
        row('Total:', f'{cs}{final_total:.2f}')
        divider('=')

        # ── Payment type ──
        p.set(align='left', bold=False, width=1, height=1)
        if payment:
            for pm in payment.payment_methods.all():
                row('Payment Type:', pm.get_payment_method_display())

        if receipt.payment_status == 'partial':
            row('Deposit Paid:', f'{cs}{float(receipt.amount_paid):.2f}')
            p.set(align='left', bold=True, width=1, height=1)
            row('Balance Due:', f'{cs}{float(receipt.balance_remaining):.2f}')
            p.set(align='left', bold=False, width=1, height=1)

        # ── Payment History ──
        if partial_payments:
            divider('-')
            p.set(align='center', bold=True, width=1, height=1)
            if receipt.payment_status == 'paid' and len(partial_payments) > 1:
                line('BALANCE SETTLEMENT - PAYMENT HISTORY')
            else:
                line('PAYMENT HISTORY')
            p.set(align='left', bold=False, width=1, height=1)
            for i, pp in enumerate(partial_payments):
                is_last = (i == len(partial_payments) - 1)
                if is_last and receipt.payment_status == 'paid' and len(partial_payments) > 1:
                    label = f'Balance Payment ({pp.payment_date.strftime("%m/%d/%Y")}):'
                else:
                    label = f'Deposit #{i + 1} ({pp.payment_date.strftime("%m/%d/%Y")}):'
                row(label, f'{cs}{float(pp.amount):.2f}')
            if receipt.payment_status == 'paid':
                p.set(align='left', bold=True, width=1, height=1)
                row('Total Paid:', f'{cs}{float(receipt.amount_paid):.2f}')
                p.set(align='left', bold=False, width=1, height=1)

        # ── Loyalty Status ──
        if receipt.customer and hasattr(receipt.customer, 'loyalty_account'):
            try:
                lc = LoyaltyConfiguration.get_active_config()
                if lc and lc.is_active:
                    acc = receipt.customer.loyalty_account
                    divider('-')
                    p.set(align='center', bold=True, width=1, height=1)
                    line('LOYALTY STATUS')
                    p.set(align='center', bold=False, width=1, height=1)
                    line(f'Progress: {acc.current_balance}/{lc.minimum_points_for_redemption} to {lc.maximum_discount_percentage:.2f}% OFF')
            except Exception:
                pass

        # ── Footer ──
        divider('-')
        p.set(align='center', bold=False, width=1, height=1)
        if store_config.receipt_footer_text:
            line(store_config.receipt_footer_text)
        else:
            line('Change/Return Only - No Cash Refunds')
            line('Thank you for shopping with us!')

        p.ln(4)
        p.cut()
        p.close()

        return JsonResponse({'success': True, 'message': f'Printed to: {printer_name}'})

    except Exception as exc:
        import traceback
        logger.error(f'ESC/POS print error: {traceback.format_exc()}')
        return JsonResponse({'success': False, 'message': str(exc)}, status=500)


@login_required(login_url='login')
def send_receipt_email(request, pk):
    logger.info(f"📧 Starting email send process for receipt {pk}")

    receipt = get_object_or_404(Receipt, pk=pk)
    sales = receipt.sales.select_related('product').all()

    if not receipt.customer or not receipt.customer.email:
        logger.warning(f"⚠️ Receipt {pk} has no customer email")
        messages.error(request, "❌ Customer does not have an email address.")
        return redirect('receipt_list')

    logger.info(f"📧 Sending email to: {receipt.customer.email} for receipt {receipt.receipt_number}")

    payment = sales.first().payment if sales.exists() and hasattr(sales.first(), 'payment') else None

    has_gifts = any(sale.is_gift for sale in sales)
    total_item_discount = sum(
        (sale.discount_amount or Decimal('0.00')) * sale.quantity
        for sale in sales if not sale.is_gift
    )
    total_price_before_discount = sum(
        sale.product.selling_price * sale.quantity
        for sale in sales if not sale.is_gift
    )
    subtotal_amount = sum(
        Decimal('0') if sale.is_gift else sale.total_price for sale in sales
    )
    total_bill_discount = payment.discount_amount if payment else Decimal('0.00')
    final_total = payment.total_amount if payment else Decimal('0.00')

    # ✅ Generate logo URL using `request` here — inside the view
    domain = get_current_site(request).domain
    protocol = 'https' if request.is_secure() else 'http'
    logo_url = f'{protocol}://{domain}{static("img/Wlogo.png")}'

    # Get loyalty points information if customer has loyalty account
    loyalty_info = None
    try:
        from ..loyalty_utils import get_customer_loyalty_summary
        config = LoyaltyConfiguration.get_active_config()
        if config.is_active and receipt.customer:
            loyalty_summary = get_customer_loyalty_summary(receipt.customer)
            if loyalty_summary['has_account']:
                # Get the loyalty transaction for this receipt
                loyalty_transaction = LoyaltyTransaction.objects.filter(
                    receipt=receipt,
                    transaction_type='earned'
                ).first()

                if loyalty_transaction:
                    loyalty_info = {
                        'program_name': config.program_name,
                        'points_earned': loyalty_transaction.points,
                        'previous_balance': loyalty_transaction.balance_after - loyalty_transaction.points,
                        'new_balance': loyalty_transaction.balance_after,
                        'redeemable_value': receipt.customer.loyalty_account.get_redeemable_value(),
                        'points_threshold': config.minimum_points_for_redemption,
                        'discount_percentage': config.maximum_discount_percentage,
                    }
    except Exception as e:
        logger.error(f"Error fetching loyalty info for receipt email: {e}")

    # Get partial payment history
    partial_payments = list(PartialPayment.objects.filter(receipt=receipt).order_by('payment_date'))

    # Get store configuration
    store_config = StoreConfiguration.get_active_config()

    # === Generate Location QR Code ===
    location_qr_code_url = None
    try:
        import qrcode
        from io import BytesIO
        import base64

        # Full address for Google Maps search
        full_address = "Wrighteous Wearhouse, Suit 10/11, Amma Centre, near AP Filling Station, opposite Old CBN, Garki, Abuja 900103, Federal Capital Territory"

        # Create Google Maps search URL
        import urllib.parse
        google_maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(full_address)}"

        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(google_maps_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()
        location_qr_code_url = f'data:image/png;base64,{qr_base64}'
    except Exception as e:
        logger.error(f"Error generating location QR code for email: {e}")

    # === Get Payment Methods ===
    # Get unique payment IDs from sales in this receipt
    payment_ids = sales.values_list('payment_id', flat=True).distinct()
    payments = PaymentMethod.objects.filter(payment_id__in=payment_ids)

    context = {
        'receipt': receipt,
        'sales': sales,
        'payment': payment,
        'payments': payments,
        'customer_name': receipt.customer.name,
        'user': receipt.user,
        'has_gifts': has_gifts,
        'total_item_discount': total_item_discount,
        'total_bill_discount': total_bill_discount,
        'total_price_before_discount': total_price_before_discount,
        'subtotal_amount': subtotal_amount,
        'final_total': final_total,
        'final_total_with_delivery': receipt.total_with_delivery or final_total,
        'delivery': None,
        'delivery_cost': Decimal('0.00'),
        'partial_payments': partial_payments,
        'logo_url': logo_url,
        'location_qr_code_url': location_qr_code_url,
        'loyalty_info': loyalty_info,
        'store_config': store_config,
        'store_name': store_config.store_name,
        'store_phone': store_config.phone,
        'store_email': store_config.email,
        'currency_symbol': store_config.currency_symbol,
    }

    html_message = render_to_string('receipt/receipt_email_template.html', context)
    pdf_html = render_to_string('receipt/receipt_pdf.html', context)

    pdf_file = BytesIO()
    try:
        HTML(string=pdf_html).write_pdf(pdf_file)
        pdf_content = pdf_file.getvalue()

        if not pdf_content or len(pdf_content) == 0:
            raise Exception("Generated PDF is empty.")

        # Validate PDF before sending
        from ..pdf_validator import validate_receipt_pdf
        is_valid, error_msg = validate_receipt_pdf(pdf_content, receipt, sales, store_config)

        if not is_valid:
            raise Exception(f"PDF validation failed: {error_msg}")

        logger.info(f"✅ PDF validation passed for receipt {pk} - all required data present")

    except Exception as e:
        logger.error(f"❌ Error generating PDF for receipt {pk}: {e}")
        messages.error(request, f"❌ Error generating PDF: {e}")
        return redirect('receipt_list')

    subject = f"Your Receipt #{receipt.receipt_number}"

    logger.info(f"📧 Creating email message...")
    logger.info(f"   From: {settings.DEFAULT_FROM_EMAIL}")
    logger.info(f"   To: {receipt.customer.email}")
    logger.info(f"   Subject: {subject}")
    logger.info(f"   PDF size: {len(pdf_content)} bytes")

    email = EmailMessage(
        subject=subject,
        body=html_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[receipt.customer.email],
        attachments=[
            (f'Receipt_{receipt.receipt_number}.pdf', pdf_content, 'application/pdf')
        ]
    )
    email.content_subtype = "html"

    try:
        logger.info(f"📧 Attempting to send email...")
        email.send()
        logger.info(f"✅ Receipt email sent successfully for receipt {pk} to {receipt.customer.email}")
        if loyalty_info:
            messages.success(request, f"✅ Receipt #{receipt.receipt_number} with {loyalty_info['points_earned']} loyalty points sent successfully to {receipt.customer.email}")
        else:
            messages.success(request, f"✅ Receipt #{receipt.receipt_number} sent successfully to {receipt.customer.email}")
    except Exception as e:
        logger.error(f"❌ Failed to send email for receipt {pk}: {str(e)}")
        messages.error(request, f"❌ Failed to send email: {str(e)}")

    # Redirect back to receipt list
    return redirect('receipt_list')



@login_required(login_url='login')
def download_receipt_pdf(request, pk):
    # Get receipt and related data
    receipt = get_object_or_404(Receipt, pk=pk)
    sales = receipt.sales.select_related('product').all()

    # Get payment (if exists)
    payment = None
    if sales.exists():
        first_sale = sales.first()
        if hasattr(first_sale, 'payment') and first_sale.payment:
            payment = first_sale.payment

    # Get customer (safe handling)
    customer = receipt.customer
    customer_name = customer.name if customer else "Walk-in Customer"

    # Flag: any gifted items on this receipt?
    has_gifts = any(sale.is_gift for sale in sales)

    # === Calculate Financials (gift items excluded — they are ₦0) ===
    total_price_before_discount = sum(
        (sale.product.selling_price * sale.quantity)
        for sale in sales if not sale.is_gift
    )

    total_item_discount = sum(
        (sale.discount_amount or Decimal('0.00')) * sale.quantity
        for sale in sales if not sale.is_gift
    )

    # Bill-level discount (from payment)
    total_bill_discount = payment.discount_amount if payment else Decimal('0.00')

    # Final subtotal after all discounts
    final_subtotal = total_price_before_discount - total_item_discount - total_bill_discount

    # === Delivery Fee ===
    delivery_cost = Decimal('0.00')
    delivery = None

    if customer:
        # Get the latest delivery for this customer (or filter by receipt if you have a relation)
        try:
            delivery = Delivery.objects.filter(customer=customer).latest('delivery_date')
            # Only apply delivery cost if delivery option is 'delivery'
            if delivery.delivery_option == 'delivery':
                delivery_cost = Decimal(str(delivery.delivery_cost))
        except Delivery.DoesNotExist:
            pass

    # Final total including delivery
    final_total_with_delivery = final_subtotal + delivery_cost

    # === Build logo URL ===
    domain = get_current_site(request).domain
    protocol = 'https' if request.is_secure() else 'http'
    logo_url = f'{protocol}://{domain}{static("img/Wlogo.png")}'

    # === Generate Location QR Code ===
    location_qr_code_url = None
    try:
        import qrcode
        from io import BytesIO
        import base64

        # Full address for Google Maps search
        full_address = "Wrighteous Wearhouse, Suit 10/11, Amma Centre, near AP Filling Station, opposite Old CBN, Garki, Abuja 900103, Federal Capital Territory"

        # Create Google Maps search URL
        import urllib.parse
        google_maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(full_address)}"

        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(google_maps_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()
        location_qr_code_url = f'data:image/png;base64,{qr_base64}'
    except Exception as e:
        logger.error(f"Error generating location QR code: {e}")

    # === Get Payment Methods ===
    # Get unique payment IDs from sales in this receipt
    payment_ids = sales.values_list('payment_id', flat=True).distinct()
    payments = PaymentMethod.objects.filter(payment_id__in=payment_ids)

    # === Get Store Config ===
    store_config = StoreConfiguration.get_active_config()

    # === Get Loyalty Info ===
    loyalty_info = None
    if receipt.customer and hasattr(receipt.customer, 'loyalty_account'):
        try:
            config = LoyaltyConfiguration.get_active_config()
            if config and config.is_active:
                loyalty_transaction = LoyaltyTransaction.objects.filter(
                    loyalty_account__customer=receipt.customer,
                    receipt=receipt
                ).order_by('-created_at').first()

                if loyalty_transaction:
                    loyalty_info = {
                        'program_name': config.program_name,
                        'points_earned': loyalty_transaction.points,
                        'previous_balance': loyalty_transaction.balance_after - loyalty_transaction.points,
                        'new_balance': loyalty_transaction.balance_after,
                        'redeemable_value': receipt.customer.loyalty_account.get_redeemable_value(),
                        'points_threshold': config.minimum_points_for_redemption,
                        'discount_percentage': config.maximum_discount_percentage,
                    }
        except Exception as e:
            logger.error(f"Error fetching loyalty info: {e}")

    # === Additional context vars for new thermal-style PDF template ===
    partial_payments = list(PartialPayment.objects.filter(receipt=receipt).order_by('payment_date'))
    subtotal_amount = sum(
        Decimal('0') if sale.is_gift else sale.total_price for sale in sales
    )

    # === Context for Template ===
    context = {
        'receipt': receipt,
        'sales': sales,
        'payment': payment,
        'payments': payments,
        'customer_name': customer_name,
        'user': receipt.user,
        'total_price_before_discount': total_price_before_discount,
        'total_item_discount': total_item_discount,
        'total_bill_discount': total_bill_discount,
        'subtotal_amount': subtotal_amount,
        'final_total': final_subtotal,  # Final amount before delivery
        'final_total_with_delivery': final_total_with_delivery,
        'delivery': delivery,
        'delivery_cost': delivery_cost,
        'logo_url': logo_url,
        'location_qr_code_url': location_qr_code_url,
        'store_config': store_config,
        'store_name': store_config.store_name,
        'store_phone': store_config.phone,
        'store_email': store_config.email,
        'currency_symbol': store_config.currency_symbol,
        'loyalty_info': loyalty_info,
        'has_gifts': has_gifts,
        'partial_payments': partial_payments,
    }

    # === Render HTML & Generate PDF ===
    html_string = render_to_string('receipt/receipt_pdf.html', context)
    pdf = HTML(string=html_string).write_pdf()

    # Log receipt download
    ActivityLog.log_activity(
        user=request.user,
        action='receipt_download',
        description=f'Downloaded receipt #{receipt.receipt_number} as PDF',
        model_name='Receipt',
        object_id=receipt.id,
        object_repr=f'Receipt #{receipt.receipt_number}',
        request=request
    )

    # === HTTP Response ===
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Receipt_{receipt.receipt_number}.pdf"'
    return response



@login_required(login_url='login')
def print_receipt(request, receipt_id):
    """Standalone print-ready receipt page (matches POS thermal template)."""
    receipt = get_object_or_404(Receipt, pk=receipt_id)
    sales = receipt.sales.select_related('product', 'payment', 'delivery').all()

    payment = sales.first().payment if sales.exists() else None
    customer_name = receipt.customer.name if receipt.customer else "No customer"

    has_gifts = any(sale.is_gift for sale in sales)

    total_item_discount = sum(
        (sale.discount_amount or Decimal('0.00')) for sale in sales if not sale.is_gift
    )
    total_price_before_discount = sum(
        sale.product.selling_price * sale.quantity for sale in sales if not sale.is_gift
    )
    total_bill_discount = payment.discount_amount if payment else Decimal('0.00')
    delivery_cost = receipt.delivery_cost or Decimal('0.00')
    final_total = payment.total_amount if payment else Decimal('0.00')

    payment_methods = payment.payment_methods.all() if payment else []
    partial_payments = list(PartialPayment.objects.filter(receipt=receipt).order_by('payment_date'))

    delivery = None
    if sales.exists():
        first_sale_delivery = sales.first().delivery
        if first_sale_delivery:
            delivery = first_sale_delivery

    subtotal_amount = sum(
        Decimal('0') if sale.is_gift else sale.total_price for sale in sales
    )

    loyalty_info = None
    if receipt.customer and hasattr(receipt.customer, 'loyalty_account'):
        try:
            config = LoyaltyConfiguration.get_active_config()
            if config and config.is_active:
                loyalty_transaction = LoyaltyTransaction.objects.filter(
                    loyalty_account__customer=receipt.customer,
                    receipt=receipt
                ).order_by('-created_at').first()
                if loyalty_transaction:
                    loyalty_info = {
                        'program_name': config.program_name,
                        'points_earned': loyalty_transaction.points,
                        'previous_balance': loyalty_transaction.balance_after - loyalty_transaction.points,
                        'new_balance': loyalty_transaction.balance_after,
                        'redeemable_value': receipt.customer.loyalty_account.get_redeemable_value(),
                        'points_threshold': config.minimum_points_for_redemption,
                        'discount_percentage': config.maximum_discount_percentage,
                    }
        except Exception:
            pass

    store_config = StoreConfiguration.get_active_config()

    return render(request, 'Receipt/print_receipt.html', {
        'receipt': receipt,
        'sales': sales,
        'payment': payment,
        'customer_name': customer_name,
        'user': receipt.user,
        'total_item_discount': total_item_discount,
        'total_bill_discount': total_bill_discount,
        'total_price_before_discount': total_price_before_discount,
        'subtotal_amount': subtotal_amount,
        'delivery_cost': delivery_cost,
        'final_total': final_total,
        'payment_methods': payment_methods,
        'partial_payments': partial_payments,
        'delivery': delivery,
        'loyalty_info': loyalty_info,
        'has_gifts': has_gifts,
        'store_config': store_config,
        'store_name': store_config.store_name,
        'store_phone': store_config.phone,
        'store_email': store_config.email,
        'currency_symbol': store_config.currency_symbol,
    })


@login_required(login_url='login')
def customer_list_view(request):
    # Get all customers
    customers = Customer.objects.all()
    return render(request, 'customer/customer_list.html', {'customers': customers})


@login_required(login_url='login')
def customer_receipt_history(request, customer_id):
    # Get the customer or return a 404 if not found
    customer = get_object_or_404(Customer, id=customer_id)

    # Get all receipts related to this customer
    receipts = Receipt.objects.filter(customer=customer).order_by('-date').prefetch_related('sales')

    # Apply date filtering
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if start_date and end_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1) - timedelta(seconds=1)
            receipts = receipts.filter(date__range=[start_date_obj, end_date_obj])
        except ValueError:
            messages.error(request, "Invalid date format. Please use YYYY-MM-DD.")

    # Prepare receipt data with total amounts
    receipt_data = []
    for receipt in receipts:
        # Use total_price which already includes discount
        total_amount = sum(sale.total_price for sale in receipt.sales.all())

        # Add delivery cost if present
        if receipt.delivery_cost:
            total_amount += receipt.delivery_cost

        receipt_data.append({
            'receipt': receipt,
            'total_amount': total_amount
        })

    return render(request, 'customer/customer_receipt_history.html', {
        'customer': customer,
        'receipt_data': receipt_data
    })


@login_required(login_url='login')
def update_delivery_status(request, sale_id):
    sale = Sale.objects.get(id=sale_id)
    if request.method == 'POST':
        # Mark sale as delivered
        sale.delivery_status = 'delivered'
        sale.save()

        messages.success(request, f"{sale.product.brand} marked as delivered.")
        return redirect('delivery_list')

    return render(request, 'delivery/update_delivery_status.html', {'sale': sale})


@login_required(login_url='login')
def cancel_order(request, sale_id):
    sale = Sale.objects.get(id=sale_id)
    sale.product.quantity += sale.quantity  # Restore stock quantity
    sale.product.save()
    sale.delete()
    return redirect('sell_product')  # Redirect back to sales view




@login_required
def add_partial_payment(request, receipt_id):
    """Add a partial payment to a receipt"""
    from ..models import Receipt, PartialPayment, PaymentMethod
    from decimal import Decimal

    receipt = get_object_or_404(Receipt, id=receipt_id)

    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', '0'))
        payment_method = request.POST.get('payment_method', 'Cash')
        notes = request.POST.get('notes', '')

        if amount <= 0:
            messages.error(request, "Payment amount must be greater than 0")
            return redirect('add_partial_payment', receipt_id=receipt_id)

        if amount > receipt.balance_remaining:
            messages.error(request, f"Payment amount (₦{amount}) cannot exceed remaining balance (₦{receipt.balance_remaining})")
            return redirect('add_partial_payment', receipt_id=receipt_id)

        # Handle store credit payment
        if payment_method == 'store_credit':
            from ..models import StoreCredit, StoreCreditUsage

            # Get customer's active store credits
            available_credits = StoreCredit.objects.filter(
                customer=receipt.customer,
                is_active=True,
                remaining_balance__gt=0
            ).order_by('issued_date')  # Use oldest credits first (FIFO)

            # Calculate total available balance
            total_available = sum([credit.remaining_balance for credit in available_credits])

            if amount > total_available:
                messages.error(request, f"Insufficient store credit. Available: ₦{total_available:.2f}, Requested: ₦{amount:.2f}")
                return redirect('add_partial_payment', receipt_id=receipt_id)

            # Deduct from store credits (FIFO - oldest first)
            remaining_to_deduct = amount
            for credit in available_credits:
                if remaining_to_deduct <= 0:
                    break

                # Calculate how much to deduct from this credit
                deduct_amount = min(credit.remaining_balance, remaining_to_deduct)

                # Create usage record
                StoreCreditUsage.objects.create(
                    store_credit=credit,
                    receipt=receipt,
                    amount_used=deduct_amount,
                    used_by=request.user
                )

                # Deduct from remaining amount
                remaining_to_deduct -= deduct_amount

            logger.info(f"Store credit used for balance payment: ₦{amount:.2f} on receipt {receipt.receipt_number}")

        # Create the partial payment
        PartialPayment.objects.create(
            receipt=receipt,
            amount=amount,
            payment_method=payment_method,
            notes=notes,
            received_by=request.user,
        )

        # Update receipt balances
        receipt.amount_paid += amount
        receipt.balance_remaining -= amount

        if receipt.balance_remaining <= 0:
            receipt.payment_status = 'paid'
            receipt.balance_remaining = Decimal('0')  # Ensure it's exactly 0
        else:
            receipt.payment_status = 'partial'

        receipt.save()

        messages.success(request, f"Payment of ₦{amount} recorded successfully")

        # If fully paid, redirect to receipt detail, otherwise stay on payment page
        if receipt.payment_status == 'paid':
            return redirect('receipt_detail', pk=receipt_id)
        else:
            return redirect('add_partial_payment', receipt_id=receipt_id)

    # GET request - show payment form
    # Get payment history
    payment_history = receipt.partial_payments.all().order_by('-payment_date')

    # Get payment method choices
    payment_method_choices = PaymentMethod.get_payment_method_choices()

    context = {
        'receipt': receipt,
        'payment_history': payment_history,
        'payment_method_choices': payment_method_choices,
    }
    return render(request, 'sales/add_partial_payment.html', context)


@login_required
def customer_debt_dashboard(request):
    """View all customers with outstanding balances"""
    from ..models import Receipt, Customer
    from django.db.models import Sum, Q, Count, Min
    from collections import defaultdict

    # Check if viewing a specific customer
    customer_id = request.GET.get('customer_id')

    if customer_id:
        # DETAIL VIEW: Show all receipts for a specific customer
        customer = get_object_or_404(Customer, id=customer_id)
        customer_receipts = Receipt.objects.filter(
            customer=customer,
            payment_status__in=['partial', 'pending'],
            balance_remaining__gt=0
        ).select_related('customer').prefetch_related('partial_payments').order_by('-date')

        total_debt = customer_receipts.aggregate(
            total=Sum('balance_remaining')
        )['total'] or 0

        context = {
            'selected_customer_id': customer_id,
            'selected_customer_data': {
                'customer': customer,
                'receipts': customer_receipts,
                'total_debt': total_debt,
                'debt_count': customer_receipts.count(),
            }
        }
    else:
        # LIST VIEW: Show all customers with outstanding balances
        outstanding_receipts = Receipt.objects.filter(
            payment_status__in=['partial', 'pending'],
            balance_remaining__gt=0
        ).select_related('customer').order_by('-date')

        # Group receipts by customer
        customer_debts_dict = defaultdict(lambda: {
            'customer': None,
            'total_debt': 0,
            'debt_count': 0,
            'oldest_debt_date': None
        })

        for receipt in outstanding_receipts:
            if receipt.customer:
                customer_id = receipt.customer.id
                customer_debts_dict[customer_id]['customer'] = receipt.customer
                customer_debts_dict[customer_id]['total_debt'] += receipt.balance_remaining
                customer_debts_dict[customer_id]['debt_count'] += 1

                # Track oldest debt date
                if (customer_debts_dict[customer_id]['oldest_debt_date'] is None or
                    receipt.date < customer_debts_dict[customer_id]['oldest_debt_date']):
                    customer_debts_dict[customer_id]['oldest_debt_date'] = receipt.date

        # Convert to list and sort by total debt (highest first)
        customer_debts = sorted(
            customer_debts_dict.values(),
            key=lambda x: x['total_debt'],
            reverse=True
        )

        # Calculate totals
        total_outstanding = sum([debt['total_debt'] for debt in customer_debts])
        total_customers = len(customer_debts)

        context = {
            'customer_debts': customer_debts,
            'total_outstanding': total_outstanding,
            'total_customers': total_customers,
        }

    return render(request, 'sales/customer_debt_dashboard.html', context)

