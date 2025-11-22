# Chrome Remote Debugging Setup

## Why This Solves Cloudflare Issues

- Uses your **actual running Chrome** browser (not a new instance)
- No detection - it's your real browser with all your sessions
- All cookies, logins, and history already present
- No Cloudflare checks needed

## Setup (One-Time)

### Step 1: Close Chrome Completely

```bash
# Make sure Chrome is fully closed
killall "Google Chrome" 2>/dev/null || true
```

### Step 2: Start Chrome with Remote Debugging

```bash
# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="/Users/rostoni/Library/Application Support/Google/Chrome" \
  > /dev/null 2>&1 &

# Or use the helper script (recommended):
./start_chrome_debug.sh
```

### Step 3: Use Chrome Normally

- Chrome will open as normal
- You can browse, use AppMagic, etc.
- Script will connect to this running instance

## Using with appmagic_metrics.py

```bash
# Use the new flag (after Chrome is running with debugging)
python3 appmagic_metrics.py --limit 10 --use-existing-chrome
```

## How to Check if Remote Debugging is Active

```bash
# Should return JSON (Chrome is ready)
curl http://localhost:9222/json

# Or use the check script:
./check_chrome_debug.sh
```

## Stopping

Just close Chrome normally - the script will detect it's not available.

## Automation (Optional)

Add to your login items or use launchd to start Chrome with debugging automatically.

