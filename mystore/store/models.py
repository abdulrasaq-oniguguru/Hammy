import datetime
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Sum
from datetime import datetime
from io import BytesIO
from barcode import EAN13
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
from django.core.files.base import ContentFile
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from .choices import ProductChoices
import logging

logger = logging.getLogger(__name__)

class Invoice(models.Model):
    invoice_number = models.CharField(max_length=50, unique=True, blank=True)
    date = models.DateTimeField(auto_now_add=True, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return self.invoice_number

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            current_year = datetime.now().year
            # Fetch the last invoice for the current year based on the invoice number format
            last_invoice = Invoice.objects.filter(invoice_number__endswith=f'/{current_year}').order_by('id').last()

            if last_invoice:
                # Extract the number part of the last invoice number and increment it
                last_invoice_number = int(last_invoice.invoice_number.split('/')[0][3:])
                new_invoice_number = last_invoice_number + 1
            else:
                new_invoice_number = 1

            # Generate a new invoice number with the correct format
            self.invoice_number = f'INV{new_invoice_number:03d}/{current_year}'

        # Call the original save method
        super(Invoice, self).save(*args, **kwargs)





class InvoiceProduct(models.Model):
    """
    This model captures a snapshot of a product at the time it is added to an invoice.
    It is used to maintain purchase history even after the product details (such as quantity) are updated.
    """
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='invoice_products')
    product_name = models.CharField(max_length=100)
    product_price = models.DecimalField(max_digits=10, decimal_places=2)
    product_color = models.CharField(max_length=30, blank=True, null=True)
    product_size = models.CharField(max_length=10)
    product_category = models.CharField(max_length=50)
    quantity = models.IntegerField()
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f'{self.product_name} - {self.invoice.invoice_number}'




# Font caching at module level to avoid repeated filesystem access
_font_cache = {}


def get_thermal_optimized_font_cached(size):
    """Cached version of font loading"""
    if size in _font_cache:
        return _font_cache[size]

    font_options = [
        ("C:/Windows/Fonts/arial.ttf", size),
        ("C:/Windows/Fonts/tahoma.ttf", size),
        ("C:/Windows/Fonts/verdana.ttf", size),
        ("C:/Windows/Fonts/calibri.ttf", size),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", size),
        ("/System/Library/Fonts/Helvetica.ttc", size),
    ]

    for font_path, font_size in font_options:
        try:
            font = ImageFont.truetype(font_path, font_size)
            _font_cache[size] = font
            return font
        except (OSError, IOError):
            continue

    font = ImageFont.load_default()
    _font_cache[size] = font
    return font


class Product(models.Model):
    LOCATION_CHOICES = [
        ('ABUJA', 'Abuja'),
        ('LAGOS', 'Lagos'),
    ]

    brand = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    color = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )
    design = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default='plain',
    )
    size = models.CharField(max_length=10)
    category = models.CharField(max_length=100)
    quantity = models.IntegerField(default=0)
    markup_type = models.CharField(max_length=10, choices=ProductChoices.MARKUP_TYPE_CHOICES, default='percentage')
    markup = models.DecimalField(max_digits=8, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True,)
    shop = models.CharField(max_length=100, choices=ProductChoices.SHOP_TYPE)
    barcode_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    barcode_image = models.ImageField(upload_to='barcodes/', blank=True, null=True)
    image = models.ImageField(upload_to='product_images/', blank=True, null=True)
    location = models.CharField(max_length=10, choices=LOCATION_CHOICES, default='ABUJA')

    def __str__(self):
        return self.brand

    class Meta:
        indexes = [
            models.Index(fields=['barcode_number']),
            models.Index(fields=['brand']),
            models.Index(fields=['category']),
            models.Index(fields=['shop']),
            models.Index(fields=['color']),
            models.Index(fields=['design']),
            models.Index(fields=['price']),
            models.Index(fields=['quantity']),
            models.Index(fields=['location']),
            models.Index(fields=['barcode_number', 'brand']),
            models.Index(fields=['category', 'shop']),
            models.Index(fields=['category', 'color']),
            models.Index(fields=['shop', 'location']),
            models.Index(fields=['price', 'quantity']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity__gte=0),
                name='product_quantity_non_negative',
            ),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_barcode_number = self.barcode_number
        self._original_brand = self.brand
        self._original_size = self.size
        self._original_color = self.color
        self._original_selling_price = self.selling_price
        self._original_design = self.design
        self._original_category = self.category

    def has_changed(self, field):
        original = getattr(self, f'_original_{field}', None)
        current = getattr(self, field)
        if field == 'barcode_number':
            original = (original or '').strip()
            current = (current or '').strip()
            return original != current
        if isinstance(current, str):
            current = current.strip()
        if isinstance(original, str):
            original = original.strip()
        return original != current

    def calculate_selling_price(self):
        if self.markup_type == 'percentage':
            return self.price * (1 + (self.markup / 100))
        elif self.markup_type == 'fixed':
            return self.price + self.markup
        return self.price

    def get_display_color(self):
        """Get display name for color, checking predefined choices first"""
        result = ProductChoices.get_display_value(ProductChoices.COLOR_CHOICES, self.color)
        return result

    def get_display_design(self):
        """Get display name for design, checking predefined choices first"""
        result = ProductChoices.get_display_value(ProductChoices.DESIGN_CHOICES, self.design)
        return result

    def get_display_category(self):
        """Get display name for category, checking predefined choices first"""
        result = ProductChoices.get_display_value(ProductChoices.CATEGORY_CHOICES, self.category)
        return result

    def get_shop_display(self):
        """Get display name for shop, checking predefined choices first"""
        result = ProductChoices.get_display_value(ProductChoices.SHOP_TYPE, self.shop)
        return result

    # Cached display properties for templates
    @property
    def color_display(self):
        return self.get_display_color()

    @property
    def design_display(self):
        return self.get_display_design()

    @property
    def category_display(self):
        return self.get_display_category()

    @property
    def shop_display(self):
        return self.get_shop_display()

    @classmethod
    def get_all_colors_with_custom(cls):
        """Get all colors including custom ones from database"""
        return ProductChoices.get_all_colors_with_custom(cls)

    @classmethod
    def get_all_designs_with_custom(cls):
        """Get all designs including custom ones from database"""
        return ProductChoices.get_all_designs_with_custom(cls)

    @classmethod
    def get_all_categories_with_custom(cls):
        """Get all categories including custom ones from database"""
        return ProductChoices.get_all_categories_with_custom(cls)

    def _calculate_ean13_check_digit(self, base_12):
        """Helper to calculate EAN13 check digit"""
        digits = [int(d) for d in base_12]
        odd_sum = sum(digits[i] for i in range(0, 12, 2))
        even_sum = sum(digits[i] for i in range(1, 12, 2)) * 3
        total = odd_sum + even_sum
        mod = total % 10
        return (10 - mod) % 10 if mod != 0 else 0

    def generate_barcode(self):
        """Optimized barcode generation with better error handling"""
        if not self.barcode_number:
            if not self.pk:
                logger.error("Cannot generate barcode: Product must be saved first to have an ID.")
                return
            base_number = f"200{str(self.id).zfill(9)}"
            check_digit = self._calculate_ean13_check_digit(base_number)
            self.barcode_number = base_number + str(check_digit)

        if len(self.barcode_number) != 13 or not self.barcode_number.isdigit():
            logger.warning(f"Invalid barcode number for EAN-13: {self.barcode_number}")
            return

        try:
            # Precompute values
            label_width = int(55 * 300 / 25.4)
            label_height = int(25 * 300 / 25.4)

            # Generate barcode
            writer = ImageWriter()
            options = {
                'module_width': 0.45,
                'module_height': 10.0,
                'quiet_zone': 0.8,
                'background': 'white',
                'foreground': 'black',
                'write_text': False,
            }

            formatted_barcode = self.barcode_number.zfill(13)
            ean = EAN13(formatted_barcode, writer=writer)
            buffer = BytesIO()
            ean.write(buffer, options)
            barcode_img = Image.open(buffer)

            # Create final image
            final_img = Image.new('RGB', (label_width, label_height), 'white')
            draw = ImageDraw.Draw(final_img)

            # Use cached fonts
            font_brand = get_thermal_optimized_font_cached(30)
            font_details = get_thermal_optimized_font_cached(22)
            font_barcode_num = get_thermal_optimized_font_cached(24)
            font_price = get_thermal_optimized_font_cached(32)

            def draw_thermal_text(draw_obj, position, text, font, fill="black", extra_bold=False):
                x, y = position
                offsets = [
                    (0, 0), (1, 0), (0, 1), (1, 1),
                ]
                if extra_bold:
                    offsets += [
                        (-1, 0), (0, -1), (2, 0), (0, 2),
                        (-1, -1), (2, 1),
                    ]
                for offset_x, offset_y in offsets:
                    draw_obj.text((x + offset_x, y + offset_y), text, font=font, fill=fill)

            left_margin = 10

            # Top: Brand
            brand_text = self.brand[:14]
            draw_thermal_text(draw, (left_margin, 2), brand_text, font_brand)

            # Middle: Barcode
            barcode_height = int(label_height * 0.35)
            barcode_aspect = barcode_img.width / barcode_img.height
            barcode_width = int(barcode_height * barcode_aspect)
            max_barcode_width = label_width - left_margin - 10
            if barcode_width > max_barcode_width:
                barcode_width = max_barcode_width
                barcode_height = int(barcode_width / barcode_aspect)

            barcode_resized = barcode_img.resize((barcode_width, barcode_height), Image.Resampling.LANCZOS)
            barcode_y = 38
            final_img.paste(barcode_resized, (left_margin, barcode_y))

            # Below barcode: number
            barcode_num_text = formatted_barcode
            barcode_num_bbox = draw.textbbox((0, 0), barcode_num_text, font=font_barcode_num)
            barcode_num_width = barcode_num_bbox[2] - barcode_num_bbox[0]
            barcode_num_x = left_margin + (barcode_width - barcode_num_width) // 2
            barcode_num_y = barcode_y + barcode_height + 1
            draw_thermal_text(draw, (barcode_num_x, barcode_num_y), barcode_num_text, font_barcode_num)

            # Size & Color
            details_y = barcode_num_y + 18
            current_y = details_y

            if self.size and self.color:
                size_text = f"Size: {self.size}"
                draw_thermal_text(draw, (left_margin, current_y), size_text, font_details)
                current_y += 20

                color_display = self.color_display
                color_text = f"Color: {color_display}"
                max_width = label_width - left_margin - 5
                color_bbox = draw.textbbox((0, 0), color_text, font=font_details)
                if color_bbox[2] > max_width:
                    max_chars = int(max_width / (color_bbox[2] / len(color_text)))
                    color_text = color_text[:max_chars - 3] + "..."
                draw_thermal_text(draw, (left_margin, current_y), color_text, font_details)
            elif self.size:
                size_text = f"Size: {self.size}"
                draw_thermal_text(draw, (left_margin, current_y), size_text, font_details)
            elif self.color:
                color_display = self.color_display
                color_text = f"Color: {color_display}"
                max_width = label_width - left_margin - 5
                color_bbox = draw.textbbox((0, 0), color_text, font=font_details)
                if color_bbox[2] > max_width:
                    max_chars = int(max_width / (color_bbox[2] / len(color_text)))
                    color_text = color_text[:max_chars - 3] + "..."
                draw_thermal_text(draw, (left_margin, current_y), color_text, font_details)

            # Bottom: Price
            price_text = f"₦{self.selling_price:.2f}"
            price_bbox = draw.textbbox((0, 0), price_text, font=font_price)
            price_width = price_bbox[2] - price_bbox[0]
            price_height = price_bbox[3] - price_bbox[1]
            if self.size or self.color:
                price_y = current_y + 12
            else:
                price_y = barcode_num_y + 25

            if price_y + price_height > label_height - 3:
                price_y = label_height - price_height - 3

            price_x = (label_width - price_width) // 2
            draw_thermal_text(draw, (price_x, price_y), price_text, font_price, extra_bold=True)

            # Save the final image
            final_buffer = BytesIO()
            final_img.save(final_buffer, format='PNG', optimize=True, dpi=(300, 300))
            filename = f'{self.brand}_{formatted_barcode}.png'

            # Only update if the barcode has changed
            if not self.barcode_image or not self.barcode_image.name.endswith(filename):
                self.barcode_image.save(filename, ContentFile(final_buffer.getvalue()), save=False)

            self.barcode_number = formatted_barcode

        except Exception as e:
            logger.error(f"Error generating barcode for product {self.id}: {e}")

    def save(self, *args, **kwargs):
        self.selling_price = self.calculate_selling_price()

        is_new = self.pk is None
        if not is_new:
            original = Product.objects.get(pk=self.pk)
        else:
            original = None

        super().save(*args, **kwargs)

        critical_fields = ['brand', 'size', 'color', 'selling_price', 'design', 'category', 'barcode_number']
        should_regenerate = is_new

        if not is_new and original:
            for field in critical_fields:
                old_val = getattr(original, field, None)
                new_val = getattr(self, field, None)
                if old_val != new_val:
                    should_regenerate = True
                    break

        if should_regenerate:
            self.generate_barcode()
            super().save(update_fields=['barcode_image', 'barcode_number'])


