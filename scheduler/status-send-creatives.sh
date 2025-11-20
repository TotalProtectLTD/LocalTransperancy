#!/bin/bash
# Check status of launchd agent for send_incoming_creative.py

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_NAME="com.localtransparency.send-creatives.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"
LABEL="com.localtransparency.send-creatives"

echo "Checking status of send-creatives scheduler..."
echo

# Check if plist exists
if [ ! -f "$PLIST_DEST" ]; then
    echo "❌ Agent not installed (plist file not found)"
    echo "   Run: ./scheduler/install-send-creatives.sh"
    exit 1
fi

# Check if agent is loaded
if launchctl list | grep -q "$LABEL"; then
    echo "✅ Agent is loaded"
    
    # Show schedule
    echo "📅 Schedule: Every 30 seconds"
    echo "   Arguments: --limit 10"
    
    # Check last log modification time
    LOG_FILE="$SCRIPT_DIR/logs/send-creatives.log"
    ERROR_LOG="$SCRIPT_DIR/logs/send-creatives-error.log"
    if [ -f "$LOG_FILE" ]; then
        LAST_RUN=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$LOG_FILE" 2>/dev/null || stat -c "%y" "$LOG_FILE" 2>/dev/null | cut -d'.' -f1)
        if [ -n "$LAST_RUN" ]; then
            echo "🕐 Last run: $LAST_RUN"
            
            # Check error log first
            if [ -f "$ERROR_LOG" ] && [ -s "$ERROR_LOG" ]; then
                LAST_ERROR=$(tail -1 "$ERROR_LOG" 2>/dev/null)
                if [ -n "$LAST_ERROR" ]; then
                    echo "❌ Last run: FAILED"
                    echo "   Error: ${LAST_ERROR:0:80}..."
                    echo "   Check error log for details: $ERROR_LOG"
                fi
            # Check if last run was successful (look for success indicators in log)
            elif grep -q "Done. Success:" "$LOG_FILE" 2>/dev/null || grep -q "✓ No eligible rows to send" "$LOG_FILE" 2>/dev/null; then
                # Extract success/failure counts from last "Done" line
                LAST_DONE=$(grep "Done. Success:" "$LOG_FILE" 2>/dev/null | tail -1)
                if [ -n "$LAST_DONE" ]; then
                    echo "✅ Last run: $LAST_DONE"
                else
                    echo "✅ Last run: SUCCESS (no rows to send)"
                fi
            elif grep -q "❌" "$LOG_FILE" 2>/dev/null || grep -q "✗" "$LOG_FILE" 2>/dev/null; then
                echo "❌ Last run: FAILED (check logs for details)"
            else
                echo "⚠️  Last run: Status unknown (log file may be empty or incomplete)"
            fi
        fi
    else
        echo "ℹ️  No log file found (agent hasn't run yet)"
        echo "   First run will be 30 seconds after installation"
    fi
else
    echo "❌ Agent is not loaded"
    echo "   Run: ./scheduler/install-send-creatives.sh"
    exit 1
fi

echo
echo "View logs:"
echo "  ./scheduler/view-send-creatives.sh          # Detailed logs"
echo "  ./scheduler/view-master-send-creatives.sh    # Master summary"

