# PythonAnywhere API Fix Deployment Guide

## Current Issue
ALL receipt batches failing with 500 Internal Server Error.
Products sync works perfectly (1918 updated, 0 created).

## Step-by-Step Deployment

### Step 1: Check Current API Code on PythonAnywhere

1. Login to https://www.pythonanywhere.com
2. Go to **Files** tab
3. Navigate to: `/home/asoniguguru/minimal_api/oem_reporting/views.py`
4. Search for line ~2605 (Ctrl+F search for: "local_payment_id")
5. Check if you see:
   ```python
   # OLD BUGGY CODE (if you see this, it needs fixing):
   if local_payment_id and Payment.objects.filter(local_payment_id=local_payment_id).exists():
       continue  # Skip - already synced
   ```
   OR
   ```python
   # NEW FIXED CODE (if you see this, it's already fixed):
   if not (local_payment_id and Payment.objects.filter(local_payment_id=local_payment_id).exists()):
       # Payment doesn't exist yet, create it
   ```

### Step 2: Check Error Logs

1. Go to **Web** tab on PythonAnywhere
2. Scroll to **"Log files"** section
3. Click **Error log** link
4. Scroll to the bottom
5. Look for recent errors (timestamp around your sync time)
6. **Copy the full error traceback** - it will look like:
   ```
   [timestamp] :Error running WSGI application
   [timestamp] :Traceback (most recent call last):
   [timestamp] :  File "...", line X, in ...
   [timestamp] :    some code here
   [timestamp] :SomeError: error message here
   ```

### Step 3: Apply the Fix

If the code is still the OLD version, replace the entire `sync_receipts_full` function (around lines 2516-2667) with the fixed version from:
`C:\III\minimal_api\oem_reporting\views.py`

**Critical changes needed:**

#### Change 1: Receipt date parsing (around line 2545)
```python
# Add this BEFORE the receipt creation code:
# Parse receipt date safely
receipt_date_str = receipt_data.get('date')
if receipt_date_str:
    try:
        receipt_date = datetime.fromisoformat(receipt_date_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError, TypeError):
        receipt_date = timezone.now()
else:
    receipt_date = timezone.now()
```

#### Change 2: Sale date parsing (around line 2593)
```python
# Parse sale date safely
sale_date_str = sale_data.get('sale_date')
if sale_date_str:
    try:
        sale_date_value = datetime.fromisoformat(sale_date_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError, TypeError):
        sale_date_value = timezone.now()
else:
    sale_date_value = timezone.now()
```

#### Change 3: Payment logic (around line 2603) - MOST IMPORTANT
```python
# OLD (WRONG):
if local_payment_id and Payment.objects.filter(local_payment_id=local_payment_id).exists():
    continue  # Skip - already synced ❌

# NEW (CORRECT):
if not (local_payment_id and Payment.objects.filter(local_payment_id=local_payment_id).exists()):
    # Payment doesn't exist yet, create it ✅

    # Parse payment date safely
    payment_date_str = payment_data.get('payment_date')
    if payment_date_str:
        try:
            payment_date_value = datetime.fromisoformat(payment_date_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError, TypeError):
            payment_date_value = timezone.now()
    else:
        payment_date_value = timezone.now()

    payment = Payment.objects.create(
        payment_status=payment_data.get('payment_status', 'pending'),
        total_amount=Decimal(str(payment_data.get('total_amount', 0))),
        total_paid=Decimal(str(payment_data.get('total_paid', 0))),
        discount_percentage=Decimal(str(payment_data.get('discount_percentage', 0))) if payment_data.get('discount_percentage') else 0,
        discount_amount=Decimal(str(payment_data.get('discount_amount', 0))) if payment_data.get('discount_amount') else 0,
        payment_date=payment_date_value,
        local_payment_id=local_payment_id,
    )
    new_payments_count += 1

    # Link payment to sales from this receipt
    for sale in receipt.sales.all():
        sale.payment = payment
        sale.save()

    # Sync payment methods
    for pm_data in payment_data.get('payment_methods', []):
        PaymentMethod.objects.create(
            payment=payment,
            payment_method=pm_data.get('method'),
            amount=Decimal(str(pm_data.get('amount', 0))),
            status='completed'
        )
```

### Step 4: Save and Reload

1. Click **"Save"** in the file editor
2. Go to **Web** tab
3. Click the big green **"Reload asoniguguru.pythonanywhere.com"** button
4. Wait for "Successfully reloaded" message

### Step 5: Test Again

Run the sync again from your local machine:
```batch
"C:\III\.venv\Scripts\python.exe" sync_to_pythonanywhere.py --full
```

### Step 6: If Still Failing

1. Check error logs again (they will have fresh errors)
2. Look for the specific error message
3. Send me the error traceback

## Common Issues

### Issue 1: Forgot to Reload
**Symptom**: Same 500 errors after editing file
**Solution**: Click "Reload" button on Web tab

### Issue 2: Syntax Error in Edit
**Symptom**: Different error or blank page
**Solution**: Check error log, fix Python syntax error

### Issue 3: Missing Import
**Symptom**: `NameError: name 'X' is not defined`
**Solution**: Add missing import at top of file

### Issue 4: Database Field Missing
**Symptom**: `Column 'local_payment_id' does not exist`
**Solution**: Run migrations on PythonAnywhere:
```bash
cd ~/minimal_api
python manage.py makemigrations
python manage.py migrate
```

## What to Send Me

If it's still not working, send me:

1. ✅ The error traceback from error log (last 30-50 lines)
2. ✅ Confirmation that you clicked "Reload"
3. ✅ What code you see at line 2605 in views.py

This will help me diagnose the exact issue!
