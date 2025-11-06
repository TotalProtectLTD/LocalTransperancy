#!/bin/bash
# Check status of cron jobs

echo "Checking cron job status..."
echo

# Show crontab
echo "📅 Current crontab:"
crontab -l 2>/dev/null || echo "No crontab found"
echo

# Check log files
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="$SCRIPT_DIR/logs"

echo "📊 Recent activity:"
echo

# Check send-creatives log
if [ -f "$LOGS_DIR/send-creatives.log" ]; then
    LAST_RUN=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$LOGS_DIR/send-creatives.log" 2>/dev/null || stat -c "%y" "$LOGS_DIR/send-creatives.log" 2>/dev/null | cut -d'.' -f1)
    if [ -n "$LAST_RUN" ]; then
        echo "🕐 send-creatives last run: $LAST_RUN"
        
        # Check last line for success
        LAST_LINE=$(tail -1 "$LOGS_DIR/send-creatives.log" 2>/dev/null)
        if echo "$LAST_LINE" | grep -q "Done. Success:"; then
            echo "✅ Last run: SUCCESS"
            echo "   $LAST_LINE"
        elif echo "$LAST_LINE" | grep -q "✓ No eligible rows to send"; then
            echo "✅ Last run: SUCCESS (no rows to send)"
        elif echo "$LAST_LINE" | grep -q "Found [0-9]"; then
            echo "✅ Last run: SUCCESS"
            echo "   $LAST_LINE"
        else
            echo "⚠️  Last run: Status unclear"
        fi
    fi
else
    echo "ℹ️  send-creatives: No log file yet"
fi

# Check bigquery-advertisers log
if [ -f "$LOGS_DIR/bigquery-advertisers.log" ]; then
    LAST_RUN=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$LOGS_DIR/bigquery-advertisers.log" 2>/dev/null || stat -c "%y" "$LOGS_DIR/bigquery-advertisers.log" 2>/dev/null | cut -d'.' -f1)
    if [ -n "$LAST_RUN" ]; then
        echo "🕐 bigquery-advertisers last run: $LAST_RUN"
    fi
else
    echo "ℹ️  bigquery-advertisers: No log file yet (runs daily at 11 PM)"
fi

echo
echo "Next scheduled runs:"
echo "  - send-creatives: Every 2 minutes (limit 15)"
echo "  - bigquery-advertisers: Daily at 11:00 PM"
echo
echo "View logs:"
echo "  tail -f $LOGS_DIR/send-creatives.log"
echo "  tail -f $LOGS_DIR/bigquery-advertisers.log"
