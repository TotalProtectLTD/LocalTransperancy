"""
Data Extraction Module for Google Ads Transparency Scraper

This module contains data extraction functions for parsing YouTube video IDs 
and App Store IDs from content.js responses and API data. It uses regex 
patterns defined in google_ads_config.py to handle multiple data formats 
including standard URLs, escaped URLs, and JSON field patterns.

Functions:
    - extract_youtube_videos_from_text: Extracts YouTube video IDs from text
    - extract_app_store_id_from_text: Extracts App Store IDs from text
"""

import re
from typing import List, Optional, Tuple

from google_ads_config import (
    PATTERN_YOUTUBE_THUMBNAIL,
    PATTERN_YOUTUBE_VIDEO_ID_FIELD,
    PATTERN_YOUTUBE_VIDEO_ID_CAMELCASE,
    PATTERN_APPSTORE_STANDARD,
    PATTERN_APPSTORE_ESCAPED,
    PATTERN_APPSTORE_DIRECT,
    PATTERN_APPSTORE_JSON
)


# ============================================================================
# DATA EXTRACTION
# ============================================================================

def extract_youtube_videos_from_text(text: str) -> List[str]:
    """
    Extract YouTube video IDs from text.
    
    Handles multiple patterns:
    - ytimg.com thumbnails: i.ytimg.com/vi/VIDEO_ID/
    - video_id field: 'video_id': 'VIDEO_ID' or "video_id": "VIDEO_ID"
    - video_videoId field: 'video_videoId': 'VIDEO_ID' (camelCase variant)
    - Escaped quotes: \\x27video_id\\x27: \\x27VIDEO_ID\\x27
    
    Args:
        text: Text content to search
        
    Returns:
        list: List of 11-character YouTube video IDs
    """
    videos = []
    
    # Pattern 1: ytimg.com thumbnails
    pattern = re.compile(PATTERN_YOUTUBE_THUMBNAIL)
    videos.extend(pattern.findall(text))
    
    # Pattern 2: video_id field (with regular or escaped quotes)
    # Matches: 'video_id': 'ID', "video_id": "ID", \x27video_id\x27: \x27ID\x27
    pattern = re.compile(PATTERN_YOUTUBE_VIDEO_ID_FIELD)
    videos.extend(pattern.findall(text))
    
    # Pattern 3: video_videoId field (camelCase variant)
    # Matches: 'video_videoId': 'ID', "video_videoId": "ID", \x27video_videoId\x27: \x27ID\x27
    pattern = re.compile(PATTERN_YOUTUBE_VIDEO_ID_CAMELCASE)
    videos.extend(pattern.findall(text))
    
    return list(set(videos))


def extract_app_store_id_from_text(text: str) -> Optional[Tuple[str, str]]:
    """
    Extract App Store ID from text.
    
    Handles multiple URL formats:
    - https://apps.apple.com/us/app/id1234567890
    - https://itunes.apple.com/app/id1234567890
    - Escaped versions with %2F, \\x2F, etc.
    
    Args:
        text: Text content to search
        
    Returns:
        tuple or None: (app_store_id, pattern_description) if found, None otherwise
    """
    patterns = [
        (
            re.compile(PATTERN_APPSTORE_STANDARD, re.IGNORECASE),
            "Pattern 1: Standard Apple URL (apps.apple.com or itunes.apple.com with optional country code and app name)"
        ),
        (
            re.compile(PATTERN_APPSTORE_ESCAPED, re.IGNORECASE),
            "Pattern 2: Escaped Apple URL (URL encoded %2F, hex escaped \\x2F, etc.)"
        ),
        (
            re.compile(PATTERN_APPSTORE_DIRECT, re.IGNORECASE),
            "Pattern 3: Direct app/id pattern (/app/id followed by 9-10 digits)"
        ),
        (
        re.compile(PATTERN_APPSTORE_JSON),
            "Pattern 4: JSON appId field"
        ),
    ]
    
    for pattern, description in patterns:
        match = pattern.search(text)
        if match:
            return (match.group(1), description)
    
    return None

