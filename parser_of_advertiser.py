#!/usr/bin/env python3
"""
Google Ads Transparency Center - Stress Test Scraper (OPTIMIZED with Session Reuse)

This script performs continuous concurrent stress testing using a worker pool pattern
with bandwidth optimization through session reuse.

OPTIMIZATION STRATEGY:
- Each worker processes batches of 20 creatives
- First creative: Full HTML load (524 KB) + extract cookies
- Creatives 2-20: API-only with gzip compression (179 KB each)
- Average: 181 KB per creative (65% bandwidth savings)

For 1000 creatives:
- Original: 524 MB
- Optimized: 181 MB
- Savings: 343 MB (65%)

Features:
- Batch processing (20 creatives per batch, session reuse)
- Continuous worker pool (no idle time between batches)
- Configurable concurrency limit
- Reads creative URLs from PostgreSQL creatives_fresh table
- Updates database with results (videos, app store ID, funded_by, errors)
- Real-time progress logging with rate statistics
- Static proxy support with IP logging
- Cache statistics tracking (hit rate, bytes saved)
- Real-time cache performance monitoring

Usage:
    # Process all pending URLs with 10 concurrent workers (each processes batches of 20)
    python3 stress_test_scraper_optimized.py --max-concurrent 10
    
    # Process 100 URLs with 20 concurrent workers
    python3 stress_test_scraper_optimized.py --max-concurrent 20 --max-urls 100
    
    # Without proxy
    python3 stress_test_scraper_optimized.py --max-concurrent 10 --no-proxy
    
    # With IP rotation enabled
    python3 stress_test_scraper_optimized.py --max-concurrent 10 --enable-rotation
"""

import asyncio
import sys
import psycopg2
import argparse
import time
import json
import traceback
from datetime import datetime
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
from pathlib import Path

try:
    import httpx
except ImportError as e:
    print("ERROR: Missing dependencies")
    print("Install: pip install httpx")
    sys.exit(1)

# Import scraping functions from optimized scraper
try:
    from google_ads_transparency_scraper_optimized import (
        scrape_ads_transparency_page,  # For first creative in batch
        scrape_ads_transparency_api_only  # For remaining 19 creatives
    )
    from google_ads_traffic import TrafficTracker
    from google_ads_browser import (
        _setup_browser_context,
        _create_route_handler,
        _create_response_handler
    )
    from google_ads_cache import (
        create_cache_aware_route_handler,
        get_cache_statistics,
        reset_cache_statistics
    )
    from google_ads_content import (
        _smart_wait_for_content,
        _identify_creative,
        _extract_data
    )
    from google_ads_api_analysis import (
        check_if_static_cached_creative,
        extract_funded_by_from_api
    )
    from google_ads_config import ENABLE_STEALTH_MODE
    from playwright.async_api import async_playwright
except ImportError as e:
    print(f"ERROR: Could not import required functions: {e}")
    print("Make sure google_ads_transparency_scraper_optimized.py is in the same directory")
    sys.exit(1)

# Stealth mode support
try:
    from playwright_stealth import Stealth
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

# ============================================================================
# CONFIGURATION
# ============================================================================

# Debug Configuration
DEBUG_FOLDER = "debug"
ENABLE_DEBUG_LOGGING = True  # Set to False to disable all debug logging

# Fixed URL for testing (advertiser page, not creative page)
FIXED_TEST_URL = "https://adstransparency.google.com/advertiser/AR05226884764400615425?region=US"

# PostgreSQL Database Configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432
}

# Proxy Configuration (optional - if not provided, uses no proxy)
# Multiple proxies with round-robin rotation support
PROXIES = [
    {
        "host": "hub-us-8.litport.net",
        "port": 31337,  # HTTPS port
        "username": "7zQu8tyk",
        "password": "l0n7LLeQiA"
    },
    {
        "host": "hub-us-8.litport.net",
        "port": 31337,  # HTTPS port
        "username": "cVlcv0AB",
        "password": "867hnC5x8d"
    },
    {
        "host": "hub-us-8.litport.net",
        "port": 31337,  # HTTPS port
        "username": "pGz76T35",
        "password": "mo43glLtIBV"
    },
    {
        "host": "hub-us-8.litport.net",
        "port": 31337,  # HTTPS port
        "username": "U62PUg",
        "password": "6RJqlSRS30f"
    },
    {
        "host": "hub-us-8.litport.net",
        "port": 31337,  # HTTPS port
        "username": "3j7Uzah",
        "password": "4kUYVNQ0RJ"
    },
    {
        "host": "hub-us-10.litport.net",
        "port": 31337,  # HTTPS port
        "username": "1YAXY4",
        "password": "GuLy3fvu6d"
    }
    # Add more proxies here as needed
    # {
    #     "host": "hub-us-9.litport.net",
    #     "port": 31337,
    #     "username": "username2",
    #     "password": "password2"
    # },
]


# IP Rotation Configuration
IPROYAL_ROTATE_URL = "https://apid.iproyal.com/v1/orders/59934727/rotate-ip/9vZGSTaLoF"
ROTATION_COOLDOWN_SECONDS = 420  # 7 minutes
ROTATION_STABILIZATION_SECONDS = 30  # Wait 30s after rotation before starting workers

# Stress Test Configuration
DEFAULT_MAX_CONCURRENT = 3   # Default number of concurrent workers (reduced to avoid rate limits)
                                # Each worker creates a separate browser session with its own cookies
                                # 3 workers = 3 concurrent sessions hitting Google
DEFAULT_BATCH_SIZE = 20      # Default number of creatives per batch (1 HTML + 9 API-only)
                                # Each batch gets a NEW browser session = NEW cookies
                                # Smaller batches = less requests per session burst

# Delay Configuration (to avoid rate limiting)
DELAY_BETWEEN_CREATIVES = 0.5     # Delay between processing creatives in a batch (seconds)
DELAY_BEFORE_API_CALL = (0.5, 1.5)    # Random delay before GetCreativeById API call (min, max seconds)
DELAY_BETWEEN_CONTENTJS = (0.5, 1.5)  # Random delay between content.js fetches (min, max seconds)

# Global state for IP rotation
_last_rotation_time: Optional[float] = None
_rotation_in_progress: bool = False
_active_workers_count: int = 0
_workers_lock = None  # Will be initialized in async context


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

def generate_transparency_url(advertiser_id: str, creative_id: str) -> str:
    """
    Generate Google Ads Transparency Center URL.
    
    Args:
        advertiser_id: Advertiser ID (format: AR...)
        creative_id: Creative ID (format: CR...)
        
    Returns:
        Full URL to creative page
        
    Example:
        >>> generate_transparency_url("AR00903679020502089729", "CR00096655163799896065")
        'https://adstransparency.google.com/advertiser/AR00903679020502089729/creative/CR00096655163799896065?region=anywhere'
    """
    return f"https://adstransparency.google.com/advertiser/{advertiser_id}/creative/{creative_id}?region=anywhere"


@contextmanager
def get_db_connection():
    """Context manager for PostgreSQL database connections."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def get_pending_urls(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get pending URLs from PostgreSQL creatives_fresh table.
    
    Args:
        limit: Maximum number of URLs to fetch
        
    Returns:
        List of creative dictionaries with URL
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, creative_id, advertiser_id
            FROM creatives_fresh
            WHERE status = 'pending'
            ORDER BY RANDOM()
            LIMIT %s
        """, (limit,))
        
        rows = cursor.fetchall()
        creatives = []
        for row in rows:
            creative = {
                'id': row[0],
                'creative_id': row[1],
                'advertiser_id': row[2]
            }
            # Generate URL from IDs
            creative['url'] = generate_transparency_url(
                creative['advertiser_id'], 
                creative['creative_id']
            )
            creatives.append(creative)
        
        return creatives


def get_pending_batch_and_mark_processing(batch_size: int = None) -> List[Dict[str, Any]]:
    """
    Get a batch of pending creatives and atomically mark them as processing.
    
    Uses SELECT FOR UPDATE SKIP LOCKED to prevent race conditions where multiple
    workers could fetch the same creatives. This ensures each creative is processed
    exactly once, even with multiple concurrent workers.
    
    Thread-safe: Multiple workers can call this concurrently without duplicates.
    
    Args:
        batch_size: Number of creatives to fetch (default: from DEFAULT_BATCH_SIZE config)
        
    Returns:
        List of creative dictionaries with id, creative_id, advertiser_id
        
    How it works:
        1. SELECT ... FOR UPDATE: Locks selected rows exclusively
        2. SKIP LOCKED: Skips rows already locked by other workers
        3. UPDATE + RETURNING: Marks as processing and returns data
        4. Single transaction: SELECT + UPDATE atomic (no race window)
        
    Example:
        Worker 1: Gets creatives 1-20 (locks them)
        Worker 2: Gets creatives 21-40 (skips 1-20, they're locked)
        Worker 3: Gets creatives 41-60 (skips 1-40, they're locked)
        Result: No duplicates, perfect parallelism
    """
    if batch_size is None:
        batch_size = DEFAULT_BATCH_SIZE
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Atomic operation: SELECT + UPDATE in same transaction
        # Uses CTE (WITH clause) for PostgreSQL 9.1+ compatibility
        cursor.execute("""
            WITH selected AS (
                SELECT id, creative_id, advertiser_id
                FROM creatives_fresh
                WHERE status = 'pending'
                ORDER BY RANDOM()
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            )
            UPDATE creatives_fresh
            SET status = 'processing'
            FROM selected
            WHERE creatives_fresh.id = selected.id
            RETURNING creatives_fresh.id, creatives_fresh.creative_id, creatives_fresh.advertiser_id
        """, (batch_size,))
        
        rows = cursor.fetchall()
        conn.commit()  # Commit immediately to release locks
        
        creatives = []
        for row in rows:
            creative = {
                'id': row[0],
                'creative_id': row[1],
                'advertiser_id': row[2]
            }
            creatives.append(creative)
        
        return creatives


