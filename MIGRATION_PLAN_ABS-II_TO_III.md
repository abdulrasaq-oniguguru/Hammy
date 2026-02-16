# Migration Plan: ABS-II Features to III
**Date:** 2026-02-02
**Status:** In Progress
**Purpose:** Port debt management, thermal printing, and enhanced loyalty from ABS-II to III

---

## Overview

This document tracks the migration of three key features from ABS-II (fashion house system) to III (boutique system):

1. **Debt Management System** - Customer deposit payments and balance tracking
2. **Simplified Receipt Design** - Direct thermal printing with 80mm ESC/POS support
3. **Enhanced Loyalty Configuration** - Transaction count and item count discount types

---

## Feature 1: Debt Management System

### Changes Required

#### 1.1 Database Models (`mystore/store/models.py`)

**Add to Receipt Model (around line 722):**
```python
# Add these fields to Receipt model
amount_paid = models.DecimalField(
    max_digits=10,
    decimal_places=2,
    default=0,
    help_text="Total amount paid so far"
)
balance_remaining = models.DecimalField(
    max_digits=10,
    decimal_places=2,
    default=0,
    help_text="Remaining balance to be paid"
)
payment_status = models.CharField(
    max_length=20,
    choices=[
        ('paid', 'Paid'),
        ('partial', 'Partial Payment'),
        ('pending', 'Pending Payment')
    ],
    default='pending'
)
```

**Create New PartialPayment Model (add after Receipt model):**
```python
class PartialPayment(models.Model):
    """Track individual installment payments for receipts"""
    receipt = models.ForeignKey(
        Receipt,
        on_delete=models.CASCADE,
        related_name='partial_payments'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50)
    payment_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    received_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='partial_payments_received'
    )

    class Meta:
        ordering = ['-payment_date']

    def __str__(self):
        return f"Payment of {self.amount} for {self.receipt.receipt_number}"
```

#### 1.2 Views (`mystore/store/views.py`)

**Add Customer Debt Dashboard View:**
- Copy `customer_debt_dashboard()` function from ABS-II (around line 11721)
- Location to add: After receipt-related views in III
- Features:
  - List all customers with outstanding balances
  - Filter by date range, amount range, search
  - Show total debt per customer
  - Links to individual receipts

**Add Complete Payment View:**
- Copy `complete_payment()` function from ABS-II
- Handles recording partial payments
- Updates Receipt balance_remaining and amount_paid
- Creates PartialPayment records

**Add Payment Details View:**
- Copy `payment_details()` function from ABS-II (line 3340)
- Shows detailed payment breakdown
- Displays payment history

#### 1.3 URLs (`mystore/store/urls.py`)

**Add URL patterns:**
```python
path('customer-debt/', views.customer_debt_dashboard, name='customer_debt_dashboard'),
path('receipt/<int:receipt_id>/complete-payment/', views.complete_payment, name='complete_payment'),
path('payment/<int:payment_id>/details/', views.payment_details, name='payment_details'),
```

#### 1.4 Templates

**Create/Update:**
- `templates/store/customer_debt_dashboard.html` - Copy from ABS-II
- `templates/Receipt/payment_history_section.html` - Partial payment history display
- Update `receipt_pdf.html` to show balance and payment history

#### 1.5 Admin Configuration (`mystore/store/admin.py`)

**Register PartialPayment model:**
```python
@admin.register(PartialPayment)
class PartialPaymentAdmin(admin.ModelAdmin):
    list_display = ['receipt', 'amount', 'payment_method', 'payment_date', 'received_by']
    list_filter = ['payment_method', 'payment_date']
    search_fields = ['receipt__receipt_number', 'notes']
    date_hierarchy = 'payment_date'
```

#### 1.6 Migration Steps

```bash
# After making model changes
cd mystore
python manage.py makemigrations store
python manage.py migrate store
```

---

## Feature 2: Thermal Printing System

### Changes Required

#### 2.1 Copy Thermal Printer Module

**Source:** `C:\Users\asoniguguru\PycharmProjects\ABS-II\mystore\store\thermal_printer.py`
**Destination:** `C:\Users\asoniguguru\PycharmProjects\III\mystore\store\thermal_printer.py`

**Key Features:**
- `ThermalPrinter` class for 80mm ESC/POS printers
- Methods: `connect()`, `print_payment_receipt()`, `_print_centered()`, `_print_line()`, `_print_logo()`
- Currency symbol sanitization (₦ → N, € → EUR)
- Logo support with PIL/Pillow

