#!/bin/bash
# View master summary log for send_incoming_creative.py

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MASTER_LOG="$SCRIPT_DIR/logs/master-send-creatives.log"
LINES=${1:-20}

if [ ! -f "$MASTER_LOG" ] || [ ! -s "$MASTER_LOG" ]; then
    echo "⚠️  Master log is empty or doesn't exist"
    echo "   Run: ./scheduler/summarize-send-creatives.sh to generate summary from detailed logs"
    exit 0
fi

echo "📊 Master Summary Log (last $LINES entries)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

# Show last N lines with color coding
tail -n "$LINES" "$MASTER_LOG" | while IFS= read -r line; do
    if echo "$line" | grep -q "SUCCESS"; then
        echo -e "\033[0;32m$line\033[0m"  # Green for success
    elif echo "$line" | grep -q "FAIL"; then
        echo -e "\033[0;31m$line\033[0m"  # Red for failures
    else
        echo "$line"
    fi
done

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Full master log: $MASTER_LOG"
echo
echo "To update master log from detailed logs:"
echo "  ./scheduler/summarize-send-creatives.sh"

