# Cache System Guide

## Overview

The `fighting_cache_problem.py` script includes an intelligent caching system for `main.dart.js` files with automatic expiration and validation.

## Features

### 1. **Smart Caching**
- Automatically caches `main.dart.js` and part files (`main.dart.js_2.part.js`, `main.dart.js_40.part.js`)
- Stores files in `main.dart/` directory
- Saves ~5.1 MB per request (98.9% bandwidth reduction)

### 2. **Metadata Tracking**
Each cached file has an associated `.meta.json` file containing:
- `url`: Original URL
- `cached_at`: Unix timestamp when cached
- `size`: File size in bytes
- `etag`: Server ETag (for validation)
- `last_modified`: Server Last-Modified header
- `cache_control`: Server Cache-Control header

### 3. **Automatic Expiration**
- Default expiration: **24 hours**
- Configurable via `CACHE_MAX_AGE_HOURS`
- Expired files are automatically re-downloaded

### 4. **Cache Status Display**
Shows cache information at script startup:
```
Cache Status: 3 file(s) cached
  - main.dart.js_40.part.js: 605.87 KB, age: 0.0h
  - main.dart.js_2.part.js: 1.89 KB, age: 0.0h
  - main.dart.js: 4.33 MB, age: 0.0h
```

## Configuration

### Enable/Disable Caching

```python
# Enable smart caching for main.dart.js files
USE_LOCAL_CACHE_FOR_MAIN_DART = True  # Set to False to disable

# Auto-cache: Download and cache on first request
AUTO_CACHE_ON_MISS = True  # Set to False to only use existing cache
```

### Cache Expiration Settings

```python
# Maximum age of cache files in hours
CACHE_MAX_AGE_HOURS = 24  # Default: 24 hours

# Enable/disable expiration checking
CACHE_VALIDATION_ENABLED = True  # Set to False to never expire
```

## How It Works

### First Run (Cache Miss)

```
[CACHE MISS] main.dart.js not in cache or expired, downloading...
[CACHE SAVE] Saved main.dart.js to cache (4543603 bytes)

Traffic: 1.26 MB (files downloaded from server)
Duration: 13 seconds
```

**What happens:**
1. Script checks `main.dart/` directory
2. File not found → downloads from server
3. Saves file + metadata to cache
4. Serves file to browser

### Subsequent Runs (Cache Hit)

```
Cache Status: 3 file(s) cached
  - main.dart.js: 4.33 MB, age: 0.0h

[CACHE HIT] Served main.dart.js from cache (4543597 bytes, age: 0.0h)

Traffic: 12.76 KB (only essential requests)
Duration: 12 seconds
```

**What happens:**
1. Script checks cache
2. File found and valid (age < 24h)
3. Serves directly from local disk
4. No network request needed

### After 24 Hours (Cache Expired)

```
Cache Status: 3 file(s) cached
  - main.dart.js: 4.33 MB, age: 25.3h [EXPIRED]

[CACHE EXPIRED] main.dart.js is 25.3 hours old (max: 24.0h)
[CACHE MISS] main.dart.js not in cache or expired, downloading...
[CACHE SAVE] Saved main.dart.js to cache (4543603 bytes)
```

**What happens:**
1. Script detects file age > 24 hours
2. Treats as cache miss
3. Downloads fresh copy from server
4. Updates cache with new file + metadata

## Cache Directory Structure

```
main.dart/
├── main.dart.js                          # Cached file (4.3 MB)
├── main.dart.js.meta.json                # Metadata
├── main.dart.js_2.part.js                # Part file (1.9 KB)
├── main.dart.js_2.part.js.meta.json      # Metadata
├── main.dart.js_40.part.js               # Part file (606 KB)
└── main.dart.js_40.part.js.meta.json     # Metadata
```

## Metadata Example

```json
{
  "url": "https://www.gstatic.com/.../main.dart.js",
  "cached_at": 1761574585.048341,
  "size": 4543603,
  "etag": null,
  "last_modified": "Mon, 20 Oct 2025 13:57:39 GMT",
  "cache_control": "public, max-age=86400"
}
```

## Cache Validation Strategies

### Current: Age-Based Expiration ✅

**How it works:**
- Checks file age against `CACHE_MAX_AGE_HOURS`
- Simple and reliable
- No server requests needed

**Pros:**
- ✅ Fast (no network requests)
- ✅ Predictable behavior
- ✅ Works offline

**Cons:**
- ⚠️ May serve stale content if server updates before expiration
- ⚠️ May re-download unchanged files after expiration

### Future: ETag/Last-Modified Validation 🔮

**How it would work:**
1. Check cache age
2. If expired, make conditional request:
   - `If-None-Match: <etag>`
   - `If-Modified-Since: <last-modified>`
