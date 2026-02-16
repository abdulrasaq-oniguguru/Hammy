"""
PostgreSQL Database Settings Template for Django
Configure these settings in your Django settings.py for PostgreSQL migration.

This template includes:
- Proper UTF-8 encoding configuration
- Africa/Lagos timezone
- Nigerian deployment optimizations
- Unicode character preservation (₦ Naira symbol support)
"""

# =============================================================================
# IMPORTANT: PostgreSQL Setup Instructions
# =============================================================================
#
# 1. Install PostgreSQL adapter:
#    pip install psycopg2-binary
#
# 2. Create PostgreSQL database:
#    psql -U postgres
#    CREATE DATABASE your_database_name;
#    CREATE USER your_db_user WITH PASSWORD 'your_password';
#    GRANT ALL PRIVILEGES ON DATABASE your_database_name TO your_db_user;
#    ALTER DATABASE your_database_name SET client_encoding = 'UTF8';
#
# 3. Update your .env file with PostgreSQL credentials
#
# 4. Copy the DATABASES configuration below to your settings.py
#
# =============================================================================

import os
from pathlib import Path

# If using environment variables (recommended)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',

        # Database connection details
        'NAME': os.getenv('DB_NAME', 'your_database_name'),
        'USER': os.getenv('DB_USER', 'your_db_user'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'your_password'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),

        # UTF-8 encoding options (critical for Nigerian Naira ₦ symbol)
        'OPTIONS': {
            'client_encoding': 'UTF8',
        },

        # Connection pool settings (optional, for production)
        'CONN_MAX_AGE': 600,  # Keep connections alive for 10 minutes

        # Additional options for production
        # 'OPTIONS': {
        #     'client_encoding': 'UTF8',
        #     'sslmode': 'require',  # For production/cloud databases
        # },
    }
}

# =============================================================================
# TIMEZONE SETTINGS
# =============================================================================

# Set timezone to Nigeria (West Africa Time - WAT)
TIME_ZONE = 'Africa/Lagos'
USE_TZ = True  # Use timezone-aware datetimes

# =============================================================================
# INTERNATIONALIZATION
# =============================================================================

LANGUAGE_CODE = 'en-us'
USE_I18N = True
USE_L10N = True

# =============================================================================
# EXAMPLE .env FILE
# =============================================================================
#
# Create a file named .env in your project root with these variables:
#
# # PostgreSQL Database Configuration
# DB_ENGINE=django.db.backends.postgresql
# DB_NAME=your_database_name
# DB_USER=your_db_user
# DB_PASSWORD=your_secure_password
# DB_HOST=localhost
# DB_PORT=5432
#
# =============================================================================

# =============================================================================
# ALTERNATIVE: Direct Configuration (without .env)
# =============================================================================
#
# If not using environment variables, you can configure directly:

DATABASES_DIRECT = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'mystore_db',
        'USER': 'mystore_user',
        'PASSWORD': 'your_secure_password_here',
        'HOST': 'localhost',
        'PORT': '5432',
        'OPTIONS': {
            'client_encoding': 'UTF8',
        },
        'CONN_MAX_AGE': 600,
    }
}

# =============================================================================
# CLOUD DEPLOYMENT EXAMPLES
# =============================================================================

# Example 1: Heroku PostgreSQL
DATABASES_HEROKU = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'OPTIONS': {
            'client_encoding': 'UTF8',
            'sslmode': 'require',
        },
    }
}

# Example 2: AWS RDS PostgreSQL
DATABASES_AWS_RDS = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),  # e.g., mydb.123456.us-east-1.rds.amazonaws.com
        'PORT': os.getenv('DB_PORT', '5432'),
        'OPTIONS': {
            'client_encoding': 'UTF8',
            'sslmode': 'require',
        },
        'CONN_MAX_AGE': 600,
    }
}

# Example 3: DigitalOcean Managed PostgreSQL
DATABASES_DIGITALOCEAN = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT', '25060'),  # DigitalOcean uses custom port
        'OPTIONS': {
            'client_encoding': 'UTF8',
            'sslmode': 'require',
        },
    }
}

# =============================================================================
# TESTING UNICODE SUPPORT
# =============================================================================
#
# After configuring PostgreSQL, test Unicode support:
#
# python manage.py shell
# >>> from django.db import connection
# >>> cursor = connection.cursor()
# >>> cursor.execute("SHOW client_encoding")
# >>> print(cursor.fetchone())  # Should show: ('UTF8',)
# >>> cursor.execute("SELECT '₦100'")
# >>> print(cursor.fetchone())  # Should show: ('₦100',)
#
# =============================================================================

# =============================================================================
# REQUIREMENTS.TXT
# =============================================================================
#
# Add these to your requirements.txt:
#
# Django>=4.2
# psycopg2-binary>=2.9.9
# python-decouple>=3.8  # For .env file support
#
# Or for production (compile from source):
# psycopg2>=2.9.9
#
# =============================================================================

# =============================================================================
# MIGRATION CHECKLIST
# =============================================================================
#
# ✓ Step-by-step migration process:
#
# 1. ✓ Install PostgreSQL on your system
# 2. ✓ Create PostgreSQL database and user
# 3. ✓ Install psycopg2-binary: pip install psycopg2-binary
# 4. ✓ Update .env with PostgreSQL credentials
# 5. ✓ Export data: python export_mssql_data.py
# 6. ✓ Update settings.py with PostgreSQL configuration (this file)
# 7. ✓ Create schema: python manage.py migrate
# 8. ✓ Import data: python import_postgresql_data.py
# 9. ✓ Verify migration: python verify_migration.py
# 10. ✓ Test application thoroughly
# 11. ✓ Test currency symbols (₦) display correctly
# 12. ✓ Update deployment configuration
#
# =============================================================================

# =============================================================================
# TROUBLESHOOTING
# =============================================================================
#
# Issue: "FATAL: password authentication failed"
# Solution: Check DB_USER and DB_PASSWORD in .env
#
# Issue: "could not connect to server"
# Solution: Check PostgreSQL is running, verify HOST and PORT
#
# Issue: "database does not exist"
# Solution: Create database first: CREATE DATABASE your_database_name;
#
# Issue: Unicode characters show as "?"
# Solution: Verify client_encoding is UTF8 in OPTIONS
#
# Issue: "permission denied for database"
# Solution: GRANT ALL PRIVILEGES ON DATABASE your_db_name TO your_user;
#
# =============================================================================

# =============================================================================
# PERFORMANCE TUNING (Optional - For Production)
# =============================================================================

DATABASES_PRODUCTION = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'OPTIONS': {
            'client_encoding': 'UTF8',
            'sslmode': 'require',
            # Connection pooling
            'connect_timeout': 10,
            # Application name for monitoring
            'application_name': 'mystore',
        },
        # Keep connections alive
        'CONN_MAX_AGE': 600,
        # Connection retry
        'ATOMIC_REQUESTS': True,
    }
}

# =============================================================================
# LOGGING (Optional - For Debugging)
# =============================================================================

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',  # Change to INFO in production
        },
    },
}

print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║  PostgreSQL Settings Template for Django                                  ║
║                                                                            ║
║  This template provides configuration for:                                ║
║    • UTF-8 encoding (Naira ₦ symbol support)                             ║
║    • Africa/Lagos timezone                                                ║
║    • Nigerian deployment optimizations                                    ║
║                                                                            ║
║  Copy the DATABASES configuration to your settings.py                     ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
""")
