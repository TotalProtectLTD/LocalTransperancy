"""
Google Ads Transparency Scraper - Debug File Management Module

This module provides a generic debug file saving system with specialized wrapper
functions for different debug file types. All debug files are saved to the debug/
folder with consistent formatting including timestamps, metadata headers, and
comprehensive error handling.

The module includes:
- save_debug_file(): Generic function handling all common logic
- save_appstore_debug_file(): Saves App Store ID extraction debug files
- save_fletch_render_debug_file(): Saves fletch-render content.js debug files
- save_all_content_js_debug_files(): Saves all content.js responses (batch)
- save_api_response_debug_file(): Saves API response debug files
"""

import os
import re
import datetime
from typing import Dict, Any, Optional, List, Tuple

from google_ads_config import PATTERN_CREATIVE_ID_FROM_URL


# ============================================================================
# DEBUG FILE UTILITIES
# ============================================================================
# This section provides a generic debug file saving system with specialized
# wrapper functions for different debug file types:
#
# - save_debug_file(): Generic function handling all common logic
#   (directory creation, timestamp generation, file writing, error handling)
#
# - save_appstore_debug_file(): Saves App Store ID extraction debug files
# - save_fletch_render_debug_file(): Saves fletch-render content.js debug files
# - save_all_content_js_debug_files(): Saves all content.js responses (batch)
# - save_api_response_debug_file(): Saves API response debug files
#
# All debug files are saved to the debug/ folder with consistent formatting.
# ============================================================================


def sanitize_filename_part(part: str) -> str:
    """
    Sanitize a filename part by replacing unsafe characters with underscores.
    
    Keeps only alphanumeric characters, dashes, and underscores.
    All other characters are replaced with underscores.
    
    Args:
        part: The filename part to sanitize
        
    Returns:
        Sanitized string safe for use in filenames
    """
    return re.sub(r'[^a-zA-Z0-9_-]', '_', str(part))


def save_debug_file(
    file_type: str,
    filename: str,
    header_sections: Dict[str, Any],
    content: str,
    success_message: Optional[str] = None,
    print_success: bool = True,
    content_title: str = "CONTENT"
) -> None:
    """
    Generic function to save debug files with consistent formatting.
    
    This function consolidates all common debug file saving logic including
    directory creation, timestamp generation, file writing, and error handling.
    
    Args:
        file_type: String identifier for the debug file type (e.g., "APPSTORE", "API")
        filename: Complete filename to use (without path)
        header_sections: Dictionary containing metadata key-value pairs for the header
                        (e.g., {"App Store ID": "123456", "Method": "fletch-render"})
        content: The main content text to save in the file
        success_message: Optional custom success message to print (if None, use default)
        print_success: Boolean flag to control whether to print success/error messages
        content_title: Optional title for the content section (default: "CONTENT")
    
    Returns:
        None
    
    Example:
        save_debug_file(
            file_type="API RESPONSE DEBUG",
            filename="api_GetCreativeById_1_20250101_120000.txt",
            header_sections={"API Type": "GetCreativeById", "Index": "1"},
            content="<response text>",
            success_message="API debug file saved",
            content_title="API RESPONSE TEXT (Full)"
        )
    """
    import datetime
    
    # Coerce content to string to avoid NoneType issues
    content = "" if content is None else str(content)
    
    # Guard against None for header_sections
    if header_sections is None:
        header_sections = {}
    
    # Create debug directory if it doesn't exist
    debug_dir = os.path.join(os.getcwd(), 'debug')
    os.makedirs(debug_dir, exist_ok=True)
    
    # Generate timestamp for header
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    
    # Build filepath
    filepath = os.path.join(debug_dir, filename)
    
    # Format debug content with header
    debug_content = "=" * 80 + "\n"
    debug_content += f"{file_type}\n"
    debug_content += "=" * 80 + "\n"
    debug_content += f"Timestamp: {timestamp}\n"
    
    # Add all header sections
    for key, value in header_sections.items():
        debug_content += f"{key}: {value}\n"
    
    debug_content += "\n"
    debug_content += "=" * 80 + "\n"
    debug_content += f"{content_title}:\n"
    debug_content += "=" * 80 + "\n"
    debug_content += content + "\n"
    debug_content += "\n"
    debug_content += "=" * 80 + "\n"
    debug_content += "END OF DEBUG FILE\n"
    debug_content += "=" * 80 + "\n"
    
    # Write to file with error handling
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(debug_content)
        if print_success:
            if success_message:
                print(success_message)
            else:
                print(f"  💾 Debug file saved: {filename}")
    except Exception as e:
        if print_success:
            print(f"  ⚠️  Failed to save debug file: {e}")


