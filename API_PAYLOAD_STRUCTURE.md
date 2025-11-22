# SearchCreatives API Payload Structure

## API Endpoint

```
POST https://adstransparency.google.com/anji/_/rpc/SearchService/SearchCreatives?authuser=
```

## Request Headers

```python
{
    "accept": "*/*",
    "content-type": "application/x-www-form-urlencoded",
    "cookie": "SESSIONID=...; __Secure-OSID=...; ...",  # From browser session
    "origin": "https://adstransparency.google.com",
    "referer": "https://adstransparency.google.com/?region=anywhere",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...",
    "x-framework-xsrf-token": "",
    "x-same-domain": "1",
    "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"'
}
```

## Payload Structure

### First Request (No Pagination)

```python
{
    "2": 40,                    # Page size (results per page)
    "3": {                      # Search filters
        "4": 3,                 # Platform type (3 = all platforms)
        "6": 20241115,          # Date from (YYYYMMDD format) - 7 days ago
        "7": 20241122,          # Date to (YYYYMMDD format) - today
        "12": {                 # Region settings
            "1": "",            # Region ID (empty = anywhere)
            "2": True           # Include all regions
        },
        "13": {                 # Advertiser filter
            "1": ["AR05226884764400615425"]  # List of advertiser IDs
        },
        "14": [5]               # Content type filter (5 = all types)
    },
    "7": {                      # UI/Display settings
        "1": 1,                 # Unknown
        "2": 39,                # Unknown
        "3": 2268               # Unknown
    }
}
```

### Paginated Request (With Pagination Token)

```python
{
    "2": 40,                    # Page size (results per page)
    "3": {                      # Search filters (same as above)
        "4": 3,
        "6": 20241115,
        "7": 20241122,
        "12": {"1": "", "2": True},
        "13": {"1": ["AR05226884764400615425"]},
        "14": [5]
    },
    "4": "CkQKPgoSEhASChIICA...",  # Pagination token from previous response
    "7": {"1": 1, "2": 39, "3": 2268}
}
```

## Encoding

The payload is URL-encoded as a form parameter:

```python
post_data = "f.req=" + urllib.parse.quote(json.dumps(first_body, separators=(',', ':')))
```

**Example encoded:**
```
f.req=%7B%222%22%3A40%2C%223%22%3A%7B%224%22%3A3%2C%226%22%3A20241115%2C%227%22%3A20241122...
```

## Field Explanations

### Top-Level Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `"2"` | int | Page size (number of results per page) | `40` |
| `"3"` | object | Search filters and criteria | See below |
| `"4"` | string | Pagination token (only for subsequent pages) | `"CkQKPgo..."` |
| `"7"` | object | UI/Display settings | `{"1": 1, "2": 39, "3": 2268}` |

### Field `"3"` - Search Filters

| Field | Type | Description | Values |
|-------|------|-------------|--------|
| `"4"` | int | Platform filter | `3` = all platforms, `1` = YouTube, `2` = Display Network |
| `"6"` | int | Date from (start date) | YYYYMMDD format: `20241115` |
| `"7"` | int | Date to (end date) | YYYYMMDD format: `20241122` |
| `"12"` | object | Region settings | `{"1": "", "2": true}` for anywhere |
| `"13"` | object | Advertiser filter | `{"1": ["AR..."]}` list of advertiser IDs |
| `"14"` | array | Content type filter | `[5]` = all types |

### Field `"12"` - Region Settings

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `"1"` | string | Region code | `""` = anywhere, `"US"` = United States |
| `"2"` | bool | Include all regions | `true` |

### Field `"13"` - Advertiser Filter

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `"1"` | array | List of advertiser IDs to filter | `["AR05226884764400615425"]` |

## Response Structure

### Successful Response

```json
{
    "1": [                      // Array of creative items
        {
            "1": "...",         // Creative metadata
            "2": "CR00096655163799896065",  // Creative ID
            "3": {...},         // Additional data
            ...
        },
        ...
    ],
    "2": "CkQKPgoSEhASChII...",  // Pagination token for next page (if more results)
    "4": "127",                 // Total creatives estimate (field 4)
    "5": "89"                   // Total creatives estimate (field 5)
}
```

### Key Response Fields

| Field | Type | Description | Usage |
|-------|------|-------------|-------|
| `"1"` | array | Creative items | Extract creative IDs from `item["2"]` |
| `"2"` | string | Pagination token | Use in next request's field `"4"` |
| `"4"` | string | Ads daily estimate (part 1) | Used for `daily_7` calculation |
| `"5"` | string | Ads daily estimate (part 2) | Used for `daily_7` calculation |

