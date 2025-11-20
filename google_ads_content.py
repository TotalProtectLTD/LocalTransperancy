"""
Content Processing Pipeline for Google Ads Transparency Scraper

This module provides the content processing pipeline for the Google Ads Transparency
scraper suite. It implements intelligent waiting, creative identification, and data
extraction functionality for both dynamic and static ad content.

The pipeline consists of three sequential stages:

1. Smart Wait (_smart_wait_for_content):
   - Implements intelligent waiting with multiple early-exit conditions
   - Monitors API responses and content.js files for efficient content loading
   - Handles static/cached content detection
   - Exits early when all expected content is received or errors are detected

2. Creative Identification (_identify_creative):
   - Determines the real 12-digit numeric creative ID
   - Uses API responses (GetCreativeById, SearchCreatives) for ID extraction
   - Handles static content detection (no ID needed for static ads)
   - Provides fallback handling when API extraction fails

3. Data Extraction (_extract_data):
   - Extracts YouTube video IDs from content.js files
   - Extracts App Store IDs from Apple App Store URLs
   - Handles base64-encoded app IDs (if extract_app_ids module available)
   - Processes matched fletch-render content.js files for data extraction

The pipeline handles both dynamic content (with fletch-render IDs) and static/cached
content (images, HTML text ads). It follows the established patterns with comprehensive
docstrings, type hints, and error handling.

Dependencies:
    - google_ads_config: Configuration constants (timeouts, intervals, patterns)
    - google_ads_api_analysis: API response analysis functions
    - google_ads_extractors: Data extraction functions (videos, App Store IDs)
    - google_ads_debug: Debug file saving functions
    - extract_app_ids: Optional base64 app ID extraction (external module)
"""

import sys
import re
from typing import Dict, List, Tuple, Optional, Set, Any

# Import app ID extraction from base64
try:
    from extract_app_ids import extract_app_ids
except ImportError:
    extract_app_ids = None

# Import configuration constants
from google_ads_config import (
    MAX_CONTENT_WAIT,
    CONTENT_CHECK_INTERVAL,
    XHR_DETECTION_THRESHOLD,
    SEARCH_CREATIVES_WAIT,
    API_SEARCH_CREATIVES,
    PATTERN_FLETCH_RENDER_ID,
    VERBOSE_LOGGING
)

# Import API analysis functions
from google_ads_api_analysis import (
    check_empty_get_creative_by_id,
    check_creative_in_search_creatives,
    check_if_static_cached_creative,
    extract_expected_fletch_renders_from_api,
    extract_real_creative_id_from_api
)

# Import data extraction functions
from google_ads_extractors import (
    extract_youtube_videos_from_text,
    extract_app_store_id_from_text,
    extract_play_store_id_from_text
)

# Import debug functions
from google_ads_debug import (
    save_fletch_render_debug_file,
    save_appstore_debug_file
)


# ============================================================================
# CONTENT PROCESSING PIPELINE FUNCTIONS
# ============================================================================

