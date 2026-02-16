import os
import sys
import django

# Setup Django
script_dir = os.path.dirname(os.path.abspath(__file__))
mystore_dir = os.path.join(script_dir, 'mystore')

sys.path.insert(0, mystore_dir)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mystore.settings')
os.chdir(mystore_dir)
django.setup()

from store.models import Receipt

print("Recent receipts (last 10):")
print("-" * 60)
for r in Receipt.objects.order_by('-date')[:10]:
    print(f"Receipt #{r.receipt_number}: {r.date}")
