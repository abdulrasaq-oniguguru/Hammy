"""
POS System Core Tests
=====================
Covers:
  - Product markup / selling-price calculation
  - Duplicate barcode prevention (DB constraint)
  - Tax: inclusive vs exclusive, percentage vs fixed
  - Receipt tax-breakdown helpers
  - Payment splitting across multiple methods
  - Partial-payment deposit / balance-remaining tracking
  - Returns and store-credit lifecycle
  - Loyalty points (per-transaction, per-amount, combined)
  - Loyalty count-based discounts (transaction-count & item-count)
  - Loyalty point redemption against a receipt
  - Sale line-level discount
  - User access levels
  - Printer configuration & task-mapping resolution
  - PrinterManager barcode & receipt print-job lifecycle
  - Barcode print views: printer resolution order, exact copy counts, partial failures
  - Receipt print view: task-mapping vs OS-default routing

Run:
    cd mystore
    python manage.py test store.tests
"""

from decimal import Decimal
import json
from unittest.mock import patch, MagicMock, ANY

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase, RequestFactory
from django.urls import reverse

from store.models import (
    Customer,
    CustomerLoyaltyAccount,
    LoyaltyConfiguration,
    LoyaltyTransaction,
    PartialPayment,
    Payment,
    PaymentMethod,
    PrinterConfiguration,
    PrintJob,
    PrinterTaskMapping,
    Product,
    Receipt,
    Return,
    ReturnItem,
    Sale,
    StoreCredit,
    StoreCreditUsage,
    TaxConfiguration,
    UserProfile,
)
from store.loyalty_utils import (
    apply_count_based_discount,
    apply_loyalty_discount,
    process_sale_loyalty_points,
)
from store.printing import PrinterManager


# ===========================================================================
# Shared factory helpers
# ===========================================================================

def make_user(username='cashier'):
    return User.objects.create_user(username, password='testpass123')


def make_customer(name='Test Customer'):
    return Customer.objects.create(name=name, phone_number='08012345678')


def make_product(brand='Test Shoe', price=10000, markup_type='percentage',
                 markup=10, barcode=None, quantity=20):
    """Create a Product suppressing barcode image generation (PIL/filesystem)."""
    with patch.object(Product, 'generate_barcode'):
        return Product.objects.create(
            brand=brand,
            price=Decimal(str(price)),
            markup_type=markup_type,
            markup=Decimal(str(markup)),
            size='M', category='shoes', shop='STORE',
            barcode_number=barcode,
            quantity=quantity,
        )


def make_receipt(user=None, customer=None, total=Decimal('10000.00')):
    """Create a saved Receipt with a manually-set total (bypasses sale chain)."""
    r = Receipt.objects.create(user=user, customer=customer)
    Receipt.objects.filter(pk=r.pk).update(total_with_delivery=total)
    r.refresh_from_db()
    return r


def make_payment(total):
    """Create a Payment with a manually-set total_amount (bypasses sale chain)."""
    p = Payment.objects.create()
    Payment.objects.filter(pk=p.pk).update(total_amount=Decimal(str(total)))
    p.refresh_from_db()
    return p


def make_loyalty_config(**overrides):
    """Active LoyaltyConfiguration with all email notifications off."""
    defaults = dict(
        program_name='Test Loyalty',
        is_active=True,
        calculation_type='per_amount',
        points_per_transaction=1,
        points_per_currency_unit=Decimal('1'),
        currency_unit_value=Decimal('100'),
        points_to_currency_rate=Decimal('1'),
        minimum_points_for_redemption=100,
        maximum_discount_percentage=Decimal('50'),
        send_welcome_email=False,
        send_points_earned_email=False,
        send_points_redeemed_email=False,
    )
    defaults.update(overrides)
    return LoyaltyConfiguration.objects.create(**defaults)


# ===========================================================================
# 1. Product – Markup & Selling Price
# ===========================================================================

class ProductCalculationTests(TestCase):

    def test_percentage_markup(self):
        p = Product(price=Decimal('10000'), markup_type='percentage', markup=Decimal('10'))
        self.assertEqual(p.calculate_selling_price(), Decimal('11000.0'))

    def test_fixed_markup(self):
        p = Product(price=Decimal('10000'), markup_type='fixed', markup=Decimal('1500'))
        self.assertEqual(p.calculate_selling_price(), Decimal('11500'))

    def test_zero_markup_returns_cost(self):
        p = Product(price=Decimal('5000'), markup_type='percentage', markup=Decimal('0'))
        self.assertEqual(p.calculate_selling_price(), Decimal('5000'))

    def test_product_save_auto_calculates_selling_price(self):
        """Product.save() sets selling_price via calculate_selling_price."""
        p = make_product(price=8000, markup_type='percentage', markup=25)
        p.refresh_from_db()
        self.assertEqual(p.selling_price, Decimal('10000.00'))

    @patch.object(Product, 'generate_barcode')
    def test_duplicate_barcode_raises_integrity_error(self, _):
        barcode = '2000000000017'
        make_product(brand='Shoe A', barcode=barcode)
        with self.assertRaises(IntegrityError):
            make_product(brand='Shoe B', barcode=barcode)

    @patch.object(Product, 'generate_barcode')
    def test_different_barcodes_both_created(self, _):
        make_product(brand='A', barcode='2000000000017')
        make_product(brand='B', barcode='2000000000024')
        self.assertEqual(Product.objects.count(), 2)


# ===========================================================================
# 2. Tax Configuration – Inclusive vs Exclusive
# ===========================================================================

class TaxCalculationTests(TestCase):

    def _tax(self, method='exclusive', rate='7.5', tax_type='percentage', code='VAT'):
        # created_by is null=True, blank=True — skip to avoid username collisions
        return TaxConfiguration.objects.create(
            name=f'Tax {code}', code=code,
            tax_type=tax_type, rate=Decimal(rate),
            calculation_method=method, is_active=True,
        )

    # ---- Exclusive (tax added on top) ------------------------------------

    def test_exclusive_percentage_tax_amount(self):
        # 10000 * 7.5% = 750
        tax = self._tax(method='exclusive', rate='7.5')
        self.assertEqual(tax.calculate_tax_amount(Decimal('10000')), Decimal('750.00'))

    def test_exclusive_total_adds_tax(self):
        tax = self._tax(method='exclusive', rate='7.5')
        total, tax_amt = tax.calculate_total_with_tax(Decimal('10000'))
        self.assertEqual(total, Decimal('10750.00'))
        self.assertEqual(tax_amt, Decimal('750.00'))

    def test_exclusive_10pct(self):
        tax = self._tax(method='exclusive', rate='10', code='VAT2')
        self.assertEqual(tax.calculate_tax_amount(Decimal('5000')), Decimal('500.00'))

    # ---- Inclusive (tax already inside the price) -------------------------

    def test_inclusive_extracts_tax_correctly(self):
        # 10750 includes 7.5% VAT: tax = 10750 - (10750 / 1.075) = 750
        tax = self._tax(method='inclusive', rate='7.5')
        self.assertEqual(tax.calculate_tax_amount(Decimal('10750')), Decimal('750.00'))

    def test_inclusive_total_unchanged(self):
        """Inclusive tax must NOT add any extra to the grand total."""
        tax = self._tax(method='inclusive', rate='7.5')
        total, tax_amt = tax.calculate_total_with_tax(Decimal('10750'))
        self.assertEqual(total, Decimal('10750.00'))
        self.assertEqual(tax_amt, Decimal('750.00'))

    def test_inclusive_vs_exclusive_invariant(self):
        """Inclusive keeps base total; exclusive increases it."""
        tax_i = self._tax(method='inclusive', rate='7.5', code='INCI')
        tax_e = self._tax(method='exclusive', rate='7.5', code='EXCI')
        base = Decimal('10000')
        total_i, _ = tax_i.calculate_total_with_tax(base)
        total_e, _ = tax_e.calculate_total_with_tax(base)
        self.assertEqual(total_i, base)
        self.assertGreater(total_e, base)

    # ---- Fixed-amount tax ------------------------------------------------

    def test_fixed_exclusive_tax_amount(self):
        tax = self._tax(method='exclusive', rate='200', tax_type='fixed', code='FEE')
        self.assertEqual(tax.calculate_tax_amount(Decimal('5000')), Decimal('200.00'))

    def test_fixed_inclusive_total_unchanged(self):
        tax = self._tax(method='inclusive', rate='200', tax_type='fixed', code='FEEI')
        total, _ = tax.calculate_total_with_tax(Decimal('5000'))
        self.assertEqual(total, Decimal('5000.00'))

    # ---- Receipt tax-breakdown helpers -----------------------------------

    def test_receipt_inclusive_tax_total(self):
        details = json.dumps({
            'VAT': {'rate': 7.5, 'amount': 750, 'method': 'inclusive'},
            'ST':  {'rate': 2.0, 'amount': 200, 'method': 'exclusive'},
        })
        r = Receipt(tax_details=details)
        self.assertEqual(r.get_inclusive_tax_total(), Decimal('750'))

    def test_receipt_exclusive_tax_total(self):
        details = json.dumps({
            'VAT': {'rate': 7.5, 'amount': 750, 'method': 'inclusive'},
            'ST':  {'rate': 2.0, 'amount': 200, 'method': 'exclusive'},
        })
        r = Receipt(tax_details=details)
        self.assertEqual(r.get_exclusive_tax_total(), Decimal('200'))

    def test_receipt_amount_before_exclusive_tax(self):
        details = json.dumps({'VAT': {'rate': 10, 'amount': 1000, 'method': 'exclusive'}})
        r = Receipt(tax_details=details, total_with_delivery=Decimal('11000'))
        self.assertEqual(r.get_amount_before_tax(), Decimal('10000'))

    def test_receipt_empty_tax_details_returns_zeros(self):
        r = Receipt(tax_details='{}')
        self.assertEqual(r.get_inclusive_tax_total(), Decimal('0'))
        self.assertEqual(r.get_exclusive_tax_total(), Decimal('0'))


# ===========================================================================
# 3. Payment Splitting
# ===========================================================================

class PaymentSplitTests(TestCase):
    """
    Payment.save() always recalculates total_amount from linked Sales.
    In unit tests there are no Sales, so we patch calculate_total to
    return a fixed total for the duration of each test.
    """

    def _payment_ctx(self, total):
        """Context manager that patches Payment.calculate_total → fixed total."""
        return patch.object(Payment, 'calculate_total', return_value=Decimal(str(total)))

    def test_single_full_cash_payment_completes(self):
        with self._payment_ctx(10000):
            payment = Payment.objects.create()
            PaymentMethod.objects.create(
                payment=payment, payment_method='cash',
                amount=Decimal('10000'), status='completed',
            )
        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, 'completed')
        self.assertEqual(payment.balance_due, Decimal('0'))

    def test_cash_plus_card_split_sums_correctly(self):
        with self._payment_ctx(10000):
            payment = Payment.objects.create()
            for method, amt in [('cash', '6000'), ('card', '4000')]:
                PaymentMethod.objects.create(
                    payment=payment, payment_method=method,
                    amount=Decimal(amt), status='completed',
                )
        payment.refresh_from_db()
        self.assertEqual(payment.total_paid, Decimal('10000'))
        self.assertEqual(payment.balance_due, Decimal('0'))
        self.assertEqual(payment.payment_status, 'completed')

    def test_partial_payment_leaves_balance_and_status_partial(self):
        with self._payment_ctx(10000):
            payment = Payment.objects.create()
            PaymentMethod.objects.create(
                payment=payment, payment_method='cash',
                amount=Decimal('4000'), status='completed',
            )
        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, 'partial')
        self.assertEqual(payment.balance_due, Decimal('6000'))

    def test_pending_method_not_counted_as_paid(self):
        """Unconfirmed transfer must not affect total_paid."""
        with self._payment_ctx(10000):
            payment = Payment.objects.create()
            PaymentMethod.objects.create(
                payment=payment, payment_method='transfer_sterling',
                amount=Decimal('10000'), status='pending',
            )
        payment.refresh_from_db()
        self.assertEqual(payment.total_paid, Decimal('0'))
        self.assertEqual(payment.payment_status, 'pending')

    def test_three_way_split_cash_transfer_store_credit(self):
        with self._payment_ctx(12000):
            payment = Payment.objects.create()
            for method, amt in [
                ('cash', '5000'), ('transfer_taj', '4000'), ('store_credit', '3000')
            ]:
                PaymentMethod.objects.create(
                    payment=payment, payment_method=method,
                    amount=Decimal(amt), status='completed',
                )
        payment.refresh_from_db()
        self.assertEqual(payment.total_paid, Decimal('12000'))
        self.assertEqual(payment.payment_status, 'completed')

    def test_balance_due_equals_total_minus_paid(self):
        with self._payment_ctx(9000):
            payment = Payment.objects.create()
            PaymentMethod.objects.create(
                payment=payment, payment_method='cash',
                amount=Decimal('3500'), status='completed',
            )
        payment.refresh_from_db()
        self.assertEqual(payment.balance_due, Decimal('5500'))

    def test_no_methods_payment_stays_pending(self):
        with self._payment_ctx(5000):
            payment = Payment.objects.create()
        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, 'pending')
        self.assertEqual(payment.total_paid, Decimal('0'))


# ===========================================================================
# 4. Partial-Payment / Deposit-Balance Tracking
# ===========================================================================

class DepositBalanceTests(TestCase):

    def setUp(self):
        self.user = make_user()

    def test_balance_remaining_equals_total_minus_paid(self):
        total, paid = Decimal('15000'), Decimal('6000')
        receipt = make_receipt(user=self.user, total=total)
        Receipt.objects.filter(pk=receipt.pk).update(
            amount_paid=paid,
            balance_remaining=total - paid,
            payment_status='partial',
        )
        receipt.refresh_from_db()
        self.assertEqual(receipt.balance_remaining, Decimal('9000'))

    def test_full_payment_clears_balance(self):
        total = Decimal('20000')
        receipt = make_receipt(user=self.user, total=total)
        Receipt.objects.filter(pk=receipt.pk).update(
            amount_paid=total,
            balance_remaining=Decimal('0'),
            payment_status='paid',
        )
        receipt.refresh_from_db()
        self.assertEqual(receipt.balance_remaining, Decimal('0'))
        self.assertEqual(receipt.payment_status, 'paid')

    def test_partial_status_set_correctly(self):
        receipt = make_receipt(user=self.user, total=Decimal('10000'))
        Receipt.objects.filter(pk=receipt.pk).update(
            amount_paid=Decimal('3000'),
            balance_remaining=Decimal('7000'),
            payment_status='partial',
        )
        receipt.refresh_from_db()
        self.assertEqual(receipt.payment_status, 'partial')

    def test_three_installments_sum_to_total(self):
        receipt = make_receipt(user=self.user, total=Decimal('9000'))
        for amt in [Decimal('3000'), Decimal('3000'), Decimal('3000')]:
            PartialPayment.objects.create(
                receipt=receipt, amount=amt,
                payment_method='cash', received_by=self.user,
            )
        total_paid = sum(
            pp.amount for pp in PartialPayment.objects.filter(receipt=receipt)
        )
        self.assertEqual(total_paid, Decimal('9000'))

    def test_receipt_number_auto_generated(self):
        r = Receipt.objects.create(user=self.user)
        self.assertTrue(r.receipt_number.startswith('RCPT'))

    def test_two_receipts_get_unique_numbers(self):
        r1 = Receipt.objects.create(user=self.user)
        r2 = Receipt.objects.create(user=self.user)
        self.assertNotEqual(r1.receipt_number, r2.receipt_number)


# ===========================================================================
# 5. Returns & Store Credit
# ===========================================================================

class ReturnStoreCreditTests(TestCase):

    def setUp(self):
        self.user = make_user()
        self.customer = make_customer()
        self.receipt = make_receipt(user=self.user, total=Decimal('10000'))

    def _sc(self, amount):
        return StoreCredit.objects.create(
            customer=self.customer,
            original_amount=Decimal(str(amount)),
            remaining_balance=Decimal(str(amount)),
            is_active=True, issued_by=self.user,
        )

    # ---- Store-credit balance lifecycle ----------------------------------

    def test_initial_credit_is_active_with_full_balance(self):
        sc = self._sc(5000)
        self.assertEqual(sc.remaining_balance, Decimal('5000'))
        self.assertTrue(sc.is_active)

    def test_partial_use_deducts_balance(self):
        r2 = make_receipt(user=self.user, total=Decimal('2000'))
        sc = self._sc(5000)
        StoreCreditUsage.objects.create(
            store_credit=sc, receipt=r2,
            amount_used=Decimal('2000'), used_by=self.user,
        )
        sc.refresh_from_db()
        self.assertEqual(sc.remaining_balance, Decimal('3000'))
        self.assertTrue(sc.is_active)

    def test_full_use_sets_balance_zero_and_deactivates(self):
        r2 = make_receipt(user=self.user, total=Decimal('5000'))
        sc = self._sc(5000)
        StoreCreditUsage.objects.create(
            store_credit=sc, receipt=r2,
            amount_used=Decimal('5000'), used_by=self.user,
        )
        sc.refresh_from_db()
        self.assertFalse(sc.is_active)
        self.assertEqual(sc.remaining_balance, Decimal('0'))

    def test_credit_number_has_sc_prefix(self):
        sc = self._sc(2000)
        self.assertTrue(sc.credit_number.startswith('SC'))

    def test_two_credits_get_unique_numbers(self):
        sc1 = self._sc(1000)
        sc2 = self._sc(2000)
        self.assertNotEqual(sc1.credit_number, sc2.credit_number)

    # ---- Return refund amounts -------------------------------------------

    def test_return_refund_amount_without_restocking_fee(self):
        ret = Return.objects.create(
            receipt=self.receipt, customer=self.customer,
            subtotal=Decimal('3000'), refund_amount=Decimal('3000'),
            refund_type='store_credit', status='approved',
            processed_by=self.user,
        )
        self.assertEqual(ret.refund_amount, Decimal('3000'))

    def test_return_refund_reduced_by_restocking_fee(self):
        ret = Return.objects.create(
            receipt=self.receipt, customer=self.customer,
            subtotal=Decimal('3000'), restocking_fee=Decimal('300'),
            refund_amount=Decimal('2700'),  # subtotal - fee
            refund_type='store_credit', status='approved',
            processed_by=self.user,
        )
        self.assertEqual(ret.refund_amount, ret.subtotal - ret.restocking_fee)

    def test_return_number_auto_generated(self):
        ret = Return.objects.create(
            receipt=self.receipt, processed_by=self.user,
            refund_amount=Decimal('1000'), status='pending',
        )
        self.assertTrue(ret.return_number.startswith('RET'))

    def test_cash_refund_type_stored(self):
        ret = Return.objects.create(
            receipt=self.receipt, processed_by=self.user,
            refund_amount=Decimal('2000'), refund_type='cash', status='approved',
        )
        self.assertEqual(ret.refund_type, 'cash')


