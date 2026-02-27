# Standard library
import io
import json
import logging
import traceback
import urllib.request
from decimal import Decimal

# Third-party libraries
import pandas as pd
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
)
from reportlab.lib.utils import ImageReader
from weasyprint import HTML

# Django imports
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.sites.shortcuts import get_current_site
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.utils import timezone

# Local app imports
from ..forms import LocationTransferForm, TransferItemForm
from ..models import (
    Product, LocationTransfer, TransferItem, ActivityLog
)
from .auth import is_md, is_cashier, is_superuser, user_required_access

logger = logging.getLogger(__name__)


@login_required(login_url='login')
def transfer_menu(request):
    return render(request, 'transfers/transfer_menu.html')


@login_required(login_url='login')
def internal_transfer_create_view(request):
    """View for internal transfers (Warehouse ↔ Shop Floor)"""
    from ..forms import InternalTransferForm

    try:
        current_location = request.user.profile.location
    except:
        current_location = 'ABUJA'  # Fallback

    # Get filters
    search = request.GET.get('search', '')
    category = request.GET.get('category', '')
    size = request.GET.get('size', '')
    color = request.GET.get('color', '')
    design = request.GET.get('design', '')
    min_quantity = request.GET.get('min_quantity', '')
    max_quantity = request.GET.get('max_quantity', '')
    shop_filter = request.GET.get('shop', '')  # Filter by shop type

    # Filter warehouse inventory at current location
    from ..models import WarehouseInventory
    warehouse_items = WarehouseInventory.objects.filter(location=current_location, quantity__gt=0)

    if search:
        warehouse_items = warehouse_items.filter(
            Q(brand__icontains=search) |
            Q(category__icontains=search) |
            Q(size__icontains=search) |
            Q(color__icontains=search) |
            Q(design__icontains=search)
        )

    if category:
        warehouse_items = warehouse_items.filter(category=category)
    if size:
        warehouse_items = warehouse_items.filter(size__icontains=size)
    if color:
        warehouse_items = warehouse_items.filter(color=color)
    if design:
        warehouse_items = warehouse_items.filter(design=design)
    if min_quantity:
        warehouse_items = warehouse_items.filter(quantity__gte=min_quantity)
    if max_quantity:
        warehouse_items = warehouse_items.filter(quantity__lte=max_quantity)

    warehouse_items = warehouse_items.order_by('brand', 'category', 'size')

    # Pagination
    paginator = Paginator(warehouse_items, 100)
    page_number = request.GET.get('page')
    products_page = paginator.get_page(page_number)

    # Unique values for dropdowns from warehouse inventory
    categories = WarehouseInventory.objects.filter(location=current_location).values_list('category', flat=True).distinct()
    sizes = WarehouseInventory.objects.filter(location=current_location).values_list('size', flat=True).distinct()
    colors = WarehouseInventory.objects.filter(location=current_location).values_list('color', flat=True).distinct()
    designs = WarehouseInventory.objects.filter(location=current_location).values_list('design', flat=True).distinct()

    has_filters = any([search, category, size, color, design, min_quantity, max_quantity, shop_filter])

    # Handle POST
    if request.method == 'POST':
        transfer_form = InternalTransferForm(request.POST)
        selected_products = []
        has_errors = False

        # Get selected products data
        selected_products_data = request.POST.get('selected_products_data', '')

        if selected_products_data:
            try:
                frontend_selections = json.loads(selected_products_data)

                # Validate and collect warehouse items
                for item_id, item_data in frontend_selections.items():
                    try:
                        warehouse_item = WarehouseInventory.objects.get(id=item_id, location=current_location)
                        qty = int(item_data.get('quantity', 1))

                        if qty <= 0:
                            messages.error(request, f"Invalid quantity for {warehouse_item.brand}.")
                            has_errors = True
                        elif qty > warehouse_item.quantity:
                            messages.error(request,
                                           f"Not enough stock for {warehouse_item.brand}. Available: {warehouse_item.quantity}, Requested: {qty}")
                            has_errors = True
                        else:
                            selected_products.append({'warehouse_item': warehouse_item, 'quantity': qty})
                    except WarehouseInventory.DoesNotExist:
                        messages.error(request, f"Warehouse item with ID {item_id} not found.")
                        has_errors = True
                    except (ValueError, TypeError):
                        messages.error(request, f"Invalid quantity data for warehouse item ID {item_id}.")
                        has_errors = True

            except json.JSONDecodeError:
                messages.error(request, "Invalid selection data format.")
                has_errors = True

        if not selected_products and not has_errors:
            messages.error(request, "Please select at least one product for internal transfer.")
            has_errors = True

        if not has_errors and transfer_form.is_valid():
            destination = transfer_form.cleaned_data['destination']
            notes = transfer_form.cleaned_data.get('notes', '')

            try:
                with transaction.atomic():
                    # Determine if this is location transfer or shop floor transfer
                    if destination == 'STORE':
                        # Transfer to shop floor (same location)
                        transfer_type = 'internal'
                        to_location = None
                        to_shop = 'STORE'
                        destination_desc = f'Shop Floor ({current_location})'
                    else:
                        # Transfer to different location (Abuja or Lagos)
                        transfer_type = 'location'
                        to_location = destination
                        to_shop = 'STORE'  # Goes to shop floor at destination
                        destination_desc = destination

                    # Create transfer record
                    transfer = LocationTransfer.objects.create(
                        transfer_type=transfer_type,
                        from_shop='WAREHOUSE',
                        to_shop=to_shop,
                        from_location=current_location if transfer_type == 'location' else None,
                        to_location=to_location,
                        internal_location=current_location if transfer_type == 'internal' else None,
                        transfer_reference=LocationTransfer.generate_transfer_reference(
                            transfer_type=transfer_type,
                            from_location=current_location,
                            to_location=to_location,
                            from_shop='WAREHOUSE',
                            to_shop=to_shop
                        ),
                        created_by=request.user,
                        notes=notes,
                        status='COMPLETED' if transfer_type == 'internal' else 'PENDING'
                    )

                    total_items = 0
                    total_value = 0

                    for item in selected_products:
                        warehouse_item = item['warehouse_item']
                        quantity = item['quantity']

                        # Create transfer item record (using a dummy Product reference for now)
                        # Note: We'll need to adjust TransferItem to handle warehouse items properly
                        # For now, create a temporary product reference
                        temp_product = Product.objects.filter(
                            brand=warehouse_item.brand,
                            category=warehouse_item.category,
                            size=warehouse_item.size,
                            color=warehouse_item.color,
                            design=warehouse_item.design,
                            location=current_location
                        ).first()

                        if not temp_product:
                            # Create a placeholder if needed
                            temp_product = Product.objects.create(
                                brand=warehouse_item.brand,
                                category=warehouse_item.category,
                                size=warehouse_item.size,
                                color=warehouse_item.color,
                                design=warehouse_item.design,
                                price=warehouse_item.price,
                                markup_type=warehouse_item.markup_type,
                                markup=warehouse_item.markup,
                                selling_price=warehouse_item.selling_price,
                                shop='STORE',
                                location=current_location,
                                quantity=0,
                                barcode_number=warehouse_item.original_barcode
                            )

                        TransferItem.objects.create(
                            transfer=transfer,
                            product=temp_product,
                            quantity=quantity,
                            unit_price=warehouse_item.price
                        )

                        # Update product based on destination
                        if destination == 'STORE':
                            # Move to shop floor at same location (internal transfer FROM warehouse TO shop floor)
                            # Find or create shop floor product
                            shop_product = temp_product  # Use the temp_product we created above

                            # Add quantity to shop floor
                            shop_product.quantity += quantity

                            # Restore barcode if it was saved in warehouse
                            if warehouse_item.original_barcode and not shop_product.barcode_number:
                                shop_product.barcode_number = warehouse_item.original_barcode

                            shop_product.save()

                            # Subtract from warehouse inventory
                            warehouse_item.quantity -= quantity
                            if warehouse_item.quantity <= 0:
                                # Warehouse depleted, delete it
                                warehouse_item.delete()
                            else:
                                warehouse_item.save()
                        else:
                            # Move to different location shop floor (location transfer from warehouse)
                            # Find or create product at destination location
                            dest_product = Product.objects.filter(
                                location=destination,
                                shop='STORE',
                                brand=warehouse_item.brand,
                                category=warehouse_item.category,
                                size=warehouse_item.size,
                                color=warehouse_item.color,
                                design=warehouse_item.design
                            ).first()

                            if not dest_product:
                                # Create product at destination location
                                dest_product = Product.objects.create(
                                    brand=warehouse_item.brand,
                                    category=warehouse_item.category,
                                    size=warehouse_item.size,
                                    color=warehouse_item.color,
                                    design=warehouse_item.design,
                                    price=warehouse_item.price,
                                    markup_type=warehouse_item.markup_type,
                                    markup=warehouse_item.markup,
                                    selling_price=warehouse_item.selling_price,
                                    shop='STORE',
                                    location=destination,
                                    quantity=0,
                                    barcode_number=warehouse_item.original_barcode
                                )

                            # Add quantity to destination
                            dest_product.quantity += quantity
                            dest_product.save()

                            # Subtract from source warehouse
                            warehouse_item.quantity -= quantity
                            if warehouse_item.quantity <= 0:
                                warehouse_item.delete()
                            else:
                                warehouse_item.save()

                        total_items += quantity
                        total_value += Decimal(str(warehouse_item.price)) * quantity

                    # Update transfer totals
                    transfer.total_items = total_items
                    transfer.total_value = total_value
                    transfer.save()

                    if not has_errors:
                        # Log the transfer
                        ActivityLog.log_activity(
                            user=request.user,
                            action='warehouse_transfer',
                            description=f'Warehouse transfer {transfer.transfer_reference} - Warehouse → {destination_desc} - {total_items} items - ₦{total_value:,.2f}',
                            model_name='LocationTransfer',
                            object_id=transfer.id,
                            object_repr=transfer.transfer_reference,
                            extra_data={
                                'from': 'WAREHOUSE',
                                'to': destination_desc,
                                'total_items': total_items,
                                'total_value': float(total_value),
                                'transfer_type': transfer_type
                            },
                            request=request
                        )

                        success_message = f"Transfer {transfer.transfer_reference} completed! {total_items} items moved from Warehouse to {destination_desc} (₦{total_value:,.2f})"
                        messages.success(request, success_message)

                        # Clear the session storage
                        request.session['transfer_created'] = True

                        return redirect('transfer_detail', transfer_id=transfer.id)

            except Exception as e:
                error_msg = f"Error completing internal transfer: {str(e)}"
                print(error_msg)
                print(traceback.format_exc())
                messages.error(request, f"An error occurred: {str(e)}")
        else:
            # Form validation errors
            if transfer_form.errors:
                for field, errors in transfer_form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field.title()}: {error}")
    else:
        transfer_form = InternalTransferForm()

    # Get store config for currency symbol
    from ..models import StoreConfiguration
    store_config = StoreConfiguration.get_active_config()

    context = {
        'transfer_form': transfer_form,
        'products': products_page,
        'categories': categories,
        'sizes': sizes,
        'colors': colors,
        'designs': designs,
        'current_location': current_location,
        'has_filters': has_filters,
        'current_filters': {
            'search': search,
            'category': category,
            'size': size,
            'color': color,
            'design': design,
            'min_quantity': min_quantity,
            'max_quantity': max_quantity,
            'shop': shop_filter,
        },
        'transfer_created': request.session.pop('transfer_created', False),
        'currency_symbol': store_config.currency_symbol if store_config else '₦',
        'is_internal_transfer': True,  # Flag to indicate this is internal transfer
    }

    return render(request, 'transfers/internal_transfer.html', context)


