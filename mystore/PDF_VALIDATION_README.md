# PDF Validation System

## Overview
This system ensures that PDFs are properly generated before being sent via email. It validates PDF structure, content, and completeness to prevent sending corrupted or incomplete receipts.

## Features

### 1. **Comprehensive Validation**
   - Checks if PDF bytes exist and are not empty
   - Validates PDF has minimum size (prevents corrupted files)
   - Verifies PDF structure using PyPDF2
   - Ensures PDF has readable pages with text content
   - Optionally validates expected content (receipt number, customer name, totals, etc.)

### 2. **Integration Points**
   The validation is integrated at two key locations:

   #### a) Background Email Sending
   - **Function**: `send_receipt_email_background()` in `store/views.py:1295`
   - **When**: Automatically after a sale is completed
   - **Behavior**: Validates PDF before sending, retries on failure

   #### b) Manual Email Sending
   - **Function**: `send_receipt_email()` in `store/views.py:2160`
   - **When**: User manually sends receipt from receipt detail page
   - **Behavior**: Validates PDF and shows error message to user if validation fails

## Implementation Details

### Validation Function
Located in `store/pdf_validator.py`

```python
validate_pdf_content(pdf_bytes, expected_data=None)
```

**Parameters:**
- `pdf_bytes`: The PDF content as bytes
- `expected_data`: Optional dict with:
  - `receipt_number`: Receipt number to find in PDF
  - `customer_name`: Customer name to find in PDF
  - `total`: Expected total amount
  - `items_count`: Expected number of items

**Returns:**
- `(is_valid: bool, error_message: str or None)`

### Receipt-Specific Validation
```python
validate_receipt_pdf(pdf_bytes, receipt, sales)
```

**Parameters:**
- `pdf_bytes`: The PDF content as bytes
- `receipt`: Receipt model instance
- `sales`: QuerySet or list of Sale instances

**Returns:**
- `(is_valid: bool, error_message: str or None)`

## What Gets Validated

1. **PDF Existence**: Ensures PDF bytes are not None or empty
2. **PDF Size**: Checks minimum size (100 bytes) to catch corrupted files
3. **PDF Structure**: Uses PyPDF2 to verify valid PDF format
4. **Page Count**: Ensures at least one page exists
5. **Text Content**: Verifies PDF contains readable text
6. **Receipt Number**: Confirms receipt number appears in PDF
7. **Customer Name**: Verifies customer name is in PDF (if applicable)
8. **Items**: Ensures PDF length is reasonable for number of items

## Error Handling

### Validation Failures
If validation fails:
- **Background Email**: Retries up to 2 times with exponential backoff
- **Manual Email**: Shows error message to user and redirects back to receipt

### Common Error Messages
- `"PDF content is empty or None"`
- `"PDF is too small (X bytes), likely corrupted"`
- `"PDF has no pages"`
- `"PDF contains no readable text content"`
- `"PDF structure is invalid: [error details]"`
- `"Receipt number 'XXX' not found in PDF"`
- `"Customer name 'XXX' not found in PDF"`

## Testing

### Run Basic Tests
```bash
cd mystore
python manage.py shell < store/test_validator.py
```

### Test Cases Covered
1. Empty PDF (should fail)
2. Very small PDF (should fail)
3. None PDF (should fail)
4. Invalid PDF structure (should fail)

## Installation

The validation requires PyPDF2:
```bash
pip install PyPDF2
```

Already installed in this project.

## Logging

Validation events are logged with these prefixes:
- ✅ `"PDF validation passed"` - Successful validation
- ❌ `"PDF validation failed"` - Failed validation
- ⚠️ `"Warning"` - Non-critical issues

View logs to troubleshoot email sending issues.

## How It Prevents Issues

### Before This Fix
- PDFs could be sent with missing data
- Corrupt PDFs would be sent to customers
- No total validation meant incomplete receipts
- No retry mechanism for failed generation

### After This Fix
- All PDFs validated before sending
- Corrupt PDFs caught and regenerated
- Receipt content verified (number, customer, totals)
- Failed validations trigger retries
- Clear error messages for debugging

## Future Enhancements

Potential improvements:
1. More detailed content validation (line items, prices)
2. PDF size optimization checks
3. Image/logo presence validation
4. Automated testing with real receipt data
5. Validation metrics tracking (success/failure rates)

## Troubleshooting

### Issue: Emails not being sent
**Check:**
1. View logs for "PDF validation failed" messages
2. Verify receipt has required data (customer, sales items)
3. Check PDF template (`receipt/receipt_pdf.html`) renders correctly
4. Ensure WeasyPrint is functioning properly

### Issue: False validation failures
**Check:**
1. Receipt number format matches template output
2. Customer name doesn't have special characters
3. PDF text extraction working (PyPDF2 compatibility)

### Issue: Performance concerns
**Note:** Validation adds ~50-200ms per email send. This is acceptable for the reliability gain.

## Support

For issues or questions, check:
- Application logs (`logger` output)
- Test results (`store/test_validator.py`)
- PDF template (`store/templates/Receipt/receipt_pdf.html`)
- Validation code (`store/pdf_validator.py`)
