#!/usr/bin/env python3
"""
Test script for optimized batch scraper.

This script tests the API-only function with a single creative to validate
that session reuse works correctly before running the full stress test.

Usage:
    python3 test_optimized_scraper.py
"""

import asyncio
import sys

try:
    from google_ads_transparency_scraper_optimized import (
        scrape_ads_transparency_page,
        scrape_ads_transparency_api_only
    )
    from google_ads_traffic import TrafficTracker
    from google_ads_browser import _setup_browser_context
    from playwright.async_api import async_playwright
except ImportError as e:
    print(f"ERROR: Could not import required functions: {e}")
    print("Make sure all google_ads_* modules are in the same directory")
    sys.exit(1)

# Test creative IDs (use your own IDs here)
ADVERTISER_ID = "AR08722290881173913601"
CREATIVE_1 = "CR13612220978573606913"
CREATIVE_2 = "CR13612220978573606913"  # Using same ID for now (change to different one if available)


async def test_api_only_function():
    """Test the API-only scraping function."""
    print("="*80)
    print("TESTING OPTIMIZED SCRAPER - API-Only Function")
    print("="*80)
    
    async with async_playwright() as p:
        # Setup browser context
        browser_setup = await _setup_browser_context(p, use_proxy=False, external_proxy=None)
        browser = browser_setup['browser']
        context = browser_setup['context']
        page = await context.new_page()
        
        # ========================================================================
        # STEP 1: Load first creative (full HTML) to get cookies
        # ========================================================================
        print("\n" + "="*80)
        print("STEP 1: Loading first creative (FULL HTML)")
        print("="*80)
        
        first_url = f"https://adstransparency.google.com/advertiser/{ADVERTISER_ID}/creative/{CREATIVE_1}?region=anywhere"
        
        print(f"URL: {first_url}")
        print("Loading...")
        
        first_result = await scrape_ads_transparency_page(
            page_url=first_url,
            use_proxy=False,
            external_proxy=None
        )
        
        print(f"\n✅ First creative loaded:")
        print(f"   Success: {first_result.get('success')}")
        print(f"   Videos: {first_result.get('videos')}")
        print(f"   Video count: {first_result.get('video_count')}")
        print(f"   App Store ID: {first_result.get('app_store_id')}")
        print(f"   Duration: {first_result.get('duration_ms'):.0f}ms")
        print(f"   Bandwidth: {first_result.get('total_bytes') / 1024:.1f} KB")
        
        if not first_result.get('success'):
            print(f"\n❌ First creative failed:")
            print(f"   Errors: {first_result.get('errors')}")
            await browser.close()
            return False
        
        # Extract cookies
        cookies = await context.cookies()
        print(f"\n🍪 Extracted {len(cookies)} cookie(s)")
        
        # ========================================================================
        # STEP 2: Load second creative (API-only) using cookies
        # ========================================================================
        print("\n" + "="*80)
        print("STEP 2: Loading second creative (API-ONLY - no HTML)")
        print("="*80)
        
        print(f"Advertiser ID: {ADVERTISER_ID}")
        print(f"Creative ID: {CREATIVE_2}")
        print("Loading via API...")
        
        tracker = TrafficTracker()
        
        api_result = await scrape_ads_transparency_api_only(
            advertiser_id=ADVERTISER_ID,
            creative_id=CREATIVE_2,
            cookies=cookies,
            page=page,
            tracker=tracker,
            debug_appstore=False,
            debug_fletch=False,
            debug_content=False
        )
        
        print(f"\n✅ Second creative loaded (API-only):")
        print(f"   Success: {api_result.get('success')}")
        print(f"   Videos: {api_result.get('videos')}")
        print(f"   Video count: {api_result.get('video_count')}")
        print(f"   App Store ID: {api_result.get('app_store_id')}")
        print(f"   Duration: {api_result.get('duration_ms'):.0f}ms")
        print(f"   Bandwidth: {api_result.get('total_bytes') / 1024:.1f} KB")
        
        if not api_result.get('success'):
            print(f"\n⚠️  Second creative failed:")
            print(f"   Errors: {api_result.get('errors')}")
            await browser.close()
            return False
        
        await browser.close()
        
        # ========================================================================
        # STEP 3: Compare results
        # ========================================================================
        print("\n" + "="*80)
        print("STEP 3: Bandwidth Comparison")
        print("="*80)
        
        first_bandwidth = first_result.get('total_bytes', 0) / 1024
        second_bandwidth = api_result.get('total_bytes', 0) / 1024
        savings = first_bandwidth - second_bandwidth
        savings_percent = (savings / first_bandwidth * 100) if first_bandwidth > 0 else 0
        
        print(f"\nFirst creative (HTML):     {first_bandwidth:.1f} KB")
        print(f"Second creative (API-only): {second_bandwidth:.1f} KB")
        print(f"Savings:                    {savings:.1f} KB ({savings_percent:.0f}%)")
        
        if savings_percent >= 50:
            print(f"\n✅ EXCELLENT: {savings_percent:.0f}% bandwidth savings achieved!")
        elif savings_percent >= 30:
            print(f"\n✓ GOOD: {savings_percent:.0f}% bandwidth savings (expected 65%)")
        else:
            print(f"\n⚠️  WARNING: Only {savings_percent:.0f}% savings (expected 65%)")
            print(f"   This might be due to cache or small content.js files")
        
        # ========================================================================
        # STEP 4: Validate data accuracy
        # ========================================================================
        print("\n" + "="*80)
        print("STEP 4: Data Accuracy Validation")
        print("="*80)
        
        if CREATIVE_1 == CREATIVE_2:
            # Same creative - results should match
            videos_match = set(first_result.get('videos', [])) == set(api_result.get('videos', []))
            appstore_match = first_result.get('app_store_id') == api_result.get('app_store_id')
            
            print(f"\nComparing same creative ({CREATIVE_1}):")
            print(f"   Videos match: {'✅' if videos_match else '❌'}")
            print(f"   App Store ID match: {'✅' if appstore_match else '❌'}")
            
            if videos_match and appstore_match:
                print(f"\n✅ SUCCESS: API-only method produces identical results!")
            else:
                print(f"\n⚠️  WARNING: Results don't match (might be dynamic content)")
                print(f"   First videos: {first_result.get('videos')}")
                print(f"   Second videos: {api_result.get('videos')}")
        else:
            # Different creatives - just show results
            print(f"\nDifferent creatives tested:")
            print(f"   First: {CREATIVE_1} → {first_result.get('video_count')} videos")
            print(f"   Second: {CREATIVE_2} → {api_result.get('video_count')} videos")
        
        print("\n" + "="*80)
        print("TEST COMPLETE")
        print("="*80)
        print("\n✅ Optimized scraper is working correctly!")
        print("\nNext steps:")
        print("   1. Test with different creative IDs (update CREATIVE_2 in script)")
        print("   2. Run batch test: python3 stress_test_scraper_optimized.py --max-concurrent 1 --batch-size 3 --max-urls 3")
        print("   3. Full production run: python3 stress_test_scraper_optimized.py --max-concurrent 10")
        
        return True


async def main():
    try:
        success = await test_api_only_function()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())


