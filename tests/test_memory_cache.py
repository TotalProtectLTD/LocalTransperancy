#!/usr/bin/env python3
"""
Test script to demonstrate memory cache performance.
Simulates multiple requests to the same file.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Import from fighting_cache_problem
from fighting_cache_problem import (
    load_from_cache,
    MEMORY_CACHE,
    format_bytes
)
import time

def test_memory_cache():
    """Test memory cache with multiple requests."""
    
    # Simulate URL (use actual cached file)
    test_url = "https://www.gstatic.com/acx/transparency/report/acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000/main.dart.js"
    
    print("="*80)
    print("Memory Cache Performance Test")
    print("="*80)
    print(f"\nTest URL: {test_url}")
    print(f"Simulating 20 sequential requests...\n")
    
    times = []
    
    for i in range(20):
        start = time.time()
        content, metadata = load_from_cache(test_url)
        elapsed = (time.time() - start) * 1000  # Convert to ms
        times.append(elapsed)
        
        if content:
            cache_type = "MEMORY" if i > 0 else "DISK"
            print(f"Request {i+1:2d}: {elapsed:7.3f}ms - {cache_type} HIT ({format_bytes(len(content))})")
        else:
            print(f"Request {i+1:2d}: {elapsed:7.3f}ms - MISS")
    
    print("\n" + "="*80)
    print("Results:")
    print("="*80)
    print(f"First request (disk):  {times[0]:.3f}ms")
    print(f"Subsequent (memory):   {sum(times[1:])/len(times[1:]):.3f}ms average")
    print(f"Speedup:               {times[0]/sum(times[1:])*len(times[1:]):.1f}x")
    print(f"\nMemory cache size:     {format_bytes(sum(cf.size for cf in MEMORY_CACHE.values()))}")
    print(f"Files in memory:       {len(MEMORY_CACHE)}")
    print("="*80)

if __name__ == "__main__":
    test_memory_cache()

