#!/usr/bin/env python3
"""
Google Ads Transparency Center - Advertiser Batch Scraper with Proxies

This script processes batches of advertisers from the database, scraping their creatives
using the SearchCreatives API with pagination. It combines proxy management from 
stress_test_scraper_optimized.py with advertiser scraping logic from parser_of_advertiser.py.

Features:
- Batch processing of 20 advertisers per worker
- API-based proxy acquisition from MagicTransparency API
- Status tracking in PostgreSQL advertisers table
- Cumulative page limit (500 pages per batch)
- Thread-safe row claiming with SELECT FOR UPDATE SKIP LOCKED
- Bulk creative insertion to creatives_fresh table

Usage:
    # Process with default settings (3 workers, batch size 20)
    python3 advertiser_batch_scraper.py
    
    # Process with custom concurrency
    python3 advertiser_batch_scraper.py --max-concurrent 5
    
    # Process limited number of batches for testing
    python3 advertiser_batch_scraper.py --max-concurrent 1 --max-batches 1
"""

import asyncio
import sys
import psycopg2
import argparse
import time
import json
import traceback
import random
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
from pathlib import Path
from io import StringIO

try:
    import httpx
except ImportError as e:
    print("ERROR: Missing dependencies")
    print("Install: pip install httpx")
    sys.exit(1)

try:
    from playwright.async_api import async_playwright
except ImportError as e:
    print(f"ERROR: Missing dependency: {e}")
    sys.exit(1)

# Import from existing modules
try:
    from google_ads_config import ENABLE_STEALTH_MODE
    from google_ads_cache import create_cache_aware_route_handler
    from google_ads_browser import _create_route_handler
    from google_ads_traffic import TrafficTracker, _get_user_agent
except ImportError as e:
    print(f"ERROR: Could not import required functions: {e}")
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
PROXY_ACQUIRE_URL = f"{API_DOMAIN}/api/proxies/acquire?job=advertisers"
PROXY_ACQUIRE_SECRET = "ad2a58397cf97c8bdf5814a95e33b2c17490933d9255e3e10d55ed36a665449e"
PROXY_ACQUIRE_TIMEOUT = 30  # Retry every 30 seconds if API fails

# Batch Processing Configuration
DEFAULT_MAX_CONCURRENT = 3   # Number of concurrent workers
DEFAULT_BATCH_SIZE = 20      # Number of advertisers per batch
MAX_PAGINATION_PAGES = 10000  # Safety limit per advertiser
CUMULATIVE_PAGE_LIMIT = 500  # Cumulative page limit per batch

# Delay Configuration
PAGINATION_DELAY_RANGE_SECONDS = (1, 3)  # Delay between pagination requests
COOKIE_PAGE_SLEEP_SECONDS = 3  # Sleep after loading cookie page

# Global state for proxy acquisition
proxy_acquire_lock: Optional[asyncio.Lock] = None  # Serializes API proxy acquisition

# Logging configuration
VERBOSE_LOGGING = False  # Set to True for detailed logs


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

@contextmanager
def get_db_connection():
    """Context manager for PostgreSQL database connections."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def _log(level: str, message: str, **kwargs: Any) -> None:
    """Structured logging helper with verbosity control."""
    global VERBOSE_LOGGING
    
    # Always show ERROR and WARN
    if level in ('ERROR', 'WARN'):
        try:
            if kwargs:
                print(f"[{level}] {message} | {json.dumps(kwargs, ensure_ascii=False)}", flush=True)
            else:
                print(f"[{level}] {message}", flush=True)
        except Exception:
            print(f"[{level}] {message}", flush=True)
        return
    
    # Show INFO only in verbose mode
    if VERBOSE_LOGGING:
        try:
            if kwargs:
                print(f"[{level}] {message} | {json.dumps(kwargs, ensure_ascii=False)}", flush=True)
            else:
                print(f"[{level}] {message}", flush=True)
        except Exception:
            print(f"[{level}] {message}", flush=True)


def _compact_log(message: str) -> None:
    """Compact logging for important progress updates (always shown)."""
    print(message, flush=True)


def normalize_pagination_key(token: Optional[str]) -> Optional[str]:
    """Normalize pagination token by adding padding if needed."""
    if not token or not isinstance(token, str):
        return token
    t = token.strip()
    try:
        if len(t) % 4 != 0:
            t += "=" * (4 - (len(t) % 4))
    except Exception:
        pass
    return t


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
    """
    headers = {"X-Incoming-Secret": PROXY_ACQUIRE_SECRET}
    
    retry_count = 0
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
                    retry_count += 1
                    if retry_count == 1 or retry_count % 5 == 0:  # Only log first failure and every 5th
                        _log("WARN", f"Proxy API returned {response.status_code}, retrying... (attempt {retry_count})")
        except Exception as e:
            retry_count += 1
            if retry_count == 1 or retry_count % 5 == 0:
                _log("WARN", f"Failed to acquire proxy, retrying... (attempt {retry_count}): {str(e)[:50]}")
        
        await asyncio.sleep(PROXY_ACQUIRE_TIMEOUT)


# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

def get_advertisers_batch_and_mark_processing(batch_size: int = None) -> List[Dict[str, Any]]:
    """
    Get a batch of advertisers and atomically mark them as processing.
    
    Selects advertisers where:
    - name contains "Apps" (case-insensitive)
    - status is NULL, 'failed', or 'pending' (NOT 'processing')
    
    Uses SELECT FOR UPDATE SKIP LOCKED to prevent race conditions where multiple
    workers could fetch the same advertisers.
    
    Args:
        batch_size: Number of advertisers to fetch (default: from DEFAULT_BATCH_SIZE config)
        
    Returns:
        List of advertiser dictionaries with advertiser_id, advertiser_name
    """
    if batch_size is None:
        batch_size = DEFAULT_BATCH_SIZE
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Atomic operation: SELECT + UPDATE in same transaction
        cursor.execute("""
            WITH selected AS (
                SELECT advertiser_id, advertiser_name
                FROM advertisers
                WHERE advertiser_name ILIKE %s
                  AND (status IS NULL OR status IN ('failed', 'pending'))
                ORDER BY advertiser_id
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            )
            UPDATE advertisers
            SET status = 'processing'
            FROM selected
            WHERE advertisers.advertiser_id = selected.advertiser_id
            RETURNING advertisers.advertiser_id, advertisers.advertiser_name
        """, ('%Apps%', batch_size))
        
        rows = cursor.fetchall()
        conn.commit()  # Commit immediately to release locks
        cursor.close()
        
        advertisers = []
        for row in rows:
            advertiser = {
                'advertiser_id': row[0],
                'advertiser_name': row[1]
            }
            advertisers.append(advertiser)
        
        return advertisers


def reset_batch_to_pending(advertiser_batch: List[Dict[str, Any]], worker_id: int) -> int:
    """
    Reset all advertisers in a batch from 'processing' back to 'pending'.
    
    This is used when:
    - Cookie acquisition fails
    - Batch processing encounters fatal error
    - Worker needs to abandon batch
    
    Args:
        advertiser_batch: List of advertiser dicts
        worker_id: Worker ID for logging
        
    Returns:
        Number of advertisers reset
    """
    if not advertiser_batch:
        return 0
    
    reset_count = 0
    for adv in advertiser_batch:
        try:
            # Only reset if still in 'processing' status
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE advertisers 
                    SET status = 'pending'
                    WHERE advertiser_id = %s 
                      AND status = 'processing'
                """, (adv['advertiser_id'],))
                if cursor.rowcount > 0:
                    reset_count += 1
                conn.commit()
                cursor.close()
        except Exception as e:
            _log("ERROR", f"[Worker {worker_id}] Failed to reset {adv.get('advertiser_id')}: {e}")
    
    return reset_count


def update_advertiser_status(
    advertiser_id: str, 
    status: str, 
    daily_7: Optional[int] = None,
    last_scraped_at: Optional[datetime] = None
):
    """
    Update advertiser status in the database.
    
    Args:
        advertiser_id: Advertiser ID (AR...)
        status: New status ('processing', 'completed', 'failed', 'pending')
        daily_7: Optional daily_7 count (ads per day from API field 4 & 5 average)
        last_scraped_at: Optional timestamp when scraped (defaults to current UTC)
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # If last_scraped_at not provided but status is completed, use current time
        if last_scraped_at is None and status == 'completed':
            last_scraped_at = datetime.utcnow()
        
        # Try to update with optional columns, fall back to basic if they don't exist
        try:
            if daily_7 is not None and last_scraped_at is not None:
                cursor.execute("""
                    UPDATE advertisers
                    SET status = %s,
                        daily_7 = %s,
                        last_scraped_at = %s
                    WHERE advertiser_id = %s
                """, (status, daily_7, last_scraped_at, advertiser_id))
            else:
                cursor.execute("""
                    UPDATE advertisers
                    SET status = %s
                    WHERE advertiser_id = %s
                """, (status, advertiser_id))
            conn.commit()
        except psycopg2.errors.UndefinedColumn:
            # Optional columns don't exist, use basic update
            conn.rollback()
            cursor.execute("""
                UPDATE advertisers
                SET status = %s
                WHERE advertiser_id = %s
            """, (status, advertiser_id))
            conn.commit()
        finally:
            cursor.close()