3. Server responds:
   - `304 Not Modified` → Keep cache
   - `200 OK` → Update cache

**Pros:**
- ✅ Always serves latest content
- ✅ Saves bandwidth if unchanged
- ✅ More accurate than age-based

**Cons:**
- ⚠️ Requires network request to validate
- ⚠️ More complex implementation

## Monitoring Cache Health

### Check Cache Status

The script automatically displays cache status at startup:

```python
cache_files = get_cache_status()
for cf in cache_files:
    print(f"{cf['filename']}: {cf['age_hours']:.1f}h")
```

### Manual Cache Inspection

```bash
# List all cached files
ls -lh main.dart/

# View metadata
cat main.dart/main.dart.js.meta.json | python3 -m json.tool

# Check file ages
find main.dart/ -name "*.js" -exec stat -f "%Sm %N" -t "%Y-%m-%d %H:%M:%S" {} \;
```

### Clear Cache

```bash
# Clear all cached files
rm -rf main.dart/*

# Clear only expired files (manual)
find main.dart/ -name "*.js" -mtime +1 -delete
find main.dart/ -name "*.meta.json" -mtime +1 -delete
```

## Performance Impact

### Without Cache
```
Traffic: 1.26 MB
Duration: 13 seconds
Requests: 63
```

### With Cache
```
Traffic: 12.76 KB (98.9% reduction)
Duration: 12 seconds
Requests: 39 (38% reduction)
Cache Hits: 3
```

### Bandwidth Savings

| Scenario | Per Run | 10 Runs | 100 Runs |
|----------|---------|---------|----------|
| **Without Cache** | 1.26 MB | 12.6 MB | 126 MB |
| **With Cache** | 12.76 KB | 127.6 KB | 1.28 MB |
| **Savings** | 98.9% | 99.0% | 99.0% |

## Troubleshooting

### Cache Not Working

**Symptoms:**
- Files always downloaded
- No cache hits

**Solutions:**
1. Check `USE_LOCAL_CACHE_FOR_MAIN_DART = True`
2. Check `AUTO_CACHE_ON_MISS = True`
3. Verify `main.dart/` directory exists
4. Check file permissions

### Files Always Expired

**Symptoms:**
- Cache hits but files re-downloaded every time

**Solutions:**
1. Check `CACHE_MAX_AGE_HOURS` setting
2. Verify system clock is correct
3. Check metadata files exist

### Stale Content Served

**Symptoms:**
- Old version of files served
- Server has newer version

**Solutions:**
1. Reduce `CACHE_MAX_AGE_HOURS` (e.g., 12 hours)
2. Manually clear cache: `rm -rf main.dart/*`
3. Wait for automatic expiration

## Best Practices

### Development

```python
# Shorter expiration for frequent changes
CACHE_MAX_AGE_HOURS = 1  # 1 hour

# Or disable caching entirely
USE_LOCAL_CACHE_FOR_MAIN_DART = False
```

### Production

```python
# Longer expiration for stability
CACHE_MAX_AGE_HOURS = 24  # 24 hours

# Enable validation
CACHE_VALIDATION_ENABLED = True
```

### Testing

```python
# Clear cache before each test
rm -rf main.dart/*

# Or disable auto-cache
AUTO_CACHE_ON_MISS = False
```

## Future Enhancements

### 1. Conditional Requests (ETag/Last-Modified)

```python
async def validate_cache_with_server(url, metadata):
    """Validate cache using conditional requests."""
    import aiohttp
    
    headers = {}
    if metadata.get('etag'):
        headers['If-None-Match'] = metadata['etag']
    if metadata.get('last_modified'):
        headers['If-Modified-Since'] = metadata['last_modified']
    
    async with aiohttp.ClientSession() as session:
        async with session.head(url, headers=headers) as response:
            if response.status == 304:
                # Not modified - cache still valid
                return True
            else:
                # Modified - need to re-download
                return False
```

### 2. Cache Size Limits

```python
CACHE_MAX_SIZE_MB = 100  # Maximum cache size

def cleanup_old_cache_files():
    """Remove oldest files if cache exceeds size limit."""
    # Implementation...
```

### 3. Multiple Cache Strategies

```python
CACHE_STRATEGY = 'age'  # Options: 'age', 'etag', 'hybrid'
```

### 4. Cache Statistics

```python
def get_cache_statistics():
    """Get detailed cache statistics."""
    return {
        'total_files': 3,
        'total_size': 5165951,
        'hit_rate': 0.95,
        'avg_age_hours': 12.5,
        'expired_count': 0
    }
```

## References

- [HTTP Caching (MDN)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching)
- [ETag (Wikipedia)](https://en.wikipedia.org/wiki/HTTP_ETag)
- [Cache-Control (MDN)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control)