#### 2.2 Update Receipt Templates

**Create thermal-optimized template:**
- **Source:** `ABS-II/mystore/store/templates/Receipt/print_receipt.html`
- **Destination:** `III/mystore/store/templates/Receipt/print_receipt_thermal.html`

**Keep existing template:**
- Keep `receipt_pdf.html` for A4/general printing
- Add option to choose between thermal and A4 printing

**Template Features to Include:**
- 80mm width optimization
- Monospace font (Courier New)
- Store logo centered
- Receipt type indicator (Sales/Deposit)
- Items table
- Tax breakdown
- Payment methods display
- Balance tracking section
- Payment history section

#### 2.3 Update Views (`mystore/store/views.py`)

**Modify/Add print_receipt() view:**
```python
def print_receipt(request, receipt_id):
    receipt = get_object_or_404(Receipt, id=receipt_id)
    printer_type = request.GET.get('printer_type', 'thermal')  # thermal or a4

    if printer_type == 'thermal':
        # Use thermal printer
        from .thermal_printer import ThermalPrinter
        printer = ThermalPrinter()
        if printer.connect():
            printer.print_payment_receipt(receipt)
        return render(request, 'Receipt/print_receipt_thermal.html', {'receipt': receipt})
    else:
        # Use existing A4 printing
        return render(request, 'Receipt/receipt_pdf.html', {'receipt': receipt})
```

#### 2.4 Update Requirements

**Add to `requirements.txt` if not present:**
```
Pillow>=10.0.0  # For logo printing
python-escpos>=3.0  # ESC/POS printer support (optional)
```

#### 2.5 Printer Configuration

**Verify PrinterConfiguration model supports thermal:**
- Check `mystore/store/models.py` line ~1183
- Ensure paper_size includes '80mm' option
- Printer type includes 'pos' option

---

## Feature 3: Enhanced Loyalty Configuration

### Changes Required

#### 3.1 Database Models (`mystore/store/models.py`)

**Update LoyaltyConfiguration Model (around line 2058):**

**Add calculation type choices:**
```python
POINT_CALCULATION_TYPES = [
    ('per_transaction', 'Points per Transaction'),
    ('per_amount', 'Points per Amount Spent'),
    ('combined', 'Combined (Transaction + Amount)'),
    ('transaction_count_discount', 'Transaction Count Discount'),  # NEW
    ('item_count_discount', 'Item Count Discount'),  # NEW
]
```

**Add fields to LoyaltyConfiguration:**
```python
# Customer type filtering
customer_type = models.CharField(
    max_length=20,
    choices=[
        ('all', 'All Customers'),
        ('regular', 'Regular Customers'),
        ('vip', 'VIP Customers')
    ],
    default='all',
    help_text="Apply this loyalty configuration to specific customer types"
)

# Transaction count discount fields
required_transaction_count = models.IntegerField(
    default=0,
    help_text="Number of transactions required for discount (for transaction_count_discount type)"
)
transaction_discount_percentage = models.DecimalField(
    max_digits=5,
    decimal_places=2,
    default=0,
    help_text="Discount percentage on next transaction after reaching count"
)

# Item count discount fields
required_item_count = models.IntegerField(
    default=0,
    help_text="Number of items purchased required for discount (for item_count_discount type)"
)
item_discount_percentage = models.DecimalField(
    max_digits=5,
    decimal_places=2,
    default=0,
    help_text="Discount percentage per item threshold reached"
)
```

**Update CustomerLoyaltyAccount Model (around line 2261):**
```python
# Add tracking fields
transaction_count = models.IntegerField(
    default=0,
    help_text="Total number of transactions made"
)
item_count = models.IntegerField(
    default=0,
    help_text="Total number of items purchased"
)
discount_count = models.IntegerField(
    default=0,
    help_text="Number of times discount has been applied"
)
discount_eligible = models.BooleanField(
    default=False,
    help_text="Whether customer is currently eligible for transaction count discount"
)
```

#### 3.2 Update Loyalty Utils (`mystore/store/loyalty_utils.py`)

**Enhance process_sale_loyalty_points() function:**
- Add logic for transaction_count_discount calculation
- Add logic for item_count_discount calculation
- Update transaction_count and item_count in CustomerLoyaltyAccount
- Handle discount_eligible flag

**Reference:** Copy logic from ABS-II `loyalty_utils.py` (around transaction count handling section)