def insert_creatives_batch(creative_ids: List[str], advertiser_id: str) -> Dict[str, int]:
    """
    Bulk insert creatives to creatives_fresh table.
    
    Uses staging temp table + COPY for performance.
    On duplicate creative_id: ignore (ON CONFLICT DO NOTHING)
    created_at: set to 2015-<current_month>-<current_day>
    
    Args:
        creative_ids: List of creative IDs (CR...)
        advertiser_id: Advertiser ID (AR...)
        
    Returns:
        Stats dict: {'input': N, 'new_rows': X, 'duplicates': Y}
    """
    stats = {'input': len(creative_ids), 'new_rows': 0, 'duplicates': 0}
    if not creative_ids:
        return stats
    
    # Create date in 2015-MM-DD format
    created_date = datetime.now().strftime('2015-%m-%d')
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            try:
                # Create temp staging table
                cursor.execute("""
                    CREATE TEMP TABLE staging_creatives (
                        creative_id   TEXT,
                        advertiser_id TEXT
                    ) ON COMMIT DROP;
                """)
                
                # Prepare CSV data
                buffer = StringIO()
                buffer.write('creative_id,advertiser_id\n')
                for cr in creative_ids:
                    buffer.write(f"{cr},{advertiser_id}\n")
                buffer.seek(0)
                
                # COPY data to staging table
                cursor.copy_expert(
                    """
                    COPY staging_creatives (creative_id, advertiser_id)
                    FROM STDIN WITH (FORMAT CSV, HEADER TRUE)
                    """,
                    buffer
                )
                
                # Count new vs duplicate
                cursor.execute("""
                    SELECT 
                        COUNT(*) FILTER (WHERE cf.creative_id IS NULL) AS new_count,
                        COUNT(*) FILTER (WHERE cf.creative_id IS NOT NULL) AS duplicate_count
                    FROM staging_creatives s
                    LEFT JOIN creatives_fresh cf ON s.creative_id = cf.creative_id
                """)
                new_count, duplicate_count = cursor.fetchone()
                stats['new_rows'] = int(new_count or 0)
                stats['duplicates'] = int(duplicate_count or 0)
                
                # Insert new creatives (excluding duplicates)
                cursor.execute(
                    """
                    INSERT INTO creatives_fresh (creative_id, advertiser_id, created_at)
                    SELECT s.creative_id, s.advertiser_id, %s::timestamp
                    FROM staging_creatives s
                    LEFT JOIN creatives_fresh cf ON s.creative_id = cf.creative_id
                    WHERE cf.creative_id IS NULL
                    ON CONFLICT (creative_id) DO NOTHING
                    """,
                    (created_date,)
                )
                
                conn.commit()
                cursor.close()
                
            except Exception as e:
                conn.rollback()
                if cursor:
                    cursor.close()
                raise
            
        return stats
    except Exception as e:
        _log("ERROR", f"Error inserting creatives batch: {e}")
        return stats


def reset_stuck_processing_advertisers():
    """
    Reset advertisers stuck in 'processing' status back to 'pending'.
    Should be called on startup to clean up from previous crashes.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE advertisers
            SET status = 'pending'
            WHERE status = 'processing'
              AND advertiser_name ILIKE %s
        """, ('%Apps%',))
        reset_count = cursor.rowcount
        conn.commit()
        cursor.close()
        return reset_count


def get_statistics() -> Dict[str, int]:
    """Get current advertisers table statistics."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Optimized single query with CASE WHEN
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status IS NULL) as null_count,
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'processing') as processing,
                COUNT(*) FILTER (WHERE status = 'completed') as completed,
                COUNT(*) FILTER (WHERE status = 'failed') as failed
            FROM advertisers 
            WHERE advertiser_name ILIKE %s
        """, ('%Apps%',))
        
        row = cursor.fetchone()
        cursor.close()
        
        return {
            'total': row[0],
            'null': row[1],
            'pending': row[2],
            'processing': row[3],
            'completed': row[4],
            'failed': row[5]
        }