class WarehouseInventory(models.Model):
    """
    Separate table for warehouse stock to avoid barcode conflicts.
    Products in warehouse don't need barcodes (only used for shop floor scanning).
    """
    LOCATION_CHOICES = [
        ('ABUJA', 'Abuja'),
        ('LAGOS', 'Lagos'),
    ]

    # Product attributes (copied from Product model for easy querying)
    brand = models.CharField(max_length=100)
    category = models.CharField(max_length=100)
    size = models.CharField(max_length=10)
    color = models.CharField(max_length=50, blank=True, null=True)
    design = models.CharField(max_length=50, blank=True, null=True, default='plain')

    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2)
    markup_type = models.CharField(max_length=10, choices=ProductChoices.MARKUP_TYPE_CHOICES, default='percentage')
    markup = models.DecimalField(max_digits=8, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    # Warehouse specific
    quantity = models.IntegerField(default=0)
    location = models.CharField(max_length=10, choices=LOCATION_CHOICES, default='ABUJA')

    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Optional: Link back to original product (if transferred from shop floor)
    # This helps track the barcode when moving back to shop floor
    original_barcode = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['brand']),
            models.Index(fields=['category']),
            models.Index(fields=['location']),
            models.Index(fields=['brand', 'size', 'color', 'design', 'location']),
        ]
        verbose_name = 'Warehouse Inventory'
        verbose_name_plural = 'Warehouse Inventories'

    def __str__(self):
        return f"{self.brand} - {self.size} ({self.location} Warehouse) - Qty: {self.quantity}"

    def get_display_color(self):
        """Get display name for color, checking predefined choices first"""
        result = ProductChoices.get_display_value(ProductChoices.COLOR_CHOICES, self.color)
        return result

    def get_display_design(self):
        """Get display name for design, checking predefined choices first"""
        result = ProductChoices.get_display_value(ProductChoices.DESIGN_CHOICES, self.design)
        return result

    def get_display_category(self):
        """Get display name for category, checking predefined choices first"""
        result = ProductChoices.get_display_value(ProductChoices.CATEGORY_CHOICES, self.category)
        return result

    def calculate_selling_price(self):
        """Calculate selling price based on markup"""
        if self.markup_type == 'percentage':
            return self.price * (Decimal('1') + (self.markup / Decimal('100')))
        elif self.markup_type == 'fixed':
            return self.price + self.markup
        return self.price

    def save(self, *args, **kwargs):
        """Auto-calculate selling price if not set"""
        if not self.selling_price:
            self.selling_price = self.calculate_selling_price()
        super().save(*args, **kwargs)


class ProductHistory(models.Model):
    ACTION_CHOICES = [
        ('EDIT', 'Edit'),
        ('DELETE', 'Delete'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)

    reason = models.TextField()
    quantity_changed = models.IntegerField(null=True, blank=True)  # Track quantity change
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.brand} - {self.get_action_display()} by {self.user.username} on {self.date}"


class LocationTransfer(models.Model):
    TRANSFER_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_TRANSIT', 'In Transit'),
        ('RECEIVED', 'Received'),
        ('CANCELLED', 'Cancelled'),
        ('COMPLETED', 'Completed'),  # For internal transfers
    ]

    TRANSFER_TYPE_CHOICES = [
        ('location', 'Location Transfer'),
        ('internal', 'Internal Transfer'),
    ]

    transfer_reference = models.CharField(max_length=50, unique=True)
    transfer_type = models.CharField(max_length=10, choices=TRANSFER_TYPE_CHOICES, default='location')

    # For location transfers (Abuja ↔ Lagos)
    from_location = models.CharField(max_length=10, choices=Product.LOCATION_CHOICES, blank=True, null=True)
    to_location = models.CharField(max_length=10, choices=Product.LOCATION_CHOICES, blank=True, null=True)

    # For internal transfers (Warehouse ↔ Shop Floor)
    from_shop = models.CharField(max_length=10, choices=ProductChoices.SHOP_TYPE, blank=True, null=True)
    to_shop = models.CharField(max_length=10, choices=ProductChoices.SHOP_TYPE, blank=True, null=True)
    internal_location = models.CharField(max_length=10, choices=Product.LOCATION_CHOICES, blank=True, null=True)  # Which location this internal transfer is at

    transfer_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=TRANSFER_STATUS_CHOICES, default='PENDING')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    notes = models.TextField(blank=True, null=True)
    total_items = models.IntegerField(default=0)
    total_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        if self.transfer_type == 'internal':
            return f"{self.transfer_reference} - {self.from_shop} to {self.to_shop} ({self.internal_location})"
        return f"{self.transfer_reference} - {self.from_location} to {self.to_location}"

    @classmethod
    def generate_transfer_reference(cls, from_location=None, to_location=None, transfer_type='location', from_shop=None, to_shop=None):
        count = cls.objects.count() + 1
        now = datetime.now()

        if transfer_type == 'internal':
            # IT = Internal Transfer
            from_code = from_shop[:2] if from_shop else 'WH'
            to_code = to_shop[:2] if to_shop else 'SF'
            return f'IT-{from_code}{to_code}-{count:04d}-{now.strftime("%m%y")}'
        else:
            # TR = Transfer (location)
            from_code = from_location[:2] if from_location else 'XX'
            to_code = to_location[:2] if to_location else 'XX'
            return f'TR-{from_code}{to_code}-{count:04d}-{now.strftime("%m%y")}'


