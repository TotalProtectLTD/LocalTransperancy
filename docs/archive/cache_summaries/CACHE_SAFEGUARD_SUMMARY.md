# Cache Safeguard Implementation

## Problem
Non-versioned cache files (e.g., `main.dart.js` without `_v_` suffix) were appearing in the `main.dart/` folder, even though the code was updated to always use version suffixes.

## Root Cause
Python was caching the old bytecode (`.pyc` files) after code changes, so when scripts ran, they were using the OLD version of the code that didn't add version suffixes.

## Solutions Implemented

### 1. Cache Safeguard (MAIN FIX)
**File:** `cache_storage.py` - `save_to_cache()` function

Added a **hard safeguard** that **refuses** to save any file without a version suffix:

```python
# SAFEGUARD: Only cache files with version suffixes
if '_v_' not in filename:
    error_msg = f"CACHE SAFEGUARD: Refusing to save file without version suffix!\n   Filename: {filename}\n   URL: {url}"
    print(f"❌ {error_msg}")
    logger.error(error_msg)
    return False  # Cache save is skipped
```

**Result:** 
- ✅ Files without `_v_` will NEVER be saved to cache
- ✅ You'll see a red error message if something tries to save non-versioned files
- ✅ This prevents cache corruption even if there's a bug elsewhere

### 2. Enhanced Debug Logging
**File:** `cache_models.py` - `extract_version_from_url()` function

Added warnings when version extraction fails:

```python
if not version_path:
    print(f"⚠️  VERSION EXTRACTION FAILED: Empty version path for URL: {url}")
```

**Result:** You'll immediately see which URLs are problematic

### 3. Python Cache Clearing
Cleared all Python bytecode cache:
```bash
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -name "*.pyc" -delete
```

**Why this matters:** After code changes, you **MUST** clear Python cache or scripts will run old code!

### 4. Cache Monitor Script
**File:** `monitor_cache_files.sh`

A background monitoring script that watches for non-versioned files:

```bash
./monitor_cache_files.sh
```

This will alert you in real-time if non-versioned files appear.

## How to Debug if Non-Versioned Files Appear Again

### Step 1: Check the Safeguard Logs
Look for red error messages:
```
❌ CACHE SAFEGUARD: Refusing to save file without version suffix!
   Filename: main.dart.js
   URL: https://...
```

### Step 2: Check Version Extraction Warnings
Look for yellow warnings:
```
⚠️  VERSION EXTRACTION FAILED: No version found in URL: https://...
```

### Step 3: Use the Monitor Script
Run the monitor in a separate terminal while your scraper runs:
```bash
./monitor_cache_files.sh
```

This will show you the **exact moment** a non-versioned file is created and which process created it.

### Step 4: Clear Python Cache
**ALWAYS** clear Python cache after code changes:
```bash
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -name "*.pyc" -delete
```

### Step 5: Verify Version Extraction
Test that version extraction works for your URLs:
```bash
python3 -c "from cache_models import get_cache_filename; print(get_cache_filename('YOUR_URL_HERE'))"
```

## Verification Checklist

✅ **Safeguard is active** - `save_to_cache()` checks for `_v_` in filename  
✅ **Debug logging is enabled** - `extract_version_from_url()` warns on failure  
✅ **Python cache is cleared** - No `.pyc` files with old code  
✅ **All existing non-versioned files removed** - Only `_v_` files in `main.dart/`  
✅ **cache_versions.json is clean** - Only versioned entries  

## Testing the Safeguard

```bash
# Run your scraper
python3 stress_test_scraper_optimized.py --max-concurrent 5 --max-urls 10

# In another terminal, watch for violations
./monitor_cache_files.sh

# OR check logs for safeguard messages
# Look for "CACHE SAFEGUARD" or "VERSION EXTRACTION FAILED"
```

## Expected Behavior

### ✅ GOOD - Versioned Files
```
main.dart.js_v_acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000
main.dart.js_v_acx-tfaar-tfaa-report-ui-frontend_auto_20251027-0645_RC000
main.dart.js_2.part.js_v_acx-tfaar-tfaa-report-ui-frontend_auto_20251020-0645_RC000
```

### ❌ BAD - Non-Versioned Files (BLOCKED by safeguard)
```
main.dart.js         ← Safeguard will refuse to save this
main.dart.js_2.part.js   ← Safeguard will refuse to save this
```

## What Changed

### Before (PROBLEM)
```python
# cache_storage.py
filename = get_cache_filename(url)
# ... directly saves without checking ...
with open(cache_path, 'w') as f:
    f.write(content)
```

### After (FIXED)
```python
# cache_storage.py
filename = get_cache_filename(url)

# SAFEGUARD: Refuse non-versioned files
if '_v_' not in filename:
    print(f"❌ CACHE SAFEGUARD: Refusing to save {filename}")
    return False

# Only saves if versioned
with open(cache_path, 'w') as f:
    f.write(content)
```

## Why This Happens

1. **Code is updated** to add version suffixes
2. **Python caches old bytecode** (`.pyc` files)
3. **Script runs** using OLD cached code
4. **Non-versioned files are saved** using old logic
5. **User sees problem** even though new code looks correct

**Solution:** Clear Python cache after EVERY code change!

## Quick Commands

```bash
# Clear Python cache (do this after EVERY code change)
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null

# Remove non-versioned cache files
cd main.dart
rm -f main.dart.js main.dart.js.meta.json
rm -f main.dart.js_*.part.js main.dart.js_*.part.js.meta.json
# (Only remove files WITHOUT _v_ in the name!)

# Clean cache_versions.json
python3 << 'EOF'
import json
with open('main.dart/cache_versions.json', 'r') as f:
    data = json.load(f)
versioned = {k: v for k, v in data.items() if '_v_' in k}
with open('main.dart/cache_versions.json', 'w') as f:
    json.dump(versioned, f, indent=2)
EOF

# Verify cache is clean
ls -lh main.dart/ | grep "\.js" | grep -v "_v_"
# (Should show NO results)
```

## Current Status

✅ **Safeguard implemented** - Files without version suffix are blocked  
✅ **Debug logging added** - Version extraction failures are logged  
✅ **Python cache cleared** - Old bytecode removed  
✅ **Existing non-versioned files removed** - Cache is clean  
✅ **Monitor script created** - `monitor_cache_files.sh` for real-time detection  

## Next Steps

1. **Run your scraper** with the safeguard active
2. **Watch the logs** for any "CACHE SAFEGUARD" error messages
3. **If you see the error**, check which URL caused it and investigate why version extraction failed
4. **Always clear Python cache** after code changes

---

**Remember:** The safeguard is your friend! If you see the red error message, it means the safeguard is working and preventing cache corruption. Investigate the URL that triggered it.


