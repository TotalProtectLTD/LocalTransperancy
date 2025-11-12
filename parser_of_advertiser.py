#!/usr/bin/env python3
"""
Google Ads Transparency Center - Single Advertiser Collector

Purpose:
  - For a given advertiser_id (AR...), open the advertiser page once to obtain cookies
  - Use those cookies to call SearchCreatives with pagination
  - Collect creative identifiers (CR..., creativeId numbers) and content.js URLs
  - No content.js analysis, no batching, no proxy/rotation

Usage:
  python3 parser_of_advertiser.py --advertiser-id AR05226884764400615425
"""

import asyncio
import sys
import argparse
import json
import traceback
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from pathlib import Path

try:
    import httpx
except ImportError as e:
    print("ERROR: Missing dependencies")
    print("Install: pip install httpx")
    sys.exit(1)

try:
    from google_ads_config import ENABLE_STEALTH_MODE
    from playwright.async_api import async_playwright
except ImportError as e:
    print(f"ERROR: Missing dependency: {e}")
    sys.exit(1)

# Cache + blocking integrations
try:
    from google_ads_cache import create_cache_aware_route_handler
    from google_ads_browser import _create_route_handler
    from google_ads_traffic import TrafficTracker
except ImportError as e:
    print(f"ERROR: Missing dependency: {e}")
    sys.exit(1)

# Stealth mode support
try:
    from playwright_stealth import Stealth
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

# API configuration
API_DOMAIN = "https://magictransparency.com"
PROXY_ACQUIRE_URL = f"{API_DOMAIN}/api/proxies/acquire?job=advertisers"
PROXY_ACQUIRE_SECRET = "ad2a58397cf97c8bdf5814a95e33b2c17490933d9255e3e10d55ed36a665449e"

# legacy configuration removed

# Advertiser acquisition configuration
ADVERTISER_NEXT_URL = f"{API_DOMAIN}/api/advertisers/next-for-scraping"
# legacy configuration removed

# Timezone support
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

# Optional DB
try:
    import psycopg2
except ImportError:
    psycopg2 = None

# Pagination and DB config
PAGINATION_DELAY_RANGE_SECONDS = (1, 3)
MAX_PAGINATION_PAGES = 5000

DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432,
}
try:
    from bigquery_creatives_postgres import DB_CONFIG as _BQ_DB_CONFIG
    DB_CONFIG = _BQ_DB_CONFIG
except Exception:
    pass


# ----------------------------------------------------------------------------
# Small structured logger and helpers
# ----------------------------------------------------------------------------
def _log(level: str, message: str, **kwargs: Any) -> None:
    try:
        if kwargs:
            print(f"[{level}] {message} | {json.dumps(kwargs, ensure_ascii=False)}")
        else:
            print(f"[{level}] {message}")
    except Exception:
        print(f"[{level}] {message}")


def normalize_pagination_key(token: Optional[str]) -> Optional[str]:
    if not token or not isinstance(token, str):
        return token
    t = token.strip()
    try:
        if len(t) % 4 != 0:
            t += "=" * (4 - (len(t) % 4))
    except Exception:
        pass
    return t


async def acquire_proxy_for_run() -> Optional[Dict[str, Any]]:
    """
    Acquire a proxy for this run and return formats for Playwright and httpx.
    Returns None if acquisition fails.
    """
    headers = {"X-Incoming-Secret": PROXY_ACQUIRE_SECRET}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(PROXY_ACQUIRE_URL, headers=headers)
            if resp.status_code != 200:
                return None
            data = resp.json()
            conn = data.get("connection_string")
            if not conn:
                return None
            # Parse: scheme://user:pass@host:port
            from urllib.parse import urlparse
            parsed = urlparse(conn)
            username = parsed.username or ""
            password = parsed.password or ""
            host = parsed.hostname or ""
            port = parsed.port
            if not host or not port:
                return None
            # Build formats
            http_proxy_url = f"http://{username}:{password}@{host}:{port}" if username else f"http://{host}:{port}"
            playwright_proxy = {
                "server": f"http://{host}:{port}",
                "username": username,
                "password": password
            }
            httpx_proxies = {"http://": http_proxy_url, "https://": http_proxy_url}
            return {
                "raw": data,
                "playwright_proxy": playwright_proxy,
                "httpx_proxies": httpx_proxies,
                "http_proxy_url": http_proxy_url
            }
    except Exception:
        return None
    

