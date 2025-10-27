"""
Google Ads Transparency Scraper - API Response Analysis Module

This module provides functions for parsing and analyzing API responses from
Google Ads Transparency Center. It extracts critical information needed for
scraping validation, content detection, and data extraction.

Functions in this module handle:
- Extracting expected fletch-render IDs from GetCreativeById responses
- Detecting static/cached creatives with no dynamic content
- Checking for empty API responses
- Verifying creative existence in SearchCreatives
- Extracting real 12-digit creative IDs from API data
- Extracting funded_by sponsor information

All functions work with captured API response dictionaries and use regex patterns
from google_ads_config.py for parsing. The functions follow consistent patterns
for error handling and JSON parsing.

This module will be imported by google_ads_content.py and google_ads_validation.py
in subsequent refactoring phases.
"""

import re
import json
import codecs
from typing import List, Dict, Any, Optional, Set

from google_ads_config import (
    PATTERN_CREATIVE_ID_FROM_PAGE_URL,
    PATTERN_CONTENT_JS_URL,
    PATTERN_FLETCH_RENDER_ID,
    PATTERN_CREATIVE_ID_FROM_URL,
    API_GET_CREATIVE_BY_ID,
    API_SEARCH_CREATIVES,
    STATIC_IMAGE_AD_URL,
    STATIC_HTML_AD_URL,
    ARCHIVE_PATH,
    ARCHIVE_INDEX_FILE,
    FLETCH_RENDER_MARKER
)


# ============================================================================
# API RESPONSE ANALYSIS FUNCTIONS
# ============================================================================


def extract_expected_fletch_renders_from_api(
    api_responses: List[Dict[str, Any]],
    page_url: str,
    debug: bool = False
) -> Set[str]:
    """
    Extract expected fletch-render IDs from GetCreativeById API response.
    
    This function parses the GetCreativeById API response to find all content.js
    URLs, then extracts fletch-render IDs from those URLs. These IDs represent
    the expected dynamic content files that should be loaded for the creative.
    
    The function handles both plain and Unicode-escaped URL formats (\u003d, \u0026)
    commonly found in JSON API responses.
    
    Args:
        api_responses: List of captured API response dictionaries, each containing
                       'url', 'text', 'type', and 'timestamp' keys.
        page_url: Full page URL containing the creative ID (format: /creative/CR123...).
        debug: If True, print detailed extraction progress and results.
    
    Returns:
        Set of fletch-render ID strings (e.g., {"13006300890096633430", "13324661215579882186"}).
        Returns empty set if no GetCreativeById response found or parsing fails.
    
    Example:
        api_responses = [
            {'url': '...GetCreativeById...', 'text': '{...}', 'type': 'GetCreativeById', 'timestamp': 123.45}
        ]
        expected_ids = extract_expected_fletch_renders_from_api(
            api_responses,
            'https://adstransparency.google.com/advertiser/AR123/creative/CR456',
            debug=True
        )
        # Returns: {'13006300890096633430', '13324661215579882186'}
    """
    # Extract main creative ID from page URL
    match = re.search(PATTERN_CREATIVE_ID_FROM_PAGE_URL, page_url)
    if not match:
        return set()
    
    page_creative_id = match.group(1)
    
    # Find GetCreativeById response
    for api_resp in api_responses:
        api_url = api_resp.get('url', '')
        
        if API_GET_CREATIVE_BY_ID not in api_url:
            continue
        
        try:
            text = api_resp.get('text', '')
            
            # Check if this response is for our creative
            if page_creative_id not in text:
                continue
            
            if debug:
                print(f"  📋 Found GetCreativeById API response for {page_creative_id}")
            
            # Extract ALL content.js URLs from the API response using regex
            # The URLs contain fletch-render IDs and represent our "expected" list
            # Pattern matches: https://displayads-formats.googleusercontent.com/ads/preview/content.js?...
            # Handles both plain and escaped formats (\u003d becomes =, etc.)
            content_js_urls = re.findall(PATTERN_CONTENT_JS_URL, text)
            
            # Extract fletch-render IDs from these URLs
            expected_fletch_ids = set()
            for url_fragment in content_js_urls:
                # Decode unicode escapes if present (\u003d becomes =, \u0026 becomes &)
                # This handles JSON-escaped URLs in API responses
                try:
                    # Use codecs.decode to properly handle \uXXXX unicode escapes
                    import codecs
                    decoded_url = codecs.decode(url_fragment, 'unicode-escape')
                except:
                    decoded_url = url_fragment
                
                # Extract fletch-render ID
                fr_match = re.search(PATTERN_FLETCH_RENDER_ID, decoded_url)
                if fr_match:
                    expected_fletch_ids.add(fr_match.group(1))
            
            if debug:
                print(f"  ✅ Expecting {len(expected_fletch_ids)} content.js with fletch-render IDs: {list(expected_fletch_ids)}")
            
            return expected_fletch_ids
            
        except Exception as e:
            if debug:
                print(f"  ⚠️  Error parsing API: {e}")
            continue
    
    return set()


