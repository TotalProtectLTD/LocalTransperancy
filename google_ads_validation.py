"""
Google Ads Transparency Scraper - Validation Module

This module provides execution validation functionality for the Google Ads
Transparency scraper suite. It performs comprehensive validation checks to
determine if a scraping operation was successful.

Validation checks include:
1. Completeness Check - Verifies all expected fletch-render content.js files were received
2. Creative Identification Check - Ensures creative was identified or static content detected
3. API Response Check - Validates API responses were captured (with diagnostic XHR/fetch info)
4. Blocking Rate Warning - Warns if >90% of requests were blocked (potential over-blocking)
5. Extraction Success Check - For fletch-render method, verifies videos were extracted

The validation function performs 5 key checks and returns detailed error and warning
reports. It's the final step in the scraping pipeline that determines overall
success/failure status.
"""

from typing import Dict, List, Tuple, Set, Optional, Any

from google_ads_config import (
    MAX_XHR_DISPLAY_COUNT,  # Limits XHR request display in diagnostics
    HIGH_BLOCKING_THRESHOLD  # Threshold for high blocking rate warning (0.9 = 90%)
)

# ============================================================================
# VALIDATION FUNCTION
# ============================================================================

def _validate_execution(
    expected_fletch_renders: Set[str],
    found_fletch_renders: Set[str],
    static_content_info: Optional[Dict[str, Any]],
    real_creative_id: Optional[str],
    critical_errors: List[str],
    tracker: 'TrafficTracker',
    all_xhr_fetch_requests: List[Dict[str, Any]],
    extraction_method: str,
    unique_videos: List[str],
    content_js_responses: List[Tuple[str, str]]
) -> Dict[str, Any]:
    """
    Validate scraping execution with detailed error and warning reporting.
    
    Performs comprehensive validation checks to determine if the scraping
    operation was successful. Checks include:
    1. Expected fletch-renders received?
    2. Creative identified or static content detected?
    3. API responses captured?
    4. High blocking rate warning
    5. Fletch-render method validation (videos extracted?)
    
    Args:
        expected_fletch_renders: Set of fletch-render IDs expected from API.
        found_fletch_renders: Set of fletch-render IDs actually received.
        static_content_info: Dictionary with static content info, or None.
        real_creative_id: 12-digit numeric creative ID, or None.
        critical_errors: List of error messages from wait phase.
        tracker: TrafficTracker instance with statistics.
        all_xhr_fetch_requests: List of XHR/fetch request metadata.
        extraction_method: Method used for extraction ('fletch-render', 'static-content', 'none').
        unique_videos: List of extracted YouTube video IDs.
        content_js_responses: List of captured content.js files.
    
    Returns:
        Dictionary containing:
            - 'execution_success': Boolean indicating overall success
            - 'execution_errors': List of error messages (failures)
            - 'execution_warnings': List of warning messages (non-critical issues)
    
    Example:
        result = _validate_execution(
            expected_fletch_renders={'13006300890096633430'},
            found_fletch_renders={'13006300890096633430'},
            static_content_info=None,
            real_creative_id='773510960098',
            critical_errors=[],
            tracker=tracker,
            all_xhr_fetch_requests=xhr_requests,
            extraction_method='fletch-render',
            unique_videos=['dQw4w9WgXcQ'],
            content_js_responses=content_responses
        )
        
        if result['execution_success']:
            print("✅ Scraping successful")
        else:
            print(f"❌ Scraping failed with {len(result['execution_errors'])} errors")
            for error in result['execution_errors']:
                print(f"  - {error}")
        
        if result['execution_warnings']:
            print(f"⚠️  {len(result['execution_warnings'])} warnings")
    
    Note:
        Validation logic:
        - Success: All expected content received, creative identified, no critical errors
        - Failure: Missing expected content, creative not identified, critical errors present
        - Warnings: Non-critical issues (no API, high blocking rate, no videos extracted)
    """
    print("\n" + "="*80)
    print("VALIDATION")
    print("="*80)
    
    execution_success = True
    execution_errors = list(critical_errors)  # Start with critical errors from wait phase
    execution_warnings = []
    
    # Check 1: Were all expected fletch-renders received?
    # If API provided expectations, verify all were captured
    # Partial or missing content indicates incomplete scraping
    if expected_fletch_renders:
        if len(found_fletch_renders) == len(expected_fletch_renders):
            print(f"✅ All expected content.js received ({len(found_fletch_renders)}/{len(expected_fletch_renders)})")
        elif len(found_fletch_renders) > 0:
            execution_success = False
            error_msg = f"INCOMPLETE: Only {len(found_fletch_renders)}/{len(expected_fletch_renders)} expected content.js received"
            if error_msg not in execution_errors:
                execution_errors.append(error_msg)
            print(f"❌ {error_msg}")
        else:
            execution_success = False
            error_msg = f"FAILED: Expected {len(expected_fletch_renders)} content.js but none received"
            if error_msg not in execution_errors:
                execution_errors.append(error_msg)
            print(f"❌ {error_msg}")
    
    # Check 2: Was creative identified or static content detected?
    # Need either a creative ID or static content info for success
    # If neither, we can't extract data or verify content
    if static_content_info:
        # Static content detected - this is a success case
        content_type = static_content_info.get('content_type', 'unknown')
        content_desc = 'image' if content_type == 'image' else 'HTML text' if content_type == 'html' else 'cached'
        print(f"✅ Static/cached content identified: {static_content_info['creative_id']}")
        execution_warnings.append(f"INFO: Static {content_desc} ad with no video/app content (creative ID: {static_content_info['creative_id']})")
    elif not real_creative_id and not found_fletch_renders:
        execution_success = False
        execution_errors.append("FAILED: Creative not found in API")
        print(f"❌ Creative not found in API")
    elif real_creative_id or found_fletch_renders:
        print(f"✅ Creative identification successful")
    
    # Check 3: Were API responses captured?
    # API responses are critical for identifying expected content
    # If missing, show diagnostic info (XHR/fetch requests)
    if len(tracker.api_responses) == 0:
        execution_warnings.append("WARNING: No API responses captured")
        print(f"⚠️  No API responses captured")
        
        # Diagnostic: Show what XHR/fetch requests were made
        if len(all_xhr_fetch_requests) > 0:
            print(f"   ℹ️  However, {len(all_xhr_fetch_requests)} XHR/fetch requests were detected:")
            for idx, req in enumerate(all_xhr_fetch_requests[:MAX_XHR_DISPLAY_COUNT], 1):  # Show first 5
                url_short = req['url'][:80] + '...' if len(req['url']) > 80 else req['url']
                print(f"      {idx}. [{req['status']}] {url_short}")
            if len(all_xhr_fetch_requests) > MAX_XHR_DISPLAY_COUNT:
                print(f"      ... and {len(all_xhr_fetch_requests) - MAX_XHR_DISPLAY_COUNT} more")
        else:
            print(f"   ℹ️  No XHR/fetch requests detected at all (JavaScript may not have executed)")
    else:
        print(f"✅ API responses captured ({len(tracker.api_responses)})")
    
    # Check 4: High blocking rate warning
    # If >90% of requests blocked, may indicate over-aggressive blocking
    # This is a warning, not an error (scraping may still succeed)
    if tracker.url_blocked_count > tracker.request_count * HIGH_BLOCKING_THRESHOLD:
        execution_warnings.append(f"WARNING: Very high blocking rate ({tracker.url_blocked_count}/{tracker.request_count})")
        print(f"⚠️  High blocking rate: {tracker.url_blocked_count}/{tracker.request_count}")
    
    # Check 5: Fletch-render method validation
    # If using fletch-render method, verify videos were extracted
    # No videos with content.js present indicates extraction failure
    if extraction_method == 'fletch-render':
        if len(unique_videos) == 0 and len(content_js_responses) > 0:
            execution_warnings.append("WARNING: Fletch-render method used but no videos found (may be non-video creative)")
            print(f"⚠️  No videos found despite having content.js (may be image/text ad)")
        else:
            print(f"✅ Extraction successful using fletch-render method")
    
    # Final verdict
    if execution_success and len(execution_errors) == 0:
        print(f"\n✅ EXECUTION SUCCESSFUL: Page scraped completely and correctly")
    elif len(execution_errors) > 0:
        execution_success = False
        print(f"\n❌ EXECUTION FAILED: {len(execution_errors)} error(s) detected")
        for err in execution_errors:
            print(f"   • {err}")
    
    if len(execution_warnings) > 0:
        print(f"\n⚠️  {len(execution_warnings)} warning(s):")
        for warn in execution_warnings:
            print(f"   • {warn}")
    
    return {
        'execution_success': execution_success,
        'execution_errors': execution_errors,
        'execution_warnings': execution_warnings
    }

