# PythonAnywhere Sync - Usage Guide

## Overview
This guide explains how to sync your local database to PythonAnywhere with duplicate prevention and various sync modes.

## What Was Fixed

### 1. Duplicate Prevention
- **Added local IDs**: All receipts, sales, and payments now include `local_receipt_id`, `local_sale_id`, and `local_payment_id`
- **API checks**: The PythonAnywhere API checks these IDs before creating records
- **Result**: No more duplicate entries when syncing multiple times

### 2. Full Historical Sync
- **New `--full` flag**: Sync ALL data from database inception (not just last 90 days)
- **Complete history**: Syncs all receipts, sales, and payments ever recorded
- **One-time operation**: Use this for initial sync to customer systems

### 3. Missing Data Fields
- **Added fields**: `discount_amount`, `discount_percentage`, `delivery_cost`, `payment_date`
- **Complete records**: All data now matches your local database structure

## Sync Modes

### 1. Standard Sync (Last 90 Days)
Syncs data from the last 90 days.

```batch
sync_all_data.bat
```

OR

```batch
"C:\III\.venv\Scripts\python.exe" sync_to_pythonanywhere.py
```

**Use when**: Regular sync for recent data

---

### 2. Incremental Sync (Recent Changes Only)
Syncs only data that changed since the last sync (tracks last sync time).

```batch
"C:\III\.venv\Scripts\python.exe" sync_to_pythonanywhere.py --incremental
```

**Use when**: Automated/scheduled syncs (Celery task uses this mode)

**Benefits**:
- Faster execution
- Less network bandwidth
- Minimal server load

---

### 3. Full Historical Sync (Database Inception)
Syncs ALL data from the beginning of your database to now.

```batch
sync_full_history.bat
```

OR

```batch
"C:\III\.venv\Scripts\python.exe" sync_to_pythonanywhere.py --full
```

**Use when**:
- First-time deployment to customer system
- Recovering from data loss
- Complete data migration
- Initial setup

**Warning**: This may take a long time depending on your database size.

---

## Automated Sync (Celery)

### Celery Task Configuration
The system is already configured to sync every 30 minutes using Celery Beat.

**Configuration Location**: `C:\III\mystore\mystore\settings.py`

```python
CELERY_BEAT_SCHEDULE = {
    'sync-to-pythonanywhere-every-30-minutes': {
        'task': 'store.tasks.sync_to_pythonanywhere_task',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
        'options': {
            'expires': 1800,  # Task expires after 30 minutes if not executed
        }
    },
}
```

### Running Celery Workers

**Start Celery Worker**:
```batch
cd C:\III\mystore
celery -A mystore worker -l info --pool=solo
```

**Start Celery Beat (Scheduler)**:
```batch
cd C:\III\mystore
celery -A mystore beat -l info
```

**Both Together** (recommended):
```batch
cd C:\III\mystore
celery -A mystore worker -l info --pool=solo -B
```

### Manual Sync with Logging (For Scheduled Tasks)
Use the provided batch file that includes logging:

```batch
sync_incremental_30min.bat
```

This creates log files in `C:\III\sync_logs\` for tracking sync operations.

---

## How Duplicate Prevention Works

### Products
- **Primary key**: `barcode_number` (if available)
- **Fallback**: Combination of `brand`, `size`, `color`, `location`
- **Behavior**: Updates existing products, creates new ones if not found

### Receipts, Sales, Payments
- **Primary key**: `local_receipt_id`, `local_sale_id`, `local_payment_id`
- **Behavior**:
  - If local ID exists in PythonAnywhere → **SKIP** (already synced)
  - If local ID not found → **CREATE** new record
  - **NEVER DUPLICATES** - same data won't be synced twice

---

## Troubleshooting

### Sync Fails with Authentication Error
**Check**:
1. Username and password in `sync_to_pythonanywhere.py` (lines 37-38)
2. User exists in PythonAnywhere Django admin
3. PythonAnywhere app is running

### Duplicate Data Still Appearing
**Cause**: Old syncs before the fix didn't include local IDs

**Solution**:
1. Clear all data on PythonAnywhere (or delete duplicates)
2. Run full historical sync with the updated script:
   ```batch
   sync_full_history.bat
   ```

### Sync Timeout
**Cause**: Too much data to sync at once

**Solution**:
1. The script already uses batching (50 products, 20 receipts per batch)
2. For very large databases, sync in smaller chunks:
   - Sync products first
   - Then sync receipts/sales in date ranges

### Missing Recent Data
**Check**:
1. Last sync time: `C:\III\.last_sync_time.txt`
2. If using incremental mode, it only syncs changes since last sync
3. Use standard or full mode to sync everything

---

## Log Files

### Sync Logs Location
`C:\III\sync_logs\`

### Log Retention
- Automatically cleaned up after 30 days
- Each sync creates a timestamped log file

### View Recent Sync Logs
```batch
dir C:\III\sync_logs
type C:\III\sync_logs\sync_YYYYMMDD_HHMMSS.log
```

---

## Deployment Checklist for Customer Systems

### First-Time Setup
1. Install dependencies on customer system
2. Configure API credentials in `sync_to_pythonanywhere.py`
3. Run full historical sync:
   ```batch
   sync_full_history.bat
   ```
4. Verify data on PythonAnywhere
5. Set up Celery for automated syncs (optional)

### Ongoing Maintenance
- Celery runs automatic syncs every 30 minutes
- Monitor log files for errors
- Manually run `sync_all_data.bat` if needed

---

## API Endpoints

### Products Sync
`POST https://asoniguguru.pythonanywhere.com/api/oem/sync/products/`

### Receipts/Sales/Payments Sync
`POST https://asoniguguru.pythonanywhere.com/api/oem/sync/receipts/`

### Authentication
`POST https://asoniguguru.pythonanywhere.com/api/oem/token/`

---

## Summary

- **Use `sync_full_history.bat`** for first-time customer deployments (syncs all historical data)
- **Use `sync_all_data.bat`** for regular manual syncs (last 90 days)
- **Use Celery** for automated syncs every 30 minutes (incremental mode)
- **Duplicate prevention** is now enabled - same data won't be synced twice
- **All data fields** are now included (discounts, delivery costs, payment dates)

---

## Files Created/Updated

### New Files
1. `sync_full_history.bat` - Full historical sync from database inception
2. `sync_incremental_30min.bat` - For scheduled/Celery tasks with logging
3. `SYNC_USAGE_GUIDE.md` - This documentation

### Updated Files
1. `sync_to_pythonanywhere.py` - Added duplicate prevention, full history mode, missing fields

### Existing Files (Unchanged)
1. `sync_all_data.bat` - Standard sync (last 90 days)
2. `mystore/store/tasks.py` - Celery task configuration
3. `mystore/mystore/settings.py` - Celery Beat schedule (already configured for 30-min interval)
