"""
Cache configuration and constants.
"""

import os

# Script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Cache directory
CACHE_DIR = os.path.join(SCRIPT_DIR, 'main.dart')
os.makedirs(CACHE_DIR, exist_ok=True)

# Cache settings
USE_LOCAL_CACHE_FOR_MAIN_DART = True
MAIN_DART_JS_URL_PATTERN = 'main.dart.js'
AUTO_CACHE_ON_MISS = True

# Cache expiration
CACHE_MAX_AGE_HOURS = 24
VERSION_AWARE_CACHING = True
VERSION_TRACKING_FILE = 'cache_versions.json'

# Memory cache settings
MEMORY_CACHE_MAX_SIZE_MB = 100
MEMORY_CACHE_TTL_SECONDS = 300  # 5 minutes

# Blocking configuration
ENABLE_BLOCKING = True

BLOCKED_URL_PATTERNS = [
    'qs_click_protection.js',
    'google-analytics.com',
    'GetAdvertiserDunsMapping?authuser=',
    'youtube.com/',
    'googlesyndication.com',
    'apis.google.com/',
    '/adframe',
    'googletagmanager.com/gtag/js?',
    'logging?authuser=',
    "images/flags/",
    "googleapis.com/css?",
    "SearchService/SearchCreatives?authuser"
]

GSTATIC_BLOCKED_PATTERNS = [
    '/images/',
    '/clarity/',
    '/_/js/k=og.qtm',
    '/_/ss/k=og.qtm',
    "prod/api/main.min.js",
    "prod/service/lazy.min.js"
]

BLOCKED_RESOURCE_TYPES = ['image', 'font', 'stylesheet']

# Mitmproxy configuration
USE_MITMPROXY = True
MITMPROXY_PORT = '8080'
MITMPROXY_SERVER_URL = 'http://localhost:8080'
MITM_ADDON_PATH = '/tmp/mitm_addon_fighting_cache.py'
PROXY_RESULTS_PATH = '/tmp/proxy_results_fighting_cache.json'
MITMDUMP_SEARCH_PATHS = [
    'mitmdump',
    '/usr/local/bin/mitmdump',
    '/Users/rostoni/Library/Python/3.9/bin/mitmdump'
]

PROXY_STARTUP_WAIT = 3
PROXY_SHUTDOWN_WAIT = 1
PROXY_TERMINATION_TIMEOUT = 10
SUBPROCESS_VERSION_CHECK_TIMEOUT = 1

