# Version-Aware Cache System - Flow Diagrams

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Google Ads Transparency                       │
│                                                                   │
│  URL: https://www.gstatic.com/acx/transparency/report/          │
│       acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000/│
│       main.dart.js                                               │
│                                                                   │
│       ↓ Version Identifier: 20251020-0645_RC000                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   fighting_cache_problem.py                      │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  1. Extract Version from URL                              │  │
│  │     extract_version_from_url(url)                         │  │
│  │     → "acx-tfaar-tfaa-report-ui-frontend_auto_20251020-   │  │
│  │        0645_RC000"                                         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              ↓                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  2. Load Version Tracking                                 │  │
│  │     load_version_tracking()                               │  │
│  │     → Read cache_versions.json                            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              ↓                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  3. Compare Versions                                      │  │
│  │     check_version_changed(url)                            │  │
│  │     Current vs Cached                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              ↓                                   │
│                    ┌─────────┴─────────┐                        │
│                    │                   │                        │
│              Version Match      Version Mismatch                │
│                    │                   │                        │
│         ┌──────────┘                   └──────────┐            │
│         ↓                                          ↓            │
│  ┌──────────────┐                      ┌──────────────────┐   │
│  │ Serve from   │                      │ Invalidate Cache │   │
│  │ Cache        │                      │ Delete old files │   │
│  │ (12.77 KB)   │                      │ Download new     │   │
│  │              │                      │ (1.26 MB)        │   │
│  └──────────────┘                      └──────────────────┘   │
│                                                  ↓              │
│                                        ┌──────────────────┐   │
│                                        │ Update Tracking  │   │
│                                        │ save_version_    │   │
│                                        │ tracking()       │   │
│                                        └──────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      Local Cache Storage                         │
│                                                                   │
│  main.dart/                                                      │
│  ├── cache_versions.json        ← Version tracking database     │
│  ├── main.dart.js                ← Cached content                │
│  ├── main.dart.js.meta.json     ← Metadata with version         │
│  └── ...                                                         │
└─────────────────────────────────────────────────────────────────┘
```

## Request Flow - Cache Hit (Same Version)

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Request Intercepted                                      │
└─────────────────────────────────────────────────────────────────┘
  URL: .../acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000/main.dart.js
                                                                    ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Extract Version                                          │
└─────────────────────────────────────────────────────────────────┘
  Regex: (acx-tfaar-tfaa-report-ui-frontend_auto_\d{8}-\d{4}_RC\d+)
  Result: "acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000"
                                                                    ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Load Cached Version                                      │
└─────────────────────────────────────────────────────────────────┘
  From: cache_versions.json
  Cached: "acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000"
                                                                    ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Compare Versions                                         │
└─────────────────────────────────────────────────────────────────┘
  Current:  ...20251020-0645_RC000
  Cached:   ...20251020-0645_RC000
  Result:   ✅ MATCH
                                                                    ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 5: Serve from Cache                                         │
└─────────────────────────────────────────────────────────────────┘
  Read: main.dart/main.dart.js (4.33 MB)
  Serve: 200 OK with cached content
  
  Log: [CACHE HIT] Served main.dart.js from cache (4543597 bytes, age: 0.0h)
                                                                    ↓
┌─────────────────────────────────────────────────────────────────┐
│ Result: 98.99% Bandwidth Savings                                 │
│         12.77 KB instead of 1.26 MB                              │
└─────────────────────────────────────────────────────────────────┘
```

## Request Flow - Cache Miss (Version Changed)

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Request Intercepted                                      │
└─────────────────────────────────────────────────────────────────┘
  URL: .../acx-tfaar-tfaa-report-ui-frontend_auto_20251027-1200_RC001/main.dart.js
                                                    ↑ NEW VERSION ↑
                                                                    ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Extract Version                                          │
└─────────────────────────────────────────────────────────────────┘
  Regex: (acx-tfaar-tfaa-report-ui-frontend_auto_\d{8}-\d{4}_RC\d+)
  Result: "acx-tfaar-tfaa-report-ui-frontend_auto_20251027-1200_RC001"
                                                                    ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Load Cached Version                                      │
└─────────────────────────────────────────────────────────────────┘
  From: cache_versions.json
  Cached: "acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000"
                                                    ↑ OLD VERSION ↑
                                                                    ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Compare Versions                                         │
└─────────────────────────────────────────────────────────────────┘
  Current:  ...20251027-1200_RC001  ← NEW
  Cached:   ...20251020-0645_RC000  ← OLD
  Result:   ❌ MISMATCH
  
  Log: [VERSION CHANGE] main.dart.js: ...20251020-0645_RC000 -> ...20251027-1200_RC001
                                                                    ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 5: Invalidate Cache                                         │
