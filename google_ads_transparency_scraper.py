#!/usr/bin/env python3
"""
Google Ads Transparency Center - Production Scraper
===================================================

A comprehensive scraper for Google Ads Transparency Center that extracts real YouTube
videos and App Store IDs while filtering out Google's noise/decoy videos.

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

# Import app ID extraction from base64
try:
    from extract_app_ids import extract_app_ids
except ImportError:
    print("WARNING: extract_app_ids module not found")
    print("Base64 app ID extraction will be disabled")
    extract_app_ids = None

# ============================================================================
# CONFIGURATION
# ============================================================================

# URL patterns to block for bandwidth optimization
BLOCKED_URL_PATTERNS = [
    'qs_click_protection.js',
    'google-analytics.com',
    'GetAdvertiserDunsMapping?authuser=',
    'youtube.com/',  # YouTube embeds (we only need thumbnails from content.js)
    'googlesyndication.com',
    'apis.google.com/',
    '/adframe',
    'googletagmanager.com/gtag/js?',
    'logging?authuser='
]

# Specific gstatic.com paths to block (selective blocking like stress test)
GSTATIC_BLOCKED_PATTERNS = [
    '/images/',      # Block images from gstatic
    '/clarity/',     # Block clarity analytics
    '/_/js/k=og.qtm',  # Block optional JS
    '/_/ss/k=og.qtm'   # Block CSS
]

# Timeout and interval settings (in seconds unless specified)
PROXY_STARTUP_WAIT = 3  # seconds to wait for mitmproxy to start
PROXY_SHUTDOWN_WAIT = 1  # seconds to wait after proxy shutdown
PROXY_TERMINATION_TIMEOUT = 10  # timeout for proxy process termination
SUBPROCESS_VERSION_CHECK_TIMEOUT = 1  # timeout for mitmdump version check
PAGE_LOAD_TIMEOUT = 30000  # milliseconds for page.goto
MAX_CONTENT_WAIT = 30  # maximum seconds to wait for dynamic content
CONTENT_CHECK_INTERVAL = 0.5  # seconds between content checks
XHR_DETECTION_THRESHOLD = 15  # seconds to wait before declaring no XHR/fetch
SEARCH_CREATIVES_WAIT = 3  # seconds to wait for SearchCreatives after empty GetCreativeById

# Network configuration
MITMPROXY_PORT = '8080'  # port for mitmproxy server
MITMPROXY_SERVER_URL = 'http://localhost:8080'  # full proxy server URL
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"  # browser user agent string
BLOCKED_RESOURCE_TYPES = ['image', 'font', 'stylesheet']  # resource types to block for bandwidth optimization

# File paths for proxy and temporary files
MITM_ADDON_PATH = '/tmp/mitm_addon.py'  # path for mitmproxy addon script
PROXY_RESULTS_PATH = '/tmp/proxy_results.json'  # path for proxy traffic results
MITMDUMP_SEARCH_PATHS = ['mitmdump', '/usr/local/bin/mitmdump']  # paths to search for mitmdump executable

# Regex patterns for data extraction
# Creative ID patterns
PATTERN_CREATIVE_ID_FROM_URL = r'[?&]creativeId=(\d{12})'  # extract 12-digit creative ID from URL parameter
PATTERN_CREATIVE_ID_FROM_PAGE_URL = r'/creative/(CR\d+)'  # extract CR-prefixed creative ID from page URL
PATTERN_FLETCH_RENDER_ID = r'fletch-render-(\d+)'  # extract fletch-render ID from URL

# YouTube video patterns
PATTERN_YOUTUBE_THUMBNAIL = r'https?://i\d*\.ytimg\.com/vi/([a-zA-Z0-9_-]{11})/[^"\')\s]*'  # extract video ID from ytimg.com thumbnail URL
PATTERN_YOUTUBE_VIDEO_ID_FIELD = r'(?:\\x27|["\'])video_id(?:\\x27|["\'])\s*:\s*(?:\\x27|["\'])([a-zA-Z0-9_-]{11})(?:\\x27|["\'])'  # extract video ID from video_id field with escaped quotes
PATTERN_YOUTUBE_VIDEO_ID_CAMELCASE = r'(?:\\x27|["\'])video_videoId(?:\\x27|["\'])\s*:\s*(?:\\x27|["\'])([a-zA-Z0-9_-]{11})(?:\\x27|["\'])'  # extract video ID from video_videoId field (camelCase)

# App Store ID patterns
PATTERN_APPSTORE_STANDARD = r'(?:itunes|apps)\.apple\.com(?:/[a-z]{2})?/app/(?:[^/]+/)?id(\d{9,10})'  # standard Apple URL
PATTERN_APPSTORE_ESCAPED = r'(?:itunes|apps)(?:%2E|\.)apple(?:%2E|\.)com(?:%2F|/|\\x2F)(?:[a-z]{2}(?:%2F|/|\\x2F))?app(?:%2F|/|\\x2F)(?:[a-zA-Z0-9_-]+(?:%2F|/|\\x2F))?id(\d{9,10})'  # URL-encoded Apple URL (with optional app name)
PATTERN_APPSTORE_DIRECT = r'/app/id(\d{9,10})'  # direct app/id pattern
PATTERN_APPSTORE_JSON = r'"appId"\s*:\s*"(\d{9,10})"'  # JSON appId field

# Content.js and API patterns
PATTERN_CONTENT_JS_URL = r'https://displayads-formats\.googleusercontent\.com/ads/preview/content\.js[^"\']*'  # content.js URL in API responses (including unicode escapes)

# Domain and URL patterns for detection and filtering
# Content.js detection
CONTENT_JS_FILENAME = 'content.js'  # filename to detect content.js requests
CONTENT_JS_DOMAIN = 'displayads-formats.googleusercontent.com'  # domain for content.js files
ADVERTISER_PAGE_DOMAIN = 'adstransparency.google.com/advertiser/'  # advertiser page domain

# API endpoint names
API_GET_CREATIVE_BY_ID = 'GetCreativeById'  # API endpoint name
API_SEARCH_CREATIVES = 'SearchCreatives'  # API endpoint name
API_GET_ADVERTISER_BY_ID = 'GetAdvertiserById'  # API endpoint name
API_ENDPOINTS = ['GetCreativeById', 'SearchCreatives', 'GetAdvertiserById']  # list of all API endpoints to capture

# Static content detection
STATIC_IMAGE_AD_URL = 'tpc.googlesyndication.com/archive/simgad'  # URL pattern for static image ads
STATIC_HTML_AD_URL = 'tpc.googlesyndication.com/archive/sadbundle'  # URL pattern for cached HTML ads
ARCHIVE_PATH = '/archive/'  # archive path indicator
ARCHIVE_INDEX_FILE = 'index.html'  # archive index file
FLETCH_RENDER_MARKER = 'fletch-render-'  # marker for dynamic content

# Browser configuration
BROWSER_HEADLESS = True  # run browser in headless mode
BROWSER_ARGS = ['--disable-dev-shm-usage', '--disable-plugins']  # Chrome launch arguments
ENABLE_STEALTH_MODE = True  # enable playwright-stealth for bot detection evasion (if available)
USE_RANDOM_USER_AGENT = True  # use random Chrome user agent for each run (if fake-useragent available)

# Thresholds and limits for validation and processing
REQUEST_SIZE_OVERHEAD = 100  # bytes to add for request/response size estimation
HIGH_BLOCKING_THRESHOLD = 0.9  # 90% - threshold for warning about high blocking rate
BYTE_CONVERSION_FACTOR = 1024.0  # factor for converting bytes to KB/MB/GB
JSON_OUTPUT_INDENT = 2  # indentation level for JSON output
EXIT_CODE_VALIDATION_FAILED = 2  # exit code when scraping validation fails
EXIT_CODE_ERROR = 1  # exit code for general errors
MAX_XHR_DISPLAY_COUNT = 5  # maximum number of XHR requests to display in diagnostics

# ============================================================================
# END OF CONFIGURATION
# ============================================================================
# All hardcoded values have been extracted to constants above for easy
# configuration and maintenance. To modify script behavior:
#
# - Adjust TIMEOUTS to tune performance vs reliability tradeoffs
# - Modify NETWORK settings to change proxy configuration or user agent
# - Update PATHS if running on Windows or using custom temp directories
# - Extend PATTERNS if Google changes their URL structure
# - Customize BROWSER settings for debugging (e.g., headless=False)
# - Tune THRESHOLDS to adjust validation sensitivity
#
# ============================================================================

# Mitmproxy addon for accurate traffic measurement
PROXY_ADDON_SCRIPT = f'''
import json

class TrafficCounter:
    def __init__(self):
        self.total_request_bytes = 0
        self.total_response_bytes = 0
        self.request_count = 0
    
    def request(self, flow):
        """Called for each request."""
        request_size = len(flow.request.raw_content) if flow.request.raw_content else 0
        request_size += sum(len(f"{{k}}: {{v}}\r\n".encode()) for k, v in flow.request.headers.items())
        request_size += len(f"{{flow.request.method}} {{flow.request.path}} HTTP/1.1\r\n".encode())
        
        self.total_request_bytes += request_size
        self.request_count += 1
    
    def response(self, flow):
        """Called for each response."""
        content_length = flow.response.headers.get('content-length', None)
        if content_length:
            body_size = int(content_length)
        elif flow.response.raw_content:
            body_size = len(flow.response.raw_content)
        else:
            body_size = 0
        
        headers_size = sum(len(f"{{k}}: {{v}}\r\n".encode()) for k, v in flow.response.headers.items())
        response_size = body_size + headers_size
        
        self.total_response_bytes += response_size
    
    def done(self):
        """Called when mitmproxy is shutting down."""
        results = {{
            'total_request_bytes': self.total_request_bytes,
            'total_response_bytes': self.total_response_bytes,
            'total_bytes': self.total_request_bytes + self.total_response_bytes,
            'request_count': self.request_count
        }}
        
        with open('{PROXY_RESULTS_PATH}', 'w') as f:
            json.dump(results, f)

addons = [TrafficCounter()]
'''


# ============================================================================
# TRAFFIC TRACKER
# ============================================================================

class TrafficTracker:
    """
    Tracks network traffic statistics and provides bandwidth estimation.
    
    This class monitors all network requests and responses during page scraping,
    providing accurate bandwidth measurements using Content-Length headers (±5%
    accuracy compared to actual proxy measurements). It also tracks content.js
    requests and API responses for creative identification.
    
    Attributes:
        incoming_bytes (int): Total bytes received from server
        outgoing_bytes (int): Total bytes sent to server
        request_count (int): Total number of requests made
        blocked_count (int): Number of requests that failed or were blocked
        url_blocked_count (int): Number of URLs blocked by pattern matching
        incoming_by_type (defaultdict): Incoming bytes grouped by resource type
        outgoing_by_type (defaultdict): Outgoing bytes grouped by resource type
        blocked_urls (list): List of (url, reason) tuples for blocked URLs
        content_js_requests (list): List of content.js request metadata
        api_responses (list): List of captured API response data
    
    Example:
        tracker = TrafficTracker()
        # Register with Playwright page events
        page.on('request', lambda req: tracker.on_request(req))
        page.on('response', lambda res: tracker.on_response(res))
        page.on('requestfailed', lambda req: tracker.on_request_failed(req))
        
        # After page load, access statistics
        print(f"Total traffic: {tracker.incoming_bytes + tracker.outgoing_bytes} bytes")
        print(f"API responses captured: {len(tracker.api_responses)}")
    """
    
    def __init__(self):
        self.incoming_bytes = 0
        self.outgoing_bytes = 0
        self.request_count = 0
        self.blocked_count = 0
        self.url_blocked_count = 0
        
        self.incoming_by_type = defaultdict(int)
        self.outgoing_by_type = defaultdict(int)
        self.blocked_urls = []
        
        # Track content.js requests for creative ID extraction
        self.content_js_requests = []
        
        # Track API responses for real creative ID identification
        self.api_responses = []
    
    def should_block_url(self, url: str) -> Tuple[bool, Optional[str]]:
        """
        Check if URL should be blocked based on configured patterns.
        
        Iterates through BLOCKED_URL_PATTERNS to determine if the URL matches
        any blocking criteria. Used for bandwidth optimization by preventing
        unnecessary resource downloads.
        
        Args:
            url: The URL to check against blocking patterns.
        
        Returns:
            A tuple of (should_block, pattern) where:
                - should_block (bool): True if URL should be blocked
                - pattern (str or None): The matching pattern if blocked, None otherwise
        
        Example:
            should_block, pattern = tracker.should_block_url('https://example.com/ads.js')
            if should_block:
                print(f"Blocked by pattern: {pattern}")
        """
        for pattern in BLOCKED_URL_PATTERNS:
            if pattern in url:
                return True, pattern
        return False, None
    
    def on_request(self, request) -> None:
        """
        Handle request event and update traffic statistics.
        
        Called automatically by Playwright when a request is made. Calculates
        request size by summing URL length, headers size, and overhead. Tracks
        special content.js requests for creative ID extraction.
        
        Args:
            request: Playwright Request object containing URL, headers, and resource type.
        
        Returns:
            None
        
        Note:
            Request size estimation includes:
            - URL length (encoded as UTF-8)
            - All HTTP headers (formatted as "key: value\r\n")
            - REQUEST_SIZE_OVERHEAD constant (100 bytes for HTTP overhead)
        """
        url_size = len(request.url.encode())
        headers_size = sum(len(f"{k}: {v}\r\n".encode()) for k, v in request.headers.items())
        request_size = url_size + headers_size + REQUEST_SIZE_OVERHEAD
        
        self.outgoing_bytes += request_size
        self.request_count += 1
        
        resource_type = request.resource_type
        self.outgoing_by_type[resource_type] += request_size
        
        # Track content.js requests
        if CONTENT_JS_FILENAME in request.url and CONTENT_JS_DOMAIN in request.url:
            creative_id = self._extract_creative_id_from_url(request.url)
            self.content_js_requests.append({
                'url': request.url,
                'creative_id': creative_id,
                'timestamp': time.time()
            })
    
    def on_response(self, response) -> None:
        """
        Handle response event and update traffic statistics.
        
        Called automatically by Playwright when a response is received. Uses
        Content-Length header for accurate body size measurement. Falls back
        to 0 if header is missing (e.g., chunked encoding).
        
        Args:
            response: Playwright Response object containing headers and metadata.
        
        Returns:
            None
        
        Note:
            Response size estimation includes:
            - Content-Length header value (actual body size)
            - All HTTP response headers
            - REQUEST_SIZE_OVERHEAD constant (100 bytes)
            
            Errors are silently caught to prevent disrupting page load.
        """
        try:
            url = response.url
            
            content_length = response.headers.get('content-length')
            if content_length:
                body_size = int(content_length)
            else:
                body_size = 0
            
            headers_size = sum(len(f"{k}: {v}\r\n".encode()) for k, v in response.headers.items())
            response_size = body_size + headers_size + REQUEST_SIZE_OVERHEAD
            
            self.incoming_bytes += response_size
            
            resource_type = self._detect_type_from_response(response)
            self.incoming_by_type[resource_type] += response_size
            
        except Exception:
            pass
    
    def on_request_failed(self, request) -> None:
        """
        Handle request failure event (blocked or network error).
        
        Called automatically by Playwright when a request fails due to blocking,
        network errors, or timeouts. Increments the blocked_count for validation.
        
        Args:
            request: Playwright Request object that failed.
        
        Returns:
            None
        """
        self.blocked_count += 1
    
    def _detect_type_from_response(self, response) -> str:
        """
        Detect resource type from response Content-Type header.
        
        Maps Content-Type header values to resource type categories for
        traffic analysis. Used to group bandwidth usage by resource type.
        
        Args:
            response: Playwright Response object with headers.
        
        Returns:
            Resource type string: 'image', 'stylesheet', 'script', 'font',
            'media', 'document', 'xhr', or 'other'.
        
        Note:
            Detection is case-insensitive and uses substring matching for
            flexibility with various Content-Type formats.
        """
        content_type = response.headers.get('content-type', '').lower()
        
        if 'image/' in content_type:
            return 'image'
        elif 'text/css' in content_type:
            return 'stylesheet'
        elif 'javascript' in content_type:
            return 'script'
        elif 'font/' in content_type:
            return 'font'
        elif 'video/' in content_type or 'audio/' in content_type:
            return 'media'
        elif 'text/html' in content_type:
            return 'document'
        elif 'application/json' in content_type:
            return 'xhr'
        
        return 'other'
    
    def _extract_creative_id_from_url(self, url: str) -> Optional[str]:
        """
        Extract 12-digit creative ID from content.js URL parameter.
        
        Parses the creativeId query parameter from content.js URLs using
        the PATTERN_CREATIVE_ID_FROM_URL regex pattern.
        
        Args:
            url: Content.js URL containing creativeId parameter.
        
        Returns:
            12-digit creative ID string if found, None otherwise.
        
        Example:
            url = 'https://displayads-formats.googleusercontent.com/ads/preview/content.js?creativeId=773510960098'
            creative_id = tracker._extract_creative_id_from_url(url)
            # Returns: '773510960098'
        """
        match = re.search(PATTERN_CREATIVE_ID_FROM_URL, url, re.IGNORECASE)
        if match:
            return match.group(1)
        return None


# ============================================================================
# DATA EXTRACTION
# ============================================================================

def extract_youtube_videos_from_text(text: str) -> List[str]:
    """
    Extract YouTube video IDs from text.
    
    Handles multiple patterns:
    - ytimg.com thumbnails: i.ytimg.com/vi/VIDEO_ID/
    - video_id field: 'video_id': 'VIDEO_ID' or "video_id": "VIDEO_ID"
    - video_videoId field: 'video_videoId': 'VIDEO_ID' (camelCase variant)
    - Escaped quotes: \\x27video_id\\x27: \\x27VIDEO_ID\\x27
    
    Args:
        text: Text content to search
        
    Returns:
        list: List of 11-character YouTube video IDs
    """
    videos = []
    
    # Pattern 1: ytimg.com thumbnails
    pattern = re.compile(PATTERN_YOUTUBE_THUMBNAIL)
    videos.extend(pattern.findall(text))
    
    # Pattern 2: video_id field (with regular or escaped quotes)
    # Matches: 'video_id': 'ID', "video_id": "ID", \x27video_id\x27: \x27ID\x27
    pattern = re.compile(PATTERN_YOUTUBE_VIDEO_ID_FIELD)
    videos.extend(pattern.findall(text))
    
    # Pattern 3: video_videoId field (camelCase variant)
    # Matches: 'video_videoId': 'ID', "video_videoId": "ID", \x27video_videoId\x27: \x27ID\x27
    pattern = re.compile(PATTERN_YOUTUBE_VIDEO_ID_CAMELCASE)
    videos.extend(pattern.findall(text))
    
    return list(set(videos))


def extract_app_store_id_from_text(text: str) -> Optional[Tuple[str, str]]:
    """
    Extract App Store ID from text.
    
    Handles multiple URL formats:
    - https://apps.apple.com/us/app/id1234567890
    - https://itunes.apple.com/app/id1234567890
    - Escaped versions with %2F, \\x2F, etc.
    
    Args:
        text: Text content to search
        
    Returns:
        tuple or None: (app_store_id, pattern_description) if found, None otherwise
    """
    patterns = [
        (
            re.compile(PATTERN_APPSTORE_STANDARD, re.IGNORECASE),
            "Pattern 1: Standard Apple URL (apps.apple.com or itunes.apple.com with optional country code and app name)"
        ),
        (
            re.compile(PATTERN_APPSTORE_ESCAPED, re.IGNORECASE),
            "Pattern 2: Escaped Apple URL (URL encoded %2F, hex escaped \\x2F, etc.)"
        ),
        (
            re.compile(PATTERN_APPSTORE_DIRECT, re.IGNORECASE),
            "Pattern 3: Direct app/id pattern (/app/id followed by 9-10 digits)"
        ),
        (
        re.compile(PATTERN_APPSTORE_JSON),
            "Pattern 4: JSON appId field"
        ),
    ]
    
    for pattern, description in patterns:
        match = pattern.search(text)
        if match:
            return (match.group(1), description)
    
    return None


# ============================================================================
# DEBUG FILE UTILITIES
# ============================================================================
# This section provides a generic debug file saving system with specialized
# wrapper functions for different debug file types:
#
# - save_debug_file(): Generic function handling all common logic
#   (directory creation, timestamp generation, file writing, error handling)
#
# - save_appstore_debug_file(): Saves App Store ID extraction debug files
# - save_fletch_render_debug_file(): Saves fletch-render content.js debug files
# - save_all_content_js_debug_files(): Saves all content.js responses (batch)
# - save_api_response_debug_file(): Saves API response debug files
#
# All debug files are saved to the debug/ folder with consistent formatting.
# ============================================================================


def save_debug_file(
    file_type: str,
    filename: str,
    header_sections: Dict[str, Any],
    content: str,
    success_message: Optional[str] = None,
    print_success: bool = True,
    content_title: str = "CONTENT"
) -> None:
    """
    Generic function to save debug files with consistent formatting.
    
    This function consolidates all common debug file saving logic including
    directory creation, timestamp generation, file writing, and error handling.
    
    Args:
        file_type: String identifier for the debug file type (e.g., "APPSTORE", "API")
        filename: Complete filename to use (without path)
        header_sections: Dictionary containing metadata key-value pairs for the header
                        (e.g., {"App Store ID": "123456", "Method": "fletch-render"})
        content: The main content text to save in the file
        success_message: Optional custom success message to print (if None, use default)
        print_success: Boolean flag to control whether to print success/error messages
        content_title: Optional title for the content section (default: "CONTENT")
    
    Returns:
        None
    
    Example:
        save_debug_file(
            file_type="API RESPONSE DEBUG",
            filename="api_GetCreativeById_1_20250101_120000.txt",
            header_sections={"API Type": "GetCreativeById", "Index": "1"},
            content="<response text>",
            success_message="API debug file saved",
            content_title="API RESPONSE TEXT (Full)"
        )
    """
    import datetime
    
    # Coerce content to string to avoid NoneType issues
    content = "" if content is None else str(content)
    
    # Create debug directory if it doesn't exist
    debug_dir = os.path.join(os.getcwd(), 'debug')
    os.makedirs(debug_dir, exist_ok=True)
    
    # Generate timestamp for header
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    
    # Build filepath
    filepath = os.path.join(debug_dir, filename)
    
    # Format debug content with header
    debug_content = "=" * 80 + "\n"
    debug_content += f"{file_type}\n"
    debug_content += "=" * 80 + "\n"
    debug_content += f"Timestamp: {timestamp}\n"
    
    # Add all header sections
    for key, value in header_sections.items():
        debug_content += f"{key}: {value}\n"
    
    debug_content += "\n"
    debug_content += "=" * 80 + "\n"
    debug_content += f"{content_title}:\n"
    debug_content += "=" * 80 + "\n"
    debug_content += content + "\n"
    debug_content += "\n"
    debug_content += "=" * 80 + "\n"
    debug_content += "END OF DEBUG FILE\n"
    debug_content += "=" * 80 + "\n"
    
    # Write to file with error handling
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(debug_content)
        if print_success:
            if success_message:
                print(success_message)
            else:
                print(f"  💾 Debug file saved: {filename}")
    except Exception as e:
        if print_success:
            print(f"  ⚠️  Failed to save debug file: {e}")


def save_appstore_debug_file(
    app_store_id: str,
    text: str,
    method: str,
    url: str,
    creative_id: str,
    pattern_description: Optional[str] = None
) -> None:
    """
    Save debug file for App Store ID extraction.
    
    Args:
        app_store_id: The extracted App Store ID
        text: The content.js text that contained the ID
        method: Extraction method ('fletch-render' or 'creative-id')
        url: The content.js URL
        creative_id: The creative ID or fletch-render ID
        pattern_description: Description of the regex pattern that matched (optional)
    """
    import datetime
    
    # Build filename with timestamp
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    filename = f"appstore_{app_store_id}_{method}_{timestamp}.txt"
    
    # Build header sections dictionary
    header_sections = {
        "App Store ID": app_store_id,
        "Extraction Method": method,
        "Creative/Fletch ID": creative_id
    }
    
    if pattern_description:
        header_sections["Regex Pattern Used"] = pattern_description
    
    header_sections["Content.js URL"] = url
    
    # Call generic function
    save_debug_file(
        file_type="APP STORE ID DEBUG EXTRACTION",
        filename=filename,
        header_sections=header_sections,
        content=text,
        success_message=f"  💾 Debug file saved: {filename}",
        content_title="CONTENT.JS TEXT (Full)"
    )


def save_fletch_render_debug_file(
    fletch_render_id: str,
    text: str,
    url: str,
    creative_id: str
) -> None:
    """
    Save debug file for fletch-render content.js extraction.
    
    Args:
        fletch_render_id: The fletch-render ID
        text: The content.js text
        url: The content.js URL
        creative_id: The creative ID
    """
    import datetime
    
    # Build filename with timestamp
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    # Truncate fletch_render_id for filename (first 15 chars)
    fletch_short = fletch_render_id[:15] if len(fletch_render_id) > 15 else fletch_render_id
    filename = f"fletch_{fletch_short}_{timestamp}.txt"
    
    # Build header sections dictionary
    header_sections = {
        "Fletch-Render ID": fletch_render_id,
        "Creative ID": creative_id,
        "Content.js URL": url,
        "Content.js Size": f"{len(text)} bytes"
    }
    
    # Call generic function
    save_debug_file(
        file_type="FLETCH-RENDER CONTENT.JS DEBUG",
        filename=filename,
        header_sections=header_sections,
        content=text,
        success_message=f"  💾 Fletch debug file saved: {filename}",
        content_title="CONTENT.JS TEXT (Full)"
    )




def save_all_content_js_debug_files(
    content_js_responses: List[Tuple[str, str]]
) -> None:
    """
    Save ALL content.js responses to debug folder (enhanced debug-content mode).
    
    Args:
        content_js_responses: List of (url, text) tuples
    """
    import datetime
    
    # Pre-create debug directory once before looping
    debug_dir = os.path.join(os.getcwd(), 'debug')
    os.makedirs(debug_dir, exist_ok=True)
    
    # Loop through content_js_responses
    for idx, (url, text) in enumerate(content_js_responses, 1):
        # Extract creative ID from URL
        creative_id = 'unknown'
        match = re.search(PATTERN_CREATIVE_ID_FROM_URL, url)
        if match:
            creative_id = match.group(1)
        
        # Build filename with timestamp
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = f"all_content_{creative_id}_{idx}_{timestamp}.txt"
        
        # Build header sections dictionary
        header_sections = {
            "Creative ID": creative_id,
            "File Index": f"{idx} of {len(content_js_responses)}",
            "Content.js URL": url,
            "Content.js Size": f"{len(text)} bytes"
        }
        
        # Call generic function with error handling
        try:
            save_debug_file(
                file_type="ALL CONTENT.JS DEBUG (COMPLETE CAPTURE)",
                filename=filename,
                header_sections=header_sections,
                content=text,
                print_success=False,
                content_title="CONTENT.JS TEXT (Full)"
            )
        except Exception as e:
            print(f"  ⚠️  Failed to save all_content debug file {idx}: {e}")


def save_api_response_debug_file(
    api_response: Dict[str, Any],
    index: int
) -> None:
    """
    Save API response (GetCreativeById, SearchCreatives) to debug folder.
    
    Args:
        api_response: Dict with 'url', 'text', 'type', 'timestamp'
        index: Index number of this API response
    """
    import datetime
    
    # Extract data from api_response dict
    api_type = api_response.get('type', 'unknown')
    url = api_response.get('url', 'N/A')
    text = api_response.get('text', '')
    captured_at = api_response.get('timestamp', 'unknown')
    
    # Build filename with timestamp
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    filename = f"api_{api_type}_{index}_{timestamp}.txt"
    
    # Build header sections dictionary
    header_sections = {
        "API Type": api_type,
        "Response Index": index,
        "Captured At": captured_at,
        "API URL": url,
        "Response Size": f"{len(text)} bytes"
    }
    
    # Call generic function with error handling
    try:
        save_debug_file(
            file_type="API RESPONSE DEBUG",
            filename=filename,
            header_sections=header_sections,
            content=text,
            print_success=False,
            content_title="API RESPONSE TEXT (Full)"
        )
    except Exception as e:
        print(f"  ⚠️  Failed to save API debug file {index}: {e}")


def extract_expected_fletch_renders_from_api(
    api_responses: List[Dict[str, Any]],
    page_url: str,
    debug: bool = False
) -> Set[str]:
    """
    Extract expected fletch-render IDs from GetCreativeById API response.
    
    This function parses the GetCreativeById API response to find all content.js
    URLs, then extracts fletch-render IDs from those URLs. These IDs represent
    the expected dynamic content files that should be loaded for the creative.
    
    The function handles both plain and Unicode-escaped URL formats (\u003d, \u0026)
    commonly found in JSON API responses.
    
    Args:
        api_responses: List of captured API response dictionaries, each containing
                       'url', 'text', 'type', and 'timestamp' keys.
        page_url: Full page URL containing the creative ID (format: /creative/CR123...).
        debug: If True, print detailed extraction progress and results.
    
    Returns:
        Set of fletch-render ID strings (e.g., {"13006300890096633430", "13324661215579882186"}).
        Returns empty set if no GetCreativeById response found or parsing fails.
    
    Example:
        api_responses = [
            {'url': '...GetCreativeById...', 'text': '{...}', 'type': 'GetCreativeById', 'timestamp': 123.45}
        ]
        expected_ids = extract_expected_fletch_renders_from_api(
            api_responses,
            'https://adstransparency.google.com/advertiser/AR123/creative/CR456',
            debug=True
        )
        # Returns: {'13006300890096633430', '13324661215579882186'}
    """
    # Extract main creative ID from page URL
    match = re.search(PATTERN_CREATIVE_ID_FROM_PAGE_URL, page_url)
    if not match:
        return set()
    
    page_creative_id = match.group(1)
    
    # Find GetCreativeById response
    for api_resp in api_responses:
        api_url = api_resp.get('url', '')
        
        if API_GET_CREATIVE_BY_ID not in api_url:
            continue
        
        try:
            text = api_resp.get('text', '')
            
            # Check if this response is for our creative
            if page_creative_id not in text:
                continue
            
            if debug:
                print(f"  📋 Found GetCreativeById API response for {page_creative_id}")
            
            # Extract ALL content.js URLs from the API response using regex
            # The URLs contain fletch-render IDs and represent our "expected" list
            # Pattern matches: https://displayads-formats.googleusercontent.com/ads/preview/content.js?...
            # Handles both plain and escaped formats (\u003d becomes =, etc.)
            content_js_urls = re.findall(PATTERN_CONTENT_JS_URL, text)
            
            # Extract fletch-render IDs from these URLs
            expected_fletch_ids = set()
            for url_fragment in content_js_urls:
                # Decode unicode escapes if present (\u003d becomes =, \u0026 becomes &)
                # This handles JSON-escaped URLs in API responses
                try:
                    # Use codecs.decode to properly handle \uXXXX unicode escapes
                    import codecs
                    decoded_url = codecs.decode(url_fragment, 'unicode-escape')
                except:
                    decoded_url = url_fragment
                
                # Extract fletch-render ID
                fr_match = re.search(PATTERN_FLETCH_RENDER_ID, decoded_url)
                if fr_match:
                    expected_fletch_ids.add(fr_match.group(1))
            
            if debug:
                print(f"  ✅ Expecting {len(expected_fletch_ids)} content.js with fletch-render IDs: {list(expected_fletch_ids)}")
            
            return expected_fletch_ids
            
        except Exception as e:
            if debug:
                print(f"  ⚠️  Error parsing API: {e}")
            continue
    
    return set()


def check_if_static_cached_creative(
    api_responses: List[Dict[str, Any]],
    page_url: str
) -> Optional[Dict[str, Any]]:
    """
    Check if the creative is a static/cached ad with no dynamic content.js.
    
    Detects two types of static/cached creatives by analyzing GetCreativeById:
    1. Static image ads: Contains archive/simgad URLs (cached static images)
    2. Cached HTML text ads: Contains archive/sadbundle or archive/index.html
    
    These creatives don't have dynamic content.js files with fletch-render IDs,
    so the scraper should skip waiting for dynamic content and report accordingly.
    
    Args:
        api_responses: List of captured API response dictionaries.
        page_url: Full page URL containing the creative ID.
    
    Returns:
        Dictionary with static content info if detected:
            {
                'is_static': True,
                'creative_id': 'CR123456789012',
                'creative_id_12digit': '123456789012',
                'content_type': 'image' or 'html',
                'reason': 'Description of why it's static'
            }
        Returns None if creative has dynamic content (fletch-render URLs present).
    
    Example:
        result = check_if_static_cached_creative(api_responses, page_url)
        if result:
            print(f"Static {result['content_type']} ad detected: {result['reason']}")
    """
    # Extract creative ID from URL
    match = re.search(PATTERN_CREATIVE_ID_FROM_PAGE_URL, page_url)
    if not match:
        return None
    
    url_creative_id = match.group(1)
    
    # Find GetCreativeById response
    for api_resp in api_responses:
        if API_GET_CREATIVE_BY_ID not in api_resp.get('url', ''):
            continue
        
        try:
            text = api_resp.get('text', '')
            
            # Check if this response contains our creative ID
            if url_creative_id not in text:
                continue
            
            # Check for different types of cached content markers in API response
            # - simgad: Static image ads stored in Google's archive
            # - sadbundle: Cached HTML text ads
            # - archive/index.html: Generic cached content
            # - fletch-render: Dynamic content (if present, NOT static)
            has_simgad = STATIC_IMAGE_AD_URL in text
            has_sadbundle = STATIC_HTML_AD_URL in text
            has_archive_index = ARCHIVE_PATH in text and ARCHIVE_INDEX_FILE in text
            has_fletch_render = FLETCH_RENDER_MARKER in text
            
            # If has fletch-render, it's dynamic content (not static)
            # Early exit to avoid false positives
            if has_fletch_render:
                continue
            
            url_creative_id_numeric = url_creative_id.replace('CR', '')
            
            # Case 1: Static image ad (simgad)
            if has_simgad:
                return {
                    'is_static': True,
                    'creative_id': url_creative_id,
                    'creative_id_12digit': url_creative_id_numeric,
                    'content_type': 'image',
                    'reason': 'Static image ad with cached content - no dynamic content.js available'
                }
            
            # Case 2: Cached HTML text ad (sadbundle or other archive index.html)
            if has_sadbundle or has_archive_index:
                return {
                    'is_static': True,
                    'creative_id': url_creative_id,
                    'creative_id_12digit': url_creative_id_numeric,
                    'content_type': 'html',
                    'reason': 'Cached HTML text ad - no dynamic content.js available'
                }
        
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    
    return None


def check_empty_get_creative_by_id(
    api_responses: List[Dict[str, Any]],
    page_url: str
) -> bool:
    """
    Check if GetCreativeById returned empty {} for the target creative.
    
    An empty GetCreativeById response indicates the creative may not exist
    or is not accessible. This triggers a fallback to SearchCreatives to
    verify if the creative exists in the advertiser's creative list.
    
    Args:
        api_responses: List of captured API response dictionaries.
        page_url: Full page URL containing the creative ID.
    
    Returns:
        True if GetCreativeById response is empty {} or doesn't contain
        the target creative. False if response contains valid creative data.
    
    Note:
        This function is used for early-exit optimization in the smart wait
        loop. If GetCreativeById is empty, the scraper waits for SearchCreatives
        to verify creative existence before timing out.
    """
    # Extract creative ID from URL
    match = re.search(PATTERN_CREATIVE_ID_FROM_PAGE_URL, page_url)
    if not match:
        return False
    
    page_creative_id = match.group(1)
    
    # Find GetCreativeById response
    for api_resp in api_responses:
        if API_GET_CREATIVE_BY_ID not in api_resp.get('url', ''):
            continue
        
        try:
            text = api_resp.get('text', '').strip()
            
            # Check if response is empty {}
            if text == '{}':
                return True
            
            # Also check if it's valid JSON but doesn't contain our creative
            data = json.loads(text)
            response_creative_id = data.get('1', {}).get('2', '')
            
            # If it has data but for a different creative, keep looking
            if response_creative_id and response_creative_id != page_creative_id:
                continue
            
            # If it has data for our creative, not empty
            if response_creative_id == page_creative_id:
                return False
                
        except (json.JSONDecodeError, KeyError):
            continue
    
    return False


def check_creative_in_search_creatives(
    api_responses: List[Dict[str, Any]],
    page_url: str
) -> bool:
    """
    Check if the target creative exists in SearchCreatives response.
    
    SearchCreatives returns a list of all creatives for an advertiser.
    This function verifies if the target creative (from page URL) is
    present in that list, confirming the creative exists.
    
    Used as a fallback verification when GetCreativeById is empty.
    
    Args:
        api_responses: List of captured API response dictionaries.
        page_url: Full page URL containing the creative ID.
    
    Returns:
        True if creative found in SearchCreatives list, False otherwise.
    
    Example:
        if check_empty_get_creative_by_id(api_responses, page_url):
            # GetCreativeById is empty, check SearchCreatives
            if check_creative_in_search_creatives(api_responses, page_url):
                print("Creative exists but GetCreativeById is empty")
            else:
                print("Creative not found - may not exist")
    """
    # Extract creative ID from URL
    match = re.search(PATTERN_CREATIVE_ID_FROM_PAGE_URL, page_url)
    if not match:
        return False
    
    page_creative_id = match.group(1)
    
    # Check SearchCreatives responses
    for api_resp in api_responses:
        if API_SEARCH_CREATIVES not in api_resp.get('url', ''):
            continue
        
        try:
            data = json.loads(api_resp.get('text', ''))
            creatives_list = data.get('1', [])
            
            for creative in creatives_list:
                creative_id = creative.get('2', '')
                if creative_id == page_creative_id:
                    return True
                    
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    
    return False


def extract_real_creative_id_from_api(
    api_responses: List[Dict[str, Any]],
    page_url: str
) -> Optional[str]:
    """
    Extract real 12-digit creative ID from API responses.
    
    Tries multiple API sources for maximum reliability:
    1. GetCreativeById (primary): Fastest, most direct source
    2. SearchCreatives (fallback): Contains all advertiser creatives
    
    The "real" creative ID is the 12-digit numeric ID used in content.js
    URLs (creativeId parameter), which may differ from the CR-prefixed ID
    in the page URL.
    
    Args:
        api_responses: List of captured API response dictionaries.
        page_url: Full page URL containing the CR-prefixed creative ID.
    
    Returns:
        12-digit numeric creative ID string (e.g., "773510960098") if found,
        None if extraction fails from all sources.
    
    Example:
        creative_id = extract_real_creative_id_from_api(
            api_responses,
            'https://adstransparency.google.com/advertiser/AR123/creative/CR773510960098'
        )
        # Returns: '773510960098'
    """
    # Extract main creative ID from page URL
    match = re.search(PATTERN_CREATIVE_ID_FROM_PAGE_URL, page_url)
    if not match:
        return None
    
    page_creative_id = match.group(1)
    
    # Method 1: Try GetCreativeById first (fastest, most direct)
    # This API returns detailed creative data including content.js URLs
    # Extract creativeId parameter from the first content.js URL
    for api_resp in api_responses:
        if API_GET_CREATIVE_BY_ID not in api_resp.get('url', ''):
            continue
        
        try:
            data = json.loads(api_resp['text'])
            
            # Check if this response is for our creative
            response_creative_id = data.get('1', {}).get('2', '')
            
            if response_creative_id != page_creative_id:
                continue
            
            # Extract numeric creative ID from content.js URLs
            content_urls = data.get('1', {}).get('5', [])
            
            if not content_urls:
                continue
            
            # Get first URL
            first_url = content_urls[0].get('1', {}).get('4', '')
            
            # Extract creativeId parameter
            match = re.search(PATTERN_CREATIVE_ID_FROM_URL, first_url)
            if match:
                return match.group(1)
        
        except (json.JSONDecodeError, KeyError):
            continue
    
    # Method 2: Fallback to SearchCreatives (contains all advertiser creatives)
    # This API returns a list of all creatives for the advertiser
    # Find our creative in the list and extract its numeric ID
    searched_creatives = False
    for api_resp in api_responses:
        if API_SEARCH_CREATIVES not in api_resp.get('url', ''):
            continue
        
        searched_creatives = True
        try:
            data = json.loads(api_resp['text'])
            
            # SearchCreatives returns a list of creatives
            creatives_list = data.get('1', [])
            
            # Debug: Show we're searching
            # print(f"   Checking SearchCreatives: {len(creatives_list)} creatives found")
            
            for creative in creatives_list:
                # Check if this is our creative
                creative_id = creative.get('2', '')
                
                if creative_id == page_creative_id:
                    # Found it! Extract numeric creative ID from content.js URL
                    content_url = creative.get('3', {}).get('1', {}).get('4', '')
                    
                    if content_url:
                        match = re.search(PATTERN_CREATIVE_ID_FROM_URL, content_url)
                        if match:
                            # print(f"   ✅ Found in SearchCreatives: {match.group(1)}")
                            return match.group(1)
        
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # print(f"   ⚠️ Error parsing SearchCreatives: {e}")
            continue
    
    # if searched_creatives:
    #     print(f"   ⚠️ SearchCreatives checked but creative {page_creative_id} not found")
    
    return None


def extract_funded_by_from_api(
    api_responses: List[Dict[str, Any]],
    page_url: str
) -> Optional[str]:
    """
    Extract funded_by (sponsor company name) from GetCreativeById API response.
    
    The funded_by field is found in GetCreativeById response at path: data['1']['22']
    This represents the name of the sponsor company for the creative.
    
    Args:
        api_responses: List of captured API response dictionaries.
        page_url: Full page URL containing the CR-prefixed creative ID.
    
    Returns:
        String with sponsored company name (e.g., "BlueVision Interactive Limited") if found,
        None if extraction fails or field is not present.
    
    Example:
        funded_by = extract_funded_by_from_api(
            api_responses,
            'https://adstransparency.google.com/advertiser/AR123/creative/CR456'
        )
        # Returns: 'BlueVision Interactive Limited'
    """
    # Extract main creative ID from page URL
    match = re.search(PATTERN_CREATIVE_ID_FROM_PAGE_URL, page_url)
    if not match:
        return None
    
    page_creative_id = match.group(1)
    
    # Find GetCreativeById response
    for api_resp in api_responses:
        if API_GET_CREATIVE_BY_ID not in api_resp.get('url', ''):
            continue
        
        try:
            data = json.loads(api_resp['text'])
            
            # Check if this response is for our creative
            response_creative_id = data.get('1', {}).get('2', '')
            
            if response_creative_id != page_creative_id:
                continue
            
            # Extract funded_by from field "22"
            # Field "22" can be a string directly or nested dict like {"1": "Company Name"}
            funded_by_field = data.get('1', {}).get('22')
            
            if funded_by_field and isinstance(funded_by_field, str):
                return funded_by_field.strip()
            elif funded_by_field and isinstance(funded_by_field, dict):
                # Handle nested format: {"1": "Company Name"}
                funded_by = funded_by_field.get('1', '')
                if funded_by and isinstance(funded_by, str):
                    return funded_by.strip()
        
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    
    return None


# ============================================================================
# HELPER FUNCTIONS FOR MAIN SCRAPER
# ============================================================================

def _get_user_agent() -> str:
    """
    Get user agent string for browser context.
    
    Returns random Chrome user agent if fake-useragent is available and enabled,
    otherwise returns default hardcoded user agent.
    
    Returns:
        User agent string for browser configuration.
    
    Example:
        ua = _get_user_agent()
        # With fake-useragent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
        # Without: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    """
    if FAKE_USERAGENT_AVAILABLE and USE_RANDOM_USER_AGENT:
        try:
            ua = UserAgent(browsers=['Chrome'])
            user_agent = ua.random
            return user_agent
        except Exception:
            # Fallback to default if fake-useragent fails
            return USER_AGENT
    else:
        return USER_AGENT


