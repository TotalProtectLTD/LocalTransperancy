#!/bin/bash
# Test script to demonstrate PID-based locking mechanism

echo "Testing PID-based locking mechanism for parser_of_advertiser.py..."
echo

LOCKFILE="/tmp/test_parser_of_advertiser.lock"
PIDFILE="/tmp/test_parser_of_advertiser.pid"

# Cleanup from any previous tests
rm -f "$LOCKFILE" "$PIDFILE"

# Function to simulate parser script
run_instance() {
    local instance_num=$1
    local duration=$2
    
    SCRIPT_LOCKFILE="$LOCKFILE"
    SCRIPT_PIDFILE="$PIDFILE"
    
    # Check if another instance is running
    if [ -f "$SCRIPT_LOCKFILE" ] && [ -f "$SCRIPT_PIDFILE" ]; then
        OLD_PID=$(cat "$SCRIPT_PIDFILE" 2>/dev/null)
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            echo "  [Instance $instance_num] Another instance (PID $OLD_PID) is running. Skipping. ✓"
            return 0
        fi
    fi
    
    # Create lock
    echo $$ > "$SCRIPT_PIDFILE"
    touch "$SCRIPT_LOCKFILE"
    
    echo "  [Instance $instance_num] Lock acquired! Running for ${duration}s (PID $$)..."
    sleep $duration
    echo "  [Instance $instance_num] Finished"
    
    # Cleanup
    rm -f "$SCRIPT_LOCKFILE" "$SCRIPT_PIDFILE"
}

# Start first instance in background
echo "Starting first instance (will sleep 5 seconds)..."
run_instance 1 5 &
FIRST_PID=$!

# Give it time to acquire lock
sleep 1

# Try to start second instance while first is running
echo "Trying to start second instance (should skip)..."
run_instance 2 1

# Wait for first instance to complete
wait $FIRST_PID

echo
echo "Trying third instance after first completed (should run)..."
run_instance 3 2

echo
echo "Test completed! This demonstrates:"
echo "  - First instance runs normally"
echo "  - Second instance skips when first is running"
echo "  - Lock is released when first instance finishes"
echo "  - Third instance runs after lock is released"
echo
echo "✅ Done"

