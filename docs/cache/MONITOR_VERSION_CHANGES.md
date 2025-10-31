# Monitoring Version Changes - Quick Reference

## Quick Commands

### 1. Check Current Cached Versions

```bash
cat main.dart/cache_versions.json | python3 -m json.tool
```

**Output:**
```json
{
  "main.dart.js": {
    "version": "acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000",
    "url": "https://www.gstatic.com/...",
    "updated_at": 1761575380.4018219
  }
}
```

### 2. Watch for Version Changes (Real-time)

**macOS:**
```bash
fswatch -o main.dart/cache_versions.json | xargs -n1 -I{} sh -c 'date && cat main.dart/cache_versions.json'
```

**Linux:**
```bash
inotifywait -m -e modify main.dart/cache_versions.json | while read; do
  date
  cat main.dart/cache_versions.json
done
```

### 3. Check Logs for Version Changes

```bash
# View all version-related events
grep -E "VERSION|CACHE" /tmp/fighting_cache_output.log

# Only version mismatches
grep "VERSION MISMATCH" /tmp/fighting_cache_output.log

# Only cache invalidations
grep "CACHE INVALIDATE" /tmp/fighting_cache_output.log
```

### 4. Extract Current Version from Live URL

```bash
curl -sI "https://www.gstatic.com/acx/transparency/report/" | grep -i location
```

Or check the page source:
```bash
curl -s "https://adstransparency.google.com/advertiser/AR08722290881173913601/creative/CR13612220978573606913" | grep -o "acx-tfaar-tfaa-report-ui-frontend_auto_[0-9]\{8\}-[0-9]\{4\}_RC[0-9]\{3\}" | head -1
```

### 5. Compare Cached vs Live Version

```bash
# Get cached version
CACHED_VERSION=$(cat main.dart/cache_versions.json | python3 -c "import sys, json; print(json.load(sys.stdin)['main.dart.js']['version'])")

# Get live version (from running script logs)
LIVE_VERSION=$(grep "VERSION TRACKING" /tmp/fighting_cache_output.log | tail -1 | grep -o "acx-tfaar-tfaa-report-ui-frontend_auto_[0-9]\{8\}-[0-9]\{4\}_RC[0-9]\{3\}")

echo "Cached: $CACHED_VERSION"
echo "Live:   $LIVE_VERSION"

if [ "$CACHED_VERSION" = "$LIVE_VERSION" ]; then
  echo "✅ Versions match"
else
  echo "⚠️  Version mismatch detected!"
fi
```

## Automated Monitoring Script

Create `monitor_versions.sh`:

```bash
#!/bin/bash

CACHE_FILE="main.dart/cache_versions.json"
LOG_FILE="version_changes.log"

# Function to get current version
get_version() {
  if [ -f "$CACHE_FILE" ]; then
    python3 -c "import sys, json; print(json.load(open('$CACHE_FILE'))['main.dart.js']['version'])" 2>/dev/null || echo "unknown"
  else
    echo "no_cache"
  fi
}

# Function to log version change
log_change() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Version changed: $1 -> $2" | tee -a "$LOG_FILE"
  
  # Optional: Send notification
  # osascript -e "display notification \"Version changed to $2\" with title \"Cache Monitor\""
  # curl -X POST https://hooks.slack.com/... -d "{\"text\":\"Version changed to $2\"}"
}

# Initial version
PREV_VERSION=$(get_version)
echo "Starting monitor. Current version: $PREV_VERSION"

# Monitor loop
while true; do
  sleep 60  # Check every minute
  
  CURRENT_VERSION=$(get_version)
  
  if [ "$CURRENT_VERSION" != "$PREV_VERSION" ] && [ "$CURRENT_VERSION" != "unknown" ]; then
    log_change "$PREV_VERSION" "$CURRENT_VERSION"
    PREV_VERSION=$CURRENT_VERSION
  fi
done
```

**Usage:**
```bash
chmod +x monitor_versions.sh
./monitor_versions.sh &
```

## Notification Options

### 1. macOS Notification

```bash
osascript -e 'display notification "New version detected!" with title "Cache Monitor" sound name "Glass"'
```

### 2. Slack Webhook

```bash
VERSION="acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000"
curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL \
  -H 'Content-Type: application/json' \
  -d "{\"text\":\"🔄 Google Ads Transparency version changed to: $VERSION\"}"
```

### 3. Email Alert

```bash
VERSION="acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000"
echo "New version detected: $VERSION" | mail -s "Cache Version Change" your@email.com
```

### 4. Discord Webhook

```bash
VERSION="acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000"
curl -X POST https://discord.com/api/webhooks/YOUR/WEBHOOK \
  -H 'Content-Type: application/json' \
  -d "{\"content\":\"🔄 Version changed to: $VERSION\"}"
```

## Cron Job Setup

### Check Every Hour

```bash
# Edit crontab
crontab -e

# Add this line (runs at minute 0 of every hour)
0 * * * * cd /Users/rostoni/Downloads/LocalTransperancy && python3 fighting_cache_problem.py >> /tmp/cache_monitor.log 2>&1
```

### Check Every 6 Hours

```bash
# Runs at 00:00, 06:00, 12:00, 18:00
0 */6 * * * cd /Users/rostoni/Downloads/LocalTransperancy && python3 fighting_cache_problem.py >> /tmp/cache_monitor.log 2>&1
```

