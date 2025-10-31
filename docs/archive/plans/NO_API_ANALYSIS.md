# Analysis: "No API responses captured" vs "Creative not found in API"

## Overview

This document explains the two main error types in the Google Ads Transparency scraper, their causes, waiting behavior, and the diagnostic improvements implemented.

---

## Error Types

### 1. ⚠️ "No API responses captured" (WARNING)

**Condition:** `len(tracker.api_responses) == 0`

**What it means:**
- No XHR/fetch requests matching the API patterns were intercepted
- The page loaded but didn't make calls to:
  - `GetCreativeById`
  - `SearchCreatives`
  - `GetAdvertiserById`

**Possible causes:**
1. **JavaScript didn't execute** - Page loaded but JS was blocked/failed
2. **Bot detection** - Google detected automation and blocked API calls
3. **Network/firewall blocking** - API endpoints were blocked
4. **API endpoints changed** - Google changed their API URL patterns
5. **Region restrictions** - Content not available in the region
6. **Page structure changed** - Different page type that doesn't use these APIs

**Wait time:** **60 seconds** (full timeout)

**Why it waits so long:**
- Line 1115: `if current_api_count > last_api_count:` is always FALSE (0 > 0)
- No API processing happens
- No early exit conditions are met
- Loop runs for full 60 seconds

**NEW: Early exit optimization:**
- After **10 seconds** with no XHR/fetch requests at all, exits early
- Saves 50 seconds when JavaScript clearly isn't executing

---

### 2. ❌ "Creative not found in API" (ERROR)

**Condition:** `extract_real_creative_id_from_api()` returns `None`

**What it means:**
- API responses were captured successfully
- BUT the creative data is missing or invalid:
  - `GetCreativeById` returned empty `{}`
  - `GetCreativeById` doesn't contain the target creative
  - `SearchCreatives` doesn't list the target creative
  - Both APIs have data but not for this specific creative

**Possible causes:**
1. **Creative deleted** - Ad was removed from Google's system
2. **Creative expired** - Ad campaign ended
3. **Creative restricted** - Not available in certain regions
4. **Data integrity issue** - Google's database has incomplete data
5. **Wrong creative ID** - The ID in the URL doesn't exist

**Wait time:** **60 seconds** (full timeout)

**Why it waits so long:**
- Line 1115: `if current_api_count > last_api_count:` triggers ONCE (~5 seconds in)
- API processing executes one time
- `extract_expected_fletch_renders()` returns empty set (no fletch-render IDs in empty `{}`)
- After that, `current_api_count == last_api_count` (4 == 4), so block never executes again
- No early exit conditions are met
- Loop continues hoping for more data for remaining 55 seconds

---

## Wait Loop Logic

### The Smart Wait Loop (Lines 1106-1205)

```python
max_wait = 60  # seconds
check_interval = 0.5  # seconds
elapsed = 0

while elapsed < max_wait:
    # NEW: Early exit if no XHR/fetch after 10s
    if elapsed >= 10 and len(all_xhr_fetch_requests) == 0:
        print("⚠️ No XHR/fetch requests detected - exiting early")
        break
    
    # Check if new API responses arrived
    current_api_count = len(tracker.api_responses)
    if current_api_count > last_api_count:
        # Process API responses
        # Check for static content
        # Extract fletch-render IDs
        # Update expectations
        last_api_count = current_api_count
    
    # Check if all expected content.js arrived
    if expected_fletch_renders:
        # Check for matching fletch-render IDs
        if all_found:
            break  # Early exit!
    
    await page.wait_for_timeout(500)
    elapsed += 0.5
```

### Early Exit Conditions

| Condition | When | Time Saved |
|-----------|------|------------|
| **Static content detected** | API shows simgad/sadbundle URLs | ~55s (exits at ~5s) |
| **All fletch-renders received** | Got all expected content.js | ~50s (exits at ~10s) |
| **No XHR/fetch requests** (NEW) | No JS activity after 10s | ~50s (exits at 10s) |

### No Early Exit (Full 60s Wait)

| Scenario | Why No Exit |
|----------|-------------|
| **"No API responses captured"** | No API count changes, no expectations set |
| **"Creative not found in API"** | Empty API data, no fletch-renders to wait for |

---

## Diagnostic Improvements

### 1. Track ALL XHR/Fetch Requests

**Added:** `all_xhr_fetch_requests` list (Line 1038)

Tracks every XHR/fetch request, not just API calls. This helps diagnose:
- Is JavaScript executing at all?
- Are requests being made but not matching our patterns?
- What other endpoints is the page calling?

### 2. Diagnostic Output for "No API"

**Added:** Lines 1507-1516

When no API responses are captured, shows:
- How many XHR/fetch requests were detected
- First 5 request URLs and their status codes
- If zero XHR/fetch: "JavaScript may not have executed"

**Example output:**
```
⚠️ No API responses captured
   ℹ️ However, 12 XHR/fetch requests were detected:
      1. [200] https://adstransparency.google.com/anji/_/rpc/SomeOtherService...
      2. [200] https://www.google.com/gen_204?...
      3. [403] https://adstransparency.google.com/blocked...
      ... and 9 more
```