async def acquire_next_advertiser() -> Optional[Dict[str, Any]]:
    """
    Acquire next advertiser to scrape from server.
    Returns dict with keys: id, transparency_id, optional last_scraped_at
    Returns None if acquisition fails or malformed.
    """
    headers = {"X-Incoming-Secret": PROXY_ACQUIRE_SECRET}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(ADVERTISER_NEXT_URL, headers=headers)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not data or 'transparency_id' not in data:
                return None
            return data
    except Exception:
        return None


# proxy and rotation logic removed


# batch scraping removed


# worker/dispatcher removed


async def collect_advertiser_creatives(advertiser_id: str, region: str = "anywhere", date_from_str: Optional[str] = None, date_to_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Single-task flow:
    1) Load advertiser page once to obtain cookies
    2) Use cookies to call SearchCreatives with pagination
    3) Return collected creative identifiers (no content.js analysis)
    """
    import re
    import urllib.parse
    from google_ads_traffic import _get_user_agent
    
    advertiser_url = f"https://adstransparency.google.com/advertiser/{advertiser_id}?region={region}&platform=YOUTUBE"
    
    # Acquire proxy for this run
    proxy_info = await acquire_proxy_for_run()
    if not proxy_info:
        raise RuntimeError("Failed to acquire proxy for this run")
    
    async with async_playwright() as p:
        # Launch minimal browser
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-dev-shm-usage', '--disable-plugins'],
            proxy=proxy_info['playwright_proxy']
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
        
        # Cache-aware route handler + URL-based blocking via optimized modules
        tracker = TrafficTracker()
        route_handler = _create_route_handler(tracker)
        cache_aware_handler = create_cache_aware_route_handler(tracker, route_handler)
        await context.route('**/*', cache_aware_handler)

        page = await context.new_page()
        
        if STEALTH_AVAILABLE and ENABLE_STEALTH_MODE:
            await Stealth().apply_stealth_async(page)
        
        # Navigate once to capture cookies
        _log("INFO", "Visiting HTML for cookies", advertiser_id=advertiser_id)
        await page.goto(advertiser_url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        cookies = await context.cookies()
        await browser.close()
    
    # Prepare SearchCreatives single request
    debug_path = Path("debug")
    debug_path.mkdir(exist_ok=True)
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
            
    one_shot_body = {
        "2": 40,
        "3": {
            "4": 3,
            **({"6": int(date_from_str)} if date_from_str else {}),
            **({"7": int(date_to_str)} if date_to_str else {}),
            "12": {"1": "", "2": True},
            "13": {"1": [advertiser_id]},
            "14": [5]
        },
        "7": {"1": 1, "2": 39, "3": 2268}
    }
    post_data = "f.req=" + urllib.parse.quote(json.dumps(one_shot_body, separators=(',', ':')))
    
    async with httpx.AsyncClient(timeout=30.0, proxies=proxy_info['httpx_proxies']) as client:
        # Retry first call
        response = None
        backoffs = [1, 2]
        for i in range(3):
            try:
                r = await client.post(api_url, headers=custom_headers, content=post_data)
                if r.status_code == 200:
                    response = r
                    break
                if i < 2:
                    await asyncio.sleep(backoffs[i] if i < len(backoffs) else backoffs[-1])
            except Exception:
                if i < 2:
                    await asyncio.sleep(backoffs[i] if i < len(backoffs) else backoffs[-1])
        if response is None:
            raise RuntimeError("First SearchCreatives request failed")
        # Save request headers and body
        (debug_path / "searchcreatives_request_headers.json").write_text(
            json.dumps({
                "url": api_url,
                "headers": custom_headers,
                "body_json": one_shot_body,
                "body_encoded": post_data
            }, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        # Save response headers
        (debug_path / "searchcreatives_response_headers.json").write_text(
            json.dumps(dict(response.headers), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        # Save raw response body
        (debug_path / "searchcreatives_response_body.txt").write_bytes(response.content)
    
    # Extract ads_daily from fields "4" and "5"; collect creatives and pagination
    ads_daily = 0
    pagination_key = None
    creative_ids: list[str] = []
    try:
        resp_json = response.json()
        pagination_key = resp_json.get("2")
        val4 = resp_json.get("4")
        val5 = resp_json.get("5")
        if isinstance(val4, str) and val4.isdigit() and isinstance(val5, str) and val5.isdigit():
            ads_daily = (int(val4) + int(val5)) // 2
        _log("INFO", f"[1] SearchCreatives - ads_daily={ads_daily}")
        items = resp_json.get("1", [])
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    cr = it.get("2")
                    if isinstance(cr, str) and cr.startswith("CR"):
                        creative_ids.append(cr)
    except Exception:
        ads_daily = 0

    # Pagination
    try:
        import random as _random
        pages = 1
        while pagination_key and pages < MAX_PAGINATION_PAGES:
            delay = _random.uniform(PAGINATION_DELAY_RANGE_SECONDS[0], PAGINATION_DELAY_RANGE_SECONDS[1])
            _log("INFO", f"[{pages+1}] Paused for {int(delay)}s. Next SearchCreatives page {pages+1}")
            await asyncio.sleep(delay)
            paginated_body = {
                "2": 40,
                "3": {
                    "4": 3,
                    **({"6": int(date_from_str)} if date_from_str else {}),
                    **({"7": int(date_to_str)} if date_to_str else {}),
                    "12": {"1": "", "2": True},
                    "13": {"1": [advertiser_id]},
                    "14": [5]
                },
                "4": normalize_pagination_key(pagination_key),
                "7": {"1": 1, "2": 39, "3": 2268}
            }
            paginated_post = "f.req=" + urllib.parse.quote(json.dumps(paginated_body, separators=(',', ':')))
            
            # Retry logic for HTTP errors (especially 5xx)
            max_retries = 3
            retry_delays = [10, 20, 30]  # Longer delays for network problems
            paginated_resp = None
            paginated_json = None
            
            for attempt in range(max_retries):
                try:
                    async with httpx.AsyncClient(timeout=30.0, proxies=proxy_info['httpx_proxies']) as _c:
                        paginated_resp = await _c.post(api_url, headers=custom_headers, content=paginated_post)
                    
                    # Check HTTP status code
                    if paginated_resp.status_code >= 500:
                        # 5xx errors - might be transient (API or proxy issue)
                        if attempt < max_retries - 1:
                            retry_delay = retry_delays[attempt]
                            _log("WARN", f"[{pages+1}] HTTP {paginated_resp.status_code} error, retrying in {retry_delay}s", 
                                 page=pages+1, status_code=paginated_resp.status_code, attempt=attempt+1, max_retries=max_retries)
                            await asyncio.sleep(retry_delay)
                            continue
                        else:
                            # All retries exhausted
                            response_preview = paginated_resp.text[:200] if paginated_resp.text else "No response body"
                            _log("ERROR", f"[{pages+1}] Pagination stopped: HTTP {paginated_resp.status_code} after {max_retries} retries", 
                                 page=pages+1, status_code=paginated_resp.status_code, response_preview=response_preview)
                            break
                    elif paginated_resp.status_code >= 400:
                        # 4xx errors - client error, likely permanent
                        response_preview = paginated_resp.text[:200] if paginated_resp.text else "No response body"
                        _log("ERROR", f"[{pages+1}] Pagination stopped: HTTP {paginated_resp.status_code} client error", 
                             page=pages+1, status_code=paginated_resp.status_code, response_preview=response_preview)
                        break
                    elif paginated_resp.status_code != 200:
                        # Other non-200 status codes
                        _log("WARN", f"[{pages+1}] Unexpected HTTP status {paginated_resp.status_code}", 
                             page=pages+1, status_code=paginated_resp.status_code)
                    
                    # Try to parse JSON
                    try:
                        paginated_json = paginated_resp.json()
                        break  # Success - exit retry loop
                    except Exception as e:
                        response_preview = paginated_resp.text[:200] if paginated_resp.text else "No response body"
                        if attempt < max_retries - 1:
                            retry_delay = retry_delays[attempt]
                            _log("WARN", f"[{pages+1}] JSON parse failed, retrying in {retry_delay}s", 
                                 page=pages+1, status_code=paginated_resp.status_code, error=str(e)[:100], attempt=attempt+1)
                            await asyncio.sleep(retry_delay)
                            continue
                        else:
                            _log("ERROR", f"[{pages+1}] Pagination stopped: JSON parse failed after {max_retries} retries", 
                                 page=pages+1, status_code=paginated_resp.status_code, error=str(e)[:100], response_preview=response_preview)
                            break
                            
                except httpx.TimeoutException as e:
                    if attempt < max_retries - 1:
                        retry_delay = retry_delays[attempt]
                        _log("WARN", f"[{pages+1}] Request timeout, retrying in {retry_delay}s", 
                             page=pages+1, attempt=attempt+1, error=str(e)[:100])
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        _log("ERROR", f"[{pages+1}] Pagination stopped: request timeout after {max_retries} retries", 
                             page=pages+1, error=str(e)[:100])
                        break
                except httpx.TransportError as e:
                    # Network/transport error (includes proxy errors)
                    if attempt < max_retries - 1:
                        retry_delay = retry_delays[attempt]
                        _log("WARN", f"[{pages+1}] Transport error, retrying in {retry_delay}s", 
                             page=pages+1, attempt=attempt+1, error=str(e)[:100])
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        _log("ERROR", f"[{pages+1}] Pagination stopped: transport error after {max_retries} retries", 
                             page=pages+1, error=str(e)[:100])
                        break
                except Exception as e:
                    # Other unexpected errors
                    if attempt < max_retries - 1:
                        retry_delay = retry_delays[attempt]
                        _log("WARN", f"[{pages+1}] Unexpected error, retrying in {retry_delay}s", 
                             page=pages+1, attempt=attempt+1, error=str(e)[:100])
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        _log("ERROR", f"[{pages+1}] Pagination stopped: unexpected error after {max_retries} retries", 
                             page=pages+1, error=str(e)[:200])
                        break
            
            # If we didn't get a valid response, exit pagination
            if paginated_json is None:
                break
            
            # Process the response
            items = paginated_json.get("1", [])
            if isinstance(items, list):
                before = len(creative_ids)
                for it in items:
                    if isinstance(it, dict):
                        cr = it.get("2")
                        if isinstance(cr, str) and cr.startswith("CR"):
                            creative_ids.append(cr)
                added = len(creative_ids) - before
                _log("INFO", f"[{pages+1}] Page collected +{added} creatives (total {len(set(creative_ids))})")
            new_pagination_key = paginated_json.get("2")
            if not new_pagination_key:
                _log("INFO", f"[{pages+1}] Pagination completed: no more pages (pagination_key is empty)")
            pagination_key = new_pagination_key
            pages += 1
        if pages >= MAX_PAGINATION_PAGES:
            _log("WARN", "Pagination stopped: reached MAX_PAGINATION_PAGES limit", max_pages=MAX_PAGINATION_PAGES)
    except Exception as e:
        _log("ERROR", "Pagination stopped: exception occurred", error=str(e)[:200])
        pass

    return {
        "advertiser_id": advertiser_id,
        "cookies_count": len(cookies),
        "ads_daily": ads_daily,
        "pagination_key": pagination_key,
        "creative_ids": sorted(list(set(creative_ids))),
        "debug_files": [
            str((debug_path / "searchcreatives_request_headers.json").absolute()),
            str((debug_path / "searchcreatives_response_headers.json").absolute()),
            str((debug_path / "searchcreatives_response_body.txt").absolute())
        ]
    }


def update_ads_daily(server_advertiser_id: int, ads_daily: int) -> bool:
    """PATCH ads_daily to API for the given server advertiser id."""
    try:
        url = f"{API_DOMAIN}/api/advertisers/{server_advertiser_id}"
        headers = {
            "X-Incoming-Secret": PROXY_ACQUIRE_SECRET,
            "Content-Type": "application/json"
        }
        payload = {"ads_daily": ads_daily}
        with httpx.Client(timeout=15.0) as client:
            r = client.patch(url, headers=headers, json=payload)
            ok = 200 <= r.status_code < 300
            _log("INFO", "PATCH ads_daily", status=r.status_code, ok=ok, ads_daily=ads_daily)
            return ok
    except Exception:
        return False


def compute_dates_from_meta(advertiser_meta: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Compute date_to (UTC today) and date_from (Pacific date from last_scraped_at or UTC-24h fallback)."""
    try:
        date_to = datetime.now(timezone.utc).date().strftime('%Y%m%d')
    except Exception:
        date_to = None
    date_from = None
    try:
        last_scraped_at = advertiser_meta.get('last_scraped_at')
        if last_scraped_at:
            iso_str = str(last_scraped_at).replace('Z', '+00:00')
            dt_utc = datetime.fromisoformat(iso_str)
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            if ZoneInfo is not None:
                pacific = ZoneInfo('America/Los_Angeles')
                dt_pacific = dt_utc.astimezone(pacific)
                date_from = dt_pacific.date().strftime('%Y%m%d')
            else:
                date_from = dt_utc.date().strftime('%Y%m%d')
        else:
            now_utc = datetime.now(timezone.utc)
            dt_utc = now_utc - timedelta(hours=24)
            if ZoneInfo is not None:
                pacific = ZoneInfo('America/Los_Angeles')
                dt_pacific = dt_utc.astimezone(pacific)
                date_from = dt_pacific.date().strftime('%Y%m%d')
            else:
                date_from = dt_utc.date().strftime('%Y%m%d')
    except Exception:
        date_from = None
    return {"date_to": date_to, "date_from": date_from}