# ============================================================================
# SCRAPING FUNCTIONS
# ============================================================================

async def get_cookies_once(
    proxy_config: Dict[str, str],
    worker_id: int,
    region: str = "anywhere"
) -> List[Dict[str, Any]]:
    """
    Get cookies once for entire batch by visiting the base URL.
    
    Args:
        proxy_config: Proxy configuration dict
        worker_id: Worker identifier for logging
        region: Region parameter (default: "anywhere")
        
    Returns:
        List of cookie dictionaries
    """
    import re
    
    advertiser_url = f"https://adstransparency.google.com/?region={region}"
    
    _compact_log(f"[Worker {worker_id}] 🍪 Getting cookies for batch...")
    
    try:
        async with async_playwright() as p:
            # Launch browser with proxy
            browser = await p.chromium.launch(
                headless=True,
                args=['--disable-dev-shm-usage', '--disable-plugins'],
                proxy=proxy_config
            )
            
            user_agent = _get_user_agent()
            chrome_version_match = re.search(r'Chrome/(\d+)', user_agent)
            chrome_version = chrome_version_match.group(1) if chrome_version_match else '130'
            
            context = await browser.new_context(
                user_agent=user_agent,
                ignore_https_errors=True,
                extra_http_headers={
                    'sec-ch-ua': f'"Chromium";v="{chrome_version}", "Google Chrome";v="{chrome_version}", "Not?A_Brand";v="99"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"'
                }
            )
            
            # Cache-aware route handler
            tracker = TrafficTracker()
            route_handler = _create_route_handler(tracker)
            cache_aware_handler = create_cache_aware_route_handler(tracker, route_handler)
            await context.route('**/*', cache_aware_handler)
            
            page = await context.new_page()
            
            # Apply stealth mode if available
            if STEALTH_AVAILABLE and ENABLE_STEALTH_MODE:
                await Stealth().apply_stealth_async(page)
            
            # Navigate to base URL to get cookies
            _log("INFO", f"[Worker {worker_id}] Visiting base URL for cookies")
            await page.goto(advertiser_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(COOKIE_PAGE_SLEEP_SECONDS)
            
            # Extract cookies
            cookies = await context.cookies()
            _compact_log(f"[Worker {worker_id}] ✓ Got {len(cookies)} cookies")
            
            await browser.close()
            
            return cookies
            
    except Exception as e:
        _log("ERROR", f"[Worker {worker_id}] Failed to get cookies: {e}")
        return []


async def scrape_advertiser_creatives(
    advertiser_id: str,
    cookies: List[Dict[str, Any]],
    proxy_config: Dict[str, str],
    worker_id: int,
    region: str = "anywhere"
) -> Dict[str, Any]:
    """
    Scrape creatives for a single advertiser using provided cookies.
    
    Process:
    1. Use provided cookies to call SearchCreatives API with pagination
    2. Collect all creative IDs
    
    Args:
        advertiser_id: Advertiser ID (AR...)
        cookies: List of cookie dicts from browser session
        proxy_config: Proxy configuration dict
        worker_id: Worker identifier for logging
        region: Region parameter (default: "anywhere")
        
    Returns:
        Dict with creative_ids, pages_scraped, success, error
    """
    import re
    
    # Calculate date range: current UTC - 7 days to current UTC
    date_to = datetime.now(timezone.utc).date()
    date_from = date_to - timedelta(days=7)
    date_to_str = date_to.strftime('%Y%m%d')
    date_from_str = date_from.strftime('%Y%m%d')
    
    advertiser_url = f"https://adstransparency.google.com/?region={region}"
    
    result = {
        'advertiser_id': advertiser_id,
        'creative_ids': [],
        'pages_scraped': 0,
        'ads_daily': 0,
        'success': False,
        'error': None
    }
    
    try:
        # Use cookies for SearchCreatives API calls
        user_agent = _get_user_agent()
        chrome_version_match = re.search(r'Chrome/(\d+)', user_agent)
        chrome_version = chrome_version_match.group(1) if chrome_version_match else '130'
        cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        custom_headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded",
            "cookie": cookie_header,
            "origin": "https://adstransparency.google.com",
            "referer": advertiser_url,
            "user-agent": user_agent,
            "x-framework-xsrf-token": "",
            "x-same-domain": "1",
            "sec-ch-ua": f'"Chromium";v="{chrome_version}", "Google Chrome";v="{chrome_version}", "Not?A_Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"'
        }
        
        api_url = "https://adstransparency.google.com/anji/_/rpc/SearchService/SearchCreatives?authuser="
        
        # Build httpx proxy format
        # Extract host:port from proxy_server (e.g., "http://hub-us-8.litport.net:31337")
        proxy_host_port = proxy_config['server'].replace('http://', '').replace('https://', '')
        proxy_username = proxy_config['username']
        proxy_password = proxy_config['password']
        http_proxy_url = f"http://{proxy_username}:{proxy_password}@{proxy_host_port}"
        httpx_proxies = {"http://": http_proxy_url, "https://": http_proxy_url}
        
        # First API request
        first_body = {
            "2": 40,
            "3": {
                "4": 3,
                "6": int(date_from_str),
                "7": int(date_to_str),
                "12": {"1": "", "2": True},
                "13": {"1": [advertiser_id]},
                "14": [5]
            },
            "7": {"1": 1, "2": 39, "3": 2268}
        }
        post_data = "f.req=" + urllib.parse.quote(json.dumps(first_body, separators=(',', ':')))
        
        async with httpx.AsyncClient(timeout=30.0, proxies=httpx_proxies) as client:
            # First request with retry
            response = None
            for attempt in range(3):
                try:
                    r = await client.post(api_url, headers=custom_headers, content=post_data)
                    if r.status_code == 200:
                        response = r
                        break
                    await asyncio.sleep(2 ** attempt)
                except Exception:
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
            
            if response is None:
                result['error'] = "First SearchCreatives request failed"
                return result
            
            # Parse first response
            creative_ids = []
            pagination_key = None
            ads_daily = 0
            
            try:
                resp_json = response.json()
                pagination_key = resp_json.get("2")
                
                # Extract ads_daily from fields "4" and "5" (average of both values)
                val4 = resp_json.get("4")
                val5 = resp_json.get("5")
                if isinstance(val4, str) and val4.isdigit() and isinstance(val5, str) and val5.isdigit():
                    ads_daily = (int(val4) + int(val5)) // 2
                    result['ads_daily'] = ads_daily
                
                # Extract creative IDs from items
                items = resp_json.get("1", [])
                if isinstance(items, list):
                    for it in items:
                        if isinstance(it, dict):
                            cr = it.get("2")
                            if isinstance(cr, str) and cr.startswith("CR"):
                                creative_ids.append(cr)
                
                result['pages_scraped'] = 1
                _log("INFO", f"[Worker {worker_id}] Page 1: {len(creative_ids)} creatives, daily_7={ads_daily}")
            except Exception as e:
                result['error'] = f"Failed to parse first response: {e}"
                return result
            
            # Pagination
            pages = 1
            last_log_pages = 1  # Track when we last logged to reduce noise
            while pagination_key and pages < MAX_PAGINATION_PAGES:
                # Random delay between requests
                delay = random.uniform(PAGINATION_DELAY_RANGE_SECONDS[0], PAGINATION_DELAY_RANGE_SECONDS[1])
                await asyncio.sleep(delay)
                
                pages += 1
                
                paginated_body = {
                    "2": 40,
                    "3": {
                        "4": 3,
                        "6": int(date_from_str),
                        "7": int(date_to_str),
                        "12": {"1": "", "2": True},
                        "13": {"1": [advertiser_id]},
                        "14": [5]
                    },
                    "4": normalize_pagination_key(pagination_key),
                    "7": {"1": 1, "2": 39, "3": 2268}
                }
                paginated_post = "f.req=" + urllib.parse.quote(json.dumps(paginated_body, separators=(',', ':')))
                
                # Retry logic for pagination
                paginated_resp = None
                for attempt in range(3):
                    try:
                        paginated_resp = await client.post(api_url, headers=custom_headers, content=paginated_post)
                        if paginated_resp.status_code == 200:
                            break
                        await asyncio.sleep(2 ** attempt)
                    except Exception:
                        if attempt < 2:
                            await asyncio.sleep(2 ** attempt)
                
                if not paginated_resp or paginated_resp.status_code != 200:
                    _log("WARN", f"[Worker {worker_id}] Pagination stopped at page {pages}: HTTP error")
                    break
                
                # Parse paginated response
                try:
                    paginated_json = paginated_resp.json()
                    items = paginated_json.get("1", [])
                    before = len(creative_ids)
                    if isinstance(items, list):
                        for it in items:
                            if isinstance(it, dict):
                                cr = it.get("2")
                                if isinstance(cr, str) and cr.startswith("CR"):
                                    creative_ids.append(cr)
                    
                    added = len(creative_ids) - before
                    result['pages_scraped'] = pages
                    
                    # Compact logging: only log every 10 pages or verbose mode
                    if pages % 10 == 0 or VERBOSE_LOGGING:
                        _log("INFO", f"[Worker {worker_id}] Page {pages}: {len(set(creative_ids))} creatives total")
                        last_log_pages = pages
                    
                    pagination_key = paginated_json.get("2")
                    if not pagination_key:
                        # Final log if we haven't logged recently
                        if pages != last_log_pages:
                            _log("INFO", f"[Worker {worker_id}] Completed: {pages} pages, {len(set(creative_ids))} creatives")
                        break
                except Exception as e:
                    _log("WARN", f"[Worker {worker_id}] Failed to parse page {pages}: {e}")
                    break
        
        # Success
        result['creative_ids'] = sorted(list(set(creative_ids)))
        result['success'] = True
        
    except Exception as e:
        result['error'] = f"{type(e).__name__}: {str(e)}"
        _log("ERROR", f"[Worker {worker_id}] Error scraping {advertiser_id}: {result['error']}")
    
    return result


