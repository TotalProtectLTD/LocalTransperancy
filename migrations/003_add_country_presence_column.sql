-- Add country_presence JSONB to creatives_fresh (nullable, no index)
ALTER TABLE creatives_fresh
ADD COLUMN IF NOT EXISTS country_presence JSONB;


