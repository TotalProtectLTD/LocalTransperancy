#!/usr/bin/env python3
"""
Simple utility to extract Google Ads app IDs from text content.

Usage:
    from extract_app_ids import extract_app_ids
    
    # Read your file
    with open('file.txt', 'r') as f:
        text = f.read()
    
    # Get app IDs
    app_ids = extract_app_ids(text)
    print(app_ids)  # {'6745007288', '1086101495'}
"""

import re
import urllib.parse
import codecs
import base64


def extract_app_ids(text):
    """
    Extract all unique Google Ads app IDs from text content.
    
    This function handles:
    - URL decoding (multiple layers)
    - JavaScript escape sequences (\x3d, \/, etc.)
    - Base64 decoding with error recovery
    - App ID extraction (10-13 digit numbers)
    
    Args:
        text (str): Raw text content from any source (HTML, debug files, etc.)
        
    Returns:
        set: Unique app IDs found (as strings), or empty set if none found
        
    Example:
        >>> text = "ads-rendering-prod.corp.google.com\\search?ad=base64..."
        >>> app_ids = extract_app_ids(text)
        >>> print(app_ids)
        {'6745007288'}
    """
    
    # Step 1: URL decode recursively
    decoded_text = text
    previous = None
    while previous != decoded_text:
        previous = decoded_text
        decoded_text = urllib.parse.unquote(decoded_text)
    
    # Step 2: Decode JavaScript escapes
    try:
        decoded_text = codecs.decode(decoded_text, 'unicode_escape')
    except:
        pass
    
    # Step 3: Extract ad= parameters from URLs
    ad_params = set()
    
    # Pattern 1: Find links with ads-rendering-prod.corp.google.com
    pattern = r'ads-rendering-prod\.corp\.google\.com\\[^\s\'"<>]*'
    links = re.findall(pattern, decoded_text)
    
    for link in links:
        # Decode JavaScript escapes in link
        try:
            link = codecs.decode(link, 'unicode_escape')
        except:
            pass
        link = urllib.parse.unquote(link)
        
        # Extract ad= parameter
        ad_match = re.search(r'ad=([^&\s\'"<>]+)', link)
        if ad_match:
            ad_params.add(ad_match.group(1))
    
    # Pattern 2: Direct ad= extraction (for HTML content)
    direct_matches = re.findall(r'ad=([A-Za-z0-9+/=_-]+)', decoded_text)
    ad_params.update(direct_matches)
    
    # Step 4: Decode Base64 and extract app IDs
    all_app_ids = set()
    
    for ad_param in ad_params:
        decoded = _decode_base64(ad_param)
        if decoded:
            # Extract 10-13 digit numbers
            app_ids = re.findall(r'(?<!\d)\d{10,13}(?!\d)', decoded)
            all_app_ids.update(app_ids)
    
    return all_app_ids


def _decode_base64(b64_string):
    """Decode Base64 with automatic padding and error recovery."""
    original_length = len(b64_string)
    
    # Try standard padding
    try:
        missing_padding = original_length % 4
        if missing_padding:
            b64_string += '=' * (4 - missing_padding)
        return base64.b64decode(b64_string).decode('utf-8', errors='replace')
    except:
        pass
    
    # Try removing last char if length is 4n+1 (invalid)
    if original_length % 4 == 1:
        try:
            b64_trimmed = b64_string[:-1]
            missing_padding = len(b64_trimmed) % 4
            if missing_padding:
                b64_trimmed += '=' * (4 - missing_padding)
            return base64.b64decode(b64_trimmed).decode('utf-8', errors='replace')
        except:
            pass
    
    # Try adding == padding
    if original_length % 4 == 0:
        try:
            return base64.b64decode(b64_string + '==').decode('utf-8', errors='replace')
        except:
            pass
    
    # Try removing 1-3 chars
    for chars_to_remove in [1, 2, 3]:
        try:
            b64_trimmed = b64_string[:-chars_to_remove]
            missing_padding = len(b64_trimmed) % 4
            if missing_padding:
                b64_trimmed += '=' * (4 - missing_padding)
            return base64.b64decode(b64_trimmed).decode('utf-8', errors='replace')
        except:
            continue
    
    return None


# Example usage
if __name__ == "__main__":
    # Test with sample
    sample = """
    ads-rendering-prod.corp.google.com\\search?ad=evQBQi9EdXBpQ2xlYW4gLSBBSVNjYW5FbmdpbmUgfCBpcGhvbmUgdmlydXMgY2xlYW5lckoAUhljbGVhbiB1cCBkdXBsaWNhdGUgcGhvdG9zaAX6AaABygOZARqWAQgBEgo2NzQ1MDA3Mjg4ShhEdXBpQ2xlYW4gLSBBSVNjYW5FbmdpbmVSAFoAYmgKZi8vbGgzLmdvb2dsZXVzZXJjb250ZW50LmNvbS9EVDdGbmN4Sk9BQjZmOHFhT0d5WjVsYlBpQ2EySnNvcHRTU2kxVnZPTkl6X0FmMHdHVnA0Y296aGVtTkxXbWI3cnB0Mlh0MVlDZ6IEAA==
    """
    
    app_ids = extract_app_ids(sample)
    print(f"Found app IDs: {app_ids}")
