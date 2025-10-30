#!/usr/bin/env python3
"""
Advertiser Utilities - Local Transparency

Utility functions for advertiser ID ↔ name lookups and batch operations.
Supports efficient lookups and inserts for 3.5M+ rows.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, List, Tuple, Dict
from contextlib import contextmanager
import logging

# Database configuration (matches setup_database.py)
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432
}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()


def normalize_name(name: str) -> str:
    """
    Normalize advertiser name for case-insensitive matching.
    
    Args:
        name: Advertiser name
    
    Returns:
        Normalized name (lowercase, stripped)
    """
    return name.lower().strip() if name else ""


# ============================================================================
# LOOKUP FUNCTIONS
# ============================================================================

def get_advertiser_name(advertiser_id: str) -> Optional[str]:
    """
    Get advertiser name by ID (fast lookup using primary key).
    
    Args:
        advertiser_id: Advertiser ID
    
    Returns:
        Advertiser name if found, None otherwise
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT advertiser_name FROM advertisers WHERE advertiser_id = %s",
                (advertiser_id,)
            )
            result = cursor.fetchone()
            cursor.close()
            return result[0] if result else None
    except Exception as e:
        logger.error(f"Error getting advertiser name for ID {advertiser_id}: {e}")
        return None


def get_advertiser_ids(advertiser_name: str) -> List[str]:
    """
    Get all advertiser IDs by name (not unique - can return multiple IDs).
    
    Args:
        advertiser_name: Advertiser name
    
    Returns:
        List of advertiser IDs (can be empty if not found)
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Use normalized name for case-insensitive matching
            normalized = normalize_name(advertiser_name)
            cursor.execute(
                "SELECT advertiser_id FROM advertisers WHERE advertiser_name_normalized = %s",
                (normalized,)
            )
            results = cursor.fetchall()
            cursor.close()
            return [row[0] for row in results]
    except Exception as e:
        logger.error(f"Error getting advertiser IDs for name '{advertiser_name}': {e}")
        return []


def get_advertiser_id(advertiser_name: str) -> Optional[str]:
    """
    Get first advertiser ID by name (convenience function).
    
    Note: Since advertiser_name is not unique, this returns the first match.
    Use get_advertiser_ids() if you need all matches.
    
    Args:
        advertiser_name: Advertiser name
    
    Returns:
        First advertiser ID found, or None
    """
    ids = get_advertiser_ids(advertiser_name)
    return ids[0] if ids else None


def batch_get_advertiser_names(advertiser_ids: List[str]) -> Dict[str, str]:
    """
    Bulk lookup: Get advertiser names for multiple IDs (single query).
    
    Args:
        advertiser_ids: List of advertiser IDs
    
    Returns:
        Dictionary mapping advertiser_id → advertiser_name
    """
    if not advertiser_ids:
        return {}
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Use parameterized query with ANY(array) for efficiency
            cursor.execute(
                "SELECT advertiser_id, advertiser_name FROM advertisers WHERE advertiser_id = ANY(%s)",
                (list(advertiser_ids),)
            )
            results = cursor.fetchall()
            cursor.close()
            return dict(results)
    except Exception as e:
        logger.error(f"Error in batch_get_advertiser_names: {e}")
        return {}


def batch_get_advertiser_ids(advertiser_names: List[str]) -> Dict[str, List[str]]:
    """
    Bulk lookup: Get advertiser IDs for multiple names (normalized).
    
    Args:
        advertiser_names: List of advertiser names
    
    Returns:
        Dictionary mapping advertiser_name → List[advertiser_id]
        (multiple IDs possible per name)
    """
    if not advertiser_names:
        return {}
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Normalize all names
            normalized_names = [normalize_name(name) for name in advertiser_names]
            cursor.execute(
                "SELECT advertiser_name_normalized, advertiser_id FROM advertisers WHERE advertiser_name_normalized = ANY(%s)",
                (list(normalized_names),)
            )
            results = cursor.fetchall()
            cursor.close()
            
            # Build result dictionary
            result_dict = {name: [] for name in advertiser_names}
            normalized_to_original = {normalize_name(name): name for name in advertiser_names}
            
            for normalized, adv_id in results:
                original_name = normalized_to_original.get(normalized)
                if original_name:
                    result_dict[original_name].append(adv_id)
            
            return result_dict
    except Exception as e:
        logger.error(f"Error in batch_get_advertiser_ids: {e}")
        return {}


# ============================================================================
# INSERT FUNCTIONS
# ============================================================================

def insert_advertiser(advertiser_id: str, advertiser_name: str, country: Optional[str] = None, skip_duplicate: bool = True) -> bool:
    """
    Insert a single advertiser (with duplicate handling).
    
    Args:
        advertiser_id: Advertiser ID
        advertiser_name: Advertiser name
        country: Optional country code (e.g., 'US', 'CA', 'FR')
        skip_duplicate: If True, skip on conflict (no error). If False, raise error on conflict.
    
    Returns:
        True if inserted or skipped (when skip_duplicate=True), False on error
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            normalized = normalize_name(advertiser_name)
            
            if skip_duplicate:
                cursor.execute("""
                    INSERT INTO advertisers (advertiser_id, advertiser_name, advertiser_name_normalized, country)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (advertiser_id) DO NOTHING
                """, (advertiser_id, advertiser_name, normalized, country))
            else:
                cursor.execute("""
                    INSERT INTO advertisers (advertiser_id, advertiser_name, advertiser_name_normalized, country)
                    VALUES (%s, %s, %s, %s)
                """, (advertiser_id, advertiser_name, normalized, country))
            
            conn.commit()
            inserted = cursor.rowcount > 0
            cursor.close()
            return inserted if skip_duplicate else True
    except psycopg2.IntegrityError as e:
        if skip_duplicate:
            logger.debug(f"Advertiser {advertiser_id} already exists, skipping")
            return True
        logger.error(f"Integrity error inserting advertiser {advertiser_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error inserting advertiser {advertiser_id}: {e}")
        return False


