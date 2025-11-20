# Investigation: Stuck "Processing" Rows in creatives_fresh

## Problem Statement

Rows in `creatives_fresh` table sometimes get stuck with `status = 'processing'` and never get updated back to other statuses (`completed`, `pending`, `failed`, `bad_ad`).

Query that reveals the issue:
```sql
SELECT * FROM creatives_fresh 
WHERE sync = false 
  AND appstore_id IS NOT NULL 
  AND status <> 'bad_ad'
  AND status = 'processing';  -- These are stuck
```

## Root Causes Identified

### 🔴 CRITICAL ISSUE #1: Early Return in `scrape_batch_optimized()` (Line 662)

**Location**: `stress_test_scraper_optimized.py:644-662`

**Problem**:
When the first creative in a batch fails, the function returns early with only 1 result, but the batch may contain 20 creatives (all marked as 'processing').

```python
except Exception as e:
    # ... create error result for first creative ...
    results.append({...})  # Only first creative gets a result
    
    # If first creative fails, close browser and return
    await browser.close()
    return results  # ❌ RETURNS ONLY 1 RESULT, BUT BATCH HAS 20 CREATIVES!
```

**Impact**:
- Batch of 20 creatives marked as 'processing' (line 831)
- First creative fails
- Function returns with only 1 result
- Worker updates only 1 creative (line 850)
- **19 creatives remain stuck as 'processing'**

**Example Scenario**:
```
1. Worker gets batch of 20 creatives → all marked as 'processing'
2. First creative fails (network error, timeout, etc.)
3. scrape_batch_optimized() returns [result_for_creative_1]
4. Worker updates only creative_1
5. Creatives 2-20 remain stuck as 'processing' forever
```

---

### 🔴 CRITICAL ISSUE #2: Exception in Worker Update Loop (Lines 848-850)

**Location**: `stress_test_scraper_optimized.py:847-872`

**Problem**:
If an exception occurs during the update loop, remaining creatives in the batch are never updated.

```python
# Update database for each result
for result in results:
    creative_db_id = result.pop('creative_db_id')  # ❌ Can raise KeyError
    update_result(creative_db_id, result)  # ❌ Can raise exception (DB connection, etc.)
    # ... update stats ...
```

**Failure Scenarios**:

1. **KeyError**: If `result` doesn't have `'creative_db_id'` key
   ```python
   creative_db_id = result.pop('creative_db_id')  # KeyError → loop breaks
   ```

2. **Database Connection Failure**: If `update_result()` raises exception
   ```python
   update_result(creative_db_id, result)  # psycopg2.OperationalError → loop breaks
   ```

3. **Transaction Failure**: If database transaction fails
   ```python
   update_result(creative_db_id, result)  # Database error → loop breaks
   ```

**Impact**:
- Batch of 20 creatives marked as 'processing'
- `scrape_batch_optimized()` returns 20 results
- Update loop processes first 5 successfully
- Exception occurs on creative #6
- **Creatives 6-20 remain stuck as 'processing'**

**Empty Finally Block**:
```python
finally:
    pass  # ❌ No cleanup - stuck rows never recovered
```

---

### 🟡 ISSUE #3: Proxy Acquisition Hang (Line 840)

**Location**: `stress_test_scraper_optimized.py:457-499` and `840`

**Problem**:
`acquire_proxy_from_api()` has an infinite retry loop. If the API is down, the worker hangs forever.

```python
async def acquire_proxy_from_api() -> Dict[str, str]:
    while True:  # ❌ INFINITE LOOP - NO TIMEOUT
        try:
            # ... try to get proxy ...
            if response.status_code == 200:
                return {...}
        except Exception as e:
            print(f"  ⚠️  Failed to acquire proxy: {e}, retrying in {PROXY_ACQUIRE_TIMEOUT}s...")
        
        await asyncio.sleep(PROXY_ACQUIRE_TIMEOUT)  # Retries forever
```

**Impact**:
- Worker gets batch of 20 creatives → all marked as 'processing'
- Worker tries to acquire proxy
- API is down/unreachable
- Worker hangs forever waiting for proxy
- **All 20 creatives remain stuck as 'processing'**

