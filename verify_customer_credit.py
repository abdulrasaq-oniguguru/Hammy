#!/usr/bin/env python
"""
Verify customer can access and use their store credit
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'mystore'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mystore.settings')
django.setup()

from store.models import Customer, StoreCredit

def verify_customer_credits(customer_id):
    """Verify customer's store credits"""
    print(f"\n{'='*60}")
    print(f"CUSTOMER STORE CREDITS VERIFICATION")
    print(f"{'='*60}\n")

    try:
        # Get the customer
        customer = Customer.objects.get(id=customer_id)
        print(f"Customer: {customer.name}")
        print(f"Phone: {customer.phone_number or 'N/A'}")
        print(f"Email: {customer.email or 'N/A'}")
        print(f"\n{'-'*60}\n")

        # Get all store credits
        all_credits = StoreCredit.objects.filter(customer=customer)
        active_credits = all_credits.filter(is_active=True, remaining_balance__gt=0)

        print(f"Total Store Credits: {all_credits.count()}")
        print(f"Active Credits with Balance: {active_credits.count()}")
        print(f"\n{'-'*60}\n")

        if active_credits.exists():
            total_balance = sum(credit.remaining_balance for credit in active_credits)
            print(f"TOTAL AVAILABLE CREDIT: NGN{total_balance:,.2f}")
            print(f"\nDETAILS:\n")

            for credit in active_credits:
                print(f"  OK {credit.credit_number}")
                print(f"    Original: NGN{credit.original_amount:,.2f}")
                print(f"    Remaining: NGN{credit.remaining_balance:,.2f}")
                print(f"    Issued: {credit.issued_date.strftime('%Y-%m-%d %H:%M')}")
                if credit.return_transaction:
                    print(f"    From Return: {credit.return_transaction.return_number}")
                if credit.expiry_date:
                    print(f"    Expires: {credit.expiry_date.strftime('%Y-%m-%d')}")
                if credit.notes:
                    print(f"    Notes: {credit.notes}")
                print()
        else:
            print("  X No active store credits found")

        print(f"{'='*60}\n")

        # Check if customer can use credits
        print("USAGE INSTRUCTIONS:")
        print("  1. Go to: http://127.0.0.1:8000/store-credits/")
        print("  2. During checkout, select 'Use Store Credit'")
        print(f"  3. Available balance: NGN{total_balance:,.2f}\n")

        return True

    except Customer.DoesNotExist:
        print(f"X ERROR: Customer with ID {customer_id} not found")
        return False
    except Exception as e:
        print(f"X ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        customer_id = int(sys.argv[1])
    else:
        customer_id = 2  # Default to customer Ham (ID 2)

    verify_customer_credits(customer_id)