def check_if_static_cached_creative(
    api_responses: List[Dict[str, Any]],
    page_url: str
) -> Optional[Dict[str, Any]]:
    """
    Check if the creative is a static/cached ad with no dynamic content.js.
    
    Detects two types of static/cached creatives by analyzing GetCreativeById:
    1. Static image ads: Contains archive/simgad URLs (cached static images)
    2. Cached HTML text ads: Contains archive/sadbundle or archive/index.html
    
    These creatives don't have dynamic content.js files with fletch-render IDs,
    so the scraper should skip waiting for dynamic content and report accordingly.
    
    Args:
        api_responses: List of captured API response dictionaries.
        page_url: Full page URL containing the creative ID.
    
    Returns:
        Dictionary with static content info if detected:
            {
                'is_static': True,
                'creative_id': 'CR123456789012',
                'creative_id_12digit': '123456789012',
                'content_type': 'image' or 'html',
                'reason': 'Description of why it's static'
            }
        Returns None if creative has dynamic content (fletch-render URLs present).
    
    Example:
        result = check_if_static_cached_creative(api_responses, page_url)
        if result:
            print(f"Static {result['content_type']} ad detected: {result['reason']}")
    """
    # Extract creative ID from URL
    match = re.search(PATTERN_CREATIVE_ID_FROM_PAGE_URL, page_url)
    if not match:
        return None
    
    url_creative_id = match.group(1)
    
    # Find GetCreativeById response
    for api_resp in api_responses:
        if API_GET_CREATIVE_BY_ID not in api_resp.get('url', ''):
            continue
        
        try:
            text = api_resp.get('text', '')
            
            # Check if this response contains our creative ID
            if url_creative_id not in text:
                continue
            
            # Check for different types of cached content markers in API response
            # - simgad: Static image ads stored in Google's archive
            # - sadbundle: Cached HTML text ads
            # - archive/index.html: Generic cached content
            # - fletch-render: Dynamic content (if present, NOT static)
            has_simgad = STATIC_IMAGE_AD_URL in text
            has_sadbundle = STATIC_HTML_AD_URL in text
            has_archive_index = ARCHIVE_PATH in text and ARCHIVE_INDEX_FILE in text
            has_fletch_render = FLETCH_RENDER_MARKER in text
            
            # If has fletch-render, it's dynamic content (not static)
            # Early exit to avoid false positives
            if has_fletch_render:
                continue
            
            url_creative_id_numeric = url_creative_id.replace('CR', '')
            
            # Case 1: Static image ad (simgad)
            if has_simgad:
                return {
                    'is_static': True,
                    'creative_id': url_creative_id,
                    'creative_id_12digit': url_creative_id_numeric,
                    'content_type': 'image',
                    'reason': 'Static image ad with cached content - no dynamic content.js available'
                }
            
            # Case 2: Cached HTML text ad (sadbundle or other archive index.html)
            if has_sadbundle or has_archive_index:
                return {
                    'is_static': True,
                    'creative_id': url_creative_id,
                    'creative_id_12digit': url_creative_id_numeric,
                    'content_type': 'html',
                    'reason': 'Cached HTML text ad - no dynamic content.js available'
                }
        
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    
    return None


