#!/usr/bin/env python3
"""
Test script to measure bandwidth for a single batch.

This runs the optimized stress test scraper with settings for 1 batch:
- 1 worker thread
- 20 creatives (1 batch)
- Shows detailed output

Usage:
    python3 test_batch_with_mitmproxy.py
"""

import subprocess
import sys

def main():
    print("="*80)
    print("BATCH BANDWIDTH MEASUREMENT TEST")
    print("="*80)
    print()
    print("Running stress test with:")
    print("  • 1 worker thread")
    print("  • 20 creatives (1 batch)")
    print("  • Session reuse optimization enabled")
    print()
    print("="*80)
    print()
    
    # Run stress test with 1 thread and 20 URLs
    cmd = [
        "python3",
        "stress_test_scraper_optimized.py",
        "--max-concurrent", "1",
        "--max-urls", "20",
        "--batch-size", "20"
    ]
    
    try:
        result = subprocess.run(cmd, cwd="/Users/rostoni/Downloads/LocalTransperancy")
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error running test: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
