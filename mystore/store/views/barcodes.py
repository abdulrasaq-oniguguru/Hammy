# Standard library
import io
import json
import logging
import time
from io import BytesIO

# Third-party libraries
import barcode as barcode_module
from barcode.writer import ImageWriter
import win32print  # Windows-specific

# Django imports
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

# Local app imports
from ..choices import ProductChoices
from ..models import (
    Product, PrinterTaskMapping, PrinterConfiguration
)
from ..utils import get_cached_choices, get_product_stats
from .auth import is_md, is_cashier, is_superuser, user_required_access

logger = logging.getLogger(__name__)


@login_required(login_url='login')
def barcode_print_manager(request):
    """Barcode print manager with selection and quantity controls and optional sorting"""
    # Get filter parameters
    search = request.GET.get('search', '')
    category = request.GET.get('category', '')
    shop = request.GET.get('shop', '')
    size = request.GET.get('size', '')
    color = request.GET.get('color', '')
    design = request.GET.get('design', '')
    min_price = request.GET.get('min_price', '')
    max_price = request.GET.get('max_price', '')
    min_quantity = request.GET.get('min_quantity', '')
    max_quantity = request.GET.get('max_quantity', '')
    sort_by_name = request.GET.get('sort_by_name', '')
    sort_by_price = request.GET.get('sort_by_price', '')
    sort_by_quantity = request.GET.get('sort_by_quantity', '')
    sort_by_id = request.GET.get('sort_by_id', '')  # New: sort by ID (creation order)

    # Start with all products
    products = Product.objects.all()

    # Apply filters
    if search:
        products = products.filter(
            Q(brand__icontains=search) |
            Q(barcode_number__icontains=search) |
            Q(color__icontains=search) |
            Q(category__icontains=search) |
            Q(design__icontains=search) |
            Q(size__icontains=search)
        )

    if category:
        products = products.filter(category=category)

    if shop:
        products = products.filter(shop=shop)

    if size:
        products = products.filter(size__icontains=size)

    if color:
        products = products.filter(color=color)

    if design:
        products = products.filter(design=design)

    if min_price:
        products = products.filter(price__gte=min_price)

    if max_price:
        products = products.filter(price__lte=max_price)

    if min_quantity:
        products = products.filter(quantity__gte=min_quantity)

    if max_quantity:
        products = products.filter(quantity__lte=max_quantity)

    # Apply sorting
    if sort_by_name:
        products = products.order_by(sort_by_name)
    elif sort_by_price:
        products = products.order_by(sort_by_price)
    elif sort_by_quantity:
        products = products.order_by(sort_by_quantity)
    elif sort_by_id:
        products = products.order_by(sort_by_id)  # Sort by ID (creation order)
    else:
        products = products.order_by('brand')  # Default sorting

    # GET CACHED STATS
    stats = get_product_stats()
    total_quantity = stats['total_quantity']
    total_inventory_value = stats['total_inventory_value']

    # Calculate barcode-specific stats
    total_products = products.count()
    products_with_barcode = products.filter(barcode_image__isnull=False).exclude(barcode_image='').count()
    products_without_barcode = total_products - products_with_barcode

    # Pagination
    paginator = Paginator(products, 25)
    page_number = request.GET.get('page')
    products_page = paginator.get_page(page_number)

    # Check if filters are active
    has_filters = any([search, category, shop, size, color, design, min_price, max_price, min_quantity, max_quantity])

    # GET CACHED CHOICES
    color_choices = get_cached_choices('color')
    design_choices = get_cached_choices('design')
    category_choices = get_cached_choices('category')

    # Process shop choices - ensure they're in tuple format
    shop_choices = []
    for shop in ProductChoices.SHOP_TYPE:
        if isinstance(shop, (tuple, list)) and len(shop) >= 2:
            shop_choices.append((shop[0], shop[1]))
        else:
            shop_choices.append((shop, shop))

    # Get configured barcode printer from task mapping
    barcode_mapping = PrinterTaskMapping.objects.filter(
        task_name='barcode_label', is_active=True
    ).select_related('printer').first()
    barcode_printer = barcode_mapping.printer if barcode_mapping else None
    if not barcode_printer:
        barcode_printer = PrinterConfiguration.objects.filter(
            printer_type='barcode', is_active=True
        ).first()

    context = {
        'products': products_page,
        'query': search,
        'current_filters': {
            'search': search,
            'category': category,
            'shop': shop,
            'size': size,
            'color': color,
            'design': design,
            'min_price': min_price,
            'max_price': max_price,
            'min_quantity': min_quantity,
            'max_quantity': max_quantity,
            'sort_by_name': sort_by_name,
            'sort_by_price': sort_by_price,
            'sort_by_quantity': sort_by_quantity,
            'sort_by_id': sort_by_id,
        },
        'has_filters': has_filters,
        'category_choices': category_choices,
        'shop_choices': shop_choices,
        'COLOR_CHOICES': color_choices,
        'DESIGN_CHOICES': design_choices,
        'total_products': total_products,
        'total_quantity': total_quantity,
        'total_inventory_value': total_inventory_value,
        'products_with_barcode': products_with_barcode,
        'products_without_barcode': products_without_barcode,
        'is_superuser': request.user.is_superuser,
        'barcode_printer': barcode_printer,
    }

    return render(request, 'barcode/barcode_print_manager.html', context)


