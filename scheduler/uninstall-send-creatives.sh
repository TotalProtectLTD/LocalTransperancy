#!/bin/bash
# Uninstall launchd agent for send_incoming_creative.py

set -e

PLIST_NAME="com.localtransparency.send-creatives.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "Uninstalling launchd agent for send_incoming_creative.py..."
echo

# Check if agent is loaded
if launchctl list | grep -q "com.localtransparency.send-creatives"; then
    echo "🔄 Unloading agent..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
    echo "✅ Agent unloaded"
else
    echo "ℹ️  Agent is not currently loaded"
fi

# Remove plist file
if [ -f "$PLIST_DEST" ]; then
    echo "🗑️  Removing plist file..."
    rm "$PLIST_DEST"
    echo "✅ Plist file removed"
else
    echo "ℹ️  Plist file not found (may have been already removed)"
fi

# Ask about log cleanup
echo
read -p "Do you want to remove log files? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    LOGS_DIR="$SCRIPT_DIR/logs"
    if [ -d "$LOGS_DIR" ]; then
        echo "🗑️  Removing log files..."
        rm -f "$LOGS_DIR"/send-creatives*.log
        rm -f "$LOGS_DIR"/master-send-creatives.log
        echo "✅ Log files removed"
    fi
fi

echo
echo "✅ Uninstallation complete!"



