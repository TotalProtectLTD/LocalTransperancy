#!/usr/bin/env python3
"""
Script to analyze network requests and responses on Google Ads Transparency page.
Logs all requests, responses, and headers for debugging cache/detection issues.

FEATURES:
- Captures all network requests and responses
- Logs request/response headers and cookies
- Saves response bodies to separate files
- Blocks unnecessary resources (images, fonts, CSS, analytics) to reduce bandwidth
- Organized file structure with cross-references
- Cookie tracking over time
- Smart caching for main.dart.js files (local cache on disk)
- Mitmproxy support for precise traffic measurement

BLOCKING:
- Set ENABLE_BLOCKING = True to block images, fonts, stylesheets, analytics, etc.
- Set ENABLE_BLOCKING = False to capture everything (useful for debugging)
- Blocking rules imported from google_ads_transparency_scraper.py

TRAFFIC MEASUREMENT:
- Set USE_MITMPROXY = True to enable precise traffic measurement via mitmproxy
- Set USE_MITMPROXY = False to use estimation mode (faster, no proxy needed)
- Requires mitmproxy/mitmdump to be installed: pip install mitmproxy

CACHING:
- Set USE_LOCAL_CACHE_FOR_MAIN_DART = True to cache main.dart.js files locally
- Set AUTO_CACHE_ON_MISS = True to automatically download and cache on first request
- Cached files stored in main.dart/ directory
"""

import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright
import logging
import tempfile
import os
import signal
import subprocess
import time
import shutil
import re
import threading
import fcntl  # For file locking on Unix/Linux/macOS

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create temp directory for logs within the project
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(SCRIPT_DIR, 'temp_network_logs')
os.makedirs(TEMP_DIR, exist_ok=True)
logger.info(f"Logs will be saved to: {TEMP_DIR}")

# Create cache directory for main.dart.js files
CACHE_DIR = os.path.join(SCRIPT_DIR, 'main.dart')
os.makedirs(CACHE_DIR, exist_ok=True)
logger.info(f"Cache directory: {CACHE_DIR}")

# ============================================================================
# BLOCKING CONFIGURATION (from google_ads_transparency_scraper.py)
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
    'logging?authuser=',
    "images/flags/",
    "googleapis.com/css?",
    "SearchService/SearchCreatives?authuser"

]

# Specific gstatic.com paths to block (selective blocking)
GSTATIC_BLOCKED_PATTERNS = [
    '/images/',      # Block images from gstatic
    '/clarity/',     # Block clarity analytics
    '/_/js/k=og.qtm',  # Block optional JS
    '/_/ss/k=og.qtm' ,
    "prod/api/main.min.js",
    "prod/service/lazy.min.js"  # Block CSS
]

# Resource types to block for bandwidth optimization
BLOCKED_RESOURCE_TYPES = ['image', 'font', 'stylesheet']

# Enable/disable blocking (set to False to capture everything)
ENABLE_BLOCKING = True

# ============================================================================
# LOCAL CACHE CONFIGURATION
# ============================================================================

# Enable smart caching for main.dart.js files
USE_LOCAL_CACHE_FOR_MAIN_DART = True

# URL pattern to intercept for main.dart.js files
MAIN_DART_JS_URL_PATTERN = 'main.dart.js'

# Auto-cache: If True, automatically download and cache files on first request
# If False, only serve from cache if file exists
AUTO_CACHE_ON_MISS = True

# Cache expiration settings
CACHE_MAX_AGE_HOURS = 24  # Maximum age of cache files in hours
VERSION_AWARE_CACHING = True  # Track URL versions and invalidate on change
VERSION_TRACKING_FILE = 'cache_versions.json'  # File to track URL versions

# Thread safety
CACHE_LOCKS = {}  # Dictionary to store locks per file
CACHE_LOCKS_LOCK = threading.Lock()  # Lock for the locks dictionary itself
VERSION_TRACKING_LOCK = threading.Lock()  # Lock for version tracking file

# In-memory cache (L1 cache - fastest)
MEMORY_CACHE = {}  # {filename: CachedFile object}
MEMORY_CACHE_LOCK = threading.Lock()
MEMORY_CACHE_MAX_SIZE_MB = 100  # Maximum memory cache size in MB
MEMORY_CACHE_TTL_SECONDS = 300  # How long to keep in memory (5 minutes)

# ============================================================================
# MITMPROXY CONFIGURATION
# ============================================================================

# Enable mitmproxy for precise traffic measurement
USE_MITMPROXY = True  # Set to True to enable mitmproxy

# Mitmproxy settings
MITMPROXY_PORT = '8080'
MITMPROXY_SERVER_URL = 'http://localhost:8080'
MITM_ADDON_PATH = '/tmp/mitm_addon_fighting_cache.py'
PROXY_RESULTS_PATH = '/tmp/proxy_results_fighting_cache.json'
MITMDUMP_SEARCH_PATHS = ['mitmdump', '/usr/local/bin/mitmdump', '/Users/rostoni/Library/Python/3.9/bin/mitmdump']

# Timeouts
PROXY_STARTUP_WAIT = 3  # seconds to wait for mitmproxy to start
PROXY_SHUTDOWN_WAIT = 1  # seconds to wait after proxy shutdown
PROXY_TERMINATION_TIMEOUT = 10  # timeout for proxy process termination
SUBPROCESS_VERSION_CHECK_TIMEOUT = 1  # timeout for mitmdump version check

# Mitmproxy addon script for traffic measurement
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
        request_size += sum(len(f"{{k}}: {{v}}\\r\\n".encode()) for k, v in flow.request.headers.items())
        request_size += len(f"{{flow.request.method}} {{flow.request.path}} HTTP/1.1\\r\\n".encode())
        
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
        
        headers_size = sum(len(f"{{k}}: {{v}}\\r\\n".encode()) for k, v in flow.response.headers.items())
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


