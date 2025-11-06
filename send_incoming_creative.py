#!/usr/bin/env python3
"""
Send Incoming Creative to Admin API

This script safely selects one or more creatives from PostgreSQL `creatives_fresh`
with statuses in ('completed', 'sync_failed') that have not been synced yet, marks
them as syncing to avoid duplicate work, builds the payload expected by the admin
server, and sends it to https://magictransparency.com/api/new-creative using the
shared-secret header. On success (HTTP 200 or 201), the row is marked as synced.
On error, the row is marked as sync_failed with an error message.

CLI flags:
  --limit N              Number of rows to send (default: 1)
  --secret SECRET        Override INCOMING_SHARED_SECRET constant
  --dry-run              Do not modify DB or call network; just print payloads
  --skip-empty-videos    Skip rows with empty youtube_video_ids
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx
import psycopg2
from psycopg2.extras import RealDictCursor
 


# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

API_BASE_URL = "https://magictransparency.com"
API_ENDPOINT = f"{API_BASE_URL}/api/new-creative"

# Default shared secret (can be overridden by env var or --secret flag)
INCOMING_SHARED_SECRET = "ad2a58397cf97c8bdf5814a95e33b2c17490933d9255e3e10d55ed36a665449e"

# Path to shared secret config file
SECRET_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "shared_secret.txt")

def load_secret_from_file() -> Optional[str]:
    """Load shared secret from config file if it exists."""
    try:
        if os.path.exists(SECRET_CONFIG_PATH):
            with open(SECRET_CONFIG_PATH, 'r') as f:
                secret = f.read().strip()
                if secret:
                    return secret
    except Exception:
        pass
    return None

# Reuse local DB config style for consistency with other project scripts
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432,
}


# ----------------------------------------------------------------------------
# Database Helpers
# ----------------------------------------------------------------------------

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def claim_rows(limit: int) -> List[Dict[str, Any]]:
    """
    Atomically claim up to `limit` rows by setting status='syncing' using
    SELECT FOR UPDATE SKIP LOCKED to avoid race with other processes.
    Returns claimed rows with needed fields (including advertiser_name).
    """
    sql = """
        WITH selected AS (
            SELECT cf.id
            FROM creatives_fresh cf
            WHERE cf.status IN ('completed', 'sync_failed')
              AND (cf.sync IS NOT TRUE)
              AND cf.appstore_id IS NOT NULL
            ORDER BY cf.created_at
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        )
        UPDATE creatives_fresh AS cf
        SET status = 'syncing'
        FROM selected s
        WHERE cf.id = s.id
        RETURNING cf.id,
                  cf.creative_id,
                  cf.advertiser_id,
                  (
                    SELECT a.advertiser_name
                    FROM advertisers a
                    WHERE a.advertiser_id = cf.advertiser_id
                  ) AS advertiser_name,
                  cf.appstore_id,
                  cf.video_ids,
                  cf.funded_by,
                  cf.country_presence,
                  cf.created_at,
                  cf.scraped_at
    """
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()
            conn.commit()
            return [dict(r) for r in rows]


def select_rows_preview(limit: int) -> List[Dict[str, Any]]:
    """
    Read-only preview for --dry-run (no locks or updates).
    """
    sql = """
        SELECT cf.id,
               cf.creative_id,
               cf.advertiser_id,
               a.advertiser_name,
               cf.appstore_id,
               cf.video_ids,
               cf.funded_by,
               cf.country_presence,
               cf.created_at,
               cf.scraped_at
        FROM creatives_fresh cf
        LEFT JOIN advertisers a ON a.advertiser_id = cf.advertiser_id
        WHERE cf.status IN ('completed', 'sync_failed')
          AND (cf.sync IS NOT TRUE)
          AND cf.appstore_id IS NOT NULL
        ORDER BY cf.created_at
        LIMIT %s
    """
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()
            return [dict(r) for r in rows]


def mark_synced(row_id: int) -> None:
    sql = """
        UPDATE creatives_fresh
        SET sync = TRUE,
            status = 'synced',
            error_message = NULL
        WHERE id = %s
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (row_id,))
            conn.commit()


