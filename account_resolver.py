"""
Account number resolution loader.

Loads account_service_lookup.csv from the normalization_engines account linkage
pipeline into the account_number_resolution table. Resolves all FKs (vendor_id,
customer_id, location_id, chain_id) via lookup against services_current.

No pandas — stdlib csv only (matching production code conventions).
"""

import csv
import logging
from datetime import date
from pathlib import Path

import psycopg2.extras

from .database import get_connection, atomic_rebuild

log = logging.getLogger(__name__)

DEFAULT_SOURCE = Path(
    "/home/scstclair/projects/normalization_engines/src/normalization_engines"
    "/account_linkage/data/output/account_service_lookup.csv"
)

CONFIDENCE_MAP = {
    'VOUCHER_VALIDATED':        'high',
    'DIRECT_SINGLE_VENDOR':     'medium',
    'SUBSTRING_SINGLE_VENDOR':  'low',
    'DIRECT_MULTI_VENDOR':      'low',
}

CONFIDENCE_RANK = {'high': 0, 'medium': 1, 'low': 2}


def _build_service_lookup(cursor) -> dict[str, tuple]:
    """Build {service_id: (vendor_id, customer_id, location_id, chain_id)} from services_current."""
    cursor.execute("""
        SELECT service_id, vendor_id, customer_id, location_id, chain_id
        FROM services_current
    """)
    return {
        str(row['service_id']): (
            row['vendor_id'], row['customer_id'],
            row['location_id'], row['chain_id'],
        )
        for row in cursor.fetchall()
    }


def resolve_accounts(source: Path = None) -> int:
    """Load account resolutions from linkage CSV into account_number_resolution.

    1. Build service lookup from services_current (for FK resolution)
    2. Read CSV, skip rows whose service_id isn't in the DB
    3. Dedup on UNIQUE key (vendor_id, hauler_account_number, location_id),
       keeping highest-confidence row per group
    4. Atomic rebuild + bulk insert

    Returns count of rows inserted.
    """
    csv_path = source or DEFAULT_SOURCE

    if not csv_path.exists():
        print(f"  Source file not found: {csv_path}")
        return 0

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Step 1: Build service lookup
    svc_lookup = _build_service_lookup(cursor)
    log.info("services_current: %d rows in lookup", len(svc_lookup))

    # Step 2: Read CSV and resolve FKs
    today = date.today()
    candidates = []
    total_rows = 0
    skipped_no_service = 0
    skipped_no_account = 0
    skipped_unknown_link = 0

    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows += 1
            service_id = (row.get('service_id') or '').strip()
            account_number = (row.get('account_number') or '').strip()
            link_type = (row.get('link_type') or '').strip()

            if not account_number:
                skipped_no_account += 1
                continue

            if service_id not in svc_lookup:
                skipped_no_service += 1
                continue

            confidence = CONFIDENCE_MAP.get(link_type)
            if confidence is None:
                skipped_unknown_link += 1
                continue

            vendor_id, customer_id, location_id, chain_id = svc_lookup[service_id]

            candidates.append({
                'vendor_id': vendor_id,
                'hauler_account_number': account_number,
                'customer_id': customer_id,
                'location_id': location_id,
                'chain_id': chain_id,
                'service_id': service_id,
                'match_confidence': confidence,
                'match_method': link_type,
            })

    log.info("CSV rows: %d total, %d matched to DB, %d skipped (no service), "
             "%d skipped (no account), %d skipped (unknown link_type)",
             total_rows, len(candidates), skipped_no_service,
             skipped_no_account, skipped_unknown_link)

    # Step 3: Dedup on UNIQUE key — keep highest confidence per group
    deduped = {}
    for c in candidates:
        key = (c['vendor_id'], c['hauler_account_number'], c['location_id'], c['service_id'])
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = c
        else:
            # Keep higher confidence (lower rank number)
            if CONFIDENCE_RANK[c['match_confidence']] < CONFIDENCE_RANK[existing['match_confidence']]:
                deduped[key] = c

    records = list(deduped.values())
    log.info("After dedup: %d unique (vendor_id, account, location_id, service_id) keys", len(records))

    # Step 4: Atomic rebuild + bulk insert
    with atomic_rebuild(conn, ['account_number_resolution']) as cur:
        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO account_number_resolution (
                vendor_id, hauler_account_number, customer_id, location_id,
                chain_id, service_id, match_confidence, match_method,
                first_verified_date, last_verified_date, verification_count, is_active
            ) VALUES %s""",
            [
                (
                    r['vendor_id'], r['hauler_account_number'],
                    r['customer_id'], r['location_id'],
                    r['chain_id'], r['service_id'],
                    r['match_confidence'], r['match_method'],
                    today, today, 1, True,
                )
                for r in records
            ],
            page_size=1000,
        )

    conn.close()

    # Confidence breakdown
    breakdown = {}
    for r in records:
        conf = r['match_confidence']
        breakdown[conf] = breakdown.get(conf, 0) + 1

    log.info("Inserted %d account resolutions:", len(records))
    for conf in ('high', 'medium', 'low'):
        if conf in breakdown:
            log.info("  %s: %d", conf, breakdown[conf])

    return len(records)