### Extracting `daily_7` (ads_daily)

```python
val4 = response_json.get("4")
val5 = response_json.get("5")

if isinstance(val4, str) and val4.isdigit() and isinstance(val5, str) and val5.isdigit():
    ads_daily = (int(val4) + int(val5)) // 2  # Average of both values
```

**Example:**
- Field `"4"` = `"127"`
- Field `"5"` = `"89"`
- `daily_7` = `(127 + 89) / 2 = 108`

## Date Range Calculation

The script uses **7 days lookback** from current UTC date:

```python
date_to = datetime.now(timezone.utc).date()        # Today
date_from = date_to - timedelta(days=7)            # 7 days ago

date_to_str = date_to.strftime('%Y%m%d')           # "20241122"
date_from_str = date_from.strftime('%Y%m%d')       # "20241115"
```

## Pagination Flow

### First Request
```python
payload = {
    "2": 40,
    "3": {...},  # Filters
    "7": {...}   # No "4" field (no pagination token)
}
```

### Subsequent Requests
```python
payload = {
    "2": 40,
    "3": {...},              # Same filters
    "4": pagination_token,   # Token from previous response
    "7": {...}
}
```

### Pagination Loop
```python
pagination_key = response.get("2")  # Get token from response

while pagination_key:
    # Make request with pagination_key in field "4"
    response = make_request(payload_with_token)
    
    pagination_key = response.get("2")  # Get next token
    
    if not pagination_key:
        break  # No more pages
```

## Pagination Token Normalization

Pagination tokens may need base64 padding normalization:

```python
def normalize_pagination_key(token: str) -> str:
    if not token:
        return token
    
    t = token.strip()
    
    # Add base64 padding if needed
    if len(t) % 4 != 0:
        t += "=" * (4 - (len(t) % 4))
    
    return t
```

## Complete Example Request

### Request
```http
POST /anji/_/rpc/SearchService/SearchCreatives?authuser= HTTP/1.1
Host: adstransparency.google.com
Content-Type: application/x-www-form-urlencoded
Cookie: SESSIONID=abc123; __Secure-OSID=xyz789
Origin: https://adstransparency.google.com
Referer: https://adstransparency.google.com/?region=anywhere
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)...

f.req=%7B%222%22%3A40%2C%223%22%3A%7B%224%22%3A3%2C%226%22%3A20241115%2C%227%22%3A20241122%2C%2212%22%3A%7B%221%22%3A%22%22%2C%222%22%3Atrue%7D%2C%2213%22%3A%7B%221%22%3A%5B%22AR05226884764400615425%22%5D%7D%2C%2214%22%3A%5B5%5D%7D%2C%227%22%3A%7B%221%22%3A1%2C%222%22%3A39%2C%223%22%3A2268%7D%7D
```

### Response
```json
{
    "1": [
        {
            "2": "CR00096655163799896065",
            ...
        },
        {
            "2": "CR00096655163799896066",
            ...
        },
        ...
    ],
    "2": "CkQKPgoSEhASChIICAwQExgBIAEoATIJCAQQBRgBIAEoAQ==",
    "4": "127",
    "5": "89"
}
```

## Important Notes

1. **Cookies Required**: The API requires valid session cookies from a browser visit to the base URL
2. **Rate Limiting**: Google may rate limit requests - use delays between pagination
3. **Proxy Support**: The script uses rotating proxies to avoid rate limits
4. **Page Size**: Fixed at 40 results per page (field `"2"`)
5. **Date Format**: Must be YYYYMMDD integers (e.g., `20241122`, not `"2024-11-22"`)
6. **Advertiser ID Format**: Must be `AR` followed by 20 digits

## Testing the Payload

To test the payload manually:

```bash
# 1. Get cookies from browser (visit https://adstransparency.google.com/?region=anywhere)
# 2. Extract cookies

# 3. Make request
curl -X POST 'https://adstransparency.google.com/anji/_/rpc/SearchService/SearchCreatives?authuser=' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Cookie: SESSIONID=...; __Secure-OSID=...' \
  --data-urlencode 'f.req={"2":40,"3":{"4":3,"6":20241115,"7":20241122,"12":{"1":"","2":true},"13":{"1":["AR05226884764400615425"]},"14":[5]},"7":{"1":1,"2":39,"3":2268}}'
```

---

**This payload structure is used by `advertiser_batch_scraper.py` for all SearchCreatives API calls.**

