"""
Loyalty Program Utility Functions
Handles points calculation, email notifications, and loyalty operations
"""

from decimal import Decimal
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from .models import (
    LoyaltyConfiguration,
    CustomerLoyaltyAccount,
    LoyaltyTransaction,
    Customer,
    Receipt,
    StoreConfiguration
)
import logging

logger = logging.getLogger(__name__)


def get_or_create_loyalty_account(customer):
    """
    Get or create a loyalty account for a customer

    Args:
        customer: Customer instance

    Returns:
        CustomerLoyaltyAccount instance
    """
    account, created = CustomerLoyaltyAccount.objects.get_or_create(
        customer=customer,
        defaults={'is_active': True}
    )

    if created:
        # Send welcome email if configured
        send_loyalty_welcome_email(account)
        logger.info(f"Created loyalty account for customer {customer.name}")

    return account


def process_sale_loyalty_points(receipt):
    """
    Process loyalty points for a completed sale

    Args:
        receipt: Receipt instance

    Returns:
        dict with points_earned, previous_balance, new_balance
    """
    # Check if loyalty program is active
    try:
        config = LoyaltyConfiguration.get_active_config()
    except Exception as e:
        logger.error(f"Error getting loyalty config: {e}")
        return None

    if not config.is_active:
        logger.info("Loyalty program is not active")
        return None

    # Check if receipt has a customer
    if not receipt.customer:
        logger.info(f"Receipt {receipt.receipt_number} has no customer")
        return None

    # Check if customer has email for notifications
    if not receipt.customer.email:
        logger.warning(f"Customer {receipt.customer.name} has no email for loyalty notifications")

    # Get or create loyalty account
    loyalty_account = get_or_create_loyalty_account(receipt.customer)

    if not loyalty_account.is_active:
        logger.info(f"Loyalty account for {receipt.customer.name} is not active")
        return None

    # Calculate transaction total (including delivery if any)
    transaction_total = receipt.total_with_delivery or Decimal('0.00')

    # Initialize result
    result = {
        'points_earned': 0,
        'previous_balance': loyalty_account.current_balance,
        'new_balance': loyalty_account.current_balance,
        'transaction_amount': transaction_total,
        'loyalty_account': loyalty_account,
        'discount_eligible': False,
        'discount_applied': False
    }

    # Handle different loyalty calculation types
    if config.calculation_type == 'transaction_count_discount':
        # Transaction Count Discount: Track transactions and apply discount
        loyalty_account.transaction_count += 1

        # Check if eligible for discount
        if loyalty_account.transaction_count >= config.required_transaction_count:
            loyalty_account.discount_eligible = True
            result['discount_eligible'] = True
            result['discount_percentage'] = config.transaction_discount_percentage
            logger.info(f"Customer {receipt.customer.name} is now eligible for {config.transaction_discount_percentage}% discount")

        loyalty_account.save()
        result['transaction_count'] = loyalty_account.transaction_count
        result['required_count'] = config.required_transaction_count

    elif config.calculation_type == 'item_count_discount':
        # Item Count Discount: Track items purchased
        # Count items in this receipt
        item_count = 0
        if hasattr(receipt, 'sales') and receipt.sales.exists():
            item_count = sum(sale.quantity for sale in receipt.sales.all())

        loyalty_account.item_count += item_count
        loyalty_account.save()

        result['item_count'] = loyalty_account.item_count
        result['items_added'] = item_count
        result['required_count'] = config.required_item_count

        # Check if eligible for discount based on item count
        if loyalty_account.item_count >= config.required_item_count:
            result['discount_eligible'] = True
            result['discount_percentage'] = config.item_discount_percentage
            logger.info(f"Customer {receipt.customer.name} has {loyalty_account.item_count} items, eligible for discount")

    else:
        # Points-based system (per_transaction, per_amount, combined)
        # Calculate points earned
        points_earned = config.calculate_points_earned(transaction_total)

        if points_earned <= 0:
            logger.info(f"No points earned for receipt {receipt.receipt_number}")
            return None

        # Store previous balance
        previous_balance = loyalty_account.current_balance

        # Add points to account
        description = f"Purchase - Receipt {receipt.receipt_number}"
        loyalty_account.add_points(
            points=points_earned,
            description=description,
            related_receipt=receipt
        )

        result['points_earned'] = points_earned
        result['previous_balance'] = previous_balance
        result['new_balance'] = loyalty_account.current_balance

    # NOTE: Loyalty points email is now sent as part of the regular receipt email
    # with PDF attachment. The separate send_points_earned_email function is no longer used
    # to avoid sending duplicate emails to customers.

    logger.info(
        f"Processed loyalty points for receipt {receipt.receipt_number}: "
        f"{points_earned} points earned"
    )

    return result


