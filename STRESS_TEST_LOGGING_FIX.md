# Stress Test Logging Issue - Analysis & Fix

## Problem Identified 🔍

When running the stress test scraper, only these logs were visible:
```
🕵️  Stealth mode: ENABLED (bot detection evasion active)
Navigating to: https://adstransparency.google.com/advertiser/AR.../creative/CR...
🔧 Using external proxy: http://lt2.4g.iproyal.com:6217
🎭 User Agent: Random Chrome 135.0.0.0
Progress: 3400/817099 URLs (2088 ✓, 0 ✗, 966 ⟳, 346 🚫) [2.0 URL/s]
```

**Missing logs:**
- No "Waiting for dynamic content..." messages
- No completion messages (success or failure)
- No error details from failed scrapes
- Only progress summaries every 10 URLs

## Root Cause Analysis

### Issue #1: Silent Exception Handling

In `stress_test_scraper.py`, the `scrape_single_url()` function was catching ALL exceptions but **not logging them to console**:

```python
# OLD CODE (lines 535-547)
except Exception as e:
    duration = (time.time() - start_time) * 1000
    error_msg = f"{type(e).__name__}: {str(e)}"
    
    return {
        'success': False,
        'error': error_msg,
        # ... (no console logging!)
    }
```

**What was happening:**
1. `page.goto()` times out (30 second timeout)
2. Main scraper prints error and re-raises exception
3. Stress test catches exception silently
4. Error stored in database only
5. **No console output** - user can't see what's failing

### Issue #2: No Real-Time Feedback

The worker function only logged progress every 10 URLs, so individual scrape results (success or failure) were invisible in real-time.

## The Fix ✅

### Fix #1: Added Exception Logging

```python
# NEW CODE (lines 535-552)
except Exception as e:
    duration = (time.time() - start_time) * 1000
    error_msg = f"{type(e).__name__}: {str(e)}"
    
    # Log the error to console for visibility in concurrent environments
    print(f"  ❌ EXCEPTION during scrape: {error_msg[:150]}")
    import sys
    sys.stdout.flush()
    
    return {
        'success': False,
        'error': error_msg,
        # ...
    }
```

**Now you'll see:**
```
  ❌ EXCEPTION during scrape: TimeoutError: Timeout 30000ms exceeded
```

### Fix #2: Added Real-Time Result Logging

```python
# NEW CODE (lines 605-613)
# Scrape URL
result = await scrape_single_url(creative, proxy_config)

# Log immediate result (for debugging concurrent issues)
if result['success']:
    videos = result.get('video_count', 0)
    print(f"  ✅ Scraped: {creative['creative_id'][:15]}... ({videos} videos)")
else:
    error_type = result.get('error', 'Unknown')[:80]
    print(f"  ⚠️  Failed: {creative['creative_id'][:15]}... - {error_type}")
import sys
sys.stdout.flush()
```

**Now you'll see:**
```
  ✅ Scraped: CR001234567890... (2 videos)
  ⚠️  Failed: CR009876543210... - TimeoutError: Timeout 30000ms exceeded
```

## What You'll See Now

### Before (Silent Failures):
```
🕵️  Stealth mode: ENABLED (bot detection evasion active)
Navigating to: https://adstransparency.google.com/advertiser/AR.../creative/CR...
🔧 Using external proxy: http://lt2.4g.iproyal.com:6217
🎭 User Agent: Random Chrome 135.0.0.0
  Progress: 3400/817099 URLs (2088 ✓, 0 ✗, 966 ⟳, 346 🚫) [2.0 URL/s]
```

