# Implementation Plan: Gift & Partial Payment in POS

## Overview
Restore the accidentally overridden gift and partial payment features to the POS system.

## Current State
✅ Models exist and are ready:
- `Sale.is_gift`, `Sale.gift_reason`, `Sale.original_value`
- `Receipt.amount_paid`, `Receipt.balance_remaining`, `Receipt.payment_status`
- `PartialPayment` model

✅ Backend views exist:
- `add_partial_payment()` - Add payments to partial receipts
- `customer_debt_dashboard()` - View outstanding balances
- `gift_report()` - View gift statistics

❌ Missing: POS UI integration for gift and partial payment

## Implementation Steps

### 1. Gift Feature (Admin Only)

#### A. Frontend Changes (sell_product_multi_payment.html)

Add per-item gift checkbox with admin check:
```html
<!-- In the product row section, add: -->
{% if user.is_superuser %}
<div class="form-check mb-2">
    <input class="form-check-input gift-checkbox"
           type="checkbox"
           id="gift-{{ forloop.counter0 }}"
           data-row-index="{{ forloop.counter0 }}">
    <label class="form-check-label text-danger" for="gift-{{ forloop.counter0 }}">
        <i class="bi bi-gift"></i> Mark as Gift (₦0)
    </label>
</div>
<div class="gift-reason-section" id="gift-reason-{{ forloop.counter0 }}" style="display:none;">
    <textarea class="form-control gift-reason-input"
              name="gift_reason_{{ forloop.counter0 }}"
              placeholder="Reason for gift..."
              rows="2"></textarea>
</div>
{% endif %}
```

Add JavaScript to handle gift selection:
```javascript
// Handle gift checkbox changes
$(document).on('change', '.gift-checkbox', function() {
    const rowIndex = $(this).data('row-index');
    const isGift = $(this).is(':checked');
    const $row = $(this).closest('.product-row');

    // Show/hide gift reason
    $(`#gift-reason-${rowIndex}`).toggle(isGift);

    // If gift, set price to 0 but store original
    if (isGift) {
        const originalPrice = $row.find('.item-total').data('original-price');
        $row.find('.item-total').data('is-gift', true);
        $row.find('.item-total').text('₦0.00 (GIFT)').addClass('text-danger');
    } else {
        $row.find('.item-total').data('is-gift', false);
        // Restore original price calculation
        recalculateRowTotal(rowIndex);
    }

    // Recalculate grand total
    calculateTotal();
});
```

#### B. Backend Changes (views.py - sell_product function)

Add gift handling in the sale processing loop (around line 2132-2148):

```python
# Inside the for form in formset loop:
# After line 2140: sale.save()

# Check if this item is marked as gift
is_gift = request.POST.get(f'is_gift_{formset.forms.index(form)}') == 'true'
if is_gift and request.user.is_superuser:
    sale.is_gift = True
    sale.gift_reason = request.POST.get(f'gift_reason_{formset.forms.index(form)}', '')
    sale.original_value = sale.total_price  # Store original price
    sale.total_price = Decimal('0')  # Gift items are ₦0
    sale.save()

    # Don't add gift items to subtotal
    subtotal += Decimal('0')
else:
    # Normal sale
    subtotal += sale.total_price
```

---

### 2. Partial Payment Feature

#### A. Frontend Changes (sell_product_multi_payment.html)

Add partial payment section after payment methods:
```html
<!-- After payment methods section -->
<div class="card mb-3">
    <div class="card-header bg-warning text-dark">
        <h6 class="mb-0">
            <i class="bi bi-clock-history"></i> Partial Payment Option
        </h6>
    </div>
    <div class="card-body">
        <div class="form-check mb-3">
            <input class="form-check-input" type="checkbox" id="enable-partial-payment">
            <label class="form-check-label" for="enable-partial-payment">
                <strong>Allow Partial Payment</strong>
                <small class="text-muted d-block">Customer will pay part now, rest later</small>
            </label>
        </div>

        <div id="partial-payment-section" style="display:none;">
            <div class="row">
                <div class="col-md-6">
                    <label class="form-label">Amount Paying Now</label>
                    <input type="number"
                           class="form-control"
                           id="partial-amount-paying"
                           name="partial_amount_paying"
                           step="0.01"
                           min="0"
                           placeholder="Enter amount">
                </div>
                <div class="col-md-6">
                    <label class="form-label">Balance Remaining</label>
                    <input type="text"
                           class="form-control"
                           id="partial-balance-remaining"
                           readonly
                           value="₦0.00">
                </div>
            </div>
            <div class="alert alert-info mt-3">
                <i class="bi bi-info-circle"></i>
                This transaction will be marked as <strong>Partially Paid</strong> and will appear in Outstanding Balances dashboard.
            </div>
        </div>
    </div>
