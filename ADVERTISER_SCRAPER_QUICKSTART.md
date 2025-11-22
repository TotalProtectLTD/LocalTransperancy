# Advertiser Batch Scraper - Quick Start Guide

## Prerequisites

### 1. Database Setup
The script requires the `advertisers` table with a `status` column:

```sql
-- Check if advertisers table exists
SELECT COUNT(*) FROM advertisers WHERE advertiser_name ILIKE '%Apps%';

-- Verify required columns exist (status column is required)
\d advertisers
```

**Required columns:**
- `advertiser_id` (TEXT, PRIMARY KEY)
- `advertiser_name` (TEXT)
- `status` (TEXT) - for tracking scraping state
- `daily_7` (INTEGER) - optional, for storing ads daily count
- `last_scraped_at` (TIMESTAMP) - optional, for tracking when scraped
- `error_message` (TEXT) - optional, for error tracking

### 2. Python Dependencies
```bash
# Install required packages
pip install httpx playwright psycopg2-binary playwright-stealth

# Install Playwright browsers
playwright install chromium
```

### 3. Database Connection
Verify PostgreSQL is running and accessible:
```bash
psql -h localhost -U transparency_user -d local_transparency
```

## Basic Usage

### 1. Test Run (Single Batch)
**Start with this to verify everything works:**

```bash
python3 advertiser_batch_scraper.py --max-concurrent 1 --max-batches 1
```

This will:
- Run 1 worker
- Process 1 batch of 20 advertisers
- Stop after completing the batch
- Take ~5-15 minutes depending on advertiser sizes

### 2. Production Run (Default Settings)
```bash
python3 advertiser_batch_scraper.py
```

This uses:
- **3 concurrent workers**
- **20 advertisers per batch**
- **500 page limit per batch**
- **Compact logging** (clean output)

### 3. Verbose Mode (For Debugging)
```bash
python3 advertiser_batch_scraper.py --verbose
```

Shows all detailed logs including:
- Cookie acquisition
- Individual page scraping
- Proxy details
- Database operations

### 4. High Concurrency Mode
```bash
python3 advertiser_batch_scraper.py --max-concurrent 5
```

Runs 5 workers in parallel (faster but more API load).

### 5. Custom Batch Size
```bash
python3 advertiser_batch_scraper.py --batch-size 10
```

Process 10 advertisers per batch instead of default 20.

## Command Line Options

```bash
python3 advertiser_batch_scraper.py [OPTIONS]

Options:
  --max-concurrent N    Number of concurrent workers (default: 3)
  --batch-size N        Advertisers per batch (default: 20)
  --max-batches N       Limit number of batches (for testing)
  --verbose            Show detailed logs
  -h, --help           Show help message
```

## Example Commands

### Test Mode (Recommended First Run)
```bash
# Single worker, single batch, verbose output
python3 advertiser_batch_scraper.py --max-concurrent 1 --max-batches 1 --verbose
```

### Development Mode
```bash
# 2 workers, verbose logging
python3 advertiser_batch_scraper.py --max-concurrent 2 --verbose
```

### Production Mode
```bash
# 3 workers, compact logs (default)
python3 advertiser_batch_scraper.py
```

### High Performance Mode
```bash
# 5 workers, compact logs, save to file
python3 advertiser_batch_scraper.py --max-concurrent 5 > scraper.log 2>&1
```

### Limited Run for Testing
```bash
# Process only 2 batches then stop
python3 advertiser_batch_scraper.py --max-concurrent 2 --max-batches 2
```

## Expected Output

### Startup
```
================================================================================
GOOGLE ADS TRANSPARENCY CENTER - ADVERTISER BATCH SCRAPER
================================================================================

🔄 Checking for stuck 'processing' advertisers...
   No stuck advertisers found

Advertisers Table Statistics (name contains 'Apps'):
  Total:      1247
  NULL:       856
  Pending:    234
  Processing: 0
  Completed:  142
  Failed:     15

Scraper Configuration:
  Max concurrent workers: 3
  Advertisers per batch:  20
  Cumulative page limit:  500 pages per batch
  Date range:             Current UTC - 7 days to current UTC
  Proxy source:           MagicTransparency API
  Verbose logging:        ✗ OFF (use --verbose for details)

🚀 Starting 3 concurrent workers...
================================================================================
```

### During Execution (Compact Mode)
```
[Worker 0] 📦 Batch: 20 advertisers
[Worker 0] [1/20] Big Fish Games Apps
[Worker 0] ✅ 127 creatives, 4 pages, daily_7=45 (+89 new, 38 dup)
[Worker 0] [2/20] King Apps Store
[Worker 0] ✅ 234 creatives, 8 pages, daily_7=78 (+201 new, 33 dup)
[Worker 0] [3/20] Mobile Apps Factory
[Worker 0] ✅ 56 creatives, 2 pages, daily_7=23 (+48 new, 8 dup)
...
[Worker 0] ✓ Batch done: 45.3s, 145 pages

[Worker 1] 📦 Batch: 20 advertisers
...
```

### Completion
```
================================================================================
SCRAPER COMPLETE
================================================================================
Total duration:       127.5s (2.1 min)
Batches processed:    3
Advertisers completed: 52
Advertisers failed:   1
Total creatives:      6,847
Total pages scraped:  1,245
Avg creatives/advertiser: 131.7
Avg pages/advertiser:     24.0
```

## What the Script Does

### For Each Advertiser:

1. **Gets Cookies**
   - Visits `https://adstransparency.google.com/?region=anywhere`
   - Extracts session cookies

2. **Scrapes SearchCreatives API**
   - Date range: Current UTC - 7 days to current UTC
   - Paginate through all results
   - Extract creative IDs and `daily_7` estimate

3. **Saves to Database**
   - Inserts creatives to `creatives_fresh` table
   - `created_at` = `2015-MM-DD` format
   - `ON CONFLICT DO NOTHING` (skips duplicates)

4. **Updates Advertiser Status**
   - `status` = `'completed'`
   - `daily_7` = ads daily estimate
   - `last_scraped_at` = current UTC timestamp

### Batch Behavior:

- Processes **20 advertisers per batch** (configurable)
- Tracks **cumulative pages** across batch
- If cumulative pages **≥ 500**:
  - Completes current advertiser
  - Marks remaining advertisers as `'pending'`
  - Ends worker

## Monitoring Progress

### Check Database Status
```sql
-- See what's being processed
SELECT 
    status, 
    COUNT(*) 
FROM advertisers 
WHERE advertiser_name ILIKE '%Apps%' 
GROUP BY status;

-- View recent completions
SELECT 
    advertiser_name,
    status,
    daily_7,
    last_scraped_at
FROM advertisers 
WHERE status = 'completed' 
ORDER BY last_scraped_at DESC 
LIMIT 10;

-- Check for errors
SELECT 
    advertiser_name,
    error_message
FROM advertisers 
WHERE status = 'failed';
```

### Check Creatives Inserted
```sql
-- Count creatives inserted today
SELECT COUNT(*) 
FROM creatives_fresh 
WHERE created_at::date = CURRENT_DATE;

-- See recent creatives
SELECT 
    creative_id,
    advertiser_id,
    created_at
FROM creatives_fresh 
ORDER BY id DESC 
LIMIT 20;
```

### Monitor Live Progress
```bash
# In another terminal, watch database changes
watch -n 5 'psql -h localhost -U transparency_user -d local_transparency -c "SELECT status, COUNT(*) FROM advertisers WHERE advertiser_name ILIKE '\''%Apps%'\'' GROUP BY status;"'
```

## Troubleshooting

### No Advertisers to Process
```
⚠️  No advertisers available to process
```

**Solution:** Check that advertisers exist with status NULL, 'pending', or 'failed':
```sql
SELECT COUNT(*) FROM advertisers 
WHERE advertiser_name ILIKE '%Apps%' 
AND (status IS NULL OR status IN ('pending', 'failed'));
```

### Proxy Acquisition Fails
```
[WARN] Proxy API returned 401, retrying... (attempt 1)
```

**Solution:** Check `PROXY_ACQUIRE_SECRET` in the script matches your API key.

### Database Connection Error
```
ERROR: Missing dependencies
```

**Solution:** 
```bash
pip install psycopg2-binary
```

### Stuck Processing Status
The script auto-resets stuck advertisers on startup. If needed, manually reset:
```sql
UPDATE advertisers 
SET status = 'pending' 
WHERE status = 'processing' 
AND advertiser_name ILIKE '%Apps%';
```

### Page Limit Hit Frequently
```
[Worker 0] ⚠️  Page limit reached: 502/500
```

**Solution:** Increase `CUMULATIVE_PAGE_LIMIT` in the script or reduce `batch_size`.

## Running in Background

### Using nohup
```bash
nohup python3 advertiser_batch_scraper.py > scraper.log 2>&1 &

# Check progress
tail -f scraper.log

# Check if running
ps aux | grep advertiser_batch_scraper
```

### Using screen
```bash
# Start screen session
screen -S advertiser_scraper

# Run script
python3 advertiser_batch_scraper.py

# Detach: Ctrl+A, then D

# Reattach later
screen -r advertiser_scraper
```

### Using systemd (Linux)
Create `/etc/systemd/system/advertiser-scraper.service`:
```ini
[Unit]
Description=Advertiser Batch Scraper
After=network.target postgresql.service

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/LocalTransperancy
ExecStart=/usr/bin/python3 /path/to/LocalTransperancy/advertiser_batch_scraper.py
Restart=on-failure
RestartSec=300

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl start advertiser-scraper
sudo systemctl status advertiser-scraper
sudo journalctl -u advertiser-scraper -f
```

## Performance Tips

1. **Start Small**: Test with `--max-concurrent 1 --max-batches 1`
2. **Monitor Resources**: Watch CPU, memory, and network usage
3. **Increase Gradually**: Scale up workers based on system capacity
4. **Use Compact Logs**: Default mode is optimized for production
5. **Save Logs**: Redirect output to file for analysis: `> scraper.log 2>&1`

## Next Steps

After running successfully:
1. Check `creatives_fresh` table for new creatives
2. Verify `advertisers` table updated with `daily_7` and `last_scraped_at`
3. Review failed advertisers and retry if needed
4. Set up scheduled runs (cron/systemd timer)

## Quick Reference

```bash
# Test run
python3 advertiser_batch_scraper.py --max-concurrent 1 --max-batches 1 --verbose

# Production run
python3 advertiser_batch_scraper.py

# Background run with logs
nohup python3 advertiser_batch_scraper.py > scraper.log 2>&1 &

# Check status
tail -f scraper.log

# Monitor database
psql -h localhost -U transparency_user -d local_transparency
```

---

**Ready to start? Run the test command first:**
```bash
python3 advertiser_batch_scraper.py --max-concurrent 1 --max-batches 1 --verbose
```