def classify_error(error_msg: str) -> tuple[bool, str, str]:
    """
    Classify error type and determine if it should be retried.
    
    Returns:
        Tuple of (should_retry, error_type, error_category)
        - should_retry: True if error should be retried
        - error_type: Short error description for logs
        - error_category: Category for database/stats (retry/bad_ad/failed)
    """
    # Bad ad - creative not found in API (permanent, no retry)
    if 'Creative not found in API' in error_msg:
        return False, 'Creative not found in API', 'bad_ad'
    
    # Legacy support for old error message
    if 'Could not identify real creative ID' in error_msg:
        return False, 'Creative not found in API', 'bad_ad'
    
    # Rate limit errors (retry with exponential backoff)
    if '429' in error_msg or 'Rate limited' in error_msg or 'Too many requests' in error_msg:
        return True, 'Rate limited (429)', 'retry'
    
    # Incomplete fletch-render errors (retry)
    if 'INCOMPLETE:' in error_msg or ('FAILED: Expected' in error_msg and 'content.js' in error_msg):
        return True, 'Incomplete fletch-render', 'retry'
    
    # SSL/TLS errors (retry - often transient)
    if 'SSL' in error_msg or 'TLS' in error_msg or 'EPROTO' in error_msg or 'wrong version number' in error_msg:
        return True, 'SSL/TLS protocol error', 'retry'
    
    # Network/proxy errors (retry)
    network_errors = [
        'ERR_PROXY_CONNECTION_FAILED',
        'ERR_EMPTY_RESPONSE',
        'ERR_CONNECTION_RESET',
        'ERR_TIMED_OUT',
        'ERR_CONNECTION_CLOSED',
        'ERR_CONNECTION_REFUSED',
        'ERR_TUNNEL_CONNECTION_FAILED',
        'TimeoutError',
        'Timeout',
        'BrokenPipeError',
        'socket hang up',           # Playwright network error
        'Socket is closed',         # APIRequestContext socket errors
        'ECONNRESET',               # Node.js connection reset
        'ETIMEDOUT',                # Node.js timeout
        'ECONNREFUSED',             # Node.js connection refused
        'content.js but none received'  # Validation error when all fetches fail
    ]
    
    for err_type in network_errors:
        if err_type in error_msg:
            return True, err_type, 'retry'
    
    # Other failures (permanent, no retry)
    return False, 'Failed', 'failed'


def update_result(creative_id: int, result: Dict[str, Any]):
    """
    Update PostgreSQL creatives_fresh table with scraping result.
    
    Database status handling:
    - Success → status='completed', error_message=NULL
    - Retryable errors (network, incomplete data) → status='pending', error_message="ERROR_TYPE - pending retry"
    - Bad ads (creative not found) → status='bad_ad', error_message="Creative not found in API..."
    - Other permanent errors → status='failed', error_message="PERMANENT ERROR: <full details>"
    
    The PERMANENT ERROR prefix helps identify unexpected failures for debugging.
    Use query_errors.sql to analyze these errors in detail.
    
    Updates the following fields on success:
    - video_count, video_ids, appstore_id, funded_by, scraped_at, error_message
    
    Args:
        creative_id: Database ID of the creative
        result: Scraping result dictionary
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        if result.get('success'):
            cursor.execute("""
                UPDATE creatives_fresh
                SET status = 'completed',
                    video_count = %s,
                    video_ids = %s,
                    appstore_id = %s,
                    funded_by = %s,
                    scraped_at = %s,
                    error_message = NULL
                WHERE id = %s
            """, (
                result.get('video_count', 0),
                json.dumps(result.get('videos', [])),
                result.get('appstore_id'),
                result.get('funded_by'),
                datetime.utcnow(),
                creative_id
            ))
        else:
            error_msg = result.get('error', 'Unknown error')
            should_retry, error_type, error_category = classify_error(error_msg)
            
            if should_retry:
                # Mark as pending for retry (temporary error)
                cursor.execute("""
                    UPDATE creatives_fresh
                    SET status = 'pending',
                        error_message = %s
                    WHERE id = %s
                """, (
                    f"{error_type} - pending retry",
                    creative_id
                ))
            elif error_category == 'bad_ad':
                # Mark as bad_ad - creative doesn't exist (broken creative page, permanent)
                cursor.execute("""
                    UPDATE creatives_fresh
                    SET status = 'bad_ad',
                        error_message = %s,
                        scraped_at = %s
                    WHERE id = %s
                """, (
                    "Creative not found in API - broken/deleted creative page",
                    datetime.utcnow(),
                    creative_id
                ))
            else:
                # Mark as failed (other permanent failure)
                # Store FULL error message with detailed information for debugging
                detailed_error = f"PERMANENT ERROR: {error_msg}"
                cursor.execute("""
                    UPDATE creatives_fresh
                    SET status = 'failed',
                        error_message = %s,
                        scraped_at = %s
                    WHERE id = %s
                """, (
                    detailed_error,
                    datetime.utcnow(),
                    creative_id
                ))
        
        conn.commit()


def get_statistics() -> Dict[str, int]:
    """Get current PostgreSQL creatives_fresh table statistics."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM creatives_fresh")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT status, COUNT(*) FROM creatives_fresh GROUP BY status")
        status_counts = dict(cursor.fetchall())
        
        return {
            'total': total,
            'pending': status_counts.get('pending', 0),
            'processing': status_counts.get('processing', 0),
            'completed': status_counts.get('completed', 0),
            'failed': status_counts.get('failed', 0),
            'bad_ad': status_counts.get('bad_ad', 0)
        }


# ============================================================================
# PROXY UTILITIES
# ============================================================================

class ProxyRotator:
    """
    Thread-safe round-robin proxy rotator.
    
    Each call to get_next_proxy() returns the next proxy in the list,
    cycling through all available proxies.
    """
    def __init__(self, proxies: List[Dict[str, Any]]):
        """
        Initialize proxy rotator.
        
        Args:
            proxies: List of proxy dictionaries with host, port, username, password
        """
        self.proxies = proxies
        self.index = 0
        self.lock = asyncio.Lock()
    
    def get_next_proxy(self) -> Optional[Dict[str, str]]:
        """
        Get next proxy in round-robin fashion (thread-safe, sync version).
        
        Note: Prefer get_next_proxy_async() in async contexts.
        
        Returns:
            Dict with server, username, password or None if no proxies configured
        """
        if not self.proxies:
            return None
        
        # Use threading.Lock for sync access
        import threading
        if not hasattr(self, '_sync_lock'):
            self._sync_lock = threading.Lock()
        
        with self._sync_lock:
            proxy = self.proxies[self.index]
            self.index = (self.index + 1) % len(self.proxies)
            
            return {
                "server": f"http://{proxy['host']}:{proxy['port']}",  # HTTP proxy (works for HTTPS tunneling)
                "username": proxy['username'],
                "password": proxy['password']
            }
    
    async def get_next_proxy_async(self) -> Optional[Dict[str, str]]:
        """
        Get next proxy in round-robin fashion (async, thread-safe).
        
        Returns:
            Dict with server, username, password or None if no proxies configured
        """
        if not self.proxies:
            return None
        
        async with self.lock:
            proxy = self.proxies[self.index]
            self.index = (self.index + 1) % len(self.proxies)
            
            return {
                "server": f"http://{proxy['host']}:{proxy['port']}",  # HTTP proxy (works for HTTPS tunneling)
                "username": proxy['username'],
                "password": proxy['password']
            }
    
    def get_proxy_count(self) -> int:
        """Get number of configured proxies."""
        return len(self.proxies)
    
    async def get_current_proxy_async(self) -> Optional[Dict[str, str]]:
        """
        Get current proxy without advancing index (for IP checking).
        
        Returns:
            Dict with server, username, password or None if no proxies configured
        """
        if not self.proxies:
            return None
        
        async with self.lock:
            proxy = self.proxies[self.index]
            
            return {
                "server": f"http://{proxy['host']}:{proxy['port']}",
                "username": proxy['username'],
                "password": proxy['password']
            }


def generate_proxy_config() -> Optional[Dict[str, str]]:
    """
    Generate proxy configuration for main scraper (backward compatibility).
    
    Returns:
        Dict with server, username, password or None if no proxy configured
        
    Note: This is deprecated. Use ProxyRotator instead.
    """
    if not PROXIES:
        return None
    
    # Return first proxy for backward compatibility
    proxy = PROXIES[0]
    return {
        "server": f"http://{proxy['host']}:{proxy['port']}",
        "username": proxy['username'],
        "password": proxy['password']
    }


