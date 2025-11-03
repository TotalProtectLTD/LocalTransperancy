# 🚀 Quick Start - Capture SearchCreatives API

## Run Test (1 Command)

```bash
python3 parser_of_advertiser.py --test-advertiser
```

Or use the shell script:
```bash
./test_advertiser_capture.sh
```

## What It Does

1. **Opens browser** with production configuration
2. **Navigates to** advertiser page: `https://adstransparency.google.com/advertiser/AR00270446617386024961?region=anywhere&platform=YOUTUBE&format=VIDEO`
3. **Captures SearchCreatives API** request/response
4. **Saves everything** to `./debug/` folder
5. **Shows statistics** (traffic, cache, cookies)

## Expected Output

```
================================================================================
ADVERTISER PAGE TEST - SearchCreatives API Capture
================================================================================
Target URL: https://adstransparency.google.com/advertiser/...
Debug folder: debug
================================================================================

✓ Browser started (SAME CONFIG AS PRODUCTION)
  User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)...
  Traffic Tracker: Initialized
  Route Handler: Cache-aware (blocks ads/images/fonts)
  Event Listeners: Registered (request/response tracking)
  Stealth: Enabled

🌐 Navigating to advertiser page...
   https://adstransparency.google.com/advertiser/...

✓ Page loaded
  Status: 200
  URL: https://adstransparency.google.com/advertiser/...

🔍 Captured SearchCreatives API call!
   URL: https://adstransparency.google.com/_/...SearchCreatives...
   ✓ Saved request to: debug/searchcreatives_request_0.json

📥 Captured SearchCreatives API response!
   Status: 200
   URL: https://adstransparency.google.com/_/...SearchCreatives...
   ✓ Saved response metadata to: debug/searchcreatives_response_0_meta.json
   ✓ Saved response body to: debug/searchcreatives_response_0_body.json
   ✓ Response is valid JSON (12345 chars)

⏳ Waiting 10 seconds for API calls to complete...

🍪 Captured 15 cookies
   ✓ Saved to: debug/cookies.json
     - NID: abc123...
     - 1P_JAR: 2025-11-02-10
     - CONSENT: YES+...
     - ...

📊 Saving traffic statistics...
   ✓ Saved to: debug/traffic_summary.json
   Total requests: 45
   Total responses: 42

💾 Cache Statistics:
   ✓ Saved to: debug/cache_statistics.json
   Cache hits: 12
   Cache misses: 8
   Hit rate: 60.0%
   Bytes saved: 1523.4 KB

📄 Captured 3 content.js responses
   ✓ Saved to: debug/content_js_responses.json

================================================================================
CAPTURE COMPLETE
================================================================================
SearchCreatives calls captured: 1
Cookies captured: 15
Debug folder: /Users/rostoni/Downloads/LocalTransperancy/debug

Files saved:
  - searchcreatives_request_*.json (request headers)
  - searchcreatives_response_*_meta.json (response headers)
  - searchcreatives_response_*_body.json (response body)
  - cookies.json (all cookies)
  - traffic_summary.json (traffic statistics)
  - cache_statistics.json (cache performance)
  - content_js_responses.json (content.js captures)
================================================================================
```

## Files to Inspect

### 1. SearchCreatives Request
```bash
cat debug/searchcreatives_request_0.json | jq .
```

Contains:
- Full URL with query parameters
- All request headers (cookies, user-agent, referer, etc.)
- POST data (if applicable)
- Timestamp

### 2. SearchCreatives Response Headers
```bash
cat debug/searchcreatives_response_0_meta.json | jq .
```

Contains:
- HTTP status code
- All response headers
- Content-Type, Content-Encoding, etc.
- Timestamp

### 3. SearchCreatives Response Body
```bash
cat debug/searchcreatives_response_0_body.json | jq .
```

Contains:
- Full JSON response with creative data
- Advertiser information
- Creative IDs, formats, regions, etc.

### 4. Cookies
```bash
cat debug/cookies.json | jq .
```

Contains all cookies:
- NID (Google Network ID)
- 1P_JAR (First-party JAR)
- CONSENT
- SIDCC, SSID, etc.

### 5. Traffic Summary
```bash
cat debug/traffic_summary.json | jq .
```

Contains:
- Total requests/responses
- Requests by type (document, script, xhr, etc.)
- API responses count
- Blocked requests count

### 6. Cache Statistics
```bash
cat debug/cache_statistics.json | jq .
```

Contains:
- Cache hits/misses
- Hit rate percentage
- Bytes saved
- Total requests

## Production Parity ✅

The test uses **EXACT same browser configuration**:

| Component | Production | Test | Status |
|-----------|-----------|------|--------|
| Browser setup | `_setup_browser_context()` | ✅ Same | ✅ |
| Traffic tracker | `TrafficTracker()` | ✅ Same | ✅ |
| Route handler | `_create_route_handler()` | ✅ Same | ✅ |
| Cache handler | `create_cache_aware_route_handler()` | ✅ Same | ✅ |
| Response handler | `_create_response_handler()` | ✅ Same | ✅ |
| Event listeners | `page.on('request/response')` | ✅ Same | ✅ |
| Stealth mode | `playwright_stealth` | ✅ Same | ✅ |
| Resource blocking | Ads/images/fonts | ✅ Same | ✅ |
| Cache system | Two-level L1+L2 | ✅ Same | ✅ |

## What Gets Blocked

The cache-aware handler blocks (same as production):
- ❌ Images
- ❌ Videos
- ❌ Fonts
- ❌ Ads
- ❌ Tracking scripts

Only essential resources load:
- ✅ HTML
- ✅ JavaScript
- ✅ API calls (SearchCreatives!)
- ✅ Content.js

## Troubleshooting

### No SearchCreatives captured?
- Page might use different API endpoint
- Check console for errors
- Increase wait time (edit script, change `await asyncio.sleep(10)` to higher)

### Browser won't start?
```bash
pip install playwright
playwright install chromium
```

### Import errors?
```bash
pip install -r requirements.txt
```

### Want to test different advertiser?
Edit `parser_of_advertiser.py`:
```python
FIXED_TEST_URL = "https://adstransparency.google.com/advertiser/YOUR_ADVERTISER_ID?region=anywhere"
```

## Next Steps

After capturing:
1. ✅ Inspect request headers (especially cookies)
2. ✅ Analyze response structure
3. ✅ Check if pagination is needed
4. ✅ Verify creative data format
5. ✅ Test with different advertisers

## Need Help?

Check these files:
- `VERIFICATION_COMPLETE.md` - Full verification details
- `TEST_MODE_README.md` - Comprehensive documentation
- `parser_of_advertiser.py` - Source code with comments