@login_required(login_url='login')
def transfer_create_view(request):
    try:
        from_location = request.user.profile.location
    except:
        from_location = 'ABUJA'  # Fallback

    # Get filters
    search = request.GET.get('search', '')
    category = request.GET.get('category', '')
    size = request.GET.get('size', '')
    color = request.GET.get('color', '')
    design = request.GET.get('design', '')
    min_quantity = request.GET.get('min_quantity', '')
    max_quantity = request.GET.get('max_quantity', '')

    # Filter products at source location
    products = Product.objects.filter(location=from_location, quantity__gt=0)

    if search:
        products = products.filter(
            Q(brand__icontains=search) |
            Q(category__icontains=search) |
            Q(size__icontains=search) |
            Q(color__icontains=search) |
            Q(design__icontains=search)
        )

    if category:
        products = products.filter(category=category)
    if size:
        products = products.filter(size__icontains=size)
    if color:
        products = products.filter(color=color)
    if design:
        products = products.filter(design=design)
    if min_quantity:
        products = products.filter(quantity__gte=min_quantity)
    if max_quantity:
        products = products.filter(quantity__lte=max_quantity)

    products = products.order_by('brand', 'category', 'size')

    # Pagination
    paginator = Paginator(products, 100)
    page_number = request.GET.get('page')
    products_page = paginator.get_page(page_number)

    # Unique values for dropdowns
    categories = Product.objects.filter(location=from_location).values_list('category', flat=True).distinct()
    sizes = Product.objects.filter(location=from_location).values_list('size', flat=True).distinct()
    colors = Product.objects.filter(location=from_location).values_list('color', flat=True).distinct()
    designs = Product.objects.filter(location=from_location).values_list('design', flat=True).distinct()

    has_filters = any([search, category, size, color, design, min_quantity, max_quantity])

    # Handle POST
    if request.method == 'POST':
        transfer_form = LocationTransferForm(request.POST)
        selected_products = []
        has_errors = False

        # Debug: Print POST data
        print("POST data:", request.POST)

        # Check if we have selected_products_data from frontend
        selected_products_data = request.POST.get('selected_products_data', '')

        if selected_products_data:
            try:
                # Parse the JSON data from frontend
                frontend_selections = json.loads(selected_products_data)

                # Process frontend selections
                for product_id, item_data in frontend_selections.items():
                    try:
                        product = Product.objects.get(id=product_id, location=from_location)
                        qty = int(item_data.get('quantity', 1))

                        if qty <= 0:
                            messages.error(request, f"Invalid quantity for {product.brand}.")
                            has_errors = True
                        elif qty > product.quantity:
                            messages.error(request,
                                           f"Not enough stock for {product.brand}. Available: {product.quantity}, Requested: {qty}")
                            has_errors = True
                        else:
                            selected_products.append({'product': product, 'quantity': qty})
                            print(f"Added from frontend data: {product.brand} - Qty: {qty}")
                    except Product.DoesNotExist:
                        messages.error(request,
                                       f"Product with ID {product_id} not found or not available at {from_location}.")
                        has_errors = True
                    except (ValueError, TypeError) as e:
                        messages.error(request, f"Invalid quantity data for product ID {product_id}.")
                        has_errors = True

            except json.JSONDecodeError:
                messages.error(request, "Invalid selection data format.")
                has_errors = True
        else:
            # Fallback to traditional form processing (for products visible on current page)
            # Get all products (not just paginated) to capture selections from all pages
            all_products = Product.objects.filter(location=from_location, quantity__gt=0)

            for product in all_products:
                selected_key = f'product_{product.id}_selected'
                quantity_key = f'product_{product.id}_quantity'

                if request.POST.get(selected_key):
                    try:
                        qty = int(request.POST.get(quantity_key, 1))
                        if qty <= 0:
                            messages.error(request, f"Invalid quantity for {product.brand}.")
                            has_errors = True
                        elif qty > product.quantity:
                            messages.error(request,
                                           f"Not enough stock for {product.brand}. Available: {product.quantity}, Requested: {qty}")
                            has_errors = True
                        else:
                            selected_products.append({'product': product, 'quantity': qty})
                            print(f"Added from form data: {product.brand} - Qty: {qty}")
                    except (ValueError, TypeError):
                        messages.error(request, f"Invalid quantity for {product.brand}.")
                        has_errors = True

        if not selected_products and not has_errors:
            messages.error(request, "Please select at least one product for transfer.")
            has_errors = True

        if not has_errors and transfer_form.is_valid():
            try:
                with transaction.atomic():
                    transfer = transfer_form.save(commit=False)
                    transfer.from_location = from_location
                    transfer.transfer_reference = LocationTransfer.generate_transfer_reference(
                        from_location, transfer.to_location
                    )
                    transfer.created_by = request.user
                    transfer.save()

                    # Debug: Print transfer details
                    print(f"Creating transfer: {transfer.transfer_reference}")

                    total_items = 0
                    total_value = 0

                    for item in selected_products:
                        # Debug: Print each transfer item
                        print(f"Adding product {item['product'].id}, quantity: {item['quantity']}")

                        # Create transfer item - let the model handle quantity deduction
                        transfer_item = TransferItem.objects.create(
                            transfer=transfer,
                            product=item['product'],
                            quantity=item['quantity'],
                            unit_price=item['product'].price
                        )

                        total_items += item['quantity']
                        total_value += item['product'].price * item['quantity']

                        print(
                            f"Transfer item created - model will handle quantity deduction for {item['product'].brand}")

                    # Update transfer totals
                    transfer.total_items = total_items
                    transfer.total_value = total_value
                    transfer.save()

                    # Log transfer creation
                    ActivityLog.log_activity(
                        user=request.user,
                        action='transfer_create',
                        description=f'Created transfer {transfer.transfer_reference} - {from_location} → {transfer.to_location} - {total_items} items - ₦{total_value:,.2f}',
                        model_name='LocationTransfer',
                        object_id=transfer.id,
                        object_repr=transfer.transfer_reference,
                        extra_data={
                            'from_location': from_location,
                            'to_location': transfer.to_location,
                            'total_items': total_items,
                            'total_value': float(total_value)
                        },
                        request=request
                    )

                    success_message = f"Transfer {transfer.transfer_reference} created successfully! {total_items} items transferred (₦{total_value:,.2f})"
                    messages.success(request, success_message)

                    # Clear the session storage by adding a success flag
                    request.session['transfer_created'] = True

                    return redirect('transfer_detail', transfer_id=transfer.id)

            except Exception as e:
                # More detailed error logging
                error_msg = f"Error creating transfer: {str(e)}"
                print(error_msg)
                print(traceback.format_exc())
                messages.error(request, f"An error occurred while creating the transfer: {str(e)}")
        else:
            # Form validation errors
            if transfer_form.errors:
                for field, errors in transfer_form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field.title()}: {error}")

            # If we have selected products but form errors, preserve the selection
            if selected_products:
                messages.info(request,
                              f"Please fix the form errors. You have {len(selected_products)} products selected.")
    else:
        transfer_form = LocationTransferForm()

    # Check if transfer was just created (to clear frontend storage)
    transfer_created = request.session.pop('transfer_created', False)

    context = {
        'transfer_form': transfer_form,
        'products': products_page,
        'from_location': from_location,
        'categories': categories,
        'sizes': sizes,
        'colors': colors,
        'designs': designs,
        'current_filters': {
            'search': search,
            'category': category,
            'size': size,
            'color': color,
            'design': design,
            'min_quantity': min_quantity,
            'max_quantity': max_quantity,
        },
        'has_filters': has_filters,
        'transfer_created': transfer_created,
    }
    return render(request, 'transfers/create_transfer.html', context)


