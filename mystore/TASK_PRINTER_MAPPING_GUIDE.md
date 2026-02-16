# 🎯 Task to Printer Mapping Guide

## Overview
The Task to Printer Mapping system allows you to assign specific printers to specific tasks. This means you can configure:
- **POS Receipts** → Your 80mm thermal printer
- **Barcodes** → Your barcode label printer
- **Transfer Documents** → Your A4 printer
- **Reports** → Your A4 printer
- And many more!

## Quick Start

### 1. Access Task Mapping
Navigate to: **Printer Management → Task Mapping** button

Or directly: `http://your-domain/printers/task-mapping/`

### 2. Available Task Types

#### For Thermal/POS Printers (80mm):
- **POS Receipt (Thermal)** - Standard 80mm sales receipts
- **Barcode Label** - Individual product barcode labels
- **Customer Receipt** - Customer copies of receipts

#### For A4 Printers:
- **Receipt (A4 Format)** - Full-size receipts for records
- **Invoice** - Formal invoices
- **Transfer Document** - Stock transfer forms
- **Sales Report** - Daily/periodic sales reports
- **Financial Report** - Financial summaries
- **Product List** - Product inventory lists
- **Barcode Sheet** - Multiple barcodes on A4 paper
- **Delivery Note** - Delivery documentation

## Setup Instructions

### Step 1: Add Your First Task Mapping

1. Go to **Printer Management** → **Task Mapping**
2. Click **"Add Task Mapping"**
3. Fill in the form:

#### Example: POS Receipt Configuration
```
Task Type: POS Receipt (Thermal)
Printer: Main POS Printer (80mm)
Copies: 1
Active: ✓
Auto Print: ✓
Notes: Prints automatically after each sale
```

#### Example: Barcode Label Configuration
```
Task Type: Barcode Label
Printer: Barcode Label Printer
Copies: 1
Active: ✓
Auto Print: ✓
Notes: Auto-print individual barcodes
```

#### Example: Transfer Document Configuration
```
Task Type: Transfer Document
Printer: Office Laser Printer (A4)
Copies: 2
Active: ✓
Auto Print: ✗ (manual confirmation)
Notes: Need 2 copies - one for each location
```

### Step 2: Configure All Your Tasks

Here's a recommended setup:

| Task Type | Recommended Printer | Copies | Auto Print |
|-----------|-------------------|--------|------------|
| POS Receipt (Thermal) | 80mm POS Printer | 1 | ✓ |
| Receipt (A4 Format) | A4 Printer | 1 | ✗ |
| Barcode Label | Barcode Printer | 1 | ✓ |
| Barcode Sheet (A4) | A4 Printer | 1 | ✗ |
| Invoice | A4 Printer | 2 | ✗ |
| Transfer Document | A4 Printer | 2 | ✗ |
| Sales Report | A4 Printer | 1 | ✗ |
| Financial Report | A4 Printer | 1 | ✗ |
| Product List | A4 Printer | 1 | ✗ |
| Customer Receipt | 80mm POS Printer | 1 | ✓ |
| Delivery Note | A4 Printer | 1 | ✗ |

## How It Works

### Automatic Printer Selection

When you trigger a print action in the system, it will:

1. **Check Task Mapping**: Look up which printer is assigned to that task
2. **Get Printer Config**: Retrieve the printer settings (copies, auto-print, etc.)
3. **Send to Printer**: Route the document to the correct printer
4. **Track Job**: Log the print job for monitoring

### Example Workflow

**Scenario: Customer makes a purchase**

1. You complete a sale in POS
2. System generates a receipt
3. Task Mapping looks up "POS Receipt (Thermal)"
4. Finds: Main POS Printer (80mm), Auto Print = Yes
5. **Automatically prints** receipt to 80mm thermal printer
6. No user intervention needed!

**Scenario: Printing a transfer document**

1. You create a stock transfer
2. Click "Download/Print"
3. System looks up "Transfer Document" task
4. Finds: Office Laser Printer (A4), Copies = 2
5. Sends 2 copies to A4 printer
6. Manual confirmation if Auto Print = No

## Using the Interface

### Task Mapping Dashboard

The main dashboard shows:
- **Current Mappings**: All configured task-to-printer assignments
- **Task Type**: What document/action
- **Assigned Printer**: Which printer handles it
- **Copies**: How many copies
- **Auto Print**: If it prints automatically
- **Status**: Active/Inactive
- **Actions**: Edit, Toggle, Delete

