#!/bin/bash
# Cron wrapper for parser_of_advertiser.py with concurrent execution prevention
# Fetches next advertiser from API and processes it (no arguments needed)

# Set PATH explicitly for cron
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Project directory
PROJECT_DIR="/Users/rostoni/Projects/LocalTransperancy"
LOCKFILE="/tmp/parser_of_advertiser.lock"
PIDFILE="/tmp/parser_of_advertiser.pid"

# Function to check if process is running
is_running() {
    local pid=$1
    if [ -z "$pid" ]; then
        return 1
    fi
    # Check if process exists and is actually our script
    if ps -p "$pid" > /dev/null 2>&1; then
        # Verify it's our python script
        if ps -p "$pid" -o command= 2>/dev/null | grep -q "parser_of_advertiser.py"; then
            return 0
        fi
    fi
    return 1
}

# Cleanup function
cleanup() {
    rm -f "$LOCKFILE" "$PIDFILE"
}

# Try to acquire lock
if [ -f "$LOCKFILE" ] && [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE" 2>/dev/null)
    if is_running "$OLD_PID"; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Another instance (PID $OLD_PID) is already running. Skipping."
        exit 0
    else
        # Stale lock - clean it up
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Removing stale lock (PID $OLD_PID not running)"
        cleanup
    fi
fi

# Create lock with current PID
echo $$ > "$PIDFILE"
touch "$LOCKFILE"

# Ensure cleanup on exit
trap cleanup EXIT INT TERM

# Run the script
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting parser_of_advertiser.py (PID $$)"
cd "$PROJECT_DIR" || exit 1

/usr/bin/python3 "$PROJECT_DIR/parser_of_advertiser.py"

EXIT_CODE=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Finished with exit code: $EXIT_CODE"

exit $EXIT_CODE

