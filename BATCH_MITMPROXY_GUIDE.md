# Measuring Batch Bandwidth with Mitmproxy

## Quick Answer

To measure bandwidth for **1 batch (20 creatives)** with mitmproxy:

```bash
python3 test_batch_with_mitmproxy.py
```

That's it! The script handles everything automatically.

---

## What It Does

The test script (`test_batch_with_mitmproxy.py`):

1. ✅ Fetches 20 pending creatives from database (1 batch)
2. ✅ Starts mitmproxy for bandwidth measurement
3. ✅ Processes batch with session reuse optimization:
   - First creative: Full HTML load (~400-600 KB)
   - Remaining 19: API-only (~100-200 KB each)
4. ✅ Stops mitmproxy and gets traffic stats
5. ✅ Updates database with results
6. ✅ Shows detailed bandwidth breakdown

---

## Output Example

```
================================================================================
BATCH BANDWIDTH MEASUREMENT WITH MITMPROXY
================================================================================

📋 Fetching 20 pending creatives (1 batch)...
✅ Got 20 creatives

🚀 Starting mitmproxy for bandwidth measurement...
✅ Mitmproxy started

================================================================================
PROCESSING BATCH (20 creatives)
================================================================================

[Worker 0] 🔄 Batch (1/20): CR13612220978... (Full HTML)
  🌐 Opening page (full load for cookie extraction)...
  ✅ Page loaded, extracted 7 cookies
  ... (extraction output) ...
  ✅ CR13612220978... (2 videos) - 4.23s

[Worker 0] 🔄 Batch (2/20): CR08350200220... (API-only)
  🍪 Adding 7 cookies to context...
  📤 Making API request...
  📤 Fetching 3 content.js file(s) in parallel...
  ✅ Fetched 3 file(s) in 0.78s (parallel)
  ✅ CR08350200220... (3 videos) - 1.45s

... (18 more creatives) ...

================================================================================
STOPPING MITMPROXY
================================================================================

================================================================================
UPDATING DATABASE
================================================================================
✅ Success: 18
🔄 Retry: 2
❌ Failed: 0

================================================================================
BANDWIDTH MEASUREMENT RESULTS
================================================================================

📊 TRAFFIC SUMMARY:
   Requests:    145 |       48.3 KB outgoing
   Responses:   145 |     3,247.8 KB incoming
   ─────────────────────────────────────────────
   Total:            3,296.1 KB

📈 PER-CREATIVE AVERAGE:
   164.8 KB per creative

💡 BATCH OPTIMIZATION BREAKDOWN:
   First creative:  ~400-600 KB (full HTML load)
   Remaining 19:    ~100-200 KB each (API-only)
   Savings:         ~70-80% per creative (after first)

🔝 TOP BANDWIDTH CONSUMERS:
 #   Compressed                      Type                              URL
────────────────────────────────────────────────────────────────────────────────
 1.       341.2 KB text/html                        https://adstransparency.google.com/advertiser/...
 2.       154.9 KB application/javascript           https://displayads-formats.googleusercontent...
 3.       154.8 KB application/javascript           https://displayads-formats.googleusercontent...
 4.       149.5 KB application/javascript           https://displayads-formats.googleusercontent...
 ...

================================================================================
BATCH TEST COMPLETE
================================================================================
⏱️  Duration: 32.45s
📊 Creatives: 20
✅ Success: 18/20
💾 Total bandwidth: 3.22 MB
📈 Average per creative: 164.8 KB
```

---

## Key Metrics

### Per-Batch Bandwidth (20 creatives)

| Metric | Value |
|--------|-------|
| Total bandwidth | ~3.0-3.5 MB |
| First creative | ~400-600 KB (full HTML) |
| Remaining 19 | ~100-200 KB each (API-only) |
| Average per creative | ~160 KB |
| Time | ~30-40 seconds |

### Breakdown

