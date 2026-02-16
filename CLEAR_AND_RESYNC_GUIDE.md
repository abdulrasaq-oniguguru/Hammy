# Clear PythonAnywhere Database and Re-Sync

## Why Clear and Re-Sync?
- ✅ Ensures all data uses the correct timezone (Africa/Lagos)
- ✅ Eliminates any cached or miscalculated data
- ✅ Fresh start with proper settings
- ✅ Guarantees data matches your local system

---

## Option 1: Clear via PythonAnywhere Console (RECOMMENDED)

### Step 1: Open PythonAnywhere Console
1. Login to https://www.pythonanywhere.com
2. Go to **Consoles** tab
3. Click **"Bash"** to open a new console

### Step 2: Run Django Shell
```bash
cd ~/minimal_api
python manage.py shell
```

### Step 3: Delete All Synced Data
Copy and paste this into the shell:

```python
from store.models import Receipt, Sale, Payment, PaymentMethod, Product

# Count records before deletion
print(f"Before deletion:")
print(f"  Products: {Product.objects.count()}")
print(f"  Receipts: {Receipt.objects.count()}")
print(f"  Sales: {Sale.objects.count()}")
print(f"  Payments: {Payment.objects.count()}")
print(f"  Payment Methods: {PaymentMethod.objects.count()}")

# Delete all synced data (keeps database structure)
print("\nDeleting all data...")
PaymentMethod.objects.all().delete()
Payment.objects.all().delete()
Sale.objects.all().delete()
Receipt.objects.all().delete()
Product.objects.all().delete()

print("\nAfter deletion:")
print(f"  Products: {Product.objects.count()}")
print(f"  Receipts: {Receipt.objects.count()}")
print(f"  Sales: {Sale.objects.count()}")
print(f"  Payments: {Payment.objects.count()}")
print(f"  Payment Methods: {PaymentMethod.objects.count()}")

print("\n✅ Database cleared! Ready for fresh sync.")
```

### Step 4: Exit Shell
```python
exit()
```

---

## Option 2: Clear via Django Admin (Alternative)

1. Go to: https://asoniguguru.pythonanywhere.com/admin/
2. Login with admin credentials
3. Manually delete:
   - All **Payment Methods**
   - All **Payments**
   - All **Sales**
   - All **Receipts**
   - All **Products**

⚠️ **Note**: This is slower for large datasets. Use Option 1 for speed.

---

## Option 3: Reset Database Completely (Nuclear Option)

**Only use if you want to completely reset everything including users:**

```bash
cd ~/minimal_api
rm db.sqlite3  # Delete the database file
python manage.py migrate  # Recreate tables
python manage.py createsuperuser  # Recreate admin user
```

⚠️ **Warning**: This deletes EVERYTHING including admin users!

---

## After Clearing: Re-Sync All Data

### Step 1: Delete Local Sync Timestamp
This ensures a full sync:
```batch
del C:\III\.last_sync_time.txt
```

### Step 2: Run Full Historical Sync
```batch
sync_full_history_robust.bat
```

OR

```batch
"C:\III\.venv\Scripts\python.exe" sync_to_pythonanywhere_robust.py --full
```

### Step 3: Verify Data
Check PythonAnywhere reports:
- https://asoniguguru.pythonanywhere.com/api/oem/reports/

Should now show:
- ✅ Correct number of receipts
- ✅ Correct revenue figures
- ✅ Correct analytics
- ✅ All dates in Africa/Lagos timezone

---

## Quick Verification Script

After re-syncing, run this to compare:
```batch
"C:\III\.venv\Scripts\python.exe" compare_local_vs_remote.py
```

Should show:
- ✅ Same receipt count
- ✅ Same revenue totals
- ✅ No missing receipts

---

## Recommended Approach

**For a clean, guaranteed fix:**

1. ✅ Clear database via PythonAnywhere console (Option 1)
2. ✅ Delete local sync timestamp
3. ✅ Run full historical sync
4. ✅ Verify data matches

**Total time**: ~10-15 minutes for complete re-sync

---

## What If Something Goes Wrong?

Don't worry! Your local database is untouched. You can always:
1. Clear PythonAnywhere again
2. Re-sync from local
3. All data is safely stored locally

---

## After Re-Sync Completes

Your PythonAnywhere will have:
- ✅ All products (1918 items)
- ✅ All receipts (401 receipts from inception)
- ✅ All sales and payments
- ✅ Correct timezone (Africa/Lagos)
- ✅ Perfect data accuracy
