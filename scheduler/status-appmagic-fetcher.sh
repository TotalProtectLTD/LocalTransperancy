#!/bin/bash
# Check status of appmagic_fetcher.py scheduled job

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="$SCRIPT_DIR/logs"

echo "Checking status of appmagic-fetcher scheduler..."
echo ""

# Check if script exists
if [ ! -f "$SCRIPT_DIR/run-appmagic-fetcher.sh" ]; then
    echo "❌ run-appmagic-fetcher.sh not found"
    echo "   Expected: $SCRIPT_DIR/run-appmagic-fetcher.sh"
    exit 1
fi

# Check if running
if pgrep -f "appmagic_fetcher.py" > /dev/null; then
    echo "✅ Process is running"
    echo "   PIDs: $(pgrep -f 'appmagic_fetcher.py' | tr '\n' ' ')"
else
    echo "ℹ️  Process is not currently running"
fi

echo ""

# Check crontab
if crontab -l 2>/dev/null | grep -q "run-appmagic-fetcher.sh"; then
    CRON_SCHEDULE=$(crontab -l | grep "run-appmagic-fetcher.sh" | awk '{print $1, $2, $3, $4, $5}')
    echo "✅ Found in crontab"
    echo "📅 Cron schedule: $CRON_SCHEDULE (every 15 minutes)"
else
    echo "⚠️  Not found in crontab"
    echo "   Install with: ./scheduler/install-appmagic-fetcher.sh"
fi

echo ""

# Check logs
if [ -f "$LOGS_DIR/appmagic-fetcher.log" ]; then
    LOG_SIZE=$(wc -l < "$LOGS_DIR/appmagic-fetcher.log" | tr -d ' ')
    LAST_RUN=$(tail -1 "$LOGS_DIR/appmagic-fetcher.log" 2>/dev/null | head -c 100)
    echo "📄 Log file: $LOGS_DIR/appmagic-fetcher.log"
    echo "   Lines: $LOG_SIZE"
    if [ -n "$LAST_RUN" ]; then
        echo "   Last entry: $LAST_RUN"
    fi
else
    echo "⚠️  Log file not found: $LOGS_DIR/appmagic-fetcher.log"
fi

if [ -f "$LOGS_DIR/appmagic-fetcher-error.log" ]; then
    ERROR_SIZE=$(wc -l < "$LOGS_DIR/appmagic-fetcher-error.log" | tr -d ' ')
    echo "📄 Error log: $LOGS_DIR/appmagic-fetcher-error.log"
    echo "   Lines: $ERROR_SIZE"
    if [ "$ERROR_SIZE" -gt 0 ]; then
        echo "   ⚠️  Errors found! Check the error log."
    fi
else
    echo "ℹ️  Error log not found (no errors yet)"
fi

echo ""
echo "Useful commands:"
echo "  ./scheduler/status-appmagic-fetcher.sh    # This status check"
echo "  tail -f $LOGS_DIR/appmagic-fetcher.log   # Watch live output"
echo "  tail -f $LOGS_DIR/appmagic-fetcher-error.log  # Watch errors"


