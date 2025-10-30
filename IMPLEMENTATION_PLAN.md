# Advertisers Table Implementation Plan

## Overview
Implement an efficient `advertisers` lookup table to support fast ID↔name lookups for 3.5M+ rows. Data will be populated from external source. This provides a fast lookup infrastructure for advertiser ID↔name conversions and funded_by matching.

## ⚠️ Data Safety Guarantee

**CRITICAL: The `creatives_fresh` table will NOT be modified in any way.**

This implementation:
- ✅ Creates a NEW table called `advertisers` (completely separate)
- ✅ Does NOT modify, delete, or update any data in `creatives_fresh`
- ✅ Does NOT add columns to `creatives_fresh`
- ✅ Does NOT create foreign keys that would lock `creatives_fresh`
- ✅ Only READS from `creatives_fresh` if you manually query it (which we're NOT doing)

The `advertisers` table is a standalone lookup table that:
- Exists independently from `creatives_fresh`
- Can be dropped without affecting `creatives_fresh`
- Is populated from external source (not from `creatives_fresh`)

**No risk to your existing data!**

---

## Phase 1: Database Schema Setup

### Task 1.1: Create Table Migration Script
**File:** `migrations/001_create_advertisers_table.sql`

**Contents:**
- Create `advertisers` table with minimal structure:
  - `advertiser_id TEXT PRIMARY KEY`
  - `advertiser_name TEXT NOT NULL`
  - `advertiser_name_normalized TEXT`
- Create indexes:
  - Primary key index (automatic)
  - Unique index on `advertiser_name`
  - Index on `advertiser_name_normalized`
- Add normalization helper function (optional)

**Validation:**
- Verify table created successfully
- Verify indexes created
- Check table structure matches specification

---

### Task 1.2: Update Main Setup Script
**File:** `setup_database.py`

**Action:** 
- Add advertisers table creation to `create_tables()` function
- Include in table list for verification

---

**Note:** Data population is handled externally. The table is ready to accept advertiser data via the utility functions in Phase 3 (see `batch_insert_advertisers()` function).

---

## Phase 3: Utility Functions

### Task 3.1: Advertiser Lookup Utilities
**File:** `advertiser_utils.py`

**Functions:**
1. `get_advertiser_name(advertiser_id: str) -> Optional[str]`
   - Fast lookup by ID (uses primary key)

2. `get_advertiser_id(advertiser_name: str) -> Optional[str]`
   - Lookup by name (uses normalized index)

3. `batch_get_advertiser_names(advertiser_ids: List[str]) -> Dict[str, str]`
   - Bulk lookup (single query with IN clause)

4. `batch_get_advertiser_ids(advertiser_names: List[str]) -> Dict[str, str]`
   - Bulk lookup by names (normalized)

5. `insert_advertiser(advertiser_id: str, advertiser_name: str, skip_duplicate: bool = True) -> bool`
   - Single insert with duplicate handling

6. `batch_insert_advertisers(advertisers: List[Tuple[str, str]], batch_size: int = 1000) -> Dict[str, int]`
   - Batch insert with statistics (inserted, skipped)

**Features:**
- Connection pooling support
- Error handling and logging
- Return statistics (success count, skipped count)

---

## Phase 4: Performance Optimization (Optional)

### Task 4.1: Create Partial Indexes
**File:** `migrations/002_add_partial_indexes.sql` (optional)

**Indexes (if needed for queries on creatives_fresh):**
```sql
-- For extraction query (only if you need this optimization)
CREATE INDEX IF NOT EXISTS idx_creatives_fresh_videos_apps 
ON creatives_fresh(advertiser_id, scraped_at) 
WHERE video_ids IS NOT NULL AND appstore_id IS NOT NULL;
```

**Note:** Only create these if your queries will benefit from them. Test query performance first.

---

## Implementation Order

### Priority 1 (Core Functionality - Required):
1. ✅ Task 1.1: Create table migration script
2. ✅ Task 1.2: Update setup_database.py
3. ✅ Task 3.1: Create utility functions

### Priority 2 (Optional Enhancements):
4. ✅ Task 4.1: Performance indexes (only if needed for your specific queries)

---

## File Structure

```
/Users/rostoni/Downloads/LocalTransperancy/
├── migrations/
│   ├── 001_create_advertisers_table.sql
│   └── 002_add_partial_indexes.sql (optional)
├── advertiser_utils.py
├── setup_database.py (updated)
└── IMPLEMENTATION_PLAN.md (this file)
```

---

## Testing Strategy

### Unit Tests:
- Test advertiser_utils functions:
  - `get_advertiser_name()` - ID → name lookup
  - `get_advertiser_id()` - name → ID lookup
  - `batch_get_advertiser_names()` - bulk ID → name
  - `batch_get_advertiser_ids()` - bulk name → ID
  - `insert_advertiser()` - single insert with duplicate handling
  - `batch_insert_advertisers()` - batch insert with statistics

### Performance Tests:
- Benchmark lookup queries (should be < 1ms for single, < 100ms for batch of 1000)
- Benchmark batch inserts (should handle 1000+ rows/sec)
- Test with sample data at scale (1K, 10K, 100K rows)

---

## Pre-Implementation Safety Steps

**Before running any migrations, protect your data:**

1. **Create Database Backup:**
   ```bash
   python3 backup_database.py backup_before_advertisers_table.sql
   ```
   Or use automatic timestamp naming:
   ```bash
   python3 backup_database.py
   ```
   Backups are saved to `db_backups/` folder.
   
2. **Verify Backup:**
   ```bash
   # List all backups
   python3 backup_database.py --list
   
   # Or check manually
   ls -lh db_backups/backup_*.sql
   ```

3. **Test on Development/Staging First:**
   - If possible, test the migration on a copy of your database first
   - Verify all operations work correctly before production

4. **Verify creatives_fresh Safety:**
   ```sql
   -- Before migration: Count your data
   SELECT COUNT(*) FROM creatives_fresh;
   
   -- After migration: Verify count unchanged
   SELECT COUNT(*) FROM creatives_fresh;
   ```

## Rollback Plan

1. **If issues with advertisers table:**
   - Drop table: `DROP TABLE advertisers CASCADE;`
   - This will NOT affect `creatives_fresh` (they are independent)
   - Re-run migration if needed

2. **If data corruption (unlikely, but safe):**
   - Restore from backup: `psql -U transparency_user -d local_transparency < db_backups/backup_before_advertisers_table.sql`
   - Verify `creatives_fresh` is intact
   - Re-populate `advertisers` from external source using utility functions

3. **If performance issues:**
   - Review index usage with `EXPLAIN ANALYZE`
   - Add/adjust indexes as needed
   - Consider partitioning if table grows beyond 10M rows
   - Check query plans for missing index usage

---

## Success Criteria

✅ Advertisers table created with proper indexes  
✅ Table structure supports 3.5M+ rows efficiently  
✅ Lookup queries (ID→name, name→ID) complete in < 5ms  
✅ Batch inserts handle 1000+ rows per second  
✅ Utility functions handle duplicate inserts gracefully (skip on conflict)  
✅ All indexes are utilized in query plans  
✅ No data loss during migration  

---

## Notes

- **🛡️ DATA SAFETY:** The `creatives_fresh` table will NOT be modified. See `DATA_SAFETY_GUARANTEE.md` for details.
- Use connection pooling for all database operations (via advertiser_utils)
- Implement proper error handling and logging in utility functions
- Data will be populated from external source using `batch_insert_advertisers()`
- Monitor query performance with `EXPLAIN ANALYZE` after loading data
- **MANDATORY:** Create database backup before running migrations (see Pre-Implementation Safety Steps)
- Test utility functions with sample data before bulk loading 3.5M rows
