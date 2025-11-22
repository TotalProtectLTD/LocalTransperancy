# AppMagic Metrics Fetcher - Implementation Summary

## 📦 What Was Created

A complete AppMagic metrics fetching system based on the existing `appmagic_fetcher.py` pattern.

### Files Created

1. **appmagic_metrics.py** - Main script (505 lines)
   - Fetches apps from API
   - Bypasses Cloudflare using SeleniumBase
   - Fetches metrics from AppMagic
   - Updates server with data

2. **scheduler/run-appmagic-metrics.sh** - Cron wrapper script
   - Runs every 10 minutes
   - Uses flock for overlap prevention
   - Logs to scheduler/logs/

3. **scheduler/install-appmagic-metrics.sh** - Installation script
   - Adds job to crontab
   - Creates log directories
   - Backs up existing crontab

4. **scheduler/status-appmagic-metrics.sh** - Status checker
   - Shows crontab entry
   - Displays current status
   - Shows recent logs and errors

5. **APPMAGIC_METRICS_QUICKSTART.md** - Quick start guide
   - Installation instructions
   - Usage examples
   - Troubleshooting tips

## 🔄 Workflow

```
┌──────────────────────────────────────────────────────────┐
│  Cron (every 10 minutes)                                 │
└───────────────────────┬──────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│  GET /api/appmagic/next?limit=10                         │
│  Response: [                                             │
│    {                                                     │
│      "id": 123,                                          │
│      "appmagic_id": "456789",                            │
│      "name": "My App",                                   │
│      "last_appmagic_scraped": "2025-11-21T10:00:00Z"     │
│    }                                                     │
│  ]                                                       │
└───────────────────────┬──────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│  If >0 apps: Open Browser with SeleniumBase             │
│  - Navigate to https://appmagic.rocks                    │
│  - Add cookies from appmagic_cookies_fresh.json          │
│  - Visit /top-charts/apps (bypass Cloudflare)            │
└───────────────────────┬──────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│  For each app:                                           │
│  POST https://appmagic.rocks/api/v2/charts/united-applications│
│  Headers:                                                │
│    - Authorization: Bearer u5-AiQHOV9TTBtPTsQ-v2m83ei9fUBcW│
│    - Content-Type: application/json                      │
│  Payload:                                                │
│    {                                                     │
│      "requests": [{                                      │
│        "aggregation": "day",                             │
│        "countries": ["WW"],                              │
│        "dateEnd": "2025-11-21",                          │
│        "dateStart": "2015-01-01",                        │
│        "store": 5,                                       │
│        "id": <appmagic_id>                               │
│      }]                                                  │
│    }                                                     │
└───────────────────────┬──────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│  POST /api/appmagic/apps/{app_id}/metrics                │
│  {                                                       │
│    "data": [{                                            │
│      "downloads": { "first_date": "...", "points": [...] }│
│      "revenue": { "first_date": "...", "points": [...] } │
│      "top_free": { "first_date": "...", "points": [...] }│
│      "top_grossing": { ... },                            │
│      "featuring": { ... }                                │
│    }]                                                    │
│  }                                                       │
│  Response: { "success": true, "rows_stored": 215 }       │
└──────────────────────────────────────────────────────────┘
```

## 🎯 Key Features

### 1. **Overlap Prevention**
- Uses `flock` to prevent concurrent executions
- Safe to run every 10 minutes even if one run takes longer

### 2. **Cloudflare Bypass**
- Uses SeleniumBase with undetected-chrome mode
- Visits landing page before making API requests
- Adds cookies from exported browser session

### 3. **Error Handling**
- Comprehensive try-catch blocks
- Detailed logging of successes and failures
- Graceful degradation (continues processing other apps if one fails)

### 4. **Batch Processing**
- Processes up to 10 apps per run (configurable)
- Individual API calls for each app
- Updates server after each successful fetch

### 5. **Configurable**
- Command-line arguments for all settings
- Environment variable support
- Config file support for secrets

## 📊 Statistics Tracking

