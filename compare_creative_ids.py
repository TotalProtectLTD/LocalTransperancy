#!/usr/bin/env python3
"""
Compare two creative ID lists and find duplicates.
"""

def load_creative_ids(filepath):
    """Load creative IDs from a file, one per line."""
    ids = set()
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line:  # Skip empty lines
                ids.add(line)
    return ids

def main():
    debug_file = 'debug/all_creative_ids.txt'
    bluevision_file = 'bluevision/all_creative_ids.txt'
    
    print("Loading creative IDs from files...")
    debug_ids = load_creative_ids(debug_file)
    bluevision_ids = load_creative_ids(bluevision_file)
    
    print(f"\nStatistics:")
    print(f"  Debug file: {len(debug_ids):,} unique IDs")
    print(f"  Bluevision file: {len(bluevision_ids):,} unique IDs")
    
    # Find duplicates (intersection)
    duplicates = debug_ids & bluevision_ids
    
    print(f"\nDuplicates (shared IDs):")
    print(f"  Total duplicates: {len(duplicates):,}")
    print(f"  Percentage of debug file: {len(duplicates)/len(debug_ids)*100:.2f}%")
    print(f"  Percentage of bluevision file: {len(duplicates)/len(bluevision_ids)*100:.2f}%")
    
    # Find unique to each file
    only_debug = debug_ids - bluevision_ids
    only_bluevision = bluevision_ids - debug_ids
    
    print(f"\nUnique to each file:")
    print(f"  Only in debug: {len(only_debug):,}")
    print(f"  Only in bluevision: {len(only_bluevision):,}")
    
    # Optionally save duplicates to a file
    if duplicates:
        output_file = 'duplicate_creative_ids.txt'
        with open(output_file, 'w') as f:
            for dup in sorted(duplicates):
                f.write(dup + '\n')
        print(f"\nDuplicates saved to: {output_file}")
    
    # Optionally save unique IDs to files
    if only_debug:
        output_file = 'unique_to_debug_creative_ids.txt'
        with open(output_file, 'w') as f:
            for id in sorted(only_debug):
                f.write(id + '\n')
        print(f"Unique to debug saved to: {output_file}")
    
    if only_bluevision:
        output_file = 'unique_to_bluevision_creative_ids.txt'
        with open(output_file, 'w') as f:
            for id in sorted(only_bluevision):
                f.write(id + '\n')
        print(f"Unique to bluevision saved to: {output_file}")

if __name__ == '__main__':
    main()

