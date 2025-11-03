#!/usr/bin/env python3
"""
Complete Advertisers Data Pipeline: BigQuery → GCS → PostgreSQL

This script provides an end-to-end solution for extracting advertiser data from
Google BigQuery public datasets, exporting to Google Cloud Storage (GCS), downloading
locally, and importing into PostgreSQL.

WORKFLOW OVERVIEW:
─────────────────
1. BigQuery Query: Queries the public Google Ads Transparency dataset
2. Export to GCS: Writes query results to a GCS bucket as CSV (cost-effective)
3. Download: Downloads the CSV file from GCS to local storage
4. PostgreSQL Import: Efficiently imports CSV data into PostgreSQL using:
   - Temporary tables for fast bulk loading (no WAL overhead)
   - PostgreSQL COPY command for maximum performance
   - Duplicate detection using ON CONFLICT
   - Data normalization (country codes, advertiser names)

PERFORMANCE:
────────────
- BigQuery → GCS: FREE (public dataset exports are free)
- GCS Download: FREE (same region)
- PostgreSQL Import: ~8-14 minutes for 3.5M+ rows
  - Uses COPY command (fastest bulk loading method)
  - Temporary table approach (minimal WAL overhead)
  - Deduplication handled in single query

FEATURES:
─────────
- Automatic file management (cleans up old GCS files)
- Duplicate detection and skipping
- Progress tracking and detailed statistics
- Error handling with cleanup on failure
- Supports dry-run mode for validation
- Can import existing CSV files or run full pipeline

USAGE EXAMPLES:
───────────────
    # Run complete pipeline (BigQuery → GCS → PostgreSQL)
    python3 advertisers_bigquery_postgres.py

    # Import specific CSV file only (skip BigQuery export)
    python3 advertisers_bigquery_postgres.py --csv-file daily_advertisers_export_20251030.csv

    # Import all CSV files from directory
    python3 advertisers_bigquery_postgres.py --import-all

    # Dry run (validate without importing)
    python3 advertisers_bigquery_postgres.py --dry-run

    # Skip BigQuery export (only import existing CSV)
    python3 advertisers_bigquery_postgres.py --skip-export
"""

import os
import sys
import json
import glob
import time
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

# Third-party imports
import psycopg2
from google.cloud import bigquery, storage
from google.oauth2 import service_account
from google.cloud.exceptions import NotFound, GoogleCloudError


# ============================================================================
# CONFIGURATION SECTION
# ============================================================================

# PostgreSQL Database Configuration
# Matches advertiser_utils.py and setup_database.py
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432
}

# Google Cloud Configuration
PROJECT_ID = "youtubeilike"
BIGQUERY_LOCATION = "US"  # CRITICAL: Must be 'US' for US public datasets
GCS_BUCKET_NAME = "youtubeilike-temp-exports"
GCS_FILE_PREFIX = "daily_advertisers_export_"

# Paths Configuration
CREDENTIALS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "config",
    "bigquery-credentials.json"
)

LOCAL_EXPORT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "gcs_exports"
)

# BigQuery Query Configuration
# This query extracts distinct advertisers from the public Google Ads Transparency dataset
# Fields mapped: advertiser_id, advertiser_disclosed_name → advertiser_name, advertiser_location → country
BIGQUERY_QUERY = """
SELECT DISTINCT
  advertiser_id,
  advertiser_disclosed_name AS advertiser_name,
  advertiser_location
FROM `bigquery-public-data.google_ads_transparency_center.creative_stats`
WHERE advertiser_id IS NOT NULL
"""


# ============================================================================
# GOOGLE CLOUD CLIENT INITIALIZATION
# ============================================================================

def get_bigquery_client() -> bigquery.Client:
    """
    Initialize and return BigQuery client with service account credentials.
    
    HOW IT WORKS:
    - Reads credentials from JSON file (config/bigquery-credentials.json)
    - Creates authenticated client with proper scopes for BigQuery operations
    - Uses US location (required for public datasets)
    
    Returns:
        BigQuery client instance configured for public dataset queries
        
    Raises:
        FileNotFoundError: If credentials file doesn't exist
        GoogleCloudError: If client creation fails
    """
    if CREDENTIALS_PATH and os.path.exists(CREDENTIALS_PATH):
        # Load credentials from JSON file
        with open(CREDENTIALS_PATH, 'r') as f:
            credentials_info = json.load(f)
        
        # Create service account credentials with full cloud platform access
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        
        # Initialize client with credentials and location
        client = bigquery.Client(
            credentials=credentials,
            project=PROJECT_ID,
            location=BIGQUERY_LOCATION
        )
        print(f"✓ BigQuery client created with service account: {credentials_info.get('client_email')}")
    else:
        # Fallback to Application Default Credentials (for development)
        client = bigquery.Client(
            project=PROJECT_ID,
            location=BIGQUERY_LOCATION
        )
        print("✓ BigQuery client created with Application Default Credentials")
    
    return client


def get_storage_client() -> storage.Client:
    """
    Initialize and return GCS storage client with service account credentials.
    
    HOW IT WORKS:
    - Uses same credentials as BigQuery client
    - Provides access to Google Cloud Storage for file operations
    
    Returns:
        Storage client instance for GCS operations
        
    Raises:
        FileNotFoundError: If credentials file doesn't exist
        GoogleCloudError: If client creation fails
    """
    if CREDENTIALS_PATH and os.path.exists(CREDENTIALS_PATH):
        with open(CREDENTIALS_PATH, 'r') as f:
            credentials_info = json.load(f)
        
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        
        client = storage.Client(
            credentials=credentials,
            project=PROJECT_ID
        )
        print(f"✓ Storage client created with service account: {credentials_info.get('client_email')}")
    else:
        client = storage.Client(project=PROJECT_ID)
        print("✓ Storage client created with Application Default Credentials")
    
    return client