class TransferItem(models.Model):
    transfer = models.ForeignKey(LocationTransfer, on_delete=models.CASCADE, related_name='transfer_items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    @property
    def total_price(self):
        return self.quantity * self.unit_price

    def save(self, *args, **kwargs):
        # Skip validation if using WarehouseInventory (check by looking at transfer direction)
        # When from_shop is 'WAREHOUSE' or to_shop is 'WAREHOUSE', we're using WarehouseInventory
        skip_shop_validation = (self.transfer.from_shop == 'WAREHOUSE' or self.transfer.to_shop == 'WAREHOUSE')

        # Validate based on transfer type
        if self.transfer.transfer_type == 'internal':
            # For internal transfers, validate location
            if self.product.location != self.transfer.internal_location:
                raise ValidationError(f"Product is not available in {self.transfer.internal_location}")

            # Only validate shop if not using WarehouseInventory
            if not skip_shop_validation and self.product.shop != self.transfer.from_shop:
                raise ValidationError(f"Product is not in {self.transfer.from_shop}. Currently in {self.product.shop}")
        else:
            # For location transfers, validate from_location
            if self.product.location != self.transfer.from_location:
                raise ValidationError(f"Product is not available in {self.transfer.from_location}")

        # Skip quantity check if using WarehouseInventory (handles validation separately)
        if not skip_shop_validation:
            # Check if enough quantity is available
            if self.quantity > self.product.quantity:
                raise ValidationError(f"Not enough stock. Available: {self.product.quantity}, Requested: {self.quantity}")

        # Store the unit price from product
        if not self.unit_price:
            self.unit_price = self.product.price

        super().save(*args, **kwargs)

        # Note: Product quantity and location updates are handled by the view logic
        # to avoid duplication and maintain proper control flow


class Customer(models.Model):
    name = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    email = models.CharField(max_length=30, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    sex = models.CharField(max_length=20,null=True, blank=True, choices=[('male', 'Male'), ('female', 'Female')])
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    frequent_customer = models.BooleanField(default=False)

    def __str__(self):
        return self.name

# models.py



class PreOrder(models.Model):
    LOCATION_CHOICES = [
        ('ABUJA', 'Abuja'),
        ('LAGOS', 'Lagos'),
    ]

    # === PRE-ORDER INFORMATION (Required when creating pre-order) ===
    brand = models.CharField(max_length=100, null=True, blank=True)  # Product brand - main identifier
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE)
    quantity = models.IntegerField()
    order_date = models.DateTimeField(auto_now_add=True)
    delivery_date = models.DateField(null=True, blank=True)
    delivered = models.BooleanField(default=False)
    remarks = models.TextField(null=True, blank=True)

    # === PRODUCT SPECIFICATIONS (Can be filled during pre-order or later) ===
    size = models.CharField(max_length=10, null=True, blank=True)  # Size
    color = models.CharField(max_length=50, blank=True, null=True)  # Color
    design = models.CharField(max_length=50, blank=True, null=True, default='plain')  # Design
    category = models.CharField(max_length=100, null=True, blank=True)  # Category

    # === PURCHASE INFORMATION (Fill in AFTER purchase, before conversion) ===
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # Buying/cost price
    markup_type = models.CharField(max_length=10, choices=ProductChoices.MARKUP_TYPE_CHOICES, default='percentage', null=True, blank=True)
    markup = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)  # Auto-calculated or manual
    shop = models.CharField(max_length=100, choices=ProductChoices.SHOP_TYPE, default='STORE', null=True, blank=True)
    barcode_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    location = models.CharField(max_length=10, choices=LOCATION_CHOICES, default='ABUJA', null=True, blank=True)

    # === CONVERSION TRACKING ===
    converted_to_product = models.BooleanField(default=False)
    conversion_date = models.DateTimeField(null=True, blank=True)
    created_product = models.ForeignKey('Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='from_preorder')
    created_invoice = models.ForeignKey('Invoice', on_delete=models.SET_NULL, null=True, blank=True, related_name='from_preorder')

    def __str__(self):
        return f"{self.brand} for {self.customer}"

    def is_ready_for_conversion(self):
        """Check if pre-order has all required fields for conversion"""
        required_fields = ['brand', 'price', 'size', 'category', 'markup_type', 'markup', 'shop']
        missing = []
        for field in required_fields:
            value = getattr(self, field)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(field)
        return len(missing) == 0, missing


class GoodsReceived(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity_received = models.IntegerField()
    received_date = models.DateTimeField(auto_now_add=True)
    batch_number = models.CharField(max_length=100)




class Delivery(models.Model):
    DELIVERY_OPTIONS = [
        ('pickup', 'Pick Up'),
        ('delivery', 'Delivery'),
    ]

    DELIVERY_STATUS = [
        ('pending', 'Pending Delivery'),
        ('delivered', 'Delivered'),
    ]

    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='deliveries')
    delivery_option = models.CharField(max_length=20, choices=DELIVERY_OPTIONS, null=True, blank=True)
    delivery_status = models.CharField(max_length=20, choices=DELIVERY_STATUS, default='pending', blank=True)
    delivery_address = models.CharField(max_length=255, blank=True, null=True)
    delivery_date = models.DateField(null=True, blank=True)
    delivery_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Enter any custom delivery amount"
    )

    def __str__(self):
        return f"{self.customer.name} - {self.delivery_option}"


# models.py
class Receipt(models.Model):
    receipt_number = models.CharField(max_length=50, unique=True, blank=True)
    date = models.DateTimeField(auto_now_add=True, null=True)
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    # Pricing breakdown
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Amount before tax")
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Total tax amount")
    delivery_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    loyalty_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Loyalty points discount applied")
    loyalty_points_redeemed = models.IntegerField(default=0, help_text="Number of loyalty points redeemed")
    total_with_delivery = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # Partial payment fields
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Total amount paid so far")
    balance_remaining = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Remaining balance to be paid")
    payment_status = models.CharField(
        max_length=20,
        choices=[
            ('paid', 'Fully Paid'),
            ('partial', 'Partially Paid'),
            ('pending', 'Payment Pending')
        ],
        default='paid',
        help_text="Payment status of this receipt"
    )

    # Tax details stored as JSON text
    tax_details = models.TextField(
        default='{}',
        blank=True,
        help_text="JSON text storing tax breakdown: {'tax_name': {'rate': X, 'amount': Y, 'method': 'inclusive/exclusive'}}"
    )

    def __str__(self):
        return self.receipt_number

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            current_year = datetime.now().year
            current_month = datetime.now().month

            # Ensure the operation is atomic
            with transaction.atomic():
                # Lock the table to avoid race conditions
                last_receipt = (
                    Receipt.objects.filter(
                        receipt_number__endswith=f'/{current_month:02d}/{current_year}'
                    )
                    .select_for_update()
                    .order_by('id')
                    .last()
                )

                if last_receipt:
                    last_receipt_number = int(last_receipt.receipt_number.split('/')[0][4:])
                    new_receipt_number = last_receipt_number + 1
                else:
                    new_receipt_number = 1

                # Generate the receipt number
                self.receipt_number = f'RCPT{new_receipt_number:03d}/{current_month:02d}/{current_year}'

        # Save first to ensure we have a pk
        super().save(*args, **kwargs)

        # After saving, recalculate totals if we have sales
        # This ensures discount is always calculated correctly on subtotal only
        if self.pk and self.sales.exists():
            calculated_total = self.calculate_total()

            # Only update if the total has changed (avoid unnecessary saves)
            if calculated_total != self.total_with_delivery:
                Receipt.objects.filter(pk=self.pk).update(
                    subtotal=self.subtotal,
                    total_with_delivery=calculated_total
                )

    def calculate_total(self):
        """
        Calculate receipt total: subtotal - discount + delivery
        Note: This should match the Payment.calculate_total() logic
        Returns the calculated total WITHOUT saving
        """
        from decimal import Decimal

        # Only calculate if receipt exists and has sales
        if not self.pk:
            return Decimal('0')

        # Get subtotal from all sales
        subtotal = self.sales.aggregate(total=Sum('total_price'))['total'] or Decimal('0')

        # Get discount from payment (if any).
        # Re-derive from discount_percentage so the receipt total is correct even
        # when Payment.save() ran before any Sales were linked.
        # NOTE: we deliberately do NOT write back to payment.discount_amount here
        # to break the old circular save chain.  Payment.save() is the sole owner
        # of payment.discount_amount.
        discount = Decimal('0')
        sales = self.sales.all()
        if sales.exists():
            first_sale = sales.first()
            if hasattr(first_sale, 'payment') and first_sale.payment:
                payment = first_sale.payment
                if payment.discount_percentage:
                    discount = subtotal * (Decimal(str(payment.discount_percentage)) / Decimal('100'))
                else:
                    discount = payment.discount_amount or Decimal('0')

        # Update subtotal
        self.subtotal = subtotal

        # Calculate and return total: subtotal - discount + delivery
        return subtotal - discount + Decimal(str(self.delivery_cost))

    def get_tax_breakdown(self):
        """
        Get parsed tax details as a dictionary
        Returns: dict with tax breakdown or empty dict if no tax
        """
        import json
        if not self.tax_details:
            return {}

        try:
            if isinstance(self.tax_details, dict):
                return self.tax_details
            return json.loads(self.tax_details)
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_inclusive_tax_total(self):
        """Calculate total inclusive tax amount"""
        from decimal import Decimal
        tax_data = self.get_tax_breakdown()
        total = Decimal('0')

        for tax_code, tax_info in tax_data.items():
            if tax_info.get('method') == 'inclusive':
                total += Decimal(str(tax_info.get('amount', 0)))

        return total

    def get_exclusive_tax_total(self):
        """Calculate total exclusive tax amount"""
        from decimal import Decimal
        tax_data = self.get_tax_breakdown()
        total = Decimal('0')

        for tax_code, tax_info in tax_data.items():
            if tax_info.get('method') == 'exclusive':
                total += Decimal(str(tax_info.get('amount', 0)))

        return total

    def get_amount_before_tax(self):
        """
        Get the amount before exclusive tax was added
        For inclusive tax, this extracts the base amount
        """
        from decimal import Decimal

        # Start with the grand total
        amount = self.total_with_delivery

        # Subtract exclusive tax (it was added on top)
        amount -= self.get_exclusive_tax_total()

        return amount





