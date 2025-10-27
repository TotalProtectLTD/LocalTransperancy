#!/usr/bin/env python3
"""
Google Ads Transparency Center - Stress Test Scraper

This script performs continuous concurrent stress testing using a worker pool pattern.
Workers continuously pull pending URLs from the database and process them until none remain.

Features:
- Continuous worker pool (no idle time between batches)
- Configurable concurrency limit
- Reads creative URLs from PostgreSQL creatives_fresh table
- Updates database with results (videos, app store ID, funded_by, errors)
- Real-time progress logging with rate statistics
- Static proxy support with IP logging
- Cache statistics tracking (hit rate, bytes saved)
- Real-time cache performance monitoring

Usage:
    # Process all pending URLs with 10 concurrent workers
    python3 stress_test_scraper.py --max-concurrent 10
    
    # Process 100 URLs with 20 concurrent workers
    python3 stress_test_scraper.py --max-concurrent 20 --max-urls 100
    
    # Without proxy
    python3 stress_test_scraper.py --max-concurrent 10 --no-proxy
    
    # With IP rotation enabled
    python3 stress_test_scraper.py --max-concurrent 10 --enable-rotation
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

# Import scraping function from main scraper
try:
    from google_ads_transparency_scraper import scrape_ads_transparency_page
except ImportError:
    print("ERROR: Could not import scrape_ads_transparency_page")
    print("Make sure google_ads_transparency_scraper.py is in the same directory")
    sys.exit(1)

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

# Proxy Configuration (optional - if not provided, uses no proxy)
PROXY_HOST = "lt2.4g.iproyal.com"
PROXY_PORT = 6253
PROXY_USERNAME = "hHvEFk3"
PROXY_PASSWORD = "UqUOnEaovKOzeNv"


# IP Rotation Configuration
IPROYAL_ROTATE_URL = "https://apid.iproyal.com/v1/orders/59934727/rotate-ip/9vZGSTaLoF"
ROTATION_COOLDOWN_SECONDS = 420  # 7 minutes
ROTATION_STABILIZATION_SECONDS = 30  # Wait 30s after rotation before starting workers

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


def mark_as_processing(creative_ids: List[int]):
    """Mark creatives as processing."""
    if not creative_ids:
        return
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        placeholders = ','.join(['%s'] * len(creative_ids))
        cursor.execute(f"""
            UPDATE creatives_fresh
            SET status = 'processing'
            WHERE id IN ({placeholders})
        """, creative_ids)
        conn.commit()


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
    
    # Incomplete fletch-render errors (retry)
    if 'INCOMPLETE:' in error_msg or ('FAILED: Expected' in error_msg and 'content.js' in error_msg):
        return True, 'Incomplete fletch-render', 'retry'
    
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
        'BrokenPipeError'
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

def generate_proxy_config() -> Optional[Dict[str, str]]:
    """
    Generate proxy configuration for main scraper.
    
    Returns:
        Dict with server, username, password or None if no proxy configured
    """
    if not PROXY_HOST or not PROXY_USERNAME or not PROXY_PASSWORD:
        return None
    
    return {
        "server": f"http://{PROXY_HOST}:{PROXY_PORT}",
        "username": PROXY_USERNAME,
        "password": PROXY_PASSWORD
    }


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
    except Exception as e:
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


async def rotation_monitor(max_concurrent: int, stats: Dict[str, Any], stats_lock: asyncio.Lock):
    """
    Background task that monitors and triggers IP rotation every 7 minutes.
    
    Args:
        max_concurrent: Maximum number of concurrent workers allowed
        stats: Shared statistics dictionary
        stats_lock: Lock for updating shared statistics
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
                    
                    # Check current IP after rotation
                    proxy_config = generate_proxy_config()
                    current_ip = await get_current_ip(proxy_config)
                    if current_ip:
                        print(f"  ✓ New IP: {current_ip}")
                    
                    print(f"{'='*80}\n")


# ============================================================================
# SCRAPING
# ============================================================================