async def _smart_wait_for_content(
    page,  # Playwright Page instance
    page_url: str,
    tracker: 'TrafficTracker',
    content_js_responses: List[Tuple[str, str]],
    all_xhr_fetch_requests: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Smart wait for dynamic content with multiple early-exit conditions.
    
    Implements an intelligent waiting algorithm that monitors API responses
    and content.js files, exiting early when all expected content is received
    or when errors are detected. This avoids unnecessary waiting and improves
    scraping efficiency.
    
    Early-exit conditions:
    1. No XHR/fetch after 10s: JavaScript not executing, exit early
    2. Static content detected: No dynamic content.js needed, exit immediately
    3. Empty GetCreativeById + creative not in SearchCreatives: Creative not found
    4. All expected fletch-renders received: All content captured, exit early
    
    Args:
        page: Playwright Page instance for timeout operations.
        page_url: Target URL being scraped (contains creative ID).
        tracker: TrafficTracker instance with API responses.
        content_js_responses: List of captured (url, text) tuples.
        all_xhr_fetch_requests: List of XHR/fetch request metadata.
    
    Returns:
        Dictionary containing:
            - 'elapsed': Total elapsed time in seconds
            - 'expected_fletch_renders': Set of expected fletch-render IDs from API
            - 'found_fletch_renders': Set of fletch-render IDs actually received
            - 'critical_errors': List of error messages from wait phase
            - 'static_content_detected': Dict with static content info or None
            - 'content_js_responses': Updated list (passed through)
            - 'all_xhr_fetch_requests': Updated list (passed through)
    
    Example:
        result = await _smart_wait_for_content(
            page, page_url, tracker, content_js_responses, all_xhr_fetch_requests
        )
        
        if result['static_content_detected']:
            print("Static content - no dynamic files needed")
        elif result['expected_fletch_renders'] == result['found_fletch_renders']:
            print(f"All {len(result['found_fletch_renders'])} expected files received")
        else:
            print(f"Missing {len(result['expected_fletch_renders'] - result['found_fletch_renders'])} files")
    
    Note:
        The smart wait algorithm:
        1. Monitors API responses for expected fletch-render IDs
        2. Matches received content.js files against expected IDs
        3. Exits early when all expected content received
        4. Handles edge cases (static content, empty API, missing creatives)
        5. Maximum wait time: MAX_CONTENT_WAIT seconds (default 60s)
        6. Check interval: CONTENT_CHECK_INTERVAL seconds (default 0.5s)
    """
    if VERBOSE_LOGGING:
        print("Waiting for dynamic content...")
        sys.stdout.flush()  # Force immediate output in concurrent environments
    
    # Initialize state variables
    max_wait = MAX_CONTENT_WAIT
    elapsed = 0
    expected_fletch_renders = set()
    found_fletch_renders = set()
    critical_errors = []
    last_api_count = 0
    static_content_detected = None
    empty_get_creative_detected = False
    empty_get_creative_detection_time = None
    
    # Main wait loop: Check every 0.5s for new content, up to 60s max
    # Multiple early-exit conditions optimize waiting time
    while elapsed < max_wait:
        # Early exit condition 1: No XHR/fetch after 10 seconds
        # If JavaScript isn't executing, API responses won't arrive
        # Exit early to avoid full 60s timeout
        if elapsed >= XHR_DETECTION_THRESHOLD and len(all_xhr_fetch_requests) == 0:
            if VERBOSE_LOGGING:
                print(f"  ⚠️  No XHR/fetch requests detected after {elapsed:.1f}s")
                print(f"  ⚠️  JavaScript may not be executing - exiting wait early")
            break
        
        # Early exit condition 2: Empty GetCreativeById detection
        # When GetCreativeById returns {}, the creative may not exist
        # Wait 3 seconds for SearchCreatives to verify existence
        # If creative not in SearchCreatives, exit early (creative not found)
        if not empty_get_creative_detected and len(tracker.api_responses) > 0:
            # Check if GetCreativeById is empty
            if check_empty_get_creative_by_id(tracker.api_responses, page_url):
                empty_get_creative_detected = True
                empty_get_creative_detection_time = elapsed
                
                # Check if SearchCreatives already exists
                has_search_creatives = any(API_SEARCH_CREATIVES in resp.get('url', '') for resp in tracker.api_responses)
                
                if has_search_creatives:
                    # SearchCreatives already arrived, check if creative is in it
                    creative_in_search = check_creative_in_search_creatives(tracker.api_responses, page_url)
                    
                    if not creative_in_search:
                        print(f"  ⚠️  Empty GetCreativeById + creative not in SearchCreatives")
                        print(f"  ⚠️  Creative not found - exiting wait early at {elapsed:.1f}s")
                        break
                else:
                    # SearchCreatives not yet arrived, will wait 3 seconds
                    print(f"  ⚠️  Empty GetCreativeById detected at {elapsed:.1f}s")
                    print(f"  ⚠️  Waiting {SEARCH_CREATIVES_WAIT}s for SearchCreatives to arrive...")
        
        # Check if 3 seconds passed since empty GetCreativeById detection
        if empty_get_creative_detected and empty_get_creative_detection_time is not None:
            if elapsed >= empty_get_creative_detection_time + SEARCH_CREATIVES_WAIT:
                # 3 seconds passed, check again
                has_search_creatives = any(API_SEARCH_CREATIVES in resp.get('url', '') for resp in tracker.api_responses)
                
                if has_search_creatives:
                    creative_in_search = check_creative_in_search_creatives(tracker.api_responses, page_url)
                    if not creative_in_search:
                        print(f"  ⚠️  Creative not in SearchCreatives after 3s wait")
                        print(f"  ⚠️  Creative not found - exiting wait early at {elapsed:.1f}s")
                        break
                else:
                    print(f"  ⚠️  SearchCreatives not arrived after 3s wait")
                    print(f"  ⚠️  Creative likely not found - exiting wait early at {elapsed:.1f}s")
                    break
        
        # Step 1: Monitor API responses for new data
        # When new API responses arrive, extract expected fletch-render IDs
        # Priority check: Detect static/cached content first (no dynamic files needed)
        current_api_count = len(tracker.api_responses)
        if current_api_count > last_api_count:
            # Priority check: Is this static/cached content?
            # Static image ads and cached HTML ads don't have dynamic content.js
            # If detected, exit immediately (no need to wait for content.js)
            static_check = check_if_static_cached_creative(tracker.api_responses, page_url)
            if static_check:
                if VERBOSE_LOGGING:
                    print(f"\n✅ Static/cached content detected in API response!")
                    content_type = static_check.get('content_type', 'unknown')
                    ad_type = 'image' if content_type == 'image' else 'HTML text' if content_type == 'html' else 'cached'
                    print(f"   Type: {ad_type} ad")
                    print(f"   Creative ID: {static_check['creative_id']}")
                    print(f"   No dynamic content.js needed - exiting wait early")
                static_content_detected = static_check
                break
            
            # Extract expected fletch-render IDs from GetCreativeById API response
            # These IDs tell us which content.js files to expect
            # Update expectations when new API data arrives
            new_expected = extract_expected_fletch_renders_from_api(
                tracker.api_responses, 
                page_url
            )
            
            if new_expected and new_expected != expected_fletch_renders:
                # Update expected fletch-renders with new data
                old_count = len(expected_fletch_renders)
                expected_fletch_renders = new_expected
                
                if old_count == 0:
                    print(f"  Expecting {len(expected_fletch_renders)} content.js with specific fletch-render IDs")
                else:
                    print(f"  Updated expectations: now expecting {len(expected_fletch_renders)} content.js (was {old_count})")
            
            last_api_count = current_api_count
        
        # Step 2: Match received content.js files against expected fletch-render IDs
        # Extract fletch-render ID from each content.js URL
        # Track newly found IDs and check if all expected IDs received
        # Exit early when all expected content captured
        if expected_fletch_renders:
            # Check all received content.js responses for matching fletch-render IDs
            new_found_fletch_renders = set()
            for url, text in content_js_responses:
                fr_match = re.search(PATTERN_FLETCH_RENDER_ID, url)
                if fr_match:
                    fr_id = fr_match.group(1)
                    if fr_id in expected_fletch_renders:
                        new_found_fletch_renders.add(fr_id)
            
            # Report newly found fletch-renders
            newly_found = new_found_fletch_renders - found_fletch_renders
            if newly_found:
                for fr_id in newly_found:
                    print(f"  ✓ Got content.js {len(new_found_fletch_renders)}/{len(expected_fletch_renders)} after {elapsed:.1f}s")
            
            found_fletch_renders = new_found_fletch_renders
            
            # Got all expected content.js! Stop waiting
            if len(found_fletch_renders) == len(expected_fletch_renders):
                print(f"  ✅ Got ALL {len(expected_fletch_renders)} expected content.js responses in {elapsed:.1f}s!")
                sys.stdout.flush()
                break
        
        await page.wait_for_timeout(int(CONTENT_CHECK_INTERVAL * 1000))
        elapsed += CONTENT_CHECK_INTERVAL
    
    # Validate wait results
    if len(content_js_responses) == 0:
        print(f"  ⚠️  No content.js responses after {elapsed:.1f}s (may be display/text ad)")
        if elapsed >= max_wait:
            critical_errors.append("TIMEOUT: No content.js responses received after max wait time")
    elif expected_fletch_renders and len(found_fletch_renders) == 0:
        print(f"  ⚠️  Expected {len(expected_fletch_renders)} fletch-renders but none arrived")
        critical_errors.append(f"INCOMPLETE: Expected {len(expected_fletch_renders)} fletch-render content.js but none arrived")
    elif expected_fletch_renders and len(found_fletch_renders) < len(expected_fletch_renders):
        missing_count = len(expected_fletch_renders) - len(found_fletch_renders)
        print(f"  ⚠️  Missing {missing_count}/{len(expected_fletch_renders)} expected fletch-renders")
        critical_errors.append(f"INCOMPLETE: Only got {len(found_fletch_renders)}/{len(expected_fletch_renders)} expected content.js")
    elif not expected_fletch_renders:
        print(f"  ℹ️  No fletch-render IDs from API, will use creative ID matching")
    
    return {
        'elapsed': elapsed,
        'expected_fletch_renders': expected_fletch_renders,
        'found_fletch_renders': found_fletch_renders,
        'critical_errors': critical_errors,
        'static_content_detected': static_content_detected,
        'content_js_responses': content_js_responses,
        'all_xhr_fetch_requests': all_xhr_fetch_requests
    }


def _identify_creative(
    tracker: 'TrafficTracker',
    page_url: str,
    static_content_info: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Identify the real creative ID using API responses or static content detection.
    
    Determines the 12-digit numeric creative ID needed for data extraction.
    Handles three scenarios:
    1. Static/cached content: No creative ID needed (uses static content info)
    2. API extraction: Extracts ID from GetCreativeById or SearchCreatives
    3. API failure: Unable to identify creative
    
    Args:
        tracker: TrafficTracker instance with captured API responses.
        page_url: Target URL containing the CR-prefixed creative ID.
        static_content_info: Dictionary with static content detection results,
                            or None if content is dynamic.
    
    Returns:
        Dictionary containing:
            - 'real_creative_id': 12-digit numeric creative ID string or None
            - 'method_used': Identification method string:
                * 'api': Successfully extracted from API
                * 'api-failed': API extraction failed
                * 'static-detected': Static content (no ID needed)
    
    Example:
        result = _identify_creative(tracker, page_url, static_content_info)
        
        if result['method_used'] == 'api':
            print(f"Creative ID: {result['real_creative_id']}")
        elif result['method_used'] == 'static-detected':
            print("Static content - no creative ID needed")
        else:
            print("Failed to identify creative ID")
    
    Note:
        The creative ID is used to match content.js files and extract data.
        For static content, no matching is needed (content is cached).
    """
    print("\n" + "="*80)
    print("IDENTIFYING REAL CREATIVE")
    print("="*80)
    
    real_creative_id = None
    method_used = None
    
    # Check if this is static/cached content
    if static_content_info:
        print(f"ℹ️  Detected static/cached content:")
        print(f"   Creative ID: {static_content_info['creative_id']}")
        print(f"   Reason: {static_content_info['reason']}")
        print(f"   No matching content.js files found")
        method_used = 'static-detected'
        # Don't set real_creative_id - this prevents guessing from wrong content.js files
    else:
        # Method 1: Try API method
        real_creative_id = extract_real_creative_id_from_api(tracker.api_responses, page_url)
        
        if real_creative_id:
            method_used = 'api'
            print(f"✅ API Method: Real creative ID = {real_creative_id}")
            print(f"   (Extracted from GetCreativeById API response)")
        else:
            print("❌ Could not identify real creative ID!")
            method_used = 'api-failed'
    
    return {'real_creative_id': real_creative_id, 'method_used': method_used}


def _extract_data(
    content_js_responses: List[Tuple[str, str]],
    found_fletch_renders: Set[str],
    static_content_info: Optional[Dict[str, Any]],
    real_creative_id: Optional[str],
    debug_fletch: bool,
    debug_appstore: bool
) -> Dict[str, Any]:
    """
    Extract YouTube video IDs, App Store IDs, and Play Store IDs from content.js files.
    
    Processes matched content.js files to extract:
    1. YouTube video IDs: From ytimg.com thumbnails and video_id fields
    2. App Store IDs: From Apple App Store URLs (apps.apple.com, itunes.apple.com)
    3. Play Store IDs: From Google Play Store URLs (play.google.com/store/apps/details?id=...)
    4. App IDs from base64: From base64-encoded ad parameters (only if "App Store" text present)
    
    Handles three extraction scenarios:
    1. Fletch-render method: Extract from matched dynamic content.js files
    2. Static content: Skip extraction (no dynamic content available)
    3. No method: No content.js files matched or available
    
    Args:
        content_js_responses: List of (url, text) tuples for all captured content.js files.
        found_fletch_renders: Set of fletch-render IDs that were matched.
        static_content_info: Dictionary with static content info, or None if dynamic.
        real_creative_id: 12-digit numeric creative ID, or None if not identified.
        debug_fletch: If True, save debug files for each fletch-render content.js.
        debug_appstore: If True, save debug files when App Store ID is found.
    
    Returns:
        Dictionary containing:
            - 'unique_videos': List of unique YouTube video IDs (11 characters each)
            - 'videos_by_request': List of dicts with 'url' and 'videos' per content.js
            - 'app_store_id': App Store ID string (9-10 digits) or None
            - 'play_store_id': Play Store package ID string (e.g., 'com.example.app') or None
            - 'app_ids_from_base64': List of app IDs (10-13 digits) extracted from base64
            - 'extraction_method': Method used ('fletch-render', 'static-content', 'none')
            - 'all_videos': List of all videos before deduplication (for statistics)
    
    Example:
        result = _extract_data(
            content_js_responses,
            found_fletch_renders={'13006300890096633430'},
            static_content_info=None,
            real_creative_id='773510960098',
            debug_fletch=False,
            debug_appstore=False
        )
        
        print(f"Found {len(result['unique_videos'])} unique videos")
        for video_id in result['unique_videos']:
            print(f"  https://youtube.com/watch?v={video_id}")
        
        if result['app_store_id']:
            print(f"App Store ID: {result['app_store_id']}")
    
    Note:
        Video extraction uses multiple regex patterns to handle different formats:
        - ytimg.com thumbnail URLs
        - video_id JSON fields (with regular or escaped quotes)
        - video_videoId JSON fields (camelCase variant)
        
        App Store ID extraction handles multiple URL formats:
        - Standard: apps.apple.com/us/app/id123456789
        - Escaped: URL-encoded versions with %2F, \x2F
        - Direct: /app/id123456789
        - JSON: "appId": "123456789"
    """
    print("\n" + "="*80)
    print("EXTRACTING VIDEOS")
    print("="*80)
    
    all_videos = []
    videos_by_request = []
    app_store_id = None
    play_store_id = None
    app_ids_from_base64 = set()  # Collect app IDs extracted from base64
    extraction_method = None
    
    # SKIP EXTRACTION FOR STATIC/CACHED CONTENT
    if static_content_info:
        extraction_method = 'static-content'
        unique_videos = []
        content_type = static_content_info.get('content_type', 'unknown')
        ad_type = 'image' if content_type == 'image' else 'HTML text' if content_type == 'html' else 'cached'
        print("\nℹ️  Static/cached content detected - skipping extraction")
        print(f"   This is a {ad_type} ad with no video/app content")
        print(f"   Content.js files present are unrelated (decoys from other ads)")
    # PRIMARY METHOD: Use fletch-render IDs if available
    elif found_fletch_renders:
        extraction_method = 'fletch-render'
        print(f"\nUsing fletch-render IDs to filter content.js (method: precise API matching)")
        print(f"Processing {len(found_fletch_renders)} matched fletch-render IDs")
        
        # Iterate through all content.js responses
        # Only process files whose fletch-render ID matches our expected set
        # This ensures we extract data from the correct creative's content
        for url, text in content_js_responses:
            fr_match = re.search(PATTERN_FLETCH_RENDER_ID, url)
            if fr_match and fr_match.group(1) in found_fletch_renders:
                # This is one of our expected content.js!
                
                # Save debug file if fletch debug mode enabled
                if debug_fletch:
                    save_fletch_render_debug_file(
                        fr_match.group(1),
                        text,
                        url,
                        real_creative_id
                    )
                
                # Extract YouTube video IDs from content.js text
                # Uses multiple regex patterns to handle different video ID formats
                # Deduplicates videos per request to avoid counting duplicates
                videos = extract_youtube_videos_from_text(text)
                
                if videos:
                    videos_by_request.append({
                        'url': url,
                        'url_short': url[:100] + '...' if len(url) > 100 else url,
                        'videos': list(set(videos))
                    })
                    all_videos.extend(videos)
                    print(f"  Found {len(set(videos))} video(s) in fletch-render-{fr_match.group(1)[:15]}...")
                
                # Extract App Store ID if not already found
                # Only need one App Store ID per creative (first match wins)
                # Saves debug file if debug_appstore flag is enabled
                if not app_store_id:
                    result = extract_app_store_id_from_text(text)
                    if result:
                        app_store_id, pattern_description = result
                        if debug_appstore:
                            save_appstore_debug_file(
                                app_store_id, 
                                text, 
                                'fletch-render', 
                                url, 
                                fr_match.group(1),
                                pattern_description
                            )
                
                # Extract Play Store ID if not already found
                # Only need one Play Store ID per creative (first match wins)
                if not play_store_id:
                    result = extract_play_store_id_from_text(text)
                    if result:
                        play_store_id, pattern_description = result
                        print(f"  Found Play Store ID: {play_store_id} in fletch-render-{fr_match.group(1)[:15]}...")
                
                # Extract app IDs from base64 in content.js response
                # This handles app IDs hidden in base64-encoded ad parameters
                # Only analyze if content.js contains "App Store" text
                if extract_app_ids is not None and "App Store" in text:
                    try:
                        base64_app_ids = extract_app_ids(text)
                        if base64_app_ids:
                            app_ids_from_base64.update(base64_app_ids)
                            print(f"  Found {len(base64_app_ids)} app ID(s) from base64 in fletch-render-{fr_match.group(1)[:15]}...")
                    except Exception as e:
                        # Silent fail - don't break scraping if base64 extraction has issues
                        pass
        
        # Deduplicate videos
        unique_videos = list(set(all_videos))
        
        print(f"\n✅ Total unique videos extracted: {len(unique_videos)}")
        for vid in unique_videos:
            print(f"   • {vid}") 
    
    # NO METHOD AVAILABLE
    else:
        extraction_method = 'none'
        unique_videos = []
        print("❌ Cannot extract videos without fletch-render IDs")
    
    if app_store_id:
        print(f"\n✅ App Store ID: {app_store_id}")
    else:
        print("\n⚠️  No App Store ID found")
    
    if play_store_id:
        print(f"\n✅ Play Store ID: {play_store_id}")
    else:
        print("\n⚠️  No Play Store ID found")
    
    # Display base64-extracted app IDs
    if app_ids_from_base64:
        print(f"\n✅ App IDs from base64: {len(app_ids_from_base64)} found")
        for app_id in sorted(app_ids_from_base64):
            print(f"   • {app_id}")
    
    return {
        'unique_videos': unique_videos,
        'videos_by_request': videos_by_request,
        'app_store_id': app_store_id,
        'play_store_id': play_store_id,
        'app_ids_from_base64': list(app_ids_from_base64),  # Convert set to list for JSON serialization
        'extraction_method': extraction_method,
        'all_videos': all_videos
    }