def mark_sync_failed(row_id: int, error_message: str) -> None:
    # Truncate overly long errors to keep row light
    max_len = 2000
    safe_message = (error_message or "").strip()
    if len(safe_message) > max_len:
        safe_message = safe_message[: max_len - 3] + "..."
    sql = """
        UPDATE creatives_fresh
        SET status = 'sync_failed',
            error_message = %s
        WHERE id = %s
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (safe_message, row_id))
            conn.commit()


# ----------------------------------------------------------------------------
# Payload Builder
# ----------------------------------------------------------------------------

def _parse_video_ids(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            # normalize to list of strings
            vids = [str(v) for v in data if v is not None]
            # de-duplicate while preserving order
            seen = set()
            result: List[str] = []
            for v in vids:
                if v not in seen:
                    seen.add(v)
                    result.append(v)
            # Allow 0–3 items; slice at 3
            return result[:3]
        return []
    except Exception:
        return []


def _parse_countries(raw: Optional[Any]) -> Optional[Dict[str, str]]:
    """Normalize country_presence JSONB to {str(country_code): iso_date}.

    Accepts dict (already parsed), JSON string, or None. Ensures keys are str and
    values are YYYY-MM-DD strings. Returns None if result is empty or invalid.
    """
    if raw is None:
        return None
    data: Any = raw
    try:
        if isinstance(raw, str):
            data = json.loads(raw)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    result: Dict[str, str] = {}
    for k, v in data.items():
        if v is None:
            continue
        key_str = str(k)
        val_str = str(v)
        # Basic guard for ISO date format length (YYYY-MM-DD)
        if len(val_str) == 10:
            result[key_str] = val_str

    return result or None


def build_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    creative_id: str = row.get('creative_id') or ''
    advertiser_id: str = row.get('advertiser_id') or ''
    advertiser_name: Optional[str] = row.get('advertiser_name')
    appstore_id: Optional[str] = row.get('appstore_id')
    funded_by: Optional[str] = row.get('funded_by')
    country_presence: Optional[Any] = row.get('country_presence')
    created_at: Optional[datetime] = row.get('created_at')
    scraped_at: Optional[datetime] = row.get('scraped_at')
    video_ids: List[str] = _parse_video_ids(row.get('video_ids'))

    # Fallback for required advertiser_name if missing
    if not advertiser_name:
        advertiser_name = advertiser_id or "Unknown Advertiser"

    payload: Dict[str, Any] = {
        "transparency_creative_id": creative_id.strip(),
        "transparency_advertiser_id": advertiser_id.strip(),
        "transparency_advertiser_name": advertiser_name.strip(),
        "appstore_id": (appstore_id or "").strip(),
        "youtube_video_ids": video_ids,
    }

    # Optional sponsor field (new schema)
    if funded_by:
        sponsor_name_value = funded_by.strip()
        if sponsor_name_value:
            advertiser_name_value = (advertiser_name or "").strip()
            # Exclude sponsor_name if it equals transparency_advertiser_name
            if sponsor_name_value.lower() != advertiser_name_value.lower():
                payload["sponsor_name"] = sponsor_name_value

    # Optional countries field from country_presence (new schema)
    countries = _parse_countries(country_presence)
    if countries:
        payload["countries"] = countries

    # Optional creative_date as YYYY-MM-DD (from created_at with a 2-day rule)
    # Rule: if created_at + 2 days > current UTC time, use today's UTC date; else use created_at's date.
    if created_at:
        try:
            now_utc = datetime.utcnow()
            if created_at + timedelta(days=2) > now_utc:
                payload["creative_date"] = now_utc.date().isoformat()
            else:
                payload["creative_date"] = created_at.date().isoformat()
        except Exception:
            pass
    elif scraped_at:
        # Fallback to previous behavior only if created_at is missing
        try:
            payload["creative_date"] = scraped_at.date().isoformat()
        except Exception:
            pass

    return payload


# ----------------------------------------------------------------------------
# HTTP Sender
# ----------------------------------------------------------------------------

def send_payload(payload: Dict[str, Any], secret: str, client: httpx.Client) -> Tuple[bool, int, Dict[str, Any]]:
    """Send payload using a shared HTTP client for connection reuse."""
    headers = {
        "Content-Type": "application/json",
        "X-Incoming-Secret": secret,
    }
    resp = client.post(API_ENDPOINT, json=payload, headers=headers)
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text}
    success = resp.status_code in (200, 201)
    return success, resp.status_code, data


def process_single_row(row: Dict[str, Any], secret: str, client: httpx.Client, skip_empty_videos: bool) -> Tuple[int, bool, Optional[str]]:
    """Process a single row and return (row_id, success, error_message)."""
    row_id = row["id"]
    payload = build_payload(row)
    
    if skip_empty_videos and not payload.get("youtube_video_ids"):
        return (row_id, False, "Skipped: empty youtube_video_ids")
    
    try:
        ok, status_code, data = send_payload(payload, secret, client)
        if ok:
            mark_synced(row_id)
            msg = data.get("message") if isinstance(data, dict) else None
            return (row_id, True, None)
        else:
            detail: Optional[str] = None
            if isinstance(data, dict):
                detail = data.get("detail") or data.get("message") or json.dumps(data)[:200]
            error_msg = f"HTTP {status_code}: {detail or 'Unknown error'}"
            mark_sync_failed(row_id, error_msg)
            return (row_id, False, error_msg)
    except httpx.RequestError as e:
        error_msg = f"Network error: {type(e).__name__}: {str(e)}"
        mark_sync_failed(row_id, error_msg)
        return (row_id, False, error_msg)
    except Exception as e:
        error_msg = f"Unexpected error: {type(e).__name__}: {str(e)}"
        mark_sync_failed(row_id, error_msg)
        return (row_id, False, error_msg)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send new creatives to admin API")
    parser.add_argument("--limit", type=int, default=1, help="Number of rows to send (default: 1)")
    parser.add_argument("--secret", type=str, help="Shared secret override (else INCOMING_SHARED_SECRET constant)")
    parser.add_argument("--dry-run", action="store_true", help="Preview rows and payloads without DB/network side-effects")
    parser.add_argument("--skip-empty-videos", action="store_true", help="Skip rows with empty youtube_video_ids []")
    parser.add_argument("--concurrency", type=int, default=10, help="Number of concurrent requests (default: 10)")
    parser.add_argument("--timeout", type=float, default=10.0, help="Request timeout in seconds (default: 10.0)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # Always use INCOMING_SHARED_SECRET constant, but allow override via --secret flag
    secret = args.secret or INCOMING_SHARED_SECRET

    if args.dry_run:
        rows = select_rows_preview(args.limit)
    else:
        rows = claim_rows(args.limit)

    if not rows:
        print("✓ No eligible rows to send")
        return 0

    total = len(rows)
    print(f"Found {total} row(s) to process")

    if args.dry_run:
        for r in rows:
            row_id = r["id"]
            payload = build_payload(r)
            print(f"[DRY-RUN] id={row_id} creative={payload.get('transparency_creative_id')} payload=")
            print(json.dumps(payload, ensure_ascii=False))
    else:
        successes = 0
        failures = 0
        
        # Create a single HTTP client for connection reuse
        with httpx.Client(timeout=args.timeout) as client:
            # Use ThreadPoolExecutor for concurrent requests
            with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
                # Submit all tasks
                futures = {
                    executor.submit(process_single_row, r, secret, client, args.skip_empty_videos): r
                    for r in rows
                }
                
                # Process results as they complete
                for future in as_completed(futures):
                    try:
                        row_id, success, error_msg = future.result()
                        if success:
                            successes += 1
                            print(f"- ✓ id={row_id} -> synced")
                        else:
                            failures += 1
                            if error_msg and "Skipped" in error_msg:
                                print(f"- Skip id={row_id} ({error_msg})")
                            else:
                                print(f"- ✗ id={row_id} -> sync_failed ({error_msg[:100] if error_msg else 'Unknown'})")
                    except Exception as e:
                        failures += 1
                        print(f"- ✗ Error processing row: {e}")
        
        print(f"Done. Success: {successes}, Failed: {failures}")
    
    if args.dry_run:
        print(f"[DRY-RUN] Previewed {total} row(s)")

    # Non-zero exit if any failures (when not dry-run)
    return 0 if args.dry_run or failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


