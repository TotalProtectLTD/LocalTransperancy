# Database Overview and Operations

This document summarizes the current database schema, key indices, read/write workflows, and safe patterns to follow for future changes.

## Environment
- PostgreSQL server: 18.0
- Database: `local_transparency`
- Primary working tables: `creatives_fresh`, `advertisers`
- Other tables: `creatives`, `scraping_sessions`, `scraping_logs`

## Tables

### creatives_fresh
Purpose: High-throughput queue of transparency creatives (hot table used by scrapers and sender).

Columns (key ones):
- `id SERIAL PRIMARY KEY`
- `creative_id TEXT NOT NULL` (UNIQUE)
- `advertiser_id TEXT NOT NULL`
- `status TEXT DEFAULT 'pending'` (e.g., `pending, processing, completed, failed, bad_ad, syncing, synced`)
- `video_count INTEGER DEFAULT 0`
- `video_ids TEXT` (JSON serialized, not queried in SQL)
- `appstore_id TEXT` (normalized on write to NULL when blank/whitespace)
- `funded_by TEXT`
- `sync BOOLEAN DEFAULT FALSE`
- `scraped_at TIMESTAMP`
- `error_message TEXT`
- `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`

Current indexes:
- `creatives_fresh_pkey` on `(id)`
- `idx_creatives_fresh_creative_id_unique` UNIQUE on `(creative_id)`
- `idx_creatives_fresh_status` on `(status)`
- `idx_creatives_fresh_created_at` on `(created_at)`
- `idx_creatives_fresh_advertiser_id` on `(advertiser_id)`
- `idx_creatives_fresh_scraped_at` on `(scraped_at)`
- Partial (claims): `idx_cf_pending_created_at` on `(created_at)` WHERE `status='pending'`
- Partial (sender): `idx_cf_sync_ready_created_at_v2` on `(created_at)` WHERE `status IN ('completed','sync_failed') AND (sync IS NOT TRUE) AND appstore_id IS NOT NULL`

Table settings (bloat control):
- `autovacuum_vacuum_scale_factor=0.02`
- `autovacuum_analyze_scale_factor=0.02`
- `fillfactor=80`

### advertisers
Purpose: Lookup of advertiser ID => name (+ normalized name, country), fed by BigQuery.

Columns:
- `advertiser_id TEXT PRIMARY KEY`
- `advertiser_name TEXT NOT NULL`
- `advertiser_name_normalized TEXT`
- `country TEXT`

Indexes:
- `advertisers_pkey` on `(advertiser_id)`
- `idx_advertisers_name` on `(advertiser_name)`
- `idx_advertisers_name_normalized` on `(advertiser_name_normalized)`
- `idx_advertisers_country` on `(country)`

### other tables
Defined in `setup_database.py`:
- `creatives` (legacy/general store)
- `scraping_sessions` (batch/session metadata)
- `scraping_logs` (per-URL results log)

## Workflows and responsible files

- Scraping and queue claims (reads/writes `creatives_fresh`):
  - `stress_test_scraper_optimized.py`
    - Claims with `SELECT ... FOR UPDATE SKIP LOCKED`
    - CTE orders by `created_at` (FIFO) using `idx_cf_pending_created_at`
    - Writes result fields (`status`, `video_*`, `appstore_id`, `funded_by`, `scraped_at`, `error_message`)
    - Normalizes `appstore_id` on write: `NULLIF(BTRIM(%s), '')`

- Sender (reads from `creatives_fresh`, marks rows syncing/synced):
  - `send_incoming_creative.py` (production)
  - `send_incoming_creative_localhost.py` (local testing)
    - Filters eligible rows: `status IN ('completed','sync_failed') AND (sync IS NOT TRUE) AND appstore_id IS NOT NULL`
    - Orders by `created_at` LIMIT N, `FOR UPDATE SKIP LOCKED`
    - Uses partial index `idx_cf_sync_ready_created_at_v2`

- Advertisers import (BigQuery → GCS → Postgres):
  - `creatives_bigquery_postgres.py` (end-to-end pipeline)
  - `export_bigquery_advertisers.py` / `advertisers_bigquery_postgres.py` (supporting)

