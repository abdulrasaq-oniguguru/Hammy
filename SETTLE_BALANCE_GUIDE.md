# Settle Balance Payment System Guide

## 🎯 Overview

The "Settle Payment" feature allows you to collect balance payments from customers who made partial/deposit payments earlier.

---

## 📋 How to Settle a Balance

### **Step 1: View Outstanding Balances**

Go to: http://127.0.0.1:8000/customer-debt/

**You'll see:**
```
┌────────────────────────────────────┐
│ Total Outstanding Balance          │
│ ₦3,015.00                          │
│ Total Customers with Debt: 2       │
└────────────────────────────────────┘

┌─────────────────┐  ┌─────────────────┐
│ 👤 John Doe     │  │ 👤 Jane Smith   │
│ 📞 0801234567   │  │ 📞 0809876543   │
│                 │  │                 │
│ Oldest Debt     │  │ Oldest Debt     │
│ Jan 15, 2026    │  │ Feb 10, 2026    │
│                 │  │                 │
│ ₦2,000.00       │  │ ₦1,015.00       │
│ 3 receipts      │  │ 1 receipt       │
└─────────────────┘  └─────────────────┘
```

### **Step 2: Click on Customer**

Click on the customer card to see their detailed debt history.

**You'll see:**
- All receipts with outstanding balances
- Receipt details (subtotal, tax, delivery, total)
- Amount paid so far
- Balance remaining
- Payment history (all deposits made)

### **Step 3: Click "Settle Payment"**

Click the green **"Settle Payment"** button on any receipt.

---

## 💳 Payment Form

### **What You'll See:**

#### **Left Side: Receipt Information**
- **Customer Details** - Name, phone, email
- **Receipt Summary** - Full breakdown of the sale
  - Subtotal
  - Discounts (if any)
  - Tax (if any)
  - Delivery (if any)
  - **Total Amount**
  - **Amount Paid** (green) - All deposits so far
  - **Balance Remaining** (red) - What's still owed
- **Payment History** - All previous payments with:
  - Date & time
  - Payment method
  - Amount
  - Who received it

#### **Right Side: Add Payment Form**
- **Outstanding Balance** - Shows current balance in big red text
- **Payment Amount** - Enter amount (defaults to full balance)
- **Payment Method** - Select how customer is paying:
  - Cash
  - POS Moniepoint
  - Transfer (Taj, Sterling, Moniepoint)
  - Card
  - Mobile Money
  - Bank Deposit
  - Cheque
  - **Store Credit** ✨
- **Notes** - Optional payment notes
- **Quick Amount Buttons**:
  - **Full** - Pay entire balance
  - **Half** - Pay half of balance

---

## 🎯 Example Scenarios

### **Scenario 1: Full Balance Payment**

**Original Sale:**
- Total: ₦10,000
- Initial Deposit: ₦7,000 (Cash)
- Balance: ₦3,000

**Now Settling:**
1. Click "Settle Payment"
2. Payment Amount: ₦3,000 (auto-filled)
3. Payment Method: Cash
4. Click "Record Payment"

**Result:**
- ✅ Receipt marked as **"FULLY PAID"**
- ✅ Balance: ₦0.00
- ✅ Removed from Outstanding Balances
- ✅ Payment history shows both payments

---

### **Scenario 2: Partial Balance Payment**

**Original Sale:**
- Total: ₦10,000
- Initial Deposit: ₦3,000 (Cash)
- Balance: ₦7,000

**First Additional Payment:**
1. Payment Amount: ₦4,000
2. Payment Method: Transfer
3. Click "Record Payment"

**Result:**
- ⏳ Receipt still **"PARTIALLY PAID"**
- Balance: ₦3,000 (updated)
- Stays in Outstanding Balances
- Page reloads for next payment

**Second Additional Payment:**
1. Payment Amount: ₦3,000
2. Payment Method: Cash
3. Click "Record Payment"

