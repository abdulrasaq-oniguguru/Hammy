"""
ROBUST Sync Script with Individual Receipt Error Handling
- Syncs receipts ONE AT A TIME to isolate errors
- Logs which receipts fail and why
- Continues processing even if some receipts fail
- Reports detailed success/failure statistics
"""

import os
import sys
import django
import requests
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

# Setup Django
script_dir = os.path.dirname(os.path.abspath(__file__))
mystore_dir = os.path.join(script_dir, 'mystore')

sys.path.insert(0, mystore_dir)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mystore.settings')

original_cwd = os.getcwd()
os.chdir(mystore_dir)

try:
    django.setup()
except Exception as e:
    print(f"Error setting up Django: {e}")
    raise

from store.models import Product, Sale, Receipt, Payment, PaymentMethod as PaymentMethodModel

# Configuration
API_BASE_URL = "https://asoniguguru.pythonanywhere.com/api/oem"
API_USERNAME = "admin"
API_PASSWORD = "*3mb741101"

# Batch sizes
PRODUCT_BATCH_SIZE = 50
RECEIPT_BATCH_SIZE = 1  # Process ONE receipt at a time for better error handling

# Track last sync time
LAST_SYNC_FILE = os.path.join(script_dir, '.last_sync_time.txt')

# Error log file
ERROR_LOG_FILE = os.path.join(script_dir, 'sync_errors.log')

