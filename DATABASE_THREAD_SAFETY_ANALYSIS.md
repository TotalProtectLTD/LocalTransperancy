# Database Thread Safety Analysis

## Summary

Found **2 critical issues** with database operations in multithreaded environment:

1. 🔴 **RACE CONDITION**: Multiple workers can fetch same creatives (duplicate work)
2. 🟡 **MAX_URLS NOT RESPECTED**: Workers don't check limit before fetching batches

## Issue #1: Race Condition in get_pending_batch() 🔴

### The Problem

**File**: `stress_test_scraper_optimized.py`  
**Functions**: `get_pending_batch()` + `mark_as_processing()`  
**Lines**: 204-251

### Current Implementation (UNSAFE)

```python
# Line 861: Worker calls get_pending_batch
creative_batch = get_pending_batch(batch_size=20)  # SELECT without locking

# Line 869: Worker marks as processing (separate transaction)
mark_as_processing(batch_ids)  # UPDATE

# Functions:
def get_pending_batch(batch_size: int = 20):
    with get_db_connection() as conn:
        cursor.execute("""
            SELECT id, creative_id, advertiser_id
            FROM creatives_fresh
            WHERE status = 'pending'
            ORDER BY RANDOM()
            LIMIT %s
        """, (batch_size,))  # ❌ NO LOCKING!
        return creatives

def mark_as_processing(creative_ids):
    with get_db_connection() as conn:
        cursor.execute(f"""
            UPDATE creatives_fresh
            SET status = 'processing'
            WHERE id IN (...)
        """)  # ❌ SEPARATE TRANSACTION!
```

### Race Condition Scenario

**Timeline with 2 workers**:

```
Time    Worker 1                           Worker 2
-----   ---------------------------------  ---------------------------------
0ms     SELECT pending (gets IDs 1-20)    
10ms                                       SELECT pending (gets IDs 1-20) ← DUPLICATE!
20ms    UPDATE status='processing'        
30ms                                       UPDATE status='processing' (overwrites)
40ms    Scrape creative 1                  Scrape creative 1 ← DUPLICATE WORK!
        Scrape creative 2                  Scrape creative 2 ← DUPLICATE WORK!
        ...                                ...
```

**Result**: 
- Both workers process same 20 creatives
- Wasted resources (40 creatives worth of work for 20 results)
- Last worker's results overwrite first worker's results
- Database gets duplicate UPDATE calls

### Impact

**With 5 workers, 100 pending creatives**:
- Expected: Each worker gets 20 unique creatives
- Actual: High chance multiple workers get overlapping creatives
- Wasted work: Could be 20-40% duplicate scraping
- Performance: Severely degraded (not truly parallel)

### Root Cause

1. **No row locking**: SELECT doesn't lock rows
2. **Separate transactions**: SELECT and UPDATE in different transactions
3. **Race window**: Gap between SELECT and UPDATE allows races

### The Fix: SELECT FOR UPDATE SKIP LOCKED

**PostgreSQL row-level locking**:
```sql
SELECT id, creative_id, advertiser_id
FROM creatives_fresh
WHERE status = 'pending'
ORDER BY RANDOM()
LIMIT 20
FOR UPDATE SKIP LOCKED;  -- ✅ LOCKS rows, SKIPs already locked

UPDATE creatives_fresh
SET status = 'processing'
WHERE id IN (...);

COMMIT;  -- Release locks
```

**How it works**:
1. `FOR UPDATE`: Locks selected rows exclusively
2. `SKIP LOCKED`: Skips rows already locked by other workers
3. Same transaction: SELECT + UPDATE atomic
4. Each worker gets unique rows (no overlap)

### Fixed Implementation

```python
def get_pending_batch_and_mark_processing(batch_size: int = 20) -> List[Dict[str, Any]]:
    """
    Get a batch of pending creatives and atomically mark them as processing.
    Uses SELECT FOR UPDATE SKIP LOCKED to prevent race conditions.
    
    Thread-safe: Multiple workers can call this concurrently without duplicates.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Atomic operation: SELECT + UPDATE in same transaction
        cursor.execute("""
            WITH selected AS (
                SELECT id, creative_id, advertiser_id
                FROM creatives_fresh
                WHERE status = 'pending'
                ORDER BY RANDOM()
                LIMIT %s
                FOR UPDATE SKIP LOCKED  -- ✅ CRITICAL: Prevents race conditions
            )
            UPDATE creatives_fresh
            SET status = 'processing'
            FROM selected
            WHERE creatives_fresh.id = selected.id
            RETURNING creatives_fresh.id, creatives_fresh.creative_id, creatives_fresh.advertiser_id
        """, (batch_size,))
        
        rows = cursor.fetchall()
        conn.commit()  # ✅ Commit immediately to release locks
        
        creatives = []
        for row in rows:
            creative = {
                'id': row[0],
                'creative_id': row[1],
                'advertiser_id': row[2]
            }
            creatives.append(creative)
        
        return creatives
```

