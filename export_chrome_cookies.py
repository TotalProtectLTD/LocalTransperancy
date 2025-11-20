#!/usr/bin/env python3
"""
Export Chrome Cookies and Convert for Cursor Browser

This script helps you export cookies from Chrome and convert them
to JavaScript code that can be loaded into Cursor's MCP browser.

Method 1: Using Chrome's cookie database (macOS)
Method 2: Using browser extension export
Method 3: Manual export via Chrome DevTools
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
import os
import platform


def get_chrome_cookie_db_path():
    """Get Chrome cookie database path based on OS."""
    system = platform.system()
    
    if system == "Darwin":  # macOS
        # Chrome stores cookies in ~/Library/Application Support/Google/Chrome/Default/Cookies
        home = os.path.expanduser("~")
        cookie_db = os.path.join(
            home,
            "Library/Application Support/Google/Chrome/Default/Cookies"
        )
        return cookie_db
    elif system == "Linux":
        home = os.path.expanduser("~")
        cookie_db = os.path.join(home, ".config/google-chrome/Default/Cookies")
        return cookie_db
    elif system == "Windows":
        # Windows path
        appdata = os.getenv("APPDATA")
        cookie_db = os.path.join(
            appdata,
            "Google/Chrome/User Data/Default/Cookies"
        )
        return cookie_db
    else:
        return None


def export_chrome_cookies_sqlite(domain_filter=None, output_file="cookies.json"):
    """
    Export cookies from Chrome's SQLite database.
    
    Note: Chrome locks the database, so you need to:
    1. Close Chrome completely, OR
    2. Copy the Cookies file to a temp location first
    """
    cookie_db = get_chrome_cookie_db_path()
    
    if not cookie_db or not os.path.exists(cookie_db):
        print(f"❌ Chrome cookie database not found at: {cookie_db}")
        print("\n💡 Try:")
        print("   1. Close Chrome completely")
        print("   2. Or use Method 2 (browser extension)")
        return None
    
    # Copy to temp location (Chrome locks the original)
    import tempfile
    import shutil
    
    temp_db = os.path.join(tempfile.gettempdir(), "chrome_cookies_temp.db")
    try:
        shutil.copy2(cookie_db, temp_db)
        print(f"✅ Copied cookie database to temp location")
    except Exception as e:
        print(f"❌ Failed to copy cookie database: {e}")
        print("   Make sure Chrome is closed!")
        return None
    
    try:
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Check what columns exist in the cookies table
        cursor.execute("PRAGMA table_info(cookies)")
        columns = [col[1] for col in cursor.fetchall()]
        has_same_site = 'same_site' in columns
        has_samesite = 'samesite' in columns
        
        # Build query based on available columns
        if has_same_site:
            select_cols = "name, value, host_key, path, expires_utc, is_secure, is_httponly, same_site"
        elif has_samesite:
            select_cols = "name, value, host_key, path, expires_utc, is_secure, is_httponly, samesite"
        else:
            select_cols = "name, value, host_key, path, expires_utc, is_secure, is_httponly, 0 as same_site"
        
        # Query cookies
        if domain_filter:
            query = f"""
                SELECT {select_cols}
                FROM cookies
                WHERE host_key LIKE ?
                ORDER BY host_key, name
            """
            cursor.execute(query, (f"%{domain_filter}%",))
        else:
            query = f"""
                SELECT {select_cols}
                FROM cookies
                ORDER BY host_key, name
            """
            cursor.execute(query)
        
        cookies = []
        for row in cursor.fetchall():
            if has_same_site or has_samesite:
                name, value, host_key, path, expires_utc, is_secure, is_httponly, same_site = row
            else:
                name, value, host_key, path, expires_utc, is_secure, is_httponly = row[:7]
                same_site = 0
            
            # Convert expires_utc (Chrome uses microseconds since 1601-01-01)
            expires = None
            if expires_utc and expires_utc > 0:
                # Chrome epoch: 1601-01-01 00:00:00 UTC
                # Unix epoch: 1970-01-01 00:00:00 UTC
                # Difference: 11644473600 seconds
                # Chrome stores in microseconds, so divide by 1,000,000
                unix_timestamp = (expires_utc / 1000000) - 11644473600
                expires = int(unix_timestamp) if unix_timestamp > 0 else None
            
            # Convert same_site (0=None, 1=Lax, 2=Strict)
            same_site_str = "None"
            if same_site == 1:
                same_site_str = "Lax"
            elif same_site == 2:
                same_site_str = "Strict"
            
            cookie = {
                "name": name,
                "value": value,
                "domain": host_key,
                "path": path or "/",
                "secure": bool(is_secure),
                "httpOnly": bool(is_httponly),
                "sameSite": same_site_str,
            }
            
            if expires:
                cookie["expires"] = expires
            
            cookies.append(cookie)
        
        conn.close()
        
        # Save to JSON
        with open(output_file, 'w') as f:
            json.dump(cookies, f, indent=2)
        
        print(f"✅ Exported {len(cookies)} cookie(s) to {output_file}")
        if domain_filter:
            print(f"   Filtered by domain: {domain_filter}")
        
        return cookies
        
    except Exception as e:
        print(f"❌ Error reading cookie database: {e}")
        return None
    finally:
        # Clean up temp file
        try:
            os.remove(temp_db)
        except:
            pass


def convert_cookies_to_js(cookies_file, output_js="load_cookies.js"):
    """
    Convert cookies JSON to JavaScript code for Cursor browser.
    """
    with open(cookies_file, 'r') as f:
        cookies = json.load(f)
    
    js_code = """// Load cookies into Cursor browser
