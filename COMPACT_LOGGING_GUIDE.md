# Compact Logging System - Advertiser Batch Scraper

## Overview

The script now features a **two-tier logging system**:
- **Compact Mode (Default)**: Shows only essential progress and errors
- **Verbose Mode**: Shows all detailed INFO logs for debugging

## Usage

```bash
# Compact mode (default) - clean output
python3 advertiser_batch_scraper.py

# Verbose mode - detailed logs
python3 advertiser_batch_scraper.py --verbose
```

## Compact Mode Output (Default)

### What You'll See:

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

[Worker 0] 📦 Batch: 20 advertisers
[Worker 0] [1/20] Big Fish Games Apps
[Worker 0] ✅ 127 creatives, 4 pages, daily_7=45 (+89 new, 38 dup)
[Worker 0] [2/20] King Apps Store
[Worker 0] ✅ 234 creatives, 8 pages, daily_7=78 (+201 new, 33 dup)
[Worker 0] [3/20] Mobile Apps Factory
[Worker 0] ⚠️  Page limit reached: 502/500
[Worker 0] 🔄 Marking 17 unfinished as pending
[Worker 0] ✓ Batch done: 45.3s, 502 pages

[Worker 1] 📦 Batch: 20 advertisers
...

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

### What's Hidden in Compact Mode:
- Cookie acquisition details
- Individual page-by-page pagination (only shows every 10th page)
- Proxy server details
- Database query internals
- Debug information

### What's Always Shown:
- ✅ **Successes** with key metrics
- ❌ **Errors** with message preview
- ⚠️ **Warnings** (rate limits, page limits, etc.)
- 📦 **Batch starts**
- 🔄 **Status changes**
- ✓ **Completions**

## Verbose Mode Output

When you add `--verbose`, you'll see:

```
[INFO] [Worker 0] Getting cookies for AR05226884764400615425
[INFO] [Worker 0] Got 8 cookies
[INFO] [Worker 0] Got proxy: hub-us-8.litport.net:31337
[INFO] [Worker 0] Page 1: 35 creatives, daily_7=127
[INFO] [Worker 0] Page 2: 72 creatives total
[INFO] [Worker 0] Page 3: 108 creatives total
...
[INFO] [Worker 0] Page 10: 350 creatives total
[INFO] [Worker 0] Completed: 22 pages, 847 creatives
[INFO] Cumulative pages in batch: 22
```

## Log Levels

| Level | Compact Mode | Verbose Mode | Description |
|-------|--------------|--------------|-------------|
| ERROR | ✅ Always shown | ✅ Always shown | Critical errors |
| WARN | ✅ Always shown | ✅ Always shown | Warnings (rate limits, retries) |
| INFO | ❌ Hidden | ✅ Shown | Detailed progress |
| Compact | ✅ Always shown | ✅ Always shown | Key progress updates |

## Key Features

### Smart Pagination Logging
- **Compact**: Shows every 10th page only
- **Verbose**: Shows every page
- Final totals always shown

### Proxy Retry Logging
- Shows first failure immediately
- Then only every 5th retry attempt
- Prevents log spam during API issues

### Advertiser Name Truncation
- Names truncated to 40 characters for clean display
- Full names available in verbose mode

### Progress Indicators
- 📦 Batch start
- [N/M] Position in batch
- ✅ Success
- ❌ Failure
- ⚠️ Warning
- 🔄 Pending update
- ✓ Completion

## Statistics Display

### Per Advertiser:
```
[Worker 0] ✅ 127 creatives, 4 pages, daily_7=45 (+89 new, 38 dup)
```
- Creatives found
- Pages scraped
- Daily_7 (ads per day estimate)
- New records inserted
- Duplicates skipped

### Per Batch:
```
[Worker 0] ✓ Batch done: 45.3s, 502 pages
```
- Duration
- Total pages in batch

### Final Summary:
- Total duration
- Batches completed
- Advertisers processed (completed/failed)
- Total creatives collected
- Averages

## When to Use Verbose Mode

Use `--verbose` when:
- 🐛 Debugging issues
- 🔍 Investigating specific advertiser behavior
- 📊 Analyzing pagination patterns
- 🔧 Troubleshooting proxy problems
- 📝 Creating detailed reports

Use **compact mode** (default) when:
- ✅ Production runs
- 🚀 Large batch processing
- 📺 Monitoring from dashboard
- 🔄 Regular scheduled runs

## Example Comparison

### Compact Mode (Clean):
```
[Worker 0] [1/20] Big Fish Games Apps
[Worker 0] ✅ 127 creatives, 4 pages, daily_7=45 (+89 new, 38 dup)
```

### Verbose Mode (Detailed):
```
[INFO] [Worker 0] Processing (1/20): AR05226884764400615425 - Big Fish Games Apps
[INFO] [Worker 0] Getting cookies for AR05226884764400615425
[INFO] [Worker 0] Got 8 cookies
[INFO] [Worker 0] Got proxy: hub-us-8.litport.net:31337
[INFO] [Worker 0] Page 1: 35 creatives, daily_7=127
[INFO] [Worker 0] Page 2: 72 creatives total
[INFO] [Worker 0] Page 3: 108 creatives total
[INFO] [Worker 0] Page 4: 127 creatives total
[INFO] [Worker 0] Completed: 4 pages, 127 creatives
[Worker 0] ✅ 127 creatives, 4 pages, daily_7=45 (+89 new, 38 dup)
[INFO] Cumulative pages in batch: 4
```

---

## Tips

1. **Start with compact mode** for production
2. **Use verbose mode** for first test run
3. **Redirect to file** for later analysis:
   ```bash
   python3 advertiser_batch_scraper.py --verbose > scraper.log 2>&1
   ```
4. **Combine with grep** for filtering:
   ```bash
   python3 advertiser_batch_scraper.py | grep -E "✅|❌|⚠️"
   ```

---

**The compact logging system reduces output by ~90% while keeping all critical information visible!**