### Check Daily at 3 AM

```bash
# Runs once per day at 3:00 AM
0 3 * * * cd /Users/rostoni/Downloads/LocalTransperancy && python3 fighting_cache_problem.py >> /tmp/cache_monitor.log 2>&1
```

## Log Analysis

### Extract Version History

```bash
grep "VERSION TRACKING" /tmp/fighting_cache_output.log | \
  awk -F' -> ' '{print $2}' | \
  sort -u
```

### Count Version Changes

```bash
grep "VERSION MISMATCH" /tmp/fighting_cache_output.log | wc -l
```

### Last Version Change Time

```bash
grep "VERSION MISMATCH" /tmp/fighting_cache_output.log | tail -1 | awk '{print $1, $2}'
```

### Version Change Frequency

```bash
# Get all version change timestamps
grep "VERSION MISMATCH" /tmp/fighting_cache_output.log | \
  awk '{print $1}' | \
  sort | \
  uniq -c
```

## Dashboard Script

Create `version_dashboard.sh`:

```bash
#!/bin/bash

clear
echo "================================"
echo "   Cache Version Dashboard"
echo "================================"
echo ""

# Current versions
echo "📦 Current Cached Versions:"
if [ -f "main.dart/cache_versions.json" ]; then
  python3 << 'EOF'
import json
with open('main.dart/cache_versions.json') as f:
    data = json.load(f)
    for filename, info in data.items():
        version = info['version'][-25:]  # Last 25 chars
        print(f"  • {filename}: {version}")
EOF
else
  echo "  No cache found"
fi

echo ""

# Cache statistics
echo "📊 Cache Statistics:"
if [ -d "main.dart" ]; then
  FILE_COUNT=$(find main.dart -type f ! -name "*.meta.json" ! -name "cache_versions.json" | wc -l | tr -d ' ')
  TOTAL_SIZE=$(du -sh main.dart | awk '{print $1}')
  echo "  • Files cached: $FILE_COUNT"
  echo "  • Total size: $TOTAL_SIZE"
else
  echo "  No cache directory"
fi

echo ""

# Recent version changes
echo "🔄 Recent Version Changes:"
if [ -f "/tmp/fighting_cache_output.log" ]; then
  grep "VERSION MISMATCH" /tmp/fighting_cache_output.log | tail -3 | while read line; do
    echo "  • $line"
  done
  
  CHANGE_COUNT=$(grep -c "VERSION MISMATCH" /tmp/fighting_cache_output.log)
  echo ""
  echo "  Total changes detected: $CHANGE_COUNT"
else
  echo "  No log file found"
fi

echo ""
echo "================================"
echo "Last updated: $(date)"
echo "================================"
```

**Usage:**
```bash
chmod +x version_dashboard.sh
watch -n 60 ./version_dashboard.sh  # Update every minute
```

## Python Integration

Add to `fighting_cache_problem.py`:

```python
def send_version_change_notification(old_version, new_version):
    """Send notification when version changes."""
    import requests
    
    # Slack example
    webhook_url = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
    message = {
        "text": f"🔄 Google Ads Transparency version changed\n"
                f"Old: {old_version}\n"
                f"New: {new_version}"
    }
    
    try:
        requests.post(webhook_url, json=message)
        logger.info("Notification sent successfully")
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")

# In check_version_changed function:
if cached_version != current_version:
    logger.warning(f"[VERSION CHANGE] {filename}: {cached_version} -> {current_version}")
    
    # Send notification
    send_version_change_notification(cached_version, current_version)
    
    return True, current_version, cached_version
```

## Monitoring Best Practices

### 1. **Regular Checks**
- Run script at least once per day
- More frequent checks during business hours (when Google likely deploys)

### 2. **Log Retention**
- Keep version change logs for analysis
- Rotate logs to prevent disk space issues

### 3. **Alerting**
- Set up notifications for version changes
- Alert on repeated cache invalidations (possible issue)

### 4. **Backup**
- Keep `cache_versions.json` in version control
- Track version history over time

### 5. **Validation**
- Periodically verify cache integrity
- Check that cached files match their versions

## Troubleshooting

### Version Not Updating

**Check:**
1. Is `VERSION_AWARE_CACHING = True`?
2. Does version tracking file have write permissions?
3. Are logs showing version extraction?

**Debug:**
```bash
# Test version extraction
python3 << 'EOF'
import re
url = "https://www.gstatic.com/acx/transparency/report/acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000/main.dart.js"
pattern = r'(acx-tfaar-tfaa-report-ui-frontend_auto_\d{8}-\d{4}_RC\d+)'
match = re.search(pattern, url)
print(f"Extracted: {match.group(1) if match else 'None'}")
EOF
```

### False Version Changes

**Possible Causes:**
- URL format changed
- Regex pattern needs update
- Corrupted version tracking file

**Fix:**
```bash
# Backup and reset
cp main.dart/cache_versions.json main.dart/cache_versions.json.backup
rm main.dart/cache_versions.json
# Run script to rebuild
```

## Summary

- ✅ Use `cache_versions.json` to track current versions
- ✅ Monitor logs for `VERSION MISMATCH` events
- ✅ Set up automated checks (cron jobs)
- ✅ Configure notifications for version changes
- ✅ Keep version history for analysis
- ✅ Validate cache integrity regularly

For detailed implementation, see `VERSION_AWARE_CACHE_GUIDE.md`.

