import os
import sys
import django
from datetime import date

# Setup Django
script_dir = os.path.dirname(os.path.abspath(__file__))
mystore_dir = os.path.join(script_dir, 'mystore')
sys.path.insert(0, mystore_dir)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mystore.settings')
os.chdir(mystore_dir)
django.setup()

from store.models import Sale, Receipt, Payment

# Get today's receipts
today = date.today()
receipts = Receipt.objects.filter(date__date=today).order_by('-date')

print(f"\n=== SALES FROM {today} ===\n")
for receipt in receipts:
    print(f"\nReceipt #{receipt.receipt_number} at {receipt.date.strftime('%I:%M %p')}")
    print(f"  Receipt ID: {receipt.id}")

    sales = receipt.sales.all()
    total = 0
    for sale in sales:
        print(f"  - {sale.product.brand} ({sale.product.category})")
        print(f"    Quantity: {sale.quantity}")
        print(f"    Total Price: ₦{sale.total_price}")
        print(f"    Discount: ₦{sale.discount_amount or 0}")
        total += sale.total_price

    print(f"  RECEIPT TOTAL: ₦{total}")

    # Check payment
    if sales.exists() and sales.first().payment:
        payment = sales.first().payment
        print(f"  Payment Total: ₦{payment.total_amount}")
        print(f"  Payment Status: {payment.payment_status}")
        print(f"  Payment Methods:")
        for pm in payment.payment_methods.all():
            print(f"    - {pm.payment_method}: ₦{pm.amount}")

print("\n")
