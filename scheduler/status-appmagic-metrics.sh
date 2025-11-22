#!/bin/bash
# Check status of appmagic_metrics.py scheduler

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="$SCRIPT_DIR/logs"
LOCKFILE="/tmp/appmagic_metrics.lock"

echo "════════════════════════════════════════════════════════════════"
echo "AppMagic Metrics Scheduler Status"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Check if job is in crontab
echo "📋 Crontab Entry:"
if crontab -l 2>/dev/null | grep -q "run-appmagic-metrics.sh"; then
    crontab -l | grep "run-appmagic-metrics.sh"
    echo "   ✅ Installed"
else
    echo "   ❌ NOT installed"
    echo ""
    echo "To install: ./scheduler/install-appmagic-metrics.sh"
    exit 1
fi
echo ""

# Check if currently running
echo "🏃 Currently Running:"
if [ -f "$LOCKFILE" ]; then
    if flock -n -E 200 "$LOCKFILE" true 2>/dev/null; then
        echo "   ❌ Not running (stale lock file)"
    else
        echo "   ✅ YES - script is running now"
    fi
else
    echo "   ❌ Not running"
fi
echo ""

# Show recent log entries
echo "📊 Recent Activity (last 20 lines):"
if [ -f "$LOGS_DIR/appmagic-metrics.log" ]; then
    tail -20 "$LOGS_DIR/appmagic-metrics.log"
else
    echo "   No log file yet: $LOGS_DIR/appmagic-metrics.log"
fi
echo ""

# Show recent errors
echo "⚠️  Recent Errors (last 10 lines):"
if [ -f "$LOGS_DIR/appmagic-metrics-error.log" ] && [ -s "$LOGS_DIR/appmagic-metrics-error.log" ]; then
    tail -10 "$LOGS_DIR/appmagic-metrics-error.log"
else
    echo "   No errors logged"
fi
echo ""

# Show next scheduled run
echo "⏰ Next Scheduled Run:"
# Get current time
NOW=$(date +%s)
# Get next 10-minute mark
NEXT_10MIN=$(( (NOW / 600 + 1) * 600 ))
NEXT_RUN=$(date -r $NEXT_10MIN '+%Y-%m-%d %H:%M:%S')
echo "   $NEXT_RUN (runs every 10 minutes)"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "Commands:"
echo "  View logs:    tail -f $LOGS_DIR/appmagic-metrics.log"
echo "  View errors:  tail -f $LOGS_DIR/appmagic-metrics-error.log"
echo "  Manual run:   $SCRIPT_DIR/run-appmagic-metrics.sh"
echo "════════════════════════════════════════════════════════════════"

