# Hammy - Retail Management System

A comprehensive Django-based Point of Sale (POS) and inventory management system with advanced reporting and analytics capabilities.

## Overview

Hammy is a full-featured retail management solution designed for local Windows environments, providing robust inventory tracking, sales processing, customer management, and business intelligence through integrated OEM reporting.

## Key Features

### Store Management
- **Point of Sale (POS)** - Modern, responsive POS interface with customer display support
- **Inventory Management** - Multi-location warehouse tracking with transfer capabilities
- **Product Management** - Comprehensive product catalog with barcode generation
- **Customer Management** - Customer profiles with loyalty points system
- **Pre-Orders & Deliveries** - Order management and delivery tracking
- **Receipt Printing** - Thermal printer support with customizable receipt templates
- **Payment Processing** - Multiple payment methods with detailed logging

### Loyalty Program
- Points-based rewards system
- Automatic point accrual on purchases
- Point redemption with configurable conversion rates
- Customer-specific discounts and tracking

### OEM Reporting & Analytics
- **Sales Analytics** - Daily, monthly, and trend analysis
- **Inventory Reports** - Stock levels, turnover rates, and low-stock alerts
- **Performance Metrics** - Category, shop, and product performance tracking
- **Business Intelligence** - Day-of-week and hourly sales patterns
- **Comparison Reports** - Period-over-period analysis

### Automation Features
- **Celery Integration** - Background task processing
- **Scheduled Tasks** - Automated daily backups and data synchronization
- **PythonAnywhere Sync** - Automatic data sync to production environment

## Technology Stack

- **Framework**: Django 5.0.14
- **Database**: Microsoft SQL Server (with ODBC Driver 17)
- **Task Queue**: Celery 5.5.3 with Redis
- **Frontend**: Bootstrap 5, jQuery, vanilla JavaScript
- **Additional Libraries**:
  - WeasyPrint - PDF generation
  - python-barcode - Barcode generation
  - Pillow - Image processing
  - pandas - Data analysis
  - python-escpos - Thermal printer support
  - pyotp - Two-factor authentication
  - python-decouple - Environment variable management
  - whitenoise - Static file serving

## Project Structure

```
III/
├── mystore/                    # Main Django project
│   ├── mystore/               # Project settings
│   ├── store/                 # Core POS and inventory app
│   │   ├── management/        # Django management commands
│   │   ├── templates/         # Store templates
│   │   └── views.py           # Store views and business logic
│   ├── oem_reporting/         # Analytics and reporting app
│   │   ├── templates/         # Reporting templates
│   │   └── models.py          # Reporting data models
│   ├── static/                # Static assets (CSS, JS, images)
│   ├── media/                 # User-uploaded content
│   └── barcodes/              # Generated barcode images
├── minimal_api/               # Lightweight production deployment version
├── requirements.txt           # Python dependencies
├── .env.example              # Environment variables template
├── start_celery.bat          # Celery worker startup
├── start_celery_service.bat  # Celery as Windows service
├── stop_celery.bat           # Stop Celery workers
└── sync_all_data.bat         # Sync data to PythonAnywhere
```

## Installation

### Prerequisites

- Python 3.11+
- Microsoft SQL Server (2019 or later)
- ODBC Driver 17 for SQL Server
- Redis (for Celery)
- Windows OS (for batch scripts and full functionality)

### Setup Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/abdulrasaq-oniguguru/Hammy.git
   cd Hammy
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   - Copy `.env.example` to `.env`
   - Update database credentials and other settings:
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

7. **Setup Celery periodic tasks** (optional but recommended)
   ```bash
   python setup_celery_tasks.py
   ```

8. **Start the development server**
   ```bash
   python manage.py runserver
   ```

9. **Start Celery worker** (in a new terminal)
   ```bash
   start_celery.bat
   ```

## Usage

### Accessing the Application

- **Admin Panel**: http://localhost:8000/admin/
- **POS System**: http://localhost:8000/
- **Customer Display**: http://localhost:8000/customer-display/
- **OEM Reports**: http://localhost:8000/oem/

### Key Management Commands

```bash
# Setup user profiles
python manage.py setup_user_profiles

# Sync OEM data
python manage.py sync_oem_data

# Send daily sales reports
python manage.py send_daily_sales_reports

# Sync payment methods
python manage.py sync_payment_methods
```

### Celery Tasks

- **Daily Backup** - Automated database backup at 2 AM
- **PythonAnywhere Sync** - Sync data to production every 6 hours

## Features Deep Dive

### Customer Display

The customer display is a second-screen interface for showing transaction details to customers in real-time:
- Live sync with POS (50ms polling)
- Shows all items, prices, discounts
- Displays loyalty points earned
- Shows delivery costs if applicable
- Beautiful, customer-friendly UI

### Loyalty System

- Configurable points per currency unit spent
- Point redemption at configurable value
- Customer-specific loyalty tracking
- Automatic point accrual
- Discount application at checkout

### Receipt Printing

- Supports thermal printers via ESC/POS
- Customizable receipt templates
- Barcode integration
- Multiple printer configuration support

## Deployment

This repository is the full development version. For production deployment on PythonAnywhere, use the minimal API version:

**Production Repository**: https://github.com/abdulrasaq-oniguguru/Hammy-API.git

The `sync_all_data.bat` script handles synchronization between local and production environments.

## Contributing

This is a private business application. Contributions are limited to authorized developers.

## Security Notes

- Never commit `.env` files or credentials
- Keep `SECRET_KEY` secure
- Use environment variables for all sensitive configuration
- Regular backups are automated via Celery
- All passwords and API keys should be stored in `.env`

## License

Proprietary - All rights reserved

## Support

For issues or questions, contact the development team.

## Author

Abdulrasaq Oniguguru

---

**Last Updated**: November 2025