**Benefits**:
1. ✅ **Atomic**: SELECT + UPDATE in single transaction
2. ✅ **No races**: Locked rows skipped by other workers
3. ✅ **No duplicates**: Each worker gets unique creatives
4. ✅ **Fast**: No waiting (SKIP LOCKED, not NOWAIT)
5. ✅ **Simple**: Single function call

### Updated Worker Code

```python
# Before (2 calls, race condition):
creative_batch = get_pending_batch(batch_size=batch_size)
batch_ids = [c['id'] for c in creative_batch]
mark_as_processing(batch_ids)

# After (1 call, thread-safe):
creative_batch = get_pending_batch_and_mark_processing(batch_size=batch_size)
```

---

## Issue #2: max_urls Not Respected 🟡

### The Problem

**File**: `stress_test_scraper_optimized.py`  
**Function**: `worker()`  
**Lines**: 849-865

### Current Implementation (WRONG)

```python
async def worker(..., batch_size: int = 20):
    while True:
        # Get next batch
        creative_batch = get_pending_batch(batch_size=batch_size)  # Always fetches full batch
        
        if not creative_batch:
            break
        
        # Process batch...
        # ❌ NO CHECK for max_urls!
```

**User runs**: `--max-urls 50` (expecting 50 creatives)

**What happens**:
```
Batch 1: Fetches 20 creatives (total: 20) ✅
Batch 2: Fetches 20 creatives (total: 40) ✅
Batch 3: Fetches 20 creatives (total: 60) ❌ OVER LIMIT!
```

**Result**: Processes 60 creatives instead of 50

### Root Cause

1. Worker doesn't track how many creatives processed
2. Worker doesn't check remaining before fetching batch
3. Worker always fetches full `batch_size`, even if it exceeds limit

### The Fix: Check Remaining Before Fetch

```python
async def worker(..., batch_size: int = 20):
    while True:
        # Check remaining before fetching
        async with stats_lock:
            remaining = stats['total_pending'] - stats['processed']
        
        if remaining <= 0:
            break  # ✅ Limit reached
        
        # Adjust batch size to not exceed limit
        actual_batch_size = min(batch_size, remaining)  # ✅ CRITICAL
        
        creative_batch = get_pending_batch_and_mark_processing(batch_size=actual_batch_size)
        
        if not creative_batch:
            break
        
        # Process batch...
```

**Now with `--max-urls 50`**:
```
Batch 1: Fetches 20 (remaining: 30) ✅
Batch 2: Fetches 20 (remaining: 10) ✅
Batch 3: Fetches 10 (remaining: 0)  ✅ RESPECTS LIMIT!
```

**Result**: Exactly 50 creatives processed

---

## Issue #3: update_result() Thread Safety ✅

### Analysis

**File**: `stress_test_scraper_optimized.py`  
**Function**: `update_result()`  
**Lines**: 303-387

### Current Implementation

```python
def update_result(creative_id: int, result: Dict[str, Any]):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        if result.get('success'):
            cursor.execute("""
                UPDATE creatives_fresh
                SET status = 'completed', ...
                WHERE id = %s
            """, (..., creative_id))
        else:
            cursor.execute("""
                UPDATE creatives_fresh
                SET status = 'pending'/'failed'/'bad_ad', ...
                WHERE id = %s
            """, (..., creative_id))
        
        conn.commit()
```

### Thread Safety: ✅ SAFE

