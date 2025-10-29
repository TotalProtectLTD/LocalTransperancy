#!/bin/bash
# Monitor cache files for non-versioned entries

CACHE_DIR="main.dart"

echo "=========================================="
echo "Cache File Monitor - Watching for non-versioned files"
echo "=========================================="
echo "Monitoring: $CACHE_DIR"
echo "Press Ctrl+C to stop"
echo ""

# Initial state
echo "Initial cache state:"
ls -lt "$CACHE_DIR" | grep "\.js$" | grep -v "_v_" | head -5

# Watch for new files
while true; do
    sleep 2
    
    # Find .js files without _v_ in the name (non-versioned)
    non_versioned=$(ls -t "$CACHE_DIR" 2>/dev/null | grep "\.js$" | grep -v "_v_" | head -1)
    
    if [ ! -z "$non_versioned" ]; then
        timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        echo ""
        echo "⚠️  [$timestamp] DETECTED NON-VERSIONED FILE: $non_versioned"
        
        # Check metadata
        if [ -f "$CACHE_DIR/$non_versioned.meta.json" ]; then
            echo "   Metadata:"
            cat "$CACHE_DIR/$non_versioned.meta.json" | grep -E "(url|version)" | head -2
        fi
        
        # Show process info
        echo "   Recent processes accessing cache:"
        lsof "$CACHE_DIR" 2>/dev/null | grep python3 | awk '{print $2, $1}' | sort -u | head -3
    fi
done


