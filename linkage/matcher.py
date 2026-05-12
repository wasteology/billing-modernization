"""
Match invoice_registry rows against billing_charges.

Uses business facts (vendor + address + amount + date) instead of
billing_reference, which fans out to 1,000+ service_ids on grouped billing.

Pre-builds in-memory indexes for vendor/month lookups, then scores each
invoice against candidate billing rows by address similarity and amount.
"""

import logging
from collections import defaultdict
from datetime import date

import psycopg2.extras

from ..database import get_connection
from .address import fuzzy_address_score

log = logging.getLogger(__name__)

# Amount tolerance thresholds
AMOUNT_PCT_THRESHOLD = 0.05   # 5% for amounts > $100
AMOUNT_ABS_THRESHOLD = 10.0   # $10 for amounts <= $100
ADDRESS_MIN_SCORE = 0.7       # Minimum address score to consider a match


def _build_billing_index(cursor) -> dict:
    """Build in-memory index: (vendor_name_lower, year, month) → [billing_rows].

    Each billing row includes location info joined from services_current → location.
    """
    log.info("Building billing index...")
    cursor.execute("""
        SELECT
            bc.billing_charge_id,
            bc.service_id,
            bc.vendor_name,
            bc.invoice_date,
            bc.transaction_month,
            bc.transaction_year,
            bc.cost,
            bc.charge,
            bc.address AS bc_address,
            bc.city AS bc_city,
            bc.region AS bc_region,
            bc.postal_code AS bc_postal,
            sc.location_id,
            sc.vendor_id
        FROM billing_charges bc
        JOIN services_current sc ON bc.service_id = sc.service_id
        WHERE bc.transaction_year IS NOT NULL
          AND bc.transaction_month IS NOT NULL
          AND bc.vendor_name IS NOT NULL
    """)

    index = defaultdict(list)
    count = 0
    for row in cursor:
        vname = (row["vendor_name"] or "").strip().lower()
        key = (vname, row["transaction_year"], row["transaction_month"])
        index[key].append(row)
        count += 1

    log.info("Billing index: %d rows across %d keys", count, len(index))
    return index


def _build_location_cache(cursor) -> dict[int, dict]:
    """Build location_id → {address, city, region, postal_code} cache."""
    cursor.execute("""
        SELECT location_id, address, city, region, postal_code, customer_id
        FROM location
        WHERE address IS NOT NULL
    """)
    cache = {}
    for row in cursor:
        cache[row["location_id"]] = row
    log.info("Location cache: %d entries", len(cache))
    return cache


def _build_vendor_name_map(cursor) -> dict[int, str]:
    """Build vendor_id → vendor_name_lower map."""
    cursor.execute("SELECT vendor_id, vendor_name FROM vendor WHERE vendor_name IS NOT NULL")
    return {row["vendor_id"]: row["vendor_name"].strip().lower() for row in cursor}


def _amount_matches(invoice_amount: float | None, location_total: float) -> tuple[bool, float]:
    """Check if invoice amount is within tolerance of location billing total.

    Returns (matches: bool, residual: float).
    """
    if invoice_amount is None or invoice_amount == 0:
        return True, 0.0  # No amount to validate — don't reject

    residual = abs(invoice_amount - location_total)

    if abs(invoice_amount) > 100:
        threshold = abs(invoice_amount) * AMOUNT_PCT_THRESHOLD
    else:
        threshold = AMOUNT_ABS_THRESHOLD

    return residual <= threshold, residual


