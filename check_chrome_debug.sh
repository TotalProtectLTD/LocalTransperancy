#!/bin/bash
# Check if Chrome remote debugging is available

echo "Checking Chrome remote debugging status..."
echo ""

if curl -s http://localhost:9222/json > /dev/null 2>&1; then
    echo "✅ Chrome remote debugging is ACTIVE on port 9222"
    echo ""
    echo "Available tabs:"
    curl -s http://localhost:9222/json | python3 -m json.tool | grep -E "(title|url)" | head -20
    echo ""
    echo "Ready to use with: --use-existing-chrome"
else
    echo "❌ Chrome remote debugging is NOT active"
    echo ""
    echo "To start it, run:"
    echo "  ./start_chrome_debug.sh"
    echo ""
    echo "Or manually:"
    echo "  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\"
    echo "    --remote-debugging-port=9222 \\"
    echo "    --user-data-dir=\"/Users/rostoni/Library/Application Support/Google/Chrome\" &"
fi

