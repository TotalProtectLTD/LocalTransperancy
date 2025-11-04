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
from datetime import datetime
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
    Returns dict with keys: id, transparency_id, transparency_name, scraping_attempts
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


async def collect_advertiser_creatives(advertiser_id: str, region: str = "anywhere") -> Dict[str, Any]:
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
        
        # Minimal blocking rules (images, fonts, stylesheets, media)
        async def blocking_route(route):
            req = route.request
            if req.resource_type in ("image", "media", "font", "stylesheet"):
                await route.abort()
            else:
                await route.continue_()
        await context.route('**/*', blocking_route)

        page = await context.new_page()
        
        if STEALTH_AVAILABLE and ENABLE_STEALTH_MODE:
            await Stealth().apply_stealth_async(page)
        
        # Navigate once to capture cookies
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
            "12": {"1": "", "2": True},
            "13": {"1": [advertiser_id]},
            "14": [5]
        },
        "7": {"1": 1, "2": 0, "3": 2268}
    }
    post_data = "f.req=" + urllib.parse.quote(json.dumps(one_shot_body, separators=(',', ':')))
    
    async with httpx.AsyncClient(timeout=30.0, proxy=proxy_info['http_proxy_url']) as client:
        response = await client.post(api_url, headers=custom_headers, content=post_data)
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
    
    # Extract objects "4" and "5" from response JSON and compute average as total_ads
    total_ads = None
    try:
        resp_json = response.json()
        val4 = resp_json.get("4")
        val5 = resp_json.get("5")
        if isinstance(val4, str) and val4.isdigit() and isinstance(val5, str) and val5.isdigit():
            total_ads = (int(val4) + int(val5)) // 2
    except Exception:
        total_ads = None
    
    return {
        "advertiser_id": advertiser_id,
        "cookies_count": len(cookies),
        "ads_total": total_ads,
        "debug_files": [
            str((debug_path / "searchcreatives_request_headers.json").absolute()),
            str((debug_path / "searchcreatives_response_headers.json").absolute()),
            str((debug_path / "searchcreatives_response_body.txt").absolute())
        ]
    }


def update_ads_total(server_advertiser_id: int, ads_total: int) -> bool:
    """PATCH ads_total to local API for the given server advertiser id."""
    try:
        url = f"{API_DOMAIN}/api/advertisers/{server_advertiser_id}"
        headers = {
            "X-Incoming-Secret": PROXY_ACQUIRE_SECRET,
            "Content-Type": "application/json"
        }
        payload = {"ads_total": ads_total}
        with httpx.Client(timeout=15.0) as client:
            r = client.patch(url, headers=headers, json=payload)
            return r.status_code >= 200 and r.status_code < 300
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Google Ads Transparency Center - Single Advertiser Collector',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--advertiser-id', required=False, help='Advertiser ID (AR...) to collect creatives for; if omitted, fetches from API')
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
        
        result = asyncio.run(collect_advertiser_creatives(advertiser_id))
        
        # Attach server advertiser metadata if available
        if advertiser_meta:
            result['server_advertiser_id'] = advertiser_meta.get('id')
            result['advertiser_name'] = advertiser_meta.get('transparency_name')
            result['scraping_attempts'] = advertiser_meta.get('scraping_attempts')
            # If ads_total computed, PATCH it to local API
            if result.get('ads_total') is not None:
                updated = update_ads_total(advertiser_meta.get('id'), int(result['ads_total']))
                result['ads_total_updated'] = bool(updated)
        
        print(json.dumps(result, ensure_ascii=False))
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

