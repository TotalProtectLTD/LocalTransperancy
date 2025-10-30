# Data Safety Guarantee

## Your `creatives_fresh` Table is 100% Safe

This implementation creates a **NEW, SEPARATE** table called `advertisers`. Your existing `creatives_fresh` table will **NOT be touched** in any way.

### What We're Doing

✅ **Creating a new table:** `advertisers`
- Completely independent from `creatives_fresh`
- No foreign keys pointing to `creatives_fresh`
- No modifications to `creatives_fresh` schema
- No data migration from `creatives_fresh`

✅ **Reading-only operations:**
- We're NOT reading from `creatives_fresh` in any scripts
- We're NOT extracting data from `creatives_fresh`
- Data for `advertisers` comes from external source only

### What We're NOT Doing

❌ **NOT Karen modifying `creatives_fresh`:**
- No ALTER TABLE statements on `creatives_fresh`
- No column additions
- No data deletions
- No data updates
- No index changes

❌ **NOT creating dependencies:**
- No foreign keys from `advertisers` to `creatives_fresh`
- No foreign keys from `creatives_fresh` to `advertisers`
- Tables remain completely independent

### Verification Steps

After running the migration, verify your data is safe:

```sql
-- 1. Check creatives_fresh row count (should be unchanged)
SELECT COUNT(*) FROM creatives_fresh;

-- 2. Verify new advertisers table exists and is separate
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('creatives_fresh', 'advertisers');

-- 3. Check that advertisers table doesn't reference creatives_fresh
SELECT
    tc.constraint_name, 
    tc.table_name, 
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name 
FROM information_schema.table_constraints AS tc 
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' 
  AND (tc.table_name = 'advertisers' OR ccu.table_name = 'creatives_fresh');
-- Should return 0 rows (no foreign keys between them)
```

### What If Something Goes Wrong?

Even in the worst case scenario:

1. **If `advertisers` table has issues:**
   ```sql
   DROP TABLE advertisers CASCADE;
   ```
   This will NOT affect `creatives_fresh` at all.

2. **If you need to restore from backup:**
   ```bash
   # Before migration: Create backup using script
   python3 backup_database.py backup_before_advertisers_table.sql
   
   # If needed: Restore from backup
   psql -U transparency_user -d local_transparency < db_backups/backup_before_advertisers_table.sql
   ```
   Your `creatives_fresh` data will be restored exactly as it was.
   
   **Backup location:** All backups are stored in `db_backups/` folder (tracked in git, but backup files are ignored).

### SQL Operations Breakdown

Here's exactly what SQL will run (for transparency):

#### Safe Operations (Creating New Table):
```sql
-- This creates a NEW table - doesn't touch existing tables
CREATE TABLE advertisers (
    advertiser_id TEXT PRIMARY KEY,
    advertiser_name TEXT NOT NULL,
    advertiser_name_normalized TEXT
);

-- These create indexes on the NEW table only
CREATE UNIQUE INDEX idx_advertisers_name_unique 
ON advertisers(advertiser_name);

CREATE INDEX idx_advertisers_name_normalized 
ON advertisers(advertiser_name_normalized);
```

#### What's NOT in the Migration:
- ❌ No `ALTER TABLE creatives_fresh ...`
- ❌ No `UPDATE creatives_fresh ...`
- ❌ No `DELETE FROM creatives_fresh ...`
- ❌ No `INSERT INTO creatives_fresh ...` (except your normal scraper operations)
- ❌ No foreign key constraints to `creatives_fresh`

### Summary

**Your `creatives_fresh` data is completely safe.** This implementation only creates a new, independent `advertisers` table that can be used for lookups. Even if you delete the `advertisers` table later, your `creatives_fresh` table will remain untouched.

---

**Still worried?** Run the migration on a test database first, or make a backup before proceeding. But rest assured: your existing data will not be modified in any way.
