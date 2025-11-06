#!/bin/bash
# Parse detailed logs and update master.log with essential information for send_incoming_creative.py

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/logs/send-creatives.log"
MASTER_LOG="$SCRIPT_DIR/logs/master-send-creatives.log"
ERROR_LOG="$SCRIPT_DIR/logs/send-creatives-error.log"

# Create master log if it doesn't exist
touch "$MASTER_LOG"

if [ ! -f "$LOG_FILE" ]; then
    echo "⚠️  No log file found: $LOG_FILE"
    exit 0
fi

# Extract execution information from the log
# Look for the most recent execution

# Get the last execution timestamp (from log file modification time or first line of execution)
LAST_MODIFIED=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$LOG_FILE" 2>/dev/null || stat -c "%y" "$LOG_FILE" 2>/dev/null | cut -d'.' -f1)

# Check if this execution is already in master log
if grep -q "$LAST_MODIFIED" "$MASTER_LOG" 2>/dev/null; then
    echo "ℹ️  Latest execution already summarized"
    exit 0
fi

# Determine status
STATUS="FAIL"
SUCCESS_COUNT="0"
FAILED_COUNT="0"
PROCESSED="0"

# Check for "Done. Success: X, Failed: Y" line
if grep -q "Done. Success:" "$LOG_FILE"; then
    LAST_DONE=$(grep "Done. Success:" "$LOG_FILE" | tail -1)
    if [ -n "$LAST_DONE" ]; then
        STATUS="SUCCESS"
        # Extract counts: "Done. Success: 10, Failed: 2"
        SUCCESS_COUNT=$(echo "$LAST_DONE" | sed -E 's/.*Success: ([0-9]+).*/\1/')
        FAILED_COUNT=$(echo "$LAST_DONE" | sed -E 's/.*Failed: ([0-9]+).*/\1/')
        PROCESSED=$((SUCCESS_COUNT + FAILED_COUNT))
    fi
elif grep -q "✓ No eligible rows to send" "$LOG_FILE"; then
    STATUS="SUCCESS"
    PROCESSED="0"
    SUCCESS_COUNT="0"
    FAILED_COUNT="0"
fi

# Extract error message if failed
ERROR_MSG=""
if [ "$STATUS" = "FAIL" ] && [ -f "$ERROR_LOG" ]; then
    ERROR_MSG=$(tail -1 "$ERROR_LOG" 2>/dev/null | head -c 100)
    if [ -n "$ERROR_MSG" ]; then
        ERROR_MSG=" | Error: $ERROR_MSG"
    fi
fi

# Format summary line
if [ "$STATUS" = "SUCCESS" ]; then
    if [ "$PROCESSED" -gt 0 ]; then
        SUMMARY="$LAST_MODIFIED | $STATUS | Processed: $PROCESSED | Success: $SUCCESS_COUNT | Failed: $FAILED_COUNT"
    else
        SUMMARY="$LAST_MODIFIED | $STATUS | No eligible rows to send"
    fi
else
    SUMMARY="$LAST_MODIFIED | $STATUS$ERROR_MSG"
fi

# Append to master log
echo "$SUMMARY" >> "$MASTER_LOG"

echo "✅ Updated master log:"
echo "   $SUMMARY"