# Add this to your models.py
class UserProfile(models.Model):
    ACCESS_LEVEL_CHOICES = [
        ('md', 'Managing Director'),
        ('cashier', 'Cashier'),
        ('accountant', 'Accountant'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    access_level = models.CharField(max_length=20, choices=ACCESS_LEVEL_CHOICES, default='cashier')
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    is_active_staff = models.BooleanField(default=True)
    created_date = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_users')

    def __str__(self):
        return f"{self.user.username} - {self.get_access_level_display()}"

    @property
    def full_name(self):
        return f"{self.user.first_name} {self.user.last_name}".strip() or self.user.username

    def can_manage_users(self):
        return self.access_level == 'md'

    def can_access_reports(self):
        return self.access_level in ['md', 'accountant']

    def can_process_sales(self):
        return self.access_level in ['md', 'cashier']

    def can_manage_inventory(self):
        return self.access_level in ['md', 'accountant']


# Updated Django Models to Support Multiple Payment Methods

from django.db import models
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.utils import timezone


class Payment(models.Model):
    """Main payment record - now acts as a container for multiple payment methods"""
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('partial', 'Partially Paid'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True)
    loyalty_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Loyalty points discount")
    payment_date = models.DateTimeField(auto_now_add=True)
    completed_date = models.DateTimeField(null=True, blank=True)

    def calculate_total(self):
        """Calculate the total amount based on related sales and apply the discount."""
        if self.pk:
            # Get the sum of all related sales (without delivery cost)
            total = self.sale_set.aggregate(total=Sum('total_price'))['total'] or Decimal('0')

            # Calculate the discount amount based on the total and discount percentage
            if self.discount_percentage:
                discount_amount = total * (Decimal(str(self.discount_percentage)) / Decimal('100'))
            else:
                discount_amount = Decimal('0')

            self.discount_amount = discount_amount
            final_amount = total - discount_amount

            # Add delivery cost if exists
            if hasattr(self, 'sale_set') and self.sale_set.exists():
                sale = self.sale_set.first()
                if sale.delivery:
                    final_amount += Decimal(str(sale.delivery.delivery_cost))

            # Subtract loyalty discount
            final_amount -= self.loyalty_discount_amount

            return final_amount
        return Decimal('0')

    def update_payment_status(self):
        """Update payment status based on total paid vs total amount"""
        self.total_paid = self.payment_methods.filter(status='completed').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        self.balance_due = self.total_amount - self.total_paid

        if self.total_paid >= self.total_amount:
            self.payment_status = 'completed'
            self.completed_date = timezone.now()
            self.balance_due = Decimal('0')
        elif self.total_paid > Decimal('0'):
            self.payment_status = 'partial'
        else:
            self.payment_status = 'pending'

    def get_payment_summary(self):
        """Get a summary of all payment methods used"""
        methods = self.payment_methods.all()
        summary = []
        for method in methods:
            summary.append({
                'method': method.get_payment_method_display(),
                'amount': method.amount,
                'status': method.get_status_display(),
                'reference': method.reference_number or 'N/A'
            })
        return summary

    def save(self, *args, **kwargs):
        with transaction.atomic():
            # Save once to persist structural fields and ensure a PK exists
            super().save(*args, **kwargs)

            # Calculate totals and status from DB aggregates
            self.total_amount = self.calculate_total()
            self.update_payment_status()

            # Persist calculated fields via queryset update — avoids a second model-level save
            Payment.objects.filter(pk=self.pk).update(
                total_amount=self.total_amount,
                discount_amount=self.discount_amount,
                loyalty_discount_amount=self.loyalty_discount_amount,
                total_paid=self.total_paid,
                balance_due=self.balance_due,
                payment_status=self.payment_status,
                completed_date=self.completed_date,
            )

        # Trigger receipt recalculation when payment changes (e.g., discount applied)
        if self.pk and self.sale_set.exists():
            first_sale = self.sale_set.first()
            if first_sale and first_sale.receipt:
                first_sale.receipt.save()

    def __str__(self):
        return f"Payment #{self.pk} - Total: {self.total_amount:.2f} - Status: {self.payment_status}"


class PaymentMethod(models.Model):
    """Individual payment method within a payment"""
    # Default payment methods - used for initialization and backward compatibility
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('pos_moniepoint', 'POS Moniepoint'),
        ('transfer_taj', 'Transfer Taj'),
        ('transfer_sterling', 'Transfer Sterling'),
        ('transfer_moniepoint', 'Transfer Moniepoint'),
        ('card', 'Card Payment'),
        ('mobile_money', 'Mobile Money'),
        ('bank_deposit', 'Bank Deposit'),
        ('cheque', 'Cheque'),
        ('store_credit', 'Store Credit'),
    ]

    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='payment_methods')
    payment_method = models.CharField(max_length=100)  # Increased to support custom payment methods
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    reference_number = models.CharField(max_length=100, blank=True, null=True,
                                        help_text="Transaction reference, receipt number, etc.")
    notes = models.TextField(blank=True, null=True, help_text="Additional payment details")
    processed_date = models.DateTimeField(auto_now_add=True)
    confirmed_date = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['processed_date']

    @classmethod
    def get_payment_method_choices(cls):
        """
        Get payment method choices dynamically from PaymentMethodConfiguration.
        Falls back to PAYMENT_METHODS if no configuration exists.
        """
        # Avoid circular import
        from .models import PaymentMethodConfiguration

        try:
            choices = PaymentMethodConfiguration.get_payment_choices()
            if choices:
                return choices
        except Exception:
            pass

        # Fallback to default PAYMENT_METHODS
        return cls.PAYMENT_METHODS

    def get_payment_method_display(self):
        """Get display name for the payment method"""
        # Try to get from PaymentMethodConfiguration first
        try:
            from .models import PaymentMethodConfiguration
            method_config = PaymentMethodConfiguration.objects.filter(code=self.payment_method).first()
            if method_config:
                return method_config.display_name
        except Exception:
            pass

        # Fall back to checking PAYMENT_METHODS
        for code, display in self.PAYMENT_METHODS:
            if code == self.payment_method:
                return display

        # If not found, return the code itself (for custom payment methods)
        return self.payment_method

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update parent payment status whenever a payment method is saved
        self.payment.update_payment_status()
        self.payment.save(update_fields=['total_paid', 'balance_due', 'payment_status', 'completed_date'])

    def __str__(self):
        return f"{self.get_payment_method_display()} - {self.amount:.2f} ({self.get_status_display()})"


class Sale(models.Model):
    """Updated Sale model - minimal changes needed"""
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)

    # Fixed amount discount per item
    discount_amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=Decimal('0.00'), null=True, blank=True
    )

    total_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True
    )

    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True)
    delivery = models.ForeignKey('Delivery', on_delete=models.SET_NULL, null=True,
                                 blank=True)  # Assuming Delivery model exists
    receipt = models.ForeignKey('Receipt', on_delete=models.CASCADE,
                                related_name='sales')  # Assuming Receipt model exists
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True)
    sale_date = models.DateTimeField(auto_now_add=True)

    # Gift payment fields
    is_gift = models.BooleanField(
        default=False,
        help_text="Mark this item as a gift (0 Naira income, only admin can set)"
    )
    gift_reason = models.TextField(
        blank=True,
        null=True,
        help_text="Reason or note for giving this item as gift"
    )
    original_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Original selling price before marking as gift (for reporting)"
    )

    def calculate_total(self):
        """Calculate total price after applying a fixed discount PER LINE, not per item"""
        item_total = self.product.selling_price * self.quantity
        total_discount = self.discount_amount or Decimal('0.00')  # Don't multiply by quantity
        return item_total - total_discount

    def save(self, *args, **kwargs):
        is_new = self.pk is None  # capture before super() assigns the pk

        # Guard: prevent selling more than available stock on new sales
        if is_new and self.quantity > self.product.quantity:
            raise ValidationError(
                f"Insufficient stock for '{self.product.brand}'. "
                f"Available: {self.product.quantity}, requested: {self.quantity}."
            )

        # Clamp discount: stored discount_amount cannot exceed the line total
        item_total = self.product.selling_price * self.quantity
        if self.discount_amount and self.discount_amount > item_total:
            self.discount_amount = item_total

        self.total_price = self.calculate_total()

        with transaction.atomic():
            if self.receipt and not self.receipt.customer:
                self.receipt.customer = self.customer
                self.receipt.save()

            super().save(*args, **kwargs)

            # Decrement product stock atomically on first insert only
            if is_new:
                Product.objects.filter(pk=self.product_id).update(
                    quantity=F('quantity') - self.quantity
                )

            # After saving, trigger receipt recalculation to ensure totals are correct
            if self.receipt:
                self.receipt.save()

    def __str__(self):
        return f"{self.product} x {self.quantity} (Total: {self.total_price})"


# Additional utility model for tracking payment attempts/logs
class PaymentLog(models.Model):
    """Track all payment attempts and changes"""
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.CASCADE, related_name='logs')
    action = models.CharField(max_length=50)  # 'created', 'updated', 'confirmed', 'failed', etc.
    previous_status = models.CharField(max_length=20, blank=True, null=True)
    new_status = models.CharField(max_length=20, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.payment_method} - {self.action} at {self.timestamp}"


