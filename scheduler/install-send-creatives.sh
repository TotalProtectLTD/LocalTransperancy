#!/bin/bash
# Install launchd agent for send_incoming_creative.py

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_NAME="com.localtransparency.send-creatives.plist"
PLIST_SOURCE="$SCRIPT_DIR/$PLIST_NAME"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"
LOGS_DIR="$SCRIPT_DIR/logs"

echo "Installing launchd agent for send_incoming_creative.py..."
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
if launchctl list | grep -q "com.localtransparency.send-creatives"; then
    echo "🔄 Unloading existing agent..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# Load the agent
echo "🚀 Loading launchd agent..."
launchctl load "$PLIST_DEST"

# Verify it's loaded
if launchctl list | grep -q "com.localtransparency.send-creatives"; then
    echo
    echo "✅ Successfully installed and loaded!"
    echo
    echo "Agent details:"
    echo "  Label: com.localtransparency.send-creatives"
    echo "  Schedule: Every 10 minutes"
    echo "  Arguments: --limit 10"
    echo "  Logs: $LOGS_DIR/"
    echo
    echo "Next steps:"
    echo "  - Check status: ./scheduler/status-send-creatives.sh"
    echo "  - View logs: ./scheduler/view-send-creatives.sh"
    echo "  - View master log: ./scheduler/view-master-send-creatives.sh"
else
    echo "⚠️  Warning: Agent may not have loaded correctly"
    echo "   Check with: launchctl list | grep send-creatives"
    exit 1
fi

