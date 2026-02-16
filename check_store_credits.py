#!/usr/bin/env python
"""
Diagnostic script to check store credits for a specific return
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'mystore'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mystore.settings')
django.setup()

from store.models import Return, StoreCredit

def check_return_credits(return_id):
    """Check store credits for a specific return"""
    print(f"\n{'='*60}")
    print(f"CHECKING STORE CREDITS FOR RETURN ID: {return_id}")
    print(f"{'='*60}\n")

    try:
        # Get the return
        return_obj = Return.objects.get(id=return_id)
        print(f"Return Number: {return_obj.return_number}")
        print(f"Status: {return_obj.status}")
        print(f"Refund Type: {return_obj.refund_type}")
        print(f"Refund Amount: ₦{return_obj.refund_amount}")
        print(f"Customer: {return_obj.customer.name if return_obj.customer else 'None'}")
        print(f"Customer ID: {return_obj.customer.id if return_obj.customer else 'None'}")
        print(f"\n{'-'*60}\n")

        # Check for store credits
        store_credits = StoreCredit.objects.filter(return_transaction=return_obj)
        print(f"Store Credits Found: {store_credits.count()}")

        if store_credits.exists():
            for credit in store_credits:
                print(f"\n  ✓ Credit Number: {credit.credit_number}")
                print(f"    Original Amount: ₦{credit.original_amount}")
                print(f"    Remaining Balance: ₦{credit.remaining_balance}")
                print(f"    Customer: {credit.customer.name}")
                print(f"    Issued Date: {credit.issued_date}")
                print(f"    Issued By: {credit.issued_by.username if credit.issued_by else 'N/A'}")
                print(f"    Active: {credit.is_active}")
        else:
            print("  ✗ No store credits found for this return")

            # Check if customer has any store credits
            if return_obj.customer:
                customer_credits = StoreCredit.objects.filter(customer=return_obj.customer)
                print(f"\n  Customer has {customer_credits.count()} total store credit(s):")
                for credit in customer_credits:
                    print(f"    - {credit.credit_number}: ₦{credit.remaining_balance}")

        print(f"\n{'='*60}\n")

    except Return.DoesNotExist:
        print(f"✗ ERROR: Return with ID {return_id} not found")
    except Exception as e:
        print(f"✗ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        return_id = int(sys.argv[1])
    else:
        return_id = 16  # Default to return ID 16

    check_return_credits(return_id)
