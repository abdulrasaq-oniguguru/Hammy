# Standard library
import json
import logging
from decimal import Decimal

# Django imports
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# Local app imports
from ..forms import CustomerForm
from ..models import (
    Customer, Receipt, LoyaltyConfiguration, LoyaltyTransaction,
    CustomerLoyaltyAccount, ActivityLog
)
from .auth import is_md, is_cashier, is_superuser, user_required_access

logger = logging.getLogger(__name__)


@login_required(login_url='login')
def customer_list(request):
    # Retrieve the search query from the GET request
    query = request.GET.get('search', '')
    customers = Customer.objects.all()

    if query:
        from django.db.models import Q
        # Filter customers based on the search query
        customers = customers.filter(
            Q(name__icontains=query) | Q(phone_number__icontains=query) | Q(address__icontains=query)
        )

    # Add loyalty information to each customer
    from ..loyalty_utils import get_customer_loyalty_summary
    frequent_count = 0
    loyalty_count = 0

    for customer in customers:
        customer.loyalty_info = get_customer_loyalty_summary(customer)
        if customer.frequent_customer:
            frequent_count += 1
        if customer.loyalty_info.get('has_account', False):
            loyalty_count += 1

    context = {
        'customers': customers,
        'search_query': query,
        'total_customers': customers.count(),
        'frequent_customers': frequent_count,
        'loyalty_members': loyalty_count,
    }

    return render(request, 'customer/customer_list.html', context)


