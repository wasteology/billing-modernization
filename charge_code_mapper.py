"""
Populate charge_code_mapping from billing_charges × charge_code_ref.

3-pass matching:
  1. Exact match:          billing.charge_description = ref.charge_code
  2. Case-insensitive:     LOWER(description) = LOWER(charge_code)
  3. Hardcoded typo map:   known misspellings → canonical charge_code

After mapping, backfills billing_charges.charge_code_id via the mapping table.
"""

import logging

import psycopg2.extras

from .database import get_connection, atomic_rebuild, scalar

log = logging.getLogger(__name__)

# Known typos/variants observed in billing_charges.charge_description
# Maps raw description → canonical charge_code in charge_code_ref
TYPO_MAP = {
    "Compactor Insallation": "Compactor Installation",
    "Compactor Installation ": "Compactor Installation",
    "Disposal  Charge": "Disposal Charge",
    "Fuel Surcharge industrial": "Fuel Surcharge Industrial",
    "Fuel Surcharge Industrial ": "Fuel Surcharge Industrial",
    "Fuel Surcharge commercial": "Fuel Surcharge Commercial",
    "Fuel Surcharge Commercial ": "Fuel Surcharge Commercial",
    "Enviromental Charge": "Environmental Charge",
    "Enviromental Fee": "Environmental Fee",
    "Admininstrative Fee": "Administrative Fee",
    "Regulartory Fee": "Regulatory Fee",
    "Regualtory Fee": "Regulatory Fee",
    "Regulatroy Fee": "Regulatory Fee",
    "Regulartory Cost Recovery Fee": "Regulatory Cost Recovery Fee",
    "DIsposal Charge": "Disposal Charge",
    "Displosal Charge": "Disposal Charge",
    "Fuel Surchage": "Fuel Surcharge",
    "Fuel Surchage ": "Fuel Surcharge",
    "Container Delviery": "Container Delivery",
    "Container Delivey": "Container Delivery",
    "Haul Chrage": "Haul Charge",
    "Haul Chrge": "Haul Charge",
    "Oveage Charge": "Overage Charge",
    "Ovearge Charge": "Overage Charge",
    "Contamiation Fee": "Contamination Fee",
    "Contamiantion Fee": "Contamination Fee",
    "Dry Run Chrage": "Dry Run Charge",
}


def populate_charge_code_mapping(pipeline_run_id: int = None):
    """Populate charge_code_mapping with 3-pass matching + backfill billing_charges.charge_code_id.

    Returns (mapped_count, backfilled_count).
    """
    conn = get_connection()

    with atomic_rebuild(conn, ['charge_code_mapping']) as cursor:
        # Load charge_code_ref into memory for lookups
        cursor.execute("SELECT charge_code_id, charge_code FROM charge_code_ref WHERE is_active = TRUE")
        ref_rows = cursor.fetchall()
        ref_exact = {r['charge_code']: r['charge_code_id'] for r in ref_rows}
        ref_lower = {r['charge_code'].lower(): r['charge_code_id'] for r in ref_rows if r['charge_code']}

        # Get all distinct charge_descriptions from billing
        cursor.execute("""
            SELECT DISTINCT charge_description
            FROM billing_charges
            WHERE charge_description IS NOT NULL
              AND TRIM(charge_description) != ''
        """)
        descriptions = [r['charge_description'] for r in cursor.fetchall()]
        log.info("Distinct charge descriptions in billing: %d", len(descriptions))

        mapped = []  # (raw_description, charge_code_id, match_type)
        unmapped = []

        for desc in descriptions:
            # Pass 1: Exact match
            cc_id = ref_exact.get(desc)
            if cc_id:
                mapped.append((desc, cc_id, 'exact'))
                continue

            # Pass 2: Case-insensitive
            cc_id = ref_lower.get(desc.lower())
            if cc_id:
                mapped.append((desc, cc_id, 'case_insensitive'))
                continue

            # Pass 3: Typo map
            canonical = TYPO_MAP.get(desc) or TYPO_MAP.get(desc.strip())
            if canonical:
                cc_id = ref_exact.get(canonical) or ref_lower.get(canonical.lower())
                if cc_id:
                    mapped.append((desc, cc_id, 'typo_correction'))
                    continue

            unmapped.append(desc)

        # Bulk insert mappings (vendor_id = NULL since these are global mappings)
        if mapped:
            psycopg2.extras.execute_values(
                cursor,
                """INSERT INTO charge_code_mapping
                       (vendor_id, raw_description, charge_code_id, match_type, created_date)
                   VALUES %s""",
                [(None, desc, cc_id, mt, 'now') for desc, cc_id, mt in mapped],
                page_size=1000,
            )

        exact_count = sum(1 for _, _, mt in mapped if mt == 'exact')
        ci_count = sum(1 for _, _, mt in mapped if mt == 'case_insensitive')
        typo_count = sum(1 for _, _, mt in mapped if mt == 'typo_correction')

        log.info("charge_code_mapping: %d mapped (%d exact, %d case-insensitive, %d typo), %d unmapped",
                 len(mapped), exact_count, ci_count, typo_count, len(unmapped))

        if unmapped and len(unmapped) <= 20:
            for u in sorted(unmapped):
                log.info("  unmapped: %s", u)
        elif unmapped:
            log.info("  (first 20 unmapped)")
            for u in sorted(unmapped)[:20]:
                log.info("  unmapped: %s", u)

    # Backfill billing_charges.charge_code_id from the mapping
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE billing_charges bc
        SET charge_code_id = ccm.charge_code_id
        FROM charge_code_mapping ccm
        WHERE ccm.raw_description = bc.charge_description
          AND bc.charge_code_id IS NULL
    """)
    backfilled = cursor.rowcount
    conn.commit()

    # Also backfill rows where charge_description directly matches charge_code_ref
    cursor.execute("""
        UPDATE billing_charges bc
        SET charge_code_id = ccr.charge_code_id
        FROM charge_code_ref ccr
        WHERE ccr.charge_code = bc.charge_description
          AND bc.charge_code_id IS NULL
    """)
    direct_backfill = cursor.rowcount
    conn.commit()

    total_backfilled = backfilled + direct_backfill
    total_bc = scalar(conn, "SELECT COUNT(*) FROM billing_charges")
    with_code = scalar(conn, "SELECT COUNT(*) FROM billing_charges WHERE charge_code_id IS NOT NULL")

    log.info("billing_charges.charge_code_id: %d/%d backfilled (%d via mapping, %d direct)",
             with_code, total_bc, backfilled, direct_backfill)

    conn.close()
    return len(mapped), total_backfilled
