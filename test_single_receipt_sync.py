"""
Test script to sync just ONE receipt to debug 500 errors
"""

import os
import sys
import django
import requests
import json
from datetime import datetime

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

from store.models import Receipt, Sale

# Configuration
API_BASE_URL = "https://asoniguguru.pythonanywhere.com/api/oem"
API_USERNAME = "admin"
API_PASSWORD = "*3mb741101"

def get_token():
    """Get JWT authentication token"""
    print("Getting authentication token...")
    try:
        response = requests.post(
            f"{API_BASE_URL}/token/",
            json={"username": API_USERNAME, "password": API_PASSWORD},
            timeout=30
        )
        response.raise_for_status()
        token = response.json()['access']
        print("✅ Authentication successful")
        return token
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return None

def test_single_receipt():
    """Test syncing a single receipt"""
    print("=" * 70)
    print("  TESTING SINGLE RECEIPT SYNC")
    print("=" * 70)

    # Get token
    token = get_token()
    if not token:
        print("❌ Cannot proceed without token")
        return

    # Get ONE receipt with sales
    receipt = Receipt.objects.filter(sales__isnull=False).first()

    if not receipt:
        print("❌ No receipts with sales found")
        return

    print(f"\n📋 Testing with Receipt: {receipt.receipt_number}")
    print(f"   Receipt ID: {receipt.id}")
    print(f"   Date: {receipt.date}")

    # Build receipt data
    sales = receipt.sales.all()
    print(f"   Sales count: {sales.count()}")

    sales_data = []
    for sale in sales:
        sale_dict = {
            'local_sale_id': sale.id,
            'product_id': sale.product.id,
            'quantity': sale.quantity,
            'total_price': float(sale.total_price),
            'discount_amount': float(sale.discount_amount) if sale.discount_amount else 0.0,
            'sale_date': sale.sale_date.isoformat() if sale.sale_date else None,
        }
        sales_data.append(sale_dict)
        print(f"   - Sale {sale.id}: Product {sale.product.id}, Qty {sale.quantity}")

    # Get payment info
    payment = None
    if sales.exists() and sales.first().payment:
        payment_obj = sales.first().payment
        print(f"   Payment ID: {payment_obj.id}")
        print(f"   Payment Status: {payment_obj.payment_status}")

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
    else:
        print("   ⚠️  No payment for this receipt")

    receipt_data = {
        'local_receipt_id': receipt.id,
        'receipt_number': receipt.receipt_number or f'R{receipt.id}',
        'date': receipt.date.isoformat() if receipt.date else None,
        'customer_id': None,
        'delivery_cost': float(receipt.delivery_cost) if receipt.delivery_cost else 0.0,
        'sales': sales_data,
        'payment': payment,
    }

    # Print the JSON data we're sending
    print("\n📤 Sending this data:")
    print(json.dumps({'receipts': [receipt_data]}, indent=2))

    # Send to API
    print("\n🚀 Sending to API...")
    headers = {'Authorization': f'Bearer {token}'}

    try:
        response = requests.post(
            f"{API_BASE_URL}/sync/receipts/",
            json={'receipts': [receipt_data]},
            headers=headers,
            timeout=120
        )

        print(f"\n📥 Response Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")

        if response.status_code == 200:
            result = response.json()
            print(f"✅ SUCCESS!")
            print(f"   Response: {json.dumps(result, indent=2)}")
        else:
            print(f"❌ FAILED!")
            print(f"   Status: {response.status_code}")
            print(f"   Response Text: {response.text}")

            # Try to parse error message
            try:
                error_data = response.json()
                print(f"   Error JSON: {json.dumps(error_data, indent=2)}")
            except:
                print(f"   Raw Error: {response.text}")

    except Exception as e:
        print(f"❌ Exception occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_single_receipt()
