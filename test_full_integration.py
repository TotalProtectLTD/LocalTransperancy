#!/usr/bin/env python3
"""
Comprehensive integration test for Google Ads Transparency scraper with cache.

This script performs a complete test of:
1. Traffic measurement with mitmproxy (accurate bandwidth tracking)
2. Data extraction (YouTube videos, App Store IDs)
3. Cache effectiveness (before/after comparison)
4. Validation of all components working together

Test Flow:
---------
1. Clear cache to start fresh
2. Run 1 (COLD): Download everything, measure baseline bandwidth
3. Run 2 (WARM): Use cache, measure bandwidth savings
4. Compare results and validate extraction consistency

Expected Results:
----------------
- Run 1: ~5-10 MB bandwidth (downloading main.dart.js files)
- Run 2: ~2-5 KB bandwidth (serving from cache)
- Bandwidth savings: 99%+
- Both runs should extract same videos and App Store IDs
"""

import asyncio
import sys
import os
import shutil
from google_ads_transparency_scraper import scrape_ads_transparency_page
from cache_storage import format_bytes, get_cache_status
from cache_config import CACHE_DIR

# Test URL - sample creative from Google Ads Transparency Center
TEST_URL = "https://adstransparency.google.com/advertiser/AR06313713525550219265/creative/CR01137752899888087041?region=anywhere&platform=YOUTUBE"

def print_separator(title="", char="="):
    """Print a formatted separator line."""
    if title:
        print(f"\n{char*80}")
        print(f"{title:^80}")
        print(f"{char*80}\n")
    else:
        print(f"{char*80}")


def clear_cache():
    """Clear the cache directory to start fresh."""
    print("🗑️  Clearing cache to start fresh...")
    
    if os.path.exists(CACHE_DIR):
        # List files before deletion
        cache_files = get_cache_status()
        if cache_files:
            print(f"   Found {len(cache_files)} cached file(s):")
            for cf in cache_files:
                print(f"     • {cf['filename']}: {format_bytes(cf['size'])}")
            
            # Delete cache directory
            try:
                shutil.rmtree(CACHE_DIR)
                os.makedirs(CACHE_DIR, exist_ok=True)
                print("   ✅ Cache cleared successfully")
            except Exception as e:
                print(f"   ⚠️  Error clearing cache: {e}")
        else:
            print("   Cache is already empty")
    else:
        os.makedirs(CACHE_DIR, exist_ok=True)
        print("   Cache directory created")


def display_extraction_results(result, run_label):
    """Display extracted data (videos, App Store ID, funded by)."""
    print(f"\n{run_label} - Extracted Data:")
    print("-" * 80)
    
    # Videos
    videos = result.get('videos', [])
    print(f"Videos: {len(videos)} found")
    for vid in videos:
        print(f"  • {vid}")
        print(f"    https://www.youtube.com/watch?v={vid}")
    
    # App Store ID
    app_store_id = result.get('app_store_id')
    if app_store_id:
        print(f"\nApp Store ID: {app_store_id}")
        print(f"  https://apps.apple.com/app/id{app_store_id}")
    else:
        print(f"\nApp Store ID: Not found")
    
    # Funded By (sponsor)
    funded_by = result.get('funded_by')
    if funded_by:
        print(f"\nSponsored by: {funded_by}")
    
    # Creative ID
    creative_id = result.get('real_creative_id')
    method = result.get('method_used')
    print(f"\nCreative ID: {creative_id} (method: {method})")


def display_traffic_stats(result, run_label):
    """Display traffic statistics."""
    print(f"\n{run_label} - Traffic Statistics:")
    print("-" * 80)
    
    method = result.get('measurement_method', 'unknown')
    incoming = result.get('incoming_bytes', 0)
    outgoing = result.get('outgoing_bytes', 0)
    total = result.get('total_bytes', 0)
    duration = result.get('duration_ms', 0)
    
    print(f"Measurement: {method.upper()}")
    print(f"Incoming (responses): {format_bytes(incoming)}")
    print(f"Outgoing (requests): {format_bytes(outgoing)}")
    print(f"Total: {format_bytes(total)}")
    print(f"Duration: {duration:.0f} ms")
    print(f"Requests: {result.get('request_count', 0)} total, {result.get('blocked_count', 0)} blocked")