# ============================================================================
# WORKER FUNCTION
# ============================================================================

async def worker(
    worker_id: int,
    semaphore: asyncio.Semaphore,
    stats: Dict[str, Any],
    stats_lock: asyncio.Lock,
    batch_size: int = None,
    max_batches: Optional[int] = None
):
    """
    Worker coroutine that continuously processes batches of advertisers.
    
    Each batch:
    1. Acquires proxy from API
    2. Processes up to batch_size advertisers
    3. Tracks cumulative pages across batch
    4. Stops if cumulative pages >= 500 after completing each advertiser
    
    Args:
        worker_id: Unique worker identifier
        semaphore: Semaphore to control concurrency
        stats: Shared statistics dictionary
        stats_lock: Lock for updating shared statistics
        batch_size: Number of advertisers per batch
        max_batches: Optional limit on number of batches to process
    """
    global proxy_acquire_lock
    
    if batch_size is None:
        batch_size = DEFAULT_BATCH_SIZE
    
    batches_processed = 0
    
    while True:
        async with semaphore:
            try:
                # Check if we've hit max_batches limit
                if max_batches and batches_processed >= max_batches:
                    _log("INFO", f"[Worker {worker_id}] Reached max_batches limit ({max_batches})")
                    break
                
                # Get next batch of advertisers
                advertiser_batch = get_advertisers_batch_and_mark_processing(batch_size=batch_size)
                
                if not advertiser_batch:
                    # No more pending advertisers
                    break
                
                _compact_log(f"[Worker {worker_id}] 📦 Batch: {len(advertiser_batch)} advertisers")
                
                # Acquire proxy from API (serialized with lock)
                async with proxy_acquire_lock:
                    proxy_config = await acquire_proxy_from_api()
                    proxy_server = proxy_config['server'].replace('http://', '')
                    _log("INFO", f"[Worker {worker_id}] Got proxy: {proxy_server}")
                
                # Get cookies ONCE for entire batch
                cookies = await get_cookies_once(proxy_config, worker_id)
                
                if not cookies:
                    _compact_log(f"[Worker {worker_id}] ⚠️  Failed to get cookies, skipping batch")
                    # Reset all advertisers in batch back to pending for retry
                    reset_count = reset_batch_to_pending(advertiser_batch, worker_id)
                    _compact_log(f"[Worker {worker_id}] 🔄 Reset {reset_count} advertisers to pending")
                    continue
                
                # Process advertisers in batch
                cumulative_pages = 0
                batch_start_time = time.time()
                
                for i, advertiser in enumerate(advertiser_batch):
                    # Validate advertiser structure
                    if not isinstance(advertiser, dict) or 'advertiser_id' not in advertiser:
                        _log("ERROR", f"[Worker {worker_id}] Invalid advertiser structure: {advertiser}")
                        continue
                    
                    advertiser_id = advertiser.get('advertiser_id')
                    advertiser_name = advertiser.get('advertiser_name', 'Unknown')
                    
                    _compact_log(f"[Worker {worker_id}] [{i+1}/{len(advertiser_batch)}] {advertiser_id} - {advertiser_name[:30]}")
                    
                    # Scrape advertiser using shared cookies
                    scrape_result = await scrape_advertiser_creatives(
                        advertiser_id=advertiser_id,
                        cookies=cookies,
                        proxy_config=proxy_config,
                        worker_id=worker_id
                    )
                    
                    # Update cumulative pages
                    cumulative_pages += scrape_result.get('pages_scraped', 0)
                    
                    # Handle result
                    if scrape_result.get('success'):
                        # Insert creatives to database
                        creative_ids = scrape_result.get('creative_ids', [])
                        insert_stats = insert_creatives_batch(creative_ids, advertiser_id)
                        
                        # Extract ads_daily for daily_7 column
                        ads_daily = scrape_result.get('ads_daily', 0)
                        
                        # Update advertiser status to completed with last_scraped_at and daily_7
                        update_advertiser_status(
                            advertiser_id, 
                            'completed',
                            daily_7=ads_daily,
                            last_scraped_at=datetime.utcnow()
                        )
                        
                        # Update shared statistics
                        async with stats_lock:
                            stats['completed'] += 1
                            stats['total_creatives'] += len(creative_ids)
                            stats['total_pages'] += scrape_result.get('pages_scraped', 0)
                        
                        _compact_log(f"[Worker {worker_id}] ✅ {advertiser_id} - {len(creative_ids)} creatives, "
                             f"{scrape_result.get('pages_scraped', 0)} pages, daily_7={ads_daily} "
                             f"(+{insert_stats['new_rows']} new, {insert_stats['duplicates']} dup)")
                        _log("INFO", f"Cumulative pages in batch: {cumulative_pages}")
                    else:
                        # Mark as failed and log full error
                        error_msg = scrape_result.get('error', 'Unknown error')
                        update_advertiser_status(advertiser_id, 'failed')
                        
                        async with stats_lock:
                            stats['failed'] += 1
                        
                        # Log full error message
                        _compact_log(f"[Worker {worker_id}] ❌ {advertiser_id} - Failed: {error_msg[:80]}")
                        _log("ERROR", f"[Worker {worker_id}] Full error for {advertiser_id} ({advertiser_name}): {error_msg}")
                    
                    # Check cumulative page limit AFTER completing advertiser
                    if cumulative_pages >= CUMULATIVE_PAGE_LIMIT:
                        _compact_log(f"[Worker {worker_id}] ⚠️  Page limit reached: {cumulative_pages}/{CUMULATIVE_PAGE_LIMIT}")
                        
                        # Reset remaining unprocessed advertisers to pending
                        remaining = advertiser_batch[i+1:]
                        if remaining:
                            reset_count = reset_batch_to_pending(remaining, worker_id)
                            _compact_log(f"[Worker {worker_id}] 🔄 Reset {reset_count} unfinished advertisers to pending")
                        
                        break
                
                batch_duration = time.time() - batch_start_time
                batches_processed += 1
                
                async with stats_lock:
                    stats['batches_completed'] += 1
                
                _compact_log(f"[Worker {worker_id}] ✓ Batch done: {batch_duration:.1f}s, {cumulative_pages} pages\n")
                
            except Exception as e:
                _log("ERROR", f"[Worker {worker_id}] Batch processing error: {e}")
                traceback.print_exc()
                
                # Reset any advertisers still in 'processing' status back to 'pending'
                # This handles crashes/exceptions during batch processing
                try:
                    if 'advertiser_batch' in locals() and advertiser_batch:
                        reset_count = reset_batch_to_pending(advertiser_batch, worker_id)
                        if reset_count > 0:
                            _compact_log(f"[Worker {worker_id}] 🔄 Reset {reset_count} stuck advertisers to pending after error")
                except Exception as reset_error:
                    _log("ERROR", f"[Worker {worker_id}] Failed to reset stuck advertisers: {reset_error}")


