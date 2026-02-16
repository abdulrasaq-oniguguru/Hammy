"""
Test script for PDF validation functionality
"""
import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'mystore'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mystore.settings')
django.setup()

from store.pdf_validator import validate_pdf_content


def test_empty_pdf():
    """Test validation with empty PDF"""
    print("Test 1: Empty PDF")
    is_valid, error = validate_pdf_content(b"")
    print(f"  Result: {'✅ PASS' if not is_valid else '❌ FAIL'}")
    print(f"  Error: {error}\n")


def test_small_pdf():
    """Test validation with too small PDF"""
    print("Test 2: Very small PDF")
    is_valid, error = validate_pdf_content(b"small")
    print(f"  Result: {'✅ PASS' if not is_valid else '❌ FAIL'}")
    print(f"  Error: {error}\n")


def test_none_pdf():
    """Test validation with None"""
    print("Test 3: None PDF")
    is_valid, error = validate_pdf_content(None)
    print(f"  Result: {'✅ PASS' if not is_valid else '❌ FAIL'}")
    print(f"  Error: {error}\n")


def test_invalid_pdf():
    """Test validation with invalid PDF structure"""
    print("Test 4: Invalid PDF structure")
    fake_pdf = b"This is not a real PDF" * 100
    is_valid, error = validate_pdf_content(fake_pdf)
    print(f"  Result: {'✅ PASS' if not is_valid else '❌ FAIL'}")
    print(f"  Error: {error}\n")


def test_real_receipt_pdf():
    """Test validation with a real receipt PDF if available"""
    print("Test 5: Real Receipt PDF (if available)")
    try:
        from store.models import Receipt
        from django.template.loader import render_to_string
        from weasyprint import HTML
        from io import BytesIO
        from decimal import Decimal

        # Try to get a recent receipt
        receipt = Receipt.objects.select_related('customer', 'user').first()
        if not receipt:
            print("  ⚠️  No receipts found in database - skipping this test\n")
            return

        sales = receipt.sales.select_related('product').all()
        if not sales:
            print("  ⚠️  Receipt has no sales - skipping this test\n")
            return

        # Generate PDF like in the actual view
        payment = None
        if sales.exists():
            first_sale = sales.first()
            if hasattr(first_sale, 'payment') and first_sale.payment:
                payment = first_sale.payment

        total_item_discount = sum(
            (sale.discount_amount or Decimal('0.00')) * sale.quantity
            for sale in sales
        )
        total_price_before_discount = sum(
            sale.product.selling_price * sale.quantity
            for sale in sales
        )
        total_bill_discount = payment.discount_amount if payment else Decimal('0.00')
        final_subtotal = total_price_before_discount - total_item_discount - total_bill_discount

        context = {
            'receipt': receipt,
            'sales': sales,
            'payment': payment,
            'customer_name': receipt.customer.name if receipt.customer else "Walk-in Customer",
            'user': receipt.user,
            'total_item_discount': total_item_discount,
            'total_bill_discount': total_bill_discount,
            'total_price_before_discount': total_price_before_discount,
            'final_total': final_subtotal,
            'final_total_with_delivery': final_subtotal,
            'delivery': None,
            'logo_url': 'https://example.com/logo.png',
        }

        pdf_html = render_to_string('receipt/receipt_pdf.html', context)
        pdf_file = BytesIO()
        HTML(string=pdf_html).write_pdf(pdf_file)
        pdf_content = pdf_file.getvalue()

        print(f"  Generated PDF: {len(pdf_content)} bytes")

        # Now validate
        from store.pdf_validator import validate_receipt_pdf
        is_valid, error = validate_receipt_pdf(pdf_content, receipt, sales)

        print(f"  Result: {'✅ PASS' if is_valid else '❌ FAIL'}")
        if error:
            print(f"  Error: {error}")
        else:
            print(f"  ✅ PDF validated successfully!")
        print()

    except Exception as e:
        print(f"  ❌ Error during test: {str(e)}\n")


if __name__ == "__main__":
    print("=" * 60)
    print("PDF Validation Tests")
    print("=" * 60 + "\n")

    test_empty_pdf()
    test_small_pdf()
    test_none_pdf()
    test_invalid_pdf()
    test_real_receipt_pdf()

    print("=" * 60)
    print("Tests completed!")
    print("=" * 60)
