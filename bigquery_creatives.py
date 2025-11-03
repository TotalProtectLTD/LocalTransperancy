#!/usr/bin/env python3
"""
BigQuery Creatives Query Export to GCS and Download

Executes a BigQuery query for creatives and exports results to Google Cloud Storage,
then downloads the file to localhost.

Flow: BigQuery Query → Export Results to GCS → Download to Localhost
"""

import os
import sys
import json
import csv
import tempfile
import time
import traceback
import argparse
from datetime import datetime, date
from typing import Optional, Dict, Any, List, Tuple
from google.cloud import bigquery, storage
from google.oauth2 import service_account
from google.cloud.exceptions import NotFound, GoogleCloudError
import psycopg2


# ============================================================================
# CONFIGURATION
# ============================================================================

# Google Cloud Project
PROJECT_ID = "youtubeilike"
BIGQUERY_LOCATION = "US"  # CRITICAL: Must be 'US' for US public datasets

# GCS Bucket
GCS_BUCKET_NAME = "youtubeilike-temp-exports"
GCS_FILE_PREFIX = "daily_creatives_export_"

# Credentials path (relative to project root)
CREDENTIALS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "config",
    "bigquery-credentials.json"
)

# Local download folder
LOCAL_EXPORT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "gcs_exports"
)

# PostgreSQL Database (see docs/DB_OVERVIEW.md)
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432,
}


# ============================================================================
# QUERY GENERATION
# ============================================================================

def build_creatives_query(target_date: date) -> str:
    """
    Build the BigQuery query for creatives with the specified date.
    
    Args:
        target_date: Target date for filtering creatives (earliest_date)
        
    Returns:
        SQL query string
    """
    date_str = target_date.strftime('%Y-%m-%d')
    
    query = f"""
WITH per_creative AS (
  SELECT
    cs.creative_id,
    ANY_VALUE(cs.advertiser_id) AS advertiser_id,
    MIN(PARSE_DATE('%Y-%m-%d', rs.first_shown)) AS earliest_date
  FROM bigquery-public-data.google_ads_transparency_center.creative_stats  AS cs
  CROSS JOIN UNNEST(cs.region_stats) AS rs
  WHERE cs.ad_format_type = 'VIDEO'
  GROUP BY cs.creative_id
)
SELECT creative_id, advertiser_id
FROM per_creative
WHERE earliest_date = DATE '{date_str}';
"""
    return query


# ============================================================================
# CLIENT INITIALIZATION
# ============================================================================

def get_bigquery_client() -> bigquery.Client:
    """
    Initialize and return BigQuery client with service account credentials.
    
    Returns:
        BigQuery client instance
        
    Raises:
        FileNotFoundError: If credentials file doesn't exist
        GoogleCloudError: If client creation fails
    """
    if CREDENTIALS_PATH and os.path.exists(CREDENTIALS_PATH):
        # Load credentials from JSON file
        with open(CREDENTIALS_PATH, 'r') as f:
            credentials_info = json.load(f)
        
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        
        client = bigquery.Client(
            credentials=credentials,
            project=PROJECT_ID,
            location=BIGQUERY_LOCATION
        )
        print(f"✓ BigQuery client created with service account: {credentials_info.get('client_email')}")
    else:
        # Use Application Default Credentials (ADC)
        client = bigquery.Client(
            project=PROJECT_ID,
            location=BIGQUERY_LOCATION
        )
        print("✓ BigQuery client created with Application Default Credentials")
    
    return client


def get_storage_client() -> storage.Client:
    """
    Initialize and return GCS storage client with service account credentials.
    
    Returns:
        Storage client instance
        
    Raises:
        FileNotFoundError: If credentials file doesn't exist
        GoogleCloudError: If client creation fails
    """
    if CREDENTIALS_PATH and os.path.exists(CREDENTIALS_PATH):
        # Load credentials from JSON file
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
        # Use Application Default Credentials (ADC)
        client = storage.Client(project=PROJECT_ID)
        print("✓ Storage client created with Application Default Credentials")
    
    return client


# ============================================================================
# GCS BUCKET SETUP
# ============================================================================