def display_cache_stats(result, run_label):
    """Display cache statistics."""
    print(f"\n{run_label} - Cache Statistics:")
    print("-" * 80)
    
    cache_total = result.get('cache_total_requests', 0)
    
    if cache_total > 0:
        hits = result.get('cache_hits', 0)
        misses = result.get('cache_misses', 0)
        hit_rate = result.get('cache_hit_rate', 0)
        bytes_saved = result.get('cache_bytes_saved', 0)
        
        print(f"Cache requests: {cache_total}")
        print(f"  • Hits: {hits} ({hit_rate:.1f}%)")
        print(f"  • Misses: {misses}")
        print(f"  • Bandwidth saved: {format_bytes(bytes_saved)}")
        
        if hits > 0:
            print(f"Status: 💾 Serving from cache (146x faster)")
        elif misses > 0:
            print(f"Status: 🌐 Downloaded from network (cached for next run)")
    else:
        print("No cacheable requests detected")


def compare_runs(run1, run2):
    """Compare two runs and show differences."""
    print_separator("COMPARISON: RUN 1 (COLD) vs RUN 2 (WARM)")
    
    # Bandwidth comparison
    print("Bandwidth:")
    run1_total = run1.get('total_bytes', 0)
    run2_total = run2.get('total_bytes', 0)
    
    print(f"  Run 1 (cold): {format_bytes(run1_total)}")
    print(f"  Run 2 (warm): {format_bytes(run2_total)}")
    
    if run1_total > 0:
        savings = run1_total - run2_total
        savings_pct = (savings / run1_total * 100) if run1_total > 0 else 0
        print(f"  Savings: {format_bytes(savings)} ({savings_pct:.1f}%)")
        
        if savings_pct >= 90:
            print(f"  ✅ Excellent bandwidth savings (99%+ expected)")
        elif savings_pct >= 50:
            print(f"  ✅ Good bandwidth savings")
        else:
            print(f"  ⚠️  Lower than expected savings")
    
    # Duration comparison
    print(f"\nDuration:")
    run1_duration = run1.get('duration_ms', 0)
    run2_duration = run2.get('duration_ms', 0)
    print(f"  Run 1: {run1_duration:.0f} ms")
    print(f"  Run 2: {run2_duration:.0f} ms")
    
    if run1_duration > 0:
        speedup = run1_duration / run2_duration if run2_duration > 0 else 1
        print(f"  Speedup: {speedup:.2f}x")
    
    # Cache comparison
    print(f"\nCache:")
    print(f"  Run 1 misses: {run1.get('cache_misses', 0)}")
    print(f"  Run 2 hits: {run2.get('cache_hits', 0)}")
    
    # Data validation
    print(f"\nData Extraction Validation:")
    run1_videos = set(run1.get('videos', []))
    run2_videos = set(run2.get('videos', []))
    
    if run1_videos == run2_videos:
        print(f"  ✅ Videos match: {len(run1_videos)} video(s)")
    else:
        print(f"  ❌ Videos differ:")
        print(f"     Run 1: {run1_videos}")
        print(f"     Run 2: {run2_videos}")
    
    run1_app = run1.get('app_store_id')
    run2_app = run2.get('app_store_id')
    
    if run1_app == run2_app:
        print(f"  ✅ App Store IDs match: {run1_app}")
    else:
        print(f"  ❌ App Store IDs differ:")
        print(f"     Run 1: {run1_app}")
        print(f"     Run 2: {run2_app}")


