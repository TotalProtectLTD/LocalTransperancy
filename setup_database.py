#!/usr/bin/env python3
"""
Database Schema Setup - Local Transparency

This script creates the database tables and indexes for the Local Transparency project.
Run this after creating the database and user.
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

def create_tables():
    """Create all database tables and indexes."""
    
    # SQL commands to create tables
    sql_commands = [
        # Main creatives table
        """
        CREATE TABLE IF NOT EXISTS creatives (
            id SERIAL PRIMARY KEY,
            creative_id TEXT UNIQUE NOT NULL,
            advertiser_id TEXT,
            url TEXT,
            status TEXT DEFAULT 'pending',
            video_count INTEGER DEFAULT 0,
            video_ids JSONB,
            appstore_id TEXT,
            funded_by TEXT DEFAULT NULL,
            sync BOOLEAN DEFAULT FALSE,
            scraped_at TIMESTAMP,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        
        # Scraping sessions table
        """
        CREATE TABLE IF NOT EXISTS scraping_sessions (
            id SERIAL PRIMARY KEY,
            session_name TEXT,
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_time TIMESTAMP,
            total_urls INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running'
        );
        """,
        
        # Detailed logs table
        """
        CREATE TABLE IF NOT EXISTS scraping_logs (
            id SERIAL PRIMARY KEY,
            session_id INTEGER REFERENCES scraping_sessions(id),
            creative_id TEXT,
            url TEXT,
            status TEXT,
            video_count INTEGER DEFAULT 0,
            video_ids JSONB,
            appstore_id TEXT,
            duration_ms INTEGER,
            error_message TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        
        # Creatives fresh table
        """
        CREATE TABLE IF NOT EXISTS creatives_fresh (
            id SERIAL PRIMARY KEY,
            creative_id TEXT NOT NULL,
            advertiser_id TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            video_count INTEGER DEFAULT 0,
            video_ids TEXT,
            appstore_id TEXT,
            funded_by TEXT DEFAULT NULL,
            sync BOOLEAN DEFAULT FALSE,
            scraped_at TIMESTAMP,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        
        # Advertisers lookup table
        """
        CREATE TABLE IF NOT EXISTS advertisers (
            advertiser_id TEXT PRIMARY KEY,
            advertiser_name TEXT NOT NULL,
            advertiser_name_normalized TEXT
        );
        """,
        
        # Create indexes for performance
        """
        CREATE INDEX IF NOT EXISTS idx_creative_status ON creatives(status);
        """,
        
        """
        CREATE INDEX IF NOT EXISTS idx_creative_scraped_at ON creatives(scraped_at);
        """,
        
        """
        CREATE INDEX IF NOT EXISTS idx_creative_created_at ON creatives(created_at);
        """,
        
        """
        CREATE INDEX IF NOT EXISTS idx_logs_session_id ON scraping_logs(session_id);
        """,
        
        """
        CREATE INDEX IF NOT EXISTS idx_logs_status ON scraping_logs(status);
        """,
        
        """
        CREATE INDEX IF NOT EXISTS idx_logs_scraped_at ON scraping_logs(scraped_at);
        """,
        
        # Indexes for creatives_fresh table
        """
        CREATE INDEX IF NOT EXISTS idx_creatives_fresh_status ON creatives_fresh(status);
        """,
        
        """
        CREATE INDEX IF NOT EXISTS idx_creatives_fresh_creative_id ON creatives_fresh(creative_id);
        """,
        
        """
        CREATE INDEX IF NOT EXISTS idx_creatives_fresh_advertiser_id ON creatives_fresh(advertiser_id);
        """,
        
        """
        CREATE INDEX IF NOT EXISTS idx_creatives_fresh_scraped_at ON creatives_fresh(scraped_at);
        """,
        
        """
        CREATE INDEX IF NOT EXISTS idx_creatives_fresh_created_at ON creatives_fresh(created_at);
        """,
        
        # Indexes for advertisers table
        """
        CREATE INDEX IF NOT EXISTS idx_advertisers_name 
        ON advertisers(advertiser_name);
        """,
        
        """
        CREATE INDEX IF NOT EXISTS idx_advertisers_name_normalized 
        ON advertisers(advertiser_name_normalized);
        """,
        
        # Create function to auto-update updated_at
        """
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
        """,
        
        # Create trigger for updated_at
        """
        DROP TRIGGER IF EXISTS update_creatives_updated_at ON creatives;
        CREATE TRIGGER update_creatives_updated_at 
            BEFORE UPDATE ON creatives 
            FOR EACH ROW 
            EXECUTE FUNCTION update_updated_at_column();
        """
    ]
    
    try:
        # Connect to database
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print("🔧 Creating database tables and indexes...")
        
        # Execute each SQL command
        for i, sql in enumerate(sql_commands, 1):
            try:
                cursor.execute(sql)
                print(f"  ✅ Step {i}/{len(sql_commands)} completed")
            except Exception as e:
                print(f"  ⚠️  Step {i} warning: {e}")
        
        # Commit changes
        conn.commit()
        
        # Verify tables were created
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        
        tables = cursor.fetchall()
        print(f"\n📊 Created tables:")
        for table in tables:
            print(f"  • {table[0]}")
        
        # Check indexes
        cursor.execute("""
            SELECT indexname, tablename 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
            ORDER BY tablename, indexname;
        """)
        
        indexes = cursor.fetchall()
        print(f"\n🔍 Created indexes:")
        for index in indexes:
            print(f"  • {index[1]}.{index[0]}")
        
        cursor.close()
        conn.close()
        
        print(f"\n✅ Database schema setup complete!")
        print(f"📊 Tables: {len(tables)}")
        print(f"🔍 Indexes: {len(indexes)}")
        
    except Exception as e:
        print(f"❌ Error setting up database: {e}")
        sys.exit(1)

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

def show_sample_data():
    """Show sample data structure."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Show table structures
        tables = ['creatives', 'scraping_sessions', 'scraping_logs', 'creatives_fresh', 'advertisers']
        
        for table in tables:
            cursor.execute(f"""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = '{table}' 
                ORDER BY ordinal_position;
            """)
            
            columns = cursor.fetchall()
            print(f"\n📋 Table: {table}")
            for col in columns:
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                default = f" DEFAULT {col['column_default']}" if col['column_default'] else ""
                print(f"  • {col['column_name']}: {col['data_type']} {nullable}{default}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"⚠️  Could not show table structure: {e}")

if __name__ == "__main__":
    print("="*60)
    print("LOCAL TRANSPARENCY - DATABASE SCHEMA SETUP")
    print("="*60)
    
    # Test connection first
    if not test_connection():
        print("❌ Cannot connect to database. Check DATABASE_CONFIG.md")
        sys.exit(1)
    
    # Create tables
    create_tables()
    
    # Show structure
    show_sample_data()
    
    print("\n" + "="*60)
    print("✅ SETUP COMPLETE!")
    print("="*60)
    print("\nNext steps:")
    print("1. Test with: python3 test_database.py")
    print("2. Start scraping: python3 google_ads_transparency_scraper.py --help")
    print("3. Check DATABASE_CONFIG.md for connection details")