### After (Visible Errors):
```
🕵️  Stealth mode: ENABLED (bot detection evasion active)
Navigating to: https://adstransparency.google.com/advertiser/AR.../creative/CR...
🔧 Using external proxy: http://lt2.4g.iproyal.com:6217
🎭 User Agent: Random Chrome 135.0.0.0
  ⚠️  page.goto() error: TimeoutError: Timeout 30000ms exceeded
  ❌ EXCEPTION during scrape: TimeoutError: Timeout 30000ms exceeded
  ⚠️  Failed: CR001234567890... - TimeoutError: Timeout 30000ms exceeded
  ✅ Scraped: CR009876543210... (2 videos)
  ⚠️  Failed: CR00555555555... - Creative not found in API
  Progress: 3410/817099 URLs (2089 ✓, 2 ✗, 966 ⟳, 346 🚫) [2.0 URL/s]
```

## Common Errors You Might See

Now that logging is fixed, here are errors you might encounter:

### 1. TimeoutError (page.goto)
```
  ⚠️  page.goto() error: TimeoutError: Timeout 30000ms exceeded
  ❌ EXCEPTION during scrape: TimeoutError: Timeout 30000ms exceeded
```
**Cause:** Page is taking longer than 30 seconds to load  
**Status:** Marked as 'pending' for retry (temporary error)

### 2. Proxy Connection Failed
```
  ⚠️  page.goto() error: Error: net::ERR_PROXY_CONNECTION_FAILED
  ❌ EXCEPTION during scrape: Error: net::ERR_PROXY_CONNECTION_FAILED
```
**Cause:** Proxy is unreachable or down  
**Status:** Marked as 'pending' for retry (temporary error)

### 3. Creative Not Found
```
  ⚠️  Failed: CR001234567890... - Creative not found in API
```
**Cause:** Creative doesn't exist or was deleted  
**Status:** Marked as 'bad_ad' (permanent error, no retry)

### 4. Incomplete Content
```
  ⚠️  Failed: CR001234567890... - INCOMPLETE: Expected 3 fletch-render content.js but only got 1
```
**Cause:** Not all dynamic content loaded  
**Status:** Marked as 'pending' for retry (temporary error)

## Why This Happened

The original code was designed for production use where:
- Errors are logged to database for later analysis
- Console output is minimized to reduce noise
- Only progress summaries are shown

But for debugging and monitoring, you need:
- **Real-time visibility** of what's happening
- **Immediate error feedback** to diagnose issues
- **Per-URL logging** to track individual failures

## Testing the Fix

Run the stress test again:
```bash
python3 stress_test_scraper.py --max-concurrent 10
```

You should now see:
1. ✅ Each successful scrape with video count
2. ⚠️ Each failed scrape with error message
3. ❌ Exception details when crashes occur
4. 📊 Progress summaries every 10 URLs

## Database Status Mapping

The errors are still saved to the database with these status values:

| Status | Description | Console Indicator |
|--------|-------------|-------------------|
| `completed` | Successfully scraped | ✅ |
| `pending` | Retry needed (network/timeout) | ⟳ |
| `bad_ad` | Creative not found (permanent) | 🚫 |
| `failed` | Other permanent errors | ✗ |

## Next Steps

1. **Run the stress test** again to see the new logging
2. **Check what errors appear** most frequently
3. **Analyze timeouts** - if many page.goto() timeouts occur:
   - Proxy might be slow
   - Increase PAGE_LOAD_TIMEOUT (currently 30s)
   - Reduce concurrency (--max-concurrent)
4. **Monitor proxy health** - if ERR_PROXY_CONNECTION_FAILED:
   - Check proxy is running
   - Test proxy manually
   - Consider IP rotation (--enable-rotation)

## Files Modified

- `stress_test_scraper.py`
  - Added exception logging in `scrape_single_url()` (line 540)
  - Added per-URL result logging in `worker()` (line 605-613)
  - Added `sys.stdout.flush()` calls for immediate output

## Related Files

- `google_ads_transparency_scraper.py` - Already had error handling with try-except around page.goto()
- `query_errors.sql` - Use this to query database for error patterns
- `ERROR_LOGGING_GUIDE.md` - Comprehensive error classification guide

