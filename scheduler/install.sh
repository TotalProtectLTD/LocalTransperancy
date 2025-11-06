#!/bin/bash
# Install launchd agent for bigquery_advertisers_postgres.py

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_NAME="com.localtransparency.bigquery-advertisers.plist"
PLIST_SOURCE="$SCRIPT_DIR/$PLIST_NAME"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"
LOGS_DIR="$SCRIPT_DIR/logs"

echo "Installing launchd agent for bigquery_advertisers_postgres.py..."
echo

# Check if plist file exists
if [ ! -f "$PLIST_SOURCE" ]; then
    echo "❌ Error: Plist file not found: $PLIST_SOURCE"
    exit 1
fi

# Create logs directory if it doesn't exist
mkdir -p "$LOGS_DIR"

# Copy plist to LaunchAgents directory
echo "📋 Copying plist to ~/Library/LaunchAgents/..."
cp "$PLIST_SOURCE" "$PLIST_DEST"

# Unload existing agent if it's already loaded
if launchctl list | grep -q "com.localtransparency.bigquery-advertisers"; then
    echo "🔄 Unloading existing agent..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# Load the agent
echo "🚀 Loading launchd agent..."
launchctl load "$PLIST_DEST"

# Verify it's loaded
if launchctl list | grep -q "com.localtransparency.bigquery-advertisers"; then
    echo
    echo "✅ Successfully installed and loaded!"
    echo
    echo "Agent details:"
    echo "  Label: com.localtransparency.bigquery-advertisers"
    echo "  Schedule: Daily at 2:00 AM"
    echo "  Logs: $LOGS_DIR/"
    echo
    echo "Next steps:"
    echo "  - Check status: ./scheduler/status.sh"
    echo "  - View logs: ./scheduler/view.sh"
    echo "  - View master log: ./scheduler/view-master.sh"
else
    echo "⚠️  Warning: Agent may not have loaded correctly"
    echo "   Check with: launchctl list | grep bigquery-advertisers"
    exit 1
fi