class NetworkLogger:
    """Logs all network activity including requests, responses, headers, and cookies."""
    
    def __init__(self, output_dir, context):
        self.output_dir = output_dir
        self.context = context
        self.requests_summary = []  # Just URLs and basic info
        self.request_count = 0
        self.response_count = 0
        self.request_response_map = {}  # Map request URLs to their responses
        self.cookies_log = []  # Track cookies over time
        self.blocked_count = 0  # Track blocked requests
        self.blocked_urls = []  # Track blocked URLs with reasons
        self.cache_hit_count = 0  # Track local cache hits (disk + memory)
        self.memory_cache_hit_count = 0  # Track memory cache hits specifically
        self.disk_cache_hit_count = 0  # Track disk cache hits specifically
        self.allowed_requests = []  # Track requests that were NOT blocked
        
    def log_request(self, request):
        """Log details about an outgoing request."""
        self.request_count += 1
        
        # Get POST data safely
        post_data = None
        if request.method == 'POST':
            try:
                post_data = request.post_data
            except Exception as e:
                post_data = f"[ERROR: {str(e)}]"
        
        request_data = {
            'index': self.request_count,
            'timestamp': datetime.now().isoformat(),
            'url': request.url,
            'method': request.method,
            'resource_type': request.resource_type,
            'headers': dict(request.headers),
            'post_data': post_data
        }
        
        # Add to summary (just URL and basic info)
        self.requests_summary.append({
            'index': self.request_count,
            'timestamp': datetime.now().isoformat(),
            'method': request.method,
            'resource_type': request.resource_type,
            'url': request.url
        })
        
        # Store full request data for later pairing with response
        self.request_response_map[self.request_count] = {
            'request': request_data,
            'response': None
        }
        
        logger.info(f"[REQUEST #{self.request_count}] {request.method} {request.resource_type} - {request.url[:100]}")
        
    async def log_response(self, response):
        """Log details about an incoming response."""
        self.response_count += 1
        
        # Try to get response body
        body = None
        body_text = None
        try:
            body_bytes = await response.body()
            # Try to decode as text
            try:
                body_text = body_bytes.decode('utf-8')
            except UnicodeDecodeError:
                # If not text, store as base64
                import base64
                body = base64.b64encode(body_bytes).decode('ascii')
                body_text = f"[BINARY DATA - {len(body_bytes)} bytes]"
        except Exception as e:
            body_text = f"[ERROR READING BODY: {str(e)}]"
        
        response_data = {
            'index': self.response_count,
            'timestamp': datetime.now().isoformat(),
            'url': response.url,
            'status': response.status,
            'status_text': response.status_text,
            'headers': dict(response.headers),
            'request_method': response.request.method,
            'request_resource_type': response.request.resource_type,
            'body': body_text if body is None else body,
            'body_size': len(body_text) if body_text else 0
        }
        
        # Find matching request and pair them
        # Search for request with matching URL
        for req_idx, pair in self.request_response_map.items():
            if pair['request']['url'] == response.url and pair['response'] is None:
                pair['response'] = response_data
                break
        
        # Log cookies after each response
        await self._log_cookies(f"After response #{self.response_count}")
        
        logger.info(f"[RESPONSE #{self.response_count}] {response.status} {response.status_text} - {response.url[:100]}")
    
    async def _log_cookies(self, event_description):
        """Log current cookies state."""
        try:
            cookies = await self.context.cookies()
            if cookies:
                self.cookies_log.append({
                    'timestamp': datetime.now().isoformat(),
                    'event': event_description,
                    'cookies': cookies,
                    'count': len(cookies)
                })
        except Exception as e:
            logger.warning(f"Could not log cookies: {e}")
    
    def log_allowed_request(self, url, method, resource_type, index):
        """Log a request that was NOT blocked."""
        self.allowed_requests.append({
            'index': index,
            'timestamp': datetime.now().isoformat(),
            'method': method,
            'resource_type': resource_type,
            'url': url
        })
        
    def save_logs(self, filename_prefix='network_log'):
        """Save all logged data to separate files."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Create session directory and subdirectories
        session_dir = os.path.join(self.output_dir, f"session_{timestamp}")
        bodies_dir = os.path.join(session_dir, "response_bodies")
        headers_dir = os.path.join(session_dir, "request_headers")
        os.makedirs(session_dir, exist_ok=True)
        os.makedirs(bodies_dir, exist_ok=True)
        os.makedirs(headers_dir, exist_ok=True)
        
        # 1. Save URLs summary file (just list of all URLs)
        urls_file = os.path.join(session_dir, "00_urls_summary.txt")
        with open(urls_file, 'w', encoding='utf-8') as f:
            f.write(f"Network Capture Session - {timestamp}\n")
            f.write("=" * 80 + "\n\n")
            for req in self.requests_summary:
                f.write(f"[{req['index']:03d}] {req['method']:6s} {req['resource_type']:12s} {req['url']}\n")
        logger.info(f"Saved URLs summary to {urls_file}")
        
        # 2. Save individual request-response pairs with consistent naming
        pairs_saved = 0
        bodies_saved = 0
        headers_saved = 0
        for req_idx, pair in self.request_response_map.items():
            request_data = pair['request']
            response_data = pair['response']
            
            # Create safe filename from URL
            url_parts = request_data['url'].split('?')[0]  # Remove query params
            url_parts = url_parts.replace('https://', '').replace('http://', '')
            url_parts = url_parts.replace('/', '_').replace(':', '_')[:100]  # Limit length
            
            # Use consistent base filename for all related files
            base_filename = f"{req_idx:03d}_{url_parts}"
            
            # Save request headers to separate file for easy access
            headers_filename = f"{base_filename}_request.json"
            headers_filepath = os.path.join(headers_dir, headers_filename)
            try:
                with open(headers_filepath, 'w', encoding='utf-8') as f:
                    json.dump(request_data, f, indent=2, ensure_ascii=False)
                headers_saved += 1
            except Exception as e:
                logger.warning(f"Could not save request headers for request {req_idx}: {e}")
            
            # Save response body to separate file if it exists
            body_filename = None
            if response_data and response_data.get('body'):
                body_content = response_data['body']
                
                # Determine file extension based on content type
                content_type = response_data.get('headers', {}).get('content-type', '')
                if 'json' in content_type:
                    ext = '.json'
                elif 'html' in content_type:
                    ext = '.html'
                elif 'javascript' in content_type or 'script' in content_type:
                    ext = '.js'
                elif 'css' in content_type:
                    ext = '.css'
                elif 'xml' in content_type:
                    ext = '.xml'
                elif body_content.startswith('[BINARY DATA'):
                    ext = '.bin.txt'  # Binary data description
                else:
                    ext = '.txt'
                
                body_filename = f"{base_filename}_response{ext}"
                body_filepath = os.path.join(bodies_dir, body_filename)
                
                # Save body content
                try:
                    with open(body_filepath, 'w', encoding='utf-8') as f:
                        f.write(body_content)
                    bodies_saved += 1
                    
                    # Update response data to reference the body file instead of including content
                    response_data_copy = response_data.copy()
                    response_data_copy['body'] = f"[SEE FILE: response_bodies/{body_filename}]"
                    response_data_copy['body_file'] = f"response_bodies/{body_filename}"
                    response_data_copy['request_headers_file'] = f"request_headers/{headers_filename}"
                    response_data = response_data_copy
                except Exception as e:
                    logger.warning(f"Could not save body for request {req_idx}: {e}")
            
            # Save combined request-response metadata JSON (summary file)
            filename = f"{base_filename}_summary.json"
            filepath = os.path.join(session_dir, filename)
            
            # Combine request and response (without body content)
            combined = {
                'request': request_data,
                'response': response_data if response_data else {'status': 'NO_RESPONSE', 'note': 'Response not captured'},
                'related_files': {
                    'request_headers': f"request_headers/{headers_filename}",
                    'response_body': f"response_bodies/{body_filename}" if body_filename else None
                }
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(combined, f, indent=2, ensure_ascii=False)
            
            pairs_saved += 1
        
        logger.info(f"Saved {pairs_saved} request-response pairs to {session_dir}")
        logger.info(f"Saved {headers_saved} request headers to {headers_dir}")
        logger.info(f"Saved {bodies_saved} response bodies to {bodies_dir}")
        
        # 3. Save cookies log
        cookies_file = os.path.join(session_dir, "00_cookies_log.json")
        with open(cookies_file, 'w', encoding='utf-8') as f:
            json.dump(self.cookies_log, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(self.cookies_log)} cookie snapshots to {cookies_file}")
        
        # 3b. Save blocked URLs log (if any)
        if self.blocked_urls:
            blocked_file = os.path.join(session_dir, "00_blocked_urls.txt")
            with open(blocked_file, 'w', encoding='utf-8') as f:
                f.write(f"Blocked URLs - {timestamp}\n")
                f.write("=" * 80 + "\n\n")
                f.write(f"Total blocked: {len(self.blocked_urls)}\n")
                f.write(f"Blocking enabled: {ENABLE_BLOCKING}\n\n")
                
                # Group by reason
                by_reason = {}
                for url, reason in self.blocked_urls:
                    if reason not in by_reason:
                        by_reason[reason] = []
                    by_reason[reason].append(url)
                
                for reason, urls in sorted(by_reason.items()):
                    f.write(f"\n{reason} ({len(urls)} blocked):\n")
                    f.write("-" * 80 + "\n")
                    for url in urls[:10]:  # Show first 10 per reason
                        f.write(f"  {url}\n")
                    if len(urls) > 10:
                        f.write(f"  ... and {len(urls) - 10} more\n")
            
            logger.info(f"Saved {len(self.blocked_urls)} blocked URLs to {blocked_file}")
        
        # 3c. Save allowed (non-blocked) requests log
        if self.allowed_requests:
            allowed_file = os.path.join(session_dir, "00_allowed_requests.txt")
            with open(allowed_file, 'w', encoding='utf-8') as f:
                f.write(f"Allowed Requests (NOT Blocked) - {timestamp}\n")
                f.write("=" * 80 + "\n\n")
                f.write(f"Total allowed: {len(self.allowed_requests)}\n")
                f.write(f"These requests were sent to the network (not blocked)\n\n")
                
                for req in self.allowed_requests:
                    f.write(f"[{req['index']:03d}] {req['method']:6s} {req['resource_type']:12s} {req['url']}\n")
            
            logger.info(f"Saved {len(self.allowed_requests)} allowed requests to {allowed_file}")
        
        # 4. Save summary statistics
        blocking_rate = 0
        if self.blocked_count > 0:
            blocking_rate = (self.blocked_count / (len(self.requests_summary) + self.blocked_count) * 100)
        
        summary = {
            'timestamp': timestamp,
            'session_directory': session_dir,
            'total_requests': len(self.requests_summary),
            'total_responses': self.response_count,
            'total_request_headers_saved': headers_saved,
            'total_response_bodies_saved': bodies_saved,
            'total_cookie_snapshots': len(self.cookies_log),
            'blocking_enabled': ENABLE_BLOCKING,
            'blocked_requests': self.blocked_count,
            'blocking_rate_percent': round(blocking_rate, 1),
            'local_cache_enabled': USE_LOCAL_CACHE_FOR_MAIN_DART,
            'cache_hits': self.cache_hit_count,
            'requests_by_type': self._count_by_resource_type(),
            'responses_by_status': self._count_by_status(),
            'unique_domains': self._get_unique_domains(),
            'file_structure': {
                'summary_files': ['00_urls_summary.txt', '00_cookies_log.json', '00_session_summary.json'],
                'request_headers': f"{headers_saved} files in request_headers/",
                'response_bodies': f"{bodies_saved} files in response_bodies/",
                'pair_summaries': f"{pairs_saved} files in root (XXX_summary.json)"
            }
        }
        
        summary_file = os.path.join(session_dir, "00_session_summary.json")
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved session summary to {summary_file}")
        
        return session_dir, urls_file, summary_file
    
    def _count_by_resource_type(self):
        """Count requests by resource type."""
        counts = {}
        for req in self.requests_summary:
            resource_type = req['resource_type']
            counts[resource_type] = counts.get(resource_type, 0) + 1
        return counts
    
    def _count_by_status(self):
        """Count responses by status code."""
        counts = {}
        for pair in self.request_response_map.values():
            if pair['response']:
                status = str(pair['response']['status'])
                counts[status] = counts.get(status, 0) + 1
        return counts
    
    def _get_unique_domains(self):
        """Extract unique domains from requests."""
        domains = set()
        for req in self.requests_summary:
            url = req['url']
            if url.startswith('http'):
                domain = url.split('/')[2]
                domains.add(domain)
        return sorted(list(domains))


class CachedFile:
    """
    Complete cached file with content and all metadata.
    Used for in-memory caching (L1 cache).
    """
    
    def __init__(self, url, content, headers=None, disk_cached_at=None):
        self.content = content
        self.url = url
        self.filename = get_cache_filename(url)
        self.version = extract_version_from_url(url)
        self.size = len(content)
        
        # Timestamps
        self.cached_at = disk_cached_at if disk_cached_at else time.time()
        self.memory_cached_at = time.time()
        
        # HTTP headers
        if headers:
            self.etag = headers.get('etag')
            self.last_modified = headers.get('last-modified')
            self.cache_control = headers.get('cache-control')
        else:
            self.etag = None
            self.last_modified = None
            self.cache_control = None
    
    def is_valid(self, current_url):
        """
        Check if cached file is still valid.
        
        Returns:
            tuple: (is_valid: bool, reason: str)
        """
        # Check 1: Version validation
        if VERSION_AWARE_CACHING:
            current_version = extract_version_from_url(current_url)
            if self.version != current_version:
                return False, f"version changed: {self.version} → {current_version}"
        
        # Check 2: Age validation (disk cache age)
        if CACHE_MAX_AGE_HOURS > 0:
            age_hours = (time.time() - self.cached_at) / 3600
            if age_hours > CACHE_MAX_AGE_HOURS:
                return False, f"age {age_hours:.1f}h > max {CACHE_MAX_AGE_HOURS}h"
        
        # Check 3: Memory cache TTL
        memory_age = time.time() - self.memory_cached_at
        if memory_age > MEMORY_CACHE_TTL_SECONDS:
            return False, f"memory cache stale ({memory_age:.0f}s > {MEMORY_CACHE_TTL_SECONDS}s)"
        
        return True, "valid"
    
    def to_metadata_dict(self):
        """Convert to metadata dictionary (for compatibility)."""
        return {
            'url': self.url,
            'cached_at': self.cached_at,
            'size': self.size,
            'version': self.version,
            'etag': self.etag,
            'last_modified': self.last_modified,
            'cache_control': self.cache_control
        }


def get_memory_cache_size():
    """Get current memory cache size in bytes."""
    total = 0
    for cached_file in MEMORY_CACHE.values():
        total += cached_file.size
    return total


def evict_from_memory_cache():
    """
    Evict least recently used items from memory cache to stay under size limit.
    Uses simple FIFO eviction (first in, first out).
    """
    max_size_bytes = MEMORY_CACHE_MAX_SIZE_MB * 1024 * 1024
    
    # Sort by memory_cached_at (oldest first)
    items = sorted(MEMORY_CACHE.items(), key=lambda x: x[1].memory_cached_at)
    
    while get_memory_cache_size() > max_size_bytes and items:
        filename, cached_file = items.pop(0)
        del MEMORY_CACHE[filename]
        logger.info(f"[MEMORY EVICT] {filename} ({format_bytes(cached_file.size)})")


def get_file_lock(filename):
    """
    Get or create a lock for a specific file.
    Thread-safe way to ensure only one thread accesses a file at a time.
    """
    with CACHE_LOCKS_LOCK:
        if filename not in CACHE_LOCKS:
            CACHE_LOCKS[filename] = threading.Lock()
        return CACHE_LOCKS[filename]


def acquire_file_lock(file_path, timeout=30):
    """
    Acquire an exclusive lock on a file using fcntl (Unix/Linux/macOS).
    
    Args:
        file_path: Path to the file to lock
        timeout: Maximum time to wait for lock (seconds)
    
    Returns:
        file object with lock acquired, or None if timeout
    """
    try:
        lock_file = open(file_path + '.lock', 'w')
        start_time = time.time()
        
        while True:
            try:
                # Try to acquire exclusive lock (non-blocking)
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return lock_file
            except IOError:
                # Lock is held by another process/thread
                if time.time() - start_time > timeout:
                    logger.warning(f"[LOCK TIMEOUT] Could not acquire lock for {file_path}")
                    lock_file.close()
                    return None
                time.sleep(0.1)  # Wait a bit before retrying
    except Exception as e:
        logger.error(f"[LOCK ERROR] Failed to acquire lock for {file_path}: {e}")
        return None


def release_file_lock(lock_file):
    """Release file lock and close lock file."""
    if lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
            # Clean up lock file
            if os.path.exists(lock_file.name):
                os.remove(lock_file.name)
        except Exception as e:
            logger.error(f"[LOCK RELEASE ERROR] {e}")


def extract_version_from_url(url):
    """
    Extract version identifier from URL by getting the parent folder path.
    
    This approach is more robust than pattern matching because it works
    regardless of Google's naming conventions.
    
    Example URLs:
    https://www.gstatic.com/acx/transparency/report/acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000/main.dart.js
    → Returns: /acx/transparency/report/acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000
    
    https://www.gstatic.com/some/other/path/v2.0/main.dart.js
    → Returns: /some/other/path/v2.0
    
    Returns:
        str: Full path before the filename (version identifier)
             or None if cannot be determined
    """
    from urllib.parse import urlparse
    
    try:
        # Parse the URL
        parsed = urlparse(url)
        
        # Get the path and remove the filename
        # Example: /acx/transparency/report/folder/main.dart.js
        # Result: /acx/transparency/report/folder
        path = parsed.path
        
        if '/main.dart.js' in path:
            # Remove everything from /main.dart.js onwards
            version_path = path.rsplit('/main.dart.js', 1)[0]
            return version_path
        
        # Fallback: just remove the last path component (filename)
        path_parts = path.rsplit('/', 1)
        return path_parts[0] if len(path_parts) > 1 else None
        
    except Exception as e:
        logger.warning(f"[VERSION EXTRACT ERROR] Failed to extract version from {url}: {e}")
        return None


def get_cache_filename(url):
    """
    Generate a cache filename from a URL.
    
    Examples:
        main.dart.js -> main.dart.js
        main.dart.js_2.part.js -> main.dart.js_2.part.js
        main.dart.js_40.part.js -> main.dart.js_40.part.js
    """
    # Extract the filename from URL
    parts = url.split('/')
    filename = parts[-1]
    
    # Remove query parameters
    if '?' in filename:
        filename = filename.split('?')[0]
    
    return filename


def get_version_tracking_path():
    """Get full path to version tracking file."""
    return os.path.join(CACHE_DIR, VERSION_TRACKING_FILE)


def load_version_tracking():
    """
    Load version tracking data from disk (thread-safe).
    
    Returns:
        dict: Mapping of filename -> version info
              Example: {'main.dart.js': {'version': 'frontend_auto_20251020-0645_RC000', 'url': '...'}}
    """
    with VERSION_TRACKING_LOCK:
        tracking_path = get_version_tracking_path()
        
        if not os.path.exists(tracking_path):
            return {}
        
        try:
            with open(tracking_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[VERSION TRACKING] Failed to load tracking file: {e}")
            return {}


def save_version_tracking(tracking_data):
    """
    Save version tracking data to disk (thread-safe with atomic write).
    
    Args:
        tracking_data: dict mapping filename -> version info
    """
    with VERSION_TRACKING_LOCK:
        tracking_path = get_version_tracking_path()
        
        try:
            # Atomic write: write to temp file, then rename
            temp_path = tracking_path + '.tmp'
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(tracking_data, f, indent=2)
            
            os.replace(temp_path, tracking_path)
        except Exception as e:
            logger.error(f"[VERSION TRACKING] Failed to save tracking file: {e}")
            # Clean up temp file if it exists
            temp_path = tracking_path + '.tmp'
            if os.path.exists(temp_path):
                os.remove(temp_path)


def check_version_changed(url):
    """
    Check if the URL version has changed compared to cached version.
    
    Args:
        url: The URL to check
    
    Returns:
        tuple: (version_changed: bool, current_version: str, cached_version: str or None)
    """
    if not VERSION_AWARE_CACHING:
        return False, None, None
    
    filename = get_cache_filename(url)
    current_version = extract_version_from_url(url)
    
    if not current_version:
        # Can't determine version, assume no change
        return False, None, None
    
    tracking_data = load_version_tracking()
    
    if filename not in tracking_data:
        # First time seeing this file
        return False, current_version, None
    
    cached_version = tracking_data[filename].get('version')
    
    if cached_version != current_version:
        logger.warning(f"[VERSION CHANGE] {filename}: {cached_version} -> {current_version}")
        return True, current_version, cached_version
    
    return False, current_version, cached_version


def update_version_tracking(url):
    """
    Update version tracking for a URL.
    
    Args:
        url: The URL that was cached
    """
    if not VERSION_AWARE_CACHING:
        return
    
    filename = get_cache_filename(url)
    version = extract_version_from_url(url)
    
    if not version:
        return
    
    tracking_data = load_version_tracking()
    
    tracking_data[filename] = {
        'version': version,
        'url': url,
        'updated_at': time.time()
    }
    
    save_version_tracking(tracking_data)
    logger.info(f"[VERSION TRACKING] Updated {filename} -> {version}")


async def save_to_cache(url, content, headers=None):
    """
    Save content to cache (both memory and disk) - thread-safe.
    
    Write-through cache: saves to both L1 (memory) and L2 (disk).
    
    Args:
        url: The URL being cached
        content: The file content
        headers: Optional response headers (for ETag, Last-Modified)
    """
    filename = get_cache_filename(url)
    cache_path = os.path.join(CACHE_DIR, filename)
    
    # Acquire thread lock for this specific file
    file_lock = get_file_lock(filename)
    
    with file_lock:
        # Acquire file system lock
        lock_file = acquire_file_lock(cache_path)
        
        try:
            metadata_path = os.path.join(CACHE_DIR, f"{filename}.meta.json")
            
            # Extract version info
            version = extract_version_from_url(url)
            
            # Save content atomically to disk (write to temp file, then rename)
            temp_path = cache_path + '.tmp'
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Atomic rename (prevents partial reads)
            os.replace(temp_path, cache_path)
            
            # Save metadata to disk
            metadata = {
                'url': url,
                'cached_at': time.time(),
                'size': len(content),
                'version': version,
                'etag': headers.get('etag') if headers else None,
                'last_modified': headers.get('last-modified') if headers else None,
                'cache_control': headers.get('cache-control') if headers else None
            }
            
            temp_meta_path = metadata_path + '.tmp'
            with open(temp_meta_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            # Atomic rename
            os.replace(temp_meta_path, metadata_path)
            
            # Update version tracking
            update_version_tracking(url)
            
            # Store in memory cache (L1)
            with MEMORY_CACHE_LOCK:
                # Check if we need to evict old items
                if get_memory_cache_size() + len(content) > MEMORY_CACHE_MAX_SIZE_MB * 1024 * 1024:
                    evict_from_memory_cache()
                
                # Create cached file object
                cached_file = CachedFile(url=url, content=content, headers=headers)
                MEMORY_CACHE[filename] = cached_file
            
            logger.info(f"[CACHE SAVE] {filename} ({format_bytes(len(content))}, version: {version}) → disk + memory")
            return True
            
        except Exception as e:
            logger.error(f"[CACHE SAVE ERROR] Failed to save to cache: {e}")
            # Clean up temp files if they exist
            temp_path = cache_path + '.tmp'
            temp_meta_path = metadata_path + '.tmp'
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(temp_meta_path):
                os.remove(temp_meta_path)
            return False
            
        finally:
            release_file_lock(lock_file)


def load_from_cache(url):
    """
    Load content from cache (L1: memory, L2: disk) - thread-safe.
    
    Two-level cache:
    1. Check memory cache (0.001ms) - includes all metadata
    2. Check disk cache (5ms) - slower but persistent
    
    Cache is valid only if:
    - Version matches (URL path unchanged) AND
    - Age < CACHE_MAX_AGE_HOURS
    
    Returns:
        tuple: (content, metadata) or (None, None) if not found/invalid
    """
    filename = get_cache_filename(url)
    
    # L1: Try memory cache first (fastest - no file I/O)
    with MEMORY_CACHE_LOCK:
        if filename in MEMORY_CACHE:
            cached_file = MEMORY_CACHE[filename]
            is_valid, reason = cached_file.is_valid(url)
            
            if is_valid:
                # Memory cache hit - instant return!
                age_hours = (time.time() - cached_file.cached_at) / 3600
                logger.info(f"[MEMORY HIT] {filename} ({format_bytes(cached_file.size)}, age: {age_hours:.1f}h)")
                return cached_file.content, cached_file.to_metadata_dict()
            else:
                # Invalid - remove from memory
                logger.info(f"[MEMORY INVALIDATE] {filename}: {reason}")
                del MEMORY_CACHE[filename]
                # Fall through to disk check
    
    # L2: Try disk cache (slower but persistent)
    cache_path = os.path.join(CACHE_DIR, filename)
    
    # Acquire thread lock for disk access
    file_lock = get_file_lock(filename)
    
    with file_lock:
        try:
            metadata_path = os.path.join(CACHE_DIR, f"{filename}.meta.json")
            
            if not os.path.exists(cache_path):
                return None, None
            
            # Load metadata
            metadata = None
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            
            should_invalidate = False
            invalidation_reason = None
            
            # Check 1: Version validation
            if VERSION_AWARE_CACHING:
                version_changed, current_version, cached_version = check_version_changed(url)
                if version_changed:
                    should_invalidate = True
                    invalidation_reason = f"version changed: {cached_version} → {current_version}"
                    logger.warning(f"[VERSION MISMATCH] {filename}: cached={cached_version}, current={current_version}")
            
            # Check 2: Age validation
            if not should_invalidate and metadata and CACHE_MAX_AGE_HOURS > 0:
                cached_at = metadata.get('cached_at', 0)
                age_hours = (time.time() - cached_at) / 3600
                
                if age_hours > CACHE_MAX_AGE_HOURS:
                    should_invalidate = True
                    invalidation_reason = f"age {age_hours:.1f}h > max {CACHE_MAX_AGE_HOURS}h"
                    logger.warning(f"[CACHE EXPIRED] {filename} is {age_hours:.1f} hours old (max: {CACHE_MAX_AGE_HOURS}h)")
            
            # Invalidate if needed
            if should_invalidate:
                logger.info(f"[DISK INVALIDATE] Removing {filename}: {invalidation_reason}")
                
                # Delete old cache files
                try:
                    if os.path.exists(cache_path):
                        os.remove(cache_path)
                    if os.path.exists(metadata_path):
                        os.remove(metadata_path)
                except Exception as e:
                    logger.error(f"[CACHE CLEANUP ERROR] Failed to remove old cache: {e}")
                
                return None, None
            
            # Load content from disk
            with open(cache_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Store in memory cache for next time
            with MEMORY_CACHE_LOCK:
                # Check if we need to evict old items
                if get_memory_cache_size() + len(content) > MEMORY_CACHE_MAX_SIZE_MB * 1024 * 1024:
                    evict_from_memory_cache()
                
                # Create cached file object
                cached_file = CachedFile(
                    url=url,
                    content=content,
                    headers={
                        'etag': metadata.get('etag'),
                        'last-modified': metadata.get('last_modified'),
                        'cache-control': metadata.get('cache_control')
                    } if metadata else None,
                    disk_cached_at=metadata.get('cached_at') if metadata else None
                )
                
                MEMORY_CACHE[filename] = cached_file
                age_hours = (time.time() - cached_file.cached_at) / 3600
                logger.info(f"[DISK HIT] {filename} ({format_bytes(len(content))}, age: {age_hours:.1f}h) → stored in memory")
            
            return content, metadata
            
        except Exception as e:
            logger.error(f"[CACHE LOAD ERROR] Failed to load from cache: {e}")
            return None, None


async def validate_cache_with_server(url, metadata):
    """
    Validate cached file with server using ETag or Last-Modified.
    
    Args:
        url: The URL to validate
        metadata: Cache metadata with etag/last-modified
    
    Returns:
        bool: True if cache is still valid, False if needs refresh
    """
    # This is a placeholder for conditional request validation
    # In a full implementation, you would make a HEAD request with:
    # - If-None-Match: <etag>
    # - If-Modified-Since: <last-modified>
    # And check if server returns 304 Not Modified
    
    # For now, we rely on age-based expiration
    return True


def get_cache_status():
    """
    Get status of all cached files with version tracking.
    
    Returns:
        list: List of dicts with cache file information
    """
    cache_files = []
    
    if not os.path.exists(CACHE_DIR):
        return cache_files
    
    # Load version tracking data
    version_tracking = load_version_tracking()
    
    for filename in os.listdir(CACHE_DIR):
        if filename.endswith('.meta.json') or filename == VERSION_TRACKING_FILE:
            continue
        
        file_path = os.path.join(CACHE_DIR, filename)
        meta_path = os.path.join(CACHE_DIR, f"{filename}.meta.json")
        
        if not os.path.isfile(file_path):
            continue
        
        file_info = {
            'filename': filename,
            'size': os.path.getsize(file_path),
            'has_metadata': os.path.exists(meta_path)
        }
        
        # Load metadata if exists
        if file_info['has_metadata']:
            try:
                with open(meta_path, 'r') as f:
                    metadata = json.load(f)
                
                cached_at = metadata.get('cached_at', 0)
                age_hours = (time.time() - cached_at) / 3600
                
                file_info.update({
                    'cached_at': cached_at,
                    'age_hours': age_hours,
                    'expired': age_hours > CACHE_MAX_AGE_HOURS if CACHE_VALIDATION_ENABLED else False,
                    'version': metadata.get('version'),
                    'etag': metadata.get('etag'),
                    'last_modified': metadata.get('last_modified'),
                    'url': metadata.get('url')
                })
            except:
                pass
        
        # Add version tracking info
        if filename in version_tracking:
            file_info['tracked_version'] = version_tracking[filename].get('version')
        
        cache_files.append(file_info)
    
    return sorted(cache_files, key=lambda x: x.get('cached_at', 0), reverse=True)


def create_route_handler(network_logger):
    """
    Create route handler for URL and resource type blocking.
    
    Blocks images, fonts, stylesheets, and URLs matching configured patterns
    to optimize bandwidth usage during debugging.
    
    Also intercepts main.dart.js and serves from local cache if enabled.
    """
    async def handle_route(route):
        url = route.request.url
        resource_type = route.request.resource_type
        
        # PRIORITY 1: Smart caching for main.dart.js files (including part files)
        if USE_LOCAL_CACHE_FOR_MAIN_DART and MAIN_DART_JS_URL_PATTERN in url:
            try:
                # Try to load from cache first
                cached_content, metadata = load_from_cache(url)
                
                if cached_content:
                    # Cache hit - serve from local cache
                    await route.fulfill(
                        status=200,
                        headers={
                            'Content-Type': 'text/javascript',
                            'Cache-Control': 'public, max-age=86400',
                            'X-Served-From': 'local-cache',
                            'X-Cache-Age-Hours': f"{(time.time() - metadata.get('cached_at', 0)) / 3600:.1f}" if metadata else '0',
                            'Access-Control-Allow-Origin': '*'
                        },
                        body=cached_content
                    )
                    
                    network_logger.cache_hit_count += 1
                    filename = get_cache_filename(url)
                    age_hours = (time.time() - metadata.get('cached_at', 0)) / 3600 if metadata else 0
                    logger.info(f"[CACHE HIT] Served {filename} from cache ({len(cached_content)} bytes, age: {age_hours:.1f}h)")
                    
                    # Log as allowed request (served from cache)
                    request = route.request
                    matching_req = next((r for r in network_logger.requests_summary if r['url'] == url), None)
                    if matching_req:
                        network_logger.log_allowed_request(url, request.method, request.resource_type, matching_req['index'])
                    return
                else:
                    # Cache miss or expired - download and cache
                    if AUTO_CACHE_ON_MISS:
                        filename = get_cache_filename(url)
                        logger.info(f"[CACHE MISS] {filename} not in cache or expired, downloading...")
                        
                        # Let the request go through, but intercept the response
                        response = await route.fetch()
                        body = await response.text()
                        
                        # Save to cache with metadata
                        await save_to_cache(url, body, dict(response.headers))
                        
                        # Forward the response
                        await route.fulfill(
                            status=response.status,
                            headers=dict(response.headers),
                            body=body
                        )
                        
                        # Log as allowed request (downloaded and cached)
                        request = route.request
                        matching_req = next((r for r in network_logger.requests_summary if r['url'] == url), None)
                        if matching_req:
                            network_logger.log_allowed_request(url, request.method, request.resource_type, matching_req['index'])
                        return
                    else:
                        # Just let it through without caching
                        filename = get_cache_filename(url)
                        logger.info(f"[CACHE MISS] {filename} not in cache, loading from network")
                        await route.continue_()
                        return
                        
            except Exception as e:
                logger.error(f"[CACHE ERROR] Failed to handle cache: {e}")
                # Fall through to normal request
        
        # Skip blocking if disabled
        if not ENABLE_BLOCKING:
            await route.continue_()
            return
        
        # Block images, fonts, and stylesheets to reduce bandwidth
        if resource_type in BLOCKED_RESOURCE_TYPES:
            network_logger.blocked_count += 1
            network_logger.blocked_urls.append((url, f'{resource_type} (resource type)'))
            await route.abort()
            return
        
        # Block specific URL patterns
        should_block = False
        pattern_matched = None
        
        for pattern in BLOCKED_URL_PATTERNS:
            if pattern in url:
                should_block = True
                pattern_matched = pattern
                break
        
        # Special handling for gstatic.com - selective blocking
        if 'gstatic.com' in url:
            # Only block specific problematic paths
            if any(gstatic_pattern in url for gstatic_pattern in GSTATIC_BLOCKED_PATTERNS):
                network_logger.blocked_count += 1
                network_logger.blocked_urls.append((url, 'gstatic.com (selective)'))
                await route.abort()
                return
            # Allow other gstatic content
            should_block = False
        
        if should_block:
            network_logger.blocked_count += 1
            network_logger.blocked_urls.append((url, pattern_matched))
            await route.abort()
        else:
            # Log this as an allowed request (not blocked)
            # We need to get the request info from the route
            request = route.request
            # Find the index from requests_summary
            matching_req = next((r for r in network_logger.requests_summary if r['url'] == url), None)
            if matching_req:
                network_logger.log_allowed_request(url, request.method, request.resource_type, matching_req['index'])
            await route.continue_()
    
    return handle_route


async def setup_proxy():
    """
    Setup mitmproxy for accurate traffic measurement.
    
    Returns:
        tuple: (proxy_process, use_proxy_flag)
            - proxy_process: subprocess.Popen object if mitmproxy started, None otherwise
            - use_proxy_flag: Boolean indicating if proxy is active
    """
    if not USE_MITMPROXY:
        return None, False
    
    logger.info("🔧 Starting mitmproxy...")
    
    # Write mitmproxy addon script to temporary file
    with open(MITM_ADDON_PATH, 'w') as f:
        f.write(PROXY_ADDON_SCRIPT)
    
    # Remove old results file if exists
    if os.path.exists(PROXY_RESULTS_PATH):
        os.remove(PROXY_RESULTS_PATH)
    
    # Try to find mitmdump executable
    mitmdump_cmd = None
    for path in MITMDUMP_SEARCH_PATHS:
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
        logger.info("✓ Mitmproxy started")
        return proxy_process, True
    else:
        logger.warning("⚠ mitmproxy not found, using estimation mode")
        return None, False


async def teardown_proxy(proxy_process):
    """
    Stop mitmproxy and read traffic results.
    
    Args:
        proxy_process: subprocess.Popen object from setup_proxy()
    
    Returns:
        dict: Proxy traffic results or None if no proxy was used
    """
    if not proxy_process:
        return None
    
    logger.info("🔧 Stopping proxy...")
    proxy_process.send_signal(signal.SIGTERM)
    
    try:
        proxy_process.wait(timeout=PROXY_TERMINATION_TIMEOUT)
    except subprocess.TimeoutExpired:
        logger.warning("⚠️  Proxy did not terminate gracefully, forcing kill...")
        proxy_process.kill()
    
    await asyncio.sleep(PROXY_SHUTDOWN_WAIT)
    
    # Read proxy results
    if os.path.exists(PROXY_RESULTS_PATH):
        with open(PROXY_RESULTS_PATH, 'r') as f:
            return json.load(f)
    
    return None


def format_bytes(bytes_value):
    """Format bytes into human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} TB"


