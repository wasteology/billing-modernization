"""
Seed ip_service_catalog from ERP data in ops_database.

Joins account_number_resolution → services_current → service_charge_tier
to build the expected container + charge catalog for invoice validation.

Usage:
    from .catalog_seeder import seed_catalog
    result = seed_catalog(vendor_filter=['Republic Services'])
"""

import logging
import sys

import psycopg2.extras

from .database import get_connection
from .db_helpers import write_service_catalog

log = logging.getLogger(__name__)

# 4 POC vendors
POC_VENDORS = ['Republic Services', 'Waste Management', 'GFL', 'Anytime Waste']


def _get_vendor_normalizer():
    """Import VendorNormalizer from normalization_engines."""
    sys.path.insert(0, '/home/scstclair/projects/normalization_engines')
    try:
        from normalization_engines import VendorNormalizer
        return VendorNormalizer()
    except ImportError:
        log.warning("Could not import VendorNormalizer — vendor names won't be normalized")
        return None


def _format_equipment_size(container_size_yards) -> str | None:
    """Convert numeric container size to display format (e.g. 8.0 → '8 YD')."""
    if container_size_yards is None:
        return None
    size = float(container_size_yards)
    if size <= 0:
        return None
    # Small sizes (< 1 yard) are likely gallons (carts)
    if size < 1:
        gallons = int(size * 100)  # 0.96 → 96
        return f"{gallons} GAL"
    int_size = int(size) if size == int(size) else size
    return f"{int_size} YD"


