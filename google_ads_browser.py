"""
Browser Automation and Network Interception Module for Google Ads Transparency Scraper.

This module provides browser automation components for the Google Ads Transparency
scraper suite, including:
- Browser context setup with proxy configuration
- Route handler factory for selective URL and resource type blocking
- Response handler factory for capturing API responses and content.js files

These functions work together with TrafficTracker from google_ads_traffic.py to 
provide complete browser automation with network monitoring. The route handler 
blocks unnecessary resources to optimize bandwidth, while the response handler 
captures critical data for creative identification.

Components:
- _setup_browser_context(): Launches Chromium browser with proxy and user agent
- _create_route_handler(): Factory for route handlers that block unwanted resources
- _create_response_handler(): Factory for response handlers that capture API data

Integration:
- Import TrafficTracker from google_ads_traffic.py for network monitoring
- Import configuration constants from google_ads_config.py for behavior control
- Used by main scraper to set up browser automation pipeline
"""

import time
from typing import Dict, List, Tuple, Optional, Any, Callable, Awaitable

# Import configuration constants
from google_ads_config import (
    BROWSER_HEADLESS,
    BROWSER_ARGS,
    MITMPROXY_SERVER_URL,
    BLOCKED_RESOURCE_TYPES,
    GSTATIC_BLOCKED_PATTERNS,
    API_ENDPOINTS,
    API_GET_CREATIVE_BY_ID,
    API_SEARCH_CREATIVES,
    API_GET_ADVERTISER_BY_ID,
    CONTENT_JS_DOMAIN,
    ADVERTISER_PAGE_DOMAIN
)

# Import traffic tracking utilities
from google_ads_traffic import _get_user_agent, TrafficTracker


# ============================================================================
# Browser Automation Functions
# ============================================================================

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
        
        # Compute resource type check once for reuse
        is_xhr_or_fetch = response.request.resource_type in ['xhr', 'fetch']
        
        # Track ALL XHR/fetch requests for debugging "No API" cases
        # This helps diagnose when API responses are not captured
        if is_xhr_or_fetch:
            all_xhr_fetch_requests.append({
                'url': url,
                'status': response.status,
                'timestamp': time.time()
            })
        
        # Capture API responses (GetCreativeById, SearchCreatives, GetAdvertiserById)
        # These contain creative metadata and expected content.js URLs
        if is_xhr_or_fetch:
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

