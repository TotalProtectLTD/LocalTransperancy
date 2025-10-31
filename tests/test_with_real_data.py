#!/usr/bin/env python3
"""
Test optimized scraper with real creatives that have videos and App Store IDs.

These creatives are known to have videos, so we can validate that the API-only
method correctly extracts them.

Usage:
    python3 test_with_real_data.py
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

# Real test data with known videos and App Store IDs
TEST_CREATIVES = [
    {
        "creative_id": "CR02498858822316064769",
        "advertiser_id": "AR01587087172895244289",
        "expected_videos": ["C_NGOLQCcBo", "df0Aym2cJDM"],
        "expected_appstore": "6747917719",
        "video_count": 2
    },
    {
        "creative_id": "CR08350200220595781633",
        "advertiser_id": "AR06387929375014125569",
        "expected_videos": ["zhRWqcGzZnE", "A8El5lJjma0", "2mAuvzXILAc"],
        "expected_appstore": "6449424463",
        "video_count": 3
    },
    {
        "creative_id": "CR09448436414883561473",
        "advertiser_id": "AR06271423714185707521",
        "expected_videos": ["pnrFt2M7NLI", "lb6_3V_gmyg", "OzfHAWFA1bE"],
        "expected_appstore": "6749265106",
        "video_count": 3
    },
    {
        "creative_id": "CR18180675299308470273",
        "advertiser_id": "AR10198443515579465729",
        "expected_videos": ["HuIvuHppITE", "F7ES8DmmcwY"],
        "expected_appstore": "6447543971",
        "video_count": 2
    },
    {
        "creative_id": "CR00029328218540474369",
        "advertiser_id": "AR14933299815847559169",
        "expected_videos": ["zDAyGpSXuSY", "qHfrAJ2XT9w", "cryfCrgV8G0"],
        "expected_appstore": "6745587171",
        "video_count": 3
    },
    {
        "creative_id": "CR11718023440488202241",
        "advertiser_id": "AR00503804302385479681",
        "expected_videos": ["rkXH2aDmhDQ"],
        "expected_appstore": "1435281792",
        "video_count": 1
    }
]


async def test_batch_with_real_data():
    """Test batch scraping with creatives that have known videos."""
    print("="*80)
    print("TESTING WITH REAL DATA - Creatives with Videos & App Store IDs")
    print("="*80)
    
    results = []
    
    async with async_playwright() as p:
        # Setup browser context (shared for all creatives)
        browser_setup = await _setup_browser_context(p, use_proxy=False, external_proxy=None)
        browser = browser_setup['browser']
        context = browser_setup['context']
        page = await context.new_page()
        
        # ========================================================================
        # STEP 1: Load first creative with FULL HTML scraping
        # ========================================================================
        print("\n" + "="*80)
        print("STEP 1: Loading first creative (FULL HTML METHOD)")
        print("="*80)
        
        first = TEST_CREATIVES[0]
        first_url = f"https://adstransparency.google.com/advertiser/{first['advertiser_id']}/creative/{first['creative_id']}?region=anywhere"
        
        print(f"Creative: {first['creative_id']}")
        print(f"Expected: {first['video_count']} videos, App Store ID: {first['expected_appstore']}")
        print("Loading HTML page to extract cookies...")
        
        try:
            # Navigate to the page to set cookies
            await page.goto(first_url, wait_until="domcontentloaded", timeout=60000)
            print("✅ Page loaded")
            
            # Wait for cookies to be set
            await asyncio.sleep(3)
            
            # Extract cookies
            cookies = await context.cookies()
            print(f"✅ Extracted {len(cookies)} cookies for session reuse")
            
            if len(cookies) == 0:
                print("⚠️  WARNING: No cookies extracted, API-only method may not work")
            
        except Exception as e:
            print(f"❌ Failed to load first creative: {e}")
            await browser.close()
            return False
        
        # Add first creative to results for processing with API-only method too
        print(f"\n📝 Note: All {len(TEST_CREATIVES)} creatives will use API-only method for testing")
        
        # ========================================================================
        # STEP 2: Test API-only method with remaining creatives
        # ========================================================================
        print("\n" + "="*80)
        print("STEP 2: Testing API-only method with remaining creatives")
        print("="*80)
        
        for i, creative in enumerate(TEST_CREATIVES, 1):
            print(f"\n--- Creative {i}/{len(TEST_CREATIVES)} ---")
            print(f"ID: {creative['creative_id']}")
            print(f"Expected: {creative['video_count']} videos, App Store: {creative['expected_appstore']}")
            
            tracker = TrafficTracker()
            
            try:
                result = await scrape_ads_transparency_api_only(
                    advertiser_id=creative['advertiser_id'],
                    creative_id=creative['creative_id'],
                    cookies=cookies,
                    page=page,
                    tracker=tracker,
                    debug_appstore=False,
                    debug_fletch=False,
                    debug_content=False
                )
                
                # Check results
                found_videos = set(result.get('videos', []))
                expected_videos = set(creative['expected_videos'])
                videos_match = found_videos == expected_videos
                
                found_appstore = result.get('app_store_id')
                appstore_match = found_appstore == creative['expected_appstore']
                
                print(f"\n✅ API-only completed:")
                print(f"   Success: {result.get('success')}")
                print(f"   Found videos: {len(found_videos)} {list(found_videos)}")
                print(f"   Expected videos: {len(expected_videos)} {list(expected_videos)}")
                print(f"   Videos match: {'✅' if videos_match else '❌'}")
                print(f"   Found App Store: {found_appstore}")
                print(f"   Expected App Store: {creative['expected_appstore']}")
                print(f"   App Store match: {'✅' if appstore_match else '❌'}")
                print(f"   Duration: {result.get('duration_ms'):.0f}ms")
                
                if not videos_match:
                    print(f"\n⚠️  Video mismatch:")
                    print(f"   Missing: {expected_videos - found_videos}")
                    print(f"   Extra: {found_videos - expected_videos}")
                
                results.append({
                    'creative_id': creative['creative_id'],
                    'success': result.get('success'),
                    'videos_match': videos_match,
                    'appstore_match': appstore_match,
                    'found_videos': len(found_videos),
                    'expected_videos': len(expected_videos),
                    'content_js_count': result.get('content_js_requests', 0)
                })
                
            except Exception as e:
                print(f"❌ Failed: {e}")
                import traceback
                traceback.print_exc()
                results.append({
                    'creative_id': creative['creative_id'],
                    'success': False,
                    'videos_match': False,
                    'appstore_match': False,
                    'error': str(e)
                })
        
        await browser.close()
        
        # ========================================================================
        # STEP 3: Summary
        # ========================================================================
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        
        total = len(results)
        success_count = sum(1 for r in results if r['success'])
        videos_match_count = sum(1 for r in results if r.get('videos_match'))
        appstore_match_count = sum(1 for r in results if r.get('appstore_match'))
        
        print(f"\nResults for {total} creatives:")
        print(f"  Success: {success_count}/{total}")
        print(f"  Videos extracted correctly: {videos_match_count}/{total}")
        print(f"  App Store ID correct: {appstore_match_count}/{total}")
        
        if success_count == total and videos_match_count == total and appstore_match_count == total:
            print("\n✅✅✅ PERFECT! All creatives extracted correctly!")
            print("\n🚀 The optimized scraper is working perfectly!")
            print("   Ready for production with 65% bandwidth savings!")
            return True
        elif success_count == total:
            print(f"\n⚠️  All scraped successfully, but data mismatch:")
            print(f"   Videos: {videos_match_count}/{total} correct")
            print(f"   App Store: {appstore_match_count}/{total} correct")
            print("\n   This might be due to:")
            print("   - Content.js files not being fetched with correct data")
            print("   - Regex extraction not finding the patterns")
            print("   - Different content returned by API vs HTML")
            return False
        else:
            print(f"\n❌ Some scrapes failed: {total - success_count}/{total}")
            return False


async def main():
    try:
        success = await test_batch_with_real_data()
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

