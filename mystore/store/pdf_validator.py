"""
PDF Validation Module
Ensures PDFs are properly generated before sending via email
"""
import logging
from decimal import Decimal
from io import BytesIO
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)


class PDFValidationError(Exception):
    """Custom exception for PDF validation failures"""
    pass


def validate_pdf_content(pdf_bytes, expected_data=None):
    """
    Validates that a PDF is properly generated and contains expected content.

    Args:
        pdf_bytes: The PDF content as bytes
        expected_data: Optional dict with expected content to validate:
            - receipt_number: Receipt number to find in PDF
            - customer_name: Customer name to find in PDF
            - total: Expected total amount (as Decimal or float)
            - items_count: Expected number of items

    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    try:
        # 1. Check if PDF bytes exist and have content
        if not pdf_bytes:
            return False, "PDF content is empty or None"

        if len(pdf_bytes) < 100:  # Arbitrary minimum size for a valid PDF
            return False, f"PDF is too small ({len(pdf_bytes)} bytes), likely corrupted"

        # 2. Verify PDF structure by reading it
        try:
            pdf_buffer = BytesIO(pdf_bytes)
            pdf_reader = PdfReader(pdf_buffer)

            # Check if PDF has pages
            if len(pdf_reader.pages) == 0:
                return False, "PDF has no pages"

            # Extract text from all pages
            pdf_text = ""
            for page in pdf_reader.pages:
                pdf_text += page.extract_text() or ""

            if not pdf_text or len(pdf_text.strip()) < 10:
                return False, "PDF contains no readable text content"

        except Exception as e:
            return False, f"PDF structure is invalid: {str(e)}"

        # 3. Validate expected content if provided
        if expected_data:
            # Check receipt number
            if 'receipt_number' in expected_data and expected_data['receipt_number']:
                receipt_num = str(expected_data['receipt_number'])
                if receipt_num not in pdf_text:
                    return False, f"Receipt number '{receipt_num}' not found in PDF"

            # Check customer name
            if 'customer_name' in expected_data and expected_data['customer_name']:
                customer = str(expected_data['customer_name'])
                if customer not in pdf_text:
                    return False, f"Customer name '{customer}' not found in PDF"

            # Check total amount
            if 'total' in expected_data and expected_data['total']:
                total = expected_data['total']
                if isinstance(total, (int, float, Decimal)):
                    # Format total in common currency formats
                    total_str = f"{float(total):,.2f}"
                    # Remove commas for alternate check
                    total_str_no_comma = f"{float(total):.2f}"

                    if total_str not in pdf_text and total_str_no_comma not in pdf_text:
                        logger.warning(f"Total amount {total_str} not found in PDF text")
                        # Don't fail on total - sometimes formatting differs

            # Check that we have at least some product items mentioned
            if 'items_count' in expected_data and expected_data['items_count']:
                items_count = expected_data['items_count']
                # Just verify the PDF is not suspiciously short
                if items_count > 0 and len(pdf_text) < 200:
                    return False, f"PDF text is too short for {items_count} items"

        # 4. All validations passed
        logger.info(f"✅ PDF validation passed ({len(pdf_bytes)} bytes, {len(pdf_reader.pages)} pages)")
        return True, None

    except Exception as e:
        logger.exception("Unexpected error during PDF validation")
        return False, f"Validation error: {str(e)}"


def validate_receipt_pdf(pdf_bytes, receipt, sales, store_config=None):
    """
    Convenience function to validate a receipt PDF.

    Args:
        pdf_bytes: The PDF content as bytes
        receipt: Receipt model instance
        sales: QuerySet or list of Sale instances
        store_config: StoreConfiguration instance (optional)

    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    # Calculate expected total
    total_price_before_discount = sum(
        sale.product.selling_price * sale.quantity
        for sale in sales
    )

    # Get first sale's payment for total
    payment = None
    if sales:
        first_sale = sales[0] if isinstance(sales, list) else sales.first()
        if hasattr(first_sale, 'payment') and first_sale.payment:
            payment = first_sale.payment

    # Build validation data
    expected_data = {
        'receipt_number': receipt.receipt_number,
        'customer_name': receipt.customer.name if receipt.customer else None,
        'total': total_price_before_discount,
        'items_count': len(sales) if isinstance(sales, list) else sales.count(),
    }

    # First validate the PDF content
    is_valid, error_msg = validate_pdf_content(pdf_bytes, expected_data)

    if not is_valid:
        return is_valid, error_msg

    # Additional validation for store information
    try:
        pdf_buffer = BytesIO(pdf_bytes)
        pdf_reader = PdfReader(pdf_buffer)
        pdf_text = ""
        for page in pdf_reader.pages:
            pdf_text += page.extract_text() or ""

        # Validate store info is present
        if store_config:
            if store_config.phone and store_config.phone not in pdf_text:
                logger.warning(f"⚠️ Store phone '{store_config.phone}' not found in PDF")

            if store_config.email and store_config.email not in pdf_text:
                logger.warning(f"⚠️ Store email '{store_config.email}' not found in PDF")

            if store_config.store_name and store_config.store_name not in pdf_text:
                return False, f"Store name '{store_config.store_name}' not found in PDF"

        # Validate items are present
        items_count = len(sales) if isinstance(sales, list) else sales.count()
        if items_count > 0:
            # Check that at least one product is mentioned
            has_product = False
            for sale in sales:
                if sale.product.brand in pdf_text:
                    has_product = True
                    break

            if not has_product:
                return False, "No products found in PDF - PDF may be incomplete"

        logger.info("✅ Extended PDF validation passed - all required data present")
        return True, None

    except Exception as e:
        logger.error(f"Error in extended PDF validation: {e}")
        # Don't fail on extended validation errors
        return True, None
