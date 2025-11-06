#!/bin/bash
# Clean up old log files

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="$SCRIPT_DIR/logs"
DAYS=${1:-30}

echo "Cleaning up log files older than $DAYS days..."
echo

if [ ! -d "$LOGS_DIR" ]; then
    echo "ℹ️  Logs directory doesn't exist: $LOGS_DIR"
    exit 0
fi

# Find and remove old log files
FOUND=0
while IFS= read -r -d '' file; do
    if [ -f "$file" ]; then
        echo "🗑️  Removing: $(basename "$file")"
        rm "$file"
        FOUND=1
    fi
done < <(find "$LOGS_DIR" -name "*.log" -type f -mtime +$DAYS -print0 2>/dev/null)

if [ $FOUND -eq 0 ]; then
    echo "✅ No old log files found (all files are newer than $DAYS days)"
else
    echo "✅ Cleanup complete"
fi

echo
echo "Note: launchd automatically rotates logs when they reach ~1MB"
echo "      This script removes old rotated/archived logs"

