#!/usr/bin/env python3
"""
Daily Creatives Upsert (staging + COPY + ON CONFLICT)

Reads a CSV with columns creative_id,advertiser_id, stages into a TEMP table,
and performs a transactional upsert into creatives_fresh:
  - Inserts new rows with status='pending' (implicit default)
  - On duplicate creative_id: updates advertiser_id and refreshes created_at

Notes:
- Does NOT touch status on conflict (never resets your statuses)
- Robust to extra columns in the input (we extract only the two needed columns)
"""

import os
import sys
import csv
import tempfile
from typing import Tuple

import psycopg2


DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432,
}


def normalize_source_to_two_columns(source_csv_path: str) -> Tuple[str, int, int]:
    """Create a temp CSV with only creative_id,advertiser_id columns.

    Returns: (temp_csv_path, total_rows_read, rows_written)
    """
    total_read = 0
    total_written = 0

    # Create temp file for normalized two-column CSV
    tmp = tempfile.NamedTemporaryFile(mode='w+', suffix='.csv', delete=False, newline='')
    tmp_path = tmp.name

    try:
        with open(source_csv_path, 'r', encoding='utf-8', newline='') as f_in, tmp:
            sample = f_in.read(2048)
            f_in.seek(0)
            try:
                delimiter = csv.Sniffer().sniff(sample).delimiter
            except Exception:
                delimiter = ','

            reader = csv.DictReader(f_in, delimiter=delimiter)

            writer = csv.writer(tmp)
            writer.writerow(['creative_id', 'advertiser_id'])

            for row in reader:
                total_read += 1
                creative_id = (row.get('creative_id') or '').strip()
                advertiser_id = (row.get('advertiser_id') or '').strip()
                if not creative_id or not advertiser_id:
                    continue
                writer.writerow([creative_id, advertiser_id])
                total_written += 1

        return tmp_path, total_read, total_written
    except Exception:
        # Ensure we don't leave a temp file behind on failure
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def upsert_from_normalized_csv(csv_path: str) -> Tuple[int, int]:
    """Upsert creatives from a two-column CSV using staging + COPY.

    Returns: (staged_rows, upserted_rows)
    """
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TEMP TABLE staging_daily_creatives (
                        creative_id  TEXT,
                        advertiser_id TEXT
                    ) ON COMMIT DROP;
                """)

                with open(csv_path, 'r', encoding='utf-8') as f:
                    cur.copy_expert(
                        """
                        COPY staging_daily_creatives (creative_id, advertiser_id)
                        FROM STDIN WITH (FORMAT CSV, HEADER TRUE)
                        """,
                        f
                    )

                cur.execute("SELECT COUNT(*) FROM staging_daily_creatives;")
                staged = cur.fetchone()[0]

                cur.execute(
                    """
                    INSERT INTO creatives_fresh (creative_id, advertiser_id)
                    SELECT creative_id, advertiser_id
                    FROM staging_daily_creatives
                    ON CONFLICT (creative_id)
                    DO UPDATE SET
                        advertiser_id = EXCLUDED.advertiser_id,
                        created_at    = NOW();
                    """
                )
                upserted = cur.rowcount

        return staged, upserted
    finally:
        conn.close()


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: import_creatives_daily_upsert.py <path_to_csv>")
        return 2

    source_csv = sys.argv[1]
    if not os.path.exists(source_csv):
        print(f"❌ CSV not found: {source_csv}")
        return 2

    print("=\nDAILY CREATIVES UPSERT\n=")
    print(f"Source: {source_csv}")

    tmp_csv, read_rows, written_rows = normalize_source_to_two_columns(source_csv)
    print(f"Normalized: read={read_rows}, kept={written_rows}")

    try:
        staged, upserted = upsert_from_normalized_csv(tmp_csv)
        print(f"Staged rows:   {staged}")
        print(f"Upserted rows: {upserted}")
        print("✅ Upsert complete (statuses unchanged)")
        return 0
    finally:
        try:
            os.unlink(tmp_csv)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())


