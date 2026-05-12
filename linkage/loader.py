"""
Pull vw_sharepoint_gapi_all → invoice_registry.

Connects to Azure SQL, queries the Doc AI extraction view, and upserts
into invoice_registry. GAPI columns become the baseline; regex/manual
columns are preserved across re-runs via ON CONFLICT DO UPDATE.
"""

import logging
from datetime import date

import psycopg2.extras

from ..azure_helpers import get_azure_connection, fmt_date, decimal_to_float
from ..database import get_connection

log = logging.getLogger(__name__)

FETCH_SIZE = 10_000
COMMIT_EVERY = 5_000

# Columns we SELECT from the GAPI view
GAPI_QUERY = """
    SELECT
        invoice_md5,
        vendor_name,
        service_address,
        invoice_date,
        invoice_amount,
        account_number,
        invoice_number,
        counterparty,
        site_state,
        status,
        created_date AS sp_created_date
    FROM dbo.vw_sharepoint_gapi_all
    WHERE invoice_md5 IS NOT NULL
      AND status NOT IN ('Obsolete', 'Duplicate')
"""

UPSERT_SQL = """
    INSERT INTO invoice_registry (
        invoice_md5,
        gapi_vendor_name, gapi_service_address, gapi_invoice_date,
        gapi_invoice_amount, gapi_account_number, gapi_invoice_number,
        gapi_counterparty, gapi_site_state, gapi_status,
        sp_created_date,
        resolved_vendor_name, resolved_address, resolved_invoice_date,
        resolved_invoice_amount, resolved_account_number, resolved_invoice_number,
        resolved_vendor_id, resolved_state,
        enrichment_status, match_status
    ) VALUES %s
    ON CONFLICT (invoice_md5) DO UPDATE SET
        gapi_vendor_name     = EXCLUDED.gapi_vendor_name,
        gapi_service_address = EXCLUDED.gapi_service_address,
        gapi_invoice_date    = EXCLUDED.gapi_invoice_date,
        gapi_invoice_amount  = EXCLUDED.gapi_invoice_amount,
        gapi_account_number  = EXCLUDED.gapi_account_number,
        gapi_invoice_number  = EXCLUDED.gapi_invoice_number,
        gapi_counterparty    = EXCLUDED.gapi_counterparty,
        gapi_site_state      = EXCLUDED.gapi_site_state,
        gapi_status          = EXCLUDED.gapi_status,
        sp_created_date      = EXCLUDED.sp_created_date,
        -- Recompute resolved only if no regex/manual override exists
        resolved_vendor_name = COALESCE(
            invoice_registry.manual_vendor_name,
            invoice_registry.regex_vendor_name,
            EXCLUDED.gapi_vendor_name
        ),
        resolved_address = COALESCE(
            invoice_registry.manual_service_address,
            invoice_registry.regex_service_address,
            EXCLUDED.gapi_service_address
        ),
        resolved_invoice_date = COALESCE(
            invoice_registry.manual_invoice_date,
            invoice_registry.regex_invoice_date,
            EXCLUDED.gapi_invoice_date
        ),
        resolved_invoice_amount = COALESCE(
            invoice_registry.manual_invoice_amount,
            invoice_registry.regex_invoice_amount,
            EXCLUDED.gapi_invoice_amount
        ),
        resolved_account_number = COALESCE(
            invoice_registry.manual_account_number,
            invoice_registry.regex_account_number,
            EXCLUDED.gapi_account_number
        ),
        resolved_invoice_number = COALESCE(
            invoice_registry.manual_invoice_number,
            invoice_registry.regex_invoice_number,
            EXCLUDED.gapi_invoice_number
        ),
        resolved_state = COALESCE(
            invoice_registry.manual_service_state,
            invoice_registry.regex_service_state,
            EXCLUDED.gapi_site_state
        ),
        updated_at = CURRENT_TIMESTAMP
"""


def _resolve_vendor_id(pg_cursor, vendor_name: str | None) -> int | None:
    """Resolve a vendor name to vendor_id via substring match."""
    if not vendor_name:
        return None
    name_lower = vendor_name.strip().lower()
    if not name_lower:
        return None
    pg_cursor.execute(
        "SELECT vendor_id FROM vendor WHERE LOWER(vendor_name) = %s",
        (name_lower,),
    )
    row = pg_cursor.fetchone()
    if row:
        return row[0]
    # Substring fallback
    pg_cursor.execute(
        "SELECT vendor_id FROM vendor WHERE LOWER(vendor_name) LIKE %s ORDER BY LENGTH(vendor_name) LIMIT 1",
        (f"%{name_lower}%",),
    )
    row = pg_cursor.fetchone()
    return row[0] if row else None


