#!/usr/bin/env python3
"""
Quick test to measure logging impact on performance.
"""

import time
import asyncio

async def test_with_logging():
    """Simulate processing with verbose logging"""
    start = time.time()
    for i in range(20):
        print(f"  [Worker 0] 📄 Batch ({i+1}/20): CR{i:016d}... (API-only)")
        print(f"    ⏱️  [0.00s] Starting API-only request...")
        print(f"  🍪 Adding 1 cookies to context:")
        print(f"     - NID: 526=...")
        print(f"  📤 Making API request to: https://adstransparency.google.com/...")
        print(f"     Headers: ['content-type', 'x-framework-xsrf-token', ...]")
        print(f"  📥 API response received:")
        print(f"     Status: 200")
        print(f"  📤 Fetching 3 content.js file(s) in parallel...")
        print(f"  ✅ Fetched 3 file(s) in 2.50s (parallel)")
        for j in range(3):
            print(f"  ✓ File {j+1}/3: 150000 bytes (video_id: True, appstore: False, encoding: gzip)")
        print(f"  📊 Total downloaded: 450,000 bytes (439.5 KB) from 3/3 files")
        print("="*80)
        print("IDENTIFYING REAL CREATIVE")
        print("="*80)
        print(f"✅ API Method: Real creative ID = 77{i:010d}")
        print(f"🔍 Extracted 3 fletch-render IDs from content.js URLs")
        print("="*80)
        print("EXTRACTING VIDEOS")
        print("="*80)
        print(f"✅ Total unique videos extracted: 1")
        print(f"   • VideoID{i}")
        print("="*80)
        print("VALIDATION")
        print("="*80)
        print(f"✅ All expected content.js received (3/3)")
        print(f"✅ EXECUTION SUCCESSFUL: Page scraped completely and correctly")
        print(f"    ⏱️  [3.50s] API-only complete (3.50s)")
        print(f"    ✅ CR{i:016d}... (1 videos)")
        await asyncio.sleep(0.001)  # Simulate minimal async work
    
    duration = time.time() - start
    return duration

async def test_without_logging():
    """Simulate processing with minimal logging"""
    start = time.time()
    for i in range(20):
        # Only essential logging
        await asyncio.sleep(0.001)  # Simulate minimal async work
    
    duration = time.time() - start
    return duration

async def main():
    print("="*80)
    print("LOGGING IMPACT TEST")
    print("="*80)
    print("\nTesting with 20 iterations (simulating 20 creatives)...\n")
    
    # Test with logging
    print("1️⃣  WITH VERBOSE LOGGING:")
    print("-"*80)
    time_with = await test_with_logging()
    print(f"\n⏱️  Time with logging: {time_with:.3f}s\n")
    
    # Test without logging
    print("\n2️⃣  WITHOUT VERBOSE LOGGING (minimal):")
    print("-"*80)
    time_without = await test_without_logging()
    print(f"\n⏱️  Time without logging: {time_without:.3f}s\n")
    
    # Calculate impact
    overhead = time_with - time_without
    overhead_pct = (overhead / time_with) * 100 if time_with > 0 else 0
    
    print("="*80)
    print("RESULTS")
    print("="*80)
    print(f"Time WITH logging:    {time_with:.3f}s")
    print(f"Time WITHOUT logging: {time_without:.3f}s")
    print(f"Logging overhead:     {overhead:.3f}s ({overhead_pct:.1f}% of total time)")
    print(f"\n💡 For 1000 creatives, this would add ~{(overhead/20)*1000:.1f}s ({((overhead/20)*1000)/60:.1f} min)")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())


