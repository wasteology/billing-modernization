"""
Load raw OCR documents (md5_hash + raw_text) into the ocr_document table.

Three modes:
  load_ocr_documents() — bulk load from CSV (initial backfill)
  sync_ocr_from_bigquery() — delta sync from BigQuery (incremental)
  backfill_ocr_dates() — backfill sp_created_date from Azure SQL sharepoint_gapi

Batch safety:
  - Streams rows (CSV DictReader / BQ result iterator, not all-in-memory)
  - Batches of 500 rows via execute_values (large TEXT blobs, avg ~2KB)
  - Commits every 2,500 rows to limit transaction size
  - ON CONFLICT DO NOTHING for idempotent re-runs
"""

import csv
import logging
from pathlib import Path

import psycopg2.extras

from .database import get_connection

try:
    from ..azure_helpers import get_azure_connection
except ImportError:
    get_azure_connection = None

log = logging.getLogger(__name__)

DEFAULT_CSV = Path(
    "/home/scstclair/projects/parsing_engines/training_data/ocr_chunks/raw_ocr_text.csv"
)

BATCH_SIZE = 500
COMMIT_EVERY = 2_500
LOG_EVERY = 5_000

INSERT_SQL = """
    INSERT INTO ocr_document (md5_hash, raw_text)
    VALUES %s
    ON CONFLICT (md5_hash) DO NOTHING
"""


