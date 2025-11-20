#!/bin/bash
# Check status of parser_of_advertiser.py scheduled job

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="$SCRIPT_DIR/logs"
PID_DIR="/tmp/parser_of_advertiser_pids"
MAX_INSTANCES=2

echo "Checking parser_of_advertiser.py status..."
echo

# Count active instances by counting actual parser_of_advertiser.py processes
ACTIVE_PIDS=($(ps aux | grep "[p]arser_of_advertiser.py" | awk '{print $2}'))
ACTIVE_COUNT=${#ACTIVE_PIDS[@]}

# Clean up stale PID files
if [ -d "$PID_DIR" ]; then
    shopt -s nullglob
    for pidfile in "$PID_DIR"/*.pid; do
        [ -f "$pidfile" ] || continue
        STORED_PID=$(cat "$pidfile" 2>/dev/null)
        if [ -n "$STORED_PID" ]; then
            # Check if the bash script (stored PID) is still running
            if ! ps -p "$STORED_PID" > /dev/null 2>&1; then
                # Bash script exited - remove stale PID file
                rm -f "$pidfile"
            fi
        else
            # Empty PID file - remove it
            rm -f "$pidfile"
        fi
    done
    shopt -u nullglob
fi

if [ $ACTIVE_COUNT -gt 0 ]; then
    echo "📊 Current status: 🔄 Running ($ACTIVE_COUNT/$MAX_INSTANCES instances)"
    for PID in "${ACTIVE_PIDS[@]}"; do
        # Show how long it's been running
        PID_START=$(ps -p "$PID" -o lstart= 2>/dev/null | awk '{print $2, $3, $4}')
        if [ -n "$PID_START" ]; then
            echo "   - PID $PID (started: $PID_START)"
        else
            echo "   - PID $PID"
        fi
    done
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

