"""
Simple test for PDF validator (run with: python manage.py shell < store/test_validator.py)
"""
from store.pdf_validator import validate_pdf_content

print("=" * 60)
print("PDF Validation Tests")
print("=" * 60 + "\n")

# Test 1: Empty PDF
print("Test 1: Empty PDF")
is_valid, error = validate_pdf_content(b"")
print(f"  Result: {'✅ PASS' if not is_valid else '❌ FAIL'}")
print(f"  Error: {error}\n")

# Test 2: Very small PDF
print("Test 2: Very small PDF")
is_valid, error = validate_pdf_content(b"small")
print(f"  Result: {'✅ PASS' if not is_valid else '❌ FAIL'}")
print(f"  Error: {error}\n")

# Test 3: None PDF
print("Test 3: None PDF")
is_valid, error = validate_pdf_content(None)
print(f"  Result: {'✅ PASS' if not is_valid else '❌ FAIL'}")
print(f"  Error: {error}\n")

# Test 4: Invalid PDF structure
print("Test 4: Invalid PDF structure")
fake_pdf = b"This is not a real PDF" * 100
is_valid, error = validate_pdf_content(fake_pdf)
print(f"  Result: {'✅ PASS' if not is_valid else '❌ FAIL'}")
print(f"  Error: {error}\n")

print("=" * 60)
print("Basic validation tests completed!")
print("=" * 60)
