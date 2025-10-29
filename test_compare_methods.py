#!/usr/bin/env python3
"""
Compare content.js captured by full HTML vs API-only methods.
"""
import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from google_ads_transparency_scraper_optimized import scrape_ads_transparency_page, scrape_ads_transparency_api_only
from google_ads_traffic import TrafficTracker
from google_ads_browser import _setup_browser_context
from playwright.async_api import async_playwright

# Use a known creative with videos
ADVERTISER_ID = "AR00503804302385479681"
CREATIVE_ID = "CR11718023440488202241"
EXPECTED_VIDEO = "rkXH2aDmhDQ"
EXPECTED_APPSTORE = "1435281792"

async def main():
    print("="*80)
    print("COMPARING FULL HTML vs API-ONLY METHODS")
    print("="*80)
    
    async with async_playwright() as p:
        # ========================================================================
        # METHOD 1: Full HTML (traditional)
        # ========================================================================
        print("\n" + "="*80)
        print("METHOD 1: Full HTML Load")
        print("="*80)
        
        url = f"https://adstransparency.google.com/advertiser/{ADVERTISER_ID}/creative/{CREATIVE_ID}?region=anywhere"
        
        result_html = await scrape_ads_transparency_page(
            url,
            use_proxy=False,
            debug_appstore=False,
            debug_fletch=False,
            debug_content=False
        )
        
        print(f"\n📊 Full HTML Results:")
        print(f"   Videos: {result_html['videos']}")
        print(f"   Video count: {result_html['video_count']}")
        print(f"   App Store ID: {result_html['app_store_id']}")
        print(f"   Content.js count: {result_html['content_js_requests']}")
        
        # Save first content.js from full HTML method
        html_content_js_file = "/Users/rostoni/Downloads/LocalTransperancy/debug_html_content.js"
        # We need to modify the scraper to save this, but for now let's continue
        
        # ========================================================================
        # METHOD 2: API-Only
        # ========================================================================
        print("\n" + "="*80)
        print("METHOD 2: API-Only (with session reuse)")
        print("="*80)
        
        # Set up browser context
        browser_setup = await _setup_browser_context(p, use_proxy=False, external_proxy=None)
        browser = browser_setup['browser']
        context = browser_setup['context']
        page = await context.new_page()
        
        # Load HTML page ONCE to get cookies
        print(f"Loading HTML page to get cookies...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)
        
        cookies = await context.cookies()
        print(f"✅ Got {len(cookies)} cookies")
        
        # Now use API-only method
        tracker = TrafficTracker()
        
        result_api = await scrape_ads_transparency_api_only(
            ADVERTISER_ID,
            CREATIVE_ID,
            cookies,
            page,
            tracker,
            debug_appstore=False,
            debug_fletch=False,
            debug_content=False
        )
        
        print(f"\n📊 API-Only Results:")
        print(f"   Videos: {result_api['videos']}")
        print(f"   Video count: {result_api['video_count']}")
        print(f"   App Store ID: {result_api['app_store_id']}")
        print(f"   Content.js count: {result_api['content_js_requests']}")
        
        await browser.close()
        
        # ========================================================================
        # COMPARISON
        # ========================================================================
        print("\n" + "="*80)
        print("COMPARISON")
        print("="*80)
        
        print(f"\nExpected:")
        print(f"   Videos: ['{EXPECTED_VIDEO}']")
        print(f"   App Store ID: {EXPECTED_APPSTORE}")
        
        print(f"\nFull HTML:")
        print(f"   Videos: {result_html['videos']} {'✅' if EXPECTED_VIDEO in result_html['videos'] else '❌'}")
        print(f"   App Store: {result_html['app_store_id']} {'✅' if result_html['app_store_id'] == EXPECTED_APPSTORE else '❌'}")
        
        print(f"\nAPI-Only:")
        print(f"   Videos: {result_api['videos']} {'✅' if EXPECTED_VIDEO in result_api['videos'] else '❌'}")
        print(f"   App Store: {result_api['app_store_id']} {'✅' if result_api['app_store_id'] == EXPECTED_APPSTORE else '❌'}")
        
        if result_html['videos'] and not result_api['videos']:
            print("\n⚠️  ISSUE: Full HTML extracts videos, but API-only doesn't!")
            print("   This means content.js responses are different OR extraction logic differs")
        elif result_html['videos'] == result_api['videos']:
            print("\n✅ BOTH methods extract the same videos!")
        else:
            print("\n⚠️  Different results between methods")

if __name__ == "__main__":
    asyncio.run(main())