### Quick Actions

**Edit Mapping**: Change printer, copies, or auto-print settings
**Toggle Status**: Temporarily disable/enable a mapping
**Delete**: Remove a task mapping completely

### Active Printers Reference

The bottom section shows all available printers with their specifications, making it easy to choose the right printer for each task.

## Best Practices

### 1. Auto-Print Settings

**Enable Auto-Print For:**
- POS receipts (customers expect immediate receipt)
- Barcode labels (efficiency in product management)
- Customer receipts

**Disable Auto-Print For:**
- Reports (review before printing)
- Invoices (may need approval)
- Transfer documents (may need adjustments)

### 2. Multiple Copies

Set appropriate copy counts:
- **1 Copy**: POS receipts, barcodes, reports
- **2 Copies**: Invoices (customer + file), transfer docs (both locations)
- **3+ Copies**: Only if required by business process

### 3. Task Organization

**Group Similar Tasks:**
- All thermal printing → 80mm POS printer
- All A4 documents → Office laser printer
- All barcodes → Dedicated barcode printer

## Troubleshooting

### Problem: Task not printing to correct printer

**Solution:**
1. Check if task mapping exists for that task type
2. Verify printer is active
3. Check task mapping is active
4. Ensure printer is online in Windows

### Problem: Auto-print not working

**Solutions:**
1. Verify "Auto Print" is enabled in task mapping
2. Check printer has "Is Active" enabled
3. Verify printer is selected (not "No Printer")
4. Check print job history for errors

### Problem: Wrong number of copies printing

**Solution:**
1. Check "Copies" setting in task mapping
2. Verify printer configuration doesn't override
3. Check Windows printer properties

## Programming Integration

### Using Task Mapping in Code

```python
from store.models import PrinterTaskMapping

# Get printer for a specific task
printer = PrinterTaskMapping.get_printer_for_task('receipt_pos')

# Check if auto-print is enabled
should_auto_print = PrinterTaskMapping.should_auto_print('barcode_label')

# Get number of copies
copies = PrinterTaskMapping.get_copies_for_task('invoice')
```

### Example: Print Receipt with Task Mapping

```python
from store.models import PrinterTaskMapping
from store.printing import PrinterManager

# Get configured printer for POS receipts
task_printer = PrinterTaskMapping.get_printer_for_task('receipt_pos')

if task_printer and PrinterTaskMapping.should_auto_print('receipt_pos'):
    # Auto-print enabled
    copies = PrinterTaskMapping.get_copies_for_task('receipt_pos')

    print_job = PrinterManager.print_receipt(
        receipt_image_or_pdf=receipt_image,
        receipt_id=receipt.id,
        user=request.user
    )
else:
    # Manual print or no printer configured
    # Show print dialog or download option
    pass
```

## Advanced Features

### Conditional Printing

You can programmatically override settings:

```python
# Force print regardless of auto-print setting
if user_requested_print:
    PrinterManager.print_receipt(...)

# Skip auto-print for specific conditions
if total_amount > 10000:
    # Large order - manager review first
    auto_print = False
```

### Custom Task Types

To add new task types, edit `PrinterTaskMapping.TASK_CHOICES` in `models.py`:

```python
TASK_CHOICES = [
    # ... existing choices ...
    ('custom_report', 'Custom Report'),
    ('packing_slip', 'Packing Slip'),
]
```

## FAQ

**Q: Can I assign multiple printers to one task?**
A: No, each task can only have one printer. However, you can create similar tasks if needed (e.g., "Receipt POS" and "Receipt A4").

**Q: What happens if no printer is assigned to a task?**
A: The system will either use the default printer for that type or prompt the user to select a printer.

**Q: Can I change task mappings without restarting the system?**
A: Yes! All changes take effect immediately.

**Q: What if my printer is offline?**
A: The print job will be logged as "Failed" with an error message. You can retry from the print job history.

**Q: Can I see which tasks use which printer?**
A: Yes, go to the Task Mapping dashboard for a complete overview.

## Summary

The Task to Printer Mapping system gives you:
- ✅ **Automatic printer selection** based on document type
- ✅ **Centralized configuration** - set once, works everywhere
- ✅ **Flexibility** - enable/disable auto-print per task
- ✅ **Control** - specify copies, printer preferences
- ✅ **Visibility** - see all mappings at a glance

This eliminates the need to manually select printers for each operation and ensures documents always go to the right printer!

---

**Last Updated**: 2025-01-05
**Version**: 1.0
