#!/bin/bash
# Cron wrapper for appmagic_fetcher.py
# Fetches missing appstore_ids and updates AppMagic data
# Runs every 15 minutes

# Set PATH explicitly for cron
export PATH="/opt/homebrew/opt/util-linux/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Project directory
PROJECT_DIR="/Users/rostoni/Projects/LocalTransperancy"

# Lock file to prevent concurrent execution
LOCKFILE="/tmp/appmagic_fetcher.lock"
FLOCK="/opt/homebrew/opt/util-linux/bin/flock"

# Create lock file if it doesn't exist
touch "$LOCKFILE"

# Run with flock to prevent concurrent execution
(
    flock -n 200 || {
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Another instance is already running, skipping..."
        exit 0
    }
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting appmagic_fetcher.py"
    cd "$PROJECT_DIR" || exit 1
    
    # Run the script with default settings (headless, limit 1000, batch-size 50)
    /usr/bin/python3 "$PROJECT_DIR/appmagic_fetcher.py" --headless --limit 1000 --batch-size 50
    
    EXIT_CODE=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Finished with exit code: $EXIT_CODE"
    
    exit $EXIT_CODE
    
) 200>"$LOCKFILE"