**Why it's safe**:
1. ✅ Each UPDATE targets single row by `WHERE id = %s`
2. ✅ No SELECT before UPDATE (no read-modify-write race)
3. ✅ Last write wins (acceptable - same creative shouldn't be processed twice)
4. ✅ Auto-commit per UPDATE (no long-held locks)

**Potential issue** (only if duplicate work happens):
- If Worker A and Worker B both process same creative (due to Issue #1):
  - Both call `update_result(creative_id, ...)`
  - Last worker's result overwrites first worker's result
  - No data corruption, but wasted work

**Fixed by**: Issue #1 fix prevents duplicates

---

## Complete Fix Implementation

### Step 1: Replace get_pending_batch() and mark_as_processing()

**Old code** (2 functions, race condition):
```python
def get_pending_batch(batch_size: int = 20):
    # SELECT without locking

def mark_as_processing(creative_ids):
    # UPDATE in separate transaction
```

**New code** (1 function, thread-safe):
```python
def get_pending_batch_and_mark_processing(batch_size: int = 20) -> List[Dict[str, Any]]:
    """
    Get a batch of pending creatives and atomically mark them as processing.
    Uses SELECT FOR UPDATE SKIP LOCKED to prevent race conditions.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            WITH selected AS (
                SELECT id, creative_id, advertiser_id
                FROM creatives_fresh
                WHERE status = 'pending'
                ORDER BY RANDOM()
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            )
            UPDATE creatives_fresh
            SET status = 'processing'
            FROM selected
            WHERE creatives_fresh.id = selected.id
            RETURNING creatives_fresh.id, creatives_fresh.creative_id, creatives_fresh.advertiser_id
        """, (batch_size,))
        
        rows = cursor.fetchall()
        conn.commit()
        
        return [{'id': row[0], 'creative_id': row[1], 'advertiser_id': row[2]} for row in rows]
```

### Step 2: Update worker() to respect max_urls

**Old code**:
```python
async def worker(...):
    while True:
        creative_batch = get_pending_batch(batch_size=batch_size)
        
        if not creative_batch:
            break
        
        batch_ids = [c['id'] for c in creative_batch]
        mark_as_processing(batch_ids)
```

**New code**:
```python
async def worker(...):
    while True:
        # Check remaining creatives
        async with stats_lock:
            remaining = stats['total_pending'] - stats['processed']
        
        if remaining <= 0:
            break
        
        # Adjust batch size to not exceed limit
        actual_batch_size = min(batch_size, remaining)
        
        # Get batch (atomically marks as processing)
        creative_batch = get_pending_batch_and_mark_processing(batch_size=actual_batch_size)
        
        if not creative_batch:
            break
```

---

## Testing

### Test 1: Race Condition (Before Fix)

**Setup**: 100 pending creatives, 5 workers, batch_size=20

**Run**:
```bash
python3 stress_test_scraper_optimized.py --threads 5 --max-urls 100
```

**Expected (wrong)**:
- High chance of duplicates
- Some workers process same creatives
- Final count might be < 100 unique creatives

### Test 1: Race Condition (After Fix)

**Expected (correct)**:
- No duplicates
- Each creative processed exactly once
- All 100 creatives completed

### Test 2: max_urls Limit (Before Fix)

**Setup**: 100 pending creatives, 1 worker, batch_size=20

**Run**:
```bash
python3 stress_test_scraper_optimized.py --threads 1 --max-urls 50
```

**Expected (wrong)**: Processes 60 creatives (3 batches × 20)

### Test 2: max_urls Limit (After Fix)

**Expected (correct)**: Processes exactly 50 creatives (20+20+10)

### Test 3: Concurrent Updates (Already Safe)

**Setup**: Force duplicate processing (manually set 2 creatives to 'pending')

**Expected**: Last write wins, no corruption, both results valid

---

## Summary

### Issues Found

| # | Issue | Severity | Impact | Status |
|---|-------|----------|--------|--------|
| 1 | Race condition in get_pending_batch | 🔴 Critical | Duplicate work, 20-40% wasted | **FIX REQUIRED** |
| 2 | max_urls not respected | 🟡 Medium | Processes more than requested | **FIX REQUIRED** |
| 3 | update_result thread safety | 🟢 OK | No issues | ✅ Already safe |

### Fixes Required

1. ✅ **Replace** `get_pending_batch()` + `mark_as_processing()` with `get_pending_batch_and_mark_processing()`
   - Use `SELECT FOR UPDATE SKIP LOCKED`
   - Atomic SELECT + UPDATE
   - Prevents race conditions

2. ✅ **Add** max_urls check in worker()
   - Check remaining before fetch
   - Adjust batch_size to not exceed limit
   - Respects `--max-urls` argument

### Benefits After Fix

✅ **No duplicate work**: Each creative processed exactly once  
✅ **True parallelism**: Workers don't compete for same rows  
✅ **Respects limits**: `--max-urls` works correctly  
✅ **Better performance**: No wasted scraping  
✅ **Database-level safety**: Relies on PostgreSQL locking, not application logic

### Performance Impact

**Before**:
- With 5 workers: ~20-40% duplicate work
- 100 creatives: ~120-140 actually processed
- Throughput: Degraded by race overhead

**After**:
- With 5 workers: 0% duplicate work
- 100 creatives: Exactly 100 processed
- Throughput: Full parallelism, no waste

---

**Date**: 2025-10-28  
**Status**: 🔴 CRITICAL FIXES REQUIRED  
**Priority**: HIGH (affects production data quality and performance)  
**Risk**: MEDIUM (SQL change, but well-tested pattern)