// Use this with browser_evaluate tool in Cursor

(function() {
"""
    
    for cookie in cookies:
        name = cookie.get('name', '')
        value = cookie.get('value', '')
        domain = cookie.get('domain', '')
        path = cookie.get('path', '/')
        secure = cookie.get('secure', False)
        sameSite = cookie.get('sameSite', 'Lax')
        
        # Escape quotes in cookie value
        value_escaped = value.replace('"', '\\"').replace("'", "\\'")
        
        # Build cookie string
        cookie_str = f"{name}={value_escaped}"
        
        if domain:
            # Remove leading dot if present for document.cookie
            domain_clean = domain.lstrip('.')
            cookie_str += f"; domain={domain_clean}"
        if path:
            cookie_str += f"; path={path}"
        if secure:
            cookie_str += "; secure"
        if sameSite and sameSite != "None":
            cookie_str += f"; SameSite={sameSite}"
        
        js_code += f'  document.cookie = "{cookie_str}";\n'
    
    cookie_count = len(cookies)
    js_code += f"""
  return `Successfully set {cookie_count} cookie(s)`;
}})();
"""
    
    with open(output_js, 'w') as f:
        f.write(js_code)
    
    print(f"✅ JavaScript code saved to: {output_js}")
    print(f"\n📋 Usage in Cursor:")
    print(f"   1. Navigate to the domain first (e.g., accounts.google.com)")
    print(f"   2. Use browser_evaluate with the code from {output_js}")
    print(f"   3. Then navigate to your target page")
    
    return output_js


def main():
    print("=" * 80)
    print("Chrome Cookie Exporter for Cursor Browser")
    print("=" * 80)
    print()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python export_chrome_cookies.py <domain> [output.json]")
        print()
        print("Examples:")
        print("  python export_chrome_cookies.py google.com")
        print("  python export_chrome_cookies.py .google.com cookies_google.json")
        print()
        print("Note: Chrome must be CLOSED for this to work!")
        print()
        sys.exit(1)
    
    domain = sys.argv[1]
    output_json = sys.argv[2] if len(sys.argv) > 2 else "cookies.json"
    output_js = output_json.replace('.json', '.js')
    
    print(f"🔍 Exporting cookies for domain: {domain}")
    print(f"📁 Output: {output_json}")
    print()
    
    cookies = export_chrome_cookies_sqlite(domain_filter=domain, output_file=output_json)
    
    if cookies:
        print()
        convert_cookies_to_js(output_json, output_js)
        print()
        print("=" * 80)
        print("✅ Done! You can now use the JavaScript code in Cursor browser.")
        print("=" * 80)
    else:
        print()
        print("=" * 80)
        print("Alternative Methods:")
        print("=" * 80)
        print()
        print("Method 2: Use Chrome Extension")
        print("  1. Install 'Cookie-Editor' or 'EditThisCookie' extension")
        print("  2. Click extension icon → Export → JSON")
        print("  3. Save to cookies.json")
        print("  4. Run: python load_cookies_cursor_browser.py cookies.json")
        print()
        print("Method 3: Manual Export")
        print("  1. Open Chrome DevTools (F12)")
        print("  2. Go to Application tab → Cookies")
        print("  3. Manually copy cookie values")
        print()


if __name__ == '__main__':
    main()