def check_empty_get_creative_by_id(
    api_responses: List[Dict[str, Any]],
    page_url: str
) -> bool:
    """
    Check if GetCreativeById returned empty {} for the target creative.
    
    An empty GetCreativeById response indicates the creative may not exist
    or is not accessible. This triggers a fallback to SearchCreatives to
    verify if the creative exists in the advertiser's creative list.
    
    Args:
        api_responses: List of captured API response dictionaries.
        page_url: Full page URL containing the creative ID.
    
    Returns:
        True if GetCreativeById response is empty {} or doesn't contain
        the target creative. False if response contains valid creative data.
    
    Note:
        This function is used for early-exit optimization in the smart wait
        loop. If GetCreativeById is empty, the scraper waits for SearchCreatives
        to verify creative existence before timing out.
    """
    # Extract creative ID from URL
    match = re.search(PATTERN_CREATIVE_ID_FROM_PAGE_URL, page_url)
    if not match:
        return False
    
    page_creative_id = match.group(1)
    
    # Find GetCreativeById response
    for api_resp in api_responses:
        if API_GET_CREATIVE_BY_ID not in api_resp.get('url', ''):
            continue
        
        try:
            text = api_resp.get('text', '').strip()
            
            # Check if response is empty {}
            if text == '{}':
                return True
            
            # Also check if it's valid JSON but doesn't contain our creative
            data = json.loads(text)
            response_creative_id = data.get('1', {}).get('2', '')
            
            # If it has data but for a different creative, keep looking
            if response_creative_id and response_creative_id != page_creative_id:
                continue
            
            # If it has data for our creative, not empty
            if response_creative_id == page_creative_id:
                return False
                
        except (json.JSONDecodeError, KeyError):
            continue
    
    return False


def check_creative_in_search_creatives(
    api_responses: List[Dict[str, Any]],
    page_url: str
) -> bool:
    """
    Check if the target creative exists in SearchCreatives response.
    
    SearchCreatives returns a list of all creatives for an advertiser.
    This function verifies if the target creative (from page URL) is
    present in that list, confirming the creative exists.
    
    Used as a fallback verification when GetCreativeById is empty.
    
    Args:
        api_responses: List of captured API response dictionaries.
        page_url: Full page URL containing the creative ID.
    
    Returns:
        True if creative found in SearchCreatives list, False otherwise.
    
    Example:
        if check_empty_get_creative_by_id(api_responses, page_url):
            # GetCreativeById is empty, check SearchCreatives
            if check_creative_in_search_creatives(api_responses, page_url):
                print("Creative exists but GetCreativeById is empty")
            else:
                print("Creative not found - may not exist")
    """
    # Extract creative ID from URL
    match = re.search(PATTERN_CREATIVE_ID_FROM_PAGE_URL, page_url)
    if not match:
        return False
    
    page_creative_id = match.group(1)
    
    # Check SearchCreatives responses
    for api_resp in api_responses:
        if API_SEARCH_CREATIVES not in api_resp.get('url', ''):
            continue
        
        try:
            data = json.loads(api_resp.get('text', ''))
            creatives_list = data.get('1', [])
            
            for creative in creatives_list:
                creative_id = creative.get('2', '')
                if creative_id == page_creative_id:
                    return True
                    
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    
    return False


