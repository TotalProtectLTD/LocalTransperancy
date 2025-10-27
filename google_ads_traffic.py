"""
Google Ads Transparency Scraper - Traffic Tracking and Proxy Setup Module

This module provides network traffic tracking and proxy management components for
the Google Ads Transparency scraper suite. It includes:

1. TrafficTracker Class
   - Monitors network traffic statistics and bandwidth estimation
   - Tracks incoming/outgoing bytes with ±5% accuracy using Content-Length headers
   - Captures content.js requests and API responses for creative ID extraction
   - Groups traffic by resource type for detailed analysis

2. User Agent Selection Helper
   - Returns randomized Chrome user agents (if fake-useragent installed)
   - Falls back to default user agent for consistent browser fingerprinting
   - Used during browser context configuration

3. Proxy Setup Function
   - Initializes mitmproxy for accurate traffic measurement
   - Manages subprocess lifecycle and startup wait logic
   - Falls back to estimation mode if mitmproxy not installed
   - Handles external proxy configuration with priority override

These components are tightly coupled and used together during browser automation
setup. The TrafficTracker is registered with Playwright page events (request,
response, requestfailed), the user agent is used for browser context configuration,
and the proxy setup must occur before browser launch.

Module Dependencies:
    - Standard Library: asyncio, subprocess, os, time, re, json, collections, typing
    - Optional: fake-useragent (for randomized user agents)
    - Local: google_ads_config (for configuration constants)

Author: Google Ads Transparency Scraper Team
"""

import asyncio
import subprocess
import os
import time
import re
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Any

# Import fake-useragent for randomized Chrome user agents
try:
    from fake_useragent import UserAgent
    FAKE_USERAGENT_AVAILABLE = True
except ImportError:
    FAKE_USERAGENT_AVAILABLE = False

# Import configuration constants
from google_ads_config import (
    BLOCKED_URL_PATTERNS,
    CONTENT_JS_FILENAME,
    CONTENT_JS_DOMAIN,
    REQUEST_SIZE_OVERHEAD,
    PATTERN_CREATIVE_ID_FROM_URL,
    USE_RANDOM_USER_AGENT,
    USER_AGENT,
    MITM_ADDON_PATH,
    PROXY_ADDON_SCRIPT,
    PROXY_RESULTS_PATH,
    MITMDUMP_SEARCH_PATHS,
    SUBPROCESS_VERSION_CHECK_TIMEOUT,
    MITMPROXY_PORT,
    PROXY_STARTUP_WAIT
)


# ============================================================================
# TRAFFIC TRACKER CLASS
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
# HELPER FUNCTIONS FOR BROWSER SETUP
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

