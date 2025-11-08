#!/bin/bash
# Cron wrapper for parser_of_advertiser.py with concurrent execution prevention
# Fetches next advertiser from API and processes it (no arguments needed)
# Uses flock for atomic locking to prevent race conditions

# Set PATH explicitly for cron
export PATH="/opt/homebrew/opt/util-linux/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Project directory
PROJECT_DIR="/Users/rostoni/Projects/LocalTransperancy"
LOCKFILE="/tmp/parser_of_advertiser.lock"

# Full path to flock (util-linux is keg-only, not in default PATH)
FLOCK="/opt/homebrew/opt/util-linux/bin/flock"

# Create lock file if it doesn't exist
touch "$LOCKFILE"

# Use flock for atomic locking
# -n = non-blocking (fail immediately if lock can't be acquired)
# -e = exclusive lock
# 200 = file descriptor number
(
    "$FLOCK" -n 200 || {
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Another instance is already running. Skipping."
        exit 0
    }
    
    # Run the script
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting parser_of_advertiser.py (PID $$)"
    cd "$PROJECT_DIR" || exit 1
    
    /usr/bin/python3 "$PROJECT_DIR/parser_of_advertiser.py"
    
    EXIT_CODE=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Finished with exit code: $EXIT_CODE"
    
    exit $EXIT_CODE
    
) 200>"$LOCKFILE"

