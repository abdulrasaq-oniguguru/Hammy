"""
Compare Local vs Remote Data to Find Discrepancies
Shows exactly what's different between local and PythonAnywhere
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

from store.models import Receipt, Sale, Payment
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
        print(f"❌ Authentication failed: {e}")
        return None

def get_local_today_stats():
    """Get today's stats from local database"""
    # Get timezone-aware today
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    print(f"\n📅 LOCAL TIMEZONE: {timezone.get_current_timezone()}")
    print(f"   Current time: {now}")
    print(f"   Today range: {today_start} to {today_end}")

    receipts_today = Receipt.objects.filter(date__gte=today_start, date__lte=today_end)

    stats = {
        'receipt_count': receipts_today.count(),
        'receipts': []
    }

    total_revenue = Decimal('0.00')
    total_discounts = Decimal('0.00')

    for receipt in receipts_today:
        sales = receipt.sales.all()
        receipt_total = sum(sale.total_price for sale in sales)
        receipt_discounts = sum(sale.discount_amount or Decimal('0.00') for sale in sales)

        payment_info = "No payment"
        if sales.exists() and sales.first().payment:
            payment = sales.first().payment
            payment_info = f"{payment.payment_status} - ₦{payment.total_paid:,.2f}"

        stats['receipts'].append({
            'id': receipt.id,
            'number': receipt.receipt_number,
            'date': receipt.date,
            'sales_count': sales.count(),
            'revenue': receipt_total,
            'discounts': receipt_discounts,
            'payment': payment_info
        })

        total_revenue += receipt_total
        total_discounts += receipt_discounts

    stats['total_revenue'] = total_revenue
    stats['total_discounts'] = total_discounts
    stats['net_revenue'] = total_revenue - total_discounts

    return stats

def get_remote_today_stats(token):
    """Get today's stats from PythonAnywhere"""
    try:
        headers = {'Authorization': f'Bearer {token}'}

        # Get dashboard stats
        response = requests.get(
            f"{API_BASE_URL}/dashboard/",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        dashboard = response.json()

        # Get recent receipts
        response = requests.get(
            f"{API_BASE_URL}/receipts/recent/",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        recent_receipts = response.json()

        return {
            'dashboard': dashboard,
            'recent_receipts': recent_receipts
        }

    except Exception as e:
        print(f"❌ Failed to get remote data: {e}")
        return None

def compare_data():
    """Compare local and remote data"""
    print("=" * 80)
    print("  LOCAL vs REMOTE DATA COMPARISON")
    print("=" * 80)

    # Get local stats
    print("\n🔍 Analyzing LOCAL database...")
    local = get_local_today_stats()

    print(f"\n📊 LOCAL STATS (Today):")
    print(f"   Receipt Count: {local['receipt_count']}")
    print(f"   Total Revenue: ₦{local['total_revenue']:,.2f}")
    print(f"   Total Discounts: ₦{local['total_discounts']:,.2f}")
    print(f"   Net Revenue: ₦{local['net_revenue']:,.2f}")

    print(f"\n📋 LOCAL RECEIPTS (Today):")
    for r in local['receipts']:
        print(f"   {r['number']} (ID: {r['id']}):")
        print(f"      Date: {r['date']}")
        print(f"      Sales: {r['sales_count']}")
        print(f"      Revenue: ₦{r['revenue']:,.2f}")
        print(f"      Discounts: ₦{r['discounts']:,.2f}")
        print(f"      Payment: {r['payment']}")

    # Get remote stats
    print(f"\n🔍 Fetching REMOTE data from PythonAnywhere...")
    token = get_token()
    if not token:
        print("❌ Cannot fetch remote data without token")
        return

    remote = get_remote_today_stats(token)
    if not remote:
        print("❌ Failed to get remote data")
        return

    print(f"\n📊 REMOTE STATS (from PythonAnywhere):")
    dashboard = remote.get('dashboard', {})
    print(f"   Today's Revenue: {dashboard.get('todays_revenue', 'N/A')}")
    print(f"   Today's Receipts: {dashboard.get('todays_receipts', 'N/A')}")
    print(f"   This Week Sales: {dashboard.get('this_week_sales', 'N/A')}")

    print(f"\n📋 REMOTE RECENT RECEIPTS:")
    recent = remote.get('recent_receipts', [])
    if isinstance(recent, list):
        for r in recent[:10]:
            print(f"   {r.get('receipt_number', 'N/A')} (ID: {r.get('id', 'N/A')}):")
            print(f"      Date: {r.get('date', 'N/A')}")
            print(f"      Total: {r.get('total', 'N/A')}")
    else:
        print(f"   {recent}")

    # Comparison
    print("\n" + "=" * 80)
    print("  COMPARISON SUMMARY")
    print("=" * 80)

    if local['receipt_count'] != dashboard.get('todays_receipts', 0):
        print(f"⚠️  MISMATCH: Receipt count")
        print(f"   Local: {local['receipt_count']}")
        print(f"   Remote: {dashboard.get('todays_receipts', 'N/A')}")
        print(f"   Difference: {local['receipt_count'] - dashboard.get('todays_receipts', 0)}")

    # Check for missing receipts
    print(f"\n🔍 Checking for missing receipts on PythonAnywhere...")
    print(f"   (Checking if all {local['receipt_count']} local receipts exist remotely)")

    headers = {'Authorization': f'Bearer {token}'}
    missing_receipts = []

    for r in local['receipts']:
        try:
            # Check if receipt exists remotely by local_receipt_id
            response = requests.get(
                f"{API_BASE_URL}/receipts/?local_receipt_id={r['id']}",
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) == 0:
                    missing_receipts.append(r)
                    print(f"   ❌ Missing: {r['number']} (ID: {r['id']})")
                elif isinstance(data, list) and len(data) > 0:
                    print(f"   ✅ Found: {r['number']} (ID: {r['id']})")
        except Exception as e:
            print(f"   ⚠️  Error checking {r['number']}: {e}")

    if missing_receipts:
        print(f"\n⚠️  {len(missing_receipts)} receipts are MISSING on PythonAnywhere:")
        for r in missing_receipts:
            print(f"   - {r['number']} (Local ID: {r['id']}, Date: {r['date']})")
    else:
        print(f"\n✅ All local receipts found on PythonAnywhere!")

    # Timezone warning
    print(f"\n💡 TIMEZONE NOTE:")
    print(f"   If numbers don't match, it's likely a timezone issue.")
    print(f"   Local timezone: {timezone.get_current_timezone()}")
    print(f"   PythonAnywhere likely uses: UTC")
    print(f"   This means 'today' might be different on each system!")

if __name__ == "__main__":
    compare_data()