def ensure_bucket_exists(storage_client: storage.Client, bucket_name: str, location: str = "US") -> storage.Bucket:
    """
    Create GCS bucket if it doesn't exist, or return existing bucket.
    
    HOW IT WORKS:
    - Checks if bucket exists in GCS
    - If not found, creates a new bucket in the specified location
    - Location must match BigQuery location for cost efficiency
    
    Args:
        storage_client: GCS storage client
        bucket_name: Name of the bucket to create/verify
        location: Geographic location (must match BigQuery location: "US")
        
    Returns:
        Bucket instance (existing or newly created)
        
    Raises:
        GoogleCloudError: If bucket creation fails
    """
    try:
        bucket = storage_client.get_bucket(bucket_name)
        print(f"✓ Bucket exists: gs://{bucket_name}")
        print(f"  Location: {bucket.location}")
        return bucket
    except NotFound:
        print(f"Creating bucket: gs://{bucket_name}...")
        bucket = storage_client.create_bucket(
            bucket_name,
            location=location,
            storage_class="STANDARD"
        )
        print(f"✓ Bucket created: gs://{bucket_name}")
        print(f"  Location: {bucket.location}")
        return bucket


# ============================================================================
# BIGQUERY EXPORT OPERATIONS
# ============================================================================

def execute_query_and_export_to_gcs(
    bq_client: bigquery.Client,
    storage_client: storage.Client,
    query: str,
    bucket_name: str,
    blob_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute BigQuery query and export results directly to GCS as CSV.
    
    HOW IT WORKS:
    ─────────────
    1. Creates a temporary table in BigQuery to store query results
       - Table is created in project's dataset (transparency_data)
       - Uses timestamp-based naming to avoid conflicts
    2. Executes query job that writes results to temporary table
       - Configured with WRITE_TRUNCATE (overwrites if exists)
       - allow_large_results=True enables handling millions of rows
    3. Exports temporary table to GCS as CSV
       - Uses BigQuery extract_table operation
       - Includes CSV header row
       - FREE operation (no cost for exports)
    4. Verifies export and cleans up temporary table
       - Waits for blob to be available in GCS
       - Deletes temporary table after successful export
    
    PERFORMANCE NOTES:
    - Query execution: Depends on data size (typically 2-5 minutes)
    - Export to GCS: Fast, handled by BigQuery infrastructure
    - Cost: $0.00 (free for public dataset queries and exports)
    
    Args:
        bq_client: BigQuery client instance
        storage_client: GCS storage client (for verification)
        query: SQL query string to execute
        bucket_name: GCS bucket name for export destination
        blob_name: Optional GCS blob name. If None, auto-generates with timestamp.
        
    Returns:
        Dictionary with export details:
        {
            'success': bool,
            'destination_uri': str,  # gs://bucket/blob_name
            'blob_name': str,
            'file_size_mb': float,
            'duration_seconds': float,
            'query_job_id': str,
            'export_job_id': str,
            'error': str (if failed)
        }
    """
    start_time = datetime.utcnow()
    temp_table_ref = None
    temp_table_id = None
    
    try:
        # Generate blob name if not provided (format: daily_advertisers_export_YYYYMMDD.csv)
        if not blob_name:
            timestamp = datetime.utcnow().strftime('%Y%m%d')
            blob_name = f"{GCS_FILE_PREFIX}{timestamp}.csv"
        
        destination_uri = f"gs://{bucket_name}/{blob_name}"
        
        print(f"\n{'='*80}")
        print(f"Executing BigQuery Query and Exporting to GCS")
        print(f"{'='*80}")
        print(f"Query Source: bigquery-public-data.google_ads_transparency_center.creative_stats")
        print(f"Destination:  {destination_uri}")
        print(f"Location:     {BIGQUERY_LOCATION}")
        print()
        
        # STEP 1: Create temporary table reference
        # BigQuery requires writing query results to a table first, then exporting
        dataset_ref = bq_client.dataset("transparency_data", project=PROJECT_ID)
        temp_table_name = f"_temp_advertisers_export_{int(datetime.utcnow().timestamp())}"
        temp_table_ref = dataset_ref.table(temp_table_name)
        temp_table_id = f"{PROJECT_ID}.transparency_data.{temp_table_name}"
        
        print("Executing query to temporary table...")
        print(f"Query: {query[:100]}..." if len(query) > 100 else f"Query: {query}")
        
        # STEP 2: Configure and execute query job
        # Write results to temporary table instead of streaming them
        job_config = bigquery.QueryJobConfig()
        job_config.destination = temp_table_ref
        job_config.write_disposition = bigquery.WriteDisposition.WRITE_TRUNCATE
        job_config.allow_large_results = True  # Required for large result sets
        
        # Execute query (this blocks until completion)
        query_job = bq_client.query(
            query,
            job_config=job_config,
            location=BIGQUERY_LOCATION
        )
        
        # Wait for query to complete
        print("Waiting for query execution to complete...")
        query_job.result()  # Blocks until job completes
        
        # Verify query succeeded
        if query_job.errors:
            error_msg = f"Query job failed: {query_job.errors}"
            print(f"✗ {error_msg}")
            _cleanup_temp_table(bq_client, temp_table_ref, temp_table_id)
            return {
                'success': False,
                'error': error_msg,
                'query_job_id': query_job.job_id
            }
        
        # STEP 3: Export temporary table to GCS
        print("Exporting temporary table to GCS...")
        extract_job_config = bigquery.ExtractJobConfig()
        extract_job_config.destination_format = bigquery.DestinationFormat.CSV
        extract_job_config.print_header = True  # Include CSV header row
        
        # Extract table to GCS
        extract_job = bq_client.extract_table(
            temp_table_ref,
            destination_uri,
            job_config=extract_job_config
        )
        
        # Wait for export to complete
        print("Waiting for export to complete...")
        extract_job.result()  # Blocks until job completes
        
        # Verify export succeeded
        if extract_job.errors:
            error_msg = f"Export job failed: {extract_job.errors}"
            print(f"✗ {error_msg}")
            _cleanup_temp_table(bq_client, temp_table_ref, temp_table_id)
            return {
                'success': False,
                'error': error_msg,
                'query_job_id': query_job.job_id,
                'export_job_id': extract_job.job_id
            }
        
        # STEP 4: Verify export and get file info
        # Wait a moment for blob to be written to GCS
        time.sleep(2)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # Retry logic for blob availability (GCS eventual consistency)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                blob.reload()
                break
            except NotFound:
                if attempt < max_retries - 1:
                    print(f"  Waiting for blob to be available (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(2)
                else:
                    raise NotFound(f"Blob not found after export: {blob_name}")
        
        file_size_mb = blob.size / (1024 * 1024)
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        print(f"✓ Query executed and export completed successfully")
        print(f"  Query Job ID: {query_job.job_id}")
        print(f"  Export Job ID: {extract_job.job_id}")
        print(f"  File Size:   {file_size_mb:.1f} MB")
        print(f"  Duration:    {duration:.1f} seconds")
        print(f"  Cost:        $0.00 (FREE!)")
        print(f"  URI:         {destination_uri}")
        
        # STEP 5: Clean up temporary table
        _cleanup_temp_table(bq_client, temp_table_ref, temp_table_id)
        
        return {
            'success': True,
            'destination_uri': destination_uri,
            'blob_name': blob_name,
            'file_size_mb': file_size_mb,
            'duration_seconds': duration,
            'query_job_id': query_job.job_id,
            'export_job_id': extract_job.job_id,
            'total_bytes_processed': getattr(query_job, 'total_bytes_processed', None)
        }
        
    except (NotFound, GoogleCloudError) as e:
        error_msg = f"Google Cloud error: {str(e)}"
        print(f"✗ {error_msg}")
        if temp_table_ref:
            _cleanup_temp_table(bq_client, temp_table_ref, temp_table_id if temp_table_id else "unknown")
        return {
            'success': False,
            'error': error_msg,
            'error_type': type(e).__name__
        }
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"✗ {error_msg}")
        traceback.print_exc()
        if temp_table_ref:
            _cleanup_temp_table(bq_client, temp_table_ref, temp_table_id if temp_table_id else "unknown")
        return {
            'success': False,
            'error': error_msg,
            'error_type': type(e).__name__
        }


def _cleanup_temp_table(
    bq_client: bigquery.Client,
    temp_table_ref: Optional[bigquery.TableReference],
    temp_table_id: str
) -> None:
    """
    Helper function to clean up temporary BigQuery table.
    
    HOW IT WORKS:
    - Attempts to delete the temporary table created during export
    - Uses not_found_ok=True to gracefully handle already-deleted tables
    - Logs warning if deletion fails (table can be manually deleted later)
    
    Args:
        bq_client: BigQuery client
        temp_table_ref: Reference to temporary table (can be None)
        temp_table_id: Full table ID for error messages
    """
    if not temp_table_ref:
        return
    
    try:
        print(f"\nCleaning up temporary table: {temp_table_id}")
        bq_client.delete_table(temp_table_ref, not_found_ok=True)
        print(f"✓ Temporary table deleted")
    except Exception as e:
        print(f"⚠ Warning: Could not delete temporary table: {e}")
        print(f"  You can delete it manually: {temp_table_id}")


# ============================================================================
# GCS DOWNLOAD OPERATIONS
# ============================================================================

def download_from_gcs(
    storage_client: storage.Client,
    bucket_name: str,
    blob_name: str,
    local_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Download file from GCS to local filesystem.
    
    HOW IT WORKS:
    ─────────────
    1. Creates local export directory if it doesn't exist
    2. Verifies blob exists in GCS before downloading
    3. Downloads file using GCS client (handles large files efficiently)
    4. Verifies download integrity by checking file size
    5. Calculates download speed statistics
    
    PERFORMANCE NOTES:
    - Download speed depends on network connection
    - GCS handles large files efficiently (streaming download)
    - Cost: $0.00 (same region, no egress charges)
    
    Args:
        storage_client: GCS storage client
        bucket_name: GCS bucket name
        blob_name: Name of the blob/file in GCS
        local_path: Local file path. If None, uses gcs_exports/ folder with blob name.
        
    Returns:
        Dictionary with download details:
        {
            'success': bool,
            'local_path': str,
            'file_size_mb': float,
            'duration_seconds': float,
            'download_speed_mb_per_sec': float,
            'error': str (if failed)
        }
    """
    start_time = datetime.utcnow()
    
    try:
        # Create local export directory if it doesn't exist
        os.makedirs(LOCAL_EXPORT_DIR, exist_ok=True)
        
        # Set local path (defaults to gcs_exports/blob_name)
        if not local_path:
            local_path = os.path.join(LOCAL_EXPORT_DIR, blob_name)
        
        print(f"\n{'='*80}")
        print(f"Downloading from GCS")
        print(f"{'='*80}")
        print(f"Source: gs://{bucket_name}/{blob_name}")
        print(f"Destination: {local_path}")
        
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # Verify blob exists
        if not blob.exists():
            raise NotFound(f"Blob not found: gs://{bucket_name}/{blob_name}")
        
        # Get file size
        blob.reload()
        file_size_mb = blob.size / (1024 * 1024)
        print(f"File Size: {file_size_mb:.1f} MB")
        
        print(f"Downloading...")
        
        # Download file (GCS client handles large files efficiently)
        blob.download_to_filename(local_path)
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        download_speed = file_size_mb / duration if duration > 0 else 0
        
        # Verify download integrity
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Downloaded file not found: {local_path}")
        
        actual_size = os.path.getsize(local_path) / (1024 * 1024)
        if abs(actual_size - file_size_mb) > 0.1:  # Allow 0.1 MB difference
            raise ValueError(f"Size mismatch: expected {file_size_mb:.1f} MB, got {actual_size:.1f} MB")
        
        print(f"✓ Download completed successfully")
        print(f"  Local Path:  {local_path}")
        print(f"  File Size:   {actual_size:.1f} MB")
        print(f"  Duration:    {duration:.1f} seconds")
        print(f"  Speed:       {download_speed:.1f} MB/s")
        
        return {
            'success': True,
            'local_path': local_path,
            'file_size_mb': actual_size,
            'duration_seconds': duration,
            'download_speed_mb_per_sec': download_speed
        }
        
    except (NotFound, GoogleCloudError) as e:
        error_msg = f"Google Cloud error: {str(e)}"
        print(f"✗ {error_msg}")
        return {
            'success': False,
            'error': error_msg,
            'error_type': type(e).__name__
        }
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"✗ {error_msg}")
        traceback.print_exc()
        return {
            'success': False,
            'error': error_msg,
            'error_type': type(e).__name__
        }


