#!/usr/bin/env python3
"""
AppMagic Login with Playwright using Exported Cookies

This script loads cookies from the exported JSON file and opens
AppMagic in Playwright with authentication.
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

# Try to import stealth mode
try:
    from playwright_stealth import Stealth
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    print("⚠️  playwright-stealth not installed (optional)")


async def load_appmagic_with_cookies(cookies_file: str = "appmagic_cookies_fresh.json", headless: bool = False):
    """
    Load AppMagic in Playwright with cookies from JSON file.
    
    Args:
        cookies_file: Path to JSON file with cookies
        headless: If False, browser will be visible
    """
    # Load cookies from JSON
    cookies_path = Path(cookies_file)
    if not cookies_path.exists():
        print(f"❌ Cookie file not found: {cookies_file}")
        return
    
    with open(cookies_path, 'r') as f:
        cookies_data = json.load(f)
    
    print(f"✅ Loaded {len(cookies_data)} cookies from {cookies_file}")
    
    # Convert cookies to Playwright format
    playwright_cookies = []
    for cookie in cookies_data:
        pw_cookie = {
            'name': cookie['name'],
            'value': cookie['value'],
            'domain': cookie['domain'].lstrip('.') if cookie['domain'].startswith('.') else cookie['domain'],
            'path': cookie.get('path', '/'),
        }
        
        # Add expiration if present
        if 'expirationDate' in cookie and cookie['expirationDate']:
            pw_cookie['expires'] = int(cookie['expirationDate'])
        
        # Add secure flag
        if cookie.get('secure', False):
            pw_cookie['secure'] = True
        
        # Add httpOnly flag
        if cookie.get('httpOnly', False):
            pw_cookie['httpOnly'] = True
        
        # Add sameSite
        same_site = cookie.get('sameSite', '')
        if same_site == 'no_restriction':
            pw_cookie['sameSite'] = 'None'
        elif same_site == 'Lax':
            pw_cookie['sameSite'] = 'Lax'
        elif same_site == 'Strict':
            pw_cookie['sameSite'] = 'Strict'
        
        playwright_cookies.append(pw_cookie)
    
    print(f"✅ Converted {len(playwright_cookies)} cookies to Playwright format")
    
    # Launch browser
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox'
            ]
        )
        
        # Create context with cookies
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York'
        )
        
        page = await context.new_page()
        
        # Apply stealth mode if available
        if STEALTH_AVAILABLE:
            await Stealth().apply_stealth_async(page)
            print("🕵️  Stealth mode: ENABLED")
        
        # First, navigate to the domain to establish context
        print("🌐 Establishing domain context...")
        await page.goto('https://appmagic.rocks', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(1)
        
        # Add cookies to context (must be done after navigating to the domain)
        await context.add_cookies(playwright_cookies)
        print(f"✅ Added {len(playwright_cookies)} cookies to browser context")
        
        # Verify cookies were added
        context_cookies = await context.cookies()
        print(f"🍪 Browser context has {len(context_cookies)} cookies")
        
        # Now navigate to the target page
        print("🌐 Navigating to AppMagic dashboard...")
        await page.goto('https://appmagic.rocks/top-charts/apps', wait_until='networkidle', timeout=60000)
        
        print("✅ Page loaded!")
        
        # Wait for page to fully render and check authentication
        await asyncio.sleep(3)
        
        # Reload page to trigger session validation
        print("🔄 Reloading page to validate session...")
        await page.reload(wait_until='networkidle', timeout=60000)
        await asyncio.sleep(2)
        
        # Check if we're logged in
        login_button = await page.query_selector('button:has-text("Log In"), a:has-text("Log In")')
        user_menu = await page.query_selector('[class*="user"], [class*="profile"], [class*="account"], [class*="avatar"]')
        
        # Also check page content for login indicators
        page_text = await page.text_content('body')
        has_login_text = 'Log In' in (page_text or '')
        
        if login_button and not user_menu:
            print("⚠️  Still seeing 'Log In' button")
            print("   This might mean:")
            print("   - Cookies are expired")
            print("   - Session needs server-side validation")
            print("   - Additional authentication step required")
        elif user_menu:
            print("✅ Successfully logged in! User menu/profile found.")
        else:
            print("ℹ️  Status unclear - check the browser window")
        
        # Show cookie status
        final_cookies = await context.cookies()
        cookie_names = [c['name'] for c in final_cookies]
        print(f"\n🍪 Active cookies ({len(final_cookies)}):")
        for name in cookie_names[:10]:  # Show first 10
            print(f"   - {name}")
        if len(cookie_names) > 10:
            print(f"   ... and {len(cookie_names) - 10} more")
        
        print("\n" + "="*80)
        print("Browser is open. Press Ctrl+C to close.")
        print("="*80)
        
        # Keep browser open
        try:
            await asyncio.sleep(3600)  # Keep open for 1 hour
        except KeyboardInterrupt:
            print("\n👋 Closing browser...")
        
        await browser.close()


if __name__ == '__main__':
    import sys
    
    headless = '--headless' in sys.argv
    cookies_file = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else "appmagic_cookies_fresh.json"
    
    if headless:
        print("⚠️  Running in headless mode (not recommended for login verification)")
    else:
        print("✅ Browser will be visible")
    
    asyncio.run(load_appmagic_with_cookies(cookies_file=cookies_file, headless=headless))

