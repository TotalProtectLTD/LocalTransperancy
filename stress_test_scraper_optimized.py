#!/usr/bin/env python3
"""
Google Ads Transparency Center - Stress Test Scraper (OPTIMIZED with API Proxies)

This script performs continuous concurrent stress testing using a worker pool pattern
with bandwidth optimization through session reuse and dynamic API-based proxy acquisition.

OPTIMIZATION STRATEGY:
- Each worker processes batches of 20 creatives
- First creative: Full HTML load (524 KB) + extract cookies
- Creatives 2-20: API-only with gzip compression (179 KB each)
- Average: 181 KB per creative (65% bandwidth savings)

For 1000 creatives:
- Original: 524 MB
- Optimized: 181 MB
- Savings: 343 MB (65%)

PROXY SYSTEM:
- Dynamic proxy acquisition from MagicTransparency API
- Fresh proxy per batch (20 creatives)
- Serialized acquisition with lock (one worker at a time)
- Automatic proxy rotation handled by API
- No manual proxy configuration needed

Features:
- Batch processing (20 creatives per batch, session reuse)
- Continuous worker pool (no idle time between batches)
- Configurable concurrency limit
- Reads creative URLs from PostgreSQL creatives_fresh table
- Updates database with results (videos, app store ID, funded_by, errors)
- Real-time progress logging with rate statistics
- API-based proxy acquisition with automatic retry
- Cache statistics tracking (hit rate, bytes saved)
- Real-time cache performance monitoring

Usage:
    # Process all pending URLs with 10 concurrent workers (each processes batches of 20)
    python3 stress_test_scraper_optimized.py --max-concurrent 10
    
    # Process 100 URLs with 20 concurrent workers
    python3 stress_test_scraper_optimized.py --max-concurrent 20 --max-urls 100
    
    # Partial proxy mode (HTML+API only, content.js direct)
    python3 stress_test_scraper_optimized.py --max-concurrent 10 --partial-proxy
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
        extract_funded_by_from_api,
        extract_country_presence_from_api
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

# PostgreSQL Database Configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432
}

# API Proxy Configuration
API_DOMAIN = "https://magictransparency.com"
PROXY_ACQUIRE_URL = f"{API_DOMAIN}/api/proxies/acquire?job=creatives"
PROXY_ACQUIRE_SECRET = "ad2a58397cf97c8bdf5814a95e33b2c17490933d9255e3e10d55ed36a665449e"
PROXY_ACQUIRE_TIMEOUT = 30  # Retry every 30 seconds if API fails

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

# Global state for proxy acquisition
proxy_acquire_lock: Optional[asyncio.Lock] = None  # Serializes API proxy acquisition (one worker at a time)


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
                ORDER BY created_at DESC
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
    - video_count, video_ids, appstore_id, playstore, funded_by, scraped_at, error_message
    
    Args:
        creative_id: Database ID of the creative
        result: Scraping result dictionary
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        if result.get('success'):
            country_presence_json = json.dumps(result.get('country_presence')) if result.get('country_presence') else None
            cursor.execute("""
                UPDATE creatives_fresh
                SET status = 'completed',
                    video_count = %s,
                    video_ids = %s,
                    appstore_id = NULLIF(BTRIM(%s), ''),
                    playstore = NULLIF(BTRIM(%s), ''),
                    funded_by = %s,
                    country_presence = %s,
                    scraped_at = %s,
                    error_message = NULL
                WHERE id = %s
            """, (
                result.get('video_count', 0),
                json.dumps(result.get('videos', [])),
                result.get('appstore_id'),
                result.get('playstore_id'),
                result.get('funded_by'),
                country_presence_json,
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

async def acquire_proxy_from_api() -> Dict[str, str]:
    """
    Acquire a proxy from the API with infinite retry on failure.
    
    Makes a GET request to the MagicTransparency API to get a fresh proxy.
    Retries every 30 seconds if the request fails.
    
    Returns:
        Dict with server, username, password in Playwright format
        
    Example response from API:
        {
            "id": 9,
            "ip": "hub-us-8.litport.net",
            "port": 31337,
            "username": "iQqXMk",
            "password": "52qx4Ia84ME",
            "type": "http",
            "job": "creatives",
            "connection_string": "http://iQqXMk:52qx4Ia84ME@hub-us-8.litport.net:31337"
        }
    """
    headers = {"X-Incoming-Secret": PROXY_ACQUIRE_SECRET}
    
    while True:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(PROXY_ACQUIRE_URL, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    # Convert to Playwright proxy format (API uses 'ip' key, not 'host')
                    return {
                        "server": f"http://{data['ip']}:{data['port']}",
                        "username": data['username'],
                        "password": data['password']
                    }
                else:
                    print(f"  ⚠️  Proxy API returned {response.status_code}, retrying in {PROXY_ACQUIRE_TIMEOUT}s...")
        except Exception as e:
            print(f"  ⚠️  Failed to acquire proxy: {e}, retrying in {PROXY_ACQUIRE_TIMEOUT}s...")
        
        await asyncio.sleep(PROXY_ACQUIRE_TIMEOUT)


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
                country_presence = extract_country_presence_from_api(tracker.api_responses, first_url)
                
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
                # Use app_ids_from_base64 as fallback when app_store_id is None
                appstore_id = extraction_results.get('app_store_id')
                playstore_id = extraction_results.get('play_store_id')
                app_ids_from_base64 = extraction_results.get('app_ids_from_base64', [])
                if not appstore_id and app_ids_from_base64:
                    # Use first app ID from base64 if no direct App Store ID found
                    appstore_id = app_ids_from_base64[0]
                
                result_dict = {
                    'creative_db_id': first_creative['id'],
                    'success': True,
                    'videos': extraction_results['unique_videos'],
                    'video_count': len(extraction_results['unique_videos']),
                    'appstore_id': appstore_id,
                    'playstore_id': playstore_id,
                    'funded_by': funded_by,
                    'country_presence': country_presence,
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
                
                # Add error result for first creative
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
                
                # If first creative fails, create error results for ALL remaining creatives
                # This ensures they get marked as 'pending' instead of staying stuck as 'processing'
                print(f"    ⚠️  First creative failed - marking remaining {len(creative_batch) - 1} creatives for retry")
                for remaining_creative in creative_batch[1:]:
                    results.append({
                        'creative_db_id': remaining_creative['id'],
                        'success': False,
                        'error': f"Batch failed: First creative failed with {error_msg}",
                        'duration_ms': 0,
                        'videos': [],
                        'video_count': 0,
                        'appstore_id': None,
                        'funded_by': None
                    })
                
                # Close browser and return all results
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
                    # Use app_ids_from_base64 as fallback when app_store_id is None
                    appstore_id = api_result.get('app_store_id')
                    playstore_id = api_result.get('play_store_id')
                    app_ids_from_base64 = api_result.get('app_ids_from_base64', [])
                    if not appstore_id and app_ids_from_base64:
                        # Use first app ID from base64 if no direct App Store ID found
                        appstore_id = app_ids_from_base64[0]
                    
                    result_dict = {
                        'creative_db_id': creative['id'],
                        'success': api_result.get('success', False),
                        'videos': api_result.get('videos', []),
                        'video_count': api_result.get('video_count', 0),
                        'playstore_id': playstore_id,
                        'appstore_id': appstore_id,
                        'funded_by': api_result.get('funded_by'),
                        'country_presence': api_result.get('country_presence'),
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
    stats: Dict[str, Any],
    stats_lock: asyncio.Lock,
    show_cache_stats: bool = True,
    batch_size: int = None,
    use_partial_proxy: bool = False
):
    """
    Worker coroutine that continuously processes BATCHES of creatives from database.
    Each batch uses session reuse optimization (1 HTML load + 19 API-only).
    Acquires a fresh proxy from API for each batch.
    
    Args:
        worker_id: Unique worker identifier
        semaphore: Semaphore to control concurrency
        stats: Shared statistics dictionary
        stats_lock: Lock for updating shared statistics
        show_cache_stats: If True, display cache statistics
        batch_size: Number of creatives per batch (default: from DEFAULT_BATCH_SIZE config)
        use_partial_proxy: If True, use proxy only for HTML+API, bypass for content.js
    """
    global proxy_acquire_lock
    
    if batch_size is None:
        batch_size = DEFAULT_BATCH_SIZE
    
    while True:
        async with semaphore:
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
                
                # Acquire proxy from API (serialized with lock - one worker at a time)
                async with proxy_acquire_lock:
                    print(f"  [Worker {worker_id}] 🔄 Acquiring proxy from API...")
                    proxy_config = await acquire_proxy_from_api()
                    proxy_server = proxy_config['server'].replace('http://', '')
                    print(f"  [Worker {worker_id}] ✓ Got proxy: {proxy_server}")
                
                # Scrape entire batch (optimized with session reuse)
                results = await scrape_batch_optimized(creative_batch, proxy_config, worker_id, use_partial_proxy)
                
                # Safety check: Ensure we have results for all creatives in batch
                # If not, create error results for missing ones to prevent stuck 'processing' status
                result_creative_ids = {result.get('creative_db_id') for result in results if 'creative_db_id' in result}
                batch_creative_ids = {creative['id'] for creative in creative_batch}
                missing_creative_ids = batch_creative_ids - result_creative_ids
                
                if missing_creative_ids:
                    print(f"  ⚠️  [Worker {worker_id}] Missing results for {len(missing_creative_ids)} creatives - creating error results")
                    for missing_id in missing_creative_ids:
                        # Find the creative info
                        missing_creative = next(c for c in creative_batch if c['id'] == missing_id)
                        results.append({
                            'creative_db_id': missing_id,
                            'success': False,
                            'error': 'Missing result from batch processing - marked for retry',
                            'duration_ms': 0,
                            'videos': [],
                            'video_count': 0,
                            'appstore_id': None,
                            'funded_by': None
                        })
                
                # Update database for each result (with exception handling to prevent stuck rows)
                for result in results:
                    try:
                        creative_db_id = result.pop('creative_db_id', None)
                        if creative_db_id is None:
                            print(f"  ⚠️  [Worker {worker_id}] Skipping result without creative_db_id: {result}")
                            continue
                        
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
                    except Exception as update_error:
                        # If update fails, mark creative as pending for retry to prevent stuck status
                        print(f"  ❌ [Worker {worker_id}] Failed to update creative {creative_db_id}: {update_error}")
                        try:
                            # Try to mark as pending for retry
                            with get_db_connection() as conn:
                                cursor = conn.cursor()
                                cursor.execute("""
                                    UPDATE creatives_fresh
                                    SET status = 'pending',
                                        error_message = %s
                                    WHERE id = %s
                                """, (
                                    f"Update failed: {type(update_error).__name__} - pending retry",
                                    creative_db_id
                                ))
                                conn.commit()
                            print(f"  ✓ [Worker {worker_id}] Marked creative {creative_db_id} as pending for retry")
                        except Exception as fallback_error:
                            print(f"  ❌ [Worker {worker_id}] Failed to mark creative {creative_db_id} as pending: {fallback_error}")
                
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
                pass  # No cleanup needed


async def run_stress_test(max_concurrent: int = None, max_urls: Optional[int] = None, show_cache_stats: bool = True, batch_size: int = None, use_partial_proxy: bool = False):
    """
    Run stress test with continuous worker pool (OPTIMIZED with batch processing).
    
    Each worker processes batches of creatives with session reuse:
    - First creative: Full HTML load (524 KB) + extract cookies
    - Remaining creatives: API-only with gzip (179 KB each)
    - Average: 181 KB per creative (65% bandwidth savings)
    
    Proxies are acquired dynamically from the MagicTransparency API for each batch.
    
    Args:
        max_concurrent: Maximum number of concurrent workers (each processes batches)
        max_urls: Maximum number of URLs to process (None for unlimited)
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
    
    # Initialize global proxy acquisition lock
    global proxy_acquire_lock
    proxy_acquire_lock = asyncio.Lock()
    
    print(f"\nStress Test Configuration:")
    print(f"  Max concurrent: {max_concurrent} workers")
    print(f"  Batch size:     {batch_size} creatives per batch")
    print(f"  URLs to process: {total_pending}")
    print(f"  Optimization:   Session reuse (1 HTML + {batch_size-1} API-only per batch)")
    print(f"  Bandwidth:      ~181 KB/creative (65% savings vs 524 KB)")
    print(f"  Proxy source:   API-based (MagicTransparency API)")
    print(f"  Proxy method:   Fresh proxy per batch via {PROXY_ACQUIRE_URL}")
    print(f"  Proxy locking:  Serialized acquisition (one worker at a time)")
    if use_partial_proxy:
        print(f"  Proxy mode:     Partial (HTML+API only, content.js direct)")
        print(f"  Proxy savings:  ~70% bandwidth reduction")
    else:
        print(f"  Proxy mode:     Full (all traffic through proxy)")
    
    # Cache status at startup
    if show_cache_stats:
        print(f"\nCache System:")
        print(f"  Status:         ✅ ENABLED (two-level: memory L1 + disk L2)")
        print(f"  Caches:         main.dart.js files (~1.5-2 MB each)")
        print(f"  Expected:       98%+ hit rate after warm-up")
        print(f"  Savings:        ~1.5 GB bandwidth per 1,000 URLs")
    
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
            worker(i, semaphore, stats, stats_lock, show_cache_stats, batch_size, use_partial_proxy)
            for i in range(max_concurrent)
        ]
        
        # Wait for all workers to complete
        await asyncio.gather(*workers)
    
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
    
    print(f"\nProxy source:     MagicTransparency API")
    print(f"Database:         PostgreSQL (creatives_fresh table)")


