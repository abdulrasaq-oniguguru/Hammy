# Partial Payment (Deposit) System Guide

## 🎯 How It Works

The partial payment system now works exactly like the **Deposit Part Image** design.

### Step-by-Step Process:

#### 1. **Create a Sale with Partial Payment (Deposit)**

1. Go to POS: http://127.0.0.1:8000/sales/
2. Select a customer
3. Add products to cart (e.g., Total: ₦9,000)
4. Add payment method(s):
   - Example: Cash ₦7,000
   - You can add multiple payment methods
5. **Check "Accept Partial Payment (Deposit)"** ✅
6. **Payment Summary** appears automatically showing:
   ```
   Payments total: ₦7,000.00 | Sale total: ₦9,000.00
   - Deposit payment. Balance: ₦2,000.00
   ```

#### 2. **What Happens When You Complete Sale**

- Receipt is created with status: **PARTIAL PAYMENT**
- Amount Paid: ₦7,000 (the deposit)
- Balance Remaining: ₦2,000
- Receipt header shows: **"*** DEPOSIT RECEIPT ***"**
- Receipt displays:
  - 💰 DEPOSIT PAID: ₦7,000.00
  - ⚠️ BALANCE DUE: ₦2,000.00

#### 3. **View Outstanding Balances**

Go to: http://127.0.0.1:8000/customer-debt/

**You'll see:**
- All customers with outstanding balances
- Click on a customer to see their receipts
- Each receipt shows:
  - Total Amount: ₦9,000.00
  - Amount Paid: ₦7,000.00 (deposit)
  - Balance Remaining: ₦2,000.00
  - Payment History (all deposits made)

#### 4. **Settle Balance Later**

1. From customer debt dashboard, click **"Settle Payment in POS"**
2. Or go to: http://127.0.0.1:8000/receipts/{receipt_id}/add-payment/
3. Enter remaining balance: ₦2,000
4. Select payment method
5. Click **"Add Payment"**

**Result:**
- Receipt status changes to: **FULLY PAID**
- Balance Remaining: ₦0.00
- Receipt now shows complete payment history:
  - 💰 DEPOSIT (original date): ₦7,000.00
  - ✅ BALANCE (payment date): ₦2,000.00
  - **TOTAL PAID: ₦9,000.00**

---

## 💡 Key Features

### ✅ Automatic Calculation
- No manual input of deposit amount needed
- System calculates deposit from payment methods total
- Balance auto-calculated: Sale Total - Payments Total

### ✅ Payment Summary Display
The Payment Summary section shows in real-time:
- **Payments total**: Sum of all payment methods
- **Sale total**: Grand total including taxes, delivery, discounts
- **Balance**: Remaining amount to be paid

### ✅ Multiple Payment Methods for Deposit
You can use multiple payment methods for the deposit:
- Cash: ₦3,000
- Store Credit: ₦2,000
- POS: ₦2,000
- **Total Deposit: ₦7,000**

### ✅ Store Credit Integration
Store credit can be used for deposits:
1. Select customer with store credit
2. Customer's available balance appears
3. Add "Store Credit" as payment method
4. Enter amount (validated against available balance)
5. Check "Accept Partial Payment (Deposit)"
6. Complete sale - store credit deducted automatically

---

## 📊 UI Design (Matches Deposit Part Image)

### Yellow Deposit Section
```
☑ Accept Partial Payment (Deposit)
Payment methods total will be recorded as deposit.
Balance will be tracked for later payment.
```

### Cyan Payment Summary Section
```
ℹ Payment Summary:
Payments total: ₦7,000.00 | Sale total: ₦9,000.00
- Deposit payment. Balance: ₦2,000.00 (in orange/gold)
```

---

## 🧪 Testing Scenarios

### Test 1: Basic Partial Payment
- Product total: ₦9,000
- Payment: Cash ₦7,000
- Check partial payment ✅
- Expected: Deposit ₦7,000, Balance ₦2,000

### Test 2: Multiple Payment Methods
- Product total: ₦15,000
- Payments:
  - Cash: ₦5,000
  - Store Credit: ₦5,000
  - POS: ₦3,000
- Total deposit: ₦13,000
- Expected: Balance ₦2,000

### Test 3: Full Payment (Even with Checkbox)
- Product total: ₦10,000
- Payment: Cash ₦10,000
- Check partial payment ✅
- Expected: Receipt marked as "PAID" (no balance)

### Test 4: No Payment (Pending Order)
- Product total: ₦5,000
- No payment methods added (or ₦0)
- Check partial payment ✅
- Expected: Receipt marked as "PENDING", Balance ₦5,000

---

## 🔧 Technical Details

### Frontend (JavaScript)
- `updatePaymentSummary()` - Calculates and displays payment summary
- Uses global `saleTotal` variable for accurate total
- Monitors all `.payment-amount` inputs for changes
- Shows/hides summary based on checkbox state

### Backend (views.py)
- Calculates `payment_methods_total` from all payment methods
- Sets `receipt.amount_paid = payment_methods_total`
- Sets `receipt.balance_remaining = final_total - payment_methods_total`
- Creates `PartialPayment` record for each payment method
- Status logic:
  - `paid` if payment ≥ total
  - `pending` if payment = 0
  - `partial` if 0 < payment < total

### Database Fields
- `receipt.payment_status` - 'paid', 'partial', or 'pending'
- `receipt.amount_paid` - Total deposited
- `receipt.balance_remaining` - Amount still owed
- `PartialPayment.amount` - Individual payment amount
- `PartialPayment.payment_method` - How it was paid

---

## ✨ Advantages

1. **Simple UI** - Just check a box, system handles the rest
2. **Flexible** - Use any payment methods for deposit
3. **Real-time** - See balance instantly as you enter amounts
4. **Complete History** - Track all payments over time
5. **Professional Receipts** - Clear deposit/balance breakdown
6. **Outstanding Tracking** - Dashboard shows all unpaid balances

---

**Last Updated:** 2026-02-16
**Status:** Fully Implemented & Ready for Use
