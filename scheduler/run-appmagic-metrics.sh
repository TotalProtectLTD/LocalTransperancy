#!/bin/bash
# Cron wrapper for appmagic_metrics.py
# Fetches AppMagic metrics for apps
# Runs every 10 minutes

# Set PATH explicitly for cron
export PATH="/opt/homebrew/opt/util-linux/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Project directory
PROJECT_DIR="/Users/rostoni/Projects/LocalTransperancy"

# Lock file to prevent concurrent execution
LOCKFILE="/tmp/appmagic_metrics.lock"
FLOCK="/opt/homebrew/opt/util-linux/bin/flock"

# Create lock file if it doesn't exist
touch "$LOCKFILE"

# Run with flock to prevent concurrent execution
(
    flock -n 200 || {
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Another instance is already running, skipping..."
        exit 0
    }
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting appmagic_metrics.py"
    cd "$PROJECT_DIR" || exit 1
    
    # Run the script with default settings (headless, limit 10, use browser profile)
    /usr/bin/python3 "$PROJECT_DIR/appmagic_metrics.py" --headless --limit 10 --use-browser-profile
    
    EXIT_CODE=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Finished with exit code: $EXIT_CODE"
    
    exit $EXIT_CODE
    
) 200>"$LOCKFILE"