def ensure_bucket_exists(storage_client: storage.Client, bucket_name: str, location: str = "US") -> storage.Bucket:
    """
    Create GCS bucket if it doesn't exist.
    
    Args:
        storage_client: GCS storage client
        bucket_name: Name of the bucket to create/verify
        location: Geographic location (must match BigQuery location)
        
    Returns:
        Bucket instance
        
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
# BIGQUERY QUERY EXECUTION AND EXPORT TO GCS
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
    
    This operation uses BigQuery query job with destination to GCS,
    which is efficient and FREE for exporting query results.
    
    Args:
        bq_client: BigQuery client
        storage_client: GCS storage client (for verification)
        query: SQL query string to execute
        bucket_name: GCS bucket name
        blob_name: Optional GCS blob name. If None, auto-generates with timestamp.
        
    Returns:
        Dict with export details:
        {
            'success': bool,
            'destination_uri': str,
            'blob_name': str,
            'file_size_mb': float,
            'duration_seconds': float,
            'job_id': str,
            'total_rows': int,
            'error': str (if failed)
        }
    """
    start_time = datetime.utcnow()
    temp_table_ref = None
    temp_table_id = None
    
    try:
        # Generate blob name if not provided
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
        
        # BigQuery requires writing query results to a table first, then exporting
        # Create a temporary table reference in the project's dataset
        dataset_ref = bq_client.dataset("transparency_data", project=PROJECT_ID)
        temp_table_name = f"_temp_creatives_export_{int(datetime.utcnow().timestamp())}"
        temp_table_ref = dataset_ref.table(temp_table_name)
        temp_table_id = f"{PROJECT_ID}.transparency_data.{temp_table_name}"
        
        print("Executing query to temporary table...")
        print(f"Full Query:\n{query}")
        
        # Configure query job to write results to temporary table
        job_config = bigquery.QueryJobConfig()
        job_config.destination = temp_table_ref
        job_config.write_disposition = bigquery.WriteDisposition.WRITE_TRUNCATE
        job_config.allow_large_results = True
        
        # Execute query
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
            # Clean up temp table on error
            _cleanup_temp_table(bq_client, temp_table_ref, temp_table_id)
            return {
                'success': False,
                'error': error_msg,
                'query_job_id': query_job.job_id
            }
        
        # Now export the temporary table to GCS
        print("Exporting temporary table to GCS...")
        extract_job_config = bigquery.ExtractJobConfig()
        extract_job_config.destination_format = bigquery.DestinationFormat.CSV
        extract_job_config.print_header = True  # Include CSV header row
        
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
            # Clean up temp table on error
            _cleanup_temp_table(bq_client, temp_table_ref, temp_table_id)
            return {
                'success': False,
                'error': error_msg,
                'query_job_id': query_job.job_id,
                'export_job_id': extract_job.job_id
            }
        
        # Get query job statistics
        total_bytes_processed = getattr(query_job, 'total_bytes_processed', None)
        
        # Get file info from GCS - wait a moment for blob to be written
        time.sleep(2)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # Try to reload the blob, with retries
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
        
        # Clean up temporary table
        _cleanup_temp_table(bq_client, temp_table_ref, temp_table_id)
        
        return {
            'success': True,
            'destination_uri': destination_uri,
            'blob_name': blob_name,
            'file_size_mb': file_size_mb,
            'duration_seconds': duration,
            'query_job_id': query_job.job_id,
            'export_job_id': extract_job.job_id,
            'total_bytes_processed': total_bytes_processed
        }
        
    except NotFound as e:
        error_msg = f"Resource not found: {str(e)}"
        print(f"✗ {error_msg}")
        if temp_table_ref:
            _cleanup_temp_table(bq_client, temp_table_ref, temp_table_id if 'temp_table_id' in locals() else "unknown")
        return {
            'success': False,
            'error': error_msg,
            'error_type': 'NotFound'
        }
    except GoogleCloudError as e:
        error_msg = f"Google Cloud error: {str(e)}"
        print(f"✗ {error_msg}")
        if temp_table_ref:
            _cleanup_temp_table(bq_client, temp_table_ref, temp_table_id if 'temp_table_id' in locals() else "unknown")
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
            _cleanup_temp_table(bq_client, temp_table_ref, temp_table_id if 'temp_table_id' in locals() else "unknown")
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
# DOWNLOAD FROM GCS
# ============================================================================

