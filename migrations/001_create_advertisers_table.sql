-- =============================================================================
-- Migration: Create Advertisers Lookup Table
-- =============================================================================
-- Purpose: Create efficient lookup table for advertiser ID ↔ name conversions
--          Supports 3.5M+ rows with fast bidirectional lookups
-- =============================================================================
-- Date: 2025-01-XX
-- Safe: Does NOT modify creatives_fresh table
-- =============================================================================

-- Create advertisers table with minimal structure
CREATE TABLE IF NOT EXISTS advertisers (
    advertiser_id TEXT PRIMARY KEY,
    advertiser_name TEXT NOT NULL,
    advertiser_name_normalized TEXT
);

-- Create index on advertiser_name for name → ID lookups (not unique - multiple IDs can have same name)
CREATE INDEX IF NOT EXISTS idx_advertisers_name 
ON advertisers(advertiser_name);

-- Create index on normalized name for case-insensitive funded_by matching
CREATE INDEX IF NOT EXISTS idx_advertisers_name_normalized 
ON advertisers(advertiser_name_normalized);

-- Add comment to table
COMMENT ON TABLE advertisers IS 'Lookup table for advertiser ID ↔ name conversions. Supports fast bidirectional lookups for 3.5M+ rows.';
COMMENT ON COLUMN advertisers.advertiser_id IS 'Primary key: Advertiser ID (TEXT)';
COMMENT ON COLUMN advertisers.advertiser_name IS 'Advertiser name (not unique - multiple IDs can share same name)';
COMMENT ON COLUMN advertisers.advertiser_name_normalized IS 'Normalized advertiser name (lowercase, trimmed) for case-insensitive matching';

-- =============================================================================
-- Verification Queries (run these after migration to verify)
-- =============================================================================
-- 
-- SELECT table_name 
-- FROM information_schema.tables 
-- WHERE table_schema = 'public' 
-- AND table_name = 'advertisers';
--
-- SELECT indexname, indexdef 
-- FROM pg_indexes 
-- WHERE tablename = 'advertisers';
--
-- =============================================================================
