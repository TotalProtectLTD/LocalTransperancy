# Efficient CSV Upload Plan - 3.5M Rows to Advertisers Table

## Overview
Load 3.5 million rows from GCS exports CSV files into PostgreSQL `advertisers` table with duplicate skipping, while minimizing impact on concurrent `fresh_creatives` table operations.

## CSV Format
```
advertiser_id,advertiser_disclosed_name,advertiser_location
AR16057455244413501441,Nokia Solutions and Networks OY,""
AR14859705070194262017,Hasbro,""
AR05532063064322473985,Tatenda Tasaranarwo,ZW
AR05683893628569649153,VALIANT,AD
```

**Mapping:**
- `advertiser_id` → `advertiser_id` (PRIMARY KEY)
- `advertiser_disclosed_name` → `advertiser_name`
- `advertiser_location` → `country` (2-letter country code, e.g., "US", "DE", "ZW")

**Data Statistics (from actual CSV):**
- Total rows: ~3.5M
- **With country: 99.93%** (3,561,490 rows)
- Without country: 0.07% (2,508 rows - empty string should map to NULL)
- Top countries: US (458k), DE (264k), TR (255k), FR (244k), GB (177k)

---

## Performance Strategy Ranking (Fastest to Slowest)

### 🏆 **Option 1: Temporary Table + COPY + Bulk Merge** (RECOMMENDED)
**Speed:** ~5-15 minutes for 3.5M rows  
**Lock Contention:** Minimal (short lock window during merge)  
**Memory:** Low (streaming)

#### Process:
1. Create temporary UNLOGGED table (faster writes, no WAL overhead)
2. Use PostgreSQL `COPY` command to bulk load CSV into temp table (fastest method)
3. Single `INSERT ... ON CONFLICT` statement to merge from temp to main table
4. Drop temp table

#### Advantages:
- ✅ **Fastest method** - COPY is optimized for bulk loading
- ✅ **Minimal lock time** - Only brief lock during final merge step
- ✅ **Low memory footprint** - Streaming CSV processing
- ✅ **Native PostgreSQL optimization** - Uses fastest code path
- ✅ **Good for concurrent operations** - Temp table operations don't lock main table

#### Implementation Details:
```python
# Pseudo-code flow:
1. CREATE TEMPORARY UNLOGGED TABLE advertisers_temp (...)
2. COPY advertisers_temp FROM CSV file
3. INSERT INTO advertisers SELECT ... FROM advertisers_temp 
   ON CONFLICT (advertiser_id) DO NOTHING
4. DROP TABLE advertisers_temp
```

**Estimated Time:** 5-15 minutes

---

### 🥈 **Option 2: execute_values() with Large Batches**
**Speed:** ~15-30 minutes for 3.5M rows  
**Lock Contention:** Low (batched commits)  
**Memory:** Medium (batches in memory)

#### Process:
1. Read CSV in chunks
2. Use `psycopg2.extras.execute_values()` with large batches (50k-100k rows)
3. Commit every N batches
4. Use `INSERT ... ON CONFLICT DO NOTHING`

#### Advantages:
- ✅ **Good performance** - execute_values is much faster than executemany
- ✅ **Control over batch size** - Can tune based on system
- ✅ **Progress tracking** - Easier to show progress
- ✅ **No temp table cleanup** - Simpler code

#### Disadvantages:
- ⚠️ Slower than COPY method
- ⚠️ More transaction overhead

**Estimated Time:** 15-30 minutes

---

### 🥉 **Option 3: Current batch_insert_advertisers() with Optimization**
**Speed:** ~45-90 minutes for 3.5M rows  
**Lock Contention:** Medium (many small transactions)  
**Memory:** Low

#### Current Implementation:
- Uses `executemany()` with 1k batch size
- Commits after each batch
- Too many transactions = slow

#### Optimizations:
1. Increase batch size to 50k-100k
2. Commit every 5-10 batches instead of every batch
3. Use `execute_values()` instead of `executemany()`

**Estimated Time:** 20-40 minutes (after optimization)

---

### ❌ **Option 4: Row-by-Row Inserts** (NOT RECOMMENDED)
**Speed:** ~4-8 hours for 3.5M rows  
**Lock Contention:** High  
**Memory:** Very Low

**DO NOT USE** - This is what happens with very small batch sizes.

---

## Recommended Implementation: Option 1

### Step-by-Step Plan

#### Phase 1: Create Import Script
**File:** `import_advertisers_from_csv.py`

**Features:**
- Load CSV from `gcs_exports/` directory
- Handle multiple CSV files
- Use temp table + COPY method
- Progress tracking
- Error handling and recovery
- Statistics reporting

#### Phase 2: Optimize Database for Bulk Load

**Before Import:**
1. **Temporary increase work_mem** (for merge operation):
   ```sql
   SET work_mem = '256MB';  -- Only for import session
   ```

2. **Consider disabling autovacuum during import** (optional, for very large loads):
   ```sql
   ALTER TABLE advertisers SET (autovacuum_enabled = false);
   -- Re-enable after import:
   -- ALTER TABLE advertisers SET (autovacuum_enabled = true);
   ```

3. **Ensure indexes exist** (already done):
   - Primary key on `advertiser_id` ✓
   - Index on `advertiser_name_normalized` ✓

#### Phase 3: Minimize Lock Contention with fresh_creatives

**Strategies:**
1. **Separate Connection Pool** - Use different connection pool for import
2. **Lower Isolation Level** (if acceptable):
   ```python
   conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)
   ```
