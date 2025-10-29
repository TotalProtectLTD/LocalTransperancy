# Sequential Fetch Analysis - Why API-Only Method is Slow

## Problem Observed

When running with 1 worker, the logs show operations happening **one line at a time** with noticeable delays:

```
[Worker 0] 🔄 Batch (17/20): CR0862645801463... (API-only)
🍪 Adding 1 cookies to context...              ← instant
📤 Making API request...                        ← instant  
📥 API response received...                     ← wait ~500-1000ms
📤 Fetching content.js 1/2...                   ← instant
📥 Response status: 200...                      ← wait ~500-1000ms
✓ Fetched content.js 1/2 (154921 bytes...)     ← instant
📤 Fetching content.js 2/2...                   ← instant
📥 Response status: 200...                      ← wait ~500-1000ms
✓ Fetched content.js 2/2 (154949 bytes...)     ← instant
```

**Total time per creative**: ~2-3 seconds (mostly waiting for network)

## Root Cause: Sequential Fetching

### Code Location

**File**: `google_ads_transparency_scraper_optimized.py`  
**Function**: `scrape_ads_transparency_api_only()`  
**Lines**: 885-920

### The Problem Code

```python
content_js_responses = []
for i, url in enumerate(content_js_urls, 1):  # ❌ SEQUENTIAL LOOP
    try:
        # Fetch content.js with gzip compression
        print(f"  📤 Fetching content.js {i}/{len(content_js_urls)}: {url[:80]}...")
        
        response = await page.request.get(  # ⏳ AWAIT - blocks until complete
            url,
            headers={"accept-encoding": "gzip, deflate, br"}
        )
        
        print(f"  📥 Response status: {response.status}...")
        content_text = await response.text()  # ⏳ AWAIT - blocks until complete
        
        content_js_responses.append((url, content_text))
```

### Why It's Slow

**Sequential execution timeline** (for 2 content.js files):

```
Time (ms)    Operation
------------ ------------------------------------------
0            Start fetch content.js #1
500          Receive content.js #1 (network latency)
500          Start fetch content.js #2        ← WAITED 500ms doing nothing!
1000         Receive content.js #2 (network latency)
------------ ------------------------------------------
TOTAL: 1000ms
```

**Problems**:
1. **Network latency dominates**: Each request has ~200-500ms round-trip time
2. **Sequential waiting**: While waiting for file #1, we could be fetching file #2
3. **Underutilized connection**: Browser/connection sits idle between requests
4. **No parallelization**: With 4 files, we wait 4× the latency

### Breakdown of Times

For a typical creative with 2 content.js files:

| Operation | Time | Cumulative |
|-----------|------|------------|
| Add cookies | ~5ms | 5ms |
| Make API request (send) | ~5ms | 10ms |
| **Wait for API response** | **~500ms** | 510ms |
| Parse API response | ~10ms | 520ms |
| Start fetch content.js #1 | ~5ms | 525ms |
| **Wait for content.js #1** | **~500ms** | 1025ms |
| Process content.js #1 | ~20ms | 1045ms |
| Start fetch content.js #2 | ~5ms | 1050ms |
| **Wait for content.js #2** | **~500ms** | **1550ms** |
| Process content.js #2 | ~20ms | 1570ms |
| Extract data | ~50ms | 1620ms |
| Validate | ~10ms | 1630ms |

**Total**: ~1.6-2 seconds per creative (mostly network waiting)

### Why You See "Slow" Line-by-Line Output

The `print()` statements appear slowly because:
1. **Network I/O is slow**: Each `await` blocks the execution
2. **Real-time logging**: Each print happens when the operation completes
3. **Human perception**: 500ms delays are very noticeable
4. **Sequential bottleneck**: No overlap between operations

## Solution: Parallel Fetching

### Optimized Code (using asyncio.gather)

```python
# ❌ CURRENT (Sequential - SLOW)
content_js_responses = []
for i, url in enumerate(content_js_urls, 1):
    response = await page.request.get(url, headers=...)  # Waits for each
    content_text = await response.text()
    content_js_responses.append((url, content_text))

# ✅ OPTIMIZED (Parallel - FAST)
async def fetch_content_js(url):
    """Fetch a single content.js file."""
    response = await page.request.get(url, headers={"accept-encoding": "gzip, deflate, br"})
    content_text = await response.text()
    return (url, content_text)

# Fetch all content.js files in parallel
print(f"  📤 Fetching {len(content_js_urls)} content.js files in parallel...")
fetch_tasks = [fetch_content_js(url) for url in content_js_urls]
content_js_responses = await asyncio.gather(*fetch_tasks)
print(f"  ✅ All {len(content_js_urls)} content.js files fetched!")
```

### Performance Improvement

**Parallel execution timeline** (for 2 content.js files):

```
Time (ms)    Operation
------------ ------------------------------------------
0            Start fetch content.js #1 AND #2 simultaneously
500          Receive both content.js #1 AND #2
------------ ------------------------------------------
TOTAL: 500ms (2× faster!)
```

