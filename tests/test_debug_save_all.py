#!/usr/bin/env python3
"""
Debug test - saves ALL responses for manual analysis.

This saves:
1. GetCreativeById API response
2. All content.js files
3. Comparison with HTML method

Usage:
    python3 test_debug_save_all.py
"""

import asyncio
import json
import sys
import os
from datetime import datetime

try:
    from google_ads_transparency_scraper_optimized import scrape_ads_transparency_api_only
    from google_ads_transparency_scraper import scrape_ads_transparency_page
    from google_ads_traffic import TrafficTracker
    from google_ads_browser import _setup_browser_context
    from playwright.async_api import async_playwright
except ImportError as e:
    print(f"ERROR: Could not import required functions: {e}")
    sys.exit(1)

# Test creative with known videos
ADVERTISER_ID = "AR01587087172895244289"
CREATIVE_ID = "CR02498858822316064769"
EXPECTED_VIDEOS = ["C_NGOLQCcBo", "df0Aym2cJDM"]
EXPECTED_APPSTORE = "6747917719"


async def test_and_save_all_debug_data():
    """Test and save all debug data for manual analysis."""
    print("="*80)
    print("DEBUG TEST - Saving All Responses")
    print("="*80)
    
    # Create debug directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_dir = f"/Users/rostoni/Downloads/LocalTransperancy/debug_comparison_{timestamp}"
    os.makedirs(debug_dir, exist_ok=True)
    
    print(f"\n📁 Debug directory: {debug_dir}")
    print(f"   Creative: {CREATIVE_ID}")
    print(f"   Expected: {len(EXPECTED_VIDEOS)} videos, App Store: {EXPECTED_APPSTORE}")
    
    async with async_playwright() as p:
        browser_setup = await _setup_browser_context(p, use_proxy=False, external_proxy=None)
        browser = browser_setup['browser']
        context = browser_setup['context']
        page = await context.new_page()
        
        # ========================================================================
        # METHOD 1: Full HTML scrape (for comparison - runs in separate context)
        # ========================================================================
        print("\n" + "="*80)
        print("METHOD 1: Full HTML Scrape (Original - for comparison)")
        print("="*80)
        
        url = f"https://adstransparency.google.com/advertiser/{ADVERTISER_ID}/creative/{CREATIVE_ID}?region=anywhere"
        
        print("Loading HTML page with original scraper...")
        html_result = await scrape_ads_transparency_page(
            page_url=url,
            use_proxy=False,
            external_proxy=None,
            debug_content=True  # This saves debug files
        )
        
        print(f"\n✅ HTML method completed:")
        print(f"   Success: {html_result.get('success')}")
        print(f"   Videos: {html_result.get('videos')}")
        print(f"   Video count: {html_result.get('video_count')}")
        print(f"   App Store: {html_result.get('app_store_id')}")
        print(f"   Content.js files: {html_result.get('content_js_requests')}")
        print(f"   API responses: {html_result.get('api_responses')}")
        
        # Save HTML result
        with open(f"{debug_dir}/01_html_result.json", 'w') as f:
            json.dump(html_result, f, indent=2)
        print(f"\n💾 Saved HTML result to 01_html_result.json")
        
        # ========================================================================
        # Now load page in OUR context to extract cookies properly
        # ========================================================================
        print("\n" + "="*80)
        print("Loading page in shared context to extract cookies...")
        print("="*80)
        
        print("Navigating to page...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        print("✅ Page loaded")
        
        # Wait for cookies to be set
        await asyncio.sleep(3)
        
        # Extract cookies from OUR context
        cookies = await context.cookies()
        print(f"🍪 Extracted {len(cookies)} cookies from shared context")
        
        # Save cookies
        with open(f"{debug_dir}/02_cookies.json", 'w') as f:
            json.dump(cookies, f, indent=2)
        print(f"💾 Saved cookies to 02_cookies.json")
        
        # ========================================================================
        # METHOD 2: API-only scrape (optimized method)
        # ========================================================================
        print("\n" + "="*80)
        print("METHOD 2: API-Only Scrape (Optimized)")
        print("="*80)
        
        # Create new page for clean test
        page2 = await context.new_page()
        tracker = TrafficTracker()
        
        print("Making API-only requests...")
        
        # Intercept API response
        api_response_captured = None
        content_js_captured = []
        
        async def capture_api_response(response):
            nonlocal api_response_captured, content_js_captured
            if 'GetCreativeById' in response.url:
                api_response_captured = {
                    'url': response.url,
                    'status': response.status,
                    'headers': dict(response.headers),
                    'text': await response.text()
                }
            elif 'fletch-render' in response.url:
                content_js_captured.append({
                    'url': response.url,
                    'status': response.status,
                    'headers': dict(response.headers),
                    'text': await response.text()
                })
        
        page2.on('response', capture_api_response)
        
        api_result = await scrape_ads_transparency_api_only(
            advertiser_id=ADVERTISER_ID,
            creative_id=CREATIVE_ID,
            cookies=cookies,
            page=page2,
            tracker=tracker,
            debug_appstore=False,
            debug_fletch=False,
            debug_content=False
        )
        
        print(f"\n✅ API-only method completed:")
        print(f"   Success: {api_result.get('success')}")
        print(f"   Videos: {api_result.get('videos')}")
        print(f"   Video count: {api_result.get('video_count')}")
        print(f"   App Store: {api_result.get('app_store_id')}")
        print(f"   Content.js files: {api_result.get('content_js_requests')}")
        print(f"   API responses: {api_result.get('api_responses')}")
        
        # Save API result
        with open(f"{debug_dir}/03_api_result.json", 'w') as f:
            json.dump(api_result, f, indent=2)
        print(f"\n💾 Saved API-only result to 03_api_result.json")
        
        # Save captured API response
        if api_response_captured:
            with open(f"{debug_dir}/04_api_response_raw.json", 'w') as f:
                json.dump(api_response_captured, f, indent=2)
            print(f"💾 Saved raw API response to 04_api_response_raw.json")
        
        # Save captured content.js files
        for i, content in enumerate(content_js_captured, 1):
            with open(f"{debug_dir}/05_content_{i:02d}.js", 'w') as f:
                f.write(content['text'])
            with open(f"{debug_dir}/05_content_{i:02d}_meta.json", 'w') as f:
                json.dump({
                    'url': content['url'],
                    'status': content['status'],
                    'headers': content['headers'],
                    'size': len(content['text'])
                }, f, indent=2)
            print(f"💾 Saved content.js #{i} to 05_content_{i:02d}.js")
        
        # Save tracker data
        tracker_data = {
            'content_js_requests': [
                {
                    'url': req['url'],
                    'text_length': len(req['text']),
                    'text_preview': req['text'][:500]
                }
                for req in tracker.content_js_requests
            ],
            'api_responses': [
                {
                    'url': resp['url'],
                    'type': resp.get('type'),
                    'text_length': len(resp['text']),
                    'text_preview': resp['text'][:500]
                }
                for resp in tracker.api_responses
            ]
        }
        
        with open(f"{debug_dir}/06_tracker_data.json", 'w') as f:
            json.dump(tracker_data, f, indent=2)
        print(f"💾 Saved tracker data to 06_tracker_data.json")
        
        await browser.close()
        
        # ========================================================================
        # Comparison
        # ========================================================================
        print("\n" + "="*80)
        print("COMPARISON")
        print("="*80)
        
        html_videos = set(html_result.get('videos', []))
        api_videos = set(api_result.get('videos', []))
        expected = set(EXPECTED_VIDEOS)
        
        comparison = {
            'expected_videos': list(expected),
            'html_videos': list(html_videos),
            'api_videos': list(api_videos),
            'html_matches_expected': html_videos == expected,
            'api_matches_expected': api_videos == expected,
            'html_matches_api': html_videos == api_videos,
            'html_appstore': html_result.get('app_store_id'),
            'api_appstore': api_result.get('app_store_id'),
            'expected_appstore': EXPECTED_APPSTORE,
            'html_content_js_count': html_result.get('content_js_requests'),
            'api_content_js_count': api_result.get('content_js_requests'),
            'html_api_responses': html_result.get('api_responses'),
            'api_api_responses': api_result.get('api_responses')
        }
        
        with open(f"{debug_dir}/07_comparison.json", 'w') as f:
            json.dump(comparison, f, indent=2)
        
        print(f"\nExpected videos: {list(expected)}")
        print(f"HTML videos:     {list(html_videos)} {'✅' if html_videos == expected else '❌'}")
        print(f"API videos:      {list(api_videos)} {'✅' if api_videos == expected else '❌'}")
        print(f"\nExpected App Store: {EXPECTED_APPSTORE}")
        print(f"HTML App Store:     {html_result.get('app_store_id')} {'✅' if html_result.get('app_store_id') == EXPECTED_APPSTORE else '❌'}")
        print(f"API App Store:      {api_result.get('app_store_id')} {'✅' if api_result.get('app_store_id') == EXPECTED_APPSTORE else '❌'}")
        
        print(f"\n💾 Saved comparison to 07_comparison.json")
        
        # ========================================================================
        # Summary
        # ========================================================================
        print("\n" + "="*80)
        print("DEBUG DATA SAVED")
        print("="*80)
        print(f"\nAll debug files saved to:")
        print(f"  {debug_dir}")
        print(f"\nFiles:")
        print(f"  01_html_result.json       - Full HTML scrape result")
        print(f"  02_cookies.json           - Extracted cookies")
        print(f"  03_api_result.json        - API-only scrape result")
        print(f"  04_api_response_raw.json  - Raw GetCreativeById API response")
        print(f"  05_content_XX.js          - Content.js files from API method")
        print(f"  05_content_XX_meta.json   - Metadata for content.js files")
        print(f"  06_tracker_data.json      - Tracker data (requests/responses)")
        print(f"  07_comparison.json        - Comparison between methods")
        print(f"  debug/*.json              - HTML method debug files")
        
        print(f"\n📊 Next steps:")
        print(f"  1. Compare content.js files from HTML vs API method")
        print(f"  2. Search for video IDs in content.js files: grep -i 'C_NGOLQCcBo\\|df0Aym2cJDM' {debug_dir}/05_content_*.js")
        print(f"  3. Check API response structure: cat {debug_dir}/04_api_response_raw.json | jq")
        print(f"  4. Compare file sizes and content")
        
        return comparison


async def main():
    try:
        comparison = await test_and_save_all_debug_data()
        
        html_ok = comparison['html_matches_expected']
        api_ok = comparison['api_matches_expected']
        
        if html_ok and api_ok:
            print("\n✅✅✅ SUCCESS: Both methods work correctly!")
            sys.exit(0)
        elif html_ok:
            print("\n⚠️  HTML works, API-only needs investigation")
            sys.exit(1)
        else:
            print("\n⚠️  Investigation needed for both methods")
            sys.exit(1)
            
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