async def test_proxy_connectivity(proxy: Dict[str, Any], timeout: float = 10.0) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Test if a proxy is working by attempting to get IP through it.
    
    Args:
        proxy: Proxy dictionary with host, port, username, password
        timeout: Request timeout in seconds
    
    Returns:
        Tuple of (is_working, ip_address, error_message)
        - is_working: True if proxy works, False otherwise
        - ip_address: IP address if successful, None if failed
        - error_message: Error description if failed, None if successful
    """
    try:
        server = proxy['host']
        port = proxy['port']
        username = proxy['username']
        password = proxy['password']
        proxy_url = f"http://{username}:{password}@{server}:{port}"
        
        async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout) as client:
            response = await client.get('http://api.ipify.org?format=json')
            
            if response.status_code == 200:
                data = response.json()
                ip_address = data.get('ip')
                if ip_address:
                    return True, ip_address, None
                else:
                    return False, None, "No IP in response"
            else:
                return False, None, f"HTTP {response.status_code}"
                
    except ImportError as e:
        if 'httpcore' in str(e) or 'asyncio' in str(e):
            return False, None, "httpcore[asyncio] not installed. Run: pip install 'httpcore[asyncio]'"
        return False, None, f"Import error: {str(e)[:60]}"
    except httpx.TimeoutException:
        return False, None, "Timeout"
    except httpx.ProxyError as e:
        return False, None, f"Proxy error: {str(e)[:60]}"
    except httpx.ConnectError as e:
        return False, None, f"Connection error: {str(e)[:60]}"
    except Exception as e:
        error_msg = str(e)
        if 'httpcore' in error_msg or 'asyncio' in error_msg:
            return False, None, "Install: pip install 'httpcore[asyncio]'"
        return False, None, f"{type(e).__name__}: {error_msg[:60]}"


async def test_all_proxies(proxies: List[Dict[str, Any]], timeout: float = 10.0) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Test all proxies in parallel and separate working from non-working ones.
    
    Args:
        proxies: List of proxy dictionaries to test
        timeout: Request timeout per proxy in seconds
    
    Returns:
        Tuple of (working_proxies, failed_proxies)
        - working_proxies: List of proxies that passed the test
        - failed_proxies: List of dicts with proxy info and error message
    """
    if not proxies:
        return [], []
    
    print(f"\n🧪 Testing {len(proxies)} proxy/proxies for connectivity...")
    print("="*80)
    
    # Test all proxies in parallel
    test_tasks = [
        test_proxy_connectivity(proxy, timeout) 
        for proxy in proxies
    ]
    results = await asyncio.gather(*test_tasks, return_exceptions=True)
    
    working_proxies = []
    failed_proxies = []
    
    for i, (proxy, result) in enumerate(zip(proxies, results), 1):
        proxy_name = f"{proxy['host']}:{proxy['port']}"
        
        if isinstance(result, Exception):
            # Exception during testing
            error_msg = f"{type(result).__name__}: {str(result)[:60]}"
            print(f"  ❌ Proxy {i}: {proxy_name} - {error_msg}")
            failed_proxies.append({
                'proxy': proxy,
                'error': error_msg
            })
        else:
            is_working, ip_address, error_msg = result
            if is_working:
                print(f"  ✅ Proxy {i}: {proxy_name} - IP: {ip_address}")
                working_proxies.append(proxy)
            else:
                print(f"  ❌ Proxy {i}: {proxy_name} - {error_msg or 'Failed'}")
                failed_proxies.append({
                    'proxy': proxy,
                    'error': error_msg or 'Unknown error'
                })
    
    print("="*80)
    print(f"✓ Working proxies: {len(working_proxies)}/{len(proxies)}")
    if failed_proxies:
        print(f"✗ Failed proxies: {len(failed_proxies)}/{len(proxies)}")
    
    return working_proxies, failed_proxies


async def get_current_ip(proxy_config: Optional[Dict[str, str]] = None) -> Optional[str]:
    """
    Get current IP address (optionally through proxy).
    
    Args:
        proxy_config: Optional proxy configuration dict
    
    Returns:
        IP address string or None if failed
    """
    try:
        if proxy_config:
            # Extract credentials from proxy_config
            server = proxy_config['server'].replace('http://', '')
            username = proxy_config['username']
            password = proxy_config['password']
            proxy_url = f"http://{username}:{password}@{server}"
            
            async with httpx.AsyncClient(proxy=proxy_url, timeout=10.0) as client:
                response = await client.get('http://api.ipify.org?format=json')
                data = response.json()
                return data.get('ip')
        else:
            # No proxy - get direct IP
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get('http://api.ipify.org?format=json')
                data = response.json()
                return data.get('ip')
    except ImportError as e:
        if 'httpcore' in str(e) or 'asyncio' in str(e):
            print(f"  ⚠️  Failed to get IP: httpcore[asyncio] not installed")
            print(f"      Run: pip install 'httpcore[asyncio]' or pip install -r requirements.txt")
        else:
            print(f"  ⚠️  Failed to get IP: {e}")
        return None
    except Exception as e:
        error_msg = str(e)
        if 'httpcore' in error_msg or 'asyncio' in error_msg:
            print(f"  ⚠️  Failed to get IP: httpcore[asyncio] not installed")
            print(f"      Run: pip install 'httpcore[asyncio]' or pip install -r requirements.txt")
        else:
            print(f"  ⚠️  Failed to get IP: {e}")
        return None


async def rotate_ip_if_needed(force: bool = False) -> bool:
    """
    Rotate IP if enough time has passed since last rotation.
    
    Enforces 7-minute cooldown between rotations (unless forced).
    After rotation, waits 30 seconds for IP to stabilize.
    During this time, _rotation_in_progress is True to pause workers.
    
    Args:
        force: If True, skip cooldown check and rotate immediately
    
    Returns:
        True if rotation was performed, False if skipped due to cooldown
    """
    global _last_rotation_time, _rotation_in_progress, _active_workers_count
    
    current_time = time.time()
    
    # Check if we're in cooldown period (unless forced)
    if not force and _last_rotation_time is not None:
        time_since_last = current_time - _last_rotation_time
        if time_since_last < ROTATION_COOLDOWN_SECONDS:
            remaining = ROTATION_COOLDOWN_SECONDS - time_since_last
            print(f"  ⏳ Cooldown active: {remaining:.0f}s remaining until next rotation allowed")
            print(f"  ℹ️  Using current IP (last rotation: {time_since_last:.0f}s ago)")
            return False
    
    # Signal workers to pause (no new work during rotation)
    _rotation_in_progress = True
    
    # Show active workers count
    async with _workers_lock:
        active_count = _active_workers_count
    print(f"  ℹ️  {active_count} workers currently active (will pause during rotation)")
    
    # Perform rotation
    if force:
        print(f"  🔄 Forcing IP rotation via API (without proxy)...")
    else:
        print(f"  🔄 Rotating IP via API (without proxy)...")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(IPROYAL_ROTATE_URL)
            
            if response.status_code == 200:
                print(f"  ✓ IP rotation successful")
                _last_rotation_time = current_time
                
                # Wait for IP to stabilize (workers are paused during this time)
                print(f"  ⏳ Waiting {ROTATION_STABILIZATION_SECONDS}s for IP to stabilize (no new work starts)...")
                await asyncio.sleep(ROTATION_STABILIZATION_SECONDS)
                print(f"  ✓ IP stabilized")
                
                # Resume workers
                _rotation_in_progress = False
                
                async with _workers_lock:
                    active_count = _active_workers_count
                print(f"  ✓ Resuming work ({active_count} active workers)")
                
                return True
            else:
                print(f"  ⚠️  Rotation API returned status {response.status_code}")
                _rotation_in_progress = False  # Resume on error
                return False
    
    except Exception as e:
        print(f"  ⚠️  Failed to rotate IP: {e}")
        _rotation_in_progress = False  # Resume on error
        return False


async def rotation_monitor(max_concurrent: int, stats: Dict[str, Any], stats_lock: asyncio.Lock, proxy_rotator: Optional[ProxyRotator] = None):
    """
    Background task that monitors and triggers IP rotation every 7 minutes.
    
    Args:
        max_concurrent: Maximum number of concurrent workers allowed
        stats: Shared statistics dictionary
        stats_lock: Lock for updating shared statistics
        proxy_rotator: Optional proxy rotator for checking IP
    """
    global _last_rotation_time, _active_workers_count
    
    while True:
        # Check every minute if rotation is needed
        await asyncio.sleep(60)
        
        # Check if we should rotate
        current_time = time.time()
        if _last_rotation_time is not None:
            time_since_last = current_time - _last_rotation_time
            
            # If 7+ minutes passed, trigger rotation
            if time_since_last >= ROTATION_COOLDOWN_SECONDS:
                async with stats_lock:
                    total_processed = stats['processed']
                    total_pending = stats['total_pending']
                
                # Only rotate if there's still work to do
                if total_processed < total_pending:
                    print(f"\n{'='*80}")
                    print(f"AUTOMATIC IP ROTATION (after {time_since_last/60:.1f} minutes)")
                    print(f"{'='*80}")
                    
                    await rotate_ip_if_needed(force=False)
                    
                    # Check current IP after rotation (use current proxy without advancing)
                    if proxy_rotator:
                        proxy_config = await proxy_rotator.get_current_proxy_async()
                    else:
                        proxy_config = generate_proxy_config()
                    current_ip = await get_current_ip(proxy_config)
                    if current_ip:
                        print(f"  ✓ New IP: {current_ip}")
                    
                    print(f"{'='*80}\n")


# ============================================================================
# SCRAPING (OPTIMIZED with Batch Processing and Session Reuse)
# ============================================================================