def apply_count_based_discount(payment, customer):
    """
    Apply transaction or item count based discount to a payment

    Args:
        payment: Payment instance
        customer: Customer instance

    Returns:
        dict with discount details or None if not eligible
    """
    try:
        config = LoyaltyConfiguration.get_active_config()
    except Exception:
        return None

    if not config.is_active:
        return None

    # Get loyalty account
    try:
        loyalty_account = customer.loyalty_account
    except CustomerLoyaltyAccount.DoesNotExist:
        return None

    if not loyalty_account.is_active:
        return None

    discount_amount = Decimal('0.00')
    discount_percentage = Decimal('0.00')

    # Transaction Count Discount
    if config.calculation_type == 'transaction_count_discount':
        if loyalty_account.discount_eligible and loyalty_account.transaction_count >= config.required_transaction_count:
            discount_percentage = config.transaction_discount_percentage
            discount_amount = payment.total_amount * (discount_percentage / Decimal('100'))

            # Apply discount
            payment.discount_percentage = discount_percentage
            payment.discount_amount = discount_amount

            # Reset transaction count and eligibility
            loyalty_account.transaction_count = 0
            loyalty_account.discount_eligible = False
            loyalty_account.discount_count += 1
            loyalty_account.save()

            logger.info(f"Applied {discount_percentage}% transaction count discount for {customer.name}")

            return {
                'discount_type': 'transaction_count',
                'discount_percentage': discount_percentage,
                'discount_amount': discount_amount,
                'transactions_required': config.required_transaction_count
            }

    # Item Count Discount
    elif config.calculation_type == 'item_count_discount':
        if loyalty_account.item_count >= config.required_item_count:
            # Calculate how many times the threshold was reached
            discount_multiplier = int(loyalty_account.item_count / config.required_item_count)
            discount_percentage = config.item_discount_percentage * discount_multiplier

            # Cap discount at reasonable limit (e.g., 50%)
            max_discount = Decimal('50.00')
            if discount_percentage > max_discount:
                discount_percentage = max_discount

            discount_amount = payment.total_amount * (discount_percentage / Decimal('100'))

            # Apply discount
            payment.discount_percentage = discount_percentage
            payment.discount_amount = discount_amount

            # Reset item count (or reduce by threshold amount)
            loyalty_account.item_count = loyalty_account.item_count % config.required_item_count
            loyalty_account.discount_count += 1
            loyalty_account.save()

            logger.info(f"Applied {discount_percentage}% item count discount for {customer.name}")

            return {
                'discount_type': 'item_count',
                'discount_percentage': discount_percentage,
                'discount_amount': discount_amount,
                'items_required': config.required_item_count,
                'multiplier': discount_multiplier
            }

    return None