@login_required(login_url='login')
def download_transfer_document(request, transfer_id, format_type):
    transfer = get_object_or_404(LocationTransfer, id=transfer_id)
    transfer_items = transfer.transfer_items.all()

    if format_type == 'pdf':
        return generate_transfer_pdf(transfer, transfer_items)
    elif format_type == 'excel':
        return generate_transfer_excel(transfer, transfer_items)
    else:
        messages.error(request, "Invalid format requested.")
        return redirect('transfer_detail', transfer_id=transfer_id)


@login_required(login_url='login')
def transfer_list_view(request):
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    # Start with all transfers
    transfers = LocationTransfer.objects.all().order_by('-transfer_date')

    # Apply filters
    if search_query:
        transfers = transfers.filter(transfer_reference__icontains=search_query)

    if status_filter:
        transfers = transfers.filter(status=status_filter)

    if type_filter:
        transfers = transfers.filter(transfer_type=type_filter)

    # Date filters
    if date_from:
        transfers = transfers.filter(transfer_date__gte=date_from)
    if date_to:
        transfers = transfers.filter(transfer_date__lte=date_to)

    # No need to annotate - total_value and total_items are now fields on the model

    context = {
        'transfers': transfers,
        'search_query': search_query,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': LocationTransfer.TRANSFER_STATUS_CHOICES,
        'type_choices': LocationTransfer.TRANSFER_TYPE_CHOICES,
    }
    return render(request, 'transfers/transfer_list.html', context)


