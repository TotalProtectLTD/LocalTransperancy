"""
Mitmproxy management for traffic measurement.
"""

import os
import json
import signal
import subprocess
import asyncio
import logging

from cache_config import (
    USE_MITMPROXY,
    MITMPROXY_PORT,
    MITM_ADDON_PATH,
    PROXY_RESULTS_PATH,
    MITMDUMP_SEARCH_PATHS,
    PROXY_STARTUP_WAIT,
    PROXY_SHUTDOWN_WAIT,
    PROXY_TERMINATION_TIMEOUT,
    SUBPROCESS_VERSION_CHECK_TIMEOUT,
    MITMPROXY_SERVER_URL
)

logger = logging.getLogger(__name__)

PROXY_ADDON_SCRIPT = f'''
import json

class TrafficCounter:
    def __init__(self):
        self.total_request_bytes = 0
        self.total_response_bytes = 0
        self.request_count = 0
    
    def request(self, flow):
        """Called for each request."""
        request_size = len(flow.request.raw_content) if flow.request.raw_content else 0
        request_size += sum(len(f"{{k}}: {{v}}\\r\\n".encode()) for k, v in flow.request.headers.items())
        request_size += len(f"{{flow.request.method}} {{flow.request.path}} HTTP/1.1\\r\\n".encode())
        
        self.total_request_bytes += request_size
        self.request_count += 1
    
    def response(self, flow):
        """Called for each response."""
        content_length = flow.response.headers.get('content-length', None)
        if content_length:
            body_size = int(content_length)
        elif flow.response.raw_content:
            body_size = len(flow.response.raw_content)
        else:
            body_size = 0
        
        headers_size = sum(len(f"{{k}}: {{v}}\\r\\n".encode()) for k, v in flow.response.headers.items())
        response_size = body_size + headers_size
        
        self.total_response_bytes += response_size
    
    def done(self):
        """Called when mitmproxy is shutting down."""
        results = {{
            'total_request_bytes': self.total_request_bytes,
            'total_response_bytes': self.total_response_bytes,
            'total_bytes': self.total_request_bytes + self.total_response_bytes,
            'request_count': self.request_count
        }}
        
        with open('{PROXY_RESULTS_PATH}', 'w') as f:
            json.dump(results, f)

addons = [TrafficCounter()]
'''


async def setup_proxy():
    """
    Setup mitmproxy for accurate traffic measurement.
    
    Returns:
        tuple: (proxy_process, use_proxy_flag)
    """
    if not USE_MITMPROXY:
        return None, False
    
    logger.info("🔧 Starting mitmproxy...")
    
    # Write mitmproxy addon script
    with open(MITM_ADDON_PATH, 'w') as f:
        f.write(PROXY_ADDON_SCRIPT)
    
    # Remove old results file
    if os.path.exists(PROXY_RESULTS_PATH):
        os.remove(PROXY_RESULTS_PATH)
    
    # Try to find mitmdump executable
    mitmdump_cmd = None
    for path in MITMDUMP_SEARCH_PATHS:
        try:
            subprocess.run([path, '--version'], capture_output=True, timeout=SUBPROCESS_VERSION_CHECK_TIMEOUT)
            mitmdump_cmd = path
            break
        except:
            continue
    
    if mitmdump_cmd:
        proxy_process = subprocess.Popen(
            [mitmdump_cmd, '-p', MITMPROXY_PORT, '-s', MITM_ADDON_PATH, '--set', 'stream_large_bodies=1'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        await asyncio.sleep(PROXY_STARTUP_WAIT)
        logger.info("✓ Mitmproxy started")
        return proxy_process, True
    else:
        logger.warning("⚠ mitmproxy not found, using estimation mode")
        return None, False


async def teardown_proxy(proxy_process):
    """
    Stop mitmproxy and read traffic results.
    
    Returns:
        dict: Proxy traffic results or None
    """
    if not proxy_process:
        return None
    
    logger.info("🔧 Stopping proxy...")
    proxy_process.send_signal(signal.SIGTERM)
    
    try:
        proxy_process.wait(timeout=PROXY_TERMINATION_TIMEOUT)
    except subprocess.TimeoutExpired:
        logger.warning("⚠️  Proxy did not terminate gracefully, forcing kill...")
        proxy_process.kill()
    
    await asyncio.sleep(PROXY_SHUTDOWN_WAIT)
    
    # Read proxy results
    if os.path.exists(PROXY_RESULTS_PATH):
        with open(PROXY_RESULTS_PATH, 'r') as f:
            return json.load(f)
    
    return None


def get_proxy_config():
    """Get proxy configuration for Playwright context."""
    if USE_MITMPROXY:
        return {
            'proxy': {"server": MITMPROXY_SERVER_URL},
            'ignore_https_errors': True
        }
    return {}