- Daily creatives upsert (BigQuery creatives dump → Postgres):
  - `import_creatives_daily_upsert.py`
    - Normalizes CSV to two columns (`creative_id,advertiser_id`)
    - `CREATE TEMP TABLE staging ...` + `COPY`
    - `INSERT ... ON CONFLICT (creative_id) DO UPDATE SET advertiser_id=EXCLUDED.advertiser_id, created_at=NOW()`
    - Does not modify `status` on conflict

## Concurrency model

- Claims and sender both use `SELECT ... FOR UPDATE SKIP LOCKED` to avoid double-work. Locks are row-level and short-lived.
- Using FIFO (`ORDER BY created_at`) allows index scans to fetch LIMIT N quickly without random sorts.
- The daily upsert may occasionally wait on a locked row; it proceeds automatically once the holder commits (no deadlocks expected due to consistent per-row locking).

## Performance principles adopted

- Avoid `ORDER BY RANDOM()`; use index-friendly order (FIFO via `created_at`).
- Prefer partial indexes that match hot predicates exactly.
- Normalize values on write to avoid function calls in WHERE (e.g., `NULLIF(BTRIM(%s), '')` → lets us use `appstore_id IS NOT NULL`).
- Keep hot table slim; results fields remain but consider splitting if row size grows.
- Bloat control: adjust autovacuum thresholds and fillfactor for frequent updates.

## Safety rules for future changes

- If introducing a partial index, ensure the query WHERE implies the index predicate exactly.
  - Example: Query `(sync IS NOT TRUE)` implies predicate `(sync IS NOT TRUE)`; it does not imply `(NOT sync)` if NULLs are involved.
- Avoid functional predicates in WHERE (e.g., `btrim(appstore_id)`) unless the predicate is mirrored in a functional index or data is normalized.
- Maintain `ON CONFLICT (creative_id)` upsert policy: update only `advertiser_id, created_at`; do not change `status`.
- Keep transactions small around claims/updates; commit promptly to release row locks.

## Common verification snippets

- Claim performance (read-only EXPLAIN):
```sql
EXPLAIN (ANALYZE,BUFFERS,TIMING)
WITH selected AS (
  SELECT id FROM creatives_fresh
  WHERE status='pending'
  ORDER BY created_at
  LIMIT 20
  FOR UPDATE SKIP LOCKED
)
UPDATE creatives_fresh cf
SET status='processing'
FROM selected s
WHERE cf.id=s.id
RETURNING cf.id;
```

- Sender performance (should use partial index):
```sql
EXPLAIN (ANALYZE,BUFFERS)
SELECT id
FROM creatives_fresh
WHERE status IN ('completed','sync_failed')
  AND (sync IS NOT TRUE)
  AND appstore_id IS NOT NULL
ORDER BY created_at
LIMIT 50;
```

- Daily upsert (transactional skeleton):
```sql
CREATE TEMP TABLE staging_daily_creatives(creative_id TEXT, advertiser_id TEXT) ON COMMIT DROP;
-- COPY into staging
INSERT INTO creatives_fresh(creative_id, advertiser_id)
SELECT creative_id, advertiser_id
FROM staging_daily_creatives
ON CONFLICT (creative_id)
DO UPDATE SET advertiser_id = EXCLUDED.advertiser_id,
              created_at    = NOW();
```

## Glossary of key files
- `setup_database.py`: creates base tables and general indexes.
- `stress_test_scraper_optimized.py`: claims work, writes results, normalizes `appstore_id`.
- `send_incoming_creative.py`: claims and sends to production API.
- `send_incoming_creative_localhost.py`: local variant of the sender.
- `creatives_bigquery_postgres.py`: advertisers pipeline (BigQuery → GCS → Postgres).
- `import_creatives_daily_upsert.py`: daily creatives upsert using staging and ON CONFLICT.

## Change checklist
- [ ] Query WHERE matches any partial index predicate exactly
- [ ] No functional predicates blocking index usage
- [ ] Upserts don’t change `status`
- [ ] Concurrency preserved (`FOR UPDATE SKIP LOCKED`, quick commits)
- [ ] EXPLAIN checked for index usage and low filtered rows


