# Concurrent Operations Analysis: CSV Import vs Stress Test Script

## Overview

**Question:** What happens to the stress test optimized script (`stress_test_scraper_optimized.py`) that reads/writes to `fresh_creatives` table when running CSV import to `advertisers` table concurrently?

**Answer:** ✅ **Minimal Impact** - The operations are on **separate tables**, so they won't directly interfere. However, there are some indirect considerations.

---

## Tables Involved

1. **`advertisers` table** (CSV import target)
   - Receives bulk CSV data
   - ~3.5M new rows per import
   - Uses `advertiser_id` as PRIMARY KEY

2. **`creatives_fresh` table** (stress test script target)
   - Continuous reads/writes by stress test workers
   - Reads: `SELECT ... FOR UPDATE SKIP LOCKED` (fetching batches)
   - Writes: `UPDATE` statements (marking as processing/completed/failed)

---

## Impact Analysis

### ✅ 1. **No Direct Table Locking Conflicts**

**Why:** Different tables = no row-level lock conflicts

```
CSV Import (advertisers table):
  - COPY to temp table → No locks on creatives_fresh ✅
  - INSERT INTO advertisers → No locks on creatives_fresh ✅

Stress Test (creatives_fresh table):
  - SELECT FOR UPDATE on creatives_fresh → No locks on advertisers ✅
  - UPDATE creatives_fresh → No locks on advertisers ✅
```

**Result:** Operations can run simultaneously without blocking each other.

---

### ⚠️ 2. **Shared Resource Impact** (Minimal)

#### A. **Connection Pool**

**Current Stress Test:**
- Each worker creates new connection: `get_db_connection()`
- Connection closed immediately after use
- Short-lived connections (milliseconds)

**CSV Import:**
- Single long-lived connection
- Holds connection for 8-14 minutes

**Impact:** ⚠️ **Minor**
- If PostgreSQL has limited `max_connections`, CSV import holds one connection
- Stress test workers may need to wait for available connections (rare)
- **Mitigation:** Both use same connection pool config, but different timing

**Recommendation:** Ensure PostgreSQL has sufficient connections:
```sql
-- Check current setting:
SHOW max_connections;  -- Should be 100+ for 3 workers + import

-- If needed, increase in postgresql.conf:
max_connections = 200
```

---

#### B. **Transaction Log (WAL) Activity**

**CSV Import:**
- ~3.5M rows written to WAL
- Temp table placing (UNLOGGED) = no WAL for temp table ✅
- Final merge = large WAL write

**Stress Test:**
- Continuous small transactions
- Frequent commits (every batch)
- Low WAL overhead

**Impact:** ⚠️ **Low to Moderate**
- WAL writes may slow down slightly during bulk import
- More checkpoint activity
- **Mitigation:** Temp table is UNLOGGED (no WAL) = faster

---

#### C. **Index Maintenance**

**Advertisers Table Indexes:**
- PRIMARY KEY on `advertiser_id`
- Index on `advertiser_name`
- Index on `advertiser_name_normalized`
- Index on `country`

**Impact:** ⚠️ **Moderate During Merge**
- Final merge operation updates all indexes
- PostgreSQL may need to rebuild index pages
- Can cause brief slowdowns

**Timeline:**
```
0:00 - 0:05  COPY to temp table (UNLOGGED, no index updates) ✅ Fast
0:05 - 0:10  Merge INSERT ... ON CONFLICT (updates indexes) ⚠️ Slower
0:10        Done ✅
```

**During merge (5 minutes):**
- Index updates on `advertisers` table
- May cause brief I/O spikes
- Should NOT affect `creatives_fresh` operations significantly

---

#### D. **I/O Bandwidth**

**CSV Import:**
- Sequential disk writes (COPY)
- Sequential disk reads (merge operation)

**Stress Test:**
- Small random I/O (SELECT/UPDATE operations)
- Frequent but lightweight

**Impact:** ⚠️ **Low**
- Sequential I/O (import) vs Random I/O مهم (stress test)
- Different access patterns = minimal competition
- If disk is slow, both may be affected

---

### ✅ 3. **Stress Test Operations Continue Normally**

#### What the Stress Test Does:

1. **Fetch Batch:**
   ```sql
   SELECT ... FROM creatives_fresh
   WHERE status = 'pending'
   FOR UPDATE SKIP LOCKED  -- Locks rows, skips locked ones
   ```

2. **Mark Processing:**
   ```sql
   UPDATE creatives_fresh SET status = 'processing'
   WHERE id IN (...)
   ```

3. **Update Results:**
   ```sql
   UPDATE creatives_fresh SET status = 'completed', ...
   WHERE id = %s
   ```

**Impact:** ✅ **None**
- All operations on `creatives_fresh` table
- CSV import doesn't touch this table
- **No blocking or interference**