def main():
    parser = argparse.ArgumentParser(
        description='Google Ads Transparency Center Stress Test Scraper (OPTIMIZED with API Proxies)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
OPTIMIZATION:
  Each worker processes batches of creatives with session reuse:
  - First creative: Full HTML load (524 KB) + extract cookies
  - Remaining creatives: API-only with gzip (179 KB each)
  - Average: 181 KB per creative (65%% bandwidth savings)

PROXY SYSTEM:
  Proxies are acquired dynamically from MagicTransparency API for each batch.
  - API endpoint: https://magictransparency.com/api/proxies/acquire?job=creatives
  - Fresh proxy per batch (20 creatives)
  - Serialized acquisition (one worker at a time) for even distribution
  - Automatic proxy rotation handled by API

Examples:
  # Process all pending URLs with 10 concurrent workers
  %(prog)s --max-concurrent 10
  
  # Process 100 URLs with 20 concurrent workers
  %(prog)s --max-concurrent 20 --max-urls 100
  
  # Custom batch size (default: 20)
  %(prog)s --max-concurrent 10 --batch-size 10
  
  # Partial proxy mode (HTML+API only, content.js direct)
  %(prog)s --max-concurrent 10 --partial-proxy
  
  # High concurrency (careful with rate limits!)
  %(prog)s --max-concurrent 50
        """
    )
    
    parser.add_argument('--max-concurrent', type=int, default=DEFAULT_MAX_CONCURRENT,
                        help=f'Maximum number of concurrent workers (default: {DEFAULT_MAX_CONCURRENT})')
    parser.add_argument('--max-urls', type=int, 
                        help='Maximum number of URLs to process (default: all pending)')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE,
                        help=f'Number of creatives per batch (default: {DEFAULT_BATCH_SIZE})')
    parser.add_argument('--partial-proxy', action='store_true',
                        help='Use proxy only for HTML+API, bypass for content.js (saves ~70%% proxy bandwidth)')
    parser.add_argument('--no-cache-stats', action='store_true',
                        help='Disable cache statistics display (for minimal output)')
    
    args = parser.parse_args()
    
    try:
        asyncio.run(run_stress_test(
            max_concurrent=args.max_concurrent,
            max_urls=args.max_urls,
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