async def scrape_batch_optimized(
    creative_batch: List[Dict[str, Any]], 
    proxy_config: Optional[Dict[str, str]],
    worker_id: int,
    use_partial_proxy: bool = False
) -> List[Dict[str, Any]]:
    """
    Scrape a batch of creatives with session reuse optimization.
    
    Strategy:
    - First creative: Full HTML load with proper extraction (stealth, handlers, blocking)
    - Remaining creatives: API-only with gzip compression
    - Average: ~196 KB per creative (63% bandwidth savings)
    
    Args:
        creative_batch: List of creative dicts (id, creative_id, advertiser_id)
        proxy_config: Optional proxy configuration dict
        worker_id: Worker identifier for logging
        
    Returns:
        List of result dictionaries (one per creative), compatible with database update
    """
    results = []
    
    if not creative_batch:
        return results
    
    # Setup browser context (once for entire batch)
    try:
        async with async_playwright() as p:
            browser_setup = await _setup_browser_context(p, use_proxy=False, external_proxy=proxy_config)
            browser = browser_setup['browser']
            context = browser_setup['context']
            
            # ================================================================
            # FIRST CREATIVE: Full HTML load with proper extraction
            # ================================================================
            first_creative = creative_batch[0]
            first_url = generate_transparency_url(first_creative['advertiser_id'], first_creative['creative_id'])
            
            batch_start = time.time()
            print(f"  [Worker {worker_id}] 📄 Batch (1/{len(creative_batch)}): {first_creative['creative_id'][:15]}... (FULL HTML)")
            print(f"    ⏱️  [{time.time() - batch_start:.2f}s] Starting first creative (full HTML)...")
            sys.stdout.flush()
            
            start_time = time.time()
            
            try:
                # Initialize tracking (same as scrape_ads_transparency_page)
                tracker = TrafficTracker()
                content_js_responses = []
                all_xhr_fetch_requests = []
                
                # Create and register handlers (same as scrape_ads_transparency_page)
                route_handler = _create_route_handler(tracker)
                cache_aware_handler = create_cache_aware_route_handler(tracker, route_handler)
                await context.route('**/*', cache_aware_handler)
                
                response_handler = _create_response_handler(tracker, content_js_responses, all_xhr_fetch_requests)
                
                page = await context.new_page()
                
                # Apply stealth mode if available (same as scrape_ads_transparency_page)
                if STEALTH_AVAILABLE and ENABLE_STEALTH_MODE:
                    await Stealth().apply_stealth_async(page)
                
                # Set up event listeners (same as scrape_ads_transparency_page)
                page.on('request', lambda req: tracker.on_request(req))
                page.on('response', lambda res: tracker.on_response(res))
                page.on('response', response_handler)
                
                # Navigate to page
                print(f"    ⏱️  [{time.time() - batch_start:.2f}s] Loading HTML page...")
                await page.goto(first_url, wait_until="domcontentloaded", timeout=60000)
                print(f"    ⏱️  [{time.time() - batch_start:.2f}s] Page loaded, waiting for content...")
                
                # Wait for content (same as scrape_ads_transparency_page)
                wait_results = await _smart_wait_for_content(page, first_url, tracker, content_js_responses, all_xhr_fetch_requests)
                found_fletch_renders = wait_results['found_fletch_renders']
                print(f"    ⏱️  [{time.time() - batch_start:.2f}s] Content loaded, extracting data...")
                
                # Extract data (same as scrape_ads_transparency_page)
                static_content_info = check_if_static_cached_creative(tracker.api_responses, first_url)
                funded_by = extract_funded_by_from_api(tracker.api_responses, first_url)
                
                # Identify creative
                creative_results = _identify_creative(tracker, first_url, static_content_info)
                real_creative_id = creative_results['real_creative_id']
                
                # Extract videos and App Store IDs
                extraction_results = _extract_data(
                    content_js_responses,
                    found_fletch_renders,
                    static_content_info,
                    real_creative_id,
                    debug_fletch=False,
                    debug_appstore=False
                )
                
                # Get cache statistics
                cache_stats = get_cache_statistics()
                
                # Build result dictionary
                result_dict = {
                    'creative_db_id': first_creative['id'],
                    'success': True,
                    'videos': extraction_results['unique_videos'],
                    'video_count': len(extraction_results['unique_videos']),
                    'appstore_id': extraction_results['app_store_id'],
                    'funded_by': funded_by,
                    'real_creative_id': real_creative_id,
                    'duration_ms': (time.time() - start_time) * 1000,
                    'error': None,
                    'cache_hits': cache_stats['hits'],
                    'cache_misses': cache_stats['misses'],
                    'cache_bytes_saved': cache_stats['bytes_saved'],
                    'cache_hit_rate': cache_stats['hit_rate'],
                    'cache_total_requests': cache_stats['total_requests']
                }
                results.append(result_dict)
                
                # Log result
                duration = time.time() - start_time
                print(f"    ⏱️  [{time.time() - batch_start:.2f}s] First creative complete ({duration:.2f}s)")
                print(f"    ✅ {first_creative['creative_id'][:15]}... ({result_dict['video_count']} videos)")
                sys.stdout.flush()
                
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                print(f"    ❌ {first_creative['creative_id'][:15]}... - {error_msg[:60]}")
                sys.stdout.flush()
                
                results.append({
                    'creative_db_id': first_creative['id'],
                    'success': False,
                    'error': error_msg,
                    'duration_ms': (time.time() - start_time) * 1000,
                    'videos': [],
                    'video_count': 0,
                    'appstore_id': None,
                    'funded_by': None
                })
                
                # If first creative fails, close browser and return
                await browser.close()
                return results
            
            # Extract cookies for reuse (already in the context from first creative)
            cookies = await context.cookies()
            
            # Reset cache statistics for subsequent API-only calls
            reset_cache_statistics()
            
            # ================================================================
            # REMAINING CREATIVES: API-only with session reuse
            # ================================================================
            for i, creative in enumerate(creative_batch[1:], start=2):
                # Add delay to avoid rate limiting (except for first request after HTML)
                if i > 2:
                    await asyncio.sleep(DELAY_BETWEEN_CREATIVES)  # Configurable delay between creatives in batch
                
                print(f"  [Worker {worker_id}] 🔄 Batch ({i}/{len(creative_batch)}): {creative['creative_id'][:15]}... (API-only)")
                print(f"    ⏱️  [{time.time() - batch_start:.2f}s] Starting API-only request...")
                sys.stdout.flush()
                
                start_time = time.time()
                tracker = TrafficTracker()
                
                try:
                    # Call API-only scraper (reuses same page and cookies)
                    api_result = await scrape_ads_transparency_api_only(
                        advertiser_id=creative['advertiser_id'],
                        creative_id=creative['creative_id'],
                        cookies=cookies,
                        page=page,
                        tracker=tracker,
                        playwright_instance=p,
                        user_agent=browser_setup['user_agent'],
                        use_partial_proxy=use_partial_proxy,
                        debug_appstore=False,
                        debug_fletch=False,
                        debug_content=False
                    )
                    
                    # Convert to stress test format
                    result_dict = {
                        'creative_db_id': creative['id'],
                        'success': api_result.get('success', False),
                        'videos': api_result.get('videos', []),
                        'video_count': api_result.get('video_count', 0),
                        'appstore_id': api_result.get('app_store_id'),
                        'funded_by': api_result.get('funded_by'),
                        'real_creative_id': api_result.get('real_creative_id'),
                        'duration_ms': api_result.get('duration_ms', 0),
                        'error': '; '.join(api_result.get('errors', [])) if not api_result.get('success') else None,
                        'cache_hits': api_result.get('cache_hits', 0),
                        'cache_misses': api_result.get('cache_misses', 0),
                        'cache_bytes_saved': api_result.get('cache_bytes_saved', 0),
                        'cache_hit_rate': api_result.get('cache_hit_rate', 0.0),
                        'cache_total_requests': api_result.get('cache_total_requests', 0)
                    }
                    results.append(result_dict)
                    
                    # Log result
                    duration = time.time() - start_time
                    print(f"    ⏱️  [{time.time() - batch_start:.2f}s] API-only complete ({duration:.2f}s)")
                    if result_dict['success']:
                        print(f"    ✅ {creative['creative_id'][:15]}... ({result_dict['video_count']} videos)")
                    else:
                        print(f"    ⚠️  {creative['creative_id'][:15]}... - {result_dict.get('error', 'Unknown')[:60]}")
                    sys.stdout.flush()
                    
                except Exception as e:
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    print(f"    ❌ {creative['creative_id'][:15]}... - {error_msg[:60]}")
                    sys.stdout.flush()
                    
                    results.append({
                        'creative_db_id': creative['id'],
                        'success': False,
                        'error': error_msg,
                        'duration_ms': (time.time() - start_time) * 1000,
                        'videos': [],
                        'video_count': 0,
                        'appstore_id': None,
                        'funded_by': None
                    })
            
            # Log batch completion time
            batch_duration = time.time() - batch_start
            print(f"    ⏱️  [{batch_duration:.2f}s] Batch complete (total time for {len(creative_batch)} creatives)")
            sys.stdout.flush()
            
            await browser.close()
    
    except Exception as e:
        # Browser setup failed - mark all creatives as failed
        error_msg = f"Browser setup failed: {type(e).__name__}: {str(e)}"
        print(f"  ❌ [Worker {worker_id}] {error_msg}")
        sys.stdout.flush()
        
        for creative in creative_batch:
            results.append({
                'creative_db_id': creative['id'],
                'success': False,
                'error': error_msg,
                'duration_ms': 0,
                'videos': [],
                'video_count': 0,
                'appstore_id': None,
                'funded_by': None
            })
    
    return results


# ============================================================================
# MAIN
# ============================================================================

