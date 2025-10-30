#!/usr/bin/env python3
"""
Verify Country Column Migration

This script verifies that the country column was successfully added to the advertisers table.
"""

import psycopg2
from psycopg2.extras import RealDictCursor

# Database configuration (same as setup_database.py)
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432
}


def verify_country_column():
    """Verify that the country column exists and is correctly configured."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("=" * 60)
        print("VERIFYING COUNTRY COLUMN MIGRATION")
        print("=" * 60)
        
        # 1. Check if table exists
        print("\n1️⃣ Checking if advertisers table exists...")
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'advertisers'
            );
        """)
        table_exists = cursor.fetchone()['exists']
        if table_exists:
            print("   ✅ advertisers table exists")
        else:
            print("   ❌ advertisers table does NOT exist")
            cursor.close()
            conn.close()
            return False
        
        # 2. Check country column
        print("\n2️⃣ Checking country column...")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = 'advertisers' 
            AND column_name = 'country';
        """)
        column_info = cursor.fetchone()
        
        if column_info:
            print(f"   ✅ country column exists")
            print(f"      - Data type: {column_info['data_type']}")
            print(f"      - Nullable: {column_info['is_nullable']}")
            print(f"      - Default: {column_info['column_default'] or 'NULL'}")
            
            # Verify it's TEXT and nullable
            if column_info['data_type'].upper() == 'TEXT' and column_info['is_nullable'] == 'YES':
                print("   ✅ Column configuration is correct (TEXT, nullable)")
            else:
                print("   ⚠️  Column configuration differs from expected")
        else:
            print("   ❌ country column does NOT exist")
            cursor.close()
            conn.close()
            return False
        
        # 3. Check country index
        print("\n3️⃣ Checking country index...")
        cursor.execute("""
            SELECT indexname, indexdef
            FROM pg_indexes 
            WHERE tablename = 'advertisers' 
            AND indexname = 'idx_advertisers_country';
        """)
        index_info = cursor.fetchone()
        
        if index_info:
            print(f"   ✅ Index exists: {index_info['indexname']}")
            print(f"      - Definition: {index_info['indexdef']}")
        else:
            print("   ❌ Index idx_advertisers_country does NOT exist")
        
        # 4. Show all columns in advertisers table
        print("\n4️⃣ All columns in advertisers table:")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, ordinal_position
            FROM information_schema.columns 
            WHERE table_name = 'advertisers' 
            ORDER BY ordinal_position;
        """)
        columns = cursor.fetchall()
        print("   Column structure:")
        for col in columns:
            nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
            print(f"      {col['ordinal_position']}. {col['column_name']}: {col['data_type']} ({nullable})")
        
        # 5. Show table statistics
        print("\n5️⃣ Table statistics:")
        cursor.execute("SELECT COUNT(*) as total FROM advertisers")
        total = cursor.fetchone()['total']
        print(f"   Total rows: {total:,}")
        
        if total > 0:
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_with_country,
                    COUNT(country) as non_null_country,
                    COUNT(*) - COUNT(country) as null_country
                FROM advertisers
            """)
            stats = cursor.fetchone()
            print(f"   Rows with country: {stats['non_null_country']:,}")
            print(f"   Rows without country (NULL): {stats['null_country']:,}")
            
            # Show sample country values
            cursor.execute("""
                SELECT DISTINCT country, COUNT(*) as count
                FROM advertisers
                WHERE country IS NOT NULL
                GROUP BY country
                ORDER BY count DESC
                LIMIT 10;
            """)
            countries = cursor.fetchall()
            if countries:
                print("\n   Top countries (sample):")
                for country in countries:
                    print(f"      {country['country']}: {country['count']:,} advertisers")
        
        # 6. Show all indexes on advertisers table
        print("\n6️⃣ All indexes on advertisers table:")
        cursor.execute("""
            SELECT indexname, indexdef
            FROM pg_indexes 
            WHERE tablename = 'advertisers'
            ORDER BY indexname;
        """)
        indexes = cursor.fetchall()
        for idx in indexes:
            print(f"      • {idx['indexname']}")
        
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 60)
        print("✅ VERIFICATION COMPLETE")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ Error during verification: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    verify_country_column()