def apply_loyalty_discount(receipt, points_to_redeem, user=None):
    """
    Apply loyalty points as a discount to a receipt

    Args:
        receipt: Receipt instance
        points_to_redeem: Integer number of points to redeem
        user: User applying the discount (optional)

    Returns:
        dict with success status and details
    """
    try:
        config = LoyaltyConfiguration.get_active_config()
    except Exception as e:
        return {
            'success': False,
            'error': f'Error loading loyalty configuration: {str(e)}'
        }

    if not config.is_active:
        return {
            'success': False,
            'error': 'Loyalty program is not active'
        }

    if not receipt.customer:
        return {
            'success': False,
            'error': 'Receipt must have a customer to apply loyalty discount'
        }

    # Get loyalty account
    try:
        loyalty_account = receipt.customer.loyalty_account
    except CustomerLoyaltyAccount.DoesNotExist:
        return {
            'success': False,
            'error': 'Customer does not have a loyalty account'
        }

    # Validate points redemption
    if not loyalty_account.can_redeem_points(points_to_redeem):
        return {
            'success': False,
            'error': f'Cannot redeem {points_to_redeem} points. '
                     f'Customer has {loyalty_account.current_balance} points. '
                     f'Minimum redemption: {config.minimum_points_for_redemption} points.'
        }

    # Calculate discount amount
    discount_amount = config.calculate_discount_from_points(points_to_redeem)

    # Get transaction total
    transaction_total = receipt.total_with_delivery or Decimal('0.00')

    # Check maximum discount percentage
    max_discount = config.get_maximum_redeemable_amount(transaction_total)

    if discount_amount > max_discount:
        return {
            'success': False,
            'error': f'Discount amount (₦{discount_amount}) exceeds maximum allowed '
                     f'(₦{max_discount}, {config.maximum_discount_percentage}% of transaction)'
        }

    if discount_amount > transaction_total:
        return {
            'success': False,
            'error': f'Discount amount (₦{discount_amount}) exceeds transaction total (₦{transaction_total})'
        }

    # Redeem points
    description = f"Redeemed for discount - Receipt {receipt.receipt_number}"
    success = loyalty_account.redeem_points(
        points=points_to_redeem,
        description=description,
        related_receipt=receipt
    )

    if not success:
        return {
            'success': False,
            'error': 'Failed to redeem points'
        }

    result = {
        'success': True,
        'points_redeemed': points_to_redeem,
        'discount_amount': discount_amount,
        'remaining_balance': loyalty_account.current_balance,
        'loyalty_account': loyalty_account
    }

    # Send redemption email if configured
    if config.send_points_redeemed_email and receipt.customer.email:
        send_points_redeemed_email(receipt, result)

    logger.info(
        f"Applied loyalty discount to receipt {receipt.receipt_number}: "
        f"{points_to_redeem} points = ₦{discount_amount}"
    )

    return result