</div>
```

Add JavaScript for partial payment:
```javascript
// Enable/disable partial payment
$('#enable-partial-payment').change(function() {
    $('#partial-payment-section').toggle(this.checked);

    if (this.checked) {
        // Suggest 50% payment
        const total = parseFloat($('#grand-total').text().replace(/[^\d.]/g, ''));
        const halfPayment = (total / 2).toFixed(2);
        $('#partial-amount-paying').val(halfPayment);
        updatePartialBalance();
    }
});

// Update balance remaining
$('#partial-amount-paying').on('input', updatePartialBalance);

function updatePartialBalance() {
    const total = parseFloat($('#grand-total').text().replace(/[^\d.]/g, ''));
    const amountPaying = parseFloat($('#partial-amount-paying').val()) || 0;
    const balance = total - amountPaying;

    $('#partial-balance-remaining').val('₦' + balance.toFixed(2));

    // Update payment methods total to match amount paying
    if ($('#enable-partial-payment').is(':checked')) {
        // Adjust first payment method to match partial amount
        $('#payment_method-0-amount').val(amountPaying.toFixed(2));
    }
}
```

#### B. Backend Changes (views.py - sell_product function)

Add partial payment handling after receipt creation (around line 2250):

```python
# After line 2250: receipt.save()

# Check if this is a partial payment
is_partial_payment = request.POST.get('enable_partial_payment') == 'true'
if is_partial_payment:
    amount_paying = Decimal(request.POST.get('partial_amount_paying', '0'))

    # Validate partial payment
    if amount_paying >= final_total:
        # If paying full amount or more, treat as full payment
        receipt.payment_status = 'paid'
        receipt.amount_paid = final_total
        receipt.balance_remaining = Decimal('0')
    elif amount_paying <= 0:
        # No payment made
        receipt.payment_status = 'pending'
        receipt.amount_paid = Decimal('0')
        receipt.balance_remaining = final_total
    else:
        # Partial payment
        receipt.payment_status = 'partial'
        receipt.amount_paid = amount_paying
        receipt.balance_remaining = final_total - amount_paying

        # Create initial partial payment record
        from .models import PartialPayment
        PartialPayment.objects.create(
            receipt=receipt,
            amount=amount_paying,
            payment_method=valid_payment_methods[0]['payment_method'],
            notes=f"Initial partial payment",
            received_by=request.user
        )

    receipt.save()
else:
    # Full payment
    receipt.payment_status = 'paid'
    receipt.amount_paid = final_total
    receipt.balance_remaining = Decimal('0')
    receipt.save()
```

---

## Files to Modify

1. **Template**: `mystore/store/templates/sales/sell_product_multi_payment.html`
   - Add gift checkbox (admin only)
   - Add gift reason textarea
   - Add partial payment section

2. **View**: `mystore/store/views.py` - `sell_product()` function
   - Add gift processing (lines ~2132-2148)
   - Add partial payment processing (after line 2250)

3. **Receipt Template**: Add display for partial payment status
   - Show payment status badge
   - Show amount paid / balance remaining
   - Add "Make Payment" button if partial

---

## Testing Checklist

### Gift Feature:
- [ ] Only admins see gift checkbox
- [ ] Gift checkbox shows/hides reason field
- [ ] Gift items show ₦0 in cart
- [ ] Gift items don't add to subtotal
- [ ] Original value is stored
- [ ] Gifts appear in gift report
- [ ] Receipt shows "GIFT" for gifted items

### Partial Payment Feature:
- [ ] Partial payment section appears when enabled
- [ ] Balance calculation is correct
- [ ] Payment methods adjust to partial amount
- [ ] Receipt status shows "Partially Paid"
- [ ] Receipt appears in Outstanding Balances dashboard
- [ ] Can add additional payments from receipt detail
- [ ] Status changes to "Fully Paid" when complete
- [ ] Payment history shows all payments

---

## Access URLs After Implementation

- **Gift Report**: http://127.0.0.1:8000/reports/gift/
- **Outstanding Balances**: http://127.0.0.1:8000/customer-debt/
- **POS**: http://127.0.0.1:8000/sales/
