#!/usr/bin/env python3
"""
BigQuery to PostgreSQL Import Script
Downloads CSV data from BigQuery and imports it into creatives_fresh table
"""

import os
import sys
import csv
import tempfile
from datetime import datetime
import psycopg2
from google.cloud import bigquery
from google.cloud import storage

# Configuration
BIGQUERY_PROJECT_ID = "youtubeilike"
BUCKET_NAME = "youtubeilike-temp-exports"
FILE_NAME = "October"  # Default file name, can be overridden
CREDENTIALS_PATH = "/Users/rostoni/Downloads/CursorTransperancy/backend/bigquery-credentials.json"

# PostgreSQL configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432
}

def setup_environment():
    """Set up environment variables for Google Cloud."""
    if os.path.exists(CREDENTIALS_PATH):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = CREDENTIALS_PATH
        print(f"✅ Using credentials from: {CREDENTIALS_PATH}")
    else:
        print(f"⚠️  Credentials file not found: {CREDENTIALS_PATH}")
        print("   Make sure the file exists or set GOOGLE_APPLICATION_CREDENTIALS manually")
        return False
    
    os.environ['BIGQUERY_PROJECT_ID'] = BIGQUERY_PROJECT_ID
    return True

def download_csv_from_bucket(file_name=None):
    """Download CSV file from Google Cloud Storage bucket."""
    if file_name is None:
        file_name = FILE_NAME
    
    try:
        # Initialize Google Cloud Storage client
        storage_client = storage.Client(project=BIGQUERY_PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        
        # Look for CSV files with the given name
        csv_files = []
        for blob in bucket.list_blobs():
            # Check for exact match first, then prefix match
            if (blob.name == file_name or 
                blob.name == f"{file_name}.csv" or 
                (blob.name.startswith(file_name) and blob.name.endswith('.csv'))):
                csv_files.append(blob.name)
        
        if not csv_files:
            print(f"❌ No CSV files found with prefix '{file_name}' in bucket '{BUCKET_NAME}'")
            print("Available files:")
            for blob in bucket.list_blobs():
                print(f"  • {blob.name}")
            return None
        
        # Use the first matching file
        csv_file = csv_files[0]
        print(f"📥 Downloading: {csv_file}")
        
        # Download to temporary file
        blob = bucket.blob(csv_file)
        temp_file = tempfile.NamedTemporaryFile(mode='w+', suffix='.csv', delete=False)
        blob.download_to_filename(temp_file.name)
        
        print(f"✅ Downloaded to: {temp_file.name}")
        return temp_file.name
        
    except Exception as e:
        print(f"❌ Error downloading CSV: {e}")
        return None

def import_csv_to_postgres(csv_file_path):
    """Import CSV data into PostgreSQL creatives_fresh table."""
    
    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print(f"📊 Importing data from: {csv_file_path}")
        
        # Read CSV and prepare data
        imported_count = 0
        skipped_count = 0
        
        with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
            # Try to detect delimiter
            sample = csvfile.read(1024)
            csvfile.seek(0)
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample).delimiter
            
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            
            print(f"📋 CSV columns detected: {reader.fieldnames}")
            
            for row_num, row in enumerate(reader, 1):
                try:
                    # Extract creative_id and advertiser_id
                    creative_id = row.get('creative_id', '').strip()
                    advertiser_id = row.get('advertiser_id', '').strip()
                    
                    if not creative_id or not advertiser_id:
                        print(f"⚠️  Row {row_num}: Missing creative_id or advertiser_id, skipping")
                        skipped_count += 1
                        continue
                    
                    # Check if record already exists
                    cursor.execute(
                        "SELECT id FROM creatives_fresh WHERE creative_id = %s AND advertiser_id = %s",
                        (creative_id, advertiser_id)
                    )
                    
                    if cursor.fetchone():
                        print(f"⚠️  Row {row_num}: Record already exists (creative_id: {creative_id}), skipping")
                        skipped_count += 1
                        continue
                    
                    # Insert new record
                    insert_sql = """
                    INSERT INTO creatives_fresh 
                    (creative_id, advertiser_id, status, created_at)
                    VALUES (%s, %s, 'pending', CURRENT_TIMESTAMP)
                    """
                    
                    cursor.execute(insert_sql, (creative_id, advertiser_id))
                    imported_count += 1
                    
                    if imported_count % 100 == 0:
                        print(f"  📈 Imported {imported_count} records...")
                        
                except Exception as e:
                    print(f"❌ Error processing row {row_num}: {e}")
                    skipped_count += 1
                    continue
        
        # Commit changes
        conn.commit()
        
        # Get final count
        cursor.execute("SELECT COUNT(*) FROM creatives_fresh")
        total_count = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        print(f"\n✅ Import completed!")
        print(f"📊 Imported: {imported_count} new records")
        print(f"⚠️  Skipped: {skipped_count} records")
        print(f"📈 Total records in creatives_fresh: {total_count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error importing to PostgreSQL: {e}")
        return False

def cleanup_temp_file(file_path):
    """Clean up temporary file."""
    try:
        os.unlink(file_path)
        print(f"🗑️  Cleaned up temporary file: {file_path}")
    except Exception as e:
        print(f"⚠️  Could not clean up temp file: {e}")

def main():
    """Main function."""
    print("="*60)
    print("BIGQUERY TO POSTGRESQL IMPORT")
    print("="*60)
    
    # Check command line arguments
    file_name = FILE_NAME
    if len(sys.argv) > 1:
        file_name = sys.argv[1]
        print(f"📁 Using custom file name: {file_name}")
    
    # Setup environment
    if not setup_environment():
        sys.exit(1)
    
    # Download CSV from bucket
    csv_file = download_csv_from_bucket(file_name)
    if not csv_file:
        sys.exit(1)
    
    try:
        # Import to PostgreSQL
        if import_csv_to_postgres(csv_file):
            print(f"\n🎉 Import successful!")
        else:
            print(f"\n❌ Import failed!")
            sys.exit(1)
    
    finally:
        # Cleanup
        cleanup_temp_file(csv_file)
    
    print("\n" + "="*60)
    print("✅ IMPORT COMPLETE!")
    print("="*60)
    print(f"\nNext steps:")
    print(f"1. Check data: python3 -c \"import psycopg2; conn = psycopg2.connect(host='localhost', database='local_transparency', user='transparency_user', password='transparency_pass_2025', port=5432); cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM creatives_fresh'); print('Total records:', cursor.fetchone()[0]); conn.close()\"")
    print(f"2. Start scraping: python3 google_ads_transparency_scraper.py --help")

if __name__ == "__main__":
    main()