**When This Happens**:
- MagicTransparency API is down
- Network connectivity issues
- API rate limiting (though it should return 429, not hang)

---

### 🟡 ISSUE #4: Exception During Scraping (Line 845)

**Location**: `stress_test_scraper_optimized.py:845`

**Problem**:
If `scrape_batch_optimized()` raises an unhandled exception, no results are returned, and all creatives remain stuck.

```python
# Scrape entire batch (optimized with session reuse)
results = await scrape_batch_optimized(...)  # ❌ Can raise exception

# Update database for each result
for result in results:  # ❌ If exception above, results is undefined → NameError
    ...
```

**Exception Scenarios**:

1. **Browser Setup Failure** (caught, but see Issue #1)
2. **Playwright Exception** (unhandled)
3. **Memory Error** (unhandled)
4. **System Error** (unhandled)

**Impact**:
- Batch of 20 creatives marked as 'processing'
- `scrape_batch_optimized()` raises exception
- Exception propagates to worker
- Worker's try block catches it, but `results` is undefined
- **All 20 creatives remain stuck as 'processing'**

**Note**: The outer try/except in `scrape_batch_optimized()` (line 762) should catch browser setup failures, but other exceptions may propagate.

---

### 🟡 ISSUE #5: Length Mismatch Between Batch and Results

**Location**: `stress_test_scraper_optimized.py:848`

**Problem**:
If `scrape_batch_optimized()` returns fewer results than the batch size, some creatives are never updated.

**How This Could Happen**:
- Bug in `scrape_batch_optimized()` that skips some creatives
- Exception in the loop that processes remaining creatives (line 673)
- Early return that doesn't include all creatives

**Example**:
```python
creative_batch = [creative_1, creative_2, ..., creative_20]  # 20 creatives
results = await scrape_batch_optimized(...)  # Returns only 18 results
for result in results:  # Only updates 18 creatives
    update_result(...)
# ❌ 2 creatives never updated, remain stuck as 'processing'
```

**Current Code Analysis**:
- Line 662: Early return with only first creative → **CONFIRMED ISSUE**
- Line 673-753: Loop processes remaining creatives, but if exception occurs mid-loop, some may be skipped
- Line 768-778: Browser setup failure creates results for all creatives → **GOOD**

---

### 🟡 ISSUE #6: Process Crash/Kill

**Location**: Anywhere in worker loop

**Problem**:
If the Python process is killed (SIGKILL, OOM killer, system crash) after marking rows as 'processing' but before updating them, rows remain stuck.

**Scenarios**:
- System runs out of memory → OOM killer kills process
- User kills process (Ctrl+C, kill -9)
- System crash/reboot
- Docker container killed

**Impact**:
- Rows marked as 'processing' in database
- Process dies before `update_result()` is called
- **Rows remain stuck as 'processing' forever**

**No Recovery Mechanism**:
- No timeout on 'processing' status
- No cleanup job to reset stuck rows
- No heartbeat/health check

---

## Summary of Issues

| Issue | Severity | Frequency | Impact |
|-------|----------|-----------|--------|
| #1: Early return (line 662) | 🔴 CRITICAL | High | 19/20 creatives stuck per failed first creative |
| #2: Exception in update loop | 🔴 CRITICAL | Medium | Variable (depends on which creative fails) |
| #3: Proxy acquisition hang | 🟡 HIGH | Low | All creatives in batch stuck |
| #4: Exception during scraping | 🟡 HIGH | Low | All creatives in batch stuck |
| #5: Length mismatch | 🟡 MEDIUM | Low | Variable (depends on bug) |
| #6: Process crash | 🟡 MEDIUM | Very Low | All creatives in active batches stuck |

---

## Evidence from Code

### Issue #1: Early Return (CONFIRMED)

**File**: `stress_test_scraper_optimized.py:644-662`

```python
except Exception as e:
    error_msg = f"{type(e).__name__}: {str(e)}"
    print(f"    ❌ {first_creative['creative_id'][:15]}... - {error_msg[:60]}")
    sys.stdout.flush()
    
    results.append({
        'creative_db_id': first_creative['id'],
        'success': False,
        'error': error_msg,
        # ...
    })
    
    # If first creative fails, close browser and return
    await browser.close()
    return results  # ❌ RETURNS ONLY 1 RESULT!
```

**Fix Required**: Continue processing remaining creatives even if first creative fails, or ensure all creatives get error results.

---

### Issue #2: No Exception Handling in Update Loop (CONFIRMED)

**File**: `stress_test_scraper_optimized.py:847-872`

```python
# Update database for each result
for result in results:
    creative_db_id = result.pop('creative_db_id')  # ❌ No try/except
    update_result(creative_db_id, result)  # ❌ No try/except
    # ... update stats ...
```

**Fix Required**: Wrap each update in try/except to continue processing remaining creatives.

---

### Issue #3: Infinite Retry in Proxy Acquisition (CONFIRMED)

**File**: `stress_test_scraper_optimized.py:457-499`

```python
async def acquire_proxy_from_api() -> Dict[str, str]:
    while True:  # ❌ INFINITE LOOP
        try:
            # ... try to get proxy ...
            if response.status_code == 200:
                return {...}
        except Exception as e:
            print(f"  ⚠️  Failed to acquire proxy: {e}, retrying in {PROXY_ACQUIRE_TIMEOUT}s...")
        
        await asyncio.sleep(PROXY_ACQUIRE_TIMEOUT)  # Retries forever
```

**Fix Required**: Add timeout or max retry limit.

---

## Recommended Solutions (For Reference - Not Implementing)

### Solution #1: Fix Early Return
- Continue processing remaining creatives even if first creative fails
- OR: Return error results for all creatives in batch

### Solution #2: Add Exception Handling in Update Loop
- Wrap each `update_result()` call in try/except
- Continue processing remaining creatives even if one fails
- Log errors for debugging

### Solution #3: Add Timeout to Proxy Acquisition
- Add max retry limit or timeout
- Return error result for all creatives if proxy acquisition fails

### Solution #4: Add Cleanup/Recovery Mechanism
- Periodic job to reset stuck 'processing' rows older than X minutes
- Heartbeat mechanism to detect dead workers
- Timeout-based recovery

### Solution #5: Add Validation
- Verify `len(results) == len(creative_batch)` before updating
- Ensure all results have required fields before processing

---

## Current Workaround

The project already has a script to reset stuck rows:
- `reset_processing_to_pending.py` - Resets all 'processing' rows to 'pending'

**Usage**:
```bash
python3 reset_processing_to_pending.py
```

This is a manual recovery mechanism, but doesn't prevent the issue from occurring.

---

## Verification: No Length Validation

**Confirmed**: The worker does NOT verify that `len(results) == len(creative_batch)` before updating.

**Code Evidence** (Line 845-850):
```python
results = await scrape_batch_optimized(creative_batch, proxy_config, worker_id, use_partial_proxy)

# Update database for each result
for result in results:  # ❌ No validation that len(results) == len(creative_batch)
    creative_db_id = result.pop('creative_db_id')
    update_result(creative_db_id, result)
```

**Impact**:
- If `scrape_batch_optimized()` returns 1 result for a batch of 20, only 1 creative gets updated
- The remaining 19 creatives remain stuck as 'processing'
- No error is logged or detected

**This confirms Issue #1 is a real bug that causes stuck rows.**

---

## Investigation Date

2025-01-XX (Current date)

## Files Analyzed

- `stress_test_scraper_optimized.py` (main scraper)
- `scheduler/run-parser-advertiser.sh` (scheduler task)
- `reset_processing_to_pending.py` (recovery script)

## Scheduler Tasks Mentioned

User mentioned "4 tasks" in scheduler:
1. `run-parser-advertiser.sh` - Parses advertisers
2. `run-bigquery-creatives.sh` - Syncs from BigQuery
3. `run-send-creatives.sh` - Sends creatives to API
4. (Unknown 4th task - possibly stress_test_scraper_optimized.py itself)

The stuck rows issue is specific to `stress_test_scraper_optimized.py`, not the scheduler tasks.