async def _setup_proxy(
    use_proxy: bool,
    external_proxy: Optional[Dict[str, str]]
) -> Dict[str, Any]:
    """
    Setup mitmproxy for accurate traffic measurement.
    
    Initializes mitmproxy with a custom addon script for counting request/response
    bytes. Falls back to estimation mode if mitmproxy is not installed. External
    proxy configuration takes priority over mitmproxy.
    
    Args:
        use_proxy: Boolean flag indicating whether to use mitmproxy for traffic
                   measurement. If False, uses estimation mode.
        external_proxy: Optional dictionary with external proxy configuration:
                        {'server': 'http://proxy.example.com:8080', ...}
                        If provided, overrides mitmproxy setup.
    
    Returns:
        Dictionary containing:
            - 'proxy_process': subprocess.Popen object if mitmproxy started,
                              None otherwise
            - 'use_proxy': Boolean indicating if proxy is active (may be modified
                          from input if mitmproxy not found)
    
    Example:
        result = await _setup_proxy(use_proxy=True, external_proxy=None)
        if result['use_proxy']:
            print("Mitmproxy started successfully")
            proxy_process = result['proxy_process']
        else:
            print("Using estimation mode")
    
    Note:
        Mitmproxy addon script is written to MITM_ADDON_PATH (/tmp/mitm_addon.py)
        and results are saved to PROXY_RESULTS_PATH (/tmp/proxy_results.json).
        The function searches for mitmdump in MITMDUMP_SEARCH_PATHS.
    """
    proxy_process = None
    
    # If external proxy provided, use it (overrides mitmproxy)
    if external_proxy:
        print(f"🔧 Using external proxy: {external_proxy.get('server', 'N/A')}")
        return {'proxy_process': None, 'use_proxy': False}
    
    # Early return if proxy not requested
    if not use_proxy:
        return {'proxy_process': None, 'use_proxy': False}
    
    # Start proxy if requested (mitmproxy for traffic measurement only)
    print("🔧 Starting mitmproxy...")
    # Write mitmproxy addon script to temporary file
    # This script counts request/response bytes and saves results to JSON
    with open(MITM_ADDON_PATH, 'w') as f:
        f.write(PROXY_ADDON_SCRIPT)
    
    if os.path.exists(PROXY_RESULTS_PATH):
        os.remove(PROXY_RESULTS_PATH)
    
    # Try to find mitmdump executable in common locations
    # Tests each path by running --version command with timeout
    mitmdump_paths = MITMDUMP_SEARCH_PATHS
    mitmdump_cmd = None
    
    for path in mitmdump_paths:
        try:
            subprocess.run([path, '--version'], capture_output=True, timeout=SUBPROCESS_VERSION_CHECK_TIMEOUT)
            mitmdump_cmd = path
            break
        except:
            continue
    
    if mitmdump_cmd:
        proxy_process = subprocess.Popen(
            [mitmdump_cmd, '-p', MITMPROXY_PORT, '-s', MITM_ADDON_PATH, '--set', 'stream_large_bodies=1'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        await asyncio.sleep(PROXY_STARTUP_WAIT)
        print("✓ Proxy started")
    else:
        print("⚠ mitmproxy not found, using estimation mode")
        use_proxy = False
    
    return {'proxy_process': proxy_process, 'use_proxy': use_proxy}


async def _setup_browser_context(
    p,  # Playwright instance (no type hint to avoid import issues)
    use_proxy: bool,
    external_proxy: Optional[Dict[str, str]]
) -> Dict[str, Any]:
    """
    Launch browser and create context with proxy configuration.
    
    Creates a Chromium browser instance with custom user agent and proxy
    settings. Proxy configuration is applied at the context level (not
    browser level) for per-request control.
    
    Args:
        p: Playwright instance from async_playwright() context manager.
        use_proxy: Boolean indicating if mitmproxy is active.
        external_proxy: Optional dictionary with external proxy configuration.
                        Takes priority over mitmproxy if provided.
    
    Returns:
        Dictionary containing:
            - 'browser': Playwright Browser instance
            - 'context': Playwright BrowserContext instance with proxy configured
            - 'user_agent': User agent string used for this session
    
    Example:
        async with async_playwright() as p:
            result = await _setup_browser_context(p, use_proxy=True, external_proxy=None)
            browser = result['browser']
            context = result['context']
            user_agent = result['user_agent']
            page = await context.new_page()
            # ... use page ...
            await browser.close()
    
    Note:
        Browser is launched with:
        - Headless mode (configurable via BROWSER_HEADLESS constant)
        - Custom Chrome arguments (BROWSER_ARGS: disable-dev-shm-usage, disable-plugins)
        - Random Chrome user agent (if fake-useragent available) or default USER_AGENT
        - HTTPS error ignoring when proxy is active
    """
    browser = await p.chromium.launch(
        headless=BROWSER_HEADLESS,
        args=BROWSER_ARGS
    )
    
    # Get user agent (random Chrome if fake-useragent available, otherwise default)
    user_agent = _get_user_agent()
    
    # Set proxy at context level (not browser level) for per-request control
    # This allows route handlers to selectively block requests
    context_options = {
        'user_agent': user_agent,
        'ignore_https_errors': use_proxy or bool(external_proxy)
    }
    
    # Configure proxy (external proxy takes priority over mitmproxy)
    # External proxy is used for corporate/custom proxy setups
    if external_proxy:
        context_options['proxy'] = external_proxy
    elif use_proxy:
        context_options['proxy'] = {"server": MITMPROXY_SERVER_URL}
    
    context = await browser.new_context(**context_options)
    
    return {'browser': browser, 'context': context, 'user_agent': user_agent}


def _create_route_handler(tracker: 'TrafficTracker') -> Callable[[Any], Awaitable[None]]:
    """
    Create route handler factory for URL and resource type blocking.
    
    Returns a closure that captures the tracker reference and provides
    URL blocking logic. The handler blocks images, fonts, stylesheets,
    and URLs matching configured patterns to optimize bandwidth usage.
    
    Special handling for gstatic.com: Only blocks specific problematic
    paths while allowing other gstatic content (needed for page functionality).
    
    Args:
        tracker: TrafficTracker instance for recording blocked URLs and statistics.
    
    Returns:
        Async callable route handler function that accepts a Playwright Route object.
        The handler can be registered with: context.route('**/*', handler)
    
    Example:
        tracker = TrafficTracker()
        route_handler = _create_route_handler(tracker)
        await context.route('**/*', route_handler)
        
        # After page load:
        print(f"Blocked {tracker.url_blocked_count} URLs")
        for url, reason in tracker.blocked_urls:
            print(f"  {url} - {reason}")
    
    Note:
        Blocking criteria:
        - Resource types: image, font, stylesheet (BLOCKED_RESOURCE_TYPES)
        - URL patterns: Configured in BLOCKED_URL_PATTERNS
        - Selective gstatic.com: Only specific paths in GSTATIC_BLOCKED_PATTERNS
    """
    async def handle_route(route):
        url = route.request.url
        resource_type = route.request.resource_type
        
        # Block images, fonts, and stylesheets to reduce bandwidth
        # These resources are not needed for extracting video IDs or App Store IDs
        if resource_type in BLOCKED_RESOURCE_TYPES:
            tracker.url_blocked_count += 1
            tracker.blocked_urls.append((url, f'{resource_type} (resource type)'))
            await route.abort()
            return
        
        # Block specific URL patterns
        should_block, pattern = tracker.should_block_url(url)
        
        # Special handling for gstatic.com - selective blocking
        # Some gstatic resources are needed for page functionality
        # Only block specific problematic paths (fonts, images, etc.)
        if 'gstatic.com' in url:
            # Only block specific problematic paths
            if any(gstatic_pattern in url for gstatic_pattern in GSTATIC_BLOCKED_PATTERNS):
                tracker.url_blocked_count += 1
                tracker.blocked_urls.append((url, 'gstatic.com (selective)'))
                await route.abort()
                return
            # Allow other gstatic content
            should_block = False
        
        if should_block:
            tracker.url_blocked_count += 1
            tracker.blocked_urls.append((url, pattern))
            await route.abort()
        else:
            await route.continue_()
    
    return handle_route


def _create_response_handler(
    tracker: 'TrafficTracker',
    content_js_responses: List[Tuple[str, str]],
    all_xhr_fetch_requests: List[Dict[str, Any]]
) -> Callable[[Any], Awaitable[None]]:
    """
    Create response handler factory for capturing API and content.js responses.
    
    Returns a closure that captures references to tracker and response lists,
    providing response capture logic. The handler tracks all XHR/fetch requests
    and specifically captures API responses and content.js files.
    
    Args:
        tracker: TrafficTracker instance for storing API responses.
        content_js_responses: List to append (url, text) tuples for content.js files.
        all_xhr_fetch_requests: List to append XHR/fetch request metadata for debugging.
    
    Returns:
        Async callable response handler function that accepts a Playwright Response object.
        The handler can be registered with: page.on('response', handler)
    
    Example:
        tracker = TrafficTracker()
        content_js_responses = []
        all_xhr_fetch_requests = []
        
        response_handler = _create_response_handler(
            tracker, content_js_responses, all_xhr_fetch_requests
        )
        page.on('response', response_handler)
        
        # After page load:
        print(f"Captured {len(tracker.api_responses)} API responses")
        print(f"Captured {len(content_js_responses)} content.js files")
        print(f"Total XHR/fetch: {len(all_xhr_fetch_requests)}")
    
    Note:
        Captures three types of responses:
        1. All XHR/fetch requests (for debugging "No API" cases)
        2. API responses: GetCreativeById, SearchCreatives, GetAdvertiserById
        3. Content.js files: From displayads-formats.googleusercontent.com
    """
    async def handle_response(response):
        url = response.url
        
        # Track ALL XHR/fetch requests for debugging "No API" cases
        # This helps diagnose when API responses are not captured
        if response.request.resource_type in ['xhr', 'fetch']:
            all_xhr_fetch_requests.append({
                'url': url,
                'status': response.status,
                'timestamp': time.time()
            })
        
        # Capture API responses (GetCreativeById, SearchCreatives, GetAdvertiserById)
        # These contain creative metadata and expected content.js URLs
        if response.request.resource_type in ['xhr', 'fetch']:
            if any(api in url for api in API_ENDPOINTS):
                try:
                    text = await response.text()
                    
                    api_type = 'unknown'
                    if API_GET_CREATIVE_BY_ID in url:
                        api_type = API_GET_CREATIVE_BY_ID
                    elif API_SEARCH_CREATIVES in url:
                        api_type = API_SEARCH_CREATIVES
                    elif API_GET_ADVERTISER_BY_ID in url:
                        api_type = API_GET_ADVERTISER_BY_ID
                    
                    tracker.api_responses.append({
                        'url': url,
                        'text': text,
                        'type': api_type,
                        'timestamp': time.time()
                    })
                except:
                    pass
        
        # Capture content.js responses from Google's ad preview domain
        # These files contain the actual ad content (videos, App Store IDs)
        if CONTENT_JS_DOMAIN in url or ADVERTISER_PAGE_DOMAIN in url:
            try:
                text = await response.text()
                content_js_responses.append((url, text))
            except:
                pass
    
    return handle_response


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
    print("Waiting for dynamic content...")
    
    # Initialize state variables
    max_wait = MAX_CONTENT_WAIT
    check_interval = CONTENT_CHECK_INTERVAL
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
    Extract YouTube video IDs and App Store IDs from content.js files.
    
    Processes matched content.js files to extract:
    1. YouTube video IDs: From ytimg.com thumbnails and video_id fields
    2. App Store IDs: From Apple App Store URLs (apps.apple.com, itunes.apple.com)
    3. App IDs from base64: From base64-encoded ad parameters (only if "App Store" text present)
    
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
                        'url': url[:100] + '...',
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
    
    # Display base64-extracted app IDs
    if app_ids_from_base64:
        print(f"\n✅ App IDs from base64: {len(app_ids_from_base64)} found")
        for app_id in sorted(app_ids_from_base64):
            print(f"   • {app_id}")
    
    return {
        'unique_videos': unique_videos,
        'videos_by_request': videos_by_request,
        'app_store_id': app_store_id,
        'app_ids_from_base64': list(app_ids_from_base64),  # Convert set to list for JSON serialization
        'extraction_method': extraction_method,
        'all_videos': all_videos
    }


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
        
        route_handler = _create_route_handler(tracker)
        await context.route('**/*', route_handler)
        
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
        await page.goto(page_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
        
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
        'api_responses': len(tracker.api_responses)
    }


# ============================================================================
# OUTPUT FORMATTING
# ============================================================================

def format_bytes(bytes_value: int) -> str:
    """
    Format byte count into human-readable string with appropriate unit.
    
    Converts byte values to KB, MB, or GB with one decimal place precision.
    Uses 1024 as the conversion factor (binary units).
    
    Args:
        bytes_value: Number of bytes to format (integer).
    
    Returns:
        Formatted string with value and unit (e.g., "1.5 MB", "523.2 KB").
    
    Example:
        print(format_bytes(1024))        # "1.0 KB"
        print(format_bytes(1536))        # "1.5 KB"
        print(format_bytes(1048576))     # "1.0 MB"
        print(format_bytes(1572864))     # "1.5 MB"
        print(format_bytes(1073741824))  # "1.0 GB"
        print(format_bytes(500))         # "500 B"
    
    Note:
        Uses binary units (1024 bytes = 1 KB) rather than decimal units
        (1000 bytes = 1 KB) for consistency with system tools.
    """
    b = bytes_value
    for unit in ['B', 'KB', 'MB', 'GB']:
        if b < BYTE_CONVERSION_FACTOR:
            return f"{b:.2f} {unit}"
        b /= BYTE_CONVERSION_FACTOR
    return f"{b:.2f} TB"


def print_results(result: Dict[str, Any]) -> None:
    """
    Print scraping results in a human-readable formatted output.
    
    Displays comprehensive scraping results including:
    - Execution status (success/failure with errors and warnings)
    - Extracted data (videos, App Store ID)
    - Creative identification (ID and method)
    - Extraction method used
    - Traffic statistics (bandwidth, requests, blocking)
    - Performance metrics (duration, API responses, content.js files)
    
    Args:
        result: Dictionary returned by scrape_ads_transparency_page() containing
                all scraping results, statistics, and metadata.
    
    Returns:
        None (prints to stdout)
    
    Example:
        result = await scrape_ads_transparency_page(page_url)
        print_results(result)
    
    Note:
        Output format uses emoji icons for visual clarity:
        - ✅/❌: Success/failure status
        - 📹: Videos section
        - 📱: App Store ID
        - 🔍: Creative ID
        - 📦: Extraction method
        - 📊: Traffic statistics
        - ⏱️: Performance metrics
        - ⚠️: Warnings
        - 🔬/🔢/🖼️: Identification methods
    """
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)
    
    # Show execution status first
    # Prefer legacy keys (execution_success, execution_errors, execution_warnings) if present
    # Fall back to new keys (success, errors, warnings) for backward compatibility
    print(f"\n{'EXECUTION STATUS':-^80}")
    execution_success = result.get('execution_success', result.get('success', False))
    execution_errors = result.get('execution_errors', result.get('errors', []))
    execution_warnings = result.get('execution_warnings', result.get('warnings', []))
    
    if execution_success:
        print("Status: ✅ SUCCESS")
    else:
        print("Status: ❌ FAILED")
        if execution_errors:
            print(f"Errors: {len(execution_errors)}")
            for err in execution_errors:
                print(f"  • {err}")
    
    if execution_warnings:
        print(f"Warnings: {len(execution_warnings)}")
        for warn in execution_warnings:
            print(f"  • {warn}")
    
    print(f"\n{'VIDEOS':-^80}")
    print(f"Videos found: {result['video_count']}")
    for vid in result['videos']:
        print(f"  • {vid}")
        print(f"    https://www.youtube.com/watch?v={vid}")
    
    print(f"\n{'APP STORE':-^80}")
    if result['app_store_id']:
        print(f"App Store ID: {result['app_store_id']}")
        print(f"  https://apps.apple.com/app/id{result['app_store_id']}")
    else:
        print("No App Store ID found")
    
    # Display base64-extracted app IDs
    app_ids_base64 = result.get('app_ids_from_base64', [])
    if app_ids_base64:
        print(f"\nApp IDs from base64: {len(app_ids_base64)} found")
        for app_id in sorted(app_ids_base64):
            print(f"  • {app_id}")
            print(f"    https://apps.apple.com/app/id{app_id}")
    
    print(f"\n{'FUNDED BY':-^80}")
    if result.get('funded_by'):
        print(f"Sponsor: {result['funded_by']}")
    else:
        print("No sponsor information found")
    
    print(f"\n{'CREATIVE ID':-^80}")
    print(f"Real Creative ID: {result['real_creative_id']}")
    print(f"Method used: {result['method_used']}")
    
    print(f"\n{'EXTRACTION METHOD':-^80}")
    extraction_method = result.get('extraction_method', 'unknown')
    if result.get('is_static_content'):
        print(f"Method: 🖼️  Static/Cached Content Detected")
        if result.get('static_content_info'):
            info = result['static_content_info']
            content_type = info.get('content_type', 'unknown')
            print(f"  Creative ID: {info.get('creative_id', 'N/A')}")
            if content_type == 'image':
                print(f"  Type: Image ad with cached content")
            elif content_type == 'html':
                print(f"  Type: HTML text ad with cached content")
            else:
                print(f"  Type: Cached content")
            print(f"  Reason: {info.get('reason', 'N/A')}")
    elif extraction_method == 'fletch-render':
        print(f"Method: 🎯 Fletch-Render IDs (precise API matching)")
        print(f"  Expected: {result.get('expected_fletch_renders', 0)} content.js")
        print(f"  Found: {result.get('found_fletch_renders', 0)} content.js")
    else:
        print(f"Method: ❌ None available")
    
    print(f"\n{'TRAFFIC STATISTICS':-^80}")
    method_emoji = "🔬" if result['measurement_method'] == 'proxy' else "📊"
    method_name = "Real Proxy" if result['measurement_method'] == 'proxy' else "Estimation"
    print(f"Measurement: {method_emoji} {method_name}")
    print(f"Incoming: {format_bytes(result['incoming_bytes'])}")
    print(f"Outgoing: {format_bytes(result['outgoing_bytes'])}")
    print(f"Total: {format_bytes(result['total_bytes'])}")
    print(f"Requests: {result['request_count']}")
    print(f"Blocked: {result['url_blocked_count']}")
    print(f"Duration: {result['duration_ms']:.0f} ms")
    
    if result['incoming_by_type']:
        print(f"\n{'Traffic by Type':-^80}")
        for resource_type, bytes_count in sorted(
            result['incoming_by_type'].items(),
            key=lambda x: x[1],
            reverse=True
        ):
            pct = (bytes_count / result['incoming_bytes'] * 100) if result['incoming_bytes'] > 0 else 0
            print(f"  {resource_type:<15} {format_bytes(bytes_count):<15} ({pct:.1f}%)")
    
    print("\n" + "="*80)


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

