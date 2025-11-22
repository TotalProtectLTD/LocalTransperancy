#!/usr/bin/env python3
"""
AppMagic Metrics Fetcher

This script:
1. Fetches apps that need AppMagic metrics from magictransparency.com API
2. Uses SeleniumBase to visit AppMagic and make API requests
3. Fetches metrics from AppMagic's charts/united-applications endpoint
4. Updates the server with the fetched metrics

Designed to be triggered by external scheduler (cron, etc.)

Usage:
    export MAGIC_TRANSPARENCY_TOKEN="your_token_here"
    python3 appmagic_metrics.py [--limit 10] [--headless]
"""

import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, date
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

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


# Configuration
MAGIC_TRANSPARENCY_API = "https://magictransparency.com/api/appmagic"
APPMAGIC_METRICS_ENDPOINT = "https://appmagic.rocks/api/v2/charts/united-applications"
APPMAGIC_AUTH_TOKEN = "r723d4mLh_zAXVFyjY5vBOCwmgsHdZO-"
DEFAULT_LIMIT = 30
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


def get_next_apps_for_metrics(api_token: str, limit: int = DEFAULT_LIMIT) -> List[Dict[str, Any]]:
    """
    Get list of apps that need AppMagic metrics.
    
    Args:
        api_token: Bearer token for magictransparency.com API
        limit: Maximum number of apps to return (default: 10)
    
    Returns:
        List of dicts with id, appmagic_appid, name, last_appmagic_scraped
    """
    url = f"{MAGIC_TRANSPARENCY_API}/next"
    params = {"limit": limit}
    
    headers = {
        "X-Incoming-Secret": api_token,
        "Accept": "application/json"
    }
    
    print(f"📥 Fetching next apps for metrics (limit={limit})...")
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        
        apps = response.json()
        
        if not isinstance(apps, list):
            print(f"❌ Unexpected response format: {type(apps)}")
            return []
        
        print(f"✅ Found {len(apps)} apps to process")
        return apps
    
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching next apps: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        raise


def check_chrome_debug_running(chrome_debug_port: int = 9222) -> bool:
    """Check if Chrome is running with remote debugging enabled."""
    try:
        response = requests.get(f"http://localhost:{chrome_debug_port}/json", timeout=2)
        return response.status_code == 200
    except:
        return False


