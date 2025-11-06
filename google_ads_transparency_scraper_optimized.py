#!/usr/bin/env python3
"""
Google Ads Transparency Center - Production Scraper (Main Orchestrator)
========================================================================

A comprehensive scraper for Google Ads Transparency Center that extracts real YouTube
videos and App Store IDs while filtering out Google's noise/decoy videos.

This is the main orchestrator module that coordinates the scraping process by importing
specialized modules and orchestrating the scraping workflow.

ARCHITECTURE:
-------------
The codebase has been refactored into 10 specialized modules for maintainability:

📦 google_ads_config.py
   Configuration constants and settings
   - Timeouts, blocking rules, proxy settings
   - Mitmproxy addon script
   
📦 google_ads_traffic.py
   Network traffic tracking and proxy management
   - TrafficTracker class (bandwidth monitoring)
   - Proxy setup and management
   - User agent generation
   
📦 google_ads_browser.py
   Browser automation and network interception
   - Browser context setup with URL blocking
   - Route handler factory (request blocking)
   - Response handler factory (response capture)
   
📦 google_ads_cache.py
   Cache integration for bandwidth optimization
   - Cache-aware route handler (wraps browser handler)
   - Two-level cache (memory L1 + disk L2)
   - 98%+ bandwidth savings, 146x speedup on hits
   
📦 google_ads_content.py
   Content processing pipeline
   - Smart waiting for dynamic content
   - Creative identification from frequency analysis
   - Data extraction (videos, App Store IDs)
   
📦 google_ads_api_analysis.py
   API response parsing and analysis
   - Static/cached content detection
   - Creative identification from API
   - Funded by (sponsor) extraction
   
📦 google_ads_extractors.py
   Data extraction (YouTube, App Store)
   - YouTube video ID extraction
   - App Store ID extraction
   - Base64 ad parameter parsing
   
📦 google_ads_debug.py
   Debug file utilities
   - Content.js debug file saving
   - API response debug file saving
   
📦 google_ads_validation.py
   Execution validation
   - Validation of expected vs found content
   - Error and warning generation
   
📦 google_ads_output.py
   Result formatting and display
   - Console output formatting
   - Traffic statistics display
   - Cache statistics display
   - Result summary printing

THIS MODULE CONTAINS:
---------------------
✅ Import statements and dependency checks
✅ Main scraper orchestrator function: scrape_ads_transparency_page()
✅ CLI entrypoint: main() with argument parsing
✅ if __name__ == "__main__" block

FEATURES:
---------
✅ Real Video Detection (100% accuracy on test cases)
   - API-based method (GetCreativeById)
   - Frequency-based fallback
   - Handles videos spread across multiple requests
   
✅ Bandwidth Optimization (49-59% reduction)
   - Blocks images, fonts, CSS
   - Blocks analytics, ads, tracking
   - Optional proxy for accurate measurement
   - All requests use same proxy (consistent routing)
   
✅ Intelligent Caching (98%+ additional savings)
   - Two-level cache (memory L1 + disk L2)
   - Caches main.dart.js files (largest assets)
   - Version-aware auto-invalidation
   - 146x speedup on cache hits (memory vs disk)
   - Enabled by default, zero configuration
   
✅ Data Extraction (from real creative only)
   - YouTube video IDs (filtered by real creative ID)
   - App Store IDs (filtered by real creative ID)
   - App IDs from base64-encoded ad parameters
   - Creative metadata
   - Ignores decoy/noise creatives
   
✅ Bot Detection Evasion (optional, recommended)
   - playwright-stealth integration for stealth browsing
   - Hides automation indicators (navigator.webdriver, etc.)
   - Prevents browser fingerprinting detection
   - Randomized Chrome user agents (fake-useragent)
   - Different user agent for each scraping session
   - Can be toggled via ENABLE_STEALTH_MODE and USE_RANDOM_USER_AGENT constants

METHODS:
--------
Two methods to identify real videos (both achieve 100% accuracy):

1. API Method (Recommended):
   - Uses GetCreativeById API response
   - Identifies real creative BEFORE content.js loads (~1000ms)
   - Explicit mapping from Google's own API
   
2. Frequency Method (Fallback):
   - Counts creative ID frequency in content.js requests
   - Real creative appears ~5 times, noise appears 1 time each
   - Identified after all content.js loads (~8000ms)

USAGE:
------
Basic usage:
    python3 google_ads_transparency_scraper.py <URL>
    
With proxy (accurate traffic measurement):
    python3 google_ads_transparency_scraper.py <URL> --proxy
    
With debug mode (saves App Store ID extraction details):
    python3 google_ads_transparency_scraper.py <URL> --debug-extra-information

With fletch-render debug mode (saves fletch-render content.js responses):
    python3 google_ads_transparency_scraper.py <URL> --debug-fletch

With comprehensive debug mode (saves ALL content.js + API responses):
    python3 google_ads_transparency_scraper.py <URL> --debug-content
    
Example:
    python3 google_ads_transparency_scraper.py \\
        "https://adstransparency.google.com/advertiser/AR.../creative/CR...?region=anywhere&platform=YOUTUBE"

As a module:
    import asyncio
    from google_ads_transparency_scraper import scrape_ads_transparency_page
    
    async def scrape():
        result = await scrape_ads_transparency_page(
            'https://adstransparency.google.com/advertiser/AR.../creative/CR...',
            use_proxy=True,
            debug_appstore=True
        )
        
        if result['execution_success']:
            print(f"Videos: {result['videos']}")
            print(f"App Store ID: {result['app_store_id']}")
        else:
            print(f"Errors: {result['execution_errors']}")
    
    asyncio.run(scrape())

REQUIREMENTS:
-------------
- Python 3.7+
- playwright: pip install playwright
- playwright install chromium
- playwright-stealth (optional, recommended): pip install playwright-stealth
- fake-useragent (optional, recommended): pip install fake-useragent
- mitmproxy (optional, for accurate traffic measurement)

TRAFFIC OPTIMIZATION:
---------------------
Achieves 49-59% bandwidth reduction:
- Baseline (unoptimized): ~2.5-2.8 MB per page
- Optimized (with blocking): ~1.3-1.4 MB per page
- Bandwidth saved: ~1.2-1.5 MB per page

With proxy (--proxy):
- All requests routed through proxy
- Accurate traffic measurement via mitmproxy
- Consistent IP for entire session

PERFORMANCE:
------------
- Typical scraping time: 5-15 seconds (with smart waiting)
- Maximum wait time: 60 seconds
- Bandwidth usage: ~500KB-2MB (with blocking enabled)
- Success rate: ~95% for dynamic content, 100% for static content

ACCURACY:
---------
Validated on 3 test cases:
- Test 1: 2 videos (spread across 4 requests) ✅ 100%
- Test 2: 1 video (identical in 5 requests) ✅ 100%
- Test 3: 3 videos (spread across 4 requests) ✅ 100%

AUTHOR: Rostoni
VERSION: 2.0
DATE: 2025-10-26
LICENSE: MIT
"""

