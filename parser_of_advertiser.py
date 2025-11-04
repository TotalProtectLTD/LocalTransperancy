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

# Proxy acquisition configuration
PROXY_ACQUIRE_URL = "https://magictransparency.com/api/proxies/acquire?job=advertisers"
PROXY_ACQUIRE_SECRET = "ad2a58397cf97c8bdf5814a95e33b2c17490933d9255e3e10d55ed36a665449e"

# legacy configuration removed
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


# proxy and rotation logic removed


# batch scraping removed


# worker/dispatcher removed


async def collect_advertiser_creatives(advertiser_id: str, region: str = "US") -> Dict[str, Any]:
    """
    Single-task flow:
    1) Load advertiser page once to obtain cookies
    2) Use cookies to call SearchCreatives with pagination
    3) Return collected creative identifiers (no content.js analysis)
    """
    import re
    import urllib.parse
    from google_ads_traffic import _get_user_agent
    
    advertiser_url = f"https://adstransparency.google.com/advertiser/{advertiser_id}?region={region}"
    
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
        page = await context.new_page()
        
        if STEALTH_AVAILABLE and ENABLE_STEALTH_MODE:
            await Stealth().apply_stealth_async(page)
        
        # Navigate once to capture cookies
        await page.goto(advertiser_url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        cookies = await context.cookies()
        await browser.close()
    
    # Prepare SearchCreatives requests
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
    
    # Date range: today only by default (yyyymmdd)
    today_int = int(datetime.utcnow().strftime('%Y%m%d'))
    
    base_post_data = {
        "2": 40,
        "3": {
            "4": 3,
            "6": today_int,
            "7": today_int,
            "12": {"1": "", "2": True},
            "13": {"1": [advertiser_id]},
            "14": [5]
        },
        "7": {"1": 1, "2": 39, "3": 2268}
    }
    
    pagination_token: Optional[str] = None
    page_num = 0
    max_pages = 1000
    total_creatives = 0
    all_creative_ids: set[str] = set()
    all_creative_id_numbers: set[str] = set()
    all_content_js_urls: set[str] = set()
    
    async with httpx.AsyncClient(timeout=30.0, proxies=proxy_info['httpx_proxies']) as client:
        while page_num < max_pages:
            page_num += 1
            if pagination_token:
                post_data_json = {**base_post_data, "4": pagination_token}
            else:
                post_data_json = base_post_data.copy()
            post_data = "f.req=" + urllib.parse.quote(json.dumps(post_data_json, separators=(',', ':')))
            response = await client.post(api_url, headers=custom_headers, content=post_data)
            if response.status_code != 200:
                break
            try:
                response_json = response.json()
            except Exception:
                break
            creatives = response_json.get("1", [])
            total_creatives += len(creatives)
            for creative in creatives:
                cr_id = creative.get("2", "")
                if cr_id:
                    all_creative_ids.add(cr_id)
                try:
                    url = creative.get("3", {}).get("1", {}).get("4", "")
                    if url:
                        all_content_js_urls.add(url)
                        if "creativeId=" in url:
                            from urllib.parse import urlparse, parse_qs
                            parsed_url = urlparse(url)
                            q = parse_qs(parsed_url.query)
                            cid = q.get("creativeId", [""])[0]
                            if cid:
                                all_creative_id_numbers.add(cid)
                except Exception:
                    pass
            pagination_token = response_json.get("2", "")
            if not pagination_token:
                break
    
    return {
        "advertiser_id": advertiser_id,
        "pages": page_num,
        "total_creatives": total_creatives,
        "creative_ids": sorted(list(all_creative_ids)),
        "creative_id_numbers": sorted(list(all_creative_id_numbers)),
        "content_js_urls": sorted(list(all_content_js_urls)),
        "cookies_count": len(cookies)
    }


def main():
    parser = argparse.ArgumentParser(
        description='Google Ads Transparency Center - Single Advertiser Collector',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--advertiser-id', required=True, help='Advertiser ID (AR...) to collect creatives for')
    args = parser.parse_args()
    
    try:
        result = asyncio.run(collect_advertiser_creatives(args.advertiser_id))
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

