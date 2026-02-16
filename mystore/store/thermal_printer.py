"""
Thermal Printer Module using python-escpos
Direct printing to thermal receipt printers (80mm)
Supports XPrinter 80 and similar ESC/POS thermal printers
"""

import logging
import os
import json
from decimal import Decimal
from datetime import datetime
from django.utils import timezone
from django.conf import settings
from escpos.printer import Win32Raw
from escpos.exceptions import Error as EscposError
import win32print

# Import PIL for logo support
try:
    from PIL import Image
except ImportError:
    Image = None
    print("Warning: PIL/Pillow not installed. Logo printing will be disabled.")

logger = logging.getLogger(__name__)


class ThermalPrinter:
    """Handle direct thermal printing using ESC/POS commands"""

    def __init__(self, printer_name=None):
        """
        Initialize thermal printer

        Args:
            printer_name: Name of the printer. If None, uses default printer
        """
        if printer_name is None:
            try:
                printer_name = win32print.GetDefaultPrinter()
            except Exception as e:
                logger.error(f"Failed to get default printer: {e}")
                raise Exception("No default printer found. Please set a default printer.")

        self.printer_name = printer_name
        self.printer = None

    def _sanitize_currency_symbol(self, symbol):
        """
        Sanitize currency symbol for thermal printer compatibility
        Thermal printers often don't support Unicode characters like ₦

        Args:
            symbol: Currency symbol string

        Returns:
            ASCII-compatible currency symbol
        """
        # Replace common Unicode currency symbols with ASCII equivalents
        replacements = {
            '₦': 'N',      # Naira
            '€': 'EUR',    # Euro
            '£': 'GBP',    # Pound
            '¥': 'YEN',    # Yen
            '₹': 'Rs',     # Rupee
            '$': '$',      # Dollar (already ASCII)
        }

        # Return replacement if found, otherwise return the symbol as-is
        return replacements.get(symbol, symbol)

    def connect(self):
        """Connect to the thermal printer"""
        try:
            # Close existing printer connection if any
            if self.printer is not None:
                try:
                    self.printer.close()
                except:
                    pass

            self.printer = Win32Raw(self.printer_name)
            # Explicitly open the printer job
            if hasattr(self.printer, 'open') and callable(self.printer.open):
                self.printer.open()
            logger.info(f"Connected to thermal printer: {self.printer_name}")
            return True
        except EscposError as e:
            logger.error(f"Failed to connect to printer {self.printer_name}: {e}")
            raise Exception(f"Failed to connect to printer: {e}")

    def _print_centered(self, text, style='normal'):
        """Print centered text with style"""
        if style == 'title':
            self.printer.set(align='center', bold=True, width=2, height=2)
        elif style == 'header':
            self.printer.set(align='center', bold=True)
        else:
            self.printer.set(align='center')

        self.printer.text(text + '\n')
        self.printer.set()  # Reset to defaults

    def _print_left(self, text, bold=False):
        """Print left-aligned text"""
        self.printer.set(align='left', bold=bold)
        self.printer.text(text + '\n')
        self.printer.set()

    def _print_line(self, left_text, right_text, bold=False):
        """Print a line with left and right aligned text"""
        # 48 characters is typical for 80mm thermal printers at normal width
        max_width = 48
        left_len = len(str(left_text))
        right_len = len(str(right_text))
        spaces = max_width - left_len - right_len

        if spaces < 1:
            # If too long, truncate left text
            left_text = str(left_text)[:max_width - right_len - 3] + "..."
            spaces = 1

        line = f"{left_text}{' ' * spaces}{right_text}"
        self.printer.set(align='left', bold=bold)
        self.printer.text(line + '\n')
        self.printer.set()

    def _print_divider(self, style='dashed'):
        """Print a divider line"""
        if style == 'dashed':
            self.printer.text('-' * 48 + '\n')
        elif style == 'double':
            self.printer.text('=' * 48 + '\n')
        else:
            self.printer.text('_' * 48 + '\n')

    def _get_logo_path(self, store_config=None):
        """Get the path to the logo file"""
        try:
            logo_paths = []

            # Check store config for receipt_logo or logo
            if store_config:
                if hasattr(store_config, 'receipt_logo') and store_config.receipt_logo:
                    logo_paths.append(store_config.receipt_logo.path)
                elif hasattr(store_config, 'logo') and store_config.logo:
                    logo_paths.append(store_config.logo.path)

            # Check default static locations - prioritize Receipt Logo.png
            possible_static_paths = [
                os.path.join(settings.BASE_DIR, 'mystore', 'static', 'img', 'Receipt Logo.png'),
                os.path.join(settings.STATIC_ROOT or '', 'img', 'Receipt Logo.png'),
                os.path.join(settings.BASE_DIR, 'static', 'img', 'Receipt Logo.png'),
                os.path.join(settings.STATIC_ROOT or '', 'img', 'W2logo.jpeg'),
                os.path.join(settings.BASE_DIR, 'mystore', 'static', 'img', 'W2logo.jpeg'),
                os.path.join(settings.BASE_DIR, 'static', 'img', 'W2logo.jpeg'),
            ]

            if hasattr(settings, 'STATICFILES_DIRS') and settings.STATICFILES_DIRS:
                for static_dir in settings.STATICFILES_DIRS:
                    possible_static_paths.insert(0, os.path.join(static_dir, 'img', 'Receipt Logo.png'))
                    possible_static_paths.append(os.path.join(static_dir, 'img', 'W2logo.jpeg'))

            logo_paths.extend(possible_static_paths)

            # Return first existing path
            for path in logo_paths:
                if path and os.path.exists(path):
                    logger.info(f"Found logo at: {path}")
                    return path

            logger.warning(f"Logo not found in any of these locations: {logo_paths}")
            return None

        except Exception as e:
            logger.error(f"Error getting logo path: {e}")
            return None

    def _print_logo(self, store_config=None, printer_width=576):
        """
        Print the company logo centered on thermal printer

        Args:
            store_config: StoreConfiguration object
            printer_width: Width in pixels (384 for 58mm, 576 for 80mm)
        """
        try:
            if Image is None:
                logger.warning("PIL/Pillow not installed. Skipping logo printing.")
                return False

            logo_path = self._get_logo_path(store_config)
            if not logo_path:
                logger.warning("Logo file not found. Skipping logo printing.")
                return False

            # Open and process the image
            img = Image.open(logo_path)

            # Convert to grayscale first
            img = img.convert('L')

            # Resize to fit printer width (use 30% of width for compact size - matching template)
            target_width = int(printer_width * 0.30)
            width_percent = (target_width / float(img.size[0]))
            new_height = int((float(img.size[1]) * float(width_percent)))
            img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)

            # Convert to pure black and white (1-bit)
            img = img.convert('1')

            # Print the image centered - pad image to center it manually
            # (avoids "media.width.pixel not set" warning from center=True)
            padded_width = printer_width
            left_padding = (padded_width - img.size[0]) // 2
            padded_img = Image.new('1', (padded_width, img.size[1]), 1)  # 1 = white
            padded_img.paste(img, (left_padding, 0))
            self.printer.image(padded_img)
            self.printer.text('\n')
            logger.info("Logo printed successfully")
            return True

        except Exception as e:
            logger.error(f"Error printing logo: {e}")
            import traceback
            traceback.print_exc()
            return False

    def print_payment_receipt(self, receipt, sales, store_config=None, items=None):
        """
        Print a payment receipt for regular sales - compact design

        Args:
            receipt: Receipt object
            sales: List of Sale objects
            store_config: StoreConfiguration object (optional)
            items: Unified items list (products + services) - optional
        """
        try:
            self.connect()
            logger.info("Printer connected and job opened successfully")

            # Get currency symbol and sanitize for thermal printer
            currency_symbol = store_config.currency_symbol if store_config else "₦"
            currency_symbol = self._sanitize_currency_symbol(currency_symbol)
            PRINTER_WIDTH = 576  # 80mm printer

            # === HEADER ===
            # Date/time at the very top - centered
            date_time = receipt.date.strftime("%m/%d/%Y, %I:%M %p")
            self._print_centered(date_time)
            self.printer.text('\n')

            # === LOGO IN BOX ===
            # Print logo centered with visual separation
            self._print_logo(store_config, PRINTER_WIDTH)
            self.printer.text('\n')

            # === STORE INFORMATION ===
            # Store name (bold, larger)
            if store_config and store_config.store_name:
                self.printer.set(align='center', bold=True)
                self.printer.text(store_config.store_name + '\n')
                self.printer.set()

            # Store contact info
            if store_config:
                if store_config.address_line_1:
                    self._print_centered(store_config.address_line_1[:40])
                if store_config.address_line_2:
                    self._print_centered(store_config.address_line_2[:40])
                if store_config.phone:
                    self._print_centered(f"Tel: {store_config.phone}")
                if store_config.email:
                    self._print_centered(store_config.email)

            self._print_divider('dashed')

            # === RECEIPT TYPE ===
            self.printer.set(bold=True, align='center')
            # Check if this is a partial payment (deposit)
            if hasattr(receipt, 'payment_status') and receipt.payment_status == 'partial':
                self.printer.text("Deposit Receipt\n")
            else:
                self.printer.text("Sales Receipt\n")
            self.printer.set()

            # Transaction details - matching template exactly
            full_date_time = receipt.date.strftime("%m/%d/%Y %I:%M %p")
            self._print_line("Date:", full_date_time)
            self._print_line("RCPT ID:", receipt.receipt_number)
            self._print_line("Employee:", receipt.user.username[:15] if receipt.user else "N/A")
            if receipt.customer and receipt.customer.name.lower() != "no customer":
                self._print_line("Customer:", receipt.customer.name[:25])
                # Add phone number if available
                if hasattr(receipt.customer, 'phone_number') and receipt.customer.phone_number:
                    self._print_line("Phone:", receipt.customer.phone_number[:20])

            # === GET PAYMENT OBJECT (same way as view does it) ===
            payment = sales.first().payment if sales.exists() else None

            # === ITEMS SECTION ===
            self._print_divider('dashed')

            # Table header - matching template layout
            self.printer.set(align='left', bold=True)
            # Adjusted column widths to match template: Item Name | Price | Qty | Total
            header = f"{'Item Name':<20} {'Price':>8} {'Qty':>5} {'Total':>10}"
            self.printer.text(header[:48] + '\n')
            self.printer.set()
            self._print_divider('dashed')

            # Calculate totals
            subtotal_before_line_discounts = Decimal('0.00')
            subtotal_after_line_discounts = Decimal('0.00')
            total_items_count = 0

            # Use unified items list if provided, otherwise fall back to sales
            if items:
                # Unified items (products + services)
                for item in items:
                    item_name = str(item['name'])[:20]
                    quantity = item['quantity']
                    unit_price = Decimal(str(item['unit_price']))
                    item_total = Decimal(str(item['total']))

                    # Calculate before and after line discounts
                    subtotal_before_line_discounts += unit_price * Decimal(str(quantity))
                    subtotal_after_line_discounts += item_total
                    total_items_count += quantity

                    price_str = f"{currency_symbol}{unit_price:.2f}"
                    qty_str = f"{int(quantity)}"
                    total_str = f"{currency_symbol}{item_total:.2f}"
                    row = f"{item_name:<20} {price_str:>8} {qty_str:>5} {total_str:>10}"
                    self.printer.text(row[:48] + '\n')
            else:
                # Regular products - simple format (legacy)
                # Skip placeholder sales for service-only transactions
                for sale in sales:
                    if sale.product is None and sale.quantity == 0:
                        continue
                    subtotal_before_line_discounts += sale.product.price * sale.quantity
                    subtotal_after_line_discounts += sale.total_price if sale.total_price else Decimal('0.00')
                    total_items_count += sale.quantity

                for sale in sales:
                    # Skip placeholder sales for service-only transactions
                    if sale.product is None and sale.quantity == 0:
                        continue

                    quantity = sale.quantity
                    sale_total = sale.total_price if sale.total_price else Decimal('0.00')
                    unit_price = sale.product.price
                    product_name = str(sale.product)[:20]

                    price_str = f"{currency_symbol}{unit_price:.2f}"
                    qty_str = f"{int(quantity)}"
                    total_str = f"{currency_symbol}{sale_total:.2f}"
                    row = f"{product_name:<20} {price_str:>8} {qty_str:>5} {total_str:>10}"
                    self.printer.text(row[:48] + '\n')

            self._print_divider('dashed')

            # === PAYMENT SUMMARY ===
            # Regular products + services - matching template layout
            # Calculate total item-level discounts
            total_item_discount = subtotal_before_line_discounts - subtotal_after_line_discounts

            # Bill discount (get from payment object, not receipt)
            total_bill_discount = Decimal('0.00')
            if payment:
                total_bill_discount = payment.discount_amount if hasattr(payment, 'discount_amount') else Decimal('0.00')

            # Show combined discount if any
            total_discount = total_item_discount + total_bill_discount

            # Summary section - matching template format exactly
            self._print_line("Subtotal:", f"{currency_symbol}{subtotal_before_line_discounts:.2f}")

            if total_discount > 0:
                self._print_line("Discount:", f"-{currency_symbol}{total_discount:.2f}")

            # Loyalty discount (if applicable)
            if hasattr(receipt, 'loyalty_discount_amount') and receipt.loyalty_discount_amount > 0:
                if receipt.loyalty_points_redeemed > 0:
                    self._print_line(f"Loyalty ({receipt.loyalty_points_redeemed}pts):", f"-{currency_symbol}{receipt.loyalty_discount_amount:.2f}")
                else:
                    self._print_line("Loyalty Discount:", f"-{currency_symbol}{receipt.loyalty_discount_amount:.2f}")

            # Delivery cost (same logic as view)
            delivery_cost = receipt.delivery_cost or Decimal('0.00')
            if not delivery_cost and sales.exists():
                first_sale_delivery = sales.first().delivery
                if first_sale_delivery:
                    delivery_cost = first_sale_delivery.delivery_cost or Decimal('0.00')

            if delivery_cost > 0:
                self._print_line("Delivery:", f"+{currency_symbol}{delivery_cost:.2f}")

            # Tax - matching template format exactly
            if hasattr(receipt, 'tax_amount') and receipt.tax_amount > 0:
                # Try to parse tax_details for breakdown
                tax_breakdown = None
                if hasattr(receipt, 'tax_details') and receipt.tax_details:
                    try:
                        tax_breakdown = json.loads(receipt.tax_details) if isinstance(receipt.tax_details, str) else receipt.tax_details
                    except (json.JSONDecodeError, TypeError):
                        pass

                if tax_breakdown and isinstance(tax_breakdown, dict):
                    # Show detailed breakdown - matching template format
                    for tax_name, tax_info in tax_breakdown.items():
                        rate = tax_info.get('rate', '')
                        method = tax_info.get('method', '').capitalize()
                        amount = tax_info.get('amount', 0)
                        label = f"{tax_name} ({rate}% {method}):"
                        self._print_line(label, f"{currency_symbol}{amount:.2f}")
                else:
                    # Fallback to simple tax line
                    self._print_line("Tax:", f"{currency_symbol}{receipt.tax_amount:.2f}")

            # Grand Total - matching template format exactly (bold)
            final_total = payment.total_amount if payment else Decimal('0.00')
            self._print_line("Total:", f"{currency_symbol}{final_total:.2f}", bold=True)

            # Payment Type - matching template format
            payment_methods = []
            total_paid = Decimal('0.00')

            if payment:
                payment_methods = payment.payment_methods.all() if hasattr(payment, 'payment_methods') else []
                total_paid = sum(
                    pm.amount for pm in payment.payment_methods.filter(status='completed')
                ) if hasattr(payment, 'payment_methods') else Decimal('0.00')

            if payment_methods:
                method_names = [pm.get_payment_method_display() if hasattr(pm, 'get_payment_method_display') else str(pm.payment_method) for pm in payment_methods]
                self._print_line("Payment Type:", f"{', '.join(method_names)[:20]}")
            else:
                self._print_line("Payment Type:", "Cash")

            # Partial Payment Info (if applicable)
            if hasattr(receipt, 'payment_status') and receipt.payment_status == 'partial':
                if hasattr(receipt, 'amount_paid'):
                    self._print_line("Deposit Paid:", f"{currency_symbol}{receipt.amount_paid:.2f}")
                if hasattr(receipt, 'balance_remaining'):
                    self._print_line("Balance Due:", f"{currency_symbol}{receipt.balance_remaining:.2f}")

            # === LOYALTY INFO - matching template format exactly ===
            if receipt.customer and hasattr(receipt.customer, 'loyalty_account'):
                try:
                    from .models import LoyaltyConfiguration
                    config = LoyaltyConfiguration.get_active_config()
                    if config and config.is_active:
                        loyalty_account = receipt.customer.loyalty_account
                        self._print_divider('dashed')

                        # Title - centered and bold
                        self.printer.set(align='center', bold=True)
                        self.printer.text("LOYALTY STATUS\n")
                        self.printer.set()
                        self.printer.text('\n')

                        if config.calculation_type == 'transaction_count_discount':
                            # Transaction count discount program - matching template
                            progress_text = f"Progress: {loyalty_account.transaction_count}/{config.required_transaction_count} to {config.transaction_discount_percentage:.2f}% OFF"
                            self._print_centered(progress_text)
                        elif config.calculation_type == 'item_count_discount':
                            # Item count discount program - matching template
                            progress_text = f"Progress: {loyalty_account.item_count}/{config.required_item_count} to {config.item_discount_percentage:.2f}% OFF"
                            self._print_centered(progress_text)
                        else:
                            # Points-based program - matching template
                            current_balance = loyalty_account.current_balance
                            redeemable = loyalty_account.get_redeemable_value()
                            progress_text = f"Progress: {current_balance}pts = {currency_symbol}{redeemable:.2f}"
                            self._print_centered(progress_text)
                except Exception as e:
                    logger.debug(f"Loyalty info not available: {e}")

            # === DELIVERY INFO (same logic as view) ===
            try:
                delivery = None
                if sales.exists():
                    first_sale_delivery = sales.first().delivery
                    if first_sale_delivery:
                        delivery = first_sale_delivery

                if delivery:
                    self._print_divider('dashed')
                    self.printer.set(bold=True)
                    self._print_centered("Delivery")
                    self.printer.set()
                    if delivery.delivery_option == 'pickup':
                        delivery_info = "Pickup"
                    else:
                        delivery_info = delivery.delivery_address[:30] if hasattr(delivery, 'delivery_address') and delivery.delivery_address else "Home Delivery"
                    if hasattr(delivery, 'delivery_date') and delivery.delivery_date:
                        delivery_info += f" | {delivery.delivery_date.strftime('%d %b %Y')}"
                    self._print_left(delivery_info)
            except Exception as e:
                logger.debug(f"Delivery info not available: {e}")

            # === CHANGE RETURN POLICY - matching template exactly ===
            self._print_divider('dashed')
            self.printer.text('\n')
            self._print_centered("Change/Return Only - No Cash Refunds")
            self.printer.text('\n')
            self._print_divider('dashed')

            # === FOOTER - matching template exactly ===
            self.printer.text('\n')
            if store_config and store_config.receipt_footer_text:
                footer_lines = store_config.receipt_footer_text.split('\n')
                for line in footer_lines[:2]:  # Max 2 lines
                    self._print_centered(line.strip()[:40])
            else:
                self._print_centered("Thank you for shopping with us!")

            # Print URL if available
            if store_config and hasattr(store_config, 'website') and store_config.website:
                self.printer.text('\n')
                self._print_centered(store_config.website[:40])

            self.printer.text('\n\n')

            # Cut paper
            self.printer.cut()

            # Close printer job
            if self.printer:
                try:
                    self.printer.close()
                    logger.info("Printer job closed successfully")
                except Exception as close_error:
                    logger.warning(f"Error closing printer: {close_error}")

            logger.info(f"Successfully printed receipt {receipt.receipt_number}")
            return True

        except Exception as e:
            logger.error(f"Failed to print receipt: {e}")
            import traceback
            traceback.print_exc()
            # Try to close printer even on error
            if self.printer:
                try:
                    self.printer.close()
                except:
                    pass
            raise


def print_thermal_receipt(receipt_id):
    """
    Convenience function to print receipts by ID

    Args:
        receipt_id: ID of the receipt
    """
    from .models import Receipt, StoreConfiguration

    store_config = StoreConfiguration.objects.first()
    printer = ThermalPrinter()

    try:
        # Regular payment receipt
        receipt = Receipt.objects.get(id=receipt_id)
        sales = receipt.sales.all()
        printer.print_payment_receipt(receipt, sales, store_config)
        return True

    except Exception as e:
        logger.error(f"Failed to print thermal receipt: {e}")
        raise
