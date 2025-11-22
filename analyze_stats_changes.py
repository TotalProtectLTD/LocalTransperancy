#!/usr/bin/env python3
"""
Analyze differences between two app statistics files to determine if:
1. Only new data points are added
2. Historical data points are modified
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

def load_json_file(filepath: str) -> dict:
    """Load and parse JSON file"""
    with open(filepath, 'r') as f:
        return json.load(f)

def analyze_metric(metric_name: str, old_data: dict, new_data: dict) -> Dict:
    """
    Compare a single metric between old and new files
    
    Returns:
        Dict with analysis results including:
        - unchanged_count: number of historical points that didn't change
        - changed_points: list of (index, old_value, new_value) tuples
        - new_points_added: number of new points added
        - total_old: total points in old data
        - total_new: total points in new data
    """
    old_points = old_data.get('points', [])
    new_points = new_data.get('points', [])
    
    old_count = len(old_points)
    new_count = len(new_points)
    
    # Find the overlap (compare up to the length of the shorter array)
    overlap_length = min(old_count, new_count)
    
    changed_points = []
    unchanged_count = 0
    
    for i in range(overlap_length):
        if old_points[i] != new_points[i]:
            changed_points.append((i, old_points[i], new_points[i]))
        else:
            unchanged_count += 1
    
    return {
        'metric_name': metric_name,
        'first_date_old': old_data.get('first_date'),
        'first_date_new': new_data.get('first_date'),
        'total_old': old_count,
        'total_new': new_count,
        'overlap_length': overlap_length,
        'unchanged_count': unchanged_count,
        'changed_points': changed_points,
        'new_points_added': new_count - old_count,
        'points_removed': old_count - new_count if new_count < old_count else 0
    }

def calculate_date_for_index(first_date: str, index: int, aggregation: str = 'day') -> str:
    """Calculate the actual date for a given index"""
    if not first_date:
        return f"Index {index}"
    
    try:
        date_obj = datetime.strptime(first_date, "%Y-%m-%d")
        if aggregation == 'day':
            target_date = date_obj + timedelta(days=index)
        else:
            target_date = date_obj + timedelta(days=index)  # Default to days
        return target_date.strftime("%Y-%m-%d")
    except:
        return f"Index {index}"

def print_analysis_report(old_file: str, new_file: str):
    """Generate and print comprehensive analysis report"""
    
    print("=" * 80)
    print("APP STATISTICS COMPARISON ANALYSIS")
    print("=" * 80)
    print(f"\nOlder File: {old_file}")
    print(f"Newer File: {new_file}")
    print()
    
    # Load data
    old_data = load_json_file(old_file)
    new_data = load_json_file(new_file)
    
    # Extract the first data object (assuming structure with data array)
    old_stats = old_data['data'][0]
    new_stats = new_data['data'][0]
    
    # Metrics to analyze
    metrics = ['downloads', 'revenue', 'top_free', 'top_grossing']
    
    all_results = []
    total_changes = 0
    total_new_points = 0
    
    for metric in metrics:
        if metric in old_stats and metric in new_stats:
            result = analyze_metric(metric, old_stats[metric], new_stats[metric])
            all_results.append(result)
            total_changes += len(result['changed_points'])
            total_new_points += result['new_points_added']
    
    # Print summary
    print("SUMMARY")
    print("-" * 80)
    print(f"Total historical data points changed: {total_changes}")
    print(f"Total new data points added: {total_new_points}")
    print()
    
    if total_changes == 0:
        print("✓ RESULT: New file ONLY ADDS new data, NO historical changes detected")
    else:
        print("✗ RESULT: New file MODIFIES historical data in addition to adding new points")
    
    print("\n" + "=" * 80)
    print("DETAILED BREAKDOWN BY METRIC")
    print("=" * 80)
    
    # Print detailed results for each metric
    for result in all_results:
        print(f"\n{'─' * 80}")
        print(f"METRIC: {result['metric_name'].upper()}")
        print(f"{'─' * 80}")
        print(f"First date (old): {result['first_date_old']}")
        print(f"First date (new): {result['first_date_new']}")
        print(f"Total points (old): {result['total_old']}")
        print(f"Total points (new): {result['total_new']}")
        print(f"New points added: {result['new_points_added']}")
        
        if result['first_date_old'] != result['first_date_new']:
            print(f"\n⚠️  WARNING: First date changed from {result['first_date_old']} to {result['first_date_new']}")
        
        print(f"\nHistorical data comparison (first {result['overlap_length']} points):")
        print(f"  - Unchanged: {result['unchanged_count']}")
        print(f"  - Changed: {len(result['changed_points'])}")
        
        if result['changed_points']:
            print(f"\n  Changed data points:")
            for idx, old_val, new_val in result['changed_points'][:10]:  # Show first 10
                date_str = calculate_date_for_index(result['first_date_old'], idx)
                diff = new_val - old_val
                diff_str = f"+{diff}" if diff > 0 else str(diff)
                print(f"    [{idx:3d}] {date_str}: {old_val:6d} → {new_val:6d} ({diff_str})")
            
            if len(result['changed_points']) > 10:
                print(f"    ... and {len(result['changed_points']) - 10} more changed points")
        else:
            print(f"  ✓ No changes in historical data")
        
        if result['new_points_added'] > 0:
            print(f"\n  New data points added ({result['new_points_added']} points):")
            new_stats = new_data['data'][0][result['metric_name']]
            new_points = new_stats['points']
            start_idx = result['total_old']
            
            for i, idx in enumerate(range(start_idx, len(new_points))):
                if i >= 5:  # Show first 5 new points
                    print(f"    ... and {result['new_points_added'] - 5} more new points")
                    break
                date_str = calculate_date_for_index(result['first_date_new'], idx)
                print(f"    [{idx:3d}] {date_str}: {new_points[idx]}")
    
    print("\n" + "=" * 80)
    print("END OF ANALYSIS")
    print("=" * 80)

if __name__ == "__main__":
    old_file = "/Users/rostoni/Downloads/DFClenup.txt"
    new_file = "/Users/rostoni/Downloads/DFcleanup2.txt"
    
    print_analysis_report(old_file, new_file)