def check_file_exists_in_gcs(
    storage_client: storage.Client,
    bucket_name: str,
    blob_name: str
) -> bool:
    """
    Check if a file exists in GCS bucket.
    
    HOW IT WORKS:
    - Queries GCS bucket for the specified blob
    - Returns True if blob exists, False otherwise
    - Used to avoid re-exporting files that already exist
    
    Args:
        storage_client: GCS storage client
        bucket_name: GCS bucket name
        blob_name: Name of the blob/file to check
        
    Returns:
        True if file exists, False otherwise
    """
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        return blob.exists()
    except Exception as e:
        print(f"⚠ Warning: Error checking if file exists: {e}")
        return False


def cleanup_old_files_from_gcs(
    storage_client: storage.Client,
    bucket_name: str,
    file_prefix: str,
    current_date: str
) -> Dict[str, Any]:
    """
    Delete old files from GCS that match the prefix pattern and are not from today.
    
    HOW IT WORKS:
    ─────────────
    1. Lists all blobs in bucket matching the file prefix
    2. Extracts date from filename (format: prefix_YYYYMMDD.csv)
    3. Compares extracted date with current date
    4. Deletes files with dates older than today
    5. Keeps today's file and skips files with future dates
    
    PURPOSE:
    - Prevents GCS bucket from accumulating old export files
    - Reduces storage costs by keeping only latest export
    - Automated cleanup before creating new export
    
    Args:
        storage_client: GCS storage client
        bucket_name: GCS bucket name
        file_prefix: Prefix to match files (e.g., "daily_advertisers_export_")
        current_date: Today's date in YYYYMMDD format
        
    Returns:
        Dictionary with cleanup statistics:
        {
            'files_deleted': int,
            'total_size_mb': float,
            'errors': List[str]
        }
    """
    stats: Dict[str, Any] = {
        'files_deleted': 0,
        'total_size_mb': 0.0,
        'errors': []
    }
    
    try:
        bucket = storage_client.bucket(bucket_name)
        blobs = list(bucket.list_blobs(prefix=file_prefix))
        
        if not blobs:
            print(f"  No files found with prefix '{file_prefix}'")
            return stats
        
        print(f"  Found {len(blobs)} file(s) with prefix '{file_prefix}'")
        
        for blob in blobs:
            filename = blob.name
            # Validate filename format (prefix_YYYYMMDD.csv)
            if not filename.startswith(file_prefix) or not filename.endswith('.csv'):
                continue
            
            # Extract date portion from filename
            date_part = filename[len(file_prefix):-4]  # Remove prefix and .csv extension
            
            # Validate date format (YYYYMMDD = 8 characters, all digits)
            if len(date_part) != 8 or not date_part.isdigit():
                print(f"  ⚠ Skipping file with unexpected format: {filename}")
                continue
            
            # Check if it's from an older day (string comparison works for YYYYMMDD)
            if date_part < current_date:
                try:
                    size_mb = blob.size / (1024 * 1024)
                    blob.delete()
                    stats['files_deleted'] += 1
                    stats['total_size_mb'] += size_mb
                    print(f"  ✓ Deleted old file: {filename} ({size_mb:.1f} MB, date: {date_part})")
                except Exception as e:
                    error_msg = f"Failed to delete {filename}: {str(e)}"
                    stats['errors'].append(error_msg)
                    print(f"  ✗ {error_msg}")
            elif date_part == current_date:
                print(f"  ⊙ Keeping today's file: {filename}")
            else:
                # Future date (shouldn't happen, but handle gracefully)
                print(f"  ⚠ Skipping file with future date: {filename} (date: {date_part})")
        
        if stats['files_deleted'] > 0:
            print(f"\n  ✓ Cleanup complete: Deleted {stats['files_deleted']} file(s), freed {stats['total_size_mb']:.1f} MB")
        else:
            print(f"  ✓ No old files to clean up")
        
        return stats
        
    except Exception as e:
        error_msg = f"Error during cleanup: {str(e)}"
        stats['errors'].append(error_msg)
        print(f"  ✗ {error_msg}")
        traceback.print_exc()
        return stats