class PrinterConfiguration(models.Model):
    """Manage printer settings for different printer types"""
    PRINTER_TYPE_CHOICES = [
        ('barcode', 'Barcode Printer'),
        ('pos', 'POS Receipt Printer (80mm)'),
        ('a4', 'A4 Printer'),
    ]

    PAPER_SIZE_CHOICES = [
        ('80mm', '80mm (POS)'),
        ('58mm', '58mm (Small POS)'),
        ('a4', 'A4 (210mm x 297mm)'),
        ('letter', 'Letter (216mm x 279mm)'),
        ('custom', 'Custom Size'),
    ]

    name = models.CharField(max_length=100, help_text="Friendly name for this printer")
    printer_type = models.CharField(max_length=20, choices=PRINTER_TYPE_CHOICES)
    system_printer_name = models.CharField(
        max_length=255,
        help_text="Exact name as it appears in system printers"
    )
    paper_size = models.CharField(max_length=20, choices=PAPER_SIZE_CHOICES, default='80mm')
    paper_width_mm = models.IntegerField(
        null=True,
        blank=True,
        help_text="Paper width in mm (for custom sizes)"
    )
    paper_height_mm = models.IntegerField(
        null=True,
        blank=True,
        help_text="Paper height in mm (for custom sizes)"
    )
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    auto_print = models.BooleanField(
        default=False,
        help_text="Automatically print when generating documents"
    )

    # Printer-specific settings
    dpi = models.IntegerField(default=203, help_text="Printer DPI (dots per inch)")
    copies = models.IntegerField(default=1, help_text="Number of copies to print")

    # Barcode specific
    barcode_width = models.IntegerField(
        default=50,
        null=True,
        blank=True,
        help_text="Width in mm for barcode labels"
    )
    barcode_height = models.IntegerField(
        default=25,
        null=True,
        blank=True,
        help_text="Height in mm for barcode labels"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['printer_type', 'name']
        verbose_name = "Printer Configuration"
        verbose_name_plural = "Printer Configurations"

    def __str__(self):
        return f"{self.name} ({self.get_printer_type_display()})"

    def save(self, *args, **kwargs):
        # If this is set as default, unset other defaults of the same type
        if self.is_default:
            PrinterConfiguration.objects.filter(
                printer_type=self.printer_type,
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_default_printer(cls, printer_type):
        """Get the default printer for a specific type"""
        try:
            return cls.objects.get(printer_type=printer_type, is_default=True, is_active=True)
        except cls.DoesNotExist:
            # Return first active printer of this type
            return cls.objects.filter(printer_type=printer_type, is_active=True).first()
        except cls.MultipleObjectsReturned:
            # If multiple defaults exist (shouldn't happen), return the first one
            return cls.objects.filter(printer_type=printer_type, is_default=True, is_active=True).first()


class PrintJob(models.Model):
    """Track print jobs for monitoring and debugging"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('printing', 'Printing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    DOCUMENT_TYPE_CHOICES = [
        ('receipt', 'Receipt'),
        ('barcode', 'Barcode'),
        ('invoice', 'Invoice'),
        ('report', 'Report'),
        ('transfer', 'Transfer Document'),
    ]

    printer = models.ForeignKey(PrinterConfiguration, on_delete=models.SET_NULL, null=True)
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES)
    document_id = models.IntegerField(null=True, blank=True, help_text="ID of the document being printed")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    copies = models.IntegerField(default=1)
    error_message = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Print Job"
        verbose_name_plural = "Print Jobs"

    def __str__(self):
        return f"{self.document_type} - {self.status} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"


class StoreConfiguration(models.Model):
    """Global store configuration - supports multiple deployments"""

    # Store Identity
    store_name = models.CharField(
        max_length=200,
        default="Wrighteous Wearhouse",
        help_text="Your store/company name"
    )
    tagline = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Store tagline or slogan"
    )

    # Contact Information
    email = models.EmailField(
        default="wrighteouswarehouse@gmail.com",
        help_text="Main contact email"
    )
    phone = models.CharField(
        max_length=50,
        default="+234 903 547 7883",
        help_text="Contact phone number"
    )
    phone_2 = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Secondary phone number"
    )

    # Address Information
    address_line_1 = models.CharField(
        max_length=200,
        default="Suit 10/11 Amma Centre, Near AP Filling Station",
        help_text="Address line 1"
    )
    address_line_2 = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Address line 2 (optional)"
    )
    city = models.CharField(
        max_length=100,
        default="Garki",
        help_text="City"
    )
    state = models.CharField(
        max_length=100,
        default="Abuja",
        help_text="State/Province"
    )
    country = models.CharField(
        max_length=100,
        default="Nigeria",
        help_text="Country"
    )
    postal_code = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Postal/ZIP code"
    )

    # Business Information
    tax_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Tax ID / Business Registration Number"
    )
    website = models.URLField(
        blank=True,
        null=True,
        help_text="Store website URL"
    )

    # Branding
    logo = models.ImageField(
        upload_to='store_config/logos/',
        blank=True,
        null=True,
        help_text="Store logo (recommended: 500x500px)"
    )
    receipt_logo = models.ImageField(
        upload_to='store_config/receipt_logos/',
        blank=True,
        null=True,
        help_text="Logo for receipts (recommended: 300x100px)"
    )
    favicon = models.ImageField(
        upload_to='store_config/favicons/',
        blank=True,
        null=True,
        help_text="Favicon (recommended: 32x32px)"
    )

    # Currency & Localization
    currency_symbol = models.CharField(
        max_length=10,
        default="₦",
        help_text="Currency symbol (e.g., $, €, ₦)"
    )
    currency_code = models.CharField(
        max_length=3,
        default="NGN",
        help_text="Currency code (e.g., USD, EUR, NGN)"
    )
    timezone = models.CharField(
        max_length=50,
        default="Africa/Lagos",
        help_text="Timezone (e.g., Africa/Lagos, America/New_York)"
    )
    date_format = models.CharField(
        max_length=50,
        default="%B %d, %Y",
        help_text="Date format (Python strftime format)"
    )

    # Receipt Settings
    receipt_header_text = models.TextField(
        blank=True,
        null=True,
        help_text="Custom text to show at top of receipts"
    )
    receipt_footer_text = models.TextField(
        default="Thank you for shopping with us!",
        help_text="Footer text on receipts"
    )
    show_receipt_tax_id = models.BooleanField(
        default=False,
        help_text="Show tax ID on receipts"
    )

    # Business Hours
    business_hours = models.TextField(
        blank=True,
        null=True,
        help_text="Business hours (e.g., Mon-Fri: 9AM-6PM)"
    )

    # Social Media
    facebook_url = models.URLField(blank=True, null=True)
    instagram_url = models.URLField(blank=True, null=True)
    twitter_url = models.URLField(blank=True, null=True)

    # System Settings
    is_active = models.BooleanField(
        default=True,
        help_text="Is this configuration active?"
    )
    deployment_name = models.CharField(
        max_length=100,
        default="Main Store",
        help_text="Deployment identifier (e.g., Main Store, Branch 1)"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = "Store Configuration"
        verbose_name_plural = "Store Configurations"

    def __str__(self):
        return f"{self.store_name} - {self.deployment_name}"

    @classmethod
    def get_active_config(cls):
        """Get the active configuration"""
        try:
            return cls.objects.get(is_active=True)
        except cls.DoesNotExist:
            # Create default config if none exists
            return cls.objects.create(
                store_name="Wrighteous Wearhouse",
                deployment_name="Main Store"
            )
        except cls.MultipleObjectsReturned:
            # If multiple active configs, return the first one
            return cls.objects.filter(is_active=True).first()

    def get_full_address(self):
        """Get formatted full address"""
        parts = [
            self.address_line_1,
            self.address_line_2,
            self.city,
            self.state,
            self.postal_code,
            self.country
        ]
        return ", ".join([p for p in parts if p])

    def save(self, *args, **kwargs):
        # If this is set as active, deactivate others
        if self.is_active:
            StoreConfiguration.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class PrinterTaskMapping(models.Model):
    """Maps specific tasks/document types to printers"""
    TASK_CHOICES = [
        ('receipt_pos', 'POS Receipt (Thermal)'),
        ('receipt_a4', 'Receipt (A4 Format)'),
        ('barcode_label', 'Barcode Label'),
        ('barcode_sheet', 'Barcode Sheet (A4)'),
        ('invoice', 'Invoice'),
        ('transfer_document', 'Transfer Document'),
        ('sales_report', 'Sales Report'),
        ('financial_report', 'Financial Report'),
        ('product_list', 'Product List'),
        ('customer_receipt', 'Customer Receipt'),
        ('delivery_note', 'Delivery Note'),
    ]

    task_name = models.CharField(
        max_length=50,
        choices=TASK_CHOICES,
        unique=True,
        help_text="The specific task or document type"
    )
    printer = models.ForeignKey(
        PrinterConfiguration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Printer to use for this task"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Enable/disable this mapping"
    )
    auto_print = models.BooleanField(
        default=False,
        help_text="Automatically print when this task is triggered"
    )
    copies = models.IntegerField(
        default=1,
        help_text="Number of copies to print"
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Additional notes about this task mapping"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['task_name']
        verbose_name = "Printer Task Mapping"
        verbose_name_plural = "Printer Task Mappings"

    def __str__(self):
        printer_name = self.printer.name if self.printer else "No Printer"
        return f"{self.get_task_name_display()} → {printer_name}"

    @classmethod
    def get_printer_for_task(cls, task_name):
        """Get the configured printer for a specific task"""
        try:
            mapping = cls.objects.get(task_name=task_name, is_active=True)
            return mapping.printer
        except cls.DoesNotExist:
            return None

    @classmethod
    def should_auto_print(cls, task_name):
        """Check if auto-print is enabled for this task"""
        try:
            mapping = cls.objects.get(task_name=task_name, is_active=True)
            return mapping.auto_print and mapping.printer is not None
        except cls.DoesNotExist:
            return False

    @classmethod
    def get_copies_for_task(cls, task_name):
        """Get number of copies configured for this task"""
        try:
            mapping = cls.objects.get(task_name=task_name, is_active=True)
            return mapping.copies
        except cls.DoesNotExist:
            return 1


class PaymentMethodConfiguration(models.Model):
    """
    Configurable payment methods - manage available payment options through UI
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Payment method name (e.g., Cash, POS Moniepoint, Transfer Taj)"
    )
    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="Internal code for the payment method (e.g., cash, pos_moniepoint)"
    )
    display_name = models.CharField(
        max_length=100,
        help_text="Display name shown to users"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Enable/disable this payment method"
    )
    icon_class = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Bootstrap icon class (e.g., bi-cash, bi-credit-card)"
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Description or notes about this payment method"
    )
    requires_reference = models.BooleanField(
        default=False,
        help_text="Require reference number for this payment method"
    )
    sort_order = models.IntegerField(
        default=0,
        help_text="Display order (lower numbers appear first)"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_methods_created'
    )

    class Meta:
        verbose_name = "Payment Method Configuration"
        verbose_name_plural = "Payment Method Configurations"
        ordering = ['sort_order', 'display_name']

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.display_name} ({status})"

    @classmethod
    def get_active_methods(cls):
        """Get all active payment methods"""
        return cls.objects.filter(is_active=True).order_by('sort_order', 'display_name')

    @classmethod
    def get_payment_choices(cls):
        """Get payment method choices for forms"""
        methods = cls.get_active_methods()
        return [(method.code, method.display_name) for method in methods]


