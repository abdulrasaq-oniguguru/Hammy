# Standard library
import logging
from decimal import Decimal

# Django imports
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import models
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

# Local app imports
from ..models import (
    Customer, Receipt, Return, ReturnItem, StoreCredit
)
from .auth import is_md, is_cashier, is_superuser, user_required_access

logger = logging.getLogger(__name__)


@login_required
def return_list(request):
    """List all returns with filtering"""
    returns = Return.objects.all().select_related('customer', 'receipt', 'processed_by')

    # Filter by status if provided
    status_filter = request.GET.get('status')
    if status_filter:
        returns = returns.filter(status=status_filter)

    # Filter by customer if provided
    customer_id = request.GET.get('customer')
    if customer_id:
        returns = returns.filter(customer_id=customer_id)

    context = {
        'returns': returns,
        'status_choices': Return.STATUS_CHOICES,
    }
    return render(request, 'returns/return_list.html', context)


@login_required
def return_detail(request, return_id):
    """View details of a specific return"""
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"=== RETURN DETAIL VIEW ===")
    logger.info(f"Return ID: {return_id}")

    return_obj = get_object_or_404(
        Return.objects.select_related('customer', 'receipt', 'processed_by', 'approved_by'),
        id=return_id
    )

    logger.info(f"Return Number: {return_obj.return_number}")
    logger.info(f"Status: {return_obj.status}")
    logger.info(f"Refund Amount: {return_obj.refund_amount}")
    logger.info(f"Customer: {return_obj.customer}")

    return_items = return_obj.return_items.all().select_related('product', 'original_sale')
    logger.info(f"Return Items Count: {return_items.count()}")

    # Check for associated store credit
    store_credit = None
    if return_obj.customer:
        store_credit = StoreCredit.objects.filter(return_transaction=return_obj).first()
        logger.info(f"Store Credit: {store_credit.credit_number if store_credit else 'None'}")

    context = {
        'return_obj': return_obj,
        'return': return_obj,  # Keep both for compatibility
        'return_items': return_items,
        'store_credit': store_credit,
    }
    logger.info("=== END RETURN DETAIL VIEW ===")
    return render(request, 'returns/return_detail.html', context)


@login_required
def return_search(request):
    """Search for receipts to create returns"""
    receipts = None
    query = request.GET.get('q', '').strip()

    if query:
        receipts = Receipt.objects.filter(
            models.Q(receipt_number__icontains=query) |
            models.Q(customer__name__icontains=query) |
            models.Q(customer__phone__icontains=query)
        ).select_related('customer')[:20]

    context = {
        'receipts': receipts,
        'query': query,
    }
    return render(request, 'returns/return_search.html', context)