async def worker(
    worker_id: int,
    semaphore: asyncio.Semaphore,
    proxy_rotator: Optional[ProxyRotator],
    stats: Dict[str, Any],
    stats_lock: asyncio.Lock,
    show_cache_stats: bool = True,
    batch_size: int = None,
    use_partial_proxy: bool = False
):
    """
    Worker coroutine that continuously processes BATCHES of creatives from database.
    Each batch uses session reuse optimization (1 HTML load + 19 API-only).
    Pauses during IP rotation and 30s stabilization period.
    
    Args:
        worker_id: Unique worker identifier
        semaphore: Semaphore to control concurrency
        proxy_rotator: Optional proxy rotator for round-robin proxy rotation
        stats: Shared statistics dictionary
        stats_lock: Lock for updating shared statistics
        show_cache_stats: If True, display cache statistics
        batch_size: Number of creatives per batch (default: from DEFAULT_BATCH_SIZE config)
    """
    global _rotation_in_progress, _active_workers_count
    
    if batch_size is None:
        batch_size = DEFAULT_BATCH_SIZE
    
    while True:
        # Wait if rotation is in progress
        while _rotation_in_progress:
            await asyncio.sleep(1)
        
        async with semaphore:
            # Increment active workers count
            async with _workers_lock:
                _active_workers_count += 1
            
            try:
                # Check remaining creatives before fetching (respects max_urls)
                async with stats_lock:
                    remaining = stats['total_pending'] - stats['processed']
                
                if remaining <= 0:
                    # Reached max_urls limit or no more pending
                    break
                
                # Adjust batch size to not exceed max_urls limit
                actual_batch_size = min(batch_size, remaining)
                
                # Get next batch and atomically mark as processing (thread-safe)
                # Uses SELECT FOR UPDATE SKIP LOCKED to prevent race conditions
                creative_batch = get_pending_batch_and_mark_processing(batch_size=actual_batch_size)
                
                if not creative_batch:
                    # No more pending URLs in database
                    break
                
                # Get next proxy for this batch (round-robin rotation)
                proxy_config = await proxy_rotator.get_next_proxy_async() if proxy_rotator else None
                
                # Log which proxy this batch is using
                if proxy_config:
                    proxy_server = proxy_config['server'].replace('http://', '')
                    print(f"  [Worker {worker_id}] 🔄 Using proxy: {proxy_server}")
                
                # Scrape entire batch (optimized with session reuse)
                results = await scrape_batch_optimized(creative_batch, proxy_config, worker_id, use_partial_proxy)
                
                # Update database for each result
                for result in results:
                    creative_db_id = result.pop('creative_db_id')
                    update_result(creative_db_id, result)
                    
                    # Update shared statistics
                    async with stats_lock:
                        stats['processed'] += 1
                        if result['success']:
                            stats['success'] += 1
                        else:
                            # Classify error type
                            error_msg = result.get('error', '')
                            should_retry, _, error_category = classify_error(error_msg)
                            
                            if should_retry:
                                stats['retries'] += 1
                            elif error_category == 'bad_ad':
                                stats['bad_ads'] += 1
                            else:
                                stats['failed'] += 1
                        
                        # Accumulate cache statistics
                        stats['cache_hits'] += result.get('cache_hits', 0)
                        stats['cache_misses'] += result.get('cache_misses', 0)
                        stats['cache_bytes_saved'] += result.get('cache_bytes_saved', 0)
                
                # Print progress after batch (every 20 URLs)
                async with stats_lock:
                    elapsed = time.time() - stats['start_time']
                    rate = stats['processed'] / elapsed if elapsed > 0 else 0
                    retry_info = f", {stats['retries']} ⟳" if stats.get('retries', 0) > 0 else ""
                    bad_ads_info = f", {stats['bad_ads']} 🚫" if stats.get('bad_ads', 0) > 0 else ""
                    
                    # Calculate cache hit rate for progress display
                    cache_info = ""
                    if show_cache_stats:
                        cache_total = stats['cache_hits'] + stats['cache_misses']
                        if cache_total > 0:
                            cache_hit_rate = (stats['cache_hits'] / cache_total) * 100
                            cache_mb_saved = stats['cache_bytes_saved'] / (1024 * 1024)
                            cache_info = f" | 💾 Cache: {cache_hit_rate:.0f}% ({cache_mb_saved:.1f} MB saved)"
                    
                    print(f"  [Worker {worker_id}] Batch complete: {stats['processed']}/{stats['total_pending']} URLs "
                          f"({stats['success']} ✓, {stats['failed']} ✗{retry_info}{bad_ads_info}) "
                          f"[{rate:.1f} URL/s]{cache_info}")
                    
                    # Special cache report after first batch (to show warm-up effect)
                    if show_cache_stats and stats['processed'] == batch_size:
                        cache_total = stats['cache_hits'] + stats['cache_misses']
                        if cache_total > 0:
                            cache_hit_rate = (stats['cache_hits'] / cache_total) * 100
                            print(f"  ℹ️  Initial cache warm-up: {cache_hit_rate:.0f}% hit rate (will improve as cache builds)")
                
            finally:
                # Decrement active workers count
                async with _workers_lock:
                    _active_workers_count -= 1


