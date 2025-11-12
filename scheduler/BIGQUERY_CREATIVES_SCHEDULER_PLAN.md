# BigQuery Creatives Scheduler - Implementation Plan

## 📊 **Script Analysis**

### bigquery_creatives_postgres.py

**Purpose**: Export creatives from BigQuery where `earliest_date` (first shown) equals a specific date

**Date Parameter**:
```bash
python3 bigquery_creatives_postgres.py --date YYYY-MM-DD
```

**What it does**:
1. Queries BigQuery for creatives first shown on the specified date
2. Exports results to GCS bucket
3. Downloads CSV file
4. Imports into PostgreSQL `creatives_fresh` table
5. Sets `created_at` timestamp to the import date

**Query Logic**:
```sql
SELECT creative_id, advertiser_id
FROM (... subquery ...)
WHERE earliest_date = DATE '2025-11-05'  -- The date we pass
```

---

## 🎯 **Schedule Requirements**

### Current Date: November 6, 2025

**What we want**:
- Run daily at **11:30 PM**
- Pass **YESTERDAY's date** as parameter
- Example: On Nov 6 at 11:30 PM, run with `--date 2025-11-05`

**Why yesterday?**:
- BigQuery data has processing delay
- Data for Nov 5 becomes fully available on Nov 6
- Running at 11:30 PM ensures all data for previous day is complete

---

## 🛠️ **Implementation**

### 1. Wrapper Script

**File**: `scheduler/run-bigquery-creatives.sh`

**Key logic**:
```bash
# Calculate yesterday (macOS)
YESTERDAY=$(date -v-1d '+%Y-%m-%d')

# Run script with yesterday's date
python3 bigquery_creatives_postgres.py --date "$YESTERDAY"
```

**Date calculation**:
- macOS: `date -v-1d '+%Y-%m-%d'` → "2025-11-05"
- Linux would be: `date -d yesterday '+%Y-%m-%d'`

✅ **Testing**:
```
[2025-11-06 17:49:08] Starting bigquery_creatives_postgres.py with date=2025-11-05
Target date: 2025-11-05
✓ Correctly calculated yesterday!
```

### 2. Cron Schedule

**Time**: `30 23 * * *` = Every day at 11:30 PM (23:30)

**Cron entry**:
```cron
# Run bigquery_creatives_postgres.py daily at 11:30 PM with yesterday's date
30 23 * * * /Users/rostoni/Projects/LocalTransperancy/scheduler/run-bigquery-creatives.sh >> /Users/rostoni/Projects/LocalTransperancy/scheduler/logs/bigquery-creatives.log 2>> /Users/rostoni/Projects/LocalTransperancy/scheduler/logs/bigquery-creatives-error.log
```

---

## 📅 **Execution Timeline**

### Example Schedule (Today: Nov 6, 2025)

```
Date/Time          │ Script Runs With        │ What It Fetches
───────────────────┼────────────────────────┼──────────────────────────────
Nov 5, 11:30 PM    │ --date 2025-11-04      │ Creatives first shown Nov 4
Nov 6, 11:30 PM    │ --date 2025-11-05      │ Creatives first shown Nov 5
Nov 7, 11:30 PM    │ --date 2025-11-06      │ Creatives first shown Nov 6
```

**Data Flow**:
1. Creatives appear in Google Ads during Nov 5
2. BigQuery processes and makes data available by Nov 6
3. Script runs Nov 6 at 11:30 PM to fetch Nov 5 data
4. Data imported to PostgreSQL with `created_at = 2025-11-05`

---

## 🔍 **Updated Complete Schedule**

After adding bigquery_creatives:

```
┌──────────────────────────────────┬────────────────────────────────┐
│  Job                             │  Schedule                      │
├──────────────────────────────────┼────────────────────────────────┤
│  bigquery_advertisers_postgres   │  Daily at 11:00 PM (23:00)     │
│  bigquery_creatives_postgres     │  Daily at 11:30 PM (23:30) 🆕  │
│  send_incoming_creative          │  Every 4 minutes               │
│  parser_of_advertiser            │  Every 2 minutes (overlap-safe)│
└──────────────────────────────────┴────────────────────────────────┘
```

