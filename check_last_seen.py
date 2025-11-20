#!/usr/bin/env python3
"""
Check last_seen for specific creative IDs
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import json

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432,
}

try:
    from bigquery_creatives_postgres import DB_CONFIG as _BQ_DB_CONFIG
    DB_CONFIG = _BQ_DB_CONFIG
except Exception:
    pass

# Creative IDs to check
creative_ids = [
    "CR01903331851192238081",
    "CR05713135793145380865",
    "CR05778729908079427585",
    "CR06396384413273292801",
    "CR08985084485313757185",
    "CR10447968763151122433",
    "CR10455369026161868801",
    "CR11878435589910953985",
    "CR15132313258721017857"
]

def check_creatives():
    """Check last_seen and other info for the given creative IDs."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # First, check if there's a last_seen column in creatives_fresh
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'creatives_fresh' 
            AND column_name LIKE '%last%seen%' OR column_name LIKE '%last_seen%'
        """)
        last_seen_columns = cursor.fetchall()
        
        print("Checking for last_seen columns...")
        if last_seen_columns:
            print(f"Found columns: {[c['column_name'] for c in last_seen_columns]}")
        else:
            print("No last_seen column found in creatives_fresh table")
        
        # Check all columns in creatives_fresh
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'creatives_fresh'
            ORDER BY ordinal_position
        """)
        all_columns = cursor.fetchall()
        print(f"\nAll columns in creatives_fresh: {[c['column_name'] for c in all_columns]}")
        
        # Query creatives_fresh for these IDs
        placeholders = ','.join(['%s'] * len(creative_ids))
        query = f"""
            SELECT 
                creative_id,
                advertiser_id,
                status,
                scraped_at,
                created_at,
                video_count,
                appstore_id,
                funded_by,
                country_presence
            FROM creatives_fresh
            WHERE creative_id IN ({placeholders})
            ORDER BY creative_id
        """
        
        cursor.execute(query, creative_ids)
        results = cursor.fetchall()
        
        print(f"\n{'='*80}")
        print(f"Found {len(results)} out of {len(creative_ids)} creative IDs in creatives_fresh:")
        print(f"{'='*80}\n")
        
        found_ids = {r['creative_id'] for r in results}
        missing_ids = set(creative_ids) - found_ids
        
        for result in results:
            print(f"Creative ID: {result['creative_id']}")
            print(f"  Advertiser ID: {result['advertiser_id']}")
            print(f"  Status: {result['status']}")
            print(f"  Created at: {result['created_at']}")
            print(f"  Scraped at: {result['scraped_at']}")
            print(f"  Video count: {result['video_count']}")
            print(f"  App Store ID: {result['appstore_id']}")
            print(f"  Funded by: {result['funded_by']}")
            if result['country_presence']:
                print(f"  Country presence: {json.dumps(result['country_presence'], indent=4)}")
            print()
        
        if missing_ids:
            print(f"\nMissing creative IDs (not found in creatives_fresh):")
            for cid in sorted(missing_ids):
                print(f"  - {cid}")
        
        # Also check the legacy creatives table
        cursor.execute(f"""
            SELECT 
                creative_id,
                advertiser_id,
                status,
                scraped_at,
                created_at,
                updated_at
            FROM creatives
            WHERE creative_id IN ({placeholders})
            ORDER BY creative_id
        """, creative_ids)
        legacy_results = cursor.fetchall()
        
        if legacy_results:
            print(f"\n{'='*80}")
            print(f"Also found {len(legacy_results)} in legacy 'creatives' table:")
            print(f"{'='*80}\n")
            for result in legacy_results:
                print(f"Creative ID: {result['creative_id']}")
                print(f"  Advertiser ID: {result['advertiser_id']}")
                print(f"  Status: {result['status']}")
                print(f"  Created at: {result['created_at']}")
                print(f"  Updated at: {result['updated_at']}")
                print(f"  Scraped at: {result['scraped_at']}")
                print()
        
        cursor.close()
        conn.close()
        
        print(f"\n{'='*80}")
        print("NOTE: The 'last_seen' field is likely stored on the remote API server")
        print("(https://magictransparency.com), not in the local database.")
        print("The bulk-update-creative-last-seen endpoint updates it remotely.")
        print(f"{'='*80}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_creatives()