async def run_stress_test(max_concurrent: int = None, max_urls: Optional[int] = None, use_proxy: bool = True, force_rotation: bool = False, enable_rotation: bool = False, show_cache_stats: bool = True, batch_size: int = None, use_partial_proxy: bool = False):
    """
    Run stress test with continuous worker pool (OPTIMIZED with batch processing).
    
    Each worker processes batches of creatives with session reuse:
    - First creative: Full HTML load (524 KB) + extract cookies
    - Remaining creatives: API-only with gzip (179 KB each)
    - Average: 181 KB per creative (65% bandwidth savings)
    
    Args:
        max_concurrent: Maximum number of concurrent workers (each processes batches)
        max_urls: Maximum number of URLs to process (None for unlimited)
        use_proxy: If True, use configured proxy; if False, no proxy
        force_rotation: If True, force IP rotation even if within cooldown period
        enable_rotation: If True, enable automatic IP rotation every 7 minutes
        show_cache_stats: If True, display cache statistics (default: True)
        batch_size: Number of creatives per batch (default: from DEFAULT_BATCH_SIZE config)
        use_partial_proxy: If True, use proxy only for HTML+API, bypass for content.js (saves ~70% proxy bandwidth)
    """
    # Use default values from configuration if not provided
    if max_concurrent is None:
        max_concurrent = DEFAULT_MAX_CONCURRENT
    if batch_size is None:
        batch_size = DEFAULT_BATCH_SIZE
    
    print("="*80)
    print("GOOGLE ADS TRANSPARENCY CENTER - STRESS TEST (OPTIMIZED)")
    print("="*80)
    
    # Get initial statistics
    db_stats = get_statistics()
    print(f"\nDatabase Statistics:")
    print(f"  Total:      {db_stats['total']}")
    print(f"  Pending:    {db_stats['pending']}")
    print(f"  Processing: {db_stats['processing']}")
    print(f"  Completed:  {db_stats['completed']}")
    print(f"  Failed:     {db_stats['failed']}")
    print(f"  Bad ads:    {db_stats['bad_ad']}")
    
    if db_stats['pending'] == 0:
        print("\n⚠️  No pending URLs found in database")
        print("Run: python3 download_creatives.py --limit 1000")
        return
    
    # Calculate total to process
    total_pending = db_stats['pending']
    if max_urls:
        total_pending = min(total_pending, max_urls)
    
    # Initialize global locks first (before any rotation)
    global _workers_lock, _active_workers_count
    _workers_lock = asyncio.Lock()
    _active_workers_count = 0
    
    # Setup proxy rotator with health testing
    proxy_rotator = None
    working_proxies = []
    failed_proxies = []
    
    if use_proxy and PROXIES:
        # Test all proxies before using them
        working_proxies, failed_proxies = await test_all_proxies(PROXIES, timeout=10.0)
        
        if working_proxies:
            proxy_rotator = ProxyRotator(working_proxies)
            print(f"\n✅ Using {len(working_proxies)} working proxy/proxies for scraping")
        else:
            print(f"\n⚠️  No working proxies found! All {len(PROXIES)} proxies failed the health check.")
            print("   Continuing without proxies (direct connection)")
            proxy_rotator = None
    elif use_proxy and not PROXIES:
        print("  ⚠️  Proxy enabled but no proxies configured")
    
    print(f"\nStress Test Configuration:")
    print(f"  Max concurrent: {max_concurrent} workers")
    print(f"  Batch size:     {batch_size} creatives per batch")
    print(f"  URLs to process: {total_pending}")
    print(f"  Optimization:   Session reuse (1 HTML + {batch_size-1} API-only per batch)")
    print(f"  Bandwidth:      ~181 KB/creative (65% savings vs 524 KB)")
    if proxy_rotator:
        proxy_count = proxy_rotator.get_proxy_count()
        print(f"  Proxies:        {proxy_count} working proxy/proxies with round-robin rotation")
        for i, proxy in enumerate(working_proxies, 1):
            print(f"    Proxy {i}:      {proxy['host']}:{proxy['port']}")
        print(f"  Rotation:       Each batch gets next proxy sequentially")
        print(f"  Distribution:  With {max_concurrent} workers, proxies will rotate evenly across batches")
        if failed_proxies:
            print(f"\n  Failed proxies ({len(failed_proxies)}):")
            for failed in failed_proxies:
                p = failed['proxy']
                print(f"    ❌ {p['host']}:{p['port']} - {failed['error']}")
        if use_partial_proxy:
            print(f"  Proxy mode:     Partial (HTML+API only, content.js direct)")
            print(f"  Proxy savings:  ~70% bandwidth reduction")
        else:
            print(f"  Proxy mode:     Full (all traffic through proxy)")
    else:
        print(f"  Proxy:          None (direct connection)")
    
    if enable_rotation:
        print(f"  IP Rotation:    Enabled (every {ROTATION_COOLDOWN_SECONDS/60:.0f} minutes)")
    else:
        print(f"  IP Rotation:    Disabled (static IP)")
    
    # Cache status at startup
    if show_cache_stats:
        print(f"\nCache System:")
        print(f"  Status:         ✅ ENABLED (two-level: memory L1 + disk L2)")
        print(f"  Caches:         main.dart.js files (~1.5-2 MB each)")
        print(f"  Expected:       98%+ hit rate after warm-up")
        print(f"  Savings:        ~1.5 GB bandwidth per 1,000 URLs")
    
    # Rotate IP if needed (only if rotation is enabled or forced)
    if enable_rotation or force_rotation:
        print("\n" + "="*80)
        print("IP ROTATION CHECK")
        print("="*80)
        await rotate_ip_if_needed(force=force_rotation)
    
    # Check current IP (using first proxy if available)
    print("\n🔄 Checking current IP...")
    try:
        # Get first proxy config for IP check (without advancing index)
        if proxy_rotator:
            first_proxy_config = await proxy_rotator.get_current_proxy_async()
        else:
            first_proxy_config = None
        
        current_ip = await get_current_ip(first_proxy_config)
        if current_ip:
            print(f"✓ Current IP: {current_ip}")
        else:
            print(f"⚠️  Could not determine IP (continuing anyway)")
            current_ip = "unknown"
    except Exception as e:
        print(f"⚠️  Failed to get IP: {e} (continuing anyway)")
        current_ip = "unknown"
    
    # Shared statistics
    stats = {
        'processed': 0,
        'success': 0,
        'failed': 0,
        'retries': 0,
        'bad_ads': 0,
        'total_pending': total_pending,
        'start_time': time.time(),
        # Cache statistics
        'cache_hits': 0,
        'cache_misses': 0,
        'cache_bytes_saved': 0
    }
    stats_lock = asyncio.Lock()
    
    # Create semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # Start workers
    print(f"\n🚀 Starting {max_concurrent} concurrent workers...")
    print("="*80)
    
    start_time = time.time()
    
    try:
        # Create worker tasks
        workers = [
            worker(i, semaphore, proxy_rotator, stats, stats_lock, show_cache_stats, batch_size, use_partial_proxy)
            for i in range(max_concurrent)
        ]
        
        # Start rotation monitor as background task (only if rotation is enabled)
        if enable_rotation:
            monitor_task = asyncio.create_task(rotation_monitor(max_concurrent, stats, stats_lock, proxy_rotator))
        else:
            monitor_task = None
        
        # Wait for all workers to complete
        await asyncio.gather(*workers)
        
        # Cancel monitor task when workers finish (if it was started)
        if monitor_task:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    
    # Final summary
    total_duration = time.time() - start_time
    
    print(f"\n{'='*80}")
    print("STRESS TEST COMPLETE")
    print(f"{'='*80}")
    print(f"Total duration:   {total_duration:.1f}s ({total_duration/60:.1f} min)")
    print(f"URLs processed:   {stats['processed']}")
    print(f"  Success:        {stats['success']}")
    print(f"  Failed:         {stats['failed']}")
    if stats['bad_ads'] > 0:
        print(f"  Bad ads:        {stats['bad_ads']} (broken creative pages)")
    if stats['retries'] > 0:
        print(f"  Pending retry:  {stats['retries']} (marked for retry)")
    print(f"Success rate:     {stats['success']/stats['processed']*100:.1f}%" if stats['processed'] > 0 else "N/A")
    print(f"Average rate:     {stats['processed']/total_duration:.2f} URL/s" if total_duration > 0 else "N/A")
    
    # Cache statistics
    if show_cache_stats:
        cache_total = stats['cache_hits'] + stats['cache_misses']
        if cache_total > 0:
            cache_hit_rate = (stats['cache_hits'] / cache_total) * 100
            cache_mb_saved = stats['cache_bytes_saved'] / (1024 * 1024)
            print(f"\nCache Statistics:")
            print(f"  Cache hits:     {stats['cache_hits']}/{cache_total} ({cache_hit_rate:.1f}%)")
            print(f"  Cache misses:   {stats['cache_misses']}")
            print(f"  Bytes saved:    {cache_mb_saved:.2f} MB")
            print(f"  Performance:    {cache_hit_rate:.0f}% bandwidth reduction from cache")
    
    print(f"\nIP used:          {current_ip}")
    print(f"Database:         PostgreSQL (creatives_fresh table)")


