"""
Sync Script to Push Data to PythonAnywhere Minimal API
Pushes only necessary data (NO customer information)
"""

import os
import sys
import django
import requests
from datetime import datetime, timedelta

# Setup Django
script_dir = os.path.dirname(os.path.abspath(__file__))
mystore_dir = os.path.join(script_dir, 'mystore')

# Add mystore directory to Python path
sys.path.insert(0, mystore_dir)

# Set Django settings and setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mystore.settings')

# Change to mystore directory for Django to find apps correctly
original_cwd = os.getcwd()
os.chdir(mystore_dir)

try:
    django.setup()
except Exception as e:
    print(f"Error setting up Django: {e}")
    print(f"Script dir: {script_dir}")
    print(f"Mystore dir: {mystore_dir}")
    print(f"Current dir: {os.getcwd()}")
    print(f"Sys path: {sys.path[:3]}")
    raise

from store.models import Product, Sale, Receipt, Payment, PaymentMethod as PaymentMethodModel

# Configuration
API_BASE_URL = "https://asoniguguru.pythonanywhere.com/api/oem"
API_USERNAME = "asoniguguru"  # Update this
API_PASSWORD = "*3mb741101"  # Update this

def get_token():
    """Get JWT authentication token"""
    print("🔑 Getting authentication token...")
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

def sync_products(token):
    """Sync all products (NO pricing info if sensitive)"""
    print("\n📦 Syncing Products...")
    try:
        products = Product.objects.all()
        product_data = []

        for product in products:
            product_data.append({
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
        response = requests.post(
            f"{API_BASE_URL}/sync/products/",
            json={'products': product_data},
            headers=headers,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        print(f"✅ Synced {result.get('total', 0)} products ({result.get('created', 0)} created, {result.get('updated', 0)} updated)")
        return True
    except Exception as e:
        print(f"❌ Product sync failed: {e}")
        return False

def sync_receipts_and_sales(token):
    """Sync receipts, sales, and payments (NO customer info)"""
    print("\n🧾 Syncing Receipts and Sales...")
    try:
        # Get recent receipts (last 90 days to avoid overload)
        cutoff_date = datetime.now() - timedelta(days=90)
        receipts = Receipt.objects.filter(date__gte=cutoff_date).select_related('customer').prefetch_related('sales__product', 'sales__payment__payment_methods')

        receipt_data = []
        for receipt in receipts:
            # Get sales for this receipt
            sales = receipt.sales.all()
            if not sales.exists():
                continue

            sales_data = []
            for sale in sales:
                sales_data.append({
                    'product_id': sale.product.id,
                    'quantity': sale.quantity,
                    'total_price': float(sale.total_price),
                    'sale_date': sale.sale_date.isoformat() if sale.sale_date else None,
                })

            # Get payment info (NO customer data)
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
                    'id': payment_obj.id,
                    'payment_status': payment_obj.payment_status,
                    'total_amount': float(payment_obj.total_amount),
                    'total_paid': float(payment_obj.total_paid),
                    'payment_methods': payment_methods,
                }

            receipt_data.append({
                'receipt_number': receipt.receipt_number or f'R{receipt.id}',
                'date': receipt.date.isoformat() if receipt.date else None,
                'customer_id': None,  # NO CUSTOMER INFO
                'sales': sales_data,
                'payment': payment,
            })

        headers = {'Authorization': f'Bearer {token}'}
        response = requests.post(
            f"{API_BASE_URL}/sync/receipts/",
            json={'receipts': receipt_data},
            headers=headers,
            timeout=120
        )
        response.raise_for_status()
        result = response.json()
        print(f"✅ Synced {result.get('synced', 0)} receipts with sales and payments")
        return True
    except Exception as e:
        print(f"❌ Receipts/Sales sync failed: {e}")
        return False

def main():
    """Main sync function"""
    print("=" * 60)
    print("  MINIMAL API SYNC - NO CUSTOMER DATA")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Target: {API_BASE_URL}")
    print()

    # Get authentication token
    token = get_token()
    if not token:
        print("\n❌ Sync aborted - authentication failed")
        return

    # Sync data
    success_count = 0

    if sync_products(token):
        success_count += 1

    if sync_receipts_and_sales(token):
        success_count += 1

    # Summary
    print("\n" + "=" * 60)
    if success_count == 2:
        print("✅ SYNC COMPLETED SUCCESSFULLY")
    else:
        print(f"⚠️ SYNC COMPLETED WITH ERRORS ({success_count}/2 successful)")
    print("=" * 60)
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

if __name__ == "__main__":
    main()
