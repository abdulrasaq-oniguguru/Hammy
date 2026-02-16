"""
Comprehensive Debug Script - Find Exact Data Issues
Shows side-by-side comparison of local vs remote data
"""

import os
import sys
import django
import requests
from datetime import datetime, timedelta
from decimal import Decimal

# Setup Django
script_dir = os.path.dirname(os.path.abspath(__file__))
mystore_dir = os.path.join(script_dir, 'mystore')

sys.path.insert(0, mystore_dir)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mystore.settings')
os.chdir(mystore_dir)

try:
    django.setup()
except Exception as e:
    print(f"Error setting up Django: {e}")
    raise

from store.models import Receipt, Sale, Payment, Product
from django.db.models import Sum, Count
from django.utils import timezone

# Configuration
API_BASE_URL = "https://asoniguguru.pythonanywhere.com/api/oem"
API_USERNAME = "admin"
API_PASSWORD = "*3mb741101"

def get_token():
    """Get JWT token"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/token/",
            json={"username": API_USERNAME, "password": API_PASSWORD},
            timeout=30
        )
        response.raise_for_status()
        return response.json()['access']
    except Exception as e:
        print(f"❌ Auth failed: {e}")
        return None

def debug_sync():
    """Comprehensive debug of sync issues"""
    print("=" * 80)
    print("  COMPREHENSIVE DATA DEBUG")
    print("=" * 80)

    # Get token
    token = get_token()
    if not token:
        print("Cannot proceed without authentication")
        return

    headers = {'Authorization': f'Bearer {token}'}

    # 1. Check total counts
    print("\n" + "=" * 80)
    print("1. TOTAL COUNTS COMPARISON")
    print("=" * 80)

    local_products = Product.objects.count()
    local_receipts = Receipt.objects.count()
    local_sales = Sale.objects.count()
    local_payments = Payment.objects.count()

    print(f"\n📊 LOCAL DATABASE:")
    print(f"   Products: {local_products}")
    print(f"   Receipts: {local_receipts}")
    print(f"   Sales: {local_sales}")
    print(f"   Payments: {local_payments}")

    # Get remote counts via API
    try:
        # Try to get products count
        response = requests.get(f"{API_BASE_URL}/products/", headers=headers, timeout=30)
        if response.status_code == 200:
            remote_products_data = response.json()
            if isinstance(remote_products_data, list):
                remote_products = len(remote_products_data)
            else:
                remote_products = remote_products_data.get('count', 'Unknown')
        else:
            remote_products = f"Error: {response.status_code}"
    except Exception as e:
        remote_products = f"Error: {e}"

    print(f"\n📊 REMOTE DATABASE (PythonAnywhere):")
    print(f"   Products: {remote_products}")

    # 2. Check today's receipts in detail
    print("\n" + "=" * 80)
    print("2. TODAY'S RECEIPTS - DETAILED CHECK")
    print("=" * 80)

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    print(f"\n📅 Timezone: {timezone.get_current_timezone()}")
    print(f"   Current time: {now}")
    print(f"   Today range: {today_start} to {today_end}")

    today_receipts = Receipt.objects.filter(date__gte=today_start, date__lte=today_end).order_by('-date')

    print(f"\n📋 LOCAL - Today's Receipts ({today_receipts.count()}):")
    for receipt in today_receipts:
        sales = receipt.sales.all()
        total = sum(s.total_price for s in sales)
        discounts = sum(s.discount_amount or Decimal('0') for s in sales)

        print(f"\n   Receipt: {receipt.receipt_number} (Local ID: {receipt.id})")
        print(f"      Date: {receipt.date}")
        print(f"      Sales: {sales.count()} items")
        print(f"      Revenue: ₦{total:,.2f}")
        print(f"      Discounts: ₦{discounts:,.2f}")

        # Check if exists remotely
        try:
            check_url = f"{API_BASE_URL}/receipts/?local_receipt_id={receipt.id}"
            response = requests.get(check_url, headers=headers, timeout=10)
            if response.status_code == 200:
                remote_data = response.json()
                if isinstance(remote_data, list):
                    if len(remote_data) > 0:
                        remote_receipt = remote_data[0]
                        print(f"      ✅ EXISTS on PythonAnywhere (Remote ID: {remote_receipt.get('id')})")

                        # Compare sales count
                        remote_sales_count = len(remote_receipt.get('sales', []))
                        if remote_sales_count != sales.count():
                            print(f"      ⚠️  Sales count mismatch! Local: {sales.count()}, Remote: {remote_sales_count}")
                    else:
                        print(f"      ❌ MISSING on PythonAnywhere!")
                else:
                    print(f"      ⚠️  Unexpected response format")
            else:
                print(f"      ❌ Error checking: HTTP {response.status_code}")
        except Exception as e:
            print(f"      ❌ Error checking: {e}")

    # 3. Check for orphaned sales (sales without receipts)
    print("\n" + "=" * 80)
    print("3. DATA INTEGRITY CHECK")
    print("=" * 80)

    orphaned_sales = Sale.objects.filter(receipt__isnull=True).count()
    orphaned_payments = Payment.objects.filter(sale__isnull=True).count()

    print(f"\n🔍 LOCAL DATABASE INTEGRITY:")
    print(f"   Orphaned sales (no receipt): {orphaned_sales}")
    print(f"   Orphaned payments (no sale): {orphaned_payments}")

    # 4. Check recent sync errors
    print("\n" + "=" * 80)
    print("4. RECENT SYNC STATUS")
    print("=" * 80)

    error_log = os.path.join(script_dir, 'sync_errors.log')
    if os.path.exists(error_log):
        print(f"\n📝 Last sync errors (from {error_log}):")
        with open(error_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if lines:
                print("   Last 10 errors:")
                for line in lines[-10:]:
                    print(f"   {line.strip()}")
            else:
                print("   ✅ No errors logged")
    else:
        print("\n✅ No error log found (good!)")

    # 5. Product ID matching check
    print("\n" + "=" * 80)
    print("5. PRODUCT ID MATCHING")
    print("=" * 80)

    print("\n🔍 Checking if local product IDs exist on PythonAnywhere...")

    # Get a few products from today's sales
    today_sales = Sale.objects.filter(receipt__in=today_receipts)[:5]

    for sale in today_sales:
        product_id = sale.product.id
        print(f"\n   Product ID {product_id} ({sale.product.brand} {sale.product.category}):")

        try:
            response = requests.get(f"{API_BASE_URL}/products/{product_id}/", headers=headers, timeout=10)
            if response.status_code == 200:
                remote_product = response.json()
                print(f"      ✅ Exists on PythonAnywhere")
                print(f"         Brand: {remote_product.get('brand')}")
                print(f"         Category: {remote_product.get('category')}")
            elif response.status_code == 404:
                print(f"      ❌ NOT FOUND on PythonAnywhere!")
                print(f"      ⚠️  This will cause sales to fail!")
            else:
                print(f"      ⚠️  HTTP {response.status_code}")
        except Exception as e:
            print(f"      ❌ Error: {e}")

    # 6. Summary
    print("\n" + "=" * 80)
    print("6. SUMMARY & RECOMMENDATIONS")
    print("=" * 80)

    print("\n🎯 KEY FINDINGS:")
    if local_receipts != remote_products:
        print(f"   ⚠️  Product count mismatch: Local={local_products}, Remote={remote_products}")

    print(f"\n📋 ACTION ITEMS:")
    print("   1. Check if all today's receipts exist on PythonAnywhere (see section 2)")
    print("   2. Verify product IDs match (see section 5)")
    print("   3. Review any sync errors (see section 4)")
    print("\n💡 If issues found, run: sync_full_history_robust.bat")

if __name__ == "__main__":
    debug_sync()