def start_chrome_debug(chrome_debug_port: int = 9222) -> bool:
    """Start Chrome with remote debugging enabled."""
    import subprocess
    
    chrome_debug_dir = os.path.expanduser("~/Library/Application Support/Google/Chrome-Debug")
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    
    # Create debug profile directory if it doesn't exist
    os.makedirs(chrome_debug_dir, exist_ok=True)
    
    try:
        # Start Chrome in background
        subprocess.Popen(
            [
                chrome_path,
                f"--remote-debugging-port={chrome_debug_port}",
                f"--user-data-dir={chrome_debug_dir}"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # Wait for Chrome to start
        print("⏳ Waiting for Chrome to start...")
        for i in range(10):  # Wait up to 10 seconds
            time.sleep(1)
            if check_chrome_debug_running(chrome_debug_port):
                print(f"✅ Chrome started successfully on port {chrome_debug_port}")
                return True
        
        print("❌ Chrome started but debug port not accessible")
        return False
        
    except Exception as e:
        print(f"❌ Failed to start Chrome: {e}")
        return False


def process_with_existing_chrome(
    apps: List[Dict[str, Any]],
    api_token: str,
    stats: Dict[str, Any],
    chrome_debug_port: int = 9222,
    auto_start_chrome: bool = True
) -> Dict[str, Any]:
    """
    Process apps using existing Chrome instance via remote debugging.
    
    This connects to your actual running Chrome browser, avoiding Cloudflare detection.
    If Chrome is not running and auto_start_chrome is True, it will start Chrome automatically.
    """
    if not SELENIUM_AVAILABLE:
        print("❌ Selenium is required for existing Chrome connection")
        return {"error": "Selenium not available"}
    
    # Check if Chrome is running, start if needed
    if not check_chrome_debug_running(chrome_debug_port):
        if auto_start_chrome:
            print(f"🔍 Chrome debug not running on port {chrome_debug_port}")
            print("🚀 Starting Chrome with remote debugging...")
            if not start_chrome_debug(chrome_debug_port):
                return {"error": "Failed to start Chrome"}
        else:
            print(f"❌ Chrome debug not running on port {chrome_debug_port}")
            print("   Run: ./start_chrome_debug.sh")
            return {"error": "Chrome not running"}
    else:
        print(f"✅ Chrome debug already running on port {chrome_debug_port}")
    
    try:
        # Connect to existing Chrome
        chrome_options = ChromeOptions()
        chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{chrome_debug_port}")
        
        print("🌐 Connecting to existing Chrome instance...")
        driver = webdriver.Chrome(options=chrome_options)
        print("✅ Connected to existing Chrome!")
        
        # Navigate to AppMagic if not already there
        current_url = driver.current_url
        if "appmagic.rocks" not in current_url:
            print("🌐 Navigating to AppMagic...")
            driver.get("https://appmagic.rocks/top-charts/apps")
            time.sleep(3)
        else:
            print(f"✅ Already on AppMagic: {current_url}")
        
        # Process each app
        for i, app in enumerate(apps, 1):
            app_id = app.get("id")
            appmagic_appid = app.get("appmagic_appid")
            app_name = app.get("appname", "Unknown")
            last_scraped = app.get("last_appmagic_scraped")
            
            print(f"\n[{i}/{len(apps)}] Processing: {app_name} (app_id={app_id}, appmagic_appid={appmagic_appid})")
            if last_scraped:
                print(f"   Last scraped: {last_scraped}")
            else:
                print(f"   Never scraped before")
            
            # Skip apps without appmagic_appid
            if not appmagic_appid or appmagic_appid == "None":
                print(f"   ⚠️  Skipping: No appmagic_appid available")
                stats["processed"] += 1
                stats["failed"] += 1
                continue
            
            # Random delay before request (3-7 seconds) to avoid rate limiting
            if i > 1:  # Skip delay for first app
                delay = random.uniform(3, 7)
                print(f"   ⏳ Waiting {delay:.1f} seconds before request...")
                time.sleep(delay)
            
            # Fetch metrics using existing Chrome
            try:
                metrics_data = fetch_appmagic_metrics_selenium(appmagic_appid, driver)
            except Exception as e:
                print(f"   ❌ Exception while fetching metrics: {e}")
                stats["failed"] += 1
                stats["processed"] += 1
                continue
            
            stats["processed"] += 1
            
            if metrics_data is None:
                stats["failed"] += 1
                print(f"   ❌ Failed to fetch metrics")
                continue
            
            stats["success"] += 1
            print(f"   ✅ Fetched metrics successfully")
            
            # Update server with metrics
            try:
                result = update_app_metrics(api_token, app_id, metrics_data)
                if result and result.get("success"):
                    stats["updated"] += 1
                    stats["total_rows_stored"] += result.get("rows_stored", 0)
                else:
                    stats["update_failed"] += 1
            except Exception as e:
                print(f"   ❌ Exception while updating metrics: {e}")
                stats["update_failed"] += 1
            
            # Small delay to avoid rate limiting
            time.sleep(1)
        
        # Don't quit the driver - it's the user's real browser!
        print("\n✅ Processing complete (keeping Chrome open)")
        
    except Exception as e:
        print(f"❌ Error connecting to Chrome: {e}")
        print(f"   Make sure Chrome is running with: ./start_chrome_debug.sh")
        return {"error": str(e)}
    
    return stats


def fetch_appmagic_metrics_selenium(appmagic_id: str, driver) -> Optional[Dict[str, Any]]:
    """
    Fetch metrics from AppMagic using Selenium WebDriver (for existing Chrome).
    """
    url = APPMAGIC_METRICS_ENDPOINT
    date_end = date.today().isoformat()
    date_start = "2015-01-01"
    
    payload = {
        "requests": [
            {
                "aggregation": "day",
                "countries": ["WW"],
                "dateEnd": date_end,
                "dateStart": date_start,
                "store": 5,
                "id": int(appmagic_id)
            }
        ]
    }
    
    try:
        response_data = driver.execute_async_script(f"""
            var callback = arguments[arguments.length - 1];
            var url = '{url}';
            var payload = {json.dumps(payload)};
            
            fetch(url, {{
                method: 'POST',
                headers: {{
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Authorization': 'Bearer {APPMAGIC_AUTH_TOKEN}',
                    'Content-Type': 'application/json',
                    'Origin': 'https://appmagic.rocks',
                    'Referer': 'https://appmagic.rocks/top-charts/apps',
                    'Sec-Fetch-Dest': 'empty',
                    'Sec-Fetch-Mode': 'cors',
                    'Sec-Fetch-Site': 'same-origin'
                }},
                body: JSON.stringify(payload)
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
            print(f"⚠️  Unexpected response format")
            return None
        
        if 'error' in response_data:
            print(f"⚠️  Error: {response_data['error']}")
            return None
        
        if response_data.get('status') != 200:
            print(f"⚠️  Non-200 status: {response_data.get('status')}")
            return None
        
        try:
            response_json = json.loads(response_data['body'])
        except json.JSONDecodeError as e:
            print(f"⚠️  Failed to parse JSON: {e}")
            return None
        
        return response_json
    
    except Exception as e:
        print(f"❌ Exception: {e}")
        return None


def fetch_appmagic_metrics(appmagic_id: str, sb: SB) -> Optional[Dict[str, Any]]:
    """
    Fetch metrics from AppMagic for given appmagic_id.
    
    Args:
        appmagic_id: AppMagic's ID for the app
        sb: SeleniumBase instance with browser context
    
    Returns:
        Dict with metrics data, or None if request failed
    """
    # Calculate date range
    date_end = date.today().isoformat()  # Today
    date_start = "2015-01-01"  # Start from 2015
    
    payload = {
        "requests": [
            {
                "aggregation": "day",
                "countries": ["WW"],
                "dateEnd": date_end,
                "dateStart": date_start,
                "store": 5,
                "id": int(appmagic_id)  # Convert to integer
            }
        ]
    }
    
    try:
        # Make API request using JavaScript fetch in browser context
        response_data = sb.execute_async_script(f"""
            var callback = arguments[arguments.length - 1];
            var url = '{APPMAGIC_METRICS_ENDPOINT}';
            var payload = {json.dumps(payload)};
            
            fetch(url, {{
                method: 'POST',
                headers: {{
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Authorization': 'Bearer {APPMAGIC_AUTH_TOKEN}',
                    'Content-Type': 'application/json',
                    'Origin': 'https://appmagic.rocks',
                    'Referer': 'https://appmagic.rocks/top-charts/apps',
                    'Sec-Fetch-Dest': 'empty',
                    'Sec-Fetch-Mode': 'cors',
                    'Sec-Fetch-Site': 'same-origin'
                }},
                body: JSON.stringify(payload)
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
            print(f"⚠️  Unexpected response format for appmagic_id {appmagic_id}")
            return None
        
        if 'error' in response_data:
            print(f"⚠️  Error fetching metrics for {appmagic_id}: {response_data['error']}")
            return None
        
        if response_data.get('status') != 200:
            print(f"⚠️  Non-200 status for {appmagic_id}: {response_data.get('status')}")
            if response_data.get('body'):
                print(f"   Response body: {response_data['body'][:200]}")
            return None
        
        # Parse JSON response
        try:
            response_json = json.loads(response_data['body'])
        except json.JSONDecodeError as e:
            print(f"⚠️  Failed to parse JSON for {appmagic_id}: {e}")
            return None
        
        return response_json
    
    except Exception as e:
        print(f"❌ Exception while fetching metrics for {appmagic_id}: {e}")
        return None


def update_app_metrics(api_token: str, app_id: int, metrics_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update app metrics on the server.
    
    Args:
        api_token: Bearer token for magictransparency.com API
        app_id: Internal app ID
        metrics_data: Metrics data from AppMagic (should contain "data" array)
    
    Returns:
        Dict with success status and details, or None if failed
    """
    url = f"https://magictransparency.com/api/appmagic/apps/{app_id}/metrics"
    
    headers = {
        "X-Incoming-Secret": api_token,
        "Content-Type": "application/json"
    }
    
    # Extract the "data" array from metrics_data
    # AppMagic response structure: {"data": [...]}
    if isinstance(metrics_data, dict) and "data" in metrics_data:
        data_array = metrics_data["data"]
    else:
        data_array = metrics_data if isinstance(metrics_data, list) else [metrics_data]
    
    # Clean up empty metrics that don't have first_date
    # Server requires first_date even if points is empty
    cleaned_data = []
    for item in data_array:
        cleaned_item = {}
        for key, value in item.items():
            if isinstance(value, dict):
                # If points is empty but first_date is missing, skip this metric
                if value.get('points') == [] and 'first_date' not in value:
                    continue  # Skip this metric entirely
                cleaned_item[key] = value
            else:
                cleaned_item[key] = value
        if cleaned_item:  # Only add if not empty
            cleaned_data.append(cleaned_item)
    
    payload = {"data": cleaned_data}
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get("success"):
            rows_stored = result.get("rows_stored", 0)
            print(f"   ✅ Metrics updated: {rows_stored} rows stored")
            return result
        else:
            print(f"   ⚠️  Unexpected response: {result}")
            return result
    
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Error updating metrics: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json()
                print(f"      Server response: {error_detail}")
            except:
                print(f"      Server response: {e.response.text}")
        return None


def process_apps(
    apps: List[Dict[str, Any]],
    api_token: str,
    cookies_file: str = COOKIES_FILE,
    headless: bool = True,
    use_browser_profile: bool = False,
    browser_profile: Optional[str] = None,
    use_existing_chrome: bool = False,
    chrome_debug_port: int = 9222,
    auto_start_chrome: bool = True
) -> Dict[str, Any]:
    """
    Process apps and fetch their metrics from AppMagic.
    
    Args:
        apps: List of app dicts with id, appmagic_id, name, last_appmagic_scraped
        api_token: Bearer token for magictransparency.com API
        cookies_file: Path to AppMagic cookies JSON file (ignored if use_browser_profile=True)
        headless: Run browser in headless mode
        use_browser_profile: Use existing Chrome profile with all cookies (default: False)
        browser_profile: Path to Chrome profile directory (optional)
        use_existing_chrome: Connect to existing Chrome with remote debugging (best option)
        chrome_debug_port: Port for Chrome remote debugging (default: 9222)
    
    Returns:
        Dict with processing statistics
    """
    # Load cookies only if not using browser profile and not using existing Chrome
    cookies_data = None
    if not use_browser_profile and not use_existing_chrome:
        cookies_path = Path(cookies_file)
        if not cookies_path.exists():
            print(f"❌ Cookie file not found: {cookies_file}")
            return {"error": f"Cookie file not found: {cookies_file}"}
        
        with open(cookies_path, 'r') as f:
            cookies_data = json.load(f)
        
        print(f"✅ Loaded {len(cookies_data)} cookies from {cookies_file}")
    elif use_existing_chrome:
        print(f"✅ Connecting to existing Chrome instance (port {chrome_debug_port})")
    else:
        print(f"✅ Using browser profile with all existing cookies")
    
    stats = {
        "total": len(apps),
        "processed": 0,
        "success": 0,
        "failed": 0,
        "updated": 0,
        "update_failed": 0,
        "total_rows_stored": 0
    }
    
    # Use existing Chrome instance if requested
    if use_existing_chrome:
        return process_with_existing_chrome(apps, api_token, stats, chrome_debug_port, auto_start_chrome)
    
    # Prepare browser options
    sb_kwargs = {
        "uc": True,  # Undetected Chrome mode (stealth)
        "headless": headless,
        "incognito": False
    }
    
    # Add browser profile if specified
    if use_browser_profile and browser_profile:
        sb_kwargs["user_data_dir"] = browser_profile
        print(f"🌐 Using Chrome profile: {browser_profile}")
    
    # Open browser with SeleniumBase
    with SB(**sb_kwargs) as sb:
        print("🌐 Opening browser with SeleniumBase...")
        
        # Navigate to AppMagic to establish domain context
        print("🌐 Navigating to AppMagic...")
        sb.open("https://appmagic.rocks")
        time.sleep(2)
        
        # Add cookies only if not using browser profile
        if not use_browser_profile and cookies_data:
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
        else:
            print("✅ Using cookies from browser profile")
        
        # Navigate to referer page to bypass Cloudflare
        print("🌐 Navigating to referer page to bypass Cloudflare...")
        sb.open("https://appmagic.rocks/top-charts/apps")
        time.sleep(3)
        
        print("✅ Page loaded, ready to fetch metrics")
        
        # Process each app
        for i, app in enumerate(apps, 1):
            app_id = app.get("id")
            appmagic_appid = app.get("appmagic_appid")  # Changed from appmagic_id
            app_name = app.get("appname", "Unknown")  # API returns "appname" not "name"
            last_scraped = app.get("last_appmagic_scraped")
            
            print(f"\n[{i}/{len(apps)}] Processing: {app_name} (app_id={app_id}, appmagic_appid={appmagic_appid})")
            if last_scraped:
                print(f"   Last scraped: {last_scraped}")
            else:
                print(f"   Never scraped before")
            
            # Skip apps without appmagic_appid
            if not appmagic_appid or appmagic_appid == "None":
                print(f"   ⚠️  Skipping: No appmagic_appid available")
                stats["processed"] += 1
                stats["failed"] += 1
                continue
            
            # Random delay before request (3-7 seconds) to avoid rate limiting
            if i > 1:  # Skip delay for first app
                delay = random.uniform(3, 7)
                print(f"   ⏳ Waiting {delay:.1f} seconds before request...")
                time.sleep(delay)
            
            # Fetch metrics
            try:
                metrics_data = fetch_appmagic_metrics(appmagic_appid, sb)
            except Exception as e:
                print(f"   ❌ Exception while fetching metrics: {e}")
                stats["failed"] += 1
                stats["processed"] += 1
                continue
            
            stats["processed"] += 1
            
            if metrics_data is None:
                stats["failed"] += 1
                print(f"   ❌ Failed to fetch metrics")
                continue
            
            stats["success"] += 1
            print(f"   ✅ Fetched metrics successfully")
            
            # Update server with metrics
            try:
                result = update_app_metrics(api_token, app_id, metrics_data)
                if result and result.get("success"):
                    stats["updated"] += 1
                    stats["total_rows_stored"] += result.get("rows_stored", 0)
                else:
                    stats["update_failed"] += 1
            except Exception as e:
                print(f"   ❌ Exception while updating metrics: {e}")
                stats["update_failed"] += 1
            
            # Small delay to avoid rate limiting
            time.sleep(1)
    
    return stats


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch AppMagic metrics for apps")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"Max apps to fetch (default: {DEFAULT_LIMIT})")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in headless mode (default: True)")
    parser.add_argument("--visible", action="store_false", dest="headless", help="Show browser window")
    parser.add_argument("--cookies-file", type=str, default=COOKIES_FILE, help=f"Path to cookies file (default: {COOKIES_FILE})")
    parser.add_argument("--use-browser-profile", action="store_true", help="Use existing Chrome profile with all cookies (ignores --cookies-file)")
    parser.add_argument("--browser-profile", type=str, help="Path to Chrome profile directory (auto-detect if not specified)")
    parser.add_argument("--use-existing-chrome", action="store_true", help="Connect to existing Chrome with remote debugging (BEST - no Cloudflare checks!)")
    parser.add_argument("--chrome-debug-port", type=int, default=9222, help="Chrome remote debugging port (default: 9222)")
    parser.add_argument("--no-auto-start-chrome", action="store_true", help="Don't automatically start Chrome if not running")
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
    print("AppMagic Metrics Fetcher")
    print("=" * 80)
    print(f"Limit: {args.limit}")
    print(f"Headless: {args.headless}")
    print("=" * 80)
    
    try:
        # Step 1: Get next apps for metrics
        apps = get_next_apps_for_metrics(
            api_token=api_token,
            limit=args.limit
        )
        
        if not apps or len(apps) == 0:
            print("✅ No apps to process")
            return
        
        # Step 2: Process apps and fetch metrics
        stats = process_apps(
            apps=apps,
            api_token=api_token,
            cookies_file=args.cookies_file,
            headless=args.headless,
            use_browser_profile=args.use_browser_profile,
            browser_profile=args.browser_profile,
            use_existing_chrome=args.use_existing_chrome,
            chrome_debug_port=args.chrome_debug_port,
            auto_start_chrome=not args.no_auto_start_chrome
        )
        
        # Print summary
        print("\n" + "=" * 80)
        print("Summary")
        print("=" * 80)
        print(f"Total apps: {stats['total']}")
        print(f"Processed: {stats['processed']}")
        print(f"Successfully fetched: {stats['success']}")
        print(f"Failed to fetch: {stats['failed']}")
        print(f"Successfully updated: {stats['updated']}")
        print(f"Update failed: {stats['update_failed']}")
        print(f"Total rows stored: {stats['total_rows_stored']}")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

