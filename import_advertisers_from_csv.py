#!/usr/bin/env python3
"""
Import Advertisers from CSV Files to PostgreSQL

Efficiently imports advertisers data from GCS export CSV files into the
PostgreSQL advertisers table using temporary table + COPY + bulk merge approach.

Features:
- Handles 3.5M+ rows efficiently (~8-14 minutes)
- Uses PostgreSQL COPY for fast bulk loading
- Temporary UNLOGGED table (no WAL overhead)
- Duplicate skipping with ON CONFLICT
- Proper handling of country codes and empty values
- Progress tracking and statistics

Usage:
    # Import latest CSV from gcs_exports directory
    python3 import_advertisers_from_csv.py
    
    # Import specific file
    python3 import_advertisers_from_csv.py daily_advertisers_export_20251030.csv
    
    # Import all CSV files in directory
    python3 import_advertisers_from_csv.py --all
"""

import os
import sys
import csv
import glob
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

# Database configuration (matches advertiser_utils.py and setup_database.py)
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432
}

# Default CSV directory
CSV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gcs_exports')


@contextmanager
def get_db_connection():
    """Context manager for database connections."""
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


def normalize_name(name: str) -> str:
    """
    Normalize advertiser name for case-insensitive matching.
    
    Args:
        name: Advertiser name
    
    Returns:
        Normalized name (lowercase, stripped)
    """
    return name.lower().strip() if name else ""


def normalize_country(country: str) -> Optional[str]:
    """
    Normalize country code: empty string or whitespace -> NULL.
    
    Args:
        country: Country code from CSV (may be empty string "")
    
    Returns:
        Country code or None if empty
    """
    if not country:
        return None
    country = country.strip().strip('"')
    return country if country else None


def create_temp_table(cursor) -> None:
    """
    Create temporary table for CSV data.
    
    Temporary tables are automatically dropped at end of session and are
    optimized for bulk operations (minimal WAL overhead).
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
    
    This is the fastest way to bulk load data into PostgreSQL.
    
    Args:
        cursor: Database cursor
        csv_file_path: Path to CSV file
    
    Returns:
        Number of rows loaded
    """
    print(f"  📥 Loading CSV into temporary table using COPY...")
    start_time = time.time()
    
    # Use COPY FROM with CSV format for proper handling of quoted fields
    with open(csv_file_path, 'r', encoding='utf-8') as csv_file:
        # Use copy_expert with CSV format to handle quoted fields properly
        cursor.copy_expert(
            """
            COPY advertisers_temp (advertiser_id, advertiser_name, advertiser_location)
            FROM STDIN
            WITH (FORMAT CSV, HEADER true, DELIMITER ',', QUOTE '"', ESCAPE '"')
            """,
            csv_file
        )
    
    # Get row count
    cursor.execute("SELECT COUNT(*) FROM advertisers_temp")
    row_count = cursor.fetchone()[0]
    
    duration = time.time() - start_time
    print(f"  ✅ Loaded {row_count:,} rows in {duration:.1f}s ({row_count/duration:.0f} rows/s)")
    
    return row_count


def merge_temp_to_main_table(cursor) -> Dict[str, int]:
    """
    Merge data from temp table to main advertisers table.
    
    Uses INSERT ... ON CONFLICT DO NOTHING to skip duplicates.
    Handles normalization and country code conversion.
    
    Args:
        cursor: Database cursor
    
    Returns:
        Dictionary with statistics: {'inserted': int, 'skipped': int}
    """
    print(f"  🔄 Merging data from temp table to main table...")
    start_time = time.time()
    
    # Get row count before merge
    cursor.execute("SELECT COUNT(*) FROM advertisers_temp")
    temp_count = cursor.fetchone()[0]
    
    # Perform bulk merge with normalization
    # NULLIF converts empty strings to NULL for country
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
    """Get statistics about the advertisers table."""
    stats = {}
    
    # Total count
    cursor.execute("SELECT COUNT(*) FROM advertisers")
    stats['total'] = cursor.fetchone()[0]
    
    # Count by country
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
    
    Args:
        csv_file_path: Path to CSV file
        dry_run: If True, don't actually import (just validate)
    
    Returns:
        Dictionary with import statistics
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
        return {'dry_run': True}
    
    start_time = time.time()
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Step 1: Create temporary table
            print(f"\n1️⃣  Creating temporary table...")
            create_temp_table(cursor)
            conn.commit()
            
            # Step 2: Copy CSV to temp table
            print(f"\n2️⃣  Copying CSV data to temporary table...")
            row_count = copy_csv_to_temp_table(cursor, csv_file_path)
            conn.commit()
            
            # Step 3: Merge from temp to main table
            print(f"\n3️⃣  Merging to main table (with duplicate skipping)...")
            merge_stats = merge_temp_to_main_table(cursor)
            print(f"    Committing merge transaction...")
            conn.commit()
            print(f"    ✅ Commit successful")
            
            # Step 4: Get final statistics
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
            print(f"Insert rate:       {merge_stats['inserted']/total_duration:.0f}d rows/s")
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
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'csv_file': csv_file_name,
            'error': str(e)
        }


def find_csv_files(csv_dir: str, pattern: Optional[str] = None) -> List[str]:
    """
    Find CSV files in the specified directory.
    
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


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Import advertisers from CSV files to PostgreSQL',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import latest CSV file from gcs_exports directory
  %(prog)s
  
  # Import specific file
  %(prog)s daily_advertisers_export_20251030.csv
  
  # Import all CSV files in directory
  %(prog)s --all
  
  # Dry run (validate without importing)
  %(prog)s --dry-run
        """
    )
    
    parser.add_argument(
        'csv_file',
        nargs='?',
        help='CSV file name or pattern (if not provided, imports latest)'
    )
    parser.add_argument(
        '--all',
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
        default=CSV_DIR,
        help=f'CSV directory (default: {CSV_DIR})'
    )
    
    args = parser.parse_args()
    
    print("="*80)
    print("ADVERTISERS CSV IMPORT TOOL")
    print("="*80)
    print(f"CSV directory: {args.dir}")
    
    try:
        # Find CSV files to import
        if args.all:
            # Import all CSV files
            csv_files = find_csv_files(args.dir)
            if not csv_files:
                print(f"❌ No CSV files found in {args.dir}")
                sys.exit(1)
            print(f"\nFound {len(csv_files)} CSV file(s) to import")
        elif args.csv_file:
            # Import specific file
            csv_files = find_csv_files(args.dir, args.csv_file)
        else:
            # Import latest file
            csv_files = find_csv_files(args.dir)
            if csv_files:
                csv_files = [csv_files[0]]  # Latest file only
                print(f"\nImporting latest file: {os.path.basename(csv_files[0])}")
            else:
                print(f"❌ No CSV files found in {args.dir}")
                sys.exit(1)
        
        # Import each file
        results = []
        for csv_file in csv_files:
            result = import_csv_file(csv_file, dry_run=args.dry_run)
            results.append(result)
            
            if not result.get('success'):
                print(f"\n❌ Import failed for {csv_file}")
                sys.exit(1)
        
        # Final summary if multiple files
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
        
        print(f"\n✅ All imports completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