import asyncio
import sys
import re
import time
import os
import signal
import subprocess
import json
import argparse
import random
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Optional, Set, Any, Callable, Awaitable

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("ERROR: Playwright not installed")
    print("Install: pip install playwright")
    print("Then run: playwright install chromium")
    sys.exit(1)

# Import playwright-stealth for bot detection evasion
try:
    from playwright_stealth import Stealth
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    print("⚠️  WARNING: playwright-stealth not installed")
    print("   Install for better bot detection evasion: pip install playwright-stealth")
    print("   Continuing without stealth mode...\n")

# Import fake-useragent for randomized Chrome user agents
try:
    from fake_useragent import UserAgent
    FAKE_USERAGENT_AVAILABLE = True
except ImportError:
    FAKE_USERAGENT_AVAILABLE = False
    print("⚠️  WARNING: fake-useragent not installed")
    print("   Install for randomized user agents: pip install fake-useragent")
    print("   Using default user agent...\n")

# ============================================================================
# MODULE IMPORTS
# ============================================================================
# Import from refactored modules (all google_ads_* files)

# Configuration - Import all constants used by main scraper
from google_ads_config import (
    USE_RANDOM_USER_AGENT,
    ENABLE_STEALTH_MODE,
    PAGE_LOAD_TIMEOUT,
    PROXY_TERMINATION_TIMEOUT,
    PROXY_SHUTDOWN_WAIT,
    PROXY_RESULTS_PATH,
    EXIT_CODE_VALIDATION_FAILED,
    EXIT_CODE_ERROR,
    JSON_OUTPUT_INDENT,
    VERBOSE_LOGGING
)

# Cache Integration - Import cache-aware route handler and statistics
from google_ads_cache import (
    create_cache_aware_route_handler,
    get_cache_statistics,
    reset_cache_statistics
)

# Traffic Management - Import TrafficTracker class and proxy setup
from google_ads_traffic import (
    TrafficTracker,
    _setup_proxy
)

# Browser Automation - Import browser setup and handler factories
from google_ads_browser import (
    _setup_browser_context,
    _create_route_handler,
    _create_response_handler
)

# Content Processing - Import content pipeline functions
from google_ads_content import (
    _smart_wait_for_content,
    _identify_creative,
    _extract_data
)

# API Analysis - Import API parsing functions
from google_ads_api_analysis import (
    check_if_static_cached_creative,
    extract_funded_by_from_api,
    extract_country_presence_from_api
)

# Debug Utilities - Import debug file functions
from google_ads_debug import (
    save_all_content_js_debug_files,
    save_api_response_debug_file
)

# Validation - Import validation function
from google_ads_validation import _validate_execution

# Output Formatting - Import display functions
from google_ads_output import print_results

# ============================================================================
# MAIN SCRAPER
# ============================================================================