async def scrape_single_url(creative: Dict[str, Any], proxy_config: Optional[Dict[str, str]], debug: bool = False) -> Dict[str, Any]:
    """
    Scrape a single URL using the main scraper function.
    
    Args:
        creative: Creative dictionary with id, url, etc.
        proxy_config: Optional proxy configuration dict
        debug: If True, enable detailed logging (not used - main scraper has its own logging)
        
    Returns:
        Result dictionary with success status, compatible with database update
    """
    start_time = time.time()
    
    try:
        # Call the main scraper function
        result = await scrape_ads_transparency_page(
            page_url=creative['url'],
            use_proxy=False,  # Don't use mitmproxy
            external_proxy=proxy_config  # Use external proxy if provided
        )
        
        # Convert result to stress test format (including cache statistics)
        return {
            'success': result.get('success', False),
            'videos': result.get('videos', []),
            'video_count': result.get('video_count', 0),
            'appstore_id': result.get('app_store_id'),
            'funded_by': result.get('funded_by'),
            'real_creative_id': result.get('real_creative_id'),
            'duration_ms': result.get('duration_ms', 0),
            'error': '; '.join(result.get('errors', [])) if not result.get('success') else None,
            # Cache statistics
            'cache_hits': result.get('cache_hits', 0),
            'cache_misses': result.get('cache_misses', 0),
            'cache_bytes_saved': result.get('cache_bytes_saved', 0),
            'cache_hit_rate': result.get('cache_hit_rate', 0.0),
            'cache_total_requests': result.get('cache_total_requests', 0)
        }
    
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        error_msg = f"{type(e).__name__}: {str(e)}"
        
        # Log the error to console for visibility in concurrent environments
        print(f"  ❌ EXCEPTION during scrape: {error_msg[:150]}")
        import sys
        sys.stdout.flush()
        
        return {
            'success': False,
            'error': error_msg,
            'duration_ms': duration,
            'videos': [],
            'video_count': 0,
            'appstore_id': None,
            'funded_by': None
        }


# ============================================================================
# MAIN
# ============================================================================

async def worker(
    worker_id: int,
    semaphore: asyncio.Semaphore,
    proxy_config: Optional[Dict[str, str]],
    stats: Dict[str, Any],
    stats_lock: asyncio.Lock,
    show_cache_stats: bool = True
):
    """
    Worker coroutine that continuously processes URLs from database.
    Pauses during IP rotation and 30s stabilization period.
    
    Args:
        worker_id: Unique worker identifier
        semaphore: Semaphore to control concurrency
        proxy_config: Optional proxy configuration
        stats: Shared statistics dictionary
        stats_lock: Lock for updating shared statistics
    """
    global _rotation_in_progress, _active_workers_count
    
    while True:
        # Wait if rotation is in progress
        while _rotation_in_progress:
            await asyncio.sleep(1)
        
        async with semaphore:
            # Increment active workers count
            async with _workers_lock:
                _active_workers_count += 1
            
            try:
                # Get next pending URL
                creatives = get_pending_urls(limit=1)
                
                if not creatives:
                    # No more pending URLs
                    break
                
                creative = creatives[0]
                
                # Mark as processing
                mark_as_processing([creative['id']])
                
                # Scrape URL
                result = await scrape_single_url(creative, proxy_config)
                
                # Log immediate result (for debugging concurrent issues)
                if result['success']:
                    videos = result.get('video_count', 0)
                    print(f"  ✅ Scraped: {creative['creative_id'][:15]}... ({videos} videos)")
                else:
                    error_type = result.get('error', 'Unknown')[:80]
                    print(f"  ⚠️  Failed: {creative['creative_id'][:15]}... - {error_type}")
                import sys
                sys.stdout.flush()
                
                # Update database
                update_result(creative['id'], result)
                
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
                    
                    # Print progress every 10 URLs
                    if stats['processed'] % 10 == 0:
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
                        
                        print(f"  Progress: {stats['processed']}/{stats['total_pending']} URLs "
                              f"({stats['success']} ✓, {stats['failed']} ✗{retry_info}{bad_ads_info}) "
                              f"[{rate:.1f} URL/s]{cache_info}")
                    
                    # Special cache report after first batch (to show warm-up effect)
                    if show_cache_stats and stats['processed'] == 10:
                        cache_total = stats['cache_hits'] + stats['cache_misses']
                        if cache_total > 0:
                            cache_hit_rate = (stats['cache_hits'] / cache_total) * 100
                            print(f"  ℹ️  Initial cache warm-up: {cache_hit_rate:.0f}% hit rate (will improve as cache builds)")
            finally:
                # Decrement active workers count
                async with _workers_lock:
                    _active_workers_count -= 1


