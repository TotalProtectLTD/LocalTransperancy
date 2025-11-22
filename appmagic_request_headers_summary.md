# AppMagic API Request Headers Summary

## Request URL
```
GET https://appmagic.rocks/api/v2/search?name={app_id}&limit=20
```

## Required Headers

The API appears to work with standard browser headers. Here are the headers that are sent:

### Standard Browser Headers (Automatically Added)

| Header | Value | Required | Notes |
|--------|-------|----------|-------|
| `Accept` | `application/json, text/plain, */*` | Yes | Indicates acceptable response types |
| `Accept-Language` | `ru-RU,ru,en-US,en;q=0.9` | Optional | Browser language preferences |
| `Accept-Encoding` | `gzip, deflate, br` | Yes | Compression support |
| `User-Agent` | `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36` | Yes | Browser identification |
| `Referer` | `https://appmagic.rocks/top-charts/publishers` | Optional | Page that initiated the request |
| `Origin` | `https://appmagic.rocks` | Yes | CORS origin |
| `Connection` | `keep-alive` | Yes | HTTP connection type |
| `Sec-Fetch-Dest` | `empty` | Yes | Fetch API metadata |
| `Sec-Fetch-Mode` | `cors` | Yes | Fetch API metadata |
| `Sec-Fetch-Site` | `same-origin` | Yes | Fetch API metadata |

### Optional Headers

| Header | Value | Notes |
|--------|-------|-------|
| `Cache-Control` | `no-cache` | Prevents caching |
| `Pragma` | `no-cache` | HTTP/1.0 cache control |

### Cookies

| Header | Value | Required |
|--------|-------|----------|
| `Cookie` | `(various cookies)` | **NO** - API works without cookies |

## Key Findings

1. **No Authentication Required**: The search API works without cookies or authentication tokens
2. **Standard Headers Only**: No custom headers are required
3. **CORS Enabled**: The API accepts same-origin requests
4. **Rate Limited**: 500 requests per limit (observed in response headers)

## Example Request (cURL)

```bash
curl -X GET "https://appmagic.rocks/api/v2/search?name=1337578317&limit=20" \
  -H "Accept: application/json, text/plain, */*" \
  -H "Accept-Language: en-US,en;q=0.9" \
  -H "Accept-Encoding: gzip, deflate, br" \
  -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36" \
  -H "Origin: https://appmagic.rocks" \
  -H "Referer: https://appmagic.rocks/top-charts/publishers" \
  -H "Sec-Fetch-Dest: empty" \
  -H "Sec-Fetch-Mode: cors" \
  -H "Sec-Fetch-Site: same-origin" \
  --compressed
```

## Example Request (Python requests)

```python
import requests

url = "https://appmagic.rocks/api/v2/search"
params = {
    "name": "1337578317",
    "limit": 20
}
headers = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Origin": "https://appmagic.rocks",
    "Referer": "https://appmagic.rocks/top-charts/publishers",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin"
}

response = requests.get(url, params=params, headers=headers)
print(response.json())
```

## Minimal Request

The absolute minimum headers needed (tested):

```bash
curl "https://appmagic.rocks/api/v2/search?name=1337578317&limit=20" \
  -H "User-Agent: Mozilla/5.0"
```

However, for best compatibility, include the standard headers listed above.