**For 4 content.js files**:
- Sequential: ~2000ms (4 × 500ms)
- Parallel: ~500ms (max latency among all)
- **Speedup**: 4× faster!

### Expected Improvement

| Scenario | Sequential | Parallel | Speedup |
|----------|-----------|----------|---------|
| 2 files | 1000ms | 500ms | 2× |
| 3 files | 1500ms | 500ms | 3× |
| 4 files | 2000ms | 500ms | 4× |
| Average (2.5 files) | 1250ms | 500ms | 2.5× |

**Overall creative processing time**:
- Current: ~1.6-2.0 seconds
- With parallel fetch: ~0.8-1.2 seconds
- **Improvement**: ~40-50% faster

## Why This Wasn't a Problem in Full HTML Method

The original `scrape_ads_transparency_page()` doesn't have this issue because:

1. **Browser handles it**: When you navigate to an HTML page, the browser automatically:
   - Fetches all resources in parallel
   - Uses HTTP/2 multiplexing
   - Optimizes connection reuse

2. **Response handler captures**: Content.js files are fetched by the browser and captured by the response handler automatically, in parallel

3. **No manual fetching**: We don't explicitly fetch each file one by one

## Impact on Batch Processing

### Current Performance (Sequential)

**For a batch of 20 creatives**:
- First creative (HTML): ~4-6 seconds
- Remaining 19 (API-only, sequential): 19 × 1.6s = ~30 seconds
- **Total**: ~34-36 seconds per batch

### With Parallel Fetching

**For a batch of 20 creatives**:
- First creative (HTML): ~4-6 seconds
- Remaining 19 (API-only, parallel): 19 × 0.8s = ~15 seconds
- **Total**: ~19-21 seconds per batch
- **Speedup**: ~40-45% faster batches

### At Scale (1,000 creatives)

| Metric | Sequential | Parallel | Improvement |
|--------|-----------|----------|-------------|
| **Time per batch** | 35 sec | 20 sec | 43% faster |
| **Total batches** | 50 | 50 | - |
| **Total time** | 29 min | 17 min | **12 min saved** |
| **Throughput** | 34 creative/min | 59 creative/min | 73% higher |

## Additional Observations

### Why It Feels Even Slower with 1 Worker

With 1 worker, you see **every operation in sequence** with no parallelism:
- No other workers processing simultaneously
- No overlap between batches
- Every network wait is visible
- Human perception amplifies the slowness

With 5 workers:
- Other workers process while one waits
- Output is interleaved, feels faster
- System appears more responsive
- But each individual creative still takes the same time

### Network Latency Breakdown

**Typical network request**:
```
DNS lookup:        ~20ms  (cached after first)
TCP handshake:     ~50ms  (reused in HTTP/2)
TLS handshake:     ~100ms (reused in HTTP/2)
Request send:      ~5ms
Server processing: ~50ms
Response receive:  ~100-300ms (depends on file size)
------------------------
TOTAL:            ~325-525ms per request
```

For 2 files sequentially: 650-1050ms  
For 2 files in parallel: 325-525ms (max of both)

## Recommendations

### 1. Implement Parallel Fetching (HIGH PRIORITY)

**Benefit**: 40-50% faster API-only creatives  
**Effort**: Medium (refactor content.js fetching loop)  
**Risk**: Low (asyncio.gather is well-tested)

### 2. Reduce Logging Verbosity (OPTIONAL)

Instead of logging each file:
```python
# Before: 4 lines per file
📤 Fetching content.js 1/2...
📥 Response status: 200...
✓ Fetched content.js 1/2 (154921 bytes...)

# After: 1 line total
✅ Fetched 2 content.js files (309KB total)
```

### 3. Add Progress Bar (NICE TO HAVE)

For better user experience with multiple files:
```
Fetching 4 content.js: [██████████] 4/4 (600KB)
```

## Conclusion

### What's Happening

The API-only method is **waiting for network I/O sequentially**:
- Each content.js file takes ~500ms to fetch
- Files are fetched one after another (not in parallel)
- Total wait time = number of files × latency per file
- You see this as "slow" line-by-line output

### Why It's Slow

1. **Sequential fetching**: for loop with await (blocks on each file)
2. **Network latency**: 200-500ms round-trip per request
3. **No parallelization**: Idle time while waiting for responses
4. **Multiple files**: Typical creative has 2-4 content.js files

### Fix Priority

**RECOMMENDED**: Implement parallel fetching using `asyncio.gather()`
- **Impact**: 40-50% faster per creative, 12+ minutes saved per 1,000 creatives
- **Complexity**: Medium (requires refactoring loop)
- **Risk**: Low (standard asyncio pattern)

---

**Status**: ✅ FIXED AND DEPLOYED (2025-10-28)

**Previous State**: ⚠️ WORKING but SUBOPTIMAL (sequential fetching)  
**Current State**: ✅ OPTIMAL (parallel fetching, 2-4× faster on this operation)

See `PARALLEL_FETCH_SUCCESS.md` for implementation details and test results.