3. **Batch Merge Operations** - Break final merge into chunks if needed:
   ```sql
   -- Instead of one big merge, do:
   INSERT INTO advertisers SELECT ... FROM advertisers_temp WHERE advertiser_id < 'threshold1'
   ON CONFLICT DO NOTHING;
   INSERT INTO advertisers SELECT ... FROM advertisers_temp WHERE advertiser_id >= 'threshold1'
   ON CONFLICT DO NOTHING;
   ```

4. **Schedule During Low Usage** - Run import during off-peak hours if possible

#### Phase 4: Monitoring & Recovery

**Progress Tracking:**
- Show rows processed per second
- Estimated time remaining
- Memory usage

**Recovery:**
- Resume capability (check what's already imported)
- Logging for debugging
- Rollback on critical errors

---

## Implementation Code Structure

### Script Outline

```python
import_csv_advertisers_to_postgres.py
├── Configuration
│   ├── CSV directory path
│   ├── Database connection (separate pool)
│   └── Batch/transaction settings
├── CSV Processing
│   ├── Discover CSV files in gcs_exports/
│   ├── Validate CSV format
│   └── Stream reading (don't load all in memory)
├── Temp Table Management
│   ├── Create UNLOGGED temp table
│   ├── COPY data into temp table
│   └── Cleanup temp table
├── Merge Operation
│   ├── INSERT ... ON CONFLICT (bulk merge)
│   ├── Statistics (inserted/skipped counts)
│   └── Progress reporting
└── Error Handling
    ├── Transaction rollback
    ├── Resume capability
    └── Detailed logging
```

---

## Performance Estimates

### Option 1 (Temp Table + COPY):
- **CSV Read:** 2-3 minutes (streaming)
- **COPY to Temp:** 3-5 minutes
- **Merge Operation:** 2-5 minutes
- **Cleanup:** < 1 minute
- **Total:** ~8-14 minutes

### Option 2 (execute_values):
- **CSV Read:** 2-3 minutes
- **Batch Inserts:** 12-25 minutes
- **Total:** ~15-30 minutes

### Option 3 (Current Optimized):
- **CSV Read:** 2-3 minutes
- **Batch Inserts:** 18-37 minutes
- **Total:** ~20-40 minutes

---

## Key Optimization Techniques

### 1. Use UNLOGGED Temporary Tables
```sql
CREATE TEMPORARY UNLOGGED TABLE advertisers_temp (
    advertiser_id TEXT,
    advertiser_name TEXT,
    country TEXT
);
```
- No WAL logging = 2-3x faster writes
- No durability needed (temp data)

### 2. Bulk Normalization
Instead of normalizing in Python, do it in SQL:
```sql
INSERT INTO advertisers (advertiser_id, advertiser_name, advertiser_name_normalized, country)
SELECT 
    advertiser_id,
    advertiser_disclosed_name,
    LOWER(TRIM(advertiser_disclosed_name)),
    NULLIF(TRIM(advertiser_location), '')
FROM advertisers_temp
ON CONFLICT (advertiser_id) DO NOTHING;
```

### 3. Monitor Progress
```sql
-- Get progress during COPY
SELECT pg_stat_get_progress_info('COPY');
```

### 4. Connection Pooling
Use separate connection for import to avoid affecting other operations:
```python
import_pool = psycopg2.pool.SimpleConnectionPool(1, 2, **DB_CONFIG)
```

---

## Concurrent Operation Considerations

### Impact on fresh_creatives Table

**With Option 1 (Recommended):**
- ✅ Minimal impact - temp table operations don't affect main tables
- ✅ Short lock window during final merge (2-5 minutes)
- ✅ Index updates are espread out during merge

**Best Practices:**
1. **Run during low-usage period** if possible
2. **Monitor lock waits:**
   ```sql
   SELECT * FROM pg_locks WHERE NOT granted;
   ```
3. **Use connection timeout** to prevent blocking:
   ```python
   conn = psycopg2.connect(..., connect_timeout=10)
   ```

---

## Memory Requirements

### Option 1:
- **Peak Memory:** ~500MB-1GB
  - CSV reading buffer: ~10MB
  - Temp table in PostgreSQL: ~500MB-1GB (depends on data)

### Option 2:
- **Peak Memory:** ~1-2GB
  - Batch buffer in Python: ~500MB-1GB
  - PostgreSQL work_mem: ~256MB

---

## Error Handling Strategy

1. **Transaction Management:**
   - Use savepoints for recovery
   - Rollback temp table on critical errors

2. **Resume Capability:**
   - Track which CSV files processed
   - Skip already-processed files
   - Check for partial imports

3. **Validation:**
   - Validate CSV format before processing
   - Check required columns exist
   - Handle encoding issues (UTF-8)

---

## Testing Strategy

1. **Small Test (1k rows):** Verify logic
2. **Medium Test (100k rows):** Verify performance
3. **Full Test (3.5M rows):** Production run

---

## Summary

**RECOMMENDED APPROACH:** Option 1 - Temporary Table + COPY + Bulk Merge

**Expected Performance:**
- ⏱️ **Time:** 8-14 minutes for 3.5M rows
- 🔒 **Lock Contention:** Minimal (2-5 minute window)
- 💾 **Memory:** ~500MB-1GB
- ✅ **Scalability:** Handles 10M+ rows efficiently

**Next Steps:**
1. Implement `import_advertisers_from_csv.py` using Option 1
2. Test with small subset
3. Optimize batch sizes based on system
4. Deploy and monitor