# ============================================================================
# MAIN
# ============================================================================

async def run_scraper(max_concurrent: int = None, batch_size: int = None, max_batches: Optional[int] = None):
    """
    Run the advertiser batch scraper with concurrent workers.
    
    Args:
        max_concurrent: Maximum number of concurrent workers
        batch_size: Number of advertisers per batch
        max_batches: Optional limit on number of batches to process
    """
    if max_concurrent is None:
        max_concurrent = DEFAULT_MAX_CONCURRENT
    if batch_size is None:
        batch_size = DEFAULT_BATCH_SIZE
    
    print("="*80)
    print("GOOGLE ADS TRANSPARENCY CENTER - ADVERTISER BATCH SCRAPER")
    print("="*80)
    
    # Reset any stuck 'processing' status from previous crashes
    print("\n🔄 Checking for stuck 'processing' advertisers...")
    reset_count = reset_stuck_processing_advertisers()
    if reset_count > 0:
        print(f"   Reset {reset_count} stuck advertisers to 'pending'")
    else:
        print("   No stuck advertisers found")
    
    # Get initial statistics
    db_stats = get_statistics()
    print(f"\nAdvertisers Table Statistics (name contains 'Apps'):")
    print(f"  Total:      {db_stats['total']}")
    print(f"  NULL:       {db_stats['null']}")
    print(f"  Pending:    {db_stats['pending']}")
    print(f"  Processing: {db_stats['processing']}")
    print(f"  Completed:  {db_stats['completed']}")
    print(f"  Failed:     {db_stats['failed']}")
    
    available = db_stats['null'] + db_stats['pending'] + db_stats['failed']
    if available == 0:
        print("\n⚠️  No advertisers available to process")
        return
    
    # Initialize global proxy acquisition lock
    global proxy_acquire_lock
    proxy_acquire_lock = asyncio.Lock()
    
    print(f"\nScraper Configuration:")
    print(f"  Max concurrent workers: {max_concurrent}")
    print(f"  Advertisers per batch:  {batch_size}")
    print(f"  Cumulative page limit:  {CUMULATIVE_PAGE_LIMIT} pages per batch")
    print(f"  Date range:             Current UTC - 7 days to current UTC")
    print(f"  Proxy source:           MagicTransparency API")
    print(f"  Verbose logging:        {'✓ ON' if VERBOSE_LOGGING else '✗ OFF (use --verbose for details)'}")
    if max_batches:
        print(f"  Max batches:            {max_batches} (test mode)")
    
    # Shared statistics
    stats = {
        'completed': 0,
        'failed': 0,
        'batches_completed': 0,
        'total_creatives': 0,
        'total_pages': 0,
        'start_time': time.time()
    }
    stats_lock = asyncio.Lock()
    
    # Create semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrent)
    
    print(f"\n🚀 Starting {max_concurrent} concurrent workers...")
    print("="*80)
    
    start_time = time.time()
    
    try:
        # Create worker tasks
        workers = [
            worker(i, semaphore, stats, stats_lock, batch_size, max_batches)
            for i in range(max_concurrent)
        ]
        
        # Wait for all workers to complete
        await asyncio.gather(*workers)
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    
    # Final summary
    total_duration = time.time() - start_time
    
    print(f"\n{'='*80}")
    print("SCRAPER COMPLETE")
    print(f"{'='*80}")
    print(f"Total duration:       {total_duration:.1f}s ({total_duration/60:.1f} min)")
    print(f"Batches processed:    {stats['batches_completed']}")
    print(f"Advertisers completed: {stats['completed']}")
    print(f"Advertisers failed:   {stats['failed']}")
    print(f"Total creatives:      {stats['total_creatives']}")
    print(f"Total pages scraped:  {stats['total_pages']}")
    if stats['completed'] > 0:
        print(f"Avg creatives/advertiser: {stats['total_creatives']/stats['completed']:.1f}")
        print(f"Avg pages/advertiser:     {stats['total_pages']/stats['completed']:.1f}")


