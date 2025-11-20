#!/usr/bin/env python3
"""
Reproduce AppMagic API Request

This script reproduces the exact HTTP request to AppMagic API with all headers and cookies.
"""

import requests
from urllib.parse import urlencode


def parse_cookie_string(cookie_string):
    """
    Parse cookie string into a dictionary.
    
    Example: "name1=value1; name2=value2" -> {"name1": "value1", "name2": "value2"}
    """
    cookies = {}
    for item in cookie_string.split('; '):
        if '=' in item:
            key, value = item.split('=', 1)
            cookies[key.strip()] = value.strip()
    return cookies


def make_appmagic_request():
    """
    Reproduce the AppMagic API request with all headers and cookies.
    """
    # Request URL
    url = "https://appmagic.rocks/api/v2/united-applications/data-countries"
    params = {"united_application_id": "13972031"}
    
    # Parse cookies from the cookie string
    cookie_string = (
        "_gcl_aw=GCL.1761287116.CjwKCAjwpOfHBhAxEiwAm1SwEvFLcbyDJqi6n9p1URE4CPZQomUotqrIDsX9qyJexBf7qjBZ54_P5BoC45YQAvD_BwE; "
        "_gcl_gs=2.1.k1$i1761287112$u121790427; "
        "_gcl_au=1.1.2080805028.1761287116; "
        "dashly_device_guid=c39c4632-dd7b-4f57-8262-a907daf5092e; "
        "dashly_realtime_services_transport=wss; "
        "dashly_uid=2041850902721069193; "
        "dashly_auth_token=user.2041850902721069193.7830-e4dd41f4662c0285e8163b41d6e.34ec28a1de1bbf0809c2d3c855f2e475c9420990de6920fb; "
        "dashly_realtime_services_key=; "
        "dashly_hide_all_unread_popups=true; "
        "_csrf=76291870213c0fd7d9af8c09c5f01de4d8f15585515f29e298fb4770f2e963b0a%3A2%3A%7Bi%3A0%3Bs%3A5%3A%22_csrf%22%3Bi%3A1%3Bs%3A32%3A%22C3U1Xhd5TaeezYg8rdrY67XDo8IQlb5V%22%3B%7D; "
        "dashly_session=h2w17v5yx25um06b4cal922nc2q2jawu; "
        "dashly_session_started=1; "
        "dashly_jwt_access=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdHQiOiJhY2Nlc3MiLCJleHAiOjE3NjM1NTQ4MzcsImlhdCI6MTc2MzU1MTIzNywianRpIjoiYTI0YjY0MGI0NDRiNDM1ZGE1NGIyZGI5MTI3ZWUzNjAiLCJhY3QiOiJ3ZWJfdXNlciIsInJvbGVzIjpbInVzZXIuJGFwcF9pZDo3ODMwLiR1c2VyX2lkOjIwOTAyNTQwMjA0NTQxMjIxMTkiLCJ1c2VyLiRhcHBfaWQ6NzgzMC4kdXNlcl9pZDoyMDg0NjU1MTE0ODc3OTI4MjM5IiwidXNlci4kYXBwX2lkOjc4MzAuJHVzZXJfaWQ6MjA4MjMyMjM1NjE2MzgzODc3NyIsInVzZXIuJGFwcF9pZDo3ODMwLiR1c2VyX2lkOjIwNDE4NTA5MDI3MjEwNjkxOTMiLCJ1c2VyLiRhcHBfaWQ6NzgzMC4kdXNlcl9pZDoyMDkwMjY1OTQ0Nzc2NTA3OTAxIiwidXNlci4kYXBwX2lkOjc4MzAuJHVzZXJfaWQ6MjA4MjMyMTY4NTU3ODUxNDc5NiJdLCJhcHBfaWQiOjc4MzAsInVzZXJfaWQiOjIwNDE4NTA5MDI3MjEwNjkxOTN9.AmtLvH-opXqzrMlN9H9hMDffM6aj67uTe_aJG50FAAY"
    )
    
    cookies = parse_cookie_string(cookie_string)
    
    # Filter out dashly cookies
    cookies_without_dashly = {k: v for k, v in cookies.items() if not k.startswith('dashly_')}
    removed_dashly = [k for k in cookies.keys() if k.startswith('dashly_')]
    
    # Filter out _gcl_ cookies (Google Analytics)
    cookies_without_gcl = {k: v for k, v in cookies_without_dashly.items() if not k.startswith('_gcl_')}
    removed_gcl = [k for k in cookies_without_dashly.keys() if k.startswith('_gcl_')]
    
    # Filter out _csrf cookie
    cookies_without_csrf = {k: v for k, v in cookies_without_gcl.items() if k != '_csrf'}
    removed_csrf = ['_csrf'] if '_csrf' in cookies_without_gcl else []
    
    cookies = cookies_without_csrf
    
    # Headers (excluding cookies which are handled separately)
    # Note: Removing baggage and sentry-trace headers (Sentry tracking)
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "authorization": "Bearer u5-AiQHOV9TTBtPTsQ-v2m83ei9fUBcW",
        # "baggage": "sentry-environment=production,sentry-release=e3f9ef4130a8383c76d39a8a68fd583bc6a967ae,sentry-public_key=7eecf182752768632317dc3761a5875e,sentry-trace_id=6f6dd29270e5463db1a4f92b5f73bf6d,sentry-sampled=false,sentry-sample_rand=0.2315564677994858,sentry-sample_rate=0.05",  # Removed
        "content-language": "en",
        "priority": "u=1, i",
        "referer": "https://appmagic.rocks/iphone/chatgpt/6448311069",
        "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        # "sentry-trace": "6f6dd29270e5463db1a4f92b5f73bf6d-84ac6d94d43f24a2-0",  # Removed
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
        "x-client-fingerprint": "c9c77edd7fe2683254eaef6ce101defd"
    }
    
    print("=" * 80)
    print("Making AppMagic API Request (WITHOUT cookies, baggage, and sentry-trace headers)")
    print("=" * 80)
    print(f"URL: {url}")
    print(f"Params: {params}")
    
    if removed_dashly:
        print(f"\n⚠️  Filtered out {len(removed_dashly)} dashly cookies: {', '.join(removed_dashly)}")
    
    if removed_gcl:
        print(f"⚠️  Filtered out {len(removed_gcl)} _gcl_ cookies: {', '.join(removed_gcl)}")
    
    if removed_csrf:
        print(f"⚠️  Filtered out {len(removed_csrf)} _csrf cookie: {', '.join(removed_csrf)}")
    
    print(f"\n⚠️  Removed headers: baggage, sentry-trace (Sentry tracking headers)")
    
    print(f"\nHeaders ({len(headers)}):")
    for key, value in headers.items():
        if key == "authorization":
            print(f"  {key}: {value[:20]}...")
        else:
            print(f"  {key}: {value[:80]}{'...' if len(str(value)) > 80 else ''}")
    
    print(f"\nCookies ({len(cookies)}):")
    for key, value in cookies.items():
        if key == "dashly_jwt_access":
            print(f"  {key}: {value[:50]}...")
        else:
            print(f"  {key}: {value[:80]}{'...' if len(str(value)) > 80 else ''}")
    
    print("\n" + "=" * 80)
    print("Sending request...")
    print("=" * 80)
    
    try:
        # Make the request
        response = requests.get(
            url,
            params=params,
            headers=headers,
            cookies=cookies,
            timeout=30
        )
        
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response Headers:")
        for key, value in response.headers.items():
            print(f"  {key}: {value}")
        
        print(f"\nResponse Body (first 500 chars):")
        try:
            response_json = response.json()
            import json
            print(json.dumps(response_json, indent=2)[:500])
            if len(json.dumps(response_json)) > 500:
                print("\n... (truncated)")
        except:
            print(response.text[:500])
            if len(response.text) > 500:
                print("\n... (truncated)")
        
        # Save full response to file
        output_file = "appmagic_api_response_minimal.json"
        try:
            response_json = response.json()
            with open(output_file, 'w') as f:
                json.dump(response_json, f, indent=2)
            print(f"\n✅ Full response saved to: {output_file}")
        except:
            with open(output_file, 'w') as f:
                f.write(response.text)
            print(f"\n✅ Full response saved to: {output_file}")
        
        return response
        
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
        return None


if __name__ == '__main__':
    make_appmagic_request()