async def test_advertiser_page():
    """
    Test function to visit advertiser page and capture SearchCreatives API calls.
    Saves all cookies, request headers, and responses to debug folder.
    
    IMPORTANT: Uses EXACT same browser configuration as production scraper:
    - TrafficTracker for request/response monitoring
    - Cache-aware route handler (blocks ads, images, etc.)
    - Response handler for content.js capture
    - Stealth mode (if available)
    - All event listeners
    """
    print("="*80)
    print("ADVERTISER PAGE TEST - SearchCreatives API Capture")
    print("="*80)
    print(f"Target URL: {FIXED_TEST_URL}")
    print(f"Debug folder: {DEBUG_FOLDER}")
    print("="*80)
    
    # Create debug folder
    debug_path = Path(DEBUG_FOLDER)
    debug_path.mkdir(exist_ok=True)
    
    # Storage for captured data
    search_creatives_calls = []
    search_creatives_responses = []  # Track responses
    all_cookies = []
    
    async with async_playwright() as p:
        # Launch browser in HEADLESS mode
        print(f"\n🔧 Launching browser in HEADLESS mode...")
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-dev-shm-usage', '--disable-plugins']
        )
        
        # Get user agent
        from google_ads_traffic import _get_user_agent
        import re
        user_agent = _get_user_agent()
        
        # Extract Chrome version from user-agent to match sec-ch-ua headers
        chrome_version_match = re.search(r'Chrome/(\d+)', user_agent)
        chrome_version = chrome_version_match.group(1) if chrome_version_match else '130'
        
        # Setup proxy if available
        proxy_config = None
        if PROXIES:
            proxy_rotator = ProxyRotator(PROXIES)
            proxy_config = await proxy_rotator.get_next_proxy_async()
            print(f"  🌐 Using proxy: {proxy_config['server']}")
        
        # Create context with headers that mask headless mode
        context_options = {
            'user_agent': user_agent,
            'ignore_https_errors': True,
            # Override Client Hints headers to hide headless mode
            # IMPORTANT: Version must match user-agent Chrome version
            'extra_http_headers': {
                'sec-ch-ua': f'"Chromium";v="{chrome_version}", "Google Chrome";v="{chrome_version}", "Not?A_Brand";v="99"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"'
            }
        }
        
        # Add proxy to context if available
        if proxy_config:
            context_options['proxy'] = proxy_config
        
        context = await browser.new_context(**context_options)
        
        print(f"  Chrome version: {chrome_version} (extracted from user-agent)")
        
        browser_setup = {
            'browser': browser,
            'context': context,
            'user_agent': user_agent
        }
        
        print(f"\n✓ Browser started (SAME CONFIG AS PRODUCTION)")
        print(f"  User-Agent: {browser_setup['user_agent'][:80]}...")
        
        # ================================================================
        # CRITICAL: Initialize SAME tracking/handlers as production!
        # ================================================================
        
        # Initialize tracking (SAME as scrape_ads_transparency_page)
        tracker = TrafficTracker()
        content_js_responses = []
        all_xhr_fetch_requests = []
        
        print(f"  Traffic Tracker: Initialized")
        
        # Create and register handlers (SAME as scrape_ads_transparency_page)
        route_handler = _create_route_handler(tracker)
        cache_aware_handler = create_cache_aware_route_handler(tracker, route_handler)
        
        # Create custom route handler to ALSO capture SearchCreatives
        async def combined_route_handler(route):
            """
            Combined handler that:
            1. Captures SearchCreatives calls for debugging
            2. Applies cache-aware routing (blocks ads, uses cache)
            3. Intercepts SearchCreatives response if possible
            """
            request = route.request
            
            # Check if this is SearchCreatives API call
            if 'SearchCreatives' in request.url:
                print(f"\n🔍 Captured SearchCreatives API call!")
                print(f"   URL: {request.url}")
                
                # Save request details
                request_data = {
                    'url': request.url,
                    'method': request.method,
                    'headers': dict(request.headers),
                    'post_data': request.post_data if request.method == 'POST' else None,
                    'timestamp': datetime.now().isoformat()
                }
                
                # Save request immediately
                request_file = debug_path / f"searchcreatives_request_{len(search_creatives_calls)}.json"
                with open(request_file, 'w', encoding='utf-8') as f:
                    json.dump(request_data, f, indent=2, ensure_ascii=False)
                print(f"   ✓ Saved request to: {request_file}")
                
                search_creatives_calls.append(request_data)
                
                # Fetch and capture response inline
                try:
                    response = await route.fetch()
                    body = await response.body()
                    
                    print(f"   📥 Got response: {response.status} ({len(body)} bytes)")
                    
                    # Save response
                    search_creatives_responses.append({
                        'body': body,
                        'url': request.url,
                        'status': response.status,
                        'headers': dict(response.headers)
                    })
                    
                    # Fulfill with the response
                    await route.fulfill(response=response)
                    return
                except Exception as e:
                    print(f"   ⚠️  Route fetch error: {e}")
            
            # For other requests, apply cache-aware handler
            await cache_aware_handler(route)
        
        # Register the combined handler
        await context.route('**/*', combined_route_handler)
        print(f"  Route Handler: Cache-aware (blocks ads/images/fonts)")
        
        # Create response handler (SAME as scrape_ads_transparency_page)
        response_handler = _create_response_handler(tracker, content_js_responses, all_xhr_fetch_requests)
        
        # Simple response capture - store responses immediately
        async def capture_response(response):
            """Capture SearchCreatives response immediately"""
            # Note: SearchCreatives responses are already captured in route handler
            # This just logs them for visibility
            
            if 'SearchCreatives' in response.url or 'SearchService' in response.url:
                print(f"  [DEBUG] Response: {response.url[:150]}")
            
            # Call standard handler
            await response_handler(response)
        
        # Create page
        page = await context.new_page()
        
        # Apply stealth mode if available (SAME as production)
        if STEALTH_AVAILABLE and ENABLE_STEALTH_MODE:
            await Stealth().apply_stealth_async(page)
            print(f"  Stealth: Enabled")
        else:
            print(f"  Stealth: Not available")
        
        # Set up event listeners (SAME as scrape_ads_transparency_page)
        page.on('request', lambda req: tracker.on_request(req))
        page.on('response', lambda res: tracker.on_response(res))
        page.on('response', lambda res: asyncio.create_task(capture_response(res)))
        print(f"  Event Listeners: Registered (request/response tracking)")
        
        print(f"\n🌐 Navigating to advertiser page...")
        print(f"   {FIXED_TEST_URL}")
        
        # Navigate to the page
        try:
            response = await page.goto(FIXED_TEST_URL, wait_until="domcontentloaded", timeout=60000)
            print(f"\n✓ Page loaded")
            print(f"  Status: {response.status}")
            print(f"  URL: {response.url}")
            
            # Wait a bit for API calls to complete
            print(f"\n⏳ Waiting 10 seconds for API calls to complete...")
            await asyncio.sleep(10)
            
            # NOTE: We ignore browser-captured SearchCreatives requests/responses
            # We only use the browser to get cookies
            print(f"\n✓ Browser captured {len(search_creatives_responses)} SearchCreatives responses (ignored - used only for cookies)")
            
            # Get cookies
            all_cookies = await context.cookies()
            print(f"\n🍪 Captured {len(all_cookies)} cookies")
            
            # Save cookies
            cookies_file = debug_path / "cookies.json"
            with open(cookies_file, 'w', encoding='utf-8') as f:
                json.dump(all_cookies, f, indent=2, ensure_ascii=False)
            print(f"   ✓ Saved to: {cookies_file}")
            
            # Print cookie names
            for cookie in all_cookies:
                print(f"     - {cookie['name']}: {cookie['value'][:50]}..." if len(cookie['value']) > 50 else f"     - {cookie['name']}: {cookie['value']}")
            
            # ================================================================
            # PAGINATION LOOP: Make SearchCreatives calls with pagination
            # ================================================================
            print(f"\n{'='*80}")
            print(f"PAGINATION LOOP - Fetching all creatives (max 10 pages)")
            print(f"{'='*80}")
            
            import urllib.parse
            import httpx
            
            # Get cookie string for header
            cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in all_cookies])
            
            # Build headers
            custom_headers = {
                "accept": "*/*",
                "content-type": "application/x-www-form-urlencoded",
                "cookie": cookie_header,
                "origin": "https://adstransparency.google.com",
                "referer": FIXED_TEST_URL,
                "user-agent": user_agent,
                "x-framework-xsrf-token": "",
                "x-same-domain": "1",
                "sec-ch-ua": f'"Chromium";v="{chrome_version}", "Google Chrome";v="{chrome_version}", "Not?A_Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"'
            }
            
            api_url = "https://adstransparency.google.com/anji/_/rpc/SearchService/SearchCreatives?authuser="
            
            # Base POST data structure (without pagination token)
            base_post_data = {
                "2": 40,
                "3": {
                    "4": 3,
                    "6": 20251029,
                    "7": 20251030,
                    "12": {"1": "", "2": True},
                    "13": {"1": ["AR05226884764400615425"]},
                    "14": [5]
                },
                "7": {"1": 1, "2": 39, "3": 2268}
            }
            
            pagination_token = None
            page_num = 0
            max_pages = 1000  # Very high limit - will stop when no more pagination token
            total_creatives = 0
            all_creative_ids = set()  # Store unique Creative IDs (CR...)
            all_creative_id_numbers = set()  # Store unique creativeId numbers from URLs
            all_content_js_urls = set()  # Store unique content.js URLs
            
            try:
                # Configure httpx client with proxy if available
                httpx_config = {"timeout": 30.0}
                if proxy_config:
                    # Convert Playwright proxy format to httpx format
                    proxy_url = f"{proxy_config['server'].replace('http://', 'http://')}"
                    if 'username' in proxy_config and proxy_config['username']:
                        # Add authentication to proxy URL
                        proxy_parts = proxy_config['server'].split('://')
                        proxy_url = f"{proxy_parts[0]}://{proxy_config['username']}:{proxy_config['password']}@{proxy_parts[1]}"
                    httpx_config["proxies"] = {"http://": proxy_url, "https://": proxy_url}
                    print(f"  🌐 API calls will use proxy: {proxy_config['server']}")
                
                async with httpx.AsyncClient(**httpx_config) as client:
                    while page_num < max_pages:
                        # Add random pause between requests (except for the first one)
                        if page_num > 0:
                            import random
                            pause = random.uniform(1.5, 3)
                            print(f"\n⏳ Waiting {pause:.1f} seconds before next request...")
                            await asyncio.sleep(pause)
                        
                        page_num += 1
                        
                        # Build POST data (add pagination token if we have one)
                        if pagination_token:
                            post_data_json = {**base_post_data, "4": pagination_token}
                            print(f"\n📄 Page {page_num} (with pagination token: {pagination_token[:50]}...)")
                        else:
                            post_data_json = base_post_data.copy()
                            print(f"\n📄 Page {page_num} (initial request)")
                        
                        post_data = "f.req=" + urllib.parse.quote(json.dumps(post_data_json, separators=(',', ':')))
                        
                        # Make API call
                        response = await client.post(
                            api_url,
                            headers=custom_headers,
                            content=post_data
                        )
                        
                        print(f"   ✓ Response: {response.status_code} ({len(response.content)} bytes)")
                        
                        # Save request
                        request_file = debug_path / f"page_{page_num}_request.json"
                        request_data = {
                            'url': api_url,
                            'method': 'POST',
                            'headers': custom_headers,
                            'post_data': post_data,
                            'post_data_decoded': post_data_json,
                            'page_number': page_num,
                            'timestamp': datetime.now().isoformat()
                        }
                        with open(request_file, 'w', encoding='utf-8') as f:
                            json.dump(request_data, f, indent=2, ensure_ascii=False)
                        print(f"   ✓ Saved request: {request_file.name}")
                        
                        # Save response metadata
                        response_meta_file = debug_path / f"page_{page_num}_response_meta.json"
                        response_meta = {
                            'url': api_url,
                            'status': response.status_code,
                            'headers': dict(response.headers),
                            'page_number': page_num,
                            'timestamp': datetime.now().isoformat()
                        }
                        with open(response_meta_file, 'w', encoding='utf-8') as f:
                            json.dump(response_meta, f, indent=2, ensure_ascii=False)
                        print(f"   ✓ Saved response metadata: {response_meta_file.name}")
                        
                        # Save response body
                        response_body_file = debug_path / f"page_{page_num}_response_body.txt"
                        with open(response_body_file, 'wb') as f:
                            f.write(response.content)
                        print(f"   ✓ Saved response body: {response_body_file.name}")
                        
                        # Parse response and extract pagination token
                        try:
                            response_json = response.json()
                            creatives = response_json.get("1", [])
                            creatives_count = len(creatives)
                            total_creatives += creatives_count
                            
                            # Extract Creative IDs, creativeId numbers, and content.js URLs from this page
                            page_creative_ids = []
                            page_creative_id_numbers = []
                            page_content_js_urls = []
                            
                            for creative in creatives:
                                # Extract Creative ID (field "2")
                                creative_id = creative.get("2", "")
                                if creative_id:
                                    all_creative_ids.add(creative_id)
                                    page_creative_ids.append(creative_id)
                                
                                # Extract content.js URL and creativeId from URL (field "3" -> "1" -> "4")
                                try:
                                    url = creative.get("3", {}).get("1", {}).get("4", "")
                                    if url:
                                        # Store the full content.js URL
                                        all_content_js_urls.add(url)
                                        page_content_js_urls.append(url)
                                        
                                        # Also extract creativeId parameter if present
                                        if "creativeId=" in url:
                                            from urllib.parse import urlparse, parse_qs
                                            parsed_url = urlparse(url)
                                            query_params = parse_qs(parsed_url.query)
                                            creative_id_num = query_params.get("creativeId", [""])[0]
                                            if creative_id_num:
                                                all_creative_id_numbers.add(creative_id_num)
                                                page_creative_id_numbers.append(creative_id_num)
                                except Exception as e:
                                    pass  # Skip if parsing fails
                            
                            print(f"   📊 Creatives in this page: {creatives_count}")
                            print(f"   🆔 Creative IDs (CR...) extracted: {len(page_creative_ids)}")
                            print(f"   🆔 creativeId numbers extracted: {len(page_creative_id_numbers)}")
                            print(f"   🔗 content.js URLs extracted: {len(page_content_js_urls)}")
                            print(f"   📊 Total creatives so far: {total_creatives}")
                            print(f"   🆔 Unique Creative IDs (CR...) so far: {len(all_creative_ids)}")
                            print(f"   🆔 Unique creativeId numbers so far: {len(all_creative_id_numbers)}")
                            print(f"   🔗 Unique content.js URLs so far: {len(all_content_js_urls)}")
                            
                            # Extract next pagination token
                            pagination_token = response_json.get("2", "")
                            
                            if not pagination_token:
                                print(f"\n✅ No more pages - pagination complete!")
                                break
                            else:
                                print(f"   ➡️  Next pagination token: {pagination_token[:50]}...")
                                
                        except Exception as e:
                            print(f"   ❌ Error parsing response: {e}")
                            break
                    
                    if page_num >= max_pages:
                        print(f"\n⚠️  Reached maximum page limit ({max_pages})")
                    
                    print(f"\n{'='*80}")
                    print(f"PAGINATION COMPLETE")
                    print(f"{'='*80}")
                    print(f"   Total pages fetched: {page_num}")
                    print(f"   Total creatives: {total_creatives}")
                    print(f"   Unique Creative IDs (CR...): {len(all_creative_ids)}")
                    print(f"   Unique creativeId numbers: {len(all_creative_id_numbers)}")
                    print(f"   Unique content.js URLs: {len(all_content_js_urls)}")
                    print(f"{'='*80}")
                    
                    # Save all Creative IDs (CR...) to file
                    if all_creative_ids:
                        creative_ids_file = debug_path / "all_creative_ids.txt"
                        sorted_ids = sorted(list(all_creative_ids))
                        with open(creative_ids_file, 'w', encoding='utf-8') as f:
                            for creative_id in sorted_ids:
                                f.write(f"{creative_id}\n")
                        print(f"\n💾 Saved {len(sorted_ids)} unique Creative IDs (CR...) to: {creative_ids_file.name}")
                    
                    # Save all creativeId numbers to file
                    if all_creative_id_numbers:
                        creative_id_numbers_file = debug_path / "all_creative_id_numbers.txt"
                        sorted_id_numbers = sorted(list(all_creative_id_numbers))
                        with open(creative_id_numbers_file, 'w', encoding='utf-8') as f:
                            for creative_id_num in sorted_id_numbers:
                                f.write(f"{creative_id_num}\n")
                        print(f"💾 Saved {len(sorted_id_numbers)} unique creativeId numbers to: {creative_id_numbers_file.name}")
                    
                    # Save all content.js URLs to file
                    if all_content_js_urls:
                        content_js_urls_file = debug_path / "all_content_js_urls.txt"
                        sorted_urls = sorted(list(all_content_js_urls))
                        with open(content_js_urls_file, 'w', encoding='utf-8') as f:
                            for url in sorted_urls:
                                f.write(f"{url}\n")
                        print(f"💾 Saved {len(sorted_urls)} unique content.js URLs to: {content_js_urls_file.name}")
                    
            except Exception as e:
                print(f"   ❌ Error in pagination loop: {e}")
            
            # Save traffic tracker data
            print(f"\n📊 Saving traffic statistics...")
            traffic_summary = {
                'api_responses': len(tracker.api_responses),
                'timestamp': datetime.now().isoformat()
            }
            
            traffic_file = debug_path / "traffic_summary.json"
            with open(traffic_file, 'w', encoding='utf-8') as f:
                json.dump(traffic_summary, f, indent=2, ensure_ascii=False)
            print(f"   ✓ Saved to: {traffic_file}")
            print(f"   API responses: {traffic_summary['api_responses']}")
            
            # Save cache statistics
            cache_stats = get_cache_statistics()
            print(f"\n💾 Cache Statistics:")
            cache_file = debug_path / "cache_statistics.json"
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_stats, f, indent=2, ensure_ascii=False)
            print(f"   ✓ Saved to: {cache_file}")
            print(f"   Cache hits: {cache_stats['hits']}")
            print(f"   Cache misses: {cache_stats['misses']}")
            print(f"   Hit rate: {cache_stats['hit_rate']:.1f}%")
            print(f"   Bytes saved: {cache_stats['bytes_saved'] / 1024:.1f} KB")
            
            # Save content.js responses if any were captured
            if content_js_responses:
                print(f"\n📄 Captured {len(content_js_responses)} content.js responses")
                contentjs_file = debug_path / "content_js_responses.json"
                contentjs_data = [
                    {
                        'url': resp.url if hasattr(resp, 'url') else 'unknown',
                        'status': resp.status if hasattr(resp, 'status') else 'unknown',
                        'size': len(str(resp)) if resp else 0
                    }
                    for resp in content_js_responses
                ]
                with open(contentjs_file, 'w', encoding='utf-8') as f:
                    json.dump(contentjs_data, f, indent=2, ensure_ascii=False)
                print(f"   ✓ Saved to: {contentjs_file}")
            
        except Exception as e:
            print(f"\n❌ Error during navigation: {e}")
            traceback.print_exc()
        
        finally:
            await browser.close()
    
    # Summary
    print(f"\n{'='*80}")
    print("CAPTURE COMPLETE")
    print(f"{'='*80}")
    print(f"SearchCreatives calls captured: {len(search_creatives_calls)}")
    print(f"Cookies captured: {len(all_cookies)}")
    print(f"Debug folder: {debug_path.absolute()}")
    print(f"\nFiles saved:")
    print(f"  - searchcreatives_request_*.json (request headers)")
    print(f"  - searchcreatives_response_*_meta.json (response headers)")
    print(f"  - searchcreatives_response_*_body.json (response body)")
    print(f"  - cookies.json (all cookies)")
    print(f"  - traffic_summary.json (traffic statistics)")
    print(f"  - cache_statistics.json (cache performance)")
    print(f"  - content_js_responses.json (content.js captures)")
    print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Google Ads Transparency Center Stress Test Scraper (OPTIMIZED with Batch Processing)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
