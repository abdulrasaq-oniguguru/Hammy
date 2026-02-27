# Nexus — Retail Management System

A comprehensive Django-based Point of Sale (POS) and inventory management system with advanced reporting, barcode printing, store credits, gift handling, partial payments, reorder management, and multi-location inventory tracking.

---

## Overview

Nexus is a full-featured retail management solution covering the entire sales lifecycle — from stock intake and barcode printing through sales, receipts, returns, and customer debt — with integrated analytics and OEM reporting.

---

## Features

### Point of Sale (POS)
- Full POS interface with product search and barcode scanning
- Customer-facing second-screen display (live sync at 50ms polling)
- Multiple payment methods (cash, card, bank transfer, etc.)
- Discount application at item and order level
- Receipt generation with auto-numbering (`RCP-YYYYMM-XXX`)
- Cancel/void orders
- Print thermal receipts (ESC/POS), download PDF, or email to customer

### Barcode Management
- Automatic EAN-13 barcode generation on product creation
- Regenerates barcode when product details change
- Thermal-optimized label printing (55mm × 25mm, 300 DPI)
- Label includes: Brand, Barcode, Size, Color, Price
- Single and bulk barcode printing
- Barcode lookup / product search by scan
- Barcode Print Manager — centralized print hub

### Printer Management
- Register and manage multiple printers
- Role-based printer routing (different printer per user role)
- Task-to-printer mapping: Barcode, Receipt, Invoice, Pre-order, Return
- Set default printer per task type
- Test print, enable/disable printers
- Print job history log
- Auto-detect system printers (AJAX)

### Partial Payments & Customer Debt
- Accept partial / installment payments on any receipt
- Record multiple payments until balance is cleared
- Customer Debt Dashboard — overview of all outstanding balances
- Remaining balance auto-calculated per receipt
- Supports any configured payment method per instalment

### Store Credits
- Issue store credits to customers (refunds, promotions, goodwill)
- Credits carry an expiry date and track remaining balance
- Auto-apply available credit at checkout
- Full usage history per credit
- API endpoint for real-time balance lookup

### Gift / Gift Sales
- Track gift transactions separately from standard sales
- Gift report showing value and volume of gifted products
- Discount and zero-price sales handled cleanly

### Returns Management
- Search and select items to return from any receipt
- Partial returns — return individual items, not the whole order
- Return workflow: Pending → Approved / Rejected → Completed
- Refund method: cash or store credit
- Return reason documentation
- MD-level approval for returns

### Reorder Module
- Session-based reorder cart
- Add products to reorder cart from the inventory list
- Review and confirm reorder quantities
- Confirmation page with order summary (`reorder_success`)
- Clears cart on completion

### Pre-Orders
- Create pre-orders for products not yet in stock
- Link pre-orders to customers with expected delivery date
- Convert pre-order directly to a product + invoice once goods arrive
- Tracks conversion date and created product/invoice IDs
- Delivery status toggling

### Inventory Management
- Product catalogue with: Brand, Category, Color, Design, Size, Location, Shop
- Two markup types: Percentage or Fixed amount (selling price auto-calculated)
- Warehouse inventory separate from shop floor stock
- Low-stock alerts and out-of-stock flags
- Product change history with reason tracking
- Product draft saving (resume adding a product later)
- Bulk import via Excel, bulk export (Excel / PDF)

### Inventory Transfers
- Location transfers: Abuja ↔ Lagos
- Internal transfers: Warehouse ↔ Shop Floor
- Transfer reference numbers: `TR-XXYY-####-MMYY` / `IT-XXYY-####-MMYY`
- Status workflow: Pending → In Transit → Received → Completed / Cancelled
- Transfer document export (PDF / Excel)

### Invoices
- Create purchase invoices with auto-numbering (`INV###/YYYY`)
- Product snapshot at invoice time (preserves history after product edits)
- Duplicate detection
- PDF and Excel export

### Customer Management
- Customer profiles: name, phone, email, address, gender
- Frequent customer flag
- Full purchase history per customer
- Customer receipt history view

### Loyalty Programme
- Points earned per Naira spent (configurable)
- Tiered membership: Bronze → Silver → Gold → Platinum
- Configurable point expiry
- Point redemption at checkout with configurable conversion rate
- Full transaction history per account
- Enrol customer, apply discount, check balance (AJAX endpoints)

### Delivery Management
- Create deliveries linked to receipts / customers
- Delivery options: Pickup or Delivery
- Status tracking: Pending → Delivered
- Delivery report and analytics

### Reports & Analytics
| Report | Description |
|--------|-------------|
| Sales Report | Daily / weekly / monthly sales with filtering |
| Financial Report | Revenue, cost of goods, gross margin |
| Discount Report | Discount value and frequency analysis |
| Gift Report | Gift sales volume and value |
| Customer Analysis | Spending patterns per customer |
| Product Performance | Revenue and units sold per product |
| Inventory Report | Current stock levels with low-stock highlights |
| Product History | Audit log of product edits and deletions |
| Tax Report | Tax collected by period |
| Delivery Report | Delivery performance metrics |

All reports support date-range filtering, category / shop / location filtering, and export to Excel or PDF. Charts powered by Chart.js.

### OEM Reporting & Analytics
A separate, read-only analytics database with no customer PII:

- Daily, weekly, and monthly sales summaries
- Top-selling products by period
- Category and shop performance
- Inventory turnover rates
- Day-of-week and hourly sales patterns
- Trend analysis with moving averages
- Comparison reports (period-over-period, location-vs-location)
- Low-stock alert tracking
- REST API with JWT authentication and rate limiting
- Audit logging on all API requests
- Multi-location support (Abuja / Lagos)

### Configuration
- **Store Configuration** — store details, receipt header/footer, logo
- **Payment Methods** — add, enable/disable, sync
- **Tax Configuration** — multiple tax rates with toggle
- **Loyalty Configuration** — points rate, tiers, expiry, redemption rules
- **User Management** — create users, set roles (MD / Cashier), assign shop & location

### User Roles & Access Control
| Role | Access |
|------|--------|
| MD (Managing Director) | Full access including returns approval, user management, all reports |
| Cashier | POS, receipts, customers, basic inventory |
| User | Standard access per configuration |

### Activity & Audit Log
- Full audit trail for every action
- Tracks: user, action, affected model, object ID, IP address, timestamp
- Viewable by MD role

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Framework | Django 5.0.14 |
| Database | Microsoft SQL Server (ODBC Driver 17) |
| Task Queue | Celery 5.5.3 + Redis |
| Frontend | Bootstrap 5, jQuery, Chart.js, vanilla JS |
| PDF Generation | WeasyPrint |
| Barcode | python-barcode + Pillow |
| Thermal Printing | python-escpos |
| Data Analysis | pandas |
| Authentication | Django sessions + JWT (OEM API) |
| 2FA | pyotp |
| Env Config | python-decouple |
| Static Files | whitenoise |

---

## Project Structure

```
III/
├── mystore/
│   ├── mystore/            # Django project settings, urls, wsgi, celery
│   ├── store/              # Core app — POS, inventory, sales, returns, etc.
│   │   ├── management/     # Management commands
│   │   ├── migrations/
│   │   ├── templates/      # All store-facing HTML templates
│   │   ├── models.py
│   │   ├── views.py
│   │   └── urls.py
│   ├── oem_reporting/      # Analytics & OEM reporting app
│   │   ├── templates/
│   │   ├── models.py
│   │   ├── views.py
│   │   └── urls.py
│   ├── static/             # CSS, JS, fonts, icons
│   └── manage.py
├── requirements.txt
├── .env                    # Local environment variables (never committed)
└── README.md
```

---

## Installation

### Prerequisites

- Python 3.11+
- Microsoft SQL Server 2019+
- ODBC Driver 17 for SQL Server
- Redis (for Celery background tasks)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/abdulrasaq-oniguguru/Hammy.git
   cd Hammy
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   source .venv/bin/activate  # Linux/Mac
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**

   Create a `.env` file in the project root:
   ```env
   DJANGO_SECRET_KEY=your-secret-key-here
   DJANGO_DEBUG=True
   DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

   DB_ENGINE=mssql
   DB_NAME=Store
   DB_USER=sa
   DB_PASSWORD=your-password
   DB_HOST=localhost
   DB_DRIVER=ODBC Driver 17 for SQL Server
   ```

5. **Run migrations**
   ```bash
   cd mystore
   python manage.py migrate
   ```

6. **Create superuser**
   ```bash
   python manage.py createsuperuser
   ```

7. **Start the development server**
   ```bash
   python manage.py runserver
   ```

8. **Start Celery worker** (separate terminal, optional)
   ```bash
   celery -A mystore worker -l info
   ```

---

## Application URLs

| URL | Description |
|-----|-------------|
| `/` | Homepage / Dashboard |
| `/sell/` | POS — Sell products |
| `/customer-display/` | Customer-facing display |
| `/products/` | Product list |
| `/customers/` | Customer list |
| `/receipts/` | Receipt list |
| `/invoices/` | Invoice list |
| `/returns/` | Returns list |
| `/pre-orders/` | Pre-order list |
| `/reorder/` | Reorder module |
| `/store-credits/` | Store credit list |
| `/debt-dashboard/` | Customer debt dashboard |
| `/barcodes/manager/` | Barcode Print Manager |
| `/printers/` | Printer management |
| `/reports/` | Reports dashboard |
| `/oem/` | OEM reporting dashboard |
| `/admin/` | Django admin panel |

---

## Management Commands

```bash
# Set up default user profiles
python manage.py setup_user_profiles

# Sync OEM analytics data
python manage.py sync_oem_data

# Send daily sales report emails
python manage.py send_daily_sales_reports

# Sync payment methods
python manage.py sync_payment_methods
```

---

## Production Deployment

**Production repository**: https://github.com/abdulrasaq-oniguguru/Hammy-API.git

For PythonAnywhere or any Linux host:
1. Clone the repo
2. Set up `.env` with production credentials
3. Run `python manage.py collectstatic`
4. Run `python manage.py migrate`
5. Configure your WSGI server to point to `mystore/mystore/wsgi.py`

---

## Security Notes

- Never commit `.env`, SSL certs (`.crt`/`.key`), or credentials
- Keep `SECRET_KEY` unique and secret per environment
- Use environment variables for all sensitive configuration
- MD role is required for returns approval and user management
- OEM API is JWT-protected with rate limiting

---

## License

Proprietary — All rights reserved.

---

## Made by Nexus &copy; 2026
