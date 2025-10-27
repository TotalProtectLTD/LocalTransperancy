#!/usr/bin/env python3
"""
Refactored version of fighting_cache_problem.py
Modular structure with separated concerns.

Usage:
    python3 fighting_cache_problem_refactored.py
"""

import asyncio
import logging
import time
from playwright.async_api import async_playwright

# Import configuration
from cache_config import *
from cache_storage import (
    save_to_cache,
    load_from_cache,
    get_cache_status,
    format_bytes,
    MEMORY_CACHE
)
from cache_models import get_cache_filename
from proxy_manager import setup_proxy, teardown_proxy, get_proxy_config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Temp directory for logs
TEMP_DIR = os.path.join(SCRIPT_DIR, 'temp_network_logs')
os.makedirs(TEMP_DIR, exist_ok=True)


class NetworkLogger:
    """Simplified network logger."""
    
    def __init__(self, output_dir, context):
        self.output_dir = output_dir
        self.context = context
        self.request_count = 0
        self.response_count = 0
        self.blocked_count = 0
        self.cache_hit_count = 0
        
    def log_request(self, request):
        """Log request."""
        self.request_count += 1
        logger.info(f"[REQUEST #{self.request_count}] {request.method} {request.resource_type} - {request.url[:100]}")
    
    async def log_response(self, response):
        """Log response."""
        self.response_count += 1
        logger.info(f"[RESPONSE #{self.response_count}] {response.status} - {response.url[:100]}")


def create_route_handler(network_logger):
    """Create route handler for URL blocking and caching."""
    
    async def handle_route(route):
        url = route.request.url
        resource_type = route.request.resource_type
        
        # Priority 1: Smart caching for main.dart.js files
        if USE_LOCAL_CACHE_FOR_MAIN_DART and MAIN_DART_JS_URL_PATTERN in url:
            try:
                # Try cache
                cached_content, metadata = load_from_cache(url)
                
                if cached_content:
                    # Cache hit
                    await route.fulfill(
                        status=200,
                        headers={
                            'Content-Type': 'text/javascript',
                            'Cache-Control': 'public, max-age=86400',
                            'X-Served-From': 'local-cache',
                            'Access-Control-Allow-Origin': '*'
                        },
                        body=cached_content
                    )
                    
                    network_logger.cache_hit_count += 1
                    filename = get_cache_filename(url)
                    logger.info(f"[CACHE HIT] Served {filename} from cache")
                    return
                else:
                    # Cache miss - download and cache
                    if AUTO_CACHE_ON_MISS:
                        filename = get_cache_filename(url)
                        logger.info(f"[CACHE MISS] {filename}, downloading...")
                        
                        response = await route.fetch()
                        body = await response.text()
                        
                        # Save to cache
                        await save_to_cache(url, body, dict(response.headers))
                        
                        # Forward response
                        await route.fulfill(
                            status=response.status,
                            headers=dict(response.headers),
                            body=body
                        )
                        return
                    else:
                        await route.continue_()
                        return
                        
            except Exception as e:
                logger.error(f"[CACHE ERROR] {e}")
        
        # Skip blocking if disabled
        if not ENABLE_BLOCKING:
            await route.continue_()
            return
        
        # Block by resource type
        if resource_type in BLOCKED_RESOURCE_TYPES:
            network_logger.blocked_count += 1
            await route.abort()
            return
        
        # Block by URL pattern
        for pattern in BLOCKED_URL_PATTERNS:
            if pattern in url:
                network_logger.blocked_count += 1
                await route.abort()
                return
        
        # Special handling for gstatic.com
        if 'gstatic.com' in url:
            if any(pattern in url for pattern in GSTATIC_BLOCKED_PATTERNS):
                network_logger.blocked_count += 1
                await route.abort()
                return
        
        # Allow request
        await route.continue_()
    
    return handle_route


