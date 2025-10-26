-- =============================================================================
-- ERROR ANALYSIS QUERIES FOR creatives_fresh TABLE
-- =============================================================================
-- Use these queries to understand what errors are happening in your database
-- =============================================================================

-- 1. COUNT ALL ERRORS BY TYPE
-- Shows how many of each error type you have
SELECT 
    CASE 
        WHEN status = 'completed' THEN '✅ Success'
        WHEN status = 'pending' AND error_message LIKE '%pending retry%' THEN '⟳ Retries (network/temp)'
        WHEN status = 'bad_ad' THEN '🚫 Bad ads (creative not found)'
        WHEN status = 'failed' THEN '✗ Failed (other permanent)'
        WHEN status = 'pending' AND error_message IS NULL THEN '⏳ Not processed yet'
        ELSE status
    END as error_category,
    COUNT(*) as count
FROM creatives_fresh
GROUP BY error_category
ORDER BY count DESC;

-- =============================================================================

-- 2. DETAILED VIEW OF ALL FAILED CREATIVES (NOT bad ads)
-- Shows the FULL error message for "other permanent failures"
-- This is what you asked for - to understand "unexpected" errors
SELECT 
    id,
    creative_id,
    advertiser_id,
    error_message,
    scraped_at
FROM creatives_fresh
WHERE status = 'failed' 
  AND error_message LIKE 'PERMANENT ERROR:%'
ORDER BY scraped_at DESC
LIMIT 50;

-- =============================================================================

-- 3. COUNT EACH SPECIFIC ERROR TYPE
-- Groups similar errors together
SELECT 
    error_message,
    COUNT(*) as count
FROM creatives_fresh
WHERE status = 'failed'
GROUP BY error_message
ORDER BY count DESC;

-- =============================================================================

-- 4. RECENT ERRORS (Last 100)
-- Shows recent errors with all details
SELECT 
    id,
    creative_id,
    advertiser_id,
    status,
    error_message,
    scraped_at,
    CASE 
        WHEN status = 'bad_ad' THEN '🚫 Bad ad'
        WHEN status = 'failed' THEN '✗ Failed'
        WHEN status = 'pending' AND error_message LIKE '%retry%' THEN '⟳ Retry'
        ELSE status
    END as category
FROM creatives_fresh
WHERE status IN ('failed', 'bad_ad', 'pending')
  AND error_message IS NOT NULL
ORDER BY scraped_at DESC
LIMIT 100;

-- =============================================================================

-- 5. NETWORK ERRORS THAT WILL RETRY
-- Shows all temporary network errors
SELECT 
    error_message,
    COUNT(*) as count
FROM creatives_fresh
WHERE status = 'pending'
  AND error_message LIKE '%pending retry%'
GROUP BY error_message
ORDER BY count DESC;

-- =============================================================================

-- 6. BAD ADS - Creatives that don't exist
SELECT 
    COUNT(*) as total_bad_ads,
    'These creatives were deleted or never existed' as note
FROM creatives_fresh
WHERE status = 'bad_ad';

-- =============================================================================

-- 7. FULL SUMMARY WITH PERCENTAGES
-- Overall statistics
WITH stats AS (
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
        SUM(CASE WHEN status = 'pending' AND error_message IS NULL THEN 1 ELSE 0 END) as not_processed,
        SUM(CASE WHEN status = 'pending' AND error_message LIKE '%retry%' THEN 1 ELSE 0 END) as retries,
        SUM(CASE WHEN status = 'bad_ad' THEN 1 ELSE 0 END) as bad_ads,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as permanent_errors
    FROM creatives_fresh
)
SELECT 
    'Total Creatives' as metric, 
    total as count, 
    '100%' as percentage
FROM stats
UNION ALL
SELECT 
    '✅ Completed Successfully', 
    completed, 
    ROUND(completed * 100.0 / total, 1) || '%'
FROM stats
UNION ALL
SELECT 
    '⏳ Not Processed Yet', 
    not_processed, 
    ROUND(not_processed * 100.0 / total, 1) || '%'
FROM stats
UNION ALL
SELECT 
    '⟳ Will Retry (temp errors)', 
    retries, 
    ROUND(retries * 100.0 / total, 1) || '%'
FROM stats
UNION ALL
SELECT 
    '🚫 Bad Ads (creative not found)', 
    bad_ads, 
    ROUND(bad_ads * 100.0 / total, 1) || '%'
FROM stats
UNION ALL
SELECT 
    '✗ Permanent Errors (other)', 
    permanent_errors, 
    ROUND(permanent_errors * 100.0 / total, 1) || '%'
FROM stats;

-- =============================================================================
-- HOW TO USE THESE QUERIES
-- =============================================================================
-- 
-- 1. Connect to your PostgreSQL database:
--    psql -U transparency_user -d local_transparency
--
-- 2. Run any query above to see errors
--
-- 3. Most useful queries:
--    - Query #1: Quick overview of all error types
--    - Query #2: See FULL error messages for unexpected failures
--    - Query #3: Group similar errors together
--    - Query #7: Full summary with percentages
--
-- =============================================================================
-- EXAMPLE OUTPUT (Query #2):
-- =============================================================================
--
-- id  | creative_id        | error_message                                    | scraped_at
-- ----+--------------------+--------------------------------------------------+---------------------
-- 123 | CR12345678901234   | PERMANENT ERROR: Timeout 60000ms exceeded        | 2025-10-26 14:32:10
-- 124 | CR98765432109876   | PERMANENT ERROR: Navigation timeout of 30000ms   | 2025-10-26 14:31:55
-- 125 | CR11111111111111   | PERMANENT ERROR: Page crashed                    | 2025-10-26 14:30:42
--
-- Now you can see EXACTLY what went wrong with each "unexpected" error!
--
-- =============================================================================

