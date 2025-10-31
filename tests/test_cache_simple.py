#!/usr/bin/env python3
"""
Simple cache test to debug the redownloading issue.
"""

import sys
from cache_storage import load_from_cache
from cache_models import extract_version_from_url, get_cache_filename

# URL that should be cached
test_url = "https://www.gstatic.com/acx/transparency/report/acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000/main.dart.js"

print("Testing cache...")
print(f"Request URL: {test_url}")
print()

# Extract version and filename
version = extract_version_from_url(test_url)
filename = get_cache_filename(test_url)

print(f"Extracted version: {version}")
print(f"Filename: {filename}")
print()

# Try to load from cache
print("Loading from cache...")
result = load_from_cache(test_url)

if result[0]:
    content, metadata = result
    print(f"✅ CACHE HIT!")
    print(f"   Content size: {len(content):,} bytes")
    print(f"   Metadata: {metadata}")
    if metadata:
        print(f"   Cached URL: {metadata.get('url')}")
        print(f"   Cached version: {metadata.get('version')}")
        print(f"   Cached at: {metadata.get('cached_at')}")
else:
    print(f"❌ CACHE MISS")
    if result[1]:
        print(f"   Metadata available: {result[1]}")


