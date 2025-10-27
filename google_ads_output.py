"""
Google Ads Transparency Scraper - Output Formatting Module

This module provides output formatting and result display functions for the
Google Ads Transparency scraper suite.

Key Features:
- Byte count formatting to human-readable units (B, KB, MB, GB, TB)
- Comprehensive result printing with formatted sections and emoji icons
- Support for all result types: execution status, videos, App Store IDs,
  funded_by, creative ID, extraction method, traffic statistics, and
  performance metrics

The functions in this module are pure display/formatting functions used to
present scraping results to the user in a clear, visually appealing format
with consistent 80-character section separators.

Usage:
    from google_ads_output import print_results
    
    result = await scrape_ads_transparency_page(page_url)
    print_results(result)
"""

from typing import Dict, Any

from google_ads_config import BYTE_CONVERSION_FACTOR


# ============================================================================
# OUTPUT FORMATTING
# ============================================================================

def format_bytes(bytes_value: int) -> str:
    """
    Format byte count into human-readable string with appropriate unit.
    
    Converts byte values to KB, MB, or GB with one decimal place precision.
    Uses 1024 as the conversion factor (binary units).
    
    Args:
        bytes_value: Number of bytes to format (integer).
    
    Returns:
        Formatted string with value and unit (e.g., "1.5 MB", "523.2 KB").
    
    Example:
        print(format_bytes(1024))        # "1.0 KB"
        print(format_bytes(1536))        # "1.5 KB"
        print(format_bytes(1048576))     # "1.0 MB"
        print(format_bytes(1572864))     # "1.5 MB"
        print(format_bytes(1073741824))  # "1.0 GB"
        print(format_bytes(500))         # "500 B"
    
    Note:
        Uses binary units (1024 bytes = 1 KB) rather than decimal units
        (1000 bytes = 1 KB) for consistency with system tools.
    """
    b = bytes_value
    for unit in ['B', 'KB', 'MB', 'GB']:
        if b < BYTE_CONVERSION_FACTOR:
            return f"{b:.2f} {unit}"
        b /= BYTE_CONVERSION_FACTOR
    return f"{b:.2f} TB"


