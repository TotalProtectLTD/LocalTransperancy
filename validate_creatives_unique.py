#!/usr/bin/env python3
"""
Validate Creative IDs Uniqueness Across CSV Files

This script validates that every creative_id is unique across all CSV export files
for the specified date range (October 20-30, 2025).

Checks:
- Each creative_id appears only once across all files
- Reports duplicates if found
- Provides statistics about total and unique creative_ids
"""

import os
import sys
from collections import defaultdict
from typing import Dict, Set, List, Tuple
from datetime import datetime, timedelta


# ============================================================================
# CONFIGURATION
# ============================================================================

# Local export directory
LOCAL_EXPORT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "gcs_exports"
)

# Date range to validate (October 1-31, 2025)
START_DATE = "2025-10-01"
END_DATE = "2025-10-31"


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def parse_date_string(date_str: str) -> datetime:
    """Parse date string in YYYY-MM-DD format."""
    return datetime.strptime(date_str, '%Y-%m-%d')


def generate_file_dates(start_date: str, end_date: str) -> List[str]:
    """
    Generate list of date strings for file names.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format (inclusive)
        
    Returns:
        List of date strings in YYYYMMDD format
    """
    start = parse_date_string(start_date)
    end = parse_date_string(end_date)
    
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime('%Y%m%d'))
        current += timedelta(days=1)
    
    return dates


def read_creative_ids_from_file(file_path: str) -> Dict[str, int]:
    """
    Read creative_ids from a CSV file and return a dictionary with counts.
    
    Args:
        file_path: Path to CSV file
        
    Returns:
        Dictionary mapping creative_id to count (should be 1 for unique IDs)
    """
    creative_ids = defaultdict(int)
    
    if not os.path.exists(file_path):
        print(f"  ⚠ Warning: File not found: {file_path}")
        return creative_ids
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # Skip header
            header = f.readline().strip()
            
            # Validate header
            if not header.startswith('creative_id'):
                print(f"  ⚠ Warning: Unexpected header in {file_path}: {header}")
            
            line_num = 1  # Start from 1 (after header)
            for line in f:
                line_num += 1
                line = line.strip()
                if not line:
                    continue
                
                # Parse CSV line (simple split, assuming no commas in values)
                parts = line.split(',')
                if len(parts) < 1:
                    print(f"  ⚠ Warning: Invalid line {line_num} in {file_path}: {line}")
                    continue
                
                creative_id = parts[0].strip()
                if creative_id:
                    creative_ids[creative_id] += 1
                
    except Exception as e:
        print(f"  ✗ Error reading {file_path}: {e}")
        return creative_ids
    
    return creative_ids


