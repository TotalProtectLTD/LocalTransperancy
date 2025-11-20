#!/bin/bash
# Test script to demonstrate overlap prevention with actual timing

LOCKFILE="/tmp/parser_of_advertiser.lock"
PIDFILE="/tmp/parser_of_advertiser.pid"

echo "==================================================================="
echo "Testing Overlap Prevention for parser_of_advertiser.py"
echo "==================================================================="
echo

# Clean up any previous locks
rm -f "$LOCKFILE" "$PIDFILE"

# Create a long-running fake process
echo "Step 1: Starting simulated long-running parser (30 seconds)..."
(
    # Simulate the wrapper script behavior
    echo $$ > "$PIDFILE"
    touch "$LOCKFILE"
    
    echo "  [Process 1] PID $$ - Running parser_of_advertiser.py (simulated 30s)"
    
    # Simulate long execution
    for i in {1..30}; do
        sleep 1
        if [ $((i % 5)) -eq 0 ]; then
            echo "  [Process 1] Still running... ${i}s elapsed"
        fi
    done
    
    echo "  [Process 1] Finished after 30s"
    rm -f "$LOCKFILE" "$PIDFILE"
) &

LONG_PROCESS_PID=$!

# Wait for lock to be created
sleep 2

echo
echo "Step 2: Attempting to start second instance (should skip)..."
./scheduler/run-parser-advertiser.sh

echo
echo "Step 3: Checking lock status..."
./scheduler/status-parser-advertiser.sh

echo
echo "Step 4: Waiting for first process to finish..."
wait $LONG_PROCESS_PID

echo
echo "Step 5: Attempting to start third instance (should run now)..."
./scheduler/run-parser-advertiser.sh | head -5

echo
echo "==================================================================="
echo "✅ Test Complete!"
echo "==================================================================="
echo
echo "Summary:"
echo "  - First instance: Ran for 30 seconds"
echo "  - Second instance: Should have skipped (overlap prevention)"
echo "  - Third instance: Should have run after first completed"