# ============================================================================
# POSTGRESQL DATABASE OPERATIONS
# ============================================================================

@contextmanager
def get_db_connection():
    """
    Context manager for PostgreSQL database connections.
    
    HOW IT WORKS:
    - Creates connection using DB_CONFIG
    - Ensures rollback on exception
    - Automatically closes connection when exiting context
    
    Usage:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # ... database operations ...
    """
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def create_temp_table(cursor) -> None:
    """
    Create temporary table for CSV data loading.
    
    HOW IT WORKS:
    ─────────────
    - Creates a TEMPORARY TABLE (automatically dropped at end of session)
    - Temporary tables are optimized for bulk operations:
      * No WAL (Write-Ahead Log) overhead (faster writes)
      * Not logged to disk (reduces I/O)
      * Perfect for staging data before merge
    
    PURPOSE:
    - Stage CSV data before merging into main table
    - Enable fast bulk loading with COPY command
    - Avoid locking main table during load
    
    Note: Temporary tables are automatically dropped when the session ends,
    so cleanup is not required.
    """
    cursor.execute("""
        CREATE TEMPORARY TABLE advertisers_temp (
            advertiser_id TEXT,
            advertiser_name TEXT,
            advertiser_location TEXT
        )
    """)


def copy_csv_to_temp_table(cursor, csv_file_path: str) -> int:
    """
    Copy CSV data into temporary table using PostgreSQL COPY command.
    
    HOW IT WORKS:
    ─────────────
    1. Opens CSV file for reading
    2. Uses PostgreSQL COPY command (fastest bulk loading method)
       - Reads directly from file stream
       - Handles CSV format with proper quote/escape handling
       - Skips header row (HEADER true)
    3. Counts loaded rows for verification
    
    PERFORMANCE:
    - COPY is the fastest way to bulk load data in PostgreSQL
    - Typically processes 50,000-200,000 rows/second
    - Much faster than INSERT statements (no query planning overhead)
    
    Args:
        cursor: Database cursor
        csv_file_path: Path to CSV file
        
    Returns:
        Number of rows loaded into temporary table
    """
    print(f"  📥 Loading CSV into temporary table using COPY...")
    start_time = time.time()
    
    # Use COPY FROM with CSV format for proper handling of quoted fields
    # This is the fastest bulk loading method in PostgreSQL
    with open(csv_file_path, 'r', encoding='utf-8') as csv_file:
        cursor.copy_expert(
            """
            COPY advertisers_temp (advertiser_id, advertiser_name, advertiser_location)
            FROM STDIN
            WITH (FORMAT CSV, HEADER true, DELIMITER ',', QUOTE '"', ESCAPE '"')
            """,
            csv_file
        )
    
    # Get row count for verification
    cursor.execute("SELECT COUNT(*) FROM advertisers_temp")
    row_count = cursor.fetchone()[0]
    
    duration = time.time() - start_time
    print(f"  ✅ Loaded {row_count:,} rows in {duration:.1f}s ({row_count/duration:.0f} rows/s)")
    
    return row_count