def save_appstore_debug_file(
    app_store_id: str,
    text: str,
    method: str,
    url: str,
    creative_id: str,
    pattern_description: Optional[str] = None
) -> None:
    """
    Save debug file for App Store ID extraction.
    
    Args:
        app_store_id: The extracted App Store ID
        text: The content.js text that contained the ID
        method: Extraction method ('fletch-render' or 'creative-id')
        url: The content.js URL
        creative_id: The creative ID or fletch-render ID
        pattern_description: Description of the regex pattern that matched (optional)
    """
    import datetime
    
    # Build filename with timestamp
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    filename = f"appstore_{sanitize_filename_part(app_store_id)}_{sanitize_filename_part(method)}_{timestamp}.txt"
    
    # Build header sections dictionary
    header_sections = {
        "App Store ID": app_store_id,
        "Extraction Method": method,
        "Creative/Fletch ID": creative_id
    }
    
    if pattern_description:
        header_sections["Regex Pattern Used"] = pattern_description
    
    header_sections["Content.js URL"] = url
    
    # Call generic function
    save_debug_file(
        file_type="APP STORE ID DEBUG EXTRACTION",
        filename=filename,
        header_sections=header_sections,
        content=text,
        success_message=f"  💾 Debug file saved: {filename}",
        content_title="CONTENT.JS TEXT (Full)"
    )


def save_fletch_render_debug_file(
    fletch_render_id: str,
    text: str,
    url: str,
    creative_id: str
) -> None:
    """
    Save debug file for fletch-render content.js extraction.
    
    Args:
        fletch_render_id: The fletch-render ID
        text: The content.js text
        url: The content.js URL
        creative_id: The creative ID
    """
    import datetime
    
    # Build filename with timestamp
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    # Truncate fletch_render_id for filename (first 15 chars)
    fletch_short = fletch_render_id[:15] if len(fletch_render_id) > 15 else fletch_render_id
    filename = f"fletch_{sanitize_filename_part(fletch_short)}_{timestamp}.txt"
    
    # Build header sections dictionary
    header_sections = {
        "Fletch-Render ID": fletch_render_id,
        "Creative ID": creative_id,
        "Content.js URL": url,
        "Content.js Size": f"{len(text)} bytes"
    }
    
    # Call generic function
    save_debug_file(
        file_type="FLETCH-RENDER CONTENT.JS DEBUG",
        filename=filename,
        header_sections=header_sections,
        content=text,
        success_message=f"  💾 Fletch debug file saved: {filename}",
        content_title="CONTENT.JS TEXT (Full)"
    )




def save_all_content_js_debug_files(
    content_js_responses: List[Tuple[str, str]]
) -> None:
    """
    Save ALL content.js responses to debug folder (enhanced debug-content mode).
    
    Args:
        content_js_responses: List of (url, text) tuples
    """
    import datetime
    
    # Pre-create debug directory once before looping
    debug_dir = os.path.join(os.getcwd(), 'debug')
    os.makedirs(debug_dir, exist_ok=True)
    
    # Loop through content_js_responses
    for idx, (url, text) in enumerate(content_js_responses, 1):
        # Extract creative ID from URL
        creative_id = 'unknown'
        match = re.search(PATTERN_CREATIVE_ID_FROM_URL, url)
        if match:
            creative_id = match.group(1)
        
        # Build filename with timestamp
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = f"all_content_{sanitize_filename_part(creative_id)}_{idx}_{timestamp}.txt"
        
        # Build header sections dictionary
        header_sections = {
            "Creative ID": creative_id,
            "File Index": f"{idx} of {len(content_js_responses)}",
            "Content.js URL": url,
            "Content.js Size": f"{len(text)} bytes"
        }
        
        # Call generic function with error handling
        try:
            save_debug_file(
                file_type="ALL CONTENT.JS DEBUG (COMPLETE CAPTURE)",
                filename=filename,
                header_sections=header_sections,
                content=text,
                print_success=False,
                content_title="CONTENT.JS TEXT (Full)"
            )
        except Exception as e:
            print(f"  ⚠️  Failed to save all_content debug file {idx}: {e}")


def save_api_response_debug_file(
    api_response: Dict[str, Any],
    index: int
) -> None:
    """
    Save API response (GetCreativeById, SearchCreatives) to debug folder.
    
    Args:
        api_response: Dict with 'url', 'text', 'type', 'timestamp'
        index: Index number of this API response
    """
    import datetime
    
    # Extract data from api_response dict
    api_type = api_response.get('type', 'unknown')
    url = api_response.get('url', 'N/A')
    text = api_response.get('text', '')
    captured_at = api_response.get('timestamp', 'unknown')
    
    # Build filename with timestamp
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    filename = f"api_{sanitize_filename_part(api_type)}_{index}_{timestamp}.txt"
    
    # Build header sections dictionary
    header_sections = {
        "API Type": api_type,
        "Response Index": index,
        "Captured At": captured_at,
        "API URL": url,
        "Response Size": f"{len(text)} bytes"
    }
    
    # Call generic function with error handling
    try:
        save_debug_file(
            file_type="API RESPONSE DEBUG",
            filename=filename,
            header_sections=header_sections,
            content=text,
            print_success=False,
            content_title="API RESPONSE TEXT (Full)"
        )
    except Exception as e:
        print(f"  ⚠️  Failed to save API debug file {index}: {e}")

