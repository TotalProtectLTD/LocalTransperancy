# Multi-Proxy Rotation - Simplified Plan

## Overview
Simple round-robin proxy rotation: each worker gets a consistent proxy from a list.

## Changes Needed

### 1. Replace Single Proxy Variables (Lines 116-119)
**Change from:**
```python
PROXY_HOST = "hub-us-8.litport.net"
PROXY_PORT = 31337
PROXY_USERNAME = "7zQu8tyk"
PROXY_PASSWORD = "l0n7LLeQiA"
```

**Change to:**
```python
# List of proxies - add 5+ proxies here
PROXIES = [
    {"host": "hub-us-8.litport.net", "port": 31337, "username": "7zQu8tyk", "password": "l0n7LLeQiA"},
    {"host": "hub-us-7.litport.net", "port": 31337, "username": "user2", "password": "pass2"},
    {"host": "hub-us-6.litport.net", "port": 31337, "username": "user3", "password": "pass3"},
    {"host": "hub-us-5.litport.net", "port": 31337, "username": "user4", "password": "pass4"},
    {"host": "hub-us-4.litport.net", "port": 31337, "username": "user5", "password": "pass5"},
    # Add more proxies here...
]
```

### 2. Update `generate_proxy_config()` Function (Lines 455-469)
**Change from:** Returns single proxy config

**Change to:** Accept worker_id, return proxy based on round-robin
```python
def get_proxy_config(worker_id: int = 0) -> Optional[Dict[str, str]]:
    """
    Get proxy configuration for a worker (round-robin rotation).
    
    Args:
        worker_id: Worker ID to determine which proxy to use
        
    Returns:
        Dict with server, username, password or None if no proxies configured
    """
    if not PROXIES:
        return None
    
    # Round-robin: worker_id % len(PROXIES)
    proxy = PROXIES[worker_id % len(PROXIES)]
    
    return {
        "server": f"http://{proxy['host']}:{proxy['port']}",
        "username": proxy['username'],
        "password": proxy['password']
    }
```

### 3. Update Worker Function (Line 888)
**Change:** Pass worker_id to get_proxy_config instead of using global proxy_config
```python
# In worker() function, replace:
proxy_config = generate_proxy_config() if use_proxy else None

# With:
proxy_config = get_proxy_config(worker_id) if use_proxy and PROXIES else None
```

### 4. Update `run_stress_test()` (Line 1062)
**Change:** Remove single proxy_config generation, workers get their own
```python
# Remove this line:
proxy_config = generate_proxy_config() if use_proxy else None

# Update display:
if PROXIES and use_proxy:
    print(f"  Proxies:        {len(PROXIES)} proxies (round-robin per worker)")
    for i, proxy in enumerate(PROXIES):
        print(f"    [{i+1}] {proxy['host']}:{proxy['port']}")
```

### 5. Update IP Check (Line 1103)
**Change:** Check IP for each proxy at startup
```python
if PROXIES and use_proxy:
    print("\n🔄 Checking IPs for all proxies...")
    for i, proxy in enumerate(PROXIES):
        proxy_config = get_proxy_config(i)
        ip = await get_current_ip(proxy_config)
        print(f"  Proxy {i+1}: {ip or 'Failed'}")
```

## Summary
- **3 main changes:**
  1. Replace single proxy vars with PROXIES list
  2. Change `generate_proxy_config()` to `get_proxy_config(worker_id)` for round-robin
  3. Update worker() to call `get_proxy_config(worker_id)`

- **Result:** Each worker gets a consistent proxy from the list based on worker_id
- **No complex health tracking, no failover, just simple rotation**
