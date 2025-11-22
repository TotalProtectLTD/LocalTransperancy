#!/usr/bin/env python3
"""
Query Singapore Advertisers with App Store ID Creatives

This script queries the database to find all Singapore advertisers
that have creatives with App Store IDs.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import sys

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432
}

def query_singapore_advertisers_with_appstore():
    """Query Singapore advertisers that have creatives with App Store IDs."""
    
    query = """
    SELECT DISTINCT
        a.advertiser_id,
        a.advertiser_name,
        COUNT(DISTINCT cf.creative_id) as creative_count,
        COUNT(DISTINCT cf.appstore_id) as unique_appstore_ids
    FROM advertisers a
    INNER JOIN creatives_fresh cf ON a.advertiser_id = cf.advertiser_id
    WHERE a.country = 'SG'
      AND cf.appstore_id IS NOT NULL
      AND cf.appstore_id != ''
    GROUP BY a.advertiser_id, a.advertiser_name
    ORDER BY a.advertiser_name;
    """
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("=" * 80)
        print("Singapore Advertisers with App Store ID Creatives")
        print("=" * 80)
        print()
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        if not results:
            print("No Singapore advertisers found with App Store ID creatives.")
            return
        
        print(f"Found {len(results)} Singapore advertiser(s):\n")
        print(f"{'Advertiser Name':<50} {'ID':<20} {'Creatives':<12} {'App Store IDs':<15}")
        print("-" * 100)
        
        total_creatives = 0
        total_appstore_ids = 0
        
        for row in results:
            advertiser_name = row['advertiser_name'] or 'N/A'
            advertiser_id = row['advertiser_id'] or 'N/A'
            creative_count = row['creative_count'] or 0
            appstore_count = row['unique_appstore_ids'] or 0
            
            # Truncate long names
            if len(advertiser_name) > 48:
                advertiser_name = advertiser_name[:45] + "..."
            
            print(f"{advertiser_name:<50} {advertiser_id:<20} {creative_count:<12} {appstore_count:<15}")
            
            total_creatives += creative_count
            total_appstore_ids += appstore_count
        
        print("-" * 100)
        print(f"{'TOTAL':<50} {'':<20} {total_creatives:<12} {total_appstore_ids:<15}")
        print()
        print(f"Summary:")
        print(f"  - Advertisers: {len(results)}")
        print(f"  - Total Creatives: {total_creatives}")
        print(f"  - Unique App Store IDs: {total_appstore_ids}")
        
        cursor.close()
        conn.close()
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    query_singapore_advertisers_with_appstore()