def insert_creatives_into_db(creative_ids: list, advertiser_id: str) -> Dict[str, int]:
    """
    Efficiently insert collected creative IDs into creatives_fresh.
    - Uses staging temp table + COPY for performance
    - On duplicate creative_id: ignore (no update) EXCEPT if status='bad_ad' → reactivate to 'pending'
    - Reactivated creatives: status='pending', created_at updated, error_message cleared
    - created_at: set to 2057-<current_month>-<current_day>
    Returns stats: {'input': N, 'new_rows': X, 'duplicates': Y, 'bad_ad_reactivated': Z}
    """
    stats = {'input': len(creative_ids), 'new_rows': 0, 'duplicates': 0, 'bad_ad_reactivated': 0}
    if not creative_ids:
        return stats
    if psycopg2 is None:
        return stats
    from io import StringIO
    created_date = datetime.now().strftime('2057-%m-%d')
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TEMP TABLE staging_creatives (
                        creative_id   TEXT,
                        advertiser_id TEXT
                    ) ON COMMIT DROP;
                """)
                buffer = StringIO()
                buffer.write('creative_id,advertiser_id\n')
                for cr in creative_ids:
                    buffer.write(f"{cr},{advertiser_id}\n")
                buffer.seek(0)
                cur.copy_expert(
                    """
                    COPY staging_creatives (creative_id, advertiser_id)
                    FROM STDIN WITH (FORMAT CSV, HEADER TRUE)
                    """,
                    buffer
                )
                cur.execute("""
                    SELECT 
                        COUNT(*) FILTER (WHERE cf.creative_id IS NULL) AS new_count,
                        COUNT(*) FILTER (WHERE cf.creative_id IS NOT NULL) AS duplicate_count
                    FROM staging_creatives s
                    LEFT JOIN creatives_fresh cf ON s.creative_id = cf.creative_id
                """)
                new_count, duplicate_count = cur.fetchone()
                stats['new_rows'] = int(new_count or 0)
                stats['duplicates'] = int(duplicate_count or 0)
                
                # Reactivate existing "bad_ad" creatives: update to "pending" with new created_at
                cur.execute("""
                    UPDATE creatives_fresh cf
                    SET 
                        status = 'pending',
                        created_at = %s::timestamp,
                        advertiser_id = s.advertiser_id,
                        error_message = NULL
                    FROM staging_creatives s
                    WHERE cf.creative_id = s.creative_id 
                      AND cf.status = 'bad_ad'
                """, (created_date,))
                reactivated_count = cur.rowcount
                stats['bad_ad_reactivated'] = int(reactivated_count or 0)
                
                # Insert new creatives (excluding those that already exist)
                cur.execute(
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
        _log("INFO", "DB insert completed", 
             input=stats['input'], 
             new=stats['new_rows'], 
             duplicates=stats['duplicates'],
             bad_ad_reactivated=stats['bad_ad_reactivated'])
        return stats
    except Exception:
        return stats


def bulk_update_creatives_last_seen(creative_ids: list, seen_date_iso: str) -> Dict[str, Any]:
    summary = {
        'batches': 0,
        'updated_total': 0,
        'received_total': 0,
        'errors': []
    }
    if not creative_ids or not seen_date_iso:
        return summary
    url = f"{API_DOMAIN}/api/bulk-update-creative-last-seen"
    headers = {
        'Content-Type': 'application/json',
        'X-Incoming-Secret': PROXY_ACQUIRE_SECRET
    }
    BATCH_SIZE = 20000
    try:
        import time as _time
        with httpx.Client(timeout=30.0) as client:
            _log("INFO", "Bulk update start", total=len(creative_ids), date=seen_date_iso)
            for i in range(0, len(creative_ids), BATCH_SIZE):
                batch = creative_ids[i:i+BATCH_SIZE]
                payload = {
                    'date': seen_date_iso,
                    'transparency_creative_ids': batch
                }
                retries = 3
                attempt = 0
                backoffs = [1, 2, 4]
                while attempt < retries:
                    try:
                        resp = client.post(url, headers=headers, json=payload)
                        if resp.status_code == 200:
                            data = resp.json()
                            summary['batches'] += 1
                            summary['updated_total'] += int(data.get('updated_count', 0) or 0)
                            summary['received_total'] += int(data.get('received_count', len(batch)) or 0)
                            _log("INFO", "Bulk batch ok", batch_index=i//BATCH_SIZE, updated=data.get('updated_count'), received=data.get('received_count'))
                            break
                        elif resp.status_code in (401, 422):
                            try:
                                detail = resp.json().get('detail')
                            except Exception:
                                detail = None
                            summary['errors'].append({
                                'status': resp.status_code,
                                'detail': detail or f'HTTP {resp.status_code}',
                                'batch_index': i // BATCH_SIZE
                            })
                            _log("ERROR", "Bulk batch failed (no-retry)", batch_index=i//BATCH_SIZE, status=resp.status_code, detail=detail)
                            break
                        else:
                            attempt += 1
                            if attempt >= retries:
                                summary['errors'].append({
                                    'status': resp.status_code,
                                    'detail': f'HTTP {resp.status_code}',
                                    'batch_index': i // BATCH_SIZE
                                })
                                _log("ERROR", "Bulk batch failed (retries exhausted)", batch_index=i//BATCH_SIZE, status=resp.status_code)
                                break
                            _time.sleep(backoffs[attempt-1])
                    except httpx.TimeoutException:
                        attempt += 1
                        if attempt >= retries:
                            summary['errors'].append({'status': 'timeout', 'batch_index': i // BATCH_SIZE})
                            _log("ERROR", "Bulk batch timeout", batch_index=i//BATCH_SIZE)
                            break
                        _time.sleep(backoffs[attempt-1])
                    except httpx.TransportError as e:
                        attempt += 1
                        if attempt >= retries:
                            summary['errors'].append({'status': 'transport', 'error': str(e)[:120], 'batch_index': i // BATCH_SIZE})
                            _log("ERROR", "Bulk batch transport error", batch_index=i//BATCH_SIZE, error=str(e)[:120])
                            break
                        _time.sleep(backoffs[attempt-1])
                    except Exception as e:
                        summary['errors'].append({'status': 'exception', 'error': str(e)[:200], 'batch_index': i // BATCH_SIZE})
                        _log("ERROR", "Bulk batch exception", batch_index=i//BATCH_SIZE, error=str(e)[:200])
                        break
            _log("INFO", "Bulk update done", batches=summary['batches'], updated_total=summary['updated_total'], received_total=summary['received_total'], errors=len(summary['errors']))
    except Exception as e:
        summary['errors'].append({'status': 'exception', 'error': str(e)[:200]})
    return summary


def post_scraping_status(server_advertiser_id: int, status: str, ads_daily: Optional[int] = None, error: Optional[str] = None) -> bool:
    try:
        url = f"{API_DOMAIN}/api/advertisers/{server_advertiser_id}/scraping-status"
        headers = {
            'Content-Type': 'application/json',
            'X-Incoming-Secret': PROXY_ACQUIRE_SECRET
        }
        payload: Dict[str, Any] = {"status": status}
        if ads_daily is not None:
            payload["ads_daily"] = ads_daily
        if error:
            payload["error"] = error[:500]
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            # Use PATCH for status updates
            resp = client.patch(url, headers=headers, json=payload)
            if resp.status_code == 405 and not url.endswith('/'):
                # Common DRF pattern: requires trailing slash
                url_slash = url + '/'
                resp = client.patch(url_slash, headers=headers, json=payload)
            ok = 200 <= resp.status_code < 300
            # Log extra diagnostics on failure
            if not ok:
                allow = resp.headers.get('allow')
                location = resp.headers.get('location')
                history_statuses = [r.status_code for r in getattr(resp, 'history', [])] or None
                try:
                    body_preview = resp.text[:200]
                except Exception:
                    body_preview = None
                _log("ERROR", "Patch status failed", status_code=resp.status_code, allow=allow, location=location, history=history_statuses, body_preview=body_preview)
            else:
                _log("INFO", "Patch status", ok=ok, status_code=resp.status_code, status=status)
            return ok
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Google Ads Transparency Center - Single Advertiser Collector',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--advertiser-id', required=False, help='Advertiser ID (AR...) to collect creatives for; if omitted, fetches from API')
    parser.add_argument('--no-db-insert', action='store_true', help='Skip inserting collected creatives into PostgreSQL')
    parser.add_argument('--no-bulk-update', action='store_true', help='Skip bulk update of last_seen to external API')
    parser.add_argument('--dry-run', action='store_true', help='Do not write to DB or external APIs')
    parser.add_argument('--print-all-ids', action='store_true', help='Print full creative_ids list in stdout')
    args = parser.parse_args()

    try:
        if args.advertiser_id:
            advertiser_meta = None
            advertiser_id = args.advertiser_id
        else:
            advertiser_meta = asyncio.run(acquire_next_advertiser())
            if not advertiser_meta:
                print(json.dumps({"status": "no_advertiser"}))
                return
            advertiser_id = advertiser_meta.get('transparency_id')
            if not advertiser_id:
                raise RuntimeError('API returned invalid advertiser payload (missing transparency_id)')

        # Compute date range
        if advertiser_meta:
            date_info = compute_dates_from_meta(advertiser_meta)
        else:
            date_info = compute_dates_from_meta({"last_scraped_at": None})

        result = asyncio.run(collect_advertiser_creatives(advertiser_id, date_from_str=date_info.get('date_from'), date_to_str=date_info.get('date_to')))

        # Attach server advertiser metadata if available
        if advertiser_meta:
            result['server_advertiser_id'] = advertiser_meta.get('id')
            # Intentionally not including advertiser_name or scraping_attempts in output
            result['last_scraped_at'] = advertiser_meta.get('last_scraped_at') if 'last_scraped_at' in advertiser_meta else None
            result.update(date_info)
            if result.get('ads_daily') is not None:
                updated = update_ads_daily(advertiser_meta.get('id'), int(result['ads_daily']))
                result['ads_daily_updated'] = bool(updated)

        # DB insert
        if not args.dry_run and not args.no_db_insert:
            try:
                insert_stats = insert_creatives_into_db(result.get('creative_ids', []), advertiser_id)
                result['db_insert_stats'] = insert_stats
            except Exception:
                pass

        # Bulk last_seen update
        if not args.dry_run and not args.no_bulk_update:
            try:
                date_to_compact = date_info.get('date_to')
                seen_date_iso = None
                if date_to_compact and isinstance(date_to_compact, str) and len(date_to_compact) == 8:
                    seen_date_iso = f"{date_to_compact[0:4]}-{date_to_compact[4:6]}-{date_to_compact[6:8]}"
                bulk_stats = bulk_update_creatives_last_seen(result.get('creative_ids', []), seen_date_iso)
                result['bulk_update_stats'] = bulk_stats
            except Exception:
                pass

        # Final status
        try:
            if advertiser_meta:
                post_scraping_status(
                    advertiser_meta.get('id'),
                    status='completed',
                    ads_daily=(int(result['ads_daily']) if result.get('ads_daily') is not None else None)
                )
        except Exception:
            pass

        # Output control to avoid huge arrays
        if args.dry_run or args.print_all_ids:
            print(json.dumps(result, ensure_ascii=False))
        else:
            result_out = dict(result)
            ids = result_out.get('creative_ids') or []
            result_out['creative_ids_count'] = len(ids)
            if ids:
                result_out['creative_ids_sample'] = ids[:50]
            result_out.pop('creative_ids', None)
            print(json.dumps(result_out, ensure_ascii=False))
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        try:
            if 'advertiser_meta' in locals() and advertiser_meta and advertiser_meta.get('id'):
                post_scraping_status(advertiser_meta.get('id'), status='failed', error=str(e))
        except Exception:
            pass
        print(f"\n\n❌ Error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