@login_required(login_url='login')
def transfer_detail_view(request, transfer_id):
    transfer = get_object_or_404(LocationTransfer, id=transfer_id)
    transfer_items = transfer.transfer_items.all()

    # Calculate totals (still safe since item.total_price should be Decimal)
    total_items = sum(item.quantity for item in transfer_items)
    total_value = sum(item.total_price for item in transfer_items)

    context = {
        'transfer': transfer,
        'transfer_items': transfer_items,
        'total_items': total_items,
        'total_value': total_value,
    }
    return render(request, 'transfers/transfer_detail.html', context)


@login_required(login_url='login')
def download_transfer_pdf(request, transfer_id):
    # Get transfer and related data
    transfer = get_object_or_404(LocationTransfer, id=transfer_id)
    transfer_items = transfer.transfer_items.select_related('product').all()

    # Calculate total value
    total_value = sum(item.total_price for item in transfer_items)

    # Build logo URL
    domain = get_current_site(request).domain
    protocol = 'https' if request.is_secure() else 'http'
    logo_url = f'{protocol}://{domain}{static("img/Wlogo.png")}'

    # Context for Template
    context = {
        'transfer': transfer,
        'transfer_items': transfer_items,
        'total_value': total_value,
        'logo_url': logo_url,
        'current_date': timezone.now().strftime('%Y-%m-%d %H:%M'),
    }

    # Render HTML & Generate PDF
    html_string = render_to_string('transfers/transfer_pdf.html', context)
    pdf = HTML(string=html_string).write_pdf()

    # HTTP Response
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Transfer_{transfer.transfer_reference}.pdf"'
    return response


