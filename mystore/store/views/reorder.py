# Standard library
import json
import logging
from decimal import Decimal

# Django imports
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

# Local app imports
from ..models import (
    Product, Invoice, InvoiceProduct, TransferItem, ReorderCartItem, ActivityLog
)
from .auth import is_md, is_cashier, is_superuser, user_required_access
from .invoices import _check_duplicate_invoice

logger = logging.getLogger(__name__)


@login_required(login_url='login')
def reorder_page(request):
    query = request.GET.get('search', '').strip()
    show_all = request.GET.get('all', '') == '1'

    filters = models.Q()
    if query:
        filters &= (
            models.Q(brand__icontains=query) |
            models.Q(color__icontains=query) |
            models.Q(category__icontains=query) |
            models.Q(design__icontains=query) |
            models.Q(size__icontains=query)
        )
        show_all = True  # when searching, show all matches regardless of stock level
    elif not show_all:
        filters &= models.Q(quantity__lt=5)  # default: low-stock only (0 and <5)

    # Sort: qty=0 first, then ascending qty, then brand
    products = Product.objects.filter(filters).order_by('quantity', 'brand')

    return render(request, 'product/reorder.html', {
        'products': products,
        'query': query,
        'show_all': show_all,
    })


@csrf_exempt
@login_required(login_url='login')
def reorder_toggle_cart(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        product_id = int(data.get('product_id'))
        product = get_object_or_404(Product, id=product_id)
        item, created = ReorderCartItem.objects.get_or_create(user=request.user, product=product)
        if not created:
            item.delete()
            action = 'removed'
        else:
            action = 'added'
        return JsonResponse({'action': action, 'product_id': product_id})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required(login_url='login')
def reorder_cart_data(request):
    items = ReorderCartItem.objects.filter(user=request.user).select_related('product')
    data = [
        {
            'id': item.id,
            'product_id': item.product.id,
            'brand': item.product.brand,
            'quantity': item.product.quantity,
            'barcode_number': item.product.barcode_number,
            'price': float(item.product.price),
        }
        for item in items
    ]
    return JsonResponse({'cart': data, 'count': len(data)})


@login_required(login_url='login')
def reorder_clear_cart(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'}, status=405)
    ReorderCartItem.objects.filter(user=request.user).delete()
    return JsonResponse({'success': True})


@login_required(login_url='login')
def reorder_confirm(request):
    if request.method != 'POST':
        return redirect('reorder_page')

    raw_ids = request.POST.getlist('selected_product_ids')
    product_ids = [int(x) for x in raw_ids if x.isdigit()]
    if not product_ids:
        messages.warning(request, "No products were selected for reorder.")
        return redirect('reorder_page')

    products_qs = Product.objects.filter(id__in=product_ids)
    invoice = Invoice.objects.create(user=request.user)
    errors = []
    reordered = []

    for product in products_qs:
        qty_str = request.POST.get(f'qty_{product.id}', '').strip()
        price_str = request.POST.get(f'price_{product.id}', '').strip()

        try:
            qty = int(qty_str)
            if qty <= 0:
                errors.append(f"Quantity for {product.brand} must be greater than 0.")
                continue
        except ValueError:
            errors.append(f"Invalid quantity for {product.brand}.")
            continue

        try:
            unit_price = Decimal(price_str)
            if unit_price < 0:
                raise ValueError
        except (ValueError, Exception):
            errors.append(f"Invalid price for {product.brand}.")
            continue

        product.quantity += qty
        if unit_price != product.price:
            product.price = unit_price
        product.save()
        reordered.append(product)

        InvoiceProduct.objects.create(
            invoice=invoice,
            product_name=product.brand,
            product_price=unit_price,
            product_color=product.color,
            product_size=product.size,
            product_category=product.category,
            quantity=qty,
            total_price=unit_price * qty
        )

        ActivityLog.log_activity(
            user=request.user,
            action='product_update',
            description=f'Reorder: added {qty} units to {product.brand} — new stock: {product.quantity}',
            model_name='Product',
            object_id=product.id,
            object_repr=str(product),
            request=request
        )

    for err in errors:
        messages.error(request, err)

    # Duplicate-invoice warning (48-hour window)
    duplicate = _check_duplicate_invoice(invoice)
    if duplicate:
        messages.warning(
            request,
            f"Invoice {duplicate.invoice_number} (created within the last 48 hours) "
            f"contains the same items as this reorder. Please verify this is not a duplicate."
        )

    request.session['reorder_product_ids'] = [p.id for p in reordered]
    request.session['reorder_invoice_number'] = invoice.invoice_number
    messages.success(request, f"Reorder complete! Invoice #{invoice.invoice_number} created.")
    return redirect('reorder_success')


@login_required(login_url='login')
def reorder_success(request):
    product_ids = request.session.pop('reorder_product_ids', [])
    invoice_number = request.session.pop('reorder_invoice_number', '')
    if not product_ids:
        return redirect('reorder_page')
    products = Product.objects.filter(id__in=product_ids)
    return render(request, 'product/reorder_success.html', {
        'products': products,
        'invoice_number': invoice_number,
        'product_ids_json': json.dumps([
            {'product_id': p.id, 'quantity': p.quantity} for p in products
        ]),
    })


def lookup_product_by_barcode(request):
    barcode = request.GET.get('barcode')
    context = request.GET.get('context')

    if not barcode:
        return JsonResponse({'found': False, 'error': 'No barcode provided'})

    try:
        product = Product.objects.get(barcode_number=barcode)

        # Build product data
        product_data = {
            'id': product.id,
            'brand': product.brand,
            'size': product.size,
            'color': product.color,
            'design': product.get_display_design() if product.design else None,
            'price': float(product.selling_price),
            'category': product.get_display_category(),
            'shop': product.get_shop_display(),
            'location': product.location,
            'quantity': product.quantity,
        }

        # Add image URL if image exists
        if product.image:
            product_data['image_url'] = product.image.url
        else:
            product_data['image_url'] = None

        # Context-based logic
        if context == 'transfer' or context == 'transfer_to_warehouse':
            # For transfer to warehouse - check if product is on shop floor
            if product.shop != 'STORE':
                return JsonResponse({
                    'found': False,
                    'error': f'Product is in {product.get_shop_display()}, not on Shop Floor.'
                })
            if product.quantity <= 0:
                return JsonResponse({
                    'found': False,
                    'error': 'This item is out of stock.'
                })
            product_data['stock'] = product.quantity

        elif context == 'transfer_from_warehouse':
            # Check if product exists in any completed transfers to this location
            # or if it has been transferred and received at the destination
            received_transfers = TransferItem.objects.filter(
                product=product,
                transfer__status='RECEIVED',
                transfer__to_location=product.location
            ).aggregate(
                total_received=models.Sum('quantity')
            )['total_received'] or 0

            # Also check for pending transfers that might be available
            pending_transfers = TransferItem.objects.filter(
                product=product,
                transfer__status__in=['PENDING', 'IN_TRANSIT'],
                transfer__from_location=product.location
            ).aggregate(
                total_pending=models.Sum('quantity')
            )['total_pending'] or 0

            available_quantity = received_transfers

            if available_quantity <= 0:
                return JsonResponse({
                    'found': False,
                    'error': f'This item has no stock available for transfer. Available: {available_quantity}'
                })

            product_data['stock'] = available_quantity

        elif context == 'sell':
            if product.quantity <= 0:
                return JsonResponse({
                    'found': False,
                    'error': f'This item is not available for sale. Current stock: {product.quantity}. Transfer from warehouse first.'
                })
            product_data['stock'] = product.quantity

        else:
            # Default fallback behavior — just return basic product info
            product_data['stock'] = product.quantity

        # Return product data wrapped in response
        return JsonResponse({
            'found': True,
            'product': product_data
        })

    except Product.DoesNotExist:
        return JsonResponse({'found': False, 'error': 'Product not found.'})
    except Product.MultipleObjectsReturned:
        return JsonResponse({
            'found': False,
            'error': 'Multiple items found with this barcode. Please fix duplicate.'
        })
    except Exception as e:
        # Add error logging for debugging — PRINT REMOVED
        return JsonResponse({
            'found': False,
            'error': f'System error occurred: {str(e)}'
        })


def barcode_lookup_page(request):
    barcode = request.GET.get('barcode')
    context = {}

    if barcode:
        try:
            product = Product.objects.get(barcode_number=barcode)
            context['product'] = product

            # Debug: Print raw values — PRINTS REMOVED
            context['data'] = {
                'id': product.id,
                'brand': product.brand,
                'size': product.size,
                'color': product.color,
                'color_display': product.get_display_color(),
                'design': product.design,
                'design_display': product.get_display_design() if product.design else 'N/A',
                'category': product.category,
                'category_display': product.get_display_category(),
                'shop': product.shop,
                'shop_display': product.get_shop_display(),
                'price': product.selling_price,
                'quantity': product.quantity,
                'image': product.image if product.image else None,
            }

            # Debug: Print display values — PRINTS REMOVED

        except Product.DoesNotExist:
            context['error'] = 'Product not found with this barcode.'
        except Product.MultipleObjectsReturned:
            context['error'] = 'Multiple products found with this barcode. Please contact admin.'

    return render(request, 'barcode/barcode_lookup.html', context)
