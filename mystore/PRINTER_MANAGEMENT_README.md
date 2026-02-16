# 🖨️ Printer Management System

## Overview
A comprehensive printer management system for your Django store application that supports:
- **Barcode Printers** - For printing product barcode labels
- **POS Receipt Printers (80mm)** - For thermal receipt printing
- **A4 Printers** - For documents, invoices, and reports

## Features

### ✨ Key Capabilities
1. **Multi-Printer Support** - Configure and manage multiple printers of different types
2. **Direct Printing** - Send jobs directly to Windows printers without user intervention
3. **Auto-Print Mode** - Automatically print when generating documents
4. **Print Job Tracking** - Monitor all print jobs with status tracking
5. **Test Printing** - Test printers with sample pages
6. **Default Printer Selection** - Set default printers for each type
7. **Printer Status Management** - Enable/disable printers as needed

## Installation & Setup

### 1. **Database Migration**
The models have already been migrated. If you need to re-migrate:
```bash
cd mystore
python manage.py makemigrations
python manage.py migrate --fake  # If tables already exist
```

### 2. **Access Printer Management**
Navigate to: **Tools & Utilities → Printer Management**

Or directly: `http://your-domain/printers/`

## Configuration Guide

### Adding a New Printer

1. **Go to Printer Management**
   - Click "Add Printer" button

2. **Fill in Printer Details**:

   **General Information:**
   - **Printer Name**: Friendly name (e.g., "Main POS Printer")
   - **Printer Type**: Select from:
     - Barcode Printer
     - POS Receipt Printer (80mm)
     - A4 Printer

   **System Configuration:**
   - **System Printer Name**: Select from dropdown of installed Windows printers

   **Paper Settings:**
   - **Paper Size**: Choose from:
     - 80mm (POS)
     - 58mm (Small POS)
     - A4
     - Letter
     - Custom Size
   - **Custom Width/Height**: (if Custom Size selected)

   **Print Settings:**
   - **DPI**: Dots Per Inch (default: 203 for thermal, 300 for laser)
   - **Copies**: Number of copies to print by default

   **Barcode Settings** (for barcode printers only):
   - **Label Width**: Width in mm (default: 50mm)
   - **Label Height**: Height in mm (default: 25mm)

   **Options:**
   - **Set as Default**: Make this the default printer for its type
   - **Active**: Enable/disable the printer
   - **Auto Print**: Automatically print when generating documents

3. **Save Configuration**

### Setting Up Your Printers

#### Barcode Printer Setup
```
Name: Barcode Label Printer
Type: Barcode Printer
System Name: [Your barcode printer from Windows]
Paper Size: Custom
Width: 50mm
Height: 25mm
DPI: 203
Auto Print: ✓ (recommended)
```

#### POS Receipt Printer Setup
```
Name: Main POS Printer
Type: POS Receipt Printer (80mm)
System Name: [Your 80mm thermal printer]
Paper Size: 80mm (POS)
DPI: 203
Copies: 1
Auto Print: ✓ (recommended)
Is Default: ✓
```

#### A4 Printer Setup
```
Name: Office Laser Printer
Type: A4 Printer
System Name: [Your A4/Letter printer]
Paper Size: A4
DPI: 300
Copies: 1
Auto Print: ☐ (user choice)
```

## Using the Printer System

### Automatic Printing

Once configured with **Auto Print** enabled, documents will automatically print when generated:

- **Barcodes**: When generating product barcodes
- **Receipts**: When completing sales (if POS printer configured)
- **Reports**: When exporting reports (if A4 printer configured)

### Manual Printing

You can manually trigger prints from various pages:
- Receipt detail pages
- Product barcode generation
- Report export pages

### Testing Printers

1. Go to **Printer Management**
2. Find your printer card
3. Click the **Test Print** button (printer icon)
4. A test page will be sent to the printer

## Print Job History

### Viewing Print Jobs

Navigate to: **Printer Management → View All** (in Recent Print Jobs section)

Or: `http://your-domain/printers/job-history/`

### Filter Print Jobs

Filter by:
- **Status**: Completed, Failed, Printing, Pending, Cancelled
- **Printer Type**: Barcode, POS, A4

### Print Job Statuses

- **✅ Completed**: Print job successful
- **❌ Failed**: Print job failed (see error message)
- **⚠️ Printing**: Currently printing
- **⏱️ Pending**: Queued for printing
- **⊘ Cancelled**: Print job cancelled

## Integration with Existing Code

### Using PrinterManager in Your Code

```python
from store.printing import PrinterManager
from PIL import Image

# Print a barcode
barcode_image = Image.open('path/to/barcode.png')
print_job = PrinterManager.print_barcode(
    barcode_image=barcode_image,
    product_name="Example Product",
    user=request.user
)

# Print a receipt
receipt_image = Image.open('path/to/receipt.png')
print_job = PrinterManager.print_receipt(
    receipt_image_or_pdf=receipt_image,
    receipt_id=123,
    user=request.user
)

# Print an A4 document
with open('document.pdf', 'rb') as f:
    pdf_bytes = f.read()

print_job = PrinterManager.print_a4_document(
    pdf_bytes=pdf_bytes,
    document_type='invoice',
    document_id=456,
    user=request.user
)
```

### Get Configured Printer