def batch_insert_advertisers(
    advertisers: List[Tuple], 
    batch_size: int = 1000,
    skip_duplicate: bool = True
) -> Dict[str, int]:
    """
    Batch insert advertisers with duplicate handling and statistics.
    
    Args:
        advertisers: List of tuples, either:
                     - (advertiser_id, advertiser_name) for backward compatibility
                     - (advertiser_id, advertiser_name, country) with country code
        batch_size: Number of rows to insert per batch
        skip_duplicate: If True, skip duplicates without error
    
    Returns:
        Dictionary with statistics: {'inserted': int, 'skipped': int, 'errors': int, 'total': int}
    """
    stats = {'inserted': 0, 'skipped': 0, 'errors': 0, 'total': len(advertisers)}
    
    if not advertisers:
        return stats
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Process in batches
            for i in range(0, len(advertisers), batch_size):
                batch = advertisers[i:i + batch_size]
                
                # Prepare batch data with normalized names
                # Handle both (id, name) and (id, name, country) tuple formats
                batch_data = []
                for item in batch:
                    if len(item) == 2:
                        adv_id, adv_name = item
                        country = None
                    elif len(item) == 3:
                        adv_id, adv_name, country = item
                    else:
                        raise ValueError(f"Invalid tuple format: expected 2 or 3 elements, got {len(item)}")
                    
                    batch_data.append((adv_id, adv_name, normalize_name(adv_name), country))
                
                try:
                    if skip_duplicate:
                        # Use executemany with ON CONFLICT
                        cursor.executemany("""
                            INSERT INTO advertisers (advertiser_id, advertiser_name, advertiser_name_normalized, country)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (advertiser_id) DO NOTHING
                        """, batch_data)
                        batch_inserted = cursor.rowcount
                        stats['inserted'] += batch_inserted
                        stats['skipped'] += len(batch) - batch_inserted
                    else:
                        cursor.executemany("""
                            INSERT INTO advertisers (advertiser_id, advertiser_name, advertiser_name_normalized, country)
                            VALUES (%s, %s, %s, %s)
                        """, batch_data)
                        stats['inserted'] += len(batch)
                    
                    conn.commit()
                    
                except psycopg2.IntegrityError as e:
                    if skip_duplicate:
                        # Fall back to individual inserts if batch fails
                        conn.rollback()
                        for adv_id, adv_name, normalized, country in batch_data:
                            if insert_advertiser(adv_id, adv_name, country=country, skip_duplicate=True):
                                stats['inserted'] += 1
                            else:
                                stats['skipped'] += 1
                    else:
                        conn.rollback()
                        stats['errors'] += len(batch)
                        logger.error(f"Batch insert error: {e}")
                        # Continue with next batch
                
                except Exception as e:
                    conn.rollback()
                    stats['errors'] += len(batch)
                    logger.error(f"Error in batch insert: {e}")
                    # Continue with next batch
            
            cursor.close()
            
    except Exception as e:
        logger.error(f"Error in batch_insert_advertisers: {e}")
        stats['errors'] = stats['total'] - stats['inserted'] - stats['skipped']
    
    return stats


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_statistics() -> Dict[str, int]:
    """
    Get statistics about the advertisers table.
    
    Returns:
        Dictionary with: {'total_advertisers': int, 'unique_names': int}
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT COUNT(*) as total FROM advertisers")
            total = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(DISTINCT advertiser_name_normalized) as unique_names FROM advertisers")
            unique_names = cursor.fetchone()['unique_names']
            
            cursor.close()
            return {
                'total_advertisers': total,
                'unique_names': unique_names
            }
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        return {'total_advertisers': 0, 'unique_names': 0}


if __name__ == "__main__":
    # Example usage
    print("=" * 60)
    print("ADVERTISER UTILITIES - Example Usage")
    print("=" * 60)
    
    # Test connection
    print("\n1. Testing connection...")
    stats = get_statistics()
    print(f"   Total advertisers: {stats['total_advertisers']}")
    print(f"   Unique names: {stats['unique_names']}")
    
    print("\n✅ Advertiser utilities loaded successfully!")
    print("\nAvailable functions:")
    print("  - get_advertiser_name(advertiser_id)")
    print("  - get_advertiser_id(advertiser_name)")
    print("  - get_advertiser_ids(advertiser_name)  # Returns list (multiple IDs possible)")
    print("  - batch_get_advertiser_names(advertiser_ids)")
    print("  - batch_get_advertiser_ids(advertiser_names)")
    print("  - insert_advertiser(advertiser_id, advertiser_name)")
    print("  - batch_insert_advertisers(advertisers, batch_size=1000)")
    print("  - get_statistics()")