class TaxConfiguration(models.Model):
    """
    Tax Configuration - Comprehensive tax management system

    This model manages tax rates and calculation methods for sales transactions.
    Supports both INCLUSIVE and EXCLUSIVE tax calculations.

    ============================================================================
    TAX CALCULATION METHODS:
    ============================================================================

    1. INCLUSIVE TAX (tax already in the price):
       - Product prices in the system already include tax
       - Tax is extracted from the price, not added to it
       - Example: Product price = ₦10,750 (including 7.5% VAT)
         * Tax amount = ₦10,750 - (₦10,750 / 1.075) = ₦750
         * Base price (without tax) = ₦10,000
         * Customer pays = ₦10,750 (no additional tax added)
         * Tax collected for reporting = ₦750

    2. EXCLUSIVE TAX (tax added on top of price):
       - Product prices in the system do NOT include tax
       - Tax is calculated and added to the final total
       - Example: Product price = ₦10,000 + 7.5% VAT
         * Tax amount = ₦10,000 × 0.075 = ₦750
         * Customer pays = ₦10,000 + ₦750 = ₦10,750
         * Tax collected for reporting = ₦750

    ============================================================================
    SALES FLOW WITH TAXES:
    ============================================================================

    During checkout (sell_product view):
    1. Calculate items subtotal (sum of all products)
    2. Add delivery cost
    3. Apply discounts (bill discount + loyalty discount)
    4. Calculate taxable amount (items after discount, excluding delivery)
    5. For each active tax:
       - Calculate tax amount based on method (inclusive/exclusive)
       - Store tax details in receipt.tax_details (JSON)
    6. For INCLUSIVE taxes: Extract tax amount but DON'T add to total
    7. For EXCLUSIVE taxes: Add tax amount to total
    8. Store in Receipt:
       - subtotal: Items total (before delivery, before tax)
       - tax_amount: Total tax (both inclusive and exclusive)
       - tax_details: JSON with full breakdown
       - total_with_delivery: Grand total (with exclusive tax added)

    ============================================================================
    TAX REPORTING:
    ============================================================================

    The tax report (/reports/tax/) shows:
    - Total tax collected (inclusive + exclusive)
    - Breakdown by tax type
    - Inclusive tax: Tax that was in the prices
    - Exclusive tax: Tax that was added to prices
    - Receipt-level details with full tax breakdown

    This makes it easy to file tax returns and track tax liability.
    """
    TAX_TYPE_CHOICES = [
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
    ]

    CALCULATION_METHOD_CHOICES = [
        ('inclusive', 'Inclusive (tax included in price)'),
        ('exclusive', 'Exclusive (tax added to price)'),
    ]

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Tax name (e.g., VAT, Sales Tax, GST)"
    )
    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="Short code for the tax (e.g., VAT, ST, GST)"
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Description or notes about this tax"
    )

    # Tax Rate
    tax_type = models.CharField(
        max_length=20,
        choices=TAX_TYPE_CHOICES,
        default='percentage',
        help_text="Type of tax calculation"
    )
    rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Tax rate (percentage or fixed amount)"
    )

    # Calculation Method
    calculation_method = models.CharField(
        max_length=20,
        choices=CALCULATION_METHOD_CHOICES,
        default='exclusive',
        help_text="How tax is calculated"
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Enable/disable this tax"
    )

    # Display Settings
    display_on_receipt = models.BooleanField(
        default=True,
        help_text="Show tax breakdown on receipts"
    )
    sort_order = models.IntegerField(
        default=0,
        help_text="Display order (lower numbers appear first)"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='taxes_created'
    )

    class Meta:
        verbose_name = "Tax Configuration"
        verbose_name_plural = "Tax Configurations"
        ordering = ['sort_order', 'name']

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        method = "Incl." if self.calculation_method == 'inclusive' else "Excl."
        return f"{self.name} - {self.rate}% ({method}) - {status}"

    @classmethod
    def get_active_taxes(cls):
        """Get all active taxes"""
        return cls.objects.filter(is_active=True).order_by('sort_order', 'name')

    def calculate_tax_amount(self, subtotal):
        """
        Calculate tax amount based on subtotal

        Args:
            subtotal: The amount to calculate tax on

        Returns:
            Decimal: The tax amount
        """
        if self.tax_type == 'percentage':
            if self.calculation_method == 'inclusive':
                # Tax is already included in the price
                # Tax = Subtotal - (Subtotal / (1 + rate/100))
                tax_amount = subtotal - (subtotal / (Decimal('1') + (self.rate / Decimal('100'))))
            else:
                # Tax is added to the price
                # Tax = Subtotal * (rate/100)
                tax_amount = subtotal * (self.rate / Decimal('100'))
        else:
            # Fixed amount tax
            tax_amount = self.rate

        return tax_amount.quantize(Decimal('0.01'))

    def calculate_total_with_tax(self, subtotal):
        """
        Calculate total amount including tax

        Args:
            subtotal: The base amount

        Returns:
            tuple: (total_amount, tax_amount)
        """
        tax_amount = self.calculate_tax_amount(subtotal)

        if self.calculation_method == 'inclusive':
            # Tax is already in the subtotal
            total_amount = subtotal
        else:
            # Add tax to subtotal
            total_amount = subtotal + tax_amount

        return total_amount.quantize(Decimal('0.01')), tax_amount


class ActivityLog(models.Model):
    """
    Comprehensive activity logging for all user actions in the system
    """

    ACTION_CHOICES = [
        # Authentication
        ('login', 'User Login'),
        ('logout', 'User Logout'),
        ('failed_login', 'Failed Login Attempt'),

        # Product Management
        ('product_create', 'Product Created'),
        ('product_update', 'Product Updated'),
        ('product_delete', 'Product Deleted'),
        ('product_view', 'Product Viewed'),

        # Sales & Transactions
        ('sale_create', 'Sale Created'),
        ('sale_cancel', 'Sale Cancelled'),
        ('receipt_view', 'Receipt Viewed'),
        ('receipt_download', 'Receipt Downloaded'),
        ('receipt_email', 'Receipt Emailed'),

        # Customer Management
        ('customer_create', 'Customer Created'),
        ('customer_update', 'Customer Updated'),
        ('customer_delete', 'Customer Deleted'),

        # Inventory
        ('transfer_create', 'Transfer Created'),
        ('transfer_update', 'Transfer Updated'),
        ('quantity_update', 'Quantity Updated'),

        # Configuration
        ('config_update', 'Configuration Updated'),
        ('printer_config', 'Printer Configuration Changed'),

        # Reports
        ('report_view', 'Report Viewed'),
        ('report_download', 'Report Downloaded'),
        ('report_email', 'Report Emailed'),

        # User Management
        ('user_create', 'User Created'),
        ('user_update', 'User Updated'),
        ('user_delete', 'User Deleted'),

        # System
        ('backup_create', 'Backup Created'),
        ('backup_restore', 'Backup Restored'),
        ('settings_change', 'Settings Changed'),

        # Other
        ('other', 'Other Action'),
    ]

    # Who performed the action
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    username = models.CharField(max_length=150, blank=True)  # Store username in case user is deleted

    # What action was performed
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    action_display = models.CharField(max_length=200, blank=True)  # Human-readable description

    # Details about the action
    description = models.TextField(blank=True)  # Detailed description of what happened
    model_name = models.CharField(max_length=100, blank=True)  # Which model was affected
    object_id = models.CharField(max_length=100, blank=True)  # ID of the affected object
    object_repr = models.CharField(max_length=200, blank=True)  # String representation of the object

    # Request metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)  # Browser/device info

    # Additional data (stored as JSON text for SQL Server compatibility)
    extra_data = models.TextField(null=True, blank=True)  # Store JSON as text

    # Status
    success = models.BooleanField(default=True)  # Whether the action succeeded
    error_message = models.TextField(blank=True)  # Error message if failed

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['action', '-created_at']),
        ]

    def __str__(self):
        user_str = self.username or 'Unknown'
        return f"{user_str} - {self.get_action_display()} at {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    def get_extra_data(self):
        """Return extra_data as a Python dictionary"""
        if self.extra_data:
            import json
            try:
                return json.loads(self.extra_data)
            except json.JSONDecodeError:
                return {}
        return {}

    def save(self, *args, **kwargs):
        # Auto-populate username if not set
        if self.user and not self.username:
            self.username = self.user.username

        # Auto-populate action_display if not set
        if not self.action_display:
            self.action_display = self.get_action_display()

        super().save(*args, **kwargs)

    @classmethod
    def log_activity(cls, user, action, description='', model_name='', object_id='',
                     object_repr='', ip_address=None, user_agent='', extra_data=None,
                     success=True, error_message='', request=None):
        """
        Convenience method to create activity log entries

        Usage:
            ActivityLog.log_activity(
                user=request.user,
                action='product_create',
                description='Created new product: Nike Shoes',
                model_name='Product',
                object_id=product.id,
                object_repr=str(product),
                request=request
            )
        """
        # Extract IP and user agent from request if provided
        if request:
            if not ip_address:
                x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                if x_forwarded_for:
                    ip_address = x_forwarded_for.split(',')[0]
                else:
                    ip_address = request.META.get('REMOTE_ADDR')

            if not user_agent:
                user_agent = request.META.get('HTTP_USER_AGENT', '')

        # Serialize extra_data to JSON string if provided
        import json
        extra_data_json = None
        if extra_data:
            extra_data_json = json.dumps(extra_data)

        return cls.objects.create(
            user=user,
            username=user.username if user else '',
            action=action,
            description=description,
            model_name=model_name,
            object_id=str(object_id) if object_id else '',
            object_repr=object_repr,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_data=extra_data_json,
            success=success,
            error_message=error_message
        )


