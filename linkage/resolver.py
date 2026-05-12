"""
Aggregate matched invoices into account_location_map.

Groups matched invoices by (vendor_id, account_number, location_id) and
computes confidence from invoice count and match quality.

Manual override rows (is_manual_override = TRUE) are preserved across rebuilds.
"""

import logging

import psycopg2.extras

from ..database import get_connection

log = logging.getLogger(__name__)


def resolve_account_locations() -> dict:
    """Build account_location_map from matched invoices.

    Groups invoice_registry rows that have:
    - match_status = 'matched'
    - resolved_account_number IS NOT NULL
    - resolved_vendor_id IS NOT NULL
    - match_location_id IS NOT NULL

    Confidence:
    - HIGH: 3+ invoices, all high-confidence matches
    - MEDIUM: 2+ invoices or mixed confidence
    - LOW: 1 invoice only

    Preserves is_manual_override = TRUE rows.

    Returns dict with counts.
    """
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Query matched invoices grouped by (vendor, account, location)
    cursor.execute("""
        SELECT
            ir.resolved_vendor_id AS vendor_id,
            ir.resolved_account_number AS account_number,
            ir.match_location_id AS location_id,
            loc.customer_id,
            COUNT(*) AS invoice_count,
            MIN(ir.resolved_invoice_date) AS first_seen,
            MAX(ir.resolved_invoice_date) AS last_seen,
            SUM(ir.resolved_invoice_amount) AS total_amount,
            -- Count high-confidence matches
            SUM(CASE WHEN ir.match_confidence = 'high' THEN 1 ELSE 0 END) AS high_count,
            SUM(CASE WHEN ir.match_confidence = 'medium' THEN 1 ELSE 0 END) AS medium_count,
            SUM(CASE WHEN ir.match_confidence = 'low' THEN 1 ELSE 0 END) AS low_count
        FROM invoice_registry ir
        JOIN location loc ON ir.match_location_id = loc.location_id
        WHERE ir.match_status = 'matched'
          AND ir.resolved_account_number IS NOT NULL
          AND ir.resolved_vendor_id IS NOT NULL
          AND ir.match_location_id IS NOT NULL
        GROUP BY ir.resolved_vendor_id, ir.resolved_account_number,
                 ir.match_location_id, loc.customer_id
    """)
    groups = cursor.fetchall()
    log.info("Account-location groups: %d", len(groups))

    if not groups:
        conn.close()
        return {"groups": 0, "inserted": 0, "manual_preserved": 0}

    # Delete non-manual rows (manual overrides survive)
    cursor.execute(
        "DELETE FROM account_location_map WHERE is_manual_override = FALSE"
    )
    deleted = cursor.rowcount
    log.info("Cleared %d non-manual rows", deleted)

    # Count remaining manual rows
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM account_location_map WHERE is_manual_override = TRUE"
    )
    manual_count = cursor.fetchone()["cnt"]

    # Build insert tuples
    inserts = []
    for g in groups:
        inv_count = g["invoice_count"]
        high = g["high_count"]

        if inv_count >= 3 and high == inv_count:
            confidence = "high"
        elif inv_count >= 2:
            confidence = "medium"
        else:
            confidence = "low"

        evidence = (
            f"{inv_count} invoices "
            f"({high} high, {g['medium_count']} medium, {g['low_count']} low)"
        )

        inserts.append((
            g["vendor_id"],
            g["account_number"],
            g["location_id"],
            g["customer_id"],
            inv_count,
            g["first_seen"],
            g["last_seen"],
            g["total_amount"],
            confidence,
            evidence,
            True,   # is_active
            False,  # is_manual_override
        ))

    # Batch insert with conflict handling (skip if manual override exists)
    psycopg2.extras.execute_values(
        cursor,
        """INSERT INTO account_location_map
            (vendor_id, hauler_account_number, location_id, customer_id,
             invoice_count, first_seen_date, last_seen_date, total_invoiced_amount,
             confidence, evidence_summary, is_active, is_manual_override)
        VALUES %s
        ON CONFLICT (vendor_id, hauler_account_number, location_id)
        DO UPDATE SET
            customer_id          = EXCLUDED.customer_id,
            invoice_count        = EXCLUDED.invoice_count,
            first_seen_date      = EXCLUDED.first_seen_date,
            last_seen_date       = EXCLUDED.last_seen_date,
            total_invoiced_amount = EXCLUDED.total_invoiced_amount,
            confidence           = EXCLUDED.confidence,
            evidence_summary     = EXCLUDED.evidence_summary,
            is_active            = TRUE,
            updated_at           = CURRENT_TIMESTAMP
        WHERE account_location_map.is_manual_override = FALSE
        """,
        inserts,
        page_size=1000,
    )
    inserted = cursor.rowcount
    conn.commit()

    # Final counts
    cursor.execute("SELECT COUNT(*) AS cnt FROM account_location_map")
    final_count = cursor.fetchone()["cnt"]

    cursor.execute("""
        SELECT COUNT(DISTINCT (vendor_id, hauler_account_number)) AS cnt
        FROM account_location_map
    """)
    unique_accounts = cursor.fetchone()["cnt"]

    conn.close()

    result = {
        "groups": len(groups),
        "inserted": inserted,
        "manual_preserved": manual_count,
        "final_count": final_count,
        "unique_accounts": unique_accounts,
    }
    log.info("Resolution complete: %s", result)
    return result