Or:
```
⚠️ No API responses captured
   ℹ️ No XHR/fetch requests detected at all (JavaScript may not have executed)
```

### 3. Early Exit for No JavaScript

**Added:** Lines 1107-1111

If no XHR/fetch requests after 10 seconds:
- Prints warning about JavaScript not executing
- Exits wait loop early
- Saves 50 seconds

---

## Comparison Table

| Aspect | "No API responses captured" | "Creative not found in API" |
|--------|----------------------------|----------------------------|
| **Severity** | ⚠️ WARNING | ❌ ERROR |
| **API captured?** | ❌ No (0 responses) | ✅ Yes (typically 4 responses) |
| **GetCreativeById** | Not received | Received but empty `{}` |
| **SearchCreatives** | Not received | May be received but creative not in list |
| **Line 1115 triggered?** | ❌ Never | ✅ Once (~5s) |
| **Static check runs?** | ❌ No | ✅ Yes (returns None) |
| **Fletch extraction runs?** | ❌ No | ✅ Yes (returns empty set) |
| **Wait time (old)** | ⏱️ 60 seconds | ⏱️ 60 seconds |
| **Wait time (NEW)** | ⏱️ **10 seconds** (if no XHR) | ⏱️ 60 seconds |
| **Early exit possible?** | ✅ Yes (NEW) | ❌ No |
| **Retry in stress test?** | N/A (warning only) | ❌ No (permanent failure) |
| **Classification** | Warning | `bad_ad` |

---

## Testing Scenarios

### Scenario 1: Working Creative
```
✅ API responses captured (4)
✅ GetCreativeById has valid data
✅ Fletch-render IDs extracted: 2
✅ All content.js received
⏱️ Wait time: ~7 seconds
✅ Result: SUCCESS
```

### Scenario 2: Static/Cached Creative
```
✅ API responses captured (3)
✅ GetCreativeById has simgad URL
✅ Static content detected
⏱️ Wait time: ~5 seconds
✅ Result: SUCCESS (static)
```

### Scenario 3: Creative Not Found in API
```
✅ API responses captured (4)
❌ GetCreativeById: {}
❌ SearchCreatives: creative not in list
❌ No fletch-render IDs
⏱️ Wait time: 60 seconds
❌ Result: FAILED - "Creative not found in API"
```

### Scenario 4: No API Responses (No JavaScript)
```
❌ API responses captured (0)
❌ XHR/fetch requests: 0
⚠️ JavaScript may not be executing
⏱️ Wait time: 10 seconds (NEW early exit)
⚠️ Result: WARNING - "No API responses captured"
```

### Scenario 5: No API Responses (JavaScript Running)
```
❌ API responses captured (0)
✅ XHR/fetch requests: 15 (other endpoints)
⚠️ API patterns not matching
⏱️ Wait time: 60 seconds
⚠️ Result: WARNING - "No API responses captured"
```

---

## Recommendations

### For "No API responses captured"

1. **Check the diagnostic output** - See what XHR/fetch requests were made
2. **If zero XHR/fetch** - JavaScript isn't executing (bot detection, blocking)
3. **If many XHR/fetch** - API endpoints may have changed
4. **Action:** Update API patterns in line 1053 if Google changed endpoints

### For "Creative not found in API"

1. **This is a permanent failure** - Creative doesn't exist in Google's system
2. **Don't retry** - Stress test correctly marks as `bad_ad`
3. **Action:** Skip this creative, it's deleted/expired/restricted

---

## Code Locations

| Feature | File | Lines |
|---------|------|-------|
| API response capture | google_ads_transparency_scraper.py | 1051-1072 |
| XHR/fetch tracking | google_ads_transparency_scraper.py | 1044-1049 |
| Early exit (no JS) | google_ads_transparency_scraper.py | 1107-1111 |
| Smart wait loop | google_ads_transparency_scraper.py | 1106-1205 |
| "No API" diagnostic | google_ads_transparency_scraper.py | 1503-1518 |
| "Creative not found" error | google_ads_transparency_scraper.py | 1496-1498 |
| Error classification | stress_test_scraper.py | 180-220 |

---

## Future Improvements

### Potential Optimizations

1. **Early exit for "Creative not found"**
   - If GetCreativeById is empty `{}`, could exit after 10 seconds
   - Currently waits full 60s hoping for more data
   - Would save 50 seconds per bad creative

2. **Progressive timeout**
   - Start with 10s wait
   - If no API, exit
   - If empty API, wait 10s more
   - If still nothing, exit
   - Max 20s instead of 60s

3. **API pattern auto-detection**
   - Log all XHR/fetch URLs when no API captured
   - Analyze patterns to suggest new API endpoints
   - Auto-update patterns if Google changes URLs

4. **Region-specific handling**
   - Detect region restrictions from API responses
   - Mark as "region_restricted" instead of "bad_ad"
   - Allow retry with different region parameter

---

## Summary

Both error types previously wasted 60 seconds waiting for content that would never arrive. With the new improvements:

- **"No API responses captured"**: Now exits after **10 seconds** if no JavaScript activity
- **"Creative not found in API"**: Still waits 60 seconds (could be optimized further)

The diagnostic output helps identify WHY the API wasn't captured, enabling better debugging and potential fixes.

