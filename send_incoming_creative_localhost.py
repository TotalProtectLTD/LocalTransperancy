#!/usr/bin/env python3
"""
Send Incoming Creative to Admin API (Localhost)

This script safely selects one or more creatives from PostgreSQL `creatives_fresh`
with statuses in ('completed', 'sync_failed') that have not been synced yet, marks
them as syncing to avoid duplicate work, builds the payload expected by the admin
server, and sends it to http://localhost:8000/api/new-creative using the
shared-secret header. On success (HTTP 200 or 201), the row is marked as synced.
On error, the row is marked as sync_failed with an error message.

CLI flags:
  --limit N              Number of rows to send (default: 1)
  --secret SECRET        Override INCOMING_SHARED_SECRET env var or default
  --dry-run              Do not modify DB or call network; just print payloads
  --skip-empty-videos    Skip rows with empty youtube_video_ids
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
import psycopg2
from psycopg2.extras import RealDictCursor
 


# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

API_BASE_URL = "http://localhost:8000"
API_ENDPOINT = f"{API_BASE_URL}/api/new-creative"

# Default shared secret for localhost
DEFAULT_LOCALHOST_SECRET = "ad2a58397cf97c8bdf5814a95e33b2c17490933d9255e3e10d55ed36a665449e"

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
            if sponsor_name_value.lower() != advertiser_name_value.lower():
                payload["sponsor_name"] = sponsor_name_value

    # Optional countries field from country_presence (new schema)
    countries = _parse_countries(country_presence)
    if countries:
        payload["countries"] = countries

    # Optional creative_date as YYYY-MM-DD
    if scraped_at:
        try:
            payload["creative_date"] = scraped_at.date().isoformat()
        except Exception:
            pass

    return payload


# ----------------------------------------------------------------------------
# HTTP Sender
# ----------------------------------------------------------------------------

def send_payload(payload: Dict[str, Any], secret: str, timeout: float = 20.0) -> Tuple[bool, int, Dict[str, Any]]:
    headers = {
        "Content-Type": "application/json",
        "X-Incoming-Secret": secret,
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(API_ENDPOINT, json=payload, headers=headers)
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}
        success = resp.status_code in (200, 201)
        return success, resp.status_code, data


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send new creatives to admin API (localhost)")
    parser.add_argument("--limit", type=int, default=1, help="Number of rows to send (default: 1)")
    parser.add_argument("--secret", type=str, help="Shared secret override (else INCOMING_SHARED_SECRET env or default localhost secret)")
    parser.add_argument("--dry-run", action="store_true", help="Preview rows and payloads without DB/network side-effects")
    parser.add_argument("--skip-empty-videos", action="store_true", help="Skip rows with empty youtube_video_ids []")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    secret = args.secret or os.environ.get("INCOMING_SHARED_SECRET") or DEFAULT_LOCALHOST_SECRET
    if not secret and not args.dry_run:
        print("❌ Missing shared secret: set INCOMING_SHARED_SECRET, use --secret, or default will be used")
        return 2

    if args.dry_run:
        rows = select_rows_preview(args.limit)
    else:
        rows = claim_rows(args.limit)

    if not rows:
        print("✓ No eligible rows to send")
        return 0

    total = len(rows)
    print(f"Found {total} row(s) to process")

    successes = 0
    failures = 0

    for r in rows:
        row_id = r["id"]
        payload = build_payload(r)

        if args.skip_empty_videos and not payload.get("youtube_video_ids"):
            print(f"- Skip id={row_id} (empty videos)")
            if not args.dry_run:
                mark_sync_failed(row_id, "Skipped: empty youtube_video_ids")
            continue

        if args.dry_run:
            print(f"[DRY-RUN] id={row_id} creative={payload.get('transparency_creative_id')} payload=")
            print(json.dumps(payload, ensure_ascii=False))
            continue

        try:
            ok, status_code, data = send_payload(payload, secret)
            if ok:
                # Success or Duplicate (idempotent)
                mark_synced(row_id)
                successes += 1
                msg = data.get("message") if isinstance(data, dict) else None
                print(f"- ✓ id={row_id} HTTP {status_code} -> synced" + (f" ({msg})" if msg else ""))
            else:
                # Capture error details
                detail: Optional[str] = None
                if isinstance(data, dict):
                    detail = data.get("detail") or data.get("message") or json.dumps(data)[:200]
                mark_sync_failed(row_id, f"HTTP {status_code}: {detail or 'Unknown error'}")
                failures += 1
                print(f"- ✗ id={row_id} HTTP {status_code} -> sync_failed")
        except httpx.RequestError as e:
            mark_sync_failed(row_id, f"Network error: {type(e).__name__}: {str(e)}")
            failures += 1
            print(f"- ✗ id={row_id} network error -> sync_failed")
        except Exception as e:
            mark_sync_failed(row_id, f"Unexpected error: {type(e).__name__}: {str(e)}")
            failures += 1
            print(f"- ✗ id={row_id} unexpected error -> sync_failed")

    if not args.dry_run:
        print(f"Done. Success: {successes}, Failed: {failures}")
    else:
        print(f"[DRY-RUN] Previewed {total} row(s)")

    # Non-zero exit if any failures (when not dry-run)
    return 0 if args.dry_run or failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


