#!/bin/bash
# Cron wrapper for parser_of_advertiser.py with concurrent execution control
# Fetches next advertiser from API and processes it (no arguments needed)
# Allows up to 2 concurrent instances using PID tracking with flock protection

# Set PATH explicitly for cron
export PATH="/opt/homebrew/opt/util-linux/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Project directory
PROJECT_DIR="/Users/rostoni/Projects/LocalTransperancy"
LOCKFILE="/tmp/parser_of_advertiser.lock"
PID_DIR="/tmp/parser_of_advertiser_pids"
MAX_INSTANCES=2

# Full path to flock (util-linux is keg-only, not in default PATH)
FLOCK="/opt/homebrew/opt/util-linux/bin/flock"

# Create lock file and PID directory if they don't exist
touch "$LOCKFILE"
mkdir -p "$PID_DIR"

# Function to count active instances
# Counts actual parser_of_advertiser.py processes (most reliable)
# Also cleans up stale PID files
count_active_instances() {
    # Count actual running parser_of_advertiser.py processes
    # Use wc -l instead of grep -c to avoid exit code issues when count is 0
    local count=$(ps aux | grep "[p]arser_of_advertiser.py" | wc -l | tr -d ' ')
    
    # Clean up stale PID files (bash scripts that exited but left PID files)
    shopt -s nullglob
    for pidfile in "$PID_DIR"/*.pid; do
        [ -f "$pidfile" ] || continue
        local stored_pid=$(cat "$pidfile" 2>/dev/null)
        if [ -n "$stored_pid" ]; then
            # Check if the bash script (stored PID) is still running
            if ! ps -p "$stored_pid" > /dev/null 2>&1; then
                # Bash script exited - remove stale PID file
                rm -f "$pidfile"
            fi
        else
            # Empty PID file - remove it
            rm -f "$pidfile"
        fi
    done
    shopt -u nullglob
    
    echo $count
}

# Use flock to protect the check-and-register operation
# -n = non-blocking (fail immediately if lock can't be acquired)
# -e = exclusive lock
# 200 = file descriptor number
(
    "$FLOCK" -n 200 || {
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Could not acquire lock for instance check. Skipping."
        exit 0
    }
    
    # Count active instances (protected by flock)
    ACTIVE_COUNT=$(count_active_instances)
    
    if [ "$ACTIVE_COUNT" -ge "$MAX_INSTANCES" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Already $ACTIVE_COUNT instance(s) running (max: $MAX_INSTANCES). Skipping."
        exit 0
    fi
    
    # Register our PID (for tracking/cleanup purposes)
    PIDFILE="$PID_DIR/$$.pid"
    if ! echo $$ > "$PIDFILE" 2>/dev/null; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Failed to create PID file. Exiting."
        exit 1
    fi
    
    # We're registered - the lock will be released when subshell exits
    # but our PID file will remain until we clean it up
    
) 200>"$LOCKFILE"

# Check if we successfully registered (passed the check)
PIDFILE="$PID_DIR/$$.pid"
if [ ! -f "$PIDFILE" ]; then
    # We didn't pass the check (max instances reached or lock failed) - exit
    exit 0
fi

# Verify PID file was written correctly
if [ ! -s "$PIDFILE" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] PID file is empty. Exiting."
    rm -f "$PIDFILE"
    exit 1
fi

# Ensure cleanup on exit
cleanup() {
    rm -f "$PIDFILE"
}
trap cleanup EXIT INT TERM

# Run the script
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting parser_of_advertiser.py (PID $$) [Active instances: $(count_active_instances)/$MAX_INSTANCES]"
cd "$PROJECT_DIR" || exit 1

/usr/bin/python3 "$PROJECT_DIR/parser_of_advertiser.py"

EXIT_CODE=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Finished with exit code: $EXIT_CODE"
exit $EXIT_CODE