**First creative (HTML load)**:
- HTML page: ~341 KB
- JavaScript: ~50-100 KB
- API calls: ~20-30 KB
- Content.js: ~150-200 KB
- **Total**: ~400-600 KB

**Remaining creatives (API-only)**:
- API call: ~5-10 KB
- Content.js: ~150-200 KB (with gzip)
- **Total**: ~100-200 KB each

**Savings**: ~70-80% per creative (after first)

---

## Comparison: Full HTML vs Batch Optimization

### 20 Creatives with Full HTML (no optimization)

```
Creative 1:  524 KB (HTML)
Creative 2:  524 KB (HTML)
Creative 3:  524 KB (HTML)
...
Creative 20: 524 KB (HTML)
─────────────────────────────
Total:      10.48 MB
```

### 20 Creatives with Batch Optimization (session reuse)

```
Creative 1:  524 KB (HTML - establishes session)
Creative 2:  161 KB (API-only - reuses session)
Creative 3:  161 KB (API-only)
...
Creative 20: 161 KB (API-only)
─────────────────────────────
Total:       3.58 MB
Savings:     6.90 MB (66% reduction)
```

---

## Troubleshooting

### No Mitmproxy Data

**Symptom**:
```
⚠️  No mitmproxy data available
```

**Solution**: Install mitmproxy
```bash
brew install mitmproxy
# or
pip install mitmproxy
```

### No Pending Creatives

**Symptom**:
```
❌ No pending creatives found in database
```

**Solution**: Import creatives to database
```bash
python3 import_bigquery_data.py
```

### Socket Hang Up Errors

**Symptom**:
```
⚠️  Failed to fetch file 1: ... - socket hang up
🔄 Retry: 2
```

**Explanation**: Temporary network errors (now automatically retried)

---

## Advanced Usage

### Test Different Batch Sizes

Edit `test_batch_with_mitmproxy.py`, line 30:

```python
# Test with 10 creatives instead of 20
creative_batch = get_pending_batch_and_mark_processing(batch_size=10)
```

### Multiple Batches

Run the script multiple times:

```bash
# Measure 3 batches (60 creatives total)
python3 test_batch_with_mitmproxy.py  # Batch 1
python3 test_batch_with_mitmproxy.py  # Batch 2
python3 test_batch_with_mitmproxy.py  # Batch 3
```

### Save Mitmproxy Results

The script automatically saves results to the traffic results file. To save to a custom location, modify the `teardown_proxy()` call.

---

## Alternative: Use Original Scraper

If you want to measure a **single creative** (not a batch), use the original scraper:

```bash
python3 google_ads_transparency_scraper_optimized.py \
  "https://adstransparency.google.com/advertiser/AR.../creative/CR..." \
  --proxy
```

This will:
- Process 1 creative with full HTML load
- Measure bandwidth with mitmproxy
- Show detailed traffic breakdown

---

## Comparing Methods

### Full HTML (Original Scraper)

```bash
python3 google_ads_transparency_scraper_optimized.py <URL> --proxy
```

**Per creative**: ~524 KB  
**Use case**: Single creative measurement

### API-Only (Not available separately)

Can't be tested in isolation - only works after establishing session.

### Batch Optimization (This Test Script)

```bash
python3 test_batch_with_mitmproxy.py
```

**Per batch (20)**: ~3.5 MB (~175 KB per creative)  
**Use case**: Production bandwidth measurement

---

## Summary

**To measure 1 batch with mitmproxy**:

```bash
python3 test_batch_with_mitmproxy.py
```

**What you get**:
- ✅ Processes 20 creatives (1 batch)
- ✅ Measures actual bandwidth with mitmproxy
- ✅ Shows optimization savings
- ✅ Updates database
- ✅ Ready for production analysis

**Expected bandwidth**: ~3-3.5 MB per batch (20 creatives)

---

**Script**: `test_batch_with_mitmproxy.py`  
**Created**: 2025-10-28  
**Purpose**: Measure batch scraping bandwidth with mitmproxy


