# Gift & Partial Payment System Summary

## ✅ What's Already Implemented

### 1. **Gift System** (Admin Only)
Gift items to customers without payment - only admins can do this.

#### Database Models (models.py)
- **Sale Model** has gift fields:
  - `is_gift` (Boolean) - Mark item as gift
  - `gift_reason` (TextField) - Reason for gifting
  - `original_value` (Decimal) - Original price before marking as gift

#### Views (views.py)
- **gift_report** (Line 7673) - View all gifted items with statistics
  - Shows total items, quantity, and value of gifts
  - Date filtering available
  - Located at: `http://127.0.0.1:8000/reports/gift/`

#### URLs (urls.py:68)
```python
path('reports/gift/', views.gift_report, name='gift_report')
```

#### Templates
- `templates/reports/gift_report.html` - Gift report page
- `templates/sales/gift_report.html` - Alternative gift report

---

### 2. **Partial Payment System**
Allow customers to pay partially and track outstanding balances.

#### Database Models (models.py)

**Receipt Model** - Partial payment fields:
- `amount_paid` (Decimal) - Total amount paid so far
- `balance_remaining` (Decimal) - Remaining balance to pay
- `payment_status` (CharField) - Choices:
  - 'paid' - Fully Paid
  - 'partial' - Partially Paid
  - 'pending' - Payment Pending

**PartialPayment Model** (Line 2472):
- `receipt` (ForeignKey) - Link to receipt
- `amount` (Decimal) - Payment amount
- `payment_method` (CharField) - Cash, Card, Transfer, etc.
- `payment_date` (DateTime) - When payment was made
- `notes` (TextField) - Payment notes
- `received_by` (ForeignKey to User) - Staff who received payment

#### Views (views.py)

**add_partial_payment** (Line 7602):
- Add a partial payment to a receipt
- Updates receipt balances
- Changes status to 'paid' when fully paid
- Located at: `receipts/<receipt_id>/add-payment/`

**customer_debt_dashboard** (Line 7649):
- View all customers with outstanding balances
- Shows total outstanding amount
- Lists all partial/pending receipts
- Located at: `http://127.0.0.1:8000/customer-debt/`

#### URLs (urls.py)
```python
path('receipts/<int:receipt_id>/add-payment/', views.add_partial_payment, name='add_partial_payment')
path('customer-debt/', views.customer_debt_dashboard, name='customer_debt_dashboard')
```

#### Templates
- `templates/sales/customer_debt_dashboard.html` - Outstanding balances dashboard

---

## 🔧 What Needs To Be Implemented/Fixed

### 1. **POS Integration for Gifts**
The gift functionality exists in the model but may not be exposed in the POS interface.

**TODO:**
- [ ] Add "Gift Item" checkbox/button in POS (homepage.html)
- [ ] Add admin-only permission check for gift option
- [ ] Add gift reason input field
- [ ] Ensure gift items show ₦0 in total but track original value
- [ ] Add visual indicator for gift items in cart

### 2. **POS Integration for Partial Payments**
The partial payment backend exists but may not be in the checkout process.

**TODO:**
- [ ] Add "Partial Payment" option during checkout
- [ ] Add input for initial payment amount
- [ ] Show remaining balance to customer
- [ ] Auto-set payment_status to 'partial' when balance > 0
- [ ] Link to outstanding balance from receipt

### 3. **Receipt Display**
**TODO:**
- [ ] Show payment status badge on receipts
- [ ] Show "Add Payment" button for partial receipts
- [ ] Display payment history for partial payments
- [ ] Show outstanding balance prominently

---

## 📍 Current Access Points

### Gift System:
- **Gift Report**: `http://127.0.0.1:8000/reports/gift/`
  - View all items given as gifts
  - See total value of gifts
  - Filter by date range

### Partial Payment System:
- **Outstanding Balances Dashboard**: `http://127.0.0.1:8000/customer-debt/`
  - View all customers with outstanding balances
  - See total amount owed
  - Access individual receipts to add payments

- **Add Payment to Receipt**: `http://127.0.0.1:8000/receipts/<receipt_id>/add-payment/`
  - Add partial payment to specific receipt
  - Update balance remaining
  - Track payment history

---

## 🎯 Recommended Next Steps

1. **Check if gift/partial payment options are in POS UI**
   - Open homepage (POS) and look for these options during checkout
   - If missing, they need to be added to the frontend

2. **Test Outstanding Balance Dashboard**
   - Go to: `http://127.0.0.1:8000/customer-debt/`
   - Should show all receipts with outstanding balances

3. **Test Gift Report**
   - Go to: `http://127.0.0.1:8000/reports/gift/`
   - Should show all gifted items

4. **Database Check**
   - All models and fields exist
   - Run migrations if needed: `python manage.py makemigrations && python manage.py migrate`

---

## 💡 How It Should Work

### Gift Flow:
1. Admin selects product in POS
2. Clicks "Mark as Gift" (admin only)
3. Enters gift reason
4. Item shows ₦0 in cart but tracks original value
5. Receipt shows "GIFT" for those items
6. Gift appears in gift report for tracking

### Partial Payment Flow:
1. Customer checks out normally
2. Selects "Partial Payment" option
3. Enters amount they can pay now (e.g., ₦5000 of ₦10000 total)
4. Receipt created with:
   - payment_status = 'partial'
   - amount_paid = ₦5000
   - balance_remaining = ₦5000
5. Receipt appears in Outstanding Balances dashboard
6. Customer can make additional payments later
7. When fully paid, status changes to 'paid'

---

## 🔍 Files to Check/Modify

1. **POS Interface**: `mystore/store/templates/homepage.html`
   - Check lines around checkout for gift/partial payment options
   - Add UI elements if missing

2. **Receipt Detail**: Check for receipt detail template
   - Should show payment status
   - Should have "Add Payment" button for partial payments

3. **Permissions**: Verify admin-only access for gifts
   - Check if `@user_passes_test(lambda u: u.is_superuser)` or similar is used
