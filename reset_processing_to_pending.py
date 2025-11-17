#!/usr/bin/env python3
"""
Reset Processing Status to Pending

This script updates all rows in creatives_fresh table that have status='processing'
to status='pending'. This is useful for resetting stuck processing rows.
"""

import psycopg2
from psycopg2.extras import RealDictCursor

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432,
}


def reset_processing_to_pending():
    """Update all rows with status='processing' to status='pending'."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # First, check how many rows will be affected
                cur.execute("""
                    SELECT COUNT(*) as count
                    FROM creatives_fresh
                    WHERE status = 'processing'
                """)
                count_result = cur.fetchone()
                affected_count = count_result['count'] if count_result else 0
                
                if affected_count == 0:
                    print("✅ No rows with status='processing' found. Nothing to update.")
                    return
                
                print(f"📊 Found {affected_count} row(s) with status='processing'")
                
                # Show a preview of what will be updated
                cur.execute("""
                    SELECT id, creative_id, advertiser_id, status, created_at
                    FROM creatives_fresh
                    WHERE status = 'processing'
                    ORDER BY created_at DESC
                    LIMIT 10
                """)
                preview_rows = cur.fetchall()
                
                if preview_rows:
                    print("\n📋 Preview of rows to be updated (first 10):")
                    for row in preview_rows:
                        print(f"  • ID: {row['id']}, Creative ID: {row['creative_id']}, "
                              f"Advertiser: {row['advertiser_id']}, Created: {row['created_at']}")
                
                # Update all rows
                cur.execute("""
                    UPDATE creatives_fresh
                    SET status = 'pending'
                    WHERE status = 'processing'
                """)
                
                updated_count = cur.rowcount
                conn.commit()
                
                print(f"\n✅ Successfully updated {updated_count} row(s) from 'processing' to 'pending'")
                
    except Exception as e:
        print(f"❌ Error updating rows: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("="*60)
    print("RESET PROCESSING STATUS TO PENDING")
    print("="*60)
    print()
    
    try:
        reset_processing_to_pending()
        print("\n" + "="*60)
        print("✅ OPERATION COMPLETE")
        print("="*60)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        exit(1)