def generate_barcodes_view(request):
    """Display products without barcodes and handle barcode generation"""
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'generate_all':
            # Generate barcodes for all products without them
            return _generate_barcodes_bulk(request)

        elif action == 'generate_selected':
            # Generate barcodes for selected products
            selected_ids = request.POST.getlist('selected_products')
            if not selected_ids:
                messages.warning(request, 'Please select at least one product.')
                return redirect('generate_barcodes')

            return _generate_barcodes_for_products(request, selected_ids)

    # GET request - display the form
    products_without_barcodes = Product.objects.filter(
        barcode_image__isnull=True
    ) | Product.objects.filter(
        barcode_number__isnull=True
    )

    context = {
        'products': products_without_barcodes,
        'total_count': products_without_barcodes.count()
    }

    return render(request, 'barcode/generate_barcodes.html', context)


def _generate_barcodes_bulk(request):
    """Generate barcodes for all products without them"""
    products = Product.objects.filter(
        barcode_image__isnull=True
    ) | Product.objects.filter(
        barcode_number__isnull=True
    )

    success_count = 0
    error_count = 0

    for product in products:
        if _generate_single_barcode(product):
            success_count += 1
        else:
            error_count += 1

    if success_count > 0:
        messages.success(request, f'Successfully generated {success_count} barcodes.')
    if error_count > 0:
        messages.error(request, f'Failed to generate {error_count} barcodes.')

    return redirect('generate_barcodes')


def _generate_barcodes_for_products(request, product_ids):
    """Generate barcodes for specific products"""
    success_count = 0
    error_count = 0

    for product_id in product_ids:
        try:
            product = Product.objects.get(id=product_id)
            if _generate_single_barcode(product):
                success_count += 1
            else:
                error_count += 1
        except Product.DoesNotExist:
            error_count += 1

    if success_count > 0:
        messages.success(request, f'Successfully generated {success_count} barcodes.')
    if error_count > 0:
        messages.error(request, f'Failed to generate {error_count} barcodes.')

    return redirect('generate_barcodes')


def _generate_single_barcode(product):
    """Generate barcode for a single product"""
    try:
        # Generate barcode number if it doesn't exist
        if not product.barcode_number:
            base_number = str(product.id).zfill(12)
            check_digit = product._calculate_ean13_check_digit(base_number)
            product.barcode_number = base_number + str(check_digit)

        # Generate barcode image
        code128 = barcode_module.Code128(product.barcode_number, writer=ImageWriter())
        buffer = BytesIO()
        code128.write(buffer)
        filename = f'{product.brand}_{product.barcode_number}.png'

        buffer.seek(0)
        product.barcode_image.save(filename, buffer, save=False)
        product.save(update_fields=['barcode_image', 'barcode_number'])

        return True

    except Exception as e:
        return False


