#!/usr/bin/env python3
"""
Reset Sync Flag to False

This script resets all rows in creatives_fresh table that have sync=TRUE
to sync=FALSE, and changes status from 'synced' to 'completed' so they can
be synced again. This is useful when you need to reprocess all rows.
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


def reset_sync_flag():
    """Reset all rows with sync=TRUE to sync=FALSE and status='synced' to 'completed'."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # First, check how many rows will be affected
                cur.execute("""
                    SELECT COUNT(*) as count
                    FROM creatives_fresh
                    WHERE sync = TRUE
                """)
                count_result = cur.fetchone()
                affected_count = count_result['count'] if count_result else 0
                
                if affected_count == 0:
                    print("✅ No rows with sync=TRUE found. Nothing to update.")
                    return
                
                print(f"📊 Found {affected_count} row(s) with sync=TRUE")
                
                # Show a preview of what will be updated
                cur.execute("""
                    SELECT id, creative_id, advertiser_id, status, sync, created_at
                    FROM creatives_fresh
                    WHERE sync = TRUE
                    ORDER BY created_at DESC
                    LIMIT 10
                """)
                preview_rows = cur.fetchall()
                
                if preview_rows:
                    print("\n📋 Preview of rows to be updated (first 10):")
                    for row in preview_rows:
                        print(f"  • ID: {row['id']}, Creative ID: {row['creative_id']}, "
                              f"Status: {row['status']}, Sync: {row['sync']}")
                
                # Update all rows: reset sync to FALSE and change 'synced' status to 'completed'
                cur.execute("""
                    UPDATE creatives_fresh
                    SET sync = FALSE,
                        status = CASE 
                            WHEN status = 'synced' THEN 'completed'
                            ELSE status
                        END
                    WHERE sync = TRUE
                """)
                
                updated_count = cur.rowcount
                conn.commit()
                
                print(f"\n✅ Successfully reset {updated_count} row(s)")
                print(f"   - sync: TRUE → FALSE")
                print(f"   - status: 'synced' → 'completed' (for rows that were synced)")
                
    except Exception as e:
        print(f"❌ Error updating rows: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("="*60)
    print("RESET SYNC FLAG TO FALSE")
    print("="*60)
    print()
    
    try:
        reset_sync_flag()
        print("\n" + "="*60)
        print("✅ OPERATION COMPLETE")
        print("="*60)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        exit(1)

