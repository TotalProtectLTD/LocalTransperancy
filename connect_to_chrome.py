#!/usr/bin/env python3
"""
Connect Playwright to Existing Chrome Browser

This script connects Playwright to your running Chrome browser,
allowing you to control it programmatically while keeping your
existing session, cookies, and extensions.
"""

import asyncio
from playwright.async_api import async_playwright


async def connect_to_chrome(headless: bool = False):
    """
    Connect to existing Chrome browser or launch Chrome with remote debugging.
    
    Usage:
    1. Close all Chrome windows
    2. Launch Chrome with remote debugging:
       /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome-debug"
    3. Run this script
    """
    print("=" * 80)
    print("Connecting to Chrome via Chrome DevTools Protocol (CDP)")
    print("=" * 80)
    
    async with async_playwright() as p:
        try:
            # Connect to existing Chrome with remote debugging enabled
            # Chrome must be launched with: --remote-debugging-port=9222
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            print("✅ Connected to existing Chrome browser!")
            
            # Get existing contexts
            contexts = browser.contexts
            if contexts:
                print(f"✅ Found {len(contexts)} existing browser context(s)")
                context = contexts[0]
            else:
                print("⚠️  No existing contexts, creating new one...")
                context = await browser.new_context()
            
            # Get pages
            pages = context.pages
            if pages:
                print(f"✅ Found {len(pages)} existing page(s)")
                page = pages[0]
            else:
                print("⚠️  No existing pages, creating new one...")
                page = await context.new_page()
            
            # Check current URL
            current_url = page.url
            print(f"📍 Current page: {current_url}")
            
            # Check cookies
            cookies = await context.cookies()
            print(f"🍪 Found {len(cookies)} cookies in browser context")
            if cookies:
                cookie_names = [c['name'] for c in cookies[:10]]
                print(f"   Sample cookies: {', '.join(cookie_names)}")
            
            # Navigate to AppMagic
            print("\n🌐 Navigating to AppMagic...")
            await page.goto('https://appmagic.rocks/top-charts/apps', wait_until='networkidle', timeout=60000)
            
            print("✅ Page loaded!")
            
            # Check login status
            await asyncio.sleep(2)
            login_button = await page.query_selector('button:has-text("Log In"), a:has-text("Log In")')
            user_menu = await page.query_selector('[class*="user"], [class*="profile"], [class*="account"]')
            
            if user_menu:
                print("✅ You are logged in! User menu found.")
            elif login_button:
                print("⚠️  Not logged in - 'Log In' button visible")
            else:
                print("ℹ️  Status unclear - check the browser")
            
            print("\n" + "=" * 80)
            print("Browser is connected. You can control it programmatically.")
            print("Press Ctrl+C to disconnect (Chrome will stay open).")
            print("=" * 80)
            
            # Keep connection alive
            try:
                await asyncio.sleep(3600)  # 1 hour
            except KeyboardInterrupt:
                print("\n👋 Disconnecting from Chrome...")
            
            await browser.close()
            
        except Exception as e:
            print(f"❌ Error connecting to Chrome: {e}")
            print("\n💡 Make sure Chrome is running with remote debugging:")
            print("   1. Close all Chrome windows")
            print("   2. Launch Chrome with:")
            print('      /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\')
            print('        --remote-debugging-port=9222 \\')
            print('        --user-data-dir="/tmp/chrome-debug"')
            print("   3. Then run this script again")


async def launch_chrome_with_debugging():
    """
    Launch Chrome with remote debugging enabled.
    """
    import subprocess
    import os
    
    chrome_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "google-chrome",
        "chromium",
    ]
    
    chrome_path = None
    for path in chrome_paths:
        if os.path.exists(path) or subprocess.run(['which', path.split('/')[-1]], 
                                                  capture_output=True).returncode == 0:
            chrome_path = path
            break
    
    if not chrome_path:
        print("❌ Chrome not found. Please install Chrome or specify path manually.")
        return
    
    user_data_dir = "/tmp/chrome-debug-playwright"
    os.makedirs(user_data_dir, exist_ok=True)
    
    print(f"🚀 Launching Chrome with remote debugging...")
    print(f"   Chrome path: {chrome_path}")
    print(f"   User data dir: {user_data_dir}")
    print(f"   Debugging port: 9222")
    
    subprocess.Popen([
        chrome_path,
        "--remote-debugging-port=9222",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ])
    
    print("✅ Chrome launched! Wait a few seconds, then run:")
    print("   python3 connect_to_chrome.py --connect")


if __name__ == '__main__':
    import sys
    
    if '--launch' in sys.argv:
        asyncio.run(launch_chrome_with_debugging())
    else:
        asyncio.run(connect_to_chrome())




