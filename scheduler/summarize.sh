#!/bin/bash
# Parse detailed logs and update master.log with essential information

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/logs/bigquery-advertisers.log"
MASTER_LOG="$SCRIPT_DIR/logs/master.log"
ERROR_LOG="$SCRIPT_DIR/logs/bigquery-advertisers-error.log"

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
if grep -q "✅ Import Complete" "$LOG_FILE" || grep -q "✓ Workflow Completed Successfully" "$LOG_FILE"; then
    STATUS="SUCCESS"
fi

# Extract rows inserted (new advertisers)
ROWS_INSERTED="N/A"
if grep -q "Rows inserted:" "$LOG_FILE"; then
    ROWS_INSERTED=$(grep "Rows inserted:" "$LOG_FILE" | tail -1 | sed -E 's/.*Rows inserted:[[:space:]]*([0-9,]+).*/\1/')
    if [ -n "$ROWS_INSERTED" ] && [ "$ROWS_INSERTED" != "Rows inserted:" ]; then
        # Remove commas and format with printf if available
        ROWS_CLEAN=$(echo "$ROWS_INSERTED" | tr -d ',')
        ROWS_INSERTED=$(printf "%'d" "$ROWS_CLEAN" 2>/dev/null || echo "$ROWS_CLEAN")
    else
        ROWS_INSERTED="N/A"
    fi
fi

# Extract duration
DURATION="N/A"
if grep -q "Duration:" "$LOG_FILE"; then
    DURATION=$(grep "Duration:" "$LOG_FILE" | tail -1 | sed -E 's/.*Duration:[[:space:]]*([0-9.]+)s.*/\1/' | cut -d' ' -f1)
    if [ -n "$DURATION" ] && [ "$DURATION" != "Duration:" ]; then
        DURATION="${DURATION}s"
    else
        DURATION="N/A"
    fi
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
    SUMMARY="$LAST_MODIFIED | $STATUS | New advertisers: $ROWS_INSERTED | Duration: $DURATION"
else
    SUMMARY="$LAST_MODIFIED | $STATUS$ERROR_MSG"
fi

# Append to master log
echo "$SUMMARY" >> "$MASTER_LOG"

echo "✅ Updated master log:"
echo "   $SUMMARY"

