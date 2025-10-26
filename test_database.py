#!/usr/bin/env python3
"""
Database Test Script - Local Transparency

Test database connection and basic operations.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432
}

def test_connection():
    """Test basic database connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✅ Database connection successful!")
        print(f"📊 PostgreSQL version: {version}")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

def test_tables():
    """Test table existence and structure."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        
        tables = [row['table_name'] for row in cursor.fetchall()]
        print(f"\n📋 Tables found: {len(tables)}")
        for table in tables:
            print(f"  • {table}")
        
        cursor.close()
        conn.close()
        return len(tables) > 0
        
    except Exception as e:
        print(f"❌ Table check failed: {e}")
        return False

def test_insert_sample():
    """Test inserting sample data."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Insert sample creative
        sample_data = {
            'creative_id': 'CR12345678901234567890',
            'advertiser_id': 'AR12345678901234567890',
            'url': 'https://adstransparency.google.com/advertiser/AR12345678901234567890/creative/CR12345678901234567890',
            'status': 'completed',
            'video_count': 2,
            'video_ids': json.dumps(['dQw4w9WgXcQ', 'jNQXAC9IVRw']),
            'appstore_id': '1234567890',
            'scraped_at': datetime.now()
        }
        
        cursor.execute("""
            INSERT INTO creatives (creative_id, advertiser_id, url, status, video_count, video_ids, appstore_id, scraped_at)
            VALUES (%(creative_id)s, %(advertiser_id)s, %(url)s, %(status)s, %(video_count)s, %(video_ids)s, %(appstore_id)s, %(scraped_at)s)
            ON CONFLICT (creative_id) DO NOTHING
        """, sample_data)
        
        conn.commit()
        print(f"✅ Sample data inserted successfully")
        
        # Verify insertion
        cursor.execute("SELECT COUNT(*) FROM creatives WHERE creative_id = %s", (sample_data['creative_id'],))
        count = cursor.fetchone()[0]
        print(f"📊 Records with test creative ID: {count}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Sample insert failed: {e}")
        return False

def test_query_sample():
    """Test querying sample data."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query sample data
        cursor.execute("""
            SELECT creative_id, status, video_count, video_ids, appstore_id, created_at
            FROM creatives 
            WHERE creative_id = 'CR12345678901234567890'
            LIMIT 1
        """)
        
        result = cursor.fetchone()
        if result:
            print(f"\n📋 Sample record found:")
            print(f"  • Creative ID: {result['creative_id']}")
            print(f"  • Status: {result['status']}")
            print(f"  • Video Count: {result['video_count']}")
            print(f"  • Video IDs: {result['video_ids']}")
            print(f"  • App Store ID: {result['appstore_id']}")
            print(f"  • Created: {result['created_at']}")
        else:
            print(f"⚠️  No sample record found")
        
        cursor.close()
        conn.close()
        return result is not None
        
    except Exception as e:
        print(f"❌ Sample query failed: {e}")
        return False

def test_json_operations():
    """Test JSONB operations."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Test JSONB query
        cursor.execute("""
            SELECT creative_id, video_ids
            FROM creatives 
            WHERE video_ids ? 'dQw4w9WgXcQ'
            LIMIT 1
        """)
        
        result = cursor.fetchone()
        if result:
            print(f"✅ JSONB query successful")
            print(f"  • Found creative with video: {result[0]}")
        else:
            print(f"⚠️  No records found with JSONB query")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ JSONB test failed: {e}")
        return False

def cleanup_sample_data():
    """Clean up sample data."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM creatives WHERE creative_id = 'CR12345678901234567890'")
        conn.commit()
        
        print(f"🧹 Sample data cleaned up")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"⚠️  Cleanup failed: {e}")
        return False

if __name__ == "__main__":
    print("="*60)
    print("LOCAL TRANSPARENCY - DATABASE TEST")
    print("="*60)
    
    tests = [
        ("Connection Test", test_connection),
        ("Tables Test", test_tables),
        ("Insert Sample", test_insert_sample),
        ("Query Sample", test_query_sample),
        ("JSONB Operations", test_json_operations),
        ("Cleanup", cleanup_sample_data)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🧪 Running: {test_name}")
        if test_func():
            passed += 1
        else:
            print(f"❌ {test_name} failed")
    
    print(f"\n" + "="*60)
    print(f"TEST RESULTS: {passed}/{total} tests passed")
    print("="*60)
    
    if passed == total:
        print("✅ All tests passed! Database is ready for use.")
        print("\nNext steps:")
        print("1. Start scraping: python3 google_ads_transparency_scraper.py --help")
        print("2. Check DATABASE_CONFIG.md for connection details")
    else:
        print("❌ Some tests failed. Check database setup.")
        print("Run: python3 setup_database.py")
