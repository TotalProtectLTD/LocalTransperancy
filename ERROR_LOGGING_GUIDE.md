# Error Logging Guide

## Overview

The stress test scraper now logs **detailed error information** to the database so you can understand exactly what went wrong with failed creatives.

## Four Database Statuses

### 1. ✅ Success

**Database Status:** `status = 'completed'`

**What happened:**
- Scraped successfully
- All data extracted and saved
- No errors

---

### 2. ⟳ Temporary Errors (Will Retry)

**Database Status:** `status = 'pending'`

**Error Messages:**
```
ERR_TIMED_OUT - pending retry
ERR_PROXY_CONNECTION_FAILED - pending retry
ERR_CONNECTION_RESET - pending retry
INCOMPLETE: Only got 2/4 expected content.js - pending retry
```

**What happens:**
- Will be retried on next stress test run
- May eventually succeed

---

### 3. 🚫 Bad Ads (Creative Doesn't Exist) - SEPARATE STATUS!

**Database Status:** `status = 'bad_ad'` ⭐ (NEW - separate from 'failed')

**Error Message:**
```
Creative not found in API - broken/deleted creative page
```

**What happened:**
- Creative doesn't exist in Google's API
- Creative was deleted by advertiser
- Won't retry (permanent)

**Why separate status?**
- Easy to query: `SELECT * FROM creatives_fresh WHERE status = 'bad_ad'`
- Clear distinction from other errors
- Helps track broken/deleted creatives

---

### 4. ✗ Other Permanent Errors (Detailed)

**Database Status:** `status = 'failed'`

**Error Messages:** (FULL details with prefix)
```
PERMANENT ERROR: Timeout 60000ms exceeded
PERMANENT ERROR: Navigation failed: net::ERR_NAME_NOT_RESOLVED
PERMANENT ERROR: Page crashed
PERMANENT ERROR: Target page, context or browser has been closed
```

**What happened:**
- Unexpected errors that aren't network-related
- Full error details saved for debugging
- Won't retry (permanent)

**This is what you asked for!** Now you can see exactly what "unexpected" means.

---

## How to Query Errors

### Quick Command (See Recent Errors)

```bash
psql -U transparency_user -d local_transparency -c "
SELECT 
    creative_id,
    error_message,
    scraped_at
FROM creatives_fresh
WHERE error_message LIKE 'PERMANENT ERROR:%'
ORDER BY scraped_at DESC
LIMIT 20;
"
```

### Use Prepared Queries

We created `query_errors.sql` with 7 useful queries:

```bash
cd /Users/rostoni/Downloads/LocalTransperancy
psql -U transparency_user -d local_transparency -f query_errors.sql
```

**The 7 Queries:**
1. Count all errors by type
2. **Detailed view of permanent failures** ← Most useful for you
3. Count each specific error type
4. Recent errors (last 100)
5. Network errors that will retry
6. Bad ads count
7. Full summary with percentages

---

## Example Output

When you query for permanent errors, you'll see:

```
creative_id          | error_message                                          | scraped_at
---------------------|--------------------------------------------------------|---------------------
CR12345678901234     | PERMANENT ERROR: Timeout 60000ms exceeded              | 2025-10-26 14:32:10
CR98765432109876     | PERMANENT ERROR: Navigation timeout of 30000ms         | 2025-10-26 14:31:55
CR11111111111111     | PERMANENT ERROR: Target page closed                    | 2025-10-26 14:30:42
CR22222222222222     | PERMANENT ERROR: Page crashed                          | 2025-10-26 14:29:18
```

Now you know **exactly** what went wrong! No more mystery "unexpected" errors.

---

## Progress Display

When stress test runs, you'll see:

```
Progress: 100/1000 URLs (45 ✓, 5 ✗, 3 ⟳, 2 🚫) [8.5 URL/s]
```

- **45 ✓** = Success (completed)
- **5 ✗** = Permanent errors with FULL details in database
- **3 ⟳** = Retries (network/temp errors)
- **2 🚫** = Bad ads (creative not found)

---

## Common Permanent Errors You Might See

### Navigation Errors
```
PERMANENT ERROR: Navigation timeout of 30000ms exceeded
PERMANENT ERROR: Navigation failed: net::ERR_NAME_NOT_RESOLVED
PERMANENT ERROR: Navigation failed: net::ERR_CONNECTION_REFUSED
```
**Meaning:** Can't reach the page (DNS issues, server down, etc.)

### Timeout Errors
```
PERMANENT ERROR: Timeout 60000ms exceeded
PERMANENT ERROR: Page.goto: Timeout 30000ms exceeded
```
**Meaning:** Page took too long to load (not network error, something else)

### Browser/Page Errors
```
PERMANENT ERROR: Page crashed
PERMANENT ERROR: Target page closed
PERMANENT ERROR: Target page, context or browser has been closed
```
**Meaning:** Browser crashed or page closed unexpectedly

### JavaScript Errors
```
PERMANENT ERROR: Evaluation failed: ReferenceError: ...
PERMANENT ERROR: Cannot read property '...' of undefined
```
**Meaning:** JavaScript error on the page

---

## What's NOT Logged as Permanent Error

These go to `pending` status (will retry):
- ✅ Network connection failures
- ✅ Proxy errors  
- ✅ Timeout errors (if classified as temporary)
- ✅ Incomplete content.js files

These get special handling:
- ✅ Bad ads → "Creative not found in API - broken/deleted creative page"

---

## Quick Reference

| Error Type | Status | Error Message Format | Will Retry? |
|------------|--------|---------------------|-------------|
| Success | `completed` | NULL | N/A |
| Network/Temp | `pending` | `ERR_TYPE - pending retry` | ✅ YES |
| Bad Ad | `bad_ad` ⭐ | `Creative not found in API - broken/deleted...` | ❌ NO |
| Other Permanent | `failed` | `PERMANENT ERROR: <details>` | ❌ NO |

---

## Summary

✅ **Problem solved!** You now have:
1. Full error details in database for debugging
2. Clear error categorization (retry, bad ad, permanent)
3. SQL queries to analyze errors
4. No more mystery "unexpected" errors

Run your stress test and check `query_errors.sql` to see what's failing!

