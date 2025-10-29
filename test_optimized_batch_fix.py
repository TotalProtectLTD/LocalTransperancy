#!/usr/bin/env python3
"""
Quick test to verify the optimized batch scraper now properly extracts data from the first creative.
Uses known-good creative IDs that have videos.
"""
import asyncio
import sys
from stress_test_scraper_optimized import scrape_batch_optimized

# Test batch with known-good creatives (confirmed to have videos)
TEST_BATCH = [
    {
        'id': 1,
        'creative_id': 'CR11718023440488202241',
        'advertiser_id': 'AR00503804302385479681'
    },
    {
        'id': 2,
        'creative_id': 'CR02498858822316064769',
        'advertiser_id': 'AR01587087172895244289'
    }
]

EXPECTED_RESULTS = {
    'CR11718023440488202241': {
        'videos': ['rkXH2aDmhDQ'],
        'appstore': '1435281792'
    },
    'CR02498858822316064769': {
        'videos': ['C_NGOLQCcBo', 'df0Aym2cJDM'],
        'appstore': '6747917719'
    }
}

async def main():
    print("="*80)
    print("TESTING OPTIMIZED BATCH SCRAPER - FIRST CREATIVE EXTRACTION FIX")
    print("="*80)
    print()
    print("Testing batch of 2 creatives:")
    print(f"  1. {TEST_BATCH[0]['creative_id']} (FULL HTML - should extract 1 video)")
    print(f"  2. {TEST_BATCH[1]['creative_id']} (API-only - should extract 2 videos)")
    print()
    print("="*80)
    print()
    
    # Run the batch scraper
    results = await scrape_batch_optimized(
        creative_batch=TEST_BATCH,
        proxy_config=None,  # No proxy for testing
        worker_id=0
    )
    
    print()
    print("="*80)
    print("RESULTS SUMMARY")
    print("="*80)
    print()
    
    # Analyze results
    success_count = 0
    for i, result in enumerate(results, 1):
        creative_id = TEST_BATCH[i-1]['creative_id']
        expected = EXPECTED_RESULTS[creative_id]
        
        print(f"{i}. {creative_id}")
        print(f"   Status: {'✅ SUCCESS' if result['success'] else '❌ FAILED'}")
        print(f"   Videos extracted: {result['video_count']}")
        print(f"   Video IDs: {result['videos']}")
        print(f"   App Store ID: {result['appstore_id']}")
        
        # Check if results match expectations
        if result['success']:
            videos_match = set(result['videos']) == set(expected['videos'])
            appstore_match = result['appstore_id'] == expected['appstore']
            
            if videos_match and appstore_match:
                print(f"   ✅ Extraction CORRECT (matches expected)")
                success_count += 1
            else:
                print(f"   ⚠️  Extraction MISMATCH")
                if not videos_match:
                    print(f"      Expected videos: {expected['videos']}")
                if not appstore_match:
                    print(f"      Expected App Store: {expected['appstore']}")
        else:
            print(f"   Error: {result.get('error', 'Unknown')}")
        
        print()
    
    print("="*80)
    print(f"TEST RESULT: {success_count}/2 creatives extracted correctly")
    print("="*80)
    
    if success_count == 2:
        print("\n✅ SUCCESS! The fix works - first creative now properly extracts data!")
        return 0
    else:
        print("\n⚠️  Some creatives failed or had incorrect extraction")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


