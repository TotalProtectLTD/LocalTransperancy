# Error Handling Analysis - Socket Hang Up Failures

## Your Question

When content.js fetches fail with "socket hang up", what happens to the result and how is it saved to the database?

## Current Flow (for API-only method)

### Step 1: Fetch Fails
```
📤 Fetching 2 content.js file(s) in parallel...
✅ Fetched 2 file(s) in 13.33s (parallel)
⚠️  Failed to fetch file 1: ... - socket hang up
⚠️  Failed to fetch file 2: ... - socket hang up
📊 Total downloaded: 0 bytes (0.0 KB) from 0/2 files
```

**Result**: `content_js_responses = []` (empty list)

### Step 2: Validation Catches It

**Code**: `google_ads_validation.py`, lines 122-127

```python
if expected_fletch_renders:  # API said we should have 2 files
    if len(found_fletch_renders) == 0:  # But we got 0
        execution_success = False
        error_msg = f"FAILED: Expected {len(expected_fletch_renders)} content.js but none received"
        execution_errors.append(error_msg)
```

**Result**: 
- `success = False`
- `errors = ["FAILED: Expected 2 content.js but none received"]`
- `videos = []`
- `video_count = 0`

### Step 3: Database Update

**Code**: `stress_test_scraper_optimized.py`, `update_result()` function

```python
if result.get('success'):
    # NOT executed (success=False)
else:
    error_msg = result.get('error', 'Unknown error')
    # error_msg = "FAILED: Expected 2 content.js but none received"
    
    should_retry, error_type, error_category = classify_error(error_msg)
    # Returns: (False, 'Failed', 'failed')  ← ❌ PROBLEM!
    
    # Marks as PERMANENT failure
    UPDATE creatives_fresh SET status = 'failed', ...
```

## The Problem 🐛

### Issue 1: "socket hang up" Not in Retry List

**Current retry list** (`stress_test_scraper_optimized.py`, line 277):
```python
network_errors = [
    'ERR_PROXY_CONNECTION_FAILED',
    'ERR_EMPTY_RESPONSE',
    'ERR_CONNECTION_RESET',
    'ERR_TIMED_OUT',
    'ERR_CONNECTION_CLOSED',
    'ERR_CONNECTION_REFUSED',
    'ERR_TUNNEL_CONNECTION_FAILED',
    'TimeoutError',
    'Timeout',
    'BrokenPipeError'
    # ❌ Missing: 'socket hang up'
]
```

**Result**: "socket hang up" is treated as a **PERMANENT failure**, not a retryable network error.

### Issue 2: Generic Validation Error Hides Root Cause

When content.js fetches fail, validation returns:
```
error_msg = "FAILED: Expected 2 content.js but none received"
```

This doesn't mention "socket hang up", so `classify_error()` doesn't recognize it as a network error.

**The actual "socket hang up" errors are only logged, not captured in the result.**

## What Happens Now

### For Your Example (CR1778848170070...)

1. ✅ API call succeeds (gets 2 content.js URLs)
2. ❌ Both content.js fetches fail with "socket hang up"
3. ❌ Validation fails: "Expected 2 content.js but none received"
4. ❌ Classified as PERMANENT failure (should_retry=False)
5. ❌ Database updated: `status='failed'`

**Problem**: This creative is marked as **permanently failed** when it should be **retried** (network error).

## The Fix 🔧

### Fix 1: Add Network Errors to Retry List

```python
# stress_test_scraper_optimized.py, line 277
network_errors = [
    'ERR_PROXY_CONNECTION_FAILED',
    'ERR_EMPTY_RESPONSE',
    'ERR_CONNECTION_RESET',
    'ERR_TIMED_OUT',
    'ERR_CONNECTION_CLOSED',
    'ERR_CONNECTION_REFUSED',
    'ERR_TUNNEL_CONNECTION_FAILED',
    'TimeoutError',
    'Timeout',
    'BrokenPipeError',
    'socket hang up',           # ← ADD THIS
    'ECONNRESET',               # ← ADD THIS
    'ETIMEDOUT',                # ← ADD THIS
    'ECONNREFUSED',             # ← ADD THIS
    'content.js but none received'  # ← ADD THIS (catches validation error)
]
```

### Fix 2: Capture Detailed Fetch Errors in Result

**Current**: Fetch errors are logged but not captured in result

**Better**: Store fetch errors in result for proper classification

```python
# In google_ads_transparency_scraper_optimized.py
# After fetch_results = await asyncio.gather(*fetch_tasks)

failed_fetches = []
for result in fetch_results:
    if not result['success']:
        failed_fetches.append({
            'url': result['url'],
            'error': result['error']
        })

# If ALL fetches failed, create detailed error message
if failed_fetches and len(failed_fetches) == len(fetch_results):
    # All content.js fetches failed - this is a network issue
    sample_error = failed_fetches[0]['error']
    error_msg = f"All content.js fetches failed: {sample_error}"
    
    return {
        'success': False,
        'error': error_msg,  # ← Will be properly classified
        'videos': [],
        ...
    }
```