# AJAX view for single product barcode generation
def generate_single_barcode_ajax(request, product_id):
    """AJAX view to generate barcode for a single product"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})

    try:
        product = get_object_or_404(Product, id=product_id)

        if _generate_single_barcode(product):
            return JsonResponse({
                'success': True,
                'message': f'Barcode generated for {product.name}',
                'barcode_number': product.barcode_number,
                'barcode_url': product.barcode_image.url if product.barcode_image else None
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to generate barcode'
            })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


# Alternative view for immediate redirect (your original approach)
def generate_barcodes_redirect_view(request):
    """Original view that generates all barcodes and redirects immediately"""
    from django.urls import reverse
    products = Product.objects.filter(
        barcode_image__isnull=True
    ) | Product.objects.filter(
        barcode_number__isnull=True
    )

    for product in products:
        if not product.barcode_number:
            base_number = str(product.id).zfill(12)
            check_digit = product._calculate_ean13_check_digit(base_number)
            product.barcode_number = base_number + str(check_digit)

        try:
            code128 = barcode_module.Code128(product.barcode_number, writer=ImageWriter())
            buffer = BytesIO()
            code128.write(buffer)
            filename = f'{product.brand}_{product.barcode_number}.png'
            buffer.seek(0)
            product.barcode_image.save(filename, buffer, save=False)
            product.save(update_fields=['barcode_image', 'barcode_number'])
        except Exception as e:
            pass

    return redirect(reverse('product_list'))


@csrf_exempt
@require_POST
def print_multiple_barcodes_directly(request):
    """Print multiple barcodes directly to thermal printer with individual quantities"""
    try:
        data = json.loads(request.body)
        products_data = data.get('products', [])  # [{product_id: 1, quantity: 3}, ...]

        if not products_data:
            return JsonResponse({
                'success': False,
                'error': 'No products specified for printing'
            })

        # Resolve barcode printer: task mapping → barcode PrinterConfiguration → session/OS default
        barcode_mapping_printer = PrinterTaskMapping.get_printer_for_task('barcode_label')
        if barcode_mapping_printer:
            printer_name = barcode_mapping_printer.system_printer_name
            printer_source = 'task_mapping'
        else:
            barcode_config = PrinterConfiguration.objects.filter(printer_type='barcode', is_active=True).first()
            if barcode_config:
                printer_name = barcode_config.system_printer_name
                printer_source = 'barcode_config'
            else:
                printer_name = request.session.get('selected_printer') or win32print.GetDefaultPrinter()
                printer_source = 'fallback'

        if not printer_name:
            return JsonResponse({
                'success': False,
                'error': 'No barcode printer configured. Go to Printer Settings and assign a Barcode Printer.',
            })

        results = []
        total_printed = 0

        for item in products_data:
            product_id = item.get('product_id')
            quantity = item.get('quantity', 1)

            try:
                product = get_object_or_404(Product, id=product_id)

                # Ensure barcode is generated
                if not product.barcode_image or not product.barcode_number:
                    product.generate_barcode()
                    product.save()

                # Get the path to the barcode image
                barcode_path = product.barcode_image.path

                # Print the required number of copies
                copies_printed = 0
                for i in range(quantity):
                    success = print_image(printer_name, barcode_path)
                    if success:
                        copies_printed += 1
                        total_printed += 1

                    # Small delay between copies
                    time.sleep(0.3)

                results.append({
                    'product_id': product_id,
                    'product_name': product.brand,
                    'requested_quantity': quantity,
                    'printed_quantity': copies_printed,
                    'success': copies_printed == quantity
                })

            except Exception as e:
                logger.error(f"Error printing barcode for product {product_id}: {str(e)}")
                results.append({
                    'product_id': product_id,
                    'product_name': f'Product {product_id}',
                    'requested_quantity': quantity,
                    'printed_quantity': 0,
                    'success': False,
                    'error': str(e)
                })

        # Check success rate
        successful_products = sum(1 for result in results if result['success'])
        total_products = len(results)

        # Surface first failure reason as top-level error when nothing printed
        top_error = None
        if successful_products == 0:
            failed = [r for r in results if not r['success'] and r.get('error')]
            if failed:
                top_error = failed[0]['error']
            else:
                top_error = f"Print job sent to '{printer_name}' but 0 copies confirmed. Check the printer is online and the name is correct."

        return JsonResponse({
            'success': successful_products > 0,
            'message': f'Printed {total_printed} barcodes for {successful_products}/{total_products} products',
            'total_printed': total_printed,
            'successful_products': successful_products,
            'total_products': total_products,
            'results': results,
            'printer_name': printer_name,
            'printer_source': printer_source,
            **(({'error': top_error}) if top_error else {}),
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        })
    except Exception as e:
        logger.error(f"Multiple direct print failed: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Multiple direct print failed: {str(e)}'
        })


@csrf_exempt
@require_POST
def print_single_barcode_directly(request, product_id):
    """Print a single barcode with specified quantity"""
    try:
        data = json.loads(request.body)
        quantity = data.get('quantity', 1)

        product = get_object_or_404(Product, id=product_id)

        # Ensure barcode is generated
        if not product.barcode_image or not product.barcode_number:
            product.generate_barcode()
            product.save()

        # Resolve barcode printer: task mapping → barcode PrinterConfiguration → session/OS default
        barcode_mapping_printer = PrinterTaskMapping.get_printer_for_task('barcode_label')
        if barcode_mapping_printer:
            printer_name = barcode_mapping_printer.system_printer_name
        else:
            barcode_config = PrinterConfiguration.objects.filter(printer_type='barcode', is_active=True).first()
            if barcode_config:
                printer_name = barcode_config.system_printer_name
            else:
                printer_name = request.session.get('selected_printer') or win32print.GetDefaultPrinter()

        if not printer_name:
            return JsonResponse({
                'success': False,
                'error': 'No barcode printer configured. Go to Printer Settings and assign a Barcode Printer.',
            })

        # Get the path to the barcode image
        barcode_path = product.barcode_image.path

        # Print the required number of copies
        copies_printed = 0
        for i in range(quantity):
            success = print_image(printer_name, barcode_path)
            if success:
                copies_printed += 1

            # Small delay between copies
            time.sleep(0.3)

        return JsonResponse({
            'success': copies_printed > 0,
            'message': f'Printed {copies_printed}/{quantity} copies of barcode for {product.brand}',
            'product_name': product.brand,
            'requested_quantity': quantity,
            'printed_quantity': copies_printed,
            'printer_name': printer_name
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        })
    except Exception as e:
        logger.error(f"Single direct print failed: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Single direct print failed: {str(e)}'
        })


def print_image(printer_name, image_path):
    """Print an image directly to a printer using Windows GDI"""
    try:
        from PIL import Image, ImageWin
        import win32ui

        # Open the image
        image = Image.open(image_path)

        # Convert to monochrome if needed (better for thermal printers)
        if image.mode != "1":
            image = image.convert("1")

        # Get the printer
        hprinter = win32print.OpenPrinter(printer_name)

        try:
            # Get printer properties
            printer_info = win32print.GetPrinter(hprinter, 2)

            # Create a device context for the printer
            hdc = win32ui.CreateDC()
            hdc.CreatePrinterDC(printer_name)

            # Start document
            hdc.StartDoc("Barcode Print")
            hdc.StartPage()

            # Calculate scaling to fit the page
            printable_area = hdc.GetDeviceCaps(110), hdc.GetDeviceCaps(111)  # HORZRES, VERTRES

            # Scale image to fit printable area
            img_width, img_height = image.size
            scaling_x = printable_area[0] / img_width
            scaling_y = printable_area[1] / img_height
            scaling = min(scaling_x, scaling_y)

            # Calculate position to center image
            x = (printable_area[0] - img_width * scaling) / 2
            y = (printable_area[1] - img_height * scaling) / 2

            # Draw the image
            dib = ImageWin.Dib(image)
            dib.draw(hdc.GetHandleOutput(), (
                int(x),
                int(y),
                int(x + img_width * scaling),
                int(y + img_height * scaling)
            ))

            # End document
            hdc.EndPage()
            hdc.EndDoc()

            return True

        finally:
            win32print.ClosePrinter(hprinter)

    except Exception as e:
        logger.error(f"Error printing image: {str(e)}")
        return False


def print_barcode(request, product_id):
    """Legacy print barcode view"""
    product = get_object_or_404(Product, id=product_id)
    if not product.barcode_image:
        messages.error(request, "No barcode image found for this product.")
        return redirect('barcode_print_manager')
    return redirect(product.barcode_image.url)