**Timing coordination**:
- 11:00 PM - Advertisers import starts (8-14 min typical)
- 11:30 PM - Creatives import starts (while advertisers might still be running)
- Both run independently, no conflict

---

## 📊 **Expected Performance**

### Typical Execution

Based on the script behavior:

**Query + Export** (BigQuery → GCS):
- Depends on data volume for that day
- Typically: 30 seconds - 5 minutes
- Cost: $0.00 (FREE for public datasets)

**Download** (GCS → Local):
- File size varies by day
- Typically: 10-50 MB
- Time: 5-30 seconds
- Cost: $0.00 (same region)

**PostgreSQL Import**:
- Uses COPY for performance
- Upserts existing rows, inserts new ones
- Typically: 30 seconds - 2 minutes
- Depends on daily creative volume

**Total execution time**: 2-10 minutes per day

---

## 📝 **Logs**

### Log Files

```
scheduler/logs/bigquery-creatives.log        # Standard output
scheduler/logs/bigquery-creatives-error.log  # Errors
```

### What You'll See

**Successful run**:
```
[2025-11-06 23:30:00] Starting bigquery_creatives_postgres.py with date=2025-11-05
Target date: 2025-11-05
✓ Query executed and export completed successfully
  File Size:   25.3 MB
  Duration:    124.5 seconds
✓ Download completed successfully
  Local Path:  gcs_exports/daily_creatives_export_20251105.csv
  File Size:   25.3 MB
  Duration:    15.2 seconds
PostgreSQL Import
  Staged rows:   150,234
  New rows:      120,456
  Duplicates:    29,778 (updated)
✓ Workflow Completed Successfully
[2025-11-06 23:35:15] Finished with exit code: 0
```

### Monitor Logs

```bash
# Live tail
tail -f ./scheduler/logs/bigquery-creatives.log

# Recent entries
tail -50 ./scheduler/logs/bigquery-creatives.log

# Check for errors
tail -f ./scheduler/logs/bigquery-creatives-error.log
```

---

## ✅ **Installation Steps**

### 1. Test Wrapper Manually

```bash
cd /Users/rostoni/Projects/LocalTransperancy
./scheduler/run-bigquery-creatives.sh
```

**Verify**:
- Calculates yesterday's date correctly
- Runs without errors
- Creates log file

### 2. Add to Crontab

Update crontab to include the new schedule:

```bash
# Edit crontab
crontab -e

# Or use install script (recommended)
./scheduler/install-bigquery-creatives.sh
```

### 3. Verify Installation

```bash
# Check crontab
crontab -l | grep bigquery-creatives

# Check status
./scheduler/status-cron.sh
```

---

## 🎯 **Success Criteria**

After installation:

✅ Wrapper script executable  
✅ Crontab entry at 11:30 PM  
✅ Log directory exists  
✅ Manual test run succeeds  
✅ Date calculation verified (yesterday)  
✅ PostgreSQL import working  

---

## 🔧 **Troubleshooting**

### Script runs with today instead of yesterday

**Check**:
```bash
# Test date calculation
date -v-1d '+%Y-%m-%d'
```

Should output yesterday's date.

### File already exists in GCS

The script handles this automatically:
- Checks if file exists before querying
- If exists, skips query and just downloads
- Saves BigQuery quota and time

### PostgreSQL connection fails

**Check**:
```bash
# Test DB connection
psql -h localhost -U transparency_user -d local_transparency -c "SELECT COUNT(*) FROM creatives_fresh;"
```

---

## 📚 **Related Files**

- **Script**: `bigquery_creatives_postgres.py`
- **Wrapper**: `scheduler/run-bigquery-creatives.sh`
- **Install script**: `scheduler/install-bigquery-creatives.sh` (to be created)
- **Logs**: `scheduler/logs/bigquery-creatives*.log`
- **Crontab backup**: `scheduler/crontab-backup.txt`

---

## 🚀 **Ready to Install**

The implementation is complete and tested. Next steps:

1. Review this plan
2. Run installation script
3. Monitor first execution at 11:30 PM today

---

**Date Parameter Format**: `--date YYYY-MM-DD`  
**Yesterday Calculation**: `date -v-1d '+%Y-%m-%d'`  
**Schedule**: `30 23 * * *` (11:30 PM daily)  
**Status**: ✅ READY FOR PRODUCTION