def _build_vendor_cache(pg_cursor) -> dict[str, int]:
    """Pre-load vendor name → vendor_id mapping for fast lookups."""
    pg_cursor.execute("SELECT vendor_id, vendor_name FROM vendor WHERE vendor_name IS NOT NULL")
    cache = {}
    for vid, vname in pg_cursor.fetchall():
        cache[vname.strip().lower()] = vid
    return cache


def _resolve_vendor_cached(cache: dict[str, int], vendor_name: str | None) -> int | None:
    """Resolve vendor_id from cache. Exact match first, then substring."""
    if not vendor_name:
        return None
    name_lower = vendor_name.strip().lower()
    if not name_lower:
        return None
    # Exact match
    if name_lower in cache:
        return cache[name_lower]
    # Substring match — find shortest vendor name that contains the query
    matches = [(k, v) for k, v in cache.items() if name_lower in k]
    if not matches:
        # Try the reverse: query contains a vendor name
        matches = [(k, v) for k, v in cache.items() if k in name_lower]
    if matches:
        matches.sort(key=lambda x: len(x[0]))
        return matches[0][1]
    return None


def load_invoice_registry() -> dict:
    """Pull GAPI view into invoice_registry.

    Returns dict with counts: total, inserted, updated, skipped, vendor_resolved.
    """
    log.info("Connecting to Azure SQL...")
    az_conn = get_azure_connection()
    az_cursor = az_conn.cursor()

    log.info("Querying vw_sharepoint_gapi_all...")
    az_cursor.execute(GAPI_QUERY)
    columns = [desc[0] for desc in az_cursor.description]

    pg_conn = get_connection()
    pg_cursor = pg_conn.cursor()

    # Pre-load vendor cache
    vendor_cache = _build_vendor_cache(pg_cursor)
    log.info("Vendor cache: %d entries", len(vendor_cache))

    total = 0
    batch = []
    vendor_resolved = 0

    while True:
        rows = az_cursor.fetchmany(FETCH_SIZE)
        if not rows:
            break

        for row in rows:
            rec = dict(zip(columns, row))
            md5 = rec.get("invoice_md5")
            if not md5:
                continue

            vendor_name = rec.get("vendor_name")
            address = rec.get("service_address")
            inv_date = fmt_date(rec.get("invoice_date"))
            inv_amount = decimal_to_float(rec.get("invoice_amount"))
            acct_num = rec.get("account_number")
            inv_num = rec.get("invoice_number")
            counterparty = rec.get("counterparty")
            site_state = rec.get("site_state")
            status = rec.get("status")
            sp_date = fmt_date(rec.get("sp_created_date"))

            vendor_id = _resolve_vendor_cached(vendor_cache, vendor_name)
            if vendor_id:
                vendor_resolved += 1

            batch.append((
                md5,
                vendor_name, address, inv_date,
                inv_amount, acct_num, inv_num,
                counterparty, site_state, status,
                sp_date,
                # Initial resolved_* = gapi_* values
                vendor_name, address, inv_date,
                inv_amount, acct_num, inv_num,
                vendor_id, site_state,
                "gapi_only", "unmatched",
            ))
            total += 1

            if len(batch) >= COMMIT_EVERY:
                psycopg2.extras.execute_values(
                    pg_cursor, UPSERT_SQL, batch, page_size=1000,
                )
                pg_conn.commit()
                log.info("  Upserted %d / %d...", total, total)
                batch = []

    # Flush remaining
    if batch:
        psycopg2.extras.execute_values(
            pg_cursor, UPSERT_SQL, batch, page_size=1000,
        )
        pg_conn.commit()

    az_conn.close()

    # Count final state
    pg_cursor.execute("SELECT COUNT(*) FROM invoice_registry")
    final_count = pg_cursor.fetchone()[0]
    pg_conn.close()

    log.info("Invoice registry: %d rows loaded (%d vendor IDs resolved)", total, vendor_resolved)
    return {
        "total_fetched": total,
        "vendor_resolved": vendor_resolved,
        "final_count": final_count,
    }