def log_error(message):
    """Log errors to file"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(ERROR_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"❌ {message}")

def log_info(message):
    """Log info message"""
    print(f"ℹ️  {message}")

def get_last_sync_time():
    """Get the last successful sync time"""
    if os.path.exists(LAST_SYNC_FILE):
        try:
            with open(LAST_SYNC_FILE, 'r') as f:
                timestamp = f.read().strip()
                return datetime.fromisoformat(timestamp)
        except:
            pass
    return None

def save_last_sync_time():
    """Save current time as last sync time"""
    with open(LAST_SYNC_FILE, 'w') as f:
        f.write(datetime.now().isoformat())

def get_token():
    """Get JWT authentication token with retry"""
    print("Getting authentication token...")
    max_retries = 3

    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{API_BASE_URL}/token/",
                json={"username": API_USERNAME, "password": API_PASSWORD},
                timeout=30
            )
            response.raise_for_status()
            token = response.json()['access']
            print("SUCCESS: Authentication successful")
            return token
        except requests.exceptions.Timeout:
            print(f"Timeout on attempt {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        except Exception as e:
            print(f"FAILED: Authentication failed: {e}")
            return None

    print("FAILED: Authentication timed out after all retries")
    return None

def batch_list(items, batch_size):
    """Split a list into batches"""
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]

def sync_products_batched(token, incremental=False):
    """Sync products in batches (same as before - this works fine)"""
    print("\nSyncing Products...")

    try:
        if incremental:
            last_sync = get_last_sync_time()
            if last_sync:
                products = Product.objects.all()
                print(f"Mode: INCREMENTAL (checking for changes)")
            else:
                products = Product.objects.all()
                print(f"Mode: FULL (no previous sync)")
        else:
            products = Product.objects.all()
            print(f"Mode: FULL (all products)")

        total_products = products.count()
        print(f"Total products to sync: {total_products}")

        if total_products == 0:
            print("No products to sync")
            return True

        product_list = []
        for product in products:
            product_list.append({
                'barcode_number': product.barcode_number or '',
                'brand': product.brand,
                'category': product.category,
                'size': product.size,
                'color': product.color,
                'design': product.design,
                'quantity': product.quantity,
                'location': product.location,
                'shop': product.shop,
                'price': float(product.price),
                'selling_price': float(product.selling_price),
                'markup': float(product.markup),
                'markup_type': product.markup_type,
            })

        headers = {'Authorization': f'Bearer {token}'}
        batches = list(batch_list(product_list, PRODUCT_BATCH_SIZE))
        total_batches = len(batches)

        total_created = 0
        total_updated = 0

        for batch_num, batch in enumerate(batches, 1):
            print(f"  Batch {batch_num}/{total_batches} ({len(batch)} products)...", end=' ')

            try:
                response = requests.post(
                    f"{API_BASE_URL}/sync/products/",
                    json={'products': batch},
                    headers=headers,
                    timeout=120
                )
                response.raise_for_status()
                result = response.json()

                created = result.get('created', 0)
                updated = result.get('updated', 0)
                total_created += created
                total_updated += updated

                print(f"OK ({created} created, {updated} updated)")

            except Exception as e:
                print(f"FAILED: {e}")
                log_error(f"Product batch {batch_num} failed: {e}")
                continue

        print(f"SUCCESS: Total synced - {total_created} created, {total_updated} updated")
        return True

    except Exception as e:
        print(f"FAILED: Product sync error: {e}")
        log_error(f"Product sync failed: {e}")
        return False

def sync_single_receipt(receipt, token_getter, headers_getter):
    """Sync a single receipt and return success/failure

    Args:
        receipt: Receipt object to sync
        token_getter: Function to get/refresh token
        headers_getter: Function to get headers with current token
    """
    try:
        # Get current headers (may have refreshed token)
        headers = headers_getter()
        sales = receipt.sales.all()
        if not sales.exists():
            return {'status': 'skipped', 'reason': 'no sales'}

        sales_data = []
        for sale in sales:
            # CRITICAL FIX: Send product identification fields, not just ID
            # Product IDs differ between local and remote after database clear
            sales_data.append({
                'local_sale_id': sale.id,
                # Send product lookup fields (barcode is unique identifier)
                'product_barcode': sale.product.barcode_number or '',
                'product_brand': sale.product.brand,
                'product_category': sale.product.category,
                'product_size': sale.product.size,
                'product_color': sale.product.color or '',
                'product_location': sale.product.location,
                'quantity': sale.quantity,
                'total_price': float(sale.total_price),
                'discount_amount': float(sale.discount_amount) if sale.discount_amount else 0.0,
                'sale_date': sale.sale_date.isoformat() if sale.sale_date else None,
            })

        # Get payment info
        payment = None
        if sales.exists() and sales.first().payment:
            payment_obj = sales.first().payment
            payment_methods = []
            for pm in payment_obj.payment_methods.all():
                payment_methods.append({
                    'method': pm.payment_method,
                    'amount': float(pm.amount),
                })

            payment = {
                'local_payment_id': payment_obj.id,
                'payment_status': payment_obj.payment_status,
                'total_amount': float(payment_obj.total_amount),
                'total_paid': float(payment_obj.total_paid),
                'discount_percentage': float(payment_obj.discount_percentage) if payment_obj.discount_percentage else 0.0,
                'discount_amount': float(payment_obj.discount_amount) if payment_obj.discount_amount else 0.0,
                'payment_date': payment_obj.payment_date.isoformat() if payment_obj.payment_date else None,
                'payment_methods': payment_methods,
            }

        receipt_data = {
            'local_receipt_id': receipt.id,
            'receipt_number': receipt.receipt_number or f'R{receipt.id}',
            'date': receipt.date.isoformat() if receipt.date else None,
            'customer_id': None,
            'delivery_cost': float(receipt.delivery_cost) if receipt.delivery_cost else 0.0,
            'sales': sales_data,
            'payment': payment,
        }

        # Send to API (with retry on 401)
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    f"{API_BASE_URL}/sync/receipts/",
                    json={'receipts': [receipt_data]},
                    headers=headers,
                    timeout=60
                )

                # If 401, refresh token and retry
                if response.status_code == 401 and attempt < max_retries - 1:
                    print("🔄 Token expired, refreshing...", end=' ')
                    token_getter()  # Refresh token
                    headers = headers_getter()  # Get new headers
                    continue

                response.raise_for_status()
                result = response.json()

                return {
                    'status': 'success',
                    'synced': result.get('synced', 0),
                    'new_sales': result.get('new_sales', 0),
                    'new_payments': result.get('new_payments', 0)
                }

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401 and attempt < max_retries - 1:
                    continue  # Retry with new token

                error_msg = f"HTTP {e.response.status_code}"
                try:
                    error_detail = e.response.json()
                    error_msg += f": {json.dumps(error_detail)}"
                except:
                    error_msg += f": {e.response.text[:200]}"
                return {'status': 'failed', 'error': error_msg}

        return {'status': 'failed', 'error': 'Max retries exceeded'}

    except Exception as e:
        return {'status': 'failed', 'error': str(e)}

def sync_receipts_individually(initial_token, incremental=False, full_history=False):
    """Sync receipts ONE AT A TIME to isolate errors"""
    print("\nSyncing Receipts and Sales (ONE AT A TIME)...")

    # Token management - refresh when needed
    current_token = {'value': initial_token, 'refresh_count': 0}

    def refresh_token():
        """Refresh the authentication token"""
        new_token = get_token()
        if new_token:
            current_token['value'] = new_token
            current_token['refresh_count'] += 1
            print(f"🔄 Token refreshed (#{current_token['refresh_count']})")
        return new_token

    def get_current_headers():
        """Get headers with current token"""
        return {'Authorization': f'Bearer {current_token["value"]}'}

    try:
        # Determine date range
        if full_history:
            receipts = Receipt.objects.all()
            print(f"Mode: FULL HISTORY (all records from inception)")
        elif incremental:
            last_sync = get_last_sync_time()
            if last_sync:
                cutoff_date = last_sync - timedelta(minutes=5)
                print(f"Mode: INCREMENTAL (since {cutoff_date.strftime('%Y-%m-%d %H:%M')})")
                receipts = Receipt.objects.filter(date__gte=cutoff_date)
            else:
                receipts = Receipt.objects.all()
                print(f"Mode: FULL (first sync - all data)")
        else:
            cutoff_date = datetime.now() - timedelta(days=90)
            print(f"Mode: FULL (last 90 days)")
            receipts = Receipt.objects.filter(date__gte=cutoff_date)

        receipts = receipts.select_related('customer').prefetch_related(
            'sales__product',
            'sales__payment__payment_methods'
        ).order_by('-date')

        total_receipts = receipts.count()
        print(f"Total receipts to sync: {total_receipts}")

        if total_receipts == 0:
            print("No receipts to sync")
            return True

        # Statistics
        stats = {
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'new_sales': 0,
            'new_payments': 0,
            'errors': [],
            'token_refreshes': 0
        }

        # Process each receipt individually
        print(f"\nProcessing {total_receipts} receipts...")
        print("💡 Token will auto-refresh if it expires\n")

        for idx, receipt in enumerate(receipts, 1):
            # Proactively refresh token every 50 receipts to avoid expiration
            if idx > 1 and idx % 50 == 0:
                print(f"\n🔄 Proactively refreshing token at receipt {idx}...")
                refresh_token()
                stats['token_refreshes'] += 1
                print()

            print(f"  [{idx}/{total_receipts}] Receipt {receipt.receipt_number or receipt.id}...", end=' ')

            result = sync_single_receipt(receipt, refresh_token, get_current_headers)

            if result['status'] == 'success':
                print(f"✅ OK (sales: {result['new_sales']}, payment: {result['new_payments']})")
                stats['success'] += 1
                stats['new_sales'] += result['new_sales']
                stats['new_payments'] += result['new_payments']

            elif result['status'] == 'skipped':
                print(f"⊘ SKIPPED ({result['reason']})")
                stats['skipped'] += 1

            elif result['status'] == 'failed':
                print(f"❌ FAILED: {result['error']}")
                stats['failed'] += 1
                error_detail = f"Receipt {receipt.receipt_number or receipt.id} (ID: {receipt.id}): {result['error']}"
                stats['errors'].append(error_detail)
                log_error(error_detail)

            # Small delay to avoid overwhelming the API
            if idx % 10 == 0:
                time.sleep(0.5)

        # Print summary
        print("\n" + "=" * 70)
        print("RECEIPTS SYNC SUMMARY")
        print("=" * 70)
        print(f"✅ Successful: {stats['success']}")
        print(f"⊘ Skipped: {stats['skipped']}")
        print(f"❌ Failed: {stats['failed']}")
        print(f"📊 New sales: {stats['new_sales']}")
        print(f"💳 New payments: {stats['new_payments']}")
        print(f"🔄 Token refreshes: {stats['token_refreshes'] + current_token['refresh_count']}")

        if stats['errors']:
            print(f"\n❌ Failed receipts ({len(stats['errors'])}):")
            for error in stats['errors'][:10]:  # Show first 10
                print(f"   - {error}")
            if len(stats['errors']) > 10:
                print(f"   ... and {len(stats['errors']) - 10} more (see {ERROR_LOG_FILE})")

        return stats['failed'] == 0  # Return True only if no failures

    except Exception as e:
        print(f"FAILED: Receipts sync error: {e}")
        log_error(f"Receipts sync crashed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main sync function"""
    incremental = '--incremental' in sys.argv
    full_history = '--full' in sys.argv

    print("=" * 70)
    print("  ROBUST DATA SYNC TO PYTHONANYWHERE")
    print("  (Individual receipt processing for error isolation)")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Target: {API_BASE_URL}")

    if full_history:
        print(f"Mode: FULL HISTORY (all data from database inception)")
    elif incremental:
        print(f"Mode: INCREMENTAL (recent changes only)")
    else:
        print(f"Mode: STANDARD (last 90 days)")
    print()

    # Clear old error log
    if os.path.exists(ERROR_LOG_FILE):
        os.remove(ERROR_LOG_FILE)
        print(f"📝 Error log: {ERROR_LOG_FILE}\n")

    # Get authentication token
    token = get_token()
    if not token:
        print("\nFAILED: Sync aborted - authentication failed")
        sys.exit(1)

    # Sync data
    success_count = 0

    if sync_products_batched(token, incremental):
        success_count += 1

    if sync_receipts_individually(token, incremental, full_history):
        success_count += 1

    # Save last sync time if successful
    if success_count == 2:
        save_last_sync_time()

    # Summary
    print("\n" + "=" * 70)
    if success_count == 2:
        print("SUCCESS: SYNC COMPLETED")
    else:
        print(f"PARTIAL: SYNC COMPLETED WITH SOME ERRORS ({success_count}/2 successful)")
    print("=" * 70)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    if os.path.exists(ERROR_LOG_FILE):
        print(f"⚠️  Some errors occurred. Check: {ERROR_LOG_FILE}")

    if success_count < 2:
        sys.exit(1)

if __name__ == "__main__":
    main()