@login_required
def return_select_items(request, receipt_id):
    """Select items from a receipt to return"""
    from datetime import timedelta

    receipt = get_object_or_404(Receipt.objects.select_related('customer'), id=receipt_id)

    # Check if receipt is within return period (7 days)
    receipt_age = timezone.now() - receipt.date
    days_since_purchase = receipt_age.days
    days_remaining = max(0, 7 - days_since_purchase)

    if days_remaining == 0:
        messages.error(request, "This receipt is beyond the 7-day return period and cannot be returned.")
        return redirect('receipt_detail', pk=receipt_id)

    sales = receipt.sales.all().select_related('product')

    # Calculate already returned quantities for each sale
    for sale in sales:
        # Get total quantity already returned for this sale
        returned_qty = ReturnItem.objects.filter(
            original_sale=sale
        ).aggregate(total=Sum('quantity_returned'))['total'] or 0

        sale.already_returned = returned_qty
        sale.max_returnable = sale.quantity - returned_qty
        sale.has_returnable = sale.max_returnable > 0

    if request.method == 'POST':
        # Process the return creation
        selected_items = []
        # Get list of selected item IDs from checkboxes
        selected_sale_ids = request.POST.getlist('selected_items')

        for sale in sales:
            # Check if this sale was selected via checkbox
            if str(sale.id) in selected_sale_ids:
                qty_str = request.POST.get(f'return_quantity_{sale.id}', '0').strip()
                try:
                    qty = int(qty_str) if qty_str else 0
                except ValueError:
                    qty = 0

                if qty > 0:
                    # Verify quantity doesn't exceed max returnable
                    if qty > sale.max_returnable:
                        messages.error(request, f"Cannot return {qty} of {sale.product.product_name} - only {sale.max_returnable} available")
                        return redirect('return_select_items', receipt_id=receipt_id)

                    selected_items.append({
                        'sale': sale,
                        'quantity': qty,
                        'new_price': request.POST.get(f'new_price_{sale.id}'),
                        'condition': request.POST.get(f'item_condition_{sale.id}', 'new'),
                        'restock': f'restock_{sale.id}' in request.POST,
                        'notes': request.POST.get(f'item_notes_{sale.id}', ''),
                    })

        if not selected_items:
            messages.error(request, "Please select at least one item to return")
            return redirect('return_select_items', receipt_id=receipt_id)

        # Create the return
        return_obj = Return.objects.create(
            receipt=receipt,
            customer=receipt.customer,
            processed_by=request.user,
            return_reason=request.POST.get('return_reason', 'other'),
            reason_notes=request.POST.get('reason_notes', ''),
        )

        # Create return items
        subtotal = Decimal('0.00')
        for item_data in selected_items:
            sale = item_data['sale']
            qty = item_data['quantity']

            # Calculate refund amount (proportional to quantity)
            refund_amount = (sale.total_price / sale.quantity) * qty

            # Use new price if provided (handle empty strings)
            new_price = item_data.get('new_price', '').strip()
            if new_price:
                try:
                    new_price = Decimal(new_price)
                except (ValueError, Exception):
                    new_price = None
            else:
                new_price = None

            ReturnItem.objects.create(
                return_transaction=return_obj,
                original_sale=sale,
                product=sale.product,
                quantity_sold=sale.quantity,
                quantity_returned=qty,
                original_selling_price=sale.product.selling_price,
                new_selling_price=new_price,
                original_total=sale.total_price,
                refund_amount=refund_amount,
                item_condition=item_data['condition'],
                restock_to_inventory=item_data['restock'],
                notes=item_data.get('notes', '').strip(),
            )

            subtotal += refund_amount

        # Update return totals
        return_obj.subtotal = subtotal
        return_obj.refund_amount = subtotal  # Can be adjusted later
        return_obj.save()

        messages.success(request, f"Return {return_obj.return_number} created successfully")
        return redirect('return_detail', return_id=return_obj.id)

    context = {
        'receipt': receipt,
        'sales': sales,
        'days_remaining': days_remaining,
        'days_since_purchase': days_since_purchase,
    }
    return render(request, 'returns/return_select_items.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def return_approve(request, return_id):
    """Approve a return"""
    return_obj = get_object_or_404(Return, id=return_id)

    if request.method == 'POST':
        return_obj.status = 'approved'
        return_obj.approved_by = request.user
        return_obj.approved_date = timezone.now()
        return_obj.save()
        messages.success(request, f"Return {return_obj.return_number} approved successfully")
        return redirect('return_detail', return_id=return_obj.id)

    return redirect('return_detail', return_id=return_obj.id)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def return_reject(request, return_id):
    """Reject a return"""
    return_obj = get_object_or_404(Return, id=return_id)

    if request.method == 'POST':
        return_obj.status = 'rejected'
        return_obj.reason_notes = request.POST.get('rejection_reason', return_obj.reason_notes)
        return_obj.save()
        messages.warning(request, f"Return {return_obj.return_number} rejected")
        return redirect('return_detail', return_id=return_obj.id)

    return redirect('return_detail', return_id=return_obj.id)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def return_cancel(request, return_id):
    """Cancel a return"""
    return_obj = get_object_or_404(Return, id=return_id)

    if request.method == 'POST':
        return_obj.status = 'cancelled'
        return_obj.save()
        messages.info(request, f"Return {return_obj.return_number} has been cancelled")
        return redirect('return_detail', return_id=return_obj.id)

    return redirect('return_detail', return_id=return_obj.id)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def return_complete_form(request, return_id):
    """Complete/approve a return and process refund"""
    import logging

    logger = logging.getLogger(__name__)
    return_obj = get_object_or_404(Return, id=return_id)

    if request.method == 'POST':
        logger.info(f"=== RETURN COMPLETE DEBUG ===")
        logger.info(f"Return ID: {return_id}")
        logger.info(f"Return Number: {return_obj.return_number}")
        logger.info(f"POST Data: {dict(request.POST)}")

        action = request.POST.get('action')
        logger.info(f"Action parameter: {action}")

        if action == 'approve':
            logger.info("Processing APPROVE action")
            return_obj.status = 'approved'
            return_obj.approved_by = request.user
            return_obj.approved_date = timezone.now()
            return_obj.save()
            messages.success(request, "Return approved successfully")

        elif action == 'complete':
            logger.info("Processing COMPLETE action")
            # Process the refund
            refund_type = request.POST.get('refund_type')
            logger.info(f"Refund type: {refund_type}")
            logger.info(f"Refund amount: {return_obj.refund_amount}")

            return_obj.refund_type = refund_type
            return_obj.status = 'completed'
            return_obj.refunded_date = timezone.now()

            if refund_type == 'store_credit':
                logger.info(f"Creating store credit for customer: {return_obj.customer}")
                logger.info(f"Customer ID: {return_obj.customer.id if return_obj.customer else 'None'}")

                if not return_obj.customer:
                    logger.error("ERROR: Cannot create store credit - no customer associated with return")
                    messages.error(request, "Cannot create store credit: No customer associated with this return")
                    return redirect('return_detail', return_id=return_obj.id)

                # Check if store credit already exists for this return
                existing_credit = StoreCredit.objects.filter(return_transaction=return_obj).first()
                if existing_credit:
                    logger.warning(f"Store credit already exists: {existing_credit.credit_number}")
                    messages.warning(request, f"Store credit {existing_credit.credit_number} already exists for this return")
                else:
                    try:
                        # Create store credit
                        store_credit = StoreCredit.objects.create(
                            customer=return_obj.customer,
                            original_amount=return_obj.refund_amount,
                            remaining_balance=return_obj.refund_amount,
                            return_transaction=return_obj,
                            issued_by=request.user,
                            notes=f"Store credit from return {return_obj.return_number}",
                        )
                        logger.info(f"✓ Store credit created successfully!")
                        logger.info(f"  - Credit Number: {store_credit.credit_number}")
                        logger.info(f"  - Amount: ₦{store_credit.original_amount}")
                        logger.info(f"  - Customer: {store_credit.customer.name}")
                        logger.info(f"  - Issued By: {request.user.username}")
                        messages.success(request, f"Store credit {store_credit.credit_number} created for ₦{return_obj.refund_amount}")
                    except Exception as e:
                        logger.error(f"ERROR creating store credit: {str(e)}")
                        logger.exception("Full traceback:")
                        messages.error(request, f"Failed to create store credit: {str(e)}")
                        return redirect('return_detail', return_id=return_obj.id)
            else:
                # Cash refund
                return_obj.refund_method = request.POST.get('refund_method', 'Cash')
                logger.info(f"Cash refund processed via {return_obj.refund_method}")
                messages.success(request, f"Cash refund of ₦{return_obj.refund_amount} processed")

            # Restock items if needed
            logger.info("Processing inventory restocking...")
            restocked_count = 0
            for return_item in return_obj.return_items.all():
                logger.info(f"Item: {return_item.product.brand} - Qty: {return_item.quantity_returned}, Restock: {return_item.restock_to_inventory}, Already Restocked: {return_item.restocked}")

                if return_item.restock_to_inventory and not return_item.restocked:
                    product = return_item.product
                    old_quantity = product.quantity
                    product.quantity += return_item.quantity_returned
                    product.save()
                    logger.info(f"Restocked {return_item.product.brand}: {old_quantity} -> {product.quantity}")

                    return_item.restocked = True
                    return_item.restocked_date = timezone.now()
                    return_item.save()
                    restocked_count += 1

            logger.info(f"Total items restocked: {restocked_count}")
            return_obj.save()

            # Verify store credit creation
            if refund_type == 'store_credit' and return_obj.customer:
                verified_credit = StoreCredit.objects.filter(return_transaction=return_obj).first()
                if verified_credit:
                    logger.info(f"✓ VERIFIED: Store credit {verified_credit.credit_number} exists in database")
                    logger.info(f"  - Balance: ₦{verified_credit.remaining_balance}")
                    logger.info(f"  - Active: {verified_credit.is_active}")
                else:
                    logger.error("✗ ERROR: Store credit was NOT saved to database!")
                    messages.error(request, "Warning: Store credit may not have been created properly")

            messages.success(request, f"Return completed successfully. {restocked_count} item(s) restocked.")

        elif action == 'reject':
            logger.info("Processing REJECT action")
            return_obj.status = 'rejected'
            return_obj.reason_notes = request.POST.get('rejection_reason', '')
            return_obj.save()
            messages.warning(request, "Return rejected")

        else:
            logger.warning(f"Unknown or missing action parameter: '{action}'")
            messages.error(request, f"Invalid action. Please try again.")

        logger.info("=== END RETURN COMPLETE DEBUG ===")
        return redirect('return_detail', return_id=return_obj.id)

    context = {
        'return_obj': return_obj,
        'return': return_obj,  # Keep both for compatibility
        'return_items': return_obj.return_items.all(),
    }
    return render(request, 'returns/return_complete_form.html', context)
