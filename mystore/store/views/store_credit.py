# Standard library
import logging
from decimal import Decimal

# Django imports
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404

# Local app imports
from ..models import (
    Customer, StoreCredit
)
from .auth import is_md, is_cashier, is_superuser, user_required_access

logger = logging.getLogger(__name__)


@login_required
def store_credit_list(request):
    """List all store credits"""
    store_credits = StoreCredit.objects.all().select_related('customer', 'issued_by')

    # Filter by active status
    is_active = request.GET.get('active')
    if is_active == '1':
        store_credits = store_credits.filter(is_active=True, remaining_balance__gt=0)
    elif is_active == '0':
        store_credits = store_credits.filter(is_active=False)

    # Filter by customer
    customer_id = request.GET.get('customer')
    if customer_id:
        store_credits = store_credits.filter(customer_id=customer_id)

    # Calculate totals
    total_credits = store_credits.count()
    total_balance = store_credits.aggregate(Sum('remaining_balance'))['remaining_balance__sum'] or 0

    context = {
        'credits': store_credits,  # Changed from 'store_credits' to 'credits' to match template
        'total_credits': total_credits,
        'total_balance': total_balance,
    }
    return render(request, 'store_credits/store_credit_list.html', context)


@login_required
def store_credit_detail(request, credit_id):
    """View details of a specific store credit"""
    store_credit = get_object_or_404(
        StoreCredit.objects.select_related('customer', 'issued_by', 'return_transaction'),
        id=credit_id
    )

    usages = store_credit.usages.all().select_related('receipt', 'used_by')

    context = {
        'store_credit': store_credit,
        'credit': store_credit,   # template uses {{ credit.* }}
        'usages': usages,
    }
    return render(request, 'store_credits/store_credit_detail.html', context)


@login_required
def get_customer_store_credit(request, customer_id):
    """API endpoint to get customer's store credit information"""
    try:
        customer = Customer.objects.get(id=customer_id)

        # Get all active store credits for this customer
        active_credits = StoreCredit.objects.filter(
            customer=customer,
            is_active=True,
            remaining_balance__gt=0
        )

        # Calculate total available balance
        total_balance = sum([credit.remaining_balance for credit in active_credits])

        # Get credit details
        credits_list = []
        for credit in active_credits:
            credits_list.append({
                'credit_number': credit.credit_number,
                'remaining_balance': float(credit.remaining_balance),
                'original_amount': float(credit.original_amount),
                'issued_date': credit.issued_date.strftime('%Y-%m-%d'),
            })

        return JsonResponse({
            'success': True,
            'customer_id': customer.id,
            'customer_name': customer.name,
            'total_balance': float(total_balance),
            'credits_count': active_credits.count(),
            'credits': credits_list
        })

    except Customer.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Customer not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