def download_from_gcs(
    storage_client: storage.Client,
    bucket_name: str,
    blob_name: str,
    local_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Download file from GCS to local filesystem.
    
    Args:
        storage_client: GCS storage client
        bucket_name: GCS bucket name
        blob_name: Name of the blob/file in GCS
        local_path: Local file path. If None, uses gcs_exports/ folder with blob name.
        
    Returns:
        Dict with download details:
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
        
        # Set local path
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
        
        # Download file
        blob.download_to_filename(local_path)
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        download_speed = file_size_mb / duration if duration > 0 else 0
        
        # Verify download
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
        
    except NotFound as e:
        error_msg = f"Blob not found: {str(e)}"
        print(f"✗ {error_msg}")
        return {
            'success': False,
            'error': error_msg,
            'error_type': 'NotFound'
        }
    except GoogleCloudError as e:
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
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': error_msg,
            'error_type': type(e).__name__
        }


# ============================================================================
# POSTGRES IMPORT (STAGING + COPY + UPSERT)
# ============================================================================

def normalize_source_to_two_columns(source_csv_path: str) -> Tuple[str, int, int]:
    """
    Create a temp CSV with only columns: creative_id, advertiser_id.
    Returns: (temp_csv_path, total_rows_read, rows_written)
    """
    total_read = 0
    total_written = 0

    tmp = tempfile.NamedTemporaryFile(mode='w+', suffix='.csv', delete=False, newline='')
    tmp_path = tmp.name

    try:
        with open(source_csv_path, 'r', encoding='utf-8', newline='') as f_in, tmp:
            sample = f_in.read(2048)
            f_in.seek(0)
            try:
                delimiter = csv.Sniffer().sniff(sample).delimiter
            except Exception:
                delimiter = ','

            reader = csv.DictReader(f_in, delimiter=delimiter)

            writer = csv.writer(tmp)
            writer.writerow(['creative_id', 'advertiser_id'])

            for row in reader:
                total_read += 1
                creative_id = (row.get('creative_id') or '').strip()
                advertiser_id = (row.get('advertiser_id') or '').strip()
                if not creative_id or not advertiser_id:
                    continue
                writer.writerow([creative_id, advertiser_id])
                total_written += 1

        return tmp_path, total_read, total_written
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def upsert_from_normalized_csv(csv_path: str, target_date: date) -> Tuple[int, int]:
    """
    Upsert creatives from a two-column CSV using staging + COPY.

    Sets created_at for both new rows and duplicates to the provided target_date
    (cast to timestamp at midnight).

    Returns: (staged_rows, upserted_rows)
    """
    created_at_literal = target_date.strftime('%Y-%m-%d')  # DATE literal, casts to timestamp

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TEMP TABLE staging_daily_creatives (
                        creative_id   TEXT,
                        advertiser_id TEXT
                    ) ON COMMIT DROP;
                """)

                with open(csv_path, 'r', encoding='utf-8') as f:
                    cur.copy_expert(
                        """
                        COPY staging_daily_creatives (creative_id, advertiser_id)
                        FROM STDIN WITH (FORMAT CSV, HEADER TRUE)
                        """,
                        f
                    )

                cur.execute("SELECT COUNT(*) FROM staging_daily_creatives;")
                staged = cur.fetchone()[0]

                # Insert and upsert with created_at set to the import's target date
                cur.execute(
                    """
                    INSERT INTO creatives_fresh (creative_id, advertiser_id, created_at)
                    SELECT creative_id, advertiser_id, %s::timestamp
                    FROM staging_daily_creatives
                    ON CONFLICT (creative_id)
                    DO UPDATE SET
                        advertiser_id = EXCLUDED.advertiser_id,
                        created_at    = EXCLUDED.created_at;
                    """,
                    (created_at_literal,)
                )
                upserted = cur.rowcount

        return staged, upserted
    finally:
        conn.close()


# ============================================================================
# CHECK EXISTING FILE IN GCS
# ============================================================================

def check_file_exists_in_gcs(
    storage_client: storage.Client,
    bucket_name: str,
    blob_name: str
) -> bool:
    """
    Check if a file exists in GCS bucket.
    
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