└─────────────────────────────────────────────────────────────────┘
  Delete: main.dart/main.dart.js
  Delete: main.dart/main.dart.js.meta.json
  
  Log: [VERSION MISMATCH] main.dart.js: cached=...RC000, current=...RC001
  Log: [CACHE INVALIDATE] Removing outdated cache for main.dart.js
                                                                    ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 6: Download New Version                                     │
└─────────────────────────────────────────────────────────────────┘
  Fetch: .../acx-tfaar-tfaa-report-ui-frontend_auto_20251027-1200_RC001/main.dart.js
  Size: 4.33 MB
  
  Log: [CACHE MISS] main.dart.js not in cache or expired, downloading...
                                                                    ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 7: Save to Cache                                            │
└─────────────────────────────────────────────────────────────────┘
  Write: main.dart/main.dart.js (content)
  Write: main.dart/main.dart.js.meta.json (metadata with version)
  
  Log: [CACHE SAVE] Saved main.dart.js to cache (4543603 bytes, version: ...RC001)
                                                                    ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 8: Update Version Tracking                                  │
└─────────────────────────────────────────────────────────────────┘
  Update: cache_versions.json
  {
    "main.dart.js": {
      "version": "acx-tfaar-tfaa-report-ui-frontend_auto_20251027-1200_RC001",
      "url": "https://...",
      "updated_at": 1761580000.0
    }
  }
  
  Log: [VERSION TRACKING] Updated main.dart.js -> ...20251027-1200_RC001
                                                                    ↓
┌─────────────────────────────────────────────────────────────────┐
│ Result: New Version Cached and Ready                             │
│         Next request will be a cache hit                         │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                        Incoming Request                           │
│  URL: .../acx-tfaar-tfaa-report-ui-frontend_auto_YYYYMMDD-       │
│       HHMM_RCXXX/main.dart.js                                    │
└──────────────────────────────────────────────────────────────────┘
                              ↓
                    ┌─────────────────┐
                    │ extract_version │
                    │   _from_url()   │
                    └─────────────────┘
                              ↓
                    Version: YYYYMMDD-HHMM_RCXXX
                              ↓
                    ┌─────────────────┐
                    │ load_version_   │
                    │   tracking()    │
                    └─────────────────┘
                              ↓
                    Read: cache_versions.json
                              ↓
              ┌───────────────┴───────────────┐
              │                               │
        Version Match                   Version Mismatch
              │                               │
              ↓                               ↓
    ┌─────────────────┐           ┌─────────────────────┐
    │ load_from_cache │           │ Invalidate & Delete │
    └─────────────────┘           └─────────────────────┘
              ↓                               ↓
    Read: main.dart.js              Delete: Old files
    Read: .meta.json                        ↓
              ↓                     ┌─────────────────┐
    ┌─────────────────┐            │ Download from   │
    │ Serve cached    │            │ Google          │
    │ content         │            └─────────────────┘
    │ (12.77 KB)      │                    ↓
    └─────────────────┘            ┌─────────────────┐
              ↓                     │ save_to_cache() │
    ┌─────────────────┐            └─────────────────┘
    │ Log cache hit   │                    ↓
    └─────────────────┘            Write: main.dart.js
                                   Write: .meta.json
                                           ↓
                                   ┌─────────────────────┐
                                   │ update_version_     │
                                   │   tracking()        │
                                   └─────────────────────┘
                                           ↓
                                   Update: cache_versions.json
                                           ↓
                                   ┌─────────────────┐
                                   │ Serve new       │
                                   │ content         │
                                   │ (1.26 MB)       │
                                   └─────────────────┘
                                           ↓
                                   ┌─────────────────┐
                                   │ Log cache miss  │
                                   │ and version     │
                                   │ update          │
                                   └─────────────────┘
```

## Version Tracking Database Structure

```
cache_versions.json
{
  "main.dart.js": {
    "version": "acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000",
    "url": "https://www.gstatic.com/.../main.dart.js",
    "updated_at": 1761575380.4018219
  },
  "main.dart.js_2.part.js": {
    "version": "acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000",
    "url": "https://www.gstatic.com/.../main.dart.js_2.part.js",
    "updated_at": 1761575380.9311922
  },
  ...
}
```

## Cache Metadata Structure

```
main.dart.js.meta.json
{
  "url": "https://www.gstatic.com/.../main.dart.js",
  "cached_at": 1761575380.4018219,
  "size": 4543603,
  "version": "acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000",
  "etag": null,
  "last_modified": "Mon, 20 Oct 2025 13:57:39 GMT",
  "cache_control": "public, max-age=86400"
}
```

## Timeline Example

```
Day 1 (Oct 20, 2025 06:45)
─────────────────────────────────────────────────────────────
Google deploys: acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000