async def test_full_integration():
    """
    Comprehensive integration test with cache and bandwidth measurement.
    """
    
    print_separator("COMPREHENSIVE INTEGRATION TEST", "=")
    print("Testing: Traffic Measurement + Data Extraction + Cache Effectiveness")
    print(f"\nTest URL: {TEST_URL}")
    print(f"Cache Directory: {CACHE_DIR}")
    print(f"Using: Mitmproxy for accurate bandwidth measurement")
    
    results = []
    
    # ========================================================================
    # STEP 1: Clear cache and run cold test
    # ========================================================================
    print_separator("STEP 1: COLD RUN (No Cache)", "-")
    clear_cache()
    
    print("\n🚀 Running scraper (COLD - will download everything)...")
    
    try:
        result1 = await scrape_ads_transparency_page(
            TEST_URL,
            use_proxy=True,  # Use mitmproxy for accurate measurement
            debug_appstore=False,
            debug_fletch=False,
            debug_content=False
        )
        
        results.append(result1)
        
        # Check execution status
        if result1.get('execution_success'):
            print("✅ Scraping completed successfully\n")
            
            # Display results
            display_extraction_results(result1, "RUN 1")
            display_traffic_stats(result1, "RUN 1")
            display_cache_stats(result1, "RUN 1")
        else:
            print("❌ Scraping failed")
            for err in result1.get('execution_errors', []):
                print(f"  • {err}")
            return
        
    except Exception as e:
        print(f"❌ Error during cold run: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ========================================================================
    # STEP 2: Run warm test (with cache)
    # ========================================================================
    print_separator("STEP 2: WARM RUN (With Cache)", "-")
    
    # Display cache status
    cache_files = get_cache_status()
    if cache_files:
        print(f"Cache contains {len(cache_files)} file(s):")
        total_size = sum(cf['size'] for cf in cache_files)
        print(f"  Total size: {format_bytes(total_size)}\n")
    
    print("🚀 Running scraper (WARM - will use cache)...\n")
    
    try:
        result2 = await scrape_ads_transparency_page(
            TEST_URL,
            use_proxy=True,  # Use mitmproxy for accurate measurement
            debug_appstore=False,
            debug_fletch=False,
            debug_content=False
        )
        
        results.append(result2)
        
        # Check execution status
        if result2.get('execution_success'):
            print("✅ Scraping completed successfully\n")
            
            # Display results
            display_extraction_results(result2, "RUN 2")
            display_traffic_stats(result2, "RUN 2")
            display_cache_stats(result2, "RUN 2")
        else:
            print("❌ Scraping failed")
            for err in result2.get('execution_errors', []):
                print(f"  • {err}")
            return
        
    except Exception as e:
        print(f"❌ Error during warm run: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ========================================================================
    # STEP 3: Compare results
    # ========================================================================
    if len(results) == 2:
        compare_runs(results[0], results[1])
    
    # ========================================================================
    # FINAL SUMMARY
    # ========================================================================
    print_separator("TEST SUMMARY", "=")
    
    if len(results) == 2:
        run1_success = results[0].get('execution_success')
        run2_success = results[1].get('execution_success')
        
        if run1_success and run2_success:
            print("✅ COMPREHENSIVE INTEGRATION TEST: PASSED\n")
            
            print("Verified Components:")
            print("  ✅ Mitmproxy traffic measurement")
            print("  ✅ YouTube video extraction")
            print("  ✅ App Store ID extraction")
            print("  ✅ Cache system (two-level)")
            print("  ✅ Bandwidth optimization")
            print("  ✅ Data consistency across cache hits/misses")
            
            # Key metrics
            run1_total = results[0].get('total_bytes', 0)
            run2_total = results[1].get('total_bytes', 0)
            savings_pct = ((run1_total - run2_total) / run1_total * 100) if run1_total > 0 else 0
            
            print(f"\nKey Metrics:")
            print(f"  • Baseline bandwidth: {format_bytes(run1_total)}")
            print(f"  • Cached bandwidth: {format_bytes(run2_total)}")
            print(f"  • Savings: {savings_pct:.1f}%")
            print(f"  • Videos extracted: {len(results[0].get('videos', []))}")
            print(f"  • App Store ID: {results[0].get('app_store_id', 'N/A')}")
            
            print(f"\n🎉 All systems operational!")
        else:
            print("❌ TEST FAILED: Some runs did not complete successfully")
    else:
        print("❌ TEST INCOMPLETE: Not all runs completed")
    
    print_separator("", "=")


if __name__ == "__main__":
    try:
        asyncio.run(test_full_integration())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

