"""
Step 8 Pipeline Orchestrator — processes charge extraction by vendor.

Fetches docs per vendor (not all 38K at once), extracts charges using the
DB-driven ExtractionEngine, writes results in per-vendor batches.

Usage (from ops_database/):
    python -m src.invoice_processing.run_step8 [--wipe] [--limit N] [--vendor NAME]
"""

import argparse
import logging
import sys
import time
from datetime import datetime

import psycopg2.extras

from .database import get_connection
from .extraction_engine import ExtractionEngine
from .gate_check import gate_check, GateBlockedError
from .db_helpers import (
    get_extraction_values_batch,
    get_confirmed_catalog_accounts,
    write_line_items,
    write_gate_results,
    write_pipeline_events,
    write_review_queue,
    wipe_line_items,
    wipe_extraction_results,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)

_DATE_FORMATS = ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%m-%d-%Y', '%B %d, %Y', '%b %d, %Y')

WRITE_BATCH = 2_000  # flush DB writes every N docs


def _parse_date(raw):
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _get_vendors() -> list[str]:
    """Get distinct vendors from step 2 extraction results (passed gate)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT er.extracted_value
        FROM ip_extraction_result er
        JOIN ip_gate_result g2 ON er.md5_hash = g2.md5_hash
            AND g2.step = 2 AND g2.gate_status = 'PASSED'
        WHERE er.field = 'detected_vendor'
          AND er.extracted_value IS NOT NULL
        ORDER BY 1
    """)
    vendors = [r[0] for r in cur.fetchall()]
    conn.close()
    return vendors


def _get_docs_for_vendor(vendor: str, limit: int = None) -> list[dict]:
    """Fetch docs needing step 8 processing for a specific vendor.

    Only returns md5_hash + raw_ocr_text for docs that:
    - Passed all upstream gates (1-7)
    - Don't have a step 8 gate result yet
    - Have detected_vendor = vendor
    """
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    sql = """
        SELECT rd.md5_hash, rd.raw_ocr_text
        FROM ip_raw_document rd
        JOIN ip_gate_result g1 ON rd.md5_hash = g1.md5_hash AND g1.step = 1 AND g1.gate_status = 'PASSED'
        JOIN ip_gate_result g2 ON rd.md5_hash = g2.md5_hash AND g2.step = 2 AND g2.gate_status = 'PASSED'
        JOIN ip_gate_result g3 ON rd.md5_hash = g3.md5_hash AND g3.step = 3 AND g3.gate_status = 'PASSED'
        JOIN ip_gate_result g4 ON rd.md5_hash = g4.md5_hash AND g4.step = 4 AND g4.gate_status = 'PASSED'
        JOIN ip_gate_result g5 ON rd.md5_hash = g5.md5_hash AND g5.step = 5 AND g5.gate_status = 'PASSED'
        JOIN ip_gate_result g6 ON rd.md5_hash = g6.md5_hash AND g6.step = 6 AND g6.gate_status = 'PASSED'
        JOIN ip_gate_result g7 ON rd.md5_hash = g7.md5_hash AND g7.step = 7 AND g7.gate_status = 'PASSED'
        JOIN ip_extraction_result ev ON rd.md5_hash = ev.md5_hash
            AND ev.field = 'detected_vendor' AND ev.extracted_value = %s
        WHERE rd.sync_status = 'OK'
        AND NOT EXISTS (
            SELECT 1 FROM ip_gate_result gr
            WHERE gr.md5_hash = rd.md5_hash AND gr.step = 8
        )
        ORDER BY rd.sp_created_date NULLS LAST
    """
    params = [vendor]
    if limit:
        sql += " LIMIT %s"
        params.append(limit)

    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def _flush_batch(line_items, gate_rows, event_rows, review_rows):
    """Write accumulated rows to DB and return empty lists."""
    conn = get_connection()
    try:
        if line_items:
            write_line_items(line_items, conn=conn)
        if gate_rows:
            write_gate_results(gate_rows, conn=conn)
        if event_rows:
            write_pipeline_events(event_rows, conn=conn)
        if review_rows:
            write_review_queue(review_rows, conn=conn)
        conn.commit()
    except Exception as e:
        log.error("Flush failed (%d items, %d gates, %d events, %d reviews): %s",
                  len(line_items), len(gate_rows), len(event_rows), len(review_rows), e)
        conn.rollback()
    finally:
        conn.close()
    return [], [], [], []


