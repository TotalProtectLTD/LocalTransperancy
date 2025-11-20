#!/bin/bash
# Abort currently running parser_of_advertiser.py process

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="/tmp/parser_of_advertiser_pids"
LOCKFILE="/tmp/parser_of_advertiser.lock"

echo "🔴 Aborting parser_of_advertiser.py..."
echo

# Find running processes
PIDS=$(ps aux | grep "[p]arser_of_advertiser.py" | awk '{print $2}')

if [ -z "$PIDS" ]; then
    echo "✅ No running process found"
    
    # Clean up stale files
    if [ -f "$LOCKFILE" ]; then
        echo "🧹 Cleaning up stale lock file: $LOCKFILE"
        rm -f "$LOCKFILE"
    fi
    
    if [ -d "$PID_DIR" ]; then
        echo "🧹 Cleaning up stale PID directory: $PID_DIR"
        rm -rf "$PID_DIR"
    fi
    
    exit 0
fi

# Kill each process found
KILLED=0
for PID in $PIDS; do
    if ps -p "$PID" > /dev/null 2>&1; then
        # Verify it's actually parser_of_advertiser.py
        if ps -p "$PID" -o command= 2>/dev/null | grep -q "parser_of_advertiser.py"; then
            echo "🛑 Killing process PID $PID"
            
            # Try graceful termination first (SIGTERM)
            kill -TERM "$PID" 2>/dev/null
            
            # Wait a bit for graceful shutdown
            sleep 2
            
            # Check if still running
            if ps -p "$PID" > /dev/null 2>&1; then
                echo "⚠️  Process still running, forcing kill (SIGKILL)"
                kill -KILL "$PID" 2>/dev/null
                sleep 1
            fi
            
            # Verify it's dead
            if ps -p "$PID" > /dev/null 2>&1; then
                echo "❌ Failed to kill PID $PID"
            else
                echo "✅ Process PID $PID terminated"
                KILLED=$((KILLED + 1))
            fi
        else
            echo "⚠️  PID $PID is not parser_of_advertiser.py, skipping"
        fi
    fi
done

# Clean up lock files and PID directory
if [ -f "$LOCKFILE" ]; then
    echo "🧹 Cleaning up lock file: $LOCKFILE"
    rm -f "$LOCKFILE"
fi

if [ -d "$PID_DIR" ]; then
    echo "🧹 Cleaning up PID directory: $PID_DIR"
    rm -rf "$PID_DIR"
fi

echo
if [ $KILLED -gt 0 ]; then
    echo "✅ Aborted $KILLED process(es)"
else
    echo "ℹ️  No processes were killed"
fi





