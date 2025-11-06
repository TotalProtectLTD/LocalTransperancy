#!/bin/bash
# Cron wrapper for bigquery_creatives_postgres.py
# Calculates yesterday's date and passes it to the script

# Set PATH explicitly for cron
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Project directory
PROJECT_DIR="/Users/rostoni/Projects/LocalTransperancy"

# Calculate yesterday's date in YYYY-MM-DD format (macOS)
# macOS uses -v-1d for "1 day ago"
YESTERDAY=$(date -v-1d '+%Y-%m-%d')

# Run the script
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting bigquery_creatives_postgres.py with date=$YESTERDAY"
cd "$PROJECT_DIR" || exit 1

/usr/bin/python3 "$PROJECT_DIR/bigquery_creatives_postgres.py" --date "$YESTERDAY"

EXIT_CODE=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Finished with exit code: $EXIT_CODE"

exit $EXIT_CODE