def generate_transfer_pdf(transfer, transfer_items, logo_url=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=40, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()

    # Add custom styles
    styles.add(ParagraphStyle(
        name='Header',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
        alignment=1  # Center
    ))

    styles.add(ParagraphStyle(
        name='Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey
    ))

    # Title with logo (if available)
    if logo_url:
        try:
            # Download and add logo
            with urllib.request.urlopen(logo_url) as response:
                img_data = response.read()
            logo = Image(ImageReader(io.BytesIO(img_data)), width=1.5 * inch, height=0.75 * inch)
            elements.append(logo)
        except:
            # Fallback if logo can't be loaded
            title = Paragraph("TRANSFER DOCUMENT", styles['Header'])
            elements.append(title)
    else:
        title = Paragraph("TRANSFER DOCUMENT", styles['Header'])
        elements.append(title)

    elements.append(Spacer(1, 12))

    # Transfer Info
    from_to = [
        ['Transfer Reference:', transfer.transfer_reference],
        ['Transfer Type:', transfer.get_transfer_type_display()],
    ]

    # Add location or shop info based on transfer type
    if transfer.transfer_type == 'location':
        from_to.extend([
            ['From Location:', transfer.get_from_location_display()],
            ['To Location:', transfer.get_to_location_display()],
        ])
    else:  # internal transfer
        from_to.extend([
            ['Location:', transfer.get_internal_location_display()],
            ['From:', transfer.get_from_shop_display()],
            ['To:', transfer.get_to_shop_display()],
        ])

    from_to.extend([
        ['Date:', transfer.transfer_date.strftime('%Y-%m-%d %H:%M')],
        ['Prepared By:', transfer.created_by.get_full_name() or transfer.created_by.username],
        ['Status:', transfer.get_status_display()],
    ])

    info_table = Table(from_to, colWidths=[120, 400])
    info_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
        ('FONT', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 15))

    # Items Table
    headers = ['Brand', 'Category', 'Size', 'Color', 'Design', 'Qty', 'Unit Price(₦)', 'Total(₦)']
    rows = [headers]

    total_value = 0
    for item in transfer_items:
        p = item.product
        total_price = item.total_price
        rows.append([
            p.brand,
            p.get_display_category() or p.category,
            p.size or '-',
            p.get_display_color() or p.color or '-',
            p.get_display_design() or p.design or '-',
            str(item.quantity),
            f"{item.unit_price:,.2f}",
            f"{total_price:,.2f}"
        ])
        total_value += total_price

    # Add total row
    rows.append(['', '', '', '', '', 'Total:', '', f"{total_value:,.2f}"])

    # Create table
    col_widths = [80, 90, 50, 60, 60, 40, 70, 80]
    item_table = Table(rows, colWidths=col_widths, repeatRows=1)
    item_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONT', (0, 1), (-1, -2), 'Helvetica', 9),
        ('FONT', (-1, -1), (-1, -1), 'Helvetica-Bold', 10),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),  # Blue header
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (5, 1), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('PADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#D9E1F2')]),  # Light blue alternating
    ]))
    elements.append(item_table)
    elements.append(Spacer(1, 20))

    # Signature section
    signature_data = [
        ['SENDER (ABUJA)', 'RECEIVER (LAGOS)'],
        ['', ''],
        ['_________________________', '_________________________'],
        ['Name:', 'Name:'],
        ['Date:', 'Date:'],
        ['Signature:', 'Signature:'],
    ]

    signature_table = Table(signature_data, colWidths=[250, 250])
    signature_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 12),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEABOVE', (0, 2), (-1, 2), 1, colors.black),
        ('SPAN', (0, 1), (0, 1)),
        ('SPAN', (1, 1), (1, 1)),
    ]))
    elements.append(signature_table)
    elements.append(Spacer(1, 15))

    # Footer
    footer = Paragraph(f"Generated on: {timezone.now().strftime('%Y-%m-%d %H:%M')} • Transfer ID: {transfer.id}",
                       styles['Footer'])
    elements.append(footer)

    # Notes section if available
    if transfer.notes:
        elements.append(Spacer(1, 10))
        notes_style = ParagraphStyle(
            name='Notes',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.darkgrey,
            borderPadding=5,
            borderColor=colors.lightgrey,
            backgroundColor=colors.whitesmoke,
            borderWidth=1
        )
        notes = Paragraph(f"<b>Notes:</b> {transfer.notes}", notes_style)
        elements.append(notes)

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="transfer_{transfer.transfer_reference}.pdf"'
    return response