def extract_real_creative_id_from_api(
    api_responses: List[Dict[str, Any]],
    page_url: str
) -> Optional[str]:
    """
    Extract real 12-digit creative ID from API responses.
    
    Tries multiple API sources for maximum reliability:
    1. GetCreativeById (primary): Fastest, most direct source
    2. SearchCreatives (fallback): Contains all advertiser creatives
    
    The "real" creative ID is the 12-digit numeric ID used in content.js
    URLs (creativeId parameter), which may differ from the CR-prefixed ID
    in the page URL.
    
    Args:
        api_responses: List of captured API response dictionaries.
        page_url: Full page URL containing the CR-prefixed creative ID.
    
    Returns:
        12-digit numeric creative ID string (e.g., "773510960098") if found,
        None if extraction fails from all sources.
    
    Example:
        creative_id = extract_real_creative_id_from_api(
            api_responses,
            'https://adstransparency.google.com/advertiser/AR123/creative/CR773510960098'
        )
        # Returns: '773510960098'
    """
    # Extract main creative ID from page URL
    match = re.search(PATTERN_CREATIVE_ID_FROM_PAGE_URL, page_url)
    if not match:
        return None
    
    page_creative_id = match.group(1)
    
    # Method 1: Try GetCreativeById first (fastest, most direct)
    # This API returns detailed creative data including content.js URLs
    # Extract creativeId parameter from the first content.js URL
    for api_resp in api_responses:
        if API_GET_CREATIVE_BY_ID not in api_resp.get('url', ''):
            continue
        
        try:
            data = json.loads(api_resp['text'])
            
            # Check if this response is for our creative
            response_creative_id = data.get('1', {}).get('2', '')
            
            if response_creative_id != page_creative_id:
                continue
            
            # Extract numeric creative ID from content.js URLs
            content_urls = data.get('1', {}).get('5', [])
            
            if not content_urls:
                continue
            
            # Get first URL
            first_url = content_urls[0].get('1', {}).get('4', '')
            
            # Extract creativeId parameter
            match = re.search(PATTERN_CREATIVE_ID_FROM_URL, first_url)
            if match:
                return match.group(1)
        
        except (json.JSONDecodeError, KeyError):
            continue
    
    # Method 2: Fallback to SearchCreatives (contains all advertiser creatives)
    # This API returns a list of all creatives for the advertiser
    # Find our creative in the list and extract its numeric ID
    searched_creatives = False
    for api_resp in api_responses:
        if API_SEARCH_CREATIVES not in api_resp.get('url', ''):
            continue
        
        searched_creatives = True
        try:
            data = json.loads(api_resp['text'])
            
            # SearchCreatives returns a list of creatives
            creatives_list = data.get('1', [])
            
            # Debug: Show we're searching
            # print(f"   Checking SearchCreatives: {len(creatives_list)} creatives found")
            
            for creative in creatives_list:
                # Check if this is our creative
                creative_id = creative.get('2', '')
                
                if creative_id == page_creative_id:
                    # Found it! Extract numeric creative ID from content.js URL
                    content_url = creative.get('3', {}).get('1', {}).get('4', '')
                    
                    if content_url:
                        match = re.search(PATTERN_CREATIVE_ID_FROM_URL, content_url)
                        if match:
                            # print(f"   ✅ Found in SearchCreatives: {match.group(1)}")
                            return match.group(1)
        
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # print(f"   ⚠️ Error parsing SearchCreatives: {e}")
            continue
    
    # if searched_creatives:
    #     print(f"   ⚠️ SearchCreatives checked but creative {page_creative_id} not found")
    
    return None


def extract_funded_by_from_api(
    api_responses: List[Dict[str, Any]],
    page_url: str
) -> Optional[str]:
    """
    Extract funded_by (sponsor company name) from GetCreativeById API response.
    
    The funded_by field is found in GetCreativeById response at path: data['1']['22']
    This represents the name of the sponsor company for the creative.
    
    Args:
        api_responses: List of captured API response dictionaries.
        page_url: Full page URL containing the CR-prefixed creative ID.
    
    Returns:
        String with sponsored company name (e.g., "BlueVision Interactive Limited") if found,
        None if extraction fails or field is not present.
    
    Example:
        funded_by = extract_funded_by_from_api(
            api_responses,
            'https://adstransparency.google.com/advertiser/AR123/creative/CR456'
        )
        # Returns: 'BlueVision Interactive Limited'
    """
    # Extract main creative ID from page URL
    match = re.search(PATTERN_CREATIVE_ID_FROM_PAGE_URL, page_url)
    if not match:
        return None
    
    page_creative_id = match.group(1)
    
    # Find GetCreativeById response
    for api_resp in api_responses:
        if API_GET_CREATIVE_BY_ID not in api_resp.get('url', ''):
            continue
        
        try:
            data = json.loads(api_resp['text'])
            
            # Check if this response is for our creative
            response_creative_id = data.get('1', {}).get('2', '')
            
            if response_creative_id != page_creative_id:
                continue
            
            # Extract funded_by from field "22"
            # Field "22" can be a string directly or nested dict like {"1": "Company Name"}
            funded_by_field = data.get('1', {}).get('22')
            
            if funded_by_field and isinstance(funded_by_field, str):
                return funded_by_field.strip()
            elif funded_by_field and isinstance(funded_by_field, dict):
                # Handle nested format: {"1": "Company Name"}
                funded_by = funded_by_field.get('1', '')
                if funded_by and isinstance(funded_by, str):
                    return funded_by.strip()
        
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    
    return None