def merge_temp_to_main_table(cursor) -> Dict[str, int]:
    """
    Merge data from temp table to main advertisers table with deduplication.
    
    HOW IT WORKS:
    ─────────────
    1. Counts rows in temp table before merge
    2. Executes INSERT ... ON CONFLICT DO NOTHING:
       - Inserts new rows into main advertisers table
       - Skips rows where advertiser_id already exists (duplicates)
       - Performs data normalization during insert:
         * advertiser_name_normalized = LOWER(TRIM(advertiser_name))
         * country = NULLIF(TRIM(advertiser_location), '')  # Empty strings become NULL
    3. Filters out rows with NULL advertiser_id or advertiser_name
    4. Calculates statistics (inserted vs skipped)
    
    PERFORMANCE:
    - Single SQL statement handles all operations efficiently
    - ON CONFLICT uses primary key index for fast duplicate detection
    - For 3.5M rows: typically takes 5-10 minutes
    - Much faster than row-by-row INSERT with duplicate checking
    
    DEDUPLICATION LOGIC:
    - Uses advertiser_id as primary key (from ON CONFLICT)
    - Duplicate advertiser_ids are automatically skipped
    - No error thrown on duplicates (graceful skipping)
    
    Args:
        cursor: Database cursor
        
    Returns:
        Dictionary with statistics:
        {
            'inserted': int,      # Number of new rows inserted
            'skipped': int,       # Number of duplicates skipped
            'total_processed': int # Total rows in temp table
        }
    """
    print(f"  🔄 Merging data from temp table to main table...")
    start_time = time.time()
    
    # Get row count before merge
    cursor.execute("SELECT COUNT(*) FROM advertisers_temp")
    temp_count = cursor.fetchone()[0]
    
    # Perform bulk merge with normalization and deduplication
    # This single query:
    # - Inserts new advertisers
    # - Skips duplicates (ON CONFLICT DO NOTHING)
    # - Normalizes advertiser names (lowercase, trimmed)
    # - Converts empty country strings to NULL
    print(f"    Executing merge query... (this may take a few minutes for 3.5M rows)")
    
    try:
        cursor.execute("""
            INSERT INTO advertisers (
                advertiser_id,
                advertiser_name,
                advertiser_name_normalized,
                country
            )
            SELECT 
                advertiser_id,
                advertiser_name,
                LOWER(TRIM(advertiser_name)),
                NULLIF(TRIM(advertiser_location), '')
            FROM advertisers_temp
            WHERE advertiser_id IS NOT NULL
              AND advertiser_name IS NOT NULL
            ON CONFLICT (advertiser_id) DO NOTHING
        """)
        
        inserted = cursor.rowcount
        
        # Verify insertion worked
        if inserted == 0 and temp_count > 0:
            print(f"    ⚠️  Warning: 0 rows inserted but {temp_count:,} rows in temp table")
            # Check if all rows are filtered out
            cursor.execute("""
                SELECT COUNT(*) FROM advertisers_temp 
                WHERE advertiser_id IS NULL OR advertiser_name IS NULL
            """)
            filtered = cursor.fetchone()[0]
            print(f"    Rows filtered out (NULL values): {filtered:,}")
            print(f"    Rows that should insert: {temp_count - filtered:,}")
            
    except Exception as e:
        print(f"    ❌ Error during merge: {e}")
        raise
    
    # Calculate skipped (duplicates)
    skipped = temp_count - inserted
    
    duration = time.time() - start_time
    print(f"  ✅ Merged {inserted:,} new rows, skipped {skipped:,} duplicates in {duration:.1f}s")
    
    return {
        'inserted': inserted,
        'skipped': skipped,
        'total_processed': temp_count
    }