def _process_vendor(vendor: str, engine: ExtractionEngine,
                    extract_all_charges, extract_line_item_fields,
                    normalize_charge, confirmed_accounts: set,
                    header_maps: dict, limit: int = None) -> dict:
    """Process all docs for a single vendor. Returns totals dict."""
    t0 = time.monotonic()

    docs = _get_docs_for_vendor(vendor, limit=limit)
    if not docs:
        return {'vendor': vendor, 'total': 0, 'skipped': True}

    md5_list = [d['md5_hash'] for d in docs]

    # Pre-load header values for this vendor's docs
    account_map = get_extraction_values_batch(md5_list, 'hauler_account_number')
    date_map = get_extraction_values_batch(md5_list, 'invoice_date')
    amount_map = get_extraction_values_batch(md5_list, 'bill_total')

    totals = {
        'vendor': vendor, 'total': len(docs),
        'engine_extracted': 0, 'fallback_extracted': 0,
        'charges_extracted': 0, 'path_a': 0, 'path_b': 0,
        'no_charges': 0, 'review_queued': 0,
    }

    line_item_rows = []
    gate_rows = []
    event_rows = []
    review_rows = []
    processed = 0

    for doc in docs:
        md5 = doc['md5_hash']
        raw_text = (doc['raw_ocr_text'] or '').replace('\\n', '\n')
        account = account_map.get(md5, '')
        inv_date = _parse_date(date_map.get(md5))
        try:
            bill_total = float(amount_map[md5]) if md5 in amount_map else None
        except (ValueError, TypeError):
            bill_total = None

        # Primary: DB-driven ExtractionEngine
        engine_charges = engine.extract_charges(vendor, raw_text)
        charges = []
        used_engine = False

        if engine_charges:
            for ec in engine_charges:
                charges.append(type('ChargeItem', (), {
                    'charge_description': ec.get('charge_description'),
                    'amount': ec.get('amount'),
                    'qty': ec.get('qty'),
                    'unit_price': ec.get('unit_price'),
                })())

            # Quality gate: if engine charge sum is <30% of bill_total,
            # the engine missed main charges — prefer fallback
            engine_sum = sum(c.amount or 0 for c in charges)
            if bill_total and bill_total > 10 and engine_sum < bill_total * 0.30:
                charges = []  # Discard engine results, try fallback
            else:
                used_engine = True
                totals['engine_extracted'] += 1

        # Fallback: parsing_engines
        if not charges:
            try:
                charges = extract_all_charges(vendor, raw_text)
                if charges:
                    totals['fallback_extracted'] += 1
            except Exception as e:
                log.debug("Charge extraction error %s: %s", md5[:8], e)
                charges = []

        # Sanity filter: drop individual charges with unreasonable amounts.
        # Catches parsing_engines fallback bugs (e.g. work-order numbers
        # parsed as dollar amounts producing $660K charges on $3.5K invoices).
        if charges:
            max_reasonable = None
            if bill_total and bill_total > 10:
                max_reasonable = bill_total * 5  # no line > 5x invoice total
            ABS_CEILING = 500_000  # hard cap — no waste line item is $500K+

            sane = []
            for c in charges:
                amt = c.amount if isinstance(c.amount, (int, float)) else 0
                if amt == 0:  # drop $0 charges (extraction noise)
                    continue
                if abs(amt) > ABS_CEILING:
                    continue
                if max_reasonable and abs(amt) > max_reasonable:
                    continue
                sane.append(c)
            charges = sane

        if not charges:
            totals['no_charges'] += 1
            totals['review_queued'] += 1
            review_rows.append({
                'md5_hash': md5, 'step': 8,
                'fail_category': 'NO_CHARGES_EXTRACTED',
                'ai_suggestion': None, 'suggestion_confidence': None,
                'suggestion_reason': f'No charges extracted for {vendor}',
            })
            gate_rows.append({'md5_hash': md5, 'step': 8, 'gate_status': 'BLOCKED'})
            event_rows.append({
                'md5_hash': md5, 'step': 8, 'event_type': 'QUEUED_REVIEW',
                'field': 'line_items', 'value': 'NO_CHARGES_EXTRACTED',
            })
            processed += 1
            if processed % WRITE_BATCH == 0:
                line_item_rows, gate_rows, event_rows, review_rows = \
                    _flush_batch(line_item_rows, gate_rows, event_rows, review_rows)
                log.info("  %s: %d / %d (%.0f/s)",
                         vendor, processed, len(docs),
                         processed / (time.monotonic() - t0))
            continue

        # Build line items
        container_idx = 0
        invoice_level_items = []
        container_items = []

        for charge in charges:
            desc = charge.charge_description or ''
            amount = charge.amount

            norm = None
            try:
                norm = normalize_charge(vendor, desc)
            except Exception:
                pass
            charge_type = norm.charge_code if norm else desc[:100]
            classification = norm.classification if norm else None

            is_invoice_level = classification in ('fuel', 'environmental', 'admin')
            if is_invoice_level:
                invoice_level_items.append({
                    'md5_hash': md5, 'invoice_date': inv_date,
                    'invoice_total': bill_total, 'vendor': vendor,
                    'account_number': account, 'container_index': 0,
                    'equipment_type': None, 'equipment_size': None,
                    'material': None, 'schedule': None,
                    'container_id': None, 'service_id': None,
                    'charge_type': charge_type,
                    'billed_amount': amount, 'expected_amount': None,
                    'variance': None, 'variance_pct': None,
                    'status': 'PENDING',
                })
                continue

            container_idx += 1
            li_fields = {}
            try:
                li_fields = extract_line_item_fields(vendor, desc) or {}
            except Exception:
                pass

            container_items.append({
                'md5_hash': md5, 'invoice_date': inv_date,
                'invoice_total': bill_total, 'vendor': vendor,
                'account_number': account, 'container_index': container_idx,
                'equipment_type': li_fields.get('equipment_type'),
                'equipment_size': li_fields.get('equipment_size'),
                'material': li_fields.get('material'),
                'schedule': None,
                'container_id': None, 'service_id': None,
                'charge_type': charge_type,
                'billed_amount': amount, 'expected_amount': None,
                'variance': None, 'variance_pct': None,
                'status': 'PENDING',
            })

        all_items = invoice_level_items + container_items

        # Deduplicate by unique constraint key
        seen_keys: dict[tuple, int] = {}
        deduped_items = []
        for item in all_items:
            key = (item['md5_hash'], item['container_index'], item['charge_type'])
            if key in seen_keys:
                idx = seen_keys[key]
                existing = deduped_items[idx]
                if existing.get('billed_amount') is not None and item.get('billed_amount') is not None:
                    existing['billed_amount'] = float(existing['billed_amount']) + float(item['billed_amount'])
                elif item.get('billed_amount') is not None:
                    existing['billed_amount'] = item['billed_amount']
            else:
                seen_keys[key] = len(deduped_items)
                deduped_items.append(item)
        all_items = deduped_items

        totals['charges_extracted'] += len(all_items)
        line_item_rows.extend(all_items)

        is_path_b = (account, vendor) in confirmed_accounts
        if is_path_b:
            totals['path_b'] += 1
            gate_rows.append({'md5_hash': md5, 'step': 8, 'gate_status': 'PASSED'})
            event_rows.append({
                'md5_hash': md5, 'step': 8, 'event_type': 'GATE_PASSED',
                'field': 'line_items',
                'value': f'{len(all_items)} charges (Path B)',
            })
        else:
            totals['path_a'] += 1
            totals['review_queued'] += 1
            review_rows.append({
                'md5_hash': md5, 'step': 8,
                'fail_category': 'PATH_A_REVIEW',
                'ai_suggestion': f'{len(container_items)} containers, {len(invoice_level_items)} invoice-level',
                'suggestion_confidence': 'MEDIUM',
                'suggestion_reason': 'No confirmed catalog — extracted charges need HITL review',
            })
            gate_rows.append({'md5_hash': md5, 'step': 8, 'gate_status': 'BLOCKED'})
            event_rows.append({
                'md5_hash': md5, 'step': 8, 'event_type': 'QUEUED_REVIEW',
                'field': 'line_items',
                'value': f'{len(all_items)} charges (Path A)',
            })

        processed += 1

        # Flush every WRITE_BATCH docs
        if processed % WRITE_BATCH == 0:
            line_item_rows, gate_rows, event_rows, review_rows = \
                _flush_batch(line_item_rows, gate_rows, event_rows, review_rows)
            log.info("  %s: %d / %d (%.0f/s)",
                     vendor, processed, len(docs),
                     processed / (time.monotonic() - t0))

    # Final flush for this vendor
    _flush_batch(line_item_rows, gate_rows, event_rows, review_rows)

    elapsed = time.monotonic() - t0
    totals['elapsed'] = round(elapsed, 1)
    totals['docs_per_sec'] = round(len(docs) / elapsed, 1) if elapsed > 0 else 0
    return totals


