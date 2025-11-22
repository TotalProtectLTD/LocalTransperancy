#!/usr/bin/env python3
"""
AppMagic Visit with SeleniumBase CDP Mode

This script uses SeleniumBase with Chrome DevTools Protocol (CDP) mode
to visit AppMagic with stealth features and cookies.

Installation:
    pip install seleniumbase

Note: SeleniumBase will automatically download ChromeDriver if needed.
"""

import json
import time
import sys
from pathlib import Path

try:
    from seleniumbase import SB
    SELENIUMBASE_AVAILABLE = True
except ImportError:
    SELENIUMBASE_AVAILABLE = False
    print("❌ SeleniumBase is not installed!")
    print("\nInstall it with:")
    print("  pip install seleniumbase")
    print("\nOr:")
    print("  pip3 install seleniumbase")
    sys.exit(1)


def visit_appmagic_with_seleniumbase(cookies_file: str = "appmagic_cookies_fresh.json", headless: bool = False):
    """
    Visit AppMagic using SeleniumBase with CDP mode.
    
    Args:
        cookies_file: Path to cookies JSON file
        headless: If True, browser will run in headless mode
    """
    # Load cookies from JSON
    cookies_path = Path(cookies_file)
    if not cookies_path.exists():
        print(f"❌ Cookie file not found: {cookies_file}")
        return
    
    with open(cookies_path, 'r') as f:
        cookies_data = json.load(f)
    
    print(f"✅ Loaded {len(cookies_data)} cookies from {cookies_file}")
    
    # SeleniumBase with undetected Chrome mode
    with SB(
        uc=True,  # Undetected Chrome mode (stealth)
        headless=headless,
        incognito=False  # Allow cookies
    ) as sb:
        print("🌐 Opening browser with SeleniumBase CDP mode...")
        
        # Navigate to AppMagic first to establish domain context
        print("🌐 Navigating to AppMagic...")
        sb.open("https://appmagic.rocks")
        time.sleep(2)  # Wait for page to load
        
        # Add cookies
        print("🍪 Adding cookies...")
        for cookie in cookies_data:
            # Convert cookie format for Selenium
            selenium_cookie = {
                'name': cookie['name'],
                'value': cookie['value'],
                'domain': cookie['domain'].lstrip('.') if cookie['domain'].startswith('.') else cookie['domain'],
                'path': cookie.get('path', '/'),
            }
            
            # Add optional fields
            if cookie.get('secure', False):
                selenium_cookie['secure'] = True
            
            if 'expirationDate' in cookie and cookie['expirationDate']:
                selenium_cookie['expiry'] = int(cookie['expirationDate'])
            
            try:
                sb.driver.add_cookie(selenium_cookie)
            except Exception as e:
                print(f"⚠️  Could not add cookie {cookie['name']}: {e}")
        
        print(f"✅ Added cookies to browser")
        
        # Navigate to the referer page
        print("🌐 Navigating to referer page...")
        sb.open("https://appmagic.rocks/top-charts/publishers")
        time.sleep(3)  # Wait for page to fully load
        
        # Make the API request using JavaScript fetch
        print("\n" + "="*80)
        print("Making API request via browser...")
        print("="*80)
        
        url = "https://appmagic.rocks/api/v2/search?name=6747110936&limit=20"
        
        # Execute fetch request in browser context using async/await
        # Embed URL directly in script to avoid argument parsing issues
        response_data = sb.execute_async_script(f"""
            var callback = arguments[arguments.length - 1];
            var url = '{url}';
            fetch(url, {{
                method: 'GET',
                headers: {{
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Origin': 'https://appmagic.rocks',
                    'Referer': 'https://appmagic.rocks/top-charts/publishers',
                    'Sec-Fetch-Dest': 'empty',
                    'Sec-Fetch-Mode': 'cors',
                    'Sec-Fetch-Site': 'same-origin'
                }}
            }})
            .then(response => {{
                return response.text().then(text => {{
                    var headersObj = {{}};
                    response.headers.forEach((value, key) => {{
                        headersObj[key] = value;
                    }});
                    callback({{
                        status: response.status,
                        statusText: response.statusText,
                        headers: headersObj,
                        body: text
                    }});
                }});
            }})
            .catch(error => {{
                callback({{
                    error: error.toString()
                }});
            }});
        """)
        
        # The response should be a dict with status, statusText, headers, body
        if isinstance(response_data, dict):
            print(f"\n✅ Status Code: {response_data.get('status', 'N/A')}")
            print(f"Status Text: {response_data.get('statusText', 'N/A')}")
            
            if 'error' in response_data:
                print(f"\n❌ Error: {response_data['error']}")
            else:
                print(f"\nResponse Headers:")
                headers = response_data.get('headers', {})
                for key, value in list(headers.items())[:10]:  # Show first 10
                    print(f"  {key}: {value}")
                if len(headers) > 10:
                    print(f"  ... and {len(headers) - 10} more")
                
                # Try to parse JSON response
                body = response_data.get('body', '')
                try:
                    response_json = json.loads(body)
                    print(f"\n✅ Response Body (JSON):")
                    print(json.dumps(response_json, indent=2)[:1000])
                    if len(json.dumps(response_json)) > 1000:
                        print("\n... (truncated)")
                    
                    # Save full response
                    output_file = "appmagic_search_response_seleniumbase.json"
                    with open(output_file, 'w') as f:
                        json.dump(response_json, f, indent=2)
                    print(f"\n✅ Full response saved to: {output_file}")
                except json.JSONDecodeError:
                    print(f"\n⚠️  Response is not JSON")
                    print(f"Response Body (first 500 chars):")
                    print(body[:500])
                    if len(body) > 500:
                        print("\n... (truncated)")
                    
                    # Save full response
                    output_file = "appmagic_search_response_seleniumbase.txt"
                    with open(output_file, 'w') as f:
                        f.write(body)
                    print(f"\n✅ Full response saved to: {output_file}")
        else:
            print(f"\n⚠️  Unexpected response format: {type(response_data)}")
            print(f"Response: {response_data}")
        
        if not headless:
            print("\n" + "="*80)
            print("✅ Browser is still open!")
            print("="*80)
            print("\nYou can also test the API request manually in the console.")
            print("Browser will stay open. Press Ctrl+C to close.")
            print("="*80 + "\n")
            
            # Keep browser open only if not headless
            try:
                input("Press Enter to close the browser...")
            except KeyboardInterrupt:
                print("\n👋 Closing browser...")
        else:
            print("\n" + "="*80)
            print("✅ Request completed successfully in headless mode!")
            print("="*80 + "\n")


if __name__ == '__main__':
    import sys
    
    # Default to headless mode (invisible), use --visible to show browser
    headless = '--visible' not in sys.argv
    cookies_file = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else "appmagic_cookies_fresh.json"
    
    if headless:
        print("✅ Running in headless mode (invisible window)")
    else:
        print("✅ Browser will be visible")
    
    visit_appmagic_with_seleniumbase(cookies_file=cookies_file, headless=headless)