def main():
    parser = argparse.ArgumentParser(
        description='Google Ads Transparency Center - Advertiser Batch Scraper',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process with default settings (3 workers, batch size 20)
  %(prog)s
  
  # Process with custom concurrency
  %(prog)s --max-concurrent 5
  
  # Test mode: single batch
  %(prog)s --max-concurrent 1 --max-batches 1
  
  # Verbose mode for debugging
  %(prog)s --verbose
  
  # Custom batch size
  %(prog)s --batch-size 10
        """
    )
    
    parser.add_argument('--max-concurrent', type=int, default=DEFAULT_MAX_CONCURRENT,
                        help=f'Maximum number of concurrent workers (default: {DEFAULT_MAX_CONCURRENT})')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE,
                        help=f'Number of advertisers per batch (default: {DEFAULT_BATCH_SIZE})')
    parser.add_argument('--max-batches', type=int,
                        help='Maximum number of batches to process (for testing)')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose logging (shows all INFO logs)')
    
    args = parser.parse_args()
    
    # Set global verbose logging flag
    global VERBOSE_LOGGING
    VERBOSE_LOGGING = args.verbose
    
    try:
        asyncio.run(run_scraper(
            max_concurrent=args.max_concurrent,
            batch_size=args.batch_size,
            max_batches=args.max_batches
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