# ===========================================================================
# 6. Loyalty Program – Points Earning & Balance
# ===========================================================================

class LoyaltyPointsTests(TestCase):

    def setUp(self):
        self.user = make_user()
        self.customer = make_customer()
        self.config = make_loyalty_config(
            calculation_type='per_amount',
            points_per_currency_unit=Decimal('1'),
            currency_unit_value=Decimal('100'),
        )
        self.account = CustomerLoyaltyAccount.objects.create(
            customer=self.customer, is_active=True,
        )

    # ---- Points calculation methods --------------------------------------

    def test_per_amount_500_naira_gives_5_pts(self):
        # 500 / 100 * 1 = 5 pts
        self.assertEqual(self.config.calculate_points_earned(Decimal('500')), 5)

    def test_per_amount_below_unit_threshold_gives_zero(self):
        # 99 < 100 threshold → 0 pts
        self.assertEqual(self.config.calculate_points_earned(Decimal('99')), 0)

    def test_per_transaction_ignores_amount(self):
        self.config.calculation_type = 'per_transaction'
        self.config.points_per_transaction = 10
        self.config.save()
        self.assertEqual(self.config.calculate_points_earned(Decimal('99999')), 10)

    def test_combined_sums_flat_and_per_amount(self):
        # flat 5 + (1000 / 100 * 1 = 10) = 15
        self.config.calculation_type = 'combined'
        self.config.points_per_transaction = 5
        self.config.save()
        self.assertEqual(self.config.calculate_points_earned(Decimal('1000')), 15)

    def test_zero_amount_earns_zero_points(self):
        self.assertEqual(self.config.calculate_points_earned(Decimal('0')), 0)

    # ---- Account add / redeem -------------------------------------------

    def test_add_points_increases_balance_and_lifetime_total(self):
        self.account.add_points(50, 'purchase')
        self.account.refresh_from_db()
        self.assertEqual(self.account.current_balance, 50)
        self.assertEqual(self.account.total_points_earned, 50)

    def test_redeem_points_decreases_balance_and_records_redeemed(self):
        self.account.add_points(200, 'purchase')
        success = self.account.redeem_points(150, 'discount')
        self.assertTrue(success)
        self.account.refresh_from_db()
        self.assertEqual(self.account.current_balance, 50)
        self.assertEqual(self.account.total_points_redeemed, 150)

    def test_cannot_redeem_more_than_balance(self):
        self.account.add_points(50, 'test')
        result = self.account.redeem_points(200, 'overdraft')
        self.assertFalse(result)
        self.account.refresh_from_db()
        self.assertEqual(self.account.current_balance, 50)  # unchanged

    def test_cannot_redeem_below_minimum_threshold(self):
        # Min is 100; 99 pts should be ineligible
        self.account.add_points(99, 'test')
        self.account.refresh_from_db()
        self.assertFalse(self.account.can_redeem_points(99))

    def test_can_redeem_at_exact_minimum(self):
        self.account.add_points(100, 'test')
        self.account.refresh_from_db()
        self.assertTrue(self.account.can_redeem_points(100))

    def test_redeemable_value_100pts_equals_100_naira(self):
        # 100 pts * rate 1 = 100
        self.account.add_points(100, 'test')
        self.assertEqual(self.account.get_redeemable_value(), Decimal('100.00'))

    # ---- Loyalty transaction records ------------------------------------

    def test_earn_creates_transaction_record(self):
        self.account.add_points(50, 'receipt')
        count = LoyaltyTransaction.objects.filter(
            loyalty_account=self.account, transaction_type='earned'
        ).count()
        self.assertEqual(count, 1)

    def test_redeem_creates_transaction_record(self):
        self.account.add_points(200, 'purchase')
        self.account.redeem_points(150, 'discount')
        count = LoyaltyTransaction.objects.filter(
            loyalty_account=self.account, transaction_type='redeemed'
        ).count()
        self.assertEqual(count, 1)

    # ---- process_sale_loyalty_points integration ------------------------

    def test_process_sale_awards_correct_points(self):
        # 500 / 100 * 1 = 5 pts
        receipt = make_receipt(user=self.user, customer=self.customer, total=Decimal('500'))
        result = process_sale_loyalty_points(receipt)
        self.assertIsNotNone(result)
        self.assertEqual(result['points_earned'], 5)
        self.account.refresh_from_db()
        self.assertEqual(self.account.current_balance, 5)

    def test_process_sale_no_customer_returns_none(self):
        receipt = make_receipt(user=self.user, total=Decimal('500'))  # no customer
        result = process_sale_loyalty_points(receipt)
        self.assertIsNone(result)

    def test_process_sale_inactive_account_returns_none(self):
        self.account.is_active = False
        self.account.save()
        receipt = make_receipt(user=self.user, customer=self.customer, total=Decimal('500'))
        result = process_sale_loyalty_points(receipt)
        self.assertIsNone(result)


# ===========================================================================
# 7. Loyalty – Count-Based Discounts
# ===========================================================================

class LoyaltyCountDiscountTests(TestCase):

    def setUp(self):
        self.user = make_user()
        self.customer = make_customer()

    def _txn_config(self, required=5, pct=10):
        return make_loyalty_config(
            calculation_type='transaction_count_discount',
            required_transaction_count=required,
            transaction_discount_percentage=Decimal(str(pct)),
        )

    def _item_config(self, required=10, pct=5):
        return make_loyalty_config(
            calculation_type='item_count_discount',
            required_item_count=required,
            item_discount_percentage=Decimal(str(pct)),
        )

    def _account(self):
        return CustomerLoyaltyAccount.objects.create(
            customer=self.customer, is_active=True,
        )

    # ---- Transaction-count discount -------------------------------------

    def test_below_transaction_threshold_returns_none(self):
        self._txn_config(required=5)
        acct = self._account()
        payment = make_payment(10000)
        acct.transaction_count = 4
        acct.save()
        result = apply_count_based_discount(payment, self.customer)
        self.assertIsNone(result)

    def test_at_transaction_threshold_discount_type_correct(self):
        self._txn_config(required=3, pct=10)
        acct = self._account()
        payment = make_payment(10000)
        acct.transaction_count = 3
        acct.discount_eligible = True
        acct.save()
        result = apply_count_based_discount(payment, self.customer)
        self.assertIsNotNone(result)
        self.assertEqual(result['discount_type'], 'transaction_count')

    def test_transaction_count_resets_to_zero_after_discount(self):
        self._txn_config(required=3)
        acct = self._account()
        payment = make_payment(10000)
        acct.transaction_count = 3
        acct.discount_eligible = True
        acct.save()
        apply_count_based_discount(payment, self.customer)
        acct.refresh_from_db()
        self.assertEqual(acct.transaction_count, 0)
        self.assertFalse(acct.discount_eligible)

    def test_discount_count_increments_after_use(self):
        self._txn_config(required=3)
        acct = self._account()
        payment = make_payment(10000)
        acct.transaction_count = 3
        acct.discount_eligible = True
        acct.save()
        apply_count_based_discount(payment, self.customer)
        acct.refresh_from_db()
        self.assertEqual(acct.discount_count, 1)

    # ---- Item-count discount --------------------------------------------

    def test_at_item_threshold_discount_applied(self):
        self._item_config(required=10, pct=5)
        acct = self._account()
        payment = make_payment(10000)
        acct.item_count = 10
        acct.save()
        result = apply_count_based_discount(payment, self.customer)
        self.assertIsNotNone(result)
        self.assertEqual(result['discount_type'], 'item_count')

    def test_item_count_remainder_kept_after_discount(self):
        # 15 items, threshold 10 → 1x discount, 5 items remaining
        self._item_config(required=10, pct=5)
        acct = self._account()
        payment = make_payment(10000)
        acct.item_count = 15
        acct.save()
        apply_count_based_discount(payment, self.customer)
        acct.refresh_from_db()
        self.assertEqual(acct.item_count, 5)

    def test_below_item_threshold_returns_none(self):
        self._item_config(required=10)
        acct = self._account()
        payment = make_payment(10000)
        acct.item_count = 9
        acct.save()
        result = apply_count_based_discount(payment, self.customer)
        self.assertIsNone(result)


# ===========================================================================
# 8. Loyalty – Points Redemption Against a Receipt
# ===========================================================================

class LoyaltyRedemptionTests(TestCase):

    def setUp(self):
        self.user = make_user()
        self.customer = make_customer()
        self.config = make_loyalty_config(
            points_to_currency_rate=Decimal('1'),
            minimum_points_for_redemption=100,
            maximum_discount_percentage=Decimal('50'),
        )
        self.account = CustomerLoyaltyAccount.objects.create(
            customer=self.customer, is_active=True,
        )
        self.account.add_points(500, 'initial load')

        # Receipt worth 2000; max 50% discount = 1000
        self.receipt = Receipt.objects.create(user=self.user, customer=self.customer)
        Receipt.objects.filter(pk=self.receipt.pk).update(
            total_with_delivery=Decimal('2000')
        )
        self.receipt.refresh_from_db()

    def test_successful_redemption_succeeds_and_deducts_balance(self):
        result = apply_loyalty_discount(self.receipt, 200)
        self.assertTrue(result['success'])
        self.account.refresh_from_db()
        self.assertEqual(self.account.current_balance, 300)

    def test_redemption_discount_amount_matches_points_rate(self):
        # 200 pts * rate 1 = 200 naira
        result = apply_loyalty_discount(self.receipt, 200)
        self.assertEqual(result['discount_amount'], Decimal('200'))

    def test_remaining_balance_in_result_is_correct(self):
        result = apply_loyalty_discount(self.receipt, 200)
        self.assertEqual(result['remaining_balance'], 300)

    def test_below_minimum_threshold_rejected(self):
        # Min 100; requesting 50 → rejected
        result = apply_loyalty_discount(self.receipt, 50)
        self.assertFalse(result['success'])

    def test_exceeding_max_discount_percentage_rejected(self):
        # Max 50% of 2000 = 1000. 1100 pts = 1100 > 1000 → rejected
        self.account.add_points(600, 'top-up')  # now 1100
        result = apply_loyalty_discount(self.receipt, 1100)
        self.assertFalse(result['success'])

    def test_redeeming_more_than_balance_rejected(self):
        # Account has 500; requesting 600 → rejected
        result = apply_loyalty_discount(self.receipt, 600)
        self.assertFalse(result['success'])

    def test_receipt_without_customer_rejected(self):
        r = make_receipt(user=self.user, total=Decimal('2000'))  # no customer
        result = apply_loyalty_discount(r, 200)
        self.assertFalse(result['success'])

    def test_customer_without_loyalty_account_rejected(self):
        other_customer = make_customer('No Account')
        r = Receipt.objects.create(user=self.user, customer=other_customer)
        Receipt.objects.filter(pk=r.pk).update(total_with_delivery=Decimal('2000'))
        r.refresh_from_db()
        result = apply_loyalty_discount(r, 200)
        self.assertFalse(result['success'])


# ===========================================================================
# 9. Sale – Line-Level Pricing & Discount
# ===========================================================================

class SaleLineTests(TestCase):

    def setUp(self):
        # 10000 cost + 10% = 11000 selling price
        self.product = make_product(price=10000, markup_type='percentage', markup=10)
        self.product.refresh_from_db()

    def test_total_no_discount(self):
        sale = Sale(product=self.product, quantity=2)
        self.assertEqual(sale.calculate_total(), Decimal('22000'))

    def test_discount_applied_once_not_per_item(self):
        """Line discount is NOT multiplied by quantity."""
        sale = Sale(product=self.product, quantity=3, discount_amount=Decimal('500'))
        # 11000 * 3 - 500 = 32500
        self.assertEqual(sale.calculate_total(), Decimal('32500'))

    def test_single_item_no_discount(self):
        sale = Sale(product=self.product, quantity=1, discount_amount=Decimal('0'))
        self.assertEqual(sale.calculate_total(), Decimal('11000'))

    def test_full_discount_gives_zero(self):
        sale = Sale(product=self.product, quantity=1, discount_amount=Decimal('11000'))
        self.assertEqual(sale.calculate_total(), Decimal('0'))

    def test_higher_qty_higher_total(self):
        s1 = Sale(product=self.product, quantity=1)
        s2 = Sale(product=self.product, quantity=5)
        self.assertLess(s1.calculate_total(), s2.calculate_total())


# ===========================================================================
# 10. User Access Levels
# ===========================================================================

class UserAccessLevelTests(TestCase):

    def test_default_access_level_is_cashier(self):
        user = User.objects.create_user('newstaff', password='pass')
        profile = UserProfile.objects.create(user=user)
        self.assertEqual(profile.access_level, 'cashier')

    def test_md_access_level_display(self):
        user = User.objects.create_user('director', password='pass')
        profile = UserProfile.objects.create(user=user, access_level='md')
        self.assertEqual(profile.get_access_level_display(), 'Managing Director')

    def test_accountant_access_level_display(self):
        user = User.objects.create_user('finance', password='pass')
        profile = UserProfile.objects.create(user=user, access_level='accountant')
        self.assertEqual(profile.get_access_level_display(), 'Accountant')

    def test_cashier_display_name(self):
        user = User.objects.create_user('cashier2', password='pass')
        profile = UserProfile.objects.create(user=user, access_level='cashier')
        self.assertEqual(profile.get_access_level_display(), 'Cashier')

    def test_two_users_have_independent_roles(self):
        u1 = User.objects.create_user('u1', password='pass')
        u2 = User.objects.create_user('u2', password='pass')
        UserProfile.objects.create(user=u1, access_level='md')
        UserProfile.objects.create(user=u2, access_level='cashier')

        self.assertNotEqual(
            UserProfile.objects.get(user=u1).access_level,
            UserProfile.objects.get(user=u2).access_level,
        )


# ===========================================================================
# 10b. MD-Only View Permission Tests
# ===========================================================================

class MdOnlyViewPermissionTests(TestCase):
    """
    is_md() checks user.is_staff. Confirms MD-only views redirect cashiers
    to access_denied and allow staff (MD) users through.
    """

    def setUp(self):
        self.md_user = User.objects.create_user(
            'md_view_user', password='pass', is_staff=True)
        UserProfile.objects.create(user=self.md_user, access_level='md')

        self.cashier_user = User.objects.create_user(
            'cashier_view_user', password='pass', is_staff=False)
        UserProfile.objects.create(user=self.cashier_user, access_level='cashier')

        self.access_denied_url = reverse('access_denied')

    def _assert_cashier_redirected(self, url_name):
        self.client.force_login(self.cashier_user)
        response = self.client.get(reverse(url_name))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/access-denied/', response.url)

    def _assert_md_not_redirected(self, url_name):
        self.client.force_login(self.md_user)
        response = self.client.get(reverse(url_name))
        self.assertNotEqual(response.status_code, 302)

    def test_financial_report_rejects_cashier(self):
        self._assert_cashier_redirected('financial_report')

    def test_discount_report_rejects_cashier(self):
        self._assert_cashier_redirected('discount_report')

    def test_delivery_report_rejects_cashier(self):
        self._assert_cashier_redirected('delivery_report')

    def test_financial_report_allows_md(self):
        self._assert_md_not_redirected('financial_report')

    def test_discount_report_allows_md(self):
        self._assert_md_not_redirected('discount_report')

    def test_delivery_report_allows_md(self):
        self._assert_md_not_redirected('delivery_report')

    def test_unauthenticated_user_cannot_reach_financial_report(self):
        """Anonymous user is redirected (to login, not past the guard)."""
        response = self.client.get(reverse('financial_report'))
        self.assertEqual(response.status_code, 302)


# ===========================================================================
# 11. Sale Chain – Receipt Total Recalculation (integration)
# ===========================================================================

class SaleChainTests(TestCase):
    """
    Sale.save() triggers Receipt.calculate_total() which re-sums linked
    sales and updates receipt.total_with_delivery.  No mocking needed here
    because we WANT to exercise the real save chain.
    """

    def setUp(self):
        self.user = make_user()
        # price=5000, 20% markup → selling_price = 6000
        self.product = make_product(price=5000, markup_type='percentage', markup=20)
        self.product.refresh_from_db()

    def test_single_sale_sets_receipt_total(self):
        receipt = Receipt.objects.create(user=self.user)
        payment = Payment.objects.create()
        Sale.objects.create(product=self.product, quantity=2,
                            receipt=receipt, payment=payment)
        receipt.refresh_from_db()
        self.assertEqual(receipt.total_with_delivery, Decimal('12000'))

    def test_two_sales_summed_in_receipt(self):
        receipt = Receipt.objects.create(user=self.user)
        payment = Payment.objects.create()
        Sale.objects.create(product=self.product, quantity=1,
                            receipt=receipt, payment=payment)
        Sale.objects.create(product=self.product, quantity=3,
                            receipt=receipt, payment=payment)
        receipt.refresh_from_db()
        # (1 + 3) × 6000 = 24000
        self.assertEqual(receipt.total_with_delivery, Decimal('24000'))

    def test_sale_line_discount_reflected_in_receipt(self):
        receipt = Receipt.objects.create(user=self.user)
        payment = Payment.objects.create()
        Sale.objects.create(product=self.product, quantity=2,
                            discount_amount=Decimal('1000'),
                            receipt=receipt, payment=payment)
        receipt.refresh_from_db()
        # 6000 × 2 − 1000 = 11000
        self.assertEqual(receipt.total_with_delivery, Decimal('11000'))

    def test_payment_percentage_discount_reduces_receipt_total(self):
        """
        discount_percentage on a Payment is read by Receipt.calculate_total()
        and subtracted from the subtotal before updating total_with_delivery.
        """
        receipt = Receipt.objects.create(user=self.user)
        payment = Payment.objects.create(discount_percentage=Decimal('10'))
        Sale.objects.create(product=self.product, quantity=1,
                            receipt=receipt, payment=payment)
        receipt.refresh_from_db()
        # 6000 − 10% = 5400
        self.assertEqual(receipt.total_with_delivery, Decimal('5400'))

    def test_payment_discount_amount_set_on_payment_save(self):
        """
        Payment.calculate_total() derives discount_amount from discount_percentage
        multiplied by the linked-sales total.  Calling payment.save() after sales
        are created populates the correct discount_amount.
        Receipt.calculate_total() no longer writes back to payment.discount_amount
        (that circular write was the source of fragile save-chain ordering bugs).
        """
        receipt = Receipt.objects.create(user=self.user)
        payment = Payment.objects.create(discount_percentage=Decimal('10'))
        Sale.objects.create(product=self.product, quantity=1,
                            receipt=receipt, payment=payment)
        # Explicitly re-save payment so Payment.calculate_total() runs with sales present.
        payment.save()
        payment.refresh_from_db()
        self.assertEqual(payment.discount_amount, Decimal('600.00'))

    def test_sale_links_customer_to_receipt(self):
        """
        When a Sale with a customer is saved against a customerless Receipt,
        the Receipt.customer should be populated.
        """
        customer = make_customer()
        receipt = Receipt.objects.create(user=self.user)
        self.assertIsNone(receipt.customer)
        Sale.objects.create(product=self.product, quantity=1,
                            receipt=receipt, customer=customer)
        receipt.refresh_from_db()
        self.assertEqual(receipt.customer, customer)

    def test_receipt_subtotal_stored_separately(self):
        """receipt.subtotal holds the pre-discount, pre-delivery item total."""
        receipt = Receipt.objects.create(user=self.user)
        payment = Payment.objects.create(discount_percentage=Decimal('10'))
        Sale.objects.create(product=self.product, quantity=2,
                            receipt=receipt, payment=payment)
        receipt.refresh_from_db()
        # subtotal = raw sum of sale totals (before discount)
        self.assertEqual(receipt.subtotal, Decimal('12000'))

    def test_gift_sale_stores_flag_and_original_value(self):
        receipt = Receipt.objects.create(user=self.user)
        Sale.objects.create(
            product=self.product, quantity=1,
            receipt=receipt,
            is_gift=True,
            original_value=self.product.selling_price,
            gift_reason='Staff appreciation',
        )
        sale = Sale.objects.get(receipt=receipt)
        self.assertTrue(sale.is_gift)
        self.assertEqual(sale.original_value, self.product.selling_price)
        self.assertEqual(sale.gift_reason, 'Staff appreciation')

    def test_gift_flag_is_false_by_default(self):
        receipt = Receipt.objects.create(user=self.user)
        Sale.objects.create(product=self.product, quantity=1, receipt=receipt)
        sale = Sale.objects.get(receipt=receipt)
        self.assertFalse(sale.is_gift)
        self.assertIsNone(sale.original_value)


