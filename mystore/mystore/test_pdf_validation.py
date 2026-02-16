"""
Test script for PDF validation functionality
"""
import os
import sys
import django

# Setup Django environment
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


if __name__ == "__main__":
    print("=" * 60)
    print("PDF Validation Tests")
    print("=" * 60 + "\n")

    test_empty_pdf()
    test_small_pdf()
    test_none_pdf()
    test_invalid_pdf()

    print("=" * 60)
    print("Tests completed!")
    print("=" * 60)
