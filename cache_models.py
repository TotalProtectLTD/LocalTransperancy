"""
Cache data models and structures.
"""

import time
from cache_config import (
    VERSION_AWARE_CACHING,
    CACHE_MAX_AGE_HOURS,
    MEMORY_CACHE_TTL_SECONDS
)


def extract_version_from_url(url):
    """
    Extract version identifier from URL by getting the parent folder path.
    
    Example:
    URL: https://www.gstatic.com/acx/transparency/report/folder/main.dart.js
    Returns: /acx/transparency/report/folder
    """
    from urllib.parse import urlparse
    
    try:
        parsed = urlparse(url)
        path = parsed.path
        
        if '/main.dart.js' in path:
            version_path = path.rsplit('/main.dart.js', 1)[0]
            return version_path
        
        path_parts = path.rsplit('/', 1)
        return path_parts[0] if len(path_parts) > 1 else None
        
    except Exception:
        return None


def get_cache_filename(url):
    """Generate cache filename from URL."""
    parts = url.split('/')
    filename = parts[-1]
    
    if '?' in filename:
        filename = filename.split('?')[0]
    
    return filename


class CachedFile:
    """Complete cached file with content and all metadata."""
    
    def __init__(self, url, content, headers=None, disk_cached_at=None):
        self.content = content
        self.url = url
        self.filename = get_cache_filename(url)
        self.version = extract_version_from_url(url)
        self.size = len(content)
        
        # Timestamps
        self.cached_at = disk_cached_at if disk_cached_at else time.time()
        self.memory_cached_at = time.time()
        
        # HTTP headers
        if headers:
            self.etag = headers.get('etag')
            self.last_modified = headers.get('last-modified')
            self.cache_control = headers.get('cache-control')
        else:
            self.etag = None
            self.last_modified = None
            self.cache_control = None
    
    def is_valid(self, current_url):
        """Check if cached file is still valid."""
        # Check 1: Version validation
        if VERSION_AWARE_CACHING:
            current_version = extract_version_from_url(current_url)
            if self.version != current_version:
                return False, f"version changed: {self.version} → {current_version}"
        
        # Check 2: Age validation
        if CACHE_MAX_AGE_HOURS > 0:
            age_hours = (time.time() - self.cached_at) / 3600
            if age_hours > CACHE_MAX_AGE_HOURS:
                return False, f"age {age_hours:.1f}h > max {CACHE_MAX_AGE_HOURS}h"
        
        # Check 3: Memory cache TTL
        memory_age = time.time() - self.memory_cached_at
        if memory_age > MEMORY_CACHE_TTL_SECONDS:
            return False, f"memory cache stale ({memory_age:.0f}s > {MEMORY_CACHE_TTL_SECONDS}s)"
        
        return True, "valid"
    
    def to_metadata_dict(self):
        """Convert to metadata dictionary."""
        return {
            'url': self.url,
            'cached_at': self.cached_at,
            'size': self.size,
            'version': self.version,
            'etag': self.etag,
            'last_modified': self.last_modified,
            'cache_control': self.cache_control
        }