```python
from store.models import PrinterConfiguration

# Get default barcode printer
barcode_printer = PrinterConfiguration.get_default_printer('barcode')

# Get default POS printer
pos_printer = PrinterConfiguration.get_default_printer('pos')

# Get default A4 printer
a4_printer = PrinterConfiguration.get_default_printer('a4')
```

## Troubleshooting

### Printer Not Showing in List

**Problem**: Printer doesn't appear in system printer dropdown

**Solutions**:
1. Ensure printer is installed in Windows
2. Restart the Django development server
3. Check printer is not paused or offline in Windows
4. Verify printer drivers are installed

### Print Jobs Failing

**Problem**: Print jobs show "Failed" status

**Solutions**:
1. Check error message in print job history
2. Verify printer is online and connected
3. Test printer from Windows (print a test page)
4. Check printer has paper and no paper jams
5. Verify correct printer name is configured

### Auto-Print Not Working

**Problem**: Documents not printing automatically

**Solutions**:
1. Verify "Auto Print" is enabled for the printer
2. Check printer "Is Active" is enabled
3. Ensure printer is set as default for its type
4. Check print job history for errors

### Barcode Size Issues

**Problem**: Barcodes printing too small/large

**Solutions**:
1. Adjust "Label Width" and "Label Height" in barcode printer settings
2. Verify DPI setting matches your printer specifications
3. Check paper size matches actual label size

### Receipt Formatting Issues

**Problem**: Receipts not formatted correctly

**Solutions**:
1. Verify paper size is set to "80mm (POS)"
2. Check DPI is set to 203 (standard for thermal printers)
3. Ensure thermal printer supports ESC/POS commands

## File Structure

```
store/
├── models.py                          # PrinterConfiguration, PrintJob models
├── forms.py                           # PrinterConfigurationForm
├── views_printer.py                   # All printer management views
├── printing.py                        # PrinterManager class
├── admin.py                           # Admin registration
├── urls.py                            # Printer management URLs
└── templates/
    └── printer/
        ├── printer_management.html    # Main management page
        ├── add_printer.html          # Add printer form
        ├── edit_printer.html         # Edit printer form
        ├── delete_printer.html       # Delete confirmation
        └── print_job_history.html    # Print job history
```

## API Endpoints

### Printer Management URLs

- `GET /printers/` - Printer management dashboard
- `GET /printers/add/` - Add new printer
- `POST /printers/add/` - Create new printer
- `GET /printers/edit/<id>/` - Edit printer form
- `POST /printers/edit/<id>/` - Update printer
- `GET /printers/delete/<id>/` - Delete confirmation
- `POST /printers/delete/<id>/` - Delete printer
- `GET /printers/test/<id>/` - Test print printer
- `GET /printers/set-default/<id>/` - Set as default
- `GET /printers/toggle-status/<id>/` - Toggle active status
- `GET /printers/job-history/` - Print job history
- `GET /api/printers/system/` - AJAX: Get system printers

## Models Reference

### PrinterConfiguration

| Field | Type | Description |
|-------|------|-------------|
| name | CharField | Friendly printer name |
| printer_type | CharField | barcode, pos, or a4 |
| system_printer_name | CharField | Windows printer name |
| paper_size | CharField | Paper size selection |
| paper_width_mm | IntegerField | Custom width (mm) |
| paper_height_mm | IntegerField | Custom height (mm) |
| is_default | BooleanField | Default for type |
| is_active | BooleanField | Printer active |
| auto_print | BooleanField | Auto print enabled |
| dpi | IntegerField | Dots per inch |
| copies | IntegerField | Default copies |
| barcode_width | IntegerField | Barcode label width |
| barcode_height | IntegerField | Barcode label height |

### PrintJob

| Field | Type | Description |
|-------|------|-------------|
| printer | ForeignKey | Associated printer |
| document_type | CharField | receipt, barcode, invoice, etc. |
| document_id | IntegerField | Document ID |
| status | CharField | pending, printing, completed, failed, cancelled |
| copies | IntegerField | Number of copies |
| error_message | TextField | Error details (if failed) |
| created_at | DateTimeField | Job creation time |
| completed_at | DateTimeField | Job completion time |
| created_by | ForeignKey | User who created job |

## Best Practices

### Security
- Only administrators should access printer management
- Regularly review print job history for anomalies
- Disable unused printers to prevent accidental printing

### Performance
- Use auto-print sparingly for high-volume operations
- Monitor print job failures and address promptly
- Clean up old print jobs periodically

### Maintenance
- Test printers weekly
- Keep printer drivers updated
- Verify printer configurations after Windows updates

## Future Enhancements

Potential improvements:
1. Network printer support
2. Print queue management
3. Printer usage statistics
4. Email notifications for print failures
5. Cloud printing support
6. Print preview functionality
7. Custom print templates per printer
8. Batch printing capabilities

## Support

For issues or questions:
1. Check print job history for error details
2. Review troubleshooting section
3. Test printer from Windows Control Panel
4. Verify printer configuration settings
5. Check application logs for detailed errors

## Contributing

When adding new printer types:
1. Update `PRINTER_TYPE_CHOICES` in `PrinterConfiguration` model
2. Add corresponding print method in `PrinterManager`
3. Update templates to show new printer type
4. Add tests for new functionality

---

**Version**: 1.0
**Last Updated**: 2025-01-05
**Author**: Wrighteous Wearhouse Development Team
