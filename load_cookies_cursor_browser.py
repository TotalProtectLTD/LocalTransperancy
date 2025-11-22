#!/usr/bin/env python3
"""
Load Cookies into Cursor Browser Extension

This script helps you load cookies into the Cursor browser extension (MCP)
by generating JavaScript code that can be executed via browser_evaluate.

Usage:
1. Export cookies from your regular browser (Chrome/Safari) using an extension
2. Save cookies as JSON file
3. Run this script to generate JavaScript code
4. Use browser_evaluate in Cursor to execute the code
"""

import json
import sys
from pathlib import Path


def cookies_to_js(cookies_file: str) -> str:
    """
    Convert cookies JSON file to JavaScript code that sets cookies.
    
    Cookie format expected:
    [
        {
            "name": "cookie_name",
            "value": "cookie_value",
            "domain": ".google.com",
            "path": "/",
            "secure": true,
            "httpOnly": false,
            "sameSite": "Lax",
            "expires": 1234567890  # Unix timestamp (optional)
        }
    ]
    """
    with open(cookies_file, 'r') as f:
        cookies = json.load(f)
    
    js_lines = [
        "// Set cookies via JavaScript",
        "(function() {",
        "  const cookies = ["
    ]
    
    for cookie in cookies:
        name = cookie.get('name', '')
        value = cookie.get('value', '')
        domain = cookie.get('domain', '')
        path = cookie.get('path', '/')
        secure = cookie.get('secure', False)
        sameSite = cookie.get('sameSite', 'Lax')
        expires = cookie.get('expires')
        
        # Build cookie string
        cookie_str = f"{name}={value}"
        
        if domain:
            cookie_str += f"; domain={domain}"
        if path:
            cookie_str += f"; path={path}"
        if secure:
            cookie_str += "; secure"
        if sameSite:
            cookie_str += f"; SameSite={sameSite}"
        if expires and expires > 0:
            # Convert Unix timestamp to Date
            cookie_str += f"; expires={expires}"
        
        js_lines.append(f'    "{cookie_str}",')
    
    js_lines.extend([
        "  ];",
        "  ",
        "  cookies.forEach(cookieStr => {",
        "    document.cookie = cookieStr;",
        "  });",
        "  ",
        "  return `Set ${cookies.length} cookie(s)`;",
        "})();"
    ])
    
    return "\n".join(js_lines)


def cookies_to_js_simple(cookies_file: str) -> str:
    """
    Simpler version - just sets cookies without expiration handling.
    Better for session cookies.
    """
    with open(cookies_file, 'r') as f:
        cookies = json.load(f)
    
    js_code = "// Set cookies\n"
    js_code += "(function() {\n"
    
    for cookie in cookies:
        name = cookie.get('name', '')
        value = cookie.get('value', '')
        domain = cookie.get('domain', '')
        path = cookie.get('path', '/')
        secure = cookie.get('secure', False)
        sameSite = cookie.get('sameSite', 'Lax')
        
        # Build cookie assignment
        cookie_assign = f"document.cookie = '{name}={value}"
        if domain:
            cookie_assign += f"; domain={domain}"
        if path:
            cookie_assign += f"; path={path}"
        if secure:
            cookie_assign += "; secure"
        if sameSite:
            cookie_assign += f"; SameSite={sameSite}"
        cookie_assign += "';\n"
        
        js_code += cookie_assign
    
    js_code += f"  return `Set {len(cookies)} cookie(s)`;\n"
    js_code += "})();"
    
    return js_code


def create_cursor_browser_script(cookies_file: str, output_file: str = None):
    """
    Create a complete script for loading cookies in Cursor browser.
    """
    js_code = cookies_to_js_simple(cookies_file)
    
    if output_file:
        with open(output_file, 'w') as f:
            f.write(js_code)
        print(f"✅ JavaScript code saved to: {output_file}")
    else:
        print("=" * 80)
        print("JavaScript code to load cookies in Cursor browser:")
        print("=" * 80)
        print(js_code)
        print("=" * 80)
        print("\n📋 Instructions:")
        print("1. Navigate to the target domain first (e.g., accounts.google.com)")
        print("2. Use browser_evaluate with the code above")
        print("3. Then navigate to your target page")


def export_from_browser_extension_format(cookies_file: str):
    """
    Handle cookies exported from browser extensions like:
    - EditThisCookie
    - Cookie-Editor
    - etc.
    """
    with open(cookies_file, 'r') as f:
        data = json.load(f)
    
    # Handle different export formats
    if isinstance(data, list):
        cookies = data
    elif isinstance(data, dict) and 'cookies' in data:
        cookies = data['cookies']
    else:
        print(f"❌ Unknown cookie format in {cookies_file}")
        return None
    
    return cookies


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python load_cookies_cursor_browser.py <cookies.json> [output.js]")
        print("\nExample:")
        print("  python load_cookies_cursor_browser.py cookies.json")
        print("  python load_cookies_cursor_browser.py cookies.json load_cookies.js")
        print("\nCookie JSON format:")
        print("  [")
        print('    {"name": "SESSION_ID", "value": "abc123", "domain": ".google.com", "path": "/", "secure": true}')
        print("  ]")
        sys.exit(1)
    
    cookies_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not Path(cookies_file).exists():
        print(f"❌ File not found: {cookies_file}")
        sys.exit(1)
    
    create_cursor_browser_script(cookies_file, output_file)




