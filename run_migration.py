#!/usr/bin/env python3
"""
Safe Migration Runner

This script safely runs database migrations.
It will NOT touch existing tables or data unless explicitly required.
Usage: python3 run_migration.py [migration_number]
Example: python3 run_migration.py 002
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


def run_migration(migration_number: str = '001'):
    """
    Run a specific migration.
    
    Args:
        migration_number: Migration number (e.g., '001', '002')
    """
    migration_file = Path(__file__).parent / 'migrations' / f'{migration_number}_*.sql'
    
    # Find migration file with the given number
    migrations_dir = Path(__file__).parent / 'migrations'
    matching_files = list(migrations_dir.glob(f'{migration_number}_*.sql'))
    
    if not matching_files:
        print(f"❌ Migration file not found for number: {migration_number}")
        print(f"   Searched in: {migrations_dir}")
        return False
    
    migration_file = matching_files[0]
    print(f"\n📄 Reading migration file: {migration_file.name}")
    
    # Read migration SQL
    try:
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
    except Exception as e:
        print(f"❌ Error reading migration file: {e}")
        return False
    
    # Migration-specific checks
    if migration_number == '001':
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
    elif migration_number == '002':
        # Verify advertisers table exists (required for migration 002)
        if not verify_table_exists('advertisers'):
            print("\n❌ ERROR: advertisers table does not exist!")
            print("   Please run migration 001 first.")
            return False
        print("✅ advertisers table exists - safe to add country column")
    
    # Run migration
    print("\n🔄 Running migration...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Execute migration SQL
        cursor.execute(migration_sql)
        conn.commit()
        
        print("✅ Migration completed successfully!")
        
        # Migration-specific verification
        if migration_number == '001':
            # Verify table was created
            if verify_table_exists('advertisers'):
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
        elif migration_number == '002':
            # Verify country column was added
            cursor.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = 'advertisers' 
                AND column_name = 'country';
            """)
            column_info = cursor.fetchone()
            if column_info:
                print(f"   ✅ country column added: {column_info[0]} ({column_info[1]}, nullable: {column_info[2]})")
            
            # Verify index was created
            cursor.execute("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'advertisers' 
                AND indexname = 'idx_advertisers_country';
            """)
            index_info = cursor.fetchone()
            if index_info:
                print(f"   ✅ Index created: {index_info[0]}")
        
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
    # Get migration number from command line args, default to 001
    migration_number = sys.argv[1] if len(sys.argv) > 1 else '001'
    
    migration_descriptions = {
        '001': 'Create Advertisers Table',
        '002': 'Add Country Column to Advertisers Table'
    }
    
    description = migration_descriptions.get(migration_number, f'Migration {migration_number}')
    
    print("=" * 60)
    print(f"SAFE MIGRATION: {description}")
    print("=" * 60)
    print("\nThis script will:")
    print("  ✅ Run migration safely")
    print("  ✅ NOT modify creatives_fresh or any other tables unnecessarily")
    print("  ✅ NOT drop or alter existing data")
    print("  ✅ Use IF NOT EXISTS / IF NOT EXISTS - safe to run multiple times")
    
    # Test connection
    if not test_connection():
        print("\n❌ Cannot connect to database.")
        sys.exit(1)
    
    # Run migration
    if run_migration(migration_number):
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
