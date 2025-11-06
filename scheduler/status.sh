#!/bin/bash
# Check status of launchd agent

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_NAME="com.localtransparency.bigquery-advertisers.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"
LABEL="com.localtransparency.bigquery-advertisers"

echo "Checking status of bigquery-advertisers scheduler..."
echo

# Check if plist exists
if [ ! -f "$PLIST_DEST" ]; then
    echo "❌ Agent not installed (plist file not found)"
    echo "   Run: ./scheduler/install.sh"
    exit 1
fi

# Check if agent is loaded
if launchctl list | grep -q "$LABEL"; then
    echo "✅ Agent is loaded"
    
    # Get next run time (launchd doesn't provide this directly, so we show schedule)
    echo "📅 Schedule: Daily at 2:00 AM"
    
    # Check last log modification time
    LOG_FILE="$SCRIPT_DIR/logs/bigquery-advertisers.log"
    if [ -f "$LOG_FILE" ]; then
        LAST_RUN=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$LOG_FILE" 2>/dev/null || stat -c "%y" "$LOG_FILE" 2>/dev/null | cut -d'.' -f1)
        if [ -n "$LAST_RUN" ]; then
            echo "🕐 Last run: $LAST_RUN"
            
            # Check if last run was successful (look for success indicators in log)
            if grep -q "✅ Import Complete" "$LOG_FILE" 2>/dev/null || grep -q "✓ Workflow Completed Successfully" "$LOG_FILE" 2>/dev/null; then
                echo "✅ Last run: SUCCESS"
            elif grep -q "❌ Error" "$LOG_FILE" 2>/dev/null || grep -q "✗" "$LOG_FILE" 2>/dev/null; then
                echo "❌ Last run: FAILED (check logs for details)"
            else
                echo "⚠️  Last run: Status unknown"
            fi
        fi
    else
        echo "ℹ️  No log file found (agent hasn't run yet)"
    fi
else
    echo "❌ Agent is not loaded"
    echo "   Run: ./scheduler/install.sh"
    exit 1
fi

echo
echo "View logs:"
echo "  ./scheduler/view.sh          # Detailed logs"
echo "  ./scheduler/view-master.sh  # Master summary"