def run(wipe: bool = False, limit: int = None, vendor_filter: str = None):
    """Main orchestrator — runs step 8 per vendor."""
    t0 = time.monotonic()

    # Gate check
    try:
        gate_check(8)
    except GateBlockedError as e:
        print(f"\n  GATE BLOCKED: {e}")
        return

    if wipe:
        log.info("Wiping step 8 data...")
        wipe_line_items()
        wipe_extraction_results(step=8)

    # Load engine once — patterns are cached
    engine = ExtractionEngine()
    engine.load_patterns(field='charge_line_item')

    # Import parsing_engines (fallback + normalization)
    sys.path.insert(0, '/home/scstclair/projects/parsing_engines')
    from charge_code.unified import extract_all_charges
    from line_items.line_item_extraction_module import extract_line_item_fields
    from charge_code_normalization.charge_code_normalization_engine import normalize_charge

    # Pre-load confirmed catalog accounts
    confirmed_accounts = get_confirmed_catalog_accounts()

    # Get vendors to process
    if vendor_filter:
        vendors = [vendor_filter]
    else:
        vendors = _get_vendors()

    print(f"\n  Step 8: Line Item Extraction (by vendor)")
    print(f"  {'=' * 60}")
    print(f"  Vendors: {len(vendors)}")
    print()

    grand = {
        'total': 0, 'engine_extracted': 0, 'fallback_extracted': 0,
        'charges_extracted': 0, 'path_a': 0, 'path_b': 0,
        'no_charges': 0, 'review_queued': 0,
    }

    for vendor in vendors:
        log.info("Processing: %s", vendor)
        result = _process_vendor(
            vendor, engine, extract_all_charges,
            extract_line_item_fields, normalize_charge,
            confirmed_accounts, {}, limit=limit,
        )

        if result.get('skipped'):
            print(f"  {vendor:<30s} — 0 docs (skipped)")
            continue

        # Accumulate grand totals
        for k in grand:
            grand[k] += result.get(k, 0)

        t = result['total']
        eng = result['engine_extracted']
        fb = result['fallback_extracted']
        charges = result['charges_extracted']
        elapsed = result.get('elapsed', 0)
        rate = result.get('docs_per_sec', 0)

        print(f"  {vendor:<30s}  docs={t:>6,}  engine={eng:>6,}  "
              f"fallback={fb:>5,}  charges={charges:>7,}  "
              f"{elapsed:>5.1f}s  ({rate:.0f}/s)")

    total_elapsed = time.monotonic() - t0
    t = grand['total']

    print(f"\n  {'=' * 60}")
    print(f"  TOTAL")
    print(f"    Documents:         {t:>8,}")
    if t:
        print(f"    Engine (DB):       {grand['engine_extracted']:>8,} ({grand['engine_extracted']/t*100:.1f}%)")
        print(f"    Fallback (PE):     {grand['fallback_extracted']:>8,} ({grand['fallback_extracted']/t*100:.1f}%)")
        print(f"    No charges:        {grand['no_charges']:>8,} ({grand['no_charges']/t*100:.1f}%)")
    print(f"    Charges extracted: {grand['charges_extracted']:>8,}")
    print(f"    Path A (review):   {grand['path_a']:>8,}")
    print(f"    Path B (catalog):  {grand['path_b']:>8,}")
    print(f"    Review queued:     {grand['review_queued']:>8,}")
    print(f"    Time: {total_elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(description='Step 8: Line Item Extraction (by vendor)')
    parser.add_argument('--wipe', action='store_true', help='Wipe existing step 8 data first')
    parser.add_argument('--limit', type=int, help='Max docs per vendor')
    parser.add_argument('--vendor', type=str, help='Process only this vendor')
    args = parser.parse_args()

    run(wipe=args.wipe, limit=args.limit, vendor_filter=args.vendor)


if __name__ == '__main__':
    main()
