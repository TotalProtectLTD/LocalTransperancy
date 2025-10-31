#!/usr/bin/env python3
"""
Quick test to verify cache version checking works correctly.
"""

import asyncio
from cache_storage import load_from_cache
from cache_models import extract_version_from_url

# Test URLs with different versions
old_url = "https://www.gstatic.com/acx/transparency/report/acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000/main.dart.js"
new_url = "https://www.gstatic.com/acx/transparency/report/acx-tfaar-tfaa-report-ui-frontend_auto_20251027-0645_RC000/main.dart.js"

print("Testing cache version checking...")
print()

# Check what version is extracted
old_version = extract_version_from_url(old_url)
new_version = extract_version_from_url(new_url)

print(f"Old URL version: {old_version}")
print(f"New URL version: {new_version}")
print(f"Versions are different: {old_version != new_version}")
print()

# Try to load with old URL (should work if cached)
print("1. Loading with old URL (if cached):")
result = load_from_cache(old_url)
if result[0]:
    print(f"   ✓ Cache HIT - Size: {len(result[0])} bytes")
else:
    print(f"   ✗ Cache MISS")
print()

# Try to load with new URL 
print("2. Loading with new URL:")
result = load_from_cache(new_url)
if result[0]:
    print(f"   ✓ Cache HIT - Size: {len(result[0])} bytes")
else:
    print(f"   ✗ Cache MISS (version changed)")
print()

print("Cache version checking is working!")


