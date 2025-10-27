"""
Google Ads Transparency Scraper - Configuration Module

This module contains all configuration constants for the Google Ads Transparency
scraper suite. It serves as the central configuration file that will be imported
by other google_ads_* modules in the refactored architecture.

Configuration includes:
- URL patterns for blocking and optimization
- Timeout and interval settings
- Network configuration (proxy, user agent)
- File paths for temporary files and scripts
- Regex patterns for data extraction
- Domain and URL patterns for detection
- Static content detection markers
- Browser configuration options
- Thresholds and limits for validation
- MITMPROXY addon script for traffic measurement

To modify script behavior:
- Adjust TIMEOUTS to tune performance vs reliability tradeoffs
- Modify NETWORK settings to change proxy configuration or user agent
- Update PATHS if running on Windows or using custom temp directories
- Extend PATTERNS if Google changes their URL structure
- Customize BROWSER settings for debugging (e.g., headless=False)
- Tune THRESHOLDS to adjust validation sensitivity
"""

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
        
        with open({repr(PROXY_RESULTS_PATH)}, 'w') as f:
            json.dump(results, f)

addons = [TrafficCounter()]
'''

