#!/bin/bash
# Install appmagic_fetcher.py to cron (every 15 minutes)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOGS_DIR="$SCRIPT_DIR/logs"

echo "Installing appmagic_fetcher.py to cron..."

# Create logs directory if it doesn't exist
mkdir -p "$LOGS_DIR"

# Backup existing crontab
crontab -l > "$SCRIPT_DIR/crontab-backup.txt" 2>/dev/null || echo "# No existing crontab" > "$SCRIPT_DIR/crontab-backup.txt"
echo "✅ Backed up existing crontab to: $SCRIPT_DIR/crontab-backup.txt"

# Read current crontab
CURRENT_CRON=$(crontab -l 2>/dev/null || echo "")

# Check if appmagic_fetcher is already in crontab
if echo "$CURRENT_CRON" | grep -q "run-appmagic-fetcher.sh"; then
    echo "⚠️  appmagic_fetcher.sh is already in crontab"
    echo "   Removing old entry and adding new one..."
    CURRENT_CRON=$(echo "$CURRENT_CRON" | grep -v "run-appmagic-fetcher.sh")
fi

# Create new crontab
cat > "$SCRIPT_DIR/crontab-new.txt" << EOF
# LocalTransperancy Scheduled Jobs - Projects Location
# Updated: $(date '+%a %b %d %H:%M:%S %z %Y')

$CURRENT_CRON

# Run appmagic_fetcher.py every 15 minutes (with flock to prevent overlap)
*/15 * * * * $PROJECT_DIR/scheduler/run-appmagic-fetcher.sh >> $LOGS_DIR/appmagic-fetcher.log 2>> $LOGS_DIR/appmagic-fetcher-error.log
EOF

# Install new crontab
crontab "$SCRIPT_DIR/crontab-new.txt"

echo "✅ Cron jobs installed successfully!"
echo ""
echo "Scheduled jobs:"
echo "  - appmagic_fetcher.py: Every 15 minutes (overlap-safe)"
echo ""
echo "Logs:"
echo "  - Output: $LOGS_DIR/appmagic-fetcher.log"
echo "  - Errors: $LOGS_DIR/appmagic-fetcher-error.log"
echo ""
echo "Manage crontab:"
echo "  View:   crontab -l"
echo "  Edit:   crontab -e"
echo "  Remove: crontab -r"
echo ""
echo "Next steps:"
echo "  - Wait 15 minutes for first appmagic_fetcher.py run"
echo "  - View status: ./scheduler/status-appmagic-fetcher.sh"
echo "  - View logs: tail -f $LOGS_DIR/appmagic-fetcher.log"

