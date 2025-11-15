#!/bin/bash
# Install bigquery_creatives_postgres.py to cron (daily at 11:30 PM with yesterday's date)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOGS_DIR="$SCRIPT_DIR/logs"

echo "Installing bigquery_creatives_postgres.py to cron..."
echo

# Create logs directory if it doesn't exist
mkdir -p "$LOGS_DIR"

# Backup existing crontab
crontab -l > "$SCRIPT_DIR/crontab-backup.txt" 2>/dev/null || echo "# No existing crontab" > "$SCRIPT_DIR/crontab-backup.txt"
echo "✅ Backed up existing crontab to: $SCRIPT_DIR/crontab-backup.txt"

# Create new crontab
cat > "$SCRIPT_DIR/crontab-new.txt" << EOF
# LocalTransperancy Scheduled Jobs - Projects Location
# Generated: $(date)

# Run bigquery_advertisers_postgres.py daily at 11:00 PM
0 23 * * * /usr/bin/python3 $PROJECT_DIR/bigquery_advertisers_postgres.py >> $LOGS_DIR/bigquery-advertisers.log 2>> $LOGS_DIR/bigquery-advertisers-error.log

# Run bigquery_creatives_postgres.py daily at 11:30 PM with yesterday's date
30 23 * * * $SCRIPT_DIR/run-bigquery-creatives.sh >> $LOGS_DIR/bigquery-creatives.log 2>> $LOGS_DIR/bigquery-creatives-error.log

# Run send_incoming_creative.py every 4 minutes
*/4 * * * * /Users/rostoni/bin/cron-send-creatives.sh >> $LOGS_DIR/send-creatives.log 2>> $LOGS_DIR/send-creatives-error.log

# Run parser_of_advertiser.py every 2 minutes (with flock to prevent overlap)
*/2 * * * * $SCRIPT_DIR/run-parser-advertiser.sh >> $LOGS_DIR/parser-advertiser.log 2>> $LOGS_DIR/parser-advertiser-error.log
EOF

# Install new crontab
crontab "$SCRIPT_DIR/crontab-new.txt"

echo "✅ Cron jobs installed successfully!"
echo
echo "Scheduled jobs:"
echo "  - bigquery_advertisers_postgres: Daily at 11:00 PM"
echo "  - bigquery_creatives_postgres:   Daily at 11:30 PM (with yesterday's date) 🆕"
echo "  - send_incoming_creative:         Every 4 minutes"
echo "  - parser_of_advertiser:           Every 2 minutes (overlap-safe)"
echo
echo "Logs: $LOGS_DIR/"
echo
echo "Date Parameter Info:"
echo "  bigquery_creatives will automatically run with yesterday's date"
echo "  Example: On Nov 6 at 11:30 PM, runs with --date 2025-11-05"
echo
echo "Manage crontab:"
echo "  View:   crontab -l"
echo "  Edit:   crontab -e"
echo "  Remove: crontab -r"
echo
echo "Next steps:"
echo "  - First run: Tonight at 11:30 PM"
echo "  - Monitor: tail -f $LOGS_DIR/bigquery-creatives.log"
echo "  - Status:  ./scheduler/status-cron.sh"