# =====================================
# CUSTOMER LOYALTY PROGRAM MODELS
# =====================================

class LoyaltyConfiguration(models.Model):
    """
    Configurable loyalty program settings - one active config per business
    """
    POINT_CALCULATION_TYPES = [
        ('per_transaction', 'Points per Transaction'),
        ('per_amount', 'Points per Amount Spent'),
        ('combined', 'Combined (Transaction + Amount)'),
        ('transaction_count_discount', 'Transaction Count Discount'),
        ('item_count_discount', 'Item Count Discount'),
    ]

    CUSTOMER_TYPE_CHOICES = [
        ('all', 'All Customers'),
        ('regular', 'Regular Customers'),
        ('vip', 'VIP Customers'),
    ]

    # Basic Configuration
    program_name = models.CharField(
        max_length=200,
        default="Loyalty Rewards Program",
        help_text="Name of your loyalty program"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Enable/disable loyalty program"
    )

    # Point Earning Rules
    calculation_type = models.CharField(
        max_length=30,
        choices=POINT_CALCULATION_TYPES,
        default='combined',
        help_text="How points are calculated"
    )

    # Customer Type
    customer_type = models.CharField(
        max_length=20,
        choices=CUSTOMER_TYPE_CHOICES,
        default='all',
        help_text="Apply this loyalty configuration to specific customer types"
    )

    # Per Transaction Points
    points_per_transaction = models.IntegerField(
        default=1,
        help_text="Points earned per transaction (regardless of amount)"
    )

    # Per Amount Spent Points
    points_per_currency_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('1.00'),
        help_text="Points earned per currency unit spent (e.g., 1 point per ₦100)"
    )
    currency_unit_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('100.00'),
        help_text="Currency amount for points calculation (e.g., ₦100)"
    )

    # Point Redemption Rules
    points_to_currency_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('1.00'),
        help_text="How much 1 point is worth in currency (e.g., 100 points = ₦100)"
    )
    minimum_points_for_redemption = models.IntegerField(
        default=100,
        help_text="Minimum points required before customer can redeem"
    )
    maximum_discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('50.00'),
        help_text="Maximum percentage of transaction that can be paid with points"
    )

    # Transaction/Item Count Discount Rules
    required_transaction_count = models.IntegerField(
        default=0,
        help_text="Number of transactions required for discount (for transaction_count_discount type)"
    )
    transaction_discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Discount percentage on next transaction after reaching count"
    )
    required_item_count = models.IntegerField(
        default=0,
        help_text="Number of items purchased required for discount (for item_count_discount type)"
    )
    item_discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Discount percentage per item threshold reached"
    )

    # Point Expiration
    points_expire = models.BooleanField(
        default=False,
        help_text="Do points expire after a certain period?"
    )
    points_expiry_days = models.IntegerField(
        default=365,
        null=True,
        blank=True,
        help_text="Number of days before points expire"
    )

    # Email Notifications
    send_welcome_email = models.BooleanField(
        default=True,
        help_text="Send welcome email when customer joins program"
    )
    send_points_earned_email = models.BooleanField(
        default=True,
        help_text="Send email after each transaction with points update"
    )
    send_points_redeemed_email = models.BooleanField(
        default=True,
        help_text="Send email when points are redeemed"
    )
    send_expiry_reminder_email = models.BooleanField(
        default=True,
        help_text="Send reminder email before points expire"
    )
    expiry_reminder_days = models.IntegerField(
        default=30,
        null=True,
        blank=True,
        help_text="Days before expiry to send reminder"
    )

    # Bonus Multipliers
    enable_bonus_multipliers = models.BooleanField(
        default=False,
        help_text="Enable special bonus periods or tiers"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='loyalty_configs_created'
    )

    class Meta:
        verbose_name = "Loyalty Configuration"
        verbose_name_plural = "Loyalty Configurations"
        ordering = ['-created_at']

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.program_name} ({status})"

    def save(self, *args, **kwargs):
        # Only one active configuration at a time
        if self.is_active:
            LoyaltyConfiguration.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active_config(cls):
        """Get the currently active loyalty configuration.

        - Returns the active config if one exists.
        - If configs exist but none is active, returns the most recently
          created one WITHOUT activating it (callers all check is_active).
        - Only seeds a default config (inactive) when the table is empty.
        """
        try:
            return cls.objects.get(is_active=True)
        except cls.DoesNotExist:
            most_recent = cls.objects.order_by('-id').first()
            if most_recent is not None:
                return most_recent  # inactive; callers check is_active
            return cls.objects.create(
                program_name="Loyalty Rewards Program",
                is_active=False,
                customer_type='all',
            )
        except cls.MultipleObjectsReturned:
            return cls.objects.filter(is_active=True).first()

    def calculate_points_earned(self, transaction_amount):
        """
        Calculate points earned based on transaction amount

        Args:
            transaction_amount: Decimal amount of the transaction

        Returns:
            Integer number of points earned
        """
        from decimal import Decimal
        points = 0

        if self.calculation_type == 'per_transaction':
            points = self.points_per_transaction

        elif self.calculation_type == 'per_amount':
            # Calculate based on currency units
            units = Decimal(str(transaction_amount)) / Decimal(str(self.currency_unit_value))
            points = int(units * Decimal(str(self.points_per_currency_unit)))

        elif self.calculation_type == 'combined':
            # Both transaction points and amount-based points
            points = self.points_per_transaction
            units = Decimal(str(transaction_amount)) / Decimal(str(self.currency_unit_value))
            points += int(units * Decimal(str(self.points_per_currency_unit)))

        return max(0, points)  # Ensure non-negative

    def calculate_discount_from_points(self, points):
        """
        Calculate the monetary value of points

        Args:
            points: Integer number of points

        Returns:
            Decimal value in currency
        """
        return Decimal(points) * self.points_to_currency_rate

    def get_maximum_redeemable_amount(self, transaction_amount):
        """
        Calculate maximum amount that can be paid with points for a transaction

        Args:
            transaction_amount: Decimal amount of the transaction

        Returns:
            Decimal maximum discount amount
        """
        return transaction_amount * (self.maximum_discount_percentage / Decimal('100'))


class CustomerLoyaltyAccount(models.Model):
    """
    Customer loyalty points account - tracks points balance and history
    """
    customer = models.OneToOneField(
        Customer,
        on_delete=models.CASCADE,
        related_name='loyalty_account'
    )

    # Points Balance
    total_points_earned = models.IntegerField(
        default=0,
        help_text="Lifetime total points earned"
    )
    total_points_redeemed = models.IntegerField(
        default=0,
        help_text="Lifetime total points redeemed"
    )
    current_balance = models.IntegerField(
        default=0,
        help_text="Current available points"
    )

    # Membership
    enrollment_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Is loyalty account active?"
    )

    # Tier/Status (for future expansion)
    tier = models.CharField(
        max_length=50,
        default='Bronze',
        help_text="Membership tier (Bronze, Silver, Gold, Platinum)"
    )

    # Transaction and Item Tracking
    transaction_count = models.IntegerField(
        default=0,
        help_text="Total number of transactions made"
    )
    item_count = models.IntegerField(
        default=0,
        help_text="Total number of items purchased"
    )
    discount_count = models.IntegerField(
        default=0,
        help_text="Number of times discount has been applied"
    )
    discount_eligible = models.BooleanField(
        default=False,
        help_text="Whether customer is currently eligible for transaction count discount"
    )

    # Metadata
    last_transaction_date = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Customer Loyalty Account"
        verbose_name_plural = "Customer Loyalty Accounts"
        ordering = ['-current_balance']

    def __str__(self):
        return f"{self.customer.name} - {self.current_balance} points"

    def add_points(self, points, description="", related_receipt=None):
        """Add points to account"""
        if points > 0:
            self.total_points_earned += points
            self.current_balance += points
            self.last_transaction_date = timezone.now()
            self.save()

            # Create transaction record
            LoyaltyTransaction.objects.create(
                loyalty_account=self,
                transaction_type='earned',
                points=points,
                description=description,
                receipt=related_receipt
            )

    def redeem_points(self, points, description="", related_receipt=None):
        """Redeem points from account"""
        if points > 0 and self.current_balance >= points:
            self.total_points_redeemed += points
            self.current_balance -= points
            self.last_transaction_date = timezone.now()
            self.save()

            # Create transaction record
            LoyaltyTransaction.objects.create(
                loyalty_account=self,
                transaction_type='redeemed',
                points=points,
                description=description,
                receipt=related_receipt
            )
            return True
        return False

    def get_redeemable_value(self):
        """Get currency value of current points"""
        config = LoyaltyConfiguration.get_active_config()
        return config.calculate_discount_from_points(self.current_balance)

    def can_redeem_points(self, points):
        """Check if customer can redeem specified points"""
        config = LoyaltyConfiguration.get_active_config()
        return (
            self.is_active and
            self.current_balance >= points and
            points >= config.minimum_points_for_redemption
        )