def load_ocr_documents(csv_path: Path = DEFAULT_CSV) -> int:
    """Stream CSV into ocr_document table with batched inserts.

    Returns the total number of rows processed (not necessarily inserted,
    due to ON CONFLICT DO NOTHING).
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    conn = get_connection()
    cursor = conn.cursor()

    batch: list[tuple[str, str]] = []
    total = 0
    skipped = 0

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            md5 = (row.get("md5_hash") or "").strip()
            text = row.get("raw_text") or ""

            if not md5 or not text:
                skipped += 1
                continue

            batch.append((md5, text))
            total += 1

            if len(batch) >= BATCH_SIZE:
                psycopg2.extras.execute_values(
                    cursor, INSERT_SQL, batch, page_size=BATCH_SIZE
                )
                batch.clear()

            if total % COMMIT_EVERY == 0:
                conn.commit()

            if total % LOG_EVERY == 0:
                log.info("  Processed %d rows...", total)

    # Flush remaining batch
    if batch:
        psycopg2.extras.execute_values(
            cursor, INSERT_SQL, batch, page_size=BATCH_SIZE
        )
    conn.commit()

    # Final count
    cursor.execute("SELECT COUNT(*) FROM ocr_document")
    db_count = cursor.fetchone()[0]
    conn.close()

    log.info("  Processed %d rows (%d skipped). Table has %d records.",
             total, skipped, db_count)
    return total


# BigQuery config
BQ_PROJECT = "academic-torch-405913"
BQ_TABLE = f"{BQ_PROJECT}.docai_invoices_normalized.raw_ocr_full_text"


def sync_ocr_from_bigquery() -> dict:
    """Delta sync: pull new OCR documents from BigQuery into ocr_document.

    1. Load existing md5_hashes from PostgreSQL
    2. Stream all rows from BigQuery, skip existing
    3. Batch insert new rows

    Returns dict with counts: existing, streamed, inserted, final.
    """
    from google.cloud import bigquery

    conn = get_connection()
    cursor = conn.cursor()

    # Step 1: existing hashes
    cursor.execute("SELECT md5_hash FROM ocr_document")
    existing = {r[0] for r in cursor.fetchall()}
    log.info("  Existing in PostgreSQL: %d", len(existing))

    # Step 2: stream from BigQuery
    client = bigquery.Client(project=BQ_PROJECT)
    query = f"SELECT md5_hash, raw_text FROM `{BQ_TABLE}`"
    rows = client.query(query).result()

    batch: list[tuple[str, str]] = []
    inserted = 0
    skipped = 0

    for row in rows:
        if not row.md5_hash or not row.raw_text or row.md5_hash in existing:
            skipped += 1
            continue

        batch.append((row.md5_hash, row.raw_text))
        inserted += 1

        if len(batch) >= BATCH_SIZE:
            psycopg2.extras.execute_values(
                cursor, INSERT_SQL, batch, page_size=BATCH_SIZE
            )
            batch.clear()

        if inserted % COMMIT_EVERY == 0:
            conn.commit()
            log.info("  Inserted %d new rows...", inserted)

    # Flush remaining
    if batch:
        psycopg2.extras.execute_values(
            cursor, INSERT_SQL, batch, page_size=BATCH_SIZE
        )
    conn.commit()

    # Final count
    cursor.execute("SELECT COUNT(*) FROM ocr_document")
    final = cursor.fetchone()[0]
    conn.close()

    log.info("  Done. %d new rows inserted (%d skipped). Table has %d records.",
             inserted, skipped, final)

    # Backfill sp_created_date from Azure SQL for any rows missing it
    dates_updated = backfill_ocr_dates()

    return {
        "existing": len(existing),
        "skipped": skipped,
        "inserted": inserted,
        "final": final,
        "dates_backfilled": dates_updated,
    }


DATE_BATCH_SIZE = 1_000
DATE_COMMIT_EVERY = 5_000


def backfill_ocr_dates() -> int:
    """Backfill sp_created_date from Azure SQL dbo.sharepoint_gapi.

    Queries Azure for (invoice_md5, sp_created_date) pairs, then batch
    updates ocr_document rows that are missing sp_created_date.

    Returns count of rows updated.
    """
    # Step 1: Find hashes missing sp_created_date in PostgreSQL
    pg_conn = get_connection()
    pg_cursor = pg_conn.cursor()
    pg_cursor.execute(
        "SELECT md5_hash FROM ocr_document WHERE sp_created_date IS NULL"
    )
    missing = {r[0] for r in pg_cursor.fetchall()}
    log.info("  ocr_document rows missing sp_created_date: %d", len(missing))

    if not missing:
        pg_conn.close()
        return 0

    # Step 2: Query Azure SQL for md5 → date mapping
    az_conn = get_azure_connection()
    az_cursor = az_conn.cursor()
    az_cursor.execute("""
        SELECT invoice_md5, sp_created_date
        FROM dbo.sharepoint_gapi
        WHERE invoice_md5 IS NOT NULL AND sp_created_date IS NOT NULL
    """)

    # Build lookup: {md5_hash: sp_created_date}
    date_map = {}
    for row in az_cursor.fetchall():
        md5, dt = row[0], row[1]
        if md5 and md5 in missing:
            date_map[md5] = dt.date() if hasattr(dt, 'date') else dt
    az_conn.close()

    log.info("  Azure GAPI dates matched: %d / %d missing", len(date_map), len(missing))

    if not date_map:
        pg_conn.close()
        return 0

    # Step 3: Batch update PostgreSQL
    updates = [(dt, md5) for md5, dt in date_map.items()]
    updated = 0

    for i in range(0, len(updates), DATE_BATCH_SIZE):
        chunk = updates[i:i + DATE_BATCH_SIZE]
        psycopg2.extras.execute_batch(
            pg_cursor,
            "UPDATE ocr_document SET sp_created_date = %s WHERE md5_hash = %s",
            chunk,
            page_size=DATE_BATCH_SIZE,
        )
        updated += len(chunk)

        if updated % DATE_COMMIT_EVERY == 0 or i + DATE_BATCH_SIZE >= len(updates):
            pg_conn.commit()
            if updated % DATE_COMMIT_EVERY == 0:
                log.info("  Updated %d / %d dates...", updated, len(updates))

    pg_conn.close()
    log.info("  Backfilled %d sp_created_date values", updated)
    return updated