def generate_transfer_excel(transfer, transfer_items):
    output = io.BytesIO()

    # Essential data only
    data = []
    for item in transfer_items:
        p = item.product

        # Determine From and To based on transfer type
        if transfer.transfer_type == 'location':
            from_location = transfer.get_from_location_display()
            to_location = transfer.get_to_location_display()
        else:  # internal transfer
            from_location = f"{transfer.get_internal_location_display()} - {transfer.get_from_shop_display()}"
            to_location = f"{transfer.get_internal_location_display()} - {transfer.get_to_shop_display()}"

        data.append({
            'Brand': p.brand,
            'Category': p.get_display_category() or p.category,
            'Size': p.size,
            'Color': p.get_display_color() or p.color or '',
            'Design': p.get_display_design() or p.design or '',
            'From': from_location,
            'To': to_location,
            'Quantity': item.quantity,
            'Unit Price (₦)': round(float(item.unit_price), 2),
            'Total (₦)': round(float(item.total_price), 2),
        })

    df = pd.DataFrame(data)

    # Write to Excel
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Items', index=False)
        worksheet = writer.sheets['Items']

        # Basic styling: header bold + auto-width
        for col_idx, column in enumerate(df.columns, 1):
            max_length = max(df[column].astype(str).map(len).max(), len(column)) + 2
            worksheet.column_dimensions[get_column_letter(col_idx)].width = min(max_length, 20)

        for cell in worksheet[1]:
            cell.font = Font(bold=True)

    output.seek(0)
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="transfer_{transfer.transfer_reference}.xlsx"'
    return response