async def main():
    """Main function."""
    
    target_url = "https://adstransparency.google.com/advertiser/AR08722290881173913601/creative/CR13612220978573606913?region=anywhere&platform=YOUTUBE"
    
    logger.info("="*80)
    logger.info("Starting Playwright Network Logger (Refactored)")
    logger.info(f"Target URL: {target_url}")
    logger.info(f"Traffic Measurement: {'MITMPROXY (precise)' if USE_MITMPROXY else 'ESTIMATION'}")
    
    # Display cache status
    if USE_LOCAL_CACHE_FOR_MAIN_DART:
        cache_files = get_cache_status()
        if cache_files:
            logger.info(f"\nCache Status: {len(cache_files)} file(s) cached")
            for cf in cache_files:
                age = cf.get('age_hours', 0)
                expired_marker = " [EXPIRED]" if cf.get('expired', False) else ""
                version = cf.get('version', 'unknown')
                version_short = version[-20:] if version and len(version) > 20 else version
                logger.info(f"  - {cf['filename']}: {format_bytes(cf['size'])}, age: {age:.1f}h, v:{version_short}{expired_marker}")
        else:
            logger.info("\nCache Status: Empty (files will be downloaded)")
    
    logger.info("="*80)
    
    # Setup proxy
    proxy_process, use_proxy = await setup_proxy()
    proxy_results = None
    start_time = time.time()
    
    try:
        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox'
                ]
            )
            
            # Create context
            context_options = {
                'viewport': {'width': 1920, 'height': 1080},
                'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'locale': 'en-US',
                'timezone_id': 'America/New_York',
            }
            
            # Add proxy config
            context_options.update(get_proxy_config())
            
            context = await browser.new_context(**context_options)
            
            # Initialize network logger
            network_logger = NetworkLogger(TEMP_DIR, context)
            
            # Create route handler
            route_handler = create_route_handler(network_logger)
            await context.route('**/*', route_handler)
            
            page = await context.new_page()
            
            # Set up event listeners
            page.on('request', lambda request: network_logger.log_request(request))
            page.on('response', lambda response: asyncio.create_task(network_logger.log_response(response)))
            
            logger.info("\nNavigating to target URL...")
            
            try:
                # Navigate
                response = await page.goto(target_url, wait_until='networkidle', timeout=60000)
                logger.info(f"\nPage loaded with status: {response.status}")
                
                # Wait for additional requests
                logger.info("\nWaiting 5 seconds to capture additional network activity...")
                await asyncio.sleep(5)
                
                # Scroll
                logger.info("\nScrolling page...")
                try:
                    await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1)
                except Exception as scroll_error:
                    logger.warning(f"Scroll error: {scroll_error}")
                
                logger.info("\nCapture complete!")
                
            except Exception as e:
                logger.error(f"Error during navigation: {e}")
            
            finally:
                duration_ms = (time.time() - start_time) * 1000
                await browser.close()
    
    finally:
        # Stop proxy
        proxy_results = await teardown_proxy(proxy_process)
    
    # Print summary
    logger.info("\n" + "="*80)
    logger.info("FINAL SUMMARY")
    logger.info("="*80)
    logger.info(f"Total Requests: {network_logger.request_count}")
    logger.info(f"Total Responses: {network_logger.response_count}")
    logger.info(f"Cache Hits: {network_logger.cache_hit_count}")
    logger.info(f"Blocked Requests: {network_logger.blocked_count}")
    
    if proxy_results:
        logger.info(f"\nTraffic Statistics:")
        logger.info(f"  - Measurement method: proxy (precise)")
        logger.info(f"  - Incoming: {format_bytes(proxy_results['total_response_bytes'])}")
        logger.info(f"  - Outgoing: {format_bytes(proxy_results['total_request_bytes'])}")
        logger.info(f"  - Total: {format_bytes(proxy_results['total_bytes'])}")
        logger.info(f"  - Duration: {duration_ms:.0f} ms")
    
    # Memory cache stats
    if MEMORY_CACHE:
        memory_size = sum(cf.size for cf in MEMORY_CACHE.values())
        logger.info(f"\nMemory Cache:")
        logger.info(f"  - Files in memory: {len(MEMORY_CACHE)}")
        logger.info(f"  - Memory used: {format_bytes(memory_size)}")
    
    logger.info("="*80)
    logger.info("\nScript completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())

