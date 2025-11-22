#!/bin/bash
# Start Chrome with remote debugging enabled

echo "Starting Chrome with remote debugging..."

# Close any existing Chrome instances
killall "Google Chrome" 2>/dev/null || true
sleep 2

# Start Chrome with remote debugging
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="/Users/rostoni/Library/Application Support/Google/Chrome" \
  > /dev/null 2>&1 &

# Wait for Chrome to start
sleep 3

# Check if it's working
if curl -s http://localhost:9222/json > /dev/null 2>&1; then
    echo "✅ Chrome started successfully with remote debugging on port 9222"
    echo ""
    echo "You can now run:"
    echo "  python3 appmagic_metrics.py --limit 10 --use-existing-chrome"
else
    echo "❌ Failed to start Chrome with remote debugging"
    echo "Check if Chrome is already running without debug mode"
fi

