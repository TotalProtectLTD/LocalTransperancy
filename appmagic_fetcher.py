#!/usr/bin/env python3
"""
AppMagic Data Fetcher

This script:
1. Fetches appstore_ids that need AppMagic data from magictransparency.com API
2. Uses SeleniumBase to visit AppMagic and make API requests
3. Extracts appmagic_appid and appmagic_url from responses
4. Bulk updates the server with the extracted data

Designed to be triggered by external scheduler (cron, etc.)

Usage:
    export MAGIC_TRANSPARENCY_TOKEN="your_token_here"
    python3 appmagic_fetcher.py [--limit 1000] [--batch-size 50] [--headless]
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
import requests

try:
    from seleniumbase import SB
    SELENIUMBASE_AVAILABLE = True
except ImportError:
    SELENIUMBASE_AVAILABLE = False
    print("❌ SeleniumBase is not installed!")
    print("Install it with: pip install seleniumbase")
    sys.exit(1)


# Configuration
MAGIC_TRANSPARENCY_API = "https://magictransparency.com/api/apps/appmagic"
DEFAULT_LIMIT = 1000
DEFAULT_BATCH_SIZE = 50
COOKIES_FILE = "appmagic_cookies_fresh.json"

# Default shared secret (can be overridden by env var, config file, or --secret flag)
INCOMING_SHARED_SECRET = "ad2a58397cf97c8bdf5814a95e33b2c17490933d9255e3e10d55ed36a665449e"

# Path to shared secret config file
SECRET_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "shared_secret.txt")


def load_secret_from_file() -> Optional[str]:
    """Load shared secret from config file if it exists."""
    try:
        if os.path.exists(SECRET_CONFIG_PATH):
            with open(SECRET_CONFIG_PATH, 'r') as f:
                secret = f.read().strip()
                if secret:
                    return secret
    except Exception:
        pass
    return None


def get_missing_appstore_ids(api_token: str, limit: int = DEFAULT_LIMIT, exclude_games: bool = True) -> Dict[str, Any]:
    """
    Get list of appstore_ids that need AppMagic data.
    
    Args:
        api_token: Bearer token for magictransparency.com API
        limit: Maximum number of IDs to return (default: 1000, max: 10000)
        exclude_games: Exclude apps with logical_category = 'Games' (default: True)
    
    Returns:
        Dict with 'appstore_ids' list and 'total' count
    """
    url = f"{MAGIC_TRANSPARENCY_API}/missing"
    params = {
        "limit": min(limit, 10000),  # Enforce max limit
        "exclude_games": "true" if exclude_games else "false"
    }
    
    headers = {
        "X-Incoming-Secret": api_token,
        "Accept": "application/json"
    }
    
    print(f"📥 Fetching missing appstore_ids (limit={params['limit']}, exclude_games={exclude_games})...")
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        appstore_ids = data.get("appstore_ids", [])
        total = data.get("total", len(appstore_ids))
        
        print(f"✅ Found {len(appstore_ids)} appstore_ids (total: {total})")
        return {"appstore_ids": appstore_ids, "total": total}
    
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching missing appstore_ids: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        raise


def extract_appmagic_data(appstore_id: str, sb: SB) -> Optional[Dict[str, Any]]:
    """
    Search AppMagic for appstore_id and extract appmagic_appid and appmagic_url.
    
    Args:
        appstore_id: App Store ID to search for
        sb: SeleniumBase instance with browser context
    
    Returns:
        Dict with 'appmagic_appid' and 'appmagic_url', or None if not found
    """
    url = f"https://appmagic.rocks/api/v2/search?name={appstore_id}&limit=20"
    
    try:
        # Make API request using JavaScript fetch in browser context
        response_data = sb.execute_async_script(f"""
            var callback = arguments[arguments.length - 1];
            var url = '{url}';
            fetch(url, {{
                method: 'GET',
                headers: {{
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Origin': 'https://appmagic.rocks',
                    'Referer': 'https://appmagic.rocks/top-charts/apps',
                    'Sec-Fetch-Dest': 'empty',
                    'Sec-Fetch-Mode': 'cors',
                    'Sec-Fetch-Site': 'same-origin'
                }}
            }})
            .then(response => {{
                return response.text().then(text => {{
                    callback({{
                        status: response.status,
                        body: text
                    }});
                }});
            }})
            .catch(error => {{
                callback({{
                    error: error.toString()
                }});
            }});
        """)
        
        if not isinstance(response_data, dict):
            print(f"⚠️  Unexpected response format for {appstore_id}")
            return None
        
        if 'error' in response_data:
            print(f"⚠️  Error fetching {appstore_id}: {response_data['error']}")
            return None
        
        if response_data.get('status') != 200:
            print(f"⚠️  Non-200 status for {appstore_id}: {response_data.get('status')}")
            return None
        
        # Parse JSON response
        try:
            response_json = json.loads(response_data['body'])
        except json.JSONDecodeError as e:
            print(f"⚠️  Failed to parse JSON for {appstore_id}: {e}")
            return None
        
        # Extract data from response - check if wrapped in 'data' field
        if 'data' in response_json:
            response_json = response_json['data']
        
        applications = response_json.get('applications', [])
        if not applications:
            return None
        
        app = applications[0]
        
        # Extract appmagic_appid from applications[0].id (convert to integer)
        appmagic_appid = app.get('id')
        if appmagic_appid is None:
            return None
        
        try:
            appmagic_appid = int(appmagic_appid)
        except (ValueError, TypeError):
            print(f"⚠️  Invalid appmagic_appid for {appstore_id}: {appmagic_appid}")
            return None
        
        # Extract appmagic_url from applications[0].apps_priority[].store_url
        # Find first URL containing apps.apple.com and extract slug
        appmagic_url = None
        apps_priority = app.get('apps_priority', [])
        
        for app_priority in apps_priority:
            store_url = app_priority.get('store_url', '')
            if 'apps.apple.com' in store_url:
                # Extract slug using regex: /app/([^/]+)/id\d+
                # Handles formats like:
                # - https://apps.apple.com/us/app/app-name/id1234567890
                # - https://apps.apple.com/app/app-name/id1234567890
                match = re.search(r'/app/([^/]+)/id\d+', store_url)
                if match:
                    appmagic_url = match.group(1).strip()
                    if appmagic_url:  # Ensure we got a valid slug
                        break
        
        if not appmagic_url:
            # If no apps_priority found, try other fields
            # Sometimes the URL might be in different fields
            return {
                "appmagic_appid": appmagic_appid,
                "appmagic_url": None  # Will be set to None if not found
            }
        
        return {
            "appmagic_appid": appmagic_appid,
            "appmagic_url": appmagic_url
        }
    
    except Exception as e:
        print(f"❌ Exception while processing {appstore_id}: {e}")
        return None


def bulk_update_apps(api_token: str, updates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Bulk update apps with AppMagic data.
    
    Args:
        api_token: Bearer token for magictransparency.com API
        updates: List of update dicts with appstore_id, appmagic_appid, appmagic_url
    
    Returns:
        Response dict with results, total, succeeded, failed
    """
    url = f"{MAGIC_TRANSPARENCY_API}/bulk-update"
    
    headers = {
        "X-Incoming-Secret": api_token,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    payload = {
        "updates": updates
    }
    
    print(f"📤 Sending bulk update for {len(updates)} apps...")
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        succeeded = data.get("succeeded", 0)
        failed = data.get("failed", 0)
        
        print(f"✅ Bulk update completed: {succeeded} succeeded, {failed} failed")
        return data
    
    except requests.exceptions.RequestException as e:
        print(f"❌ Error sending bulk update: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        raise


def process_appstore_ids(
    appstore_ids: List[str],
    api_token: str,
    cookies_file: str = COOKIES_FILE,
    batch_size: int = DEFAULT_BATCH_SIZE,
    headless: bool = True
) -> Dict[str, Any]:
    """
    Process appstore_ids and update server with AppMagic data.
    
    Args:
        appstore_ids: List of appstore_ids to process
        api_token: Bearer token for magictransparency.com API
        cookies_file: Path to AppMagic cookies JSON file
        batch_size: Number of apps to process before sending bulk update
        headless: Run browser in headless mode
    
    Returns:
        Dict with processing statistics
    """
    # Load cookies
    cookies_path = Path(cookies_file)
    if not cookies_path.exists():
        print(f"❌ Cookie file not found: {cookies_file}")
        return {"error": f"Cookie file not found: {cookies_file}"}
    
    with open(cookies_path, 'r') as f:
        cookies_data = json.load(f)
    
    print(f"✅ Loaded {len(cookies_data)} cookies from {cookies_file}")
    
    stats = {
        "total": len(appstore_ids),
        "processed": 0,
        "found": 0,
        "not_found": 0,
        "errors": 0,
        "updated": 0,
        "update_failed": 0
    }
    
    # Open browser with SeleniumBase
    with SB(
        uc=True,  # Undetected Chrome mode (stealth)
        headless=headless,
        incognito=False
    ) as sb:
        print("🌐 Opening browser with SeleniumBase...")
        
        # Navigate to AppMagic to establish domain context
        print("🌐 Navigating to AppMagic...")
        sb.open("https://appmagic.rocks")
        time.sleep(2)
        
        # Add cookies
        print("🍪 Adding cookies...")
        for cookie in cookies_data:
            selenium_cookie = {
                'name': cookie['name'],
                'value': cookie['value'],
                'domain': cookie['domain'].lstrip('.') if cookie['domain'].startswith('.') else cookie['domain'],
                'path': cookie.get('path', '/'),
            }
            
            if cookie.get('secure', False):
                selenium_cookie['secure'] = True
            
            if 'expirationDate' in cookie and cookie['expirationDate']:
                selenium_cookie['expiry'] = int(cookie['expirationDate'])
            
            try:
                sb.driver.add_cookie(selenium_cookie)
            except Exception as e:
                print(f"⚠️  Could not add cookie {cookie['name']}: {e}")
        
        print("✅ Cookies added")
        
        # Navigate to referer page
        print("🌐 Navigating to referer page...")
        sb.open("https://appmagic.rocks/top-charts/apps")
        time.sleep(3)
        
        # Process appstore_ids in batches
        updates_batch = []
        
        for i, appstore_id in enumerate(appstore_ids, 1):
            print(f"\n[{i}/{len(appstore_ids)}] Processing appstore_id: {appstore_id}")
            
            # Extract AppMagic data
            try:
                appmagic_data = extract_appmagic_data(appstore_id, sb)
            except Exception as e:
                print(f"   ❌ Exception while extracting data: {e}")
                stats["errors"] += 1
                stats["processed"] += 1
                continue
            
            stats["processed"] += 1
            
            if appmagic_data is None:
                stats["not_found"] += 1
                print(f"   ❌ Not found in AppMagic")
                continue
            
            if appmagic_data.get("appmagic_url") is None:
                stats["not_found"] += 1
                print(f"   ⚠️  Found appmagic_appid={appmagic_data['appmagic_appid']} but no appmagic_url")
                continue
            
            stats["found"] += 1
            print(f"   ✅ Found: appmagic_appid={appmagic_data['appmagic_appid']}, appmagic_url={appmagic_data['appmagic_url']}")
            
            # Add to batch - convert appmagic_appid to string as API expects string
            updates_batch.append({
                "appstore_id": appstore_id,
                "appmagic_appid": str(appmagic_data["appmagic_appid"]),
                "appmagic_url": appmagic_data["appmagic_url"]
            })
            
            # Send bulk update when batch is full
            if len(updates_batch) >= batch_size:
                try:
                    result = bulk_update_apps(api_token, updates_batch)
                    stats["updated"] += result.get("succeeded", 0)
                    stats["update_failed"] += result.get("failed", 0)
                    updates_batch = []
                except Exception as e:
                    print(f"❌ Error in bulk update: {e}")
                    stats["errors"] += 1
                    stats["update_failed"] += len(updates_batch)
                    updates_batch = []
            
            # Small delay to avoid rate limiting
            time.sleep(0.5)
        
        # Send remaining updates
        if updates_batch:
            try:
                result = bulk_update_apps(api_token, updates_batch)
                stats["updated"] += result.get("succeeded", 0)
                stats["update_failed"] += result.get("failed", 0)
            except Exception as e:
                print(f"❌ Error in final bulk update: {e}")
                stats["errors"] += 1
                stats["update_failed"] += len(updates_batch)
    
    return stats


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch AppMagic data for missing appstore_ids")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"Max appstore_ids to fetch (default: {DEFAULT_LIMIT})")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"Batch size for bulk updates (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--exclude-games", action="store_true", default=True, help="Exclude games (default: True)")
    parser.add_argument("--include-games", action="store_false", dest="exclude_games", help="Include games")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in headless mode (default: True)")
    parser.add_argument("--visible", action="store_false", dest="headless", help="Show browser window")
    parser.add_argument("--cookies-file", type=str, default=COOKIES_FILE, help=f"Path to cookies file (default: {COOKIES_FILE})")
    parser.add_argument("--secret", type=str, help="Shared secret override (else INCOMING_SHARED_SECRET constant)")
    parser.add_argument("--token", type=str, help="API token (overrides MAGIC_TRANSPARENCY_TOKEN env var or shared secret)")
    
    args = parser.parse_args()
    
    # Get API token - priority: --token > env var > config file > constant
    api_token = args.token
    if not api_token:
        api_token = os.getenv("MAGIC_TRANSPARENCY_TOKEN")
    if not api_token:
        api_token = load_secret_from_file()
    if not api_token:
        # Use shared secret constant, but allow override via --secret flag
        api_token = args.secret or INCOMING_SHARED_SECRET
    
    if not api_token:
        print("❌ API token required!")
        print("   Set MAGIC_TRANSPARENCY_TOKEN environment variable, use --token, or --secret")
        sys.exit(1)
    
    print("=" * 80)
    print("AppMagic Data Fetcher")
    print("=" * 80)
    print(f"Limit: {args.limit}")
    print(f"Batch size: {args.batch_size}")
    print(f"Exclude games: {args.exclude_games}")
    print(f"Headless: {args.headless}")
    print("=" * 80)
    
    try:
        # Step 1: Get missing appstore_ids
        missing_data = get_missing_appstore_ids(
            api_token=api_token,
            limit=args.limit,
            exclude_games=args.exclude_games
        )
        
        appstore_ids = missing_data["appstore_ids"]
        if not appstore_ids:
            print("✅ No appstore_ids to process")
            return
        
        # Step 2: Process appstore_ids and update server
        stats = process_appstore_ids(
            appstore_ids=appstore_ids,
            api_token=api_token,
            cookies_file=args.cookies_file,
            batch_size=args.batch_size,
            headless=args.headless
        )
        
        # Print summary
        print("\n" + "=" * 80)
        print("Summary")
        print("=" * 80)
        print(f"Total appstore_ids: {stats['total']}")
        print(f"Processed: {stats['processed']}")
        print(f"Found in AppMagic: {stats['found']}")
        print(f"Not found: {stats['not_found']}")
        print(f"Errors: {stats['errors']}")
        print(f"Successfully updated: {stats['updated']}")
        print(f"Update failed: {stats['update_failed']}")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