class LoyaltyTransaction(models.Model):
    """
    Record of all loyalty point transactions
    """
    TRANSACTION_TYPES = [
        ('earned', 'Points Earned'),
        ('redeemed', 'Points Redeemed'),
        ('expired', 'Points Expired'),
        ('adjusted', 'Manual Adjustment'),
        ('bonus', 'Bonus Points'),
    ]

    loyalty_account = models.ForeignKey(
        CustomerLoyaltyAccount,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPES
    )
    points = models.IntegerField(help_text="Points amount (positive or negative)")
    balance_after = models.IntegerField(help_text="Balance after this transaction")
    description = models.TextField(blank=True)

    # Link to sale/receipt
    receipt = models.ForeignKey(
        Receipt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='loyalty_transactions'
    )

    # Monetary value at time of transaction
    monetary_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Currency value of points for this transaction"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Expiration tracking
    expires_at = models.DateTimeField(null=True, blank=True)
    is_expired = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Loyalty Transaction"
        verbose_name_plural = "Loyalty Transactions"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['loyalty_account', '-created_at']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['receipt']),
        ]

    def __str__(self):
        return f"{self.loyalty_account.customer.name} - {self.transaction_type} {self.points} points"

    def save(self, *args, **kwargs):
        # Set balance_after
        if not self.balance_after:
            self.balance_after = self.loyalty_account.current_balance

        # Calculate expiration date if applicable
        if not self.expires_at and self.transaction_type == 'earned':
            config = LoyaltyConfiguration.get_active_config()
            if config.points_expire and config.points_expiry_days:
                from datetime import timedelta
                self.expires_at = timezone.now() + timedelta(days=config.points_expiry_days)

        super().save(*args, **kwargs)


class PartialPayment(models.Model):
    """Track partial/installment payments for a receipt"""
    receipt = models.ForeignKey(
        'Receipt',
        on_delete=models.CASCADE,
        related_name='partial_payments',
        help_text="The receipt this payment is for"
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Amount paid in this installment"
    )
    payment_method = models.CharField(
        max_length=50,
        help_text="Payment method used (Cash, Card, Transfer, etc.)"
    )
    payment_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Notes about this payment"
    )
    received_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='partial_payments_received',
        help_text="Staff member who received this payment"
    )

    class Meta:
        verbose_name = "Partial Payment"
        verbose_name_plural = "Partial Payments"
        ordering = ['-payment_date']

    def __str__(self):
        return f"{self.receipt.receipt_number} - {self.amount} on {self.payment_date}"


class Return(models.Model):
    """Track product returns and refunds"""
    RETURN_REASON_CHOICES = [
        ('defective', 'Defective/Damaged'),
        ('wrong_item', 'Wrong Item'),
        ('wrong_size', 'Wrong Size'),
        ('changed_mind', 'Changed Mind'),
        ('not_as_described', 'Not as Described'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]

    REFUND_TYPE_CHOICES = [
        ('cash', 'Cash Refund'),
        ('store_credit', 'Store Credit'),
    ]

    return_number = models.CharField(max_length=50, unique=True, blank=True)
    receipt = models.ForeignKey(
        'Receipt',
        on_delete=models.CASCADE,
        related_name='returns'
    )
    customer = models.ForeignKey(
        'Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    restocking_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    return_reason = models.CharField(
        max_length=50,
        choices=RETURN_REASON_CHOICES,
        default='other'
    )
    reason_notes = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    return_date = models.DateTimeField(auto_now_add=True)
    approved_date = models.DateTimeField(blank=True, null=True)
    refund_type = models.CharField(
        max_length=20,
        choices=REFUND_TYPE_CHOICES,
        blank=True,
        null=True
    )
    refund_method = models.CharField(max_length=50, blank=True, null=True)
    refund_reference = models.CharField(max_length=100, blank=True, null=True)
    refunded_date = models.DateTimeField(blank=True, null=True)

    # Staff tracking
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='returns_processed'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='returns_approved'
    )

    class Meta:
        ordering = ['-return_date']
        indexes = [
            models.Index(fields=['-return_date']),
            models.Index(fields=['receipt']),
            models.Index(fields=['customer']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Return {self.return_number} - {self.receipt.receipt_number}"

    def save(self, *args, **kwargs):
        if not self.return_number:
            from datetime import datetime
            from django.db import transaction

            current_year = datetime.now().year
            current_month = datetime.now().month

            with transaction.atomic():
                last_return = (
                    Return.objects.filter(
                        return_number__endswith=f'/{current_month:02d}/{current_year}'
                    )
                    .select_for_update()
                    .order_by('id')
                    .last()
                )

                if last_return:
                    last_number = int(last_return.return_number.split('/')[0][3:])
                    new_number = last_number + 1
                else:
                    new_number = 1

                self.return_number = f'RET{new_number:03d}/{current_month:02d}/{current_year}'

        super().save(*args, **kwargs)


class ReturnItem(models.Model):
    """Individual items in a return transaction"""
    CONDITION_CHOICES = [
        ('new', 'Like New'),
        ('good', 'Good Condition'),
        ('fair', 'Fair Condition'),
        ('damaged', 'Damaged'),
        ('defective', 'Defective'),
    ]

    return_transaction = models.ForeignKey(
        'Return',
        on_delete=models.CASCADE,
        related_name='return_items'
    )
    original_sale = models.ForeignKey(
        'Sale',
        on_delete=models.CASCADE,
        related_name='returns'
    )
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    quantity_sold = models.IntegerField()
    quantity_returned = models.IntegerField()
    original_selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    new_selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True
    )
    original_total = models.DecimalField(max_digits=10, decimal_places=2)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2)
    item_condition = models.CharField(
        max_length=20,
        choices=CONDITION_CHOICES,
        default='new'
    )
    restock_to_inventory = models.BooleanField(default=True)
    restocked = models.BooleanField(default=False)
    restocked_date = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.product.product_name} - Qty: {self.quantity_returned}"


class StoreCredit(models.Model):
    """Store credit that can be issued from returns or other sources"""
    credit_number = models.CharField(max_length=50, unique=True, blank=True)
    customer = models.ForeignKey(
        'Customer',
        on_delete=models.CASCADE,
        related_name='store_credits'
    )
    original_amount = models.DecimalField(max_digits=10, decimal_places=2)
    remaining_balance = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    issued_date = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    # Link to return if issued from a return
    return_transaction = models.OneToOneField(
        'Return',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    issued_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True
    )

    class Meta:
        ordering = ['-issued_date']
        indexes = [
            models.Index(fields=['customer', 'is_active']),
            models.Index(fields=['-issued_date']),
        ]

    def __str__(self):
        return f"{self.credit_number} - {self.customer.name} - Balance: {self.remaining_balance}"

    def save(self, *args, **kwargs):
        if not self.credit_number:
            from datetime import datetime
            from django.db import transaction

            current_year = datetime.now().year
            current_month = datetime.now().month

            with transaction.atomic():
                last_credit = (
                    StoreCredit.objects.filter(
                        credit_number__endswith=f'/{current_month:02d}/{current_year}'
                    )
                    .select_for_update()
                    .order_by('id')
                    .last()
                )

                if last_credit:
                    last_number = int(last_credit.credit_number.split('/')[0][2:])
                    new_number = last_number + 1
                else:
                    new_number = 1

                self.credit_number = f'SC{new_number:03d}/{current_month:02d}/{current_year}'

        super().save(*args, **kwargs)


class StoreCreditUsage(models.Model):
    """Track usage of store credits"""
    store_credit = models.ForeignKey(
        'StoreCredit',
        on_delete=models.CASCADE,
        related_name='usages'
    )
    receipt = models.ForeignKey('Receipt', on_delete=models.CASCADE)
    amount_used = models.DecimalField(max_digits=10, decimal_places=2)
    used_date = models.DateTimeField(auto_now_add=True)
    used_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True
    )

    class Meta:
        ordering = ['-used_date']

    def __str__(self):
        return f"{self.store_credit.credit_number} - {self.amount_used} used on {self.used_date}"

    def save(self, *args, **kwargs):
        # Deduct from store credit balance when used
        if not self.pk:  # Only on creation
            self.store_credit.remaining_balance -= self.amount_used
            if self.store_credit.remaining_balance <= 0:
                self.store_credit.is_active = False
            self.store_credit.save()

        super().save(*args, **kwargs)


# =====================================
# PRODUCT DRAFT MODEL
# =====================================

class ProductDraft(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='product_drafts')
    name = models.CharField(max_length=100, default='Draft')
    form_data = models.JSONField()          # serialised formset field values
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user.username} \u2013 {self.name} ({self.updated_at:%Y-%m-%d %H:%M})"


# =====================================
# REORDER CART MODEL
# =====================================

class ReorderCartItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reorder_cart')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')
        ordering = ['added_at']

    def __str__(self):
        return f"{self.user.username} \u2013 {self.product.brand}"