def match_invoices() -> dict:
    """Match invoice_registry rows against billing_charges.

    For each unmatched invoice:
    1. Find billing rows matching vendor for that month (±1 month)
    2. Score candidate locations by address similarity
    3. Validate amount against location billing total
    4. If 1-2 locations match → matched; 3+ → ambiguous

    Returns dict with counts.
    """
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Build indexes
    billing_index = _build_billing_index(cursor)
    location_cache = _build_location_cache(cursor)
    vendor_name_map = _build_vendor_name_map(cursor)

    # Clear previous matches (non-manual)
    cursor.execute("DELETE FROM invoice_service_match")
    deleted = cursor.rowcount
    log.info("Cleared %d previous match rows", deleted)

    # Reset match status for non-excluded invoices
    cursor.execute("""
        UPDATE invoice_registry
        SET match_status = 'unmatched', match_location_id = NULL, match_confidence = NULL
        WHERE match_status != 'excluded'
    """)
    conn.commit()

    # Fetch invoices to match
    cursor.execute("""
        SELECT invoice_md5, resolved_vendor_name, resolved_vendor_id,
               resolved_address, resolved_city, resolved_state, resolved_postal_code,
               resolved_invoice_date, resolved_invoice_amount,
               resolved_account_number, resolved_invoice_number
        FROM invoice_registry
        WHERE match_status = 'unmatched'
          AND resolved_vendor_id IS NOT NULL
    """)
    invoices = cursor.fetchall()
    log.info("Invoices to match: %d", len(invoices))

    stats = {
        "total": len(invoices),
        "matched": 0,
        "ambiguous": 0,
        "unmatched": 0,
        "no_candidates": 0,
        "match_rows_inserted": 0,
    }

    match_inserts = []
    registry_updates = []

    for inv in invoices:
        vendor_id = inv["resolved_vendor_id"]
        vendor_name_lower = vendor_name_map.get(vendor_id, "").strip().lower()

        inv_date = inv["resolved_invoice_date"]
        if not inv_date:
            stats["unmatched"] += 1
            continue

        if isinstance(inv_date, str):
            try:
                parts = inv_date.split("-")
                inv_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                stats["unmatched"] += 1
                continue

        inv_year = inv_date.year
        inv_month = inv_date.month

        # Collect candidates: exact month + ±1 month
        candidates = []
        for delta in [0, -1, 1]:
            m = inv_month + delta
            y = inv_year
            if m < 1:
                m = 12
                y -= 1
            elif m > 12:
                m = 1
                y += 1
            key = (vendor_name_lower, y, m)
            candidates.extend(billing_index.get(key, []))

        if not candidates:
            stats["no_candidates"] += 1
            stats["unmatched"] += 1
            continue

        # Group candidates by location_id
        location_billing = defaultdict(list)
        for bc in candidates:
            loc_id = bc["location_id"]
            if loc_id:
                location_billing[loc_id].append(bc)

        # Score each location
        scored_locations = []
        for loc_id, bc_rows in location_billing.items():
            loc = location_cache.get(loc_id)
            if not loc:
                continue

            # Address score (use billing row address if available, else location table)
            # Prefer billing_charges address (more specific)
            sample_bc = bc_rows[0]
            loc_addr = sample_bc["bc_address"] or (loc.get("address") or "")
            loc_city = sample_bc["bc_city"] or (loc.get("city") or "")
            loc_region = sample_bc["bc_region"] or (loc.get("region") or "")
            loc_postal = sample_bc["bc_postal"] or (loc.get("postal_code") or "")

            addr_score = fuzzy_address_score(
                inv["resolved_address"], inv["resolved_city"],
                inv["resolved_state"], inv["resolved_postal_code"],
                loc_addr, loc_city, loc_region, loc_postal,
            )

            if addr_score < ADDRESS_MIN_SCORE:
                continue

            # Amount validation: sum costs at this location for the month
            location_total = sum(
                (bc["cost"] or 0.0) for bc in bc_rows
            )
            amt_ok, residual = _amount_matches(inv["resolved_invoice_amount"], location_total)

            if not amt_ok:
                continue

            scored_locations.append({
                "location_id": loc_id,
                "customer_id": loc.get("customer_id"),
                "addr_score": addr_score,
                "residual": residual,
                "bc_rows": bc_rows,
            })

        # Determine match status
        if not scored_locations:
            stats["unmatched"] += 1
            continue

        # Sort by address score descending
        scored_locations.sort(key=lambda x: (-x["addr_score"], x["residual"]))

        if len(scored_locations) <= 2:
            match_status = "matched"
            match_confidence = "high" if scored_locations[0]["addr_score"] >= 0.8 else "medium"
            stats["matched"] += 1
        else:
            match_status = "ambiguous"
            match_confidence = "low"
            stats["ambiguous"] += 1

        # Use best location
        best = scored_locations[0]

        # Insert match rows for the best location's billing charges
        for bc in best["bc_rows"]:
            match_inserts.append((
                inv["invoice_md5"],
                bc["billing_charge_id"],
                bc["service_id"],
                best["location_id"],
                True,  # vendor_match
                best["addr_score"],
                True,  # date_match
                best["residual"],
                "vendor_address_amount",
                match_confidence,
            ))
            stats["match_rows_inserted"] += 1

        # Update registry
        registry_updates.append((
            match_status,
            best["location_id"],
            match_confidence,
            inv["invoice_md5"],
        ))

        # Commit periodically
        if len(match_inserts) >= 5000:
            _flush_matches(cursor, conn, match_inserts, registry_updates)
            match_inserts = []
            registry_updates = []

    # Final flush
    if match_inserts or registry_updates:
        _flush_matches(cursor, conn, match_inserts, registry_updates)

    conn.close()
    log.info("Matching complete: %s", stats)
    return stats


def _flush_matches(cursor, conn, match_inserts, registry_updates):
    """Batch insert matches and update registry."""
    if match_inserts:
        psycopg2.extras.execute_values(
            cursor,
            """INSERT INTO invoice_service_match
                (invoice_md5, billing_charge_id, service_id, location_id,
                 vendor_match, address_match_score, date_match, amount_residual,
                 match_method, match_confidence)
            VALUES %s""",
            match_inserts,
            page_size=1000,
        )
    if registry_updates:
        psycopg2.extras.execute_batch(
            cursor,
            """UPDATE invoice_registry
               SET match_status = %s, match_location_id = %s,
                   match_confidence = %s, updated_at = CURRENT_TIMESTAMP
               WHERE invoice_md5 = %s""",
            registry_updates,
            page_size=1000,
        )
    conn.commit()
