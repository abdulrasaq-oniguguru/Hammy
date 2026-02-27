# Standard library
import logging

# Django imports
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

# Local app imports
from ..forms import (
    PreOrderForm, PreOrderStatusForm
)
from ..models import (
    Product, PreOrder, Invoice, InvoiceProduct
)
from .auth import is_md, is_cashier, is_superuser, user_required_access

logger = logging.getLogger(__name__)


@login_required(login_url='login')
def pre_order(request):
    if request.method == 'POST':
        form = PreOrderForm(request.POST)
        if form.is_valid():
            form.save()
            # Add success message
            messages.success(request, "Pre-order created successfully!")
            # Redirect to the pre_order_list page after successful form submission
            return redirect('pre_order_list')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PreOrderForm()

    return render(request, 'orders/pre_order.html', {'form': form})


@login_required(login_url='login')
def pre_order_list(request):
    # Retrieve search and filter parameters from the GET request
    query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')

    # Retrieve pre-orders and allow filtering by status
    pre_orders = PreOrder.objects.all().order_by('-order_date')

    if status_filter == 'pending':
        pre_orders = pre_orders.filter(converted_to_product=False)
    elif status_filter == 'converted':
        pre_orders = pre_orders.filter(converted_to_product=True)

    if query:
        # Search filter
        pre_orders = pre_orders.filter(
            models.Q(brand__icontains=query) |
            models.Q(customer__name__icontains=query) |
            models.Q(quantity__icontains=query)
        )

    return render(
        request,
        'orders/pre_order_list.html',
        {
            'pre_orders': pre_orders,
            'search_query': query,
            'status_filter': status_filter,
        },
    )


@login_required(login_url='login')
def toggle_delivered(request, pre_order_id):
    # Toggle the delivered status for the pre-order
    pre_order = get_object_or_404(PreOrder, id=pre_order_id)
    pre_order.delivered = not pre_order.delivered
    pre_order.save()
    return redirect('pre_order_list')


@login_required(login_url='login')
def pre_order_detail(request, pre_order_id):
    # Get the specific pre-order by ID
    pre_order = get_object_or_404(PreOrder, id=pre_order_id)

    if request.method == 'POST':
        # Use a form to update the delivery status
        form = PreOrderStatusForm(request.POST, instance=pre_order)
        if form.is_valid():
            form.save()
            return redirect('pre_order_list')
    else:
        form = PreOrderStatusForm(instance=pre_order)

    return render(request, 'orders/pre_order_detail.html', {'pre_order': pre_order, 'form': form})


@login_required(login_url='login')
def edit_pre_order(request, pre_order_id):
    """Edit an existing pre-order"""
    pre_order = get_object_or_404(PreOrder, id=pre_order_id)

    if request.method == 'POST':
        form = PreOrderForm(request.POST, instance=pre_order)
        if form.is_valid():
            form.save()
            messages.success(request, "Pre-order updated successfully!")
            return redirect('pre_order_list')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PreOrderForm(instance=pre_order)

    return render(request, 'orders/edit_pre_order.html', {'form': form, 'pre_order': pre_order})


@login_required(login_url='login')
def delete_pre_order(request, pre_order_id):
    """Delete a pre-order"""
    pre_order = get_object_or_404(PreOrder, id=pre_order_id)

    if request.method == 'POST':
        brand = pre_order.brand
        pre_order.delete()
        messages.success(request, f"Pre-order for '{brand}' has been deleted successfully!")
        return redirect('pre_order_list')

    return render(request, 'orders/confirm_delete_pre_order.html', {'pre_order': pre_order})


@login_required(login_url='login')
def convert_preorder_to_product(request, pre_order_id):
    """Convert a pre-order to an actual product and create invoice"""
    from django.utils import timezone

    pre_order = get_object_or_404(PreOrder, id=pre_order_id)

    # Check if already converted
    if pre_order.converted_to_product:
        messages.warning(request, f"This pre-order has already been converted to a product on {pre_order.conversion_date.strftime('%Y-%m-%d %H:%M')}!")
        return redirect('pre_order_list')

    # Check if pre-order is ready for conversion
    is_ready, missing_fields = pre_order.is_ready_for_conversion()

    if not is_ready:
        field_labels = {
            'brand': 'Brand',
            'price': 'Buying Price',
            'size': 'Size',
            'category': 'Category',
            'markup_type': 'Markup Type',
            'markup': 'Markup',
            'shop': 'Shop'
        }
        missing_labels = [field_labels.get(f, f.title()) for f in missing_fields]
        messages.error(
            request,
            f"⚠️ Cannot convert to product yet! Please edit the pre-order and fill in these purchase details: {', '.join(missing_labels)}"
        )
        return redirect('edit_pre_order', pre_order_id=pre_order_id)

    try:
        # Create the product - match Product model exactly
        product = Product(
            brand=pre_order.brand,
            price=pre_order.price,  # This is the buying/cost price
            color=pre_order.color or '',
            design=pre_order.design or 'plain',
            size=pre_order.size,
            category=pre_order.category,
            quantity=pre_order.quantity,
            markup_type=pre_order.markup_type,
            markup=pre_order.markup or 0,
            selling_price=pre_order.selling_price,  # Can be null, will be calculated
            shop=pre_order.shop,
            barcode_number=pre_order.barcode_number or '',
            location=pre_order.location or 'ABUJA'
        )

        # Calculate selling price if not set
        if not product.selling_price:
            product.selling_price = product.calculate_selling_price()

        product.save()

        # Create the invoice
        invoice = Invoice(user=request.user)
        invoice.save()

        # Create invoice product entry
        invoice_product = InvoiceProduct(
            invoice=invoice,
            product_name=pre_order.brand,  # Use brand as product name in invoice
            product_price=pre_order.price,  # Buying price
            product_color=pre_order.color or '',
            product_size=pre_order.size,
            product_category=pre_order.category,
            quantity=pre_order.quantity,
            total_price=pre_order.price * pre_order.quantity
        )
        invoice_product.save()

        # Update pre-order to mark as converted
        pre_order.converted_to_product = True
        pre_order.conversion_date = timezone.now()
        pre_order.created_product = product
        pre_order.created_invoice = invoice
        pre_order.save()

        messages.success(
            request,
            f"✅ Pre-order converted successfully! Product '{product.brand}' added to inventory with {product.quantity} units. Invoice #{invoice.invoice_number} created."
        )

        # Redirect to invoice detail page
        return redirect('invoice_detail', invoice_id=invoice.id)

    except Exception as e:
        messages.error(request, f"Error converting pre-order to product: {str(e)}")
        return redirect('pre_order_list')
