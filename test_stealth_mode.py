#!/usr/bin/env python3
"""
Stealth Mode Test Script
========================

This script tests the effectiveness of playwright-stealth by checking
common bot detection indicators.

Usage:
    python test_stealth_mode.py --with-stealth    # Test with stealth enabled
    python test_stealth_mode.py --without-stealth # Test without stealth
    python test_stealth_mode.py                   # Test both modes (default)
"""

import asyncio
import argparse
from playwright.async_api import async_playwright

try:
    from playwright_stealth import Stealth
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    print("⚠️  playwright-stealth not installed")
    print("   Install: pip install playwright-stealth\n")


# JavaScript detection tests
DETECTION_TESTS = """
(() => {
    const results = {
        'navigator.webdriver': window.navigator.webdriver,
        'navigator.plugins.length': window.navigator.plugins.length,
        'navigator.languages': window.navigator.languages,
        'window.chrome': typeof window.chrome !== 'undefined',
        'navigator.permissions': typeof navigator.permissions !== 'undefined',
        'Notification.permission': Notification.permission,
        'navigator.vendor': navigator.vendor,
        'navigator.platform': navigator.platform
    };
    
    return results;
})();
"""


async def test_detection(use_stealth=False):
    """
    Test bot detection with or without stealth mode.
    
    Args:
        use_stealth: If True, apply stealth_async to page
    """
    mode = "WITH STEALTH" if use_stealth else "WITHOUT STEALTH"
    print("\n" + "="*80)
    print(f"TESTING {mode}")
    print("="*80)
    
    if use_stealth and not STEALTH_AVAILABLE:
        print("❌ Cannot test with stealth - playwright-stealth not installed")
        return
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        # Apply stealth if requested
        if use_stealth and STEALTH_AVAILABLE:
            await Stealth().apply_stealth_async(page)
            print("🕵️  Stealth mode applied\n")
        
        # Navigate to a blank page
        await page.goto("about:blank")
        
        # Run detection tests
        results = await page.evaluate(DETECTION_TESTS)
        
        # Print results
        print("Detection Test Results:")
        print("-" * 80)
        
        for key, value in results.items():
            # Determine if this is a detection indicator
            is_detected = False
            indicator = "✅"
            
            if key == 'navigator.webdriver':
                if value is True:
                    is_detected = True
                    indicator = "❌ DETECTED"
                else:
                    indicator = "✅ HIDDEN"
            elif key == 'navigator.plugins.length':
                if value == 0:
                    indicator = "⚠️  SUSPICIOUS"
                else:
                    indicator = "✅ OK"
            elif key == 'window.chrome':
                if value is False:
                    indicator = "⚠️  MISSING"
                else:
                    indicator = "✅ PRESENT"
            elif key == 'navigator.permissions':
                if value is False:
                    indicator = "⚠️  MISSING"
                else:
                    indicator = "✅ PRESENT"
            
            print(f"  {key:30} = {str(value):20} {indicator}")
        
        # Test on bot detection sites
        print("\n" + "-" * 80)
        print("Testing on bot detection sites:")
        print("-" * 80)
        
        test_sites = [
            ("Bot Sannysoft", "https://bot.sannysoft.com/"),
            ("Are You Headless", "https://arh.antoinevastel.com/bots/areyouheadless")
        ]
        
        for name, url in test_sites:
            try:
                print(f"\n  Testing {name}...")
                print(f"  URL: {url}")
                await page.goto(url, timeout=10000)
                await page.wait_for_timeout(2000)
                
                # Check if page loaded successfully
                title = await page.title()
                print(f"  ✅ Page loaded: {title[:50]}")
                print(f"  💡 Open manually to see detection results")
                
            except Exception as e:
                print(f"  ⚠️  Error loading {name}: {str(e)[:50]}")
        
        await browser.close()
    
    print("\n" + "="*80 + "\n")


async def compare_modes():
    """Compare stealth mode enabled vs disabled."""
    print("\n" + "="*80)
    print("PLAYWRIGHT-STEALTH COMPARISON TEST")
    print("="*80)
    
    if not STEALTH_AVAILABLE:
        print("\n⚠️  playwright-stealth is not installed!")
        print("   Install it to see the full comparison:")
        print("   pip install playwright-stealth\n")
        print("   Testing without stealth only...\n")
        await test_detection(use_stealth=False)
    else:
        print("\n✅ playwright-stealth is installed")
        print("   Running comparison tests...\n")
        
        # Test without stealth
        await test_detection(use_stealth=False)
        
        # Test with stealth
        await test_detection(use_stealth=True)
        
        # Summary
        print("="*80)
        print("SUMMARY")
        print("="*80)
        print("""
Key Differences:

WITHOUT STEALTH:
  ❌ navigator.webdriver = true (CLEAR BOT INDICATOR)
  ⚠️  navigator.plugins.length = 0 (suspicious)
  ⚠️  window.chrome missing (headless indicator)
  ⚠️  Easy to detect as automation

WITH STEALTH:
  ✅ navigator.webdriver = undefined (appears normal)
  ✅ navigator.plugins.length > 0 (has plugins)
  ✅ window.chrome present (appears real)
  ✅ Much harder to detect as automation

RECOMMENDATION:
  Use stealth mode for production scraping to avoid detection.
        """)


async def main():
    parser = argparse.ArgumentParser(
        description='Test playwright-stealth bot detection evasion',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--with-stealth', action='store_true',
                        help='Test only with stealth mode enabled')
    parser.add_argument('--without-stealth', action='store_true',
                        help='Test only without stealth mode')
    
    args = parser.parse_args()
    
    if args.with_stealth and args.without_stealth:
        print("❌ Cannot use both --with-stealth and --without-stealth")
        return
    
    if args.with_stealth:
        await test_detection(use_stealth=True)
    elif args.without_stealth:
        await test_detection(use_stealth=False)
    else:
        # Default: compare both modes
        await compare_modes()


if __name__ == "__main__":
    asyncio.run(main())