def validate_creatives_unique(
    date_range_start: str,
    date_range_end: str,
    file_prefix: str = "daily_creatives_export_"
) -> Tuple[bool, Dict[str, any]]:
    """
    Validate that all creative_ids are unique across all files in the date range.
    
    Args:
        date_range_start: Start date in YYYY-MM-DD format
        date_range_end: End date in YYYY-MM-DD format (inclusive)
        file_prefix: Prefix for CSV file names
        
    Returns:
        Tuple of (is_valid: bool, stats: dict)
    """
    print(f"\n{'='*80}")
    print("Creative IDs Uniqueness Validation")
    print(f"{'='*80}")
    print(f"Date Range: {date_range_start} to {date_range_end}")
    print(f"Directory: {LOCAL_EXPORT_DIR}")
    print(f"File Prefix: {file_prefix}")
    print()
    
    # Generate list of dates
    date_strings = generate_file_dates(date_range_start, date_range_end)
    
    print(f"Checking {len(date_strings)} files...")
    print()
    
    # Read all creative_ids from all files
    all_creative_ids = defaultdict(list)  # Maps creative_id to list of (file, line_count)
    file_stats = {}
    
    for date_str in date_strings:
        file_name = f"{file_prefix}{date_str}.csv"
        file_path = os.path.join(LOCAL_EXPORT_DIR, file_name)
        
        print(f"  Reading: {file_name}...", end=" ", flush=True)
        
        # Read creative_ids from this file
        file_creative_ids = read_creative_ids_from_file(file_path)
        
        # Track statistics per file
        file_count = sum(file_creative_ids.values())
        file_unique = len(file_creative_ids)
        file_stats[file_name] = {
            'total': file_count,
            'unique': file_unique,
            'duplicates_in_file': file_count - file_unique
        }
        
        # Check for duplicates within the file itself
        file_duplicates = {cid: count for cid, count in file_creative_ids.items() if count > 1}
        if file_duplicates:
            print(f"⚠ WARNING: {len(file_duplicates)} duplicate(s) found within file!")
            for dup_id, count in list(file_duplicates.items())[:5]:  # Show first 5
                print(f"    - {dup_id} appears {count} times")
        else:
            print(f"✓ {file_unique:,} unique creative_ids")
        
        # Add to overall tracking
        for creative_id, count in file_creative_ids.items():
            all_creative_ids[creative_id].append({
                'file': file_name,
                'count': count
            })
    
    print()
    print(f"{'='*80}")
    print("Analysis Results")
    print(f"{'='*80}")
    
    # Calculate overall statistics
    total_creative_ids = sum(len(ids) for ids in all_creative_ids.values())
    unique_creative_ids = len(all_creative_ids)
    
    # Find duplicates across files
    duplicates = {}
    for creative_id, occurrences in all_creative_ids.items():
        if len(occurrences) > 1:
            duplicates[creative_id] = occurrences
    
    # Summary
    print(f"\nOverall Statistics:")
    print(f"  Total creative_id occurrences: {total_creative_ids:,}")
    print(f"  Unique creative_ids:           {unique_creative_ids:,}")
    print(f"  Duplicates found:              {len(duplicates):,}")
    
    if duplicates:
        print(f"\n✗ VALIDATION FAILED: Found {len(duplicates):,} creative_id(s) that appear in multiple files")
        print(f"\nDuplicate Details (showing first 10):")
        count = 0
        for creative_id, occurrences in duplicates.items():
            if count >= 10:
                print(f"  ... and {len(duplicates) - 10} more duplicate(s)")
                break
            files = [occ['file'] for occ in occurrences]
            print(f"  {creative_id} appears in {len(files)} file(s): {', '.join(files)}")
            count += 1
        
        # If there are more duplicates, offer to save full report
        if len(duplicates) > 10:
            print(f"\n  Saving full duplicate report to: duplicates_report.txt")
            save_duplicates_report(duplicates, LOCAL_EXPORT_DIR)
    else:
        print(f"\n✓ VALIDATION PASSED: All creative_ids are unique across all files!")
    
    # Per-file statistics
    print(f"\n{'='*80}")
    print("Per-File Statistics")
    print(f"{'='*80}")
    print(f"{'File':<40} {'Total IDs':<12} {'Unique':<12} {'Duplicates':<12}")
    print(f"{'-'*80}")
    for file_name, stats in sorted(file_stats.items()):
        print(f"{file_name:<40} {stats['total']:>11,} {stats['unique']:>11,} {stats['duplicates_in_file']:>11,}")
    
    is_valid = len(duplicates) == 0
    
    return is_valid, {
        'total_occurrences': total_creative_ids,
        'unique_creative_ids': unique_creative_ids,
        'duplicates_count': len(duplicates),
        'duplicates': duplicates,
        'file_stats': file_stats,
        'date_range': (date_range_start, date_range_end),
        'files_checked': len(date_strings)
    }


def save_duplicates_report(duplicates: Dict[str, List], output_dir: str) -> None:
    """Save a detailed report of all duplicates to a file."""
    report_path = os.path.join(output_dir, "duplicates_report.txt")
    
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("Creative IDs Duplicates Report\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Total duplicates found: {len(duplicates)}\n\n")
            
            for creative_id, occurrences in sorted(duplicates.items()):
                files = [occ['file'] for occ in occurrences]
                f.write(f"creative_id: {creative_id}\n")
                f.write(f"  Appears in {len(files)} file(s):\n")
                for file_name in files:
                    f.write(f"    - {file_name}\n")
                f.write("\n")
        
        print(f"  ✓ Report saved to: {report_path}")
    except Exception as e:
        print(f"  ✗ Error saving report: {e}")


# ============================================================================
# MAIN WORKFLOW
# ============================================================================

def main() -> int:
    """Main execution function."""
    try:
        # Validate date range
        parse_date_string(START_DATE)
        parse_date_string(END_DATE)
        
        # Check if export directory exists
        if not os.path.exists(LOCAL_EXPORT_DIR):
            print(f"✗ Error: Export directory not found: {LOCAL_EXPORT_DIR}")
            return 1
        
        # Run validation
        is_valid, stats = validate_creatives_unique(
            START_DATE,
            END_DATE,
            file_prefix="daily_creatives_export_"
        )
        
        # Print final summary
        print(f"\n{'='*80}")
        if is_valid:
            print("✓ VALIDATION PASSED")
        else:
            print("✗ VALIDATION FAILED")
        print(f"{'='*80}")
        print(f"Files checked: {stats['files_checked']}")
        print(f"Total creative_id occurrences: {stats['total_occurrences']:,}")
        print(f"Unique creative_ids: {stats['unique_creative_ids']:,}")
        print(f"Duplicates: {stats['duplicates_count']:,}")
        
        return 0 if is_valid else 1
        
    except ValueError as e:
        print(f"✗ Error: Invalid date format: {e}")
        print(f"  Expected format: YYYY-MM-DD")
        return 1
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        return 1
    except Exception as e:
        print(f"\n✗ Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

