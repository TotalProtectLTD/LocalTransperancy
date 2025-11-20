#!/bin/bash
# Install cron jobs for LocalTransperancy schedulers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOGS_DIR="$SCRIPT_DIR/logs"

echo "Installing cron jobs for LocalTransperancy..."
echo

# Create logs directory if it doesn't exist
mkdir -p "$LOGS_DIR"

# Backup existing crontab
crontab -l > "$SCRIPT_DIR/crontab-backup.txt" 2>/dev/null || echo "# No existing crontab" > "$SCRIPT_DIR/crontab-backup.txt"
echo "✅ Backed up existing crontab to: $SCRIPT_DIR/crontab-backup.txt"

# Create new crontab
cat > "$SCRIPT_DIR/crontab-new.txt" << EOF
# LocalTransperancy Scheduled Jobs
# Generated: $(date)

# Run bigquery_advertisers_postgres.py daily at 11:00 PM
0 23 * * * /usr/bin/python3 $PROJECT_DIR/bigquery_advertisers_postgres.py >> $LOGS_DIR/bigquery-advertisers.log 2>> $LOGS_DIR/bigquery-advertisers-error.log

# Run send_incoming_creative.py every 1 minute (batch 30)
* * * * * /Users/rostoni/bin/cron-send-creatives.sh >> $LOGS_DIR/send-creatives.log 2>> $LOGS_DIR/send-creatives-error.log
EOF

# Install new crontab
crontab "$SCRIPT_DIR/crontab-new.txt"

echo "✅ Cron jobs installed successfully!"
echo
echo "Scheduled jobs:"
echo "  - bigquery_advertisers_postgres.py: Daily at 11:00 PM"
echo "  - send_incoming_creative.py: Every 1 minute (batch 30)"
echo
echo "Logs: $LOGS_DIR/"
echo
echo "Manage crontab:"
echo "  View:   crontab -l"
echo "  Edit:   crontab -e"
echo "  Remove: crontab -r"
echo
echo "Next steps:"
echo "  - Wait 1 minute for first send_incoming_creative.py run"
echo "  - Check logs: tail -f $LOGS_DIR/send-creatives.log"
echo "  - View status: ./scheduler/status-cron.sh"


