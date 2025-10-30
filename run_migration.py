#!/usr/bin/env python3
"""
Safe Migration Runner - Create Advertisers Table Only

This script safely runs ONLY the advertisers table migration.
It will NOT touch existing tables or data.
"""

import psycopg2
import sys
from pathlib import Path

# Database configuration (same as setup_database.py)
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432
}


def test_connection():
    """Test database connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✅ Connected to: {version}")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def verify_table_exists(table_name: str) -> bool:
    """Check if a table already exists."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %s
            );
        """, (table_name,))
        exists = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return exists
    except Exception as e:
        print(f"⚠️  Error checking table existence: {e}")
        return False


def verify_creatives_fresh_safe():
    """Verify creatives_fresh table exists and is safe."""
    print("\n🛡️  Verifying data safety...")
    
    if not verify_table_exists('creatives_fresh'):
        print("⚠️  Warning: creatives_fresh table not found. This is unexpected.")
        response = input("Continue anyway? (yes/no): ")
        if response.lower() != 'yes':
            return False
    else:
        # Count rows to verify table is accessible
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM creatives_fresh")
            count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            print(f"✅ creatives_fresh table verified: {count:,} rows")
        except Exception as e:
            print(f"⚠️  Could not verify creatives_fresh: {e}")
            response = input("Continue anyway? (yes/no): ")
            if response.lower() != 'yes':
                return False
    
    return True


def run_migration():
    """Run the advertisers table migration."""
    migration_file = Path(__file__).parent / 'migrations' / '001_create_advertisers_table.sql'
    
    if not migration_file.exists():
        print(f"❌ Migration file not found: {migration_file}")
        return False
    
    print(f"\n📄 Reading migration file: {migration_file.name}")
    
    # Read migration SQL
    try:
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
    except Exception as e:
        print(f"❌ Error reading migration file: {e}")
        return False
    
    # Check if advertisers table already exists
    if verify_table_exists('advertisers'):
        print("\n⚠️  WARNING: advertisers table already exists!")
        print("   This migration will be skipped (uses IF NOT EXISTS)")
        print("   Your existing data in advertisers table is safe.")
        response = input("\nContinue anyway? (yes/no): ")
        if response.lower() != 'yes':
            return False
    
    # Verify creatives_fresh is safe
    if not verify_creatives_fresh_safe():
        print("\n❌ Migration cancelled for safety.")
        return False
    
    # Run migration
    print("\n🔄 Running migration...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Execute migration SQL
        cursor.execute(migration_sql)
        conn.commit()
        
        # Verify table was created
        if verify_table_exists('advertisers'):
            print("✅ Migration completed successfully!")
            
            # Get table info
            cursor.execute("""
                SELECT COUNT(*) FROM advertisers
            """)
            count = cursor.fetchone()[0]
            print(f"   advertisers table created with {count} row(s)")
            
            # Show indexes
            cursor.execute("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'advertisers'
                ORDER BY indexname;
            """)
            indexes = cursor.fetchall()
            print(f"   Indexes created: {len(indexes)}")
            for idx in indexes:
                print(f"     • {idx[0]}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        if conn:
            conn.rollback()
        return False


def main():
    """Main function."""
    print("=" * 60)
    print("SAFE MIGRATION: Create Advertisers Table")
    print("=" * 60)
    print("\nThis script will:")
    print("  ✅ Create ONLY the advertisers table")
    print("  ✅ NOT modify creatives_fresh or any other tables")
    print("  ✅ NOT drop or alter any existing data")
    print("  ✅ Use IF NOT EXISTS - safe to run multiple times")
    
    # Test connection
    if not test_connection():
        print("\n❌ Cannot connect to database.")
        sys.exit(1)
    
    # Run migration
    if run_migration():
        print("\n" + "=" * 60)
        print("✅ MIGRATION COMPLETE!")
        print("=" * 60)
        print("\nNext steps:")
        print("  1. Verify: python3 advertiser_utils.py")
        print("  2. Populate data: Use batch_insert_advertisers() function")
        print("  3. Check statistics: get_statistics() from advertiser_utils")
    else:
        print("\n" + "=" * 60)
        print("❌ MIGRATION FAILED OR CANCELLED")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