# ===========================================================================
# 12. Loyalty Configuration Management
# ===========================================================================

class LoyaltyConfigurationTests(TestCase):
    """Singleton active config, point/discount calculation helpers."""

    def test_only_one_config_active_at_a_time(self):
        c1 = make_loyalty_config(program_name='Program A')
        c2 = make_loyalty_config(program_name='Program B')
        c1.refresh_from_db()
        self.assertFalse(c1.is_active)
        self.assertTrue(c2.is_active)

    def test_get_active_config_returns_the_active_one(self):
        c = make_loyalty_config(program_name='My Program')
        result = LoyaltyConfiguration.get_active_config()
        self.assertEqual(result.pk, c.pk)

    def test_get_active_config_creates_inactive_default_when_table_empty(self):
        """When no config exists at all, a default seed is created with is_active=False."""
        self.assertEqual(LoyaltyConfiguration.objects.count(), 0)
        config = LoyaltyConfiguration.get_active_config()
        self.assertIsNotNone(config)
        # Fixed: seed is inactive so callers can detect and bail gracefully
        self.assertFalse(config.is_active)

    def test_calculate_discount_double_rate(self):
        # 100 pts × ₦2/pt = ₦200
        config = make_loyalty_config(points_to_currency_rate=Decimal('2'))
        self.assertEqual(config.calculate_discount_from_points(100), Decimal('200'))

    def test_calculate_discount_zero_points(self):
        config = make_loyalty_config()
        self.assertEqual(config.calculate_discount_from_points(0), Decimal('0'))

    def test_get_maximum_redeemable_amount(self):
        # 30% of ₦10,000 = ₦3,000
        config = make_loyalty_config(maximum_discount_percentage=Decimal('30'))
        self.assertEqual(config.get_maximum_redeemable_amount(Decimal('10000')), Decimal('3000'))

    def test_get_maximum_redeemable_zero_total(self):
        config = make_loyalty_config(maximum_discount_percentage=Decimal('50'))
        self.assertEqual(config.get_maximum_redeemable_amount(Decimal('0')), Decimal('0'))

    def test_item_count_discount_capped_at_50_pct(self):
        """
        When multiplier × discount% > 50, apply_count_based_discount caps at 50%.
        """
        make_loyalty_config(
            calculation_type='item_count_discount',
            required_item_count=10,
            item_discount_percentage=Decimal('30'),  # 3 thresholds = 90% → capped
        )
        customer = make_customer()
        account = CustomerLoyaltyAccount.objects.create(customer=customer, is_active=True)
        account.item_count = 30  # 3 thresholds reached
        account.save()
        payment = make_payment(10000)

        result = apply_count_based_discount(payment, customer)
        self.assertIsNotNone(result)
        self.assertEqual(result['discount_percentage'], Decimal('50'))
        self.assertEqual(result['multiplier'], 3)

    def test_deactivating_config_returns_it_inactive(self):
        """Deactivating the only config now returns it (inactive) instead of creating a new one."""
        c = make_loyalty_config()
        c.is_active = False
        c.save()
        returned = LoyaltyConfiguration.get_active_config()
        # Same object returned, now inactive — no phantom active config created
        self.assertEqual(returned.pk, c.pk)
        self.assertFalse(returned.is_active)

    def test_transaction_count_discount_percentage_stored(self):
        config = make_loyalty_config(
            calculation_type='transaction_count_discount',
            required_transaction_count=5,
            transaction_discount_percentage=Decimal('15'),
        )
        config.refresh_from_db()
        self.assertEqual(config.transaction_discount_percentage, Decimal('15'))
        self.assertEqual(config.required_transaction_count, 5)


# ===========================================================================
# 13. Receipt Tax Details – JSON Storage & Parsing
# ===========================================================================

class ReceiptTaxDetailTests(TestCase):
    """Receipt.tax_details JSON round-trip and get_tax_breakdown() parsing."""

    def test_get_tax_breakdown_returns_dict(self):
        details = json.dumps({
            'VAT': {'rate': 7.5, 'amount': 750, 'method': 'exclusive'},
        })
        r = Receipt(tax_details=details)
        breakdown = r.get_tax_breakdown()
        self.assertIsInstance(breakdown, dict)
        self.assertIn('VAT', breakdown)

    def test_invalid_json_returns_empty_dict(self):
        r = Receipt(tax_details='not-valid-json{{}')
        self.assertEqual(r.get_tax_breakdown(), {})

    def test_empty_string_returns_empty_dict(self):
        r = Receipt(tax_details='')
        self.assertEqual(r.get_tax_breakdown(), {})

    def test_tax_details_persisted_to_database(self):
        user = make_user()
        details = json.dumps({'VAT': {'rate': 7.5, 'amount': 750, 'method': 'exclusive'}})
        r = Receipt.objects.create(user=user, tax_details=details)
        r.refresh_from_db()
        self.assertEqual(r.get_tax_breakdown()['VAT']['method'], 'exclusive')

    def test_multiple_taxes_inclusive_exclusive_split(self):
        details = json.dumps({
            'VAT':  {'rate': 7.5, 'amount': 750,  'method': 'exclusive'},
            'WHT':  {'rate': 2.0, 'amount': 200,  'method': 'inclusive'},
            'LEVY': {'rate': 1.0, 'amount': 100,  'method': 'exclusive'},
        })
        r = Receipt(tax_details=details)
        self.assertEqual(r.get_inclusive_tax_total(), Decimal('200'))
        self.assertEqual(r.get_exclusive_tax_total(), Decimal('850'))  # 750+100

    def test_no_taxes_at_all(self):
        r = Receipt(tax_details='{}')
        self.assertEqual(r.get_inclusive_tax_total(), Decimal('0'))
        self.assertEqual(r.get_exclusive_tax_total(), Decimal('0'))

    def test_all_inclusive_no_exclusive(self):
        details = json.dumps({
            'VAT': {'rate': 7.5, 'amount': 750, 'method': 'inclusive'},
        })
        r = Receipt(tax_details=details)
        self.assertEqual(r.get_exclusive_tax_total(), Decimal('0'))
        self.assertEqual(r.get_inclusive_tax_total(), Decimal('750'))

    def test_amount_before_tax_subtracts_exclusive_only(self):
        """Inclusive tax is already in the price; only exclusive is subtracted."""
        details = json.dumps({
            'EXCL': {'rate': 10, 'amount': 1000, 'method': 'exclusive'},
            'INCL': {'rate': 5,  'amount': 500,  'method': 'inclusive'},
        })
        r = Receipt(tax_details=details, total_with_delivery=Decimal('11000'))
        # 11000 − 1000 (exclusive) = 10000
        self.assertEqual(r.get_amount_before_tax(), Decimal('10000'))


# ===========================================================================
# 14. Return Items – Partial Returns & Restock Tracking
# ===========================================================================

class ReturnItemTests(TestCase):
    """ReturnItem quantities, condition, and restock flags."""

    def setUp(self):
        self.user = make_user()
        self.customer = make_customer()
        self.product = make_product(price=5000, markup_type='percentage', markup=20,
                                    quantity=10)
        self.product.refresh_from_db()  # selling_price = 6000
        self.receipt = make_receipt(user=self.user, total=Decimal('12000'))
        payment = Payment.objects.create()
        self.sale = Sale.objects.create(
            product=self.product, quantity=2,
            receipt=self.receipt, payment=payment,
        )
        self.ret = Return.objects.create(
            receipt=self.receipt, customer=self.customer,
            subtotal=Decimal('12000'), refund_amount=Decimal('12000'),
            refund_type='store_credit', status='approved',
            processed_by=self.user,
        )

    def _item(self, qty_returned=1, restock=True, condition='new'):
        return ReturnItem.objects.create(
            return_transaction=self.ret,
            original_sale=self.sale,
            product=self.product,
            quantity_sold=2,
            quantity_returned=qty_returned,
            original_selling_price=self.product.selling_price,
            original_total=self.product.selling_price * 2,
            refund_amount=self.product.selling_price * qty_returned,
            restock_to_inventory=restock,
            item_condition=condition,
        )

    def test_partial_return_quantity_stored(self):
        item = self._item(qty_returned=1)
        self.assertEqual(item.quantity_returned, 1)
        self.assertEqual(item.quantity_sold, 2)

    def test_full_return_quantity_stored(self):
        item = self._item(qty_returned=2)
        self.assertEqual(item.quantity_returned, 2)

    def test_restock_flag_defaults_to_true(self):
        item = self._item()
        self.assertTrue(item.restock_to_inventory)
        self.assertFalse(item.restocked)  # not yet actioned

    def test_no_restock_for_damaged_item(self):
        item = self._item(restock=False, condition='damaged')
        self.assertFalse(item.restock_to_inventory)
        self.assertEqual(item.item_condition, 'damaged')

    def test_refund_amount_matches_qty_returned(self):
        # Returning 1 of 2: refund = 1 × selling_price
        item = self._item(qty_returned=1)
        self.assertEqual(item.refund_amount, self.product.selling_price)

    def test_return_item_linked_to_correct_sale(self):
        item = self._item()
        self.assertEqual(item.original_sale, self.sale)
        self.assertEqual(item.product, self.product)

    def test_multiple_return_items_on_same_return(self):
        """Two different items can be returned in one Return transaction."""
        product2 = make_product(brand='Shirt', price=3000, markup_type='fixed',
                                markup=500, barcode='2000000000024', quantity=5)
        product2.refresh_from_db()
        payment2 = Payment.objects.create()
        sale2 = Sale.objects.create(product=product2, quantity=1,
                                    receipt=self.receipt, payment=payment2)
        item1 = self._item(qty_returned=2)
        item2 = ReturnItem.objects.create(
            return_transaction=self.ret,
            original_sale=sale2,
            product=product2,
            quantity_sold=1, quantity_returned=1,
            original_selling_price=product2.selling_price,
            original_total=product2.selling_price,
            refund_amount=product2.selling_price,
        )
        count = ReturnItem.objects.filter(return_transaction=self.ret).count()
        self.assertEqual(count, 2)

    def test_defective_condition_stored(self):
        item = self._item(condition='defective')
        self.assertEqual(item.item_condition, 'defective')


# ===========================================================================
# Printer factory helpers
# ===========================================================================

def make_printer_config(printer_type='barcode', system_name='DYMO LabelWriter 450',
                         name=None, is_default=True, is_active=True,
                         auto_print=False, copies=1):
    if name is None:
        name = f'Test {printer_type.upper()} Printer'
    return PrinterConfiguration.objects.create(
        name=name,
        printer_type=printer_type,
        system_printer_name=system_name,
        is_default=is_default,
        is_active=is_active,
        auto_print=auto_print,
        copies=copies,
    )


def make_task_mapping(task_name='barcode_label', printer=None, is_active=True,
                      auto_print=False, copies=1):
    return PrinterTaskMapping.objects.create(
        task_name=task_name,
        printer=printer,
        is_active=is_active,
        auto_print=auto_print,
        copies=copies,
    )


# ===========================================================================
# 15. PrinterConfiguration – default printer resolution
# ===========================================================================

class PrinterConfigurationTests(TestCase):
    """PrinterConfiguration model: get_default_printer() resolution and singleton default."""

    def _make(self, printer_type='barcode', system_name='DYMO', **kw):
        return make_printer_config(printer_type=printer_type, system_name=system_name, **kw)

    def test_get_default_returns_flagged_printer(self):
        pc = self._make(is_default=True)
        self.assertEqual(PrinterConfiguration.get_default_printer('barcode').pk, pc.pk)

    def test_get_default_falls_back_to_first_active_when_no_default_set(self):
        """is_default=False → still returned as first active for that type."""
        pc = self._make(is_default=False)
        self.assertEqual(PrinterConfiguration.get_default_printer('barcode').pk, pc.pk)

    def test_get_default_returns_none_when_no_printers_exist(self):
        self.assertIsNone(PrinterConfiguration.get_default_printer('barcode'))

    def test_saving_new_default_unsets_previous_same_type(self):
        """Only one printer per type can be is_default=True."""
        p1 = self._make(name='Barcode A', system_name='DYMO-A', is_default=True)
        p2 = self._make(name='Barcode B', system_name='DYMO-B', is_default=True)
        p1.refresh_from_db()
        self.assertFalse(p1.is_default)
        self.assertTrue(p2.is_default)

    def test_each_printer_type_has_independent_default(self):
        bc = self._make(printer_type='barcode', system_name='DYMO', name='Barcode')
        pos = self._make(printer_type='pos', system_name='XPrinter', name='POS')
        self.assertEqual(PrinterConfiguration.get_default_printer('barcode').pk, bc.pk)
        self.assertEqual(PrinterConfiguration.get_default_printer('pos').pk, pos.pk)

    def test_inactive_printer_excluded_from_default_resolution(self):
        self._make(is_default=True, is_active=False, system_name='Offline DYMO')
        self.assertIsNone(PrinterConfiguration.get_default_printer('barcode'))

    def test_system_printer_name_stored_exactly(self):
        pc = self._make(system_name='DYMO LabelWriter 450 DPI 300')
        pc.refresh_from_db()
        self.assertEqual(pc.system_printer_name, 'DYMO LabelWriter 450 DPI 300')

    def test_copies_field_defaults_to_one(self):
        pc = self._make()
        self.assertEqual(pc.copies, 1)


# ===========================================================================
# 16. PrinterTaskMapping – task-to-printer routing
# ===========================================================================

class PrinterTaskMappingTests(TestCase):
    """PrinterTaskMapping: routes tasks to printers, tracks auto-print and copies."""

    def setUp(self):
        self.barcode_printer = make_printer_config(
            printer_type='barcode', system_name='DYMO 450', name='Barcode')
        self.pos_printer = make_printer_config(
            printer_type='pos', system_name='XPrinter 80', name='POS')

    def test_get_printer_for_task_returns_correct_printer(self):
        make_task_mapping('barcode_label', printer=self.barcode_printer)
        result = PrinterTaskMapping.get_printer_for_task('barcode_label')
        self.assertEqual(result.pk, self.barcode_printer.pk)

    def test_get_printer_for_task_returns_none_when_no_mapping(self):
        self.assertIsNone(PrinterTaskMapping.get_printer_for_task('barcode_label'))

    def test_get_printer_for_task_returns_none_when_mapping_inactive(self):
        make_task_mapping('barcode_label', printer=self.barcode_printer, is_active=False)
        self.assertIsNone(PrinterTaskMapping.get_printer_for_task('barcode_label'))

    def test_barcode_and_receipt_tasks_resolved_independently(self):
        make_task_mapping('barcode_label', printer=self.barcode_printer)
        make_task_mapping('receipt_pos', printer=self.pos_printer)
        self.assertEqual(
            PrinterTaskMapping.get_printer_for_task('barcode_label').pk,
            self.barcode_printer.pk,
        )
        self.assertEqual(
            PrinterTaskMapping.get_printer_for_task('receipt_pos').pk,
            self.pos_printer.pk,
        )

    def test_should_auto_print_true_when_enabled_and_printer_set(self):
        make_task_mapping('barcode_label', printer=self.barcode_printer, auto_print=True)
        self.assertTrue(PrinterTaskMapping.should_auto_print('barcode_label'))

    def test_should_auto_print_false_when_flag_off(self):
        make_task_mapping('barcode_label', printer=self.barcode_printer, auto_print=False)
        self.assertFalse(PrinterTaskMapping.should_auto_print('barcode_label'))

    def test_should_auto_print_false_when_no_printer_assigned(self):
        """auto_print=True but printer=None → still False."""
        make_task_mapping('barcode_label', printer=None, auto_print=True)
        self.assertFalse(PrinterTaskMapping.should_auto_print('barcode_label'))

    def test_get_copies_returns_configured_count(self):
        make_task_mapping('barcode_label', printer=self.barcode_printer, copies=3)
        self.assertEqual(PrinterTaskMapping.get_copies_for_task('barcode_label'), 3)

    def test_get_copies_defaults_to_1_when_no_mapping_exists(self):
        self.assertEqual(PrinterTaskMapping.get_copies_for_task('barcode_label'), 1)


# ===========================================================================
# 17. PrinterManager – barcode print-job lifecycle
# ===========================================================================