## Current Workaround

Until the fix is deployed, these creatives will be:
- ❌ Marked as `status='failed'` (permanent)
- ⚠️ Need manual intervention to reset to `status='pending'` for retry

**Manual retry query**:
```sql
-- Reset failed socket hang up errors to pending
UPDATE creatives_fresh
SET status = 'pending',
    error_message = NULL
WHERE status = 'failed'
  AND error_message LIKE '%content.js but none received%'
  AND scraped_at > NOW() - INTERVAL '1 day';
```

## Impact Assessment

### Current Behavior

**Socket hang up errors**:
- Treated as: ❌ Permanent failure
- Database status: `failed`
- Retried: ❌ No
- Impact: Creative marked as permanently broken (false negative)

**Other network errors** (already in retry list):
- Treated as: ✅ Temporary error
- Database status: `pending`
- Retried: ✅ Yes
- Impact: Correctly retried

### After Fix

**Socket hang up errors**:
- Treated as: ✅ Temporary error (network issue)
- Database status: `pending`
- Retried: ✅ Yes
- Impact: Will be retried automatically

## Recommendations

### Priority 1: Add Network Errors to Retry List ⚠️

**Impact**: HIGH - prevents false permanent failures  
**Effort**: LOW - 5 lines of code  
**Risk**: LOW - only changes error classification

```python
# Add to network_errors list in classify_error():
'socket hang up',
'ECONNRESET',
'ETIMEDOUT', 
'ECONNREFUSED',
'content.js but none received'
```

### Priority 2: Improve Error Capture (OPTIONAL)

**Impact**: MEDIUM - better error messages  
**Effort**: MEDIUM - requires refactoring  
**Risk**: LOW - only affects error reporting

Capture actual fetch errors in the result for better classification.

### Priority 3: Add Retry Count Limit (OPTIONAL)

**Impact**: LOW - prevents infinite retries  
**Effort**: MEDIUM - requires database schema change  
**Risk**: LOW - only adds safety limit

Add `retry_count` column to track how many times a creative has been retried.

## Example Scenarios

### Scenario 1: All Content.js Fail (Socket Hang Up)

**Current Flow**:
```
1. API call: ✅ Success (2 URLs)
2. Fetch file 1: ❌ socket hang up
3. Fetch file 2: ❌ socket hang up
4. Validation: ❌ "Expected 2 but none received"
5. Classification: ❌ PERMANENT failure
6. Database: status='failed' ← WRONG!
```

**After Fix**:
```
1. API call: ✅ Success (2 URLs)
2. Fetch file 1: ❌ socket hang up
3. Fetch file 2: ❌ socket hang up
4. Validation: ❌ "Expected 2 but none received"
5. Classification: ✅ RETRY (network error)
6. Database: status='pending' ← CORRECT!
```

### Scenario 2: Partial Content.js Fail

**Current Flow**:
```
1. API call: ✅ Success (2 URLs)
2. Fetch file 1: ✅ Success
3. Fetch file 2: ❌ socket hang up
4. Validation: ❌ "Only 1/2 received"
5. Classification: ✅ RETRY (incomplete)
6. Database: status='pending' ← CORRECT!
```

**After Fix**: Same (already works correctly for partial failures)

### Scenario 3: Non-Network Error

**Current Flow**:
```
1. API call: ❌ "Creative not found in API"
2. Validation: ❌ "Creative not identified"
3. Classification: ✅ BAD_AD (permanent)
4. Database: status='bad_ad' ← CORRECT!
```

**After Fix**: Same (non-network errors still permanent)

## Summary

### Current State ❌

**Socket hang up errors are marked as PERMANENT failures**:
- Not in retry list
- Creatives marked as `status='failed'`
- Require manual intervention
- False negatives (good creatives marked as broken)

### After Fix ✅

**Socket hang up errors are marked as RETRYABLE**:
- Added to network error retry list
- Creatives marked as `status='pending'`
- Automatically retried
- Correctly handled as temporary network issues

### Action Required

**Immediate**: Add network error patterns to `classify_error()`:
```python
'socket hang up',
'ECONNRESET',
'ETIMEDOUT',
'ECONNREFUSED',
'content.js but none received'
```

**Result**: Socket hang up errors will be automatically retried instead of permanently failed.

---

**Date**: 2025-10-28  
**Status**: ⚠️ BUG IDENTIFIED - Fix Recommended  
**Impact**: Medium (causes false permanent failures for network errors)  
**Fix Effort**: Low (5 lines of code)