async def run_stress_test(max_concurrent: int = 10, max_urls: Optional[int] = None, use_proxy: bool = True, force_rotation: bool = False, enable_rotation: bool = False, show_cache_stats: bool = True):
    """
    Run stress test with continuous worker pool.
    
    Args:
        max_concurrent: Maximum number of concurrent workers
        max_urls: Maximum number of URLs to process (None for unlimited)
        use_proxy: If True, use configured proxy; if False, no proxy
        force_rotation: If True, force IP rotation even if within cooldown period
        enable_rotation: If True, enable automatic IP rotation every 7 minutes
        show_cache_stats: If True, display cache statistics (default: True)
    """
    print("="*80)
    print("GOOGLE ADS TRANSPARENCY CENTER - STRESS TEST")
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
    
    # Setup proxy
    proxy_config = generate_proxy_config() if use_proxy else None
    
    print(f"\nStress Test Configuration:")
    print(f"  Max concurrent: {max_concurrent}")
    print(f"  URLs to process: {total_pending}")
    if proxy_config:
        print(f"  Proxy:          {PROXY_HOST}:{PROXY_PORT}")
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
    
    # Check current IP
    print("\n🔄 Checking current IP...")
    try:
        current_ip = await get_current_ip(proxy_config)
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
            worker(i, semaphore, proxy_config, stats, stats_lock, show_cache_stats)
            for i in range(max_concurrent)
        ]
        
        # Start rotation monitor as background task (only if rotation is enabled)
        if enable_rotation:
            monitor_task = asyncio.create_task(rotation_monitor(max_concurrent, stats, stats_lock))
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


def main():
    parser = argparse.ArgumentParser(
        description='Google Ads Transparency Center Stress Test Scraper (Continuous Worker Pool)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all pending URLs with 10 concurrent workers (no rotation)
  %(prog)s --max-concurrent 10
  
  # Process with automatic IP rotation every 7 minutes
  %(prog)s --max-concurrent 20 --enable-rotation
  
  # Process 100 URLs with 20 concurrent workers
  %(prog)s --max-concurrent 20 --max-urls 100
  
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
    
    parser.add_argument('--max-concurrent', type=int, default=10, 
                        help='Maximum number of concurrent workers (default: 10)')
    parser.add_argument('--max-urls', type=int, 
                        help='Maximum number of URLs to process (default: all pending)')
    parser.add_argument('--no-proxy', action='store_true', 
                        help='Disable proxy (use direct connection)')
    parser.add_argument('--enable-rotation', action='store_true',
                        help='Enable automatic IP rotation every 7 minutes')
    parser.add_argument('--force-rotation', action='store_true',
                        help='Force IP rotation once at startup (bypasses 7-minute cooldown)')
    parser.add_argument('--no-cache-stats', action='store_true',
                        help='Disable cache statistics display (for minimal output)')
    
    args = parser.parse_args()
    
    try:
        asyncio.run(run_stress_test(
            max_concurrent=args.max_concurrent,
            max_urls=args.max_urls,
            use_proxy=not args.no_proxy,
            force_rotation=args.force_rotation,
            enable_rotation=args.enable_rotation,
            show_cache_stats=not args.no_cache_stats
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