**Result:**
- ✅ Receipt marked as **"FULLY PAID"**
- ✅ Balance: ₦0.00
- ✅ Redirected to receipt detail

---

### **Scenario 3: Store Credit Payment**

**Customer has ₦5,000 store credit**

**Outstanding Balance: ₦3,000**

1. Click "Settle Payment"
2. Payment Method: **Store Credit**
3. System shows: "Store credit available: ₦5,000, Max usable: ₦3,000"
4. Amount auto-fills to ₦3,000
5. Click "Record Payment"

**Result:**
- ✅ Balance paid using store credit
- ✅ Customer's store credit reduced to ₦2,000
- ✅ StoreCreditUsage record created
- ✅ Receipt marked as "FULLY PAID"

---

### **Scenario 4: Multiple Payment Methods**

**Balance: ₦8,000**

**Payment 1:**
- Amount: ₦3,000
- Method: Cash
- Balance becomes: ₦5,000

**Payment 2:**
- Amount: ₦2,000
- Method: Store Credit
- Balance becomes: ₦3,000

**Payment 3:**
- Amount: ₦3,000
- Method: Transfer
- Balance becomes: ₦0.00
- Status: FULLY PAID ✅

---

## ✨ Features

### **1. Smart Validation**
- ✅ Cannot pay more than balance remaining
- ✅ Store credit validated against available balance
- ✅ Amount must be greater than 0

### **2. Real-time Updates**
- Balance updates immediately after each payment
- Payment history shows all transactions
- Receipt status auto-updates

### **3. Store Credit Support**
- Fetches customer's available store credit
- Validates amount against balance
- Uses FIFO (oldest credits first)
- Auto-deducts from customer's credit

### **4. Payment History Tracking**
- Every payment recorded with:
  - Date & time
  - Amount
  - Payment method
  - Who received it
  - Optional notes

### **5. Flexible Payments**
- Pay full balance at once
- Pay in multiple installments
- Mix different payment methods
- Use store credit for all or part

---

## 🔄 Payment Status Flow

```
PENDING (₦0 paid)
    ↓ Make deposit
PARTIAL (some paid, balance > 0)
    ↓ Add payment(s)
PARTIAL (balance reducing)
    ↓ Pay remaining balance
PAID (balance = ₦0) ✅
```

---

## 📊 Receipt Display

### **During Partial Payment:**
```
*** DEPOSIT RECEIPT ***

💰 DEPOSIT PAID: ₦7,000.00
⚠️ BALANCE DUE: ₦3,000.00

Payment History:
1. Cash ₦5,000 (Feb 15, 2026 - DEPOSIT)
2. POS ₦2,000 (Feb 15, 2026 - DEPOSIT)
```

### **After Full Payment:**
```
Sales Receipt
Status: FULLY PAID ✅

PAYMENT BREAKDOWN:
💰 DEPOSIT (Feb 15, 2026): ₦7,000.00
✅ BALANCE (Feb 16, 2026): ₦3,000.00

TOTAL PAID: ₦10,000.00
```

---

## 🛠️ Technical Details

### **Files Created/Modified:**
- `views.py` - Updated `add_partial_payment` view with form and store credit support
- `add_partial_payment.html` - New template with payment form
- `customer_debt_dashboard.html` - Updated link to payment form

### **Features:**
- Store credit API integration
- FIFO store credit deduction
- Real-time validation
- Payment history tracking
- Auto-status updates

---

## ✅ Success Criteria

Balance payment is working when:
- [x] Can view all customers with outstanding balances
- [x] Can click on customer to see their receipts
- [x] "Settle Payment" shows receipt details and payment form
- [x] Can enter payment amount and method
- [x] Store credit validated and deducted
- [x] Payment recorded in history
- [x] Balance updates correctly
- [x] Receipt status changes to "PAID" when balance = 0
- [x] Multiple payments supported
- [x] All payment methods work (including store credit)

---

**Last Updated:** 2026-02-16
**Status:** ✅ Fully Implemented & Ready to Use