class PrinterManagerBarcodeTests(TestCase):
    """PrinterManager.print_barcode(): resolves barcode printer, tracks PrintJob status."""

    def _printer(self, copies=1, system_name='DYMO 450'):
        return make_printer_config(
            printer_type='barcode', system_name=system_name, is_default=True, copies=copies)

    def _img(self):
        from PIL import Image
        return Image.new('RGB', (100, 50), 'white')

    @patch.object(PrinterManager, 'print_image', return_value=True)
    def test_uses_barcode_printer_resolved_by_type(self, mock_print):
        """print_barcode() calls print_image with the barcode printer's system_printer_name."""
        self._printer(system_name='DYMO LabelWriter 450')
        img = self._img()
        PrinterManager.print_barcode(img)
        mock_print.assert_called_once_with(img, 'DYMO LabelWriter 450', 1)

    @patch.object(PrinterManager, 'print_image', return_value=True)
    def test_success_creates_completed_barcode_job(self, _):
        self._printer()
        job = PrinterManager.print_barcode(self._img())
        self.assertEqual(job.status, 'completed')
        self.assertEqual(job.document_type, 'barcode')
        self.assertIsNotNone(job.completed_at)

    @patch.object(PrinterManager, 'print_image', return_value=False)
    def test_print_failure_creates_failed_job(self, _):
        self._printer()
        job = PrinterManager.print_barcode(self._img())
        self.assertEqual(job.status, 'failed')

    def test_no_barcode_printer_marks_job_failed_with_message(self):
        """With no barcode PrinterConfiguration in DB, job is marked failed."""
        job = PrinterManager.print_barcode(self._img())
        self.assertEqual(job.status, 'failed')
        self.assertIn('No barcode printer', job.error_message)

    @patch.object(PrinterManager, 'print_image', return_value=True)
    def test_job_copies_matches_printer_config(self, mock_print):
        self._printer(copies=3)
        job = PrinterManager.print_barcode(self._img())
        self.assertEqual(job.copies, 3)
        # Third positional arg to print_image is the copy count
        self.assertEqual(mock_print.call_args[0][2], 3)

    @patch.object(PrinterManager, 'print_image', return_value=True)
    def test_job_linked_to_the_configured_printer(self, _):
        pc = self._printer()
        job = PrinterManager.print_barcode(self._img())
        self.assertEqual(job.printer.pk, pc.pk)


# ===========================================================================
# 18. PrinterManager – receipt print-job lifecycle
# ===========================================================================

class PrinterManagerReceiptTests(TestCase):
    """PrinterManager.print_receipt(): pos printer, auto_print flag, receipt_id tracking."""

    def _printer(self, auto_print=True, copies=1):
        return make_printer_config(
            printer_type='pos', system_name='XPrinter 80',
            is_default=True, auto_print=auto_print, copies=copies)

    def _img(self):
        from PIL import Image
        return Image.new('RGB', (576, 400), 'white')

    @patch.object(PrinterManager, 'print_image', return_value=True)
    def test_uses_pos_printer_resolved_by_type(self, mock_print):
        self._printer()
        img = self._img()
        PrinterManager.print_receipt(img, receipt_id=7)
        mock_print.assert_called_once_with(img, 'XPrinter 80', 1)

    @patch.object(PrinterManager, 'print_image', return_value=True)
    def test_success_creates_completed_job_with_receipt_id(self, _):
        self._printer()
        job = PrinterManager.print_receipt(self._img(), receipt_id=99)
        self.assertEqual(job.status, 'completed')
        self.assertEqual(job.document_type, 'receipt')
        self.assertEqual(job.document_id, 99)

    @patch.object(PrinterManager, 'print_image', return_value=True)
    def test_auto_print_false_cancels_job_without_printing(self, mock_print):
        """auto_print=False → job cancelled immediately, print_image never called."""
        self._printer(auto_print=False)
        job = PrinterManager.print_receipt(self._img())
        self.assertEqual(job.status, 'cancelled')
        mock_print.assert_not_called()

    def test_no_pos_printer_marks_job_failed_with_message(self):
        job = PrinterManager.print_receipt(self._img())
        self.assertEqual(job.status, 'failed')
        self.assertIn('No POS printer', job.error_message)

    @patch.object(PrinterManager, 'print_image', return_value=False)
    def test_print_image_failure_marks_job_failed(self, _):
        self._printer()
        job = PrinterManager.print_receipt(self._img())
        self.assertEqual(job.status, 'failed')

    @patch.object(PrinterManager, 'print_image', return_value=True)
    def test_job_copies_matches_printer_config(self, mock_print):
        self._printer(copies=2)
        job = PrinterManager.print_receipt(self._img())
        self.assertEqual(job.copies, 2)
        self.assertEqual(mock_print.call_args[0][2], 2)


# ===========================================================================
# 19. Barcode Print Views – printer resolution & exact copy counts
# ===========================================================================

