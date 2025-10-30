-- =============================================================================
-- Migration: Add Country Column to Advertisers Table
-- =============================================================================
-- Purpose: Add country code column (e.g., US, CA, FR) to advertisers table
--          for geographic filtering and analysis
-- =============================================================================
-- Date: 2025-01-XX
-- Safe: Only adds a new nullable column - no data loss
-- =============================================================================

-- Add country column (nullable to support existing data)
ALTER TABLE advertisers 
ADD COLUMN IF NOT EXISTS country TEXT;

-- Create index on country for filtering and analysis
CREATE INDEX IF NOT EXISTS idx_advertisers_country 
ON advertisers(country);

-- Add comment to column
COMMENT ON COLUMN advertisers.country IS 'Country code (e.g., US, CA, FR) for advertiser location';

-- =============================================================================
-- Verification Queries (run these after migration to verify)
-- =============================================================================
-- 
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns 
-- WHERE table_name = 'advertisers' 
-- AND column_name = 'country';
--
-- SELECT indexname 
-- FROM pg_indexes 
-- WHERE tablename = 'advertisers' 
-- AND indexname = 'idx_advertisers_country';
--
-- =============================================================================

