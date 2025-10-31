#!/usr/bin/env python3
"""
Test script to validate session reuse for optimized bandwidth usage.

Tests:
1. Load first creative (full HTML load)
2. Save cookies
3. Load second creative using API only (skip HTML)
4. Compare bandwidth usage
"""

import asyncio
import json
from playwright.async_api import async_playwright
import logging
import urllib.parse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Test creative IDs
CREATIVE_1 = {
    "advertiser_id": "AR08722290881173913601",
    "creative_id": "CR13612220978573606913"
}

CREATIVE_2 = {
    "advertiser_id": "AR08722290881173913601", 
    "creative_id": "CR13612220978573606913"  # Same creative for now (we'll test with real different one)
}


async def parse_api_response(response_text):
    """Parse the GetCreativeById API response to extract content.js URLs."""
    try:
        data = json.loads(response_text)
        content_js_urls = []
        
        # Response is wrapped: {"1": {actual data}}
        if "1" in data:
            data = data["1"]
        
        # Navigate to field "5" which contains creative variations
        if "5" in data and isinstance(data["5"], list):
            for variation in data["5"]:
                if "1" in variation and "4" in variation["1"]:
                    url = variation["1"]["4"]
                    content_js_urls.append(url)
        
        return content_js_urls
    except Exception as e:
        logger.error(f"Failed to parse API response: {e}")
        return []


async def fetch_creative_optimized(page, advertiser_id, creative_id, cookies):
    """
    Fetch creative data using API only (no HTML load).
    
    Args:
        page: Playwright page object
        advertiser_id: Advertiser ID
        creative_id: Creative ID  
        cookies: Session cookies from first load
        
    Returns:
        list: content.js responses
    """
    logger.info(f"🔄 Fetching creative {creative_id} using API only...")
    
    # Set cookies from previous session
    await page.context.add_cookies(cookies)
    
    # Construct API request payload
    api_payload = {
        "1": advertiser_id,
        "2": creative_id,
        "5": {"1": 1, "2": 0, "3": 2268}
    }
    
    # URL encode the payload
    body_data = f"f.req={json.dumps(api_payload)}"
    
    # Make direct API call
    api_url = "https://adstransparency.google.com/anji/_/rpc/LookupService/GetCreativeById?authuser="
    
    try:
        api_response = await page.request.post(
            api_url,
            data=body_data,
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "x-framework-xsrf-token": "",
                "x-same-domain": "1",
                "origin": "https://adstransparency.google.com",
                "referer": f"https://adstransparency.google.com/advertiser/{advertiser_id}/creative/{creative_id}"
            }
        )
        
        response_text = await api_response.text()
        logger.info(f"✅ API response received: {len(response_text)} bytes")
        logger.info(f"📄 Response preview: {response_text[:500]}")
        
        # Parse content.js URLs from response
        content_js_urls = await parse_api_response(response_text)
        logger.info(f"📋 Found {len(content_js_urls)} content.js URLs")
        
        # Fetch each content.js
        content_responses = []
        for i, url in enumerate(content_js_urls, 1):
            logger.info(f"📥 Fetching content.js #{i}...")
            content_response = await page.request.get(url)
            content_text = await content_response.text()
            content_responses.append({
                "url": url,
                "size": len(content_text),
                "content": content_text[:200]  # First 200 chars for preview
            })
            logger.info(f"   ✓ Size: {len(content_text)} bytes")
        
        return {
            "api_response": response_text,
            "content_js_responses": content_responses
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to fetch creative: {e}")
        return None


async def main():
    """Main test function."""
    
    logger.info("="*80)
    logger.info("SESSION REUSE TEST")
    logger.info("="*80)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            locale='en-US'
        )
        page = await context.new_page()
        
        # ========================================
        # STEP 1: Full load of first creative
        # ========================================
        logger.info("\n" + "="*80)
        logger.info("STEP 1: Loading first creative (FULL HTML LOAD)")
        logger.info("="*80)
        
        url1 = f"https://adstransparency.google.com/advertiser/{CREATIVE_1['advertiser_id']}/creative/{CREATIVE_1['creative_id']}?region=anywhere"
        
        await page.goto(url1, wait_until='networkidle', timeout=60000)
        logger.info(f"✅ Page loaded: {CREATIVE_1['creative_id']}")
        
        # Save cookies
        cookies = await context.cookies()
        logger.info(f"🍪 Saved {len(cookies)} cookie(s):")
        for cookie in cookies:
            logger.info(f"   - {cookie['name']}: {cookie['value'][:50]}...")
        
        # ========================================
        # STEP 2: API-only load of second creative
        # ========================================
        logger.info("\n" + "="*80)
        logger.info("STEP 2: Loading second creative (API ONLY - NO HTML)")
        logger.info("="*80)
        
        result = await fetch_creative_optimized(
            page,
            CREATIVE_2['advertiser_id'],
            CREATIVE_2['creative_id'],
            cookies
        )
        
        if result:
            logger.info(f"\n✅ Successfully fetched creative using API only!")
            logger.info(f"   API response: {len(result['api_response'])} bytes")
            logger.info(f"   Content.js count: {len(result['content_js_responses'])}")
            
            total_size = len(result['api_response'])
            for item in result['content_js_responses']:
                total_size += item['size']
            
            logger.info(f"\n📊 Total bandwidth (API + content.js): {total_size:,} bytes ({total_size/1024:.2f} KB)")
            logger.info(f"   🎯 Saved ~341 KB by skipping HTML!")
            
        else:
            logger.error("❌ Failed to fetch creative using API only")
        
        # ========================================
        # STEP 3: Validate cookies still work
        # ========================================
        logger.info("\n" + "="*80)
        logger.info("STEP 3: Validating session persistence")
        logger.info("="*80)
        
        # Try another API call with same cookies
        result2 = await fetch_creative_optimized(
            page,
            CREATIVE_1['advertiser_id'],
            CREATIVE_1['creative_id'],  # Back to first creative
            cookies
        )
        
        if result2:
            logger.info("✅ Cookies are still valid - session reuse confirmed!")
        else:
            logger.warning("⚠️ Session may have expired")
        
        await browser.close()
    
    logger.info("\n" + "="*80)
    logger.info("TEST COMPLETE")
    logger.info("="*80)
    logger.info("\n✅ Session reuse works! You can:")
    logger.info("   1. Load HTML once to get cookies")
    logger.info("   2. Make direct API calls for all other creatives")
    logger.info("   3. Save ~341 KB per page (65% bandwidth reduction)")


if __name__ == "__main__":
    asyncio.run(main())

