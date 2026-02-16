"""
Printer Management System
Handles direct printing to barcode, POS, and A4 printers
"""
import logging
import win32print
import win32ui
import win32con
from PIL import Image, ImageWin
from io import BytesIO
from django.utils import timezone
from .models import PrinterConfiguration, PrintJob

logger = logging.getLogger(__name__)


class PrinterManager:
    """Manages printing operations for different printer types"""

    @staticmethod
    def get_system_printers():
        """Get list of available system printers"""
        try:
            printers = []
            printer_enum = win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )
            for printer in printer_enum:
                printers.append({
                    'name': printer[2],
                    'is_default': printer[2] == win32print.GetDefaultPrinter()
                })
            return printers
        except Exception as e:
            logger.error(f"Error enumerating printers: {str(e)}")
            return []

    @staticmethod
    def get_printer_config(printer_type):
        """Get configured printer for a specific type"""
        return PrinterConfiguration.get_default_printer(printer_type)

    @staticmethod
    def print_image(image_data, printer_name=None, copies=1):
        """
        Print an image directly to a printer

        Args:
            image_data: PIL Image object or bytes
            printer_name: Name of the printer (if None, uses default)
            copies: Number of copies to print

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Convert bytes to PIL Image if needed
            if isinstance(image_data, bytes):
                image = Image.open(BytesIO(image_data))
            else:
                image = image_data

            # Get printer name
            if not printer_name:
                printer_name = win32print.GetDefaultPrinter()

            # Open printer
            hprinter = win32print.OpenPrinter(printer_name)
            try:
                # Get printer device context
                hdc = win32ui.CreateDC()
                hdc.CreatePrinterDC(printer_name)

                # Get printer capabilities
                printer_width = hdc.GetDeviceCaps(win32con.HORZRES)
                printer_height = hdc.GetDeviceCaps(win32con.VERTRES)
                dpi_x = hdc.GetDeviceCaps(win32con.LOGPIXELSX)
                dpi_y = hdc.GetDeviceCaps(win32con.LOGPIXELSY)

                # Calculate scaling to fit image to printer
                img_width, img_height = image.size
                scale_x = printer_width / img_width
                scale_y = printer_height / img_height
                scale = min(scale_x, scale_y)

                # Calculate centered position
                scaled_width = int(img_width * scale)
                scaled_height = int(img_height * scale)
                x_offset = (printer_width - scaled_width) // 2
                y_offset = 0  # Top align for receipts

                # Print multiple copies
                for copy in range(copies):
                    # Start document
                    hdc.StartDoc(f"Print Job - Copy {copy + 1}")
                    hdc.StartPage()

                    # Draw image
                    dib = ImageWin.Dib(image)
                    dib.draw(hdc.GetHandleOutput(), (x_offset, y_offset, x_offset + scaled_width, y_offset + scaled_height))

                    hdc.EndPage()
                    hdc.EndDoc()

                hdc.DeleteDC()
                logger.info(f"✅ Successfully printed to {printer_name} ({copies} copies)")
                return True

            finally:
                win32print.ClosePrinter(hprinter)

        except Exception as e:
            logger.error(f"❌ Print error: {str(e)}")
            return False

    @staticmethod
    def print_raw_data(data, printer_name=None):
        """
        Send raw data directly to printer (for ESC/POS commands)

        Args:
            data: Raw bytes to send to printer
            printer_name: Name of the printer

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not printer_name:
                printer_name = win32print.GetDefaultPrinter()

            hprinter = win32print.OpenPrinter(printer_name)
            try:
                job_id = win32print.StartDocPrinter(hprinter, 1, ("Raw Print Job", None, "RAW"))
                win32print.StartPagePrinter(hprinter)
                win32print.WritePrinter(hprinter, data)
                win32print.EndPagePrinter(hprinter)
                win32print.EndDocPrinter(hprinter)

                logger.info(f"✅ Successfully sent raw data to {printer_name}")
                return True

            finally:
                win32print.ClosePrinter(hprinter)

        except Exception as e:
            logger.error(f"❌ Raw print error: {str(e)}")
            return False

    @classmethod
    def print_barcode(cls, barcode_image, product_name=None, user=None):
        """
        Print a barcode label

        Args:
            barcode_image: PIL Image of the barcode
            product_name: Optional product name for print job tracking
            user: User who initiated the print

        Returns:
            PrintJob instance
        """
        printer_config = cls.get_printer_config('barcode')

        # Create print job record
        print_job = PrintJob.objects.create(
            printer=printer_config,
            document_type='barcode',
            status='printing',
            copies=printer_config.copies if printer_config else 1,
            created_by=user
        )

        try:
            if not printer_config:
                raise Exception("No barcode printer configured")

            success = cls.print_image(
                barcode_image,
                printer_config.system_printer_name,
                printer_config.copies
            )

            if success:
                print_job.status = 'completed'
                print_job.completed_at = timezone.now()
            else:
                print_job.status = 'failed'
                print_job.error_message = "Failed to print image"

        except Exception as e:
            print_job.status = 'failed'
            print_job.error_message = str(e)
            logger.error(f"❌ Barcode print failed: {str(e)}")

        print_job.save()
        return print_job

    @classmethod
    def print_receipt(cls, receipt_image_or_pdf, receipt_id=None, user=None):
        """
        Print a POS receipt

        Args:
            receipt_image_or_pdf: PIL Image or PDF bytes of the receipt
            receipt_id: Receipt ID for tracking
            user: User who initiated the print

        Returns:
            PrintJob instance
        """
        printer_config = cls.get_printer_config('pos')

        # Create print job record
        print_job = PrintJob.objects.create(
            printer=printer_config,
            document_type='receipt',
            document_id=receipt_id,
            status='printing',
            copies=printer_config.copies if printer_config else 1,
            created_by=user
        )

        try:
            if not printer_config:
                raise Exception("No POS printer configured")

            # Check if auto-print is enabled
            if not printer_config.auto_print:
                print_job.status = 'cancelled'
                print_job.error_message = "Auto-print is disabled for this printer"
                print_job.save()
                return print_job

            success = cls.print_image(
                receipt_image_or_pdf,
                printer_config.system_printer_name,
                printer_config.copies
            )

            if success:
                print_job.status = 'completed'
                print_job.completed_at = timezone.now()
            else:
                print_job.status = 'failed'
                print_job.error_message = "Failed to print receipt"

        except Exception as e:
            print_job.status = 'failed'
            print_job.error_message = str(e)
            logger.error(f"❌ Receipt print failed: {str(e)}")

        print_job.save()
        return print_job

    @classmethod
    def print_a4_document(cls, pdf_bytes, document_type='report', document_id=None, user=None):
        """
        Print an A4 document

        Args:
            pdf_bytes: PDF file as bytes
            document_type: Type of document (report, invoice, etc.)
            document_id: Document ID for tracking
            user: User who initiated the print

        Returns:
            PrintJob instance
        """
        printer_config = cls.get_printer_config('a4')

        # Create print job record
        print_job = PrintJob.objects.create(
            printer=printer_config,
            document_type=document_type,
            document_id=document_id,
            status='printing',
            copies=printer_config.copies if printer_config else 1,
            created_by=user
        )

        try:
            if not printer_config:
                raise Exception("No A4 printer configured")

            # For PDFs, we need to convert to image or use a PDF printer
            # For now, we'll use the default Windows PDF handler
            import tempfile
            import subprocess
            import os

            # Save PDF to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name

            try:
                # Use Windows default PDF printer association
                # This will open the PDF with the default app and print
                os.startfile(tmp_path, "print")

                # Wait a bit for print to spool
                import time
                time.sleep(2)

                print_job.status = 'completed'
                print_job.completed_at = timezone.now()

            finally:
                # Clean up temp file after a delay
                import threading
                def cleanup():
                    time.sleep(10)
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
                threading.Thread(target=cleanup, daemon=True).start()

        except Exception as e:
            print_job.status = 'failed'
            print_job.error_message = str(e)
            logger.error(f"❌ A4 document print failed: {str(e)}")

        print_job.save()
        return print_job

    @classmethod
    def test_printer(cls, printer_config):
        """
        Print a test page to verify printer configuration

        Args:
            printer_config: PrinterConfiguration instance

        Returns:
            bool: True if successful
        """
        try:
            # Create a simple test image
            from PIL import Image, ImageDraw, ImageFont

            # Determine image size based on printer type
            if printer_config.printer_type == 'barcode':
                width = printer_config.barcode_width * 8 or 400
                height = printer_config.barcode_height * 8 or 200
            elif printer_config.printer_type == 'pos':
                width = 576  # 80mm at 203 DPI
                height = 400
            else:  # A4
                width = 1654  # A4 width at 200 DPI
                height = 2339  # A4 height at 200 DPI

            # Create test image
            img = Image.new('RGB', (width, height), 'white')
            draw = ImageDraw.Draw(img)

            # Try to load a font
            try:
                font_large = ImageFont.truetype("arial.ttf", 40)
                font_small = ImageFont.truetype("arial.ttf", 20)
            except:
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()

            # Draw test content
            draw.text((20, 20), "TEST PAGE", fill='black', font=font_large)
            draw.text((20, 80), f"Printer: {printer_config.name}", fill='black', font=font_small)
            draw.text((20, 110), f"Type: {printer_config.get_printer_type_display()}", fill='black', font=font_small)
            draw.text((20, 140), f"System: {printer_config.system_printer_name}", fill='black', font=font_small)
            draw.text((20, 170), f"Paper: {printer_config.get_paper_size_display()}", fill='black', font=font_small)

            # Draw border
            draw.rectangle([(10, 10), (width-10, height-10)], outline='black', width=2)

            # Print the test image
            return cls.print_image(img, printer_config.system_printer_name, 1)

        except Exception as e:
            logger.error(f"❌ Test print failed: {str(e)}")
            return False