async def main():
    """Main function to run the network logging script."""
    
    target_url = "https://adstransparency.google.com/advertiser/AR08722290881173913601/creative/CR13612220978573606913?region=anywhere&platform=YOUTUBE"
    
    # Clear old session folders before starting
    logger.info("="*80)
    logger.info("Cleaning up old session folders...")
    logger.info("="*80)
    
    if os.path.exists(TEMP_DIR):
        import shutil
        for item in os.listdir(TEMP_DIR):
            item_path = os.path.join(TEMP_DIR, item)
            if os.path.isdir(item_path) and item.startswith('session_'):
                try:
                    shutil.rmtree(item_path)
                    logger.info(f"Removed old session: {item}")
                except Exception as e:
                    logger.warning(f"Could not remove {item}: {e}")
    
    logger.info("\n" + "="*80)
    logger.info("Starting Playwright Network Logger")
    logger.info(f"Target URL: {target_url}")
    if USE_MITMPROXY:
        logger.info("Traffic Measurement: MITMPROXY (precise)")
    else:
        logger.info("Traffic Measurement: ESTIMATION (Content-Length headers)")
    
    # Display cache status
    if USE_LOCAL_CACHE_FOR_MAIN_DART:
        cache_files = get_cache_status()
        if cache_files:
            logger.info(f"\nCache Status: {len(cache_files)} file(s) cached")
            for cf in cache_files:
                age = cf.get('age_hours', 0)
                expired_marker = " [EXPIRED]" if cf.get('expired', False) else ""
                version = cf.get('version', 'unknown')
                version_short = version[-20:] if version and len(version) > 20 else version
                logger.info(f"  - {cf['filename']}: {format_bytes(cf['size'])}, age: {age:.1f}h, v:{version_short}{expired_marker}")
        else:
            logger.info("\nCache Status: Empty (files will be downloaded)")
    
    logger.info("="*80)
    
    # Setup proxy if enabled
    proxy_process, use_proxy = await setup_proxy()
    proxy_results = None
    start_time = time.time()
    
    try:
        async with async_playwright() as p:
            # Launch browser in headless mode
            browser = await p.chromium.launch(
                headless=True,  # Headless mode for faster execution
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox'
                ]
            )
            
            # Create context with realistic settings (and proxy if enabled)
            context_options = {
                'viewport': {'width': 1920, 'height': 1080},
                'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'locale': 'en-US',
                'timezone_id': 'America/New_York',
                'ignore_https_errors': use_proxy  # Ignore HTTPS errors when using proxy
            }
            
            if use_proxy:
                context_options['proxy'] = {"server": MITMPROXY_SERVER_URL}
            
            context = await browser.new_context(**context_options)
            
            # Initialize network logger with context for cookie access
            network_logger = NetworkLogger(TEMP_DIR, context)
            
            # Log initial cookies
            await network_logger._log_cookies("Initial state (before navigation)")
            
            # Create route handler for blocking
            route_handler = create_route_handler(network_logger)
            await context.route('**/*', route_handler)
            
            page = await context.new_page()
            
            # Set up network event listeners
            page.on('request', lambda request: network_logger.log_request(request))
            page.on('response', lambda response: asyncio.create_task(network_logger.log_response(response)))
            
            logger.info("\nNavigating to target URL...")
            
            try:
                # Navigate to the page
                response = await page.goto(target_url, wait_until='networkidle', timeout=60000)
                logger.info(f"\nPage loaded with status: {response.status}")
                
                # Wait a bit more to capture any delayed requests
                logger.info("\nWaiting 5 seconds to capture additional network activity...")
                await asyncio.sleep(5)
                
                # Try scrolling to trigger any lazy-loaded content
                logger.info("\nScrolling page to trigger lazy-loaded content...")
                try:
                    await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1)
                except Exception as scroll_error:
                    logger.warning(f"Scroll error (non-critical): {scroll_error}")
                
                logger.info("\nCapture complete!")
                
            except Exception as e:
                logger.error(f"Error during page navigation: {e}")
            
            finally:
                # Log final cookies state
                await network_logger._log_cookies("Final state (after all activity)")
                
                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000
                
                # Save all logs
                logger.info("\n" + "="*80)
                logger.info("Saving network logs...")
                logger.info("="*80)
                
                session_dir, urls_file, summary_file = network_logger.save_logs()
                
                await browser.close()
    
    finally:
        # Stop proxy and get results
        proxy_results = await teardown_proxy(proxy_process)
    
    # Determine traffic measurement
    if proxy_results:
        incoming_bytes = proxy_results['total_response_bytes']
        outgoing_bytes = proxy_results['total_request_bytes']
        total_bytes = proxy_results['total_bytes']
        measurement_method = 'proxy (precise)'
    else:
        # Estimation mode - we don't have byte tracking in NetworkLogger yet
        # This would need to be added similar to TrafficTracker in google_ads_transparency_scraper.py
        incoming_bytes = 0
        outgoing_bytes = 0
        total_bytes = 0
        measurement_method = 'estimation (not implemented)'
    
    # Print final summary with traffic stats
    logger.info("\n" + "="*80)
    logger.info("FINAL SUMMARY")
    logger.info("="*80)
    logger.info(f"Total Requests: {network_logger.request_count}")
    logger.info(f"Total Responses: {network_logger.response_count}")
    logger.info(f"Cache Hits: {network_logger.cache_hit_count}")
    if USE_LOCAL_CACHE_FOR_MAIN_DART:
        logger.info(f"  - Local cache: ENABLED (main.dart.js)")
    logger.info(f"Blocked Requests: {network_logger.blocked_count}")
    if ENABLE_BLOCKING:
        logger.info(f"  - Blocking: ENABLED")
        if network_logger.blocked_count > 0:
            blocking_rate = (network_logger.blocked_count / (network_logger.request_count + network_logger.blocked_count) * 100)
            logger.info(f"  - Blocking rate: {blocking_rate:.1f}%")
    else:
        logger.info(f"  - Blocking: DISABLED")
    
    # Traffic statistics
    logger.info(f"\nTraffic Statistics:")
    logger.info(f"  - Measurement method: {measurement_method}")
    if proxy_results:
        logger.info(f"  - Incoming: {format_bytes(incoming_bytes)}")
        logger.info(f"  - Outgoing: {format_bytes(outgoing_bytes)}")
        logger.info(f"  - Total: {format_bytes(total_bytes)}")
        logger.info(f"  - Duration: {duration_ms:.0f} ms")
    
    logger.info(f"\nSession directory: {session_dir}")
    logger.info(f"  - URLs summary: {urls_file}")
    logger.info(f"  - Session summary: {summary_file}")
    logger.info(f"  - Individual request-response files: {network_logger.request_count} files")
    logger.info("="*80)
    
    logger.info("\nScript completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())