Run 1: Empty cache
  → Download all files (1.26 MB)
  → Create cache_versions.json
  → Cache: 20251020-0645_RC000

Run 2-10: Same version
  → Serve from cache (12.77 KB each)
  → 98.99% bandwidth savings
  → Cache: 20251020-0645_RC000


Day 7 (Oct 27, 2025 12:00)
─────────────────────────────────────────────────────────────
Google deploys: acx-tfaar-tfaa-report-ui-frontend_auto_20251027-1200_RC001

Run 11: Version changed
  → Detect mismatch: RC000 vs RC001
  → Invalidate cache
  → Download new version (1.26 MB)
  → Update cache_versions.json
  → Cache: 20251027-1200_RC001

Run 12-20: Same version
  → Serve from cache (12.77 KB each)
  → 98.99% bandwidth savings
  → Cache: 20251027-1200_RC001
```

## Bandwidth Savings Over Time

```
Without Version-Aware Cache:
─────────────────────────────────────────────────────────────
Day 1:  1.26 MB × 10 runs = 12.6 MB
Day 2:  1.26 MB × 10 runs = 12.6 MB  (re-download after 24h)
Day 3:  1.26 MB × 10 runs = 12.6 MB  (re-download after 24h)
...
Total (7 days): 88.2 MB


With Version-Aware Cache:
─────────────────────────────────────────────────────────────
Day 1:  1.26 MB (initial) + 12.77 KB × 9 = 1.37 MB
Day 2:  12.77 KB × 10 runs = 127.7 KB  (no re-download, version matches)
Day 3:  12.77 KB × 10 runs = 127.7 KB  (no re-download, version matches)
...
Day 7:  1.26 MB (new version) + 12.77 KB × 9 = 1.37 MB
Total (7 days): 3.52 MB

Savings: 84.6 MB (96% reduction!)
```

## State Machine

```
┌─────────────┐
│   START     │
└──────┬──────┘
       │
       ↓
┌─────────────────────┐
│  Extract Version    │
│  from URL           │
└──────┬──────────────┘
       │
       ↓
┌─────────────────────┐
│  Load Tracking      │
│  Data               │
└──────┬──────────────┘
       │
       ↓
┌─────────────────────┐
│  Compare Versions   │
└──────┬──────────────┘
       │
       ├─────────────────────┐
       │                     │
       ↓                     ↓
┌──────────────┐    ┌────────────────┐
│ MATCH        │    │ MISMATCH       │
└──────┬───────┘    └────────┬───────┘
       │                     │
       ↓                     ↓
┌──────────────┐    ┌────────────────┐
│ Check Age    │    │ Delete Old     │
└──────┬───────┘    │ Cache          │
       │            └────────┬───────┘
       ├─────────┐           │
       │         │           ↓
       ↓         ↓  ┌────────────────┐
┌──────────┐ ┌─────────────┐        │
│ Valid    │ │ Expired     │        │
└────┬─────┘ └──────┬──────┘        │
     │              │               │
     ↓              ↓               ↓
┌──────────┐ ┌─────────────────────────┐
│ SERVE    │ │    DOWNLOAD NEW         │
│ FROM     │ │                         │
│ CACHE    │ └──────────┬──────────────┘
└────┬─────┘            │
     │                  ↓
     │         ┌────────────────┐
     │         │ Save to Cache  │
     │         └────────┬───────┘
     │                  │
     │                  ↓
     │         ┌────────────────┐
     │         │ Update Tracking│
     │         └────────┬───────┘
     │                  │
     └──────────────────┘
                │
                ↓
         ┌─────────────┐
         │    END      │
         └─────────────┘
```

## Key Functions

```
extract_version_from_url(url)
    ↓ Returns version string
    
check_version_changed(url)
    ↓ Returns (changed, current_version, cached_version)
    
load_from_cache(url)
    ↓ Returns (content, metadata) or (None, None)
    
save_to_cache(url, content, headers)
    ↓ Saves content + metadata + updates tracking
    
update_version_tracking(url)
    ↓ Updates cache_versions.json
```

## Summary

This version-aware caching system provides:

✅ **Automatic detection** of Google's version changes  
✅ **Intelligent invalidation** of outdated cache  
✅ **Massive bandwidth savings** (98.99% for unchanged versions)  
✅ **Zero manual intervention** required  
✅ **Full transparency** with detailed logging  
✅ **Reliable operation** across all scenarios  

The system ensures you always have the latest JavaScript files while minimizing network traffic and maintaining stealth.

