#!/bin/bash
# View recent detailed logs for send_incoming_creative.py

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/logs/send-creatives.log"
ERROR_LOG="$SCRIPT_DIR/logs/send-creatives-error.log"
LINES=${1:-30}

echo "📊 Recent Activity (last $LINES lines)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

if [ ! -f "$LOG_FILE" ]; then
    echo "⚠️  No log file found: $LOG_FILE"
    echo "   The agent may not have run yet."
    exit 0
fi

# Show last N lines with color coding
tail -n "$LINES" "$LOG_FILE" | while IFS= read -r line; do
    if echo "$line" | grep -qE "(✓|SUCCESS|Done. Success)"; then
        echo -e "\033[0;32m$line\033[0m"  # Green for success
    elif echo "$line" | grep -qE "(❌|✗|FAIL|Error|sync_failed)"; then
        echo -e "\033[0;31m$line\033[0m"  # Red for errors
    else
        echo "$line"
    fi
done

# Show errors if they exist
if [ -f "$ERROR_LOG" ] && [ -s "$ERROR_LOG" ]; then
    ERROR_LINES=$(wc -l < "$ERROR_LOG" 2>/dev/null || echo "0")
    if [ "$ERROR_LINES" -gt 0 ]; then
        echo
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "❌ Errors (last 10 lines):"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        tail -n 10 "$ERROR_LOG" | sed 's/^/  /'
    fi
fi

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Full log: $LOG_FILE"
echo "Error log: $ERROR_LOG"