def get_table_statistics(cursor) -> Dict[str, Any]:
    """
    Get statistics about the advertisers table.
    
    HOW IT WORKS:
    - Queries table for total count
    - Counts advertisers with/without country codes
    - Gets top 10 countries by advertiser count
    - Provides overview of data distribution
    
    Returns:
        Dictionary with statistics:
        {
            'total': int,
            'with_country': int,
            'without_country': int,
            'top_countries': List[Tuple[str, int]]  # (country_code, count)
        }
    """
    stats = {}
    
    # Total count
    cursor.execute("SELECT COUNT(*) FROM advertisers")
    stats['total'] = cursor.fetchone()[0]
    
    # Count by country (top 10)
    cursor.execute("""
        SELECT country, COUNT(*) as count
        FROM advertisers
        WHERE country IS NOT NULL
        GROUP BY country
        ORDER BY count DESC
        LIMIT 10
    """)
    stats['top_countries'] = cursor.fetchall()
    
    # Count with country vs without
    cursor.execute("SELECT COUNT(*) FROM advertisers WHERE country IS NOT NULL")
    stats['with_country'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM advertisers WHERE country IS NULL")
    stats['without_country'] = cursor.fetchone()[0]
    
    return stats


def import_csv_file(csv_file_path: str, dry_run: bool = False) -> Dict[str, Any]:
    """
    Import a single CSV file into the advertisers table.
    
    HOW IT WORKS:
    ─────────────
    1. Validates CSV file exists and gets file size
    2. Creates temporary table for staging
    3. Loads CSV data into temp table using COPY (fast bulk load)
    4. Merges temp table into main table (with deduplication)
    5. Gets final statistics about the database
    6. Cleans up (temp table auto-drops on connection close)
    
    PERFORMANCE BREAKDOWN:
    - COPY to temp table: ~30-60 seconds for 3.5M rows
    - Merge to main table: ~5-10 minutes for 3.5M rows
    - Total: ~8-14 minutes for full import
    
    Args:
        csv_file_path: Path to CSV file
        dry_run: If True, don't actually import (just validate file)
        
    Returns:
        Dictionary with import statistics:
        {
            'success': bool,
            'csv_file': str,
            'file_size_mb': float,
            'duration_seconds': float,
            'rows_loaded': int,
            'rows_inserted': int,
            'rows_skipped': int,
            'final_total': int,
            'final_with_country': int,
            'final_without_country': int,
            'top_countries': List[Tuple[str, int]]
        }
    """
    csv_file_name = os.path.basename(csv_file_path)
    print(f"\n{'='*80}")
    print(f"Processing: {csv_file_name}")
    print(f"{'='*80}")
    
    # Validate file exists
    if not os.path.exists(csv_file_path):
        raise FileNotFoundError(f"CSV file not found: {csv_file_path}")
    
    # Get file size
    file_size_mb = os.path.getsize(csv_file_path) / (1024 * 1024)
    print(f"File size: {file_size_mb:.1f} MB")
    
    if dry_run:
        print(f"  ⚠️  DRY RUN mode - not importing")
        return {'dry_run': True, 'csv_file': csv_file_name}
    
    start_time = time.time()
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # STEP 1: Create temporary table
            print(f"\n1️⃣  Creating temporary table...")
            create_temp_table(cursor)
            conn.commit()
            
            # STEP 2: Copy CSV to temp table (fast bulk load)
            print(f"\n2️⃣  Copying CSV data to temporary table...")
            row_count = copy_csv_to_temp_table(cursor, csv_file_path)
            conn.commit()
            
            # STEP 3: Merge from temp to main table (with duplicate skipping)
            print(f"\n3️⃣  Merging to main table (with duplicate skipping)...")
            merge_stats = merge_temp_to_main_table(cursor)
            print(f"    Committing merge transaction...")
            conn.commit()
            print(f"    ✅ Commit successful")
            
            # STEP 4: Get final statistics
            print(f"\n4️⃣  Getting final statistics...")
            final_stats = get_table_statistics(cursor)
            
            # Cleanup: Temp table is automatically dropped when connection closes
            
            total_duration = time.time() - start_time
            
            # Build result dictionary
            result = {
                'success': True,
                'csv_file': csv_file_name,
                'file_size_mb': file_size_mb,
                'duration_seconds': total_duration,
                'rows_loaded': row_count,
                'rows_inserted': merge_stats['inserted'],
                'rows_skipped': merge_stats['skipped'],
                'final_total': final_stats['total'],
                'final_with_country': final_stats['with_country'],
                'final_without_country': final_stats['without_country'],
                'top_countries': final_stats['top_countries']
            }
            
            # Print summary
            print(f"\n{'='*80}")
            print(f"✅ Import Complete")
            print(f"{'='*80}")
            print(f"File:              {csv_file_name}")
            print(f"File size:         {file_size_mb:.1f} MB")
            print(f"Rows loaded:       {row_count:,}")
            print(f"Rows inserted:     {merge_stats['inserted']:,}")
            print(f"Rows skipped:      {merge_stats['skipped']:,} (duplicates)")
            print(f"Duration:          {total_duration:.1f}s ({total_duration/60:.1f} min)")
            print(f"Insert rate:       {merge_stats['inserted']/total_duration:.0f} rows/s")
            print(f"\nFinal table stats:")
            print(f"  Total advertisers: {final_stats['total']:,}")
            print(f"  With country:      {final_stats['with_country']:,}")
            print(f"  Without country:   {final_stats['without_country']:,}")
            
            if final_stats['top_countries']:
                print(f"\n  Top countries:")
                for country, count in final_stats['top_countries']:
                    print(f"    {country}: {count:,}")
            
            cursor.close()
            
            return result
            
    except Exception as e:
        print(f"\n❌ Error importing {csv_file_name}: {e}")
        traceback.print_exc()
        return {
            'success': False,
            'csv_file': csv_file_name,
            'error': str(e)
        }


def find_csv_files(csv_dir: str, pattern: Optional[str] = None) -> List[str]:
    """
    Find CSV files in the specified directory.
    
    HOW IT WORKS:
    - Searches directory for CSV files matching pattern
    - If pattern provided, matches specific file
    - If no pattern, returns all CSV files
    - Sorts results by modification time (newest first)
    
    Args:
        csv_dir: Directory to search
        pattern: Optional pattern to match (e.g., 'daily_advertisers_export_20251030.csv')
                 If None, finds all CSV files
        
    Returns:
        List of CSV file paths, sorted by modification time (newest first)
    """
    if not os.path.exists(csv_dir):
        raise FileNotFoundError(f"CSV directory not found: {csv_dir}")
    
    if pattern:
        # Match specific file
        full_path = os.path.join(csv_dir, pattern)
        if os.path.exists(full_path):
            return [full_path]
        else:
            # Try with .csv extension if not provided
            if not pattern.endswith('.csv'):
                full_path = os.path.join(csv_dir, f"{pattern}.csv")
                if os.path.exists(full_path):
                    return [full_path]
            raise FileNotFoundError(f"CSV file not found: {full_path}")
    else:
        # Find all CSV files
        pattern_glob = os.path.join(csv_dir, '*.csv')
        files = glob.glob(pattern_glob)
        # Sort by modification time (newest first)
        files.sort(key=os.path.getmtime, reverse=True)
        return files


# ============================================================================
# MAIN WORKFLOW ORCHESTRATION
# ============================================================================

def run_bigquery_export_workflow(
    skip_export: bool = False,
    blob_name: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Execute the BigQuery → GCS → Download workflow.
    
    HOW IT WORKS:
    ─────────────
    1. Initializes BigQuery and GCS clients
    2. Ensures GCS bucket exists
    3. Cleans up old files from GCS
    4. Checks if today's file already exists (skips export if exists)
    5. Executes BigQuery query and exports to GCS (if needed)
    6. Downloads file from GCS to local storage
    7. Returns download result with local file path
    
    Args:
        skip_export: If True, skip BigQuery export step entirely
        blob_name: Optional blob name. If None, uses today's date format.
        
    Returns:
        Dictionary with download result (contains 'local_path' on success)
        None if skip_export=True and no existing file found
    """
    print("\n" + "="*80)
    print("BigQuery → GCS → Download Workflow")
    print("="*80 + "\n")
    
    try:
        # Verify credentials file exists
        if not os.path.exists(CREDENTIALS_PATH):
            print(f"✗ Credentials file not found: {CREDENTIALS_PATH}")
            print("  Please ensure the credentials file exists or set GOOGLE_APPLICATION_CREDENTIALS environment variable.")
            return None
        
        # Initialize clients
        print("Initializing clients...")
        bq_client = get_bigquery_client()
        storage_client = get_storage_client()
        print()
        
        # Ensure bucket exists
        ensure_bucket_exists(storage_client, GCS_BUCKET_NAME, BIGQUERY_LOCATION)
        
        # Get today's date for filename and cleanup
        today_timestamp = datetime.utcnow().strftime('%Y%m%d')
        if not blob_name:
            blob_name = f"{GCS_FILE_PREFIX}{today_timestamp}.csv"
        
        # Clean up old files from GCS (before checking/creating today's file)
        print(f"\nCleaning up old files from GCS...")
        print(f"  Looking for files with prefix: {GCS_FILE_PREFIX}")
        cleanup_stats = cleanup_old_files_from_gcs(
            storage_client,
            GCS_BUCKET_NAME,
            GCS_FILE_PREFIX,
            today_timestamp
        )
        if cleanup_stats['errors']:
            print(f"  ⚠ Warnings during cleanup: {len(cleanup_stats['errors'])} error(s)")
        
        # Check if file already exists or skip export
        if skip_export:
            print(f"\n⚠ Skipping BigQuery export (--skip-export flag)")
            # Still try to download if file exists
            if not check_file_exists_in_gcs(storage_client, GCS_BUCKET_NAME, blob_name):
                print(f"  ✗ File not found in GCS: gs://{GCS_BUCKET_NAME}/{blob_name}")
                return None
        else:
            print(f"\nChecking if file for today already exists in GCS...")
            print(f"  Looking for: gs://{GCS_BUCKET_NAME}/{blob_name}")
            
            if check_file_exists_in_gcs(storage_client, GCS_BUCKET_NAME, blob_name):
                print(f"✓ File for today already exists in GCS")
                print(f"  Skipping BigQuery query and export, downloading existing file...")
            else:
                print(f"  File not found, proceeding with query and export...")
                
                # Execute query and export to GCS
                export_result = execute_query_and_export_to_gcs(
                    bq_client,
                    storage_client,
                    BIGQUERY_QUERY,
                    GCS_BUCKET_NAME,
                    blob_name=blob_name
                )
                
                if not export_result['success']:
                    print(f"\n✗ Export failed: {export_result['error']}")
                    return None
        
        # Download from GCS
        download_result = download_from_gcs(
            storage_client,
            GCS_BUCKET_NAME,
            blob_name
        )
        
        if not download_result['success']:
            print(f"\n✗ Download failed: {download_result['error']}")
            return None
        
        # Summary
        print(f"\n{'='*80}")
        print("✓ BigQuery Export Workflow Completed Successfully")
        print(f"{'='*80}")
        print(f"Query Source:  bigquery-public-data.google_ads_transparency_center.creative_stats")
        print(f"GCS URI:       gs://{GCS_BUCKET_NAME}/{blob_name}")
        print(f"Local File:    {download_result['local_path']}")
        print(f"File Size:     {download_result['file_size_mb']:.1f} MB")
        
        return download_result
        
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        return None
    except Exception as e:
        print(f"\n✗ Fatal error: {str(e)}")
        traceback.print_exc()
        return None


def main() -> int:
    """
    Main execution function - orchestrates the complete pipeline.
    
    WORKFLOW STEPS:
    ──────────────
    1. Parse command-line arguments
    2. Execute BigQuery export workflow (if not skipped):
       - Query BigQuery → Export to GCS → Download locally
    3. Execute PostgreSQL import workflow:
       - Import CSV file(s) into PostgreSQL
       - Handle deduplication and normalization
    4. Print final summary statistics
    
    COMMAND-LINE OPTIONS:
    ─────────────────────
    --skip-export: Skip BigQuery export, only import existing CSV files
    --csv-file: Import specific CSV file (skip export if file exists)
    --import-all: Import all CSV files from directory
    --dry-run: Validate CSV without importing
    --dir: Specify CSV directory (default: gcs_exports/)
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Complete Advertisers Pipeline: BigQuery → GCS → PostgreSQL',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run complete pipeline (BigQuery → GCS → PostgreSQL)
  %(prog)s

  # Import specific CSV file only (skip BigQuery export)
  %(prog)s --csv-file daily_advertisers_export_20251030.csv

  # Import all CSV files from directory
  %(prog)s --import-all

  # Skip BigQuery export, only import existing CSV files
  %(prog)s --skip-export

  # Dry run (validate without importing)
  %(prog)s --dry-run
        """
    )
    
    parser.add_argument(
        '--skip-export',
        action='store_true',
        help='Skip BigQuery export step, only import existing CSV files'
    )
    parser.add_argument(
        '--csv-file',
        nargs='?',
        help='Import specific CSV file (if not provided, imports latest or runs full pipeline)'
    )
    parser.add_argument(
        '--import-all',
        action='store_true',
        help='Import all CSV files in gcs_exports directory'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate CSV file without importing (dry run)'
    )
    parser.add_argument(
        '--dir',
        default=LOCAL_EXPORT_DIR,
        help=f'CSV directory (default: {LOCAL_EXPORT_DIR})'
    )
    
    args = parser.parse_args()
    
    print("="*80)
    print("ADVERTISERS BIGQUERY → POSTGRESQL PIPELINE")
    print("="*80)
    
    try:
        # STEP 1: Execute BigQuery export workflow (unless skipped or CSV file specified)
        export_result = None
        csv_files = []
        
        if args.csv_file:
            # User specified a CSV file - skip export, import specified file
            print(f"\n⚠ Skipping BigQuery export (CSV file specified: {args.csv_file})")
            csv_files = find_csv_files(args.dir, args.csv_file)
        elif not args.skip_export and not args.import_all:
            # Run full pipeline: BigQuery → GCS → Download → Import
            export_result = run_bigquery_export_workflow(skip_export=False)
            if export_result and export_result.get('local_path'):
                # Use the downloaded file
                csv_files = [export_result['local_path']]
            else:
                print("\n✗ Export workflow failed, cannot proceed with import")
                return 1
        else:
            # Skip export, will import from existing files
            print(f"\n⚠ Skipping BigQuery export (--skip-export or --import-all specified)")
        
        # STEP 2: Determine which CSV files to import
        if not csv_files:
            if args.import_all:
                # Import all CSV files
                csv_files = find_csv_files(args.dir)
                if not csv_files:
                    print(f"❌ No CSV files found in {args.dir}")
                    return 1
                print(f"\nFound {len(csv_files)} CSV file(s) to import")
            else:
                # Import latest file
                csv_files = find_csv_files(args.dir)
                if csv_files:
                    csv_files = [csv_files[0]]  # Latest file only
                    print(f"\nImporting latest file: {os.path.basename(csv_files[0])}")
                else:
                    print(f"❌ No CSV files found in {args.dir}")
                    return 1
        
        # STEP 3: Import CSV files into PostgreSQL
        print(f"\n{'='*80}")
        print("PostgreSQL Import Workflow")
        print(f"{'='*80}")
        print(f"CSV directory: {args.dir}")
        
        results = []
        for csv_file in csv_files:
            result = import_csv_file(csv_file, dry_run=args.dry_run)
            results.append(result)
            
            if not result.get('success') and not result.get('dry_run'):
                print(f"\n❌ Import failed for {csv_file}")
                return 1
        
        # STEP 4: Print final summary
        if len(results) > 1:
            print(f"\n{'='*80}")
            print(f"SUMMARY - {len(results)} file(s) imported")
            print(f"{'='*80}")
            total_inserted = sum(r.get('rows_inserted', 0) for r in results)
            total_skipped = sum(r.get('rows_skipped', 0) for r in results)
            total_duration = sum(r.get('duration_seconds', 0) for r in results)
            
            print(f"Total rows inserted: {total_inserted:,}")
            print(f"Total rows skipped:  {total_skipped:,}")
            print(f"Total duration:      {total_duration:.1f}s ({total_duration/60:.1f} min)")
        
        print(f"\n✅ Complete pipeline executed successfully!")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