def print_results(result: Dict[str, Any]) -> None:
    """
    Print scraping results in a human-readable formatted output.
    
    Displays comprehensive scraping results including:
    - Execution status (success/failure with errors and warnings)
    - Extracted data (videos, App Store ID)
    - Creative identification (ID and method)
    - Extraction method used
    - Traffic statistics (bandwidth, requests, blocking)
    - Cache statistics (hits, misses, bandwidth saved)
    - Performance metrics (duration, API responses, content.js files)
    
    Args:
        result: Dictionary returned by scrape_ads_transparency_page() containing
                all scraping results, statistics, and metadata.
    
    Returns:
        None (prints to stdout)
    
    Example:
        result = await scrape_ads_transparency_page(page_url)
        print_results(result)
    
    Note:
        Output format uses emoji icons for visual clarity:
        - ✅/❌: Success/failure status
        - 📹: Videos section
        - 📱: App Store ID
        - 🔍: Creative ID
        - 📦: Extraction method
        - 📊: Traffic statistics
        - ⏱️: Performance metrics
        - ⚠️: Warnings
        - 🔬/🔢/🖼️: Identification methods
    """
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)
    
    # Show execution status first
    # Prefer legacy keys (execution_success, execution_errors, execution_warnings) if present
    # Fall back to new keys (success, errors, warnings) for backward compatibility
    print(f"\n{'EXECUTION STATUS':-^80}")
    execution_success = result.get('execution_success', result.get('success', False))
    execution_errors = result.get('execution_errors', result.get('errors', []))
    execution_warnings = result.get('execution_warnings', result.get('warnings', []))
    
    if execution_success:
        print("Status: ✅ SUCCESS")
    else:
        print("Status: ❌ FAILED")
        if execution_errors:
            print(f"Errors: {len(execution_errors)}")
            for err in execution_errors:
                print(f"  • {err}")
    
    if execution_warnings:
        print(f"Warnings: {len(execution_warnings)}")
        for warn in execution_warnings:
            print(f"  • {warn}")
    
    print(f"\n{'VIDEOS':-^80}")
    print(f"Videos found: {result.get('video_count', 0)}")
    for vid in result.get('videos', []):
        print(f"  • {vid}")
        print(f"    https://www.youtube.com/watch?v={vid}")
    
    print(f"\n{'APP STORE':-^80}")
    if result.get('app_store_id'):
        print(f"App Store ID: {result.get('app_store_id')}")
        print(f"  https://apps.apple.com/app/id{result.get('app_store_id')}")
    else:
        print("No App Store ID found")
    
    # Display base64-extracted app IDs
    app_ids_base64 = result.get('app_ids_from_base64', [])
    if app_ids_base64:
        print(f"\nApp IDs from base64: {len(app_ids_base64)} found")
        for app_id in sorted(app_ids_base64):
            print(f"  • {app_id}")
            print(f"    https://apps.apple.com/app/id{app_id}")
    
    print(f"\n{'FUNDED BY':-^80}")
    if result.get('funded_by'):
        print(f"Sponsor: {result['funded_by']}")
    else:
        print("No sponsor information found")
    
    print(f"\n{'CREATIVE ID':-^80}")
    print(f"Real Creative ID: {result.get('real_creative_id', 'N/A')}")
    print(f"Method used: {result.get('method_used', 'unknown')}")
    
    print(f"\n{'EXTRACTION METHOD':-^80}")
    extraction_method = result.get('extraction_method', 'unknown')
    if result.get('is_static_content'):
        print(f"Method: 🖼️  Static/Cached Content Detected")
        if result.get('static_content_info'):
            info = result['static_content_info']
            content_type = info.get('content_type', 'unknown')
            print(f"  Creative ID: {info.get('creative_id', 'N/A')}")
            if content_type == 'image':
                print(f"  Type: Image ad with cached content")
            elif content_type == 'html':
                print(f"  Type: HTML text ad with cached content")
            else:
                print(f"  Type: Cached content")
            print(f"  Reason: {info.get('reason', 'N/A')}")
    elif extraction_method == 'fletch-render':
        print(f"Method: 🎯 Fletch-Render IDs (precise API matching)")
        print(f"  Expected: {result.get('expected_fletch_renders', 0)} content.js")
        print(f"  Found: {result.get('found_fletch_renders', 0)} content.js")
    else:
        print(f"Method: ❌ None available")
    
    print(f"\n{'TRAFFIC STATISTICS':-^80}")
    method_emoji = "🔬" if result.get('measurement_method') == 'proxy' else "📊"
    method_name = "Real Proxy" if result.get('measurement_method') == 'proxy' else "Estimation"
    print(f"Measurement: {method_emoji} {method_name}")
    print(f"Incoming: {format_bytes(result.get('incoming_bytes', 0))}")
    print(f"Outgoing: {format_bytes(result.get('outgoing_bytes', 0))}")
    print(f"Total: {format_bytes(result.get('total_bytes', 0))}")
    print(f"Requests: {result.get('request_count', 0)}")
    print(f"Blocked: {result.get('url_blocked_count', 0)}")
    print(f"Duration: {result.get('duration_ms', 0):.0f} ms")
    
    if result.get('incoming_by_type'):
        print(f"\n{'Traffic by Type':-^80}")
        for resource_type, bytes_count in sorted(
            result.get('incoming_by_type', {}).items(),
            key=lambda x: x[1],
            reverse=True
        ):
            pct = (bytes_count / result.get('incoming_bytes', 0) * 100) if result.get('incoming_bytes', 0) > 0 else 0
            print(f"  {resource_type:<15} {format_bytes(bytes_count):<15} ({pct:.1f}%)")
    
    # Display cache statistics if any cacheable requests were made
    cache_total = result.get('cache_total_requests', 0)
    if cache_total > 0:
        print(f"\n{'CACHE STATISTICS':-^80}")
        cache_hits = result.get('cache_hits', 0)
        cache_misses = result.get('cache_misses', 0)
        cache_hit_rate = result.get('cache_hit_rate', 0)
        cache_bytes_saved = result.get('cache_bytes_saved', 0)
        
        print(f"Cache Hits: {cache_hits}/{cache_total} ({cache_hit_rate:.1f}%)")
        print(f"Cache Misses: {cache_misses}")
        print(f"Bandwidth Saved: {format_bytes(cache_bytes_saved)}")
        
        if cache_hits > 0:
            print(f"Status: 💾 Serving main.dart.js from cache (146x faster)")
        elif cache_misses > 0:
            print(f"Status: 🌐 Downloaded main.dart.js (will be cached for next run)")
    
    print("\n" + "="*80)

