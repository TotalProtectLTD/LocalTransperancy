# Mitmproxy Integration Guide

## Overview

The `fighting_cache_problem.py` script now includes **mitmproxy support** for precise traffic measurement, similar to `google_ads_transparency_scraper.py`.

## Features

### Traffic Measurement Modes

1. **Estimation Mode** (default, `USE_MITMPROXY = False`)
   - Fast, no proxy needed
   - No traffic measurement currently implemented
   - Good for debugging and development

2. **Mitmproxy Mode** (`USE_MITMPROXY = True`)
   - Precise traffic measurement
   - Captures exact byte counts for requests and responses
   - Requires mitmproxy/mitmdump to be installed

## Installation

### Install Mitmproxy

```bash
pip install mitmproxy
```

Or on macOS:
```bash
brew install mitmproxy
```

### Verify Installation

```bash
mitmdump --version
```

## Configuration

### Enable Mitmproxy

Edit `fighting_cache_problem.py` and set:

```python
USE_MITMPROXY = True  # Enable mitmproxy for precise traffic measurement
```

### Mitmproxy Settings

The following constants control mitmproxy behavior:

```python
# Mitmproxy settings
MITMPROXY_PORT = '8080'  # Port for mitmproxy server
MITMPROXY_SERVER_URL = 'http://localhost:8080'  # Proxy server URL
MITM_ADDON_PATH = '/tmp/mitm_addon_fighting_cache.py'  # Addon script path
PROXY_RESULTS_PATH = '/tmp/proxy_results_fighting_cache.json'  # Results file

# Timeouts
PROXY_STARTUP_WAIT = 3  # seconds to wait for mitmproxy to start
PROXY_SHUTDOWN_WAIT = 1  # seconds to wait after proxy shutdown
PROXY_TERMINATION_TIMEOUT = 10  # timeout for proxy process termination
```

## How It Works

### 1. Proxy Setup Phase

When the script starts with `USE_MITMPROXY = True`:

1. Creates a mitmproxy addon script at `/tmp/mitm_addon_fighting_cache.py`
2. Starts `mitmdump` process on port 8080
3. Waits 3 seconds for proxy to initialize
4. Configures Playwright browser context to use the proxy

### 2. Traffic Capture Phase

During page scraping:

1. All browser requests go through mitmproxy
2. Mitmproxy addon counts bytes for each request/response:
   - Request size = URL + headers + body
   - Response size = headers + body (from Content-Length or actual size)
3. Counts are accumulated in the addon's state

### 3. Proxy Teardown Phase

After scraping completes:

1. Sends SIGTERM to mitmdump process
2. Waits up to 10 seconds for graceful shutdown
3. Reads traffic results from `/tmp/proxy_results_fighting_cache.json`
4. Displays traffic statistics in final summary

## Output

### With Mitmproxy Enabled

```
Traffic Statistics:
  - Measurement method: proxy (precise)
  - Incoming: 1.23 MB
  - Outgoing: 45.67 KB
  - Total: 1.28 MB
  - Duration: 15234 ms
```

### Without Mitmproxy (Estimation Mode)

```
Traffic Statistics:
  - Measurement method: estimation (not implemented)
```

## Traffic Results Format

The proxy results JSON file contains:

```json
{
  "total_request_bytes": 46789,
  "total_response_bytes": 1289456,
  "total_bytes": 1336245,
  "request_count": 63
}
```

## Comparison with google_ads_transparency_scraper.py

| Feature | fighting_cache_problem.py | google_ads_transparency_scraper.py |
|---------|---------------------------|-------------------------------------|
| Mitmproxy support | ✅ Yes | ✅ Yes |
| Estimation mode | ⚠️ Not implemented | ✅ Content-Length headers |
| Proxy addon script | ✅ Separate file | ✅ Separate file |
| Traffic by type | ❌ No | ✅ Yes |
| Blocking stats | ✅ Yes | ✅ Yes |
| Cache stats | ✅ Yes (main.dart.js) | ❌ No |

## Troubleshooting

### Mitmproxy Not Found

**Error:**
```
⚠ mitmproxy not found, using estimation mode
```

**Solution:**
```bash
pip install mitmproxy
# or
brew install mitmproxy
```

### Proxy Startup Timeout

**Error:**
```
⚠️  Proxy did not terminate gracefully, forcing kill...
```

**Solution:**
- Increase `PROXY_TERMINATION_TIMEOUT` in the script
- Check if port 8080 is already in use: `lsof -i :8080`

### HTTPS Certificate Errors

**Error:**
```
SSL certificate verification failed
```

**Solution:**
- The script automatically sets `ignore_https_errors=True` when proxy is enabled
- If issues persist, install mitmproxy's CA certificate:
  ```bash
  mitmdump  # Start once to generate certificate
  # Follow instructions to install certificate
  ```

## Advanced Usage

### Custom Proxy Port

Edit the configuration:

```python
MITMPROXY_PORT = '9090'  # Use port 9090 instead
MITMPROXY_SERVER_URL = 'http://localhost:9090'
```

### External Proxy

To use an external proxy instead of mitmproxy, modify the browser context setup:

```python
context_options['proxy'] = {
    'server': 'http://proxy.example.com:8080',
    'username': 'user',
    'password': 'pass'
}
```

## Future Enhancements

### Estimation Mode Implementation

To add Content-Length based estimation (like google_ads_transparency_scraper.py):

1. Add byte tracking to `NetworkLogger`:
   ```python
   self.incoming_bytes = 0
   self.outgoing_bytes = 0
   ```

2. Track in `log_request` and `log_response`:
   ```python
   def log_request(self, request):
       # Calculate request size
       url_size = len(request.url.encode())
       headers_size = sum(len(f"{k}: {v}\r\n".encode()) 
                         for k, v in request.headers.items())
       self.outgoing_bytes += url_size + headers_size + 100
   
   async def log_response(self, response):
       # Get Content-Length
       content_length = response.headers.get('content-length')
       if content_length:
           self.incoming_bytes += int(content_length)
   ```

3. Use in final summary when proxy not enabled

### Traffic by Type

Add resource type tracking similar to `google_ads_transparency_scraper.py`:

```python
self.incoming_by_type = defaultdict(int)
self.outgoing_by_type = defaultdict(int)
```

## References

- [Mitmproxy Documentation](https://docs.mitmproxy.org/)
- [Playwright Proxy Documentation](https://playwright.dev/python/docs/network#http-proxy)
- `google_ads_transparency_scraper.py` - Reference implementation

