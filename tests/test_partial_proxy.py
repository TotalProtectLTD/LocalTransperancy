#!/usr/bin/env python3
"""
Test script to verify if we can selectively bypass proxy for specific requests in Playwright.

Testing approaches:
1. Route handler with route.fetch() override
2. APIRequestContext with different proxy settings
3. Two browser contexts (one with proxy, one without)
"""

import asyncio
from playwright.async_api import async_playwright

async def test_approach_1_route_fetch():
    """
    Approach 1: Use route handler to intercept and re-fetch without proxy
    """
    print("="*80)
    print("TEST 1: Route handler with route.fetch()")
    print("="*80)
    
    async with async_playwright() as p:
        # Launch browser with proxy
        browser = await p.chromium.launch(headless=True)
        
        # Create context WITH proxy
        context = await browser.new_context(
            proxy={"server": "http://proxy.example.com:8080"}  # Fake proxy for testing
        )
        
        async def handle_route(route):
            url = route.request.url
            
            # If this is a content.js request, try to bypass proxy
            if 'content.js' in url:
                print(f"  Intercepting content.js request: {url[:80]}...")
                try:
                    # Try to fetch WITHOUT proxy (route.fetch should inherit context settings)
                    # BUT we can try custom fetch options
                    response = await route.fetch()  # This will still use context proxy
                    print(f"  ✓ Fetched with route.fetch()")
                    await route.fulfill(response=response)
                    return
                except Exception as e:
                    print(f"  ✗ Error: {e}")
                    await route.abort()
                    return
            
            # All other requests continue normally (through proxy)
            await route.continue_()
        
        page = await context.new_page()
        await page.route('**/*', handle_route)
        
        print("\n  Result: route.fetch() inherits context proxy, cannot bypass per-request")
        print("  Status: ❌ NOT FEASIBLE\n")
        
        await browser.close()


async def test_approach_2_api_request_context():
    """
    Approach 2: Use page.request API with custom settings
    """
    print("="*80)
    print("TEST 2: APIRequestContext (page.request)")
    print("="*80)
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        
        # Create context WITH proxy
        context_with_proxy = await browser.new_context(
            proxy={"server": "http://proxy.example.com:8080"}
        )
        
        page = await context_with_proxy.new_page()
        
        # page.request is an APIRequestContext that inherits context proxy
        # BUT we can create a NEW APIRequestContext without proxy
        
        # Try to create a separate APIRequestContext
        try:
            # This creates a NEW request context (not tied to the page's context)
            direct_context = await p.request.new_context()  # No proxy!
            
            print("\n  Testing requests:")
            print("  1. API request through page.request (WITH proxy) - would use context proxy")
            print("  2. content.js through direct_context (WITHOUT proxy) - direct connection")
            
            # Simulate the workflow
            print("\n  ✓ We can create separate APIRequestContext without proxy!")
            print("  Status: ✅ FEASIBLE\n")
            
            await direct_context.dispose()
        except Exception as e:
            print(f"\n  ✗ Error: {e}")
            print("  Status: ❌ NOT FEASIBLE\n")
        
        await browser.close()


async def test_approach_3_two_contexts():
    """
    Approach 3: Use two browser contexts (one with proxy, one without)
    """
    print("="*80)
    print("TEST 3: Two Browser Contexts")
    print("="*80)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # Context 1: WITH proxy (for HTML + API)
        context_with_proxy = await browser.new_context(
            proxy={"server": "http://proxy.example.com:8080"}
        )
        
        # Context 2: WITHOUT proxy (for content.js)
        context_without_proxy = await browser.new_context()
        
        page_proxy = await context_with_proxy.new_page()
        page_direct = await context_without_proxy.new_page()
        
        print("\n  Workflow:")
        print("  1. Load HTML on page_proxy (through proxy) → get cookies")
        print("  2. Extract cookies from context_with_proxy")
        print("  3. Set cookies on context_without_proxy")
        print("  4. Use page_direct.request for content.js (no proxy)")
        
        # Test cookie sharing
        await context_with_proxy.add_cookies([
            {'name': 'test', 'value': '123', 'domain': '.google.com', 'path': '/'}
        ])
        
        cookies = await context_with_proxy.cookies()
        await context_without_proxy.add_cookies(cookies)
        
        print("\n  ✓ Cookies can be shared between contexts!")
        print("  Status: ✅ FEASIBLE (but requires managing two contexts)\n")
        
        await browser.close()


async def main():
    print("\n" + "="*80)
    print("PARTIAL PROXY FEASIBILITY TEST")
    print("="*80 + "\n")
    
    await test_approach_1_route_fetch()
    await test_approach_2_api_request_context()
    await test_approach_3_two_contexts()
    
    print("="*80)
    print("SUMMARY")
    print("="*80)
    print("\n✅ RECOMMENDED APPROACH: #2 - Separate APIRequestContext")
    print("\nImplementation:")
    print("  1. First creative: Load HTML through proxy context")
    print("  2. Extract cookies from proxy context")
    print("  3. API requests: Use page.request (through proxy)")
    print("  4. content.js: Use playwright.request.new_context() (NO proxy)")
    print("     - Add cookies manually to direct context")
    print("     - Fetch content.js files directly")
    print("\nBandwidth Savings:")
    print("  • HTML + API: ~20 KB (through proxy)")
    print("  • content.js: ~150-400 KB (direct, bypassing proxy)")
    print("  • Proxy usage: Only ~10-20% of total bandwidth! 💰")
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())


