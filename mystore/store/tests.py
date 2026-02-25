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

    def test_payment_discount_amount_written_back_by_receipt(self):
        """
        Receipt.calculate_total() writes Payment.discount_amount via queryset
        update so both objects agree on the discount.
        """
        receipt = Receipt.objects.create(user=self.user)
        payment = Payment.objects.create(discount_percentage=Decimal('10'))
        Sale.objects.create(product=self.product, quantity=1,
                            receipt=receipt, payment=payment)
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

    def test_get_active_config_creates_default_when_none_exist(self):
        self.assertEqual(LoyaltyConfiguration.objects.count(), 0)
        config = LoyaltyConfiguration.get_active_config()
        self.assertIsNotNone(config)
        self.assertTrue(config.is_active)

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

    def test_deactivating_config_allows_new_default_creation(self):
        c = make_loyalty_config()
        c.is_active = False
        c.save()
        # get_active_config creates a fresh default since none are active
        new_config = LoyaltyConfiguration.get_active_config()
        self.assertTrue(new_config.is_active)

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
