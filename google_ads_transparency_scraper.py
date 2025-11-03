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
    JSON_OUTPUT_INDENT
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
