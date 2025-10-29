# How To Speed Up Batch Processing - Deep Analysis

## Current Performance

**Baseline** (1 worker, 1 batch of 20):
- Total time: 162.5s
- Per creative: 8.1s average
- Bottleneck: Content.js downloads (5-7s = 70-80% of time)

## Timing Breakdown

```
Creative 1 (HTML):   15.54s | [Page: 9.42s] [Content.js: 6.03s] [Extract: 0.02s]
Creative 2 (API):     9.52s | [API: 2.90s] [Content.js: 6.62s] [Extract: 0.00s]
Creative 3 (API):     9.74s | [API: 3.56s] [Content.js: 6.18s] [Extract: 0.00s]
Creative 4 (API):     ~5-10s | [API: ~3s] [Content.js: 5-7s] [Extract: 0.00s]
```

**Key observation**: During content.js download (5-7s), CPU is idle - just waiting for network!

---

## Optimization Ideas (Ranked by Impact)

### 🥇 Idea #1: Parallel Creatives Within Batch (HIGHEST IMPACT)

**Concept**: Process multiple creatives simultaneously within same batch.

**Current flow**:
```
Creative 2: [API call] → [wait 3s] → [Content.js] → [wait 6s] → [Extract]
Creative 3: [API call] → [wait 3s] → [Content.js] → [wait 6s] → [Extract]
Creative 4: [API call] → [wait 3s] → [Content.js] → [wait 6s] → [Extract]
Total: 9s + 9s + 9s = 27s
```

**Parallel flow**:
```
Time   Creative 2              Creative 3              Creative 4
────   ──────────────────────  ──────────────────────  ──────────────────────
0s     [API call starts]       [API call starts]       [API call starts]
3s     [Content.js download]   [Content.js download]   [Content.js download]
9s     [Extract & done]        [Extract & done]        [Extract & done]
────
Total: 9s (3× speedup!)
```

**Why it works**:
- Network I/O is the bottleneck (70-80% of time)
- While waiting for one creative's download, process others
- Browser can handle multiple parallel requests
- All creatives share same cookies/session

**Potential speedup**: **3-5× faster** (for 19 API-only creatives)

**Implementation**:
```python
# Process API-only creatives in chunks of 3-5
for chunk in chunks(creative_batch[1:], chunk_size=3):
    tasks = [scrape_ads_transparency_api_only(...) for creative in chunk]
    results = await asyncio.gather(*tasks)  # All 3 run in parallel
```

**Risks**:
- Rate limiting: Google might throttle parallel requests from same IP
- Memory: Multiple pages open simultaneously
- Cookie concurrency: Need to ensure thread-safe cookie access

**Mitigation**:
- Start conservative (2-3 parallel)
- Monitor for rate limiting errors
- Test with small batch first

---

### 🥈 Idea #2: Pipeline API Calls and Downloads (MEDIUM IMPACT)

**Concept**: Start next creative's API call while current creative's content.js is downloading.

**Current flow**:
```
Creative 2: [API 3s] → [Download 6s] → [Extract 0.5s]
Creative 3:              [API 3s] → [Download 6s] → [Extract 0.5s]
Total: 9.5s + 9.5s = 19s
```

**Pipelined flow**:
```
Creative 2: [API 3s] → [Download 6s] → [Extract 0.5s]
Creative 3:     [API 3s] → [Download 6s] → [Extract 0.5s]
                    ↑ Starts while Creative 2 is downloading
Total: 9.5s + 6.5s = 16s (saved 3s = 16% faster)
```

**Why it works**:
- API calls are fast (~3s) but mostly waiting
- Can overlap API waiting with content.js downloading
- No extra browser contexts needed

**Potential speedup**: **15-20% faster**

**Implementation**:
```python
# Start next API call as soon as current one starts downloading
api_futures = []
download_futures = []

for creative in batch[1:]:
    # Start API call immediately
    api_future = asyncio.create_task(call_api(creative))
    api_futures.append(api_future)
    
    # When ready, start download
    api_result = await api_future
    download_future = asyncio.create_task(download_contentjs(api_result))
    download_futures.append(download_future)
    
    # Don't wait for download, move to next creative
```

**Risks**:
- Complexity: More complex code flow
- Errors: Harder to track which creative failed

---

### 🥉 Idea #3: Optimize First Page Load (LOW-MEDIUM IMPACT)

**Concept**: Reduce first creative's 9.42s page load time.

**Current**: Wait for domcontentloaded (9.42s)

**Potential optimizations**:

**A. Extract cookies earlier**
```python
# Start extracting cookies as soon as API response arrives
# Don't wait for all content.js to load
cookies = await context.cookies()  # Extract after 3-4s instead of 15s
```
**Speedup**: Could save 5-10s on first creative

**B. Skip unnecessary waiting**
```python
# Current: Wait for all content.js (6s)
# Alternative: Extract cookies immediately after first content.js
await page.goto(url, wait_until='domcontentloaded')
await asyncio.sleep(2)  # Wait for initial API call only
cookies = await context.cookies()
# Continue with rest of batch
```
**Speedup**: Could save 4-6s on first creative

**C. Use lighter page load**
```python
# Instead of full page, load minimal HTML just to get cookies
# Then use API-only for even the first creative
```
**Speedup**: Could reduce first creative from 15s to 8s (7s saved)

**Why it might work**:
- First creative is slowest (15.54s)
- We only need cookies from it, not full extraction
- Could treat it more like API-only

**Potential speedup**: **30-40% faster for first creative** (saves 5-10s per batch)

**Risks**:
- Cookies might not be set early enough
- May need to wait for specific API call

---

### 💡 Idea #4: Batch API Calls (LOW IMPACT)