The script tracks and reports:
- `total`: Total apps to process
- `processed`: Apps attempted
- `success`: Successfully fetched metrics from AppMagic
- `failed`: Failed to fetch metrics
- `updated`: Successfully updated on server
- `update_failed`: Failed to update on server
- `total_rows_stored`: Total metric rows stored across all apps

## 🔐 Authentication

### Input API (magictransparency.com)
- Header: `X-Incoming-Secret: <token>`
- Token sources (priority):
  1. `--token` flag
  2. `MAGIC_TRANSPARENCY_TOKEN` env var
  3. `config/shared_secret.txt` file
  4. `INCOMING_SHARED_SECRET` constant in script

### AppMagic API
- Header: `Authorization: Bearer u5-AiQHOV9TTBtPTsQ-v2m83ei9fUBcW`
- Hardcoded in script (can be made configurable if needed)

## 🚀 Quick Start

```bash
# 1. Test manually
python3 appmagic_metrics.py --visible --limit 1

# 2. Test headless
python3 appmagic_metrics.py --headless --limit 10

# 3. Install to cron
./scheduler/install-appmagic-metrics.sh

# 4. Check status
./scheduler/status-appmagic-metrics.sh

# 5. View logs
tail -f scheduler/logs/appmagic-metrics.log
```

## 📅 Schedule

**Runs every 10 minutes**
- 00, 10, 20, 30, 40, 50 minutes past every hour
- Processes 10 apps per run
- ~6 runs per hour = ~60 apps per hour

## 🔧 Similar to appmagic_fetcher.py

This script follows the same pattern as `appmagic_fetcher.py`:

| Feature | appmagic_fetcher.py | appmagic_metrics.py |
|---------|---------------------|---------------------|
| **Purpose** | Fetch appmagic_id & appmagic_url | Fetch metrics/charts data |
| **API Endpoint** | `/api/apps/appmagic/missing` | `/api/appmagic/next` |
| **AppMagic Call** | `/api/v2/search` | `/api/v2/charts/united-applications` |
| **Schedule** | Every 15 minutes | Every 10 minutes |
| **Batch Size** | 50 apps | 10 apps |
| **Overlap Prevention** | ✅ flock | ✅ flock |
| **Cloudflare Bypass** | ✅ SeleniumBase | ✅ SeleniumBase |
| **Cookies** | appmagic_cookies_fresh.json | appmagic_cookies_fresh.json |

## 📝 Next Steps

1. **Test the script manually**:
   ```bash
   python3 appmagic_metrics.py --visible --limit 1
   ```

2. **Verify API endpoints exist on server**:
   - `GET /api/appmagic/next?limit=10` ✅
   - `POST /api/appmagic/apps/{app_id}/metrics` ✅

3. **Install to cron when ready**:
   ```bash
   ./scheduler/install-appmagic-metrics.sh
   ```

4. **Monitor logs**:
   ```bash
   tail -f scheduler/logs/appmagic-metrics.log
   ```

## ⚠️ Important Notes

1. **Cookies**: Make sure `appmagic_cookies_fresh.json` exists and is up-to-date
2. **API Token**: Set `MAGIC_TRANSPARENCY_TOKEN` environment variable or use config file
3. **Rate Limiting**: Script includes 1-second delay between apps to avoid rate limiting
4. **Date Range**: Fetches metrics from 2015-01-01 to today (dynamic `dateEnd`)
5. **Store ID**: Uses store=5 (likely App Store ID) - verify this is correct

## 🐛 Known Limitations

1. AppMagic Bearer token is hardcoded (may need to be refreshed periodically)
2. No retry logic for failed requests (could be added)
3. Processes apps sequentially (could be parallelized for speed)
4. Apps without `appmagic_appid` are skipped (need to run appmagic_fetcher.py first)

## 📚 Documentation

- **Quick Start**: `APPMAGIC_METRICS_QUICKSTART.md`
- **This File**: `APPMAGIC_METRICS_IMPLEMENTATION.md`
- **Related**: `ADVERTISER_SCRAPER_QUICKSTART.md`, `PARSER_SCHEDULER_QUICKSTART.md`