@user_passes_test(is_md, login_url='access_denied')
@login_required(login_url='login')
def edit_customer(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            customer = form.save()
            # Log customer update
            ActivityLog.log_activity(
                user=request.user,
                action='customer_update',
                description=f'Updated customer: {customer.name} - {customer.phone_number}',
                model_name='Customer',
                object_id=customer.id,
                object_repr=str(customer),
                request=request
            )
            return redirect('customer_list')
    else:
        form = CustomerForm(instance=customer)
    return render(request, 'customer/edit_customer.html', {'form': form})


@user_passes_test(is_md, login_url='access_denied')
@login_required(login_url='login')
def delete_customer(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        # Log customer deletion before deleting
        customer_info = str(customer)
        customer_id = customer.id
        ActivityLog.log_activity(
            user=request.user,
            action='customer_delete',
            description=f'Deleted customer: {customer_info}',
            model_name='Customer',
            object_id=customer_id,
            object_repr=customer_info,
            request=request
        )
        customer.delete()
        return redirect('customer_list')
    return render(request, 'customer/delete_customer.html', {'customer': customer})


@login_required(login_url='login')
@require_http_methods(["GET"])
def get_customer_loyalty_info(request, customer_id):
    """
    AJAX endpoint to get customer loyalty information
    Returns JSON with customer's loyalty points, balance, and redemption eligibility
    """
    try:
        customer = get_object_or_404(Customer, id=customer_id)

        from ..loyalty_utils import get_customer_loyalty_summary

        # Get loyalty configuration
        try:
            config = LoyaltyConfiguration.get_active_config()
        except Exception:
            return JsonResponse({
                'success': False,
                'error': 'Loyalty program is not configured'
            })

        if not config.is_active:
            return JsonResponse({
                'success': False,
                'error': 'Loyalty program is not active'
            })

        # Get customer loyalty summary
        loyalty_info = get_customer_loyalty_summary(customer)

        if not loyalty_info['has_account']:
            return JsonResponse({
                'success': True,
                'has_account': False,
                'message': 'Customer does not have a loyalty account'
            })

        return JsonResponse({
            'success': True,
            'has_account': True,
            'is_active': loyalty_info['is_active'],
            'current_balance': loyalty_info['current_balance'],
            'total_earned': loyalty_info['total_earned'],
            'total_redeemed': loyalty_info['total_redeemed'],
            'redeemable_value': float(loyalty_info['redeemable_value']),
            'can_redeem': loyalty_info['can_redeem'],
            'tier': loyalty_info.get('tier', ''),
            'minimum_points_for_redemption': config.minimum_points_for_redemption,
            'points_to_currency_rate': float(config.points_to_currency_rate),
            'maximum_discount_percentage': float(config.maximum_discount_percentage)
        })

    except Customer.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Customer not found'
        })
    except Exception as e:
        logger.error(f"Error fetching loyalty info for customer {customer_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required(login_url='login')
@require_http_methods(["POST"])
@csrf_exempt
def apply_loyalty_discount(request):
    """
    AJAX endpoint to calculate loyalty discount before applying it to a receipt
    This is called during POS to preview the discount
    """
    try:
        data = json.loads(request.body)
        customer_id = data.get('customer_id')
        points_to_redeem = int(data.get('points_to_redeem', 0))
        transaction_total = Decimal(str(data.get('transaction_total', 0)))

        if not customer_id or not points_to_redeem or not transaction_total:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameters'
            })

        customer = get_object_or_404(Customer, id=customer_id)

        # Get loyalty configuration
        try:
            config = LoyaltyConfiguration.get_active_config()
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error loading loyalty configuration: {str(e)}'
            })

        if not config.is_active:
            return JsonResponse({
                'success': False,
                'error': 'Loyalty program is not active'
            })

        # Get loyalty account
        try:
            loyalty_account = customer.loyalty_account
        except CustomerLoyaltyAccount.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Customer does not have a loyalty account'
            })

        # Validate points redemption
        if not loyalty_account.can_redeem_points(points_to_redeem):
            return JsonResponse({
                'success': False,
                'error': f'Cannot redeem {points_to_redeem} points. '
                         f'Customer has {loyalty_account.current_balance} points. '
                         f'Minimum redemption: {config.minimum_points_for_redemption} points.'
            })

        # Calculate discount amount
        discount_amount = config.calculate_discount_from_points(points_to_redeem)

        # Check maximum discount percentage
        max_discount = config.get_maximum_redeemable_amount(transaction_total)

        if discount_amount > max_discount:
            return JsonResponse({
                'success': False,
                'error': f'Discount amount (₦{discount_amount}) exceeds maximum allowed '
                         f'(₦{max_discount}, {config.maximum_discount_percentage}% of transaction)'
            })

        if discount_amount > transaction_total:
            return JsonResponse({
                'success': False,
                'error': f'Discount amount (₦{discount_amount}) exceeds transaction total (₦{transaction_total})'
            })

        # Return discount preview
        return JsonResponse({
            'success': True,
            'points_to_redeem': points_to_redeem,
            'discount_amount': float(discount_amount),
            'remaining_balance': loyalty_account.current_balance - points_to_redeem,
            'new_total': float(transaction_total - discount_amount)
        })

    except Customer.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Customer not found'
        })
    except Exception as e:
        logger.error(f"Error applying loyalty discount: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required(login_url='login')
@require_http_methods(["POST"])
@csrf_exempt
def enroll_customer_in_loyalty(request):
    """
    AJAX endpoint to enroll a customer in the loyalty program
    """
    try:
        data = json.loads(request.body)
        customer_id = data.get('customer_id')

        if not customer_id:
            return JsonResponse({
                'success': False,
                'error': 'Customer ID is required'
            })

        customer = get_object_or_404(Customer, id=customer_id)

        # Check if customer already has a loyalty account
        if hasattr(customer, 'loyalty_account'):
            return JsonResponse({
                'success': False,
                'error': 'Customer is already enrolled in the loyalty program'
            })

        # Check if loyalty program is configured and active
        try:
            config = LoyaltyConfiguration.get_active_config()
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': 'Loyalty program is not configured'
            })

        if not config.is_active:
            return JsonResponse({
                'success': False,
                'error': 'Loyalty program is not active'
            })

        # Create loyalty account
        from ..loyalty_utils import get_or_create_loyalty_account
        loyalty_account = get_or_create_loyalty_account(customer)

        logger.info(f"Customer {customer.name} (ID: {customer.id}) enrolled in loyalty program by user {request.user.username}")

        return JsonResponse({
            'success': True,
            'message': f'{customer.name} has been enrolled in the loyalty program',
            'loyalty_account_id': loyalty_account.id,
            'current_balance': loyalty_account.current_balance
        })

    except Customer.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Customer not found'
        })
    except Exception as e:
        logger.error(f"Error enrolling customer in loyalty program: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required(login_url='login')
def customer_detail(request, pk):
    """
    View customer details including loyalty information
    """
    customer = get_object_or_404(Customer, pk=pk)

    # Get loyalty information
    from ..loyalty_utils import get_customer_loyalty_summary

    loyalty_info = get_customer_loyalty_summary(customer)

    # Get recent loyalty transactions if enrolled
    loyalty_transactions = []
    if loyalty_info['has_account']:
        loyalty_transactions = LoyaltyTransaction.objects.filter(
            loyalty_account=customer.loyalty_account
        ).order_by('-created_at')[:10]

    # Get recent receipts
    recent_receipts = Receipt.objects.filter(
        customer=customer
    ).order_by('-date')[:5]

    context = {
        'customer': customer,
        'loyalty_info': loyalty_info,
        'loyalty_transactions': loyalty_transactions,
        'recent_receipts': recent_receipts,
    }

    return render(request, 'customer/customer_detail.html', context)