class BarcodePrintViewTests(TestCase):
    """
    print_multiple_barcodes_directly & print_single_barcode_directly:
      - Printer resolution order: task mapping → barcode config → OS default
      - print_image called exactly the requested number of times (no over/under)
      - Partial failures reported accurately per product
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.barcode_printer = make_printer_config(
            printer_type='barcode', system_name='DYMO 450', is_default=True)
        self.product = make_product(
            price=5000, markup_type='percentage', markup=10, barcode='1234567890123')
        # Give the product a fake barcode image path so the view skips re-generation
        Product.objects.filter(pk=self.product.pk).update(
            barcode_image='barcodes/fake_test.png')
        self.product.refresh_from_db()

    def _multi_request(self, products_data):
        req = self.factory.post(
            '/print_multiple_barcodes_directly/',
            data=json.dumps({'products': products_data}),
            content_type='application/json',
        )
        req.session = {}
        return req

    def _single_request(self, product_id, quantity):
        req = self.factory.post(
            f'/print_single_barcode_directly/{product_id}/',
            data=json.dumps({'quantity': quantity}),
            content_type='application/json',
        )
        req.session = {}
        return req

    # ── Printer resolution ────────────────────────────────────────────────

    @patch('store.views.print_image', return_value=True)
    @patch('store.views.time.sleep')
    def test_multi_task_mapping_takes_priority_over_config(self, _sleep, _print):
        """Task mapping is checked before PrinterConfiguration."""
        from store.views import print_multiple_barcodes_directly
        make_task_mapping('barcode_label', printer=self.barcode_printer)
        response = print_multiple_barcodes_directly(
            self._multi_request([{'product_id': self.product.pk, 'quantity': 1}]))
        data = json.loads(response.content)
        self.assertEqual(data['printer_name'], 'DYMO 450')
        self.assertEqual(data['printer_source'], 'task_mapping')

    @patch('store.views.print_image', return_value=True)
    @patch('store.views.time.sleep')
    def test_multi_falls_back_to_barcode_config_when_no_task_mapping(self, _sleep, _print):
        """No task mapping → PrinterConfiguration(type='barcode') used."""
        from store.views import print_multiple_barcodes_directly
        response = print_multiple_barcodes_directly(
            self._multi_request([{'product_id': self.product.pk, 'quantity': 1}]))
        data = json.loads(response.content)
        self.assertEqual(data['printer_name'], 'DYMO 450')
        self.assertEqual(data['printer_source'], 'barcode_config')

    @patch('store.views.print_image', return_value=True)
    @patch('store.views.time.sleep')
    @patch('store.views.win32print.GetDefaultPrinter', return_value='OS Default Printer')
    def test_multi_falls_back_to_os_default_when_no_active_config(
            self, _default, _sleep, _print):
        """No task mapping and no active barcode config → OS default printer."""
        from store.views import print_multiple_barcodes_directly
        self.barcode_printer.is_active = False
        self.barcode_printer.save()
        response = print_multiple_barcodes_directly(
            self._multi_request([{'product_id': self.product.pk, 'quantity': 1}]))
        data = json.loads(response.content)
        self.assertEqual(data['printer_name'], 'OS Default Printer')
        self.assertEqual(data['printer_source'], 'fallback')

    # ── Error handling ───────────────────────────────────────────────────

    def test_multi_empty_products_list_returns_error(self):
        from store.views import print_multiple_barcodes_directly
        response = print_multiple_barcodes_directly(self._multi_request([]))
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('No products', data['error'])

    def test_multi_invalid_json_returns_error(self):
        from store.views import print_multiple_barcodes_directly
        req = self.factory.post(
            '/print_multiple_barcodes_directly/',
            data='not valid json {{',
            content_type='application/json',
        )
        req.session = {}
        response = print_multiple_barcodes_directly(req)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('Invalid JSON', data['error'])

    # ── Quantity accuracy (no over/under printing) ───────────────────────

    @patch('store.views.print_image', return_value=True)
    @patch('store.views.time.sleep')
    def test_multi_prints_exact_requested_quantity(self, _sleep, mock_print):
        """print_image called exactly quantity times; response confirms correct count."""
        from store.views import print_multiple_barcodes_directly
        response = print_multiple_barcodes_directly(
            self._multi_request([{'product_id': self.product.pk, 'quantity': 3}]))
        data = json.loads(response.content)
        self.assertEqual(mock_print.call_count, 3)
        self.assertEqual(data['total_printed'], 3)
        result = data['results'][0]
        self.assertEqual(result['printed_quantity'], 3)
        self.assertEqual(result['requested_quantity'], 3)
        self.assertTrue(result['success'])

    @patch('store.views.print_image', return_value=True)
    @patch('store.views.time.sleep')
    def test_multi_two_products_printed_with_independent_quantities(self, _sleep, mock_print):
        """Each product receives its own quantity — totals add up correctly."""
        product2 = make_product(
            brand='Shirt', price=3000, markup_type='fixed', markup=500, barcode='9999999999991')
        Product.objects.filter(pk=product2.pk).update(barcode_image='barcodes/fake2.png')
        product2.refresh_from_db()
        from store.views import print_multiple_barcodes_directly
        response = print_multiple_barcodes_directly(self._multi_request([
            {'product_id': self.product.pk, 'quantity': 2},
            {'product_id': product2.pk,     'quantity': 1},
        ]))
        data = json.loads(response.content)
        self.assertEqual(mock_print.call_count, 3)   # 2 + 1
        self.assertEqual(data['total_printed'], 3)
        self.assertEqual(data['total_products'], 2)
        self.assertEqual(data['results'][0]['printed_quantity'], 2)
        self.assertEqual(data['results'][1]['printed_quantity'], 1)

    @patch('store.views.print_image', side_effect=[True, False, True])
    @patch('store.views.time.sleep')
    def test_multi_partial_copy_failures_reported_accurately(self, _sleep, mock_print):
        """2 of 3 copies succeed → printed_quantity=2, success=False (not all printed)."""
        from store.views import print_multiple_barcodes_directly
        response = print_multiple_barcodes_directly(
            self._multi_request([{'product_id': self.product.pk, 'quantity': 3}]))
        data = json.loads(response.content)
        self.assertEqual(data['total_printed'], 2)
        result = data['results'][0]
        self.assertEqual(result['printed_quantity'], 2)
        self.assertEqual(result['requested_quantity'], 3)
        self.assertFalse(result['success'])   # 2 ≠ 3

    # ── Single barcode view ──────────────────────────────────────────────

    @patch('store.views.print_image', return_value=True)
    @patch('store.views.time.sleep')
    def test_single_uses_task_mapping_printer(self, _sleep, mock_print):
        from store.views import print_single_barcode_directly
        make_task_mapping('barcode_label', printer=self.barcode_printer)
        response = print_single_barcode_directly(
            self._single_request(self.product.pk, 2), self.product.pk)
        data = json.loads(response.content)
        self.assertEqual(data['printer_name'], 'DYMO 450')
        self.assertEqual(mock_print.call_count, 2)

    @patch('store.views.print_image', return_value=True)
    @patch('store.views.time.sleep')
    def test_single_prints_exact_requested_quantity(self, _sleep, mock_print):
        """print_image called exactly quantity times for a single product."""
        from store.views import print_single_barcode_directly
        response = print_single_barcode_directly(
            self._single_request(self.product.pk, 4), self.product.pk)
        data = json.loads(response.content)
        self.assertEqual(mock_print.call_count, 4)
        self.assertEqual(data['printed_quantity'], 4)
        self.assertEqual(data['requested_quantity'], 4)
        self.assertTrue(data['success'])

    @patch('store.views.print_image', side_effect=[True, False])
    @patch('store.views.time.sleep')
    def test_single_partial_failure_shows_actual_printed_count(self, _sleep, mock_print):
        """1 of 2 copies fail → printed_quantity=1, success=True (>0 printed)."""
        from store.views import print_single_barcode_directly
        response = print_single_barcode_directly(
            self._single_request(self.product.pk, 2), self.product.pk)
        data = json.loads(response.content)
        self.assertEqual(data['printed_quantity'], 1)
        self.assertEqual(data['requested_quantity'], 2)
        self.assertTrue(data['success'])


# ===========================================================================
# 20. Receipt Printer Routing – print_pos_receipt view
# ===========================================================================

class ReceiptPrinterRoutingTests(TestCase):
    """
    print_pos_receipt view: correct printer name passed to Win32Raw based on
    task mapping, falling back to OS default when no mapping exists.
    """

    def setUp(self):
        self.user = make_user()
        self.receipt = make_receipt(user=self.user, total=Decimal('10000'))
        self.pos_printer = make_printer_config(
            printer_type='pos', system_name='XPrinter 80', is_default=True)
        self.client.force_login(self.user)

    @patch('escpos.printer.Win32Raw')
    def test_task_mapping_printer_used_for_receipt(self, MockWin32):
        """When receipt_pos task mapping exists, Win32Raw is opened with that printer."""
        make_task_mapping('receipt_pos', printer=self.pos_printer)
        self.client.post(reverse('print_pos_receipt', args=[self.receipt.pk]))
        MockWin32.assert_called_with('XPrinter 80')

    @patch('store.views.win32print.GetDefaultPrinter', return_value='FALLBACK PRINTER')
    @patch('escpos.printer.Win32Raw')
    def test_falls_back_to_os_default_when_no_task_mapping(self, MockWin32, _default):
        """No task mapping → Win32Raw opened with the OS default printer name."""
        self.client.post(reverse('print_pos_receipt', args=[self.receipt.pk]))
        MockWin32.assert_called_with('FALLBACK PRINTER')

    @patch('escpos.printer.Win32Raw')
    def test_successful_print_returns_success_json(self, _):
        """Successful (mocked) print returns {success: True, message: printer_name}."""
        make_task_mapping('receipt_pos', printer=self.pos_printer)
        response = self.client.post(
            reverse('print_pos_receipt', args=[self.receipt.pk]))
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn('XPrinter 80', data['message'])

    def test_get_request_rejected_with_405(self):
        """print_pos_receipt only accepts POST requests."""
        response = self.client.get(
            reverse('print_pos_receipt', args=[self.receipt.pk]))
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertEqual(response.status_code, 405)


# ===========================================================================
# 21. Sale – Line Discount Edge Cases
# ===========================================================================

class SaleLineDiscountEdgeCasesTests(TestCase):
    """Edge cases for Sale.calculate_total(): oversized discount, None, decimal precision."""

    def setUp(self):
        # price=10000, 10% markup → selling_price=11000
        self.product = make_product(price=10000, markup_type='percentage', markup=10)
        self.product.refresh_from_db()

    def test_discount_larger_than_line_total_gives_negative(self):
        """discount_amount > item_total → negative line total (no guard in model)."""
        sale = Sale(product=self.product, quantity=1, discount_amount=Decimal('12000'))
        # 11000 - 12000 = -1000
        self.assertEqual(sale.calculate_total(), Decimal('-1000'))

    def test_discount_exactly_equals_line_total_gives_zero(self):
        sale = Sale(product=self.product, quantity=2, discount_amount=Decimal('22000'))
        self.assertEqual(sale.calculate_total(), Decimal('0'))

    def test_none_discount_amount_treated_as_zero(self):
        sale = Sale(product=self.product, quantity=1, discount_amount=None)
        self.assertEqual(sale.calculate_total(), Decimal('11000'))

    def test_decimal_precision_preserved(self):
        """Fractional selling price × qty keeps decimal precision."""
        with patch.object(Product, 'generate_barcode'):
            p = Product.objects.create(
                brand='Precise', price=Decimal('333.33'),
                markup_type='percentage', markup=Decimal('0'),
                size='S', category='shoes', shop='STORE', quantity=10,
            )
        p.refresh_from_db()
        sale = Sale(product=p, quantity=3, discount_amount=Decimal('0'))
        # 333.33 * 3 = 999.99
        self.assertEqual(sale.calculate_total(), Decimal('999.99'))

    def test_multiple_sales_different_discounts_sum_correctly_on_receipt(self):
        """Two discounted lines: receipt total = sum of each calculate_total()."""
        user = make_user()
        receipt = Receipt.objects.create(user=user)
        payment = Payment.objects.create()
        # Line 1: 11000*2 - 1000 = 21000
        Sale.objects.create(product=self.product, quantity=2,
                            discount_amount=Decimal('1000'),
                            receipt=receipt, payment=payment)
        # Line 2: 11000*1 - 500 = 10500
        Sale.objects.create(product=self.product, quantity=1,
                            discount_amount=Decimal('500'),
                            receipt=receipt, payment=payment)
        receipt.refresh_from_db()
        self.assertEqual(receipt.total_with_delivery, Decimal('31500'))

    def test_discount_only_on_one_line_other_line_full_price(self):
        user = make_user()
        receipt = Receipt.objects.create(user=user)
        payment = Payment.objects.create()
        Sale.objects.create(product=self.product, quantity=1,
                            discount_amount=Decimal('1000'),
                            receipt=receipt, payment=payment)
        Sale.objects.create(product=self.product, quantity=1,
                            discount_amount=Decimal('0'),
                            receipt=receipt, payment=payment)
        receipt.refresh_from_db()
        # (11000 - 1000) + 11000 = 21000
        self.assertEqual(receipt.total_with_delivery, Decimal('21000'))

    def test_discount_larger_than_line_total_clamped_on_save(self):
        """discount_amount > item_total is clamped to item_total when saved."""
        user = make_user('clamp_user')
        receipt = Receipt.objects.create(user=user)
        sale = Sale.objects.create(
            product=self.product,
            quantity=1,
            discount_amount=Decimal('99000'),  # far exceeds 11000
            receipt=receipt,
            payment=Payment.objects.create(),
        )
        sale.refresh_from_db()
        # Clamped to item_total (11000); total_price = 0
        self.assertEqual(sale.discount_amount, Decimal('11000.00'))
        self.assertEqual(sale.total_price, Decimal('0.00'))


# ===========================================================================
# 22. Payment – Discount Chain Interaction
# ===========================================================================

class PaymentDiscountChainTests(TestCase):
    """
    Payment.calculate_total() discount chain:
    - loyalty_discount_amount reduces the final total after % discount
    - discount_amount is derived from discount_percentage when set
    - No guard prevents negative totals when loyalty_discount > subtotal
    """

    def setUp(self):
        self.user = make_user()
        # price=10000, 20% markup → selling_price=12000
        self.product = make_product(price=10000, markup_type='percentage', markup=20)
        self.product.refresh_from_db()

    def _make_receipt_payment(self, qty=1, disc_pct=None, loyalty_disc=Decimal('0')):
        receipt = Receipt.objects.create(user=self.user)
        payment = Payment.objects.create(
            discount_percentage=disc_pct,
            loyalty_discount_amount=loyalty_disc,
        )
        Sale.objects.create(product=self.product, quantity=qty,
                            receipt=receipt, payment=payment)
        # Payment was saved before the Sale existed; recalculate now.
        payment.save()
        payment.refresh_from_db()
        return payment

    def test_loyalty_discount_reduces_total(self):
        """loyalty_discount_amount is subtracted from the final payment total."""
        payment = self._make_receipt_payment(qty=1, loyalty_disc=Decimal('500'))
        # 12000 - 500 = 11500
        self.assertEqual(payment.total_amount, Decimal('11500'))

    def test_percentage_discount_then_loyalty_discount(self):
        """10% off 12000 = 10800, then loyalty 800 → 10000."""
        payment = self._make_receipt_payment(
            qty=1, disc_pct=Decimal('10'), loyalty_disc=Decimal('800'))
        self.assertEqual(payment.total_amount, Decimal('10000'))

    def test_loyalty_discount_zero_does_not_affect_total(self):
        payment = self._make_receipt_payment(qty=1, loyalty_disc=Decimal('0'))
        self.assertEqual(payment.total_amount, Decimal('12000'))

    def test_percentage_discount_recalculates_discount_amount(self):
        """When discount_percentage is set, discount_amount = pct × subtotal."""
        payment = self._make_receipt_payment(qty=1, disc_pct=Decimal('25'))
        # 25% of 12000 = 3000
        self.assertEqual(payment.discount_amount, Decimal('3000'))

    def test_loyalty_exceeding_subtotal_gives_negative_total(self):
        """No guard: loyalty_discount_amount > total → negative total_amount."""
        payment = self._make_receipt_payment(qty=1, loyalty_disc=Decimal('15000'))
        # 12000 - 15000 = -3000
        self.assertEqual(payment.total_amount, Decimal('-3000'))

    def test_two_sales_discount_percentage_on_combined_total(self):
        """discount_percentage is applied to the SUM of all sales, not per line."""
        receipt = Receipt.objects.create(user=self.user)
        payment = Payment.objects.create(discount_percentage=Decimal('10'))
        Sale.objects.create(product=self.product, quantity=1,
                            receipt=receipt, payment=payment)
        Sale.objects.create(product=self.product, quantity=1,
                            receipt=receipt, payment=payment)
        # Recalculate with both sales now linked.
        payment.save()
        payment.refresh_from_db()
        # 12000 + 12000 = 24000; 10% off = 21600
        self.assertEqual(payment.total_amount, Decimal('21600'))

    def test_no_discount_full_price(self):
        """No percentage, no loyalty → total_amount = selling_price × qty."""
        payment = self._make_receipt_payment(qty=2)
        self.assertEqual(payment.total_amount, Decimal('24000'))


# ===========================================================================
# 23. Return – Refund Amount Calculations
# ===========================================================================

class ReturnRefundAmountsTests(TestCase):
    """
    ReturnItem.refund_amount reflects quantity_returned × original_selling_price.
    Return.restocking_fee and Return.refund_amount are stored fields (caller sets them).
    """

    def setUp(self):
        self.user = make_user()
        self.customer = make_customer()
        # price=5000, 20% markup → selling_price=6000
        self.product = make_product(price=5000, markup_type='percentage', markup=20)
        self.product.refresh_from_db()
        self.receipt = Receipt.objects.create(user=self.user, customer=self.customer)
        self.payment = Payment.objects.create()
        self.sale = Sale.objects.create(
            product=self.product, quantity=10,
            receipt=self.receipt, payment=self.payment,
        )
        self.sale.refresh_from_db()

    def _make_return(self, restocking_fee=Decimal('0'), refund_amount=Decimal('0')):
        return Return.objects.create(
            receipt=self.receipt,
            customer=self.customer,
            subtotal=self.sale.total_price,
            restocking_fee=restocking_fee,
            refund_amount=refund_amount,
            processed_by=self.user,
        )

    def _make_return_item(self, ret, qty_returned):
        refund = self.product.selling_price * qty_returned
        return ReturnItem.objects.create(
            return_transaction=ret,
            original_sale=self.sale,
            product=self.product,
            quantity_sold=self.sale.quantity,
            quantity_returned=qty_returned,
            original_selling_price=self.product.selling_price,
            original_total=refund,
            refund_amount=refund,
        )

    def test_partial_return_refund_is_pro_rated(self):
        """Returning 3 out of 10: refund = 3 × selling_price."""
        ret = self._make_return()
        item = self._make_return_item(ret, qty_returned=3)
        self.assertEqual(item.refund_amount, Decimal('18000'))

    def test_full_return_refund_equals_original_total(self):
        ret = self._make_return()
        item = self._make_return_item(ret, qty_returned=10)
        self.assertEqual(item.refund_amount, Decimal('60000'))

    def test_single_item_return(self):
        ret = self._make_return()
        item = self._make_return_item(ret, qty_returned=1)
        self.assertEqual(item.refund_amount, Decimal('6000'))

    def test_restocking_fee_reduces_net_refund(self):
        """restocking_fee stored on Return; net refund = gross − fee."""
        restocking = Decimal('500')
        gross = self.product.selling_price * 2  # 12000
        net = gross - restocking                 # 11500
        ret = self._make_return(restocking_fee=restocking, refund_amount=net)
        self.assertEqual(ret.restocking_fee, Decimal('500'))
        self.assertEqual(ret.refund_amount, Decimal('11500'))

    def test_zero_restocking_fee_full_refund(self):
        gross = self.product.selling_price * 5  # 30000
        ret = self._make_return(restocking_fee=Decimal('0'), refund_amount=gross)
        self.assertEqual(ret.refund_amount, Decimal('30000'))

    def test_multiple_return_items_have_independent_refunds(self):
        """Two ReturnItems on same Return carry separate refund_amount values."""
        product2 = make_product(brand='Second', price=3000,
                                markup_type='percentage', markup=10)
        product2.refresh_from_db()  # selling_price=3300
        sale2 = Sale.objects.create(
            product=product2, quantity=5,
            receipt=self.receipt, payment=self.payment,
        )
        ret = self._make_return()
        item1 = self._make_return_item(ret, qty_returned=2)  # 2×6000=12000
        item2 = ReturnItem.objects.create(
            return_transaction=ret,
            original_sale=sale2,
            product=product2,
            quantity_sold=5,
            quantity_returned=3,
            original_selling_price=product2.selling_price,
            original_total=product2.selling_price * 3,
            refund_amount=product2.selling_price * 3,  # 3×3300=9900
        )
        self.assertEqual(item1.refund_amount, Decimal('12000'))
        self.assertEqual(item2.refund_amount, Decimal('9900'))

    def test_return_number_auto_generated_with_ret_prefix(self):
        ret = self._make_return()
        self.assertTrue(ret.return_number.startswith('RET'))
        self.assertIn('/', ret.return_number)


# ===========================================================================
# 24. Product – Inventory Stock Level Tracking
# ===========================================================================

class ProductStockLevelTests(TestCase):
    """Sale.save() decrements product.quantity and guards against overselling."""

    def setUp(self):
        self.user = make_user()
        self.product = make_product(price=5000, markup_type='percentage',
                                    markup=10, quantity=20)
        self.product.refresh_from_db()

    def test_product_quantity_decremented_after_sale_save(self):
        """Sale.save() atomically decrements product.quantity on insert."""
        receipt = Receipt.objects.create(user=self.user)
        payment = Payment.objects.create()
        Sale.objects.create(product=self.product, quantity=5,
                            receipt=receipt, payment=payment)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 15)  # 20 - 5

    def test_product_quantity_not_decremented_on_sale_update(self):
        """Updating an existing Sale does NOT decrement quantity a second time."""
        receipt = Receipt.objects.create(user=self.user)
        payment = Payment.objects.create()
        sale = Sale.objects.create(product=self.product, quantity=5,
                                   receipt=receipt, payment=payment)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 15)  # first decrement

        # Update the sale (e.g. change discount) — should NOT decrement again
        sale.discount_amount = Decimal('100')
        sale.save()
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 15)  # unchanged

    def test_manual_quantity_decrement_persists(self):
        self.product.quantity -= 5
        with patch.object(Product, 'generate_barcode'):
            self.product.save()
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 15)

    def test_low_stock_threshold_filter(self):
        """Products with quantity < 10 appear in low-stock filter."""
        low = make_product(brand='LowStock', price=1000,
                           markup_type='percentage', markup=10, quantity=3)
        high = make_product(brand='HighStock', price=1000,
                            markup_type='percentage', markup=10, quantity=50)
        low_qs = Product.objects.filter(quantity__lt=10)
        self.assertIn(low, low_qs)
        self.assertNotIn(high, low_qs)

    def test_critical_stock_filter(self):
        """Products with quantity < 5 appear in critical filter."""
        critical = make_product(brand='Critical', price=1000,
                                markup_type='percentage', markup=10, quantity=2)
        normal = make_product(brand='Normal', price=1000,
                              markup_type='percentage', markup=10, quantity=8)
        critical_qs = Product.objects.filter(quantity__lt=5)
        self.assertIn(critical, critical_qs)
        self.assertNotIn(normal, critical_qs)

    def test_zero_quantity_product_in_critical_filter(self):
        zero = make_product(brand='ZeroStock', price=1000,
                            markup_type='percentage', markup=10, quantity=0)
        self.assertIn(zero, Product.objects.filter(quantity__lt=5))

    def test_inventory_total_value_calculation(self):
        """Total inventory value = sum(selling_price × quantity) across products."""
        # self.product: selling_price=5500, qty=20 → 110000
        p2 = make_product(brand='Second', price=2000,
                          markup_type='percentage', markup=10, quantity=5)
        p2.refresh_from_db()  # selling_price=2200, qty=5 → 11000
        total_value = sum(
            p.selling_price * p.quantity for p in Product.objects.all()
        )
        self.assertEqual(total_value, Decimal('110000') + Decimal('11000'))

    def test_inventory_potential_profit(self):
        """Potential profit = sum(selling_price × qty) − sum(cost × qty)."""
        # self.product: (5500−5000)×20 = 10000 profit
        selling = sum(p.selling_price * p.quantity for p in Product.objects.all())
        cost = sum(p.price * p.quantity for p in Product.objects.all())
        self.assertEqual(selling - cost, Decimal('10000'))

    def test_average_markup_aggregation(self):
        from django.db.models import Avg
        avg = Product.objects.aggregate(avg_markup=Avg('markup'))['avg_markup']
        self.assertEqual(avg, Decimal('10'))

    def test_oversell_raises_validation_error(self):
        """Selling more than available stock raises ValidationError."""
        receipt = Receipt.objects.create(user=self.user)
        payment = Payment.objects.create()
        with self.assertRaises(ValidationError):
            Sale.objects.create(product=self.product, quantity=21,  # only 20 in stock
                                receipt=receipt, payment=payment)

    def test_selling_exact_stock_succeeds(self):
        """Selling exactly the available quantity is allowed."""
        receipt = Receipt.objects.create(user=self.user)
        payment = Payment.objects.create()
        Sale.objects.create(product=self.product, quantity=20,
                            receipt=receipt, payment=payment)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 0)

    def test_selling_zero_stock_raises_validation_error(self):
        """Selling any unit when stock is 0 raises ValidationError."""
        self.product.quantity = 0
        with patch.object(Product, 'generate_barcode'):
            self.product.save()
        receipt = Receipt.objects.create(user=self.user)
        with self.assertRaises(ValidationError):
            Sale.objects.create(product=self.product, quantity=1,
                                receipt=receipt, payment=Payment.objects.create())

    def test_stock_guard_does_not_fire_on_update(self):
        """Updating an existing sale never triggers the stock guard."""
        receipt = Receipt.objects.create(user=self.user)
        sale = Sale.objects.create(product=self.product, quantity=20,
                                   receipt=receipt, payment=Payment.objects.create())
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 0)

        # Even though stock is now 0, updating the existing sale must not raise
        sale.discount_amount = Decimal('500')
        sale.save()  # should not raise


# ===========================================================================
# 25. Discount Report – Aggregation Formulas
# ===========================================================================

class DiscountReportAggregationTests(TestCase):
    """
    Verifies the exact aggregation formulas used in the discount_report view:
    - Sum of payment-level discount_amount
    - Sum of sale line-level discount_amount
    - Combined total = payment + line discounts
    """

    def setUp(self):
        from django.db.models import Sum
        self.Sum = Sum
        self.user = make_user()
        self.product = make_product(price=10000, markup_type='percentage', markup=10)
        self.product.refresh_from_db()

    def test_payment_level_discount_sum(self):
        with patch.object(Payment, 'calculate_total', return_value=Decimal('9000')):
            p1 = Payment.objects.create()
            Payment.objects.filter(pk=p1.pk).update(discount_amount=Decimal('1000'))
        with patch.object(Payment, 'calculate_total', return_value=Decimal('8500')):
            p2 = Payment.objects.create()
            Payment.objects.filter(pk=p2.pk).update(discount_amount=Decimal('1500'))
        total = (Payment.objects
                 .filter(discount_amount__gt=0)
                 .aggregate(total=self.Sum('discount_amount'))['total'] or 0)
        self.assertEqual(total, Decimal('2500'))

    def test_line_level_discount_sum(self):
        receipt = Receipt.objects.create(user=self.user)
        payment = Payment.objects.create()
        Sale.objects.create(product=self.product, quantity=1,
                            discount_amount=Decimal('500'),
                            receipt=receipt, payment=payment)
        Sale.objects.create(product=self.product, quantity=1,
                            discount_amount=Decimal('300'),
                            receipt=receipt, payment=payment)
        # Sale with no discount should NOT be counted
        Sale.objects.create(product=self.product, quantity=1,
                            discount_amount=Decimal('0'),
                            receipt=receipt, payment=payment)
        total = (Sale.objects
                 .filter(discount_amount__gt=0)
                 .aggregate(total=self.Sum('discount_amount'))['total'] or 0)
        self.assertEqual(total, Decimal('800'))

    def test_combined_payment_and_line_discount_total(self):
        with patch.object(Payment, 'calculate_total', return_value=Decimal('9000')):
            p = Payment.objects.create()
            Payment.objects.filter(pk=p.pk).update(discount_amount=Decimal('1000'))
        receipt = Receipt.objects.create(user=self.user)
        Sale.objects.create(product=self.product, quantity=1,
                            discount_amount=Decimal('400'),
                            receipt=receipt, payment=p)
        pay_disc = (Payment.objects
                    .filter(discount_amount__gt=0)
                    .aggregate(total=self.Sum('discount_amount'))['total'] or 0)
        line_disc = (Sale.objects
                     .filter(discount_amount__gt=0)
                     .aggregate(total=self.Sum('discount_amount'))['total'] or 0)
        self.assertEqual(pay_disc + line_disc, Decimal('1400'))

    def test_no_discounts_returns_zero_not_none(self):
        total = (Payment.objects
                 .filter(discount_amount__gt=0)
                 .aggregate(total=self.Sum('discount_amount'))['total'] or 0)
        self.assertEqual(total, 0)


# ===========================================================================
# 26. Delivery – Fee Aggregation & Average
# ===========================================================================

class DeliveryAggregationTests(TestCase):
    """
    delivery_report view formulas:
    - total_delivery_fees = Sum(delivery_cost) for receipts with delivery_cost > 0
    - avg_delivery_fee = total / count, zero-division guard when no deliveries
    """

    def setUp(self):
        from django.db.models import Sum
        self.Sum = Sum
        self.user = make_user()

    def _receipt_with_delivery(self, cost):
        r = Receipt.objects.create(user=self.user)
        Receipt.objects.filter(pk=r.pk).update(delivery_cost=cost)
        r.refresh_from_db()
        return r

    def test_total_delivery_fees_sum(self):
        self._receipt_with_delivery(Decimal('500'))
        self._receipt_with_delivery(Decimal('750'))
        self._receipt_with_delivery(Decimal('250'))
        total = (Receipt.objects
                 .filter(delivery_cost__gt=0)
                 .aggregate(total=self.Sum('delivery_cost'))['total'] or 0)
        self.assertEqual(total, Decimal('1500'))

    def test_average_delivery_fee(self):
        self._receipt_with_delivery(Decimal('600'))
        self._receipt_with_delivery(Decimal('400'))
        qs = Receipt.objects.filter(delivery_cost__gt=0)
        total = qs.aggregate(total=self.Sum('delivery_cost'))['total'] or 0
        count = qs.count()
        avg = total / count if count > 0 else 0
        self.assertEqual(avg, Decimal('500'))

    def test_no_deliveries_average_is_zero(self):
        """Zero-division guard: no receipts with delivery → avg = 0."""
        qs = Receipt.objects.filter(delivery_cost__gt=0)
        total = qs.aggregate(total=self.Sum('delivery_cost'))['total'] or 0
        count = qs.count()
        avg = total / count if count > 0 else 0
        self.assertEqual(avg, 0)

    def test_single_receipt_average_equals_that_fee(self):
        self._receipt_with_delivery(Decimal('800'))
        qs = Receipt.objects.filter(delivery_cost__gt=0)
        total = qs.aggregate(total=self.Sum('delivery_cost'))['total'] or 0
        count = qs.count()
        avg = total / count if count > 0 else 0
        self.assertEqual(avg, Decimal('800'))

    def test_zero_cost_receipts_excluded_from_sum(self):
        self._receipt_with_delivery(Decimal('0'))
        self._receipt_with_delivery(Decimal('300'))
        total = (Receipt.objects
                 .filter(delivery_cost__gt=0)
                 .aggregate(total=self.Sum('delivery_cost'))['total'] or 0)
        self.assertEqual(total, Decimal('300'))


# ===========================================================================
# 27. Financial Report – Revenue, Cost & Profit Metrics
# ===========================================================================

class FinancialMetricsTests(TestCase):
    """
    Verifies financial_report formulas:
    - gross_revenue = sum(selling_price × qty)
    - total_cost    = sum(cost_price × qty)
    - profit        = net_revenue - total_cost
    - profit_margin = (profit / net_revenue) × 100, with zero-division guard
    """

    def setUp(self):
        self.user = make_user()
        # cost=5000, 20% markup → selling_price=6000
        self.product = make_product(price=5000, markup_type='percentage', markup=20)
        self.product.refresh_from_db()

    def _make_sales(self, quantities):
        receipt = Receipt.objects.create(user=self.user)
        payment = Payment.objects.create()
        for qty in quantities:
            Sale.objects.create(product=self.product, quantity=qty,
                                receipt=receipt, payment=payment)
        return Sale.objects.filter(receipt=receipt)

    def test_gross_revenue_single_sale(self):
        sales = self._make_sales([3])
        gross = sum(s.product.selling_price * s.quantity for s in sales)
        self.assertEqual(gross, Decimal('18000'))

    def test_gross_revenue_multiple_sales(self):
        sales = self._make_sales([2, 4])
        gross = sum(s.product.selling_price * s.quantity for s in sales)
        self.assertEqual(gross, Decimal('36000'))

    def test_total_cost_is_cost_price_times_qty(self):
        sales = self._make_sales([3])
        total_cost = sum(s.product.price * s.quantity for s in sales)
        self.assertEqual(total_cost, Decimal('15000'))

    def test_profit_equals_revenue_minus_cost(self):
        sales = self._make_sales([5])
        revenue = sum(s.product.selling_price * s.quantity for s in sales)
        cost = sum(s.product.price * s.quantity for s in sales)
        self.assertEqual(revenue - cost, Decimal('5000'))

    def test_profit_margin_percentage(self):
        sales = self._make_sales([10])
        revenue = sum(s.product.selling_price * s.quantity for s in sales)  # 60000
        cost = sum(s.product.price * s.quantity for s in sales)             # 50000
        profit = revenue - cost                                              # 10000
        margin = float(profit / revenue * 100) if revenue > 0 else 0
        self.assertAlmostEqual(margin, 16.666, places=2)

    def test_zero_revenue_profit_margin_is_zero(self):
        revenue = Decimal('0')
        profit = Decimal('0')
        margin = (profit / revenue * 100) if revenue > 0 else 0
        self.assertEqual(margin, 0)

    def test_combined_item_and_payment_discounts_summed(self):
        """total_discounts = item_discounts + payment_discounts."""
        receipt = Receipt.objects.create(user=self.user)
        payment = Payment.objects.create(discount_percentage=Decimal('10'))
        Sale.objects.create(product=self.product, quantity=1,
                            discount_amount=Decimal('200'),
                            receipt=receipt, payment=payment)
        payment.refresh_from_db()
        sales = Sale.objects.filter(receipt=receipt)
        unique_payments = Payment.objects.filter(sale__in=sales).distinct()
        item_disc = sum(s.discount_amount or 0 for s in sales)
        pay_disc = sum(p.discount_amount or 0 for p in unique_payments)
        # item: 200, payment: 10% of (6000-200)=580 → check total is non-zero
        self.assertGreater(item_disc + pay_disc, 0)


# ===========================================================================
# 28. Item Count Discount – Multiplier, Cap & Remainder
# ===========================================================================

class ItemCountDiscountMultiplierTests(TestCase):
    """
    apply_count_based_discount() item_count path:
    - 2× multiplier → doubles discount percentage
    - 3× multiplier hitting 50% cap
    - Modulo remainder stored correctly after discount
    - Full transaction_count cycle: earn → apply → reset → re-earn
    """

    def setUp(self):
        self.customer = make_customer()

    def _item_config(self, required, pct):
        return make_loyalty_config(
            calculation_type='item_count_discount',
            required_item_count=required,
            item_discount_percentage=Decimal(str(pct)),
        )

    def _account(self):
        return CustomerLoyaltyAccount.objects.create(
            customer=self.customer, is_active=True)

    def test_multiplier_2x_doubles_discount_percentage(self):
        """20 items at threshold 10, 5% each → 10% discount."""
        self._item_config(required=10, pct=5)
        acct = self._account()
        acct.item_count = 20
        acct.save()
        result = apply_count_based_discount(make_payment(10000), self.customer)
        self.assertIsNotNone(result)
        self.assertEqual(result['multiplier'], 2)
        self.assertEqual(result['discount_percentage'], Decimal('10'))

    def test_multiplier_3x_applies_correct_percentage(self):
        """30 items at threshold 10, 5% each → 15% discount."""
        self._item_config(required=10, pct=5)
        acct = self._account()
        acct.item_count = 30
        acct.save()
        result = apply_count_based_discount(make_payment(10000), self.customer)
        self.assertEqual(result['multiplier'], 3)
        self.assertEqual(result['discount_percentage'], Decimal('15'))

    def test_discount_capped_at_50_percent(self):
        """3× multiplier × 20% = 60% → capped at 50%."""
        self._item_config(required=10, pct=20)
        acct = self._account()
        acct.item_count = 30
        acct.save()
        result = apply_count_based_discount(make_payment(10000), self.customer)
        self.assertEqual(result['discount_percentage'], Decimal('50'))

    def test_discount_exactly_at_50_percent_cap_not_reduced(self):
        """2× × 25% = 50% → at cap exactly, no reduction."""
        self._item_config(required=10, pct=25)
        acct = self._account()
        acct.item_count = 20
        acct.save()
        result = apply_count_based_discount(make_payment(10000), self.customer)
        self.assertEqual(result['discount_percentage'], Decimal('50'))

    def test_remainder_stored_after_discount(self):
        """27 items, threshold 10 → 2× discount, 7 items remaining."""
        self._item_config(required=10, pct=5)
        acct = self._account()
        acct.item_count = 27
        acct.save()
        apply_count_based_discount(make_payment(10000), self.customer)
        acct.refresh_from_db()
        self.assertEqual(acct.item_count, 7)

    def test_remainder_zero_when_exactly_divisible(self):
        """20 items exactly (2× threshold) → 0 remainder."""
        self._item_config(required=10, pct=5)
        acct = self._account()
        acct.item_count = 20
        acct.save()
        apply_count_based_discount(make_payment(10000), self.customer)
        acct.refresh_from_db()
        self.assertEqual(acct.item_count, 0)

    def test_discount_amount_calculated_from_capped_percentage(self):
        """50% cap: discount_amount = 50% × payment_total."""
        self._item_config(required=10, pct=20)
        acct = self._account()
        acct.item_count = 30
        acct.save()
        result = apply_count_based_discount(make_payment(10000), self.customer)
        # 50% of 10000 = 5000
        self.assertEqual(result['discount_amount'], Decimal('5000'))

    def test_transaction_count_full_cycle_earn_apply_reset_earn(self):
        """Full cycle: reach threshold → discount applied → reset → re-earn."""
        make_loyalty_config(
            calculation_type='transaction_count_discount',
            required_transaction_count=3,
            transaction_discount_percentage=Decimal('10'),
        )
        acct = CustomerLoyaltyAccount.objects.create(
            customer=self.customer, is_active=True,
            transaction_count=3, discount_eligible=True,
        )
        # First application
        result1 = apply_count_based_discount(make_payment(10000), self.customer)
        self.assertIsNotNone(result1)
        acct.refresh_from_db()
        self.assertEqual(acct.transaction_count, 0)
        self.assertFalse(acct.discount_eligible)
        self.assertEqual(acct.discount_count, 1)

        # Not yet eligible again
        acct.transaction_count = 2
        acct.save()
        result2 = apply_count_based_discount(make_payment(10000), self.customer)
        self.assertIsNone(result2)

        # Reach threshold again
        acct.transaction_count = 3
        acct.discount_eligible = True
        acct.save()
        result3 = apply_count_based_discount(make_payment(10000), self.customer)
        self.assertIsNotNone(result3)
        acct.refresh_from_db()
        self.assertEqual(acct.discount_count, 2)


# ===========================================================================
# 29. Loyalty Points – Calculation Edge Cases
# ===========================================================================

class LoyaltyPointsCalculationEdgeCasesTests(TestCase):
    """
    LoyaltyConfiguration.calculate_points_earned():
    - per_transaction ignores amount (even zero)
    - per_amount truncates fractional units via int()
    - combined = per_transaction + per_amount
    - calculate_discount_from_points uses points_to_currency_rate
    - get_maximum_redeemable_amount is a percentage of transaction
    """

    def _config(self, **kw):
        defaults = dict(
            program_name='EdgePts',
            is_active=True,
            points_to_currency_rate=Decimal('1'),
            minimum_points_for_redemption=10,
            maximum_discount_percentage=Decimal('50'),
            send_welcome_email=False,
            send_points_earned_email=False,
            send_points_redeemed_email=False,
        )
        defaults.update(kw)
        return LoyaltyConfiguration.objects.create(**defaults)

    def test_per_transaction_ignores_zero_amount(self):
        config = self._config(calculation_type='per_transaction',
                              points_per_transaction=5)
        self.assertEqual(config.calculate_points_earned(Decimal('0')), 5)

    def test_per_transaction_ignores_large_amount(self):
        config = self._config(calculation_type='per_transaction',
                              points_per_transaction=3)
        self.assertEqual(config.calculate_points_earned(Decimal('999999')), 3)

    def test_per_amount_truncates_fractional_units(self):
        """750 / 500 = 1.5 units × 2 pts = 3.0 → int → 3 points."""
        config = self._config(calculation_type='per_amount',
                              points_per_currency_unit=Decimal('2'),
                              currency_unit_value=Decimal('500'))
        self.assertEqual(config.calculate_points_earned(Decimal('750')), 3)

    def test_per_amount_below_one_unit_gives_zero(self):
        """299 / 500 = 0.598 → int → 0 points."""
        config = self._config(calculation_type='per_amount',
                              points_per_currency_unit=Decimal('1'),
                              currency_unit_value=Decimal('500'))
        self.assertEqual(config.calculate_points_earned(Decimal('299')), 0)

    def test_per_amount_exactly_one_unit(self):
        config = self._config(calculation_type='per_amount',
                              points_per_currency_unit=Decimal('1'),
                              currency_unit_value=Decimal('500'))
        self.assertEqual(config.calculate_points_earned(Decimal('500')), 1)

    def test_combined_adds_transaction_plus_amount_points(self):
        """combined: 5 flat + floor(1000/200)*2 = 5 + 10 = 15 points."""
        config = self._config(calculation_type='combined',
                              points_per_transaction=5,
                              points_per_currency_unit=Decimal('2'),
                              currency_unit_value=Decimal('200'))
        self.assertEqual(config.calculate_points_earned(Decimal('1000')), 15)

    def test_calculate_discount_from_points_uses_rate(self):
        """10 points × rate 1.5 = 15 naira."""
        config = self._config(calculation_type='per_transaction',
                              points_per_transaction=1,
                              points_to_currency_rate=Decimal('1.5'))
        self.assertEqual(config.calculate_discount_from_points(10), Decimal('15.0'))

    def test_maximum_redeemable_amount_is_percentage_of_transaction(self):
        """50% cap on 10000 = 5000."""
        config = self._config(calculation_type='per_transaction',
                              points_per_transaction=1,
                              maximum_discount_percentage=Decimal('50'))
        self.assertEqual(
            config.get_maximum_redeemable_amount(Decimal('10000')),
            Decimal('5000'),
        )


# ===========================================================================
# 30. Loyalty Redemption – Boundary Conditions
# ===========================================================================

class LoyaltyRedemptionBoundaryTests(TestCase):
    """
    apply_loyalty_discount() boundary conditions:
    - points == minimum threshold (exact boundary) → success
    - points == one below minimum → rejected
    - discount == full transaction total (100% cap) → success
    - discount one unit over total → rejected
    - inactive config → error
    - non-unit currency rate applied correctly
    """

    def setUp(self):
        self.user = make_user()
        self.customer = make_customer()
        self.config = make_loyalty_config(
            points_to_currency_rate=Decimal('1'),
            minimum_points_for_redemption=100,
            maximum_discount_percentage=Decimal('100'),
        )
        self.account = CustomerLoyaltyAccount.objects.create(
            customer=self.customer, is_active=True)
        self.account.add_points(2000, 'load')
        self.receipt = Receipt.objects.create(user=self.user, customer=self.customer)
        Receipt.objects.filter(pk=self.receipt.pk).update(
            total_with_delivery=Decimal('1000'))
        self.receipt.refresh_from_db()

    def test_exact_minimum_points_succeeds(self):
        result = apply_loyalty_discount(self.receipt, 100)
        self.assertTrue(result['success'])

    def test_one_below_minimum_fails(self):
        result = apply_loyalty_discount(self.receipt, 99)
        self.assertFalse(result['success'])

    def test_discount_equals_full_transaction_total_succeeds(self):
        """100 cap: 1000 pts = 1000 naira = 100% of 1000 receipt."""
        result = apply_loyalty_discount(self.receipt, 1000)
        self.assertTrue(result['success'])
        self.assertEqual(result['discount_amount'], Decimal('1000'))

    def test_discount_one_over_total_fails(self):
        """1001 pts = 1001 naira > 1000 total → rejected."""
        self.account.add_points(8000, 'more')
        result = apply_loyalty_discount(self.receipt, 1001)
        self.assertFalse(result['success'])

    def test_inactive_loyalty_config_returns_error(self):
        """Deactivating the config is now correctly seen by apply_loyalty_discount."""
        self.config.is_active = False
        self.config.save()
        result = apply_loyalty_discount(self.receipt, 200)
        self.assertFalse(result['success'])
        self.assertIn('not active', result['error'])

    def test_remaining_balance_after_minimum_redemption(self):
        """After redeeming 100 from 2000 → 1900 remaining."""
        result = apply_loyalty_discount(self.receipt, 100)
        self.assertEqual(result['remaining_balance'], 1900)

    def test_non_unit_currency_rate_applied(self):
        """Rate of 2: 200 pts × 2 = 400 naira discount."""
        self.config.points_to_currency_rate = Decimal('2')
        self.config.save()
        result = apply_loyalty_discount(self.receipt, 200)
        self.assertTrue(result['success'])
        self.assertEqual(result['discount_amount'], Decimal('400'))


# ===========================================================================
# 31. Receipt – Tax Amount Before Tax & Mixed Tax Types
# ===========================================================================

class ReceiptTaxInteractionTests(TestCase):
    """
    Receipt.get_amount_before_tax() and tax totals with edge cases:
    - exclusive only: subtracts exclusive tax from total
    - inclusive only: total unchanged (inclusive already inside price)
    - both types together: only exclusive subtracted
    - None / malformed tax_details handled gracefully
    """

    def test_amount_before_exclusive_tax_subtracts_tax(self):
        details = json.dumps({'VAT': {'rate': 10, 'amount': 1000, 'method': 'exclusive'}})
        r = Receipt(tax_details=details, total_with_delivery=Decimal('11000'))
        self.assertEqual(r.get_amount_before_tax(), Decimal('10000'))

    def test_amount_before_inclusive_tax_unchanged(self):
        """Inclusive tax is already inside the price — no subtraction."""
        details = json.dumps({'VAT': {'rate': 7.5, 'amount': 750, 'method': 'inclusive'}})
        r = Receipt(tax_details=details, total_with_delivery=Decimal('10750'))
        self.assertEqual(r.get_amount_before_tax(), Decimal('10750'))

    def test_amount_before_tax_with_both_types_subtracts_only_exclusive(self):
        details = json.dumps({
            'VAT': {'rate': 7.5, 'amount': 750, 'method': 'inclusive'},
            'ST':  {'rate': 5,   'amount': 500, 'method': 'exclusive'},
        })
        r = Receipt(tax_details=details, total_with_delivery=Decimal('11250'))
        # Only 500 exclusive is subtracted → 10750
        self.assertEqual(r.get_amount_before_tax(), Decimal('10750'))

    def test_null_tax_details_inclusive_returns_zero(self):
        r = Receipt(tax_details=None)
        self.assertEqual(r.get_inclusive_tax_total(), Decimal('0'))

    def test_null_tax_details_exclusive_returns_zero(self):
        r = Receipt(tax_details=None)
        self.assertEqual(r.get_exclusive_tax_total(), Decimal('0'))

    def test_malformed_json_tax_details_returns_zeros(self):
        r = Receipt(tax_details='not valid json {{{')
        self.assertEqual(r.get_inclusive_tax_total(), Decimal('0'))
        self.assertEqual(r.get_exclusive_tax_total(), Decimal('0'))

    def test_both_tax_types_totalled_independently(self):
        details = json.dumps({
            'INC': {'rate': 5, 'amount': 200, 'method': 'inclusive'},
            'EXC': {'rate': 3, 'amount': 150, 'method': 'exclusive'},
        })
        r = Receipt(tax_details=details)
        self.assertEqual(r.get_inclusive_tax_total(), Decimal('200'))
        self.assertEqual(r.get_exclusive_tax_total(), Decimal('150'))

    def test_multiple_exclusive_taxes_summed(self):
        details = json.dumps({
            'VAT':  {'rate': 7.5, 'amount': 750,  'method': 'exclusive'},
            'LEVY': {'rate': 2.5, 'amount': 250, 'method': 'exclusive'},
        })
        r = Receipt(tax_details=details)
        self.assertEqual(r.get_exclusive_tax_total(), Decimal('1000'))


# ===========================================================================
# 32. Loyalty Transaction – balance_after Sequence
# ===========================================================================

class LoyaltyTransactionBalanceAfterTests(TestCase):
    """
    add_points() / redeem_points() create LoyaltyTransaction records.
    Verifies: balance accumulates correctly across a sequence of transactions,
    redeem_points returns False and creates no transaction when balance is insufficient.
    """

    def setUp(self):
        self.customer = make_customer()
        make_loyalty_config(
            points_to_currency_rate=Decimal('1'),
            minimum_points_for_redemption=10,
            maximum_discount_percentage=Decimal('50'),
        )
        self.account = CustomerLoyaltyAccount.objects.create(
            customer=self.customer, is_active=True)

    def test_first_earn_balance_is_correct(self):
        self.account.add_points(100, 'first earn')
        self.account.refresh_from_db()
        self.assertEqual(self.account.current_balance, 100)
        self.assertEqual(self.account.total_points_earned, 100)

    def test_sequential_earns_accumulate(self):
        self.account.add_points(50, 'earn 1')
        self.account.add_points(70, 'earn 2')
        self.account.refresh_from_db()
        self.assertEqual(self.account.current_balance, 120)
        self.assertEqual(self.account.total_points_earned, 120)

    def test_earn_then_redeem_balance_correct(self):
        self.account.add_points(200, 'earn')
        self.account.redeem_points(80, 'redeem')
        self.account.refresh_from_db()
        self.assertEqual(self.account.current_balance, 120)
        self.assertEqual(self.account.total_points_redeemed, 80)

    def test_transaction_records_created_for_each_operation(self):
        self.account.add_points(100, 'earn')
        self.account.redeem_points(30, 'redeem')
        count = LoyaltyTransaction.objects.filter(
            loyalty_account=self.account).count()
        self.assertEqual(count, 2)

    def test_earn_transaction_type_is_earned(self):
        self.account.add_points(50, 'earn')
        txn = LoyaltyTransaction.objects.filter(loyalty_account=self.account).first()
        self.assertEqual(txn.transaction_type, 'earned')

    def test_redeem_transaction_type_is_redeemed(self):
        self.account.add_points(100, 'earn')
        self.account.redeem_points(40, 'redeem')
        txn = LoyaltyTransaction.objects.filter(
            loyalty_account=self.account,
            transaction_type='redeemed',
        ).first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.points, 40)

    def test_redeem_returns_false_when_insufficient_balance(self):
        self.account.add_points(50, 'earn')
        result = self.account.redeem_points(100, 'too many')
        self.assertFalse(result)

    def test_failed_redeem_creates_no_transaction(self):
        self.account.add_points(50, 'earn')
        self.account.redeem_points(200, 'fail')
        self.assertEqual(
            LoyaltyTransaction.objects.filter(loyalty_account=self.account).count(), 1)

    def test_failed_redeem_leaves_balance_unchanged(self):
        self.account.add_points(50, 'earn')
        self.account.redeem_points(200, 'fail')
        self.account.refresh_from_db()
        self.assertEqual(self.account.current_balance, 50)

    def test_sequential_transactions_balance_after_increases(self):
        """Each earn transaction has a higher balance_after than the prior one."""
        self.account.add_points(50, 'earn 1')
        self.account.add_points(50, 'earn 2')
        txns = list(LoyaltyTransaction.objects.filter(
            loyalty_account=self.account).order_by('id'))
        self.assertGreater(txns[1].balance_after, txns[0].balance_after)


# ===========================================================================
# 33. Store Credit – Balance Aggregation
# ===========================================================================

class StoreCreditAggregationTests(TestCase):
    """
    Verifies Sum aggregation of StoreCredit.remaining_balance
    (mirrors store_credit_list view formula).
    """

    def setUp(self):
        from django.db.models import Sum
        self.Sum = Sum
        self.user = make_user()
        self.customer = make_customer()

    def _make_credit(self, amount, is_active=True):
        return StoreCredit.objects.create(
            customer=self.customer,
            original_amount=Decimal(str(amount)),
            remaining_balance=Decimal(str(amount)),
            is_active=is_active,
            issued_by=self.user,
        )

    def test_total_balance_sums_active_credits(self):
        self._make_credit(500)
        self._make_credit(300)
        total = (StoreCredit.objects
                 .filter(is_active=True)
                 .aggregate(total=self.Sum('remaining_balance'))['total'] or 0)
        self.assertEqual(total, Decimal('800'))

    def test_inactive_credits_excluded(self):
        self._make_credit(500, is_active=True)
        self._make_credit(200, is_active=False)
        total = (StoreCredit.objects
                 .filter(is_active=True)
                 .aggregate(total=self.Sum('remaining_balance'))['total'] or 0)
        self.assertEqual(total, Decimal('500'))

    def test_no_credits_returns_zero_not_none(self):
        total = (StoreCredit.objects
                 .filter(is_active=True)
                 .aggregate(total=self.Sum('remaining_balance'))['total'] or 0)
        self.assertEqual(total, 0)

    def test_single_credit_total_equals_its_balance(self):
        self._make_credit(750)
        total = (StoreCredit.objects
                 .filter(is_active=True)
                 .aggregate(total=self.Sum('remaining_balance'))['total'] or 0)
        self.assertEqual(total, Decimal('750'))


# ===========================================================================
# 34. Report View Aggregation Tests (integration)
# ===========================================================================

class ReportAggregationViewTests(TestCase):
    """
    Integration tests: hit financial_report, discount_report, and
    inventory_report with real DB data and assert correct aggregate values
    in the response context.

    All three views default to today's date when no date params are given,
    so test data created during the run is always included.
    """

    def setUp(self):
        self.md_user = User.objects.create_user(
            'report_md_user', password='pass', is_staff=True
        )
        UserProfile.objects.create(user=self.md_user, access_level='md')
        self.client.force_login(self.md_user)

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _make_sale(self, price=10000, markup=10, qty=2, discount=None, brand=None):
        """Create Product → Receipt → Payment → Sale; return (sale, payment)."""
        kwargs = dict(price=price, markup=markup, markup_type='percentage',
                      quantity=qty + 10)
        if brand:
            kwargs['brand'] = brand
        p = make_product(**kwargs)
        r = Receipt.objects.create(user=self.md_user)
        pay = Payment.objects.create()
        sale_kwargs = dict(product=p, quantity=qty, receipt=r, payment=pay)
        if discount is not None:
            sale_kwargs['discount_amount'] = Decimal(str(discount))
        s = Sale.objects.create(**sale_kwargs)
        pay.save()
        return s, pay

    # ------------------------------------------------------------------
    # financial_report
    # ------------------------------------------------------------------

    def test_financial_report_gross_revenue(self):
        """gross_revenue = selling_price * qty (price=10000, markup=10% → 11000 * 2 = 22000)."""
        self._make_sale(price=10000, markup=10, qty=2)
        resp = self.client.get(reverse('financial_report'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['gross_revenue'], Decimal('22000.00'))

    def test_financial_report_total_cost(self):
        """total_cost = cost_price * qty (10000 * 2 = 20000)."""
        self._make_sale(price=10000, markup=10, qty=2)
        resp = self.client.get(reverse('financial_report'))
        self.assertEqual(resp.context['total_cost'], Decimal('20000.00'))

    def test_financial_report_total_revenue_equals_payment_total(self):
        """total_revenue aggregates payment.total_amount; equals sale total when no discount."""
        self._make_sale(price=10000, markup=10, qty=2)
        resp = self.client.get(reverse('financial_report'))
        self.assertEqual(resp.context['total_revenue'], Decimal('22000.00'))

    def test_financial_report_no_sales_returns_zero(self):
        """With no sales today, all revenue/cost metrics are zero."""
        resp = self.client.get(reverse('financial_report'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['gross_revenue'], Decimal('0'))
        self.assertEqual(resp.context['total_revenue'], Decimal('0'))
        self.assertEqual(resp.context['total_cost'], Decimal('0'))

    # ------------------------------------------------------------------
    # discount_report
    # ------------------------------------------------------------------

    def test_discount_report_line_discount_total(self):
        """line_discount_total = sum of Sale.discount_amount for today's discounted sales."""
        self._make_sale(price=10000, markup=10, qty=2, discount=500)
        resp = self.client.get(reverse('discount_report'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['line_discount_total'], Decimal('500.00'))
        self.assertEqual(resp.context['line_transactions'], 1)

    def test_discount_report_payment_discount_total(self):
        """payment_discount_total = sum of Payment.discount_amount for today's discounted payments."""
        _, pay = self._make_sale(price=10000, markup=10, qty=1, brand='Disc Pay Product')
        Payment.objects.filter(pk=pay.pk).update(discount_amount=Decimal('300.00'))
        resp = self.client.get(reverse('discount_report'))
        self.assertEqual(resp.context['payment_discount_total'], Decimal('300.00'))
        self.assertEqual(resp.context['payment_transactions'], 1)

    def test_discount_report_total_is_line_plus_payment(self):
        """total_discount_amount = line_discount_total + payment_discount_total."""
        self._make_sale(price=10000, markup=10, qty=2, discount=500, brand='Line Disc')
        _, pay2 = self._make_sale(price=5000, markup=20, qty=1, brand='Pay Disc')
        Payment.objects.filter(pk=pay2.pk).update(discount_amount=Decimal('200.00'))
        resp = self.client.get(reverse('discount_report'))
        self.assertEqual(
            resp.context['total_discount_amount'],
            resp.context['line_discount_total'] + resp.context['payment_discount_total'],
        )

    def test_discount_report_no_discounts_returns_zero(self):
        """With no discounts applied, all totals are zero."""
        self._make_sale(price=5000, markup=20, qty=1)
        resp = self.client.get(reverse('discount_report'))
        self.assertEqual(resp.context['total_discount_amount'], 0)
        self.assertEqual(resp.context['total_transactions'], 0)

    # ------------------------------------------------------------------
    # inventory_report
    # ------------------------------------------------------------------

    def test_inventory_report_total_value(self):
        """total_value = selling_price * quantity (11000 * 20 = 220000)."""
        make_product(price=10000, markup=10, markup_type='percentage', quantity=20)
        resp = self.client.get(reverse('inventory_report'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_value'], Decimal('220000.00'))

    def test_inventory_report_potential_profit(self):
        """potential_profit = total_value - total_cost_value (220000 - 200000 = 20000)."""
        make_product(price=10000, markup=10, markup_type='percentage', quantity=20)
        resp = self.client.get(reverse('inventory_report'))
        self.assertEqual(resp.context['total_cost_value'], Decimal('200000.00'))
        self.assertEqual(resp.context['potential_profit'], Decimal('20000.00'))

    def test_inventory_report_low_and_critical_stock_counts(self):
        """low_stock_count = qty<10; critical_stock_count = qty<5."""
        make_product(brand='Critical Item', price=5000, markup=10,
                     markup_type='percentage', quantity=3)   # critical (qty<5) and low (qty<10)
        make_product(brand='Low Only Item', price=5000, markup=10,
                     markup_type='percentage', quantity=7)   # low (qty<10), not critical
        make_product(brand='Normal Item', price=5000, markup=10,
                     markup_type='percentage', quantity=20)  # neither
        resp = self.client.get(reverse('inventory_report'))
        self.assertEqual(resp.context['low_stock_count'], 2)
        self.assertEqual(resp.context['critical_stock_count'], 1)

    def test_inventory_report_no_products_returns_zero(self):
        """With no products, value and profit metrics are zero."""
        resp = self.client.get(reverse('inventory_report'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_value'], Decimal('0'))
        self.assertEqual(resp.context['potential_profit'], Decimal('0'))


# ── Class 35: Service Layer Pure Unit Tests ─────────────────────────────────
class ServiceLayerTests(TestCase):
    """Pure unit tests for store/services.py — no DB required."""
    databases = set()  # No DB access needed

    def test_clamp_discount_clamped_when_above_item_total(self):
        from store.services import clamp_discount
        result = clamp_discount(Decimal('50.00'), Decimal('30.00'))
        self.assertEqual(result, Decimal('30.00'))

    def test_clamp_discount_unchanged_when_below_item_total(self):
        from store.services import clamp_discount
        result = clamp_discount(Decimal('10.00'), Decimal('30.00'))
        self.assertEqual(result, Decimal('10.00'))

    def test_clamp_discount_zero_when_none(self):
        from store.services import clamp_discount
        result = clamp_discount(None, Decimal('30.00'))
        self.assertEqual(result, Decimal('0'))

    def test_sale_line_total_no_discount(self):
        from store.services import calculate_sale_line_total
        result = calculate_sale_line_total(Decimal('10.00'), 3, None)
        self.assertEqual(result, Decimal('30.00'))

    def test_sale_line_total_with_discount(self):
        from store.services import calculate_sale_line_total
        result = calculate_sale_line_total(Decimal('10.00'), 3, Decimal('5.00'))
        self.assertEqual(result, Decimal('25.00'))

    def test_determine_status_completed_when_fully_paid(self):
        from store.services import determine_payment_status
        status, balance, completed_date = determine_payment_status(Decimal('100.00'), Decimal('100.00'))
        self.assertEqual(status, 'completed')
        self.assertEqual(balance, Decimal('0'))
        self.assertIsNotNone(completed_date)

    def test_determine_status_partial_when_partly_paid(self):
        from store.services import determine_payment_status
        status, balance, completed_date = determine_payment_status(Decimal('100.00'), Decimal('50.00'))
        self.assertEqual(status, 'partial')
        self.assertEqual(balance, Decimal('50.00'))
        self.assertIsNone(completed_date)

    def test_determine_status_pending_when_nothing_paid(self):
        from store.services import determine_payment_status
        status, balance, completed_date = determine_payment_status(Decimal('100.00'), Decimal('0'))
        self.assertEqual(status, 'pending')
        self.assertEqual(balance, Decimal('100.00'))
        self.assertIsNone(completed_date)


# ===========================================================================
# 36. Role Permissions Utility Tests
# ===========================================================================

class RolePermissionsUtilityTests(TestCase):
    """Unit tests for store/role_permissions.py helper functions."""

    # ── access_level_for_role ──────────────────────────────────────────────

    def test_access_level_md_variants(self):
        from store.role_permissions import access_level_for_role
        for name in ('MD', 'md', 'Managing Director', 'Manager'):
            with self.subTest(name=name):
                self.assertEqual(access_level_for_role(name), 'md')

    def test_access_level_cashier(self):
        from store.role_permissions import access_level_for_role
        self.assertEqual(access_level_for_role('Cashier'), 'cashier')
        self.assertEqual(access_level_for_role('cashier'), 'cashier')

    def test_access_level_accountant(self):
        from store.role_permissions import access_level_for_role
        self.assertEqual(access_level_for_role('Accountant'), 'accountant')

    def test_access_level_unknown_defaults_to_cashier(self):
        from store.role_permissions import access_level_for_role
        for name in ('Warehouse Staff', '', 'Random Role', '   '):
            with self.subTest(name=name):
                self.assertEqual(access_level_for_role(name), 'cashier')

    # ── get_grouped_permissions ────────────────────────────────────────────

    def test_get_grouped_permissions_returns_non_empty_list(self):
        from store.role_permissions import get_grouped_permissions
        groups = get_grouped_permissions()
        self.assertIsInstance(groups, list)
        self.assertGreater(len(groups), 0)

    def test_each_group_has_all_required_keys(self):
        from store.role_permissions import get_grouped_permissions
        required = (
            'display_name', 'category',
            'view_key', 'view_label', 'view_perms',
            'edit_key', 'edit_label', 'edit_perms',
            'delete_key', 'delete_label', 'delete_perms',
        )
        for group in get_grouped_permissions():
            for key in required:
                with self.subTest(group=group['display_name'], key=key):
                    self.assertIn(key, group)

    def test_view_label_says_can_view_and_create(self):
        from store.role_permissions import get_grouped_permissions
        for group in get_grouped_permissions():
            self.assertIn('Can View & Create', group['view_label'])

    def test_edit_label_says_can_edit(self):
        from store.role_permissions import get_grouped_permissions
        for group in get_grouped_permissions():
            self.assertIn('Can Edit', group['edit_label'])

    def test_delete_label_says_can_delete(self):
        from store.role_permissions import get_grouped_permissions
        for group in get_grouped_permissions():
            self.assertIn('Can Delete', group['delete_label'])

    # ── get_permissions_from_post ──────────────────────────────────────────

    def test_empty_post_returns_no_permissions(self):
        from store.role_permissions import get_grouped_permissions, get_permissions_from_post
        groups = get_grouped_permissions()
        self.assertEqual(get_permissions_from_post({}, groups), [])

    def test_view_key_in_post_selects_view_perms(self):
        from store.role_permissions import get_grouped_permissions, get_permissions_from_post
        groups = get_grouped_permissions()
        first = next((g for g in groups if g['view_perms']), None)
        if not first:
            return
        selected_ids = {p.id for p in get_permissions_from_post({first['view_key']: '1'}, groups)}
        expected_ids = {p.id for p in first['view_perms']}
        self.assertTrue(expected_ids.issubset(selected_ids))

    def test_edit_key_in_post_selects_edit_perms(self):
        from store.role_permissions import get_grouped_permissions, get_permissions_from_post
        groups = get_grouped_permissions()
        first = next((g for g in groups if g['edit_perms']), None)
        if not first:
            return
        selected_ids = {p.id for p in get_permissions_from_post({first['edit_key']: '1'}, groups)}
        expected_ids = {p.id for p in first['edit_perms']}
        self.assertTrue(expected_ids.issubset(selected_ids))

    def test_delete_key_in_post_selects_delete_perms(self):
        from store.role_permissions import get_grouped_permissions, get_permissions_from_post
        groups = get_grouped_permissions()
        first = next((g for g in groups if g['delete_perms']), None)
        if not first:
            return
        selected_ids = {p.id for p in get_permissions_from_post({first['delete_key']: '1'}, groups)}
        expected_ids = {p.id for p in first['delete_perms']}
        self.assertTrue(expected_ids.issubset(selected_ids))

    def test_only_checked_keys_are_included(self):
        from store.role_permissions import get_grouped_permissions, get_permissions_from_post
        groups = get_grouped_permissions()
        if len(groups) < 2:
            return
        first, second = groups[0], groups[1]
        # Only post the first group's view key
        post = {first['view_key']: '1'}
        selected_ids = {p.id for p in get_permissions_from_post(post, groups)}
        # Second group's perms should NOT be included
        second_all_ids = (
            {p.id for p in second['view_perms']} |
            {p.id for p in second['edit_perms']} |
            {p.id for p in second['delete_perms']}
        )
        self.assertFalse(second_all_ids & selected_ids)

    # ── get_checked_keys_for_group ─────────────────────────────────────────

    def test_checked_keys_reflect_group_view_permissions(self):
        from django.contrib.auth.models import Group as DjangoGroup
        from store.role_permissions import get_grouped_permissions, get_checked_keys_for_group
        groups = get_grouped_permissions()
        first = next((g for g in groups if g['view_perms']), None)
        if not first:
            return
        role = DjangoGroup.objects.create(name='_TestCheckedView')
        role.permissions.set(first['view_perms'])
        checked = get_checked_keys_for_group(role, groups)
        self.assertIn(first['view_key'], checked)
        self.assertNotIn(first['delete_key'], checked)

    def test_checked_keys_empty_for_group_with_no_permissions(self):
        from django.contrib.auth.models import Group as DjangoGroup
        from store.role_permissions import get_grouped_permissions, get_checked_keys_for_group
        groups = get_grouped_permissions()
        role = DjangoGroup.objects.create(name='_TestCheckedEmpty')
        checked = get_checked_keys_for_group(role, groups)
        self.assertEqual(len(checked), 0)

    def test_all_three_keys_checked_when_all_perms_assigned(self):
        from django.contrib.auth.models import Group as DjangoGroup
        from store.role_permissions import get_grouped_permissions, get_checked_keys_for_group
        groups = get_grouped_permissions()
        first = next((
            g for g in groups
            if g['view_perms'] and g['edit_perms'] and g['delete_perms']
        ), None)
        if not first:
            return
        role = DjangoGroup.objects.create(name='_TestCheckedAll')
        role.permissions.set(
            first['view_perms'] + first['edit_perms'] + first['delete_perms']
        )
        checked = get_checked_keys_for_group(role, groups)
        self.assertIn(first['view_key'], checked)
        self.assertIn(first['edit_key'], checked)
        self.assertIn(first['delete_key'], checked)

    # ── group_permissions_by_category ─────────────────────────────────────

    def test_category_grouping_returns_ordered_dict(self):
        from collections import OrderedDict
        from store.role_permissions import get_grouped_permissions, group_permissions_by_category
        categorized = group_permissions_by_category(get_grouped_permissions())
        self.assertIsInstance(categorized, OrderedDict)

    def test_each_item_belongs_to_its_category(self):
        from store.role_permissions import get_grouped_permissions, group_permissions_by_category
        categorized = group_permissions_by_category(get_grouped_permissions())
        for cat, items in categorized.items():
            for item in items:
                self.assertEqual(item['category'], cat)


# ===========================================================================
# 37. Role Management View Tests
# ===========================================================================

class RoleViewTests(TestCase):
    """View-level tests for list_roles, create_role, edit_role, delete_role."""

    def setUp(self):
        self.md = User.objects.create_user('rv_md', password='pass', is_staff=True)
        UserProfile.objects.create(user=self.md, access_level='md')
        self.cashier = User.objects.create_user('rv_cashier', password='pass', is_staff=False)
        UserProfile.objects.create(user=self.cashier, access_level='cashier')

    # ── Access control ─────────────────────────────────────────────────────

    def test_list_roles_requires_login(self):
        self.assertEqual(self.client.get(reverse('list_roles')).status_code, 302)

    def test_list_roles_rejects_cashier(self):
        self.client.force_login(self.cashier)
        r = self.client.get(reverse('list_roles'))
        self.assertEqual(r.status_code, 302)
        self.assertIn('/access-denied/', r.url)

    def test_list_roles_allows_md(self):
        self.client.force_login(self.md)
        self.assertEqual(self.client.get(reverse('list_roles')).status_code, 200)

    def test_create_role_get_allows_md(self):
        self.client.force_login(self.md)
        self.assertEqual(self.client.get(reverse('create_role')).status_code, 200)

    def test_create_role_rejects_cashier(self):
        self.client.force_login(self.cashier)
        r = self.client.get(reverse('create_role'))
        self.assertIn('/access-denied/', r.url)

    def test_edit_role_rejects_cashier(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role = DjangoGroup.objects.create(name='_rv_edit_cashier')
        self.client.force_login(self.cashier)
        r = self.client.get(reverse('edit_role', args=[role.id]))
        self.assertIn('/access-denied/', r.url)

    # ── Create role ────────────────────────────────────────────────────────

    def test_create_role_makes_django_group(self):
        from django.contrib.auth.models import Group as DjangoGroup
        self.client.force_login(self.md)
        self.client.post(reverse('create_role'), {'role_name': 'Supervisor'})
        self.assertTrue(DjangoGroup.objects.filter(name='Supervisor').exists())

    def test_create_role_assigns_view_permissions(self):
        from django.contrib.auth.models import Group as DjangoGroup
        from store.role_permissions import get_grouped_permissions
        groups = get_grouped_permissions()
        first = next((g for g in groups if g['view_perms']), None)
        if not first:
            return
        self.client.force_login(self.md)
        self.client.post(reverse('create_role'), {'role_name': '_rv_perm', first['view_key']: '1'})
        role = DjangoGroup.objects.get(name='_rv_perm')
        assigned = set(role.permissions.values_list('id', flat=True))
        expected = {p.id for p in first['view_perms']}
        self.assertTrue(expected.issubset(assigned))

    def test_create_role_assigns_edit_permissions(self):
        from django.contrib.auth.models import Group as DjangoGroup
        from store.role_permissions import get_grouped_permissions
        groups = get_grouped_permissions()
        first = next((g for g in groups if g['edit_perms']), None)
        if not first:
            return
        self.client.force_login(self.md)
        self.client.post(reverse('create_role'), {'role_name': '_rv_edit_perm', first['edit_key']: '1'})
        role = DjangoGroup.objects.get(name='_rv_edit_perm')
        assigned = set(role.permissions.values_list('id', flat=True))
        expected = {p.id for p in first['edit_perms']}
        self.assertTrue(expected.issubset(assigned))

    def test_create_role_rejects_duplicate_name(self):
        from django.contrib.auth.models import Group as DjangoGroup
        DjangoGroup.objects.create(name='_rv_dupe')
        self.client.force_login(self.md)
        self.client.post(reverse('create_role'), {'role_name': '_rv_dupe'})
        self.assertEqual(DjangoGroup.objects.filter(name='_rv_dupe').count(), 1)

    def test_create_role_empty_name_does_not_create_group(self):
        from django.contrib.auth.models import Group as DjangoGroup
        count_before = DjangoGroup.objects.count()
        self.client.force_login(self.md)
        self.client.post(reverse('create_role'), {'role_name': ''})
        self.assertEqual(DjangoGroup.objects.count(), count_before)

    def test_create_role_redirects_to_list_roles(self):
        self.client.force_login(self.md)
        r = self.client.post(reverse('create_role'), {'role_name': '_rv_redirect'})
        self.assertRedirects(r, reverse('list_roles'))

    # ── Edit role ──────────────────────────────────────────────────────────

    def test_edit_role_updates_name(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role = DjangoGroup.objects.create(name='_rv_old')
        self.client.force_login(self.md)
        self.client.post(reverse('edit_role', args=[role.id]), {'role_name': '_rv_new'})
        role.refresh_from_db()
        self.assertEqual(role.name, '_rv_new')

    def test_edit_role_replaces_permissions(self):
        from django.contrib.auth.models import Group as DjangoGroup
        from store.role_permissions import get_grouped_permissions
        groups = get_grouped_permissions()
        first = next((g for g in groups if g['view_perms']), None)
        second = next((g for g in groups if g['delete_perms'] and g is not first), None)
        if not first or not second:
            return
        role = DjangoGroup.objects.create(name='_rv_replace_perms')
        role.permissions.set(first['view_perms'])
        self.client.force_login(self.md)
        self.client.post(
            reverse('edit_role', args=[role.id]),
            {'role_name': '_rv_replace_perms', second['delete_key']: '1'},
        )
        role.refresh_from_db()
        assigned = set(role.permissions.values_list('id', flat=True))
        self.assertTrue({p.id for p in second['delete_perms']}.issubset(assigned))
        self.assertFalse({p.id for p in first['view_perms']}.issubset(assigned))

    def test_edit_role_duplicate_name_blocked(self):
        from django.contrib.auth.models import Group as DjangoGroup
        DjangoGroup.objects.create(name='_rv_taken')
        role = DjangoGroup.objects.create(name='_rv_original')
        self.client.force_login(self.md)
        self.client.post(reverse('edit_role', args=[role.id]), {'role_name': '_rv_taken'})
        role.refresh_from_db()
        self.assertEqual(role.name, '_rv_original')

    # ── Delete role ────────────────────────────────────────────────────────

    def test_delete_role_removes_custom_role(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role = DjangoGroup.objects.create(name='_rv_custom_delete')
        self.client.force_login(self.md)
        self.client.post(reverse('delete_role', args=[role.id]))
        self.assertFalse(DjangoGroup.objects.filter(name='_rv_custom_delete').exists())

    def test_delete_role_blocks_md_system_role(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role, _ = DjangoGroup.objects.get_or_create(name='MD')
        self.client.force_login(self.md)
        self.client.post(reverse('delete_role', args=[role.id]))
        self.assertTrue(DjangoGroup.objects.filter(name='MD').exists())

    def test_delete_role_blocks_cashier_system_role(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role, _ = DjangoGroup.objects.get_or_create(name='Cashier')
        self.client.force_login(self.md)
        self.client.post(reverse('delete_role', args=[role.id]))
        self.assertTrue(DjangoGroup.objects.filter(name='Cashier').exists())

    def test_delete_role_blocks_accountant_system_role(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role, _ = DjangoGroup.objects.get_or_create(name='Accountant')
        self.client.force_login(self.md)
        self.client.post(reverse('delete_role', args=[role.id]))
        self.assertTrue(DjangoGroup.objects.filter(name='Accountant').exists())


# ===========================================================================
# 38. Create User RBAC Tests
# ===========================================================================

class CreateUserRbacTests(TestCase):
    """Tests for role assignment and admin toggle in the create_user view."""

    def setUp(self):
        self.md = User.objects.create_user('cu_md', password='pass', is_staff=True)
        UserProfile.objects.create(user=self.md, access_level='md')

    def _post(self, extra=None):
        data = {
            'username': 'cu_newuser',
            'password1': 'ComplexPass99!',
            'password2': 'ComplexPass99!',
        }
        if extra:
            data.update(extra)
        self.client.force_login(self.md)
        return self.client.post(reverse('create_user'), data)

    def test_create_user_with_role_assigns_that_group(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role = DjangoGroup.objects.create(name='_cu_sales')
        self._post({'role_id': role.id})
        user = User.objects.get(username='cu_newuser')
        self.assertIn(role, user.groups.all())

    def test_create_user_with_cashier_role_sets_cashier_access_level(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role, _ = DjangoGroup.objects.get_or_create(name='Cashier')
        self._post({'role_id': role.id})
        self.assertEqual(User.objects.get(username='cu_newuser').profile.access_level, 'cashier')

    def test_create_user_with_md_role_sets_md_access_level(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role, _ = DjangoGroup.objects.get_or_create(name='MD')
        self._post({'role_id': role.id})
        self.assertEqual(User.objects.get(username='cu_newuser').profile.access_level, 'md')

    def test_create_user_with_md_role_grants_staff_flag(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role, _ = DjangoGroup.objects.get_or_create(name='MD')
        self._post({'role_id': role.id})
        self.assertTrue(User.objects.get(username='cu_newuser').is_staff)

    def test_create_user_unknown_role_defaults_access_level_cashier(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role = DjangoGroup.objects.create(name='_cu_warehouse')
        self._post({'role_id': role.id})
        self.assertEqual(User.objects.get(username='cu_newuser').profile.access_level, 'cashier')

    def test_create_user_no_role_defaults_access_level_cashier(self):
        self._post()
        self.assertEqual(User.objects.get(username='cu_newuser').profile.access_level, 'cashier')

    def test_create_admin_sets_is_superuser(self):
        self._post({'is_admin': 'on'})
        self.assertTrue(User.objects.get(username='cu_newuser').is_superuser)

    def test_create_admin_sets_is_staff(self):
        self._post({'is_admin': 'on'})
        self.assertTrue(User.objects.get(username='cu_newuser').is_staff)

    def test_create_admin_sets_access_level_md(self):
        self._post({'is_admin': 'on'})
        self.assertEqual(User.objects.get(username='cu_newuser').profile.access_level, 'md')

    def test_create_admin_without_role_succeeds(self):
        """Admin flag must not require a role_id to create successfully."""
        self._post({'is_admin': 'on'})
        self.assertTrue(User.objects.filter(username='cu_newuser').exists())

    def test_create_user_redirects_to_list_users(self):
        r = self._post()
        self.assertRedirects(r, reverse('list_users'))

    def test_non_admin_user_is_not_superuser(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role = DjangoGroup.objects.create(name='_cu_normal')
        self._post({'role_id': role.id})
        self.assertFalse(User.objects.get(username='cu_newuser').is_superuser)


# ===========================================================================
# 39. Edit User RBAC Tests
# ===========================================================================

class EditUserRbacTests(TestCase):
    """Tests for role dropdown pre-population and saving in edit_user view."""

    def setUp(self):
        self.md = User.objects.create_user('eu_md', password='pass', is_staff=True)
        UserProfile.objects.create(user=self.md, access_level='md')
        self.target = User.objects.create_user(
            'eu_target', password='pass',
            first_name='Edit', last_name='Target', email='edit@example.com',
        )
        UserProfile.objects.create(user=self.target, access_level='cashier')

    def _post_edit(self, extra=None):
        data = {
            'username': self.target.username,
            'first_name': 'Edit',
            'last_name': 'Target',
            'email': 'edit@example.com',
            'is_active': 'on',
            'access_level': 'cashier',
            'phone_number': '',
            'is_active_staff': 'on',
        }
        if extra:
            data.update(extra)
        self.client.force_login(self.md)
        return self.client.post(reverse('edit_user', args=[self.target.id]), data)

    def test_edit_user_get_passes_all_roles_to_context(self):
        from django.contrib.auth.models import Group as DjangoGroup
        r1 = DjangoGroup.objects.create(name='_eu_roleA')
        r2 = DjangoGroup.objects.create(name='_eu_roleB')
        self.client.force_login(self.md)
        response = self.client.get(reverse('edit_user', args=[self.target.id]))
        self.assertEqual(response.status_code, 200)
        role_ids = [r.id for r in response.context['all_roles']]
        self.assertIn(r1.id, role_ids)
        self.assertIn(r2.id, role_ids)

    def test_edit_user_get_pre_selects_current_role(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role = DjangoGroup.objects.create(name='_eu_current')
        self.target.groups.add(role)
        self.client.force_login(self.md)
        response = self.client.get(reverse('edit_user', args=[self.target.id]))
        self.assertEqual(response.context['current_role'].id, role.id)

    def test_edit_user_get_current_role_none_when_no_group(self):
        self.client.force_login(self.md)
        response = self.client.get(reverse('edit_user', args=[self.target.id]))
        self.assertIsNone(response.context['current_role'])

    def test_edit_user_changes_assigned_group(self):
        from django.contrib.auth.models import Group as DjangoGroup
        old = DjangoGroup.objects.create(name='_eu_old')
        new = DjangoGroup.objects.create(name='_eu_new')
        self.target.groups.add(old)
        self._post_edit({'role_id': new.id})
        self.target.refresh_from_db()
        self.assertIn(new, self.target.groups.all())
        self.assertNotIn(old, self.target.groups.all())

    def test_edit_user_syncs_access_level_from_new_role(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role, _ = DjangoGroup.objects.get_or_create(name='MD')
        self._post_edit({'role_id': role.id})
        self.target.profile.refresh_from_db()
        self.assertEqual(self.target.profile.access_level, 'md')

    def test_edit_user_md_role_grants_staff_flag(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role, _ = DjangoGroup.objects.get_or_create(name='MD')
        self._post_edit({'role_id': role.id})
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_staff)

    def test_edit_user_unknown_role_defaults_cashier(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role = DjangoGroup.objects.create(name='_eu_unknown')
        self._post_edit({'role_id': role.id})
        self.target.profile.refresh_from_db()
        self.assertEqual(self.target.profile.access_level, 'cashier')

    def test_edit_user_redirects_to_list_users(self):
        from django.contrib.auth.models import Group as DjangoGroup
        role = DjangoGroup.objects.create(name='_eu_redir')
        r = self._post_edit({'role_id': role.id})
        self.assertRedirects(r, reverse('list_users'))


# ===========================================================================
# 40. List Users View Tests
# ===========================================================================

class ListUsersViewTests(TestCase):
    """Tests for the list_users view."""

    def setUp(self):
        self.md = User.objects.create_user('lu_md', password='pass', is_staff=True)
        UserProfile.objects.create(user=self.md, access_level='md')
        self.cashier = User.objects.create_user('lu_cashier', password='pass')
        UserProfile.objects.create(user=self.cashier, access_level='cashier')

    def test_list_users_requires_login(self):
        self.assertEqual(self.client.get(reverse('list_users')).status_code, 302)

    def test_list_users_rejects_cashier(self):
        self.client.force_login(self.cashier)
        r = self.client.get(reverse('list_users'))
        self.assertEqual(r.status_code, 302)
        self.assertIn('/access-denied/', r.url)

    def test_list_users_allows_md(self):
        self.client.force_login(self.md)
        self.assertEqual(self.client.get(reverse('list_users')).status_code, 200)

    def test_list_users_contains_all_users(self):
        self.client.force_login(self.md)
        response = self.client.get(reverse('list_users'))
        usernames = [u.username for u in response.context['users']]
        self.assertIn('lu_md', usernames)
        self.assertIn('lu_cashier', usernames)

    def test_search_by_username_filters_correctly(self):
        self.client.force_login(self.md)
        r = self.client.get(reverse('list_users'), {'search': 'lu_cashier'})
        usernames = [u.username for u in r.context['users']]
        self.assertIn('lu_cashier', usernames)
        self.assertNotIn('lu_md', usernames)

    def test_search_by_first_name_filters_correctly(self):
        self.cashier.first_name = 'Alice'
        self.cashier.save()
        self.client.force_login(self.md)
        r = self.client.get(reverse('list_users'), {'search': 'Alice'})
        usernames = [u.username for u in r.context['users']]
        self.assertIn('lu_cashier', usernames)
        self.assertNotIn('lu_md', usernames)

    def test_search_by_last_name_filters_correctly(self):
        self.md.last_name = 'Director'
        self.md.save()
        self.client.force_login(self.md)
        r = self.client.get(reverse('list_users'), {'search': 'Director'})
        usernames = [u.username for u in r.context['users']]
        self.assertIn('lu_md', usernames)
        self.assertNotIn('lu_cashier', usernames)

    def test_empty_search_returns_all_users(self):
        self.client.force_login(self.md)
        r = self.client.get(reverse('list_users'), {'search': ''})
        self.assertGreaterEqual(len(r.context['users']), 2)

    def test_nonmatching_search_returns_empty(self):
        self.client.force_login(self.md)
        r = self.client.get(reverse('list_users'), {'search': 'zzznomatch999'})
        self.assertEqual(len(r.context['users']), 0)

    def test_search_query_passed_back_to_context(self):
        self.client.force_login(self.md)
        r = self.client.get(reverse('list_users'), {'search': 'lu_md'})
        self.assertEqual(r.context['search_query'], 'lu_md')
