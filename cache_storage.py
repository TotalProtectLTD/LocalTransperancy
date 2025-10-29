"""
Cache storage layer - handles disk and memory operations.
"""

import os
import json
import time
import threading
import fcntl
import logging

from cache_config import CACHE_DIR, VERSION_TRACKING_FILE, MEMORY_CACHE_MAX_SIZE_MB
from cache_models import CachedFile, get_cache_filename, extract_version_from_url
from datetime import datetime

logger = logging.getLogger(__name__)

# Thread safety
CACHE_LOCKS = {}
CACHE_LOCKS_LOCK = threading.Lock()
VERSION_TRACKING_LOCK = threading.Lock()

# Version change log
VERSION_CHANGE_LOG_FILE = os.path.join(CACHE_DIR, 'version_changes.log')

# In-memory cache
MEMORY_CACHE = {}
MEMORY_CACHE_LOCK = threading.Lock()


def format_bytes(bytes_value):
    """Format bytes into human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} TB"


def get_file_lock(filename):
    """Get or create a lock for a specific file."""
    with CACHE_LOCKS_LOCK:
        if filename not in CACHE_LOCKS:
            CACHE_LOCKS[filename] = threading.Lock()
        return CACHE_LOCKS[filename]


def acquire_file_lock(file_path, timeout=30):
    """Acquire an exclusive lock on a file using fcntl."""
    try:
        lock_file = open(file_path + '.lock', 'w')
        start_time = time.time()
        
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return lock_file
            except IOError:
                if time.time() - start_time > timeout:
                    logger.warning(f"[LOCK TIMEOUT] Could not acquire lock for {file_path}")
                    lock_file.close()
                    return None
                time.sleep(0.1)
    except Exception as e:
        logger.error(f"[LOCK ERROR] Failed to acquire lock for {file_path}: {e}")
        return None


def release_file_lock(lock_file):
    """Release file lock and close lock file."""
    if lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
            if os.path.exists(lock_file.name):
                os.remove(lock_file.name)
        except Exception as e:
            logger.error(f"[LOCK RELEASE ERROR] {e}")


def get_memory_cache_size():
    """Get current memory cache size in bytes."""
    return sum(cf.size for cf in MEMORY_CACHE.values())


def evict_from_memory_cache():
    """Evict least recently used items from memory cache."""
    max_size_bytes = MEMORY_CACHE_MAX_SIZE_MB * 1024 * 1024
    items = sorted(MEMORY_CACHE.items(), key=lambda x: x[1].memory_cached_at)
    
    while get_memory_cache_size() > max_size_bytes and items:
        filename, cached_file = items.pop(0)
        del MEMORY_CACHE[filename]
        logger.info(f"[MEMORY EVICT] {filename} ({format_bytes(cached_file.size)})")


def get_version_tracking_path():
    """Get full path to version tracking file."""
    return os.path.join(CACHE_DIR, VERSION_TRACKING_FILE)


def log_version_change(old_version, new_version, old_url, new_url, old_size, new_size):
    """Log version change to file in the cache directory."""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        log_entry = f"[{timestamp}] VERSION UPDATE\n"
        log_entry += f"  Old version: {old_version}\n"
        log_entry += f"  New version: {new_version}\n"
        log_entry += f"  Old URL: {old_url}\n"
        log_entry += f"  New URL: {new_url}\n"
        log_entry += f"  Size change: {format_bytes(old_size)} → {format_bytes(new_size)} "
        log_entry += f"({new_size - old_size:+,} bytes)\n"
        log_entry += "-" * 80 + "\n\n"
        
        # Append to log file (thread-safe)
        with open(VERSION_CHANGE_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
            f.flush()
            
        logger.info(f"[VERSION LOG] Written to {VERSION_CHANGE_LOG_FILE}")
        
    except Exception as e:
        logger.error(f"[VERSION LOG ERROR] Failed to write log: {e}")


def load_version_tracking():
    """Load version tracking data from disk (thread-safe)."""
    with VERSION_TRACKING_LOCK:
        tracking_path = get_version_tracking_path()
        
        if not os.path.exists(tracking_path):
            return {}
        
        try:
            with open(tracking_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[VERSION TRACKING] Failed to load tracking file: {e}")
            return {}


def save_version_tracking(tracking_data):
    """Save version tracking data to disk (thread-safe with atomic write)."""
    with VERSION_TRACKING_LOCK:
        tracking_path = get_version_tracking_path()
        
        try:
            temp_path = tracking_path + '.tmp'
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(tracking_data, f, indent=2)
            
            os.replace(temp_path, tracking_path)
        except Exception as e:
            logger.error(f"[VERSION TRACKING] Failed to save tracking file: {e}")
            temp_path = tracking_path + '.tmp'
            if os.path.exists(temp_path):
                os.remove(temp_path)


def check_version_changed(url):
    """Check if the URL version has changed compared to cached version."""
    filename = get_cache_filename(url)
    current_version = extract_version_from_url(url)
    
    if not current_version:
        return False, None, None
    
    tracking_data = load_version_tracking()
    
    if filename not in tracking_data:
        return False, current_version, None
    
    cached_version = tracking_data[filename].get('version')
    
    if cached_version != current_version:
        # Enhanced version change logging
        cached_url = tracking_data[filename].get('url', 'N/A')
        logger.warning(f"[VERSION CHANGE] {filename}: {cached_version} -> {current_version}")
        logger.warning(f"   Cached version: {cached_version}")
        logger.warning(f"   Current version: {current_version}")
        logger.warning(f"   Cached URL: {cached_url}")
        logger.warning(f"   Current URL: {url}")
        return True, current_version, cached_version
    
    return False, current_version, cached_version


def update_version_tracking(url):
    """Update version tracking for a URL."""
    filename = get_cache_filename(url)
    version = extract_version_from_url(url)
    
    if not version:
        return
    
    tracking_data = load_version_tracking()
    
    tracking_data[filename] = {
        'version': version,
        'url': url,
        'updated_at': time.time()
    }
    
    save_version_tracking(tracking_data)
    logger.info(f"[VERSION TRACKING] Updated {filename} -> {version}")


async def save_to_cache(url, content, headers=None):
    """Save content to cache (both memory and disk) - thread-safe."""
    filename = get_cache_filename(url)
    cache_path = os.path.join(CACHE_DIR, filename)
    
    # SAFEGUARD: Only cache files with version suffixes
    # This prevents accidental caching of non-versioned files
    if '_v_' not in filename:
        error_msg = f"CACHE SAFEGUARD: Refusing to save file without version suffix!\n   Filename: {filename}\n   URL: {url}"
        print(f"❌ {error_msg}")
        logger.error(error_msg)
        # Return False to indicate cache save was skipped
        return False
    
    # DEBUG: Log what filename is being used
    print(f"💾 SAVING TO CACHE: {filename}")
    
    file_lock = get_file_lock(filename)
    
    with file_lock:
        lock_file = acquire_file_lock(cache_path)
        
        try:
            metadata_path = os.path.join(CACHE_DIR, f"{filename}.meta.json")
            version = extract_version_from_url(url)
            
            # Check if this is an update to an existing file
            was_update = os.path.exists(cache_path)
            old_size = 0
            if was_update and os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        old_metadata = json.load(f)
                    old_size = old_metadata.get('size', 0)
                    old_version = old_metadata.get('version')
                    
                    # Log detailed version update information
                    if old_version and old_version != version:
                        size_diff = len(content) - old_size
                        print(f"   📊 Version Comparison:")
                        print(f"      Size: {format_bytes(old_size)} → {format_bytes(len(content))} ({size_diff:+,} bytes)")
                        print(f"      Old URL: {old_metadata.get('url', 'N/A')}")
                        print(f"      New URL: {url}")
                        
                        # Write to version change log file
                        log_version_change(
                            old_version=old_version,
                            new_version=version,
                            old_url=old_metadata.get('url', 'N/A'),
                            new_url=url,
                            old_size=old_size,
                            new_size=len(content)
                        )
                except:
                    pass
            
            # Save content atomically to disk
            temp_path = cache_path + '.tmp'
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            os.replace(temp_path, cache_path)
            
            # Save metadata to disk
            metadata = {
                'url': url,
                'cached_at': time.time(),
                'size': len(content),
                'version': version,
                'etag': headers.get('etag') if headers else None,
                'last_modified': headers.get('last-modified') if headers else None,
                'cache_control': headers.get('cache-control') if headers else None
            }
            
            temp_meta_path = metadata_path + '.tmp'
            with open(temp_meta_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            os.replace(temp_meta_path, metadata_path)
            
            # Update version tracking
            update_version_tracking(url)
            
            # Store in memory cache
            with MEMORY_CACHE_LOCK:
                if get_memory_cache_size() + len(content) > MEMORY_CACHE_MAX_SIZE_MB * 1024 * 1024:
                    evict_from_memory_cache()
                
                cached_file = CachedFile(url=url, content=content, headers=headers)
                MEMORY_CACHE[filename] = cached_file
            
            if was_update:
                logger.info(f"[CACHE UPDATE] {filename} ({format_bytes(len(content))}, version: {version}) → disk + memory")
            else:
                logger.info(f"[CACHE SAVE] {filename} ({format_bytes(len(content))}, version: {version}) → disk + memory")
            return True
            
        except Exception as e:
            logger.error(f"[CACHE SAVE ERROR] Failed to save to cache: {e}")
            # Clean up temp files
            for temp in [cache_path + '.tmp', metadata_path + '.tmp']:
                if os.path.exists(temp):
                    os.remove(temp)
            return False
            
        finally:
            release_file_lock(lock_file)


def load_from_cache(url):
    """Load content from cache (L1: memory, L2: disk) - thread-safe."""
    filename = get_cache_filename(url)
    
    # L1: Try memory cache first
    with MEMORY_CACHE_LOCK:
        if filename in MEMORY_CACHE:
            cached_file = MEMORY_CACHE[filename]
            is_valid, reason = cached_file.is_valid(url)
            
            if is_valid:
                age_hours = (time.time() - cached_file.cached_at) / 3600
                logger.info(f"[MEMORY HIT] {filename} ({format_bytes(cached_file.size)}, age: {age_hours:.1f}h)")
                metadata = cached_file.to_metadata_dict()
                metadata['cache_level'] = 'memory'
                return cached_file.content, metadata
            else:
                logger.info(f"[MEMORY INVALIDATE] {filename}: {reason}")
                del MEMORY_CACHE[filename]
    
    # L2: Try disk cache
    cache_path = os.path.join(CACHE_DIR, filename)
    file_lock = get_file_lock(filename)
    
    with file_lock:
        try:
            metadata_path = os.path.join(CACHE_DIR, f"{filename}.meta.json")
            
            if not os.path.exists(cache_path):
                return None, None
            
            # Load metadata
            metadata = None
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            
            # Version check removed - we now cache multiple versions simultaneously
            # Google load-balances between different versions, so we keep all versions
            # and only expire based on age (24 hours)
            
            # Check age
            if metadata:
                from cache_config import CACHE_MAX_AGE_HOURS
                if CACHE_MAX_AGE_HOURS > 0:
                    cached_at = metadata.get('cached_at', 0)
                    age_hours = (time.time() - cached_at) / 3600
                    
                    if age_hours > CACHE_MAX_AGE_HOURS:
                        logger.warning(f"[CACHE EXPIRED] {filename} is {age_hours:.1f} hours old")
                        logger.info(f"[DISK INVALIDATE] Removing {filename}: age expired")
                        
                        for path in [cache_path, metadata_path]:
                            if os.path.exists(path):
                                os.remove(path)
                        
                        return None, None
            
            # Load content from disk
            with open(cache_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Store in memory cache
            with MEMORY_CACHE_LOCK:
                if get_memory_cache_size() + len(content) > MEMORY_CACHE_MAX_SIZE_MB * 1024 * 1024:
                    evict_from_memory_cache()
                
                # Use cached URL from metadata to preserve original version info
                cached_url = metadata.get('url', url) if metadata else url
                cached_file = CachedFile(
                    url=cached_url,
                    content=content,
                    headers={
                        'etag': metadata.get('etag'),
                        'last-modified': metadata.get('last_modified'),
                        'cache-control': metadata.get('cache_control')
                    } if metadata else None,
                    disk_cached_at=metadata.get('cached_at') if metadata else None
                )
                
                MEMORY_CACHE[filename] = cached_file
                age_hours = (time.time() - cached_file.cached_at) / 3600
                logger.info(f"[DISK HIT] {filename} ({format_bytes(len(content))}, age: {age_hours:.1f}h) → stored in memory")
            
            # Add cache_level to metadata for reporting
            if metadata:
                metadata['cache_level'] = 'disk'
            
            return content, metadata
            
        except Exception as e:
            logger.error(f"[CACHE LOAD ERROR] Failed to load from cache: {e}")
            return None, None


def get_cache_status():
    """Get status of all cached files with version tracking."""
    cache_files = []
    
    if not os.path.exists(CACHE_DIR):
        return cache_files
    
    version_tracking = load_version_tracking()
    
    for filename in os.listdir(CACHE_DIR):
        if filename.endswith('.meta.json') or filename == VERSION_TRACKING_FILE:
            continue
        
        file_path = os.path.join(CACHE_DIR, filename)
        meta_path = os.path.join(CACHE_DIR, f"{filename}.meta.json")
        
        if not os.path.isfile(file_path):
            continue
        
        file_info = {
            'filename': filename,
            'size': os.path.getsize(file_path),
            'has_metadata': os.path.exists(meta_path)
        }
        
        if file_info['has_metadata']:
            try:
                with open(meta_path, 'r') as f:
                    metadata = json.load(f)
                
                cached_at = metadata.get('cached_at', 0)
                age_hours = (time.time() - cached_at) / 3600
                
                from cache_config import CACHE_MAX_AGE_HOURS
                file_info.update({
                    'cached_at': cached_at,
                    'age_hours': age_hours,
                    'expired': age_hours > CACHE_MAX_AGE_HOURS if CACHE_MAX_AGE_HOURS > 0 else False,
                    'version': metadata.get('version'),
                    'etag': metadata.get('etag'),
                    'last_modified': metadata.get('last_modified'),
                    'url': metadata.get('url')
                })
            except:
                pass
        
        if filename in version_tracking:
            file_info['tracked_version'] = version_tracking[filename].get('version')
        
        cache_files.append(file_info)
    
    return sorted(cache_files, key=lambda x: x.get('cached_at', 0), reverse=True)

