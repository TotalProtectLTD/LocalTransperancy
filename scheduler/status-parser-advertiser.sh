#!/bin/bash
# Check status of parser_of_advertiser.py scheduled job

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="$SCRIPT_DIR/logs"
LOCKFILE="/tmp/parser_of_advertiser.lock"

echo "Checking parser_of_advertiser.py status..."
echo

# Check if currently running
PIDFILE="/tmp/parser_of_advertiser.pid"

if [ -f "$LOCKFILE" ] && [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE" 2>/dev/null)
    if [ -n "$PID" ] && ps -p "$PID" > /dev/null 2>&1; then
        if ps -p "$PID" -o command= 2>/dev/null | grep -q "parser_of_advertiser.py"; then
            echo "📊 Current status: 🔄 Running (PID $PID)"
            # Show how long it's been running
            LOCK_AGE=$(( $(date +%s) - $(stat -f %m "$LOCKFILE" 2>/dev/null || stat -c %Y "$LOCKFILE" 2>/dev/null || echo 0) ))
            if [ $LOCK_AGE -gt 0 ]; then
                MINUTES=$(( LOCK_AGE / 60 ))
                SECONDS=$(( LOCK_AGE % 60 ))
                echo "   Running for: ${MINUTES}m ${SECONDS}s"
            fi
        else
            echo "📊 Current status: ✅ Idle (stale lock detected)"
        fi
    else
        echo "📊 Current status: ✅ Idle (stale lock detected)"
    fi
else
    echo "📊 Current status: ✅ Idle (not running)"
fi

echo

# Check crontab
if crontab -l 2>/dev/null | grep -q "run-parser-advertiser.sh"; then
    CRON_SCHEDULE=$(crontab -l | grep "run-parser-advertiser.sh" | awk '{print $1, $2, $3, $4, $5}')
    echo "📅 Cron schedule: $CRON_SCHEDULE (every 1 minute)"
else
    echo "⚠️  Not found in crontab"
    echo "   Install with: ./scheduler/install-parser-advertiser.sh"
fi

echo

# Check log files
if [ -f "$LOGS_DIR/parser-advertiser.log" ]; then
    LAST_RUN=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$LOGS_DIR/parser-advertiser.log" 2>/dev/null || stat -c "%y" "$LOGS_DIR/parser-advertiser.log" 2>/dev/null | cut -d'.' -f1)
    if [ -n "$LAST_RUN" ]; then
        echo "🕐 Last activity: $LAST_RUN"
        
        # Show last few lines
        echo
        echo "📋 Recent log entries (last 5 lines):"
        tail -5 "$LOGS_DIR/parser-advertiser.log" | sed 's/^/   /'
    fi
else
    echo "ℹ️  No log file yet (hasn't run)"
fi

echo
echo "View logs:"
echo "  tail -f $LOGS_DIR/parser-advertiser.log"
echo "  tail -f $LOGS_DIR/parser-advertiser-error.log"