@login_required(login_url='login')
def update_transfer_status(request, transfer_id):
    transfer = get_object_or_404(LocationTransfer, id=transfer_id)

    if request.method == 'POST':
        new_status = request.POST.get('status')

        # Validate status choice
        if new_status not in dict(LocationTransfer.TRANSFER_STATUS_CHOICES):
            messages.error(request, "Invalid status.")
        else:
            old_status = transfer.status
            transfer.status = new_status
            transfer.save()

            # Optional: Notify only
            if new_status == 'RECEIVED':
                messages.success(request, f"Transfer {transfer.transfer_reference} marked as received. No inventory update was made at destination.")
            else:
                messages.success(request, f"Transfer status updated to {transfer.get_status_display()}.")

    return redirect('transfer_detail', transfer_id=transfer_id)


@login_required(login_url='login')
def transfer_to_warehouse_view(request):
    """Bulk transfer from shop floor to warehouse"""
    try:
        current_location = request.user.profile.location
    except:
        current_location = 'ABUJA'  # Fallback

    # Get filters
    search = request.GET.get('search', '')
    category = request.GET.get('category', '')
    size = request.GET.get('size', '')
    color = request.GET.get('color', '')
    design = request.GET.get('design', '')
    min_quantity = request.GET.get('min_quantity', '')
    max_quantity = request.GET.get('max_quantity', '')

    # Filter products at current location - ONLY SHOP FLOOR ITEMS
    products = Product.objects.filter(location=current_location, quantity__gt=0, shop='STORE')

    if search:
        products = products.filter(
            Q(brand__icontains=search) |
            Q(category__icontains=search) |
            Q(size__icontains=search) |
            Q(color__icontains=search) |
            Q(design__icontains=search)
        )

    if category:
        products = products.filter(category=category)
    if size:
        products = products.filter(size__icontains=size)
    if color:
        products = products.filter(color=color)
    if design:
        products = products.filter(design=design)
    if min_quantity:
        products = products.filter(quantity__gte=min_quantity)
    if max_quantity:
        products = products.filter(quantity__lte=max_quantity)

    products = products.order_by('brand', 'category', 'size')

    # Pagination
    paginator = Paginator(products, 100)
    page_number = request.GET.get('page')
    products_page = paginator.get_page(page_number)

    # Unique values for dropdowns
    categories = Product.objects.filter(location=current_location, shop='STORE').values_list('category', flat=True).distinct()
    sizes = Product.objects.filter(location=current_location, shop='STORE').values_list('size', flat=True).distinct()
    colors = Product.objects.filter(location=current_location, shop='STORE').values_list('color', flat=True).distinct()
    designs = Product.objects.filter(location=current_location, shop='STORE').values_list('design', flat=True).distinct()

    has_filters = any([search, category, size, color, design, min_quantity, max_quantity])

    # Handle POST
    if request.method == 'POST':
        selected_products = []
        has_errors = False

        # Get selected products data
        selected_products_data = request.POST.get('selected_products_data', '')
        notes = request.POST.get('notes', '')

        print(f"DEBUG: POST request received")
        print(f"DEBUG: selected_products_data = {selected_products_data}")
        print(f"DEBUG: notes = {notes}")

        if selected_products_data:
            try:
                frontend_selections = json.loads(selected_products_data)

                # Validate and collect products
                for product_id, item_data in frontend_selections.items():
                    try:
                        product = Product.objects.get(id=product_id, location=current_location, shop='STORE')
                        qty = int(item_data.get('quantity', 1))

                        if qty <= 0:
                            messages.error(request, f"Invalid quantity for {product.brand}.")
                            has_errors = True
                        elif qty > product.quantity:
                            messages.error(request,
                                           f"Not enough stock for {product.brand}. Available: {product.quantity}, Requested: {qty}")
                            has_errors = True
                        else:
                            selected_products.append({'product': product, 'quantity': qty})
                    except Product.DoesNotExist:
                        messages.error(request, f"Product with ID {product_id} not found on shop floor.")
                        has_errors = True
                    except (ValueError, TypeError):
                        messages.error(request, f"Invalid quantity data for product ID {product_id}.")
                        has_errors = True

            except json.JSONDecodeError:
                messages.error(request, "Invalid selection data format.")
                has_errors = True

        if not selected_products and not has_errors:
            print(f"DEBUG: No products selected")
            messages.error(request, "Please select at least one product to transfer to warehouse.")
            has_errors = True

        if not selected_products_data:
            print(f"DEBUG: selected_products_data is empty!")
            messages.error(request, "No selection data received. Please try selecting products again.")
            has_errors = True

        if not has_errors:
            try:
                with transaction.atomic():
                    # Create transfer record
                    transfer = LocationTransfer.objects.create(
                        transfer_type='internal',
                        from_shop='STORE',
                        to_shop='WAREHOUSE',
                        internal_location=current_location,
                        transfer_reference=LocationTransfer.generate_transfer_reference(
                            transfer_type='internal',
                            from_shop='STORE',
                            to_shop='WAREHOUSE'
                        ),
                        created_by=request.user,
                        notes=notes,
                        status='COMPLETED'
                    )

                    total_items = 0
                    total_value = 0

                    for item in selected_products:
                        product = item['product']
                        quantity = item['quantity']

                        # Create transfer item record
                        TransferItem.objects.create(
                            transfer=transfer,
                            product=product,
                            quantity=quantity,
                            unit_price=product.price
                        )

                        # Move quantity to warehouse using WarehouseInventory table
                        from ..models import WarehouseInventory

                        # Find or create warehouse inventory
                        warehouse_item, created = WarehouseInventory.objects.get_or_create(
                            location=current_location,
                            brand=product.brand,
                            category=product.category,
                            size=product.size,
                            color=product.color,
                            design=product.design,
                            defaults={
                                'price': product.price,
                                'markup_type': product.markup_type,
                                'markup': product.markup,
                                'selling_price': product.selling_price,
                                'quantity': 0,
                                'original_barcode': product.barcode_number  # Store barcode for reference
                            }
                        )

                        # Add quantity to warehouse
                        warehouse_item.quantity += quantity
                        # Update barcode reference if not set
                        if not warehouse_item.original_barcode and product.barcode_number:
                            warehouse_item.original_barcode = product.barcode_number
                        warehouse_item.save()

                        # Subtract from shop floor product
                        product.quantity -= quantity
                        if product.quantity <= 0:
                            # Shop floor product depleted, can delete it
                            product.delete()
                        else:
                            product.save()

                        total_items += quantity
                        total_value += Decimal(str(product.price)) * quantity

                    # Update transfer totals
                    transfer.total_items = total_items
                    transfer.total_value = total_value
                    transfer.save()

                    # Log the transfer
                    ActivityLog.log_activity(
                        user=request.user,
                        action='transfer_to_warehouse',
                        description=f'Transferred to warehouse {transfer.transfer_reference} - Shop Floor → Warehouse - {total_items} items - ₦{total_value:,.2f}',
                        model_name='LocationTransfer',
                        object_id=transfer.id,
                        object_repr=transfer.transfer_reference,
                        extra_data={
                            'from': 'Shop Floor',
                            'to': 'Warehouse',
                            'total_items': total_items,
                            'total_value': float(total_value),
                            'location': current_location
                        },
                        request=request
                    )

                    success_message = f"Transfer {transfer.transfer_reference} completed! {total_items} items moved to warehouse (₦{total_value:,.2f})"
                    messages.success(request, success_message)

                    # Clear the session storage
                    request.session['transfer_created'] = True

                    return redirect('transfer_detail', transfer_id=transfer.id)

            except Exception as e:
                error_msg = f"Error completing warehouse transfer: {str(e)}"
                print(error_msg)
                print(traceback.format_exc())
                messages.error(request, f"An error occurred: {str(e)}")

    # Get store config for currency symbol
    from ..models import StoreConfiguration
    store_config = StoreConfiguration.get_active_config()

    context = {
        'products': products_page,
        'categories': categories,
        'sizes': sizes,
        'colors': colors,
        'designs': designs,
        'current_location': current_location,
        'has_filters': has_filters,
        'current_filters': {
            'search': search,
            'category': category,
            'size': size,
            'color': color,
            'design': design,
            'min_quantity': min_quantity,
            'max_quantity': max_quantity,
        },
        'transfer_created': request.session.pop('transfer_created', False),
        'currency_symbol': store_config.currency_symbol if store_config else '₦',
    }

    return render(request, 'transfers/transfer_to_warehouse.html', context)
