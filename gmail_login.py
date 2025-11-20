#!/usr/bin/env python3
"""
Gmail Login Script using Playwright with Stealth Mode

This script uses your existing Playwright setup with stealth mode
to log into Gmail, bypassing Google's bot detection.
"""

import asyncio
import sys
from playwright.async_api import async_playwright

# Try to import stealth mode
try:
    from playwright_stealth import Stealth
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    print("⚠️  playwright-stealth not installed. Install with: pip install playwright-stealth")

# Import your browser setup
try:
    from google_ads_browser import _setup_browser_context
    from google_ads_config import BROWSER_HEADLESS, ENABLE_STEALTH_MODE
except ImportError:
    print("⚠️  Could not import browser setup. Using basic configuration.")
    BROWSER_HEADLESS = False  # Set to False to see the browser
    ENABLE_STEALTH_MODE = True


async def login_to_gmail(email: str = None, headless: bool = False):
    """
    Login to Gmail using Playwright with stealth mode.
    
    Args:
        email: Optional email address to pre-fill
        headless: If False, browser will be visible (recommended for login)
    """
    print("🚀 Starting Gmail login with Playwright...")
    
    async with async_playwright() as p:
        # Setup browser - FORCE visible mode for login (headless=False)
        # Even if config has headless=True, we override it for login
        print("Using browser setup with stealth mode...")
        browser = await p.chromium.launch(
            headless=headless,  # Use the parameter, not config
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox'
            ]
        )
        
        # Get user agent from your config if available
        try:
            from google_ads_traffic import _get_user_agent
            user_agent = _get_user_agent()
        except:
            user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        
        print(f"🎭 User Agent: {user_agent[:80]}...")
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent=user_agent,
            locale='en-US',
            timezone_id='America/New_York'
        )
        
        page = await context.new_page()
        
        # Apply stealth mode if available
        if STEALTH_AVAILABLE and ENABLE_STEALTH_MODE:
            await Stealth().apply_stealth_async(page)
            print("🕵️  Stealth mode: ENABLED")
        elif ENABLE_STEALTH_MODE and not STEALTH_AVAILABLE:
            print("⚠️  Stealth mode: DISABLED (playwright-stealth not installed)")
        
        # Navigate to Gmail
        print("📧 Navigating to Gmail...")
        await page.goto('https://accounts.google.com/signin/v2/identifier?continue=https%3A%2F%2Fmail.google.com%2Fmail&service=mail&sacu=1&rip=1&flowName=GlifWebSignIn&flowEntry=ServiceLogin', 
                       wait_until='networkidle', timeout=60000)
        
        print("✅ Gmail login page loaded")
        print("👤 Please complete the login manually in the browser window...")
        print("   (The browser will stay open for 5 minutes after you log in)")
        
        # Wait for user to complete login
        # Check if we're logged in by looking for Gmail interface
        try:
            # Wait for either successful login (Gmail interface) or timeout
            await page.wait_for_selector('input[name="identifier"]', timeout=300000, state='hidden')
            print("✅ Login appears successful! Waiting for Gmail to load...")
            await page.wait_for_selector('div[role="main"]', timeout=30000)
            print("✅ Successfully logged into Gmail!")
        except:
            print("⏱️  Waiting for manual login (5 minute timeout)...")
            await asyncio.sleep(300)  # Wait 5 minutes
        
        # Keep browser open for a bit so user can see it worked
        print("\n✅ Browser will close in 10 seconds...")
        await asyncio.sleep(10)
        
        await browser.close()
        print("✅ Done!")


if __name__ == '__main__':
    # Default to visible browser (headless=False) for login
    # Only use headless if explicitly requested
    headless = '--headless' in sys.argv
    if headless:
        print("⚠️  Running in headless mode (not recommended for login)")
    else:
        print("✅ Browser will be visible (recommended for login)")
    
    email = None
    if '--email' in sys.argv:
        idx = sys.argv.index('--email')
        if idx + 1 < len(sys.argv):
            email = sys.argv[idx + 1]
    
    asyncio.run(login_to_gmail(email=email, headless=headless))