def send_loyalty_welcome_email(loyalty_account):
    """Send welcome email to new loyalty program member"""
    try:
        config = LoyaltyConfiguration.get_active_config()
        store_config = StoreConfiguration.get_active_config()

        if not config.send_welcome_email:
            return

        customer = loyalty_account.customer

        if not customer.email:
            return

        subject = f"🎉 Welcome to {config.program_name} - {store_config.store_name}"

        # Plain text message
        text_content = f"""
Welcome to {config.program_name}, {customer.name}!

{store_config.store_name}
{store_config.address_line_1}
{store_config.city}, {store_config.state}
Phone: {store_config.phone}
Email: {store_config.email}

You have been enrolled in our loyalty rewards program!

How it works:
- Earn points with every purchase
- Redeem points for discounts on future purchases
- Keep track of your points with every receipt

Point Earning Rules:
{get_earning_rules_text(config)}

Point Redemption:
- Minimum {config.minimum_points_for_redemption} points required to redeem
- Each point is worth ₦{config.points_to_currency_rate}

Start shopping to earn points today!

Thank you for being a valued customer.

---
{store_config.store_name}
{store_config.phone}
{store_config.email}
"""

        # Colorful HTML version
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); margin: 0; padding: 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 20px; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px 30px; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 32px; font-weight: 700; text-shadow: 0 2px 4px rgba(0,0,0,0.2); }}
        .header .emoji {{ font-size: 60px; margin-bottom: 15px; animation: bounce 2s infinite; }}
        @keyframes bounce {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-10px); }} }}
        .content {{ padding: 40px 30px; }}
        .welcome-box {{ background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 25px; border-radius: 15px; margin: 20px 0; text-align: center; box-shadow: 0 10px 25px rgba(240, 147, 251, 0.3); }}
        .welcome-box h2 {{ margin: 0 0 10px 0; font-size: 24px; }}
        .info-box {{ background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); padding: 20px; border-radius: 12px; margin: 20px 0; border-left: 5px solid #667eea; }}
        .info-box h3 {{ color: #667eea; margin-top: 0; font-size: 20px; }}
        .benefit-item {{ background: white; padding: 15px; margin: 10px 0; border-radius: 10px; border-left: 4px solid #4facfe; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        .benefit-item .icon {{ font-size: 24px; margin-right: 10px; }}
        .rules-box {{ background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%); padding: 20px; border-radius: 12px; margin: 20px 0; }}
        .rules-box h3 {{ color: #ff6b6b; margin-top: 0; }}
        .cta-button {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px 40px; border-radius: 30px; text-decoration: none; font-weight: bold; margin: 20px 0; box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3); transition: transform 0.3s; }}
        .cta-button:hover {{ transform: translateY(-3px); }}
        .footer {{ background: #f8f9fa; padding: 30px; text-align: center; color: #6c757d; border-top: 3px solid #667eea; }}
        .stats {{ display: flex; justify-content: space-around; margin: 20px 0; }}
        .stat-item {{ text-align: center; }}
        .stat-value {{ font-size: 32px; font-weight: bold; color: #667eea; }}
        .stat-label {{ font-size: 12px; color: #6c757d; text-transform: uppercase; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="emoji">🎉</div>
            <h1>Welcome to {config.program_name}!</h1>
            <p style="margin: 10px 0 0 0; font-size: 18px; opacity: 0.95;">Start earning rewards today</p>
        </div>

        <div class="content">
            <div class="welcome-box">
                <h2>Hi {customer.name}! 👋</h2>
                <p style="margin: 0; font-size: 16px;">You're now part of our exclusive loyalty rewards program!</p>
            </div>

            <div class="info-box">
                <h3>✨ How It Works</h3>
                <div class="benefit-item">
                    <span class="icon">🛍️</span>
                    <strong>Shop & Earn</strong> - Earn points with every purchase
                </div>
                <div class="benefit-item">
                    <span class="icon">🎁</span>
                    <strong>Redeem Rewards</strong> - Use points for discounts on future purchases
                </div>
                <div class="benefit-item">
                    <span class="icon">📊</span>
                    <strong>Track Points</strong> - See your points balance on every receipt
                </div>
            </div>

            <div class="rules-box">
                <h3>💎 Your Earning Rules</h3>
                <p style="margin: 10px 0; font-size: 16px; color: #333;">{get_earning_rules_text(config).replace(chr(10), '<br>')}</p>

                <div class="stats">
                    <div class="stat-item">
                        <div class="stat-value">{config.minimum_points_for_redemption}</div>
                        <div class="stat-label">Min Points to Redeem</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">₦{config.points_to_currency_rate}</div>
                        <div class="stat-label">Value Per Point</div>
                    </div>
                </div>
            </div>

            <div style="text-align: center; margin: 30px 0;">
                <p style="font-size: 18px; color: #333; margin-bottom: 20px;">Ready to start earning?</p>
                <a href="#" class="cta-button">🛒 Start Shopping Now</a>
            </div>
        </div>

        <div class="footer">
            <p style="margin: 0 0 10px 0; font-weight: bold; color: #333;">{store_config.store_name}</p>
            <p style="margin: 5px 0;">{store_config.address_line_1}<br>{store_config.city}, {store_config.state}</p>
            <p style="margin: 5px 0;">📞 {store_config.phone} | ✉️ {store_config.email}</p>
        </div>
    </div>
</body>
</html>
"""

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[customer.email]
        )
        msg.attach_alternative(html_content, "text/html")

        msg.send()
        logger.info(f"Sent welcome email to {customer.email}")

    except Exception as e:
        logger.error(f"Error sending welcome email: {e}")


def send_points_earned_email(receipt, points_info):
    """Send email notification with receipt and points earned"""
    try:
        config = LoyaltyConfiguration.get_active_config()
        store_config = StoreConfiguration.get_active_config()
        customer = receipt.customer
        loyalty_account = points_info['loyalty_account']

        if not customer.email:
            return

        subject = f"Receipt {receipt.receipt_number} - You earned {points_info['points_earned']} points!"

        # Get sales items
        sales_items = receipt.sales.all()

        # Plain text message
        text_content = f"""
{store_config.store_name}
{store_config.address_line_1}
{store_config.city}, {store_config.state}
Phone: {store_config.phone}
Email: {store_config.email}

=====================================
        RECEIPT
=====================================

Receipt #: {receipt.receipt_number}
Date: {receipt.date.strftime('%B %d, %Y %I:%M %p')}

Dear {customer.name},

Thank you for your purchase!

--- ITEMS PURCHASED ---
"""

        for sale in sales_items:
            text_content += f"\n{sale.product.brand} x{sale.quantity} - ₦{sale.total_price:.2f}"

        if receipt.delivery_cost > 0:
            text_content += f"\nDelivery Cost: ₦{receipt.delivery_cost:.2f}"

        text_content += f"""

-------------------------------------
Total: ₦{points_info['transaction_amount']:.2f}
=====================================

--- {config.program_name.upper()} ---
✨ Points Earned: {points_info['points_earned']} points
📊 Previous Balance: {points_info['previous_balance']} points
🎯 New Balance: {points_info['new_balance']} points
💰 Redeemable Value: ₦{loyalty_account.get_redeemable_value():.2f}

Keep shopping to earn more points!

Thank you for being a valued customer.

---
{store_config.store_name}
{store_config.phone}
{store_config.email}
{store_config.website if store_config.website else ''}
"""

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[customer.email]
        )

        msg.send()
        logger.info(f"Sent points earned email to {customer.email}")

    except Exception as e:
        logger.error(f"Error sending points earned email: {e}")


def send_points_redeemed_email(receipt, redemption_info):
    """Send email notification when points are redeemed"""
    try:
        config = LoyaltyConfiguration.get_active_config()
        store_config = StoreConfiguration.get_active_config()
        customer = receipt.customer
        loyalty_account = redemption_info['loyalty_account']

        if not customer.email:
            return

        subject = f"🎁 Points Redeemed - Receipt {receipt.receipt_number} - {store_config.store_name}"

        text_content = f"""
{store_config.store_name}
{store_config.address_line_1}
{store_config.city}, {store_config.state}
Phone: {store_config.phone}
Email: {store_config.email}

=====================================
   LOYALTY POINTS REDEEMED
=====================================

Dear {customer.name},

You have successfully redeemed your loyalty points!

Receipt: {receipt.receipt_number}
Date: {receipt.date.strftime('%B %d, %Y %I:%M %p')}

--- REDEMPTION DETAILS ---
🎁 Points Redeemed: {redemption_info['points_redeemed']} points
💵 Discount Applied: ₦{redemption_info['discount_amount']:.2f}

--- {config.program_name.upper()} BALANCE ---
📊 Remaining Points: {redemption_info['remaining_balance']} points
💰 Redeemable Value: ₦{loyalty_account.get_redeemable_value():.2f}

Thank you for being a loyal customer!

Keep shopping to earn more rewards!

---
{store_config.store_name}
{store_config.phone}
{store_config.email}
{store_config.website if store_config.website else ''}
"""

        # Colorful HTML version
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); margin: 0; padding: 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 20px; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }}
        .header {{ background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; padding: 40px 30px; text-align: center; position: relative; overflow: hidden; }}
        .header::before {{ content: ''; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%; background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%); animation: pulse 3s infinite; }}
        @keyframes pulse {{ 0%, 100% {{ transform: scale(1); }} 50% {{ transform: scale(1.1); }} }}
        .header h1 {{ margin: 0; font-size: 32px; font-weight: 700; text-shadow: 0 2px 4px rgba(0,0,0,0.2); position: relative; z-index: 1; }}
        .header .emoji {{ font-size: 70px; margin-bottom: 15px; animation: rotate 3s infinite; position: relative; z-index: 1; }}
        @keyframes rotate {{ 0%, 100% {{ transform: rotate(0deg); }} 25% {{ transform: rotate(-10deg); }} 75% {{ transform: rotate(10deg); }} }}
        .content {{ padding: 40px 30px; }}
        .success-banner {{ background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 30px; border-radius: 15px; margin: 20px 0; text-align: center; box-shadow: 0 15px 35px rgba(245, 87, 108, 0.4); }}
        .success-banner h2 {{ margin: 0 0 10px 0; font-size: 28px; }}
        .success-banner p {{ margin: 0; font-size: 16px; opacity: 0.95; }}
        .receipt-info {{ background: #f8f9fa; padding: 20px; border-radius: 12px; margin: 20px 0; border-left: 5px solid #38ef7d; }}
        .receipt-info p {{ margin: 8px 0; color: #6c757d; }}
        .receipt-info strong {{ color: #333; }}
        .redemption-box {{ background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%); padding: 25px; border-radius: 15px; margin: 20px 0; }}
        .redemption-box h3 {{ color: #ff6b6b; margin: 0 0 20px 0; font-size: 22px; text-align: center; }}
        .savings-card {{ background: white; padding: 20px; border-radius: 12px; text-align: center; margin: 15px 0; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
        .savings-amount {{ font-size: 48px; font-weight: bold; color: #f5576c; margin: 10px 0; text-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .savings-label {{ color: #6c757d; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; }}
        .balance-box {{ background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); padding: 25px; border-radius: 15px; margin: 20px 0; }}
        .balance-box h3 {{ color: #11998e; margin: 0 0 20px 0; font-size: 22px; text-align: center; }}
        .balance-stats {{ display: flex; justify-content: space-around; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 12px; text-align: center; flex: 1; margin: 0 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
        .stat-value {{ font-size: 36px; font-weight: bold; color: #11998e; margin: 5px 0; }}
        .stat-label {{ color: #6c757d; font-size: 12px; text-transform: uppercase; }}
        .cta-box {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 25px; border-radius: 15px; text-align: center; margin: 20px 0; }}
        .cta-box p {{ margin: 0 0 15px 0; font-size: 18px; }}
        .cta-button {{ display: inline-block; background: white; color: #667eea; padding: 15px 40px; border-radius: 30px; text-decoration: none; font-weight: bold; box-shadow: 0 10px 20px rgba(0,0,0,0.2); transition: transform 0.3s; }}
        .cta-button:hover {{ transform: translateY(-3px); }}
        .footer {{ background: #f8f9fa; padding: 30px; text-align: center; color: #6c757d; border-top: 3px solid #38ef7d; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="emoji">🎁</div>
            <h1>Points Redeemed Successfully!</h1>
            <p style="margin: 10px 0 0 0; font-size: 18px; opacity: 0.95;">Your savings have been applied</p>
        </div>

        <div class="content">
            <div class="success-banner">
                <h2>Congratulations, {customer.name}! 🎊</h2>
                <p>You've successfully redeemed your loyalty points and saved money on your purchase!</p>
            </div>

            <div class="receipt-info">
                <p><strong>Receipt:</strong> {receipt.receipt_number}</p>
                <p><strong>Date:</strong> {receipt.date.strftime('%B %d, %Y at %I:%M %p')}</p>
            </div>

            <div class="redemption-box">
                <h3>💰 Your Savings</h3>
                <div class="savings-card">
                    <div class="savings-label">🎁 Points Redeemed</div>
                    <div class="savings-amount" style="font-size: 42px; color: #ff6b6b;">{redemption_info['points_redeemed']}</div>
                    <div class="savings-label" style="margin-top: 10px;">Points Used</div>
                </div>
                <div class="savings-card">
                    <div class="savings-label">💵 Discount Applied</div>
                    <div class="savings-amount">₦{redemption_info['discount_amount']:.2f}</div>
                    <div class="savings-label" style="margin-top: 10px;">Total Savings</div>
                </div>
            </div>

            <div class="balance-box">
                <h3>📊 Your {config.program_name} Balance</h3>
                <div class="balance-stats">
                    <div class="stat-card">
                        <div class="stat-label">Remaining Points</div>
                        <div class="stat-value">{redemption_info['remaining_balance']}</div>
                        <div class="stat-label" style="margin-top: 5px;">points</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Redeemable Value</div>
                        <div class="stat-value">₦{loyalty_account.get_redeemable_value():.2f}</div>
                        <div class="stat-label" style="margin-top: 5px;">available</div>
                    </div>
                </div>
            </div>

            <div class="cta-box">
                <p>💚 Thank you for being a loyal customer!</p>
                <p style="margin-bottom: 20px; font-size: 16px; opacity: 0.9;">Keep shopping to earn more rewards and unlock bigger savings</p>
                <a href="#" class="cta-button">🛍️ Shop Again</a>
            </div>
        </div>

        <div class="footer">
            <p style="margin: 0 0 10px 0; font-weight: bold; color: #333;">{store_config.store_name}</p>
            <p style="margin: 5px 0;">{store_config.address_line_1}<br>{store_config.city}, {store_config.state}</p>
            <p style="margin: 5px 0;">📞 {store_config.phone} | ✉️ {store_config.email}</p>
            {f'<p style="margin: 5px 0;">🌐 {store_config.website}</p>' if store_config.website else ''}
        </div>
    </div>
</body>
</html>
"""

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[customer.email]
        )
        msg.attach_alternative(html_content, "text/html")

        msg.send()
        logger.info(f"Sent points redeemed email to {customer.email}")

    except Exception as e:
        logger.error(f"Error sending points redeemed email: {e}")


def get_earning_rules_text(config):
    """Generate human-readable text for point earning rules"""
    if config.calculation_type == 'per_transaction':
        return f"- Earn {config.points_per_transaction} point(s) per transaction"

    elif config.calculation_type == 'per_amount':
        return f"- Earn {config.points_per_currency_unit} point(s) for every ₦{config.currency_unit_value} spent"

    elif config.calculation_type == 'combined':
        return f"""- Earn {config.points_per_transaction} point(s) per transaction
- PLUS {config.points_per_currency_unit} point(s) for every ₦{config.currency_unit_value} spent"""

    return "Contact us for point earning details"


def get_customer_loyalty_summary(customer):
    """
    Get a summary of customer's loyalty status

    Args:
        customer: Customer instance

    Returns:
        dict with loyalty information
    """
    try:
        loyalty_account = customer.loyalty_account
        config = LoyaltyConfiguration.get_active_config()

        return {
            'has_account': True,
            'is_active': loyalty_account.is_active,
            'current_balance': loyalty_account.current_balance,
            'total_earned': loyalty_account.total_points_earned,
            'total_redeemed': loyalty_account.total_points_redeemed,
            'redeemable_value': loyalty_account.get_redeemable_value(),
            'can_redeem': loyalty_account.current_balance >= config.minimum_points_for_redemption,
            'tier': loyalty_account.tier,
            'enrollment_date': loyalty_account.enrollment_date,
            'last_transaction': loyalty_account.last_transaction_date,
        }
    except CustomerLoyaltyAccount.DoesNotExist:
        return {
            'has_account': False,
            'is_active': False,
            'current_balance': 0,
        }