#### 3.3 Update Views (`mystore/store/views_config.py`)

**Update edit_loyalty_configuration() view:**
- Add form fields for new loyalty types
- Handle customer_type filtering
- Add validation for transaction/item count fields

#### 3.4 Update Forms (`mystore/store/forms.py`)

**Update LoyaltyConfigurationForm:**
```python
class LoyaltyConfigurationForm(forms.ModelForm):
    class Meta:
        model = LoyaltyConfiguration
        fields = [
            'program_name',
            'is_active',
            'customer_type',  # NEW
            'calculation_type',
            'points_per_transaction',
            'points_per_currency_unit',
            'currency_unit_value',
            'required_transaction_count',  # NEW
            'transaction_discount_percentage',  # NEW
            'required_item_count',  # NEW
            'item_discount_percentage',  # NEW
            # ... other existing fields
        ]
```

#### 3.5 Update Templates

**Update loyalty configuration template:**
- Add UI for customer_type selection
- Add conditional fields for transaction_count_discount type
- Add conditional fields for item_count_discount type
- Add JavaScript to show/hide relevant fields based on calculation_type

#### 3.6 Migration Steps

```bash
cd mystore
python manage.py makemigrations store
python manage.py migrate store
```

---

## Implementation Order

### Phase 1: Database Changes (Complete First)
1. ✅ Create migration document (this file)
2. ✅ Update Receipt model (add amount_paid, balance_remaining, payment_status)
3. ✅ Create PartialPayment model
4. ✅ Update LoyaltyConfiguration model (add new fields)
5. ✅ Update CustomerLoyaltyAccount model (add transaction_count, item_count)
6. ✅ Run migrations
   - 0007: Receipt debt management fields + PartialPayment model
   - 0008: Enhanced loyalty fields

### Phase 2: Thermal Printing (Second)
1. ✅ Copy thermal_printer.py module
2. ⬜ Create print_receipt_thermal.html template
3. ⬜ Update print views to support thermal printing
4. ⬜ Test thermal printing functionality
5. ✅ Update requirements.txt (already has python-escpos, pillow, pywin32)

### Phase 3: Debt Management Views (Third)
1. ✅ Add customer_debt_dashboard view
2. ✅ Add complete_payment view
3. ⬜ Add payment_details view (optional)
4. ⬜ Create debt dashboard template (needs frontend work)
5. ✅ Update URLs
6. ✅ Register PartialPayment in admin

### Phase 4: Enhanced Loyalty (Fourth)
1. ✅ Update LoyaltyConfiguration and CustomerLoyaltyAccount models
2. ✅ Create migrations for new loyalty fields
3. ⬜ Update loyalty_utils.py calculation logic (needs implementation)
4. ⬜ Update loyalty configuration form (needs frontend work)
5. ⬜ Update loyalty configuration views (needs frontend work)
6. ⬜ Update loyalty configuration template (needs frontend work)
7. ⬜ Test loyalty calculations

### Phase 5: Testing (Final)
1. ⬜ Test debt management workflow
2. ⬜ Test thermal receipt printing
3. ⬜ Test enhanced loyalty types
4. ⬜ Create sample data for testing
5. ⬜ User acceptance testing

---

## File Locations Reference

### III (Target - Boutique System)
```
C:\Users\asoniguguru\PycharmProjects\III\mystore\store\
├── models.py (2362 lines) - Add debt & loyalty fields
├── views.py (306KB) - Add debt views
├── views_config.py - Update loyalty config views
├── forms.py - Update loyalty forms
├── loyalty_utils.py (28KB) - Enhance loyalty logic
├── thermal_printer.py - NEW FILE (copy from ABS-II)
├── printing.py (13KB) - May need updates
├── admin.py - Register new models
├── urls.py (19KB) - Add debt URLs
└── templates/
    ├── Receipt/
    │   ├── receipt_pdf.html (636 lines) - Keep for A4
    │   └── print_receipt_thermal.html - NEW (copy from ABS-II)
    └── store/
        └── customer_debt_dashboard.html - NEW
```

### ABS-II (Source - Fashion House System)
```
C:\Users\asoniguguru\PycharmProjects\ABS-II\mystore\store\
├── models.py (3878+ lines) - Reference for debt & loyalty models
├── views.py (524KB) - Reference for debt dashboard (line 11721)
├── views_config.py (49KB) - Reference for loyalty config
├── loyalty_utils.py (41KB) - Reference for enhanced loyalty logic
├── thermal_printer.py (38KB) - COPY THIS FILE
└── templates/
    └── Receipt/
        └── print_receipt.html (15KB) - COPY/ADAPT THIS
```

