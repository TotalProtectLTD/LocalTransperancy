# Cache Validation Strategies - Complete Guide

## Your Questions Answered

### 1. Version Extraction (Improved)

**Old Approach (Pattern-based):**
```python
# ❌ Problem: Assumes specific prefix that might change
pattern = r'(acx-tfaar-tfaa-report-ui-frontend_auto_\d{8}-\d{4}_RC\d+)'
```

**New Approach (Path-based):**
```python
# ✅ Solution: Extracts full path regardless of naming convention
def extract_version_from_url(url):
    # URL: https://www.gstatic.com/acx/transparency/report/FOLDER/main.dart.js
    # Returns: /acx/transparency/report/FOLDER
    
    path = urlparse(url).path
    version_path = path.rsplit('/main.dart.js', 1)[0]
    return version_path
```

**Why This Is Better:**
- ✅ Works with **any** folder structure
- ✅ No assumptions about naming conventions
- ✅ Captures the entire path as version identifier
- ✅ More robust and future-proof

**Examples:**
```
URL: https://www.gstatic.com/acx/transparency/report/acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000/main.dart.js
Version: /acx/transparency/report/acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000

URL: https://www.gstatic.com/some/other/path/v2.0/main.dart.js
Version: /some/other/path/v2.0

URL: https://example.com/completely/different/structure/main.dart.js
Version: /completely/different/structure
```

### 2. Cache Validation Logic

**Your Question:** "If version is not changed we claim that cached files valid all the time?"

**Answer:** **NO!** The cache has multiple validation layers:

## Cache Validation Strategies

You can now choose different validation strategies based on your needs:

### Strategy 1: `age_and_version` (DEFAULT - Most Strict)

```python
CACHE_VALIDATION_STRATEGY = 'age_and_version'
CACHE_MAX_AGE_HOURS = 24
```

**Logic:**
```
┌─────────────────────────────────────┐
│ 1. Check if version changed         │
│    ├─ YES → Invalidate cache        │
│    └─ NO → Continue to step 2       │
└─────────────────────────────────────┘
                ↓
┌─────────────────────────────────────┐
│ 2. Check if cache age > 24 hours    │
│    ├─ YES → Invalidate cache        │
│    └─ NO → Serve from cache         │
└─────────────────────────────────────┘
```

**When Cache Is Valid:**
- ✅ Version matches **AND**
- ✅ Age < 24 hours

**When Cache Is Invalid:**
- ❌ Version changed **OR**
- ❌ Age > 24 hours

**Example Timeline:**
```
Hour 0:  Download and cache (version: /path/v1)
Hour 1:  Cache hit (version matches, age: 1h) ✅
Hour 12: Cache hit (version matches, age: 12h) ✅
Hour 23: Cache hit (version matches, age: 23h) ✅
Hour 25: Cache miss (version matches, but age: 25h > 24h) ❌ Re-download
Hour 26: Cache hit (version matches, age: 1h) ✅

--- Google deploys new version ---

Hour 27: Cache miss (version changed: /path/v1 → /path/v2) ❌ Re-download
Hour 28: Cache hit (new version, age: 1h) ✅
```

### Strategy 2: `version_only` (Ignore Age)

```python
CACHE_VALIDATION_STRATEGY = 'version_only'
```

**Logic:**
```
┌─────────────────────────────────────┐
│ Check if version changed            │
│    ├─ YES → Invalidate cache        │
│    └─ NO → Serve from cache         │
└─────────────────────────────────────┘
```

