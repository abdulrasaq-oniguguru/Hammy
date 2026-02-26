"""
Django settings TEMPLATE for mystore project.

SETUP INSTRUCTIONS FOR A NEW SYSTEM:
======================================
1. Copy this file to settings.py:
       cp settings.example.py settings.py

2. Create a .env file in the mystore/ directory (same folder as manage.py)
   and fill in all required values. See .env.example for reference.

3. Install dependencies:
       pip install -r requirements.txt

4. Run migrations (each system generates its own):
       python manage.py makemigrations
       python manage.py migrate

5. Create a superuser:
       python manage.py createsuperuser

NOTE: settings.py is NOT committed to git.
      Each system keeps its own local settings.py.
"""

from pathlib import Path
import os
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

# =====================================
# SECURITY SETTINGS
# =====================================
SECRET_KEY = config('DJANGO_SECRET_KEY', default='CHANGE-THIS-TO-A-RANDOM-SECRET-KEY')
DEBUG = config('DJANGO_DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('DJANGO_ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'store',
    "crispy_forms",
    "crispy_bootstrap5",
    "widget_tweaks",
    'django_celery_beat',
    'django_celery_results',
    'oem_reporting',
    'rest_framework',
    'rest_framework_simplejwt',
]

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'store.middleware.AccessControlMiddleware',
]

ROOT_URLCONF = 'mystore.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.media',
                'store.context_processors.user_permissions',
                'store.context_processors.store_config',
            ],
        },
    },
]

WSGI_APPLICATION = 'mystore.wsgi.application'

# =====================================
# DATABASE CONFIGURATION
# =====================================
# Set DB_ENGINE in your .env file to match your local database:
#   PostgreSQL:  django.db.backends.postgresql
#   MySQL:       django.db.backends.mysql
#   SQLite:      django.db.backends.sqlite3
#   MS SQL:      mssql
#
DB_ENGINE = config('DB_ENGINE', default='django.db.backends.postgresql')

if DB_ENGINE == 'django.db.backends.postgresql':
    DB_OPTIONS = {'client_encoding': 'UTF8'}
    DB_PORT_DEFAULT = '5432'
elif DB_ENGINE == 'mssql':
    DB_OPTIONS = {
        'driver': config('DB_DRIVER', default='ODBC Driver 17 for SQL Server'),
        'Encrypt': True,
        'TrustServerCertificate': True,
        'ATOMIC_REQUESTS': True
    }
    DB_PORT_DEFAULT = ''
elif DB_ENGINE == 'django.db.backends.mysql':
    DB_OPTIONS = {
        'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        'charset': 'utf8mb4',
    }
    DB_PORT_DEFAULT = '3306'
else:
    DB_OPTIONS = {}
    DB_PORT_DEFAULT = ''

DATABASES = {
    'default': {
        'ENGINE': DB_ENGINE,
        'NAME': config('DB_NAME', default='Store'),
        'USER': config('DB_USER', default=''),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default=DB_PORT_DEFAULT),
        'OPTIONS': DB_OPTIONS,
        'CONN_MAX_AGE': 600 if DB_ENGINE == 'django.db.backends.postgresql' else 0,
    },
}

# =====================================
# REST FRAMEWORK CONFIGURATION
# =====================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '10/hour',
        'user': '1000/day'
    }
}

from datetime import timedelta as jwt_timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': jwt_timedelta(hours=24),
    'REFRESH_TOKEN_LIFETIME': jwt_timedelta(days=7),
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = config('STATIC_ROOT', default=os.path.join(BASE_DIR, 'static_root'))

SASS_PROCESSOR_ROOT = os.path.join(BASE_DIR, 'static', 'scss')
SASS_PROCESSOR_OUTPUT_DIR = 'css'

MEDIA_URL = '/media/'
MEDIA_ROOT = config('MEDIA_ROOT', default=os.path.join(BASE_DIR, 'media'))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =====================================
# EMAIL CONFIGURATION
# =====================================
from datetime import timedelta

DAILY_REPORT_EMAIL = config('DAILY_REPORT_EMAIL', default='')
DAILY_REPORT_CC_EMAILS = config('DAILY_REPORT_CC_EMAILS', default='', cast=Csv())

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='')

DAILY_REPORT_CONFIG = {
    'SEND_TIME': '11:00',
    'RETRY_ATTEMPTS': 3,
    'RETRY_DELAY': 600,
    'INCLUDE_ZERO_SALES_DAYS': True,
    'ATTACHMENT_FORMATS': ['pdf', 'excel'],
    'MAX_EMAIL_SIZE': 25 * 1024 * 1024,
}

DAILY_REPORT_RECIPIENTS = {
    'primary': [DAILY_REPORT_EMAIL],
    'cc': DAILY_REPORT_CC_EMAILS,
    'bcc': [],
}

DAILY_REPORT_CONTENT = {
    'include_summary': True,
    'include_item_breakdown': True,
    'include_payment_methods': True,
    'include_customer_details': True,
    'group_by_receipt': True,
    'show_discounts': True,
    'show_delivery_costs': True,
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {'format': '{levelname} {asctime} {message}', 'style': '{'},
    },
    'handlers': {
        'daily_reports_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'daily_reports.log'),
            'maxBytes': 1024 * 1024 * 5,
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'daily_reports': {
            'handlers': ['daily_reports_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django': {'handlers': ['console'], 'level': 'INFO'},
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

logs_dir = os.path.join(BASE_DIR, 'logs')
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

# =====================================
# CELERY CONFIGURATION
# =====================================
REDIS_URL = config('REDIS_URL', default='redis://localhost:6379/0')

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
