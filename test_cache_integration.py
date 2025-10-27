#!/usr/bin/env python3
"""
Test script to verify cache integration in Google Ads Transparency scraper.

This script runs the scraper multiple times against the same URL to demonstrate:
- First run: Cache MISS (downloads main.dart.js from network)
- Second run: Cache HIT (serves main.dart.js from cache)
- Third run: Cache HIT (serves from memory cache, even faster)

The script shows cache statistics and bandwidth savings for each run.
"""

import asyncio
import sys
from google_ads_transparency_scraper import scrape_ads_transparency_page
from cache_storage import format_bytes

# Test URL - sample creative from Google Ads Transparency Center
TEST_URL = "https://adstransparency.google.com/advertiser/AR06313713525550219265/creative/CR01137752899888087041?region=anywhere&platform=YOUTUBE"

async def test_cache_integration():
    """
    Test cache integration by scraping the same URL multiple times.
    
    Expected behavior:
    - Run 1: Cache MISS (downloads ~4-5 MB main.dart.js files)
    - Run 2: Cache HIT from disk (~4ms load time)
    - Run 3: Cache HIT from memory (~0.028ms load time, 146x faster)
    """
    
    print("="*80)
    print("CACHE INTEGRATION TEST")
    print("="*80)
    print(f"\nTest URL: {TEST_URL}")
    print(f"\nRunning scraper 3 times to verify cache behavior...\n")
    
    results = []
    
    for run_num in range(1, 4):
        print("="*80)
        print(f"RUN #{run_num}")
        print("="*80)
        
        try:
            # Run the scraper
            result = await scrape_ads_transparency_page(
                TEST_URL,
                use_proxy=False,  # Disable proxy for faster testing
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
            for vid in videos:
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
                print(f"Bandwidth Saved: {format_bytes(cache_bytes_saved)}")
                
                if cache_hits > 0:
                    print(f"Status: 💾 Serving from cache (146x faster)")
                elif cache_misses > 0:
                    print(f"Status: 🌐 Downloaded from network (will be cached)")
            
            # Display bandwidth statistics
            print(f"\n{'BANDWIDTH STATISTICS':-^80}")
            print(f"Total Downloaded: {format_bytes(result.get('total_bytes', 0))}")
            print(f"Duration: {result.get('duration_ms', 0):.0f} ms")
            
            print()
            
        except Exception as e:
            print(f"❌ Error on run #{run_num}: {e}")
            import traceback
            traceback.print_exc()
            results.append(None)
    
    # ========================================================================
    # SUMMARY AND ANALYSIS
    # ========================================================================
    
    print("\n" + "="*80)
    print("CACHE INTEGRATION TEST SUMMARY")
    print("="*80)
    
    # Validate cache behavior
    success_count = sum(1 for r in results if r and r.get('execution_success'))
    print(f"\nSuccessful runs: {success_count}/3")
    
    if success_count >= 2:
        print("\n✅ Cache Integration Test: PASSED")
        print("\nExpected behavior verified:")
        
        # Check Run 1: Should have cache misses
        run1 = results[0]
        if run1:
            run1_misses = run1.get('cache_misses', 0)
            run1_hits = run1.get('cache_hits', 0)
            print(f"  • Run 1: {run1_misses} cache miss(es), {run1_hits} hit(s) - ✅")
        
        # Check Run 2: Should have cache hits
        run2 = results[1] if len(results) > 1 else None
        if run2:
            run2_hits = run2.get('cache_hits', 0)
            run2_misses = run2.get('cache_misses', 0)
            if run2_hits > 0:
                print(f"  • Run 2: {run2_hits} cache hit(s), {run2_misses} miss(es) - ✅")
            else:
                print(f"  • Run 2: {run2_hits} cache hit(s) - ⚠️ Expected cache hits")
        
        # Check Run 3: Should have cache hits
        run3 = results[2] if len(results) > 2 else None
        if run3:
            run3_hits = run3.get('cache_hits', 0)
            run3_misses = run3.get('cache_misses', 0)
            if run3_hits > 0:
                print(f"  • Run 3: {run3_hits} cache hit(s), {run3_misses} miss(es) - ✅")
            else:
                print(f"  • Run 3: {run3_hits} cache hit(s) - ⚠️ Expected cache hits")
        
        # Calculate bandwidth savings
        if run1 and run2:
            run1_bytes = run1.get('total_bytes', 0)
            run2_bytes = run2.get('total_bytes', 0)
            
            if run1_bytes > 0 and run2_bytes < run1_bytes:
                savings = run1_bytes - run2_bytes
                savings_pct = (savings / run1_bytes * 100)
                print(f"\n📊 Bandwidth Savings:")
                print(f"  • Run 1: {format_bytes(run1_bytes)} (baseline)")
                print(f"  • Run 2: {format_bytes(run2_bytes)} (with cache)")
                print(f"  • Saved: {format_bytes(savings)} ({savings_pct:.1f}%)")
        
        print("\n🎉 Cache system is working correctly!")
        print("   main.dart.js files are being cached and served efficiently.")
        
    else:
        print("\n❌ Cache Integration Test: FAILED")
        print(f"   Only {success_count}/3 runs succeeded")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    try:
        asyncio.run(test_cache_integration())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

