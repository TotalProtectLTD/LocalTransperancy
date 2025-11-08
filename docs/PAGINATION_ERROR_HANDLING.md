# Pagination Error Handling Logic

## Overview

The pagination loop in `parser_of_advertiser.py` uses a **multi-layered error handling strategy** with retry logic to handle transient failures while gracefully stopping on permanent errors.

## Architecture

```
Outer Try-Except (lines 339-475)
  └─> Pagination Loop (while pagination_key and pages < MAX_PAGINATION_PAGES)
        └─> Retry Loop (for attempt in range(max_retries))
              └─> HTTP Request + Response Processing
```

## Error Handling Layers

### Layer 1: Outer Exception Handler (Lines 473-475)

**Purpose**: Catches any unexpected exceptions that escape the retry logic.

```python
except Exception as e:
    _log("ERROR", "Pagination stopped: exception occurred", error=str(e)[:200])
    pass
```

**Behavior**:
- Logs the error
- Continues execution (doesn't crash)
- Returns whatever data was collected so far

**When it triggers**:
- Unexpected exceptions in the pagination loop setup
- Exceptions in the retry loop structure itself
- Any unhandled edge cases

---

### Layer 2: Retry Loop (Lines 367-449)

**Purpose**: Retries failed requests up to 3 times with exponential backoff.

**Configuration**:
- `max_retries = 3` (attempts: 0, 1, 2)
- `retry_delays = [2, 4, 8]` seconds (exponential backoff)

**Flow**:
1. Attempt request
2. If error occurs, check if retries remaining
3. If yes: wait, retry
4. If no: log error, break retry loop, exit pagination

---

### Layer 3: HTTP Status Code Handling (Lines 372-396)

**Purpose**: Categorizes HTTP responses and handles them appropriately.

#### 5xx Errors (Server Errors) - Lines 373-386

**Status codes**: 500, 501, 502, 503, 504, etc.

**Behavior**:
- **Retryable**: Yes (up to 3 attempts)
- **Reason**: Server errors are often transient (overload, temporary issues)
- **Action**:
  - If retries remaining: Log WARN, wait, retry
  - If retries exhausted: Log ERROR, break retry loop, exit pagination

**Example scenarios**:
- Google API server overload
- Proxy server 500 error
- Temporary network issues

**Log output**:
```
[WARN] [N] HTTP 500 error, retrying in 2s | {"page": N, "status_code": 500, "attempt": 1, "max_retries": 3}
[ERROR] [N] Pagination stopped: HTTP 500 after 3 retries | {"page": N, "status_code": 500, "response_preview": "..."}
```

#### 4xx Errors (Client Errors) - Lines 387-392

**Status codes**: 400, 401, 403, 404, 429, etc.

**Behavior**:
- **Retryable**: No (immediate stop)
- **Reason**: Client errors are usually permanent (bad request, auth failure, rate limit)
- **Action**: Log ERROR, break retry loop, exit pagination

**Example scenarios**:
- Invalid pagination key
- Authentication expired
- Rate limit exceeded (429)
- Bad request format

**Log output**:
```
[ERROR] [N] Pagination stopped: HTTP 400 client error | {"page": N, "status_code": 400, "response_preview": "..."}
```

#### Other Non-200 Status Codes - Lines 393-396

**Status codes**: 1xx, 3xx (redirects), etc.

**Behavior**:
- **Retryable**: No (continues processing)
- **Reason**: Unexpected but might still have valid JSON
- **Action**: Log WARN, continue to JSON parsing

---

### Layer 4: JSON Parsing Errors (Lines 398-413)

**Purpose**: Handles cases where HTTP request succeeds but response isn't valid JSON.

**Behavior**:
- **Retryable**: Yes (up to 3 attempts)
- **Reason**: Network corruption, partial responses, encoding issues
- **Action**:
  - If retries remaining: Log WARN, wait, retry
  - If retries exhausted: Log ERROR, break retry loop, exit pagination

**Example scenarios**:
- Partial response received
- Encoding issues
- HTML error page instead of JSON
- Network corruption

**Log output**:
```
[WARN] [N] JSON parse failed, retrying in 2s | {"page": N, "status_code": 200, "error": "...", "attempt": 1}
[ERROR] [N] Pagination stopped: JSON parse failed after 3 retries | {"page": N, "status_code": 200, "error": "...", "response_preview": "..."}
```

---

### Layer 5: Network/Transport Exceptions (Lines 415-449)

**Purpose**: Handles low-level network and transport errors.

#### TimeoutException (Lines 415-425)

**When it occurs**:
- Request exceeds 30-second timeout
- No response received

**Behavior**:
- **Retryable**: Yes (up to 3 attempts)
- **Action**:
  - If retries remaining: Log WARN, wait, retry
  - If retries exhausted: Log ERROR, break retry loop, exit pagination

**Log output**:
```
[WARN] [N] Request timeout, retrying in 2s | {"page": N, "attempt": 2, "error": "..."}
[ERROR] [N] Pagination stopped: request timeout after 3 retries | {"page": N, "error": "..."}
```

#### TransportError (Lines 426-437)

**When it occurs**:
- Connection refused
- Proxy connection failed
- Network unreachable
- SSL/TLS errors
- Socket errors

**Behavior**:
- **Retryable**: Yes (up to 3 attempts)
- **Action**:
  - If retries remaining: Log WARN, wait, retry
  - If retries exhausted: Log ERROR, break retry loop, exit pagination

**Log output**:
```
[WARN] [N] Transport error, retrying in 2s | {"page": N, "attempt": 2, "error": "..."}
[ERROR] [N] Pagination stopped: transport error after 3 retries | {"page": N, "error": "..."}
```

#### Generic Exception (Lines 438-449)

**When it occurs**:
- Any other unexpected exception
- Unknown error types

**Behavior**:
- **Retryable**: Yes (up to 3 attempts)
- **Action**:
  - If retries remaining: Log WARN, wait, retry
  - If retries exhausted: Log ERROR, break retry loop, exit pagination

**Log output**:
```
[WARN] [N] Unexpected error, retrying in 2s | {"page": N, "attempt": 2, "error": "..."}
[ERROR] [N] Pagination stopped: unexpected error after 3 retries | {"page": N, "error": "..."}
```

---

## Exit Conditions

The pagination loop exits when:

1. **No more pages** (normal completion):
   - `pagination_key` becomes `None` or empty
   - Log: `[INFO] [N] Pagination completed: no more pages (pagination_key is empty)`

2. **HTTP 4xx error** (client error):
   - Immediate stop, no retries
   - Log: `[ERROR] [N] Pagination stopped: HTTP 4xx client error`

3. **HTTP 5xx error after retries** (server error):
   - After 3 failed attempts
   - Log: `[ERROR] [N] Pagination stopped: HTTP 5xx after 3 retries`

4. **JSON parse failure after retries**:
   - After 3 failed attempts
   - Log: `[ERROR] [N] Pagination stopped: JSON parse failed after 3 retries`

5. **Network/transport error after retries**:
   - After 3 failed attempts
   - Log: `[ERROR] [N] Pagination stopped: [error type] after 3 retries`

6. **Max pages reached** (safety limit):
   - `pages >= MAX_PAGINATION_PAGES` (5000)
   - Log: `[WARN] Pagination stopped: reached MAX_PAGINATION_PAGES limit`

7. **Unexpected exception** (outer handler):
   - Any exception escaping retry logic
   - Log: `[ERROR] Pagination stopped: exception occurred`

---

## Retry Strategy

### Exponential Backoff

```
Attempt 1: Wait 2 seconds
Attempt 2: Wait 4 seconds
Attempt 3: Wait 8 seconds
Total wait time: 14 seconds (if all retries fail)
```

### Retryable Errors

✅ **Retried** (up to 3 times):
- HTTP 5xx errors
- JSON parse failures
- TimeoutException
- TransportError
- Generic exceptions

❌ **Not Retried** (immediate stop):
- HTTP 4xx errors (client errors)
- Normal completion (no pagination_key)

---

## Response Validation

After successful HTTP request and JSON parsing:

1. **Extract items** from `paginated_json.get("1", [])`
2. **Extract pagination_key** from `paginated_json.get("2")`
3. **Check if pagination_key is empty**:
   - If empty: Log completion, exit loop
   - If present: Continue to next page

---

## Data Preservation

**Important**: Even if pagination stops early due to errors:
- All successfully collected creatives are preserved
- Function returns with `creative_ids` containing all collected data
- `pagination_key` is preserved (can be used to resume later)

---

## Example Error Scenarios

### Scenario 1: Transient 500 Error (Recovers)

```
[INFO] [5] Paused for 6s. Next SearchCreatives page 5
[WARN] [5] HTTP 500 error, retrying in 2s | {"page": 5, "status_code": 500, "attempt": 1, "max_retries": 3}
[WARN] [5] HTTP 500 error, retrying in 4s | {"page": 5, "status_code": 500, "attempt": 2, "max_retries": 3}
[INFO] [5] Page collected +40 creatives (total 200)
```

### Scenario 2: Persistent 500 Error (Fails)

```
[INFO] [10] Paused for 7s. Next SearchCreatives page 10
[WARN] [10] HTTP 500 error, retrying in 2s | {"page": 10, "status_code": 500, "attempt": 1, "max_retries": 3}
[WARN] [10] HTTP 500 error, retrying in 4s | {"page": 10, "status_code": 500, "attempt": 2, "max_retries": 3}
[WARN] [10] HTTP 500 error, retrying in 8s | {"page": 10, "status_code": 500, "attempt": 3, "max_retries": 3}
[ERROR] [10] Pagination stopped: HTTP 500 after 3 retries | {"page": 10, "status_code": 500, "response_preview": "..."}
```

### Scenario 3: Client Error (Immediate Stop)

```
[INFO] [8] Paused for 5s. Next SearchCreatives page 8
[ERROR] [8] Pagination stopped: HTTP 400 client error | {"page": 8, "status_code": 400, "response_preview": "Invalid pagination key"}
```

### Scenario 4: Proxy/Network Error (Recovers)

```
[INFO] [12] Paused for 8s. Next SearchCreatives page 12
[WARN] [12] Transport error, retrying in 2s | {"page": 12, "attempt": 1, "error": "Proxy connection failed"}
[INFO] [12] Page collected +40 creatives (total 480)
```

---

## Key Design Decisions

1. **4xx errors don't retry**: Client errors are usually permanent (bad request, auth failure)
2. **5xx errors do retry**: Server errors are often transient
3. **Network errors retry**: Connection issues are often temporary
4. **Preserve collected data**: Never lose successfully collected creatives
5. **Exponential backoff**: Prevents overwhelming failing servers
6. **Comprehensive logging**: Every error type is logged with context

---

## Summary

The error handling is **defensive and resilient**:
- ✅ Retries transient errors (5xx, timeouts, network issues)
- ✅ Stops immediately on permanent errors (4xx)
- ✅ Preserves all successfully collected data
- ✅ Provides detailed logging for debugging
- ✅ Never crashes - always returns collected data

