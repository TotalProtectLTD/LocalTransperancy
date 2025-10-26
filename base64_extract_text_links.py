#!/usr/bin/env python3
"""
Extract app IDs from Google Ads transparency debug files.
Simplified version - outputs only unique app IDs.
"""

import re
import urllib.parse
import codecs
import base64
from pathlib import Path


def url_decode_text(text):
    """URL decode text, handling multiple encoding layers"""
    previous = None
    while previous != text:
        previous = text
        text = urllib.parse.unquote(text)
    return text


def decode_javascript_escapes(text):
    """Decode JavaScript escape sequences like \\x3d, \\/"""
    try:
        text = codecs.decode(text, 'unicode_escape')
    except:
        pass
    return text


def decode_base64_value(b64_string):
    """Decode Base64 with automatic padding and error recovery"""
    original_length = len(b64_string)
    
    # Strategy 1: Standard padding
    try:
        missing_padding = original_length % 4
        if missing_padding:
            b64_string += '=' * (4 - missing_padding)
        return base64.b64decode(b64_string).decode('utf-8', errors='replace')
    except:
        pass
    
    # Strategy 2: Remove last char if length is 4n+1 (invalid)
    if original_length % 4 == 1:
        try:
            b64_trimmed = b64_string[:-1]
            missing_padding = len(b64_trimmed) % 4
            if missing_padding:
                b64_trimmed += '=' * (4 - missing_padding)
            return base64.b64decode(b64_trimmed).decode('utf-8', errors='replace')
        except:
            pass
    
    # Strategy 3: Try adding == padding
    if original_length % 4 == 0:
        try:
            return base64.b64decode(b64_string + '==').decode('utf-8', errors='replace')
        except:
            pass
    
    # Strategy 4: Remove 1-3 chars and retry
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


def extract_app_ids(decoded_text):
    """Extract app IDs (10-13 digit numbers) from decoded Base64 text"""
    if not decoded_text:
        return []
    
    # Look for 10-13 digit numbers (typical app ID length)
    # Use lookahead/lookbehind to match numbers not surrounded by other digits
    app_ids = re.findall(r'(?<!\d)\d{10,13}(?!\d)', decoded_text)
    return list(set(app_ids))  # Return unique IDs


def extract_ad_parameters_from_file(file_path, domain_prefix='ads-rendering-prod.corp.google.com'):
    """Extract ad= parameter values from a file"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except:
        return []
    
    # URL decode
    decoded_content = url_decode_text(content)
    
    # Find links with domain prefix + backslash that contain ad=
    pattern = rf'{re.escape(domain_prefix)}\\[^\s\'"<>]*'
    links = re.findall(pattern, decoded_content)
    
    ad_params = []
    for link in links:
        # Decode JavaScript escapes
        link = decode_javascript_escapes(link)
        # URL decode again
        link = url_decode_text(link)
        
        # Extract ad= parameter
        ad_match = re.search(r'ad=([^&\s\'"<>]+)', link)
        if ad_match:
            ad_params.append(ad_match.group(1))
    
    return ad_params


def extract_app_ids_from_pattern(file_pattern, debug_dir='debug', verbose=False):
    """
    Extract all unique app IDs from files matching the pattern.
    
    Args:
        file_pattern: Pattern to match in filenames (e.g., "778557462128")
        debug_dir: Directory containing debug files (default: 'debug')
        verbose: Print debug information (default: False)
    
    Returns:
        set: Unique app IDs found
    """
    script_dir = Path(__file__).parent
    debug_path = script_dir / debug_dir
    
    if not debug_path.exists():
        print(f"Error: Directory not found: {debug_path}")
        return set()
    
    # Find matching files
    files = list(debug_path.glob(f"*{file_pattern}*.txt"))
    
    if not files:
        print(f"No files found matching pattern: *{file_pattern}*.txt")
        return set()
    
    if verbose:
        print(f"Found {len(files)} files")
    
    all_app_ids = set()
    unique_base64_strings = set()
    
    # Process each file
    for file_path in files:
        ad_params = extract_ad_parameters_from_file(file_path)
        unique_base64_strings.update(ad_params)
        if verbose and ad_params:
            print(f"  {file_path.name}: {len(ad_params)} ad params")
    
    if verbose:
        print(f"Total unique Base64 strings: {len(unique_base64_strings)}")
    
    # Decode unique Base64 strings and extract app IDs
    for b64_string in unique_base64_strings:
        decoded = decode_base64_value(b64_string)
        if decoded:
            app_ids = extract_app_ids(decoded)
            all_app_ids.update(app_ids)
    
    return all_app_ids


def extract_app_ids_from_single_file(file_path):
    """Extract app IDs from a single file (like html.txt)"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except:
        print(f"Error reading file: {file_path}")
        return set()
    
    # URL decode the content multiple times
    decoded_content = url_decode_text(content)
    
    # Extract ad= parameters from URLs
    ad_pattern = r'ad=([A-Za-z0-9+/=_-]+)'
    ad_params = re.findall(ad_pattern, decoded_content)
    
    # Deduplicate
    unique_ad_params = set(ad_params)
    
    all_app_ids = set()
    for ad_param in unique_ad_params:
        decoded = decode_base64_value(ad_param)
        if decoded:
            app_ids = extract_app_ids(decoded)
            all_app_ids.update(app_ids)
    
    return all_app_ids


def main():
    """Main function"""
    all_results = {}
    
    # Try html.txt first
    script_dir = Path(__file__).parent
    html_file = script_dir / 'debug' / 'html.txt'
    if html_file.exists():
        app_ids = extract_app_ids_from_single_file(html_file)
        if app_ids:
            all_results['html.txt'] = app_ids
        else:
            # Check if file was processed but no IDs found
            try:
                with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                    if f.read(100):  # File exists and has content
                        all_results['html.txt'] = set(['No numeric app IDs (URL-based ads)'])
            except:
                pass
    
    # Process numbered file patterns
    file_patterns = ["778557462128", "779887668213"]
    for pattern in file_patterns:
        app_ids = extract_app_ids_from_pattern(pattern, verbose=False)
        if app_ids:
            all_results[pattern] = app_ids
    
    # Output results
    if all_results:
        for source, app_ids in all_results.items():
            print(f"{source}: {', '.join(sorted(app_ids))}")
    else:
        print("No app IDs found.")
    
    return all_results


if __name__ == "__main__":
    main()