OPTIMIZATION:
  Each worker processes batches of creatives with session reuse:
  - First creative: Full HTML load (524 KB) + extract cookies
  - Remaining creatives: API-only with gzip (179 KB each)
  - Average: 181 KB per creative (65%% bandwidth savings)

Examples:
  # Process all pending URLs with 10 concurrent workers (no rotation)
  %(prog)s --max-concurrent 10
  
  # Process with automatic IP rotation every 7 minutes
  %(prog)s --max-concurrent 20 --enable-rotation
  
  # Process 100 URLs with 20 concurrent workers
  %(prog)s --max-concurrent 20 --max-urls 100
  
  # Custom batch size (default: 20)
  %(prog)s --max-concurrent 10 --batch-size 10
  
  # Force IP rotation before starting (bypasses 7-minute cooldown)
  %(prog)s --max-concurrent 10 --force-rotation
  
  # Without proxy
  %(prog)s --max-concurrent 10 --no-proxy
  
  # High concurrency with rotation (careful with rate limits!)
  %(prog)s --max-concurrent 50 --enable-rotation

IP Rotation:
  - Disabled by default (static IP throughout)
  - Use --enable-rotation to enable automatic rotation every 7 minutes
  - Use --force-rotation to rotate once at startup (bypasses cooldown)
  - After rotation, waits 30 seconds for IP to stabilize
        """
    )
    
    parser.add_argument('--max-concurrent', type=int, default=DEFAULT_MAX_CONCURRENT,
                        help=f'Maximum number of concurrent workers (default: {DEFAULT_MAX_CONCURRENT})')
    parser.add_argument('--max-urls', type=int, 
                        help='Maximum number of URLs to process (default: all pending)')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE,
                        help=f'Number of creatives per batch (default: {DEFAULT_BATCH_SIZE})')
    parser.add_argument('--no-proxy', action='store_true', 
                        help='Disable proxy (use direct connection)')
    parser.add_argument('--partial-proxy', action='store_true',
                        help='Use proxy only for HTML+API, bypass for content.js (saves ~70%% proxy bandwidth)')
    parser.add_argument('--enable-rotation', action='store_true',
                        help='Enable automatic IP rotation every 7 minutes')
    parser.add_argument('--force-rotation', action='store_true',
                        help='Force IP rotation once at startup (bypasses 7-minute cooldown)')
    parser.add_argument('--no-cache-stats', action='store_true',
                        help='Disable cache statistics display (for minimal output)')
    parser.add_argument('--test-advertiser', action='store_true',
                        help='Test mode: Visit fixed advertiser page and capture SearchCreatives API calls')
    
    args = parser.parse_args()
    
    # Run test mode if requested
    if args.test_advertiser:
        try:
            asyncio.run(test_advertiser_page())
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n\n❌ Error: {e}")
            traceback.print_exc()
            sys.exit(1)
        return
    
    # Otherwise run normal stress test
    try:
        asyncio.run(run_stress_test(
            max_concurrent=args.max_concurrent,
            max_urls=args.max_urls,
            use_proxy=not args.no_proxy,
            force_rotation=args.force_rotation,
            enable_rotation=args.enable_rotation,
            show_cache_stats=not args.no_cache_stats,
            batch_size=args.batch_size,
            use_partial_proxy=args.partial_proxy
        ))
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

