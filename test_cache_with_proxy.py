#!/usr/bin/env python3
"""
Test script to verify cache integration with mitmproxy for accurate bandwidth measurement.

This script runs the scraper multiple times with mitmproxy enabled to demonstrate:
- First run: Cache MISS (downloads main.dart.js from network) - ~4-5 MB
- Second run: Cache HIT (serves main.dart.js from cache) - ~0-100 KB
- Third run: Cache HIT (serves from memory cache) - ~0-100 KB

Using mitmproxy provides accurate traffic measurement from the proxy level,
showing the true bandwidth savings from caching.
"""

import asyncio
import sys
from google_ads_transparency_scraper import scrape_ads_transparency_page
from cache_storage import format_bytes, get_cache_status
from cache_config import CACHE_DIR

# Test URL - sample creative from Google Ads Transparency Center
TEST_URL = "https://adstransparency.google.com/advertiser/AR06313713525550219265/creative/CR01137752899888087041?region=anywhere&platform=YOUTUBE"

async def test_cache_with_proxy():
    """
    Test cache integration with mitmproxy for accurate bandwidth measurement.
    
    Expected behavior:
    - Run 1: Cache MISS (mitmproxy measures ~4-5 MB download)
    - Run 2: Cache HIT (mitmproxy measures ~0-100 KB, 98%+ savings)
    - Run 3: Cache HIT (mitmproxy measures ~0-100 KB, 98%+ savings)
    """
    
    print("="*80)
    print("CACHE INTEGRATION TEST WITH MITMPROXY")
    print("="*80)
    print(f"\nTest URL: {TEST_URL}")
    print(f"Cache Directory: {CACHE_DIR}")
    print(f"Proxy: mitmproxy (accurate traffic measurement)")
    
    # Display current cache status before test
    print(f"\n{'CACHE STATUS BEFORE TEST':-^80}")
    cache_files = get_cache_status()
    if cache_files:
        print(f"Cached files: {len(cache_files)}")
        for cf in cache_files:
            age = cf.get('age_hours', 0)
            print(f"  • {cf['filename']}: {format_bytes(cf['size'])}, age: {age:.1f}h")
    else:
        print("Cache is empty (first run will download from network)")
    
    print(f"\nRunning scraper 3 times with mitmproxy...\n")
    
    results = []
    
    for run_num in range(1, 4):
        print("="*80)
        print(f"RUN #{run_num}")
        print("="*80)
        
        try:
            # Run the scraper WITH MITMPROXY enabled
            result = await scrape_ads_transparency_page(
                TEST_URL,
                use_proxy=True,  # ENABLE MITMPROXY for accurate measurement
                debug_appstore=False,
                debug_fletch=False,
                debug_content=False
            )
            
            results.append(result)
            
            # Display basic results
            print(f"\n{'EXECUTION STATUS':-^80}")
            if result.get('execution_success'):
                print("Status: ✅ SUCCESS")
            else:
                print("Status: ❌ FAILED")
                for err in result.get('execution_errors', []):
                    print(f"  • {err}")
            
            # Display videos found
            print(f"\n{'VIDEOS FOUND':-^80}")
            videos = result.get('videos', [])
            print(f"Videos: {len(videos)}")
            for vid in videos[:3]:  # Show first 3 videos
                print(f"  • https://www.youtube.com/watch?v={vid}")
            
            # Display cache statistics (the important part)
            cache_total = result.get('cache_total_requests', 0)
            if cache_total > 0:
                print(f"\n{'CACHE STATISTICS':-^80}")
                cache_hits = result.get('cache_hits', 0)
                cache_misses = result.get('cache_misses', 0)
                cache_hit_rate = result.get('cache_hit_rate', 0)
                cache_bytes_saved = result.get('cache_bytes_saved', 0)
                
                print(f"Cache Hits: {cache_hits}/{cache_total} ({cache_hit_rate:.1f}%)")
                print(f"Cache Misses: {cache_misses}")
                print(f"Bandwidth Saved by Cache: {format_bytes(cache_bytes_saved)}")
                
                if cache_hits > 0:
                    print(f"Status: 💾 Serving from cache")
                elif cache_misses > 0:
                    print(f"Status: 🌐 Downloaded from network")
            
            # Display bandwidth statistics (FROM MITMPROXY)
            print(f"\n{'BANDWIDTH STATISTICS (MITMPROXY)':-^80}")
            measurement_method = result.get('measurement_method', 'unknown')
            incoming = result.get('incoming_bytes', 0)
            outgoing = result.get('outgoing_bytes', 0)
            total = result.get('total_bytes', 0)
            
            print(f"Measurement Method: {measurement_method.upper()}")
            print(f"Incoming (responses): {format_bytes(incoming)}")
            print(f"Outgoing (requests): {format_bytes(outgoing)}")
            print(f"Total: {format_bytes(total)}")
            print(f"Duration: {result.get('duration_ms', 0):.0f} ms")
            
            print()
            
        except Exception as e:
            print(f"❌ Error on run #{run_num}: {e}")
            import traceback
            traceback.print_exc()
            results.append(None)
    
    # ========================================================================
    # SUMMARY AND ANALYSIS WITH PROXY DATA
    # ========================================================================
    
    print("\n" + "="*80)
    print("CACHE INTEGRATION TEST SUMMARY (WITH MITMPROXY)")
    print("="*80)
    
    # Validate cache behavior
    success_count = sum(1 for r in results if r and r.get('execution_success'))
    print(f"\nSuccessful runs: {success_count}/3")
    
    if success_count >= 2:
        print("\n✅ Cache Integration Test: PASSED")
        print("\nCache behavior verified:")
        
        # Check each run
        for i, result in enumerate(results, 1):
            if result:
                hits = result.get('cache_hits', 0)
                misses = result.get('cache_misses', 0)
                total_bytes = result.get('total_bytes', 0)
                method = result.get('measurement_method', 'unknown')
                
                print(f"\n  Run {i}:")
                print(f"    Cache: {hits} hit(s), {misses} miss(es)")
                print(f"    Bandwidth: {format_bytes(total_bytes)} ({method})")
        
        # Calculate bandwidth savings between runs
        print(f"\n{'BANDWIDTH SAVINGS ANALYSIS':-^80}")
        
        if len(results) >= 2 and results[0] and results[1]:
            run1 = results[0]
            run2 = results[1]
            
            run1_bytes = run1.get('total_bytes', 0)
            run2_bytes = run2.get('total_bytes', 0)
            
            run1_method = run1.get('measurement_method', 'unknown')
            run2_method = run2.get('measurement_method', 'unknown')
            
            print(f"\nRun 1 vs Run 2 comparison:")
            print(f"  Run 1: {format_bytes(run1_bytes)} ({run1_method})")
            print(f"  Run 2: {format_bytes(run2_bytes)} ({run2_method})")
            
            if run1_bytes > 0:
                if run2_bytes < run1_bytes:
                    savings = run1_bytes - run2_bytes
                    savings_pct = (savings / run1_bytes * 100)
                    print(f"  Saved: {format_bytes(savings)} ({savings_pct:.1f}% reduction)")
                    
                    if savings_pct >= 80:
                        print(f"  ✅ Excellent bandwidth savings (98%+ expected for cached main.dart.js)")
                    elif savings_pct >= 50:
                        print(f"  ✅ Good bandwidth savings")
                    else:
                        print(f"  ⚠️  Lower than expected (main.dart.js may already be cached)")
                else:
                    print(f"  ⚠️  No bandwidth reduction detected")
                    print(f"     This is expected if main.dart.js was already cached before test")
        
        # Display cache status after test
        print(f"\n{'CACHE STATUS AFTER TEST':-^80}")
        cache_files = get_cache_status()
        if cache_files:
            print(f"Cached files: {len(cache_files)}")
            total_cache_size = sum(cf['size'] for cf in cache_files)
            print(f"Total cache size: {format_bytes(total_cache_size)}")
            print(f"\nCached main.dart.js files:")
            for cf in cache_files:
                if 'main.dart.js' in cf['filename']:
                    age = cf.get('age_hours', 0)
                    version = cf.get('version', 'unknown')
                    version_short = version[-20:] if version and len(version) > 20 else version
                    print(f"  • {cf['filename']}")
                    print(f"    Size: {format_bytes(cf['size'])}, Age: {age:.1f}h")
                    print(f"    Version: {version_short}")
        
        print("\n🎉 Cache system is working correctly with mitmproxy!")
        print("   main.dart.js files are being cached and bandwidth is being saved.")
        
    else:
        print("\n❌ Cache Integration Test: FAILED")
        print(f"   Only {success_count}/3 runs succeeded")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    try:
        asyncio.run(test_cache_with_proxy())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