def seed_catalog(vendor_filter: list[str] = None, dry_run: bool = False,
                 _cancel_event=None) -> dict:
    """Seed ip_service_catalog from ERP data.

    Args:
        vendor_filter: Limit to these vendor names (default: POC_VENDORS)
        dry_run: If True, don't write — just return counts
        _cancel_event: Threading event for cancellation

    Returns:
        {vendors, services, catalog_rows, skipped_no_charges}
    """
    if vendor_filter is None:
        vendor_filter = POC_VENDORS

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get vendor_id → vendor_name mapping for our target vendors
    normalizer = _get_vendor_normalizer()

    # Load vendor table to get vendor_id → vendor_name
    cur.execute("SELECT vendor_id, vendor_name FROM vendor WHERE is_active = TRUE")
    vendor_rows = cur.fetchall()
    vendor_name_map = {r['vendor_id']: r['vendor_name'] for r in vendor_rows}

    # Find vendor_ids matching our filter (using canonical names)
    target_vendor_ids = []
    vendor_id_to_canonical = {}
    for vid, vname in vendor_name_map.items():
        canonical = vname
        if normalizer:
            try:
                cn = normalizer.get_canonical_name(vname)
                if cn:
                    canonical = cn
            except Exception:
                pass
        if canonical in vendor_filter or vname in vendor_filter:
            target_vendor_ids.append(vid)
            vendor_id_to_canonical[vid] = canonical

    if not target_vendor_ids:
        conn.close()
        log.warning("No matching vendors found for filter: %s", vendor_filter)
        return {'vendors': 0, 'services': 0, 'catalog_rows': 0, 'skipped_no_charges': 0}

    log.info("Seed catalog: %d vendors matched (%s)",
             len(target_vendor_ids),
             ', '.join(vendor_id_to_canonical.values()))

    # Load account_number_resolution for target vendors
    cur.execute("""
        SELECT DISTINCT hauler_account_number, vendor_id, service_id
        FROM account_number_resolution
        WHERE vendor_id = ANY(%s)
          AND service_id IS NOT NULL
          AND hauler_account_number IS NOT NULL
          AND is_active = TRUE
    """, (target_vendor_ids,))
    acct_rows = cur.fetchall()
    log.info("Seed catalog: %d account→service mappings", len(acct_rows))

    # Build service_id → (account_number, vendor_id) map
    service_ids = list(set(r['service_id'] for r in acct_rows))
    acct_map = {}  # service_id → {account_number, vendor_id}
    for r in acct_rows:
        # If multiple accounts map to same service, keep first
        if r['service_id'] not in acct_map:
            acct_map[r['service_id']] = {
                'account_number': r['hauler_account_number'],
                'vendor_id': r['vendor_id'],
            }

    if not service_ids:
        conn.close()
        return {'vendors': len(target_vendor_ids), 'services': 0,
                'catalog_rows': 0, 'skipped_no_charges': 0}

    # Load services_current for these service_ids
    cur.execute("""
        SELECT service_id, equipment_type, container_size_yards, schedule,
               waste_stream_id, vendor_id
        FROM services_current
        WHERE service_id = ANY(%s)
    """, (service_ids,))
    svc_rows = {r['service_id']: dict(r) for r in cur.fetchall()}

    # Load waste_stream_ref for material names
    cur.execute("SELECT waste_stream_id, waste_stream_name FROM waste_stream_ref")
    ws_map = {r['waste_stream_id']: r['waste_stream_name'] for r in cur.fetchall()}

    # Load service_charge_tier for these service_ids
    cur.execute("""
        SELECT service_id, tier, charge_type, cost, charge, charge_uom
        FROM service_charge_tier
        WHERE service_id = ANY(%s)
        ORDER BY service_id, tier
    """, (service_ids,))
    charge_rows = cur.fetchall()
    conn.close()

    # Group charges by service_id
    charges_by_svc = {}
    for r in charge_rows:
        charges_by_svc.setdefault(r['service_id'], []).append(dict(r))

    # Build catalog rows
    catalog_rows = []
    skipped_no_charges = 0
    seen_accounts = {}  # (account_number, vendor) → container_index counter

    for sid in service_ids:
        if _cancel_event and _cancel_event.is_set():
            break

        if sid not in acct_map or sid not in svc_rows:
            continue

        acct = acct_map[sid]
        svc = svc_rows[sid]
        vendor_id = acct['vendor_id']
        vendor_name = vendor_id_to_canonical.get(vendor_id, vendor_name_map.get(vendor_id, ''))
        account_number = acct['account_number']

        charges = charges_by_svc.get(sid, [])
        if not charges:
            skipped_no_charges += 1
            continue

        # Determine container_index (sequential per account+vendor)
        key = (account_number, vendor_name)
        if key not in seen_accounts:
            seen_accounts[key] = 0
        seen_accounts[key] += 1
        container_idx = seen_accounts[key]

        # Container fields
        equipment_type = svc.get('equipment_type')
        equipment_size = _format_equipment_size(svc.get('container_size_yards'))
        material = ws_map.get(svc.get('waste_stream_id'))
        schedule = svc.get('schedule')
        container_id = f"{sid}_{container_idx}"

        # One catalog row per charge_type
        for charge in charges:
            ct = charge.get('charge_type')
            if not ct:
                continue
            catalog_rows.append({
                'service_id': sid,
                'account_number': account_number,
                'vendor': vendor_name,
                'container_id': container_id,
                'container_index': container_idx,
                'equipment_type': equipment_type or 'UNKNOWN',
                'equipment_size': equipment_size,
                'material': material,
                'schedule': schedule,
                'charge_type': ct,
                'expected_rate': charge.get('charge'),
                'rate_uom': charge.get('charge_uom'),
                'catalog_status': 'BUILDING',
            })

    log.info("Seed catalog: built %d catalog rows for %d accounts (%d skipped no charges)",
             len(catalog_rows), len(seen_accounts), skipped_no_charges)

    if not dry_run and catalog_rows:
        # Truncate existing catalog for these vendors, then insert
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM ip_service_catalog WHERE vendor = ANY(%s)",
            (list(set(vendor_id_to_canonical.values())),),
        )
        conn.commit()
        conn.close()

        written = write_service_catalog(catalog_rows)
        log.info("Seed catalog: wrote %d rows", written)

    result = {
        'vendors': len(target_vendor_ids),
        'services': len(svc_rows),
        'catalog_rows': len(catalog_rows),
        'skipped_no_charges': skipped_no_charges,
    }

    print(f"\n  Catalog Seeder")
    print(f"  {'=' * 50}")
    print(f"    Vendors matched:     {result['vendors']}")
    print(f"    Services found:      {result['services']}")
    print(f"    Catalog rows built:  {result['catalog_rows']}")
    print(f"    Skipped (no charges):{result['skipped_no_charges']}")
    if dry_run:
        print(f"    (DRY RUN — nothing written)")

    return result