# ============================================================================
# CLEANUP OLD FILES FROM GCS
# ============================================================================

def cleanup_old_files_from_gcs(
    storage_client: storage.Client,
    bucket_name: str,
    file_prefix: str,
    current_date: str
) -> Dict[str, Any]:
    """
    Delete old files from GCS that match the prefix pattern and are not from today.
    
    Args:
        storage_client: GCS storage client
        bucket_name: GCS bucket name
        file_prefix: Prefix to match files (e.g., "daily_creatives_export_")
        current_date: Today's date in YYYYMMDD format
        
    Returns:
        Dict with cleanup statistics:
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
            # Extract date from filename (format: daily_creatives_export_YYYYMMDD.csv)
            # Get the part after the prefix and before .csv
            filename = blob.name
            if not filename.startswith(file_prefix) or not filename.endswith('.csv'):
                continue
            
            # Extract date portion
            date_part = filename[len(file_prefix):-4]  # Remove prefix and .csv extension
            
            # Check if it's a valid date format (YYYYMMDD = 8 characters)
            if len(date_part) != 8 or not date_part.isdigit():
                print(f"  ⚠ Skipping file with unexpected format: {filename}")
                continue
            
            # Check if it's from an older day
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
                # Future date (shouldn't happen, but handle it)
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
# MAIN WORKFLOW
# ============================================================================

def main() -> int:
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='Export creatives from BigQuery to GCS, download, and optionally import to PostgreSQL',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export creatives for today's date
  %(prog)s

  # Export creatives for a specific date
  %(prog)s --date 2025-11-01

  # Export creatives for yesterday
  %(prog)s --date $(date -d yesterday +%%Y-%%m-%%d)

  # Export and import into PostgreSQL (created_at set to target date)
  %(prog)s --date 2025-10-31 --import-db
        """
    )
    
    parser.add_argument(
        '--date',
        type=str,
        help='Target date in YYYY-MM-DD format (default: today)',
        default=None
    )
    parser.add_argument(
        '--import-db',
        action='store_true',
        help='After download, import CSV into PostgreSQL creatives_fresh using staging + COPY + upsert'
    )
    
    args = parser.parse_args()
    
    # Parse date argument
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        except ValueError:
            print(f"✗ Invalid date format: {args.date}. Expected YYYY-MM-DD format.")
            return 1
    else:
        target_date = date.today()
    
    print("\n" + "="*80)
    print("BigQuery Creatives Query → GCS → Download Workflow")
    print("="*80 + "\n")
    print(f"Target date: {target_date}")
    
    try:
        # Verify credentials file exists
        if not os.path.exists(CREDENTIALS_PATH):
            print(f"✗ Credentials file not found: {CREDENTIALS_PATH}")
            print("  Please ensure the credentials file exists or set GOOGLE_APPLICATION_CREDENTIALS environment variable.")
            sys.exit(1)
        
        # Build query with target date
        query = build_creatives_query(target_date)
        
        # Initialize clients
        print("Initializing clients...")
        bq_client = get_bigquery_client()
        storage_client = get_storage_client()
        print()
        
        # Ensure bucket exists
        ensure_bucket_exists(storage_client, GCS_BUCKET_NAME, BIGQUERY_LOCATION)
        
        # Get date string for filename and cleanup
        date_timestamp = target_date.strftime('%Y%m%d')
        today_timestamp = datetime.utcnow().strftime('%Y%m%d')
        blob_name = f"{GCS_FILE_PREFIX}{date_timestamp}.csv"
        
        # Clean up old files from GCS (before checking/creating today's file)
        # COMMENTED OUT FOR NOW
        # print(f"\nCleaning up old files from GCS...")
        # print(f"  Looking for files with prefix: {GCS_FILE_PREFIX}")
        # cleanup_stats = cleanup_old_files_from_gcs(
        #     storage_client,
        #     GCS_BUCKET_NAME,
        #     GCS_FILE_PREFIX,
        #     today_timestamp
        # )
        # if cleanup_stats['errors']:
        #     print(f"  ⚠ Warnings during cleanup: {len(cleanup_stats['errors'])} error(s)")
        
        print(f"\nChecking if file for target date already exists in GCS...")
        print(f"  Looking for: gs://{GCS_BUCKET_NAME}/{blob_name}")
        
        if check_file_exists_in_gcs(storage_client, GCS_BUCKET_NAME, blob_name):
            print(f"✓ File for target date already exists in GCS")
            print(f"  Skipping BigQuery query and export, downloading existing file...")
            
            # Create a mock export_result for existing file
            export_result = {
                'success': True,
                'destination_uri': f"gs://{GCS_BUCKET_NAME}/{blob_name}",
                'blob_name': blob_name,
                'duration_seconds': 0.0,
                'skipped_export': True
            }
        else:
            print(f"  File not found, proceeding with query and export...")
            
            # Step 1: Execute query and export to GCS
            export_result = execute_query_and_export_to_gcs(
                bq_client,
                storage_client,
                query,
                GCS_BUCKET_NAME,
                blob_name=blob_name  # Use target date for filename
            )
            
            if not export_result['success']:
                print(f"\n✗ Export failed: {export_result['error']}")
                sys.exit(1)
        
        # Step 2: Download from GCS
        download_result = download_from_gcs(
            storage_client,
            GCS_BUCKET_NAME,
            export_result['blob_name']
        )
        
        if not download_result['success']:
            print(f"\n✗ Download failed: {download_result['error']}")
            sys.exit(1)
        
        # Optional: Import into PostgreSQL creatives_fresh
        if args.import_db:
            print(f"\n{'='*80}")
            print("PostgreSQL Import")
            print(f"{'='*80}")
            print(f"Normalizing CSV to two columns (creative_id, advertiser_id)...")
            tmp_csv, read_rows, written_rows = normalize_source_to_two_columns(download_result['local_path'])
            print(f"  Normalized rows: read={read_rows:,}, kept={written_rows:,}")

            try:
                print("Upserting into creatives_fresh (created_at = target date)...")
                staged, upserted = upsert_from_normalized_csv(tmp_csv, target_date)
                print(f"  Staged rows:   {staged:,}")
                print(f"  Upserted rows: {upserted:,}")
                print("✓ PostgreSQL import complete")
            finally:
                try:
                    os.unlink(tmp_csv)
                except Exception:
                    pass

        # Summary
        print(f"\n{'='*80}")
        print("✓ Workflow Completed Successfully")
        print(f"{'='*80}")
        print(f"Target Date:   {target_date}")
        print(f"Query Source:  bigquery-public-data.google_ads_transparency_center.creative_stats")
        print(f"GCS URI:       {export_result['destination_uri']}")
        print(f"Local File:    {download_result['local_path']}")
        print(f"File Size:     {download_result['file_size_mb']:.1f} MB")
        print(f"\nTiming:")
        if export_result.get('skipped_export'):
            print(f"  Query/Export: SKIPPED (file already existed)")
            print(f"  Download:     {download_result['duration_seconds']:.1f}s")
            print(f"  Total:        {download_result['duration_seconds']:.1f}s")
        else:
            print(f"  Query/Export: {export_result['duration_seconds']:.1f}s")
            print(f"  Download:     {download_result['duration_seconds']:.1f}s")
            print(f"  Total:        {export_result['duration_seconds'] + download_result['duration_seconds']:.1f}s")
        print(f"\nCost:")
        print(f"  BigQuery Query: $0.00 (FREE for public datasets!)")
        print(f"  GCS Download:   $0.00 (same region)")
        print(f"  Total:          $0.00")
        
        # Note: PostgreSQL operations commented out for now
        # TODO: Add PostgreSQL import functionality if needed in the future
        # Example:
        # import_csv_to_postgres(download_result['local_path'])
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        return 1
    except Exception as e:
        print(f"\n✗ Fatal error: {str(e)}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