---

### ⚠️ 4. **Potential Slowdowns** (Indirect)

#### Scenarios:

**Scenario A: Heavy I/O Load**
```
Timeline:
10:00 AM - Start CSV import
10:05 AM - Start merge (heavy I/O)
10:05 AM - Stress test workers may experience:
           - Slightly slower SELECT queries (10-50ms delay)
           - Normal UPDATE performance
```

**Scenario B: Connection Pool Exhaustion**
```
If max_connections = 20:
  - 3 stress test workers = 3 connections
  - CSV import = 1 connection
  - Remaining = 16 connections ✅ Sufficient
```

**Scenario C: Checkpoint Activity**
```
During CSV import merge:
  - WAL grows (3.5M rows)
  - PostgreSQL triggers checkpoint
  - Brief I/O spike
  - Both operations may slow down for 10-30 seconds
```

---

## Performance Estimates

### CSV Import Impact on Stress Test:

| Metric | Normal | During Import | Impact |
|--------|--------|---------------|--------|
| SELECT latency | 5-20ms | 10-50ms | ⚠️ +5-30ms |
| UPDATE latency | 5-15ms | 5-20ms | ⚠️ +0-5ms |
| Batch processing | 20 URLs/batch | 20 URLs/batch | ✅ No change |
| Throughput | ~10-50 URLs/min | ~8-45 URLs/min | ⚠️ -10-20% |

**Conclusion:** Stress test will continue normally with **minor slowdown** (10-20% during merge operation).

---

## Recommendations

### ✅ **Best Practice: Run Both Concurrently**

**Why:**
- Separate tables = no direct conflicts
- Resource competition is minimal
- Both operations complete successfully

### ⚙️ **Optimization Tips:**

1. **Schedule CSV Import During Lower Activity**
   - If possible, run import during off-peak hours
   - Stress test will still work, but slower during merge

2. **Monitor PostgreSQL Connections**
   ```sql
   -- Check active connections:
   SELECT count(*) FROM pg_stat_activity;
   
   -- Check max connections:
   SHOW max_connections;
   ```

3. **Monitor Lock Waits**
   ```sql
   -- Check if stress test is waiting for locks:
   SELECT * FROM pg_locks WHERE NOT granted;
   
   -- Should show NO locks on creatives_fresh during CSV import ✅
   ```

4. **Increase WAL Size Temporarily**
   ```sql
   -- Temporarily increase checkpoint_segments for large import
   -- (If running very large imports)
   ```

5. **Use Connection Pooling**
   - CSV import: Dedicated connection (1)
   - Stress test: Separate connection pool
   - Both share same PostgreSQL instance

---

## Worst Case Scenario Analysis

### What Could Go Wrong?

**Scenario 1: Disk I/O Saturation**
- **Symptom:** Both operations slow down significantly
- **Cause:** Slow disk, insufficient I/O bandwidth
- **Solution:** 
  - Run CSV import during lower stress test activity
  - Consider faster storage (SSD)
  - Increase `checkpoint_segments`

**Scenario 2: Connection Pool Exhaustion**
- **Symptom:** Stress test workers timeout waiting for connections
- **Cause:** Too many connections, low `max_connections`
- **Solution:**
  - Increase `max_connections` in postgresql.conf
  - Use connection pooling (pgBouncer)

**Scenario 3: Memory Pressure**
- **Symptom:** OOM or slow operations
- **Cause:** Large temp table + active queries
- **Solution:**
  - Temp table uses minimal memory (UNLOGGED)
  - Increase `work_mem` for merge operation only

---

## Summary

### ✅ **Safe to Run Concurrently**

**Direct Impact:** ✅ **None**
- Different tables = no locking conflicts
- Operations independent

**Indirect Impact:** ⚠️ **Minor (10-20% slowdown during merge)**
- I/O competition during merge (5 minutes)
- Slightly slower SELECT queries
- No functional issues

**Recommendation:** ✅ **Run both simultaneously**
- Stress test continues normally
- CSV import completes in 8-14 minutes
- Temporary slowdown during merge operation only
- Both operations succeed

### Monitoring Checklist

During concurrent operation:
1. ✅ Check active connections: `SELECT count(*) FROM pg_stat_activity;`
2. ✅ Monitor lock waits: `SELECT * FROM pg_locks WHERE NOT granted;`
3. ✅ Watch stress test throughput (should be ~80-90% of normal during merge)
4. ✅ Monitor disk I/O (should spike during merge, then return to normal)

---

## Conclusion

**Your stress test script will continue operating normally** while CSV import runs. There may be a **minor performance degradation (10-20%) during the 5-minute merge operation**, but both operations will complete successfully.

**No action required** - the systems are designed to handle concurrent operations on different tables.

