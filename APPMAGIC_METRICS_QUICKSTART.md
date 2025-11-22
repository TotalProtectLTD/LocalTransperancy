# appmagic_metrics.py - Quick Start Guide

## 🚀 What It Does

Fetches AppMagic metrics (charts/analytics data) for apps:
1. Gets next apps from API that need metrics update
2. Opens browser and bypasses Cloudflare
3. Fetches metrics from AppMagic's `charts/united-applications` endpoint
4. Updates server with the fetched data

## 📋 Prerequisites

```bash
# Install SeleniumBase if not already installed
pip install seleniumbase

# Make sure you have fresh AppMagic cookies
# Cookie file: appmagic_cookies_fresh.json
```

## 🎯 Manual Test Run

```bash
cd /Users/rostoni/Projects/LocalTransperancy

# Test with visible browser (10 apps)
python3 appmagic_metrics.py --visible --limit 10

# Test with headless browser (recommended for scheduler)
python3 appmagic_metrics.py --headless --limit 10
```

## ⚙️ Install Scheduler (1 Command)

```bash
cd /Users/rostoni/Projects/LocalTransperancy
./scheduler/install-appmagic-metrics.sh
```

This will:
- Add cron job to run every 10 minutes
- Use flock to prevent overlapping executions
- Process 10 apps per run

## 📊 Check Status

```bash
./scheduler/status-appmagic-metrics.sh
```

## 📝 View Logs

```bash
# Live tail
tail -f ./scheduler/logs/appmagic-metrics.log

# Last 50 lines
tail -50 ./scheduler/logs/appmagic-metrics.log

# Errors only
tail -f ./scheduler/logs/appmagic-metrics-error.log
```

## 🔧 How It Works

```
Every 10 minutes:
    ↓
Get next 10 apps from API
    ↓
If >0 apps found:
    ↓
Open browser → Bypass Cloudflare
    ↓
For each app:
    - Fetch metrics from AppMagic
    - Update server with data
    ↓
Done (wait 10 minutes)
```

## 📡 API Endpoints Used

### Input (Get Next Apps)
- **Endpoint**: `GET /api/appmagic/next?limit=10`
- **Headers**: `X-Incoming-Secret: <token>`
- **Response**: List of apps with `id`, `appmagic_id`, `name`, `last_appmagic_scraped`

### AppMagic Request
- **Endpoint**: `POST https://appmagic.rocks/api/v2/charts/united-applications`
- **Headers**: 
  - `Authorization: Bearer u5-AiQHOV9TTBtPTsQ-v2m83ei9fUBcW`
  - `Content-Type: application/json`
- **Payload**:
  ```json
  {
    "requests": [{
      "aggregation": "day",
      "countries": ["WW"],
      "dateEnd": "2025-11-21",
      "dateStart": "2015-01-01",
      "store": 5,
      "id": <appmagic_id>
    }]
  }
  ```

### Output (Update Server)
- **Endpoint**: `POST /api/appmagic/apps/{app_id}/metrics`
- **Headers**: `X-Incoming-Secret: <token>`
- **Payload**: `{ "data": [...] }` (extracted from AppMagic response)
- **Response**: `{ "success": true, "app_id": 123, "rows_stored": 215 }`

## 🐛 Troubleshooting

### Script not running?
```bash
# Check crontab
crontab -l | grep appmagic-metrics

# Test manually
./scheduler/run-appmagic-metrics.sh
```

### Stuck/stale lock?
```bash
# Check status
./scheduler/status-appmagic-metrics.sh

# Manual cleanup
rm -f /tmp/appmagic_metrics.lock
```

### Cookies expired?
```bash
# Export fresh cookies from browser
# Follow: COOKIE_EXPORT_INSTRUCTIONS.txt
# Save to: appmagic_cookies_fresh.json
```

### Getting Cloudflare blocks?
```bash
# Try running with visible browser first
python3 appmagic_metrics.py --visible --limit 1

# If successful, then switch to headless
python3 appmagic_metrics.py --headless --limit 1
```

## 📈 Current Schedule Overview

```
✓ bigquery_advertisers_postgres.py → Daily at 2:00 AM
✓ send_incoming_creative.py → Every 4 minutes
✓ parser_of_advertiser.py → Every 1 minute (overlap-safe)
✓ appmagic_fetcher.py → Every 15 minutes (overlap-safe)
✓ appmagic_metrics.py → Every 10 minutes (overlap-safe)  ← NEW
```

## 🎛️ Command-Line Options

```bash
python3 appmagic_metrics.py \
  --limit 10                        # Number of apps to process (default: 10)
  --headless                        # Run in headless mode (default)
  --visible                         # Show browser window
  --cookies-file <path>             # Custom cookies file
  --token <token>                   # Override API token
  --secret <secret>                 # Override shared secret
```

## ✅ Done!

Your metrics fetcher is ready. It will:
1. Fetch next 10 apps from API every 10 minutes
2. Visit AppMagic and bypass Cloudflare
3. Fetch metrics for each app (downloads, revenue, rankings, etc.)
4. Update server with fetched metrics
5. Repeat every 10 minutes (when not busy)

## 📚 Related Files

- **Main script**: `appmagic_metrics.py`
- **Scheduler wrapper**: `scheduler/run-appmagic-metrics.sh`
- **Install script**: `scheduler/install-appmagic-metrics.sh`
- **Status checker**: `scheduler/status-appmagic-metrics.sh`
- **Cookies file**: `appmagic_cookies_fresh.json`