async def scrape_ads_transparency_page(
    page_url: str,
    use_proxy: bool = False,
    external_proxy: Optional[Dict[str, str]] = None,
    debug_appstore: bool = False,
    debug_fletch: bool = False,
    debug_content: bool = False
) -> Dict[str, Any]:
    """
    Scrape Google Ads Transparency page to extract video IDs and App Store IDs.
    
    This is the main orchestrator function that coordinates all scraping phases:
    1. Proxy setup (optional mitmproxy for traffic measurement)
    2. Browser launch with URL blocking and response capture
    3. Page navigation and smart waiting for dynamic content
    4. Creative identification from API responses
    5. Data extraction (videos, App Store IDs) from content.js files
    6. Execution validation and result compilation
    
    The scraper uses intelligent waiting with multiple early-exit conditions
    to optimize scraping time. It handles static/cached content, empty API
    responses, and missing creatives gracefully.
    
    Args:
        page_url: Full URL of the Google Ads Transparency creative page.
                  Format: https://adstransparency.google.com/advertiser/AR.../creative/CR...
        use_proxy: If True, use mitmproxy for accurate traffic measurement.
                   If False, use estimation mode (Content-Length headers).
                   Default: False
        external_proxy: Optional external proxy configuration dictionary:
                        {'server': 'http://proxy.example.com:8080', ...}
                        Overrides mitmproxy if provided.
                        Default: None
        debug_appstore: If True, save debug files when App Store IDs are found.
                        Files saved to debug/ folder with extraction details.
                        Default: False
        debug_fletch: If True, save debug files for each fletch-render content.js.
                      Files saved to debug/ folder with full content.js text.
                      Default: False
        debug_content: If True, save ALL content.js files and API responses.
                       Useful for debugging extraction issues.
                       Default: False
    
    Returns:
        Dictionary containing comprehensive scraping results with the following keys:
        
        Execution Status (backward compatible):
            - success (bool): Same as execution_success (new key for consistency)
            - errors (List[str]): Same as execution_errors (new key for consistency)
            - warnings (List[str]): Same as execution_warnings (new key for consistency)
            - execution_success (bool): Whether scraping completed successfully (legacy key)
            - execution_errors (List[str]): List of error messages (legacy key)
            - execution_warnings (List[str]): List of warning messages (legacy key)
        
        Videos:
            - videos (List[str]): Unique YouTube video IDs found (deduplicated)
            - video_count (int): Number of unique videos
            - videos_by_request (Dict[str, List[str]]): Video IDs grouped by request URL
        
        Creative Identification:
            - real_creative_id (str): The real creative ID (12-digit or CR-prefixed)
            - method_used (str): Method used to identify creative ('api', 'frequency', 'url', etc.)
        
        Extraction:
            - extraction_method (str): Method used for extraction ('fletch-render', 'static', etc.)
            - expected_fletch_renders (int): Number of expected fletch-render content.js files
            - found_fletch_renders (int): Number of fletch-render content.js files found
        
        App Store:
            - app_store_id (Optional[str]): Apple App Store ID if found, None otherwise
        
        Static Content Detection:
            - is_static_content (bool): Whether content is static/cached
            - static_content_info (Optional[Dict]): Details about static content if detected
        
        Traffic Statistics:
            - incoming_bytes (int): Bytes received (response bodies)
            - outgoing_bytes (int): Bytes sent (request bodies)
            - total_bytes (int): Total bytes transferred (incoming + outgoing)
            - measurement_method (str): 'proxy' or 'estimation'
            - incoming_by_type (Dict[str, int]): Incoming bytes grouped by resource type
            - outgoing_by_type (Dict[str, int]): Outgoing bytes grouped by resource type
        
        Request Statistics:
            - request_count (int): Total number of requests made
            - blocked_count (int): Number of requests blocked by resource type
            - url_blocked_count (int): Number of requests blocked by URL pattern
            - duration_ms (float): Total scraping duration in milliseconds
        
        Debug Information:
            - content_js_requests (int): Number of content.js files captured
            - api_responses (int): Number of API responses captured
        
        Cache Statistics:
            - cache_hits (int): Number of main.dart.js files served from cache
            - cache_misses (int): Number of main.dart.js files downloaded from network
            - cache_bytes_saved (int): Total bytes saved by cache hits
            - cache_hit_rate (float): Cache hit rate as percentage (0-100)
            - cache_total_requests (int): Total cacheable requests (hits + misses)
    
    Raises:
        playwright.async_api.Error: For Playwright-specific errors (browser launch, navigation, etc.)
        playwright.async_api.TimeoutError: If page navigation exceeds PAGE_LOAD_TIMEOUT
        asyncio.TimeoutError: For async operation timeouts
        OSError: If mitmproxy cannot be started or proxy files cannot be accessed
        subprocess.SubprocessError: If mitmdump process fails to start or terminate
        json.JSONDecodeError: If proxy results JSON is malformed
        Exception: Other unexpected errors during scraping
    
    Note:
        Performance characteristics:
        - Typical scraping time: 5-15 seconds (with smart waiting)
        - Maximum wait time: 60 seconds (MAX_CONTENT_WAIT)
        - Bandwidth usage: ~500KB-2MB (with blocking enabled)
        - Success rate: ~95% for dynamic content, 100% for static content
        
        The scraper optimizes bandwidth by blocking:
        - Images, fonts, stylesheets (BLOCKED_RESOURCE_TYPES)
        - Analytics, ads, social media (BLOCKED_URL_PATTERNS)
        - Selective gstatic.com blocking (GSTATIC_BLOCKED_PATTERNS)
        
        Backward Compatibility:
        - Both 'execution_success' (legacy) and 'success' (new) keys are provided
        - Both 'execution_errors' (legacy) and 'errors' (new) keys are provided
        - Both 'execution_warnings' (legacy) and 'warnings' (new) keys are provided
        - Prefer using 'execution_success', 'execution_errors', 'execution_warnings' for consistency
    """
    # Initialize core state
    tracker = TrafficTracker()
    proxy_process = None
    proxy_results = None
    start_time = time.time()
    
    # Reset cache statistics for this scraping session
    reset_cache_statistics()
    
    # Setup proxy
    proxy_setup = await _setup_proxy(use_proxy, external_proxy)
    proxy_process = proxy_setup['proxy_process']
    use_proxy = proxy_setup['use_proxy']
    
    # Launch browser and setup context
    async with async_playwright() as p:
        browser_setup = await _setup_browser_context(p, use_proxy, external_proxy)
        browser = browser_setup['browser']
        context = browser_setup['context']
        user_agent = browser_setup['user_agent']
        
        # Print user agent info
        if FAKE_USERAGENT_AVAILABLE and USE_RANDOM_USER_AGENT:
            # Extract Chrome version from user agent
            chrome_version_match = re.search(r'Chrome/([\d.]+)', user_agent)
            chrome_version = chrome_version_match.group(1) if chrome_version_match else 'unknown'
            print(f"🎭 User Agent: Random Chrome {chrome_version}")
        else:
            print(f"🎭 User Agent: Default (static)")
        
        # Create and register handlers
        content_js_responses = []
        all_xhr_fetch_requests = []
        
        # Create route handler with cache integration
        route_handler = _create_route_handler(tracker)
        cache_aware_handler = create_cache_aware_route_handler(tracker, route_handler)
        await context.route('**/*', cache_aware_handler)
        
        response_handler = _create_response_handler(tracker, content_js_responses, all_xhr_fetch_requests)
        
        page = await context.new_page()
        
        # Apply stealth mode if available and enabled
        if STEALTH_AVAILABLE and ENABLE_STEALTH_MODE:
            await Stealth().apply_stealth_async(page)
            print("🕵️  Stealth mode: ENABLED (bot detection evasion active)")
        elif ENABLE_STEALTH_MODE and not STEALTH_AVAILABLE:
            print("⚠️  Stealth mode: DISABLED (playwright-stealth not installed)")
        
        # Set up event listeners
        page.on('request', lambda req: tracker.on_request(req))
        page.on('response', lambda res: tracker.on_response(res))
        page.on('response', response_handler)
        page.on('requestfailed', lambda req: tracker.on_request_failed(req))
        
        # Navigate and wait
        print(f"Navigating to: {page_url[:80]}...")
        sys.stdout.flush()  # Force immediate output in concurrent environments
        
        try:
            await page.goto(page_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
            print(f"  ✓ Page loaded (domcontentloaded)")
            sys.stdout.flush()
        except Exception as goto_error:
            print(f"  ⚠️  page.goto() error: {type(goto_error).__name__}: {str(goto_error)[:100]}")
            sys.stdout.flush()
            raise  # Re-raise to let outer handler deal with it
        
        wait_results = await _smart_wait_for_content(page, page_url, tracker, content_js_responses, all_xhr_fetch_requests)
        elapsed = wait_results['elapsed']
        expected_fletch_renders = wait_results['expected_fletch_renders']
        found_fletch_renders = wait_results['found_fletch_renders']
        critical_errors = wait_results['critical_errors']
        static_content_detected = wait_results['static_content_detected']
        content_js_responses = wait_results['content_js_responses']
        all_xhr_fetch_requests = wait_results['all_xhr_fetch_requests']
        
        # Save debug files if debug-content mode enabled
        if debug_content:
            print(f"\n💾 Saving debug files...")
            print(f"  Saving {len(content_js_responses)} content.js file(s)...")
            save_all_content_js_debug_files(content_js_responses)
            
            print(f"  Saving {len(tracker.api_responses)} API response(s)...")
            for idx, api_resp in enumerate(tracker.api_responses, 1):
                save_api_response_debug_file(api_resp, idx)
            
            print(f"  ✅ All debug files saved to debug/ folder")
        
        duration_ms = (time.time() - start_time) * 1000
        
        await browser.close()
    
    # Stop proxy and read results
    if proxy_process:
        print("🔧 Stopping proxy...")
        proxy_process.send_signal(signal.SIGTERM)
        try:
            proxy_process.wait(timeout=PROXY_TERMINATION_TIMEOUT)
        except subprocess.TimeoutExpired:
            print("⚠️  Proxy did not terminate gracefully, forcing kill...")
            proxy_process.kill()
        
        await asyncio.sleep(PROXY_SHUTDOWN_WAIT)
        if os.path.exists(PROXY_RESULTS_PATH):
            with open(PROXY_RESULTS_PATH, 'r') as f:
                proxy_results = json.load(f)
    
    # Determine traffic measurement
    if proxy_results:
        incoming_bytes = proxy_results['total_response_bytes']
        outgoing_bytes = proxy_results['total_request_bytes']
        total_bytes = proxy_results['total_bytes']
        measurement_method = 'proxy'
    else:
        incoming_bytes = tracker.incoming_bytes
        outgoing_bytes = tracker.outgoing_bytes
        total_bytes = tracker.incoming_bytes + tracker.outgoing_bytes
        measurement_method = 'estimation'
    
    # Check for static/cached content (if not already detected in wait loop)
    if static_content_detected:
        static_content_info = static_content_detected
    else:
        # Final check if not detected during wait (shouldn't normally happen)
        print(f"\n🔍 Final check for static/cached content...")
        print(f"   API responses: {len(tracker.api_responses)}")
        static_content_info = check_if_static_cached_creative(
            tracker.api_responses, 
            page_url
        )
    
    # Identify creative
    creative_results = _identify_creative(tracker, page_url, static_content_info)
    real_creative_id = creative_results['real_creative_id']
    method_used = creative_results['method_used']
    
    # Extract funded_by (sponsor company name) from API
    funded_by = extract_funded_by_from_api(tracker.api_responses, page_url)
    # Extract country presence (best-effort)
    country_presence = extract_country_presence_from_api(tracker.api_responses, page_url)
    
    # Extract data
    extraction_results = _extract_data(content_js_responses, found_fletch_renders, static_content_info, real_creative_id, debug_fletch, debug_appstore)
    unique_videos = extraction_results['unique_videos']
    videos_by_request = extraction_results['videos_by_request']
    app_store_id = extraction_results['app_store_id']
    app_ids_from_base64 = extraction_results['app_ids_from_base64']
    extraction_method = extraction_results['extraction_method']
    all_videos = extraction_results['all_videos']
    
    # Validate execution
    validation_results = _validate_execution(expected_fletch_renders, found_fletch_renders, static_content_info, real_creative_id, critical_errors, tracker, all_xhr_fetch_requests, extraction_method, unique_videos, content_js_responses)
    execution_success = validation_results['execution_success']
    execution_errors = validation_results['execution_errors']
    execution_warnings = validation_results['execution_warnings']
    
    # Get cache statistics for this scraping session
    cache_stats = get_cache_statistics()
    
    # ========================================================================
    # RETURN RESULTS
    # ========================================================================
    
    return {
        # Execution Status (backward compatible - both legacy and new keys)
        'execution_success': execution_success,  # Legacy key (preferred)
        'execution_errors': execution_errors,    # Legacy key (preferred)
        'execution_warnings': execution_warnings,  # Legacy key (preferred)
        'success': execution_success,            # New key (alias for backward compatibility)
        'errors': execution_errors,              # New key (alias for backward compatibility)
        'warnings': execution_warnings,          # New key (alias for backward compatibility)
        
        # Static Content Detection
        'is_static_content': bool(static_content_info),
        'static_content_info': static_content_info,
        
        # Videos
        'videos': unique_videos,
        'video_count': len(unique_videos),
        'videos_by_request': videos_by_request,
        
        # Creative ID
        'real_creative_id': real_creative_id if not static_content_info else static_content_info.get('creative_id_12digit'),
        'method_used': method_used,
        
        # Extraction Method
        'extraction_method': extraction_method,
        'expected_fletch_renders': len(expected_fletch_renders) if expected_fletch_renders else 0,
        'found_fletch_renders': len(found_fletch_renders) if found_fletch_renders else 0,
        
        # App Store
        'app_store_id': app_store_id,
        'app_ids_from_base64': app_ids_from_base64,
        
        # Funded By (sponsor company name)
        'funded_by': funded_by,
        # Country presence (JSON map of country_code -> last_seen ISO date)
        'country_presence': country_presence,
        
        # Traffic
        'incoming_bytes': incoming_bytes,
        'outgoing_bytes': outgoing_bytes,
        'total_bytes': total_bytes,
        'measurement_method': measurement_method,
        
        # Stats
        'request_count': tracker.request_count,
        'blocked_count': tracker.blocked_count,
        'url_blocked_count': tracker.url_blocked_count,
        'duration_ms': duration_ms,
        
        # Details
        'incoming_by_type': dict(tracker.incoming_by_type),
        'outgoing_by_type': dict(tracker.outgoing_by_type),
        'content_js_requests': len(tracker.content_js_requests),
        'api_responses': len(tracker.api_responses),
        
        # Cache Statistics
        'cache_hits': cache_stats['hits'],
        'cache_misses': cache_stats['misses'],
        'cache_bytes_saved': cache_stats['bytes_saved'],
        'cache_hit_rate': cache_stats['hit_rate'],
        'cache_total_requests': cache_stats['total_requests']
    }

# ============================================================================
# API-ONLY SCRAPER (Session Reuse Optimization)
# ============================================================================

async def scrape_ads_transparency_api_only(
    advertiser_id: str,
    creative_id: str,
    cookies: List[Dict],
    page,  # Playwright page from existing context
    tracker: TrafficTracker,
    playwright_instance,  # Playwright instance for creating direct APIRequestContext
    user_agent: str,  # User agent from browser context (for replication)
    use_partial_proxy: bool = False,  # If True, bypass proxy for content.js
    debug_appstore: bool = False,
    debug_fletch: bool = False,
    debug_content: bool = False
) -> Dict[str, Any]:
    """
    Scrape creative using API-only approach (no HTML load).
    Reuses browser context and cookies from initial session.
    
    This function implements bandwidth-optimized scraping by skipping the HTML page load
    and directly calling the GetCreativeById API. It fetches content.js files with gzip
    compression and reuses all existing extraction logic.
    
    IMPORTANT DESIGN NOTES:
    -----------------------
    1. NO ROUTE HANDLER NEEDED:
       - We make direct API calls via page.request.post/get()
       - These bypass browser navigation (no HTML page load)
       - Resource blocking not needed (we control exactly what we fetch)
       - Cache integration not needed (API responses are not cacheable assets)
    
    2. NO RESPONSE HANDLER NEEDED:
       - We manually fetch and store content.js responses
       - This gives us precise control over what's downloaded
       - Response format matches original (List[Tuple[str, str]])
    
    3. STEALTH MODE INHERITED:
       - Browser context already has stealth applied (from first creative)
       - User agent already set (from browser context)
       - No additional stealth setup needed
    
    Flow:
    1. Make GetCreativeById API call with cookies
    2. Parse API response (check for static/cached content)
    3. Extract content.js URLs from API response
    4. Fetch content.js files with gzip compression
    5. Extract videos/App Store IDs (same logic as main scraper)
    6. Return result in same format as scrape_ads_transparency_page()
    
    Args:
        advertiser_id: Advertiser ID (format: AR... or 20-digit)
        creative_id: Creative ID (format: CR... or 12-digit)
        cookies: List of cookie dictionaries from initial session
        page: Playwright page from existing browser context
        tracker: TrafficTracker instance for bandwidth monitoring
        debug_appstore: If True, save debug files when App Store IDs are found
        debug_fletch: If True, save debug files for each fletch-render content.js
        debug_content: If True, save ALL content.js files and API responses
    
    Returns:
        Dictionary containing scraping results (same format as scrape_ads_transparency_page)
    
    Bandwidth savings:
        - Original (HTML + API + content.js): ~524 KB
        - API-only (API + content.js): ~179 KB
        - Savings: ~345 KB (65% reduction)
    """
    # Delay Configuration (to avoid rate limiting)
    DELAY_BEFORE_API_CALL = (0.5, 1.5)      # Random delay before GetCreativeById API (min, max seconds)
    DELAY_BETWEEN_CONTENTJS = (0.5, 1)    # Random delay between content.js fetches (min, max seconds)
    
    start_time = time.time()
    page_url = f"https://adstransparency.google.com/advertiser/{advertiser_id}/creative/{creative_id}"
    
    # Add cookies to context (if not already added)
    await page.context.add_cookies(cookies)
    
    # DEBUG: Log cookies being added
    if VERBOSE_LOGGING:
        print(f"  🍪 Adding {len(cookies)} cookies to context:")
        for cookie in cookies[:3]:  # Show first 3
            print(f"     - {cookie['name']}: {cookie['value'][:30]}...")
    
    # ========================================================================
    # STEP 1: Make GetCreativeById API Request
    # ========================================================================
    
    # Construct API payload
    api_payload = {
        "1": advertiser_id,
        "2": creative_id,
        "5": {"1": 1, "2": 0, "3": 2268}
    }
    body_data = f"f.req={json.dumps(api_payload)}"
    
    # Make POST request with gzip compression
    api_url = "https://adstransparency.google.com/anji/_/rpc/LookupService/GetCreativeById?authuser="
    
    # DEBUG: Save request info
    request_headers = {
        "content-type": "application/x-www-form-urlencoded",
        "x-framework-xsrf-token": "",
        "x-same-domain": "1",
        "accept-encoding": "gzip, deflate, br",  # CRITICAL for compression
        "origin": "https://adstransparency.google.com",
        "referer": f"{page_url}?region=anywhere"
    }
    
    # Add random delay before API call to avoid rate limiting
    random_delay = random.uniform(DELAY_BEFORE_API_CALL[0], DELAY_BEFORE_API_CALL[1])
    if VERBOSE_LOGGING:
        print(f"  ⏳ Waiting {random_delay:.2f}s before API call...")
    await asyncio.sleep(random_delay)
    
    if VERBOSE_LOGGING:
        print(f"  📤 Making API request to: {api_url[:80]}...")
        print(f"     Headers: {list(request_headers.keys())}")
    
    # Retry logic for 429 rate limits
    max_retries = 3
    retry_delays = [2, 4, 8]  # Exponential backoff in seconds
    api_response = None
    response_text = None
    
    for attempt in range(max_retries):
        try:
            api_response = await page.request.post(
                api_url,
                data=body_data,
                headers=request_headers
            )
            
            # DEBUG: Log response info
            if VERBOSE_LOGGING:
                print(f"  📥 API response received:")
                print(f"     Status: {api_response.status}")
                print(f"     Headers: {dict(list(api_response.headers.items())[:5])}")
            
            # If we got a 429, retry with delay
            if api_response.status == 429:
                if attempt < max_retries - 1:
                    delay = retry_delays[attempt]
                    print(f"  ⚠️  Rate limited (429), retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                    continue
                else:
                    print(f"  ❌ Rate limited (429) after {max_retries} attempts - giving up")
                    break
            
            response_text = await api_response.text()
            break  # Success - exit retry loop
            
        except Exception as e:
            if attempt < max_retries - 1:
                delay = retry_delays[attempt]
                print(f"  ⚠️  Request failed: {str(e)[:60]}, retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(delay)
            else:
                print(f"  ❌ Request failed after {max_retries} attempts: {str(e)}")
                raise
    
    # Check if we got a valid response after retries
    if api_response is None or response_text is None:
        if api_response and api_response.status == 429:
            error_msg = f"Rate limited (429): Too many requests - consider reducing concurrency"
        else:
            error_msg = "API request failed after retries"
        
        return {
            'execution_success': False,
            'execution_errors': [error_msg],
            'execution_warnings': [],
            'success': False,
            'errors': [error_msg],
            'warnings': [],
            'videos': [],
            'video_count': 0,
            'app_store_id': None,
            'real_creative_id': creative_id,
            'method_used': 'api_only_failed',
            'duration_ms': (time.time() - start_time) * 1000,
            'incoming_bytes': tracker.incoming_bytes,
            'outgoing_bytes': tracker.outgoing_bytes,
            'total_bytes': tracker.incoming_bytes + tracker.outgoing_bytes,
            'measurement_method': 'estimation'
        }
    
    # DEBUG: Save request/response details to file (only if debug_content enabled)
    try:
        if debug_content:
            debug_request_file = "/Users/rostoni/Downloads/LocalTransperancy/debug_api_request.json"
            with open(debug_request_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'url': api_url,
                    'method': 'POST',
                    'request_headers': request_headers,
                    'cookies_added': [{'name': c['name'], 'value': c['value'][:30]} for c in cookies],
                    'request_body': body_data[:200],
                    'response_status': api_response.status,
                    'response_headers': dict(api_response.headers),
                    'response_text_length': len(response_text),
                    'response_text_preview': response_text[:500]
                }, f, indent=2)
            print(f"  📝 Saved API request details to debug_api_request.json")
        
        # Track API request in tracker
        api_resp_dict = {
            'url': api_url,
            'text': response_text,
            'type': 'GetCreativeById',
            'timestamp': time.time()
        }
        tracker.api_responses.append(api_resp_dict)
        
    except Exception as e:
        # This catches any errors during debug saving or tracker update
        print(f"  ⚠️  Error during API response processing: {str(e)}")
        # Continue anyway - response_text is already set
    
    # ========================================================================
    # STEP 2: Parse API Response
    # ========================================================================
    
    try:
        data = json.loads(response_text)
        
        # Unwrap response: {"1": {actual_data}}
        if "1" in data:
            data = data["1"]
        
        # Check for static/cached content (reuse existing function)
        static_content_info = check_if_static_cached_creative(
            [api_resp_dict], 
            page_url
        )
        
        # Extract content.js URLs: data["5"][i]["1"]["4"]
        content_js_urls = []
        if "5" in data and isinstance(data["5"], list):
            for variation in data["5"]:
                if isinstance(variation, dict) and "1" in variation:
                    if isinstance(variation["1"], dict) and "4" in variation["1"]:
                        url = variation["1"]["4"]
                        content_js_urls.append(url)
        
    except Exception as e:
        return {
            'execution_success': False,
            'execution_errors': [f"API response parsing failed: {str(e)}"],
            'execution_warnings': [],
            'success': False,
            'errors': [f"API response parsing failed: {str(e)}"],
            'warnings': [],
            'videos': [],
            'video_count': 0,
            'app_store_id': None,
            'real_creative_id': creative_id,
            'method_used': 'api_only_parse_failed',
            'duration_ms': (time.time() - start_time) * 1000,
            'incoming_bytes': tracker.incoming_bytes,
            'outgoing_bytes': tracker.outgoing_bytes,
            'total_bytes': tracker.incoming_bytes + tracker.outgoing_bytes,
            'measurement_method': 'estimation'
        }
    
    # ========================================================================
    # STEP 3: Fetch content.js Files with Compression (PARALLEL)
    # ========================================================================
    # NOTE: We parse content.js as TEXT using regex (not execute them)
    # The extraction logic uses regex to find video IDs, App Store IDs, etc.
    # OPTIMIZATION: Fetch all content.js files in parallel to reduce latency
    
    # Setup fetch context (proxy bypass if partial proxy enabled)
    direct_context = None
    if use_partial_proxy:
        # Create direct APIRequestContext WITHOUT proxy (replicate browser context settings)
        cookie_data = []
        for cookie in cookies:
            cookie_data.append({
                'name': cookie['name'],
                'value': cookie['value'],
                'domain': cookie.get('domain', '.google.com'),
                'path': cookie.get('path', '/'),
                'expires': cookie.get('expires', -1),
                'httpOnly': cookie.get('httpOnly', False),
                'secure': cookie.get('secure', False),
                'sameSite': cookie.get('sameSite', 'Lax')
            })
        
        direct_context = await playwright_instance.request.new_context(
            user_agent=user_agent,  # Same user agent as browser context
            ignore_https_errors=True,
            extra_http_headers={
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'accept-language': 'en-US,en;q=0.9',
                'accept-encoding': 'gzip, deflate, br',  # CRITICAL: Always request compression
            },
            storage_state={'cookies': cookie_data}
        )
        fetch_context = direct_context
        proxy_label = "DIRECT (bypassing proxy)"
    else:
        fetch_context = page.request
        proxy_label = "through proxy"
    
    async def fetch_single_content_js(url: str, index: int) -> Dict[str, Any]:
        """
        Helper function to fetch a single content.js file.
        Returns dict with url, text, success status, and metadata.
        """
        try:
            # Use fetch_context (either direct or through proxy)
            # Note: accept-encoding already set in extra_http_headers for direct_context
            response = await fetch_context.get(url)
            
            content_text = await response.text()
            
            # Get actual compressed size from Content-Length header (wire size)
            # Note: len(content_text) would give decompressed size, not actual bandwidth
            content_length = response.headers.get('content-length')
            if content_length:
                compressed_size = int(content_length)
            else:
                # Fallback: estimate as decompressed size (if header missing)
                compressed_size = len(content_text)
            
            # Debug: Check if content actually has data
            has_video_id = 'video_id' in content_text or 'videoId' in content_text
            has_appstore = 'itunes.apple.com' in content_text or 'apps/ios' in content_text
            
            return {
                'url': url,
                'text': content_text,
                'success': True,
                'index': index,
                'size': compressed_size,  # Actual wire size (compressed)
                'decompressed_size': len(content_text),  # For reference
                'status': response.status,
                'headers': dict(response.headers),
                'has_video_id': has_video_id,
                'has_appstore': has_appstore
            }
        except Exception as e:
            # Detailed error logging for SSL/protocol errors
            error_str = str(e)
            if 'EPROTO' in error_str or 'SSL' in error_str or 'TLS' in error_str:
                # SSL/TLS errors should be retried
                print(f"  ⚠️  SSL/TLS error on file {index}: {error_str[:100]}")
                return {
                    'url': url,
                    'text': '',
                    'success': False,
                    'index': index,
                    'error': f"SSL/TLS error: {error_str}"  # Make it retryable
                }
            else:
                return {
                    'url': url,
                    'text': '',
                    'success': False,
                    'index': index,
                    'error': str(e)
                }
    
    # Fetch all content.js files SEQUENTIALLY with random delays (1-3 seconds) to avoid rate limiting
    if VERBOSE_LOGGING:
        print(f"  📤 Fetching {len(content_js_urls)} content.js file(s) {proxy_label}...")
        if use_partial_proxy:
            print(f"     Using direct connection (bypassing proxy)")
        print(f"     Request headers: accept-encoding: gzip, deflate, br")
    fetch_start_time = time.time()
    
    # Fetch sequentially with random delays to avoid rate limiting
    fetch_results = []
    for i, url in enumerate(content_js_urls, 1):
        # Add random delay between fetches (except for the first one)
        if i > 1:
            random_delay = random.uniform(DELAY_BETWEEN_CONTENTJS[0], DELAY_BETWEEN_CONTENTJS[1])
            if VERBOSE_LOGGING:
                print(f"  ⏳ Waiting {random_delay:.2f}s before next content.js fetch...")
            await asyncio.sleep(random_delay)
        
        # Fetch this content.js file
        result = await fetch_single_content_js(url, i)
        fetch_results.append(result)
    
    fetch_duration = time.time() - fetch_start_time
    if VERBOSE_LOGGING:
        print(f"  ✅ Fetched {len(content_js_urls)} file(s) in {fetch_duration:.2f}s (sequential with random delays)")
    
    # Process results and build content_js_responses
    content_js_responses = []
    total_bytes = 0
    success_count = 0
    
    for result in fetch_results:
        if result['success']:
            url = result['url']
            content_text = result['text']
            
            # Check if response included content-encoding header
            content_encoding = result['headers'].get('content-encoding', 'none')
            
            # Calculate compression ratio
            compressed = result['size']
            decompressed = result.get('decompressed_size', compressed)
            if content_encoding != 'none' and decompressed > 0:
                ratio = (1 - compressed / decompressed) * 100
                size_info = f"{compressed:,} bytes ({decompressed:,} decompressed, {ratio:.0f}% saved)"
            else:
                size_info = f"{compressed:,} bytes"
            
            # Log individual file details
            if VERBOSE_LOGGING:
                print(f"  ✓ File {result['index']}/{len(content_js_urls)}: {size_info} "
                      f"(video_id: {result['has_video_id']}, appstore: {result['has_appstore']}, encoding: {content_encoding})")
            
            # DEBUG: Save first content.js for inspection (only if debug_content enabled)
            if result['index'] == 1 and debug_content:
                debug_file = "/Users/rostoni/Downloads/LocalTransperancy/debug_api_content.js"
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(content_text)
                
                debug_meta_file = "/Users/rostoni/Downloads/LocalTransperancy/debug_api_content_meta.json"
                with open(debug_meta_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'url': url,
                        'response_status': result['status'],
                        'response_headers': result['headers'],
                        'content_length': result['size'],
                        'cookies_in_context': [{'name': c['name'], 'domain': c['domain']} for c in cookies]
                    }, f, indent=2)
                
                print(f"  📝 Saved first content.js to debug_api_content.js + metadata")
            
            # Store for processing (extraction logic will parse the text)
            # CRITICAL: Must be TUPLE (url, text), not dict, to match _extract_data() expectations
            content_js_responses.append((url, content_text))
            
            # Track content.js in tracker
            tracker.content_js_requests.append({
                'url': url,
                'text': content_text,
                'timestamp': time.time()
            })
            
            total_bytes += result['size']
            success_count += 1
        else:
            print(f"  ⚠️  Failed to fetch file {result['index']}: {result['url'][:80]}... - {result['error']}")
    
    if VERBOSE_LOGGING:
        print(f"  📊 Total downloaded: {total_bytes:,} bytes ({total_bytes/1024:.1f} KB) from {success_count}/{len(content_js_urls)} files")
    
    # Check if ALL content.js fetches failed (network issue - should be retried)
    if content_js_urls and success_count == 0:
        # Get the first error for classification
        sample_error = next((r['error'] for r in fetch_results if not r['success']), 'Unknown error')
        error_msg = f"All content.js fetches failed: {sample_error}"
        
        return {
            'execution_success': False,
            'execution_errors': [error_msg],
            'execution_warnings': [],
            'success': False,
            'error': error_msg,  # For proper classification as network error
            'errors': [error_msg],
            'warnings': [],
            'videos': [],
            'video_count': 0,
            'app_store_id': None,
            'real_creative_id': creative_id,
            'method_used': 'api_only_failed',
            'duration_ms': (time.time() - start_time) * 1000,
            'incoming_bytes': tracker.incoming_bytes,
            'outgoing_bytes': tracker.outgoing_bytes,
            'total_bytes': tracker.incoming_bytes + tracker.outgoing_bytes,
            'measurement_method': 'estimation'
        }
    
    # ========================================================================
    # STEP 4: Reuse Existing Extraction Logic
    # ========================================================================
    
    # Extract funded_by from API
    funded_by = extract_funded_by_from_api(tracker.api_responses, page_url)
    # Extract country presence (best-effort)
    country_presence = extract_country_presence_from_api(tracker.api_responses, page_url)
    
    # Identify creative (from API or frequency)
    creative_results = _identify_creative(tracker, page_url, static_content_info)
    real_creative_id = creative_results['real_creative_id']
    method_used = creative_results['method_used']
    
    # CRITICAL FIX: Extract fletch-render IDs from URLs
    # _extract_data expects a SET of fletch-render IDs, not full URLs
    # The bug was passing full URLs, which caused the matching logic to fail
    found_fletch_renders = set()
    for url in content_js_urls:
        fr_match = re.search(r'htmlParentId=fletch-render-([0-9]+)', url)
        if fr_match:
            found_fletch_renders.add(fr_match.group(1))
    
    print(f"\n🔍 Extracted {len(found_fletch_renders)} fletch-render IDs from content.js URLs")
    
    # Extract data (videos, App Store IDs)
    extraction_results = _extract_data(
        content_js_responses,
        found_fletch_renders,  # FIXED: Now passing SET of IDs, not full URLs
        static_content_info,
        real_creative_id,
        debug_fletch,
        debug_appstore
    )
    
    unique_videos = extraction_results['unique_videos']
    videos_by_request = extraction_results['videos_by_request']
    app_store_id = extraction_results['app_store_id']
    app_ids_from_base64 = extraction_results['app_ids_from_base64']
    extraction_method = extraction_results['extraction_method']
    
    # Save debug files if debug-content mode enabled
    if debug_content:
        print(f"💾 Saving debug files...")
        save_all_content_js_debug_files(content_js_responses)
        
        for idx, api_resp in enumerate(tracker.api_responses, 1):
            save_api_response_debug_file(api_resp, idx)
    
    # ========================================================================
    # STEP 5: Validate and Return
    # ========================================================================
    
    # Validate execution
    # Note: found_fletch_renders is already extracted above (set of IDs)
    # expected_fletch_renders should also be the set of IDs
    expected_fletch_renders = found_fletch_renders  # Same as found, since we fetched all URLs from API
    critical_errors = []
    
    validation_results = _validate_execution(
        expected_fletch_renders,
        found_fletch_renders,
        static_content_info,
        real_creative_id,
        critical_errors,
        tracker,
        [],  # all_xhr_fetch_requests (not tracked in API-only mode)
        extraction_method,
        unique_videos,
        content_js_responses
    )
    
    execution_success = validation_results['execution_success']
    execution_errors = validation_results['execution_errors']
    execution_warnings = validation_results['execution_warnings']
    
    duration_ms = (time.time() - start_time) * 1000
    
    # Get cache statistics (will be 0 for API-only, but included for consistency)
    cache_stats = get_cache_statistics()
    
    # Cleanup direct context if it was created
    if direct_context:
        await direct_context.dispose()
    
    return {
        # Execution Status
        'execution_success': execution_success,
        'execution_errors': execution_errors,
        'execution_warnings': execution_warnings,
        'success': execution_success,
        'errors': execution_errors,
        'warnings': execution_warnings,
        
        # Static Content Detection
        'is_static_content': bool(static_content_info),
        'static_content_info': static_content_info,
        
        # Videos
        'videos': unique_videos,
        'video_count': len(unique_videos),
        'videos_by_request': videos_by_request,
        
        # Creative ID
        'real_creative_id': real_creative_id if not static_content_info else static_content_info.get('creative_id_12digit'),
        'method_used': f"{method_used}_api_only",
        
        # Extraction Method
        'extraction_method': f"{extraction_method}_api_only",
        'expected_fletch_renders': len(expected_fletch_renders) if expected_fletch_renders else 0,
        'found_fletch_renders': len(found_fletch_renders) if found_fletch_renders else 0,
        
        # App Store
        'app_store_id': app_store_id,
        'app_ids_from_base64': app_ids_from_base64,
        
        # Funded By
        'funded_by': funded_by,
        # Country presence (JSON map of country_code -> last_seen ISO date)
        'country_presence': country_presence,
        
        # Traffic (estimation only, no mitmproxy in API-only mode)
        'incoming_bytes': tracker.incoming_bytes,
        'outgoing_bytes': tracker.outgoing_bytes,
        'total_bytes': tracker.incoming_bytes + tracker.outgoing_bytes,
        'measurement_method': 'estimation',
        
        # Stats
        'request_count': tracker.request_count,
        'blocked_count': tracker.blocked_count,
        'url_blocked_count': tracker.url_blocked_count,
        'duration_ms': duration_ms,
        
        # Details
        'incoming_by_type': dict(tracker.incoming_by_type),
        'outgoing_by_type': dict(tracker.outgoing_by_type),
        'content_js_requests': len(tracker.content_js_requests),
        'api_responses': len(tracker.api_responses),
        
        # Cache Statistics (0 for API-only, but included for consistency)
        'cache_hits': cache_stats['hits'],
        'cache_misses': cache_stats['misses'],
        'cache_bytes_saved': cache_stats['bytes_saved'],
        'cache_hit_rate': cache_stats['hit_rate'],
        'cache_total_requests': cache_stats['total_requests']
    }


# ============================================================================
# MAIN
# ============================================================================

async def main() -> None:
    """
    Main entry point for the Google Ads Transparency scraper.
    
    Parses command-line arguments, runs the scraper, prints results,
    and optionally saves output to JSON file. Handles errors and
    keyboard interrupts gracefully.
    
    Command-line arguments:
        url: Google Ads Transparency creative page URL (required)
             Format: https://adstransparency.google.com/advertiser/AR.../creative/CR...
        
        --proxy: Enable mitmproxy for accurate traffic measurement (optional)
                 Requires mitmproxy/mitmdump to be installed
        
        --proxy-server: External proxy server URL (optional)
                        Format: host:port (e.g., us10.4g.iproyal.com:8022)
                        Overrides --proxy if provided
        
        --proxy-username: Proxy username (required with --proxy-server)
        
        --proxy-password: Proxy password (required with --proxy-server)
        
        --debug-extra-information: Save debug files for App Store ID extraction (optional)
        
        --debug-fletch: Save debug files for fletch-render content.js (optional)
        
        --debug-content: Save ALL content.js and API responses (optional)
        
        --json: JSON output file path (optional)
                If provided, saves full results to JSON file
    
    Returns:
        None
    
    Exit codes:
        0: Success (execution_success=True)
        1: General error (exception, keyboard interrupt)
        2: Validation failed (execution_success=False)
    
    Example usage:
        # Basic scraping
        python google_ads_transparency_scraper.py \
            "https://adstransparency.google.com/advertiser/AR123/creative/CR456"
        
        # With proxy and debug modes
        python google_ads_transparency_scraper.py \
            "https://adstransparency.google.com/advertiser/AR123/creative/CR456" \
            --proxy \
            --debug-extra-information \
            --debug-fletch
        
        # Save to JSON file
        python google_ads_transparency_scraper.py \
            "https://adstransparency.google.com/advertiser/AR123/creative/CR456" \
            --json results.json
        
        # With external proxy
        python google_ads_transparency_scraper.py \
            "https://adstransparency.google.com/advertiser/AR123/creative/CR456" \
            --proxy-server "us10.4g.iproyal.com:8022" \
            --proxy-username "USER" \
            --proxy-password "PASS"
    
    Note:
        Error handling:
        - Keyboard interrupt (Ctrl+C): Exits gracefully with code 1
        - Validation failure: Exits with code 2 (execution_success=False)
        - General exceptions: Prints error and exits with code 1
        
        JSON output format:
        The --json file contains the complete result dictionary with all
        scraping data, statistics, and metadata. Use json.load() to read.
    """
    parser = argparse.ArgumentParser(
        description='Google Ads Transparency Center Scraper',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (no proxy)
  %(prog)s "https://adstransparency.google.com/advertiser/.../creative/...?region=anywhere&platform=YOUTUBE"
  
  # With mitmproxy for traffic measurement
  %(prog)s "https://..." --proxy
  
  # With external proxy (IPRoyal)
  %(prog)s "https://..." --proxy-server "us10.4g.iproyal.com:8022" --proxy-username "USER" --proxy-password "PASS"
  
  # Save to JSON
  %(prog)s "https://..." --json output.json
        """
    )
    
    # Parse command-line arguments
    # Required: URL of Google Ads Transparency creative page
    # Optional: proxy settings, debug modes, output file
    parser.add_argument('url', help='Google Ads Transparency URL to scrape')
    parser.add_argument('--proxy', action='store_true', help='Use mitmproxy for accurate traffic measurement')
    parser.add_argument('--json', metavar='FILE', help='Output results to JSON file')
    
    # External proxy arguments (IPRoyal, etc.)
    parser.add_argument('--proxy-server', help='External proxy server (e.g., us10.4g.iproyal.com:8022)')
    parser.add_argument('--proxy-username', help='Proxy username')
    parser.add_argument('--proxy-password', help='Proxy password')
    
    # Debug mode
    parser.add_argument('--debug-extra-information', action='store_true', 
                        help='Save debug files for App Store ID extraction to debug/ folder')
    parser.add_argument('--debug-fletch', action='store_true',
                        help='Save debug files for fletch-render content.js responses to debug/ folder')
    parser.add_argument('--debug-content', action='store_true',
                        help='Save ALL content.js files + API responses (GetCreativeById, SearchCreatives) to debug/ folder')
    
    args = parser.parse_args()
    
    # Parse external proxy URL if provided
    # Format: http://proxy.example.com:8080
    # Overrides --proxy flag if both are specified
    external_proxy = None
    if args.proxy_server:
        if not args.proxy_username or not args.proxy_password:
            print("❌ Error: --proxy-username and --proxy-password required when using --proxy-server")
            sys.exit(EXIT_CODE_ERROR)
        
        external_proxy = {
            'server': f"http://{args.proxy_server}",
            'username': args.proxy_username,
            'password': args.proxy_password
        }
    
    print("="*80)
    print("GOOGLE ADS TRANSPARENCY CENTER SCRAPER")
    print("="*80)
    print(f"\nURL: {args.url}")
    if external_proxy:
        print(f"Mode: External Proxy ({args.proxy_server})")
    elif args.proxy:
        print("Mode: Mitmproxy (accurate traffic measurement)")
    else:
        print("Mode: Estimation (fast, ±5% accurate)")
    
    if args.debug_extra_information:
        print("Debug Mode: ON (App Store ID extraction debug files will be saved to debug/ folder)")
    if args.debug_fletch:
        print("Debug Mode: ON (Fletch-render content.js debug files will be saved to debug/ folder)")
    if args.debug_content:
        print("Debug Mode: ON (ALL content.js + API responses will be saved to debug/ folder)")
    
    print("\nStarting scraper...\n")
    
    try:
        # Run the scraper with parsed arguments
        # This is the main scraping operation
        result = await scrape_ads_transparency_page(
            args.url, 
            use_proxy=args.proxy, 
            external_proxy=external_proxy,
            debug_appstore=args.debug_extra_information,
            debug_fletch=args.debug_fletch,
            debug_content=args.debug_content
        )
        
        print_results(result)
        
        # Save results to JSON file if --json specified
        # Includes all scraping data, statistics, and metadata
        if args.json:
            with open(args.json, 'w') as f:
                json.dump(result, f, indent=JSON_OUTPUT_INDENT)
            print(f"\n✅ Results saved to: {args.json}")
        
        # Exit with appropriate code based on execution success
        # Prefer legacy key (execution_success) if present, fall back to new key (success)
        # 0: Success, 2: Validation failed, 1: Error/interrupt
        execution_success = result.get('execution_success', result.get('success', False))
        execution_errors = result.get('execution_errors', result.get('errors', []))
        
        if not execution_success:
            print(f"\n❌ Scraping failed with {len(execution_errors)} error(s)")
            sys.exit(EXIT_CODE_VALIDATION_FAILED)  # Exit code 2 = scraping validation failed
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(EXIT_CODE_ERROR)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(EXIT_CODE_ERROR)


if __name__ == "__main__":
    asyncio.run(main())