---

## Testing Checklist

### Debt Management Testing
- [ ] Create receipt with partial payment
- [ ] Record additional payments via complete_payment view
- [ ] Verify balance_remaining updates correctly
- [ ] Check customer_debt_dashboard displays all outstanding balances
- [ ] Test filtering by date range
- [ ] Test filtering by amount range
- [ ] Test search functionality
- [ ] Verify PartialPayment records are created
- [ ] Check payment history displays on receipt

### Thermal Printing Testing
- [ ] Connect to 80mm thermal printer
- [ ] Print sales receipt with items
- [ ] Print deposit receipt
- [ ] Verify logo prints correctly
- [ ] Check currency symbols display correctly
- [ ] Test payment history section
- [ ] Test balance display
- [ ] Verify 48-character line width formatting
- [ ] Test divider lines and centering

### Enhanced Loyalty Testing
- [ ] Configure transaction_count_discount loyalty
- [ ] Test transaction count tracking
- [ ] Verify discount applies after reaching threshold
- [ ] Configure item_count_discount loyalty
- [ ] Test item count tracking
- [ ] Verify item discount applies correctly
- [ ] Test customer_type filtering (regular vs VIP)
- [ ] Check loyalty account updates after sale

---

## Rollback Procedure

If issues occur during migration:

### Database Rollback
```bash
cd mystore
python manage.py migrate store <previous_migration_number>
```

### Code Rollback
```bash
git stash  # Save current changes
git checkout <commit_before_migration>
```

### Restore from Backup
1. Stop Django server
2. Restore database backup
3. Restore code backup
4. Restart server

---

## Dependencies

### Required Python Packages
```
Django>=4.0
Pillow>=10.0.0  # For logo printing in thermal receipts
python-escpos>=3.0  # Optional: For advanced thermal printer features
```

### System Requirements
- Windows system (for win32print API in printing.py)
- Thermal printer with ESC/POS support (80mm recommended)
- PostgreSQL or compatible database

---

## Notes & Considerations

### Database Considerations
- **amount_paid and balance_remaining** should be computed fields, but storing them improves query performance
- Add database triggers or signals to keep balance_remaining in sync
- Consider adding index on payment_status for faster debt queries

### Thermal Printer Considerations
- Test with actual 80mm thermal printer before deployment
- Some thermal printers may not support logo printing
- Currency symbol sanitization is critical for thermal compatibility
- Keep font size readable (10-12pt for 80mm)

### Loyalty Considerations
- Transaction count discount resets after discount is applied
- Item count discount can apply multiple times per transaction
- Customer type filtering requires Customer model to have customer_type field
- Consider adding customer type field to Customer model if not present

### Performance Considerations
- Add database indexes for frequently queried fields:
  - Receipt.balance_remaining
  - Receipt.payment_status
  - PartialPayment.payment_date
  - CustomerLoyaltyAccount.transaction_count

---

## Contact & Support

**Project Lead:** [Your Name]
**Documentation Date:** 2026-02-02
**Last Updated:** 2026-02-02
**Version:** 1.0

---

## Change Log

| Date | Phase | Changes | Status |
|------|-------|---------|--------|
| 2026-02-02 | Planning | Created migration plan document | ✅ Complete |
| 2026-02-02 | Phase 1 | Database model updates (Receipt, PartialPayment, Loyalty) | ✅ Complete |
| 2026-02-02 | Phase 2 | Thermal printing implementation | ✅ Complete (Module) |
| 2026-02-02 | Phase 3 | Debt management views (Backend) | ✅ Complete |
| 2026-02-02 | Phase 4 | Enhanced loyalty (Database) | ✅ Complete |
| | Remaining | Frontend templates and loyalty logic | ⬜ Pending |
| | Phase 5 | Testing | ⬜ Pending |

---

## Quick Resume Guide

**If you need to resume this migration later:**

1. **Check this document** for current phase status (see Change Log above)
2. **Review Phase completion** in Implementation Order section
3. **Start from the next uncompleted phase** (marked with ⬜)
4. **Reference File Locations** section for exact file paths
5. **Use Testing Checklist** to verify completed features
6. **Update Change Log** as you complete each phase

**Current Status:** Planning Complete, Ready for Phase 1 (Database Changes)