**When Cache Is Valid:**
- ✅ Version matches (age doesn't matter)

**When Cache Is Invalid:**
- ❌ Version changed

**Use Case:**
- When you trust Google's versioning completely
- When you want to minimize re-downloads
- When bandwidth is more important than freshness

**Example Timeline:**
```
Hour 0:   Download and cache (version: /path/v1)
Hour 1:   Cache hit ✅
Hour 24:  Cache hit ✅ (age doesn't matter)
Hour 48:  Cache hit ✅ (age doesn't matter)
Hour 168: Cache hit ✅ (1 week old, still valid!)

--- Google deploys new version ---

Hour 169: Cache miss (version changed) ❌ Re-download
Hour 170: Cache hit ✅
```

### Strategy 3: `age_only` (Ignore Version)

```python
CACHE_VALIDATION_STRATEGY = 'age_only'
CACHE_MAX_AGE_HOURS = 24
```

**Logic:**
```
┌─────────────────────────────────────┐
│ Check if cache age > 24 hours       │
│    ├─ YES → Invalidate cache        │
│    └─ NO → Serve from cache         │
└─────────────────────────────────────┘
```

**When Cache Is Valid:**
- ✅ Age < 24 hours (version doesn't matter)

**When Cache Is Invalid:**
- ❌ Age > 24 hours

**Use Case:**
- When you don't trust version detection
- When you want regular refreshes regardless of version
- When you want predictable cache behavior

**Example Timeline:**
```
Hour 0:  Download and cache
Hour 1:  Cache hit ✅
Hour 23: Cache hit ✅
Hour 25: Cache miss (age > 24h) ❌ Re-download
Hour 26: Cache hit ✅

--- Google deploys new version (but age < 24h) ---

Hour 27: Cache hit ✅ (serves OLD version! Version change ignored)
Hour 50: Cache miss (age > 24h) ❌ Re-download (gets NEW version)
```

**⚠️ Warning:** This strategy might serve outdated files if Google deploys within the 24-hour window!

### Strategy 4: `always_revalidate` (No Cache)

```python
CACHE_VALIDATION_STRATEGY = 'always_revalidate'
```

**Logic:**
```
┌─────────────────────────────────────┐
│ Always invalidate cache             │
│ → Download every time               │
└─────────────────────────────────────┘
```

**When Cache Is Valid:**
- ❌ Never (always re-downloads)

**Use Case:**
- Debugging
- Testing
- When you need absolute freshness
- When bandwidth is not a concern

**Example Timeline:**
```
Hour 0: Download ❌
Hour 1: Download ❌
Hour 2: Download ❌
...
(No bandwidth savings, always fresh)
```

## Configuration Examples

### Example 1: Maximum Freshness (Recommended for Production)

```python
CACHE_VALIDATION_STRATEGY = 'age_and_version'
CACHE_MAX_AGE_HOURS = 6  # Refresh every 6 hours
VERSION_AWARE_CACHING = True
```

**Behavior:**
- Invalidates on version change
- Invalidates after 6 hours
- Best balance of freshness and bandwidth

### Example 2: Maximum Bandwidth Savings

```python
CACHE_VALIDATION_STRATEGY = 'version_only'
CACHE_MAX_AGE_HOURS = 0  # Ignored
VERSION_AWARE_CACHING = True
```

**Behavior:**
- Only invalidates on version change
- Cache can be days/weeks old
- Minimal re-downloads

### Example 3: Time-Based Only (No Version Tracking)

```python
CACHE_VALIDATION_STRATEGY = 'age_only'
CACHE_MAX_AGE_HOURS = 12
VERSION_AWARE_CACHING = False
```

**Behavior:**
- Refreshes every 12 hours
- Ignores version changes
- Predictable behavior

### Example 4: No Cache (Testing)

```python
CACHE_VALIDATION_STRATEGY = 'always_revalidate'
```

**Behavior:**
- Downloads every time
- No bandwidth savings
- Always fresh

## Special Configuration: No Age Limit

```python
CACHE_VALIDATION_STRATEGY = 'age_and_version'
CACHE_MAX_AGE_HOURS = 0  # 0 = no age limit
VERSION_AWARE_CACHING = True
```

**Behavior:**
- Only invalidates on version change
- Age check is skipped
- Equivalent to 'version_only' but more explicit

## Server Validation (Future Enhancement)

```python
SERVER_VALIDATION_ENABLED = True
```

**How It Would Work:**
1. Check version (as usual)
2. Check age (as usual)
3. **Make HEAD request to server** with `If-None-Match: <etag>`
4. If server returns `304 Not Modified` → serve from cache
5. If server returns `200 OK` → download new version

**Benefits:**
- Maximum freshness guarantee
- Detects changes even without version change
- Small network overhead (HEAD request only)

**Cost:**
- Extra network request per file
- Slightly slower (adds ~50-100ms per file)

**Not Yet Implemented** (placeholder in code)

## Comparison Table

| Strategy | Checks Version | Checks Age | Bandwidth | Freshness | Use Case |
|----------|---------------|------------|-----------|-----------|----------|
| `age_and_version` | ✅ | ✅ | Medium | High | **Recommended** |
| `version_only` | ✅ | ❌ | Low | Medium | Max savings |
| `age_only` | ❌ | ✅ | Medium | Medium | No version trust |
| `always_revalidate` | ❌ | ❌ | High | Maximum | Testing/Debug |

## Real-World Scenarios

### Scenario 1: Google Deploys New Version

**Setup:** `age_and_version`, cache age: 2 hours

```
Request comes in with URL: .../new_version/main.dart.js
                                ↓
Check version: /old_version vs /new_version
Result: MISMATCH ❌
                                ↓
Invalidate cache, download new version
                                ↓
Cache is now fresh (age: 0h, version: new)
```

### Scenario 2: Cache Is Old But Version Same

**Setup:** `age_and_version`, cache age: 30 hours, max: 24 hours

```
Request comes in with URL: .../same_version/main.dart.js
                                ↓
Check version: /same_version vs /same_version
Result: MATCH ✅
                                ↓
Check age: 30h vs 24h max
Result: TOO OLD ❌
                                ↓
Invalidate cache, download fresh copy
                                ↓
Cache is now fresh (age: 0h, version: same)
```

### Scenario 3: Cache Is Fresh And Version Same

**Setup:** `age_and_version`, cache age: 5 hours, max: 24 hours

```
Request comes in with URL: .../same_version/main.dart.js
                                ↓
Check version: /same_version vs /same_version
Result: MATCH ✅
                                ↓
Check age: 5h vs 24h max
Result: FRESH ✅
                                ↓
Serve from cache (12.77 KB instead of 1.26 MB)
                                ↓
98.99% bandwidth savings!
```

## Monitoring Cache Behavior

### Check Current Strategy

```bash
grep "CACHE_VALIDATION_STRATEGY" fighting_cache_problem.py
```

### View Cache Invalidations

```bash
grep "CACHE INVALIDATE" /tmp/fighting_cache_output.log
```

### See Why Cache Was Invalidated

```bash
# Version changes
grep "version changed" /tmp/fighting_cache_output.log

# Age expiration
grep "age.*>.*max" /tmp/fighting_cache_output.log
```

### Cache Hit Rate

```bash
# Count cache hits
HITS=$(grep -c "CACHE HIT" /tmp/fighting_cache_output.log)

# Count cache misses
MISSES=$(grep -c "CACHE MISS" /tmp/fighting_cache_output.log)

# Calculate hit rate
echo "Cache Hit Rate: $(python3 -c "print(f'{$HITS/($HITS+$MISSES)*100:.1f}%')")"
```

## Recommendations

### For Production Scraping

```python
CACHE_VALIDATION_STRATEGY = 'age_and_version'
CACHE_MAX_AGE_HOURS = 12  # Refresh twice daily
VERSION_AWARE_CACHING = True
```

**Why:**
- Catches version changes immediately
- Refreshes regularly even without version change
- Good balance of freshness and bandwidth

### For High-Frequency Scraping

```python
CACHE_VALIDATION_STRATEGY = 'version_only'
CACHE_MAX_AGE_HOURS = 0  # No age limit
VERSION_AWARE_CACHING = True
```

**Why:**
- Minimizes re-downloads
- Relies on Google's versioning
- Maximum bandwidth savings

### For Testing/Development

```python
CACHE_VALIDATION_STRATEGY = 'always_revalidate'
```

**Why:**
- Always gets fresh data
- No cache-related bugs
- Easy debugging

## Summary

**Your Questions Answered:**

1. **Version Extraction:** Now uses full path extraction instead of pattern matching - works with any URL structure

2. **Cache Validity:** Cache is **NOT** valid "all the time" - it's validated based on:
   - **Version changes** (URL path changed)
   - **Age limits** (cache too old)
   - **Strategy choice** (you control the logic)

**Default Behavior:**
- Strategy: `age_and_version`
- Max age: 24 hours
- Cache is valid only if **both** version matches **and** age < 24 hours

**You Have Full Control:**
- Choose validation strategy
- Set age limits (or disable)
- Enable/disable version tracking
- Force revalidation if needed

The cache system is now **flexible, robust, and transparent**!

