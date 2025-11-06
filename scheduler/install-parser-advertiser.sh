#!/bin/bash
# Install parser_of_advertiser.py to cron with flock-based overlap prevention

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOGS_DIR="$SCRIPT_DIR/logs"

echo "Installing parser_of_advertiser.py to cron..."
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
echo "  - bigquery_advertisers_postgres.py: Daily at 11:00 PM"
echo "  - send_incoming_creative.py: Every 4 minutes"
echo "  - parser_of_advertiser.py: Every 2 minutes (overlap-safe)"
echo
echo "Logs: $LOGS_DIR/"
echo
echo "⚠️  IMPORTANT: Overlap Prevention"
echo "   parser_of_advertiser.py uses flock to prevent concurrent execution."
echo "   If a run takes 30 minutes, new attempts will skip with a message:"
echo "   'Another instance is already running. Skipping.'"
echo
echo "Manage crontab:"
echo "  View:   crontab -l"
echo "  Edit:   crontab -e"
echo "  Remove: crontab -r"
echo
echo "Next steps:"
echo "  - Wait 2 minutes for first parser_of_advertiser.py run"
echo "  - Check logs: tail -f $LOGS_DIR/parser-advertiser.log"
echo "  - View status: ./scheduler/status-cron.sh"

