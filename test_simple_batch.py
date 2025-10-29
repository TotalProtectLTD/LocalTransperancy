#!/usr/bin/env python3
"""
Simple test for batch scraping with session reuse.

This test validates that:
1. Browser context can load an HTML page and extract cookies
2. Cookies can be reused for API-only requests
3. API-only requests successfully fetch data

Usage:
    python3 test_simple_batch.py
"""

import asyncio
import json
import sys

try:
    from google_ads_transparency_scraper_optimized import scrape_ads_transparency_api_only
    from google_ads_traffic import TrafficTracker
    from google_ads_browser import _setup_browser_context
    from playwright.async_api import async_playwright
except ImportError as e:
    print(f"ERROR: Could not import required functions: {e}")
    sys.exit(1)

# Test creative IDs
ADVERTISER_ID = "AR08722290881173913601"
CREATIVE_1 = "CR13612220978573606913"
CREATIVE_2 = "CR13612220978573606913"  # Same for now


async def test_simple_batch():
    """Test simple batch scraping with session reuse."""
    print("="*80)
    print("SIMPLE BATCH TEST - Session Reuse Validation")
    print("="*80)
    
    async with async_playwright() as p:
        # Setup browser context (shared for all creatives in batch)
        browser_setup = await _setup_browser_context(p, use_proxy=False, external_proxy=None)
        browser = browser_setup['browser']
        context = browser_setup['context']
        page = await context.new_page()
        
        # ========================================================================
        # STEP 1: Load first creative (simple HTML load)
        # ========================================================================
        print("\n" + "="*80)
        print("STEP 1: Loading first creative (HTML load)")
        print("="*80)
        
        first_url = f"https://adstransparency.google.com/advertiser/{ADVERTISER_ID}/creative/{CREATIVE_1}?region=anywhere"
        print(f"URL: {first_url}")
        print("Loading page...")
        
        try:
            await page.goto(first_url, wait_until="domcontentloaded", timeout=60000)
            print("✅ Page loaded successfully")
            
            # Wait for cookies to be set
            await asyncio.sleep(3)
            
            # Extract cookies
            cookies = await context.cookies()
            print(f"✅ Extracted {len(cookies)} cookie(s)")
            
            if cookies:
                for i, cookie in enumerate(cookies[:5], 1):
                    print(f"   {i}. {cookie['name']}: {cookie['value'][:30]}...")
            else:
                print("   ⚠️  No cookies found!")
            
        except Exception as e:
            print(f"❌ Failed to load first creative: {e}")
            await browser.close()
            return False
        
        # ========================================================================
        # STEP 2: Use API-only for second creative
        # ========================================================================
        print("\n" + "="*80)
        print("STEP 2: Loading second creative (API-only)")
        print("="*80)
        
        print(f"Advertiser: {ADVERTISER_ID}")
        print(f"Creative: {CREATIVE_2}")
        print("Making API request...")
        
        tracker = TrafficTracker()
        
        try:
            result = await scrape_ads_transparency_api_only(
                advertiser_id=ADVERTISER_ID,
                creative_id=CREATIVE_2,
                cookies=cookies,
                page=page,
                tracker=tracker,
                debug_appstore=False,
                debug_fletch=False,
                debug_content=False
            )
            
            print(f"\n✅ API-only request completed:")
            print(f"   Success: {result.get('success')}")
            print(f"   Videos: {result.get('videos')}")
            print(f"   Video count: {result.get('video_count')}")
            print(f"   App Store ID: {result.get('app_store_id')}")
            print(f"   Duration: {result.get('duration_ms'):.0f}ms")
            print(f"   API responses: {result.get('api_responses')}")
            print(f"   Content.js: {result.get('content_js_requests')}")
            
            if not result.get('success'):
                print(f"\n⚠️  Errors: {result.get('errors')}")
            
        except Exception as e:
            print(f"❌ API-only request failed: {e}")
            import traceback
            traceback.print_exc()
            await browser.close()
            return False
        
        await browser.close()
        
        # ========================================================================
        # Summary
        # ========================================================================
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        
        if len(cookies) > 0 and result.get('success'):
            print("\n✅ SUCCESS: Session reuse is working!")
            print(f"   - Cookies extracted: {len(cookies)}")
            print(f"   - API-only succeeded: Yes")
            print(f"   - Videos found: {result.get('video_count')}")
            print("\n📊 Ready for batch processing!")
            return True
        else:
            print("\n⚠️  PARTIAL SUCCESS:")
            print(f"   - Cookies extracted: {len(cookies)}")
            print(f"   - API-only succeeded: {result.get('success')}")
            if len(cookies) == 0:
                print("\n   ⚠️  No cookies were set. This might be expected for this site.")
                print("   The API-only method may still work without cookies if the session is maintained.")
            return result.get('success', False)


async def main():
    try:
        success = await test_simple_batch()
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