**Concept**: Make multiple GetCreativeById calls in one request.

**Current**: 1 API call per creative
```
API call 1: GetCreativeById(creative_2)
API call 2: GetCreativeById(creative_3)
API call 3: GetCreativeById(creative_4)
Total: 3 × 3s = 9s
```

**Batched**:
```
API call: GetCreativeById([creative_2, creative_3, creative_4])
Total: 1 × 3s = 3s (saved 6s)
```

**Why it might not work**:
- Google's API probably doesn't support batch requests
- Would need to reverse engineer API format
- Risk of breaking when Google updates API

**Potential speedup**: **20-30% faster** (if API supports it)

**Risks**: HIGH - API format unknown, might break easily

---

### 🔧 Idea #5: HTTP/2 Connection Reuse (ALREADY DONE)

**Status**: ✅ Playwright already does this

Playwright automatically:
- Reuses HTTP/2 connections
- Uses connection pooling
- Multiplexes requests

**No additional speedup available.**

---

### 🔧 Idea #6: Cache Content.js (NOT VIABLE)

**Concept**: Cache content.js files to avoid re-downloading.

**Why it won't work**:
- Each creative has unique content.js URLs
- URLs include creative-specific parameters
- Files are dynamic, not reusable
- No cache hits across creatives

**Speedup**: 0% (not applicable)

---

### 🔧 Idea #7: Skip Unnecessary Extraction (MINIMAL IMPACT)

**Concept**: Make extraction optional/faster.

**Current**: Extract videos, App Store IDs, funded_by, validate everything

**Optimized**:
```python
# Skip validation in production mode
if not debug_mode:
    skip_validation()  # Save ~0.5s per creative
```

**Speedup**: ~5-10% faster (0.5s per creative)

**Trade-off**: Less error detection

---

## Combined Optimization Strategy

### Strategy A: Aggressive Parallelism (RECOMMENDED)

**Combine**:
1. Parallel creatives within batch (3-5 at once)
2. Optimized first page load (extract cookies earlier)

**Expected speedup**:
```
Current:  162s for 20 creatives
Optimized: 40s for 20 creatives (4× faster!)

Breakdown:
- First creative: 7s (optimized from 15.54s)
- Remaining 19 in chunks of 3: (19/3) × 9s = 57s
- Parallel speedup: 57s / 3 = 19s
- Total: 7s + 19s = 26s

With overhead: ~30-40s (still 4-5× faster!)
```

**Implementation complexity**: Medium  
**Risk**: Medium (rate limiting possible)

---

### Strategy B: Conservative Pipelining (SAFE)

**Combine**:
1. Pipeline API calls and downloads
2. Optimize first page load

**Expected speedup**:
```
Current:  162s for 20 creatives
Optimized: 120s for 20 creatives (25% faster)

Breakdown:
- First creative: 7s (optimized from 15.54s)
- Remaining 19 pipelined: 19 × 7s = 133s
- Pipelining saves 15%: 133s × 0.85 = 113s
- Total: 7s + 113s = 120s
```

**Implementation complexity**: Low  
**Risk**: Low

---

### Strategy C: Multi-Worker + Parallel Creatives (MAXIMUM SPEED)

**Combine**:
1. Use 5 workers (as already suggested)
2. Each worker processes 3 creatives in parallel

**Expected speedup**:
```
Current (1 worker):  162s for 20 creatives

With 5 workers: 162s / 5 = 32s

With 5 workers + 3 parallel per worker:
- Each worker handles 4 creatives
- With 3 parallel: 4 creatives in ~12s
- Total: ~12-15s for 20 creatives

**10× faster!**
```

**Implementation complexity**: High  
**Risk**: High (rate limiting very likely)

---

## Recommended Next Steps

### Phase 1: Test Parallel Creatives (Quick Win)

**Change**: Process 2-3 API-only creatives in parallel within batch

**Expected gain**: 2-3× faster  
**Risk**: Low  
**Effort**: 1-2 hours coding

**Test**:
```bash
# Run with 2 parallel creatives per batch
python3 test_batch_with_mitmproxy.py
# Compare: 162s → 60-80s
```

---

### Phase 2: Optimize First Load (Medium Win)

**Change**: Extract cookies earlier, skip unnecessary waiting

**Expected gain**: 30-50% faster for first creative  
**Risk**: Low  
**Effort**: 1 hour coding

---

### Phase 3: Full Parallelism (Big Win, More Risk)

**Change**: 5 workers + 3 parallel per worker

**Expected gain**: 5-10× faster  
**Risk**: Medium (rate limiting)  
**Effort**: 2-3 hours coding + testing

---

## Bottleneck Summary

| Operation | Current Time | Can Optimize? | How Much? |
|-----------|-------------|---------------|-----------|
| Content.js download | 5-7s (70%) | ✅ Yes (parallel) | 3-5× |
| First page load | 9.4s | ✅ Yes (optimize) | 30-50% |
| API calls | 2-3s (20%) | ✅ Yes (pipeline) | 15-20% |
| Extraction | <0.5s (5%) | ❌ No | Already fast |
| Network latency | 3-5s | ❌ No | Server limited |

---

## Final Recommendation

**Start with**: Parallel creatives within batch (Idea #1)  
**Reason**: Biggest impact, medium risk, clear implementation  
**Expected**: 3-4× speedup with 3-5 parallel creatives  
**Next**: Add first page optimization for another 30%  
**Future**: Scale to multiple workers for 5-10× total speedup

---

**Analysis Date**: 2025-10-28  
**Current Performance**: 8.1s per creative  
**Target Performance**: 2-3s per creative (3-4× faster)  
**Maximum Potential**: 1-2s per creative (with full parallelism + multi-worker)


